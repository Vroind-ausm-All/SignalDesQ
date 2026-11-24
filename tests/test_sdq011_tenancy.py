"""SDQ-011/012: Eine Datenbank je Organisation – Verzeichnis der Organisationen und Negativtests über Mandantengrenzen.

Geprüft wird, dass zwei Organisationen im selben Prozess nichts voneinander sehen oder beeinflussen: Daten, Offline-Schalter,
Anmeldesperre, Zugangsdaten, Impressum-Läufe, Planer und Auftragsschritte. Alle Daten sind fiktiv."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import auth, credentials, imprint_batch, netpolicy, quality, tenancy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402

PW = 'Lange-Passphrase-7391'


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'mandanten')

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_list_get(self):
        a = self.dir.create('studio-nord', 'Studio Nord')
        self.dir.create('studio-sued', 'Studio Süd')
        self.assertTrue(Path(a['db_path']).is_file())
        self.assertEqual(Path(a['db_path']).parent.name, 'studio-nord')
        with connect(a['db_path']) as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM sqlite_master WHERE name='invoices'").fetchone(), 'Datenbank ist migriert')
        self.assertEqual([o['slug'] for o in self.dir.list()], ['studio-nord', 'studio-sued'])
        self.assertEqual(self.dir.get('studio-sued')['name'], 'Studio Süd')

    def test_slug_rules(self):
        for bad in ('../x', 'a/b', 'Studio', '-x', 'x-', 'a--b', 'admin', '', 'x' * 41, 'nord.db', None):
            with self.assertRaises(tenancy.TenantError, msg=repr(bad)):
                self.dir.path_for(bad)
        with self.assertRaises(tenancy.TenantError):
            self.dir.create('ok', '')

    def test_no_duplicate_and_no_overwrite(self):
        self.dir.create('nord', 'Nord')
        with self.assertRaises(tenancy.TenantError):
            self.dir.create('nord', 'Nord 2')
        stray = self.dir.root / 'orgs' / 'fremd'
        stray.mkdir()
        (stray / tenancy.DB_NAME).write_bytes(b'bestehende Daten')
        with self.assertRaises(tenancy.TenantError):
            self.dir.create('fremd', 'Fremd')
        self.assertEqual((stray / tenancy.DB_NAME).read_bytes(), b'bestehende Daten')

    @unittest.skipIf(os.name == 'nt', 'Verknüpfungen brauchen unter Windows Sonderrechte')
    def test_symlink_cannot_leave_directory(self):
        outside = Path(self.tmp.name) / 'woanders'
        outside.mkdir()
        (self.dir.root / 'orgs' / 'umweg').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(tenancy.TenantError):
            self.dir.path_for('umweg')

    def test_archive_keeps_data_and_blocks_open(self):
        org = self.dir.create('alt', 'Alt GmbH')
        self.assertEqual(self.dir.open('alt'), Path(org['db_path']))
        self.dir.archive('alt')
        with self.assertRaises(tenancy.TenantError):
            self.dir.open('alt')
        self.assertTrue(Path(org['db_path']).is_file(), 'Archivieren löscht nichts')
        self.assertEqual(self.dir.list(), [])
        self.assertEqual(len(self.dir.list(include_archived=True)), 1)
        with self.assertRaises(LookupError):
            self.dir.get('unbekannt')


class IsolationTests(unittest.TestCase):
    """Zwei Organisationen in einem Prozess."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        d = tenancy.Directory(Path(cls.tmp.name) / 'm')
        cls.a = Path(d.create('nord', 'Nord')['db_path'])
        cls.b = Path(d.create('sued', 'Süd')['db_path'])

    @classmethod
    def tearDownClass(cls):
        for db in (cls.a, cls.b):
            jobs.stop_workers(db, timeout=5)
        cls.tmp.cleanup()

    def tearDown(self):
        netpolicy.STATE.update(stored=False, forced=False)
        for db in (self.a, self.b):
            with connect(db) as conn:
                netpolicy.set_offline(conn, False)

    def test_same_ids_different_data_over_http(self):
        for db, name in ((self.a, 'Nord Fiktiv GmbH'), (self.b, 'Süd Fiktiv GmbH')):
            with connect(db) as conn:
                conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'neu')", (name,))
                conn.commit()
        seen = {}
        for db in (self.a, self.b):
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(db))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                data = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/leads').read())
                rows = data if isinstance(data, list) else data.get('leads', data.get('items', []))
                seen[db] = {r['company'] for r in rows}
            finally:
                server.shutdown()
                server.server_close()
        self.assertIn('Nord Fiktiv GmbH', seen[self.a])
        self.assertNotIn('Süd Fiktiv GmbH', seen[self.a])
        self.assertIn('Süd Fiktiv GmbH', seen[self.b])
        self.assertNotIn('Nord Fiktiv GmbH', seen[self.b])

    def test_offline_switch_belongs_to_one_organisation(self):
        with connect(self.a) as ca, connect(self.b) as cb:
            netpolicy.load(cb)
            netpolicy.set_offline(ca, True)
            self.assertTrue(netpolicy.status(ca)['offline'])
            self.assertFalse(netpolicy.status(cb)['offline'], 'Offline bei Nord schaltet Süd nicht ab')
        with tenancy.use(self.a):
            self.assertTrue(netpolicy.offline())
        with tenancy.use(self.b):
            self.assertFalse(netpolicy.offline())
        netpolicy.STATE['forced'] = True  # Start mit --offline gilt für die ganze Installation
        with tenancy.use(self.b):
            self.assertTrue(netpolicy.offline())

    def test_offline_organisation_holds_only_its_own_network_tasks(self):
        task = [{'key': 'w1', 'kind': 'website', 'label': 'x', 'payload': {}}]
        with connect(self.a) as ca, connect(self.b) as cb:
            netpolicy.load(cb)
            netpolicy.set_offline(ca, True)
            jobs.submit(ca, 'website', 'Nord', task, start=False)
            jobs.submit(cb, 'website', 'Süd', task, start=False)
            self.assertIsNone(jobs.claim(ca, kinds=('website',)), 'Nord ist offline: Netzschritt wartet')
            self.assertIsNotNone(jobs.claim(cb, kinds=('website',)), 'Süd ist online: Netzschritt läuft')

    def test_login_lockout_per_organisation(self):
        auth._FAILS.clear()
        for db in (self.a, self.b):
            with connect(db) as conn:
                if not auth.has_users(conn):
                    auth.setup_admin(conn, {'username': 'admin', 'password': PW})
                    conn.commit()
        with connect(self.a) as ca:
            for i in range(auth.MAX_FAILS):
                with self.assertRaises(auth.NotLoggedIn):
                    auth.login(ca, {'username': 'admin', 'password': 'falsch'}, client=f'10.0.0.{i}')
            with self.assertRaises(auth.Throttled):
                auth.login(ca, {'username': 'admin', 'password': PW}, client='10.0.1.1')
        with connect(self.b) as cb:
            user, _ = auth.login(cb, {'username': 'admin', 'password': PW}, client='10.0.1.2')
            self.assertEqual(user['username'], 'admin', 'Sperre bei Nord sperrt Süd nicht')
        auth._FAILS.clear()

    def test_credentials_stay_with_their_database(self):
        credentials.put(self.a, 'imap', 'nord-geheim')
        try:
            self.assertEqual(credentials.get(self.a, 'imap'), 'nord-geheim')
            self.assertIsNone(credentials.get(self.b, 'imap'))
        finally:
            credentials.forget(self.a, 'imap')

    def test_batch_runner_numbers_per_organisation(self):
        release = threading.Event()
        with mock.patch.object(imprint_batch, '_run', lambda db, rid: release.wait(10)):
            self.assertTrue(imprint_batch.start_runner(self.a, 1))
            self.assertFalse(imprint_batch.start_runner(self.a, 1), 'derselbe Lauf läuft schon')
            self.assertTrue(imprint_batch.start_runner(self.b, 1), 'Lauf 1 bei Süd ist ein anderer Lauf')
            release.set()
            imprint_batch.wait_for(1)

    def test_scheduler_per_organisation(self):
        with mock.patch.object(quality, 'run_due', lambda conn, db: []):
            ta = quality.start_scheduler(self.a, every_seconds=3600)
            tb = quality.start_scheduler(self.b, every_seconds=3600)
            try:
                self.assertIsNot(ta, tb, 'jede Organisation hat ihren Planer')
                self.assertIs(quality.start_scheduler(self.a), ta)
            finally:
                quality.stop_scheduler(self.a)
                quality.stop_scheduler(self.b)

    def test_threads_carry_the_tenant(self):
        seen = []
        t = tenancy.thread(lambda: seen.append(tenancy.current()), self.b)
        t.start()
        t.join(5)
        self.assertEqual(seen, [tenancy.db_key(self.b)])
        self.assertIsNone(tenancy.current())

    def test_keys(self):
        with connect(self.a) as conn:
            self.assertEqual(tenancy.conn_key(conn), tenancy.db_key(self.a))
        import sqlite3
        m1, m2 = sqlite3.connect(':memory:'), sqlite3.connect(':memory:')
        self.assertNotEqual(tenancy.conn_key(m1), tenancy.conn_key(m2))


class FilesAndExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        self.db = Path(self.dir.create('nord', 'Nord')['db_path'])

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_files_stay_in_the_organisation_folder(self):
        folder = self.db.parent
        for kind, path in tenancy.org_files(self.db).items():
            self.assertEqual(Path(path).resolve().parent if kind != 'datenbank' else folder, folder, kind)
        other = Path(self.dir.create('sued', 'Süd')['db_path'])
        mine, theirs = tenancy.org_files(self.db), tenancy.org_files(other)
        self.assertFalse(set(map(str, mine.values())) & set(map(str, theirs.values())), 'keine gemeinsame Datei')

    def test_backups_land_in_the_organisation_folder(self):
        from sales_tool.accounting_api import create_backup
        path = Path(create_backup(self.db)['path'])
        self.assertEqual(path.parent, tenancy.org_files(self.db)['sicherungen'])

    def test_export_without_secrets(self):
        import sqlite3
        import zipfile
        with connect(self.db) as conn:
            auth.setup_admin(conn, {'username': 'admin', 'password': PW})
            auth.create_session(conn, 1)
            conn.execute("INSERT INTO leads(company, stage) VALUES ('Export Fiktiv GmbH', 'neu')")
            conn.commit()
        credentials.put(self.db, 'imap', 'nicht-im-export')
        shots = tenancy.org_files(self.db)['bildschirmfotos']
        (shots / '1').mkdir(parents=True)
        (shots / '1' / 'start.png').write_bytes(b'png')
        try:
            out = Path(self.tmp.name) / 'export' / 'nord.zip'
            res = tenancy.export_organization(self.db, out)
            self.assertEqual((res['screenshots'], res['format']), (1, tenancy.EXPORT_FORMAT))
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
                manifest = json.loads(zf.read('manifest.json'))
                raw = b''.join(zf.read(n) for n in names)
                zf.extract('signaldesk.sqlite3', self.tmp.name)
            self.assertEqual(names, {'signaldesk.sqlite3', 'manifest.json', 'bildschirmfotos/1/start.png'})
            self.assertNotIn(b'nicht-im-export', raw)
            self.assertEqual(manifest['tables']['leads']['rows'], 1)
            self.assertTrue(manifest['tables']['invoices']['retention'] == 'gobd' and manifest['tables']['leads']['personal'])
            copy = sqlite3.connect(str(Path(self.tmp.name) / 'signaldesk.sqlite3'))
            try:
                self.assertEqual(copy.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
                self.assertEqual(copy.execute('SELECT pw_hash FROM users').fetchone()[0], '')
                self.assertEqual(copy.execute('SELECT company FROM leads').fetchone()[0], 'Export Fiktiv GmbH')
            finally:
                copy.close()
            with connect(self.db) as conn:
                self.assertNotEqual(conn.execute('SELECT pw_hash FROM users').fetchone()[0], '', 'Original unverändert')
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 1)
            with self.assertRaises(tenancy.TenantError):
                tenancy.export_organization(self.db, out)
        finally:
            credentials.forget(self.db, 'imap')


class CliTests(unittest.TestCase):
    def test_create_list_archive_export(self):
        import subprocess
        tool = str(Path(__file__).resolve().parent.parent / 'tools' / 'organisationen.py')
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            run = lambda *a: subprocess.run([sys.executable, tool, '--root', str(Path(tmp) / 'm'), *a], capture_output=True, text=True)
            self.assertEqual(run('anlegen', 'nord', 'Nord').returncode, 0)
            self.assertEqual(run('anlegen', '../x', 'X').returncode, 1)
            self.assertEqual(json.loads(run('liste').stdout)[0]['slug'], 'nord')
            res = run('export', 'nord', '--out', str(Path(tmp) / 'nord.zip'))
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(run('archivieren', 'nord').returncode, 0)
            self.assertEqual(json.loads(run('liste').stdout), [])


if __name__ == '__main__':
    unittest.main()
