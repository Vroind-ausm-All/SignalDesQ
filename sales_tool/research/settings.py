"""Schalter für die Recherche-Technik (Feature-Flags, in app_settings gespeichert).

- fetcher: 'http' (neu, IP-Pinning, Standard) oder 'legacy' (Abruf bis v1.14 – nur für Vergleich/Rückfall)
- parser: 'stdlib' (Standard – im Sprint-1-Benchmark gleiche Ergebnisse, 2,4× schneller), 'auto' (Scrapling, falls installiert) oder 'scrapling'
- browser_fallback: Seiten ohne statischen Text zusätzlich mit dem Browser (Playwright, JavaScript aus) lesen – nur wenn installiert
- content: Haupttext-Leser 'stdlib' (Standard) oder 'trafilatura' (optional, requirements-research.txt)
"""
from __future__ import annotations

import threading

DEFAULTS = {'fetcher': 'http', 'parser': 'stdlib', 'browser_fallback': True, 'content': 'stdlib'}  # Messung S1: Scrapling ohne Vorteil, 2,4× langsamer
CHOICES = {'fetcher': ('http', 'legacy'), 'parser': ('auto', 'scrapling', 'stdlib'), 'browser_fallback': (True, False),
           'content': ('stdlib', 'trafilatura')}
KEY = 'research_settings'
_LOCK = threading.Lock()
_CURRENT = dict(DEFAULTS)


def get():
    with _LOCK:
        return dict(_CURRENT)


def set_runtime(values):
    with _LOCK:
        _CURRENT.update(values)


def reset():
    with _LOCK:
        _CURRENT.clear()
        _CURRENT.update(DEFAULTS)


def validate(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('Erlaubt: ' + ', '.join(DEFAULTS) + '.')
    for k, v in data.items():
        if v not in CHOICES[k]:
            raise ValueError(f'{k}: ' + ', '.join(map(str, CHOICES[k])) + '.')
    return data


def load(conn):
    from ..quality import get_setting
    values = get_setting(conn, KEY, dict(DEFAULTS))
    try:
        set_runtime({k: v for k, v in validate({k: values[k] for k in DEFAULTS if k in values}).items()})
    except ValueError:
        reset()
    return get()


def save(conn, data):
    from ..quality import put_setting
    validate(data)
    merged = {**get(), **data}
    put_setting(conn, KEY, merged)
    conn.commit()
    set_runtime(merged)
    return merged


def status():
    """Selbstauskunft für die Oberfläche: Schalter + installierte Zusätze."""
    from .extractors.content import trafilatura_available
    from .fetchers import browser
    from .parse import engine, scrapling_available
    version = ''
    if scrapling_available():
        try:
            import scrapling
            version = scrapling.__version__
        except Exception:  # noqa: BLE001
            version = '?'
    return {'settings': get(), 'parser_in_use': engine(), 'scrapling': {'installed': bool(version), 'version': version},
            'browser': {'installed': browser.available()}, 'trafilatura': {'installed': trafilatura_available()},
            'notice': 'Abruf immer mit IP-Pinning, robots.txt (RFC 9309) und Größenbremsen. Scrapling dient nur der HTML-Auswertung; '
                      'sein eigener Abruf ist nicht eingebaut (Tarnung als Chrome und Google-Referer als Voreinstellung, kein IP-Pinning).'}


def route_research(h, conn, method, route, query):
    from .service_profile import route as route_service_profile
    if route_service_profile(h, conn, method, route):
        return True
    if route != '/api/research/settings':
        return False
    if method == 'GET':
        h._send(200, status())
        return True
    if method == 'POST':
        save(conn, h._body())
        h._send(200, status())
        return True
    return False
