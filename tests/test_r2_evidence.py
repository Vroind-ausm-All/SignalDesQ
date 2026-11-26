"""R2.3 Evidence-Vertrag v2: Fundstelle, Prüfsumme, Extraktorversion, deterministische Gegenprüfung. Nur erfundene Daten."""
import unittest

from sales_tool.research import evidence as ev


TEXT = 'Team\nGeschäftsführerin: Anna Beispiel\nZentrale: 0711 000000'


class EvidenceV2Tests(unittest.TestCase):
    def test_text_ref_has_all_contract_fields(self):
        r = ev.text_ref('full_name', 'Anna Beispiel', TEXT, 'https://beispiel.example/team', 'test-v1', chash=ev.content_hash(b'x'),
                        published_at='2026-11-01', legal_entity='Beispiel GmbH')
        self.assertEqual(ev.check_ref(r), [])
        for key in ('value', 'normalized', 'source_url', 'locator', 'content_hash', 'fetched_at', 'published_at', 'extractor',
                    'legal_entity', 'review_status'):
            self.assertIn(key, r)
        self.assertTrue(r['content_hash'].startswith('sha256:'))
        loc = r['locator']
        self.assertEqual(TEXT[loc['start']:loc['end']], 'Anna Beispiel')
        self.assertTrue(ev.verify_ref(r, text=TEXT))

    def test_ref_without_locator_is_rejected(self):
        r = ev.make_ref('full_name', 'Anna Beispiel', 'https://beispiel.example/', 'test-v1', {})
        self.assertIn('Fundstelle fehlt', ev.check_ref(r))
        self.assertFalse(ev.verify_ref(r, text=TEXT))
        claim, problems = ev.keep_with_refs({'evidence_refs': {'full_name': r}}, ('full_name',))
        self.assertIsNone(claim)
        self.assertTrue(problems)
        self.assertEqual(ev.check_ref(None), ['kein Beleg v2'])

    def test_invented_value_gets_no_ref(self):
        self.assertIsNone(ev.text_ref('full_name', 'Erfundene Person', TEXT, 'https://beispiel.example/', 'test-v1'))
        self.assertIsNone(ev.json_ref('full_name', 'Erfunden', {'name': 'Anna'}, 0, ['name'], 'https://beispiel.example/', 'test-v1'))

    def test_verify_detects_changed_source_and_tampered_span(self):
        r = ev.text_ref('full_name', 'Anna Beispiel', TEXT, 'https://beispiel.example/', 'test-v1')
        self.assertFalse(ev.verify_ref(r, text=TEXT.replace('Anna', 'Anne')))  # anderer Quellinhalt → andere Prüfsumme
        bad = {**r, 'locator': {**r['locator'], 'start': r['locator']['start'] + 1}}
        self.assertFalse(ev.verify_ref(bad, text=TEXT))
        wrong = {**r, 'value': 'Max Muster'}
        self.assertFalse(ev.verify_ref(wrong, text=TEXT))

    def test_json_path_ref(self):
        block = {'@type': 'Organization', 'employee': [{'@type': 'Person', 'name': 'Anna Beispiel', 'jobTitle': 'Geschäftsführerin'}]}
        r = ev.json_ref('job_title', 'Geschäftsführerin', block, 0, ['employee', 0, 'jobTitle'], 'https://beispiel.example/', 'test-v1')
        self.assertEqual(ev.check_ref(r), [])
        self.assertTrue(ev.verify_ref(r, blocks=[block]))
        self.assertFalse(ev.verify_ref(r, blocks=[{'employee': [{'jobTitle': 'Vertrieb'}]}]))
        self.assertIsNone(ev.json_ref('job_title', 'Geschäftsführerin', block, 0, ['employee', 5, 'jobTitle'], 'https://b.example/', 't'))

    def test_pdf_ref_needs_page_and_quote(self):
        r = ev.make_ref('job_title', 'Vorstand', 'https://beispiel.example/bericht.pdf', 'test-v1', {'kind': 'pdf', 'page': 3, 'quote': 'Der Vorstand'})
        self.assertEqual(ev.check_ref(r), [])
        self.assertTrue(ev.verify_ref(r, text='Seite 3: Der Vorstand berichtet'))
        self.assertIn('PDF-Seite oder Wortlaut fehlt', ev.check_ref({**r, 'locator': {'kind': 'pdf', 'page': 0}}))

    def test_v1_validator_still_rejects_invented_values(self):
        checked, rejected = ev.validate_fields({'legal_name': {'value': 'Erfunden GmbH', 'excerpt': ''}}, TEXT, 'https://b.example/')
        self.assertEqual(rejected, ['legal_name'])


if __name__ == '__main__':
    unittest.main()
