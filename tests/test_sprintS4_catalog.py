"""Masterplan 2.0 – Sprint 4: großer Firmenkatalog (GLEIF Golden Copy/Delta) per Streaming.

Abnahme laut Plan: großer synthetischer CSV-Test ohne vollständiges Laden in den Arbeitsspeicher; identische LEIs werden
nicht dupliziert. Dazu: Delta-Semantik, Importprotokoll mit Lizenz, Übernahme in die Sichtung mit Dubletten-Abgleich,
GLEIF-Ersatz bei API-Ausfall. Alle Firmen und LEIs sind fiktiv (tools/make_gleif_sample.py), keine Netzabfragen.
"""
import json
import sys
import tempfile
import threading
import tracemalloc
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).parent))
import make_gleif_sample as gs  # noqa: E402
import test_sprintB_sweep as tb  # noqa: E402

from sales_tool import sweep as sw  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import catalog as cat  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from tmpclean import cleanup_tmp  # noqa: E402 – Worker beenden, dann löschen (Windows)


class CatalogBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / 'k.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.cat = cat.catalog_path(self.db)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)


class StreamingImportTests(CatalogBase):
    def test_large_csv_streams_with_bounded_memory(self):
        src = gs.write(self.dir / 'golden.csv', 45_000)
        size = src.stat().st_size
        self.assertGreater(size, 9_000_000)
        tracemalloc.start()
        try:
            res = cat.import_file(self.cat, src, 'golden')
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(res['status'], 'fertig', res['error'])
        self.assertEqual((res['rows'], res['inserted'], res['skipped']['ausland']), (45_000, 43_200, 1_800))
        self.assertLess(peak, 6_000_000, f'Spitze {peak / 1e6:.1f} MB – Datei {size / 1e6:.1f} MB darf nicht komplett geladen werden')
        self.assertLess(peak, size * 0.6)
        st = cat.status(self.cat)
        self.assertEqual((st['entities'], st['active']), (43_200, 43_200))
        self.assertEqual(st['last_import']['license'], cat.LICENSE)

    def test_zip_and_identical_leis_not_duplicated(self):
        cat.import_file(self.cat, gs.write(self.dir / 'g.zip', 3000), 'golden')
        again = cat.import_file(self.cat, gs.write(self.dir / 'g.csv', 3000), 'golden')
        self.assertEqual((again['inserted'], again['updated'], again['unchanged']), (0, 0, 2880))
        c = cat.connect_catalog(self.cat)
        self.assertEqual(c.execute('SELECT COUNT(*), COUNT(DISTINCT lei) FROM entities').fetchone()[:], (2880, 2880))
        c.close()

    def test_delta_and_golden_semantics(self):
        cat.import_file(self.cat, gs.write(self.dir / 'g.csv', 2000), 'golden')
        delta = gs.write(self.dir / 'd.csv', 2001, changed={5: 'Neuer Name Präzision GmbH'}, inactive={7}, skip=set(range(8, 2000)))
        res = cat.import_file(self.cat, delta, 'delta')
        # Zeilen 0–7 + 2000: 0–4 und 6 unverändert, 5 geändert, 7 inaktiv, 2000 neu
        self.assertEqual((res['inserted'], res['updated'], res['unchanged'], res['deactivated']), (1, 2, 6, 1))
        self.assertEqual(cat.search(self.cat, 'Neuer Name Praezision')['items'][0]['lei'], gs.lei(5))
        self.assertEqual(cat.search(self.cat, 'Neuer Name')['total'], 1)
        self.assertEqual(cat.status(self.cat)['active'], 1920 - 1 + 1)
        # Vollbestand ohne die Zeilen 10–19 → diese gelten als nicht mehr aktiv (nicht gelöscht)
        res = cat.import_file(self.cat, gs.write(self.dir / 'g2.csv', 2001, skip=set(range(10, 20))), 'golden')
        self.assertEqual(res['deactivated'], 10 + 0)
        st = cat.status(self.cat)
        self.assertEqual(st['entities'], 1921)

    def test_search_filters(self):
        cat.import_file(self.cat, gs.write(self.dir / 'g.csv', 3000), 'golden')
        r = cat.search(self.cat, 'Mueller', zip_prefix='70')
        self.assertTrue(r['items'] and all(i['zip'].startswith('70') and 'Müller' in i['name'] for i in r['items']))
        self.assertEqual(cat.search(self.cat, city='esslingen')['total'], cat.search(self.cat, zip_prefix='73728')['total'])
        self.assertTrue(all(i['city'] == 'Stuttgart' for i in cat.search(self.cat, city='STUTTGART', limit=200)['items']))
        with self.assertRaises(ValueError):
            cat.search(self.cat)
        with self.assertRaises(ValueError):
            cat.search(self.cat, zip_prefix='7x')

    def test_bad_file_is_logged_not_crashing(self):
        bad = self.dir / 'x.csv'
        bad.write_text('Firma;Ort\nA;B\n', encoding='utf-8')
        res = cat.import_file(self.cat, bad, 'golden')
        self.assertEqual(res['status'], 'fehler')
        self.assertIn('Keine GLEIF-Datei', res['error'])
        self.assertEqual(cat.status(self.cat)['imports'][0]['status'], 'fehler')

    def test_cancel_keeps_progress_and_resume_is_idempotent(self):
        src = gs.write(self.dir / 'g.csv', 6000)
        res = cat.import_file(self.cat, src, 'golden', cancelled=lambda: True)
        self.assertEqual(res['status'], 'abgebrochen')
        self.assertEqual(cat.status(self.cat)['entities'], cat.BATCH)
        res = cat.import_file(self.cat, src, 'golden')
        self.assertEqual((res['inserted'], res['unchanged']), (5760 - cat.BATCH, cat.BATCH))


class TakeOverTests(CatalogBase):
    def test_take_over_goes_through_dedupe(self):
        cat.import_file(self.cat, gs.write(self.dir / 'g.csv', 300), 'golden')
        leis = [gs.lei(i) for i in range(0, 30)]
        first = cat.take_over(self.conn, self.db, leis)
        self.assertEqual(first['new'] + first['filtered'], 30 - 1)  # Nr. 24 liegt in Österreich → nicht im DE-Katalog
        second = cat.take_over(self.conn, self.db, leis)
        self.assertEqual(second['new'], 0)
        n, d = self.conn.execute("SELECT COUNT(*), COUNT(DISTINCT lei) FROM discovery_candidates WHERE status<>'zusammengefuehrt'").fetchone()
        self.assertEqual(n, d)
        known = cat.known_leis(self.conn, [gs.lei(0), gs.lei(299)])
        self.assertIn(gs.lei(0), known)
        self.assertNotIn(gs.lei(299), known)
        with self.assertRaises(ValueError):
            cat.take_over(self.conn, self.db, ['kaputt'])


class GleifFallbackTests(tb.SweepBase):
    def test_sweep_uses_catalog_when_api_down(self):
        c = cat.connect_catalog(cat.catalog_path(self.db))
        c.execute("""INSERT INTO entities(lei, name, name_norm, legal_form, zip, city, city_norm, country, register_id, active)
                     VALUES (?, 'Katalogwerk Präzision GmbH', 'katalogwerk praezision', 'GmbH', '70173', 'Stuttgart', 'stuttgart', 'DE', 'HRB 4711', 1)""",
                  (tb.LEI_A,))
        c.commit()
        c.close()
        self.net.fail.add('gleif')
        detail = self.run_sweep(sources=['gleif'])
        g = detail['progress']['gleif']
        self.assertEqual(g['status'], 'fertig', g)
        self.assertIn('lokalen GLEIF-Katalog', g['detail'])
        names = [x['name'] for x in self.cands()]
        self.assertIn('Katalogwerk Präzision GmbH', names)

    def test_without_catalog_error_stays_visible(self):
        self.net.fail.add('gleif')
        detail = self.run_sweep(sources=['gleif'])
        self.assertEqual(detail['progress']['gleif']['status'], 'fehler')


class HttpTests(CatalogBase):
    def test_upload_job_search_takeover(self):
        src = gs.write(self.dir / 'g.zip', 1500)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]

        def call(path, method='GET', body=None, raw=None, ctype='application/json'):
            c = HTTPConnection('127.0.0.1', port, timeout=30)
            data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
            c.request(method, path, body=data, headers={'Content-Type': ctype} if data is not None else {})
            r = c.getresponse()
            out = (r.status, json.loads(r.read() or b'{}'))
            c.close()
            return out
        try:
            self.assertFalse(call('/api/catalog')[1]['exists'])
            self.assertEqual(call('/api/catalog/upload?kind=quatsch', 'POST', raw=b'x', ctype='text/csv')[0], 400)
            self.assertEqual(call('/api/catalog/upload', 'POST', raw=b'x', ctype='image/png')[0], 400)
            st, r = call('/api/catalog/upload?filename=golden.zip&kind=golden', 'POST', raw=src.read_bytes(), ctype='application/zip')
            self.assertEqual(st, 202, r)
            jobs.wait_idle(self.db, timeout=60)
            info = call('/api/catalog')[1]
            self.assertEqual((info['entities'], info['jobs'][0]['status']), (1440, 'done'))
            self.assertFalse(any(cat.upload_dir(self.db).iterdir()), 'hochgeladene Datei wird nach dem Import gelöscht')
            st, res = call('/api/catalog/search?zip=70')
            self.assertEqual(st, 200)
            leis = [i['lei'] for i in res['items'][:5]]
            self.assertEqual(call('/api/catalog/take-over', 'POST', {'leis': leis})[1]['new'], 5)
            res = call('/api/catalog/search?zip=70')[1]
            self.assertEqual(sum(1 for i in res['items'] if i['known']), 5)
            self.assertEqual(call('/api/catalog/search')[0], 400)
        finally:
            server.shutdown()
            server.server_close()
            jobs.wait_idle(self.db, timeout=10)


if __name__ == '__main__':
    unittest.main()
