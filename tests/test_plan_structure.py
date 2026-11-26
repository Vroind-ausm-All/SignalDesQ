"""Open-Intelligence-Plan R0–R7 (2.0.0-dev66): Struktur der Planquelle, Phasenzuordnung, erzeugte Dokumente, Versionswahrheit.

Planquelle: docs/plan/open_intelligence.json, Werkzeug: tools/plan_status.py.
"""
import copy
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import plan_status as ps  # noqa: E402

from sales_tool import __version__  # noqa: E402


class PlanSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = ps.load()

    def test_plan_is_valid(self):
        self.assertEqual(ps.validate(self.plan), [])

    def test_every_phase_has_packages_and_gate(self):
        phases = {p['id']: p for p in self.plan['phasen']}
        self.assertEqual(list(phases), ['R0', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7'])
        for pid, ph in phases.items():
            with self.subTest(pid):
                self.assertTrue(ph['abnahme'])
                self.assertTrue([p for p in self.plan['pakete'] if p['id'].startswith(pid + '.')])

    def test_critical_path_matches_plan(self):
        crit = [p['id'] for p in self.plan['phasen'] if p['kritischer_pfad']]
        self.assertEqual(crit, ['R0', 'R1', 'R2', 'R4', 'R5', 'R7'])
        deps = {p['id']: p['abhaengig_von'] for p in self.plan['phasen']}
        self.assertEqual(deps['R3'], ['R1'], 'R3 parallel nach R1')
        self.assertEqual(deps['R6'], ['R0'], 'R6-Betriebsmaßnahmen beginnen früh')
        self.assertEqual(sorted(deps['R7']), ['R5', 'R6'], 'kein Start ohne Pilot und Nachprüfung')

    def test_security_findings_and_skills_are_assigned(self):
        self.assertEqual([f['id'] for f in self.plan['sicherheitsbefunde']], [f'F{i:02d}' for i in range(1, 13)])
        names = {s['name'] for s in self.plan['skills']}
        self.assertTrue({'privacy-and-contact-guardrails', 'qa-release-gate', 'research-source-policy', 'contact-entity-evidence',
                         'document-intelligence', 'organization-graph', 'research-benchmark', 'dependency-security', 'saas-operations'} <= names)
        existing = {p.name for p in (ROOT / '.claude' / 'skills').iterdir() if (p / 'SKILL.md').exists()}
        self.assertEqual(existing - names, set(), 'jeder vorhandene Skill ist im Plan geführt')

    def test_launch_waits_for_external_gates(self):
        launch = next(p for p in self.plan['pakete'] if p['id'] == 'R7.5')
        self.assertIn('R6.10', launch['abhaengig_von'], 'Start erst nach unabhängiger Security-Nachprüfung')
        self.assertIn('R5.1', launch['abhaengig_von'], 'Start erst nach Referenzmessung')
        for pid in ('R6.10', 'R5.1', 'R7.3'):
            with self.subTest(pid):
                self.assertNotEqual(next(p for p in self.plan['pakete'] if p['id'] == pid)['verantwortlich'], 'Engineering',
                                    'externe Nachweise kann das Engineering nicht selbst abhaken')


class ValidatorCatchesErrorsTests(unittest.TestCase):
    """Die Prüfung muss kaputte Pläne erkennen – sonst wäre der grüne Test oben wertlos."""
    def setUp(self):
        self.plan = copy.deepcopy(ps.load())

    def pkg(self, pid):
        return next(p for p in self.plan['pakete'] if p['id'] == pid)

    def assertError(self, pattern):
        errors = ps.validate(self.plan)
        self.assertTrue(any(re.search(pattern, e) for e in errors), errors)

    def test_dependency_on_later_phase(self):
        self.pkg('R1.1')['abhaengig_von'].append('R4.1')
        self.assertError(r'R1\.1: hängt von R4\.1 aus einer späteren Phase ab')

    def test_cycle(self):
        self.pkg('R0.3')['abhaengig_von'].append('R0.5')
        self.pkg('R0.4')['abhaengig_von'].append('R0.3')
        self.assertError(r'Zyklus')

    def test_done_without_evidence(self):
        p = self.pkg('R1.3')
        p['status'] = 'erledigt'
        self.assertError(r'R1\.3: Status erledigt ohne Nachweis')
        p['nachweis'] = 'irgendwie fertig'
        self.assertError(r'R1\.3: erledigt ohne Version im Nachweis')

    def test_unknown_values_and_missing_paths(self):
        self.pkg('R2.1')['status'] = 'fast fertig'
        self.pkg('R2.1')['basis'].append('sales_tool/gibt_es_nicht.py')
        self.assertError(r"R2\.1: Status 'fast fertig' unbekannt")
        self.assertError(r'R2\.1: Grundlage sales_tool/gibt_es_nicht\.py existiert nicht')

    def test_security_finding_without_package(self):
        self.plan['sicherheitsbefunde'][4]['pakete'] = []
        self.assertError(r'F05: kein oder unbekanntes Paket')

    def test_unknown_dependency(self):
        self.pkg('R3.1')['abhaengig_von'].append('R3.99')
        self.assertError(r'R3\.1: Abhängigkeit R3\.99 unbekannt')


class GeneratedDocsTests(unittest.TestCase):
    def test_generated_documents_are_current(self):
        self.assertEqual(ps.main(['--check']), 0, 'python tools/plan_status.py --write ausführen')

    def test_roadmap_links_plan(self):
        text = ps.ROADMAP.read_text(encoding='utf-8')
        self.assertIn(ps.BEGIN, text)
        self.assertIn('MASTERPLAN_OPEN_INTELLIGENCE.md', text)
        master = ps.MASTERPLAN.read_text(encoding='utf-8')
        for pid in ('R0.1', 'R4.2', 'R6.10', 'R7.5'):
            self.assertIn(f'**{pid}**', master)
        self.assertTrue((ROOT / ps.load()['quelle']).exists(), 'Quell-PDF des Plans liegt im Repository')

    def test_baseline_report_exists_when_r01_done(self):
        """R0.1: ein Baseline-Bericht mit Commit, Testläufen, Überspringungen mit Grund und Planstand."""
        r01 = next(p for p in ps.load()['pakete'] if p['id'] == 'R0.1')
        reports = sorted((ROOT / 'docs').glob('BASELINE_*.md'))
        if r01['status'] != 'erledigt':
            self.skipTest('R0.1 noch nicht erledigt')
        if os.environ.get('SIGNALDESK_BASELINE_RUN'):
            self.skipTest('läuft innerhalb von tools/baseline.py – der Bericht entsteht erst am Ende dieses Laufs')
        self.assertTrue(reports, 'docs/BASELINE_<version>.md fehlt (python tools/baseline.py)')
        text = reports[-1].read_text(encoding='utf-8')
        for part in ('Commit `', '## Testläufe', '## Übersprungene Tests mit Grund', '## CI', '## Planstand'):
            self.assertIn(part, text)
        self.assertRegex(text, r'\| Unit \(`tests/`, Python 3\.\d+')

    def test_status_sources_name_current_version(self):
        """R0.2 Versionswahrheit: Statusquellen nennen die Version aus sales_tool/__init__.py."""
        for rel, pattern in (('README.md', r'Stand (2\.0\.0-dev\d+)'), ('docs/ROADMAP.md', r'Stand (2\.0\.0-dev\d+)'),
                             ('docs/EINSCHRAENKUNGEN.md', r'Stand (2\.0\.0-dev\d+)'), ('CHANGELOG.md', r'## (2\.0\.0-dev\d+)')):
            with self.subTest(rel):
                m = re.search(pattern, (ROOT / rel).read_text(encoding='utf-8'))
                self.assertIsNotNone(m)
                self.assertEqual(m.group(1), __version__)


if __name__ == '__main__':
    unittest.main()
