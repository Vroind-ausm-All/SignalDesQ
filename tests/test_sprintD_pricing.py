"""Sprint D – Leistungskatalog, nachvollziehbare Festpreise, Anreise/Tagespauschale, Mindestverdienst,
Kundendokument ohne interne Kalkulation, Rechnung mit Positionen. Fiktive Daten."""
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from sales_tool import accounting as acc
from sales_tool import pricing as pr
from sales_tool.model import connect, init_db
from sales_tool.sales_workspace import customer_markdown, make_proposal
from sales_tool.server import make_handler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_accounting import SELLER  # noqa: E402

USER_SERVICES = {  # Angaben des Nutzers → Katalogschlüssel
    'handgestaltete Kunst': 'kunst', 'Texter': 'texte', 'Webdesign': 'webdesign', 'Grafikdesign': 'grafik', 'Print': 'print', 'Logogestaltung': 'logo',
    'Individualsoftware': 'software', 'Anbindung an Shops': 'shop_anbindung', 'eigener Webshop': 'webshop', 'Fotografie': 'foto', 'Videografie': 'video',
    'Werbung': 'werbung', 'SEO + GEO': 'seo_geo', 'KI-Chatbot': 'chatbot', 'Telefon-Sprachbot': 'voicebot', 'Webseiten-Analyse': 'website_analyse',
    'Anreise': 'anreise', 'Tagespauschale': 'tagessatz'}

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from tmpclean import cleanup_tmp  # noqa: E402 – Worker beenden, dann löschen (Windows)


class PricingBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'pr.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.lead = self.conn.execute("INSERT INTO leads(company, industry, stage) VALUES ('Fiktiv Werkstatt GmbH', 'Sonstige', 'angebot')").lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def pos(self, **p):
        return pr.price_position(p, pr.pricing_settings(self.conn), pr.overrides(self.conn))


class CatalogTests(PricingBase):
    def test_all_user_services_with_sizes_and_min_earning(self):
        for label, key in USER_SERVICES.items():
            self.assertIn(key, pr.SERVICES, label)
        cat = pr.catalog(self.conn)
        for g in cat['groups']:
            for s in g['services']:
                if s['kind'] == 'paket':
                    self.assertEqual(set(s['sizes']), {'S', 'M', 'L'}, s['key'])
                    for size, v in s['sizes'].items():
                        self.assertGreaterEqual(v['effective_hourly'], 66, f"{s['key']} {size}")
                        self.assertEqual(v['price_eur'] % 10, 0, 'auf volle 10 € gerundet')
        self.assertEqual(cat['settings']['hourly_rate'], 66)

    def test_price_formulas(self):
        c, i = self.pos(service='logo', size='M')
        self.assertEqual((i['hours'], i['labor_eur'], i['buffer_eur'], i['price_eur']), (22, 1452, 145.2, 1600))
        self.assertIn('22 h × 66 €/h + 10 % Puffer', i['formula'])
        self.assertEqual(c['scope'], 'Standard: 3 Entwürfe, 2 Korrekturschleifen, Farb-/Schwarzweiß-Varianten, Favicon')
        _, i = self.pos(service='texte', qty=4)
        self.assertEqual(i['price_eur'], 880)
        _, i = self.pos(service='kunst', size='M')
        self.assertEqual((i['external_eur'], i['price_eur']), (150, 1900), 'Material im Festpreis enthalten')
        self.assertGreaterEqual(i['effective_hourly'], 66)
        _, i = self.pos(service='anreise', km=35, minutes=40)
        self.assertEqual((i['external_eur'], i['price_eur']), (35, 79))
        self.assertIn('35 km × 0,5 €', i['formula'])
        _, i = self.pos(service='tagessatz', days=1.5)
        self.assertEqual((i['price_eur'], i['hours']), (818, 12))
        _, i = self.pos(service='aufwand', qty=3)
        self.assertEqual((i['price_eur'], i['buffer_eur']), (198, 0))
        c, _ = self.pos(service='seo_betreuung', size='S')
        self.assertEqual(c['billing'], 'monatlich')

    def test_validation(self):
        for bad in ({'service': 'raumfahrt'}, {'service': 'logo', 'size': 'XL'}, {'service': 'produktfoto', 'qty': 2}, {'service': 'tagessatz', 'days': 1.3},
                    {'service': 'anreise'}, {'service': 'logo', 'size': 'S', 'preis': 1}, {'service': 'texte', 'qty': 2.5}):
            with self.assertRaises(ValueError, msg=bad):
                self.pos(**bad)
        with self.assertRaises(ValueError):
            pr.build_quote(self.conn, {'positions': []})
        with self.assertRaises(ValueError):
            pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'S'}] * 41})


class SettingsAndOverrideTests(PricingBase):
    def test_settings_change_prices(self):
        with self.assertRaises(ValueError):
            pr.save_pricing_settings(self.conn, {'hourly_rate': 5})
        with self.assertRaises(ValueError):
            pr.save_pricing_settings(self.conn, {'unbekannt': 1})
        pr.save_pricing_settings(self.conn, {'hourly_rate': 80, 'day_rate': 640})
        _, i = self.pos(service='logo', size='M')
        self.assertEqual(i['price_eur'], 1940)
        _, i = self.pos(service='tagessatz', days=1)
        self.assertEqual(i['price_eur'], 640)
        self.assertTrue(self.conn.execute("SELECT 1 FROM audit_log WHERE action='kalkulation_geaendert'").fetchone())

    def test_overrides_and_min_earning_warning(self):
        pr.save_override(self.conn, {'service': 'logo', 'size': 'S', 'hours': 10})
        _, i = self.pos(service='logo', size='S')
        self.assertEqual(i['price_eur'], 730)
        pr.save_override(self.conn, {'service': 'logo', 'size': 'M', 'fixed_price': 990})
        q = pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'M'}, {'service': 'webdesign', 'size': 'S'}]})
        logo = q['internal']['positions'][0]
        self.assertTrue(logo['fixed'])
        self.assertEqual(logo['price_eur'], 990)
        self.assertFalse(q['internal']['ok'], '990 € für 22 h liegt unter 66 €/h')
        self.assertIn('unter deinem Mindestverdienst', q['internal']['warnings'][0])
        pr.save_override(self.conn, {'service': 'texte', 'fixed_price': 250})
        _, i = self.pos(service='texte', qty=2)
        self.assertEqual(i['price_eur'], 500)
        cat = pr.save_override(self.conn, {'service': 'logo', 'size': 'M', 'reset': True})
        logo_m = next(s for g in cat['groups'] for s in g['services'] if s['key'] == 'logo')['sizes']['M']
        self.assertEqual((logo_m['price_eur'], logo_m['customized']), (1600, False))
        for bad in ({'service': 'anreise', 'hours': 1}, {'service': 'logo', 'size': 'XL', 'hours': 1}, {'service': 'logo', 'size': 'S', 'hours': -1}):
            with self.assertRaises(ValueError, msg=bad):
                pr.save_override(self.conn, bad)


class QuoteTests(PricingBase):
    POSITIONS = [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 5}, {'service': 'foto', 'size': 'S'},
                 {'service': 'anreise', 'km': 30, 'minutes': 35, 'trips': 2}, {'service': 'pflege', 'size': 'S'}, {'service': 'chatbot', 'size': 'S'}]

    def test_mixed_quote_totals_and_transparency(self):
        q = pr.build_quote(self.conn, {'positions': self.POSITIONS, 'tax_mode': 'regel_19', 'project_label': 'Neuer Webauftritt'})
        c, i = q['customer'], q['internal']
        once = sum(p['price_eur'] for p in c['positions'] if p['billing'] == 'einmalig')
        self.assertEqual((c['billing'], c['once_net_eur'], c['monthly_net_eur']), ('gemischt', once, 150))
        self.assertAlmostEqual(c['vat_eur'], round(once * 0.19, 2))
        self.assertTrue(any('KI-/Plattformkosten' in t for t in c['third_party_costs']), 'laufende Kosten Dritter ausgewiesen')
        self.assertTrue(i['ok'])
        self.assertGreaterEqual(i['effective_hourly'], 66)
        blob = json.dumps(c, ensure_ascii=False)
        for secret in ('"hours"', '€/h', 'labor', 'buffer', 'effective_hourly', '"formula"'):
            self.assertNotIn(secret, blob, f'interne Kalkulation ({secret}) nicht im Kundendokument')

    def test_proposal_markdown_and_legacy(self):
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': self.POSITIONS, 'tax_mode': 'regel_19', 'customer_goal': 'Mehr Anfragen über die Website'})
        md = customer_markdown(p['customer'])
        self.assertIn('| 1 | Webdesign & Website-Umsetzung | Standard: Unternehmenswebsite bis 8 Seiten |', md)
        self.assertIn('**Summe einmalig**', md)
        self.assertIn('150,00 € / Monat', md)
        self.assertIn('nicht im Festpreis', md)
        for secret in ('€/h', ' h ×', 'Puffer', 'Stundensatz'):
            self.assertNotIn(secret, md)
        stored = self.conn.execute('SELECT customer_json, internal_json FROM proposals WHERE id=?', (p['id'],)).fetchone()
        self.assertEqual(len(json.loads(stored['customer_json'])['positions']), 6)
        self.assertEqual(json.loads(stored['internal_json'])['mode'], 'baukasten')
        legacy = make_proposal(self.conn, {'lead_id': self.lead, 'package': 'conversion', 'tax_mode': 'regel_19'})
        self.assertNotIn('positions', legacy['customer'], 'alte Paket-Angebote funktionieren unverändert')

    def test_templates_and_matching_draft(self):
        for key, tpl in pr.TEMPLATES.items():
            q = pr.build_quote(self.conn, {'positions': tpl, 'template': key})
            self.assertTrue(q['customer']['positions'], key)
        from sales_tool.sales_integration import match_offers, quote_draft
        self.conn.execute("""INSERT INTO discovery(lead_id, problem, impact, desired_outcome, timing, decision_process)
                             VALUES (?, 'Aufträge werden manuell in Excel abgetippt', 'Zwei Stunden täglich', 'Ohne Medienbruch ins System', 'Q2', 'GF entscheidet')""", (self.lead,))
        rec = match_offers(self.conn, self.lead)['recommendations'][0]
        d = quote_draft(self.conn, rec['id'])
        self.assertEqual(d['positions'], pr.TEMPLATES[rec['package']])


class InvoiceTests(PricingBase):
    def test_invoice_lines_per_position(self):
        acc.save_settings(self.conn, SELLER)
        self.conn.execute("UPDATE leads SET legal_name='Fiktiv Werkstatt GmbH', street='Werkstraße 5', zip='70173', city='Stuttgart' WHERE id=?", (self.lead,))
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': QuoteTests.POSITIONS, 'tax_mode': 'regel_19'})
        with self.assertRaises(ValueError):
            acc.invoice_from_proposal(self.conn, {'proposal_id': p['id']})
        self.conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (p['id'],))
        self.conn.commit()
        inv = acc.invoice_from_proposal(self.conn, {'proposal_id': p['id'], 'mode': 'voll'})
        lines = acc.invoice_detail(self.conn, inv['id'])['lines']
        self.assertEqual(len(lines), 5, 'eine Rechnungszeile je einmaliger Position')
        self.assertIn('Pos. 1', lines[0]['description'])
        self.assertEqual(sum(l['net_cents'] for l in lines), round(p['customer']['once_net_eur'] * 100))
        monthly = acc.invoice_from_proposal(self.conn, {'proposal_id': p['id'], 'mode': 'monat'})
        mlines = acc.invoice_detail(self.conn, monthly['id'])['lines']
        self.assertEqual((len(mlines), mlines[0]['unit']), (1, 'monat'))
        dp = acc.invoice_from_proposal(self.conn, {'proposal_id': p['id'], 'mode': 'abschlag', 'percent': 40})
        self.assertEqual(acc.invoice_detail(self.conn, dp['id'])['net_cents'], round(p['customer']['once_net_eur'] * 40))
        only_once = make_proposal(self.conn, {'lead_id': self.lead, 'positions': [{'service': 'logo', 'size': 'S'}], 'tax_mode': 'regel_19'})
        self.conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (only_once['id'],))
        with self.assertRaises(ValueError):
            acc.invoice_from_proposal(self.conn, {'proposal_id': only_once['id'], 'mode': 'monat'})


class PricingHttpTests(PricingBase):
    def test_endpoints(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def call(path, method='GET', body=None):
                c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=20)
                c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'} if body is not None else {})
                r = c.getresponse()
                out = json.loads(r.read())
                c.close()
                return r.status, out
            status, cat = call('/api/pricing/catalog')
            self.assertEqual((status, cat['settings']['hourly_rate']), (200, 66))
            status, q = call('/api/pricing/preview', 'POST', {'positions': [{'service': 'voicebot', 'size': 'M'}, {'service': 'ki_betrieb', 'size': 'S'}]})
            self.assertEqual((status, q['customer']['billing']), (200, 'gemischt'))
            self.assertEqual(call('/api/pricing/settings', 'PUT', {'buffer_pct': 15})[0], 200)
            self.assertEqual(call('/api/pricing/overrides', 'PUT', {'service': 'video', 'size': 'S', 'external': 80})[0], 200)
            self.assertEqual(call('/api/pricing/templates/conversion')[1]['positions'], pr.TEMPLATES['conversion'])
            self.assertEqual(call('/api/pricing/templates/gibtsnicht')[0], 404)
            status, saved = call('/api/workspace/proposals', 'POST', {'lead_id': self.lead, 'positions': [{'service': 'website_analyse', 'size': 'S'}]})
            self.assertEqual(status, 201)
            status, out = call(f"/api/workspace/proposals/{saved['id']}/customer")
            self.assertEqual(status, 200)
            self.assertEqual(call('/api/pricing/preview', 'POST', {'positions': [{'service': 'x'}]})[0], 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
