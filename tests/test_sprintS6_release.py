"""Masterplan 2.0 – Sprint 6: Windows-Release, Lockdateien, SBOM, Offline-Modus, Sicherung/Wiederherstellung.

Abnahme laut Plan: reproduzierbare Installation auf frischem Windows-Rechner (→ CI-Job „install“ mit
tools/install_check.py), keine Datenbankverluste, dokumentierte Einschränkungen. Diese Tests prüfen alles, was ohne
Netz und ohne Windows prüfbar ist; die echte Windows-Installation läuft in .github/workflows/tests.yml.
"""
import contextlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import build_release as br  # noqa: E402
import make_sbom as ms  # noqa: E402

from sales_tool import __version__, bootstrap, netpolicy  # noqa: E402
from sales_tool import backup_restore as bkr  # noqa: E402
from sales_tool import lead_finder as lf  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402
from sales_tool.accounting_api import create_backup  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import fetch, jobs  # noqa: E402
from sales_tool.research.fetchers.base import FetchError  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, make_handler, prepare_database  # noqa: E402
from sales_tool.website_analyzer import CrawlError, crawl_site  # noqa: E402


class VersionAndLockTests(unittest.TestCase):
    def test_versions_are_consistent(self):
        short = __version__.rsplit('.', 1)[0]
        from sales_tool.research.policy import AGENT
        self.assertIn(f'SignalDeskResearch/{short} ', AGENT)
        self.assertIn(f'v{short} ·', (ROOT / 'sales_tool/public/index.html').read_text(encoding='utf-8'))
        self.assertTrue((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').split('\n## ', 1)[1].startswith(__version__))
        handler = make_handler(Path(tempfile.mkdtemp()) / 'x.sqlite3')
        self.assertEqual(handler.server_version, f'SignalDesk/{short}')

    def test_lock_files_are_complete_and_hashed(self):
        for variant, spec in bootstrap.VARIANTS.items():
            for lock in bootstrap.lock_files(variant):
                self.assertTrue(lock.exists(), lock.name)
                pkgs = ms.parse_lock(lock)
                self.assertTrue(pkgs, lock.name)
                for p in pkgs:
                    self.assertRegex(p['version'], r'^\d')
                    self.assertTrue(p['hashes'], f"{lock.name}: {p['name']} ohne Prüfsumme")
        names = {p['name'] for p in ms.parse_lock(ROOT / 'requirements-lock-browser.txt')}
        self.assertTrue({'playwright', 'greenlet', 'pyee'} <= names)
        self.assertIn('cryptography', {p['name'] for p in ms.parse_lock(ROOT / 'requirements-lock-team.txt')})

    def test_sbom_lists_every_locked_package_with_license(self):
        bom = ms.build()
        self.assertEqual((bom['bomFormat'], bom['specVersion']), ('CycloneDX', '1.5'))
        self.assertEqual(bom['metadata']['component']['version'], __version__)
        libs = {c['name']: c for c in bom['components'] if c['type'] == 'library'}
        for lock in ROOT.glob('requirements-lock-*.txt'):
            for p in ms.parse_lock(lock):
                self.assertIn(p['name'], libs)
                self.assertEqual(libs[p['name']]['version'], p['version'])
                self.assertNotEqual(libs[p['name']]['licenses'][0].get('license', {}).get('name'), 'NOASSERTION', p['name'])
        data = [c for c in bom['components'] if c['type'] == 'data']
        self.assertEqual(data[0]['licenses'][0]['expression'], 'CC-BY-4.0')
        self.assertEqual(json.dumps(bom, sort_keys=True), json.dumps(ms.build(), sort_keys=True), 'deterministisch')
        md = ms.markdown(bom)
        self.assertIn('ODbL', md)
        committed = json.loads((ROOT / 'sbom' / 'signaldesk.cdx.json').read_text(encoding='utf-8'))
        self.assertEqual(committed['metadata']['component']['version'], __version__, 'SBOM neu erzeugen: python tools/make_sbom.py')


class ReleaseZipTests(unittest.TestCase):
    def test_reproducible_and_clean(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict('os.environ', {'SOURCE_DATE_EPOCH': '1790000000'}):
            a, da, n = br.build(Path(tmp) / 'a')
            b, db, _ = br.build(Path(tmp) / 'b')
            self.assertEqual(da, db, 'byte-gleich')
            with zipfile.ZipFile(a) as zf:
                names = zf.namelist()
                top = f'SignalDesk-{__version__}/'
                self.assertTrue(all(x.startswith(top) for x in names))
                rel = [x[len(top):] for x in names]
                for must in ('SignalDesk_starten.bat', 'SignalDesk_wiederherstellen.bat', 'requirements-lock-browser.txt',
                             'sbom/signaldesk.cdx.json', 'sales_tool/lead_imprint.py', 'MANIFEST.sha256', 'LICENSE'):
                    self.assertIn(must, rel)
                self.assertFalse([x for x in rel if x.startswith(('tests/', 'tools/', '.github/'))])
                self.assertFalse([x for x in rel if re.search(r'\.(sqlite3|sdenc)$', x)])
                self.assertEqual(len({i.date_time for i in zf.infolist()}), 1)
                bat = zf.read(top + 'SignalDesk_starten.bat')
                self.assertNotIn(b'\n', bat.replace(b'\r\n', b''))
                manifest = zf.read(top + 'MANIFEST.sha256').decode()
                self.assertEqual(len(manifest.splitlines()), n - 1)

    def test_secrets_and_databases_are_refused(self):
        with self.assertRaises(SystemExit):
            br.check_safe('daten/akquise.sqlite3', b'')
        with self.assertRaises(SystemExit):
            br.check_safe('notes.txt', b'key: ' + b'-----BEGIN ' + b'PRIVATE KEY-----')
        br.check_safe('README.md', b'Alles gut')

    def test_exported_source_manifest_can_build_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'README.md').write_text('source', encoding='utf-8')
            manifest = root / 'MANIFEST.sha256'
            manifest.write_text('a' * 64 + '  README.md\n', encoding='utf-8')
            with mock.patch.object(br, 'ROOT', root), mock.patch.object(br.subprocess, 'run', side_effect=FileNotFoundError):
                self.assertEqual(br.git_files(), ['README.md'])
                manifest.write_text('a' * 64 + '  ../README.md\n', encoding='utf-8')
                with self.assertRaises(SystemExit):
                    br.git_files()


class VariantTests(unittest.TestCase):
    def test_choose_variant(self):
        self.assertEqual(bootstrap.choose_variant('team', {'variant': 'basis'}, True), 'team')
        self.assertEqual(bootstrap.choose_variant(None, {'variant': 'basis'}, True), 'basis')
        self.assertEqual(bootstrap.choose_variant(None, {}, True, ask=lambda q: '1'), 'basis')
        self.assertEqual(bootstrap.choose_variant(None, {}, True, ask=lambda q: ''), 'browser')
        self.assertEqual(bootstrap.choose_variant(None, {}, False), 'browser')

    def test_install_uses_hashes_and_offline_wheels(self):
        lock = ROOT / 'requirements-lock-browser.txt'
        cmd = bootstrap.pip_install_cmd(Path('py'), lock)
        self.assertIn('--require-hashes', cmd)
        self.assertNotIn('--no-index', cmd)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(bootstrap, 'WHEELS', Path(tmp)):
            cmd = bootstrap.pip_install_cmd(Path('py'), lock)
            self.assertEqual(cmd[cmd.index('--find-links') + 1], tmp)
            self.assertIn('--no-index', cmd)

    def test_basis_installs_nothing_and_variant_change_reinstalls(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'm.json'
            with mock.patch.object(bootstrap, 'MARKER', marker), mock.patch.object(bootstrap, 'run', return_value=True) as run:
                self.assertTrue(bootstrap.ensure_crawler(Path('py'), variant='basis'))
                run.assert_not_called()
                self.assertEqual(json.loads(marker.read_text())['variant'], 'basis')
                self.assertTrue(bootstrap.ensure_crawler(Path('py'), variant='team'))
                calls = [c[0][0] for c in run.call_args_list]
                self.assertEqual(sum('--require-hashes' in c for c in calls), 2, 'browser + team je eine Lockdatei')
                self.assertTrue(any('playwright' in c and 'install' in c for c in calls))
                run.reset_mock()
                self.assertTrue(bootstrap.ensure_crawler(Path('py'), variant='team'))
                run.assert_not_called()

    def test_offline_flag_skips_install_and_starts_offline(self):
        with mock.patch.object(bootstrap, 'instance_running', return_value=False), \
             mock.patch.object(bootstrap, 'ensure_venv', return_value=Path('/venv/python')), \
             mock.patch.object(bootstrap, 'ensure_crawler') as crawler, mock.patch.object(bootstrap, 'ensure_shortcut'), \
             mock.patch.object(bootstrap.subprocess, 'call', return_value=0) as call:
            bootstrap.main(['--offline', '--no-browser'])
            crawler.assert_not_called()
            self.assertIn('--offline', call.call_args[0][0])

    def test_windows_helper_files(self):
        for name in ('SignalDesk_wiederherstellen.bat', 'SignalDesk_offline_starten.bat'):
            data = (ROOT / name).read_bytes()
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''), name)
            self.assertIn(b'SignalDesk_starten.bat', data)


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'o.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        netpolicy.STATE.update(stored=False, forced=False)
        self.conn.close()
        self.tmp.cleanup()

    def test_offline_blocks_every_network_path(self):
        netpolicy.set_offline(self.conn, True)
        with self.assertRaises(FetchError) as ctx:
            fetch('https://example.org/')
        self.assertEqual(ctx.exception.kind, 'offline')
        with self.assertRaises(CrawlError):
            crawl_site('https://example.org/')
        with self.assertRaises(lf.SourceError):
            lf._http('https://api.gleif.org/api/v1/lei-records', 'ua')
        with self.assertRaises(ValueError) as ctx:
            sw.start_sweep(self.conn, {'place': '70173', 'radius_km': 30, 'sources': ['gleif']}, self.db, start=False)
        self.assertIn('Offline-Modus', str(ctx.exception))
        from sales_tool.source_check import run_check
        self.assertTrue(run_check(self.conn)['offline'])
        netpolicy.STATE['stored'] = False
        self.assertTrue(netpolicy.load(self.conn), 'dauerhaft gespeichert')

    def test_network_jobs_wait_while_offline(self):
        calls = []
        jobs.HANDLERS['website'] = lambda db, payload, ctx: calls.append('web') or {}
        jobs.HANDLERS['catalog_import'] = lambda db, payload, ctx: calls.append('cat') or {}
        try:
            jobs.submit(self.conn, 'website', 'W', [{'key': 'w', 'kind': 'website', 'payload': {}}], start=False)
            jobs.submit(self.conn, 'catalog_import', 'C', [{'key': 'c', 'kind': 'catalog_import', 'payload': {}}], start=False)
            netpolicy.STATE['forced'] = True
            jobs.run_until_idle(self.db)
            self.assertEqual(calls, ['cat'], 'Katalog-Import ist lokal, Website wartet')
            netpolicy.STATE['forced'] = False
            jobs.run_until_idle(self.db)
            self.assertEqual(calls, ['cat', 'web'])
        finally:
            from sales_tool import sweep, research  # noqa: F401 – echte Handler wieder registrieren
            import importlib
            import sales_tool.research.catalog as cat
            importlib.reload(cat)
            jobs.HANDLERS['website'] = sweep._job_website

    def test_offline_http_route_and_cli_flag(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def call(method, path, body=None):
            c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
            c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b'{}')
        try:
            self.assertFalse(call('GET', '/api/system/offline')[1]['offline'])
            self.assertTrue(call('PUT', '/api/system/offline', {'enabled': True})[1]['offline'])
            self.assertEqual(call('PUT', '/api/system/offline', {'enabled': 'ja'})[0], 400)
            self.assertEqual(call('POST', '/api/sweeps', {'place': '70173', 'radius_km': 30, 'sources': ['gleif']})[0], 400)
            self.assertFalse(call('PUT', '/api/system/offline', {'enabled': False})[1]['offline'])
        finally:
            server.shutdown()
            server.server_close()
        out = subprocess.run([sys.executable, '-m', 'sales_tool', '--help'], cwd=ROOT, capture_output=True, text=True)
        self.assertIn('--offline', out.stdout)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'live.sqlite3'
        prepare_database(self.db)
        with connect(self.db) as c:
            c.execute("INSERT INTO leads(company) VALUES ('Vorher GmbH')")
            c.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def count(self):
        with connect(self.db) as c:
            return [r[0] for r in c.execute('SELECT company FROM leads ORDER BY id')]

    def test_restore_named_with_safety_backup(self):
        name = Path(create_backup(self.db)['path']).name
        with connect(self.db) as c:
            c.execute("INSERT INTO leads(company) VALUES ('Nachher GmbH')")
            c.commit()
        with self.assertRaises(ValueError):
            bkr.restore_named(self.db, name)  # ohne Bestätigung
        with self.assertRaises(ValueError):
            bkr.restore_named(self.db, '../../etc/passwd', confirm=True)
        r = bkr.restore_named(self.db, name, confirm=True)
        self.assertEqual(self.count(), ['Vorher GmbH'])
        self.assertTrue(Path(r['safety_backup']).name.endswith('-vor-wiederherstellung.sqlite3'))
        # Wiederherstellung ist selbst umkehrbar
        bkr.restore_named(self.db, Path(r['safety_backup']).name, confirm=True)
        self.assertEqual(self.count(), ['Vorher GmbH', 'Nachher GmbH'])
        names = [b['name'] for b in bkr.list_all(self.db)['backups']]
        self.assertTrue(any('vor-wiederherstellung' in n for n in names))

    def test_old_schema_is_migrated_and_newer_refused(self):
        old = Path(self.tmp.name) / 'alt.sqlite3'
        with connect(old) as c:  # Stand wie aus v1.17: jüngere Tabellen fehlen noch
            init_db(c)
            for t in ('search_profiles', 'day_closings', 'lead_not_duplicate'):
                c.execute(f'DROP TABLE {t}')
            c.execute("INSERT INTO leads(company) VALUES ('Uralt GmbH')")
            c.execute('PRAGMA user_version = 22')
            c.commit()
        r = bkr.restore(self.db, old, confirm=True)
        self.assertEqual((r['schema'], self.count()), (SCHEMA_VERSION, ['Uralt GmbH']))
        with connect(self.db) as c:
            self.assertTrue(c.execute("SELECT 1 FROM sqlite_master WHERE name='search_profiles'").fetchone(), 'auf aktuelles Schema migriert')
        newer = Path(self.tmp.name) / 'neu.sqlite3'
        with contextlib.closing(sqlite3.connect(newer)) as c, c:
            for t in ('leads', 'activities', 'tasks'):
                c.execute(f'CREATE TABLE {t}(id INTEGER PRIMARY KEY)')
            c.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')
        with self.assertRaises(ValueError) as ctx:
            bkr.restore(self.db, newer, confirm=True)
        self.assertIn('neueren SignalDesk-Version', str(ctx.exception))
        junk = Path(self.tmp.name) / 'kaputt.sqlite3'
        junk.write_bytes(b'kein sqlite')
        with self.assertRaises(ValueError):
            bkr.restore(self.db, junk, confirm=True)

    def test_gobd_refuses_losing_final_invoices(self):
        name = Path(create_backup(self.db)['path']).name
        with connect(self.db) as c:
            lid = c.execute("SELECT id FROM leads").fetchone()[0]
            c.execute("INSERT INTO invoices(lead_id, number, status, buyer_name) VALUES (?, 'RE-2026-0007', 'festgeschrieben', 'X')", (lid,))
            c.commit()
        with self.assertRaises(ValueError) as ctx:
            bkr.restore_named(self.db, name, confirm=True)
        self.assertIn('RE-2026-0007', str(ctx.exception))
        self.assertEqual(self.count(), ['Vorher GmbH'], 'nichts verändert')

    def test_broken_current_database_can_be_replaced(self):
        good = create_backup(self.db)['path']
        self.db.write_bytes(b'SQLite format 3\x00' + b'\x00' * 200)  # beschädigt
        for suffix in ('-wal', '-shm'):
            Path(str(self.db) + suffix).unlink(missing_ok=True)
        r = bkr.restore(self.db, good, confirm=True)
        self.assertTrue(r['current_was_broken'])
        self.assertTrue(r['safety_backup'].endswith('-beschaedigt.sqlite3'))
        self.assertEqual(self.count(), ['Vorher GmbH'])

    def test_encrypted_backup_roundtrip(self):
        from sales_tool import backup_crypto
        if not backup_crypto.available():
            self.skipTest('cryptography nicht installiert (Variante „team“)')
        enc = backup_crypto.create_encrypted_backup(self.db, {'password': 'ein-langes-passwort'})['path']
        with connect(self.db) as c:
            c.execute("INSERT INTO leads(company) VALUES ('Später GmbH')")
            c.commit()
        with self.assertRaises(ValueError):
            bkr.restore_named(self.db, Path(enc).name, password='falsches-passwort', confirm=True)
        bkr.restore_named(self.db, Path(enc).name, password='ein-langes-passwort', confirm=True)
        self.assertEqual(self.count(), ['Vorher GmbH'])

    def test_cli_and_http_upload(self):
        good = create_backup(self.db)['path']
        with connect(self.db) as c:
            c.execute("INSERT INTO leads(company) VALUES ('Weg GmbH')")
            c.commit()
        rc = bkr.main(['wiederherstellen', good, '--db', str(self.db), '--ja'])
        self.assertEqual((rc, self.count()), (0, ['Vorher GmbH']))
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            data = Path(good).read_bytes()
            c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=30)
            c.request('POST', '/api/backups/restore-upload?confirm=1', body=data, headers={'Content-Type': 'application/octet-stream'})
            r = c.getresponse()
            out = json.loads(r.read())
            self.assertEqual((r.status, out['after']['leads']), (200, 1), out)
            c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=30)
            c.request('POST', '/api/backups/restore-upload', body=data, headers={'Content-Type': 'application/octet-stream'})
            self.assertEqual(c.getresponse().status, 400, 'ohne Bestätigung')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
