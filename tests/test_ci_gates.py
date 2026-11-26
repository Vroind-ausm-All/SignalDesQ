"""R0.5 (2.0.0-dev67): Dependency- und Code-Gates in der CI.

Geprüft wird die Konfiguration, nicht das Ergebnis (das liefert der CI-Job „audit“ selbst):
- pip-audit über ALLE Lockdateien, Ruff mit Fehlerklassen, Gitleaks über Code und Historie;
- Prüfwerkzeuge nur aus einer Lockdatei mit Prüfsummen, Gitleaks-Download mit fester Version und SHA-256;
- alle Actions per Commit gepinnt (SDQ-038);
- die Gitleaks-Ausnahme gibt keinen Pfad pauschal frei;
- Prüfwerkzeuge gelangen weder ins Release-Paket noch in die SBOM.
Nur Standardbibliothek (kein YAML-Parser in der Variante „basis“).
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / '.github' / 'workflows' / 'tests.yml').read_text(encoding='utf-8')
sys.path.insert(0, str(ROOT / 'tools'))


def job(name):
    m = re.search(rf'(?ms)^  {name}:\n(.*?)(?=^  \w[\w-]*:\n|\Z)', WORKFLOW)
    return m.group(1) if m else ''


class CiGateTests(unittest.TestCase):
    def test_audit_job_runs_all_checks(self):
        audit = job('audit')
        self.assertTrue(audit, 'CI-Job „audit“ fehlt')
        self.assertIn('fetch-depth: 0', audit, 'Gitleaks braucht die ganze Historie')
        self.assertIn('pip install --require-hashes -r tools/requirements-lock-dev.txt', audit)
        self.assertRegex(audit, r'for f in requirements-lock-\*\.txt tools/requirements-lock-dev\.txt')
        self.assertIn('pip-audit --require-hashes --disable-pip', audit)
        self.assertRegex(audit, r'ruff check --select E9,F63,F7,F82 .*sales_tool tools tests')
        self.assertIn('gitleaks" git . --config .gitleaks.toml', audit)
        self.assertIn('gitleaks" dir . --config .gitleaks.toml', audit)
        self.assertNotIn('|| true', audit, 'Funde dürfen den Job nicht still bestehen lassen')
        self.assertNotIn('continue-on-error', audit)

    def test_every_lock_installs_on_every_unit_target(self):
        """dev67: Variante „team“ war unter Python 3.10 nicht installierbar (typing-extensions fehlte) – die CI prüfte nur 3.12."""
        unit = job('unit')
        self.assertIn('os: [windows-latest, ubuntu-latest]', unit)
        self.assertIn('python: ["3.10", "3.13"]', unit)
        self.assertRegex(unit, r'for f in requirements-lock-\*\.txt; do')
        self.assertIn('pip install --dry-run --ignore-installed --require-hashes', unit)
        self.assertLess(unit.index('--dry-run'), unit.index('unittest discover'))

    def test_gitleaks_download_is_pinned_and_verified(self):
        audit = job('audit')
        self.assertRegex(audit, r'GITLEAKS_VERSION: "\d+\.\d+\.\d+"')
        self.assertRegex(audit, r'GITLEAKS_SHA256: "[0-9a-f]{64}"')
        self.assertIn('sha256sum -c -', audit)
        self.assertLess(audit.index('sha256sum -c -'), audit.index('tar -xzf'), 'erst prüfen, dann entpacken')

    def test_all_actions_pinned_by_commit(self):
        uses = re.findall(r'uses: (\S+)', WORKFLOW)
        self.assertTrue(uses)
        for u in uses:
            with self.subTest(u):
                self.assertRegex(u, r'@[0-9a-f]{40}$')

    def test_gitleaks_allowlist_is_narrow(self):
        cfg = (ROOT / '.gitleaks.toml').read_text(encoding='utf-8')
        self.assertIn('useDefault = true', cfg)
        self.assertNotRegex(cfg, r'(?m)^\s*paths\s*=', 'keine Pfad-Ausnahme – ein echter Schlüssel in tests/ bleibt ein Fund')
        for rx in re.findall(r"'''(.*?)'''", cfg):
            with self.subTest(rx):
                self.assertNotIn(rx, ('.*', '.+'), 'keine Ausnahme, die alles trifft')

    def test_dev_lock_has_hashes_and_stays_out_of_release(self):
        lock = ROOT / 'tools' / 'requirements-lock-dev.txt'
        text = lock.read_text(encoding='utf-8')
        for pkg in ('pip-audit', 'ruff'):
            with self.subTest(pkg):
                self.assertRegex(text, rf'(?m)^{pkg}==\S+ ?(;[^\\]*)?\\\n    --hash=sha256:[0-9a-f]{{64}}')
        pins = re.findall(r'(?m)^([A-Za-z0-9_.-]+)==', text)
        hashed = re.findall(r'(?m)^[A-Za-z0-9_.-]+==[^\n]*\\\n    --hash=sha256:', text)
        self.assertEqual(len(pins), len(hashed), 'jede Abhängigkeit mit Prüfsumme')
        import build_release
        import make_sbom
        self.assertFalse([f for f in build_release.release_files() if 'requirements-lock-dev' in f or f == 'requirements-dev.txt'])
        sbom_names = {c['name'] for c in make_sbom.build()['components']}
        self.assertNotIn('pip-audit', sbom_names)
        self.assertNotIn('ruff', sbom_names)


if __name__ == '__main__':
    unittest.main()
