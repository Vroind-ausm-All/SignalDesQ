"""2.0.0-dev5: Nachkalkulation – tatsächliche Stunden je angenommenem Festpreisangebot.

Abnahme:
- Zeiten nur für angenommene Angebote; abgeschlossene Aufträge sind gegen Änderungen geschützt, bis man sie wieder öffnet.
- Soll/Ist, tatsächlicher Stundenverdienst und Urteil gegen den eigenen Mindestverdienst.
- Die Auslastung rechnet mit verbleibenden Stunden; abgeschlossene Aufträge zählen nicht mehr.
- Rechnungen und Angebote bleiben unverändert.
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

from sales_tool import postcalc as pc  # noqa: E402
from sales_tool import reach  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, make_handler, prepare_database  # noqa: E402

TODAY = dt.date(2026, 11, 13)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / 't.sqlite3'))
        init_db(self.conn)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Elektro Beispiel e.K.', 'gewonnen')").lastrowid

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def offer(self, status='angenommen', hours=20, net=2000, ext=100, minimum=66):
        cur = self.conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, number, updated_at) VALUES (?,?,?,?,?,?)",
                                (self.lead, status, json.dumps({'estimated_hours': hours, 'external_cost_eur': ext, 'min_hourly_earning': minimum}),
                                 json.dumps({'net_eur': net, 'project_label': 'Website-Relaunch'}), 'AN-2026-0001', '2026-11-10 10:00:00'))
        self.conn.commit()
        return cur.lastrowid

    def log(self, pid, hours, day='2026-11-12', note=''):
        return pc.add_entry(self.conn, {'proposal_id': pid, 'hours': hours, 'work_date': day, 'note': note}, today=TODAY)

    def project(self, pid):
        return next(p for p in pc.overview(self.conn)['projects'] if p['proposal_id'] == pid)


class EntryTests(Base):
    def test_only_accepted_offers_and_valid_values(self):
        draft = self.offer(status='entwurf')
        with self.assertRaises(ValueError):
            self.log(draft, 2)
        pid = self.offer()
        for bad in ({'hours': 0}, {'hours': 300}, {'hours': '2'}, {'hours': True}, {'hours': 2, 'work_date': '2026-11-14'},
                    {'hours': 2, 'work_date': 'gestern'}, {'hours': 2, 'note': 'x' * 301}, {'hours': 2, 'extra': 1}):
            with self.assertRaises(ValueError, msg=bad):
                pc.add_entry(self.conn, {'proposal_id': pid, **bad}, today=TODAY)
        with self.assertRaises(ValueError):
            pc.add_entry(self.conn, {'proposal_id': 999, 'hours': 1}, today=TODAY)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM time_entries').fetchone()[0], 0)

    def test_running_project_shows_remaining_hours(self):
        pid = self.offer(hours=20)
        self.assertEqual(self.project(pid)['status'], 'nicht_begonnen')
        r = self.log(pid, 6.5, note='Konzept')
        self.assertEqual((r['project']['actual_hours'], r['project']['remaining_hours'], r['project']['status']), (6.5, 13.5, 'laeuft'))
        self.assertEqual(r['project']['planned_hourly'], 95.0)  # (2000 − 100) / 20
        self.assertEqual(r['project']['entries'][0]['note'], 'Konzept')

    def test_overrun_is_flagged(self):
        pid = self.offer(hours=10)
        self.log(pid, 8)
        self.log(pid, 6)
        p = self.project(pid)
        self.assertEqual((p['status'], p['variance_pct'], p['remaining_hours']), ('ueberzogen', 40, 0.0))
        self.assertIn('über der Kalkulation', p['verdict'])


class ClosingTests(Base):
    def test_close_needs_entries_and_judges_against_minimum(self):
        pid = self.offer(hours=20, net=2000, ext=100, minimum=66)
        with self.assertRaises(ValueError):
            pc.close_project(self.conn, pid, {}, today=TODAY)
        self.log(pid, 25)
        p = pc.close_project(self.conn, pid, {'actual_external_eur': 150, 'note': 'zwei Korrekturrunden mehr'}, today=TODAY)
        self.assertEqual((p['status'], p['actual_hourly'], p['below_minimum'], p['remaining_hours']), ('abgeschlossen', 74.0, False, 0.0))
        self.assertIn('Hat sich gelohnt', p['verdict'])
        weak = self.offer(hours=10, net=900, ext=0)
        self.log(weak, 20)
        p = pc.close_project(self.conn, weak, {}, today=TODAY)
        self.assertEqual((p['actual_hourly'], p['below_minimum']), (45.0, True))
        self.assertIn('Unter deinem Mindestverdienst', p['verdict'])

    def test_closed_project_is_protected_until_reopened(self):
        pid = self.offer()
        entry = self.log(pid, 5)['id']
        pc.close_project(self.conn, pid, {}, today=TODAY)
        with self.assertRaises(ValueError):
            self.log(pid, 1)
        with self.assertRaises(ValueError):
            pc.delete_entry(self.conn, entry)
        pc.reopen_project(self.conn, pid)
        self.log(pid, 1)
        self.assertEqual(pc.delete_entry(self.conn, entry), {'deleted': True})
        self.assertEqual(self.project(pid)['actual_hours'], 1.0)

    def test_lesson_only_from_three_closed_projects(self):
        for i, actual in enumerate((12, 11, 13)):
            pid = self.offer(hours=10)
            self.log(pid, actual)
            self.assertIsNone(pc.overview(self.conn)['lesson'])
            pc.close_project(self.conn, pid, {}, today=TODAY)
            del i
        lesson = pc.overview(self.conn)['lesson']
        self.assertEqual((lesson['projects'], lesson['avg_variance_pct']), (3, 20))
        self.assertIn('20 % mehr Zeit', lesson['text'])

    def test_offer_and_invoices_untouched(self):
        pid = self.offer()
        before = dict(self.conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone())
        self.log(pid, 3)
        pc.close_project(self.conn, pid, {}, today=TODAY)
        self.assertEqual(dict(self.conn.execute('SELECT * FROM proposals WHERE id=?', (pid,)).fetchone()), before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM invoices').fetchone()[0], 0)


class CapacityTests(Base):
    def test_capacity_uses_remaining_hours_and_drops_closed_projects(self):
        pid = self.offer(hours=42)
        c = reach.capacity(self.conn, today=TODAY)
        self.assertEqual((c['accepted_hours'], c['untracked_projects']), (42.0, 1))
        self.log(pid, 30)
        c = reach.capacity(self.conn, today=TODAY)
        self.assertEqual((c['accepted_hours'], c['tracked_projects'], c['untracked_projects']), (12.0, 1, 0))
        pc.close_project(self.conn, pid, {}, today=TODAY)
        self.assertEqual(reach.capacity(self.conn, today=TODAY)['accepted_hours'], 0.0)

    def test_old_project_with_logged_time_still_counts_its_rest(self):
        """Früher fiel ein Auftrag nach 8 Wochen ganz aus der Auslastung, auch wenn noch Arbeit offen war."""
        pid = self.offer(hours=100)
        self.conn.execute("UPDATE proposals SET updated_at='2026-06-01 10:00:00' WHERE id=?", (pid,))
        self.assertEqual(reach.capacity(self.conn, today=TODAY)['accepted_hours'], 0.0)
        self.log(pid, 40)
        self.assertEqual(reach.capacity(self.conn, today=TODAY)['accepted_hours'], 60.0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'api.sqlite3')
        prepare_database(self.db)
        with connect(self.db) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            lead = c.execute("INSERT INTO leads(company, stage) VALUES ('Elektro Fiktiv e.K.', 'gewonnen')").lastrowid
            self.pid = c.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json) VALUES (?, 'angenommen', ?, ?)",
                                 (lead, json.dumps({'estimated_hours': 10}), json.dumps({'net_eur': 1000}))).lastrowid
            c.commit()
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

    def test_roundtrip(self):
        st, d = self.call('POST', '/api/postcalc/entries', {'proposal_id': self.pid, 'hours': 4})
        self.assertEqual((st, d['project']['remaining_hours']), (201, 6.0))
        self.assertEqual(self.call('POST', '/api/postcalc/entries', {'proposal_id': self.pid, 'hours': 999})[0], 400)
        st, ov = self.call('GET', '/api/postcalc')
        self.assertEqual((st, ov['open'], ov['projects'][0]['company']), (200, 1, 'Elektro Fiktiv e.K.'))
        self.assertEqual(self.call('POST', f'/api/postcalc/{self.pid}/close', {})[0], 200)
        self.assertEqual(self.call('DELETE', f"/api/postcalc/entries/{d['id']}")[0], 400)
        self.assertEqual(self.call('POST', f'/api/postcalc/{self.pid}/reopen')[0], 200)
        self.assertEqual(self.call('DELETE', f"/api/postcalc/entries/{d['id']}")[0], 200)


if __name__ == '__main__':
    unittest.main()
