"""SDQ-029 bis SDQ-032: offene Betriebspunkte ohne Freigabe.

- SDQ-029: Referenzliste aus der Tabellenvorlage (xlsx/CSV) umwandeln.
- SDQ-030: Wiederkehrende Aufträge ruhen, solange eine Organisation nur lesbar ist.
- SDQ-031: Sicherungssatz an einen zweiten Ort kopieren; ganze Installation in einen leeren Ordner wiederherstellen.
- SDQ-032: Abmelden nach Leerlauf (Mehrmandanten-Betrieb).

Alle Daten fiktiv."""
import csv
import json
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
sys.path.insert(0, str(ROOT / 'tools'))

from sales_tool import abrechnung, accounts, auth, backup_crypto, betreiber, ops, quality, tenancy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402
from sales_tool.research import benchmark as bm  # noqa: E402
from test_sdq014_multi_tenant import PW, Client  # noqa: E402

import research_benchmark  # noqa: E402

SET_PW = 'Sicherungs-Passphrase-2026'
HEADER = ['Suche (q1–q5)', 'Ref-Nr', 'Firmenname', 'Rechtsform', 'PLZ', 'Ort', 'Website (oder "keine")',
          'Registernummer (z. B. HRB 12345, Amtsgericht)', 'Status', 'Beleg 1', 'Beleg 2', 'Prüfer 1', 'Prüfer 2',
          'Prüfdatum', 'Notiz']
ROW_A = ['q1', 'r1', 'Alpha Fiktiv GmbH', 'GmbH', '70173', 'Stuttgart', 'https://alpha.example', 'HRB 1 Fiktiv', 'aktiv',
         'Handelsregister-Auszug', 'Website Impressum', 'Prüferin A', 'Prüfer B', '2026-11-20', '']
ROW_B = ['q1', 'r2', 'Beta Fiktiv KG', 'KG', '70174', 'Stuttgart', 'keine', '', 'aktiv', 'Telefonbuch', '', 'Prüferin A', '',
         '2026-11-21', '']
ROW_C = ['q2', 'r1', 'Gamma Fiktiv eK', '', '70175', 'Stuttgart', '', '', 'geschlossen', 'Gewerbeamt', '', 'Prüfer B', '',
         '2026-11-21', 'schon 2025 aufgegeben']


def _add(db_path, company):
    with connect(db_path) as conn:
        conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'neu')", (company,))
        conn.commit()


def _companies(db_path):
    with connect(db_path) as conn:
        return sorted(r[0] for r in conn.execute('SELECT company FROM leads'))


class ReferenceTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_to_valid_reference(self):
        ref = bm.reference_from_table([HEADER, ROW_A, ROW_B, [''] * len(HEADER), ROW_C],
                                      {'q1': {'description': 'Steuerberatung 70173–70199', 'complete': True}})
        self.assertEqual(bm.validate_reference(ref), [])
        self.assertFalse(ref['synthetic'])
        q1, q2 = ref['queries']
        self.assertEqual((q1['id'], q1['complete'], len(q1['companies'])), ('q1', True, 2))
        self.assertEqual((q2['id'], q2['complete'], len(q2['companies'])), ('q2', False, 1))
        a, b = q1['companies']
        self.assertEqual(a['website'], 'https://alpha.example')
        self.assertEqual(a['evidence'], ['Handelsregister-Auszug', 'Website Impressum'])
        self.assertEqual(a['checked_by'], ['Prüferin A', 'Prüfer B'])
        self.assertIsNone(b['website'])            # „keine“: geprüft, es gibt keine
        self.assertNotIn('register_id', b)         # leer: nicht geprüft
        self.assertEqual(q2['companies'][0]['status'], 'geschlossen')

    def test_unknown_column_and_sample_row_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unbekannte Spalten.*Ansprechpartner'):
            bm.reference_from_table([HEADER + ['Ansprechpartner'], ROW_A + ['Frau Fiktiv']])
        sample = list(ROW_A)
        sample[2] = 'Beispiel Fiktiv GmbH (Zeile löschen)'
        with self.assertRaisesRegex(ValueError, 'Beispielzeile'):
            bm.reference_from_table([HEADER, sample])

    def test_cli_csv_semicolon_writes_only_valid_lists(self):
        good = self.dir / 'liste.csv'
        good.write_text('\n'.join(';'.join(r) for r in (HEADER, ROW_A, ROW_B)), encoding='utf-8-sig')
        out = self.dir / 'ref.json'
        with mock.patch('sys.stdout', new=StringIO()) as so:
            code = research_benchmark.main(['import-table', str(good), '--out', str(out), '--suche', 'q1=Steuerberatung',
                                            '--vollstaendig', 'q1', '--methode', 'q1=Register und Website, Stichtag 2026-11-20'])
        self.assertEqual(code, 0, so.getvalue())
        ref = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(ref['queries'][0]['method'], 'Register und Website, Stichtag 2026-11-20')
        self.assertTrue(ref['queries'][0]['complete'])
        bad = self.dir / 'fehler.csv'
        no_reviewer = list(ROW_A)
        no_reviewer[11] = no_reviewer[12] = ''
        with open(bad, 'w', encoding='utf-8', newline='') as fh:  # Komma-CSV mit Anführungszeichen (LibreOffice-Standard)
            csv.writer(fh).writerows([HEADER, no_reviewer])
        out2 = self.dir / 'ref2.json'
        with mock.patch('sys.stdout', new=StringIO()) as so:
            code = research_benchmark.main(['import-table', str(bad), '--out', str(out2)])
        self.assertEqual(code, 1)
        self.assertIn('checked_by fehlt', so.getvalue())
        self.assertFalse(out2.exists())

    def test_cli_xlsx(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest('openpyxl nicht installiert – xlsx-Weg übersprungen (CSV ist getestet)')
        wb = openpyxl.Workbook()
        ws = wb.active
        for r in (HEADER, ROW_A, ROW_C):
            ws.append(r)
        path = self.dir / 'liste.xlsx'
        wb.save(path)
        out = self.dir / 'ref.json'
        with mock.patch('sys.stdout', new=StringIO()):
            self.assertEqual(research_benchmark.main(['import-table', str(path), '--out', str(out)]), 0)
        self.assertEqual([q['id'] for q in json.loads(out.read_text(encoding='utf-8'))['queries']], ['q1', 'q2'])


class Base(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base_dir = Path(self.tmp.name)
        self.root = self.base_dir / 'm'
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


class SchedulerPauseTests(Base):
    def test_tick_skips_while_read_only_and_resumes(self):
        db = self.orgs['nord']
        with mock.patch.object(quality, 'run_due', return_value=['auftrag']) as run_due:
            abrechnung.start_trial(self.dir, 'nord', days=1, actor='betreiber:test')
            paused = lambda: abrechnung.state(self.dir, 'nord')['read_only']  # noqa: E731 – wie in multi_server
            self.assertEqual(quality.scheduler_tick(db, paused), ['auftrag'])     # Testphase läuft: Aufträge laufen
            with mock.patch.object(abrechnung, '_today', return_value=abrechnung._today().replace(year=2099)):
                self.assertIsNone(quality.scheduler_tick(db, paused))             # abgelaufen: nichts läuft
            self.assertEqual(run_due.call_count, 1)
            self.assertEqual(quality.scheduler_tick(db), ['auftrag'])             # ohne Sperre wie bisher
            self.assertEqual(run_due.call_count, 2)


class CopyBackupTests(Base):
    def test_copy_verifies_and_never_overwrites(self):
        m = ops.backup_all(self.dir, actor='betreiber:test')
        second = self.base_dir / 'zweiter-ort'
        out = ops.copy_backup(self.dir, m['name'], second, actor='betreiber:test')
        self.assertTrue(out['checksums_ok'])
        copied = second / m['name']
        self.assertTrue((copied / 'manifest.json').exists())
        self.assertEqual(sorted(p.name for p in second.iterdir()), [m['name']])  # kein .unfertig übrig
        for f in m['files']:
            self.assertEqual(ops._sha256(copied / f['file']), f['sha256'])
        with self.assertRaisesRegex(ValueError, 'nichts überschrieben'):
            ops.copy_backup(self.dir, m['name'], second)
        with self.assertRaisesRegex(ValueError, 'derselbe Ordner'):
            ops.copy_backup(self.dir, m['name'], ops.backup_root(self.dir))

    def test_corrupted_copy_is_removed(self):
        m = ops.backup_all(self.dir)
        second = self.base_dir / 'zweiter-ort'
        real = ops._sha256
        with mock.patch.object(ops, '_sha256', side_effect=lambda p: 'x' if '.unfertig' in str(p) else real(p)):
            with self.assertRaisesRegex(ValueError, 'Prüfsumme nach dem Kopieren'):
                ops.copy_backup(self.dir, m['name'], second)
        self.assertEqual(list(second.iterdir()), [])

    def test_cli_copy(self):
        m = ops.backup_all(self.dir)
        with mock.patch('sys.stdout', new=StringIO()) as so:
            code = betreiber.main(['--root', str(self.root), 'sicherung-kopieren', m['name'], '--nach', str(self.base_dir / 'usb')])
        self.assertEqual(code, 0, so.getvalue())
        self.assertTrue((self.base_dir / 'usb' / m['name'] / 'manifest.json').exists())


class RestoreInstallationTests(Base):
    def _check_restored(self, new_root):
        d = tenancy.Directory(new_root)
        self.assertEqual(sorted(o['slug'] for o in d.list(include_archived=True)), ['alt', 'nord', 'sued'])
        self.assertEqual(_companies(d.open('nord')), ['Nord Fiktiv GmbH'])
        self.assertEqual(_companies(d.path_for('alt')), ['Alt Fiktiv GmbH'])
        self.assertEqual(accounts.membership(d, 'erika', 'nord'), 'vertrieb')
        self.assertEqual(ops.readiness(d)['status'], 'bereit')
        return d

    def test_plain_set_into_empty_folder_and_server_answers(self):
        m = ops.backup_all(self.dir)
        new_root = self.base_dir / 'neu'
        with self.assertRaisesRegex(ValueError, 'bestätigen'):
            ops.restore_installation(m['path'], new_root)
        self.assertFalse(new_root.exists())
        out = ops.restore_installation(m['path'], new_root, confirm=True)
        self.assertEqual(sorted(out['organizations']), ['alt', 'nord', 'sued'])
        d = self._check_restored(new_root)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(d))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            c = Client(f'http://127.0.0.1:{server.server_port}')
            self.assertEqual(c.login('erika')[0], 200)            # Konto und Passwort kommen mit
            status, data, _ = c.call('/api/leads')
            self.assertEqual(status, 200)
            self.assertIn('Nord Fiktiv GmbH', json.dumps(data, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()

    def test_non_empty_target_and_tampered_set_refused(self):
        m = ops.backup_all(self.dir)
        with self.assertRaisesRegex(ValueError, 'nicht leer'):
            ops.restore_installation(m['path'], self.root, confirm=True)  # die laufende Installation bleibt unberührt
        self.assertEqual(_companies(self.orgs['nord']), ['Nord Fiktiv GmbH'])
        org_file = Path(m['path']) / next(f['file'] for f in m['files'] if f['slug'] == 'sued')
        with sqlite3.connect(org_file) as c:
            c.execute("INSERT INTO leads(company, stage) VALUES ('Untergeschoben Fiktiv', 'neu')")
        new_root = self.base_dir / 'neu'
        with self.assertRaisesRegex(ValueError, 'Prüfsumme'):
            ops.restore_installation(m['path'], new_root, confirm=True)
        self.assertFalse(new_root.exists())

    @unittest.skipUnless(backup_crypto.available(), 'cryptography nicht installiert – verschlüsselter Satz übersprungen')
    def test_encrypted_set_via_cli(self):
        m = ops.backup_all(self.dir, password=SET_PW)
        new_root = self.base_dir / 'neu'
        with self.assertRaisesRegex(ValueError, 'Passwort'):
            ops.restore_installation(m['path'], new_root, confirm=True)
        with mock.patch.dict('os.environ', {'SIGNALDESK_SICHERUNG_PASSWORT': SET_PW}), \
                mock.patch('sys.stdout', new=StringIO()) as so:
            code = betreiber.main(['--root', str(new_root), 'gesamt-wiederherstellen', m['path'], '--ja'])
        self.assertEqual(code, 0, so.getvalue())
        self._check_restored(new_root)

    def test_cli_plain_set_does_not_ask_for_password(self):
        m = ops.backup_all(self.dir)
        new_root = self.base_dir / 'neu'
        with mock.patch('getpass.getpass', side_effect=AssertionError('kein Passwort nötig')), \
                mock.patch.dict('os.environ', {'SIGNALDESK_SICHERUNG_PASSWORT': ''}), mock.patch('sys.stdout', new=StringIO()) as so:
            code = betreiber.main(['--root', str(new_root), 'gesamt-wiederherstellen', m['path'], '--ja'])
        self.assertEqual(code, 0, so.getvalue())
        self._check_restored(new_root)


class RejectedBodyTests(Base):
    """Windows-CI: Eine abgelehnte Anfrage (fremde Herkunft) mit ungelesenem Körper wurde hart abgebrochen
    (WinError 10053) statt mit 403 beantwortet. Der Server für mehrere Organisationen liest den Rest jetzt wie der Einzelplatz."""

    def test_foreign_origin_body_is_read_before_close(self):
        from sales_tool import multi_server, server as single
        seen = []

        def spy(handler, limit=1024 * 1024):
            single.drain_request(handler, limit)
            seen.append(handler.rfile.count - handler._body_from)

        srv = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            body = {'username': 'erika', 'password': PW, 'pad': 'x' * 200_000}
            with mock.patch.object(multi_server, 'drain_request', side_effect=spy):
                status, _, _ = Client(f'http://127.0.0.1:{srv.server_port}').call(
                    '/api/zentral/login', 'POST', body, headers={'Origin': 'http://evil.example'})
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(status, 403)
        self.assertEqual(seen, [len(json.dumps(body).encode())])


class IdleLogoutTests(Base):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(self.dir))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.client = Client(f'http://127.0.0.1:{self.server.server_port}')
        self.assertEqual(self.client.login('erika')[0], 200)  # genau eine Organisation: direkt hinein

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def _age(self, minutes):
        """Alle Sitzungen so tun lassen, als wären sie seit ``minutes`` Minuten unbenutzt."""
        with connect(self.orgs['nord']) as conn:
            conn.execute("UPDATE sessions SET last_seen=datetime('now', ?)", (f'-{minutes} minutes',))
            conn.commit()
        with self.dir._connect() as conn:
            conn.execute("UPDATE account_sessions SET last_seen=datetime('now', ?)", (f'-{minutes} minutes',))

    def test_default_sixty_minutes(self):
        self.assertEqual(accounts.idle_minutes(self.dir), 60)
        self._age(30)
        self.assertEqual(self.client.call('/api/leads')[0], 200)  # 30 Minuten: noch angemeldet, Zeit läuft neu
        self._age(61)
        self.assertEqual(self.client.call('/api/leads')[0], 401)
        self.assertEqual(self.client.call('/api/zentral/status')[1].get('logged_in'), False)
        with connect(self.orgs['nord']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)  # Sitzung gelöscht, nicht nur abgelehnt

    def test_work_in_org_keeps_central_session(self):
        self._age(50)
        self.assertEqual(self.client.call('/api/leads')[0], 200)
        with self.dir._connect() as conn:
            fresh = conn.execute("SELECT COUNT(*) FROM account_sessions WHERE last_seen > datetime('now', '-1 minutes')").fetchone()[0]
        self.assertEqual(fresh, 1)

    def test_setting_changes_limit_and_zero_turns_off(self):
        accounts.set_setting(self.dir, 'leerlauf_minuten', '15', actor='betreiber:test')
        self._age(20)
        self.assertEqual(self.client.call('/api/leads')[0], 401)
        accounts.set_setting(self.dir, 'leerlauf_minuten', '0', actor='betreiber:test')
        self.assertIsNone(accounts.idle_minutes(self.dir))
        self.assertEqual(self.client.login('erika')[0], 200)
        self._age(600)
        self.assertEqual(self.client.call('/api/leads')[0], 200)
        for bad in ('3', '721', 'abc'):
            with self.assertRaises(ValueError):
                accounts.set_setting(self.dir, 'leerlauf_minuten', bad)

    def test_old_sessions_without_last_seen_stay_valid(self):
        with connect(self.orgs['nord']) as conn:
            conn.execute("UPDATE sessions SET last_seen=''")
            conn.commit()
        self.assertEqual(self.client.call('/api/leads')[0], 200)

    def test_single_user_server_unchanged(self):
        with connect(self.orgs['nord']) as conn:
            user = conn.execute('SELECT * FROM users').fetchone()
            token = auth.create_session(conn, user['id'])
            conn.execute("UPDATE sessions SET last_seen=datetime('now', '-999 minutes')")
            conn.commit()
            self.assertIsNotNone(auth.session_user(conn, f'{auth.COOKIE}={token}'))  # ohne Grenze: wie bisher


if __name__ == '__main__':
    unittest.main()
