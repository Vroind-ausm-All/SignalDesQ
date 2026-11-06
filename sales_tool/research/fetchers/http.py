"""Sicherer HTTP-Abruf mit IP-Pinning (Sprint 1) – nur Standardbibliothek.

Je Schritt (auch nach jeder Weiterleitung):
1. URL prüfen (Schema, Port, keine Zugangsdaten, keine IP-Literale/internen Namen).
2. robots.txt der Website prüfen (RFC 9309, zwischengespeichert, Weiterleitungen geprüft).
3. Namen EINMAL auflösen, jede Adresse muss öffentlich sein → Verbindung genau zu dieser geprüften Adresse
   (TLS weiterhin mit Zertifikatsprüfung auf den Hostnamen). Keine zweite Auflösung = keine DNS-Rebinding-Lücke.
4. Weiterleitungen selbst auswerten: höchstens 5, nur dieselbe Firma, jede neu geprüft.
5. Grenzen: Inhaltstyp, Content-Length, gestreamtes Lesen mit Höchstgröße, Gesamtzeit, gzip/deflate nur mit
   Größenbremse (gzip-Bomben). Kein Tarnen, keine Proxys, keine Wiederholungsschleifen.
"""
from __future__ import annotations

import datetime as dt
import http.client
import socket
import ssl
import time
import zlib
from urllib.parse import urljoin, urlsplit

from .. import policy as pol
from ..safe_urls import check_url, resolve_public, same_site
from .base import FetchError, FetchResult

NAME = 'http'


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)  # Zertifikat gilt für den Namen, nicht die IP


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _single(url, policy, deadline, accept, limit_for):
    """Ein Abruf ohne Weiterleitung. Gibt (status, headers, body, ip) zurück."""
    p = urlsplit(url)
    port = p.port or (443 if p.scheme == 'https' else 80)
    ips = resolve_public(p.hostname, port)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchError('Zeitüberschreitung (Gesamtbudget aufgebraucht).', 'timeout')
    cls = _PinnedHTTPSConnection if p.scheme == 'https' else _PinnedHTTPConnection
    conn = cls(p.hostname, port, ips[0], min(policy.timeout, remaining))
    path = (p.path or '/') + (f'?{p.query}' if p.query else '')
    try:
        conn.request('GET', path, headers={'User-Agent': policy.user_agent, 'Accept': accept, 'Accept-Encoding': 'gzip, deflate',
                                           'Accept-Language': 'de,en;q=0.5', 'Connection': 'close'})
        resp = conn.getresponse()
        status, headers = resp.status, {k.lower(): v for k, v in resp.getheaders()}
        if 300 <= status < 400:
            return status, headers, b'', ips[0]
        ctype = (headers.get('content-type') or '').split(';')[0].strip().lower()
        limit = limit_for(ctype)
        declared = headers.get('content-length', '')
        if declared.isdigit() and int(declared) > limit:
            raise FetchError(f'Seite zu groß ({int(declared) // 1_000_000} MB angekündigt, erlaubt {limit // 1_000_000} MB).', 'size')
        chunks, size = [], 0
        while True:
            if time.monotonic() > deadline:
                raise FetchError('Zeitüberschreitung beim Lesen.', 'timeout')
            chunk = resp.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise FetchError('Seite zu groß.', 'size')
            chunks.append(chunk)
        return status, headers, b''.join(chunks), ips[0]
    except (socket.timeout, TimeoutError) as exc:
        raise FetchError('Zeitüberschreitung (keine Antwort).', 'timeout') from exc
    except ssl.SSLError as exc:
        raise FetchError(f'TLS-Fehler: {exc.reason or exc}', 'network') from exc
    except (http.client.HTTPException, ConnectionError, OSError) as exc:
        if isinstance(exc, FetchError):
            raise
        raise FetchError(f'Nicht erreichbar ({exc})', 'network') from exc
    finally:
        conn.close()


def _decode_content(body, encoding, policy):
    enc = (encoding or '').strip().lower()
    if enc in ('', 'identity'):
        return body
    if enc in ('gzip', 'x-gzip', 'deflate'):
        wbits = 16 + zlib.MAX_WBITS if 'gzip' in enc else zlib.MAX_WBITS
        d = zlib.decompressobj(wbits)
        try:
            out = d.decompress(body, policy.max_decoded + 1)
        except zlib.error:
            if enc == 'deflate':  # manche Server senden „deflate“ ohne zlib-Kopf
                d = zlib.decompressobj(-zlib.MAX_WBITS)
                out = d.decompress(body, policy.max_decoded + 1)
            else:
                raise FetchError('Ungültige gzip-Daten.', 'encoding')
        if len(out) > policy.max_decoded or d.unconsumed_tail:
            raise FetchError('Seite zu groß (entpackt über der Grenze – mögliche gzip-Bombe).', 'size')
        return out
    raise FetchError(f'Nicht unterstützte Kodierung „{enc}“.', 'encoding')


def robots_check(url, policy=pol.DEFAULT_POLICY):
    """True/False nach RFC 9309; Regeln je Website zwischengespeichert."""
    rules = pol.ROBOTS.get(url, policy.robots_ttl)
    if rules is None:
        p = urlsplit(url)
        robots_url = f'{p.scheme}://{p.netloc}/robots.txt'
        try:
            res = fetch(robots_url, policy=_robots_policy(policy), origin=robots_url)
            rules = pol.rules_from_response(res.status, res.body)
        except FetchError as exc:
            rules = pol.rules_from_response(exc.status, b'') if exc.status else pol.RobotsRules(
                disallow_all=True, reason=f'robots.txt nicht prüfbar ({exc}) – vorsorglich gesperrt (RFC 9309)')
        pol.ROBOTS.put(url, rules)
    return rules.allowed(url), rules.reason


def _robots_policy(policy):
    from dataclasses import replace
    return replace(policy, respect_robots=False, max_html=policy.max_robots, allowed_types=policy.allowed_types + ('',),
                   extra={**policy.extra, 'robots': True})


def fetch(url, policy=pol.DEFAULT_POLICY, origin=None):
    """Seite abrufen. ``origin``: Weiterleitungen nur innerhalb dieser Firma (Standard: Firma der Start-URL)."""
    started = time.monotonic()
    deadline = started + policy.total_timeout
    current = check_url(url, policy.ports)
    origin = origin or current
    redirects, robots_note = [], 'nicht geprüft'
    accept = 'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5'
    is_robots = policy.extra.get('robots')

    def limit_for(ctype):
        return policy.max_pdf if ctype == 'application/pdf' else policy.max_html

    for hop in range(policy.max_redirects + 1):
        if policy.same_site_redirects and not same_site(origin, current):
            raise FetchError(f'Weiterleitung auf fremde Domain ({urlsplit(current).hostname}) – nicht gefolgt.', 'redirect')
        if policy.respect_robots:
            ok, reason = robots_check(current, policy)
            if not ok:
                raise FetchError('robots.txt untersagt den Abruf dieser Seite.' + (f' ({reason})' if reason != 'robots.txt' else ''), 'robots')
            robots_note = 'erlaubt'
        status, headers, body, ip = _single(current, policy, deadline, accept, limit_for)
        if 300 <= status < 400 and status != 304:
            loc = headers.get('location')
            if not loc:
                raise FetchError(f'Weiterleitung (HTTP {status}) ohne Ziel.', 'redirect')
            if hop >= policy.max_redirects:
                raise FetchError('Zu viele Weiterleitungen.', 'redirect')
            target = check_url(urljoin(current, loc), policy.ports)
            if target in redirects or target == current:
                raise FetchError('Weiterleitungsschleife erkannt.', 'redirect')
            redirects.append(current)
            current = target
            continue
        if status >= 400:
            ra = headers.get('retry-after', '')
            raise FetchError(f'HTTP {status}', 'http', status=status, retry_after=int(ra) if ra.isdigit() else None)
        ctype_full = headers.get('content-type', '')
        ctype = ctype_full.split(';')[0].strip().lower()
        if not is_robots and ctype not in policy.allowed_types:
            if not ctype:
                ctype = 'text/html'  # ohne Angabe wie Browser als HTML behandeln, Inhalt wird später geprüft
            else:
                raise FetchError(f'Inhaltstyp „{ctype}“ wird nicht ausgewertet.', 'content_type')
        body = _decode_content(body, headers.get('content-encoding'), policy)
        charset = ''
        if 'charset=' in ctype_full.lower():
            charset = ctype_full.lower().split('charset=', 1)[1].split(';')[0].strip(' "\'')
        return FetchResult(source_url=url, final_url=current, status=status, content_type=ctype, body=body, fetched_at=_now(),
                           fetcher=NAME, charset=charset, redirects=redirects, robots=robots_note if not is_robots else 'robots.txt',
                           peer_ip=ip, elapsed_ms=int((time.monotonic() - started) * 1000))
    raise FetchError('Zu viele Weiterleitungen.', 'redirect')
