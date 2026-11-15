"""2.0.0-dev35: Abnahmefall T14 – Recherche nach einem Fehler oder Neustart wieder aufnehmen (Produktreview M23, Teil 1).

Website-Bewertung und Karriereseiten-Scan laufen jetzt über das gemeinsame Auftragssystem:
- Ein Neustart mitten in einer Bewertung bzw. einem Scan setzt sie fort, statt sie als „fehlgeschlagen“ zu verwerfen.
- Bewertungen bzw. Scans aus älteren Versionen (ohne Auftragsschritt) werden beim Neustart übernommen.
- Nach einem Abruffehler lässt sich genau dieser Schritt erneut ausführen; erfolgreiche Schritte bleiben, wie sie sind.
Alle Firmen sind fiktiv; die Abrufe sind Attrappen, keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_phase2_scoring import capture  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import buying_signals as bs  # noqa: E402
from sales_tool import website_scorer as ws  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402
from sales_tool.website_analyzer import CrawlError  # noqa: E402


class ResumeScenario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 't14.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self._orig = (ws.CAPTURE, ws.CAPTURE_FALLBACK, ws.playwright_available, bs.scan_career)
        self.calls = []

        def cap(url):
            self.calls.append(url)
            if 'kaputt' in url and len([c for c in self.calls if 'kaputt' in c]) == 1:
                raise CrawlError('Zeitüberschreitung beim Abruf der Startseite.')
            return dict(capture(), screenshots=[])
        ws.CAPTURE = ws.CAPTURE_FALLBACK = cap
        ws.playwright_available = lambda: False
        bs.scan_career = lambda website, company=None: ([], [{'url': website, 'status': 'gelesen'}])
        add = lambda name, web: self.conn.execute("INSERT INTO leads(company, website) VALUES (?, ?)", (name, web)).lastrowid
        self.a = add('Fortsetzen Fiktiv GmbH', 'https://fortsetzen.example')
        self.b = add('Kaputt Fiktiv GmbH', 'https://kaputt.example')
        self.conn.commit()

    def tearDown(self):
        ws.CAPTURE, ws.CAPTURE_FALLBACK, ws.playwright_available, bs.scan_career = self._orig
        jobs.stop_workers(self.db)
        self.conn.close()
        cleanup_tmp(self.tmp)

    def status(self, table, ident):
        return self.conn.execute(f'SELECT status FROM {table} WHERE id=?', (ident,)).fetchone()[0]

    def restart(self):
        """Neustart nachstellen: Prozess weg, Datenbank bleibt; danach die üblichen Wiederaufnahmen."""
        self.conn.close()
        prepare_database(self.db)
        self.conn = connect(self.db)

    def test_audit_interrupted_by_restart_is_resumed(self):
        res = ws.enqueue(self.conn, [self.a], None)  # ohne db_path: Auftrag angelegt, noch kein Arbeiter gestartet
        [aid] = res['queued']
        task = jobs.claim(self.conn)  # Schritt läuft …
        self.conn.execute("UPDATE website_audits SET status='running' WHERE id=?", (aid,))
        self.conn.commit()
        self.assertEqual(task['kind'], 'website_audit')
        self.restart()  # … und der Rechner startet neu
        self.assertEqual(self.status('website_audits', aid), 'queued', 'nicht verworfen, sondern wieder eingereiht')
        jobs.run_until_idle(self.db, kinds=('website_audit',))
        self.assertEqual(self.status('website_audits', aid), 'done')

    def test_legacy_queued_audit_and_scan_are_adopted_on_restart(self):
        aid = self.conn.execute("INSERT INTO website_audits(lead_id, url, status) VALUES (?, 'https://fortsetzen.example', 'running')", (self.a,)).lastrowid
        sid = self.conn.execute("INSERT INTO signal_scans(lead_id, status) VALUES (?, 'running')", (self.a,)).lastrowid
        self.conn.commit()
        self.restart()
        self.assertEqual((self.status('website_audits', aid), self.status('signal_scans', sid)), ('queued', 'queued'))
        n = self.conn.execute("SELECT COUNT(*) FROM research_tasks WHERE kind IN ('website_audit','career_scan') AND status='queued'").fetchone()[0]
        self.assertEqual(n, 2, 'als Auftragsschritte übernommen')
        jobs.run_until_idle(self.db)
        self.assertEqual((self.status('website_audits', aid), self.status('signal_scans', sid)), ('done', 'done'))
        self.restart()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM research_tasks WHERE kind='website_audit'").fetchone()[0], 1, 'kein zweiter Schritt')

    def test_failed_fetch_retries_only_that_step(self):
        res = ws.enqueue(self.conn, [self.a, self.b], None)
        jobs.run_until_idle(self.db, kinds=('website_audit',))
        ok, bad = res['queued']
        self.assertEqual((self.status('website_audits', ok), self.status('website_audits', bad)), ('done', 'failed'))
        job_id = self.conn.execute("SELECT job_id FROM research_tasks WHERE task_key=?", (f'audit:{bad}',)).fetchone()[0]
        view = jobs.job_view(self.conn, job_id)
        self.assertEqual(sorted(t['status'] for t in view['tasks']), ['done', 'failed'])
        self.assertIn('Zeitüberschreitung', next(t for t in view['tasks'] if t['status'] == 'failed')['last_error'])
        before = len(self.calls)
        jobs.retry_failed(self.conn, job_id)
        self.assertEqual(self.status('website_audits', bad), 'queued')
        jobs.run_until_idle(self.db, kinds=('website_audit',))
        self.assertEqual(self.status('website_audits', bad), 'done')
        self.assertEqual(self.calls[before:], ['https://kaputt.example'], 'nur der fehlgeschlagene Schritt erneut')
        self.assertEqual(self.status('website_audits', ok), 'done')

    def test_scan_runs_through_shared_jobs(self):
        res = bs.enqueue_scans(self.conn, [self.a], None)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM research_tasks WHERE kind='career_scan'").fetchone()[0], 1)
        jobs.run_until_idle(self.db, kinds=('career_scan',))
        self.assertEqual(self.status('signal_scans', res['queued'][0]), 'done')


if __name__ == '__main__':
    unittest.main()
