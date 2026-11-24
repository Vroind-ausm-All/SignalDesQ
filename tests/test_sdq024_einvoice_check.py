"""SDQ-024: Eigene E-Rechnungen vor dem Versand gegen die wichtigsten Regeln aus EN 16931 und XRechnung 3.0 prüfen.

Die Prüfung ersetzt den KoSIT-Validator nicht. Die Tests sichern zweierlei: Was SignalDesk selbst erzeugt, besteht die
Prüfung in allen Steuerarten. Gezielt verfälschte Rechnungen (Summe, IBAN, Platzhalter-Adresse, Steuer) fallen auf."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent))
from test_accounting import SELLER, buyer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool.einvoice import xrechnung_xml  # noqa: E402
from sales_tool.einvoice_check import check  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402


def rules(result):
    return {e['rule'] for e in result['errors']}


class CheckBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 't.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        acc.save_settings(self.conn, SELLER)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def xml(self, **extra):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer(buyer_reference='04011000-12345-67', **extra))['id'])
        return xrechnung_xml(self.conn, inv['id'])[0], inv


class GeneratedInvoicesPass(CheckBase):
    def test_standard_mixed_rates_and_storno(self):
        data, inv = self.xml(lines=[
            {'description': 'Workshop', 'quantity': 3, 'unit': 'stunde', 'unit_price_eur': '95.50', 'vat_rate': 7},
            {'description': 'Umsetzung', 'quantity': '2.5', 'unit': 'stunde', 'unit_price_eur': '33.33', 'vat_rate': 19}])
        result = check(data)
        self.assertTrue(result['valid'], result['errors'])
        self.assertEqual(result['profile'], 'XRechnung 3.0')
        self.assertGreater(result['rules_checked'], 50)
        self.assertIn('KoSIT', result['notice'])
        storno = acc.cancel_invoice(self.conn, inv['id'])
        self.assertTrue(check(xrechnung_xml(self.conn, storno['id'])[0])['valid'])

    def test_reverse_charge_and_small_business(self):
        data, _ = self.xml(tax_mode='reverse_charge', buyer_vat_id='ATU12345678', buyer_country='AT')
        self.assertTrue(check(data)['valid'], check(data)['errors'])
        acc.save_settings(self.conn, {'small_business': True, 'vat_id': ''})
        data, _ = self.xml(tax_mode='kleinunternehmer')
        self.assertTrue(check(data)['valid'], check(data)['errors'])

    def test_missing_buyer_email_is_an_error_not_a_placeholder(self):
        data, _ = self.xml(buyer_email='')
        self.assertIn('BR-DE-26', rules(check(data)))


class TamperedInvoicesFail(CheckBase):
    def setUp(self):
        super().setUp()
        self.data, _ = self.xml()

    def swap(self, old, new):
        self.assertIn(old.encode(), self.data)
        return self.data.replace(old.encode(), new.encode(), 1)

    def test_wrong_payable_amount(self):
        self.assertIn('BR-CO-16', rules(check(self.swap('PayableAmount currencyID="EUR">7021.00', 'PayableAmount currencyID="EUR">7012.00'))))

    def test_wrong_tax_amount(self):
        result = check(self.swap('<cbc:TaxAmount currencyID="EUR">1121.00', '<cbc:TaxAmount currencyID="EUR">1120.00'))
        self.assertFalse(result['valid'])

    def test_iban_checksum(self):
        self.assertIn('BR-DE-19', rules(check(self.swap('DE89370400440532013000', 'DE89370400440532013001'))))

    def test_placeholder_email_counts_as_missing(self):
        self.assertIn('BR-DE-26', rules(check(self.swap('buchhaltung@beispiel.example', 'unbekannt@invalid'))))

    def test_unknown_currency_and_missing_number(self):
        self.assertIn('BR-CL-04', rules(check(self.swap('<cbc:DocumentCurrencyCode>EUR', '<cbc:DocumentCurrencyCode>Euro'))))
        number = self.data.split(b'<cbc:ID>', 1)[1].split(b'<', 1)[0].decode()
        self.assertIn('BR-02', rules(check(self.swap(f'<cbc:ID>{number}</cbc:ID>', '<cbc:ID></cbc:ID>'))))

    def test_dangerous_and_foreign_formats(self):
        result = check(b'<!DOCTYPE x [<!ENTITY a "aaaa">]><Invoice>&a;</Invoice>')
        self.assertFalse(result['valid'])
        self.assertFalse(check(b'kein xml')['valid'])
        cii = check(b'<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"/>')
        self.assertIsNone(cii['valid'])  # nicht geprüft – weder gültig noch fehlerhaft
        self.assertEqual(cii['errors'], [])


class CheckOverHttp(unittest.TestCase):
    def test_route_and_import(self):
        tmp = tempfile.TemporaryDirectory()
        db = Path(tmp.name) / 'h.sqlite3'
        with connect(db) as conn:
            init_db(conn)
            acc.save_settings(conn, SELLER)
            inv = acc.finalize_invoice(conn, acc.create_invoice(conn, buyer(buyer_reference='X'))['id'])
            xml = xrechnung_xml(conn, inv['id'])[0]
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_address[1]}'
        try:
            with urlopen(f"{base}/api/accounting/invoices/{inv['id']}/xrechnung/check") as resp:
                body = json.loads(resp.read())
            self.assertTrue(body['valid'])
            self.assertEqual(body['generator_warnings'], [])
            req = Request(base + '/api/accounting/einvoice/import', method='POST', headers={'Content-Type': 'application/json'},
                          data=json.dumps({'filename': 'eigene.xml', 'xml': xml.decode().replace('DE89370400440532013000', 'DE00370400440532013000')}).encode())
            with urlopen(req) as resp:
                body = json.loads(resp.read())
            self.assertFalse(body['check']['valid'])
            self.assertIn('BR-DE-19', rules(body['check']))
        finally:
            server.shutdown()
            server.server_close()
            cleanup_tmp(tmp)


if __name__ == '__main__':
    unittest.main()
