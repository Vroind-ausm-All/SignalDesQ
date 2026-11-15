"""2.0.0-dev41: Produktreview M24 Stufe 1 – Kalender-Abo und Termin-Export (iCalendar).

- Abo nur mit geheimem Schlüssel; ausgeschaltet oder falscher Schlüssel → nichts. Neuer Schlüssel macht die alte Adresse ungültig.
- Auch mit eingeschaltetem Login abrufbar (Kalenderprogramme können sich nicht anmelden) – aber nur das Abo, nicht die Verwaltung.
- Inhalt: Titel, Firma, Zeit, Ort, Status; keine Gesprächsnotizen. Gültiges Format (Escapes, Zeilenlänge).
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import calendar_feed as cf  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.quality import put_setting  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'k.sqlite3')
        prepare_database(self.db)
        c = self.conn = connect(self.db)
        lead = c.execute("INSERT INTO leads(company) VALUES ('Kalender, Fiktiv; GmbH')").lastrowid
        c.execute("""INSERT INTO meetings(lead_id, title, starts_at, duration_min, location, status, notes)
                     VALUES (?, 'Erstgespräch Website-Relaunch mit sehr langem Titel für die Prüfung der Zeilenlänge', '2099-03-04T10:30', 45, 'Büro, 2. OG', 'bestaetigt', 'Geheime Notiz: Budget knapp')""", (lead,))
        c.execute("INSERT INTO meetings(lead_id, title, starts_at, status) VALUES (?, 'Abgesagt', '2099-03-05T09:00', 'abgesagt')", (lead,))
        c.execute("INSERT INTO meetings(lead_id, title, starts_at, status) VALUES (?, 'Erledigt', '2099-03-06T09:00', 'erledigt')", (lead,))
        c.commit()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.conn.close()
        cleanup_tmp(self.tmp)

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.headers.get('Content-Type', ''), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get('Content-Type', ''), e.read()

    def test_ics_content_and_format(self):
        ics = cf.build(self.conn).decode('utf-8')
        self.assertTrue(ics.startswith('BEGIN:VCALENDAR\r\n') and ics.endswith('END:VCALENDAR\r\n'))
        self.assertEqual(ics.count('BEGIN:VEVENT'), 2, 'geplant/bestätigt/abgesagt, nicht erledigt')
        self.assertIn('DTSTART;TZID=Europe/Berlin:20990304T103000', ics)
        self.assertIn('DTEND;TZID=Europe/Berlin:20990304T111500', ics)
        self.assertIn('STATUS:CONFIRMED', ics)
        self.assertIn('STATUS:CANCELLED', ics)
        self.assertIn('LOCATION:Büro\\, 2. OG', ics)
        self.assertIn('Kalender\\, Fiktiv\\; GmbH', ics.replace('\r\n ', ''))
        self.assertNotIn('Geheime Notiz', ics)
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in ics.split('\r\n')), 'Zeilen höchstens 75 Oktette')

    def test_feed_requires_secret_token_also_with_login(self):
        self.assertEqual(self.get('/kalender/' + 'x' * 32 + '.ics')[0], 404, 'ausgeschaltet')
        v = cf.update(self.conn, {'enabled': True})
        status, ctype, body = self.get(v['path'])
        self.assertEqual((status, ctype.split(';')[0]), (200, 'text/calendar'))
        self.assertIn(b'SignalDesk Termine', body)
        self.assertEqual(self.get('/kalender/' + 'y' * 32 + '.ics')[0], 404, 'falscher Schlüssel')
        put_setting(self.conn, 'auth_required', True)
        self.conn.commit()
        self.assertEqual(self.get(v['path'])[0], 200, 'Abo auch mit Login, über den Schlüssel')
        self.assertEqual(self.get('/api/kalender')[0], 401, 'Verwaltung nur mit Anmeldung')
        self.assertEqual(self.get('/api/kalender/export.ics')[0], 401)
        put_setting(self.conn, 'auth_required', False)
        self.conn.commit()
        new = cf.update(self.conn, {'regenerate': True})
        self.assertNotEqual(new['path'], v['path'])
        self.assertEqual(self.get(v['path'])[0], 404, 'alte Adresse ungültig')
        self.assertEqual(self.get(new['path'])[0], 200)
        cf.update(self.conn, {'enabled': False})
        self.assertEqual(self.get(new['path'])[0], 404, 'Abo ausgeschaltet')
        status, ctype, body = self.get('/api/kalender/export.ics')
        self.assertEqual(status, 200)
        self.assertIn(b'BEGIN:VEVENT', body)


if __name__ == '__main__':
    unittest.main()
