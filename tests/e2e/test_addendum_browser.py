"""Browserprüfung 2.0.0-dev25 (Produktreview M18): Am angenommenen Auftrag „Zusatzauftrag erstellen“, eine Leistung
hinzufügen, Anlass eintragen, speichern → -Z1 mit Auftragsumfang; der Auftrag bleibt unverändert. Fiktive Firma, keine Abrufe nach außen."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

sys.path.insert(0, str(Path(__file__).parent.parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402

from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AddendumBrowserTests(unittest.TestCase):
    def test_create_addendum_from_accepted_order(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'za.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Zusatz Fiktiv GmbH', 'stage': 'termin'})
            conn = connect(str(db))
            confirm_need(conn, lead['id'])
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Neue Website',
                                                     'positions': [{'service': 'webdesign', 'size': 'M'}]})
            conn = connect(str(db))
            release_offer(conn, p['id'])
            of.set_status(conn, p['id'], {'status': 'gesendet_manuell'})
            of.set_status(conn, p['id'], {'status': 'angenommen'})
            before = conn.execute('SELECT customer_json FROM proposals WHERE id=?', (p['id'],)).fetchone()[0]
            conn.close()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'[data-quote-open="{p["id"]}"]').first.click()
                        page.locator(f'[data-of-addendum="{p["id"]}"]').click()
                        page.locator('#qbAddendum').wait_for(state='visible')
                        self.assertIn(p['number'], page.locator('#qbAddendumOf').inner_text())
                        self.assertEqual(page.locator('#qbPositions .qb-pos').count(), 0, 'leerer Baukasten')
                        page.select_option('#qbService', 'texte')
                        page.fill('#qbQty', '3')
                        page.locator('#qbAdd').click()
                        page.fill('#quoteForm [name=project_label]', 'Englische Version')
                        page.fill('#qbAddendumReason', 'Kundenwunsch: Englische Sprachversion')
                        page.locator('#quoteForm button[type=submit]').click()
                        page.locator('#quoteSaved h3', has_text=p['number'] + '-Z1').wait_for()
                        self.assertTrue(page.locator('#qbAddendum').is_hidden())
                        scope = page.locator('.of-scope')
                        scope.wait_for()
                        text = scope.inner_text()
                        self.assertIn(p['number'], text)
                        self.assertIn('Zusatzauftrag 1: Englische Version', text)
                        self.assertIn('Anlass: Kundenwunsch: Englische Sprachversion', text)
                        z1 = next(r for r in api('/workspace/proposals') if r['number'] == p['number'] + '-Z1')
                        self.assertIn('Bezug zum bestehenden Auftrag', api(f"/workspace/proposals/{z1['id']}/customer")['markdown'])
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
            conn = connect(str(db))
            self.assertEqual(conn.execute('SELECT customer_json FROM proposals WHERE id=?', (p['id'],)).fetchone()[0], before, 'Auftrag unverändert')
            conn.close()


if __name__ == '__main__':
    unittest.main()
