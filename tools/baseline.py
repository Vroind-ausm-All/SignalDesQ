"""Reproduzierbare Baseline (R0.1): Testzähler, Überspringungen mit Grund, Laufzeiten und Stand als Bericht.

    python tools/baseline.py [--no-browser] [--python PFAD ...] [--ci TEXT] [--out docs/BASELINE_<version>.md]

- Unit-Suite (`tests/`) und Browser-Suite (`tests/e2e/`) laufen je in einem eigenen Prozess; gezählt wird, was wirklich lief.
- `--python` (mehrfach): Unit-Suite zusätzlich mit weiteren Interpretern, z. B. der ältesten zugesagten Version 3.10.
- `--ci`: Ergebnis der CI für denselben Commit (z. B. „Lauf 220: 11/11 Jobs grün“) – wird nur übernommen, nicht geprüft.
- Ohne Netz; keine Daten außer Zählern, Testnamen und Gründen gelangen in den Bericht.
Beendet sich mit Code 1, wenn ein Test fehlschlug oder ein Browser-Test übersprungen wurde.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHILD = r'''
import json, sys, time, unittest, io
sys.path[:0] = [ROOT, START]
suite = unittest.defaultTestLoader.discover(START, top_level_dir=START)
t0 = time.monotonic()
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
print(json.dumps({'found': suite.countTestCases(), 'run': res.testsRun, 'failures': [str(t) for t, _ in res.failures],
                  'errors': [str(t) for t, _ in res.errors], 'skipped': [[str(t), r] for t, r in res.skipped],
                  'seconds': round(time.monotonic() - t0, 1), 'python': sys.version.split()[0]}))
'''


def run_suite(python, start, env_extra=None):
    code = CHILD.replace('ROOT', repr(str(ROOT))).replace('START', repr(str(start)))
    env = {**os.environ, 'PYTHONUTF8': '1', **(env_extra or {})}
    p = subprocess.run([python, '-c', code], cwd=str(ROOT), capture_output=True, text=True, errors='replace', env=env)
    line = next((l for l in reversed(p.stdout.splitlines()) if l.startswith('{')), None)
    if not line:
        raise SystemExit(f'Suite {start} mit {python} lieferte kein Ergebnis:\n{p.stderr[-2000:]}')
    return json.loads(line)


def git(*args):
    try:
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def plan_counts():
    sys.path.insert(0, str(ROOT / 'tools'))
    import plan_status
    plan = plan_status.load()
    return {ph['id']: plan_status.counts([p for p in plan['pakete'] if p['id'].startswith(ph['id'] + '.')]) for ph in plan['phasen']}


def _status(r, strict_skips=False):
    bad = len(r['failures']) + len(r['errors'])
    if bad:
        return f'**{bad} nicht bestanden**'
    if strict_skips and r['skipped']:
        return f"**{len(r['skipped'])} übersprungen**"
    return 'bestanden'


def report(data):
    from sales_tool import __version__
    L = [f'# Baseline {__version__}', '',
         f"> Erzeugt mit `python tools/baseline.py` am {data['date']}. Commit `{data['commit']}`"
         f"{' (Arbeitsbaum mit Änderungen)' if data['dirty'] else ''}, {data['system']}.", '',
         'Was hier steht, ist in diesem Lauf ausgeführt worden. CI-Ergebnis nur, wenn mit `--ci` angegeben.', '',
         '## Testläufe', '', '| Suite | Python | gefunden | gelaufen | übersprungen | Ergebnis | Dauer |', '|---|---|---|---|---|---|---|']
    for name, r, strict in data['suites']:
        L.append(f"| {name} | {r['python']} | {r['found']} | {r['run']} | {len(r['skipped'])} | {_status(r, strict)} | {r['seconds']} s |")
    L += ['', '## Übersprungene Tests mit Grund', '']
    skips = [(name, t, why) for name, r, _ in data['suites'] for t, why in r['skipped']]
    L += [f'- {name}: `{t}` – {why}' for name, t, why in skips] or ['- keine']
    fails = [(name, t) for name, r, _ in data['suites'] for t in r['failures'] + r['errors']]
    if fails:
        L += ['', '## Nicht bestanden', ''] + [f'- {name}: `{t}`' for name, t in fails]
    L += ['', '## CI', '', data['ci'] or 'nicht angegeben (in diesem Lauf nicht gelesen).', '',
          '## Planstand (R0–R7)', '', '| Phase | offen | teilweise | erledigt | blockiert |', '|---|---|---|---|---|']
    L += [f"| {ph} | {c['offen']} | {c['teilweise']} | {c['erledigt']} | {c['blockiert']} |" for ph, c in data['plan'].items()]
    L += ['', '## Nicht Teil dieser Baseline', '', '- macOS; echte Websites (alle Tests nutzen Attrappen); Lastmessung; Trefferquote an echten Firmen.', '']
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--python', action='append', default=[])
    ap.add_argument('--ci', default='')
    ap.add_argument('--out', default='')
    a = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from sales_tool import __version__
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    suites = []
    started = time.monotonic()
    for py in [sys.executable] + a.python:
        r = run_suite(py, ROOT / 'tests')
        suites.append((f'Unit (`tests/`)', r, False))
        print(f"Unit {r['python']}: {r['run']} gelaufen, {len(r['skipped'])} übersprungen, {len(r['failures']) + len(r['errors'])} nicht bestanden, {r['seconds']} s", flush=True)
    if not a.no_browser:
        r = run_suite(sys.executable, ROOT / 'tests' / 'e2e')
        suites.append(('Browser (`tests/e2e/`)', r, True))
        print(f"Browser: {r['run']} gelaufen, {len(r['skipped'])} übersprungen, {len(r['failures']) + len(r['errors'])} nicht bestanden, {r['seconds']} s", flush=True)
    data = {'date': dt.date.today().isoformat(), 'commit': git('rev-parse', '--short=12', 'HEAD') or 'unbekannt',
            'dirty': bool(git('status', '--porcelain', '--untracked-files=no')),
            'system': f'{platform.system()} {platform.machine()}', 'suites': suites, 'ci': a.ci, 'plan': plan_counts(),
            'seconds': round(time.monotonic() - started, 1)}
    out = Path(a.out) if a.out else ROOT / 'docs' / f'BASELINE_{__version__}.md'
    out.write_text(report(data), encoding='utf-8')
    print('geschrieben:', out.relative_to(ROOT) if out.is_relative_to(ROOT) else out)
    bad = any(r['failures'] or r['errors'] or (strict and r['skipped']) for _, r, strict in suites)
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
