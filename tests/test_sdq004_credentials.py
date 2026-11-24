"""SDQ-004 (Audit B3): Zugangsdaten nie im Klartext auf dem Datenträger.

Vorher schrieb „auf diesem Rechner merken“ IMAP-/CalDAV-Passwörter als JSON im Klartext neben die Datenbank.
Jetzt: Passwortspeicher des Betriebssystems, sonst nur Arbeitsspeicher; Altbestand wird übernommen bzw. abgebaut.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cred_fake import FakeStore  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import credentials  # noqa: E402

PW, PW2 = 'App-Passwort-7f3a!', 'Postfach-Geheim-91'


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'c.sqlite3')
        Path(self.db).write_bytes(b'')
        self.legacy = Path(self.tmp.name) / 'zugangsdaten.json'

    def tearDown(self):
        credentials._MEMORY.clear()
        credentials.set_backend('auto')
        cleanup_tmp(self.tmp)

    def restart(self):
        credentials._MEMORY.clear()

    def assert_no_plaintext_on_disk(self, *secrets):
        for root, _dirs, files in os.walk(self.tmp.name):
            for name in files:
                data = (Path(root) / name).read_bytes()
                for s in secrets:
                    self.assertNotIn(s.encode(), data, f'Klartext-Passwort in {name}')

    def test_remember_uses_secure_store_and_survives_restart(self):
        store = FakeStore()
        credentials.set_backend(store)
        self.assertTrue(credentials.put(self.db, 'caldav', PW, remember=True))
        self.assertFalse(self.legacy.exists())
        self.assert_no_plaintext_on_disk(PW)
        self.assertEqual(list(store.data.values()), [PW])
        self.assertNotIn(self.tmp.name, ''.join(store.data), 'Pfad der Datenbank steht nicht im Schlüsselbund')
        self.restart()
        self.assertEqual(credentials.get(self.db, 'caldav'), PW)
        self.assertEqual(credentials.status(self.db, 'caldav'), {'stored': True, 'remembered': True})
        info = credentials.store_info(self.db, 'caldav')
        self.assertEqual((info['secure_store'], info['legacy_plaintext']), (True, False))
        # Rotation: neues Passwort ersetzt das alte
        credentials.put(self.db, 'caldav', PW + 'neu', remember=True)
        self.restart()
        self.assertEqual(credentials.get(self.db, 'caldav'), PW + 'neu')
        # Widerruf
        credentials.forget(self.db, 'caldav')
        self.assertEqual(store.data, {})
        self.restart()
        self.assertIsNone(credentials.get(self.db, 'caldav'))

    def test_without_secure_store_nothing_is_written(self):
        credentials.set_backend(None)
        self.assertFalse(credentials.put(self.db, 'imap', PW, remember=True))
        self.assertEqual(credentials.get(self.db, 'imap'), PW, 'bis zum Neustart nutzbar')
        self.assertFalse(self.legacy.exists())
        self.assert_no_plaintext_on_disk(PW)
        self.assertEqual(credentials.status(self.db, 'imap'), {'stored': True, 'remembered': False})
        self.assertFalse(credentials.store_info(self.db)['secure_store'])
        self.assertIn('bis zum Neustart', credentials.store_info(self.db)['notice'])
        self.restart()
        self.assertIsNone(credentials.get(self.db, 'imap'))

    def test_not_remembered_removes_stored_secret(self):
        store = FakeStore()
        credentials.set_backend(store)
        credentials.put(self.db, 'caldav', PW, remember=True)
        credentials.put(self.db, 'caldav', PW, remember=False)
        self.assertEqual(store.data, {})
        self.restart()
        self.assertIsNone(credentials.get(self.db, 'caldav'))

    def test_store_refuses_falls_back_to_memory(self):
        credentials.set_backend(FakeStore(fail=True))
        self.assertFalse(credentials.put(self.db, 'caldav', PW, remember=True))
        self.assertEqual(credentials.get(self.db, 'caldav'), PW)
        self.assert_no_plaintext_on_disk(PW)

    def test_legacy_plaintext_is_migrated_and_removed(self):
        self.legacy.write_text(json.dumps({'caldav': PW, 'imap': PW2}), encoding='utf-8')
        store = FakeStore()
        credentials.set_backend(store)
        self.assertTrue(credentials.store_info(self.db, 'caldav')['legacy_plaintext'])
        self.assertEqual(credentials.get(self.db, 'caldav'), PW)
        self.assertEqual(json.loads(self.legacy.read_text()), {'imap': PW2}, 'nur der übernommene Eintrag verschwindet')
        self.assertEqual(credentials.status(self.db, 'imap'), {'stored': True, 'remembered': True})
        self.assertFalse(self.legacy.exists(), 'leere Altdatei wird entfernt')
        self.assertEqual(sorted(store.data.values()), sorted([PW, PW2]))
        self.restart()
        self.assertEqual((credentials.get(self.db, 'caldav'), credentials.get(self.db, 'imap')), (PW, PW2))
        self.assert_no_plaintext_on_disk(PW, PW2)

    def test_legacy_without_store_is_read_but_never_rewritten(self):
        self.legacy.write_text(json.dumps({'caldav': PW, 'imap': PW2}), encoding='utf-8')
        before = self.legacy.read_bytes()
        credentials.set_backend(None)
        self.assertEqual(credentials.get(self.db, 'caldav'), PW, 'bestehende Einrichtung funktioniert weiter')
        self.assertEqual(self.legacy.read_bytes(), before, 'ohne Neu-Eingabe keine Änderung an der Datei')
        self.assertTrue(credentials.store_info(self.db, 'caldav')['legacy_plaintext'])
        # Neu-Eingabe entfernt den Klartext-Eintrag und schreibt keinen neuen
        credentials.put(self.db, 'caldav', PW + 'neu', remember=True)
        self.assertEqual(json.loads(self.legacy.read_text()), {'imap': PW2})
        credentials.forget(self.db, 'imap')
        self.assertFalse(self.legacy.exists())
        self.assert_no_plaintext_on_disk(PW + 'neu')

    def test_installations_do_not_share_secrets(self):
        store = FakeStore()
        credentials.set_backend(store)
        other = str(Path(self.tmp.name) / 'andere' / 'c.sqlite3')
        credentials.put(self.db, 'caldav', PW, remember=True)
        self.restart()
        self.assertIsNone(credentials.get(other, 'caldav'))

    def test_secret_tool_gets_password_via_stdin_only(self):
        calls = []

        class Done:
            returncode, stdout, stderr = 0, '', ''
        orig = credentials.subprocess.run
        credentials.subprocess.run = lambda args, **kw: calls.append((args, kw.get('input'))) or Done()
        try:
            credentials._SecretTool('/usr/bin/secret-tool').set('caldav:abc', PW)
        finally:
            credentials.subprocess.run = orig
        args, data = calls[0]
        self.assertNotIn(PW, ' '.join(args), 'Passwort nie auf der Befehlszeile (für andere Prozesse sichtbar)')
        self.assertEqual(data, PW)

    @unittest.skipUnless(os.name == 'nt', 'nur unter Windows (CI)')
    def test_windows_dpapi_roundtrip(self):
        store = credentials._DPAPI(self.tmp.name)
        store.set('caldav:abc', PW)
        self.assertEqual(store.get('caldav:abc'), PW)
        self.assert_no_plaintext_on_disk(PW)
        store.delete('caldav:abc')
        self.assertIsNone(store.get('caldav:abc'))


if __name__ == '__main__':
    unittest.main()
