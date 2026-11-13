"""Browserprüfung 2.0.0-dev17 (Roadmap M35, M36, M27):
- Gespeichertes Angebot: Export heißt „Entwurf“, bis die Versandfassung bewusst freigegeben ist (vier Prüfpunkte).
- Nach der Freigabe: Download mit Stand im Dateinamen, ohne Entwurfshinweis; Versand mit Weg und Datum dokumentieren.
- Zusage mit Weg und Person; danach Projektstart: Startaufgaben vorgeschlagen, Nachfassaufgabe beenden, kein Duplikat.
- Website-Bewertung spricht von „Auffällig“ und „Akquise-Priorität“, nicht von einer Gesamtnote.
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
from s5_helpers import confirm_need  # noqa: E402

from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

SHOTS = os.environ.get('SIGNALDESK_E2E_SHOTS')


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class OfferFlowBrowserTests(unittest.TestCase):
    def test_release_send_accept_start(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'f.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Ablauf Fiktiv GmbH', 'stage': 'termin'})
            with connect(db) as conn:
                confirm_need(conn, lead['id'])
            offer = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19',
                                                         'positions': [{'service': 'logo', 'size': 'M'}, {'service': 'software', 'size': 'S'}]})
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/angebote')
                        page.wait_for_load_state('networkidle')
                        page.locator(f'[data-quote-open="{offer["id"]}"]').click()
                        panel = page.locator('#ofPanel')
                        panel.wait_for()
                        self.assertEqual(page.locator('[data-quote-status]').count(), 0, 'freie Statusauswahl ersetzt')
                        self.assertEqual(page.locator('[data-quote-export]').inner_text(), 'Entwurf herunterladen (.md)')
                        with page.expect_download() as dl:
                            page.locator('[data-quote-export]').click()
                        self.assertTrue(dl.value.suggested_filename.startswith('ENTWURF_Angebot_'))
                        self.assertIn('ENTWURF', Path(dl.value.path()).read_text(encoding='utf-8'))
                        self.assertNotIn('fehlt', panel.locator('.of-checks').inner_text())

                        # Freigabe nur mit allen Prüfpunkten
                        panel.locator('[data-of-release]').click()
                        page.wait_for_function('() => document.querySelector("#toast").textContent.includes("Prüfpunkte")')
                        for box in panel.locator('[data-of-confirm]').all():
                            box.check()
                        panel.locator('[data-of-release]').click()
                        page.wait_for_function('() => document.querySelector("[data-quote-export]")?.textContent.startsWith("Versandfassung")')
                        stand = api(f"/workspace/proposals/{offer['id']}/versand")['stand']
                        self.assertIn(stand, page.locator('#ofPanel').inner_text())
                        with page.expect_download() as dl:
                            page.locator('[data-quote-export]').click()
                        self.assertEqual(dl.value.suggested_filename, f"Angebot_{offer['number']}_Stand-{stand}.md")
                        text = Path(dl.value.path()).read_text(encoding='utf-8')
                        self.assertNotIn('ENTWURF', text)
                        self.assertNotIn('Angebotsentwurf', text)

                        # Versand dokumentieren
                        page.locator('#ofPanel [data-of-channel]').select_option('post')
                        page.locator('#ofPanel [data-of-sent]').click()
                        page.locator('#ofPanel .of-step.done', has_text='per Post').wait_for()

                        # Zusage → Projektstart
                        page.locator('#ofPanel [data-of-dchannel]').select_option('bestellung')
                        page.fill('#ofPanel [data-of-person]', 'Frau Beispiel')
                        page.locator('#ofPanel [data-of-decide="angenommen"]').click()
                        start = page.locator('#ofStart')
                        start.wait_for()
                        self.assertEqual(start.locator('[data-of-create]').count(), 6)
                        self.assertEqual(start.locator('[data-of-close]').count(), 1)
                        if SHOTS:
                            page.locator('#quoteSaved').screenshot(path=str(Path(SHOTS) / 'projektstart.png'))
                        start.locator('[data-of-create="ueberblick"]').uncheck()
                        start.locator('[data-of-start]').click()
                        page.locator('#ofPanel .of-step.done', has_text='keine offenen Nachfassaufgaben').wait_for()
                        tasks = api('/tasks')
                        mine = [t for t in tasks if t.get('lead_id') == lead['id']]
                        started = [t['title'] for t in mine if t['title'].startswith(offer['number']) and not t['done']]
                        self.assertEqual(len(started), 5)
                        self.assertFalse([t for t in mine if 'Rückfrage' in t['title'] and not t['done']])
                        self.assertIn('Frau Beispiel', page.locator('#ofPanel').inner_text())

                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
