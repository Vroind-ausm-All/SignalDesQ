"""Browserprüfung 2.0.0-dev13 (Produktreview M01/M03/M04, Abnahmefälle T02–T04):
- T04: Notiz eingeben und Escape drücken → Rückfrage; „Weiter bearbeiten“ behält den Text, „Verwerfen“ löscht ihn bewusst,
  „Speichern“ speichert über das vorhandene Formular.
- Verlässt man den Dialog über einen Sprung in eine andere Ansicht, kommt die Eingabe beim nächsten Öffnen zurück.
- T03: Eine bestehende Firma öffnet im Überblick mit Fokus auf dem Reiter, eine neue Firma im Namensfeld; nach dem
  Schließen liegt der Fokus wieder auf der Zeile.
- T02: Eine neue Firma nur mit Namen bekommt keine Branche und keine Leistung; die Liste zeigt Passung statt Punktzahl.
Fiktive Firmen, keine Abrufe nach außen."""
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


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class FormGuardBrowserTests(unittest.TestCase):
    def test_unsaved_input_focus_and_neutral_defaults(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'g.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Beispiel Malerbetrieb', 'location': 'Stuttgart 70191', 'stage': 'qualifiziert'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 768})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base)
                        page.locator('.sidebar [data-view="leads"]').click()
                        row = page.locator('#leadRows tr', has_text='Beispiel Malerbetrieb')
                        row.wait_for()

                        def open_lead():
                            row.focus()
                            page.keyboard.press('Enter')
                            page.locator('#leadTabs').wait_for(state='visible')
                            page.wait_for_function('() => document.activeElement && document.activeElement.dataset.lfTab === "ueberblick"')

                        # T03: Überblick mit Fokus auf dem Reiter, nicht im Namensfeld
                        open_lead()
                        # T04: Notiz tippen, Escape → Rückfrage, Text bleibt
                        page.locator('[data-lf-tab="kontakt"]').click()
                        page.fill('#activityForm [name=detail]', 'Rückruf zugesagt, Freitag 10 Uhr')
                        self.assertIn('Aktivitätsprotokoll', page.text_content('#lfDirty'))
                        page.keyboard.press('Escape')
                        page.locator('#lfGuard').wait_for(state='visible')
                        if SHOTS:
                            page.screenshot(path=str(Path(SHOTS) / 'rueckfrage.png'))
                        page.locator('[data-guard="edit"]').click()
                        self.assertFalse(page.locator('#lfGuard').is_visible())
                        self.assertTrue(page.locator('#modal').is_visible())
                        self.assertEqual(page.input_value('#activityForm [name=detail]'), 'Rückruf zugesagt, Freitag 10 Uhr')
                        self.assertEqual(page.evaluate('() => document.activeElement.name'), 'detail')

                        # Escape im Rückfrage-Dialog heißt „weiter bearbeiten“
                        page.keyboard.press('Escape')
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.keyboard.press('Escape')
                        self.assertFalse(page.locator('#lfGuard').is_visible())
                        self.assertTrue(page.locator('#modal').is_visible())

                        # Sprung in eine andere Ansicht: Eingabe bleibt im Arbeitsspeicher und kommt beim Öffnen zurück
                        page.evaluate('() => { closeModal(); switchView("pipeline"); }')
                        self.assertFalse(page.locator('#modal').is_visible())
                        page.locator('.sidebar [data-view="leads"]').click()
                        open_lead_restore = row.locator('td').first
                        open_lead_restore.click()
                        page.locator('#leadTabs').wait_for(state='visible')
                        self.assertEqual(page.locator('[data-lf-tab][aria-selected="true"]').get_attribute('data-lf-tab'), 'kontakt')
                        self.assertEqual(page.input_value('#activityForm [name=detail]'), 'Rückruf zugesagt, Freitag 10 Uhr')

                        # Speichern über die Rückfrage legt die Aktivität an und schließt
                        page.locator('#closeModal').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.locator('[data-guard="save"]').click()
                        page.locator('#modal').wait_for(state='hidden', timeout=15000)
                        acts = api(f"/activities?lead_id={lead['id']}")
                        self.assertTrue(any('Freitag 10 Uhr' in (a.get('detail') or '') for a in acts), acts)
                        # T03: Fokus zurück auf der Zeile
                        page.wait_for_function('() => document.activeElement && document.activeElement.matches("#leadRows tr")')

                        # Verwerfen: Text ist weg, keine Wiederherstellung
                        open_lead()
                        page.locator('[data-lf-tab="stammdaten"]').click()
                        page.fill('#leadForm [name=location]', 'Esslingen')
                        page.keyboard.press('Escape')
                        page.locator('[data-guard="discard"]').click()
                        page.locator('#modal').wait_for(state='hidden')
                        open_lead()
                        page.locator('[data-lf-tab="stammdaten"]').click()
                        self.assertEqual(page.input_value('#leadForm [name=location]'), 'Stuttgart 70191')
                        self.assertTrue(page.locator('#lfDirty').is_hidden())
                        page.keyboard.press('Escape')  # nichts geändert → schließt ohne Rückfrage
                        page.locator('#modal').wait_for(state='hidden')

                        # T02: neue Firma nur mit Namen – keine Branche, keine Leistung; Fokus im Namensfeld
                        page.locator('#newLeadBtn').click()
                        page.wait_for_function('() => document.activeElement && document.activeElement.name === "company"')
                        self.assertEqual(page.input_value('#leadForm [name=industry]'), '')
                        self.assertEqual(page.input_value('#leadForm [name=offer]'), '')
                        page.fill('#leadForm [name=company]', 'Probe Architekten')
                        page.locator('#leadForm button[type=submit]').click()
                        page.locator('#modal').wait_for(state='hidden')
                        created = next(x for x in api('/leads') if x['company'] == 'Probe Architekten')
                        self.assertEqual((created['industry'], created['offer']), ('', ''))
                        new_row = page.locator('#leadRows tr', has_text='Probe Architekten')
                        self.assertIn('Branche unbekannt', new_row.text_content())
                        self.assertIn('noch nicht gewählt', new_row.text_content())
                        self.assertNotIn('/100', page.text_content('#leadRows'))
                        new_row.locator('.fit-cell').locator('text=Datenlage unzureichend').wait_for()

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
