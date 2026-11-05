"""Verschlüsselte Datensicherung (Phase 6, optional).

Format `.sdenc`: b'SDENC1' | salt (16) | nonce (12) | AES-256-GCM(Datenbank-Kopie). Der Schlüssel wird mit scrypt
(n=2^15, r=8, p=1) aus dem Passwort abgeleitet. Das Passwort wird nirgends gespeichert – ohne Passwort ist die
Sicherung nicht wiederherstellbar.

Benötigt das optionale Paket `cryptography` (requirements-team.txt). Fehlt es, bleibt die normale Sicherung verfügbar.

Entschlüsseln: python -m sales_tool.backup_crypto entschluesseln <datei.sdenc> <ziel.sqlite3>
"""
from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

MAGIC = b'SDENC1'
MIN_PASSWORD = 12


def available():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except ImportError:
        return False


def _key(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


def encrypt_bytes(data, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    return MAGIC + salt + nonce + AESGCM(_key(password, salt)).encrypt(nonce, data, MAGIC)


def decrypt_bytes(blob, password):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28 + 16:
        raise ValueError('Keine SignalDesk-Sicherung (.sdenc).')
    salt, nonce, body = blob[6:22], blob[22:34], blob[34:]
    try:
        return AESGCM(_key(password, salt)).decrypt(nonce, body, MAGIC)
    except InvalidTag as exc:
        raise ValueError('Passwort falsch oder Datei beschädigt.') from exc


def create_encrypted_backup(db_path, data):
    if not available():
        raise ValueError("Verschlüsselte Sicherung braucht das optionale Paket „cryptography“ (pip install -r requirements-team.txt). "
                         "Die normale Sicherung funktioniert weiterhin.")
    if not isinstance(data, dict) or set(data) != {'password'} or not isinstance(data['password'], str) or len(data['password']) < MIN_PASSWORD:
        raise ValueError(f'Passwort für die Sicherung: mindestens {MIN_PASSWORD} Zeichen. Es wird nicht gespeichert.')
    from .accounting_api import _backup_dir
    folder = _backup_dir(db_path)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'copy.sqlite3'
        src, dst = sqlite3.connect(str(db_path)), sqlite3.connect(str(copy))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        blob = encrypt_bytes(copy.read_bytes(), data['password'])
    target = folder / f"signaldesk-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.sdenc"
    n = 1
    while target.exists():
        target = target.with_name(target.stem + f'-{n}.sdenc')
        n += 1
    target.write_bytes(blob)
    return {'saved': True, 'path': str(target), 'size_bytes': len(blob),
            'notice': 'Verschlüsselte Sicherung erstellt (AES-256-GCM). Ohne das Passwort ist sie nicht wiederherstellbar – Passwort sicher aufbewahren.'}


def decrypt_file(src, dst, password):
    plain = decrypt_bytes(Path(src).read_bytes(), password)
    if not plain.startswith(b'SQLite format 3\x00'):
        raise ValueError('Entschlüsselter Inhalt ist keine SQLite-Datenbank.')
    if Path(dst).exists():
        raise ValueError('Zieldatei existiert bereits – bitte einen neuen Dateinamen wählen.')
    Path(dst).write_bytes(plain)
    return str(dst)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 3 or argv[0] != 'entschluesseln':
        print('Aufruf: python -m sales_tool.backup_crypto entschluesseln <datei.sdenc> <ziel.sqlite3>')
        return 2
    try:
        print('Entschlüsselt:', decrypt_file(argv[1], argv[2], getpass.getpass('Passwort der Sicherung: ')))
    except (ValueError, OSError, ImportError) as exc:
        print('Fehler:', exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
