"""URL- und Adressprüfung (Sprint 1). Grundlage für das IP-Pinning im HTTP-Abruf.

- Nur http/https, keine Zugangsdaten in der URL, keine Fragmente, nur Ports 80/443.
- Keine IP-Literale, keine lokalen/internen Namen (localhost, .local, .internal, .test, ohne Punkt).
- Jede aufgelöste Adresse muss global routbar sein (IPv4/IPv6); sonst wird abgelehnt.
- ``resolve_public`` liefert die geprüften Adressen. Der Abruf verbindet sich genau mit einer davon (Pinning) –
  es gibt keine zweite DNS-Auflösung, die auf ein internes Ziel umgebogen werden könnte (DNS-Rebinding).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from ..website_analyzer import CrawlError


class UnsafeURL(CrawlError):
    kind = 'ssrf'


class DomainMissing(CrawlError):
    """Der Name hat keinen DNS-Eintrag (NXDOMAIN/NODATA). Für die Website-Suche heißt das: Diese Domain gibt es nicht –
    kein Abruffehler. Nur sicher, wenn die Namensauflösung grundsätzlich funktioniert (siehe ``dns_available``)."""
    kind = 'dns_missing'


class DnsUnavailable(CrawlError):
    """Namensauflösung vorübergehend gestört (Zeitüberschreitung, Server nicht erreichbar) – ein echter Abruffehler."""
    kind = 'dns'


# „Name unbekannt“ bzw. „keine Adresse“ – unter Linux/macOS als EAI_*, unter Windows als WSAHOST_NOT_FOUND/WSANO_DATA
_NO_NAME = {c for c in (getattr(socket, 'EAI_NONAME', None), getattr(socket, 'EAI_NODATA', None), 11001, 11004) if c is not None}
_DNS_PROBE = ('denic.de', 'example.com')
_DNS_STATE = {'at': -1e9, 'ok': True}


def check_url(url, ports=(80, 443)):
    """Syntaktische Prüfung ohne DNS. Gibt die normalisierte URL zurück."""
    if not isinstance(url, str) or len(url) > 2048:
        raise UnsafeURL('Ungültige URL.')
    url = url.strip()
    p = urlsplit(url)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.fragment
            or p.port not in (None, *ports)):
        raise UnsafeURL('Nur öffentliche HTTP(S)-Websites ohne Login, Fragment oder Sonderport erlaubt.')
    host = p.hostname.rstrip('.').lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.test', '.lan', '.home.arpa')):
        raise UnsafeURL('Lokale und interne Hostnamen sind gesperrt.')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host:
            raise UnsafeURL('Bitte einen öffentlichen Domainnamen verwenden.')
    else:
        raise UnsafeURL('IP-Adressen sind als Ziel gesperrt.')
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or '/', p.query, ''))


def resolve_public(host, port):
    """Löst den Namen EINMAL auf und prüft jede Adresse. Gibt die geprüften Adressen (Reihenfolge des Resolvers) zurück."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except UnicodeError as exc:  # kein gültiger Domainname – kann es nicht geben
        raise DomainMissing('Ungültiger Domainname.') from exc
    except socket.gaierror as exc:
        if exc.errno in _NO_NAME:
            raise DomainMissing('Domain existiert nicht (kein DNS-Eintrag).') from exc
        raise DnsUnavailable('Domain konnte nicht aufgelöst werden (Namensauflösung gestört).') from exc
    ips = []
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip.split('%')[0])
        except ValueError as exc:
            raise UnsafeURL('Ungültige Adresse vom Namensdienst.') from exc
        if not addr.is_global or addr.is_multicast:
            raise UnsafeURL('Interne, private oder nicht öffentliche IP-Adresse erkannt.')
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise DomainMissing('Domain hat keine Adresse.')
    return ips


def dns_available(max_age=300):
    """Funktioniert die Namensauflösung überhaupt? Ohne DNS (z. B. Firmennetz nur mit Proxy) meldet jeder Name „unbekannt“ –
    dann darf „Domain existiert nicht“ nicht als Ergebnis gelten. Fragt zwei bekannte Namen ab (keine Firmendaten), 5 Minuten gemerkt."""
    import time
    now = time.monotonic()
    if now - _DNS_STATE['at'] < max_age:
        return _DNS_STATE['ok']
    ok = False
    for host in _DNS_PROBE:
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            ok = True
            break
        except (OSError, UnicodeError):
            continue
    _DNS_STATE.update(at=now, ok=ok)
    return ok


def public_url(url):
    """Kompatibel zu website_analyzer.public_url: Syntax + DNS-Prüfung."""
    norm = check_url(url)
    p = urlsplit(norm)
    resolve_public(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
    return norm


def site_key(url):
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    return host[4:] if host.startswith('www.') else host


def same_site(a, b):
    """Dieselbe Firma: gleicher Host ohne „www.“ (wie bisher same_company_host)."""
    return site_key(a) == site_key(b)
