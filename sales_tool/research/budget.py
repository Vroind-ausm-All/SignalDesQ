"""Recherchemodi und Jobbudgets (R1.4, 2.0.0-dev69; Tagesbudget je Organisation 2.0.0-dev71).

Ein Budget gilt für einen Auftragsschritt (eine Firma, eine Quelle) und begrenzt alle Website-Abrufe darin:
Seiten, Zeit, Bytes und verschiedene Hosts. Modi nach Plan: Quick 10, Deep 30, Org 50 Seiten als Obergrenze.

- Gezählt wird in ``research.fetchers.fetch`` – dem einzigen Weg für Website-Abrufe. Ist das Budget aufgebraucht, wirft der
  Abruf ``FetchError(kind='budget')``; was bis dahin gelesen wurde, bleibt als Teilergebnis erhalten.
- Ein aufgebrauchtes Budget wird nie wiederholt: Der Auftrag beendet den Schritt statt einen neuen Versuch einzuplanen
  (``research.jobs``), sonst liefe er mit frischem Budget endlos weiter.
- Ohne gesetztes Budget (direkte Aufrufe, Tests) gilt keine zusätzliche Grenze; die Grenzen je Abruf (Größe, Zeit) gelten immer.
"""
from __future__ import annotations

import contextlib
import contextvars
import threading
import time
from dataclasses import dataclass, field

MODES = {
    'quick': {'label': 'Quick', 'max_pages': 10, 'max_seconds': 180, 'max_bytes': 20_000_000, 'max_hosts': 10},
    'deep': {'label': 'Deep', 'max_pages': 30, 'max_seconds': 600, 'max_bytes': 60_000_000, 'max_hosts': 20},
    'org': {'label': 'Org', 'max_pages': 50, 'max_seconds': 900, 'max_bytes': 100_000_000, 'max_hosts': 30},
}
# Hosts: die Website-Suche prüft mehrere Kandidaten-Domains (verschiedene Hosts) – die Grenze muss das zulassen.
# Zeit: höchstens so lang wie die Reservierung eines Schritts (jobs.LEASE_SECONDS = 900 s).
DEFAULT_MODE = 'deep'  # bisheriges Verhalten bleibt innerhalb dieser Grenzen (Firmen-Bericht: höchstens etwa 20 Seiten)
CLOCK = time.monotonic  # in Tests ersetzbar

_CURRENT: contextvars.ContextVar = contextvars.ContextVar('research_budget', default=None)


@dataclass
class Budget:
    mode: str = DEFAULT_MODE
    max_pages: int = 30
    max_seconds: float = 600
    max_bytes: int = 60_000_000
    max_hosts: int = 20
    pages: int = 0
    bytes: int = 0
    hosts: set = field(default_factory=set)
    started: float = field(default_factory=lambda: CLOCK())
    exhausted: str = ''
    daily_refused: bool = False  # ein Abruf scheiterte am Tagesbudget der Organisation
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def for_mode(cls, mode=None):
        mode = mode if mode in MODES else DEFAULT_MODE
        spec = {k: v for k, v in MODES[mode].items() if k != 'label'}
        return cls(mode=mode, **spec)

    def _stop(self, reason):
        self.exhausted = self.exhausted or reason
        from .fetchers.base import FetchError
        raise FetchError(f'Budget „{MODES[self.mode]["label"]}“ erreicht: {reason} – Teilergebnis.', kind='budget')

    def before(self, host):
        """Vor einem Abruf: Seiten-, Zeit- und Hostgrenze prüfen und die Seite verbuchen."""
        host = (host or '').lower()
        with self._lock:
            if self.exhausted:
                self._stop(self.exhausted)
            if CLOCK() - self.started > self.max_seconds:
                self._stop(f'mehr als {int(self.max_seconds)} s')
            if self.pages >= self.max_pages:
                self._stop(f'{self.max_pages} Seiten')
            if host and host not in self.hosts and len(self.hosts) >= self.max_hosts:
                self._stop(f'{self.max_hosts} verschiedene Hosts')
            self.pages += 1
            if host:
                self.hosts.add(host)

    def after(self, nbytes):
        with self._lock:
            self.bytes += int(nbytes or 0)
            if self.bytes > self.max_bytes and not self.exhausted:
                self.exhausted = f'mehr als {self.max_bytes // 1_000_000} MB'

    def summary(self):
        return {'mode': self.mode, 'pages': self.pages, 'max_pages': self.max_pages, 'bytes': self.bytes, 'hosts': len(self.hosts),
                'seconds': round(CLOCK() - self.started, 1), 'exhausted': self.exhausted, 'daily_refused': self.daily_refused}


def current():
    return _CURRENT.get()


@contextlib.contextmanager
def use(budget):
    token = _CURRENT.set(budget)
    try:
        yield budget
    finally:
        _CURRENT.reset(token)


def validate_mode(value):
    if value in (None, ''):
        return DEFAULT_MODE
    if value not in MODES:
        raise ValueError('mode: ' + ', '.join(MODES) + '.')
    return value


def modes():
    return {k: {kk: vv for kk, vv in v.items()} for k, v in MODES.items()}


# ---------------------------------------------------------------- Tagesbudget je Organisation (Mandantenbudget, R1.4)
#
# Zusätzlich zum Budget je Auftragsschritt begrenzt ein Tagesbudget alle Website-Abrufe einer Organisation – auch die, die
# nicht als Auftrag laufen (Firmen-Bericht aus der Oberfläche). Es gilt je Datenbank (Mandant) und Kalendertag:
# - Grenze: Einstellung ``daily_pages`` der Recherche (0 = keine Grenze; im Server für mehrere Organisationen Pflicht,
#   siehe hosting.LIMITS). Bytegrenze = Seiten × DAILY_BYTES_PER_PAGE.
# - Gezählt wird im Speicher je Organisation (``tenancy.current()``); der Stand wird am Ende jedes Auftragsschritts und beim
#   Speichern der Einstellungen in app_settings (``research_usage``) festgehalten und nach einem Neustart von dort gelesen.
# - Ist das Tagesbudget aufgebraucht, wirft der Abruf ``FetchError(kind='budget')``; wartende Aufträge mit Internetbedarf
#   werden bis zum nächsten Tag nicht gestartet (research.jobs.claim), ein unterbrochener Schritt wird auf morgen verschoben.

USAGE_KEY = 'research_usage'
DAILY_BYTES_PER_PAGE = 1_000_000
TODAY = lambda: __import__('datetime').date.today().isoformat()  # noqa: E731 – in Tests ersetzbar
_USAGE: dict = {}
_USAGE_LOCK = threading.Lock()


class DailyExhausted(Exception):
    pass


def _daily_limit(key):
    from . import settings
    try:
        return int(settings.get(key).get('daily_pages') or 0)
    except (TypeError, ValueError):
        return 0


def _stored_usage(key):
    """Gespeicherten Stand einer Organisation lesen (nur lesend, kurze Wartezeit; Fehler = kein Stand)."""
    import sqlite3
    if not key or key.startswith(':memory:'):
        return {}
    try:
        from pathlib import Path
        con = sqlite3.connect(Path(key).as_uri() + '?mode=ro', uri=True, timeout=1)
        try:
            row = con.execute('SELECT value_json FROM app_settings WHERE key=?', (USAGE_KEY,)).fetchone()
        finally:
            con.close()
        import json
        value = json.loads(row[0]) if row else {}
        return value if isinstance(value, dict) else {}
    except Exception:  # noqa: BLE001 – ohne lesbaren Stand beginnt der Tag bei 0
        return {}


def _entry(key):
    """Zähler der Organisation für heute (unter _USAGE_LOCK aufrufen)."""
    today = TODAY()
    e = _USAGE.get(key)
    if e is None:
        stored = _stored_usage(key)
        e = {'day': stored.get('day', ''), 'pages': int(stored.get('pages') or 0), 'bytes': int(stored.get('bytes') or 0)}
        _USAGE[key] = e
    if e['day'] != today:
        e.update(day=today, pages=0, bytes=0)
    return e


def _tenant_key(key=None):
    from .. import tenancy
    return key or tenancy.current() or ''


def daily_before(key=None):
    """Vor einem Abruf: Tagesbudget der Organisation prüfen und die Seite verbuchen."""
    key = _tenant_key(key)
    limit = _daily_limit(key or None)
    with _USAGE_LOCK:
        e = _entry(key)
        if limit and (e['pages'] >= limit or e['bytes'] > limit * DAILY_BYTES_PER_PAGE):
            from .fetchers.base import FetchError
            raise FetchError(f'Tagesbudget der Organisation erreicht ({limit} Seiten bzw. {limit * DAILY_BYTES_PER_PAGE // 1_000_000} MB '
                             'je Tag) – weitere Abrufe ab morgen. Teilergebnis.', kind='budget')
        e['pages'] += 1


def daily_after(nbytes, key=None):
    key = _tenant_key(key)
    with _USAGE_LOCK:
        _entry(key)['bytes'] += int(nbytes or 0)


def daily_exhausted(key=None):
    key = _tenant_key(key)
    limit = _daily_limit(key or None)
    if not limit:
        return False
    with _USAGE_LOCK:
        e = _entry(key)
        return e['pages'] >= limit or e['bytes'] > limit * DAILY_BYTES_PER_PAGE


def daily_usage(key=None):
    key = _tenant_key(key)
    limit = _daily_limit(key or None)
    with _USAGE_LOCK:
        e = dict(_entry(key))
    return {**e, 'max_pages': limit, 'max_bytes': limit * DAILY_BYTES_PER_PAGE,
            'exhausted': bool(limit) and (e['pages'] >= limit or e['bytes'] > limit * DAILY_BYTES_PER_PAGE)}


def save_usage(conn):
    """Stand der Organisation dieser Verbindung festhalten (ohne Commit – der Aufrufer schreibt ohnehin)."""
    from .. import tenancy
    from ..quality import put_setting
    key = tenancy.conn_key(conn)
    with _USAGE_LOCK:
        if key not in _USAGE:
            return
        e = dict(_entry(key))
    put_setting(conn, USAGE_KEY, e)


def seconds_until_tomorrow():
    import datetime as dt
    now = dt.datetime.now()
    return max(60, int((dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time()) - now).total_seconds()) + 60)


def reset_usage():  # Tests
    with _USAGE_LOCK:
        _USAGE.clear()
