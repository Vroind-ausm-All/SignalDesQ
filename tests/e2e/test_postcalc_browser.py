"""Browserprüfung 2.0.0-dev5: Zeit erfassen, Auftrag abschließen, Urteil sehen; Auslastung auf „Heute“ folgt.
Lokale, fiktive Testdaten; keine Netzabfragen."""
import json
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

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class PostcalcBrowserTests(unittest.TestCase):
    def test_log_time_close_project_and_capacity_follows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'p.sqlite3'
            with connect(db) as conn:
                init_db(conn)
                conn.execute("INSERT INTO leads(company, stage) VALUES ('Elektro Fiktiv e.K.', 'gewonnen')")
                conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, number) VALUES (1, 'angenommen', ?, ?, 'AN-2026-0001')",
                             (json.dumps({'estimated_hours': 20, 'external_cost_eur': 100, 'min_hourly_earning': 66}),
                              json.dumps({'net_eur': 2000, 'project_label': 'Website-Relaunch'})))
                conn.commit()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1400, 'height': 1000})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        page.locator('#rcCap', has_text='Zugesagt 20 h').wait_for(timeout=15000)  # ohne Zeiten: volle Kalkulation

                        page.locator('[data-view="quotes"]').click()
                        card = page.locator('.pk-card', has_text='Elektro Fiktiv')
                        card.wait_for(timeout=15000)
                        self.assertIn('keine Zeiten', card.inner_text())
                        card.locator('[data-pk-form] input[name="hours"]').fill('12.5')
                        card.locator('[data-pk-form] input[name="note"]').fill('Konzept und Gestaltung')
                        card.locator('[data-pk-form] button[type="submit"]').click()
                        page.locator('.pk-card', has_text='7,5 von 20 kalkulierten Stunden übrig').wait_for(timeout=15000)
                        if SHOTS:
                            page.locator('#nachkalkulation').screenshot(path=str(Path(SHOTS) / 'nachkalkulation.png'))

                        card.locator('[data-pk-close] input[name="ext"]').fill('150')
                        card.locator('[data-pk-close] button[type="submit"]').click()
                        done = page.locator('.pk-card.done', has_text='Hat sich gelohnt')
                        done.wait_for(timeout=15000)
                        self.assertIn('148,00', done.inner_text())  # (2000 − 150) / 12,5

                        page.locator('[data-view="dashboard"]').click()
                        page.locator('#rcCap', has_text='Zugesagt 0 h').wait_for(timeout=15000)  # abgeschlossen zählt nicht mehr
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
