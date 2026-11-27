"""Bedingte Abrufe mit ETag/Last-Modified (R1.4, 2.0.0-dev71).

Hat eine Seite beim letzten Abruf ``ETag`` oder ``Last-Modified`` gesendet, fragt der nächste Abruf mit ``If-None-Match`` bzw.
``If-Modified-Since`` nach. Antwortet der Server mit 304 („unverändert“), wird die zuletzt gelesene Fassung wiederverwendet:
weniger Bytes, gleicher Inhalt, gleicher Inhalts-Hash für Belege.

- Nur im Speicher und je Organisation getrennt (``tenancy.current()``), nie in der Datenbank oder im Export.
- Gespeichert werden nur öffentlich abgerufene Seiten mit HTTP 200 ohne Weiterleitung, die ein Prüfmerkmal tragen.
- Höchstalter MAX_AGE: danach wird ohne Bedingung neu abgerufen. Grenzen je Organisation: MAX_ENTRIES Seiten, MAX_BYTES.
- Die Zwischenablage ersetzt keine Prüfung: Offline-Schalter, Source Registry, robots.txt, IP-Pinning und Budgets gelten
  vor jedem Abruf genauso; ein Inhalt kommt nur nach einer echten 304-Antwort des Servers aus dem Speicher.
"""
from __future__ import annotations

import collections
import dataclasses
import threading
import time

MAX_AGE = 24 * 3600
MAX_ENTRIES = 200
MAX_BYTES = 30_000_000
CLOCK = time.monotonic
_LOCK = threading.Lock()
_STORE: dict = {}  # Organisation → OrderedDict(url → (zeit, FetchResult))


def _key(key=None):
    from .. import tenancy
    return key or tenancy.current() or ''


def lookup(url, key=None):
    """Frühere Fassung (FetchResult) oder None; abgelaufene Einträge werden entfernt."""
    with _LOCK:
        store = _STORE.get(_key(key))
        if not store or url not in store:
            return None
        at, res = store[url]
        if CLOCK() - at > MAX_AGE:
            del store[url]
            return None
        store.move_to_end(url)
        return res


def conditional(url, key=None):
    res = lookup(url, key)
    if res is None:
        return None
    return {'etag': res.etag, 'last_modified': res.last_modified}


def remember(res, key=None):
    if res.status != 200 or res.redirects or res.final_url != res.source_url or not (res.etag or res.last_modified):
        return
    if len(res.body or b'') > MAX_BYTES // 4:
        return
    with _LOCK:
        store = _STORE.setdefault(_key(key), collections.OrderedDict())
        store[res.source_url] = (CLOCK(), res)
        store.move_to_end(res.source_url)
        total = sum(len(r.body or b'') for _, r in store.values())
        while store and (len(store) > MAX_ENTRIES or total > MAX_BYTES):
            _, (_, old) = store.popitem(last=False)
            total -= len(old.body or b'')


def revalidated(old, fresh):
    """Ergebnis nach HTTP 304: Inhalt der früheren Fassung, Zeit und Abrufdaten der neuen Antwort."""
    return dataclasses.replace(old, fetched_at=fresh.fetched_at, peer_ip=fresh.peer_ip or old.peer_ip, elapsed_ms=fresh.elapsed_ms,
                               robots=fresh.robots, etag=fresh.etag or old.etag, last_modified=fresh.last_modified or old.last_modified,
                               revalidated=True, warnings=list(old.warnings) + ['unverändert seit dem letzten Abruf (HTTP 304)'])


def clear(key=None):
    with _LOCK:
        if key is None:
            _STORE.clear()
        else:
            _STORE.pop(key, None)


def stats(key=None):
    with _LOCK:
        store = _STORE.get(_key(key)) or {}
        return {'pages': len(store), 'bytes': sum(len(r.body or b'') for _, r in store.values())}
