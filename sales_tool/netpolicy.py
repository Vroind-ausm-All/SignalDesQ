"""Offline-Modus (Masterplan 2.0, Sprint 6 – SignalDesk v1.19).

Ein Schalter für „keine Abrufe aus dem Internet“: CRM, Angebote, Buchhaltung, Sichtung, Katalog-Suche und Sicherungen
funktionieren weiter; Firmensuche-Quellen, Website-Abrufe, Impressum und Browser-Prüfung sind aus. Aufträge, die das Netz
brauchen, warten (statt fehlzuschlagen) und laufen nach dem Ausschalten weiter. Die lokale KI (Ollama auf 127.0.0.1)
bleibt erlaubt.

Einschalten: unter „Einstellungen → Sicherung & Zugang“ (dauerhaft) oder beim Start mit `--offline` (nur für diese Sitzung).
"""
from __future__ import annotations

from . import tenancy

SETTING = 'offline_mode'
# 'forced' (Start mit --offline) gilt für die ganze Installation. Der gespeicherte Schalter gehört der Organisation
# (SDQ-012): _BY_DB hält ihn je Datenbank; 'stored' ist der zuletzt geladene Wert und gilt nur, wo kein Mandant gesetzt ist
# (Einzelplatz, direkte Aufrufe in Tests).
STATE = {'stored': False, 'forced': False}
_BY_DB: dict[str, bool] = {}
# Auftragsarten, die Internet brauchen – im Offline-Modus werden sie nicht gestartet (bleiben in der Warteschlange)
NETWORK_KINDS = ('sweep_source', 'sweep_finish', 'website', 'report', 'lead_imprint')
MESSAGE = 'Offline-Modus ist eingeschaltet – {what} braucht Internet. Ausschalten unter „Einstellungen → Sicherung & Zugang“.'


def _stored(key=None):
    key = key or tenancy.current()
    return _BY_DB[key] if key in _BY_DB else STATE['stored']


def offline(key=None):
    return bool(STATE['forced'] or _stored(key))


def load(conn):
    from .quality import get_setting
    value = bool(get_setting(conn, SETTING, {'enabled': False}).get('enabled'))
    key = tenancy.conn_key(conn)
    _BY_DB[key] = STATE['stored'] = value
    return offline(key)


def set_offline(conn, enabled):
    from .quality import put_setting
    if not isinstance(enabled, bool):
        raise ValueError('enabled: true/false.')
    put_setting(conn, SETTING, {'enabled': enabled})
    conn.commit()
    key = tenancy.conn_key(conn)
    _BY_DB[key] = STATE['stored'] = enabled
    if not offline(key):
        from .research import jobs
        jobs.ensure_workers_all()
    return status(conn)


def status(conn=None):
    key = tenancy.conn_key(conn) if conn is not None else None
    off = offline(key)
    return {'offline': off, 'stored': _stored(key), 'forced': STATE['forced'],
            'notice': 'Offline: keine Abrufe aus dem Internet. Recherche-Aufträge warten, bis du wieder online gehst.' if off else ''}


class OfflineError(Exception):
    pass


def assert_online(what='dieser Abruf'):
    if offline():
        raise OfflineError(MESSAGE.format(what=what))


def route_netpolicy(h, conn, method, route):
    if route != '/api/system/offline':
        return False
    if method == 'GET':
        h._send(200, status(conn))
        return True
    if method == 'PUT':
        b = h._body()
        if set(b) != {'enabled'}:
            raise ValueError('Erwartet: {enabled: true/false}.')
        h._send(200, set_offline(conn, b['enabled']))
        return True
    return False
