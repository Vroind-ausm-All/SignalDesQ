"""Browserprüfung SDQ-002 (Audit B1): Adresse und sichtbarer Hauptbereich widersprechen sich nie.

Vorher: Firmenakte offen, in der Seitenleiste „Abrechnen“ geklickt → Adresse #/abrechnen, Seitenleiste und Reiter „Abrechnen“,
sichtbar blieb aber die Firmenakte.
Jetzt:
- Jeder Bereich der Seitenleiste und jeder Reiter der Bereichsleiste schließt die Akte und zeigt den gewählten Bereich.
- Zurück öffnet die Akte wieder, Vor zeigt wieder den Bereich; Direktlink auf die Akte zeigt die Akte.
- Ungespeicherte Eingaben in der Akte: Rückfrage vor dem Wechsel. „Weiter bearbeiten“ bricht den Wechsel ab (Adresse bleibt),
  „Verwerfen“ wechselt ohne zu speichern, „Speichern“ speichert und wechselt.
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

AREAS = {'heute': '#/heute', 'finden': '#/finden', 'firmen': '#/firmen', 'angebote': '#/angebote', 'abrechnen': '#/abrechnen',
         'einstellungen': '#/einstellungen'}

STATE = '''() => ({hash: location.hash,
  views: [...document.querySelectorAll('.content')].filter(e => !e.classList.contains('hidden')).map(e => e.id),
  akte: !document.getElementById('modal').classList.contains('hidden'),
  aktePage: document.body.classList.contains('akte-page'),
  area: document.querySelector('.sidebar .nav[aria-current="page"]')?.dataset.area || ''})'''


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class AkteNavigationBrowserTests(unittest.TestCase):
    def test_url_and_visible_area_agree(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'nav.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Beispiel Werkzeugbau GmbH', 'location': 'Stuttgart 70191', 'stage': 'recherche'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 800})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        state = lambda: page.evaluate(STATE)
                        akte_hash = f"#/firmen/akte/{lead['id']}"

                        def open_akte():
                            page.goto(base + '/' + akte_hash)
                            page.wait_for_load_state('networkidle')
                            page.locator('#leadTabs').wait_for(state='visible')
                            s = state()
                            self.assertTrue(s['akte'] and s['aktePage'], s)
                            self.assertEqual(s['hash'], akte_hash)

                        def assert_area(area):
                            page.wait_for_function('h => location.hash.startsWith(h)', arg=AREAS[area])
                            page.locator('#modal').wait_for(state='hidden')
                            s = state()
                            self.assertFalse(s['akte'], s)
                            self.assertFalse(s['aktePage'], s)
                            self.assertEqual(s['area'], area, s)
                            self.assertEqual(len(s['views']), 1, s)

                        # ---- Der Fall aus dem Audit: Akte → Abrechnen
                        open_akte()
                        page.locator('.sidebar .nav[data-area="abrechnen"]').click()
                        assert_area('abrechnen')
                        self.assertEqual(state()['views'], ['viewAccounting'])
                        # Zurück: wieder die Akte; Vor: wieder Abrechnen
                        page.go_back()
                        page.locator('#modal').wait_for(state='visible')
                        self.assertEqual(state()['hash'], akte_hash)
                        self.assertTrue(state()['aktePage'])
                        page.go_forward()
                        assert_area('abrechnen')

                        # ---- jeder Bereich der Seitenleiste
                        for area in AREAS:
                            with self.subTest(area=area):
                                open_akte()
                                page.locator(f'.sidebar .nav[data-area="{area}"]').click()
                                assert_area(area)

                        # ---- Reiter der Bereichsleiste (Akte über „Abrechnen“ geöffnet)
                        page.goto(base + '/#/abrechnen')
                        page.wait_for_load_state('networkidle')
                        page.evaluate(f"() => showModal({lead['id']})")
                        page.locator('#modal').wait_for(state='visible')
                        page.locator('#areaBar [data-area-view="expenses"]').click()
                        page.wait_for_function('() => location.hash.startsWith("#/abrechnen/ausgaben")')
                        page.locator('#modal').wait_for(state='hidden')
                        self.assertEqual(state()['views'], ['viewExpenses'])

                        # ---- ungespeicherte Eingabe: Weiter bearbeiten bricht ab
                        def edit_location(value):
                            open_akte()
                            page.locator('[data-lf-tab="stammdaten"]').click()
                            page.fill('#leadForm [name=location]', value)

                        edit_location('Esslingen')
                        page.locator('.sidebar .nav[data-area="angebote"]').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        self.assertEqual(state()['hash'], akte_hash, 'vor der Entscheidung kein Wechsel der Adresse')
                        page.locator('[data-guard="edit"]').click()
                        self.assertFalse(page.locator('#lfGuard').is_visible())
                        s = state()
                        self.assertEqual((s['hash'], s['akte']), (akte_hash, True))
                        self.assertEqual(page.input_value('#leadForm [name=location]'), 'Esslingen')

                        # Verwerfen: Wechsel, nichts gespeichert
                        page.locator('.sidebar .nav[data-area="angebote"]').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.locator('[data-guard="discard"]').click()
                        assert_area('angebote')
                        self.assertEqual(next(x for x in api('/leads') if x['id'] == lead['id'])['location'], 'Stuttgart 70191')

                        # Speichern: gespeichert, dann Wechsel
                        edit_location('Ludwigsburg')
                        page.locator('.sidebar .nav[data-area="heute"]').click()
                        page.locator('#lfGuard').wait_for(state='visible')
                        page.locator('[data-guard="save"]').click()
                        assert_area('heute')
                        self.assertEqual(next(x for x in api('/leads') if x['id'] == lead['id'])['location'], 'Ludwigsburg')

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
