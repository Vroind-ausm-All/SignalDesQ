"""DATEV-Buchungsstapel (EXTF, Format 700, Kategorie 21) als Übergabe an die Steuerberatung.

Erzeugt eine Datei im Aufbau, den DATEV Rechnungswesen beim Import „Buchungsstapel“ erwartet: Kopfzeile mit Berater- und
Mandantennummer, Spaltenzeile, eine Zeile je Buchung. Kontenrahmen SKR03, Sachkontenlänge 4, Beträge mit Komma, Zeichensatz
Windows-1252, Zeilenende CRLF.

Grenzen (ehrlich): Es sind nur die ersten 14 Spalten belegt (Umsatz bis Buchungstext). Ein Probeimport in DATEV ist nicht
erfolgt. Buchungen mit § 13b (Ausgaben im Reverse-Charge-Verfahren) werden ohne Steuerschlüssel übergeben und als
„prüfen“ gekennzeichnet, weil der richtige Schlüssel vom Einzelfall abhängt.
"""
from __future__ import annotations

import datetime as dt
import re

from .accounting import EXPENSE_CATEGORIES, REVENUE_ACCOUNTS, _invoice_rate_groups, _period
from .quality import get_setting, put_setting

SETTINGS_KEY = 'datev_v1'
DEFAULTS = {'berater_nr': '', 'mandant_nr': '', 'wj_beginn_monat': 1, 'debitor': '10000', 'bank': '1200', 'diktat': 'SD'}
COLUMNS = ['Umsatz (ohne Soll/Haben-Kz)', 'Soll/Haben-Kennzeichen', 'WKZ Umsatz', 'Kurs', 'Basis-Umsatz',
           'WKZ Basis-Umsatz', 'Konto', 'Gegenkonto (ohne BU-Schlüssel)', 'BU-Schlüssel', 'Belegdatum', 'Belegfeld 1',
           'Belegfeld 2', 'Skonto', 'Buchungstext']
# Vorsteuer-Schlüssel für Ausgaben im SKR03; Erlöskonten 8400/8300 sind Automatikkonten und brauchen keinen Schlüssel.
VORSTEUER_BU = {19: '9', 7: '8'}
NOTICE = ('DATEV-Buchungsstapel (EXTF 700) mit den Kernspalten, Kontenrahmen SKR03. Ein Probeimport in DATEV ist nicht '
          'erfolgt: Vor der ersten Übergabe mit der Steuerberatung einen Testimport vereinbaren. Buchungen mit „prüfen“ '
          'brauchen eine Entscheidung der Steuerberatung. Die Datei ist für den Import in DATEV gedacht, nicht zum Bearbeiten '
          'in Excel oder LibreOffice.')


def get_datev_settings(conn):
    s = {**DEFAULTS, **get_setting(conn, SETTINGS_KEY, {})}
    s['missing'] = [label for key, label in (('berater_nr', 'Beraternummer'), ('mandant_nr', 'Mandantennummer')) if not s[key]]
    return s


def save_datev_settings(conn, data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('Erwartet: ' + ', '.join(DEFAULTS) + '.')
    s = {k: v for k, v in get_datev_settings(conn).items() if k != 'missing'}
    for key in ('berater_nr', 'mandant_nr', 'debitor', 'bank', 'diktat'):
        if key in data:
            s[key] = str(data[key] or '').strip()
    checks = (('berater_nr', r'(|\d{4,7})', 'Beraternummer: 4 bis 7 Ziffern.'),
              ('mandant_nr', r'(|\d{1,5})', 'Mandantennummer: 1 bis 5 Ziffern.'),
              ('debitor', r'\d{5}', 'Sammeldebitor: fünfstellig (Sachkontenlänge 4), z. B. 10000.'),
              ('bank', r'\d{4}', 'Bankkonto: vierstellig, z. B. 1200.'),
              ('diktat', r'[A-Za-z0-9]{0,2}', 'Diktatkürzel: höchstens 2 Zeichen.'))
    for key, pattern, message in checks:
        if not re.fullmatch(pattern, s[key]):
            raise ValueError(message)
    if 'wj_beginn_monat' in data:
        month = data['wj_beginn_monat']
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError('Beginn des Wirtschaftsjahrs: Monat 1 bis 12.')
        s['wj_beginn_monat'] = month
    put_setting(conn, SETTINGS_KEY, s)
    conn.commit()
    return get_datev_settings(conn)


def _fiscal_start(day, month):
    year = day.year if day.month >= month else day.year - 1
    return dt.date(year, month, 1)


def _amount(cents):
    return f'{abs(cents) // 100},{abs(cents) % 100:02d}'


# SDQ-042 (Prüfbericht F11): Ein Tabellenprogramm würde Felder, die mit = + - @ (oder Tab/Zeilenumbruch) beginnen, als
# Formel lesen. Ein Apostroph davor stünde in DATEV im Buchungstext; deshalb werden solche Zeichen am Anfang entfernt.
_FORMULA_START = re.compile(r'^[=+\-@\t\r\s]+')


def _text(value, limit):
    value = re.sub(r'\s+', ' ', re.sub(r'[;"]', ' ', str(value or ''))).strip()
    value = _FORMULA_START.sub('', value)
    return '"' + value.encode('cp1252', 'replace').decode('cp1252')[:limit] + '"'


def _beleg(value):
    # Belegfeld 1: höchstens 36 Zeichen aus a-z A-Z 0-9 $ & % * + - / . – nicht mit + oder - beginnend (Formel, F11)
    return '"' + _FORMULA_START.sub('', re.sub(r'[^A-Za-z0-9$&%*+\-/.]', '', str(value or '')))[:36] + '"'


def bookings(conn, start, end, s):
    """Liste der Buchungen als dicts (cents, sh, konto, gegen, bu, datum, beleg, text, pruefen)."""
    out = []
    for inv in conn.execute("SELECT * FROM invoices WHERE status<>'entwurf' AND issue_date BETWEEN ? AND ? ORDER BY issue_date, number", (start, end)):
        storno = inv['kind'] == 'storno'
        for g in _invoice_rate_groups(conn, inv['id'], inv['tax_mode']):
            account = (REVENUE_ACCOUNTS['reverse_charge'] if inv['tax_mode'] == 'reverse_charge' else
                       REVENUE_ACCOUNTS['kleinunternehmer'] if inv['tax_mode'] == 'kleinunternehmer' else
                       REVENUE_ACCOUNTS.get(f"regel_{g['rate']}", '8400'))
            cents = g['net_cents'] + g['vat_cents']
            if not cents:
                continue
            # Storno: Beträge sind negativ gespeichert; DATEV erwartet positive Umsätze mit umgekehrtem Kennzeichen.
            sh = 'H' if cents < 0 else 'S'
            out.append({'cents': abs(cents), 'sh': sh, 'konto': s['debitor'], 'gegen': account, 'bu': '',
                        'datum': inv['issue_date'], 'beleg': inv['number'],
                        'text': f"{'Storno ' if storno else ''}{inv['buyer_name']}", 'pruefen': False})
    for pay in conn.execute("""SELECT p.*, i.number, i.buyer_name FROM payments p JOIN invoices i ON i.id=p.invoice_id
                               WHERE p.paid_on BETWEEN ? AND ? ORDER BY p.paid_on, p.id""", (start, end)):
        if pay['amount_cents']:
            out.append({'cents': abs(pay['amount_cents']), 'sh': 'S' if pay['amount_cents'] > 0 else 'H', 'konto': s['bank'],
                        'gegen': s['debitor'], 'bu': '', 'datum': pay['paid_on'], 'beleg': pay['number'],
                        'text': f"Zahlung {pay['buyer_name']}", 'pruefen': False})
    for e in conn.execute("SELECT * FROM expenses WHERE status='aktiv' AND expense_date BETWEEN ? AND ? ORDER BY expense_date, id", (start, end)):
        rc = bool(e['reverse_charge'])
        out.append({'cents': abs(e['gross_cents']), 'sh': 'S', 'konto': EXPENSE_CATEGORIES.get(e['category'], ('', '4900'))[1],
                    'gegen': s['bank'], 'bu': '' if rc else VORSTEUER_BU.get(int(e['vat_rate'] or 0), ''),
                    'datum': e['expense_date'], 'beleg': e['receipt_ref'] or f"A{e['id']}",
                    'text': f"{'prüfen §13b ' if rc else ''}{e['supplier']} {e['description']}".strip(), 'pruefen': rc})
    return out


def buchungsstapel(conn, params, now=None):
    """Gibt ``(bytes, info)`` zurück. ``info`` enthält Anzahl, Zeitraum und die zu prüfenden Zeilen."""
    s = get_datev_settings(conn)
    if s['missing']:
        raise ValueError('Für den DATEV-Export fehlen: ' + ', '.join(s['missing']) + ' (von der Steuerberatung).')
    start, end = _period(params)
    d_start, d_end = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    fy = _fiscal_start(d_start, s['wj_beginn_monat'])
    if _fiscal_start(d_end, s['wj_beginn_monat']) != fy:
        raise ValueError('Der Zeitraum muss in einem Wirtschaftsjahr liegen (DATEV-Belegdatum ohne Jahr).')
    rows = bookings(conn, start, end, s)
    now = now or dt.datetime.now()
    header = ['"EXTF"', '700', '21', '"Buchungsstapel"', '13', now.strftime('%Y%m%d%H%M%S') + f'{now.microsecond // 1000:03d}',
              '', '"SD"', '""', '""', s['berater_nr'], s['mandant_nr'], fy.strftime('%Y%m%d'), '4',
              d_start.strftime('%Y%m%d'), d_end.strftime('%Y%m%d'), _text(f"SignalDesk {d_start:%Y%m%d}-{d_end:%Y%m%d}", 30), _text(s['diktat'], 2),
              '1', '0', '0', '"EUR"', '', '""', '', '', '"03"', '', '', '""', '""']
    lines = [';'.join(header), ';'.join(COLUMNS)]
    for b in rows:
        day = dt.date.fromisoformat(b['datum'])
        lines.append(';'.join([_amount(b['cents']), f'"{b["sh"]}"', '"EUR"', '', '', '""', b['konto'], b['gegen'],
                               f'"{b["bu"]}"', day.strftime('%d%m'), _beleg(b['beleg']), '""', '', _text(b['text'], 60)]))
    data = ('\r\n'.join(lines) + '\r\n').encode('cp1252', 'replace')
    return data, {'count': len(rows), 'from': start, 'to': end, 'review': [b for b in rows if b['pruefen']], 'notice': NOTICE}
