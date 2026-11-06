"""Sprint C – Firmen-Bericht mit einem Klick, Rückfall ohne Browser für URL-Recherche und Entscheider-Recherche.

Fiktive Firma „Kesselwerk Anlagenbau GmbH“; alle Webseiten sind Attrappen (kein Netzwerk).
"""
import datetime as dt
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from sales_tool import imprint
from sales_tool import report as rp
from sales_tool import website_analyzer as wa
from sales_tool import website_scorer as ws
from sales_tool.company_data import add_suppression
from sales_tool.model import connect, init_db
from sales_tool.public_contacts import review_candidate
from sales_tool.server import make_handler
from sales_tool.website_analyzer import CrawlError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_phase2_scoring import capture  # noqa: E402

ISO = lambda n: (dt.date.today() - dt.timedelta(days=n)).isoformat()
SITE = 'https://kesselwerk-beispiel.de'
CAREER = ('<html><body><h1>Karriere</h1><script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@type': 'JobPosting',
          'title': 'Online-Marketing Manager (m/w/d)', 'datePosted': ISO(12), 'description': 'Ausbau unserer Website, Kampagnen und SEO.'}) + '</script></body></html>').encode()
PAGES = {
    SITE: ('text/html', ('<html><head><title>Kesselwerk Anlagenbau – Startseite</title></head><body><h1>Anlagenbau aus Stuttgart</h1>'
                         '<p>Anfragen bitte per Fax oder telefonisch. Unsere Auftragsabwicklung läuft über Excel-Listen.</p>'
                         '<a href="/team">Team</a><a href="/impressum">Impressum</a><a href="/karriere">Karriere</a><a href="/kontakt">Kontakt</a></body></html>').encode()),
    SITE + '/impressum': ('text/html', ('<html><body><h1>Impressum</h1><p>Kesselwerk Anlagenbau GmbH<br>Industriestraße 5<br>70565 Stuttgart</p>'
                                        '<p>Geschäftsführer: Max Mustermann</p><p>Registergericht: Amtsgericht Stuttgart, HRB 765432</p>'
                                        '<p>Telefon: +49 711 9876543<br>E-Mail: info@kesselwerk-beispiel.de</p></body></html>').encode()),
    SITE + '/team': ('text/html', ('<html><head><title>Team</title></head><body><h1>Unser Team</h1><h3>Erika Beispiel</h3><p>Leitung Marketing</p>'
                                   '<p>E-Mail: e.beispiel@kesselwerk-beispiel.de</p><h3>Jonas Probe</h3><p>Head of IT</p></body></html>').encode()),
    SITE + '/kontakt': ('text/html', b'<html><body><h1>Kontakt</h1><form><input name="x"></form><p>Tel. +49 711 9876543</p></body></html>'),
    SITE + '/karriere': ('text/html', CAREER),
}


class FakeWeb:
    def __call__(self, url, origin=None):
        key = url.rstrip('/')
        if key in PAGES:
            return key, *PAGES[key]
        raise CrawlError('HTTP 404')


class ReportBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'rp.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.patches = [mock.patch.object(imprint, 'FETCH', FakeWeb()), mock.patch.object(imprint, 'SLEEP', lambda s: None),
                        mock.patch.object(wa, 'public_url', lambda u: u), mock.patch.object(wa, 'robots_allowed', lambda u: True),
                        mock.patch.object(ws, 'playwright_available', lambda: False),
                        mock.patch.object(ws, 'CAPTURE_FALLBACK', lambda url: capture(renderer='html')),
                        mock.patch.dict(sys.modules, {'playwright': None, 'playwright.sync_api': None})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, company='Kesselwerk', website=SITE, **extra):
        data = {'company': company, 'website': website, 'industry': 'Industrie & B2B-Technik', 'employees': 80, **extra}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid


class LightCrawlTests(ReportBase):
    def test_crawl_without_browser(self):
        crawl = wa.crawl_site(SITE, purpose='full')
        self.assertEqual(crawl['renderer'], 'html')
        urls = [p['url'] for p in crawl['pages']]
        self.assertEqual(urls[0], SITE)
        self.assertIn(SITE + '/team', urls)
        self.assertIn('Ohne Browser', crawl['warnings'][0])
        self.assertEqual(crawl['pages'][0]['title'], 'Kesselwerk Anlagenbau – Startseite')
        self.assertTrue(crawl['pages'][0]['raw_text'])

    def test_crawl_fails_cleanly(self):
        with self.assertRaises(CrawlError):
            wa.light_crawl('https://gibtsnicht-beispiel.de')


class ReportTests(ReportBase):
    def run_all(self):
        rp._worker(self.db)

    def test_one_click_report_runs_all_steps(self):
        lid = self.lead()
        r = rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
        self.assertEqual(len(r['queued']), 1)
        self.run_all()
        v = rp.report_view(self.conn, lead_id=lid)
        steps = v['report']['steps']
        self.assertEqual({k: s['status'] for k, s in steps.items()}, {k: 'fertig' for k, _ in rp.STEPS}, steps)
        self.assertEqual(v['report']['status'], 'fertig')
        self.assertEqual(v['imprint']['fields']['register_number']['value'], 'HRB 765432')
        self.assertEqual(v['imprint']['review_status'], 'uebernommen', 'v1.13: Firmendaten automatisch in leere Felder übernommen')
        lead = self.conn.execute('SELECT legal_name, register_number, company FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((lead['legal_name'], lead['register_number'], lead['company']), ('Kesselwerk Anlagenbau GmbH', 'HRB 765432', 'Kesselwerk'),
                         'leere Felder gefüllt, vorhandener Name bleibt')
        self.assertIn('automatisch übernommen', steps['impressum']['detail'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM decision_contacts WHERE lead_id=?', (lid,)).fetchone()[0], 0, 'keine Personen automatisch angelegt')
        self.assertIn('ohne Browser', steps['website']['detail'])
        self.assertIsNotNone(v['website']['scores'])
        self.assertIn('ohne Browser', steps['inhalte']['detail'])
        self.assertTrue(v['inhalte']['pages'])
        names = [c['full_name'] for c in v['candidates']]
        self.assertIn('Erika Beispiel', names)
        self.assertTrue(v['dossier']['signals'], 'Stellenanzeige als Kaufsignal')
        self.assertIn('Stellenanzeige', steps['signale']['detail'])
        self.assertTrue(v['offers'], 'Paketempfehlung vorhanden')
        self.assertTrue(all(o['status'] == 'unverbindlich' for o in v['offers']), 'ohne Bedarfsklärung unverbindlich')
        self.assertIn('keine Kontakterlaubnis', v['notice'])
        self.assertTrue(self.conn.execute("SELECT 1 FROM activities WHERE lead_id=? AND detail LIKE 'Firmen-Bericht erstellt%'", (lid,)).fetchone())
        # Ansprechpartner übernehmen, erneuter Bericht erzeugt keine doppelten Kandidaten
        cand = next(c for c in v['candidates'] if c['full_name'] == 'Erika Beispiel')
        review_candidate(self.conn, cand['id'], 'accept')
        self.conn.commit()
        rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
        self.run_all()
        v2 = rp.report_view(self.conn, lead_id=lid)
        self.assertNotIn('Erika Beispiel', [c['full_name'] for c in v2['candidates']])
        self.assertIn('Erika Beispiel', [c['full_name'] for c in v2['contacts']])

    def test_failing_step_does_not_stop_others(self):
        lid = self.lead()

        def boom(url):
            raise CrawlError('Website nicht erreichbar (Test)')
        with mock.patch.object(ws, 'CAPTURE_FALLBACK', boom):
            rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
            self.run_all()
        steps = rp.report_view(self.conn, lead_id=lid)['report']['steps']
        self.assertEqual(steps['website']['status'], 'fehler')
        self.assertIn('nicht erreichbar', steps['website']['detail'])
        self.assertEqual(steps['impressum']['status'], 'fertig')
        self.assertEqual(steps['verknuepfen']['status'], 'fertig')

    def test_queue_rules(self):
        no_web = self.lead('Ohne Web GmbH', website='')
        blocked = self.lead('Gesperrt GmbH', stage='gesperrt')
        ok = self.lead()
        r = rp.create_reports(self.conn, {'lead_ids': [no_web, blocked, ok, 9999]}, self.db, start=False)
        reasons = {s['lead_id']: s['reason'] for s in r['skipped']}
        self.assertIn('keine Website', reasons[no_web])
        self.assertEqual(reasons[blocked], 'gesperrt')
        self.assertEqual(reasons[9999], 'nicht gefunden')
        again = rp.create_reports(self.conn, {'lead_ids': [ok]}, self.db, start=False)
        self.assertEqual(again['skipped'][0]['reason'], 'Bericht läuft bereits')
        for bad in ({}, {'lead_ids': []}, {'lead_ids': list(range(1, 60))}, {'lead_ids': ['1']}, {'url': 'kein link'}):
            with self.assertRaises(ValueError, msg=bad):
                rp.create_reports(self.conn, bad, self.db, start=False)

    def test_report_for_url_creates_or_reuses_lead(self):
        r = rp.create_reports(self.conn, {'url': 'kesselwerk-beispiel.de'}, self.db, start=False)
        lid = r['created_lead']
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((lead['stage'], lead['permission'], lead['website']), ('recherche', 'unbekannt', SITE))
        self.run_all()
        self.assertEqual(self.conn.execute('SELECT company FROM leads WHERE id=?', (lid,)).fetchone()[0], 'Kesselwerk Anlagenbau GmbH',
                         'Platzhalter-Name durch Impressumsnamen ersetzt')
        r2 = rp.create_reports(self.conn, {'url': 'https://www.kesselwerk-beispiel.de/'}, self.db, start=False)
        self.assertIsNone(r2['created_lead'], 'gleiche Domain → bestehender Lead')
        self.assertEqual(r2['queued'][0]['lead_id'], lid)
        add_suppression(self.conn, 'domain', 'gesperrt-beispiel.de', 'Widerspruch')
        with self.assertRaises(ValueError):
            rp.create_reports(self.conn, {'url': 'https://gesperrt-beispiel.de'}, self.db, start=False)

    def test_view_without_report(self):
        lid = self.lead()
        v = rp.report_view(self.conn, lead_id=lid)
        self.assertIsNone(v['report'])
        self.assertEqual(v['dossier']['company'], 'Kesselwerk')
        with self.assertRaises(LookupError):
            rp.report_view(self.conn, lead_id=999)


class ReportHttpTests(ReportBase):
    def test_endpoints(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def call(path, method='GET', body=None):
                c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=30)
                c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'} if body is not None else {})
                r = c.getresponse()
                out = json.loads(r.read())
                c.close()
                return r.status, out
            status, r = call('/api/reports', 'POST', {'url': SITE})
            self.assertEqual(status, 202)
            rp.wait_idle(60)
            lid = r['queued'][0]['lead_id']
            status, v = call(f'/api/leads/{lid}/report')
            self.assertEqual((status, v['report']['status']), (200, 'fertig'))
            self.assertEqual(call(f"/api/reports/{v['report']['id']}")[0], 200)
            status, rows = call('/api/reports')
            self.assertEqual(rows[0]['lead_id'], lid)
            self.assertEqual(v['imprint']['review_status'], 'uebernommen')
            lead = self.conn.execute('SELECT legal_name, register_number FROM leads WHERE id=?', (lid,)).fetchone()
            self.assertEqual((lead['legal_name'], lead['register_number']), ('Kesselwerk Anlagenbau GmbH', 'HRB 765432'))
            self.assertEqual(call('/api/reports/999')[0], 404)
            self.assertEqual(call('/api/reports', 'POST', {'lead_ids': 'x'})[0], 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
