"""2.0.0-dev16: Produktreview M12 – zentraler Leistungskatalog.

Abnahme (Review 13.11.2026, ergänzt um Leitfaden Kundenonboarding und Bewertungsmodell vom selben Tag):
- Eine geänderte Leistung wird bei künftigen Empfehlungen und Angeboten konsistent verwendet (Vorlagenpreis, Empfehlung,
  Angebot, Konfiguration der Oberfläche – eine Rechnung).
- Vorhandene Angebote ändern weder Text noch Preis.
- Die 5/6/26 bestehenden Katalogstrukturen werden über nachvollziehbare Zuordnungen zusammengeführt; Kennungen bleiben gültig.
- Positionsumfang und allgemeine Angaben widersprechen sich nicht (K01: Korrekturschleifen; Ausschluss „Texte“ bei Textposition).
- Zahlungsplan ist eine sichtbare Vorgabe und gilt bis in die Abschlagsrechnung; Prüfpunkte je Leistungsbereich nur intern.
- Analyseangebote sind abgegrenzt (Bewertungsmodell M31): Expertenprüfung ohne Nutzerstudie, Lieferung ≠ Wirkungsziel.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import json
import re
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import catalog, pricing as pr  # noqa: E402
from sales_tool.model import OFFERS, connect, init_db  # noqa: E402
from sales_tool.sales_integration import match_offers, quote_draft  # noqa: E402
from sales_tool.sales_workspace import customer_markdown, make_proposal, proposal_detail, quote_preview  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# Kennungen bis dev15 – sie stehen in gespeicherten Firmen, Empfehlungen, Bewertungen und Angeboten und dürfen nicht wegfallen
SERVICE_KEYS_DEV15 = ['website_analyse', 'workshop', 'logo', 'grafik', 'print', 'kunst', 'texte', 'fachartikel', 'webdesign', 'webshop',
                      'shop_anbindung', 'pflege', 'seo_geo', 'seo_betreuung', 'werbung', 'werbung_betreuung', 'foto', 'produktfoto', 'video',
                      'software', 'chatbot', 'voicebot', 'ki_betrieb', 'tagessatz', 'anreise', 'aufwand']
OFFER_KEYS_DEV15 = ['pilot', 'conversion', 'portal', 'brand', 'automation']
PACKAGE_KEYS_DEV15 = ['pilot', 'conversion', 'brand', 'care', 'portal', 'automation']
ADDON_KEYS_DEV15 = ['copy', 'analytics', 'seo', 'integration', 'training']


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'k.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Katalog Fiktiv GmbH', 'angebot')").lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def vorlage(self, key):
        return next(v for v in catalog.vorlagen(self.conn) if v['key'] == key)


class MappingTests(Base):
    def test_all_former_structures_are_mapped(self):
        self.assertEqual(list(catalog.SERVICES), SERVICE_KEYS_DEV15, 'Leistungskennungen bleiben unverändert')
        self.assertEqual(sorted(catalog.FRUEHER['angebote']), sorted(OFFER_KEYS_DEV15))
        self.assertEqual(sorted(catalog.FRUEHER['pakete']), sorted(PACKAGE_KEYS_DEV15))
        self.assertEqual(sorted(catalog.FRUEHER['zusatz']), sorted(ADDON_KEYS_DEV15))
        for key in OFFER_KEYS_DEV15 + PACKAGE_KEYS_DEV15:
            self.assertIn(key, catalog.VORLAGEN, key)
        self.assertEqual(list(OFFERS), list(catalog.VORLAGEN), 'Auswahl „Leistung“ der Firma = Vorlagen des Katalogs')
        h = catalog.herkunft(self.conn)
        self.assertEqual(len(h['vorlagen']), 6)
        self.assertEqual(h['leistungen'], 26)
        portal = next(r for r in h['vorlagen'] if r['key'] == 'portal')
        self.assertIn('Kundenportal & Prozess-App', portal['former_offer'])
        self.assertIn('ab 18.500 €', portal['former_package'])
        self.assertTrue(portal['price_now'].endswith('netto'))
        self.assertEqual(next(r for r in h['vorlagen'] if r['key'] == 'care')['former_offer'], '', 'Betreuung gab es nur als Paket')

    def test_no_second_price_source_left(self):
        src = {p.name: p.read_text(encoding='utf-8') for p in (ROOT / 'sales_tool').glob('*.py')}
        for name, text in src.items():
            if name == 'catalog.py':
                continue
            for needle in ('minimum_eur', 'price_from', 'PACKAGE_DETAILS =', 'ADDONS =', 'ADDONS[', 'from .sales_workspace import PACKAGES'):
                self.assertFalse(needle in text, f'{name}: {needle}')
        js = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'sales_tool' / 'public').glob('*.js'))
        self.assertNotIn('price_from', js)
        self.assertNotIn('minimum_eur', js)
        self.assertNotIn('percent: 40', js, 'Abschlag kommt aus dem Angebot, nicht aus einer festen Zahl')

    def test_legacy_package_call_uses_catalog(self):
        q = quote_preview(self.conn, {'package': 'pilot', 'addons': ['training'], 'tax_mode': 'regel_19'})
        self.assertEqual([p['service'] for p in q['customer']['positions']], ['website_analyse', 'aufwand', 'workshop'])
        self.assertEqual(q['customer']['positions'][2]['title'], 'Zusätzlicher Übergabe-Workshop')
        self.assertEqual(q['customer']['goal'], catalog.VORLAGEN['pilot']['outcome'])
        for field in catalog.LEGACY_CALC_FIELDS:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'zentralen Leistungskatalog'):
                quote_preview(self.conn, {'package': 'pilot', field: 50})


class ConsistencyTests(Base):
    """M12: eine geänderte Leistung wirkt überall gleich – und nur auf künftige Angebote."""

    def need(self):
        self.conn.execute("""INSERT INTO discovery(lead_id, problem, impact, desired_outcome, timing, decision_process)
                             VALUES (?, 'Kaum Anfragen über die Website, Relaunch geplant', 'Vertrieb wartet', 'Mehr passende Anfragen', 'Q1', 'GF')""", (self.lead,))
        self.conn.commit()

    def test_changed_service_flows_into_template_recommendation_and_quote(self):
        self.need()
        old = self.vorlage('conversion')['once_net_eur']
        rec = next(r for r in match_offers(self.conn, self.lead)['recommendations'] if r['package'] == 'conversion')
        self.assertEqual(rec['price_eur'], old)
        pr.save_override(self.conn, {'service': 'webdesign', 'size': 'M', 'fixed_price': 5000})
        new = self.vorlage('conversion')['once_net_eur']
        self.assertNotEqual(old, new)
        rec = next(r for r in match_offers(self.conn, self.lead)['recommendations'] if r['package'] == 'conversion')
        self.assertEqual(rec['price_eur'], new)
        self.assertIn(f"{new:,.0f}".replace(',', '.') + ' € einmalig', rec['price_label'])
        draft = quote_draft(self.conn, rec['id'])
        quote = pr.build_quote(self.conn, {'positions': draft['positions'], 'template': 'conversion'})
        self.assertEqual(quote['customer']['once_net_eur'], new)
        self.assertEqual(catalog.offers_for_client(self.conn)['conversion']['once_net_eur'], new)
        self.assertEqual(quote_preview(self.conn, {'package': 'conversion'})['customer']['net_eur'], new)
        # Zeitraum der Vorlage = Zeitraum im Angebot (eine Rechnung)
        self.assertEqual(self.vorlage('conversion')['weeks'], quote['customer']['weeks'])

    def test_saved_offers_keep_text_and_price(self):
        p = make_proposal(self.conn, {'lead_id': self.lead, 'package': 'brand', 'tax_mode': 'regel_19'})
        # ein Angebot im Format bis dev15 (früherer Paket-Rechner), direkt gespeichert
        legacy_customer = {'project_label': 'Alt', 'package': 'pilot', 'package_title': 'Website- & Anfrage-Pilot', 'goal': 'Ziel',
                           'included': ['Kurzaudit eines Anfragewegs'], 'excluded': ['Relaunch'], 'assumptions': '', 'deliverables': [],
                           'acceptance_criteria': [], 'third_party_costs': [], 'weeks': '1–2 Wochen', 'billing': 'einmalig', 'revision_rounds': 1,
                           'net_eur': 1450.0, 'vat_eur': 275.5, 'total_eur': 1725.5, 'tax_mode': 'regel_19', 'tax_note': 'Zuzüglich 19 % Umsatzsteuer',
                           'payment_plan': '40 % bei Beauftragung, 60 % nach vereinbarter Abnahme (Vorschlag, anpassen)',
                           'change_requests': 'x', 'guarantee': 'y'}
        lid = self.conn.execute("INSERT INTO proposals(lead_id, internal_json, customer_json, number) VALUES (?, '{}', ?, 'AN-2026-0099')",
                                (self.lead, json.dumps(legacy_customer))).lastrowid
        self.conn.commit()
        before = {i: (proposal_detail(self.conn, i), customer_markdown(proposal_detail(self.conn, i)['customer'])) for i in (p['id'], lid)}
        pr.save_override(self.conn, {'service': 'logo', 'size': 'L', 'fixed_price': 9990, 'revisions': 4})
        pr.save_pricing_settings(self.conn, {'hourly_rate': 90, 'deposit_pct': 20})
        init_db(self.conn)  # erneuter Start: keine Umrechnung gespeicherter Angebote
        after = {i: (proposal_detail(self.conn, i), customer_markdown(proposal_detail(self.conn, i)['customer'])) for i in (p['id'], lid)}
        self.assertEqual(before, after)
        self.assertIn('- Korrekturschleifen: 1', after[lid][1])
        self.assertNotEqual(self.vorlage('brand')['once_net_eur'], p['customer']['once_net_eur'])

    def test_catalog_version_is_stored_internally(self):
        a = make_proposal(self.conn, {'lead_id': self.lead, 'package': 'care'})
        pr.save_override(self.conn, {'service': 'pflege', 'size': 'M', 'hours': 6})
        b = make_proposal(self.conn, {'lead_id': self.lead, 'package': 'care'})
        va, vb = (proposal_detail(self.conn, x['id'])['internal']['catalog_version'] for x in (a, b))
        self.assertRegex(va, r'^[0-9a-f]{12}$')
        self.assertNotEqual(va, vb)
        self.assertNotIn('catalog_version', json.dumps(proposal_detail(self.conn, b['id'], customer_only=True)))


class RevisionAndScopeTests(Base):
    """K01 dauerhaft: Korrekturschleifen sind ein Feld je Leistung; der Umfangstext wiederholt keine Zahl, die abweichen könnte."""

    def test_no_revision_numbers_inside_scope_texts(self):
        for key, svc in catalog.SERVICES.items():
            for size, s in svc['sizes'].items():
                self.assertNotRegex(s['scope'], r'\d+\s+Korrektur', f'{key}/{size}')
            self.assertNotIn('Korrekturschleife', ' '.join(svc['included']), key)

    def test_override_changes_scope_and_summary_together(self):
        pr.save_override(self.conn, {'service': 'logo', 'size': 'S', 'revisions': 3})
        c = pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'S'}, {'service': 'texte', 'qty': 2}]})['customer']
        self.assertTrue(c['positions'][0]['scope'].endswith('· 3 Korrekturschleifen'))
        self.assertEqual(c['revision_note'], 'Pos. 1 Logogestaltung: 3 Korrekturschleifen; Pos. 2 Website- & Werbetexte: 1 Korrekturschleife je Seite/Text')
        md = customer_markdown(c)
        self.assertEqual(re.findall(r'(\d+) Korrekturschleife', md).count('1'), 2)  # Texte: im Umfang und in der Zusammenfassung
        self.assertNotIn('Korrekturschleifen: 2', md)
        with self.assertRaises(ValueError):
            pr.save_override(self.conn, {'service': 'logo', 'size': 'S', 'revisions': 1.5})
        pr.save_override(self.conn, {'service': 'logo', 'size': 'S', 'revisions': None})
        self.assertIn('1 Korrekturschleife', pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'S'}]})['customer']['positions'][0]['scope'])

    def test_missing_revisions_are_an_internal_open_point_only(self):
        q = pr.build_quote(self.conn, {'positions': [{'service': 'grafik', 'size': 'M'}, {'service': 'software', 'size': 'S'}]})
        self.assertTrue(any('Grafikdesign' in x and 'nicht festgelegt' in x for x in q['internal']['open_points']))
        self.assertFalse(any('Individualsoftware' in x for x in q['internal']['open_points']), 'Software hat keine Korrekturschleifen')
        self.assertEqual(q['customer']['revision_note'], '')
        md = customer_markdown(q['customer'])
        self.assertNotIn('Korrekturschleifen', md)
        self.assertNotIn('nicht festgelegt', md)

    def test_separate_position_exclusions_do_not_contradict(self):
        with_text = pr.build_quote(self.conn, {'positions': [{'service': 'webdesign', 'size': 'S'}, {'service': 'texte', 'qty': 3}]})['customer']
        self.assertNotIn('Texte (separate Position)', with_text['excluded'])
        self.assertIn('Fotografie (separate Position)', with_text['excluded'])
        alone = pr.build_quote(self.conn, {'positions': [{'service': 'webdesign', 'size': 'S'}]})['customer']
        self.assertIn('Texte (separate Position)', alone['excluded'])
        travel = pr.build_quote(self.conn, {'positions': [{'service': 'foto', 'size': 'S'}, {'service': 'anreise', 'km': 20, 'minutes': 25}]})['customer']
        self.assertNotIn('Anreise (separate Position)', travel['excluded'])


class PaymentAndChecksTests(Base):
    def test_deposit_is_a_visible_default_used_for_the_deposit_invoice(self):
        from sales_tool import accounting as acc
        acc.save_settings(self.conn, {'company_name': 'Fiktiv Studio', 'street': 'Musterweg 1', 'zip': '70191', 'city': 'Stuttgart',
                                      'tax_number': '99/999/99999', 'iban': 'DE89370400440532013000'})
        pr.save_pricing_settings(self.conn, {'deposit_pct': 30})
        p = make_proposal(self.conn, {'lead_id': self.lead, 'positions': [{'service': 'logo', 'size': 'M'}], 'tax_mode': 'regel_19'})
        c = p['customer']
        self.assertEqual((c['deposit_pct'], c['payment_plan']), (30, '30 % bei Beauftragung, 70 % nach Abnahme'))
        self.assertTrue(any('ausdrücklich vereinbaren' in x for x in p['internal']['open_points']))
        self.conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (p['id'],))
        inv = acc.invoice_from_proposal(self.conn, {'proposal_id': p['id'], 'mode': 'abschlag'})
        self.assertEqual(inv['net_cents'], round(c['net_eur'] * 30))
        pr.save_pricing_settings(self.conn, {'deposit_pct': 0})
        q = make_proposal(self.conn, {'lead_id': self.lead, 'positions': [{'service': 'logo', 'size': 'M'}], 'tax_mode': 'regel_19'})
        self.assertEqual(q['customer']['payment_plan'], 'Zahlung nach Abnahme')
        self.conn.execute("UPDATE proposals SET status='angenommen' WHERE id=?", (q['id'],))
        with self.assertRaisesRegex(ValueError, 'keine Anzahlung'):
            acc.invoice_from_proposal(self.conn, {'proposal_id': q['id'], 'mode': 'abschlag'})
        with self.assertRaises(ValueError):
            pr.save_pricing_settings(self.conn, {'deposit_pct': 95})

    def test_area_checks_internal_only(self):
        q = pr.build_quote(self.conn, {'positions': [{'service': 'webdesign', 'size': 'M'}, {'service': 'anreise', 'km': 10, 'minutes': 15}]})
        self.assertEqual([c['area'] for c in q['internal']['checks']], ['medien', 'software'])
        self.assertTrue(any('Quelldateien' in x for c in q['internal']['checks'] for x in c['items']))
        self.assertTrue(any('Betrieb' in x for c in q['internal']['checks'] for x in c['items']))
        blob = json.dumps(q['customer'], ensure_ascii=False) + customer_markdown(q['customer'])
        for word in ('Vor dem Versand', 'Quelldateien sind geklärt', 'open_points', 'checks'):
            self.assertNotIn(word, blob)


class AnalysisScopeTests(Base):
    """Bewertungsmodell (M31): Expertenprüfung abgegrenzt; eine Person, vier Blickwinkel; Lieferung ≠ Wirkungsziel."""

    def test_website_analysis_is_delimited(self):
        svc = catalog.SERVICES['website_analyse']
        self.assertIn('durch eine Person aus vier Blickwinkeln', svc['description'])
        self.assertIn('kein größerer Umbau nötig', svc['description'])
        self.assertTrue(any('Nutzerstudie' in x for x in svc['excluded']))
        self.assertTrue(any('Barrierefreiheit' in x for x in svc['excluded']))
        self.assertTrue(any('Wirkung' in x for x in svc['excluded']))
        self.assertIn('nicht eine spätere Wirkung', svc['acceptance'][0])
        self.assertEqual([s['hours'] for s in svc['sizes'].values()], [3, 8, 16], 'Startwerte unverändert')
        md = customer_markdown(quote_preview(self.conn, {'package': 'pilot'})['customer'])
        self.assertIn('Tests mit Personen aus der Zielgruppe (Nutzerstudie)', md)


class ApiTests(Base):
    def test_endpoints_deliver_one_catalog(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(str(self.db)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def get(path):
                c = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                c.request('GET', path)
                r = c.getresponse()
                body = json.loads(r.read())
                c.close()
                return r.status, body
            _, cat = get('/api/pricing/catalog')
            self.assertEqual([v['key'] for v in cat['vorlagen']], list(catalog.VORLAGEN))
            self.assertEqual(len(cat['herkunft']['vorlagen']), 6)
            self.assertIn('deposit_pct', cat['settings'])
            self.assertRegex(cat['version'], r'^[0-9a-f]{12}$')
            logo = next(s for g in cat['groups'] for s in g['services'] if s['key'] == 'logo')
            self.assertEqual((logo['sizes']['S']['revisions'], logo['sizes']['L']['revisions'], logo['korrekturen']), (1, None, True))
            _, conf = get('/api/config')
            self.assertEqual(conf['offers']['pilot']['once_net_eur'], cat['vorlagen'][0]['once_net_eur'])
            self.assertTrue(conf['offers']['care']['price_label'].endswith('/ Monat netto'))
            _, ws = get('/api/workspace/catalog')
            self.assertEqual(ws['packages'], conf['offers'])
            self.assertEqual(ws['addons'], {})
        finally:
            server.shutdown()
            server.server_close()

    def test_release_contains_catalog(self):
        from tools.build_release import RELEASE_ADDITIONS
        self.assertIn('sales_tool/catalog.py', RELEASE_ADDITIONS)
        self.assertIn('docs/LEISTUNGSKATALOG.md', RELEASE_ADDITIONS)


if __name__ == '__main__':
    unittest.main()
