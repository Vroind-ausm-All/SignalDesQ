"""SDQ-008: Beschreibung je Datenquelle – Lizenz, Aktualität, Limits, Kosten, Personendaten – und gemessene Werte
(Abfragen, Fehlerrate, letzter Erfolg, Übernahmequote) aus den eigenen Abfragen dieser Installation. Keine Abrufe nach außen."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import lead_finder as lf  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

REQUIRED = ('license', 'attribution', 'ampel', 'freshness', 'provider_limits', 'cost', 'personal_data')
IMPORTS = ('gleif_csv', 'liste')  # Dateiimporte haben keine Abruf-Adresse


class ProviderReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / 'p.sqlite3'
        prepare_database(self.db)
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def run_row(self, source, status, results=0, filtered=0, error='', age_days=0):
        cur = self.conn.execute(
            """INSERT INTO discovery_runs(source, params_json, status, result_count, filtered_count, error, created_at, finished_at)
               VALUES (?, '{}', ?, ?, ?, ?, datetime('now', ?), datetime('now', ?))""",
            (source, status, results, filtered, error, f'-{age_days} days', f'-{age_days} days'))
        return cur.lastrowid

    def cand(self, run_id, source, status, n=1):
        for i in range(n):
            self.conn.execute("INSERT INTO discovery_candidates(run_id, source, name, status) VALUES (?, ?, ?, ?)",
                              (run_id, source, f'Fiktiv {status} {i} GmbH', status))

    def by_key(self, rep):
        return {p['key']: p for p in rep['providers']}

    def test_every_source_is_described(self):
        rep = lf.provider_report(self.conn)
        self.assertEqual({p['key'] for p in rep['providers']}, set(lf.SOURCES))
        for p in rep['providers']:
            for f in REQUIRED + (() if p['key'] in IMPORTS else ('url',)):
                self.assertTrue(p[f], f'{p["key"]}: {f} fehlt')
        self.assertFalse(rep['live_verified'], 'Angaben sind nicht live geprüft – das muss die Antwort sagen')
        self.assertIn('Stand', rep['note'])

    def test_no_runs_means_no_rate(self):
        m = self.by_key(lf.provider_report(self.conn))['osm']['measured']
        self.assertEqual((m['runs'], m['error_rate'], m['error_rate_ci95'], m['take_over_rate']), (0, None, None, None))

    def test_error_rate_last_success_and_take_over(self):
        r1 = self.run_row('osm', 'done', results=10, filtered=3, age_days=2)
        self.run_row('osm', 'done', results=6, age_days=1)
        self.run_row('osm', 'failed', error='Overpass: 504 Gateway Timeout', age_days=0)
        self.run_row('osm', 'running')                    # läuft noch: zählt als Abfrage, nicht in die Fehlerrate
        self.run_row('osm', 'failed', error='alt', age_days=40)  # außerhalb des Zeitraums
        self.run_row('gleif', 'done', results=1)
        self.cand(r1, 'osm', 'uebernommen', 2)
        self.cand(r1, 'osm', 'verworfen', 5)
        self.cand(r1, 'osm', 'dublette', 1)
        self.cand(r1, 'osm', 'neu', 2)
        self.conn.commit()
        rep = self.by_key(lf.provider_report(self.conn))
        m = rep['osm']['measured']
        self.assertEqual((m['runs'], m['done'], m['failed']), (4, 2, 1))
        self.assertEqual(m['error_rate'], round(1 / 3, 3))
        lo, hi = m['error_rate_ci95']
        self.assertTrue(0 < lo < 0.34 < hi < 1)
        self.assertEqual(m['last_error'], 'Overpass: 504 Gateway Timeout')
        self.assertTrue(m['last_success'] and m['last_failure'])
        self.assertEqual((m['results'], m['filtered'], m['results_per_run']), (16, 3, 8.0))
        self.assertEqual((m['candidates'], m['reviewed'], m['taken_over'], m['rejected'], m['duplicates']), (10, 8, 2, 5, 1))
        self.assertEqual(m['take_over_rate'], 0.25)
        self.assertEqual(rep['gleif']['measured']['error_rate'], 0.0)
        self.assertEqual(rep['wikidata']['measured']['runs'], 0)

    def test_window_in_days(self):
        self.run_row('ted', 'failed', error='x', age_days=10)
        self.conn.commit()
        self.assertEqual(self.by_key(lf.provider_report(self.conn, days=7))['ted']['measured']['runs'], 0)
        self.assertEqual(self.by_key(lf.provider_report(self.conn, days=30))['ted']['measured']['runs'], 1)
        self.assertEqual(lf.provider_report(self.conn, days=0)['providers'][0]['measured']['days'], 1)

    def test_local_osm_import_date(self):
        self.assertIsNone(lf.provider_report(self.conn)['local_osm'])
        self.conn.execute("""INSERT INTO osm_imports(filename, kind, status, places, finished_at)
                             VALUES ('/home/x/baden-wuerttemberg-latest.osm.pbf', 'pbf', 'fertig', 1234, '2026-11-20 08:00:00')""")
        self.conn.commit()
        local = lf.provider_report(self.conn)['local_osm']
        self.assertEqual(local, {'filename': 'baden-wuerttemberg-latest.osm.pbf', 'places': 1234, 'imported_at': '2026-11-20 08:00:00'},
                         'nur Dateiname, kein Pfad aus dem Nutzerverzeichnis')

    def test_route(self):
        self.run_row('wikidata', 'done', results=4)
        self.conn.commit()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            rep = json.loads(urllib.request.urlopen(base + '/api/lead-finder/providers?days=30').read())
            self.assertEqual(self.by_key(rep)['wikidata']['measured']['done'], 1)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + '/api/lead-finder/providers?days=x')
            self.assertEqual(ctx.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
