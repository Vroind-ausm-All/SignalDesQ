"""Entwürfe ins Postfach legen über IMAP (2.0.0-dev43, Produktreview M24 Stufe 3).

IMAP ist der offene Standard aller Postfach-Anbieter (Google, iCloud, mailbox.org, IONOS, Strato, GMX, web.de …).
SignalDesk legt einen fertigen Entwurf in den **Entwürfe-Ordner** – dort öffnest du ihn in deinem Mailprogramm, prüfst
Empfänger und Inhalt und versendest ihn selbst.

- **Nie Versand:** kein SMTP, kein Senden-Befehl. Die einzige schreibende Aktion ist APPEND in den Entwürfe-Ordner
  mit der Markierung \\Draft. Andere Ordner und vorhandene Nachrichten werden weder gelesen noch geändert.
- **Vor jedem Ablegen erneut geprüft:** Kontaktsperre der Firma (inkl. Sperrliste) und Einschränkungen der Person.
- **Empfänger:** nur die geschäftliche E-Mail-Adresse der Firma, wenn eingetragen – sonst leer (im Mailprogramm ergänzen).
- Nur verschlüsselt (IMAP über SSL, Port 993); unverschlüsselt nur zu Testzwecken auf diesem Rechner.
- Passwort nie in der Datenbank (credentials.py), App-Passwort empfohlen. Offline-Modus: keine Verbindung.
"""
from __future__ import annotations

import datetime as dt
import imaplib
import re
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

SETTING = 'imap'
LOCAL = ('127.0.0.1', 'localhost', '::1')
DRAFT_NAMES = ('entwürfe', 'drafts', 'entwurf', 'inbox.drafts', 'inbox/drafts', 'inbox.entwürfe', '[gmail]/drafts', '[gmail]/entwürfe')


def init_imap(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(mail_drafts)')}
    for name, decl in (('imap_saved_at', "TEXT NOT NULL DEFAULT ''"), ('imap_folder', "TEXT NOT NULL DEFAULT ''")):
        if name not in cols:
            conn.execute(f'ALTER TABLE mail_drafts ADD COLUMN {name} {decl}')


def _settings(conn):
    from .quality import get_setting
    return get_setting(conn, SETTING, {'host': '', 'port': 993, 'username': '', 'sender': '', 'folder': '', 'last_result': ''})


# ------------------------------------------------------------- Ordnernamen (IMAP: modifiziertes UTF-7, RFC 3501)

def decode_mutf7(name):
    def rep(m):
        s = m.group(1)
        if not s:
            return '&'
        b = s.replace(',', '/')
        b += '=' * (-len(b) % 4)
        import base64
        return base64.b64decode(b).decode('utf-16-be')
    return re.sub(r'&([A-Za-z0-9+,]*)-', rep, name)


def _quote(name):
    return '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'


LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?:"(?:[^"\\]|\\.)*"|NIL) (?P<name>"(?:[^"\\]|\\.)*"|\S+)$')


def pick_drafts(lines):
    """Entwürfe-Ordner aus der LIST-Antwort: zuerst die Markierung \\Drafts (RFC 6154), sonst übliche Namen."""
    folders = []
    for raw in lines:
        if not isinstance(raw, bytes):
            continue
        m = LIST_RE.search(raw.strip())
        if not m:
            continue
        name = m.group('name').decode('ascii', 'replace')
        if name.startswith('"'):
            name = name[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        folders.append((m.group('flags').decode('ascii', 'replace').lower(), name))
    for flags, name in folders:
        if '\\drafts' in flags.split():
            return name
    for flags, name in folders:
        if decode_mutf7(name).lower() in DRAFT_NAMES:
            return name
    return ''


# ------------------------------------------------------------- Verbindung

def _check_host(host, port):
    if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9.-]{1,253}|::1', host.strip()):
        raise ValueError('Postfach-Server angeben, z. B. imap.anbieter.de.')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Port: Zahl zwischen 1 und 65535 (üblich: 993).')
    from . import hosting
    hosting.check_service_host(host.strip().lower(), port, hosting.IMAP_PORTS, 'Postfach-Server')
    return host.strip().lower()


def view(conn, db_path):
    from .credentials import status, store_info
    s = _settings(conn)
    return {'host': s['host'], 'port': s['port'], 'username': s['username'], 'sender': s['sender'], 'folder': s['folder'],
            'folder_label': decode_mutf7(s['folder']) if s['folder'] else '', 'configured': bool(s['host'] and s['username']),
            'password': status(db_path, 'imap'), 'password_store': store_info(db_path, 'imap'), 'last_result': s['last_result'],
            'notice': 'SignalDesk legt nur Entwürfe in den Entwürfe-Ordner und versendet nie. Am besten ein App-Passwort verwenden.'}


def save(conn, db_path, data):
    if not isinstance(data, dict) or set(data) - {'host', 'port', 'username', 'sender', 'password', 'remember', 'forget'}:
        raise ValueError('Erwartet: host, port, username, sender, password, remember, forget.')
    from .credentials import forget, put
    from .quality import put_setting
    s = _settings(conn)
    before = ((s['host'] or '').lower().rstrip('.'), s['port'], (s['username'] or '').strip())
    if data.get('forget') is True:
        forget(db_path, 'imap')
    if 'host' in data or 'port' in data:
        host, port = data.get('host', s['host']), data.get('port', s['port'])
        s['host'], s['port'] = (_check_host(host, port), port) if host else ('', port)
        s['folder'] = ''  # neuer Server → Ordner neu suchen
    for key, limit in (('username', 200), ('sender', 200)):
        if key in data:
            v = data[key]
            if not isinstance(v, str) or len(v) > limit:
                raise ValueError(f'{key}: höchstens {limit} Zeichen.')
            s[key] = v.strip()
    if s['sender'] and not re.fullmatch(r'[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+', s['sender']):
        raise ValueError('Absender: eine E-Mail-Adresse, z. B. hallo@deine-agentur.de.')
    if data.get('password'):
        put(db_path, 'imap', data['password'], remember=data.get('remember') is True)
    elif ((s['host'] or '').lower().rstrip('.'), s['port'], (s['username'] or '').strip()) != before:
        forget(db_path, 'imap')  # F03: neues Ziel oder Konto – das alte Passwort geht nie an einen anderen Server
    put_setting(conn, SETTING, s)
    conn.commit()
    return view(conn, db_path)


def _connect(conn, db_path):
    from . import netpolicy
    from .credentials import get
    netpolicy.load(conn)
    netpolicy.assert_online('das Ablegen im Postfach')
    s = _settings(conn)
    if not (s['host'] and s['username']):
        raise ValueError('Zuerst Postfach-Server und Benutzername eintragen.')
    from . import hosting
    hosting.check_service_host(s['host'], s['port'], hosting.IMAP_PORTS, 'Postfach-Server')  # bei jeder Verwendung
    pw = get(db_path, 'imap')
    if not pw:
        raise ValueError('Passwort für das Postfach fehlt (nach einem Neustart erneut eingeben oder „auf diesem Rechner merken“).')
    try:
        if s['host'] in LOCAL and s['port'] != 993:
            box = imaplib.IMAP4(s['host'], s['port'], timeout=20)  # nur zu Testzwecken auf diesem Rechner
        else:
            box = imaplib.IMAP4_SSL(s['host'], s['port'], ssl_context=ssl.create_default_context(), timeout=20)
    except (OSError, imaplib.IMAP4.error) as e:
        raise ValueError(f'Postfach nicht erreichbar ({e}).') from e
    try:
        box.login(s['username'], pw)
    except (imaplib.IMAP4.error, UnicodeEncodeError) as e:
        _close(box)
        raise ValueError('Anmeldung beim Postfach abgelehnt – Benutzername oder (App-)Passwort prüfen.') from e
    return box, s


def _close(box):
    try:
        box.logout()
    except (OSError, imaplib.IMAP4.error):
        pass


def _find_folder(box):
    typ, lines = box.list()
    if typ != 'OK':
        raise ValueError('Ordnerliste des Postfachs nicht lesbar.')
    folder = pick_drafts(lines or [])
    if not folder:
        raise ValueError('Kein Entwürfe-Ordner gefunden. Bitte im Mailprogramm einmal einen Entwurf speichern und erneut prüfen.')
    return folder


def test(conn, db_path):
    from .quality import put_setting
    box, s = _connect(conn, db_path)
    try:
        s['folder'] = _find_folder(box)
    finally:
        _close(box)
    s['last_result'] = f'Verbindung steht, Entwürfe-Ordner „{decode_mutf7(s["folder"])}“ ({dt.datetime.now():%d.%m.%Y %H:%M})'
    put_setting(conn, SETTING, s)
    conn.commit()
    return {**view(conn, db_path), 'ok': True}


# ------------------------------------------------------------- Entwurf ablegen

def build_message(conn, draft, sender):
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (draft['lead_id'],)).fetchone()
    msg = EmailMessage()
    msg['Subject'] = draft['subject']
    if sender:
        msg['From'] = sender
    if lead['business_email']:
        msg['To'] = lead['business_email']
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='signaldesk.local')
    msg.set_content(draft['body'])
    return msg


def put_draft(conn, db_path, draft_id):
    d = conn.execute('SELECT * FROM mail_drafts WHERE id=?', (draft_id,)).fetchone()
    if not d:
        raise LookupError('Entwurf nicht gefunden.')
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (d['lead_id'],)).fetchone()
    from .workday import assert_contact_allowed
    assert_contact_allowed(conn, lead, 'Entwurf ins Postfach legen')  # Stand jetzt, nicht beim Erstellen
    if d['contact_id']:
        from .messages import values
        values(conn, lead, None, d['contact_id'])  # Einschränkungen der Person (z. B. „keine E-Mail“)
    box, s = _connect(conn, db_path)
    try:
        folder = s['folder'] or _find_folder(box)
        msg = build_message(conn, d, s['sender'])
        typ, data = box.append(_quote(folder), '(\\Draft)', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != 'OK':
            raise ValueError(f'Postfach hat den Entwurf nicht angenommen ({(data or [b""])[0]!r}).')
    finally:
        _close(box)
    from .quality import put_setting
    now = dt.datetime.now().isoformat(timespec='seconds')
    s['folder'] = folder
    s['last_result'] = f'Entwurf „{d["subject"]}“ abgelegt ({dt.datetime.now():%d.%m.%Y %H:%M})'
    put_setting(conn, SETTING, s)
    conn.execute('UPDATE mail_drafts SET imap_saved_at=?, imap_folder=? WHERE id=?', (now, folder, draft_id))
    conn.commit()
    return {'saved': True, 'folder': decode_mutf7(folder), 'imap_saved_at': now, 'to': msg['To'] or '',
            'notice': f'Im Ordner „{decode_mutf7(folder)}“ abgelegt – nicht versendet. Im Mailprogramm Empfänger und Inhalt prüfen und selbst senden.'}


def route_imap(h, conn, method, route, db_path):
    if route == '/api/imap':
        if method == 'GET':
            h._send(200, view(conn, db_path))
            return True
        if method == 'POST':
            h._send(200, save(conn, db_path, h._body()))
            return True
        return False
    if route == '/api/imap/test' and method == 'POST':
        h._send(200, test(conn, db_path))
        return True
    m = re.fullmatch(r'/api/workspace/mail-drafts/(\d+)/postfach', route)
    if m and method == 'POST':
        h._send(200, put_draft(conn, db_path, int(m.group(1))))
        return True
    return False
