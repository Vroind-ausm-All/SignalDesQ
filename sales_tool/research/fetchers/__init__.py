"""Fetcher-Auswahl per Schalter. Einheitliches Protokoll: fetch(url, policy, origin) -> FetchResult."""
from __future__ import annotations

from .. import policy as pol
from .. import settings
from .base import FetchError, FetchResult  # noqa: F401


def get_fetcher(name=None):
    name = name or settings.get()['fetcher']
    if name == 'legacy':
        from . import legacy
        return legacy
    from . import http
    return http


def fetch(url, policy=None, origin=None, fetcher=None):
    from ... import netpolicy
    if netpolicy.offline():
        raise FetchError(netpolicy.MESSAGE.format(what='der Website-Abruf'), kind='offline')
    from .. import sources
    try:
        sources.check_url(url)  # R1.1: Source Registry vor jedem Website-Abruf
    except sources.SourceBlocked as exc:
        raise FetchError(str(exc), kind='source') from exc
    from urllib.parse import urlsplit

    from .. import budget, pagecache
    b = budget.current()  # R1.4: Seiten-, Zeit-, Byte- und Hostbudget des laufenden Auftragsschritts
    if b is not None:
        b.before(urlsplit(url).hostname)
    try:
        budget.daily_before()  # R1.4: Tagesbudget der Organisation (Mandantenbudget)
    except FetchError:
        if b is not None:
            b.daily_refused = True
        raise
    policy = policy or pol.DEFAULT_POLICY
    previous = pagecache.lookup(url)  # R1.4: bedingter Abruf mit ETag/Last-Modified der letzten Fassung dieser Organisation
    extra = {k: v for k, v in policy.extra.items() if k != 'conditional'}
    if previous is not None:
        extra['conditional'] = {'etag': previous.etag, 'last_modified': previous.last_modified}
    if extra != policy.extra:
        from dataclasses import replace
        policy = replace(policy, extra=extra)
    res = get_fetcher(fetcher).fetch(url, policy, origin)
    nbytes = len(res.body or b'')  # übertragene Bytes: bei 304 keine
    if b is not None:
        b.after(nbytes)
    budget.daily_after(nbytes)
    if res.status == 304 and previous is not None:
        return pagecache.revalidated(previous, res)
    if res.status == 304:
        raise FetchError('HTTP 304 ohne frühere Fassung.', kind='http', status=304)
    pagecache.remember(res)
    return res
