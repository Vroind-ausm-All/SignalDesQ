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


if __name__ == '__main__':
    unittest.main()
