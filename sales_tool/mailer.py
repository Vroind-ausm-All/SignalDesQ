"""Austauschbarer Postausgang für Einladungen und Bestätigungen (SDQ-027).

SignalDesk verschickt in dieser Fassung **keine** E-Mails. Der einzige Weg ist ``ablage``: Jede Nachricht wird als
``.eml``-Datei in ``<root>/postausgang/`` abgelegt und in der Tabelle ``outbox`` des Verzeichnisses vermerkt. Der Betreiber
kann sie ansehen (``betreiber … postausgang``) und den Link von Hand weitergeben. Ein echter Versand (SMTP oder Anbieter)
braucht eine eigene Klasse mit derselben Methode ``send`` und eine ausdrückliche Freigabe – Zugangsdaten gehören dann in
die Umgebung des Dienstes, nicht in den Code.

Der Inhalt einer Nachricht ist ein einmaliger Link. Er steht nur in der Datei, nicht im Protokoll und nicht in ``outbox``
(dort nur Empfänger, Betreff, Zweck und Dateiname).
"""
from __future__ import annotations

import datetime as dt
import os
import secrets
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

from . import tenancy

BACKENDS = ('ablage',)
FOLDER = 'postausgang'


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        to_addr TEXT NOT NULL, subject TEXT NOT NULL, purpose TEXT NOT NULL, backend TEXT NOT NULL,
        file TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'abgelegt')''')


class AblageMailer:
    """Legt Nachrichten als Datei ab. Nichts verlässt den Server."""
    name = 'ablage'

    def __init__(self, directory: tenancy.Directory, sender='signaldesk@localhost'):
        self.directory = directory
        self.sender = sender
        self.folder = directory.root / FOLDER

    def send(self, to, subject, body, purpose):
        msg = EmailMessage()
        msg['From'] = self.sender
        msg['To'] = to
        msg['Subject'] = subject
        msg['Date'] = format_datetime(dt.datetime.now(dt.timezone.utc))
        msg['Message-ID'] = make_msgid(domain='signaldesk.invalid')
        msg.set_content(body, cte='8bit')  # Link nicht umbrechen (kein quoted-printable)
        self.folder.mkdir(mode=0o700, exist_ok=True)
        name = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{purpose}-{secrets.token_hex(4)}.eml"
        path = self.folder / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # nur der Dienst darf den Link lesen
        with os.fdopen(fd, 'wb') as fh:
            fh.write(bytes(msg))
        with self.directory._connect() as conn:
            init(conn)
            cur = conn.execute('INSERT INTO outbox(to_addr, subject, purpose, backend, file) VALUES (?,?,?,?,?)',
                               (to, subject, purpose, self.name, name))
        return {'id': cur.lastrowid, 'backend': self.name, 'file': name, 'sent': False}


def get_mailer(directory):
    return AblageMailer(directory)


def outbox(directory, limit=50):
    with directory._connect() as conn:
        init(conn)
        rows = conn.execute('SELECT * FROM outbox ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
    return [dict(r) for r in rows]
