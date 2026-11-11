"""2.0.0-dev2: Zielkundenprofil, Passung vor / Qualifizierung nach dem Gespräch, Erreichbarkeit, Verlustgrund.

Abnahme:
- Unbekanntes bleibt unbekannt und senkt die Note nicht; bei zu dünner Datenlage gibt es keine Note.
- K.-o.-Kriterien (Sperre, Auflösung, Ausschlussbranche, kein Budget) schlagen jede Punktzahl.
- „Nicht erreicht“ und „Mailbox“ enden nie ohne nächsten Schritt; nach der Höchstzahl an Versuchen folgt ein Kanalwechsel.
- „Verloren“ gibt es nur mit Grund. Bestehende Datenbanken werden schonend erweitert.
Alle Firmen sind fiktiv; es gibt keine Netzabfragen.
"""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need  # noqa: E402

from sales_tool import qualification as q  # noqa: E402
from sales_tool import workday  # noqa: E402
from sales_tool.company_data import suppress_lead  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.sales_workspace import create_call  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, make_handler, prepare_database  # noqa: E402

PROFILE = {'name': 'Handwerk Stuttgart', 'industries': ['elektro', 'shk'], 'excluded_industries': ['bau'], 'employees_min': 1, 'employees_max': 30,
           'home': '70173', 'radius_km': 30, 'min_order_eur': 1500, 'weekly_hours': 30, 'prefer_owner_led': True,
           'max_attempts': 3, 'retry_days': 2, 'park_days': 90}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 't.sqlite3')
        self.conn = connect(self.db)
        init_db(self.conn)
        q.save(self.conn, dict(PROFILE))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, company='Elektro Beispiel e.K.', **kw):
        fields = {'company': company, **kw}
        cur = self.conn.execute(f"INSERT INTO leads({','.join(fields)}) VALUES ({','.join('?' * len(fields))})", tuple(fields.values()))
        self.conn.commit()
        return cur.lastrowid

    def row(self, lid):
        return self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()

    def crit(self, result, key):
        return next(c for c in result['criteria'] if c['key'] == key)


class ProfileTests(Base):
    def test_default_profile_is_valid_and_loads_without_settings(self):
        self.conn.execute('DELETE FROM app_settings')
        self.assertEqual(q.load(self.conn), q.default_profile())

    def test_rejects_bad_values(self):
        for bad in ({'industries': ['gibtsnicht']}, {'employees_min': 60, 'employees_max': 50}, {'radius_km': 0}, {'unbekannt': 1},
                    {'industries': ['bau'], 'excluded_industries': ['bau']}, {'home': 'Nirgendwo-Xyz'}, {'max_attempts': True}):
            with self.assertRaises(ValueError, msg=bad):
                q.validate({**PROFILE, **bad})

    def test_broken_stored_profile_falls_back_to_default(self):
        self.conn.execute("UPDATE app_settings SET value_json='{\"radius_km\": \"weit\"}' WHERE key=?", (q.KEY,))
        self.assertEqual(q.load(self.conn)['radius_km'], 30)


class FitTests(Base):
    def test_craft_business_in_target_gets_grade_a(self):
        lid = self.lead(employees=8, zip='70173', city='Stuttgart', legal_form='e.K.')
        f = q.fit(self.conn, self.row(lid))
        self.assertEqual(f['grade'], 'A')
        self.assertEqual(self.crit(f, 'branche')['status'], 'passt')
        self.assertEqual(self.crit(f, 'region')['status'], 'passt')
        self.assertEqual(self.crit(f, 'entscheidungsweg')['status'], 'passt')
        # das alte Agentur-Raster hätte diese Firma als „Sonstige“ kaum bewertet
        self.assertNotIn('Kaufwahrscheinlichkeit', f['verdict'])

    def test_unknown_is_not_bad(self):
        """Fehlende Angaben senken die Punktzahl nicht – sie senken nur die Abdeckung."""
        full = q.fit(self.conn, self.row(self.lead(employees=8, zip='70173', city='Stuttgart', legal_form='e.K.')))
        sparse = q.fit(self.conn, self.row(self.lead('Elektro Knapp e.K.', zip='70173', city='Stuttgart')))
        self.assertEqual(self.crit(sparse, 'groesse')['status'], 'unbekannt')
        self.assertEqual(sparse['score'], full['score'])
        self.assertLess(sparse['coverage_pct'], full['coverage_pct'])
        self.assertIn('Unternehmensgröße', sparse['missing'])

    def test_no_grade_when_data_is_thin(self):
        f = q.fit(self.conn, self.row(self.lead('Müller GmbH')))
        self.assertIsNone(f['grade'])
        self.assertIn('Datenlage unzureichend', f['verdict'])

    def test_empty_profile_does_not_judge_industry(self):
        q.save(self.conn, {**PROFILE, 'industries': [], 'excluded_industries': []})
        f = q.fit(self.conn, self.row(self.lead(employees=8, zip='70173', city='Stuttgart')))
        self.assertEqual(self.crit(f, 'branche')['status'], 'unbekannt')
        self.assertEqual(self.crit(f, 'branche')['action']['view'], 'quality')

    def test_far_away_and_wrong_industry_is_c_with_warning(self):
        lid = self.lead('Zahnarztpraxis Nord GmbH', employees=400, zip='20095', city='Hamburg', legal_form='GmbH')
        f = q.fit(self.conn, self.row(lid))
        self.assertEqual(f['grade'], 'C')
        self.assertTrue(any('Außerhalb' in w for w in f['warnings']))

    def test_knockouts_beat_any_score(self):
        lid = self.lead(employees=8, zip='70173', city='Stuttgart', legal_form='e.K.')
        self.conn.execute("""INSERT INTO register_events(dedupe_key, lead_id, company, event_type, published_at, text)
                             VALUES ('k1', ?, 'Elektro Beispiel e.K.', 'aufloesung', '2026-10-01', 'Die Firma ist erloschen.')""", (lid,))
        f = q.fit(self.conn, self.row(lid))
        self.assertEqual(f['grade'], 'X')
        self.assertEqual(f['knockouts'][0]['key'], 'aufloesung')
        excluded = q.fit(self.conn, self.row(self.lead('Hochbau Stein GmbH', employees=10, zip='70173', city='Stuttgart')))
        self.assertEqual((excluded['grade'], excluded['knockouts'][0]['key']), ('X', 'branche'))

    def test_suppressed_company_is_excluded(self):
        lid = self.lead(employees=8, zip='70173', city='Stuttgart', website='https://elektro-beispiel.example')
        suppress_lead(self.conn, lid, 'Widerspruch per Brief')
        a = q.assessment(self.conn, self.row(lid))
        self.assertEqual(a['fit']['grade'], 'X')
        self.assertEqual(a['headline'], 'Nicht weiterverfolgen')
        self.assertEqual(a['reachability']['status'], 'gesperrt')
        self.assertIsNone(a['reachability']['next_slot'])

    def test_fit_does_not_change_data(self):
        lid = self.lead(employees=8, zip='70173', city='Stuttgart')
        before = dict(self.row(lid))
        q.assessment(self.conn, self.row(lid))
        self.assertEqual(dict(self.row(lid)), before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 0)


class QualificationTests(Base):
    def test_no_talk_means_open_not_bad(self):
        r = q.qualification(self.conn, self.row(self.lead()))
        self.assertEqual((r['status'], r['criteria']), ('offen', []))

    def test_missed_calls_are_not_talks(self):
        lid = self.lead()
        create_call(self.conn, {'lead_id': lid, 'outcome': 'mailbox'})
        self.assertEqual(q.qualification(self.conn, self.row(lid))['status'], 'offen')

    def test_partial_then_qualified(self):
        lid = self.lead()
        create_call(self.conn, {'lead_id': lid, 'outcome': 'erreicht', 'notes': 'Website bringt keine Anfragen'})
        r = q.qualification(self.conn, self.row(lid))
        self.assertEqual(r['status'], 'teilweise')
        self.assertGreaterEqual(len(r['questions']), 3)
        confirm_need(self.conn, lid)
        self.conn.execute("UPDATE discovery SET budget_status='budget_vorhanden', timing='bis März', decision_process='Inhaber entscheidet allein' WHERE lead_id=?", (lid,))
        r = q.qualification(self.conn, self.row(lid))
        self.assertEqual(r['status'], 'qualifiziert')
        self.assertEqual(q.assessment(self.conn, self.row(lid))['headline'], 'Qualifiziert – Angebot vorbereiten')

    def test_no_budget_is_knockout(self):
        lid = self.lead()
        confirm_need(self.conn, lid)
        self.conn.execute("UPDATE discovery SET budget_status='kein_budget' WHERE lead_id=?", (lid,))
        r = q.qualification(self.conn, self.row(lid))
        self.assertEqual((r['status'], r['knockouts'][0]['key']), ('nicht_qualifiziert', 'budget'))

    def test_order_value_below_minimum_blocks_qualified(self):
        lid = self.lead()
        confirm_need(self.conn, lid)
        self.conn.execute("UPDATE discovery SET budget_status='budget_vorhanden', timing='sofort', decision_process='Inhaber' WHERE lead_id=?", (lid,))
        self.conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, number) VALUES (?, 'entwurf', '{}', ?, 'AN-2026-0001')",
                          (lid, json.dumps({'net_eur': 600})))
        r = q.qualification(self.conn, self.row(lid))
        self.assertEqual(self.crit(r, 'auftragswert')['status'], 'passt_nicht')
        self.assertEqual(r['status'], 'teilweise')


class ReachabilityTests(Base):
    def call(self, lid, outcome, slot):
        return create_call(self.conn, {'lead_id': lid, 'outcome': outcome, 'slot': slot})

    def open_tasks(self, lid):
        return [r['title'] for r in self.conn.execute('SELECT title FROM tasks WHERE lead_id=? AND done=0 ORDER BY id', (lid,))]

    def test_missed_call_creates_retry_at_other_time_on_a_workday(self):
        lid = self.lead(stage='kontakt', business_phone='0711 000000')
        r = self.call(lid, 'nicht_erreicht', 'vormittag')
        self.assertEqual(r['follow_up']['slot'], 'nachmittag')
        self.assertLess(dt.date.fromisoformat(r['follow_up']['due']).weekday(), 5)
        self.assertEqual(self.open_tasks(lid), ['Erneut anrufen (2. Versuch) – diesmal nachmittags (14–17 Uhr)'])
        lead = self.row(lid)
        self.assertTrue(lead['next_step'].startswith('Erneut anrufen') and lead['next_date'])
        self.assertEqual(workday.dead_ends(self.conn), [])  # keine Sackgasse

    def test_after_max_attempts_switch_channel_instead_of_endless_loop(self):
        lid = self.lead(stage='kontakt', business_phone='0711 000000', street='Musterweg 1', zip='70173', city='Stuttgart')
        self.call(lid, 'nicht_erreicht', 'vormittag')
        self.call(lid, 'mailbox', 'nachmittag')
        r = self.call(lid, 'nicht_erreicht', 'mittag')
        self.assertTrue(r['follow_up']['exhausted'])
        tasks = self.open_tasks(lid)
        self.assertEqual(len(tasks), 1)  # alte „Erneut anrufen“-Aufgaben sind erledigt
        self.assertIn('Kanal wechseln', tasks[0])
        reach = q.reachability(self.conn, self.row(lid))
        self.assertEqual((reach['status'], reach['attempts_open'], reach['next_slot']), ('ausgeschoepft', 3, None))
        self.assertIn('Brief möglich', reach['hint'])

    def test_reached_call_resets_streak_and_remembers_good_slot(self):
        lid = self.lead(stage='kontakt', business_phone='0711 000000')
        self.call(lid, 'nicht_erreicht', 'vormittag')
        self.call(lid, 'erreicht', 'abend')
        self.assertEqual(q.attempts(self.conn, lid), [])
        self.call(lid, 'mailbox', 'vormittag')
        reach = q.reachability(self.conn, self.row(lid))
        self.assertEqual(reach['next_slot']['key'], 'abend')
        self.assertEqual((reach['attempts_total'], reach['reached_total']), (3, 1))

    def test_own_next_step_is_not_overwritten(self):
        lid = self.lead(stage='kontakt', next_step='Auf Messe ansprechen', next_date='2027-01-10')
        self.call(lid, 'nicht_erreicht', 'vormittag')
        self.assertEqual(self.row(lid)['next_step'], 'Auf Messe ansprechen')

    def test_channels_show_only_documented_routes_and_never_grant_permission(self):
        lid = self.lead(business_phone='0711 000000')
        reach = q.reachability(self.conn, self.row(lid))
        known = {c['key']: c['known'] for c in reach['channels']}
        self.assertEqual(known, {'telefon': True, 'email': False, 'brief': False})
        self.assertIn('§ 7 UWG', reach['notice'])
        self.assertEqual(self.row(lid)['permission'], 'unbekannt')

    def test_invalid_slot_rejected_and_default_slot_from_clock(self):
        lid = self.lead()
        with self.assertRaises(ValueError):
            self.call(lid, 'nicht_erreicht', 'nachts')
        create_call(self.conn, {'lead_id': lid, 'outcome': 'nicht_erreicht'})
        self.assertIn(self.conn.execute('SELECT slot FROM calls').fetchone()[0], q.SLOTS)
        self.assertEqual(q.slot_of(dt.datetime(2026, 11, 11, 15, 30)), 'nachmittag')

    def test_slot_stats_need_enough_calls(self):
        lid = self.lead()
        self.call(lid, 'erreicht', 'vormittag')
        s = q.slot_stats(self.conn)
        self.assertFalse(s['enough'])
        self.assertEqual(next(x for x in s['slots'] if x['slot'] == 'vormittag')['rate_pct'], 100)


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
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'} if body is not None else {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, json.loads(data) if data else None

    def test_profile_roundtrip_and_validation(self):
        st, d = self.call('GET', '/api/profile/target')
        self.assertEqual((st, d['profile']['radius_km']), (200, 30))
        self.assertTrue(any(i['key'] == 'elektro' for g in d['industries'] for i in g['items']))
        self.assertEqual(self.call('POST', '/api/profile/target', PROFILE)[0], 200)
        self.assertEqual(self.call('GET', '/api/profile/target')[1]['profile']['industries'], ['elektro', 'shk'])
        st, d = self.call('POST', '/api/profile/target', {**PROFILE, 'radius_km': -5})
        self.assertEqual(st, 400)

    def test_lost_needs_reason(self):
        _, lead = self.call('POST', '/api/leads', {'company': 'Elektro Fiktiv GmbH'})
        st, d = self.call('PATCH', f"/api/leads/{lead['id']}", {'stage': 'verloren'})
        self.assertEqual(st, 400)
        self.assertIn('Verlustgrund', d['error'])
        self.assertEqual(self.call('PATCH', f"/api/leads/{lead['id']}", {'stage': 'verloren', 'lost_reason': 'sonstiges'})[0], 400)
        st, d = self.call('PATCH', f"/api/leads/{lead['id']}", {'stage': 'verloren', 'lost_reason': 'preis', 'lost_note': 'Angebot 20 % über Budget'})
        self.assertEqual((st, d['stage'], d['lost_reason']), (200, 'verloren', 'preis'))
        # schon verloren: weitere Änderungen brauchen keinen neuen Grund
        self.assertEqual(self.call('PATCH', f"/api/leads/{lead['id']}", {'stage': 'verloren', 'note': 'Nachtrag'})[0], 200)
        _, ov = self.call('GET', '/api/assessment')
        self.assertEqual(ov['lost_reasons'], [{'reason': 'preis', 'label': 'Preis zu hoch', 'count': 1}])

    def test_assessment_in_company_file_and_overview_sorted(self):
        self.call('POST', '/api/profile/target', PROFILE)
        _, weak = self.call('POST', '/api/leads', {'company': 'Zahnarztpraxis Nord GmbH', 'location': '20095 Hamburg', 'employees': 400})
        _, good = self.call('POST', '/api/leads', {'company': 'Elektro Fiktiv e.K.', 'location': '70173 Stuttgart', 'employees': 6})
        st, f = self.call('GET', f"/api/leads/{good['id']}/file")
        self.assertEqual((st, f['assessment']['fit']['grade']), (200, 'A'))
        _, ov = self.call('GET', '/api/assessment')
        self.assertEqual([r['company'] for r in ov['leads']], ['Elektro Fiktiv e.K.', 'Zahnarztpraxis Nord GmbH'])
        self.assertTrue(ov['profile_complete'])
        self.assertEqual(self.call('GET', '/api/leads/99999/assessment')[0], 400)

    def test_missed_call_via_api_returns_follow_up(self):
        _, lead = self.call('POST', '/api/leads', {'company': 'Elektro Fiktiv GmbH'})
        st, d = self.call('POST', '/api/workspace/calls', {'lead_id': lead['id'], 'outcome': 'mailbox', 'slot': 'mittag'})
        self.assertEqual(st, 201)
        self.assertIn('Erneut anrufen (2. Versuch)', d['follow_up']['task'])


class MigrationTests(unittest.TestCase):
    def test_old_database_gets_new_columns_and_keeps_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'alt.sqlite3')
            raw = sqlite3.connect(db)
            raw.executescript((Path(__file__).parent / 'fixtures' / 'migration' / 'v1_6.sql').read_text(encoding='utf-8'))
            n_leads = raw.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
            n_calls = raw.execute('SELECT COUNT(*) FROM calls').fetchone()[0]
            raw.commit()
            raw.close()
            prepare_database(db)
            with connect(db) as conn:
                self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], n_leads)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM calls WHERE slot=''").fetchone()[0], n_calls)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM leads WHERE lost_reason<>''").fetchone()[0], 0)
                for lead in conn.execute('SELECT * FROM leads'):
                    q.assessment(conn, lead)  # Altdaten lassen sich bewerten, ohne Fehler


if __name__ == '__main__':
    unittest.main()
