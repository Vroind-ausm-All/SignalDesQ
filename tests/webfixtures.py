"""Testgelände für den Website-Abruf (Sprint 0): lokaler Server + simuliertes Netz.

- ``FixtureServer`` bedient die fiktiven Websites aus ``tests/fixtures/web/manifest.json`` (nach Host-Header).
- ``simulated_network`` lenkt DNS und Verbindungen um, ohne die Sicherheitsprüfungen von SignalDesk abzuschalten:
  *.example löst auf eine (fiktive) öffentliche Adresse auf, Verbindungen dorthin landen beim lokalen Server.
  Private Ziele (z. B. 10.0.0.1) werden protokolliert und sofort abgelehnt – so ist messbar, ob Code eine
  NICHT geprüfte Adresse überhaupt ansteuert (DNS-Rebinding-Lücke).
Es gibt keinerlei echte Netzwerkzugriffe.
"""
from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent / 'fixtures' / 'web'
FAKE_PUBLIC_IP = '93.184.216.34'


def load_manifest():
    return json.loads((WEB / 'manifest.json').read_text(encoding='utf-8'))


class FixtureServer:
    def __init__(self):
        self.manifest = load_manifest()
        self.log = []  # (host, path, status)
        self.headers_log = []  # (host, path, {Kopfzeilen})
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def do_GET(self):
                host = (self.headers.get('Host') or '').split(':')[0].lower()
                path = self.path.split('?')[0]
                site = outer.manifest['sites'].get(host)
                status, headers, body = 404, {'Content-Type': 'text/plain'}, b'not found'
                route = {}
                if site:
                    route = {**site['routes'].get('*', {}), **site['routes'].get(path, {})}
                    if 'headers' in site['routes'].get('*', {}) and 'headers' in site['routes'].get(path, {}):
                        route['headers'] = {**site['routes']['*']['headers'], **site['routes'][path]['headers']}
                    if route.get('delay'):
                        time.sleep(route['delay'])
                    if route.get('location'):
                        status, headers, body = route.get('status', 302), {'Location': route['location'].replace('{path}', self.path)}, b''
                    elif route.get('status') and route['status'] >= 400:
                        status, body = route['status'], b'error'
                    elif route.get('size'):
                        status, headers, body = 200, {'Content-Type': 'text/html'}, None
                    elif path == '/robots.txt' and site.get('robots') is not None:
                        status, headers, body = 200, {'Content-Type': 'text/plain'}, site['robots'].encode()
                    elif path in site['pages']:
                        fname = site['pages'][path]
                        body = (WEB / fname).read_bytes()
                        ctype = 'application/pdf' if path.endswith('.pdf') else 'text/html'
                        status, headers = 200, {'Content-Type': ctype}
                    for k, v in (route.get('headers') or {}).items():
                        headers[k] = v
                    if path == '/robots.txt' and headers.get('Content-Encoding') == 'gzip' and body and body[:2] != b'\x1f\x8b':
                        import gzip
                        body = gzip.compress(body)  # Kopfzeile sagt gzip → Inhalt auch wirklich gzip
                outer.log.append((host, path, status))
                outer.headers_log.append((host, path, dict(self.headers.items())))
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                if body is None:  # große Antwort streamen
                    size = route['size']
                    self.send_header('Content-Length', str(size))
                    self.end_headers()
                    chunk = b'<p>' + b'x' * 65530 + b'</p>'
                    sent = 0
                    try:
                        while sent < size:
                            part = chunk[:min(len(chunk), size - sent)]
                            self.wfile.write(part)
                            sent += len(part)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    def hits(self, host=None, path=None):
        return [x for x in self.log if (host is None or x[0] == host) and (path is None or x[1] == path)]


class NetLog:
    def __init__(self):
        self.resolutions = []        # (host, ip)
        self.connects = []           # (ip, port, ok)
        self.unvalidated = []        # Verbindungsversuche zu privaten/unbekannten Adressen


@contextlib.contextmanager
def simulated_network(server, rebind_hosts=('rebind.example',)):
    """DNS: *.example → FAKE_PUBLIC_IP (Ausnahmen aus manifest['resolve']); rebind.example liefert beim ersten Mal die
    öffentliche, danach eine private Adresse. Verbindungen zu FAKE_PUBLIC_IP gehen an den lokalen Server."""
    log = NetLog()
    real_gai, real_cc = socket.getaddrinfo, socket.create_connection
    special = server.manifest.get('resolve', {})
    counts = {}

    def gai(host, port, family=0, type=0, proto=0, flags=0):
        h = (host or '').lower().rstrip('.')
        if h in ('127.0.0.1', 'localhost'):
            return real_gai(host, port, family, type, proto, flags)
        counts[h] = counts.get(h, 0) + 1
        if h in rebind_hosts:
            ip = FAKE_PUBLIC_IP if counts[h] == 1 else '10.0.0.2'
        elif h in special:
            ip = special[h]
        elif h.endswith('.example'):
            ip = FAKE_PUBLIC_IP
        else:
            raise socket.gaierror(-2, 'Name or service not known (simuliertes Netz)')
        log.resolutions.append((h, ip))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port or 80))]

    def cc(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, **kw):
        host, port = address
        ip = host
        try:
            socket.inet_aton(host)
        except OSError:
            ip = gai(host, port)[0][4][0]
        if ip == '127.0.0.1' and port == server.port:
            log.connects.append((ip, port, True))
            return real_cc((ip, port), timeout, source_address)
        if ip == FAKE_PUBLIC_IP:
            log.connects.append((ip, port, True))
            return real_cc(('127.0.0.1', server.port), timeout, source_address)
        log.connects.append((ip, port, False))
        log.unvalidated.append((ip, port))
        raise ConnectionRefusedError(f'simuliertes Netz: Verbindung zu {ip} verweigert')

    socket.getaddrinfo, socket.create_connection = gai, cc
    try:
        yield log
    finally:
        socket.getaddrinfo, socket.create_connection = real_gai, real_cc


def add_rebind_site(server):
    """Ergänzt rebind.example zur Laufzeit (kein eigener Datei-Eintrag nötig)."""
    server.manifest['sites']['rebind.example'] = {
        'pages': {'/': 'mueller-metall.example__index.html'}, 'robots': 'User-agent: *\nAllow: /\n', 'routes': {},
        'expect': {'blocked': 'rebind'}, 'note': 'DNS-Rebinding: 2. Auflösung zeigt auf 10.0.0.2'}
