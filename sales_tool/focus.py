"""2.0.0-dev15 (Produktreview M08, M09, M11): Fokusliste für „Heute“, geführter Einstieg, gespeicherte Arbeitsansichten.

- Fokus: höchstens drei nächste Aktionen mit Grund und Frist. Reihenfolge wie im Review: überfällige Zusagen, Termine,
  heute Zugesagtes, vereinbartes Nachfassen – erst danach neue Akquise. Eine Passungsnote verdrängt nie eine Rückrufzusage.
- Einstieg: was ein neuer Nutzer einrichten sollte, jeweils mit echter Prüfung statt Häkchen zum Abhaken.
- Ansichten: eigene Filterkombinationen der Firmenliste speichern (nur Filter, keine Firmendaten).
Nichts davon schreibt Firmendaten oder versendet etwas.
"""
import datetime as dt
import re

from . import reach
from .quality import get_setting, put_setting
from .today import wiedervorlage

# ---------------------------------------------------------------- Fokus

_RANK = {'zusage_ueberfaellig': 0, 'termin': 1, 'zusage_heute': 2, 'angebot_frist': 3, 'nachfassen': 4, 'angebot_entwurf': 5,
         'bedarfsanalyse': 6, 'recherche': 7, 'akquise': 8}
_PROMISES = ('rueckruf', 'aufgabe', 'naechster_schritt')


def _days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a[:10])).days


def _bucket(item, today):
    kind, due = item['kind'], item['due']
    if kind in _PROMISES:
        return 'zusage_ueberfaellig' if item['overdue'] else 'zusage_heute'
    return kind if kind in _RANK else 'nachfassen'


def _why(item, bucket, today):
    t = today.isoformat()
    due, detail = item['due'], item.get('detail') or ''
    if bucket == 'zusage_ueberfaellig':
        n = _days(due, t)
        text = f"seit {n} {'Tag' if n == 1 else 'Tagen'} überfällig"
    elif bucket == 'termin':
        text = ('Termin heute' if due == t else 'Termin morgen') + (f' · {detail}' if detail else '')
        return text
    elif bucket == 'zusage_heute':
        if due > t:
            text = 'morgen zugesagt' if item['kind'] == 'rueckruf' else 'morgen fällig'
        else:
            text = 'heute zugesagt' if item['kind'] == 'rueckruf' else 'heute fällig'
    elif bucket == 'angebot_frist':
        text = f"Bindefrist endet am {dt.date.fromisoformat(due).strftime('%d.%m.')}"
    else:
        text = ''
    return ' · '.join(x for x in (text, detail) if x)


def focus(conn, today=None, now=None, limit=3):
    today = today or dt.date.today()
    now = now or dt.datetime.combine(today, dt.time(10, 0))
    out = []
    for item in wiedervorlage(conn, today):
        b = _bucket(item, today)
        out.append({'rank': _RANK[b], 'bucket': b, 'title': item['title'], 'company': item['company'], 'lead_id': item['lead_id'],
                    'due': item['due'], 'overdue': item['overdue'], 'why': _why(item, b, today),
                    'action': {'label': item['action'], 'view': item['view'], 'section': item.get('section'), 'lead_id': item['lead_id'],
                               'anchor': item.get('anchor'), 'ref': item['ref'] if item['view'] == 'quotes' else None}})
    out.sort(key=lambda x: (x['rank'], x['due'] or '9999'))
    open_total = len(out)
    if len(out) < limit:  # erst wenn Zugesagtes und Nachfassen erledigt sind: neue Akquise
        cl = reach.contact_list(conn, now, limit=limit)
        for c in cl['items'][:limit - len(out)]:
            why = f"Passung {c['grade']} · {c['hint']}" + (' · jetzt passendes Zeitfenster' if c['fits_now'] else '')
            out.append({'rank': _RANK['akquise'], 'bucket': 'akquise', 'title': 'Kontakt aufnehmen', 'company': c['company'],
                        'lead_id': c['lead_id'], 'due': '', 'overdue': False, 'why': why,
                        'action': {'label': 'Firma öffnen', 'view': 'lead', 'lead_id': c['lead_id']}})
    return {'items': out[:limit], 'more': max(0, open_total - limit),
            'empty_next': None if out else {'label': 'Neue Firmen finden', 'view': 'finder'},
            'notice': 'Zuerst Zugesagtes und Termine, dann Nachfassen, danach neue Akquise. Vor jedem Erstkontakt die Rechtsgrundlage prüfen.'}


# ---------------------------------------------------------------- Einstieg

ONBOARDING_KEY = 'onboarding_v1'


def onboarding(conn):
    has = lambda key: conn.execute('SELECT 1 FROM app_settings WHERE key=?', (key,)).fetchone() is not None
    target = get_setting(conn, 'target_profile_v1', {})
    leads = conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
    inbound = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='inbound'").fetchone()[0] and \
        conn.execute('SELECT COUNT(*) FROM inbound').fetchone()[0]
    steps = [
        {'key': 'preise', 'label': 'Leistungen und Preise prüfen', 'detail': 'Stundensatz, Mindestverdienst und Katalogwerte – Grundlage jedes Festpreises.',
         'done': has('pricing'), 'action': {'label': 'Öffnen', 'view': 'settings', 'anchor': 'preise'}},
        {'key': 'zielkunden', 'label': 'Zielkunden festlegen', 'detail': 'Region, Größe und Branchen – danach bewertet SignalDesk die Passung.',
         'done': bool(target.get('home') and target.get('industries')), 'action': {'label': 'Öffnen', 'view': 'settings', 'anchor': 'targetProfile'}},
        {'key': 'zeiten', 'label': 'Arbeitszeiten und Erreichbarkeit eintragen', 'detail': 'Rückrufzeiten, Wochenstunden, Abwesenheiten.',
         'done': has(reach.KEY), 'action': {'label': 'Öffnen', 'view': 'settings', 'anchor': 'ownTimes'}},
        {'key': 'erste_firma', 'label': 'Erste Firma oder Anfrage erfassen', 'detail': 'Eine konkrete Anfrage oder Firma genügt – ein Recherchelauf ist nicht nötig.',
         'done': bool(leads or inbound), 'action': {'label': 'Firma erfassen', 'view': 'new_lead'}},
    ]
    state = get_setting(conn, ONBOARDING_KEY, {'dismissed': False})
    done = sum(s['done'] for s in steps)
    return {'steps': steps, 'done': done, 'total': len(steps), 'dismissed': bool(state.get('dismissed')),
            'show': not state.get('dismissed') and done < len(steps)}


def set_onboarding(conn, data):
    if not isinstance(data, dict) or not isinstance(data.get('dismissed'), bool):
        raise ValueError('Erwartet: {"dismissed": true|false}.')
    put_setting(conn, ONBOARDING_KEY, {'dismissed': data['dismissed']})
    conn.commit()
    return onboarding(conn)


# ---------------------------------------------------------------- Arbeitsansichten der Firmenliste

VIEWS_KEY = 'lead_views_v1'
PRESETS = ('alle', 'heute', 'ohne_schritt', 'angebote', 'recherche', 'passung_ab', 'kunden')
_STAGES = ('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot', 'gewonnen', 'verloren', 'gesperrt')


def lead_views(conn):
    v = get_setting(conn, VIEWS_KEY, [])
    return v if isinstance(v, list) else []


def save_lead_views(conn, data):
    views = data.get('views') if isinstance(data, dict) else None
    if not isinstance(views, list) or len(views) > 12:
        raise ValueError('Höchstens 12 gespeicherte Ansichten.')
    clean, names = [], set()
    for v in views:
        if not isinstance(v, dict):
            raise ValueError('Ungültige Ansicht.')
        name = re.sub(r'\s+', ' ', str(v.get('name') or '')).strip()
        if not 1 <= len(name) <= 40:
            raise ValueError('Name der Ansicht: 1 bis 40 Zeichen.')
        if name.casefold() in names:
            raise ValueError(f'Ansicht „{name}“ gibt es schon.')
        names.add(name.casefold())
        preset = str(v.get('preset') or 'alle')
        stage = str(v.get('stage') or '')
        q = re.sub(r'\s+', ' ', str(v.get('q') or '')).strip()[:120]
        if preset not in PRESETS:
            raise ValueError('Unbekannte Arbeitsansicht.')
        if stage and stage not in _STAGES:
            raise ValueError('Unbekannte Phase.')
        clean.append({'name': name, 'preset': preset, 'stage': stage, 'q': q})
    put_setting(conn, VIEWS_KEY, clean)
    conn.commit()
    return clean


def last_contacts(conn):
    """Letzter dokumentierter Kontakt je Firma: Gesprächsnotiz, Anruf oder erledigter Termin."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    parts = ["SELECT lead_id, created_at AS ts FROM activities WHERE activity_type IN ('gespraech','anfrage','angebot','einwand','abschluss')"]
    if 'calls' in tables:
        parts.append('SELECT lead_id, created_at FROM calls')
    if 'meetings' in tables:
        parts.append("SELECT lead_id, starts_at FROM meetings WHERE status='erledigt'")
    rows = conn.execute(f"SELECT lead_id, MAX(ts) FROM ({' UNION ALL '.join(parts)}) GROUP BY lead_id").fetchall()
    return {r[0]: (r[1] or '')[:10] for r in rows}


def route(h, conn, method, path):
    if path == '/api/focus' and method == 'GET':
        h._send(200, {'focus': focus(conn), 'onboarding': onboarding(conn)})
        return True
    if path == '/api/onboarding' and method in ('PUT', 'POST'):
        h._send(200, set_onboarding(conn, h._body(max_len=1024)))
        return True
    if path == '/api/lead-views':
        if method == 'GET':
            h._send(200, {'views': lead_views(conn), 'presets': list(PRESETS)})
            return True
        if method in ('PUT', 'POST'):
            h._send(200, {'views': save_lead_views(conn, h._body(max_len=16384)), 'presets': list(PRESETS)})
            return True
    return False
