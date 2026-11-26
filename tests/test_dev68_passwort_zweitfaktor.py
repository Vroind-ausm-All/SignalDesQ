"""2.0.0-dev68: Passwortregel und empfohlener zweiter Faktor.

Passwortregel: mindestens 12 Zeichen, Groß- und Kleinbuchstaben, mindestens ein Sonderzeichen – überall, wo ein Passwort gesetzt
wird (Einzelplatz-Team, zentrale Konten, Registrierung, Einladung, Passwortwechsel). Bestehende Passwörter gelten weiter.
Zweiter Faktor: empfohlen und nach jeder Anmeldung ohne ihn angeboten (``suggest_2fa``), aber ohne Pflicht nicht nötig, um eine
Organisation zu betreten. Alle Daten fiktiv."""
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from sales_tool import accounts, auth, tenancy, totp  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402
from test_sdq014_multi_tenant import PW, Client  # noqa: E402


class PasswordRuleTests(unittest.TestCase):
    def test_rule_values(self):
        self.assertEqual(auth.MIN_PASSWORD, 12)

    def test_accepted(self):
        for pw in ('Lange-Passphrase-7391', 'Sommer!Regen#Ab', 'Äpfel_und_Birnen', 'Kurz genug? Nein!', 'Zwölf#Zeiche'):
            with self.subTest(pw=pw):
                auth._check_password_policy(pw, 'erika')

    def test_rejected_with_reason(self):
        cases = {
            'Kurz-Pass1!': 'mindestens 12 Zeichen',               # 11 Zeichen
            'langepassphrase-7391': 'ein Großbuchstabe',
            'LANGEPASSPHRASE-7391': 'ein Kleinbuchstabe',
            'LangePassphrase7391': 'ein Sonderzeichen',
            'Lange Passphrase 7391': 'ein Sonderzeichen',          # Leerzeichen zählt nicht als Sonderzeichen
            'nurkleinbuchstaben': 'ein Großbuchstabe, ein Sonderzeichen',
        }
        for pw, reason in cases.items():
            with self.subTest(pw=pw):
                with self.assertRaises(ValueError) as cm:
                    auth._check_password_policy(pw)
                self.assertIn(reason, str(cm.exception))
                self.assertIn('mindestens 12 Zeichen, Groß- und Kleinbuchstaben und ein Sonderzeichen', str(cm.exception))

    def test_old_rules_still_apply(self):
        with self.assertRaises(ValueError):
            auth._check_password_policy('Erika.Beispiel-2026', 'erika.beispiel')   # enthält den Benutzernamen
        with self.assertRaises(ValueError):
            auth._check_password_policy('A' + 'a' * 200 + '!')                      # über 200 Zeichen
        with self.assertRaises(ValueError):
            auth._check_password_policy(None)

    def test_every_way_to_set_a_password_checks_the_rule(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = tenancy.Directory(Path(tmp) / 'm')
            weak = 'langepassphrase-7391'
            with self.assertRaises(ValueError):
                accounts.create_account(d, 'erika', weak)
            accounts.create_account(d, 'erika', PW)
            with self.assertRaises(ValueError):
                accounts.reset_password(d, 'erika', weak)
            with self.assertRaises(ValueError):
                accounts.change_password(d, 'erika', PW, weak)
            accounts.change_password(d, 'erika', PW, 'Neue-Passphrase#2026')
            conn = connect(Path(tmp) / 'einzel.sqlite3')
            init_db(conn)
            try:
                with self.assertRaises(ValueError):
                    auth.setup_admin(conn, {'username': 'anna.admin', 'password': weak})
                admin = auth.setup_admin(conn, {'username': 'anna.admin', 'password': PW})
                with self.assertRaises(ValueError):
                    auth.create_user(conn, {'username': 'max.muster', 'password': weak, 'role': 'vertrieb'}, dict(admin))
                with self.assertRaises(ValueError):
                    auth.change_password(conn, dict(conn.execute('SELECT * FROM users WHERE id=?', (admin['id'],)).fetchone()), {'old_password': PW, 'new_password': weak})
            finally:
                conn.close()

    def test_existing_weaker_password_still_logs_in(self):
        """Die Regel gilt beim Setzen. Ein früher gesetztes Passwort (10 Zeichen, ohne Sonderzeichen) bleibt gültig."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            d = tenancy.Directory(Path(tmp) / 'm')
            accounts.create_account(d, 'erika', None, pw_hash=auth.hash_password('altpasswort'))
            view, _ = accounts.login(d, 'erika', 'altpasswort')
            self.assertEqual(view['stage'], 'voll')

    def test_forms_name_the_rule(self):
        for name in ('zentral.html', 'quality.js'):
            text = (ROOT / 'sales_tool' / 'public' / name).read_text(encoding='utf-8')
            with self.subTest(name=name):
                self.assertNotIn('mind. 10 Zeichen', text)
                self.assertNotIn('minlength="10"', text)
                self.assertIn('mind. 12 Zeichen, Groß- und Kleinbuchstaben, ein Sonderzeichen', text)


class SuggestTwoFactorTests(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        self.dir.create('nord', 'Nord')
        accounts.create_account(self.dir, 'erika', PW, 'Erika Beispiel')
        accounts.set_membership(self.dir, 'erika', 'nord', 'vertrieb')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_suggested_but_not_required(self):
        c = Client(self.base)
        status, data, _ = c.login('erika')
        self.assertEqual((status, data['stage'], data['suggest_2fa']), (200, 'voll', True))
        self.assertEqual(data['entered'], 'nord')               # freiwillig: Zutritt wie bisher
        self.assertEqual(c.call('/api/leads')[0], 200)
        status, data, _ = c.call('/api/zentral/status')
        self.assertEqual((data['two_factor'], data['require_2fa'], data['suggest_2fa']), (False, False, True))

    def test_no_suggestion_once_set_up(self):
        c = Client(self.base)
        c.login('erika')
        status, data, _ = c.call('/api/zentral/2fa/start', 'POST', {'password': PW})
        secret = data['secret'].replace(' ', '')
        self.assertEqual(c.call('/api/zentral/2fa/confirm', 'POST', {'code': totp.code(secret)})[0], 200)
        self.assertFalse(c.call('/api/zentral/status')[1]['suggest_2fa'])
        c2 = Client(self.base)
        status, data, _ = c2.login('erika')
        self.assertEqual(data['stage'], 'zweitfaktor')
        import time
        status, data, _ = c2.call('/api/zentral/code', 'POST', {'code': totp.hotp(totp._key(secret), totp.step(time.time()) + 1)})
        self.assertEqual(status, 200, data)
        self.assertFalse(data['suggest_2fa'])

    def test_required_stays_required(self):
        accounts.set_require_2fa(self.dir, True)
        status, data, _ = Client(self.base).login('erika')
        self.assertEqual(data['stage'], 'einrichtung')
        self.assertNotIn('entered', data)

    def test_login_page_offers_setup_and_later(self):
        html = (ROOT / 'sales_tool' / 'public' / 'zentral.html').read_text(encoding='utf-8')
        js = (ROOT / 'sales_tool' / 'public' / 'zentral.js').read_text(encoding='utf-8')
        for needle in ('id="zSuggest"', 'id="zSuggestYes"', 'id="zSuggestLater"', 'Zwei-Faktor-Anmeldung empfohlen'):
            self.assertIn(needle, html)
        self.assertIn('r.suggest_2fa', js)
        self.assertIn("'#zSuggest'", js)


if __name__ == '__main__':
    unittest.main()
