"""Phase 2 – Website-Bedarfs-Scorer v2.

Teil 1 prüft Rubriken und Scores mit festen Erfassungsdaten (reproduzierbar, ohne Browser).
Teil 2 rendert zwei fiktive Testwebsites über einen lokalen HTTP-Server mit echtem Chromium.
Das ist ein echter Browser-Test, aber kein Live-Test öffentlicher Websites. Er wird
übersprungen, wenn Playwright nicht installiert ist.
"""
import copy
import functools
import json
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sales_tool import website_scorer as ws
from sales_tool.model import connect, init_db
from sales_tool.sales_workspace import PACKAGES

SITES = Path(__file__).parent / 'fixtures' / 'sites'
LEAD = {'id': 1, 'industry': 'Industrie & B2B-Technik', 'employees': 80, 'signal_type': 'kein_signal', 'signal_date': '', 'permission': 'unbekannt'}


def facts(**over):
    base = {'url': 'https://firma.example/', 'title': 'T', 'metaDescription': 'x', 'viewportMeta': True, 'h1': 1, 'h2': 3, 'headings': [],
            'navLinks': 6, 'links': [{'href': 'https://firma.example/leistungen', 'text': 'Leistungen'}], 'forms': [{'fields': 4, 'required': 2, 'file': False, 'search': False}],
            'tel': 1, 'mailto': 1, 'ctaTotal': 2, 'ctaAboveFold': ['Anfrage senden'], 'images': 4, 'imagesNoAlt': 0,
            'fontFamilies': ['arial'], 'textElements': 100, 'smallText': 2, 'smallTapTargets': 1, 'overflowX': False,
            'scrollHeight': 2000, 'layoutWidth': 390, 'deviceWidth': 390, 'scrollWidth': 390, 'copyrightYear': 2026, 'loginLinks': 1, 'pdfLinks': [], 'text': 'Fräsen und Drehen.',
            'timing': {'dcl': 600, 'load': 1200, 'transfer': 900000, 'requests': 20}, 'status': 200}
    base.update(over)
    return base


def capture(desktop=None, mobile=None, renderer='playwright', broken=(), checked=10, console=0):
    d = desktop or facts()
    m = mobile if mobile is not None else facts()
    page = {'url': 'https://firma.example/', 'kind': 'home', 'desktop': d}
    if renderer == 'playwright':
        page['mobile'] = m
    return {'url': 'https://firma.example/', 'final_url': 'https://firma.example/', 'renderer': renderer, 'https': True,
            'pages': [page], 'screenshots': [], 'errors': [], 'console_errors': console if renderer == 'playwright' else None,
            'link_check': {'checked': checked, 'broken': [{'url': u, 'status': 404, 'found_on': 'https://firma.example/'} for u in broken], 'skipped': 0}}


class RubricAndScoreTests(unittest.TestCase):
    cfg = copy.deepcopy(ws.DEFAULT_CONFIG)

    def run_score(self, cap, lead=LEAD, cfg=None):
        return ws.score(cap, lead, cfg or self.cfg, set(PACKAGES))

    def test_good_site_has_low_potential_and_full_coverage(self):
        r = self.run_score(capture())
        self.assertEqual(r['coverage'], 100)
        self.assertLessEqual(r['potential'], 15)
        self.assertIsNotNone(r['overall'])
        self.assertIn('ohne Anlass', r['overall_note'])  # kein Signal → unbekannt, nicht 0
        self.assertIsNone(r['signal'])

    def test_weak_site_flags_measured_issues(self):
        d = facts(h1=0, h2=0, ctaAboveFold=[], tel=0, mailto=0, forms=[], loginLinks=0, viewportMeta=False, metaDescription='',
                  copyrightYear=2017, fontFamilies=['georgia', 'courier', 'verdana', 'impact', 'tahoma'], imagesNoAlt=4,
                  timing={'dcl': 3000, 'load': 6500, 'transfer': 7_000_000, 'requests': 140},
                  pdfLinks=[{'href': 'https://firma.example/Bestellformular.pdf', 'text': 'Bestellformular'}],
                  text='Formular ausdrucken, ausfüllen und per Fax zurücksenden.')
        m = facts(overflowX=True, smallText=40, smallTapTargets=12)
        r = self.run_score(capture(d, m, broken=['https://firma.example/alt']))
        flagged = {f['rubric'] for f in r['findings'] if f['result'] == 'auffaellig'}
        for rid in ('A1_mobile_overflow', 'A2_small_text', 'A3_heading_hierarchy', 'A4_alt_texts', 'A5_tap_targets', 'A6_font_consistency',
                    'A7_freshness', 'B1_load_time', 'B2_page_weight', 'B3_cta_above_fold', 'B4_contact_options', 'B6_broken_links',
                    'B9_technical', 'C1_pdf_workflows', 'C2_manual_requests', 'C3_self_service'):
            self.assertIn(rid, flagged, rid)
        self.assertGreaterEqual(r['area_scores']['design']['score'], 90)
        self.assertGreater(r['potential'], 70)
        c1 = next(f for f in r['findings'] if f['rubric'] == 'C1_pdf_workflows')
        self.assertEqual(c1['certainty'], 'hypothese')
        self.assertIn('Hypothese', c1['evidence'])
        b1 = next(f for f in r['findings'] if f['rubric'] == 'B1_load_time')
        self.assertIn('6.5 s', b1['evidence'])

    def test_html_only_capture_leaves_design_unknown_and_blocks_overall(self):
        d = facts(navLinks=None, ctaAboveFold=None, images=None, imagesNoAlt=None, fontFamilies=None, smallText=None,
                  textElements=None, smallTapTargets=None, overflowX=None, timing=None)
        r = self.run_score(capture(d, renderer='html'))
        design = {f['rubric']: f['result'] for f in r['findings'] if f['area'] == 'design'}
        for rid in ('A1_mobile_overflow', 'A2_small_text', 'A5_tap_targets', 'A6_font_consistency'):
            self.assertEqual(design[rid], 'unbekannt')
        self.assertIsNone(r['area_scores']['design']['score'])
        self.assertLess(r['coverage'], 60)
        self.assertIsNone(r['overall'])
        self.assertIn('Datenlage unzureichend', r['overall_note'])

    def test_reproducible_and_config_versioning(self):
        cap = capture()
        self.assertEqual(json.dumps(self.run_score(cap), sort_keys=True), json.dumps(self.run_score(cap), sort_keys=True))
        cfg = ws.validate_config({'overall_weights': {'potential': 50, 'fit': 25, 'signal': 25}, 'rubrics': {'A7_freshness': {'enabled': False}}})
        self.assertNotEqual(ws.config_hash(cfg), ws.config_hash(ws.DEFAULT_CONFIG))
        self.assertNotIn('A7_freshness', {f['rubric'] for f in self.run_score(cap, cfg=cfg)['findings']})
        for bad in ({'overall_weights': {'potential': 1}}, {'rubrics': {'X': {}}}, {'min_coverage_pct': 5}, {'evil': 1},
                    {'rubrics': {'A1_mobile_overflow': {'weight': 99}}}, {'overall_weights': {'potential': 0, 'fit': 0, 'signal': 0}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ws.validate_config(bad)

    def test_signal_and_fit_components(self):
        lead = dict(LEAD, signal_type='digitalprojekt', signal_date=__import__('datetime').date.today().isoformat(), employees=0, industry='Sonstige')
        r = self.run_score(capture(), lead)
        self.assertEqual(r['signal'], 100)
        self.assertIn('Größe unbekannt', r['fit_basis'])
        self.assertNotIn('ohne Anlass', r['overall_note'])

    def test_summary_questions_offers_and_disclaimer(self):
        d = facts(ctaAboveFold=[], forms=[{'fields': 14, 'required': 9, 'file': True, 'search': False}])
        r = self.run_score(capture(d))
        s = ws.summarize(r, capture(d), LEAD, PACKAGES)
        self.assertTrue(3 <= len(s['questions']) <= 5)
        self.assertTrue(all(o['key'] in PACKAGES for o in s['offers']))
        self.assertIn('Kaufbereitschaft', s['disclaimer'])
        self.assertIn('Kontaktweg', s['next_step'])  # ohne Berechtigung: erst Kontaktweg klären
        text = json.dumps(s, ensure_ascii=False).lower()
        for word in ('kaufbereit ', 'kaufwahrscheinlich', 'budget vorhanden', 'will kaufen'):
            self.assertNotIn(word, text)
        self.assertFalse(any(f['area'] == 'campaign' for f in r['findings']))  # Bereich D inaktiv (kein Katalogpaket)


class ScoringDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'sc.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self._orig = (ws.CAPTURE, ws.CAPTURE_FALLBACK, ws.playwright_available)
        ws.CAPTURE = ws.CAPTURE_FALLBACK = lambda url: dict(capture(), screenshots=[{'page_url': url, 'kind': 'desktop', 'bytes': b'\xff\xd8fakejpeg'}])
        ws.playwright_available = lambda: True

    def tearDown(self):
        ws.CAPTURE, ws.CAPTURE_FALLBACK, ws.playwright_available = self._orig
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, **over):
        data = {'company': 'Testfirma GmbH', 'website': 'https://firma.example', 'industry': 'Industrie & B2B-Technik', 'employees': 50, **over}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid

    def test_queue_persists_scores_findings_screenshots_and_comparability(self):
        lid = self.lead()
        blocked = self.lead(company='Gesperrt AG', website='https://gesperrt.example', stage='gesperrt', permission='nicht_kontaktieren')
        nosite = self.lead(company='Ohne Web GmbH', website='')
        res = ws.enqueue(self.conn, [lid, blocked, nosite], self.db)
        self.assertEqual(len(res['queued']), 1)
        self.assertEqual({s['reason'] for s in res['skipped']}, {'gesperrt', 'keine Website'})
        ws.wait_idle()
        a = ws.audit_detail(self.conn, res['queued'][0])
        self.assertEqual(a['status'], 'done')
        self.assertEqual(len(a['findings']), len(ws.DEFAULT_CONFIG['rubrics']))
        self.assertEqual(a['score']['coverage'], 100)
        self.assertEqual(ws.screenshot_file(self.conn, a['screenshots'][0]['id'], self.db), b'\xff\xd8fakejpeg')
        ws.enqueue(self.conn, [lid], self.db)
        ws.wait_idle()
        second = ws.lead_audits(self.conn, lid)[0]
        b = ws.audit_detail(self.conn, second['id'])
        self.assertTrue(b['comparison']['comparable'])
        self.assertEqual(b['comparison']['delta'], 0)
        ws.activate_config(self.conn, ws.validate_config({'overall_weights': {'potential': 60, 'fit': 20, 'signal': 20}}))
        self.conn.commit()
        ws.enqueue(self.conn, [lid], self.db)
        ws.wait_idle()
        c = ws.audit_detail(self.conn, ws.lead_audits(self.conn, lid)[0]['id'])
        self.assertFalse(c['comparison']['comparable'])
        self.assertIn('andere Bewertungsversion', c['comparison']['note'])
        self.assertEqual(ws.ranking(self.conn)['ranking'][0]['lead_id'], lid)

    def test_failed_capture_is_recorded_and_restart_recovery(self):
        from sales_tool.website_analyzer import CrawlError
        def boom(url):
            raise CrawlError('robots.txt untersagt den Abruf der Startseite.')
        ws.CAPTURE = boom
        lid = self.lead()
        res = ws.enqueue(self.conn, [lid], self.db)
        ws.wait_idle()
        a = ws.audit_detail(self.conn, res['queued'][0])
        self.assertEqual(a['status'], 'failed')
        self.assertIn('robots', a['error'])
        self.conn.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'https://firma.example', 'running')", (lid,))
        ws.recover_audits(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM website_audits WHERE status='running'").fetchone()[0], 0)

    def test_screenshot_path_traversal_blocked(self):
        lid = self.lead()
        cur = self.conn.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'x', 'done')", (lid,))
        self.conn.execute("INSERT INTO website_screenshots(audit_id, page_url, kind, path, size_bytes) VALUES (?, 'x', 'desktop', '/etc/passwd', 1)", (cur.lastrowid,))
        sid = self.conn.execute('SELECT id FROM website_screenshots').fetchone()[0]
        with self.assertRaises(LookupError):
            ws.screenshot_file(self.conn, sid, self.db)


@unittest.skipUnless(ws.playwright_available(), 'Playwright nicht installiert – Browser-Test übersprungen')
class RealBrowserTests(unittest.TestCase):
    """Echtes Chromium gegen lokale, fiktive Testseiten (kein Internet)."""
    @classmethod
    def setUpClass(cls):
        cls.servers = {}
        for name in ('gut', 'schwach'):
            handler = functools.partial(_QuietHandler, directory=str(SITES / name))
            srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            cls.servers[name] = srv
        cls._orig = (ws.URL_GUARD, ws.ROBOTS)
        ws.URL_GUARD = lambda u: u          # nur im Test: lokale Testseiten zulassen
        ws.ROBOTS = lambda u: True
        cls.caps = {name: ws.capture_site(f'http://127.0.0.1:{srv.server_address[1]}/') for name, srv in cls.servers.items()}

    @classmethod
    def tearDownClass(cls):
        ws.URL_GUARD, ws.ROBOTS = cls._orig
        for srv in cls.servers.values():
            srv.shutdown()
            srv.server_close()

    def test_rendered_capture_contains_screenshots_and_measurements(self):
        cap = self.caps['gut']
        kinds = [s['kind'] for s in cap['screenshots']]
        self.assertIn('desktop', kinds)
        self.assertIn('mobile', kinds)
        self.assertTrue(all(s['bytes'][:2] == b'\xff\xd8' for s in cap['screenshots']))  # JPEG
        home = cap['pages'][0]
        self.assertGreater(home['desktop']['timing']['load'], 0)
        self.assertEqual(home['desktop']['h1'], 1)
        self.assertIn('Jetzt Anfrage senden', home['desktop']['ctaAboveFold'])
        self.assertFalse(home['mobile']['overflowX'])
        self.assertTrue(any(p['url'].endswith('kontakt.html') for p in cap['pages']))
        self.assertEqual(cap['link_check']['broken'], [])

    def test_weak_site_is_flagged_from_real_rendering(self):
        cap = self.caps['schwach']
        m = cap['pages'][0]['mobile']
        self.assertGreater(m['layoutWidth'], m['deviceWidth'])  # ohne Viewport-Meta: Desktop-Layout wird verkleinert
        self.assertGreater(m['smallText'], 0)
        r = ws.score(cap, LEAD, ws.DEFAULT_CONFIG, set(PACKAGES))
        flagged = {f['rubric'] for f in r['findings'] if f['result'] == 'auffaellig'}
        for rid in ('A1_mobile_overflow', 'A3_heading_hierarchy', 'A6_font_consistency', 'A7_freshness', 'B3_cta_above_fold',
                    'B6_broken_links', 'B9_technical', 'C1_pdf_workflows', 'C2_manual_requests'):
            self.assertIn(rid, flagged, rid)
        good = ws.score(self.caps['gut'], LEAD, ws.DEFAULT_CONFIG, set(PACKAGES))
        self.assertGreater(r['potential'], good['potential'] + 40)
        self.assertTrue(any('gibt-es-nicht' in b['url'] for b in cap['link_check']['broken']))


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


if __name__ == '__main__':
    unittest.main()
