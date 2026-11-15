"""Browserprüfung 2.0.0-dev41 (Produktreview M24 Stufe 1): In „Einstellungen → Kalender & Postfach“ das Kalender-Abo
einschalten, die Adresse liefert die Termine im iCalendar-Format; Ausschalten macht sie ungültig. Fiktive Firma, keine Abrufe nach außen."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class CalendarBrowserTests(unittest.TestCase):
    def test_subscribe_feed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'cal.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Termin Fiktiv GmbH', 'stage': 'termin'})
            api('/workspace/meetings', 'POST', {'lead_id': lead['id'], 'title': 'Erstgespräch', 'starts_at': '2099-05-06T09:30', 'duration_min': 30})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(base + '/#/einstellungen?abschnitt=kalender')
                        page.wait_for_load_state('networkidle')
                        page.locator('#calEnabled').check()
                        page.wait_for_function('() => document.querySelector("#calUrl").value.includes("/kalender/")')
                        url = page.input_value('#calUrl')
                        body = urllib.request.urlopen(url).read().decode()
                        self.assertIn('SUMMARY:Erstgespräch – Termin Fiktiv GmbH', body)
                        page.locator('#calEnabled').uncheck()
                        page.wait_for_function('() => document.querySelector("#calUrl").value === ""')
                        with self.assertRaises(urllib.error.HTTPError):
                            urllib.request.urlopen(url)
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
