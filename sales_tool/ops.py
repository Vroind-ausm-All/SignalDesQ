"""Betrieb einer Mehrmandanten-Installation (SDQ-017 bis SDQ-019).

- **Zustand** (SDQ-017): ``health`` (lebt der Prozess?) und ``readiness`` (kann er arbeiten? Verzeichnis beschreibbar, jede
  aktive Organisation lesbar und auf dem aktuellen Schema, genug freier Speicher, letzte geprüfte Sicherung nicht zu alt).
- **Sicherung aller Organisationen** (SDQ-018): ``backup_all`` legt einen Satz an – Verzeichnis plus jede Organisation
  (auch archivierte, wegen der Aufbewahrungspflicht) –, optional verschlüsselt (AES-256-GCM wie ``backup_crypto``).
  ``verify_backup`` ist der **Wiederherstellungstest**: Prüfsummen, Entschlüsseln, ``integrity_check``, Zeilenzahlen gegen das
  Manifest, Migration einer Kopie auf das aktuelle Schema. ``restore_org`` spielt eine Organisation aus einem Satz zurück
  (über ``backup_restore.restore``: GoBD-Schutz, vorherige Sicherung, Migration).
- **Protokolle** (SDQ-019): ``access_logger`` schreibt je Anfrage eine JSON-Zeile (Zeit, Anfrage-Nummer, Methode, Pfad ohne
  Abfrage und ohne Kennungen, Status, Dauer, Organisation). Keine Cookies, keine Abfrageparameter, keine Inhalte, keine IP.

Gelöscht wird hier nichts automatisch: Alte Sicherungen entfernt ``prune_backups`` nur, wenn der Betreiber es ausdrücklich
aufruft (``--behalten N``).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import logging
import logging.handlers
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from . import __version__, audit_trail

BACKUP_FORMAT = 'signaldesk-sicherungssatz/1'
BACKUP_DIR = 'sicherungen'
SET_RE = re.compile(r'^\d{8}-\d{6}(-\d+)?$')
MIN_FREE_BYTES = 512 * 1024 ** 2
MAX_BACKUP_AGE_HOURS = 26  # tägliche Sicherung plus Puffer


# ---------------------------------------------------------------- Zustand (SDQ-017)

def health():
    return {'status': 'ok', 'version': __version__}


def _schema_version():
    from .server import SCHEMA_VERSION
    return SCHEMA_VERSION


def readiness(directory, detail=False, backup_target=None):
    """Bereitschaft. ``detail`` nur für den lokalen Aufruf (nennt Kennungen der Organisationen).
    ``backup_target``: Ordner der Sicherungssätze, falls nicht ``<root>/sicherungen``."""
    checks = []

    def check(name, ok, info='', warn=False):
        checks.append({'name': name, 'ok': bool(ok), 'level': 'ok' if ok else ('warnung' if warn else 'fehler'), 'info': info})

    try:
        with contextlib.closing(sqlite3.connect(str(directory.root / 'organisationen.sqlite3'), timeout=3, isolation_level=None)) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('ROLLBACK')
        check('verzeichnis', True)
    except sqlite3.Error as exc:
        check('verzeichnis', False, f'nicht beschreibbar ({exc.__class__.__name__})')
    want, bad, orgs = _schema_version(), [], []
    try:
        orgs = directory.list()
    except Exception as exc:  # noqa: BLE001
        bad.append(f'Verzeichnis nicht lesbar ({exc.__class__.__name__})')
    for org in orgs:
        try:
            with contextlib.closing(sqlite3.connect(f"file:{Path(org['db_path']).as_posix()}?mode=ro", uri=True, timeout=3)) as c:
                version = c.execute('PRAGMA user_version').fetchone()[0]
            if version != want:
                bad.append(f"{org['slug']}: Schema {version} statt {want}")
        except sqlite3.Error as exc:
            bad.append(f"{org['slug']}: {exc.__class__.__name__}")
    check('organisationen', not bad, (f'{len(orgs)} aktiv' if not bad else f'{len(bad)} nicht bereit')
          + ((': ' + '; '.join(bad)) if bad and detail else ''))
    free = shutil.disk_usage(directory.root).free
    check('speicher', free >= MIN_FREE_BYTES, f'{free // 1024 ** 2} MB frei')
    last = last_verified_backup(directory, backup_target)
    if last is None:
        check('sicherung', False, 'noch keine geprüfte Sicherung', warn=True)
    else:
        age = (dt.datetime.now(dt.timezone.utc) - last).total_seconds() / 3600
        check('sicherung', age <= MAX_BACKUP_AGE_HOURS, f'letzte geprüfte Sicherung vor {age:.0f} h', warn=True)
    ready = all(c['ok'] or c['level'] == 'warnung' for c in checks)
    return {'status': 'bereit' if ready else 'nicht_bereit', 'version': __version__, 'checks': checks}


# ---------------------------------------------------------------- Sicherung (SDQ-018)

def backup_root(directory, target=None):
    return Path(target).expanduser().resolve() if target else directory.root / BACKUP_DIR


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _counts(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    out = {}
    for t in sorted(tables):
        try:
            out[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        except sqlite3.DatabaseError:  # virtuelle Tabellen (FTS) ohne Modul
            continue
    return out


def _snapshot(src_path, dst_path):
    """Konsistente Kopie über die SQLite-Backup-Schnittstelle (auch bei laufendem Server)."""
    src = sqlite3.connect(f'file:{Path(src_path).as_posix()}?mode=ro', uri=True, timeout=30)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')  # eine einzige Datei, kein -wal daneben (sonst gingen Änderungen an der Prüfsumme vorbei)
        version = dst.execute('PRAGMA user_version').fetchone()[0]
        counts = _counts(dst)
    finally:
        dst.close()
        src.close()
    return version, counts


def _check_password(password):
    from .backup_crypto import MIN_PASSWORD, available
    if not available():
        raise ValueError('Verschlüsselung braucht das optionale Paket „cryptography“ (pip install -r requirements-team.txt).')
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValueError(f'Passwort: mindestens {MIN_PASSWORD} Zeichen. Es wird nicht gespeichert.')


def backup_all(directory, target=None, password=None, actor=None):
    """Sicherungssatz aller Organisationen anlegen. Gibt das Manifest zurück.

    Ablauf: Kopien in ``<stamp>.unfertig`` schreiben, Manifest zuletzt, dann umbenennen – ein abgebrochener Lauf hinterlässt
    nie einen Satz, der wie ein vollständiger aussieht.
    """
    if password is not None:
        _check_password(password)
    root = backup_root(directory, target)
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    name, n = stamp, 1
    while (root / name).exists() or (root / f'{name}.unfertig').exists():
        name = f'{stamp}-{n}'
        n += 1
    work = root / f'{name}.unfertig'
    (work / 'orgs').mkdir(parents=True)
    files = []
    started = time.monotonic()
    try:
        items = [('organisationen.sqlite3', None, directory.root / 'organisationen.sqlite3')]
        items += [(f"orgs/{o['slug']}.sqlite3", o['slug'], Path(o['db_path'])) for o in directory.list(include_archived=True)]
        for rel, slug, src in items:
            out = work / rel
            version, counts = _snapshot(src, out)
            if password is not None:
                from .backup_crypto import encrypt_bytes
                enc = out.with_suffix('.sdenc')
                enc.write_bytes(encrypt_bytes(out.read_bytes(), password))
                out.unlink()
                out, rel = enc, rel[:-len('.sqlite3')] + '.sdenc'
            files.append({'file': rel, 'slug': slug, 'schema': version, 'bytes': out.stat().st_size, 'sha256': _sha256(out),
                          'rows': counts})
        manifest = {'format': BACKUP_FORMAT, 'name': name, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                    'version': __version__, 'encrypted': password is not None, 'organizations': sum(1 for f in files if f['slug']),
                    'seconds': round(time.monotonic() - started, 2), 'files': files}
        (work / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
        work.rename(root / name)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)  # nur der eigene, unfertige Ordner dieses Laufs
        raise
    audit_trail.record(directory, actor or audit_trail.operator(), 'sicherung_angelegt', name,
                       f"{manifest['organizations']} Organisation{'en' if manifest['organizations'] != 1 else ''}{', verschlüsselt' if password is not None else ''}")
    return {**manifest, 'path': str(root / name)}


def list_backups(directory, target=None):
    root = backup_root(directory, target)
    out = []
    if root.is_dir():
        for p in sorted(root.iterdir(), reverse=True):
            if p.is_dir() and SET_RE.match(p.name) and (p / 'manifest.json').exists():
                m = json.loads((p / 'manifest.json').read_text(encoding='utf-8'))
                check = json.loads((p / 'pruefung.json').read_text(encoding='utf-8')) if (p / 'pruefung.json').exists() else None
                out.append({'name': p.name, 'created_at': m['created_at'], 'encrypted': m['encrypted'],
                            'organizations': m['organizations'], 'verified': bool(check and check['ok']),
                            'verified_at': check['checked_at'] if check else ''})
    return out


def _set_dir(directory, name, target=None):
    if not isinstance(name, str) or not SET_RE.match(name):
        raise ValueError('Ungültiger Name eines Sicherungssatzes (JJJJMMTT-HHMMSS).')
    path = backup_root(directory, target) / name
    if not (path / 'manifest.json').exists():
        raise LookupError(f'Sicherungssatz „{name}“ nicht gefunden.')
    return path


def _plain(path, password, tmp):
    from .backup_restore import _plain_copy
    return _plain_copy(path, password, tmp)


def verify_backup(directory, name, target=None, password=None, actor=None):
    """Wiederherstellungstest eines Satzes. Schreibt das Ergebnis nach ``pruefung.json`` und gibt es zurück."""
    from .model import init_db
    folder = _set_dir(directory, name, target)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != BACKUP_FORMAT:
        raise ValueError('Unbekanntes Format des Sicherungssatzes.')
    if manifest['encrypted'] and not password:
        raise ValueError('Verschlüsselter Satz: Passwort angeben.')
    results, started = [], time.monotonic()
    for f in manifest['files']:
        r = {'file': f['file'], 'slug': f['slug'], 'ok': False, 'problem': ''}
        results.append(r)
        path = folder / f['file']
        try:
            if path.resolve().parent not in (folder.resolve(), (folder / 'orgs').resolve()):
                raise ValueError('Pfad außerhalb des Satzes.')
            if not path.exists():
                raise ValueError('Datei fehlt.')
            if _sha256(path) != f['sha256']:
                raise ValueError('Prüfsumme stimmt nicht (Datei verändert oder beschädigt).')
            with tempfile.TemporaryDirectory() as tmp:
                plain = _plain(path, password, tmp)
                with contextlib.closing(sqlite3.connect(str(plain))) as c:
                    ok = c.execute('PRAGMA integrity_check').fetchone()[0]
                    if ok != 'ok':
                        raise ValueError(f'integrity_check: {ok[:120]}')
                    counts = _counts(c)
                    diff = sorted(t for t, n in f['rows'].items() if counts.get(t) != n)
                    if diff:
                        raise ValueError('Zeilenzahlen weichen ab: ' + ', '.join(diff[:8]))
                    if f['slug'] is None:
                        orgs = {row[0] for row in c.execute('SELECT slug FROM organizations')}
                        missing = sorted({x['slug'] for x in manifest['files'] if x['slug']} - orgs)
                        if missing:
                            raise ValueError('Verzeichnis kennt nicht alle Organisationen: ' + ', '.join(missing))
                    else:
                        if c.execute('PRAGMA user_version').fetchone()[0] > _schema_version():
                            raise ValueError('Schema neuer als dieses Programm.')
                if f['slug'] is not None:  # Migration auf das aktuelle Schema an einer Kopie – wie beim Zurückspielen
                    from .model import connect
                    with connect(plain) as conn:
                        init_db(conn)
                        conn.commit()
                        r['rows_after_migration'] = sum(_counts(conn).get(t, 0) for t in ('leads', 'activities', 'invoices'))
            r['ok'] = True
        except (ValueError, sqlite3.DatabaseError, OSError) as exc:
            r['problem'] = str(exc)[:300]
    report = {'name': name, 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'version': __version__,
              'ok': all(r['ok'] for r in results), 'files': results, 'seconds': round(time.monotonic() - started, 2)}
    (folder / 'pruefung.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    audit_trail.record(directory, actor or audit_trail.operator(), 'sicherung_geprueft', name,
                       'in Ordnung' if report['ok'] else 'FEHLER: ' + '; '.join(f"{r['file']}: {r['problem']}" for r in results if not r['ok']))
    return report


def last_verified_backup(directory, target=None):
    for b in list_backups(directory, target):
        if b['verified']:
            return dt.datetime.fromisoformat(b['verified_at'])
    return None


def restore_org(directory, name, slug, target=None, password=None, confirm=False, actor=None):
    """Eine Organisation aus einem Sicherungssatz zurückspielen (der Satz wird vorher geprüft)."""
    from .backup_restore import restore
    folder = _set_dir(directory, name, target)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    entry = next((f for f in manifest['files'] if f['slug'] == slug), None)
    if not entry:
        raise LookupError(f'Organisation „{slug}“ ist in diesem Satz nicht enthalten.')
    if confirm is not True:
        raise ValueError('Zurückspielen ersetzt den aktuellen Stand der Organisation – ausdrücklich bestätigen (--ja).')
    source = folder / entry['file']
    if _sha256(source) != entry['sha256']:
        raise ValueError('Prüfsumme stimmt nicht – Satz nicht verwenden.')
    org = directory.get(slug)
    out = restore(org['db_path'], source, password=password, confirm=True)
    audit_trail.record(directory, actor or audit_trail.operator(), 'organisation_zurueckgespielt', slug,
                       f"aus {name}; vorher gesichert: {Path(out['safety_backup']).name if out.get('safety_backup') else '–'}")
    return out


def prune_backups(directory, keep, target=None, actor=None):
    """Nur auf ausdrücklichen Aufruf: die ``keep`` neuesten vollständigen Sätze behalten, ältere entfernen.
    Der neueste geprüfte Satz bleibt immer erhalten."""
    if not isinstance(keep, int) or keep < 1:
        raise ValueError('Mindestens einen Satz behalten.')
    sets = list_backups(directory, target)
    newest_ok = next((b['name'] for b in sets if b['verified']), None)
    removed = []
    for b in sets[keep:]:
        if b['name'] == newest_ok:
            continue
        shutil.rmtree(_set_dir(directory, b['name'], target))
        removed.append(b['name'])
    if removed:
        audit_trail.record(directory, actor or audit_trail.operator(), 'sicherungen_entfernt', f'{len(removed)} Sätze',
                           ', '.join(removed)[:500])
    return {'kept': [b['name'] for b in sets if b['name'] not in removed], 'removed': removed}


# ---------------------------------------------------------------- Protokolle (SDQ-019)

_ID_SEGMENT = re.compile(r'^(\d+|[A-Za-z0-9_-]{20,})(\.[A-Za-z0-9]{1,5})?$')


def route_label(path):
    """Pfad fürs Protokoll: ohne Abfrage, Zahlen und lange Kennungen (z. B. Kalender-Token) ersetzt."""
    path = path.split('?', 1)[0].split('#', 1)[0][:200]
    return '/'.join(':id' if seg and _ID_SEGMENT.match(seg) else seg for seg in path.split('/'))


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {'ts': dt.datetime.fromtimestamp(record.created, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                'level': record.levelname.lower(), 'msg': record.getMessage()}
        data.update(getattr(record, 'fields', {}) or {})
        if record.exc_info:
            data['error'] = record.exc_info[0].__name__ if record.exc_info[0] else 'Exception'
        return json.dumps(data, ensure_ascii=False)


def access_logger(log_file=None, level='INFO', stream=None):
    """Logger ``signaldesk.betrieb``: JSON-Zeilen auf stderr oder in eine Datei (10 MB, 10 Generationen)."""
    logger = logging.getLogger('signaldesk.betrieb')
    logger.setLevel(level)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10 * 1024 ** 2, backupCount=10, encoding='utf-8')
    else:
        handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def log_request(logger, *, rid, method, path, status, ms, org=None):
    if logger is None:
        return
    level = logging.ERROR if status >= 500 else logging.WARNING if status in (401, 403, 421, 429) else logging.INFO
    logger.log(level, 'anfrage', extra={'fields': {'rid': rid, 'method': method, 'route': route_label(path), 'status': status,
                                                   'ms': round(ms, 1), 'org': org or ''}})
