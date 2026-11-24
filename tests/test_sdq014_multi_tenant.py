"""SDQ-014/015/016: Zentrale Anmeldung und Server für mehrere Organisationen – Negativtests über Mandantengrenzen per HTTP.

Geprüft wird, dass jede Anfrage nur mit gültiger Sitzung in genau einer Organisation weitergereicht wird: Eine gefälschte
Organisation im Cookie, ein Sitzungstoken einer anderen Organisation, eine entzogene Mitgliedschaft, ein gesperrtes Konto und
eine archivierte Organisation führen alle zur Anmeldung zurück. Alle Daten sind fiktiv."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import accounts, auth, tenancy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402

PW = 'Lange-Passphrase-7391'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Client:
    """Kleiner HTTP-Client mit eigener, sichtbarer Cookie-Ablage (damit Tests Cookies gezielt fälschen können)."""

    def __init__(self, base):
        self.base, self.cookies = base, {}
        self.opener = urllib.request.build_opener(_NoRedirect)

    def call(self, path, method='GET', body=None, headers=None):
        hdr = {'Cookie': '; '.join(f'{k}={v}' for k, v in self.cookies.items()), **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            hdr['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdr)
        try:
            res = self.opener.open(req)
        except urllib.error.HTTPError as exc:
            res = exc
        for raw in res.headers.get_all('Set-Cookie') or []:
            name, _, rest = raw.partition('=')
            value = rest.split(';', 1)[0]
            if 'Max-Age=0' in raw:
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value
        text = res.read().decode('utf-8', 'replace')
        try:
            payload = json.loads(text) if text else None
        except json.JSONDecodeError:
            payload = text
        return res.status, payload, res.headers

    def login(self, username, password=PW):
        return self.call('/api/zentral/login', 'POST', {'username': username, 'password': password})


class MultiTenantTests(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        for slug, name in (('nord', 'Nord'), ('sued', 'Süd')):
            org = self.dir.create(slug, name)
            with connect(org['db_path']) as conn:
                conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'neu')", (f'{name} Fiktiv GmbH',))
                conn.commit()
        accounts.create_account(self.dir, 'erika', PW, 'Erika Beispiel')
        accounts.set_membership(self.dir, 'erika', 'nord', 'vertrieb')
        accounts.create_account(self.dir, 'max', PW)
        accounts.set_membership(self.dir, 'max', 'sued', 'admin')
        accounts.create_account(self.dir, 'beide', PW)
        accounts.set_membership(self.dir, 'beide', 'nord', 'lesen')
        accounts.set_membership(self.dir, 'beide', 'sued', 'buchhaltung')
        accounts.create_account(self.dir, 'ohne', PW)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        auth._FAILS.clear()
        self.tmp.cleanup()

    def companies(self, client):
        status, data, _ = client.call('/api/leads')
        if status != 200:
            return status
        rows = data if isinstance(data, list) else data.get('leads', data.get('items', []))
        return {r['company'] for r in rows}

    def test_without_login_only_login_page_and_program_files(self):
        c = Client(self.base)
        status, _, headers = c.call('/')
        self.assertEqual((status, headers['Location']), (302, '/anmelden'))
        status, data, _ = c.call('/api/leads')
        self.assertEqual((status, data['login_url']), (401, '/anmelden'))
        self.assertEqual(c.call('/anmelden')[0], 200)
        self.assertEqual(c.call('/zentral.js')[0], 200)
        self.assertEqual(c.call('/app.js')[0], 200)
        self.assertEqual(c.call('/rechnung/1')[0], 302)
        self.assertEqual(c.call('/api/zentral/status')[1], {'logged_in': False, 'registration_open': False})  # dev64: Registrierung ist standardmäßig aus

    def test_single_membership_enters_directly_and_sees_only_own_data(self):
        c = Client(self.base)
        status, data, _ = c.login('erika')
        self.assertEqual((status, data['entered']), (200, 'nord'))
        self.assertEqual(self.companies(c), {'Nord Fiktiv GmbH'})
        status, me, _ = c.call('/api/auth/status')
        self.assertEqual((me['user']['username'], me['user']['role'], me['auth_required']), ('erika', 'vertrieb', True))
        self.assertEqual((me['central'], me['organization']), (True, {'slug': 'nord', 'name': 'Nord'}))

    def test_forged_organisation_cookie_is_rejected(self):
        c = Client(self.base)
        c.login('erika')
        c.cookies[accounts.ORG_COOKIE] = 'sued'
        self.assertEqual(self.companies(c), 401, 'Sitzung aus Nord gilt nicht in Süd')
        c.cookies[accounts.ORG_COOKIE] = '../nord'
        self.assertEqual(self.companies(c), 401)

    def test_session_of_another_organisation_is_rejected(self):
        erika, max_ = Client(self.base), Client(self.base)
        erika.login('erika')
        max_.login('max')
        stolen = Client(self.base)
        stolen.cookies = {accounts.ORG_COOKIE: 'nord', auth.COOKIE: max_.cookies[auth.COOKIE]}
        self.assertEqual(self.companies(stolen), 401)

    def test_roles_follow_membership(self):
        c = Client(self.base)
        status, data, _ = c.login('beide')
        self.assertEqual((status, data['entered'], {o['slug'] for o in data['organizations']}), (200, None, {'nord', 'sued'}))
        self.assertEqual(self.companies(c), 401, 'erst eine Organisation wählen')
        self.assertEqual(c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 200)
        self.assertEqual(self.companies(c), {'Nord Fiktiv GmbH'})
        self.assertEqual(c.call('/api/leads', 'POST', {'company': 'Neu GmbH', 'stage': 'neu'})[0], 403, 'lesen darf nicht schreiben')
        old_token = c.cookies[auth.COOKIE]
        self.assertEqual(c.call('/api/zentral/enter', 'POST', {'slug': 'sued'})[0], 200)
        self.assertEqual(self.companies(c), {'Süd Fiktiv GmbH'})
        self.assertEqual(c.call('/api/leads', 'POST', {'company': 'Neu GmbH', 'stage': 'neu'})[0], 403, 'Buchhaltung legt keine Firmen an')
        replay = Client(self.base)
        replay.cookies = {accounts.ORG_COOKIE: 'nord', auth.COOKIE: old_token}
        self.assertEqual(self.companies(replay), 401, 'Wechsel beendet die alte Sitzung')
        self.assertEqual(c.call('/api/zentral/enter', 'POST', {'slug': 'unbekannt'})[0], 403)

    def test_role_change_applies_on_next_request(self):
        c = Client(self.base)
        c.login('erika')
        accounts.set_membership(self.dir, 'erika', 'nord', 'lesen')
        self.assertEqual(c.call('/api/leads', 'POST', {'company': 'Neu GmbH', 'stage': 'neu'})[0], 403)

    def test_revoked_membership_ends_access_immediately(self):
        c = Client(self.base)
        c.login('erika')
        self.assertEqual(self.companies(c), {'Nord Fiktiv GmbH'})
        accounts.remove_membership(self.dir, 'erika', 'nord')
        self.assertEqual(self.companies(c), 401)
        with connect(self.dir.open('nord')) as conn:
            row = conn.execute("SELECT active FROM users WHERE username='erika'").fetchone()
            self.assertEqual(row['active'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_revocation_checked_even_if_organisation_db_not_updated(self):
        """Mitgliedschaft nur im Verzeichnis entfernt (z. B. Organisation gerade nicht erreichbar): trotzdem kein Zugang."""
        c = Client(self.base)
        c.login('erika')
        with self.dir._connect() as conn:
            conn.execute("DELETE FROM memberships WHERE slug='nord'")
        self.assertEqual(self.companies(c), 401)

    def test_locked_account_and_archived_organisation(self):
        c, m = Client(self.base), Client(self.base)
        c.login('erika')
        m.login('max')
        accounts.set_active(self.dir, 'erika', False)
        self.assertEqual(self.companies(c), 401)
        self.assertEqual(c.login('erika')[0], 401)
        self.dir.archive('sued')
        self.assertEqual(self.companies(m), 401)
        status, data, _ = m.login('max')
        self.assertEqual((status, data['entered'], data['organizations']), (200, None, []))

    def test_account_without_membership(self):
        c = Client(self.base)
        status, data, _ = c.login('ohne')
        self.assertEqual((status, data['entered'], data['organizations']), (200, None, []))
        self.assertEqual(c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 403)

    def test_local_login_and_user_admin_are_central(self):
        c = Client(self.base)
        c.login('max')
        for method, path, body in (('POST', '/api/auth/login', {'username': 'max', 'password': PW}),
                                   ('POST', '/api/auth/setup', {'username': 'x', 'password': PW}),
                                   ('PUT', '/api/auth/settings', {'auth_required': False}),
                                   ('POST', '/api/auth/password', {'old': PW, 'new': PW + 'x'}),
                                   ('GET', '/api/auth/users', None)):
            self.assertEqual(c.call(path, method, body)[0], 403, path)
        with connect(self.dir.open('sued')) as conn:
            with self.assertRaises(auth.NotLoggedIn, msg='kein eigenes Passwort in der Organisation'):
                auth.login(conn, {'username': 'max', 'password': PW}, client='t')

    def test_logout_and_password_change(self):
        c = Client(self.base)
        c.login('erika')
        token = c.cookies[auth.COOKIE]
        self.assertEqual(c.call('/api/auth/logout', 'POST', {})[0], 200)
        self.assertEqual(self.companies(c), 401)
        replay = Client(self.base)
        replay.cookies = {accounts.ORG_COOKIE: 'nord', auth.COOKIE: token}
        self.assertEqual(self.companies(replay), 401, 'Abmelden beendet die Sitzung in der Organisation')
        self.assertFalse(c.call('/api/zentral/status')[1]['logged_in'])
        c.login('erika')
        self.assertEqual(c.call('/api/zentral/password', 'POST', {'old': 'falsch-falsch', 'new': 'Neue-Passphrase-4821'})[0], 403)
        self.assertEqual(c.call('/api/zentral/password', 'POST', {'old': PW, 'new': 'Neue-Passphrase-4821'})[0], 200)
        self.assertEqual(self.companies(c), 401)
        self.assertEqual(c.login('erika')[0], 401)
        self.assertEqual(c.login('erika', 'Neue-Passphrase-4821')[0], 200)

    def test_throttle_and_foreign_origin(self):
        c = Client(self.base)
        for _ in range(auth.MAX_FAILS):
            self.assertEqual(c.login('erika', 'falsch-falsch')[0], 401)
        self.assertEqual(c.login('erika')[0], 429)
        auth._FAILS.clear()
        d = Client(self.base)
        status, _, _ = d.call('/api/zentral/login', 'POST', {'username': 'erika', 'password': PW}, headers={'Origin': 'http://evil.example'})
        self.assertEqual(status, 403)

    def test_unknown_host_rejected(self):
        c = Client(self.base)
        self.assertEqual(c.call('/anmelden', headers={'Host': 'evil.example'})[0], 421)


class AccountRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        self.dir.create('nord', 'Nord')

    def tearDown(self):
        self.tmp.cleanup()

    def test_rules(self):
        with self.assertRaises(ValueError):
            accounts.create_account(self.dir, 'erika', 'kurz')
        accounts.create_account(self.dir, 'erika', PW)
        with self.assertRaises(ValueError):
            accounts.create_account(self.dir, 'ERIKA', PW)
        with self.assertRaises(ValueError):
            accounts.set_membership(self.dir, 'erika', 'nord', 'chef')
        with self.assertRaises(LookupError):
            accounts.set_membership(self.dir, 'erika', 'sued', 'lesen')
        with self.assertRaises(LookupError):
            accounts.set_membership(self.dir, 'niemand', 'nord', 'lesen')
        with self.dir._connect() as conn:
            stored = conn.execute("SELECT pw_hash FROM accounts WHERE username='erika'").fetchone()[0]
        self.assertNotIn(PW, stored)
        self.assertTrue(stored.startswith('scrypt$'))


if __name__ == '__main__':
    unittest.main()
