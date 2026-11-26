"""R1.1 (2.0.0-dev69): Source Registry als zwingende Sperre.

Abnahme laut Plan: Abruf einer nicht freigegebenen Quelle wird serverseitig abgewiesen; Quellenstatus unter Einstellungen →
Datenquellen. Alle Abrufe laufen gegen Attrappen – kein Test verbindet sich nach außen.
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import auth, area, lead_finder as lf, source_check, tenancy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import fetchers, sources  # noqa: E402
from sales_tool.research.fetchers.base import FetchError  # noqa: E402
from sales_tool.server import make_handler, prepare_database  # noqa: E402
from sales_tool.website_analyzer import CrawlError, public_url  # noqa: E402

FIELDS = ('id', 'title', 'operator', 'purpose', 'access', 'fields', 'license', 'terms_url', 'checked', 'review', 'rate',
          'storage', 'export', 'legal_basis', 'owner')


class Recorder:
    """Attrappe für lead_finder.FETCH: merkt sich jede Adresse, verbindet sich nie."""

    def __init__(self, answer=None):
        self.urls, self.answer = [], answer if answer is not None else {}

    def __call__(self, url, ua, **kw):
        self.urls.append(url)
        return self.answer


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / 'q.sqlite3'
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.fetch, self.rec = lf.FETCH, Recorder()
        lf.FETCH = self.rec

    def tearDown(self):
        lf.FETCH = self.fetch
        sources.reset()
        self.conn.close()
        self.tmp.cleanup()


class RegistryContentTests(unittest.TestCase):
    def test_every_entry_is_complete(self):
        for src in sources.REGISTRY.values():
            with self.subTest(src.id):
                for f in FIELDS:
                    self.assertTrue(getattr(src, f) or f == 'fields' and src.access == 'manuell', f'{src.id}: {f} fehlt')
                self.assertIn(src.review, sources.REVIEWS)
                self.assertIn(src.access, ('api', 'website', 'manuell'))
                self.assertRegex(src.checked, r'^\d{4}-\d{2}$')
                if src.review == 'freigegeben':
                    self.assertTrue(src.approved_by, 'Freigabe nennt, wer freigegeben hat')
                if src.access != 'website':
                    self.assertTrue(src.hosts, 'Schnittstellen und gesperrte Quellen nennen ihre Hosts')

    def test_every_automated_source_is_registered(self):
        """Jede Adresse, die der Code für offene Quellen benutzt, gehört zu einer eingetragenen Schnittstelle."""
        urls = [lf.GLEIF_URL, 'https://query.wikidata.org/sparql', 'https://api.ted.europa.eu/v3/notices/search', area.NOMINATIM,
                *lf.OVERPASS_SERVERS]
        for url in urls:
            with self.subTest(url):
                src = sources.source_for_host(urllib.parse.urlsplit(url).hostname)
                self.assertIsNotNone(src)
                self.assertEqual(src.access, 'api')
        for key in lf.SEARCHERS:
            self.assertIn(key, sources.REGISTRY)

    def test_manual_platforms_are_blocked_sources(self):
        for host in ('www.linkedin.com', 'xing.com', 'www.google.de', 'maps.google.com', 'www.gelbeseiten.de', 'www.handelsregister.de'):
            with self.subTest(host):
                src = sources.source_for_host(host)
                self.assertEqual((src.access, src.review), ('manuell', 'gesperrt'))
        self.assertIsNone(sources.source_for_host('notlinkedin.com'), 'nur echte Subdomains zählen')


class ApiGateTests(Base):
    def test_unregistered_api_is_rejected_before_any_connection(self):
        with self.assertRaises(lf.SourceError) as err:
            lf.fetch_source('https://api.unbekannt-fiktiv.example/v1/firmen', 'UA')
        self.assertTrue(err.exception.blocked)
        self.assertFalse(err.exception.retryable, 'eine Sperre ist kein Grund für Wiederholungen')
        self.assertEqual(self.rec.urls, [])

    def test_blocked_platform_is_never_called_as_api(self):
        with self.assertRaises(lf.SourceError):
            lf.fetch_source('https://www.linkedin.com/company/fiktiv', 'UA')
        self.assertEqual(self.rec.urls, [])

    def test_switched_off_source_is_rejected_and_comes_back(self):
        sources.set_enabled(self.conn, 'gleif', False, by='admin')
        with self.assertRaises(lf.SourceError):
            lf.search_gleif({'place': 'Stuttgart'}, 'UA')
        self.assertEqual(self.rec.urls, [])
        sources.set_enabled(self.conn, 'gleif', True, by='admin')
        lf.fetch_source(lf.GLEIF_URL + 'x=1', 'UA')
        self.assertEqual(len(self.rec.urls), 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audit_log WHERE entity='source_policy'").fetchone()[0], 2)

    def test_source_check_respects_registry(self):
        sources.set_enabled(self.conn, 'ted', False)
        with self.assertRaises(lf.SourceError):
            source_check._ted('UA')
        self.assertEqual(self.rec.urls, [])

    def test_blocked_and_unchecked_sources_cannot_be_switched_on(self):
        with self.assertRaises(sources.SourceBlocked):
            sources.set_enabled(self.conn, 'linkedin_xing', True)
        with self.assertRaises(LookupError):
            sources.set_enabled(self.conn, 'erfunden', True)
        with self.assertRaises(ValueError):
            sources.set_enabled(self.conn, 'gleif', 'ja')

    def test_switching_survives_restart(self):
        sources.set_enabled(self.conn, 'wikidata', False)
        sources.reset()
        self.assertTrue(sources.enabled('wikidata'), 'ohne geladene Einstellung gilt der Registry-Stand')
        prepare_database(self.db)
        with tenancy.use(self.db):
            self.assertFalse(sources.enabled('wikidata'), 'nach dem Neustart wieder aus')


class WebsiteGateTests(Base):
    def test_blocked_platform_is_never_fetched_as_website(self):
        for url in ('https://www.linkedin.com/company/fiktiv', 'https://www.google.de/search?q=fiktiv'):
            with self.subTest(url):
                with self.assertRaises(FetchError) as err:
                    fetchers.fetch(url, fetcher='http')
                self.assertEqual(err.exception.kind, 'source')

    def test_company_websites_can_be_switched_off(self):
        sources.set_enabled(self.conn, sources.WEBSITE, False)
        with self.assertRaises(FetchError) as err:
            fetchers.fetch('https://fiktiv-beispiel.example/impressum', fetcher='http')
        self.assertEqual(err.exception.kind, 'source')

    def test_browser_and_scoring_path_uses_the_registry(self):
        """website_analyzer.public_url prüft jede Adresse auch für den Browser-Abruf und das Scoring."""
        orig = sources.check_url
        seen = []
        try:
            from sales_tool.research import safe_urls
            safe, safe_urls.public_url = safe_urls.public_url, lambda u: u
            sources.check_url = lambda u, key=None: seen.append(u) or orig(u, key)
            with self.assertRaises(CrawlError):
                public_url('https://de.linkedin.com/in/fiktiv')
            self.assertEqual(public_url('https://fiktiv-beispiel.example/'), 'https://fiktiv-beispiel.example/')
        finally:
            sources.check_url, safe_urls.public_url = orig, safe
        self.assertEqual(len(seen), 2)


class ServerTests(Base):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def req(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': 'application/json'} if data else {}
        with urlopen(Request(self.base + path, data=data, method=method, headers=headers), timeout=5) as resp:
            return resp.status, json.load(resp)

    def test_search_of_switched_off_source_is_rejected_by_server(self):
        _, state = self.req('/api/sources/gleif', 'PUT', {'enabled': False})
        self.assertFalse({s['id']: s for s in state['sources']}['gleif']['enabled'])
        with self.assertRaises(HTTPError) as err:
            self.req('/api/lead-finder/search', 'POST', {'source': 'gleif', 'place': 'Stuttgart'})
        self.assertEqual(err.exception.code, 403)
        self.assertIn('ausgeschaltet', json.load(err.exception)['error'])
        self.assertEqual(self.rec.urls, [], 'kein Abruf nach außen')

    def test_status_lists_every_source_with_review_and_age(self):
        _, state = self.req('/api/sources')
        rows = {s['id']: s for s in state['sources']}
        self.assertEqual(set(rows), set(sources.REGISTRY))
        for s in rows.values():
            for key in ('review', 'checked', 'license', 'legal_basis', 'enabled', 'switchable', 'measured'):
                self.assertIn(key, s)
        self.assertFalse(rows['linkedin_xing']['switchable'])
        self.assertEqual(state['pending_approval'], [], 'E2 entschieden: keine vorläufige Quelle mehr')
        for key in ('wikidata', 'osm', 'nominatim', 'gleif', 'ted', sources.WEBSITE):
            self.assertEqual((rows[key]['review'], rows[key]['enabled']), ('freigegeben', True), key)
            self.assertIn('26.11.2026', rows[key]['approved_by'])
        with self.assertRaises(HTTPError) as err:
            self.req('/api/sources/linkedin_xing', 'PUT', {'enabled': True})
        self.assertEqual(err.exception.code, 403)
        with self.assertRaises(HTTPError) as err:
            self.req('/api/sources/erfunden', 'PUT', {'enabled': True})
        self.assertEqual(err.exception.code, 404)


class RoleAndTenantTests(unittest.TestCase):
    def test_only_admin_switches_sources(self):
        self.assertTrue(auth.allowed('admin', 'PUT', '/api/sources/gleif'))
        for role in ('vertrieb', 'buchhaltung', 'lesen'):
            self.assertFalse(auth.allowed(role, 'PUT', '/api/sources/gleif'), role)
            self.assertTrue(auth.allowed(role, 'GET', '/api/sources'), role)

    def test_switch_stays_in_its_org(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            directory = tenancy.Directory(Path(tmp) / 'm')
            nord, sued = (Path(directory.create(s, n)['db_path']) for s, n in (('nord', 'Nord'), ('sued', 'Süd')))
            for db in (nord, sued):
                prepare_database(db)
            with connect(nord) as conn:
                sources.set_enabled(conn, 'osm', False)
            try:
                with tenancy.use(nord):
                    self.assertFalse(sources.enabled('osm'))
                with tenancy.use(sued):
                    self.assertTrue(sources.enabled('osm'), 'Süd behält die Quelle')
                sources.reset()
                with tenancy.use(sued):
                    self.assertTrue(sources.enabled('osm'), 'nicht geladene Organisation liest ihre eigene Datenbank')
                with tenancy.use(nord):
                    self.assertFalse(sources.enabled('osm'), 'auch ohne Neustart: Nord bleibt aus')
            finally:
                sources.reset()


if __name__ == '__main__':
    unittest.main()
