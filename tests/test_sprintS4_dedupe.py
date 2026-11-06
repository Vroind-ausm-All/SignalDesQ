"""Masterplan 2.0 – Sprint 4: Dubletten zuverlässig erkennen und nicht doppelt aufführen.

Abnahme laut Plan: gleiche LEI wird nicht dupliziert; fremde Firmen werden nicht versehentlich zusammengeführt;
fehlende Websites sind sichtbar. Dazu (Wunsch des Nutzers): mögliche Dubletten erscheinen nicht als eigene Einträge,
sondern beim Haupteintrag zur Entscheidung. Alle Firmen sind fiktiv, es gibt keine Netzabfragen.
"""
import json
import sqlite3
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from sales_tool import duplicates as du
from sales_tool import lead_finder as lf
from sales_tool import sweep as sw
from sales_tool.company_data import find_duplicate
from sales_tool.model import connect, init_db
from sales_tool.research import identity as ident
from sales_tool.server import make_handler, prepare_database

LEI = '529900ABCDEFGHIJKL01'


def F(name, **kw):
    return {'name': name, **kw}


class IdentityTests(unittest.TestCase):
    def v(self, a, b):
        return ident.decide(a, b)[0]

    def test_same(self):
        cases = [
            (F('Müller Maschinenbau GmbH', city='Stuttgart'), F('Mueller Maschinenbau GmbH', city='Stuttgart')),
            (F('Müller Maschinenbau GmbH', zip='70173'), F('Müller Maschinenbau Gesellschaft mit beschränkter Haftung', zip='70173')),
            (F('Kabelwerk Reith GmbH', city='Esslingen am Neckar'), F('Reith Kabelwerk GmbH', city='Esslingen')),
            (F('Reith-Spezialkabel GmbH', city='Stuttgart'), F('Reith Spezialkabel GmbH', city='Stuttgart')),
            (F('A GmbH', lei=LEI), F('Ganz anders AG', lei=LEI)),
            (F('Nordlicht Software GmbH', register_id='HRB 12345', city='Ulm'), F('Nordlicht GmbH', register_id='HRB12345', city='Ulm')),
            (F('Nordlicht Software GmbH', website='https://www.nordlicht.example/kontakt'), F('Nordlicht Software', website='nordlicht.example')),
        ]
        for a, b in cases:
            self.assertEqual(self.v(a, b), 'same', (a, b, ident.decide(a, b)))

    def test_different(self):
        cases = [
            (F('Müller Maschinenbau GmbH', city='Stuttgart'), F('Müller Maschinenbau GmbH & Co. KG', city='Stuttgart')),
            (F('Müller Maschinenbau', legal_form='GmbH', city='Stuttgart'), F('Müller Maschinenbau GmbH & Co. KG', legal_form='GmbH', city='Stuttgart')),
            (F('Nordlicht GmbH', register_id='HRB 1'), F('Nordlicht GmbH', register_id='HRB 2')),
            (F('Nordlicht GmbH', lei=LEI), F('Nordlicht GmbH', lei='529900ZZZZZZZZZZZZ99')),
            (F('Nordlicht GmbH', city='Ulm'), F('Nordlicht GmbH', city='Hamburg')),
            (F('Nordlicht GmbH', city='Ulm'), F('Südwind GmbH', city='Ulm')),
            (F('Kesselwerk GmbH', website='https://facebook.com/x'), F('Bäckerei Sonne GmbH', website='https://facebook.com/x')),
            (F('Nordlicht Verwaltungs GmbH', city='Ulm'), F('Nordlicht GmbH & Co. KG', city='Ulm')),
        ]
        for a, b in cases:
            self.assertEqual(self.v(a, b), 'different', (a, b, ident.decide(a, b)))

    def test_possible(self):
        # gewöhnlicher Name ohne Ort: Prüffrage statt automatisch
        self.assertEqual(self.v(F('Müller GmbH'), F('Müller GmbH', city='Ulm')), 'possible')
        self.assertEqual(self.v(F('Nordlicht Software GmbH', city='Ulm'), F('Nordlicht Softwares GmbH', city='Ulm')), 'possible')

    def test_ambiguous_match_is_only_possible(self):
        idx = ident.Index()
        idx.add(1, F('Müller Maschinenbau GmbH', city='Stuttgart'))
        idx.add(2, F('Müller Maschinenbau GmbH', city='Hamburg'))
        hit = idx.best(F('Müller Maschinenbau', legal_form='GmbH'))
        self.assertEqual(hit[0], 'possible')
        self.assertIn('mehreren Firmen', hit[3])
        self.assertEqual(idx.best(F('Mueller Maschinenbau GmbH', city='Hamburg'))[:2], ('same', 2))

    def test_blocking_is_fast(self):
        import time
        idx = ident.Index()
        for i in range(20000):
            idx.add(i, F(f'Firma{i:05d} Beispielwerk GmbH', zip=f'{10000 + i % 80000:05d}', city=f'Ort{i % 500}'))
        t = time.perf_counter()
        for i in range(0, 20000, 100):
            idx.best(F(f'Firma{i:05d} Beispielwerk GmbH', zip=f'{10000 + i % 80000:05d}', city=f'Ort{i % 500}'))
        self.assertLess((time.perf_counter() - t) / 200, 0.05)  # < 50 ms je Abgleich bei 20 000 Firmen


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'd.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.sid = self.conn.execute("INSERT INTO sweeps(label, params_json) VALUES ('Test', '{}')").lastrowid
        self.run = sw._run_record(self.conn, 'gleif', self.sid, {})
        self.ctx = {'industries': [], 'keywords': [], 'org_kinds': sw.ORG_KINDS_DEFAULT}

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def store(self, source, items):
        return sw.store_items(self.conn, self.sid, self.run, source, [dict(x) for x in items], self.ctx)

    def listing(self, **q):
        return sw.candidates(self.conn, {k: [v] for k, v in q.items()})

    def lead(self, company, **kw):
        cols = {'company': company, **kw}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(cols.values()))
        self.conn.commit()
        return cur.lastrowid


class SweepDuplicateTests(Base):
    def test_same_lei_never_duplicated(self):
        self.store('gleif', [F('Nordlicht Software GmbH', lei=LEI, zip='89073', city='Ulm', register_id='HRB 1')])
        self.store('gleif_csv', [F('NORDLICHT SOFTWARE GMBH', lei=LEI)])
        self.store('wikidata', [F('Nordlicht Software', lei=LEI, website='https://nordlicht.example', legal_form='GmbH')])
        self.store('osm', [F('Nordlicht Software GmbH', zip='89073', city='Ulm', website='https://www.nordlicht.example/')])
        rows = self.conn.execute("SELECT * FROM discovery_candidates WHERE status<>'zusammengefuehrt'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual({s['source'] for s in json.loads(rows[0]['sources_json'])}, {'gleif', 'gleif_csv', 'wikidata', 'osm'})
        self.assertEqual(rows[0]['website'], 'https://nordlicht.example')
        # zweiter Lauf: nichts Neues
        c = self.store('gleif', [F('Nordlicht Software GmbH', lei=LEI, zip='89073', city='Ulm')])
        self.assertEqual((c['new'], c['merged']), (0, 1))

    def test_foreign_firms_not_merged(self):
        self.ctx['operative'] = False  # Verwaltungs-GmbH nicht als Holding ausfiltern – hier geht es um die Trennung
        self.store('gleif', [
            F('Müller Maschinenbau GmbH', zip='70173', city='Stuttgart', register_id='HRB 100'),
            F('Müller Maschinenbau GmbH & Co. KG', zip='70173', city='Stuttgart', register_id='HRA 200'),
            F('Müller Maschinenbau Verwaltungs GmbH', zip='70173', city='Stuttgart'),
            F('Müller Maschinenbau GmbH', zip='20095', city='Hamburg'),
            F('Müller Maschinenbau GmbH', zip='70173', city='Stuttgart', register_id='HRB 999', lei='529900ZZZZZZZZZZZZ99'),
        ])
        # Wikidata nennt „GmbH“ als Rechtsform, der Name sagt „& Co. KG“ – bleibt die KG
        self.store('wikidata', [F('Müller Maschinenbau GmbH & Co. KG', legal_form='GmbH', zip='70173', city='Stuttgart')])
        items = self.listing(status='neu')['items']
        self.assertEqual(len(items), 5)
        kg = [x for x in items if 'Co. KG' in x['name']][0]
        self.assertEqual({s['source'] for s in kg['sources']}, {'gleif', 'wikidata'})
        self.assertFalse(any(x['possible_duplicates'] for x in items))

    def test_possible_duplicates_grouped_not_listed_twice(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm')])
        self.store('osm', [F('Nordlicht Softwares GmbH', zip='89073', city='Ulm'), F('Südwind Bau GmbH', zip='89073', city='Ulm')])
        data = self.listing(status='neu')
        names = [x['name'] for x in data['items']]
        self.assertEqual(sorted(names), ['Nordlicht Software GmbH', 'Südwind Bau GmbH'])
        primary = [x for x in data['items'] if x['name'].startswith('Nordlicht')][0]
        self.assertEqual([d['name'] for d in primary['possible_duplicates']], ['Nordlicht Softwares GmbH'])
        self.assertEqual(data['counts']['neu'], 2)
        self.assertEqual(data['counts']['moegliche_dubletten'], 1)
        review = self.listing(dups='1')
        self.assertEqual([x['name'] for x in review['items']], ['Nordlicht Softwares GmbH'])
        self.assertEqual(review['items'][0]['duplicate_primary']['id'], primary['id'])

    def test_review_same_merges_and_learns_keys(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm', lei=LEI)])
        self.store('osm', [F('Nordlicht Softwares GmbH', zip='89073', city='Ulm', website='https://nordlicht.example')])
        dup = self.listing(dups='1')['items'][0]
        res = sw.review_duplicate(self.conn, dup['id'], 'gleich')
        self.assertEqual(res['status'], 'zusammengefuehrt')
        items = self.listing(status='neu')['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['website'], 'https://nordlicht.example')
        self.assertEqual({s['source'] for s in items[0]['sources']}, {'gleif', 'osm'})
        # derselbe OSM-Eintrag kommt beim nächsten Suchlauf wieder → landet sofort beim Haupteintrag
        c = self.store('osm', [F('Nordlicht Softwares GmbH', zip='89073', city='Ulm', website='https://nordlicht.example')])
        self.assertEqual((c['new'], c['merged']), (0, 1))
        self.assertEqual(self.listing(status='zusammengefuehrt')['total'], 1)

    def test_review_different_keeps_both_and_is_remembered(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm')])
        self.store('osm', [F('Nordlicht Softwares GmbH', zip='89073', city='Ulm')])
        dup = self.listing(dups='1')['items'][0]
        sw.review_duplicate(self.conn, dup['id'], 'verschieden')
        self.assertEqual(len(self.listing(status='neu')['items']), 2)
        self.assertEqual(sw.dedupe_candidates(self.conn)['possible'], 0)
        self.assertEqual(self.listing(dups='1')['total'], 0)
        with self.assertRaises(ValueError):
            sw.review_duplicate(self.conn, dup['id'], 'gleich')

    def test_takeover_rehomes_possible_duplicates(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm')])
        self.store('osm', [F('Nordlicht Softwares GmbH', zip='89073', city='Ulm')])
        primary = self.listing(status='neu')['items'][0]
        lid = sw.decide(self.conn, primary['id'], 'uebernehmen')['lead_id']
        items = self.listing(status='neu')['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['possible_lead']['id'], lid)
        sw.review_duplicate(self.conn, items[0]['id'], 'lead_gleich')
        self.assertEqual(self.listing(status='neu')['total'], 0)
        self.assertEqual(self.listing(status='dublette')['items'][0]['duplicate_lead_id'], lid)

    def test_existing_lead_detected_with_identity_rules(self):
        lid = self.lead('Müller Maschinenbau GmbH', zip='70173', city='Stuttgart')
        self.store('gleif', [F('Mueller Maschinenbau GmbH', zip='70173', city='Stuttgart'),
                             F('Müller Maschinenbau GmbH & Co. KG', zip='70173', city='Stuttgart')])
        rows = {r['name']: r for r in self.conn.execute('SELECT * FROM discovery_candidates')}
        self.assertEqual((rows['Mueller Maschinenbau GmbH']['status'], rows['Mueller Maschinenbau GmbH']['duplicate_lead_id']), ('dublette', lid))
        self.assertEqual(rows['Müller Maschinenbau GmbH & Co. KG']['status'], 'neu')
        # Übernahme der KG ist erlaubt (früher: „bereits als Lead vorhanden“, weil die Rechtsform abgeschnitten wurde)
        res = sw.decide(self.conn, rows['Müller Maschinenbau GmbH & Co. KG']['id'], 'uebernehmen')
        self.assertNotEqual(res['lead_id'], lid)

    def test_suggested_website_is_not_used_for_matching(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm')])
        cid = self.listing(status='neu')['items'][0]['id']
        self.conn.execute("UPDATE discovery_candidates SET website='https://shared.example', website_status='wahrscheinlich' WHERE id=?", (cid,))
        self.conn.commit()
        self.ctx.pop('_cindex', None)
        self.store('osm', [F('Südwind Bau GmbH', zip='89073', city='Ulm', website='https://shared.example')])
        self.assertEqual(self.listing(status='neu')['total'], 2)

    def test_missing_websites_visible(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm'),
                             F('Südwind Bau GmbH', zip='89073', city='Ulm', website='https://suedwind.example')])
        no_web = self.listing(status='neu', website='0')['items']
        self.assertEqual([x['name'] for x in no_web], ['Nordlicht Software GmbH'])
        self.assertEqual(no_web[0]['website'], '')
        self.assertEqual(self.listing(status='neu')['counts']['ohne_website'], 1)

    def test_dedupe_cleans_legacy_data(self):
        # Bestand aus v1.16: gleiche Firma doppelt (Umlaut-Schreibweise), dazu eine echte Namensvetterin anderswo
        for name, city, zip_ in (('Müller Maschinenbau GmbH', 'Stuttgart', '70173'), ('Mueller Maschinenbau GmbH', 'Stuttgart', '70173'),
                                 ('Müller Maschinenbau GmbH', 'Hamburg', '20095'), ('Müller Maschinenbauer GmbH', 'Stuttgart', '70173')):
            self.conn.execute("""INSERT INTO discovery_candidates(run_id, sweep_id, source, name, zip, city, legal_form, status, sources_json)
                                 VALUES (?,?,?,?,?,?,?,?,?)""", (self.run, self.sid, 'osm', name, zip_, city, 'GmbH', 'neu', '[{"source": "osm", "url": ""}]'))
        self.conn.commit()
        res = sw.dedupe_candidates(self.conn)
        self.assertEqual((res['merged'], res['possible']), (1, 1))
        self.assertEqual(self.listing(status='neu')['total'], 2)
        self.assertEqual(sw.dedupe_candidates(self.conn)['merged'], 0)  # idempotent

    def test_migration_runs_dedupe(self):
        db = Path(self.tmp.name) / 'alt.sqlite3'
        with connect(db) as c:
            init_db(c)
            sid = c.execute("INSERT INTO sweeps(label, params_json) VALUES ('alt', '{}')").lastrowid
            run = sw._run_record(c, 'osm', sid, {})
            for name in ('Nordlicht Software GmbH', 'Nordlicht-Software GmbH'):
                c.execute("""INSERT INTO discovery_candidates(run_id, sweep_id, source, name, zip, city, status, sources_json)
                             VALUES (?,?,?,?,?,?,?,?)""", (run, sid, 'osm', name, '89073', 'Ulm', 'neu', '[]'))
            c.execute('PRAGMA user_version = 22')
            c.commit()
        prepare_database(db)
        with connect(db) as c:
            n = c.execute("SELECT COUNT(*) FROM discovery_candidates WHERE status='neu'").fetchone()[0]
            self.assertEqual(n, 1)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 23)


class LeadDuplicateTests(Base):
    def test_find_duplicate_uses_identity(self):
        a = self.lead('Müller Maschinenbau GmbH', website='https://mueller.example', city='Stuttgart', zip='70173',
                      register_court='Amtsgericht Stuttgart', register_number='HRB 100')
        self.assertEqual(find_duplicate(self.conn, website='https://www.mueller.example/impressum'), (a, 'domain'))
        self.assertEqual(find_duplicate(self.conn, name='x', register_court='Stuttgart', register_number='HRB100'), (a, 'register'))
        self.assertEqual(find_duplicate(self.conn, name='Mueller Maschinenbau GmbH', city='Stuttgart')[0], a)
        self.assertEqual(find_duplicate(self.conn, name='Müller Maschinenbau GmbH & Co. KG', city='Stuttgart'), (None, None))
        self.assertEqual(find_duplicate(self.conn, name='Müller Maschinenbau GmbH', city='Stuttgart', exclude_id=a), (None, None))

    def test_list_and_not_duplicate(self):
        a = self.lead('Nordlicht Software GmbH', city='Ulm')
        b = self.lead('Nordlicht-Software GmbH', city='Ulm', website='https://nordlicht.example')
        self.lead('Nordlicht Software GmbH & Co. KG', city='Ulm')
        res = du.lead_duplicates(self.conn)
        self.assertEqual(res['total'], 1)
        self.assertEqual((res['pairs'][0]['keep']['id'], res['pairs'][0]['drop']['id'], res['pairs'][0]['verdict']), (a, b, 'same'))
        du.mark_not_duplicate(self.conn, b, a)
        self.assertEqual(du.lead_duplicates(self.conn)['total'], 0)

    def test_merge_moves_everything_and_fills_gaps(self):
        from sales_tool.company_data import add_fact
        a = self.lead('Nordlicht Software GmbH', city='Ulm', note='A')
        b = self.lead('Nordlicht-Software GmbH', city='Ulm', website='https://nordlicht.example', business_phone='+49 731 0000', note='B')
        for lid in (a, b):
            self.conn.execute("INSERT INTO activities(lead_id, activity_type, detail) VALUES (?, 'notiz', ?)", (lid, f'von {lid}'))
            self.conn.execute("INSERT INTO action_dismissals(lead_id, action_key) VALUES (?, 'x')", (lid,))
        add_fact(self.conn, b, 'vat_id', 'DE123456789', 'impressum_html', 'https://nordlicht.example/impressum')
        sid = self.conn.execute("INSERT INTO sweeps(label, params_json) VALUES ('m', '{}')").lastrowid
        self.conn.execute("""INSERT INTO discovery_candidates(run_id, sweep_id, source, name, status, lead_id, sources_json)
                             VALUES (?,?,?,?,?,?,?)""", (self.run, sid, 'osm', 'Nordlicht', 'uebernommen', b, '[]'))
        self.conn.commit()
        res = du.merge_leads(self.conn, a, b)
        self.assertIsNone(self.conn.execute('SELECT 1 FROM leads WHERE id=?', (b,)).fetchone())
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (a,)).fetchone()
        self.assertEqual((lead['website'], lead['business_phone']), ('https://nordlicht.example', '+49 731 0000'))
        self.assertIn('Zusammengeführt aus', lead['note'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM company_facts WHERE lead_id=?', (a,)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute('SELECT lead_id FROM discovery_candidates WHERE sweep_id=?', (sid,)).fetchone()[0], a)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM action_dismissals WHERE lead_id IN (?,?)', (a, b)).fetchone()[0], 1)
        acts = [r[0] for r in self.conn.execute('SELECT detail FROM activities WHERE lead_id=?', (a,))]
        self.assertTrue(any('von ' + str(b) == x for x in acts) and any('zusammengeführt' in x for x in acts))
        self.assertIn('website', res['filled'])

    def test_merge_refuses_when_drop_has_invoices(self):
        a = self.lead('Nordlicht Software GmbH', city='Ulm')
        b = self.lead('Nordlicht-Software GmbH', city='Ulm')
        self.conn.execute("INSERT INTO invoices(lead_id, buyer_name) VALUES (?, 'Nordlicht')", (b,))
        self.conn.commit()
        with self.assertRaises(ValueError) as ctx:
            du.merge_leads(self.conn, a, b)
        self.assertIn('umgekehrt', str(ctx.exception))
        self.assertIsNotNone(self.conn.execute('SELECT 1 FROM leads WHERE id=?', (b,)).fetchone())
        du.merge_leads(self.conn, b, a)  # umgekehrt geht
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)

    def test_review_candidate_blocks_real_duplicate_only(self):
        self.lead('Müller Maschinenbau GmbH', city='Stuttgart', zip='70173')
        self.store('gleif', [F('Mueller Maschinenbau GmbH', city='Stuttgart', zip='70173', lei=LEI)])
        cid = self.conn.execute("SELECT id FROM discovery_candidates").fetchone()[0]
        self.conn.execute("UPDATE discovery_candidates SET status='neu', duplicate_lead_id=NULL WHERE id=?", (cid,))
        self.conn.commit()
        with self.assertRaises(ValueError):
            lf.review_candidate(self.conn, cid, 'uebernehmen')


class HttpTests(Base):
    def test_endpoints(self):
        self.store('gleif', [F('Nordlicht Software GmbH', zip='89073', city='Ulm')])
        self.store('osm', [F('Nordlicht Softwares GmbH', zip='89073', city='Ulm')])
        a = self.lead('Kesselwerk GmbH', city='Ulm')
        b = self.lead('Kessel-Werk GmbH', city='Ulm')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def call(path, method='GET', body=None):
            c = HTTPConnection('127.0.0.1', server.server_address[1], timeout=10)
            c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json'} if body is not None else {})
            r = c.getresponse()
            out = (r.status, json.loads(r.read() or b'{}'))
            c.close()
            return out
        try:
            st, lst = call('/api/sweep-candidates?status=neu')
            self.assertEqual((st, lst['total'], len(lst['items'][0]['possible_duplicates'])), (200, 1, 1))
            dup = lst['items'][0]['possible_duplicates'][0]['id']
            self.assertEqual(call(f'/api/sweep-candidates/{dup}/duplicate', 'POST', {'decision': 'quatsch'})[0], 400)
            self.assertEqual(call(f'/api/sweep-candidates/{dup}/duplicate', 'POST', {'decision': 'gleich'})[1]['status'], 'zusammengefuehrt')
            self.assertEqual(call('/api/sweep-candidates/dedupe', 'POST', {})[0], 400)
            self.assertEqual(call('/api/sweep-candidates/dedupe', 'POST', {'run': True})[0], 200)
            st, d = call('/api/leads/duplicates')
            self.assertEqual((st, d['total']), (200, 1))
            self.assertEqual(call('/api/leads/merge', 'POST', {'keep': a, 'drop': a})[0], 400)
            self.assertEqual(call('/api/leads/merge', 'POST', {'keep': a, 'drop': 9999})[0], 404)
            self.assertEqual(call('/api/leads/merge', 'POST', {'keep': a, 'drop': b})[1]['dropped'], b)
            self.assertEqual(call('/api/leads/duplicates')[1]['total'], 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
