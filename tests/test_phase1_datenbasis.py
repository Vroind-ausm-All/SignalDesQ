"""Phase 1 – Datenbasis: Impressum-Extraktion, Batch, Sperrliste, Feldbelege, Datenschutz-Nachweise.

Alle Firmen, Personen und Nummern sind fiktiv. Der Netzwerkzugriff wird durch einen Stub ersetzt –
das ist kein Live-Test echter Websites.
"""
import json
import tempfile
import threading
import unittest
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool import imprint, imprint_batch as ib
from sales_tool import company_data as cd
from sales_tool.model import connect, init_db
from sales_tool.server import make_handler, import_leads
from sales_tool.website_analyzer import CrawlError

FIX = Path(__file__).parent / 'fixtures' / 'impressum'


def html(name):
    return (FIX / name).read_bytes()


def make_pdf(lines):
    content = b'BT /F1 11 Tf 50 800 Td ' + b' T* '.join(b'(' + l.encode('cp1252').replace(b'(', b'\\(').replace(b')', b'\\)') + b') Tj' for l in lines) + b' ET'
    stream = zlib.compress(content)
    return (b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n4 0 obj << /Length ' + str(len(stream)).encode() +
            b' /Filter /FlateDecode >>\nstream\n' + stream + b'\nendstream\nendobj\ntrailer << >>\n%%EOF')


class FakeWeb:
    """Bildet Websites als Dict url → (content_type, bytes) ab. Fehlende URLs → HTTP 404."""
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url, origin=None):
        self.calls.append(url)
        url = url if '://' in url else 'https://' + url
        key = url.rstrip('/')
        for candidate in (key, key + '/', url):
            if candidate in self.pages:
                ctype, body = self.pages[candidate]
                if isinstance(body, Exception):
                    raise body
                return candidate, ctype, body
        raise CrawlError('HTTP 404')


HOME = lambda links: ('text/html', ('<html><body><nav>' + ''.join(f'<a href="{h}">{t}</a>' for h, t in links) + '</nav><h1>Willkommen</h1></body></html>').encode())

WEB = {
    'https://musterwerk-beispiel.de': HOME([('/kontakt', 'Kontakt'), ('/datenschutz', 'Datenschutz'), ('/rechtliches/anbieter', 'Impressum')]),
    'https://musterwerk-beispiel.de/rechtliches/anbieter': ('text/html', html('gmbh_co_kg.html')),
    'https://pixelhafen-beispiel.de': HOME([('https://fremde-agentur.example/impressum', 'Impressum')]),
    'https://pixelhafen-beispiel.de/impressum': ('text/html', html('ug.html')),
    'https://holzmann-beispiel.de': HOME([('/imprint.pdf', 'Impressum (PDF)')]),
    'https://holzmann-beispiel.de/imprint.pdf': ('application/pdf', make_pdf(['Impressum', 'Tischlerei Holzmann e.K.', 'Inhaber: Peter Holzmann',
                                                                              'Lindenweg 3', '01067 Dresden', 'Amtsgericht Dresden, HRA 4567'])),
    'https://offline-beispiel.de': ('text/html', CrawlError('Nicht erreichbar (timeout)')),
    'https://leer-beispiel.de': HOME([('/kontakt', 'Kontakt')]),
}


class ExtractionTests(unittest.TestCase):
    def extract(self, name, domain=''):
        text, _, mails = imprint.html_to_text(html(name))
        return imprint.extract(text, mails, domain)

    def test_gmbh_co_kg_with_general_partner(self):
        r = self.extract('gmbh_co_kg.html', 'musterwerk-beispiel.de')
        f = {k: (v['value'] if v else None) for k, v in r['fields'].items()}
        self.assertEqual(f['legal_name'], 'Musterwerk Präzisionstechnik GmbH & Co. KG')
        self.assertEqual(f['legal_form'], 'GmbH & Co. KG')
        self.assertEqual((f['street'], f['zip'], f['city']), ('Industriestraße 12a', '70565', 'Stuttgart'))
        self.assertEqual((f['register_court'], f['register_number']), ('Amtsgericht Stuttgart', 'HRA 123456'))
        self.assertEqual(f['vat_id'], 'DE136695976')
        self.assertTrue(r['fields']['vat_id']['checksum_ok'])
        self.assertEqual(f['business_email'], 'info@musterwerk-beispiel.de')  # [at]/[dot] aufgelöst
        self.assertEqual(f['business_phone'], '+49 (0)711 123456-0')          # nicht die Faxnummer
        self.assertIn('keine persönliche Durchwahl', r['fields']['business_phone']['note'])
        partner = r['entities'][1]
        self.assertEqual((partner['name'], partner['role'], partner['register']),
                         ('Musterwerk Verwaltungs GmbH', 'Komplementärin', 'Amtsgericht Stuttgart HRB 765432'))
        self.assertEqual([p['name'] for p in r['representatives']], ['Anna Beispiel', 'Max Mustermann'])
        self.assertNotIn('Fake GmbH', json.dumps(r))  # Script-Inhalte werden ignoriert
        for key, field in r['fields'].items():
            if field:
                self.assertTrue(field['excerpt'], key)
                self.assertEqual(field['method'], imprint.METHOD)

    def test_ug_sentence_style_and_mailto(self):
        r = self.extract('ug.html', 'pixelhafen-beispiel.de')
        f = {k: (v['value'] if v else None) for k, v in r['fields'].items()}
        self.assertEqual(f['legal_name'], 'Pixelhafen UG (haftungsbeschränkt)')
        self.assertEqual((f['street'], f['zip'], f['city']), ('Am Sandtorkai 5', '20457', 'Hamburg'))
        self.assertEqual((f['register_court'], f['register_number']), ('Amtsgericht Hamburg', 'HRB 998877'))
        self.assertEqual(f['business_email'], 'hallo@pixelhafen-beispiel.de')
        self.assertEqual([(p['name'], p['role']) for p in r['representatives']], [('Lea Nordmann', 'Geschäftsführung')])
        self.assertFalse(r['fields']['vat_id']['checksum_ok'])
        self.assertTrue(any('Prüfziffer' in w for w in r['warnings']))

    def test_sole_trader_english_and_minimal(self):
        ek = self.extract('ek.html')
        self.assertEqual(ek['fields']['legal_form']['value'], 'e.K.')
        self.assertEqual([(p['name'], p['role']) for p in ek['representatives']], [('Peter Holzmann', 'Inhaber/in')])
        en = self.extract('english.html', 'nordlicht-beispiel.de')
        self.assertEqual(en['fields']['register_court']['value'], 'Amtsgericht München')
        self.assertEqual([p['name'] for p in en['representatives']], ['Jonas Weber', 'Maria Schulz'])  # Aufsichtsrat nicht
        self.assertIn('personenbezogen', en['fields']['business_email']['note'])
        minimal = self.extract('minimal.html')
        self.assertTrue(all(v is None for v in minimal['fields'].values()))
        self.assertEqual(minimal['completeness']['found'], 0)
        self.assertTrue(minimal['warnings'])

    def test_persons_can_be_disabled(self):
        text, _, mails = imprint.html_to_text(html('gmbh_co_kg.html'))
        self.assertEqual(imprint.extract(text, mails, '', include_persons=False)['representatives'], [])

    def test_vat_checksum(self):
        self.assertTrue(imprint.vat_checksum_ok('DE136695976'))
        self.assertFalse(imprint.vat_checksum_ok('DE136695977'))
        self.assertFalse(imprint.vat_checksum_ok('ATU12345678'))

    def test_pdf_text_extraction(self):
        text = imprint.pdf_to_text(make_pdf(['Impressum', 'Druckhaus Beispiel GmbH', 'Papierweg 1', '04109 Leipzig']))
        self.assertIn('Druckhaus Beispiel GmbH', text)
        self.assertEqual(imprint.pdf_to_text(b'%PDF-1.4 kaputt'), '')

    def test_imprint_link_detection(self):
        links = [{'href': '/datenschutz', 'text': 'Datenschutz'}, {'href': '/service/legal-notice', 'text': 'Legal Notice'},
                 {'href': 'https://other.example/impressum', 'text': 'Impressum'}, {'href': '/de/impressum#top', 'text': 'Impressum'}]
        found = imprint.find_imprint_links('https://www.firma-beispiel.de/', links)
        self.assertEqual(found, ['https://www.firma-beispiel.de/de/impressum', 'https://www.firma-beispiel.de/service/legal-notice'])


class ResearchDomainTests(unittest.TestCase):
    def setUp(self):
        self._orig = (imprint.FETCH, imprint.SLEEP)
        imprint.FETCH, imprint.SLEEP = FakeWeb(WEB), (lambda s: None)

    def tearDown(self):
        imprint.FETCH, imprint.SLEEP = self._orig

    def test_link_not_named_impressum_path(self):
        r = imprint.research_domain('musterwerk-beispiel.de')
        self.assertEqual(r['imprint_url'], 'https://musterwerk-beispiel.de/rechtliches/anbieter')
        self.assertEqual(r['status'], 'ok')

    def test_foreign_link_ignored_and_fallback_path(self):
        r = imprint.research_domain('pixelhafen-beispiel.de')
        self.assertEqual(r['imprint_url'], 'https://pixelhafen-beispiel.de/impressum')
        self.assertNotIn('https://fremde-agentur.example/impressum', imprint.FETCH.calls)

    def test_pdf_imprint(self):
        r = imprint.research_domain('holzmann-beispiel.de')
        self.assertEqual(r['source_type'], 'impressum_pdf')
        self.assertEqual(r['fields']['register_number']['value'], 'HRA 4567')

    def test_missing_and_unreachable(self):
        r = imprint.research_domain('leer-beispiel.de')
        self.assertEqual(r['status'], 'kein_impressum')
        with self.assertRaises(CrawlError):
            imprint.research_domain('offline-beispiel.de')


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'p1.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self._orig = (imprint.FETCH, imprint.SLEEP)
        imprint.FETCH, imprint.SLEEP = FakeWeb(WEB), (lambda s: None)

    def tearDown(self):
        imprint.FETCH, imprint.SLEEP = self._orig
        self.conn.close()
        self.tmp.cleanup()

    def run_all(self, domains, **opts):
        run = ib.create_run(self.conn, {'domains': domains, **opts}, self.db)
        ib.wait_for(run['id'])
        return ib.run_detail(self.conn, run['id'])

    def test_batch_survives_errors_and_dedupes_input(self):
        run = self.run_all('musterwerk-beispiel.de\nhttps://www.musterwerk-beispiel.de/\noffline-beispiel.de\nleer-beispiel.de\nkein domain\npixelhafen-beispiel.de')
        status = {i['domain']: i['status'] for i in run['items']}
        self.assertEqual(status, {'musterwerk-beispiel.de': 'done', 'offline-beispiel.de': 'failed',
                                  'leer-beispiel.de': 'kein_impressum', 'pixelhafen-beispiel.de': 'done'})
        self.assertEqual(run['status'], 'done')
        failed = next(i for i in run['items'] if i['status'] == 'failed')
        self.assertIn('timeout', failed['error'])
        self.assertEqual(run['review_open'], 2)

    def test_limits_and_csv(self):
        with self.assertRaisesRegex(ValueError, '100'):
            ib.parse_input('\n'.join(f'firma{i}-beispiel.de' for i in range(101)))
        items, rejected = ib.parse_input(csv_text='﻿firma;website\nMusterwerk;musterwerk-beispiel.de\nX;;\n')
        self.assertEqual(items[0]['company_hint'], 'Musterwerk')
        with self.assertRaisesRegex(ValueError, 'Spalte'):
            ib.parse_input(csv_text='name;ort\nA;B\n')
        for bad in ({'domains': 'a.de', 'parallel': 9}, {'domains': 'a.de', 'evil': 1}, {'domains': ''}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ib.create_run(self.conn, bad, self.db, start=False)

    def test_pause_resume_and_restart_recovery(self):
        run = ib.create_run(self.conn, {'domains': 'musterwerk-beispiel.de\npixelhafen-beispiel.de'}, self.db, start=False)
        ib.control_run(self.conn, run['id'], 'pause', self.db)
        self.assertEqual(ib.run_detail(self.conn, run['id'])['status'], 'paused')
        self.conn.execute("UPDATE batch_items SET status='running' WHERE run_id=? AND position=1", (run['id'],))
        self.conn.execute("UPDATE batch_runs SET status='running' WHERE id=?", (run['id'],))
        self.conn.commit()
        ib.recover_batches(self.conn)  # simulierter Neustart
        self.conn.commit()
        detail = ib.run_detail(self.conn, run['id'])
        self.assertEqual(detail['status'], 'paused')
        self.assertEqual(detail['counts'], {'pending': 2})
        ib.control_run(self.conn, run['id'], 'resume', self.db)
        ib.wait_for(run['id'])
        self.assertEqual(ib.run_detail(self.conn, run['id'])['counts'], {'done': 2})
        with self.assertRaises(ValueError):
            ib.control_run(self.conn, run['id'], 'pause', self.db)

    def test_review_new_lead_with_facts_persons_and_privacy(self):
        run = self.run_all('musterwerk-beispiel.de')
        item = run['items'][0]
        res = ib.review_item(self.conn, item['id'], {'decision': 'neu'})
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertEqual(lead['company'], 'Musterwerk Präzisionstechnik GmbH & Co. KG')
        self.assertEqual((lead['register_number'], lead['zip'], lead['permission']), ('HRA 123456', '70565', 'unbekannt'))
        self.assertEqual(lead['imprint_url'], 'https://musterwerk-beispiel.de/rechtliches/anbieter')
        facts = cd.facts_for_lead(self.conn, res['lead_id'])
        self.assertTrue(all(f['source_url'] and f['method'] for f in facts))
        self.assertIn('related_entity', {f['field'] for f in facts})
        contacts = self.conn.execute('SELECT * FROM decision_contacts WHERE lead_id=?', (res['lead_id'],)).fetchall()
        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0]['verification_status'], 'quelle_geprueft')
        self.assertNotIn('123456', contacts[0]['business_phone'] or '')  # keine Firmennummer als Durchwahl
        privacy = cd.privacy_rows(self.conn, res['lead_id'])
        self.assertEqual(len(privacy), 2)
        self.assertIn('Art. 6 Abs. 1 lit. f', privacy[0]['legal_basis'])
        self.assertIn('Art. 21', cd.art14_text(self.conn, privacy[0]['id'])['text'])
        with self.assertRaisesRegex(ValueError, 'bereits'):
            ib.review_item(self.conn, item['id'], {'decision': 'neu'})

    def test_duplicate_by_register_and_merge_without_overwrite(self):
        cur = self.conn.execute("""INSERT INTO leads(company, website, register_court, register_number, city)
                                   VALUES ('Musterwerk KG', 'https://alt-domain-beispiel.de', 'Amtsgericht Stuttgart', 'HRA 123456', 'Esslingen')""")
        lead_id = cur.lastrowid
        self.conn.commit()
        run = self.run_all('musterwerk-beispiel.de')
        item = run['items'][0]
        self.assertEqual((item['duplicate_lead_id'], item['duplicate_reason']), (lead_id, 'register'))
        with self.assertRaisesRegex(ValueError, 'ergänzen'):
            ib.review_item(self.conn, item['id'], {'decision': 'neu'})
        res = ib.review_item(self.conn, item['id'], {'decision': 'ergaenzen', 'include_representatives': False})
        self.assertIn('city', res['kept_existing'])
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
        self.assertEqual(lead['city'], 'Esslingen')
        self.assertEqual(lead['vat_id'], 'DE136695976')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM decision_contacts').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM privacy_records').fetchone()[0], 0)

    def test_choose_other_entity_and_discard(self):
        run = self.run_all('musterwerk-beispiel.de\npixelhafen-beispiel.de')
        a, b = run['items']
        res = ib.review_item(self.conn, a['id'], {'decision': 'neu', 'entity_index': 1, 'include_representatives': False})
        self.assertEqual(self.conn.execute('SELECT company FROM leads WHERE id=?', (res['lead_id'],)).fetchone()[0], 'Musterwerk Verwaltungs GmbH')
        self.assertEqual(ib.review_item(self.conn, b['id'], {'decision': 'verwerfen'})['review_status'], 'verworfen')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)


class SuppressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'sup.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self._orig = (imprint.FETCH, imprint.SLEEP)
        imprint.FETCH, imprint.SLEEP = FakeWeb(WEB), (lambda s: None)

    def tearDown(self):
        imprint.FETCH, imprint.SLEEP = self._orig
        self.conn.close()
        self.tmp.cleanup()

    def blocked_lead(self):
        cur = self.conn.execute("""INSERT INTO leads(company, website, register_court, register_number, stage, permission)
                                   VALUES ('Pixelhafen UG (haftungsbeschränkt)', 'https://www.pixelhafen-beispiel.de', 'Amtsgericht Hamburg', 'HRB 998877', 'gesperrt', 'nicht_kontaktieren')""")
        cd.suppress_lead(self.conn, cur.lastrowid)
        self.conn.commit()
        return cur.lastrowid

    def test_suppression_survives_deletion_and_blocks_all_imports(self):
        lid = self.blocked_lead()
        kinds = {r['kind'] for r in cd.suppression_rows(self.conn)}
        self.assertEqual(kinds, {'domain', 'name', 'register'})
        self.conn.execute('DELETE FROM leads WHERE id=?', (lid,))
        self.conn.commit()
        res = import_leads(self.conn, {'rows': [{'company': 'Pixelhafen', 'website': 'https://pixelhafen-beispiel.de'}]})
        self.assertEqual((res['imported'], res.get('suppressed')), (0, 1))
        run = ib.create_run(self.conn, {'domains': 'pixelhafen-beispiel.de'}, self.db)
        ib.wait_for(run['id'])
        detail = ib.run_detail(self.conn, run['id'])
        self.assertEqual(detail['items'][0]['status'], 'gesperrt')
        self.assertEqual(detail['skipped_suppressed'] if 'skipped_suppressed' in detail else run['skipped_suppressed'], 1)
        self.assertNotIn('https://pixelhafen-beispiel.de', imprint.FETCH.calls)  # gar nicht abgerufen
        with self.assertRaisesRegex(ValueError, 'Sperrliste'):
            cd.assert_not_suppressed(self.conn, register_court='AG Hamburg', register_number='HRB 998877')

    def test_register_hit_after_extraction(self):
        cd.add_suppression(self.conn, 'register', ('Amtsgericht Stuttgart', 'HRA 123456'), 'Widerspruch per Brief')
        self.conn.commit()
        run = ib.create_run(self.conn, {'domains': 'musterwerk-beispiel.de'}, self.db)
        ib.wait_for(run['id'])
        item = ib.run_detail(self.conn, run['id'])['items'][0]
        self.assertEqual(item['status'], 'gesperrt')
        with self.assertRaises(ValueError):
            ib.review_item(self.conn, item['id'], {'decision': 'neu'})

    def test_remove_requires_reason(self):
        self.blocked_lead()
        entry = cd.suppression_rows(self.conn)[0]
        with self.assertRaisesRegex(ValueError, 'Begründung'):
            cd.remove_suppression(self.conn, entry['id'], '')
        cd.remove_suppression(self.conn, entry['id'], 'Schriftliche Einwilligung vom 01.11.2026')
        self.assertIn('aufgehoben', [r['action'] for r in self.conn.execute('SELECT action FROM audit_log')])

    def test_fact_status_updates_lead(self):
        cur = self.conn.execute("INSERT INTO leads(company) VALUES ('Beispiel GmbH')")
        lid = cur.lastrowid
        fid = cd.add_fact(self.conn, lid, 'vat_id', 'DE136695976', 'manuell', '', 'USt-IdNr. DE136695976', 'manuell')
        cd.set_fact_status(self.conn, fid, 'bestaetigt')
        self.assertEqual(self.conn.execute('SELECT vat_id FROM leads WHERE id=?', (lid,)).fetchone()[0], 'DE136695976')
        cd.set_fact_status(self.conn, fid, 'veraltet')
        self.assertEqual(self.conn.execute('SELECT vat_id FROM leads WHERE id=?', (lid,)).fetchone()[0], '')
        with self.assertRaises(ValueError):
            cd.set_fact_status(self.conn, fid, 'egal')


class Phase1HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'http.sqlite3'
        with connect(self.db) as conn:
            init_db(conn)
        self._orig = (imprint.FETCH, imprint.SLEEP)
        imprint.FETCH, imprint.SLEEP = FakeWeb(WEB), (lambda s: None)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        imprint.FETCH, imprint.SLEEP = self._orig
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_flow_over_http(self):
        status, run = self.call('/api/imprint/runs', 'POST', {'domains': 'musterwerk-beispiel.de'})
        self.assertEqual(status, 202, run)
        ib.wait_for(run['id'])
        status, detail = self.call(f"/api/imprint/runs/{run['id']}")
        item = detail['items'][0]
        self.assertEqual(item['status'], 'done')
        status, res = self.call(f"/api/imprint/items/{item['id']}/review", 'POST', {'decision': 'neu', 'fields': ['legal_name', 'zip', 'city']})
        self.assertEqual(status, 200, res)
        status, facts = self.call(f"/api/leads/{res['lead_id']}/facts")
        statuses = {f['field']: f['status'] for f in facts['facts']}
        self.assertEqual(statuses['legal_name'], 'bestaetigt')
        self.assertEqual(statuses['vat_id'], 'ungeprueft')  # nicht ausgewählt → nur als Beleg gespeichert
        self.assertEqual(facts['company']['vat_id'], '')
        status, lead = self.call(f"/api/leads/{res['lead_id']}", 'PATCH', {'stage': 'gesperrt'})
        self.assertEqual(lead['permission'], 'nicht_kontaktieren')
        status, sup = self.call('/api/suppression')
        self.assertTrue(any(s['kind'] == 'domain' and s['value'] == 'musterwerk-beispiel.de' for s in sup))
        status, err = self.call('/api/leads', 'POST', {'company': 'Neu', 'website': 'https://www.musterwerk-beispiel.de'})
        self.assertEqual(status, 409)
        self.assertIn('Sperrliste', err['error'])
        status, err = self.call(f"/api/suppression/{sup[0]['id']}", 'DELETE', {'reason': ''})
        self.assertEqual(status, 400)
        status, priv = self.call('/api/privacy')
        self.assertEqual(status, 200)
        status, _ = self.call('/api/suppression', 'POST', {'kind': 'email', 'value': 'stop@beispiel.de', 'reason': 'Abmeldung'})
        self.assertEqual(status, 201)


if __name__ == '__main__':
    unittest.main()
