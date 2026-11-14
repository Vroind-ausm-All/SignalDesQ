"""Reproduzierbares Release-ZIP für Windows/macOS/Linux (Masterplan 2.0, Sprint 6).

python tools/build_release.py [--out dist] [--offline-wheels win_amd64:3.12:browser]

- Inhalt: alles, was git verwaltet, ohne Tests/Werkzeuge/CI (Liste: INCLUDE/EXCLUDE unten), plus SBOM und Lockdateien.
- Reproduzierbar: feste Reihenfolge, fester Zeitstempel (letzter Commit bzw. SOURCE_DATE_EPOCH), feste Dateirechte –
  gleicher Stand → byte-gleiche ZIP. Prüfsumme in `<zip>.sha256`, Inhaltsliste mit Prüfsummen in `MANIFEST.sha256`.
- Sicherheitsprüfung: keine Datenbanken, Sicherungen, .env oder geheimen Schlüssel im Paket (Abbruch).
- `--offline-wheels PLATTFORM:PYTHON:VARIANTE`: zusätzlich ein Offline-Paket mit allen Paketdateien der Variante in `wheels/`
  (Installation ganz ohne Internet; Chromium für die Browser-Prüfung wird dennoch beim ersten Start geladen).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EXCLUDE_DIRS = ('tests/', 'tools/', '.github/', 'docs/bench/', 'ausgabe/', '.claude/')  # ausgabe/: fertige Pakete gehören nicht ins Paket
EXCLUDE_FILES = ('.gitignore', '.gitattributes', '.source-date-epoch')
# Neue, noch nicht eingecheckte Dateien müssen im lokalen Entwicklungs-Release enthalten sein.
# Eine feste Liste verhindert, dass beliebige Nutzerdaten in das Paket geraten.
RELEASE_ADDITIONS = ('sales_tool/research/service_profile.py', 'docs/MASTERPLAN_SOLOSELBSTAENDIGE.md',
                     'docs/V2_ENTWICKLUNGSSTAND.md', 'docs/UEBERGABE_FABLE.md', 'sales_tool/qualification.py',
                     'sales_tool/public/assessment.js', 'sales_tool/reach.py', 'sales_tool/public/reach.js', 'sales_tool/postcalc.py', 'sales_tool/public/postcalc.js', 'sales_tool/research/osm_local.py', 'sales_tool/public/osmlocal.js', 'docs/LAUNCH_AUDIT.md', 'docs/ARCHITECTURE_DECISIONS.md', 'docs/SELF_REVIEW_LOG.md', 'docs/PRAXISTEST_70191.md', 'docs/OPENSTREETMAP_LOKAL.md', 'sales_tool/appearance.py', 'sales_tool/public/theme.js', 'sales_tool/public/formguard.js', 'sales_tool/public/nav.js', 'sales_tool/public/leadlist.js', 'sales_tool/focus.py', 'docs/UI_UX_VORSCHLAEGE.md',
                     'sales_tool/catalog.py', 'docs/LEISTUNGSKATALOG.md',
                     'sales_tool/offer_flow.py', 'sales_tool/public/offerflow.js',
                     'sales_tool/chances.py', 'sales_tool/public/chances.js',
                     'sales_tool/briefing.py', 'sales_tool/revisions.py')
FORBIDDEN = re.compile(r'(\.sqlite3(-wal|-shm)?|\.sdenc|\.db|\.env|\.pem|\.key|id_rsa)$', re.I)
SECRET = re.compile(rb'(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-ant-[A-Za-z0-9]{10}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30})')
EXECUTABLE = ('.sh', '.command')


def git_files():
    try:
        proc = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=False)
        if proc.returncode == 0:
            return sorted(f for f in proc.stdout.decode('utf-8').split('\0') if f)
    except FileNotFoundError:
        pass
    # Quellpakete enthalten keine Git-Metadaten. Das Manifest dient hier nur als
    # Dateiliste: bearbeitete Quelldateien dürfen neu gebaut werden.
    manifest = ROOT / 'MANIFEST.sha256'
    if not manifest.is_file():
        raise SystemExit('Weder Git-Dateiliste noch Quellpaket-MANIFEST.sha256 vorhanden.')
    files = []
    for line in manifest.read_text(encoding='utf-8').splitlines():
        parts = line.split('  ', 1)
        if len(parts) != 2 or not re.fullmatch(r'[0-9a-f]{64}', parts[0]):
            raise SystemExit('Ungültige Dateiliste im Quellpaket-Manifest.')
        name = parts[1]
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or not (ROOT / name).is_file():
            raise SystemExit(f'Ungültiger Dateiname im Quellpaket-Manifest: {name}')
        if not (ROOT / name).resolve().is_relative_to(ROOT.resolve()):
            raise SystemExit(f'Datei außerhalb des Quellpakets: {name}')
        files.append(name)
    return sorted(set(files))


def release_files():
    files = [f for f in git_files() if not f.startswith(EXCLUDE_DIRS) and f not in EXCLUDE_FILES]
    files.extend(f for f in RELEASE_ADDITIONS if (ROOT / f).is_file())
    for extra in sorted(ROOT.glob('requirements-lock-*.txt')) + [ROOT / 'sbom' / 'signaldesk.cdx.json']:
        rel = extra.relative_to(ROOT).as_posix()
        if extra.exists() and rel not in files:
            files.append(rel)
    return sorted(set(files))


def source_epoch():
    if os.environ.get('SOURCE_DATE_EPOCH', '').isdigit():
        return int(os.environ['SOURCE_DATE_EPOCH'])
    snapshot_epoch = ROOT / '.source-date-epoch'
    if snapshot_epoch.is_file():
        value = snapshot_epoch.read_text(encoding='ascii').strip()
        if not value.isdigit():
            raise SystemExit('Ungültiger Zeitstempel im Quellpaket.')
        return int(value)
    try:
        return int(subprocess.run(['git', 'log', '-1', '--format=%ct'], cwd=ROOT, capture_output=True, check=True).stdout.strip())
    except (subprocess.CalledProcessError, ValueError, OSError):
        return 1767225600  # 2026-01-01


def check_safe(rel, data):
    if FORBIDDEN.search(rel):
        raise SystemExit(f'Abbruch: {rel} gehört nicht ins Release (Datenbank/Sicherung/Schlüssel).')
    m = SECRET.search(data)
    if m:
        raise SystemExit(f'Abbruch: {rel} enthält etwas, das wie ein geheimer Schlüssel aussieht.')


def _info(name, epoch, executable=False):
    t = time.gmtime(max(epoch, 315532800))[:6]  # ZIP kann erst ab 1980
    zi = zipfile.ZipInfo(name, date_time=t)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.create_system = 3  # Unix – Rechte werden übernommen, Windows ignoriert sie
    zi.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
    return zi


def build(out_dir, version=None, extra=None, suffix=''):
    """Baut die ZIP-Datei. extra: {relativer Pfad: bytes} (z. B. wheels). Gibt (Pfad, sha256) zurück."""
    from sales_tool import __version__
    version = version or __version__
    top = f'SignalDesk-{version}'
    epoch = source_epoch()
    entries = []
    for rel in release_files():
        data = (ROOT / rel).read_bytes()
        check_safe(rel, data)
        entries.append((rel, data))
    for rel, data in sorted((extra or {}).items()):
        entries.append((rel, data))
    manifest = ''.join(f'{hashlib.sha256(d).hexdigest()}  {r}\n' for r, d in entries)
    entries.append(('MANIFEST.sha256', manifest.encode('utf-8')))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'{top}{suffix}.zip'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compresslevel=9) as zf:
        for rel, data in entries:
            zf.writestr(_info(f'{top}/{rel}', epoch, rel.endswith(EXECUTABLE)), data)
    target.write_bytes(buf.getvalue())
    digest = hashlib.sha256(buf.getvalue()).hexdigest()
    target.with_name(target.name + '.sha256').write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    return target, digest, len(entries)


def offline_wheels(spec):
    """PLATTFORM:PYTHON:VARIANTE → {wheels/datei: bytes} (lädt mit pip die gesperrten Dateien der Zielplattform)."""
    from sales_tool.bootstrap import VARIANTS
    platform, python, variant = spec.split(':')
    files = {}
    with tempfile.TemporaryDirectory() as tmp:
        for lock in VARIANTS[variant]['locks']:
            cmd = [sys.executable, '-m', 'pip', 'download', '-q', '--require-hashes', '--only-binary=:all:', '--platform', platform,
                   '--python-version', python, '--implementation', 'cp', '-d', tmp, '-r', str(ROOT / f'requirements-lock-{lock}.txt')]
            subprocess.run(cmd, check=True)
        for f in sorted(Path(tmp).iterdir()):
            files[f'wheels/{f.name}'] = f.read_bytes()
    return files


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'dist'))
    ap.add_argument('--offline-wheels', help='z. B. win_amd64:3.12:browser')
    a = ap.parse_args(argv)
    path, digest, n = build(a.out)
    print(f'{path.name}: {n} Dateien, {path.stat().st_size / 1e6:.1f} MB, sha256 {digest}')
    if a.offline_wheels:
        plat, py, variant = a.offline_wheels.split(':')
        path, digest, n = build(a.out, extra=offline_wheels(a.offline_wheels), suffix=f'-offline-{variant}-{plat}-py{py.replace(".", "")}')
        print(f'{path.name}: {n} Dateien, {path.stat().st_size / 1e6:.1f} MB, sha256 {digest}')


if __name__ == '__main__':
    main()
