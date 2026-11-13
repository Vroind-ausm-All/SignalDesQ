"""2.0.0-dev19: Produktreview M13 Teil 2 – Bedarf und Freigabe je Chance, Chancen in Pipeline und Heute.

Abnahme:
- Jede weitere Chance hat eine eigene Bedarfsanalyse und eine eigene Freigabe; die erste Chance nutzt die der Firma.
- Ein Angebot prüft bei Versandfreigabe und Statuswechsel den Bedarf seiner Chance – die Freigabe einer anderen Chance genügt nicht.
- „Angebot aus bestätigtem Bedarf“ übernimmt die bestätigten Leistungen der Chance und ordnet das Angebot ihr zu.
- Heute zeigt fällige nächste Schritte offener Chancen, ohne den Schritt der Firma doppelt zu zeigen.
- Pipeline-Daten: alle offenen Chancen nicht gesperrter Firmen mit ihrer Spalte.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import chances as ch  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool import workday as wd  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOGO = [{'service': 'logo', 'size': 'M'}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'n.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Bedarf Fiktiv GmbH', 'kontakt')").lastrowid
        self.conn.commit()
        self.a = ch.create(self.conn, self.lead, {'title': 'Website'})
        self.b = ch.create(self.conn, self.lead, {'title': 'Kundenportal', 'problem': 'Statusanfragen per Telefon'})

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)


class NeedPerChanceTests(Base):
    def test_separate_analysis_and_confirmation(self):
        self.conn.execute("INSERT INTO discovery(lead_id, problem, desired_outcome) VALUES (?, 'Website veraltet', 'Mehr Anfragen')", (self.lead,))
        self.assertEqual(wd.need_status(self.conn, self.lead)['problem'], 'Website veraltet')
        self.assertEqual(wd.need_status(self.conn, self.lead, self.a['id'])['problem'], 'Website veraltet', 'erste Chance = Firma')
        self.assertEqual(wd.need_status(self.conn, self.lead, self.b['id'])['problem'], 'Statusanfragen per Telefon')
        confirm_need(self.conn, self.lead, chance=self.b['id'], needs=[{'service': 'software', 'size': 'M'}])
        self.assertTrue(wd.need_status(self.conn, self.lead, self.b['id'])['confirmed'])
        self.assertFalse(wd.need_status(self.conn, self.lead)['confirmed'], 'Freigabe von B gilt nicht für die Firma/erste Chance')
        view = {c['id']: c for c in ch.list_chances(self.conn, self.lead)['chances']}
        self.assertEqual((view[self.a['id']]['need_confirmed'], view[self.b['id']]['need_confirmed']), (False, True))
        self.assertEqual(view[self.b['id']]['stage'], 'termin', 'bestätigter Bedarf hebt nur diese Chance')
        self.assertEqual(view[self.a['id']]['stage'], 'bedarf')
        act = self.conn.execute("SELECT detail FROM activities WHERE lead_id=? AND activity_type='bedarf' ORDER BY id DESC", (self.lead,)).fetchone()['detail']
        self.assertIn('Kundenportal', act)
        wd.reopen_need(self.conn, self.lead, {'reason': 'Umfang ändert sich', 'opportunity_id': self.b['id']})
        self.assertFalse(wd.need_status(self.conn, self.lead, self.b['id'])['confirmed'])

    def test_offer_checks_the_need_of_its_own_chance(self):
        confirm_need(self.conn, self.lead)  # nur Firma / erste Chance
        pb = make_proposal(self.conn, {'lead_id': self.lead, 'positions': LOGO, 'tax_mode': 'regel_19', 'opportunity_id': self.b['id']})
        st = of.state(self.conn, pb['id'])
        self.assertEqual([c['key'] for c in st['checks'] if not c['ok']], ['bedarf'])
        with self.assertRaisesRegex(ValueError, 'Bedarf'):
            release_offer(self.conn, pb['id'])
        pa = make_proposal(self.conn, {'lead_id': self.lead, 'positions': LOGO, 'tax_mode': 'regel_19', 'opportunity_id': self.a['id']})
        self.assertTrue(release_offer(self.conn, pa['id'])['released'], 'erste Chance nutzt die Freigabe der Firma')
        confirm_need(self.conn, self.lead, chance=self.b['id'])
        self.assertTrue(release_offer(self.conn, pb['id'])['released'])
        of.set_status(self.conn, pb['id'], {'status': 'gesendet_manuell'})
        wd.reopen_need(self.conn, self.lead, {'reason': 'Kunde will neu planen', 'opportunity_id': self.b['id']})
        with self.assertRaisesRegex(Exception, 'Bedarf'):
            of.set_status(self.conn, pb['id'], {'status': 'angenommen'})

    def test_quote_from_need_of_a_chance(self):
        confirm_need(self.conn, self.lead, chance=self.b['id'], needs=[{'service': 'software', 'size': 'M'}, {'service': 'texte', 'qty': 2}])
        with self.assertRaisesRegex(Exception, 'Bedarf'):
            wd.quote_from_need(self.conn, self.lead, {'tax_mode': 'regel_19', 'opportunity_id': self.a['id']})
        p = wd.quote_from_need(self.conn, self.lead, {'tax_mode': 'regel_19', 'opportunity_id': self.b['id']})
        self.assertEqual(p['opportunity_id'], self.b['id'])
        self.assertEqual([x['service'] for x in p['customer']['positions']], ['software', 'texte'])
        self.assertEqual(p['customer']['goal'], 'Selbstauskunft im Portal')
        with self.assertRaisesRegex(ValueError, 'andere'):
            other = self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv KG')").lastrowid
            wd.need_status(self.conn, other, self.b['id'])


class TodayAndPipelineTests(Base):
    def test_due_chance_steps_in_today_without_duplicates(self):
        today = dt.date.today()
        ch.update(self.conn, self.b['id'], {'next_step': 'Prozess aufnehmen', 'next_date': today.isoformat()})
        ch.update(self.conn, self.a['id'], {'next_step': 'Website-Briefing schicken', 'next_date': (today + dt.timedelta(days=3)).isoformat()})
        self.conn.execute("UPDATE leads SET next_step='Prozess aufnehmen', next_date='' WHERE id=?", (self.lead,))
        self.conn.commit()
        items = [i for i in td.wiedervorlage(self.conn) if i['lead_id'] == self.lead]
        self.assertEqual(items, [], 'gleicher Schritt wie bei der Firma wird nicht doppelt gezeigt')
        self.conn.execute("UPDATE leads SET next_step='Rückruf' WHERE id=?", (self.lead,))
        self.conn.commit()
        items = [i for i in td.wiedervorlage(self.conn) if i['lead_id'] == self.lead]
        self.assertEqual([i['title'] for i in items], ['Kundenportal: Prozess aufnehmen'])
        self.assertEqual(items[0]['view'], 'lead')
        ch.update(self.conn, self.b['id'], {'stage': 'verloren', 'lost_reason': 'kein_budget'})
        self.assertEqual([i for i in td.wiedervorlage(self.conn) if i['lead_id'] == self.lead], [])

    def test_open_overview_and_api(self):
        blocked = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Gesperrt Fiktiv', 'kontakt')").lastrowid
        x = ch.create(self.conn, blocked, {'title': 'X'})
        self.conn.execute("UPDATE leads SET stage='gesperrt' WHERE id=?", (blocked,))
        ch.update(self.conn, self.a['id'], {'stage': 'angebot'})
        self.conn.commit()
        rows = ch.open_overview(self.conn)
        self.assertEqual({r['id']: r['lead_stage'] for r in rows}, {self.a['id']: 'angebot', self.b['id']: 'antwort'})
        self.assertNotIn(x['id'], [r['id'] for r in rows])
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def call(method, path, body=None):
                c = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                c.request(method, path, body=json.dumps(body) if body is not None else None,
                          headers={'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{server.server_port}'})
                r = c.getresponse()
                out = (r.status, json.loads(r.read() or b'null'))
                c.close()
                return out
            st, lst = call('GET', '/api/chances')
            self.assertEqual((st, len(lst)), (200, 2))
            st, d = call('GET', f"/api/leads/{self.lead}/discovery?chance={self.b['id']}")
            self.assertEqual((st, d['problem'], d['opportunity_id']), (200, 'Statusanfragen per Telefon', self.b['id']))
            st, d = call('PUT', f"/api/leads/{self.lead}/discovery?chance={self.b['id']}", {'impact': 'Zwei Stunden täglich', 'desired_outcome': 'Selbstauskunft'})
            self.assertEqual((st, d['impact']), (200, 'Zwei Stunden täglich'))
            self.assertFalse(self.conn.execute('SELECT 1 FROM discovery WHERE lead_id=?', (self.lead,)).fetchone(), 'Firma unberührt')
            st, d = call('GET', f"/api/leads/{self.lead}/discovery?chance={self.a['id']}")
            self.assertEqual((st, d.get('opportunity_id')), (200, None), 'erste Chance = Bedarfsanalyse der Firma')
            st, n = call('GET', f"/api/leads/{self.lead}/need?chance={self.b['id']}")
            self.assertEqual((st, n['desired_outcome']), (200, 'Selbstauskunft'))
            st, err = call('GET', f"/api/leads/{blocked}/discovery?chance={self.b['id']}")
            self.assertEqual(st, 400)
        finally:
            server.shutdown()
            server.server_close()


class WiringTests(unittest.TestCase):
    def test_ui_hooks(self):
        pub = ROOT / 'sales_tool' / 'public'
        html = (pub / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="discoveryChance"', html)
        self.assertLess(html.index('id="discoveryChanceWrap"'), html.index('<form id="discoveryForm">'))
        guard = (pub / 'formguard.js').read_text(encoding='utf-8')
        self.assertIn('dialogOpen, rebase,', guard)
        self.assertEqual(guard.count('function rebase('), 1)
        self.assertNotIn('const rebase', guard)  # doppelte Deklaration legte das Skript still (gefunden im Browser-Test)
        js = (pub / 'chances.js').read_text(encoding='utf-8')
        for hook in ("api('/chances')", 'data-ch-confirm', 'data-ch-quote', 'discovery?chance='):
            self.assertIn(hook, js)
        self.assertIn('window.openChances', (pub / 'pipeline.js').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
