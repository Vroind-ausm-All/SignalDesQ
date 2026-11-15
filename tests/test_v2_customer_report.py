"""2.0.0-dev30: Produktreview M25 – kundenfähiger Kurzbericht.

Abnahme: nur ausgewählte, geprüfte Befunde; keine internen Kalkulationen. Gesperrte Firmen bekommen keinen Bericht.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import customer_report as cr  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402
from sales_tool.workday import ContactLocked  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'r.sqlite3')
        prepare_database(self.db)
        c = self.conn = connect(self.db)
        self.lead = c.execute("INSERT INTO leads(company, website) VALUES ('Bericht Fiktiv GmbH', 'https://bericht.example')").lastrowid
        a = c.execute("INSERT INTO website_audits(lead_id, url, status, finished_at) VALUES (?, 'https://bericht.example', 'done', '2026-11-10 10:00:00')", (self.lead,)).lastrowid
        vid = c.execute('SELECT id FROM score_versions WHERE active=1').fetchone()[0]
        c.execute("INSERT INTO website_scores(audit_id, lead_id, version_id, design, web, process, coverage, overall, basis_json) VALUES (?,?,?,40,70,60,90,77,'{}')", (a, self.lead, vid))
        ins = """INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, source_url, method, certainty, offer, question, review_status)
                 VALUES (?, ?, ?, ?, ?, 'auffaellig', ?, ?, 'https://bericht.example/', 'dom', 'beobachtet', 'conversion', ?, ?)"""
        self.ok = c.execute(ins, (a, self.lead, 'B3', 'web', 'Sichtbarer Anfrageaufruf', 3, 'Auf der Startseite ist ohne Scrollen kein Anfrageweg sichtbar.',
                                  'Wie erreichen Kunden Sie heute am häufigsten?', 'bestaetigt')).lastrowid
        self.raw = c.execute(ins, (a, self.lead, 'D1', 'design', 'Bildsprache', 2, 'Ungeprüfte Vermutung zur Bildsprache', '', 'ungeprueft')).lastrowid
        run = c.execute("INSERT INTO analysis_runs(lead_id, status) VALUES (?, 'done')", (self.lead,)).lastrowid
        self.rf = c.execute("""INSERT INTO findings(run_id, lead_id, category, observation, hypothesis, evidence, source_url, offer, question, review_status, reviewed_at)
                               VALUES (?, ?, 'Kontakt', 'Kontaktformular mit 9 Pflichtfeldern', 'Interne Hypothese: verliert Anfragen', 'Formular unter /kontakt verlangt 9 Pflichtfelder.',
                               'https://bericht.example/kontakt', 'conversion', 'Welche Angaben brauchen Sie wirklich?', 'freigegeben', '2026-11-11')""", (run, self.lead)).lastrowid
        c.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)


class CustomerReportTests(Base):
    def test_only_reviewed_findings_and_no_internal_values(self):
        cand = cr.candidates(self.conn, self.lead)
        self.assertEqual([i['id'] for i in cand['items']], [f'w{self.ok}', f'r{self.rf}'])
        self.assertEqual(cand['not_selectable'], 1)
        with self.assertRaisesRegex(ValueError, 'Nur geprüfte'):
            cr.build(self.conn, self.lead, {'items': [f'w{self.raw}']})
        with self.assertRaisesRegex(ValueError, 'mindestens'):
            cr.build(self.conn, self.lead, {'items': []})
        r = cr.build(self.conn, self.lead, {'items': [f'w{self.ok}', f'r{self.rf}'], 'intro': 'Wie im Gespräch angekündigt, hier meine Beobachtungen.'})
        md = r['markdown']
        self.assertIn('# Beobachtungen zur Website von Bericht Fiktiv GmbH', md)
        self.assertIn('### 1. Sichtbarer Anfrageaufruf (Technik & Auffindbarkeit)', md)
        self.assertIn('*Fundstelle: https://bericht.example/ · Stand 10.11.2026*', md)
        self.assertIn('**Frage an Sie:** Welche Angaben brauchen Sie wirklich?', md)
        self.assertIn('keine Rechtsberatung', md)
        for internal in ('Interne Hypothese', 'conversion', 'Ungeprüfte Vermutung', 'Priorität', 'Gewicht', '77', 'auffaellig', '€'):
            self.assertNotIn(internal, md)
        row = self.conn.execute('SELECT items_json FROM customer_reports WHERE id=?', (r['id'],)).fetchone()
        self.assertEqual(row['items_json'], f'["w{self.ok}", "r{self.rf}"]', 'gespeichert, was der Kunde sieht')
        other = self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv KG')").lastrowid
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'Nur geprüfte'):
            cr.build(self.conn, other, {'items': [f'w{self.ok}']})

    def test_blocked_firm_gets_no_report(self):
        self.conn.execute("UPDATE leads SET permission='nicht_kontaktieren' WHERE id=?", (self.lead,))
        self.conn.commit()
        with self.assertRaises(ContactLocked):
            cr.build(self.conn, self.lead, {'items': [f'w{self.ok}']})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM customer_reports').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
