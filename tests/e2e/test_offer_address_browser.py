"""Browserprüfung 2.0.0-dev38 (Produktreview M07): Ein geöffnetes Angebot hat eine eigene Adresse (#/angebote?angebot=ID);
Neuladen und direkt eingegebene Adresse öffnen es wieder. Fiktive Firma, keine Abrufe nach außen."""
import json
import os
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

from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class OfferAddressBrowserTests(unittest.TestCase):
    def test_offer_has_address(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'oa.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Adresse Fiktiv GmbH', 'stage': 'termin'})
            p1 = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}]})
            p2 = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'opportunity_id': 'neu', 'positions': [{'service': 'texte', 'qty': 2}]})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'[data-quote-open="{p1["id"]}"]').first.click()
                        page.locator('#quoteSaved h3', has_text=p1['number']).wait_for()
                        page.wait_for_function(f'() => location.hash === "#/angebote?angebot={p1["id"]}"')
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        page.locator('#quoteSaved h3', has_text=p1['number']).wait_for()
                        page.goto(base + f'/#/angebote?angebot={p2["id"]}')
                        page.locator('#quoteSaved h3', has_text=p2['number']).wait_for()
                        page.locator(f'[data-quote-open="{p1["id"]}"]').first.click()
                        page.wait_for_function(f'() => location.hash === "#/angebote?angebot={p1["id"]}"')  # Eintrag entsteht nach dem Aufbau
                        page.go_back()
                        page.locator('#quoteSaved h3', has_text=p2['number']).wait_for()
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
