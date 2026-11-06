"""Empfehlung A (v1.15): Website-Vorschläge kennzeichnen – automatisch zählt nur „belegt“ (Registernummer im Impressum).

Fiktive Firmen, Impressums-Recherche durch Attrappe ersetzt (keine Netzabfragen).
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402


def fake_research(domain, include_persons=True):
    if domain.startswith('frisch'):  # Name + PLZ passen, Registernummer fehlt → nur „wahrscheinlich“
        return {'status': 'ok', 'home_url': f'https://{domain}/', 'imprint_url': f'https://{domain}/impressum',
                'fields': {'legal_name': {'value': 'Frisch-Lamm Metzgereigesellschaft mbH'}, 'zip': {'value': '70173'},
                           'register_number': {'value': 'HRB 1234567'}, 'vat_id': {'value': 'DE999000099'}}}
    if domain == 'reith-spezialkabel.de':
        return {'status': 'ok', 'home_url': 'https://reith-spezialkabel.de/', 'imprint_url': 'https://reith-spezialkabel.de/impressum',
                'fields': {'legal_name': {'value': 'Reith Spezialkabel GmbH'}, 'register_number': {'value': 'HRB 14671'}}}
    raise imprint.CrawlError('Domain existiert nicht')


class SuggestionTests(tb.SweepBase):
    def setUp(self):
        super().setUp()
        sw.import_file(self.conn, tb.GLEIF_CSV.replace('"HRB 8602"', '""'), {'plz': '70'})
        self.cands_by = lambda: {c['name']: c for c in self.cands()}
        ids = [c['id'] for c in self.cands()]
        sw.queue_websites(self.conn, {'ids': ids}, self.db, start=False)
        with mock.patch.object(imprint, 'research_domain', side_effect=fake_research):
            sw._web_worker(self.db)
        self.frisch = self.cands_by()['"Frisch-Lamm" Metzgereigesellschaft mbH']

    def test_probable_is_labelled_and_takes_nothing_from_imprint(self):
        f = self.frisch
        self.assertEqual(f['website_status'], 'wahrscheinlich')
        self.assertTrue(f['website_evidence'].startswith('Vorschlag:'))
        self.assertEqual(f['register_id'], '', 'keine Registernummer aus einem nur vorgeschlagenen Impressum')
        self.assertEqual(self.cands_by()['Reith Spezialkabel GmbH']['website_status'], 'belegt')

    def test_takeover_keeps_suggestion_out_of_lead(self):
        res = sw.decide(self.conn, self.frisch['id'], 'uebernehmen')
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertEqual((lead['website'], lead['vat_id']), ('', ''), 'Vorschlag wird nicht zur Firmen-Website, nichts automatisch übernommen')
        self.assertTrue(self.conn.execute("SELECT 1 FROM activities WHERE lead_id=? AND detail LIKE 'Website-Vorschlag%noch nicht bestätigt%'",
                                          (res['lead_id'],)).fetchone())
        reith = self.cands_by()['Reith Spezialkabel GmbH']
        lead2 = self.conn.execute('SELECT website FROM leads WHERE id=?', (sw.decide(self.conn, reith['id'], 'uebernehmen')['lead_id'],)).fetchone()
        self.assertEqual(lead2['website'], 'https://reith-spezialkabel.de', '„belegt“ wird übernommen')

    def test_confirm_after_takeover_fills_lead(self):
        lid = sw.decide(self.conn, self.frisch['id'], 'uebernehmen')['lead_id']
        c = sw.review_website(self.conn, self.frisch['id'], {'decision': 'bestaetigen'})
        self.assertEqual(c['website_status'], 'bestaetigt')
        self.assertIn('von dir bestätigt', c['website_evidence'])
        lead = self.conn.execute('SELECT website, vat_id FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((lead['website'], lead['vat_id']), (self.frisch['website'], 'DE999000099'))
        with self.assertRaises(ValueError):
            sw.review_website(self.conn, self.frisch['id'], {'decision': 'bestaetigen'})

    def test_reject_is_remembered(self):
        rejected = self.frisch['website'].split('//')[1]
        c = sw.review_website(self.conn, self.frisch['id'], {'decision': 'ablehnen'})
        self.assertEqual((c['website'], c['website_status']), ('', 'abgelehnt'))
        tried = []
        with mock.patch.object(imprint, 'research_domain', side_effect=lambda d, include_persons=True: tried.append(d) or fake_research(d)):
            sw.find_website(self.conn, self.frisch['id'])
        self.assertNotIn(rejected, tried, 'abgelehnte Domain wird nicht erneut vorgeschlagen')
        self.assertTrue(tried, 'andere Domain-Varianten werden weiter geprüft')
        with self.assertRaises(ValueError):
            sw.review_website(self.conn, self.frisch['id'], {'decision': 'vielleicht'})


class SuggestionHttpTests(tb.SweepHttpTests):
    def test_endpoints(self):
        sw.import_file(self.conn, tb.GLEIF_CSV.replace('"HRB 8602"', '""'), {'plz': '70'})
        f = next(c for c in self.cands() if c['name'].startswith('"Frisch'))
        self.conn.execute("UPDATE discovery_candidates SET website='https://frisch.example', website_status='wahrscheinlich' WHERE id=?", (f['id'],))
        self.conn.commit()
        self.assertEqual(self.call(f"/api/sweep-candidates/{f['id']}/website", 'POST', {'decision': 'bestaetigen'})[0], 200)
        self.assertEqual(self.call(f"/api/sweep-candidates/{f['id']}/website", 'POST', {'decision': 'bestaetigen'})[0], 400)
        self.assertEqual(self.call('/api/sweep-candidates/999999/website', 'POST', {'decision': 'ablehnen'})[0], 404)


if __name__ == '__main__':
    unittest.main()
