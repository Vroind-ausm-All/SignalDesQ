"""Erzeugt die Lockdateien mit festen Versionen und Prüfsummen (Masterplan 2.0, Sprint 6).

python tools/make_lock.py [--cooldown-days 14] [--variants browser,team,research]

Je Installationsvariante wird mit pip für alle Zielsysteme aufgelöst (Windows x64 und Linux x64, Python 3.10–3.13).
Gewählt wird je Paket eine Version, die auf ALLEN Zielen installierbar ist, und nur Versionen, die mindestens
`--cooldown-days` Tage alt sind (Schutz vor frisch kompromittierten Releases). In die Lockdatei kommen die
SHA-256-Prüfsummen aller Dateien dieser Version (pip prüft beim Installieren mit --require-hashes).
Ergebnis: requirements-lock-<variante>.txt im Projektordner + docs/bench/lock-resolution.json (Protokoll).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VARIANTS = {'browser': ['requirements-ai.txt'], 'team': ['requirements-team.txt'], 'research': ['requirements-research.txt']}
PYTHONS = ('3.10', '3.11', '3.12', '3.13')
PLATFORMS = {'windows': ['win_amd64'],
             'linux': ['manylinux_2_28_x86_64', 'manylinux_2_17_x86_64', 'manylinux2014_x86_64', 'manylinux1_x86_64', 'linux_x86_64']}
_PYPI = {}


def pypi(name):
    key = name.lower().replace('_', '-')
    if key not in _PYPI:
        with urllib.request.urlopen(f'https://pypi.org/pypi/{key}/json', timeout=30) as r:
            _PYPI[key] = json.load(r)
    return _PYPI[key]


CLASSIFIER_SPDX = {'MIT License': 'MIT', 'BSD License': 'BSD-3-Clause', 'Apache Software License': 'Apache-2.0',
                   'Mozilla Public License 2.0 (MPL 2.0)': 'MPL-2.0', 'Python Software Foundation License': 'PSF-2.0',
                   'ISC License (ISCL)': 'ISC', 'GNU Lesser General Public License v2 or later (LGPLv2+)': 'LGPL-2.0-or-later'}


def license_of(name):
    info = pypi(name)['info']
    if (info.get('license_expression') or '').strip():
        return info['license_expression'].strip()
    found = [CLASSIFIER_SPDX[c.split(' :: ')[-1]] for c in info.get('classifiers') or []
             if c.startswith('License :: OSI Approved ::') and c.split(' :: ')[-1] in CLASSIFIER_SPDX]
    if found:
        return ' OR '.join(sorted(set(found)))
    lic = (info.get('license') or '').strip()
    return lic if 0 < len(lic) <= 40 and '\n' not in lic else ''


def files_of(name, version):
    return pypi(name)['releases'].get(version) or []


def uploaded(name, version):
    times = [f['upload_time_iso_8601'][:19] for f in files_of(name, version)]
    return min(times) if times else ''


def vkey(v):
    out = []
    for part in v.replace('-', '.').split('.'):
        num = ''.join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return out


def resolve(req_files, constraints, platform, python):
    with tempfile.TemporaryDirectory() as tmp:
        report, cons = Path(tmp) / 'r.json', Path(tmp) / 'c.txt'
        cons.write_text('\n'.join(f'{k}{v}' for k, v in sorted(constraints.items())) + '\n', encoding='utf-8')
        cmd = [sys.executable, '-m', 'pip', 'install', '-q', '--dry-run', '--ignore-installed', '--report', str(report),
               '--python-version', python, '--implementation', 'cp', '--only-binary=:all:', '-c', str(cons)]
        for p in PLATFORMS[platform]:
            cmd += ['--platform', p]
        for f in req_files:
            cmd += ['-r', str(ROOT / f)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return None, [l for l in (r.stderr or r.stdout).strip().splitlines() if l.strip()][-12:]
        d = json.loads(report.read_text(encoding='utf-8'))
        return {i['metadata']['name'].lower().replace('_', '-'): i['metadata']['version'] for i in d['install']}, []


def explicit_pins(req_files):
    """Ausdrücklich mit == festgelegte Hauptpakete (bewusst geprüft, z. B. Scrapling 0.5.1 aus Sprint 1) – ohne Wartezeit."""
    import re
    out = {}
    for f in req_files:
        for line in (ROOT / f).read_text(encoding='utf-8').splitlines():
            m = re.match(r'^\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s#;]+)', line)
            if m:
                out[m.group(1).lower().replace('_', '-')] = m.group(2)
    return out


def lock_variant(name, req_files, cutoff, log):
    constraints = {}
    pinned = explicit_pins(req_files)
    for rnd in range(8):
        results, errors = {}, []
        for plat in PLATFORMS:
            for py in PYTHONS:
                res, err = resolve(req_files, constraints, plat, py)
                if res is None:
                    errors.append(f'{plat} {py}: {err}')
                else:
                    results[(plat, py)] = res
        if errors:
            raise SystemExit(f'{name}: nicht auflösbar – ' + '; '.join(errors))
        changed = False
        pkgs = sorted({p for r in results.values() for p in r})
        for p in pkgs:
            versions = sorted({r[p] for r in results.values() if p in r}, key=vkey)
            too_new = [v for v in versions if uploaded(p, v) > cutoff and pinned.get(p) != v]
            if too_new:  # jünger als die Wartezeit → nächstältere Version erzwingen
                constraints[p] = f'<{min(too_new, key=vkey)}'
                changed = True
            elif len(versions) > 1:  # unterschiedliche Versionen je Ziel → gemeinsame (älteste) Version
                constraints[p] = f'=={versions[0]}'
                changed = True
        log.append({'variant': name, 'round': rnd + 1, 'constraints': dict(constraints)})
        if not changed:
            final = {}
            for r in results.values():
                final.update(r)
            platforms = {p: sorted(f'{plat}-py{py}' for (plat, py), r in results.items() if p in r) for p in final}
            return final, platforms
    raise SystemExit(f'{name}: keine stabile Auflösung nach 8 Runden.')


def write_lock(name, req_files, pins, platforms, cutoff):
    every = {f'{plat}-py{py}' for plat in PLATFORMS for py in PYTHONS}
    lines = [f'# SignalDesk – Installationsvariante „{name}“ (erzeugt mit tools/make_lock.py, nicht von Hand ändern)',
             f'# Quelle: {", ".join(req_files)} · Ziele: Windows x64 und Linux x64, Python {PYTHONS[0]}–{PYTHONS[-1]}',
             f'# Nur Versionen, die vor {cutoff[:10]} veröffentlicht wurden. Installation: pip install --require-hashes -r <diese Datei>', '']
    for p in sorted(pins):
        v = pins[p]
        hashes = sorted({f['digests']['sha256'] for f in files_of(p, v)})
        marker = ''
        if set(platforms[p]) != every:  # nur auf manchen Zielen nötig (z. B. tzdata unter Windows)
            plats = sorted({x.split('-')[0] for x in platforms[p]})
            pys = sorted({x.split('-py')[1] for x in platforms[p]}, key=vkey)
            conds = []
            if plats == ['windows']:
                conds.append('sys_platform == "win32"')
            elif plats == ['linux']:
                conds.append('sys_platform == "linux"')
            if set(pys) != set(PYTHONS):
                conds.append(f'python_version < "{_next_minor(pys[-1])}"' if pys[0] == PYTHONS[0] else f'python_version >= "{pys[0]}"')
            marker = ' ; ' + ' and '.join(conds) if conds else ''
        lines.append(f'{p}=={v}{marker} \\')
        lines += [f'    --hash=sha256:{h}' + (' \\' if i < len(hashes) - 1 else '') for i, h in enumerate(hashes)]
    (ROOT / f'requirements-lock-{name}.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _next_minor(v):
    a, b = v.split('.')
    return f'{a}.{int(b) + 1}'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--cooldown-days', type=int, default=14)
    ap.add_argument('--variants', default=','.join(VARIANTS))
    ap.add_argument('--today', default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    cutoff = (dt.date.fromisoformat(a.today) - dt.timedelta(days=a.cooldown_days)).isoformat() + 'T00:00:00'
    res_path = ROOT / 'docs' / 'bench' / 'lock-resolution.json'
    old = json.loads(res_path.read_text(encoding='utf-8')) if res_path.exists() else {}
    log, summary = [], dict(old.get('variants') or {})
    for name in a.variants.split(','):
        pins, platforms = lock_variant(name, VARIANTS[name], cutoff, log)
        write_lock(name, VARIANTS[name], pins, platforms, cutoff)
        summary[name] = {p: {'version': v, 'uploaded': uploaded(p, v)[:10], 'targets': len(platforms[p]),
                             'license': license_of(p)} for p, v in sorted(pins.items())}
        print(f"{name}: {', '.join(f'{p}=={v}' for p, v in sorted(pins.items()))}")
    res_path.write_text(json.dumps({'cutoff': cutoff, 'pythons': PYTHONS, 'platforms': list(PLATFORMS),
                                                                              'variants': summary, 'rounds': log}, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
