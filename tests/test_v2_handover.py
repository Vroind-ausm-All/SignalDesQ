"""2.0.0-dev24: Produktreview M17 – schlanke Auftragsübergabe und Abnahme (Abnahmefall T12).

Abnahme: Aus dem angenommenen Angebot entstehen Liefergegenstände und Abnahmekriterien. Übergabe erst, wenn nichts mehr
offen ist; Abnahme nur für einen übergebenen Stand. Restpunkte und Nachbesserungen werden Aufgaben mit Frist; nach einer
Nachbesserung folgt eine neue Übergabe. Das Protokoll für den Kunden enthält keine internen Zahlen.
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
from sales_tool import handover as ho  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.postcalc import overview  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

D = lambda n: (dt.date.today() + dt.timedelta(days=n)).isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'h.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Abnahme Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lead)
        self.p = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'project_label': 'Neue Website',
                                           'positions': [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 2, 'optional': True}]})
        release_offer(self.conn, self.p['id'])
        of.set_status(self.conn, self.p['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, self.p['id'], {'status': 'angenommen'})
        self.pid = self.p['id']

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def act(self, **kw):
        return ho.act(self.conn, self.pid, kw)

    def finish_deliverables(self, s):
        for i in s['items']:
            if i['kind'] in ('liefer', 'nachbesserung') and i['state'] == 'offen':
                s = self.act(action='item', item_id=i['id'], state='erledigt')
        return s

    def open_tasks(self, kind):
        return [r['title'] for r in self.conn.execute('SELECT title FROM tasks WHERE proposal_id=? AND action_type=? AND done=0', (self.pid, kind))]


class HandoverTests(Base):
    def test_full_path_with_rework_and_rest_points(self):
        s = ho.state(self.conn, self.pid)
        kinds = {i['kind'] for i in s['items']}
        self.assertEqual(kinds, {'liefer', 'kriterium'}, 'aus dem Angebot übernommen')
        self.assertFalse(any('Texte' in i['label'] for i in s['items'] if i['kind'] == 'liefer'), 'optionale Position ist kein Liefergegenstand')
        self.assertEqual(len(ho.state(self.conn, self.pid)['items']), len(s['items']), 'erneutes Öffnen legt nichts doppelt an')
        self.assertFalse(s['can_hand_over'])
        with self.assertRaisesRegex(ValueError, 'offen'):
            self.act(action='uebergabe')
        with self.assertRaisesRegex(ValueError, 'Übergabe dokumentieren'):
            self.act(action='abnahme', result='abgenommen')
        first = next(i for i in s['items'] if i['kind'] == 'liefer')
        with self.assertRaisesRegex(ValueError, 'begründen'):
            self.act(action='item', item_id=first['id'], state='entfaellt')
        self.act(action='item', item_id=first['id'], state='entfaellt', note='auf Kundenwunsch gestrichen')
        self.act(action='add', kind='liefer', label='Einweisung ins Redaktionssystem')
        s = self.finish_deliverables(ho.state(self.conn, self.pid))
        r = self.act(action='uebergabe', date=D(-2), channel='termin', due=D(5))
        self.assertEqual((r['status'], r['handed_at']), ('uebergeben', D(-2)))
        self.assertEqual(self.open_tasks('abnahme'), [f"{self.p['number']}: Abnahme einholen"])
        with self.assertRaisesRegex(ValueError, 'bereits'):
            self.act(action='uebergabe')
        with self.assertRaisesRegex(ValueError, 'vor der Übergabe'):
            self.act(action='abnahme', result='abgenommen', date=D(-3))
        with self.assertRaisesRegex(ValueError, 'einzeln nennen'):
            self.act(action='abnahme', result='nachbesserung')
        r = self.act(action='abnahme', result='nachbesserung', person='Frau Beispiel', points=[{'label': 'Kontaktformular sendet nicht', 'due': D(3)}])
        self.assertEqual((r['status'], r['round']), ('nachbesserung', 2))
        self.assertEqual(self.open_tasks('abnahme'), [])
        self.assertEqual(self.open_tasks('nachbesserung'), [f"{self.p['number']}: Nachbesserung: Kontaktformular sendet nicht"])
        self.assertFalse(r['can_hand_over'], 'Nachbesserung blockiert die erneute Übergabe')
        r = self.finish_deliverables(r)
        self.assertEqual(self.open_tasks('nachbesserung'), [], 'erledigter Punkt beendet seine Aufgabe')
        self.act(action='uebergabe', channel='email')
        r = self.act(action='abnahme', result='vorbehalt', person='Frau Beispiel', channel='email',
                     points=[{'label': 'Impressum um Registernummer ergänzen', 'due': D(7)}])
        self.assertEqual((r['status'], r['result'], r['rest_open']), ('vorbehalt', 'vorbehalt', 1))
        self.assertIn('Schlussrechnung', r['notice'], 'Zahlungsplan „nach Abnahme“')
        crit = next(i for i in r['items'] if i['kind'] == 'kriterium')
        with self.assertRaisesRegex(ValueError, 'abgenommene Stand'):
            self.act(action='item', item_id=crit['id'], state='offen')
        rest = next(i for i in r['items'] if i['kind'] == 'restpunkt')
        r = self.act(action='item', item_id=rest['id'], state='erledigt')
        self.assertEqual(r['status'], 'abgenommen')
        self.assertIn('vollständig abgenommen', r['notice'])
        log = [a['detail'] for a in self.conn.execute("SELECT detail FROM activities WHERE lead_id=? AND activity_type='projekt' ORDER BY id", (self.lead,))]
        self.assertEqual(len(log), 5)
        self.assertIn('Erneute Übergabe', log[2])
        card = next(p for p in overview(self.conn)['projects'] if p['proposal_id'] == self.pid)
        self.assertEqual(card['handover']['status'], 'abgenommen')

    def test_protocol_draft_and_final_without_internal_numbers(self):
        d = ho.protocol(self.conn, self.pid)
        self.assertTrue(d['filename'].endswith('-Entwurf.md'))
        self.assertIn('Entwurf zur Abnahme', d['markdown'])
        self.assertIn('☐ Abgenommen mit folgenden Restpunkten', d['markdown'])
        self.finish_deliverables(ho.state(self.conn, self.pid))
        self.act(action='uebergabe')
        self.act(action='abnahme', result='abgenommen', person='Herr Muster')
        md = ho.protocol(self.conn, self.pid)['markdown']
        self.assertIn('Abgenommen am', md)
        self.assertIn('durch Herr Muster', md)
        self.assertIn('Angebot ' + self.p['number'], md)
        for internal in ('€', 'Stunde', 'hourly', 'Kalkulation'):
            self.assertNotIn(internal, md)

    def test_only_for_accepted_current_offers_and_followups_stay_separate(self):
        other = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'webdesign', 'size': 'S'}]})
        with self.assertRaisesRegex(ValueError, 'angenommenes'):
            ho.state(self.conn, other['id'])
        self.finish_deliverables(ho.state(self.conn, self.pid))
        self.act(action='uebergabe')
        self.assertEqual(len(fu.for_proposal(self.conn, self.pid)['items']), 1, 'Abnahmeaufgabe ist kein Nachfassen')
        plan = of.start_plan(self.conn, self.pid)
        self.assertFalse([f for f in plan['followups'] if 'Abnahme' in f['title']])
        abn = self.conn.execute("SELECT id FROM tasks WHERE action_type='abnahme'").fetchone()['id']
        with self.assertRaises(LookupError):
            fu.record(self.conn, abn, {'outcome': 'beendet'})
        with self.assertRaisesRegex(ValueError, 'Restpunkten'):
            self.act(action='abnahme', result='abgenommen', points=[{'label': 'x'}])


if __name__ == '__main__':
    unittest.main()
