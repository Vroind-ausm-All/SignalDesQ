"""Prüfung einer E-Rechnung (UBL 2.1) gegen die Geschäftsregeln von EN 16931 und XRechnung 3.0 (SDQ-024).

Geprüft werden die Regeln, die sich ohne Schematron-Prozessor sicher nachrechnen lassen: Pflichtangaben (BR-01 … BR-16),
Rechenregeln der Summen (BR-CO-10, -13, -15, -16), Steuergruppen (BR-S-08/09, BR-E-10, BR-AE-10, BR-Z-10), Codelisten
für Währung, Rechnungsart, Einheit, Zahlungsart, Datumsformat und die deutschen Zusatzregeln (BR-DE-1 bis -23) samt
IBAN-Prüfziffer. Jede Regel hat ihre Kennung aus der Spezifikation.

**Kein Ersatz für den KoSIT-Validator:** Die vollständige Prüfung (XSD-Schema und alle rund 300 Schematron-Regeln) macht
nur der offizielle Validator (https://github.com/itplr-kosit/validator). Diese Prüfung findet die häufigen Fehler vor dem
Versand – ein „bestanden“ hier heißt nicht, dass ein Empfängerportal die Datei annimmt.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

XRECHNUNG_3 = 'urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0'
TYPE_CODES = {'326', '380', '381', '384', '389', '751', '875', '876', '877'}   # Auswahl UNTDID 1001, wie XRechnung zulässt
PAYMENT_CODES = {'1', '10', '20', '30', '31', '42', '48', '49', '57', '58', '59', '97', 'ZZZ'}
CREDIT_TRANSFER = {'30', '58'}
DIRECT_DEBIT = {'59'}
CARD = {'48', '54', '55'}
CATEGORIES = {'S', 'Z', 'E', 'AE', 'K', 'G', 'O', 'L', 'M'}
UNIT_RE = re.compile(r'^[A-Z0-9]{2,3}$')       # UN/ECE Rec. 20/21 (Form, nicht die vollständige Liste)
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PLACEHOLDER_EMAIL = 'unbekannt@invalid'
CENT = Decimal('0.01')


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _kids(node, name):
    return [c for c in list(node) if _local(c.tag) == name] if node is not None else []


def _kid(node, *path):
    for name in path:
        found = _kids(node, name)
        node = found[0] if found else None
        if node is None:
            return None
    return node


def _txt(node, *path):
    n = _kid(node, *path)
    return (n.text or '').strip() if n is not None and n.text else ''


def _dec(value):
    try:
        return Decimal(value) if value not in (None, '') else None
    except InvalidOperation:
        return None


def iban_ok(iban):
    s = re.sub(r'\s+', '', iban or '').upper()
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{10,30}', s):
        return False
    return int(''.join(str(int(ch, 36)) for ch in s[4:] + s[:4])) % 97 == 1


class _Report:
    def __init__(self):
        self.errors, self.warnings, self.checked = [], [], set()

    def rule(self, rule_id, ok, text, warn=False):
        self.checked.add(rule_id)
        if not ok:
            (self.warnings if warn else self.errors).append({'rule': rule_id, 'text': text})
        return ok


def check(xml_bytes):
    """Gibt ``{'valid', 'errors', 'warnings', 'rules_checked', 'profile', 'notice'}`` zurück."""
    r = _Report()
    try:
        if b'<!DOCTYPE' in xml_bytes[:4096].upper() or b'<!ENTITY' in xml_bytes.upper():
            raise ValueError('XML mit DOCTYPE/ENTITY wird abgelehnt.')
        root = ET.fromstring(xml_bytes)
    except (ET.ParseError, ValueError) as exc:
        return {'valid': False, 'errors': [{'rule': 'XML', 'text': f'Keine lesbare XML-Datei ({exc}).'}], 'warnings': [],
                'rules_checked': 1, 'profile': '', 'notice': NOTICE}
    if _local(root.tag) != 'Invoice':
        # CII oder Gutschrift: nicht geprüft – weder als gültig noch als fehlerhaft melden.
        return {'valid': None, 'errors': [], 'warnings': [{'rule': 'UBL', 'text': f'Nicht geprüft: Format {_local(root.tag)}. Die '
                                                           'Prüfung deckt nur UBL-Rechnungen ab; CII und Gutschriften prüft der KoSIT-Validator.'}],
                'rules_checked': 0, 'profile': _local(root.tag), 'notice': NOTICE}
    profile = _txt(root, 'CustomizationID')
    xr = profile.startswith(XRECHNUNG_3)
    _header(r, root, profile, xr)
    seller = _kid(root, 'AccountingSupplierParty', 'Party')
    buyer = _kid(root, 'AccountingCustomerParty', 'Party')
    _parties(r, seller, buyer, xr)
    lines = _kids(root, 'InvoiceLine')
    line_sum = _lines(r, lines)
    _totals(r, root, line_sum)
    _taxes(r, root, seller, lines)
    _payment(r, root, xr)
    return {'valid': not r.errors, 'errors': r.errors, 'warnings': r.warnings, 'rules_checked': len(r.checked),
            'profile': 'XRechnung 3.0' if xr else (profile or 'unbekannt'), 'notice': NOTICE}


NOTICE = ('Prüfung der häufigsten Regeln aus EN 16931 und XRechnung 3.0 – kein Ersatz für den KoSIT-Validator. '
          'Vor dem ersten Versand an ein Behördenportal einmal mit dem offiziellen Validator prüfen.')


def _date(r, rule, value, label):
    ok = bool(DATE_RE.match(value))
    if ok:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            ok = False
    return r.rule(rule, ok, f'{label}: kein gültiges Datum (JJJJ-MM-TT): „{value}“.')


def _header(r, root, profile, xr):
    r.rule('BR-01', bool(profile), 'Spezifikationskennung (BT-24, CustomizationID) fehlt.')
    r.rule('BR-DE-21', xr, f'Spezifikationskennung ist nicht XRechnung 3.0: „{profile}“.', warn=True)
    r.rule('BR-02', bool(_txt(root, 'ID')), 'Rechnungsnummer (BT-1) fehlt.')
    issue = _txt(root, 'IssueDate')
    if r.rule('BR-03', bool(issue), 'Rechnungsdatum (BT-2) fehlt.'):
        _date(r, 'BR-03', issue, 'Rechnungsdatum (BT-2)')
    code = _txt(root, 'InvoiceTypeCode')
    if r.rule('BR-04', bool(code), 'Rechnungsart (BT-3) fehlt.'):
        r.rule('BR-CL-01', code in TYPE_CODES, f'Rechnungsart „{code}“ ist nicht zulässig.')
    currency = _txt(root, 'DocumentCurrencyCode')
    if r.rule('BR-05', bool(currency), 'Währung (BT-5) fehlt.'):
        r.rule('BR-CL-04', bool(re.fullmatch(r'[A-Z]{3}', currency)), f'Währung „{currency}“ ist kein ISO-4217-Code.')
        r.rule('SD-EUR', currency == 'EUR', f'Währung {currency}: Beträge in Fremdwährung prüft diese Prüfung nicht.', warn=True)
    due = _txt(root, 'DueDate')
    if due:
        _date(r, 'BR-CL-DATE', due, 'Fälligkeitsdatum (BT-9)')
    r.rule('BR-DE-15', bool(_txt(root, 'BuyerReference')), 'Käuferreferenz/Leitweg-ID (BT-10) fehlt.')
    period = _kid(root, 'InvoicePeriod')
    if period is not None:
        start, end = _txt(period, 'StartDate'), _txt(period, 'EndDate')
        if start and end and DATE_RE.match(start) and DATE_RE.match(end):
            r.rule('BR-29', end >= start, 'Leistungszeitraum: Ende liegt vor dem Beginn (BT-73/74).')
    r.rule('BR-16', bool(_kids(root, 'InvoiceLine')), 'Keine Rechnungsposition (BG-25).')


def _email(r, rule, value, label):
    if not r.rule(rule, bool(value) and value != PLACEHOLDER_EMAIL, f'{label} fehlt.'):
        return
    r.rule(rule, bool(EMAIL_RE.match(value)), f'{label} ist keine E-Mail-Adresse: „{value}“.')


def _parties(r, seller, buyer, xr):
    r.rule('BR-06', bool(_txt(seller, 'PartyLegalEntity', 'RegistrationName')), 'Name des Verkäufers (BT-27) fehlt.')
    r.rule('BR-07', bool(_txt(buyer, 'PartyLegalEntity', 'RegistrationName')), 'Name des Käufers (BT-44) fehlt.')
    for who, party, rule_addr, rule_country, rule_city, rule_zip in (
            ('Verkäufer', seller, 'BR-08', 'BR-09', 'BR-DE-3', 'BR-DE-4'),
            ('Käufer', buyer, 'BR-10', 'BR-11', 'BR-DE-8', 'BR-DE-9')):
        addr = _kid(party, 'PostalAddress')
        if r.rule(rule_addr, addr is not None, f'Anschrift {who} fehlt.'):
            country = _txt(addr, 'Country', 'IdentificationCode')
            r.rule(rule_country, bool(re.fullmatch(r'[A-Z]{2}', country)), f'Ländercode {who} fehlt oder ist ungültig.')
            if xr:
                r.rule(rule_city, bool(_txt(addr, 'CityName')), f'Ort {who} fehlt.')
                r.rule(rule_zip, bool(_txt(addr, 'PostalZone')), f'PLZ {who} fehlt.')
    seller_endpoint = _kid(seller, 'EndpointID')
    buyer_endpoint = _kid(buyer, 'EndpointID')
    if xr:
        _email(r, 'BR-DE-16', _txt(seller, 'EndpointID'), 'Elektronische Adresse des Verkäufers (BT-34)')
        _email(r, 'BR-DE-26', _txt(buyer, 'EndpointID'), 'Elektronische Adresse des Käufers (BT-49)')
        for label, node in (('Verkäufer', seller_endpoint), ('Käufer', buyer_endpoint)):
            if node is not None:
                r.rule('BR-62/63', bool(node.get('schemeID')), f'Elektronische Adresse {label}: Schema (schemeID) fehlt.')
        contact = _kid(seller, 'Contact')
        if r.rule('BR-DE-2', contact is not None, 'Kontakt des Verkäufers (BG-6) fehlt.'):
            r.rule('BR-DE-5', bool(_txt(contact, 'Name')), 'Kontaktname des Verkäufers (BT-41) fehlt.')
            phone = _txt(contact, 'Telephone')
            r.rule('BR-DE-6', bool(phone) and phone != '-' and sum(ch.isdigit() for ch in phone) >= 3,
                   'Telefonnummer des Verkäufers (BT-42) fehlt.')
            _email(r, 'BR-DE-7', _txt(contact, 'ElectronicMail'), 'E-Mail des Verkäufers (BT-43)')
    ids = [(_txt(p, 'TaxScheme', 'ID'), _txt(p, 'CompanyID')) for p in _kids(seller, 'PartyTaxScheme')]
    vat = next((v for s, v in ids if s == 'VAT' and v), '')
    if vat:
        r.rule('BR-CO-09', bool(re.fullmatch(r'[A-Z]{2}[A-Z0-9+*.]{2,13}', vat)), f'USt-IdNr. des Verkäufers „{vat}“ beginnt nicht mit einem Ländercode.')
    r.seller_tax_ids = ids


def _lines(r, lines):
    total = Decimal('0')
    for i, line in enumerate(lines, 1):
        lid = _txt(line, 'ID') or str(i)
        r.rule('BR-21', bool(_txt(line, 'ID')), f'Position {i}: Kennung (BT-126) fehlt.')
        qty_node = _kid(line, 'InvoicedQuantity')
        qty = _dec(_txt(line, 'InvoicedQuantity'))
        r.rule('BR-22', qty is not None, f'Position {lid}: Menge (BT-129) fehlt.')
        unit = qty_node.get('unitCode', '') if qty_node is not None else ''
        r.rule('BR-23', bool(UNIT_RE.match(unit)), f'Position {lid}: Einheit (BT-130) fehlt oder ist ungültig.')
        amount = _dec(_txt(line, 'LineExtensionAmount'))
        r.rule('BR-24', amount is not None, f'Position {lid}: Nettobetrag (BT-131) fehlt.')
        r.rule('BR-25', bool(_txt(line, 'Item', 'Name')), f'Position {lid}: Bezeichnung (BT-153) fehlt.')
        price = _dec(_txt(line, 'Price', 'PriceAmount'))
        if r.rule('BR-26', price is not None, f'Position {lid}: Nettopreis (BT-146) fehlt.'):
            r.rule('BR-27', price >= 0, f'Position {lid}: Nettopreis darf nicht negativ sein.')
        r.rule('BR-CO-04', bool(_txt(line, 'Item', 'ClassifiedTaxCategory', 'ID')),
               f'Position {lid}: Umsatzsteuerkategorie (BT-151) fehlt.')
        if qty is not None and price is not None and amount is not None:
            base = _dec(_txt(line, 'Price', 'BaseQuantity')) or Decimal('1')
            expected = (qty * price / base).quantize(CENT)
            r.rule('SD-LINE', abs(expected - amount) <= CENT, f'Position {lid}: Menge × Preis = {expected}, angegeben {amount}.')
        if amount is not None:
            total += amount
    return total


def _money(node, name):
    return _dec(_txt(node, name))


def _totals(r, root, line_sum):
    m = _kid(root, 'LegalMonetaryTotal')
    if not r.rule('BR-12', m is not None and _money(m, 'LineExtensionAmount') is not None, 'Summe der Positionen (BT-106) fehlt.'):
        return
    lines_total = _money(m, 'LineExtensionAmount')
    tax_excl = _money(m, 'TaxExclusiveAmount')
    tax_incl = _money(m, 'TaxInclusiveAmount')
    payable = _money(m, 'PayableAmount')
    r.rule('BR-13', tax_excl is not None, 'Gesamtbetrag ohne USt (BT-109) fehlt.')
    r.rule('BR-14', tax_incl is not None, 'Gesamtbetrag mit USt (BT-112) fehlt.')
    r.rule('BR-15', payable is not None, 'Zahlbetrag (BT-115) fehlt.')
    r.rule('BR-CO-10', lines_total == line_sum.quantize(CENT), f'Summe der Positionen {line_sum} ≠ BT-106 {lines_total}.')
    allowances = _money(m, 'AllowanceTotalAmount') or Decimal('0')
    charges = _money(m, 'ChargeTotalAmount') or Decimal('0')
    if tax_excl is not None:
        r.rule('BR-CO-13', tax_excl == lines_total - allowances + charges,
               f'BT-109 {tax_excl} ≠ Positionen {lines_total} − Nachlässe {allowances} + Zuschläge {charges}.')
    vat = sum((_dec(_txt(t, 'TaxAmount')) or Decimal('0')) for t in _kids(root, 'TaxTotal') if _kids(t, 'TaxSubtotal'))
    if tax_excl is not None and tax_incl is not None:
        r.rule('BR-CO-15', tax_incl == tax_excl + vat, f'BT-112 {tax_incl} ≠ BT-109 {tax_excl} + USt {vat}.')
    if tax_incl is not None and payable is not None:
        prepaid = _money(m, 'PrepaidAmount') or Decimal('0')
        rounding = _money(m, 'PayableRoundingAmount') or Decimal('0')
        r.rule('BR-CO-16', payable == tax_incl - prepaid + rounding, f'Zahlbetrag {payable} ≠ {tax_incl} − Anzahlung {prepaid} + Rundung {rounding}.')
    for name in ('LineExtensionAmount', 'TaxExclusiveAmount', 'TaxInclusiveAmount', 'PayableAmount'):
        node = _kid(m, name)
        if node is not None:
            r.rule('BR-DEC-01', len((node.text or '').strip().partition('.')[2]) <= 2, f'{name}: höchstens zwei Nachkommastellen.')


def _taxes(r, root, seller, lines):
    totals = [t for t in _kids(root, 'TaxTotal') if _kids(t, 'TaxSubtotal')]
    if not r.rule('BR-CO-18', bool(totals), 'Keine Aufschlüsselung der Umsatzsteuer (BG-23).'):
        return
    subs = _kids(totals[0], 'TaxSubtotal')
    by_cat = {}
    for line in lines:
        cat = _kid(line, 'Item', 'ClassifiedTaxCategory')
        key = (_txt(cat, 'ID'), _dec(_txt(cat, 'Percent')) or Decimal('0'))
        by_cat[key] = by_cat.get(key, Decimal('0')) + (_dec(_txt(line, 'LineExtensionAmount')) or Decimal('0'))
    seen = set()
    for sub in subs:
        cat = _kid(sub, 'TaxCategory')
        code = _txt(cat, 'ID')
        rate = _dec(_txt(cat, 'Percent')) or Decimal('0')
        base = _dec(_txt(sub, 'TaxableAmount'))
        tax = _dec(_txt(sub, 'TaxAmount'))
        label = f'Steuergruppe {code} {rate} %'
        r.rule('BR-CL-17', code in CATEGORIES, f'{label}: unbekannte Umsatzsteuerkategorie.')
        r.rule('BR-45', base is not None, f'{label}: Bemessungsgrundlage (BT-116) fehlt.')
        r.rule('BR-46', tax is not None, f'{label}: Steuerbetrag (BT-117) fehlt.')
        seen.add((code, rate))
        if base is not None and (code, rate) in by_cat:
            r.rule(f'BR-{code}-08' if code in ('S', 'Z', 'E', 'AE') else 'BR-CO-BASE', base == by_cat[(code, rate)].quantize(CENT),
                   f'{label}: Bemessungsgrundlage {base} ≠ Summe der Positionen {by_cat[(code, rate)]}.')
        if base is not None and tax is not None:
            if code == 'S':
                expected = (base * rate / 100).quantize(CENT)
                r.rule('BR-S-09', abs(expected - tax) <= CENT, f'{label}: Steuer {tax} ≠ {base} × {rate} % = {expected}.')
                r.rule('BR-S-05', rate > 0, f'{label}: Normalsatz mit 0 %.')
            elif code in ('Z', 'E', 'AE', 'K', 'G', 'O'):
                r.rule(f'BR-{code}-09', tax == 0, f'{label}: Steuerbetrag muss 0 sein.')
        if code in ('E', 'AE', 'K', 'G', 'O'):
            r.rule(f'BR-{code}-10', bool(_txt(cat, 'TaxExemptionReason') or _txt(cat, 'TaxExemptionReasonCode')),
                   f'{label}: Befreiungsgrund (BT-120/121) fehlt.')
        if code in ('S', 'Z', 'E', 'AE'):
            ids = {s for s, v in getattr(r, 'seller_tax_ids', []) if v}
            r.rule(f'BR-{code}-02', bool(ids & {'VAT', 'FC'}) if code != 'E' else bool(ids),
                   f'{label}: USt-IdNr. oder Steuernummer des Verkäufers (BT-31/32) fehlt.')
    missing = sorted(set(by_cat) - seen)
    r.rule('BR-CO-17', not missing, 'Positionen ohne passende Steuergruppe: ' + ', '.join(f'{c} {p} %' for c, p in missing))


def _payment(r, root, xr):
    means = _kids(root, 'PaymentMeans')
    if xr:
        r.rule('BR-DE-1', bool(means), 'Zahlungsanweisungen (BG-16) fehlen.')
    for m in means:
        code = _txt(m, 'PaymentMeansCode')
        if not r.rule('BR-49', bool(code), 'Zahlungsart (BT-81) fehlt.'):
            continue
        r.rule('BR-CL-16', code in PAYMENT_CODES, f'Zahlungsart „{code}“ ist nicht zulässig.')
        if code in CREDIT_TRANSFER:
            iban = _txt(m, 'PayeeFinancialAccount', 'ID')
            if r.rule('BR-DE-23-a', bool(iban), 'Überweisung ohne IBAN (BT-84).'):
                r.rule('BR-DE-19', iban_ok(iban), f'IBAN „{iban}“: Prüfziffer stimmt nicht.')
        if code in DIRECT_DEBIT and xr:
            r.rule('BR-DE-24-b', bool(_txt(m, 'PaymentMandate', 'ID')), 'Lastschrift ohne Mandatsreferenz (BT-89).')
    due = _txt(root, 'DueDate')
    terms = _txt(root, 'PaymentTerms', 'Note')
    payable = _dec(_txt(root, 'LegalMonetaryTotal', 'PayableAmount'))
    if payable is not None and payable > 0:
        r.rule('BR-CO-25', bool(due or terms), 'Zahlbetrag > 0 ohne Fälligkeitsdatum (BT-9) oder Zahlungsbedingungen (BT-20).')
