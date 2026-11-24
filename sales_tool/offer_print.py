"""Gestaltetes Angebot zum Drucken bzw. „Als PDF speichern“ (SDQ-009). Keine externen Abhängigkeiten.

Inhalt kommt ausschließlich aus dem Kundendokument (`proposal_detail(..., customer_only=True)`) – dieselbe Quelle wie der
Markdown-Export. Stunden, Sätze und Kalkulation stehen dort nicht und können hier nicht erscheinen. Absender aus den
Stammdaten (Abrechnen → Einstellungen), Anschrift der Kundin aus den Firmendaten der Firma (keine Person).
Ohne Freigabe oder nach einer Änderung seit der Freigabe trägt das Blatt sichtbar „ENTWURF“.
"""
from __future__ import annotations

import datetime as dt
from html import escape

from .accounting import get_settings
from .offer_flow import release_info
from .sales_workspace import proposal_detail


def _e(value):
    return escape(str(value if value is not None else ''))


def _d(iso):
    try:
        return dt.date.fromisoformat(str(iso)[:10]).strftime('%d.%m.%Y') if iso else ''
    except ValueError:
        return str(iso)


def _eur(v):
    return f"{float(v or 0):,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')


def _ul(items):
    items = [x for x in (items or []) if str(x).strip()]
    return '<ul>' + ''.join(f'<li>{_e(x)}</li>' for x in items) + '</ul>' if items else ''


def _section(title, body):
    return f'<section class="block"><h2>{_e(title)}</h2>{body}</section>' if body else ''


def _buyer(conn, lead_id, fallback):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(leads)')}
    want = [c for c in ('legal_name', 'street', 'zip', 'city') if c in cols]
    row = conn.execute(f"SELECT company{''.join(', ' + c for c in want)} FROM leads WHERE id=?", (lead_id,)).fetchone() if lead_id else None
    if not row:
        return {'name': fallback, 'street': '', 'zip': '', 'city': ''}
    d = dict(zip(['company', *want], row))
    return {'name': d.get('legal_name') or fallback or d['company'], 'street': d.get('street') or '', 'zip': d.get('zip') or '', 'city': d.get('city') or ''}


def offer_html(conn, proposal_id):
    detail = proposal_detail(conn, proposal_id, customer_only=True)  # ValueError, wenn es das Angebot nicht gibt
    cu = detail['customer']
    rel = release_info(conn.execute('SELECT * FROM proposals WHERE id=?', (proposal_id,)).fetchone())
    final = bool(rel and not rel.get('changed'))
    seller = get_settings(conn)
    buyer = _buyer(conn, detail.get('lead_id'), cu.get('customer_company', ''))
    title = 'Zusatzauftrag' if cu.get('addendum') else 'Angebot'
    monthly = lambda p: ' / Monat' if p.get('billing') == 'monatlich' else ''

    head_rows = [('Angebotsnummer', cu.get('offer_number') or 'noch ohne Nummer'), ('Datum', _d(cu.get('offer_date'))),
                 ('Gültig bis', _d(cu.get('valid_until'))), ('Projekt', cu.get('project_label'))]
    if final:
        head_rows.append(('Stand', f"{rel['stand']} · freigegeben am {_d(rel['released_at'])}"))
    meta = ''.join(f'<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>' for k, v in head_rows if v)

    notes = []
    rev, add = cu.get('revision'), cu.get('addendum')
    if rev:
        notes.append(f"<p class='note'>Überarbeitete Fassung {_e(rev.get('no'))} – ersetzt Angebot {_e(rev.get('replaces'))}"
                     f"{' vom ' + _e(_d(rev.get('replaces_date'))) if rev.get('replaces_date') else ''}.</p>")
    if add:
        notes.append(f"<p class='note'>Zusatzauftrag {_e(add.get('no'))} zu Angebot {_e(add.get('base'))}. Der beauftragte Umfang bleibt "
                     f"unverändert; die folgenden Leistungen werden gesondert beauftragt, abgenommen und abgerechnet. "
                     f"Anlass: {_e(add.get('reason'))}</p>")

    rows, details = [], []
    for n, pos in enumerate(cu.get('positions') or [], 1):
        opt = pos.get('optional')
        scope = _e(pos.get('scope')) + (f" · {_e(pos['note'])}" if pos.get('note') else '')
        price = ('optional: ' if opt else '') + _eur(pos.get('price_eur')) + monthly(pos)
        rows.append(f"<tr class='{'opt' if opt else ''}'><td>{n}</td><td><b>{_e(pos.get('title'))}</b>{' <span class=tag>optional</span>' if opt else ''}"
                    f"<div class='muted'>{scope}</div></td><td class='num'>{price}</td></tr>")
        inc = pos.get('included') or []
        details.append(f"<div class='pos'><h3>Pos. {n} · {_e(pos.get('title'))}</h3><p>{_e(pos.get('description'))}</p>{_ul(inc)}</div>")
    sums = []
    if cu.get('once_net_eur'):
        sums.append(('Summe einmalig netto', _eur(cu['once_net_eur'])))
    if cu.get('monthly_net_eur'):
        sums.append(('Summe monatlich netto', _eur(cu['monthly_net_eur']) + ' / Monat'))
    if cu.get('tax_mode') == 'regel_19':
        if cu.get('once_net_eur'):
            sums.append(('zzgl. 19 % USt. einmalig', _eur(cu['once_net_eur'] * 0.19)))
        if cu.get('monthly_net_eur'):
            sums.append(('zzgl. 19 % USt. monatlich', _eur(cu['monthly_net_eur'] * 0.19) + ' / Monat'))
    total = []
    if cu.get('tax_mode') == 'regel_19':
        if cu.get('once_net_eur'):
            total.append(('Gesamtbetrag einmalig', _eur(cu['once_net_eur'] * 1.19)))
        if cu.get('monthly_net_eur'):
            total.append(('Gesamtbetrag monatlich', _eur(cu['monthly_net_eur'] * 1.19) + ' / Monat'))
    elif cu.get('tax_mode') != 'offen':
        if cu.get('once_net_eur'):
            total.append(('Gesamtbetrag einmalig', _eur(cu['once_net_eur'])))
        if cu.get('monthly_net_eur'):
            total.append(('Gesamtbetrag monatlich', _eur(cu['monthly_net_eur']) + ' / Monat'))
    sum_html = ''.join(f"<tr><td>{_e(k)}</td><td class='num'>{_e(v)}</td></tr>" for k, v in sums)
    sum_html += ''.join(f"<tr class='total'><td>{_e(k)}</td><td class='num'>{_e(v)}</td></tr>" for k, v in total)
    items = (f"<table class='items'><thead><tr><th>Pos.</th><th>Leistung</th><th class='num'>Festpreis netto</th></tr></thead>"
             f"<tbody>{''.join(rows)}</tbody></table><table class='sum'>{sum_html}</table>"
             f"<p class='muted'>{_e(cu.get('tax_note'))}</p>") if rows else _ul(cu.get('included'))

    rounds = (f"Korrekturschleifen: {cu['revision_rounds']}" if cu.get('revision_rounds') is not None
              else (f"Korrekturschleifen: {cu['revision_note']}" if cu.get('revision_note') else ''))
    frame = _ul([f"Geplanter Zeitraum: {cu.get('weeks')}" if cu.get('weeks') else '', rounds,
                 'Abnahme anhand der genannten Liefergegenstände nach gemeinsamer Prüfung.'])
    body = ''.join([
        _section('Ziel und Ergebnis', f"<p>{_e(cu.get('goal'))}</p>" if cu.get('goal') else ''),
        _section(f"Änderungen gegenüber Angebot {rev.get('replaces')}" if rev else '', _ul(rev.get('changes')) if rev else ''),
        _section('Leistungen und Festpreise', items),
        _section('Was enthalten ist', ''.join(details)),
        _section('Liefergegenstände', _ul(cu.get('deliverables'))),
        _section('Nicht enthalten', _ul(cu.get('excluded'))),
        _section('Voraussetzungen', f"<p>{_e(cu.get('assumptions'))}</p>" if cu.get('assumptions') else ''),
        _section('Umfang und Abnahme', frame),
        _section('Abnahmekriterien', _ul(cu.get('acceptance_criteria'))),
        _section('Mögliche Drittanbieter- und Folgekosten (nicht im Festpreis)', _ul(cu.get('third_party_costs'))),
        _section('Zahlung und Änderungen', ''.join(f'<p>{_e(x)}</p>' for x in (cu.get('payment_plan'), cu.get('change_requests')) if x)),
        _section('Hinweise', f"<p>{_e(cu.get('guarantee'))}</p>" if cu.get('guarantee') else ''),
    ])
    validity = (f"Dieses Angebot ist bis {_e(_d(cu.get('valid_until')) or 'zum genannten Datum')} gültig. Stand {_e(rel['stand'])}."
                if final else 'Dieses Dokument ist ein Angebotsentwurf und nicht zum Versand freigegeben.')
    sign = ("<section class='sign'><div><span></span>Ort, Datum</div><div><span></span>Auftrag erteilt – Unterschrift und Firmenstempel</div></section>"
            if final else '')
    mark = '' if final else ('<div class="draft-mark">ENTWURF – nicht versenden</div>' if not rel else
                             '<div class="draft-mark">ENTWURF – seit Freigabe geändert</div>')
    seller_tax = ' · '.join(x for x in (f"Steuernummer: {_e(seller.get('tax_number'))}" if seller.get('tax_number') else '',
                                         f"USt-IdNr.: {_e(seller.get('vat_id'))}" if seller.get('vat_id') else '') if x)
    sender_line = ' · '.join(_e(x) for x in (seller.get('company_name'), seller.get('street'),
                                              f"{seller.get('zip') or ''} {seller.get('city') or ''}".strip()) if x)
    brand = '<br>'.join(_e(x) for x in (seller.get('owner_name'), seller.get('street'),
                                         f"{seller.get('zip') or ''} {seller.get('city') or ''}".strip(), seller.get('email'),
                                         seller.get('phone'), seller.get('website')) if x)
    postal = ' · '.join(_e(x) for x in (seller.get('street'), f"{seller.get('zip') or ''} {seller.get('city') or ''}".strip()) if x)
    address = '<br>'.join(_e(x) for x in (buyer['street'], f"{buyer['zip']} {buyer['city']}".strip()) if x)
    doc_title = f"{title} {cu.get('offer_number') or ''}".strip()
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(doc_title)} · {_e(buyer['name'])}</title><link rel="stylesheet" href="/invoice.css"><link rel="stylesheet" href="/offer.css"></head>
<body><div class="toolbar no-print"><button type="button" id="printBtn">Drucken / als PDF speichern</button>
<span>Tipp: Im Druckdialog „Als PDF speichern“ wählen. {'Versandfassung mit Stand ' + _e(rel['stand']) + '.' if final else 'Entwurf: erst nach Freigabe versenden.'}</span></div>
<main class="sheet offer" data-offer-final="{'1' if final else '0'}">{mark}
<header class="head"><div class="sender">{sender_line}</div>
<div class="brand"><b>{_e(seller.get('company_name'))}</b>{'<br>' + brand if brand else ''}</div></header>
<section class="address"><b>{_e(buyer['name'])}</b>{'<br>' + address if address else ''}</section>
<h1>{_e(title)}: {_e(cu.get('project_label'))}</h1><table class="meta">{meta}</table>{''.join(notes)}
{body}
<p class="validity">{validity}</p>{sign}
<footer><div>{_e(seller.get('company_name'))}<br>{_e(seller.get('owner_name'))}<br>{postal}</div>
<div>{seller_tax}<br>{' · '.join(_e(x) for x in (seller.get('email'), seller.get('website')) if x)}</div>
<div>{_e(seller.get('bank_name'))}{'<br>IBAN ' + _e(' '.join((seller.get('iban') or '')[i:i + 4] for i in range(0, len(seller.get('iban') or ''), 4))) if seller.get('iban') else ''}</div></footer>
</main><script src="/print.js"></script></body></html>"""


def route_offer_print(h, route, db_path, connect):
    import re
    match = re.fullmatch(r'/angebot/(\d+)', route)
    if not match:
        return False
    with connect(db_path) as conn:
        try:
            html = offer_html(conn, int(match.group(1)))
        except (ValueError, LookupError, TypeError):
            h._error('Angebot nicht gefunden.', 404)
            return True
    h._send_raw(200, html.encode('utf-8'), 'text/html')
    return True
