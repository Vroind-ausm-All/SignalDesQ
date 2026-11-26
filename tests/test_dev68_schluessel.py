"""2.0.0-dev68: Entscheidungen vom 26.11.2026 – Python 3.10 ankündigen, TOTP-Geheimnisse mit Server-Schlüssel verschlüsseln
(Prüfbericht F09), Sicherungssätze mit Ed25519 signieren (F06). Alle Daten fiktiv, alles in temporären Ordnern."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from sales_tool import accounts, auth, betreiber, ops, python_support, schluessel, tenancy, totp  # noqa: E402
from test_sdq014_multi_tenant import PW  # noqa: E402


class PythonNoticeTests(unittest.TestCase):
    def test_only_python_310_gets_the_notice(self):
        self.assertIn('Python 3.11 oder neuer', python_support.notice((3, 10, 20)))
        self.assertIn('Sicherheitskorrekturen', python_support.notice((3, 10, 0)))
        for v in ((3, 11, 0), (3, 13, 18), (3, 14, 6), (3, 15, 0), (3, 9, 0)):
            self.assertEqual(python_support.notice(v), '', v)

    def test_starters_show_it(self):
        for rel in ('sales_tool/bootstrap.py', 'sales_tool/server.py', 'sales_tool/multi_server.py'):
            self.assertIn('python_notice()', (ROOT / rel).read_text(encoding='utf-8'), rel)


class Base(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'm'
        self.dir = tenancy.Directory(self.root)
        self.dir.create('nord', 'Nord')
        accounts.create_account(self.dir, 'erika', PW)
        accounts.set_membership(self.dir, 'erika', 'nord', 'vertrieb')

    def tearDown(self):
        self.tmp.cleanup()

    def enable(self):
        _, token = accounts.login(self.dir, 'erika', PW)
        secret = accounts.mfa_start(self.dir, token, PW)['secret'].replace(' ', '')
        accounts.mfa_confirm(self.dir, token, totp.code(secret))
        return secret

    def row(self):
        with closing(sqlite3.connect(self.root / 'organisationen.sqlite3')) as c:
            return c.execute('SELECT account_id, secret FROM account_mfa').fetchone()


class MfaKeyTests(Base):
    def test_secret_never_in_plain_text_and_key_outside_data(self):
        secret = self.enable()
        account_id, stored = self.row()
        self.assertTrue(stored.startswith('sdq1:'))
        self.assertNotIn(secret, stored)
        raw = b''.join(p.read_bytes() for p in self.root.rglob('*') if p.is_file())
        self.assertNotIn(secret.encode(), raw, 'Geheimnis darf nirgends im Datenordner im Klartext stehen')
        key = schluessel.key_dir(self.root) / schluessel.MFA_KEY_FILE
        self.assertTrue(key.exists())
        self.assertNotIn(self.root, key.parents)
        if os.name == 'posix':
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(schluessel.unseal(self.root, account_id, stored), secret)

    def test_second_factor_still_works(self):
        import time
        secret = self.enable()
        view, token = accounts.login(self.dir, 'erika', PW)
        self.assertEqual(view['stage'], 'zweitfaktor')
        view, _ = accounts.second_factor(self.dir, token, totp.hotp(totp._key(secret), totp.step(time.time()) + 1))
        self.assertTrue(view['two_factor'])

    def test_bound_to_account_and_tamper_evident(self):
        self.enable()
        account_id, stored = self.row()
        with self.assertRaises(ValueError):
            schluessel.unseal(self.root, account_id + 1, stored)     # in die Zeile eines anderen Kontos kopiert
        blob = stored[:-6] + ('A' if stored[-6] != 'A' else 'B') + stored[-5:]
        with self.assertRaises(ValueError):
            schluessel.unseal(self.root, account_id, blob)

    def test_old_plain_secret_is_sealed_on_upgrade(self):
        secret = totp.new_secret()
        with closing(sqlite3.connect(self.root / 'organisationen.sqlite3')) as c:  # Stand vor dev68: Klartext
            acc = c.execute("SELECT id FROM accounts WHERE username='erika'").fetchone()[0]
            c.execute('INSERT INTO account_mfa(account_id, secret, active, last_step) VALUES (?,?,1,-1)', (acc, secret))
            c.commit()
        accounts.init(self.dir)
        _, stored = self.row()
        self.assertTrue(stored.startswith('sdq1:'))
        self.assertEqual(schluessel.unseal(self.root, acc, stored), secret)

    def test_missing_key_is_reported_not_replaced(self):
        self.enable()
        key = schluessel.key_dir(self.root) / schluessel.MFA_KEY_FILE
        key.unlink()
        schluessel._CACHE.clear()
        with self.assertRaisesRegex(schluessel.KeyMissing, 'fehlt'):
            accounts.check_mfa_key(self.dir)
        self.assertFalse(key.exists(), 'kein neuer Schlüssel, solange verschlüsselte Geheimnisse da sind')
        with mock.patch('sys.stdout', new=StringIO()) as so:
            self.assertEqual(betreiber.main(['--root', str(self.root), 'schluessel']), 1)
        self.assertIn('fehlt', so.getvalue())

    def test_key_folder_inside_data_refused(self):
        with mock.patch.dict('os.environ', {'SIGNALDESK_SCHLUESSEL_ORDNER': str(self.root / 'schluessel')}):
            with self.assertRaisesRegex(ValueError, 'im Datenordner'):
                schluessel.key_dir(self.root)

    def test_operator_sees_key_ids(self):
        self.enable()
        with mock.patch('sys.stdout', new=StringIO()) as so:
            self.assertEqual(betreiber.main(['--root', str(self.root), 'schluessel']), 0)
        out = json.loads(so.getvalue())
        self.assertEqual(len(out['mfa_kennung']), 8)
        self.assertNotIn(self.root.resolve(), Path(out['ordner']).parents)
        self.assertNotEqual(Path(out['ordner']), self.root.resolve())


@unittest.skipUnless(schluessel.signing_available(), 'cryptography nicht installiert – Signatur nur in der Variante „team“')
class SignedBackupTests(Base):
    def test_set_is_signed_and_verifies(self):
        m = ops.backup_all(self.dir)
        self.assertEqual(len(m['signature']), 16)
        self.assertTrue((Path(m['path']) / schluessel.SIGNATURE_FILE).exists())
        report = ops.verify_backup(self.dir, m['name'])
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['signature']['status'], 'gueltig')
        out = ops.restore_org(self.dir, m['name'], 'nord', confirm=True)
        self.assertEqual(out['signature']['status'], 'gueltig')

    def test_manifest_rewritten_with_matching_checksums_is_refused(self):
        """Angriff am Ablageort: Datei ändern UND Prüfsumme im Manifest nachziehen – nur die Signatur verrät es."""
        m = ops.backup_all(self.dir)
        folder = Path(m['path'])
        target = folder / 'orgs' / 'nord.sqlite3'
        with closing(sqlite3.connect(target)) as c:
            c.execute("INSERT INTO leads(company, stage) VALUES ('Untergeschoben Fiktiv', 'neu')")
            c.commit()
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        for f in manifest['files']:
            if f['file'] == 'orgs/nord.sqlite3':
                f['sha256'] = ops._sha256(target)
                f['rows']['leads'] = f['rows'].get('leads', 0) + 1
        (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
        report = ops.verify_backup(self.dir, m['name'])
        self.assertFalse(report['ok'])
        self.assertIn('Signatur ungültig', report['signature']['problem'])
        with self.assertRaisesRegex(schluessel.SignatureError, 'Signatur ungültig'):
            ops.restore_org(self.dir, m['name'], 'nord', confirm=True)
        with self.assertRaisesRegex(schluessel.SignatureError, 'Signatur ungültig'):  # auch nicht mit dem Schalter
            ops.restore_org(self.dir, m['name'], 'nord', confirm=True, allow_unsigned=True)

    def test_removed_signature_needs_explicit_switch(self):
        m = ops.backup_all(self.dir)
        (Path(m['path']) / schluessel.SIGNATURE_FILE).unlink()
        with self.assertRaisesRegex(schluessel.SignatureError, 'nicht signiert'):
            ops.restore_org(self.dir, m['name'], 'nord', confirm=True)
        with mock.patch('sys.stdout', new=StringIO()) as so:
            code = betreiber.main(['--root', str(self.root), 'zurueckspielen', m['name'], 'nord', '--ja'])
        self.assertEqual(code, 1, so.getvalue())
        with mock.patch('sys.stdout', new=StringIO()) as so:
            code = betreiber.main(['--root', str(self.root), 'zurueckspielen', m['name'], 'nord', '--ja', '--unsigniert-zulassen'])
        self.assertEqual(code, 0, so.getvalue())
        self.assertEqual(json.loads(so.getvalue())['signature']['status'], 'unsigniert_zugelassen')
        from sales_tool import audit_trail
        self.assertTrue(any('unsigniert_zugelassen' in e['detail'] for e in audit_trail.events(self.dir, 5)))

    def test_replacement_system_needs_the_public_key(self):
        m = ops.backup_all(self.dir)
        new_root = self.base / 'ersatz'
        with self.assertRaisesRegex(schluessel.SignatureError, 'kein öffentlicher Schlüssel'):
            ops.restore_installation(m['path'], new_root, confirm=True)
        self.assertFalse(new_root.exists())
        pub = schluessel.key_dir(self.root) / schluessel.SIGN_PUB_FILE
        out = ops.restore_installation(m['path'], new_root, confirm=True, public_key_path=pub)
        self.assertEqual(out['signature']['status'], 'gueltig')

    def test_foreign_key_is_refused(self):
        m = ops.backup_all(self.dir)
        other = tenancy.Directory(self.base / 'fremd')
        other.create('x', 'X')
        ops.backup_all(other)  # legt eigene Schlüssel an
        foreign = schluessel.key_dir(other.root) / schluessel.SIGN_PUB_FILE
        with self.assertRaisesRegex(schluessel.SignatureError, 'anderen Schlüssel'):
            ops.restore_installation(m['path'], self.base / 'ersatz', confirm=True, public_key_path=foreign)

    def test_key_material_not_in_the_set(self):
        m = ops.backup_all(self.dir)
        names = {p.name for p in Path(m['path']).rglob('*')}
        self.assertFalse(names & {schluessel.MFA_KEY_FILE, schluessel.SIGN_KEY_FILE})


class DeployTests(unittest.TestCase):
    def test_services_may_write_the_key_folder(self):
        for name in ('signaldesk-mandanten.service', 'signaldesk-sicherung.service'):
            text = (ROOT / 'deploy' / name).read_text(encoding='utf-8')
            line = next(x for x in text.splitlines() if x.startswith('ReadWritePaths='))
            self.assertIn('/srv/signaldesk.schluessel', line.split('=', 1)[1].split(), name)
        self.assertEqual(str(schluessel.key_dir('/srv/signaldesk')).replace('\\', '/').split(':')[-1], '/srv/signaldesk.schluessel')


class UnsignedLegacyTests(Base):
    def test_installation_without_any_key_accepts_unsigned_sets(self):
        """Basis-Variante ohne cryptography (oder Sätze vor dev68): kein Schlüssel bekannt → wie bisher, Status „unsigniert“."""
        with mock.patch.object(schluessel, 'signing_available', return_value=False):
            m = ops.backup_all(self.dir)
            self.assertEqual(m['signature'], '')
            self.assertFalse((Path(m['path']) / schluessel.SIGNATURE_FILE).exists())
            out = ops.restore_org(self.dir, m['name'], 'nord', confirm=True)
        self.assertEqual(out['signature']['status'], 'unsigniert')


if __name__ == '__main__':
    unittest.main()
