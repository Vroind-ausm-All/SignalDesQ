"""v1.19 – Fehlerbehebung „automatische Datenübertragung ins Firmenprofil“.

Nachgestellt werden die Wege, auf denen bis v1.18 keine Firmendaten im Lead ankamen:
1. Übernahme mit Website-*Vorschlag* (Empfehlung A): Website wurde entfernt, gelesene Impressumsdaten verworfen,
   bestätigen ließ sich danach nichts mehr.
2. Übernahme mit Website „laut Quelle“ (OSM/Wikidata): kein Impressum gelesen.
3. Website von Hand eingetragen: kein Impressum gelesen.
Fiktive Firma „Kesselwerk Anlagenbau GmbH“, Webseiten sind Attrappen (kein Netzwerk).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintC_report as tc  # noqa: E402
import test_sprintS5_workday as t5  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import lead_imprint as li  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402
from sales_tool.company_data import add_suppression  # noqa: E402
from sales_tool.research import jobs  # noqa: E402


class CompanyDataBase(t5.DayBase):
    def setUp(self):
        super().setUp()
        li.ENABLED = True

    def tearDown(self):
        jobs.wait_idle(self.db, timeout=20)
        li.ENABLED = False
        super().tearDown()

    def candidate(self, website, status, imprint_json='{}', name='Kesselwerk Anlagenbau GmbH'):
        sid = self.conn.execute("INSERT INTO sweeps(label, params_json) VALUES ('t', '{}')").lastrowid
        run = sw._run_record(self.conn, 'osm', sid, {})
        cid = self.conn.execute("""INSERT INTO discovery_candidates(run_id, sweep_id, source, name, website, zip, city, status, sources_json,
                                   website_status, website_evidence, imprint_json, legal_form) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (run, sid, 'osm', name, website, '70565', 'Stuttgart', 'neu', '[{"source": "osm", "url": ""}]', status,
                                 'Vorschlag: Name und PLZ im Impressum – bitte prüfen' if status == 'wahrscheinlich' else 'Website laut OSM',
                                 imprint_json, 'GmbH')).lastrowid
        self.conn.commit()
        return cid

    def run_jobs(self):
        jobs.run_until_idle(self.db, kinds=('lead_imprint',))
        jobs.wait_idle(self.db, timeout=20)

    def lead_row(self, lid):
        return self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()


class TransferTests(CompanyDataBase):
    def test_suggested_website_can_be_confirmed_after_takeover(self):
        import json
        res = imprint.research_domain(tc.SITE)
        imp = json.dumps({'fields': res['fields'], 'imprint_url': res['imprint_url'], 'source_type': res['source_type'], 'checked_at': res['checked_at']})
        cid = self.candidate(tc.SITE, 'wahrscheinlich', imp)
        out = self.ok('POST', f'/api/sweep-candidates/{cid}/decision', {'decision': 'uebernehmen'})
        lid = out['lead_id']
        self.assertEqual(out['website_suggestion'], tc.SITE)
        self.assertEqual(self.lead_row(lid)['website'], '', 'Empfehlung A: Vorschlag ist noch nicht die Website der Firma')
        cd = self.file(lid)['company_data']
        self.assertEqual(cd['state'], 'vorschlag')
        self.assertIn('register_number', cd['suggestion']['fields'])
        r = self.ok('POST', f'/api/leads/{lid}/website-suggestion', {'decision': 'bestaetigen'})
        lead = self.lead_row(lid)
        self.assertEqual(lead['website'], tc.SITE)
        self.assertEqual((lead['legal_name'], lead['register_number'], lead['street'], lead['business_phone']),
                         ('Kesselwerk Anlagenbau GmbH', 'HRB 765432', 'Industriestraße 5', '+49 711 9876543'))
        self.assertEqual(r['status']['state'], 'uebernommen')
        self.assertIsNone(self.file(lid)['company_data']['suggestion'])

    def test_source_website_reads_imprint_automatically_on_takeover(self):
        cid = self.candidate(tc.SITE, 'quelle', name='Kesselwerk')
        out = self.ok('POST', f'/api/sweep-candidates/{cid}/decision', {'decision': 'uebernehmen'})
        self.assertTrue(out['imprint_queued'])
        self.run_jobs()
        lead = self.lead_row(out['lead_id'])
        self.assertEqual((lead['company'], lead['legal_name'], lead['register_number'], lead['zip'], lead['business_email']),
                         ('Kesselwerk', 'Kesselwerk Anlagenbau GmbH', 'HRB 765432', '70565', 'info@kesselwerk-beispiel.de'),
                         'leere Felder gefüllt, vorhandener Name bleibt')
        self.assertTrue(lead['imprint_checked_at'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM decision_contacts WHERE lead_id=?', (out['lead_id'],)).fetchone()[0], 0,
                         'Personen nie automatisch')
        cd = self.file(out['lead_id'])['company_data']
        self.assertEqual(cd['state'], 'uebernommen')
        self.assertIn('legal_name', cd['filled'])

    def test_manual_website_triggers_transfer_and_keeps_existing_values(self):
        lead = self.ok('POST', '/api/leads', {'company': 'Kesselwerk', 'website': tc.SITE, 'industry': 'Industrie & B2B-Technik'})
        self.run_jobs()
        self.assertEqual(self.lead_row(lead['id'])['register_number'], 'HRB 765432')
        other = self.ok('POST', '/api/leads', {'company': 'Ohne Website GmbH', 'industry': 'Sonstige'})
        self.conn.execute("UPDATE leads SET business_phone='+49 711 1111111' WHERE id=?", (other['id'],))
        self.conn.commit()
        self.assertEqual(self.file(other['id'])['company_data']['state'], 'ohne_website')
        self.ok('PATCH', f"/api/leads/{other['id']}", {'website': tc.SITE})
        self.run_jobs()
        row = self.lead_row(other['id'])
        self.assertEqual((row['legal_name'], row['business_phone']), ('Kesselwerk Anlagenbau GmbH', '+49 711 1111111'), 'vorhandene Werte bleiben')

    def test_read_button_and_switch(self):
        self.ok('PUT', '/api/settings/auto-imprint', {'enabled': False})
        lead = self.ok('POST', '/api/leads', {'company': 'Kesselwerk', 'website': tc.SITE, 'industry': 'Sonstige'})
        self.assertFalse(self.conn.execute("SELECT 1 FROM research_tasks WHERE kind='lead_imprint'").fetchone(), 'abgeschaltet: nichts automatisch')
        self.assertFalse(self.file(lead['id'])['company_data']['auto'])
        self.ok('POST', f"/api/leads/{lead['id']}/company-data/read", {})
        self.run_jobs()
        self.assertEqual(self.lead_row(lead['id'])['legal_name'], 'Kesselwerk Anlagenbau GmbH', 'auf Knopfdruck trotzdem')
        self.assertEqual(self.call('PUT', '/api/settings/auto-imprint', {'enabled': 'ja'})[0], 400)

    def test_errors_are_visible_and_suppression_blocks_fetch(self):
        lead = self.ok('POST', '/api/leads', {'company': 'Weg GmbH', 'website': 'https://gibtsnicht-beispiel.de', 'industry': 'Sonstige'})
        self.run_jobs()
        cd = self.file(lead['id'])['company_data']
        self.assertIn(cd['state'], ('fehler', 'kein_impressum'))
        self.assertTrue(cd['detail'])
        blocked = self.ok('POST', '/api/leads', {'company': 'Gesperrt GmbH', 'industry': 'Sonstige'})
        add_suppression(self.conn, 'domain', 'https://sperr-beispiel.de', 'Widerspruch')
        self.conn.commit()
        self.conn.execute("UPDATE leads SET website='https://sperr-beispiel.de' WHERE id=?", (blocked['id'],))
        self.conn.commit()
        st, err = self.call('POST', f"/api/leads/{blocked['id']}/company-data/read", {})
        self.assertEqual(st, 400, err)

    def test_disabled_outside_running_app(self):
        li.ENABLED = False
        lead = self.ok('POST', '/api/leads', {'company': 'Kesselwerk', 'website': tc.SITE, 'industry': 'Sonstige'})
        self.assertIsNone(li.queue(self.conn, self.db, lead['id']))


if __name__ == '__main__':
    unittest.main()
