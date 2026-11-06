"""Bisheriger Abruf (bis v1.14) als Adapter – nur für Vergleichsmessung und Rückfall per Schalter.

Bekannte Schwächen (im Sprint-0-Benchmark gemessen): zweite DNS-Auflösung beim Verbinden (DNS-Rebinding-Lücke),
robots.txt-Weiterleitungen werden abgelehnt, robots.txt-403 sperrt, kein Entpacken von gzip, robots.txt vor jeder Seite.
"""
from __future__ import annotations

import datetime as dt
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ... import website_analyzer as wa
from .. import policy as pol
from .base import FetchError, FetchResult

NAME = 'legacy'


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, origin):
        super().__init__()
        self.origin, self.count = origin, 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 4:
            raise FetchError('Zu viele Weiterleitungen.', 'redirect')
        target = wa.public_url(urljoin(req.full_url, newurl))
        if self.origin and not wa.same_company_host(self.origin, target):
            raise FetchError(f'Weiterleitung auf fremde Domain ({urlsplit(target).hostname}) – nicht gefolgt.', 'redirect')
        return super().redirect_request(req, fp, code, msg, headers, target)


def fetch(url, policy=pol.DEFAULT_POLICY, origin=None):
    started = time.monotonic()
    url = wa.public_url(url)
    if policy.respect_robots and not wa.legacy_robots_allowed(url):
        raise FetchError('robots.txt untersagt den Abruf dieser Seite.', 'robots')
    opener = build_opener(_SafeRedirect(origin))
    req = Request(url, headers={'User-Agent': policy.user_agent, 'Accept': 'text/html,application/xhtml+xml,application/pdf;q=0.8'})
    try:
        with opener.open(req, timeout=12) as resp:
            ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            limit = policy.max_pdf if ctype == 'application/pdf' else policy.max_html
            data = resp.read(limit + 1)
            if len(data) > limit:
                raise FetchError('Seite zu groß.', 'size')
            return FetchResult(source_url=url, final_url=resp.geturl(), status=resp.status, content_type=ctype, body=data,
                               fetched_at=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), fetcher=NAME,
                               elapsed_ms=int((time.monotonic() - started) * 1000))
    except HTTPError as exc:
        raise FetchError(f'HTTP {exc.code}', 'http', status=exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FetchError(f'Nicht erreichbar ({getattr(exc, "reason", exc)})', 'network') from exc
