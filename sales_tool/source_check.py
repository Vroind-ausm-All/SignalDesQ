"""Quellen-Check (v1.14): prüft jede offene Quelle mit einer winzigen echten Anfrage – auf dem Rechner des Nutzers.

Ergebnis je Quelle: ok / überlastet (mit Wartezeit) / blockiert (Firewall/Proxy) / Feldänderung (Antwortformat passt nicht
mehr zum Adapter). Nichts wird gespeichert außer dem letzten Ergebnis im Speicher; keine Firmendaten, keine Kontaktaufnahme.
"""
import json
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import lead_finder as lf

MIN_INTERVAL = 60  # Sekunden zwischen zwei Prüfungen (Fair Use)
TIMEOUT = 20
_LAST = {'at': 0.0, 'result': None}
_LOCK = threading.Lock()


def _gleif(ua):
    q = {'filter[fulltext]': 'Stuttgart', 'filter[entity.legalAddress.country]': 'DE', 'filter[entity.status]': 'ACTIVE', 'page[size]': 1}
    d = lf.FETCH(lf.GLEIF_URL + urllib.parse.urlencode(q), ua, accept='application/vnd.api+json', timeout=TIMEOUT)
    rec = (d.get('data') or [{}])[0]
    ent = (rec.get('attributes') or {}).get('entity') or {}
    missing = [k for k, ok in (('legalName', ent.get('legalName')), ('legalAddress.city', (ent.get('legalAddress') or {}).get('city')),
                               ('legalForm.id', (ent.get('legalForm') or {}).get('id'))) if not ok]
    total = (d.get('meta') or {}).get('pagination', {}).get('total')
    return missing, f'{total} aktive Einträge für „Stuttgart“' if total is not None else ''


def _wikidata(ua):
    st = lf.wikidata_status()
    if st['blocked_s']:
        raise lf.SourceError(f'Wikidata hat um eine Pause gebeten (HTTP 429) – noch etwa {lf._fmt_wait(st["blocked_s"])}.', retry_after=st['blocked_s'])
    d = lf.wikidata_sparql('SELECT ?pop WHERE { wd:Q1022 wdt:P1082 ?pop }', ua, retries=0)
    rows = d.get('results', {}).get('bindings', [])
    note = 'gestört: höchstens 1 Anfrage pro Minute – SignalDesk taktet automatisch' if lf.wikidata_status()['slow'] else 'erreichbar'
    return ([] if rows else ['results.bindings']), note


def _nominatim(ua):
    d = lf.FETCH('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
        {'format': 'json', 'countrycodes': 'de', 'limit': 1, 'postalcode': '70173'}), ua, timeout=TIMEOUT)
    hit = d[0] if isinstance(d, list) and d else {}
    return ([] if hit.get('lat') and hit.get('lon') else ['lat/lon']), 'nur als Rückfall für unbekannte Orte (das Ortsverzeichnis liegt offline vor)'


def _overpass_server(server):
    def check(ua):
        d = lf.FETCH(server, ua, data=urllib.parse.urlencode({'data': '[out:json][timeout:10];node(1);out ids;'}).encode(),
                     content_type='application/x-www-form-urlencoded', timeout=TIMEOUT)
        return ([] if 'elements' in d else ['elements']), urllib.parse.urlsplit(server).hostname
    return check


def _ted(ua):
    body = {'query': 'classification-cpv IN (72413000) AND place-of-performance IN (DEU) AND publication-date>=20240101',
            'fields': ['publication-number', 'buyer-name', 'buyer-city', 'buyer-post-code'], 'page': 1, 'limit': 1,
            'scope': 'ALL', 'paginationMode': 'PAGE_NUMBER'}
    d = lf.FETCH('https://api.ted.europa.eu/v3/notices/search', ua, data=json.dumps(body).encode(), content_type='application/json', timeout=TIMEOUT)
    n = (d.get('notices') or [{}])[0]
    missing = [f for f in ('publication-number', 'buyer-name', 'buyer-city') if f not in n]
    return missing, f"{d.get('totalNoticeCount', '?')} Bekanntmachungen erreichbar"


CHECKS = [('gleif', 'GLEIF (Firmendaten)', _gleif), ('wikidata', 'Wikidata', _wikidata), ('nominatim', 'Nominatim (Ortssuche)', _nominatim)] + \
    [(f'osm{i + 1}', f'OpenStreetMap-Server {i + 1}', _overpass_server(s)) for i, s in enumerate(lf.OVERPASS_SERVERS)] + \
    [('ted', 'TED-Ausschreibungen', _ted)]


def _classify(exc):
    msg = str(exc)
    if 'HTTP 429' in msg or getattr(exc, 'retry_after', None):
        wait = getattr(exc, 'retry_after', None)
        return 'ueberlastet', msg, f'Wartet automatisch; nächster Versuch in etwa {lf._fmt_wait(wait)}.' if wait else 'Später erneut versuchen.'
    if re.search(r'HTTP 50[234]|capacity|überlastet|timed out|Zeitüberschreitung', msg, re.I):
        return 'ueberlastet', msg, 'Server gerade überlastet – SignalDesk wiederholt automatisch mit wachsender Pause.'
    if re.search(r'HTTP 40[13]|Forbidden|Tunnel|CERTIFICATE|SSL|nicht erreichbar|refused|reset', msg, re.I):
        return 'blockiert', msg, 'Verbindung kommt nicht zustande – Internetverbindung, Firewall, Proxy oder Virenscanner prüfen.'
    return 'fehler', msg, 'Unerwartete Antwort – bitte melden, eventuell hat die Quelle ihr Format geändert.'


def run_check(conn):
    with _LOCK:
        if _LAST['result'] and time.time() - _LAST['at'] < MIN_INTERVAL:
            return {**_LAST['result'], 'cached': True}
    ua = lf._user_agent(conn)

    def one(entry):
        key, label, fn = entry
        t = time.time()
        try:
            missing, note = fn(ua)
            status, detail, hint = ('ok', note, '') if not missing else (
                'format', f'Antwort ohne erwartete Felder: {", ".join(missing)}', 'Die Quelle hat ihr Antwortformat geändert – Adapter prüfen.')
        except (lf.SourceError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            status, detail, hint = _classify(exc)
        return {'key': key, 'label': label, 'status': status, 'ms': int((time.time() - t) * 1000), 'detail': str(detail)[:400], 'hint': hint}

    with ThreadPoolExecutor(max_workers=len(CHECKS)) as pool:
        rows = list(pool.map(one, CHECKS))
    osm = [r for r in rows if r['key'].startswith('osm')]
    summary = {
        'ok': sum(r['status'] == 'ok' for r in rows), 'total': len(rows),
        'osm_any': any(r['status'] == 'ok' for r in osm),
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'notice': 'Je Quelle eine winzige Testanfrage. Es werden keine Firmendaten gespeichert und niemand kontaktiert.',
    }
    result = {'rows': rows, **summary, 'cached': False}
    with _LOCK:
        _LAST.update(at=time.time(), result=result)
    return result


def route_source_check(h, conn, method, route, query):
    if route == '/api/sources/check' and method == 'POST':
        if h._body() != {'run': True}:  # löst echte Anfragen aus – nur auf ausdrücklichen Auftrag
            raise ValueError('Erwartet: {"run": true}.')
        h._send(200, run_check(conn))
        return True
    return False
