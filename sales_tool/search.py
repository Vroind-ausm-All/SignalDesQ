"""Globale Suche (2.0.0-dev34, Produktreview M10).

Ein Suchfeld für Firma (Name, Firmierung, Website), Chance, Angebot (Nummer, Projekt) und Rechnungsnummer. Personen und
Gesprächsnotizen werden bewusst nicht durchsucht (Datensparsamkeit). Nur lesend; je Gruppe höchstens acht Treffer.
"""
from __future__ import annotations

import json
import re

LIMIT = 8


def _like(q):
    return '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def search(conn, q):
    q = re.sub(r'\s+', ' ', str(q or '')).strip()
    if len(q) < 2:
        return {'q': q, 'groups': [], 'total': 0, 'notice': 'Mindestens zwei Zeichen eingeben.'}
    if len(q) > 80:
        raise ValueError('Suchbegriff: höchstens 80 Zeichen.')
    pat = _like(q)
    groups = []
    firms = [{'kind': 'firma', 'id': r['id'], 'lead_id': r['id'], 'title': r['company'],
              'detail': ' · '.join(x for x in (r['legal_name'] if r['legal_name'] and r['legal_name'] != r['company'] else '', r['website'] or '',
                                               'gesperrt' if r['stage'] == 'gesperrt' or r['permission'] == 'nicht_kontaktieren' else '') if x)}
             for r in conn.execute(r"""SELECT id, company, legal_name, website, stage, permission FROM leads
                                      WHERE company LIKE ? ESCAPE '\' OR legal_name LIKE ? ESCAPE '\' OR website LIKE ? ESCAPE '\'
                                      ORDER BY CASE WHEN company LIKE ? ESCAPE '\' THEN 0 ELSE 1 END, company LIMIT ?""",
                                   (pat, pat, pat, _like(q)[1:], LIMIT))]
    if firms:
        groups.append({'key': 'firmen', 'label': 'Firmen', 'items': firms})
    ch = [{'kind': 'chance', 'id': r['id'], 'lead_id': r['lead_id'], 'title': r['title'], 'detail': f"{r['company']} · {r['stage']}"}
          for r in conn.execute(r"""SELECT o.id, o.lead_id, o.title, o.stage, l.company FROM opportunities o JOIN leads l ON l.id=o.lead_id
                                   WHERE o.title LIKE ? ESCAPE '\' ORDER BY o.id DESC LIMIT ?""", (pat, LIMIT))]
    if ch:
        groups.append({'key': 'chancen', 'label': 'Chancen', 'items': ch})
    offers = []
    for r in conn.execute(r"""SELECT p.id, p.lead_id, p.number, p.status, p.superseded_by, p.customer_json, l.company FROM proposals p
                             JOIN leads l ON l.id=p.lead_id
                             WHERE p.number LIKE ? ESCAPE '\' OR json_extract(p.customer_json, '$.project_label') LIKE ? ESCAPE '\'
                             ORDER BY p.id DESC LIMIT ?""", (pat, pat, LIMIT)):
        label = (json.loads(r['customer_json']).get('project_label') or '')
        offers.append({'kind': 'angebot', 'id': r['id'], 'lead_id': r['lead_id'], 'title': f"{r['number'] or '#' + str(r['id'])} {label}".strip(),
                       'detail': f"{r['company']} · {'ersetzt' if r['superseded_by'] else r['status'].replace('_', ' ')}"})
    if offers:
        groups.append({'key': 'angebote', 'label': 'Angebote', 'items': offers})
    inv = [{'kind': 'rechnung', 'id': r['id'], 'lead_id': r['lead_id'], 'title': r['number'] or f"Entwurf #{r['id']}", 'detail': f"{r['buyer_name']} · {r['status']}"}
           for r in conn.execute(r"""SELECT id, lead_id, number, buyer_name, status FROM invoices WHERE number LIKE ? ESCAPE '\'
                                    ORDER BY id DESC LIMIT ?""", (pat, LIMIT))]
    if inv:
        groups.append({'key': 'rechnungen', 'label': 'Rechnungen', 'items': inv})
    total = sum(len(g['items']) for g in groups)
    return {'q': q, 'groups': groups, 'total': total, 'notice': '' if total else 'Nichts gefunden. Gesucht werden Firmen, Chancen, Angebote und Rechnungsnummern.'}


def route_search(h, conn, method, route, query):
    if route != '/api/suche' or method != 'GET':
        return False
    h._send(200, search(conn, (query.get('q') or [''])[0] if isinstance(query, dict) else ''))
    return True
