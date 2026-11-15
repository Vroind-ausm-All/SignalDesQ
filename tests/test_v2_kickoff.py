"""2.0.0-dev28: Produktreview M38 (Projektkompass und Startstatus) und M39 (Material- und Entscheidungsliste).

Abnahme M38: aus dem bestätigten Angebot vorbelegt; „Vorbereitung“, „wartet auf …“, „bereit“, „gestartet“ je Auftrag;
mehrere Projekte einer Firma unabhängig.
Abnahme M39: Verantwortliche, Termin, fehlender Punkt und Auswirkung sichtbar; Zugänge nie als Klartext-Passwort.
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

from sales_tool import briefing  # noqa: E402
from sales_tool import care  # noqa: E402
from sales_tool import chances  # noqa: E402
from sales_tool import kickoff as ko  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

D = lambda n: (dt.date.today() + dt.timedelta(days=n)).isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'k.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Start Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lead)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def accept(self, positions, **kw):
        p = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': positions, **kw})
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        return p

    def act(self, pid, **kw):
        return ko.act(self.conn, pid, kw)


class KickoffTests(Base):
    def test_prefilled_status_flow_and_waiting_on(self):
        oid = chances.create(self.conn, self.lead, {'title': 'Neues Logo'})['id']
        confirm_need(self.conn, self.lead, chance=oid)
        briefing.save(self.conn, oid, {'areas': ['medien'], 'answers': [{'key': 'inhalte', 'status': 'offen', 'answer': 'Texte liefert Frau Beispiel bis Monatsende'}]})
        p = self.accept([{'service': 'logo', 'size': 'S'}], opportunity_id=oid)
        s = ko.state(self.conn, p['id'])
        labels = [i['label'] for i in s['items']]
        self.assertTrue(labels[0].startswith('Startgespräch'))
        self.assertIn('Inhalte: Texte liefert Frau Beispiel bis Monatsende', labels, 'offener Briefing-Punkt übernommen')
        self.assertIn('Logo, Bilder und Texte für den ersten Arbeitsschritt', labels, 'Vorgabe Mediengestaltung')
        self.assertEqual(s['status'], 'wartet')
        self.assertEqual(s['status_label'], 'wartet auf Kunde')
        self.assertEqual(len(ko.state(self.conn, p['id'])['items']), len(s['items']), 'erneutes Öffnen legt nichts doppelt an')
        mat = next(i for i in s['items'] if i['label'].startswith('Logo, Bilder'))
        s = self.act(p['id'], action='item', item_id=mat['id'], owner_name='Frau Beispiel', due_date=D(3))
        w = next(x for x in s['waiting'] if x['label'].startswith('Logo, Bilder'))
        self.assertEqual((w['owner'], w['due_date'], w['impact']), ('Frau Beispiel', D(3), 'Gestaltung kann nicht beginnen'))
        self.assertIn('Frau Beispiel', s['status_label'])
        with self.assertRaisesRegex(ValueError, 'begründen'):
            self.act(p['id'], action='item', item_id=mat['id'], state='entfaellt')
        for i in s['items']:
            if i['owner'] != 'ich':
                s = self.act(p['id'], action='item', item_id=i['id'], state='erledigt')
        self.assertEqual(s['status'], 'vorbereitung', 'nur noch eigene Punkte offen')
        with self.assertRaisesRegex(ValueError, 'offen'):
            self.act(p['id'], action='start')
        s = self.act(p['id'], action='item', item_id=s['items'][0]['id'], state='erledigt')
        self.assertEqual((s['status'], s['status_label']), ('bereit', 'bereit zum Start'))
        s = self.act(p['id'], action='start', note='Kick-off per Video')
        self.assertEqual(s['status'], 'gestartet')
        with self.assertRaisesRegex(ValueError, 'bereits'):
            self.act(p['id'], action='start')

    def test_no_passwords_and_custom_items(self):
        p = self.accept([{'service': 'webdesign', 'size': 'S'}])
        for bad in ('Passwort: geheim123', 'Login = admin', 'Zugangsdaten: admin/admin', 'Token ghp_abcdefghijklmnop1234'):
            with self.assertRaisesRegex(ValueError, 'keine Passwörter'):
                self.act(p['id'], action='add', kind='zugang', label=bad)
        s = self.act(p['id'], action='add', kind='zugang', label='Hosting-Zugang: Einladung als Nutzer über das Kundenkonto', owner='dritte',
                     owner_name='Hoster des Kunden', due_date=D(-1), impact='Livegang nicht möglich')
        it = s['items'][-1]
        self.assertEqual((it['kind_label'], it['owner_label'], it['overdue']), ('Zugang', 'Dritte', True))
        self.assertIn('Hoster des Kunden', s['status_label'])
        items = [i for i in td.wiedervorlage(self.conn) if i['kind'] == 'start']
        self.assertEqual(len(items), 1)
        self.assertIn('Livegang nicht möglich', items[0]['detail'])
        s = self.act(p['id'], action='start', trotz_offener_punkte=True)
        self.assertEqual(s['status'], 'gestartet')
        self.assertFalse([i for i in td.wiedervorlage(self.conn) if i['kind'] == 'start'], 'nach dem Start keine Starterinnerung mehr')
        log = [a['detail'] for a in self.conn.execute("SELECT detail FROM activities WHERE activity_type='projekt'")]
        self.assertTrue(any('trotz' in x for x in log))

    def test_projects_of_one_firm_are_independent(self):
        a = self.accept([{'service': 'logo', 'size': 'S'}])
        oid = chances.create(self.conn, self.lead, {'title': 'Zweites Projekt'})['id']
        confirm_need(self.conn, self.lead, chance=oid)
        b = self.accept([{'service': 'webdesign', 'size': 'S'}], opportunity_id=oid)
        self.act(a['id'], action='start', trotz_offener_punkte=True)
        self.assertEqual(ko.state(self.conn, a['id'])['status'], 'gestartet')
        self.assertNotEqual(ko.state(self.conn, b['id'])['status'], 'gestartet')
        [firm] = care.overview(self.conn)['firms']
        st = {x['proposal_id']: x['kickoff']['status'] for x in firm['projects']}
        self.assertEqual(st[a['id']], 'gestartet')
        self.assertNotEqual(st[b['id']], 'gestartet')
        draft = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}], 'opportunity_id': 'neu'})
        with self.assertRaisesRegex(ValueError, 'angenommene'):
            ko.state(self.conn, draft['id'])


if __name__ == '__main__':
    unittest.main()
