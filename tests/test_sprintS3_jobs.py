"""Masterplan 2.0 – Sprint 3: persistente Recherche-Aufträge.

Abnahme laut Plan: App-Neustart während eines Auftrags ohne Datenverlust; mehrfacher Start erzeugt keine doppelten
Fakten/Leads; ein 403/Timeout bricht die Sitzung nicht ab. Fiktive Daten, keine echten Netzabfragen.
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402
import test_sprintC_report as tc  # noqa: E402

from sales_tool import report as rp  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402
from sales_tool.website_analyzer import CrawlError  # noqa: E402


class JobBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'j.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self.calls = []
        self.now = [1_000_000.0]
        self.p = mock.patch.object(jobs, 'CLOCK', lambda: self.now[0])
        self.p.start()
        jobs.HANDLERS['test'] = self.handler

    def tearDown(self):
        self.p.stop()
        jobs.HANDLERS.pop('test', None)
        jobs.HANDLERS.pop('test:cancel', None)
        self.conn.close()
        self.tmp.cleanup()

    def handler(self, db_path, payload, ctx):
        self.calls.append(payload['n'])
        if payload.get('fail') == 'retry':
            raise jobs.Retry('Quelle überlastet (HTTP 503)', delay=30)
        if payload.get('fail') == 'hard':
            raise CrawlError('HTTP 403')
        return {'ok': payload['n']}

    def submit(self, tasks, **kw):
        return jobs.submit(self.conn, 'test', 'Testauftrag', [{'key': f't{t["n"]}', 'kind': 'test', 'payload': t, 'domain': t.get('d', '')}
                                                               for t in tasks], db_path=self.db, start=False, **kw)[0]


class LifecycleTests(JobBase):
    def test_run_counts_and_states(self):
        job = self.submit([{'n': 1}, {'n': 2}, {'n': 3}])
        self.assertEqual((job['status'], job['total']), ('queued', 3))
        self.assertEqual(jobs.run_until_idle(self.db), 3)
        v = jobs.job_view(self.conn, job['id'])
        self.assertEqual((v['status'], v['done'], v['failed']), ('done', 3, 0))
        self.assertTrue(v['started_at'] and v['finished_at'])
        self.assertEqual(json.loads(self.conn.execute('SELECT result_json FROM research_tasks WHERE task_key=?', ('t2',)).fetchone()[0]), {'ok': 2})

    def test_idempotent_key(self):
        a, created_a = jobs.submit(self.conn, 'test', 'A', [{'key': 'x', 'kind': 'test', 'payload': {'n': 1}}], job_key='k1', start=False)
        b, created_b = jobs.submit(self.conn, 'test', 'B', [{'key': 'y', 'kind': 'test', 'payload': {'n': 2}}], job_key='k1', start=False)
        self.assertEqual((a['id'], created_a, created_b), (b['id'], True, False), 'Doppelklick → derselbe Auftrag')
        jobs.run_until_idle(self.db)
        c, created_c = jobs.submit(self.conn, 'test', 'C', [{'key': 'z', 'kind': 'test', 'payload': {'n': 3}}], job_key='k1', start=False)
        self.assertTrue(created_c, 'nach Abschluss darf derselbe Schlüssel neu starten')
        self.assertEqual(jobs.add_tasks(self.conn, c['id'], [{'key': 'z', 'kind': 'test', 'payload': {'n': 3}}]), 0, 'Schritt-Schlüssel eindeutig')

    def test_pause_resume_cancel(self):
        jobs.HANDLERS['test:cancel'] = lambda conn, payload: self.calls.append(('abgebrochen', payload['n']))
        job = self.submit([{'n': 1}, {'n': 2}])
        jobs.pause(self.conn, job['id'])
        self.assertEqual(jobs.run_until_idle(self.db), 0, 'pausiert → nichts läuft')
        jobs.resume(self.conn, job['id'])
        self.assertEqual(jobs.run_one(self.db), True)
        jobs.cancel(self.conn, job['id'])
        v = jobs.job_view(self.conn, job['id'])
        self.assertEqual((v['status'], [t['status'] for t in v['tasks']]), ('cancelled', ['done', 'cancelled']))
        self.assertIn(('abgebrochen', 2), self.calls, 'fachliches Aufräumen beim Abbruch')
        with self.assertRaises(ValueError):
            jobs.pause(self.conn, job['id'])
        with self.assertRaises(LookupError):
            jobs.resume(self.conn, 9999)

    def test_retry_backoff_and_partial(self):
        job = self.submit([{'n': 1, 'fail': 'retry'}, {'n': 2}, {'n': 3, 'fail': 'hard'}])
        jobs.run_until_idle(self.db)
        v = jobs.job_view(self.conn, job['id'])
        t1 = next(t for t in v['tasks'] if t['task_key'] == 't1')
        self.assertEqual((t1['status'], t1['attempts'], t1['retry_in']), ('queued', 1, 30), 'Wartezeit statt sofort erneut')
        self.assertEqual(next(t for t in v['tasks'] if t['task_key'] == 't3')['status'], 'failed', '403 = nur dieser Schritt')
        self.assertEqual(v['status'], 'running', 'Auftrag läuft weiter')
        for _ in range(3):
            self.now[0] += 31
            jobs.run_until_idle(self.db)
        v = jobs.job_view(self.conn, job['id'])
        t1 = next(t for t in v['tasks'] if t['task_key'] == 't1')
        self.assertEqual((t1['status'], t1['attempts'], len(t1['errors'])), ('failed', 3, 3))
        self.assertEqual((v['status'], v['done'], v['failed']), ('partial', 1, 2))
        jobs.HANDLERS['test'] = lambda db, payload, ctx: {'ok': True}
        jobs.retry_failed(self.conn, job['id'])
        jobs.run_until_idle(self.db)
        self.assertEqual(jobs.job_view(self.conn, job['id'])['status'], 'done', 'Fehlgeschlagene erneut → fertig')

    def test_one_task_per_domain(self):
        self.submit([{'n': 1, 'd': 'firma-a.example'}, {'n': 2, 'd': 'firma-a.example'}, {'n': 3, 'd': 'firma-b.example'}])
        first = jobs.claim(self.conn)
        self.assertEqual(first['domain'], 'firma-a.example')
        second = jobs.claim(self.conn)
        self.assertEqual(second['domain'], 'firma-b.example', 'gleiche Domain wartet, andere darf')
        self.assertIsNone(jobs.claim(self.conn))
        self.now[0] += jobs.LEASE_SECONDS + 1
        self.assertEqual(jobs.claim(self.conn)['domain'], 'firma-a.example', 'abgelaufene Reservierung blockiert nicht mehr')

    def test_restart_recovery(self):
        job = self.submit([{'n': 1}, {'n': 2}])
        crashed = jobs.claim(self.conn)  # Worker stirbt mitten im Schritt
        self.assertEqual(crashed['status'], 'running')
        self.assertEqual(jobs.recover(self.conn), 1)
        row = self.conn.execute('SELECT status, note FROM research_tasks WHERE id=?', (crashed['id'],)).fetchone()
        self.assertEqual((row['status'], row['note']), ('queued', 'nach Neustart erneut eingereiht'))
        jobs.run_until_idle(self.db)
        self.assertEqual(jobs.job_view(self.conn, job['id'])['status'], 'done')
        self.assertEqual(sorted(self.calls), [1, 2])

    def test_real_threads_respect_limits(self):
        self.p.stop()
        active, peak, lock = {}, {'all': 0, 'dom': 0}, threading.Lock()

        def slow(db, payload, ctx):
            with lock:
                active[payload['n']] = payload['d']
                peak['all'] = max(peak['all'], len(active))
                peak['dom'] = max(peak['dom'], max(list(active.values()).count(d) for d in active.values()))
            time.sleep(0.15)
            with lock:
                active.pop(payload['n'])
            return {}
        jobs.HANDLERS['test'] = slow
        job = self.submit([{'n': i, 'd': f'firma-{i % 3}.example'} for i in range(9)])
        jobs.ensure_workers(self.db)
        self.assertTrue(jobs.wait_idle(self.db, 20))
        self.p.start()
        self.assertEqual(jobs.job_view(self.conn, job['id'])['done'], 9)
        self.assertLessEqual(peak['all'], jobs.MAX_WORKERS)
        self.assertEqual(peak['dom'], 1, 'nie zwei Abrufe derselben Domain gleichzeitig')


class ReportJobTests(tc.ReportBase):
    def facts(self):
        return self.conn.execute('SELECT COUNT(*) FROM company_facts').fetchone()[0]

    def test_retry_keeps_successful_steps_and_recomputes_recommendations(self):
        lid = self.lead()
        result = rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
        original = rp.RUNNERS['signale']
        with mock.patch.dict(rp.RUNNERS, {'signale': mock.Mock(side_effect=CrawlError('HTTP 403'))}):
            rp._worker(self.db)
        audit_count = self.conn.execute('SELECT COUNT(*) FROM website_audits').fetchone()[0]
        scan_count = self.conn.execute('SELECT COUNT(*) FROM quick_scans').fetchone()[0]
        self.assertEqual(jobs.job_view(self.conn, result['job_id'])['status'], 'failed')
        jobs.retry_failed(self.conn, result['job_id'])
        with mock.patch.dict(rp.RUNNERS, {'signale': original}):
            rp._worker(self.db)
        report = rp.report_view(self.conn, lead_id=lid)['report']
        self.assertEqual(report['steps']['signale']['status'], 'fertig')
        self.assertEqual(report['steps']['verknuepfen']['status'], 'fertig')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM website_audits').fetchone()[0], audit_count)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM quick_scans').fetchone()[0], scan_count)

    def test_restart_mid_report_no_loss_no_duplicates(self):
        ids = [self.lead(), self.lead(company='Zweite Firma', website='https://zweite-beispiel.example')]
        r = rp.create_reports(self.conn, {'lead_ids': ids}, self.db, start=False)
        self.assertTrue(r['job_id'])
        task = jobs.claim(self.conn, kinds=('report',))  # Schritt reserviert …
        self.conn.execute("UPDATE company_reports SET status='running' WHERE id=?", (json.loads(task['payload_json'])['report_id'],))
        self.conn.commit()  # … und dann „stürzt die App ab“
        jobs.recover(self.conn)
        rp.recover_reports(self.conn)
        self.conn.commit()
        rp._worker(self.db)
        stati = [row[0] for row in self.conn.execute('SELECT status FROM company_reports ORDER BY id')]
        self.assertEqual(stati[0], 'fertig')
        self.assertEqual(jobs.job_view(self.conn, r['job_id'])['done'] + jobs.job_view(self.conn, r['job_id'])['failed'], 2)
        leads, facts = self.conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], self.facts()
        rp.create_reports(self.conn, {'lead_ids': [ids[0]]}, self.db, start=False)  # zweiter Start
        rp._worker(self.db)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], leads, 'keine doppelten Leads')
        self.assertEqual(self.facts(), facts, 'keine doppelten Fakten')

    def test_403_does_not_stop_the_session(self):
        ok = self.lead()
        bad = self.lead(company='Gesperrt AG', website='https://gesperrt-403.example')
        r = rp.create_reports(self.conn, {'lead_ids': [bad, ok]}, self.db, start=False)
        rp._worker(self.db)
        v = jobs.job_view(self.conn, r['job_id'])
        self.assertEqual({t['label']: t['status'] for t in v['tasks']}, {'Gesperrt AG': 'failed', 'Kesselwerk': 'done'})
        self.assertEqual(v['status'], 'partial')
        self.assertIn('Bericht unvollständig', next(t for t in v['tasks'] if t['label'] == 'Gesperrt AG')['last_error'])
        jobs.retry_failed(self.conn, r['job_id'])
        self.assertEqual(self.conn.execute('SELECT status FROM company_reports WHERE lead_id=?', (bad,)).fetchone()[0], 'queued')
        rp._worker(self.db)
        retried = jobs.job_view(self.conn, r['job_id'])
        self.assertEqual(next(t for t in retried['tasks'] if t['label'] == 'Gesperrt AG')['attempts'], 1, 'erneut ausgeführt (Zähler neu)')
        self.assertEqual(retried['status'], 'partial', 'Website weiterhin gesperrt – ehrlich als Teilerfolg')

    def test_cancel_marks_reports(self):
        r = rp.create_reports(self.conn, {'lead_ids': [self.lead()]}, self.db, start=False)
        jobs.cancel(self.conn, r['job_id'])
        self.assertEqual(self.conn.execute('SELECT status FROM company_reports').fetchone()[0], 'abgebrochen')
        rp._worker(self.db)
        self.assertEqual(self.conn.execute('SELECT status FROM company_reports').fetchone()[0], 'abgebrochen', 'nicht nachträglich ausgeführt')


class SweepJobTests(tb.SweepBase):
    def cand_count(self):
        return self.conn.execute('SELECT COUNT(*) FROM discovery_candidates').fetchone()[0]

    def test_sweep_as_job_with_restart(self):
        s = sw.start_sweep(self.conn, {'place': '70173', 'radius_km': 30}, self.db, start=False)
        job = sw._sweep_job(self.conn, s['id'])
        keys = [t['task_key'] for t in jobs.job_view(self.conn, job['id'])['tasks']]
        self.assertEqual(keys, ['source:gleif', 'source:wikidata', 'source:osm', 'source:ted', 'finish'])
        jobs.run_one(self.db)                     # GLEIF fertig …
        crashed = jobs.claim(self.conn)           # … Wikidata läuft, dann Neustart
        self.assertEqual(crashed['task_key'], 'source:wikidata')
        jobs.recover(self.conn)
        sw.recover_sweeps(self.conn)
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT status FROM sweeps WHERE id=?', (s['id'],)).fetchone()[0], 'queued', 'nicht abgebrochen')
        jobs.run_until_idle(self.db)
        d = sw.sweep_detail(self.conn, s['id'])
        self.assertEqual(d['status'], 'fertig')
        self.assertTrue(all(d['progress'][k]['status'] == 'fertig' for k in ('gleif', 'wikidata', 'osm', 'ted')))
        self.assertIn('Websites über Wikidata (LEI)', d['progress']['gleif']['detail'], 'LEI-Ergänzung aus der Datenbank')
        n = self.cand_count()
        retry = jobs.job_view(self.conn, job['id'])
        self.assertEqual(retry['status'], 'done')
        jobs.retry_failed  # noqa: B018 – Dokumentation: kein Fehler → nichts zu wiederholen
        s2 = sw.start_sweep(self.conn, {'place': '70173', 'radius_km': 30}, self.db, start=False)
        jobs.run_until_idle(self.db)
        self.assertEqual(self.cand_count(), n, 'zweiter Lauf erzeugt keine Dubletten')
        self.assertEqual(sw.sweep_detail(self.conn, s2['id'])['progress']['gleif']['new'], 0)

    def test_failed_source_retry_through_job(self):
        self.net.fail.add('ted')
        s = sw.start_sweep(self.conn, {'place': '70173', 'radius_km': 30, 'sources': ['gleif', 'ted']}, self.db, start=False)
        jobs.run_until_idle(self.db)
        job = jobs.job_view(self.conn, sw._sweep_job(self.conn, s['id'])['id'])
        self.assertEqual(job['status'], 'partial')
        self.assertEqual({t['task_key']: t['status'] for t in job['tasks']}, {'source:gleif': 'done', 'source:ted': 'failed', 'finish': 'done'})
        self.net.fail.clear()
        self.assertEqual(sw.retry_sweep(self.conn, s['id'], self.db, start=False), {'retrying': ['ted']})
        jobs.run_until_idle(self.db)
        self.assertEqual(sw.sweep_detail(self.conn, s['id'])['progress']['ted']['status'], 'fertig')
        self.assertEqual(jobs.job_view(self.conn, job['id'])['status'], 'done')

    def test_websites_as_job(self):
        sw.import_file(self.conn, tb.GLEIF_CSV, {'plz': '70'})
        ids = [c['id'] for c in self.cands()]
        q = sw.queue_websites(self.conn, {'ids': ids}, self.db, start=False)
        self.assertTrue(q['job_id'])
        with mock.patch('sales_tool.imprint.research_domain', side_effect=CrawlError('HTTP 403')):
            sw._web_worker(self.db)
        v = jobs.job_view(self.conn, q['job_id'])
        self.assertEqual(v['status'], 'failed', '403 je Firma wird erfasst und bleibt erneut ausführbar')
        self.assertTrue(all(c['website_status'] == 'pruefung_fehlgeschlagen' for c in self.cands()))
        jobs.retry_failed(self.conn, q['job_id'])
        self.assertTrue(all(c['website_status'] == 'wartet' for c in self.cands()))


class JobHttpTests(JobBase):
    def test_endpoints(self):
        job = self.submit([{'n': 1}])
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
            status, lst = call('/api/research/jobs')
            self.assertEqual((status, lst['jobs'][0]['id'], lst['max_workers']), (200, job['id'], 3))
            self.assertEqual(call(f"/api/research/jobs/{job['id']}")[1]['tasks'][0]['task_key'], 't1')
            self.assertEqual(call(f"/api/research/jobs/{job['id']}/pause", 'POST', {})[1]['status'], 'paused')
            self.assertEqual(call(f"/api/research/jobs/{job['id']}/pause", 'POST', {})[0], 400)
            self.assertEqual(call(f"/api/research/jobs/{job['id']}/cancel", 'POST', {})[1]['status'], 'cancelled')
            self.assertEqual(call('/api/research/jobs/999/resume', 'POST', {})[0], 404)
            self.assertEqual(call(f"/api/research/jobs/{job['id']}/retry", 'POST', {})[0], 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
