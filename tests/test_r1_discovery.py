"""R1.3 (2.0.0-dev69): Discovery auf bekannten Websites – Sitemap, Feed, priorisierte Links, sicheres XML.

Abnahme laut Plan: mehr relevante Seiten bei gleichem Seitenbudget (Messung: tools/bench_discovery.py auf erfundenen
Websites) und XML ohne externe Entitäten (Test mit XXE-Beispiel). Keine echten Abrufe.
"""
import gzip
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))

from sales_tool import imprint, website_analyzer as wa  # noqa: E402
from sales_tool.research import discovery as dc  # noqa: E402
from sales_tool.website_analyzer import CrawlError  # noqa: E402

ORIGIN = 'https://fiktiv-bau.example/'
SITEMAP = b'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://fiktiv-bau.example/produkte/daemmung</loc></url>
  <url><loc>https://www.fiktiv-bau.example/unternehmen/geschaeftsfuehrung</loc></url>
  <url><loc>https://fiktiv-bau.example/team</loc></url>
  <url><loc>https://fiktiv-bau.example/presse/2026-neubau</loc></url>
  <url><loc>https://fremde-firma.example/team</loc></url>
  <url><loc>https://fiktiv-bau.example/flyer.pdf</loc></url>
</urlset>'''
XXE = b'''<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&xxe;</loc></url></urlset>'''
BOMB = b'''<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<urlset><url><loc>&lol2;</loc></url></urlset>'''
FEED = b'''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><link href="https://fiktiv-bau.example/presse/richtfest"/></entry>
<entry><link href="https://andere.example/x"/></entry></feed>'''


class XmlSafetyTests(unittest.TestCase):
    def test_xxe_and_entity_bombs_are_rejected(self):
        for data in (XXE, BOMB, b'<!doctype html><html></html>'):
            with self.subTest(data[:30]):
                with self.assertRaises(dc.XmlRejected):
                    dc.parse_sitemap(data, ORIGIN)
        with self.assertRaises(dc.XmlRejected):
            dc.parse_feed(XXE, ORIGIN)

    def test_size_and_gzip_limits(self):
        with self.assertRaises(dc.XmlRejected):
            dc.safe_xml(b'<a>' + b'x' * (dc.MAX_XML + 1) + b'</a>')
        with self.assertRaises(dc.XmlRejected):
            dc.safe_xml(gzip.compress(b'<a>' + b' ' * (dc.MAX_XML + 10) + b'</a>'))
        pages, _ = dc.parse_sitemap(gzip.compress(SITEMAP), ORIGIN)
        self.assertEqual(len(pages), 4)

    def test_broken_xml_is_a_clean_error(self):
        with self.assertRaises(dc.XmlRejected):
            dc.parse_sitemap(b'<urlset><url>', ORIGIN)


class ParseTests(unittest.TestCase):
    def test_sitemap_keeps_only_own_pages(self):
        pages, subs = dc.parse_sitemap(SITEMAP, ORIGIN)
        self.assertEqual(subs, [])
        self.assertNotIn('https://fremde-firma.example/team', pages)
        self.assertFalse(any(p.endswith('.pdf') for p in pages))
        self.assertIn('https://www.fiktiv-bau.example/unternehmen/geschaeftsfuehrung', pages, 'www. gehört zur selben Website')

    def test_sitemap_index_and_feed(self):
        idx = b'''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://fiktiv-bau.example/s-pages.xml</loc></sitemap>
                  <sitemap><loc>https://fremd.example/s.xml</loc></sitemap></sitemapindex>'''
        self.assertEqual(dc.parse_sitemap(idx, ORIGIN), ([], ['https://fiktiv-bau.example/s-pages.xml']))
        self.assertEqual(dc.parse_feed(FEED, ORIGIN), ['https://fiktiv-bau.example/presse/richtfest'])

    def test_priority_puts_people_and_press_before_products(self):
        cands = [(u, '') for u in dc.parse_sitemap(SITEMAP, ORIGIN)[0]] + [(ORIGIN + 'impressum', 'Impressum')]
        got = dc.plan(ORIGIN, cands, 4)
        self.assertEqual([dc.category(u) for u in got], ['impressum', 'management', 'team', 'presse'])
        self.assertEqual(dc.plan(ORIGIN, cands, 10)[-1], 'https://fiktiv-bau.example/produkte/daemmung')
        self.assertEqual(dc.plan(ORIGIN, cands, 0), [])


class DiscoverTests(unittest.TestCase):
    def test_only_sitemap_and_one_sub_sitemap_are_fetched(self):
        calls = []
        idx = b'''<sitemapindex><sitemap><loc>https://fiktiv-bau.example/s-posts.xml</loc></sitemap>
                  <sitemap><loc>https://fiktiv-bau.example/s-pages.xml</loc></sitemap></sitemapindex>'''

        def fetch(url):
            calls.append(url)
            return url, 'application/xml', idx if url.endswith('/sitemap.xml') else SITEMAP
        urls, _ = dc.discover(ORIGIN, [], fetch, 3)
        self.assertEqual(calls, [ORIGIN + 'sitemap.xml', 'https://fiktiv-bau.example/s-pages.xml'], 'kein Voll-Scan')
        self.assertEqual(len(urls), 3)

    def test_missing_sitemap_is_only_a_note(self):
        def fetch(url):
            raise CrawlError('HTTP 404')
        urls, notes = dc.discover(ORIGIN, [{'href': '/kontakt', 'text': 'Kontakt'}], fetch, 4)
        self.assertEqual(urls, [ORIGIN + 'kontakt'])
        self.assertIn('Sitemap nicht genutzt', notes[0])


class LightCrawlTests(unittest.TestCase):
    def test_contacts_crawl_reaches_team_page_only_listed_in_sitemap(self):
        home = b'<html><body><h1>Fiktiv Bau</h1><p>' + b'Wir bauen. ' * 40 + b'</p><a href="/produkte">Produkte</a></body></html>'
        team = b'<html><body><h1>Team</h1><p>' + b'Unser Team. ' * 40 + b'</p></body></html>'
        site = {ORIGIN: home, ORIGIN + 'sitemap.xml': SITEMAP}
        for p in ('team', 'unternehmen/geschaeftsfuehrung', 'presse/2026-neubau', 'produkte/daemmung'):
            site[ORIGIN + p] = team
        site['https://www.fiktiv-bau.example/unternehmen/geschaeftsfuehrung'] = team

        def fetch(url, origin=None):
            if url not in site:
                raise CrawlError('HTTP 404')
            return url, 'application/xml' if url.endswith('.xml') else 'text/html', site[url]
        with mock.patch.object(imprint, 'FETCH', fetch), mock.patch.object(wa, 'public_url', lambda u: u), \
                mock.patch('sales_tool.netpolicy.offline', lambda *a: False):
            res = wa.light_crawl(ORIGIN, 'contacts')
        urls = [p['url'] for p in res['pages']]
        self.assertIn(ORIGIN + 'team', urls)
        self.assertTrue(any('geschaeftsfuehrung' in u for u in urls))
        self.assertLessEqual(len(urls), wa.MAX_PAGES, 'Seitenbudget bleibt gleich')


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_shows_more_relevant_pages_at_same_budget(self):
        import bench_discovery
        res = bench_discovery.run()
        self.assertEqual(res['pages_budget_same'], True)
        self.assertGreater(res['with_discovery']['relevant'], res['links_only']['relevant'])


if __name__ == '__main__':
    unittest.main()
