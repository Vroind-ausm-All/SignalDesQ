"""Nachkalkulation (2.0.0-dev5): tatsächliche Stunden je angenommenem Festpreisangebot.

Für das Festpreisgeschäft die entscheidende Frage: Lohnt sich der Auftrag bei der Zeit, die er wirklich gebraucht hat?
- Zeiten werden von Hand je Auftrag erfasst (kein Tracker, keine Stoppuhr).
- Verglichen wird mit der internen Kalkulation des Angebots; der Kunde sieht davon nichts.
- Die Auslastung rechnet mit den verbleibenden Stunden, sobald Zeiten erfasst sind oder der Auftrag abgeschlossen ist.
Rechnungen und festgeschriebene Belege werden nicht berührt.
"""
from __future__ import annotations

import datetime as dt
import json
import re


def init_postcalc(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS time_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
        work_date TEXT NOT NULL, hours REAL NOT NULL, note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_time_entries_proposal ON time_entries(proposal_id, work_date);
      CREATE TABLE IF NOT EXISTS project_closings (
        proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
        done_at TEXT NOT NULL, actual_external_eur REAL, note TEXT NOT NULL DEFAULT ''
      );
    ''')


def _json(text):
    try:
        v = json.loads(text or '{}')
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _de(value, digits=None):
    """Zahl in deutscher Schreibweise (Komma)."""
    return (f'{value:.{digits}f}' if digits is not None else f'{value:g}').replace('.', ',')


def _accepted(conn, proposal_id):
    if isinstance(proposal_id, bool) or not str(proposal_id).isdigit():
        raise ValueError('Ungültiger Auftrag.')
    row = conn.execute('SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.id=?', (int(proposal_id),)).fetchone()
    if not row:
        raise ValueError('Angebot existiert nicht.')
    if row['status'] != 'angenommen':
        raise ValueError('Zeiten lassen sich nur für angenommene Angebote erfassen.')
    return row


def add_entry(conn, data, today=None):
    if not isinstance(data, dict) or set(data) - {'proposal_id', 'work_date', 'hours', 'note'}:
        raise ValueError('Erwartet: proposal_id, hours, optional work_date, note.')
    row = _accepted(conn, data.get('proposal_id'))
    if conn.execute('SELECT 1 FROM project_closings WHERE proposal_id=?', (row['id'],)).fetchone():
        raise ValueError('Der Auftrag ist abgeschlossen. Zum Nachtragen zuerst wieder öffnen.')
    hours = data.get('hours')
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not 0.1 <= hours <= 200:  # auch Sammeleinträge („diese Woche 18 Stunden“) sind erlaubt
        raise ValueError('Stunden: Zahl zwischen 0,1 und 200 je Eintrag.')
    today = today or dt.date.today()
    try:
        day = dt.date.fromisoformat(data.get('work_date') or today.isoformat())
    except (TypeError, ValueError) as exc:
        raise ValueError('Datum als JJJJ-MM-TT.') from exc
    if day > today:
        raise ValueError('Das Datum liegt in der Zukunft.')
    note = data.get('note', '')
    if not isinstance(note, str) or len(note) > 300:
        raise ValueError('Notiz: höchstens 300 Zeichen.')
    cur = conn.execute('INSERT INTO time_entries(proposal_id, work_date, hours, note) VALUES (?,?,?,?)',
                       (row['id'], day.isoformat(), round(float(hours), 2), re.sub(r'[\r\n]+', ' ', note).strip()))
    conn.commit()
    return {'id': cur.lastrowid, 'project': project(conn, row)}


def delete_entry(conn, entry_id):
    row = conn.execute('SELECT proposal_id FROM time_entries WHERE id=?', (entry_id,)).fetchone()
    if not row:
        raise ValueError('Eintrag existiert nicht.')
    if conn.execute('SELECT 1 FROM project_closings WHERE proposal_id=?', (row['proposal_id'],)).fetchone():
        raise ValueError('Der Auftrag ist abgeschlossen. Zum Ändern zuerst wieder öffnen.')
    conn.execute('DELETE FROM time_entries WHERE id=?', (entry_id,))
    conn.commit()
    return {'deleted': True}


def close_project(conn, proposal_id, data, today=None):
    """Auftrag abschließen: ab jetzt zählt er nicht mehr zur Auslastung. Optional die tatsächlichen Fremdkosten."""
    row = _accepted(conn, proposal_id)
    data = data if isinstance(data, dict) else {}
    if set(data) - {'actual_external_eur', 'note'}:
        raise ValueError('Erwartet: optional actual_external_eur, note.')
    ext = data.get('actual_external_eur')
    if ext is not None and (isinstance(ext, bool) or not isinstance(ext, (int, float)) or not 0 <= ext <= 1_000_000):
        raise ValueError('Fremdkosten: Betrag zwischen 0 und 1.000.000 €.')
    note = data.get('note', '')
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError('Notiz: höchstens 500 Zeichen.')
    if not conn.execute('SELECT 1 FROM time_entries WHERE proposal_id=?', (row['id'],)).fetchone():
        raise ValueError('Ohne erfasste Zeiten lässt sich nichts nachkalkulieren. Bitte mindestens einen Eintrag anlegen.')
    conn.execute('''INSERT INTO project_closings(proposal_id, done_at, actual_external_eur, note) VALUES (?,?,?,?)
                    ON CONFLICT(proposal_id) DO UPDATE SET done_at=excluded.done_at, actual_external_eur=excluded.actual_external_eur, note=excluded.note''',
                 (row['id'], (today or dt.date.today()).isoformat(), ext, note.strip()))
    conn.commit()
    return project(conn, row)


def reopen_project(conn, proposal_id):
    row = _accepted(conn, proposal_id)
    conn.execute('DELETE FROM project_closings WHERE proposal_id=?', (row['id'],))
    conn.commit()
    return project(conn, row)


def _min_earning(conn, internal):
    if internal.get('min_hourly_earning'):
        return _num(internal['min_hourly_earning'])
    try:
        from .pricing import pricing_settings
        return _num(pricing_settings(conn).get('min_hourly_earning'))
    except Exception:  # noqa: BLE001 – ältere Angebote ohne Katalog-Einstellungen
        return 0.0


def project(conn, row):
    """Soll/Ist eines angenommenen Angebots. row: proposals-Zeile mit company."""
    internal, customer = _json(row['internal_json']), _json(row['customer_json'])
    est = _num(internal.get('estimated_hours') or internal.get('hours'))
    net = _num(customer.get('net_eur'))
    est_ext = _num(internal.get('external_cost_eur'))
    entries = [dict(r) for r in conn.execute('SELECT id, work_date, hours, note FROM time_entries WHERE proposal_id=? ORDER BY work_date DESC, id DESC', (row['id'],))]
    actual = round(sum(e['hours'] for e in entries), 2)
    closing = conn.execute('SELECT * FROM project_closings WHERE proposal_id=?', (row['id'],)).fetchone()
    done = bool(closing)
    ext = closing['actual_external_eur'] if closing and closing['actual_external_eur'] is not None else est_ext
    minimum = _min_earning(conn, internal)
    planned_hourly = round((net - est_ext) / est, 2) if est else None
    actual_hourly = round((net - ext) / actual, 2) if actual else None
    variance = round(100 * (actual - est) / est) if est and actual else None
    remaining = 0.0 if done else (max(0.0, round(est - actual, 2)) if est else 0.0)
    if not entries:
        status, verdict = 'nicht_begonnen', 'Noch keine Zeiten erfasst.'
    elif done:
        status = 'abgeschlossen'
        if actual_hourly is None or not minimum:
            verdict = f'Abgeschlossen mit {_de(actual)} Stunden.'
        elif actual_hourly >= minimum:
            verdict = f'Hat sich gelohnt: {_de(actual_hourly, 2)} € je Stunde bei mindestens {_de(minimum)} €.'
        else:
            verdict = f'Unter deinem Mindestverdienst: {_de(actual_hourly, 2)} € je Stunde statt mindestens {_de(minimum)} €.'
    elif est and actual > est:
        status, verdict = 'ueberzogen', f'{_de(actual - est)} Stunden über der Kalkulation – Umfang mit dem Kunden prüfen oder künftig mehr Zeit ansetzen.'
    else:
        status = 'laeuft'
        verdict = f'{_de(remaining)} von {_de(est)} kalkulierten Stunden übrig.' if est else f'{_de(actual)} Stunden erfasst; das Angebot hat keine kalkulierten Stunden.'
    return {'proposal_id': row['id'], 'lead_id': row['lead_id'], 'company': row['company'], 'number': row['number'] or f"Angebot {row['id']}",
            'label': customer.get('project_label') or customer.get('title') or '', 'net_eur': net, 'estimated_hours': est, 'actual_hours': actual,
            'remaining_hours': remaining, 'variance_pct': variance, 'planned_hourly': planned_hourly, 'actual_hourly': actual_hourly,
            'min_hourly': minimum, 'estimated_external_eur': est_ext, 'actual_external_eur': ext, 'status': status, 'verdict': verdict,
            'done': done, 'done_at': closing['done_at'] if closing else '', 'closing_note': closing['note'] if closing else '',
            'below_minimum': bool(done and actual_hourly is not None and minimum and actual_hourly < minimum), 'entries': entries[:50]}


def remaining_by_proposal(conn):
    """Für die Auslastung: je angenommenem Angebot die verbleibenden Stunden – nur wo Zeiten erfasst sind oder abgeschlossen wurde."""
    out = {}
    for r in conn.execute("""SELECT p.id, p.internal_json, (SELECT SUM(hours) FROM time_entries t WHERE t.proposal_id=p.id) AS actual,
                                    (SELECT 1 FROM project_closings c WHERE c.proposal_id=p.id) AS done
                             FROM proposals p WHERE p.status='angenommen'"""):
        if r['done']:
            out[r['id']] = 0.0
        elif r['actual'] is not None:
            internal = _json(r['internal_json'])
            est = _num(internal.get('estimated_hours') or internal.get('hours'))
            out[r['id']] = max(0.0, est - r['actual'])
    return out


def overview(conn):
    rows = conn.execute("""SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.status='angenommen'
                           ORDER BY p.updated_at DESC, p.id DESC LIMIT 200""").fetchall()
    projects = [project(conn, r) for r in rows]
    projects.sort(key=lambda p: (p['done'], p['status'] != 'ueberzogen', -p['proposal_id']))
    done = [p for p in projects if p['done'] and p['estimated_hours'] and p['actual_hours']]
    lesson = None
    if len(done) >= 3:
        avg = round(sum(p['variance_pct'] for p in done) / len(done))
        below = sum(1 for p in done if p['below_minimum'])
        lesson = {'projects': len(done), 'avg_variance_pct': avg, 'below_minimum': below,
                  'text': (f'Über {len(done)} abgeschlossene Aufträge brauchst du im Mittel {abs(avg)} % '
                           f"{'mehr' if avg > 0 else 'weniger'} Zeit als kalkuliert." if avg else f'Über {len(done)} abgeschlossene Aufträge triffst du deine Kalkulation im Mittel genau.')
                          + (f' {below} davon lagen unter deinem Mindestverdienst.' if below else '')}
    return {'projects': projects, 'open': sum(1 for p in projects if not p['done']), 'lesson': lesson,
            'notice': 'Zeiten erfasst du selbst. Erst ab drei abgeschlossenen Aufträgen zeigt SignalDesk, wie gut deine Kalkulation im Mittel trifft. '
                      'Der Kunde sieht weder Stunden noch diese Auswertung.'}


def route(h, conn, method, path):
    if path == '/api/postcalc' and method == 'GET':
        h._send(200, overview(conn))
        return True
    if path == '/api/postcalc/entries' and method == 'POST':
        h._send(201, add_entry(conn, h._body()))
        return True
    m = re.fullmatch(r'/api/postcalc/entries/(\d+)', path)
    if m and method == 'DELETE':
        h._send(200, delete_entry(conn, int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/postcalc/(\d+)/(close|reopen)', path)
    if m and method == 'POST':
        pid = int(m.group(1))
        if m.group(2) == 'close':
            body = h._body() if h.headers.get('Content-Length', '0') not in ('0', '') else {}
            h._send(200, close_project(conn, pid, body))
        else:
            h._send(200, reopen_project(conn, pid))
        return True
    return False
