"""SDQ-006: Recherche-Benchmark – Referenzformat, Zuordnung, Messgrößen, Bericht, Export.

Alle Daten sind fiktiv. Die Tests prüfen das Werkzeug, nicht die Recherchequalität von SignalDesk.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_tool.model import connect  # noqa: E402
from sales_tool.research import benchmark as bm  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402

FIX = ROOT / 'tests' / 'fixtures' / 'research_benchmark'


def load(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def rows(res, qid):
    return {(r['ref_id'], r['cand_id']): r for r in next(d for d in res['details'] if d['id'] == qid)['rows']}


class ValidationTests(unittest.TestCase):
    def test_fixture_and_template_valid(self):
        self.assertEqual(bm.validate_reference(load('reference.json')), [])
        self.assertEqual(bm.validate_run(load('run.json')), [])
        tpl = json.loads((ROOT / 'docs' / 'bench' / 'research' / 'vorlage-referenz.json').read_text(encoding='utf-8'))
        self.assertEqual(bm.validate_reference(tpl), [])
        self.assertTrue(tpl['synthetic'], 'Vorlage darf nie als echte Referenz gelten')

    def test_entry_without_reviewer_date_or_evidence_rejected(self):
        ref = load('reference.json')
        c = ref['queries'][0]['companies'][0]
        del c['checked_by'], c['checked_on']
        c['evidence'] = []
        errs = ' | '.join(bm.validate_reference(ref))
        self.assertIn('checked_by fehlt', errs)
        self.assertIn('checked_on fehlt', errs)
        self.assertIn('evidence fehlt', errs)

    def test_personal_data_fields_rejected(self):
        ref = load('reference.json')
        ref['queries'][0]['companies'][0]['contact_email'] = 'max@example.org'
        run = load('run.json')
        run['queries'][0]['candidates'][0]['contact_name'] = 'Max Muster'
        self.assertTrue(any('contact_email' in e and 'Personendaten' in e for e in bm.validate_reference(ref)))
        self.assertTrue(any('contact_name' in e for e in bm.validate_run(run)))

    def test_bad_status_duplicate_ids_and_complete_flag(self):
        ref = load('reference.json')
        q = ref['queries'][0]
        q['companies'][1]['ref_id'] = 'r1'
        q['companies'][2]['status'] = 'vielleicht'
        del q['complete']
        ref['queries'][1]['id'] = 'q1'
        errs = ' | '.join(bm.validate_reference(ref))
        for part in ('ref_id "r1" doppelt', 'status muss', 'complete muss', 'id "q1" doppelt'):
            self.assertIn(part, errs)

    def test_evaluate_refuses_invalid_files(self):
        with self.assertRaises(ValueError):
            bm.evaluate({'format': 'x'}, load('run.json'))


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.res = bm.evaluate(load('reference.json'), load('run.json'))

    def test_counts_and_rates(self):
        t = self.res['total']['counts']
        self.assertEqual((t['refs_in_scope'], t['found'], t['true_pos']), (5, 8, 4))
        self.assertEqual((t['false_pos_known'], t['duplicates'], t['unmatched'], t['unmatched_judgeable']), (1, 1, 2, 1))
        m = self.res['total']['metrics']
        self.assertEqual(m['recall']['value'], 0.8)
        # q2 nicht abschließend → Gesamtpräzision ist obere Schranke: 4 / (4 + 1 geschlossen + 1 Dublette + 1 sicher falsch)
        self.assertEqual(m['precision_kind'], 'obere_schranke')
        self.assertEqual((m['precision']['k'], m['precision']['n']), (4, 7))
        self.assertEqual((m['precision_lower_bound']['k'], m['precision_lower_bound']['n']), (4, 8))
        q1 = self.res['queries'][0]['metrics']
        self.assertEqual(q1['precision_kind'], 'abschliessend')
        self.assertEqual((q1['precision']['k'], q1['precision']['n']), (3, 6))

    def test_wrong_website_does_not_steer_matching(self):
        """c2 trägt die Website einer anderen Firma: Zuordnung bleibt r2, die Website zählt als falsch."""
        r = rows(self.res, 'q1')
        self.assertEqual(r[('r2', 'c2')]['result'], 'treffer')
        self.assertEqual(r[('r2', 'c2')]['website'], 'falsch')
        self.assertEqual(r[('r1', 'c1')]['website'], 'richtig', 'https://www. und Schrägstrich egal')
        w = self.res['total']['metrics']['website']
        self.assertEqual((w['wrong_assignment_rate']['k'], w['wrong_assignment_rate']['n']), (1, 3))

    def test_platform_page_is_no_website(self):
        self.assertEqual(rows(self.res, 'q1')[('r3', 'c3')]['website'], 'richtig_leer')

    def test_closed_duplicate_missing_and_unjudgeable(self):
        r1, r2 = rows(self.res, 'q1'), rows(self.res, 'q2')
        self.assertEqual(r1[('r5', 'c5')]['result'], 'falsch_geschlossen')
        self.assertEqual(r1[('', 'c4')]['result'], 'dublette')
        self.assertEqual(r1[('r4', '')]['result'], 'nicht_gefunden')
        self.assertEqual(r1[('', 'c6')]['result'], 'falsch_gefunden')
        self.assertEqual(r2[('', 'd2')]['result'], 'nicht_beurteilbar', 'offene Liste: nicht als falsch werten')

    def test_different_register_never_matches(self):
        ref, run = load('reference.json'), load('run.json')
        run['queries'][0]['candidates'][0]['register_id'] = 'HRB 9999'
        run['queries'][0]['candidates'] = run['queries'][0]['candidates'][:1]
        res = bm.evaluate(ref, run)
        self.assertEqual(rows(res, 'q1')[('r1', '')]['result'], 'nicht_gefunden')

    def test_unchecked_fields_are_not_scored(self):
        ref, run = load('reference.json'), load('run.json')
        del ref['queries'][0]['companies'][1]['website']
        res = bm.evaluate(ref, run)
        self.assertEqual(rows(res, 'q1')[('r2', 'c2')]['website'], 'nicht_geprueft')
        self.assertEqual(res['total']['metrics']['website']['wrong_assignment_rate']['k'], 0)

    def test_missing_run_counts_as_nothing_found(self):
        run = load('run.json')
        run['queries'] = run['queries'][:1]
        res = bm.evaluate(load('reference.json'), run)
        self.assertEqual(res['queries_without_run'], ['q2'])
        self.assertEqual(res['queries'][1]['metrics']['recall']['value'], 0.0)

    def test_reviewer_coverage(self):
        self.assertEqual(self.res['reviewer_coverage'], {'entries': 6, 'two_or_more_reviewers': 1})

    def test_wilson(self):
        self.assertIsNone(bm.wilson(0, 0))
        lo, hi = bm.wilson(8, 10)
        self.assertTrue(0.44 < lo < 0.5 and 0.94 < hi < 0.95)
        self.assertEqual(bm.wilson(10, 10)[1], 1.0)


class ReportTests(unittest.TestCase):
    def test_synthetic_report_says_so_first(self):
        md = bm.report_markdown(bm.evaluate(load('reference.json'), load('run.json')))
        self.assertTrue(md.startswith('> **Synthetische Testdaten – kein Messergebnis.**'))
        self.assertIn('Website falsch zugeordnet', md)
        self.assertIn('obere Schranke', md)

    def test_real_reference_has_no_synthetic_banner(self):
        ref = copy.deepcopy(load('reference.json'))
        ref['synthetic'] = False
        md = bm.report_markdown(bm.evaluate(ref, load('run.json')))
        self.assertNotIn('kein Messergebnis', md)


class ExportTests(unittest.TestCase):
    def test_export_only_company_data(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / 'b.sqlite3'
            prepare_database(db)
            conn = connect(db)
            conn.execute("INSERT INTO leads(company, website, location, contact_name, contact_role) "
                         "VALUES ('Holzwerk Fiktiv GmbH', 'holzwerk-fiktiv.example', '99901 Musterstadt', 'Max Muster', 'Inhaber')")
            conn.commit()
            conn.close()
            run = bm.export_run(db, 'q1', system='Test')
        self.assertEqual(bm.validate_run(run), [])
        c = run['queries'][0]['candidates'][0]
        self.assertEqual((c['name'], c['zip'], c['city']), ('Holzwerk Fiktiv GmbH', '99901', 'Musterstadt'))
        self.assertNotIn('Max Muster', json.dumps(run))
        self.assertNotIn('Inhaber', json.dumps(run))


class CliTests(unittest.TestCase):
    def test_validate_and_evaluate(self):
        tool = str(ROOT / 'tools' / 'research_benchmark.py')
        ok = subprocess.run([sys.executable, tool, 'validate', str(FIX / 'reference.json')], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.json'
            bad.write_text(json.dumps({'format': bm.REF_FORMAT, 'queries': [{'id': 'q', 'complete': True, 'companies': [{'name': 'X'}]}]}))
            res = subprocess.run([sys.executable, tool, 'validate', str(bad)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            out = Path(tmp) / 'e.md'
            ev = subprocess.run([sys.executable, tool, 'evaluate', str(FIX / 'reference.json'), str(FIX / 'run.json'), '--md', str(out)],
                                capture_output=True, text=True)
            self.assertEqual(ev.returncode, 0, ev.stdout + ev.stderr)
            self.assertIn('Synthetische Testdaten', out.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
