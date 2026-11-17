"""Browserprüfung 2.0.0-dev47 (Produktreview M30/M34): Erlebnisstudie anlegen, Sitzung erfassen, erst nach der Bestätigung
„stammt von der Testperson“ zählt sie; „Was du lernst“ zeigt Grenzen. Smartphone-Breite ohne waagerechtes Scrollen.
Fiktive Firma, nur 127.0.0.1."""
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
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class StudiesBrowserTests(unittest.TestCase):
    def test_study_session_confirm_and_learning(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'st.sqlite3'
            prepare_database(db)
            conn = connect(str(db))
            conn.execute("INSERT INTO leads(company, stage) VALUES ('Studie Fiktiv GmbH', 'termin')")
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
                        page.goto(base + '/#/angebote/auswertung')  # 2.0.0-dev52: Angebote → Auswertung
                        page.wait_for_load_state('networkidle')
                        page.locator('#stBox > summary').click()
                        page.locator('#stLead option', has_text='Studie Fiktiv GmbH').wait_for(state='attached')
                        f = page.locator('#stCreate')
                        f.locator('[name=title]').fill('Website vor dem Relaunch')
                        f.locator('[name=phase]').select_option('vorher')
                        f.locator('[name=tasks]').fill('Telefonnummer finden\nTermin anfragen')
                        f.locator('[name=questions]').fill('Was hat gestört?')
                        f.locator('button[type=submit]').click()
                        page.locator('#stSessionForm').wait_for()
                        page.locator('#stSessionForm [name=device]').select_option('smartphone')
                        page.locator('#stSessionForm button[type=submit]').click()
                        sess = page.locator('details[data-st-session]').first
                        sess.wait_for()
                        sid = sess.get_attribute('data-st-session')
                        self.assertIn('zählt noch nicht', sess.inner_text())
                        # 2.0.0-dev51: Jede Eingabe speichert sofort und zeichnet die Studie danach neu. wait_for_load_state('networkidle')
                        # kehrt sofort zurück, wenn die Seite den Zustand schon einmal erreicht hatte – dann konnte das Neuzeichnen nach der
                        # zweiten Auswahl die gerade getippte Antwort überschreiben (sporadisch „Antworten (0)“). Deshalb auf das Neuzeichnen warten.
                        def changed_and_redrawn(selector, act):
                            old = page.locator(selector).element_handle()
                            act(page.locator(selector))
                            page.wait_for_function('el => !el.isConnected', arg=old)
                        out = f'select[data-st-s="{sid}"][data-st-k="outcome"]'
                        changed_and_redrawn(f'{out} >> nth=0', lambda l: l.select_option('geschafft'))
                        changed_and_redrawn(f'{out} >> nth=1', lambda l: l.select_option('nicht_geschafft'))
                        ans = f'textarea[data-st-s="{sid}"][data-st-k="answer"]'
                        changed_and_redrawn(ans, lambda l: (l.fill('Kontakt war versteckt'), l.press('Tab')))
                        self.assertEqual(page.input_value(ans), 'Kontakt war versteckt')
                        # vor der Bestätigung zählt nichts
                        self.assertIn('–', page.locator('[data-st-overall]').inner_text())
                        page.locator(f'input[data-st-s="{sid}"][data-st-k="confirmed"]').check()
                        page.locator('[data-st-overall]', has_text='50 %').wait_for()
                        self.assertIn('Erst 1 bestätigte', page.locator('[data-st-notice]').inner_text())
                        page.locator('#stDetail summary', has_text='Antworten').click()
                        self.assertIn('P1: Kontakt war versteckt', page.locator('#stDetail').inner_text())
                        page.locator('#lnBox > summary').click()
                        page.locator('#lnMethods', has_text='erst 1').wait_for()  # beim Öffnen neu geladen – auf den neuen Stand warten
                        self.assertGreater(page.locator('#lnLimits li').count(), 0)
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
