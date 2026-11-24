"""Selbstregistrierung und Einladungen in der Mehrmandanten-Installation (SDQ-027).

**Registrierung** (nur wenn der Betreiber ``registrierung=offen`` gesetzt hat): Eine Person gibt E-Mail, Benutzername,
Passwort und den Namen ihrer Organisation an. Gespeichert wird zunächst nur eine Anfrage mit Passwort-Hash
(``signup_requests``); per Postausgang geht ein einmaliger Link an die E-Mail-Adresse. Erst mit diesem Link entstehen
Konto, Organisation (Testphase, ``abrechnung``) und die Rolle ``admin``. Die Antwort verrät nie, ob es eine Adresse schon gibt.

**Einladung**: Wer in einer Organisation ``admin`` ist, lädt per E-Mail ein (``invitations``). Der Link gilt 7 Tage und
genau einmal. Wer ihn öffnet, meldet sich mit einem vorhandenen Konto an oder legt ein neues an (die E-Mail-Adresse gilt
damit als bestätigt). Einladungen lassen sich zurückziehen; Mitglieder lassen sich entfernen (nicht die letzte Verwaltung).

Tokens stehen nur als SHA-256 in der Datenbank. Jede Aktion landet im Protokoll (``audit_trail``), der Link nie.
Häufigkeit: höchstens 5 Registrierungen je IP-Adresse und Stunde, 3 je E-Mail-Adresse und Tag, 50 Einladungen je
Organisation und Tag (``signup_events``).
"""
from __future__ import annotations

import datetime as dt
import re
import secrets

from . import abrechnung, accounts, audit_trail, auth, mailer, tenancy

SIGNUP_HOURS = 24
INVITE_DAYS = 7
LIMITS = {'ip': (5, 60), 'email': (3, 24 * 60), 'einladung': (50, 24 * 60)}
GENERIC = ('Wenn die Angaben stimmen, liegt jetzt eine Nachricht mit einem Bestätigungslink im Postausgang. '
           'Der Link gilt 24 Stunden.')


def init(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS signup_requests (
        token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, username TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
        pw_hash TEXT NOT NULL, org_name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL, confirmed_at TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS invitations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT NOT NULL UNIQUE, slug TEXT NOT NULL REFERENCES organizations(slug),
        email TEXT NOT NULL, role TEXT NOT NULL, invited_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL, accepted_at TEXT NOT NULL DEFAULT '', accepted_by TEXT NOT NULL DEFAULT '',
        revoked_at TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS signup_events (key TEXT NOT NULL, at TEXT NOT NULL DEFAULT (datetime('now')));
      CREATE INDEX IF NOT EXISTS signup_events_key ON signup_events(key, at);
    ''')


def _hash(token):
    return auth._token_hash(token)


def _now(delta):
    return (dt.datetime.now(dt.timezone.utc) + delta).strftime('%Y-%m-%d %H:%M:%S')


def _limit(directory, kind, value):
    limit, minutes = LIMITS[kind]
    key = f'{kind}:{(value or "").casefold()}'
    with directory._connect() as conn:
        init(conn)
        conn.execute("DELETE FROM signup_events WHERE at < datetime('now', '-2 days')")
        n = conn.execute("SELECT COUNT(*) FROM signup_events WHERE key=? AND at > datetime('now', ?)",
                         (key, f'-{minutes} minutes')).fetchone()[0]
        if n >= limit:
            raise auth.Throttled('Zu viele Anfragen – bitte später erneut versuchen.')
        conn.execute('INSERT INTO signup_events(key) VALUES (?)', (key,))


def _link(directory, fragment):
    base = accounts.setting(directory, 'public_url', '') or 'http://127.0.0.1:8765'
    return f'{base}/anmelden#{fragment}'


def registration_open(directory):
    return accounts.setting(directory, 'registrierung', 'aus') == 'offen'


def _slug_for(directory, name):
    base = re.sub(r'[^a-z0-9]+', '-', name.casefold().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
                  .replace('ß', 'ss')).strip('-')[:30].strip('-') or 'organisation'
    if base in tenancy.RESERVED:
        base = 'org-' + base
    slug, n = base, 1
    while True:
        try:
            directory.get(slug)
        except LookupError:
            if not directory.path_for(slug).exists():
                return slug
        n += 1
        slug = f'{base}-{n}'


# ---------------------------------------------------------------- Registrierung

def register(directory, data, client=''):
    """Registrierung anfragen. Gibt immer dieselbe Antwort zurück, außer bei offensichtlich falschen Eingaben."""
    if not registration_open(directory):
        raise PermissionError('Registrierung ist in dieser Installation nicht freigeschaltet.')
    if not isinstance(data, dict) or set(data) - {'email', 'username', 'display_name', 'password', 'org_name'}:
        raise ValueError('Erwartet: {email, username, display_name, password, org_name}.')
    email = accounts.check_email(data.get('email'))
    username = data.get('username')
    auth._check_username(username)
    auth._check_password_policy(data.get('password'), username)
    org_name = str(data.get('org_name') or '').strip()
    if not 2 <= len(org_name) <= 120:
        raise ValueError('Name der Organisation: 2–120 Zeichen.')
    _limit(directory, 'ip', client)
    _limit(directory, 'email', email)
    taken_email = accounts.account_by_email(directory, email)
    with directory._connect() as conn:
        taken_user = conn.execute('SELECT 1 FROM accounts WHERE username=?', (username,)).fetchone()
    m = mailer.get_mailer(directory)
    if taken_email:  # kein Hinweis in der Antwort – die Person erfährt es nur über ihr Postfach
        m.send(email, 'SignalDesk: Registrierung', 'Für diese E-Mail-Adresse gibt es schon ein Konto. Bitte dort anmelden: '
               + _link(directory, 'anmelden') + '\n\nWar das nicht Ihre Anfrage, können Sie diese Nachricht ignorieren.\n',
               'registrierung-vorhanden')
        audit_trail.record(directory, 'anonym', 'registrierung_angefragt', email, 'Adresse vorhanden', client)
        return {'requested': True, 'notice': GENERIC}
    if taken_user:
        raise ValueError(f'Benutzername „{username}“ ist vergeben.')
    token = secrets.token_urlsafe(32)
    with directory._connect() as conn:
        init(conn)
        conn.execute('''INSERT INTO signup_requests(token_hash, email, username, display_name, pw_hash, org_name, expires_at)
                        VALUES (?,?,?,?,?,?,?)''', (_hash(token), email, username, str(data.get('display_name') or '')[:80],
                                                    auth.hash_password(data['password']), org_name,
                                                    _now(dt.timedelta(hours=SIGNUP_HOURS))))
    m.send(email, 'SignalDesk: Registrierung bestätigen',
           f'Bitte bestätigen Sie die Registrierung von „{org_name}“ mit diesem Link (24 Stunden gültig):\n\n'
           + _link(directory, 'bestaetigen=' + token) + '\n\nWar das nicht Ihre Anfrage, ignorieren Sie diese Nachricht.\n',
           'registrierung')
    audit_trail.record(directory, 'anonym', 'registrierung_angefragt', email, username, client)
    return {'requested': True, 'notice': GENERIC}


def confirm(directory, token, client=''):
    """Registrierung bestätigen: Konto, Organisation (Testphase) und Rolle admin entstehen erst hier."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise ValueError('Link ungültig.')
    with directory._connect() as conn:
        init(conn)
        row = conn.execute('''SELECT * FROM signup_requests WHERE token_hash=? AND confirmed_at='' AND expires_at > datetime('now')''',
                           (_hash(token),)).fetchone()
        if not row:
            raise LookupError('Link ungültig, abgelaufen oder schon benutzt.')
    actor = f"konto:{row['username']}"
    # Konto zuerst: Ist der Name inzwischen vergeben, scheitert es hier, und der Link bleibt unverbraucht.
    accounts.create_account(directory, row['username'], None, row['display_name'], actor=actor, email=row['email'],
                            pw_hash=row['pw_hash'])
    with directory._connect() as conn:
        conn.execute("UPDATE signup_requests SET confirmed_at=datetime('now') WHERE token_hash=?", (_hash(token),))
    slug = _slug_for(directory, row['org_name'])
    directory.create(slug, row['org_name'], actor=actor)
    abrechnung.start_trial(directory, slug, accounts.setting(directory, 'testphase_tage', None), actor=actor)
    accounts.set_membership(directory, row['username'], slug, 'admin', actor=actor)
    audit_trail.record(directory, actor, 'registrierung_bestaetigt', slug, '', client)
    return {'confirmed': True, 'username': row['username'], 'organization': {'slug': slug, 'name': row['org_name']},
            'notice': 'Registrierung bestätigt. Bitte jetzt anmelden.'}


# ---------------------------------------------------------------- Einladungen

def _require_admin(directory, account, slug):
    if accounts.membership(directory, account['username'], slug) != 'admin':
        raise PermissionError('Nur die Verwaltung der Organisation darf einladen und Mitglieder entfernen.')


def invite(directory, account, slug, email, role, client=''):
    _require_admin(directory, account, slug)
    email = accounts.check_email(email)
    if role not in auth.ROLES:
        raise ValueError('Rolle: ' + ', '.join(auth.ROLES))
    abrechnung.check_member_limit(directory, slug, adding=1 + len(pending(directory, slug)))
    _limit(directory, 'einladung', slug)
    token = secrets.token_urlsafe(32)
    org = directory.get(slug)
    with directory._connect() as conn:
        init(conn)
        conn.execute('''UPDATE invitations SET revoked_at=datetime('now')
                        WHERE slug=? AND email=? COLLATE NOCASE AND accepted_at='' AND revoked_at=\'\'''', (slug, email))
        cur = conn.execute('INSERT INTO invitations(token_hash, slug, email, role, invited_by, expires_at) VALUES (?,?,?,?,?,?)',
                           (_hash(token), slug, email, role, account['username'], _now(dt.timedelta(days=INVITE_DAYS))))
    sent = mailer.get_mailer(directory).send(
        email, f"SignalDesk: Einladung zu {org['name']}",
        f"{account['display_name'] or account['username']} lädt Sie zu „{org['name']}“ in SignalDesk ein (Rolle: {role}).\n\n"
        f"Einladung annehmen (7 Tage gültig, nur einmal):\n{_link(directory, 'einladung=' + token)}\n\n"
        'Kennen Sie die einladende Person nicht, ignorieren Sie diese Nachricht.\n', 'einladung')
    audit_trail.record(directory, f"konto:{account['username']}", 'einladung_erstellt', slug, f'{email} als {role}', client)
    return {'id': cur.lastrowid, 'email': email, 'role': role, 'outbox': sent['file'], 'sent': sent['sent']}


def pending(directory, slug):
    with directory._connect() as conn:
        init(conn)
        rows = conn.execute('''SELECT id, email, role, invited_by, created_at, expires_at FROM invitations
                               WHERE slug=? AND accepted_at='' AND revoked_at='' AND expires_at > datetime('now') ORDER BY id''',
                            (slug,)).fetchall()
    return [dict(r) for r in rows]


def members(directory, account, slug):
    _require_admin(directory, account, slug)
    with directory._connect() as conn:
        rows = conn.execute('''SELECT a.username, a.display_name, a.email, a.active, m.role FROM memberships m
                               JOIN accounts a ON a.id=m.account_id WHERE m.slug=? ORDER BY a.username''', (slug,)).fetchall()
    return {'members': [dict(r) for r in rows], 'invitations': pending(directory, slug),
            'subscription': abrechnung.state(directory, slug), 'roles': auth.ROLES}


def revoke(directory, account, slug, invitation_id, client=''):
    _require_admin(directory, account, slug)
    with directory._connect() as conn:
        init(conn)
        n = conn.execute('''UPDATE invitations SET revoked_at=datetime('now')
                            WHERE id=? AND slug=? AND accepted_at='' AND revoked_at=\'\'''', (invitation_id, slug)).rowcount
    if not n:
        raise LookupError('Einladung nicht gefunden oder schon erledigt.')
    audit_trail.record(directory, f"konto:{account['username']}", 'einladung_zurueckgezogen', slug, str(invitation_id), client)
    return {'revoked': True}


def remove_member(directory, account, slug, username, client=''):
    _require_admin(directory, account, slug)
    with directory._connect() as conn:
        admins = [r['username'] for r in conn.execute('''SELECT a.username FROM memberships m JOIN accounts a ON a.id=m.account_id
                                                         WHERE m.slug=? AND m.role='admin' AND a.active=1''', (slug,))]
    if admins == [username]:
        raise ValueError('Die letzte Verwaltung kann nicht entfernt werden.')
    return accounts.remove_membership(directory, username, slug, actor=f"konto:{account['username']}")


def _invitation(conn, token):
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise ValueError('Link ungültig.')
    row = conn.execute('''SELECT i.*, o.name AS org_name FROM invitations i JOIN organizations o ON o.slug=i.slug
                          WHERE i.token_hash=? AND i.accepted_at='' AND i.revoked_at='' AND i.expires_at > datetime('now')
                          AND o.status='aktiv' ''', (_hash(token),)).fetchone()
    if not row:
        raise LookupError('Einladung ungültig, abgelaufen, zurückgezogen oder schon angenommen.')
    return row


def invitation_info(directory, token):
    with directory._connect() as conn:
        init(conn)
        row = _invitation(conn, token)
    return {'organization': row['org_name'], 'role': row['role'], 'email': row['email'],
            'has_account': bool(accounts.account_by_email(directory, row['email']))}


def accept(directory, token, account=None, new=None, client=''):
    """Einladung annehmen – mit angemeldetem Konto (``account``) oder neuem Konto (``new`` = {username, password, display_name})."""
    with directory._connect() as conn:
        init(conn)
        row = _invitation(conn, token)
    if account is None:
        if not isinstance(new, dict) or set(new) - {'username', 'password', 'display_name'}:
            raise ValueError('Erwartet: {username, password, display_name} oder vorher anmelden.')
        if accounts.account_by_email(directory, row['email']):
            raise ValueError('Für diese E-Mail-Adresse gibt es schon ein Konto – bitte zuerst anmelden.')
        accounts.create_account(directory, new.get('username'), new.get('password'), new.get('display_name') or '',
                                actor=f"konto:{new.get('username')}", email=row['email'])
        username = new['username']
    else:
        username = account['username']
    if not accounts.membership(directory, username, row['slug']):
        abrechnung.check_member_limit(directory, row['slug'])
    with directory._connect() as conn:  # erst jetzt verbrauchen: einmalig, auch bei gleichzeitigen Aufrufen
        n = conn.execute('''UPDATE invitations SET accepted_at=datetime('now'), accepted_by=?
                            WHERE id=? AND accepted_at='' AND revoked_at=\'\'''', (username, row['id'])).rowcount
    if not n:
        raise LookupError('Einladung wurde gerade schon verwendet.')
    accounts.set_membership(directory, username, row['slug'], row['role'], actor=f'konto:{username}')
    audit_trail.record(directory, f'konto:{username}', 'einladung_angenommen', row['slug'], row['role'], client)
    return {'accepted': True, 'username': username, 'organization': {'slug': row['slug'], 'name': row['org_name']}}
