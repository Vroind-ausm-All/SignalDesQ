"""Firmen-Bericht 2.0.0-dev66: Website finden & zuordnen, „Auf einen Blick“ (Kernfakten, Lücken, Aktualität).

Fiktive Firma „Kesselwerk Anlagenbau GmbH“ (Attrappen aus test_sprintC_report); jede andere Domain „gibt es nicht“.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_sprintC_report as base  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import report as rp  # noqa: E402
from sales_tool.company_data import add_suppression  # noqa: E402
from sales_tool.research import safe_urls  # noqa: E402
from sales_tool.research.safe_urls import DomainMissing  # noqa: E402

DOMAIN = 'kesselwerk-beispiel.de'


class FakeWebDns(base.FakeWeb):
    """Wie die Attrappe aus Sprint C, aber unbekannte Domains haben keinen DNS-Eintrag."""
    def __init__(self):
        self.hosts = []

    def __call__(self, url, origin=None):
        host = url.split('://', 1)[1].split('/')[0]
        self.hosts.append(host)
        if host != DOMAIN:
            raise DomainMissing('Domain existiert nicht (kein DNS-Eintrag).')
        return super().__call__(url, origin)


class GlanceBase(base.ReportBase):
    def setUp(self):
        super().setUp()
        self.web = FakeWebDns()
        self.p = mock.patch.object(imprint, 'FETCH', self.web)
        self.p.start()
        safe_urls._DNS_STATE.update(at=1e12, ok=True)

    def tearDown(self):
        safe_urls._DNS_STATE.update(at=-1e9, ok=True)
        self.p.stop()
        super().tearDown()

    def report(self, lid):
        rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
        rp._worker(self.db)
        return rp.report_view(self.conn, lead_id=lid)


class WebsiteFindingTests(GlanceBase):
    def test_proven_website_is_entered_and_all_steps_run(self):
        lid = self.lead('Kesselwerk Anlagenbau GmbH', website='', street='Industriestraße 5', zip='70565', city='Stuttgart',
                        business_email='info@kesselwerk-beispiel.de', business_phone='0711 9876543')
        v = self.report(lid)
        steps = v['report']['steps']
        self.assertEqual(steps['webfinden']['status'], 'fertig', steps['webfinden'])
        self.assertIn('belegt', steps['webfinden']['detail'])
        self.assertEqual(self.web.hosts[0], DOMAIN, 'E-Mail-Domain der Firma zuerst – keine geratenen Domains nötig')
        lead = self.conn.execute('SELECT website, register_number FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual(lead['website'], base.SITE)
        self.assertEqual(lead['register_number'], 'HRB 765432', 'Impressum-Schritt läuft danach mit der gefundenen Website')
        self.assertEqual({k: s['status'] for k, s in steps.items()}, {k: 'fertig' for k, _ in rp.STEPS})
        self.assertTrue(self.conn.execute("SELECT 1 FROM activities WHERE lead_id=? AND detail LIKE 'Website gefunden und belegt%'", (lid,)).fetchone())

    def test_brand_name_gives_suggestion_and_confirm_fills_website(self):
        lid = self.lead('Kessel Anlagen Stuttgart', website='', street='Industriestr. 5', zip='70565', city='Stuttgart',
                        business_email='anfrage@kesselwerk-beispiel.de', business_phone='+49 711 9876543')
        v = self.report(lid)
        steps = v['report']['steps']
        self.assertEqual(steps['webfinden']['status'], 'hinweis')
        self.assertIn('Vorschlag', steps['webfinden']['detail'])
        for key in rp.NEEDS_WEBSITE:
            self.assertEqual(steps[key]['status'], 'übersprungen', key)
        self.assertEqual(v['report']['status'], 'teilweise')
        self.assertEqual(v['website_suggestion']['url'], base.SITE)
        self.assertIn('Keine bestätigte Website – Vorschlag liegt vor, bitte prüfen', v['summary']['gaps'])
        lead = self.conn.execute('SELECT website, next_step FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual(lead['website'], '', 'Vorschlag wird nicht automatisch eingetragen (Empfehlung A)')
        self.assertEqual(lead['next_step'], 'Website-Vorschlag im Firmen-Bericht prüfen')
        r = rp.decide_suggestion(self.conn, lid, {'decision': 'bestaetigen'})
        self.assertEqual(r['website'], base.SITE)
        self.assertEqual(self.conn.execute('SELECT website FROM leads WHERE id=?', (lid,)).fetchone()[0], base.SITE)
        with self.assertRaises(ValueError):
            rp.decide_suggestion(self.conn, lid, {'decision': 'bestaetigen'})

    def test_rejected_suggestion_is_not_proposed_again(self):
        lid = self.lead('Kessel Anlagen Stuttgart', website='', street='Industriestr. 5', zip='70565', business_phone='+49 711 9876543',
                        business_email='anfrage@kesselwerk-beispiel.de')
        self.report(lid)
        rp.decide_suggestion(self.conn, lid, {'decision': 'ablehnen'})
        self.web.hosts.clear()
        v = self.report(lid)
        self.assertNotIn(DOMAIN, self.web.hosts)
        self.assertIsNone(v['website_suggestion'])
        self.assertIn('gibt es nicht', v['report']['steps']['webfinden']['detail'])

    def test_suppressed_domain_is_not_entered(self):
        add_suppression(self.conn, 'domain', DOMAIN, 'Widerspruch')
        self.conn.commit()
        lid = self.lead('Kesselwerk Anlagenbau GmbH', website='', street='Industriestraße 5', zip='70565',
                        business_email='info@kesselwerk-beispiel.de', business_phone='0711 9876543')
        v = self.report(lid)
        self.assertEqual(v['report']['steps']['webfinden']['status'], 'übersprungen')
        self.assertIn('Sperrliste', v['report']['steps']['webfinden']['detail'])
        self.assertEqual(self.conn.execute('SELECT website FROM leads WHERE id=?', (lid,)).fetchone()[0], '')

    def test_blocked_company_report_does_nothing(self):
        lid = self.lead('Kesselwerk Anlagenbau GmbH', website='', business_email='info@kesselwerk-beispiel.de', permission='nicht_kontaktieren')
        r = rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
        self.assertEqual(r['skipped'][0]['reason'], 'gesperrt')
        self.assertEqual(self.web.hosts, [], 'keine Abfrage für gesperrte Firmen')

    def test_suggestion_on_blocked_company_is_refused(self):
        lid = self.lead('Kessel Anlagen Stuttgart', website='', street='Industriestr. 5', zip='70565', business_phone='+49 711 9876543',
                        business_email='anfrage@kesselwerk-beispiel.de')
        self.report(lid)
        self.conn.execute("UPDATE leads SET permission='nicht_kontaktieren' WHERE id=?", (lid,))
        self.conn.commit()
        with self.assertRaises(ValueError):
            rp.decide_suggestion(self.conn, lid, {'decision': 'bestaetigen'})
        self.assertEqual(self.conn.execute('SELECT website FROM leads WHERE id=?', (lid,)).fetchone()[0], '')

    def test_existing_website_is_kept(self):
        lid = self.lead()
        v = self.report(lid)
        self.assertEqual(v['report']['steps']['webfinden']['status'], 'fertig')
        self.assertIn('laut Firmendaten', v['report']['steps']['webfinden']['detail'])
        self.assertNotIn('kesselwerk.de', self.web.hosts, 'keine Suche, wenn die Website bekannt ist')


class GlanceTests(GlanceBase):
    def test_summary_lists_facts_gaps_and_contact_status(self):
        lid = self.lead()
        sm = self.report(lid)['summary']
        labels = {f['label']: f for f in sm['facts']}
        self.assertEqual(labels['Registernummer']['value'], 'HRB 765432')
        self.assertEqual(labels['Registernummer']['source'], 'Impressum')
        self.assertEqual(sm['steps_ok'], sm['steps_total'])
        self.assertIn('Website ohne Browser bewertet – Gestaltung und Screenshots fehlen', sm['gaps'])
        self.assertTrue(any('Kontakterlaubnis ungeklärt' in g for g in sm['gaps']), 'gefunden ≠ erlaubt')
        self.assertIn('ungeklärt', sm['permission'])
        self.assertFalse(sm['stale'])
        self.assertTrue(sm['highlights'], 'wichtigste Hinweise mit Beleg')
        self.assertTrue(all(h['text'] for h in sm['highlights']))

    def test_old_report_is_marked_stale(self):
        lid = self.lead()
        self.report(lid)
        self.conn.execute("UPDATE company_reports SET finished_at=date('now', '-120 days') WHERE lead_id=?", (lid,))
        self.conn.commit()
        sm = rp.report_view(self.conn, lead_id=lid)['summary']
        self.assertTrue(sm['stale'])
        self.assertGreaterEqual(sm['age_days'], 120)

    def test_view_is_read_only(self):
        lid = self.lead()
        self.report(lid)
        before = dict(self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone())
        n = self.conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        rp.report_view(self.conn, lead_id=lid)
        self.assertEqual(dict(self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()), before)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], n)

    def test_old_report_without_new_step_still_renders_and_reruns(self):
        lid = self.lead()
        steps = {k: {'label': v, 'status': 'fertig'} for k, v in rp.STEPS if k != 'webfinden'}
        rid = self.conn.execute("INSERT INTO company_reports(lead_id, status, steps_json, finished_at) VALUES (?, 'fertig', ?, datetime('now'))",
                                (lid, json.dumps(steps))).lastrowid
        self.conn.commit()
        v = rp.report_view(self.conn, rid=rid)
        self.assertEqual(v['summary']['steps_total'], len(rp.STEPS) - 1)
        rp._set(self.conn, rid, 'webfinden', status='fertig', detail='x')
        self.assertIn('webfinden', rp.report_view(self.conn, rid=rid)['report']['steps'])


class SuggestionHttpTests(GlanceBase):
    def test_report_suggestion_via_company_file_endpoint(self):
        """Gleicher Weg wie der Vorschlag in der Firmenakte (lead_imprint): Vorschlag sichtbar, bestätigen trägt ein."""
        import threading
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from sales_tool import lead_imprint
        from sales_tool.server import make_handler
        lid = self.lead('Kessel Anlagen Stuttgart', website='', street='Industriestr. 5', zip='70565', business_phone='+49 711 9876543',
                        business_email='anfrage@kesselwerk-beispiel.de')
        self.report(lid)
        self.assertEqual(lead_imprint.status(self.conn, lid)['state'], 'vorschlag', 'Vorschlag erscheint auch in der Firmenakte')
        srv = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def call(path, body):
                c = HTTPConnection('127.0.0.1', srv.server_address[1], timeout=10)
                c.request('POST', path, json.dumps(body), {'Content-Type': 'application/json'})
                r = c.getresponse()
                return r.status, json.loads(r.read() or b'{}')
            self.assertEqual(call(f'/api/leads/{lid}/website-suggestion', {'decision': 'vielleicht'})[0], 400)
            st, body = call(f'/api/leads/{lid}/website-suggestion', {'decision': 'bestaetigen'})
            self.assertEqual((st, body['decision'], body['website']), (200, 'bestaetigen', base.SITE))
            self.assertEqual(call(f'/api/leads/{lid}/website-suggestion', {'decision': 'bestaetigen'})[0], 400, 'kein offener Vorschlag mehr')
        finally:
            srv.shutdown()
            srv.server_close()
        self.conn.commit()
        acts = [r[0] for r in self.conn.execute("SELECT detail FROM activities WHERE lead_id=? AND detail LIKE 'Website-Vorschlag%'", (lid,))]
        self.assertEqual(len(acts), 1, acts)


if __name__ == '__main__':
    unittest.main()
