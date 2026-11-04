"""Druckansicht einer Rechnung (Browser → „Als PDF speichern“). Keine externen Abhängigkeiten."""
from __future__ import annotations

import datetime as dt
from html import escape

from .accounting import UNITS, eur, get_settings, invoice_detail

KIND_TITLES = {'rechnung': 'Rechnung', 'abschlag': 'Abschlagsrechnung', 'schluss': 'Schlussrechnung', 'storno': 'Stornorechnung'}


def _d(iso):
    return dt.date.fromisoformat(iso).strftime('%d.%m.%Y') if iso else ''


def _e(value):
    return escape(str(value or ''))


def _lines(text):
    return '<br>'.join(_e(x) for x in str(text or '').splitlines())


def invoice_html(conn, invoice_id):
    inv = invoice_detail(conn, invoice_id)
    draft = inv['status'] == 'entwurf'
    seller = get_settings(conn) if draft else inv['seller']
    title = KIND_TITLES.get(inv['kind'], 'Rechnung')
    number = inv['number'] or 'ENTWURF – noch keine Rechnungsnummer'
    service = (f"{_d(inv['service_from'])} – {_d(inv['service_to'])}" if inv['service_to']
               else _d(inv['service_from']) or 'entspricht Rechnungsdatum')
    rows = []
    for line in inv['lines']:
        unit = UNITS.get(line['unit'], (line['unit'],))[0]
        rows.append(
            f"<tr><td>{line['position']}</td><td>{_lines(line['description'])}</td>"
            f"<td class='num'>{_e(line['quantity'].replace('.', ','))} {_e(unit)}</td>"
            f"<td class='num'>{eur(line['unit_price_cents'])} €</td>"
            + (f"<td class='num'>{line['vat_rate']} %</td>" if inv['tax_mode'] == 'regel' else '')
            + f"<td class='num'>{eur(line['net_cents'])} €</td></tr>")
    tax_rows = ''
    if inv['tax_mode'] == 'regel':
        tax_rows = ''.join(f"<tr><td>zzgl. {g['rate']} % USt. auf {eur(g['net_cents'])} €</td><td class='num'>{eur(g['vat_cents'])} €</td></tr>"
                           for g in inv['totals']['breakdown'])
    seller_tax = ' · '.join(x for x in (
        f"Steuernummer: {_e(seller.get('tax_number'))}" if seller.get('tax_number') else '',
        f"USt-IdNr.: {_e(seller.get('vat_id'))}" if seller.get('vat_id') else '') if x)
    corrects = ''
    if inv.get('corrects'):
        corrects = f"<p><b>Korrigiert Rechnung {_e(inv['corrects']['number'])} vom {_d(inv['corrects']['issue_date'])}</b></p>"
    payment = ''
    if inv['kind'] != 'storno':
        due = _d(inv['due_date']) if inv['due_date'] else f"{inv['payment_days']} Tage nach Rechnungsdatum"
        payment = (f"<p>Bitte überweisen Sie den Rechnungsbetrag bis zum <b>{_e(due)}</b> ohne Abzug unter Angabe der "
                   f"Rechnungsnummer auf das unten genannte Konto.</p>")
    notes = ''.join(f'<p class="note">{_e(n)}</p>' for n in inv['notes'])
    head_rows = [('Rechnungsnummer', number), ('Rechnungsdatum', _d(inv['issue_date']) or 'bei Festschreibung'),
                 ('Leistungsdatum', service)]
    if inv['buyer_reference']:
        head_rows.append(('Ihre Referenz', inv['buyer_reference']))
    if inv['buyer_vat_id']:
        head_rows.append(('USt-IdNr. Kunde', inv['buyer_vat_id']))
    meta = ''.join(f'<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>' for k, v in head_rows)
    status_badge = ''
    if draft:
        status_badge = '<div class="draft-mark">ENTWURF – nicht versenden</div>'
    elif inv['status'] == 'storniert':
        status_badge = '<div class="draft-mark">STORNIERT</div>'
    vat_head = '<th class="num">USt.</th>' if inv['tax_mode'] == 'regel' else ''
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} {_e(inv['number'] or 'Entwurf')}</title><link rel="stylesheet" href="/invoice.css"></head>
<body><div class="toolbar no-print"><button type="button" id="printBtn">Drucken / als PDF speichern</button>
<span>Tipp: Im Druckdialog „Als PDF speichern“ wählen. Die E-Rechnung (XRechnung) lädst du in SignalDesk unter „Rechnungen“ herunter.</span></div>
<main class="sheet">{status_badge}
<header class="head"><div class="sender">{_e(seller.get('company_name'))} · {_e(seller.get('street'))} · {_e(seller.get('zip'))} {_e(seller.get('city'))}</div>
<div class="brand"><b>{_e(seller.get('company_name'))}</b><br>{_e(seller.get('owner_name'))}<br>{_e(seller.get('street'))}<br>{_e(seller.get('zip'))} {_e(seller.get('city'))}<br>{_e(seller.get('email'))}<br>{_e(seller.get('phone'))}</div></header>
<section class="address"><b>{_e(inv['buyer_name'])}</b><br>{_e(inv['buyer_contact'])}{'<br>' if inv['buyer_contact'] else ''}{_e(inv['buyer_street'])}<br>{_e(inv['buyer_zip'])} {_e(inv['buyer_city'])}{'<br>' + _e(inv['buyer_country']) if inv['buyer_country'] != 'DE' else ''}</section>
<h1>{_e(title)}</h1><table class="meta">{meta}</table>{corrects}
{f'<p>{_lines(inv["intro_text"])}</p>' if inv['intro_text'] else ''}
<table class="items"><thead><tr><th>Pos.</th><th>Leistung</th><th class="num">Menge</th><th class="num">Einzelpreis</th>{vat_head}<th class="num">Netto</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<table class="sum"><tr><td>Summe netto</td><td class="num">{eur(inv['totals']['net_cents'])} €</td></tr>{tax_rows}
<tr class="total"><td>{'Gutschriftsbetrag' if inv['kind'] == 'storno' else 'Rechnungsbetrag'}</td><td class="num">{eur(inv['totals']['gross_cents'])} €</td></tr></table>
{notes}{payment}{f'<p>{_lines(inv["closing_text"])}</p>' if inv['closing_text'] else ''}
<footer><div>{_e(seller.get('company_name'))}<br>{_e(seller.get('owner_name'))}<br>{_e(seller.get('street'))}, {_e(seller.get('zip'))} {_e(seller.get('city'))}</div>
<div>{seller_tax}<br>{' · '.join(_e(x) for x in (seller.get('email'), seller.get('website')) if x)}</div>
<div>{_e(seller.get('bank_name'))}<br>IBAN {_e(' '.join((seller.get('iban') or '')[i:i + 4] for i in range(0, len(seller.get('iban') or ''), 4)))}<br>{('BIC ' + _e(seller.get('bic'))) if seller.get('bic') else ''}</div></footer>
{f'<p class="footnote">{_e(seller.get("footer_note"))}</p>' if seller.get('footer_note') else ''}
</main><script src="/print.js"></script></body></html>"""
