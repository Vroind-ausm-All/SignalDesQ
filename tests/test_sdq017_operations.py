"""SDQ-017 bis SDQ-020: Betrieb einer Mehrmandanten-Installation.

Zustand (/healthz, /readyz), Sicherungssatz aller Organisationen mit Wiederherstellungstest und Zurückspielen,
Betriebsprotokoll als JSON-Zeilen ohne Cookies und Abfragen, sauberes Beenden des Dienstes. Alle Daten fiktiv."""
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))

from sales_tool import accounts, audit_trail, auth, backup_crypto, ops, tenancy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402
from test_sdq014_multi_tenant import PW, Client  # noqa: E402

import organisationen  # noqa: E402

SET_PW = 'Sicherungs-Passphrase-2026'


def _add(db_path, company):
    with connect(db_path) as conn:
        conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'neu')", (company,))
        conn.commit()


def _companies(db_path):
    with connect(db_path) as conn:
        return sorted(r[0] for r in conn.execute('SELECT company FROM leads'))


class Base(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name) / 'm'
        self.dir = tenancy.Directory(self.root)
        self.orgs = {}
        for slug, name in (('nord', 'Nord'), ('sued', 'Süd'), ('alt', 'Alt')):
            self.orgs[slug] = self.dir.create(slug, name)['db_path']
            _add(self.orgs[slug], f'{name} Fiktiv GmbH')
        self.dir.archive('alt')
        accounts.create_account(self.dir, 'erika', PW)
        accounts.set_membership(self.dir, 'erika', 'nord', 'vertrieb')

    def tearDown(self):
        self.tmp.cleanup()


class HealthAndLogTests(Base):
    def setUp(self):
        super().setUp()
        self.stream = StringIO()
        self.logger = ops.access_logger(stream=self.stream)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir, logger=self.logger))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def lines(self):
        return [json.loads(x) for x in self.stream.getvalue().splitlines() if x.strip()]

    def test_healthz_without_login(self):
        status, data, _ = Client(self.base).call('/healthz')
        self.assertEqual((status, data['status']), (200, 'ok'))

    def test_readyz_local_detail_remote_summary(self):
        status, data, _ = Client(self.base).call('/readyz')
        self.assertEqual((status, data['status']), (200, 'bereit'))  # fehlende Sicherung ist nur eine Warnung
        names = {c['name']: c for c in data['checks']}
        self.assertEqual(set(names), {'verzeichnis', 'organisationen', 'speicher', 'sicherung'})
        self.assertEqual(names['sicherung']['level'], 'warnung')
        self.assertEqual(names['organisationen']['info'], '2 aktiv')
        status, data, _ = Client(self.base).call('/readyz', headers={'X-Forwarded-For': '203.0.113.7'})
        self.assertEqual(set(data), {'status', 'version'})  # über den Proxy: keine Einzelheiten

    def test_readyz_fails_on_outdated_org_schema(self):
        with sqlite3.connect(self.orgs['sued']) as c:
            c.execute('PRAGMA user_version = 3')
        status, data, _ = Client(self.base).call('/readyz')
        self.assertEqual((status, data['status']), (503, 'nicht_bereit'))
        org = next(c for c in data['checks'] if c['name'] == 'organisationen')
        self.assertIn('sued: Schema 3', org['info'])

    def test_request_id_and_json_log_without_secrets(self):
        c = Client(self.base)
        c.login('erika')
        c.call('/api/zentral/enter', 'POST', {'slug': 'nord'})
        status, _, headers = c.call('/api/leads?q=Geheimname&token=abc')
        self.assertEqual(status, 200)
        rid = headers['X-Request-ID']
        self.assertRegex(rid, r'^[0-9a-f]{12}$')
        c.call('/kalender/AbCdEfGhIjKlMnOpQrStUvWxYz123456.ics')
        deadline = time.time() + 5  # die Zeile entsteht erst nach der Antwort
        while not any(x['route'] == '/kalender/:id' for x in self.lines()) and time.time() < deadline:
            time.sleep(0.05)
        logged = self.lines()
        entry = next(x for x in logged if x.get('rid') == rid)
        self.assertEqual((entry['method'], entry['route'], entry['status'], entry['org']), ('GET', '/api/leads', 200, 'nord'))
        text = self.stream.getvalue()
        for secret in ('Geheimname', 'token=abc', c.cookies[auth.COOKIE], c.cookies[accounts.CENTRAL_COOKIE], PW,
                       'AbCdEfGhIjKlMnOpQrStUvWxYz123456', '127.0.0.1'):
            self.assertNotIn(secret, text)
        self.assertTrue(any(x['route'] == '/kalender/:id' for x in logged))
        self.assertTrue(any(x['route'] == '/api/zentral/login' and x['status'] == 200 for x in logged))

    def test_unauthorized_logged_as_warning(self):
        Client(self.base).call('/api/leads')
        entry = self.lines()[-1]
        self.assertEqual((entry['status'], entry['level']), (401, 'warning'))

    def test_route_label(self):
        self.assertEqual(ops.route_label('/api/leads/42/notes?x=1'), '/api/leads/:id/notes')
        self.assertEqual(ops.route_label('/rechnung/7#druck'), '/rechnung/:id')


class BackupTests(Base):
    def test_backup_covers_directory_and_all_orgs_including_archived(self):
        m = ops.backup_all(self.dir, actor='betreiber:test')
        files = {f['file']: f for f in m['files']}
        self.assertEqual(set(files), {'organisationen.sqlite3', 'orgs/nord.sqlite3', 'orgs/sued.sqlite3', 'orgs/alt.sqlite3'})
        self.assertEqual(m['organizations'], 3)
        self.assertEqual(files['orgs/nord.sqlite3']['rows']['leads'], 1)
        report = ops.verify_backup(self.dir, m['name'], actor='betreiber:test')
        self.assertTrue(report['ok'], report)
        self.assertEqual(ops.list_backups(self.dir)[0]['verified'], True)
        self.assertIsNotNone(ops.last_verified_backup(self.dir))
        actions = [e['action'] for e in audit_trail.events(self.dir)]
        self.assertIn('sicherung_angelegt', actions)
        self.assertIn('sicherung_geprueft', actions)

    def test_tampered_file_fails_restore_test(self):
        m = ops.backup_all(self.dir)
        target = Path(m['path']) / 'orgs' / 'sued.sqlite3'
        with sqlite3.connect(target) as c:
            c.execute("INSERT INTO leads(company, stage) VALUES ('Untergeschoben', 'neu')")
        report = ops.verify_backup(self.dir, m['name'])
        self.assertFalse(report['ok'])
        bad = next(f for f in report['files'] if not f['ok'])
        self.assertEqual(bad['slug'], 'sued')
        self.assertIn('Prüfsumme', bad['problem'])
        self.assertIsNone(ops.last_verified_backup(self.dir))

    def test_rows_compared_against_manifest(self):
        m = ops.backup_all(self.dir)
        folder = Path(m['path'])
        target = folder / 'orgs' / 'nord.sqlite3'
        with sqlite3.connect(target) as c:
            c.execute('DELETE FROM leads')
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        for f in manifest['files']:  # jemand passt die Prüfsumme an – die Zeilenzahlen verraten es trotzdem
            if f['file'] == 'orgs/nord.sqlite3':
                f['sha256'] = ops._sha256(target)
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        report = ops.verify_backup(self.dir, m['name'])
        self.assertIn('Zeilenzahlen', next(f for f in report['files'] if not f['ok'])['problem'])

    def test_aborted_run_leaves_no_set(self):
        real = ops._snapshot
        calls = []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) == 3:
                raise OSError('Datenträger voll (simuliert)')
            return real(src, dst)

        with mock.patch.object(ops, '_snapshot', flaky):
            with self.assertRaises(OSError):
                ops.backup_all(self.dir)
        self.assertEqual(ops.list_backups(self.dir), [])
        self.assertEqual(list((self.root / ops.BACKUP_DIR).iterdir()), [])

    def test_restore_one_org_from_set(self):
        m = ops.backup_all(self.dir)
        self.assertTrue(ops.verify_backup(self.dir, m['name'])['ok'])
        _add(self.orgs['nord'], 'Später Fiktiv KG')
        _add(self.orgs['sued'], 'Süd Später Fiktiv KG')
        with self.assertRaises(ValueError):
            ops.restore_org(self.dir, m['name'], 'nord')  # ohne Bestätigung nichts
        out = ops.restore_org(self.dir, m['name'], 'nord', confirm=True, actor='betreiber:test')
        self.assertTrue(out['restored'])
        self.assertEqual(_companies(self.orgs['nord']), ['Nord Fiktiv GmbH'])
        self.assertEqual(_companies(self.orgs['sued']), ['Süd Fiktiv GmbH', 'Süd Später Fiktiv KG'])  # andere unberührt
        self.assertTrue(Path(out['safety_backup']).exists())  # vorheriger Stand liegt bereit
        self.assertIn('organisation_zurueckgespielt', [e['action'] for e in audit_trail.events(self.dir)])
        with self.assertRaises(ValueError):
            ops.restore_org(self.dir, '../nord', 'nord', confirm=True)
        with self.assertRaises(LookupError):
            ops.restore_org(self.dir, m['name'], 'gibtsnicht', confirm=True)

    @unittest.skipUnless(backup_crypto.available(), 'Paket cryptography fehlt')
    def test_encrypted_set(self):
        m = ops.backup_all(self.dir, password=SET_PW)
        self.assertTrue(m['encrypted'])
        for f in m['files']:
            blob = (Path(m['path']) / f['file']).read_bytes()
            self.assertTrue(f['file'].endswith('.sdenc'))
            self.assertTrue(blob.startswith(backup_crypto.MAGIC))
            self.assertNotIn(b'Fiktiv GmbH', blob)
            self.assertNotIn(b'erika', blob)
        with self.assertRaises(ValueError):
            ops.verify_backup(self.dir, m['name'])
        wrong = ops.verify_backup(self.dir, m['name'], password='falsche-Passphrase-1')
        self.assertFalse(wrong['ok'])
        self.assertTrue(ops.verify_backup(self.dir, m['name'], password=SET_PW)['ok'])
        _add(self.orgs['sued'], 'Neu Fiktiv KG')
        ops.restore_org(self.dir, m['name'], 'sued', password=SET_PW, confirm=True)
        self.assertEqual(_companies(self.orgs['sued']), ['Süd Fiktiv GmbH'])
        with self.assertRaises(ValueError):
            ops.backup_all(self.dir, password='kurz')

    def test_prune_only_on_request_and_keeps_newest_verified(self):
        names = [ops.backup_all(self.dir)['name'] for _ in range(3)]
        ops.verify_backup(self.dir, names[0])  # ältester ist der einzige geprüfte
        self.assertEqual(len(ops.list_backups(self.dir)), 3)  # nichts verschwindet von selbst
        out = ops.prune_backups(self.dir, 1)
        self.assertEqual(set(out['kept']), {names[2], names[0]})
        self.assertEqual(out['removed'], [names[1]])
        with self.assertRaises(ValueError):
            ops.prune_backups(self.dir, 0)

    def test_cli_backup_verify_and_state(self):
        with mock.patch.dict(os.environ, {'SIGNALDESK_SICHERUNG_PASSWORT': SET_PW}), mock.patch('sys.stdout', new=StringIO()) as out, \
                mock.patch('sys.stderr', new=StringIO()):
            args = ['--root', str(self.root), 'sichern', '--pruefen'] + (['--verschluesselt'] if backup_crypto.available() else [])
            self.assertEqual(organisationen.main(args), 0)
            name = json.loads(out.getvalue())['name']
            self.assertEqual(organisationen.main(['--root', str(self.root), 'sicherung-pruefen', name]), 0)
            self.assertEqual(organisationen.main(['--root', str(self.root), 'zustand']), 0)
            self.assertEqual(organisationen.main(['--root', str(self.root), 'protokoll-pruefen']), 0)
            self.assertEqual(organisationen.main(['--root', str(self.root), 'zurueckspielen', name, 'nord']), 1)  # ohne --ja


class ServiceTests(unittest.TestCase):
    def test_sigterm_stops_cleanly_and_logs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp) / 'm'
            tenancy.Directory(root).create('nord', 'Nord')
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0))
                port = s.getsockname()[1]
            log = Path(tmp) / 'betrieb.log'
            env = {**os.environ, 'NO_PROXY': '127.0.0.1,localhost'}
            proc = subprocess.Popen([sys.executable, '-m', 'sales_tool.multi_server', '--root', str(root), '--port', str(port),
                                     '--no-scheduler', '--log-file', str(log)], cwd=ROOT, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline = time.time() + 30
                while True:
                    try:
                        with opener.open(f'http://127.0.0.1:{port}/healthz', timeout=2) as r:
                            self.assertEqual(json.loads(r.read())['status'], 'ok')
                        break
                    except OSError:
                        if time.time() > deadline or proc.poll() is not None:
                            self.fail('Dienst startet nicht: ' + proc.stderr.read().decode(errors='replace')[-500:])
                        time.sleep(0.2)
                proc.send_signal(signal.SIGTERM)
                self.assertEqual(proc.wait(timeout=15), 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.stderr.close()
            events = [json.loads(x)['msg'] for x in log.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(events[0], 'start')
            self.assertIn('anfrage', events)
            self.assertEqual(events[-2:], ['stopp', 'beendet'])

    def test_fixed_port_no_silent_fallback(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, socket.socket() as blocker:
            blocker.bind(('127.0.0.1', 0))
            blocker.listen(1)
            port = blocker.getsockname()[1]
            proc = subprocess.run([sys.executable, '-m', 'sales_tool.multi_server', '--root', str(Path(tmp) / 'm'), '--port', str(port),
                                   '--no-scheduler'], cwd=ROOT, capture_output=True, timeout=60)
            self.assertNotEqual(proc.returncode, 0)  # belegter Port: Fehler statt still auf einen anderen Port auszuweichen


if __name__ == '__main__':
    unittest.main()
