"""Browserprüfung 2.0.0-dev22 (Produktreview M15 Teil 2): Eine als „optional“ markierte Position erscheint in der
Kundenvorschau als optional und ändert die Summe nicht. Fiktive Firma, keine Abrufe nach außen."""
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
class OptionsBrowserTests(unittest.TestCase):
    def test_optional_position_not_in_total(self):
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

            lead = api('/leads', 'POST', {'company': 'Option Fiktiv GmbH', 'stage': 'termin'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.select_option('#quoteForm [name=lead_id]', str(lead['id']))
                        page.select_option('#quotePackage', 'conversion')
                        page.locator('#qbTemplate').click()
                        page.locator('#quoteCustomer .qb-table').wait_for()
                        total = lambda: page.locator('#quoteCustomer .quote-total strong').first.inner_text()
                        before = total()
                        page.locator('#qbPositions [data-qb-f="optional"][data-i="2"]').check()
                        page.wait_for_function('() => document.querySelector("#quoteCustomer").textContent.includes("optional")')
                        page.wait_for_function(f'() => document.querySelector("#quoteCustomer .quote-total strong").textContent !== {json.dumps(before)}')
                        self.assertIn('nicht im Festpreis', page.locator('#quoteCustomer').inner_text())
                        q = api('/pricing/preview', 'POST', {'positions': [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 4}], 'tax_mode': 'offen'})
                        self.assertIn(f"{q['customer']['once_net_eur']:,.0f}".replace(',', '.'), total())
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
