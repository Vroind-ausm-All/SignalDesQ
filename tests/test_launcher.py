"""Ein-Klick-Start: Bootstrap-Entscheidungen, Port-Ausweichen, Erkennung laufender Instanz."""
import contextlib
import os
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

from sales_tool import bootstrap
from sales_tool.model import connect, init_db
from sales_tool.server import bind_server, make_handler, running_instance

ROOT = Path(__file__).resolve().parent.parent


class BootstrapTests(unittest.TestCase):
    def test_install_decision_uses_marker_and_requirement_hash(self):
        self.assertTrue(bootstrap.needs_install({}, 'abc'))
        self.assertTrue(bootstrap.needs_install({'requirements': 'old', 'crawler_ok': True}, 'abc'))
        self.assertTrue(bootstrap.needs_install({'requirements': 'abc', 'crawler_ok': False}, 'abc'))
        failed_today = {'requirements': 'abc', 'crawler_ok': False, 'last_attempt': '2026-11-04'}
        self.assertFalse(bootstrap.needs_install(failed_today, 'abc', today='2026-11-04'))
        self.assertTrue(bootstrap.needs_install(failed_today, 'abc', today='2026-11-05'))
        self.assertFalse(bootstrap.needs_install({'requirements': 'abc', 'crawler_ok': True}, 'abc'))
        self.assertTrue(bootstrap.needs_install({'requirements': 'abc', 'crawler_ok': True}, 'abc', reinstall=True))

    def test_marker_roundtrip_and_broken_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.json'
            self.assertEqual(bootstrap.read_marker(path), {})
            bootstrap.write_marker({'crawler_ok': True}, path)
            self.assertEqual(bootstrap.read_marker(path), {'crawler_ok': True})
            path.write_text('{kaputt')
            self.assertEqual(bootstrap.read_marker(path), {})

    def test_requirements_hash_changes_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / 'r.txt'
            req.write_text('playwright>=1.50,<2\n')
            first = bootstrap.requirements_hash(req)
            req.write_text('playwright>=1.51,<2\n')
            self.assertNotEqual(first, bootstrap.requirements_hash(req))
            self.assertEqual(bootstrap.requirements_hash(Path(tmp) / 'fehlt.txt'), 'none')

    def test_zip_preview_detection_only_on_windows(self):
        temp_zip = Path('C:/Users/Alex/AppData/Local/Temp/Temp1_SignalDesk.zip/SignalDesk')
        documents = Path('C:/Users/Alex/Documents/SignalDesk')  # vor dem Umschalten anlegen: Python < 3.12 baut sonst einen WindowsPath
        with mock.patch.object(bootstrap.os, 'name', 'nt'):
            self.assertTrue(bootstrap.is_inside_zip_preview(temp_zip))
            self.assertFalse(bootstrap.is_inside_zip_preview(documents))
        with mock.patch.object(bootstrap.os, 'name', 'posix'):
            self.assertFalse(bootstrap.is_inside_zip_preview(temp_zip))

    def test_crawler_failure_does_not_block_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'marker.json'
            with mock.patch.object(bootstrap, 'MARKER', marker), \
                 mock.patch.object(bootstrap, 'run', return_value=False) as run, \
                 mock.patch.object(bootstrap, 'read_marker', lambda path=marker: {}), \
                 mock.patch.object(bootstrap, 'write_marker', lambda data, path=marker: marker.write_text(str(data))):
                self.assertFalse(bootstrap.ensure_crawler(Path('python')))
                self.assertEqual(run.call_count, 1)  # pip schlägt fehl → kein Browser-Download, kein Abbruch
            self.assertIn("'crawler_ok': False", marker.read_text())

    def test_main_passes_open_browser_and_setup_only(self):
        with mock.patch.object(bootstrap, 'instance_running', return_value=False), \
             mock.patch.object(bootstrap, 'ensure_venv', return_value=Path('/venv/python')), \
             mock.patch.object(bootstrap, 'ensure_crawler', return_value=True), \
             mock.patch.object(bootstrap, 'ensure_shortcut'), \
             mock.patch.object(bootstrap.subprocess, 'call', return_value=0) as call:
            self.assertEqual(bootstrap.main(['--port', '9000']), 0)
            cmd = call.call_args[0][0]
            self.assertIn('--open-browser', cmd)
            self.assertEqual(cmd[cmd.index('--port') + 1], '9000')
            call.reset_mock()
            bootstrap.main(['--no-browser'])
            self.assertNotIn('--open-browser', call.call_args[0][0])
            call.reset_mock()
            self.assertEqual(bootstrap.main(['--setup-only']), 0)
            call.assert_not_called()

    def test_second_start_only_opens_browser(self):
        with mock.patch.object(bootstrap, 'instance_running', return_value=True), \
             mock.patch.object(bootstrap, 'ensure_venv') as venv_step, \
             mock.patch('webbrowser.open') as browser:
            self.assertEqual(bootstrap.main([]), 0)
            venv_step.assert_not_called()
            browser.assert_called_once_with('http://127.0.0.1:8765', new=2)

    def test_launcher_files_exist_with_correct_line_endings(self):
        bat = (ROOT / 'SignalDesk_starten.bat').read_bytes()
        self.assertIn(b'\r\n', bat)
        self.assertNotIn(b'\n', bat.replace(b'\r\n', b''))
        self.assertIn(b'sales_tool.bootstrap', bat)
        for name in ('SignalDesk_starten.command', 'start.sh'):
            data = (ROOT / name).read_bytes()
            self.assertNotIn(b'\r\n', data)
            self.assertTrue(data.startswith(b'#!'))
            if os.name != 'nt':
                self.assertTrue(os.access(ROOT / name, os.X_OK), name)


class MigrationBackupTests(unittest.TestCase):
    def test_backup_only_for_older_existing_database(self):
        import sqlite3
        from sales_tool.server import SCHEMA_VERSION, backup_before_migration
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'akquise.sqlite3'
            self.assertIsNone(backup_before_migration(db))  # neue Installation
            with contextlib.closing(sqlite3.connect(db)) as raw, raw:
                raw.execute('CREATE TABLE leads (id INTEGER)')
            path = backup_before_migration(db)  # alte Version (user_version 0)
            self.assertTrue(path and Path(path).exists())
            with contextlib.closing(sqlite3.connect(db)) as raw, raw:
                raw.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
            self.assertIsNone(backup_before_migration(db))


class PortTests(unittest.TestCase):
    def test_bind_server_skips_busy_port(self):
        blocker = socket.socket()
        blocker.bind(('127.0.0.1', 0))
        blocker.listen(1)
        busy = blocker.getsockname()[1]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / 'p.sqlite3'
                with connect(db) as conn:
                    init_db(conn)
                server, port = bind_server(make_handler(db), busy, attempts=5)
                try:
                    self.assertNotEqual(port, busy)
                    self.assertTrue(busy < port <= busy + 4)
                finally:
                    server.server_close()
        finally:
            blocker.close()

    def test_running_instance_recognises_only_signaldesk(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'r.sqlite3'
            with connect(db) as conn:
                init_db(conn)
            server, port = bind_server(make_handler(db), 18765, attempts=50)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                self.assertTrue(running_instance(port))
            finally:
                server.shutdown()
                server.server_close()

        class Other(BaseHTTPRequestHandler):
            server_version = 'Apache/2.4'

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *a):
                pass
        other = ThreadingHTTPServer(('127.0.0.1', 0), Other)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        try:
            self.assertFalse(running_instance(other.server_address[1]))
        finally:
            other.shutdown()
            other.server_close()
        free = socket.socket()
        free.bind(('127.0.0.1', 0))
        free_port = free.getsockname()[1]
        free.close()
        self.assertFalse(running_instance(free_port, timeout=0.5))


if __name__ == '__main__':
    unittest.main()
