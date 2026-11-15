"""Browserprüfung 2.0.0-dev33 (Produktreview M32): Am gespeicherten Angebot zeigt „Grundlage je Position“ bestätigten Bedarf,
geprüften Befund, Positionen ohne Grundlage und offene Hypothesen; die Versandfreigabe nennt die Lücke. Fiktive Firma, keine Abrufe nach außen."""
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

sys.path.insert(0, str(Path(__file__).parent.parent))
from s5_helpers import confirm_need  # noqa: E402

from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class OfferBasisBrowserTests(unittest.TestCase):
    def test_basis_visible(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'ob.sqlite3'
            prepare_database(db)
            c = connect(str(db))
            lead = c.execute("INSERT INTO leads(company, stage) VALUES ('Beleg Fiktiv GmbH', 'termin')").lastrowid
            a = c.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'https://b.example', 'done')", (lead,)).lastrowid
            c.execute("""INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, method, certainty, offer, review_status)
                         VALUES (?, ?, 'D1', 'design', 'Uneinheitlicher Auftritt', 'auffaellig', 2, 'Drei Logovarianten', 'dom', 'beobachtet', 'brand', 'ungeprueft')""", (a, lead))
            c.commit()
            confirm_need(c, lead, needs=[{'service': 'pflege', 'size': 'S'}])
            c.close()
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            p = api('/workspace/proposals', 'POST', {'lead_id': lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'pflege', 'size': 'S'}, {'service': 'logo', 'size': 'S'}]})
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
                        page.locator(f'[data-quote-open="{p["id"]}"]').first.click()
                        box = page.locator('.of-basis')
                        box.wait_for()
                        self.assertIn('1 ohne Grundlage', box.locator('summary').inner_text())
                        self.assertIn('bestätigter Bedarf', box.locator('[data-basis="bedarf"]').inner_text())
                        logo = box.locator('[data-basis="ohne"]')
                        self.assertIn('Offene Hypothese (ungeprüft): Uneinheitlicher Auftritt', logo.inner_text())
                        self.assertIn('Pos. 2 Logogestaltung: weder bestätigter Bedarf', page.locator('#ofPanel .of-hints').inner_text())
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
