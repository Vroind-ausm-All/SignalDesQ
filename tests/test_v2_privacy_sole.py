"""2.0.0-dev10: Datenschutz für Betriebe ohne Rechtsform.

Abnahme:
- Jede Übernahme eines Betriebs ohne Rechtsform legt einen Nachweis mit Zweck, Rechtsgrundlage, Quelle und Löschfrist an
  (einmal je Lead; auch bei der Sammelübernahme). Firmen mit Rechtsform bekommen keinen.
- Der Hinweistext nach Art. 14 passt zum Betrieb (nicht zum Ansprechpartner).
- Nach Ablauf der Frist wird der Betrieb gelöscht – außer bei Kunden und laufenden Gesprächen. Eine Sperre bleibt bestehen,
  und der Betrieb darf bei einer späteren Suche wieder auftauchen.
- Verlängern nur mit Grund. Bestand wird beim Update nachgezogen.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import datetime as dt
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import company_data as cd  # noqa: E402
from sales_tool import quality, sweep as sw  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import SCHEMA_VERSION, prepare_database  # noqa: E402


class SoleBase(tb.SweepBase):
    def adopt(self, name):
        cid = next(c['id'] for c in self.cands(status='alle') if c['name'] == name)
        return sw.decide(self.conn, cid, 'uebernehmen', self.db)['lead_id']

    def records(self, lid=None):
        q = "SELECT * FROM privacy_records WHERE kind='einzelunternehmen'" + (' AND lead_id=?' if lid else '')
        return self.conn.execute(q, (lid,) if lid else ()).fetchall()

    def expire(self, rid):
        self.conn.execute("UPDATE privacy_records SET retention_until='2020-01-01' WHERE id=?", (rid,))
        self.conn.commit()


class RecordTests(SoleBase):
    def test_adoption_creates_one_record_only_for_sole_businesses(self):
        self.run_sweep(sources=['osm'], industries=[], operative=False)
        lid = self.adopt('Bäckerei Kornfeld')
        rec = self.records(lid)
        self.assertEqual(len(rec), 1)
        rec = rec[0]
        self.assertIsNone(rec['contact_id'])
        self.assertIn('Art. 6 Abs. 1 lit. f', rec['legal_basis'])
        self.assertIn('Personenname', rec['data_categories'])
        self.assertTrue(rec['source_url'].startswith('https://www.openstreetmap.org/'))
        days = (dt.date.fromisoformat(rec['retention_until']) - dt.date.today()).days
        self.assertEqual(days, cd.RETENTION_DAYS_PERSON)
        gmbh = self.adopt('Elektro Sommer GmbH')
        self.assertEqual(self.records(gmbh), [])
        self.assertIsNone(cd.add_sole_record(self.conn, lid, 'Bäckerei Kornfeld'))  # einmal je Lead

    def test_bulk_adoption_also_creates_records(self):
        d = self.run_sweep(sources=['gleif', 'osm'], industries=[], operative=False)
        sw.bulk_all(self.conn, {'filter': {'sweep_id': str(d['id']), 'sole': '1'}, 'decision': 'uebernehmen'}, self.db)
        sole_leads = self.conn.execute("SELECT COUNT(*) FROM discovery_candidates WHERE status='uebernommen' AND legal_form=''").fetchone()[0]
        self.assertGreaterEqual(sole_leads, 1)
        self.assertEqual(len(self.records()), sole_leads)

    def test_art14_text_fits_a_business(self):
        self.run_sweep(sources=['osm'], industries=[])
        rid = self.records(self.adopt('Bäckerei Kornfeld'))[0]['id']
        text = cd.art14_text(self.conn, rid)['text']
        self.assertIn('Namen und die Geschäftsanschrift Ihres Betriebs', text)
        self.assertIn('Art. 21 DSGVO', text)
        self.assertNotIn('berufliche Funktion', text)

    def test_extend_needs_a_reason_and_appends_it(self):
        self.run_sweep(sources=['osm'], industries=[])
        rec = self.records(self.adopt('Bäckerei Kornfeld'))[0]
        for bad in ({'months': 12}, {'months': 12, 'reason': 'ok'}, {'months': 0, 'reason': 'Gespräch vereinbart'},
                    {'months': 40, 'reason': 'Gespräch vereinbart'}, {'months': 12, 'reason': 'Gespräch vereinbart', 'x': 1}):
            with self.assertRaises(ValueError, msg=bad):
                cd.extend_retention(self.conn, rec['id'], bad)
        r = cd.extend_retention(self.conn, rec['id'], {'months': 12, 'reason': 'Gespräch am 12.11. vereinbart'})
        self.assertGreater(r['retention_until'], rec['retention_until'])
        self.assertIn('Gespräch am 12.11. vereinbart', self.conn.execute('SELECT note FROM privacy_records WHERE id=?', (rec['id'],)).fetchone()[0])


class ErasureTests(SoleBase):
    def test_expired_business_is_deleted_and_may_reappear_later(self):
        d = self.run_sweep(sources=['osm'], industries=[])
        lid = self.adopt('Bäckerei Kornfeld')
        self.conn.execute("INSERT INTO tasks(lead_id, title, due_date) VALUES (?, 'Anrufen', '2026-12-01')", (lid,))
        rec = self.records(lid)[0]
        with self.assertRaises(ValueError):
            quality.erase_expired_person(self.conn, rec['id'], {'confirm': True})  # Frist noch nicht abgelaufen
        self.expire(rec['id'])
        r = quality.erase_expired_person(self.conn, rec['id'], {'confirm': True})
        self.assertEqual(r['deleted_lead'], lid)
        self.assertIsNone(self.conn.execute('SELECT 1 FROM leads WHERE id=?', (lid,)).fetchone())
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tasks WHERE lead_id=?', (lid,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM discovery_candidates WHERE name='Bäckerei Kornfeld'").fetchone()[0], 0)
        log = self.conn.execute("SELECT detail FROM audit_log WHERE action='einzelunternehmen_geloescht'").fetchone()[0]
        self.assertNotIn('Kornfeld', log)  # Löschnachweis ohne Personendaten
        # keine Sperre: eine spätere Suche darf den Betrieb neu finden
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM suppression_list').fetchone()[0], 0)
        sw.run_sweep(self.db, sw.start_sweep(self.conn, {'place': '70173', 'radius_km': 30, 'sources': ['osm'], 'osm_online': True}, self.db, start=False)['id'])
        self.assertIn('Bäckerei Kornfeld', {c['name'] for c in self.cands(status='neu')})
        del d

    def test_customers_and_ongoing_talks_are_not_deleted(self):
        self.run_sweep(sources=['osm'], industries=[])
        lid = self.adopt('Bäckerei Kornfeld')
        rid = self.records(lid)[0]['id']
        self.expire(rid)
        for stage in ('antwort', 'termin', 'angebot', 'gewonnen'):
            self.conn.execute('UPDATE leads SET stage=? WHERE id=?', (stage, lid))
            with self.assertRaises(ValueError, msg=stage):
                quality.erase_expired_person(self.conn, rid, {'confirm': True})
        self.assertTrue(self.conn.execute('SELECT 1 FROM leads WHERE id=?', (lid,)).fetchone())

    def test_lock_survives_deletion(self):
        self.run_sweep(sources=['osm'], industries=[])
        lid = self.adopt('Bäckerei Kornfeld')
        self.conn.execute("UPDATE leads SET stage='gesperrt', permission='nicht_kontaktieren' WHERE id=?", (lid,))
        rid = self.records(lid)[0]['id']
        self.expire(rid)
        quality.erase_expired_person(self.conn, rid, {'confirm': True})
        self.assertTrue(cd.check_suppressed(self.conn, name='Bäckerei Kornfeld'))  # Widerspruch gilt weiter


class BackfillTests(unittest.TestCase):
    def test_existing_sole_leads_get_records_on_upgrade(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            db = str(Path(tmp.name) / 'alt.sqlite3')
            prepare_database(db)
            with connect(db) as c:
                run = c.execute("INSERT INTO discovery_runs(source, params_json) VALUES ('osm', '{}')").lastrowid
                for name, legal in (('Malerbetrieb Beispiel', ''), ('Elektro Fiktiv GmbH', 'GmbH')):
                    lid = c.execute("INSERT INTO leads(company, legal_form, created_at) VALUES (?, ?, '2025-01-10 09:00:00')", (name, legal)).lastrowid
                    c.execute("INSERT INTO discovery_candidates(run_id, source, name, lead_id, status, source_url) VALUES (?, 'osm', ?, ?, 'uebernommen', 'https://www.openstreetmap.org/node/1')", (run, name, lid))
                c.execute("INSERT INTO leads(company) VALUES ('Selbst eingetragen')")  # nicht aus der Firmensuche: kein Nachweis
                c.execute('PRAGMA user_version = 28')
                c.commit()
            prepare_database(db)
            with connect(db) as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                rows = c.execute("SELECT subject, collected_at, retention_until FROM privacy_records WHERE kind='einzelunternehmen'").fetchall()
                self.assertEqual([(r['subject'], r['collected_at'][:10], r['retention_until']) for r in rows],
                                 [('Malerbetrieb Beispiel', '2025-01-10', (dt.date(2025, 1, 10) + dt.timedelta(days=cd.RETENTION_DAYS_PERSON)).isoformat())])
            prepare_database(db)  # zweiter Start: nichts doppelt
            with connect(db) as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM privacy_records WHERE kind='einzelunternehmen'").fetchone()[0], 1)
        finally:
            cleanup_tmp(tmp)

    def test_old_privacy_records_keep_working(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            db = str(Path(tmp.name) / 'p.sqlite3')
            prepare_database(db)
            with connect(db) as c:
                cols = {r[1] for r in c.execute('PRAGMA table_info(privacy_records)')}
                self.assertIn('kind', cols)
                lid = c.execute("INSERT INTO leads(company) VALUES ('X GmbH')").lastrowid
                rid = cd.add_privacy_record(c, lid, None, 'Frau Beispiel', 'https://x.example/impressum')
                self.assertEqual(c.execute('SELECT kind FROM privacy_records WHERE id=?', (rid,)).fetchone()[0], 'person')
                self.assertIn('berufliche Funktion', cd.art14_text(c, rid)['text'])
        finally:
            cleanup_tmp(tmp)


if __name__ == '__main__':
    unittest.main()
