"""Browserprüfung 2.0.0-dev23 (Produktreview M16): Versand mit gewählter Nachfassfrist und Anlass dokumentieren, Ergebnis
„nicht erreicht“ mit neuer Frist festhalten, dann „nicht weiter nachfassen“. Fiktive Firma, keine Abrufe nach außen."""
import datetime as dt
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

from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

D = lambda n: (dt.date.today() + dt.timedelta(days=n)).isoformat()


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class FollowupBrowserTests(unittest.TestCase):
    def test_followup_with_deadline_and_outcome(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'fu.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Nachfass Fiktiv GmbH', 'stage': 'termin', 'permission': 'opt_in'})
            conn = connect(str(db))
            confirm_need(conn, lead['id'])
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'positions': [{'service': 'webdesign', 'size': 'M'}]})
            conn = connect(str(db))
            release_offer(conn, p['id'])
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
                        page.locator(f'[data-quote-open="{p["id"]}"]').click()
                        page.locator('#ofPanel [data-of-followdate]').wait_for()
                        self.assertEqual(page.input_value('#ofPanel [data-of-followdate]'), D(7))
                        page.fill('#ofPanel [data-of-followdate]', D(3))
                        page.fill('#ofPanel [data-of-followreason]', 'Entscheidung nach Gesellschafterrunde')
                        page.locator('#ofPanel [data-of-sent]').click()
                        item = page.locator('#ofFollow [data-of-fu-item]')
                        item.wait_for()
                        self.assertIn('Entscheidung nach Gesellschafterrunde', item.inner_text())
                        self.assertIn(f"{dt.date.fromisoformat(D(3)).day}. ", item.inner_text())
                        item.locator('[data-of-fu-outcome]').select_option('nicht_erreicht')
                        item.locator('[data-of-fu-note]').fill('Mailbox')
                        item.locator('[data-of-fu-next]').fill(D(5))
                        item.locator('[data-of-fu]').click()
                        page.locator('#ofFollow .of-fu-done', has_text='Nicht erreicht').wait_for()
                        self.assertIn('Erneut versuchen', page.locator('#ofFollow [data-of-fu-item]').inner_text())
                        nxt = page.locator('#ofFollow [data-of-fu-item]')
                        nxt.locator('[data-of-fu-outcome]').select_option('beendet')
                        self.assertTrue(nxt.locator('[data-of-fu-next]').is_disabled())
                        nxt.locator('[data-of-fu]').click()
                        page.locator('#ofFollow', has_text='kein nächster Schritt').wait_for()
                        self.assertEqual(len(api(f'/workspace/proposals/{p["id"]}/nachfassen')['items']), 2)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
