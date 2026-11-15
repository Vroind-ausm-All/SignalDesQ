"""Browserprüfung 2.0.0-dev45 (Produktreview M21): Unter „Finden“ eine Stichprobe ziehen, Firmen von Hand bewerten,
Quoten aktualisieren sich, Export ist verlinkt. Auf Smartphone-Breite kein waagerechtes Scrollen. Fiktive Firmen, nur 127.0.0.1."""
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

from sales_tool import sweep as sw
from sales_tool.model import connect
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class PilotBrowserTests(unittest.TestCase):
    def test_draw_mark_and_metrics(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'pl.sqlite3'
            prepare_database(db)
            conn = connect(str(db))
            run = sw._run_record(conn, 'osm', None, {})
            for i in range(25):
                conn.execute("""INSERT INTO discovery_candidates(run_id, source, name, website, zip, city, industry)
                                VALUES (?, 'osm', ?, ?, '70191', 'Stuttgart', 'Maler')""", (run, f'Malerbetrieb {i:02d} Fiktiv', f'maler{i}.example'))
            conn.commit()
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
                        page.goto(base + '/#/finden')
                        page.wait_for_load_state('networkidle')
                        page.locator('#plBox > summary').click()
                        page.locator('#plSource option[value="osm"]').wait_for(state='attached')
                        page.select_option('#plSize', '20')
                        page.locator('#plDraw button[type=submit]').click()
                        page.locator('[data-pl-row]').first.wait_for()
                        self.assertEqual(page.locator('[data-pl-row]').count(), 20)
                        first = page.locator('[data-pl-row]').first
                        rid = first.get_attribute('data-pl-row')
                        for key, value in (('target', 'ja'), ('website', 'richtig'), ('has_site', 'ja'), ('industry', 'richtig')):
                            page.locator(f'[data-pl-row="{rid}"] input[data-pl-key="{key}"][value="{value}"]').check()
                            page.wait_for_function(f'() => document.querySelector(\'[data-pl-row="{rid}"] input[data-pl-key="{key}"][value="{value}"]\')?.checked')
                            page.wait_for_load_state('networkidle')
                        page.locator('[data-pl-metric="website_precision"]', has_text='100 %').wait_for()
                        self.assertIn('1 von 1', page.locator('[data-pl-metric="website_precision"]').inner_text())
                        self.assertIn('pl-done', page.locator(f'[data-pl-row="{rid}"]').get_attribute('class'))
                        # zweite Firma: kein Zielbetrieb → Fragen zur Website entfallen
                        second = page.locator('[data-pl-row]').nth(1).get_attribute('data-pl-row')
                        page.locator(f'[data-pl-row="{second}"] input[data-pl-key="target"][value="nein"]').check()
                        page.wait_for_function(f'() => !document.querySelector(\'[data-pl-row="{second}"] input[data-pl-key="website"]\')')
                        page.locator('[data-pl-metric="target_share"]', has_text='50 %').wait_for()
                        self.assertTrue(page.locator('#plSample a[href$="/export.csv"]').is_visible())
                        page.set_viewport_size({'width': 390, 'height': 844})
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 391)
                        self.assertEqual(outside, [])
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
