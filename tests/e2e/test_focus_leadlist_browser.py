"""Browserprüfung 2.0.0-dev15 (Produktreview M08, M09, M11; Abnahmefall T01):
- Heute zeigt oben die nächsten Schritte mit Grund und Frist; die überfällige Zusage steht vorn und öffnet die Firma.
- Die Erste-Schritte-Karte prüft echte Daten und bleibt nach dem Ausblenden ausgeblendet.
- Firmenliste: Arbeitsansichten mit Trefferzahl, aktive Filter sichtbar, Ansicht in der Adresse; eigene Ansicht speichern,
  wieder öffnen und löschen; leerer Filter sagt, dass nur der Filter nichts liefert; Spalten zuschaltbar.
- Start auch dann ohne Fehler, wenn ein Skript langsam lädt (Regression „renderPipeline is not defined“).
Fiktive Firmen, keine Abrufe nach außen."""
import datetime as dt
import json
import os
import tempfile
import threading
import time
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


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class FocusLeadListBrowserTests(unittest.TestCase):
    def test_focus_onboarding_and_work_views(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'v.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, body):
                req = urllib.request.Request(base + '/api' + path, method='POST', headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode())
                return json.loads(urllib.request.urlopen(req).read())

            today = dt.date.today()
            api('/leads', {'company': 'Zusage Fiktiv e.K.', 'stage': 'kontakt', 'next_step': 'Unterlagen schicken',
                           'next_date': (today - dt.timedelta(days=1)).isoformat()})
            api('/leads', {'company': 'Heute Fiktiv OHG', 'stage': 'antwort', 'next_step': 'Rückruf bestätigen', 'next_date': today.isoformat()})
            api('/leads', {'company': 'Ohne Schritt Fiktiv KG', 'stage': 'kontakt'})
            api('/leads', {'company': 'Recherche Fiktiv GmbH', 'stage': 'recherche'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)

                        def slow(route):  # ein spätes Skript: Der Start darf trotzdem nicht ohne renderPipeline loslaufen
                            time.sleep(1.2)
                            route.continue_()
                        page.route('**/pipeline.js', slow)
                        page.goto(base)
                        page.wait_for_load_state('networkidle')
                        self.assertEqual(errors, [], 'Start bei langsam ladendem Skript')
                        page.unroute('**/pipeline.js')

                        # M08 / T01: wichtigste Aufgabe ohne Suche erkennbar
                        first = page.locator('#tdFocusList .td-focus-item').first
                        first.wait_for(timeout=15000)
                        self.assertIn('Zusage Fiktiv e.K.', first.inner_text())
                        self.assertIn('überfällig', first.inner_text())
                        self.assertIn('Heute Fiktiv OHG', page.locator('#tdFocusList .td-focus-item').nth(1).inner_text())
                        if SHOTS:
                            page.locator('#tdFocus').screenshot(path=str(Path(SHOTS) / 'fokus.png'))
                        first.locator('button').click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertEqual(page.text_content('#modalTitle'), 'Zusage Fiktiv e.K.')
                        page.locator('#closeModal').click()
                        page.locator('#modal').wait_for(state='hidden')

                        # M11: Erste Schritte – echte Prüfung, ausblendbar
                        onb = page.locator('#tdOnboarding')
                        self.assertTrue(onb.is_visible())
                        self.assertIn('1 von 4 erledigt', page.text_content('#tdOnbState'))  # Firmen sind schon da
                        page.locator('#tdOnbHide').click()
                        onb.wait_for(state='hidden')
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        self.assertFalse(page.locator('#tdOnboarding').is_visible())

                        # M09: Arbeitsansichten
                        page.locator('.sidebar [data-area="firmen"]').click()
                        chip = page.locator('[data-ll-preset="heute"]')
                        self.assertIn('2', chip.inner_text())
                        chip.click()
                        rows = page.locator('#leadRows tr')
                        self.assertEqual(rows.count(), 2)
                        self.assertIn('Zusage Fiktiv', rows.first.inner_text())  # überfällig zuerst
                        self.assertIn('2 von 4 Firmen', page.text_content('#leadFilterInfo'))
                        self.assertIn('Heute fällig', page.text_content('#leadFilterInfo'))
                        self.assertIn('ansicht=heute', page.url)
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        self.assertEqual(page.locator('[data-ll-preset="heute"]').get_attribute('aria-pressed'), 'true')
                        self.assertEqual(page.locator('#leadRows tr').count(), 2)
                        page.locator('[data-ll-preset="ohne_schritt"]').click()
                        self.assertEqual([t.split('\n')[0] for t in page.locator('#leadRows tr td:first-child b').all_inner_texts()], ['Ohne Schritt Fiktiv KG'])

                        # eigene Ansicht speichern, wieder öffnen, löschen
                        page.locator('[data-ll-preset="heute"]').click()
                        page.fill('#leadSearch', 'Zusage')
                        page.once('dialog', lambda d: d.accept('Meine Zusagen'))
                        page.locator('[data-ll-save]').click()
                        saved = page.locator('[data-ll-view]', has_text='Meine Zusagen')
                        saved.wait_for()
                        page.locator('[data-ll-reset]').first.click()
                        self.assertEqual(page.locator('#leadRows tr').count(), 4)
                        saved.click()
                        self.assertEqual(page.input_value('#leadSearch'), 'Zusage')
                        self.assertEqual(page.locator('#leadRows tr').count(), 1)
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        page.locator('[data-ll-view]', has_text='Meine Zusagen').wait_for()
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'firmenliste.png'))
                        page.once('dialog', lambda d: d.accept())
                        page.locator('[data-ll-del="0"]').click()
                        page.locator('[data-ll-view]').first.wait_for(state='detached')

                        # Leerer Filter ≠ keine Firmen; Spalten zuschaltbar
                        page.fill('#leadSearch', 'gibt es nicht')
                        self.assertIn('Keine Firma passt zu diesen Filtern.', page.text_content('#leadRows'))
                        page.locator('#leadRows [data-ll-reset]').click()
                        self.assertEqual(page.locator('#leadRows tr').count(), 4)
                        page.check('[data-ll-col="signal"]')
                        self.assertIn('KAUFSIGNAL', page.text_content('#leadHead'))
                        page.reload()
                        page.wait_for_load_state('networkidle')
                        self.assertIn('KAUFSIGNAL', page.text_content('#leadHead'))  # bleibt in diesem Browser gemerkt

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
