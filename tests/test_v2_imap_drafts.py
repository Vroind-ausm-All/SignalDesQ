"""2.0.0-dev43: Produktreview M24 Stufe 3 – Entwürfe ins Postfach (IMAP), nie Versand.

Gegen einen nachgebauten IMAP-Server auf 127.0.0.1 (LOGIN, LIST, APPEND) – keine Abrufe nach außen.
- Entwürfe-Ordner wird erkannt (Markierung \\Drafts, sonst übliche Namen; Umlaute in modifiziertem UTF-7).
- Ablegen nur mit APPEND und Markierung \\Draft; kein anderer schreibender Befehl, kein SMTP im ganzen Programm.
- Vor dem Ablegen erneut geprüft: Kontaktsperre der Firma, Sperrliste, Einschränkung der Person.
- Empfänger nur die geschäftliche Adresse der Firma; Passwort nie in der Datenbank; Offline-Modus: keine Verbindung.
Alle Firmen sind fiktiv.
"""
import email
import json
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tmpclean import cleanup_tmp  # noqa: E402

from cred_fake import FakeStore  # noqa: E402
from sales_tool import credentials, imap_drafts, netpolicy  # noqa: E402
from sales_tool.model import connect  # noqa: E402
from sales_tool.server import prepare_database  # noqa: E402
from sales_tool.workday import ContactLocked  # noqa: E402

USER, PASS = 'hallo@agentur-fiktiv.de', 'imap-app-pass'
ROOT = Path(__file__).parent.parent / 'sales_tool'


class FakeIMAP(socketserver.StreamRequestHandler):
    folders = [(r'\HasNoChildren', 'INBOX'), (r'\HasNoChildren \Drafts', 'Entw&APw-rfe'), (r'\HasNoChildren \Sent', 'Gesendet')]
    appended: list = []
    commands: list = []

    def send(self, line):
        self.wfile.write(line.encode() + b'\r\n')

    def handle(self):
        self.send('* OK IMAP4rev1 Fiktiv bereit')
        authed = False
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            tag, _, rest = line.partition(' ')
            cmd, _, args = rest.partition(' ')
            cmd = cmd.upper()
            FakeIMAP.commands.append(cmd)
            if cmd == 'CAPABILITY':
                self.send('* CAPABILITY IMAP4rev1 AUTH=PLAIN')
                self.send(f'{tag} OK CAPABILITY fertig')
            elif cmd == 'LOGIN':
                user, pw = [a.strip('"') for a in args.split(' ', 1)]
                authed = (user, pw) == (USER, PASS)
                self.send(f'{tag} OK angemeldet' if authed else f'{tag} NO [AUTHENTICATIONFAILED] falsch')
            elif cmd == 'LIST' and authed:
                for flags, name in FakeIMAP.folders:
                    self.send(f'* LIST ({flags}) "/" "{name}"')
                self.send(f'{tag} OK LIST fertig')
            elif cmd == 'APPEND' and authed:
                size = int(args.rsplit('{', 1)[1].rstrip('}'))
                head = args.rsplit('{', 1)[0].strip()
                self.send('+ bereit')
                data = self.rfile.read(size)
                self.rfile.readline()
                FakeIMAP.appended.append((head, data))
                self.send(f'{tag} OK [APPENDUID 1 {len(FakeIMAP.appended)}] APPEND fertig')
            elif cmd == 'LOGOUT':
                self.send('* BYE')
                self.send(f'{tag} OK LOGOUT fertig')
                return
            else:
                self.send(f'{tag} BAD unbekannt')


class ImapDraftTests(unittest.TestCase):
    def setUp(self):
        credentials.set_backend(FakeStore())  # SDQ-004: nie den echten Schlüsselbund benutzen
        netpolicy.STATE.update(stored=False, forced=False)
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'i.sqlite3')
        prepare_database(self.db)
        c = self.conn = connect(self.db)
        self.lead = c.execute("INSERT INTO leads(company, business_email, stage) VALUES ('Postfach Fiktiv GmbH', 'info@postfach-fiktiv.example', 'termin')").lastrowid
        self.draft = c.execute("""INSERT INTO mail_drafts(lead_id, draft_type, subject, body, contact_basis)
                                  VALUES (?, 'nach_gespraech', 'Unser Gespräch – nächste Schritte', 'Guten Tag,\n\nvielen Dank.', 'Gespräch vom 10.11.')""",
                               (self.lead,)).lastrowid
        c.commit()
        FakeIMAP.appended, FakeIMAP.commands = [], []
        FakeIMAP.folders = [(r'\HasNoChildren', 'INBOX'), (r'\HasNoChildren \Drafts', 'Entw&APw-rfe'), (r'\HasNoChildren \Sent', 'Gesendet')]
        self.srv = socketserver.ThreadingTCPServer(('127.0.0.1', 0), FakeIMAP)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.conn.close()
        credentials._MEMORY.clear()
        credentials.set_backend('auto')
        netpolicy.STATE.update(stored=False, forced=False)
        cleanup_tmp(self.tmp)

    def configure(self, pw=PASS):
        return imap_drafts.save(self.conn, self.db, {'host': '127.0.0.1', 'port': self.srv.server_address[1], 'username': USER,
                                                     'sender': USER, 'password': pw})

    def test_put_draft_into_drafts_folder(self):
        self.configure()
        v = imap_drafts.test(self.conn, self.db)
        self.assertEqual(v['folder_label'], 'Entwürfe')
        r = imap_drafts.put_draft(self.conn, self.db, self.draft)
        self.assertEqual(r['folder'], 'Entwürfe')
        self.assertIn('nicht versendet', r['notice'])
        self.assertEqual(len(FakeIMAP.appended), 1)
        head, data = FakeIMAP.appended[0]
        self.assertTrue(head.startswith('"Entw&APw-rfe" (\\Draft)'), head)
        msg = email.message_from_bytes(data)
        self.assertEqual(msg['To'], 'info@postfach-fiktiv.example')
        self.assertEqual(msg['From'], USER)
        self.assertIn('Unser Gespräch', str(email.header.make_header(email.header.decode_header(msg['Subject']))))
        self.assertIn('vielen Dank', msg.get_content() if hasattr(msg, 'get_content') else msg.get_payload(decode=True).decode())
        row = self.conn.execute('SELECT imap_saved_at, imap_folder FROM mail_drafts WHERE id=?', (self.draft,)).fetchone()
        self.assertTrue(row['imap_saved_at'])
        self.assertEqual(row['imap_folder'], 'Entw&APw-rfe')
        self.assertEqual(set(FakeIMAP.commands) - {'CAPABILITY', 'LOGIN', 'LIST', 'APPEND', 'LOGOUT'}, set(), 'nur lesen der Ordnerliste und APPEND')

    def test_folder_detection_by_name(self):
        self.assertEqual(imap_drafts.pick_drafts([b'(\\HasNoChildren) "." INBOX', b'(\\HasNoChildren) "." "INBOX.Drafts"']), 'INBOX.Drafts')
        self.assertEqual(imap_drafts.pick_drafts([b'(\\HasNoChildren) "/" "Entw&APw-rfe"']), 'Entw&APw-rfe')
        self.assertEqual(imap_drafts.pick_drafts([b'(\\HasNoChildren) "/" INBOX']), '')
        self.assertEqual(imap_drafts.decode_mutf7('Entw&APw-rfe'), 'Entwürfe')
        FakeIMAP.folders = [(r'\HasNoChildren', 'INBOX')]
        self.configure()
        with self.assertRaisesRegex(ValueError, 'Kein Entwürfe-Ordner'):
            imap_drafts.put_draft(self.conn, self.db, self.draft)
        self.assertEqual(FakeIMAP.appended, [])

    def test_locks_are_checked_again(self):
        self.configure()
        self.conn.execute("UPDATE leads SET permission='nicht_kontaktieren' WHERE id=?", (self.lead,))
        self.conn.commit()
        with self.assertRaises(ContactLocked):
            imap_drafts.put_draft(self.conn, self.db, self.draft)
        self.conn.execute("UPDATE leads SET permission='unbekannt' WHERE id=?", (self.lead,))
        pid = self.conn.execute("INSERT INTO decision_contacts(lead_id, full_name, contact_restrictions) VALUES (?, 'Frau Beispiel', '[\"keine_email\"]')",
                                (self.lead,)).lastrowid
        self.conn.execute('UPDATE mail_drafts SET contact_id=? WHERE id=?', (pid, self.draft))
        self.conn.commit()
        with self.assertRaisesRegex(ContactLocked, 'keine E-Mails'):
            imap_drafts.put_draft(self.conn, self.db, self.draft)
        self.assertEqual(FakeIMAP.appended, [], 'gesperrt: keine Verbindung, nichts abgelegt')
        self.assertNotIn('LOGIN', FakeIMAP.commands)

    def test_password_offline_and_wrong_login(self):
        self.configure(pw='falsch')
        with self.assertRaisesRegex(ValueError, 'Anmeldung beim Postfach abgelehnt'):
            imap_drafts.test(self.conn, self.db)
        self.configure()
        self.assertNotIn(PASS, json.dumps(imap_drafts.view(self.conn, self.db)))
        self.conn.execute('PRAGMA wal_checkpoint(FULL)')
        for p in Path(self.tmp.name).glob('i.sqlite3*'):
            self.assertNotIn(PASS.encode(), p.read_bytes(), p.name)
        netpolicy.set_offline(self.conn, True)
        n = len(FakeIMAP.commands)
        with self.assertRaises(Exception):
            imap_drafts.put_draft(self.conn, self.db, self.draft)
        self.assertEqual(len(FakeIMAP.commands), n, 'offline: keine Verbindung')
        with self.assertRaisesRegex(ValueError, 'Absender'):
            imap_drafts.save(self.conn, self.db, {'sender': 'kein-mail'})

    def test_no_sending_anywhere(self):
        for f in ROOT.rglob('*.py'):
            text = f.read_text(encoding='utf-8')
            self.assertNotIn('smtplib', text, f'{f.name}: SignalDesk versendet nie')
            if 'imaplib' in text:
                self.assertEqual(f.name, 'imap_drafts.py', f'{f.name}: Postfach nur über imap_drafts.py')
        code = (ROOT / 'imap_drafts.py').read_text(encoding='utf-8')
        for call in ('.store(', '.expunge(', '.copy(', '.move(', '.delete(', '.select(', '.fetch(', '.uid('):
            self.assertNotIn(call, code, f'kein {call} – nur Entwürfe ablegen')


if __name__ == '__main__':
    unittest.main()
