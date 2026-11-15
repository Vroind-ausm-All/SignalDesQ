"""Browserprüfung 2.0.0-dev28 (Produktreview M38/M39): Projektkompass am angenommenen Auftrag – „wartet auf Kunde“,
Name und Frist setzen, Punkte erledigen bis „bereit zum Start“, Passwort-Eingabe wird abgelehnt, Start dokumentieren.
Fiktive Firma, keine Abrufe nach außen."""
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
class KickoffBrowserTests(unittest.TestCase):
    def test_kickoff_to_start(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ko.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Start Fiktiv GmbH', 'stage': 'termin'})
            conn = connect(str(db))
            confirm_need(conn, lead['id'])
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}]})
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
                        page.locator(f'[data-quote-open="{p["id"]}"]').first.click()
                        step = page.locator('#ofKickoff')
                        step.wait_for()
                        self.assertEqual(step.locator('[data-ko-status]').inner_text(), 'wartet auf Kunde')
                        self.assertIn('Gestaltung kann nicht beginnen', step.inner_text())
                        mat = step.locator('[data-ko-row]', has_text='Logo, Bilder')
                        mat.locator('[data-ko-name]').fill('Frau Beispiel')
                        mat.locator('[data-ko-name]').dispatch_event('change')
                        page.locator('#ofKickoff [data-ko-status]', has_text='Frau Beispiel').wait_for()
                        page.fill('#ofKickoff [data-ko-addlabel]', 'Passwort: geheim123')
                        page.locator('#ofKickoff [data-ko-add]').click()
                        page.locator('.toast, #toast', has_text='keine Passwörter').first.wait_for()
                        n = page.locator('#ofKickoff [data-ko-row]').count()
                        for _ in range(n):
                            page.locator('#ofKickoff select[data-ko-state]:has(option[value="offen"]:checked)').first.select_option('erledigt')
                            page.wait_for_load_state('networkidle')
                        page.wait_for_function('() => document.querySelector("#ofKickoff [data-ko-status]")?.textContent.trim() === "bereit zum Start"')
                        if SHOTS:
                            page.locator('#ofKickoff').screenshot(path=str(Path(SHOTS) / 'kompass.png'))
                        page.fill('#ofKickoff [data-ko-snote]', 'Kick-off per Video')
                        page.locator('#ofKickoff [data-ko-start]').click()
                        page.locator('#ofKickoff [data-ko-status]', has_text='gestartet am').wait_for()
                        self.assertEqual(api(f'/workspace/proposals/{p["id"]}/kompass')['status'], 'gestartet')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
