"""2.0.0-dev25: Produktreview M18 – Zusatzaufträge und Leistungsänderungen.

Abnahme: Der Ursprungsumfang bleibt erkennbar.
- Zusatzauftrag nur zu einem angenommenen Auftrag; Nummer mit Zähler -Z1, gleiche Firma und Chance; Anlass Pflicht.
- Der Auftrag bleibt unverändert (Dokument, Status, Abnahme); der Zusatzauftrag nennt Bezug, Anlass und bisherigen Umfang.
- Auftragsumfang: ursprünglicher Auftrag plus angenommene Zusatzaufträge; offene getrennt; Revisionen zählen nicht doppelt.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import addenda as ad  # noqa: E402
from sales_tool import handover as ho  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import revisions as rv  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'z.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Zusatz Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()
        confirm_need(self.conn, self.lead)
        self.order = self.offer([{'service': 'webdesign', 'size': 'M'}], project_label='Neue Website')
        self.accept(self.order['id'])

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def offer(self, positions, **kw):
        return make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': positions, **kw})

    def accept(self, pid):
        release_offer(self.conn, pid)
        of.set_status(self.conn, pid, {'status': 'gesendet_manuell'})
        of.set_status(self.conn, pid, {'status': 'angenommen'})

    def addendum(self, positions, reason='Kundenwunsch: Englische Sprachversion', of_id=None):
        return self.offer(positions, project_label='Englische Version', addendum_of=of_id or self.order['id'], addendum_reason=reason)


class AddendumTests(Base):
    def test_addendum_keeps_original_scope_visible(self):
        before = self.conn.execute('SELECT customer_json, status FROM proposals WHERE id=?', (self.order['id'],)).fetchone()
        prep = ad.prepare(self.conn, self.order['id'])
        self.assertEqual((prep['next_no'], prep['lead_id'], prep['opportunity_id']), (1, self.lead, self.order['opportunity_id']))
        z1 = self.addendum([{'service': 'texte', 'qty': 3}])
        self.assertEqual(z1['number'], self.order['number'] + '-Z1')
        self.assertEqual((z1['addendum_of'], z1['addendum_no'], z1['opportunity_id']), (self.order['id'], 1, self.order['opportunity_id']))
        md = customer_markdown(z1['customer'])
        self.assertTrue(md.startswith('# Zusatzauftrag: Englische Version'))
        self.assertIn(f"**Zusatzauftrag 1** zu Angebot {self.order['number']}", md)
        self.assertIn('bleibt unverändert', md)
        self.assertIn('Anlass: Kundenwunsch: Englische Sprachversion', md)
        self.assertIn('Bisher beauftragt:', md)
        self.assertIn('- Webdesign & Website-Umsetzung', md)
        after = self.conn.execute('SELECT customer_json, status FROM proposals WHERE id=?', (self.order['id'],)).fetchone()
        self.assertEqual(tuple(after), tuple(before), 'Auftrag unverändert')
        sc = ad.scope(self.conn, self.order['id'])
        self.assertEqual([a['number'] for a in sc['addenda']], [z1['number']])
        self.assertEqual((sc['accepted_net_eur'], sc['open_net_eur']), (0, z1['customer']['net_eur']))
        self.assertEqual(sc['total_net_eur'], self.order['customer']['net_eur'], 'offener Zusatzauftrag zählt nicht zum Auftrag')
        # Revision des Zusatzauftrags vor der Zusage: bleibt Zusatzauftrag, zählt nicht doppelt
        z1b = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'texte', 'qty': 2}],
                                        'revision_of': z1['id'], 'revision_reason': 'Nur zwei Seiten übersetzen'})
        self.assertEqual(z1b['number'], z1['number'] + '-R2')
        self.assertEqual(z1b['addendum_of'], self.order['id'])
        self.assertIn('Zusatzauftrag 1', customer_markdown(z1b['customer']))
        self.accept(z1b['id'])
        sc = ad.scope(self.conn, z1b['id'])
        self.assertEqual([a['id'] for a in sc['addenda']], [z1b['id']])
        self.assertEqual(sc['total_net_eur'], round(self.order['customer']['net_eur'] + z1b['customer']['net_eur'], 2))
        # Zweiter Zusatzauftrag – auch vom Zusatzauftrag aus angelegt, bezieht er sich auf den Auftrag
        z2 = self.addendum([{'service': 'seo_geo', 'size': 'S'}], 'Kundenwunsch: Suchmaschinenoptimierung', of_id=z1b['id'])
        self.assertEqual(z2['number'], self.order['number'] + '-Z2')
        self.assertEqual(ad.prepare(self.conn, z2['id'])['addendum_of'], self.order['id'])
        self.assertEqual(len(ad.scope(self.conn, self.order['id'])['addenda']), 2)
        # Abnahme des Auftrags und des Zusatzauftrags getrennt
        self.assertEqual(ho.state(self.conn, z1b['id'])['number'], z1b['number'])
        self.assertEqual(ho.state(self.conn, self.order['id'])['status'], 'in_arbeit')

    def test_rules(self):
        draft = self.offer([{'service': 'logo', 'size': 'S'}])
        with self.assertRaisesRegex(ValueError, 'angenommenen Auftrag'):
            self.addendum([{'service': 'texte', 'qty': 1}], of_id=draft['id'])
        with self.assertRaisesRegex(ValueError, 'Anlass'):
            self.addendum([{'service': 'texte', 'qty': 1}], reason='')
        with self.assertRaisesRegex(ValueError, 'nicht beides'):
            self.offer([{'service': 'texte', 'qty': 1}], addendum_of=self.order['id'], addendum_reason='Kundenwunsch x', revision_of=draft['id'], revision_reason='egal egal')
        other = self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv KG')").lastrowid
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'andere'):
            make_proposal(self.conn, {'lead_id': other, 'tax_mode': 'regel_19', 'positions': [{'service': 'texte', 'qty': 1}],
                                      'addendum_of': self.order['id'], 'addendum_reason': 'Kundenwunsch x'})
        with self.assertRaisesRegex(ValueError, 'Zusatzauftrag'):
            rv.prepare(self.conn, self.order['id'])
        st = of.state(self.conn, self.order['id'])
        self.assertTrue(st['addable'])
        self.assertFalse(of.state(self.conn, draft['id'])['addable'])


if __name__ == '__main__':
    unittest.main()
