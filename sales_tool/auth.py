"""Vorbereitung Team-Betrieb (Phase 6): optionaler Login mit Rollen und Sitzungen.

Standard bleibt der lokale Einzelplatz ohne Login. Wird der Login eingeschaltet, braucht jede API-Anfrage
eine gültige Sitzung (HttpOnly-Cookie, SameSite=Strict). Passwörter werden mit scrypt gehasht (Standardbibliothek),
Sitzungs-Tokens nur als SHA-256-Hash gespeichert. Fehlversuche werden gebremst und protokolliert.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
import threading
import time

from .company_data import _audit

ROLES = {
    'admin': 'Administration – alles inkl. Benutzer, Einstellungen, Backups',
    'vertrieb': 'Vertrieb & Recherche – Leads, Recherche, Angebote; Buchhaltung nur lesen',
    'buchhaltung': 'Buchhaltung – Rechnungen und Ausgaben; Vertrieb nur lesen',
    'lesen': 'Nur lesen',
}
SESSION_HOURS = 12
COOKIE = 'sd_session'
MIN_PASSWORD = 10
_FAILS = {}
_FAIL_LOCK = threading.Lock()
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60
PUBLIC_API = {('GET', '/api/auth/status'), ('POST', '/api/auth/login'), ('POST', '/api/auth/setup')}
ADMIN_ONLY = (r'/api/auth/users.*', r'/api/auth/settings', r'/api/quality/settings', r'/api/backup.*', r'/api/accounting/settings')
ACCOUNTING = r'/api/accounting/.*|/rechnung/.*'
SELF_SERVICE = {('POST', '/api/auth/logout'), ('POST', '/api/auth/password')}


def init_auth(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL, pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), last_login_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT NOT NULL
      );
    ''')


# ---------------------------------------------------------------- Passwörter

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f'scrypt$16384$8$1${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    try:
        _, n, r, p, salt, digest = stored.split('$')
        calc = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc.hex(), digest)


_DUMMY_HASH = hash_password(secrets.token_hex(8))


def _check_password_policy(password, username=''):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD or len(password) > 200:
        raise ValueError(f'Passwort: mindestens {MIN_PASSWORD} Zeichen.')
    if username and username.casefold() in password.casefold():
        raise ValueError('Das Passwort darf den Benutzernamen nicht enthalten.')
    if len(set(password)) < 5:
        raise ValueError('Das Passwort ist zu einfach.')


def _check_username(username):
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9._-]{3,40}', username):
        raise ValueError('Benutzername: 3–40 Zeichen (Buchstaben, Ziffern, . _ -).')


# ---------------------------------------------------------------- Einstellungen

def auth_required(conn):
    from .quality import get_setting
    return bool(get_setting(conn, 'auth_required', False))


def has_users(conn):
    return conn.execute('SELECT 1 FROM users WHERE active=1 LIMIT 1').fetchone() is not None


def user_view(row):
    return {k: row[k] for k in ('id', 'username', 'display_name', 'role', 'active', 'created_at', 'last_login_at')} | {'active': bool(row['active'])}


def status(conn, user):
    return {'auth_required': auth_required(conn), 'has_users': has_users(conn), 'user': user_view(user) if user else None, 'roles': ROLES,
            'notice': 'Ohne Login ist SignalDesk ein lokaler Einzelplatz (nur 127.0.0.1). Für Team-Betrieb Login einschalten und hinter einem TLS-Proxy betreiben.'}


# ---------------------------------------------------------------- Sitzungen

def _token_hash(token):
    return hashlib.sha256(token.encode('ascii', 'ignore')).hexdigest()


def create_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=SESSION_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
    conn.execute('INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)', (_token_hash(token), user_id, expires))
    conn.execute("UPDATE users SET last_login_at=datetime('now') WHERE id=?", (user_id,))
    conn.commit()
    return token


def session_user(conn, cookie_header):
    token = _cookie(cookie_header)
    if not token:
        return None
    return conn.execute('''SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                           WHERE s.token_hash=? AND s.expires_at > datetime('now') AND u.active=1''', (_token_hash(token),)).fetchone()


def _cookie(header):
    for part in (header or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == COOKIE and re.fullmatch(r'[A-Za-z0-9_-]{20,100}', v):
            return v
    return ''


def cookie_header(token, secure=False, clear=False):
    attrs = f"{COOKIE}={'' if clear else token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else SESSION_HOURS * 3600}"
    return attrs + ('; Secure' if secure else '')


def logout(conn, cookie_header_value):
    token = _cookie(cookie_header_value)
    if token:
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (_token_hash(token),))
        conn.commit()


# ---------------------------------------------------------------- Login & Benutzer

class Throttled(PermissionError):
    """Zu viele Fehlversuche (HTTP 429)."""


class NotLoggedIn(PermissionError):
    """Anmeldung erforderlich (HTTP 401)."""


def _throttled(key):
    now = time.monotonic()
    with _FAIL_LOCK:
        fails = [t for t in _FAILS.get(key, []) if now - t < FAIL_WINDOW]
        _FAILS[key] = fails
        return len(fails) >= MAX_FAILS


def _fail(key):
    with _FAIL_LOCK:
        _FAILS.setdefault(key, []).append(time.monotonic())


def login(conn, data, client=''):
    if not isinstance(data, dict) or set(data) != {'username', 'password'} or not all(isinstance(v, str) for v in data.values()):
        raise ValueError('Erwartet: {username, password}.')
    key = data['username'].casefold()[:40]
    if _throttled(key) or _throttled('ip:' + client):
        raise Throttled('Zu viele Fehlversuche – bitte 15 Minuten warten.')
    user = conn.execute('SELECT * FROM users WHERE username=? AND active=1', (data['username'],)).fetchone()
    ok = verify_password(data['password'], user['pw_hash'] if user else _DUMMY_HASH)  # gleiche Laufzeit ohne Benutzer
    if not user or not ok:
        _fail(key)
        _fail('ip:' + client)
        _audit(conn, 'auth', 0, 'login_fehlgeschlagen', key)
        conn.commit()
        raise NotLoggedIn('Benutzername oder Passwort falsch.')
    with _FAIL_LOCK:
        _FAILS.pop(key, None)
    _audit(conn, 'auth', user['id'], 'login', user['username'])
    return user, create_session(conn, user['id'])


def setup_admin(conn, data):
    if has_users(conn):
        raise PermissionError('Es gibt bereits Benutzer – neue Benutzer legt die Administration an.')
    return create_user(conn, {**data, 'role': 'admin'}, actor=None)


def create_user(conn, data, actor):
    if not isinstance(data, dict) or set(data) - {'username', 'password', 'display_name', 'role'}:
        raise ValueError('Erwartet: {username, password, display_name, role}.')
    _check_username(data.get('username'))
    _check_password_policy(data.get('password'), data['username'])
    if data.get('role') not in ROLES:
        raise ValueError('Rolle: ' + ', '.join(ROLES))
    name = str(data.get('display_name') or data['username']).strip()[:80]
    if conn.execute('SELECT 1 FROM users WHERE username=?', (data['username'],)).fetchone():
        raise ValueError('Benutzername ist vergeben.')
    cur = conn.execute('INSERT INTO users(username, display_name, role, pw_hash) VALUES (?,?,?,?)',
                       (data['username'], name, data['role'], hash_password(data['password'])))
    _audit(conn, 'user', cur.lastrowid, 'angelegt', f"{data['username']} ({data['role']}) durch {actor['username'] if actor else 'Ersteinrichtung'}")
    conn.commit()
    return user_view(conn.execute('SELECT * FROM users WHERE id=?', (cur.lastrowid,)).fetchone())


def _active_admins(conn, exclude=None):
    return conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id<>?", (exclude or 0,)).fetchone()[0]


def update_user(conn, user_id, data, actor):
    if not isinstance(data, dict) or not data or set(data) - {'role', 'active', 'password', 'display_name'}:
        raise ValueError('Erwartet: {role?, active?, password?, display_name?}.')
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        raise LookupError('Benutzer nicht gefunden.')
    out = {}
    if 'role' in data:
        if data['role'] not in ROLES:
            raise ValueError('Rolle: ' + ', '.join(ROLES))
        out['role'] = data['role']
    if 'active' in data:
        if not isinstance(data['active'], bool):
            raise ValueError('active: true/false.')
        out['active'] = int(data['active'])
    if 'display_name' in data:
        out['display_name'] = str(data['display_name']).strip()[:80]
    if 'password' in data:
        _check_password_policy(data['password'], user['username'])
        out['pw_hash'] = hash_password(data['password'])
    demoted = user['role'] == 'admin' and (out.get('role', 'admin') != 'admin' or out.get('active', 1) == 0)
    if demoted and _active_admins(conn, exclude=user_id) == 0:
        raise ValueError('Mindestens eine aktive Administration muss bleiben.')
    conn.execute(f"UPDATE users SET {', '.join(k + '=?' for k in out)} WHERE id=?", (*out.values(), user_id))
    if 'pw_hash' in out or out.get('active') == 0:
        conn.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    _audit(conn, 'user', user_id, 'geaendert', f"{user['username']}: {', '.join(k for k in out if k != 'pw_hash') or ''}{' Passwort' if 'pw_hash' in out else ''} durch {actor['username']}")
    conn.commit()
    return user_view(conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())


def change_password(conn, user, data):
    if not isinstance(data, dict) or set(data) != {'old_password', 'new_password'}:
        raise ValueError('Erwartet: {old_password, new_password}.')
    if not verify_password(str(data['old_password']), user['pw_hash']):
        raise PermissionError('Bisheriges Passwort falsch.')
    _check_password_policy(data['new_password'], user['username'])
    conn.execute('UPDATE users SET pw_hash=? WHERE id=?', (hash_password(data['new_password']), user['id']))
    conn.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
    _audit(conn, 'user', user['id'], 'passwort_geaendert', user['username'])
    conn.commit()


def set_auth_required(conn, data, actor):
    from .quality import put_setting
    if not isinstance(data, dict) or set(data) != {'auth_required'} or not isinstance(data['auth_required'], bool):
        raise ValueError('Erwartet: {auth_required: true/false}.')
    if data['auth_required']:
        if not actor or actor['role'] != 'admin':
            raise PermissionError('Login einschalten: bitte zuerst als Administration anmelden.')
        if _active_admins(conn) == 0:
            raise ValueError('Zuerst eine Administration anlegen.')
    put_setting(conn, 'auth_required', data['auth_required'])
    _audit(conn, 'auth', 0, 'login_pflicht_' + ('an' if data['auth_required'] else 'aus'), actor['username'] if actor else 'lokal')
    conn.commit()
    return {'auth_required': data['auth_required']}


# ---------------------------------------------------------------- Rechte

def allowed(role, method, route):
    """Rollenrechte je Route. Lesen ist für alle angemeldeten Rollen erlaubt."""
    if (method, route) in SELF_SERVICE:
        return True
    if role == 'admin':
        return True
    if any(re.fullmatch(p, route) for p in ADMIN_ONLY):
        return False
    if method in ('GET', 'HEAD'):
        return True
    if role == 'lesen':
        return False
    is_accounting = bool(re.fullmatch(ACCOUNTING, route))
    if role == 'buchhaltung':
        return is_accounting
    if role == 'vertrieb':
        return not is_accounting
    return False


def route_auth(h, conn, method, route, user):
    if not route.startswith('/api/auth/'):
        return False
    secure = h.headers.get('X-Forwarded-Proto', '') == 'https'
    if route == '/api/auth/status' and method == 'GET':
        h._send(200, status(conn, user))
        return True
    if route == '/api/auth/setup' and method == 'POST':
        u = setup_admin(conn, h._body())
        token = create_session(conn, u['id'])
        h._send(201, {'user': u}, {'Set-Cookie': cookie_header(token, secure)})
        return True
    if route == '/api/auth/login' and method == 'POST':
        u, token = login(conn, h._body(), h.client_address[0] if h.client_address else '')
        h._send(200, {'user': user_view(u)}, {'Set-Cookie': cookie_header(token, secure)})
        return True
    if route == '/api/auth/logout' and method == 'POST':
        logout(conn, h.headers.get('Cookie', ''))
        h._send(200, {'logged_out': True}, {'Set-Cookie': cookie_header('', secure, clear=True)})
        return True
    if route == '/api/auth/password' and method == 'POST':
        if not user:
            raise NotLoggedIn('Nicht angemeldet.')
        change_password(conn, user, h._body())
        h._send(200, {'changed': True, 'notice': 'Passwort geändert – bitte neu anmelden.'}, {'Set-Cookie': cookie_header('', secure, clear=True)})
        return True
    if route == '/api/auth/settings' and method == 'PUT':
        if has_users(conn) and auth_required(conn) and (not user or user['role'] != 'admin'):
            raise PermissionError('Nur die Administration kann den Login ein- oder ausschalten.')
        h._send(200, set_auth_required(conn, h._body(), user))
        return True
    if route == '/api/auth/users':
        if method == 'GET':
            h._send(200, [user_view(r) for r in conn.execute('SELECT * FROM users ORDER BY username')])
            return True
        if method == 'POST':
            if has_users(conn) and (not user or user['role'] != 'admin'):
                raise PermissionError('Benutzer anlegen: bitte als Administration anmelden.')
            h._send(201, create_user(conn, h._body(), user))
            return True
    m = re.fullmatch(r'/api/auth/users/(\d+)', route)
    if m and method == 'PATCH':
        if not user or user['role'] != 'admin':
            raise PermissionError('Benutzer ändern: bitte als Administration anmelden.')
        h._send(200, update_user(conn, int(m.group(1)), h._body(), user))
        return True
    return False
