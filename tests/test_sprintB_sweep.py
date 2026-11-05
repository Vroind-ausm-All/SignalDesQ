"""Sprint B – Sammelsuche, Suchgebiet, Quellen-Reparatur, großer Import, Dubletten, Website-Suche mit Nachweis.

Alle Netzwerkantworten sind Attrappen mit fiktiven Firmen. Die echten Fehlerbilder des Nutzers werden nachgestellt:
GLEIF „HTTP 400 Filter should contain only allowed values“, Wikidata „HTTP 502“, OpenStreetMap „timed out“.
"""
import json
import tempfile
import threading
import unittest
import urllib.parse
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from sales_tool import area as ar
from sales_tool import imprint
from sales_tool import industries as ind
from sales_tool import lead_finder as lf
from sales_tool import sweep as sw
from sales_tool.company_data import add_suppression
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

LEI_A, LEI_B, LEI_C = 'A' * 18 + '01', 'B' * 18 + '02', 'C' * 18 + '03'


def gleif_record(lei, name, city, zip_, register='', status='ACTIVE', category='GENERAL'):
    return {'id': lei, 'attributes': {'lei': lei, 'entity': {'legalName': {'name': name}, 'status': status, 'category': category,
            'legalAddress': {'addressLines': ['Industriestraße 1'], 'postalCode': zip_, 'city': city, 'country': 'DE'},
            'registeredAs': register}, 'registration': {'initialRegistrationDate': '2019-05-01T00:00:00Z'}}}


class FakeNet:
    """Leitet Anfragen nach URL an Antworten weiter und zählt sie."""
    def __init__(self):
        self.calls = []
        self.fail = set()

    def __call__(self, url, ua, data=None, content_type=None, accept='application/json', timeout=None):
        self.calls.append(url)
        body = urllib.parse.unquote_plus((data or b'').decode()) if data else ''
        if 'nominatim' in url:
            return [{'lat': '48.7758', 'lon': '9.1829', 'address': {'postcode': '70173', 'city': 'Stuttgart'}}]
        if 'gleif' in url:
            if 'gleif' in self.fail:
                raise lf.SourceError('Quelle nicht erreichbar (The read operation timed out).')
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            if 'filter[entity.status]' in q:  # Fehlerbild des Nutzers
                raise lf.SourceError('Quelle antwortet mit HTTP 400: {"errors":[{"title":"Filter should contain only allowed values.","source":{"parameter":"filter"}}]}')
            city = q.get('filter[entity.legalAddress.city]', [''])[0]
            recs = {'Stuttgart': [gleif_record(LEI_A, 'Reith Spezialkabel GmbH', 'Stuttgart', '70173', 'HRB 14671'),
                                  gleif_record(LEI_B, 'Kesselwerk Verwaltungs GmbH', 'Stuttgart', '70174', 'HRB 999'),
                                  gleif_record('D' * 18 + '04', 'Alt GmbH', 'Stuttgart', '70175', status='INACTIVE'),
                                  gleif_record('E' * 18 + '05', 'Rentenfonds Süd', 'Stuttgart', '70176', category='FUND'),
                                  gleif_record('F' * 18 + '06', 'Gesperrte Muster AG', 'Stuttgart', '70176', 'HRB 555')],
                    'Esslingen am Neckar': [gleif_record(LEI_C, 'Neckar Präzisionsteile GmbH', 'Esslingen am Neckar', '73728', 'HRB 7300')]}.get(city, [])
            return {'data': recs, 'meta': {'pagination': {'lastPage': 1}}}
        if 'wikidata' in url:
            if 'wikidata' in self.fail:
                raise lf.SourceError('Quelle antwortet mit HTTP 502: 502 Bad Gateway nginx/1.22.1')
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['query'][0]
            if 'Q262166' in q:
                pts = [('Stuttgart', 9.1829, 48.7758, 630000), ('Esslingen am Neckar', 9.3071, 48.7406, 94000), ('Ulm', 9.9876, 48.4011, 126000)]
                return {'results': {'bindings': [{'place': {'value': 'x'}, 'placeLabel': {'value': n}, 'pop': {'value': str(p)},
                                                  'coord': {'value': f'Point({lo} {la})'}} for n, lo, la, p in pts]}}
            if 'VALUES ?lei' in q:
                return {'results': {'bindings': [{'lei': {'value': LEI_C}, 'website': {'value': 'https://www.neckar-praezision.example/'}}]}}
            return {'results': {'bindings': [
                {'company': {'value': 'http://www.wikidata.org/entity/Q1'}, 'companyLabel': {'value': 'Reith Spezialkabel GmbH'},
                 'website': {'value': 'https://reith-kabel.example'}, 'lei': {'value': LEI_A}, 'coord': {'value': 'Point(9.18 48.77)'},
                 'placeLabel': {'value': 'Stuttgart'}, 'employees': {'value': '85'}},
                {'company': {'value': 'http://www.wikidata.org/entity/Q2'}, 'companyLabel': {'value': 'Hanna Beispiel'},
                 'coord': {'value': 'Point(9.18 48.77)'}, 'placeLabel': {'value': 'Stuttgart'}},
                {'company': {'value': 'http://www.wikidata.org/entity/Q3'}, 'companyLabel': {'value': 'Q3'}}]}}
        if 'overpass' in url or 'interpreter' in url:
            if 'overpass-api.de' in url and 'osm_main' in self.fail:
                raise lf.SourceError('Quelle nicht erreichbar (The read operation timed out). Internetverbindung/Firewall prüfen.')
            if 'node["place"' in body:
                return {'elements': []}
            return {'elements': [
                {'type': 'node', 'id': 1, 'lat': 48.78, 'lon': 9.17, 'tags': {'name': 'Elektro Sommer GmbH', 'craft': 'electrician', 'website': 'https://elektro-sommer.example',
                                                                         'addr:city': 'Stuttgart', 'addr:postcode': '70178'}},
                {'type': 'node', 'id': 2, 'lat': 48.79, 'lon': 9.19, 'tags': {'name': 'Bäckerei Kornfeld', 'shop': 'bakery'}},
                {'type': 'node', 'id': 3, 'lat': 48.70, 'lon': 9.10, 'tags': {'name': 'Bestandskunde Werkzeugbau GmbH', 'craft': 'metal_construction', 'website': 'https://bestand.example'}}]}
        if 'ted.europa.eu' in url:
            if 'ted' in self.fail:
                raise lf.SourceError('Quelle antwortet mit HTTP 503: Wartung')
            return {'notices': [{'publication-number': '123-2026', 'notice-title': {'deu': 'Relaunch Website Stadtwerke'}, 'buyer-name': {'deu': ['Stadtwerke Beispielstadt']},
                                 'publication-date': ['2026-11-01'], 'links': {}}]}
        raise AssertionError('unerwartete URL ' + url)


class SweepBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'sw.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.net = FakeNet()
        self._orig = (lf.FETCH, lf.SLEEP, sw.GLEIF_DELAY)
        lf.FETCH, lf.SLEEP, sw.GLEIF_DELAY = self.net, (lambda s: None), 0

    def tearDown(self):
        lf.FETCH, lf.SLEEP, sw.GLEIF_DELAY = self._orig
        self.conn.close()
        self.tmp.cleanup()

    def run_sweep(self, **params):
        p = {'place': '70173', 'radius_km': 30, **params}
        s = sw.start_sweep(self.conn, p, self.db, start=False)
        sw.run_sweep(self.db, s['id'])
        return sw.sweep_detail(self.conn, s['id'])

    def cands(self, **q):
        return sw.candidates(self.conn, {k: [v] for k, v in {'status': 'alle', **q}.items()})['items']


class SourceRepairTests(SweepBase):
    def test_gleif_falls_back_when_filter_rejected(self):
        data = lf.gleif_page('ua', city='Stuttgart')
        self.assertEqual(data['_attempt'], 1, 'ohne Status-Filter erneut gefragt')
        items = lf.gleif_items(data, city='Stuttgart')
        names = [i['name'] for i in items]
        self.assertIn('Reith Spezialkabel GmbH', names)
        self.assertNotIn('Alt GmbH', names, 'Inaktive lokal gefiltert')
        self.assertNotIn('Rentenfonds Süd', names, 'Fonds lokal gefiltert')
        self.assertEqual(items[0]['lei'], LEI_A)
        self.assertEqual(lf.gleif_page('ua', city='Stuttgart', page=2, attempt_from=1)['_attempt'], 1, 'Folgeseiten ohne erneuten Fehlversuch')

    def test_wikidata_retry_and_clear_message(self):
        self.net.fail.add('wikidata')
        with self.assertRaises(lf.SourceError) as err:
            lf.wikidata_sparql('SELECT 1', 'ua')
        self.assertIn('überlastet', str(err.exception))
        self.assertEqual(sum('wikidata' in c for c in self.net.calls), 2, 'ein Wiederholversuch')

    def test_overpass_uses_fallback_server(self):
        self.net.fail.add('osm_main')
        data = lf.overpass('[out:json];node(1);out;', 'ua')
        self.assertTrue(data['elements'])
        self.assertIn('private.coffee', self.net.calls[-1])


class AreaTests(SweepBase):
    def test_resolve_area_with_cache(self):
        a = ar.resolve(self.conn, '70173', 30)
        names = [p['name'] for p in a['places']]
        self.assertEqual(names, ['Stuttgart', 'Esslingen am Neckar'], 'Ulm liegt außerhalb von 30 km')
        self.assertAlmostEqual(a['places'][1]['distance_km'], 9.7, delta=1.5)
        calls = len(self.net.calls)
        b = ar.resolve(self.conn, '70173', 30)
        self.assertTrue(b['cached'])
        self.assertEqual(len(self.net.calls), calls, 'zweite Anfrage ohne Netzwerk')
        with self.assertRaises(ValueError):
            ar.resolve(self.conn, '70173', 33)

    def test_fallback_to_center_only(self):
        self.net.fail.add('wikidata')
        a = ar.resolve(self.conn, 'Stuttgart', 10)
        self.assertEqual([p['name'] for p in a['places']], ['Stuttgart'])
        self.assertEqual(a['source'], 'nur Mittelpunkt')


class SweepTests(SweepBase):
    def test_full_sweep_merges_and_dedupes(self):
        self.conn.execute("INSERT INTO leads(company, website, industry) VALUES ('Bestandskunde Werkzeugbau GmbH', 'https://bestand.example', 'Sonstige')")
        add_suppression(self.conn, 'name', 'Gesperrte Muster AG', 'Widerspruch')
        d = self.run_sweep()
        self.assertEqual(d['status'], 'fertig')
        for s in ('gleif', 'wikidata', 'osm', 'ted'):
            self.assertEqual(d['progress'][s]['status'], 'fertig', s)
        self.assertIn('vereinfacht', d['progress']['gleif']['detail'])
        cs = {c['name']: c for c in self.cands()}
        reith = cs['Reith Spezialkabel GmbH']
        self.assertEqual(sorted(s['source'] for s in reith['sources']), ['gleif', 'wikidata'], 'GLEIF + Wikidata über LEI zusammengeführt')
        self.assertEqual(reith['website'], 'https://reith-kabel.example')
        self.assertEqual(reith['register_id'], 'HRB 14671')
        self.assertEqual(cs['Neckar Präzisionsteile GmbH']['website'], 'https://www.neckar-praezision.example', 'Website über LEI aus Wikidata')
        self.assertAlmostEqual(cs['Neckar Präzisionsteile GmbH']['distance_km'], 9.7, delta=1.5, msg='Entfernung über die Gemeinde')
        self.assertNotIn('Kesselwerk Verwaltungs GmbH', cs, 'nicht operative Gesellschaft ausgefiltert')
        self.assertNotIn('Hanna Beispiel', cs, 'ohne Rechtsform (evtl. Person) ausgefiltert')
        self.assertNotIn('Bäckerei Kornfeld', cs, 'OSM ohne Rechtsform ausgefiltert')
        self.assertEqual(cs['Gesperrte Muster AG']['status'], 'gesperrt')
        self.assertEqual(cs['Bestandskunde Werkzeugbau GmbH']['status'], 'dublette')
        self.assertEqual(cs['Stadtwerke Beispielstadt']['sources'][0]['source'], 'ted')
        before = len(self.cands())
        self.net.calls.clear()
        d2 = self.run_sweep()
        self.assertEqual(len(self.cands()), before, 'zweite Suche erzeugt keine Dubletten')
        self.assertEqual(d2['progress']['gleif']['new'], 0)

    def test_dismissed_never_return_and_source_isolation(self):
        self.run_sweep(sources=['gleif'])
        reith = next(c for c in self.cands() if c['name'].startswith('Reith'))
        sw.decide(self.conn, reith['id'], 'verwerfen')
        self.net.fail.add('ted')
        d = self.run_sweep(sources=['gleif', 'wikidata', 'ted'])
        self.assertEqual(d['progress']['ted']['status'], 'fehler')
        self.assertIn('HTTP 503', d['progress']['ted']['error'])
        self.assertEqual(d['status'], 'fertig', 'andere Quellen laufen weiter')
        self.assertGreaterEqual(d['progress']['wikidata']['dismissed'], 1, 'verworfene Firma kommt über Wikidata nicht zurück')
        self.assertEqual([c['status'] for c in self.cands() if c['name'].startswith('Reith')], ['verworfen'])

    def test_industry_and_keyword_filters(self):
        d = self.run_sweep(sources=['gleif', 'osm'], industries=['elektro', 'metall'])
        names = {c['name'] for c in self.cands()}
        self.assertIn('Elektro Sommer GmbH', names, 'OSM-Treffer über Branchenmerkmal')
        self.assertIn('Neckar Präzisionsteile GmbH', names, 'GLEIF-Treffer über Wort „Präzision“ im Namen')
        self.assertNotIn('Reith Spezialkabel GmbH', names)
        self.assertGreater(d['progress']['gleif']['filtered'], 0)
        e = next(c for c in self.cands() if c['name'] == 'Elektro Sommer GmbH')
        self.assertEqual(e['industry_label'], 'Elektroinstallation & Elektrotechnik')

    def test_validation_and_limits(self):
        for bad in ({'place': '7'}, {'place': '70173', 'radius_km': 33}, {'place': '70173', 'sources': ['google_maps']},
                    {'place': '70173', 'industries': ['raumfahrt']}, {'place': '70173', 'keywords': 'a'}):
            with self.assertRaises(ValueError, msg=bad):
                sw.start_sweep(self.conn, bad, self.db, start=False)
        sw.start_sweep(self.conn, {'place': '70173'}, self.db, start=False)
        with self.assertRaises(ValueError):
            sw.start_sweep(self.conn, {'place': '70173'}, self.db, start=False)


GLEIF_CSV = ('"LEI","Entity.LegalName","Entity.LegalAddress.FirstAddressLine","Entity.LegalAddress.AddressNumber","Entity.LegalAddress.City",'
             '"Entity.LegalAddress.Country","Entity.LegalAddress.PostalCode","Entity.RegistrationAuthority.RegistrationAuthorityEntityID",'
             '"Entity.EntityCategory","Entity.EntityStatus","Registration.InitialRegistrationDate","Entity.EntityCreationDate"\n'
             f'"{LEI_A}","Reith Spezialkabel GmbH","Industriestraße 1","","STUTTGART","DE","70173","HRB 14671","GENERAL","ACTIVE","2019-01-01T00:00:00+00:00",""\n'
             '"G00000000000000000007","""Frisch-Lamm"" Metzgereigesellschaft mbH","Marktplatz 2","","Stuttgart","DE","70173","HRB 8602","GENERAL","ACTIVE","2018-01-01",""\n'
             '"H00000000000000000008","Muster Beteiligungs GmbH","Weg 1","","Stuttgart","DE","70174","HRB 1","GENERAL","ACTIVE","2018-01-01",""\n'
             '"I00000000000000000009","Inaktiv GmbH","Weg 1","","Stuttgart","DE","70174","HRB 2","GENERAL","INACTIVE","2018-01-01",""\n'
             '"J00000000000000000010","Zukunftsfonds","Weg 1","","Stuttgart","DE","70174","","FUND","ACTIVE","2018-01-01",""\n'
             '"K00000000000000000011","Ulmer Bau GmbH","Weg 1","","Ulm","DE","89073","HRB 3","GENERAL","ACTIVE","2018-01-01",""\n')


class ImportTests(SweepBase):
    def test_gleif_export_import(self):
        r = sw.import_file(self.conn, GLEIF_CSV, {'filename': 'lei-records.csv', 'plz': '70'})
        self.assertEqual(r['source'], 'gleif_csv')
        self.assertEqual((r['skipped']['inaktiv'], r['skipped']['fonds_einzel'], r['skipped']['plz']), (1, 1, 1))
        names = {c['name']: c for c in self.cands()}
        self.assertIn('"Frisch-Lamm" Metzgereigesellschaft mbH', names, 'Anführungszeichen korrekt gelesen')
        self.assertEqual(names['Reith Spezialkabel GmbH']['city'], 'Stuttgart', 'Großschreibung normalisiert')
        self.assertNotIn('Muster Beteiligungs GmbH', names)
        self.assertEqual(names['"Frisch-Lamm" Metzgereigesellschaft mbH']['industry_label'], 'Bäckerei, Metzgerei, Konditorei')
        r2 = sw.import_file(self.conn, GLEIF_CSV, {'filename': 'lei-records.csv', 'plz': '70'})
        self.assertEqual(r2['new'], 0, 'erneuter Import ohne Dubletten')
        self.run_sweep(sources=['gleif'])
        reith = [c for c in self.cands() if c['name'] == 'Reith Spezialkabel GmbH']
        self.assertEqual(len(reith), 1, 'Import und Live-Suche über LEI zusammengeführt')

    def test_generic_list_with_semicolon(self):
        text = 'Firma;Website;PLZ;Ort\nKorn & Kunst GmbH;korn-kunst.example;70178;Stuttgart\nOhne Website KG;;70180;Stuttgart\n'
        r = sw.import_file(self.conn, text, {'filename': 'liste.csv'})
        self.assertEqual((r['source'], r['new']), ('liste', 2))
        c = next(x for x in self.cands() if x['name'].startswith('Korn'))
        self.assertEqual((c['website'], c['website_status']), ('https://korn-kunst.example', 'quelle'))
        with self.assertRaises(ValueError):
            sw.import_file(self.conn, 'Spalte1;Spalte2\na;b\n', {})


class DecisionAndWebsiteTests(SweepBase):
    def test_take_over_creates_enriched_lead(self):
        sw.import_file(self.conn, GLEIF_CSV, {'plz': '70'})
        c = next(x for x in self.cands() if x['name'] == 'Reith Spezialkabel GmbH')
        res = sw.decide(self.conn, c['id'], 'uebernehmen')
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertEqual((lead['register_number'], lead['zip'], lead['permission'], lead['stage']), ('HRB 14671', '70173', 'unbekannt', 'recherche'))
        with self.assertRaises(ValueError):
            sw.decide(self.conn, c['id'], 'uebernehmen')
        r = sw.bulk(self.conn, {'ids': [x['id'] for x in self.cands(status='neu')], 'decision': 'verwerfen'})
        self.assertGreaterEqual(r['done'], 1)
        self.assertTrue(self.conn.execute('SELECT COUNT(*) FROM discovery_dismissed').fetchone()[0])

    def test_domain_guesses(self):
        self.assertEqual(sw.domain_guesses('Reith Spezialkabel GmbH', 'Stuttgart')[:3], ['reithspezialkabel.de', 'reith-spezialkabel.de', 'reith.de'])
        self.assertIn('dinkelacker.de', sw.domain_guesses('Dinkelacker-Schwaben Bräu GmbH & Co. KG', 'Stuttgart'))
        self.assertEqual(sw.domain_guesses('GmbH & Co. KG'), [])

    def test_website_finder_requires_evidence(self):
        sw.import_file(self.conn, GLEIF_CSV + '"L00000000000000000012","Nirgendwo Technik GmbH","Weg 9","","Stuttgart","DE","70190","HRB 77","GENERAL","ACTIVE","2018",""\n', {'plz': '70'})
        cands = {c['name']: c for c in self.cands()}

        def fake_research(domain, include_persons=True):
            if domain == 'reithspezialkabel.de':
                raise imprint.CrawlError('DNS: Domain existiert nicht')
            if domain == 'reith-spezialkabel.de':
                return {'status': 'ok', 'home_url': 'https://reith-spezialkabel.de/', 'imprint_url': 'https://reith-spezialkabel.de/impressum',
                        'fields': {'legal_name': {'value': 'Reith Spezialkabel GmbH'}, 'register_number': {'value': 'HRB 14671'},
                                   'business_phone': {'value': '+49 711 000000'}, 'business_email': {'value': 'info@reith-spezialkabel.de'}}}
            if domain.startswith('frisch'):
                return {'status': 'ok', 'home_url': f'https://{domain}/', 'fields': {'legal_name': {'value': 'Frisch-Lamm Metzgereigesellschaft mbH'}, 'zip': {'value': '70173'}}}
            return {'status': 'ok', 'home_url': f'https://{domain}/', 'fields': {'legal_name': {'value': 'Ganz Andere Firma GmbH'}, 'register_number': {'value': 'HRB 1'}}}
        ids = [cands[n]['id'] for n in ('Reith Spezialkabel GmbH', '"Frisch-Lamm" Metzgereigesellschaft mbH', 'Nirgendwo Technik GmbH')]
        self.assertEqual(sw.queue_websites(self.conn, {'ids': ids}, self.db, start=False)['queued'], 3)
        with mock.patch.object(imprint, 'research_domain', side_effect=fake_research):
            sw._web_worker(self.db)
        cs = {c['name']: c for c in self.cands()}
        r = cs['Reith Spezialkabel GmbH']
        self.assertEqual((r['website'], r['website_status']), ('https://reith-spezialkabel.de', 'belegt'))
        self.assertIn('HRB 14671', r['website_evidence'])
        self.assertEqual(r['contact']['business_email'], 'info@reith-spezialkabel.de')
        self.assertEqual(cs['"Frisch-Lamm" Metzgereigesellschaft mbH']['website_status'], 'wahrscheinlich')
        n = cs['Nirgendwo Technik GmbH']
        self.assertEqual((n['website'], n['website_status']), ('', 'nicht_gefunden'), 'fremdes Impressum wird nicht zugeordnet')
        self.assertIn('nirgendwotechnik.de', n['website_evidence'])
        sw.decide(self.conn, r['id'], 'uebernehmen')
        lead = self.conn.execute("SELECT * FROM leads WHERE company='Reith Spezialkabel GmbH'").fetchone()
        self.assertEqual((lead['website'], lead['business_email']), ('https://reith-spezialkabel.de', 'info@reith-spezialkabel.de'))


class IndustryTests(unittest.TestCase):
    def test_catalog_and_matching(self):
        cat = ind.catalog()
        self.assertGreaterEqual(sum(len(g['items']) for g in cat['groups']), 60)
        self.assertEqual(ind.match('Elektro Sommer GmbH', ['elektro'], []), (True, 'elektro'))
        self.assertEqual(ind.match('Müller GmbH', ['elektro'], ['manufaktur'])[0], False)
        self.assertEqual(ind.match('Glas Manufaktur Müller', [], ['manufaktur'])[0], True)
        self.assertEqual(ind.match('Irgendwas', [], []), (True, ''))
        self.assertEqual(ind.parse_keywords('Manufaktur, Weingut ;Präzision'), ['manufaktur', 'weingut', 'präzision'])
        self.assertTrue(ind.NON_OPERATIVE_RE.search('Muster Verwaltungs GmbH'))
        self.assertFalse(ind.NON_OPERATIVE_RE.search('Reith Spezialkabel GmbH'))


class SweepHttpTests(SweepBase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, method='GET', body=None, ctype='application/json'):
        c = HTTPConnection('127.0.0.1', self.port, timeout=30)
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        c.request(method, path, body=data, headers={'Content-Type': ctype} if data is not None else {})
        r = c.getresponse()
        out = json.loads(r.read() or b'{}')
        c.close()
        return r.status, out

    def test_endpoints(self):
        self.assertEqual(self.call('/api/industries')[0], 200)
        status, s = self.call('/api/sweeps', 'POST', {'place': 'Stuttgart', 'radius_km': 30, 'sources': ['gleif', 'ted']})
        self.assertEqual(status, 202)
        sw._THREADS[s['id']].join(30)
        status, d = self.call(f"/api/sweeps/{s['id']}")
        self.assertEqual(d['status'], 'fertig')
        status, lst = self.call('/api/sweep-candidates?status=neu&sort=distanz')
        self.assertGreater(lst['total'], 0)
        cid = lst['items'][0]['id']
        self.assertEqual(self.call(f'/api/sweep-candidates/{cid}/decision', 'POST', {'decision': 'verwerfen'})[0], 200)
        status, r = self.call('/api/sweeps/import?filename=lei.csv&plz=70', 'POST', GLEIF_CSV.encode(), 'text/csv')
        self.assertEqual((status, r['source']), (201, 'gleif_csv'))
        self.assertEqual(self.call('/api/sweeps/import', 'POST', b'x', 'application/x-www-form-urlencoded')[0], 400)
        self.assertEqual(self.call('/api/sweeps')[0], 200)
        self.assertEqual(self.call('/api/sweep-candidates?status=quatsch')[0], 400)


if __name__ == '__main__':
    unittest.main()
