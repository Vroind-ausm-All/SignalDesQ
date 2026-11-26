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
        from .base import FetchError
        raise FetchError(netpolicy.MESSAGE.format(what='der Website-Abruf'), kind='offline')
    from .. import sources
    try:
        sources.check_url(url)  # R1.1: Source Registry vor jedem Website-Abruf
    except sources.SourceBlocked as exc:
        from .base import FetchError
        raise FetchError(str(exc), kind='source') from exc
    from urllib.parse import urlsplit

    from .. import budget
    b = budget.current()  # R1.4: Seiten-, Zeit-, Byte- und Hostbudget des laufenden Auftragsschritts
    if b is not None:
        b.before(urlsplit(url).hostname)
    res = get_fetcher(fetcher).fetch(url, policy or pol.DEFAULT_POLICY, origin)
    if b is not None:
        b.after(len(res.body or b''))
    return res
