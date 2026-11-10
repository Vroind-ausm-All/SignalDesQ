"""Offline-Modus (Masterplan 2.0, Sprint 6 – SignalDesk v1.19).

Ein Schalter für „keine Abrufe aus dem Internet“: CRM, Angebote, Buchhaltung, Sichtung, Katalog-Suche und Sicherungen
funktionieren weiter; Firmensuche-Quellen, Website-Abrufe, Impressum und Browser-Prüfung sind aus. Aufträge, die das Netz
brauchen, warten (statt fehlzuschlagen) und laufen nach dem Ausschalten weiter. Die lokale KI (Ollama auf 127.0.0.1)
bleibt erlaubt.

Einschalten: in „Datenqualität & System“ (dauerhaft) oder beim Start mit `--offline` (nur für diese Sitzung).
"""
from __future__ import annotations

SETTING = 'offline_mode'
STATE = {'stored': False, 'forced': False}
# Auftragsarten, die Internet brauchen – im Offline-Modus werden sie nicht gestartet (bleiben in der Warteschlange)
NETWORK_KINDS = ('sweep_source', 'sweep_finish', 'website', 'report', 'lead_imprint')
MESSAGE = 'Offline-Modus ist eingeschaltet – {what} braucht Internet. Ausschalten unter „Datenqualität & System“.'


def offline():
    return bool(STATE['stored'] or STATE['forced'])


def load(conn):
    from .quality import get_setting
    STATE['stored'] = bool(get_setting(conn, SETTING, {'enabled': False}).get('enabled'))
    return offline()


def set_offline(conn, enabled):
    from .quality import put_setting
    if not isinstance(enabled, bool):
        raise ValueError('enabled: true/false.')
    put_setting(conn, SETTING, {'enabled': enabled})
    conn.commit()
    STATE['stored'] = enabled
    if not offline():
        from .research import jobs
        jobs.ensure_workers_all()
    return status()


def status():
    return {'offline': offline(), 'stored': STATE['stored'], 'forced': STATE['forced'],
            'notice': 'Offline: keine Abrufe aus dem Internet. Recherche-Aufträge warten, bis du wieder online gehst.' if offline() else ''}


class OfflineError(Exception):
    pass


def assert_online(what='dieser Abruf'):
    if offline():
        raise OfflineError(MESSAGE.format(what=what))


def route_netpolicy(h, conn, method, route):
    if route != '/api/system/offline':
        return False
    if method == 'GET':
        h._send(200, status())
        return True
    if method == 'PUT':
        b = h._body()
        if set(b) != {'enabled'}:
            raise ValueError('Erwartet: {enabled: true/false}.')
        h._send(200, set_offline(conn, b['enabled']))
        return True
    return False
