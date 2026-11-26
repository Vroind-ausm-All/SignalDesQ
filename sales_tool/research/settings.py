"""Schalter für die Recherche-Technik (Feature-Flags, in app_settings gespeichert).

- fetcher: 'http' (neu, IP-Pinning, Standard) oder 'legacy' (Abruf bis v1.14 – nur für Vergleich/Rückfall)
- parser: 'stdlib' (Standard – im Sprint-1-Benchmark gleiche Ergebnisse, 2,4× schneller), 'auto' (Scrapling, falls installiert) oder 'scrapling'
- browser_fallback: Seiten ohne statischen Text zusätzlich mit dem Browser (Playwright, JavaScript aus) lesen – nur wenn installiert
- content: Haupttext-Leser 'stdlib' (Standard) oder 'trafilatura' (optional, requirements-research.txt)
- mode: Recherchemodus der Organisation (R1.4): 'quick', 'deep' (Standard) oder 'org' – Budget je Auftragsschritt
"""
from __future__ import annotations

import threading

DEFAULTS = {'fetcher': 'http', 'parser': 'stdlib', 'browser_fallback': True, 'content': 'stdlib', 'mode': 'deep'}  # Messung S1: Scrapling ohne Vorteil, 2,4× langsamer
CHOICES = {'fetcher': ('http', 'legacy'), 'parser': ('auto', 'scrapling', 'stdlib'), 'browser_fallback': (True, False),
           'content': ('stdlib', 'trafilatura'), 'mode': ('quick', 'deep', 'org')}  # mode: R1.4, Budget je Auftragsschritt
KEY = 'research_settings'
_LOCK = threading.Lock()
# SDQ-036 (Prüfbericht F04): Schalter je Organisation. _BY_DB hält sie je Datenbank (wie der Offline-Schalter); _CURRENT gilt
# nur, wo kein Mandant gesetzt ist (Einzelplatz, direkte Aufrufe in Tests).
_CURRENT = dict(DEFAULTS)
_BY_DB: dict[str, dict] = {}
# Betriebsgrenzen (F05): Für Organisationen im Server für mehrere Organisationen gelten hosting.LIMITS. Mandanten dürfen
# Einstellungen nur innerhalb dieser Grenzen wählen; ein gespeicherter Wert außerhalb wirkt nicht.


def _limits(key):
    from .. import hosting
    return hosting.LIMITS if hosting.hosted(key) else {}


def _clamp(values, key):
    lim = _limits(key)
    return {k: (v if k not in lim or v in lim[k] else lim[k][0]) for k, v in values.items()}


def get(key=None):
    from .. import tenancy
    key = key or tenancy.current()
    with _LOCK:
        values = dict(_BY_DB[key] if key in _BY_DB else _CURRENT)
    return _clamp(values, key)


def set_runtime(values, key=None):
    with _LOCK:
        if key:
            _BY_DB.setdefault(key, dict(DEFAULTS)).update(values)
        _CURRENT.update(values)


def reset():
    with _LOCK:
        _CURRENT.clear()
        _CURRENT.update(DEFAULTS)
        _BY_DB.clear()


def validate(data, key=None):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('Erlaubt: ' + ', '.join(DEFAULTS) + '.')
    lim = _limits(key)
    for k, v in data.items():
        if v not in CHOICES[k]:
            raise ValueError(f'{k}: ' + ', '.join(map(str, CHOICES[k])) + '.')
        if k in lim and v not in lim[k]:
            raise PermissionError(f'{k}={v} ist im Server für mehrere Organisationen gesperrt.')
    return data


def load(conn):
    from .. import tenancy
    from ..quality import get_setting
    key = tenancy.conn_key(conn)
    values = get_setting(conn, KEY, dict(DEFAULTS))
    clean = {k: values[k] for k in DEFAULTS if k in values and values[k] in CHOICES[k]}
    with _LOCK:
        _BY_DB[key] = {**DEFAULTS, **clean}
        _CURRENT.clear()
        _CURRENT.update(_BY_DB[key])
    return get(key)


def save(conn, data):
    from .. import tenancy
    from ..quality import put_setting
    key = tenancy.conn_key(conn)
    validate(data, key)
    merged = {**DEFAULTS, **get_setting_safe(conn), **data}  # Ausgangspunkt ist der Eintrag dieser Datenbank, nie ein fremder
    put_setting(conn, KEY, merged)
    conn.commit()
    with _LOCK:
        _BY_DB[key] = dict(merged)
        _CURRENT.clear()
        _CURRENT.update(merged)
    return get(key)


def get_setting_safe(conn):
    from ..quality import get_setting
    values = get_setting(conn, KEY, {})
    return {k: values[k] for k in DEFAULTS if isinstance(values, dict) and k in values and values[k] in CHOICES[k]}


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
    from .budget import modes
    return {'settings': get(), 'modes': modes(), 'parser_in_use': engine(), 'scrapling': {'installed': bool(version), 'version': version},
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
