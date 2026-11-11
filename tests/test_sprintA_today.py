"""Sprint A – „Heute“: Tagesplan, Wiedervorlage, offenes Potenzial aus Angeboten, klickbare Pipeline, Funktionsstatus.

Fiktive Daten, keine Netzwerkzugriffe (Ollama-Prüfung wird ersetzt).
"""
import datetime as dt
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.request import urlopen

from sales_tool import today as td
from sales_tool.model import connect, init_db
from sales_tool.sales_workspace import make_proposal
from sales_tool.server import make_handler

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from tmpclean import cleanup_tmp  # noqa: E402 – Worker beenden, dann löschen (Windows)


class TodayBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'td.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, company, **extra):
        data = {'company': company, 'industry': 'Industrie & B2B-Technik', **extra}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid

    def proposal(self, lead_id, status='entwurf', age_days=0, package='pilot'):
        p = make_proposal(self.conn, {'lead_id': lead_id, 'package': package, 'tax_mode': 'regel_19'})
        self.conn.execute("UPDATE proposals SET status=?, updated_at=datetime('now', ?) WHERE id=?", (status, f'-{age_days} day', p['id']))
        self.conn.commit()
        return p


class WiedervorlageTests(TodayBase):
    def test_collects_due_and_started_items(self):
        a = self.lead('Fiktiv Antrieb GmbH', stage='kontakt', next_step='Rückfrage zur Website', next_date=D(-1))
        b = self.lead('Pixelhafen UG', stage='termin')
        blocked = self.lead('Gesperrt AG', stage='gesperrt', next_step='nicht mehr', next_date=D(-3))
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Unterlagen schicken', ?)", (a, D(0)))
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Später', ?)", (a, D(5)))
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date, permission_status) VALUES (?, 'Erstkontakt per E-Mail', ?, 'zu_pruefen')", (a, D(-2)))
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Gesperrt-Aufgabe', ?)", (blocked, D(-1)))
        self.conn.execute("INSERT INTO calls(lead_id, outcome, notes, callback_date) VALUES (?, 'rueckruf_vereinbart', 'Bitte Donnerstag anrufen', ?)", (b, D(0)))
        self.conn.execute("INSERT INTO meetings(lead_id, title, starts_at, location) VALUES (?, 'Bedarfsgespräch', ?, 'Online')", (b, D(1) + 'T10:00'))
        self.conn.execute("INSERT INTO meetings(lead_id, title, starts_at) VALUES (?, 'Später', ?)", (b, D(9) + 'T10:00'))
        self.conn.execute("INSERT INTO discovery(lead_id, problem, impact) VALUES (?, 'Anfragen nur per Telefon', 'Zeitverlust')", (b,))
        self.proposal(a, 'gesendet_manuell', age_days=10)
        self.proposal(b, 'entwurf', age_days=3)
        items = td.wiedervorlage(self.conn)
        kinds = [i['kind'] for i in items]
        for k in ('aufgabe', 'naechster_schritt', 'rueckruf', 'termin', 'bedarfsanalyse', 'nachfassen', 'angebot_entwurf'):
            self.assertIn(k, kinds, k)
        titles = ' '.join(i['title'] for i in items)
        self.assertNotIn('Später', titles)
        self.assertNotIn('Gesperrt', ' '.join(i['company'] for i in items))
        perm = next(i for i in items if i['title'] == 'Erstkontakt per E-Mail')
        self.assertEqual((perm['view'], perm['section'], perm['action']), ('workspace', 'permissions', 'Freigabe prüfen'))
        self.assertEqual(items[0]['kind'], 'termin', 'Termine zuerst')
        self.assertTrue(items[1]['overdue'], 'danach Überfälliges')
        callback = next(i for i in items if i['kind'] == 'rueckruf')
        self.assertEqual((callback['view'], callback['section'], callback['lead_id']), ('workspace', 'contact', b))
        self.conn.execute("INSERT INTO calls(lead_id, outcome) VALUES (?, 'erreicht')", (b,))
        self.assertNotIn('rueckruf', [i['kind'] for i in td.wiedervorlage(self.conn)], 'Rückruf erledigt, sobald ein neueres Gespräch dokumentiert ist')

    def test_callback_suppressed_for_objection(self):
        b = self.lead('Widerspruch GmbH', stage='kontakt', permission='nicht_kontaktieren')
        self.conn.execute("INSERT INTO calls(lead_id, outcome, callback_date) VALUES (?, 'rueckruf_vereinbart', ?)", (b, D(0)))
        self.assertEqual(td.wiedervorlage(self.conn), [])


class PotentialTests(TodayBase):
    def test_potential_from_calculated_offers(self):
        a = self.lead('Angebot GmbH', stage='angebot', estimated_budget=99999)
        b = self.lead('Angenommen GmbH', stage='gewonnen')
        c = self.lead('Nur Schätzung GmbH', stage='kontakt', estimated_budget=8000)
        d = self.lead('Abgelaufen GmbH', stage='angebot')
        pa = self.proposal(a, 'gesendet_manuell')
        pb = self.proposal(b, 'angenommen', package='conversion')
        pd = self.proposal(d, 'entwurf')
        self.conn.execute("UPDATE proposals SET valid_until=? WHERE id=?", (D(-1), pd['id']))
        self.conn.commit()
        pot = td.potential(self.conn)
        self.assertEqual([o['proposal_id'] for o in pot['offers']], [pa['id']])
        self.assertEqual(pot['offers_sum'], pa['customer']['net_eur'])
        self.assertEqual(pot['sent_sum'], pa['customer']['net_eur'])
        self.assertEqual(pot['accepted_sum'], pb['customer']['net_eur'])
        self.assertEqual([e['company'] for e in pot['estimates']], ['Nur Schätzung GmbH'], 'Schätzung nur ohne Angebot')
        self.assertEqual(pot['estimates_sum'], 8000)
        self.assertIn('keine Zusage', pot['notice'])


class PipelineAndPlanTests(TodayBase):
    def test_pipeline_actions(self):
        self.lead('K GmbH', stage='kontakt')
        t = self.lead('T GmbH', stage='termin')
        self.proposal(t, 'entwurf')
        stages = {s['stage']: s for s in td.pipeline(self.conn)}
        self.assertEqual(list(stages), ['recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot', 'gewonnen'])
        self.assertEqual((stages['kontakt']['action_label'], stages['kontakt']['action_view'], stages['kontakt']['action_section']),
                         ('Kontakt aufnehmen', 'workspace', 'contact'))
        self.assertEqual(stages['antwort']['action_label'], 'Termin vereinbaren')
        self.assertIn('Termine vereinbaren', stages['termin']['action_label'])
        self.assertEqual(stages['termin']['action_section'], 'meeting')
        self.assertEqual(stages['kontakt']['count'], 1)
        self.assertGreater(stages['termin']['offer_value'], 0)

    def test_plan_order_and_next_step(self):
        view = td.today_view(self.conn)
        keys = [s['key'] for s in view['plan']['steps']]
        self.assertEqual(keys, ['termine', 'wiedervorlage', 'nachfassen', 'freigaben', 'pruefen', 'finden'])
        self.assertEqual(view['plan']['next_key'], 'finden', 'leerer Tag: neue Firmen finden')
        a = self.lead('Fiktiv GmbH', stage='kontakt', next_step='Anrufen', next_date=D(0))
        view = td.today_view(self.conn)
        self.assertEqual(view['plan']['next_key'], 'wiedervorlage')
        self.conn.execute("INSERT INTO meetings(lead_id, title, starts_at) VALUES (?, 'Gespräch', ?)", (a, D(0) + 'T15:00'))
        self.assertEqual(td.today_view(self.conn)['plan']['next_key'], 'termine')
        self.conn.execute("INSERT INTO discovery_runs(source, params_json, status) VALUES ('ted', '{}', 'done')")
        steps = {s['key']: s for s in td.today_view(self.conn)['plan']['steps']}
        self.assertTrue(steps['finden']['done'], 'heute schon gesucht und nichts zu sichten')

    def test_capabilities_are_honest(self):
        self.conn.execute("INSERT INTO discovery_runs(source, params_json, status, error) VALUES ('gleif', '{}', 'failed', 'Quelle antwortet mit HTTP 400: Bad filter')")
        self.conn.execute("INSERT INTO discovery_runs(source, params_json, status, result_count) VALUES ('ted', '{}', 'done', 12)")
        with mock.patch('sales_tool.ai_lab.ollama_health', return_value={'online': False, 'message': 'Ollama nicht erreichbar.'}):
            caps = {i['key']: i for i in td.capabilities(self.conn)['items']}
        self.assertFalse(caps['ai']['ok'])
        self.assertIn('Regelmodus', caps['ai']['detail'])
        self.assertFalse(caps['src_gleif']['ok'])
        self.assertIn('HTTP 400', caps['src_gleif']['detail'])
        self.assertTrue(caps['src_ted']['ok'])
        self.assertIsNone(caps['src_osm']['ok'], 'noch nicht ausprobiert ≠ kaputt')
        self.assertTrue(caps['crm']['ok'])


class TodayHttpTests(TodayBase):
    def test_endpoints(self):
        self.lead('Fiktiv GmbH', stage='kontakt', next_step='Anrufen', next_date=D(0))
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{server.server_address[1]}'
            with urlopen(base + '/api/today') as r:
                body = json.loads(r.read())
            self.assertEqual(body['wiedervorlage'][0]['title'], 'Anrufen')
            with mock.patch('sales_tool.ai_lab.ollama_health', return_value={'online': False, 'message': 'aus'}):
                with urlopen(base + '/api/system/capabilities') as r:
                    self.assertIn('items', json.loads(r.read()))
            with urlopen(base + '/today.js') as r:
                self.assertEqual(r.status, 200)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
