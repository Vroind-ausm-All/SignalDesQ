"""Zusatzaufträge und Leistungsänderungen (2.0.0-dev25, Produktreview M18).

Ein Zusatzauftrag ist ein eigenes Angebot mit ausdrücklichem Bezug auf einen angenommenen Auftrag:
- Nummer: Stammnummer des Auftrags mit Zähler (AN-2026-0003-Z1), gleiche Firma und Chance.
- Der ursprüngliche Auftrag bleibt unverändert: Kundendokument, Preis, Abnahme und Nachkalkulation des Auftrags werden
  nicht angefasst. Das Kundendokument des Zusatzauftrags nennt den Bezug, den Anlass und den bisher beauftragten Umfang.
- Freigabe, Versand, Zusage, Übergabe und Abnahme laufen wie bei jedem Angebot. Bis zur Zusage gehört er nicht zum Auftrag.
- „Auftragsumfang“ zeigt den ursprünglichen Auftrag und alle Zusatzaufträge mit Stand und Summe – so bleibt erkennbar,
  was ursprünglich vereinbart war und was dazukam.
"""
from __future__ import annotations

import json
import re


def init_addenda(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(proposals)')}
    for name, decl in (('addendum_of', 'INTEGER'), ('addendum_no', 'INTEGER NOT NULL DEFAULT 0')):
        if name not in cols:
            conn.execute(f'ALTER TABLE proposals ADD COLUMN {name} {decl}')


def _row(conn, pid):
    row = conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
    if not row:
        raise LookupError('Angebot nicht gefunden.')
    return row


def _number(row):
    return row['number'] or f"#{row['id']}"


def base_order(conn, pid):
    """Der angenommene Auftrag, auf den sich ein Zusatzauftrag bezieht (bei einem Zusatzauftrag: dessen Auftrag)."""
    row = _row(conn, pid)
    if row['addendum_of']:
        row = _row(conn, row['addendum_of'])
    if row['status'] != 'angenommen' or row['superseded_by']:
        raise ValueError('Ein Zusatzauftrag bezieht sich immer auf einen angenommenen Auftrag. Vor der Zusage wird das Angebot '
                         'überarbeitet („Überarbeiten“), nicht ergänzt.')
    return row


def _scope_lines(cust):
    pos = [p for p in cust.get('positions') or [] if not p.get('optional')]
    return [f"{p['title']} – {p['scope']}" for p in pos] or list(cust.get('included') or [])


def prepare(conn, pid):
    base = base_order(conn, pid)
    cust = json.loads(base['customer_json'])
    return {'addendum_of': base['id'], 'number': _number(base), 'lead_id': base['lead_id'], 'opportunity_id': base['opportunity_id'],
            'next_no': _next_no(conn, base['id']), 'project_label': cust.get('project_label', ''), 'base_scope': _scope_lines(cust),
            'tax_mode': cust.get('tax_mode', 'offen')}


def _next_no(conn, base_id):
    return (conn.execute('SELECT MAX(addendum_no) FROM proposals WHERE addendum_of=?', (base_id,)).fetchone()[0] or 0) + 1


def apply(conn, base_id, reason, proposal, lead_id):
    """Beim Speichern eines Zusatzauftrags: Bezug, Anlass und Nummer setzen. Gibt (Nummer, Zähler, Auftrag) zurück."""
    base = base_order(conn, base_id)
    if base['lead_id'] != lead_id:
        raise ValueError('Der Auftrag gehört zu einer anderen Firma.')
    reason = re.sub(r'\s+', ' ', str(reason or '')).strip()[:300]
    if len(reason) < 5:
        raise ValueError('Bitte kurz den Anlass des Zusatzauftrags angeben (z. B. „Kundenwunsch: zusätzliche Sprachversion“).')
    no = _next_no(conn, base['id'])
    cust = json.loads(base['customer_json'])
    info = {'no': no, 'base': _number(base), 'base_date': cust.get('offer_date', ''), 'base_label': cust.get('project_label', ''),
            'reason': reason, 'base_scope': _scope_lines(cust)}
    proposal['customer']['addendum'] = info
    proposal['internal']['addendum'] = {'of': base['id'], 'no': no, 'reason': reason}
    root = re.sub(r'-R\d+$', '', _number(base))
    return f'{root}-Z{no}', no, base


def scope(conn, pid):
    """Auftragsumfang: ursprünglicher Auftrag und Zusatzaufträge (aktuelle Fassungen) mit Stand und Summen."""
    row = _row(conn, pid)
    base = _row(conn, row['addendum_of']) if row['addendum_of'] else row
    bc = json.loads(base['customer_json'])
    adds = []
    for r in conn.execute('SELECT * FROM proposals WHERE addendum_of=? AND superseded_by IS NULL ORDER BY addendum_no, id', (base['id'],)):
        c = json.loads(r['customer_json'])
        adds.append({'id': r['id'], 'number': _number(r), 'no': r['addendum_no'], 'status': r['status'], 'net_eur': c.get('net_eur') or 0,
                     'project_label': c.get('project_label', ''), 'reason': (c.get('addendum') or {}).get('reason', '')})
    accepted = [a for a in adds if a['status'] == 'angenommen']
    base_net = bc.get('net_eur') or 0
    return {'proposal_id': pid, 'base': {'id': base['id'], 'number': _number(base), 'status': base['status'], 'net_eur': base_net,
                                         'project_label': bc.get('project_label', ''), 'scope': _scope_lines(bc)},
            'addenda': adds, 'accepted_net_eur': round(sum(a['net_eur'] for a in accepted), 2),
            'open_net_eur': round(sum(a['net_eur'] for a in adds if a['status'] in ('entwurf', 'gesendet_manuell')), 2),
            'total_net_eur': round(base_net + sum(a['net_eur'] for a in accepted), 2) if base['status'] == 'angenommen' else None,
            'can_add': base['status'] == 'angenommen' and not base['superseded_by']}


def route_addenda(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/(zusatzauftrag|umfang)', route)
    if not m or method != 'GET':
        return False
    pid = int(m.group(1))
    h._send(200, prepare(conn, pid) if m.group(2) == 'zusatzauftrag' else scope(conn, pid))
    return True
