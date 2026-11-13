"""Browserprüfung 2.0.0-dev18 (Produktreview M13 Teil 1, Abnahmefall T08 in der Oberfläche):
- Firmenakte → Bedarf & Angebot zeigt die Chancen; eine zweite Chance mit eigenem Anliegen lässt sich anlegen.
- „Verloren“ verlangt einen Grund; der Verlust der zweiten Chance lässt die erste offen.
- Angebot und Termin bieten die offenen Chancen der gewählten Firma zur Auswahl an.
Fiktive Firma, keine Abrufe nach außen."""
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

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ChancesBrowserTests(unittest.TestCase):
    def test_two_chances_in_file_offer_and_meeting(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ch.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Zwei Projekte Fiktiv GmbH', 'stage': 'kontakt'})
            api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Markenauftritt',
                                                 'positions': [{'service': 'logo', 'size': 'M'}]})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(f"{base}/#/firmen?firma={lead['id']}")
                        page.locator('#leadTabs').wait_for(state='visible')
                        page.locator('[data-lf-tab="bedarf"]').click()
                        items = page.locator('#chList .ch-item')
                        items.first.wait_for()
                        self.assertEqual(items.count(), 1)
                        self.assertIn('Markenauftritt', items.first.inner_text())
                        self.assertIn('Bedarfsanalyse unten', items.first.inner_text())

                        # zweite Chance mit eigenem Anliegen
                        page.locator('#chNewBtn').click()
                        page.fill('#chNewForm [name=title]', 'Kundenportal')
                        page.select_option('#chNewForm [name=offer]', 'portal')
                        page.fill('#chNewForm [name=problem]', 'Statusanfragen kommen per Telefon')
                        page.locator('#chNewForm button[type=submit]').click()
                        page.wait_for_function('() => document.querySelectorAll("#chList .ch-item").length === 2')
                        ids = {c['title']: c['id'] for c in api(f"/leads/{lead['id']}/chances")['chances']}
                        second = page.locator(f'#chList [data-ch="{ids["Kundenportal"]}"]')  # Auswahllisten enthalten ähnliche Texte
                        self.assertIn('Statusanfragen kommen per Telefon', second.inner_text())
                        self.assertEqual(len(api('/leads')), 1, 'keine zweite Firma angelegt')

                        # verloren nur mit Grund; die erste Chance bleibt offen
                        second.locator('[name=stage]').select_option('verloren')
                        second.locator('button[type=submit]').click()
                        page.wait_for_function('() => document.querySelector("#toast").textContent.includes("Verlustgrund")')
                        second.locator('[name=lost_reason]').select_option('kein_budget')
                        second.locator('button[type=submit]').click()
                        page.locator(f'#chList [data-ch="{ids["Kundenportal"]}"] summary .pill.bad').wait_for()
                        first = page.locator(f'#chList [data-ch="{ids["Markenauftritt"]}"]')
                        self.assertIn('Bedarf klären', first.locator('summary').inner_text())
                        if SHOTS:
                            page.locator('.ch-panel').screenshot(path=str(Path(SHOTS) / 'chancen.png'))
                        page.locator('#closeModal').click()

                        # Angebot: Chance zur Auswahl
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.select_option('#quoteForm [name=lead_id]', str(lead['id']))
                        sel = page.locator('#quoteForm [name=opportunity_id]')
                        page.wait_for_function('() => document.querySelectorAll("#quoteForm [name=opportunity_id] option").length === 2')
                        opts = sel.locator('option').all_inner_texts()
                        self.assertTrue(opts[0].startswith('Markenauftritt'), opts)
                        self.assertIn('neue Chance', opts[1])

                        # Termin: Chance zur Auswahl
                        page.goto(base + '/#/heute/kontakt-termine')
                        page.wait_for_load_state('networkidle')
                        page.select_option('#wsMeetingForm [name=lead_id]', str(lead['id']))
                        page.wait_for_function('() => [...document.querySelectorAll("#wsMeetingForm [name=opportunity_id] option")].some(o => o.textContent.startsWith("Markenauftritt"))')

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
