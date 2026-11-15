"""Kalender-Abo und Termin-Export im iCalendar-Format (2.0.0-dev41, Produktreview M24 Stufe 1).

- **Abo-Adresse** (`/kalender/<schlüssel>.ics`): Kalenderprogramme auf diesem Rechner (z. B. Apple Kalender, Thunderbird,
  Outlook) abonnieren sie und zeigen deine Termine an. Der Schlüssel ist zufällig, lässt sich neu erzeugen (alte Adresse
  wird sofort ungültig) und das Abo lässt sich ausschalten. Ohne gültigen Schlüssel gibt es nichts.
- **Export** (`.ics`-Datei): für jeden Kalender, auch Web-Kalender wie Google, per Import.
- **Inhalt nur das Nötige:** Titel, Firma, Zeit, Ort, Status. Gesprächsnotizen und Personen bleiben in SignalDesk.
- Nur lesend: Der Kalender ändert nichts an SignalDesk. Abgleich in beide Richtungen ist CalDAV (Stufe 2).

Hinweis: Ein Web-Kalender im Internet kann eine Adresse auf deinem Rechner (127.0.0.1) nicht abrufen – dafür den Export
nutzen oder CalDAV.
"""
from __future__ import annotations

import datetime as dt
import hmac
import re
import secrets

SETTING = 'calendar_feed'
STATUS = {'geplant': 'TENTATIVE', 'bestaetigt': 'CONFIRMED', 'erledigt': 'CONFIRMED', 'abgesagt': 'CANCELLED'}


def _settings(conn):
    from .quality import get_setting
    return get_setting(conn, SETTING, {'enabled': False, 'token': ''})


def view(conn):
    s = _settings(conn)
    return {'enabled': bool(s['enabled'] and s['token']), 'path': f"/kalender/{s['token']}.ics" if s['enabled'] and s['token'] else '',
            'notice': 'Für Kalenderprogramme auf diesem Rechner. Web-Kalender im Internet können diese Adresse nicht abrufen – '
                      'dort die .ics-Datei importieren oder CalDAV nutzen.'}


def update(conn, data):
    if not isinstance(data, dict) or set(data) - {'enabled', 'regenerate'}:
        raise ValueError('Erwartet: enabled, regenerate.')
    from .quality import put_setting
    s = _settings(conn)
    if 'enabled' in data:
        if not isinstance(data['enabled'], bool):
            raise ValueError('enabled: true/false.')
        s['enabled'] = data['enabled']
    if data.get('regenerate') is True or (s['enabled'] and not s['token']):
        s['token'] = secrets.token_urlsafe(24)
    put_setting(conn, SETTING, s)
    conn.commit()
    return view(conn)


def token_ok(conn, token):
    s = _settings(conn)
    return bool(s['enabled'] and s['token'] and isinstance(token, str) and hmac.compare_digest(token, s['token']))


def _esc(v):
    return re.sub(r'[\r\n]+', '\\n', str(v or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')).strip()


def _fold(line):
    """RFC 5545: Zeilen höchstens 75 Oktette, Fortsetzung mit Leerzeichen."""
    raw = line.encode('utf-8')
    if len(raw) <= 75:
        return line
    out, cur = [], ''
    for ch in line:
        if len((cur + ch).encode('utf-8')) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return '\r\n '.join(out)


def _local(ts):
    return dt.datetime.strptime(ts[:16], '%Y-%m-%dT%H:%M')


HEAD = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//SignalDesk//Termine//DE', 'CALSCALE:GREGORIAN']


def _vevent(m, stamp):
    """Ein Termin als VEVENT – nur Titel, Firma, Zeit, Ort, Status (gemeinsam für Abo und CalDAV)."""
    try:
        start = _local(m['starts_at'])
    except ValueError:
        return None
    end = start + dt.timedelta(minutes=m['duration_min'] or 30)
    lines = ['BEGIN:VEVENT', f"UID:meeting-{m['id']}@signaldesk.local", f'DTSTAMP:{stamp}',
             f"DTSTART;TZID=Europe/Berlin:{start:%Y%m%dT%H%M%S}", f"DTEND;TZID=Europe/Berlin:{end:%Y%m%dT%H%M%S}",
             f"SUMMARY:{_esc(m['title'])} – {_esc(m['company'])}", f"STATUS:{STATUS.get(m['status'], 'TENTATIVE')}"]
    if m['location']:
        lines.append(f"LOCATION:{_esc(m['location'])}")
    return lines + ['DESCRIPTION:Termin aus SignalDesk. Notizen und Ansprechpartner stehen in SignalDesk.', 'END:VEVENT']


def _out(lines):
    return ('\r\n'.join(_fold(x) for x in lines) + '\r\n').encode('utf-8')


def build_event(m):
    """Einzelnes Kalenderobjekt für CalDAV. DTSTAMP fest aus dem Termin, damit unveränderte Termine nicht neu übertragen werden."""
    stamp = re.sub(r'[^0-9T]', '', (m['created_at'] or '2000-01-01 00:00:00').replace(' ', 'T'))[:15] + 'Z'
    ev = _vevent(m, stamp)
    return _out(HEAD + ev + ['END:VCALENDAR']) if ev else None


def build(conn, days_back=30):
    since = (dt.datetime.now() - dt.timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M')
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = HEAD + ['METHOD:PUBLISH', 'X-WR-CALNAME:SignalDesk Termine', 'X-WR-TIMEZONE:Europe/Berlin']
    for m in conn.execute("""SELECT m.*, l.company FROM meetings m JOIN leads l ON l.id=m.lead_id
                             WHERE m.status IN ('geplant','bestaetigt','abgesagt') AND m.starts_at>=? ORDER BY m.starts_at""", (since,)):
        ev = _vevent(m, stamp)
        if ev:
            lines += ev
    lines.append('END:VCALENDAR')
    return _out(lines)


def route_calendar(h, conn, method, route):
    if route == '/api/kalender':
        if method == 'GET':
            h._send(200, view(conn))
            return True
        if method == 'POST':
            h._send(200, update(conn, h._body()))
            return True
        return False
    if route == '/api/kalender/export.ics' and method == 'GET':
        h._send_raw(200, build(conn), 'text/calendar', f'SignalDesk-Termine-{dt.date.today().isoformat()}.ics')
        return True
    m = re.fullmatch(r'/kalender/([A-Za-z0-9_-]{16,64})\.ics', route)
    if m and method == 'GET':
        if not token_ok(conn, m.group(1)):
            h._error('Nicht gefunden.', 404)
        else:
            h._send_raw(200, build(conn), 'text/calendar')
        return True
    return False
