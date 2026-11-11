"""Installationsprüfung auf einem frischen Rechner (Masterplan 2.0, Sprint 6: „reproduzierbare Installation, keine
Datenbankverluste“). Läuft in der CI auf frischen Windows- und Linux-Maschinen, geht aber auch lokal:

    python tools/install_check.py dist/SignalDesk-<version>.zip --variant basis [--report bericht.json]

1. ZIP in einen neuen Ordner mit Leerzeichen und Umlauten entpacken (typischer Windows-Pfad).
2. Einrichten wie per Doppelklick: `python -m sales_tool.bootstrap --setup-only --variante <v>` (feste Versionen + Prüfsummen).
3. SignalDesk starten, Oberfläche und Schnittstelle prüfen, Lead anlegen, sichern, wiederherstellen.
4. Beenden und neu starten: Daten sind noch da (kein Datenverlust), Schema aktuell.
Nur Standardbibliothek. Beendet sich mit Code 0, wenn alles passt.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def call(base, path, method='GET', body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b'{}'), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'{}'), dict(exc.headers)


def start(py, root, port, db, log):
    env = {**os.environ, 'PYTHONUTF8': '1'}
    proc = subprocess.Popen([str(py), '-m', 'sales_tool', '--port', str(port), '--db', str(db), '--no-scheduler'], cwd=str(root),
                            stdout=log, stderr=subprocess.STDOUT, env=env)
    base = f'http://127.0.0.1:{port}'
    t0 = time.monotonic()
    while time.monotonic() - t0 < 90:
        if proc.poll() is not None:
            raise SystemExit(f'SignalDesk hat sich beim Start beendet (Code {proc.returncode}).')
        try:
            st, _, headers = call(base, '/api/config', timeout=3)
            if st == 200:
                return proc, base, round((time.monotonic() - t0) * 1000), headers.get('Server', '')
        except (OSError, ValueError):
            pass
        time.sleep(0.4)
    proc.kill()
    raise SystemExit('SignalDesk antwortet nicht innerhalb von 90 Sekunden.')


def stop(proc):
    proc.terminate()
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('zip')
    ap.add_argument('--variant', default='basis', choices=('basis', 'browser', 'team', 'voll'))
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--report', default='')
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')  # Windows-Konsole ohne UTF-8: Häkchen ersetzen statt abbrechen
    report, checks = {'variant': a.variant, 'platform': sys.platform, 'python': a.python}, []

    def ok(name, cond, detail=''):
        checks.append({'check': name, 'ok': bool(cond), 'detail': str(detail)[:300]})
        print(('✓ ' if cond else '✗ ') + name + (f' – {detail}' if detail else ''), flush=True)
        return cond

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / 'Mein Ordner – Übung'
        t0 = time.monotonic()
        with zipfile.ZipFile(a.zip) as zf:
            names = zf.namelist()
            top = names[0].split('/')[0]
            zf.extractall(dest)
        root = dest / top
        ok('ZIP entpackt', (root / 'SignalDesk_starten.bat').exists(), f'{len(names)} Dateien')
        manifest = (root / 'MANIFEST.sha256').read_text(encoding='utf-8').splitlines()
        import hashlib
        bad = [l for l in manifest if hashlib.sha256((root / l.split('  ', 1)[1]).read_bytes()).hexdigest() != l.split('  ', 1)[0]]
        ok('Prüfsummen laut MANIFEST', not bad, f'{len(manifest)} Dateien' if not bad else bad[:3])
        bat = (root / 'SignalDesk_starten.bat').read_bytes()
        ok('Startdatei mit Windows-Zeilenenden', b'\r\n' in bat and b'\n' not in bat.replace(b'\r\n', b''))
        t1 = time.monotonic()
        r = subprocess.run([a.python, '-m', 'sales_tool.bootstrap', '--setup-only', '--no-browser', '--variante', a.variant],
                           cwd=str(root), capture_output=True, text=True, errors='replace', env={**os.environ, 'PYTHONUTF8': '1'})
        print(r.stdout[-1500:], r.stderr[-1500:], sep='\n', flush=True)
        report['setup_seconds'] = round(time.monotonic() - t1, 1)
        ok('Einrichtung (bootstrap --setup-only)', r.returncode == 0, f"{report['setup_seconds']} s")
        venv_py = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        ok('eigene Python-Umgebung', venv_py.exists())
        marker = json.loads((root / '.venv' / 'signaldesk-setup.json').read_text(encoding='utf-8'))
        ok('Variante installiert', marker.get('variant') == a.variant and marker.get('crawler_ok'), marker)
        if a.variant != 'basis':
            r2 = subprocess.run([str(venv_py), '-c', 'import playwright, greenlet; print("ok")'], capture_output=True, text=True)
            ok('Browser-Pakete importierbar', r2.returncode == 0, r2.stderr[-200:])
        if a.variant in ('team', 'voll'):
            r3 = subprocess.run([str(venv_py), '-c', 'import cryptography; print(cryptography.__version__)'], capture_output=True, text=True)
            ok('cryptography importierbar', r3.returncode == 0, r3.stdout.strip())
        db = Path(tmp) / 'Daten Ö' / 'akquise.sqlite3'
        log = open(Path(tmp) / 'server.log', 'w', encoding='utf-8')
        port = free_port()
        proc, base, ms, server = start(venv_py, root, port, db, log)
        report['startup_ms'] = ms
        try:
            ok('Server startet', server.startswith('SignalDesk/'), f'{server} in {ms} ms')
            st, page, _ = 200, None, None
            with urllib.request.urlopen(base + '/', timeout=10) as resp:
                html = resp.read().decode('utf-8')
            ok('Oberfläche ausgeliefert', 'SignalDesk' in html and '/akte.js' in html)
            st, lead, _ = call(base, '/api/leads', 'POST', {'company': 'Installtest GmbH', 'industry': 'Sonstige'})
            ok('Lead anlegen', st == 201, lead.get('id'))
            st, bk, _ = call(base, '/api/backup', 'POST', {})
            ok('Sicherung anlegen', st == 201, Path(bk.get('path', '')).name)
            call(base, '/api/leads', 'POST', {'company': 'Nach der Sicherung GmbH', 'industry': 'Sonstige'})
            st, rs, _ = call(base, '/api/backups/restore', 'POST', {'name': Path(bk['path']).name, 'confirm': True}, timeout=60)
            ok('Sicherung wiederherstellen', st == 200 and rs.get('after', {}).get('leads') == 1, rs.get('error') or rs.get('after'))
            st, leads, _ = call(base, '/api/leads')
            ok('Stand nach Wiederherstellung', st == 200 and [l['company'] for l in leads] == ['Installtest GmbH'])
            st, off, _ = call(base, '/api/system/offline')
            ok('Offline-Modus abfragbar', st == 200 and off.get('offline') is False)
        finally:
            stop(proc)
        proc, base, ms2, _ = start(venv_py, root, free_port(), db, log)
        try:
            st, leads, _ = call(base, '/api/leads')
            ok('Neustart ohne Datenverlust', st == 200 and len(leads) == 1, f'{len(leads)} Lead(s), Start {ms2} ms')
            st, sec, _ = call(base, '/api/system/security')
            ok('Schema aktuell', st == 200 and sec.get('schema_version'), sec.get('schema_version'))
        finally:
            stop(proc)
            log.close()
        report['total_seconds'] = round(time.monotonic() - t0, 1)
        if not all(c['ok'] for c in checks):
            print((Path(tmp) / 'server.log').read_text(encoding='utf-8', errors='replace')[-3000:])
    report['checks'] = checks
    report['ok'] = all(c['ok'] for c in checks)
    if a.report:
        Path(a.report).write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print('ERGEBNIS:', 'bestanden' if report['ok'] else 'NICHT bestanden', f"({sum(c['ok'] for c in checks)}/{len(checks)})")
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
