"""Kundenbewertung und Erreichbarkeit (2.0.0-dev2).

Drei getrennte Ergebnisse je Firma – keines davon ist eine Kaufwahrscheinlichkeit oder eine Kontakterlaubnis:

- Passung (vor dem Gespräch): passt die Firma laut Recherche zum eigenen Zielkundenprofil?
- Qualifizierung (nach dem Gespräch): was hat der Kunde tatsächlich bestätigt?
- Erreichbarkeit: welche Kontaktwege sind belegt, wie viele Versuche gab es, was ist der nächste sinnvolle Versuch?

Grundregeln: Unbekanntes bleibt „unbekannt“ und zählt nicht als schlecht. Jedes Kriterium nennt, worauf es sich stützt.
K.-o.-Kriterien schlagen jede Punktzahl. Das Modul liest nur; es ändert keine Firmendaten.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from . import gemeinden as gm
from . import industries as ind

KEY = 'target_profile_v1'
SLOTS = {'vormittag': 'vormittags (8–11 Uhr)', 'mittag': 'mittags (11–14 Uhr)', 'nachmittag': 'nachmittags (14–17 Uhr)', 'abend': 'am frühen Abend (17–19 Uhr)'}
SLOT_ORDER = ('vormittag', 'nachmittag', 'mittag', 'abend')
MISSED = ('nicht_erreicht', 'mailbox')
LOST_REASONS = {
    'kein_bedarf': 'Kein Bedarf',
    'kein_budget': 'Kein Budget',
    'zeitpunkt': 'Falscher Zeitpunkt – später wieder',
    'wettbewerber': 'Anderer Anbieter gewählt',
    'inhouse': 'Wird intern gelöst',
    'preis': 'Preis zu hoch',
    'nicht_erreicht': 'Niemanden erreicht',
    'passt_nicht': 'Passt nicht zu meinem Angebot',
    'sonstiges': 'Sonstiges',
}
OWNER_LED = re.compile(r'\b(e\.?\s?k\.?|e\.?\s?kfm\.?|e\.?\s?kfr\.?|einzelunternehm\w*|inhaber\w*|gbr|ohg|partg\w*|freiberuf\w*)\b', re.I)
CORPORATE = re.compile(r'\b(ag|se|kgaa|aktiengesellschaft)\b', re.I)
VALUE = {'passt': 1.0, 'teilweise': 0.5, 'passt_nicht': 0.0}
STATUS_LABEL = {'passt': 'passt', 'teilweise': 'teilweise', 'passt_nicht': 'passt nicht', 'unbekannt': 'unbekannt'}


def default_profile():
    return {'name': 'Mein Zielkundenprofil', 'industries': [], 'excluded_industries': [], 'employees_min': 1, 'employees_max': 50,
            'home': '', 'radius_km': 30, 'min_order_eur': 1500, 'weekly_hours': 30, 'prefer_owner_led': True,
            'max_attempts': 3, 'retry_days': 2, 'park_days': 90}


_INT_LIMITS = {'employees_min': (0, 100000), 'employees_max': (1, 1000000), 'radius_km': (1, 1000), 'min_order_eur': (0, 1000000),
               'weekly_hours': (1, 80), 'max_attempts': (1, 10), 'retry_days': (1, 30), 'park_days': (7, 730)}


def validate(data):
    base = default_profile()
    if not isinstance(data, dict) or set(data) - set(base):
        raise ValueError('Unbekannte Angaben im Zielkundenprofil.')
    out = {**base, **data}
    if not isinstance(out['name'], str) or not 1 <= len(out['name'].strip()) <= 80:
        raise ValueError('Profilname: 1–80 Zeichen.')
    out['name'] = out['name'].strip()
    for key in ('industries', 'excluded_industries'):
        out[key] = ind.validate_keys(out[key])
    if set(out['industries']) & set(out['excluded_industries']):
        raise ValueError('Eine Branche kann nicht zugleich Ziel und Ausschluss sein.')
    for key, (lo, hi) in _INT_LIMITS.items():
        if type(out[key]) is not int or not lo <= out[key] <= hi:
            raise ValueError(f'{key}: ganze Zahl zwischen {lo} und {hi}.')
    if out['employees_min'] > out['employees_max']:
        raise ValueError('Mitarbeiter: „von“ darf nicht größer sein als „bis“.')
    if not isinstance(out['prefer_owner_led'], bool):
        raise ValueError('prefer_owner_led: ja oder nein.')
    if not isinstance(out['home'], str) or len(out['home']) > 80:
        raise ValueError('Standort: höchstens 80 Zeichen.')
    out['home'] = out['home'].strip()
    if out['home'] and not _center(out['home']):
        raise ValueError('Standort nicht im Ortsverzeichnis gefunden – bitte PLZ oder Ortsnamen angeben.')
    return out


def load(conn):
    from .quality import get_setting
    try:
        return validate(get_setting(conn, KEY, default_profile()))
    except ValueError:
        return default_profile()


def save(conn, data):
    from .quality import put_setting
    profile = validate(data)
    put_setting(conn, KEY, profile)
    conn.commit()
    return profile


_CENTERS = {}


def _center(place):
    """Koordinaten zu PLZ oder Ortsname aus dem mitgelieferten Ortsverzeichnis (offline).
    Treffer werden gemerkt (das Verzeichnis ist fest); Fehlschläge nicht, damit ein später verfügbares Verzeichnis wirkt."""
    place = (place or '').strip()
    if place in _CENTERS:
        return _CENTERS[place]
    m = re.match(r'(\d{5})\b\s*(.*)', place)
    g = None
    try:
        if m:
            g = gm.by_postcode(m.group(1)) or (gm.by_name(m.group(2), m.group(1)) if m.group(2) else None)
        elif place:
            g = gm.by_name(place)
    except Exception:  # Ortsverzeichnis fehlt oder ist beschädigt – Entfernung bleibt unbekannt
        g = None
    if not g:
        return None
    if len(_CENTERS) > 20000:
        _CENTERS.clear()
    _CENTERS[place] = {'lat': g['lat'], 'lon': g['lon'], 'name': g['name']}
    return _CENTERS[place]


def _crit(key, label, weight, status, detail, action=None):
    return {'key': key, 'label': label, 'weight': weight, 'status': status, 'status_label': STATUS_LABEL[status], 'detail': detail, 'action': action}


def _candidate(conn, lead_id):
    row = conn.execute('SELECT industry_key, distance_km FROM discovery_candidates WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lead_id,)).fetchone()
    return dict(row) if row else {}


def _industry(lead, cand):
    key = cand.get('industry_key') or ind.guess(f"{lead['company']} {lead['legal_name'] or ''} {lead['industry'] or ''}")
    if not key:
        m = re.search(r'Branche laut Quelle: ([^.]+)', lead['note'] or '')
        key = ind.guess(m.group(1)) if m else ''
    return key, ('laut Firmensuche' if cand.get('industry_key') else 'aus Firmenname geschätzt')


def _distance(lead, cand, profile):
    home = _center(profile['home']) if profile['home'] else None
    place = _center(f"{lead['zip'] or ''} {lead['city'] or ''}".strip() or lead['location'])
    if home and place:
        return round(gm.haversine(home['lat'], home['lon'], place['lat'], place['lon'])), f"von {home['name']} bis {place['name']}"
    if cand.get('distance_km') is not None:
        return round(cand['distance_km']), 'laut Suchgebiet der Firmensuche'
    return None, ''


def knockouts(conn, lead, profile, industry_key='', lock=None):
    """Harte Ausschlussgründe – schlagen jede Punktzahl."""
    from .workday import contact_lock
    out = []
    lock = contact_lock(conn, lead) if lock is None else lock
    if lock:
        out.append({'key': 'sperre', 'label': 'Kontaktsperre', 'detail': f'Firma ist {lock}.'})
    stop = conn.execute("SELECT title FROM buying_signals WHERE lead_id=? AND category='aufloesung' AND status<>'verworfen' LIMIT 1", (lead['id'],)).fetchone()
    reg = conn.execute("SELECT published_at FROM register_events WHERE lead_id=? AND event_type='aufloesung' LIMIT 1", (lead['id'],)).fetchone()
    if stop or reg:
        out.append({'key': 'aufloesung', 'label': 'Auflösung oder Löschung im Register',
                    'detail': (stop['title'] if stop else f"Registerbekanntmachung {reg['published_at'] or 'ohne Datum'}") + ' – vor weiterer Arbeit prüfen.'})
    if industry_key and industry_key in profile['excluded_industries']:
        out.append({'key': 'branche', 'label': 'Ausgeschlossene Branche', 'detail': f"{ind.INDUSTRIES[industry_key]['label']} steht im Profil unter „nicht bedienen“."})
    return out


def fit(conn, lead, profile=None, lock=None):
    """Passung vor dem Gespräch. Note A/B/C nur bei ausreichender Datenlage, sonst None („Datenlage unzureichend“)."""
    profile = profile or load(conn)
    lid = lead['id']
    cand = _candidate(conn, lid)
    crits, warnings = [], []
    profile_action = {'label': 'Zielkundenprofil einstellen', 'view': 'settings', 'anchor': 'targetProfile'}  # 2.0.0-dev14: eigener Bereich

    key, basis = _industry(lead, cand)
    if not profile['industries']:
        crits.append(_crit('branche', 'Branche', 25, 'unbekannt', 'Im Zielkundenprofil sind noch keine Zielbranchen gewählt.', profile_action))
    elif not key:
        crits.append(_crit('branche', 'Branche', 25, 'unbekannt', 'Branche der Firma nicht erkennbar.'))
    else:
        ok = key in profile['industries']
        crits.append(_crit('branche', 'Branche', 25, 'passt' if ok else 'passt_nicht',
                           f"{ind.INDUSTRIES[key]['label']} ({basis}) – {'Zielbranche' if ok else 'keine Zielbranche'}."))

    size = int(lead['employees'] or 0)
    lo, hi = profile['employees_min'], profile['employees_max']
    if not size:
        crits.append(_crit('groesse', 'Unternehmensgröße', 15, 'unbekannt', 'Mitarbeiterzahl nicht bekannt.'))
    else:
        st = 'passt' if lo <= size <= hi else ('teilweise' if size <= hi * 2 else 'passt_nicht')
        crits.append(_crit('groesse', 'Unternehmensgröße', 15, st, f'{size} Mitarbeiter; Wunsch {lo}–{hi}.'))

    km, how = _distance(lead, cand, profile)
    if km is None:
        crits.append(_crit('region', 'Entfernung', 15, 'unbekannt',
                           'Standort im Profil fehlt.' if not profile['home'] else 'Ort der Firma nicht bekannt.', None if profile['home'] else profile_action))
    else:
        r = profile['radius_km']
        st = 'passt' if km <= r else ('teilweise' if km <= r * 1.5 else 'passt_nicht')
        crits.append(_crit('region', 'Entfernung', 15, st, f'{km} km ({how}); Einzugsgebiet {r} km.'))
        if st == 'passt_nicht':
            warnings.append(f'Außerhalb des Einzugsgebiets ({km} km).')

    sig = conn.execute("""SELECT SUM(polarity='pro') AS pro, SUM(polarity='contra') AS contra, SUM(polarity='pro' AND status='bestaetigt') AS ok
                          FROM buying_signals WHERE lead_id=? AND status<>'verworfen' AND category<>'aufloesung'""", (lid,)).fetchone()
    pro, contra, confirmed = sig['pro'] or 0, sig['contra'] or 0, sig['ok'] or 0
    has_src = (lead['signal_source'] or '').startswith('http') and lead['signal_type'] not in ('', 'kein_signal')
    act = {'label': 'Kaufsignale prüfen', 'view': 'signals', 'lead_id': lid}
    if confirmed or has_src:
        crits.append(_crit('anlass', 'Anlass mit Quelle', 20, 'passt', f'{confirmed} bestätigte Kaufsignale' if confirmed else 'Anlass mit Quelle am Lead eingetragen.'))
    elif pro:
        crits.append(_crit('anlass', 'Anlass mit Quelle', 20, 'teilweise', f'{pro} ungeprüfte Hinweise – Quelle ansehen und bestätigen.', act))
    else:
        crits.append(_crit('anlass', 'Anlass mit Quelle', 20, 'unbekannt', 'Kein Anlass belegt. Das heißt nicht, dass es keinen gibt.', act))
    if contra and contra >= max(1, pro):
        warnings.append(f'{contra} Gegenhinweis(e), z. B. eigene Stelle für die Aufgabe ausgeschrieben.')

    ws = conn.execute('SELECT potential, coverage FROM website_scores WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lid,)).fetchone()
    act = {'label': 'Firmen-Bericht erstellen', 'view': 'report', 'lead_id': lid}
    if not ws or ws['potential'] is None:
        crits.append(_crit('website', 'Sichtbarer Bedarf auf der Website', 15, 'unbekannt',
                           'Website noch nicht bewertet.' if lead['website'] else 'Keine belegte Website.', act if lead['website'] else None))
    else:
        p = ws['potential']
        st = 'passt' if p >= 55 else ('teilweise' if p >= 30 else 'passt_nicht')
        crits.append(_crit('website', 'Sichtbarer Bedarf auf der Website', 15, st, f"Auffälligkeiten {p} von 100 ({ws['coverage']} % der Kriterien belegt)."))

    if profile['prefer_owner_led']:
        form = f"{lead['legal_form'] or ''} {lead['legal_name'] or ''} {lead['company']}"
        if CORPORATE.search(lead['legal_form'] or '') or size > 250:
            crits.append(_crit('entscheidungsweg', 'Kurzer Entscheidungsweg', 10, 'passt_nicht', 'Kapitalgesellschaft bzw. über 250 Mitarbeiter – meist mehrere Entscheider.'))
        elif OWNER_LED.search(form) or 0 < size <= 20:
            crits.append(_crit('entscheidungsweg', 'Kurzer Entscheidungsweg', 10, 'passt', 'Vermutlich inhabergeführt (Rechtsform bzw. Größe) – im Gespräch bestätigen.'))
        elif lead['legal_form']:
            crits.append(_crit('entscheidungsweg', 'Kurzer Entscheidungsweg', 10, 'teilweise', f"Rechtsform {lead['legal_form']}, Größe unbekannt."))
        else:
            crits.append(_crit('entscheidungsweg', 'Kurzer Entscheidungsweg', 10, 'unbekannt', 'Rechtsform und Größe nicht bekannt.'))

    ko = knockouts(conn, lead, profile, key, lock)
    known = [c for c in crits if c['status'] != 'unbekannt']
    total = sum(c['weight'] for c in crits)
    known_w = sum(c['weight'] for c in known)
    coverage = round(100 * known_w / total) if total else 0
    score = round(100 * sum(c['weight'] * VALUE[c['status']] for c in known) / known_w) if known_w else None
    if ko:
        grade, verdict = 'X', 'Ausschluss: ' + '; '.join(k['label'] for k in ko)
    elif coverage < 40 or score is None:
        grade, verdict = None, f'Datenlage unzureichend ({coverage} % der Kriterien bekannt) – erst recherchieren, dann bewerten.'
    else:
        grade = 'A' if score >= 70 else ('B' if score >= 45 else 'C')
        verdict = {'A': 'Passt gut zum Profil – vorrangig bearbeiten.', 'B': 'Passt teilweise – bearbeiten, wenn Zeit ist.',
                   'C': 'Passt kaum – nur mit konkretem Anlass weiterverfolgen.'}[grade]
    return {'grade': grade, 'score': score, 'coverage_pct': coverage, 'verdict': verdict, 'criteria': crits, 'knockouts': ko, 'warnings': warnings,
            'missing': [c['label'] for c in crits if c['status'] == 'unbekannt'], 'profile_name': profile['name'],
            'notice': 'Passung = Übereinstimmung mit deinem Zielkundenprofil laut Recherche. Keine Kaufwahrscheinlichkeit, keine Kontakterlaubnis.'}


def _order_value(conn, lead_id):
    row = conn.execute("SELECT customer_json, number FROM proposals WHERE lead_id=? AND status<>'abgelehnt' ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone()
    if not row:
        return None, ''
    try:
        return float(json.loads(row['customer_json']).get('net_eur') or 0) or None, row['number'] or 'Entwurf'
    except (ValueError, TypeError):
        return None, ''


def qualification(conn, lead, profile=None):
    """Qualifizierung nach dem Gespräch – nur aus dem, was dokumentiert und vom Kunden bestätigt ist."""
    from .workday import need_status, talks
    profile = profile or load(conn)
    lid = lead['id']
    n_talks = len(talks(conn, lid))
    notice = 'Qualifizierung = was im Gespräch geklärt und dokumentiert wurde. Offene Punkte sind Fragen für das nächste Gespräch.'
    if not n_talks:
        return {'status': 'offen', 'status_label': 'noch kein Gespräch', 'verdict': 'Noch kein Gespräch dokumentiert – Qualifizierung beginnt danach.',
                'criteria': [], 'knockouts': [], 'questions': [], 'talks': 0, 'notice': notice}
    d = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lid,)).fetchone()
    d = dict(d) if d else {}
    need = need_status(conn, lid)
    crits, ko, questions = [], [], []
    act = {'label': 'Bedarfsanalyse öffnen', 'view': 'lead', 'lead_id': lid, 'focus': 'need'}

    if need['confirmed']:
        crits.append(_crit('bedarf', 'Bedarf', 30, 'passt', f"Vom Kunden bestätigt am {need['confirmed_at'][:10]}."))
    elif (d.get('problem') or '').strip():
        crits.append(_crit('bedarf', 'Bedarf', 30, 'teilweise', 'Problem notiert, vom Kunden noch nicht bestätigt.', act))
        questions.append('Habe ich das Problem richtig verstanden – und soll es gelöst werden?')
    else:
        crits.append(_crit('bedarf', 'Bedarf', 30, 'unbekannt', 'Kein Problem dokumentiert.', act))
        questions.append('Wie läuft das heute ab, und was stört daran?')

    bs = d.get('budget_status') or 'offen'
    if bs == 'budget_vorhanden':
        crits.append(_crit('budget', 'Budget', 20, 'passt', 'Budget vorhanden (laut Kunde).'))
    elif bs == 'freigabe_offen':
        crits.append(_crit('budget', 'Budget', 20, 'teilweise', 'Freigabe steht noch aus.', act))
        questions.append('Wer gibt das Budget frei, und bis wann?')
    elif bs == 'kein_budget':
        crits.append(_crit('budget', 'Budget', 20, 'passt_nicht', 'Kunde nennt kein Budget.'))
        ko.append({'key': 'budget', 'label': 'Kein Budget', 'detail': 'Laut Bedarfsanalyse ist kein Budget vorhanden – Wiedervorlage statt Angebot.'})
    else:
        crits.append(_crit('budget', 'Budget', 20, 'unbekannt', 'Budget nicht besprochen.', act))
        questions.append('In welchem Rahmen darf sich eine Lösung bewegen?')

    if (d.get('timing') or '').strip():
        crits.append(_crit('zeitpunkt', 'Zeitpunkt', 15, 'passt', 'Besprochen: ' + d['timing'].strip()[:120]))
    else:
        crits.append(_crit('zeitpunkt', 'Zeitpunkt', 15, 'unbekannt', 'Zeitrahmen nicht besprochen.', act))
        questions.append('Bis wann soll das Ergebnis da sein?')

    dm = conn.execute("SELECT SUM(verification_status='rolle_bestaetigt') AS ok, COUNT(*) AS n FROM decision_contacts WHERE lead_id=?", (lid,)).fetchone()
    if dm['ok']:
        crits.append(_crit('entscheider', 'Entscheider', 20, 'passt', 'Rolle einer Ansprechperson bestätigt.'))
    elif (d.get('decision_process') or '').strip():
        crits.append(_crit('entscheider', 'Entscheider', 20, 'teilweise', 'Entscheidungsweg notiert: ' + d['decision_process'].strip()[:120]))
    else:
        crits.append(_crit('entscheider', 'Entscheider', 20, 'unbekannt', 'Nicht geklärt, wer entscheidet.', act))
        questions.append('Wer entscheidet außer Ihnen mit?')

    value, ref = _order_value(conn, lid)
    if value is None:
        crits.append(_crit('auftragswert', 'Auftragswert', 15, 'unbekannt', 'Noch kein kalkuliertes Angebot.'))
    else:
        ok = value >= profile['min_order_eur']
        crits.append(_crit('auftragswert', 'Auftragswert', 15, 'passt' if ok else 'passt_nicht',
                           f"Angebot {ref}: {value:,.0f} € netto; Mindestauftrag {profile['min_order_eur']:,} €.".replace(',', '.')))

    last = conn.execute('SELECT outcome FROM calls WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lid,)).fetchone()
    if last and last['outcome'] == 'kein_bedarf':
        ko.append({'key': 'kein_bedarf', 'label': 'Kein Bedarf', 'detail': 'Im letzten Gespräch hat der Kunde keinen Bedarf genannt.'})

    passt = sum(1 for c in crits if c['status'] == 'passt')
    if ko:
        status, label, verdict = 'nicht_qualifiziert', 'nicht qualifiziert', 'Nicht weiterverfolgen: ' + '; '.join(k['label'] for k in ko)
    elif crits[0]['status'] == 'passt' and passt >= 3 and not any(c['status'] == 'passt_nicht' for c in crits):
        status, label, verdict = 'qualifiziert', 'qualifiziert', 'Bedarf bestätigt und die wichtigsten Punkte geklärt – Angebot lohnt sich.'
    else:
        status, label = 'teilweise', 'teilweise geklärt'
        verdict = f'{passt} von {len(crits)} Punkten geklärt – offene Fragen im nächsten Gespräch stellen.'
    return {'status': status, 'status_label': label, 'verdict': verdict, 'criteria': crits, 'knockouts': ko, 'questions': questions, 'talks': n_talks, 'notice': notice}


# ---------------------------------------------------------------- Erreichbarkeit

def slot_of(when=None):
    """Zeitfenster eines Anrufversuchs aus der lokalen Uhrzeit."""
    h = (when or dt.datetime.now()).hour
    return 'vormittag' if h < 11 else ('mittag' if h < 14 else ('nachmittag' if h < 17 else 'abend'))


def init_qualification(conn):
    """Schonende Schemaerweiterung: Zeitfenster je Anrufversuch, Verlustgrund am Lead."""
    cols = {r[1] for r in conn.execute('PRAGMA table_info(calls)')}
    if 'slot' not in cols:
        conn.execute("ALTER TABLE calls ADD COLUMN slot TEXT NOT NULL DEFAULT ''")
    cols = {r[1] for r in conn.execute('PRAGMA table_info(leads)')}
    for name in ('lost_reason', 'lost_note'):
        if name not in cols:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def attempts(conn, lead_id):
    """Vergebliche Anrufversuche seit dem letzten geführten Gespräch (neueste zuerst)."""
    out = []
    for r in conn.execute('SELECT outcome, slot, created_at FROM calls WHERE lead_id=? ORDER BY id DESC', (lead_id,)):
        if r['outcome'] not in MISSED:
            break
        out.append(dict(r))
    return out


def next_slot(conn, lead_id, tried):
    """Zeitfenster, in dem diese Firma schon erreicht wurde – sonst das erste noch nicht versuchte."""
    hit = conn.execute(f"SELECT slot FROM calls WHERE lead_id=? AND slot<>'' AND outcome NOT IN ({','.join('?' * len(MISSED))}) AND outcome<>'widerspruch' ORDER BY id DESC LIMIT 1",
                       (lead_id, *MISSED)).fetchone()
    if hit and hit['slot'] not in tried:
        return hit['slot'], 'dort wurde die Firma schon einmal erreicht'
    for s in SLOT_ORDER:
        if s not in tried:
            return s, 'noch nicht versucht'
    return SLOT_ORDER[0], 'alle Zeitfenster versucht'


def _workday(start, days):
    d = start
    while days > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d


def after_missed_call(conn, lead_id):
    """Nach „nicht erreicht“ / „Mailbox“: neuer Versuch zu anderer Tageszeit; nach max_attempts Kanalwechsel oder Parken.
    Legt nur Aufgaben und den nächsten Schritt an – keine Kontaktaufnahme."""
    from .workday import _advance, _lead, _today, ensure_task
    profile = load(conn)
    lead = _lead(conn, lead_id)
    tries = attempts(conn, lead_id)
    n = len(tries)
    for t in conn.execute("SELECT id FROM tasks WHERE lead_id=? AND done=0 AND title LIKE 'Erneut anrufen (%'", (lead_id,)).fetchall():
        conn.execute("UPDATE tasks SET done=1, done_at=datetime('now') WHERE id=?", (t['id'],))
    if n >= profile['max_attempts']:
        title = f'Nicht erreicht nach {n} Versuchen: Kanal wechseln (Brief) oder bis {(_today() + dt.timedelta(days=profile["park_days"])).strftime("%d.%m.%Y")} parken'
        ensure_task(conn, lead_id, title, 1)
        _advance(conn, lead, None, title, 1)
        return {'attempts': n, 'exhausted': True, 'task': title}
    slot, _why = next_slot(conn, lead_id, {t['slot'] for t in tries if t['slot']})
    due = _workday(_today(), profile['retry_days'])
    title = f'Erneut anrufen ({n + 1}. Versuch) – diesmal {SLOTS[slot]}'
    conn.execute('INSERT INTO tasks(lead_id, title, due_date) VALUES (?,?,?)', (lead_id, title, due.isoformat()))
    _advance(conn, lead, None, title, (due - _today()).days)
    return {'attempts': n, 'exhausted': False, 'task': title, 'due': due.isoformat(), 'slot': slot}


_DAYS = {'mo': 0, 'tu': 1, 'di': 1, 'we': 2, 'mi': 2, 'th': 3, 'do': 3, 'fr': 4, 'sa': 5, 'su': 6, 'so': 6}
_DAY_RE = r'(?:mo|tu|di|we|mi|th|do|fr|sa|su|so)'
_TIME_RE = re.compile(r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})')


def opening_schedule(text):
    """Öffnungszeiten im OpenStreetMap-Format → {wochentag: [(von_min, bis_min), …]} oder None, wenn nicht sicher lesbar.
    Verstanden wird das Übliche („Mo-Fr 08:00-12:00,13:00-17:00; Sa 09:00-12:00“, „24/7“, „Sa off“). Alles andere bleibt
    unbekannt – lieber keine Aussage als eine falsche."""
    text = (text or '').strip().lower()
    if not text:
        return None
    if text == '24/7':
        return {d: [(0, 1440)] for d in range(7)}
    sched = {}
    for rule in text.split(';'):
        rule = rule.strip()
        if not rule:
            continue
        if rule.startswith('ph'):  # Feiertage: nicht ausgewertet
            continue
        m = re.fullmatch(rf'((?:{_DAY_RE}(?:\s*-\s*{_DAY_RE})?)(?:\s*,\s*{_DAY_RE}(?:\s*-\s*{_DAY_RE})?)*)\s+(.+)', rule)
        if m:
            days_txt, rest = m.group(1), m.group(2).strip()
        elif _TIME_RE.match(rule):
            days_txt, rest = 'mo-su', rule
        else:
            return None
        days = set()
        for part in re.split(r'\s*,\s*', days_txt):
            a, _, b = [x.strip() for x in part.partition('-')]
            lo, hi = _DAYS[a], _DAYS[b] if b else _DAYS[a]
            days.update(range(lo, hi + 1) if lo <= hi else list(range(lo, 7)) + list(range(0, hi + 1)))
        if rest in ('off', 'closed'):
            spans = []
        else:
            spans = []
            for piece in re.split(r'\s*,\s*', rest):
                t = _TIME_RE.fullmatch(piece.strip())
                if not t:
                    return None
                h1, m1, h2, m2 = map(int, t.groups())
                if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
                    return None
                start, end = h1 * 60 + m1, h2 * 60 + m2
                if end <= start:
                    return None  # über Mitternacht: nicht ausgewertet
                spans.append((start, end))
        for d in days:
            sched[d] = spans
    return sched or None


def open_now(text, now=None):
    """True/False, wenn die Öffnungszeiten sicher lesbar sind; sonst None (unbekannt)."""
    sched = opening_schedule(text)
    if sched is None:
        return None
    now = now or dt.datetime.now()
    minute = now.hour * 60 + now.minute
    return any(a <= minute < b for a, b in sched.get(now.weekday(), []))


def osm_info(conn, lead_id):
    """Telefon und Öffnungszeiten aus dem lokalen OpenStreetMap-Bestand, falls die Firma von dort stammt. Ungeprüfte Angaben."""
    for r in conn.execute("SELECT external_id, source, sources_json FROM discovery_candidates WHERE lead_id=? ORDER BY id DESC LIMIT 5", (lead_id,)):
        ids = re.findall(r'openstreetmap\.org/((?:node|way|relation)/\d+)', r['sources_json'] or '')
        if r['source'] == 'osm' and r['external_id']:
            ids.insert(0, r['external_id'])
        for oid in ids:
            row = conn.execute('SELECT osm_id, phone, opening_hours FROM osm_places WHERE osm_id=?', (oid,)).fetchone()
            if row and (row['phone'] or row['opening_hours']):
                return dict(row)
    return None


def reachability(conn, lead, profile=None, lock=None, now=None):
    """Belegte Kontaktwege, bisherige Versuche und der nächste sinnvolle Versuch. Keine Erlaubnis zur Werbung."""
    from .sales_workspace import call_permission
    from .workday import contact_lock
    profile = profile or load(conn)
    lid = lead['id']
    lock = contact_lock(conn, lead) if lock is None else lock
    perm = call_permission(lead)
    address = ', '.join(x for x in (lead['street'], f"{lead['zip'] or ''} {lead['city'] or ''}".strip()) if x)
    src = 'Impressum' if lead['imprint_checked_at'] else 'eingetragen'
    channels = [
        {'key': 'telefon', 'label': 'Telefon (Zentrale)', 'value': lead['business_phone'] or '', 'known': bool(lead['business_phone']),
         'note': perm['reason']},
        {'key': 'email', 'label': 'E-Mail (allgemein)', 'value': lead['business_email'] or '', 'known': bool(lead['business_email']),
         'note': 'Werbliche E-Mail nur mit ausdrücklicher Einwilligung.' if lead['permission'] != 'opt_in' else 'Opt-in dokumentiert – Umfang prüfen.'},
        {'key': 'brief', 'label': 'Brief', 'value': address, 'known': bool(lead['street'] and lead['zip']),
         'note': 'Briefwerbung an Firmen ist grundsätzlich möglich, solange kein Widerspruch vorliegt.'},
    ]
    for c in channels:
        c['source'] = src if c['known'] else ''
        c['blocked'] = bool(lock)
    osm = osm_info(conn, lid)
    hours = None
    if osm:
        if osm['phone'] and not channels[0]['known']:  # nur wenn keine belegte Nummer vorliegt – nichts wird überschrieben
            channels[0].update(value=osm['phone'], known=True, source='OpenStreetMap (ungeprüft)')
        if osm['opening_hours']:
            state = open_now(osm['opening_hours'], now)
            hours = {'text': osm['opening_hours'], 'open_now': state, 'source': 'OpenStreetMap (ungeprüft)',
                     'label': 'jetzt geöffnet' if state else ('jetzt geschlossen' if state is False else 'Öffnungszeiten nicht sicher lesbar')}
    tries = attempts(conn, lid)
    total = conn.execute('SELECT COUNT(*) AS n, SUM(outcome NOT IN (?,?)) AS reached FROM calls WHERE lead_id=?', (*MISSED, lid)).fetchone()
    tried = {t['slot'] for t in tries if t['slot']}
    slot, why = next_slot(conn, lid, tried)
    exhausted = len(tries) >= profile['max_attempts']
    known = [c['label'] for c in channels if c['known']]
    if lock:
        status, hint = 'gesperrt', f'Kontaktsperre: Firma ist {lock}.'
    elif exhausted:
        status = 'ausgeschoepft'
        hint = f"{len(tries)} vergebliche Versuche – Kanal wechseln{' (Brief möglich)' if channels[2]['known'] else ''} oder parken."
    elif not known:
        status, hint = 'kein_weg', 'Kein Kontaktweg belegt – Impressum lesen lassen.'
    elif tries:
        status, hint = 'versuch_offen', f'{len(tries)} vergebliche(r) Versuch(e). Nächster Versuch {SLOTS[slot]} ({why}).'
    else:
        status, hint = 'bereit', 'Kontaktwege belegt: ' + ', '.join(known) + '. Vor dem Erstkontakt die Rechtsgrundlage dokumentieren.'
    return {'status': status, 'hint': hint, 'channels': channels, 'attempts_open': len(tries), 'attempts_total': total['n'] or 0,
            'reached_total': total['reached'] or 0, 'max_attempts': profile['max_attempts'], 'exhausted': exhausted,
            'next_slot': None if lock or exhausted else {'key': slot, 'label': SLOTS[slot], 'why': why},
            'history': [{'outcome': t['outcome'], 'slot': t['slot'], 'at': t['created_at']} for t in tries[:10]],
            'hours': hours,
            'notice': 'Ein belegter Kontaktweg ist keine Werbeerlaubnis (§ 7 UWG). Telefon und E-Mail im Einzelfall prüfen und dokumentieren.'}


def slot_stats(conn, min_calls=20):
    """Zu welcher Tageszeit wurden Firmen bisher erreicht? Erst ab min_calls Versuchen mit Zeitfenster aussagekräftig."""
    rows = {r['slot']: r for r in conn.execute(
        "SELECT slot, COUNT(*) AS n, SUM(outcome NOT IN (?,?)) AS reached FROM calls WHERE slot<>'' AND outcome<>'widerspruch' GROUP BY slot", MISSED)}
    n = sum(r['n'] for r in rows.values())
    out = [{'slot': s, 'label': SLOTS[s], 'calls': rows[s]['n'] if s in rows else 0, 'reached': (rows[s]['reached'] or 0) if s in rows else 0} for s in SLOTS]
    for o in out:
        o['rate_pct'] = round(100 * o['reached'] / o['calls']) if o['calls'] else None
    return {'calls': n, 'enough': n >= min_calls, 'slots': out,
            'notice': f'Auswertung ab {min_calls} Anrufversuchen; bisher {n}. Kleine Zahlen sagen wenig.' if n < min_calls else 'Eigene Anrufversuche nach Tageszeit.'}


# ---------------------------------------------------------------- Verlustgrund

def check_lost(row, data, reason, note):
    """Wechsel nach „verloren“ nur mit Grund. Gibt die zusätzlich zu speichernden Felder zurück."""
    if data.get('stage') != 'verloren' or row['stage'] == 'verloren':
        return {}
    if reason not in LOST_REASONS:
        raise ValueError('Bitte einen Verlustgrund angeben: ' + ', '.join(LOST_REASONS.values()) + '.')
    if not isinstance(note, str):
        raise ValueError('Notiz zum Verlustgrund muss Text sein.')
    if reason == 'sonstiges' and not note.strip():
        raise ValueError('Bei „Sonstiges“ bitte kurz notieren, woran es lag.')
    return {'lost_reason': reason, 'lost_note': note.strip()[:500]}


def lost_stats(conn):
    rows = conn.execute("SELECT lost_reason, COUNT(*) AS n FROM leads WHERE stage='verloren' GROUP BY lost_reason ORDER BY n DESC").fetchall()
    return [{'reason': r['lost_reason'], 'label': LOST_REASONS.get(r['lost_reason'], 'ohne Grund (vor dieser Version)'), 'count': r['n']} for r in rows]


# ---------------------------------------------------------------- Gesamtbild

def assessment(conn, lead, profile=None, now=None):
    from .workday import contact_lock
    profile = profile or load(conn)
    lock = contact_lock(conn, lead)
    f, q, r = fit(conn, lead, profile, lock), qualification(conn, lead, profile), reachability(conn, lead, profile, lock, now)
    if f['grade'] == 'X' or q['status'] == 'nicht_qualifiziert':
        headline = 'Nicht weiterverfolgen'
    elif q['status'] == 'qualifiziert':
        headline = 'Qualifiziert – Angebot vorbereiten'
    elif q['talks']:
        headline = 'Im Gespräch – offene Punkte klären'
    elif f['grade'] is None:
        headline = 'Erst recherchieren'
    else:
        headline = {'A': 'Vorrangig kontaktieren', 'B': 'Kontaktieren, wenn Zeit ist', 'C': 'Zurückstellen'}[f['grade']]
    return {'lead_id': lead['id'], 'company': lead['company'], 'stage': lead['stage'], 'headline': headline, 'fit': f, 'qualification': q, 'reachability': r}


GRADE_ORDER = {'A': 0, 'B': 1, None: 2, 'C': 3, 'X': 4}


def overview(conn):
    """Alle offenen Firmen mit Urteil – beste Passung zuerst, Unbekanntes vor „passt kaum“."""
    profile = load(conn)
    rows = []
    for lead in conn.execute("SELECT * FROM leads WHERE stage NOT IN ('gewonnen','verloren')"):
        a = assessment(conn, lead, profile)
        rows.append({'lead_id': a['lead_id'], 'company': a['company'], 'stage': a['stage'], 'headline': a['headline'], 'grade': a['fit']['grade'],
                     'score': a['fit']['score'], 'coverage_pct': a['fit']['coverage_pct'], 'qualification': a['qualification']['status'],
                     'reach': a['reachability']['status'], 'reach_hint': a['reachability']['hint'],
                     'knockouts': [k['label'] for k in a['fit']['knockouts'] + a['qualification']['knockouts']]})
    rows.sort(key=lambda r: (GRADE_ORDER[r['grade']], -(r['score'] or 0), r['company'].lower()))
    return {'leads': rows, 'profile': profile, 'profile_complete': bool(profile['industries'] and profile['home']),
            'lost_reasons': lost_stats(conn), 'slot_stats': slot_stats(conn)}


def route(h, conn, method, path):
    if path == '/api/profile/target':
        if method == 'GET':
            profile = load(conn)
        elif method == 'POST':
            profile = save(conn, h._body())
        else:
            return False
        h._send(200, {'profile': profile, 'industries': ind.catalog()['groups'], 'lost_reasons': LOST_REASONS, 'slots': SLOTS})
        return True
    if path == '/api/assessment' and method == 'GET':
        h._send(200, overview(conn))
        return True
    m = re.fullmatch(r'/api/leads/(\d+)/assessment', path)
    if m and method == 'GET':
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (int(m.group(1)),)).fetchone()
        if not lead:
            raise ValueError('Lead existiert nicht.')
        h._send(200, assessment(conn, lead))
        return True
    return False
