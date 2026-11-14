"""Eigene Erreichbarkeit und Auslastung (2.0.0-dev3).

Für Soloselbstständige ohne Sekretariat: eingegangene Anrufe und Anfragen in Sekunden festhalten, Rückruf mit Frist,
eigene Zeiten, Terminvorschläge, Auslastung aus kalkulierten Angeboten und eine Liste „als Nächstes kontaktieren“.

Nichts wird versendet oder angerufen. Die Liste ist eine Arbeitsreihenfolge, keine Kontakterlaubnis.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import statistics

from . import qualification as ql

KEY = 'availability_v1'
CHANNELS = {'anruf': 'Anruf verpasst', 'mailbox': 'Nachricht auf der Mailbox', 'email': 'E-Mail-Anfrage', 'formular': 'Kontaktformular', 'persoenlich': 'Persönlich angesprochen'}
WEEKDAYS = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')
TIME_RE = re.compile(r'([01]\d|2[0-3]):[0-5]\d')
FMT = '%Y-%m-%dT%H:%M'


def default_availability():
    return {'days': [0, 1, 2, 3, 4], 'callback_from': '16:00', 'callback_to': '17:30', 'meeting_from': '09:00', 'meeting_to': '16:00',
            'meeting_minutes': 45, 'delivery_share_pct': 70, 'absences': [], 'display_name': '', 'inbound_keep_days': 90}


def _t(text):
    return dt.time.fromisoformat(text)


def validate(data):
    base = default_availability()
    if not isinstance(data, dict) or set(data) - set(base):
        raise ValueError('Unbekannte Angaben bei den eigenen Zeiten.')
    out = {**base, **data}
    if not isinstance(out['days'], list) or not out['days'] or any(type(d) is not int or not 0 <= d <= 6 for d in out['days']):
        raise ValueError('Mindestens einen Arbeitstag wählen.')
    out['days'] = sorted(set(out['days']))
    for k in ('callback_from', 'callback_to', 'meeting_from', 'meeting_to'):
        if not isinstance(out[k], str) or not TIME_RE.fullmatch(out[k]):
            raise ValueError('Uhrzeiten als HH:MM angeben.')
    if _t(out['callback_from']) >= _t(out['callback_to']) or _t(out['meeting_from']) >= _t(out['meeting_to']):
        raise ValueError('„von“ muss vor „bis“ liegen.')
    if type(out['meeting_minutes']) is not int or not 15 <= out['meeting_minutes'] <= 180:
        raise ValueError('Termindauer: 15–180 Minuten.')
    if type(out['delivery_share_pct']) is not int or not 10 <= out['delivery_share_pct'] <= 100:
        raise ValueError('Anteil für Kundenprojekte: 10–100 %.')
    if type(out['inbound_keep_days']) is not int or not 7 <= out['inbound_keep_days'] <= 730:
        raise ValueError('Aufbewahrung des Eingangs: 7–730 Tage.')
    if not isinstance(out['display_name'], str) or len(out['display_name']) > 80:
        raise ValueError('Name: höchstens 80 Zeichen.')
    out['display_name'] = out['display_name'].strip()
    if not isinstance(out['absences'], list) or len(out['absences']) > 30:
        raise ValueError('Höchstens 30 Abwesenheiten.')
    clean = []
    for a in out['absences']:
        if not isinstance(a, dict) or set(a) - {'from', 'to', 'note'}:
            raise ValueError('Abwesenheit: von, bis, Notiz.')
        try:
            f, t = dt.date.fromisoformat(a.get('from', '')), dt.date.fromisoformat(a.get('to', ''))
        except (TypeError, ValueError) as exc:
            raise ValueError('Abwesenheit: Datum als JJJJ-MM-TT.') from exc
        if f > t:
            raise ValueError('Abwesenheit: „von“ liegt nach „bis“.')
        note = a.get('note', '')
        if not isinstance(note, str) or len(note) > 120:
            raise ValueError('Abwesenheit: Notiz höchstens 120 Zeichen.')
        clean.append({'from': f.isoformat(), 'to': t.isoformat(), 'note': note.strip()})
    out['absences'] = sorted(clean, key=lambda a: a['from'])
    return out


def load(conn):
    from .quality import get_setting
    try:
        return validate(get_setting(conn, KEY, default_availability()))
    except ValueError:
        return default_availability()


def save(conn, data):
    from .quality import put_setting
    av = validate(data)
    put_setting(conn, KEY, av)
    conn.commit()
    return av


def init_reach(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS inbound (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        who TEXT NOT NULL, contact TEXT NOT NULL DEFAULT '', channel TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
        received_at TEXT NOT NULL, due_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'offen',
        done_at TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_inbound_open ON inbound(status, due_at);
    ''')


# ---------------------------------------------------------------- eigene Zeiten

def absent(day, av):
    return next((a for a in av['absences'] if a['from'] <= day.isoformat() <= a['to']), None)


def is_workday(day, av):
    return day.weekday() in av['days'] and not absent(day, av)


def callback_due(received, av):
    """Frist für den Rückruf: Ende des nächsten eigenen Rückruf-Zeitfensters, das noch mindestens 15 Minuten offen ist."""
    start, end = _t(av['callback_from']), _t(av['callback_to'])
    day = received.date()
    for _ in range(400):
        if is_workday(day, av):
            close = dt.datetime.combine(day, end)
            if received + dt.timedelta(minutes=15) <= close:
                return close
        day += dt.timedelta(days=1)
        received = dt.datetime.combine(day, start)
    return dt.datetime.combine(day, end)


def meeting_slots(conn, av=None, count=3, now=None, horizon_days=21):
    """Freie Terminvorschläge an verschiedenen Tagen, abwechselnd vor- und nachmittags; bestehende Termine werden ausgespart."""
    av = av or load(conn)
    now = now or dt.datetime.now()
    dur = dt.timedelta(minutes=av['meeting_minutes'])
    gap = dt.timedelta(minutes=15)
    busy = []
    for m in conn.execute("SELECT starts_at, duration_min FROM meetings WHERE status IN ('geplant','bestaetigt') AND starts_at>=?", (now.strftime(FMT),)):
        try:
            s = dt.datetime.strptime(m['starts_at'], FMT)
        except ValueError:
            continue
        busy.append((s - gap, s + dt.timedelta(minutes=m['duration_min']) + gap))
    cb = (_t(av['callback_from']), _t(av['callback_to']))
    out, day, i = [], now.date() + dt.timedelta(days=1), 0
    while len(out) < count and i < horizon_days:
        i += 1
        if is_workday(day, av):
            first, last = dt.datetime.combine(day, _t(av['meeting_from'])), dt.datetime.combine(day, _t(av['meeting_to'])) - dur
            cands = []
            t = first
            while t <= last:
                cands.append(t)
                t += dt.timedelta(minutes=30)
            if len(out) % 2:  # abwechselnd: einmal früh, einmal spät am Tag
                cands.reverse()
            for c in cands:
                in_callback = c.time() < cb[1] and (c + dur).time() > cb[0]
                if not in_callback and all(c + dur <= b0 or c >= b1 for b0, b1 in busy):
                    out.append(c)
                    break
        day += dt.timedelta(days=1)
    slots = [{'starts_at': s.strftime(FMT), 'label': f"{WEEKDAYS[s.weekday()]}, {s.strftime('%d.%m.')} um {s.strftime('%H:%M')} Uhr"} for s in out]
    text = ''
    if slots:
        text = 'Für unser Gespräch (' + str(av['meeting_minutes']) + ' Minuten) kann ich Ihnen anbieten:\n' + '\n'.join('– ' + s['label'] for s in slots) + '\nPasst einer der Termine?'
    return {'slots': slots, 'text': text, 'notice': 'Vorschläge aus deinen Zeiten und den eingetragenen Terminen. SignalDesk kennt deinen Kalender außerhalb des Programms nicht.'}


def templates(av):
    name = av['display_name'] or '[dein Name]'
    days = ', '.join(WEEKDAYS[d] for d in av['days'])
    window = f"{av['callback_from']} und {av['callback_to']} Uhr"
    out = [{'key': 'mailbox', 'title': 'Mailbox-Ansage',
            'text': f'Guten Tag, hier ist {name}. Ich bin gerade im Kundentermin. Nennen Sie mir bitte Ihren Namen, Ihre Firma und Ihre Nummer – '
                    f'ich rufe Sie werktags zwischen {window} zurück.'},
           {'key': 'signatur', 'title': 'Zeile für Brief und Signatur', 'text': f'Telefonisch erreichen Sie mich am besten {days} zwischen {window}.'}]
    today = dt.date.today().isoformat()
    nxt = next((a for a in av['absences'] if a['to'] >= today), None)
    if nxt:
        back = dt.date.fromisoformat(nxt['to']) + dt.timedelta(days=1)
        while not is_workday(back, av):
            back += dt.timedelta(days=1)
        out.append({'key': 'abwesenheit', 'title': 'Abwesenheitsnotiz',
                    'text': f"Vielen Dank für Ihre Nachricht. Ich bin vom {dt.date.fromisoformat(nxt['from']).strftime('%d.%m.')} bis {dt.date.fromisoformat(nxt['to']).strftime('%d.%m.%Y')} "
                            f"nicht erreichbar und melde mich ab dem {back.strftime('%d.%m.%Y')} bei Ihnen. Ihre Nachricht wird nicht weitergeleitet.\n{name}"})
    return out


# ---------------------------------------------------------------- Eingang

def _text(data, key, lo, hi):
    v = data.get(key, '')
    if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
        raise ValueError(f'{key}: {lo}–{hi} Zeichen.')
    return re.sub(r'[\r\n]+', ' ', v).strip()


def create_inbound(conn, data, now=None):
    """Eingegangenen Anruf oder Anfrage festhalten – mit Rückruffrist aus den eigenen Zeiten. Kein Lead nötig."""
    if not isinstance(data, dict) or set(data) - {'lead_id', 'who', 'contact', 'channel', 'note', 'received_at'}:
        raise ValueError('Erwartet: who, channel, optional contact, note, lead_id, received_at.')
    now = now or dt.datetime.now()
    channel = data.get('channel')
    if channel not in CHANNELS:
        raise ValueError('Unbekannter Eingangsweg.')
    lead_id, lead = data.get('lead_id'), None
    if lead_id not in (None, ''):
        if isinstance(lead_id, bool) or not str(lead_id).isdigit():
            raise ValueError('Ungültige Firma.')
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (int(lead_id),)).fetchone()
        if not lead:
            raise ValueError('Firma existiert nicht.')
    who = _text(data, 'who', 0, 120) or (lead['company'] if lead else '')
    if not who:
        raise ValueError('Bitte angeben, wer sich gemeldet hat (Name oder Firma).')
    received = now
    if data.get('received_at'):
        try:
            received = dt.datetime.strptime(data['received_at'], FMT)
        except (TypeError, ValueError) as exc:
            raise ValueError('Zeitpunkt als JJJJ-MM-TTTHH:MM.') from exc
        if received > now + dt.timedelta(minutes=5):
            raise ValueError('Der Eingang kann nicht in der Zukunft liegen.')
    due = callback_due(max(received, now), load(conn))
    cur = conn.execute('INSERT INTO inbound(lead_id, who, contact, channel, note, received_at, due_at) VALUES (?,?,?,?,?,?,?)',
                       (lead['id'] if lead else None, who, _text(data, 'contact', 0, 120), channel, _text(data, 'note', 0, 1000),
                        received.strftime(FMT), due.strftime(FMT)))
    conn.commit()
    warning = ''
    if lead:
        from .workday import contact_lock
        lock = contact_lock(conn, lead)
        if lock:
            warning = f'Achtung: Diese Firma ist {lock}. Auf eine eigene Anfrage der Firma darfst du antworten – Werbung bleibt gesperrt.'
    return {'id': cur.lastrowid, 'due_at': due.strftime(FMT), 'warning': warning}


def complete_inbound(conn, ident, data, now=None):
    row = conn.execute('SELECT * FROM inbound WHERE id=?', (ident,)).fetchone()
    if not row:
        raise ValueError('Eintrag existiert nicht.')
    if row['status'] != 'offen':
        raise ValueError('Eintrag ist schon erledigt.')
    result = _text(data if isinstance(data, dict) else {}, 'result', 0, 500)
    now = now or dt.datetime.now()
    conn.execute("UPDATE inbound SET status='erledigt', done_at=?, result=? WHERE id=?", (now.strftime(FMT), result, ident))
    conn.commit()
    return {'done': True, 'in_time': now.strftime(FMT) <= row['due_at']}


def delete_inbound(conn, ident):
    conn.execute('DELETE FROM inbound WHERE id=?', (ident,))
    conn.commit()
    return {'deleted': True}


def anonymize_old_inbound(conn, av=None, now=None):
    """Datensparsamkeit: erledigte Einträge verlieren nach der eingestellten Frist Name, Kontakt und Notiz.
    Zeitpunkte bleiben für die Antwortzeit-Statistik. Offene Einträge werden nie angetastet."""
    av, now = av or load(conn), now or dt.datetime.now()
    limit = (now - dt.timedelta(days=av['inbound_keep_days'])).strftime(FMT)
    cur = conn.execute("""UPDATE inbound SET who='(gelöscht)', contact='', note='', result='', lead_id=NULL
                          WHERE status='erledigt' AND done_at<>'' AND done_at<? AND who<>'(gelöscht)'""", (limit,))
    if cur.rowcount:
        conn.commit()
    return cur.rowcount


def inbound_view(conn, now=None):
    now = now or dt.datetime.now()
    anonymize_old_inbound(conn, now=now)
    stamp = now.strftime(FMT)
    items = []
    for r in conn.execute("""SELECT i.*, l.company FROM inbound i LEFT JOIN leads l ON l.id=i.lead_id WHERE i.status='offen' ORDER BY i.due_at, i.id"""):
        d = dict(r)
        d['channel_label'] = CHANNELS.get(d['channel'], d['channel'])
        d['overdue'] = d['due_at'] < stamp
        d['due_today'] = d['due_at'][:10] == stamp[:10]
        items.append(d)
    done = conn.execute("SELECT received_at, done_at, due_at FROM inbound WHERE status='erledigt' ORDER BY id DESC LIMIT 50").fetchall()
    hours = []
    for r in done:
        try:
            hours.append((dt.datetime.strptime(r['done_at'], FMT) - dt.datetime.strptime(r['received_at'], FMT)).total_seconds() / 3600)
        except ValueError:
            pass
    stats = {'done': len(done), 'median_hours': round(statistics.median(hours), 1) if hours else None,
             'in_time_pct': round(100 * sum(1 for r in done if r['done_at'] <= r['due_at']) / len(done)) if done else None}
    return {'open': items, 'overdue': sum(1 for i in items if i['overdue']), 'stats': stats, 'channels': CHANNELS}


# ---------------------------------------------------------------- Auslastung

def _hours(internal_json):
    try:
        d = json.loads(internal_json or '{}')
        return float(d.get('estimated_hours') or d.get('hours') or 0)
    except (ValueError, TypeError):
        return 0.0


def capacity(conn, profile=None, av=None, today=None):
    """Auslastung aus kalkulierten Stunden: angenommene Angebote der letzten 8 Wochen und offene Angebote gegen die eigenen Wochenstunden."""
    profile, av = profile or ql.load(conn), av or load(conn)
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=56)).isoformat()
    from .postcalc import remaining_by_proposal
    tracked = remaining_by_proposal(conn)  # 2.0.0-dev5: wo Zeiten erfasst sind, zählt der Rest statt der vollen Kalkulation
    accepted = sum(tracked.values())
    untracked = 0
    for r in conn.execute("SELECT id, internal_json FROM proposals WHERE status='angenommen' AND substr(updated_at,1,10)>=?", (since,)):
        if r['id'] not in tracked:
            accepted += _hours(r['internal_json'])
            untracked += 1
    open_rows = conn.execute("""SELECT p.internal_json FROM proposals p JOIN leads l ON l.id=p.lead_id
                                WHERE p.superseded_by IS NULL AND p.status IN ('entwurf','gesendet_manuell') AND l.stage NOT IN ('verloren','gesperrt')""").fetchall()
    offered = sum(_hours(r['internal_json']) for r in open_rows)
    per_week = round(profile['weekly_hours'] * av['delivery_share_pct'] / 100, 1)
    weeks_accepted = round(accepted / per_week, 1) if per_week else None
    weeks_all = round((accepted + offered) / per_week, 1) if per_week else None
    if not accepted and not offered:
        level, hint = 'frei', 'Keine kalkulierten Stunden in Arbeit oder im Angebot – Zeit für Akquise.'
    elif weeks_all > 8:
        level, hint = 'voll', f'Würden alle offenen Angebote angenommen, wärst du etwa {weeks_all:g} Wochen ausgelastet. Neue Angebote mit späterem Starttermin kalkulieren.'
    elif weeks_accepted >= 4:
        level, hint = 'gut', f'Rund {weeks_accepted:g} Wochen Arbeit sind zugesagt. Akquise auf A-Firmen beschränken.'
    elif not accepted:
        level, hint = 'luft', f'Noch nichts zugesagt; {offered:g} Stunden sind angeboten. Es ist Platz für neue Aufträge.'
    else:
        level, hint = 'luft', f'Zugesagt sind rund {weeks_accepted:g} Wochen. Es ist Platz für neue Aufträge.'
    return {'weekly_hours': profile['weekly_hours'], 'delivery_hours_per_week': per_week, 'accepted_hours': round(accepted, 1), 'offered_hours': round(offered, 1),
            'offers_open': len(open_rows), 'weeks_accepted': weeks_accepted, 'weeks_if_all_accepted': weeks_all, 'level': level, 'hint': hint,
            'tracked_projects': len(tracked), 'untracked_projects': untracked,
            'notice': 'Aufträge mit erfassten Zeiten zählen mit ihren verbleibenden Stunden, abgeschlossene gar nicht mehr. '
                      + (f'{untracked} Auftrag/Aufträge ohne erfasste Zeiten zählen 8 Wochen lang mit der vollen Kalkulation – Zeiten unter „Angebote & Preise → Nachkalkulation“ erfassen.'
                         if untracked else 'Grundlage sind die kalkulierten Stunden der Angebote.')}


# ---------------------------------------------------------------- als Nächstes kontaktieren

def contact_list(conn, now=None, limit=12):
    """Arbeitsreihenfolge für Kontaktversuche: A vor B, „jetzt passendes Zeitfenster“ zuerst. Gesperrte, ausgeschlossene und
    C-Firmen erscheinen nicht. Keine Kontakterlaubnis – die Rechtsgrundlage bleibt je Kontakt zu prüfen."""
    now = now or dt.datetime.now()
    slot_now = ql.slot_of(now)
    profile = ql.load(conn)
    rows = []
    for lead in conn.execute("SELECT * FROM leads WHERE stage IN ('qualifiziert','kontakt','antwort')"):
        a = ql.assessment(conn, lead, profile, now)
        f, r, q = a['fit'], a['reachability'], a['qualification']
        if f['grade'] not in ('A', 'B') or q['status'] == 'nicht_qualifiziert' or r['status'] not in ('bereit', 'versuch_offen'):
            continue
        slot = r['next_slot']
        fits_now = bool(slot and r['attempts_open'] and slot['key'] == slot_now)
        rows.append({'lead_id': lead['id'], 'company': lead['company'], 'stage': lead['stage'], 'grade': f['grade'], 'score': f['score'],
                     'headline': a['headline'], 'hint': r['hint'], 'attempts_open': r['attempts_open'], 'fits_now': fits_now,
                     'channels': [c['label'] for c in r['channels'] if c['known']], 'permission': lead['permission'],
                     # 2.0.0-dev9: Öffnungszeiten aus OpenStreetMap (ungeprüft) – None heißt unbekannt, nicht geschlossen
                     'open_now': (r.get('hours') or {}).get('open_now'), 'hours_label': (r.get('hours') or {}).get('label', '')})
    # A vor B; innerhalb der Note: laut Öffnungszeiten gerade geschlossene Betriebe nach hinten, passendes Zeitfenster nach vorn
    rows.sort(key=lambda x: (x['grade'], x['open_now'] is False, not x['fits_now'], -(x['score'] or 0), x['company'].lower()))
    return {'items': rows[:limit], 'total': len(rows), 'slot_now': ql.SLOTS[slot_now],
            'notice': 'Reihenfolge nach Passung. Vor jedem Erstkontakt die Rechtsgrundlage prüfen und dokumentieren – ein belegter Kontaktweg ist keine Werbeerlaubnis.'}


def today(conn, now=None):
    av = load(conn)
    now = now or dt.datetime.now()
    return {'inbound': inbound_view(conn, now), 'contact_list': contact_list(conn, now), 'capacity': capacity(conn, av=av, today=now.date()),
            'absent_today': absent(now.date(), av), 'callback_window': f"{av['callback_from']}–{av['callback_to']} Uhr"}


def route(h, conn, method, path):
    if path == '/api/availability':
        if method == 'GET':
            av = load(conn)
        elif method == 'POST':
            av = save(conn, h._body())
        else:
            return False
        h._send(200, {'availability': av, 'weekdays': WEEKDAYS, 'templates': templates(av), 'slots': meeting_slots(conn, av)})
        return True
    if path == '/api/reach/today' and method == 'GET':
        h._send(200, today(conn))
        return True
    if path == '/api/inbound':
        if method == 'GET':
            h._send(200, inbound_view(conn))
            return True
        if method == 'POST':
            h._send(201, create_inbound(conn, h._body()))
            return True
    m = re.fullmatch(r'/api/inbound/(\d+)(/done)?', path)
    if m:
        ident = int(m.group(1))
        if m.group(2) and method == 'POST':
            body = h._body() if h.headers.get('Content-Length', '0') not in ('0', '') else {}
            h._send(200, complete_inbound(conn, ident, body))
            return True
        if not m.group(2) and method == 'DELETE':
            h._send(200, delete_inbound(conn, ident))
            return True
    return False
