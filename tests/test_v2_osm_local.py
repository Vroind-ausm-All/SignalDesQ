"""2.0.0-dev7: OpenStreetMap manuell und offline – Betriebe aus einem lokalen Auszug (.osm.pbf) oder einem Handexport (JSON).

Die Datei `fixtures/osm/beispiel.osm.pbf` wurde mit dem offiziellen Werkzeug osmium erzeugt (fiktive Betriebe); der eigene
Leser muss sie ohne Zusatzpaket richtig lesen.

Abnahme:
- Ohne Auftrag wird kein öffentlicher OpenStreetMap-Server mehr abgefragt.
- Mit eingelesenem Auszug liefert die Suche Betriebe offline: genau eine PLZ, die ganze Stadt (alle PLZ) oder ein Umkreis.
- Nur benannte Betriebe werden gespeichert; Spielplätze, Straßen, Stillgelegtes und Namenloses nicht.
- Kaputte oder fremde Dateien führen zu einer klaren Meldung, nicht zu einem Absturz.
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import jobs, osm_local  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402

PBF = Path(__file__).parent / 'fixtures' / 'osm' / 'beispiel.osm.pbf'
OVERPASS = {'elements': [
    {'type': 'node', 'id': 201, 'lat': 48.8001, 'lon': 9.1753, 'tags': {'name': 'Sanitär Fiktiv GmbH', 'craft': 'plumber', 'addr:postcode': '70191', 'addr:city': 'Stuttgart'}},
    {'type': 'way', 'id': 202, 'center': {'lat': 48.8002, 'lon': 9.1755}, 'tags': {'name': 'Werkstatt Beispiel GmbH', 'shop': 'car_repair'}},
    {'type': 'node', 'id': 203, 'lat': 48.8003, 'lon': 9.1757, 'tags': {'name': 'Parkhaus Nord', 'amenity': 'parking'}}]}


class ReaderTests(unittest.TestCase):
    def test_pbf_from_official_tool_is_read_correctly(self):
        got = {f'{t}/{i}': (tags, lat, lon) for t, i, tags, lat, lon in osm_local.iter_pbf(PBF)}
        tags, lat, lon = got['node/101']
        self.assertEqual((tags['name'], tags['craft'], tags['addr:postcode'], tags['opening_hours']), ('Elektro Fiktiv GmbH', 'electrician', '70191', 'Mo-Fr 07:30-16:30'))
        self.assertAlmostEqual(lat, 48.80012, places=6)
        self.assertAlmostEqual(lon, 9.17534, places=6)
        self.assertEqual(got['node/104'][0]['name'], 'Bäckerei Ähre & Söhne')  # Umlaute
        self.assertAlmostEqual(got['node/109'][1], -33.5, places=6)  # negative Koordinaten
        self.assertAlmostEqual(got['node/109'][2], -70.6, places=6)
        self.assertEqual(got['way/5001'][0]['shop'], 'car')
        self.assertIsNone(got['way/5001'][1])  # Wege haben im Auszug keine Koordinaten
        self.assertNotIn('node/106', got)  # ohne Namen
        self.assertNotIn('node/1000', got)  # ohne Merkmale

    def test_only_named_businesses_are_kept(self):
        names = {p['name'] for p in filter(None, (osm_local.place_from_tags(*e) for e in osm_local.iter_pbf(PBF)))}
        self.assertEqual(names, {'Elektro Fiktiv GmbH', 'Malerbetrieb Beispiel', 'Bäckerei Ähre & Söhne', 'Schreinerei Fern GmbH',
                                 'Südhalbkugel Test', 'Autohaus Muster GmbH'})
        # nicht dabei: Platz, Spielplatz, stillgelegtes Kino, Straße

    def test_place_fields_and_no_personal_data(self):
        p = osm_local.place_from_tags('node', 1, {'name': 'Elektro Fiktiv GmbH', 'craft': 'electrician', 'addr:street': 'Musterweg', 'addr:housenumber': '1',
                                                  'addr:postcode': '70191', 'website': 'elektro-fiktiv.example', 'phone': '+49 711 000000',
                                                  'email': 'chef@elektro-fiktiv.example', 'operator': 'Max Beispiel'}, 48.8, 9.17)
        self.assertEqual((p['street'], p['zip'], p['phone']), ('Musterweg 1', '70191', '+49 711 000000'))
        self.assertTrue(p['website'].startswith('https://'))
        self.assertNotIn('email', p)
        self.assertNotIn('Max Beispiel', json.dumps(p, ensure_ascii=False))
        self.assertIsNone(osm_local.place_from_tags('node', 2, {'name': 'Familie Beispiel', 'addr:street': 'Wohnweg'}, 48.8, 9.17))  # reine Adresse
        self.assertEqual(osm_local.place_from_tags('node', 3, {'name': 'X GmbH', 'office': 'company', 'addr:postcode': '7019'}, None, None)['zip'], '')


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / 'o.sqlite3'))
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def write(self, name, content):
        p = Path(self.tmp.name) / name
        p.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode('utf-8'))
        return p

    def test_pbf_import_and_reimport_does_not_duplicate(self):
        r = osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        self.assertEqual((r['status'], r['kind'], r['places']), ('fertig', 'pbf', 6))
        osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        st = osm_local.status(self.conn)
        self.assertEqual((st['places'], st['with_phone'], st['with_hours'], len(st['imports'])), (6, 1, 1, 2))
        self.assertIn('ODbL', st['license'])

    def test_building_outlines_get_a_location_from_their_first_point(self):
        r = osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        self.assertEqual(r['ways_located'], 1)
        row = self.conn.execute("SELECT lat, lon FROM osm_places WHERE osm_id='way/5001'").fetchone()
        self.assertAlmostEqual(row['lat'], 48.01, places=5)  # Knoten 1000 der Testdatei
        self.assertAlmostEqual(row['lon'], 9.01, places=5)
        self.assertEqual(osm_local.status(self.conn)['without_location'], 0)

    def test_missing_postcode_is_guessed_only_from_close_neighbours(self):
        r = osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        self.assertEqual(r['postcodes_guessed'], 1)
        got = dict(self.conn.execute("SELECT name, zip_guess FROM osm_places WHERE zip=''").fetchall())
        self.assertEqual(got['Malerbetrieb Beispiel'], '70191')  # 170 m neben einem Betrieb mit PLZ
        self.assertEqual(got['Südhalbkugel Test'], '')           # kein Nachbar in 250 m – bleibt unbekannt
        # die eigene Angabe wird nie überschrieben, und ein weit entfernter Nachbar zählt nicht
        self.conn.execute("INSERT INTO osm_places(osm_id, name, kind_key, kind, lat, lon, import_id) VALUES ('node/900', 'Weit weg GmbH', 'office', 'company', 48.81, 9.19, 1)")
        osm_local.guess_postcodes(self.conn)
        self.assertEqual(self.conn.execute("SELECT zip_guess FROM osm_places WHERE osm_id='node/900'").fetchone()[0], '')
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM osm_places WHERE zip<>'' AND zip_guess<>''").fetchone()[0], 0)

    def test_overpass_json_and_geojson(self):
        r = osm_local.import_file(self.conn, self.write('export.json', OVERPASS), 'export.json')
        self.assertEqual((r['status'], r['kind'], r['places']), ('fertig', 'json', 2))
        row = self.conn.execute("SELECT lat, lon FROM osm_places WHERE osm_id='way/202'").fetchone()
        self.assertAlmostEqual(row['lat'], 48.8002)  # Mittelpunkt des Umrisses
        geo = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'id': 'node/301', 'properties': {'@id': 'node/301', 'name': 'Dach Fiktiv GmbH', 'craft': 'roofer'},
                                                         'geometry': {'type': 'Point', 'coordinates': [9.18, 48.81]}}]}
        r = osm_local.import_file(self.conn, self.write('export.geojson', geo), 'export.geojson')
        self.assertEqual(r['places'], 1)
        row = self.conn.execute("SELECT lat, lon, kind FROM osm_places WHERE osm_id='node/301'").fetchone()
        self.assertEqual((row['lat'], row['lon'], row['kind']), (48.81, 9.18, 'roofer'))

    def test_broken_and_foreign_files_fail_cleanly(self):
        for name, content, expect in (('kaputt.osm.pbf', PBF.read_bytes()[:400], 'fehler'), ('muell.osm.pbf', b'\x00\x00\x00\x05abcde' * 30, 'fehler'),
                                      ('leer.json', b'{"x": 1}', 'fehler'), ('kein.json', b'{nicht json', 'fehler')):
            r = osm_local.import_file(self.conn, self.write(name, content), name)
            self.assertEqual(r['status'], expect, name)
            self.assertTrue(r['error'], name)
        with self.assertRaises(ValueError):
            osm_local.import_file(self.conn, self.write('bild.png', b'\x89PNG....'), 'bild.png')
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM osm_imports WHERE status='fehler'").fetchone()[0], 4)


class SearchTests(tb.SweepBase):
    def local(self, **params):
        return self.run_sweep(sources=['osm'], osm_online=False, include_sole=True, **params)

    def overpass_calls(self):
        return [c for c in self.net.calls if 'overpass' in c or 'interpreter' in c]

    def test_without_extract_osm_is_manual_and_no_server_is_called(self):
        d = self.local(place='70191', radius_km=0)
        self.assertEqual(self.overpass_calls(), [])
        self.assertIn('läuft manuell', d['progress']['osm']['detail'])
        self.assertEqual(self.cands(), [])

    def test_postcode_only_from_local_extract_without_network(self):
        osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        d = self.local(place='70191', radius_km=0)
        self.assertEqual(self.overpass_calls(), [])
        names = {c['name'] for c in self.cands()}
        # PLZ 70191 laut Eintrag – plus der Malerbetrieb ohne PLZ-Angabe, der 170 m neben einem Betrieb in 70191 liegt (dev8)
        self.assertEqual(names, {'Elektro Fiktiv GmbH', 'Bäckerei Ähre & Söhne', 'Autohaus Muster GmbH', 'Malerbetrieb Beispiel'})
        self.assertNotIn('Schreinerei Fern GmbH', names)  # andere PLZ
        self.assertIn('lokalen Auszug', d['progress']['osm']['detail'])
        self.assertIn('1 ohne PLZ-Angabe', d['progress']['osm']['detail'])
        self.assertIn('Schätzung', d['progress']['osm']['detail'])

    def test_whole_town_covers_all_its_postcodes(self):
        from sales_tool import gemeinden as gm
        gm._STATE['rows'] = None  # echtes Ortsverzeichnis: Stuttgart mit allen PLZ
        osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        self.local(place='Stuttgart', radius_km=0)
        names = {c['name'] for c in self.cands()}
        self.assertIn('Schreinerei Fern GmbH', names)   # andere PLZ derselben Stadt (70565)
        self.assertIn('Elektro Fiktiv GmbH', names)
        self.assertIn('Autohaus Muster GmbH', names)    # Gebäudeumriss ohne Koordinaten, über Ort/PLZ
        self.assertIn('Malerbetrieb Beispiel', names)   # ohne Adresse, aber nahe der Ortsmitte
        self.assertNotIn('Südhalbkugel Test', names)

    def test_radius_and_industry_filter(self):
        from sales_tool import gemeinden as gm
        gm._STATE['rows'] = None
        osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        self.local(place='70191', radius_km=20, industries=['elektro'])
        self.assertEqual({c['name'] for c in self.cands()}, {'Elektro Fiktiv GmbH'})

    def test_online_query_only_on_request(self):
        osm_local.import_file(self.conn, PBF, 'beispiel.osm.pbf')
        self.run_sweep(sources=['osm'], osm_online=True, industries=['elektro'])
        self.assertTrue(self.overpass_calls())


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

    def call(self, method, path, body=None, ctype='application/json'):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=20)
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        c.request(method, path, data, {'Content-Type': ctype} if data is not None else {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, json.loads(raw) if raw else None

    def test_status_howto_and_turbo_link(self):
        st, d = self.call('GET', '/api/osm?place=70191&radius=0')
        self.assertEqual((st, d['places']), (200, 0))
        self.assertEqual([h['key'] for h in d['howto']], ['auszug', 'turbo', 'online'])
        self.assertIn('"postal_code"="70191"', d['turbo']['query'])
        self.assertTrue(d['turbo']['url'].startswith('https://overpass-turbo.eu/?Q='))
        _, d = self.call('GET', '/api/osm?place=Stuttgart&radius=0')
        self.assertIn('"name"="Stuttgart"', d['turbo']['query'])

    def test_upload_runs_as_job_and_fills_local_data(self):
        st, d = self.call('POST', '/api/osm/upload?filename=beispiel.osm.pbf', PBF.read_bytes(), 'application/octet-stream')
        self.assertEqual(st, 202)
        self.assertTrue(jobs.wait_idle(self.db, timeout=30, kinds=['osm_import']))
        deadline = time.time() + 10
        while time.time() < deadline and self.call('GET', '/api/osm')[1]['places'] < 6:
            time.sleep(0.1)
        _, s = self.call('GET', '/api/osm')
        self.assertEqual((s['places'], s['imports'][0]['status']), (6, 'fertig'))
        self.assertEqual(self.call('POST', '/api/osm/upload?filename=bild.png', b'\x89PNG', 'application/octet-stream')[0], 400)
        self.assertEqual(self.call('DELETE', '/api/osm/places')[1]['deleted'], 6)


if __name__ == '__main__':
    unittest.main()
