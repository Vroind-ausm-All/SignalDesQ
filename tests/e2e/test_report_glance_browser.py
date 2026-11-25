"""Browserprüfung 2.0.0-dev66: Firmen-Bericht „Auf einen Blick“ und Website-Vorschlag („Passt / Passt nicht“).
Fiktive Firma ohne Website, gespeicherter Bericht – keine Abrufe nach außen."""
import json
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

from sales_tool.model import connect
from sales_tool.report import STEPS
from sales_tool.server import make_handler, prepare_database


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class ReportGlanceBrowserTests(unittest.TestCase):
    def test_glance_and_reject_suggestion(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'rg.sqlite3'
            prepare_database(db)
            c = connect(str(db))
            lead = c.execute("""INSERT INTO leads(company, website, street, zip, city, business_phone, stage, permission)
                                VALUES ('Kessel Anlagen Fiktiv', '', 'Industriestr. 5', '70565', 'Stuttgart', '0711 0000000', 'recherche', 'unbekannt')""").lastrowid
            steps = {k: {'label': v, 'status': 'übersprungen', 'detail': 'Keine bestätigte Website'} for k, v in STEPS}
            steps['webfinden'] = {'label': 'Website finden & zuordnen', 'status': 'hinweis', 'detail': 'Vorschlag kessel-fiktiv.example'}
            steps['verknuepfen'] = {'label': 'Signale verknüpfen & passende Pakete', 'status': 'fertig', 'detail': '0 Hypothesen'}
            refs = {'website_suggestion': {'url': 'https://kessel-fiktiv.example', 'imprint_url': '',
                                           'evidence': 'PLZ, Straße, Telefon stimmen mit dem Impressum überein'}}
            c.execute("INSERT INTO company_reports(lead_id, status, steps_json, refs_json, finished_at) VALUES (?, 'teilweise', ?, ?, datetime('now'))",
                      (lead, json.dumps(steps, ensure_ascii=False), json.dumps(refs, ensure_ascii=False)))
            c.commit()
            c.close()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        for width in (1366, 390):
                            page = browser.new_page(viewport={'width': width, 'height': 900})
                            errors, outside = [], []
                            page.on('pageerror', lambda exc: errors.append(str(exc)))
                            page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                            page.goto(base + '/')
                            page.wait_for_load_state('networkidle')
                            page.evaluate(f'openReport({lead})')
                            glance = page.locator('[data-rp-glance]')
                            glance.wait_for()
                            text = glance.inner_text()
                            self.assertIn('Kurzfazit', text)
                            self.assertIn('Keine bestätigte Website – Vorschlag liegt vor, bitte prüfen', text)
                            self.assertIn('Kontakterlaubnis ungeklärt', text)
                            self.assertIn('kessel-fiktiv.example', page.locator('[data-rp-suggestion]').inner_text())
                            self.assertIn('keine bestätigte Website', page.locator('#rpBody .page-title').inner_text())
                            overflow = page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
                            self.assertLessEqual(overflow, 1, f'kein seitliches Scrollen bei {width} px')
                            self.assertEqual(errors, [])
                            self.assertEqual(outside, [])
                            if width == 390:
                                page.locator('[data-rp-suggest="ablehnen"]').click()
                                page.locator('[data-rp-suggestion]').wait_for(state='detached')
                                self.assertIn('Keine bestätigte Website', page.locator('[data-rp-glance]').inner_text())
                            page.close()
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
            c = connect(str(db))
            try:
                row = c.execute('SELECT website FROM leads WHERE id=?', (lead,)).fetchone()
                refs = json.loads(c.execute('SELECT refs_json FROM company_reports WHERE lead_id=?', (lead,)).fetchone()[0])
            finally:
                c.close()
            self.assertEqual(row['website'], '', 'abgelehnt: nichts eingetragen')
            self.assertEqual(refs['rejected_domains'], ['kessel-fiktiv.example'])


if __name__ == '__main__':
    unittest.main()
