"""2.0.0-dev34: Produktreview M10 – globale Suche.

Abnahme: Firma, Chance und Angebotsnummer über ein Suchfeld. Personen werden nicht durchsucht; Platzhalterzeichen im
Suchbegriff wirken nicht als Joker; nur lesend. Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import chances  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.search import search  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 's.sqlite3')
        prepare_database(self.db)
        c = self.conn = connect(self.db)
        self.a = c.execute("INSERT INTO leads(company, legal_name, website, stage) VALUES ('Bäckerei Sonnenschein', 'Sonnenschein Backwaren GmbH', 'https://sonnenschein.example', 'termin')").lastrowid
        self.b = c.execute("INSERT INTO leads(company, stage, permission) VALUES ('Sonnenhof 100% Bio KG', 'gesperrt', 'nicht_kontaktieren')").lastrowid
        c.execute("INSERT INTO decision_contacts(lead_id, full_name) VALUES (?, 'Maria Sonnenberg')", (self.a,))
        c.commit()
        self.oid = chances.create(c, self.a, {'title': 'Online-Shop für Torten'})['id']
        self.p = make_proposal(c, {'lead_id': self.a, 'opportunity_id': self.oid, 'tax_mode': 'regel_19', 'project_label': 'Tortenshop',
                                   'positions': [{'service': 'webshop', 'size': 'S'}]})

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def keys(self, q):
        return {g['key']: [i['title'] for i in g['items']] for g in search(self.conn, q)['groups']}

    def test_firm_chance_offer_and_invoice(self):
        r = self.keys('sonnen')
        self.assertEqual(r['firmen'], ['Sonnenhof 100% Bio KG', 'Bäckerei Sonnenschein'], 'Treffer am Namensanfang zuerst')
        self.assertNotIn('Maria Sonnenberg', str(r), 'Personen werden nicht durchsucht')
        self.assertEqual(self.keys('Backwaren')['firmen'], ['Bäckerei Sonnenschein'], 'Firmierung')
        self.assertEqual(self.keys('torten')['chancen'], ['Online-Shop für Torten'])
        self.assertEqual(self.keys('tortenshop')['angebote'], [f"{self.p['number']} Tortenshop"])
        self.assertEqual(self.keys(self.p['number'][-4:])['angebote'], [f"{self.p['number']} Tortenshop"], 'Teil der Angebotsnummer')
        gesperrt = next(i for g in search(self.conn, 'sonnenhof')['groups'] for i in g['items'])
        self.assertIn('gesperrt', gesperrt['detail'])
        self.conn.execute("INSERT INTO invoices(number, lead_id, buyer_name, status) VALUES ('RE-2026-0042', ?, 'Bäckerei Sonnenschein', 'offen')", (self.a,))
        self.conn.commit()
        self.assertEqual(self.keys('0042')['rechnungen'], ['RE-2026-0042'])

    def test_wildcards_short_and_long_input(self):
        self.assertEqual(self.keys('100%'), {'firmen': ['Sonnenhof 100% Bio KG']})
        self.assertEqual(self.keys('%%'), {}, '% ist kein Joker')
        self.assertEqual(self.keys('__'), {}, '_ ist kein Joker')
        self.assertEqual(search(self.conn, 'a')['groups'], [])
        with self.assertRaisesRegex(ValueError, '80'):
            search(self.conn, 'x' * 81)
        self.assertIn('Nichts gefunden', search(self.conn, 'zzzz')['notice'])


if __name__ == '__main__':
    unittest.main()
