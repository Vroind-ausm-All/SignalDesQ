"""Phase 3 – Buying Signals: Registerereignisse, Job-Signale, Dubletten, Korrelation, Scoring-Anbindung.

Alle Bekanntmachungen, Firmen, Personen und Stellen sind fiktiv. Die Netzwerkschicht ist ein Stub –
das ist kein Live-Test echter Karriereseiten.
"""
import datetime as dt
import json
import tempfile
import threading
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool import buying_signals as bs
from sales_tool import imprint
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler
from sales_tool.website_analyzer import CrawlError

TODAY = dt.date.today()
D = lambda days: (TODAY - dt.timedelta(days=days)).strftime('%d.%m.%Y')
ISO = lambda days: (TODAY - dt.timedelta(days=days)).isoformat()

REGISTER_TEXT = f"""Amtsgericht Stuttgart Aktenzeichen: HRB 765432
Bekannt gemacht am: {D(20)}
Neueintragungen
HRB 765432: Nordlicht Digital GmbH, Stuttgart, Königstraße 1, 70173 Stuttgart. Stammkapital: 25.000,00 EUR. Geschäftsführer: Mustermann, Max, Stuttgart, *01.02.1980, einzelvertretungsberechtigt.

Amtsgericht Hamburg Aktenzeichen: HRB 998877
Bekannt gemacht am: {D(15)}
Veränderungen
HRB 998877: Pixelhafen UG (haftungsbeschränkt), Hamburg. Firma geändert; nun: Pixelhafen Studio GmbH. Neue Geschäftsanschrift: Am Sandtorkai 7, 20457 Hamburg.

Amtsgericht Stuttgart Aktenzeichen: HRA 123456
Bekannt gemacht am: {D(5)}
Veränderungen
HRA 123456: Musterwerk Präzisionstechnik GmbH & Co. KG, Stuttgart. Nicht mehr Geschäftsführer: Beispiel, Anna, Esslingen, *03.04.1970. Bestellt als Geschäftsführer: Neumann, Nina, Stuttgart, *05.06.1985.

Amtsgericht München Aktenzeichen: HRB 222333
Bekannt gemacht am: {D(400)}
Löschungen
HRB 222333: Altlast Handels GmbH, München. Die Gesellschaft ist aufgelöst. Liquidator bestellt.
"""

JSONLD_CAREER = ('<html><body><h1>Karriere</h1><script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@graph': [
    {'@type': 'JobPosting', 'title': 'Online-Marketing Manager (m/w/d)', 'datePosted': ISO(10), 'validThrough': ISO(-30),
     'description': '<p>Ausbau unserer Website, SEO und Content. Kontakt: hr@musterwerk-beispiel.de, Tel. 0711 123456</p>'},
    {'@type': 'JobPosting', 'title': 'Prozessmanager Digitalisierung (w/m/d)', 'datePosted': ISO(200),
     'description': 'Einführung neuer Software, Stammdaten in mehreren Systemen, Excel-basierte Abläufe ablösen.'},
    {'@type': 'JobPosting', 'title': 'Softwareentwickler Kundenportal (m/w/d)', 'datePosted': ISO(90), 'validThrough': ISO(5),
     'description': 'Entwicklung unserer Kundenplattform und Schnittstellen.'},
]}) + '</script></body></html>').encode()
PERSONIO_XML = f"""<?xml version="1.0" encoding="UTF-8"?><workzag-jobs>
<position><name>Head of E-Commerce (m/w/d)</name><department>Vertrieb</department><createdAt>{ISO(3)}T08:00:00+00:00</createdAt>
<jobDescriptions><jobDescription><name>Aufgaben</name><value>Onlineshop und Produktmarketing ausbauen.</value></jobDescription></jobDescriptions></position>
<position><name>Lagerhelfer (m/w/d)</name><createdAt>{ISO(3)}</createdAt></position></workzag-jobs>""".encode()

WEB = {
    'https://musterwerk-beispiel.de': ('text/html', b'<html><body><a href="/karriere">Karriere</a><a href="/impressum">Impressum</a></body></html>'),
    'https://musterwerk-beispiel.de/karriere': ('text/html', JSONLD_CAREER),
    'https://pixelhafen-beispiel.de': ('text/html', b'<html><body><a href="https://pixelhafen.jobs.personio.de/">Jobs</a></body></html>'),
    'https://pixelhafen.jobs.personio.de/xml': ('application/xml', PERSONIO_XML),
    'https://liste-beispiel.de': ('text/html', b'<html><body><a href="https://jobs.fremdportal.example/liste">Stellenangebote</a></body></html>'),
    'https://liste-beispiel.de/karriere': ('text/html', '<html><body><h2>Offene Stellen</h2><ul><li>UX/UI Designer (m/w/d)</li><li>Initiativbewerbung</li><li>Kaufmännische Sachbearbeitung (w/m/d)</li></ul></body></html>'.encode()),
}

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from tmpclean import cleanup_tmp  # noqa: E402 – Worker beenden, dann löschen (Windows)


class FakeWeb:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url, origin=None):
        self.calls.append(url)
        key = url.rstrip('/')
        if key in self.pages:
            return key, *self.pages[key]
        raise CrawlError('HTTP 404')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'p3.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self._orig = (imprint.FETCH, imprint.SLEEP)
        imprint.FETCH, imprint.SLEEP = FakeWeb(WEB), (lambda s: None)
        self.musterwerk = self.lead('Musterwerk Präzisionstechnik GmbH & Co. KG', 'https://musterwerk-beispiel.de', 'Amtsgericht Stuttgart', 'HRA 123456')
        self.pixel = self.lead('Pixelhafen UG (haftungsbeschränkt)', 'https://pixelhafen-beispiel.de', 'Amtsgericht Hamburg', 'HRB 998877')

    def tearDown(self):
        imprint.FETCH, imprint.SLEEP = self._orig
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, company, website, court='', number='', **extra):
        data = {'company': company, 'website': website, 'register_court': court, 'register_number': number, **extra}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid


class RegisterTests(Base):
    def test_parse_classify_match_and_minimize(self):
        res = bs.import_register(self.conn, {'text': REGISTER_TEXT})
        self.assertEqual(res['imported'], 5)  # Neueintragung, Umbenennung + Sitz, GF-Wechsel, Auflösung
        events = {(r['company'], r['event_type']): dict(r) for r in self.conn.execute('SELECT * FROM register_events')}
        self.assertIn(('Nordlicht Digital GmbH', 'neueintragung'), events)
        self.assertNotIn(('Nordlicht Digital GmbH', 'gf_wechsel'), events)  # Geschäftsführer in Neueintragung ist keine Änderung
        self.assertEqual(events[('Pixelhafen UG (haftungsbeschränkt)', 'umbenennung')]['lead_id'], self.pixel)
        self.assertIn(('Pixelhafen UG (haftungsbeschränkt)', 'sitzverlegung'), events)
        gf = events[('Musterwerk Präzisionstechnik GmbH & Co. KG', 'gf_wechsel')]
        self.assertEqual((gf['lead_id'], gf['published_at']), (self.musterwerk, ISO(5)))
        self.assertNotIn('*05.06.1985', gf['text'])  # Geburtsdaten entfernt
        self.assertNotIn('1985', gf['text'])
        self.assertIsNone(events[('Nordlicht Digital GmbH', 'neueintragung')]['lead_id'])
        stop = next(s for s in bs.list_signals(self.conn, {}) if s['category'] == 'aufloesung')
        self.assertEqual(stop['polarity'], 'contra')
        self.assertTrue(stop['old'])
        umb = next(s for s in bs.list_signals(self.conn, {}) if s['category'] == 'umbenennung')
        self.assertIn('brand', umb['offers'])
        self.assertTrue(umb['contra'] and umb['questions'] and umb['uncertainties'])

    def test_duplicate_announcements_and_csv(self):
        bs.import_register(self.conn, {'text': REGISTER_TEXT})
        again = bs.import_register(self.conn, {'text': REGISTER_TEXT})
        self.assertEqual((again['imported'], again['duplicates']), (0, 5))
        csv_text = f'datum;gericht;registernummer;firma;text\n{D(5)};Amtsgericht Stuttgart;HRA 123456;Musterwerk Präzisionstechnik GmbH & Co. KG;Bestellt als Geschäftsführer: Neumann, Nina\n'
        res = bs.import_register(self.conn, {'csv': csv_text})
        self.assertEqual(res['imported'], 1)
        gf_signals = [s for s in bs.list_signals(self.conn, {'lead_id': self.musterwerk}) if s['category'] == 'gf_wechsel']
        self.assertEqual(len(gf_signals), 1)            # gleiches Ereignis aus zweiter Quelle zusammengeführt
        self.assertEqual(len(gf_signals[0]['sources']), 2)
        with self.assertRaises(ValueError):
            bs.import_register(self.conn, {'text': ''})

    def test_suppressed_company_is_flagged(self):
        from sales_tool.company_data import add_suppression
        add_suppression(self.conn, 'register', ('Amtsgericht Stuttgart', 'HRB 765432'), 'Widerspruch')
        res = bs.import_register(self.conn, {'text': REGISTER_TEXT})
        self.assertEqual(res['suppressed'], 1)
        sig = next(s for s in bs.list_signals(self.conn, {}) if s['company'] == 'Nordlicht Digital GmbH')
        self.assertEqual(sig['suppressed'], 1)


class JobTests(Base):
    def test_partial_career_failure_is_disclosed(self):
        def fetch(url, origin):
            if url == 'https://example.org':
                return url, 'text/html', b'<a href="/karriere">Karriere</a><a href="/jobs">Jobs</a>'
            if url.endswith('/karriere'):
                raise CrawlError('HTTP 403')
            return url, 'text/html', b'<html><body>Keine passenden Stellen</body></html>'
        with mock.patch.object(imprint, 'FETCH', side_effect=fetch):
            jobs, log = bs.scan_career('https://example.org')
        self.assertEqual(jobs, [])
        self.assertTrue(any('Unvollständige Prüfung' in item for item in log))

    def test_career_fetch_failure_is_not_an_empty_result(self):
        def fetch(url, origin):
            if url == 'https://example.org':
                return url, 'text/html', b'<a href="/karriere">Karriere</a>'
            raise CrawlError('HTTP 403')
        with mock.patch.object(imprint, 'FETCH', side_effect=fetch):
            with self.assertRaisesRegex(CrawlError, 'Karriereseiten konnten nicht geprüft'):
                bs.scan_career('https://example.org')

    def test_classification_with_pro_and_contra(self):
        hits = bs.classify_job('Online-Marketing Manager (m/w/d)', 'SEO und Content')
        self.assertEqual(list(hits)[0], 'web')
        p = bs.job_signal_payload({'title': 'Softwareentwickler Kundenportal (m/w/d)', 'text': 'Schnittstellen', 'source_type': 'manuell',
                                   'published_at': ISO(5)}, self.musterwerk)
        self.assertIn('software', p['areas'])
        self.assertTrue(any('beweist keinen externen' in c for c in p['contra']))
        self.assertTrue(any('Inhouse' in c for c in p['contra']))
        self.assertIsNone(bs.job_signal_payload({'title': 'Lagerhelfer (m/w/d)', 'source_type': 'manuell'}, None))

    def test_old_and_expired_postings(self):
        old = bs.job_signal_payload({'title': 'Prozessmanager Digitalisierung (m/w/d)', 'source_type': 'manuell', 'published_at': ISO(200)}, 1)
        self.assertTrue(any('200 Tage alt' in c for c in old['contra']))
        expired = bs.job_signal_payload({'title': 'Marketing Manager (m/w/d)', 'source_type': 'manuell', 'published_at': ISO(70), 'valid_through': ISO(3)}, 1)
        self.assertEqual(expired['polarity'], 'contra')
        unknown = bs.job_signal_payload({'title': 'Marketing Manager (m/w/d)', 'source_type': 'manuell'}, 1)
        self.assertTrue(any('unbekannt' in u for u in unknown['uncertainties']))

    def test_career_page_jsonld_personio_and_fallback(self):
        jobs, log = bs.scan_career('https://musterwerk-beispiel.de')
        self.assertEqual({j['title'] for j in jobs}, {'Online-Marketing Manager (m/w/d)', 'Prozessmanager Digitalisierung (w/m/d)', 'Softwareentwickler Kundenportal (m/w/d)'})
        self.assertEqual(next(j for j in jobs if 'Marketing' in j['title'])['published_at'], ISO(10))
        pj, _ = bs.scan_career('https://pixelhafen-beispiel.de')
        self.assertEqual([j['source_type'] for j in pj], ['ats_feed_personio', 'ats_feed_personio'])
        lj, llog = bs.scan_career('https://liste-beispiel.de')
        self.assertNotIn('https://jobs.fremdportal.example/liste', imprint.FETCH.calls)  # fremdes Portal nicht gelesen
        self.assertEqual([j['title'] for j in lj], ['UX/UI Designer (m/w/d)', 'Kaufmännische Sachbearbeitung (w/m/d)'])

    def test_scan_queue_stores_signals_and_dedupes_with_manual_import(self):
        res = bs.enqueue_scans(self.conn, [self.musterwerk, self.pixel], self.db)
        self.assertEqual(len(res['queued']), 2)
        bs.wait_scans()
        sigs = bs.list_signals(self.conn, {'lead_id': self.musterwerk})
        self.assertEqual(len([s for s in sigs if s['kind'] == 'job']), 3)
        mk = next(s for s in sigs if 'Online-Marketing' in s['title'])
        self.assertNotIn('hr@musterwerk', json.dumps(mk))
        excerpt = self.conn.execute("SELECT excerpt FROM job_signals WHERE title LIKE 'Online-Marketing%'").fetchone()[0]
        self.assertNotIn('0711 123456', excerpt)        # Kontaktdaten aus Anzeigentext entfernt
        bs.import_jobs(self.conn, {'text': 'Online-Marketing Manager (w/m/d)\nWebsite und Kampagnen', 'lead_id': self.musterwerk, 'published_at': D(9)})
        mk2 = [s for s in bs.list_signals(self.conn, {'lead_id': self.musterwerk}) if 'Online-Marketing' in s['title']]
        self.assertEqual(len(mk2), 1)
        self.assertEqual(len(mk2[0]['sources']), 2)
        bs.enqueue_scans(self.conn, [self.musterwerk], self.db)  # erneuter Scan: keine neuen Signale
        bs.wait_scans()
        self.assertEqual(len([s for s in bs.list_signals(self.conn, {'lead_id': self.musterwerk}) if s['kind'] == 'job']), 3)
        pix = bs.list_signals(self.conn, {'lead_id': self.pixel})
        self.assertEqual([s['title'] for s in pix], ['Stellenanzeige: Head of E-Commerce (m/w/d)'])  # Lagerhelfer nicht relevant


class CorrelationTests(Base):
    def site_score(self, lead_id, design=10, web=70, process=60):
        a = self.conn.execute("INSERT INTO website_audits(lead_id, url, status, finished_at) VALUES (?, 'x', 'done', datetime('now'))", (lead_id,)).lastrowid
        vid = self.conn.execute('SELECT id FROM score_versions WHERE active=1').fetchone()[0]
        self.conn.execute("INSERT INTO website_scores(audit_id, lead_id, version_id, design, web, process, coverage, basis_json) VALUES (?,?,?,?,?,?,90,'{}')",
                          (a, lead_id, vid, design, web, process))
        self.conn.execute("""INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, method, certainty)
                             VALUES (?, ?, 'B3_cta_above_fold', 'web', 'Sichtbarer Anfrageaufruf', 'auffaellig', 3, 'Kein CTA', 'dom', 'beobachtet')""", (a, lead_id))
        self.conn.commit()

    def test_independent_sources_form_hypothesis_with_counter_and_missing(self):
        bs.import_register(self.conn, {'text': REGISTER_TEXT})
        bs.import_jobs(self.conn, {'text': 'Online-Marketing Manager (m/w/d)\nWebsite, SEO', 'lead_id': self.musterwerk, 'published_at': D(10)})
        self.site_score(self.musterwerk)
        res = bs.correlate(self.conn, self.musterwerk)
        themes = {h['theme']: h for h in res['hypotheses']}
        web = themes['web']
        self.assertEqual(web['strength'], 'mehrere unabhängige Hinweise')
        self.assertEqual({e['kind'] for e in web['evidence']}, {'job', 'website'})
        self.assertTrue(web['hypothesis'].startswith('Möglicherweise'))
        self.assertTrue(any('besetzt' in m for m in web['missing']))
        self.assertTrue(any('beweist keinen' in c for c in web['counter']))
        self.assertIn('brand', themes)  # GF-Wechsel + Marketing-Stelle
        self.assertTrue(any('Website-Bewertung zeigt' in c for c in themes['brand']['counter']))  # Design-Potenzial gering
        self.assertIn('keine Kausalität', res['notice'])
        stored = self.conn.execute('SELECT COUNT(*) FROM signal_correlations WHERE lead_id=?', (self.musterwerk,)).fetchone()[0]
        self.assertEqual(stored, len(res['hypotheses']))

    def test_contradiction_dissolution_caps_score(self):
        alt = self.lead('Altlast Handels GmbH', 'https://altlast-beispiel.de', 'Amtsgericht München', 'HRB 222333')
        bs.import_register(self.conn, {'text': REGISTER_TEXT})
        bs.import_jobs(self.conn, {'text': 'Marketing Manager (m/w/d)\nE-Commerce', 'lead_id': alt, 'published_at': D(3)})
        res = bs.correlate(self.conn, alt)
        self.assertTrue(res['contradictions'])
        self.assertTrue(all(h['score'] <= 10 for h in res['hypotheses']))
        self.assertEqual(bs.signal_strength_for_scoring(self.conn, alt)[0], 0)

    def test_single_source_is_weak_and_old_signals_count_less(self):
        bs.import_jobs(self.conn, {'text': 'Marketing Manager (m/w/d)', 'lead_id': self.pixel, 'published_at': D(5)})
        fresh = bs.correlate(self.conn, self.pixel)['hypotheses'][0]
        self.assertIn('Nur eine Quellenart', ' '.join(fresh['counter']))
        self.assertNotEqual(fresh['strength'], 'mehrere unabhängige Hinweise')
        other = self.lead('Langsam GmbH', 'https://langsam-beispiel.de')
        bs.import_jobs(self.conn, {'text': 'Marketing Manager (m/w/d)', 'lead_id': other, 'published_at': D(300)})
        old = bs.correlate(self.conn, other)['hypotheses'][0]
        self.assertLess(old['score'], fresh['score'])
        self.assertTrue(any('älter als 6 Monate' in m for m in old['missing']))

    def test_scoring_uses_real_signals_and_promote(self):
        bs.import_register(self.conn, {'text': REGISTER_TEXT})
        score, basis = bs.signal_strength_for_scoring(self.conn, self.musterwerk)
        self.assertEqual(score, 100)
        self.assertIn('ungeprüft', basis)
        sig = next(s for s in bs.list_signals(self.conn, {'lead_id': self.musterwerk}) if s['category'] == 'gf_wechsel')
        with self.assertRaisesRegex(ValueError, 'bestätigte'):
            bs.promote_to_lead(self.conn, sig['id'])
        bs.update_signal(self.conn, sig['id'], {'status': 'bestaetigt'})
        bs.promote_to_lead(self.conn, sig['id'])
        lead = self.conn.execute('SELECT signal_type, signal_date FROM leads WHERE id=?', (self.musterwerk,)).fetchone()
        self.assertEqual((lead['signal_type'], lead['signal_date']), ('expansion', ISO(5)))
        with self.assertRaisesRegex(ValueError, 'bereits'):
            bs.promote_to_lead(self.conn, sig['id'])
        from sales_tool import website_scorer as ws
        self.assertEqual(ws._signal_score({'_buying_signal': (70, 'x'), 'signal_type': 'kein_signal'}), (70, 'x'))

    def test_assign_unassigned_signal(self):
        bs.import_register(self.conn, {'text': REGISTER_TEXT})
        nord = next(s for s in bs.list_signals(self.conn, {'unassigned': '1'}) if s['company'] == 'Nordlicht Digital GmbH')
        lid = self.lead('Nordlicht Digital GmbH', 'https://nordlicht-beispiel.de')
        bs.update_signal(self.conn, nord['id'], {'lead_id': lid})
        self.assertEqual(self.conn.execute("SELECT lead_id FROM register_events WHERE company='Nordlicht Digital GmbH'").fetchone()[0], lid)
        with self.assertRaises(ValueError):
            bs.update_signal(self.conn, nord['id'], {'status': 'egal'})


class SignalsHttpTests(Base):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_flow(self):
        status, res = self.call('/api/signals/register-import', 'POST', {'text': REGISTER_TEXT})
        self.assertEqual((status, res['imported']), (201, 5))
        status, res = self.call('/api/signals/career-scan', 'POST', {'lead_ids': [self.musterwerk]})
        self.assertEqual(status, 202)
        bs.wait_scans()
        status, summary = self.call('/api/signals/summary')
        self.assertGreaterEqual(summary['new'], 5)
        self.assertEqual(summary['scans'][0]['status'], 'done')
        status, lst = self.call(f'/api/signals?lead_id={self.musterwerk}')
        self.assertTrue(lst)
        status, upd = self.call(f"/api/signals/{lst[0]['id']}", 'PATCH', {'status': 'bestaetigt'})
        self.assertEqual(upd['status'], 'bestaetigt')
        status, corr = self.call(f'/api/leads/{self.musterwerk}/correlation', 'POST', {})
        self.assertEqual(status, 200)
        status, got = self.call(f'/api/leads/{self.musterwerk}/correlation')
        self.assertEqual(len(got['hypotheses']), len(corr['hypotheses']))
        status, err = self.call('/api/signals/job-import', 'POST', {'evil': 1})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
