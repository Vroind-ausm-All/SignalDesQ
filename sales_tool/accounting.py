"""Lokale Rechnungsstellung und einfache Buchhaltung (v1.0).

Grundsätze:
- Beträge werden intern ausschließlich in ganzen Cent (int) gespeichert.
- Rechnungen sind bis zur Festschreibung Entwürfe. Festgeschriebene Rechnungen
  sind per SQLite-Trigger unveränderbar (GoBD: Unveränderbarkeit). Korrekturen
  erfolgen ausschließlich über eine Stornorechnung.
- Rechnungsnummern werden erst bei Festschreibung lückenlos je Jahr vergeben.
- Jede buchhalterisch relevante Aktion landet im Änderungsprotokoll (audit_log).
- Es wird nichts versendet und nichts an ELSTER/DATEV übermittelt. Auswertungen
  sind Vorbereitungen für die eigene Prüfung bzw. den Steuerberater.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

INVOICE_KINDS = ('rechnung', 'abschlag', 'schluss', 'storno')
INVOICE_STATUSES = ('entwurf', 'offen', 'teilbezahlt', 'bezahlt', 'storniert')
TAX_MODES = ('regel', 'kleinunternehmer', 'reverse_charge')
VAT_RATES = (0, 7, 19)
UNITS = {  # Anzeige → UN/ECE Rec. 20 Code für die E-Rechnung
    'pauschal': ('Pauschal', 'LS'), 'stueck': ('Stück', 'C62'), 'monat': ('Monat', 'MON'),
    'stunde': ('Stunde', 'HUR'), 'tag': ('Tag', 'DAY'),
}
PAYMENT_METHODS = ('ueberweisung', 'lastschrift', 'paypal', 'bar', 'sonstiges')
DUNNING_LEVELS = {1: 'Zahlungserinnerung', 2: '1. Mahnung', 3: 'Letzte Mahnung'}
# Kontenvorschläge SKR03 – ausdrücklich nur Vorschläge, mit Steuerberatung abstimmen.
EXPENSE_CATEGORIES = {
    'fremdleistung': ('Fremdleistungen / Freelancer', '3100'),
    'software': ('Software, Lizenzen, SaaS', '4964'),
    'hardware_gwg': ('Hardware / GWG bis 800 € netto', '4855'),
    'werbung': ('Werbung & Anzeigen', '4600'),
    'buero': ('Bürobedarf', '4930'),
    'telefon_internet': ('Telefon & Internet', '4920'),
    'reise': ('Reisekosten', '4660'),
    'fortbildung': ('Fortbildung & Fachliteratur', '4945'),
    'beratung': ('Rechts- & Steuerberatung', '4950'),
    'versicherung': ('Versicherungen', '4360'),
    'miete': ('Miete & Raumkosten', '4210'),
    'bank': ('Kontoführung & Zahlungsgebühren', '4970'),
    'sonstiges': ('Sonstige betriebliche Ausgaben', '4900'),
}
REVENUE_ACCOUNTS = {'regel_19': '8400', 'regel_7': '8300', 'regel_0': '8200',
                    'kleinunternehmer': '8195', 'reverse_charge': '8338'}
SETTINGS_FIELDS = {
    'company_name': 200, 'owner_name': 160, 'street': 200, 'zip': 10, 'city': 120, 'country': 2,
    'tax_number': 40, 'vat_id': 20, 'email': 200, 'phone': 60, 'website': 200,
    'iban': 34, 'bic': 11, 'bank_name': 120, 'invoice_prefix': 8, 'footer_note': 500,
}
SETTINGS_DEFAULTS = {'country': 'DE', 'invoice_prefix': 'RE', 'payment_days': 14, 'small_business': 0,
                     'tax_basis': 'ist', 'base_rate_pct': '1.27'}
SMALL_BUSINESS_NOTE = 'Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.'
REVERSE_CHARGE_NOTE = 'Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, § 13b UStG / Art. 196 MwStSystRL).'
STORNO_NOTE = 'Diese Stornorechnung hebt die unten genannte Rechnung vollständig auf.'


# ---------------------------------------------------------------- Schema

def init_accounting(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS company_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        company_name TEXT NOT NULL DEFAULT '', owner_name TEXT NOT NULL DEFAULT '',
        street TEXT NOT NULL DEFAULT '', zip TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT 'DE', tax_number TEXT NOT NULL DEFAULT '', vat_id TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
        iban TEXT NOT NULL DEFAULT '', bic TEXT NOT NULL DEFAULT '', bank_name TEXT NOT NULL DEFAULT '',
        small_business INTEGER NOT NULL DEFAULT 0, tax_basis TEXT NOT NULL DEFAULT 'ist',
        payment_days INTEGER NOT NULL DEFAULT 14, invoice_prefix TEXT NOT NULL DEFAULT 'RE',
        base_rate_pct TEXT NOT NULL DEFAULT '1.27', footer_note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      INSERT OR IGNORE INTO company_settings(id) VALUES (1);
      CREATE TABLE IF NOT EXISTS number_sequences (
        prefix TEXT NOT NULL, year INTEGER NOT NULL, last INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (prefix, year)
      );
      CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT UNIQUE, kind TEXT NOT NULL DEFAULT 'rechnung', status TEXT NOT NULL DEFAULT 'entwurf',
        lead_id INTEGER REFERENCES leads(id), proposal_id INTEGER REFERENCES proposals(id),
        corrects_invoice_id INTEGER REFERENCES invoices(id),
        tax_mode TEXT NOT NULL DEFAULT 'regel',
        issue_date TEXT NOT NULL DEFAULT '', service_from TEXT NOT NULL DEFAULT '', service_to TEXT NOT NULL DEFAULT '',
        payment_days INTEGER NOT NULL DEFAULT 14, due_date TEXT NOT NULL DEFAULT '',
        buyer_name TEXT NOT NULL DEFAULT '', buyer_contact TEXT NOT NULL DEFAULT '',
        buyer_street TEXT NOT NULL DEFAULT '', buyer_zip TEXT NOT NULL DEFAULT '', buyer_city TEXT NOT NULL DEFAULT '',
        buyer_country TEXT NOT NULL DEFAULT 'DE', buyer_vat_id TEXT NOT NULL DEFAULT '',
        buyer_reference TEXT NOT NULL DEFAULT '', buyer_email TEXT NOT NULL DEFAULT '',
        intro_text TEXT NOT NULL DEFAULT '', closing_text TEXT NOT NULL DEFAULT '',
        net_cents INTEGER NOT NULL DEFAULT 0, vat_cents INTEGER NOT NULL DEFAULT 0, gross_cents INTEGER NOT NULL DEFAULT 0,
        seller_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), finalized_at TEXT NOT NULL DEFAULT '',
        cancelled_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS invoice_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, description TEXT NOT NULL, quantity TEXT NOT NULL DEFAULT '1',
        unit TEXT NOT NULL DEFAULT 'pauschal', unit_price_cents INTEGER NOT NULL,
        vat_rate INTEGER NOT NULL DEFAULT 19, net_cents INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        paid_on TEXT NOT NULL, amount_cents INTEGER NOT NULL, method TEXT NOT NULL DEFAULT 'ueberweisung',
        note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS dunning_notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        level INTEGER NOT NULL, created_on TEXT NOT NULL, new_due_date TEXT NOT NULL,
        outstanding_cents INTEGER NOT NULL, interest_cents INTEGER NOT NULL DEFAULT 0,
        fee_cents INTEGER NOT NULL DEFAULT 0, text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_date TEXT NOT NULL, paid_on TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'sonstiges',
        net_cents INTEGER NOT NULL, vat_rate INTEGER NOT NULL DEFAULT 19, vat_cents INTEGER NOT NULL DEFAULT 0,
        gross_cents INTEGER NOT NULL, reverse_charge INTEGER NOT NULL DEFAULT 0,
        receipt_ref TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'aktiv', source TEXT NOT NULL DEFAULT 'manuell',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now')), entity TEXT NOT NULL, entity_id INTEGER,
        action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status, due_date);
      CREATE INDEX IF NOT EXISTS idx_invoices_lead ON invoices(lead_id);
      CREATE INDEX IF NOT EXISTS idx_invoice_lines_inv ON invoice_lines(invoice_id, position);
      CREATE INDEX IF NOT EXISTS idx_payments_inv ON payments(invoice_id);
      CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(paid_on);
      CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);

      -- GoBD: festgeschriebene Rechnungen bleiben inhaltlich unverändert.
      CREATE TRIGGER IF NOT EXISTS trg_invoice_immutable
      BEFORE UPDATE OF number, kind, lead_id, proposal_id, corrects_invoice_id, tax_mode, issue_date,
        service_from, service_to, payment_days, due_date, buyer_name, buyer_contact, buyer_street, buyer_zip,
        buyer_city, buyer_country, buyer_vat_id, buyer_reference, buyer_email, intro_text, closing_text,
        net_cents, vat_cents, gross_cents, seller_json, finalized_at ON invoices
      WHEN OLD.status <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Festgeschriebene Rechnung ist unveränderbar – Korrektur nur per Storno.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_invoice_no_delete
      BEFORE DELETE ON invoices WHEN OLD.status <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Festgeschriebene Rechnung darf nicht gelöscht werden.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_lines_insert_locked
      BEFORE INSERT ON invoice_lines
      WHEN (SELECT status FROM invoices WHERE id = NEW.invoice_id) <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Positionen festgeschriebener Rechnungen sind gesperrt.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_lines_update_locked
      BEFORE UPDATE ON invoice_lines
      WHEN (SELECT status FROM invoices WHERE id = OLD.invoice_id) <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Positionen festgeschriebener Rechnungen sind gesperrt.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_lines_delete_locked
      BEFORE DELETE ON invoice_lines
      WHEN (SELECT status FROM invoices WHERE id = OLD.invoice_id) <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Positionen festgeschriebener Rechnungen sind gesperrt.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_audit_no_update
      BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'Protokoll ist unveränderbar.'); END;
      CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
      BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'Protokoll ist unveränderbar.'); END;
    ''')


def audit(conn, entity, entity_id, action, detail=''):
    conn.execute('INSERT INTO audit_log(entity,entity_id,action,detail) VALUES (?,?,?,?)',
                 (entity, entity_id, action, str(detail)[:2000]))


# ---------------------------------------------------------------- Hilfsfunktionen

def today():
    return dt.date.today()


def cents(value, key='Betrag', lo=-100_000_000, hi=100_000_000):
    """Euro-Eingabe (Zahl oder Text mit Komma/Punkt) → ganze Cent."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f'{key}: Betrag erforderlich.')
    if isinstance(value, str):
        raw = value.strip().replace(' ', '').replace('€', '')
        if ',' in raw:
            raw = raw.replace('.', '').replace(',', '.')
        value = raw
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{key}: ungültiger Betrag.') from exc
    if not amount.is_finite():
        raise ValueError(f'{key}: ungültiger Betrag.')
    result = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if not lo * 100 <= result <= hi * 100:
        raise ValueError(f'{key}: Betrag außerhalb des erlaubten Bereichs.')
    return result


def eur(c):
    """Cent → '1.234,56' (deutsches Format, ohne Währungszeichen)."""
    sign = '-' if c < 0 else ''
    c = abs(int(c))
    whole = f'{c // 100:,}'.replace(',', '.')
    return f'{sign}{whole},{c % 100:02d}'


def eur_dot(c):
    """Cent → '1234.56' (für XML)."""
    sign = '-' if c < 0 else ''
    c = abs(int(c))
    return f'{sign}{c // 100}.{c % 100:02d}'


def _quantity(value):
    try:
        q = Decimal(str(value).replace(',', '.')) if not isinstance(value, bool) else None
    except InvalidOperation:
        q = None
    if q is None or not q.is_finite() or q <= 0 or q > 100000 or q != q.quantize(Decimal('0.001')):
        raise ValueError('Menge: positive Zahl mit höchstens 3 Nachkommastellen.')
    return q


def _text(data, key, max_len, required=False):
    value = data.get(key, '')
    if value is None:
        value = ''
    if not isinstance(value, str) or len(value.strip()) > max_len:
        raise ValueError(f'{key}: Text mit höchstens {max_len} Zeichen.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{key}: Angabe erforderlich.')
    return value


def _date(value, key, required=False):
    if value in (None, ''):
        if required:
            raise ValueError(f'{key}: Datum erforderlich.')
        return ''
    if not isinstance(value, str):
        raise ValueError(f'{key}: Datum als JJJJ-MM-TT.')
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'{key}: Datum als JJJJ-MM-TT.') from exc
    return value


def _int_id(value, key='ID'):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError(f'Ungültige {key}.')
    return int(value)


def iban_valid(iban):
    s = re.sub(r'\s+', '', iban or '').upper()
    if not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{10,30}', s):
        return False
    rearranged = s[4:] + s[:4]
    digits = ''.join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


# ---------------------------------------------------------------- Stammdaten

def get_settings(conn):
    row = dict(conn.execute('SELECT * FROM company_settings WHERE id=1').fetchone())
    row['small_business'] = bool(row['small_business'])
    row['missing'] = settings_missing(row)
    return row


def settings_missing(s):
    missing = []
    for key, label in (('company_name', 'Firmenname'), ('street', 'Straße'), ('zip', 'PLZ'), ('city', 'Ort'),
                       ('email', 'E-Mail (für E-Rechnung)'), ('iban', 'IBAN')):
        if not str(s.get(key) or '').strip():
            missing.append(label)
    if not (str(s.get('tax_number') or '').strip() or str(s.get('vat_id') or '').strip()):
        missing.append('Steuernummer oder USt-IdNr.')
    return missing


def save_settings(conn, data):
    if not isinstance(data, dict):
        raise ValueError('JSON-Objekt erwartet.')
    allowed = set(SETTINGS_FIELDS) | {'small_business', 'tax_basis', 'payment_days', 'base_rate_pct'}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError('Unbekannte Felder: ' + ', '.join(sorted(unknown)))
    out = {}
    for key, limit in SETTINGS_FIELDS.items():
        if key in data:
            out[key] = _text(data, key, limit)
    if 'country' in out:
        out['country'] = out['country'].upper() or 'DE'
        if not re.fullmatch(r'[A-Z]{2}', out['country']):
            raise ValueError('Land als zweistelliger ISO-Code, z. B. DE.')
    if out.get('iban'):
        out['iban'] = re.sub(r'\s+', '', out['iban']).upper()
        if not iban_valid(out['iban']):
            raise ValueError('IBAN-Prüfziffer ungültig.')
    if out.get('bic'):
        out['bic'] = out['bic'].replace(' ', '').upper()
        if not re.fullmatch(r'[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?', out['bic']):
            raise ValueError('BIC ungültig.')
    if out.get('vat_id'):
        out['vat_id'] = out['vat_id'].replace(' ', '').upper()
        if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{2,13}', out['vat_id']):
            raise ValueError('USt-IdNr. ungültig (z. B. DE123456789).')
    if 'invoice_prefix' in out:
        if not re.fullmatch(r'[A-Z0-9]{1,8}', out['invoice_prefix'] or ''):
            raise ValueError('Rechnungspräfix: 1–8 Großbuchstaben/Ziffern.')
    if 'email' in out and out['email'] and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', out['email']):
        raise ValueError('E-Mail-Adresse ungültig.')
    if 'small_business' in data:
        if not isinstance(data['small_business'], bool):
            raise ValueError('small_business: true/false.')
        out['small_business'] = int(data['small_business'])
    if 'tax_basis' in data:
        if data['tax_basis'] not in ('ist', 'soll'):
            raise ValueError('Versteuerung: ist oder soll.')
        out['tax_basis'] = data['tax_basis']
    if 'payment_days' in data:
        days = data['payment_days']
        if isinstance(days, bool) or type(days) is not int or not 0 <= days <= 120:
            raise ValueError('Zahlungsziel: 0–120 Tage.')
        out['payment_days'] = days
    if 'base_rate_pct' in data:
        try:
            rate = Decimal(str(data['base_rate_pct']).replace(',', '.'))
        except InvalidOperation as exc:
            raise ValueError('Basiszinssatz ungültig.') from exc
        if not rate.is_finite() or not Decimal('-5') <= rate <= Decimal('15'):
            raise ValueError('Basiszinssatz ungültig.')
        out['base_rate_pct'] = str(rate)
    if not out:
        raise ValueError('Keine Änderung.')
    conn.execute(f"UPDATE company_settings SET {', '.join(k + '=?' for k in out)}, updated_at=datetime('now') WHERE id=1",
                 tuple(out.values()))
    audit(conn, 'settings', 1, 'geaendert', ', '.join(sorted(out)))
    conn.commit()
    return get_settings(conn)


# ---------------------------------------------------------------- Rechnungen: Berechnung

def compute_totals(lines, tax_mode):
    """Summen je Steuersatz (EN 16931: USt je Kategorie auf die Nettosumme)."""
    groups = {}
    for line in lines:
        rate = line['vat_rate'] if tax_mode == 'regel' else 0
        groups[rate] = groups.get(rate, 0) + line['net_cents']
    breakdown = []
    for rate in sorted(groups, reverse=True):
        net = groups[rate]
        vat = int((Decimal(net) * Decimal(rate) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        breakdown.append({'rate': rate, 'net_cents': net, 'vat_cents': vat})
    net = sum(g['net_cents'] for g in breakdown)
    vat = sum(g['vat_cents'] for g in breakdown)
    return {'net_cents': net, 'vat_cents': vat, 'gross_cents': net + vat, 'breakdown': breakdown}


def _validate_lines(raw_lines, tax_mode, allow_negative_total=False):
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 60:
        raise ValueError('Eine Rechnung braucht 1–60 Positionen.')
    lines = []
    for index, raw in enumerate(raw_lines, 1):
        if not isinstance(raw, dict) or set(raw) - {'description', 'quantity', 'unit', 'unit_price_eur', 'unit_price_cents', 'vat_rate'}:
            raise ValueError(f'Position {index}: ungültige Felder.')
        description = _text(raw, 'description', 1000, required=True)
        quantity = _quantity(raw.get('quantity', 1))
        unit = raw.get('unit', 'pauschal')
        if unit not in UNITS:
            raise ValueError(f'Position {index}: unbekannte Einheit.')
        if 'unit_price_cents' in raw:
            price = raw['unit_price_cents']
            if isinstance(price, bool) or type(price) is not int or abs(price) > 10_000_000_000:
                raise ValueError(f'Position {index}: ungültiger Preis.')
        else:
            price = cents(raw.get('unit_price_eur'), f'Position {index} Einzelpreis', -10_000_000, 10_000_000)
        rate = raw.get('vat_rate', 19)
        if isinstance(rate, bool) or rate not in VAT_RATES:
            raise ValueError(f'Position {index}: Steuersatz 0, 7 oder 19 %.')
        if tax_mode != 'regel':
            rate = 0
        net = int((quantity * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        lines.append({'position': index, 'description': description, 'quantity': format(quantity.normalize(), 'f'),
                      'unit': unit, 'unit_price_cents': price, 'vat_rate': rate, 'net_cents': net})
    totals = compute_totals(lines, tax_mode)
    if not allow_negative_total and totals['gross_cents'] <= 0:
        raise ValueError('Rechnungsbetrag muss größer als 0 sein.')
    return lines, totals


def _validate_invoice(conn, data, settings):
    allowed = {'lead_id', 'kind', 'tax_mode', 'issue_date', 'service_from', 'service_to', 'payment_days',
               'buyer_name', 'buyer_contact', 'buyer_street', 'buyer_zip', 'buyer_city', 'buyer_country',
               'buyer_vat_id', 'buyer_reference', 'buyer_email', 'intro_text', 'closing_text', 'lines'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Ungültige Rechnungsfelder: ' + ', '.join(sorted(set(data) - allowed)) if isinstance(data, dict) else 'JSON-Objekt erwartet.')
    lead_id = data.get('lead_id')
    if lead_id in ('', None):
        lead_id = None
    else:
        lead_id = _int_id(lead_id, 'Lead-ID')
        if not conn.execute('SELECT id FROM leads WHERE id=?', (lead_id,)).fetchone():
            raise ValueError('Lead existiert nicht.')
    kind = data.get('kind', 'rechnung')
    if kind not in ('rechnung', 'abschlag', 'schluss'):
        raise ValueError('Rechnungsart ungültig.')
    tax_mode = data.get('tax_mode') or ('kleinunternehmer' if settings['small_business'] else 'regel')
    if tax_mode not in TAX_MODES:
        raise ValueError('Steuerbehandlung ungültig.')
    if settings['small_business'] and tax_mode != 'kleinunternehmer':
        raise ValueError('In den Stammdaten ist § 19 UStG aktiv – nur Kleinunternehmer-Rechnungen möglich.')
    if not settings['small_business'] and tax_mode == 'kleinunternehmer':
        raise ValueError('Kleinunternehmerregelung ist in den Stammdaten nicht aktiviert.')
    payment_days = data.get('payment_days', settings['payment_days'])
    if isinstance(payment_days, bool) or type(payment_days) is not int or not 0 <= payment_days <= 120:
        raise ValueError('Zahlungsziel: 0–120 Tage.')
    out = {
        'lead_id': lead_id, 'kind': kind, 'tax_mode': tax_mode, 'payment_days': payment_days,
        'issue_date': _date(data.get('issue_date'), 'Rechnungsdatum'),
        'service_from': _date(data.get('service_from'), 'Leistungsdatum'),
        'service_to': _date(data.get('service_to'), 'Leistungszeitraum bis'),
        'buyer_name': _text(data, 'buyer_name', 200), 'buyer_contact': _text(data, 'buyer_contact', 160),
        'buyer_street': _text(data, 'buyer_street', 200), 'buyer_zip': _text(data, 'buyer_zip', 10),
        'buyer_city': _text(data, 'buyer_city', 120),
        'buyer_country': (_text(data, 'buyer_country', 2) or 'DE').upper(),
        'buyer_vat_id': _text(data, 'buyer_vat_id', 20).replace(' ', '').upper(),
        'buyer_reference': _text(data, 'buyer_reference', 100), 'buyer_email': _text(data, 'buyer_email', 200),
        'intro_text': _text(data, 'intro_text', 1000), 'closing_text': _text(data, 'closing_text', 1000),
    }
    if not re.fullmatch(r'[A-Z]{2}', out['buyer_country']):
        raise ValueError('Land des Kunden als ISO-Code, z. B. DE.')
    if out['service_from'] and out['service_to'] and out['service_to'] < out['service_from']:
        raise ValueError('Leistungszeitraum: Ende liegt vor Beginn.')
    lines, totals = _validate_lines(data.get('lines'), tax_mode)
    return out, lines, totals


def _store_lines(conn, invoice_id, lines):
    conn.execute('DELETE FROM invoice_lines WHERE invoice_id=?', (invoice_id,))
    for line in lines:
        conn.execute('INSERT INTO invoice_lines(invoice_id,position,description,quantity,unit,unit_price_cents,vat_rate,net_cents) VALUES (?,?,?,?,?,?,?,?)',
                     (invoice_id, line['position'], line['description'], line['quantity'], line['unit'],
                      line['unit_price_cents'], line['vat_rate'], line['net_cents']))


def create_invoice(conn, data, proposal_id=None, commit=True):
    settings = get_settings(conn)
    header, lines, totals = _validate_invoice(conn, data, settings)
    cols = {**header, 'proposal_id': proposal_id, 'net_cents': totals['net_cents'],
            'vat_cents': totals['vat_cents'], 'gross_cents': totals['gross_cents']}
    cur = conn.execute(f"INSERT INTO invoices ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(cols.values()))
    _store_lines(conn, cur.lastrowid, lines)
    audit(conn, 'invoice', cur.lastrowid, 'entwurf_angelegt', f"{eur(totals['gross_cents'])} EUR brutto")
    if commit:
        conn.commit()
    return invoice_detail(conn, cur.lastrowid)


def update_invoice(conn, invoice_id, data):
    row = _invoice_row(conn, invoice_id)
    if row['status'] != 'entwurf':
        raise ValueError('Nur Entwürfe können bearbeitet werden. Festgeschriebene Rechnungen per Storno korrigieren.')
    settings = get_settings(conn)
    header, lines, totals = _validate_invoice(conn, data, settings)
    if 'kind' not in data:
        header['kind'] = row['kind']
    cols = {**header, 'net_cents': totals['net_cents'], 'vat_cents': totals['vat_cents'], 'gross_cents': totals['gross_cents']}
    conn.execute(f"UPDATE invoices SET {', '.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), invoice_id))
    _store_lines(conn, invoice_id, lines)
    conn.commit()
    return invoice_detail(conn, invoice_id)


def delete_draft(conn, invoice_id):
    row = _invoice_row(conn, invoice_id)
    if row['status'] != 'entwurf':
        raise ValueError('Festgeschriebene Rechnungen können nicht gelöscht werden (GoBD). Bitte stornieren.')
    conn.execute('DELETE FROM invoices WHERE id=?', (invoice_id,))
    audit(conn, 'invoice', invoice_id, 'entwurf_geloescht')
    conn.commit()
    return {'deleted': True}


def _invoice_row(conn, invoice_id):
    row = conn.execute('SELECT * FROM invoices WHERE id=?', (invoice_id,)).fetchone()
    if not row:
        raise LookupError('Rechnung nicht gefunden.')
    return row


def paid_cents(conn, invoice_id):
    return conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE invoice_id=?', (invoice_id,)).fetchone()[0]


def invoice_detail(conn, invoice_id):
    row = dict(_invoice_row(conn, invoice_id))
    row['lines'] = [dict(r) for r in conn.execute('SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY position', (invoice_id,))]
    row['totals'] = compute_totals(row['lines'], row['tax_mode'])
    row['seller'] = json.loads(row.pop('seller_json') or '{}')
    row['payments'] = [dict(r) for r in conn.execute('SELECT * FROM payments WHERE invoice_id=? ORDER BY paid_on, id', (invoice_id,))]
    row['dunning'] = [dict(r) for r in conn.execute('SELECT * FROM dunning_notices WHERE invoice_id=? ORDER BY level, id', (invoice_id,))]
    row['paid_cents'] = sum(p['amount_cents'] for p in row['payments'])
    row['outstanding_cents'] = row['gross_cents'] - row['paid_cents'] if row['status'] in ('offen', 'teilbezahlt') else 0
    row['overdue_days'] = _overdue_days(row)
    row['corrected_by'] = [dict(r) for r in conn.execute('SELECT id, number FROM invoices WHERE corrects_invoice_id=?', (invoice_id,))]
    if row['corrects_invoice_id']:
        ref = conn.execute('SELECT number, issue_date FROM invoices WHERE id=?', (row['corrects_invoice_id'],)).fetchone()
        row['corrects'] = dict(ref) if ref else None
    row['checks'] = finalize_checks(row, get_settings(conn)) if row['status'] == 'entwurf' else []
    row['notes'] = invoice_tax_notes(row)
    return row


def _overdue_days(row):
    if row['status'] not in ('offen', 'teilbezahlt') or not row['due_date']:
        return 0
    return max(0, (today() - dt.date.fromisoformat(row['due_date'])).days)


def invoice_tax_notes(inv):
    notes = []
    if inv['tax_mode'] == 'kleinunternehmer':
        notes.append(SMALL_BUSINESS_NOTE)
    if inv['tax_mode'] == 'reverse_charge':
        notes.append(REVERSE_CHARGE_NOTE)
    if inv['kind'] == 'storno':
        notes.append(STORNO_NOTE)
    return notes


def invoice_rows(conn, status=None):
    sql = '''SELECT i.id,i.number,i.kind,i.status,i.lead_id,i.buyer_name,i.issue_date,i.due_date,
               i.net_cents,i.vat_cents,i.gross_cents,i.corrects_invoice_id,i.proposal_id,
               COALESCE((SELECT SUM(amount_cents) FROM payments p WHERE p.invoice_id=i.id),0) AS paid_cents,
               COALESCE((SELECT MAX(level) FROM dunning_notices d WHERE d.invoice_id=i.id),0) AS dunning_level
             FROM invoices i'''
    params = ()
    if status:
        if status not in INVOICE_STATUSES:
            raise ValueError('Ungültiger Status.')
        sql += ' WHERE i.status=?'
        params = (status,)
    sql += " ORDER BY (i.status='entwurf') DESC, i.issue_date DESC, i.id DESC LIMIT 500"
    rows = []
    for r in conn.execute(sql, params):
        item = dict(r)
        item['outstanding_cents'] = item['gross_cents'] - item['paid_cents'] if item['status'] in ('offen', 'teilbezahlt') else 0
        item['overdue_days'] = _overdue_days(item)
        rows.append(item)
    return rows


# ---------------------------------------------------------------- Festschreibung & Storno

def finalize_checks(inv, settings):
    """Pflichtangaben nach § 14 Abs. 4 UStG (vereinfachte Prüfung, keine Rechtsberatung)."""
    problems = [f'Stammdaten: {m} fehlt' for m in settings_missing(settings)]
    if not inv['buyer_name']:
        problems.append('Name des Leistungsempfängers fehlt')
    if not (inv['buyer_street'] and inv['buyer_zip'] and inv['buyer_city']):
        problems.append('Vollständige Anschrift des Leistungsempfängers fehlt')
    if not inv['service_from']:
        problems.append('Leistungsdatum bzw. Beginn des Leistungszeitraums fehlt')
    if inv['tax_mode'] == 'reverse_charge':
        if not inv['buyer_vat_id']:
            problems.append('Reverse Charge: USt-IdNr. des Kunden fehlt')
        if not settings.get('vat_id'):
            problems.append('Reverse Charge: eigene USt-IdNr. fehlt in den Stammdaten')
        if inv['buyer_country'] == 'DE':
            problems.append('Reverse Charge ist hier nur für Kunden mit Sitz im EU-Ausland vorgesehen')
    if inv['issue_date'] and inv['issue_date'] > today().isoformat():
        problems.append('Rechnungsdatum liegt in der Zukunft')
    return problems


def _next_number(conn, prefix, year):
    conn.execute('INSERT OR IGNORE INTO number_sequences(prefix,year,last) VALUES (?,?,0)', (prefix, year))
    conn.execute('UPDATE number_sequences SET last=last+1 WHERE prefix=? AND year=?', (prefix, year))
    seq = conn.execute('SELECT last FROM number_sequences WHERE prefix=? AND year=?', (prefix, year)).fetchone()[0]
    return f'{prefix}-{year}-{seq:04d}'


def _seller_snapshot(settings):
    keys = list(SETTINGS_FIELDS) + ['small_business']
    return {k: settings[k] for k in keys}


def finalize_invoice(conn, invoice_id, commit=True):
    row = dict(_invoice_row(conn, invoice_id))
    if row['status'] != 'entwurf':
        raise ValueError('Rechnung ist bereits festgeschrieben.')
    settings = get_settings(conn)
    if not row['issue_date']:
        row['issue_date'] = today().isoformat()
    problems = finalize_checks(row, settings)
    if problems:
        raise ValueError('Pflichtangaben fehlen: ' + '; '.join(problems))
    prefix = settings['invoice_prefix'] or 'RE'
    year = int(row['issue_date'][:4])
    last_date = conn.execute("SELECT MAX(issue_date) FROM invoices WHERE status<>'entwurf' AND number LIKE ?",
                             (f'{prefix}-{year}-%',)).fetchone()[0]
    if last_date and row['issue_date'] < last_date:
        raise ValueError(f'Rechnungsdatum liegt vor der letzten festgeschriebenen Rechnung ({last_date}). Nummern und Daten müssen chronologisch bleiben.')
    number = _next_number(conn, prefix, year)
    due = (dt.date.fromisoformat(row['issue_date']) + dt.timedelta(days=row['payment_days'])).isoformat()
    service_to = row['service_to'] or ''
    conn.execute('''UPDATE invoices SET number=?, issue_date=?, due_date=?, service_to=?, seller_json=?,
                    finalized_at=datetime('now') WHERE id=? AND status='entwurf' ''',
                 (number, row['issue_date'], due, service_to, json.dumps(_seller_snapshot(settings), ensure_ascii=False), invoice_id))
    conn.execute("UPDATE invoices SET status='offen' WHERE id=?", (invoice_id,))
    audit(conn, 'invoice', invoice_id, 'festgeschrieben', f"{number} · {eur(row['gross_cents'])} EUR brutto")
    if commit:
        conn.commit()
    return invoice_detail(conn, invoice_id)


def cancel_invoice(conn, invoice_id, reason=''):
    row = dict(_invoice_row(conn, invoice_id))
    if row['status'] not in ('offen',):
        if row['status'] == 'entwurf':
            raise ValueError('Entwürfe werden gelöscht, nicht storniert.')
        if row['status'] == 'storniert':
            raise ValueError('Rechnung ist bereits storniert.')
        raise ValueError('Rechnung hat Zahlungseingänge. Zuerst Zahlung zurücknehmen bzw. Erstattung klären.')
    if row['kind'] == 'storno':
        raise ValueError('Eine Stornorechnung kann nicht erneut storniert werden.')
    reason = (reason or '').strip()[:300]
    settings = get_settings(conn)
    lines = [dict(r) for r in conn.execute('SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY position', (invoice_id,))]
    storno_lines = [{'position': l['position'], 'description': 'Storno: ' + l['description'], 'quantity': l['quantity'],
                     'unit': l['unit'], 'unit_price_cents': -l['unit_price_cents'], 'vat_rate': l['vat_rate'],
                     'net_cents': -l['net_cents']} for l in lines]
    totals = compute_totals(storno_lines, row['tax_mode'])
    issue = max(today().isoformat(), row['issue_date'])
    cols = {k: row[k] for k in ('lead_id', 'proposal_id', 'tax_mode', 'service_from', 'service_to', 'buyer_name', 'buyer_contact',
                                'buyer_street', 'buyer_zip', 'buyer_city', 'buyer_country', 'buyer_vat_id', 'buyer_reference', 'buyer_email')}
    cols.update({'kind': 'storno', 'corrects_invoice_id': invoice_id, 'issue_date': issue, 'payment_days': 0,
                 'intro_text': f"Stornorechnung zu Rechnung {row['number']} vom {row['issue_date']}." + (f' Grund: {reason}' if reason else ''),
                 'closing_text': '', 'net_cents': totals['net_cents'], 'vat_cents': totals['vat_cents'], 'gross_cents': totals['gross_cents']})
    cur = conn.execute(f"INSERT INTO invoices ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(cols.values()))
    storno_id = cur.lastrowid
    _store_lines(conn, storno_id, storno_lines)
    prefix = settings['invoice_prefix'] or 'RE'
    number = _next_number(conn, prefix, int(issue[:4]))
    conn.execute("UPDATE invoices SET number=?, due_date=?, seller_json=?, finalized_at=datetime('now') WHERE id=?",
                 (number, issue, json.dumps(_seller_snapshot(settings), ensure_ascii=False), storno_id))
    conn.execute("UPDATE invoices SET status='bezahlt' WHERE id=?", (storno_id,))
    conn.execute("UPDATE invoices SET status='storniert', cancelled_at=datetime('now') WHERE id=?", (invoice_id,))
    audit(conn, 'invoice', invoice_id, 'storniert', f"durch {number}" + (f' – {reason}' if reason else ''))
    audit(conn, 'invoice', storno_id, 'storno_festgeschrieben', f"{number} korrigiert {row['number']}")
    conn.commit()
    return invoice_detail(conn, storno_id)


def duplicate_invoice(conn, invoice_id):
    """Kopie als neuer Entwurf, z. B. für monatlich wiederkehrende Leistungen."""
    row = dict(_invoice_row(conn, invoice_id))
    if row['kind'] == 'storno':
        raise ValueError('Stornorechnungen können nicht dupliziert werden.')
    lines = [{'description': l['description'], 'quantity': l['quantity'], 'unit': l['unit'],
              'unit_price_cents': l['unit_price_cents'], 'vat_rate': l['vat_rate']}
             for l in conn.execute('SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY position', (invoice_id,))]
    data = {k: row[k] for k in ('lead_id', 'tax_mode', 'payment_days', 'buyer_name', 'buyer_contact', 'buyer_street', 'buyer_zip',
                                'buyer_city', 'buyer_country', 'buyer_vat_id', 'buyer_reference', 'buyer_email', 'intro_text', 'closing_text')}
    data.update({'kind': 'rechnung', 'issue_date': '', 'service_from': '', 'service_to': '', 'lines': lines})
    settings = get_settings(conn)
    data['tax_mode'] = 'kleinunternehmer' if settings['small_business'] else (row['tax_mode'] if row['tax_mode'] != 'kleinunternehmer' else 'regel')
    return create_invoice(conn, data, proposal_id=row['proposal_id'])


# ---------------------------------------------------------------- Angebot → Rechnung

def invoice_from_proposal(conn, data):
    if not isinstance(data, dict) or set(data) - {'proposal_id', 'mode', 'percent'}:
        raise ValueError('Ungültige Angaben.')
    pid = _int_id(data.get('proposal_id'), 'Angebots-ID')
    prop = conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()
    if not prop:
        raise LookupError('Angebot nicht gefunden.')
    if prop['status'] != 'angenommen':
        raise ValueError('Rechnung erst nach dokumentierter Annahme des Angebots erstellen.')
    customer = json.loads(prop['customer_json'])
    settings = get_settings(conn)
    if customer.get('tax_mode') == 'offen':
        raise ValueError('Steuerstatus im Angebot ist offen.')
    tax_mode = 'kleinunternehmer' if settings['small_business'] else 'regel'
    if customer.get('tax_mode') == 'kleinunternehmer' and not settings['small_business']:
        raise ValueError('Angebot wurde nach § 19 UStG erstellt, Stammdaten sehen Regelbesteuerung vor – bitte klären.')
    mode = data.get('mode', 'voll')
    if mode not in ('voll', 'abschlag', 'schluss'):
        raise ValueError('Modus: voll, abschlag oder schluss.')
    net_total = cents(customer['net_eur'], 'Angebotspreis')
    title = customer.get('project_label') or customer.get('package_title') or 'Leistung laut Angebot'
    ref = customer.get('offer_number') or f'#{pid}'
    monthly = customer.get('billing') == 'monatlich'
    lines = []
    kind = 'rechnung'
    if mode == 'voll':
        lines.append({'description': f"{title} – Festpreis gemäß Angebot {ref}" + (' (Monatspauschale)' if monthly else ''),
                      'quantity': 1, 'unit': 'monat' if monthly else 'pauschal', 'unit_price_cents': net_total, 'vat_rate': 19})
    elif mode == 'abschlag':
        if monthly:
            raise ValueError('Für monatliche Leistungen keine Abschlagsrechnung – Monatsrechnung verwenden.')
        pct = data.get('percent', 40)
        if isinstance(pct, bool) or type(pct) not in (int, float) or not 1 <= pct <= 99:
            raise ValueError('Abschlag in Prozent: 1–99.')
        amount = int((Decimal(net_total) * Decimal(str(pct)) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        kind = 'abschlag'
        lines.append({'description': f"Abschlag {pct:g} % auf {title} gemäß Angebot {ref} (Gesamtfestpreis {eur(net_total)} EUR netto)",
                      'quantity': 1, 'unit': 'pauschal', 'unit_price_cents': amount, 'vat_rate': 19})
    else:
        kind = 'schluss'
        lines.append({'description': f"{title} – Gesamtfestpreis gemäß Angebot {ref}", 'quantity': 1, 'unit': 'pauschal',
                      'unit_price_cents': net_total, 'vat_rate': 19})
        for prev in conn.execute("""SELECT * FROM invoices WHERE proposal_id=? AND kind='abschlag'
                                    AND status IN ('offen','teilbezahlt','bezahlt') ORDER BY issue_date, id""", (pid,)):
            lines.append({'description': f"abzüglich Abschlagsrechnung {prev['number']} vom {prev['issue_date']}",
                          'quantity': 1, 'unit': 'pauschal', 'unit_price_cents': -prev['net_cents'], 'vat_rate': 19})
    defaults = buyer_defaults(conn, prop['lead_id'])
    payload = {**defaults, 'lead_id': prop['lead_id'], 'kind': kind, 'tax_mode': tax_mode, 'lines': lines,
               'intro_text': f"Vielen Dank für Ihren Auftrag. Wir berechnen Ihnen die Leistungen gemäß Angebot {ref}."}
    return create_invoice(conn, payload, proposal_id=pid)


def buyer_defaults(conn, lead_id):
    """Rechnungsempfänger aus der letzten Rechnung an diesen Lead, sonst Firmenname des Leads."""
    if lead_id in (None, ''):
        return {}
    lead_id = _int_id(lead_id, 'Lead-ID')
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    last = conn.execute('SELECT * FROM invoices WHERE lead_id=? AND kind<>\'storno\' ORDER BY id DESC LIMIT 1', (lead_id,)).fetchone()
    keys = ('buyer_name', 'buyer_contact', 'buyer_street', 'buyer_zip', 'buyer_city', 'buyer_country',
            'buyer_vat_id', 'buyer_reference', 'buyer_email')
    if last:
        return {k: last[k] for k in keys}
    keys_of = lambda k: lead[k] if k in lead.keys() and lead[k] else ''
    return {'buyer_name': keys_of('legal_name') or lead['company'], 'buyer_contact': lead['contact_name'] or '',
            'buyer_street': keys_of('street'), 'buyer_zip': keys_of('zip'),
            'buyer_city': keys_of('city') or (lead['location'] or ''), 'buyer_country': 'DE', 'buyer_vat_id': keys_of('vat_id'),
            'buyer_email': ''}


# ---------------------------------------------------------------- Zahlungen & Mahnwesen

def _refresh_payment_status(conn, invoice_id):
    row = _invoice_row(conn, invoice_id)
    if row['status'] in ('entwurf', 'storniert') or row['kind'] == 'storno':
        return
    paid = paid_cents(conn, invoice_id)
    status = 'offen' if paid <= 0 else ('bezahlt' if paid >= row['gross_cents'] else 'teilbezahlt')
    conn.execute('UPDATE invoices SET status=? WHERE id=?', (status, invoice_id))


def add_payment(conn, invoice_id, data):
    if not isinstance(data, dict) or set(data) - {'paid_on', 'amount_eur', 'method', 'note'}:
        raise ValueError('Ungültige Zahlungsdaten.')
    row = _invoice_row(conn, invoice_id)
    if row['status'] not in ('offen', 'teilbezahlt'):
        raise ValueError('Zahlungen nur für offene, festgeschriebene Rechnungen.')
    outstanding = row['gross_cents'] - paid_cents(conn, invoice_id)
    amount = cents(data.get('amount_eur', eur_dot(outstanding)), 'Zahlbetrag', 0, 100_000_000)
    if amount <= 0:
        raise ValueError('Zahlbetrag muss größer als 0 sein.')
    if amount > outstanding:
        raise ValueError(f'Zahlbetrag übersteigt den offenen Betrag ({eur(outstanding)} EUR). Überzahlungen bitte separat klären.')
    paid_on = _date(data.get('paid_on') or today().isoformat(), 'Zahlungsdatum', required=True)
    if paid_on > today().isoformat():
        raise ValueError('Zahlungsdatum liegt in der Zukunft.')
    if paid_on < row['issue_date']:
        raise ValueError('Zahlung vor Rechnungsdatum: bitte als Anzahlung separat prüfen.')
    method = data.get('method', 'ueberweisung')
    if method not in PAYMENT_METHODS:
        raise ValueError('Zahlungsart ungültig.')
    note = _text(data, 'note', 300)
    cur = conn.execute('INSERT INTO payments(invoice_id,paid_on,amount_cents,method,note) VALUES (?,?,?,?,?)',
                       (invoice_id, paid_on, amount, method, note))
    _refresh_payment_status(conn, invoice_id)
    audit(conn, 'payment', cur.lastrowid, 'erfasst', f"{row['number']}: {eur(amount)} EUR am {paid_on}")
    conn.commit()
    return invoice_detail(conn, invoice_id)


def delete_payment(conn, payment_id):
    pay = conn.execute('SELECT * FROM payments WHERE id=?', (payment_id,)).fetchone()
    if not pay:
        raise LookupError('Zahlung nicht gefunden.')
    inv = _invoice_row(conn, pay['invoice_id'])
    conn.execute('DELETE FROM payments WHERE id=?', (payment_id,))
    _refresh_payment_status(conn, pay['invoice_id'])
    audit(conn, 'payment', payment_id, 'zurueckgenommen', f"{inv['number']}: {eur(pay['amount_cents'])} EUR vom {pay['paid_on']}")
    conn.commit()
    return invoice_detail(conn, pay['invoice_id'])


def default_interest_cents(outstanding, base_rate_pct, days, b2b=True):
    """Verzugszinsen § 288 BGB: B2B Basiszins + 9 Prozentpunkte, Verbraucher + 5."""
    rate = Decimal(str(base_rate_pct)) + (9 if b2b else 5)
    if days <= 0 or rate <= 0 or outstanding <= 0:
        return 0
    return int((Decimal(outstanding) * rate / 100 * Decimal(days) / 365).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def create_dunning(conn, invoice_id, data):
    if not isinstance(data, dict) or set(data) - {'level', 'include_interest', 'include_fee', 'days'}:
        raise ValueError('Ungültige Mahndaten.')
    inv = invoice_detail(conn, invoice_id)
    if inv['status'] not in ('offen', 'teilbezahlt'):
        raise ValueError('Nur offene Rechnungen können gemahnt werden.')
    if inv['overdue_days'] <= 0:
        raise ValueError('Rechnung ist noch nicht fällig.')
    level = data.get('level', (max([d['level'] for d in inv['dunning']] or [0]) + 1))
    if level not in DUNNING_LEVELS:
        raise ValueError('Mahnstufe 1–3.')
    days = data.get('days', 10)
    if isinstance(days, bool) or type(days) is not int or not 3 <= days <= 30:
        raise ValueError('Neue Frist: 3–30 Tage.')
    settings = get_settings(conn)
    b2b = True  # SignalDesk richtet sich an Geschäftskunden
    interest = default_interest_cents(inv['outstanding_cents'], settings['base_rate_pct'], inv['overdue_days'], b2b) if data.get('include_interest') else 0
    fee = 4000 if data.get('include_fee') and b2b else 0  # Verzugspauschale § 288 Abs. 5 BGB
    new_due = (today() + dt.timedelta(days=days)).isoformat()
    total = inv['outstanding_cents'] + interest + fee
    title = DUNNING_LEVELS[level]
    seller = settings['company_name'] or '[Firma]'
    greeting = f"Sehr geehrte Damen und Herren," if not inv['buyer_contact'] else f"Guten Tag {inv['buyer_contact']},"
    body = {
        1: f"sicher ist es Ihrer Aufmerksamkeit entgangen: Unsere Rechnung {inv['number']} vom {_de(inv['issue_date'])} "
           f"über {eur(inv['gross_cents'])} EUR war am {_de(inv['due_date'])} fällig. Offen sind noch {eur(inv['outstanding_cents'])} EUR.",
        2: f"trotz Fälligkeit am {_de(inv['due_date'])} konnten wir zu unserer Rechnung {inv['number']} vom {_de(inv['issue_date'])} "
           f"noch keinen vollständigen Zahlungseingang feststellen. Offen sind {eur(inv['outstanding_cents'])} EUR.",
        3: f"unsere Rechnung {inv['number']} vom {_de(inv['issue_date'])} ist seit {inv['overdue_days']} Tagen überfällig. "
           f"Wir bitten Sie letztmalig um Ausgleich des offenen Betrags von {eur(inv['outstanding_cents'])} EUR.",
    }[level]
    extra = []
    if interest:
        extra.append(f"Verzugszinsen gemäß § 288 Abs. 2 BGB ({settings['base_rate_pct']} % Basiszins + 9 Prozentpunkte, {inv['overdue_days']} Tage): {eur(interest)} EUR")
    if fee:
        extra.append(f"Verzugspauschale gemäß § 288 Abs. 5 BGB: {eur(fee)} EUR")
    text = '\n'.join([f'{title} zu Rechnung {inv["number"]}', '', greeting, '', body, ''] +
                     ([*extra, f'Gesamtforderung: {eur(total)} EUR', ''] if extra else []) +
                     [f"Bitte überweisen Sie den Betrag bis zum {_de(new_due)} auf das Konto {settings['iban'] or '[IBAN]'} "
                      f"unter Angabe der Rechnungsnummer {inv['number']}.",
                      'Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben, betrachten Sie es bitte als gegenstandslos.',
                      '', 'Freundliche Grüße', seller])
    cur = conn.execute('INSERT INTO dunning_notices(invoice_id,level,created_on,new_due_date,outstanding_cents,interest_cents,fee_cents,text) VALUES (?,?,?,?,?,?,?,?)',
                       (invoice_id, level, today().isoformat(), new_due, inv['outstanding_cents'], interest, fee, text))
    audit(conn, 'dunning', cur.lastrowid, 'erstellt', f"{inv['number']}: {title}, {eur(total)} EUR")
    if inv['lead_id']:
        conn.execute('INSERT INTO tasks(lead_id,title,due_date) VALUES (?,?,?)',
                     (inv['lead_id'], f"Zahlungseingang prüfen: {inv['number']} ({title})", new_due))
    conn.commit()
    return {'id': cur.lastrowid, 'level': level, 'title': title, 'text': text, 'interest_cents': interest,
            'fee_cents': fee, 'total_cents': total, 'new_due_date': new_due,
            'notice': 'Nur Entwurf – nichts wurde versendet. Zinsen/Pauschale nur bei tatsächlichem Verzug und Geschäftskunden.'}


def _de(iso):
    return dt.date.fromisoformat(iso).strftime('%d.%m.%Y') if iso else ''


# ---------------------------------------------------------------- Ausgaben

def create_expense(conn, data, source='manuell'):
    allowed = {'expense_date', 'paid_on', 'supplier', 'description', 'category', 'gross_eur', 'net_eur',
               'vat_rate', 'vat_eur', 'reverse_charge', 'receipt_ref', 'note', 'document_id'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Ungültige Ausgabefelder.')
    document_id = data.get('document_id')
    if document_id not in (None, ''):
        document_id = _int_id(document_id, 'Dokument-ID')
        if not conn.execute('SELECT id FROM einvoice_documents WHERE id=?', (document_id,)).fetchone():
            raise ValueError('E-Rechnungs-Dokument nicht gefunden.')
        if conn.execute("SELECT id FROM expenses WHERE document_id=? AND status='aktiv'", (document_id,)).fetchone():
            raise ValueError('Diese E-Rechnung ist bereits als Ausgabe erfasst.')
        source = 'e-rechnung'
    else:
        document_id = None
    expense_date = _date(data.get('expense_date'), 'Belegdatum', required=True)
    paid_on = _date(data.get('paid_on'), 'Bezahlt am')
    supplier = _text(data, 'supplier', 200, required=True)
    category = data.get('category', 'sonstiges')
    if category not in EXPENSE_CATEGORIES:
        raise ValueError('Unbekannte Kategorie.')
    rate = data.get('vat_rate', 19)
    if isinstance(rate, bool) or rate not in VAT_RATES:
        raise ValueError('Steuersatz 0, 7 oder 19 %.')
    rc = data.get('reverse_charge', False)
    if not isinstance(rc, bool):
        raise ValueError('reverse_charge: true/false.')
    if rc:
        # § 13b: Rechnung ohne USt; Steuer schuldet der Leistungsempfänger.
        net = cents(data.get('net_eur', data.get('gross_eur')), 'Nettobetrag', 0, 10_000_000)
        rate = 19 if rate == 0 else rate
        vat = 0
        gross = net
    elif data.get('net_eur') not in (None, '') and data.get('gross_eur') in (None, ''):
        net = cents(data.get('net_eur'), 'Nettobetrag', 0, 10_000_000)
        vat = cents(data['vat_eur'], 'USt-Betrag', 0, 10_000_000) if data.get('vat_eur') not in (None, '') else \
            int((Decimal(net) * rate / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        gross = net + vat
    else:
        gross = cents(data.get('gross_eur'), 'Bruttobetrag', 0, 10_000_000)
        if data.get('vat_eur') not in (None, ''):
            vat = cents(data['vat_eur'], 'USt-Betrag', 0, 10_000_000)
        else:
            vat = gross - int((Decimal(gross) * 100 / (100 + rate)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        net = gross - vat
    if gross <= 0 or vat > gross:
        raise ValueError('Beträge prüfen: Brutto muss größer 0 und größer als die USt sein.')
    cols = {'expense_date': expense_date, 'paid_on': paid_on, 'supplier': supplier,
            'description': _text(data, 'description', 500), 'category': category, 'net_cents': net,
            'vat_rate': rate, 'vat_cents': vat, 'gross_cents': gross, 'reverse_charge': int(rc),
            'receipt_ref': _text(data, 'receipt_ref', 200), 'note': _text(data, 'note', 1000), 'source': source,
            'document_id': document_id}
    cur = conn.execute(f"INSERT INTO expenses ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(cols.values()))
    audit(conn, 'expense', cur.lastrowid, 'erfasst', f"{supplier}: {eur(gross)} EUR ({source})")
    conn.commit()
    return expense_detail(conn, cur.lastrowid)


def expense_detail(conn, expense_id):
    row = conn.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
    if not row:
        raise LookupError('Ausgabe nicht gefunden.')
    item = dict(row)
    item['category_label'], item['account_skr03'] = EXPENSE_CATEGORIES.get(item['category'], ('?', ''))
    item['warnings'] = []
    if item['category'] == 'hardware_gwg' and item['net_cents'] > 80000:
        item['warnings'].append('Über 800 € netto: keine GWG-Sofortabschreibung, ggf. AfA (für Computerhardware gilt häufig 1 Jahr Nutzungsdauer) – mit Steuerberatung klären.')
    if not item['paid_on']:
        item['warnings'].append('Zahlungsdatum fehlt: bei Ist-Versteuerung/EÜR zählt der Abfluss.')
    if not item['receipt_ref']:
        item['warnings'].append('Belegverweis fehlt (Belegnummer/Dateiname) – ohne Beleg keine Buchung.')
    return item


def expense_rows(conn, include_cancelled=False):
    sql = 'SELECT id FROM expenses' + ('' if include_cancelled else " WHERE status='aktiv'") + ' ORDER BY expense_date DESC, id DESC LIMIT 500'
    return [expense_detail(conn, r['id']) for r in conn.execute(sql)]


def set_expense_paid(conn, expense_id, paid_on):
    row = conn.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
    if not row:
        raise LookupError('Ausgabe nicht gefunden.')
    paid_on = _date(paid_on, 'Bezahlt am', required=True)
    if row['paid_on']:
        raise ValueError('Zahlungsdatum ist bereits erfasst. Für Korrekturen die Ausgabe stornieren und neu erfassen.')
    conn.execute('UPDATE expenses SET paid_on=? WHERE id=?', (paid_on, expense_id))
    audit(conn, 'expense', expense_id, 'bezahlt', paid_on)
    conn.commit()
    return expense_detail(conn, expense_id)


def cancel_expense(conn, expense_id, reason=''):
    row = conn.execute('SELECT * FROM expenses WHERE id=?', (expense_id,)).fetchone()
    if not row:
        raise LookupError('Ausgabe nicht gefunden.')
    if row['status'] != 'aktiv':
        raise ValueError('Ausgabe ist bereits storniert.')
    conn.execute("UPDATE expenses SET status='storniert' WHERE id=?", (expense_id,))
    audit(conn, 'expense', expense_id, 'storniert', (reason or '')[:300])
    conn.commit()
    return {'cancelled': True}


# ---------------------------------------------------------------- Auswertungen

def _period(params):
    year = today().year
    start = params.get('from') or f'{year}-01-01'
    end = params.get('to') or f'{year}-12-31'
    _date(start, 'Von', True)
    _date(end, 'Bis', True)
    if end < start:
        raise ValueError('Zeitraum: Ende vor Beginn.')
    return start, end


def _invoice_rate_groups(conn, invoice_id, tax_mode):
    lines = [dict(r) for r in conn.execute('SELECT net_cents, vat_rate FROM invoice_lines WHERE invoice_id=?', (invoice_id,))]
    return compute_totals(lines, tax_mode)['breakdown']


def tax_report(conn, params):
    """Vorbereitung UStVA und vereinfachte EÜR für einen Zeitraum. Keine Steuerberatung."""
    start, end = _period(params)
    settings = get_settings(conn)
    basis = params.get('basis') or settings['tax_basis']
    if basis not in ('ist', 'soll'):
        raise ValueError('Basis: ist oder soll.')
    small = settings['small_business']
    kz = {'81': 0, '81_tax': 0, '86': 0, '86_tax': 0, '21': 0, '46': 0, '47': 0, '66': 0, '67': 0, 'steuerfrei_0': 0}
    revenue_net = revenue_vat = 0

    def add_sales(tax_mode, groups, factor=Decimal(1)):
        nonlocal revenue_net, revenue_vat
        for g in groups:
            net = int((Decimal(g['net_cents']) * factor).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            vat = int((Decimal(g['vat_cents']) * factor).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            revenue_net += net
            revenue_vat += vat
            if tax_mode == 'reverse_charge':
                kz['21'] += net
            elif tax_mode == 'regel' and g['rate'] == 19:
                kz['81'] += net
                kz['81_tax'] += vat
            elif tax_mode == 'regel' and g['rate'] == 7:
                kz['86'] += net
                kz['86_tax'] += vat
            elif tax_mode == 'regel':
                kz['steuerfrei_0'] += net

    if basis == 'soll':
        for inv in conn.execute("""SELECT * FROM invoices WHERE status<>'entwurf' AND issue_date BETWEEN ? AND ?""", (start, end)):
            add_sales(inv['tax_mode'], _invoice_rate_groups(conn, inv['id'], inv['tax_mode']))
    else:
        for pay in conn.execute("""SELECT p.amount_cents, i.id, i.tax_mode, i.gross_cents FROM payments p JOIN invoices i ON i.id=p.invoice_id
                                   WHERE p.paid_on BETWEEN ? AND ?""", (start, end)):
            if pay['gross_cents'] > 0:
                add_sales(pay['tax_mode'], _invoice_rate_groups(conn, pay['id'], pay['tax_mode']),
                          Decimal(pay['amount_cents']) / Decimal(pay['gross_cents']))
        # Reverse-Charge-Umsätze (Kz 21) sind unabhängig vom Zahlungseingang im Leistungszeitraum zu melden.
        kz['21'] = 0
        for inv in conn.execute("""SELECT * FROM invoices WHERE status<>'entwurf' AND tax_mode='reverse_charge' AND issue_date BETWEEN ? AND ?""", (start, end)):
            kz['21'] += inv['net_cents']

    date_col = 'paid_on' if basis == 'ist' else 'expense_date'
    expenses = [dict(r) for r in conn.execute(f"""SELECT * FROM expenses WHERE status='aktiv' AND {date_col}<>'' AND {date_col} BETWEEN ? AND ?""", (start, end))]
    exp_net = exp_vat = 0
    by_category = {}
    for e in expenses:
        if e['reverse_charge']:
            tax = int((Decimal(e['net_cents']) * e['vat_rate'] / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            kz['46'] += e['net_cents']
            kz['47'] += tax
            if not small:
                kz['67'] += tax
            cost = e['net_cents'] + (tax if small else 0)
        else:
            if not small:
                kz['66'] += e['vat_cents']
                exp_vat += e['vat_cents']
            cost = e['net_cents'] if not small else e['gross_cents']
        exp_net += cost
        label = EXPENSE_CATEGORIES.get(e['category'], ('Sonstiges', ''))[0]
        by_category[label] = by_category.get(label, 0) + cost

    if small:
        output_tax = kz['47']
        input_tax = 0
    else:
        output_tax = kz['81_tax'] + kz['86_tax'] + kz['47']
        input_tax = kz['66'] + kz['67']
    whole = lambda c: int(Decimal(c) / 100)  # Bemessungsgrundlagen in vollen Euro (abgerundet)
    ustva = [
        {'kz': '81', 'label': 'Steuerpflichtige Umsätze 19 % (Bemessungsgrundlage, volle €)', 'value_eur': whole(kz['81']), 'tax_cents': kz['81_tax']},
        {'kz': '86', 'label': 'Steuerpflichtige Umsätze 7 % (Bemessungsgrundlage, volle €)', 'value_eur': whole(kz['86']), 'tax_cents': kz['86_tax']},
        {'kz': '21', 'label': 'Nicht steuerbare sonstige Leistungen EU (§ 18b UStG) – auch ZM melden', 'value_eur': whole(kz['21']), 'tax_cents': 0},
        {'kz': '46', 'label': 'Bezogene sonstige Leistungen EU-Unternehmer (§ 13b Abs. 1 UStG)', 'value_eur': whole(kz['46']), 'tax_cents': kz['47']},
        {'kz': '66', 'label': 'Vorsteuer aus Rechnungen anderer Unternehmer', 'value_eur': None, 'tax_cents': kz['66']},
        {'kz': '67', 'label': 'Vorsteuer aus Leistungen nach § 13b UStG', 'value_eur': None, 'tax_cents': kz['67']},
    ]
    hints = []
    if small:
        hints.append('§ 19 UStG aktiv: keine USt auf Ausgangsrechnungen, kein Vorsteuerabzug. § 13b-Leistungen (z. B. Werbeplattformen/SaaS aus dem EU-Ausland) bleiben trotzdem steuerpflichtig.')
    if kz['21']:
        hints.append('EU-Reverse-Charge-Umsätze zusätzlich in der Zusammenfassenden Meldung (ZM) beim BZSt melden.')
    if kz['steuerfrei_0']:
        hints.append(f"Umsätze mit 0 % ohne Reverse Charge: {eur(kz['steuerfrei_0'])} EUR – Steuerbefreiung prüfen und korrekt zuordnen.")
    hints.append('Vorbereitung, keine Steuererklärung: Werte in ELSTER bzw. mit Steuerberatung prüfen und übermitteln.')

    income_for_euer = revenue_net
    return {
        'period': {'from': start, 'to': end, 'basis': basis},
        'small_business': small,
        'ustva': ustva,
        'output_tax_cents': output_tax, 'input_tax_cents': input_tax,
        'payable_cents': output_tax - input_tax,
        'euer': {
            'income_net_cents': income_for_euer, 'income_vat_cents': revenue_vat,
            'expenses_cents': exp_net, 'input_vat_cents': exp_vat,
            'profit_cents': income_for_euer - exp_net,
            'by_category': [{'label': k, 'cents': v} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
            'note': ('Vereinfachte Netto-Sicht nach Zufluss/Abfluss. Die Anlage EÜR erfasst vereinnahmte USt und erstattete '
                     'Vorsteuer zusätzlich als Einnahme, gezahlte USt/Vorsteuer als Ausgabe; AfA und Privatanteile fehlen hier.'),
        },
        'hints': hints,
    }


def overview(conn):
    t = today()
    year_start = f'{t.year}-01-01'
    rows = invoice_rows(conn)
    open_rows = [r for r in rows if r['status'] in ('offen', 'teilbezahlt')]
    overdue = [r for r in open_rows if r['overdue_days'] > 0]
    paid_year = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE paid_on>=?', (year_start,)).fetchone()[0]
    invoiced_year = conn.execute("SELECT COALESCE(SUM(net_cents),0) FROM invoices WHERE status<>'entwurf' AND issue_date>=?", (year_start,)).fetchone()[0]
    expenses_year = conn.execute("SELECT COALESCE(SUM(gross_cents),0) FROM expenses WHERE status='aktiv' AND expense_date>=?", (year_start,)).fetchone()[0]
    quarter = (t.month - 1) // 3
    q_start = dt.date(t.year, quarter * 3 + 1, 1)
    q_end = (dt.date(t.year + (quarter == 3), (quarter * 3 + 3) % 12 + 1, 1) - dt.timedelta(days=1))
    q_report = tax_report(conn, {'from': q_start.isoformat(), 'to': q_end.isoformat()})
    months = []
    for i in range(11, -1, -1):
        y, m = t.year, t.month - i
        while m <= 0:
            y, m = y - 1, m + 12
        prefix = f'{y}-{m:02d}'
        inv = conn.execute("SELECT COALESCE(SUM(net_cents),0) FROM invoices WHERE status<>'entwurf' AND substr(issue_date,1,7)=?", (prefix,)).fetchone()[0]
        paid = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE substr(paid_on,1,7)=?', (prefix,)).fetchone()[0]
        months.append({'month': prefix, 'invoiced_net_cents': inv, 'paid_cents': paid})
    settings = get_settings(conn)
    warnings = []
    if settings['missing']:
        warnings.append('Stammdaten unvollständig: ' + ', '.join(settings['missing']) + '. Ohne diese Angaben keine Festschreibung.')
    if settings['small_business']:
        prev_year = conn.execute("SELECT COALESCE(SUM(net_cents),0) FROM invoices WHERE status<>'entwurf' AND substr(issue_date,1,4)=?", (str(t.year - 1),)).fetchone()[0]
        if invoiced_year > 10_000_000:
            warnings.append('Kleinunternehmer: Umsatz im laufenden Jahr über 100.000 € – § 19 UStG entfällt ab dem überschreitenden Umsatz. Sofort Steuerberatung einbeziehen.')
        elif invoiced_year > 2_500_000 or prev_year > 2_500_000:
            warnings.append('Kleinunternehmer: 25.000-€-Grenze (Vorjahr) überschritten bzw. in Reichweite – Status für das Folgejahr prüfen.')
    drafts = sum(1 for r in rows if r['status'] == 'entwurf')
    return {
        'open_cents': sum(r['outstanding_cents'] for r in open_rows), 'open_count': len(open_rows),
        'overdue_cents': sum(r['outstanding_cents'] for r in overdue), 'overdue_count': len(overdue),
        'paid_year_cents': paid_year, 'invoiced_year_net_cents': invoiced_year, 'expenses_year_cents': expenses_year,
        'drafts': drafts, 'quarter': {'from': q_start.isoformat(), 'to': q_end.isoformat(), 'payable_cents': q_report['payable_cents']},
        'months': months, 'overdue': overdue[:20], 'warnings': warnings,
        'accepted_without_invoice': accepted_without_invoice(conn),
    }


def accepted_without_invoice(conn):
    return [{'id': r['id'], 'lead_id': r['lead_id'], 'company': r['company'], 'number': r['number'] or f"#{r['id']}",
             'project_label': json.loads(r['customer_json']).get('project_label', '')}
            for r in conn.execute("""SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id
                                     WHERE p.status='angenommen' AND NOT EXISTS
                                     (SELECT 1 FROM invoices i WHERE i.proposal_id=p.id AND i.kind<>'storno' AND i.status<>'storniert')
                                     ORDER BY p.id DESC LIMIT 20""")]


def sales_kpis(conn, params):
    """Vertriebskennzahlen: Angebotsquote, Auftragswert, Umsatz je Kontaktweg."""
    start, end = _period(params)
    props = [dict(r) for r in conn.execute("SELECT status, customer_json FROM proposals WHERE substr(created_at,1,10) BETWEEN ? AND ?", (start, end))]
    by_status = {}
    for p in props:
        by_status[p['status']] = by_status.get(p['status'], 0) + 1
    accepted = [json.loads(p['customer_json'])['net_eur'] for p in props if p['status'] == 'angenommen']
    decided = by_status.get('angenommen', 0) + by_status.get('abgelehnt', 0)
    by_route = {}
    for r in conn.execute("""SELECT l.contact_route, SUM(p.amount_cents) AS paid FROM payments p
                             JOIN invoices i ON i.id=p.invoice_id JOIN leads l ON l.id=i.lead_id
                             WHERE p.paid_on BETWEEN ? AND ? GROUP BY l.contact_route""", (start, end)):
        by_route[r['contact_route'] or 'unbekannt'] = r['paid']
    lost = conn.execute("SELECT COUNT(*) FROM leads WHERE stage='verloren' AND substr(updated_at,1,10) BETWEEN ? AND ?", (start, end)).fetchone()[0]
    won = conn.execute("SELECT COUNT(*) FROM leads WHERE stage='gewonnen' AND substr(updated_at,1,10) BETWEEN ? AND ?", (start, end)).fetchone()[0]
    return {
        'proposals_by_status': by_status, 'proposals_total': len(props),
        'acceptance_rate_pct': round(100 * by_status.get('angenommen', 0) / decided, 1) if decided else None,
        'avg_accepted_net_eur': round(sum(accepted) / len(accepted), 2) if accepted else None,
        'paid_by_contact_route_cents': by_route, 'leads_won': won, 'leads_lost': lost,
        'note': 'Kleine Fallzahlen sind nicht aussagekräftig. Gewonnen/Verloren nach letzter Lead-Änderung im Zeitraum.',
    }


def audit_rows(conn, limit=200):
    return [dict(r) for r in conn.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT ?', (min(int(limit), 1000),))]


# ---------------------------------------------------------------- CSV-Exporte

def _csv(rows, header):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';', lineterminator='\r\n', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for row in rows:
        writer.writerow(['' if v is None else _csv_safe(v) for v in row])
    return '﻿' + buf.getvalue()


def _csv_safe(value):
    """Schutz vor Formel-Injection beim Öffnen in Tabellenkalkulationen."""
    s = str(value)
    if s and s[0] in '=+-@\t\r' and not re.fullmatch(r'-?[\d.]+(,\d+)?', s):
        return "'" + s
    return s


def export_csv(conn, kind, params):
    start, end = _period(params)
    if kind == 'rechnungen':
        rows = conn.execute("""SELECT number, kind, status, issue_date, service_from, service_to, due_date, buyer_name, buyer_vat_id,
                               tax_mode, net_cents, vat_cents, gross_cents,
                               COALESCE((SELECT SUM(amount_cents) FROM payments p WHERE p.invoice_id=invoices.id),0) AS paid
                               FROM invoices WHERE status<>'entwurf' AND issue_date BETWEEN ? AND ? ORDER BY number""", (start, end)).fetchall()
        return _csv([(r['number'], r['kind'], r['status'], r['issue_date'], r['service_from'], r['service_to'], r['due_date'],
                      r['buyer_name'], r['buyer_vat_id'], r['tax_mode'], eur(r['net_cents']), eur(r['vat_cents']),
                      eur(r['gross_cents']), eur(r['paid'])) for r in rows],
                    ['Rechnungsnr', 'Art', 'Status', 'Rechnungsdatum', 'Leistung von', 'Leistung bis', 'Fällig', 'Kunde',
                     'USt-IdNr Kunde', 'Steuer', 'Netto', 'USt', 'Brutto', 'Bezahlt'])
    if kind == 'ausgaben':
        rows = conn.execute("""SELECT * FROM expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date, id""", (start, end)).fetchall()
        return _csv([(r['expense_date'], r['paid_on'], r['supplier'], r['description'], EXPENSE_CATEGORIES.get(r['category'], ('', ''))[0],
                      EXPENSE_CATEGORIES.get(r['category'], ('', ''))[1], eur(r['net_cents']), r['vat_rate'], eur(r['vat_cents']),
                      eur(r['gross_cents']), 'ja' if r['reverse_charge'] else 'nein', r['receipt_ref'], r['status']) for r in rows],
                    ['Belegdatum', 'Bezahlt am', 'Lieferant', 'Beschreibung', 'Kategorie', 'Konto SKR03 (Vorschlag)', 'Netto',
                     'USt-Satz', 'USt', 'Brutto', '§13b', 'Beleg', 'Status'])
    if kind == 'buchungen':
        return _csv(_booking_rows(conn, start, end),
                    ['Datum', 'Belegnr', 'Buchungstext', 'Umsatz (Brutto)', 'Soll/Haben', 'Konto', 'Gegenkonto', 'USt-Satz', 'Hinweis'])
    raise LookupError('Unbekannter Export.')


def _booking_rows(conn, start, end):
    """Vereinfachte Buchungsliste (SKR03-Vorschläge) als Übergabe an die Steuerberatung – kein DATEV-Format."""
    out = []
    for inv in conn.execute("SELECT * FROM invoices WHERE status<>'entwurf' AND issue_date BETWEEN ? AND ? ORDER BY issue_date, number", (start, end)):
        for g in _invoice_rate_groups(conn, inv['id'], inv['tax_mode']):
            account = (REVENUE_ACCOUNTS['reverse_charge'] if inv['tax_mode'] == 'reverse_charge' else
                       REVENUE_ACCOUNTS['kleinunternehmer'] if inv['tax_mode'] == 'kleinunternehmer' else
                       REVENUE_ACCOUNTS.get(f"regel_{g['rate']}", '8400'))
            out.append((inv['issue_date'], inv['number'], f"{'Storno ' if inv['kind'] == 'storno' else ''}Ausgangsrechnung {inv['buyer_name']}",
                        eur(g['net_cents'] + g['vat_cents']), 'S', '1400', account, g['rate'], 'Forderung an Erlöse (Sollversteuerung/Bilanz) – bei EÜR nur Zahlung buchen'))
    for pay in conn.execute("""SELECT p.*, i.number, i.buyer_name FROM payments p JOIN invoices i ON i.id=p.invoice_id
                               WHERE p.paid_on BETWEEN ? AND ? ORDER BY p.paid_on, p.id""", (start, end)):
        out.append((pay['paid_on'], pay['number'], f"Zahlungseingang {pay['buyer_name']}", eur(pay['amount_cents']), 'S', '1200', '1400', '', pay['method']))
    for e in conn.execute("""SELECT * FROM expenses WHERE status='aktiv' AND expense_date BETWEEN ? AND ? ORDER BY expense_date, id""", (start, end)):
        account = EXPENSE_CATEGORIES.get(e['category'], ('', '4900'))[1]
        out.append((e['paid_on'] or e['expense_date'], e['receipt_ref'] or f"A{e['id']}", f"{e['supplier']} {e['description']}".strip(),
                    eur(e['gross_cents']), 'S', account, '1200', e['vat_rate'], '§ 13b Reverse Charge' if e['reverse_charge'] else ''))
    return out
