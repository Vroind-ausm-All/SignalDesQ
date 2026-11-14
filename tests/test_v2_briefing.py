"""2.0.0-dev20: Produktreview M14 – Briefings für Medien und Software.

Abnahme: Das Briefing blendet je Leistungsbereich passende Fragen ein. Jede Angebotsannahme lässt sich auf bestätigte Angaben
oder ausdrücklich offene Voraussetzungen zurückführen.
- Bereiche folgen aus bestätigten Leistungen, Vorlage und Angeboten der Chance; eine eigene Auswahl ist möglich.
- „geklärt“ und „offen“ nur mit Text; „entfällt“ ohne; leer = unbeantwortet.
- Angebot aus bestätigtem Bedarf übernimmt geklärte Angaben als Grundlage und offene Punkte als offene Voraussetzungen;
  neue Angebote speichern intern einen Schnappschuss; die Versandfreigabe weist auf Unbeantwortetes hin.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import briefing as br  # noqa: E402
from sales_tool import chances as ch  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import workday as wd  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'b.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Briefing Fiktiv GmbH', 'kontakt')").lastrowid
        self.conn.commit()
        self.first = ch.create(self.conn, self.lead, {'title': 'Website'})
        self.portal = ch.create(self.conn, self.lead, {'title': 'Kundenportal', 'problem': 'Statusanfragen per Telefon'})

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def answer(self, oid, **kv):
        return br.save(self.conn, oid, {'answers': [{'key': k, 'status': s, 'answer': a} for k, (s, a) in kv.items()]})


class AreaTests(Base):
    def test_questions_follow_the_areas_of_the_chance(self):
        self.assertEqual(br.get(self.conn, self.portal['id'])['areas'], [], 'ohne Leistung noch kein Bereich')
        confirm_need(self.conn, self.lead, chance=self.portal['id'], needs=[{'service': 'software', 'size': 'M'}])
        b = br.get(self.conn, self.portal['id'])
        self.assertEqual([a['key'] for a in b['areas']], ['software'])
        self.assertEqual([i['key'] for i in b['items']], ['kernprozess', 'rollen', 'daten', 'schnittstellen', 'umfang', 'betrieb', 'pruefung'])
        self.assertEqual(b['summary']['unbeantwortet'], 7)
        ch.update(self.conn, self.first['id'], {'offer': 'conversion'})  # Webdesign + Texte + SEO
        self.assertEqual([a['key'] for a in br.get(self.conn, self.first['id'])['areas']], ['medien', 'software', 'sichtbarkeit'])
        b = br.save(self.conn, self.portal['id'], {'areas': ['software', 'beratung']})
        self.assertTrue(b['chosen'])
        self.assertEqual([a['key'] for a in b['areas']], ['beratung', 'software'])
        with self.assertRaises(ValueError):
            br.save(self.conn, self.portal['id'], {'areas': ['raumfahrt']})

    def test_offer_positions_add_areas(self):
        make_proposal(self.conn, {'lead_id': self.lead, 'positions': [{'service': 'logo', 'size': 'S'}], 'opportunity_id': self.portal['id']})
        self.assertIn('medien', [a['key'] for a in br.get(self.conn, self.portal['id'])['areas']])


class AnswerTests(Base):
    def test_status_rules_and_summary(self):
        br.save(self.conn, self.portal['id'], {'areas': ['software']})
        with self.assertRaisesRegex(ValueError, 'Angabe des Kunden'):
            self.answer(self.portal['id'], kernprozess=('geklaert', ''))
        with self.assertRaisesRegex(ValueError, 'was fehlt'):
            self.answer(self.portal['id'], schnittstellen=('offen', ''))
        with self.assertRaisesRegex(ValueError, 'Unbekannte'):
            self.answer(self.portal['id'], raumfahrt=('geklaert', 'x'))
        b = self.answer(self.portal['id'], kernprozess=('geklaert', 'Statusabfrage durch Kunden'), schnittstellen=('offen', 'API-Zugang ERP liefert IT bis 15.12.'),
                        betrieb=('entfaellt', ''))
        self.assertEqual(b['summary'], {'geklaert': 1, 'offen': 1, 'entfaellt': 1, 'unbeantwortet': 4})
        b = self.answer(self.portal['id'], betrieb=('', ''))  # zurück auf unbeantwortet
        self.assertEqual(b['summary']['unbeantwortet'], 5)
        self.assertEqual(br.get(self.conn, self.first['id'])['summary']['geklaert'], 0, 'Briefing gilt je Chance')


class OfferTraceTests(Base):
    def test_offer_assumptions_trace_back_to_briefing(self):
        confirm_need(self.conn, self.lead, chance=self.portal['id'], needs=[{'service': 'software', 'size': 'M'}])
        self.answer(self.portal['id'], kernprozess=('geklaert', 'Statusabfrage durch Kunden'), daten=('geklaert', 'Aufträge aus dem ERP'),
                    schnittstellen=('offen', 'API-Zugang ERP liefert IT bis 15.12.'))
        p = wd.quote_from_need(self.conn, self.lead, {'tax_mode': 'regel_19', 'opportunity_id': self.portal['id']})
        a = p['customer']['assumptions']
        self.assertIn('Grundlage laut Briefing – Kernprozess: Statusabfrage durch Kunden; Daten: Aufträge aus dem ERP.', a)
        self.assertIn('Offene Voraussetzungen, vor Projektstart zu klären – Schnittstellen: API-Zugang ERP liefert IT bis 15.12.', a)
        self.assertIn('Offene Voraussetzungen', customer_markdown(p['customer']))
        snap = json.loads(self.conn.execute('SELECT internal_json FROM proposals WHERE id=?', (p['id'],)).fetchone()['internal_json'])['briefing']
        self.assertEqual({i['key']: i['status'] for i in snap['items']}, {'kernprozess': 'geklaert', 'daten': 'geklaert', 'schnittstellen': 'offen'})
        self.assertNotIn('briefing', p['customer'], 'Schnappschuss nur intern')
        hints = of.state(self.conn, p['id'])['hints']
        self.assertTrue(any('4 Frage(n) noch unbeantwortet' in h for h in hints), hints)
        self.assertFalse(any('offene Voraussetzung' in h for h in hints), 'offene Punkte stehen bereits im Angebot')

    def test_release_hint_when_open_points_missing_in_offer(self):
        br.save(self.conn, self.portal['id'], {'areas': ['medien'], 'answers': [{'key': 'nutzung', 'status': 'offen', 'answer': 'Bildrechte klärt Kunde'}]})
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': [{'service': 'logo', 'size': 'S'}], 'tax_mode': 'regel_19', 'opportunity_id': self.portal['id']})
        hints = of.state(self.conn, p['id'])['hints']
        self.assertTrue(any('1 offene Voraussetzung' in h for h in hints), hints)

    def test_api(self):
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
            st, b = call('PUT', f"/api/chances/{self.portal['id']}/briefing", {'areas': ['software'], 'answers': [{'key': 'rollen', 'status': 'geklaert', 'answer': 'Innendienst und Kunden'}]})
            self.assertEqual((st, b['summary']['geklaert']), (200, 1))
            st, v = call('GET', f"/api/chances/{self.portal['id']}/briefing/voraussetzungen")
            self.assertEqual((st, v['text']), (200, 'Grundlage laut Briefing – Nutzer und Rollen: Innendienst und Kunden.'))
            st, lst = call('GET', f'/api/leads/{self.lead}/chances')
            self.assertEqual(next(c for c in lst['chances'] if c['id'] == self.portal['id'])['briefing']['geklaert'], 1)
            st, _ = call('GET', '/api/chances/9999/briefing')
            self.assertEqual(st, 404)
        finally:
            server.shutdown()
            server.server_close()


class WiringTests(unittest.TestCase):
    def test_ui_and_release(self):
        pub = ROOT / 'sales_tool' / 'public'
        html = (pub / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="qbBriefing"', html)
        js = (pub / 'chances.js').read_text(encoding='utf-8')
        for hook in ('data-ch-brief', '/briefing/voraussetzungen', "'toggle'"):
            self.assertIn(hook, js)
        from tools.build_release import RELEASE_ADDITIONS
        self.assertIn('sales_tool/briefing.py', RELEASE_ADDITIONS)


if __name__ == '__main__':
    unittest.main()
