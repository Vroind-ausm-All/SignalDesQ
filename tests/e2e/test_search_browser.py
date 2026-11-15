"""Browserprüfung 2.0.0-dev34 (Produktreview M10): Strg+K öffnet die Suche, Treffer für Firma und Angebot, Pfeiltaste und
Enter öffnen das Angebot; Escape schließt und gibt den Fokus zurück. Fiktive Firma, keine Abrufe nach außen."""
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
class SearchBrowserTests(unittest.TestCase):
    def test_ctrl_k_search_and_open(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'gs.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Sonnenschein Fiktiv GmbH', 'stage': 'termin'})
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Sonnenschein-Website',
                                                     'positions': [{'service': 'webdesign', 'size': 'S'}]})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/heute')
                        page.wait_for_load_state('networkidle')
                        page.locator('#gsOpen').focus()
                        page.keyboard.press('Control+k')
                        page.locator('#gsInput').wait_for(state='visible')
                        self.assertTrue(page.evaluate('document.activeElement.id') == 'gsInput')
                        page.keyboard.press('Escape')
                        self.assertTrue(page.locator('#gsBackdrop').is_hidden())
                        self.assertEqual(page.evaluate('document.activeElement.id'), 'gsOpen', 'Fokus zurück')
                        page.keyboard.press('Control+k')
                        page.locator('#gsInput').fill('sonnen')
                        page.locator('#gsResults [data-gs-kind="angebot"]').wait_for()
                        self.assertEqual(page.locator('#gsResults [data-gs-kind="firma"]').count(), 1)
                        self.assertEqual(page.locator('#gsResults [aria-selected="true"]').get_attribute('data-gs-kind'), 'firma')
                        kinds = [page.locator('#gsResults [role=option]').nth(i).get_attribute('data-gs-kind') for i in range(page.locator('#gsResults [role=option]').count())]
                        self.assertEqual(kinds, ['firma', 'chance', 'angebot'], 'Chance entstand mit dem Angebot')
                        page.keyboard.press('ArrowDown')
                        page.keyboard.press('ArrowDown')
                        self.assertEqual(page.locator('#gsResults [aria-selected="true"]').get_attribute('data-gs-kind'), 'angebot')
                        page.keyboard.press('ArrowDown')
                        self.assertEqual(page.locator('#gsResults [aria-selected="true"]').get_attribute('data-gs-kind'), 'firma', 'springt an den Anfang')
                        page.keyboard.press('ArrowUp')
                        page.keyboard.press('Enter')
                        page.locator('#quoteSaved h3', has_text=p['number']).wait_for()
                        self.assertTrue(page.locator('#gsBackdrop').is_hidden())
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
