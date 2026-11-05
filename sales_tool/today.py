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

OPEN_STAGES = ('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot')
STAGE_ACTIONS = {
    'recherche': {'label': 'Firma recherchieren', 'view': 'center', 'hint': 'Website, Impressum, Signale und Entscheider prüfen'},
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
    for r in conn.execute("""SELECT id, company, next_step, next_date FROM leads WHERE next_step<>'' AND next_date<>'' AND next_date<=?
                             AND stage NOT IN ('gewonnen','verloren','gesperrt') ORDER BY next_date""", (t,)):
        add('naechster_schritt', r['next_step'], r['company'], r['id'], r['next_date'], 'Lead öffnen', 'lead', r['id'])
    for r in conn.execute("""SELECT c.*, l.company FROM calls c JOIN leads l ON l.id=c.lead_id
                             WHERE c.outcome='rueckruf_vereinbart' AND c.callback_date<>'' AND c.callback_date<=? AND l.stage NOT IN ('gesperrt','verloren')
                             AND l.permission<>'nicht_kontaktieren'
                             AND NOT EXISTS (SELECT 1 FROM calls c2 WHERE c2.lead_id=c.lead_id AND c2.id>c.id)
                             ORDER BY c.callback_date""", (tomorrow,)):
        add('rueckruf', 'Vereinbarten Rückruf wahrnehmen', r['company'], r['lead_id'], r['callback_date'], 'Anruf dokumentieren', 'workspace',
            r['id'], (r['notes'] or '')[:140], 'contact')
    for r in conn.execute("""SELECT p.*, l.company FROM proposals p JOIN leads l ON l.id=p.lead_id
                             WHERE p.status IN ('entwurf','gesendet_manuell') AND l.stage NOT IN ('gesperrt','verloren') ORDER BY p.updated_at"""):
        age = _days_since(r['updated_at'], today)
        expires = r['valid_until'] or ''
        if r['status'] == 'gesendet_manuell' and age >= 7:
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
    for r in conn.execute("""SELECT m.*, l.company FROM meetings m JOIN leads l ON l.id=m.lead_id WHERE m.status IN ('geplant','bestaetigt')
                             AND substr(m.starts_at,1,10) BETWEEN ? AND ? ORDER BY m.starts_at""", (t, tomorrow)):
        add('termin', m_title(r), r['company'], r['lead_id'], r['starts_at'][:10], 'Vorbereiten', 'lead', r['lead_id'],
            r['starts_at'].replace('T', ' ')[11:16] + ' Uhr' + (f" · {r['location']}" if r['location'] else ''))
    order = {'termin': 0, 'rueckruf': 1, 'aufgabe': 2, 'naechster_schritt': 3, 'nachfassen': 4, 'angebot_frist': 5, 'bedarfsanalyse': 6, 'angebot_entwurf': 7}
    items.sort(key=lambda i: (i['kind'] != 'termin', not i['overdue'], order.get(i['kind'], 9), i['due'] or '9999'))
    return items


def m_title(r):
    return f"Termin: {r['title']}"


def potential(conn, today=None):
    today = (today or dt.date.today()).isoformat()
    offers, accepted = [], []
    for r in conn.execute("""SELECT p.*, l.company, l.stage FROM proposals p JOIN leads l ON l.id=p.lead_id
                             WHERE l.stage NOT IN ('gesperrt','verloren') ORDER BY p.id DESC"""):
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
    if route == '/api/system/capabilities' and method == 'GET':
        h._send(200, capabilities(conn))
        return True
    return False
