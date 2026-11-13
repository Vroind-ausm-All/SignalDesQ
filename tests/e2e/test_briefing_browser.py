"""Browserprüfung 2.0.0-dev20 (Produktreview M14):
- Die Chance zeigt ein Briefing mit Fragen ihrer Leistungsbereiche; Antworten als geklärt / offen speichern.
- Im Angebot übernimmt „Voraussetzungen aus dem Briefing“ geklärte Angaben und offene Voraussetzungen.
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
class BriefingBrowserTests(unittest.TestCase):
    def test_briefing_in_file_and_offer(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'br.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Briefing Fiktiv GmbH', 'stage': 'kontakt'})
            chance = api(f"/leads/{lead['id']}/chances", 'POST', {'title': 'Prozess digital', 'offer': 'automation'})
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
                        brief = page.locator(f'[data-ch-brief="{chance["id"]}"]')
                        brief.locator('summary').click()
                        brief.locator('[data-q="kernprozess"]').wait_for()
                        self.assertEqual(brief.locator('.ch-brief-area legend').all_inner_texts(), ['Analyse & Beratung', 'Software & Web-Technik'])
                        q = brief.locator('[data-q="kernprozess"]')
                        q.locator('[name=status]').select_option('geklaert')
                        q.locator('[name=answer]').fill('Aufträge aus dem Webformular ins ERP')
                        q = brief.locator('[data-q="schnittstellen"]')
                        q.locator('[name=status]').select_option('offen')
                        q.locator('[name=answer]').fill('API-Zugang liefert die IT bis 15.12.')
                        brief.locator('button[type=submit]').click()
                        page.wait_for_function(f'() => document.querySelector(\'[data-ch-brief="{chance["id"]}"] summary small\').textContent.startsWith("1 geklärt · 1 offen")')
                        if SHOTS:
                            brief.screenshot(path=str(Path(SHOTS) / 'briefing.png'))
                        page.locator('#closeModal').click()

                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.select_option('#quoteForm [name=lead_id]', str(lead['id']))
                        page.wait_for_function(f'() => document.querySelector("#quoteForm [name=opportunity_id]").value === "{chance["id"]}"')
                        page.locator('#qbBriefing').click()
                        page.wait_for_function('() => document.querySelector("#quoteForm [name=assumptions]").value.includes("Offene Voraussetzungen")')
                        text = page.input_value('#quoteForm [name=assumptions]')
                        self.assertIn('Kernprozess: Aufträge aus dem Webformular ins ERP', text)
                        self.assertIn('Schnittstellen: API-Zugang liefert die IT bis 15.12.', text)

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
