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
    except (socket.gaierror, UnicodeError) as exc:
        raise CrawlError('Domain konnte nicht aufgelöst werden.') from exc
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
        raise CrawlError('Domain konnte nicht aufgelöst werden.')
    return ips


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
