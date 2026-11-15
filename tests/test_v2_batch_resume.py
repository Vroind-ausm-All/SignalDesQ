"""2.0.0-dev39: Produktreview M23 – Impressum-Sammelprüfung setzt nach einem Neustart fort.

- Ein Lauf, der beim Neustart lief, wird beim Start der App automatisch fortgesetzt.
- Ein von dir pausierter Lauf bleibt pausiert.
- Im Offline-Modus wird nichts fortgesetzt; der Lauf wartet sichtbar.
- „Heute“ zeigt laufende bzw. wartende Sammelprüfungen.
Alle Domains sind fiktiv; die Abrufe sind Attrappen, keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_phase1_datenbasis as p1  # noqa: E402 – nur Testdaten (FakeWeb, WEB), keine Testklasse übernehmen
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import imprint_batch as ib  # noqa: E402
from sales_tool.model import connect, init_db  # noqa: E402
from sales_tool import imprint  # noqa: E402
from sales_tool import netpolicy  # noqa: E402
from sales_tool import today as td  # noqa: E402

DOMAINS = 'musterwerk-beispiel.de\npixelhafen-beispiel.de'


class BatchResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'resume.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)
        self._orig = (imprint.FETCH, imprint.SLEEP)
        imprint.FETCH, imprint.SLEEP = p1.FakeWeb(p1.WEB), (lambda s: None)

    def interrupted_run(self):
        run = ib.create_run(self.conn, {'domains': DOMAINS}, self.db, start=False)
        self.conn.execute("UPDATE batch_items SET status='running' WHERE run_id=? AND position=1", (run['id'],))
        self.conn.commit()
        ib.recover_batches(self.conn)  # Neustart
        self.conn.commit()
        return run['id']

    def tearDown(self):
        netpolicy.STATE['stored'] = False
        imprint.FETCH, imprint.SLEEP = self._orig
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_interrupted_run_resumes_automatically(self):
        rid = self.interrupted_run()
        self.assertEqual(ib.run_detail(self.conn, rid)['status'], 'paused')
        self.assertEqual(ib.resume_after_restart(self.db), 1)
        ib.wait_for(rid)
        self.assertEqual(ib.run_detail(self.conn, rid)['counts'], {'done': 2})
        self.assertEqual(ib.resume_after_restart(self.db), 0, 'nichts doppelt')

    def test_user_pause_stays_paused_and_offline_waits(self):
        user = ib.create_run(self.conn, {'domains': DOMAINS}, self.db, start=False)['id']
        ib.control_run(self.conn, user, 'pause', self.db)
        ib.recover_batches(self.conn)
        self.conn.commit()
        rid = self.interrupted_run()
        netpolicy.set_offline(self.conn, True)
        self.assertEqual(ib.resume_after_restart(self.db), 0, 'offline: nicht fortsetzen')
        items = [i for i in td.wiedervorlage(self.conn) if i['kind'] == 'sammelpruefung']
        self.assertEqual(len(items), 1)
        self.assertIn('wartet auf Fortsetzen', items[0]['title'])
        netpolicy.set_offline(self.conn, False)
        self.assertEqual(ib.resume_after_restart(self.db), 1, 'nur der durch Neustart pausierte Lauf')
        ib.wait_for(rid)
        self.assertEqual(ib.run_detail(self.conn, user)['status'], 'paused', 'von dir pausiert bleibt pausiert')


if __name__ == '__main__':
    unittest.main()
