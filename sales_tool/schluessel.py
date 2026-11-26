"""Schlüssel der Mehrmandanten-Installation, getrennt von den Daten (2.0.0-dev68, Prüfbericht F06 und F09).

Der Schlüsselordner liegt **neben** dem Datenordner, nie darin: ``<root>.schluessel`` (z. B. ``/var/lib/signaldesk`` →
``/var/lib/signaldesk.schluessel``) oder der Ordner aus ``SIGNALDESK_SCHLUESSEL_ORDNER``. Sicherungssätze enthalten ihn nicht.
Wer die Installation auf einem Ersatzsystem wiederherstellt, braucht eine Kopie dieses Ordners (oder mindestens der
``mfa.key`` und des öffentlichen Sicherungsschlüssels).

- ``mfa.key``: Server-Schlüssel für die TOTP-Geheimnisse (32 Zufallsbytes). Die Geheimnisse stehen nur verschlüsselt in
  ``organisationen.sqlite3``: Encrypt-then-MAC mit HMAC-SHA256 – Schlüsselstrom im Zählermodus aus einem zufälligen
  16-Byte-Nonce, Prüfwert über Schlüssel-ID, Konto und Geheimtext. Nur Standardbibliothek, damit jede Variante (auch „basis“)
  dieselbe Speicherung hat. Ein Geheimnis ist an sein Konto gebunden: in eine andere Zeile kopiert, lässt es sich nicht öffnen.
- ``sicherung-ed25519.key`` / ``.pub``: Signaturschlüssel für Sicherungssätze (braucht das Paket ``cryptography``,
  Variante „team“). Signiert wird das Manifest; geprüft wird mit dem öffentlichen Schlüssel, auch auf einem leeren Ersatzsystem.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from pathlib import Path

MFA_PREFIX = 'sdq1:'
MFA_KEY_FILE = 'mfa.key'
SIGN_KEY_FILE = 'sicherung-ed25519.key'
SIGN_PUB_FILE = 'sicherung-ed25519.pub'
SIGNATURE_FILE = 'manifest.sig'
_HEADER_MFA = 'sdq-mfa-schluessel-v1'
_LOCK = threading.Lock()
_CACHE = {}


class KeyMissing(RuntimeError):
    """Schlüssel fehlt, wird aber gebraucht (z. B. verschlüsselte TOTP-Geheimnisse ohne ``mfa.key``)."""


class SignatureError(ValueError):
    """Signatur eines Sicherungssatzes fehlt, ist ungültig oder kann nicht geprüft werden."""


def key_dir(root) -> Path:
    """Schlüsselordner zur Installation ``root`` – immer außerhalb des Datenordners."""
    root = Path(root).expanduser().resolve()
    env = os.environ.get('SIGNALDESK_SCHLUESSEL_ORDNER')
    folder = Path(env).expanduser().resolve() if env else root.parent / f'{root.name}.schluessel'
    if folder == root or root in folder.parents:
        raise ValueError(f'Der Schlüsselordner „{folder}“ liegt im Datenordner – er muss getrennt liegen (sonst landet er in jeder Sicherung).')
    return folder


def _private_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='ascii') as fh:
        fh.write(text)


# ---------------------------------------------------------------- TOTP-Geheimnisse

def _key_id(master: bytes) -> str:
    return hashlib.sha256(b'sdq-key-id|' + master).hexdigest()[:8]


def mfa_key(root, create=True):
    """(Schlüssel-ID, 32 Bytes) aus ``mfa.key``. Legt ihn an, wenn er fehlt und ``create`` gilt; sonst ``KeyMissing``."""
    path = key_dir(root) / MFA_KEY_FILE
    with _LOCK:
        if str(path) in _CACHE and path.exists():
            return _CACHE[str(path)]
        if not path.exists():
            if not create:
                raise KeyMissing(f'Schlüssel für die Zwei-Faktor-Geheimnisse fehlt: {path}. Kopie aus der Schlüsselverwahrung '
                                 'zurücklegen (ohne ihn müssen alle Konten den zweiten Faktor neu einrichten: betreiber zwei-faktor-zuruecksetzen).')
            _private_write(path, f'{_HEADER_MFA} {secrets.token_hex(32)}\n')
        parts = path.read_text(encoding='ascii').split()
        if len(parts) != 2 or parts[0] != _HEADER_MFA or len(parts[1]) != 64:
            raise KeyMissing(f'Schlüsseldatei {path} ist beschädigt oder hat ein unbekanntes Format.')
        master = bytes.fromhex(parts[1])
        _CACHE[str(path)] = (_key_id(master), master)
        return _CACHE[str(path)]


def _subkeys(master):
    return hmac.new(master, b'sdq-mfa-enc', hashlib.sha256).digest(), hmac.new(master, b'sdq-mfa-mac', hashlib.sha256).digest()


def _stream(enc_key, nonce, n):
    out, ctr = b'', 0
    while len(out) < n:
        out += hmac.new(enc_key, nonce + ctr.to_bytes(4, 'big'), hashlib.sha256).digest()
        ctr += 1
    return out[:n]


def _tag(mac_key, key_id, account_id, nonce, ct):
    return hmac.new(mac_key, b'|'.join((b'sdq1', key_id.encode(), str(account_id).encode(), nonce + ct)), hashlib.sha256).digest()


def is_sealed(value) -> bool:
    return isinstance(value, str) and value.startswith(MFA_PREFIX)


def seal(root, account_id, secret: str) -> str:
    """TOTP-Geheimnis (Base32-Text) für die Datenbank verschlüsseln, gebunden an ``account_id``."""
    key_id, master = mfa_key(root)
    enc_key, mac_key = _subkeys(master)
    nonce = secrets.token_bytes(16)
    pt = secret.encode('ascii')
    ct = bytes(a ^ b for a, b in zip(pt, _stream(enc_key, nonce, len(pt))))
    blob = base64.urlsafe_b64encode(nonce + ct + _tag(mac_key, key_id, account_id, nonce, ct)).decode('ascii')
    return f'{MFA_PREFIX}{key_id}:{blob}'


def unseal(root, account_id, value: str) -> str:
    """Gegenstück zu ``seal``. Falscher Schlüssel, falsches Konto oder veränderter Wert → ``KeyMissing``/``ValueError``."""
    if not is_sealed(value):
        raise ValueError('TOTP-Geheimnis ist nicht verschlüsselt gespeichert.')
    key_id, master = mfa_key(root, create=False)
    try:
        stored_id, blob = value[len(MFA_PREFIX):].split(':', 1)
        raw = base64.urlsafe_b64decode(blob.encode('ascii'))
    except (ValueError, TypeError) as exc:
        raise ValueError('TOTP-Geheimnis beschädigt.') from exc
    if stored_id != key_id:
        raise KeyMissing(f'TOTP-Geheimnis wurde mit einem anderen Schlüssel ({stored_id}) verschlüsselt als dem vorhandenen ({key_id}).')
    if len(raw) < 49:
        raise ValueError('TOTP-Geheimnis beschädigt.')
    nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
    enc_key, mac_key = _subkeys(master)
    if not hmac.compare_digest(tag, _tag(mac_key, key_id, account_id, nonce, ct)):
        raise ValueError('TOTP-Geheimnis beschädigt oder gehört zu einem anderen Konto.')
    return bytes(a ^ b for a, b in zip(ct, _stream(enc_key, nonce, len(ct)))).decode('ascii')


# ---------------------------------------------------------------- Signatur der Sicherungssätze

def signing_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
    except ImportError:
        return False
    return True


def _pub_id(pub: bytes) -> str:
    return hashlib.sha256(pub).hexdigest()[:16]


def public_key(root=None, path=None):
    """(ID, 32 Bytes) des öffentlichen Signaturschlüssels – aus ``path`` oder dem Schlüsselordner. None, wenn keiner da ist."""
    p = Path(path).expanduser() if path else key_dir(root) / SIGN_PUB_FILE
    if not p.exists():
        if path:
            raise SignatureError(f'Öffentlicher Schlüssel nicht gefunden: {p}')
        return None
    raw = bytes.fromhex(p.read_text(encoding='ascii').split()[-1])
    if len(raw) != 32:
        raise SignatureError(f'Öffentlicher Schlüssel {p} hat ein unbekanntes Format.')
    return _pub_id(raw), raw


def _signing_key(root):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    folder = key_dir(root)
    priv_path, pub_path = folder / SIGN_KEY_FILE, folder / SIGN_PUB_FILE
    with _LOCK:
        if not priv_path.exists():
            if pub_path.exists():
                raise KeyMissing(f'Privater Signaturschlüssel fehlt ({priv_path}), der öffentliche ist da – nicht stillschweigend neu anlegen.')
            key = ed25519.Ed25519PrivateKey.generate()
            raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
            pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            _private_write(priv_path, f'sdq-ed25519-privat-v1 {raw.hex()}\n')
            pub_path.write_text(f'sdq-ed25519-oeffentlich-v1 {pub.hex()}\n', encoding='ascii')
        raw = bytes.fromhex(priv_path.read_text(encoding='ascii').split()[-1])
        return ed25519.Ed25519PrivateKey.from_private_bytes(raw)


def sign_manifest(root, folder: Path):
    """``manifest.sig`` neben ``manifest.json`` schreiben. Gibt die Schlüssel-ID zurück."""
    from cryptography.hazmat.primitives import serialization
    key = _signing_key(root)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    data = (folder / 'manifest.json').read_bytes()
    sig = {'alg': 'ed25519', 'key_id': _pub_id(pub), 'signature': base64.b64encode(key.sign(data)).decode('ascii')}
    (folder / SIGNATURE_FILE).write_text(json.dumps(sig, indent=1), encoding='utf-8')
    return sig['key_id']


def check_signature(folder: Path, root=None, public_key_path=None, allow_unsigned=False):
    """Signatur eines Satzes prüfen. Gibt ``{'status': 'gueltig'|'unsigniert'|'unsigniert_zugelassen', 'key_id': …}``.

    Regeln: Gibt es einen vertrauenswürdigen öffentlichen Schlüssel (``public_key_path`` oder im Schlüsselordner), muss die
    Signatur stimmen; ein unsignierter Satz wird dann nur mit ``allow_unsigned`` angenommen. Ohne jeden Schlüssel (Installation,
    die nie signiert hat) wird ein unsignierter Satz wie bisher angenommen. Eine vorhandene, aber falsche Signatur wird nie
    angenommen – auch nicht mit ``allow_unsigned``."""
    folder = Path(folder)
    trusted = public_key(root, public_key_path)
    sig_path = folder / SIGNATURE_FILE
    if not sig_path.exists():
        if trusted is None:
            return {'status': 'unsigniert', 'key_id': ''}
        if allow_unsigned:
            return {'status': 'unsigniert_zugelassen', 'key_id': ''}
        raise SignatureError('Satz ist nicht signiert, diese Installation signiert aber ihre Sicherungen. Nur nach Prüfung der Herkunft '
                             'mit --unsigniert-zulassen verwenden.')
    try:
        sig = json.loads(sig_path.read_text(encoding='utf-8'))
        signature = base64.b64decode(sig['signature'])
    except (ValueError, KeyError, TypeError) as exc:
        raise SignatureError('Signaturdatei beschädigt – Satz nicht verwenden.') from exc
    if trusted is None:
        raise SignatureError('Satz ist signiert, aber kein öffentlicher Schlüssel ist bekannt: --oeffentlicher-schluessel DATEI angeben.')
    if not signing_available():
        raise SignatureError('Signatur kann ohne das Paket „cryptography“ nicht geprüft werden (Variante „team“).')
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519
    key_id, raw = trusted
    if sig.get('alg') != 'ed25519' or sig.get('key_id') != key_id:
        raise SignatureError(f"Satz wurde mit einem anderen Schlüssel signiert ({sig.get('key_id')}) als dem vertrauenswürdigen ({key_id}).")
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(raw).verify(signature, (folder / 'manifest.json').read_bytes())
    except InvalidSignature as exc:
        raise SignatureError('Signatur ungültig – Manifest verändert oder nicht von dieser Installation. Satz nicht verwenden.') from exc
    return {'status': 'gueltig', 'key_id': key_id}
