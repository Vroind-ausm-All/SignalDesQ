"""Browserprüfung 2.0.0-dev24 (Produktreview M17, Abnahmefall T12): Am angenommenen Angebot Liefergegenstände abhaken,
Übergabe dokumentieren, Abnahme mit einem Restpunkt festhalten, Protokoll herunterladen. Fiktive Firma, keine Abrufe nach außen."""
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

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class HandoverBrowserTests(unittest.TestCase):
    def test_hand_over_and_accept_with_rest_point(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ho.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Übergabe Fiktiv GmbH', 'stage': 'termin'})
            conn = connect(str(db))
            confirm_need(conn, lead['id'])
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Neues Logo',
                                                     'positions': [{'service': 'logo', 'size': 'S'}]})
            conn = connect(str(db))
            release_offer(conn, p['id'])
            of.set_status(conn, p['id'], {'status': 'gesendet_manuell'})
            of.set_status(conn, p['id'], {'status': 'angenommen'})
            conn.close()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'[data-quote-open="{p["id"]}"]').first.click()
                        step = page.locator('#ofHandover')
                        step.wait_for()
                        self.assertTrue(step.locator('[data-ho-handover]').is_disabled(), 'offene Liefergegenstände blockieren')
                        n = step.locator('.ho-items').first.locator('[data-ho-item]').count()
                        self.assertGreater(n, 0)
                        for _ in range(n):  # jeder Wechsel lädt den Schritt neu
                            page.locator('#ofHandover .ho-items').first.locator('select[data-ho-item]:has(option[value="offen"]:checked)').first.select_option('erledigt')
                            page.wait_for_load_state('networkidle')
                        page.locator('#ofHandover [data-ho-handover]:not([disabled])').wait_for()
                        page.locator('#ofHandover [data-ho-handover]').click()
                        page.locator('#ofHandover [data-ho-accept]').wait_for()
                        page.select_option('#ofHandover [data-ho-result]', 'vorbehalt')
                        page.fill('#ofHandover [data-ho-person]', 'Frau Beispiel')
                        page.fill('#ofHandover [data-ho-points]', 'Logo zusätzlich als SVG liefern')
                        page.locator('#ofHandover [data-ho-accept]').click()
                        page.locator('#ofHandover [data-ho-status]', has_text='Restpunkte offen').wait_for()
                        self.assertIn('Logo zusätzlich als SVG liefern', page.locator('#ofHandover').inner_text())
                        if SHOTS:
                            page.locator('#ofHandover').screenshot(path=str(Path(SHOTS) / 'abnahme.png'))
                        with page.expect_download() as dl:
                            page.locator('#ofHandover [data-ho-protocol]').click()
                        self.assertEqual(dl.value.suggested_filename, f"Abnahmeprotokoll-{p['number']}.md")
                        md = Path(dl.value.path()).read_text(encoding='utf-8')
                        self.assertIn('Abgenommen mit Restpunkten', md)
                        page.locator('#ofHandover select[data-ho-item]').last.select_option('erledigt')
                        page.wait_for_function('() => document.querySelector("#ofHandover [data-ho-status]")?.textContent.trim() === "abgenommen"')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
