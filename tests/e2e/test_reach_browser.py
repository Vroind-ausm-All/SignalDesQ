"""Browserprüfung 2.0.0-dev3: Eingang festhalten und erledigen, Kontaktliste und Auslastung auf „Heute“, Note in der
Pipeline, eigene Zeiten speichern. Lokale, fiktive Testdaten; keine Netzabfragen."""
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

from sales_tool import qualification
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ReachBrowserTests(unittest.TestCase):
    def test_inbound_contact_list_pipeline_and_own_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'r.sqlite3'
            with connect(db) as conn:
                init_db(conn)
                qualification.save(conn, {**qualification.default_profile(), 'industries': ['elektro'], 'home': '70173'})
                conn.execute("""INSERT INTO leads(company, employees, legal_form, stage, business_phone, zip, city)
                                VALUES ('Elektro Fiktiv e.K.', 6, 'e.K.', 'kontakt', '0711 000000', '70173', 'Stuttgart')""")
                conn.execute("INSERT INTO leads(company, employees, stage, zip, city) VALUES ('Kanzlei Fern AG', 900, 'kontakt', '20095', 'Hamburg')")
                conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json) VALUES (1, 'gesendet_manuell', ?, '{}')",
                             (json.dumps({'estimated_hours': 40}),))
                conn.commit()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1400, 'height': 1100})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                        page.goto(f'http://127.0.0.1:{server.server_port}')

                        # 1. Kontaktliste: A-Firma ja, C-Firma nein; Auslastung genannt
                        page.locator('#rcList .td-item', has_text='Elektro Fiktiv').wait_for(timeout=15000)
                        self.assertEqual(page.locator('#rcList .td-item', has_text='Kanzlei Fern').count(), 0)
                        self.assertIn('keine Werbeerlaubnis', page.locator('#rcListNote').inner_text())
                        self.assertIn('angeboten 40 h', page.locator('#rcCap').inner_text())

                        # 2. Verpassten Anruf festhalten → erscheint mit Frist → erledigen
                        form = page.locator('#rcInForm')
                        form.locator('input[name="who"]').fill('Frau Beispiel, Malerbetrieb')
                        form.locator('input[name="contact"]').fill('0711 111111')
                        form.locator('button[type="submit"]').click()
                        item = page.locator('#rcInList .td-item', has_text='Frau Beispiel')
                        item.wait_for(timeout=15000)
                        self.assertIn('Rückruf bis', item.inner_text())
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'heute.png'), full_page=False)
                        item.locator('[data-rc-done]').click()
                        page.locator('#rcInList .empty').wait_for(timeout=15000)
                        self.assertIn('Rückmeldungen', page.locator('#rcInStats').inner_text())

                        # 3. Pipeline zeigt die Note auf der Karte
                        page.locator('.sidebar [data-view="leads"]').click()
                        page.locator('[data-area-view="pipeline"]').click()  # 2.0.0-dev14: Reiter im Bereich Firmen
                        card = page.locator('.pipeline-card', has_text='Elektro Fiktiv')
                        card.locator('.as-grade').wait_for(timeout=15000)
                        self.assertEqual(card.locator('.as-grade').inner_text(), 'A')

                        # 4. Eigene Zeiten speichern → Textbaustein und Terminvorschläge folgen
                        page.locator('.sidebar [data-view="settings"]').click()  # 2.0.0-dev14: eigener Bereich Einstellungen
                        av = page.locator('#availabilityForm')
                        av.locator('input[name="callback_from"]').fill('11:00')
                        av.locator('input[name="callback_to"]').fill('12:00')
                        av.locator('input[name="display_name"]').fill('Alex Muster')
                        av.locator('button[type="submit"]').click()
                        page.wait_for_function("() => document.querySelector('#avTemplates')?.innerText.includes('zwischen 11:00 und 12:00 Uhr')", timeout=15000)
                        self.assertIn('Passt einer der Termine?', page.locator('#avSlots').inner_text())
                        if SHOTS:
                            page.locator('#ownTimes').screenshot(path=str(Path(SHOTS) / 'zeiten.png'))
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
