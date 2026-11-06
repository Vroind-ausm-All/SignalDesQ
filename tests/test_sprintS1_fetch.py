"""Masterplan 2.0 – Sprint 1: sichere Fetcher-Schnittstelle (IP-Pinning, robots.txt RFC 9309, Grenzen) + Scrapling-Auswertung.

Alle Websites sind fiktiv (tests/fixtures/web); DNS und Verbindungen simuliert tests/webfixtures.py – keine echten Abrufe.
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
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from webfixtures import FAKE_PUBLIC_IP, FixtureServer, add_rebind_site, simulated_network  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import website_analyzer as wa  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import FetchError, FetchPolicy, fetch, parse_html, scrapling_available, settings  # noqa: E402
from sales_tool.research import policy as pol  # noqa: E402
from sales_tool.research.fetchers import browser  # noqa: E402
from sales_tool.research.fetchers.base import decode_html  # noqa: E402
from sales_tool.research.safe_urls import UnsafeURL, check_url  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402


class RobotsRulesTests(unittest.TestCase):
    def test_rfc9309_matching(self):
        r = pol.RobotsRules.parse('User-agent: *\nDisallow: /intern/\nDisallow: /*.pdf$\nAllow: /intern/presse\n'
                                  'User-agent: SignalDeskResearch\nDisallow: /nur-fuer-uns\n')
        self.assertTrue(r.allowed('http://x.example/nur-fuer-uns/alles-andere') is False, 'eigene Gruppe hat Vorrang')
        self.assertTrue(r.allowed('http://x.example/intern/'), 'eigene Gruppe gefunden → *-Gruppe gilt nicht')
        star = pol.RobotsRules.parse('User-agent: *\nDisallow: /intern/\nDisallow: /*.pdf$\nAllow: /intern/presse\nDisallow:\n')
        self.assertFalse(star.allowed('http://x.example/intern/plan'))
        self.assertTrue(star.allowed('http://x.example/intern/presse/2026'), 'längster Treffer gewinnt (Allow)')
        self.assertFalse(star.allowed('http://x.example/downloads/preise.pdf'), 'Platzhalter * und Anker $')
        self.assertTrue(star.allowed('http://x.example/downloads/preise.pdf?x=1'), '$ verankert am Ende')
        self.assertTrue(star.allowed('http://x.example/robots.txt'))
        tie = pol.RobotsRules.parse('User-agent: *\nDisallow: /a\nAllow: /a\n')
        self.assertTrue(tie.allowed('http://x.example/a'), 'Gleichstand → Allow')

    def test_status_mapping(self):
        self.assertTrue(pol.rules_from_response(404, b'').allowed('http://x.example/'))
        self.assertTrue(pol.rules_from_response(403, b'').allowed('http://x.example/'), '4xx = nicht verfügbar = erlaubt')
        self.assertFalse(pol.rules_from_response(429, b'').allowed('http://x.example/'), '429 vorsichtig gesperrt')
        self.assertFalse(pol.rules_from_response(503, b'').allowed('http://x.example/'), '5xx = gesperrt')
        self.assertFalse(pol.rules_from_response(None, b'').allowed('http://x.example/'), 'nicht erreichbar = gesperrt')


class UrlCheckTests(unittest.TestCase):
    def test_syntax(self):
        for url in ('http://127.0.0.1/', 'http://[::1]/', 'http://localhost/', 'http://drucker.local/', 'https://x.example:8080/',
                    'https://user:pw@x.example/', 'file:///etc/passwd', 'ftp://x.example/', 'http://intranet/', 'https://x.example/#a',
                    'http://nas.home.arpa/'):
            with self.subTest(url=url), self.assertRaises(UnsafeURL):
                check_url(url)
        self.assertEqual(check_url('HTTPS://X.Example'), 'https://x.example/')


class DecodeTests(unittest.TestCase):
    def test_charsets(self):
        self.assertEqual(decode_html('<p>Göppingen</p>'.encode('latin-1')), '<p>Göppingen</p>', 'ohne Angabe: Windows-1252-Rückfall')
        self.assertIn('Süß', decode_html('<meta charset="windows-1252"><p>Süß – ok</p>'.encode('cp1252')))
        self.assertEqual(decode_html(b'\xef\xbb\xbf<p>\xc3\xa4</p>'), '<p>ä</p>', 'UTF-8 mit BOM')
        self.assertIn('ß', decode_html('<p>ß</p>'.encode('latin-1'), 'iso-8859-1'))
        self.assertIn('€', decode_html('<p>€</p>'.encode('utf-8')))


class ParseTests(unittest.TestCase):
    HTML = ('<html><head><title>Impressum – Muster GmbH</title><script>var x="Geheim";</script></head><body>'
            '<nav><a href="/">Start</a></nav><h1>Impressum</h1><p>Muster GmbH<br>Weg 1</p><a href="mailto:info@muster.example">Mail</a>'
            '<form><input></form><noscript>Bitte JS</noscript></body></html>')

    def check(self, engine):
        p = parse_html(self.HTML, 'http://muster.example/', use=engine)
        self.assertEqual(p['title'], 'Impressum – Muster GmbH')
        self.assertNotIn('Impressum – Muster', p['text'], 'Seitentitel gehört nicht in den Fließtext (Live-Fehler „Impressum – Firma“)')
        self.assertNotIn('Geheim', p['text'])
        self.assertNotIn('Bitte JS', p['text'])
        self.assertIn('Muster GmbH\nWeg 1', p['text'])
        self.assertEqual(p['mailtos'], ['info@muster.example'])
        self.assertEqual(p['forms'], 1)
        self.assertIn({'href': '/', 'text': 'Start'}, p['links'])
        self.assertEqual(p['headings'], ['Impressum'])
        return p

    def test_stdlib(self):
        self.assertEqual(self.check('stdlib')['engine'], 'stdlib')

    @unittest.skipUnless(scrapling_available(), 'Scrapling optional (requirements-research.txt)')
    def test_scrapling(self):
        self.assertEqual(self.check('scrapling')['engine'], 'scrapling')

    def test_scrapling_failure_falls_back(self):
        with mock.patch('sales_tool.research.parse._parse_scrapling', side_effect=RuntimeError('kaputt')):
            p = parse_html(self.HTML, use='scrapling')
        self.assertEqual(p['engine'], 'stdlib')
        self.assertIn('fehlgeschlagen', p['warning'])


class FetchBase(unittest.TestCase):
    def setUp(self):
        settings.reset()
        pol.ROBOTS.clear()
        self.server = FixtureServer().__enter__()
        add_rebind_site(self.server)
        self.netctx = simulated_network(self.server)
        self.net = self.netctx.__enter__()

    def tearDown(self):
        self.netctx.__exit__(None, None, None)
        self.server.__exit__()
        settings.reset()
        pol.ROBOTS.clear()


class FetchTests(FetchBase):
    def test_ok_with_pinning_and_contract(self):
        r = fetch('http://mueller-metall.example/impressum')
        self.assertEqual((r.status, r.content_type, r.peer_ip, r.robots, r.fetcher), (200, 'text/html', FAKE_PUBLIC_IP, 'erlaubt', 'http'))
        self.assertIn('HRB 700001', r.text())
        meta = r.meta()
        self.assertTrue(meta['content_hash'].startswith('sha256:'))
        self.assertNotIn('body', meta)
        for k in ('source_url', 'final_url', 'fetched_at', 'fetcher', 'redirects', 'robots'):
            self.assertIn(k, meta)

    def test_robots_redirect_and_www_redirect_followed(self):
        r = fetch('http://kanzlei-berg.example/impressum')
        self.assertEqual(r.final_url, 'http://www.kanzlei-berg.example/impressum')
        self.assertEqual(r.redirects, ['http://kanzlei-berg.example/impressum'])
        self.assertIn('HRB 700004', r.text())

    def test_robots_status_rules_and_cache(self):
        self.assertEqual(fetch('http://robots403.example/').status, 200, '403 auf robots.txt = erlaubt (RFC 9309)')
        for host in ('robots500.example', 'geschlossen.example'):
            with self.subTest(host=host), self.assertRaises(FetchError) as ctx:
                fetch(f'http://{host}/')
            self.assertEqual(ctx.exception.kind, 'robots')
        fetch('http://teilgesperrt.example/')
        with self.assertRaises(FetchError):
            fetch('http://teilgesperrt.example/kontakt')
        self.assertEqual(len(self.server.hits('teilgesperrt.example', '/robots.txt')), 1, 'robots.txt je Website einmal')

    def test_ssrf_redirects_never_connect(self):
        with self.assertRaises(UnsafeURL):
            fetch('http://boese-weiterleitung.example/')
        with self.assertRaises(FetchError):
            fetch('http://intern-weiterleitung.example/')
        self.assertEqual(self.net.unvalidated, [], 'keine Verbindung zu einer ungeprüften Adresse')

    def test_dns_rebinding_blocked_by_pinning(self):
        with self.assertRaises(UnsafeURL):
            fetch('http://rebind.example/')  # 1. Auflösung öffentlich (robots), 2. privat → abgelehnt
        self.assertEqual(self.net.unvalidated, [], 'die private Adresse 10.0.0.2 wurde nie angesteuert')
        self.assertTrue(all(c[0] == FAKE_PUBLIC_IP for c in self.net.connects))

    def test_legacy_fetcher_had_rebinding_gap(self):
        settings.set_runtime({'fetcher': 'legacy'})
        with self.assertRaises(Exception):
            imprint.http_fetch('http://rebind.example/')
        self.assertTrue(self.net.unvalidated, 'Messung: bisheriger Abruf verband sich mit der ungeprüften Adresse')

    def test_redirect_rules(self):
        with self.assertRaises(FetchError) as ctx:
            fetch('http://fremd-weiterleitung.example/impressum')
        self.assertIn('fremde Domain', str(ctx.exception))
        with self.assertRaises(FetchError) as ctx:
            fetch('http://schleife.example/')
        self.assertEqual(ctx.exception.kind, 'redirect')

    def test_limits(self):
        cases = {'riesig.example': 'size', 'gzip-bombe.example': 'size', 'kein-html.example': 'content_type', 'drossel429.example': 'http'}
        for host, kind in cases.items():
            with self.subTest(host=host), self.assertRaises(FetchError) as ctx:
                fetch(f'http://{host}/')
            self.assertEqual(ctx.exception.kind, kind)
        with self.assertRaises(FetchError) as ctx:
            fetch('http://drossel429.example/')
        self.assertEqual((ctx.exception.status, ctx.exception.retry_after), (429, 120))
        self.assertIn('Gzip Technik GmbH', fetch('http://gzip-technik.example/impressum').text(), 'gzip korrekt entpackt')

    def test_timeout_budget(self):
        t = time.monotonic()
        with self.assertRaises(FetchError) as ctx:
            fetch('http://langsam.example/', FetchPolicy(timeout=0.5, total_timeout=1.0))
        self.assertEqual(ctx.exception.kind, 'timeout')
        self.assertLess(time.monotonic() - t, 4)


class ImprintIntegrationTests(FetchBase):
    def setUp(self):
        super().setUp()
        self.p = mock.patch.object(imprint, 'SLEEP', lambda s: None)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        super().tearDown()

    def field(self, host, key):
        return ((imprint.research_domain(f'http://{host}/', include_persons=False)['fields'].get(key)) or {}).get('value')

    def test_live_bugs_fixed(self):
        self.assertEqual(self.field('schmid-kg.example', 'legal_name'), 'Schmid Anlagenbau GmbH & Co. KG', 'kein „Impressum – …“ mehr')
        self.assertEqual(self.field('groessle.example', 'city'), 'Göppingen', 'ISO-8859-1 ohne Angabe')
        self.assertEqual(self.field('kanzlei-berg.example', 'register_number'), 'HRB 700004', 'robots.txt-Weiterleitung')
        self.assertEqual(self.field('robots403.example', 'register_number'), 'HRB 700006', 'robots.txt 403')
        self.assertEqual(self.field('gzip-technik.example', 'vat_id'), 'DE999000013', 'gzip')

    def test_crawl_http_first_and_browser_fallback(self):
        calls = []
        fake = lambda *a, **k: calls.append(a[0]) or {'pages': [{'url': a[0], 'title': 'B', 'text': 'Gerendert ' * 50, 'raw_text': '', 'headings': [], 'form_count': 0}], 'errors': []}
        with mock.patch.object(browser, 'available', lambda: True), mock.patch.object(browser, 'crawl', fake):
            rich = wa.crawl_site('http://mueller-metall.example/', 'website')
            self.assertEqual(rich['renderer'], 'html')
            self.assertEqual(calls, [], 'genug statischer Text → kein Browser')
            thin = wa.crawl_site('http://nur-javascript.example/', 'website')
            self.assertEqual(thin['renderer'], 'browser', 'ohne statischen Text → Browser-Rückfall')
            settings.set_runtime({'browser_fallback': False})
            with self.assertRaises(wa.CrawlError):
                wa.crawl_site('http://nur-javascript.example/', 'website')
        self.assertEqual(len(calls), 1)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        settings.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 's.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        settings.reset()
        self.conn.close()
        self.tmp.cleanup()

    def test_validate_save_load(self):
        with self.assertRaises(ValueError):
            settings.save(self.conn, {'fetcher': 'scrapling'})
        with self.assertRaises(ValueError):
            settings.save(self.conn, {'tarnung': True})
        settings.save(self.conn, {'parser': 'stdlib', 'browser_fallback': False})
        settings.reset()
        self.assertEqual(settings.load(self.conn), {'fetcher': 'http', 'parser': 'stdlib', 'browser_fallback': False, 'content': 'stdlib'})
        st = settings.status()
        self.assertEqual(st['parser_in_use'], 'stdlib')
        self.assertIn('Tarnung', st['notice'])

    def test_http_route(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def call(method, body=None):
                c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
                c.request(method, '/api/research/settings', body=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'} if body is not None else {})
                r = c.getresponse()
                out = (r.status, json.loads(r.read() or b'{}'))
                c.close()
                return out
            self.assertEqual(call('GET')[0], 200)
            status, r = call('POST', {'fetcher': 'legacy'})
            self.assertEqual((status, r['settings']['fetcher']), (200, 'legacy'))
            self.assertEqual(call('POST', {'fetcher': 'stealth'})[0], 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
