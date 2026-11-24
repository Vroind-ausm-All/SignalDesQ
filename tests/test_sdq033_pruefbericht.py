"""SDQ-033 bis SDQ-043: Abnahmetests zu den Befunden der externen Sicherheitsprüfung vom 24.11.2026 (Stand dev64).

Je Befund ein Negativtest am Server oder an der Funktion. Alle Daten fiktiv, keine Netzzugriffe nach außen.
"""
import json
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from sales_tool import (accounts, audit_trail, auth, betreiber, bootstrap, caldav, datev, einladungen, hosting,  # noqa: E402
                        imap_drafts, mailer, tenancy)
from sales_tool.model import connect  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402
from sales_tool.research import settings as rsettings  # noqa: E402
from test_sdq014_multi_tenant import PW, Client  # noqa: E402

NEW_PW = 'Neue-Passphrase-4821'


class Base(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name) / 'm'
        self.dir = tenancy.Directory(self.root)
        self.nord = self.dir.create('nord', 'Nord')['db_path']
        self.sued = self.dir.create('sued', 'Süd')['db_path']
        accounts.create_account(self.dir, 'erika', PW, email='erika@nord.example')
        accounts.set_membership(self.dir, 'erika', 'nord', 'admin')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        hosting.unregister_all()
        rsettings.reset()
        self.tmp.cleanup()

    def account(self, name):
        with self.dir._connect() as conn:
            return conn.execute('SELECT * FROM accounts WHERE username=?', (name,)).fetchone()

    def client(self, name='erika', password=PW):
        c = Client(self.base)
        status, data, _ = c.login(name, password)
        self.assertEqual(status, 200, data)
        return c


class InvitationIdentityTests(Base):
    """F01: Einladung nur für das Konto mit der eingeladenen Adresse; Verbrauch und Rolle gemeinsam."""

    def _invite(self, email, role='vertrieb'):
        einladungen.invite(self.dir, self.account('erika'), 'nord', email, role)
        text = (self.root / mailer.FOLDER / mailer.outbox(self.dir, 1)[0]['file']).read_text(encoding='utf-8')
        return re.search(r'einladung=([A-Za-z0-9_-]+)', text).group(1)

    def test_other_account_cannot_take_invitation(self):
        token = self._invite('anna@nord.example', 'admin')
        accounts.create_account(self.dir, 'bert', PW, email='bert@anders.example')
        accounts.create_account(self.dir, 'ohne', PW)  # Konto ohne Adresse
        for name in ('bert', 'ohne'):
            with self.assertRaisesRegex(PermissionError, 'andere E-Mail-Adresse'):
                einladungen.accept(self.dir, token, account=self.account(name))
            self.assertIsNone(accounts.membership(self.dir, name, 'nord'))
        self.assertEqual(len(einladungen.pending(self.dir, 'nord')), 1)  # bleibt verwendbar
        accounts.create_account(self.dir, 'anna', PW, email='  Anna@Nord.Example ')
        out = einladungen.accept(self.dir, token, account=self.account('anna'))
        self.assertTrue(out['accepted'])
        self.assertEqual(accounts.membership(self.dir, 'anna', 'nord'), 'admin')
        with self.assertRaises(LookupError):
            einladungen.accept(self.dir, token, account=self.account('anna'))

    def test_over_http_wrong_account_gets_403_without_account_data(self):
        token = self._invite('anna@nord.example')
        accounts.create_account(self.dir, 'bert', PW, email='bert@anders.example')
        c = self.client('bert')
        status, data, _ = c.call('/api/zentral/einladung/annehmen', 'POST', {'token': token})
        self.assertEqual(status, 403, data)
        self.assertNotIn('bert@anders.example', json.dumps(data))
        self.assertIsNone(accounts.membership(self.dir, 'bert', 'nord'))

    def test_concurrent_use_creates_no_membership(self):
        token = self._invite('anna@nord.example', 'admin')
        accounts.create_account(self.dir, 'anna', PW, email='anna@nord.example')
        real = accounts.membership

        def race(*a, **kw):  # zwischen Prüfung und Festschreiben verbraucht ein zweiter Aufruf die Einladung
            with self.dir._connect() as conn:
                conn.execute("UPDATE invitations SET accepted_at=datetime('now'), accepted_by='anderer'")
            return real(*a, **kw)
        with mock.patch.object(accounts, 'membership', side_effect=race):
            with self.assertRaises(LookupError):
                einladungen.accept(self.dir, token, account=self.account('anna'))
        self.assertIsNone(accounts.membership(self.dir, 'anna', 'nord'))  # Rolle und Verbrauch nur gemeinsam


class RevocationTests(Base):
    """F02: Passwortwechsel, zweiter Faktor und Pflicht beenden Organisationssitzungen auf allen Geräten."""

    def test_password_change_ends_org_session_on_second_device(self):
        a, b = self.client(), self.client()
        self.assertEqual(b.call('/api/leads')[0], 200)
        status, data, _ = a.call('/api/zentral/password', 'POST', {'old': PW, 'new': NEW_PW})
        self.assertEqual(status, 200, data)
        self.assertEqual(b.call('/api/leads')[0], 401)
        self.assertEqual(b.call('/api/zentral/status')[1].get('logged_in'), False)
        self.assertEqual(self.client('erika', NEW_PW).call('/api/leads')[0], 200)

    def test_operator_reset_and_lock_end_sessions_in_all_orgs(self):
        accounts.set_membership(self.dir, 'erika', 'sued', 'vertrieb')
        n, s = self.client(), self.client()
        n.call('/api/zentral/enter', 'POST', {'slug': 'nord'})
        s.call('/api/zentral/enter', 'POST', {'slug': 'sued'})
        self.assertEqual((n.call('/api/leads')[0], s.call('/api/leads')[0]), (200, 200))
        accounts.reset_password(self.dir, 'erika', NEW_PW, actor='betreiber:test')
        self.assertEqual((n.call('/api/leads')[0], s.call('/api/leads')[0]), (401, 401))

    def test_mandatory_second_factor_applies_to_open_org_sessions(self):
        b = self.client()
        self.assertEqual(b.call('/api/leads')[0], 200)
        accounts.set_require_2fa(self.dir, True, actor='betreiber:test')
        self.assertEqual(b.call('/api/leads')[0], 401)

    def test_stamp_mismatch_alone_ends_session(self):
        b = self.client()
        with self.dir._connect() as conn:
            accounts._bump(conn, self.account('erika')['id'])
        self.assertEqual(b.call('/api/leads')[0], 401)


class ConnectorTests(Base):
    """F03: Zugänge nur durch die Verwaltung; ein neues Ziel bekommt nie das alte Passwort."""

    def test_sales_role_cannot_change_connectors(self):
        for route in ('/api/caldav', '/api/imap'):
            self.assertFalse(auth.allowed('vertrieb', 'POST', route))
            self.assertTrue(auth.allowed('vertrieb', 'GET', route))
            self.assertTrue(auth.allowed('admin', 'POST', route))
        self.assertTrue(auth.allowed('vertrieb', 'POST', '/api/caldav/sync'))

    def test_target_change_forgets_password(self):
        from sales_tool import credentials
        db = self.nord
        with connect(db) as conn, mock.patch.object(credentials, 'forget') as forget, \
                mock.patch.object(credentials, 'put') as put:
            caldav.save(conn, db, {'url': 'https://dav.alt.example/cal/', 'username': 'erika', 'password': 'app-pw-1'})
            self.assertEqual(put.call_count, 1)
            caldav.save(conn, db, {'username': 'erika'})  # gleiches Ziel: Passwort bleibt
            forget.assert_not_called()
            caldav.save(conn, db, {'url': 'https://dav.fremd.example/cal/'})
            forget.assert_called_once_with(db, 'caldav')
            forget.reset_mock()
            imap_drafts.save(conn, db, {'host': 'imap.alt.example', 'port': 993, 'username': 'erika', 'password': 'app-pw-2'})
            imap_drafts.save(conn, db, {'username': 'erika2'})
            forget.assert_called_once_with(db, 'imap')


class ResearchSettingsTests(Base):
    """F04/F05: Recherche-Schalter je Organisation; im Server kein Legacy-Abruf und kein Browser."""

    def test_settings_are_per_organisation(self):
        with connect(self.nord) as a, connect(self.sued) as b:
            rsettings.load(a)
            rsettings.load(b)
            rsettings.save(a, {'content': 'trafilatura', 'parser': 'auto'})
            self.assertEqual(rsettings.get(tenancy.conn_key(b))['content'], 'stdlib')
            rsettings.save(b, {'parser': 'scrapling'})
            self.assertEqual(rsettings.get(tenancy.conn_key(a))['parser'], 'auto')  # B übernimmt nichts von A und umgekehrt
            with tenancy.use(self.sued):
                self.assertEqual(rsettings.get()['content'], 'stdlib')

    def test_hosted_org_cannot_choose_legacy_or_browser(self):
        c = self.client()
        status, data, _ = c.call('/api/research/settings', 'POST', {'fetcher': 'legacy'})
        self.assertEqual(status, 403, data)
        with connect(self.nord) as conn:  # auch ein früher gespeicherter Wert wirkt nicht
            from sales_tool.quality import put_setting
            put_setting(conn, rsettings.KEY, {'fetcher': 'legacy', 'browser_fallback': True})
            conn.commit()
            rsettings.load(conn)
        key = tenancy.db_key(self.nord)
        self.assertEqual(rsettings.get(key)['fetcher'], 'http')
        self.assertFalse(rsettings.get(key)['browser_fallback'])
        from sales_tool.research.fetchers import browser
        from sales_tool.website_scorer import playwright_available
        with tenancy.use(self.nord):
            self.assertFalse(browser.available())
            self.assertFalse(playwright_available())
        # ein Einzelplatz im selben Prozess bleibt unberührt
        single = Path(self.tmp.name) / 'einzel.sqlite3'
        with connect(single) as conn:
            from sales_tool.model import init_db
            init_db(conn)
            rsettings.save(conn, {'fetcher': 'legacy'})
            self.assertEqual(rsettings.get(tenancy.conn_key(conn))['fetcher'], 'legacy')

    def test_hosted_connector_targets_must_be_public(self):
        self.assertEqual(self.client().call('/api/leads')[0], 200)  # Organisation wird mit der ersten Anfrage gehostet
        with tenancy.use(self.nord):
            for url in ('http://127.0.0.1:5232/cal/', 'https://localhost/cal/', 'https://10.0.0.5/cal/', 'https://dav.example:8443/'):
                with self.assertRaises(ValueError, msg=url):
                    caldav._check_url(url)
            for host, port in (('127.0.0.1', 1143), ('imap.example', 143), ('mail.internal', 993)):
                with self.assertRaises(ValueError, msg=host):
                    imap_drafts._check_host(host, port)
            with mock.patch('sales_tool.research.safe_urls.resolve_public', return_value=['192.168.1.9']) as rp:
                rp.side_effect = __import__('sales_tool.research.safe_urls', fromlist=['UnsafeURL']).UnsafeURL('privat')
                with self.assertRaises(ValueError):
                    caldav._check_url('https://dav.anbieter.example/cal/')
            with mock.patch('sales_tool.research.safe_urls.resolve_public', return_value=['203.0.113.7']):
                self.assertEqual(caldav._check_url('https://dav.anbieter.example/cal/'), 'https://dav.anbieter.example/cal/')
        self.assertEqual(caldav._check_url('http://127.0.0.1:5232/cal/'), 'http://127.0.0.1:5232/cal/')  # Einzelplatz: Testziel ok

    def test_web_restore_blocked_in_server(self):
        c = self.client()
        status, data, _ = c.call('/api/backups/restore', 'POST', {'name': 'x.sqlite3', 'confirm': True})
        self.assertEqual(status, 403, data)
        self.assertIn('betreiber', data['error'])


class ProxyAndReadinessTests(Base):
    """F08: Client-IP nur über einen eingetragenen Proxy; F10: öffentliche Bereitschaft zwischengespeichert."""

    def _server(self, **kw):
        srv = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir, **kw))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f'http://127.0.0.1:{srv.server_port}'

    def _fail_until_throttled(self, base, ip):
        c = Client(base)
        codes = [c.call('/api/zentral/login', 'POST', {'username': f'x{i}', 'password': 'falsch-falsch'},
                        headers={'X-Forwarded-For': ip})[0] for i in range(accounts.FAIL_LIMIT + 1)]
        return codes

    def test_forwarded_for_only_from_trusted_proxy(self):
        base = self._server(trusted_proxies=['127.0.0.1'])
        self.assertEqual(self._fail_until_throttled(base, '198.51.100.1')[-1], 429)
        # ein anderer Client hinter demselben Proxy hat sein eigenes Budget
        c = Client(base)
        self.assertEqual(c.call('/api/zentral/login', 'POST', {'username': 'erika', 'password': PW},
                                headers={'X-Forwarded-For': '198.51.100.2'})[0], 200)
        # Rechts steht, was der Proxy angehängt hat; selbst gesetzte Einträge davor zählen nicht
        h = Client(base)
        self.assertEqual(h.call('/api/zentral/login', 'POST', {'username': 'erika', 'password': PW},
                                headers={'X-Forwarded-For': '198.51.100.2, 198.51.100.1'})[0], 429)

    def test_untrusted_forwarded_for_is_ignored(self):
        base = self._server()  # ohne eingetragenen Proxy
        self._fail_until_throttled(base, '198.51.100.1')
        c = Client(base)
        self.assertEqual(c.call('/api/zentral/login', 'POST', {'username': 'erika', 'password': PW},
                                headers={'X-Forwarded-For': '198.51.100.99'})[0], 429)

    def test_public_readiness_is_cached(self):
        base = self._server(ready_cache_seconds=60)
        from sales_tool import ops
        with mock.patch.object(ops, 'readiness', wraps=ops.readiness) as ready:
            for _ in range(5):
                status, data, _ = Client(base).call('/readyz', headers={'X-Forwarded-For': '203.0.113.7'})
                self.assertEqual(set(data), {'status', 'version'})
            self.assertEqual(ready.call_count, 1)
            Client(base).call('/readyz')  # lokal (Überwachung): immer frisch und mit Einzelheiten
            self.assertEqual(ready.call_count, 2)


class PasswordHashTests(Base):
    """F09: stärkeres scrypt-Profil, alte Hashes werden beim richtigen Login erneuert, beim falschen nicht."""

    def test_old_hash_upgraded_on_login_only(self):
        import hashlib
        import secrets
        salt = secrets.token_bytes(16)
        old = f"scrypt$16384$8$1${salt.hex()}${hashlib.scrypt(PW.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32).hex()}"
        self.assertTrue(auth.verify_password(PW, old))
        self.assertTrue(auth.needs_rehash(old))
        self.assertFalse(auth.needs_rehash(auth.hash_password(PW)))
        with self.dir._connect() as conn:
            conn.execute('UPDATE accounts SET pw_hash=? WHERE username=?', (old, 'erika'))
        self.assertEqual(Client(self.base).login('erika', 'falsch-falsch')[0], 401)
        self.assertEqual(self.account('erika')['pw_hash'], old)
        self.assertEqual(Client(self.base).login('erika')[0], 200)
        new = self.account('erika')['pw_hash']
        self.assertTrue(new.startswith(f'scrypt$16384$8${auth.SCRYPT_P}$'))
        self.assertTrue(auth.verify_password(PW, new))


class DatevFormulaTests(unittest.TestCase):
    """F11: keine Formelanfänge in Text- und Belegfeldern des DATEV-Stapels."""

    def test_formula_starts_removed(self):
        for raw in ('=HYPERLINK("http://x")', '+1+1', '-2+3', '@SUMME(A1)', '\t=1', ' =1'):
            out = datev._text(raw, 60)
            self.assertNotRegex(out, r'^"[=+\-@\t]', raw)
        self.assertEqual(datev._text('Fiktiv GmbH - Nord', 60), '"Fiktiv GmbH - Nord"')
        self.assertEqual(datev._beleg('-R-2026-7'), '"R-2026-7"')


class AuditAnchorTests(Base):
    """F12: Ein extern hinterlegter Anker zeigt ein gekürztes Protokoll."""

    def test_truncation_detected_with_anchor(self):
        audit_trail.record(self.dir, 'betreiber:test', 'probe', 'a')
        with mock.patch('sys.stdout', new=StringIO()) as so:
            self.assertEqual(betreiber.main(['--root', str(self.root), 'protokoll-anker']), 0)
        anchor_file = Path(self.tmp.name) / 'anker.json'
        text = so.getvalue()
        anchor_file.write_text(text[text.index('{'):], encoding='utf-8')
        anchor = json.loads(anchor_file.read_text(encoding='utf-8'))
        self.assertEqual(anchor['format'], 'signaldesk-protokoll-anker-1')
        audit_trail.record(self.dir, 'betreiber:test', 'probe', 'b')
        self.assertTrue(audit_trail.verify_anchor(self.dir, anchor)['ok'])
        with sqlite3.connect(self.root / 'organisationen.sqlite3') as c:  # Ende abschneiden: Kette selbst bleibt „gültig“
            c.execute('DELETE FROM audit_events WHERE id >= ?', (anchor['last_id'],))
        self.assertTrue(audit_trail.verify(self.dir)['ok'])
        out = audit_trail.verify_anchor(self.dir, anchor)
        self.assertFalse(out['ok'])
        self.assertIn('gekürzt', out['reason'])
        with mock.patch('sys.stdout', new=StringIO()):
            self.assertEqual(betreiber.main(['--root', str(self.root), 'protokoll-pruefen', '--anker', str(anchor_file)]), 1)


class SupplyChainTests(unittest.TestCase):
    """F07: kein betroffenes cryptography im Lock, keine Installation ohne Prüfsummen."""

    def test_team_lock_has_fixed_cryptography(self):
        text = (ROOT / 'requirements-lock-team.txt').read_text(encoding='utf-8')
        version = re.search(r'^cryptography==([\d.]+)', text, re.M).group(1)
        self.assertGreaterEqual(tuple(int(x) for x in version.split('.')), (48, 0, 1))

    def test_missing_lock_refuses_install(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(bootstrap, 'lock_files', return_value=[Path(tmp) / 'requirements-lock-team.txt']), \
                mock.patch.object(bootstrap, 'read_marker', return_value={}), \
                mock.patch.object(bootstrap, 'write_marker'), \
                mock.patch.object(bootstrap, 'run', side_effect=lambda cmd, **kw: calls.append(cmd) or True), \
                mock.patch.object(bootstrap, 'say'):
            ok = bootstrap.ensure_crawler(Path(tmp) / 'python', variant='team')
        self.assertFalse(ok)
        self.assertEqual(calls, [])  # weder pip noch Browser-Download


if __name__ == '__main__':
    unittest.main()
