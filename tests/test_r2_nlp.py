"""R2.5 optionales Profil „nlp“: Zuordnung, Beleg, Schalter – mit einer Attrappe statt spaCy (läuft ohne Modell)."""
import re
import unittest
from unittest import mock

from sales_tool.public_contacts import extract_public_contacts
from sales_tool.research import evidence as ev
from sales_tool.research import settings
from sales_tool.research.extractors import nlp

URL = 'https://www.beispiel-technik.example/team'


class _Ent:
    def __init__(self, text, start, label='PER'):
        self.text, self.start_char, self.label_ = text, start, label


class _Doc:
    def __init__(self, ents):
        self.ents = ents


class FakeNLP:
    """Erkennt erfundene Namen aus einer festen Liste – wie ein NER-Modell, aber deterministisch."""
    NAMES = ('Nina Blau', 'Timo Kraft', 'Peter Klein', 'Bernd Kern', 'Ben Yilmaz', 'Anna Beispiel')

    def pipe(self, texts):
        for t in texts:
            yield _Doc([_Ent(n, m.start()) for n in self.NAMES for m in re.finditer(re.escape(n), t)])


class NlpTests(unittest.TestCase):
    def test_nearest_title_in_prose_and_evidence(self):
        raw = 'Seit 2019 führt Nina Blau als Geschäftsführerin die Agentur. Unterstützt wird sie von Timo Kraft, unserem Head of Marketing.'
        got = {p['full_name']: p for p in nlp.persons(raw, URL, nlp=FakeNLP())}
        self.assertEqual(got['Nina Blau']['job_title'], 'Geschäftsführerin')
        self.assertIn('Marketing', got['Timo Kraft']['job_title'])
        for p in got.values():
            self.assertEqual(p['method'], 'nlp')
            for r in p['evidence_refs'].values():
                self.assertTrue(ev.verify_ref(r, text=raw))

    def test_title_on_neighbour_line_and_no_title_no_candidate(self):
        raw = 'Personalleitung\nBen Yilmaz\n\nAnna Beispiel ist bei uns seit 2010.'
        got = {p['full_name']: p for p in nlp.persons(raw, URL, nlp=FakeNLP())}
        self.assertEqual(list(got), ['Ben Yilmaz'])
        self.assertEqual(got['Ben Yilmaz']['job_title'], 'Personalleitung')

    def test_quotes_and_testimonials_are_skipped(self):
        raw = '„Großartige Zusammenarbeit!“ – Peter Klein, Geschäftsführer der Fremdfirma AG\nKundenstimme: Anna Beispiel, Inhaberin'
        self.assertEqual(nlp.persons(raw, URL, nlp=FakeNLP()), [])

    def test_off_by_default_and_never_confirmed(self):
        settings.reset()
        self.assertFalse(settings.get()['nlp'])
        self.assertFalse(nlp.enabled())
        raw = 'Ihr Ansprechpartner ist Bernd Kern, Betriebsleiter am Standort Süd.'
        crawl = {'pages': [{'url': URL, 'raw_text': raw}]}
        self.assertEqual(extract_public_contacts(crawl)['people'], [])
        with mock.patch.object(nlp, 'enabled', lambda: True), mock.patch.object(nlp, '_model', lambda: FakeNLP()):
            people = extract_public_contacts(crawl)['people']
        self.assertEqual([(p['full_name'], p['role_key'], p['status']) for p in people], [('Bernd Kern', 'betrieb_leitung', 'kandidat')])

    def test_hosted_server_cannot_switch_on(self):
        from sales_tool import hosting
        self.assertEqual(hosting.LIMITS['nlp'], (False,))
        with self.assertRaises(ValueError):
            settings.validate({'nlp': 'ja'})


@unittest.skipUnless(nlp.available(), 'NLP-Profil optional (requirements-lock-nlp.txt, requirements-nlp-model.txt)')
class RealModelTests(unittest.TestCase):
    def test_real_model_proposes_with_evidence(self):
        raw = 'Ihr Ansprechpartner für Großprojekte ist Bernd Kern, Betriebsleiter am Standort Süd.'
        got = nlp.persons(raw, URL)
        self.assertEqual([p['full_name'] for p in got], ['Bernd Kern'])
        self.assertTrue(all(ev.verify_ref(r, text=raw) for r in got[0]['evidence_refs'].values()))


if __name__ == '__main__':
    unittest.main()
