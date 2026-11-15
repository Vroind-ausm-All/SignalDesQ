"""2.0.0-dev26: Produktreview M19 – Bestandskunden und Betreuungsleistungen.

Abnahme: Betreuung und neue Projekte sind getrennt.
- Monatliche Positionen eines angenommenen Angebots werden zur Betreuung mit Beginn und optionalem Ende.
- Je Monat genau eine Rechnung mit Leistungszeitraum; außerhalb der Laufzeit, in der Zukunft oder doppelt: abgelehnt.
- „Heute“ zeigt nicht abgerechnete Monate; die Bestandsübersicht trennt Betreuung, Projekte und offene Chancen.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from test_sprintD_pricing import SELLER  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool import care  # noqa: E402
from sales_tool import chances  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

TODAY = dt.date.today()
THIS = TODAY.isoformat()[:7]


def month_back(n):
    y, m = TODAY.year, TODAY.month - n
    while m < 1:
        y, m = y - 1, m + 12
    return f'{y:04d}-{m:02d}'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'c.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        acc.save_settings(self.conn, SELLER)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Betreuung Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lead)
        self.p = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'project_label': 'Website mit Betreuung',
                                           'positions': [{'service': 'webdesign', 'size': 'S'}, {'service': 'pflege', 'size': 'M'}]})
        release_offer(self.conn, self.p['id'])
        of.set_status(self.conn, self.p['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, self.p['id'], {'status': 'angenommen'})
        self.pid = self.p['id']

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def monthly(self, month=None):
        return acc.invoice_from_proposal(self.conn, {'proposal_id': self.pid, 'mode': 'monat', **({'month': month} if month else {})})


class CareTests(Base):
    def test_monthly_billing_once_per_month_within_term(self):
        care.update(self.conn, self.pid, {'start_date': month_back(2) + '-15'})
        ov = care.overview(self.conn)
        [firm] = ov['firms']
        [k] = firm['care']
        self.assertEqual(k['due_months'], [month_back(2), month_back(1), THIS])
        self.assertEqual(len(firm['projects']), 1, 'einmalige Website ist ein Projekt, die Betreuung getrennt')
        inv = self.monthly()
        self.assertEqual(inv['service_from'], month_back(2) + '-01', 'ältester offener Monat zuerst')
        self.assertIn(f'Leistungszeitraum {month_back(2)[5:7]}/{month_back(2)[:4]}', inv['lines'][0]['description'])
        with self.assertRaisesRegex(ValueError, 'bereits eine Monatsrechnung'):
            self.monthly(month_back(2))
        self.monthly(THIS)
        with self.assertRaisesRegex(ValueError, 'Zukunft'):
            self.monthly('2999-01')
        with self.assertRaisesRegex(ValueError, 'beginnt erst'):
            self.monthly(month_back(3))
        self.assertEqual(care.overview(self.conn)['firms'][0]['care'][0]['due_months'], [month_back(1)])
        items = [i for i in td.wiedervorlage(self.conn) if i['kind'] == 'betreuung']
        self.assertEqual(len(items), 1)
        self.assertIn(f'{month_back(1)[5:7]}/{month_back(1)[:4]}', items[0]['title'])
        self.monthly()
        with self.assertRaisesRegex(ValueError, 'bereits abgerechnet'):
            self.monthly()
        self.assertFalse([i for i in td.wiedervorlage(self.conn) if i['kind'] == 'betreuung'])
        # storniert zählt nicht als abgerechnet
        self.conn.execute("UPDATE invoices SET status='storniert' WHERE service_from=?", (THIS + '-01',))
        self.conn.commit()
        self.assertEqual(care.overview(self.conn)['firms'][0]['care'][0]['due_months'], [THIS])

    def test_end_of_care_and_separation_from_new_projects(self):
        care.update(self.conn, self.pid, {'start_date': month_back(1) + '-01'})
        self.monthly(month_back(1))
        with self.assertRaisesRegex(ValueError, 'abgerechnete Monate'):
            care.update(self.conn, self.pid, {'start_date': THIS + '-01'})
        end = (TODAY - dt.timedelta(days=TODAY.day)).isoformat()  # letzter Tag des Vormonats
        k = care.update(self.conn, self.pid, {'end_date': end, 'note': 'Kunde wechselt zu eigener IT'})
        self.assertEqual((k['status'], k['due_months']), ('beendet', []))
        with self.assertRaisesRegex(ValueError, 'endet'):
            self.monthly(THIS)
        self.assertEqual(care.overview(self.conn)['care_count'], 0)
        log = [a['detail'] for a in self.conn.execute("SELECT detail FROM activities WHERE activity_type='projekt'")]
        self.assertTrue(any('endet am' in x and 'eigener IT' in x for x in log))
        # neues Projekt derselben Firma: eigene Chance, nicht Teil der Betreuung
        chances.create(self.conn, self.lead, {'title': 'Online-Shop'})
        [firm] = care.overview(self.conn)['firms']
        self.assertEqual([c['title'] for c in firm['chances']], ['Online-Shop'])
        self.assertEqual(len(firm['care']), 1)

    def test_only_monthly_offers_are_care_and_invoice_without_care(self):
        once = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}]})
        with self.assertRaises(LookupError):
            care.update(self.conn, once['id'], {'end_date': THIS + '-28'})
        inv = acc.invoice_from_proposal(self.conn, {'proposal_id': self.pid, 'mode': 'voll'})
        self.assertEqual(inv['service_from'], '', 'einmalige Rechnung ohne Betreuungszeitraum')
        self.assertEqual(json.loads(self.conn.execute('SELECT customer_json FROM proposals WHERE id=?', (self.pid,)).fetchone()[0])['billing'], 'gemischt')


if __name__ == '__main__':
    unittest.main()
