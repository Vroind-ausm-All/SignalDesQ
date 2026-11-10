"""Browserprüfung des gespeicherten Leistungsprofils (lokale Testdaten)."""
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

from sales_tool.model import connect, init_db
from sales_tool.server import make_handler


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ServiceProfileBrowserTests(unittest.TestCase):
    def test_profile_is_editable_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'profile.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1400, 'height': 900})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        page.locator('.nav-more summary').click()
                        page.locator('[data-view="quality"]').click()
                        campaign = page.locator('#serviceProfileThemes [data-service-theme="campaign"] [data-keywords]')
                        campaign.wait_for(timeout=15000)
                        page.locator('#serviceProfileForm input[name="name"]').fill('Agenturprofil')
                        campaign.fill('Kundentag, Fachmesse')
                        page.locator('#serviceProfileThemes [data-service-theme="recruiting"] [data-enabled]').uncheck()
                        page.locator('#serviceProfileForm button[type="submit"]').click()
                        page.wait_for_function("""async () => {
                          const p = await (await fetch('/api/research/service-profile')).json();
                          return p.profile.name === 'Agenturprofil' && !p.profile.themes.recruiting.enabled
                            && p.profile.themes.campaign.keywords.includes('Kundentag');
                        }""", timeout=15000)
                        page.reload()
                        page.locator('.nav-more summary').click()
                        page.locator('[data-view="quality"]').click()
                        campaign.wait_for(timeout=15000)
                        self.assertEqual(page.locator('#serviceProfileForm input[name="name"]').input_value(), 'Agenturprofil')
                        self.assertFalse(page.locator('#serviceProfileThemes [data-service-theme="recruiting"] [data-enabled]').is_checked())
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
