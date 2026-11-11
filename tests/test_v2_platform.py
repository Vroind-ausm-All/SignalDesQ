"""2.0.0-dev4: Plattformfestigkeit – Fehler, die nur unter Python 3.10/3.11 oder Windows auftraten und die CI rot hielten.

- Kein Backslash in f-String-Ausdrücken (Syntaxfehler vor Python 3.12; das Programm startete dort nicht).
- Ausgaben brechen in einer Windows-Konsole ohne UTF-8 (cp1252) nicht ab.
- Nach der Datenbank-Vorbereitung bleibt keine Verbindung offen (unter Windows wäre die Datei sonst gesperrt).
"""
import ast
import gc
import io
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool import bootstrap  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


class SyntaxCompatibilityTests(unittest.TestCase):
    def test_no_backslash_or_reused_quote_inside_fstring_expressions(self):
        """Python 3.10/3.11 verbieten Backslash und das äußere Anführungszeichen im Ausdruck eines f-Strings."""
        bad = []
        files = [p for d in ('sales_tool', 'tools', 'tests') for p in (ROOT / d).rglob('*.py')]
        self.assertGreater(len(files), 80)
        for path in files:
            src = path.read_text(encoding='utf-8')
            for node in ast.walk(ast.parse(src)):
                if not isinstance(node, ast.JoinedStr):
                    continue
                whole = ast.get_source_segment(src, node) or ''
                quote = next((q for q in ('"""', "'''", '"', "'") if whole.lstrip('rRfFbB').startswith(q)), '')
                for part in node.values:
                    if isinstance(part, ast.FormattedValue):
                        seg = ast.get_source_segment(src, part.value) or ''
                        if '\\' in seg or (len(quote) == 1 and quote in seg and '\n' not in whole):
                            bad.append(f'{path.relative_to(ROOT)}:{part.lineno}: {seg[:60]}')
        self.assertEqual(bad, [], 'Ausdruck vorher in eine Variable legen')


class ConsoleEncodingTests(unittest.TestCase):
    def test_say_survives_cp1252_console(self):
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding='cp1252', errors='strict')
        with mock.patch.object(sys, 'stdout', out):
            bootstrap.say('② Variante „basis“: keine Zusatzpakete ← Enter ✓')
            out.flush()
        text = raw.getvalue().decode('cp1252')
        self.assertIn('Variante „basis“: keine Zusatzpakete', text)
        self.assertIn('?', text)  # nicht darstellbare Zeichen ersetzt, nicht abgebrochen


class ConnectionHygieneTests(unittest.TestCase):
    def test_prepare_database_leaves_no_open_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'alt.sqlite3')
            raw = sqlite3.connect(db)
            raw.executescript((Path(__file__).parent / 'fixtures' / 'migration' / 'v1_6.sql').read_text(encoding='utf-8'))
            raw.commit()
            raw.close()
            gc.collect()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', ResourceWarning)
                prepare_database(db)   # bestehende Datenbank: Sicherung + Migration
                prepare_database(db)   # zweiter Start: nichts zu tun
                gc.collect()
            leaks = [str(w.message) for w in caught if 'unclosed database' in str(w.message)]
            self.assertEqual(leaks, [])


class RestoreSafetyTests(unittest.TestCase):
    def test_two_restores_in_one_second_keep_both_safety_backups(self):
        """Früher überschrieb die zweite Wiederherstellung die Sicherheitskopie der ersten (unter Windows: Abbruch)."""
        from sales_tool import backup_restore as bkr
        from sales_tool.accounting_api import create_backup
        from sales_tool.model import connect
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'live.sqlite3'
            prepare_database(db)
            name = Path(create_backup(db)['path']).name
            with connect(db) as c:
                c.execute("INSERT INTO leads(company) VALUES ('Nachher GmbH')")
                c.commit()
            first = bkr.restore_named(db, name, confirm=True)
            second = bkr.restore_named(db, Path(first['safety_backup']).name, confirm=True)
            self.assertNotEqual(first['safety_backup'], second['safety_backup'])
            self.assertTrue(Path(first['safety_backup']).exists() and Path(second['safety_backup']).exists())
            with connect(db) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)
            # die erste Sicherheitskopie enthält weiterhin den Stand vor der ersten Wiederherstellung
            with connect(first['safety_backup']) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)


class WorkerShutdownTests(unittest.TestCase):
    def test_stop_workers_ends_polling_and_restart_is_possible(self):
        from sales_tool.research import jobs
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'w.sqlite3')
            prepare_database(db)
            jobs.ensure_workers(db)
            self.assertGreater(jobs.workers_alive(db), 0)
            self.assertTrue(jobs.stop_workers(db, timeout=10))
            self.assertEqual(jobs.workers_alive(db), 0)
            jobs.ensure_workers(db)  # nach dem Beenden wieder startbar
            self.assertGreater(jobs.workers_alive(db), 0)
            self.assertTrue(jobs.stop_workers(db, timeout=10))


if __name__ == '__main__':
    unittest.main()
