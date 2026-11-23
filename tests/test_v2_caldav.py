"""2.0.0-dev42: Produktreview M24 Stufe 2 – Kalender-Abgleich über CalDAV, Zugangsdaten außerhalb der Datenbank.

Gegen einen nachgebauten CalDAV-Server auf 127.0.0.1 (PROPFIND, PUT, DELETE, REPORT) – keine Abrufe nach außen.
- Termine werden geschrieben (nur Titel, Firma, Zeit, Ort – keine Notizen), unveränderte nicht erneut, gelöschte entfernt.
- Fremde Einträge bleiben unangetastet; nur „belegt“ wird gelesen (eigene, abgesagte und „frei“ markierte zählen nicht).
- Konfliktwarnung beim Anlegen, freie Vorschläge sparen belegte Zeiten aus.
- Passwort nie in der Datenbank; „merken“ nur im Passwortspeicher des Betriebssystems (SDQ-004, vorher Klartext-JSON); falsches Passwort → klare Meldung.
- Nur HTTPS außer auf diesem Rechner; im Offline-Modus kein Abgleich.
Alle Firmen sind fiktiv.
"""
import base64
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from cred_fake import FakeStore  # noqa: E402
from sales_tool import caldav, credentials, netpolicy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

USER, PASS = 'agentur', 'app-pass-123'
TOMORROW = (dt.date.today() + dt.timedelta(days=1)).strftime('%Y%m%d')
FOREIGN = (f'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:fremd-1@anbieter\r\nSUMMARY:Zahnarzt privat\r\n'
           f'DTSTART;TZID=Europe/Berlin:{TOMORROW}T100000\r\nDTEND;TZID=Europe/Berlin:{TOMORROW}T110000\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')


class FakeCalDAV(BaseHTTPRequestHandler):
    store: dict = {}
    log: list = []

    def log_message(self, *a):
        pass

    def _ok_auth(self):
        want = 'Basic ' + base64.b64encode(f'{USER}:{PASS}'.encode()).decode()
        if self.headers.get('Authorization') != want:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="cal"')
            self.end_headers()
            return False
        return True

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def _reply(self, code, body=b'', ctype='application/xml'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PROPFIND(self):
        self._body()
        FakeCalDAV.log.append(('PROPFIND', self.path))
        if self._ok_auth():
            self._reply(207, b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>'
                             b'<d:href>/cal/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/></d:resourcetype>'
                             b'</d:prop></d:propstat></d:response></d:multistatus>')

    def do_PUT(self):
        body = self._body()
        FakeCalDAV.log.append(('PUT', self.path))
        if self._ok_auth():
            created = self.path not in FakeCalDAV.store
            FakeCalDAV.store[self.path] = body.decode()
            self._reply(201 if created else 204)

    def do_DELETE(self):
        self._body()
        FakeCalDAV.log.append(('DELETE', self.path))
        if self._ok_auth():
            self._reply(204 if FakeCalDAV.store.pop(self.path, None) is not None else 404)

    def do_REPORT(self):
        self._body()
        FakeCalDAV.log.append(('REPORT', self.path))
        if self._ok_auth():
            parts = ''.join(f'<d:response><d:href>{h}</d:href><d:propstat><d:prop><c:calendar-data>{_x(v)}</c:calendar-data>'
                            f'</d:prop></d:propstat></d:response>' for h, v in FakeCalDAV.store.items())
            self._reply(207, ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                              f'{parts}</d:multistatus>').encode())


def _x(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


class CalDavTests(unittest.TestCase):
    def setUp(self):
        netpolicy.STATE.update(stored=False, forced=False)
        self.store = FakeStore()
        credentials.set_backend(self.store)  # SDQ-004: nie den echten Schlüsselbund des Rechners benutzen
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'c.sqlite3')
        prepare_database(self.db)
        c = self.conn = connect(self.db)
        self.lead = c.execute("INSERT INTO leads(company) VALUES ('Abgleich Fiktiv GmbH')").lastrowid
        start = (dt.datetime.now() + dt.timedelta(days=2)).replace(hour=14, minute=0).strftime('%Y-%m-%dT%H:%M')
        self.mid = c.execute("""INSERT INTO meetings(lead_id, title, starts_at, duration_min, location, status, notes)
                                VALUES (?, 'Erstgespräch', ?, 45, 'Büro', 'geplant', 'Geheime Notiz: Budget knapp')""", (self.lead, start)).lastrowid
        c.commit()
        FakeCalDAV.store = {'/cal/fremd-1.ics': FOREIGN}
        FakeCalDAV.log = []
        self.dav = ThreadingHTTPServer(('127.0.0.1', 0), FakeCalDAV)
        threading.Thread(target=self.dav.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.dav.server_port}/cal/'

    def tearDown(self):
        self.dav.shutdown()
        self.dav.server_close()
        self.conn.close()
        credentials._MEMORY.clear()
        credentials.set_backend('auto')
        netpolicy.STATE.update(stored=False, forced=False)
        cleanup_tmp(self.tmp)

    def configure(self, pw=PASS, remember=False):
        return caldav.save(self.conn, self.db, {'url': self.url, 'username': USER, 'password': pw, 'remember': remember})

    def test_sync_both_directions(self):
        v = self.configure()
        self.assertTrue(v['configured'])
        self.assertEqual(v['password'], {'stored': True, 'remembered': False})
        self.assertTrue(caldav.test(self.conn, self.db)['calendar'])
        r = caldav.sync(self.conn, self.db)
        self.assertEqual((r['pushed'], r['deleted'], r['busy']), (1, 0, 1), r)
        own = FakeCalDAV.store[f'/cal/signaldesk-meeting-{self.mid}.ics']
        self.assertIn('SUMMARY:Erstgespräch – Abgleich Fiktiv GmbH', own)
        self.assertIn('LOCATION:Büro', own)
        self.assertNotIn('Budget', own, 'keine Notizen im Kalender')
        self.assertEqual(FakeCalDAV.store['/cal/fremd-1.ics'], FOREIGN, 'fremder Eintrag unverändert')
        busy = self.conn.execute('SELECT starts_at, ends_at FROM caldav_busy').fetchall()
        day = f'{TOMORROW[:4]}-{TOMORROW[4:6]}-{TOMORROW[6:]}'
        self.assertEqual([tuple(b) for b in busy], [(f'{day}T10:00', f'{day}T11:00')], 'nur fremde Zeit, ohne Titel')
        self.assertNotIn('Zahnarzt', json.dumps(caldav.view(self.conn, self.db)))
        # zweiter Lauf: nichts geändert → nichts übertragen
        FakeCalDAV.log = []
        r = caldav.sync(self.conn, self.db)
        self.assertEqual((r['pushed'], r['unchanged']), (0, 1))
        self.assertFalse([x for x in FakeCalDAV.log if x[0] == 'PUT'])
        # geändert → erneut; gelöscht → entfernt (nur der eigene Eintrag)
        self.conn.execute("UPDATE meetings SET status='bestaetigt' WHERE id=?", (self.mid,))
        self.conn.commit()
        self.assertEqual(caldav.sync(self.conn, self.db)['pushed'], 1)
        self.assertIn('STATUS:CONFIRMED', FakeCalDAV.store[f'/cal/signaldesk-meeting-{self.mid}.ics'])
        self.conn.execute('DELETE FROM meetings WHERE id=?', (self.mid,))
        self.conn.commit()
        r = caldav.sync(self.conn, self.db)
        self.assertEqual(r['deleted'], 1)
        self.assertEqual(list(FakeCalDAV.store), ['/cal/fremd-1.ics'])
        self.assertIn('1 entfernt', r['last_result'])
        self.assertFalse(r['stale'])

    def test_conflicts_and_free_slots(self):
        self.configure()
        caldav.sync(self.conn, self.db)
        day = f'{TOMORROW[:4]}-{TOMORROW[4:6]}-{TOMORROW[6:]}'
        from sales_tool.sales_workspace import create_meeting
        clash = create_meeting(self.conn, {'lead_id': self.lead, 'title': 'Folgetermin', 'starts_at': f'{day}T10:30', 'duration_min': 30})
        self.assertEqual(len(clash['conflicts']), 1)
        self.assertEqual(clash['conflicts'][0]['source'], 'kalender')
        self.assertIn('überschneidet', clash['warning'])
        free = create_meeting(self.conn, {'lead_id': self.lead, 'title': 'Später', 'starts_at': f'{day}T15:00', 'duration_min': 30})
        self.assertEqual((free['conflicts'], free['warning']), ([], ''))
        # zwei SignalDesk-Termine überlappen sich ebenfalls
        twin = create_meeting(self.conn, {'lead_id': self.lead, 'title': 'Doppelt', 'starts_at': f'{day}T15:15', 'duration_min': 30})
        self.assertEqual([c['source'] for c in twin['conflicts']], ['signaldesk'])
        # freie Vorschläge: eine belegte Kalenderzeit genau auf dem ersten Vorschlag verschiebt ihn
        from sales_tool import reach
        self.conn.execute('DELETE FROM meetings')
        self.conn.execute('DELETE FROM caldav_busy')
        now = dt.datetime(2099, 6, 1, 8, 0)
        first = reach.meeting_slots(self.conn, now=now, count=1)
        self.assertIn('Kalender (letzter Abgleich)', first['notice'])
        s0 = first['slots'][0]['starts_at']
        end = (dt.datetime.strptime(s0, '%Y-%m-%dT%H:%M') + dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
        self.conn.execute('INSERT INTO caldav_busy(starts_at, ends_at) VALUES (?,?)', (s0, end))
        s1 = reach.meeting_slots(self.conn, now=now, count=1)['slots'][0]['starts_at']
        self.assertNotEqual(s0, s1)
        self.assertFalse(s0 <= s1 < end, 'kein Vorschlag in belegter Zeit')

    def test_busy_parser(self):
        text = ('BEGIN:VEVENT\r\nUID:meeting-7@signaldesk.local\r\nDTSTART:20990101T100000Z\r\nDTEND:20990101T110000Z\r\nEND:VEVENT\r\n'
                'BEGIN:VEVENT\r\nUID:a\r\nSTATUS:CANCELLED\r\nDTSTART:20990101T100000Z\r\nEND:VEVENT\r\n'
                'BEGIN:VEVENT\r\nUID:b\r\nTRANSP:TRANSPARENT\r\nDTSTART:20990101T100000Z\r\nEND:VEVENT\r\n'
                'BEGIN:VEVENT\r\nUID:c\r\nDTSTART;VALUE=DATE:20990102\r\nEND:VEVENT\r\n'
                'BEGIN:VEVENT\r\nUID:d\r\nDTSTART;TZID=Europe/Berlin:20990103T090000\r\nDURATION:PT1H30M\r\nEND:VEVENT\r\n')
        got = caldav.busy_from_ics(text)
        self.assertEqual(got, [(dt.datetime(2099, 1, 2), dt.datetime(2099, 1, 3), True),
                               (dt.datetime(2099, 1, 3, 9), dt.datetime(2099, 1, 3, 10, 30), False)])

    def test_password_never_in_database(self):
        self.configure(remember=False)
        f = Path(self.tmp.name) / 'zugangsdaten.json'
        self.assertFalse(f.exists(), 'ohne „merken“ nur im Arbeitsspeicher')
        self.configure(remember=True)
        # SDQ-004: „merken“ schreibt nie mehr Klartext auf den Datenträger, sondern in den Passwortspeicher des Betriebssystems
        self.assertFalse(f.exists(), 'keine Klartext-Datei mehr')
        self.assertEqual(list(self.store.data.values()), [PASS])
        for name in os.listdir(self.tmp.name):
            if (Path(self.tmp.name) / name).is_file():
                self.assertNotIn(PASS.encode(), (Path(self.tmp.name) / name).read_bytes(), name)
        self.conn.commit()
        self.conn.execute('PRAGMA wal_checkpoint(FULL)')
        for name in os.listdir(self.tmp.name):
            if name.startswith('c.sqlite3'):
                self.assertNotIn(PASS.encode(), (Path(self.tmp.name) / name).read_bytes(), name)
        self.assertNotIn(PASS, json.dumps(caldav.view(self.conn, self.db)))
        credentials._MEMORY.clear()  # „Neustart“
        self.assertEqual(credentials.get(self.db, 'caldav'), PASS, 'gemerkt überlebt den Neustart')
        v = caldav.save(self.conn, self.db, {'forget': True})
        self.assertEqual(v['password'], {'stored': False, 'remembered': False})
        self.assertFalse(f.exists())
        with self.assertRaisesRegex(ValueError, 'Passwort für den Kalender fehlt'):
            caldav.sync(self.conn, self.db)

    def test_wrong_password_https_and_offline(self):
        self.configure(pw='falsch')
        with self.assertRaisesRegex(ValueError, 'Anmeldung beim Kalender abgelehnt'):
            caldav.sync(self.conn, self.db)
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            caldav.save(self.conn, self.db, {'url': 'http://dav.example.org/cal/'})
        self.assertTrue(caldav.save(self.conn, self.db, {'url': 'https://dav.example.org/cal'})['url'].endswith('/cal/'))
        self.configure()
        netpolicy.set_offline(self.conn, True)
        n = len(FakeCalDAV.log)
        with self.assertRaises(Exception):
            caldav.sync(self.conn, self.db)
        self.assertEqual(len(FakeCalDAV.log), n, 'offline: keine Anfrage')

    def test_api_routes(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            def api(path, method='GET', body=None):
                req = urllib.request.Request(base + '/api' + path, method=method, headers={'Content-Type': 'application/json', 'Origin': base},
                                             data=json.dumps(body).encode() if body is not None else None)
                return json.loads(urllib.request.urlopen(req).read())
            v = api('/caldav', 'POST', {'url': self.url, 'username': USER, 'password': PASS})
            self.assertNotIn(PASS, json.dumps(v))
            self.assertTrue(api('/caldav/test', 'POST', {})['ok'])
            self.assertEqual(api('/caldav/sync', 'POST', {})['pushed'], 1)
            self.assertTrue(api('/caldav')['last_sync'])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
