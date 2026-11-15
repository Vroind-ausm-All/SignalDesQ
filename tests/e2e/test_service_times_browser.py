"""Browserprüfung 2.0.0-dev27 (Produktreview M20): In der Nachkalkulation Zeit einer Angebotsposition zuordnen; die Tabelle
zeigt Soll/Ist je Position. Fiktive Firma, keine Abrufe nach außen."""
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
class ServiceTimesBrowserTests(unittest.TestCase):
    def test_time_per_position(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'st.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Zeiten Fiktiv GmbH', 'stage': 'termin'})
            conn = connect(str(db))
            confirm_need(conn, lead['id'])
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19',
                                                     'positions': [{'service': 'logo', 'size': 'S'}, {'service': 'texte', 'qty': 2}]})
            conn = connect(str(db))
            release_offer(conn, p['id'])
            of.set_status(conn, p['id'], {'status': 'gesendet_manuell'})
            of.set_status(conn, p['id'], {'status': 'angenommen'})
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
                        card = page.locator(f'[data-pk="{p["id"]}"]')
                        card.wait_for()
                        form = card.locator(f'[data-pk-form="{p["id"]}"]')
                        form.locator('[name=position]').select_option('2')
                        form.locator('[name=hours]').fill('3')
                        form.locator('button[type=submit]').click()
                        page.wait_for_function(f'() => document.querySelector(\'[data-pk="{p["id"]}"] .pk-pos tbody tr:nth-child(2) td:nth-child(3)\')?.textContent.trim() === "3 h"')
                        row = card.locator('.pk-pos tbody tr').nth(1)
                        self.assertIn('Pos. 2', row.inner_text())
                        self.assertEqual(api('/postcalc')['projects'][0]['positions'][1]['actual_hours'], 3)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
