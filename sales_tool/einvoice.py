"""E-Rechnung: XRechnung-Export (UBL 2.1) und Einlesen eingehender XRechnung/ZUGFeRD-XML.

Hintergrund (Stand 2026): Seit 01.01.2025 müssen inländische Unternehmen E-Rechnungen
empfangen und verarbeiten können. Die Ausstellungspflicht für B2B-Rechnungen gilt ab
2027 (Vorjahresumsatz > 800.000 €) bzw. ab 2028 für alle; Kleinunternehmer sind davon
ausgenommen. Die erzeugte Datei sollte vor dem ersten produktiven Einsatz mit dem
KoSIT-Validator geprüft werden (https://github.com/itplr-kosit/validator).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from .accounting import UNITS, audit, eur_dot, get_settings, invoice_detail

NS = {
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}
XRECHNUNG_CUSTOMIZATION = 'urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0'
PEPPOL_PROFILE = 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'
TYPE_CODES = {'rechnung': '380', 'schluss': '380', 'abschlag': '326', 'storno': '384'}
MAX_XML_BYTES = 3_000_000

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def _el(parent, tag, text=None, **attrs):
    prefix, name = tag.split(':')
    node = ET.SubElement(parent, f'{{{NS[prefix]}}}{name}', attrs)
    if text is not None:
        node.text = str(text)
    return node


def _amount(parent, tag, cents_value):
    return _el(parent, tag, eur_dot(cents_value), currencyID='EUR')


def _category(inv, rate):
    if inv['tax_mode'] == 'kleinunternehmer':
        return 'E', 0, 'Kleinunternehmer gemäß § 19 UStG'
    if inv['tax_mode'] == 'reverse_charge':
        return 'AE', 0, 'Reverse charge – Steuerschuldnerschaft des Leistungsempfängers'
    if rate == 0:
        return 'Z', 0, None
    return 'S', rate, None


def _tax_category(parent, tag, inv, rate, with_reason=True):
    code, percent, reason = _category(inv, rate)
    cat = _el(parent, tag)
    _el(cat, 'cbc:ID', code)
    _el(cat, 'cbc:Percent', f'{percent}')
    if with_reason and reason:
        _el(cat, 'cbc:TaxExemptionReason', reason)
    scheme = _el(cat, 'cac:TaxScheme')
    _el(scheme, 'cbc:ID', 'VAT')
    return cat


def _address(parent, street, city, zip_code, country):
    addr = _el(parent, 'cac:PostalAddress')
    if street:
        _el(addr, 'cbc:StreetName', street)
    _el(addr, 'cbc:CityName', city)
    _el(addr, 'cbc:PostalZone', zip_code)
    country_el = _el(addr, 'cac:Country')
    _el(country_el, 'cbc:IdentificationCode', country or 'DE')


def xrechnung_warnings(inv):
    seller = inv['seller']
    warnings = []
    if not seller.get('email'):
        warnings.append('Elektronische Adresse des Verkäufers (E-Mail) fehlt (BT-34).')
    if not seller.get('phone'):
        warnings.append('Telefonnummer des Verkäufers fehlt (BR-DE-5/BT-42).')
    if not inv['buyer_email']:
        warnings.append('Elektronische Adresse des Käufers (E-Mail) fehlt (BT-49).')
    if not inv['buyer_reference']:
        warnings.append('Käuferreferenz/Leitweg-ID fehlt (BT-10) – Rechnungsnummer wird ersatzweise eingetragen.')
    if not seller.get('iban'):
        warnings.append('IBAN fehlt (BR-DE-23-a).')
    return warnings


def xrechnung_xml(conn, invoice_id):
    inv = invoice_detail(conn, invoice_id)
    if inv['status'] == 'entwurf':
        raise ValueError('E-Rechnung erst nach Festschreibung erzeugen.')
    seller = inv['seller']
    warnings = xrechnung_warnings(inv)
    root = ET.Element(f"{{{NS['ubl']}}}Invoice")
    _el(root, 'cbc:CustomizationID', XRECHNUNG_CUSTOMIZATION)
    _el(root, 'cbc:ProfileID', PEPPOL_PROFILE)
    _el(root, 'cbc:ID', inv['number'])
    _el(root, 'cbc:IssueDate', inv['issue_date'])
    if inv['due_date'] and inv['kind'] != 'storno':
        _el(root, 'cbc:DueDate', inv['due_date'])
    _el(root, 'cbc:InvoiceTypeCode', TYPE_CODES[inv['kind']])
    for note in [inv['intro_text'], *inv['notes'], seller.get('footer_note', '')]:
        if note:
            _el(root, 'cbc:Note', note)
    _el(root, 'cbc:DocumentCurrencyCode', 'EUR')
    _el(root, 'cbc:BuyerReference', inv['buyer_reference'] or inv['number'])
    if inv['service_to']:
        period = _el(root, 'cac:InvoicePeriod')
        _el(period, 'cbc:StartDate', inv['service_from'])
        _el(period, 'cbc:EndDate', inv['service_to'])
    if inv.get('corrects'):
        ref = _el(_el(root, 'cac:BillingReference'), 'cac:InvoiceDocumentReference')
        _el(ref, 'cbc:ID', inv['corrects']['number'])
        _el(ref, 'cbc:IssueDate', inv['corrects']['issue_date'])

    party = _el(_el(root, 'cac:AccountingSupplierParty'), 'cac:Party')
    _el(party, 'cbc:EndpointID', seller.get('email') or 'unbekannt@invalid', schemeID='EM')
    _address(party, seller.get('street'), seller.get('city'), seller.get('zip'), seller.get('country'))
    if seller.get('vat_id'):
        pts = _el(party, 'cac:PartyTaxScheme')
        _el(pts, 'cbc:CompanyID', seller['vat_id'])
        _el(_el(pts, 'cac:TaxScheme'), 'cbc:ID', 'VAT')
    if seller.get('tax_number'):
        pts = _el(party, 'cac:PartyTaxScheme')
        _el(pts, 'cbc:CompanyID', seller['tax_number'])
        _el(_el(pts, 'cac:TaxScheme'), 'cbc:ID', 'FC')
    _el(_el(party, 'cac:PartyLegalEntity'), 'cbc:RegistrationName', seller.get('company_name'))
    contact = _el(party, 'cac:Contact')
    _el(contact, 'cbc:Name', seller.get('owner_name') or seller.get('company_name'))
    _el(contact, 'cbc:Telephone', seller.get('phone') or '-')
    _el(contact, 'cbc:ElectronicMail', seller.get('email') or 'unbekannt@invalid')

    buyer = _el(_el(root, 'cac:AccountingCustomerParty'), 'cac:Party')
    _el(buyer, 'cbc:EndpointID', inv['buyer_email'] or 'unbekannt@invalid', schemeID='EM')
    _address(buyer, inv['buyer_street'], inv['buyer_city'], inv['buyer_zip'], inv['buyer_country'])
    if inv['buyer_vat_id']:
        pts = _el(buyer, 'cac:PartyTaxScheme')
        _el(pts, 'cbc:CompanyID', inv['buyer_vat_id'])
        _el(_el(pts, 'cac:TaxScheme'), 'cbc:ID', 'VAT')
    _el(_el(buyer, 'cac:PartyLegalEntity'), 'cbc:RegistrationName', inv['buyer_name'])
    if inv['buyer_contact']:
        _el(_el(buyer, 'cac:Contact'), 'cbc:Name', inv['buyer_contact'])

    if not inv['service_to'] and inv['service_from']:
        _el(_el(root, 'cac:Delivery'), 'cbc:ActualDeliveryDate', inv['service_from'])

    means = _el(root, 'cac:PaymentMeans')
    _el(means, 'cbc:PaymentMeansCode', '58')
    _el(means, 'cbc:PaymentID', inv['number'])
    account = _el(means, 'cac:PayeeFinancialAccount')
    _el(account, 'cbc:ID', seller.get('iban') or '')
    _el(account, 'cbc:Name', seller.get('company_name'))
    if seller.get('bic'):
        _el(_el(account, 'cac:FinancialInstitutionBranch'), 'cbc:ID', seller['bic'])
    if inv['kind'] != 'storno':
        _el(_el(root, 'cac:PaymentTerms'), 'cbc:Note',
            f"Zahlbar ohne Abzug bis {dt.date.fromisoformat(inv['due_date']).strftime('%d.%m.%Y')}." if inv['due_date'] else 'Zahlbar sofort ohne Abzug.')

    totals = inv['totals']
    tax_total = _el(root, 'cac:TaxTotal')
    _amount(tax_total, 'cbc:TaxAmount', totals['vat_cents'])
    for group in totals['breakdown']:
        sub = _el(tax_total, 'cac:TaxSubtotal')
        _amount(sub, 'cbc:TaxableAmount', group['net_cents'])
        _amount(sub, 'cbc:TaxAmount', group['vat_cents'])
        _tax_category(sub, 'cac:TaxCategory', inv, group['rate'])

    money = _el(root, 'cac:LegalMonetaryTotal')
    _amount(money, 'cbc:LineExtensionAmount', totals['net_cents'])
    _amount(money, 'cbc:TaxExclusiveAmount', totals['net_cents'])
    _amount(money, 'cbc:TaxInclusiveAmount', totals['gross_cents'])
    _amount(money, 'cbc:PayableAmount', totals['gross_cents'])

    for line in inv['lines']:
        qty = Decimal(line['quantity'])
        price = line['unit_price_cents']
        if price < 0:  # BR-27: Nettopreis darf nicht negativ sein → Menge negativ
            qty, price = -qty, -price
        node = _el(root, 'cac:InvoiceLine')
        _el(node, 'cbc:ID', line['position'])
        _el(node, 'cbc:InvoicedQuantity', format(qty.normalize(), 'f'), unitCode=UNITS[line['unit']][1])
        _amount(node, 'cbc:LineExtensionAmount', line['net_cents'])
        item = _el(node, 'cac:Item')
        _el(item, 'cbc:Name', line['description'][:200])
        _tax_category(item, 'cac:ClassifiedTaxCategory', inv, line['vat_rate'] if inv['tax_mode'] == 'regel' else 0, with_reason=False)
        _amount(_el(node, 'cac:Price'), 'cbc:PriceAmount', price)

    ET.indent(root, space='  ')
    data = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8')
    return data, warnings


# ---------------------------------------------------------------- Eingehende E-Rechnungen

def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _child(node, *names):
    """Pfad über lokale Elementnamen (namespace-unabhängig)."""
    for name in names:
        if node is None:
            return None
        node = next((c for c in node if _local(c.tag) == name), None)
    return node


def _children(node, name):
    return [c for c in node if _local(c.tag) == name] if node is not None else []


def _txt(node, *names):
    found = _child(node, *names) if names else node
    return (found.text or '').strip() if found is not None and found.text else ''


def _dec(value):
    try:
        return Decimal(value) if value else None
    except InvalidOperation:
        return None


def _cii_date(value):
    value = (value or '').strip()
    if re.fullmatch(r'\d{8}', value):
        return f'{value[:4]}-{value[4:6]}-{value[6:]}'
    return value[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}.*', value) else ''


def parse_einvoice(xml_bytes):
    if not isinstance(xml_bytes, bytes) or not xml_bytes.strip():
        raise ValueError('Leere Datei.')
    if len(xml_bytes) > MAX_XML_BYTES:
        raise ValueError('Datei zu groß (max. 3 MB).')
    head = xml_bytes[:4096].upper()
    if b'<!DOCTYPE' in head or b'<!ENTITY' in xml_bytes.upper():
        raise ValueError('XML mit DOCTYPE/ENTITY wird aus Sicherheitsgründen abgelehnt.')
    if xml_bytes[:5] == b'%PDF-':
        raise ValueError('PDF erkannt. ZUGFeRD/Factur-X: bitte die eingebettete XML-Datei (factur-x.xml / zugferd-invoice.xml) importieren.')
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f'Keine gültige XML-Datei: {exc}') from exc
    kind = _local(root.tag)
    if kind in ('Invoice', 'CreditNote'):
        result = _parse_ubl(root, kind)
    elif kind == 'CrossIndustryInvoice':
        result = _parse_cii(root)
    else:
        raise ValueError(f'Unbekanntes Format ({kind}). Unterstützt: XRechnung/UBL, XRechnung/CII, ZUGFeRD/Factur-X-XML.')
    result['warnings'] = _plausibility(result)
    return result


def _parse_ubl(root, kind):
    supplier = _child(root, 'AccountingSupplierParty', 'Party')
    name = _txt(supplier, 'PartyLegalEntity', 'RegistrationName') or _txt(supplier, 'PartyName', 'Name')
    vat_id = ''
    for pts in _children(supplier, 'PartyTaxScheme'):
        if _txt(pts, 'TaxScheme', 'ID') == 'VAT':
            vat_id = _txt(pts, 'CompanyID')
    money = _child(root, 'LegalMonetaryTotal')
    tax_total = _child(root, 'TaxTotal')
    rates, categories = set(), set()
    for sub in _children(tax_total, 'TaxSubtotal'):
        rates.add(_dec(_txt(sub, 'TaxCategory', 'Percent')))
        categories.add(_txt(sub, 'TaxCategory', 'ID'))
    lines = [_txt(l, 'Item', 'Name') for l in _children(root, 'InvoiceLine') + _children(root, 'CreditNoteLine')]
    due = _txt(root, 'DueDate') or _txt(root, 'PaymentMeans', 'PaymentDueDate')
    return {
        'format': 'UBL ' + ('Gutschrift' if kind == 'CreditNote' else 'Rechnung'),
        'customization': _txt(root, 'CustomizationID'),
        'credit_note': kind == 'CreditNote' or _txt(root, 'InvoiceTypeCode') == '381',
        'number': _txt(root, 'ID'), 'issue_date': _txt(root, 'IssueDate'), 'due_date': due,
        'currency': _txt(root, 'DocumentCurrencyCode') or 'EUR',
        'supplier': name, 'supplier_vat_id': vat_id,
        'net': _dec(_txt(money, 'TaxExclusiveAmount')), 'vat': _dec(_txt(tax_total, 'TaxAmount')),
        'gross': _dec(_txt(money, 'TaxInclusiveAmount')), 'payable': _dec(_txt(money, 'PayableAmount')),
        'rates': sorted(r for r in rates if r is not None), 'categories': sorted(c for c in categories if c),
        'lines': [l for l in lines if l][:30],
        'iban': _txt(root, 'PaymentMeans', 'PayeeFinancialAccount', 'ID'),
    }


def _parse_cii(root):
    doc = _child(root, 'ExchangedDocument')
    trade = _child(root, 'SupplyChainTradeTransaction')
    agreement = _child(trade, 'ApplicableHeaderTradeAgreement')
    seller = _child(agreement, 'SellerTradeParty')
    vat_id = ''
    for reg in _children(seller, 'SpecifiedTaxRegistration'):
        node = _child(reg, 'ID')
        if node is not None and node.get('schemeID') == 'VA':
            vat_id = (node.text or '').strip()
    settlement = _child(trade, 'ApplicableHeaderTradeSettlement')
    summary = _child(settlement, 'SpecifiedTradeSettlementHeaderMonetarySummation')
    rates, categories = set(), set()
    for tax in _children(settlement, 'ApplicableTradeTax'):
        rates.add(_dec(_txt(tax, 'RateApplicablePercent')))
        categories.add(_txt(tax, 'CategoryCode'))
    lines = [_txt(l, 'SpecifiedTradeProduct', 'Name') for l in _children(trade, 'IncludedSupplyChainTradeLineItem')]
    vat_total = None
    for node in _children(summary, 'TaxTotalAmount'):
        if node.get('currencyID') in (None, 'EUR'):
            vat_total = _dec((node.text or '').strip())
    type_code = _txt(doc, 'TypeCode')
    return {
        'format': 'CII (XRechnung/ZUGFeRD)', 'customization': _txt(root, 'ExchangedDocumentContext', 'GuidelineSpecifiedDocumentContextParameter', 'ID'),
        'credit_note': type_code == '381',
        'number': _txt(doc, 'ID'), 'issue_date': _cii_date(_txt(doc, 'IssueDateTime', 'DateTimeString')),
        'due_date': _cii_date(_txt(settlement, 'SpecifiedTradePaymentTerms', 'DueDateDateTime', 'DateTimeString')),
        'currency': _txt(settlement, 'InvoiceCurrencyCode') or 'EUR',
        'supplier': _txt(seller, 'Name'), 'supplier_vat_id': vat_id,
        'net': _dec(_txt(summary, 'TaxBasisTotalAmount')), 'vat': vat_total,
        'gross': _dec(_txt(summary, 'GrandTotalAmount')), 'payable': _dec(_txt(summary, 'DuePayableAmount')),
        'rates': sorted(r for r in rates if r is not None), 'categories': sorted(c for c in categories if c),
        'lines': [l for l in lines if l][:30],
        'iban': _txt(settlement, 'SpecifiedTradeSettlementPaymentMeans', 'PayeePartyCreditorFinancialAccount', 'IBANID'),
    }


def _plausibility(r):
    warnings = []
    if not r['number']:
        warnings.append('Rechnungsnummer fehlt.')
    if not r['supplier']:
        warnings.append('Lieferant/Verkäufer fehlt.')
    if r['currency'] != 'EUR':
        warnings.append(f"Währung {r['currency']} – Umrechnung manuell prüfen.")
    if r['net'] is not None and r['vat'] is not None and r['gross'] is not None and r['net'] + r['vat'] != r['gross']:
        warnings.append('Netto + USt ergibt nicht den Bruttobetrag.')
    if len(r['rates']) > 1:
        warnings.append('Mehrere Steuersätze – Ausgabe ggf. aufteilen.')
    if 'AE' in r['categories']:
        warnings.append('Reverse Charge (AE): Du schuldest die Umsatzsteuer (§ 13b UStG).')
    if r['credit_note']:
        warnings.append('Gutschrift/Rechnungskorrektur – nicht als Ausgabe erfassen, sondern mit der Ursprungsrechnung verrechnen.')
    return warnings


def import_document(conn, data):
    if not isinstance(data, dict) or set(data) - {'filename', 'xml'} or not isinstance(data.get('xml'), str):
        raise ValueError('Erwartet: {filename, xml}.')
    filename = str(data.get('filename') or 'e-rechnung.xml')[:200]
    raw = data['xml'].encode('utf-8')
    parsed = parse_einvoice(raw)
    digest = hashlib.sha256(raw).hexdigest()
    existing = conn.execute('SELECT id FROM einvoice_documents WHERE sha256=?', (digest,)).fetchone()
    if existing:
        doc_id, duplicate = existing['id'], True
    else:
        cur = conn.execute('INSERT INTO einvoice_documents(filename,sha256,format,number,supplier,xml) VALUES (?,?,?,?,?,?)',
                           (filename, digest, parsed['format'], parsed['number'], parsed['supplier'], raw))
        doc_id, duplicate = cur.lastrowid, False
        audit(conn, 'einvoice', doc_id, 'archiviert', f"{parsed['supplier']} {parsed['number']} sha256={digest[:16]}…")
        conn.commit()
    linked = conn.execute("SELECT id FROM expenses WHERE document_id=? AND status='aktiv'", (doc_id,)).fetchone()
    single_rate = parsed['rates'][0] if len(parsed['rates']) == 1 else None
    suggestion = {
        'supplier': parsed['supplier'], 'expense_date': parsed['issue_date'], 'receipt_ref': f"E-Rechnung {parsed['number']}",
        'description': '; '.join(parsed['lines'][:3])[:500],
        'gross_eur': str(parsed['gross']) if parsed['gross'] is not None else '',
        'vat_eur': str(parsed['vat']) if parsed['vat'] is not None else '',
        'net_eur': str(parsed['net']) if parsed['net'] is not None else '',
        'vat_rate': int(single_rate) if single_rate is not None and single_rate in (0, 7, 19) else 19,
        'reverse_charge': 'AE' in parsed['categories'],
    }
    out = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in parsed.items()}
    out['rates'] = [str(r) for r in parsed['rates']]
    return {'document_id': doc_id, 'duplicate': duplicate, 'already_booked_expense_id': linked['id'] if linked else None,
            'parsed': out, 'expense_suggestion': suggestion,
            'notice': 'Original-XML wurde unverändert archiviert (GoBD). Bitte Werte prüfen und dann als Ausgabe übernehmen.'}


def init_einvoice(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS einvoice_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, format TEXT NOT NULL DEFAULT '',
        number TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL DEFAULT '', xml BLOB NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TRIGGER IF NOT EXISTS trg_einvoice_doc_immutable
      BEFORE UPDATE ON einvoice_documents BEGIN SELECT RAISE(ABORT, 'Archivierte E-Rechnung ist unveränderbar.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_einvoice_doc_no_delete
      BEFORE DELETE ON einvoice_documents BEGIN SELECT RAISE(ABORT, 'Archivierte E-Rechnung darf nicht gelöscht werden.'); END;
    ''')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(expenses)')}
    if 'document_id' not in cols:
        conn.execute('ALTER TABLE expenses ADD COLUMN document_id INTEGER REFERENCES einvoice_documents(id)')


def document_row(conn, doc_id):
    row = conn.execute('SELECT * FROM einvoice_documents WHERE id=?', (doc_id,)).fetchone()
    if not row:
        raise LookupError('Dokument nicht gefunden.')
    return row


def document_rows(conn):
    return [dict(r) for r in conn.execute('''SELECT d.id, d.filename, d.format, d.number, d.supplier, d.created_at, d.sha256,
                                              (SELECT e.id FROM expenses e WHERE e.document_id=d.id AND e.status='aktiv') AS expense_id
                                              FROM einvoice_documents d ORDER BY d.id DESC LIMIT 200''')]


def settings_ready_for_xrechnung(conn):
    s = get_settings(conn)
    return [m for m, ok in (('E-Mail', s['email']), ('Telefon', s['phone']), ('IBAN', s['iban'])) if not ok]
