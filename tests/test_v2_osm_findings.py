"""2.0.0-dev44: Befund des Eigentümers mit dem Stuttgart-Auszug – „viel ausgefiltert, kaum Websites“.

- Jeder ausgefilterte Treffer zählt mit Grund; „ohne Rechtsform“ ist bei Handwerk der häufigste und wird erklärt.
- Domain-Vorschläge enthalten den Ort (elektro-mueller-stuttgart.de) – vorher fiel der Ort ganz heraus.
- Firmenname im Impressum mit anderer Wortreihenfolge passt als Vorschlag („Malerbetrieb Huber“ / „Huber Malerbetrieb e.K.“);
  andere Namen weiterhin nicht.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import sweep as sw  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402

OSM_ITEMS = [
    {'name': 'Elektro Fiktiv', 'industry': 'electrician', '_industry_matched': True, 'zip': '70191', 'city': 'Stuttgart', 'distance_km': 1.0},
    {'name': 'Malerbetrieb Beispiel', 'industry': 'painter', '_industry_matched': True, 'zip': '70191', 'city': 'Stuttgart', 'distance_km': 1.2},
    {'name': 'Sanitär Muster', 'industry': 'plumber', '_industry_matched': True, 'zip': '70192', 'city': 'Stuttgart', 'distance_km': 2.0},
    {'name': 'Dach Fiktiv GmbH', 'industry': 'roofer', '_industry_matched': True, 'zip': '70191', 'city': 'Stuttgart', 'distance_km': 1.5},
    {'name': 'Weit Weg GmbH', 'industry': 'roofer', '_industry_matched': True, 'zip': '71000', 'city': 'Woanders', 'distance_km': 40.0},
]


class FilterReasonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / 'f.sqlite3')
        init_db(self.conn)
        self.sid = self.conn.execute("INSERT INTO sweeps(label, params_json) VALUES ('Test', '{}')").lastrowid
        self.run = sw._run_record(self.conn, 'osm', self.sid, {})

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def store(self, **ctx):
        ctx = {'industries': [], 'keywords': [], 'org_kinds': sw.ORG_KINDS_DEFAULT, 'radius_km': 10, **ctx}
        return sw.store_items(self.conn, self.sid, self.run, 'osm', [dict(x) for x in OSM_ITEMS], ctx)

    def test_reasons_are_counted(self):
        c = self.store(include_sole=False)
        self.assertEqual(c['filtered'], 4)
        self.assertEqual(c['filtered_why'], {'ohne_rechtsform': 3, 'entfernung': 1})
        self.assertEqual(c['new'], 1)
        self.assertEqual(sum(c['filtered_why'].values()), c['filtered'], 'jeder ausgefilterte Treffer hat einen Grund')

    def test_with_sole_traders_they_come_in(self):
        c = self.store(include_sole=True)
        self.assertEqual(c['filtered_why'], {'entfernung': 1})
        self.assertEqual(c['new'], 4)


class WebsiteGuessTests(unittest.TestCase):
    def test_town_variants(self):
        g = sw.domain_guesses('Elektro Müller', 'Stuttgart')
        self.assertIn('elektro-mueller-stuttgart.de', g)
        self.assertIn('elektromuellerstuttgart.de', g)
        self.assertEqual(g[:2], ['elektromueller.de', 'elektro-mueller.de'], 'bisherige Reihenfolge bleibt vorn')
        self.assertLessEqual(len(g), 9)
        self.assertEqual(sw.domain_guesses('Elektro Müller'), ['elektromueller.de', 'elektro-mueller.de', 'elektro.de', 'elektromueller.com', 'elektro-mueller.com'])

    def test_word_order_in_imprint(self):
        cand = {'name': 'Malerbetrieb Huber', 'register_id': '', 'zip': '70191', 'register_court': ''}
        status, why = sw._match(cand, {'legal_name': {'value': 'Huber Malerbetrieb e.K.'}, 'zip': {'value': '70191'}})
        self.assertEqual(status, 'wahrscheinlich', 'nur Vorschlag, muss bestätigt werden')
        self.assertIsNone(sw._match(cand, {'legal_name': {'value': 'Huber Bau GmbH'}, 'zip': {'value': '70191'}})[0])
        self.assertIsNone(sw._match(cand, {'legal_name': {'value': 'Huber Malerbetrieb e.K.'}, 'zip': {'value': '80331'}})[0], 'andere PLZ')
        self.assertFalse(sw._same_words('Müller', 'Müller Bau GmbH'), 'ein einzelnes Wort genügt nicht')
        self.assertTrue(sw._same_words('Bäckerei Ähre', 'Bäckerei Ähre Inh. Max Muster'))


if __name__ == '__main__':
    unittest.main()
