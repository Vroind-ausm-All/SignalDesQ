"""v1.13 – Feedbackrunde: Ortsbezug, Überlastung der offenen Quellen, automatische Website-/Impressums-Übernahme,
gegliederte Aufgaben, Recherche-Sammelpunkt.

Alle Netzwerkantworten sind Attrappen mit fiktiven Firmen (keine Live-Abfragen). Die Fehlerbilder des Nutzers werden
nachgestellt: Wikidata „HTTP 429“, OpenStreetMap „502 … server is currently at capacity“.
"""
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from sales_tool import area as ar
from sales_tool import lead_finder as lf
from sales_tool import report as rp
from sales_tool import sweep as sw
from sales_tool import today as td
from sales_tool.model import connect, init_db

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402  (Modul statt Namen importieren: sonst liefe der geerbte Test doppelt)
import test_sprintC_report as tc  # noqa: E402

GLEIF_CSV = tb.GLEIF_CSV


class SourceErrorTests(unittest.TestCase):
    def test_retryable_flags(self):
        self.assertTrue(lf.SourceError('Quelle antwortet mit HTTP 502: server is currently at capacity').retryable)
        self.assertTrue(lf.SourceError('Quelle antwortet mit HTTP 504: Gateway Timeout').retryable)
        self.assertTrue(lf.SourceError('Quelle nicht erreichbar (The read operation timed out).').retryable)
        self.assertFalse(lf.SourceError('Quelle antwortet mit HTTP 400: Filter').retryable, 'falsche Anfrage – Wiederholen bringt nichts')
        self.assertFalse(lf.SourceError('HTTP 503', retryable=False).retryable)

    def test_http_429_reads_retry_after(self):
        err = urllib.error.HTTPError('https://query.wikidata.org/sparql', 429, 'Too Many Requests', {'Retry-After': '7'}, io.BytesIO(b''))
        with mock.patch('urllib.request.urlopen', side_effect=err):
            with self.assertRaises(lf.SourceError) as ctx:
                lf._http('https://query.wikidata.org/sparql', 'ua')
        self.assertIn('HTTP 429', str(ctx.exception))
        self.assertEqual(ctx.exception.retry_after, 7)
        self.assertTrue(ctx.exception.retryable)


class OverloadTests(tb.SweepBase):
    def setUp(self):
        super().setUp()
        self.sleeps = []
        lf.SLEEP = self.sleeps.append

    def test_sweep_waits_and_retries_overloaded_source(self):
        orig, calls = sw.SOURCE_RUNNERS['ted'], []

        def flaky(*a):
            calls.append(1)
            if len(calls) == 1:
                raise lf.SourceError('Die Quelle meldet zu viele Anfragen (HTTP 429).', retry_after=5)
            return orig(*a)
        with mock.patch.dict(sw.SOURCE_RUNNERS, {'ted': flaky}):
            d = self.run_sweep(sources=['ted'])
        self.assertEqual(d['progress']['ted']['status'], 'fertig')
        self.assertIn('2. Versuch', d['progress']['ted']['detail'])
        self.assertIn(20, self.sleeps, 'mindestens 20 s Pause (Retry-After 5 s ist kürzer)')
        self.assertEqual(d['status'], 'fertig')

    def test_retry_after_is_capped(self):
        orig, calls = sw.SOURCE_RUNNERS['ted'], []

        def flaky(*a):
            calls.append(1)
            if len(calls) == 1:
                raise lf.SourceError('HTTP 429', retry_after=900)
            return orig(*a)
        with mock.patch.dict(sw.SOURCE_RUNNERS, {'ted': flaky}):
            self.run_sweep(sources=['ted'])
        self.assertIn(120, self.sleeps, 'höchstens 2 Minuten warten')

    def test_failed_source_can_be_retried_later(self):
        self.net.fail.add('ted')  # HTTP 503 – überlastet
        d = self.run_sweep(sources=['gleif', 'ted'])
        self.assertEqual(d['progress']['ted']['status'], 'fehler')
        self.assertIn('erneut abfragen', d['progress']['ted']['error'])
        self.assertEqual([s for s in self.sleeps if s >= 20], [20, 60], 'zwei Wiederholungen mit wachsender Pause')
        self.assertEqual(d['progress']['gleif']['status'], 'fertig', 'andere Quellen laufen weiter')
        gleif_new = d['progress']['gleif']['new']
        self.net.fail.clear()
        self.assertEqual(sw.retry_sweep(self.conn, d['id'], self.db, start=False), {'retrying': ['ted']})
        sw.run_sweep(self.db, d['id'], ['ted'])
        d2 = sw.sweep_detail(self.conn, d['id'])
        self.assertEqual((d2['progress']['ted']['status'], d2['status']), ('fertig', 'fertig'))
        self.assertEqual(d2['progress']['gleif']['new'], gleif_new, 'erfolgreiche Quelle wird nicht erneut abgefragt')
        with self.assertRaises(ValueError):
            sw.retry_sweep(self.conn, d['id'], self.db, start=False)
        with self.assertRaises(LookupError):
            sw.retry_sweep(self.conn, 9999, self.db, start=False)

    def test_osm_partial_success_in_chunks(self):
        orig, queries = lf.overpass, []

        def part(query, ua):
            queries.append(query)
            if len(queries) == 2:
                raise lf.SourceError('Quelle antwortet mit HTTP 502: The server is currently at capacity')
            return orig(query, ua) if len(queries) == 1 else {'elements': []}
        with mock.patch.object(lf, 'overpass', side_effect=part):
            d = self.run_sweep(sources=['osm'])
        self.assertGreaterEqual(len(queries), 2, 'Abfrage in Teile zerlegt')
        self.assertEqual(d['progress']['osm']['status'], 'fertig')
        self.assertIn('Teilabfragen überlastet', d['progress']['osm']['detail'])
        self.assertIn('Elektro Sommer GmbH', [c['name'] for c in self.cands()])

    def test_osm_all_chunks_fail(self):
        with mock.patch.object(lf, 'overpass', side_effect=lf.SourceError('Quelle antwortet mit HTTP 504: Gateway Timeout')):
            d = self.run_sweep(sources=['osm'])
        self.assertEqual(d['progress']['osm']['status'], 'fehler')


class LocationTests(tb.SweepBase):
    def test_radius_zero_is_only_the_place(self):
        a = ar.resolve(self.conn, '70173', 0)
        self.assertEqual([p['name'] for p in a['places']], ['Stuttgart'])
        self.assertEqual(a['source'], 'nur dieser Ort')
        self.assertFalse([c for c in self.net.calls if 'wikidata' in c], 'keine Umkreissuche')
        self.assertEqual(sw.validate_params({'place': 'Stuttgart', 'radius_km': 0})['radius_km'], 0)

    def test_review_filters_city_distance_ted(self):
        self.run_sweep()
        all_ = self.cands()
        self.assertTrue(any(c['source'] == 'ted' for c in all_))
        self.assertFalse([c for c in self.cands(no_ted='1') if c['source'] == 'ted'], 'Ausschreibungen ausblendbar')
        near = self.cands(max_km='5')
        self.assertTrue(near)
        self.assertTrue(all(c['distance_km'] is not None and c['distance_km'] <= 5 for c in near))
        self.assertNotIn('Neckar Präzisionsteile GmbH', [c['name'] for c in near], 'Esslingen liegt ~10 km entfernt')
        st = self.cands(city='stuttgart')
        self.assertTrue(st)
        self.assertTrue(all(c['city'].casefold() == 'stuttgart' for c in st), 'nur Firmen mit Sitz im Ort')
        res = sw.candidates(self.conn, {'status': ['alle'], 'city': ['Stuttgart']})
        self.assertIn('Esslingen am Neckar', [x['city'] for x in res['cities']], 'Ortsliste bleibt vollständig, auch wenn ein Ort gewählt ist')
        with self.assertRaises(ValueError):
            sw.candidates(self.conn, {'max_km': ['weit']})

    def test_websites_searched_automatically_after_sweep(self):
        d = self.run_sweep(sources=['gleif', 'ted'])
        self.assertGreaterEqual(d['progress']['_web']['queued'], 1)
        cs = {c['name']: c for c in self.cands()}
        self.assertEqual(cs['Reith Spezialkabel GmbH']['website_status'], 'wartet', 'ohne Website → Suche eingeplant')
        self.assertNotEqual(cs['Stadtwerke Beispielstadt']['website_status'], 'wartet', 'keine Website-Suche für Ausschreibungen')
        self.assertNotEqual(cs['Neckar Präzisionsteile GmbH']['website_status'], 'wartet', 'Website schon bekannt')

    def test_auto_websites_can_be_switched_off(self):
        d = self.run_sweep(sources=['gleif'], find_websites=False)
        self.assertNotIn('_web', d['progress'])
        self.assertFalse([c for c in self.cands() if c['website_status'] == 'wartet'])


class ImprintAutoApplyTests(tb.SweepBase):
    def prepare(self, status):
        sw.import_file(self.conn, GLEIF_CSV, {'plz': '70'})
        c = next(x for x in self.cands() if x['name'] == 'Reith Spezialkabel GmbH')
        imp = {'imprint_url': 'https://reith-spezialkabel.example/impressum', 'source_type': 'impressum_html',
               'fields': {'legal_name': {'value': 'Reith Spezialkabel GmbH & Co. KG'}, 'register_number': {'value': 'HRB 14671'},
                          'register_court': {'value': 'Amtsgericht Stuttgart'}, 'vat_id': {'value': 'DE999999999'},
                          'business_phone': {'value': '+49 711 0000000'}, 'business_email': {'value': 'info@reith-spezialkabel.example'}}}
        self.conn.execute("UPDATE discovery_candidates SET website='https://reith-spezialkabel.example', website_status=?, imprint_json=? WHERE id=?",
                          (status, json.dumps(imp), c['id']))
        self.conn.commit()
        return c['id']

    def test_confirmed_imprint_fills_empty_fields_only(self):
        res = sw.decide(self.conn, self.prepare('belegt'), 'uebernehmen')
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertEqual(lead['legal_name'], 'Reith Spezialkabel GmbH', 'vorhandener Wert wird nicht überschrieben')
        self.assertEqual((lead['vat_id'], lead['register_court'], lead['business_phone']), ('DE999999999', 'Amtsgericht Stuttgart', '+49 711 0000000'))
        self.assertEqual(lead['imprint_url'], 'https://reith-spezialkabel.example/impressum')
        self.assertIn('vat_id', res['auto_applied'])
        self.assertNotIn('legal_name', res['auto_applied'])
        facts = {r['field']: r['status'] for r in self.conn.execute('SELECT field, status FROM company_facts WHERE lead_id=?', (res['lead_id'],))}
        self.assertEqual(facts['vat_id'], 'bestaetigt')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM decision_contacts WHERE lead_id=?', (res['lead_id'],)).fetchone()[0], 0)
        self.assertTrue(self.conn.execute("SELECT 1 FROM activities WHERE lead_id=? AND detail LIKE '%automatisch übernommen%'", (res['lead_id'],)).fetchone())
        self.assertEqual((lead['permission'], lead['next_step'], lead['next_date']), ('unbekannt', 'Firmen-Bericht erstellen', ''),
                         'keine Kontakterlaubnis, kein Termin-Druck durch Recherche')

    def test_probable_imprint_stays_unconfirmed(self):
        res = sw.decide(self.conn, self.prepare('wahrscheinlich'), 'uebernehmen')
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertEqual((lead['vat_id'], lead['register_court']), ('', ''), 'nur „belegt“ füllt Felder automatisch')
        self.assertEqual(res['auto_applied'], [])
        facts = {r['field']: r['status'] for r in self.conn.execute('SELECT field, status FROM company_facts WHERE lead_id=?', (res['lead_id'],))}
        self.assertEqual(facts['vat_id'], 'ungeprueft', 'als Beleg zur Prüfung gespeichert')

    def test_ted_takeover_keeps_deadline(self):
        self.run_sweep(sources=['ted'])
        c = next(x for x in self.cands() if x['source'] == 'ted')
        res = sw.decide(self.conn, c['id'], 'uebernehmen')
        lead = self.conn.execute('SELECT next_step, next_date FROM leads WHERE id=?', (res['lead_id'],)).fetchone()
        self.assertIn('Vergabe', lead['next_step'])
        self.assertEqual(lead['next_date'], (dt.date.today() + dt.timedelta(days=2)).isoformat())


class TaskOverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / 't.sqlite3')
        init_db(self.conn)
        self.yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, company, stage='recherche', next_step='', next_date='', website=''):
        cur = self.conn.execute('INSERT INTO leads(company, stage, next_step, next_date, website, industry) VALUES (?,?,?,?,?,?)',
                                (company, stage, next_step, next_date, website, 'Sonstige'))
        self.conn.commit()
        return cur.lastrowid

    def task(self, title, lead_id=None, due=''):
        self.conn.execute('INSERT INTO tasks(title, lead_id, due_date) VALUES (?,?,?)', (title, lead_id, due))
        self.conn.commit()

    def test_grouped_and_research_summarised(self):
        a = self.lead('Alpha Fiktiv GmbH', next_step='Website prüfen (URL-Recherche) und Anlass belegen', next_date=self.yesterday, website='https://alpha.example')
        b = self.lead('Beta Fiktiv GmbH', next_step='Firmen-Bericht erstellen')
        self.lead('Gamma Fiktiv GmbH')  # Recherche-Phase ohne Schritt
        c = self.lead('Delta Fiktiv GmbH', stage='kontakt', next_step='Kontakt aufnehmen per Telefon')
        d = self.lead('Epsilon Fiktiv GmbH', stage='termin', next_step='Termin vorbereiten')
        self.task('Angebot nach Gespräch überarbeiten', d)
        self.task('Steuerberater Unterlagen schicken', None, self.yesterday)
        self.task('Impressum prüfen', b)
        ov = td.task_overview(self.conn)
        g = {x['key']: x for x in ov['groups']}
        self.assertEqual(list(g), ['recherche', 'kontakt', 'termine', 'angebot', 'sonstiges'])
        firms = {f['company']: f for f in g['recherche']['firms']}
        self.assertEqual(set(firms), {'Alpha Fiktiv GmbH', 'Beta Fiktiv GmbH', 'Gamma Fiktiv GmbH'}, 'eine Zeile je Firma')
        self.assertEqual(len(firms['Beta Fiktiv GmbH']['steps']), 2, 'Schritt + Aufgabe derselben Firma zusammengefasst')
        self.assertTrue(firms['Alpha Fiktiv GmbH']['website'])
        self.assertEqual(g['recherche']['count'], 3)
        self.assertEqual([i['lead_id'] for i in g['kontakt']['items']], [c])
        self.assertEqual([i['title'] for i in g['termine']['items']], ['Termin vorbereiten'])
        self.assertEqual([i['title'] for i in g['angebot']['items']], ['Angebot nach Gespräch überarbeiten'])
        self.assertEqual(g['sonstiges']['overdue'], 1)
        self.assertEqual(ov['research_without_report'], 1, 'nur Alpha hat eine Website für den Bericht')
        self.assertNotIn(a, [i['lead_id'] for grp in ov['groups'] for i in grp['items']], 'Recherche-Schritte nicht doppelt')

    def test_wiedervorlage_aggregates_research(self):
        for n in ('Eins', 'Zwei', 'Drei'):
            self.lead(f'{n} Fiktiv GmbH', next_step='Website prüfen (URL-Recherche)', next_date=self.yesterday)
        self.lead('Vier Fiktiv GmbH', stage='kontakt', next_step='Rückruf vereinbaren', next_date=self.yesterday)
        items = td.wiedervorlage(self.conn)
        kinds = [i['kind'] for i in items]
        self.assertEqual(kinds.count('recherche'), 1, 'ein Sammelpunkt statt drei Einzelzeilen')
        r = next(i for i in items if i['kind'] == 'recherche')
        self.assertTrue(r['title'].startswith('3 Firma'))
        self.assertEqual(r['view'], 'tasks')
        self.assertIn('Rückruf vereinbaren', [i['title'] for i in items])

    def test_cleanup_after_report(self):
        a = self.lead('Alpha Fiktiv GmbH', next_step='Website prüfen (URL-Recherche)', next_date=self.yesterday)
        b = self.lead('Beta Fiktiv GmbH', next_step='Website prüfen (URL-Recherche)', next_date=self.yesterday)
        self.conn.execute("INSERT INTO company_reports(lead_id, status, steps_json) VALUES (?, 'fertig', '{}')", (a,))
        self.conn.commit()
        self.assertEqual(td.cleanup_research_steps(self.conn), {'updated': 1})
        rows = {r['id']: r for r in self.conn.execute('SELECT id, next_step, next_date FROM leads')}
        self.assertEqual((rows[a]['next_step'], rows[a]['next_date']), ('Kontaktweg klären (Firmen-Bericht liegt vor)', ''))
        self.assertEqual(rows[b]['next_step'], 'Website prüfen (URL-Recherche)', 'ohne Bericht unverändert')


class ReportNextStepTests(tc.ReportBase):
    def test_report_closes_research_step(self):
        lid = self.lead(next_step='Website prüfen (URL-Recherche)', next_date='2026-01-01')
        other = self.lead(company='Zweitfirma', next_step='Angebot nachfassen', next_date='2026-01-01')
        rp.create_reports(self.conn, {'lead_ids': [lid, other]}, self.db, start=False)
        rp._worker(self.db)
        rows = {r['id']: r for r in self.conn.execute('SELECT id, next_step, next_date FROM leads')}
        self.assertEqual((rows[lid]['next_step'], rows[lid]['next_date']), ('Kontaktweg klären (Firmen-Bericht liegt vor)', ''))
        self.assertEqual((rows[other]['next_step'], rows[other]['next_date']), ('Angebot nachfassen', '2026-01-01'), 'fremde Schritte bleiben')


class V113HttpTests(tb.SweepHttpTests):
    def test_endpoints(self):  # ersetzt den geerbten Test
        status, ov = self.call('/api/tasks/overview')
        self.assertEqual(status, 200)
        self.assertEqual([g['key'] for g in ov['groups']][0], 'recherche')
        self.assertEqual(self.call('/api/tasks/research-cleanup', 'POST', {}), (200, {'updated': 0}))
        status, s = self.call('/api/sweeps', 'POST', {'place': 'Stuttgart', 'radius_km': 0, 'sources': ['gleif'], 'find_websites': False})
        self.assertEqual(status, 202)
        sw._THREADS[s['id']].join(30)
        self.assertEqual(self.call(f"/api/sweeps/{s['id']}/retry", 'POST', {})[0], 400, 'nichts fehlgeschlagen')
        self.assertEqual(self.call('/api/sweeps/9999/retry', 'POST', {})[0], 404)
        status, lst = self.call('/api/sweep-candidates?status=alle&city=Stuttgart&max_km=5&no_ted=1')
        self.assertEqual(status, 200)
        self.assertIn('cities', lst)
        self.assertEqual(self.call('/api/sweeps', 'POST', {'place': 'Stuttgart', 'radius_km': 0, 'sources': ['gleif'], 'find_websites': 'ja'})[0], 400)
        for path in ('/tasks.js', '/pipeline.js'):
            c = __import__('http.client').client.HTTPConnection('127.0.0.1', self.port, timeout=10)
            c.request('GET', path)
            r = c.getresponse()
            self.assertEqual(r.status, 200, path)
            r.read()
            c.close()


if __name__ == '__main__':
    unittest.main()
