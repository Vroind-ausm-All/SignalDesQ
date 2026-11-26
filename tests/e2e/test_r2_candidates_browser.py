"""Browserprüfung 2.0.0-dev70 (R2.4): Kandidaten-Sichtung in der Firmenakte – Status, Beleg, widersprüchlicher Arbeitgeber,
historisch, Übernahme nur auf Klick. Erfundene Firma und Personen, keine Abrufe nach außen."""
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

from sales_tool import candidates as cd
from sales_tool.model import connect
from sales_tool.public_contacts import extract_public_contacts
from sales_tool.server import make_handler, prepare_database

RAW = 'Geschäftsführerin: Anna Fiktiv\nMarketingleitung: Max Erfunden\nIT-Leitung: Carla Probe'


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class CandidateReviewBrowserTests(unittest.TestCase):
    def test_review_candidates_in_akte(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'kand.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            req = urllib.request.Request(base + '/api/leads', method='POST', headers={'Content-Type': 'application/json', 'Origin': base},
                                         data=json.dumps({'company': 'Kandidat Fiktiv GmbH', 'website': 'https://kandidat-fiktiv.example'}).encode())
            lead = json.loads(urllib.request.urlopen(req).read())['id']
            c = connect(str(db))
            run = c.execute("INSERT INTO contact_research_runs(lead_id, status, finished_at) VALUES (?, 'done', datetime('now'))", (lead,)).lastrowid
            people = extract_public_contacts({'pages': [{'url': 'https://kandidat-fiktiv.example/team', 'raw_text': RAW}]})['people']
            next(p for p in people if p['full_name'] == 'Max Erfunden')['employer'] = 'Ganz Andere Holding AG'  # Quelle nennt anderen Arbeitgeber
            names = {p['full_name']: cd.store(c, run, lead, p) for p in people}
            c.execute("INSERT INTO contact_candidates(run_id, lead_id, full_name, job_title, source_url, status) VALUES (?,?,?,?,?, 'kandidat')",
                      (run, lead, 'Alt Bestand', 'Geschäftsführer', 'https://kandidat-fiktiv.example/team'))
            c.commit()
            c.close()
            self.assertEqual(names['Max Erfunden'][1], 'widerspruechlich')
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside, dialogs = [], [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.on('dialog', lambda d: (dialogs.append(d.message), d.accept()))
                        page.goto(base + '/#/firmen')
                        page.wait_for_load_state('networkidle')
                        page.evaluate(f'() => showModal({lead})')
                        page.locator('#leadTabs').wait_for(state='visible')
                        page.locator('#lfTab-kontakt').click()
                        page.locator('#lfPeople > summary').click()
                        cards = page.locator('#contactResearchResults [data-candidate-status]')
                        cards.first.wait_for()
                        self.assertEqual(cards.count(), 4)
                        conflict = page.locator('[data-candidate-status="widerspruechlich"]')
                        self.assertIn('Widersprüchlich', conflict.inner_text())
                        self.assertIn('Ganz Andere Holding AG', conflict.inner_text())
                        anna = page.locator('[data-candidate-status="kandidat"]', has_text='Anna Fiktiv')
                        self.assertIn('Fundstelle belegt', anna.inner_text())
                        self.assertIn('Abteilung Geschäftsleitung', anna.inner_text())
                        legacy = page.locator('[data-candidate-status="kandidat"]', has_text='Alt Bestand')
                        self.assertIn('ohne Fundstelle', legacy.inner_text())
                        # historisch
                        page.locator('[data-candidate-status="kandidat"]', has_text='Carla Probe').locator('[data-review-decision="historic"]').click()
                        page.locator('[data-candidate-status="historisch"]', has_text='Carla Probe').wait_for()
                        # widersprüchlich übernehmen: eigene Rückfrage nennt den anderen Arbeitgeber
                        conflict.locator('[data-review-decision="accept"]').click()
                        page.locator('[data-candidate-status="bestaetigt"]', has_text='Max Erfunden').wait_for()
                        self.assertTrue(any('anderen Arbeitgeber' in m for m in dialogs))
                        # alter Kandidat ohne Fundstelle: Übernahme abgelehnt, nichts im CRM
                        legacy.locator('[data-review-decision="accept"]').click()
                        page.locator('.toast.show', has_text='Fundstelle').wait_for()  # vorige Meldung kann noch stehen
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
                with connect(str(db)) as c:
                    crm = [r['full_name'] for r in c.execute('SELECT full_name FROM decision_contacts WHERE lead_id=?', (lead,))]
                self.assertEqual(crm, ['Max Erfunden'])
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
