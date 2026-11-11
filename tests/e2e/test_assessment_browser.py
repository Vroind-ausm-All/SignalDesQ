"""Browserprüfung 2.0.0-dev2: Zielkundenprofil speichern, Bewertung in Liste und Firmenakte, „nicht erreicht“ mit
Wiedervorlage, „verloren“ nur mit Grund. Lokale, fiktive Testdaten; keine Netzabfragen."""
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

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')  # optional: Ordner für Bildschirmfotos


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AssessmentBrowserTests(unittest.TestCase):
    def test_profile_grade_missed_call_and_lost_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'a.sqlite3'
            with connect(db) as conn:
                init_db(conn)
                conn.execute("""INSERT INTO leads(company, location, employees, legal_form, stage, business_phone, street, zip, city)
                                VALUES ('Elektro Fiktiv e.K.', '70173 Stuttgart', 6, 'e.K.', 'kontakt', '0711 000000', 'Musterweg 1', '70173', 'Stuttgart')""")
                conn.execute("INSERT INTO leads(company, location, employees) VALUES ('Zahnarztpraxis Nord GmbH', '20095 Hamburg', 400)")
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

                        # 1. Zielkundenprofil einstellen
                        page.locator('.nav-more summary').click()
                        page.locator('[data-view="quality"]').click()
                        form = page.locator('#targetProfileForm')
                        form.locator('input[name="home"]').fill('70173')
                        form.locator('summary').click()
                        page.locator('#targetIndustries [data-tp="elektro"]').select_option('ziel')
                        form.locator('button[type="submit"]').click()
                        page.wait_for_function("""async () => {
                          const p = (await (await fetch('/api/profile/target')).json()).profile;
                          return p.home === '70173' && p.industries.includes('elektro');
                        }""", timeout=15000)
                        if SHOTS:
                            page.locator('#targetProfile').screenshot(path=str(Path(SHOTS) / 'profil.png'))

                        # 2. Note in der Lead-Liste
                        page.locator('[data-view="leads"]').click()
                        row = page.locator('#leadRows tr', has_text='Elektro Fiktiv')
                        row.locator('.as-grade.ok').wait_for(timeout=15000)
                        self.assertEqual(row.locator('.as-grade').inner_text(), 'A')

                        # 3. Bewertung in der Firmenakte
                        row.click()
                        box = page.locator('#lfAssessment')
                        box.wait_for(timeout=15000)
                        text = box.inner_text()
                        for expected in ('Vorrangig kontaktieren', 'Passung', 'Qualifizierung', 'Erreichbarkeit', 'noch kein Gespräch', '0711 000000', '§ 7 UWG'):
                            self.assertIn(expected, text)
                        if SHOTS:
                            box.screenshot(path=str(Path(SHOTS) / 'bewertung.png'))
                        page.locator('#closeModal').click()

                        # 4. „Nicht erreicht“ erzeugt eine Wiedervorlage zu anderer Tageszeit
                        page.locator('[data-view="workspace"]').click()
                        call = page.locator('#wsCallForm')
                        call.locator('select[name="lead_id"]').select_option(label='Elektro Fiktiv e.K.')
                        call.locator('select[name="outcome"]').select_option('nicht_erreicht')
                        call.locator('select[name="slot"]').select_option('vormittag')
                        call.locator('button[type="submit"]').click()
                        page.wait_for_function("""async () => {
                          const t = await (await fetch('/api/tasks')).json();
                          return t.some(x => x.title.startsWith('Erneut anrufen (2. Versuch) – diesmal nachmittags'));
                        }""", timeout=15000)

                        # 5. „verloren“ nur mit Grund: Abbrechen ändert nichts, mit Grund wird gespeichert
                        page.locator('[data-view="pipeline"]').click()
                        page.locator('[data-pc-toggle]').first.click()  # Karte aufklappen
                        sel = page.locator('[data-pipeline-update]').first
                        sel.wait_for(timeout=15000)
                        lead_id = sel.get_attribute('data-pipeline-update')
                        sel.select_option('verloren')
                        dlg = page.locator('#lostDialog')
                        dlg.wait_for(state='visible', timeout=15000)
                        page.locator('#lostCancel').click()
                        dlg.wait_for(state='hidden', timeout=15000)
                        stage = page.evaluate(f"async () => (await (await fetch('/api/leads/{lead_id}')).json()).stage")
                        self.assertNotEqual(stage, 'verloren')
                        page.locator(f'[data-pipeline-update="{lead_id}"]').select_option('verloren')
                        dlg.wait_for(state='visible', timeout=15000)
                        dlg.locator('select[name="lost_reason"]').select_option('preis')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'verloren.png'))
                        dlg.locator('button[type="submit"]').click()
                        page.wait_for_function(f"""async () => {{
                          const l = await (await fetch('/api/leads/{lead_id}')).json();
                          return l.stage === 'verloren' && l.lost_reason === 'preis';
                        }}""", timeout=15000)
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
