"""Browserprüfung 2.0.0-dev40 (Produktreview M07, Variante B): Die Firmenakte ist eine eigene Seite.
- Öffnen aus der Firmenliste: Adresse #/firmen/akte/ID, die Liste dahinter ist ausgeblendet, die Seite scrollt normal.
- „← Zurück“ schließt die Akte und zeigt wieder die Liste.
- Öffnen aus einer anderen Ansicht (Pipeline): Browser-Zurück führt dorthin zurück.
- Handyansicht: keine waagerechte Scrollleiste.
Fiktive Firma, keine Abrufe nach außen."""
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
class AktePageBrowserTests(unittest.TestCase):
    def test_akte_is_a_page(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ak.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Seite Fiktiv GmbH', 'stage': 'termin'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        page.locator('#leadRows tr', has_text='Seite Fiktiv GmbH').click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        page.wait_for_function(f'() => location.hash.startsWith("#/firmen/akte/{lead["id"]}")')
                        self.assertTrue(page.locator('#viewLeads').is_hidden(), 'Liste ausgeblendet')
                        self.assertEqual(page.evaluate('getComputedStyle(document.getElementById("modal")).position'), 'static', 'kein Fenster darüber')
                        self.assertEqual(page.evaluate('document.body.style.overflow'), '', 'Seite scrollt normal')
                        self.assertEqual(page.text_content('#sectionBreadcrumb'), 'Firmenakte')
                        self.assertEqual(page.text_content('#closeModal'), '← Firmen')  # 2.0.0-dev54: nennt das Ziel (vorher „← Zurück“)
                        self.assertIn('zurück', page.get_attribute('#closeModal', 'aria-label'))
                        page.locator('#closeModal').click()
                        page.locator('#modal').wait_for(state='hidden')
                        page.locator('#viewLeads').wait_for(state='visible')
                        page.wait_for_function('() => location.hash === "#/firmen"')

                        page.goto(base + '/#/firmen/pipeline')
                        page.wait_for_load_state('networkidle')
                        page.evaluate(f'() => showModal({lead["id"]})')
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertTrue(page.locator('#viewPipeline').is_hidden())
                        page.go_back()
                        page.locator('#modal').wait_for(state='hidden')
                        page.locator('#viewPipeline').wait_for(state='visible')

                        page.set_viewport_size({'width': 390, 'height': 844})
                        page.evaluate(f'() => showModal({lead["id"]})')
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertFalse(page.evaluate('() => document.documentElement.scrollWidth > window.innerWidth + 1'), 'Handy: kein seitliches Scrollen')
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
