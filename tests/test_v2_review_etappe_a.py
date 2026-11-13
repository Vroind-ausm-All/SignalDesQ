"""2.0.0-dev13: Produktreview vom 13.11.2026, Etappe A (M01, M03, M04, M05) – Teil ohne Browser.

Abnahme:
- M04/T02: Eine neue Firma bekommt weder eine Branche noch eine Leistung, die niemand gewählt hat – über das Formular,
  die Schnittstelle, den CSV-Import, „Bericht für Website“ und die Übernahme aus der Firmensuche. Leer ist erlaubt,
  unbekannte Werte nicht. Bestehende Daten bleiben unverändert.
- M04: Liste und Pipeline zeigen die Passung statt der alten Punktzahl; der alte Lead-Fit bleibt nur eingeklappt sichtbar.
- U08/B05: Ein leerer Schritt im Tagesplan heißt „nichts offen“, nicht „erledigt“.
- U11/B06: Der Gesprächsentwurf behauptet keinen Anlass und keine Leistung, die nicht dokumentiert ist.
- M01/M03: Der Schutz ungespeicherter Eingaben ist eingebunden (Verhalten im Browser-Test test_formguard_browser).
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_sprintB_sweep as tb  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import report, sweep as sw  # noqa: E402
from sales_tool import today as td  # noqa: E402
from sales_tool.model import connect, init_db, score_lead  # noqa: E402
from sales_tool.server import import_leads, make_handler, prepare_database  # noqa: E402

PUBLIC = Path(__file__).resolve().parent.parent / 'sales_tool' / 'public'


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'api.sqlite3')
        prepare_database(self.db)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        cleanup_tmp(self.tmp)

    def call(self, method, path, body=None):
        c = HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'} if body is not None else {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, json.loads(data) if data else None

    def test_new_lead_only_with_name_has_no_invented_values(self):
        st, lead = self.call('POST', '/api/leads', {'company': 'Probe Architekten'})
        self.assertEqual(st, 201)
        self.assertEqual((lead['industry'], lead['offer']), ('', ''))
        st, lead = self.call('POST', '/api/leads', {'company': 'Leer Formular', 'industry': '', 'offer': ''})
        self.assertEqual((st, lead['industry'], lead['offer']), (201, '', ''))
        # bewusste Wahl bleibt möglich, Unsinn nicht
        st, _ = self.call('PATCH', f"/api/leads/{lead['id']}", {'industry': 'B2B-SaaS', 'offer': 'portal'})
        self.assertEqual(st, 200)
        self.assertEqual(self.call('PATCH', f"/api/leads/{lead['id']}", {'offer': 'erfunden'})[0], 400)
        self.assertEqual(self.call('PATCH', f"/api/leads/{lead['id']}", {'stage': ''})[0], 400)  # Phase bleibt Pflicht
        st, _ = self.call('PATCH', f"/api/leads/{lead['id']}", {'industry': '', 'offer': ''})
        self.assertEqual(st, 200)


class CreationPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / 't.sqlite3'))
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_csv_import_and_website_report_stay_neutral(self):
        res = import_leads(self.conn, {'rows': [{'company': 'Import Fiktiv GmbH', 'website': 'https://import.example'}]})
        self.assertEqual(res['imported'], 1)
        row = self.conn.execute("SELECT industry, offer FROM leads WHERE company='Import Fiktiv GmbH'").fetchone()
        self.assertEqual(tuple(row), ('', ''))
        lid, created = report.lead_for_url(self.conn, 'https://bericht-fiktiv.example')
        self.assertTrue(created)
        self.assertEqual(tuple(self.conn.execute('SELECT industry, offer FROM leads WHERE id=?', (lid,)).fetchone()), ('', ''))

    def test_existing_data_untouched_and_old_score_tolerates_empty(self):
        self.conn.execute("INSERT INTO leads(company, industry, offer) VALUES ('Alt Fiktiv KG', 'Sonstige', 'conversion')")
        self.assertEqual(tuple(self.conn.execute("SELECT industry, offer FROM leads WHERE company='Alt Fiktiv KG'").fetchone()), ('Sonstige', 'conversion'))
        score, reasons = score_lead({'company': 'Nur Name', 'industry': '', 'offer': ''})
        self.assertEqual(score, 0)
        self.assertIn('Branchen-Fit +0', reasons)

    def test_empty_day_plan_says_nothing_open_not_done(self):
        view = td.today_view(self.conn)
        states = {s['key']: s['state'] for s in view['plan']['steps']}
        self.assertEqual(states['finden'], 'offen')
        self.assertTrue(all(v == 'nichts_offen' for k, v in states.items() if k != 'finden'), states)
        self.assertFalse(any(v == 'erledigt' for v in states.values()))


class QuoteConsistencyTests(unittest.TestCase):
    """Prüffall K01 aus dem Review: Positionsumfang und allgemeine Korrekturrunden dürfen sich nicht widersprechen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(str(Path(self.tmp.name) / 'q.sqlite3'))
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def test_logo_basis_has_no_contradicting_flat_revision_count(self):
        from sales_tool import pricing as pr
        from sales_tool.sales_workspace import customer_markdown
        q = pr.build_quote(self.conn, {'positions': [{'service': 'logo', 'size': 'S'}]})
        cust = q['customer']
        self.assertIn('1 Korrekturschleife', cust['positions'][0]['scope'])
        self.assertIsNone(cust['revision_rounds'])
        lines = [x for x in customer_markdown(cust).splitlines() if x.startswith('- Korrekturschleifen')]
        # 2.0.0-dev16: die Angaben je Position werden eindeutig zusammengeführt
        self.assertEqual(lines, ['- Korrekturschleifen: Pos. 1 Logogestaltung: 1 Korrekturschleife'])
        self.assertNotIn('Korrekturschleifen: 2', customer_markdown(cust))
        # ältere Angebote mit fester Zahl (bis dev12) und mit Sammelhinweis (dev13–dev15) bleiben lesbar
        self.assertIn('- Korrekturschleifen: 2', customer_markdown({**cust, 'revision_rounds': 2}))
        old = {k: v for k, v in cust.items() if k != 'revisions'}
        self.assertIn('- Korrekturschleifen: je Leistung wie im Umfang angegeben',
                      customer_markdown({**old, 'revision_note': 'je Leistung wie im Umfang angegeben'}))


class AdoptionTests(tb.SweepBase):
    def test_adopted_search_result_has_no_preselected_offer(self):
        self.run_sweep(sources=['osm'], industries=[], operative=False)
        cid = next(c['id'] for c in self.cands(status='alle') if c['name'] == 'Bäckerei Kornfeld')
        lid = sw.decide(self.conn, cid, 'uebernehmen', self.db)['lead_id']
        row = self.conn.execute('SELECT industry, offer, stage FROM leads WHERE id=?', (lid,)).fetchone()
        self.assertEqual((row['industry'], row['offer'], row['stage']), ('', '', 'recherche'))


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.app = (PUBLIC / 'app.js').read_text(encoding='utf-8')
        self.html = (PUBLIC / 'index.html').read_text(encoding='utf-8')

    def test_fit_replaces_old_score_in_lists(self):
        render = self.app[self.app.index('function renderLeads()'):self.app.index('\n', self.app.index('function renderLeads()'))]
        self.assertNotIn('/100', render)
        self.assertIn('leadGradeCell', render)
        self.assertIn('leadGradeRank', render)
        self.assertIn('<th>PASSUNG</th>', self.html)
        self.assertNotIn('<th>PRIORITÄT</th><th> </th></tr></thead><tbody id="leadRows">', self.html)
        self.assertIn('<details class="legacy-score">', self.html)
        self.assertNotIn('${l.score}', (PUBLIC / 'pipeline.js').read_text(encoding='utf-8'))
        assessment = (PUBLIC / 'assessment.js').read_text(encoding='utf-8')
        self.assertIn("window.gradeLabel = g => (GRADE[g] ? GRADE[g][2] : 'Datenlage unzureichend');", assessment)
        self.assertIn('window.gradeLabel(grade)', (PUBLIC / 'akte.js').read_text(encoding='utf-8'))

    def test_neutral_defaults_in_form(self):
        self.assertIn("form.elements.industry.value='';", self.app)
        self.assertIn("form.elements.offer.value=offer||'';", self.app)
        self.assertIn("opt('','– unbekannt –')", self.app)
        self.assertIn("opt('','– noch keine Leistung gewählt –')", self.app)

    def test_draft_claims_nothing_undocumented(self):
        draft = self.app[self.app.index('function renderDraft(l)'):self.app.index('\n', self.app.index('function renderDraft(l)'))]
        self.assertNotIn("'folgende Veränderung aufgefallen: '+signal", draft)
        self.assertIn("l.signal_type!=='kein_signal'", draft)
        self.assertIn('noch keiner dokumentiert', draft)
        self.assertIn('noch nicht gewählt', draft)

    def test_close_paths_go_through_the_guard(self):
        for needle in ("$('#closeModal').addEventListener('click',()=>requestCloseModal())",
                       "$('#cancelLead').addEventListener('click',()=>requestCloseModal())",
                       "if(e.target.id==='modal')requestCloseModal()",
                       "window.leadGuard.dialogOpen())return window.leadGuard.cancel()",
                       "window.leadGuard.onClose()", "window.leadGuard.afterOpen(!!id)"):
            self.assertIn(needle, self.app)
        self.assertIn('id="lfGuard"', self.html)
        self.assertIn('<script src="/formguard.js" defer></script>', self.html)
        guard = (PUBLIC / 'formguard.js').read_text(encoding='utf-8')
        self.assertNotIn('localStorage', guard)  # Entwürfe nur im Arbeitsspeicher
        self.assertIn("data-guard", self.html)
        for choice in ('save', 'edit', 'discard'):
            self.assertIn(f'data-guard="{choice}"', self.html)

    def test_texts_match_current_behaviour(self):
        self.assertNotIn('ohne Personendaten, ohne Kontaktversand', self.html)
        self.assertNotIn('Jede offene Firma hat einen nächsten Schritt', (PUBLIC / 'workday.js').read_text(encoding='utf-8'))
        today = (PUBLIC / 'today.js').read_text(encoding='utf-8')
        self.assertNotIn('von ${p.steps.length} erledigt', today)


if __name__ == '__main__':
    unittest.main()
