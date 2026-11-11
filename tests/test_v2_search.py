"""2.0.0-dev6: Befunde aus dem Praxistest (Suche in PLZ 70191, 11.11.2026).

- „70191“ mit „nur dieser Ort“ lieferte ganz Stuttgart: 300 Treffer, davon 2 in 70191. Jetzt gilt die PLZ.
- Die erste Quelle verbrauchte das ganze Budget, OpenStreetMap lief nie. Jetzt wird das Budget auf die Quellen verteilt.
Alle Firmen sind fiktiv; die Quellen sind Attrappen.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402

from sales_tool import lead_finder as lf  # noqa: E402


class PostcodeOnlyTests(tb.SweepBase):
    def test_postcode_with_only_this_place_means_that_postcode(self):
        d = self.run_sweep(place='70173', radius_km=0, sources=['gleif'])
        cands = self.cands()
        self.assertEqual({c['zip'] for c in cands}, {'70173'})
        self.assertIn('Reith Spezialkabel GmbH', {c['name'] for c in cands})
        self.assertEqual(d['progress']['_area']['postcode_only'], '70173')

    def test_place_name_still_covers_the_whole_town(self):
        self.run_sweep(place='Stuttgart', radius_km=0, sources=['gleif'], operative=False)
        self.assertGreater(len({c['zip'] for c in self.cands()}), 1)

    def test_postcode_with_radius_is_not_restricted(self):
        d = self.run_sweep(place='70173', radius_km=30, sources=['gleif'], operative=False)
        self.assertEqual(d['progress']['_area']['postcode_only'], '')
        self.assertGreater(len({c['zip'] for c in self.cands()}), 1)

    def test_osm_queries_the_postcode_area_and_keeps_entries_without_postcode_tag(self):
        queries = []
        real = lf.overpass

        def spy(query, ua, **kw):
            queries.append(query)
            return real(query, ua, **kw)
        with mock.patch.object(lf, 'overpass', spy):
            d = self.run_sweep(place='70173', radius_km=0, sources=['osm'], industries=['elektro', 'metallbau'])
            self.assertTrue(queries and all('"postal_code"="70173"' in q and '(area.plz)' in q and 'around:' not in q for q in queries))
            # Eintrag mit anderer PLZ am Eintrag (70178) fällt heraus; Eintrag ohne PLZ-Angabe liegt laut Abfrage im Gebiet
            # und bleibt erhalten (hier als bereits bekannte Firma gezählt)
            self.assertNotIn('Elektro Sommer GmbH', {c['name'] for c in self.cands()})
            self.assertGreaterEqual(d['progress']['osm']['known'] + d['progress']['osm']['new'] + d['progress']['osm']['merged'], 1)
            queries.clear()
            self.run_sweep(place='Stuttgart', radius_km=0, sources=['osm'], industries=['elektro'])
            self.assertTrue(queries and all('around:' in q and 'postal_code' not in q for q in queries))


class FairBudgetTests(tb.SweepBase):
    def test_first_source_cannot_use_up_the_whole_budget(self):
        d = self.run_sweep(sources=['gleif', 'osm'], industries=['elektro', 'metall'], operative=False,
                           budget={'max_companies': 2, 'max_websites': 0, 'max_minutes': 30})
        by_source = {}
        for c in self.cands(status='neu'):
            for s in c.get('sources') or [c.get('source')]:
                by_source[s if isinstance(s, str) else s.get('source')] = True
        self.assertEqual(d['progress']['osm']['status'], 'fertig')  # früher: „übersprungen – Budget erreicht“
        self.assertGreaterEqual(d['progress']['osm'].get('new', 0), 1)
        self.assertLessEqual(d['progress']['gleif'].get('new', 0), 1)
        self.assertLessEqual(len(self.cands(status='neu')), 2)

    def test_unused_share_goes_to_later_sources(self):
        self.net.fail.add('gleif')
        d = self.run_sweep(sources=['gleif', 'osm'], industries=['elektro', 'metall'],
                           budget={'max_companies': 1, 'max_websites': 0, 'max_minutes': 30})
        self.assertEqual(d['progress']['gleif']['status'], 'fehler')
        self.assertEqual(d['progress']['osm'].get('new', 0), 1)  # die ausgefallene Quelle hat nichts vom Budget verbraucht


if __name__ == '__main__':
    unittest.main()
