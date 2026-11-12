"""Browserprüfung 2.0.0-dev11: Darstellung umschalten – Hell/Dunkel oben, Theme und Dichte in den Einstellungen,
Wahl bleibt nach dem Neuladen erhalten, „Wie System“ folgt dem Betriebssystem. Keine Netzabfragen nach außen."""
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

from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


def _root(page, attr):
    return page.evaluate(f'document.documentElement.dataset.{attr}')


def _bg(page):
    return page.evaluate('getComputedStyle(document.body).backgroundColor')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AppearanceBrowserTests(unittest.TestCase):
    def test_switch_persist_and_follow_system(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'a.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        ctx = browser.new_context(viewport={'width': 1400, 'height': 1000}, color_scheme='light')
                        page = ctx.new_page()
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base)
                        page.wait_for_load_state('networkidle')
                        self.assertEqual((_root(page, 'theme'), _root(page, 'mode')), ('klassisch', 'light'))
                        self.assertEqual(_bg(page), 'rgb(246, 247, 244)')  # Klassisch hell wie bisher

                        page.locator('#modeToggle').click()  # oben: Hell ⇄ Dunkel
                        page.wait_for_function('() => document.documentElement.dataset.mode === "dark"')
                        page.wait_for_load_state('networkidle')

                        page.locator('.sidebar summary.nav-group').click()
                        page.locator('[data-view="quality"]').click()
                        page.locator('[data-ap-theme="sand"]').click()
                        page.wait_for_function('() => document.documentElement.dataset.theme === "sand"')
                        page.locator('[data-ap-density="kompakt"]').click()
                        page.wait_for_function('() => document.documentElement.dataset.density === "kompakt"')
                        page.wait_for_load_state('networkidle')
                        self.assertEqual(page.locator('[data-ap-theme="sand"]').get_attribute('aria-pressed'), 'true')
                        self.assertEqual(page.locator('[data-ap-mode="dunkel"]').get_attribute('aria-pressed'), 'true')
                        self.assertEqual(_bg(page), 'rgb(23, 19, 15)')  # Sand dunkel
                        if SHOTS:
                            page.locator('#darstellung').screenshot(path=str(Path(SHOTS) / 'darstellung-sand-dunkel.png'))

                        page.reload()
                        page.wait_for_load_state('networkidle')
                        self.assertEqual((_root(page, 'theme'), _root(page, 'mode'), _root(page, 'density')), ('sand', 'dark', 'kompakt'))
                        with urllib.request.urlopen(base + '/api/ui/appearance') as r:
                            self.assertEqual(json.load(r)['appearance'], {'theme': 'sand', 'mode': 'dunkel', 'density': 'kompakt'})

                        # Neuer Browser ohne lokale Kopie: die gespeicherte Wahl kommt vom Server; „Wie System“ folgt dem System.
                        fresh = browser.new_context(viewport={'width': 1200, 'height': 800}, color_scheme='dark')
                        other = fresh.new_page()
                        other.on('pageerror', lambda exc: errors.append(str(exc)))
                        other.goto(base)
                        other.wait_for_function('() => document.documentElement.dataset.theme === "sand"')
                        other.locator('#modeToggle').wait_for()
                        other.evaluate('window.SignalAppearance.set({mode: "system"})')
                        other.wait_for_load_state('networkidle')
                        self.assertEqual(_root(other, 'mode'), 'dark')
                        other.emulate_media(color_scheme='light')
                        other.wait_for_function('() => document.documentElement.dataset.mode === "light"')
                        self.assertEqual(_bg(other), 'rgb(246, 242, 235)')  # Sand hell
                        fresh.close()

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
