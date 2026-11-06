"""Gemeinsames Fetcher-Protokoll (Sprint 1): ``fetch(url, policy) -> FetchResult``."""
from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import asdict, dataclass, field

from ...website_analyzer import CrawlError


class FetchError(CrawlError):
    """Abruf gescheitert. ``kind``: robots, ssrf, redirect, size, timeout, http, content_type, network, encoding."""

    def __init__(self, message, kind='network', status=None, retry_after=None):
        super().__init__(message)
        self.kind, self.status, self.retry_after = kind, status, retry_after


@dataclass
class FetchResult:
    source_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: str
    fetcher: str
    charset: str = ''
    redirects: list = field(default_factory=list)
    robots: str = 'nicht geprüft'
    peer_ip: str = ''
    elapsed_ms: int = 0
    warnings: list = field(default_factory=list)

    @property
    def content_hash(self):
        return 'sha256:' + hashlib.sha256(self.body).hexdigest()

    def text(self):
        return decode_html(self.body, self.charset)

    def meta(self):
        """Datenvertrag „Normalisierte Seite“ (ohne Inhalt), z. B. für Protokolle und Belege."""
        d = asdict(self)
        d.pop('body')
        d['content_hash'] = self.content_hash
        d['bytes'] = len(self.body)
        return d


META_CHARSET = re.compile(rb'<meta[^>]+charset\s*=\s*["\']?\s*([A-Za-z0-9_\-:.]+)', re.I)


def _known(name):
    try:
        return codecs.lookup(name).name
    except (LookupError, TypeError):
        return ''


def decode_html(body, header_charset=''):
    """Reihenfolge: BOM → HTTP-Zeichensatz → <meta charset> → UTF-8 (streng) → Windows-1252.
    Behebt den Live-Fehler „ISO-8859-1 ohne Angabe“ (vorher erst nach Ersatzzeichen-Suche latin-1)."""
    if body.startswith(codecs.BOM_UTF8):
        return body[3:].decode('utf-8', 'replace')
    for enc in (_known(header_charset), _known((META_CHARSET.search(body[:4096]) or [None, b''])[1].decode('ascii', 'ignore'))):
        if enc:
            if enc in ('latin-1', 'iso8859-1', 'ascii'):
                enc = 'cp1252'  # Browser-Verhalten: ISO-8859-1 wird als Windows-1252 gelesen
            return body.decode(enc, 'replace')
    try:
        return body.decode('utf-8')
    except UnicodeDecodeError:
        return body.decode('cp1252', 'replace')
