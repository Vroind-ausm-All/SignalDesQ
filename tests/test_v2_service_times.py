"""2.0.0-dev27: Produktreview M20 – Zeiten je Leistung und Lernvorschläge.

Abnahme: Ist-Zeiten lassen sich je Angebotsposition erfassen; die Nachkalkulation zeigt Soll/Ist je Position. Aus
abgeschlossenen Aufträgen entsteht je Leistung eine Aussage – ein Vorschlag erst ab drei Stichproben, mit Spanne.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import postcalc as pc  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

POS = [{'service': 'logo', 'size': 'S'}, {'service': 'texte', 'qty': 2}, {'service': 'grafik', 'size': 'S', 'optional': True}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 't.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.n = 1

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def order(self):
        lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'termin')", (f'Zeiten Fiktiv {self.n} GmbH',)).lastrowid
        self.n += 1
        self.conn.commit()
        confirm_need(self.conn, lead)
        p = make_proposal(self.conn, {'lead_id': lead, 'tax_mode': 'regel_19', 'positions': POS})
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        return p

    def card(self, pid):
        return next(p for p in pc.overview(self.conn)['projects'] if p['proposal_id'] == pid)


class ServiceTimeTests(Base):
    def test_times_per_position(self):
        p = self.order()
        card = self.card(p['id'])
        self.assertEqual([x['n'] for x in card['positions']], [1, 2], 'optionale Position 3 nicht erfassbar')
        est_logo = card['positions'][0]['estimated_hours']
        self.assertGreater(est_logo, 0)
        pc.add_entry(self.conn, {'proposal_id': p['id'], 'hours': est_logo * 1.5, 'position': 1})
        pc.add_entry(self.conn, {'proposal_id': p['id'], 'hours': 1, 'note': 'Abstimmung'})
        for bad in (3, 9, True, '1'):
            with self.assertRaisesRegex(ValueError, 'Position'):
                pc.add_entry(self.conn, {'proposal_id': p['id'], 'hours': 1, 'position': bad})
        card = self.card(p['id'])
        self.assertEqual(card['positions'][0]['variance_pct'], 50)
        self.assertIsNone(card['positions'][1]['variance_pct'])
        self.assertEqual(card['unassigned_hours'], 1)
        self.assertEqual(card['actual_hours'], round(est_logo * 1.5 + 1, 2), 'Gesamtsumme zählt alle Einträge')

    def test_lessons_only_from_three_closed_orders(self):
        ratios = (1.4, 1.2, 1.3)
        for i, r in enumerate(ratios):
            p = self.order()
            est = self.card(p['id'])['positions'][0]['estimated_hours']
            pc.add_entry(self.conn, {'proposal_id': p['id'], 'hours': round(est * r, 2), 'position': 1})
            if i < 2:
                pc.close_project(self.conn, p['id'], {})
                lessons = {x['service']: x for x in pc.overview(self.conn)['service_lessons']}
                self.assertIsNone(lessons['logo']['avg_variance_pct'])
                self.assertIn(f'erst {i + 1}', lessons['logo']['text'])
        self.assertEqual(len(pc.overview(self.conn)['service_lessons']), 1, 'offener Auftrag zählt noch nicht')
        pc.close_project(self.conn, p['id'], {})
        [lesson] = pc.overview(self.conn)['service_lessons']
        self.assertEqual((lesson['samples'], lesson['avg_variance_pct']), (3, 30))
        self.assertIn('30 % mehr Zeit', lesson['text'])
        self.assertIn('Spanne 20 Prozentpunkte', lesson['text'])
        self.assertIn('Leistungen & Preise', lesson['suggestion'])


if __name__ == '__main__':
    unittest.main()
