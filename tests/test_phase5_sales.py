"""Phase 5 – Sales-Integration: Angebots-Matching, Entscheider v3, Sales Action Center.

Alle Firmen, Personen und Aussagen sind fiktiv; keine Netzwerkzugriffe.
"""
import datetime as dt
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sales_tool import sales_integration as si
from sales_tool.model import connect, init_db
from sales_tool.sales_workspace import PACKAGES, customer_markdown, quote_preview
from sales_tool.server import make_handler

TODAY = dt.date.today()

FULL_DISCOVERY = {
    'problem': 'Aufträge werden heute aus E-Mails manuell in Excel abgetippt und doppelt im Warenwirtschaftssystem erfasst.',
    'impact': 'Laut Vertriebsinnendienst rund zwei Stunden Zeitaufwand pro Tag, dazu fehleranfällige Übertragungen.',
    'current_solution': 'Excel-Liste und Copy-and-paste ins ERP.',
    'desired_outcome': 'Aufträge sollen ohne Medienbruch digital im ERP landen; Erfassungszeit halbieren.',
    'timing': 'Bis Ende Q2 2027',
    'decision_process': 'Leitung Innendienst prüft fachlich, Geschäftsführung gibt frei.',
}


class SalesBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'si.sqlite3'
        self.conn = connect(self.db)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def lead(self, company='Fiktiv Antriebstechnik GmbH', **extra):
        data = {'company': company, 'website': 'https://fiktiv-antrieb.example', 'industry': 'Industrie & B2B-Technik', 'employees': 90, **extra}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid

    def discovery(self, lead_id, **fields):
        data = {**fields}
        cols = ['lead_id', *data]
        self.conn.execute(f"INSERT OR REPLACE INTO discovery ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", (lead_id, *data.values()))
        self.conn.commit()

    def hypothesis(self, lead_id, theme='process', offers=('automation',)):
        self.conn.execute("""INSERT INTO signal_correlations(lead_id, theme, hypothesis, strength, score, signal_ids_json, counter_json,
                             contradictions_json, missing_json, questions_json, offers_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (lead_id, theme, 'Mögliche Prozesslücke in der Auftragserfassung', 'einzelner Hinweis', 40, '[]', '[]', '[]', '[]', '[]', json.dumps(list(offers))))
        self.conn.commit()

    def contact(self, lead_id, name='Erika Beispiel', title='Leitung Operations', status='ungeprueft', **extra):
        data = {'lead_id': lead_id, 'full_name': name, 'job_title': title, 'verification_status': status, 'source_url': 'https://fiktiv-antrieb.example/team', **extra}
        cur = self.conn.execute(f"INSERT INTO decision_contacts ({','.join(data)}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        self.conn.commit()
        return cur.lastrowid


class OfferMatchingTests(SalesBase):
    def test_hints_only_are_unverbindlich(self):
        lid = self.lead()
        self.hypothesis(lid)
        out = si.match_offers(self.conn, lid)
        self.assertFalse(out['discovery']['complete'])
        rec = next(r for r in out['recommendations'] if r['package'] == 'automation')
        self.assertEqual(rec['status'], 'unverbindlich')
        self.assertEqual(rec['confirmed'], [])
        self.assertTrue(rec['hints'])
        self.assertIn('unverbindlich', out['notice'])
        with self.assertRaises(ValueError):
            si.quote_draft(self.conn, rec['id'])

    def test_incomplete_discovery_keeps_confirmed_quotes_unverbindlich(self):
        lid = self.lead()
        self.discovery(lid, problem=FULL_DISCOVERY['problem'])
        rec = si.match_offers(self.conn, lid)['recommendations'][0]
        self.assertEqual(rec['package'], 'automation')
        self.assertTrue(rec['confirmed'])
        self.assertEqual(rec['status'], 'unverbindlich')

    def test_complete_discovery_makes_offer_basis_with_literal_quotes(self):
        lid = self.lead()
        self.hypothesis(lid, theme='web', offers=('conversion',))
        self.discovery(lid, **FULL_DISCOVERY)
        out = si.match_offers(self.conn, lid)
        top = out['recommendations'][0]
        self.assertEqual(top['package'], 'automation')
        self.assertEqual(top['status'], 'angebotsgrundlage')
        for q in top['confirmed']:  # Zitate stammen wörtlich aus der Bedarfsanalyse
            self.assertTrue(any(q['quote'].strip('…')[:20] in v for v in FULL_DISCOVERY.values()), q)
        conv = next(r for r in out['recommendations'] if r['package'] == 'conversion')
        self.assertEqual(conv['status'], 'unverbindlich', 'Nur Recherche-Hinweis, keine Kundenaussage')
        draft = si.quote_draft(self.conn, top['id'])
        self.assertEqual(draft['package'], 'automation')
        self.assertEqual(draft['customer_goal'], FULL_DISCOVERY['desired_outcome'])
        self.assertIn('Q2 2027', draft['assumptions'])
        stored = si.stored_recommendations(self.conn, lid)
        self.assertEqual([r['package'] for r in stored], [r['package'] for r in out['recommendations']])

    def test_budget_note_and_no_invented_matches(self):
        lid = self.lead()
        self.discovery(lid, **FULL_DISCOVERY, budget_status='kein_budget')
        rec = si.match_offers(self.conn, lid)['recommendations'][0]
        self.assertTrue(any('Budget' in n for n in rec['notes']))
        empty = self.lead('Ohne Daten GmbH')
        self.assertEqual(si.match_offers(self.conn, empty)['recommendations'], [])

    def test_automation_package_in_customer_document(self):
        self.assertIn('automation', PACKAGES)
        prev = quote_preview({'package': 'automation', 'tax_mode': 'regel_19'})
        md = customer_markdown(prev['customer'])
        for section in ('## Liefergegenstände', '## Abnahmekriterien', '## Mögliche Drittanbieter- und Folgekosten'):
            self.assertIn(section, md)
        self.assertGreaterEqual(prev['customer']['net_eur'], PACKAGES['automation']['minimum_eur'])
        self.assertNotIn('estimated_hours', prev['customer'])
        for internal in ('cost_rate', 'Deckungsbeitrag', 'Stunden', 'risk'):
            self.assertNotIn(internal, md)


class DecisionMakerTests(SalesBase):
    def test_role_map_and_gaps(self):
        lid = self.lead(offer='automation')
        self.contact(lid, title='Leitung Operations', status='quelle_geprueft')
        d = si.decision_map(self.conn, lid)
        self.assertIn('process', d['topics'])
        ops = next(r for r in d['roles'] if r['role'] == 'Operations')
        self.assertFalse(ops['gap'])
        it = next(r for r in d['roles'] if r['role'] == 'IT')
        self.assertTrue(it['gap'])

    def test_confirmation_requires_verified_source(self):
        lid = self.lead()
        cid = self.contact(lid)
        with self.assertRaises(ValueError):
            si.update_contact_roles(self.conn, cid, {'role_fachlich': 'bestaetigt'})
        self.assertEqual(si.update_contact_roles(self.conn, cid, {'role_fachlich': 'vermutet'})['roles']['fachlich'], 'vermutet')
        self.conn.execute("UPDATE decision_contacts SET verification_status='quelle_geprueft' WHERE id=?", (cid,))
        self.assertEqual(si.update_contact_roles(self.conn, cid, {'role_budget': 'bestaetigt'})['roles']['budget'], 'bestaetigt')
        with self.assertRaises(ValueError):  # finale Entscheidung nur nach bestätigter Rolle
            si.update_contact_roles(self.conn, cid, {'role_entscheidung': 'bestaetigt'})
        self.conn.execute("UPDATE decision_contacts SET verification_status='rolle_bestaetigt' WHERE id=?", (cid,))
        self.assertEqual(si.update_contact_roles(self.conn, cid, {'role_entscheidung': 'bestaetigt'})['roles']['entscheidung'], 'bestaetigt')
        with self.assertRaises(ValueError):
            si.update_contact_roles(self.conn, cid, {'role_budget': 'sicher'})
        with self.assertRaises(ValueError):
            si.update_contact_roles(self.conn, cid, {'email': 'x@y.de'})

    def test_business_channel_rules(self):
        lid = self.lead(business_phone='+49 711 1234560', business_email='info@fiktiv-antrieb.example')
        cid = self.contact(lid)
        src = 'https://fiktiv-antrieb.example/team'
        with self.assertRaises(ValueError):  # Firmennummer ist keine Durchwahl
            si.update_contact_roles(self.conn, cid, {'business_channel': '0711 1234560', 'business_channel_kind': 'telefon', 'business_channel_source': src})
        with self.assertRaises(ValueError):  # allgemeine Adresse
            si.update_contact_roles(self.conn, cid, {'business_channel': 'kontakt@fiktiv-antrieb.example', 'business_channel_kind': 'email', 'business_channel_source': src})
        with self.assertRaises(ValueError):  # Quelle fehlt
            si.update_contact_roles(self.conn, cid, {'business_channel': 'e.beispiel@fiktiv-antrieb.example', 'business_channel_kind': 'email'})
        with self.assertRaises(ValueError):  # Art fehlt
            si.update_contact_roles(self.conn, cid, {'business_channel': 'e.beispiel@fiktiv-antrieb.example', 'business_channel_source': src})
        c = si.update_contact_roles(self.conn, cid, {'business_channel': 'e.beispiel@fiktiv-antrieb.example', 'business_channel_kind': 'email', 'business_channel_source': src})
        self.assertEqual(c['business_channel_kind'], 'email')

    def test_objection_suppresses_and_rejects_open_tasks(self):
        lid = self.lead(permission='opt_in', permission_evidence='Opt-in per Formular am 02.11.2026')
        cid = self.contact(lid)
        si.update_contact_roles(self.conn, cid, {'business_channel': 'e.beispiel@fiktiv-antrieb.example', 'business_channel_kind': 'email',
                                                 'business_channel_source': 'https://fiktiv-antrieb.example/team'})
        tid = self.conn.execute("INSERT INTO tasks(lead_id, title, contact_id, permission_status, channel) VALUES (?, 'Erstkontakt', ?, 'freigegeben', 'email')", (lid, cid)).lastrowid
        self.conn.commit()
        si.update_contact_roles(self.conn, cid, {'contact_restrictions': ['widerspruch']})
        self.assertEqual(self.conn.execute('SELECT permission_status FROM tasks WHERE id=?', (tid,)).fetchone()[0], 'abgelehnt')
        self.assertTrue(self.conn.execute("SELECT 1 FROM suppression_list WHERE kind='email' AND value LIKE 'e.beispiel@%'").fetchone())
        with self.assertRaises(ValueError):
            si.update_contact_roles(self.conn, cid, {'contact_restrictions': ['gar_nicht']})


class ActionCenterTests(SalesBase):
    def test_suggestions_from_research_and_dedupe(self):
        lid = self.lead()
        self.hypothesis(lid)
        cid = self.contact(lid)
        keys = {a['key'] for a in si.suggest_actions(self.conn, lid)}
        self.assertIn(f'verify:{cid}', keys)
        self.assertIn('bedarfsfrage', keys)
        self.assertIn('empfehlung', keys)
        self.assertFalse(any(k.startswith('erstkontakt') for k in keys), 'ohne Rechtsstatus keine Kontaktaktion')
        r = si.accept_suggestion(self.conn, {'lead_id': lid, 'key': 'bedarfsfrage'})
        self.assertFalse(r['requires_permission'])
        keys2 = {a['key'] for a in si.suggest_actions(self.conn, lid)}
        self.assertNotIn('bedarfsfrage', keys2, 'offene Aufgabe wird nicht erneut vorgeschlagen')
        si.dismiss_suggestion(self.conn, {'lead_id': lid, 'key': 'empfehlung'})
        self.assertNotIn('empfehlung', {a['key'] for a in si.suggest_actions(self.conn, lid)})
        with self.assertRaises(ValueError):
            si.accept_suggestion(self.conn, {'lead_id': lid, 'key': 'empfehlung'})

    def test_blocked_or_suppressed_leads_get_no_suggestions(self):
        lid = self.lead(stage='gesperrt')
        self.hypothesis(lid)
        self.assertEqual(si.suggest_actions(self.conn, lid), [])
        lid2 = self.lead('Widerspruch AG', permission='nicht_kontaktieren')
        self.hypothesis(lid2)
        self.assertEqual(si.suggest_actions(self.conn, lid2), [])

    def test_offer_and_followup_suggestions(self):
        lid = self.lead(permission='opt_in', permission_evidence='Opt-in per Formular am 02.11.2026')
        self.discovery(lid, **FULL_DISCOVERY)
        si.match_offers(self.conn, lid)
        keys = {a['key'] for a in si.suggest_actions(self.conn, lid)}
        self.assertIn('angebot:automation', keys)
        self.assertIn('erstkontakt:email', keys)
        self.conn.execute("INSERT INTO proposals(lead_id, status, internal_json, customer_json, updated_at) VALUES (?, 'gesendet_manuell', '{}', '{}', datetime('now','-10 day'))", (lid,))
        self.conn.commit()
        acts = {a['key']: a for a in si.suggest_actions(self.conn, lid)}
        self.assertNotIn('angebot:automation', acts)
        fu = next(a for k, a in acts.items() if k.startswith('followup:'))
        self.assertTrue(fu['requires_permission'])

    def contact_task(self, lid, **lead_update):
        if lead_update:
            self.conn.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in lead_update)} WHERE id=?", (*lead_update.values(), lid))
        self.hypothesis(lid)
        key = next(a['key'] for a in si.suggest_actions(self.conn, lid) if a['action_type'] == 'erstkontakt')
        r = si.accept_suggestion(self.conn, {'lead_id': lid, 'key': key})
        self.assertTrue(r['requires_permission'])
        return r['task_id']

    def test_permission_rules_per_channel(self):
        lid = self.lead()
        tid = self.contact_task(lid, permission='telefon_einzelfall', permission_evidence='Rückruf auf Messe am 28.10.2026 erbeten')
        self.assertFalse(si.can_complete_task(self.conn, tid)[0])
        basis = 'Rückrufbitte auf Messe am 28.10.2026, Visitenkarte liegt vor'
        with self.assertRaises(ValueError):  # Begründung zu knapp
            si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'telefon', 'basis': 'ok'})
        with self.assertRaises(ValueError):  # E-Mail ohne Opt-in
            si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'email', 'basis': basis})
        with self.assertRaises(ValueError):  # persönlich ohne dokumentierten Weg
            si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'persoenlich', 'basis': basis})
        r = si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'telefon', 'basis': basis})
        self.assertEqual(r['permission_status'], 'freigegeben')
        self.assertIn('keine Kontaktaktion aus', r['notice'])
        self.assertTrue(si.can_complete_task(self.conn, tid)[0])
        self.assertTrue(self.conn.execute("SELECT 1 FROM audit_log WHERE entity='task' AND entity_id=? AND action='kontakt_freigegeben'", (tid,)).fetchone())

    def test_person_restrictions_block_channel(self):
        lid = self.lead()
        cid = self.contact(lid, status='quelle_geprueft')
        self.conn.execute("UPDATE leads SET permission='telefon_einzelfall', permission_evidence='Rückrufbitte per Kontaktformular vom 01.11.2026' WHERE id=?", (lid,))
        tid = self.conn.execute("INSERT INTO tasks(lead_id, title, contact_id, permission_status, channel) VALUES (?, 'Anruf', ?, 'zu_pruefen', 'telefon')", (lid, cid)).lastrowid
        si.update_contact_roles(self.conn, cid, {'contact_restrictions': ['kein_telefon']})
        with self.assertRaises(ValueError) as err:
            si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'telefon', 'basis': 'Rückrufbitte per Kontaktformular vom 01.11.2026'})
        self.assertIn('Keine Anrufe', str(err.exception))
        self.assertEqual(si.review_permission(self.conn, tid, {'decision': 'ablehnen', 'basis': 'Person wünscht keine Anrufe'})['permission_status'], 'abgelehnt')
        self.assertFalse(si.can_complete_task(self.conn, tid)[0])

    def test_blocked_lead_cannot_be_released(self):
        lid = self.lead()
        tid = self.contact_task(lid, permission='opt_in', permission_evidence='Opt-in per Formular am 02.11.2026')
        self.conn.execute("UPDATE leads SET stage='gesperrt' WHERE id=?", (lid,))
        with self.assertRaises(ValueError):
            si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'email', 'basis': 'Opt-in per Formular am 02.11.2026'})


class SalesHttpTests(SalesBase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except HTTPError as err:
            return err.code, json.loads(err.read())

    def test_endpoints_and_completion_block(self):
        lid = self.lead(permission='opt_in', permission_evidence='Opt-in per Formular am 02.11.2026')
        self.discovery(lid, **FULL_DISCOVERY)
        cid = self.contact(lid)
        status, out = self.call(f'/api/leads/{lid}/offer-matching', 'POST', {})
        self.assertEqual(status, 200)
        rec = out['recommendations'][0]
        self.assertEqual(rec['status'], 'angebotsgrundlage')
        status, stored = self.call(f'/api/leads/{lid}/offer-matching')
        self.assertEqual((status, len(stored['recommendations'])), (200, len(out['recommendations'])))
        self.assertEqual(self.call(f"/api/offer-recommendations/{rec['id']}/quote-draft")[0], 200)
        self.assertEqual(self.call(f'/api/leads/{lid}/decision-map')[0], 200)
        self.assertEqual(self.call(f'/api/contacts/{cid}/roles', 'PATCH', {'role_fachlich': 'bestaetigt'})[0], 400)
        self.assertEqual(self.call(f'/api/contacts/{cid}/roles', 'PATCH', {'role_fachlich': 'vermutet'})[0], 200)
        status, sugg = self.call(f'/api/leads/{lid}/action-suggestions')
        self.assertEqual(status, 200)
        self.assertEqual(self.call('/api/action-suggestions')[0], 200)
        status, acc = self.call('/api/action-suggestions/accept', 'POST', {'lead_id': lid, 'key': 'erstkontakt:email'})
        self.assertEqual(status, 201)
        tid = acc['task_id']
        status, err = self.call(f'/api/tasks/{tid}', 'PATCH', {'done': True})
        self.assertEqual(status, 409)
        self.assertIn('freigegeben', err['error'])
        self.assertEqual(self.call(f'/api/tasks/{tid}/permission', 'POST', {'decision': 'freigeben', 'channel': 'email', 'basis': 'Opt-in per Formular am 02.11.2026'})[0], 200)
        self.assertEqual(self.call(f'/api/tasks/{tid}', 'PATCH', {'done': True})[0], 200)
        self.assertEqual(self.call('/api/action-suggestions/dismiss', 'POST', {'lead_id': lid, 'key': 'bedarfsfrage'})[0], 200)
        self.assertEqual(self.call('/api/action-suggestions/accept', 'POST', {'lead_id': 'x', 'key': 'a'})[0], 400)
        self.assertEqual(self.call('/api/offer-recommendations/9999/quote-draft')[0], 404)
        status, ws = self.call('/api/workspace')
        self.assertEqual(status, 200)
        self.assertTrue(all('permission_status' in t for t in ws['tasks']))
        with urlopen(self.base + '/salesint.js') as resp:
            self.assertEqual(resp.status, 200)


if __name__ == '__main__':
    unittest.main()
