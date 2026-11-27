"""R1.4-Rest (2.0.0-dev71): bedingte Abrufe mit ETag/Last-Modified und Tagesbudget je Organisation.

Abnahme laut Plan: Budgetüberschreitung bricht sauber ab und zeigt ein Teilergebnis; keine unendlichen Wiederholungen.
Alle Abrufe laufen gegen Attrappen – kein Test verbindet sich nach außen.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import hosting, tenancy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import budget, fetchers, jobs, pagecache  # noqa: E402
from sales_tool.research import settings as rsettings  # noqa: E402
from sales_tool.research.fetchers import http as http_fetcher  # noqa: E402
from sales_tool.research.fetchers.base import FetchError, FetchResult  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

BODY = b'<html><body>Fiktive Seite</body></html>'


class FakeServer:
    """Antwortet mit ETag; kennt der Abruf das ETag, kommt 304 ohne Inhalt."""

    def __init__(self, etag='"v1"', last_modified='Wed, 25 Nov 2026 10:00:00 GMT'):
        self.etag, self.last_modified, self.seen = etag, last_modified, []

    def fetch(self, url, policy=None, origin=None):
        cond = (policy.extra if policy else {}).get('conditional')
        self.seen.append(cond)
        if cond and cond.get('etag') == self.etag:
            return FetchResult(source_url=url, final_url=url, status=304, content_type='', body=b'', fetched_at='2026-11-26T12:00:00Z',
                               fetcher='attrappe', etag=self.etag)
        return FetchResult(source_url=url, final_url=url, status=200, content_type='text/html', body=BODY,
                           fetched_at='2026-11-26T11:00:00Z', fetcher='attrappe', etag=self.etag, last_modified=self.last_modified)


class ConditionalTests(unittest.TestCase):
    def setUp(self):
        pagecache.clear()
        self.server = FakeServer()
        self.p = mock.patch.object(http_fetcher, 'fetch', self.server.fetch)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        pagecache.clear()

    def test_second_fetch_is_conditional_and_reuses_the_body(self):
        first = fetchers.fetch('https://fiktiv.example/team', fetcher='http')
        with budget.use(budget.Budget.for_mode('quick')) as b:
            second = fetchers.fetch('https://fiktiv.example/team', fetcher='http')
        self.assertIsNone(self.server.seen[0])
        self.assertEqual(self.server.seen[1], {'etag': '"v1"', 'last_modified': 'Wed, 25 Nov 2026 10:00:00 GMT'})
        self.assertEqual((second.status, second.body, second.revalidated), (200, BODY, True))
        self.assertEqual(second.content_hash, first.content_hash, 'gleicher Inhalt → gleicher Beleg-Hash')
        self.assertEqual(second.fetched_at, '2026-11-26T12:00:00Z')
        self.assertIn('HTTP 304', ' '.join(second.warnings))
        self.assertEqual((b.pages, b.bytes), (1, 0), 'eine Anfrage, aber keine übertragenen Bytes')

    def test_changed_page_replaces_the_stored_version(self):
        fetchers.fetch('https://fiktiv.example/', fetcher='http')
        self.server.etag = '"v2"'
        res = fetchers.fetch('https://fiktiv.example/', fetcher='http')
        self.assertFalse(res.revalidated)
        self.assertEqual(pagecache.lookup('https://fiktiv.example/').etag, '"v2"')

    def test_pages_without_validators_or_with_redirect_are_not_stored(self):
        self.server.etag = self.server.last_modified = ''
        fetchers.fetch('https://fiktiv.example/a', fetcher='http')
        self.assertIsNone(pagecache.lookup('https://fiktiv.example/a'))
        moved = FetchResult(source_url='https://fiktiv.example/b', final_url='https://fiktiv.example/c', status=200, content_type='text/html',
                            body=BODY, fetched_at='', fetcher='x', redirects=['https://fiktiv.example/b'], etag='"x"')
        pagecache.remember(moved)
        self.assertIsNone(pagecache.lookup('https://fiktiv.example/b'))

    def test_store_is_separate_per_organization(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a.sqlite3', Path(tmp) / 'b.sqlite3'
            with tenancy.use(a):
                fetchers.fetch('https://fiktiv.example/x', fetcher='http')
            with tenancy.use(b):
                fetchers.fetch('https://fiktiv.example/x', fetcher='http')
                self.assertIsNotNone(pagecache.lookup('https://fiktiv.example/x'))
        self.assertEqual(self.server.seen, [None, None], 'Organisation B nutzt nie die Fassung von Organisation A')

    def test_old_entries_expire(self):
        now = [1000.0]
        with mock.patch.object(pagecache, 'CLOCK', lambda: now[0]):
            fetchers.fetch('https://fiktiv.example/alt', fetcher='http')
            now[0] += pagecache.MAX_AGE + 1
            fetchers.fetch('https://fiktiv.example/alt', fetcher='http')
        self.assertEqual(self.server.seen, [None, None])

    def test_registry_and_offline_still_apply_before_the_store(self):
        fetchers.fetch('https://fiktiv.example/s', fetcher='http')
        from sales_tool import netpolicy
        with mock.patch.object(netpolicy, 'offline', lambda *a, **k: True):
            with self.assertRaises(FetchError) as err:
                fetchers.fetch('https://fiktiv.example/s', fetcher='http')
        self.assertEqual(err.exception.kind, 'offline')
        from sales_tool.research import sources
        with mock.patch.object(sources, 'check_url', side_effect=sources.SourceBlocked('gesperrt')):
            with self.assertRaises(FetchError) as err:
                fetchers.fetch('https://fiktiv.example/s', fetcher='http')
        self.assertEqual(err.exception.kind, 'source')

    def test_unexpected_304_is_an_error(self):
        with mock.patch.object(http_fetcher, 'fetch', lambda url, policy=None, origin=None: FetchResult(
                source_url=url, final_url=url, status=304, content_type='', body=b'', fetched_at='', fetcher='x')):
            with self.assertRaises(FetchError):
                fetchers.fetch('https://fiktiv.example/neu', fetcher='http')


class HttpHeaderTests(unittest.TestCase):
    """Der echte HTTP-Fetcher sendet die Prüfmerkmale und wertet 304 aus (Verbindung ist eine Attrappe)."""

    def run_fetch(self, status, conditional):
        sent = {}

        class Resp:
            def __init__(self):
                self.status = status

            def getheaders(self):
                return [('ETag', '"v1"'), ('Content-Type', 'text/html')]

            def read(self, n):
                body = b'' if status == 304 else BODY
                if sent.get('read'):
                    return b''
                sent['read'] = True
                return body

        class Conn:
            def __init__(self, host, port, ip, timeout):
                pass

            def request(self, method, path, headers):
                sent['headers'] = headers

            def getresponse(self):
                return Resp()

            def close(self):
                pass

        from sales_tool.research import policy as pol
        from dataclasses import replace
        policy = replace(pol.DEFAULT_POLICY, respect_robots=False, extra={'conditional': conditional} if conditional else {})
        with mock.patch.object(http_fetcher, 'resolve_public', lambda host, port: ['203.0.113.10']), \
                mock.patch.object(http_fetcher, '_PinnedHTTPSConnection', Conn):
            res = http_fetcher.fetch('https://fiktiv.example/', policy)
        return res, sent['headers']

    def test_conditional_headers_are_sent(self):
        res, headers = self.run_fetch(304, {'etag': '"v1"', 'last_modified': 'Wed, 25 Nov 2026 10:00:00 GMT'})
        self.assertEqual(headers['If-None-Match'], '"v1"')
        self.assertEqual(headers['If-Modified-Since'], 'Wed, 25 Nov 2026 10:00:00 GMT')
        self.assertEqual((res.status, res.body, res.etag), (304, b'', '"v1"'))

    def test_header_injection_is_refused(self):
        _, headers = self.run_fetch(200, {'etag': '"v1"\r\nX-Evil: 1', 'last_modified': ''})
        self.assertNotIn('If-None-Match', headers)

    def test_304_without_condition_is_an_error(self):
        with self.assertRaises(FetchError):
            self.run_fetch(304, None)

    def test_normal_answer_carries_validators(self):
        res, headers = self.run_fetch(200, None)
        self.assertNotIn('If-None-Match', headers)
        self.assertEqual((res.status, res.etag), (200, '"v1"'))


def fake_fetch(url, policy=None, origin=None):
    return FetchResult(source_url=url, final_url=url, status=200, content_type='text/html', body=b'x' * 1000,
                       fetched_at='2026-11-26T00:00:00Z', fetcher='attrappe')


class DailyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / 'd.sqlite3'
        prepare_database(self.db)
        budget.reset_usage()
        rsettings.reset()
        with connect(self.db) as conn:
            rsettings.save(conn, {'daily_pages': 200})
        self.key = tenancy.db_key(self.db)
        self.calls = []
        jobs.HANDLERS['daily_probe'] = self.handler
        self.p = mock.patch.object(http_fetcher, 'fetch', fake_fetch)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        jobs.HANDLERS.pop('daily_probe', None)
        jobs.stop_all_workers()
        rsettings.reset()
        budget.reset_usage()
        hosting.unregister_all()
        self.tmp.cleanup()

    def handler(self, db_path, payload, ctx):
        self.calls.append(1)
        pages = 0
        for i in range(payload.get('n', 5)):
            try:
                fetchers.fetch(f'https://fiktiv-{i % 9}.example/{i}', fetcher='http')
            except FetchError:
                if payload.get('raise'):
                    raise
                break
            pages += 1
        return {'pages': pages}

    def submit(self, n, kind='daily_probe', **payload):
        """n Seiten, verteilt auf Schritte zu höchstens 40 (das Org-Budget je Schritt liegt bei 50)."""
        tasks = [{'key': f'p{i}', 'kind': kind, 'payload': {'n': min(40, n - i), **payload}} for i in range(0, n, 40)]
        with connect(self.db) as conn:
            job, _ = jobs.submit(conn, kind, 'Probe', tasks, params={'mode': 'org'}, start=False)
        return job['id']

    def use_up(self, pages):
        with tenancy.use(self.db):
            for i in range(pages):
                fetchers.fetch(f'https://fiktiv.example/vorher/{i}', fetcher='http')

    def tasks(self, job_id):
        with connect(self.db) as conn:
            return conn.execute('SELECT * FROM research_tasks WHERE job_id=? ORDER BY id', (job_id,)).fetchall()

    def task(self, job_id):
        with connect(self.db) as conn:
            return conn.execute('SELECT * FROM research_tasks WHERE job_id=?', (job_id,)).fetchone()

    def test_daily_limit_stops_with_partial_result(self):
        with tenancy.use(self.db):
            for i in range(200):
                fetchers.fetch(f'https://fiktiv.example/{i}', fetcher='http')
            with self.assertRaises(FetchError) as err:
                fetchers.fetch('https://fiktiv.example/zuviel', fetcher='http')
            self.assertEqual(err.exception.kind, 'budget')
            self.assertIn('Tagesbudget', str(err.exception))
            self.assertTrue(budget.daily_usage()['exhausted'])
        self.assertFalse(budget.daily_exhausted(':memory:andere'), 'andere Organisation unberührt')

    def test_new_day_starts_at_zero(self):
        with tenancy.use(self.db):
            with mock.patch.object(budget, 'TODAY', lambda: '2026-11-26'):
                for i in range(200):
                    fetchers.fetch(f'https://fiktiv.example/{i}', fetcher='http')
                self.assertTrue(budget.daily_exhausted())
            with mock.patch.object(budget, 'TODAY', lambda: '2026-11-27'):
                self.assertFalse(budget.daily_exhausted())
                fetchers.fetch('https://fiktiv.example/morgen', fetcher='http')
                self.assertEqual(budget.daily_usage()['pages'], 1)

    def test_byte_limit_counts_too(self):
        big = lambda url, policy=None, origin=None: FetchResult(source_url=url, final_url=url, status=200, content_type='text/html',  # noqa: E731
                                                                body=b'x' * 2_000_000, fetched_at='', fetcher='x')
        with tenancy.use(self.db), mock.patch.object(http_fetcher, 'fetch', big):
            for i in range(101):
                fetchers.fetch(f'https://fiktiv.example/{i}', fetcher='http')
            with self.assertRaises(FetchError):
                fetchers.fetch('https://fiktiv.example/x', fetcher='http')

    def test_interrupted_step_waits_for_tomorrow_without_using_an_attempt(self):
        self.use_up(190)
        job = self.submit(30, **{'raise': True})
        jobs.run_until_idle(self.db)
        task = self.task(job)
        self.assertEqual(task['status'], 'queued', 'Schritt wartet statt zu scheitern')
        self.assertEqual(task['attempts'], 0, 'der Versuch zählt nicht')
        self.assertIn('Tagesbudget', task['last_error'])
        self.assertEqual(len(self.calls), 1, 'keine Wiederholung am selben Tag')
        self.assertGreater(task['next_attempt_at'], jobs.CLOCK() + 30)

    def test_partial_result_is_kept_when_the_handler_stops(self):
        self.use_up(190)
        job = self.submit(30)
        jobs.run_until_idle(self.db)
        task = self.task(job)
        self.assertEqual(task['status'], 'done')
        self.assertEqual(json.loads(task['result_json'])['pages'], 10)

    def test_waiting_web_jobs_do_not_start_when_exhausted(self):
        self.use_up(200)
        with mock.patch.object(jobs, 'WEB_KINDS', jobs.WEB_KINDS + ('daily_probe',)):
            job = self.submit(3)
            jobs.run_until_idle(self.db)
        self.assertEqual(self.task(job)['status'], 'queued')
        self.assertEqual(self.calls, [], 'Website-Auftrag startet erst morgen')

    def test_usage_survives_a_restart(self):
        job = self.submit(150)
        jobs.run_until_idle(self.db)
        self.assertEqual([t['status'] for t in self.tasks(job)], ['done'] * 4)
        budget.reset_usage()  # Neustart: Zähler im Speicher leer
        self.assertEqual(budget.daily_usage(self.key)['pages'], 150)

    def test_without_limit_nothing_is_refused(self):
        with connect(self.db) as conn:
            rsettings.save(conn, {'daily_pages': 0})
        with tenancy.use(self.db):
            for i in range(300):
                fetchers.fetch(f'https://fiktiv.example/{i}', fetcher='http')
            self.assertFalse(budget.daily_exhausted())

    def test_hosted_organizations_always_have_a_limit(self):
        hosting.register(self.db)
        with connect(self.db) as conn:
            with self.assertRaises(PermissionError):
                rsettings.save(conn, {'daily_pages': 0})
            rsettings.save(conn, {'daily_pages': 200})
        self.assertEqual(rsettings.get(self.key)['daily_pages'], 200)
        with connect(self.db) as conn:
            from sales_tool.quality import put_setting
            put_setting(conn, rsettings.KEY, {**rsettings.DEFAULTS, 'daily_pages': 0})
            conn.commit()
            rsettings.load(conn)
        self.assertEqual(rsettings.get(self.key)['daily_pages'], 1000, 'gespeicherte 0 wirkt im Server nicht')


if __name__ == '__main__':
    unittest.main()
