"""2.0.0-dev37: Produktreview M28 – Rubriken fachlich überarbeiten.

Abnahme: Pauschale Schrift-, Jahres-, Überschriften- und Navigationsregeln liefern Hinweise statt Urteile; Version dokumentiert.
- Ein Treffer dieser Faustregeln ist „hinweis“ mit Erklärung, warum die Regel irren kann.
- Hinweise zählen als geprüft, aber nie als Mangel: Sie verschieben die Priorität nicht nach oben und belegen keine Angebotsposition.
- Neue Bewertungsversion – ältere Bewertungen gelten als nicht vergleichbar.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_phase2_scoring import LEAD, PACKAGES, capture, facts  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import offer_basis  # noqa: E402
from sales_tool import website_scorer as ws  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


class RubricHintTests(unittest.TestCase):
    cfg = copy.deepcopy(ws.DEFAULT_CONFIG)

    def score(self, d):
        return ws.score(capture(d), LEAD, self.cfg, set(PACKAGES))

    def test_heuristics_are_hints_with_explanation_and_do_not_raise_priority(self):
        clean = self.score(facts())
        heur = self.score(facts(h1=0, h2=0, copyrightYear=2015, fontFamilies=['a', 'b', 'c', 'd', 'e', 'f'], navLinks=0))
        res = {f['rubric']: f for f in heur['findings']}
        for rid in ws.HINT_RUBRICS:
            self.assertEqual(res[rid]['result'], 'hinweis', rid)
            self.assertIn('Hinweis, kein Urteil', res[rid]['evidence'])
        self.assertFalse([f for f in heur['findings'] if f['result'] == 'auffaellig' and f['rubric'] in ws.HINT_RUBRICS])
        self.assertEqual(heur['coverage'], clean['coverage'], 'Hinweise zählen als geprüft')
        self.assertLessEqual(heur['potential'] or 0, clean['potential'] or 0, 'Faustregeln heben die Priorität nicht')
        self.assertEqual({f['rubric']: f['result'] for f in clean['findings'] if f['rubric'] in ws.HINT_RUBRICS},
                         {r: 'ok' for r in ws.HINT_RUBRICS})

    def test_new_version_and_hints_never_back_an_offer(self):
        self.assertTrue(ws.SCORE_ENGINE_VERSION.startswith('2.1'))
        tmp = tempfile.TemporaryDirectory()
        try:
            db = str(Path(tmp.name) / 'h.sqlite3')
            prepare_database(db)
            c = connect(db)
            lead = c.execute("INSERT INTO leads(company) VALUES ('Hinweis Fiktiv GmbH')").lastrowid
            a = c.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'https://h.example', 'done')", (lead,)).lastrowid
            c.execute("""INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, method, certainty, offer, review_status)
                         VALUES (?, ?, 'A6_font_consistency', 'design', 'Einheitliche Schriftverwendung', 'hinweis', 1, '6 Schriftfamilien', 'messung', 'beobachtet', 'brand', 'bestaetigt')""",
                      (a, lead))
            c.commit()
            p = make_proposal(c, {'lead_id': lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}]})
            b = offer_basis.for_proposal(c, p['id'])
            self.assertEqual(b['positions'][0]['basis'], 'ohne', 'ein Hinweis ist kein Beleg für ein Angebot')
            self.assertEqual(b['open_hypotheses'], 0)
            c.close()
        finally:
            cleanup_tmp(tmp)


if __name__ == '__main__':
    unittest.main()
