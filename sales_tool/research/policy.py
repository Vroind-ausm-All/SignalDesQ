"""Abrufregeln (Sprint 1): Grenzen je Anfrage und robots.txt nach RFC 9309 – ohne Fremdpakete.

robots.txt (RFC 9309):
- 2xx: Regeln gelten; „*“ und „$“ werden unterstützt; der längste passende Pfad gewinnt, bei Gleichstand „Allow“.
- 4xx (Datei „nicht verfügbar“): Abruf erlaubt. Ausnahme 429: wir behandeln „zu viele Anfragen“ vorsichtig als gesperrt.
- 5xx oder nicht erreichbar: vollständig gesperrt.
- Weiterleitungen werden gefolgt (bis 5), nur innerhalb derselben Firma und mit Sicherheitsprüfung je Schritt.
- Ergebnis je Website (Schema + Host + Port) eine Stunde im Speicher – nicht mehr vor jeder Seite neu laden.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

AGENT = 'SignalDeskResearch/1.17 (+public company data research; single pages, no bulk crawling)'  # nur ASCII in Kopfzeilen
AGENT_TOKEN = 'signaldeskresearch'

HTML_TYPES = ('text/html', 'application/xhtml+xml')
ALLOWED_TYPES = HTML_TYPES + ('application/pdf', 'text/plain', 'application/xml', 'text/xml', 'application/rss+xml',
                              'application/atom+xml', 'application/json', 'application/ld+json', 'application/feed+json')


@dataclass(frozen=True)
class FetchPolicy:
    """Startwerte nach Masterplan 2.0 (konfigurierbar, im Benchmark überprüft)."""
    user_agent: str = AGENT
    timeout: float = 10.0            # Sekunden je Verbindungsschritt (Plan: 10 s/Request)
    total_timeout: float = 25.0      # Gesamtbudget je Abruf inkl. Weiterleitungen
    max_redirects: int = 5
    max_html: int = 2_000_000
    max_pdf: int = 5_000_000
    max_robots: int = 500_000        # RFC 9309: mindestens 500 KiB auswerten
    max_decoded: int = 4_000_000     # Grenze nach dem Entpacken (gzip-Bomben)
    allowed_types: tuple = ALLOWED_TYPES
    ports: tuple = (80, 443)
    same_site_redirects: bool = True
    respect_robots: bool = True
    robots_ttl: float = 3600.0
    extra: dict = field(default_factory=dict)


DEFAULT_POLICY = FetchPolicy()


# ---------------------------------------------------------------- robots.txt (RFC 9309)

def _pattern(path):
    """RFC 9309 Pfadmuster → Regex. „*“ beliebig, „$“ am Ende verankert."""
    anchored = path.endswith('$')
    core = path[:-1] if anchored else path
    rx = ''.join('.*' if ch == '*' else re.escape(ch) for ch in core)
    return re.compile(rx + ('$' if anchored else ''))


class RobotsRules:
    def __init__(self, allow_all=False, disallow_all=False, rules=None, reason=''):
        self.allow_all, self.disallow_all, self.rules, self.reason = allow_all, disallow_all, rules or [], reason

    @classmethod
    def parse(cls, text, agent_token=AGENT_TOKEN):
        groups, current, seen_rule = [], None, False
        for raw in text.splitlines():
            line = raw.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            key, value = (x.strip() for x in line.split(':', 1))
            key = key.lower()
            if key == 'user-agent':
                if current is None or seen_rule:
                    current = {'agents': [], 'rules': []}
                    groups.append(current)
                    seen_rule = False
                current['agents'].append(value.lower())
            elif key in ('allow', 'disallow') and current is not None:
                seen_rule = True
                if value or key == 'allow':
                    current['rules'].append((key == 'allow', value))
        mine = [g for g in groups if any(a != '*' and a in agent_token for a in g['agents'])]
        chosen = mine or [g for g in groups if '*' in g['agents']]
        rules = [(allow, path) for g in chosen for allow, path in g['rules'] if path]
        return cls(rules=[(allow, path, _pattern(path)) for allow, path in rules], reason='robots.txt')

    def allowed(self, url):
        if self.allow_all:
            return True
        if self.disallow_all:
            return False
        p = urlsplit(url)
        target = unquote(p.path or '/') + (f'?{p.query}' if p.query else '')
        if target == '/robots.txt':
            return True
        best = None  # (Länge, allow)
        for allow, path, rx in self.rules:
            if rx.match(target):
                length = len(path.rstrip('$'))
                if best is None or length > best[0] or (length == best[0] and allow):
                    best = (length, allow)
        return True if best is None else best[1]


class RobotsCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    @staticmethod
    def key(url):
        p = urlsplit(url)
        return f'{p.scheme}://{(p.hostname or "").lower()}:{p.port or (443 if p.scheme == "https" else 80)}'

    def get(self, url, ttl):
        with self._lock:
            hit = self._data.get(self.key(url))
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
        return None

    def put(self, url, rules):
        with self._lock:
            self._data[self.key(url)] = (time.monotonic(), rules)

    def clear(self):
        with self._lock:
            self._data.clear()


ROBOTS = RobotsCache()


def rules_from_response(status, body):
    """Abbildung des Abrufergebnisses auf Regeln nach RFC 9309."""
    if status is None:
        return RobotsRules(disallow_all=True, reason='robots.txt nicht erreichbar – vorsorglich gesperrt (RFC 9309)')
    if 200 <= status < 300:
        return RobotsRules.parse(body.decode('utf-8', 'replace'))
    if status == 429:
        return RobotsRules(disallow_all=True, reason='robots.txt: zu viele Anfragen (HTTP 429) – vorsorglich gesperrt')
    if 400 <= status < 500:
        return RobotsRules(allow_all=True, reason=f'robots.txt nicht vorhanden (HTTP {status}) – Abruf erlaubt (RFC 9309)')
    return RobotsRules(disallow_all=True, reason=f'robots.txt-Server-Fehler (HTTP {status}) – vorsorglich gesperrt (RFC 9309)')
