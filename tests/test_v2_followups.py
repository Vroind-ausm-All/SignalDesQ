"""2.0.0-dev23: Produktreview M16 – Nachfassen mit Anlass, Frist und Ergebnis.

Abnahme: Ein versendetes Angebot hat eine Nachfassaufgabe mit selbst gewählter Frist und Anlass, verknüpft mit Angebot und
Chance. Ein Nachfassen endet mit einem Ergebnis; bleibt die Entscheidung offen, folgt eine neue Frist. Die feste
7-Tage-Wiedervorlage gilt nur noch für ältere Angebote ohne verknüpfte Nachfassaufgabe.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import followups as fu  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_integration import suggest_actions  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

D = lambda n: (dt.date.today() + dt.timedelta(days=n)).isoformat()
POS = [{'service': 'webdesign', 'size': 'M'}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'f.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage, permission) VALUES ('Nachfass Fiktiv GmbH', 'termin', 'opt_in')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lead)
        self.p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': POS, 'tax_mode': 'regel_19'})
        release_offer(self.conn, self.p['id'])

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def send(self, **kw):
        return of.set_status(self.conn, self.p['id'], {'status': 'gesendet_manuell', **kw})

    def open_items(self):
        return fu.for_proposal(self.conn, self.p['id'])['open']


class FollowupTests(Base):
    def test_send_creates_linked_followup_with_chosen_deadline_and_reason(self):
        r = self.send(follow_up=D(3), follow_reason='Entscheidung nach Gesellschafterrunde')
        self.assertEqual(r['follow_up'], D(3))
        [t] = self.open_items()
        self.assertEqual((t['due_date'], t['reason']), (D(3), 'Entscheidung nach Gesellschafterrunde'))
        self.assertIn(self.p['number'], t['title'])
        row = self.conn.execute('SELECT opportunity_id FROM tasks WHERE id=?', (t['id'],)).fetchone()
        self.assertEqual(row['opportunity_id'], self.p['opportunity_id'])
        lead = self.conn.execute('SELECT next_date FROM leads WHERE id=?', (self.lead,)).fetchone()
        self.assertEqual(lead['next_date'], D(3), 'nächster Schritt der Firma folgt der gewählten Frist')

    def test_default_deadline_counts_from_send_date(self):
        self.send(date=D(-5))
        [t] = self.open_items()
        self.assertEqual(t['due_date'], D(2), '7 Tage nach dem Versanddatum, nicht nach heute')
        self.assertEqual(t['reason'], 'Entscheidung erfragen')

    def test_invalid_deadlines(self):
        for bad, msg in ((D(-1), 'Vergangenheit'), (D(200), 'höchstens'), ('morgen', 'JJJJ')):
            with self.assertRaisesRegex(ValueError, msg):
                self.send(follow_up=bad)

    def test_open_decision_needs_next_deadline_and_chain_continues(self):
        self.send(follow_up=D(1))
        [t] = self.open_items()
        with self.assertRaisesRegex(ValueError, 'nächste Frist'):
            fu.record(self.conn, t['id'], {'outcome': 'nicht_erreicht'})
        with self.assertRaisesRegex(ValueError, 'Rückfragen'):
            fu.record(self.conn, t['id'], {'outcome': 'rueckfragen', 'next_date': D(4)})
        r = fu.record(self.conn, t['id'], {'outcome': 'nicht_erreicht', 'note': 'Mailbox', 'next_date': D(4)})
        self.assertEqual([i['due_date'] for i in r['open']], [D(4)])
        self.assertEqual(r['open'][0]['reason'], 'Erneut versuchen')
        done = [i for i in r['items'] if i['done']]
        self.assertEqual((done[0]['outcome_label'], done[0]['outcome_note']), ('Nicht erreicht', 'Mailbox'))
        with self.assertRaisesRegex(ValueError, 'bereits'):
            fu.record(self.conn, t['id'], {'outcome': 'beendet'})
        r = fu.record(self.conn, r['open'][0]['id'], {'outcome': 'rueckfragen', 'note': 'Möchte SEO später', 'next_date': D(2), 'next_reason': 'Fassung mit weniger Umfang besprechen'})
        self.assertIn('überarbeitete Fassung', r['notice'])
        self.assertEqual(r['open'][0]['reason'], 'Fassung mit weniger Umfang besprechen')
        r = fu.record(self.conn, r['open'][0]['id'], {'outcome': 'beendet'})
        self.assertEqual(r['open'], [])
        log = [a['detail'] for a in self.conn.execute("SELECT detail FROM activities WHERE lead_id=? AND detail LIKE '%nachgefasst%'", (self.lead,))]
        self.assertEqual(len(log), 3)
        with self.assertRaisesRegex(ValueError, 'Neue Frist passt nur|neue Frist passt nur'):
            fu.record(self.conn, fu.create(self.conn, self.conn.execute('SELECT * FROM proposals WHERE id=?', (self.p['id'],)).fetchone(),
                                           self.p['number'], dt.date.today(), 'x'), {'outcome': 'absage', 'next_date': D(3)})

    def test_today_shows_task_not_fixed_seven_day_rule(self):
        self.send(follow_up=D(0))
        self.conn.execute("UPDATE proposals SET updated_at=datetime('now','-9 day')")
        self.conn.commit()
        items = td.wiedervorlage(self.conn)
        self.assertEqual([i['kind'] for i in items if self.p['number'] in i['title']], ['aufgabe'])
        self.assertFalse([a for a in suggest_actions(self.conn, self.lead) if a['action_type'] == 'followup'])
        # Älteres Angebot ohne verknüpfte Aufgabe: weiterhin feste 7-Tage-Regel
        self.conn.execute('UPDATE tasks SET proposal_id=NULL')
        self.conn.commit()
        self.assertIn('nachfassen', [i['kind'] for i in td.wiedervorlage(self.conn)])

    def test_revision_and_decision_end_followups_with_outcome(self):
        self.send()
        v2 = make_proposal(self.conn, {'lead_id': self.lead, 'positions': [{'service': 'webdesign', 'size': 'S'}], 'tax_mode': 'regel_19',
                                       'revision_of': self.p['id'], 'revision_reason': 'Umfang reduziert'})
        items = fu.for_proposal(self.conn, self.p['id'])['items']
        self.assertEqual([(i['done'], i['outcome']) for i in items], [(True, 'ersetzt')])
        release_offer(self.conn, v2['id'])
        of.set_status(self.conn, v2['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, v2['id'], {'status': 'abgelehnt'})
        plan = of.start_plan(self.conn, v2['id'])
        self.assertEqual(len(plan['followups']), 1)
        of.start(self.conn, v2['id'], {'close': [plan['followups'][0]['id']]})
        self.assertEqual([i['outcome'] for i in fu.for_proposal(self.conn, v2['id'])['items']], ['entschieden'])


if __name__ == '__main__':
    unittest.main()
