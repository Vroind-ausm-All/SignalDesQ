"""Browserprüfung 2.0.0-dev19 (Produktreview M13 Teil 2):
- Bedarfsanalyse: Auswahl der Chance über dem Formular; die zweite Chance lädt und speichert ihren eigenen Bedarf, die Firma
  bleibt unverändert.
- Freigabe des Bedarfs direkt an der Chance; „Angebot aus bestätigtem Bedarf“ legt das Angebot für diese Chance an.
- Pipeline zeigt offene Chancen als eigene Karten statt der Firma.
Fiktive Firma, keine Abrufe nach außen."""
import json
import os
import sys
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ChanceNeedBrowserTests(unittest.TestCase):
    def test_need_per_chance_offer_and_pipeline(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'cn.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Zwei Bedarfe Fiktiv GmbH', 'stage': 'kontakt'})
            api(f"/leads/{lead['id']}/discovery", 'PUT', {'problem': 'Website veraltet', 'desired_outcome': 'Mehr Anfragen'})
            first = api(f"/leads/{lead['id']}/chances", 'POST', {'title': 'Website'})
            second = api(f"/leads/{lead['id']}/chances", 'POST', {'title': 'Kundenportal', 'problem': 'Statusanfragen per Telefon'})
            with connect(db) as conn:  # dokumentiertes Gespräch als Grundlage der Freigabe
                conn.execute("INSERT INTO calls(lead_id, outcome, notes) VALUES (?, 'erreicht', 'Portal besprochen')", (lead['id'],))
                conn.commit()
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
                        page.locator('#discoveryChanceWrap').wait_for(state='visible')
                        self.assertEqual(page.input_value('#discoveryForm [name=problem]'), 'Website veraltet')

                        # Bedarfsanalyse der zweiten Chance laden, ergänzen, speichern
                        page.select_option('#discoveryChance', str(second['id']))
                        page.wait_for_function('() => document.querySelector("#discoveryForm [name=problem]").value === "Statusanfragen per Telefon"')
                        self.assertTrue(page.locator('#lfDirty').is_hidden(), 'Wechsel der Chance gilt nicht als ungespeicherte Eingabe')
                        page.fill('#discoveryForm [name=desired_outcome]', 'Selbstauskunft im Portal')
                        page.locator('#discoveryForm button[type=submit]').click()
                        page.wait_for_function('() => document.querySelector("#toast").textContent.includes("Chance gespeichert")')
                        self.assertEqual(api(f"/leads/{lead['id']}/discovery")['desired_outcome'], 'Mehr Anfragen', 'Firma unverändert')
                        self.assertEqual(api(f"/leads/{lead['id']}/need?chance={second['id']}")['desired_outcome'], 'Selbstauskunft im Portal')

                        # Freigabe an der Chance, dann Angebot aus ihrem Bedarf
                        card = page.locator(f'#chList [data-ch="{second["id"]}"]')
                        card.locator('.ch-confirm summary').click()
                        card.locator('[data-ch-confirm] [name=note]').fill('Portal für Statusabfragen bestätigt')
                        card.locator('[data-ch-confirm] [name=service]').select_option('software')
                        card.locator('[data-ch-confirm] button[type=submit]').click()
                        page.locator(f'#chList [data-ch="{second["id"]}"] [data-ch-quote]').wait_for()
                        if SHOTS:
                            page.locator('.ch-panel').screenshot(path=str(Path(SHOTS) / 'chance_bedarf.png'))
                        page.locator(f'#chList [data-ch="{second["id"]}"] [data-ch-quote]').click()
                        page.wait_for_function('() => location.hash.startsWith("#/angebote")')
                        props = api('/workspace/proposals')
                        self.assertEqual(len(props), 1)
                        detail = api(f"/workspace/proposals/{props[0]['id']}/versand")
                        self.assertNotIn('bedarf', [c['key'] for c in detail['checks'] if not c['ok']], 'Bedarf der Chance ist bestätigt')
                        chances = {c['id']: c for c in api(f"/leads/{lead['id']}/chances")['chances']}
                        self.assertEqual([p['id'] for p in chances[second['id']]['proposals']], [props[0]['id']])
                        self.assertEqual(chances[first['id']]['proposals'], [])

                        # Pipeline: Chancen als eigene Karten
                        page.goto(base + '/#/firmen/pipeline')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'[data-pchance="{second["id"]}"]').wait_for()
                        self.assertEqual(page.locator(f'[data-pcol="termin"] [data-pchance="{second["id"]}"]').count(), 1)
                        self.assertEqual(page.locator(f'[data-pcol="antwort"] [data-pchance="{first["id"]}"]').count(), 1)
                        self.assertEqual(page.locator(f'[data-pcard="{lead["id"]}"]').count(), 0, 'Firma erscheint über ihre Chancen')
                        page.locator(f'[data-pc-ctoggle="{first["id"]}"]').click()
                        page.select_option(f'[data-chance-update="{first["id"]}"]', 'angebot')
                        page.locator(f'[data-pcol="angebot"] [data-pchance="{first["id"]}"]').wait_for()
                        if SHOTS:
                            page.locator('#pipelineBoard').screenshot(path=str(Path(SHOTS) / 'pipeline_chancen.png'))

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
