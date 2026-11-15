"""2.0.0-dev48: Befund des Eigentümers (Stuttgart, 50 km): GLEIF verbrauchte das ganze Budget von 300 neuen Firmen,
Wikidata, OpenStreetMap und TED wurden „übersprungen – Budget erreicht“.

Ursache: Seit der Umstellung auf den gemeinsamen Auftragsdienst läuft jede Quelle als eigener Schritt (run_sweep mit
only=[quelle]); die faire Aufteilung rechnete dann nur mit dieser einen Quelle. Die bisherige Prüfung rief run_sweep direkt
mit allen Quellen auf und sah den Fehler nicht. Hier läuft die Suche über den echten Auftragsweg.
Alle Firmen sind fiktiv; keine Netzabfragen (nachgebaute Quellen aus test_sprintB_sweep).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402

from sales_tool import sweep as sw  # noqa: E402
from sales_tool.research import jobs  # noqa: E402


class BudgetViaJobsTests(tb.SweepBase):
    def run_via_jobs(self, **params):
        p = {'place': '70173', 'radius_km': 30, 'osm_online': True, **params}
        s = sw.start_sweep(self.conn, p, self.db, start=False)
        jobs.run_until_idle(self.db)
        return sw.sweep_detail(self.conn, s['id'])

    def test_first_source_cannot_use_up_the_whole_budget(self):
        # GLEIF allein liefert hier 4 neue Firmen; bei Budget 4 und zwei Quellen stehen ihr höchstens 2 zu
        d = self.run_via_jobs(sources=['gleif', 'osm'], operative=False, budget={'max_companies': 4, 'max_websites': 0, 'max_minutes': 30})
        self.assertEqual(d['progress']['osm']['status'], 'fertig', d['progress']['osm'])
        self.assertLessEqual(d['progress']['gleif'].get('new', 0), 2, d['progress']['gleif'])
        self.assertGreaterEqual(d['progress']['osm'].get('new', 0), 1)
        self.assertLessEqual(len(self.cands(status='neu')), 4)

    def test_unused_share_goes_to_later_sources(self):
        self.net.fail.add('gleif')
        d = self.run_via_jobs(sources=['gleif', 'osm'], industries=['elektro', 'metall'],
                              budget={'max_companies': 1, 'max_websites': 0, 'max_minutes': 30})
        self.assertEqual(d['progress']['gleif']['status'], 'fehler')
        self.assertEqual(d['progress']['osm'].get('new', 0), 1)



if __name__ == '__main__':
    unittest.main()
