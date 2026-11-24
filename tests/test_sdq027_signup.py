"""SDQ-027/028: Selbstregistrierung, Einladungen, Postausgang und Tarif mit Testphase – über HTTP am Mehrmandanten-Server.

Geprüft: Registrierung nur, wenn freigeschaltet; Konto und Organisation erst nach dem Link; der Link gilt einmal; die
Antwort verrät keine vorhandenen Adressen; Einladung nur durch die Verwaltung, einmalig, zurückziehbar; die letzte
Verwaltung bleibt; Tarifgrenze für Mitglieder; nach Ablauf der Testphase nur lesen (402), Ansehen geht weiter; nichts
verlässt den Server (nur Dateien im Postausgang). Alle Daten fiktiv."""
import datetime as dt
import re
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from sales_tool import abrechnung, accounts, auth, betreiber, einladungen, mailer, tenancy  # noqa: E402
from sales_tool.multi_server import make_multi_handler  # noqa: E402
from test_sdq014_multi_tenant import PW, Client  # noqa: E402

REG = {'email': 'erika@studio.example', 'username': 'erika', 'display_name': 'Erika Beispiel', 'password': PW,
       'org_name': 'Studio Nörd'}


class SignupBase(unittest.TestCase):
    def setUp(self):
        auth._FAILS.clear()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name) / 'm'
        self.dir = tenancy.Directory(self.root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_multi_handler(tenancy.Directory(self.root)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def mails(self):
        """Abgelegte Nachrichten in der Reihenfolge des Postausgangs (älteste zuerst)."""
        return [self.root / mailer.FOLDER / m['file'] for m in reversed(mailer.outbox(self.dir, 500))]

    def last_link(self, kind):
        text = self.mails()[-1].read_text(encoding='utf-8')
        return re.search(kind + r'=([A-Za-z0-9_-]+)', text).group(1)

    def register_and_confirm(self, c=None):
        c = c or Client(self.base)
        status, data, _ = c.call('/api/zentral/registrieren', 'POST', REG)
        self.assertEqual(status, 200, data)
        status, data, _ = c.call('/api/zentral/registrieren/bestaetigen', 'POST', {'token': self.last_link('bestaetigen')})
        self.assertEqual(status, 200, data)
        return data['organization']['slug']


class RegistrationTests(SignupBase):
    def test_closed_by_default_then_confirm_creates_everything(self):
        c = Client(self.base)
        self.assertFalse(c.call('/api/zentral/status')[1]['registration_open'])
        status, data, _ = c.call('/api/zentral/registrieren', 'POST', REG)
        self.assertEqual(status, 403, data)
        betreiber.run(betreiber._parser().parse_args(['--root', str(self.root), 'einstellung', 'registrierung', 'offen']), self.dir)
        accounts.set_setting(self.dir, 'public_url', 'https://app.example.org')
        self.assertTrue(c.call('/api/zentral/status')[1]['registration_open'])
        status, data, _ = c.call('/api/zentral/registrieren', 'POST', REG)
        self.assertEqual(status, 200, data)
        # Noch nichts angelegt: nur Anfrage und Nachricht im Postausgang
        self.assertEqual(self.dir.list(), [])
        with self.assertRaises(LookupError):
            accounts.account_view(self.dir, 'erika')
        mail = self.mails()[-1].read_text(encoding='utf-8')
        self.assertIn('To: erika@studio.example', mail)
        self.assertIn('https://app.example.org/anmelden#bestaetigen=', mail)
        token = self.last_link('bestaetigen')
        with self.dir._connect() as conn:  # Token nur als Hash gespeichert, Link nicht im Protokoll
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM signup_requests WHERE token_hash=?', (token,)).fetchone()[0], 0)
            self.assertNotIn(token, ' '.join(r['detail'] for r in conn.execute('SELECT detail FROM audit_events')))
        status, data, _ = c.call('/api/zentral/registrieren/bestaetigen', 'POST', {'token': token})
        self.assertEqual((status, data['organization']['slug']), (200, 'studio-noerd'))
        status, again, _ = c.call('/api/zentral/registrieren/bestaetigen', 'POST', {'token': token})
        self.assertEqual(status, 404)  # einmalig
        view = accounts.account_view(self.dir, 'erika')
        self.assertEqual((view['email'], view['organizations'][0]['role']), ('erika@studio.example', 'admin'))
        state = abrechnung.state(self.dir, 'studio-noerd')
        self.assertEqual((state['status'], state['days_left']), ('test', abrechnung.DEFAULT_TRIAL_DAYS))
        status, data, _ = c.login('erika')
        self.assertEqual((status, data['entered']), (200, 'studio-noerd'))

    def test_answers_do_not_reveal_existing_addresses_and_are_limited(self):
        accounts.set_setting(self.dir, 'registrierung', 'offen')
        accounts.create_account(self.dir, 'vorhanden', PW, email='erika@studio.example')
        c = Client(self.base)
        status, data, _ = c.call('/api/zentral/registrieren', 'POST', {**REG, 'username': 'neu-erika'})
        self.assertEqual(status, 200)
        self.assertEqual(data['notice'], einladungen.GENERIC)
        self.assertIn('schon ein Konto', self.mails()[-1].read_text(encoding='utf-8'))
        with self.dir._connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM signup_requests').fetchone()[0], 0)
        for bad in ({**REG, 'email': 'keine-adresse'}, {**REG, 'password': 'kurz'}, {**REG, 'org_name': 'x'}, {**REG, 'extra': 1}):
            with self.subTest(bad=bad):
                self.assertEqual(c.call('/api/zentral/registrieren', 'POST', bad)[0], 400)
        codes = [c.call('/api/zentral/registrieren', 'POST', {**REG, 'email': f'p{i}@studio.example', 'username': f'person{i}'})[0]
                 for i in range(6)]
        self.assertIn(429, codes)  # höchstens 5 je IP und Stunde (die erste Anfrage oben zählt mit)

    def test_expired_link_rejected(self):
        accounts.set_setting(self.dir, 'registrierung', 'offen')
        Client(self.base).call('/api/zentral/registrieren', 'POST', REG)
        with self.dir._connect() as conn:
            conn.execute("UPDATE signup_requests SET expires_at=datetime('now', '-1 minute')")
        self.assertEqual(Client(self.base).call('/api/zentral/registrieren/bestaetigen', 'POST',
                                                {'token': self.last_link('bestaetigen')})[0], 404)


class InvitationTests(SignupBase):
    def setUp(self):
        super().setUp()
        accounts.set_setting(self.dir, 'registrierung', 'offen')
        self.slug = self.register_and_confirm()
        self.admin = Client(self.base)
        self.admin.login('erika')

    def invite(self, email='max@studio.example', role='vertrieb', client=None):
        return (client or self.admin).call(f'/api/zentral/orgs/{self.slug}/einladungen', 'POST', {'email': email, 'role': role})

    def test_invite_accept_with_new_account_once(self):
        status, data, _ = self.invite()
        self.assertEqual((status, data['sent']), (201, False))  # nur abgelegt, nicht versendet
        token = self.last_link('einladung')
        guest = Client(self.base)
        status, info, _ = guest.call('/api/zentral/einladung', 'POST', {'token': token})
        self.assertEqual((info['organization'], info['role'], info['has_account'], info['logged_in']), ('Studio Nörd', 'vertrieb', False, False))
        status, data, _ = guest.call('/api/zentral/einladung/annehmen', 'POST', {'token': token, 'username': 'max', 'password': 'Noch-eine-Passphrase-42'})
        self.assertEqual(status, 200, data)
        self.assertEqual(guest.call('/api/zentral/einladung/annehmen', 'POST', {'token': token, 'username': 'max2', 'password': 'Noch-eine-Passphrase-42'})[0], 404)
        self.assertEqual(accounts.membership(self.dir, 'max', self.slug), 'vertrieb')
        self.assertEqual(accounts.account_view(self.dir, 'max')['email'], 'max@studio.example')
        status, team, _ = self.admin.call(f'/api/zentral/orgs/{self.slug}/mitglieder')
        self.assertEqual({m['username'] for m in team['members']}, {'erika', 'max'})
        self.assertEqual(team['invitations'], [])

    def test_existing_account_joins_after_login_and_revoke(self):
        accounts.create_account(self.dir, 'lena', PW, email='lena@studio.example')
        self.invite('lena@studio.example', 'lesen')
        token = self.last_link('einladung')
        lena = Client(self.base)
        self.assertTrue(lena.call('/api/zentral/einladung', 'POST', {'token': token})[1]['has_account'])
        status, data, _ = lena.call('/api/zentral/einladung/annehmen', 'POST', {'token': token, 'username': 'lena2', 'password': 'Noch-eine-Passphrase-42'})
        self.assertEqual(status, 400)  # Adresse hat ein Konto: erst anmelden
        lena.login('lena')
        self.assertEqual(lena.call('/api/zentral/einladung/annehmen', 'POST', {'token': token})[0], 200)
        self.assertEqual(accounts.membership(self.dir, 'lena', self.slug), 'lesen')
        # Zurückziehen
        status, data, _ = self.invite('tom@studio.example')
        token = self.last_link('einladung')
        self.assertEqual(self.admin.call(f"/api/zentral/orgs/{self.slug}/einladungen/{data['id']}", 'DELETE')[0], 200)
        self.assertEqual(Client(self.base).call('/api/zentral/einladung', 'POST', {'token': token})[0], 404)

    def test_only_admins_and_last_admin_stays(self):
        accounts.create_account(self.dir, 'max', PW)
        accounts.set_membership(self.dir, 'max', self.slug, 'vertrieb')
        maxc = Client(self.base)
        maxc.login('max')
        self.assertEqual(self.invite(client=maxc)[0], 403)
        self.assertEqual(maxc.call(f'/api/zentral/orgs/{self.slug}/mitglieder')[0], 403)
        self.assertEqual(maxc.call(f'/api/zentral/orgs/{self.slug}/mitglieder/erika', 'DELETE')[0], 403)
        self.assertEqual(Client(self.base).call(f'/api/zentral/orgs/{self.slug}/mitglieder')[0], 401)
        self.assertEqual(self.admin.call(f'/api/zentral/orgs/{self.slug}/mitglieder/erika', 'DELETE')[0], 400)
        self.assertEqual(self.admin.call(f'/api/zentral/orgs/{self.slug}/mitglieder/max', 'DELETE')[0], 200)
        self.assertIsNone(accounts.membership(self.dir, 'max', self.slug))
        self.assertEqual(self.invite('kaputt', 'vertrieb')[0], 400)
        self.assertEqual(self.invite('ok@studio.example', 'chef')[0], 400)

    def test_member_limit_of_trial(self):
        limit = abrechnung.PLANS['test']['members']
        for i in range(limit - 1):
            self.assertEqual(self.invite(f'p{i}@studio.example')[0], 201)
        status, data, _ = self.invite('zu-viel@studio.example')
        self.assertEqual(status, 403)
        self.assertIn('höchstens', data['error'])


class BillingTests(SignupBase):
    def test_expired_trial_is_read_only_and_operator_reactivates(self):
        accounts.set_setting(self.dir, 'registrierung', 'offen')
        slug = self.register_and_confirm()
        c = Client(self.base)
        c.login('erika')
        status, st, _ = c.call('/api/auth/status')
        self.assertEqual(st['subscription']['status'], 'test')
        self.assertEqual(c.call('/api/leads', 'POST', {'company': 'Vorher Fiktiv GmbH'})[0], 201)
        with self.dir._connect() as conn:
            conn.execute("UPDATE subscriptions SET trial_ends=?", ((dt.date.today() - dt.timedelta(days=1)).isoformat(),))
        status, data, _ = c.call('/api/leads', 'POST', {'company': 'Nachher Fiktiv GmbH'})
        self.assertEqual(status, 402)
        self.assertTrue(data['subscription']['read_only'])
        status, leads, _ = c.call('/api/leads')
        self.assertEqual(status, 200)  # Ansehen geht weiter, nichts gelöscht
        self.assertIn('Vorher Fiktiv GmbH', str(leads))
        self.assertEqual(c.call('/api/auth/logout', 'POST', {})[0], 200)  # Abmelden bleibt möglich
        args = betreiber._parser().parse_args(['--root', str(self.root), 'tarif', slug, '--plan', 'team', '--status', 'aktiv',
                                              '--bis', (dt.date.today() + dt.timedelta(days=30)).isoformat()])
        out, code = betreiber.run(args, self.dir)
        self.assertEqual((code, out['status'], out['read_only'], out['members_limit']), (0, 'aktiv', False, 10))
        c.login('erika')
        self.assertEqual(c.call('/api/leads', 'POST', {'company': 'Nachher Fiktiv GmbH'})[0], 201)

    def test_operator_orgs_unrestricted_and_manual_provider_only(self):
        self.dir.create('nord', 'Nord')
        self.assertTrue(abrechnung.state(self.dir, 'nord')['managed'])
        self.assertIsNone(abrechnung.blocks(self.dir, 'nord', 'POST', '/api/leads'))
        with self.assertRaises(PermissionError):
            abrechnung.provider().checkout('nord', 'team')
        with self.assertRaises(ValueError):
            abrechnung.set_subscription(self.dir, 'nord', plan='gold')
        self.assertTrue(all(set(p) == {'label', 'members'} for p in abrechnung.PLANS.values()))  # keine erfundenen Preise

    def test_operator_settings_validated_and_admin_on_create(self):
        for key, value in (('registrierung', 'ja'), ('public_url', 'http://app.example.org'), ('public_url', 'https://x/pfad'),
                           ('testphase_tage', '0'), ('unbekannt', 'x')):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                accounts.set_setting(self.dir, key, value)
        accounts.create_account(self.dir, 'erika', PW)
        out, code = betreiber.run(betreiber._parser().parse_args(['--root', str(self.root), 'anlegen', 'sued', 'Süd', '--admin', 'erika']), self.dir)
        self.assertEqual(accounts.membership(self.dir, 'erika', 'sued'), 'admin')
        with self.assertRaises(LookupError):  # unbekanntes Konto: Organisation entsteht gar nicht erst
            betreiber.run(betreiber._parser().parse_args(['--root', str(self.root), 'anlegen', 'west', 'West', '--admin', 'nobody']), self.dir)
        self.assertNotIn('west', [o['slug'] for o in self.dir.list()])


if __name__ == '__main__':
    unittest.main()
