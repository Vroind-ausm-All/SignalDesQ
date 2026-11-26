"""Browserprüfung 2.0.0-dev66: Schnelle Klicks unter Darstellung (Theme, dann Dichte) dürfen sich nicht überholen.
Die Antwort auf die erste Speicheranfrage wird im Browser absichtlich verzögert; vorher setzte sie die Dichte zurück
(in der CI als wackeliger test_appearance_browser aufgefallen). Keine Abrufe nach außen."""
import json
import os
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

from sales_tool.server import make_handler, prepare_database

SLOW_THEME_ANSWER = """(() => { const f = window.fetch; window.fetch = async (u, o) => { const r = await f(u, o);
  if (o && o.method === 'PUT' && String(o.body).includes('theme')) await new Promise(res => setTimeout(res, 800)); return r; }; })();"""


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AppearanceRaceBrowserTests(unittest.TestCase):
    def test_late_answer_does_not_reset_later_choice(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ap.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page()
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.add_init_script(SLOW_THEME_ANSWER)
                        page.goto(base)
                        page.wait_for_load_state('networkidle')
                        page.locator('.sidebar [data-view="settings"]').click()
                        page.locator('#esNav [data-settings-jump="darstellung"]').click()
                        page.locator('[data-ap-theme="sand"]').click()
                        page.locator('[data-ap-density="kompakt"]').click()  # bevor die erste Antwort da ist
                        page.wait_for_timeout(2000)
                        page.wait_for_load_state('networkidle')
                        root = page.evaluate('[document.documentElement.dataset.theme, document.documentElement.dataset.density]')
                        self.assertEqual(root, ['sand', 'kompakt'])
                        self.assertEqual(page.locator('[data-ap-density="kompakt"]').get_attribute('aria-pressed'), 'true')
                        with urllib.request.urlopen(base + '/api/ui/appearance') as r:
                            stored = json.load(r)['appearance']
                        self.assertEqual((stored['theme'], stored['density']), ('sand', 'kompakt'))
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
