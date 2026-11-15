"""Browserprüfung 2.0.0-dev42 (Produktreview M24 Stufe 2): Kalender-Abgleich in „Einstellungen → Kalender & Postfach“ –
Zugang eintragen, Verbindung prüfen, abgleichen; der Termin steht im (nachgebauten) Kalender, das Passwort nie in der Oberfläche.
Danach warnt das Anlegen eines Termins in einer belegten Zeit. Fiktive Firma, nur Abrufe auf 127.0.0.1."""
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
from test_v2_caldav import FOREIGN, PASS, TOMORROW, USER, FakeCalDAV  # noqa: E402

from sales_tool import credentials  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class CalDavBrowserTests(unittest.TestCase):
    def test_setup_sync_and_conflict(self):
        FakeCalDAV.store = {'/cal/fremd-1.ics': FOREIGN}
        FakeCalDAV.log = []
        dav = ThreadingHTTPServer(('127.0.0.1', 0), FakeCalDAV)
        threading.Thread(target=dav.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'cd.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Abgleich Fiktiv GmbH', 'stage': 'termin'})
            start = (dt.datetime.now() + dt.timedelta(days=3)).strftime('%Y-%m-%dT10:00')
            api('/workspace/meetings', 'POST', {'lead_id': lead['id'], 'title': 'Erstgespräch', 'starts_at': start, 'duration_min': 30})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(base + '/#/einstellungen?abschnitt=kalender')
                        page.wait_for_load_state('networkidle')
                        page.locator('#cdForm').wait_for()
                        self.assertTrue(page.locator('#cdSync').is_disabled(), 'ohne Zugang kein Abgleich')
                        page.fill('#cdUrl', f'http://127.0.0.1:{dav.server_port}/cal/')
                        page.fill('#cdUser', USER)
                        page.fill('#cdPass', PASS)
                        page.locator('#cdForm button[type=submit]').click()
                        page.wait_for_function('() => document.querySelector("#cdStatus")?.textContent.includes("hinterlegt (bis zum Neustart)")')
                        self.assertEqual(page.input_value('#cdPass'), '', 'Passwort kommt nicht zurück in die Oberfläche')
                        self.assertNotIn(PASS, page.content())
                        page.locator('#cdTest').click()
                        page.wait_for_function('() => document.getElementById("toast").textContent.includes("Verbindung steht")')
                        page.locator('#cdSync').click()
                        page.wait_for_function('() => document.querySelector("#cdStatus")?.textContent.includes("1 Termin(e) übertragen")')
                        self.assertTrue(any(k.startswith('/cal/signaldesk-meeting-') for k in FakeCalDAV.store))
                        self.assertEqual(FakeCalDAV.store['/cal/fremd-1.ics'], FOREIGN)
                        self.assertIn('1 belegte Zeit(en) bekannt', page.inner_text('#cdStatus'))
                        self.assertEqual(page.locator('[data-cd-stale]').count(), 0)
                        day = f'{TOMORROW[:4]}-{TOMORROW[4:6]}-{TOMORROW[6:]}'
                        r = api('/workspace/meetings', 'POST', {'lead_id': lead['id'], 'title': 'Kollision', 'starts_at': f'{day}T10:15', 'duration_min': 30})
                        self.assertIn('überschneidet', r['warning'])
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                dav.shutdown()
                dav.server_close()
                credentials._MEMORY.clear()


if __name__ == '__main__':
    unittest.main()
