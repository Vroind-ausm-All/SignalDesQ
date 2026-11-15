"""Erlebnisstudien mit echten Testpersonen (2.0.0-dev47, Produktreview M30).

Eine kleine Nutzerstudie zu einer Website (z. B. vor und nach einem Relaunch): Aufgaben und Fragen festlegen, Sitzungen mit
echten Testpersonen erfassen, Ergebnisse auswerten.

- **Getrennt gehalten:** Aufgabenergebnisse (geschafft / mit Hilfe / nicht geschafft, Zeit), Antworten der Testpersonen und die
  Stichprobe (Gerät, Zielgruppe ja/nein, wie gewonnen).
- **Nur echte Antworten:** Jede Sitzung braucht die Bestätigung „Antworten stammen von dieser Testperson“. Unbestätigte Sitzungen
  zählen in keiner Auswertung. SignalDesk erzeugt keine Antworten und schickt nichts an eine KI.
- **Keine Personendaten:** Testpersonen haben nur ein Kürzel (P1, P2 …); Namen gehören nicht hierher.
- **Grenzen sichtbar:** Jede Quote mit Anzahl; unter 5 Sitzungen ein Hinweis. Vorher/Nachher nur innerhalb derselben Firma.
"""
from __future__ import annotations

import re

PHASES = ('vorher', 'nachher', 'einmalig')
METHODS = ('moderiert', 'unmoderiert')
DEVICES = ('desktop', 'smartphone', 'tablet')
OUTCOMES = ('geschafft', 'mit_hilfe', 'nicht_geschafft', 'nicht_bearbeitet')
MIN_SESSIONS = 5
PERSONAL = re.compile(r'@|\+?\d[\d\s/-]{6,}')  # E-Mail-Adressen oder Telefonnummern gehören nicht in Studiendaten


def init_studies(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS studies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        proposal_id INTEGER REFERENCES proposals(id) ON DELETE SET NULL,
        title TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', phase TEXT NOT NULL DEFAULT 'einmalig', method TEXT NOT NULL DEFAULT 'moderiert',
        status TEXT NOT NULL DEFAULT 'laeuft', created_at TEXT NOT NULL DEFAULT (datetime('now')), closed_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS study_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, study_id INTEGER NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
        pos INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'aufgabe', text TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS study_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, study_id INTEGER NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
        code TEXT NOT NULL, device TEXT NOT NULL DEFAULT 'desktop', target_group TEXT NOT NULL DEFAULT 'unklar',
        recruited_via TEXT NOT NULL DEFAULT '', held_on TEXT NOT NULL DEFAULT '', confirmed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(study_id, code)
      );
      CREATE TABLE IF NOT EXISTS study_results (
        session_id INTEGER NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
        task_id INTEGER NOT NULL REFERENCES study_tasks(id) ON DELETE CASCADE,
        outcome TEXT NOT NULL DEFAULT '', seconds INTEGER, answer TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(session_id, task_id)
      );
    ''')


def _text(v, limit, what, required=False):
    if not isinstance(v, str) or len(v) > limit:
        raise ValueError(f'{what}: Text mit höchstens {limit} Zeichen.')
    v = v.strip()
    if required and not v:
        raise ValueError(f'{what}: bitte angeben.')
    return v


def _no_personal(v, what):
    if PERSONAL.search(v or ''):
        raise ValueError(f'{what}: keine E-Mail-Adressen oder Telefonnummern – Testpersonen bleiben anonym (Kürzel P1, P2 …).')
    return v


def _study(conn, sid):
    s = conn.execute('SELECT s.*, l.company FROM studies s JOIN leads l ON l.id=s.lead_id WHERE s.id=?', (sid,)).fetchone()
    if not s:
        raise LookupError('Studie nicht gefunden.')
    return s


def create(conn, data):
    if not isinstance(data, dict) or set(data) - {'lead_id', 'proposal_id', 'title', 'url', 'phase', 'method', 'tasks', 'questions'}:
        raise ValueError('Erwartet: lead_id, proposal_id, title, url, phase, method, tasks, questions.')
    if not conn.execute('SELECT 1 FROM leads WHERE id=?', (data.get('lead_id'),)).fetchone():
        raise LookupError('Firma nicht gefunden.')
    pid = data.get('proposal_id') or None
    if pid and not conn.execute('SELECT 1 FROM proposals WHERE id=? AND lead_id=?', (pid, data['lead_id'])).fetchone():
        raise ValueError('Das Angebot gehört nicht zu dieser Firma.')
    phase, method = data.get('phase', 'einmalig'), data.get('method', 'moderiert')
    if phase not in PHASES or method not in METHODS:
        raise ValueError('Phase: vorher, nachher oder einmalig; Methode: moderiert oder unmoderiert.')
    tasks, questions = data.get('tasks') or [], data.get('questions') or []
    if not isinstance(tasks, list) or not isinstance(questions, list) or not 1 <= len(tasks) + len(questions) <= 20:
        raise ValueError('1 bis 20 Aufgaben und Fragen.')
    if not tasks:
        raise ValueError('Mindestens eine Aufgabe (z. B. „Finden Sie die Telefonnummer“).')
    sid = conn.execute('INSERT INTO studies(lead_id, proposal_id, title, url, phase, method) VALUES (?,?,?,?,?,?)',
                       (data['lead_id'], pid, _text(data.get('title', ''), 120, 'Titel', True), _text(data.get('url', ''), 300, 'Website'),
                        phase, method)).lastrowid
    pos = 0
    for kind, items in (('aufgabe', tasks), ('frage', questions)):
        for t in items:
            pos += 1
            conn.execute('INSERT INTO study_tasks(study_id, pos, kind, text) VALUES (?,?,?,?)', (sid, pos, kind, _text(t, 300, 'Aufgabe/Frage', True)))
    conn.commit()
    return view(conn, sid)


def add_session(conn, sid, data):
    if not isinstance(data, dict) or set(data) - {'device', 'target_group', 'recruited_via', 'held_on'}:
        raise ValueError('Erwartet: device, target_group, recruited_via, held_on.')
    s = _study(conn, sid)
    if s['status'] != 'laeuft':
        raise ValueError('Die Studie ist abgeschlossen.')
    device, tg = data.get('device', 'desktop'), data.get('target_group', 'unklar')
    if device not in DEVICES or tg not in ('ja', 'nein', 'unklar'):
        raise ValueError('Gerät: desktop, smartphone, tablet; Zielgruppe: ja, nein, unklar.')
    held = _text(data.get('held_on', ''), 10, 'Datum')
    if held and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', held):
        raise ValueError('Datum als JJJJ-MM-TT.')
    n = conn.execute('SELECT COUNT(*) FROM study_sessions WHERE study_id=?', (sid,)).fetchone()[0] + 1
    code = f'P{n}'
    while conn.execute('SELECT 1 FROM study_sessions WHERE study_id=? AND code=?', (sid, code)).fetchone():
        n += 1
        code = f'P{n}'
    conn.execute('INSERT INTO study_sessions(study_id, code, device, target_group, recruited_via, held_on) VALUES (?,?,?,?,?,?)',
                 (sid, code, device, tg, _no_personal(_text(data.get('recruited_via', ''), 120, 'Wie gewonnen'), 'Wie gewonnen'), held))
    conn.commit()
    return view(conn, sid)


def record(conn, session_id, data):
    """Ergebnis je Aufgabe/Frage und die Bestätigung, dass die Angaben von der Testperson stammen."""
    if not isinstance(data, dict) or set(data) - {'task_id', 'outcome', 'seconds', 'answer', 'note', 'confirmed'}:
        raise ValueError('Erwartet: task_id, outcome, seconds, answer, note, confirmed.')
    se = conn.execute('SELECT ss.*, s.status FROM study_sessions ss JOIN studies s ON s.id=ss.study_id WHERE ss.id=?', (session_id,)).fetchone()
    if not se:
        raise LookupError('Sitzung nicht gefunden.')
    if se['status'] != 'laeuft':
        raise ValueError('Die Studie ist abgeschlossen.')
    if 'confirmed' in data:
        if not isinstance(data['confirmed'], bool):
            raise ValueError('confirmed: true/false.')
        conn.execute('UPDATE study_sessions SET confirmed=? WHERE id=?', (int(data['confirmed']), session_id))
    if 'task_id' in data:
        t = conn.execute('SELECT * FROM study_tasks WHERE id=? AND study_id=?', (data['task_id'], se['study_id'])).fetchone()
        if not t:
            raise ValueError('Aufgabe gehört nicht zu dieser Studie.')
        cur = conn.execute('SELECT * FROM study_results WHERE session_id=? AND task_id=?', (session_id, t['id'])).fetchone()
        row = dict(cur) if cur else {'outcome': '', 'seconds': None, 'answer': '', 'note': ''}
        if 'outcome' in data:
            if data['outcome'] not in ('', *OUTCOMES) or (t['kind'] == 'frage' and data['outcome']):
                raise ValueError('Ergebnis: geschafft, mit Hilfe, nicht geschafft, nicht bearbeitet (nur bei Aufgaben).')
            row['outcome'] = data['outcome']
        if 'seconds' in data:
            sec = data['seconds']
            if sec is not None and (type(sec) is not int or not 0 <= sec <= 7200):
                raise ValueError('Zeit in Sekunden (0–7200) oder leer.')
            row['seconds'] = sec
        if 'answer' in data:
            row['answer'] = _no_personal(_text(data['answer'], 2000, 'Antwort'), 'Antwort')
        if 'note' in data:
            row['note'] = _no_personal(_text(data['note'], 500, 'Beobachtung'), 'Beobachtung')
        conn.execute('''INSERT INTO study_results(session_id, task_id, outcome, seconds, answer, note) VALUES (?,?,?,?,?,?)
                        ON CONFLICT(session_id, task_id) DO UPDATE SET outcome=excluded.outcome, seconds=excluded.seconds,
                        answer=excluded.answer, note=excluded.note''', (session_id, t['id'], row['outcome'], row['seconds'], row['answer'], row['note']))
    conn.commit()
    return view(conn, se['study_id'])


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2)


def analysis(conn, sid):
    tasks = [dict(t) for t in conn.execute('SELECT * FROM study_tasks WHERE study_id=? ORDER BY pos', (sid,))]
    sessions = [dict(s) for s in conn.execute('SELECT * FROM study_sessions WHERE study_id=? ORDER BY id', (sid,))]
    counted = [s for s in sessions if s['confirmed']]
    ids = [s['id'] for s in counted]
    res = [dict(r) for r in conn.execute(f"SELECT * FROM study_results WHERE session_id IN ({','.join('?' * len(ids)) or 'NULL'})", ids)]
    out = []
    for t in tasks:
        rows = [r for r in res if r['task_id'] == t['id']]
        if t['kind'] == 'aufgabe':
            tried = [r for r in rows if r['outcome'] in ('geschafft', 'mit_hilfe', 'nicht_geschafft')]
            ok = sum(1 for r in tried if r['outcome'] == 'geschafft')
            helped = sum(1 for r in tried if r['outcome'] == 'mit_hilfe')
            out.append({**t, 'tried': len(tried), 'success': ok, 'helped': helped,
                        'success_pct': round(100 * ok / len(tried)) if tried else None,
                        'median_seconds': _median([r['seconds'] for r in tried if r['seconds'] is not None])})
        else:
            out.append({**t, 'answers': [{'code': next(s['code'] for s in counted if s['id'] == r['session_id']), 'text': r['answer']}
                                         for r in rows if r['answer']]})
    sample = {'sessions': len(counted), 'unconfirmed': len(sessions) - len(counted),
              'devices': {d: sum(1 for s in counted if s['device'] == d) for d in DEVICES},
              'target_group': {k: sum(1 for s in counted if s['target_group'] == k) for k in ('ja', 'nein', 'unklar')},
              'recruited': sorted({s['recruited_via'] for s in counted if s['recruited_via']})}
    task_rows = [t for t in out if t['kind'] == 'aufgabe' and t['tried']]
    overall = round(sum(t['success'] for t in task_rows) * 100 / sum(t['tried'] for t in task_rows)) if task_rows else None
    notice = ''
    if len(counted) < MIN_SESSIONS:
        notice = f'Erst {len(counted)} bestätigte Sitzung(en) – Ergebnisse zeigen Probleme, aber keine belastbaren Quoten (ab {MIN_SESSIONS}).'
    if sample['unconfirmed']:
        notice += f" {sample['unconfirmed']} Sitzung(en) ohne Bestätigung zählen nicht."
    return {'tasks': out, 'sample': sample, 'overall_success_pct': overall, 'notice': notice.strip()}


def view(conn, sid):
    s = _study(conn, sid)
    sessions = []
    for se in conn.execute('SELECT * FROM study_sessions WHERE study_id=? ORDER BY id', (sid,)):
        d = dict(se)
        d['results'] = {r['task_id']: dict(r) for r in conn.execute('SELECT * FROM study_results WHERE session_id=?', (se['id'],))}
        sessions.append(d)
    compare = None
    if s['phase'] in ('vorher', 'nachher'):
        other = conn.execute("""SELECT id FROM studies WHERE lead_id=? AND phase=? AND id<>? ORDER BY id DESC LIMIT 1""",
                             (s['lead_id'], 'nachher' if s['phase'] == 'vorher' else 'vorher', sid)).fetchone()
        if other:
            a = analysis(conn, other['id'])
            compare = {'study_id': other['id'], 'overall_success_pct': a['overall_success_pct'], 'sessions': a['sample']['sessions']}
    return {**dict(s), 'tasks': [dict(t) for t in conn.execute('SELECT * FROM study_tasks WHERE study_id=? ORDER BY pos', (sid,))],
            'sessions': sessions, 'analysis': analysis(conn, sid), 'compare': compare}


def close(conn, sid):
    _study(conn, sid)
    conn.execute("UPDATE studies SET status='abgeschlossen', closed_at=datetime('now') WHERE id=?", (sid,))
    conn.commit()
    return view(conn, sid)


def delete_session(conn, session_id):
    se = conn.execute('SELECT ss.study_id, s.status FROM study_sessions ss JOIN studies s ON s.id=ss.study_id WHERE ss.id=?', (session_id,)).fetchone()
    if not se:
        raise LookupError('Sitzung nicht gefunden.')
    if se['status'] != 'laeuft':
        raise ValueError('Die Studie ist abgeschlossen.')
    conn.execute('DELETE FROM study_sessions WHERE id=?', (session_id,))
    conn.commit()
    return view(conn, se['study_id'])


def overview(conn):
    out = []
    for s in conn.execute('SELECT s.*, l.company FROM studies s JOIN leads l ON l.id=s.lead_id ORDER BY s.id DESC LIMIT 50'):
        a = analysis(conn, s['id'])
        out.append({'id': s['id'], 'title': s['title'], 'company': s['company'], 'phase': s['phase'], 'method': s['method'],
                    'status': s['status'], 'sessions': a['sample']['sessions'], 'overall_success_pct': a['overall_success_pct']})
    return {'studies': out, 'leads': [dict(r) for r in conn.execute("SELECT id, company FROM leads WHERE stage<>'gesperrt' ORDER BY company LIMIT 500")],
            'notice': 'Erlebnisstudien mit echten Testpersonen. Nur bestätigte Sitzungen zählen; SignalDesk erzeugt keine Antworten.'}


def route_studies(h, conn, method, route):
    if route == '/api/studien':
        if method == 'GET':
            h._send(200, overview(conn))
            return True
        if method == 'POST':
            h._send(201, create(conn, h._body()))
            return True
        return False
    m = re.fullmatch(r'/api/studien/(\d+)(/sitzungen|/abschliessen)?', route)
    if m:
        sid = int(m.group(1))
        if m.group(2) == '/sitzungen' and method == 'POST':
            h._send(201, add_session(conn, sid, h._body()))
            return True
        if m.group(2) == '/abschliessen' and method == 'POST':
            h._send(200, close(conn, sid))
            return True
        if not m.group(2) and method == 'GET':
            h._send(200, view(conn, sid))
            return True
        return False
    m = re.fullmatch(r'/api/studien/sitzung/(\d+)', route)
    if m:
        if method == 'POST':
            h._send(200, record(conn, int(m.group(1)), h._body()))
            return True
        if method == 'DELETE':
            h._send(200, delete_session(conn, int(m.group(1))))
            return True
    return False
