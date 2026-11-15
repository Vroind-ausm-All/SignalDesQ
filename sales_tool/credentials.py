"""Zugangsdaten für Kalender (CalDAV) und Postfach (IMAP) – nie in der Datenbank (2.0.0-dev42, Produktreview M24).

- Standard: nur im Arbeitsspeicher, solange SignalDesk läuft. Nach einem Neustart fragt SignalDesk erneut.
- Auf Wunsch „auf diesem Rechner merken“: eigene Datei `zugangsdaten.json` neben der Datenbank, nur für dein Benutzerkonto
  lesbar (Dateirechte 600, wo das Betriebssystem es zulässt). Sie liegt nicht in der Datenbank und damit in keiner Sicherung.
- Die Oberfläche bekommt Passwörter nie zurück, nur „hinterlegt: ja/nein“.
- Empfehlung: ein App-Passwort des Anbieters statt des Hauptpassworts verwenden.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

KINDS = ('caldav', 'imap')
_MEMORY: dict = {}
_LOCK = threading.Lock()


def _file(db_path):
    return Path(db_path).resolve().parent / 'zugangsdaten.json'


def _read_file(db_path):
    f = _file(db_path)
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_file(db_path, data):
    f = _file(db_path)
    if not data:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_suffix('.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump(data, fh)
    os.replace(tmp, f)
    try:
        os.chmod(f, 0o600)
    except OSError:  # z. B. Windows: Rechte über das Benutzerprofil
        pass


def put(db_path, kind, password, remember=False):
    if kind not in KINDS:
        raise ValueError('Unbekannte Zugangsart.')
    if not isinstance(password, str) or not 1 <= len(password) <= 500:
        raise ValueError('Passwort fehlt oder ist zu lang.')
    key = str(Path(db_path).resolve())
    with _LOCK:
        _MEMORY.setdefault(key, {})[kind] = password
        data = _read_file(db_path)
        if remember:
            data[kind] = password
        else:
            data.pop(kind, None)
        _write_file(db_path, data)


def get(db_path, kind):
    key = str(Path(db_path).resolve())
    with _LOCK:
        pw = _MEMORY.get(key, {}).get(kind)
        if pw is None:
            pw = _read_file(db_path).get(kind)
            if pw is not None:
                _MEMORY.setdefault(key, {})[kind] = pw
        return pw


def forget(db_path, kind):
    key = str(Path(db_path).resolve())
    with _LOCK:
        _MEMORY.get(key, {}).pop(kind, None)
        data = _read_file(db_path)
        data.pop(kind, None)
        _write_file(db_path, data)


def status(db_path, kind):
    return {'stored': get(db_path, kind) is not None, 'remembered': kind in _read_file(db_path)}
