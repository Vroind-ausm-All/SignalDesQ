"""SDQ-001: Abrechnungsstand je Angebot – eine Abschlagsrechnung ist keine vollständige Abrechnung.

Vorher galt ein angenommenes Angebot als „berechnet“, sobald irgendeine Rechnung (auch ein Entwurf oder ein Abschlag über 40 %)
daran hing. Die restlichen 60 % verschwanden aus „Angenommen, noch nicht abgerechnet“ (Abrechnen, Heute, Angebotsliste, Akte).
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402
from test_accounting import SELLER, buyer  # noqa: E402

from sales_tool import accounting as acc  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.sales_workspace import make_proposal, proposal_rows  # noqa: E402
from sales_tool.today import potential  # noqa: E402
from sales_tool.workday import lead_file  # noqa: E402


class BillingStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / 'test.sqlite3')
        init_db(self.conn)
        acc.save_settings(self.conn, SELLER)
        cur = self.conn.execute("INSERT INTO leads(company, permission, stage) VALUES ('Beispiel Maschinenbau GmbH', 'opt_in', 'angebot')")
        self.lead_id = cur.lastrowid
        from sales_tool.pricing import save_override
        save_override(self.conn, {'service': 'logo', 'size': 'L', 'fixed_price': 10000})
        self.prop = make_proposal(self.conn, {'lead_id': self.lead_id, 'positions': [{'service': 'logo', 'size': 'L'}], 'tax_mode': 'regel_19'})
        self.conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (self.prop['id'],))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    # -- Hilfen
    def issue(self, inv):
        lines = [{k: x[k] for k in ('description', 'quantity', 'unit', 'unit_price_cents', 'vat_rate')} for x in inv['lines']]
        return acc.finalize_invoice(self.conn, acc.update_invoice(self.conn, inv['id'], {**buyer(), 'lines': lines})['id'])

    def deposit(self, pct=40):
        return acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id'], 'mode': 'abschlag', 'percent': pct})

    def billing(self):
        return acc.proposal_billing(self.conn, self.prop['id'])

    def unbilled_ids(self):
        return [p['id'] for p in acc.overview(self.conn)['accepted_without_invoice']]

    def row(self):
        return next(r for r in proposal_rows(self.conn) if r['id'] == self.prop['id'])

    def closing_step(self):
        return next(s for s in lead_file(self.conn, self.lead_id)['steps'] if s['key'] == 'abschluss')

    # -- Fälle
    def test_accepted_without_invoice_is_open(self):
        b = self.billing()
        self.assertEqual(b['state'], 'offen')
        self.assertEqual(b['remaining_net_cents'], 1_000_000)
        self.assertEqual(b['payment_state'], 'keine')
        self.assertIn(self.prop['id'], self.unbilled_ids())
        self.assertFalse(self.row()['invoiced'])

    def test_draft_is_not_billed(self):
        self.deposit()
        b = self.billing()
        self.assertEqual(b['state'], 'entwurf')
        self.assertEqual(b['invoiced_net_cents'], 0)
        self.assertEqual(b['remaining_net_cents'], 1_000_000)
        self.assertEqual(b['draft_count'], 1)
        self.assertIn(self.prop['id'], self.unbilled_ids(), 'ein Rechnungsentwurf darf das Angebot nicht als abgerechnet ausblenden')
        self.assertFalse(self.row()['invoiced'])
        pot = potential(self.conn)
        self.assertEqual([o['proposal_id'] for o in pot['accepted']], [self.prop['id']])
        self.assertEqual(pot['accepted_sum'], 10000)

    def test_forty_percent_deposit_keeps_sixty_percent_visible(self):
        """Der im Audit genannte Fall: 40 % Abschlag festgeschrieben → 60 % bleiben als noch abzurechnen sichtbar."""
        self.issue(self.deposit(40))
        b = self.billing()
        self.assertEqual(b['state'], 'teilweise')
        self.assertFalse(b['complete'])
        self.assertEqual(b['invoiced_net_cents'], 400_000)
        self.assertEqual(b['remaining_net_cents'], 600_000)
        self.assertEqual(b['invoiced_pct'], 40.0)
        self.assertEqual(b['payment_state'], 'ausstehend')
        # Abrechnen: weiterhin in der Liste, mit Rest
        unbilled = acc.overview(self.conn)['accepted_without_invoice']
        self.assertEqual([p['id'] for p in unbilled], [self.prop['id']])
        self.assertEqual(unbilled[0]['billing']['remaining_net_cents'], 600_000)
        # Heute: Potenzial zeigt den Rest, nicht null und nicht den vollen Betrag
        pot = potential(self.conn)
        self.assertEqual(pot['accepted_sum'], 6000)
        self.assertEqual(pot['accepted'][0]['total_net_eur'], 10000)
        self.assertEqual(pot['accepted'][0]['billing_state'], 'teilweise')
        # Angebotsliste: nicht „berechnet“
        self.assertFalse(self.row()['invoiced'])
        self.assertEqual(self.row()['billing']['state'], 'teilweise')
        # Akte: Abschluss nicht erledigt, Rest genannt
        step = self.closing_step()
        self.assertFalse(step['done'])
        self.assertTrue(step['partial'])
        self.assertIn('teilweise abgerechnet', step['detail'])
        self.assertIn('6.000,00 € netto offen', step['detail'])

    def test_paid_deposit_is_paid_but_not_fully_billed(self):
        dep = self.issue(self.deposit(40))
        acc.add_payment(self.conn, dep['id'], {})
        b = self.billing()
        self.assertEqual(b['payment_state'], 'bezahlt')
        self.assertEqual(b['state'], 'teilweise', 'bezahlt heißt nicht vollständig abgerechnet')
        self.assertIn(self.prop['id'], self.unbilled_ids())

    def test_partial_payment_state(self):
        dep = self.issue(self.deposit(40))
        acc.add_payment(self.conn, dep['id'], {'amount_eur': '100'})
        self.assertEqual(self.billing()['payment_state'], 'teilbezahlt')
        self.assertEqual(self.billing()['outstanding_cents'], dep['gross_cents'] - 10_000)

    def test_final_invoice_completes_billing(self):
        self.issue(self.deposit(40))
        final = acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id'], 'mode': 'schluss'})
        # Schlussrechnung nur als Entwurf: noch teilweise, Entwurf ausgewiesen
        b = self.billing()
        self.assertEqual((b['state'], b['draft_count']), ('teilweise', 1))
        self.assertIn(self.prop['id'], self.unbilled_ids())
        self.issue(final)
        b = self.billing()
        self.assertEqual(b['state'], 'vollstaendig')
        self.assertEqual(b['invoiced_net_cents'], 1_000_000)
        self.assertEqual(b['remaining_net_cents'], 0)
        self.assertEqual(self.unbilled_ids(), [])
        self.assertEqual(potential(self.conn)['accepted'], [])
        self.assertTrue(self.row()['invoiced'])
        step = self.closing_step()
        self.assertTrue(step['done'])
        self.assertIn('abgerechnet', step['detail'])

    def test_full_invoice_completes_billing(self):
        self.issue(acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id'], 'mode': 'voll'}))
        self.assertEqual(self.billing()['state'], 'vollstaendig')
        self.assertEqual(self.unbilled_ids(), [])

    def test_cancelled_invoice_brings_offer_back(self):
        inv = self.issue(acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id'], 'mode': 'voll'}))
        acc.cancel_invoice(self.conn, inv['id'], 'falscher Empfänger')
        b = self.billing()
        self.assertEqual(b['state'], 'storniert')
        self.assertEqual(b['invoiced_net_cents'], 0, 'Storno und stornierte Rechnung zählen nicht als abgerechnet')
        self.assertEqual(b['remaining_net_cents'], 1_000_000)
        self.assertIn(self.prop['id'], self.unbilled_ids())
        self.assertFalse(self.closing_step()['done'])

    def test_two_deposits_reaching_total_complete_billing(self):
        self.issue(self.deposit(60))
        self.assertEqual(self.billing()['remaining_net_cents'], 400_000)
        self.issue(self.deposit(40))
        self.assertEqual(self.billing()['state'], 'vollstaendig')

    def test_billing_state_does_not_write(self):
        """Lesende Auswertung: der Abrechnungsstand ändert keine Rechnungen und kein Änderungsprotokoll."""
        self.issue(self.deposit(40))
        before = (self.conn.total_changes, self.conn.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0])
        self.billing(); acc.overview(self.conn); potential(self.conn); proposal_rows(self.conn)
        self.assertEqual(before, (self.conn.total_changes, self.conn.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0]))


if __name__ == '__main__':
    unittest.main()
