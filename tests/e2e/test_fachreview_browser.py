"""Browserprüfung 2.0.0-dev46 (Produktreview M29/M33): Fachreview zu einer Website-Bewertung anlegen, Rubriken beurteilen
(sofort gespeichert – nach Neuladen noch da), Abschließen erst wenn vollständig, Kalibrierung zeigt die Übereinstimmung.
Fiktive Firma, nur 127.0.0.1."""
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
from test_v2_expert_review import make_audit  # noqa: E402

from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class FachreviewBrowserTests(unittest.TestCase):
    def test_review_save_complete_calibrate(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'fr.sqlite3'
            prepare_database(db)
            conn = connect(str(db))
            lead = conn.execute("INSERT INTO leads(company) VALUES ('Review Fiktiv GmbH')").lastrowid
            conn.commit()
            make_audit(conn, lead)
            conn.close()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/finden/website-scoring')
                        page.wait_for_load_state('networkidle')
                        page.locator('#frBox > summary').click()
                        page.locator('#frAudit option', has_text='Review Fiktiv GmbH').wait_for(state='attached')
                        page.fill('#frReviewer', 'AB')
                        page.locator('#frStartForm button[type=submit]').click()
                        page.locator('[data-fr-row]').first.wait_for()
                        rows = page.locator('[data-fr-row]')
                        self.assertEqual(rows.count(), 4)
                        ids = [rows.nth(i).get_attribute('data-fr-row') for i in range(4)]
                        # zwei Rubriken abwählen, zwei beurteilen
                        for rid in ids[2:]:
                            page.locator(f'[data-fr-row="{rid}"] input[data-fr-key="included"]').uncheck()
                            page.wait_for_function(f'() => !document.querySelector(\'[data-fr-row="{rid}"] [data-fr-key="verdict"]\')')
                        for rid, verdict in ((ids[0], 'auffaellig'), (ids[1], 'ok')):
                            page.locator(f'[data-fr-row="{rid}"] select[data-fr-key="verdict"]').select_option(verdict)
                            page.wait_for_load_state('networkidle')
                            page.locator(f'[data-fr-row="{rid}"] [data-fr-key="reason"]').fill('am Bildschirm geprüft')
                            page.locator(f'[data-fr-row="{rid}"] [data-fr-key="evidence"]').fill('Screenshot Startseite')
                            page.locator(f'[data-fr-row="{rid}"] [data-fr-key="evidence"]').press('Tab')
                            page.wait_for_load_state('networkidle')
                        page.wait_for_function('() => !document.querySelector("[data-fr-missing]")')
                        # „Abbruch“: Seite neu laden – Eingaben sind gespeichert
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        page.locator('#frBox > summary').click()
                        page.locator('[data-fr-open]').first.click()
                        page.locator(f'[data-fr-row="{ids[0]}"] [data-fr-key="reason"]').wait_for()
                        self.assertEqual(page.input_value(f'[data-fr-row="{ids[0]}"] [data-fr-key="reason"]'), 'am Bildschirm geprüft')
                        page.locator('#frComplete').click()
                        page.locator('#frReview', has_text='abgeschlossen').wait_for()
                        page.locator('[data-fr-cal="A1"]', has_text='100 %').wait_for()
                        page.locator('[data-fr-cal="A3"]', has_text='0 %').wait_for()
                        req = urllib.request.Request(base + '/api/fachreview', headers={'Origin': base})
                        self.assertEqual(json.loads(urllib.request.urlopen(req).read())['calibration']['completed_reviews'], 1)
                        self.assertEqual(outside, [])
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
