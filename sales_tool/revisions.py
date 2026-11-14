"""Angebotsrevisionen (2.0.0-dev21, Produktreview M15 Teil 1, Abnahmefall T11).

Eine Revision ist ein neues Angebot, das ausdrücklich ein früheres ersetzt:
- Nummer: Stammnummer mit Revisionszähler (AN-2026-0003-R2), gleiche Firma und Chance wie der Vorgänger.
- Sichtbar: Vorgänger, Änderungsgrund und die wesentlichen Änderungen (Positionen, Preise, Zeitraum, Zahlungsplan) – intern
  und im Kundendokument.
- Der Vorgänger bleibt unverändert gespeichert, gilt aber als „ersetzt“: keine Freigabe, kein Versand, keine Zusage, keine
  Nachfass-Erinnerung mehr.
- Ein angenommenes oder abgelehntes Angebot wird nicht überarbeitet – der angenommene Stand bleibt die Grundlage
  (Änderungen danach sind Zusatzaufträge, M18).
"""
from __future__ import annotations

import json
import re

SIZES = {'Basis': 'S', 'Standard': 'M', 'Umfangreich': 'L'}


def init_revisions(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(proposals)')}
    for name, decl in (('revision_of', 'INTEGER'), ('revision_no', 'INTEGER NOT NULL DEFAULT 1'),
                       ('revision_reason', "TEXT NOT NULL DEFAULT ''"), ('superseded_by', 'INTEGER')):
        if name not in cols:
            conn.execute(f'ALTER TABLE proposals ADD COLUMN {name} {decl}')


def _row(conn, pid):
    row = conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
    if not row:
        raise LookupError('Angebot nicht gefunden.')
    return row


def _number(row):
    return row['number'] or f"#{row['id']}"


def payload_of(row):
    """Bauplan eines Angebots für die Überarbeitung. Neue Angebote speichern ihn; ältere werden aus dem Kundendokument
    rekonstruiert (Leistung, Umfang aus der Bezeichnung, Menge, Titel)."""
    internal = json.loads(row['internal_json'] or '{}')
    cust = json.loads(row['customer_json'])
    if internal.get('payload'):
        p = dict(internal['payload'])
    else:
        positions = []
        for c in cust.get('positions') or []:
            pos = {'service': c['service']}
            label = (c.get('scope') or '').split(':', 1)[0]
            if label in SIZES:
                pos['size'] = SIZES[label]
            elif c.get('unit') == 'Tag':
                pos['days'] = c.get('quantity') or 1
            elif c.get('unit') not in ('pauschal', 'Fahrt'):
                pos['qty'] = c.get('quantity') or 1
            if c.get('title'):
                pos['title'] = c['title']
            positions.append(pos)
        p = {'positions': positions}
        if not positions and cust.get('package'):
            p = {'package': cust['package']}
        for k in ('project_label', 'tax_mode', 'assumptions'):
            if cust.get(k):
                p[k] = cust[k]
        if cust.get('goal'):
            p['customer_goal'] = cust['goal']
    return p


def assert_revisable(conn, pid):
    row = _row(conn, pid)
    if row['status'] in ('angenommen', 'abgelehnt'):
        raise ValueError('Ein angenommenes oder abgelehntes Angebot bleibt, wie es ist. Änderungen nach einer Zusage sind ein '
                         'Zusatzauftrag; nach einer Absage ein neues Angebot.')
    if row['superseded_by']:
        nxt = conn.execute('SELECT number FROM proposals WHERE id=?', (row['superseded_by'],)).fetchone()
        raise ValueError(f"Dieses Angebot ist bereits durch {nxt['number'] if nxt else 'eine Revision'} ersetzt – bitte die neueste Fassung überarbeiten.")
    return row


def prepare(conn, pid):
    """Vorlage für das Angebotsformular: Bauplan des Vorgängers, Firma und Chance."""
    row = assert_revisable(conn, pid)
    return {'revision_of': row['id'], 'number': _number(row), 'lead_id': row['lead_id'], 'opportunity_id': row['opportunity_id'],
            'next_no': (row['revision_no'] or 1) + 1, 'payload': payload_of(row)}


def _money(v):
    return f"{v:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')


def changes(old, new):
    """Wesentliche Änderungen zwischen zwei Kundendokumenten – in Worten, wie sie der Kunde lesen kann."""
    out = []
    key = lambda p: (p.get('service'), p.get('title'))
    before = {key(p): p for p in old.get('positions') or []}
    after = {key(p): p for p in new.get('positions') or []}
    for k, p in after.items():
        if k not in before:
            out.append(f"Neu: {p['title']} – {p['scope']} ({_money(p['price_eur'])})")
        else:
            o = before[k]
            if o.get('scope') != p.get('scope') or o.get('price_eur') != p.get('price_eur'):
                out.append(f"Geändert: {p['title']} – {o.get('scope')} → {p.get('scope')} ({_money(o.get('price_eur', 0))} → {_money(p['price_eur'])})")
    for k, o in before.items():
        if k not in after:
            out.append(f"Entfällt: {o['title']} – {o.get('scope', '')}")
    for field, label in (('once_net_eur', 'Summe einmalig netto'), ('monthly_net_eur', 'Summe monatlich netto')):
        a, b = old.get(field) or 0, new.get(field) or 0
        if a != b:
            out.append(f"{label}: {_money(a)} → {_money(b)}")
    if not new.get('positions') and old.get('net_eur') != new.get('net_eur'):
        out.append(f"Festpreis netto: {_money(old.get('net_eur') or 0)} → {_money(new.get('net_eur') or 0)}")
    for field, label in (('weeks', 'Zeitraum'), ('payment_plan', 'Zahlungsplan'), ('assumptions', 'Voraussetzungen')):
        if (old.get(field) or '') != (new.get(field) or ''):
            out.append(f"{label} geändert" + (f": {old.get(field) or '–'} → {new.get(field) or '–'}" if field != 'assumptions' else ''))
    return out or ['Keine inhaltlichen Änderungen an Positionen, Preisen, Zeitraum oder Zahlungsplan.']


def apply(conn, pred_id, reason, proposal):
    """Beim Speichern einer Revision: Nummer, Bezug und Änderungen setzen. Gibt (Nummer, Revisionsnummer, Chance) zurück."""
    row = assert_revisable(conn, pred_id)
    reason = re.sub(r'\s+', ' ', str(reason or '')).strip()[:300]
    if len(reason) < 5:
        raise ValueError('Bitte kurz den Grund der Überarbeitung angeben (z. B. „Umfang auf Wunsch reduziert“).')
    no = (row['revision_no'] or 1) + 1
    root = re.sub(r'-R\d+$', '', _number(row))
    old = json.loads(row['customer_json'])
    diff = changes(old, proposal['customer'])
    proposal['customer']['revision'] = {'no': no, 'replaces': _number(row), 'replaces_date': old.get('offer_date', ''), 'reason': reason, 'changes': diff}
    proposal['internal']['revision'] = {'of': row['id'], 'no': no, 'reason': reason, 'changes': diff}
    return f'{root}-R{no}', no, row


def link(conn, pred_row, new_id, new_number, reason):
    conn.execute("UPDATE proposals SET superseded_by=?, updated_at=datetime('now') WHERE id=?", (new_id, pred_row['id']))
    closed = conn.execute(r"""UPDATE tasks SET done=1, done_at=datetime('now') WHERE lead_id=? AND done=0
                              AND (title LIKE ? OR title LIKE ?) AND (title LIKE '%nachfass%' OR title LIKE '%Rückfrage%' OR title LIKE '%prüfen und manuell versenden%')""",
                          (pred_row['lead_id'], f"%{_number(pred_row)}%", f"%(#{pred_row['id']})%")).rowcount
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (pred_row['lead_id'], 'notiz', f"Angebot {_number(pred_row)} überarbeitet → {new_number}: {reason}"
                  + (f" ({closed} Nachfassaufgabe(n) zum Vorgänger beendet)" if closed else '')))


def history(conn, pid):
    """Kette aller Fassungen, älteste zuerst."""
    row = _row(conn, pid)
    while row['revision_of']:
        row = _row(conn, row['revision_of'])
    chain = [row]
    while chain[-1]['superseded_by']:
        chain.append(_row(conn, chain[-1]['superseded_by']))
    out = []
    for r in chain:
        c = json.loads(r['customer_json'])
        out.append({'id': r['id'], 'number': _number(r), 'revision_no': r['revision_no'] or 1, 'status': r['status'],
                    'superseded': bool(r['superseded_by']), 'reason': r['revision_reason'], 'net_eur': c.get('net_eur'),
                    'offer_date': c.get('offer_date', ''), 'changes': (c.get('revision') or {}).get('changes', [])})
    return {'proposal_id': pid, 'versions': out}


def route_revisions(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/(revision|fassungen)', route)
    if not m or method != 'GET':
        return False
    pid = int(m.group(1))
    h._send(200, prepare(conn, pid) if m.group(2) == 'revision' else history(conn, pid))
    return True
