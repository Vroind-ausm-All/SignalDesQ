"""2.0.0-dev15: Produktreview M08, M09, M11 – Fokusliste, geführter Einstieg, Arbeitsansichten der Firmenliste.

Abnahme:
- M08: Höchstens drei nächste Aktionen mit Grund und Frist. Überfällige Zusagen vor Terminen vor heute Zugesagtem vor Nachfassen;
  neue Akquise erst, wenn nichts Zugesagtes mehr Platz braucht. Eine Rückrufzusage wird nie von einer Passungsnote verdrängt.
- M11: Der Einstieg prüft echte Daten (Preise gespeichert, Zielkunden mit Region und Branche, Zeiten, erste Firma oder Anfrage)
  und lässt sich ausblenden. Ein Recherchelauf ist dafür nicht nötig.
- M09: Eigene Ansichten speichern nur Filter (Name, Arbeitsansicht, Phase, Suche) und werden geprüft; die Firmenliste
  bekommt den letzten dokumentierten Kontakt.
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
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import focus, qualification, reach  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

TODAY = dt.date(2026, 11, 13)
PUBLIC = Path(__file__).resolve().parent.parent / 'sales_tool' / 'public'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'f.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, company, stage='kontakt', **kw):
        cols = ['company', 'stage'] + list(kw)
        cur = self.conn.execute(f"INSERT INTO leads({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", [company, stage, *kw.values()])
        self.conn.commit()
        return cur.lastrowid

    def day(self, n):
        return (TODAY + dt.timedelta(days=n)).isoformat()


class FocusTests(Base):
    def test_order_promises_before_meetings_before_follow_up(self):
        a = self.lead('Nachfass Fiktiv GmbH', 'angebot')
        self.conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, number, updated_at) VALUES (?, 'gesendet_manuell', '{}', '{}', 'AN-1', ?)",
                          (a, self.day(-10) + ' 09:00:00'))
        b = self.lead('Termin Fiktiv KG', 'termin')
        self.conn.execute("INSERT INTO meetings(lead_id, title, starts_at, status, location) VALUES (?, 'Erstgespräch', ?, 'geplant', 'vor Ort')", (b, self.day(1) + 'T09:00'))
        self.lead('Zusage Fiktiv e.K.', 'kontakt', next_step='Unterlagen schicken', next_date=self.day(-2))
        self.lead('Heute Fiktiv OHG', 'antwort', next_step='Rückruf bestätigen', next_date=self.day(0))
        self.conn.commit()
        f = focus.focus(self.conn, TODAY)
        self.assertEqual([i['company'] for i in f['items']], ['Zusage Fiktiv e.K.', 'Termin Fiktiv KG', 'Heute Fiktiv OHG'])
        self.assertEqual(f['items'][0]['why'], 'seit 2 Tagen überfällig')
        self.assertTrue(f['items'][1]['why'].startswith('Termin morgen'))
        self.assertEqual(f['items'][2]['why'], 'heute fällig')
        self.assertEqual(f['more'], 1)  # das Angebot zum Nachfassen steht in der Wiedervorlage
        self.assertEqual(f['items'][0]['action']['view'], 'lead')
        self.assertTrue(all(i['action']['label'] for i in f['items']))

    def test_callback_promise_beats_best_fit_acquisition(self):
        qualification.save(self.conn, {**qualification.default_profile(), 'industries': ['elektro'], 'home': '70173'})
        self.lead('Elektro Fiktiv e.K.', 'kontakt', employees=6, legal_form='e.K.', business_phone='0711 000000', zip='70173', city='Stuttgart')
        cust = self.lead('Kanzlei Fern AG', 'kontakt', zip='20095', city='Hamburg')
        self.conn.execute("INSERT INTO calls(lead_id, outcome, callback_date, notes) VALUES (?, 'rueckruf_vereinbart', ?, 'Freitag zurückrufen')", (cust, self.day(0)))
        self.conn.commit()
        f = focus.focus(self.conn, TODAY, now=dt.datetime(2026, 11, 13, 10, 0))
        self.assertEqual(f['items'][0]['company'], 'Kanzlei Fern AG')
        self.assertIn('heute zugesagt', f['items'][0]['why'])
        acq = [i for i in f['items'] if i['bucket'] == 'akquise']
        self.assertEqual([i['company'] for i in acq], ['Elektro Fiktiv e.K.'])  # erst danach, mit Passung als Grund
        self.assertTrue(acq[0]['why'].startswith('Passung A'))

    def test_empty_day_points_to_next_step_not_to_success(self):
        f = focus.focus(self.conn, TODAY)
        self.assertEqual(f['items'], [])
        self.assertEqual(f['empty_next']['view'], 'finder')


class OnboardingTests(Base):
    def test_steps_follow_real_data_and_can_be_hidden(self):
        o = focus.onboarding(self.conn)
        self.assertEqual((o['done'], o['total'], o['show']), (0, 4, True))
        from sales_tool import pricing
        pricing.save_pricing_settings(self.conn, {**pricing.pricing_settings(self.conn), 'hourly_rate': 95})
        qualification.save(self.conn, {**qualification.default_profile(), 'industries': [], 'home': '70173'})
        self.assertFalse(next(s for s in focus.onboarding(self.conn)['steps'] if s['key'] == 'zielkunden')['done'])  # ohne Branchen nicht fertig
        qualification.save(self.conn, {**qualification.default_profile(), 'industries': ['elektro'], 'home': '70173'})
        reach.save(self.conn, reach.load(self.conn))
        self.conn.commit()
        o = focus.onboarding(self.conn)
        self.assertEqual({s['key']: s['done'] for s in o['steps']}, {'preise': True, 'zielkunden': True, 'zeiten': True, 'erste_firma': False})
        self.assertEqual(next(s for s in o['steps'] if s['key'] == 'erste_firma')['action']['view'], 'new_lead')
        self.lead('Erste Fiktiv GmbH', 'recherche')
        o = focus.onboarding(self.conn)
        self.assertEqual((o['done'], o['show']), (4, False))  # alles eingerichtet: verschwindet von selbst

    def test_dismiss_and_validation(self):
        self.assertFalse(focus.set_onboarding(self.conn, {'dismissed': True})['show'])
        self.assertTrue(focus.set_onboarding(self.conn, {'dismissed': False})['show'])
        for bad in ({}, {'dismissed': 'ja'}, ['x']):
            with self.assertRaises(ValueError):
                focus.set_onboarding(self.conn, bad)


class LeadViewTests(Base):
    def test_save_and_validate_views(self):
        views = focus.save_lead_views(self.conn, {'views': [{'name': '  Heute   fällig ', 'preset': 'heute'},
                                                            {'name': 'Kanzleien', 'preset': 'alle', 'stage': 'kontakt', 'q': 'kanzlei'}]})
        self.assertEqual(views[0], {'name': 'Heute fällig', 'preset': 'heute', 'stage': '', 'q': ''})
        self.assertEqual(focus.lead_views(self.conn)[1]['stage'], 'kontakt')
        for bad in ({'views': [{'name': '', 'preset': 'alle'}]}, {'views': [{'name': 'x' * 41}]}, {'views': [{'name': 'A'}, {'name': 'a'}]},
                    {'views': [{'name': 'X', 'preset': 'erfunden'}]}, {'views': [{'name': 'X', 'stage': 'nirgends'}]},
                    {'views': [{'name': str(i)} for i in range(13)]}, {'views': 'x'}):
            with self.assertRaises(ValueError):
                focus.save_lead_views(self.conn, bad)
        self.assertEqual(len(focus.lead_views(self.conn)), 2)  # Fehlversuche ändern nichts

    def test_last_contact_from_talks_calls_and_meetings(self):
        a = self.lead('Kontakt Fiktiv GmbH')
        b = self.lead('Nur Notiz Fiktiv KG')
        self.conn.execute("INSERT INTO activities(lead_id, activity_type, detail, created_at) VALUES (?, 'gespraech', 'Telefonat', '2026-11-02 10:00:00')", (a,))
        self.conn.execute("INSERT INTO calls(lead_id, outcome, created_at) VALUES (?, 'erreicht', '2026-11-09 08:00:00')", (a,))
        self.conn.execute("INSERT INTO activities(lead_id, activity_type, detail, created_at) VALUES (?, 'notiz', 'interne Notiz', '2026-11-10 10:00:00')", (b,))
        self.conn.commit()
        last = focus.last_contacts(self.conn)
        self.assertEqual(last.get(a), '2026-11-09')
        self.assertNotIn(b, last)  # eine interne Notiz ist kein Kontakt


class HttpTests(Base):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, method, path, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'} if body is not None else {})
        r = c.getresponse()
        data = r.read()
        ctype = r.getheader('Content-Type', '')
        c.close()
        return r.status, (json.loads(data) if data and 'json' in ctype else data)

    def test_endpoints(self):
        st, d = self.call('GET', '/api/focus')
        self.assertEqual((st, d['focus']['items'], d['onboarding']['total']), (200, [], 4))
        self.assertFalse(self.call('PUT', '/api/onboarding', {'dismissed': True})[1]['show'])
        self.assertFalse(self.call('GET', '/api/focus')[1]['onboarding']['show'])  # vor der Antwort gespeichert
        self.assertEqual(self.call('PUT', '/api/onboarding', {'dismissed': 'ja'})[0], 400)
        st, d = self.call('PUT', '/api/lead-views', {'views': [{'name': 'Heute fällig', 'preset': 'heute'}]})
        self.assertEqual((st, d['views'][0]['preset']), (200, 'heute'))
        self.assertEqual(self.call('GET', '/api/lead-views')[1]['views'][0]['name'], 'Heute fällig')
        self.assertEqual(self.call('PUT', '/api/lead-views', {'views': [{'name': 'X', 'preset': 'nein'}]})[0], 400)
        self.lead('Liste Fiktiv GmbH')
        st, rows = self.call('GET', '/api/leads')
        self.assertEqual((st, rows[0]['last_contact']), (200, ''))
        st, body = self.call('GET', '/leadlist.js')
        self.assertEqual(st, 200)
        self.assertIn(b'window.renderLeads', body)


class FrontendTests(unittest.TestCase):
    def test_markup_and_hooks(self):
        html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
        for needle in ('id="tdFocus"', 'id="tdOnboarding"', 'id="tdOnbHide"', '<details class="panel td-plan" id="tdPlanBox">',
                       '<details class="panel td-close" id="tagesabschluss">', 'id="leadViews"', 'id="leadFilterInfo"', 'id="leadHead"',
                       'data-ll-col="signal"', 'data-ll-col="offer"', '<script src="/leadlist.js" defer></script>'):
            self.assertIn(needle, html)
        self.assertLess(html.index('id="tdFocus"'), html.index('id="erreichbarkeit"'))  # Fokus steht oben
        self.assertLess(html.index('<script src="/leadlist.js"'), html.index('<script src="/nav.js"'))
        ll = (PUBLIC / 'leadlist.js').read_text(encoding='utf-8')
        for preset in focus.PRESETS:
            self.assertIn(f"key: '{preset}'", ll)
        self.assertIn('Noch keine Firmen.', ll)
        self.assertIn('Keine Firma passt zu diesen Filtern.', ll)
        nav = (PUBLIC / 'nav.js').read_text(encoding='utf-8')
        self.assertIn("p.set('ansicht', window.leadList.preset)", nav)
        today = (PUBLIC / 'today.js').read_text(encoding='utf-8')
        self.assertIn("if (a.view === 'new_lead') return showModal();", today)
        self.assertNotIn("'Alles erledigt – neue Firmen finden →'", today)


if __name__ == '__main__':
    unittest.main()
