"""Browserprüfung SDQ-014/015: Anmeldung in der Mehrmandanten-Installation – Konto anmelden, Organisation wählen, nur deren
Firmen sehen, wechseln, abmelden. Fiktive Organisationen, keine Abrufe nach außen."""
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

from sales_tool import accounts, tenancy
from sales_tool.model import connect
from sales_tool.multi_server import make_multi_handler

PW = 'Lange-Passphrase-7391'


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class MultiTenantBrowserTests(unittest.TestCase):
    def test_login_choose_switch_logout(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = tenancy.Directory(Path(tmp) / 'm')
            for slug, name in (('nord', 'Nord'), ('sued', 'Süd')):
                org = d.create(slug, name)
                with connect(org['db_path']) as conn:
                    conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'neu')", (f'{name} Fiktiv GmbH',))
                    conn.commit()
            accounts.create_account(d, 'beide', PW, 'Beide Beispiel')
            accounts.set_membership(d, 'beide', 'nord', 'vertrieb')
            accounts.set_membership(d, 'beide', 'sued', 'vertrieb')
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(d))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 1366, 'height': 900})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/#/firmen')
                        page.wait_for_url(lambda u: '/anmelden' in u)
                        page.fill('#zLogin [name=username]', 'beide')
                        page.fill('#zLogin [name=password]', 'falsch-falsch')
                        page.click('#zLogin button[type=submit]')
                        page.locator('#zMsg', has_text='falsch').wait_for()
                        page.fill('#zLogin [name=password]', PW)
                        page.click('#zLogin button[type=submit]')
                        # dev68: ohne zweiten Faktor wird er empfohlen – „Später“ führt zur Auswahl der Organisation
                        page.locator('#zSuggest >> visible=true').wait_for()
                        page.click('#zSuggestLater')
                        page.locator('[data-z-org="nord"]').wait_for()
                        self.assertEqual(page.locator('[data-z-org]').count(), 2)
                        page.click('[data-z-org="nord"]')
                        page.wait_for_url(base + '/')
                        page.wait_for_load_state('networkidle')
                        page.goto(base + '/#/firmen')
                        page.locator('#authBar [data-q-org]', has_text='Nord').wait_for()
                        page.locator('text=Nord Fiktiv GmbH >> visible=true').first.wait_for()
                        self.assertEqual(page.get_by_text('Süd Fiktiv GmbH').count(), 0)
                        page.click('#authBar [data-q-org]')
                        page.locator('[data-z-org="nord"]', has_text='aktuell').wait_for()
                        page.click('[data-z-org="sued"]')
                        page.wait_for_url(base + '/')
                        page.goto(base + '/#/firmen')
                        page.locator('#authBar [data-q-org]', has_text='Süd').wait_for()
                        page.locator('text=Süd Fiktiv GmbH >> visible=true').first.wait_for()
                        self.assertEqual(page.get_by_text('Nord Fiktiv GmbH').count(), 0)
                        page.goto(base + '/anmelden')
                        page.click('#zLogout')
                        page.locator('#zLogin').wait_for()
                        page.goto(base + '/')
                        page.wait_for_url(lambda u: '/anmelden' in u)
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
