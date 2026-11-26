"""Browserprüfung SDQ-021: Zwei-Faktor-Pflicht in der Mehrmandanten-Installation – Einrichtung bei der ersten Anmeldung,
Wiederherstellungscodes, danach Anmeldung nur mit Code aus der App. Fiktives Konto, keine Abrufe nach außen."""
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from sales_tool import accounts, tenancy, totp
from sales_tool.model import connect
from sales_tool.multi_server import make_multi_handler

PW = 'Lange-Passphrase-7391'


def _next_code(secret):
    return totp.hotp(totp._key(secret), totp.step(time.time()) + 1)


@unittest.skipUnless(sync_playwright, 'Playwright optional')
class TwoFactorBrowserTests(unittest.TestCase):
    def test_required_setup_then_code_login(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = tenancy.Directory(Path(tmp) / 'm')
            org = d.create('nord', 'Nord')
            with connect(org['db_path']) as conn:
                conn.execute("INSERT INTO leads(company, stage) VALUES ('Nord Fiktiv GmbH', 'neu')")
                conn.commit()
            accounts.create_account(d, 'erika', PW, 'Erika Beispiel')
            accounts.set_membership(d, 'erika', 'nord', 'vertrieb')
            accounts.set_require_2fa(d, True)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(d))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 390, 'height': 844})  # Telefonbreite: Einrichtung unterwegs
                        errors, outside = [], []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))
                        page.on('request', lambda r: outside.append(r.url) if '127.0.0.1' not in r.url else None)
                        page.goto(base + '/anmelden')
                        page.fill('#zLogin [name=username]', 'erika')
                        page.fill('#zLogin [name=password]', PW)
                        page.click('#zLogin button[type=submit]')
                        # Pflicht: zuerst einrichten, keine Organisationen sichtbar
                        page.locator('#zSetup >> visible=true').wait_for()
                        self.assertEqual(page.locator('[data-z-org]').count(), 0)
                        page.fill('#zSetupStart [name=password]', PW)
                        page.click('#zSetupStart button[type=submit]')
                        page.locator('[data-z-secret] >> visible=true').wait_for()
                        secret = page.locator('[data-z-secret]').inner_text().replace(' ', '')
                        self.assertRegex(secret, r'^[A-Z2-7]{32}$')
                        self.assertEqual(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), True)
                        page.fill('#zSetupConfirm [name=code]', '000000' if totp.code(secret) != '000000' else '111111')
                        page.click('#zSetupConfirm button[type=submit]')
                        page.locator('#zMsg', has_text='Code stimmt nicht').wait_for()
                        page.fill('#zSetupConfirm [name=code]', totp.code(secret))
                        page.click('#zSetupConfirm button[type=submit]')
                        page.locator('#zCodeList li').first.wait_for()
                        self.assertEqual(page.locator('#zCodeList li').count(), accounts.RECOVERY_CODES)
                        page.click('#zCodesDone')
                        page.locator('[data-z-org="nord"]').wait_for()
                        page.locator('#zMfaState', has_text='an').wait_for(state='attached')
                        page.click('#zLogout')
                        page.locator('#zLogin >> visible=true').wait_for()
                        # Zweite Anmeldung: Passwort, dann Code aus der App
                        page.fill('#zLogin [name=username]', 'erika')
                        page.fill('#zLogin [name=password]', PW)
                        page.click('#zLogin button[type=submit]')
                        page.locator('#zCode >> visible=true').wait_for()
                        self.assertEqual(page.locator('[data-z-org]').count(), 0)
                        page.fill('#zCode [name=code]', _next_code(secret))
                        page.click('#zCode button[type=submit]')
                        page.wait_for_url(base + '/')  # genau eine Organisation: direkt hinein
                        page.goto(base + '/#/firmen')
                        page.locator('text=Nord Fiktiv GmbH >> visible=true').first.wait_for()
                        self.assertEqual(errors, [])
                        self.assertEqual(outside, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


    def test_optional_suggestion_later_and_setup(self):
        """dev68: ohne Pflicht wird der zweite Faktor nach der Anmeldung empfohlen; „Später“ führt hinein, „Jetzt einrichten“ richtet ein."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = tenancy.Directory(Path(tmp) / 'm')
            org = d.create('nord', 'Nord')
            with connect(org['db_path']) as conn:
                conn.execute("INSERT INTO leads(company, stage) VALUES ('Nord Fiktiv GmbH', 'neu')")
                conn.commit()
            accounts.create_account(d, 'erika', PW, 'Erika Beispiel')
            accounts.set_membership(d, 'erika', 'nord', 'vertrieb')
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(d))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None)
                    try:
                        page = browser.new_page(viewport={'width': 390, 'height': 844})
                        errors = []
                        page.on('pageerror', lambda exc: errors.append(str(exc)))

                        def login():
                            page.goto(base + '/anmelden')
                            page.fill('#zLogin [name=username]', 'erika')
                            page.fill('#zLogin [name=password]', PW)
                            page.click('#zLogin button[type=submit]')
                            page.locator('#zSuggest >> visible=true').wait_for()

                        login()
                        page.click('#zSuggestLater')
                        page.wait_for_url(base + '/')  # freiwillig: direkt hinein
                        page.goto(base + '/#/firmen')
                        page.locator('text=Nord Fiktiv GmbH >> visible=true').first.wait_for()
                        page.context.clear_cookies()
                        login()  # ohne zweiten Faktor: wieder gefragt
                        page.click('#zSuggestYes')
                        page.locator('#zSetup >> visible=true').wait_for()
                        page.locator('#zSetupWhy', has_text='zusätzlich einen Code').wait_for()
                        page.fill('#zSetupStart [name=password]', PW)
                        page.click('#zSetupStart button[type=submit]')
                        page.locator('[data-z-secret] >> visible=true').wait_for()
                        secret = page.locator('[data-z-secret]').inner_text().replace(' ', '')
                        page.fill('#zSetupConfirm [name=code]', totp.code(secret))
                        page.click('#zSetupConfirm button[type=submit]')
                        page.locator('#zCodeList li').first.wait_for()
                        page.click('#zCodesDone')
                        page.locator('[data-z-org="nord"]').wait_for()
                        page.locator('#zMfaState', has_text='an').wait_for(state='attached')
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
