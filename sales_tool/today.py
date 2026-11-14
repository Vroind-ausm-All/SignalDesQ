"""Tagesansicht „Heute“ (Sprint A): der Arbeitstag von oben nach unten.

1. Tagesplan – die ersten Schritte in sinnvoller Reihenfolge, jeweils mit Anzahl und Direktsprung.
2. Wiedervorlage – fällige und angefangene Dinge: Aufgaben, nächste Schritte, vereinbarte Rückrufe,
   Angebote zum Nachfassen oder Fertigstellen, begonnene Bedarfsanalysen, Termine, offene Freigaben.
3. Offenes Potenzial – aus kalkulierten Angeboten statt aus Schätzungen; Schätzungen ohne Angebot getrennt.
4. Pipeline – jede Phase mit Anzahl, Wert und der Aktion, die als Nächstes ansteht.
5. Funktionsstatus – was gerade funktioniert und was eine Voraussetzung braucht.

Es wird nichts versendet und niemand kontaktiert.
"""
from __future__ import annotations

import datetime as dt
import json
import re

OPEN_STAGES = ('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot')
STAGE_ACTIONS = {
    'recherche': {'label': 'Firmen-Berichte erstellen', 'view': 'center', 'hint': 'Ein Klick: Impressum, Website, Inhalte, Ansprechpartner, Signale'},
    'qualifiziert': {'label': 'Kontaktweg klären', 'view': 'leads', 'hint': 'Zulässigen Weg und Rechtsgrundlage dokumentieren'},
    'kontakt': {'label': 'Kontakt aufnehmen', 'view': 'workspace', 'section': 'contact', 'hint': 'Freigabe prüfen, Anruf oder Nachricht vorbereiten'},
    'antwort': {'label': 'Termin vereinbaren', 'view': 'workspace', 'section': 'meeting', 'hint': 'Rückmeldung in einen Gesprächstermin verwandeln'},
    'termin': {'label': 'Termine vereinbaren & vorbereiten', 'view': 'workspace', 'section': 'meeting', 'hint': 'Dossier lesen, Bedarfsanalyse im Gespräch ausfüllen'},
    'angebot': {'label': 'Angebot nachfassen', 'view': 'quotes', 'hint': 'Vereinbarte Rückmeldung einholen'},
    'gewonnen': {'label': 'Rechnung schreiben', 'view': 'accounting', 'hint': 'Aus dem Angebot eine Rechnung erstellen'},
}
STAGE_LABELS = {'recherche': 'Recherche', 'qualifiziert': 'Qualifiziert', 'kontakt': 'Kontakt geprüft', 'antwort': 'Rückmeldung',
                'termin': 'Termin', 'angebot': 'Angebot', 'gewonnen': 'Gewonnen'}


def _net(row):
    try:
        return float(json.loads(row['customer_json']).get('net_eur') or 0)
    except (ValueError, TypeError):
        return 0.0


def _label(row):
    try:
        return json.loads(row['customer_json']).get('project_label') or ''
    except ValueError:
        return ''


def _days_since(ts, today):
    try:
        return (today - dt.date.fromisoformat(str(ts)[:10])).days
    except ValueError:
        return 0


def wiedervorlage(conn, today=None):
    today = today or dt.date.today()
    t, tomorrow = today.isoformat(), (today + dt.timedelta(days=1)).isoformat()
    items = []

    def add(kind, title, company, lead_id, due, action, view, ref=None, detail='', section=None):
        items.append({'kind': kind, 'title': title, 'company': company or 'Allgemein', 'lead_id': lead_id, 'due': due or '',
                      'overdue': bool(due and due < t), 'action': action, 'view': view, 'section': section, 'ref': ref, 'detail': detail})

    open_filter = "(l.id IS NULL OR l.stage NOT IN ('gesperrt','verloren'))"
    for r in conn.execute(f"""SELECT t.*, l.company FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id
                              WHERE t.done=0 AND t.due_date<>'' AND t.due_date<=? AND {open_filter} ORDER BY t.due_date""", (t,)):
        needs = r['permission_status'] == 'zu_pruefen'
        add('aufgabe', r['title'], r['company'], r['lead_id'], r['due_date'], 'Freigabe prüfen' if needs else 'Erledigen',
            'workspace' if needs else 'tasks', r['id'], 'Kontaktaktion – erst Freigabe dokumentieren' if needs else '', 'permissions' if needs else None)
    research = 0
    for r in conn.execute("""SELECT id, company, next_step, next_date FROM leads WHERE next_step<>'' AND next_date<>'' AND next_date<=?
                             AND stage NOT IN ('gewonnen','verloren','gesperrt') ORDER BY next_date""", (t,)):
        if RESEARCH_RE.search(r['next_step']):
            research += 1  # v1.13: Recherche-Schritte nicht einzeln, sondern als ein Sammelpunkt
            continue
        if any(i['lead_id'] == r['id'] and i['title'] == r['next_step'] for i in items):
            continue  # 2.0.0-dev23: derselbe Schritt steht schon als fällige Aufgabe da (z. B. Nachfassen eines Angebots)
        add('naechster_schritt', r['next_step'], r['company'], r['id'], r['next_date'], 'Lead öffnen', 'lead', r['id'])
    if research:
        add('recherche', f'{research} Firma(en) mit fälligem Recherche-Schritt', 'Recherche', None, t, 'Gesammelt ansehen', 'tasks',
            detail='Am schnellsten: Firmen-Berichte für alle auf einmal erstellen')
    # 2.0.0-dev19 (M13 Teil 2): fällige nächste Schritte einzelner Chancen – ohne Doppelung mit dem Schritt der Firma
    for r in conn.execute("""SELECT o.id, o.title, o.next_step, o.next_date, l.id AS lead_id, l.company, l.next_step AS lead_step
                             FROM opportunities o JOIN leads l ON l.id=o.lead_id
                             WHERE o.stage IN ('bedarf','termin','angebot') AND o.next_step<>'' AND o.next_date<>'' AND o.next_date<=?
                             AND l.stage NOT IN ('gesperrt','verloren') ORDER BY o.next_date""", (t,)):
        if r['next_step'].strip() == (r['lead_step'] or '').strip():
            continue
        add('naechster_schritt', f"{r['title']}: {r['next_step']}", r['company'], r['lead_id'], r['next_date'], 'Firma öffnen', 'lead', r['lead_id'],
            'Nächster Schritt einer Chance')
    for r in conn.execute("""SELECT c.*, l.company FROM calls c JOIN leads l ON l.id=c.lead_id
                             WHERE c.outcome='rueckruf_vereinbart' AND c.callback_date<>'' AND c.callback_date<=? AND l.stage NOT IN ('gesperrt','verloren')
                             AND l.permission<>'nicht_kontaktieren'
                             AND NOT EXISTS (SELECT 1 FROM calls c2 WHERE c2.lead_id=c.lead_id AND c2.id>c.id)
                             ORDER BY c.callback_date""", (tomorrow,)):
        add('rueckruf', 'Vereinbarten Rückruf wahrnehmen', r['company'], r['lead_id'], r['callback_date'], 'Anruf dokumentieren', 'workspace',
            r['id'], (r['notes'] or '')[:140], 'contact')
    for r in conn.execute("""SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id
                             WHERE p.superseded_by IS NULL AND p.status IN ('entwurf','gesendet_manuell') AND l.stage NOT IN ('gesperrt','verloren') ORDER BY p.updated_at"""):
        age = _days_since(r['updated_at'], today)
        expires = r['valid_until'] or ''
        linked = conn.execute('SELECT 1 FROM tasks WHERE proposal_id=? LIMIT 1', (r['id'],)).fetchone()  # 2.0.0-dev23 (M16)
        if r['status'] == 'gesendet_manuell' and age >= 7 and not linked:
            add('nachfassen', f"Angebot {r['number'] or '#' + str(r['id'])} nachfassen", r['company'], r['lead_id'], '', 'Angebot öffnen', 'quotes',
                r['id'], f"seit {age} Tagen beim Kunden · {_net(r):,.0f} € netto".replace(',', '.'))
        elif r['status'] == 'entwurf' and age >= 2:
            add('angebot_entwurf', f"Angebotsentwurf {r['number'] or '#' + str(r['id'])} fertigstellen", r['company'], r['lead_id'], '', 'Angebot öffnen',
                'quotes', r['id'], f"Entwurf seit {age} Tagen · {_label(r)}")
        if expires and t <= expires <= (today + dt.timedelta(days=7)).isoformat():
            add('angebot_frist', f"Bindefrist von Angebot {r['number'] or '#' + str(r['id'])} endet", r['company'], r['lead_id'], expires,
                'Angebot öffnen', 'quotes', r['id'], 'Verlängern oder Rückmeldung einholen')
    for r in conn.execute("""SELECT d.*, l.company FROM discovery d JOIN leads l ON l.id=d.lead_id
                             WHERE l.stage IN ('kontakt','antwort','termin','angebot','qualifiziert')"""):
        answered = sum(bool((r[f] or '').strip()) for f in ('problem', 'impact', 'desired_outcome', 'timing', 'decision_process'))
        if 0 < answered < 5:
            add('bedarfsanalyse', 'Begonnene Bedarfsanalyse vervollständigen', r['company'], r['lead_id'], '', 'Lead öffnen', 'lead', r['lead_id'],
                f'{answered} von 5 Kernfragen beantwortet')
    # 2.0.0-dev3: eingegangene Anrufe/Anfragen mit fälliger Rückruffrist gehören zum Zugesagten
    for r in conn.execute("SELECT i.*, l.company FROM inbound i LEFT JOIN leads l ON l.id=i.lead_id WHERE i.status='offen' AND substr(i.due_at,1,10)<=? ORDER BY i.due_at", (t,)):
        add('rueckruf', f"Zurückmelden: {r['who']}", r['company'] or r['who'], r['lead_id'], r['due_at'][:10], 'Zum Eingang', 'today', r['id'],
            (r['note'] or r['contact'] or '')[:140], None)
        items[-1]['anchor'] = 'erreichbarkeit'
    for r in conn.execute("""SELECT m.*, l.company FROM meetings m JOIN leads l ON l.id=m.lead_id WHERE m.status IN ('geplant','bestaetigt')
                             AND substr(m.starts_at,1,10) BETWEEN ? AND ? ORDER BY m.starts_at""", (t, tomorrow)):
        add('termin', m_title(r), r['company'], r['lead_id'], r['starts_at'][:10], 'Vorbereiten', 'lead', r['lead_id'],
            r['starts_at'].replace('T', ' ')[11:16] + ' Uhr' + (f" · {r['location']}" if r['location'] else ''))
    order = {'termin': 0, 'rueckruf': 1, 'aufgabe': 2, 'naechster_schritt': 3, 'nachfassen': 4, 'angebot_frist': 5, 'bedarfsanalyse': 6, 'angebot_entwurf': 7}
    items.sort(key=lambda i: (i['kind'] != 'termin', not i['overdue'], order.get(i['kind'], 9), i['due'] or '9999'))
    return items


RESEARCH_RE = re.compile(r'bericht|recherch|website prüfen|impressum|url-recherche|signal belegen|anlass|ansprechpartner verifizieren|zuständige person', re.I)
GROUP_RULES = (
    ('recherche', 'Recherche', ('website_pruefen', 'ansprechpartner_verifizieren'), RESEARCH_RE),
    ('kontakt', 'Kontakt & Freigaben', ('erstkontakt', 'followup', 'rueckruf', 'empfehlung_anfragen'),
     re.compile(r'kontakt|anruf|rückruf|ruf .* an|e-mail|mail|nachfass|empfehlung|freigabe|ansprechen|anschreiben', re.I)),
    ('termine', 'Termine & Gespräche', ('termin_vorbereiten', 'bedarfsfrage_vorbereiten'), re.compile(r'termin|gespräch|meeting|workshop|bedarf|besuch|präsentation', re.I)),
    ('angebot', 'Angebote & Abrechnung', ('angebot_kalkulieren',), re.compile(r'angebot|rechnung|vertrag|zahlung|kalkul|preis', re.I)),
)

MATCH_ORDER = ('recherche', 'angebot', 'termine', 'kontakt')


def _group_of(title, action_type='', permission_status=''):
    if permission_status and permission_status != 'nicht_erforderlich':
        return 'kontakt'
    rules = {r[0]: r for r in GROUP_RULES}
    for key in MATCH_ORDER:  # das konkretere Geschäftsobjekt gewinnt: „Angebot nach Gespräch …“ → Angebote
        _, _, actions, rx = rules[key]
        if action_type in actions or rx.search(title or ''):
            return key
    return 'sonstiges'


def task_overview(conn, today=None):
    """Aufgaben gegliedert: Recherche zusammengefasst je Firma, danach Kontakt, Termine, Angebote, Sonstiges."""
    t = (today or dt.date.today()).isoformat()
    groups = {k: {'key': k, 'label': l, 'items': []} for k, l, _, _ in GROUP_RULES}
    groups['sonstiges'] = {'key': 'sonstiges', 'label': 'Sonstiges', 'items': []}
    for r in conn.execute("""SELECT t.*, l.company FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id
                             WHERE t.done=0 AND (l.id IS NULL OR l.stage NOT IN ('gesperrt','verloren')) ORDER BY (t.due_date=''), t.due_date, t.id"""):
        g = _group_of(r['title'], r['action_type'] or '', r['permission_status'] or '')
        groups[g]['items'].append({'type': 'task', 'id': r['id'], 'lead_id': r['lead_id'], 'company': r['company'] or 'Allgemein', 'title': r['title'],
                                   'due': r['due_date'], 'overdue': bool(r['due_date'] and r['due_date'] < t), 'permission_status': r['permission_status'],
                                   'channel': r['channel']})
    for r in conn.execute("""SELECT id, company, next_step, next_date, stage FROM leads WHERE next_step<>''
                             AND stage NOT IN ('gewonnen','verloren','gesperrt') ORDER BY (next_date=''), next_date"""):
        g = _group_of(r['next_step'])
        groups[g]['items'].append({'type': 'step', 'id': r['id'], 'lead_id': r['id'], 'company': r['company'], 'title': r['next_step'],
                                   'due': r['next_date'], 'overdue': bool(r['next_date'] and r['next_date'] < t)})
    # Recherche je Firma zusammenfassen: Firmen in Recherche ohne fertigen Bericht
    research = {}
    for it in groups['recherche']['items']:
        if it['lead_id']:
            research.setdefault(it['lead_id'], {'lead_id': it['lead_id'], 'company': it['company'], 'steps': []})['steps'].append(it['title'])
    for r in conn.execute("""SELECT l.id, l.company FROM leads l WHERE l.stage='recherche' AND l.permission<>'nicht_kontaktieren'
                             AND NOT EXISTS (SELECT 1 FROM company_reports r WHERE r.lead_id=l.id AND r.status='fertig')"""):
        research.setdefault(r['id'], {'lead_id': r['id'], 'company': r['company'], 'steps': []})
    for lid, entry in research.items():
        row = conn.execute("SELECT status FROM company_reports WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lid,)).fetchone()
        entry['report'] = row['status'] if row else ''
        entry['website'] = bool(conn.execute("SELECT website<>'' FROM leads WHERE id=?", (lid,)).fetchone()[0])
    firms = sorted(research.values(), key=lambda e: (e['report'] == 'fertig', not e['website'], e['company'].casefold()))
    other = [it for it in groups['recherche']['items'] if not it['lead_id']]
    groups['recherche']['items'] = other
    groups['recherche']['firms'] = firms
    for g in groups.values():
        g['count'] = len(g['items']) + len(g.get('firms', []))
        g['overdue'] = sum(1 for i in g['items'] if i['overdue'])
    done = [dict(r) for r in conn.execute("""SELECT t.id, t.title, t.due_date, l.company FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id
                                             WHERE t.done=1 ORDER BY t.id DESC LIMIT 30""")]
    return {'groups': list(groups.values()), 'done': done,
            'research_without_report': sum(1 for f in firms if f['report'] != 'fertig' and f['website'])}


def cleanup_research_steps(conn):
    """Entfernt erledigte Recherche-Schritte: Lead hat einen fertigen Firmen-Bericht."""
    n = 0
    for r in conn.execute("SELECT id, next_step FROM leads WHERE next_step<>''").fetchall():
        if RESEARCH_RE.search(r['next_step']) and conn.execute("SELECT 1 FROM company_reports WHERE lead_id=? AND status='fertig'", (r['id'],)).fetchone():
            conn.execute("UPDATE leads SET next_step='Kontaktweg klären (Firmen-Bericht liegt vor)', next_date='' WHERE id=?", (r['id'],))
            n += 1
    conn.commit()
    return {'updated': n}


def m_title(r):
    return f"Termin: {r['title']}"


def potential(conn, today=None):
    today = (today or dt.date.today()).isoformat()
    offers, accepted = [], []
    for r in conn.execute("""SELECT p.*, l.company, l.stage FROM proposals p JOIN leads l ON l.id=p.lead_id
                             WHERE l.stage NOT IN ('gesperrt','verloren') AND p.superseded_by IS NULL ORDER BY p.id DESC"""):
        invoiced = conn.execute("SELECT 1 FROM invoices WHERE proposal_id=? AND kind<>'storno' AND status<>'storniert' LIMIT 1", (r['id'],)).fetchone()
        entry = {'proposal_id': r['id'], 'lead_id': r['lead_id'], 'company': r['company'], 'number': r['number'] or f"#{r['id']}",
                 'status': r['status'], 'net_eur': round(_net(r), 2), 'project_label': _label(r), 'valid_until': r['valid_until'] or '',
                 'expired': bool(r['valid_until'] and r['valid_until'] < today)}
        if r['status'] in ('entwurf', 'gesendet_manuell') and not entry['expired']:
            offers.append(entry)
        elif r['status'] == 'angenommen' and not invoiced:
            accepted.append(entry)
    with_offer = {o['lead_id'] for o in offers + accepted}
    estimates = [{'lead_id': r['id'], 'company': r['company'], 'stage': r['stage'], 'estimated_budget': r['estimated_budget'], 'offer': r['offer']}
                 for r in conn.execute(f"""SELECT id, company, stage, estimated_budget, offer FROM leads WHERE estimated_budget>0
                                           AND stage IN ({','.join('?' for _ in OPEN_STAGES)}) ORDER BY estimated_budget DESC""", OPEN_STAGES)
                 if r['id'] not in with_offer]
    return {
        'offers': offers, 'offers_sum': round(sum(o['net_eur'] for o in offers), 2),
        'sent_sum': round(sum(o['net_eur'] for o in offers if o['status'] == 'gesendet_manuell'), 2),
        'accepted': accepted, 'accepted_sum': round(sum(o['net_eur'] for o in accepted), 2),
        'estimates': estimates[:10], 'estimates_sum': sum(e['estimated_budget'] for e in estimates), 'estimates_count': len(estimates),
        'notice': 'Offenes Potenzial = Summe der kalkulierten, noch gültigen Angebote (netto). Schätzungen ohne Angebot stehen getrennt – sie sind keine Zusage und kein Umsatz.',
    }


def pipeline(conn):
    out = []
    for stage, label in STAGE_LABELS.items():
        ids = [r['id'] for r in conn.execute('SELECT id FROM leads WHERE stage=?', (stage,))]
        value = 0.0
        for lid in ids:
            p = conn.execute("""SELECT customer_json FROM proposals WHERE lead_id=? AND status IN ('entwurf','gesendet_manuell','angenommen')
                                ORDER BY id DESC LIMIT 1""", (lid,)).fetchone()
            if p:
                value += _net(p)
        out.append({'stage': stage, 'label': label, 'count': len(ids), 'offer_value': round(value, 2), **{f'action_{k}': v for k, v in STAGE_ACTIONS[stage].items()}})
    return out


def capabilities(conn, check_ollama=True):
    """Ehrlicher Funktionsstatus: was funktioniert, was braucht eine Voraussetzung."""
    from .ai_lab import ollama_health
    from .backup_crypto import available as crypto_ok
    from .website_scorer import playwright_available
    sources = {}
    for r in conn.execute('''SELECT source, status, error, created_at, result_count FROM discovery_runs d
                             WHERE id=(SELECT MAX(id) FROM discovery_runs WHERE source=d.source)'''):
        sources[r['source']] = {'status': r['status'], 'error': r['error'], 'last_run': r['created_at'], 'results': r['result_count']}
    ai = ollama_health(timeout=0.6) if check_ollama else {'online': False, 'message': 'nicht geprüft'}
    browser = playwright_available()
    items = [
        {'key': 'crm', 'label': 'Leads, Pipeline, Aufgaben, Angebote, Rechnungen', 'ok': True, 'detail': 'Funktioniert vollständig offline.'},
        {'key': 'crawler', 'label': 'Website-Prüfung mit Browser (Scoring, Screenshots)', 'ok': browser,
         'detail': 'Chromium/Playwright installiert.' if browser else 'Ohne Playwright nur eingeschränkt (HTML ohne Screenshots). Einmalig: Startdatei mit --reinstall ausführen.'},
        {'key': 'ai', 'label': 'Lokale KI (Ollama) für KI-Studio und URL-Recherche', 'ok': bool(ai.get('online')),
         'detail': ai.get('message', '') + ('' if ai.get('online') else ' Alles Wichtige läuft auch ohne KI im Regelmodus.')},
        {'key': 'crypto', 'label': 'Verschlüsselte Sicherung', 'ok': crypto_ok(), 'detail': '' if crypto_ok() else 'Optional: pip install -r requirements-team.txt'},
    ]
    for src, label in (('gleif', 'GLEIF (Firmenregister-Kennungen)'), ('wikidata', 'Wikidata'), ('osm', 'OpenStreetMap'), ('ted', 'TED-Ausschreibungen')):
        s = sources.get(src)
        if not s:
            items.append({'key': 'src_' + src, 'label': f'Firmensuche: {label}', 'ok': None, 'detail': 'Noch nicht ausprobiert.'})
        else:
            ok = s['status'] == 'done'
            items.append({'key': 'src_' + src, 'label': f'Firmensuche: {label}', 'ok': ok,
                          'detail': f"Letzter Versuch {s['last_run'][:16]}: " + (f"{s['results']} Treffer" if ok else (s['error'] or s['status'])[:220])})
    return {'items': items, 'ai_online': bool(ai.get('online')), 'browser': browser}


def plan(conn, items, pot, today=None):
    today = (today or dt.date.today()).isoformat()
    from .research_center import review_queue
    rq = review_queue(conn)['total']
    meetings = sum(1 for i in items if i['kind'] == 'termin')
    due = sum(1 for i in items if i['kind'] in ('aufgabe', 'naechster_schritt', 'rueckruf', 'bedarfsanalyse'))
    perms = conn.execute("SELECT COUNT(*) FROM tasks t LEFT JOIN leads l ON l.id=t.lead_id WHERE t.done=0 AND t.permission_status='zu_pruefen' AND (l.id IS NULL OR l.stage<>'gesperrt')").fetchone()[0]
    follow = sum(1 for i in items if i['kind'] in ('nachfassen', 'angebot_frist', 'angebot_entwurf'))
    new_candidates = conn.execute("SELECT COUNT(*) FROM discovery_candidates WHERE status='neu'").fetchone()[0]
    searched_today = conn.execute("SELECT 1 FROM discovery_runs WHERE substr(created_at,1,10)=?", (today,)).fetchone() is not None
    steps = [
        {'key': 'termine', 'title': 'Termine von heute und morgen vorbereiten', 'count': meetings, 'view': 'today', 'anchor': 'wiedervorlage',
         'why': 'Gespräche haben feste Zeiten – zuerst Dossier und Bedarfsfragen lesen.'},
        {'key': 'wiedervorlage', 'title': 'Wiedervorlagen erledigen (Rückrufe, Aufgaben, nächste Schritte)', 'count': due, 'view': 'today', 'anchor': 'wiedervorlage',
         'why': 'Zugesagtes zuerst – das schafft Vertrauen.'},
        {'key': 'nachfassen', 'title': 'Angebote nachfassen oder fertigstellen', 'count': follow, 'view': 'quotes',
         'why': f"{pot['sent_sum']:,.0f} € netto liegen beim Kunden.".replace(',', '.') if pot['sent_sum'] else 'Offene Angebote im Blick behalten.'},
        {'key': 'freigaben', 'title': 'Kontaktaktionen freigeben', 'count': perms, 'view': 'workspace', 'section': 'permissions',
         'why': 'Jede Ansprache braucht eine dokumentierte Grundlage (§ 7 UWG).'},
        {'key': 'pruefen', 'title': 'Rechercheergebnisse prüfen', 'count': rq, 'view': 'center',
         'why': 'Funde, Impressen, Signale und Änderungen warten auf deine Entscheidung.'},
        {'key': 'finden', 'title': 'Neue Firmen finden und sichten', 'count': new_candidates, 'view': 'finder', 'done_override': searched_today,
         'why': f'{new_candidates} Treffer warten auf Sichtung.' if new_candidates else 'Für morgen neue passende Firmen suchen.'},
    ]
    for s in steps:
        override = s.pop('done_override', None)
        s['done'] = s['count'] == 0 if override is None else (override and s['count'] == 0)
        # 2.0.0-dev13: „nichts offen“ ist nicht dasselbe wie „erledigt“ (Produktreview U08/B05)
        s['state'] = 'offen' if not s['done'] else ('erledigt' if override else 'nichts_offen')
    nxt = next((s for s in steps if not s['done']), None)
    return {'steps': steps, 'next_key': nxt['key'] if nxt else None}


def today_view(conn, today=None, check_ollama=False):
    items = wiedervorlage(conn, today)
    pot = potential(conn, today)
    return {'date': (today or dt.date.today()).isoformat(), 'plan': plan(conn, items, pot, today), 'wiedervorlage': items[:40],
            'wiedervorlage_total': len(items), 'potential': pot, 'pipeline': pipeline(conn)}


def route_today(h, conn, method, route, query):
    if route == '/api/today' and method == 'GET':
        h._send(200, today_view(conn))
        return True
    if route == '/api/tasks/overview' and method == 'GET':
        h._send(200, task_overview(conn))
        return True
    if route == '/api/tasks/research-cleanup' and method == 'POST':
        h._send(200, cleanup_research_steps(conn))
        return True
    if route == '/api/system/capabilities' and method == 'GET':
        h._send(200, capabilities(conn))
        return True
    return False
