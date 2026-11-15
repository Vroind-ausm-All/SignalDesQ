"""Bestandskunden und Betreuungsleistungen (2.0.0-dev26, Produktreview M19).

Getrennt wird, was im Alltag verschwimmt:
- **Betreuung** = die monatlichen Positionen eines angenommenen Angebots (Wartung, Hosting-Betreuung, Retainer). Sie hat
  einen Beginn, optional ein Ende, und wird Monat für Monat abgerechnet – je Monat genau eine Rechnung mit Leistungszeitraum.
- **Projekte** = einmalige Leistungen eines angenommenen Angebots, mit Übergabe und Abnahme (M17) und Zusatzaufträgen (M18).
- **Neue Projekte** = offene Chancen derselben Firma. Sie entstehen als eigene Chance und vermischen sich nicht mit der Betreuung.

SignalDesk erstellt keine Rechnung von selbst; es zeigt, welcher Monat noch nicht abgerechnet ist.
"""
from __future__ import annotations

import datetime as dt
import json
import re


def init_care(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS care_contracts (
        proposal_id INTEGER PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
        start_date TEXT NOT NULL, end_date TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
    ''')


def _month(d):
    return d.isoformat()[:7]


def _month_start(m):
    return dt.date.fromisoformat(m + '-01')


def _month_end(m):
    s = _month_start(m)
    nxt = (s.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return nxt - dt.timedelta(days=1)


def _months(a, b):
    """Monate von a bis b (JJJJ-MM), beide eingeschlossen."""
    out, y, m = [], int(a[:4]), int(a[5:7])
    while f'{y:04d}-{m:02d}' <= b:
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _de_month(m):
    return f'{m[5:7]}/{m[:4]}'


def monthly_positions(cust):
    return [p for p in cust.get('positions') or [] if p.get('billing') == 'monatlich' and not p.get('optional')] or (
        [{'title': cust.get('project_label') or 'Monatsleistung', 'scope': 'laut Angebot', 'price_eur': cust.get('net_eur') or 0}]
        if cust.get('billing') == 'monatlich' and not cust.get('positions') else [])


def _care_rows(conn, lead_id=None):
    sql = "SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.status='angenommen' AND p.superseded_by IS NULL"
    args = ()
    if lead_id is not None:
        sql += ' AND p.lead_id=?'
        args = (lead_id,)
    for r in conn.execute(sql + ' ORDER BY p.id', args):
        cust = json.loads(r['customer_json'])
        if monthly_positions(cust):
            yield r, cust


def _ensure(conn, row):
    c = conn.execute('SELECT * FROM care_contracts WHERE proposal_id=?', (row['id'],)).fetchone()
    if c:
        return c
    start = (row['decided_at'] or row['updated_at'] or dt.date.today().isoformat())[:10]
    conn.execute('INSERT OR IGNORE INTO care_contracts(proposal_id, start_date) VALUES (?,?)', (row['id'], start))
    return conn.execute('SELECT * FROM care_contracts WHERE proposal_id=?', (row['id'],)).fetchone()


def billed_months(conn, pid):
    out = set()
    for r in conn.execute("""SELECT service_from FROM invoices WHERE proposal_id=? AND kind<>'storno' AND status<>'storniert'
                             AND service_from<>''""", (pid,)):
        out.add(r['service_from'][:7])
    return out


def contract(conn, row, cust, today=None):
    today = today or dt.date.today()
    c = _ensure(conn, row)
    pos = monthly_positions(cust)
    monthly = round(sum(p['price_eur'] for p in pos), 2)
    first = c['start_date'][:7]
    ended = bool(c['end_date']) and c['end_date'] < today.isoformat()
    last = min(_month(today), c['end_date'][:7]) if c['end_date'] else _month(today)
    billed = billed_months(conn, row['id'])
    due = [m for m in _months(first, last) if m not in billed] if first <= last else []
    status = 'beendet' if ended else ('gekuendigt' if c['end_date'] else 'laufend')
    return {'proposal_id': row['id'], 'lead_id': row['lead_id'], 'company': row['company'], 'number': row['number'] or f"#{row['id']}",
            'project_label': cust.get('project_label', ''), 'positions': [f"{p['title']} – {p['scope']}" for p in pos],
            'monthly_net_eur': monthly, 'start_date': c['start_date'], 'end_date': c['end_date'], 'note': c['note'], 'status': status,
            'status_label': {'laufend': 'läuft', 'gekuendigt': f"gekündigt zum {dt.date.fromisoformat(c['end_date']).strftime('%d.%m.%Y')}" if c['end_date'] else '',
                             'beendet': 'beendet'}[status],
            'billed_months': sorted(billed), 'due_months': due, 'due_labels': [_de_month(m) for m in due]}


def assert_month_billable(conn, pid, month):
    """Für Monatsrechnungen: Monat liegt in der Laufzeit und ist noch nicht abgerechnet."""
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise ValueError('Monat als JJJJ-MM angeben.')
    row = conn.execute('SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.id=?', (pid,)).fetchone()
    c = _ensure(conn, row)
    if month < c['start_date'][:7]:
        raise ValueError(f"Die Betreuung beginnt erst {_de_month(c['start_date'][:7])}.")
    if c['end_date'] and month > c['end_date'][:7]:
        raise ValueError(f"Die Betreuung endet {_de_month(c['end_date'][:7])}.")
    if month > _month(dt.date.today()):
        raise ValueError('Monate in der Zukunft werden noch nicht abgerechnet.')
    if month in billed_months(conn, pid):
        raise ValueError(f'Für {_de_month(month)} gibt es bereits eine Monatsrechnung zu diesem Angebot.')
    return _month_start(month).isoformat(), _month_end(month).isoformat()


def default_month(conn, pid):
    row = conn.execute('SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id WHERE p.id=?', (pid,)).fetchone()
    k = contract(conn, row, json.loads(row['customer_json']))
    return k['due_months'][0] if k['due_months'] else None


def update(conn, pid, data):
    if not isinstance(data, dict) or set(data) - {'start_date', 'end_date', 'note'}:
        raise ValueError('Erwartet: start_date, end_date, note.')
    row = next((r for r, _ in _care_rows(conn) if r['id'] == pid), None)
    if not row:
        raise LookupError('Keine laufende Betreuung zu diesem Angebot (angenommen, mit monatlichen Positionen).')
    c = _ensure(conn, row)
    start, end = c['start_date'], c['end_date']
    for key in ('start_date', 'end_date'):
        if key in data:
            v = data[key] or ''
            if v:
                try:
                    dt.date.fromisoformat(v)
                except (TypeError, ValueError) as exc:
                    raise ValueError('Datum als JJJJ-MM-TT angeben.') from exc
            if key == 'start_date':
                if not v:
                    raise ValueError('Beginn: bitte angeben.')
                start = v
            else:
                end = v
    if end and end < start:
        raise ValueError('Das Ende liegt vor dem Beginn.')
    billed = billed_months(conn, pid)
    if billed and (start[:7] > min(billed) or (end and end[:7] < max(billed))):
        raise ValueError('Bereits abgerechnete Monate müssen in der Laufzeit bleiben – bei Bedarf die Rechnung stornieren.')
    note = re.sub(r'\s+', ' ', str(data.get('note', c['note']) or '')).strip()[:300]
    conn.execute("UPDATE care_contracts SET start_date=?, end_date=?, note=?, updated_at=datetime('now') WHERE proposal_id=?", (start, end, note, pid))
    if end != c['end_date']:
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (row['lead_id'], 'projekt', f"Betreuung {row['number'] or '#' + str(pid)}: " +
                      (f"endet am {dt.date.fromisoformat(end).strftime('%d.%m.%Y')}" if end else 'Ende aufgehoben, läuft weiter') + (f' – {note}' if note else '') + '.'))
    conn.commit()
    return contract(conn, row, json.loads(row['customer_json']))


def overview(conn, today=None):
    """Bestandskunden: Firmen mit mindestens einem angenommenen Auftrag – Betreuung, Projekte und neue Chancen getrennt."""
    from .handover import summary
    firms = {}
    for r in conn.execute("""SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id
                             WHERE p.status='angenommen' AND p.superseded_by IS NULL ORDER BY l.company, p.id"""):
        cust = json.loads(r['customer_json'])
        f = firms.setdefault(r['lead_id'], {'lead_id': r['lead_id'], 'company': r['company'], 'care': [], 'projects': [], 'chances': []})
        if monthly_positions(cust):
            f['care'].append(contract(conn, r, cust, today))
        once = [p for p in cust.get('positions') or [] if p.get('billing') == 'einmalig' and not p.get('optional')]
        if once or (not cust.get('positions') and cust.get('billing') != 'monatlich'):
            f['projects'].append({'proposal_id': r['id'], 'number': r['number'] or f"#{r['id']}", 'project_label': cust.get('project_label', ''),
                                  'net_eur': cust.get('once_net_eur') or cust.get('net_eur') or 0, 'addendum_no': r['addendum_no'] or 0,
                                  'handover': summary(conn, r['id'])})
    from .chances import OPEN
    for lid, f in firms.items():
        f['chances'] = [{'id': c['id'], 'title': c['title'], 'stage': c['stage']} for c in conn.execute(
            f"SELECT id, title, stage FROM opportunities WHERE lead_id=? AND stage IN ({','.join('?' * len(OPEN))}) ORDER BY id", (lid, *OPEN))]
    conn.commit()
    items = sorted(firms.values(), key=lambda f: f['company'].lower())
    care = [c for f in items for c in f['care']]
    return {'firms': items, 'care_count': len([c for c in care if c['status'] != 'beendet']),
            'monthly_net_eur': round(sum(c['monthly_net_eur'] for c in care if c['status'] != 'beendet'), 2),
            'due_count': sum(len(c['due_months']) for c in care)}


def due_items(conn, today=None):
    """Für „Heute“: nicht abgerechnete Monate laufender oder gekündigter Betreuungen."""
    out = []
    for r, cust in _care_rows(conn):
        k = contract(conn, r, cust, today)
        if k['due_months']:
            out.append(k)
    conn.commit()
    return out


def route_care(h, conn, method, route):
    if route == '/api/bestand' and method == 'GET':
        h._send(200, overview(conn))
        return True
    m = re.fullmatch(r'/api/bestand/betreuung/(\d+)', route)
    if m and method == 'PATCH':
        h._send(200, update(conn, int(m.group(1)), h._body()))
        return True
    return False
