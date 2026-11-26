"""R0.7 (2.0.0-dev67): Sperre und Mandantengrenze über alle Wege – Import, Hintergrundauftrag, Export, Wiederherstellung.

Kennzahl des Plans: „0 Tenant-/Sperrverletzungen in definierten Tests“. Jeder Test hier wird ohne die zugehörige Regel rot:
- Wiederherstellen einer älteren Sicherung hob vor dev67 spätere Sperren auf (backup_restore.keep_suppressions).
- Ein wartender Auftrag rief die Website einer inzwischen gesperrten Firma ab (research/jobs.blocked_reason).
- Die Impressum-Sammelprüfung prüfte die Sperre nur beim Anlegen (imprint_batch._process).
- Der Recherche-Export zeigte eine nur über die Sperrliste gesperrte Firma als „unbekannt“ (research_center.export_csv).
Alle Firmen und Domains sind erfunden; es gibt keine Netzabfragen.
"""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sales_tool import backup_restore, buying_signals, imprint, imprint_batch, research_center, tenancy  # noqa: E402
from sales_tool import website_scorer as ws  # noqa: E402
from sales_tool.accounting_api import create_backup  # noqa: E402
from sales_tool.company_data import add_suppression, suppress_lead  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.research import jobs  # noqa: E402
from sales_tool.server import import_leads, prepare_database  # noqa: E402
from sales_tool.workday import ContactLocked, assert_contact_allowed, contact_lock  # noqa: E402

from tmpclean import cleanup_tmp  # noqa: E402

SITE = 'https://gesperrt-beispiel.example'


def no_network(*a, **k):
    raise AssertionError('Für eine gesperrte Firma darf nichts abgerufen werden.')


class GateBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'gate.sqlite3'
        prepare_database(self.db)
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, company='Gesperrt Beispiel GmbH', website=SITE, **extra):
        data = {'company': company, 'website': website, **extra}
        lid = self.conn.execute(f"INSERT INTO leads({','.join(data)}) VALUES ({','.join('?' * len(data))})", tuple(data.values())).lastrowid
        self.conn.commit()
        return lid

    def block_domain(self):
        add_suppression(self.conn, 'domain', SITE, 'Widerspruch (Test)')
        self.conn.commit()

    def run_jobs(self):
        with mock.patch.object(imprint, 'FETCH', no_network), mock.patch.object(ws, 'CAPTURE_FALLBACK', no_network), \
             mock.patch.object(ws, 'playwright_available', lambda: False), mock.patch.object(buying_signals, 'scan_career', no_network):
            jobs.run_until_idle(self.db)

    def task_rows(self, kind):
        return self.conn.execute('SELECT status, last_error FROM research_tasks WHERE kind=?', (kind,)).fetchall()


class ImportGateTests(GateBase):
    def test_lead_import_skips_suppressed(self):
        self.block_domain()
        res = import_leads(self.conn, {'rows': [{'company': 'Andere Firmierung GmbH', 'website': SITE}, {'company': 'Frei Beispiel GmbH'}]})
        self.assertEqual((res['imported'], res.get('suppressed')), (1, 1))
        self.assertIsNone(self.conn.execute('SELECT 1 FROM leads WHERE website=?', (SITE,)).fetchone())

    def test_imprint_batch_marks_suppressed_without_fetch(self):
        self.block_domain()
        run = imprint_batch.create_run(self.conn, {'domains': 'gesperrt-beispiel.example'}, self.db, start=False)
        self.assertEqual(run['items'][0]['status'], 'gesperrt')


class JobGateTests(GateBase):
    """Gesperrt, WÄHREND der Auftrag wartet: Ausführung prüft erneut, die Website wird nicht abgerufen."""

    def test_website_audit_blocked_after_queueing(self):
        lid = self.lead()
        aid = self.conn.execute('INSERT INTO website_audits(lead_id, url) VALUES (?,?)', (lid, SITE)).lastrowid
        self.conn.commit()
        ws._audit_job(self.conn, [aid], self.db, False)
        suppress_lead(self.conn, lid)
        self.conn.execute("UPDATE leads SET permission='nicht_kontaktieren' WHERE id=?", (lid,))
        self.conn.commit()
        self.run_jobs()
        self.assertEqual(self.task_rows('website_audit')[0]['status'], 'skipped')
        audit = self.conn.execute('SELECT status, error FROM website_audits WHERE id=?', (aid,)).fetchone()
        self.assertEqual(audit['status'], 'failed')
        self.assertIn('Gesperrt', audit['error'])

    def test_career_scan_blocked_by_domain_list_only(self):
        lid = self.lead()
        sid = self.conn.execute('INSERT INTO signal_scans(lead_id) VALUES (?)', (lid,)).lastrowid
        self.conn.commit()
        buying_signals._scan_job(self.conn, [sid], self.db, False)
        self.block_domain()  # Firma selbst unverändert („unbekannt“), nur die Domain steht auf der Sperrliste
        self.run_jobs()
        row = self.task_rows('career_scan')[0]
        self.assertEqual(row['status'], 'skipped')
        self.assertIn('Sperrliste', row['last_error'])

    def test_imprint_batch_item_blocked_while_waiting(self):
        run = imprint_batch.create_run(self.conn, {'domains': 'gesperrt-beispiel.example'}, self.db, start=False)
        item = run['items'][0]
        self.assertEqual(item['status'], 'pending')
        self.block_domain()
        with mock.patch.object(imprint, 'research_domain', no_network):
            imprint_batch._process(self.db, item['id'], False)
        self.assertEqual(self.conn.execute('SELECT status FROM batch_items WHERE id=?', (item['id'],)).fetchone()[0], 'gesperrt')

    def test_website_search_blocked_while_waiting(self):
        from sales_tool import sweep as sw
        sid = self.conn.execute("INSERT INTO sweeps(label, params_json, status) VALUES ('t', '{}', 'fertig')").lastrowid
        run = sw._run_record(self.conn, 'osm', sid, {})
        ctx = {'industries': [], 'keywords': [], 'org_kinds': sw.ORG_KINDS_DEFAULT, 'operative': False}
        sw.store_items(self.conn, sid, run, 'osm', [{'name': 'Gesperrt Beispiel GmbH', 'zip': '70173', 'city': 'Stuttgart'}], ctx)
        cid = self.conn.execute('SELECT id FROM discovery_candidates').fetchone()[0]
        sw.queue_websites(self.conn, {'ids': [cid]}, self.db, start=False)
        add_suppression(self.conn, 'name', 'Gesperrt Beispiel GmbH', 'Widerspruch (Test)')
        self.conn.commit()
        with mock.patch.object(imprint, 'research_domain', no_network):
            jobs.run_until_idle(self.db, kinds=('website',))
        self.assertEqual(self.task_rows('website')[0]['status'], 'skipped')
        self.assertEqual(self.conn.execute('SELECT website_status FROM discovery_candidates WHERE id=?', (cid,)).fetchone()[0], '')

    def test_unblocked_firm_still_runs(self):
        """Gegenprobe: ohne Sperre läuft der Auftrag (die Prüfung blockiert nicht pauschal)."""
        lid = self.lead('Frei Beispiel GmbH', 'https://frei-beispiel.example')
        sid = self.conn.execute('INSERT INTO signal_scans(lead_id) VALUES (?)', (lid,)).lastrowid
        self.conn.commit()
        buying_signals._scan_job(self.conn, [sid], self.db, False)
        with mock.patch.object(buying_signals, 'scan_career', lambda website, company='': ([], ['geprüft (Test)'])):
            jobs.run_until_idle(self.db)
        self.assertEqual(self.task_rows('career_scan')[0]['status'], 'done')


class ExportGateTests(GateBase):
    def test_research_export_names_suppression(self):
        self.lead()
        self.lead('Frei Beispiel GmbH', 'https://frei-beispiel.example')
        self.block_domain()
        rows = {r[0]: r for r in __import__('csv').reader(io.StringIO(research_center.export_csv(self.conn).lstrip('﻿')), delimiter=';')}
        self.assertEqual(rows['Firma'][4], 'Kontaktsperre')
        self.assertTrue(rows['Gesperrt Beispiel GmbH'][4].startswith('GESPERRT'), rows['Gesperrt Beispiel GmbH'])
        self.assertEqual(rows['Frei Beispiel GmbH'][4], 'nein')


class RestoreGateTests(GateBase):
    def test_restore_keeps_later_suppressions(self):
        lid = self.lead(business_email='info@gesperrt-beispiel.example')
        backup = create_backup(self.db)['path']  # Stand ohne Sperre
        suppress_lead(self.conn, lid, 'Widerspruch nach der Sicherung')
        self.conn.execute("UPDATE leads SET permission='nicht_kontaktieren', stage='gesperrt' WHERE id=?", (lid,))
        add_suppression(self.conn, 'name', 'Ganz Andere Fiktiv GmbH', 'Sperrliste (Test)')
        self.conn.commit()
        self.conn.close()
        out = backup_restore.restore(self.db, backup, confirm=True)
        self.conn = connect(self.db)
        self.assertGreater(out['kept_suppressions'], 0)
        self.assertIn('hebt keine Sperre auf', out['notice'])
        lead = self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual(lead['permission'], 'unbekannt', 'Firmendaten sind der alte Stand …')
        self.assertTrue(contact_lock(self.conn, lead), '… die Sperre gilt trotzdem')
        with self.assertRaises(ContactLocked):
            assert_contact_allowed(self.conn, lead, 'Entwurf')
        self.assertTrue(self.conn.execute("SELECT 1 FROM suppression_list WHERE kind='name' AND display='Ganz Andere Fiktiv GmbH'").fetchone(),
                        'auch Sperrlisten-Einträge ohne Firma bleiben')

    def test_restore_does_not_bring_back_candidates_of_suppressed_company(self):
        # R2.4: Kandidaten aus dem alten Stand einer inzwischen gesperrten Firma werden beim Wiederherstellen gelöscht
        lid = self.lead(business_email='info@gesperrt-beispiel.example')
        run = self.conn.execute("INSERT INTO contact_research_runs(lead_id, status) VALUES (?, 'done')", (lid,)).lastrowid
        self.conn.execute("INSERT INTO contact_candidates(run_id, lead_id, full_name, job_title, source_url) VALUES (?,?,?,?,?)",
                          (run, lid, 'Erika Fiktiv', 'Geschäftsführerin', 'https://gesperrt-beispiel.example/team'))
        self.conn.commit()
        backup = create_backup(self.db)['path']
        suppress_lead(self.conn, lid, 'Widerspruch nach der Sicherung')
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM contact_candidates').fetchone()[0], 0)
        self.conn.close()
        backup_restore.restore(self.db, backup, confirm=True)
        self.conn = connect(self.db)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM contact_candidates WHERE lead_id=?', (lid,)).fetchone()[0], 0)

    def test_restore_without_suppressions_changes_nothing(self):
        self.lead('Frei Beispiel GmbH', 'https://frei-beispiel.example')
        backup = create_backup(self.db)['path']
        self.conn.close()
        out = backup_restore.restore(self.db, backup, confirm=True)
        self.conn = connect(self.db)
        self.assertEqual(out['kept_suppressions'], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM suppression_list').fetchone()[0], 0)


class TenantGateTests(unittest.TestCase):
    """Mandantengrenze über Auftrag, Sperre, Export und Wiederherstellung (eine Datenbank je Organisation)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = tenancy.Directory(Path(self.tmp.name) / 'm')
        self.orgs = {}
        for slug, name in (('nord', 'Nord'), ('sued', 'Süd')):
            org = self.dir.create(slug, name)
            with connect(org['db_path']) as conn:
                lid = conn.execute('INSERT INTO leads(company, website) VALUES (?,?)', (f'{name} Fiktiv GmbH', SITE)).lastrowid
                conn.commit()
            self.orgs[slug] = {'db': Path(org['db_path']), 'lead': lid}

    def tearDown(self):
        jobs.stop_all_workers()
        self.tmp.cleanup()

    def test_job_of_one_org_never_runs_in_the_other(self):
        nord, sued = self.orgs['nord'], self.orgs['sued']
        with connect(nord['db']) as conn:
            sid = conn.execute('INSERT INTO signal_scans(lead_id) VALUES (?)', (nord['lead'],)).lastrowid
            conn.commit()
            buying_signals._scan_job(conn, [sid], nord['db'], False)
        self.assertFalse(jobs.run_one(sued['db']), 'Süd sieht den Auftrag von Nord nicht')
        with connect(nord['db']) as conn:
            self.assertEqual(conn.execute("SELECT status FROM research_tasks WHERE kind='career_scan'").fetchone()[0], 'queued')

    def test_suppression_stays_in_its_org(self):
        with connect(self.orgs['nord']['db']) as conn:
            add_suppression(conn, 'domain', SITE, 'Widerspruch bei Nord')
            conn.commit()
            self.assertTrue(contact_lock(conn, conn.execute('SELECT * FROM leads').fetchone()))
        with connect(self.orgs['sued']['db']) as conn:
            self.assertEqual(contact_lock(conn, conn.execute('SELECT * FROM leads').fetchone()), '',
                             'eine Sperre gilt in der Organisation, die sie erfasst hat')

    def test_export_and_restore_touch_only_one_org(self):
        target = Path(self.tmp.name) / 'nord-export.zip'
        tenancy.export_organization(self.orgs['nord']['db'], target)
        with zipfile.ZipFile(target) as zf, tempfile.TemporaryDirectory() as t:
            name = next(n for n in zf.namelist() if n.endswith('.sqlite3'))
            zf.extract(name, t)
            with contextlib.closing(sqlite3.connect(Path(t) / name)) as c:
                self.assertEqual([r[0] for r in c.execute('SELECT company FROM leads')], ['Nord Fiktiv GmbH'])
        backup = create_backup(self.orgs['nord']['db'])['path']
        with connect(self.orgs['sued']['db']) as conn:
            conn.execute("INSERT INTO leads(company) VALUES ('Süd Neu Fiktiv GmbH')")
            conn.commit()
        backup_restore.restore(self.orgs['nord']['db'], backup, confirm=True)
        with connect(self.orgs['sued']['db']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 2, 'Wiederherstellen von Nord ändert Süd nicht')


if __name__ == '__main__':
    unittest.main()
