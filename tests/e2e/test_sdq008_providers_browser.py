"""Browserprüfung SDQ-008: Die Quellenkarten unter „Einzelne Quelle gezielt abfragen“ zeigen Aktualität, Kosten und die eigenen
Messwerte (Abfragen, Fehlerrate, letzter Erfolg). Keine Abfrage nach außen – Messwerte kommen aus vorbereiteten Einträgen."""
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool.model import connect
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ProvidersBrowserTests(unittest.TestCase):
    def test_source_cards_show_freshness_cost_and_measured_values(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'pr.sqlite3'
            prepare_database(db)
            with connect(db) as conn:
                for status, err in (('done', ''), ('done', ''), ('done', ''), ('failed', 'Overpass: 504 Gateway Timeout')):
                    conn.execute("""INSERT INTO discovery_runs(source, params_json, status, result_count, error, finished_at)
                                    VALUES ('osm', '{}', ?, 5, ?, datetime('now'))""", (status, err))
                conn.commit()
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
                        page.goto(base + '/#/finden/neue-suche')
                        page.wait_for_load_state('networkidle')
                        page.locator('#lfExpert > summary').click()
                        osm = page.locator('[data-lf-measured="osm"]')
                        page.wait_for_function('() => (document.querySelector(\'[data-lf-measured="osm"]\')?.textContent || "").includes("Abfragen")')
                        text = osm.inner_text()
                        self.assertIn('Aktualität:', text)
                        self.assertIn('Kosten: kostenlos', text)
                        self.assertIn('4 Abfragen, 25 % fehlgeschlagen', text)
                        self.assertIn('zuletzt erfolgreich am', text)
                        self.assertIn('504 Gateway Timeout', osm.get_attribute('title'))
                        self.assertIn('noch keine Abfrage', page.locator('[data-lf-measured="wikidata"]').inner_text())
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
