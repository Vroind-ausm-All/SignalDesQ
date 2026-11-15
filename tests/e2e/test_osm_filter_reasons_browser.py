"""Browserprüfung 2.0.0-dev44 (Befund mit dem Stuttgart-Auszug): Sucht man ohne „auch Betriebe ohne Rechtsform“, zeigt die
Ergebniszeile, warum Treffer ausgefiltert wurden, und ein Hinweis erklärt den Haken. Fiktive Betriebe, nur 127.0.0.1."""
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
from sales_tool.research import jobs
from sales_tool.server import make_handler

PBF = Path(__file__).resolve().parent.parent / 'fixtures' / 'osm' / 'beispiel.osm.pbf'


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class OsmFilterReasonBrowserTests(unittest.TestCase):
    def test_reasons_and_sole_hint(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'r.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1400, 'height': 1100})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        page.locator('[data-view="finder"]').click()
                        page.locator('#swForm input[name="place"]').fill('70191')
                        page.locator('#swForm select[name="radius_km"]').select_option('0')
                        page.locator('#osmBox > summary').click()
                        page.locator('#osmFile').set_input_files(str(PBF))
                        page.locator('#osmState', has_text='6 Betriebe').wait_for(timeout=30000)
                        for src in ('gleif', 'wikidata', 'ted'):
                            page.locator(f'#swForm input[name="src"][value="{src}"]').uncheck()
                        page.locator('#swForm input[name="include_sole"]').uncheck()
                        page.locator('#swForm input[name="find_websites"]').uncheck()
                        page.locator('#swGo').click()
                        hint = page.locator('[data-sw-sole-hint]')
                        hint.wait_for(timeout=30000)
                        self.assertIn('keine Rechtsform', hint.inner_text())
                        self.assertIn('ohne Rechtsform)', page.locator('#swProgress').inner_text())
                        self.assertEqual(outside, [])
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                jobs.stop_all_workers()


if __name__ == '__main__':
    unittest.main()
