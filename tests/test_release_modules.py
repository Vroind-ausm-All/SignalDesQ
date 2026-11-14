"""2.0.0-dev23: Jedes Python-Modul und jede Oberflächendatei von SignalDesk gehört ins Release-Paket – auch neue, noch nicht
committete Dateien (sonst startet das Paket nicht). Liest nur die Dateiliste, baut nichts."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('build_release', ROOT / 'tools' / 'build_release.py')
build_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_release)


class ReleaseModulesTests(unittest.TestCase):
    def test_every_module_and_ui_file_is_packaged(self):
        files = set(build_release.release_files())
        wanted = [p.relative_to(ROOT).as_posix() for pattern in ('sales_tool/**/*.py', 'sales_tool/public/*.js', 'sales_tool/public/*.css')
                  for p in ROOT.glob(pattern) if '__pycache__' not in p.parts]
        self.assertTrue(wanted)
        self.assertEqual([f for f in sorted(wanted) if f not in files], [])


if __name__ == '__main__':
    unittest.main()
