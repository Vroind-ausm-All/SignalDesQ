"""Baue ein Quellpaket für die Weiterarbeit einschließlich Tests und Werkzeugen.

Es enthält den aktuellen Arbeitsbaum verwalteter Dateien und ausdrücklich
benannte neue Dateien; keine Git-Metadaten, virtuellen Umgebungen oder Nutzerdaten.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from build_release import ROOT, _info, check_safe, git_files, source_epoch
import zipfile

ADDITIONS = (
    'sales_tool/research/service_profile.py',
    'tests/test_service_profile_v2.py',
    'tests/e2e/test_service_profile_browser.py',
    'docs/MASTERPLAN_SOLOSELBSTAENDIGE.md',
    'docs/V2_ENTWICKLUNGSSTAND.md',
    'docs/UEBERGABE_FABLE.md',
    'tools/build_handoff.py',
)


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    names = sorted((set(git_files()) | set(ADDITIONS)) - {'.source-date-epoch', 'MANIFEST.sha256'})
    entries = []
    for name in names:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f'Datei fehlt oder ist ein Symlink: {name}')
        content = path.read_bytes()
        check_safe(name, content)
        entries.append((name, content))
    epoch = source_epoch()
    entries.append(('.source-date-epoch', f'{epoch}\n'.encode('ascii')))
    manifest = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in entries)
    entries.append(('MANIFEST.sha256', manifest.encode('utf-8')))
    target = out / 'SignalDesk-2.0-Quellpaket-Fable.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in entries:
            archive.writestr(_info('SignalDesk-Quellpaket/' + name, epoch, name.endswith(('.sh', '.command'))), data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + '.sha256').write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    return target, len(entries), digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT / 'dist'))
    args = parser.parse_args()
    path, count, digest = build(args.out)
    print(f'{path}: {count} Dateien, sha256 {digest}')
