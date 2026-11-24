"""SDQ-009: Gestaltetes Angebot als Druckseite (/angebot/ID → im Browser „Als PDF speichern“).

Prüft: nur Kundenangaben (nichts Internes), Käuferanschrift ohne Person, Entwurfsmarke vor Freigabe und nach Änderung,
Versandfassung mit Stand und Unterschriftsfeld, 404 für unbekannte Angebote. Alle Daten sind fiktiv."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sales_tool import accounting as acc  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.offer_print import offer_html  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402
from s5_helpers import confirm_need, release_offer  # noqa: E402
from test_accounting import SELLER  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / 'o.sqlite3'
        prepare_database(self.db)
        self.conn = connect(self.db)
        acc.save_settings(self.conn, SELLER)
        self.lid = self.conn.execute(
            "INSERT INTO leads(company, stage, street, zip, city, contact_name, contact_role) "
            "VALUES ('Beispiel Werkzeugbau GmbH', 'termin', 'Industriestr. 4', '70565', 'Stuttgart', "
            "'Erika Muster', 'Geschäftsführerin')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lid)
        self.p = make_proposal(self.conn, {'lead_id': self.lid, 'tax_mode': 'regel_19', 'project_label': 'Neue Website',
                                           'positions': [{'service': 'webdesign', 'size': 'M'}, {'service': 'pflege', 'size': 'M'}]})
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def internal(self):
        row = self.conn.execute('SELECT internal_json FROM proposals WHERE id=?', (self.p['id'],)).fetchone()
        return json.loads(row[0])


class OfferPrintTests(_Base):
    def test_draft_is_marked_and_has_no_signature(self):
        html = offer_html(self.conn, self.p['id'])
        self.assertIn('data-offer-final="0"', html)
        self.assertIn('ENTWURF – nicht versenden', html)
        self.assertIn('nicht zum Versand freigegeben', html)
        self.assertNotIn('Unterschrift', html)

    def test_released_offer_has_stand_and_signature(self):
        rel = release_offer(self.conn, self.p['id'])
        self.conn.commit()
        html = offer_html(self.conn, self.p['id'])
        self.assertIn('data-offer-final="1"', html)
        self.assertNotIn('ENTWURF', html)
        self.assertIn('Auftrag erteilt – Unterschrift und Firmenstempel', html)
        stand = rel.get('stand') if isinstance(rel, dict) else None
        if stand:
            self.assertIn(f'Stand {stand}', html)
        self.assertIn('freigegeben am', html)

    def test_change_after_release_marks_draft_again(self):
        release_offer(self.conn, self.p['id'])
        row = self.conn.execute('SELECT customer_json FROM proposals WHERE id=?', (self.p['id'],)).fetchone()
        cu = json.loads(row[0])
        cu['goal'] = (cu.get('goal') or '') + ' Geändert nach Freigabe.'
        self.conn.execute('UPDATE proposals SET customer_json=? WHERE id=?', (json.dumps(cu, ensure_ascii=False), self.p['id']))
        self.conn.commit()
        html = offer_html(self.conn, self.p['id'])
        self.assertIn('ENTWURF – seit Freigabe geändert', html)
        self.assertNotIn('Unterschrift', html)

    def test_buyer_is_company_never_person(self):
        html = offer_html(self.conn, self.p['id'])
        for part in ('Beispiel Werkzeugbau GmbH', 'Industriestr. 4', '70565 Stuttgart'):
            self.assertIn(part, html)
        for person in ('Erika Muster', 'Geschäftsführerin'):
            self.assertNotIn(person, html)

    def test_no_internal_values(self):
        internal = self.internal()
        html = offer_html(self.conn, self.p['id'])
        self.assertTrue(internal['positions'][0]['formula'] and internal['basis'], 'Testvoraussetzung: interne Kalkulation vorhanden')
        for secret in (internal['positions'][0]['formula'], internal['basis'], '€/h', 'Puffer', 'Mindestverdienst', 'Stundensatz',
                       internal['need_confirmed_at'], internal['catalog_version']):
            self.assertNotIn(secret, html)
        self.assertNotIn('Anfragen gehen verloren', html, 'Bedarfsnotiz ist intern')

    def test_sums_with_vat(self):
        html = offer_html(self.conn, self.p['id'])
        self.assertIn('zzgl. 19 % USt. einmalig', html)
        self.assertIn('Gesamtbetrag einmalig', html)
        self.assertIn('/ Monat', html)

    def test_escapes_customer_text(self):
        self.conn.execute("UPDATE leads SET legal_name='<script>x</script> GmbH' WHERE id=?", (self.lid,))
        self.conn.commit()
        html = offer_html(self.conn, self.p['id'])
        self.assertNotIn('<script>x</script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_unknown_offer_raises(self):
        with self.assertRaises((ValueError, LookupError)):
            offer_html(self.conn, 9999)


class OfferRouteTests(_Base):
    def test_route_and_404(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            res = urllib.request.urlopen(f"{base}/angebot/{self.p['id']}")
            self.assertIn('text/html', res.headers.get('Content-Type'))
            self.assertIn('Beispiel Werkzeugbau GmbH', res.read().decode('utf-8'))
            self.assertIn('.draft-mark', urllib.request.urlopen(base + '/offer.css').read().decode('utf-8'))
            for bad in ('/angebot/9999', '/angebot/abc'):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base + bad)
                self.assertEqual(ctx.exception.code, 404, bad)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
