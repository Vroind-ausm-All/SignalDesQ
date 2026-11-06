"""Masterplan 2.0 – Sprint 5: geführter Arbeitstag, CRM und Angebote.

Abnahme laut Plan: Ein Nutzer führt den kompletten Beispieltag von Recherche bis Angebotsentwurf ohne Sackgasse durch;
Kontaktsperren und alle manuell erforderlichen Freigaben greifen. Abnahmeablauf (Abschnitt 12): Profil auswählen →
Session starten → Ergebnisliste öffnen → Originalsite öffnen → Gesamtbericht prüfen → Kontaktstatus dokumentieren →
Firma im CRM → Gespräch/Termin (manuell) → bestätigter Bedarf → Festpreisangebot → Wiedervorlage → Tagesabschluss.
Alle Firmen und Webseiten sind fiktiv, es gibt keine Netzabfragen.
"""
import datetime as dt
import json
import sys
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402
import test_sprintC_report as tc  # noqa: E402

from sales_tool import profiles as pf  # noqa: E402
from sales_tool import report as rp  # noqa: E402
from sales_tool import sweep as sw  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool import workday as wd  # noqa: E402
from sales_tool.company_data import add_suppression, remove_suppression  # noqa: E402
from sales_tool.server import make_handler  # noqa: E402

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()


class DayBase(tb.SweepBase):
    """Sammelsuche (Attrappen-Netz aus Sprint B) + Firmen-Bericht (Attrappen-Website aus Sprint C) + HTTP-Server."""

    def setUp(self):
        super().setUp()
        self.rp = tc.ReportBase()
        self.rp.patches = [p for p in (tc.mock.patch.object(tc.imprint, 'FETCH', tc.FakeWeb()), tc.mock.patch.object(tc.imprint, 'SLEEP', lambda s: None),
                                       tc.mock.patch.object(tc.wa, 'public_url', lambda u: u), tc.mock.patch.object(tc.wa, 'robots_allowed', lambda u: True),
                                       tc.mock.patch.object(tc.ws, 'playwright_available', lambda: False),
                                       tc.mock.patch.object(tc.ws, 'CAPTURE_FALLBACK', lambda url: tc.capture(renderer='html')),
                                       tc.mock.patch.dict(sys.modules, {'playwright': None, 'playwright.sync_api': None}))]
        for p in self.rp.patches:
            p.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for p in reversed(self.rp.patches):
            p.stop()
        super().tearDown()

    def call(self, method, path, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=20)
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json'} if body is not None else {})
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b'{}'))
        c.close()
        return out

    def ok(self, method, path, body=None, status=(200, 201, 202)):
        st, data = self.call(method, path, body)
        self.assertIn(st, status, (path, data))
        return data

    def file(self, lid):
        return self.ok('GET', f'/api/leads/{lid}/file')

    def lead(self, company='Testfirma GmbH', **kw):
        cols = {'company': company, **kw}
        cur = self.conn.execute(f"INSERT INTO leads ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(cols.values()))
        self.conn.commit()
        return cur.lastrowid


class ExampleDayTests(DayBase):
    def test_example_day_from_profile_to_offer_without_dead_end(self):
        nexts = []
        # 1 Profil auswählen → Session starten (mit sichtbarem Budget)
        prof = self.ok('POST', '/api/search-profiles', {'name': 'Stuttgart Kabel 30 km', 'params': {'place': '70173', 'radius_km': 30, 'sources': ['gleif']},
                                                        'budget': {'max_companies': 50, 'max_websites': 0, 'max_minutes': 20}})
        self.assertIn('Budget 50 Firmen', prof['summary'])
        run = pf.start_profile(self.conn, prof['id'], self.db, start=False)
        sw.run_sweep(self.db, run['id'])
        detail = sw.sweep_detail(self.conn, run['id'])
        self.assertEqual(detail['progress']['gleif']['status'], 'fertig')
        self.assertEqual(detail['progress']['_budget']['max_companies'], 50)
        self.assertEqual(self.ok('GET', '/api/search-profiles')['profiles'][0]['runs'], 1)
        # 2 Ergebnisliste öffnen → 3 Originalquelle öffnen (Link in neuem Tab, Quelle je Treffer)
        items = self.ok('GET', f"/api/sweep-candidates?status=neu&sweep_id={run['id']}")['items']
        reith = next(c for c in items if c['name'] == 'Reith Spezialkabel GmbH')
        self.assertTrue(reith['sources'][0]['url'].startswith('https://'))
        # Firma im CRM
        lid = self.ok('POST', f"/api/sweep-candidates/{reith['id']}/decision", {'decision': 'uebernehmen'})['lead_id']
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertEqual(f['next']['step'], 'recherche')
        self.assertIn('fund', [e['kind'] for e in f['timeline']])
        # 4 Gesamtbericht prüfen (Website der Firma eingetragen; Bericht in einem Klick)
        self.ok('PATCH', f'/api/leads/{lid}', {'website': tc.SITE})
        rp.create_reports(self.conn, {'lead_ids': [lid]}, self.db, start=False)
        rp._worker(self.db)
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertTrue(f['steps'][0]['done'], f['steps'][0])
        self.assertGreater(f['coverage']['pct'], 0)
        self.assertEqual(f['next']['step'], 'kontaktweg')
        # Freigaben greifen: ohne Gespräch kein bestätigter Bedarf, ohne Bedarf kein Angebot „beim Kunden“
        st, err = self.call('POST', f'/api/leads/{lid}/quote-from-need', {})
        self.assertEqual(st, 409, err)
        self.ok('PUT', f'/api/leads/{lid}/discovery', {'problem': 'Anfragen nur per Fax', 'desired_outcome': 'Online-Anfragen mit Formular'})
        st, err = self.call('POST', f'/api/leads/{lid}/need/confirm', {'via': 'gespraech', 'note': 'Relaunch gewünscht laut Telefonat',
                                                                       'needs': [{'service': 'webdesign', 'size': 'M'}]})
        self.assertEqual(st, 400)
        self.assertIn('dokumentierten Gespräch', err['error'])
        # 5 Kontaktstatus dokumentieren
        self.ok('PATCH', f'/api/leads/{lid}', {'contact_route': 'netzwerk', 'permission_evidence': 'Empfehlung durch Netzwerkpartner am ' + D(0)})
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertEqual(f['next']['step'], 'gespraech')
        # 6 Gespräch/Termin (manuell dokumentiert)
        self.ok('POST', '/api/workspace/calls', {'lead_id': lid, 'outcome': 'termin_vereinbart', 'notes': 'Termin vor Ort vereinbart'})
        self.assertTrue(self.conn.execute("SELECT 1 FROM tasks WHERE lead_id=? AND title='Vereinbarten Termin eintragen' AND done=0", (lid,)).fetchone())
        m = self.ok('POST', '/api/workspace/meetings', {'lead_id': lid, 'title': 'Bedarfsgespräch', 'starts_at': D(1) + 'T10:00'})
        self.assertFalse(self.conn.execute("SELECT 1 FROM tasks WHERE lead_id=? AND title='Vereinbarten Termin eintragen' AND done=0", (lid,)).fetchone(),
                         'Folgeaufgabe erledigt sich mit dem Termin')
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertEqual(f['lead']['stage'], 'termin')
        self.assertTrue(any('vorbereiten' in t['title'] for t in f['open_tasks']))
        self.ok('PATCH', f"/api/workspace/meetings/{m['id']}", {'status': 'erledigt'})
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertEqual(f['next']['step'], 'bedarf')
        # 7 Bestätigter Bedarf (manuelle Freigabe mit Leistungen aus dem Festpreis-Katalog)
        need = self.ok('POST', f'/api/leads/{lid}/need/confirm', {'via': 'termin', 'note': 'Website-Relaunch mit Anfrageformular und 4 Texten bis März',
                                                                   'needs': [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 4}]})
        self.assertTrue(need['confirmed'])
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertEqual(f['next']['action']['view'], 'quote_from_need')
        self.assertEqual(f['coverage']['items'][-1]['value'], 1.0)
        # 8 Festpreisangebot aus dem bestätigten Bedarf – interne Kalkulation bleibt verborgen
        offer = self.ok('POST', f'/api/leads/{lid}/quote-from-need', {'tax_mode': 'regel_19'})
        pos = offer['customer']['positions']
        self.assertEqual([(p['service'], p['quantity']) for p in pos], [('webdesign', 1), ('texte', 4)])
        self.assertTrue(pos[0]['scope'].startswith('Standard'))
        cust = self.ok('GET', f"/api/workspace/proposals/{offer['id']}/customer")
        blob = json.dumps(cust, ensure_ascii=False)
        for secret in ('hours', 'hourly', 'effective', 'buffer', 'Stundensatz', '€/h', 'need_confirmed_at'):
            self.assertNotIn(secret, blob, secret)
        self.assertIn('need_confirmed_at', self.ok('GET', f"/api/workspace/proposals/{offer['id']}")['internal'])
        self.assertFalse(self.conn.execute("SELECT 1 FROM tasks WHERE lead_id=? AND title LIKE 'Festpreisangebot%' AND done=0", (lid,)).fetchone())
        self.ok('PATCH', f"/api/workspace/proposals/{offer['id']}", {'status': 'gesendet_manuell'})
        f = self.file(lid)
        nexts.append(f['next'])
        self.assertEqual(f['lead']['stage'], 'angebot')
        self.assertTrue(f['steps'][5]['done'])
        # 9 Wiedervorlage: Nachfassen in 7 Tagen
        later = td.wiedervorlage(self.conn, TODAY + dt.timedelta(days=7))
        self.assertTrue(any(i['lead_id'] == lid and i['kind'] in ('aufgabe', 'naechster_schritt', 'nachfassen') for i in later))
        # 10 Tagesabschluss
        day = self.ok('GET', '/api/today/close')
        self.assertGreaterEqual(day['done']['bedarf_bestaetigt'], 1)
        self.assertGreaterEqual(day['done']['angebote'], 1)
        self.assertNotIn(lid, [d['lead_id'] for d in day['dead_ends']])
        closed = self.ok('POST', '/api/today/close', {'note': 'Beispieltag', 'backup': True})
        self.assertTrue(closed['backup_today'])
        self.assertEqual(closed['closed']['note'], 'Beispieltag')
        # ohne Sackgasse: jeder Zwischenstand hatte einen klickbaren nächsten Schritt
        self.assertTrue(all(n['action'] for n in nexts), nexts)
        kinds = {e['kind'] for e in self.file(lid)['timeline']}
        self.assertTrue({'fund', 'bericht', 'anruf', 'termin', 'angebot', 'aktivitaet', 'aufgabe'} <= kinds, kinds)


class LockTests(DayBase):
    def test_suppression_blocks_every_contact_path(self):
        lid = self.lead('Sperrfirma GmbH', website='https://sperrfirma.example', stage='qualifiziert')
        add_suppression(self.conn, 'domain', 'https://sperrfirma.example', 'Widerspruch per Brief')
        self.conn.commit()
        for path, body in (('/api/workspace/calls', {'lead_id': lid, 'outcome': 'erreicht', 'notes': 'x'}),
                           ('/api/workspace/meetings', {'lead_id': lid, 'title': 'T', 'starts_at': D(1) + 'T10:00'}),
                           ('/api/workspace/mail-drafts', {'lead_id': lid, 'draft_type': 'rueckfrage', 'contact_basis': 'Gespräch'}),
                           ('/api/workspace/proposals', {'lead_id': lid, 'package': 'pilot', 'tax_mode': 'regel_19'}),
                           (f'/api/leads/{lid}/need/confirm', {'via': 'schriftlich', 'note': 'Kunde schreibt', 'needs': [{'service': 'logo', 'size': 'S'}]})):
            st, err = self.call('POST', path, body)
            self.assertEqual(st, 409, (path, err))
            self.assertIn('Kontaktsperre', err['error'])
        st, err = self.call('PATCH', f'/api/leads/{lid}', {'stage': 'kontakt'})
        self.assertEqual(st, 409, err)
        # Action Center: keine Kontaktvorschläge, keine Freigabe
        from sales_tool import sales_integration as si
        self.assertEqual(si.suggest_actions(self.conn, lid), [])
        tid = self.conn.execute("INSERT INTO tasks(lead_id, title, permission_status, channel) VALUES (?, 'Erstkontakt', 'zu_pruefen', 'brief')", (lid,)).lastrowid
        self.conn.commit()
        with self.assertRaises(wd.ContactLocked):
            si.review_permission(self.conn, tid, {'decision': 'freigeben', 'channel': 'brief', 'basis': 'Geschäftlicher Brief an die Firmenadresse'})
        # ein Widerspruch lässt sich immer dokumentieren
        self.assertEqual(self.call('POST', '/api/workspace/calls', {'lead_id': lid, 'outcome': 'widerspruch', 'notes': 'nochmals widersprochen'})[0], 201)
        f = self.file(lid)
        self.assertTrue(f['lock'])
        self.assertTrue(f['next']['blocked'])
        self.assertIsNone(f['next']['action'])

    def test_unlock_only_via_suppression_list(self):
        lid = self.lead('Widerspruch GmbH', website='https://widerspruch.example')
        self.ok('POST', '/api/workspace/calls', {'lead_id': lid, 'outcome': 'widerspruch', 'notes': 'keine Werbung'})
        self.assertEqual(self.call('PATCH', f'/api/leads/{lid}', {'permission': 'unbekannt', 'stage': 'qualifiziert'})[0], 409)
        for r in self.conn.execute('SELECT id FROM suppression_list').fetchall():
            remove_suppression(self.conn, r['id'], 'Einwilligung vom 01.11. liegt schriftlich vor')
        lead = self.ok('PATCH', f'/api/leads/{lid}', {'permission': 'opt_in', 'permission_evidence': 'Einwilligung 01.11.', 'stage': 'kontakt'})
        self.assertEqual(lead['stage'], 'kontakt')

    def test_proposal_send_needs_confirmed_need(self):
        lid = self.lead('Angebot GmbH', contact_route='inbound')
        p = self.ok('POST', '/api/workspace/proposals', {'lead_id': lid, 'package': 'pilot', 'tax_mode': 'regel_19'})
        self.assertFalse(p['need_confirmed'])
        for status in ('gesendet_manuell', 'angenommen'):
            st, err = self.call('PATCH', f"/api/workspace/proposals/{p['id']}", {'status': status})
            self.assertEqual(st, 409)
            self.assertIn('Bedarf', err['error'])


class NeedAndGuideTests(DayBase):
    def test_need_validation_and_reopen(self):
        lid = self.lead('Bedarf GmbH')
        self.ok('PUT', f'/api/leads/{lid}/discovery', {'problem': 'Kein Shop', 'desired_outcome': 'Online verkaufen'})
        for needs in ([], [{'service': 'gibtsnicht'}], [{'service': 'webshop', 'size': 'XXL'}], [{'service': 'texte', 'qty': 0}]):
            self.assertEqual(self.call('POST', f'/api/leads/{lid}/need/confirm', {'via': 'schriftlich', 'note': 'Kunde schreibt per Mail', 'needs': needs})[0], 400)
        self.assertEqual(self.call('POST', f'/api/leads/{lid}/need/confirm', {'via': 'schriftlich', 'note': 'kurz', 'needs': [{'service': 'webshop', 'size': 'S'}]})[0], 400)
        n = self.ok('POST', f'/api/leads/{lid}/need/confirm', {'via': 'schriftlich', 'note': 'Kunde bestätigt per E-Mail den Shop', 'needs': [{'service': 'webshop', 'size': 'S'}]})
        self.assertTrue(n['confirmed'])
        self.assertEqual(self.call('POST', f'/api/leads/{lid}/need/reopen', {'reason': ''})[0], 400)
        self.assertFalse(self.ok('POST', f'/api/leads/{lid}/need/reopen', {'reason': 'Kunde will erst Logo'})['confirmed'])
        self.assertEqual(self.call('POST', f'/api/leads/{lid}/quote-from-need', {})[0], 409)

    def test_user_next_step_is_never_overwritten(self):
        lid = self.lead('Eigener Schritt GmbH', next_step='Messe-Kontakt anrufen', next_date=D(3), contact_route='veranstaltung')
        self.ok('POST', '/api/workspace/calls', {'lead_id': lid, 'outcome': 'erreicht', 'notes': 'gut'})
        self.ok('POST', '/api/workspace/meetings', {'lead_id': lid, 'title': 'T', 'starts_at': D(2) + 'T09:00'})
        row = self.conn.execute('SELECT next_step, next_date, stage FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((row['next_step'], row['next_date'], row['stage']), ('Messe-Kontakt anrufen', D(3), 'termin'))

    def test_stage_only_moves_forward_and_followups_once(self):
        lid = self.lead('Vorwärts GmbH', stage='angebot', contact_route='inbound')
        self.ok('POST', '/api/workspace/calls', {'lead_id': lid, 'outcome': 'erreicht', 'notes': 'x'})
        m = self.ok('POST', '/api/workspace/meetings', {'lead_id': lid, 'title': 'T', 'starts_at': D(4) + 'T09:00'})
        self.assertEqual(self.conn.execute('SELECT stage FROM leads WHERE id=?', (lid,)).fetchone()[0], 'angebot')
        for _ in range(2):
            self.ok('PATCH', f"/api/workspace/meetings/{m['id']}", {'status': 'erledigt'})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks WHERE lead_id=? AND title LIKE 'Bedarf aus dem Termin%'", (lid,)).fetchone()[0], 1)

    def test_coverage_counts_only_evidence(self):
        lid = self.lead('Belege GmbH', signal_note='Neue Halle (Hörensagen)')
        c = self.file(lid)['coverage']
        self.assertLess(c['pct'], 20)
        self.assertIn('Anlass/Kaufsignal mit Quelle', c['missing'])
        self.ok('PATCH', f'/api/leads/{lid}', {'signal_source': 'https://presse.example/halle', 'contact_route': 'inbound'})
        c2 = self.file(lid)['coverage']
        self.assertGreater(c2['pct'], c['pct'])
        self.assertNotIn('Anlass/Kaufsignal mit Quelle', c2['missing'])

    def test_day_close_finds_and_fixes_dead_ends(self):
        dead = self.lead('Liegt GmbH', stage='kontakt', contact_route='inbound')
        fine = self.lead('Läuft GmbH', stage='kontakt', next_step='Anrufen', next_date=D(1))
        s = self.ok('GET', '/api/today/close')
        ids = [d['lead_id'] for d in s['dead_ends']]
        self.assertIn(dead, ids)
        self.assertNotIn(fine, ids)
        self.assertEqual(self.call('POST', '/api/today/close', {'followups': [{'lead_id': dead, 'date': 'morgen'}]})[0], 400)
        s = self.ok('POST', '/api/today/close', {'followups': [{'lead_id': dead, 'date': D(2), 'step': 'Rückfrage zum Angebot'}]})
        self.assertNotIn(dead, [d['lead_id'] for d in s['dead_ends']])
        self.assertEqual(self.conn.execute('SELECT next_step FROM leads WHERE id=?', (dead,)).fetchone()[0], 'Rückfrage zum Angebot')
        # gesperrte Firmen sind keine Sackgasse (sie sollen liegen bleiben)
        self.lead('Gesperrt GmbH', stage='kontakt', permission='nicht_kontaktieren')
        self.assertEqual(len(self.ok('GET', '/api/today/close')['dead_ends']), 0)


class ProfileBudgetTests(DayBase):
    def test_profile_crud_and_validation(self):
        base = {'name': 'Ulm', 'params': {'place': '89073', 'radius_km': 10, 'sources': ['gleif'], 'keywords': 'kabel'}}
        p = self.ok('POST', '/api/search-profiles', base)
        self.assertEqual(p['budget'], sw.BUDGET_DEFAULT)
        self.assertEqual(self.call('POST', '/api/search-profiles', base)[0], 400, 'Name eindeutig')
        self.assertEqual(self.call('POST', '/api/search-profiles', {**base, 'name': 'X2', 'budget': {'max_companies': 0}})[0], 400)
        self.assertEqual(self.call('POST', '/api/search-profiles', {**base, 'name': 'X3', 'params': {'place': '89073', 'radius_km': 33}})[0], 400)
        p = self.ok('PUT', f"/api/search-profiles/{p['id']}", {**base, 'budget': {'max_companies': 10, 'max_websites': 5, 'max_minutes': 3}})
        self.assertEqual(p['budget']['max_minutes'], 3)
        self.ok('DELETE', f"/api/search-profiles/{p['id']}")
        self.assertEqual(self.call('POST', f"/api/search-profiles/{p['id']}/start", {})[0], 404)

    def test_company_budget_is_enforced_and_visible(self):
        d = self.run_sweep(sources=['gleif', 'wikidata'], budget={'max_companies': 1, 'max_websites': 0, 'max_minutes': 30})
        self.assertEqual(d['progress']['_budget']['companies'], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM discovery_candidates WHERE sweep_id=? AND status='neu'", (d['id'],)).fetchone()[0], 1)
        self.assertEqual(d['progress']['wikidata']['status'], 'übersprungen')
        self.assertIn('Budget', d['progress']['wikidata']['detail'])

    def test_time_budget_skips_remaining_sources(self):
        s = sw.start_sweep(self.conn, {'place': '70173', 'radius_km': 30, 'sources': ['gleif'], 'budget': {'max_minutes': 1}}, self.db, start=False)
        sw._progress(self.conn, s['id'], '_budget', started=time.time() - 120)
        sw.run_sweep(self.db, s['id'])
        d = sw.sweep_detail(self.conn, s['id'])
        self.assertEqual(d['progress']['gleif']['status'], 'übersprungen')
        self.assertIn('Zeitbudget', d['progress']['gleif']['detail'])


if __name__ == '__main__':
    unittest.main()
