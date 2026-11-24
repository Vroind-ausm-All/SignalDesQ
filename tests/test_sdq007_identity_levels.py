"""SDQ-007: Website-Zuordnung in „Finden“ – Stufen und harte Gegenbelege.

Stufen: 'belegt' (Registernummer, Registergericht und Name stimmen) · 'wahrscheinlich' (nur Vorschlag, ein Mensch bestätigt)
· keine Zuordnung. Ein harter Gegenbeleg schließt jede Zuordnung aus, auch als Vorschlag: andere Registernummer, anderes
Registergericht, anderer Name, andere Rechtsform, andere PLZ, anderer Ort. Vorher wurden z. B. „Müller Elektro GmbH“ und das
Impressum „Müller Elektro e.K.“ als wahrscheinlich gleich vorgeschlagen. Alle Daten fiktiv, keine Abrufe nach außen."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sprintB_sweep import GLEIF_CSV, SweepBase  # noqa: E402

from sales_tool import imprint  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402


def cand(**k):
    d = {'name': '', 'zip': '', 'city': '', 'register_id': '', 'register_court': ''}
    d.update(k)
    return d


def fields(**k):
    return {a: {'value': b} for a, b in k.items()}


class CounterEvidenceTests(unittest.TestCase):
    def assertNone(self, c, f, reason):
        status, why = sw._match(c, f)
        self.assertIsNone(status, why)
        self.assertIn(reason, why)

    def test_other_legal_form(self):
        self.assertNone(cand(name='Müller Elektro GmbH', zip='70173'), fields(legal_name='Müller Elektro e.K.', zip='70173'), 'andere Rechtsform')

    def test_management_gmbh_is_not_the_kg(self):
        self.assertNone(cand(name='Muster Bau GmbH & Co. KG', zip='70173'), fields(legal_name='Muster Bau Verwaltungs GmbH', zip='70173'),
                        'andere Rechtsform')

    def test_other_city_when_one_zip_is_missing(self):
        self.assertNone(cand(name='Müller Elektro GmbH', city='Stuttgart'), fields(legal_name='Müller Elektro GmbH', zip='20095', city='Hamburg'),
                        'anderer Ort')

    def test_generic_single_word_is_not_a_name_match(self):
        self.assertNone(cand(name='Elektro GmbH', zip='70173'), fields(legal_name='Elektro Schmidt GmbH', zip='70173'), 'anderer Firmenname')

    def test_other_register_court_and_number_and_zip(self):
        self.assertNone(cand(name='Muster GmbH', register_id='HRB 123', register_court='Amtsgericht Stuttgart'),
                        fields(legal_name='Muster GmbH', register_number='HRB 123', register_court='Amtsgericht Berlin'), 'anderes Registergericht')
        self.assertNone(cand(name='Muster GmbH', register_id='HRB 123'), fields(legal_name='Muster GmbH', register_number='HRB 999'),
                        'andere Registernummer')
        self.assertNone(cand(name='Muster GmbH', zip='70173'), fields(legal_name='Muster GmbH', zip='70174'), 'andere PLZ')

    def test_still_matching(self):
        same = [(cand(name='Reith Spezialkabel GmbH', zip='70173'), fields(legal_name='Reith Spezialkabel GmbH', zip='70173')),
                (cand(name='Huber Malerbetrieb', zip='70191'), fields(legal_name='Malerbetrieb Huber e.K.', zip='70191')),
                (cand(name='Muster Bau GmbH & Co. KG'), fields(legal_name='Muster Bau GmbH & Co. KG', city='Stuttgart')),
                (cand(name='Schmidt Elektrotechnik GmbH', city='Esslingen am Neckar'), fields(legal_name='Schmidt Elektrotechnik GmbH', city='Esslingen'))]
        for c, f in same:
            with self.subTest(c['name']):
                self.assertEqual(sw._match(c, f)[0], 'wahrscheinlich')
        c = cand(name='Muster GmbH', register_id='HRB 123', register_court='Amtsgericht Stuttgart')
        f = fields(legal_name='Muster GmbH', register_number='HRB 123', register_court='Amtsgericht Stuttgart')
        self.assertEqual(sw._match(c, f)[0], 'belegt')


class FinderEvidenceTests(SweepBase):
    def test_rejected_domain_is_named_in_the_evidence(self):
        sw.import_file(self.conn, GLEIF_CSV + '"L00000000000000000012","Nirgendwo Technik GmbH","Weg 9","","Stuttgart","DE","70190","HRB 77","GENERAL","ACTIVE","2018",""\n',
                       {'plz': '70'})
        c = next(x for x in self.cands() if x['name'] == 'Nirgendwo Technik GmbH')

        def fake_research(domain, include_persons=True):
            return {'status': 'ok', 'home_url': f'https://{domain}/', 'fields': {'legal_name': {'value': 'Nirgendwo Technik e.K.'}, 'zip': {'value': '70190'}}}
        with mock.patch.object(imprint, 'research_domain', side_effect=fake_research):
            res = sw.find_website(self.conn, c['id'])
        self.assertEqual(res['status'], 'nicht_gefunden')
        row = next(x for x in self.cands() if x['name'] == 'Nirgendwo Technik GmbH')
        self.assertEqual((row['website'], row['website_status']), ('', 'nicht_gefunden'))
        self.assertIn('Gegenbeleg', row['website_evidence'])
        self.assertIn('andere Rechtsform', row['website_evidence'])


if __name__ == '__main__':
    unittest.main()
