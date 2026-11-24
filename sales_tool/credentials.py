"""Zugangsdaten für Kalender (CalDAV) und Postfach (IMAP) – nie in der Datenbank, nie im Klartext auf dem Datenträger.

Seit 2.0.0-dev55 (SDQ-004, Audit B3):
- Standard: nur im Arbeitsspeicher, solange SignalDesk läuft. Nach einem Neustart fragt SignalDesk erneut.
- „Merken“ legt das Passwort im Passwortspeicher des Betriebssystems ab, sofern einer verfügbar ist:
  1. das Paket `keyring`, falls installiert (Schlüsselbund unter macOS, Anmeldeinformationsverwaltung unter Windows,
     Secret Service unter Linux),
  2. Windows ohne `keyring`: DPAPI (an das Windows-Benutzerkonto gebunden verschlüsselt, Datei `zugangsdaten.dpapi.json`),
  3. Linux ohne `keyring`: `secret-tool` (libsecret); das Passwort geht über die Standardeingabe, nie über die Befehlszeile.
  Ohne sicheren Speicher bleibt das Passwort nur bis zum Neustart – es wird nichts im Klartext geschrieben.
- Altbestand: Frühere Versionen schrieben bei „merken“ `zugangsdaten.json` im Klartext. Beim ersten Lesen wandert ein Eintrag
  in den sicheren Speicher und wird aus der Datei entfernt. Ohne sicheren Speicher wird er nur noch gelesen (nie neu geschrieben)
  und die Oberfläche bittet, das Passwort neu einzugeben; beim Neu-Eingeben oder „Vergessen“ verschwindet der Klartext-Eintrag.
- Die Oberfläche bekommt Passwörter nie zurück, nur „hinterlegt: ja/nein“ und welcher Speicher benutzt wird.
- Rotation: neues Passwort eingeben ersetzt das alte überall; Widerruf: „Vergessen“ löscht es aus Arbeitsspeicher, sicherem
  Speicher und Altdatei. Empfehlung: ein App-Passwort des Anbieters statt des Hauptpassworts verwenden.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

KINDS = ('caldav', 'imap')
SERVICE = 'SignalDesk'
_MEMORY: dict = {}
_LOCK = threading.Lock()
_BACKEND = None          # für Tests austauschbar (set_backend)
_BACKEND_CHOSEN = False


# ---------------------------------------------------------------- Speicher des Betriebssystems

class _Keyring:
    name = 'Passwortspeicher des Betriebssystems (keyring)'

    def __init__(self, module):
        self.k = module

    def get(self, account):
        return self.k.get_password(SERVICE, account)

    def set(self, account, secret):
        self.k.set_password(SERVICE, account, secret)

    def delete(self, account):
        try:
            self.k.delete_password(SERVICE, account)
        except Exception:  # nicht vorhanden – nichts zu löschen
            pass


class _SecretTool:
    name = 'Linux-Schlüsselbund (Secret Service)'

    def __init__(self, exe):
        self.exe = exe

    def _run(self, args, data=None):
        return subprocess.run([self.exe, *args], input=data, capture_output=True, text=True, timeout=15)

    def get(self, account):
        r = self._run(['lookup', 'service', SERVICE, 'account', account])
        return r.stdout if r.returncode == 0 and r.stdout else None

    def set(self, account, secret):
        r = self._run(['store', '--label', f'{SERVICE} {account}', 'service', SERVICE, 'account', account], data=secret)
        if r.returncode != 0:
            raise OSError('Schlüsselbund hat das Passwort nicht angenommen.')

    def delete(self, account):
        self._run(['clear', 'service', SERVICE, 'account', account])

    def usable(self):
        try:
            probe = self._run(['lookup', 'service', SERVICE, 'account', '__probe__'])
        except (OSError, subprocess.SubprocessError):
            return False
        return probe.returncode in (0, 1) and 'error' not in (probe.stderr or '').lower()


class _DPAPI:
    """Windows: CryptProtectData – nur dieses Windows-Benutzerkonto kann entschlüsseln. Datei neben der Datenbank."""
    name = 'Windows-Datenschutz (DPAPI)'

    def __init__(self, folder):
        self.folder = Path(folder)

    @staticmethod
    def _crypt(data: bytes, protect: bool) -> bytes:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in, blob_out = BLOB(len(data), buf), BLOB()
        entropy_raw = SERVICE.encode()
        ebuf = ctypes.create_string_buffer(entropy_raw, len(entropy_raw))
        entropy = BLOB(len(entropy_raw), ebuf)
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        ok = fn(ctypes.byref(blob_in), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(blob_out))  # 0x1: keine Rückfrage
        if not ok:
            raise OSError('DPAPI fehlgeschlagen.')
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)

    def _file(self):
        return self.folder / 'zugangsdaten.dpapi.json'

    def _load(self):
        try:
            data = json.loads(self._file().read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data):
        f = self._file()
        if not data:
            f.unlink(missing_ok=True)
            return
        tmp = f.with_suffix('.tmp')
        tmp.write_text(json.dumps(data), encoding='utf-8')
        os.replace(tmp, f)

    def get(self, account):
        enc = self._load().get(account)
        if not enc:
            return None
        try:
            return self._crypt(base64.b64decode(enc), False).decode('utf-8')
        except (OSError, ValueError):
            return None

    def set(self, account, secret):
        data = self._load()
        data[account] = base64.b64encode(self._crypt(secret.encode('utf-8'), True)).decode('ascii')
        self._save(data)

    def delete(self, account):
        data = self._load()
        if data.pop(account, None) is not None:
            self._save(data)


def _detect(db_path):
    try:
        import keyring  # optional
        from keyring.backends import fail
        if not isinstance(keyring.get_keyring(), fail.Keyring):
            return _Keyring(keyring)
    except Exception:  # nicht installiert oder ohne nutzbaren Speicher
        pass
    if os.name == 'nt':
        return _DPAPI(Path(db_path).resolve().parent)
    exe = shutil.which('secret-tool')
    if exe and os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        st = _SecretTool(exe)
        if st.usable():
            return st
    return None


def set_backend(backend):
    """Speicher festlegen (Tests, Diagnose). None = kein sicherer Speicher; 'auto' = neu erkennen."""
    global _BACKEND, _BACKEND_CHOSEN
    with _LOCK:
        _BACKEND, _BACKEND_CHOSEN = (None, False) if backend == 'auto' else (backend, True)


def _backend(db_path):
    global _BACKEND, _BACKEND_CHOSEN
    if not _BACKEND_CHOSEN:
        _BACKEND, _BACKEND_CHOSEN = _detect(db_path), True
    return _BACKEND


def _account(db_path, kind):
    # je Installation (Datenbankpfad) ein eigener Eintrag; der Pfad selbst steht nicht im Schlüsselbund
    return f"{kind}:{hashlib.sha256(str(Path(db_path).resolve()).encode()).hexdigest()[:16]}"


# ---------------------------------------------------------------- Altdatei (Klartext, nur noch lesen und abbauen)

def _legacy_file(db_path):
    return Path(db_path).resolve().parent / 'zugangsdaten.json'


def _legacy_read(db_path):
    f = _legacy_file(db_path)
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _legacy_drop(db_path, kind):
    """Eintrag aus der Klartext-Altdatei entfernen; leere Datei wird gelöscht. Andere Einträge bleiben unverändert."""
    data = _legacy_read(db_path)
    if kind not in data:
        return
    data.pop(kind)
    f = _legacy_file(db_path)
    if not data:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_suffix('.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump(data, fh)
    os.replace(tmp, f)


# ---------------------------------------------------------------- Schnittstelle (unverändert)

def put(db_path, kind, password, remember=False):
    """Passwort setzen. remember=True legt es im sicheren Speicher ab, falls vorhanden; sonst nur bis zum Neustart.
    Gibt zurück, ob es gemerkt wurde."""
    if kind not in KINDS:
        raise ValueError('Unbekannte Zugangsart.')
    if not isinstance(password, str) or not 1 <= len(password) <= 500:
        raise ValueError('Passwort fehlt oder ist zu lang.')
    key = str(Path(db_path).resolve())
    with _LOCK:
        _MEMORY.setdefault(key, {})[kind] = password
        backend = _backend(db_path)
        remembered = False
        if backend is not None:
            if remember:
                try:
                    backend.set(_account(db_path, kind), password)
                    remembered = True
                except Exception:  # Speicher verweigert: bis zum Neustart im Arbeitsspeicher
                    remembered = False
            else:
                backend.delete(_account(db_path, kind))
        _legacy_drop(db_path, kind)  # neues Passwort ersetzt einen alten Klartext-Eintrag
        return remembered


def get(db_path, kind):
    key = str(Path(db_path).resolve())
    with _LOCK:
        pw = _MEMORY.get(key, {}).get(kind)
        if pw is not None:
            return pw
        backend = _backend(db_path)
        if backend is not None:
            try:
                pw = backend.get(_account(db_path, kind))
            except Exception:
                pw = None
        if pw is None:
            pw = _legacy_read(db_path).get(kind)
            if pw is not None and backend is not None:
                try:  # Altbestand in den sicheren Speicher übernehmen, dann aus der Klartext-Datei entfernen
                    backend.set(_account(db_path, kind), pw)
                    _legacy_drop(db_path, kind)
                except Exception:
                    pass
        if pw is not None:
            _MEMORY.setdefault(key, {})[kind] = pw
        return pw


def forget(db_path, kind):
    key = str(Path(db_path).resolve())
    with _LOCK:
        _MEMORY.get(key, {}).pop(kind, None)
        backend = _backend(db_path)
        if backend is not None:
            backend.delete(_account(db_path, kind))
        _legacy_drop(db_path, kind)


def _remembered(db_path, kind):
    backend = _backend(db_path)
    if backend is None:
        return False
    try:
        return backend.get(_account(db_path, kind)) is not None
    except Exception:
        return False


def status(db_path, kind):
    stored = get(db_path, kind) is not None  # übernimmt dabei ggf. den Altbestand
    return {'stored': stored, 'remembered': _remembered(db_path, kind)}


def store_info(db_path, kind=None):
    """Für die Oberfläche: Gibt es einen sicheren Speicher, und liegt noch ein Klartext-Altbestand vor?"""
    backend = _backend(db_path)
    legacy = _legacy_read(db_path)
    return {'secure_store': backend is not None, 'store_name': backend.name if backend is not None else '',
            'legacy_plaintext': bool(legacy.get(kind)) if kind else bool(legacy),
            'notice': ('Gemerkt wird im ' + backend.name + '.') if backend is not None else
                      'Auf diesem Rechner steht kein sicherer Passwortspeicher bereit – das Passwort gilt bis zum Neustart.'}
