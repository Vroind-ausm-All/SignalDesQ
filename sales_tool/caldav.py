"""Kalender-Abgleich über CalDAV (2.0.0-dev42, Produktreview M24 Stufe 2).

CalDAV ist der offene Standard, den Google, iCloud, mailbox.org, IONOS, Strato, Nextcloud und viele andere anbieten – eine
Umsetzung für alle. Abgleich in beide Richtungen, aber sparsam:
- **SignalDesk → Kalender:** geplante, bestätigte und abgesagte Termine werden als Ereignis angelegt bzw. aktualisiert
  (nur Titel, Firma, Zeit, Ort, Status – keine Notizen). Termine, die es in SignalDesk nicht mehr gibt, werden entfernt.
  Fremde Kalendereinträge fasst SignalDesk nie an.
- **Kalender → SignalDesk:** nur „belegt von … bis …“ der nächsten 60 Tage, ohne Titel oder Teilnehmer. Daraus entstehen
  Konfliktwarnungen beim Anlegen eines Termins und freie Vorschläge für Rückrufzeiten.
- **Aktualität:** Zeitpunkt des letzten Abgleichs ist sichtbar; älter als 24 Stunden → Hinweis.
- Nur HTTPS (außer zu Testzwecken auf diesem Rechner). Passwort nie in der Datenbank (credentials.py), App-Passwort empfohlen.
- Offline-Modus: kein Abgleich.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit

SETTING = 'caldav'
OWN_UID = re.compile(r'^meeting-\d+@signaldesk\.local$')
HORIZON_DAYS = 60
STALE_HOURS = 24
NS = {'d': 'DAV:', 'c': 'urn:ietf:params:xml:ns:caldav'}


def init_caldav(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS caldav_sync (
        meeting_id INTEGER PRIMARY KEY, href TEXT NOT NULL, content_hash TEXT NOT NULL, synced_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS caldav_busy (
        id INTEGER PRIMARY KEY AUTOINCREMENT, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, all_day INTEGER NOT NULL DEFAULT 0
      );
    ''')


def _settings(conn):
    from .quality import get_setting
    return get_setting(conn, SETTING, {'url': '', 'username': '', 'last_sync': '', 'last_result': ''})


def _check_url(url):
    if not isinstance(url, str) or len(url) > 500:
        raise ValueError('Kalender-Adresse fehlt oder ist zu lang.')
    p = urlsplit(url.strip())
    local = p.hostname in ('127.0.0.1', 'localhost', '::1')
    if p.scheme != 'https' and not (p.scheme == 'http' and local):
        raise ValueError('Bitte die HTTPS-Adresse des Kalenders angeben (z. B. https://dav.anbieter.de/calendars/name/kalender/).')
    if not p.hostname:
        raise ValueError('Kalender-Adresse unvollständig.')
    return url.strip() if url.strip().endswith('/') else url.strip() + '/'


def view(conn, db_path):
    from .credentials import status, store_info
    s = _settings(conn)
    stale = bool(s['last_sync']) and dt.datetime.now() - dt.datetime.fromisoformat(s['last_sync']) > dt.timedelta(hours=STALE_HOURS)
    return {'url': s['url'], 'username': s['username'], 'configured': bool(s['url'] and s['username']), 'password': status(db_path, 'caldav'), 'password_store': store_info(db_path, 'caldav'),
            'last_sync': s['last_sync'], 'last_result': s['last_result'], 'stale': stale,
            'busy_count': conn.execute('SELECT COUNT(*) FROM caldav_busy').fetchone()[0],
            'notice': 'Am besten ein App-Passwort des Anbieters verwenden. Passwörter stehen nie in der Datenbank.'}


def save(conn, db_path, data):
    if not isinstance(data, dict) or set(data) - {'url', 'username', 'password', 'remember', 'forget'}:
        raise ValueError('Erwartet: url, username, password, remember, forget.')
    from .credentials import forget, put
    from .quality import put_setting
    s = _settings(conn)
    if data.get('forget') is True:
        forget(db_path, 'caldav')
    if 'url' in data:
        s['url'] = _check_url(data['url']) if data['url'] else ''
    if 'username' in data:
        u = data['username']
        if not isinstance(u, str) or len(u) > 200:
            raise ValueError('Benutzername: höchstens 200 Zeichen.')
        s['username'] = u.strip()
    if data.get('password'):
        put(db_path, 'caldav', data['password'], remember=data.get('remember') is True)
    put_setting(conn, SETTING, s)
    conn.commit()
    return view(conn, db_path)


def _auth(conn, db_path):
    from . import netpolicy
    from .credentials import get
    netpolicy.load(conn)
    netpolicy.assert_online('der Kalender-Abgleich')
    s = _settings(conn)
    if not (s['url'] and s['username']):
        raise ValueError('Zuerst Kalender-Adresse und Benutzername eintragen.')
    pw = get(db_path, 'caldav')
    if not pw:
        raise ValueError('Passwort für den Kalender fehlt (nach einem Neustart erneut eingeben oder „auf diesem Rechner merken“).')
    token = base64.b64encode(f"{s['username']}:{pw}".encode()).decode()
    return s['url'], {'Authorization': 'Basic ' + token}


def _request(method, url, headers, body=None, timeout=20):
    req = urllib.request.Request(url, method=method, data=body.encode('utf-8') if isinstance(body, str) else body,
                                 headers={'User-Agent': 'SignalDesk-CalDAV', **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError('Anmeldung beim Kalender abgelehnt – Benutzername oder (App-)Passwort prüfen.') from e
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f'Kalender nicht erreichbar ({getattr(e, "reason", e)}).') from e


def test(conn, db_path):
    url, auth = _auth(conn, db_path)
    status, body = _request('PROPFIND', url, {**auth, 'Depth': '0', 'Content-Type': 'application/xml; charset=utf-8'},
                            '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:displayname/></d:prop></d:propfind>')
    if status != 207:
        raise ValueError(f'Der Server antwortet nicht wie ein CalDAV-Kalender (Status {status}). Adresse des Kalenders prüfen.')
    is_cal = b'calendar' in body
    return {'ok': True, 'calendar': is_cal,
            'notice': 'Verbindung steht.' + ('' if is_cal else ' Die Adresse ist aber kein Kalender – bitte die Adresse eines einzelnen Kalenders angeben.')}


# ---------------------------------------------------------------- iCalendar lesen

def _unfold(text):
    return re.sub(r'\r?\n[ \t]', '', text)


def _parse_dt(name_params, value):
    params = name_params.upper()
    v = value.strip()
    if 'VALUE=DATE' in params and re.fullmatch(r'\d{8}', v):
        return dt.datetime.strptime(v, '%Y%m%d'), True
    if v.endswith('Z'):
        utc = dt.datetime.strptime(v, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc)
        return utc.astimezone().replace(tzinfo=None), False  # Ortszeit des Rechners
    return dt.datetime.strptime(v[:15], '%Y%m%dT%H%M%S'), False  # TZID bzw. ohne Zone: als Ortszeit verstanden


def _duration(value):
    m = re.fullmatch(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?', value.strip())
    if not m:
        return dt.timedelta(hours=1)
    d, h, mi = (int(x or 0) for x in m.groups())
    return dt.timedelta(days=d, hours=h, minutes=mi)


def busy_from_ics(text):
    """Belegte Zeiten aus iCalendar-Text: (start, ende, ganztägig). Eigene SignalDesk-Termine, abgesagte und als
    „frei“ (TRANSPARENT) markierte Einträge zählen nicht."""
    out = []
    for block in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', _unfold(text), re.S):
        props = {}
        for line in block.splitlines():
            if ':' not in line:
                continue
            head, val = line.split(':', 1)
            name = head.split(';', 1)[0].upper()
            props.setdefault(name, (head, val))
        uid = props.get('UID', ('', ''))[1].strip()
        if OWN_UID.match(uid) or props.get('STATUS', ('', ''))[1].strip().upper() == 'CANCELLED' \
                or props.get('TRANSP', ('', ''))[1].strip().upper() == 'TRANSPARENT' or 'DTSTART' not in props:
            continue
        try:
            start, all_day = _parse_dt(*props['DTSTART'])
            if 'DTEND' in props:
                end, _ = _parse_dt(*props['DTEND'])
            elif 'DURATION' in props:
                end = start + _duration(props['DURATION'][1])
            else:
                end = start + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))
        except ValueError:
            continue
        out.append((start, end, all_day))
    return out


def _report(start, end):
    f = lambda d: d.strftime('%Y%m%dT%H%M%SZ')
    return ('<?xml version="1.0" encoding="utf-8"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:prop><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
            f'<c:time-range start="{f(start)}" end="{f(end)}"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')


# ---------------------------------------------------------------- Abgleich



def sync(conn, db_path):
    url, auth = _auth(conn, db_path)
    put_n = del_n = skip_n = 0
    since = (dt.datetime.now() - dt.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
    rows = conn.execute("""SELECT m.*, l.company FROM meetings m JOIN leads l ON l.id=m.lead_id
                           WHERE m.status IN ('geplant','bestaetigt','erledigt','abgesagt') AND m.starts_at>=?""", (since,)).fetchall()
    known = {r['meeting_id']: dict(r) for r in conn.execute('SELECT * FROM caldav_sync')}
    seen = set()
    for m in rows:
        from .calendar_feed import build_event
        ics = build_event(m)
        if ics is None:
            continue
        seen.add(m['id'])
        h = hashlib.sha256(ics).hexdigest()
        if known.get(m['id'], {}).get('content_hash') == h:
            skip_n += 1
            continue
        href = urljoin(url, f"signaldesk-meeting-{m['id']}.ics")
        status, _ = _request('PUT', href, {**auth, 'Content-Type': 'text/calendar; charset=utf-8'}, ics)
        if status not in (200, 201, 204):
            raise ValueError(f'Termin „{m["title"]}“ konnte nicht in den Kalender geschrieben werden (Status {status}).')
        conn.execute('''INSERT INTO caldav_sync(meeting_id, href, content_hash, synced_at) VALUES (?,?,?,datetime('now'))
                        ON CONFLICT(meeting_id) DO UPDATE SET href=excluded.href, content_hash=excluded.content_hash, synced_at=excluded.synced_at''',
                     (m['id'], href, h))
        put_n += 1
    for mid, k in known.items():  # in SignalDesk gelöscht → im Kalender entfernen (nur eigene Einträge; ältere bleiben stehen)
        if mid not in seen and not conn.execute('SELECT 1 FROM meetings WHERE id=?', (mid,)).fetchone():
            status, _ = _request('DELETE', k['href'], auth)
            if status in (200, 204, 404):
                conn.execute('DELETE FROM caldav_sync WHERE meeting_id=?', (mid,))
                del_n += 1
    now_utc = dt.datetime.now(dt.timezone.utc)
    status, body = _request('REPORT', url, {**auth, 'Depth': '1', 'Content-Type': 'application/xml; charset=utf-8'},
                            _report(now_utc - dt.timedelta(days=1), now_utc + dt.timedelta(days=HORIZON_DAYS)))
    if status != 207:
        raise ValueError(f'Belegte Zeiten konnten nicht gelesen werden (Status {status}).')
    busy = []
    try:
        root = ET.fromstring(body)
        for cd in root.iter('{urn:ietf:params:xml:ns:caldav}calendar-data'):
            busy += busy_from_ics(cd.text or '')
    except ET.ParseError as e:
        raise ValueError('Antwort des Kalenders nicht lesbar.') from e
    conn.execute('DELETE FROM caldav_busy')
    for start, end, all_day in busy:
        conn.execute('INSERT INTO caldav_busy(starts_at, ends_at, all_day) VALUES (?,?,?)',
                     (start.strftime('%Y-%m-%dT%H:%M'), end.strftime('%Y-%m-%dT%H:%M'), int(all_day)))
    from .quality import put_setting
    s = _settings(conn)
    s['last_sync'] = dt.datetime.now().isoformat(timespec='seconds')
    s['last_result'] = f'{put_n} Termin(e) übertragen, {skip_n} unverändert, {del_n} entfernt, {len(busy)} belegte Zeit(en) gelesen'
    put_setting(conn, SETTING, s)
    conn.commit()
    return {**view(conn, db_path), 'pushed': put_n, 'unchanged': skip_n, 'deleted': del_n, 'busy': len(busy)}


def conflicts(conn, starts_at, duration_min, ignore_meeting=None):
    """Überschneidungen eines geplanten Termins mit belegten Kalenderzeiten und anderen SignalDesk-Terminen."""
    try:
        start = dt.datetime.strptime(starts_at[:16], '%Y-%m-%dT%H:%M')
    except (TypeError, ValueError):
        return []
    end = start + dt.timedelta(minutes=int(duration_min or 30))
    s, e = start.strftime('%Y-%m-%dT%H:%M'), end.strftime('%Y-%m-%dT%H:%M')
    out = [{'source': 'kalender', 'from': r['starts_at'], 'to': r['ends_at'], 'all_day': bool(r['all_day'])}
           for r in conn.execute('SELECT * FROM caldav_busy WHERE starts_at<? AND ends_at>? ORDER BY starts_at', (e, s))]
    for r in conn.execute("""SELECT m.id, m.title, m.starts_at, m.duration_min FROM meetings m WHERE m.status IN ('geplant','bestaetigt')
                             AND substr(m.starts_at,1,10)=? AND m.id IS NOT ?""", (s[:10], ignore_meeting)):
        ms = dt.datetime.strptime(r['starts_at'][:16], '%Y-%m-%dT%H:%M')
        me = ms + dt.timedelta(minutes=r['duration_min'] or 30)
        if ms < end and me > start:
            out.append({'source': 'signaldesk', 'from': r['starts_at'][:16], 'to': me.strftime('%Y-%m-%dT%H:%M'), 'title': r['title']})
    return out


def route_caldav(h, conn, method, route, db_path):
    if route == '/api/caldav':
        if method == 'GET':
            h._send(200, view(conn, db_path))
            return True
        if method == 'POST':
            h._send(200, save(conn, db_path, h._body()))
            return True
        return False
    if route == '/api/caldav/test' and method == 'POST':
        h._send(200, test(conn, db_path))
        return True
    if route == '/api/caldav/sync' and method == 'POST':
        h._send(200, sync(conn, db_path))
        return True
    return False
