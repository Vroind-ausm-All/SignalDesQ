"""Nachfassen mit Anlass, Frist und Ergebnis (2.0.0-dev23, Produktreview M16).

- Beim Dokumentieren des Versands wählst du die Frist selbst (Vorgabe: 7 Tage nach dem Versanddatum, nicht nach heute)
  und kannst einen Anlass angeben. Die Nachfassaufgabe ist mit Angebot und Chance verknüpft.
- Ein Nachfassen endet immer mit einem Ergebnis. Bleibt die Entscheidung offen, braucht es eine neue Frist – oder du
  entscheidest bewusst „nicht weiter nachfassen“. So hängt kein versendetes Angebot ohne nächsten Schritt.
- SignalDesk ruft nicht an und schreibt nicht: Es hält fest, was du getan hast und wann der nächste Schritt fällig ist.
"""
from __future__ import annotations

import datetime as dt
import re

OUTCOMES = {
    'entscheidung_offen': 'Erreicht – Entscheidung noch offen',
    'rueckfragen': 'Rückfragen oder Änderungswünsche',
    'nicht_erreicht': 'Nicht erreicht',
    'zusage_angekuendigt': 'Zusage angekündigt',
    'absage': 'Absage angekündigt',
    'beendet': 'Nicht weiter nachfassen',
}
LABELS = {**OUTCOMES, 'ersetzt': 'Angebot durch neue Fassung ersetzt', 'entschieden': 'Entscheidung dokumentiert'}
NEEDS_NEXT = {'entscheidung_offen', 'rueckfragen', 'nicht_erreicht'}
DEFAULT_DAYS = 7
MAX_DAYS = 120


def init_followups(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
    for name, decl in (('proposal_id', 'INTEGER'), ('opportunity_id', 'INTEGER'), ('reason', "TEXT NOT NULL DEFAULT ''"),
                       ('outcome', "TEXT NOT NULL DEFAULT ''"), ('outcome_note', "TEXT NOT NULL DEFAULT ''")):
        if name not in cols:
            conn.execute(f'ALTER TABLE tasks ADD COLUMN {name} {decl}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_proposal ON tasks(proposal_id)')


def _clean(v, limit, what):
    if v is None:
        return ''
    if not isinstance(v, str) or len(v.strip()) > limit:
        raise ValueError(f'{what}: höchstens {limit} Zeichen.')
    return re.sub(r'\s+', ' ', v).strip()


def due_date(value, base=None):
    """Frist fürs Nachfassen: leer → 7 Tage nach `base` (Versanddatum); sonst ein Datum ab heute bis höchstens 120 Tage."""
    today = dt.date.today()
    if value in (None, ''):
        return max((base or today) + dt.timedelta(days=DEFAULT_DAYS), today)
    try:
        d = dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Nachfassen am: Datum als JJJJ-MM-TT angeben.') from exc
    if d < today:
        raise ValueError('Nachfassen am: Die Frist darf nicht in der Vergangenheit liegen.')
    if d > today + dt.timedelta(days=MAX_DAYS):
        raise ValueError(f'Nachfassen am: höchstens {MAX_DAYS} Tage im Voraus – längere Pausen bitte als Wiedervorlage der Chance.')
    return d


def _title(number, pid, reason):
    return f'Angebot {number} nachfassen (#{pid}) – zulässigen Weg prüfen: {reason}'[:250]


def create(conn, prow, number, due, reason):
    reason = reason or 'Entscheidung erfragen'
    return conn.execute('''INSERT INTO tasks(lead_id, title, due_date, proposal_id, opportunity_id, reason, action_type)
                           VALUES (?,?,?,?,?,?,'followup')''',
                        (prow['lead_id'], _title(number, prow['id'], reason), due.isoformat(), prow['id'], prow['opportunity_id'], reason)).lastrowid


def for_proposal(conn, pid):
    rows = conn.execute('''SELECT id, title, due_date, done, done_at, reason, outcome, outcome_note FROM tasks
                           WHERE proposal_id=? ORDER BY id''', (pid,)).fetchall()
    today = dt.date.today().isoformat()
    items = [{'id': r['id'], 'title': r['title'], 'due_date': r['due_date'], 'done': bool(r['done']), 'done_at': r['done_at'],
              'reason': r['reason'], 'outcome': r['outcome'], 'outcome_label': LABELS.get(r['outcome'], r['outcome']),
              'outcome_note': r['outcome_note'], 'overdue': not r['done'] and bool(r['due_date']) and r['due_date'] < today} for r in rows]
    return {'proposal_id': pid, 'items': items, 'open': [i for i in items if not i['done']], 'outcomes': OUTCOMES,
            'default_next': (dt.date.today() + dt.timedelta(days=DEFAULT_DAYS)).isoformat()}


def record(conn, task_id, data):
    """Ergebnis eines Nachfassens festhalten; bei offener Entscheidung gleich die nächste Frist setzen."""
    if not isinstance(data, dict) or set(data) - {'outcome', 'note', 'next_date', 'next_reason'} or data.get('outcome') not in OUTCOMES:
        raise ValueError('Ergebnis: ' + ', '.join(OUTCOMES))
    t = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not t or not t['proposal_id']:
        raise LookupError('Nachfassaufgabe zu einem Angebot nicht gefunden.')
    if t['done']:
        raise ValueError('Für dieses Nachfassen ist bereits ein Ergebnis festgehalten.')
    p = conn.execute('SELECT * FROM proposals WHERE id=?', (t['proposal_id'],)).fetchone()
    outcome = data['outcome']
    note = _clean(data.get('note'), 500, 'Notiz')
    next_reason = _clean(data.get('next_reason'), 160, 'Anlass')
    nxt = None
    if data.get('next_date'):
        if outcome not in NEEDS_NEXT:
            raise ValueError('Eine neue Frist passt nur, wenn die Entscheidung noch offen ist.')
        if not p or p['superseded_by'] or p['status'] != 'gesendet_manuell':
            raise ValueError('Neues Nachfassen nur für ein versendetes, aktuelles Angebot ohne Entscheidung.')
        nxt = due_date(data['next_date'])
    elif outcome in NEEDS_NEXT and p and p['status'] == 'gesendet_manuell' and not p['superseded_by']:
        raise ValueError('Die Entscheidung ist noch offen: Bitte die nächste Frist setzen – oder „Nicht weiter nachfassen“ wählen.')
    if outcome == 'rueckfragen' and not note:
        raise ValueError('Bitte kurz notieren, welche Rückfragen oder Änderungswünsche es gibt.')
    conn.execute("UPDATE tasks SET done=1, done_at=datetime('now'), outcome=?, outcome_note=? WHERE id=?", (outcome, note, task_id))
    number = (p['number'] if p and p['number'] else f"#{t['proposal_id']}")
    detail = f"Angebot {number} nachgefasst: {OUTCOMES[outcome]}" + (f" – {note}" if note else '')
    new_id = None
    if nxt:
        new_id = create(conn, p, number, nxt, next_reason or {'rueckfragen': 'Rückfragen klären', 'nicht_erreicht': 'Erneut versuchen'}.get(outcome, 'Entscheidung erfragen'))
        detail += f". Nächstes Nachfassen am {nxt.strftime('%d.%m.%Y')}."
        from .workday import _advance, _lead
        step = conn.execute('SELECT title FROM tasks WHERE id=?', (new_id,)).fetchone()['title']
        _advance(conn, _lead(conn, t['lead_id']), None, step, (nxt - dt.date.today()).days)
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)', (t['lead_id'], 'angebot', detail))
    conn.commit()
    hint = {
        'rueckfragen': 'Änderungswünsche gehören in eine überarbeitete Fassung („Überarbeiten“) – die versendete bleibt unverändert.',
        'zusage_angekuendigt': 'Eine Ankündigung ist noch keine Zusage: Die Zusage bitte erst dokumentieren, wenn sie zu diesem Stand vorliegt.',
        'absage': 'Bitte die Absage am Angebot dokumentieren, damit Chance und Summen stimmen.',
        'beendet': 'Kein weiteres Nachfassen geplant. Das Angebot bleibt offen, bis du Zusage oder Absage dokumentierst.',
    }.get(outcome, '')
    return {'saved': True, 'next_task_id': new_id, 'notice': hint, **for_proposal(conn, t['proposal_id'])}


def close_for(conn, pid, outcome='beendet', note=''):
    """Offene Nachfassaufgaben eines Angebots mit Ergebnis beenden (z. B. bei Ersetzung durch eine Revision)."""
    return conn.execute("UPDATE tasks SET done=1, done_at=datetime('now'), outcome=?, outcome_note=? WHERE proposal_id=? AND done=0",
                        (outcome, note[:500], pid)).rowcount


def route_followups(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/nachfassen', route)
    if m and method == 'GET':
        h._send(200, for_proposal(conn, int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/tasks/(\d+)/ergebnis', route)
    if m and method == 'POST':
        h._send(200, record(conn, int(m.group(1)), h._body()))
        return True
    return False
