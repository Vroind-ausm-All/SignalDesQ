"""Masterplan 2.0 – Sprint 2: Extraktion und einheitliche Belege.

Fertig-Kriterien aus dem Plan: alle Fakten in Fixtures belegbar; fehlende Daten bleiben leer; kein erdachter
Entscheider/Domain/Telefon; manuelle Prüffreigabe funktioniert. Fiktive Websites, simuliertes Netz – keine echten Abrufe.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from webfixtures import WEB, FixtureServer, simulated_network  # noqa: E402

from sales_tool import buying_signals as bs  # noqa: E402
from sales_tool import imprint  # noqa: E402
from sales_tool import report as rp  # noqa: E402
from sales_tool.company_data import facts_for_lead  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import policy as pol  # noqa: E402
from sales_tool.research import settings  # noqa: E402
from sales_tool.research.evidence import found_in, structured_evidence, validate_fields  # noqa: E402
from sales_tool.research.extractors import content, structured  # noqa: E402
from sales_tool.research.fetchers.base import decode_html  # noqa: E402


class StructuredTests(unittest.TestCase):
    def test_jsonld_organization_from_fixture(self):
        html = decode_html((WEB / 'strukturiert.example__index.html').read_bytes())
        st = structured.extract(html, 'http://strukturiert.example/')
        org = st['organizations'][0]
        self.assertEqual((org['name'], org['telephone'], org['email'], org['vat_id'], org['zip'], org['city']),
                         ('Strukturiert Daten GmbH', '+49 711 0000021', 'info@strukturiert.example', 'DE999000021', '70197', 'Stuttgart'))
        self.assertEqual(org['method'], 'jsonld')
        ev = {e['field']: e for e in structured_evidence(org, 'http://strukturiert.example/', html)}
        self.assertEqual(ev['business_phone']['value'], '+49 711 0000021')
        self.assertTrue(ev['business_phone']['content_hash'].startswith('sha256:'))

    def test_graph_microdata_opengraph_and_broken_blocks(self):
        page = ('<head><meta property="og:site_name" content="Muster"><script type="application/ld+json">{"@context":"https://schema.org",'
                '"@graph":[{"@type":"WebSite","name":"x"},{"@type":["LocalBusiness","Store"],"name":"Laden Muster KG","telephone":"0711 123456",}]}'
                '</script><script type="application/ld+json">{kaputt</script></head><body>'
                '<div itemscope itemtype="https://schema.org/Organization"><span itemprop="name">Mikro GmbH</span>'
                '<div itemprop="address" itemscope itemtype="https://schema.org/PostalAddress"><span itemprop="postalCode">70173</span>'
                '<span itemprop="addressLocality">Stuttgart</span></div><a itemprop="email" href="mailto:info@mikro.example">Mail</a></div>'
                '<div itemscope itemtype="https://schema.org/JobPosting"><h2 itemprop="title">Grafikdesigner (m/w/d)</h2>'
                '<meta itemprop="datePosted" content="2026-10-01"></div></body>')
        st = structured.extract(page)
        names = {o['name']: o for o in st['organizations']}
        self.assertEqual(names['Laden Muster KG']['telephone'], '0711 123456', '@graph + Typliste + abschließendes Komma')
        self.assertEqual(names['Mikro GmbH']['method'], 'microdata')
        self.assertEqual(names['Mikro GmbH']['email'], 'info@mikro.example')
        self.assertEqual(st['jobpostings'][0]['title'], 'Grafikdesigner (m/w/d)')
        self.assertEqual(st['opengraph']['site_name'], 'Muster')
        self.assertIn('Ungültiges JSON-LD – ausgelassen.', st['warnings'])
        huge = '<script type="application/ld+json">' + '{"a":"' + 'x' * 300_000 + '"}</script>'
        self.assertIn('zu groß', structured.extract(huge)['warnings'][0])


class EvidenceTests(unittest.TestCase):
    SRC = 'Impressum\nMuster GmbH\nTelefon: 0711 / 00 00 01\nRegistergericht: Stuttgart, HRB 700001\nUSt-IdNr.: DE 999 000 001\nmailto:info@muster.example'

    def test_found_in_normalisations(self):
        self.assertTrue(found_in('+49 711 000001', self.SRC, 'business_phone'), '+49 und 0-Vorwahl gleichwertig')
        self.assertTrue(found_in('DE999000001', self.SRC, 'vat_id'))
        self.assertTrue(found_in('Amtsgericht Stuttgart', self.SRC, 'register_court'))
        self.assertTrue(found_in('info@muster.example', self.SRC))
        self.assertFalse(found_in('+49 711 999999', self.SRC, 'business_phone'))
        self.assertFalse(found_in('', self.SRC))

    def test_invented_values_are_rejected(self):
        fields = {'legal_name': {'value': 'Muster GmbH', 'excerpt': 'Muster GmbH'},
                  'business_phone': {'value': '+49 711 4242424', 'excerpt': 'Telefon: 0711 4242424'},   # erfunden
                  'vat_id': {'value': 'DE999000001', 'excerpt': 'USt-IdNr.: DE 999 000 001'},
                  'business_email': {'value': 'chef@muster.example', 'excerpt': 'chef@muster.example'},  # erfunden
                  'street': None}
        checked, rejected = validate_fields(fields, self.SRC, 'http://muster.example/impressum', 'regel', chash='sha256:x')
        self.assertEqual(sorted(rejected), ['business_email', 'business_phone'])
        self.assertIsNone(checked['business_phone'], 'kein erdachtes Telefon')
        self.assertIsNone(checked['street'], 'fehlende Daten bleiben leer')
        ev = checked['vat_id']['evidence']
        self.assertEqual((ev['source_url'], ev['confidence'], ev['review_status'], ev['content_hash']),
                         ('http://muster.example/impressum', 'source_observed', 'unverified', 'sha256:x'))


class ContentTests(unittest.TestCase):
    HTML = ('<html><head><title>T</title></head><body><header><a href="/">Logo</a></header><nav>Start Leistungen</nav>'
            '<div class="cookie-banner">Wir nutzen Cookies</div><main><h1>Unsere Leistungen</h1><p>Wir planen und bauen Anlagen für den '
            'Mittelstand – seit 1998 in Stuttgart und der Region.</p></main><aside>Newsletter</aside><footer>Impressum · Datenschutz</footer></body></html>')

    def test_stdlib_main_text(self):
        t = content.main_text(self.HTML, use='stdlib')['text']
        self.assertIn('Unsere Leistungen', t)
        self.assertIn('seit 1998', t)
        for noise in ('Start Leistungen', 'Cookies', 'Newsletter', 'Datenschutz', 'Logo'):
            self.assertNotIn(noise, t)

    @unittest.skipUnless(content.trafilatura_available(), 'Trafilatura optional')
    def test_trafilatura_optional(self):
        out = content.main_text(self.HTML, use='trafilatura')
        self.assertEqual(out['engine'], 'trafilatura')
        self.assertIn('seit 1998', out['text'])


class FixtureExtractionTests(unittest.TestCase):
    def setUp(self):
        settings.reset()
        pol.ROBOTS.clear()
        self.server = FixtureServer().__enter__()
        self.netctx = simulated_network(self.server)
        self.netctx.__enter__()
        self.p = mock.patch.object(imprint, 'SLEEP', lambda s: None)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.netctx.__exit__(None, None, None)
        self.server.__exit__()
        pol.ROBOTS.clear()

    def test_every_value_has_evidence(self):
        manifest = json.loads((WEB / 'manifest.json').read_text(encoding='utf-8'))
        total = 0
        for host, spec in manifest['sites'].items():
            if 'legal_name' not in spec['expect'] or host.startswith('www.'):
                continue
            res = imprint.research_domain(f'http://{host}/', include_persons=False)
            for name, f in res['fields'].items():
                if f and f.get('value'):
                    total += 1
                    ev = f['evidence']
                    self.assertTrue(ev['source_url'].startswith('http://'), host)
                    self.assertTrue(ev['checked_at'] and ev['content_hash'].startswith('sha256:') and ev['method'], (host, name))
        self.assertGreater(total, 120)

    def test_pdf_zip_and_no_onepager_false_positive(self):
        pdf = imprint.research_domain('http://pdf-impressum.example/', include_persons=False)
        self.assertEqual(pdf['fields']['zip']['value'], '70180', 'PLZ im PDF-Fließtext')
        fremd = imprint.research_domain('http://fremd-weiterleitung.example/', include_persons=False)
        self.assertEqual(fremd['status'], 'kein_impressum', 'Wort „Impressum“ im Fuß ist kein One-Pager')
        one = imprint.research_domain('http://onepager.example/', include_persons=False)
        self.assertEqual(one['fields']['register_number']['value'], 'HRB 700017', 'echter One-Pager weiterhin erkannt')

    def test_structured_on_homepage_and_jobposting_signal(self):
        res = imprint.research_domain('http://strukturiert.example/', include_persons=False)
        self.assertEqual(res['structured']['organizations'][0]['telephone'], '+49 711 0000021')
        self.assertIn('business_phone', {e['field'] for e in res['structured']['evidence']})
        jobs, log = bs.scan_career('http://karriere-werke.example/', 'Karriere Werke AG')
        self.assertEqual([j['title'] for j in jobs], ['Webentwickler (m/w/d)'])
        self.assertEqual(jobs[0]['source_type'], 'karriereseite_jsonld')

    def test_report_stores_structured_facts_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'r.sqlite3'
            conn = connect(db)
            init_db(conn)
            conn.execute("INSERT INTO leads(company, website, industry) VALUES ('Strukturiert Daten GmbH', 'http://strukturiert.example/', 'Sonstige')")
            conn.commit()
            lead = conn.execute('SELECT * FROM leads').fetchone()
            status, detail, refs = rp._step_impressum(conn, db, lead)
            self.assertEqual(status, 'fertig')
            self.assertIn('strukturierte Angaben', detail)
            facts = [f for f in facts_for_lead(conn, lead['id']) if f['source_type'] == 'website_strukturiert']
            self.assertTrue(facts)
            self.assertTrue(all(f['status'] == 'ungeprueft' and f['method'] == 'jsonld' for f in facts), 'manuelle Prüffreigabe nötig')
            n = len(facts_for_lead(conn, lead['id']))
            rp._step_impressum(conn, db, lead)
            self.assertEqual(len(facts_for_lead(conn, lead['id'])), n, 'erneuter Lauf erzeugt keine doppelten Fakten')
            view = rp.report_view(conn, lead_id=lead['id'])
            conn.close()


if __name__ == '__main__':
    unittest.main()
