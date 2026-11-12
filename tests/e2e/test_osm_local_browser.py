"""Browserprüfung 2.0.0-dev7: OpenStreetMap manuell – Anleitung sehen, Auszug einlesen, Suche in einer PLZ läuft offline
aus dem lokalen Bestand. Fiktive Betriebe; es wird kein öffentlicher Server abgefragt."""
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
from sales_tool.research import jobs
from sales_tool.server import make_handler

PBF = Path(__file__).resolve().parent.parent / 'fixtures' / 'osm' / 'beispiel.osm.pbf'
SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class OsmLocalBrowserTests(unittest.TestCase):
    def test_howto_import_and_offline_search(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'o.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1400, 'height': 1100})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(f'http://127.0.0.1:{server.server_port}')
                        page.locator('[data-view="finder"]').click()
                        page.locator('#swForm input[name="place"]').fill('70191')
                        page.locator('#swForm select[name="radius_km"]').select_option('0')
                        self.assertFalse(page.locator('#swForm input[name="osm_online"]').is_checked())  # online nur auf Wunsch

                        page.locator('#osmBox > summary').click()
                        page.locator('#osmState', has_text='noch kein lokaler Bestand').wait_for(timeout=15000)
                        self.assertEqual(page.locator('#osmHowto .osm-how').count(), 3)
                        link = page.locator('#osmTurbo')
                        link.wait_for(state='visible', timeout=15000)
                        self.assertIn('overpass-turbo.eu', link.get_attribute('href'))
                        self.assertIn('70191', link.get_attribute('href'))

                        page.locator('#osmFile').set_input_files(str(PBF))
                        page.locator('#osmState', has_text='6 Betriebe').wait_for(timeout=30000)
                        if SHOTS:
                            page.locator('#osmBox').screenshot(path=str(Path(SHOTS) / 'osm.png'))

                        # Suche nur über OpenStreetMap, offline aus dem lokalen Bestand
                        for src in ('gleif', 'wikidata', 'ted'):
                            page.locator(f'#swForm input[name="src"][value="{src}"]').uncheck()
                        page.locator('#swForm input[name="include_sole"]').check()
                        page.locator('#swForm input[name="find_websites"]').uncheck()
                        page.locator('#swGo').click()
                        page.wait_for_function("""async () => {
                          const r = await (await fetch('/api/sweep-candidates?status=neu')).json();
                          const s = await (await fetch('/api/sweeps')).json();
                          const done = (s.sweeps || s.items || s)[0]?.status === 'fertig';
                          // 3 Betriebe mit PLZ 70191 und 1 ohne PLZ-Angabe, über den Nachbarbetrieb zugeordnet
                          return done && r.items.length === 4 && r.items.every(i => i.zip === '70191' || i.zip === '');
                        }""", timeout=30000)
                        # 2.0.0-dev9: Betriebe ohne Rechtsform sind gekennzeichnet, die Branche kommt aus dem OSM-Merkmal
                        maler = page.locator('.sw-main', has_text='Malerbetrieb Beispiel')
                        maler.wait_for(timeout=15000)
                        self.assertIn('ohne Rechtsform', maler.inner_text())
                        self.assertNotIn('ohne Rechtsform', page.locator('.sw-main', has_text='Elektro Fiktiv GmbH').inner_text())
                        if SHOTS:
                            page.locator('#swList, .sw-list').first.screenshot(path=str(Path(SHOTS) / 'treffer.png'))
                        # alle Treffer des Filters in einem Zug übernehmen
                        page.once('dialog', lambda dlg: dlg.accept())
                        page.locator('#swTakeAll').click()
                        page.wait_for_function("async () => (await (await fetch('/api/leads')).json()).length === 4", timeout=30000)
                        # 2.0.0-dev10: Firmenakte eines Betriebs ohne Rechtsform zeigt Datenschutz-Hinweis und Löschfrist
                        page.locator('[data-view="leads"]').click()
                        page.locator('#leadRows tr', has_text='Malerbetrieb Beispiel').click()
                        box = page.locator('.lf-privacy')
                        box.wait_for(timeout=15000)
                        self.assertIn('Löschfrist bis', box.inner_text())
                        page.once('dialog', lambda dlg: dlg.accept('Gespräch für nächste Woche vereinbart'))
                        box.locator('[data-dc-extend]').click()
                        page.wait_for_function("""async () => (await (await fetch('/api/privacy')).json())
                          .some(r => r.kind === 'einzelunternehmen' && r.note.includes('Gespräch für nächste Woche vereinbart'))""", timeout=15000)
                        if SHOTS:  # die Akte wird nach dem Verlängern neu gezeichnet – erst danach fotografieren
                            page.wait_for_timeout(1500)
                            page.locator('.lf-privacy').screenshot(path=str(Path(SHOTS) / 'datenschutz.png'))
                        self.assertEqual(outside, [], 'kein Abruf außerhalb des eigenen Rechners')
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                jobs.stop_all_workers()


if __name__ == '__main__':
    unittest.main()
