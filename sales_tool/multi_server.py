"""Server für mehrere Organisationen (SDQ-015) – eine Datenbank je Organisation, zentrale Anmeldung.

Start:  python -m sales_tool.multi_server --root D:/signaldesk-mandanten [--port 8765] [--host 0.0.0.0 --allowed-host app.example]

Jede Anfrage wird genau einer Organisation zugeordnet, und zwar nur über eine gültige Sitzung in deren Datenbank:
1. Cookie ``sd_org`` nennt die Organisation, Cookie ``sd_session`` die Sitzung. Beide setzt nur der Server (HttpOnly).
2. Die Organisation muss aktiv sein, die Sitzung muss in *ihrer* Datenbank gültig sein, und das Konto muss im Verzeichnis
   noch Mitglied sein. Fehlt eines davon, wird die Anfrage nicht weitergereicht (Seiten → /anmelden, API → 401).
3. Dann übernimmt der gewohnte Handler dieser einen Datenbank (``server.make_handler``) – mit Rollenrechten wie im Team-Betrieb.

Eine fremde oder gefälschte Organisation im Cookie hilft nicht: Ein Sitzungstoken gilt nur in der Datenbank, in der es angelegt
wurde. Ohne Sitzung gibt es nur die Anmeldeseite, ihre Skripte und die unveränderlichen Programmdateien.
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from . import accounts, auth, tenancy
from .model import connect
from .server import (CSP, LOOPBACK_HOSTS, PUBLIC, STATIC_FILES, _CountingReader, _host_name, bind_server, make_handler,
                     prepare_database)

CENTRAL_FILES = {'/anmelden': ('zentral.html', 'text/html'), '/zentral.js': ('zentral.js', 'text/javascript'),
                 '/zentral.css': ('zentral.css', 'text/css')}
# In der Mehrmandanten-Installation zentral geregelt – in der Organisation gesperrt
CENTRAL_ONLY = {('POST', '/api/auth/login'), ('POST', '/api/auth/setup'), ('POST', '/api/auth/password'),
                ('PUT', '/api/auth/settings')}
CENTRAL_ONLY_PREFIX = '/api/auth/users'
MAX_BODY = 16 * 1024


def make_multi_handler(directory: tenancy.Directory, allowed_hosts=None, scheduler=False):
    hosts = LOOPBACK_HOSTS | {h.lower() for h in (allowed_hosts or ())}
    accounts.init(directory)
    classes, lock = {}, threading.Lock()

    def org_class(slug, db_path):
        with lock:
            if slug not in classes:
                classes[slug] = make_handler(db_path, allowed_hosts)
                if scheduler:
                    from .quality import start_scheduler
                    start_scheduler(db_path)
            return classes[slug]

    class FrontHandler(BaseHTTPRequestHandler):
        server_version = 'SignalDesk'

        def setup(self):
            super().setup()
            self.rfile = _CountingReader(self.rfile)

        def log_message(self, fmt, *args):  # keine Pfade/Cookies ins Protokoll
            pass

        # ------------------------------------------------ Antworten
        def _headers(self):
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', CSP)
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cache-Control', 'no-store')

        def _send(self, status, payload, cookies=()):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self._headers()
            for c in cookies:
                self.send_header('Set-Cookie', c)
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, where):
            self.send_response(302)
            self.send_header('Location', where)
            self.send_header('Content-Length', '0')
            self._headers()
            self.end_headers()

        def _file(self, name, mime):
            data = (PUBLIC / name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self._headers()
            self.end_headers()
            self.wfile.write(data)

        def _secure(self):
            return self.headers.get('X-Forwarded-Proto', '') == 'https'

        def _cookie(self, name, value, clear=False, hours=accounts.CENTRAL_HOURS):
            attrs = f"{name}={'' if clear else value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else hours * 3600}"
            return attrs + ('; Secure' if self._secure() else '')

        def _cookies(self):
            out = {}
            for part in (self.headers.get('Cookie') or '').split(';'):
                k, _, v = part.strip().partition('=')
                out.setdefault(k, v)
            return out

        def _body(self):
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ValueError('Nur application/json erlaubt.')
            raw = self.headers.get('Content-Length', '0')
            if not raw.isdigit() or not 0 < int(raw) <= MAX_BODY:
                raise ValueError('Ungültige Anfragegröße.')
            data = json.loads(self.rfile.read(int(raw)))
            if not isinstance(data, dict):
                raise ValueError('Erwartet wird ein JSON-Objekt.')
            return data

        def _unauthorized(self, route, method):
            if route.startswith('/api/'):
                return self._send(401, {'error': 'Bitte anmelden.', 'auth_required': True, 'login_url': '/anmelden'},
                                  [self._cookie(auth.COOKIE, '', clear=True)])
            if method == 'GET':
                return self._redirect('/anmelden')
            return self._send(401, {'error': 'Bitte anmelden.', 'login_url': '/anmelden'})

        # ------------------------------------------------ Ablauf
        def handle_one_request(self):
            try:
                self.raw_requestline = self.rfile.readline(65537)
                if len(self.raw_requestline) > 65536:
                    self.send_error(414)
                    return
                if not self.raw_requestline:
                    self.close_connection = True
                    return
                if not self.parse_request():
                    return
                try:
                    self._dispatch()
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send(400, {'error': str(exc)})
                except auth.Throttled as exc:
                    self._send(429, {'error': str(exc)})
                except auth.NotLoggedIn as exc:
                    self._send(401, {'error': str(exc)})
                except PermissionError as exc:
                    self._send(403, {'error': str(exc)})
                except LookupError as exc:
                    self._send(404, {'error': str(exc).strip("'\"")})
                except Exception as exc:  # noqa: BLE001
                    print('Serverfehler (Mehrmandanten):', repr(exc))
                    self._send(500, {'error': 'Interner Serverfehler'})
                self.wfile.flush()
            except TimeoutError:
                self.close_connection = True

        def _origin_ok(self):
            origin = self.headers.get('Origin')
            host = self.headers.get('Host', '')
            return not origin or origin in (f'http://{host}', f'https://{host}')

        def _dispatch(self):
            method = self.command
            route = urlparse(self.path).path
            if _host_name(self.headers.get('Host', '')) not in hosts:
                return self._send(421, {'error': 'Unbekannter Host.'})
            if method not in ('GET', 'HEAD') and not self._origin_ok():
                return self._send(403, {'error': 'Anfragen von fremden Webseiten sind gesperrt.'})
            if route in CENTRAL_FILES and method == 'GET':
                return self._file(*CENTRAL_FILES[route])
            if route.startswith('/api/zentral/'):
                return self._central(method, route)
            if route == '/api/auth/logout' and method == 'POST':
                return self._logout()
            if (method, route) in CENTRAL_ONLY or route.startswith(CENTRAL_ONLY_PREFIX):
                raise PermissionError('In dieser Installation werden Anmeldung, Passwörter und Benutzer zentral verwaltet.')
            org = self._org_session()
            if not org:
                if method == 'GET' and route in STATIC_FILES and route != '/':
                    return self._file(*STATIC_FILES[route])  # Programmdateien sind für alle gleich
                return self._unauthorized(route, method)
            slug, db_path = org
            if (method, route) == ('GET', '/api/auth/status'):  # wie im Team-Betrieb, dazu Organisation und Hinweis „zentral“
                with connect(db_path) as conn:
                    st = auth.status(conn, auth.session_user(conn, self.headers.get('Cookie', '')))
                return self._send(200, {**st, 'central': True, 'switch_url': '/anmelden',
                                        'organization': {'slug': slug, 'name': directory.get(slug)['name']},
                                        'notice': 'Konten, Passwörter und Rollen verwaltet der Betreiber zentral.'})
            handler_cls = org_class(slug, db_path)
            h = handler_cls.__new__(handler_cls)
            h.__dict__.update(self.__dict__)
            do = getattr(h, 'do_' + method, None)
            if do is None:
                return self._send(405, {'error': 'Methode nicht erlaubt.'})
            do()
            self.close_connection = h.close_connection

        def _org_session(self):
            """(Kennung, Datenbank) der Organisation dieser Anfrage – nur mit gültiger Sitzung und Mitgliedschaft."""
            cookies = self._cookies()
            slug = cookies.get(accounts.ORG_COOKIE, '')
            if not tenancy.SLUG_RE.match(slug or ''):
                return None
            try:
                db_path = directory.open(slug)
            except (LookupError, tenancy.TenantError):
                return None
            with connect(db_path) as conn:
                user = auth.session_user(conn, self.headers.get('Cookie', ''))
                if not user:
                    return None
                role = accounts.membership(directory, user['username'], slug)
                if not role:  # Mitgliedschaft entzogen oder Konto gesperrt: Sitzung hier beenden
                    conn.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                    conn.commit()
                    return None
                if role != user['role']:
                    conn.execute('UPDATE users SET role=? WHERE id=?', (role, user['id']))
                    conn.commit()
            return slug, db_path

        # ------------------------------------------------ zentrale Endpunkte
        def _central(self, method, route):
            token = self._cookies().get(accounts.CENTRAL_COOKIE, '')
            if route == '/api/zentral/login' and method == 'POST':
                b = self._body()
                if set(b) != {'username', 'password'}:
                    raise ValueError('Erwartet: {username, password}.')
                view, tok = accounts.login(directory, b['username'], b['password'], self.client_address[0] if self.client_address else '')
                cookies = [self._cookie(accounts.CENTRAL_COOKIE, tok)]
                active = [o for o in view['organizations'] if o['status'] == 'aktiv']
                entered = None
                if len(active) == 1:  # nur eine Organisation: direkt hinein
                    acc = accounts.central_account(directory, tok)
                    cookies += self._enter_cookies(acc, active[0]['slug'])
                    entered = active[0]['slug']
                return self._send(200, {**self._view(view), 'entered': entered}, cookies)
            acc = accounts.central_account(directory, token)
            if route == '/api/zentral/status' and method == 'GET':
                if not acc:
                    return self._send(200, {'logged_in': False})
                return self._send(200, {'logged_in': True, **self._view(accounts.account_view(directory, acc['username'])),
                                        'current': self._cookies().get(accounts.ORG_COOKIE, '')})
            if not acc:
                raise auth.NotLoggedIn('Bitte anmelden.')
            if route == '/api/zentral/enter' and method == 'POST':
                b = self._body()
                slug = b.get('slug') if set(b) == {'slug'} else None
                if not isinstance(slug, str):
                    raise ValueError('Erwartet: {slug}.')
                self._end_org_session()
                return self._send(200, {'entered': slug}, self._enter_cookies(acc, slug))
            if route == '/api/zentral/password' and method == 'POST':
                b = self._body()
                if set(b) != {'old', 'new'}:
                    raise ValueError('Erwartet: {old, new}.')
                accounts.change_password(directory, acc['username'], b['old'], b['new'])
                self._end_org_session()
                return self._send(200, {'changed': True, 'notice': 'Passwort geändert – bitte neu anmelden.'}, self._clear_all())
            if route == '/api/zentral/logout' and method == 'POST':
                return self._logout()
            return self._send(404, {'error': 'Endpunkt nicht gefunden'})

        @staticmethod
        def _view(view):
            return {'user': {k: view[k] for k in ('username', 'display_name')},
                    'organizations': [{k: o[k] for k in ('slug', 'name', 'role')} for o in view['organizations'] if o['status'] == 'aktiv']}

        def _enter_cookies(self, acc, slug):
            token = accounts.enter(directory, acc, slug)
            return [self._cookie(accounts.ORG_COOKIE, slug, hours=auth.SESSION_HOURS),
                    self._cookie(auth.COOKIE, token, hours=auth.SESSION_HOURS)]

        def _end_org_session(self):
            org = self._org_session()
            if org:
                with connect(org[1]) as conn:
                    auth.logout(conn, self.headers.get('Cookie', ''))

        def _clear_all(self):
            return [self._cookie(n, '', clear=True) for n in (accounts.CENTRAL_COOKIE, accounts.ORG_COOKIE, auth.COOKIE)]

        def _logout(self):
            self._end_org_session()
            accounts.logout(directory, self._cookies().get(accounts.CENTRAL_COOKIE, ''))
            return self._send(200, {'logged_out': True, 'login_url': '/anmelden'}, self._clear_all())

    return FrontHandler


def prepare_all(directory):
    """Beim Start: jede aktive Organisation migrieren und offene Aufträge fortsetzen."""
    from .research import jobs as research_jobs
    out = []
    for org in directory.list():
        db = Path(org['db_path'])
        prepare_database(db)
        with connect(db) as conn:
            if research_jobs.pending(conn)[0]:
                research_jobs.ensure_workers(db)
        out.append(org['slug'])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='SignalDesk für mehrere Organisationen (eine Datenbank je Organisation)')
    ap.add_argument('--root', required=True, help='Ordner des Mandantenverzeichnisses (tools/organisationen.py)')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--allowed-host', action='append', default=[])
    ap.add_argument('--no-scheduler', action='store_true')
    args = ap.parse_args(argv)
    directory = tenancy.Directory(args.root)
    allowed = set(args.allowed_host)
    if args.host not in ('127.0.0.1', 'localhost', '::1'):
        print('Hinweis: SignalDesk spricht nur HTTP. Im Netzwerk unbedingt hinter einem TLS-Proxy (HTTPS) betreiben.')
        if args.host not in ('0.0.0.0', '::'):
            allowed.add(args.host)
    orgs = prepare_all(directory)
    server, port = bind_server(make_multi_handler(directory, allowed, scheduler=not args.no_scheduler), args.port, host=args.host)
    print(f'SignalDesk (Mehrmandanten) läuft: http://127.0.0.1:{port}/anmelden  |  {len(orgs)} Organisationen in {directory.root}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
