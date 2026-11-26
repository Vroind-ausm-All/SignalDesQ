"""Recherchemodi und Jobbudgets (R1.4, 2.0.0-dev69).

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
                'seconds': round(CLOCK() - self.started, 1), 'exhausted': self.exhausted}


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
