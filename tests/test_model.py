import sqlite3
import tempfile
import unittest
from pathlib import Path
from sales_tool.model import init_db, connect, as_lead, score_lead, stats
from sales_tool.server import validate


class ScoringTests(unittest.TestCase):
    def test_signal_fit_and_evidence_increase_priority(self):
        base = dict(industry='Industrie & B2B-Technik', employees=55, signal_type='kein_signal',
                    offer='conversion', estimated_budget=8000, stage='recherche', permission='unbekannt')
        improved = dict(base, signal_type='produktlaunch', signal_source='https://beispiel.de/neu')
        first, _ = score_lead(base)
        second, reasons = score_lead(improved)
        self.assertGreater(second, first)
        self.assertIn('Signal-Angebots-Passung +8', reasons)

    def test_do_not_contact_has_zero_score(self):
        lead = dict(industry='Industrie & B2B-Technik', employees=100, signal_type='produktlaunch',
                    estimated_budget=30000, offer='conversion', permission='nicht_kontaktieren')
        self.assertEqual(score_lead(lead)[0], 0)
        self.assertEqual(score_lead({**lead, 'permission':'opt_in', 'stage':'gesperrt'})[0],0)

    def test_score_is_bounded(self):
        sample = dict(industry='Industrie & B2B-Technik', employees=90, signal_type='produktlaunch',
                      estimated_budget=50000, offer='conversion', signal_source='https://example.org', permission='opt_in')
        self.assertLessEqual(score_lead(sample)[0], 100)

    def test_validate_rejects_javascript_url(self):
        with self.assertRaises(ValueError):
            validate({'company': 'Test', 'website':'javascript:alert(1)'})

    def test_validate_rejects_negative_budget(self):
        with self.assertRaises(ValueError):
            validate({'company': 'Test', 'estimated_budget': -4})

    def test_validate_requires_name(self):
        with self.assertRaises(ValueError):
            validate({'company': '   '})

    def test_validate_rejects_unsanctioned_fields(self):
        with self.assertRaises(ValueError):
            validate({'company': 'Test', 'sql':'DROP TABLE leads;'})


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'leads.sqlite3'
        with connect(self.db) as con:
            init_db(con)

    def tearDown(self):
        self.tmp.cleanup()

    def test_insert_and_stats(self):
        with connect(self.db) as con:
            con.execute("INSERT INTO leads(company,stage,estimated_budget) VALUES ('Alpha', 'angebot', 10000)")
            con.execute("INSERT INTO leads(company,stage,estimated_budget) VALUES ('Beta', 'gewonnen', 4000)")
            s = stats(con)
            self.assertEqual(s['total'], 2)
            self.assertEqual(s['open_value'], 10000)
            self.assertEqual(s['won_value'], 4000)
            self.assertEqual(s['by_stage']['gewonnen'], 1)

    def test_cascading_deletion(self):
        with connect(self.db) as con:
            ident = con.execute("INSERT INTO leads(company) VALUES ('Alpha')").lastrowid
            con.execute("INSERT INTO activities(lead_id,activity_type) VALUES (?, 'notiz')", (ident,))
            con.execute("INSERT INTO tasks(lead_id,title) VALUES (?, 'Test')", (ident,))
            con.execute("DELETE FROM leads WHERE id=?", (ident,))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM activities').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)

if __name__ == '__main__':
    unittest.main()
