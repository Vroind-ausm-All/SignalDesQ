"""Phase 6 – Qualität & Skalierung: Einstellungen, Veraltung, Änderungserkennung, wiederkehrende Aufträge,
Löschfristen, Login/Rollen, Sicherheitsprüfung, Last-/Fehlertests, Migration und verschlüsselte Sicherung.

Alle Daten sind fiktiv; keine Netzwerkzugriffe (wiederkehrende Aufträge laufen mit start=False bzw. Stubs).
"""
import datetime as dt
import contextlib
import hashlib
import json
import re
import sqlite3
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from sales_tool import auth, backup_crypto, quality as q, research_center as rc
from sales_tool.company_data import add_fact, add_suppression, facts_for_lead
from sales_tool.model import connect, init_db
from sales_tool.server import SCHEMA_VERSION, make_handler, prepare_database

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'migration'
OLD = (dt.date.today() - dt.timedelta(days=500)).isoformat() + ' 10:00:00'
RECENT = (dt.date.today() - dt.timedelta(days=3)).isoformat() + ' 10:00:00'


class QBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'q.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, company='Fiktiv Werkzeugbau GmbH', **extra):
        slug = re.sub(r'[^a-z]', '', company.split()[0].lower())
        data = {'company': company, 'website': f'https://{slug}-beispiel.example', 'industry': 'Industrie & B2B-Technik', 'employees': 60, **extra}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid

    def score(self, lead_id, overall, finished=RECENT, findings=()):
        a = self.conn.execute("INSERT INTO website_audits(lead_id, url, status, finished_at) VALUES (?, 'https://x.example', 'done', ?)", (lead_id, finished)).lastrowid
        vid = self.conn.execute('SELECT id FROM score_versions WHERE active=1').fetchone()[0]
        self.conn.execute("INSERT INTO website_scores(audit_id, lead_id, version_id, overall, potential, coverage, basis_json) VALUES (?,?,?,?,?,80,'{}')",
                          (a, lead_id, vid, overall, overall))
        for rubric, result in findings:
            self.conn.execute("""INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, method, certainty)
                                 VALUES (?,?,?, 'web', ?, ?, 2, 'Beleg', 'dom', 'gemessen')""", (a, lead_id, rubric, rubric.upper(), result))
        self.conn.commit()
        return a

    def batch_item(self, lead_id, domain, fields, status='done'):
        run = self.conn.execute("INSERT INTO batch_runs(label, total) VALUES ('Test', 1)").lastrowid
        result = {'status': 'ok', 'imprint_url': f'https://{domain}/impressum',
                  'fields': {k: {'value': v, 'excerpt': f'{v} (laut Impressum)'} for k, v in fields.items()}}
        cur = self.conn.execute("""INSERT INTO batch_items(run_id, position, input, domain, duplicate_lead_id, status, result_json)
                                   VALUES (?, 1, ?, ?, ?, ?, ?)""", (run, domain, domain, lead_id, status, json.dumps(result)))
        self.conn.commit()
        return cur.lastrowid


# ---------------------------------------------------------------- Einstellungen

class SettingsTests(QBase):
    def test_weights_validation_and_effect(self):
        for bad in ({'website': 50, 'signal': 30, 'fit': 30}, {'website': 0, 'signal': 0, 'fit': 100}, {'website': 50, 'signal': 50},
                    {'website': '40', 'signal': 30, 'fit': 30}, {'website': True, 'signal': 69, 'fit': 30}):
            with self.assertRaises(ValueError):
                q.save_settings(self.conn, {'priority_weights': bad})
        lid = self.lead()
        self.score(lid, 80)
        before = rc.overview(self.conn)['leads'][0]
        self.assertIn('40/30/30', before['priority_basis'])
        q.save_settings(self.conn, {'priority_weights': {'website': 70, 'signal': 20, 'fit': 10}})
        after = rc.overview(self.conn)
        self.assertEqual(after['weights'], {'website': 70, 'signal': 20, 'fit': 10})
        self.assertIn('70/20/10', after['leads'][0]['priority_basis'])
        fit = after['leads'][0]['fit_score']
        self.assertEqual(after['leads'][0]['priority'], round((70 * 80 + 10 * fit) / 80))  # Signale fehlen → Gewichte neu verteilt
        self.assertTrue(self.conn.execute("SELECT 1 FROM audit_log WHERE entity='settings' AND action='geaendert'").fetchone())

    def test_zero_weight_component(self):
        value, basis = rc.research_priority({'website': 70, 'signal': None, 'fit': 50}, None, '', {'website': 0, 'signal': 100, 'fit': 0})
        self.assertIsNone(value)
        self.assertIn('Gewicht 0', basis)

    def test_stale_days_validation(self):
        with self.assertRaises(ValueError):
            q.save_settings(self.conn, {'stale_days': {'imprint': 3}})
        with self.assertRaises(ValueError):
            q.save_settings(self.conn, {'stale_days': {'unbekannt': 30}})
        out = q.save_settings(self.conn, {'stale_days': {'imprint': 30}})
        self.assertEqual(out['stale_days']['imprint'], 30)
        self.assertEqual(out['stale_days']['website'], q.DEFAULT_STALE_DAYS['website'])


# ---------------------------------------------------------------- Veraltung & Löschfristen

class StalenessTests(QBase):
    def test_flags_each_kind_without_changing_data(self):
        lid = self.lead(imprint_checked_at=OLD, legal_name='Fiktiv Werkzeugbau GmbH')
        fid = add_fact(self.conn, lid, 'legal_name', 'Fiktiv Werkzeugbau GmbH', 'impressum_html', 'https://fiktiv.example/impressum', status='bestaetigt')
        self.conn.execute('UPDATE company_facts SET checked_at=? WHERE id=?', (OLD, fid))
        self.score(lid, 60, finished=OLD)
        self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name, job_title, verification_status, updated_at) VALUES (?, 'Pia Beispiel', 'Marketing', 'quelle_geprueft', ?)", (lid, OLD))
        self.conn.execute("INSERT INTO buying_signals(lead_id, kind, category, title, published_at, found_at) VALUES (?, 'job', 'web', 'Alte Stelle', ?, ?)", (lid, OLD[:10], OLD[:10]))
        self.conn.execute("INSERT INTO signal_scans(lead_id, status, finished_at) VALUES (?, 'done', ?)", (lid, OLD))
        fresh = self.lead('Frisch GmbH', imprint_checked_at=RECENT)
        self.lead('Gesperrt GmbH', stage='gesperrt', imprint_checked_at=OLD)
        self.conn.commit()
        rep = q.staleness_report(self.conn)
        kinds = {i['kind'] for l in rep['leads'] if l['lead_id'] == lid for i in l['items']}
        self.assertEqual(kinds, set(q.STALE_LABELS))
        self.assertNotIn(fresh, [l['lead_id'] for l in rep['leads']])
        self.assertEqual(len(rep['leads']), 1, 'gesperrte Leads nicht in der Arbeitsliste')
        facts = facts_for_lead(self.conn, lid)
        self.assertTrue(facts[0]['stale'])
        self.assertEqual(facts[0]['status'], 'bestaetigt', 'Veraltung ändert keinen Prüfstatus')
        self.assertEqual(self.conn.execute('SELECT legal_name FROM leads WHERE id=?', (lid,)).fetchone()[0], 'Fiktiv Werkzeugbau GmbH')
        row = next(r for r in rc.overview(self.conn)['leads'] if r['lead_id'] == lid)
        self.assertTrue(row['stale'])

    def test_missing_data_is_not_stale(self):
        lid = self.lead()
        self.assertEqual(q.lead_staleness(self.conn, self.conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()), [])

    def test_expired_retention_erase(self):
        lid = self.lead()
        cid = self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name, job_title) VALUES (?, 'Ole Altbestand', 'Geschäftsführung')", (lid,)).lastrowid
        past = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        future = (dt.date.today() + dt.timedelta(days=30)).isoformat()
        rid = self.conn.execute("""INSERT INTO privacy_records(lead_id, contact_id, subject, data_categories, purpose, legal_basis, retention_until)
                                   VALUES (?, ?, 'Ole Altbestand', 'Name, Funktion', 'B2B-Akquise', 'Art. 6 Abs. 1 lit. f DSGVO', ?)""", (lid, cid, past)).lastrowid
        keep = self.conn.execute("""INSERT INTO privacy_records(lead_id, subject, data_categories, purpose, legal_basis, retention_until)
                                    VALUES (?, 'Noch gültig', 'Name', 'B2B', 'Art. 6', ?)""", (lid, future)).lastrowid
        tid = self.conn.execute("INSERT INTO tasks(lead_id, title, contact_id) VALUES (?, 'Anruf', ?)", (lid, cid)).lastrowid
        self.conn.commit()
        self.assertEqual([p['id'] for p in q.expired_privacy(self.conn)], [rid])
        with self.assertRaises(ValueError):
            q.erase_expired_person(self.conn, rid, {})
        with self.assertRaises(ValueError):
            q.erase_expired_person(self.conn, keep, {'confirm': True})
        out = q.erase_expired_person(self.conn, rid, {'confirm': True})
        self.assertEqual(out['deleted_contacts'], 1)
        self.assertIsNone(self.conn.execute('SELECT 1 FROM decision_contacts WHERE id=?', (cid,)).fetchone())
        self.assertIsNone(self.conn.execute('SELECT contact_id FROM tasks WHERE id=?', (tid,)).fetchone()[0])
        log = self.conn.execute("SELECT detail FROM audit_log WHERE action='personendaten_geloescht'").fetchone()[0]
        self.assertNotIn('Ole', log, 'Löschnachweis ohne Personendaten')


# ---------------------------------------------------------------- Änderungserkennung

class ChangeTests(QBase):
    def test_imprint_change_detect_and_apply(self):
        lid = self.lead(legal_name='Fiktiv Werkzeugbau GmbH', street='Hafenstraße 1', city='Stuttgart', zip='70173')
        old = add_fact(self.conn, lid, 'street', 'Hafenstraße 1', 'impressum_html', 'https://alt.example/impressum', status='bestaetigt')
        self.batch_item(lid, 'fiktiv-beispiel.example', {'legal_name': 'Fiktiv Werkzeugbau GmbH', 'street': 'Industriering 7', 'city': 'stuttgart', 'zip': '70173'})
        self.batch_item(lid, 'fiktiv-beispiel.example', {'street': 'Hafenstr. 1'})  # nur Schreibweise anders → keine Änderung
        out = q.detect_changes(self.conn)
        self.assertEqual(out['impressum'], 1)
        self.assertEqual(q.detect_changes(self.conn)['impressum'], 0, 'keine Doppelmeldung')
        ev = q.change_rows(self.conn)[0]
        self.assertEqual((ev['field'], ev['old_value'], ev['new_value']), ('street', 'Hafenstraße 1', 'Industriering 7'))
        self.assertTrue(ev['can_apply'])
        self.assertEqual(self.conn.execute('SELECT street FROM leads WHERE id=?', (lid,)).fetchone()[0], 'Hafenstraße 1', 'nichts automatisch übernommen')
        q.decide_change(self.conn, ev['id'], {'decision': 'uebernehmen'})
        self.assertEqual(self.conn.execute('SELECT street FROM leads WHERE id=?', (lid,)).fetchone()[0], 'Industriering 7')
        self.assertEqual(self.conn.execute('SELECT status FROM company_facts WHERE id=?', (old,)).fetchone()[0], 'veraltet')
        self.assertTrue(self.conn.execute("SELECT 1 FROM company_facts WHERE lead_id=? AND field='street' AND value='Industriering 7' AND status='bestaetigt'", (lid,)).fetchone())
        with self.assertRaises(ValueError):
            q.decide_change(self.conn, ev['id'], {'decision': 'ignorieren'})

    def test_website_and_register_changes(self):
        lid = self.lead()
        self.score(lid, 40, finished=OLD, findings=[('b3_cta', 'auffaellig'), ('b1_ssl', 'ok'), ('b2_x', 'unbekannt')])
        self.score(lid, 65, findings=[('b3_cta', 'ok'), ('b1_ssl', 'ok'), ('b2_x', 'ok')])
        self.conn.execute("""INSERT INTO register_events(dedupe_key, lead_id, company, event_type, text, source_url)
                             VALUES ('k1', ?, 'Fiktiv', 'umbenennung', 'Neue Firma: Fiktiv Präzision GmbH', 'https://bekanntmachung.example/1')""", (lid,))
        self.conn.commit()
        out = q.detect_changes(self.conn)
        self.assertEqual((out['website'], out['register']), (2, 1))
        rows = {r['field']: r for r in q.change_rows(self.conn)}
        self.assertIn('B3_CTA: auffaellig → ok', rows['rubriken']['new_value'])
        self.assertNotIn('B2_X', rows['rubriken']['new_value'], 'unbekannt zählt nicht als Änderung')
        self.assertFalse(rows['overall']['can_apply'])
        with self.assertRaises(ValueError):
            q.decide_change(self.conn, rows['overall']['id'], {'decision': 'uebernehmen'})
        q.decide_change(self.conn, rows['overall']['id'], {'decision': 'erledigt'})
        self.assertEqual(len(q.change_rows(self.conn)), 2)
        self.assertEqual(rc.review_queue(self.conn)['items'][-2]['count'], 2)

    def test_blocked_lead_change_not_applied(self):
        lid = self.lead(city='Ulm')
        self.batch_item(lid, 'fiktiv-beispiel.example', {'city': 'Neu-Ulm'})
        q.detect_changes(self.conn)
        self.conn.execute("UPDATE leads SET stage='gesperrt' WHERE id=?", (lid,))
        with self.assertRaises(ValueError):
            q.decide_change(self.conn, q.change_rows(self.conn)[0]['id'], {'decision': 'uebernehmen'})


# ---------------------------------------------------------------- Wiederkehrende Aufträge

class JobTests(QBase):
    def test_career_interval_and_failed_scans(self):
        due = self.lead('Faellig GmbH')
        recent = self.lead('Frisch GmbH')
        failed = self.lead('Fehlerhaft GmbH')
        busy = self.lead('Laufend GmbH')
        for lid, status, days in ((due, 'done', 7), (recent, 'done', 6), (failed, 'failed', 1), (busy, 'running', 20)):
            date = (dt.date.today() - dt.timedelta(days=days)).isoformat()
            self.conn.execute('INSERT INTO signal_scans(lead_id, status, finished_at) VALUES (?,?,?)', (lid, status, date))
        self.conn.commit()
        ids = {r['id'] for r in q.candidates(self.conn, 'karriereseiten_pruefen', 20, career_interval=7)}
        self.assertEqual(ids, {due, failed})

    def test_validation(self):
        for bad in ({'kind': 'spam_versand'}, {'kind': 'impressum_aktualisieren', 'interval_days': 0},
                    {'kind': 'impressum_aktualisieren', 'params': {'limit': 500}}, {'kind': 'lead_finder_suche', 'params': {'source': 'google_maps'}},
                    {'kind': 'impressum_aktualisieren', 'params': {'domains': 'x'}}):
            with self.assertRaises(ValueError, msg=bad):
                q.create_job(self.conn, bad)
        j = q.create_job(self.conn, {'kind': 'datenqualitaet_pruefen', 'interval_days': 7})
        self.assertEqual(j['label'], q.JOB_KINDS['datenqualitaet_pruefen'])
        with self.assertRaises(ValueError):
            q.update_job(self.conn, j['id'], {'kind': 'impressum_aktualisieren'})
        self.assertFalse(q.update_job(self.conn, j['id'], {'enabled': False})['enabled'])
        q.delete_job(self.conn, j['id'])
        with self.assertRaises(LookupError):
            q.delete_job(self.conn, j['id'])

    def test_imprint_job_selects_due_leads_only(self):
        due = self.lead('Nie Geprüft GmbH')
        old = self.lead('Alt Geprüft GmbH', imprint_checked_at=OLD)
        self.lead('Frisch Geprüft GmbH', imprint_checked_at=RECENT)
        self.lead('Gesperrt GmbH', stage='gesperrt')
        self.lead('Widerspruch GmbH', permission='nicht_kontaktieren')
        sup = self.lead('Sperrliste GmbH')
        add_suppression(self.conn, 'domain', 'https://sperrliste-beispiel.example', 'Test', sup)
        self.lead('Ohne Website GmbH', website='')
        j = q.create_job(self.conn, {'kind': 'impressum_aktualisieren', 'interval_days': 30, 'params': {'limit': 10}})
        r = q.run_job(self.conn, j['id'], self.db, start=False)
        self.assertEqual(r['last_status'], 'ok', r['last_detail'])
        domains = {row[0] for row in self.conn.execute('SELECT domain FROM batch_items')}
        self.assertEqual(domains, {'nie-beispiel.example', 'alt-beispiel.example'})
        self.assertGreater(r['next_run_at'], r['last_run_at'])
        self.assertEqual(q.run_job(self.conn, j['id'], self.db, start=False)['last_status'], 'nichts_zu_tun', 'laufende/ungeprüfte Einträge nicht erneut')
        self.assertEqual({due, old}, {row[0] for row in self.conn.execute('SELECT l.id FROM leads l JOIN batch_items b ON b.domain LIKE substr(l.website, 9)')})

    def test_website_and_career_jobs(self):
        stale = self.lead('Alt Bewertet GmbH')
        self.score(stale, 50, finished=OLD)
        fresh = self.lead('Neu Bewertet GmbH')
        self.score(fresh, 50)
        self.lead('Nie Bewertet GmbH')
        j = q.create_job(self.conn, {'kind': 'websites_neu_bewerten', 'params': {'limit': 5}})
        q.run_job(self.conn, j['id'], self.db, start=False)
        queued = [r[0] for r in self.conn.execute("SELECT lead_id FROM website_audits WHERE status='queued'")]
        self.assertEqual(queued, [stale])
        k = q.create_job(self.conn, {'kind': 'karriereseiten_pruefen', 'params': {'limit': 5}})
        self.conn.execute("INSERT INTO signal_scans(lead_id, status, finished_at) VALUES (?, 'done', ?)", (fresh, RECENT))
        self.conn.commit()
        q.run_job(self.conn, k['id'], self.db, start=False)
        scanned = {r[0] for r in self.conn.execute("SELECT lead_id FROM signal_scans WHERE status<>'done'")}
        self.assertEqual(scanned, {stale, self.conn.execute("SELECT id FROM leads WHERE company='Nie Bewertet GmbH'").fetchone()[0]})

    def test_errors_logged_and_due_scheduling(self):
        j = q.create_job(self.conn, {'kind': 'lead_finder_suche', 'params': {'source': 'wikidata', 'place': 'Stuttgart'}})
        with mock.patch('sales_tool.lead_finder.run_search', side_effect=ValueError('Quelle nicht erreichbar (Test)')):
            r = q.run_job(self.conn, j['id'], self.db)
        self.assertEqual((r['last_status'], r['last_detail']), ('fehler', 'Quelle nicht erreichbar (Test)'))
        dq = q.create_job(self.conn, {'kind': 'datenqualitaet_pruefen'})
        self.assertEqual(q.run_due(self.conn, self.db, start=False), [], 'erster Lauf erst nach 5 Minuten')
        later = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        q.update_job(self.conn, j['id'], {'enabled': False})
        ran = q.run_due(self.conn, self.db, start=False, now=later)
        self.assertEqual([x['id'] for x in ran], [dq['id']])
        self.assertIn('Änderung', ran[0]['last_detail'])


# ---------------------------------------------------------------- Login & Rollen

class AuthUnitTests(QBase):
    def setUp(self):
        super().setUp()
        auth._FAILS.clear()

    def test_password_hashing_and_policy(self):
        h = auth.hash_password('Sehr-geheim-2026')
        self.assertTrue(h.startswith('scrypt$'))
        self.assertNotIn('Sehr-geheim', h)
        self.assertTrue(auth.verify_password('Sehr-geheim-2026', h))
        self.assertFalse(auth.verify_password('sehr-geheim-2026', h))
        self.assertFalse(auth.verify_password('x', 'kaputt'))
        for pw in ('kurz', 'aaaaaaaaaaaa', 'anna.admin-2026'):
            with self.assertRaises(ValueError):
                auth.create_user(self.conn, {'username': 'anna.admin', 'password': pw, 'role': 'admin'}, None)

    def test_setup_login_throttle_and_last_admin(self):
        admin = auth.setup_admin(self.conn, {'username': 'anna.admin', 'password': 'Lange-Passphrase-42'})
        with self.assertRaises(PermissionError):
            auth.setup_admin(self.conn, {'username': 'zweite', 'password': 'Lange-Passphrase-42'})
        user, token = auth.login(self.conn, {'username': 'ANNA.admin', 'password': 'Lange-Passphrase-42'})
        self.assertEqual(user['id'], admin['id'])
        self.assertEqual(auth.session_user(self.conn, f'x=1; {auth.COOKIE}={token}')['username'], 'anna.admin')
        stored = self.conn.execute('SELECT token_hash FROM sessions').fetchone()[0]
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest(), 'nur Hash gespeichert')
        for _ in range(auth.MAX_FAILS):
            with self.assertRaises(auth.NotLoggedIn):
                auth.login(self.conn, {'username': 'anna.admin', 'password': 'falsch-falsch-1'})
        with self.assertRaises(auth.Throttled):
            auth.login(self.conn, {'username': 'anna.admin', 'password': 'Lange-Passphrase-42'})
        with self.assertRaises(ValueError):
            auth.update_user(self.conn, admin['id'], {'role': 'lesen'}, dict(admin))
        self.assertTrue(self.conn.execute("SELECT 1 FROM audit_log WHERE action='login_fehlgeschlagen'").fetchone())

    def test_role_matrix(self):
        cases = [
            ('lesen', 'GET', '/api/leads', True), ('lesen', 'POST', '/api/leads', False),
            ('vertrieb', 'POST', '/api/leads', True), ('vertrieb', 'POST', '/api/accounting/invoices', False), ('vertrieb', 'GET', '/api/accounting/overview', True),
            ('buchhaltung', 'POST', '/api/accounting/invoices', True), ('buchhaltung', 'POST', '/api/leads', False),
            ('vertrieb', 'PUT', '/api/quality/settings', False), ('vertrieb', 'POST', '/api/auth/users', False), ('vertrieb', 'POST', '/api/backup', False),
            ('lesen', 'POST', '/api/auth/logout', True), ('admin', 'DELETE', '/api/leads/1', True),
        ]
        for role, method, route, expected in cases:
            self.assertEqual(auth.allowed(role, method, route), expected, (role, method, route))


class HttpBase(QBase):
    hosts = None

    def setUp(self):
        super().setUp()
        auth._FAILS.clear()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db, self.hosts))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, method='GET', body=None, headers=None, raw_body=None):
        c = HTTPConnection('127.0.0.1', self.port, timeout=20)
        h = {'Host': f'127.0.0.1:{self.port}', **(headers or {})}
        data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None and 'Content-Type' not in h:
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        content = r.read()
        c.close()
        try:
            payload = json.loads(content)
        except ValueError:
            payload = content
        return r.status, payload, r


class AuthHttpTests(HttpBase):
    def test_login_flow_and_roles(self):
        self.assertEqual(self.call('/api/leads')[0], 200, 'ohne Login-Pflicht offen (lokaler Einzelplatz)')
        status, _, resp = self.call('/api/auth/setup', 'POST', {'username': 'anna.admin', 'password': 'Lange-Passphrase-42'})
        self.assertEqual(status, 201)
        cookie = resp.getheader('Set-Cookie')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        admin = {'Cookie': cookie.split(';')[0]}
        self.assertEqual(self.call('/api/auth/settings', 'PUT', {'auth_required': True})[0], 403, 'Einschalten nur mit Admin-Sitzung')
        self.assertEqual(self.call('/api/auth/settings', 'PUT', {'auth_required': True}, admin)[0], 200)
        status, body, _ = self.call('/api/leads')
        self.assertEqual((status, body.get('auth_required')), (401, True))
        self.assertEqual(self.call('/')[0], 200, 'Oberfläche (Login-Dialog) bleibt erreichbar')
        self.assertEqual(self.call('/rechnung/1')[0], 401, 'Druckansicht ebenfalls geschützt')
        self.assertEqual(self.call('/api/auth/users', 'POST', {'username': 'lena.lesen', 'password': 'Nur-lesen-Konto-7', 'role': 'lesen'}, admin)[0], 201)
        self.assertEqual(self.call('/api/auth/login', 'POST', {'username': 'lena.lesen', 'password': 'falsch'})[0], 401)
        status, _, resp = self.call('/api/auth/login', 'POST', {'username': 'lena.lesen', 'password': 'Nur-lesen-Konto-7'})
        reader = {'Cookie': resp.getheader('Set-Cookie').split(';')[0]}
        self.assertEqual(self.call('/api/leads', headers=reader)[0], 200)
        self.assertEqual(self.call('/api/leads', 'POST', {'company': 'Neu GmbH'}, reader)[0], 403)
        self.assertEqual(self.call('/api/leads', 'POST', {'company': 'Neu GmbH'}, admin)[0], 201)
        self.assertEqual(self.call('/api/auth/logout', 'POST', {}, reader)[0], 200)
        self.assertEqual(self.call('/api/leads', headers=reader)[0], 401, 'Sitzung nach Abmelden ungültig')
        self.assertEqual(self.call('/api/auth/settings', 'PUT', {'auth_required': False}, admin)[0], 200)


# ---------------------------------------------------------------- Sicherheitsprüfung

def _expand(pattern):
    """Erzeugt konkrete Pfade aus den Routen-Mustern der Module ((\\d+) → 1, Alternativen, optionale Gruppen)."""
    pattern = pattern.replace(r'\.', '.').replace(r'(\d+)', '1').replace('(?:', '(')
    m = re.search(r'\(([^()]*)\)(\?)?', pattern)
    if not m:
        return [pattern] if not re.search(r'[\\\[\]*+^$]', pattern) else []
    alts = m.group(1).split('|') + ([''] if m.group(2) else [])
    out = []
    for a in alts:
        out += _expand(pattern[:m.start()] + a + pattern[m.end():])
    return out


def all_routes():
    paths = set()
    for f in (ROOT / 'sales_tool').glob('*.py'):
        for lit in re.findall(r"""r?['"](/(?:api|rechnung)/[^'"\s]*)['"]""", f.read_text(encoding='utf-8')):
            paths.update(_expand(lit))
    return sorted(p for p in paths if p.startswith(('/api/', '/rechnung/')) and '{' not in p and not p.endswith('/'))


class SecurityTests(HttpBase):
    def test_dns_rebinding_and_headers(self):
        status, body, _ = self.call('/api/leads', headers={'Host': 'angreifer.example:8765'})
        self.assertEqual(status, 421)
        self.assertEqual(self.call('/', headers={'Host': 'angreifer.example'})[0], 421)
        self.assertEqual(self.call('/api/leads', headers={'Host': f'localhost:{self.port}'})[0], 200)
        status, _, resp = self.call('/')
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", resp.getheader('Content-Security-Policy'))
        self.assertNotIn('unsafe-inline', resp.getheader('Content-Security-Policy'))
        self.assertEqual(resp.getheader('X-Frame-Options'), 'DENY')
        self.assertEqual(resp.getheader('Referrer-Policy'), 'no-referrer')
        self.assertEqual(self.call('/api/leads', 'POST', {'company': 'X GmbH'}, {'Origin': 'https://angreifer.example'})[0], 403)
        self.assertEqual(self.call('/api/leads', 'POST', raw_body=b'company=X', headers={'Content-Type': 'application/x-www-form-urlencoded'})[0], 400)
        self.assertEqual(self.call('/api/leads', 'POST', raw_body=b'{}', headers={'Content-Length': '-5'})[0], 400)
        for p in ('/../server.py', '/%2e%2e/server.py', '/public/../../server.py', '/index.html'):
            self.assertEqual(self.call(p)[0], 404, p)

    def test_get_endpoints_have_no_side_effects(self):
        lid = self.lead(legal_name='Fiktiv Werkzeugbau GmbH')
        self.score(lid, 70)
        self.conn.execute("INSERT INTO tasks(lead_id, title) VALUES (?, 'Aufgabe')", (lid,))
        self.conn.commit()
        routes = all_routes()
        self.assertGreater(len(routes), 80, 'Routen-Erkennung unvollständig')

        def digest():
            with contextlib.closing(sqlite3.connect(self.db)) as raw, raw:
                return hashlib.sha256('\n'.join(l for l in raw.iterdump() if 'audit_log' not in l).encode()).hexdigest()
        before = digest()
        statuses = {}
        with mock.patch('sales_tool.server.ollama_health', return_value={'ok': False}):
            for p in routes:
                statuses[p] = self.call(p)[0]
        self.assertEqual(digest(), before, 'GET-Anfragen dürfen nichts verändern (Schutz vor Cross-Site-GET)')
        self.assertFalse({p: s for p, s in statuses.items() if s >= 500}, 'keine Serverfehler')

    def test_malformed_requests_never_500(self):
        routes = all_routes()
        bodies = [None, b'kein json', b'[]', b'{"x": 1}', b'"text"', b'{"lead_id": "1; DROP TABLE leads"}', b'{' * 5000]
        errors = []
        for p in routes:
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                for b in bodies:
                    status = self.call(p, method, raw_body=b if b is not None else b'')[0]
                    if status >= 500:
                        errors.append((method, p, b[:20] if b else b, status))
        self.assertEqual(errors, [])
        self.assertTrue(self.conn.execute("SELECT name FROM sqlite_master WHERE name='leads'").fetchone())
        self.assertEqual(self.call('/api/leads')[0], 200, 'Server läuft weiter')


class ResetLoginTests(QBase):
    def test_emergency_reset(self):
        from sales_tool.server import reset_login
        u = auth.setup_admin(self.conn, {'username': 'anna.admin', 'password': 'Lange-Passphrase-42'})
        auth.set_auth_required(self.conn, {'auth_required': True}, self.conn.execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone())
        auth.create_session(self.conn, u['id'])
        reset_login(self.conn)
        self.assertFalse(auth.auth_required(self.conn))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
        self.assertTrue(self.conn.execute("SELECT 1 FROM audit_log WHERE action='login_pflicht_notfall_aus'").fetchone())


class TeamHostTests(HttpBase):
    hosts = {'signaldesk.firma.intern'}

    def test_allowed_host(self):
        self.assertEqual(self.call('/api/leads', headers={'Host': 'signaldesk.firma.intern'})[0], 200)
        self.assertEqual(self.call('/api/leads', headers={'Host': 'andere.firma.intern'})[0], 421)
        status, body, _ = self.call('/api/system/security', headers={'Host': 'signaldesk.firma.intern'})
        tls = next(c for c in body['checks'] if c['key'] == 'tls')
        self.assertFalse(tls['ok'], 'Hinweis auf fehlendes TLS im Netzwerkbetrieb')


# ---------------------------------------------------------------- Last & Nebenläufigkeit

class LoadTests(HttpBase):
    def test_overview_with_many_leads(self):
        today = dt.date.today().isoformat()
        for i in range(1000):
            lid = self.conn.execute("INSERT INTO leads(company, website, industry, employees, imprint_checked_at) VALUES (?,?,?,?,?)",
                                    (f'Lastfirma {i:04d} GmbH', f'https://last{i}.example', 'Industrie & B2B-Technik', 20 + i % 200, OLD if i % 3 else '')).lastrowid
            if i % 2:
                self.conn.execute("INSERT INTO buying_signals(lead_id, kind, category, title, polarity, published_at, found_at) VALUES (?, 'job', 'web', 'Stelle', 'pro', ?, ?)", (lid, today, today))
            if i % 5 == 0:
                self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name, job_title, verification_status) VALUES (?, 'Person', 'Marketing', 'quelle_geprueft')", (lid,))
        self.conn.commit()
        t = time.perf_counter()
        status, body, _ = self.call('/api/research-center/overview')
        elapsed = time.perf_counter() - t
        self.assertEqual((status, len(body['leads'])), (200, 1000))
        self.assertLess(elapsed, 10, f'Übersicht mit 1000 Firmen dauerte {elapsed:.1f}s')
        for path in ('/api/quality/staleness', '/api/research-center/export.csv', '/api/research-center/review', '/api/action-suggestions'):
            t = time.perf_counter()
            self.assertEqual(self.call(path)[0], 200, path)
            self.assertLess(time.perf_counter() - t, 10, path)

    def test_concurrent_writes_and_reads(self):
        errors = []

        def writer(n):
            for i in range(25):
                s = self.call('/api/leads', 'POST', {'company': f'Parallel {n}-{i} GmbH', 'website': f'https://p{n}-{i}.example'})[0]
                if s != 201:
                    errors.append(('POST', s))

        def reader():
            for _ in range(15):
                s = self.call('/api/research-center/overview')[0]
                if s != 200:
                    errors.append(('GET', s))
        threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)] + [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120)
        self.assertEqual(errors, [])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 200)
        self.assertEqual(self.conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


# ---------------------------------------------------------------- Migration

class MigrationTests(unittest.TestCase):
    def load(self, name, version):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / 'akquise.sqlite3'
        raw = sqlite3.connect(db)
        raw.executescript((FIXTURES / f'{name}.sql').read_text(encoding='utf-8'))
        raw.execute(f'PRAGMA user_version = {version}')
        raw.commit()
        raw.close()
        return db

    def check(self, name, version, has_invoice):
        db = self.load(name, version)
        backup = prepare_database(db)
        self.assertTrue(backup and Path(backup).exists(), 'Sicherung vor der Migration')
        with contextlib.closing(sqlite3.connect(backup)) as b, b:
            self.assertEqual(b.execute('PRAGMA user_version').fetchone()[0], version, 'Sicherung enthält den Altstand')
        conn = connect(db)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(list(conn.execute('PRAGMA foreign_key_check')), [])
        lead = conn.execute("SELECT * FROM leads WHERE company='Altbestand Maschinenbau GmbH'").fetchone()
        self.assertEqual(lead['note'], 'Altdaten-Notiz äöü ß')
        self.assertEqual(lead['permission_evidence'], 'Opt-in per Formular am 01.03.2026')
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 2)
        self.assertEqual(conn.execute("SELECT problem FROM discovery WHERE lead_id=?", (lead['id'],)).fetchone()[0], 'Anfragen kommen nur telefonisch')
        self.assertEqual(conn.execute("SELECT role_fachlich FROM decision_contacts").fetchone()[0], 'unbekannt', 'neue Spalten mit Standardwert')
        for table in ('company_facts', 'suppression_list', 'website_audits', 'buying_signals', 'offer_recommendations', 'change_events', 'recurring_jobs', 'users', 'app_settings'):
            self.assertTrue(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone(), table)
        if has_invoice:
            inv = conn.execute("SELECT * FROM invoices WHERE status<>'entwurf'").fetchone()
            self.assertTrue(inv['number'])
            with self.assertRaises(sqlite3.DatabaseError, msg='GoBD-Schutz bleibt nach Migration aktiv'):
                conn.execute("UPDATE invoices SET buyer_name='Manipuliert' WHERE id=?", (inv['id'],))
        # Programm arbeitet mit der migrierten Datenbank
        self.assertEqual(len(rc.overview(conn)['leads']), 1)
        conn.close()
        self.assertIsNone(prepare_database(db), 'zweiter Start: keine erneute Migration/Sicherung')

    def test_from_v0_9(self):
        self.check('v0_9', 0, has_invoice=False)

    def test_from_v1_2(self):
        self.check('v1_2', 0, has_invoice=True)

    def test_from_v1_6(self):
        self.check('v1_6', 15, has_invoice=True)


# ---------------------------------------------------------------- Verschlüsselte Sicherung

@unittest.skipUnless(backup_crypto.available(), 'cryptography nicht installiert – verschlüsselte Sicherung übersprungen')
class EncryptedBackupTests(QBase):
    def test_roundtrip_and_wrong_password(self):
        self.lead('Geheim GmbH')
        out = backup_crypto.create_encrypted_backup(self.db, {'password': 'Backup-Passwort-2026'})
        blob = Path(out['path']).read_bytes()
        self.assertTrue(blob.startswith(b'SDENC1'))
        self.assertNotIn(b'Geheim GmbH', blob)
        self.assertNotIn(b'SQLite format 3', blob)
        target = Path(self.tmp.name) / 'wieder.sqlite3'
        backup_crypto.decrypt_file(out['path'], target, 'Backup-Passwort-2026')
        with contextlib.closing(sqlite3.connect(target)) as raw, raw:
            self.assertEqual(raw.execute('SELECT company FROM leads').fetchone()[0], 'Geheim GmbH')
        with self.assertRaises(ValueError):
            backup_crypto.decrypt_file(out['path'], Path(self.tmp.name) / 'x.sqlite3', 'falsches-Passwort')
        with self.assertRaises(ValueError):
            backup_crypto.decrypt_file(out['path'], target, 'Backup-Passwort-2026')  # Ziel existiert
        with self.assertRaises(ValueError):
            backup_crypto.create_encrypted_backup(self.db, {'password': 'kurz'})


class EncryptedBackupMissingTests(QBase):
    def test_clear_message_without_package(self):
        with mock.patch.object(backup_crypto, 'available', return_value=False):
            with self.assertRaises(ValueError) as err:
                backup_crypto.create_encrypted_backup(self.db, {'password': 'Backup-Passwort-2026'})
        self.assertIn('requirements-team.txt', str(err.exception))


if __name__ == '__main__':
    unittest.main()
