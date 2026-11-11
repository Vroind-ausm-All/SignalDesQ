"""Datensicherung wiederherstellen (Masterplan 2.0, Sprint 6 – SignalDesk v1.19).

Abnahme laut Plan: keine Datenbankverluste. Ablauf einer Wiederherstellung:
1. Sicherung prüfen: echte SQLite-Datei (bei `.sdenc` erst mit Passwort entschlüsseln), `PRAGMA integrity_check`,
   SignalDesk-Tabellen vorhanden, Schema nicht neuer als dieses Programm.
2. Buchhaltung schützen (GoBD): fehlen in der Sicherung festgeschriebene Rechnungen, die es jetzt gibt, wird abgelehnt –
   sonst gingen unveränderbare Belege verloren. Ausnahme: die aktuelle Datenbank ist selbst beschädigt.
3. Aktuellen Stand vorher sichern („vor-wiederherstellung“) – die Wiederherstellung ist damit selbst umkehrbar.
4. Einspielen über die SQLite-Backup-Schnittstelle (atomar, auch bei laufendem Programm) und auf das aktuelle Schema
   migrieren (gleicher Weg wie beim Programmstart).

Kommandozeile (wenn SignalDesk nicht mehr startet):
    python -m sales_tool.backup_restore liste --db <datenbank>
    python -m sales_tool.backup_restore wiederherstellen <sicherung.sqlite3|.sdenc> --db <datenbank>
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REQUIRED_TABLES = ('leads', 'activities', 'tasks')
NAME_RE = re.compile(r'^signaldesk-[\w.-]+\.(sqlite3|sdenc)$')
MAX_UPLOAD = 2 * 1024 ** 3


def backup_dir(db_path):
    from .accounting_api import _backup_dir
    return _backup_dir(db_path)


def list_all(db_path):
    folder = backup_dir(db_path)
    items = []
    if folder.exists():
        for p in sorted(list(folder.glob('signaldesk-*.sqlite3')) + list(folder.glob('signaldesk-*.sdenc')), key=lambda x: x.stat().st_mtime, reverse=True)[:100]:
            items.append({'name': p.name, 'encrypted': p.suffix == '.sdenc', 'size_bytes': p.stat().st_size,
                          'modified': dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'),
                          'before_restore': '-vor-wiederherstellung' in p.name})
    return {'folder': str(folder), 'backups': items}


def _open_ro(path):
    return sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)


def inspect(path):
    """Prüft eine (unverschlüsselte) Sicherung. Gibt Kennzahlen zurück oder wirft ValueError mit verständlichem Grund."""
    from .server import SCHEMA_VERSION
    p = Path(path)
    head = p.read_bytes()[:16] if p.exists() else b''
    if head != b'SQLite format 3\x00':
        raise ValueError('Keine SignalDesk-Sicherung (keine SQLite-Datenbank).')
    try:
        c = _open_ro(p)
        try:
            ok = c.execute('PRAGMA integrity_check').fetchone()[0]
            if ok != 'ok':
                raise ValueError(f'Sicherung ist beschädigt ({ok[:120]}).')
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            if missing:
                raise ValueError('Keine SignalDesk-Datenbank (es fehlen: ' + ', '.join(missing) + ').')
            version = c.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError(f'Sicherung stammt aus einer neueren SignalDesk-Version (Schema {version} > {SCHEMA_VERSION}) – zuerst SignalDesk aktualisieren.')
            count = lambda t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] if t in tables else 0
            numbers = sorted(r[0] for r in c.execute("SELECT number FROM invoices WHERE status<>'entwurf' AND number IS NOT NULL")) if 'invoices' in tables else []
            return {'schema': version, 'leads': count('leads'), 'invoices': count('invoices'), 'proposals': count('proposals'),
                    'tasks': count('tasks'), 'final_invoices': numbers}
        finally:
            c.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'Sicherung nicht lesbar ({exc}).') from exc


def _current(db_path):
    try:
        return inspect(db_path), None
    except ValueError as exc:
        return None, str(exc)


def _plain_copy(src, password, tmp):
    """Gibt den Pfad einer unverschlüsselten Kopie zurück (entschlüsselt .sdenc)."""
    src = Path(src)
    raw = src.read_bytes()[:6]
    from .backup_crypto import MAGIC
    if raw == MAGIC:
        if not password:
            raise ValueError('Verschlüsselte Sicherung: Passwort angeben.')
        from .backup_crypto import available, decrypt_bytes
        if not available():
            raise ValueError('Zum Entschlüsseln wird das Paket „cryptography“ benötigt (Installationsvariante „Team“).')
        plain = decrypt_bytes(src.read_bytes(), password)
        out = Path(tmp) / 'restore.sqlite3'
        out.write_bytes(plain)
        return out
    out = Path(tmp) / 'restore.sqlite3'
    shutil.copyfile(src, out)
    return out


def restore(db_path, source, password=None, confirm=False):
    """Stellt `source` (Pfad) als aktuelle Datenbank `db_path` wieder her. Gibt eine Zusammenfassung zurück."""
    from .accounting_api import create_backup
    from .server import prepare_database
    if confirm is not True:
        raise ValueError('Wiederherstellen ersetzt den aktuellen Stand – bitte ausdrücklich bestätigen (confirm: true).')
    db_path = Path(db_path)
    with tempfile.TemporaryDirectory() as tmp:
        plain = _plain_copy(source, password, tmp)
        incoming = inspect(plain)
        current, broken = _current(db_path) if db_path.exists() else ({'leads': 0, 'invoices': 0, 'final_invoices': []}, None)
        if current:
            lost = sorted(set(current['final_invoices']) - set(incoming['final_invoices']))
            if lost:
                raise ValueError('Abgelehnt (GoBD): In der Sicherung fehlen festgeschriebene Rechnungen, die es jetzt gibt: '
                                 + ', '.join(lost[:10]) + (' …' if len(lost) > 10 else '') + '. Eine neuere Sicherung wählen.')
        safety = None
        if db_path.exists() and current:
            safety = create_backup(db_path)['path']
            renamed = Path(safety).with_name(Path(safety).stem + '-vor-wiederherstellung.sqlite3')
            n = 1
            while renamed.exists():  # zwei Wiederherstellungen in derselben Sekunde: nie eine frühere Sicherung überschreiben
                n += 1
                renamed = Path(safety).with_name(f'{Path(safety).stem}-vor-wiederherstellung-{n}.sqlite3')
            Path(safety).rename(renamed)
            safety = str(renamed)
        elif db_path.exists():
            # beschädigt: Datei unverändert beiseitelegen, nichts überschreiben, was sich nicht lesen ließ
            folder = backup_dir(db_path)
            folder.mkdir(parents=True, exist_ok=True)
            safety = str(folder / f"signaldesk-{dt.datetime.now():%Y%m%d-%H%M%S}-beschaedigt.sqlite3")
            shutil.copyfile(db_path, safety)
        if current or not db_path.exists():
            src = sqlite3.connect(str(plain))
            dst = sqlite3.connect(str(db_path), timeout=30)
            try:
                src.backup(dst)  # atomar, auch während SignalDesk läuft
            finally:
                dst.close()
                src.close()
        else:  # beschädigt – SQLite kann die Datei nicht öffnen, also ersetzen (beschädigte Fassung liegt als Kopie bereit)
            for suffix in ('-wal', '-shm'):
                Path(str(db_path) + suffix).unlink(missing_ok=True)
            shutil.copyfile(plain, db_path)
    prepare_database(db_path)  # auf das aktuelle Schema migrieren, Aufträge wieder aufnehmen
    after = inspect(db_path)
    return {'restored': True, 'from': Path(source).name, 'safety_backup': safety, 'current_was_broken': broken,
            'before': {k: current[k] for k in ('leads', 'invoices')} if current else None,
            'after': {k: after[k] for k in ('leads', 'invoices', 'proposals', 'tasks')}, 'schema': after['schema'],
            'notice': 'Wiederhergestellt. Der vorherige Stand liegt als Sicherung „…-vor-wiederherstellung“ bereit.'}


def restore_named(db_path, name, password=None, confirm=False):
    if not isinstance(name, str) or not NAME_RE.match(name) or '/' in name or '\\' in name:
        raise ValueError('Ungültiger Sicherungsname.')
    path = backup_dir(db_path) / name
    if not path.exists():
        raise LookupError('Sicherung nicht gefunden.')
    return restore(db_path, path, password, confirm)


def restore_upload(h, db_path, password=None, confirm=False):
    raw_len = h.headers.get('Content-Length', '0')
    if not raw_len.isdigit() or not 0 < int(raw_len) <= MAX_UPLOAD:
        raise ValueError('Datei leer oder zu groß.')
    left = int(raw_len)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'upload.bin'
        with open(target, 'wb') as f:
            while left:
                chunk = h.rfile.read(min(1024 * 1024, left))
                if not chunk:
                    raise ValueError('Übertragung abgebrochen.')
                f.write(chunk)
                left -= len(chunk)
        res = restore(db_path, target, password, confirm)
        res['from'] = 'hochgeladene Datei'
        return res


def route_restore(h, conn, method, route, query, db_path):
    if route == '/api/backups/all' and method == 'GET':
        h._send(200, list_all(db_path))
        return True
    if route == '/api/backups/restore' and method == 'POST':
        b = h._body()
        if set(b) - {'name', 'password', 'confirm'} or 'name' not in b:
            raise ValueError('Erwartet: {name, password?, confirm: true}.')
        conn.commit()
        h._send(200, restore_named(db_path, b['name'], b.get('password'), b.get('confirm')))
        return True
    if route == '/api/backups/restore-upload' and method == 'POST':
        get = lambda k: (query.get(k, ['']) or [''])[0]
        if h.headers.get('Content-Type', '').split(';')[0].strip() != 'application/octet-stream':
            raise ValueError('Bitte als application/octet-stream senden.')
        password = h.headers.get('X-Backup-Password') or None
        h._send(200, restore_upload(h, db_path, password, get('confirm') == '1'))
        return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description='SignalDesk-Sicherung wiederherstellen')
    sub = ap.add_subparsers(dest='cmd', required=True)
    ls = sub.add_parser('liste', help='Sicherungen anzeigen')
    ls.add_argument('--db', default=str(Path.home() / '.akquise-tool' / 'akquise.sqlite3'))
    rs = sub.add_parser('wiederherstellen', help='Sicherung einspielen (der aktuelle Stand wird vorher gesichert)')
    rs.add_argument('datei')
    rs.add_argument('--db', default=str(Path.home() / '.akquise-tool' / 'akquise.sqlite3'))
    rs.add_argument('--ja', action='store_true', help='ohne Rückfrage')
    a = ap.parse_args(argv)
    db = Path(a.db).expanduser().resolve()
    if a.cmd == 'liste':
        for b in list_all(db)['backups']:
            print(f"{b['modified']}  {b['size_bytes'] / 1e6:8.1f} MB  {'verschlüsselt ' if b['encrypted'] else ''}{b['name']}")
        return 0
    src = Path(a.datei)
    if not src.exists():
        src = backup_dir(db) / a.datei
    if not a.ja and input(f'„{src.name}“ wiederherstellen? Der aktuelle Stand wird vorher gesichert. [j/N] ').strip().lower() not in ('j', 'ja', 'y'):
        print('Abgebrochen.')
        return 1
    password = getpass.getpass('Passwort der Sicherung: ') if src.suffix == '.sdenc' else None
    try:
        r = restore(db, src, password, confirm=True)
    except (ValueError, LookupError, OSError) as exc:
        print('Fehler:', exc)
        return 1
    print(f"Wiederhergestellt: {r['after']['leads']} Leads, {r['after']['invoices']} Rechnungen (Schema {r['schema']}).")
    if r['safety_backup']:
        print('Vorheriger Stand gesichert:', r['safety_backup'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
