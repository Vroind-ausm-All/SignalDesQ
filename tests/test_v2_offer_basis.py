"""2.0.0-dev33: Produktreview M32 – Befund mit Angebot verbinden.

Abnahme: Jede Position zeigt ihre Grundlage (bestätigter Bedarf oder geprüfter Befund); Positionen ohne Grundlage und offene
Hypothesen sind bei der Versandfreigabe sichtbar; ungeprüfte Hypothesen zählen nie als Grundlage; nichts davon im Kundendokument.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import offer_basis as ob  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


class BasisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'b.sqlite3')
        prepare_database(self.db)
        c = self.conn = connect(self.db)
        self.lead = c.execute("INSERT INTO leads(company, stage) VALUES ('Beleg Fiktiv GmbH', 'termin')").lastrowid
        a = c.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'https://g.example', 'done')", (self.lead,)).lastrowid
        ins = """INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, method, certainty, offer, review_status)
                 VALUES (?, ?, ?, 'web', ?, 'auffaellig', 3, ?, 'dom', 'beobachtet', ?, ?)"""
        self.f_ok = c.execute(ins, (a, self.lead, 'B3', 'Kein Anfrageweg sichtbar', 'Startseite ohne Kontaktaufruf', 'conversion', 'bestaetigt')).lastrowid
        self.f_open = c.execute(ins, (a, self.lead, 'D1', 'Uneinheitlicher Auftritt', 'Drei Logovarianten', 'brand', 'ungeprueft')).lastrowid
        c.commit()
        confirm_need(c, self.lead, needs=[{'service': 'pflege', 'size': 'S'}])
        self.p = make_proposal(c, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': [
            {'service': 'pflege', 'size': 'S'}, {'service': 'webdesign', 'size': 'S'}, {'service': 'logo', 'size': 'S'},
            {'service': 'anreise', 'km': 20}, {'service': 'video', 'size': 'S', 'optional': True}]})

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_basis_per_position_and_release_hints(self):
        b = ob.for_proposal(self.conn, self.p['id'])
        kinds = [(i['service'], i['basis']) for i in b['positions']]
        self.assertEqual(kinds, [('pflege', 'bedarf'), ('webdesign', 'befund'), ('logo', 'ohne'), ('anreise', 'begleitend'), ('video', 'ohne')])
        self.assertEqual(b['positions'][1]['evidence'][0]['label'], 'Kein Anfrageweg sichtbar')
        self.assertEqual([h['label'] for h in b['positions'][2]['hypotheses']], ['Uneinheitlicher Auftritt'], 'offene Hypothese sichtbar')
        self.assertEqual([i['service'] for i in b['without']], ['logo'], 'optionale Position ohne Beleg nicht als Lücke gezählt')
        hints = of.checks(self.conn, self.conn.execute('SELECT * FROM proposals WHERE id=?', (self.p['id'],)).fetchone())['hints']
        self.assertTrue(any(h.startswith('Pos. 3 Logogestaltung: weder bestätigter Bedarf') for h in hints), hints)
        self.assertTrue(any('ungeprüfte Hypothese' in h and h.startswith('Pos. 3') for h in hints), hints)
        md = customer_markdown(self.p['customer'])
        for internal in ('Grundlage', 'Hypothese', 'Befund', 'Kein Anfrageweg', 'Uneinheitlich'):
            self.assertNotIn(internal, md)

    def test_hypothesis_becomes_basis_only_after_review(self):
        self.conn.execute("UPDATE website_findings SET review_status='bestaetigt' WHERE id=?", (self.f_open,))
        self.conn.commit()
        b = ob.for_proposal(self.conn, self.p['id'])
        self.assertEqual(b['positions'][2]['basis'], 'befund')
        self.assertEqual(b['without'], [])
        self.conn.execute("UPDATE website_findings SET review_status='verworfen'")
        self.conn.commit()
        b = ob.for_proposal(self.conn, self.p['id'])
        self.assertEqual([i['basis'] for i in b['positions'][:3]], ['bedarf', 'ohne', 'ohne'], 'verworfene Befunde zählen nicht')
        self.assertEqual(b['open_hypotheses'], 0)


if __name__ == '__main__':
    unittest.main()
