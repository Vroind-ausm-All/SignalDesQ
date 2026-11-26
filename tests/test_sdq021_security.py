"""SDQ-021 bis SDQ-023: Zwei-Faktor-Anmeldung, Protokoll der Verwaltungsaktionen, verschlüsselter Export.

Über HTTP gegen den Mehrmandanten-Server geprüft: Ohne Code gibt es weder die Liste der Organisationen noch Zutritt; ein Code
gilt nur einmal; Wiederherstellungscodes gelten einmal; die Pflicht zwingt zur Einrichtung; der Betreiber kann zurücksetzen;
Fehlversuche sperren auch nach einem Neustart. Das Protokoll erkennt veränderte und entfernte Einträge. Alle Daten fiktiv."""
import sqlite3
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from sales_tool import accounts, audit_trail, auth, backup_crypto, schluessel, tenancy, totp  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402
from test_sdq014_multi_tenant import PW, Client  # noqa: E402


class TotpTests(unittest.TestCase):
    def test_rfc6238_vectors(self):
        # RFC 6238, Anhang B (SHA-1, Geheimnis „12345678901234567890“), 8 Stellen
        key = b'12345678901234567890'
        for t, want in ((59, '94287082'), (1111111109, '07081804'), (1111111111, '14050471'), (1234567890, '89005924'),
                        (2000000000, '69279037'), (20000000000, '65353130')):
            self.assertEqual(totp.hotp(key, t // 30, digits=8), want, t)

    def test_window_and_replay(self):
        secret = totp.new_secret()
        now = 1_800_000_000
        self.assertIsNotNone(totp.match(secret, totp.code(secret, now - 30), now=now))   # 30 s alte Uhr: noch gültig
        self.assertIsNone(totp.match(secret, totp.code(secret, now - 90), now=now))      # 90 s: abgelehnt
        used = totp.match(secret, totp.code(secret, now), now=now)
        self.assertIsNone(totp.match(secret, totp.code(secret, now), now=now, last_step=used))  # derselbe Code zweimal: nein
        self.assertIsNone(totp.match(secret, 'abcdef', now=now))
        self.assertIn('otpauth://totp/SignalDesk%3Aerika?secret=', totp.uri(secret, 'erika'))


class TwoFactorHttpTests(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name) / 'm'
        self.dir = tenancy.Directory(self.root)
        for slug, name in (('nord', 'Nord'), ('sued', 'Süd')):
            org = self.dir.create(slug, name)
            with connect(org['db_path']) as conn:
                conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'neu')", (f'{name} Fiktiv GmbH',))
                conn.commit()
        accounts.create_account(self.dir, 'erika', PW, 'Erika Beispiel')
        accounts.set_membership(self.dir, 'erika', 'nord', 'vertrieb')
        accounts.set_membership(self.dir, 'erika', 'sued', 'lesen')
        self.start()

    def start(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(tenancy.Directory(self.root)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def tearDown(self):
        self.stop()
        self.tmp.cleanup()

    def secret(self):
        with self.dir._connect() as conn:
            row = conn.execute('SELECT account_id, secret FROM account_mfa').fetchone()
        # dev68: in der Datenbank steht das Geheimnis nur verschlüsselt (F09) – hier mit dem Server-Schlüssel geöffnet
        self.assertTrue(row['secret'].startswith(schluessel.MFA_PREFIX))
        return schluessel.unseal(self.dir.root, row['account_id'], row['secret'])

    def enable_2fa(self, c):
        """Einrichtung über die Oberfläche: Schlüssel holen, Code bestätigen. Gibt (Geheimnis, Wiederherstellungscodes)."""
        status, data, _ = c.call('/api/zentral/2fa/start', 'POST', {'password': PW})
        self.assertEqual(status, 200, data)
        secret = data['secret'].replace(' ', '')
        self.assertEqual(secret, self.secret())
        status, data, _ = c.call('/api/zentral/2fa/confirm', 'POST', {'code': totp.code(secret)})
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data['recovery_codes']), accounts.RECOVERY_CODES)
        return secret, data['recovery_codes']

    def fresh_code(self, secret):
        """Code des nächsten Zeitschritts (der aktuelle wurde schon verbraucht)."""
        import time
        return totp.hotp(totp._key(secret), totp.step(time.time()) + 1)

    def test_password_alone_gives_no_access_once_enabled(self):
        c = Client(self.base)
        c.login('erika')
        secret, _ = self.enable_2fa(c)
        c2 = Client(self.base)
        status, data, _ = c2.login('erika')
        self.assertEqual((status, data['stage']), (200, 'zweitfaktor'))
        self.assertNotIn('organizations', data)  # keine Organisationsliste vor dem zweiten Faktor
        self.assertFalse(c2.call('/api/zentral/status')[1]['logged_in'])
        self.assertEqual(c2.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 401)
        self.assertEqual(c2.call('/api/leads')[0], 401)
        pending = c2.cookies[accounts.CENTRAL_COOKIE]
        status, data, _ = c2.call('/api/zentral/code', 'POST', {'code': '000000' if self.fresh_code(secret) != '000000' else '111111'})
        self.assertEqual(status, 401)
        status, data, _ = c2.call('/api/zentral/code', 'POST', {'code': self.fresh_code(secret)})
        self.assertEqual(status, 200, data)
        self.assertNotEqual(c2.cookies[accounts.CENTRAL_COOKIE], pending)  # neues Token nach dem zweiten Faktor
        self.assertEqual(len(data['organizations']), 2)
        # Das Zwischen-Token ist verbraucht
        c3 = Client(self.base)
        c3.cookies[accounts.CENTRAL_COOKIE] = pending
        self.assertEqual(c3.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 401)
        self.assertEqual(c2.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 200)
        self.assertEqual(c2.call('/api/leads')[0], 200)

    def test_code_is_single_use(self):
        c = Client(self.base)
        c.login('erika')
        secret, _ = self.enable_2fa(c)
        code = self.fresh_code(secret)
        a, b = Client(self.base), Client(self.base)
        a.login('erika')
        b.login('erika')
        self.assertEqual(a.call('/api/zentral/code', 'POST', {'code': code})[0], 200)
        self.assertEqual(b.call('/api/zentral/code', 'POST', {'code': code})[0], 401)  # abgefangener Code: wertlos

    def test_recovery_code_once(self):
        c = Client(self.base)
        c.login('erika')
        _, codes = self.enable_2fa(c)
        a = Client(self.base)
        a.login('erika')
        self.assertEqual(a.call('/api/zentral/code', 'POST', {'code': codes[0].lower()})[0], 200)
        self.assertEqual(a.call('/api/zentral/status')[1]['recovery_codes_left'], accounts.RECOVERY_CODES - 1)
        b = Client(self.base)
        b.login('erika')
        self.assertEqual(b.call('/api/zentral/code', 'POST', {'code': codes[0]})[0], 401)

    def test_enabling_ends_other_sessions(self):
        other = Client(self.base)
        other.login('erika')
        c = Client(self.base)
        c.login('erika')
        self.enable_2fa(c)
        self.assertFalse(other.call('/api/zentral/status')[1]['logged_in'])
        self.assertTrue(c.call('/api/zentral/status')[1]['logged_in'])

    def test_wrong_codes_throttled_and_survive_restart(self):
        c = Client(self.base)
        c.login('erika')
        secret, _ = self.enable_2fa(c)
        bad = '000000' if self.fresh_code(secret) != '000000' else '111111'
        a = Client(self.base)
        a.login('erika')
        for _ in range(accounts.FAIL_LIMIT):
            self.assertEqual(a.call('/api/zentral/code', 'POST', {'code': bad})[0], 401)
        self.assertEqual(a.call('/api/zentral/code', 'POST', {'code': self.fresh_code(secret)})[0], 429)
        self.stop()
        auth._FAILS.clear()   # Neustart: Speicher des Prozesses ist leer …
        self.start()
        b = Client(self.base)
        b.login('erika')      # … die Sperre steht im Verzeichnis
        self.assertEqual(b.call('/api/zentral/code', 'POST', {'code': self.fresh_code(secret)})[0], 429)

    def test_password_lockout_survives_restart(self):
        c = Client(self.base)
        for _ in range(accounts.FAIL_LIMIT):
            self.assertEqual(c.login('erika', 'falsch-falsch-falsch')[0], 401)
        self.stop()
        auth._FAILS.clear()
        self.start()
        self.assertEqual(Client(self.base).login('erika')[0], 429)

    def test_required_2fa_forces_setup_before_entering(self):
        accounts.set_require_2fa(self.dir, True)
        c = Client(self.base)
        status, data, _ = c.login('erika')
        self.assertEqual(data['stage'], 'einrichtung')
        self.assertEqual(c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 401)
        self.assertEqual(c.call('/api/zentral/password', 'POST', {'old': PW, 'new': PW + 'x'})[0], 401)
        secret, _ = self.enable_2fa(c)
        st = c.call('/api/zentral/status')[1]
        self.assertTrue(st['logged_in'] and st['two_factor'] and st['require_2fa'])
        self.assertEqual(c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 200)
        # Abschalten ist bei Pflicht nicht erlaubt
        self.assertEqual(c.call('/api/zentral/2fa/off', 'POST', {'password': PW, 'code': self.fresh_code(secret)})[0], 403)

    def test_requirement_ends_sessions_without_2fa(self):
        c = Client(self.base)
        c.login('erika')
        c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})
        accounts.set_require_2fa(self.dir, True)
        self.assertFalse(c.call('/api/zentral/status')[1]['logged_in'])
        with self.assertRaises(PermissionError):
            accounts.enter(self.dir, self._acc('erika'), 'nord')

    def _acc(self, name):
        with self.dir._connect() as conn:
            return accounts._account(conn, name)

    def test_disable_needs_password_and_code(self):
        c = Client(self.base)
        c.login('erika')
        secret, _ = self.enable_2fa(c)
        self.assertEqual(c.call('/api/zentral/2fa/off', 'POST', {'password': 'falsch', 'code': self.fresh_code(secret)})[0], 403)
        self.assertEqual(c.call('/api/zentral/2fa/off', 'POST', {'password': PW, 'code': '12345'})[0], 403)
        self.assertEqual(c.call('/api/zentral/2fa/off', 'POST', {'password': PW, 'code': self.fresh_code(secret)})[0], 200)
        self.assertEqual(Client(self.base).login('erika')[1]['stage'], 'voll')

    def test_operator_reset_ends_all_sessions(self):
        c = Client(self.base)
        c.login('erika')
        self.enable_2fa(c)
        a = Client(self.base)
        a.login('erika')
        # Anmeldung mit Code und Zutritt
        a.call('/api/zentral/code', 'POST', {'code': self.fresh_code(self.secret())})
        self.assertEqual(a.call('/api/zentral/enter', 'POST', {'slug': 'nord'})[0], 200)
        self.assertEqual(a.call('/api/leads')[0], 200)
        view = accounts.mfa_reset(self.dir, 'erika', actor='betreiber:test')
        self.assertFalse(view['two_factor'])
        self.assertEqual(a.call('/api/leads')[0], 401)
        self.assertFalse(a.call('/api/zentral/status')[1]['logged_in'])
        self.assertEqual(Client(self.base).login('erika')[1]['stage'], 'voll')

    def test_audit_trail_records_logins_and_admin_actions(self):
        c = Client(self.base)
        c.login('erika', 'falsch-falsch-falsch')
        c.login('niemand', 'falsch-falsch-falsch')
        c.login('erika')
        c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})
        accounts.remove_membership(self.dir, 'erika', 'sued', actor='betreiber:test')
        ev = audit_trail.events(self.dir, 100)
        actions = [(e['action'], e['target']) for e in reversed(ev)]
        for want in [('organisation_angelegt', 'nord'), ('konto_angelegt', 'erika'), ('mitgliedschaft_gesetzt', 'erika'),
                     ('anmeldung_fehlgeschlagen', 'erika'), ('anmeldung_fehlgeschlagen', 'unbekannt'), ('anmeldung', 'erika'),
                     ('organisation_betreten', 'nord'), ('mitgliedschaft_entzogen', 'erika')]:
            self.assertIn(want, actions)
        self.assertNotIn('niemand', str(ev))       # unbekannte Namen (oft vertippte Passwörter) werden nicht gespeichert
        self.assertNotIn(PW, str(ev))
        login = next(e for e in ev if e['action'] == 'anmeldung')
        self.assertEqual((login['actor'], login['ip']), ('konto:erika', '127.0.0.1'))
        self.assertTrue(audit_trail.verify(self.dir)['ok'])


class AuditChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        for i in range(5):
            audit_trail.record(self.dir, 'betreiber:test', 'probe', f'ziel-{i}', 'fiktiv')
        self.db = self.dir.root / 'organisationen.sqlite3'

    def tearDown(self):
        self.tmp.cleanup()

    def sql(self, statement, args=()):
        with sqlite3.connect(self.db) as c:
            c.execute(statement, args)

    def test_intact(self):
        self.assertEqual(audit_trail.verify(self.dir), {'ok': True, 'events': 5, 'first_bad': None, 'reason': ''})

    def test_changed_entry_detected(self):
        self.sql("UPDATE audit_events SET target='anders' WHERE id=3")
        r = audit_trail.verify(self.dir)
        self.assertEqual((r['ok'], r['first_bad']), (False, 3))

    def test_removed_entry_detected(self):
        self.sql('DELETE FROM audit_events WHERE id=2')
        r = audit_trail.verify(self.dir)
        self.assertEqual((r['ok'], r['first_bad']), (False, 3))

    def test_removed_start_detected(self):
        self.sql('DELETE FROM audit_events WHERE id=1')
        self.assertFalse(audit_trail.verify(self.dir)['ok'])

    def test_concurrent_writers_keep_one_chain(self):
        threads = [threading.Thread(target=audit_trail.record, args=(self.dir, 'betreiber:test', 'parallel', str(i))) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(audit_trail.verify(self.dir)['events'], 17)
        self.assertTrue(audit_trail.verify(self.dir)['ok'])


@unittest.skipUnless(backup_crypto.available(), 'Paket cryptography fehlt (requirements-team.txt)')
class EncryptedExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        org = self.dir.create('nord', 'Nord')
        with connect(org['db_path']) as conn:
            conn.execute("INSERT INTO leads(company, stage) VALUES ('Nord Fiktiv GmbH', 'neu')")
            conn.commit()
        self.db = org['db_path']
        self.out = Path(self.tmp.name) / 'nord.zip.sdenc'

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        res = tenancy.export_organization(self.db, self.out, password='Export-Passphrase-42')
        self.assertTrue(res['encrypted'])
        blob = self.out.read_bytes()
        self.assertTrue(blob.startswith(backup_crypto.MAGIC))
        self.assertNotIn(b'Nord Fiktiv GmbH', blob)
        self.assertNotIn(b'PK\x03\x04', blob[:64])
        with self.assertRaises(ValueError):
            backup_crypto.decrypt_bytes(blob, 'falsches-Passwort-123')
        plain = Path(self.tmp.name) / 'nord.zip'
        backup_crypto.decrypt_file(self.out, plain, 'Export-Passphrase-42')
        with zipfile.ZipFile(plain) as zf:
            self.assertIn('signaldesk.sqlite3', zf.namelist())
            self.assertIn('Verschlüsselt übergeben', zf.read('manifest.json').decode('utf-8'))
            db = Path(self.tmp.name) / 'x.sqlite3'
            db.write_bytes(zf.read('signaldesk.sqlite3'))
        with sqlite3.connect(db) as c:
            self.assertEqual(c.execute('SELECT company FROM leads').fetchone()[0], 'Nord Fiktiv GmbH')

    def test_rules(self):
        with self.assertRaises(tenancy.TenantError):
            tenancy.export_organization(self.db, self.out, password='kurz')
        with self.assertRaises(tenancy.TenantError):
            tenancy.export_organization(self.db, Path(self.tmp.name) / 'nord.zip', password='Export-Passphrase-42')
        self.out.write_bytes(b'vorhanden')
        with self.assertRaises(tenancy.TenantError):
            tenancy.export_organization(self.db, self.out, password='Export-Passphrase-42')
        self.assertEqual(self.out.read_bytes(), b'vorhanden')


if __name__ == '__main__':
    unittest.main()
