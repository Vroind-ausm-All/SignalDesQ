"""2.0.0-dev47: Produktreview M30 (Erlebnisstudien) und M34 (Wirkung und Aufwand lernen).

M30: Aufgabenergebnisse, Antworten und Stichprobe getrennt; nur bestätigte Sitzungen zählen („keine KI-Antworten als
Nutzerdaten“); Testpersonen nur mit Kürzel, keine E-Mail/Telefon; Quoten mit Anzahl, Hinweis unter 5 Sitzungen; Vorher/Nachher.
M34: Aufwand je Projektart aus abgeschlossenen Aufträgen, Ergebnisse je Methode, Wirkung vorher/nachher – Aussage erst ab 3 Fällen,
Grenzen sichtbar.
Alle Firmen sind fiktiv; keine Netzabfragen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5_helpers import confirm_need, release_offer  # noqa: E402
from tmpclean import cleanup_tmp  # noqa: E402

from sales_tool import learning  # noqa: E402
from sales_tool import offer_flow as of  # noqa: E402
from sales_tool import postcalc as pc  # noqa: E402
from sales_tool import studies as st  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.sales_workspace import make_proposal  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402


class StudyBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 's.sqlite3')
        prepare_database(self.db)
        self.conn = connect(self.db)
        self.lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES ('Studie Fiktiv GmbH', 'termin')").lastrowid
        self.conn.commit()
        self.n = 1

    def tearDown(self):
        self.conn.close()
        cleanup_tmp(self.tmp)

    def study(self, phase='einmalig', method='moderiert', proposal_id=None, lead=None):
        return st.create(self.conn, {'lead_id': lead or self.lead, 'title': f'Test {phase}', 'phase': phase, 'method': method, 'proposal_id': proposal_id,
                                     'tasks': ['Telefonnummer finden', 'Termin anfragen'], 'questions': ['Was hat gestört?']})

    def session(self, v, outcomes, confirmed=True, answer=''):
        v = st.add_session(self.conn, v['id'], {'device': 'smartphone', 'target_group': 'ja', 'recruited_via': 'Kundenkontakt'})
        sid = v['sessions'][-1]['id']
        tasks = [t for t in v['tasks'] if t['kind'] == 'aufgabe']
        for t, o in zip(tasks, outcomes):
            v = st.record(self.conn, sid, {'task_id': t['id'], 'outcome': o, 'seconds': 40})
        if answer:
            q = next(t for t in v['tasks'] if t['kind'] == 'frage')
            v = st.record(self.conn, sid, {'task_id': q['id'], 'answer': answer})
        if confirmed:
            v = st.record(self.conn, sid, {'confirmed': True})
        return v

    def order(self, hours_factor):
        lead = self.conn.execute("INSERT INTO leads(company, stage) VALUES (?, 'termin')", (f'Auftrag Fiktiv {self.n} GmbH',)).lastrowid
        self.n += 1
        self.conn.commit()
        confirm_need(self.conn, lead)
        p = make_proposal(self.conn, {'lead_id': lead, 'tax_mode': 'regel_19', 'positions': [{'service': 'logo', 'size': 'S'}]})
        release_offer(self.conn, p['id'])
        of.set_status(self.conn, p['id'], {'status': 'gesendet_manuell'})
        of.set_status(self.conn, p['id'], {'status': 'angenommen'})
        card = next(x for x in pc.overview(self.conn)['projects'] if x['proposal_id'] == p['id'])
        pc.add_entry(self.conn, {'proposal_id': p['id'], 'hours': round(card['estimated_hours'] * hours_factor, 2)})
        pc.close_project(self.conn, p['id'], {})
        return p, lead


class StudyTests(StudyBase):
    def test_only_confirmed_sessions_count(self):
        v = self.study()
        self.assertEqual(v['tasks'][0]['pos'], 1)
        v = self.session(v, ['geschafft', 'nicht_geschafft'], answer='Kontaktseite schwer zu finden')
        v = self.session(v, ['mit_hilfe', 'geschafft'])
        v = self.session(v, ['nicht_geschafft', 'nicht_geschafft'], confirmed=False, answer='erfunden')
        a = v['analysis']
        self.assertEqual(a['sample']['sessions'], 2)
        self.assertEqual(a['sample']['unconfirmed'], 1)
        t1, t2 = [t for t in a['tasks'] if t['kind'] == 'aufgabe']
        self.assertEqual((t1['success'], t1['helped'], t1['tried'], t1['success_pct']), (1, 1, 2, 50))
        self.assertEqual((t2['success'], t2['tried']), (1, 2))
        self.assertEqual(t1['median_seconds'], 40)
        self.assertEqual(a['overall_success_pct'], 50)
        answers = next(t for t in a['tasks'] if t['kind'] == 'frage')['answers']
        self.assertEqual(answers, [{'code': 'P1', 'text': 'Kontaktseite schwer zu finden'}], 'unbestätigte Antwort zählt nicht')
        self.assertIn('Erst 2 bestätigte', a['notice'])
        self.assertIn('1 Sitzung(en) ohne Bestätigung', a['notice'])
        self.assertEqual([s['code'] for s in v['sessions']], ['P1', 'P2', 'P3'])

    def test_validation_and_privacy(self):
        with self.assertRaisesRegex(ValueError, 'Mindestens eine Aufgabe'):
            st.create(self.conn, {'lead_id': self.lead, 'title': 'x', 'tasks': [], 'questions': ['?']})
        v = self.study()
        with self.assertRaisesRegex(ValueError, 'anonym'):
            st.add_session(self.conn, v['id'], {'recruited_via': 'max@beispiel.example'})
        v = st.add_session(self.conn, v['id'], {})
        sid = v['sessions'][0]['id']
        q = next(t for t in v['tasks'] if t['kind'] == 'frage')
        with self.assertRaisesRegex(ValueError, 'anonym'):
            st.record(self.conn, sid, {'task_id': q['id'], 'answer': 'ruf mich an: 0711 1234567'})
        with self.assertRaisesRegex(ValueError, 'nur bei Aufgaben'):
            st.record(self.conn, sid, {'task_id': q['id'], 'outcome': 'geschafft'})
        with self.assertRaises(ValueError):
            st.record(self.conn, sid, {'task_id': v['tasks'][0]['id'], 'seconds': -1})
        other = self.study(lead=self.conn.execute("INSERT INTO leads(company) VALUES ('Andere Fiktiv GmbH')").lastrowid)
        with self.assertRaisesRegex(ValueError, 'gehört nicht'):
            st.record(self.conn, sid, {'task_id': other['tasks'][0]['id'], 'outcome': 'geschafft'})
        st.close(self.conn, v['id'])
        with self.assertRaisesRegex(ValueError, 'abgeschlossen'):
            st.record(self.conn, sid, {'confirmed': True})

    def test_before_after_compare(self):
        before = self.study('vorher')
        before = self.session(before, ['nicht_geschafft', 'geschafft'])
        after = self.study('nachher')
        after = self.session(after, ['geschafft', 'geschafft'])
        self.assertEqual(after['compare'], {'study_id': before['id'], 'overall_success_pct': 50, 'sessions': 1})


class LearningTests(StudyBase):
    def test_effort_by_type_from_three_cases(self):
        self.order(1.5)
        self.order(1.5)
        g = next(x for x in learning.overview(self.conn)['effort'] if x['type'] == 'logo')
        self.assertEqual((g['n'], g['enough'], g['avg_variance_pct']), (2, False, None), 'unter 3 Fällen keine Aussage')
        self.order(1.2)
        g = next(x for x in learning.overview(self.conn)['effort'] if x['type'] == 'logo')
        self.assertEqual((g['n'], g['enough'], g['avg_variance_pct']), (3, True, 40))
        self.assertIsNotNone(g['median_hourly'])

    def test_methods_and_before_after_pairs(self):
        for method in ('moderiert', 'moderiert', 'moderiert', 'unmoderiert'):
            self.session(self.study(method=method), ['geschafft', 'nicht_geschafft'])
        o = learning.overview(self.conn)
        m = {x['method']: x for x in o['methods']}
        self.assertEqual((m['moderiert']['studies'], m['moderiert']['avg_success_pct']), (3, 50))
        self.assertEqual((m['unmoderiert']['studies'], m['unmoderiert']['avg_success_pct']), (1, None))
        for _ in range(3):
            p, lead = self.order(1.0)
            self.session(self.study('vorher', lead=lead), ['nicht_geschafft', 'nicht_geschafft'])
            self.session(self.study('nachher', lead=lead, proposal_id=p['id']), ['geschafft', 'nicht_geschafft'])
        ba = {x['type']: x for x in learning.overview(self.conn)['before_after']}
        self.assertEqual((ba['logo']['pairs'], ba['logo']['avg_delta_points']), (3, 50))
        self.assertTrue(o['limits'])


if __name__ == '__main__':
    unittest.main()
