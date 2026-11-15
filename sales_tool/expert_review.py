"""Fachreview der Website-Bewertung erfassen und die Bewertung kalibrieren (2.0.0-dev46, Produktreview M29 und M33).

M29 – Fachreview erfassen:
- Zu einer abgeschlossenen Website-Bewertung legst du ein Review an. Alle Rubriken der Bewertung stehen darin; du wählst,
  welche du prüfst (Kriterienauswahl), und trägst je Rubrik dein Urteil, einen Beleg und eine Begründung ein.
- „offen“ ist erlaubt und bleibt sichtbar. Jede Eingabe wird sofort gespeichert – ein Abbruch verliert nichts.
- Abschließen nur, wenn jede gewählte Rubrik ein Urteil mit Begründung hat und jede „auffällig“ einen Beleg.
- Festgehalten werden Prüfer, Zeitpunkt und die Bewertungsversion; das automatische Ergebnis wird beim Anlegen kopiert.

M33 – Bewertung kalibrieren:
- Je Rubrik und Bewertungsversion: wie oft dein Urteil mit dem automatischen übereinstimmt, und in welche Richtung es abweicht.
- Nur abgeschlossene Reviews und nur eindeutige Urteile (nicht „offen“/„unbekannt“) zählen.
- SignalDesk ändert **keine** Gewichte oder Regeln selbst. Die Auswertung zeigt nur, wo eine Prüfung lohnt; Änderungen machst du im
  Bewertungsraster, das daraus eine neue Version erzeugt.
"""
from __future__ import annotations

import re

VERDICTS = ('ok', 'auffaellig', 'hinweis', 'unbekannt', 'offen')
VERDICT_LABEL = {'ok': 'ok', 'auffaellig': 'auffällig', 'hinweis': 'Hinweis', 'unbekannt': 'unbekannt', 'offen': 'offen'}
CLEAR = ('ok', 'auffaellig', 'hinweis')
MIN_SAMPLE = 5


def init_expert_review(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS expert_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL REFERENCES website_audits(id) ON DELETE CASCADE,
        reviewer TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'entwurf', version_hash TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')), completed_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS expert_review_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        review_id INTEGER NOT NULL REFERENCES expert_reviews(id) ON DELETE CASCADE,
        rubric TEXT NOT NULL, area TEXT NOT NULL, label TEXT NOT NULL, auto_result TEXT NOT NULL, auto_evidence TEXT NOT NULL DEFAULT '',
        included INTEGER NOT NULL DEFAULT 1, verdict TEXT NOT NULL DEFAULT 'offen', evidence TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(review_id, rubric)
      );
      CREATE INDEX IF NOT EXISTS idx_expert_reviews_audit ON expert_reviews(audit_id);
    ''')


def _text(v, limit, what, required=False):
    if not isinstance(v, str) or len(v) > limit:
        raise ValueError(f'{what}: Text mit höchstens {limit} Zeichen.')
    v = v.strip()
    if required and not v:
        raise ValueError(f'{what}: bitte angeben.')
    return v


def create(conn, data):
    if not isinstance(data, dict) or set(data) - {'audit_id', 'reviewer'}:
        raise ValueError('Erwartet: audit_id, reviewer.')
    a = conn.execute('''SELECT a.*, v.hash FROM website_audits a LEFT JOIN score_versions v ON v.id=a.version_id WHERE a.id=?''',
                     (data.get('audit_id'),)).fetchone()
    if not a:
        raise LookupError('Bewertung nicht gefunden.')
    if a['status'] != 'done':
        raise ValueError('Nur abgeschlossene Bewertungen lassen sich prüfen.')
    reviewer = re.sub(r'\s+', ' ', _text(data.get('reviewer', ''), 80, 'Prüfer', required=True))
    rid = conn.execute('INSERT INTO expert_reviews(audit_id, reviewer, version_hash) VALUES (?,?,?)', (a['id'], reviewer, a['hash'] or '')).lastrowid
    for f in conn.execute('SELECT * FROM website_findings WHERE audit_id=? ORDER BY area, rubric', (a['id'],)):
        conn.execute('''INSERT OR IGNORE INTO expert_review_items(review_id, rubric, area, label, auto_result, auto_evidence)
                        VALUES (?,?,?,?,?,?)''', (rid, f['rubric'], f['area'], f['label'], f['result'], (f['evidence'] or '')[:500]))
    conn.commit()
    return view(conn, rid)


def _missing(items):
    out = []
    for i in items:
        if not i['included']:
            continue
        if i['verdict'] == 'offen':
            out.append(f"{i['label']}: noch offen")
        elif not i['reason']:
            out.append(f"{i['label']}: Begründung fehlt")
        elif i['verdict'] == 'auffaellig' and not i['evidence']:
            out.append(f"{i['label']}: Beleg fehlt")
    return out


def view(conn, rid):
    r = conn.execute('''SELECT r.*, l.company, a.url FROM expert_reviews r JOIN website_audits a ON a.id=r.audit_id
                        JOIN leads l ON l.id=a.lead_id WHERE r.id=?''', (rid,)).fetchone()
    if not r:
        raise LookupError('Review nicht gefunden.')
    items = [dict(x) for x in conn.execute('SELECT * FROM expert_review_items WHERE review_id=? ORDER BY area, rubric', (rid,))]
    chosen = [i for i in items if i['included']]
    return {**dict(r), 'items': items, 'missing': _missing(items), 'verdicts': VERDICTS, 'labels': VERDICT_LABEL,
            'progress': {'chosen': len(chosen), 'decided': sum(1 for i in chosen if i['verdict'] != 'offen'),
                         'agree': sum(1 for i in chosen if i['verdict'] in CLEAR and i['verdict'] == i['auto_result'])}}


def update_item(conn, item_id, data):
    if not isinstance(data, dict) or set(data) - {'included', 'verdict', 'evidence', 'reason'}:
        raise ValueError('Erwartet: included, verdict, evidence, reason.')
    row = conn.execute('''SELECT i.*, r.status FROM expert_review_items i JOIN expert_reviews r ON r.id=i.review_id WHERE i.id=?''', (item_id,)).fetchone()
    if not row:
        raise LookupError('Rubrik nicht gefunden.')
    if row['status'] != 'entwurf':
        raise ValueError('Abgeschlossene Reviews sind unveränderlich. Bei Bedarf ein neues Review anlegen.')
    sets, args = [], []
    if 'included' in data:
        if not isinstance(data['included'], bool):
            raise ValueError('included: true/false.')
        sets.append('included=?')
        args.append(int(data['included']))
    if 'verdict' in data:
        if data['verdict'] not in VERDICTS:
            raise ValueError('Urteil: ' + ', '.join(VERDICT_LABEL.values()) + '.')
        sets.append('verdict=?')
        args.append(data['verdict'])
    for key, limit in (('evidence', 500), ('reason', 1000)):
        if key in data:
            sets.append(f'{key}=?')
            args.append(_text(data[key], limit, 'Beleg' if key == 'evidence' else 'Begründung'))
    if sets:
        conn.execute(f"UPDATE expert_review_items SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?", (*args, item_id))
        conn.execute("UPDATE expert_reviews SET updated_at=datetime('now') WHERE id=?", (row['review_id'],))
        conn.commit()
    return view(conn, row['review_id'])


def complete(conn, rid, data):
    if not isinstance(data, dict) or set(data) - {'note'}:
        raise ValueError('Erwartet: note.')
    v = view(conn, rid)
    if v['status'] != 'entwurf':
        raise ValueError('Review ist bereits abgeschlossen.')
    if not v['progress']['chosen']:
        raise ValueError('Mindestens eine Rubrik auswählen.')
    if v['missing']:
        raise ValueError('Noch nicht vollständig: ' + '; '.join(v['missing'][:5]) + (' …' if len(v['missing']) > 5 else ''))
    conn.execute("UPDATE expert_reviews SET status='abgeschlossen', note=?, completed_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
                 (_text(data.get('note', ''), 1000, 'Notiz'), rid))
    conn.commit()
    return view(conn, rid)


def delete(conn, rid):
    row = conn.execute('SELECT status FROM expert_reviews WHERE id=?', (rid,)).fetchone()
    if not row:
        raise LookupError('Review nicht gefunden.')
    if row['status'] != 'entwurf':
        raise ValueError('Abgeschlossene Reviews bleiben für die Kalibrierung erhalten.')
    conn.execute('DELETE FROM expert_reviews WHERE id=?', (rid,))
    conn.commit()
    return {'deleted': True}


def overview(conn):
    reviews = [dict(r) for r in conn.execute('''SELECT r.id, r.audit_id, r.reviewer, r.status, r.version_hash, r.created_at, r.completed_at, l.company
                                               FROM expert_reviews r JOIN website_audits a ON a.id=r.audit_id JOIN leads l ON l.id=a.lead_id
                                               ORDER BY r.id DESC LIMIT 50''')]
    audits = [dict(r) for r in conn.execute('''SELECT a.id, l.company, a.url, a.finished_at, v.hash AS version FROM website_audits a
                                              JOIN leads l ON l.id=a.lead_id LEFT JOIN score_versions v ON v.id=a.version_id
                                              WHERE a.status='done' ORDER BY a.id DESC LIMIT 50''')]
    return {'reviews': reviews, 'audits': audits, 'calibration': calibration(conn)}


def calibration(conn):
    """Übereinstimmung je Bewertungsversion und Rubrik – nur abgeschlossene Reviews, nur eindeutige Urteile."""
    rows = conn.execute('''SELECT r.version_hash, i.rubric, i.label, i.auto_result, i.verdict FROM expert_review_items i
                           JOIN expert_reviews r ON r.id=i.review_id
                           WHERE r.status='abgeschlossen' AND i.included=1 AND i.verdict IN ('ok','auffaellig','hinweis')''').fetchall()
    groups = {}
    for x in rows:
        g = groups.setdefault((x['version_hash'], x['rubric']), {'version': x['version_hash'], 'rubric': x['rubric'], 'label': x['label'],
                                                                  'n': 0, 'agree': 0, 'directions': {}})
        g['n'] += 1
        if x['verdict'] == x['auto_result']:
            g['agree'] += 1
        else:
            key = f"{VERDICT_LABEL.get(x['auto_result'], x['auto_result'])} → {VERDICT_LABEL[x['verdict']]}"
            g['directions'][key] = g['directions'].get(key, 0) + 1
    out = []
    for g in groups.values():
        g['pct'] = round(100 * g['agree'] / g['n'])
        g['enough'] = g['n'] >= MIN_SAMPLE
        g['flag'] = g['enough'] and g['pct'] < 70
        out.append(g)
    out.sort(key=lambda g: (g['version'], not g['flag'], g['pct'], g['rubric']))
    completed = conn.execute("SELECT COUNT(*) FROM expert_reviews WHERE status='abgeschlossen'").fetchone()[0]
    return {'rows': out, 'completed_reviews': completed, 'min_sample': MIN_SAMPLE,
            'notice': (f'Aus {completed} abgeschlossenen Review(s). Rubriken mit weniger als {MIN_SAMPLE} Urteilen sind nur ein erster Eindruck. '
                       'SignalDesk ändert keine Gewichte selbst – Änderungen im Bewertungsraster erzeugen eine neue Version, '
                       'Übereinstimmungen werden je Version getrennt gezählt.')}


def route_expert_review(h, conn, method, route):
    if route == '/api/fachreview':
        if method == 'GET':
            h._send(200, overview(conn))
            return True
        if method == 'POST':
            h._send(201, create(conn, h._body()))
            return True
        return False
    m = re.fullmatch(r'/api/fachreview/(\d+)(/abschliessen)?', route)
    if m:
        rid = int(m.group(1))
        if m.group(2) and method == 'POST':
            h._send(200, complete(conn, rid, h._body()))
            return True
        if not m.group(2) and method == 'GET':
            h._send(200, view(conn, rid))
            return True
        if not m.group(2) and method == 'DELETE':
            h._send(200, delete(conn, rid))
            return True
        return False
    m = re.fullmatch(r'/api/fachreview/rubrik/(\d+)', route)
    if m and method == 'POST':
        h._send(200, update_item(conn, int(m.group(1)), h._body()))
        return True
    return False
