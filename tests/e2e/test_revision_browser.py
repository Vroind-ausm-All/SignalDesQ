"""Browserprüfung 2.0.0-dev21 (Produktreview M15, Abnahmefall T11):
- Gespeichertes Angebot „Überarbeiten“: Positionen, Titel und Firma werden in den Baukasten geladen.
- Speichern mit Grund ergibt die Fassung -R2 mit Änderungsliste; die Fassungen-Übersicht zeigt beide.
- Die alte Fassung zeigt „Ersetzt“ statt Freigabe, Versand und Zusage.
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
class RevisionBrowserTests(unittest.TestCase):
    def test_revise_offer(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'rv.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Fassung Fiktiv GmbH', 'stage': 'termin'})
            v1 = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Neue Website',
                                                      'positions': [{'service': 'webdesign', 'size': 'M'}, {'service': 'seo_geo', 'size': 'S'}]})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'[data-quote-open="{v1["id"]}"]').click()
                        page.locator(f'[data-of-revise="{v1["id"]}"]').click()
                        page.locator('#qbRevision').wait_for(state='visible')
                        page.wait_for_function('() => document.querySelectorAll("#qbPositions .qb-pos").length === 2')
                        self.assertEqual(page.input_value('#quoteForm [name=project_label]'), 'Neue Website')
                        self.assertEqual(page.input_value('#quoteForm [name=lead_id]'), str(lead['id']))
                        page.locator('#qbPositions [data-qb-del="1"]').click()  # SEO entfällt
                        page.wait_for_function('() => document.querySelectorAll("#qbPositions .qb-pos").length === 1')
                        page.fill('#qbRevisionReason', 'SEO später als eigenes Projekt')
                        page.locator('#quoteForm button[type=submit]').click()
                        page.locator('#quoteSaved h3', has_text=v1['number'] + '-R2').wait_for()
                        self.assertTrue(page.locator('#qbRevision').is_hidden())
                        hist = page.locator('.of-history')
                        hist.locator('summary').click()
                        text = hist.inner_text()
                        self.assertIn('Fassungen (2)', text)
                        self.assertIn('Entfällt: SEO- & GEO-Optimierung', text)
                        self.assertIn('Grund: SEO später als eigenes Projekt', text)
                        if SHOTS:
                            page.locator('#quoteSaved').screenshot(path=str(Path(SHOTS) / 'revision.png'))
                        page.locator(f'[data-quote-open="{v1["id"]}"]').first.click()
                        page.locator('#ofPanel', has_text='Ersetzt').wait_for()
                        self.assertEqual(page.locator('#ofPanel [data-of-release]').count(), 0)
                        self.assertEqual(page.locator(f'[data-of-revise="{v1["id"]}"]').count(), 0)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
