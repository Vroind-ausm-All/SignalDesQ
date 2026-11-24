"""Server für mehrere Organisationen (SDQ-015) – eine Datenbank je Organisation, zentrale Anmeldung.

Start:  python -m sales_tool.multi_server --root D:/signaldesk-mandanten [--port 8765] [--host 0.0.0.0 --allowed-host app.example]

Jede Anfrage wird genau einer Organisation zugeordnet, und zwar nur über eine gültige Sitzung in deren Datenbank:
1. Cookie ``sd_org`` nennt die Organisation, Cookie ``sd_session`` die Sitzung. Beide setzt nur der Server (HttpOnly).
2. Die Organisation muss aktiv sein, die Sitzung muss in *ihrer* Datenbank gültig sein, und das Konto muss im Verzeichnis
   noch Mitglied sein. Fehlt eines davon, wird die Anfrage nicht weitergereicht (Seiten → /anmelden, API → 401).
3. Dann übernimmt der gewohnte Handler dieser einen Datenbank (``server.make_handler``) – mit Rollenrechten wie im Team-Betrieb.

Eine fremde oder gefälschte Organisation im Cookie hilft nicht: Ein Sitzungstoken gilt nur in der Datenbank, in der es angelegt
wurde. Ohne Sitzung gibt es nur die Anmeldeseite, ihre Skripte und die unveränderlichen Programmdateien.

Betrieb (SDQ-017/019): ``/healthz`` (Prozess lebt) und ``/readyz`` (bereit; Einzelheiten nur bei direktem lokalem Aufruf)
ohne Anmeldung; je Anfrage eine JSON-Zeile im Betriebsprotokoll und eine Anfrage-Nummer im Kopf ``X-Request-ID``.
Zweiter Faktor (SDQ-021): Nach dem Passwort folgt bei eingerichtetem zweitem Faktor der Code aus der App; vorher gibt es
keine Liste der Organisationen und keinen Zutritt.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import secrets
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import re

from . import hosting, abrechnung, accounts, auth, einladungen, ops, tenancy
from .model import connect
from .server import (CSP, LOOPBACK_HOSTS, PUBLIC, STATIC_FILES, _CountingReader, _host_name, bind_server, drain_request, make_handler,
                     prepare_database)

CENTRAL_FILES = {'/anmelden': ('zentral.html', 'text/html'), '/zentral.js': ('zentral.js', 'text/javascript'),
                 '/zentral.css': ('zentral.css', 'text/css')}
# In der Mehrmandanten-Installation zentral geregelt – in der Organisation gesperrt
CENTRAL_ONLY = {('POST', '/api/auth/login'), ('POST', '/api/auth/setup'), ('POST', '/api/auth/password'),
                ('PUT', '/api/auth/settings')}
CENTRAL_ONLY_PREFIX = '/api/auth/users'
MAX_BODY = 16 * 1024
HEALTH_ROUTES = ('/healthz', '/readyz')


class _RequestMeta:
    """Status und Anfrage-Nummer mitschreiben – auch im Handler der Organisation, der die Antwort selbst sendet."""

    def send_response(self, code, message=None):
        self._sd_status = code
        super().send_response(code, message)
        rid = getattr(self, '_sd_rid', '')
        if rid:
            self.send_header('X-Request-ID', rid)


def make_multi_handler(directory: tenancy.Directory, allowed_hosts=None, scheduler=False, logger=None, backup_target=None,
                       trusted_proxies=(), ready_cache_seconds=30):
    hosts = LOOPBACK_HOSTS | {h.lower() for h in (allowed_hosts or ())}
    accounts.init(directory)
    classes, lock = {}, threading.Lock()
    trusted = {ipaddress.ip_address(p) for p in trusted_proxies}  # SDQ-039 (F08): nur diesen Proxys wird X-Forwarded-For geglaubt
    ready_lock = threading.Lock()
    ready_cache = {'at': 0.0, 'report': None}  # SDQ-040 (F10): öffentliche Bereitschaft höchstens alle 30 s neu prüfen

    def org_class(slug, db_path):
        with lock:
            if slug not in classes:
                hosting.register(db_path)  # SDQ-037: Betriebsgrenzen (Legacy-Abruf, Browser, lokale Ziele, Web-Restore)
                classes[slug] = type('OrgHandler', (_RequestMeta, make_handler(db_path, allowed_hosts)), {})
                if scheduler:
                    from .quality import start_scheduler
                    start_scheduler(db_path, paused=lambda: abrechnung.state(directory, slug)['read_only'])
            return classes[slug]

    class FrontHandler(_RequestMeta, BaseHTTPRequestHandler):
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
            attrs = f"{name}={'' if clear else value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else int(hours * 3600)}"
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
                self._sd_rid, self._sd_status, self._sd_org = secrets.token_hex(6), 0, ''
                self._body_from = self.rfile.count
                t0 = time.perf_counter()
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
                    if logger:
                        logger.error('serverfehler', exc_info=True, extra={'fields': {'rid': self._sd_rid, 'type': exc.__class__.__name__}})
                    else:
                        print('Serverfehler (Mehrmandanten):', repr(exc))
                    self._send(500, {'error': 'Interner Serverfehler', 'request_id': self._sd_rid})
                drain_request(self)  # abgelehnte Anfrage (fremde Herkunft, Host, Tarif): Körper lesen, sonst bricht Windows ab
                self.wfile.flush()
                ops.log_request(logger, rid=self._sd_rid, method=self.command, path=self.path, status=self._sd_status,
                                ms=(time.perf_counter() - t0) * 1000, org=self._sd_org)
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
            if route in HEALTH_ROUTES and method in ('GET', 'HEAD'):
                return self._health(route)
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
            self._sd_org = slug
            blocked = abrechnung.blocks(directory, slug, method, route)
            if blocked:  # SDQ-028: Testphase/Tarif abgelaufen – nur lesen und exportieren
                return self._send(402, {'error': blocked['notice'], 'subscription': blocked})
            if (method, route) == ('GET', '/api/auth/status'):  # wie im Team-Betrieb, dazu Organisation und Hinweis „zentral“
                with connect(db_path) as conn:
                    st = auth.status(conn, auth.session_user(conn, self.headers.get('Cookie', '')))
                return self._send(200, {**st, 'central': True, 'switch_url': '/anmelden',
                                        'organization': {'slug': slug, 'name': directory.get(slug)['name']},
                                        'subscription': abrechnung.state(directory, slug),
                                        'notice': 'Konten, Passwörter und Rollen verwaltet der Betreiber zentral.'})
            handler_cls = org_class(slug, db_path)
            h = handler_cls.__new__(handler_cls)
            h.__dict__.update(self.__dict__)
            do = getattr(h, 'do_' + method, None)
            if do is None:
                return self._send(405, {'error': 'Methode nicht erlaubt.'})
            do()
            self.close_connection = h.close_connection
            self._sd_status = getattr(h, '_sd_status', 0)

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
                user = auth.session_user(conn, self.headers.get('Cookie', ''), idle_minutes=accounts.idle_minutes(directory))
                if not user:
                    return None
                role, stamp = accounts.org_access(directory, user['username'], slug)
                if not role:  # Mitgliedschaft entzogen, Konto gesperrt oder zweiter Faktor Pflicht und fehlt: Sitzung beenden
                    conn.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                    conn.commit()
                    return None
                if auth.session_stamp(conn, self.headers.get('Cookie', '')) != stamp:
                    # Passwort, zweiter Faktor oder Sperre haben sich seit dem Öffnen geändert (F02): neu anmelden
                    auth.end_session(conn, self.headers.get('Cookie', ''))
                    return None
                if role != user['role']:
                    conn.execute('UPDATE users SET role=? WHERE id=?', (role, user['id']))
                    conn.commit()
            central = cookies.get(accounts.CENTRAL_COOKIE, '')
            if central:  # Arbeit in der Organisation hält auch die zentrale Sitzung (Wechsel der Organisation) am Leben
                accounts.session(directory, central)
            return slug, db_path

        # ------------------------------------------------ Betrieb
        def _local(self):
            """Direkter Aufruf vom selben Rechner (nicht über den Proxy weitergereicht)."""
            ip = self.client_address[0] if self.client_address else ''
            return ip in ('127.0.0.1', '::1') and not self.headers.get('X-Forwarded-For')

        def _health(self, route):
            if route == '/healthz':
                return self._send(200, ops.health())
            if self._local():
                report = ops.readiness(directory, detail=True, backup_target=backup_target)
            else:  # von außen nur das Ergebnis, keine Einzelheiten – und zwischengespeichert, damit Abfragen nichts kosten
                with ready_lock:
                    if ready_cache['report'] is None or time.monotonic() - ready_cache['at'] > ready_cache_seconds:
                        full = ops.readiness(directory, detail=False, backup_target=backup_target)
                        ready_cache.update(at=time.monotonic(), report={'status': full['status'], 'version': full['version']})
                    report = dict(ready_cache['report'])
            return self._send(200 if report['status'] == 'bereit' else 503, report)

        # ------------------------------------------------ zentrale Endpunkte
        def _client(self):
            """IP des Clients. Hinter einem eingetragenen Proxy (``--vertrauter-proxy``) der Eintrag, den dieser Proxy als
            letzten an X-Forwarded-For angehängt hat; sonst immer der direkte Verbindungspartner (selbst gesetzte Header
            zählen nicht)."""
            direct = self.client_address[0] if self.client_address else ''
            try:
                from_proxy = ipaddress.ip_address(direct) in trusted
            except ValueError:
                from_proxy = False
            if from_proxy:
                last = (self.headers.get('X-Forwarded-For') or '').split(',')[-1].strip()
                try:
                    return str(ipaddress.ip_address(last))
                except ValueError:
                    return direct
            return direct

        def _after_full_login(self, view, tok):
            """Volle Anmeldung: Cookie setzen, bei genau einer Organisation direkt hinein."""
            cookies = [self._cookie(accounts.CENTRAL_COOKIE, tok)]
            active = [o for o in view['organizations'] if o['status'] == 'aktiv']
            entered = None
            if len(active) == 1:  # nur eine Organisation: direkt hinein
                acc = accounts.central_account(directory, tok)
                cookies += self._enter_cookies(acc, active[0]['slug'])
                entered = active[0]['slug']
            return self._send(200, {**self._view(view), 'stage': 'voll', 'entered': entered}, cookies)

        def _central(self, method, route):
            token = self._cookies().get(accounts.CENTRAL_COOKIE, '')
            if route == '/api/zentral/login' and method == 'POST':
                b = self._body()
                if set(b) != {'username', 'password'}:
                    raise ValueError('Erwartet: {username, password}.')
                view, tok = accounts.login(directory, b['username'], b['password'], self._client())
                if view['stage'] == 'voll':
                    return self._after_full_login(view, tok)
                # Zwischenstufe: kurzlebiges Cookie, keine Organisationen, kein Zutritt
                pending = [self._cookie(accounts.CENTRAL_COOKIE, tok, hours=accounts.PENDING_MINUTES / 60)]
                return self._send(200, {'stage': view['stage'], 'user': {'username': view['username'], 'display_name': view['display_name']}},
                                  pending)
            if route == '/api/zentral/logout' and method == 'POST':
                return self._logout()
            acc, stage = accounts.session(directory, token)
            full = acc if stage == 'voll' else None
            # SDQ-027: Registrierung und Einladung – ohne Anmeldung erreichbar, jeweils mit einmaligem Link
            if route == '/api/zentral/registrieren' and method == 'POST':
                return self._send(200, einladungen.register(directory, self._body(), self._client()))
            if route == '/api/zentral/registrieren/bestaetigen' and method == 'POST':
                b = self._body()
                if set(b) != {'token'}:
                    raise ValueError('Erwartet: {token}.')
                return self._send(200, einladungen.confirm(directory, b['token'], self._client()))
            if route == '/api/zentral/einladung' and method == 'POST':
                b = self._body()
                if set(b) != {'token'}:
                    raise ValueError('Erwartet: {token}.')
                return self._send(200, {**einladungen.invitation_info(directory, b['token']), 'logged_in': bool(full),
                                        'username': full['username'] if full else ''})
            if route == '/api/zentral/einladung/annehmen' and method == 'POST':
                b = self._body()
                tok = b.pop('token', None)
                out = einladungen.accept(directory, tok, account=full, new=None if full else b, client=self._client())
                return self._send(200, out)
            if route == '/api/zentral/status' and method == 'GET':
                if not acc:
                    return self._send(200, {'logged_in': False, 'registration_open': einladungen.registration_open(directory)})
                if stage != 'voll':
                    return self._send(200, {'logged_in': False, 'stage': stage,
                                            'user': {'username': acc['username'], 'display_name': acc['display_name']}})
                view = accounts.account_view(directory, acc['username'])
                return self._send(200, {'logged_in': True, 'stage': 'voll', **self._view(view),
                                        'two_factor': view['two_factor'], 'recovery_codes_left': view['recovery_codes_left'],
                                        'require_2fa': accounts.require_2fa(directory),
                                        'current': self._cookies().get(accounts.ORG_COOKIE, '')})
            if route == '/api/zentral/code' and method == 'POST':
                b = self._body()
                if set(b) != {'code'}:
                    raise ValueError('Erwartet: {code}.')
                view, tok = accounts.second_factor(directory, token, b['code'], self._client())
                return self._after_full_login(view, tok)
            if route == '/api/zentral/2fa/start' and method == 'POST':
                b = self._body()
                if set(b) != {'password'}:
                    raise ValueError('Erwartet: {password}.')
                return self._send(200, accounts.mfa_start(directory, token, b['password']))
            if route == '/api/zentral/2fa/confirm' and method == 'POST':
                b = self._body()
                if set(b) != {'code'}:
                    raise ValueError('Erwartet: {code}.')
                out, new = accounts.mfa_confirm(directory, token, b['code'], self._client())
                return self._send(200, out, [self._cookie(accounts.CENTRAL_COOKIE, new)] if new else [])
            if not acc or stage != 'voll':
                raise auth.NotLoggedIn('Bitte anmelden.')
            if route == '/api/zentral/2fa/off' and method == 'POST':
                b = self._body()
                if set(b) != {'password', 'code'}:
                    raise ValueError('Erwartet: {password, code}.')
                return self._send(200, accounts.mfa_disable(directory, token, b['password'], b['code'], self._client()))
            if route == '/api/zentral/enter' and method == 'POST':
                b = self._body()
                slug = b.get('slug') if set(b) == {'slug'} else None
                if not isinstance(slug, str):
                    raise ValueError('Erwartet: {slug}.')
                self._end_org_session()
                return self._send(200, {'entered': slug}, self._enter_cookies(acc, slug))
            m = re.fullmatch(r'/api/zentral/orgs/([a-z0-9-]{1,40})/(mitglieder|einladungen)(?:/([A-Za-z0-9._-]{1,40}))?', route)
            if m:
                slug, kind, item = m.groups()
                if kind == 'mitglieder' and method == 'GET' and not item:
                    return self._send(200, einladungen.members(directory, acc, slug))
                if kind == 'einladungen' and method == 'POST' and not item:
                    b = self._body()
                    if set(b) != {'email', 'role'}:
                        raise ValueError('Erwartet: {email, role}.')
                    return self._send(201, einladungen.invite(directory, acc, slug, b['email'], b['role'], self._client()))
                if kind == 'einladungen' and method == 'DELETE' and item and item.isdigit():
                    return self._send(200, einladungen.revoke(directory, acc, slug, int(item), self._client()))
                if kind == 'mitglieder' and method == 'DELETE' and item:
                    return self._send(200, einladungen.remove_member(directory, acc, slug, item, self._client()))
                return self._send(405, {'error': 'Methode nicht erlaubt.'})
            if route == '/api/zentral/password' and method == 'POST':
                b = self._body()
                if set(b) != {'old', 'new'}:
                    raise ValueError('Erwartet: {old, new}.')
                accounts.change_password(directory, acc['username'], b['old'], b['new'], ip=self._client())
                self._end_org_session()
                return self._send(200, {'changed': True, 'notice': 'Passwort geändert – bitte neu anmelden.'}, self._clear_all())
            return self._send(404, {'error': 'Endpunkt nicht gefunden'})

        @staticmethod
        def _view(view):
            return {'user': {k: view[k] for k in ('username', 'display_name')},
                    'organizations': [{k: o[k] for k in ('slug', 'name', 'role')} for o in view['organizations'] if o['status'] == 'aktiv']}

        def _enter_cookies(self, acc, slug):
            token = accounts.enter(directory, acc, slug, self._client())
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


def build_parser():
    ap = argparse.ArgumentParser(description='SignalDesk für mehrere Organisationen (eine Datenbank je Organisation)')
    ap.add_argument('--root', required=True, help='Ordner des Mandantenverzeichnisses (python -m sales_tool.betreiber)')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--allowed-host', action='append', default=[])
    ap.add_argument('--no-scheduler', action='store_true')
    ap.add_argument('--log-file', help='Betriebsprotokoll als JSON-Zeilen (Standard: stderr); Rotation 10 × 10 MB')
    ap.add_argument('--log-level', default='INFO', choices=('DEBUG', 'INFO', 'WARNING', 'ERROR'))
    ap.add_argument('--vertrauter-proxy', action='append', default=[], metavar='IP',
                    help='IP des TLS-Proxys, dessen X-Forwarded-For gilt (z. B. 127.0.0.1). Ohne: direkte Verbindung zählt.')
    ap.add_argument('--backup-dir', help='Ordner der Sicherungssätze für /readyz (Standard: <root>/sicherungen)')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    directory = tenancy.Directory(args.root)
    logger = ops.access_logger(args.log_file, args.log_level)
    allowed = set(args.allowed_host)
    if args.host not in ('127.0.0.1', 'localhost', '::1'):
        print('Hinweis: SignalDesk spricht nur HTTP. Im Netzwerk unbedingt hinter einem TLS-Proxy (HTTPS) betreiben.')
        if args.host not in ('0.0.0.0', '::'):
            allowed.add(args.host)
    orgs = prepare_all(directory)
    handler = make_multi_handler(directory, allowed, scheduler=not args.no_scheduler, logger=logger, backup_target=args.backup_dir,
                                 trusted_proxies=args.vertrauter_proxy)
    server, port = bind_server(handler, args.port, attempts=1, host=args.host)  # Dienst: fester Port, kein Ausweichen
    server.daemon_threads = True

    def stop(signum, _frame):  # systemd stop / docker stop: laufende Anfragen beenden lassen, dann aus
        logger.info('stopp', extra={'fields': {'signal': signum}})
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    logger.info('start', extra={'fields': {'port': port, 'organizations': len(orgs), 'version': ops.__version__}})
    print(f'SignalDesk (Mehrmandanten) läuft: http://127.0.0.1:{port}/anmelden  |  {len(orgs)} Organisationen in {directory.root}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        from .quality import stop_scheduler
        for org in directory.list(include_archived=True):
            stop_scheduler(org['db_path'])
        server.server_close()
        logger.info('beendet')


if __name__ == '__main__':
    main()
