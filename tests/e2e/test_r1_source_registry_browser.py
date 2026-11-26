"""Browserprüfung R1.1: Einstellungen → Datenquellen → „Freigaben (Source Registry)“ zeigt je Quelle den Prüfstand und schaltet
eine erlaubte Quelle aus; gesperrte Quellen haben keinen Schalter. Keine Abfrage nach außen."""
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

from sales_tool.research import sources
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class SourceRegistryBrowserTests(unittest.TestCase):
    def tearDown(self):
        sources.reset()

    def test_registry_lists_review_and_switches_a_source_off(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'src.sqlite3'
            prepare_database(db)
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
                        page.goto(base + '/#/einstellungen')
                        page.wait_for_load_state('networkidle')
                        page.locator('[data-settings-jump="datenquellen"]').click()
                        page.locator('#srcBox > summary').click()
                        gleif = page.locator('[data-src-row="gleif"]')
                        gleif.wait_for()
                        self.assertIn('freigegeben', gleif.inner_text())
                        self.assertIn('CC0 1.0', gleif.inner_text())
                        linkedin = page.locator('[data-src-row="linkedin_xing"]')
                        self.assertIn('nur manuell', linkedin.inner_text())
                        self.assertEqual(linkedin.locator('[data-src-toggle]').count(), 0, 'gesperrte Quelle ohne Schalter')
                        self.assertIn('6 von 10 Quellen an', page.locator('#srcSummary').inner_text())
                        gleif.locator('[data-src-toggle]').click()
                        page.wait_for_function('() => (document.querySelector(\'[data-src-row="gleif"] [data-src-toggle]\')?.textContent || "") === "Einschalten"')
                        self.assertIn('aus', gleif.inner_text())
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
