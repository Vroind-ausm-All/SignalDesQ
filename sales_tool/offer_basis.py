"""Befund mit Angebot verbinden (2.0.0-dev33, Produktreview M32).

Für jede Position eines Angebots zeigt SignalDesk, worauf sie beruht:
- **bestätigter Bedarf**: die Leistung steht im bestätigten Bedarf der Chance (bzw. der Firma),
- **geprüfter Befund**: ein bestätigter Website-Befund oder eine freigegebene Recherche-Beobachtung, deren Paketvorschlag
  diese Leistung enthält,
- **begleitend**: Anreise, Tagespauschale, Aufwand – brauchen keinen eigenen Beleg,
- **ohne Grundlage**: nichts davon – vor dem Versand begründen oder streichen.
Ungeprüfte Hypothesen, die auf eine Position zeigen, werden ausdrücklich als „offen“ angezeigt und nie als Grundlage gezählt.

Nur intern: Die Grundlage erscheint nie im Kundendokument. Sie blockiert den Versand nicht, sondern erscheint als Hinweis
bei der Versandfreigabe – ob ein Angebot ohne Beleg rausgeht, entscheidest du.
"""
from __future__ import annotations

import json
import re

BEGLEITEND = {'anreise', 'tagessatz', 'aufwand'}
LABELS = {'bedarf': 'bestätigter Bedarf', 'befund': 'geprüfter Befund', 'begleitend': 'begleitend', 'ohne': 'ohne Grundlage'}


def _services_of_package(pkg):
    from .catalog import VORLAGEN
    return {p['service'] for p in (VORLAGEN.get(pkg) or {}).get('positions', [])}


def _findings(conn, lead_id):
    """(geprüft, offen) – je Eintrag Leistungen, Bezeichnung, Quelle."""
    checked, open_ = [], []
    for r in conn.execute("""SELECT id, label, evidence, offer, review_status FROM website_findings
                             WHERE lead_id=? AND offer IS NOT NULL AND offer<>'' AND result='auffaellig' AND review_status<>'verworfen'""", (lead_id,)):
        item = {'id': f"w{r['id']}", 'label': r['label'], 'detail': r['evidence'][:200], 'services': _services_of_package(r['offer']), 'source': 'Website-Bewertung'}
        (checked if r['review_status'] == 'bestaetigt' else open_).append(item)
    for r in conn.execute("""SELECT id, observation, hypothesis, offer, review_status FROM findings
                             WHERE lead_id=? AND offer<>'' AND review_status<>'verworfen'""", (lead_id,)):
        item = {'id': f"r{r['id']}", 'label': r['observation'][:140], 'detail': r['hypothesis'][:200], 'services': _services_of_package(r['offer']),
                'source': 'Website-Inhalte'}
        (checked if r['review_status'] == 'freigegeben' else open_).append(item)
    return checked, open_


def basis(conn, lead_id, chance, positions):
    from .workday import need_status
    needs = {n.get('service') for n in need_status(conn, lead_id, chance)['needs']}
    if chance:
        needs |= {n.get('service') for n in need_status(conn, lead_id)['needs']}  # Bedarf der Firma gilt mit
    checked, open_ = _findings(conn, lead_id)
    out = []
    for n, p in enumerate(positions, 1):
        svc = p.get('service')
        ev = [f for f in checked if svc in f['services']]
        hyp = [f for f in open_ if svc in f['services']]
        if svc in BEGLEITEND:
            kind = 'begleitend'
        elif svc in needs:
            kind = 'bedarf'
        elif ev:
            kind = 'befund'
        else:
            kind = 'ohne'
        out.append({'n': n, 'service': svc, 'title': p.get('title', svc), 'optional': bool(p.get('optional')), 'basis': kind, 'label': LABELS[kind],
                    'evidence': [{'id': f['id'], 'label': f['label'], 'source': f['source']} for f in ev],
                    'hypotheses': [{'id': f['id'], 'label': f['label'], 'detail': f['detail'], 'source': f['source']} for f in hyp]})
    return out


def for_proposal(conn, pid):
    row = conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
    if not row:
        raise LookupError('Angebot nicht gefunden.')
    cust = json.loads(row['customer_json'])
    items = basis(conn, row['lead_id'], row['opportunity_id'], cust.get('positions') or [])
    return {'proposal_id': pid, 'positions': items, 'without': [i for i in items if i['basis'] == 'ohne' and not i['optional']],
            'open_hypotheses': sum(len(i['hypotheses']) for i in items), 'labels': LABELS,
            'notice': 'Nur intern. Ungeprüfte Hypothesen zählen nie als Grundlage.'}


def hints(conn, row):
    """Hinweise für die Versandfreigabe."""
    try:
        b = for_proposal(conn, row['id'])
    except LookupError:
        return []
    out = [f"Pos. {i['n']} {i['title']}: weder bestätigter Bedarf noch geprüfter Befund – vor dem Versand begründen oder streichen."
           for i in b['without']]
    for i in b['positions']:
        if i['hypotheses'] and i['basis'] in ('ohne', 'befund'):
            out.append(f"Pos. {i['n']} {i['title']}: {len(i['hypotheses'])} ungeprüfte Hypothese(n) – erst prüfen, nicht als Tatsache verwenden.")
    return out


def route_offer_basis(h, conn, method, route):
    m = re.fullmatch(r'/api/workspace/proposals/(\d+)/grundlage', route)
    if not m or method != 'GET':
        return False
    h._send(200, for_proposal(conn, int(m.group(1))))
    return True
