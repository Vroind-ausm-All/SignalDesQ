"""Browserprüfung SDQ-003 (Audit B2): Ungespeicherte Eingaben im Rechnungseditor gehen nicht still verloren.

- Geänderter Entwurf + Wechsel des Bereichs: Rückfrage (Speichern · Weiter bearbeiten · Verwerfen); die Adresse bleibt bis zur Antwort.
- „Weiter bearbeiten“: Editor bleibt mit der Eingabe. „Verwerfen“: zurück zum gespeicherten Stand. „Speichern“: als Entwurf gespeichert
  (nie festgeschrieben), dann Wechsel.
- „← Rechnungen“ im Editor fragt ebenso. Unveränderter Editor: keine Rückfrage.
- Fenster schließen oder neu laden mit Änderungen: beforeunload hält an, der Browser fragt nach.
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

from sales_tool import accounting as acc
from sales_tool.model import connect
from sales_tool.server import make_handler, prepare_database

SELLER = {'company_name': 'Beispiel Studio', 'owner_name': 'Alex Muster', 'street': 'Musterweg 1', 'zip': '20457', 'city': 'Hamburg',
          'tax_number': '22/123/45678', 'email': 'rechnung@studio.example', 'iban': 'DE89 3704 0044 0532 0130 00'}


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class InvoiceGuardBrowserTests(unittest.TestCase):
    def test_invoice_editor_never_drops_input_silently(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ig.sqlite3'
            prepare_database(db)
            with connect(db) as conn:
                acc.save_settings(conn, SELLER)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path):
                req = urllib.request.Request(base + '/api' + path, headers={'Origin': base})
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            def drafts():
                data = api('/accounting/invoices')
                rows = data['invoices'] if isinstance(data, dict) else data
                return [r for r in rows if r['status'] == 'entwurf']

            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1280, 'height': 800})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        guard = page.locator('#lfGuard')
                        mode = lambda: page.evaluate('() => document.getElementById("viewAccounting").dataset.accMode')

                        def new_invoice():
                            page.goto(base + '/#/abrechnen')
                            page.wait_for_load_state('networkidle')
                            page.locator('#accNewInvoice').click()
                            page.locator('#accInvoiceForm [name=buyer_name]').wait_for(state='visible')

                        # ---- unverändert: keine Rückfrage
                        new_invoice()
                        page.locator('.sidebar .nav[data-area="heute"]').click()
                        page.wait_for_function('() => location.hash.startsWith("#/heute")')
                        self.assertFalse(guard.is_visible())

                        # ---- geändert + Bereichswechsel → Rückfrage; Weiter bearbeiten
                        new_invoice()
                        page.fill('#accInvoiceForm [name=buyer_name]', 'Beispiel Maschinenbau GmbH')
                        page.locator('.sidebar .nav[data-area="angebote"]').click()
                        guard.wait_for(state='visible')
                        self.assertTrue(page.evaluate('() => location.hash.startsWith("#/abrechnen")'), 'Adresse bleibt bis zur Antwort')
                        self.assertIn('Rechnungsentwurf', page.text_content('#lfGuardText'))
                        page.locator('[data-guard="edit"]').click()
                        guard.wait_for(state='hidden')
                        self.assertTrue(page.evaluate('() => location.hash.startsWith("#/abrechnen")'))
                        self.assertEqual(mode(), 'edit')
                        self.assertEqual(page.input_value('#accInvoiceForm [name=buyer_name]'), 'Beispiel Maschinenbau GmbH')

                        # ---- „← Rechnungen“ + Verwerfen → Liste, nichts gespeichert
                        page.locator('#accEditorClose').click()
                        guard.wait_for(state='visible')
                        page.locator('[data-guard="discard"]').click()
                        page.wait_for_function('() => document.getElementById("viewAccounting").dataset.accMode === "list"')
                        self.assertEqual(drafts(), [])

                        # ---- Speichern → Entwurf gespeichert (nicht festgeschrieben), dann Wechsel
                        new_invoice()
                        page.fill('#accInvoiceForm [name=buyer_name]', 'Beispiel Maschinenbau GmbH')
                        page.fill('#accLines [data-f="description"]', 'Konzept Landingpage')
                        page.fill('#accLines [data-f="unit_price_eur"]', '1200')
                        page.locator('.sidebar .nav[data-area="heute"]').click()
                        guard.wait_for(state='visible')
                        page.locator('[data-guard="save"]').click()
                        page.wait_for_function('() => location.hash.startsWith("#/heute")')
                        saved = drafts()
                        self.assertEqual(len(saved), 1)
                        self.assertEqual(saved[0]['buyer_name'], 'Beispiel Maschinenbau GmbH')
                        self.assertFalse(saved[0].get('number'), 'Speichern schreibt nie fest')

                        # ---- gespeicherter Entwurf, erneut geändert, Verwerfen → gespeicherter Stand
                        page.goto(base + '/#/abrechnen')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'#accInvoiceRows [data-acc-open="{saved[0]["id"]}"]').click()
                        page.locator('#accInvoiceForm [name=buyer_name]').wait_for(state='visible')
                        page.fill('#accInvoiceForm [name=buyer_name]', 'Tippfehler GmbH')
                        page.locator('.sidebar .nav[data-area="firmen"]').click()
                        guard.wait_for(state='visible')
                        page.locator('[data-guard="discard"]').click()
                        page.wait_for_function('() => location.hash.startsWith("#/firmen")')
                        self.assertEqual(drafts()[0]['buyer_name'], 'Beispiel Maschinenbau GmbH')
                        self.assertEqual(page.input_value('#accInvoiceForm [name=buyer_name]'), 'Beispiel Maschinenbau GmbH')

                        # ---- Fenster schließen/neu laden mit Änderungen → beforeunload hält an (der Browser fragt dann nach)
                        unload = '() => { const e = new Event("beforeunload", {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; }'
                        new_invoice()
                        self.assertFalse(page.evaluate(unload), 'unveränderter Editor hält nicht an')
                        page.fill('#accInvoiceForm [name=buyer_name]', 'Noch nicht gespeichert GmbH')
                        self.assertTrue(page.evaluate(unload))
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
