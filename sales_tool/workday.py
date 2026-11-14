"""Geführter Arbeitstag, Firmenakte und Freigaben (Masterplan 2.0, Sprint 5 – SignalDesk v1.18).

Abnahme laut Plan: Ein Nutzer führt den kompletten Beispieltag von der Recherche bis zum Angebotsentwurf ohne Sackgasse
durch; Kontaktsperren und alle manuell erforderlichen Freigaben greifen.

- **Kontaktsperre zentral** (`contact_lock`): Widerspruch, Phase „gesperrt“ oder ein Treffer auf der Sperrliste
  (Domain, Name, Registerangabe, E-Mail) sperren Anruf, Termin, Mail-Entwurf, Angebot und den Wechsel in Kontaktphasen.
  Ein Widerspruch lässt sich immer dokumentieren.
- **Bestätigter Bedarf** als manuelle Freigabe: nur nach einem dokumentierten Gespräch, mit Problem und Ziel aus der
  Bedarfsanalyse und den konkret bestätigten Leistungen aus dem Festpreis-Katalog. Erst dann darf ein Angebot als
  „beim Kunden“ oder „angenommen“ gelten; „Angebot aus bestätigtem Bedarf“ übernimmt genau diese Leistungen.
- **Firmenakte**: Ablauf Recherche → Kontaktweg → Gespräch → Termin → Bedarf → Angebot → Abschluss, nächster Schritt mit
  Direktsprung, Belegabdeckung des Scores und eine Zeitleiste aus allen Modulen.
- **Folgeaufgaben** nach jedem Schritt (ohne Dubletten) und **Tagesabschluss** mit Sackgassen-Prüfung.
Nichts wird versendet, niemand wird automatisch kontaktiert.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from .company_data import check_suppressed

CONTACT_STAGES = ('kontakt', 'antwort', 'termin', 'angebot', 'gewonnen')
OPEN_STAGES = ('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot')
CONFIRM_VIA = {'gespraech': 'im Telefonat', 'termin': 'im Termin', 'schriftlich': 'schriftlich (E-Mail/Brief des Kunden)'}
TALK_OUTCOMES = ('erreicht', 'termin_vereinbart', 'rueckruf_vereinbart', 'kein_bedarf')
STAGE_ORDER = {s: i for i, s in enumerate(('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot', 'gewonnen'))}


def init_workday(conn):
    cols = {r[1] for r in conn.execute('PRAGMA table_info(discovery)')}
    for name, decl in (('confirmed_at', "TEXT NOT NULL DEFAULT ''"), ('confirmed_via', "TEXT NOT NULL DEFAULT ''"),
                       ('confirmed_note', "TEXT NOT NULL DEFAULT ''"), ('needs_json', "TEXT NOT NULL DEFAULT '[]'")):
        if name not in cols:
            conn.execute(f'ALTER TABLE discovery ADD COLUMN {name} {decl}')
    tcols = {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
    if 'done_at' not in tcols:
        conn.execute("ALTER TABLE tasks ADD COLUMN done_at TEXT NOT NULL DEFAULT ''")
    conn.execute('''CREATE TABLE IF NOT EXISTS day_closings (
        day TEXT PRIMARY KEY, summary_json TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
        closed_at TEXT NOT NULL DEFAULT (datetime('now')))''')


def _today():
    return dt.date.today()


# ---------------------------------------------------------------- Kontaktsperre

def contact_lock(conn, lead):
    """Grund der Kontaktsperre oder ''. lead: Zeile/dict aus leads."""
    if lead['permission'] == 'nicht_kontaktieren' or lead['stage'] == 'gesperrt':
        return 'Widerspruch bzw. Sperre dokumentiert'
    hits = check_suppressed(conn, website=lead['website'], name=lead['company'], register_court=lead['register_court'],
                            register_number=lead['register_number'], email=lead['business_email'])
    if not hits and lead['legal_name']:
        hits = check_suppressed(conn, name=lead['legal_name'])
    if hits:
        return 'auf der Sperrliste (' + ', '.join(f"{h['kind']} „{h['display']}“" for h in hits[:3]) + ')'
    return ''


class ContactLocked(ValueError):
    status = 409


def assert_contact_allowed(conn, lead, what):
    reason = contact_lock(conn, lead)
    if reason:
        raise ContactLocked(f'Kontaktsperre: Firma ist {reason} – {what} nicht möglich.')


def check_stage_change(conn, lead, data):
    """Phasenwechsel prüfen: keine Kontaktphase bei Sperre; Sperre nur über die Sperrliste (mit Begründung) aufheben."""
    target = data.get('stage')
    after = {**dict(lead), **{k: v for k, v in data.items() if k in ('stage', 'permission', 'website', 'company', 'legal_name', 'business_email',
                                                                       'register_court', 'register_number')}}
    locked = contact_lock(conn, after)  # Zustand NACH der Änderung (Sperre ggf. gerade aufgehoben)
    if locked and target in CONTACT_STAGES:
        raise ContactLocked(f'Kontaktsperre: Firma ist {locked} – nicht in „{target}“ verschieben.')
    unlocking = (lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren') and (
        (target and target != 'gesperrt') or (data.get('permission') and data['permission'] != 'nicht_kontaktieren'))
    if unlocking:
        hits = check_suppressed(conn, website=lead['website'], name=lead['company'], register_court=lead['register_court'],
                                register_number=lead['register_number'], email=lead['business_email'])
        if hits:
            raise ContactLocked('Sperre zuerst unter „Import & Prüfung → Sperrliste“ mit Begründung aufheben (z. B. Einwilligung vom …).')
        if target and target in CONTACT_STAGES and data.get('permission', lead['permission']) == 'nicht_kontaktieren':
            raise ContactLocked('Erst den Kontaktstatus ändern (Widerspruch ist noch eingetragen).')


# ---------------------------------------------------------------- Bedarf bestätigen

def _lead(conn, lead_id):
    row = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        raise LookupError('Lead nicht gefunden.')
    return row


def _discovery(conn, lead_id, chance=None):
    """Bedarfsanalyse der Firma bzw. – seit 2.0.0-dev19 – einer weiteren Chance (gleiche Felder)."""
    from .chances import need_row
    opp = need_row(conn, lead_id, chance)
    if opp is not None:
        return dict(opp)
    row = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lead_id,)).fetchone()
    return dict(row) if row else None


def _chance_of(data):
    """Chance aus dem Anfrage-Körper (opportunity_id) – fehlt sie, gilt die Bedarfsanalyse der Firma."""
    return (data or {}).get('opportunity_id') if isinstance(data, dict) else None


def talks(conn, lead_id):
    """Dokumentierte Gespräche (Telefonat, Termin, Gesprächsnotiz)."""
    out = []
    for r in conn.execute(f"SELECT id, outcome, created_at FROM calls WHERE lead_id=? AND outcome IN ({','.join('?' * len(TALK_OUTCOMES))})",
                          (lead_id, *TALK_OUTCOMES)):
        out.append({'kind': 'call', 'id': r['id'], 'at': r['created_at']})
    for r in conn.execute("SELECT id, starts_at FROM meetings WHERE lead_id=? AND status='erledigt'", (lead_id,)):
        out.append({'kind': 'meeting', 'id': r['id'], 'at': r['starts_at']})
    for r in conn.execute("SELECT id, created_at FROM activities WHERE lead_id=? AND activity_type IN ('gespraech','anfrage')", (lead_id,)):
        out.append({'kind': 'activity', 'id': r['id'], 'at': r['created_at']})
    return out


def need_status(conn, lead_id, chance=None):
    d = _discovery(conn, lead_id, chance) or {}
    needs = json.loads(d.get('needs_json') or '[]')
    return {'confirmed': bool(d.get('confirmed_at')), 'confirmed_at': d.get('confirmed_at', ''), 'via': d.get('confirmed_via', ''),
            'note': d.get('confirmed_note', ''), 'needs': needs, 'problem': d.get('problem', ''), 'desired_outcome': d.get('desired_outcome', ''),
            'talks': len(talks(conn, lead_id))}


def _validate_needs(conn, needs):
    from .pricing import SERVICES, overrides, price_position, pricing_settings
    if not isinstance(needs, list) or not 1 <= len(needs) <= 20:
        raise ValueError('Bitte 1–20 bestätigte Leistungen aus dem Festpreis-Katalog angeben.')
    settings, ov = pricing_settings(conn), overrides(conn)
    out = []
    for n in needs:
        if not isinstance(n, dict) or n.get('service') not in SERVICES:
            raise ValueError('Unbekannte Leistung im bestätigten Bedarf.')
        pos = {k: n[k] for k in ('service', 'size', 'qty', 'note', 'km', 'minutes', 'trips', 'days') if k in n}
        price_position(pos, settings, ov)  # prüft Umfang/Menge wie im Angebot
        out.append(pos)
    return out


def confirm_need(conn, lead_id, data):
    """Manuelle Freigabe „Bedarf bestätigt“."""
    if not isinstance(data, dict) or set(data) - {'via', 'note', 'needs', 'opportunity_id'}:
        raise ValueError('Erwartet: {via, note, needs, opportunity_id?}.')
    from .chances import need_row
    chance = _chance_of(data)
    opp = need_row(conn, lead_id, chance)
    lead = _lead(conn, lead_id)
    assert_contact_allowed(conn, lead, 'Bedarf bestätigen')
    via = data.get('via')
    if via not in CONFIRM_VIA:
        raise ValueError('Wie wurde der Bedarf bestätigt? gespraech, termin oder schriftlich.')
    note = re.sub(r'\s+', ' ', str(data.get('note') or '')).strip()[:1000]
    if len(note) < 10:
        raise ValueError('Kurz festhalten, was der Kunde bestätigt hat (mind. 10 Zeichen).')
    d = _discovery(conn, lead_id, chance) or {}
    if not (d.get('problem') or '').strip() or not (d.get('desired_outcome') or '').strip():
        raise ValueError('Bedarfsanalyse zuerst ausfüllen: mindestens „Problem“ und „Gewünschtes Ergebnis“.')
    if via != 'schriftlich' and not talks(conn, lead_id):
        raise ValueError('Bedarf kann erst nach einem dokumentierten Gespräch bestätigt werden (Telefonat, erledigter Termin oder Gesprächsnotiz).')
    needs = _validate_needs(conn, data.get('needs'))
    now = dt.datetime.now().isoformat(timespec='seconds')
    if opp is not None:  # 2.0.0-dev19: Freigabe einer weiteren Chance
        conn.execute("""UPDATE opportunities SET confirmed_at=?, confirmed_via=?, confirmed_note=?, needs_json=?, updated_at=datetime('now')
                        WHERE id=?""", (now, via, note, json.dumps(needs, ensure_ascii=False), opp['id']))
    else:
        if not d:
            conn.execute('INSERT INTO discovery(lead_id) VALUES (?)', (lead_id,))
        conn.execute("""UPDATE discovery SET confirmed_at=?, confirmed_via=?, confirmed_note=?, needs_json=?, updated_at=datetime('now')
                        WHERE lead_id=?""", (now, via, note, json.dumps(needs, ensure_ascii=False), lead_id))
    from .pricing import SERVICES
    titles = ', '.join(SERVICES[n['service']]['title'] for n in needs)
    where = f" (Chance „{opp['title']}“)" if opp is not None else ''
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lead_id, 'bedarf', f'Bedarf{where} {CONFIRM_VIA[via]} bestätigt: {note} · Leistungen: {titles}'[:900]))
    step = 'Festpreisangebot aus bestätigtem Bedarf erstellen' + (f": {opp['title']}" if opp is not None else '')
    ensure_task(conn, lead_id, step, 2)
    _advance(conn, lead, 'termin', step, 2)
    from .chances import advance, first_chance
    target = opp['id'] if opp is not None else first_chance(conn, lead_id)
    advance(conn, target, 'termin')
    conn.commit()
    return need_status(conn, lead_id, chance)


def reopen_need(conn, lead_id, data):
    reason = re.sub(r'\s+', ' ', str((data or {}).get('reason') or '')).strip()[:500]
    if len(reason) < 5:
        raise ValueError('Begründung angeben, warum der Bedarf neu geklärt wird.')
    _lead(conn, lead_id)
    from .chances import need_row
    chance = _chance_of(data)
    opp = need_row(conn, lead_id, chance)
    if opp is not None:
        conn.execute("UPDATE opportunities SET confirmed_at='', updated_at=datetime('now') WHERE id=?", (opp['id'],))
    else:
        conn.execute("UPDATE discovery SET confirmed_at='', updated_at=datetime('now') WHERE lead_id=?", (lead_id,))
    where = f" (Chance „{opp['title']}“)" if opp is not None else ''
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)', (lead_id, 'bedarf', f'Bedarf{where} wieder offen: {reason}'))
    conn.commit()
    return need_status(conn, lead_id, chance)


def assert_need_confirmed(conn, lead_id, what, chance=None):
    if not need_status(conn, lead_id, chance)['confirmed']:
        raise ContactLocked(f'Freigabe fehlt: Bedarf ist noch nicht bestätigt – {what} erst nach „Bedarf bestätigen“ in der Firmenakte.')


def quote_from_need(conn, lead_id, data):
    """Angebotsentwurf mit genau den bestätigten Leistungen (Festpreise aus dem Katalog; interne Kalkulation bleibt intern)."""
    from .sales_workspace import make_proposal
    data = data or {}
    if set(data) - {'tax_mode', 'project_label', 'opportunity_id'}:
        raise ValueError('Erwartet: {tax_mode?, project_label?, opportunity_id?}.')
    chance = _chance_of(data)
    assert_need_confirmed(conn, lead_id, 'Angebot aus Bedarf', chance)
    st = need_status(conn, lead_id, chance)
    payload = {'lead_id': lead_id, 'positions': st['needs'], 'tax_mode': data.get('tax_mode', 'offen'),
               'customer_goal': st['desired_outcome'][:500], 'assumptions': f"Grundlage: Bedarf {CONFIRM_VIA.get(st['via'], '')} bestätigt am {st['confirmed_at'][:10]}."}
    if data.get('project_label'):
        payload['project_label'] = str(data['project_label'])[:140]
    if chance not in (None, ''):
        payload['opportunity_id'] = chance  # 2.0.0-dev19: Angebot gehört zur Chance, deren Bedarf bestätigt ist
    from .briefing import assumptions
    from .chances import first_chance
    oid = int(chance) if chance not in (None, '') else first_chance(conn, lead_id)
    brief = assumptions(conn, oid)[0] if oid else ''
    if brief:  # 2.0.0-dev20: geklärte Angaben und ausdrücklich offene Voraussetzungen aus dem Briefing
        payload['assumptions'] = f"{payload['assumptions']} {brief}"[:1000]
    return make_proposal(conn, payload)


# ---------------------------------------------------------------- Folgeaufgaben & Phasen

def ensure_task(conn, lead_id, title, days, action_type=None):
    """Legt eine Folgeaufgabe an, falls nicht schon eine offene mit gleichem Titel existiert."""
    if conn.execute('SELECT 1 FROM tasks WHERE lead_id=? AND title=? AND done=0', (lead_id, title)).fetchone():
        return None
    due = (_today() + dt.timedelta(days=days)).isoformat() if days is not None else ''
    return conn.execute('INSERT INTO tasks(lead_id, title, due_date) VALUES (?,?,?)', (lead_id, title, due)).lastrowid


# Automatisch gesetzte nächste Schritte – nur diese (oder ein leerer) werden ersetzt; was du selbst einträgst, bleibt stehen
AUTO_STEP_RE = re.compile(r'^(Firmen-Bericht erstellen|Kontaktweg klären|Festpreisangebot aus bestätigtem Bedarf|Vereinbarten Termin eintragen|'
                          r'Bedarf klären und Termin vereinbaren|Termin am .* danach Bedarf bestätigen|Bedarf aus dem Termin bestätigen|'
                          r'Angebot .* (prüfen und manuell versenden|nachfassen)|Erneut anrufen \(|Nicht erreicht nach |Projektstart .*: )')


def _advance(conn, lead, stage=None, next_step='', days=None):
    """Phase nur vorwärts, nie aus gesperrt/verloren/gewonnen; nächster Schritt nur, wenn leer oder automatisch gesetzt."""
    cur = lead['stage']
    upd = {}
    if stage and cur not in ('gesperrt', 'verloren', 'gewonnen') and STAGE_ORDER.get(stage, -1) > STAGE_ORDER.get(cur, -1):
        upd['stage'] = stage
    if next_step and cur not in ('gesperrt', 'verloren') and (not (lead['next_step'] or '').strip() or AUTO_STEP_RE.match(lead['next_step'])):
        upd['next_step'] = next_step[:300]
        upd['next_date'] = (_today() + dt.timedelta(days=days)).isoformat() if days is not None else ''
    if upd:
        conn.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in upd)}, updated_at=datetime('now') WHERE id=?", (*upd.values(), lead['id']))


def after_call(conn, lead_id, outcome):
    lead = _lead(conn, lead_id)
    if outcome == 'termin_vereinbart' and not conn.execute("SELECT 1 FROM meetings WHERE lead_id=? AND status IN ('geplant','bestaetigt')", (lead_id,)).fetchone():
        ensure_task(conn, lead_id, 'Vereinbarten Termin eintragen', 0)
        _advance(conn, lead, 'antwort', 'Vereinbarten Termin eintragen', 0)
    elif outcome == 'erreicht':
        _advance(conn, lead, 'antwort', 'Bedarf klären und Termin vereinbaren', 2)
    elif outcome == 'kein_bedarf':
        ensure_task(conn, lead_id, 'Kein Bedarf: Phase auf „verloren“ setzen oder Wiedervorlage in 6 Monaten', 1)


def after_meeting_created(conn, lead_id, starts_at):
    lead = _lead(conn, lead_id)
    day = starts_at[:10]
    try:
        before = max(0, (dt.date.fromisoformat(day) - _today()).days - 1)
    except ValueError:
        before = 0
    ensure_task(conn, lead_id, f'Termin am {day} vorbereiten: Firmenakte und Bericht lesen, Bedarfsfragen notieren', before)
    _advance(conn, lead, 'termin', f'Termin am {day} – danach Bedarf bestätigen', None)
    for t in conn.execute("SELECT id FROM tasks WHERE lead_id=? AND title='Vereinbarten Termin eintragen' AND done=0", (lead_id,)).fetchall():
        conn.execute("UPDATE tasks SET done=1, done_at=datetime('now') WHERE id=?", (t['id'],))


def after_meeting_done(conn, lead_id):
    lead = _lead(conn, lead_id)
    if not need_status(conn, lead_id)['confirmed']:
        ensure_task(conn, lead_id, 'Bedarf aus dem Termin bestätigen (Firmenakte)', 1)
        _advance(conn, lead, 'termin', 'Bedarf aus dem Termin bestätigen', 1)


def after_proposal(conn, lead_id, number):
    lead = _lead(conn, lead_id)
    for t in conn.execute("SELECT id FROM tasks WHERE lead_id=? AND title='Festpreisangebot aus bestätigtem Bedarf erstellen' AND done=0", (lead_id,)).fetchall():
        conn.execute("UPDATE tasks SET done=1, done_at=datetime('now') WHERE id=?", (t['id'],))
    _advance(conn, lead, None, f'Angebot {number} prüfen und manuell versenden', 1)  # Entwurf: Phase bleibt, erst Versand → „Angebot“


def after_proposal_sent(conn, lead_id, number, days=7, step=''):
    lead = _lead(conn, lead_id)
    _advance(conn, lead, 'angebot', step or f'Angebot {number} nachfassen (zulässigen Weg prüfen)', days)


# ---------------------------------------------------------------- Belegabdeckung

def evidence_coverage(conn, lead):
    """Wie viel vom Score ist belegt? Je Baustein belegt / teilweise / fehlt – mit Weg zum Beleg."""
    lid = lead['id']
    items = []
    facts = conn.execute("SELECT COUNT(*) FROM company_facts WHERE lead_id=? AND status='bestaetigt'", (lid,)).fetchone()[0]
    unchecked = conn.execute("SELECT COUNT(*) FROM company_facts WHERE lead_id=? AND status='ungeprueft'", (lid,)).fetchone()[0]
    items.append({'key': 'firmendaten', 'label': 'Firmendaten (Impressum/Register)', 'weight': 20,
                  'value': 1.0 if facts >= 2 else (0.5 if facts or unchecked else 0.0),
                  'detail': f'{facts} bestätigt, {unchecked} ungeprüft' if facts or unchecked else 'kein Beleg',
                  'action': {'label': 'Firmen-Bericht', 'view': 'report', 'lead_id': lid}})
    ws = conn.execute('SELECT coverage, overall FROM website_scores WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lid,)).fetchone()
    items.append({'key': 'website', 'label': 'Website-Bewertung', 'weight': 25, 'value': round((ws['coverage'] or 0) / 100, 2) if ws else 0.0,
                  'detail': f"Bewertung {ws['overall'] if ws['overall'] is not None else '–'}, {ws['coverage']} % der Kriterien belegt" if ws else 'nicht bewertet',
                  'action': {'label': 'Website bewerten', 'view': 'report', 'lead_id': lid}})
    sig = conn.execute("SELECT COUNT(*) FROM buying_signals WHERE lead_id=? AND status='bestaetigt'", (lid,)).fetchone()[0]
    has_src = bool((lead['signal_source'] or '').startswith('http'))
    items.append({'key': 'anlass', 'label': 'Anlass/Kaufsignal mit Quelle', 'weight': 20,
                  'value': 1.0 if sig or has_src else (0.3 if lead['signal_note'] else 0.0),
                  'detail': f'{sig} bestätigte Signale' if sig else ('Quelle verlinkt' if has_src else ('Notiz ohne Quelle' if lead['signal_note'] else 'kein Anlass belegt')),
                  'action': {'label': 'Kaufsignale prüfen', 'view': 'signals', 'lead_id': lid}})
    route_ok = lead['contact_route'] not in ('', 'unbekannt') or (lead['permission'] not in ('', 'unbekannt') and lead['permission_evidence'])
    items.append({'key': 'kontaktweg', 'label': 'Kontaktweg & Rechtsgrundlage', 'weight': 15, 'value': 1.0 if route_ok else 0.0,
                  'detail': 'dokumentiert' if route_ok else 'offen', 'action': {'label': 'Kontaktweg klären', 'view': 'lead', 'lead_id': lid}})
    ns = need_status(conn, lid)
    items.append({'key': 'bedarf', 'label': 'Bedarf (vom Kunden bestätigt)', 'weight': 20,
                  'value': 1.0 if ns['confirmed'] else (0.4 if ns['problem'] else 0.0),
                  'detail': f"bestätigt am {ns['confirmed_at'][:10]}" if ns['confirmed'] else ('Analyse begonnen' if ns['problem'] else 'offen'),
                  'action': {'label': 'Bedarf klären', 'view': 'lead', 'lead_id': lid}})
    total = sum(i['weight'] for i in items)
    pct = round(100 * sum(i['weight'] * i['value'] for i in items) / total)
    return {'pct': pct, 'items': items, 'missing': [i['label'] for i in items if i['value'] < 0.5],
            'notice': 'Belegabdeckung: Anteil des Scores, der durch geprüfte Quellen gedeckt ist – kein Maß für Kaufwahrscheinlichkeit.'}


# ---------------------------------------------------------------- Firmenakte

def _steps(conn, lead, lock):
    lid = lead['id']
    report = conn.execute("SELECT status FROM company_reports WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lid,)).fetchone()
    researched = bool(report and report['status'] == 'done') or bool(conn.execute(
        "SELECT 1 FROM website_scores WHERE lead_id=? UNION SELECT 1 FROM company_facts WHERE lead_id=? AND status='bestaetigt' LIMIT 1", (lid, lid)).fetchone())
    route_ok = lead['contact_route'] not in ('', 'unbekannt') or (lead['permission'] not in ('', 'unbekannt') and bool(lead['permission_evidence']))
    talked = bool(talks(conn, lid))
    meeting = conn.execute("SELECT status, starts_at FROM meetings WHERE lead_id=? AND status<>'abgesagt' ORDER BY starts_at DESC LIMIT 1", (lid,)).fetchone()
    ns = need_status(conn, lid)
    props = conn.execute('SELECT id, number, status FROM proposals WHERE lead_id=? ORDER BY id DESC', (lid,)).fetchall()
    sent = next((p for p in props if p['status'] in ('gesendet_manuell', 'angenommen')), None)
    won = lead['stage'] == 'gewonnen' or any(p['status'] == 'angenommen' for p in props)
    invoiced = bool(conn.execute("SELECT 1 FROM invoices WHERE lead_id=? AND status<>'entwurf' LIMIT 1", (lid,)).fetchone())
    S = []

    def step(key, label, done, detail, action, partial=False):
        S.append({'key': key, 'label': label, 'done': bool(done), 'partial': bool(partial and not done), 'detail': detail, 'action': action})
    step('recherche', 'Recherche', researched, 'Bericht/Belege liegen vor' if researched else ('Bericht läuft' if report and report['status'] in ('queued', 'running') else 'noch kein Bericht'),
         {'label': 'Firmen-Bericht erstellen' if not report else 'Bericht öffnen', 'view': 'report', 'lead_id': lid, 'open_only': bool(report)},
         partial=bool(report))
    step('kontaktweg', 'Kontaktweg geklärt', route_ok, 'Weg und Grundlage dokumentiert' if route_ok else 'Weg/Rechtsgrundlage offen',
         {'label': 'Kontaktstatus dokumentieren', 'view': 'lead', 'lead_id': lid, 'focus': 'permission'})
    step('gespraech', 'Gespräch', talked, 'dokumentiert' if talked else 'noch kein Gespräch',
         {'label': 'Gespräch dokumentieren', 'view': 'workspace', 'section': 'contact', 'lead_id': lid})
    step('termin', 'Termin', meeting and meeting['status'] == 'erledigt',
         (f"{meeting['starts_at'].replace('T', ' ')} · {meeting['status']}" if meeting else 'kein Termin'),
         {'label': 'Termin eintragen' if not meeting else 'Termin als erledigt markieren', 'view': 'workspace', 'section': 'meeting', 'lead_id': lid},
         partial=bool(meeting))
    step('bedarf', 'Bedarf bestätigt', ns['confirmed'], f"am {ns['confirmed_at'][:10]}" if ns['confirmed'] else ('Analyse begonnen' if ns['problem'] else 'offen'),
         {'label': 'Bedarf bestätigen', 'view': 'lead', 'lead_id': lid, 'focus': 'need'}, partial=bool(ns['problem']))
    step('angebot', 'Festpreisangebot', bool(sent), (f"{sent['number']} beim Kunden" if sent else (f"{props[0]['number']} als Entwurf" if props else 'kein Angebot')),
         ({'label': 'Angebot öffnen', 'view': 'quotes', 'lead_id': lid, 'ref': props[0]['id']} if props else
          {'label': 'Angebot aus bestätigtem Bedarf', 'view': 'quote_from_need', 'lead_id': lid}), partial=bool(props))
    step('abschluss', 'Abschluss', won and invoiced, 'gewonnen' + (' · abgerechnet' if invoiced else ' · Rechnung offen') if won else 'offen',
         {'label': 'Rechnung schreiben', 'view': 'accounting', 'lead_id': lid}, partial=won)
    # Nächster Schritt: erster offener Schritt in sinnvoller Reihenfolge – mit Sperre/Freigabe-Regeln
    nxt = None
    if lock:
        nxt = {'label': 'Kontaktsperre – keine Ansprache', 'detail': lock, 'action': None, 'blocked': True}
    elif lead['stage'] == 'verloren':
        nxt = {'label': 'Verloren – keine Aktion nötig', 'detail': 'Bei neuem Anlass Phase zurücksetzen.', 'action': None}
    else:
        for s in S:
            if s['done']:
                continue
            if s['key'] == 'termin' and ns['confirmed']:
                continue  # Bedarf auch ohne Termin bestätigt (z. B. im Telefonat)
            if s['key'] == 'gespraech' and not route_ok and not S[1]['done']:
                s = S[1]
            if s['key'] == 'angebot' and not ns['confirmed'] and not props:
                s = S[4]
            nxt = {'label': s['action']['label'], 'detail': s['detail'], 'action': s['action'], 'step': s['key']}
            break
        nxt = nxt or {'label': 'Alles erledigt', 'detail': 'Abgeschlossen und abgerechnet.', 'action': None}
    return S, nxt


def _ev(at, kind, title, detail='', ref=None):
    return {'at': str(at or '')[:19].replace('T', ' '), 'kind': kind, 'title': title, 'detail': (detail or '')[:400], 'ref': ref}


def timeline(conn, lead_id, limit=200):
    T = []
    q = lambda sql: conn.execute(sql, (lead_id,)).fetchall()
    for r in q('SELECT * FROM activities WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'aktivitaet', {'notiz': 'Notiz', 'gespraech': 'Gespräch', 'anfrage': 'Anfrage', 'angebot': 'Angebot',
                                                    'einwand': 'Einwand', 'abschluss': 'Abschluss', 'widerspruch': 'Widerspruch',
                                                    'bedarf': 'Bedarf'}.get(r['activity_type'], r['activity_type']), r['detail']))
    for r in q('SELECT * FROM calls WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'anruf', 'Telefonat: ' + r['outcome'].replace('_', ' '), r['notes'] + (f" · Rückruf {r['callback_date']}" if r['callback_date'] else ''), r['id']))
    for r in q('SELECT * FROM meetings WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'termin', f"Termin eingetragen: {r['title']}", f"{r['starts_at'].replace('T', ' ')} · {r['status']}", r['id']))
    for r in q('SELECT * FROM proposals WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'angebot', f"Angebot {r['number'] or '#' + str(r['id'])} erstellt", f"Status: {r['status']}", r['id']))
        if r['status'] != 'entwurf' and r['updated_at'] != r['created_at']:
            T.append(_ev(r['updated_at'], 'angebot', f"Angebot {r['number'] or '#' + str(r['id'])}: {r['status'].replace('_', ' ')}", '', r['id']))
    for r in q('SELECT * FROM mail_drafts WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'mail', f"Mail-Entwurf: {r['subject']}", f"Anlass: {r['contact_basis']} (nicht versendet)", r['id']))
    for r in q('SELECT * FROM tasks WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'aufgabe', f"Aufgabe: {r['title']}", (f"fällig {r['due_date']}" if r['due_date'] else 'ohne Termin') + (' · erledigt' if r['done'] else ''), r['id']))
    for r in q('SELECT * FROM company_reports WHERE lead_id=?'):
        T.append(_ev(r['finished_at'] or r['created_at'], 'bericht', f"Firmen-Bericht: {r['status']}", '', r['id']))
    for r in q("SELECT date(found_at) AS d, COUNT(*) AS n, SUM(status='bestaetigt') AS ok FROM company_facts WHERE lead_id=? GROUP BY date(found_at)"):
        T.append(_ev(r['d'], 'beleg', f"{r['n']} Firmendaten mit Beleg", f"{r['ok'] or 0} bestätigt"))
    for r in q('SELECT * FROM website_scores WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'bewertung', f"Website-Bewertung {r['overall'] if r['overall'] is not None else '–'}", f"{r['coverage']} % belegt", r['id']))
    for r in q('SELECT * FROM buying_signals WHERE lead_id=?'):
        T.append(_ev(r['found_at'], 'signal', f"Kaufsignal: {r['title']}", r['status'], r['id']))
    for r in q('SELECT * FROM invoices WHERE lead_id=?'):
        T.append(_ev(r['created_at'], 'rechnung', f"Rechnung {r['number'] or 'Entwurf'}", r['status'], r['id']))
    for r in q('SELECT * FROM discovery_candidates WHERE lead_id=?'):
        srcs = ', '.join(s.get('source', '') for s in json.loads(r['sources_json'] or '[]')) if 'sources_json' in r.keys() else r['source']
        T.append(_ev(r['created_at'], 'fund', 'Aus der Sichtung übernommen', f'Quellen: {srcs or r["source"]}', r['id']))
    T.sort(key=lambda e: e['at'], reverse=True)
    return T[:limit]


def lead_file(conn, lead_id):
    from .model import as_lead
    lead = _lead(conn, lead_id)
    lock = contact_lock(conn, lead)
    steps, nxt = _steps(conn, lead, lock)
    open_tasks = [dict(r) for r in conn.execute("SELECT id, title, due_date FROM tasks WHERE lead_id=? AND done=0 ORDER BY (due_date=''), due_date", (lead_id,))]
    lv = as_lead(lead)
    from .lead_imprint import status as company_data_status
    from .qualification import assessment
    privacy = [dict(r) for r in conn.execute("""SELECT id, kind, retention_until, art14_informed_at FROM privacy_records
                                                WHERE lead_id=? AND kind='einzelunternehmen'""", (lead_id,))]
    return {'privacy': privacy, 'company_data': company_data_status(conn, lead_id),
            'lead': {k: lv[k] for k in ('id', 'company', 'stage', 'permission', 'contact_route', 'website', 'location', 'next_step', 'next_date', 'score')},
            'score_reasons': lv['score_reasons'], 'lock': lock, 'steps': steps, 'next': nxt, 'need': need_status(conn, lead_id),
            'assessment': assessment(conn, lead), 'coverage': evidence_coverage(conn, lead), 'open_tasks': open_tasks, 'timeline': timeline(conn, lead_id)}


# ---------------------------------------------------------------- Tagesabschluss

def dead_ends(conn):
    """Offene Firmen in Kontaktphasen ohne nächsten Schritt mit Datum und ohne offene Aufgabe – würden sonst liegen bleiben."""
    out = []
    for r in conn.execute("""SELECT l.* FROM leads l WHERE l.stage IN ('qualifiziert','kontakt','antwort','termin','angebot')
                             AND (l.next_date='' OR l.next_date IS NULL)
                             AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.lead_id=l.id AND t.done=0 AND t.due_date<>'')
                             AND NOT EXISTS (SELECT 1 FROM meetings m WHERE m.lead_id=l.id AND m.status IN ('geplant','bestaetigt'))
                             ORDER BY l.updated_at DESC LIMIT 100"""):
        if contact_lock(conn, r):
            continue
        out.append({'lead_id': r['id'], 'company': r['company'], 'stage': r['stage'], 'next_step': r['next_step']})
    return out


def day_summary(conn, day=None, db_path=None):
    day = day or _today().isoformat()
    one = lambda sql, *a: conn.execute(sql, (day, *a)).fetchone()[0]
    done = {
        'neue_leads': one("SELECT COUNT(*) FROM leads WHERE date(created_at)=?"),
        'gesichtet': one("SELECT COUNT(*) FROM discovery_candidates WHERE date(updated_at)=? AND status IN ('uebernommen','verworfen','zusammengefuehrt','dublette')"),
        'berichte': one("SELECT COUNT(*) FROM company_reports WHERE date(finished_at)=? AND status='done'"),
        'telefonate': one("SELECT COUNT(*) FROM calls WHERE date(created_at)=?"),
        'termine_eingetragen': one("SELECT COUNT(*) FROM meetings WHERE date(created_at)=?"),
        'bedarf_bestaetigt': one("SELECT COUNT(*) FROM discovery WHERE date(confirmed_at)=?"),
        'angebote': one("SELECT COUNT(*) FROM proposals WHERE date(created_at)=?"),
        'aufgaben_erledigt': one("SELECT COUNT(*) FROM tasks WHERE date(done_at)=?"),
    }
    tomorrow = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    overdue = conn.execute("""SELECT COUNT(*) FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id WHERE t.done=0 AND t.due_date<>'' AND t.due_date<=?
                              AND (l.id IS NULL OR l.stage NOT IN ('gesperrt','verloren'))""", (day,)).fetchone()[0]
    due_tomorrow = conn.execute("SELECT COUNT(*) FROM tasks WHERE done=0 AND due_date=?", (tomorrow,)).fetchone()[0]
    meetings_tomorrow = [dict(r) for r in conn.execute("""SELECT m.id, m.title, m.starts_at, l.company, m.lead_id FROM meetings m JOIN leads l ON l.id=m.lead_id
                                                          WHERE date(m.starts_at)=? AND m.status IN ('geplant','bestaetigt') ORDER BY m.starts_at""", (tomorrow,))]
    drafts = [dict(r) for r in conn.execute("""SELECT p.id, p.number, l.company, p.lead_id FROM proposals p JOIN leads l ON l.id=p.lead_id
                                               WHERE p.status='entwurf' AND p.superseded_by IS NULL ORDER BY p.id DESC LIMIT 20""")]
    backup = None
    if db_path:
        from .accounting_api import list_backups
        b = list_backups(db_path)['backups']
        backup = b[0]['modified'] if b else ''
    closed = conn.execute('SELECT closed_at, note FROM day_closings WHERE day=?', (day,)).fetchone()
    return {'day': day, 'done': done, 'open': {'ueberfaellig': overdue, 'morgen_faellig': due_tomorrow, 'angebotsentwuerfe': len(drafts)},
            'meetings_tomorrow': meetings_tomorrow, 'drafts': drafts, 'dead_ends': (de := dead_ends(conn)), 'dead_ends_capped': len(de) >= 100,
            'last_backup': backup,
            'backup_today': bool(backup and backup[:10] == day), 'closed': dict(closed) if closed else None,
            'notice': 'Tagesabschluss: jede offene Firma braucht einen nächsten Schritt mit Datum – sonst bleibt sie liegen.'}


def close_day(conn, data, db_path=None):
    data = data or {}
    if set(data) - {'note', 'backup', 'followups'}:
        raise ValueError('Erwartet: {note?, backup?, followups?}.')
    followups = data.get('followups') or []
    if not isinstance(followups, list) or len(followups) > 100:
        raise ValueError('followups: Liste mit {lead_id, date, step}.')
    for f in followups:  # Sackgassen schließen: nächsten Schritt mit Datum setzen
        if not isinstance(f, dict) or set(f) - {'lead_id', 'date', 'step'}:
            raise ValueError('followups: {lead_id, date, step}.')
        try:
            d = dt.date.fromisoformat(str(f.get('date')))
        except ValueError as exc:
            raise ValueError('Datum als JJJJ-MM-TT.') from exc
        lead = _lead(conn, f.get('lead_id'))
        step = re.sub(r'\s+', ' ', str(f.get('step') or 'Wiedervorlage')).strip()[:300]
        conn.execute("UPDATE leads SET next_step=?, next_date=?, updated_at=datetime('now') WHERE id=?", (step, d.isoformat(), lead['id']))
    backup = None
    if data.get('backup') is True and db_path:
        conn.commit()
        from .accounting_api import create_backup
        backup = create_backup(db_path)['path']
    s = day_summary(conn, db_path=db_path)
    note = re.sub(r'\s+', ' ', str(data.get('note') or '')).strip()[:1000]
    conn.execute('INSERT OR REPLACE INTO day_closings(day, summary_json, note, closed_at) VALUES (?,?,?,datetime(\'now\'))',
                 (s['day'], json.dumps(s, ensure_ascii=False, default=str), note))
    conn.commit()
    s = day_summary(conn, db_path=db_path)
    s['backup_path'] = backup
    return s


# ---------------------------------------------------------------- Routen

def route_workday(h, conn, method, route, query, db_path):
    m = re.fullmatch(r'/api/leads/(\d+)/(file|need|need/confirm|need/reopen|quote-from-need)', route)
    if m:
        lid, what = int(m.group(1)), m.group(2)
        if what == 'file' and method == 'GET':
            h._send(200, lead_file(conn, lid))
            return True
        if what == 'need' and method == 'GET':
            _lead(conn, lid)
            h._send(200, need_status(conn, lid, (query.get('chance') or [None])[0]))
            return True
        if what == 'need/confirm' and method == 'POST':
            h._send(200, confirm_need(conn, lid, h._body()))
            return True
        if what == 'need/reopen' and method == 'POST':
            h._send(200, reopen_need(conn, lid, h._body()))
            return True
        if what == 'quote-from-need' and method == 'POST':
            body = h._body() if h.headers.get('Content-Length', '0') not in ('0', '') else {}
            h._send(201, quote_from_need(conn, lid, body))
            return True
    if route == '/api/today/close':
        if method == 'GET':
            h._send(200, day_summary(conn, db_path=db_path))
            return True
        if method == 'POST':
            h._send(200, close_day(conn, h._body(), db_path))
            return True
    return False
