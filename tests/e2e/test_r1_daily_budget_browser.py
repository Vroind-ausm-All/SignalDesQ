"""Browserprüfung R1.4 (2.0.0-dev71): Einstellungen → Datenquellen → „Website-Abruf & Auswertung“ zeigt das Tagesbudget der
Organisation mit heutigem Stand und speichert eine neue Grenze. Keine Abfrage nach außen."""
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
from sales_tool.research import budget
from sales_tool.research import settings as rsettings
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class DailyBudgetBrowserTests(unittest.TestCase):
    def tearDown(self):
        rsettings.reset()
        budget.reset_usage()

    def test_daily_budget_is_shown_and_saved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'daily.sqlite3'
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
                        select = page.locator('#rtForm select[name="daily_pages"]')
                        select.wait_for()
                        self.assertEqual(select.input_value(), '0')
                        page.wait_for_function('() => (document.querySelector("#rtDaily")?.textContent || "").includes("Heute 0 Seiten")')
                        select.select_option('200')
                        page.locator('#rtForm button[type=submit]').click()
                        page.wait_for_function('() => (document.querySelector("#rtDaily")?.textContent || "").includes("von 200 Seiten")')
                        with connect(db) as conn:
                            self.assertEqual(rsettings.get_setting_safe(conn)['daily_pages'], 200)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
