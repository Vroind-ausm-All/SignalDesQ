"""Browserprüfung SDQ-005: Akte schließen und gleich wieder eine Akte aufrufen – die Adresse bleibt bei der Akte.

Gefunden durch die volle Browser-Suite in der CI (SDQ-005): Beim Schließen der Akte prüft SignalDesk einen Augenblick später,
ob die Adresse noch auf die Firma zeigt, und nimmt sie dann zurück. Kam in diesem Augenblick schon die nächste Adresse – etwa
wieder die Akte über Zurück, einen Link oder eine eingegebene Adresse –, wurde diese mit „#/firmen“ überschrieben, obwohl die
Akte offen war. Das ist derselbe Widerspruch wie in Audit-Befund B1, nur seltener (hängt vom Zeitpunkt ab).
Fiktive Firma, keine Abrufe nach außen."""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool.server import make_handler, prepare_database

OPEN = "() => !document.getElementById('modal').classList.contains('hidden')"


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AkteCloseRaceBrowserTests(unittest.TestCase):
    def test_new_address_right_after_closing_is_kept(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'race.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            req = urllib.request.Request(base + '/api/leads', method='POST', headers={'Content-Type': 'application/json', 'Origin': base},
                                         data=json.dumps({'company': 'Beispiel Drehteile GmbH', 'stage': 'recherche'}).encode())
            lead = json.loads(urllib.request.urlopen(req).read())
            akte = f"#/firmen/akte/{lead['id']}"
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 800})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        for area in ('abrechnen', 'angebote', 'firmen'):
                            with self.subTest(area=area):
                                page.goto(base + '/#/' + area)
                                page.wait_for_load_state('networkidle')
                                page.goto(base + '/' + akte)
                                page.locator('#leadTabs').wait_for(state='visible')
                                self.assertEqual(page.evaluate('location.hash'), akte)
                                # Seitenleiste, und noch im selben Augenblick die nächste Adresse: wieder die Akte
                                page.evaluate(f"""() => {{ document.querySelector('.sidebar .nav[data-area="{area}"]').click();
                                                         location.hash = '{akte}'; }}""")
                                page.locator('#leadTabs').wait_for(state='visible')
                                time.sleep(0.3)  # der aufgeschobene Schließ-Check ist sicher gelaufen
                                self.assertTrue(page.evaluate(OPEN))
                                self.assertEqual(page.evaluate('location.hash'), akte, 'Akte offen, Adresse muss die Akte sein')
                                # normales Schließen nimmt die Adresse weiterhin zurück
                                page.locator('.sidebar .nav[data-area="heute"]').click()
                                page.wait_for_function('() => location.hash.startsWith("#/heute")')
                                page.locator('#modal').wait_for(state='hidden')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
