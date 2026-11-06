"""Rechnungen, GoBD-Festschreibung, Zahlungen, Mahnungen, Ausgaben, UStVA/EÜR, E-Rechnung."""
import datetime as dt
import json
import sqlite3
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from s5_helpers import confirm_need  # noqa: E402
from sales_tool import accounting as acc
from sales_tool.einvoice import parse_einvoice, xrechnung_xml, import_document
from sales_tool.model import connect, init_db
from sales_tool.sales_workspace import make_proposal
from sales_tool.server import make_handler

TODAY = dt.date.today().isoformat()
SELLER = {'company_name': 'Pixel & Prozess Studio', 'owner_name': 'Alex Muster', 'street': 'Hafenstraße 1',
          'zip': '20457', 'city': 'Hamburg', 'tax_number': '22/123/45678', 'vat_id': 'DE123456789',
          'email': 'rechnung@pixel-prozess.example', 'phone': '+49 40 123456', 'iban': 'DE89 3704 0044 0532 0130 00',
          'bic': 'COBADEFFXXX', 'bank_name': 'Commerzbank'}


def buyer(**extra):
    data = {'buyer_name': 'Beispiel Maschinenbau GmbH', 'buyer_street': 'Werkstraße 5', 'buyer_zip': '70173',
            'buyer_city': 'Stuttgart', 'buyer_email': 'buchhaltung@beispiel.example', 'service_from': TODAY,
            'lines': [{'description': 'Conversion-Sprint', 'quantity': 1, 'unit': 'pauschal', 'unit_price_eur': '5900', 'vat_rate': 19}]}
    data.update(extra)
    return data


class AccountingBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'test.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def configure(self, **extra):
        return acc.save_settings(self.conn, {**SELLER, **extra})

    def lead(self, company='Beispiel Maschinenbau GmbH'):
        cur = self.conn.execute("INSERT INTO leads(company, permission, stage) VALUES (?, 'opt_in', 'angebot')", (company,))
        self.conn.commit()
        return cur.lastrowid


class MoneyAndSettingsTests(AccountingBase):
    def test_cents_parsing_german_and_dot_formats(self):
        self.assertEqual(acc.cents('1.234,56'), 123456)
        self.assertEqual(acc.cents('1234.56'), 123456)
        self.assertEqual(acc.cents(19.99), 1999)
        self.assertEqual(acc.eur(-123456), '-1.234,56')
        for bad in ('abc', None, True, 'nan', 'inf'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                acc.cents(bad)

    def test_iban_checksum_and_settings_validation(self):
        self.assertTrue(acc.iban_valid('DE89370400440532013000'))
        self.assertFalse(acc.iban_valid('DE89370400440532013001'))
        with self.assertRaises(ValueError):
            acc.save_settings(self.conn, {'iban': 'DE00123'})
        with self.assertRaises(ValueError):
            acc.save_settings(self.conn, {'unknown': 'x'})
        s = self.configure()
        self.assertEqual(s['iban'], 'DE89370400440532013000')
        self.assertEqual(s['missing'], [])

    def test_missing_master_data_blocks_finalization(self):
        inv = acc.create_invoice(self.conn, buyer())
        self.assertTrue(any('Stammdaten' in c for c in inv['checks']))
        with self.assertRaisesRegex(ValueError, 'Pflichtangaben'):
            acc.finalize_invoice(self.conn, inv['id'])


class InvoiceLifecycleTests(AccountingBase):
    def setUp(self):
        super().setUp()
        self.configure()

    def test_mixed_rates_are_summed_per_rate(self):
        inv = acc.create_invoice(self.conn, buyer(lines=[
            {'description': 'Webdesign', 'quantity': '2,5', 'unit': 'tag', 'unit_price_eur': '800', 'vat_rate': 19},
            {'description': 'Fachbuch', 'quantity': 1, 'unit': 'stueck', 'unit_price_eur': '39,90', 'vat_rate': 7}]))
        self.assertEqual(inv['net_cents'], 200000 + 3990)
        self.assertEqual(inv['vat_cents'], 38000 + 279)
        self.assertEqual(inv['gross_cents'], inv['net_cents'] + inv['vat_cents'])
        self.assertEqual([g['rate'] for g in inv['totals']['breakdown']], [19, 7])

    def test_finalize_assigns_gapless_numbers_and_locks_invoice(self):
        a = acc.create_invoice(self.conn, buyer())
        b = acc.create_invoice(self.conn, buyer())
        self.assertIsNone(a['number'])
        fb = acc.finalize_invoice(self.conn, b['id'])
        fa = acc.finalize_invoice(self.conn, a['id'])
        year = TODAY[:4]
        self.assertEqual(fb['number'], f'RE-{year}-0001')
        self.assertEqual(fa['number'], f'RE-{year}-0002')
        self.assertEqual(fa['status'], 'offen')
        self.assertEqual(fa['seller']['company_name'], SELLER['company_name'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE invoices SET gross_cents=1 WHERE id=?', (fa['id'],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('DELETE FROM invoices WHERE id=?', (fa['id'],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE invoice_lines SET net_cents=1 WHERE invoice_id=?', (fa['id'],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('DELETE FROM audit_log')
        self.conn.rollback()
        with self.assertRaisesRegex(ValueError, 'Entwürfe'):
            acc.update_invoice(self.conn, fa['id'], buyer())
        with self.assertRaises(ValueError):
            acc.delete_draft(self.conn, fa['id'])
        actions = [r['action'] for r in acc.audit_rows(self.conn)]
        self.assertIn('festgeschrieben', actions)

    def test_settings_change_does_not_alter_finalized_seller_snapshot(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        acc.save_settings(self.conn, {'company_name': 'Neuer Name GmbH'})
        self.assertEqual(acc.invoice_detail(self.conn, inv['id'])['seller']['company_name'], SELLER['company_name'])

    def test_future_and_non_chronological_dates_rejected(self):
        future = (dt.date.today() + dt.timedelta(days=3)).isoformat()
        inv = acc.create_invoice(self.conn, buyer(issue_date=future))
        with self.assertRaisesRegex(ValueError, 'Zukunft'):
            acc.finalize_invoice(self.conn, inv['id'])
        acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        older = (dt.date.today() - dt.timedelta(days=400)).isoformat() if dt.date.today().month == 1 else (dt.date.today().replace(day=1) - dt.timedelta(days=1)).isoformat()
        if older[:4] == TODAY[:4]:
            late = acc.create_invoice(self.conn, buyer(issue_date=older, service_from=older))
            with self.assertRaisesRegex(ValueError, 'chronologisch'):
                acc.finalize_invoice(self.conn, late['id'])

    def test_payments_partial_full_and_overpayment(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        self.assertEqual(inv['gross_cents'], 702100)
        part = acc.add_payment(self.conn, inv['id'], {'amount_eur': '2000', 'paid_on': TODAY})
        self.assertEqual(part['status'], 'teilbezahlt')
        self.assertEqual(part['outstanding_cents'], 502100)
        with self.assertRaisesRegex(ValueError, 'übersteigt'):
            acc.add_payment(self.conn, inv['id'], {'amount_eur': '6000', 'paid_on': TODAY})
        full = acc.add_payment(self.conn, inv['id'], {'paid_on': TODAY})
        self.assertEqual(full['status'], 'bezahlt')
        undone = acc.delete_payment(self.conn, full['payments'][-1]['id'])
        self.assertEqual(undone['status'], 'teilbezahlt')

    def test_storno_creates_negative_counter_invoice(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        storno = acc.cancel_invoice(self.conn, inv['id'], 'Falscher Empfänger')
        self.assertEqual(storno['kind'], 'storno')
        self.assertEqual(storno['gross_cents'], -inv['gross_cents'])
        self.assertTrue(storno['number'].endswith('0002'))
        self.assertEqual(storno['corrects']['number'], inv['number'])
        self.assertEqual(acc.invoice_detail(self.conn, inv['id'])['status'], 'storniert')
        with self.assertRaises(ValueError):
            acc.cancel_invoice(self.conn, inv['id'])
        paid = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        acc.add_payment(self.conn, paid['id'], {'amount_eur': 100, 'paid_on': TODAY})
        with self.assertRaisesRegex(ValueError, 'Zahlungseingänge'):
            acc.cancel_invoice(self.conn, paid['id'])

    def test_duplicate_for_recurring_billing(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        copy = acc.duplicate_invoice(self.conn, inv['id'])
        self.assertEqual(copy['status'], 'entwurf')
        self.assertEqual(copy['gross_cents'], inv['gross_cents'])
        self.assertEqual(copy['service_from'], '')

    def test_reverse_charge_requires_eu_buyer_with_vat_id(self):
        inv = acc.create_invoice(self.conn, buyer(tax_mode='reverse_charge'))
        self.assertEqual(inv['vat_cents'], 0)
        self.assertTrue(any('USt-IdNr' in c for c in inv['checks']))
        ok = acc.create_invoice(self.conn, buyer(tax_mode='reverse_charge', buyer_country='AT', buyer_vat_id='ATU12345678'))
        final = acc.finalize_invoice(self.conn, ok['id'])
        self.assertIn('Reverse Charge', ' '.join(final['notes']))

    def test_invalid_lines_rejected(self):
        for lines in ([], [{'description': '', 'unit_price_eur': 1}], [{'description': 'x', 'unit_price_eur': 1, 'vat_rate': 16}],
                      [{'description': 'x', 'unit_price_eur': 1, 'quantity': 0}], [{'description': 'x', 'unit_price_eur': -10}],
                      [{'description': 'x', 'unit_price_eur': 1, 'unit': 'kg'}], [{'description': 'x', 'unit_price_eur': 1, 'evil': 1}]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                acc.create_invoice(self.conn, buyer(lines=lines))


class SmallBusinessTests(AccountingBase):
    def test_kleinunternehmer_invoice_has_no_vat_and_note(self):
        self.configure(small_business=True, vat_id='')
        inv = acc.create_invoice(self.conn, buyer())
        self.assertEqual(inv['tax_mode'], 'kleinunternehmer')
        self.assertEqual(inv['vat_cents'], 0)
        self.assertIn('§ 19 UStG', ' '.join(inv['notes']))
        with self.assertRaises(ValueError):
            acc.create_invoice(self.conn, buyer(tax_mode='regel'))


class ProposalToInvoiceTests(AccountingBase):
    def setUp(self):
        super().setUp()
        self.configure()
        self.lead_id = self.lead()
        self.prop = make_proposal(self.conn, {'lead_id': self.lead_id, 'package': 'conversion', 'tax_mode': 'regel_19',
                                              'custom_price_eur': 10000})

    def test_proposal_has_number_and_validity(self):
        self.assertRegex(self.prop['number'], r'^AN-\d{4}-0001$')
        self.assertTrue(self.prop['customer']['valid_until'] > TODAY)

    def test_invoice_requires_accepted_proposal(self):
        with self.assertRaisesRegex(ValueError, 'Annahme'):
            acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id']})

    def test_deposit_and_final_invoice_deduct_correctly(self):
        self.conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (self.prop['id'],))
        dep = acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id'], 'mode': 'abschlag', 'percent': 40})
        self.assertEqual(dep['kind'], 'abschlag')
        self.assertEqual(dep['net_cents'], 400000)
        lines = [{k: x[k] for k in ('description', 'quantity', 'unit', 'unit_price_cents', 'vat_rate')} for x in dep['lines']]
        dep = acc.finalize_invoice(self.conn, acc.update_invoice(self.conn, dep['id'], {**buyer(), 'lines': lines})['id'])
        self.assertEqual(dep['kind'], 'abschlag')
        final = acc.invoice_from_proposal(self.conn, {'proposal_id': self.prop['id'], 'mode': 'schluss'})
        self.assertEqual(final['kind'], 'schluss')
        self.assertEqual(final['net_cents'], 600000)
        self.assertEqual(final['lines'][1]['unit_price_cents'], -400000)
        self.assertIn(dep['number'], final['lines'][1]['description'])
        self.assertEqual(acc.overview(self.conn)['accepted_without_invoice'], [])

    def test_buyer_defaults_fall_back_to_lead(self):
        self.assertEqual(acc.buyer_defaults(self.conn, self.lead_id)['buyer_name'], 'Beispiel Maschinenbau GmbH')


class ReportTests(AccountingBase):
    def setUp(self):
        super().setUp()
        self.configure()

    def test_ist_vs_soll_and_input_tax(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        acc.add_payment(self.conn, inv['id'], {'amount_eur': '3510,50', 'paid_on': TODAY})  # Hälfte
        acc.create_expense(self.conn, {'expense_date': TODAY, 'paid_on': TODAY, 'supplier': 'Hosting AG', 'gross_eur': '119,00',
                                       'vat_rate': 19, 'category': 'software', 'receipt_ref': 'B-1'})
        acc.create_expense(self.conn, {'expense_date': TODAY, 'paid_on': TODAY, 'supplier': 'Ads Ireland Ltd', 'net_eur': '100',
                                       'reverse_charge': True, 'category': 'werbung', 'receipt_ref': 'B-2'})
        soll = acc.tax_report(self.conn, {'basis': 'soll'})
        ist = acc.tax_report(self.conn, {'basis': 'ist'})
        kz = lambda r, k: next(x for x in r['ustva'] if x['kz'] == k)
        self.assertEqual(kz(soll, '81')['value_eur'], 5900)
        self.assertEqual(kz(soll, '81')['tax_cents'], 112100)
        self.assertEqual(kz(ist, '81')['value_eur'], 2950)
        self.assertEqual(kz(ist, '66')['tax_cents'], 1900)
        self.assertEqual(kz(ist, '46')['value_eur'], 100)
        self.assertEqual(kz(ist, '46')['tax_cents'], 1900)
        self.assertEqual(kz(ist, '67')['tax_cents'], 1900)
        self.assertEqual(ist['payable_cents'], 56050 + 1900 - 1900 - 1900)
        self.assertEqual(ist['euer']['expenses_cents'], 10000 + 10000)

    def test_small_business_reverse_charge_tax_is_owed_without_deduction(self):
        acc.save_settings(self.conn, {'small_business': True})
        acc.create_expense(self.conn, {'expense_date': TODAY, 'paid_on': TODAY, 'supplier': 'SaaS Ltd', 'net_eur': '100',
                                       'reverse_charge': True, 'category': 'software', 'receipt_ref': 'X'})
        r = acc.tax_report(self.conn, {'basis': 'ist'})
        self.assertEqual(r['payable_cents'], 1900)
        self.assertEqual(r['euer']['expenses_cents'], 11900)

    def test_dunning_interest_and_fee(self):
        self.assertEqual(acc.default_interest_cents(100000, '1.27', 365), 10270)
        inv = acc.create_invoice(self.conn, buyer(payment_days=0))
        past = (dt.date.today() - dt.timedelta(days=20)).isoformat()
        self.conn.execute('UPDATE invoices SET issue_date=? WHERE id=?', (past, inv['id']))
        inv = acc.finalize_invoice(self.conn, inv['id'])
        self.assertEqual(inv['overdue_days'], 20)
        notice = acc.create_dunning(self.conn, inv['id'], {'level': 2, 'include_interest': True, 'include_fee': True})
        self.assertEqual(notice['fee_cents'], 4000)
        self.assertGreater(notice['interest_cents'], 0)
        self.assertIn('§ 288', notice['text'])
        self.assertIn(inv['number'], notice['text'])

    def test_csv_export_has_bom_and_blocks_formula_injection(self):
        acc.create_expense(self.conn, {'expense_date': TODAY, 'supplier': '=HYPERLINK("http://x")', 'gross_eur': 10, 'receipt_ref': 'r'})
        out = acc.export_csv(self.conn, 'ausgaben', {})
        self.assertTrue(out.startswith('﻿'))
        self.assertIn("'=HYPERLINK", out)
        self.assertIn('4900', out)
        self.assertIn('Belegdatum;', out)

    def test_overview_flags_overdue_and_small_business_limit(self):
        acc.save_settings(self.conn, {'small_business': True, 'vat_id': ''})
        inv = acc.create_invoice(self.conn, buyer(lines=[{'description': 'Großprojekt', 'unit_price_eur': 30000}]))
        acc.finalize_invoice(self.conn, inv['id'])
        o = acc.overview(self.conn)
        self.assertEqual(o['open_count'], 1)
        self.assertTrue(any('25.000' in w for w in o['warnings']))


class EInvoiceTests(AccountingBase):
    def setUp(self):
        super().setUp()
        self.configure()

    def test_xrechnung_contains_mandatory_fields_and_roundtrips(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer(buyer_reference='04011000-12345-67'))['id'])
        data, warnings = xrechnung_xml(self.conn, inv['id'])
        self.assertEqual(warnings, [])
        root = ET.fromstring(data)
        ns = {'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
              'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'}
        self.assertIn('xrechnung_3.0', root.find('cbc:CustomizationID', ns).text)
        self.assertEqual(root.find('cbc:ID', ns).text, inv['number'])
        self.assertEqual(root.find('cbc:BuyerReference', ns).text, '04011000-12345-67')
        self.assertEqual(root.find('cac:LegalMonetaryTotal/cbc:PayableAmount', ns).text, '7021.00')
        self.assertEqual(root.find('cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID', ns).text, 'DE89370400440532013000')
        parsed = parse_einvoice(data)
        self.assertEqual(parsed['gross'], Decimal('7021.00'))
        self.assertEqual(parsed['supplier'], SELLER['company_name'])
        with self.assertRaises(ValueError):
            xrechnung_xml(self.conn, acc.create_invoice(self.conn, buyer())['id'])

    def test_storno_xml_uses_positive_prices_and_reference(self):
        inv = acc.finalize_invoice(self.conn, acc.create_invoice(self.conn, buyer())['id'])
        storno = acc.cancel_invoice(self.conn, inv['id'])
        data, _ = xrechnung_xml(self.conn, storno['id'])
        root = ET.fromstring(data)
        ns = {'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
              'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'}
        self.assertEqual(root.find('cbc:InvoiceTypeCode', ns).text, '384')
        self.assertEqual(root.find('cac:InvoiceLine/cac:Price/cbc:PriceAmount', ns).text, '5900.00')
        self.assertEqual(root.find('cac:InvoiceLine/cbc:InvoicedQuantity', ns).text, '-1')
        self.assertEqual(root.find('cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID', ns).text, inv['number'])

    def test_cii_import_archives_original_and_suggests_expense(self):
        cii = b'''<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
 xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
 xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>urn:cen.eu:en16931:2017</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter></rsm:ExchangedDocumentContext>
 <rsm:ExchangedDocument><ram:ID>HX-2026-778</ram:ID><ram:TypeCode>380</ram:TypeCode>
  <ram:IssueDateTime><udt:DateTimeString format="102">20261015</udt:DateTimeString></ram:IssueDateTime></rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>
  <ram:IncludedSupplyChainTradeLineItem><ram:SpecifiedTradeProduct><ram:Name>Webhosting Business</ram:Name></ram:SpecifiedTradeProduct></ram:IncludedSupplyChainTradeLineItem>
  <ram:ApplicableHeaderTradeAgreement><ram:SellerTradeParty><ram:Name>Hosting Nord GmbH</ram:Name>
   <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">DE999999999</ram:ID></ram:SpecifiedTaxRegistration></ram:SellerTradeParty></ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>3.80</ram:CalculatedAmount><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>19</ram:RateApplicablePercent></ram:ApplicableTradeTax>
   <ram:SpecifiedTradePaymentTerms><ram:DueDateDateTime><udt:DateTimeString format="102">20261029</udt:DateTimeString></ram:DueDateDateTime></ram:SpecifiedTradePaymentTerms>
   <ram:SpecifiedTradeSettlementHeaderMonetarySummation><ram:TaxBasisTotalAmount>20.00</ram:TaxBasisTotalAmount>
    <ram:TaxTotalAmount currencyID="EUR">3.80</ram:TaxTotalAmount><ram:GrandTotalAmount>23.80</ram:GrandTotalAmount>
    <ram:DuePayableAmount>23.80</ram:DuePayableAmount></ram:SpecifiedTradeSettlementHeaderMonetarySummation>
  </ram:ApplicableHeaderTradeSettlement></rsm:SupplyChainTradeTransaction></rsm:CrossIndustryInvoice>'''
        result = import_document(self.conn, {'filename': 'hosting.xml', 'xml': cii.decode()})
        self.assertEqual(result['parsed']['number'], 'HX-2026-778')
        self.assertEqual(result['parsed']['issue_date'], '2026-10-15')
        self.assertEqual(result['expense_suggestion']['gross_eur'], '23.80')
        self.assertEqual(result['expense_suggestion']['vat_rate'], 19)
        again = import_document(self.conn, {'filename': 'hosting.xml', 'xml': cii.decode()})
        self.assertTrue(again['duplicate'])
        exp = acc.create_expense(self.conn, {**{k: result['expense_suggestion'][k] for k in ('supplier', 'expense_date', 'receipt_ref', 'gross_eur', 'vat_eur', 'vat_rate')},
                                             'document_id': result['document_id']})
        self.assertEqual(exp['source'], 'e-rechnung')
        self.assertEqual(exp['vat_cents'], 380)
        with self.assertRaisesRegex(ValueError, 'bereits'):
            acc.create_expense(self.conn, {'expense_date': TODAY, 'supplier': 'x', 'gross_eur': 1, 'document_id': result['document_id']})
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('DELETE FROM einvoice_documents')

    def test_dangerous_or_unknown_xml_rejected(self):
        for payload in (b'<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>', b'%PDF-1.7 ...', b'<foo/>', b'not xml'):
            with self.subTest(payload=payload[:20]), self.assertRaises(ValueError):
                parse_einvoice(payload)


class AccountingHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'http.sqlite3'
        with connect(self.db) as conn:
            init_db(conn)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path, method='GET', body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(req) as resp:
                content = resp.read()
                return resp.status, (content if raw else json.loads(content)), resp.headers
        except HTTPError as err:
            return err.code, json.loads(err.read()), err.headers

    def test_full_flow_over_http(self):
        status, settings, _ = self.call('/api/accounting/settings', 'PUT', SELLER)
        self.assertEqual(status, 200, settings)
        status, lead, _ = self.call('/api/leads', 'POST', {'company': 'Beispiel Maschinenbau GmbH', 'stage': 'angebot'})
        status, prop, _ = self.call('/api/workspace/proposals', 'POST', {'lead_id': lead['id'], 'package': 'pilot', 'tax_mode': 'regel_19'})
        self.assertEqual(status, 201)
        confirm_need(self.db, lead['id'])  # v1.18: Annahme nur mit bestätigtem Bedarf
        status, _, _ = self.call(f"/api/workspace/proposals/{prop['id']}", 'PATCH', {'status': 'angenommen'})
        self.assertEqual(status, 200)
        status, lead_after, _ = self.call(f"/api/leads/{lead['id']}")
        self.assertEqual(lead_after['stage'], 'gewonnen')
        status, inv, _ = self.call('/api/accounting/invoices/from-proposal', 'POST', {'proposal_id': prop['id']})
        self.assertEqual(status, 201, inv)
        payload = buyer(lines=[{k: l[k] for k in ('description', 'quantity', 'unit', 'unit_price_cents', 'vat_rate')} for l in inv['lines']],
                        lead_id=lead['id'])
        status, inv, _ = self.call(f"/api/accounting/invoices/{inv['id']}", 'PUT', payload)
        self.assertEqual(status, 200, inv)
        status, err, _ = self.call(f"/api/accounting/invoices/{inv['id']}/finalize", 'POST', {'confirm': False})
        self.assertEqual(status, 400)
        status, inv, _ = self.call(f"/api/accounting/invoices/{inv['id']}/finalize", 'POST', {'confirm': True})
        self.assertEqual(status, 200, inv)
        status, xml, headers = self.call(f"/api/accounting/invoices/{inv['id']}/xrechnung", raw=True)
        self.assertEqual(status, 200)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertTrue(xml.startswith(b'<?xml'))
        status, html, _ = self.call(f"/rechnung/{inv['id']}", raw=True)
        self.assertEqual(status, 200)
        self.assertIn(inv['number'].encode(), html)
        self.assertIn(b'USt-IdNr.: DE123456789', html)
        status, err, _ = self.call(f"/api/leads/{lead['id']}", 'DELETE')
        self.assertEqual(status, 409)
        self.assertIn('Aufbewahrung', err['error'])
        status, csv_body, headers = self.call('/api/accounting/export/rechnungen.csv', raw=True)
        self.assertEqual(status, 200)
        self.assertIn(inv['number'], csv_body.decode('utf-8-sig'))
        status, report, _ = self.call('/api/accounting/report?basis=soll')
        self.assertEqual(status, 200)
        status, overview, _ = self.call('/api/accounting/overview')
        self.assertEqual(overview['open_count'], 1)
        status, kpis, _ = self.call('/api/accounting/sales-kpis')
        self.assertEqual(kpis['proposals_by_status'].get('angenommen'), 1)
        status, _, _ = self.call('/api/accounting/invoices/999')
        self.assertEqual(status, 404)
        status, backup, _ = self.call('/api/backup', 'POST', {})
        self.assertEqual(status, 201)
        self.assertTrue(Path(backup['path']).exists())
        status, listing, _ = self.call('/api/backups')
        self.assertEqual(len(listing['backups']), 1)

    def test_cross_origin_write_blocked(self):
        req = Request(self.base + '/api/accounting/settings', data=b'{"company_name":"x"}', method='PUT',
                      headers={'Content-Type': 'application/json', 'Origin': 'http://evil.example'})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == '__main__':
    unittest.main()
