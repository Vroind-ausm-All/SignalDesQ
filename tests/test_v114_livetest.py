"""v1.14 – Befunde aus dem Live-Test der Quellen (11/2026), als Attrappen nachgestellt.

Die Attrappen spiegeln die echten Antworten, die der Live-Test geliefert hat:
- Wikidata: HTTP 429 „Aggressively rate-limiting to 1 req / min – this rule was created during active wdqs outage“, Retry-After 1000.
- GLEIF: Ortsfilter (entity.legalAddress.city/postalCode) → HTTP 400; erlaubt sind nur fulltext, country, status, category.
  Datensätze tragen den Rechtsform-Code (ELF) und Ortsteile wie „Stuttgart - Möhringen“.
- TED: Felder buyer-city {'mul': [...]}, buyer-post-code [...]; serverseitiger Filter „buyer-city IN (…)“.
- Overpass: Verbindung wird sofort abgebrochen (aus Rechenzentren) – Server muss übersprungen werden.
Es laufen keine echten Netzwerkabfragen.
"""
import io
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from sales_tool import area as ar
from sales_tool import gemeinden as gm
from sales_tool import lead_finder as lf
from sales_tool import legal_forms as lfm
from sales_tool import source_check as sc
from sales_tool import sweep as sw
from sales_tool.model import connect, init_db

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402

GEM_ROWS = [  # Auswahl im Format von data/gemeinden_de.json (Name, Kreis, lat, lon, Anzahl PLZ, PLZ)
    ['Stuttgart', '08111', 48.7683, 9.1861, 35, '70173,70174,70176,70565,70629'],
    ['Esslingen am Neckar', '08116', 48.7454, 9.3083, 5, '73728,73730,73732,73733,73734'],
    ['Ludwigsburg', '08118', 48.8976, 9.1955, 5, '71634,71636,71638,71640,71642'],
    ['Neustadt an der Weinstraße', '07316', 49.3512, 8.1411, 3, '67433,67434,67435'],
    ['Neustadt bei Coburg', '09473', 50.3297, 11.1211, 1, '96465'],
    ['Ulm', '08421', 48.4011, 9.9876, 7, '89073-89081'],
]


class Fixture:
    def __init__(self, rows=GEM_ROWS):
        self.rows = rows

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'gem.json'
        path.write_text(json.dumps({'source': 'Test', 'license': 'CC0', 'rows': self.rows}, ensure_ascii=False), encoding='utf-8')
        self.p = mock.patch.object(gm, 'DATA', path)
        self.p.start()
        gm._STATE['rows'] = None
        return self

    def __exit__(self, *a):
        self.p.stop()
        gm._STATE['rows'] = None
        self.tmp.cleanup()


class GemeindenTests(unittest.TestCase):
    def test_lookup_by_postcode_name_and_radius(self):
        with Fixture():
            self.assertEqual(gm.by_postcode('70173')['name'], 'Stuttgart')
            self.assertEqual(gm.by_postcode('96465')['name'], 'Neustadt bei Coburg')
            self.assertIsNone(gm.by_postcode('12345'))
            self.assertEqual(gm.by_name('esslingen am neckar')['kreis'], '08116')
            self.assertEqual(gm.by_name('Esslingen')['name'], 'Esslingen am Neckar', 'Kurzform')
            self.assertEqual(gm.by_name('Neustadt', '96465')['name'], 'Neustadt bei Coburg', 'gleichnamige Orte über PLZ unterschieden')
            near = {p['name']: p['distance_km'] for p in gm.within(48.7683, 9.1861, 30)}
            self.assertEqual(set(near), {'Stuttgart', 'Esslingen am Neckar', 'Ludwigsburg'})
            self.assertLess(near['Esslingen am Neckar'], 12)

    def test_bundled_file_is_valid(self):
        gm._STATE['rows'] = None
        if not gm.DATA.exists():
            self.skipTest('Gemeindeverzeichnis nicht mitgeliefert')
        meta = gm.meta()
        self.assertGreater(meta['count'], 10000, 'alle deutschen Orte')
        self.assertIn('CC BY 4.0', meta['license'])
        self.assertIn('GeoNames', meta['license'])
        self.assertEqual(gm.by_postcode('70173')['name'], 'Stuttgart')
        self.assertTrue(30 < len(gm.within(48.7683, 9.1861, 30)) < 600)
        gm._STATE['rows'] = None


class OfflineAreaTests(tb.SweepBase):
    def test_area_without_network(self):
        with Fixture():
            a = ar.resolve(self.conn, '70173', 30)
            self.assertIn('Ortsverzeichnis offline', a['source'])
            self.assertEqual([p['name'] for p in a['places']][0], 'Stuttgart')
            self.assertIn('Esslingen am Neckar', [p['name'] for p in a['places']])
            self.assertFalse(self.net.calls, 'weder Nominatim noch Wikidata/OSM gefragt')
            zero = ar.resolve(self.conn, 'Stuttgart', 0)
            self.assertEqual([p['name'] for p in zero['places']], ['Stuttgart'])
            ar.resolve(self.conn, '01067', 10)  # unbekannte PLZ → Rückfall auf Nominatim
            self.assertTrue(any('nominatim' in c for c in self.net.calls))

    def test_center_only_fallback_is_not_cached(self):
        self.net.fail.add('wikidata')
        self.net.fail.add('osm_main')
        with mock.patch.object(lf, 'OVERPASS_SERVERS', ('https://overpass-api.de/api/interpreter',)):
            a = ar.resolve(self.conn, 'Stuttgart', 10)
        self.assertEqual(a['source'], 'nur Mittelpunkt')
        self.net.fail.clear()
        b = ar.resolve(self.conn, 'Stuttgart', 10)
        self.assertFalse(b['cached'], 'Notlösung wurde nicht gespeichert')
        self.assertEqual(b['source'], 'Wikidata')


class WikidataThrottleTests(unittest.TestCase):
    def setUp(self):
        lf.wikidata_reset()
        self.now = [1000.0]
        self.sleeps = []
        self.p = [mock.patch.object(lf, 'CLOCK', lambda: self.now[0]), mock.patch.object(lf, 'SLEEP', self.sleep)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        lf.wikidata_reset()

    def sleep(self, s):
        self.sleeps.append(round(s, 1))
        self.now[0] += s

    def test_outage_429_blocks_and_slows_down(self):
        calls = []

        def fetch(url, ua, **kw):
            calls.append(url)
            if len(calls) == 1:
                err = lf.SourceError('Die Quelle meldet zu viele Anfragen (HTTP 429) – sie ist gerade gestört und erlaubt nur 1 Anfrage pro Minute.', retry_after=1000)
                err.outage = True
                raise err
            return {'results': {'bindings': [{'x': {'value': '1'}}]}}
        with mock.patch.object(lf, 'FETCH', fetch):
            with self.assertRaises(lf.SourceError) as ctx:
                lf.wikidata_sparql('SELECT 1', 'ua')
            self.assertFalse(ctx.exception.retryable, '1000 s Sperre: in der Suche nicht sinnlos warten')
            self.assertIn('17 min', str(ctx.exception))
            self.assertEqual(len(calls), 1, 'kein sofortiger Wiederholversuch nach 429')
            with self.assertRaises(lf.SourceError):
                lf.wikidata_sparql('SELECT 1', 'ua')
            self.assertEqual(len(calls), 1, 'während der Sperre gar nicht erst anfragen')
            self.assertTrue(lf.wikidata_status()['blocked_s'] > 900)
            self.now[0] += 1001
            lf.wikidata_sparql('SELECT 1', 'ua')
            lf.wikidata_sparql('SELECT 2', 'ua')
        self.assertIn(65.0, self.sleeps, 'im Störungsmodus 65 s Abstand zwischen Anfragen')
        self.assertTrue(lf.wikidata_status()['slow'])

    def test_normal_gap_and_post_for_long_queries(self):
        seen = []
        with mock.patch.object(lf, 'FETCH', lambda url, ua, **kw: seen.append((url, kw.get('data'))) or {'results': {'bindings': []}}):
            lf.wikidata_sparql('SELECT 1', 'ua')
            lf.wikidata_sparql('SELECT ?lei WHERE { VALUES ?lei { ' + ' '.join(f'"{i:020d}"' for i in range(400)) + ' } }', 'ua')
        self.assertEqual(self.sleeps, [2.0], 'normaler Mindestabstand 2 s')
        self.assertIsNone(seen[0][1])
        self.assertEqual(seen[1][0], 'https://query.wikidata.org/sparql', 'lange Abfrage per POST')
        self.assertIn(b'query=', seen[1][1])

    def test_http_429_detects_outage_text(self):
        body = b'<html><p>Error: 429, Aggressively rate-limiting to 1 req / min - this rule was created during active wdqs outage</p></html>'
        err = urllib.error.HTTPError('https://query.wikidata.org/sparql', 429, 'Too Many Requests', {'Retry-After': '1000'}, io.BytesIO(body))
        with mock.patch('urllib.request.urlopen', side_effect=err):
            with self.assertRaises(lf.SourceError) as ctx:
                lf._http('https://query.wikidata.org/sparql', 'ua')
        self.assertTrue(ctx.exception.outage)
        self.assertEqual(ctx.exception.retry_after, 1000)
        self.assertIn('1 Anfrage pro Minute', str(ctx.exception))


class GleifLiveFormatTests(unittest.TestCase):
    def rec(self, name, city, elf, lines=('Königstraße 7', '70173 Stuttgart')):
        return {'id': 'X' * 20, 'attributes': {'lei': 'X' * 20, 'registration': {}, 'entity': {
            'legalName': {'name': name}, 'status': 'ACTIVE', 'category': 'GENERAL', 'legalForm': {'id': elf},
            'legalAddress': {'addressLines': list(lines), 'postalCode': '70567', 'city': city, 'country': 'DE'}}}}

    def test_districts_elf_and_street(self):
        data = {'data': [self.rec('Muster Technik GmbH', 'Stuttgart - Möhringen', '2HBR'),
                         self.rec('Stuttgarter Studentenwerk e.V.', 'Stuttgart', 'QZ3L'),
                         self.rec('IHK Region Stuttgart', 'Stuttgart', 'SQKS'),
                         self.rec('Stuttgarter Hof GmbH', 'Köln', '2HBR')]}
        items = {i['name']: i for i in lf.gleif_items(data, city='Stuttgart')}
        self.assertEqual(set(items), {'Muster Technik GmbH', 'Stuttgarter Studentenwerk e.V.', 'IHK Region Stuttgart'}, 'Ortsteil ja, Köln nein')
        self.assertEqual((items['Muster Technik GmbH']['legal_form'], items['Muster Technik GmbH']['org_kind']), ('GmbH', 'unternehmen'))
        self.assertEqual(items['Stuttgarter Studentenwerk e.V.']['org_kind'], 'verein')
        self.assertEqual(items['IHK Region Stuttgart']['org_kind'], 'oeffentlich')
        self.assertEqual(items['Muster Technik GmbH']['street'], 'Königstraße 7', 'PLZ-Zeile nicht in der Straße')

    def test_legal_form_regex_no_false_group(self):
        self.assertEqual(lf.legal_form_of('Interessengemeinschaft deutscher akademischer Fliegergruppen e.V.'), 'e.V.')
        self.assertEqual(lf.legal_form_of('Gruppe Nord'), '', '„Gruppe“ ist keine Rechtsform')
        self.assertEqual(lf.legal_form_of('Muster Holding'), '')
        self.assertEqual(lf.legal_form_of('Bäckerei Kornfeld e.K.'), 'e.K.')

    def test_all_german_elf_codes(self):
        self.assertEqual(len(lfm.ELF_DE), 31)
        self.assertEqual(lfm.from_elf('2hbr'), ('GmbH', 'unternehmen'))
        self.assertIsNone(lfm.from_elf('8888'), '„nicht gelistet“ → über den Namen bestimmen')
        self.assertEqual(lfm.kind_of('Ev. Kirchengemeinde Stuttgart-Stammheim', '8888'), 'oeffentlich')
        self.assertEqual(lfm.kind_of('Grub-Stiftung', '8888'), 'verein')


class NonOperativeLiveTests(unittest.TestCase):
    def test_patterns_from_live_gleif_stuttgart(self):
        from sales_tool import industries as ind
        drop = ['Frida Grundbesitz GmbH', '2V Besitz-GmbH', 'AVL Besitzgesellschaft mbh', 'SWS Windpark Lieskau II GmbH & Co. KG',
                'Solarpark Zernitz GmbH & Co. KG', 'EKK & Co. III Management GmbH', 'KOEHLER Real Estate XIII GmbH', 'Lenz VV KG',
                'DFH Stuttgart GmbH & Co. Nr. 90 KG', 'Mätch.vc Fund I GmbH & Co. KG']
        keep = ['0711 Digital GmbH', 'Studio 3 GmbH', 'Hotel 1 Stuttgart GmbH', 'Werwigk Immobilien KG', 'Motor Presse Stuttgart GmbH & Co. KG',
                'Event Management GmbH', '3am Studio GmbH']
        self.assertEqual([n for n in drop if not ind.NON_OPERATIVE_RE.search(n)], [])
        self.assertEqual([n for n in keep if ind.NON_OPERATIVE_RE.search(n)], [])


class OrgKindSweepTests(tb.SweepBase):
    def test_default_only_companies_option_for_others(self):
        recs = [tb.gleif_record('V' * 18 + '20', 'Turnverein Muster e.V.', 'Stuttgart', '70173'),
                tb.gleif_record('K' * 18 + '21', 'Handwerkskammer Muster', 'Stuttgart', '70173')]
        recs[0]['attributes']['entity']['legalForm'] = {'id': 'QZ3L'}
        recs[1]['attributes']['entity']['legalForm'] = {'id': 'SQKS'}
        orig = self.net.__call__

        def fetch(url, ua, data=None, **kw):
            out = orig(url, ua, data, **kw)
            if 'gleif' in url and out.get('data'):
                out['data'] = out['data'] + recs
            return out
        lf.FETCH = fetch
        d = self.run_sweep(sources=['gleif'], radius_km=0)
        names = {c['name'] for c in self.cands()}
        self.assertNotIn('Turnverein Muster e.V.', names)
        self.assertNotIn('Handwerkskammer Muster', names)
        self.assertGreaterEqual(d['progress']['gleif']['filtered'], 2)
        self.run_sweep(sources=['gleif'], radius_km=0, org_kinds=['unternehmen', 'verein', 'oeffentlich'])
        cs = {c['name']: c for c in self.cands()}
        lead_id = sw.decide(self.conn, cs['Reith Spezialkabel GmbH']['id'], 'uebernehmen')['lead_id']
        self.assertEqual(self.conn.execute('SELECT legal_form FROM leads WHERE id=?', (lead_id,)).fetchone()[0], 'GmbH',
                         'Live-Test: Rechtsform kam bisher nicht im Lead an')
        self.assertEqual(cs['Turnverein Muster e.V.']['org_kind'], 'verein')
        self.assertEqual(cs['Handwerkskammer Muster']['org_kind'], 'oeffentlich')
        with self.assertRaises(ValueError):
            sw.validate_params({'place': 'Stuttgart', 'org_kinds': []})
        with self.assertRaises(ValueError):
            sw.validate_params({'place': 'Stuttgart', 'org_kinds': ['personen']})


class LeiOrderTests(tb.SweepBase):
    def test_company_query_first_lei_lookup_last_with_gap(self):
        sleeps = []
        lf.SLEEP = sleeps.append
        d = self.run_sweep(sources=['gleif', 'wikidata'])
        wd = [c for c in self.net.calls if 'wikidata' in c]
        self.assertTrue(wd, 'Wikidata gefragt')
        self.assertNotIn('VALUES', urllib.parse.unquote_plus(wd[0]), 'zuerst die Firmenabfrage, nicht die LEI-Ergänzung')
        self.assertTrue(any(s >= 60 for s in sleeps), 'LEI-Ergänzung erst mit ≥ 65 s Abstand (Live-Befund: 2. Anfrage pro Minute → Sperre)')
        self.assertIn('Websites über Wikidata (LEI)', d['progress']['gleif']['detail'])
        self.assertEqual(next(c for c in self.cands() if c['name'].startswith('Neckar'))['website'], 'https://www.neckar-praezision.example')


class TedRegionalTests(tb.SweepBase):
    def test_regional_by_default_nationwide_optional(self):
        d = self.run_sweep(sources=['ted'])
        names = {c['name']: c for c in self.cands()}
        self.assertIn('Stadtwerke Beispielstadt', names)
        self.assertNotIn('Hafenamt Musterhafen', names, 'Hamburg liegt nicht im Suchgebiet')
        self.assertEqual((names['Stadtwerke Beispielstadt']['city'], names['Stadtwerke Beispielstadt']['zip']), ('Stuttgart', '70173'))
        self.assertIsNotNone(names['Stadtwerke Beispielstadt']['distance_km'])
        self.assertIn('Suchgebiet', d['progress']['ted']['detail'])
        ted_call = next(c for c in self.net.calls if 'ted.europa.eu' in c)
        self.assertTrue(ted_call)
        self.run_sweep(sources=['ted'], ted_nationwide=True)
        self.assertIn('Hafenamt Musterhafen', {c['name'] for c in self.cands()})

    def test_query_and_joint_procurement_city(self):
        q = lf.ted_query(['72413000'], '2026-08-01', ['Stuttgart', 'Esslingen am Neckar', 'Böse"Stadt'])
        self.assertIn('buyer-city IN ("Stuttgart" "Esslingen am Neckar" "BöseStadt")', q)
        place = lf._ted_place({'buyer-city': {'mul': ['Berlin', 'Stuttgart', 'München']}, 'buyer-post-code': ['10178', '70191', '81739']}, ['Stuttgart'])
        self.assertEqual(place, {'city': 'Stuttgart', 'zip': '70191'}, 'gemeinsame Beschaffung: Ort aus dem Suchgebiet')


class OverpassSkipTests(unittest.TestCase):
    def setUp(self):
        lf.wikidata_reset()

    def tearDown(self):
        lf.wikidata_reset()

    def test_unreachable_server_skipped_for_ten_minutes(self):
        calls = []

        def fetch(url, ua, **kw):
            calls.append(url)
            if 'overpass-api.de' in url:
                raise lf.SourceError('Quelle nicht erreichbar (Connection reset by peer). Internetverbindung/Firewall prüfen.')
            return {'elements': []}
        with mock.patch.object(lf, 'FETCH', fetch):
            lf.overpass('[out:json];node(1);out;', 'ua')
            lf.overpass('[out:json];node(1);out;', 'ua')
        self.assertEqual(sum('overpass-api.de' in c for c in calls), 1, 'toter Server nur einmal versucht')
        self.assertEqual(lf.OVERPASS_TIMEOUT, 45)

    def test_all_unreachable_fails_fast_without_retry(self):
        calls = []

        def fetch(url, ua, **kw):
            calls.append(url)
            raise lf.SourceError('Quelle nicht erreichbar (The read operation timed out). Internetverbindung/Firewall prüfen.')
        with mock.patch.object(lf, 'FETCH', fetch):
            with self.assertRaises(lf.SourceError) as first:
                lf.overpass('q', 'ua')
            self.assertFalse(first.exception.retryable, 'kein Server antwortet: in der Suche nicht sinnlos warten')
            with self.assertRaises(lf.SourceError) as second:
                lf.overpass('q', 'ua')
        self.assertEqual(len(calls), 3, 'zweiter Aufruf fragt keinen Server mehr')
        self.assertIn('übersprungen', str(second.exception))


class SourceCheckTests(unittest.TestCase):
    def setUp(self):
        lf.wikidata_reset()
        sc._LAST.update(at=0.0, result=None)
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / 'c.sqlite3')
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()
        sc._LAST.update(at=0.0, result=None)
        lf.wikidata_reset()

    def test_statuses(self):
        def fetch(url, ua, data=None, **kw):
            if 'gleif' in url:
                return {'data': [{'attributes': {'entity': {'legalName': {'name': 'A GmbH'}, 'legalAddress': {'city': 'Stuttgart'}, 'legalForm': {'id': '2HBR'}}}}],
                        'meta': {'pagination': {'total': 3404}}}
            if 'wikidata' in url:
                raise lf.SourceError('Die Quelle meldet zu viele Anfragen (HTTP 429).', retry_after=60)
            if 'nominatim' in url:
                return [{'lat': '48.78', 'lon': '9.18'}]
            if 'overpass-api.de' in url:
                raise lf.SourceError('Quelle nicht erreichbar (Connection reset by peer).')
            if 'interpreter' in url:
                raise lf.SourceError('Quelle antwortet mit HTTP 504: Gateway Timeout')
            if 'ted' in url:
                return {'notices': [{'publication-number': '1-2026', 'buyer-name': {'deu': ['X']}}], 'totalNoticeCount': 5}
            raise AssertionError(url)
        with mock.patch.object(lf, 'FETCH', fetch):
            r = sc.run_check(self.conn)
            again = sc.run_check(self.conn)
        st = {x['key']: x['status'] for x in r['rows']}
        self.assertEqual(st['gleif'], 'ok')
        self.assertEqual(st['wikidata'], 'ueberlastet')
        self.assertEqual(st['nominatim'], 'ok')
        self.assertEqual(st['osm1'], 'blockiert')
        self.assertEqual(st['osm2'], 'ueberlastet')
        self.assertEqual(st['ted'], 'format', 'buyer-city fehlt → Adapter prüfen')
        self.assertFalse(r['osm_any'])
        self.assertTrue(again['cached'], 'höchstens eine Prüfung pro Minute')
        self.assertIn('3404', next(x for x in r['rows'] if x['key'] == 'gleif')['detail'])


class V114HttpTests(tb.SweepHttpTests):
    def test_endpoints(self):
        sc._LAST.update(at=0.0, result=None)
        with mock.patch.object(sc, 'run_check', lambda conn: {'rows': [], 'ok': 0, 'total': 0, 'cached': False}):
            status, r = self.call('/api/sources/check', 'POST', {'run': True})
            self.assertEqual(self.call('/api/sources/check', 'POST', {})[0], 400, 'ohne ausdrücklichen Auftrag keine Netzabfrage')
        self.assertEqual((status, r['total']), (200, 0))
        self.assertEqual(self.call('/api/sources/check')[0], 404, 'nur POST (löst echte Anfragen aus)')
        status, s = self.call('/api/sweeps', 'POST', {'place': 'Stuttgart', 'radius_km': 0, 'sources': ['gleif'], 'org_kinds': ['unternehmen', 'verein'],
                                                     'ted_nationwide': False, 'find_websites': False})
        self.assertEqual(status, 202)
        sw._THREADS[s['id']].join(30)
        self.assertEqual(self.call('/api/sweeps', 'POST', {'place': 'Stuttgart', 'org_kinds': ['alle']})[0], 400)


if __name__ == '__main__':
    unittest.main()
