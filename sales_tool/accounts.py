"""Zentrale Anmeldung einer Mehrmandanten-Installation (SDQ-014, zweiter Faktor SDQ-021, Protokoll SDQ-022).

Konten und Mitgliedschaften liegen im Verzeichnis (``organisationen.sqlite3``), nicht in den Datenbanken der Organisationen:

- ``accounts``: eine Person = ein Konto (Benutzername, Passwort-Hash, aktiv).
- ``memberships``: Konto ↔ Organisation mit Rolle (admin, vertrieb, buchhaltung, lesen – dieselben Rollen wie ``auth.ROLES``).
- ``account_sessions``: zentrale Sitzung nach der Anmeldung (nur für Auswahl und Wechsel der Organisation). ``stage`` sagt,
  wie weit die Anmeldung ist: ``zweitfaktor`` (Passwort stimmt, Code fehlt), ``einrichtung`` (zweiter Faktor ist Pflicht,
  aber noch nicht eingerichtet) oder ``voll``. Nur ``voll`` darf eine Organisation betreten.
- ``account_mfa`` / ``account_recovery_codes``: zweiter Faktor (TOTP nach RFC 6238) und Wiederherstellungscodes (nur Hash).
- ``login_failures``: Fehlversuche der letzten Minuten – die Sperre gilt auch nach einem Neustart des Servers.
- ``directory_settings``: Einstellungen der Installation (``require_2fa``).

Betritt eine Person eine Organisation, legt ``enter`` dort einen Benutzer ohne eigenes Passwort an (oder aktualisiert dessen Rolle)
und öffnet eine Sitzung in der Datenbank dieser Organisation. Danach gelten deren Rollenrechte wie im Einzelplatz-Team-Betrieb.
Wird eine Mitgliedschaft entfernt oder ein Konto gesperrt, endet der Zugang sofort: Der Benutzer in der Organisation wird
gesperrt, seine Sitzungen gelöscht, und der Server prüft die Mitgliedschaft zusätzlich bei jeder Anfrage.

Jede Änderung und jede Anmeldung landet im Protokoll (``audit_trail``). ``actor`` nennt, wer gehandelt hat: ``konto:<name>``
im Browser, ``betreiber:<Betriebssystem-Benutzer>`` über die Kommandozeile.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets

from . import audit_trail, auth, tenancy, totp
from .model import connect

CENTRAL_COOKIE = 'sd_konto'
ORG_COOKIE = 'sd_org'
CENTRAL_HOURS = 12
PENDING_MINUTES = 5          # Zeit für die Eingabe des Codes nach dem Passwort
RECOVERY_CODES = 10
FAIL_LIMIT, FAIL_MINUTES = 5, 15
STAGES = ('zweitfaktor', 'einrichtung', 'voll')


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
          CREATE TABLE IF NOT EXISTS account_mfa (
            account_id INTEGER PRIMARY KEY REFERENCES accounts(id), secret TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
            last_step INTEGER NOT NULL DEFAULT -1, created_at TEXT NOT NULL DEFAULT (datetime('now')),
            confirmed_at TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS account_recovery_codes (
            account_id INTEGER NOT NULL REFERENCES accounts(id), code_hash TEXT NOT NULL, used_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (account_id, code_hash));
          CREATE TABLE IF NOT EXISTS login_failures (key TEXT NOT NULL, at TEXT NOT NULL DEFAULT (datetime('now')));
          CREATE INDEX IF NOT EXISTS login_failures_key ON login_failures(key, at);
          CREATE TABLE IF NOT EXISTS directory_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(account_sessions)')}
        if 'stage' not in cols:  # dev62 → dev63: bestehende Sitzungen sind vollständige Anmeldungen
            conn.execute("ALTER TABLE account_sessions ADD COLUMN stage TEXT NOT NULL DEFAULT 'voll'")
        if 'last_seen' not in cols:  # dev65: Abmelden nach Leerlauf
            conn.execute("ALTER TABLE account_sessions ADD COLUMN last_seen TEXT NOT NULL DEFAULT ''")
        if 'email' not in {r['name'] for r in conn.execute('PRAGMA table_info(accounts)')}:  # dev64: Einladung, Registrierung
            conn.execute("ALTER TABLE accounts ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        audit_trail.init(conn)


def _account(conn, username):
    row = conn.execute('SELECT * FROM accounts WHERE username=?', (username,)).fetchone()
    if not row:
        raise LookupError(f'Konto „{username}“ unbekannt.')
    return row


def _log(directory, actor, action, target='', detail='', ip=''):
    audit_trail.record(directory, actor or audit_trail.operator(), action, target, detail, ip)


# ---------------------------------------------------------------- Einstellungen der Installation

def setting(directory, key, default=None):
    init(directory)
    with directory._connect() as conn:
        row = conn.execute('SELECT value FROM directory_settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


# Einstellungen, die der Betreiber setzen darf (SDQ-027). Werte sind Text; die Prüfung steht hier, nicht beim Aufrufer.
SETTINGS = {
    'registrierung': ('aus', 'offen'),   # Selbstregistrierung neuer Organisationen
    'public_url': None,                  # öffentliche Adresse für Links in E-Mails, z. B. https://app.example.org
    'testphase_tage': None,              # Länge der Testphase einer selbst registrierten Organisation
    'leerlauf_minuten': None,            # Abmelden nach so vielen Minuten ohne Anfrage (Standard 60, 0 = aus)
}
IDLE_DEFAULT = 60


def idle_minutes(directory):
    """Leerlauf-Grenze in Minuten (None = aus)."""
    value = setting(directory, 'leerlauf_minuten', '')
    minutes = int(value) if str(value).isdigit() else IDLE_DEFAULT
    return minutes or None


def set_setting(directory, key, value, actor=None):
    if key not in SETTINGS:
        raise ValueError('Einstellung: ' + ', '.join(SETTINGS))
    value = str(value or '').strip()
    allowed = SETTINGS[key]
    if allowed and value not in allowed:
        raise ValueError(f'{key}: ' + ' oder '.join(allowed))
    if key == 'public_url' and not re.fullmatch(r'https://[A-Za-z0-9.-]+(:\d{2,5})?', value) and \
            not re.fullmatch(r'http://(127\.0\.0\.1|localhost)(:\d{2,5})?', value):
        raise ValueError('public_url: https://hostname (ohne Pfad); http nur für 127.0.0.1/localhost.')
    if key == 'testphase_tage' and not (value.isdigit() and 1 <= int(value) <= 365):
        raise ValueError('testphase_tage: 1 bis 365.')
    if key == 'leerlauf_minuten' and not (value.isdigit() and (int(value) == 0 or 5 <= int(value) <= 720)):
        raise ValueError('leerlauf_minuten: 5 bis 720, oder 0 für aus.')
    init(directory)
    with directory._connect() as conn:
        conn.execute('INSERT INTO directory_settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (key, value))
    _log(directory, actor, 'einstellung_gesetzt', key, value)
    return {key: value}


EMAIL_RE = re.compile(r'[^@\s<>"\',;]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}')


def check_email(email):
    email = (email or '').strip() if isinstance(email, str) else ''
    if len(email) > 200 or not EMAIL_RE.fullmatch(email):
        raise ValueError('E-Mail-Adresse ungültig.')
    return email


def account_by_email(directory, email):
    init(directory)
    with directory._connect() as conn:
        row = conn.execute('SELECT username FROM accounts WHERE email=? COLLATE NOCASE AND email<>\'\'', (email,)).fetchone()
    return row['username'] if row else None


def set_email(directory, username, email, actor=None):
    email = check_email(email) if email else ''
    init(directory)
    with directory._connect() as conn:
        acc = _account(conn, username)
        if email and conn.execute('SELECT 1 FROM accounts WHERE email=? COLLATE NOCASE AND id<>?', (email, acc['id'])).fetchone():
            raise ValueError('Diese E-Mail-Adresse gehört schon zu einem anderen Konto.')
        conn.execute('UPDATE accounts SET email=? WHERE id=?', (email, acc['id']))
    _log(directory, actor, 'email_gesetzt', username)
    return account_view(directory, username)


def require_2fa(directory):
    return setting(directory, 'require_2fa', '0') == '1'


def set_require_2fa(directory, on, actor=None):
    """Zwei-Faktor-Pflicht für alle Konten. Konten ohne zweiten Faktor müssen ihn bei der nächsten Anmeldung einrichten."""
    init(directory)
    with directory._connect() as conn:
        conn.execute('INSERT INTO directory_settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     ('require_2fa', '1' if on else '0'))
        if on:  # laufende zentrale Sitzungen ohne zweiten Faktor beenden – Pflicht gilt ab sofort
            conn.execute('''DELETE FROM account_sessions WHERE account_id NOT IN
                            (SELECT account_id FROM account_mfa WHERE active=1)''')
    _log(directory, actor, 'zwei_faktor_pflicht_' + ('an' if on else 'aus'))
    return {'require_2fa': bool(on)}


# ---------------------------------------------------------------- Verwaltung (Kommandozeile, Betreiber)

def create_account(directory, username, password, display_name='', actor=None, email='', pw_hash=None):
    """Konto anlegen. ``pw_hash`` statt ``password`` nur für eine bestätigte Registrierung (Passwort dort schon geprüft)."""
    init(directory)
    auth._check_username(username)
    if pw_hash is None:
        auth._check_password_policy(password, username)
        pw_hash = auth.hash_password(password)
    email = check_email(email) if email else ''
    with directory._connect() as conn:
        if conn.execute('SELECT 1 FROM accounts WHERE username=?', (username,)).fetchone():
            raise ValueError(f'Konto „{username}“ gibt es schon.')
        if email and conn.execute('SELECT 1 FROM accounts WHERE email=? COLLATE NOCASE', (email,)).fetchone():
            raise ValueError('Diese E-Mail-Adresse gehört schon zu einem Konto.')
        conn.execute('INSERT INTO accounts(username, display_name, pw_hash, email) VALUES (?,?,?,?)',
                     (username, (display_name or username).strip()[:80], pw_hash, email))
    _log(directory, actor, 'konto_angelegt', username)
    return account_view(directory, username)


def account_view(directory, username):
    init(directory)
    with directory._connect() as conn:
        acc = _account(conn, username)
        orgs = conn.execute('''SELECT m.slug, m.role, o.name, o.status FROM memberships m JOIN organizations o ON o.slug=m.slug
                               WHERE m.account_id=? ORDER BY m.slug''', (acc['id'],)).fetchall()
        mfa = conn.execute('SELECT active FROM account_mfa WHERE account_id=?', (acc['id'],)).fetchone()
        left = conn.execute("SELECT COUNT(*) FROM account_recovery_codes WHERE account_id=? AND used_at=''", (acc['id'],)).fetchone()[0]
    return {'username': acc['username'], 'display_name': acc['display_name'], 'email': acc['email'], 'active': bool(acc['active']),
            'two_factor': bool(mfa and mfa['active']), 'recovery_codes_left': left if mfa and mfa['active'] else 0,
            'organizations': [dict(r) for r in orgs]}


def set_membership(directory, username, slug, role, actor=None):
    """Konto einer Organisation zuordnen oder seine Rolle ändern. Eine Rollenänderung wirkt mit der nächsten Anfrage."""
    if role not in auth.ROLES:
        raise ValueError('Rolle: ' + ', '.join(auth.ROLES))
    org = directory.get(slug)
    init(directory)
    with directory._connect() as conn:
        acc = _account(conn, username)
        before = conn.execute('SELECT role FROM memberships WHERE account_id=? AND slug=?', (acc['id'], slug)).fetchone()
        conn.execute('''INSERT INTO memberships(account_id, slug, role) VALUES (?,?,?)
                        ON CONFLICT(account_id, slug) DO UPDATE SET role=excluded.role''', (acc['id'], slug, role))
    with connect(org['db_path']) as oc:  # Rolle in der Organisation sofort angleichen, falls die Person dort schon war
        oc.execute('UPDATE users SET role=? WHERE username=?', (role, username))
        oc.commit()
    _log(directory, actor, 'mitgliedschaft_gesetzt', username, f"{slug}: {before['role'] + ' → ' if before else ''}{role}")
    return account_view(directory, username)


def _revoke_in_org(db_path, username, deactivate=True):
    with connect(db_path) as oc:
        row = oc.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if row:
            if deactivate:
                oc.execute('UPDATE users SET active=0 WHERE id=?', (row['id'],))
            oc.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            oc.commit()


def _end_everywhere(directory, conn, acc):
    """Zentrale Sitzungen beenden; gibt die Organisationen zurück, in denen danach die Sitzungen enden müssen."""
    conn.execute('DELETE FROM account_sessions WHERE account_id=?', (acc['id'],))
    slugs = [r['slug'] for r in conn.execute('SELECT slug FROM memberships WHERE account_id=?', (acc['id'],))]
    return slugs


def remove_membership(directory, username, slug, actor=None):
    """Zugang zu einer Organisation entziehen: Mitgliedschaft löschen, Benutzer dort sperren, Sitzungen beenden.
    Was die Person dort angelegt hat, bleibt erhalten."""
    org = directory.get(slug)
    with directory._connect() as conn:
        acc = _account(conn, username)
        conn.execute('DELETE FROM memberships WHERE account_id=? AND slug=?', (acc['id'], slug))
    _revoke_in_org(org['db_path'], username)
    _log(directory, actor, 'mitgliedschaft_entzogen', username, slug)
    return account_view(directory, username)


def set_active(directory, username, active, actor=None):
    """Konto sperren (überall abgemeldet) oder wieder freigeben."""
    with directory._connect() as conn:
        acc = _account(conn, username)
        conn.execute('UPDATE accounts SET active=? WHERE id=?', (int(bool(active)), acc['id']))
        slugs = _end_everywhere(directory, conn, acc) if not active else []
    for slug in slugs:
        _revoke_in_org(directory.get(slug)['db_path'], username)
    _log(directory, actor, 'konto_' + ('freigegeben' if active else 'gesperrt'), username)
    return account_view(directory, username)


def reset_password(directory, username, password, actor=None):
    """Betreiber setzt ein neues Passwort (Passwort vergessen). Alle Sitzungen des Kontos enden."""
    with directory._connect() as conn:
        acc = _account(conn, username)
        auth._check_password_policy(password, username)
        conn.execute('UPDATE accounts SET pw_hash=? WHERE id=?', (auth.hash_password(password), acc['id']))
        slugs = _end_everywhere(directory, conn, acc)
    for slug in slugs:
        _revoke_in_org(directory.get(slug)['db_path'], username, deactivate=False)
    _log(directory, actor, 'passwort_zurueckgesetzt', username)
    return {'changed': True}


def change_password(directory, username, old, new, actor=None, ip=''):
    with directory._connect() as conn:
        acc = _account(conn, username)
        if not auth.verify_password(old or '', acc['pw_hash']):
            raise PermissionError('Bisheriges Passwort stimmt nicht.')
        auth._check_password_policy(new, username)
        conn.execute('UPDATE accounts SET pw_hash=? WHERE id=?', (auth.hash_password(new), acc['id']))
        conn.execute('DELETE FROM account_sessions WHERE account_id=?', (acc['id'],))
    _log(directory, actor or f'konto:{username}', 'passwort_geaendert', username, ip=ip)
    return {'changed': True}


# ---------------------------------------------------------------- Fehlversuche (überdauern einen Neustart)

def _throttled(conn, *keys):
    since = f'-{FAIL_MINUTES} minutes'
    return any(conn.execute("SELECT COUNT(*) FROM login_failures WHERE key=? AND at > datetime('now', ?)", (k, since)).fetchone()[0]
               >= FAIL_LIMIT for k in keys)


def _fail(directory, *keys):
    with directory._connect() as conn:
        conn.execute("DELETE FROM login_failures WHERE at < datetime('now', '-1 day')")
        conn.executemany('INSERT INTO login_failures(key) VALUES (?)', [(k,) for k in keys])


def _clear_fails(conn, key):
    conn.execute('DELETE FROM login_failures WHERE key=?', (key,))


# ---------------------------------------------------------------- Anmeldung

def _new_session(conn, account_id, stage):
    token = secrets.token_urlsafe(32)
    span = dt.timedelta(hours=CENTRAL_HOURS) if stage == 'voll' else dt.timedelta(minutes=PENDING_MINUTES)
    expires = (dt.datetime.now(dt.timezone.utc) + span).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("DELETE FROM account_sessions WHERE expires_at < datetime('now')")
    conn.execute("INSERT INTO account_sessions(token_hash, account_id, expires_at, stage, last_seen) VALUES (?,?,?,?,datetime('now'))",
                 (auth._token_hash(token), account_id, expires, stage))
    return token


def _mfa_active(conn, account_id):
    row = conn.execute('SELECT active FROM account_mfa WHERE account_id=?', (account_id,)).fetchone()
    return bool(row and row['active'])


def login(directory, username, password, client=''):
    """Erster Schritt der zentralen Anmeldung (Passwort). Gibt (Konto-Ansicht mit ``stage``, Token) zurück.

    ``stage`` ``voll``: angemeldet. ``zweitfaktor``: Code aus der App (oder Wiederherstellungscode) mit ``second_factor``
    nachreichen. ``einrichtung``: zweiter Faktor ist Pflicht und muss zuerst eingerichtet werden (``mfa_start``/``mfa_confirm``).
    """
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('Erwartet: {username, password}.')
    name = username.casefold()[:40]
    key, ipkey = f'zentral|{name}', 'ip:' + (client or '')
    init(directory)
    with directory._connect() as conn:
        if _throttled(conn, key, ipkey):
            raise auth.Throttled('Zu viele Fehlversuche – bitte 15 Minuten warten.')
        acc = conn.execute('SELECT * FROM accounts WHERE username=? AND active=1', (username,)).fetchone()
        ok = auth.verify_password(password, acc['pw_hash'] if acc else auth._DUMMY_HASH)
    if not acc or not ok:
        _fail(directory, key, ipkey)
        _log(directory, 'anonym', 'anmeldung_fehlgeschlagen', acc['username'] if acc else 'unbekannt', 'Passwort', client)
        raise auth.NotLoggedIn('Benutzername oder Passwort falsch.')
    required = require_2fa(directory)
    with directory._connect() as conn:
        if _mfa_active(conn, acc['id']):
            stage = 'zweitfaktor'
        elif required:
            stage = 'einrichtung'
        else:
            stage = 'voll'
        token = _new_session(conn, acc['id'], stage)
        _clear_fails(conn, key)
        if stage == 'voll':
            conn.execute("UPDATE accounts SET last_login_at=datetime('now') WHERE id=?", (acc['id'],))
    _log(directory, f"konto:{acc['username']}", 'anmeldung' if stage == 'voll' else 'anmeldung_passwort_ok',
         acc['username'], '' if stage == 'voll' else f'weiter: {stage}', client)
    return {**account_view(directory, acc['username']), 'stage': stage}, token


def _touch_idle(conn, token_hash, minutes):
    """Wie ``auth.touch_idle`` für die zentrale Sitzung: False (und gelöscht), wenn zu lange unbenutzt."""
    gone = conn.execute("DELETE FROM account_sessions WHERE token_hash=? AND last_seen<>'' AND last_seen < datetime('now', ?)",
                        (token_hash, f'-{int(minutes)} minutes')).rowcount
    if not gone:
        conn.execute("UPDATE account_sessions SET last_seen=datetime('now') WHERE token_hash=? AND "
                     "(last_seen='' OR last_seen < datetime('now', '-1 minutes'))", (token_hash,))
    return not gone


def session(directory, token):
    """(Konto, Stufe) zur zentralen Sitzung – oder (None, None)."""
    if not token:
        return None, None
    init(directory)
    limit = idle_minutes(directory)
    with directory._connect() as conn:
        row = conn.execute('''SELECT a.*, s.stage AS session_stage FROM account_sessions s JOIN accounts a ON a.id=s.account_id
                              WHERE s.token_hash=? AND s.expires_at > datetime('now') AND a.active=1''',
                           (auth._token_hash(token),)).fetchone()
        if row and row['session_stage'] == 'voll':
            if limit and not _touch_idle(conn, auth._token_hash(token), limit):
                return None, None
    return (row, row['session_stage']) if row else (None, None)


def central_account(directory, token):
    """Konto zur vollständig angemeldeten zentralen Sitzung (oder None)."""
    acc, stage = session(directory, token)
    return acc if stage == 'voll' else None


def _upgrade(conn, old_token, account_id):
    """Zwischenstufe → volle Sitzung. Neues Token (kein Weiterverwenden des Zwischen-Tokens)."""
    conn.execute('DELETE FROM account_sessions WHERE token_hash=?', (auth._token_hash(old_token),))
    conn.execute("UPDATE accounts SET last_login_at=datetime('now') WHERE id=?", (account_id,))
    return _new_session(conn, account_id, 'voll')


def _hash_recovery(code):
    return hashlib.sha256(code.replace('-', '').replace(' ', '').upper().encode('ascii', 'ignore')).hexdigest()


def second_factor(directory, token, code, client=''):
    """Zweiter Schritt: Code aus der App oder ein Wiederherstellungscode. Gibt (Konto-Ansicht, neues Token) zurück."""
    acc, stage = session(directory, token)
    if not acc or stage != 'zweitfaktor':
        raise auth.NotLoggedIn('Anmeldung abgelaufen – bitte erneut mit Passwort anmelden.')
    if not isinstance(code, str) or not 6 <= len(code.strip()) <= 20:
        raise ValueError('Code: 6 Ziffern aus der App oder ein Wiederherstellungscode.')
    key = f"zweitfaktor|{acc['username'].casefold()}"
    with directory._connect() as conn:
        if _throttled(conn, key):
            conn.execute('DELETE FROM account_sessions WHERE token_hash=?', (auth._token_hash(token),))
            raise auth.Throttled('Zu viele falsche Codes – bitte 15 Minuten warten und neu anmelden.')
        mfa = conn.execute('SELECT * FROM account_mfa WHERE account_id=? AND active=1', (acc['id'],)).fetchone()
        used = None
        hit = totp.match(mfa['secret'], code, last_step=mfa['last_step']) if mfa else None
        if hit is not None:
            conn.execute('UPDATE account_mfa SET last_step=? WHERE account_id=?', (hit, acc['id']))
            used = 'App'
        else:
            row = conn.execute("SELECT code_hash FROM account_recovery_codes WHERE account_id=? AND code_hash=? AND used_at=''",
                               (acc['id'], _hash_recovery(code))).fetchone()
            if row:
                conn.execute("UPDATE account_recovery_codes SET used_at=datetime('now') WHERE account_id=? AND code_hash=?",
                             (acc['id'], row['code_hash']))
                used = 'Wiederherstellungscode'
        if used:
            _clear_fails(conn, key)
            new = _upgrade(conn, token, acc['id'])
    if not used:
        _fail(directory, key)
        _log(directory, f"konto:{acc['username']}", 'anmeldung_fehlgeschlagen', acc['username'], 'zweiter Faktor', client)
        raise auth.NotLoggedIn('Code stimmt nicht.')
    _log(directory, f"konto:{acc['username']}", 'anmeldung', acc['username'], f'zweiter Faktor: {used}', client)
    return account_view(directory, acc['username']), new


# ---------------------------------------------------------------- zweiten Faktor einrichten

def mfa_start(directory, token, password):
    """Neues Geheimnis erzeugen (noch nicht aktiv). Gibt Geheimnis und otpauth-Adresse für die App zurück."""
    acc, stage = session(directory, token)
    if not acc or stage not in ('voll', 'einrichtung'):
        raise auth.NotLoggedIn('Bitte anmelden.')
    if not auth.verify_password(password or '', acc['pw_hash']):
        raise PermissionError('Passwort stimmt nicht.')
    secret = totp.new_secret()
    with directory._connect() as conn:
        if _mfa_active(conn, acc['id']):
            raise ValueError('Der zweite Faktor ist schon eingerichtet.')
        conn.execute('''INSERT INTO account_mfa(account_id, secret, active) VALUES (?,?,0)
                        ON CONFLICT(account_id) DO UPDATE SET secret=excluded.secret, active=0, last_step=-1''', (acc['id'], secret))
    return {'secret': ' '.join(secret[i:i + 4] for i in range(0, len(secret), 4)), 'uri': totp.uri(secret, acc['username']),
            'notice': 'In der Authenticator-App „Konto hinzufügen“ → Schlüssel eingeben (zeitbasiert). Dann den angezeigten Code bestätigen.'}


def mfa_confirm(directory, token, code, client=''):
    """Einrichtung abschließen: Code aus der App bestätigen. Gibt Wiederherstellungscodes (nur jetzt sichtbar) und ggf. ein neues Token."""
    acc, stage = session(directory, token)
    if not acc or stage not in ('voll', 'einrichtung'):
        raise auth.NotLoggedIn('Bitte anmelden.')
    with directory._connect() as conn:
        mfa = conn.execute('SELECT * FROM account_mfa WHERE account_id=? AND active=0', (acc['id'],)).fetchone()
        if not mfa:
            raise ValueError('Zuerst die Einrichtung starten.')
        hit = totp.match(mfa['secret'], code)
        if hit is None:
            raise PermissionError('Code stimmt nicht – Uhrzeit des Telefons prüfen und den aktuellen Code eingeben.')
        conn.execute("UPDATE account_mfa SET active=1, last_step=?, confirmed_at=datetime('now') WHERE account_id=?", (hit, acc['id']))
        conn.execute('DELETE FROM account_recovery_codes WHERE account_id=?', (acc['id'],))
        codes = []
        for _ in range(RECOVERY_CODES):
            raw = secrets.token_hex(5).upper()
            codes.append(raw[:5] + '-' + raw[5:])
            conn.execute('INSERT INTO account_recovery_codes(account_id, code_hash) VALUES (?,?)', (acc['id'], _hash_recovery(raw)))
        # alle anderen zentralen Sitzungen des Kontos beenden – sie wurden ohne zweiten Faktor geöffnet
        conn.execute('DELETE FROM account_sessions WHERE account_id=? AND token_hash<>?', (acc['id'], auth._token_hash(token)))
        new = _upgrade(conn, token, acc['id']) if stage == 'einrichtung' else None
    _log(directory, f"konto:{acc['username']}", 'zweiter_faktor_eingerichtet', acc['username'], ip=client)
    return {'active': True, 'recovery_codes': codes,
            'notice': 'Wiederherstellungscodes jetzt ausdrucken oder im Passwort-Manager ablegen. Jeder gilt einmal, wenn das Telefon fehlt.'}, new


def mfa_disable(directory, token, password, code, client=''):
    """Zweiten Faktor abschalten (nur ohne Pflicht): Passwort und aktueller Code nötig."""
    acc, stage = session(directory, token)
    if not acc or stage != 'voll':
        raise auth.NotLoggedIn('Bitte anmelden.')
    if require_2fa(directory):
        raise PermissionError('In dieser Installation ist der zweite Faktor Pflicht.')
    if not auth.verify_password(password or '', acc['pw_hash']):
        raise PermissionError('Passwort stimmt nicht.')
    with directory._connect() as conn:
        mfa = conn.execute('SELECT * FROM account_mfa WHERE account_id=? AND active=1', (acc['id'],)).fetchone()
        if not mfa:
            raise ValueError('Kein zweiter Faktor eingerichtet.')
        if totp.match(mfa['secret'], code, last_step=mfa['last_step']) is None:
            raise PermissionError('Code stimmt nicht.')
        conn.execute('DELETE FROM account_mfa WHERE account_id=?', (acc['id'],))
        conn.execute('DELETE FROM account_recovery_codes WHERE account_id=?', (acc['id'],))
    _log(directory, f"konto:{acc['username']}", 'zweiter_faktor_abgeschaltet', acc['username'], ip=client)
    return {'active': False}


def mfa_reset(directory, username, actor=None):
    """Betreiber: zweiten Faktor zurücksetzen (Telefon verloren, keine Codes mehr). Beendet alle Sitzungen des Kontos."""
    with directory._connect() as conn:
        acc = _account(conn, username)
        conn.execute('DELETE FROM account_mfa WHERE account_id=?', (acc['id'],))
        conn.execute('DELETE FROM account_recovery_codes WHERE account_id=?', (acc['id'],))
        slugs = _end_everywhere(directory, conn, acc)
    for slug in slugs:
        _revoke_in_org(directory.get(slug)['db_path'], username, deactivate=False)
    _log(directory, actor, 'zweiter_faktor_zurueckgesetzt', username)
    return account_view(directory, username)


# ---------------------------------------------------------------- Organisation betreten

def membership(directory, username, slug):
    """Rolle eines aktiven Kontos in einer aktiven Organisation – oder None."""
    init(directory)
    with directory._connect() as conn:
        row = conn.execute('''SELECT m.role FROM memberships m JOIN accounts a ON a.id=m.account_id
                              JOIN organizations o ON o.slug=m.slug
                              WHERE a.username=? AND a.active=1 AND m.slug=? AND o.status='aktiv' ''', (username, slug)).fetchone()
    return row['role'] if row else None


def enter(directory, account, slug, client=''):
    """Organisation betreten: Mitgliedschaft prüfen, Benutzer dort anlegen/angleichen, Sitzung öffnen. Gibt das Token zurück."""
    role = membership(directory, account['username'], slug)
    if not role:
        raise PermissionError('Kein Zugang zu dieser Organisation.')
    if require_2fa(directory):
        with directory._connect() as conn:
            if not _mfa_active(conn, account['id']):
                raise PermissionError('Zuerst den zweiten Faktor einrichten.')
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
    _log(directory, f"konto:{account['username']}", 'organisation_betreten', slug, role, client)
    return token


def logout(directory, central_token):
    if central_token:
        with directory._connect() as conn:
            conn.execute('DELETE FROM account_sessions WHERE token_hash=?', (auth._token_hash(central_token),))
