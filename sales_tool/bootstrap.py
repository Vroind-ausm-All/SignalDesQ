"""Ein-Klick-Start: richtet SignalDesk beim ersten Start selbst ein und öffnet die Oberfläche.

Aufruf (macht SignalDesk_starten.bat / .command / start.sh automatisch):
    python -m sales_tool.bootstrap [--no-browser] [--port 8765] [--reinstall] [--setup-only]

Ablauf
1. Eigene virtuelle Umgebung `.venv` im Programmordner anlegen (nur beim ersten Start).
2. Website-Crawler (Playwright + Chromium) installieren – nur einmal bzw. nach einem Update
   der Anforderungen. Ohne Internet geht es trotzdem weiter: CRM, Angebote, Buchhaltung und
   Lead-Finder-Verwaltung funktionieren, nur die Website-Recherche fehlt dann.
3. Unter Windows einmalig eine Desktop-Verknüpfung „SignalDesk“ anlegen.
4. SignalDesk starten und den Browser öffnen.

Nur Python-Standardbibliothek, damit es vor jeder Installation lauffähig ist.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / '.venv'
REQUIREMENTS = ROOT / 'requirements-ai.txt'
MARKER = VENV / 'signaldesk-setup.json'
MIN_PYTHON = (3, 10)


def say(msg=''):
    print(msg, flush=True)


def venv_python(venv_dir: Path = VENV) -> Path:
    return venv_dir / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def requirements_hash(path: Path = REQUIREMENTS) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else 'none'


def read_marker(path: Path = MARKER) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def write_marker(data: dict, path: Path = MARKER):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def needs_install(marker: dict, req_hash: str, reinstall=False, today: str | None = None) -> bool:
    if reinstall or marker.get('requirements') != req_hash:
        return True
    if marker.get('crawler_ok'):
        return False
    # Fehlgeschlagen (z. B. offline): höchstens einmal pro Tag erneut versuchen, damit der Start schnell bleibt.
    return marker.get('last_attempt') != (today or dt.date.today().isoformat())


def is_inside_zip_preview(path: Path) -> bool:
    """Windows öffnet Dateien aus einer nicht entpackten ZIP in einem Temp-Ordner."""
    p = str(path).lower().replace('/', '\\')
    return os.name == 'nt' and '\\appdata\\local\\temp\\' in p and ('.zip' in p or '\\temp1_' in p or '\\rar$' in p)


def run(cmd, quiet=False) -> bool:
    """Führt einen Installationsschritt aus. Bei quiet=True nur eine kurze Fehlerzeile statt Logflut."""
    try:
        if not quiet:
            return subprocess.run(cmd, cwd=str(ROOT)).returncode == 0
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, errors='replace')
        if result.returncode != 0:
            lines = [l.strip() for l in (result.stderr + result.stdout).splitlines() if l.strip().startswith(('Error', 'ERROR', 'error'))]
            if lines:
                say('     ' + lines[-1][:220])
        return result.returncode == 0
    except OSError as exc:
        say(f'  Fehler beim Ausführen: {exc}')
        return False


def instance_running(port, timeout=1.5) -> bool:
    from urllib.request import urlopen
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/config', timeout=timeout) as resp:
            return resp.headers.get('Server', '').startswith('SignalDesk/')
    except (OSError, ValueError):
        return False


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists():
        return py
    say('① Lege eine eigene Python-Umgebung an (einmalig, ca. 20 Sekunden) …')
    venv.EnvBuilder(with_pip=True, clear=False).create(str(VENV))
    if not py.exists():
        raise SystemExit('Die Python-Umgebung konnte nicht angelegt werden. Bitte Python neu installieren (python.org).')
    return py


def ensure_crawler(py: Path, reinstall=False) -> bool:
    req_hash = requirements_hash()
    marker = read_marker()
    if not needs_install(marker, req_hash, reinstall):
        return True
    say('② Installiere den Website-Crawler (einmalig, benötigt Internet, 1–3 Minuten) …')
    ok = run([str(py), '-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', str(REQUIREMENTS)], quiet=True)
    if ok:
        say('   Lade den Browser für die Website-Recherche (Chromium, ca. 150 MB) …')
        ok = run([str(py), '-m', 'playwright', 'install', 'chromium'], quiet=True)
    if ok:
        say('   ✓ Website-Recherche ist eingerichtet.')
    else:
        say('   ⚠ Website-Crawler konnte nicht installiert werden (keine Internetverbindung oder Firewall).')
        say('     SignalDesk startet trotzdem – nur die Website-Recherche fehlt. Neuer Versuch beim ersten Start morgen')
        say('     oder sofort mit: SignalDesk_starten --reinstall')
    write_marker({**marker, 'requirements': req_hash, 'crawler_ok': ok, 'python': sys.version.split()[0],
                  'last_attempt': dt.date.today().isoformat()})
    return ok


def desktop_dir() -> Path | None:
    if os.name != 'nt':
        return None
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', "[Environment]::GetFolderPath('Desktop')"],
                             capture_output=True, text=True, timeout=20)
        path = Path(out.stdout.strip())
        return path if out.returncode == 0 and path.is_dir() else None
    except (OSError, subprocess.SubprocessError):
        return None


def ensure_shortcut():
    """Legt unter Windows einmalig eine Desktop-Verknüpfung an (Fehler werden ignoriert)."""
    if os.name != 'nt':
        return
    marker = read_marker()
    if marker.get('shortcut_done'):
        return
    target = ROOT / 'SignalDesk_starten.bat'
    desktop = desktop_dir()
    if desktop and target.exists():
        link = desktop / 'SignalDesk.lnk'
        ps = ('$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:SD_LINK);'
              '$s.TargetPath=$env:SD_TARGET;$s.WorkingDirectory=$env:SD_DIR;'
              '$s.IconLocation=$env:SD_ICON;$s.Description="SignalDesk starten";$s.Save()')
        icon = ROOT / 'sales_tool' / 'public' / 'signaldesk.ico'
        env = {**os.environ, 'SD_LINK': str(link), 'SD_TARGET': str(target), 'SD_DIR': str(ROOT),
               'SD_ICON': str(icon) if icon.exists() else 'shell32.dll,13'}
        try:
            done = subprocess.run(['powershell', '-NoProfile', '-Command', ps], env=env, timeout=30).returncode == 0
        except (OSError, subprocess.SubprocessError):
            done = False
        if done:
            say('   ✓ Desktop-Verknüpfung „SignalDesk“ angelegt – künftig einfach dort doppelklicken.')
    marker['shortcut_done'] = True
    write_marker(marker)


def main(argv=None):
    parser = argparse.ArgumentParser(description='SignalDesk einrichten und starten')
    parser.add_argument('--no-browser', action='store_true', help='Browser nicht automatisch öffnen')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default=None, help='Pfad zur Datenbank (Standard: ~/.akquise-tool/akquise.sqlite3)')
    parser.add_argument('--reinstall', action='store_true', help='Crawler-Installation erzwingen')
    parser.add_argument('--setup-only', action='store_true', help='Nur einrichten, nicht starten')
    args = parser.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        raise SystemExit(f'SignalDesk benötigt Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} oder neuer (gefunden: {sys.version.split()[0]}).')
    if is_inside_zip_preview(ROOT):
        raise SystemExit('Bitte die ZIP-Datei zuerst entpacken (Rechtsklick → „Alle extrahieren…“) und dann im entpackten Ordner starten.')

    if not args.setup_only and instance_running(args.port):
        url = f'http://127.0.0.1:{args.port}'
        say(f'SignalDesk läuft bereits – öffne {url}')
        if not args.no_browser:
            import webbrowser
            webbrowser.open(url, new=2)
        return 0
    say('SignalDesk wird gestartet …')
    py = ensure_venv()
    ensure_crawler(py, args.reinstall)
    ensure_shortcut()
    if args.setup_only:
        say('Einrichtung abgeschlossen.')
        return 0
    cmd = [str(py), '-m', 'sales_tool', '--port', str(args.port)]
    if args.db:
        cmd += ['--db', args.db]
    if not args.no_browser:
        cmd.append('--open-browser')
    say('③ Starte SignalDesk – der Browser öffnet sich gleich.')
    say('')
    try:
        return subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
