"""Browserprüfung 2.0.0-dev16 (Produktreview M12, zentraler Leistungskatalog):
- Einstellungen → Leistungen & Preise zeigt die sechs Vorlagen mit Preis aus den Positionen und die Herkunft der früheren Listen.
- Ein geänderter Katalogwert (fester Preis) erscheint sofort im Vorlagenpreis, auf der Angebotskarte der Hilfe und im neuen Angebot.
- Korrekturschleifen lassen sich je Leistung festlegen; die Kundenvorschau führt sie je Position zusammen (K01).
- Intern stehen offene Punkte und „Vor dem Versand klären“ je Leistungsbereich; im Kundendokument nicht.
- Ein gespeichertes Angebot behält Text und Preis, wenn der Katalog danach geändert wird.
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

from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class CatalogBrowserTests(unittest.TestCase):
    def test_one_catalog_everywhere_and_saved_offers_stay(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'k.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Katalog Fiktiv GmbH', 'stage': 'qualifiziert'})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/einstellungen')
                        page.wait_for_load_state('networkidle')
                        page.locator('[data-settings-jump="preise"]').click()

                        # Vorlagen mit Preis und Herkunft
                        rows = page.locator('#qbVorlagen [data-qb-vorlage]')
                        rows.first.wait_for()
                        self.assertEqual(rows.count(), 6)
                        conv = page.locator('[data-qb-vorlage="conversion"]')
                        before = conv.locator('td.num').inner_text()
                        self.assertIn('einmalig', before)
                        self.assertIn('Website- & Werbetexte', conv.inner_text())
                        page.locator('.qb-herkunft summary').click()
                        self.assertIn('Conversion- & Web-Sprint', page.locator('.qb-herkunft').inner_text())  # früherer Angebotsname

                        # Geänderte Leistung: fester Preis für Webdesign (Standard) und 3 Korrekturschleifen für Texte
                        web = page.locator('[data-qb-row="webdesign"][data-size="M"]')
                        web.locator('[name=fixed_price]').fill('5000')
                        web.locator('[name=revisions]').fill('2')
                        web.locator('[data-qb-save]').click()
                        page.wait_for_function('() => document.querySelector(\'[data-qb-row="webdesign"][data-size="M"]\').classList.contains("custom")')
                        after = page.locator('[data-qb-vorlage="conversion"] td.num').inner_text()
                        self.assertNotEqual(before, after)
                        price_now = api('/pricing/catalog')['vorlagen'][1]
                        self.assertEqual(price_now['key'], 'conversion')
                        euro = lambda v: f"{v:,.0f}".replace(',', '.') + ' €'
                        self.assertIn(euro(price_now['once_net_eur']), after)
                        if SHOTS:
                            page.locator('#qbSettingsBox').screenshot(path=str(Path(SHOTS) / 'katalog_vorlagen.png'))

                        # Hilfe: Angebotskarte zeigt denselben Preis (Seite neu laden, Konfiguration wird beim Start gelesen)
                        page.goto(base + '/#/einstellungen/hilfe')
                        page.wait_for_load_state('networkidle')
                        card = page.locator('.offer-card', has_text='B2B Website- & Conversion-Sprint')
                        self.assertIn(euro(price_now['once_net_eur']), card.inner_text())

                        # Angebot aus der Vorlage
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.select_option('#quoteForm [name=lead_id]', str(lead['id']))
                        page.select_option('#quotePackage', 'conversion')
                        page.locator('#qbTemplate').click()
                        page.locator('#quoteCustomer .qb-table').wait_for()
                        page.wait_for_function('() => document.querySelector("#quoteInternal").textContent.includes("Vor dem Versand klären")')
                        cust = page.locator('#quoteCustomer').inner_text()
                        self.assertIn('Korrekturschleifen: Pos. 1 Webdesign & Website-Umsetzung: 2 Korrekturschleifen; Pos. 2 Website- & Werbetexte: 1 Korrekturschleife je Seite/Text', cust)
                        self.assertNotIn('Texte (separate Position)', cust)  # Texte sind eine eigene Position – kein Widerspruch
                        self.assertNotIn('Vor dem Versand', cust)
                        internal = page.locator('#quoteInternal').inner_text()
                        for area in ('Mediengestaltung', 'Software & Web-Technik', 'Sichtbarkeit & Kampagnen'):
                            self.assertIn(area, internal)
                        self.assertIn('ist die Vorgabe aus deinen Kalkulationsgrundlagen', internal)
                        if SHOTS:
                            page.locator('#viewQuotes').screenshot(path=str(Path(SHOTS) / 'katalog_angebot.png'))
                        page.select_option('#quoteForm [name=tax_mode]', 'regel_19')
                        page.locator('#quoteForm button[type=submit]').click()
                        page.locator('#quoteSaved h3').wait_for()
                        saved = api('/workspace/proposals')[0]
                        self.assertEqual(saved['net_eur'], price_now['once_net_eur'])

                        # Katalog danach ändern: gespeichertes Angebot bleibt in Text und Preis gleich
                        detail_before = api(f"/workspace/proposals/{saved['id']}/customer")
                        api('/pricing/overrides', 'PUT', {'service': 'webdesign', 'size': 'M', 'fixed_price': 6500, 'revisions': 3})
                        detail_after = api(f"/workspace/proposals/{saved['id']}/customer")
                        self.assertEqual(detail_before, detail_after)
                        self.assertNotEqual(api('/pricing/catalog')['vorlagen'][1]['once_net_eur'], price_now['once_net_eur'])

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
