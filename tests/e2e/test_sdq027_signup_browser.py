"""Browserprüfung SDQ-027/028: Organisation registrieren, Link aus dem Postausgang öffnen, anmelden, jemanden einladen und
die Einladung mit neuem Konto annehmen – auf Telefonbreite. Nichts wird versendet; fiktive Daten, keine Abrufe nach außen."""
import os
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool import accounts, mailer, tenancy
from sales_tool.multi_server import make_multi_handler

PW = 'Lange-Passphrase-7391'


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class SignupBrowserTests(unittest.TestCase):
    def test_register_confirm_invite_accept(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = tenancy.Directory(Path(tmp) / 'm')
            accounts.set_setting(d, 'registrierung', 'offen')
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(d))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            accounts.set_setting(d, 'public_url', base)

            def link(kind):
                text = (d.root / mailer.FOLDER / mailer.outbox(d, 1)[0]['file']).read_text(encoding='utf-8')
                return re.search(r'(http://\S+#' + kind + r'=[A-Za-z0-9_-]+)', text).group(1)
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 390, 'height': 844})
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/anmelden')
                        page.click('#zToRegister')
                        f = '#zRegister '
                        page.fill(f + '[name=email]', 'erika@studio.example')
                        page.fill(f + '[name=org_name]', 'Studio Nord')
                        page.fill(f + '[name=username]', 'erika')
                        page.fill(f + '[name=password]', PW)
                        page.click(f + 'button[type=submit]')
                        page.locator('#zMsg', has_text='Postausgang').wait_for()
                        self.assertEqual(d.list(), [])
                        page.goto(link('bestaetigen'))
                        page.locator('#zMsg', has_text='Registrierung bestätigt').wait_for()
                        self.assertNotIn('bestaetigen', page.url)  # Link verschwindet aus der Adresszeile
                        self.assertEqual(page.input_value('#zLogin [name=username]'), 'erika')
                        page.fill('#zLogin [name=password]', PW)
                        page.click('#zLogin button[type=submit]')
                        page.wait_for_url(base + '/')
                        page.goto(base + '/anmelden')
                        page.click('[data-z-team="studio-nord"]')
                        page.locator('#zTeamPlan', has_text='Testphase').wait_for()
                        page.fill('#zTeamInvite [name=email]', 'max@studio.example')
                        page.select_option('#zTeamInvite [name=role]', 'buchhaltung')
                        page.click('#zTeamInvite button[type=submit]')
                        page.locator('#zTeamInvites li', has_text='max@studio.example').wait_for()
                        self.assertEqual(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), True)
                        invite = link('einladung')
                        page.click('[data-z-orgs]')
                        page.click('#zLogout')
                        page.locator('#zLogin >> visible=true').wait_for()
                        page.goto(invite)
                        page.locator('#zInviteInfo', has_text='Studio Nord').wait_for()
                        page.fill('#zInviteNew [name=username]', 'max')
                        page.fill('#zInviteNew [name=password]', 'Noch-eine-Passphrase-42')
                        page.click('#zInviteNew button[type=submit]')
                        page.locator('#zMsg', has_text='beigetreten').wait_for()
                        self.assertEqual(accounts.membership(d, 'max', 'studio-nord'), 'buchhaltung')
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
