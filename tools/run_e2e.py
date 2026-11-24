"""Alle Browser-Tests ausführen und ehrlich zählen (SDQ-005).

python tools/run_e2e.py [--no-skips] [--min-tests N]

Läuft wie `python -m unittest discover -s tests/e2e`, zählt aber zusätzlich, wie viele Tests übersprungen wurden.
Mit --no-skips gilt ein übersprungener Test als Fehler: Fehlt Playwright oder Chromium in der CI, würden sonst alle
Browser-Tests still übersprungen und der Lauf wäre trotzdem grün. --min-tests schützt davor, dass die Suche
versehentlich weniger Dateien findet (z. B. nach einer Umbenennung).
"""
from __future__ import annotations

import argparse
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--no-skips', action='store_true', help='übersprungene Tests als Fehler werten')
    ap.add_argument('--min-tests', type=int, default=0, help='mindestens so viele Tests müssen gefunden werden')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests' / 'e2e'), top_level_dir=str(ROOT / 'tests' / 'e2e'))
    found = suite.countTestCases()
    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    took = time.monotonic() - start

    problems = []
    if result.failures or result.errors:
        problems.append(f'{len(result.failures)} fehlgeschlagen, {len(result.errors)} mit Fehler')
    if found < args.min_tests:
        problems.append(f'nur {found} Browser-Tests gefunden, erwartet mindestens {args.min_tests}')
    if args.no_skips and result.skipped:
        reasons = sorted({reason for _, reason in result.skipped})
        problems.append(f'{len(result.skipped)} übersprungen ({"; ".join(reasons)})')

    print(f'\nBrowser-Tests: {found} gefunden, {result.testsRun} gelaufen, {len(result.skipped)} übersprungen, '
          f'{len(result.failures) + len(result.errors)} nicht bestanden, {took:.0f} s')
    for p in problems:
        print('FEHLER:', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
