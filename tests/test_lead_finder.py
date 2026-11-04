"""Lead-Finder: Parsing, Datensparsamkeit, Dubletten, Fair-Use-Limits, Übernahme ins CRM.

Die Netzwerkschicht wird durch einen Stub ersetzt; die Antwortstrukturen folgen den
dokumentierten Formaten (SPARQL-JSON, Overpass-JSON, GLEIF JSON:API, TED v3).
"""
import json
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool import lead_finder as lf
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler

WIKIDATA = {'results': {'bindings': [
    {'company': {'value': 'http://www.wikidata.org/entity/Q100'}, 'companyLabel': {'value': 'Muster Maschinenbau GmbH'},
     'website': {'value': 'https://www.muster-maschinen.example/'}, 'employees': {'value': '180'},
     'industryLabel': {'value': 'Maschinenbau'}, 'hqLabel': {'value': 'Stuttgart'}},
    {'company': {'value': 'http://www.wikidata.org/entity/Q100'}, 'companyLabel': {'value': 'Muster Maschinenbau GmbH'},
     'industryLabel': {'value': 'Automatisierungstechnik'}, 'hqLabel': {'value': 'Stuttgart'}},
    {'company': {'value': 'http://www.wikidata.org/entity/Q200'}, 'companyLabel': {'value': 'Q200'}},
    {'company': {'value': 'http://www.wikidata.org/entity/Q300'}, 'companyLabel': {'value': 'Beispiel Software AG'},
     'website': {'value': 'beispiel-software.example'}, 'hqLabel': {'value': 'Stuttgart'}},
]}}
OVERPASS = {'elements': [
    {'type': 'node', 'id': 1, 'tags': {'name': 'Nord Ingenieure GmbH', 'office': 'engineer', 'website': 'https://nord-ing.example',
                                       'addr:street': 'Hafenweg', 'addr:housenumber': '3', 'addr:postcode': '20457', 'addr:city': 'Hamburg',
                                       'phone': '+49 40 1', 'email': 'info@nord-ing.example'}},
    {'type': 'way', 'id': 2, 'tags': {'name': 'Steuerbüro Erika Mustermann', 'office': 'tax_advisor', 'website': 'https://mustermann.example'}},
    {'type': 'node', 'id': 3, 'tags': {'name': 'Nord Ingenieure GmbH', 'office': 'engineer', 'website': 'https://www.nord-ing.example/'}},
]}
GLEIF = {'data': [
    {'id': '5299001ABCDEF1234567', 'attributes': {'lei': '5299001ABCDEF1234567', 'entity': {
        'legalName': {'name': 'Präzision Werkzeug GmbH'}, 'category': 'GENERAL', 'registeredAs': 'HRB 123456',
        'legalAddress': {'addressLines': ['Industriestraße 7'], 'city': 'Stuttgart', 'postalCode': '70565', 'country': 'DE'}},
        'registration': {'initialRegistrationDate': '2019-05-02T00:00:00Z'}}},
    {'id': 'FUND00000000000000000', 'attributes': {'lei': 'FUND00000000000000000', 'entity': {
        'legalName': {'name': 'Muster Fonds'}, 'category': 'FUND', 'legalAddress': {'city': 'Stuttgart'}}}},
]}
TED = {'notices': [
    {'publication-number': '654321-2026', 'notice-title': {'deu': 'Relaunch der Website der Stadtwerke'},
     'buyer-name': {'deu': ['Stadtwerke Musterstadt GmbH']}, 'publication-date': ['2026-10-20+02:00'],
     'deadline-receipt-tender-date-lot': ['2026-11-30T12:00:00+01:00'],
     'links': {'html': {'DEU': 'https://ted.europa.eu/de/notice/-/detail/654321-2026'}}},
], 'totalNoticeCount': 1}


class FakeFetch:
    def __init__(self):
        self.calls = []

    def __call__(self, url, ua, data=None, content_type=None, accept='application/json'):
        self.calls.append({'url': url, 'ua': ua, 'data': data})
        if 'wikidata' in url:
            return WIKIDATA
        if 'overpass' in url:
            return OVERPASS
        if 'gleif' in url:
            return GLEIF
        if 'ted.europa.eu' in url:
            return TED
        raise AssertionError(url)


class LeadFinderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / 'lf.sqlite3')
        init_db(self.conn)
        self.fake = FakeFetch()
        self._orig = (lf.FETCH, lf.MIN_SECONDS_BETWEEN_RUNS)
        lf.FETCH = self.fake
        lf.MIN_SECONDS_BETWEEN_RUNS = 0

    def tearDown(self):
        lf.FETCH, lf.MIN_SECONDS_BETWEEN_RUNS = self._orig
        self.conn.close()
        self.tmp.cleanup()

    def test_wikidata_merges_rows_and_drops_unlabeled(self):
        run = lf.run_search(self.conn, {'source': 'wikidata', 'place': 'Stuttgart', 'keyword': 'maschinen'})
        names = [c['name'] for c in run['candidates']]
        self.assertEqual(sorted(names), ['Beispiel Software AG', 'Muster Maschinenbau GmbH'])
        muster = next(c for c in run['candidates'] if c['name'].startswith('Muster'))
        self.assertEqual(muster['employees'], 180)
        self.assertIn('Automatisierungstechnik', muster['industry'])
        self.assertEqual(muster['license'], 'CC0 1.0')
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.fake.calls[0]['url']).query)['query'][0]
        self.assertIn('"Stuttgart"@de', query)
        self.assertIn('maschinen', query)
        self.assertTrue(self.fake.calls[0]['ua'].startswith('SignalDesk/'))

    def test_osm_minimises_personal_data_and_dedupes(self):
        run = lf.run_search(self.conn, {'source': 'osm', 'place': 'Hamburg', 'category': 'ingenieur'})
        self.assertEqual([c['name'] for c in run['candidates']], ['Nord Ingenieure GmbH'])
        self.assertEqual(run['filtered_count'], 1)  # Steuerbüro mit Personennamen ausgefiltert
        cols = run['candidates'][0].keys()
        self.assertNotIn('email', cols)
        self.assertNotIn('phone', cols)
        self.assertEqual(run['candidates'][0]['street'], 'Hafenweg 3')
        body = urllib.parse.parse_qs(self.fake.calls[0]['data'].decode())['data'][0]
        self.assertIn('"office"="engineer"', body)
        lf.run_search(self.conn, {'source': 'osm', 'place': 'Hamburg', 'category': 'beratung', 'legal_entities_only': False})
        run2 = lf.run_detail(self.conn, 2)
        self.assertIn('Steuerbüro Erika Mustermann', [c['name'] for c in run2['candidates']])

    def test_gleif_skips_funds_and_keeps_register(self):
        run = lf.run_search(self.conn, {'source': 'gleif', 'place': 'Stuttgart'})
        self.assertEqual(len(run['candidates']), 1)
        c = run['candidates'][0]
        self.assertEqual((c['register_id'], c['zip'], c['legal_form']), ('HRB 123456', '70565', 'GmbH'))
        self.assertIn('filter%5Bentity.legalAddress.city%5D=Stuttgart', self.fake.calls[0]['url'])

    def test_ted_tenders_become_signals(self):
        run = lf.run_search(self.conn, {'source': 'ted', 'preset': 'web', 'days': 30})
        c = run['candidates'][0]
        self.assertEqual(c['name'], 'Stadtwerke Musterstadt GmbH')
        self.assertEqual(c['signal_type'], 'digitalprojekt')
        self.assertEqual(c['signal_date'], '2026-10-20')
        self.assertIn('Angebotsfrist 2026-11-30', c['signal_note'])
        body = json.loads(self.fake.calls[0]['data'])
        self.assertIn('72413000', body['query'])
        lead = lf.review_candidate(self.conn, c['id'], 'uebernehmen')
        row = self.conn.execute('SELECT * FROM leads WHERE id=?', (lead['lead_id'],)).fetchone()
        self.assertEqual(row['contact_route'], 'ausschreibung')
        self.assertEqual(row['signal_source'], 'https://ted.europa.eu/de/notice/-/detail/654321-2026')

    def test_cache_rate_limit_and_daily_limit(self):
        lf.run_search(self.conn, {'source': 'gleif', 'place': 'Stuttgart'})
        again = lf.run_search(self.conn, {'source': 'gleif', 'place': 'Stuttgart'})
        self.assertTrue(again['cached'])
        self.assertEqual(len(self.fake.calls), 1)
        lf.MIN_SECONDS_BETWEEN_RUNS = 60
        with self.assertRaisesRegex(ValueError, 'Sekunden'):
            lf.run_search(self.conn, {'source': 'gleif', 'place': 'München'})
        lf.MIN_SECONDS_BETWEEN_RUNS = 0
        orig = lf.DAILY_LIMIT_PER_SOURCE
        lf.DAILY_LIMIT_PER_SOURCE = 1
        try:
            with self.assertRaisesRegex(ValueError, 'Tageslimit'):
                lf.run_search(self.conn, {'source': 'gleif', 'place': 'Köln'})
        finally:
            lf.DAILY_LIMIT_PER_SOURCE = orig

    def test_input_validation_blocks_query_injection(self):
        for bad in ('Stuttgart"} ; DELETE', 'a', 'x' * 90, 'Köln<script>'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                lf.run_search(self.conn, {'source': 'wikidata', 'place': bad})
        for bad in ({'source': 'unknown', 'place': 'Berlin'}, {'source': 'osm', 'place': 'Berlin', 'category': 'xx'},
                    {'source': 'ted', 'days': 999}, {'source': 'gleif', 'place': 'Berlin', 'limit': 5000},
                    {'source': 'gleif', 'place': 'Berlin', 'evil': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                lf.run_search(self.conn, bad)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM discovery_runs').fetchone()[0], 0)

    def test_duplicates_against_existing_leads_and_import(self):
        self.conn.execute("INSERT INTO leads(company, website) VALUES ('Muster Maschinenbau', 'https://muster-maschinen.example')")
        self.conn.commit()
        run = lf.run_search(self.conn, {'source': 'wikidata', 'place': 'Stuttgart'})
        status = {c['name']: c['status'] for c in run['candidates']}
        self.assertEqual(status['Muster Maschinenbau GmbH'], 'dublette')
        dup = next(c for c in run['candidates'] if c['status'] == 'dublette')
        with self.assertRaisesRegex(ValueError, 'bereits'):
            lf.review_candidate(self.conn, dup['id'], 'uebernehmen')
        new = next(c for c in run['candidates'] if c['status'] == 'neu')
        res = lf.review_candidate(self.conn, new['id'], 'uebernehmen')
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertEqual(lead['permission'], 'unbekannt')
        self.assertEqual(lead['stage'], 'recherche')
        self.assertEqual(lead['industry'], 'B2B-SaaS')
        self.assertIn('CC0', lead['note'])
        self.assertIn('keine Einwilligung', lead['note'])
        with self.assertRaises(ValueError):
            lf.review_candidate(self.conn, new['id'], 'uebernehmen')

    def test_source_errors_are_recorded(self):
        def failing(*a, **k):
            raise lf.SourceError('Quelle nicht erreichbar (403).')
        lf.FETCH = failing
        with self.assertRaises(lf.SourceError):
            lf.run_search(self.conn, {'source': 'osm', 'place': 'Berlin'})
        row = self.conn.execute('SELECT status, error FROM discovery_runs').fetchone()
        self.assertEqual(row['status'], 'failed')
        self.assertIn('403', row['error'])

    def test_manual_links_and_catalog(self):
        links = lf.manual_links('Stuttgart', 'Maschinenbau')
        self.assertTrue(any(l['ampel'] == 'rot' for l in links))
        job = next(l for l in links if 'Bundesagentur' in l['name'])
        self.assertIn('wo=Stuttgart', job['link'])
        self.assertFalse(lf.catalog()['live_verified'])


class LeadFinderHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'http.sqlite3'
        with connect(self.db) as conn:
            init_db(conn)
        self._orig = (lf.FETCH, lf.MIN_SECONDS_BETWEEN_RUNS)
        lf.FETCH = FakeFetch()
        lf.MIN_SECONDS_BETWEEN_RUNS = 0
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        lf.FETCH, lf.MIN_SECONDS_BETWEEN_RUNS = self._orig
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_search_review_flow(self):
        status, cat = self.call('/api/lead-finder/catalog')
        self.assertEqual(status, 200)
        self.assertIn('ted', cat['sources'])
        status, run = self.call('/api/lead-finder/search', 'POST', {'source': 'gleif', 'place': 'Stuttgart'})
        self.assertEqual(status, 201, run)
        cid = run['candidates'][0]['id']
        status, res = self.call(f'/api/lead-finder/candidates/{cid}/review', 'POST', {'decision': 'uebernehmen'})
        self.assertEqual(status, 200, res)
        status, lead = self.call(f"/api/leads/{res['lead_id']}")
        self.assertEqual(lead['company'], 'Präzision Werkzeug GmbH')
        status, runs = self.call('/api/lead-finder/runs')
        self.assertEqual(len(runs), 1)
        def failing(*a, **k):
            raise lf.SourceError('HTTP 403')
        lf.FETCH = failing
        status, err = self.call('/api/lead-finder/search', 'POST', {'source': 'osm', 'place': 'Berlin'})
        self.assertEqual(status, 502)


if __name__ == '__main__':
    unittest.main()
