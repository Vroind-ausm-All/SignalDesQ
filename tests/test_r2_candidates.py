"""R2.4 Kandidaten-Sichtung getrennt vom CRM: Status, Frist, Sperren, Löschung, Export, Migration. Nur erfundene Daten."""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from sales_tool import candidates as cd
from sales_tool.company_data import add_suppression, suppress_lead
from sales_tool.model import connect, init_db
from sales_tool.public_contacts import extract_public_contacts
from sales_tool.server import SCHEMA_VERSION, prepare_database

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

URL = 'https://beispiel-technik.example/team'
RAW = ('Geschäftsführerin: Anna Beispiel\nMarketingleitung: Max Muster, max.muster@beispiel-technik.example\n'
       'IT-Leitung: Carla Meyer')


def people(raw=RAW):
    return extract_public_contacts({'pages': [{'url': URL, 'raw_text': raw}]})['people']


class CandidateBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 't.sqlite3')
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def lead(self, company='Beispiel Technik GmbH', website='https://beispiel-technik.example', **kw):
        cols = {'company': company, 'website': website, **kw}
        lid = self.conn.execute(f"INSERT INTO leads({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(cols.values())).lastrowid
        run = self.conn.execute("INSERT INTO contact_research_runs(lead_id, status) VALUES (?, 'done')", (lid,)).lastrowid
        return lid, run

    def crm(self, lid):
        return self.conn.execute('SELECT COUNT(*) FROM decision_contacts WHERE lead_id=?', (lid,)).fetchone()[0]

    def cands(self, lid):
        return {r['full_name']: dict(r) for r in self.conn.execute('SELECT * FROM contact_candidates WHERE lead_id=?', (lid,))}


class StoreAndReviewTests(CandidateBase):
    def test_store_sets_status_ttl_evidence_and_never_crm(self):
        lid, run = self.lead()
        res = cd.store_all(self.conn, run, lid, people())
        self.assertEqual(res['stored'], 3)
        rows = self.cands(lid)
        self.assertEqual({r['status'] for r in rows.values()}, {'kandidat'})
        self.assertEqual(self.crm(lid), 0)  # kein Kandidat gelangt ohne Freigabe ins CRM
        r = rows['Max Muster']
        self.assertEqual(r['department'], 'Marketing')
        self.assertEqual(r['role_key'], 'marketing_leitung')
        ev = json.loads(r['evidence_json'])
        self.assertEqual(cd.evidence_problems({'evidence_refs': ev['refs']}), [])
        expires = dt.datetime.strptime(r['expires_at'], '%Y-%m-%d %H:%M:%S')
        created = dt.datetime.strptime(r['created_at'], '%Y-%m-%d %H:%M:%S')
        self.assertEqual((expires - created).days, cd.DEFAULT_TTL_DAYS)
        # zweiter Lauf legt keine Dubletten an
        self.assertEqual(cd.store_all(self.conn, run, lid, people())['stored'], 0)

    def test_candidate_without_locator_is_rejected(self):
        lid, run = self.lead()
        p = dict(people()[0])
        p['evidence_refs'] = {'full_name': {**p['evidence_refs']['full_name'], 'locator': {}}, 'job_title': p['evidence_refs']['job_title']}
        cid, why = cd.store(self.conn, run, lid, p)
        self.assertIsNone(cid)
        self.assertIn('ohne Fundstelle', why)
        self.assertIsNone(cd.store(self.conn, run, lid, {'full_name': 'Anna Beispiel', 'job_title': 'CEO', 'evidence': 'x'})[0])

    def test_accept_creates_crm_contact_with_evidence_only_on_human_decision(self):
        lid, run = self.lead()
        cd.store_all(self.conn, run, lid, people())
        cid = self.cands(lid)['Anna Beispiel']['id']
        self.assertEqual(cd.review(self.conn, cid, 'accept'), {'status': 'bestaetigt'})
        c = self.conn.execute('SELECT * FROM decision_contacts WHERE lead_id=?', (lid,)).fetchone()
        self.assertEqual(c['full_name'], 'Anna Beispiel')
        self.assertEqual(c['decision_role'], 'unbekannt')  # Rolle ist keine Entscheidungsbefugnis
        self.assertEqual(c['verification_status'], 'ungeprueft')
        self.assertTrue(json.loads(c['evidence_json'])['refs'])
        with self.assertRaises(ValueError):
            cd.review(self.conn, cid, 'accept')  # bereits bearbeitet
        other = self.cands(lid)['Carla Meyer']['id']
        self.assertEqual(cd.review(self.conn, other, 'historic')['status'], 'historisch')
        self.assertEqual(self.crm(lid), 1)

    def test_locked_company_gets_no_candidates_and_no_acceptance(self):
        lid, run = self.lead()
        cd.store_all(self.conn, run, lid, people())
        cid = self.cands(lid)['Anna Beispiel']['id']
        # Sperre über die Sperrliste (nicht nur Phase) blockiert die Übernahme
        self.conn.execute('INSERT INTO suppression_list(kind, value, display, reason) VALUES (?,?,?,?)',
                          ('domain', 'beispiel-technik.example', 'beispiel-technik.example', 'Widerspruch'))
        with self.assertRaises(ValueError):
            cd.review(self.conn, cid, 'accept')
        self.assertEqual(self.crm(lid), 0)
        lid2, run2 = self.lead('Gesperrt Beispiel AG', 'https://gesperrt.example', stage='gesperrt', permission='nicht_kontaktieren')
        self.assertEqual(cd.store_all(self.conn, run2, lid2, people())['stored'], 0)
        self.assertEqual(self.cands(lid2), {})

    def test_new_suppression_reaches_existing_candidates(self):
        lid, run = self.lead()
        lid_b, run_b = self.lead('Zweite Firma GmbH', 'https://zweite.example')
        cd.store_all(self.conn, run, lid, people())
        cd.store_all(self.conn, run_b, lid_b, extract_public_contacts({'pages': [{'url': 'https://zweite.example/team',
                                                                                  'raw_text': 'Geschäftsführer: Paul Probe'}]})['people'])
        add_suppression(self.conn, 'email', 'max.muster@beispiel-technik.example', 'Widerspruch der Person')
        self.assertNotIn('Max Muster', self.cands(lid))       # gesperrte E-Mail-Adresse
        self.assertIn('Anna Beispiel', self.cands(lid))
        add_suppression(self.conn, 'domain', 'https://beispiel-technik.example', 'Widerspruch der Firma')
        self.assertEqual(self.cands(lid), {})                 # gesperrte Firma: alle Kandidaten gelöscht
        self.assertIn('Paul Probe', self.cands(lid_b))        # andere Firma unberührt
        self.conn.execute("UPDATE leads SET stage='gesperrt', permission='nicht_kontaktieren' WHERE id=?", (lid_b,))
        suppress_lead(self.conn, lid_b)
        self.assertEqual(self.cands(lid_b), {})

    def test_employer_conflict_is_contradictory_and_needs_confirmation(self):
        lid, run = self.lead()
        p = dict(people()[0])
        p['employer'] = 'Ganz Andere Holding AG'
        cid, status = cd.store(self.conn, run, lid, p)
        self.assertEqual(status, 'widerspruechlich')
        with self.assertRaises(ValueError):
            cd.review(self.conn, cid, 'accept')
        self.assertEqual(cd.review(self.conn, cid, 'accept', confirm_conflict=True)['status'], 'bestaetigt')
        p2 = dict(people()[1])
        p2['employer'] = 'Beispiel Technik'
        self.assertEqual(cd.store(self.conn, run, lid, p2)[1], 'kandidat')

    def test_ttl_expiry_deletes(self):
        lid, run = self.lead()
        cd.store_all(self.conn, run, lid, people())
        self.assertEqual(cd.purge_expired(self.conn), 0)
        later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=cd.DEFAULT_TTL_DAYS + 1)
        self.assertEqual(cd.purge_expired(self.conn, now=later), 3)
        self.assertEqual(self.cands(lid), {})
        with self.assertRaises(ValueError):
            cd.set_ttl_days(self.conn, 5)
        cd.set_ttl_days(self.conn, 60)
        self.assertEqual(cd.ttl_days(self.conn), 60)

    def test_deleting_crm_person_reaches_candidate(self):
        lid, run = self.lead()
        cd.store_all(self.conn, run, lid, people())
        self.assertEqual(cd.purge_person(self.conn, lid, 'anna beispiel'), 1)
        self.assertNotIn('Anna Beispiel', self.cands(lid))

    def test_export_map_lists_candidates(self):
        from sales_tool import data_map
        self.assertIn('contact_candidates', Path(data_map.__file__).read_text(encoding='utf-8'))

    def test_legacy_candidate_without_v2_evidence_cannot_be_accepted(self):
        lid, run = self.lead()
        cid = self.conn.execute("INSERT INTO contact_candidates(run_id, lead_id, full_name, job_title, source_url, status) VALUES (?,?,?,?,?, 'ungeprueft')",
                                (run, lid, 'Alt Bestand', 'Geschäftsführer', URL)).lastrowid
        with self.assertRaises(ValueError) as cm:
            cd.review(self.conn, cid, 'accept')
        self.assertIn('Fundstelle', str(cm.exception))
        self.assertEqual(cd.review(self.conn, cid, 'reject')['status'], 'verworfen')
        self.assertEqual(self.crm(lid), 0)


class MigrationTests(unittest.TestCase):
    def test_v1_6_candidates_are_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'alt.sqlite3')
            raw = sqlite3.connect(db)
            raw.executescript((Path(__file__).parent / 'fixtures' / 'migration' / 'v1_6.sql').read_text(encoding='utf-8'))
            run = raw.execute("INSERT INTO contact_research_runs(lead_id, status) VALUES (1, 'done')").lastrowid
            for name, status in (('Erika Alt', 'ungeprueft'), ('Paul Alt', 'freigegeben'), ('Lena Alt', 'abgelehnt')):
                raw.execute('INSERT INTO contact_candidates(run_id, lead_id, full_name, job_title, source_url, status) VALUES (?,?,?,?,?,?)',
                            (run, 1, name, 'Geschäftsführung', 'https://altbestand-maschinenbau.example/team', status))
            raw.commit()
            raw.close()
            prepare_database(db)
            with connect(db) as conn:
                self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                got = {r['full_name']: r for r in conn.execute('SELECT * FROM contact_candidates')}
                self.assertEqual({k: v['status'] for k, v in got.items()},
                                 {'Erika Alt': 'kandidat', 'Paul Alt': 'bestaetigt', 'Lena Alt': 'verworfen'})
                self.assertTrue(all(v['expires_at'] for v in got.values()))
                cols = {r[1] for r in conn.execute('PRAGMA table_info(decision_contacts)')}
                self.assertIn('evidence_json', cols)
            prepare_database(db)  # zweimal migrieren ändert nichts
            with connect(db) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM contact_candidates').fetchone()[0], 3)


if __name__ == '__main__':
    unittest.main()
