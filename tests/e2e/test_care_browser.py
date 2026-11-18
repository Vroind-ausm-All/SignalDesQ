"""Browserprüfung 2.0.0-dev26 (Produktreview M19): Bestandskunden zeigen Betreuung und Projekte getrennt; Monatsrechnung
für den offenen Monat erstellen; Laufzeit beenden; neues Projekt als eigene Chance anlegen. Fiktive Firma, keine Abrufe nach außen."""
import datetime as dt
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
from s5_helpers import confirm_need, release_offer  # noqa: E402
from test_accounting import SELLER  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class CareBrowserTests(unittest.TestCase):
    def test_care_billing_and_new_project(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'cr.sqlite3'
            prepare_database(db)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'

            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read() or b'null')

            lead = api('/leads', 'POST', {'company': 'Betreuung Fiktiv GmbH', 'stage': 'termin'})
            conn = connect(str(db))
            acc.save_settings(conn, SELLER)
            confirm_need(conn, lead['id'])
            conn.close()
            p = api('/workspace/proposals', 'POST', {'lead_id': lead['id'], 'tax_mode': 'regel_19', 'project_label': 'Website mit Betreuung',
                                                     'positions': [{'service': 'webdesign', 'size': 'S'}, {'service': 'pflege', 'size': 'M'}]})
            conn = connect(str(db))
            release_offer(conn, p['id'])
            of.set_status(conn, p['id'], {'status': 'gesendet_manuell'})
            of.set_status(conn, p['id'], {'status': 'angenommen'})
            conn.close()
            month = dt.date.today().strftime('%m/%Y')
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/angebote/auftraege')  # 2.0.0-dev52: Angebote → Aufträge & Betreuung
                        page.wait_for_load_state('networkidle')
                        firm = page.locator(f'[data-cr-firm="{lead["id"]}"]')
                        firm.wait_for()
                        self.assertIn('Website-/Shop-Betreuung', firm.locator('.cr-care').inner_text())
                        self.assertIn(f'Nicht abgerechnet: {month}', firm.inner_text())
                        self.assertIn(p['number'], firm.locator('.cr-cols > div').nth(1).inner_text(), 'Website als Projekt getrennt')
                        firm.locator('[data-quote-invoice][data-mode="monat"]').click()
                        for _ in range(50):  # Rechnungsentwurf entsteht nach dem Wechsel in „Abrechnen“
                            invs = api('/accounting/invoices')
                            if invs:
                                break
                            page.wait_for_timeout(100)
                        self.assertEqual(len(invs), 1)
                        page.goto(base + '/#/angebote/auftraege')  # 2.0.0-dev52: Angebote → Aufträge & Betreuung
                        page.wait_for_load_state('networkidle')
                        firm = page.locator(f'[data-cr-firm="{lead["id"]}"]')
                        firm.locator('.cr-care', has_text='Alle Monate bis heute abgerechnet').wait_for()
                        end = (dt.date.today().replace(day=28) + dt.timedelta(days=10)).replace(day=1) - dt.timedelta(days=1)
                        firm.locator('[data-cr-term] [name=end_date]').fill(end.isoformat())
                        firm.locator('[data-cr-term] [name=note]').fill('Kündigung per Mail')
                        firm.locator('[data-cr-term] button[type=submit]').click()
                        page.locator(f'[data-cr-firm="{lead["id"]}"] .cr-care', has_text='gekündigt zum').wait_for()
                        page.locator(f'[data-cr-firm="{lead["id"]}"] [data-cr-chance] [name=title]').fill('Online-Shop')
                        page.locator(f'[data-cr-firm="{lead["id"]}"] [data-cr-chance] button[type=submit]').click()
                        page.locator(f'[data-cr-firm="{lead["id"]}"] .cr-list li', has_text='Online-Shop').wait_for()
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
