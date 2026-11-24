"""Einmalcodes nach RFC 6238 (TOTP, HMAC-SHA1, 30 Sekunden, 6 Stellen) – nur Standardbibliothek (SDQ-021).

Passt zu den üblichen Authenticator-Apps (z. B. Aegis, FreeOTP, Google/Microsoft Authenticator, 1Password).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6
WINDOW = 1  # ±1 Zeitschritt: Uhren von Telefon und Server dürfen 30 Sekunden auseinanderliegen


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _key(secret):
    s = secret.strip().replace(' ', '').upper()
    return base64.b32decode(s + '=' * (-len(s) % 8))


def hotp(key: bytes, counter: int, digits=DIGITS, digest=hashlib.sha1):
    mac = hmac.new(key, struct.pack('>Q', counter), digest).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)


def step(now=None):
    return int((time.time() if now is None else now) // STEP)


def code(secret, now=None):
    return hotp(_key(secret), step(now))


def match(secret, candidate, now=None, last_step=-1):
    """Zeitschritt des passenden Codes – oder None. Ein Schritt ≤ ``last_step`` gilt nicht (kein zweites Mal derselbe Code)."""
    candidate = (candidate or '').replace(' ', '')
    if not (candidate.isdigit() and len(candidate) == DIGITS):
        return None
    key, current = _key(secret), step(now)
    for s in range(current - WINDOW, current + WINDOW + 1):
        if s > last_step and hmac.compare_digest(hotp(key, s), candidate):
            return s
    return None


def uri(secret, account, issuer='SignalDesk'):
    label = quote(f'{issuer}:{account}')
    return f'otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}'
