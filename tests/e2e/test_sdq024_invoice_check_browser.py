"""Browserprüfung SDQ-024/025/026: E-Rechnung prüfen in der Rechnungsansicht, DATEV-Nummern eintragen und den
Buchungsstapel herunterladen, Ersteinrichtung nennt fehlende Rechnungsdaten. Fiktive Daten, keine Abrufe nach außen."""
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_accounting import SELLER, buyer  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class InvoiceCheckBrowserTests(unittest.TestCase):
    def test_check_button_datev_and_onboarding(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'r.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        # Ersteinrichtung: ohne Stammdaten steht „Rechnungsdaten eintragen“ vorn und nennt, was fehlt
                        page.goto(base + '/#/heute')
                        page.locator('#tdOnboarding', has_text='Erste Schritte').locator('text=Erste Schritte').first.click(timeout=15000)
                        page.locator('#tdOnbList li').first.wait_for()
                        self.assertIn('Rechnungsdaten eintragen', page.locator('#tdOnbList li').first.inner_text())
                        page.locator('text=/Noch offen: .*IBAN/ >> visible=true').first.wait_for()
                        with connect(db) as conn:
                            acc.save_settings(conn, SELLER)
                            inv = acc.finalize_invoice(conn, acc.create_invoice(conn, buyer(buyer_reference='04011000-12345-67'))['id'])
                        # E-Rechnung prüfen
                        page.goto(base + '/#/abrechnen')
                        page.locator(f'#accInvoiceRows [data-acc-open="{inv["id"]}"]').click()
                        page.locator(f'[data-acc-check="{inv["id"]}"]').click()
                        ok = page.locator('[data-acc-check-state="ok"]')
                        ok.wait_for()
                        self.assertIn('Keine Fehler', ok.inner_text())
                        self.assertIn('KoSIT', ok.inner_text())
                        # DATEV: erst Nummern der Steuerberatung, dann Download mit Anzahl
                        page.goto(base + '/#/abrechnen/steuer')
                        page.locator('#accDatevForm >> visible=true').wait_for()
                        page.fill('#accDatevForm [name=berater_nr]', '1001')
                        page.fill('#accDatevForm [name=mandant_nr]', '7')
                        page.click('#accDatevForm button[type=submit]')
                        link = page.locator('#accDatevDownload')
                        link.wait_for()
                        self.assertIn('1 Buchungen', link.inner_text())
                        with page.expect_download() as dl:
                            link.click()
                        data = Path(dl.value.path()).read_bytes()
                        self.assertTrue(data.startswith(b'"EXTF";700;21;"Buchungsstapel"'))
                        self.assertIn(b';1001;7;', data)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
