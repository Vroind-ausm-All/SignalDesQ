"""2.0.0-dev22: Produktreview M15 Teil 2 – optionale Positionen ohne Doppelkalkulation.

Abnahme: „Optionen werden nicht versehentlich doppelt kalkuliert.“ Optionale Positionen stehen im Angebot, zählen aber weder
im Festpreis, in Summen, Stunden, Abschlägen noch in Rechnungen. Gewünschte Optionen werden per Revision fest aufgenommen.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import pricing as pr  # noqa: E402
from sales_tool import revisions as rv  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

CORE = [{'service': 'webdesign', 'size': 'M'}]
WITH_OPT = CORE + [{'service': 'seo_geo', 'size': 'S', 'optional': True}, {'service': 'pflege', 'size': 'S', 'optional': True}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'o.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Option Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)


class OptionTests(Base):
    def test_options_never_count(self):
        base = pr.build_quote(self.conn, {'positions': CORE, 'tax_mode': 'regel_19'})
        q = pr.build_quote(self.conn, {'positions': WITH_OPT, 'tax_mode': 'regel_19'})
        c, i = q['customer'], q['internal']
        for k in ('net_eur', 'once_net_eur', 'monthly_net_eur', 'vat_eur', 'total_eur', 'billing'):
            self.assertEqual(c[k], base['customer'][k], k)
        self.assertEqual((i['estimated_hours'], i['total_price_eur']), (base['internal']['estimated_hours'], base['internal']['total_price_eur']))
        self.assertEqual([o['position'] for o in c['options']], [2, 3])
        self.assertEqual(len(c['positions']), 3)
        self.assertNotIn('Garantie für Rankings oder Nennungen in KI-Antworten', c['excluded'], 'Ausschlüsse nur aus festen Positionen')
        md = customer_markdown(c)
        self.assertIn('| 2 | SEO- & GEO-Optimierung (optional) |', md)
        self.assertIn('– nicht im Festpreis |', md)
        self.assertIn('## Optionale Positionen', md)
        with self.assertRaisesRegex(ValueError, 'fest im Angebot'):
            pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'S', 'optional': True}]})
        with self.assertRaisesRegex(ValueError, 'optional'):
            pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'S', 'optional': 'ja'}]})

    def test_invoice_and_deposit_ignore_options_and_revision_takes_option(self):
        acc.save_settings(self.conn, {'company_name': 'Fiktiv Studio', 'street': 'Musterweg 1', 'zip': '70191', 'city': 'Stuttgart',
                                      'tax_number': '99/999/99999', 'iban': 'DE89370400440532013000'})
        confirm_need(self.conn, self.lead)
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': WITH_OPT, 'tax_mode': 'regel_19'})
        self.assertTrue(any('optionale Position' in h for h in of.state(self.conn, p['id'])['hints']))
        self.assertTrue(rv.prepare(self.conn, p['id'])['payload']['positions'][1]['optional'])
        v2 = make_proposal(self.conn, {'lead_id': self.lead, 'tax_mode': 'regel_19', 'revision_of': p['id'], 'revision_reason': 'Kunde nimmt SEO dazu',
                                       'positions': CORE + [{'service': 'seo_geo', 'size': 'S'}, {'service': 'pflege', 'size': 'S', 'optional': True}]})
        self.assertIn('Option fest übernommen: SEO- & GEO-Optimierung', ' '.join(v2['customer']['revision']['changes']))
        self.assertGreater(v2['customer']['once_net_eur'], p['customer']['once_net_eur'])
        release_offer(self.conn, v2['id'])
        of.set_status(self.conn, v2['id'], {'status': 'angenommen'})
        inv = acc.invoice_from_proposal(self.conn, {'proposal_id': v2['id'], 'mode': 'voll'})
        self.assertEqual(len(inv['lines']), 2, 'Pflege bleibt optional und wird nicht berechnet')
        self.assertEqual(inv['net_cents'], round(v2['customer']['once_net_eur'] * 100))


if __name__ == '__main__':
    unittest.main()
