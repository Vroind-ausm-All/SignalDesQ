"""SDQ-025: DATEV-Buchungsstapel (EXTF 700) für die Steuerberatung.

Geprüft wird der Aufbau, den die DATEV-Formatbeschreibung vorgibt (Kopfzeile, Spaltenzeile, Datenzeilen, Zeichensatz,
Zahlenformat, Belegdatum TTMM) und die Kontierung. Ein Probeimport in DATEV ist damit nicht ersetzt."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent))
from test_accounting import SELLER, TODAY, buyer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import accounting as acc, datev  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402

YEAR = TODAY[:4]


class DatevBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'd.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        acc.save_settings(self.conn, SELLER)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def rows(self, params=None):
        data, info = datev.buchungsstapel(self.conn, params or {})
        text = data.decode('cp1252')
        self.assertTrue(text.endswith('\r\n'))
        lines = text.split('\r\n')[:-1]
        return lines[0].split(';'), lines[1].split(';'), [l.split(';') for l in lines[2:]], info


class DatevSettingsTests(DatevBase):
    def test_numbers_required_and_validated(self):
        with self.assertRaisesRegex(ValueError, 'Beraternummer, Mandantennummer'):
            datev.buchungsstapel(self.conn, {})
        for bad in ({'berater_nr': '12a'}, {'mandant_nr': '123456'}, {'debitor': '1400'}, {'wj_beginn_monat': 13},
                    {'wj_beginn_monat': True}, {'unbekannt': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                datev.save_datev_settings(self.conn, bad)
        s = datev.save_datev_settings(self.conn, {'berater_nr': '1234567', 'mandant_nr': '42'})
        self.assertEqual(s['missing'], [])
        self.assertEqual((s['debitor'], s['bank']), ('10000', '1200'))


class DatevFileTests(DatevBase):
    def setUp(self):
        super().setUp()
        datev.save_datev_settings(self.conn, {'berater_nr': '1234567', 'mandant_nr': '42'})

    def test_header_and_columns(self):
        header, cols, data, info = self.rows()
        self.assertEqual(header[:5], ['"EXTF"', '700', '21', '"Buchungsstapel"', '13'])
        self.assertRegex(header[5], r'^\d{17}$')
        self.assertEqual(header[10:16], ['1234567', '42', f'{YEAR}0101', '4', f'{YEAR}0101', f'{YEAR}1231'])
        self.assertEqual(header[21], '"EUR"')
        self.assertEqual(header[26], '"03"')
        self.assertEqual(cols[0], 'Umsatz (ohne Soll/Haben-Kz)')
        self.assertEqual(cols[13], 'Buchungstext')
        self.assertEqual(data, [])
        self.assertIn('Probeimport', info['notice'])

    def test_bookings_accounts_and_formats(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer(lines=[
            {'description': 'a', 'quantity': 1, 'unit': 'pauschal', 'unit_price_eur': '1000', 'vat_rate': 19},
            {'description': 'b', 'quantity': 1, 'unit': 'pauschal', 'unit_price_eur': '1234.5', 'vat_rate': 7}]))['id'])
        acc.cancel_invoice(self.conn, inv['id'])
        paid = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        acc.add_payment(self.conn, paid['id'], {'amount_eur': '500', 'paid_on': TODAY, 'method': 'ueberweisung'})
        acc.create_expense(self.conn, {'expense_date': TODAY, 'supplier': 'Bürobedarf Müller; "Spezial"', 'gross_eur': '119',
                                       'vat_rate': 19, 'category': 'buero', 'receipt_ref': 'B 2026/11 #7'})
        acc.create_expense(self.conn, {'expense_date': TODAY, 'supplier': 'SaaS Ltd', 'gross_eur': '50', 'vat_rate': 19,
                                       'category': 'software', 'reverse_charge': True})
        _, cols, data, info = self.rows()
        self.assertTrue(all(len(r) == len(cols) == 14 for r in data))
        by = lambda **kv: [r for r in data if all(r[cols.index(k)] == v for k, v in kv.items())]
        ttmm = TODAY[8:10] + TODAY[5:7]
        # Ausgangsrechnung: Debitor an Automatik-Erlöskonto, kein BU-Schlüssel, Belegdatum TTMM, Dezimalkomma ohne Tausenderpunkt
        self.assertEqual(len(by(Konto='10000', **{'Gegenkonto (ohne BU-Schlüssel)': '8300', 'Soll/Haben-Kennzeichen': '"S"'})), 1)
        row = by(**{'Gegenkonto (ohne BU-Schlüssel)': '8300', 'Soll/Haben-Kennzeichen': '"S"'})[0]
        self.assertEqual(row[0], '1320,92')  # 1234,50 + 7 %
        self.assertEqual(row[cols.index('Belegdatum')], ttmm)
        self.assertEqual(row[cols.index('BU-Schlüssel')], '""')
        # Storno: positiver Betrag, Haben
        self.assertEqual(len(by(**{'Soll/Haben-Kennzeichen': '"H"', 'Gegenkonto (ohne BU-Schlüssel)': '8300'})), 1)
        self.assertTrue(all(not r[0].startswith('-') for r in data))
        # Zahlung: Bank an Debitor
        self.assertEqual(by(Konto='1200')[0][0], '500,00')
        # Ausgabe mit Vorsteuer 19 %: BU 9; Text ohne Trennzeichen, Belegfeld bereinigt
        office = by(Konto='4930')[0]
        self.assertEqual(office[cols.index('BU-Schlüssel')], '"9"')
        self.assertEqual(office[cols.index('Belegfeld 1')], '"B2026/117"')
        self.assertEqual(office[cols.index('Buchungstext')], '"Bürobedarf Müller Spezial"')
        # § 13b: ohne Schlüssel, zur Prüfung markiert
        self.assertEqual(len(info['review']), 1)
        self.assertEqual(by(Konto='4964')[0][cols.index('BU-Schlüssel')], '""')

    def test_period_must_stay_in_one_fiscal_year(self):
        with self.assertRaisesRegex(ValueError, 'Wirtschaftsjahr'):
            datev.buchungsstapel(self.conn, {'from': f'{int(YEAR) - 1}-12-01', 'to': f'{YEAR}-01-31'})
        datev.save_datev_settings(self.conn, {'wj_beginn_monat': 7})
        header, _, _, _ = self.rows({'from': f'{int(YEAR) - 1}-12-01', 'to': f'{YEAR}-01-31'})
        self.assertEqual(header[12], f'{int(YEAR) - 1}0701')


class DatevHttpTests(unittest.TestCase):
    def test_settings_preview_and_download(self):
        tmp = tempfile.TemporaryDirectory()
        db = Path(tmp.name) / 'h.sqlite3'
        with connect(db) as conn:
            init_db(conn)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_address[1]}/api/accounting'
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(base + '/datev/preview')
            self.assertEqual(ctx.exception.code, 400)
            req = Request(base + '/datev/settings', method='PUT', headers={'Content-Type': 'application/json'},
                          data=json.dumps({'berater_nr': '1001', 'mandant_nr': '1'}).encode())
            with urlopen(req) as resp:
                self.assertEqual(json.loads(resp.read())['missing'], [])
            with urlopen(base + '/datev/preview') as resp:
                self.assertEqual(json.loads(resp.read())['count'], 0)
            with urlopen(base + '/export/datev.csv') as resp:
                self.assertEqual(resp.headers['Content-Type'], 'text/csv; charset=windows-1252')
                self.assertIn('EXTF_Buchungsstapel', resp.headers['Content-Disposition'])
                self.assertTrue(resp.read().startswith(b'"EXTF";700;21;'))
        finally:
            server.shutdown()
            server.server_close()
            cleanup_tmp(tmp)


if __name__ == '__main__':
    unittest.main()
