"""2.0.0-dev36: Abnahmefall T14 für die übrigen Recherche-Läufe (Produktreview M23 Teil 2).

Schnellprüfung, Suche nach öffentlichen Ansprechpartnern und KI-Analyse laufen jetzt über das gemeinsame Auftragssystem:
- Neustart mitten im Lauf → der Lauf wird fortgesetzt (vorher: verworfen bzw. bei den Ansprechpartnern dauerhaft „läuft“).
- Läufe aus älteren Versionen ohne Auftragsschritt → als unterbrochen gekennzeichnet, nie dauerhaft „läuft“.
- Ein fehlgeschlagener Lauf ist ein fehlgeschlagener Auftragsschritt mit Grund.
Alle Firmen sind fiktiv; die Abrufe sind Attrappen, keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import analysis_jobs, public_contacts, quickscan  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

CRAWL = {'source': 'https://lauf.example/', 'pages': [{'url': 'https://lauf.example/', 'title': 'Start', 'text': 'Willkommen bei Lauf Fiktiv GmbH. Kontakt über das Formular.',
                                                    'links': [], 'forms': 1, 'html': ''}], 'warnings': []}


class RunResumeScenario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'runs.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, website, offer) VALUES ('Lauf Fiktiv GmbH', 'https://lauf.example', 'conversion')").lastrowid
        self.conn.commit()
        self.no_workers = patch('sales_tool.research.jobs.ensure_workers')  # Ablauf im Test von Hand steuern
        self.no_workers.start()

    def tearDown(self):
        self.no_workers.stop()
        jobs.stop_workers(self.db)
        self.conn.close()
        cleanup_tmp(self.tmp)

    def restart(self):
        self.conn.close()
        prepare_database(self.db)
        self.conn = connect(self.db)

    def row(self, table, ident):
        return self.conn.execute(f'SELECT status, error FROM {table} WHERE id=?', (ident,)).fetchone()

    def crash_during_first_task(self, table, ident):
        task = jobs.claim(self.conn)
        self.conn.execute(f"UPDATE {table} SET status='running' WHERE id=?", (ident,))
        self.conn.commit()
        self.restart()
        return task

    def test_quickscan_resumes_after_restart(self):
        rid = self.conn.execute("INSERT INTO quick_scans(url, provider, model) VALUES ('https://lauf.example/', 'rules', 'regelmodus')").lastrowid
        self.conn.commit()
        quickscan.enqueue(self.db, rid, 'https://lauf.example/', 'rules', 'regelmodus')
        self.assertEqual(self.crash_during_first_task('quick_scans', rid)['kind'], 'schnellpruefung')
        self.assertEqual(self.row('quick_scans', rid)['status'], 'queued', 'fortgesetzt statt verworfen')
        with patch('sales_tool.quickscan.crawl_site', return_value=CRAWL):
            jobs.run_until_idle(self.db, kinds=('schnellpruefung',))
        self.assertEqual(self.row('quick_scans', rid)['status'], 'done')

    def test_contact_research_resumes_and_legacy_never_stays_running(self):
        rid = self.conn.execute('INSERT INTO contact_research_runs(lead_id) VALUES (?)', (self.lead,)).lastrowid
        legacy = self.conn.execute("INSERT INTO contact_research_runs(lead_id, status) VALUES (?, 'running')", (self.lead,)).lastrowid
        self.conn.commit()
        public_contacts.enqueue(self.db, rid, self.lead, 'https://lauf.example', 'conversion')
        self.crash_during_first_task('contact_research_runs', rid)
        self.assertEqual(self.row('contact_research_runs', rid)['status'], 'queued')
        old = self.row('contact_research_runs', legacy)
        self.assertEqual(old['status'], 'failed', 'früher blieb so ein Lauf dauerhaft auf „läuft“')
        self.assertIn('Neustart', old['error'])
        with patch('sales_tool.public_contacts.crawl_site', return_value=CRAWL):
            jobs.run_until_idle(self.db, kinds=('ansprechpartner',))
        self.assertEqual(self.row('contact_research_runs', rid)['status'], 'done')

    def test_failed_analysis_is_failed_task_with_reason(self):
        rid = self.conn.execute("INSERT INTO analysis_runs(lead_id, provider, model) VALUES (?, 'rules', 'regelmodus')", (self.lead,)).lastrowid
        self.conn.commit()
        analysis_jobs.enqueue(self.db, rid, self.lead, 'https://lauf.example', 'rules', 'regelmodus')
        with patch('sales_tool.analysis_jobs.crawl_site', side_effect=ValueError('Abruf durch robots.txt untersagt.')):
            jobs.run_until_idle(self.db, kinds=('ki_analyse',))
        self.assertEqual(self.row('analysis_runs', rid)['status'], 'failed')
        t = self.conn.execute("SELECT status, last_error FROM research_tasks WHERE kind='ki_analyse'").fetchone()
        self.assertEqual(t['status'], 'failed')
        self.assertIn('robots', t['last_error'])
        self.restart()
        self.assertEqual(self.row('analysis_runs', rid)['status'], 'failed', 'abgeschlossene Läufe bleiben, wie sie sind')


if __name__ == '__main__':
    unittest.main()
