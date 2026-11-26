"""R1.4 (2.0.0-dev69): Recherchemodi und Jobbudgets.

Abnahme laut Plan: Budgetüberschreitung bricht sauber ab und zeigt ein Teilergebnis; keine unendlichen Wiederholungen.
Website-Abrufe laufen gegen eine Attrappe – kein Test verbindet sich nach außen.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import report as rp  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import budget, fetchers, jobs  # noqa: E402
from sales_tool.research.fetchers import http as http_fetcher  # noqa: E402
from sales_tool.research.fetchers.base import FetchError, FetchResult  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


def fake_fetch(url, policy=None, origin=None):
    return FetchResult(source_url=url, final_url=url, status=200, content_type='text/html', body=b'x' * 1000,
                       fetched_at='2026-11-26T00:00:00Z', fetcher='attrappe')


class BudgetTests(unittest.TestCase):
    def test_modes_follow_the_plan(self):
        self.assertEqual({k: v['max_pages'] for k, v in budget.MODES.items()}, {'quick': 10, 'deep': 30, 'org': 50})
        self.assertEqual(budget.Budget.for_mode('erfunden').mode, budget.DEFAULT_MODE)
        with self.assertRaises(ValueError):
            budget.validate_mode('alles')

    def test_page_limit(self):
        b = budget.Budget.for_mode('quick')
        for _ in range(10):
            b.before('fiktiv.example')
        with self.assertRaises(FetchError) as err:
            b.before('fiktiv.example')
        self.assertEqual(err.exception.kind, 'budget')
        self.assertIn('Teilergebnis', str(err.exception))
        self.assertEqual((b.pages, b.exhausted), (10, '10 Seiten'))

    def test_host_time_and_byte_limits(self):
        b = budget.Budget.for_mode('quick')
        b.max_pages = 100
        for i in range(10):
            b.before(f'h{i}.example')
        b.before('h0.example')  # bekannter Host zählt nicht neu
        with self.assertRaises(FetchError):
            b.before('neu.example')
        self.assertEqual(b.exhausted, '10 verschiedene Hosts')
        now = [0.0]
        with mock.patch.object(budget, 'CLOCK', lambda: now[0]):
            t = budget.Budget.for_mode('quick')
            now[0] = 181
            with self.assertRaises(FetchError):
                t.before('a.example')
        m = budget.Budget.for_mode('quick')
        m.before('a.example')
        m.after(20_000_001)
        with self.assertRaises(FetchError):
            m.before('a.example')

    def test_fetch_counts_against_the_budget(self):
        with mock.patch.object(http_fetcher, 'fetch', fake_fetch):
            fetchers.fetch('https://fiktiv.example/', fetcher='http')  # ohne Budget: keine zusätzliche Grenze
            with budget.use(budget.Budget.for_mode('quick')) as b:
                got = 0
                with self.assertRaises(FetchError):
                    for i in range(20):
                        fetchers.fetch(f'https://fiktiv.example/{i}', fetcher='http')
                        got += 1
        self.assertEqual((got, b.pages, b.bytes), (10, 10, 10_000))
        self.assertIsNone(budget.current())


class JobBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / 'b.sqlite3'
        prepare_database(self.db)
        self.calls = []
        jobs.HANDLERS['budget_probe'] = self.handler
        self.p = mock.patch.object(http_fetcher, 'fetch', fake_fetch)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        jobs.HANDLERS.pop('budget_probe', None)
        jobs.stop_all_workers()
        self.tmp.cleanup()

    def handler(self, db_path, payload, ctx):
        """Liest Seiten, bis das Budget greift; behält, was gelesen wurde (Teilergebnis)."""
        self.calls.append(1)
        pages = []
        for i in range(100):
            try:
                fetchers.fetch(f'https://fiktiv.example/{i}', fetcher='http')
            except FetchError as exc:
                if payload.get('retry'):
                    raise jobs.Retry(str(exc))
                break
            pages.append(i)
        return {'pages': len(pages)}

    def run_job(self, mode, **payload):
        with connect(self.db) as conn:
            job, _ = jobs.submit(conn, 'budget_probe', 'Probe', [{'key': 'p1', 'kind': 'budget_probe', 'payload': payload}],
                                 params={'mode': mode}, start=False)
        jobs.run_until_idle(self.db)
        with connect(self.db) as conn:
            return conn.execute('SELECT * FROM research_tasks WHERE job_id=?', (job['id'],)).fetchone()

    def test_budget_stops_cleanly_with_partial_result(self):
        for mode, pages in (('quick', 10), ('deep', 30), ('org', 50)):
            with self.subTest(mode):
                task = self.run_job(mode)
                result = json.loads(task['result_json'])
                self.assertEqual(task['status'], 'done')
                self.assertEqual(result['pages'], pages, 'Teilergebnis bleibt erhalten')
                self.assertEqual((result['budget']['mode'], result['budget']['pages']), (mode, pages))
                self.assertIn('Teilergebnis', task['last_error'])

    def test_exhausted_budget_is_never_retried(self):
        task = self.run_job('quick', retry=True)
        self.assertEqual((task['status'], task['attempts']), ('failed', 1))
        self.assertEqual(len(self.calls), 1, 'kein zweiter Versuch mit frischem Budget')
        self.assertIn('Budget', task['last_error'])

    def test_without_mode_the_default_applies(self):
        with connect(self.db) as conn:
            jobs.submit(conn, 'budget_probe', 'Probe', [{'key': 'p1', 'kind': 'budget_probe', 'payload': {}}], start=False)
        jobs.run_until_idle(self.db)
        with connect(self.db) as conn:
            result = json.loads(conn.execute('SELECT result_json FROM research_tasks').fetchone()[0])
        self.assertEqual(result['budget']['mode'], budget.DEFAULT_MODE)

    def test_report_takes_the_mode(self):
        with connect(self.db) as conn:
            lid = conn.execute("INSERT INTO leads(company, website) VALUES ('Fiktiv Budget GmbH', 'https://fiktiv.example')").lastrowid
            conn.commit()
            with self.assertRaises(ValueError):
                rp.create_reports(conn, {'lead_ids': [lid], 'mode': 'alles'}, self.db, start=False)
            out = rp.create_reports(conn, {'lead_ids': [lid], 'mode': 'quick'}, self.db, start=False)
            params = json.loads(conn.execute('SELECT params_json FROM research_jobs WHERE id=?', (out['job_id'],)).fetchone()[0])
        self.assertEqual(params['mode'], 'quick')


if __name__ == '__main__':
    unittest.main()
