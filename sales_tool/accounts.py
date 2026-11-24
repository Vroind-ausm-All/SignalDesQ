"""Zentrale Anmeldung einer Mehrmandanten-Installation (SDQ-014).

Konten und Mitgliedschaften liegen im Verzeichnis (``organisationen.sqlite3``), nicht in den Datenbanken der Organisationen:

- ``accounts``: eine Person = ein Konto (Benutzername, Passwort-Hash, aktiv).
- ``memberships``: Konto ↔ Organisation mit Rolle (admin, vertrieb, buchhaltung, lesen – dieselben Rollen wie ``auth.ROLES``).
- ``account_sessions``: zentrale Sitzung nach der Anmeldung (nur für Auswahl und Wechsel der Organisation).

Betritt eine Person eine Organisation, legt ``enter`` dort einen Benutzer ohne eigenes Passwort an (oder aktualisiert dessen Rolle)
und öffnet eine Sitzung in der Datenbank dieser Organisation. Danach gelten deren Rollenrechte wie im Einzelplatz-Team-Betrieb.
Wird eine Mitgliedschaft entfernt oder ein Konto gesperrt, endet der Zugang sofort: Der Benutzer in der Organisation wird
gesperrt, seine Sitzungen gelöscht, und der Server prüft die Mitgliedschaft zusätzlich bei jeder Anfrage.
"""
from __future__ import annotations

import datetime as dt
import secrets

from . import auth, tenancy
from .model import connect

CENTRAL_COOKIE = 'sd_konto'
ORG_COOKIE = 'sd_org'
CENTRAL_HOURS = 12


def init(directory: tenancy.Directory):
    with directory._connect() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL DEFAULT '', pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), last_login_at TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS memberships (
            account_id INTEGER NOT NULL REFERENCES accounts(id), slug TEXT NOT NULL REFERENCES organizations(slug),
            role TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (account_id, slug));
          CREATE TABLE IF NOT EXISTS account_sessions (
            token_hash TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT NOT NULL);
        ''')


def _account(conn, username):
    row = conn.execute('SELECT * FROM accounts WHERE username=?', (username,)).fetchone()
    if not row:
        raise LookupError(f'Konto „{username}“ unbekannt.')
    return row


# ---------------------------------------------------------------- Verwaltung (Kommandozeile, Betreiber)

def create_account(directory, username, password, display_name=''):
    init(directory)
    auth._check_username(username)
    auth._check_password_policy(password, username)
    with directory._connect() as conn:
        if conn.execute('SELECT 1 FROM accounts WHERE username=?', (username,)).fetchone():
            raise ValueError(f'Konto „{username}“ gibt es schon.')
        conn.execute('INSERT INTO accounts(username, display_name, pw_hash) VALUES (?,?,?)',
                     (username, (display_name or username).strip()[:80], auth.hash_password(password)))
    return account_view(directory, username)


def account_view(directory, username):
    with directory._connect() as conn:
        acc = _account(conn, username)
        orgs = conn.execute('''SELECT m.slug, m.role, o.name, o.status FROM memberships m JOIN organizations o ON o.slug=m.slug
                               WHERE m.account_id=? ORDER BY m.slug''', (acc['id'],)).fetchall()
    return {'username': acc['username'], 'display_name': acc['display_name'], 'active': bool(acc['active']),
            'organizations': [dict(r) for r in orgs]}


def set_membership(directory, username, slug, role):
    """Konto einer Organisation zuordnen oder seine Rolle ändern. Eine Rollenänderung wirkt mit der nächsten Anfrage."""
    if role not in auth.ROLES:
        raise ValueError('Rolle: ' + ', '.join(auth.ROLES))
    org = directory.get(slug)
    init(directory)
    with directory._connect() as conn:
        acc = _account(conn, username)
        conn.execute('''INSERT INTO memberships(account_id, slug, role) VALUES (?,?,?)
                        ON CONFLICT(account_id, slug) DO UPDATE SET role=excluded.role''', (acc['id'], slug, role))
    with connect(org['db_path']) as oc:  # Rolle in der Organisation sofort angleichen, falls die Person dort schon war
        oc.execute('UPDATE users SET role=? WHERE username=?', (role, username))
        oc.commit()
    return account_view(directory, username)


def _revoke_in_org(db_path, username):
    with connect(db_path) as oc:
        row = oc.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if row:
            oc.execute('UPDATE users SET active=0 WHERE id=?', (row['id'],))
            oc.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            oc.commit()


def remove_membership(directory, username, slug):
    """Zugang zu einer Organisation entziehen: Mitgliedschaft löschen, Benutzer dort sperren, Sitzungen beenden.
    Was die Person dort angelegt hat, bleibt erhalten."""
    org = directory.get(slug)
    with directory._connect() as conn:
        acc = _account(conn, username)
        conn.execute('DELETE FROM memberships WHERE account_id=? AND slug=?', (acc['id'], slug))
    _revoke_in_org(org['db_path'], username)
    return account_view(directory, username)


def set_active(directory, username, active):
    """Konto sperren (überall abgemeldet) oder wieder freigeben."""
    with directory._connect() as conn:
        acc = _account(conn, username)
        conn.execute('UPDATE accounts SET active=? WHERE id=?', (int(bool(active)), acc['id']))
        if not active:
            conn.execute('DELETE FROM account_sessions WHERE account_id=?', (acc['id'],))
        slugs = [r['slug'] for r in conn.execute('SELECT slug FROM memberships WHERE account_id=?', (acc['id'],))]
    if not active:
        for slug in slugs:
            _revoke_in_org(directory.get(slug)['db_path'], username)
    return account_view(directory, username)


def change_password(directory, username, old, new):
    with directory._connect() as conn:
        acc = _account(conn, username)
        if not auth.verify_password(old or '', acc['pw_hash']):
            raise PermissionError('Bisheriges Passwort stimmt nicht.')
        auth._check_password_policy(new, username)
        conn.execute('UPDATE accounts SET pw_hash=? WHERE id=?', (auth.hash_password(new), acc['id']))
        conn.execute('DELETE FROM account_sessions WHERE account_id=?', (acc['id'],))
    return {'changed': True}


# ---------------------------------------------------------------- Anmeldung

def login(directory, username, password, client=''):
    """Zentrale Anmeldung. Gibt (Konto-Ansicht, Token der zentralen Sitzung) zurück."""
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('Erwartet: {username, password}.')
    name = username.casefold()[:40]
    key = f'zentral|{name}'
    if auth._throttled(key) or auth._throttled('ip:' + client):
        raise auth.Throttled('Zu viele Fehlversuche – bitte 15 Minuten warten.')
    init(directory)
    with directory._connect() as conn:
        acc = conn.execute('SELECT * FROM accounts WHERE username=? AND active=1', (username,)).fetchone()
        ok = auth.verify_password(password, acc['pw_hash'] if acc else auth._DUMMY_HASH)
        if not acc or not ok:
            auth._fail(key)
            auth._fail('ip:' + client)
            raise auth.NotLoggedIn('Benutzername oder Passwort falsch.')
        token = secrets.token_urlsafe(32)
        expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=CENTRAL_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("DELETE FROM account_sessions WHERE expires_at < datetime('now')")
        conn.execute('INSERT INTO account_sessions(token_hash, account_id, expires_at) VALUES (?,?,?)',
                     (auth._token_hash(token), acc['id'], expires))
        conn.execute("UPDATE accounts SET last_login_at=datetime('now') WHERE id=?", (acc['id'],))
    with auth._FAIL_LOCK:
        auth._FAILS.pop(key, None)
    return account_view(directory, acc['username']), token


def central_account(directory, token):
    """Konto zur zentralen Sitzung (oder None)."""
    if not token:
        return None
    init(directory)
    with directory._connect() as conn:
        return conn.execute('''SELECT a.* FROM account_sessions s JOIN accounts a ON a.id=s.account_id
                               WHERE s.token_hash=? AND s.expires_at > datetime('now') AND a.active=1''',
                            (auth._token_hash(token),)).fetchone()


def membership(directory, username, slug):
    """Rolle eines aktiven Kontos in einer aktiven Organisation – oder None."""
    init(directory)
    with directory._connect() as conn:
        row = conn.execute('''SELECT m.role FROM memberships m JOIN accounts a ON a.id=m.account_id
                              JOIN organizations o ON o.slug=m.slug
                              WHERE a.username=? AND a.active=1 AND m.slug=? AND o.status='aktiv' ''', (username, slug)).fetchone()
    return row['role'] if row else None


def enter(directory, account, slug):
    """Organisation betreten: Mitgliedschaft prüfen, Benutzer dort anlegen/angleichen, Sitzung öffnen. Gibt das Token zurück."""
    role = membership(directory, account['username'], slug)
    if not role:
        raise PermissionError('Kein Zugang zu dieser Organisation.')
    db_path = directory.open(slug)
    with connect(db_path) as oc:
        row = oc.execute('SELECT id FROM users WHERE username=?', (account['username'],)).fetchone()
        if row:
            oc.execute("UPDATE users SET role=?, display_name=?, active=1, pw_hash='' WHERE id=?",
                       (role, account['display_name'], row['id']))
            uid = row['id']
        else:  # kein eigenes Passwort in der Organisation: Anmeldung nur zentral
            uid = oc.execute("INSERT INTO users(username, display_name, role, pw_hash) VALUES (?,?,?,'')",
                             (account['username'], account['display_name'], role)).lastrowid
        from .quality import put_setting
        put_setting(oc, 'auth_required', True)  # Rollenrechte gelten immer – auch ohne Zutun der Organisation
        token = auth.create_session(oc, uid)
        oc.commit()
    return token


def logout(directory, central_token):
    if central_token:
        with directory._connect() as conn:
            conn.execute('DELETE FROM account_sessions WHERE token_hash=?', (auth._token_hash(central_token),))
