"""2.0.0-dev3: eigene Erreichbarkeit – Eingang mit Rückruffrist, eigene Zeiten, Terminvorschläge, Auslastung,
Reihenfolge „als Nächstes kontaktieren“.

Abnahme:
- Ein verpasster Anruf ist in einem Schritt festgehalten und hat immer eine Frist an einem eigenen Arbeitstag.
- Terminvorschläge kollidieren nie mit eingetragenen Terminen, Abwesenheiten oder dem Rückruf-Zeitfenster.
- Gesperrte, ausgeschlossene und C-Firmen stehen nie auf der Kontaktliste; die Liste ändert keine Daten.
- Auslastung nennt ihre Grundlage und rechnet nur mit kalkulierten Stunden.
Alle Firmen sind fiktiv; es gibt keine Netzabfragen.
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

from sales_tool import qualification as q  # noqa: E402
from sales_tool import reach  # noqa: E402
from sales_tool.company_data import suppress_lead  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.sales_workspace import create_call  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

FRI = dt.datetime(2026, 11, 13, 10, 0)  # ein Freitag
PROFILE = {**q.default_profile(), 'industries': ['elektro'], 'home': '70173'}

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from tmpclean import cleanup_tmp  # noqa: E402 – Worker beenden, dann löschen (Windows)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / 't.sqlite3'))
        init_db(self.conn)
        q.save(self.conn, dict(PROFILE))

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, company='Elektro Beispiel e.K.', **kw):
        fields = {'company': company, 'employees': 6, 'zip': '70173', 'city': 'Stuttgart', 'stage': 'kontakt', 'business_phone': '0711 000000', **kw}
        cur = self.conn.execute(f"INSERT INTO leads({','.join(fields)}) VALUES ({','.join('?' * len(fields))})", tuple(fields.values()))
        self.conn.commit()
        return cur.lastrowid


class AvailabilityTests(Base):
    def test_defaults_and_validation(self):
        self.assertEqual(reach.load(self.conn), reach.default_availability())
        for bad in ({'days': []}, {'days': [7]}, {'callback_from': '18:00'}, {'meeting_minutes': 5}, {'callback_to': '25:00'},
                    {'absences': [{'from': '2026-12-24', 'to': '2026-12-01'}]}, {'unbekannt': 1}, {'delivery_share_pct': 0}):
            with self.assertRaises(ValueError, msg=bad):
                reach.validate({**reach.default_availability(), **bad})

    def test_callback_due_is_end_of_next_own_window(self):
        av = reach.default_availability()
        self.assertEqual(reach.callback_due(FRI, av), dt.datetime(2026, 11, 13, 17, 30))  # am selben Tag
        self.assertEqual(reach.callback_due(dt.datetime(2026, 11, 13, 17, 20), av), dt.datetime(2026, 11, 16, 17, 30))  # zu knapp → Montag
        self.assertEqual(reach.callback_due(dt.datetime(2026, 11, 14, 11, 0), av), dt.datetime(2026, 11, 16, 17, 30))  # Samstag → Montag
        away = {**av, 'absences': [{'from': '2026-11-13', 'to': '2026-11-17', 'note': 'Urlaub'}]}
        self.assertEqual(reach.callback_due(FRI, reach.validate(away)), dt.datetime(2026, 11, 18, 17, 30))

    def test_meeting_slots_avoid_meetings_absences_and_callback_window(self):
        lid = self.lead()
        self.conn.execute("INSERT INTO meetings(lead_id, title, starts_at, duration_min) VALUES (?, 'Belegt', '2026-11-16T09:00', 60)", (lid,))
        av = reach.validate({**reach.default_availability(), 'meeting_to': '18:00', 'absences': [{'from': '2026-11-17', 'to': '2026-11-17', 'note': ''}]})
        r = reach.meeting_slots(self.conn, av, now=FRI)
        starts = [dt.datetime.strptime(s['starts_at'], reach.FMT) for s in r['slots']]
        self.assertEqual(len(starts), 3)
        self.assertEqual(len({s.date() for s in starts}), 3)  # verschiedene Tage
        for s in starts:
            self.assertLess(s.weekday(), 5)
            self.assertNotEqual(s.date(), dt.date(2026, 11, 17))  # abwesend
            end = s + dt.timedelta(minutes=45)
            self.assertFalse(s.time() < dt.time(17, 30) and end.time() > dt.time(16, 0), s)  # nicht im Rückruf-Fenster
        monday = next(s for s in starts if s.date() == dt.date(2026, 11, 16))
        self.assertGreaterEqual(monday, dt.datetime(2026, 11, 16, 10, 15))  # nach dem belegten Termin samt Puffer
        self.assertIn('Passt einer der Termine?', r['text'])

    def test_templates_use_own_times_and_next_absence(self):
        av = reach.validate({**reach.default_availability(), 'display_name': 'Alex Muster',
                             'absences': [{'from': '2099-12-24', 'to': '2099-12-31', 'note': 'Urlaub'}]})
        t = {x['key']: x['text'] for x in reach.templates(av)}
        self.assertIn('zwischen 16:00 und 17:30 Uhr', t['mailbox'])
        self.assertIn('Alex Muster', t['mailbox'])
        self.assertIn('24.12.', t['abwesenheit'])
        self.assertNotIn('abwesenheit', {x['key'] for x in reach.templates(reach.default_availability())})


class InboundTests(Base):
    def test_capture_without_lead_gets_due_date_and_completes_with_stats(self):
        r = reach.create_inbound(self.conn, {'who': 'Frau Beispiel, Malerbetrieb', 'channel': 'anruf', 'contact': '0711 111111'}, now=FRI)
        self.assertEqual(r['due_at'], '2026-11-13T17:30')
        v = reach.inbound_view(self.conn, now=FRI)
        self.assertEqual((len(v['open']), v['overdue'], v['open'][0]['channel_label']), (1, 0, 'Anruf verpasst'))
        self.assertEqual(reach.inbound_view(self.conn, now=FRI + dt.timedelta(days=1))['overdue'], 1)
        done = reach.complete_inbound(self.conn, r['id'], {'result': 'zurückgerufen, Termin vereinbart'}, now=FRI + dt.timedelta(hours=2))
        self.assertTrue(done['in_time'])
        v = reach.inbound_view(self.conn, now=FRI + dt.timedelta(hours=3))
        self.assertEqual((v['open'], v['stats']['median_hours'], v['stats']['in_time_pct']), ([], 2.0, 100))
        with self.assertRaises(ValueError):
            reach.complete_inbound(self.conn, r['id'], {})

    def test_due_callback_appears_in_todays_follow_ups_until_done(self):
        from sales_tool.today import wiedervorlage
        r = reach.create_inbound(self.conn, {'who': 'Herr Fiktiv', 'channel': 'anruf'}, now=FRI)
        items = [i for i in wiedervorlage(self.conn, today=FRI.date()) if i['title'] == 'Zurückmelden: Herr Fiktiv']
        self.assertEqual([(i['kind'], i['view'], i['anchor'], i['overdue']) for i in items], [('rueckruf', 'today', 'erreichbarkeit', False)])
        self.assertTrue([i for i in wiedervorlage(self.conn, today=FRI.date() + dt.timedelta(days=3)) if i['overdue']])
        reach.complete_inbound(self.conn, r['id'], {}, now=FRI)
        self.assertEqual(wiedervorlage(self.conn, today=FRI.date()), [])

    def test_done_entries_lose_personal_data_after_retention_but_keep_statistics(self):
        r = reach.create_inbound(self.conn, {'who': 'Frau Beispiel', 'channel': 'anruf', 'contact': '0711 111111', 'note': 'privat'}, now=FRI)
        still_open = reach.create_inbound(self.conn, {'who': 'Herr Offen', 'channel': 'anruf'}, now=FRI)
        reach.complete_inbound(self.conn, r['id'], {'result': 'Rückruf erfolgt'}, now=FRI + dt.timedelta(hours=2))
        reach.inbound_view(self.conn, now=FRI + dt.timedelta(days=89))
        self.assertEqual(self.conn.execute('SELECT who FROM inbound WHERE id=?', (r['id'],)).fetchone()[0], 'Frau Beispiel')
        v = reach.inbound_view(self.conn, now=FRI + dt.timedelta(days=91))
        row = self.conn.execute('SELECT who, contact, note, result FROM inbound WHERE id=?', (r['id'],)).fetchone()
        self.assertEqual(tuple(row), ('(gelöscht)', '', '', ''))
        self.assertEqual(v['stats']['median_hours'], 2.0)  # Statistik bleibt
        self.assertEqual([i['who'] for i in v['open']], ['Herr Offen'])  # Offenes wird nie anonymisiert
        del still_open
        with self.assertRaises(ValueError):
            reach.validate({**reach.default_availability(), 'inbound_keep_days': 3})

    def test_validation(self):
        for bad in ({'channel': 'anruf'}, {'who': 'x', 'channel': 'fax'}, {'who': 'x', 'channel': 'anruf', 'lead_id': 999},
                    {'who': 'x', 'channel': 'anruf', 'received_at': '2099-01-01T10:00'}, {'who': 'x', 'channel': 'anruf', 'extra': 1}):
            with self.assertRaises(ValueError, msg=bad):
                reach.create_inbound(self.conn, bad, now=FRI)

    def test_inbound_from_locked_company_is_recorded_with_warning_and_lock_stays(self):
        lid = self.lead(website='https://elektro-beispiel.example')
        suppress_lead(self.conn, lid, 'Widerspruch')
        r = reach.create_inbound(self.conn, {'lead_id': lid, 'channel': 'email'}, now=FRI)
        self.assertIn('Werbung bleibt gesperrt', r['warning'])
        self.assertEqual(reach.inbound_view(self.conn, now=FRI)['open'][0]['who'], 'Elektro Beispiel e.K.')
        self.assertEqual(q.assessment(self.conn, self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone())['fit']['grade'], 'X')

    def test_inbound_survives_lead_deletion(self):
        lid = self.lead()
        reach.create_inbound(self.conn, {'lead_id': lid, 'channel': 'anruf'}, now=FRI)
        self.conn.execute('DELETE FROM leads WHERE id=?', (lid,))
        self.assertEqual(len(reach.inbound_view(self.conn, now=FRI)['open']), 1)


class ContactListTests(Base):
    def test_order_and_exclusions(self):
        a = self.lead('Elektro Alpha e.K.')
        b = self.lead('Zahnarztpraxis Beta GmbH', employees=30, legal_form='GmbH')  # Branche passt nicht → höchstens B
        self.lead('Elektro Recherche GmbH', stage='recherche')  # falsche Phase
        locked = self.lead('Elektro Gesperrt e.K.', website='https://gesperrt.example')
        suppress_lead(self.conn, locked, 'Widerspruch')
        far = self.lead('Kanzlei Fern AG', zip='20095', city='Hamburg', employees=900, legal_form='AG')  # C
        r = reach.contact_list(self.conn, now=FRI)
        names = [i['company'] for i in r['items']]
        self.assertEqual(names[0], 'Elektro Alpha e.K.')
        self.assertNotIn('Elektro Gesperrt e.K.', names)
        self.assertNotIn('Elektro Recherche GmbH', names)
        self.assertNotIn('Kanzlei Fern AG', names)
        self.assertIn('keine Werbeerlaubnis', r['notice'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 0)  # Liste ändert nichts
        del a, b, far

    def test_closed_businesses_move_back_and_unknown_hours_are_not_treated_as_closed(self):
        from sales_tool.research import osm_local
        osm_local.init_osm_local(self.conn)
        run = self.conn.execute("INSERT INTO discovery_runs(source, params_json) VALUES ('osm', '{}')").lastrowid
        hours = {'Elektro Auf e.K.': 'Mo-Fr 08:00-17:00', 'Elektro Zu e.K.': 'Mo-Fr 14:00-18:00', 'Elektro Unklar e.K.': 'nach Vereinbarung'}
        for n, (name, h) in enumerate(hours.items(), 1):
            lid = self.lead(name)
            self.conn.execute("INSERT INTO osm_places(osm_id, name, kind_key, kind, opening_hours, import_id) VALUES (?,?, 'craft', 'electrician', ?, 1)", (f'node/{n}', name, h))
            self.conn.execute("INSERT INTO discovery_candidates(run_id, source, external_id, name, lead_id, sources_json) VALUES (?, 'osm', ?, ?, ?, '[]')", (run, f'node/{n}', name, lid))
        plain = self.lead('Elektro Ohne Angabe e.K.')
        r = reach.contact_list(self.conn, now=FRI)  # Freitag 10 Uhr
        state = {i['company']: i['open_now'] for i in r['items']}
        self.assertEqual(state, {'Elektro Auf e.K.': True, 'Elektro Zu e.K.': False, 'Elektro Unklar e.K.': None, 'Elektro Ohne Angabe e.K.': None})
        self.assertEqual(r['items'][-1]['company'], 'Elektro Zu e.K.')  # geschlossen → ans Ende, aber nicht entfernt
        del plain

    def test_matching_time_slot_comes_first_and_exhausted_company_drops_out(self):
        first = self.lead('Elektro Alpha e.K.')
        second = self.lead('Elektro Beta e.K.')
        create_call(self.conn, {'lead_id': second, 'outcome': 'nicht_erreicht', 'slot': 'nachmittag'})  # nächster Versuch: vormittags
        r = reach.contact_list(self.conn, now=FRI)
        self.assertEqual([(i['company'], i['fits_now']) for i in r['items']], [('Elektro Beta e.K.', True), ('Elektro Alpha e.K.', False)])
        for slot in ('vormittag', 'mittag'):
            create_call(self.conn, {'lead_id': second, 'outcome': 'mailbox', 'slot': slot})
        self.assertEqual([i['company'] for i in reach.contact_list(self.conn, now=FRI)['items']], ['Elektro Alpha e.K.'])
        del first


class CapacityTests(Base):
    def offer(self, lid, status, hours, key='estimated_hours', updated=None):
        self.conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, updated_at) VALUES (?,?,?, '{}', ?)",
                          (lid, status, json.dumps({key: hours}), updated or '2026-11-10 10:00:00'))

    def test_levels_from_calculated_hours(self):
        today = dt.date(2026, 11, 13)
        self.assertEqual(reach.capacity(self.conn, today=today)['level'], 'frei')
        lid = self.lead()
        self.offer(lid, 'angenommen', 42)
        self.offer(lid, 'angenommen', 500, updated='2026-06-01 10:00:00')  # älter als 8 Wochen – zählt nicht mehr
        c = reach.capacity(self.conn, today=today)
        self.assertEqual((c['delivery_hours_per_week'], c['accepted_hours'], c['weeks_accepted'], c['level']), (21.0, 42.0, 2.0, 'luft'))
        self.offer(lid, 'gesendet_manuell', 200, key='hours')  # altes Paketformat
        c = reach.capacity(self.conn, today=today)
        self.assertEqual((c['offered_hours'], c['level']), (200.0, 'voll'))
        self.assertIn('vollen Kalkulation', c['notice'])  # nennt weiter die Grundlage (seit dev5: solange keine Zeiten erfasst sind)
        self.assertEqual(c['untracked_projects'], 1)

    def test_offers_of_lost_leads_do_not_count(self):
        lid = self.lead(stage='verloren')
        self.offer(lid, 'gesendet_manuell', 100)
        self.assertEqual(reach.capacity(self.conn, today=dt.date(2026, 11, 13))['offered_hours'], 0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'api.sqlite3')
        prepare_database(self.db)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        cleanup_tmp(self.tmp)

    def call(self, method, path, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'} if body is not None else {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, json.loads(data) if data else None

    def test_inbound_roundtrip(self):
        st, d = self.call('POST', '/api/inbound', {'who': 'Herr Fiktiv', 'channel': 'mailbox', 'note': 'bittet um Rückruf wegen Website'})
        self.assertEqual(st, 201)
        _, t = self.call('GET', '/api/reach/today')
        self.assertEqual(t['inbound']['open'][0]['who'], 'Herr Fiktiv')
        self.assertEqual(set(t), {'inbound', 'contact_list', 'capacity', 'absent_today', 'callback_window'})
        self.assertEqual(self.call('POST', f"/api/inbound/{d['id']}/done", {'result': 'erledigt'})[0], 200)
        self.assertEqual(self.call('GET', '/api/inbound')[1]['open'], [])
        self.assertEqual(self.call('POST', '/api/inbound', {'who': '', 'channel': 'anruf'})[0], 400)
        _, d2 = self.call('POST', '/api/inbound', {'who': 'Löschen', 'channel': 'anruf'})
        self.assertEqual(self.call('DELETE', f"/api/inbound/{d2['id']}")[0], 200)

    def test_availability_roundtrip(self):
        st, d = self.call('GET', '/api/availability')
        self.assertEqual((st, d['availability']['callback_from'], len(d['weekdays'])), (200, '16:00', 7))
        new = {**d['availability'], 'days': [0, 1, 2, 3], 'callback_from': '11:00', 'callback_to': '12:00', 'display_name': 'Alex Muster'}
        st, d = self.call('POST', '/api/availability', new)
        self.assertEqual(st, 200)
        self.assertIn('zwischen 11:00 und 12:00 Uhr', d['templates'][0]['text'])
        self.assertTrue(all(not s['label'].startswith(('Fr', 'Sa', 'So')) for s in d['slots']['slots']))
        self.assertEqual(self.call('POST', '/api/availability', {**new, 'days': []})[0], 400)


if __name__ == '__main__':
    unittest.main()
