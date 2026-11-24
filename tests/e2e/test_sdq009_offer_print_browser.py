"""Browserprüfung SDQ-009: Im geöffneten Angebot führt „Angebot als PDF ↗“ zur gestalteten Druckseite (/angebot/ID).
Ein nicht freigegebenes Angebot trägt dort die Entwurfsmarke und kein Unterschriftsfeld. Fiktive Firma, keine Abrufe nach außen."""
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
class OfferPrintBrowserTests(unittest.TestCase):
    def test_pdf_button_opens_designed_offer(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'op.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Druckbild Fiktiv GmbH', 'stage': 'termin'})
            prop = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}]})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.context.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + f'/#/angebote?angebot={prop["id"]}')
                        page.locator('#quoteSaved h3', has_text=prop['number']).wait_for()
                        button = page.locator(f'[data-quote-print="{prop["id"]}"]')
                        self.assertEqual(button.get_attribute('href'), f'/angebot/{prop["id"]}')
                        with page.context.expect_page() as popup_info:
                            button.click()
                        doc = popup_info.value
                        doc.on('pageerror', lambda exc: errors.append(str(exc)))
                        doc.wait_for_load_state('networkidle')
                        self.assertEqual(doc.locator('main.sheet').get_attribute('data-offer-final'), '0')
                        self.assertIn('ENTWURF', doc.locator('.draft-mark').inner_text())
                        self.assertIn('Druckbild Fiktiv GmbH', doc.locator('.address').inner_text())
                        self.assertIn(prop['number'], doc.locator('table.meta').inner_text())
                        self.assertEqual(doc.locator('.sign').count(), 0)
                        self.assertTrue(doc.locator('#printBtn').is_visible())
                        self.assertNotEqual(doc.evaluate("getComputedStyle(document.querySelector('.draft-mark')).position"), 'static',
                                            'offer.css/invoice.css geladen')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
