"""SDQ-010: Tabellenregister und Inventar aller SQL-Zugriffe – Grundlage für Mandantentrennung, Datenschutz und Aufbewahrung.

Die Tests halten das Register vollständig und schützen die Grenzen, die heute im Quelltext gelten: Rechnungs- und Steuerdaten
schreibt nur die Buchhaltung, Anmeldedaten nur die Anmeldung, und jeder SQL-Text ist statisch lesbar."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from sales_tool import data_map, sql_scan  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import catalog  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402
import sql_inventory  # noqa: E402

SRC = ROOT / 'sales_tool'
# Schreibstellen mit zur Laufzeit eingesetztem Tabellennamen – von Hand geprüft, jeweils feste Auswahl an Tabellen:
# bg_jobs: Lauftabellen aus bg_jobs.TABLES; buying_signals: register_events/job_signals (geprüft per Liste);
# quality: Warteschlangen der Website-Prüfung und Schnellprüfung.
REVIEWED_VARIABLE_WRITERS = {'sales_tool/bg_jobs.py', 'sales_tool/buying_signals.py', 'sales_tool/quality.py'}


class RegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.db = Path(cls.tmp.name) / 'r.sqlite3'
        prepare_database(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_table_is_registered(self):
        with connect(self.db) as conn:
            self.assertEqual(data_map.check_register(conn), [])

    def test_catalog_tables_registered(self):
        conn = catalog.connect_catalog(Path(self.tmp.name) / 'k.sqlite3')
        try:
            names = {n for n in data_map.db_tables(conn) if not n.startswith('entities_fts_')}
        finally:
            conn.close()
        self.assertEqual(names, set(data_map.CATALOG_TABLES))

    def test_register_detects_gaps(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE neu_ohne_eintrag (id INTEGER)')
        errs = ' | '.join(data_map.check_register(conn))
        self.assertIn('neu_ohne_eintrag fehlt im Tabellenregister', errs)
        self.assertIn('steht im Register, existiert aber nicht', errs)
        conn = sqlite3.connect(':memory:')
        for t in data_map.TABLES:
            conn.execute(f'CREATE TABLE {t} (id INTEGER)')
        conn.execute('ALTER TABLE calls ADD COLUMN contact_name TEXT')
        self.assertEqual(data_map.check_register(conn),
                         ['Tabelle calls hat Personenspalten (contact_name), ist aber nicht als personenbezogen markiert'])

    def test_register_values(self):
        self.assertIn('invoices', data_map.tables(retention='gobd'))
        self.assertEqual(data_map.tables(scope='zugang'), ['sessions', 'users'])
        self.assertIn('decision_contacts', data_map.tables(personal=True))
        with self.assertRaises(ValueError):
            data_map._parse('x | mandant | A | ja | gobd')


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = sql_scan.inventory(SRC)

    def test_all_sql_statically_readable(self):
        dyn = [f"{r['module']}:{r['line']}" for r in sql_scan.scan(SRC) if r['dynamic']]
        self.assertEqual(dyn, [], 'SQL-Text aus festen Teilen bauen, damit Tabellenzugriffe prüfbar bleiben')

    def test_no_unknown_table_names(self):
        self.assertEqual(self.inv['unknown'], [])

    def test_tax_records_written_only_by_accounting(self):
        allowed = {'sales_tool/accounting.py', 'sales_tool/einvoice.py'}
        for table in data_map.tables(retention='gobd'):
            self.assertLessEqual(set(sql_scan.writers(SRC, table)), allowed, table)

    def test_login_data_written_only_by_auth(self):
        # tenancy.py leert Sitzungen und Passwort-Hashes nur in der Kopie für den Datenexport (export_organization);
        # accounts.py legt bei zentraler Anmeldung Benutzer ohne Passwort an und sperrt sie beim Entzug;
        # multi_server.py beendet Sitzungen ohne Mitgliedschaft und gleicht die Rolle an (SDQ-014/015).
        allowed = {'sales_tool/auth.py', 'sales_tool/server.py', 'sales_tool/tenancy.py', 'sales_tool/accounts.py',
                   'sales_tool/multi_server.py'}
        for table in data_map.tables(scope='zugang'):
            self.assertLessEqual(set(sql_scan.writers(SRC, table)), allowed, table)

    def test_central_accounts_written_only_by_accounts(self):
        for table in ('accounts', 'memberships', 'account_sessions', 'account_mfa', 'account_recovery_codes',
                      'login_failures', 'directory_settings'):
            self.assertEqual(set(sql_scan.writers(SRC, table)), {'sales_tool/accounts.py'}, table)

    def test_audit_trail_append_only(self):
        # SDQ-022: Das Protokoll schreibt nur audit_trail.py – und nur per INSERT (kein UPDATE, kein DELETE).
        self.assertEqual(set(sql_scan.writers(SRC, 'audit_events')), {'sales_tool/audit_trail.py'})
        src = (SRC / 'audit_trail.py').read_text(encoding='utf-8')
        self.assertNotRegex(src, r'(?i)(UPDATE|DELETE FROM)\s+audit_events')

    def test_variable_write_targets_reviewed(self):
        self.assertEqual(set(sql_scan.writers(SRC, sql_scan.VARIABLE)), REVIEWED_VARIABLE_WRITERS)

    def test_scanner_reads_assembled_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'pkg'
            src.mkdir()
            (src / 'm.py').write_text(
                "Q = 'SELECT * FROM leads'\n"
                "def a(conn, t, lid):\n"
                "    sql = 'UPDATE invoices SET status=?'\n"
                "    sql += ' WHERE id=?'\n"
                "    conn.execute(sql, ('x', 1))\n"
                "    conn.execute(Q)\n"
                "    conn.execute(f'DELETE FROM {t} WHERE id=?', (lid,))\n"
                "    run = lambda q: conn.execute(q).fetchall()\n"
                "    run('SELECT id FROM payments')\n"
                "    conn.execute(make_sql())\n", encoding='utf-8')
            rows = {r['line']: r for r in sql_scan.scan(src)}
        self.assertEqual(rows[5]['writes'], ['invoices'])
        self.assertEqual(rows[6]['tables'], ['leads'])
        self.assertEqual(rows[7]['writes'], [sql_scan.VARIABLE])
        self.assertEqual(rows[8]['kind'], 'durchgereicht')
        self.assertEqual((rows[9]['kind'], rows[9]['tables']), ('indirekt', ['payments']))
        self.assertTrue(rows[10]['dynamic'])

    def test_inventory_document_current(self):
        doc = (ROOT / 'docs' / 'DATENZUGRIFF.md').read_text(encoding='utf-8')
        self.assertEqual(doc, sql_inventory.markdown(self.inv),
                         'docs/DATENZUGRIFF.md neu erzeugen: python tools/sql_inventory.py --md docs/DATENZUGRIFF.md')


if __name__ == '__main__':
    unittest.main()
