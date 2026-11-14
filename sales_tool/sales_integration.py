"""Sales-Integration (Phase 5): Offer Matching, Decision Maker Finder v3, Sales Action Center.

- Offer Matching: Pakete aus dem tatsächlichen Leistungskatalog werden aus *bestätigten*
  Kundenaussagen (Bedarfsanalyse) empfohlen. Vor der Bedarfsklärung sind Empfehlungen nur
  unverbindliche Möglichkeiten; erst nach dokumentierter Bedarfsklärung sind sie Angebotsgrundlage.
- Entscheider v3: fachliche Zuständigkeit, Budgetverantwortung und finale Entscheidungsbefugnis
  getrennt (unbekannt/vermutet/bestätigt), veröffentlichter geschäftlicher Kontaktweg mit Quelle,
  Kontaktbeschränkungen je Person; Zielrollen je Thema mit Lückenanalyse.
- Action Center: Aufgabenvorschläge aus Rechercheergebnissen. Jede Kontaktaktion hat einen eigenen
  Freigabe- und Berechtigungsstatus (§ 7 UWG); ohne Freigabe kann sie nicht erledigt werden. Es wird
  niemand automatisch kontaktiert.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from .company_data import add_suppression, _audit
from .model import discovery_summary

# ---------------------------------------------------------------- Schema

def init_sales_integration(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS offer_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        package TEXT NOT NULL, rank INTEGER NOT NULL, status TEXT NOT NULL, score INTEGER NOT NULL,
        basis_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS action_dismissals (
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE, action_key TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (lead_id, action_key)
      );
    ''')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(decision_contacts)')}
    for name, decl in (('role_fachlich', "TEXT DEFAULT 'unbekannt'"), ('role_budget', "TEXT DEFAULT 'unbekannt'"),
                       ('role_entscheidung', "TEXT DEFAULT 'unbekannt'"), ('contact_restrictions', "TEXT DEFAULT '[]'"),
                       ('restriction_note', "TEXT DEFAULT ''"), ('business_channel', "TEXT DEFAULT ''"),
                       ('business_channel_kind', "TEXT DEFAULT ''"), ('business_channel_source', "TEXT DEFAULT ''")):
        if name not in cols:
            conn.execute(f'ALTER TABLE decision_contacts ADD COLUMN {name} {decl}')
    tcols = {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
    for name, decl in (('action_type', "TEXT DEFAULT ''"), ('source', "TEXT DEFAULT ''"), ('channel', "TEXT DEFAULT ''"),
                       ('contact_id', 'INTEGER'), ('permission_status', "TEXT DEFAULT 'nicht_erforderlich'"),
                       ('permission_basis', "TEXT DEFAULT ''"), ('permission_checked_at', "TEXT DEFAULT ''")):
        if name not in tcols:
            conn.execute(f'ALTER TABLE tasks ADD COLUMN {name} {decl}')


# ---------------------------------------------------------------- Offer Matching (Modul 8)

MATCH_RULES = {
    'conversion': [r'anfrage', r'leads?\b', r'conversion', r'kontaktformular', r'website.{0,30}(veraltet|alt|relaunch|neu)', r'relaunch',
                   r'produkt.{0,20}(präsentation|seite|darstell)', r'online.{0,15}(sichtbar|gefunden)', r'vertrieb.{0,20}digital'],
    'pilot': [r'erst(mal)? klein', r'test(en|weise)', r'pilot', r'schnell(e|er)? (ergebnis|verbesserung)', r'ein(en)? (konkreten )?anfrageweg', r'formular.{0,20}(funktioniert|kompliziert)'],
    'brand': [r'marke', r'corporate design', r'\bci\b', r'logo', r'auftritt', r'umfirmier', r'umbenenn', r'einheitlich', r'erscheinungsbild', r'design.{0,15}(veraltet|uneinheitlich)'],
    'portal': [r'portal', r'kunden.{0,30}selbst', r'self.?service', r'kundenbereich', r'login', r'app\b', r'status.{0,20}(abfrag|nachfrag)', r'bestell.{0,20}(online|digital)'],
    'automation': [r'excel', r'manuell', r'doppelt', r'mehrfach.{0,15}(erfass|eingeb|eintrag)', r'automatis', r'workflow', r'schnittstelle',
                   r'medienbruch', r'abtippen', r'übertrag(en|ung).{0,30}(system|hand)', r'zeitaufw', r'fehleranf'],
    'care': [r'pflege', r'laufend', r'betreuung', r'updates?\b', r'niemand (kümmert|pflegt)', r'wartung', r'aktuell halten'],
}
DISCOVERY_LABELS = {'problem': 'Bestätigtes Problem', 'impact': 'Auswirkung', 'current_solution': 'Bisherige Lösung',
                    'desired_outcome': 'Gewünschtes Ergebnis', 'timing': 'Zeitrahmen', 'decision_process': 'Entscheidungsweg', 'budget_note': 'Budget'}


def _quote(text, m):
    a, b = max(0, m.start() - 60), min(len(text), m.end() + 80)
    return ('…' if a else '') + re.sub(r'\s+', ' ', text[a:b]).strip() + ('…' if b < len(text) else '')


def discovery_state(disc):
    if not disc:
        return {'complete': False, 'answered': 0, 'total': 5, 'missing': ['problem', 'impact', 'desired_outcome', 'timing', 'decision_process']}
    s = discovery_summary(disc)
    complete = bool((disc.get('problem') or '').strip()) and bool((disc.get('desired_outcome') or '').strip()) and s['answered'] >= 4
    return {'complete': complete, **s}


def match_offers(conn, lead_id):
    from .catalog import VORLAGEN as PACKAGES
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    row = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lead_id,)).fetchone()
    disc = dict(row) if row else None
    state = discovery_state(disc)
    recs = {k: {'package': k, 'title': PACKAGES[k]['title'], 'confirmed': [], 'hints': [], 'notes': []} for k in PACKAGES}
    if disc:
        for field, label in DISCOVERY_LABELS.items():
            text = (disc.get(field) or '').strip()
            if not text:
                continue
            for pkg, patterns in MATCH_RULES.items():
                for pat in patterns:
                    m = re.search(pat, text, re.I)
                    if m:
                        recs[pkg]['confirmed'].append({'field': label, 'quote': _quote(text, m)})
                        break
    for h in conn.execute('SELECT hypothesis, strength, offers_json FROM signal_correlations WHERE lead_id=?', (lead_id,)):
        for pkg in json.loads(h['offers_json']):
            if pkg in recs:
                recs[pkg]['hints'].append({'source': 'Signal-Hypothese', 'text': f"{h['hypothesis']} ({h['strength']})"})
    audit = conn.execute("SELECT summary_json FROM website_audits WHERE lead_id=? AND status='done' ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone()
    if audit:
        for o in json.loads(audit['summary_json'] or '{}').get('offers', []):
            if o['key'] in recs:
                recs[o['key']]['hints'].append({'source': 'Website-Bewertung', 'text': '; '.join(o.get('reasons', [])[:3])})
    out = []
    from .catalog import price_label, vorlagen
    current = {v['key']: v for v in vorlagen(conn)} if any(r['confirmed'] or r['hints'] for r in recs.values()) else {}
    for pkg, r in recs.items():
        if not r['confirmed'] and not r['hints']:
            continue
        r['score'] = 3 * len(r['confirmed']) + len(r['hints'])
        r['status'] = 'angebotsgrundlage' if state['complete'] and r['confirmed'] else 'unverbindlich'
        # 2.0.0-dev16 (M12): Preis der Vorlage aus dem zentralen Katalog – dieselbe Rechnung wie im Angebot
        r['price_eur'] = current[pkg]['once_net_eur'] or current[pkg]['monthly_net_eur']
        r['price_label'] = price_label(current[pkg])
        if disc and disc.get('budget_status') in ('kein_budget', 'freigabe_offen') and current[pkg]['once_net_eur'] > 3000:
            r['notes'].append('Budget laut Gespräch noch nicht freigegeben – Einstieg über den Website- & Anfrage-Pilot erwägen.')
        if r['status'] == 'unverbindlich':
            r['notes'].append('Unverbindliche Möglichkeit: erst nach dokumentierter Bedarfsklärung als Angebotsgrundlage verwenden.'
                              if not state['complete'] else 'Keine bestätigte Kundenaussage für dieses Paket – nur Hinweise aus der Recherche.')
        out.append(r)
    out.sort(key=lambda r: (r['status'] != 'angebotsgrundlage', -r['score']))
    conn.execute('DELETE FROM offer_recommendations WHERE lead_id=?', (lead_id,))
    for rank, r in enumerate(out, 1):
        cur = conn.execute('INSERT INTO offer_recommendations(lead_id, package, rank, status, score, basis_json) VALUES (?,?,?,?,?,?)',
                           (lead_id, r['package'], rank, r['status'], r['score'],
                            json.dumps({k: r[k] for k in ('confirmed', 'hints', 'notes')}, ensure_ascii=False)))
        r['id'] = cur.lastrowid
        r['rank'] = rank
    conn.commit()
    return {'lead_id': lead_id, 'discovery': state, 'recommendations': out,
            'notice': ('Bedarfsklärung dokumentiert: Pakete mit bestätigten Kundenaussagen können als Angebotsgrundlage dienen.' if state['complete'] else
                       'Bedarfsklärung unvollständig: alle Empfehlungen sind unverbindliche Möglichkeiten. Bitte zuerst Problem, Auswirkung, gewünschtes Ergebnis, Zeitrahmen und Entscheidungsweg im Gespräch bestätigen.')}


def stored_recommendations(conn, lead_id):
    from .catalog import VORLAGEN as PACKAGES
    rows = []
    for r in conn.execute('SELECT * FROM offer_recommendations WHERE lead_id=? ORDER BY rank', (lead_id,)):
        d = dict(r)
        d.update(json.loads(d.pop('basis_json')))
        d['title'] = PACKAGES.get(d['package'], {}).get('title', d['package'])
        rows.append(d)
    return rows


def quote_draft(conn, rec_id):
    rec = conn.execute('SELECT * FROM offer_recommendations WHERE id=?', (rec_id,)).fetchone()
    if not rec:
        raise LookupError('Empfehlung nicht gefunden.')
    if rec['status'] != 'angebotsgrundlage':
        raise ValueError('Unverbindliche Empfehlung: Erst die Bedarfsklärung dokumentieren, dann als Angebotsgrundlage verwenden.')
    disc = dict(conn.execute('SELECT * FROM discovery WHERE lead_id=?', (rec['lead_id'],)).fetchone())
    from .catalog import VORLAGEN as PACKAGES
    assumptions = '; '.join(x for x in (f"Zeitrahmen laut Gespräch: {disc['timing']}" if disc.get('timing') else '',
                                        f"Entscheidungsweg: {disc['decision_process']}" if disc.get('decision_process') else '',
                                        f"Bisherige Lösung: {disc['current_solution']}" if disc.get('current_solution') else '') if x)
    from .pricing import TEMPLATES
    return {'lead_id': rec['lead_id'], 'package': rec['package'], 'project_label': PACKAGES[rec['package']]['title'],
            'positions': TEMPLATES.get(rec['package'], []),
            'customer_goal': (disc.get('desired_outcome') or PACKAGES[rec['package']]['outcome'])[:500], 'assumptions': assumptions[:1000],
            'notice': 'Aus der dokumentierten Bedarfsklärung vorbelegt. Leistungsumfang, Festpreis und Steuerstatus vor dem Versand prüfen.'}


# ---------------------------------------------------------------- Entscheider v3 (Modul 6)

ROLE_STATES = ('unbekannt', 'vermutet', 'bestaetigt')
RESTRICTIONS = {'kein_telefon': 'Keine Anrufe', 'keine_email': 'Keine E-Mails', 'nur_post': 'Nur Briefpost',
                'nur_ueber_zentrale': 'Nur über Zentrale/Assistenz', 'widerspruch': 'Widerspruch – keine Ansprache'}
TOPIC_ROLES = {
    'web': ['Marketing', 'Geschäftsführung'],
    'brand': ['Marketing', 'Brand Management', 'Geschäftsführung'],
    'software': ['IT', 'Digitalisierung', 'Operations'],
    'process': ['Operations', 'Fachbereich', 'IT'],
}
ROLE_PATTERNS = {
    'Marketing': r'marketing|kommunikation|vertrieb|sales|e-?commerce|growth', 'Brand Management': r'brand|marke|corporate|design',
    'Geschäftsführung': r'geschäftsführ|inhaber|ceo|vorstand|managing|gründer|founder',
    'IT': r'\bit\b|it-|informatik|cto|technik|software|entwickl', 'Digitalisierung': r'digital|transformation|innovation|cdo',
    'Operations': r'operations|betrieb|coo|produktion|logistik|werkleit|prozess', 'Fachbereich': r'leiter|leitung|head of|abteilung|bereich|teamlead',
}
TOPIC_LABELS = {'web': 'Website & Anfragen', 'brand': 'Marke & Design', 'software': 'Portal / Software', 'process': 'Prozess & Automatisierung'}
THEME_TOPIC = {'brand': 'brand', 'web': 'web', 'process': 'process', 'growth': 'web'}
OFFER_TOPIC = {'pilot': 'web', 'conversion': 'web', 'care': 'web', 'brand': 'brand', 'portal': 'software', 'automation': 'process'}


def lead_topics(conn, lead):
    topics = []
    for r in conn.execute('SELECT theme FROM signal_correlations WHERE lead_id=? ORDER BY score DESC', (lead['id'],)):
        t = THEME_TOPIC.get(r['theme'])
        if t and t not in topics:
            topics.append(t)
    for r in conn.execute('SELECT package FROM offer_recommendations WHERE lead_id=? ORDER BY rank', (lead['id'],)):
        t = OFFER_TOPIC.get(r['package'])
        if t and t not in topics:
            topics.append(t)
    t = OFFER_TOPIC.get(lead['offer'])
    if t and t not in topics:
        topics.append(t)
    return topics or ['web']


def contact_view(row):
    d = dict(row)
    d['contact_restrictions'] = json.loads(d.get('contact_restrictions') or '[]')
    d['roles'] = {'fachlich': d.get('role_fachlich') or 'unbekannt', 'budget': d.get('role_budget') or 'unbekannt',
                  'entscheidung': d.get('role_entscheidung') or 'unbekannt'}
    d.pop('preview_json', None)
    return d


def decision_map(conn, lead_id):
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    contacts = [contact_view(r) for r in conn.execute('SELECT * FROM decision_contacts WHERE lead_id=? ORDER BY id', (lead_id,))]
    topics = lead_topics(conn, lead)
    roles = []
    for t in topics:
        for role in TOPIC_ROLES[t]:
            if role in [r['role'] for r in roles]:
                continue
            matches = [c for c in contacts if re.search(ROLE_PATTERNS[role], (c.get('job_title') or '').lower())]
            verified = [c for c in matches if c.get('verification_status') in ('quelle_geprueft', 'rolle_bestaetigt')]
            roles.append({'role': role, 'topic': t, 'topic_label': TOPIC_LABELS[t], 'persons': [{'id': c['id'], 'name': c['full_name'], 'verified': c in verified} for c in matches],
                          'gap': not verified})
    return {'lead_id': lead_id, 'topics': topics, 'topic_labels': {t: TOPIC_LABELS[t] for t in topics}, 'roles': roles, 'contacts': contacts, 'restriction_labels': RESTRICTIONS,
            'note': 'Fachliche Zuständigkeit, Budgetverantwortung und Entscheidungsbefugnis sind getrennte Fragen. Eine Funktion laut Website ist keine bestätigte Befugnis.'}


def update_contact_roles(conn, contact_id, data):
    allowed = {'role_fachlich', 'role_budget', 'role_entscheidung', 'contact_restrictions', 'restriction_note',
               'business_channel', 'business_channel_kind', 'business_channel_source'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Ungültige Felder.')
    c = conn.execute('''SELECT d.*, l.business_phone AS lead_phone, l.business_email AS lead_email, l.stage, l.permission
                        FROM decision_contacts d JOIN leads l ON l.id=d.lead_id WHERE d.id=?''', (contact_id,)).fetchone()
    if not c:
        raise LookupError('Kontakt nicht gefunden.')
    out = {}
    for k in ('role_fachlich', 'role_budget', 'role_entscheidung'):
        if k in data:
            if data[k] not in ROLE_STATES:
                raise ValueError(f'{k}: unbekannt, vermutet oder bestaetigt.')
            out[k] = data[k]
    verified = c['verification_status'] in ('quelle_geprueft', 'rolle_bestaetigt')
    if any(out.get(k) == 'bestaetigt' for k in ('role_fachlich', 'role_budget')) and not verified:
        raise ValueError('„Bestätigt“ nur mit geprüfter Quelle (Prüfstatus „Quelle geprüft“ oder „Rolle bestätigt“).')
    if out.get('role_entscheidung') == 'bestaetigt' and c['verification_status'] != 'rolle_bestaetigt':
        raise ValueError('Finale Entscheidungsbefugnis nur nach bestätigter Rolle (z. B. im Gespräch) kennzeichnen.')
    if 'contact_restrictions' in data:
        r = data['contact_restrictions']
        if not isinstance(r, list) or any(x not in RESTRICTIONS for x in r):
            raise ValueError('Unbekannte Kontaktbeschränkung.')
        out['contact_restrictions'] = json.dumps(sorted(set(r)))
    for k, limit in (('restriction_note', 500), ('business_channel', 200), ('business_channel_source', 500)):
        if k in data:
            v = data[k]
            if not isinstance(v, str) or len(v.strip()) > limit:
                raise ValueError(f'{k}: Text bis {limit} Zeichen.')
            out[k] = v.strip()
    if 'business_channel_kind' in data:
        if data['business_channel_kind'] not in ('', 'email', 'telefon'):
            raise ValueError('Kontaktweg: email oder telefon.')
        out['business_channel_kind'] = data['business_channel_kind']
    channel = out.get('business_channel', c['business_channel'] or '')
    kind = out.get('business_channel_kind', c['business_channel_kind'] or '')
    source = out.get('business_channel_source', c['business_channel_source'] or '')
    if channel:
        if kind not in ('email', 'telefon'):
            raise ValueError('Art des Kontaktwegs angeben (E-Mail oder Telefon).')
        if not source.startswith('https://'):
            raise ValueError('Für einen persönlichen geschäftlichen Kontaktweg ist eine HTTPS-Fundstelle erforderlich.')
        digits = lambda s: re.sub(r'\D', '', s or '')[-8:]
        if kind == 'telefon' and c['lead_phone'] and digits(channel) == digits(c['lead_phone']):
            raise ValueError('Das ist die allgemeine Firmennummer – sie darf nicht als persönliche Durchwahl gespeichert werden.')
        if kind == 'email':
            if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', channel):
                raise ValueError('E-Mail-Adresse ungültig.')
            if channel.lower() == (c['lead_email'] or '').lower() or channel.split('@')[0].lower() in ('info', 'kontakt', 'office', 'mail', 'hello', 'service'):
                raise ValueError('Allgemeine Firmenadresse ist kein persönlicher Kontaktweg.')
    if not out:
        raise ValueError('Keine Änderung.')
    conn.execute(f"UPDATE decision_contacts SET {', '.join(k + '=?' for k in out)}, updated_at=datetime('now') WHERE id=?", (*out.values(), contact_id))
    restrictions = json.loads(out.get('contact_restrictions', c['contact_restrictions'] or '[]'))
    if 'widerspruch' in restrictions:
        if kind == 'email' and channel:
            add_suppression(conn, 'email', channel, f"Widerspruch {c['full_name']}", c['lead_id'])
        conn.execute("""UPDATE tasks SET permission_status='abgelehnt', permission_basis='Widerspruch der Person' WHERE contact_id=? AND done=0
                        AND permission_status IN ('zu_pruefen','freigegeben')""", (contact_id,))
        _audit(conn, 'contact', contact_id, 'widerspruch', f"Lead {c['lead_id']}: Widerspruch eingetragen")  # ohne Namen: Audit-Log ist unveränderbar
    conn.commit()
    return contact_view(conn.execute('SELECT * FROM decision_contacts WHERE id=?', (contact_id,)).fetchone())


# ---------------------------------------------------------------- Sales Action Center (Modul 10)

CONTACT_CHANNELS = ('email', 'telefon', 'brief', 'persoenlich')
CHANNEL_LABELS = {'email': 'E-Mail', 'telefon': 'Telefon', 'brief': 'Brief', 'persoenlich': 'persönliches Gespräch'}
ACTION_LABELS = {
    'website_pruefen': 'Unternehmenswebsite manuell prüfen', 'ansprechpartner_verifizieren': 'Ansprechpartner verifizieren',
    'bedarfsfrage_vorbereiten': 'Bedarfsfrage vorbereiten', 'empfehlung_anfragen': 'Persönliche Empfehlung anfragen',
    'termin_vorbereiten': 'Kundentermin vorbereiten', 'angebot_kalkulieren': 'Angebot kalkulieren',
    'erstkontakt': 'Erstkontakt vorbereiten', 'followup': 'Vereinbarten Follow-up-Termin bearbeiten', 'rueckruf': 'Vereinbarten Rückruf wahrnehmen',
}


def suggest_actions(conn, lead_id):
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    if lead['stage'] in ('gesperrt', 'gewonnen', 'verloren') or lead['permission'] == 'nicht_kontaktieren':
        return []
    from .workday import contact_lock
    if contact_lock(conn, lead):  # v1.18: auch Sperrliste (Domain/Name/Register/E-Mail)
        return []
    out = []

    def add(key, atype, title, reason, contact_id=None, channel='', requires=False):
        out.append({'key': key, 'lead_id': lead_id, 'company': lead['company'], 'action_type': atype, 'title': title, 'reason': reason,
                    'contact_id': contact_id, 'channel': channel, 'requires_permission': requires})

    f = conn.execute("""SELECT COUNT(*) FROM website_findings WHERE result='auffaellig' AND review_status='ungeprueft'
                        AND audit_id=(SELECT MAX(id) FROM website_audits WHERE lead_id=? AND status='done')""", (lead_id,)).fetchone()[0]
    if f:
        add('website_pruefen', 'website_pruefen', f'Website manuell prüfen: {f} auffällige Befunde bestätigen oder verwerfen',
            'Automatische Befunde sind Hinweise, keine Fakten.')
    dm = decision_map(conn, lead_id)
    for c in dm['contacts']:
        if c['verification_status'] == 'ungeprueft':
            add(f"verify:{c['id']}", 'ansprechpartner_verifizieren', f"Ansprechpartner verifizieren: {c['full_name']}",
                'Funktion und Quelle sind noch nicht geprüft.', c['id'])
    for r in dm['roles']:
        if r['gap']:
            add(f"role:{r['role']}", 'ansprechpartner_verifizieren', f"Zuständige Person recherchieren: {r['role']}",
                f"Für das Thema „{r['topic_label']}“ ist diese Rolle relevant, aber noch keine Person mit geprüfter Quelle erfasst.")
            break
    disc = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lead_id,)).fetchone()
    state = discovery_state(dict(disc) if disc else None)
    hyp = conn.execute('SELECT hypothesis FROM signal_correlations WHERE lead_id=? ORDER BY score DESC LIMIT 1', (lead_id,)).fetchone()
    if hyp and not state['complete']:
        add('bedarfsfrage', 'bedarfsfrage_vorbereiten', 'Bedarfsfragen fürs Erstgespräch vorbereiten',
            f"Hypothese „{hyp['hypothesis'][:90]}…“ muss im Gespräch bestätigt werden.")
    route = lead['contact_route'] or 'unbekannt'
    if lead['permission'] == 'unbekannt' and route == 'unbekannt' and (hyp or f):
        add('empfehlung', 'empfehlung_anfragen', 'Persönliche Empfehlung oder Einführung anfragen',
            'Kein dokumentierter Kontaktweg – eine Empfehlung ist der sauberste Erstkontakt.', channel='persoenlich')
    for m in conn.execute("""SELECT id, title, starts_at FROM meetings WHERE lead_id=? AND status IN ('geplant','bestaetigt')
                             AND starts_at BETWEEN datetime('now') AND datetime('now','+7 day')""", (lead_id,)):
        add(f"meeting:{m['id']}", 'termin_vorbereiten', f"Kundentermin vorbereiten: {m['title']} ({m['starts_at'].replace('T', ' ')})",
            'Dossier, Bedarfsfragen und Belege vorab durchgehen.')
    rec = conn.execute("SELECT package FROM offer_recommendations WHERE lead_id=? AND status='angebotsgrundlage' ORDER BY rank LIMIT 1", (lead_id,)).fetchone()
    if rec and not conn.execute("SELECT 1 FROM proposals WHERE lead_id=? AND status<>'abgelehnt'", (lead_id,)).fetchone():
        from .catalog import VORLAGEN as PACKAGES
        add(f"angebot:{rec['package']}", 'angebot_kalkulieren', f"Angebot kalkulieren: {PACKAGES[rec['package']]['title']}",
            'Bedarfsklärung ist dokumentiert und passt zu diesem Paket.')
    for p in conn.execute("""SELECT id FROM proposals WHERE lead_id=? AND status='gesendet_manuell' AND superseded_by IS NULL AND updated_at <= datetime('now','-7 day')
                             AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.proposal_id=proposals.id)""", (lead_id,)):
        add(f"followup:{p['id']}", 'followup', f'Vereinbarten Follow-up zu Angebot #{p["id"]} bearbeiten',
            'Angebot liegt seit über einer Woche beim Kunden – nur im vereinbarten Rahmen nachfassen.', requires=True,
            channel='email' if lead['permission'] == 'opt_in' else 'telefon')
    if lead['permission'] in ('opt_in', 'bestandskunde_pruefen', 'telefon_einzelfall') and (hyp or rec):
        channel = 'email' if lead['permission'] == 'opt_in' else 'telefon' if lead['permission'] == 'telefon_einzelfall' else 'brief'
        add(f'erstkontakt:{channel}', 'erstkontakt', f"Erstkontakt per {CHANNEL_LABELS[channel]} vorbereiten",
            'Kontaktaktion – vor Ausführung Freigabe und Berechtigung prüfen.', channel=channel, requires=True)
    open_keys = {r['source'] for r in conn.execute("SELECT source FROM tasks WHERE lead_id=? AND done=0 AND source<>''", (lead_id,))}
    dismissed = {r['action_key'] for r in conn.execute('SELECT action_key FROM action_dismissals WHERE lead_id=?', (lead_id,))}
    return [a for a in out if f"vorschlag:{a['key']}" not in open_keys and a['key'] not in dismissed]


def all_suggestions(conn, limit=30):
    out = []
    for r in conn.execute("SELECT id FROM leads WHERE stage IN ('recherche','qualifiziert','kontakt','antwort','termin','angebot') ORDER BY updated_at DESC LIMIT 200"):
        out += suggest_actions(conn, r['id'])
        if len(out) >= limit:
            break
    return out[:limit]


def accept_suggestion(conn, data):
    if not isinstance(data, dict) or set(data) - {'lead_id', 'key', 'due_date'} or not isinstance(data.get('lead_id'), int):
        raise ValueError('Erwartet: {lead_id, key}.')
    match = next((a for a in suggest_actions(conn, data['lead_id']) if a['key'] == data.get('key')), None)
    if not match:
        raise ValueError('Vorschlag nicht (mehr) verfügbar.')
    due = data.get('due_date') or (dt.date.today() + dt.timedelta(days=2)).isoformat()
    dt.date.fromisoformat(due)
    cur = conn.execute('''INSERT INTO tasks(lead_id, title, due_date, action_type, source, channel, contact_id, permission_status)
                          VALUES (?,?,?,?,?,?,?,?)''',
                       (match['lead_id'], match['title'][:250], due, match['action_type'], f"vorschlag:{match['key']}", match['channel'],
                        match['contact_id'], 'zu_pruefen' if match['requires_permission'] else 'nicht_erforderlich'))
    conn.commit()
    return {'task_id': cur.lastrowid, 'requires_permission': match['requires_permission']}


def dismiss_suggestion(conn, data):
    if not isinstance(data, dict) or set(data) != {'lead_id', 'key'} or not isinstance(data['lead_id'], int) or not isinstance(data['key'], str):
        raise ValueError('Erwartet: {lead_id, key}.')
    conn.execute('INSERT OR IGNORE INTO action_dismissals(lead_id, action_key) VALUES (?,?)', (data['lead_id'], data['key'][:120]))
    conn.commit()
    return {'dismissed': True}


def review_permission(conn, task_id, data):
    """Freigabe einer Kontaktaktion: prüft Lead-Rechtsstatus, Kanal und Beschränkungen der Person."""
    if not isinstance(data, dict) or set(data) - {'decision', 'channel', 'basis'} or data.get('decision') not in ('freigeben', 'ablehnen'):
        raise ValueError('Erwartet: {decision: freigeben|ablehnen, channel, basis}.')
    t = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not t:
        raise LookupError('Aufgabe nicht gefunden.')
    if t['permission_status'] == 'nicht_erforderlich':
        raise ValueError('Diese Aufgabe ist keine Kontaktaktion.')
    basis = str(data.get('basis') or '').strip()
    if data['decision'] == 'ablehnen':
        conn.execute("UPDATE tasks SET permission_status='abgelehnt', permission_basis=?, permission_checked_at=datetime('now') WHERE id=?", (basis[:500], task_id))
        conn.commit()
        return {'permission_status': 'abgelehnt'}
    channel = data.get('channel') or t['channel']
    if channel not in CONTACT_CHANNELS:
        raise ValueError('Kanal: email, telefon, brief oder persoenlich.')
    if len(basis) < 15:
        raise ValueError('Rechtsgrundlage konkret dokumentieren (z. B. „Opt-in per Formular am 03.11.2026, Umfang: Projektinfos“).')
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (t['lead_id'],)).fetchone()
    if lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
        raise ValueError('Lead ist gesperrt – keine Kontaktaktion.')
    from .workday import assert_contact_allowed
    assert_contact_allowed(conn, lead, 'Kontaktaktion freigeben')  # v1.18: Sperrliste greift auch hier
    perm, evidence = lead['permission'], (lead['permission_evidence'] or '').strip()
    if channel == 'email' and not (perm == 'opt_in' and evidence or perm == 'bestandskunde_pruefen' and evidence):
        raise ValueError('E-Mail-Werbung nur mit dokumentierter Einwilligung (Opt-in) bzw. geprüfter Bestandskunden-Ausnahme (§ 7 Abs. 2 Nr. 3, Abs. 3 UWG).')
    if channel == 'telefon' and not (perm in ('opt_in', 'telefon_einzelfall') and evidence):
        raise ValueError('Telefonische Ansprache nur mit dokumentierter (mutmaßlicher) Einwilligung bzw. Einzelfallprüfung (§ 7 Abs. 2 Nr. 1 UWG).')
    if channel == 'persoenlich' and (lead['contact_route'] or 'unbekannt') not in ('persoenliche_empfehlung', 'veranstaltung', 'netzwerk', 'inbound'):
        raise ValueError('Persönliche Ansprache nur über dokumentierte Empfehlung, Veranstaltung, Netzwerk oder eigene Anfrage.')
    if t['contact_id']:
        c = conn.execute('SELECT contact_restrictions, full_name FROM decision_contacts WHERE id=?', (t['contact_id'],)).fetchone()
        r = set(json.loads(c['contact_restrictions'] or '[]')) if c else set()
        blocked = ('widerspruch' in r or (channel == 'telefon' and 'kein_telefon' in r) or (channel == 'email' and 'keine_email' in r)
                   or ('nur_post' in r and channel != 'brief'))
        if blocked:
            raise ValueError(f"Kontaktbeschränkung von {c['full_name']} verbietet diesen Kanal ({', '.join(RESTRICTIONS[x] for x in sorted(r))}).")
    conn.execute("UPDATE tasks SET permission_status='freigegeben', channel=?, permission_basis=?, permission_checked_at=datetime('now') WHERE id=?",
                 (channel, basis[:500], task_id))
    _audit(conn, 'task', task_id, 'kontakt_freigegeben', f'{channel}: {basis[:200]}')
    conn.commit()
    return {'permission_status': 'freigegeben', 'channel': channel,
            'notice': 'Freigabe dokumentiert. SignalDesk führt keine Kontaktaktion aus – du kontaktierst selbst und protokollierst das Ergebnis.'}


def can_complete_task(conn, task_id):
    t = conn.execute('SELECT permission_status FROM tasks WHERE id=?', (task_id,)).fetchone()
    if t and t['permission_status'] in ('zu_pruefen', 'abgelehnt'):
        return False, ('Kontaktaktion ist noch nicht freigegeben – zuerst Berechtigung prüfen.' if t['permission_status'] == 'zu_pruefen'
                       else 'Kontaktaktion wurde abgelehnt – nicht als erledigt markieren, sondern löschen oder neu planen.')
    return True, ''


# ---------------------------------------------------------------- HTTP-Routen

def route_sales_integration(h, conn, method, route, query):
    m = re.fullmatch(r'/api/leads/(\d+)/(offer-matching|decision-map|action-suggestions)', route)
    if m:
        lid, what = int(m.group(1)), m.group(2)
        if what == 'offer-matching':
            if method == 'POST':
                h._send(200, match_offers(conn, lid))
                return True
            if method == 'GET':
                row = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lid,)).fetchone()
                h._send(200, {'lead_id': lid, 'recommendations': stored_recommendations(conn, lid), 'discovery': discovery_state(dict(row) if row else None)})
                return True
        if what == 'decision-map' and method == 'GET':
            h._send(200, decision_map(conn, lid))
            return True
        if what == 'action-suggestions' and method == 'GET':
            h._send(200, suggest_actions(conn, lid))
            return True
    m = re.fullmatch(r'/api/offer-recommendations/(\d+)/quote-draft', route)
    if m and method == 'GET':
        h._send(200, quote_draft(conn, int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/contacts/(\d+)/roles', route)
    if m and method == 'PATCH':
        h._send(200, update_contact_roles(conn, int(m.group(1)), h._body()))
        return True
    if route == '/api/action-suggestions' and method == 'GET':
        h._send(200, all_suggestions(conn))
        return True
    if route == '/api/action-suggestions/accept' and method == 'POST':
        h._send(201, accept_suggestion(conn, h._body()))
        return True
    if route == '/api/action-suggestions/dismiss' and method == 'POST':
        h._send(200, dismiss_suggestion(conn, h._body()))
        return True
    m = re.fullmatch(r'/api/tasks/(\d+)/permission', route)
    if m and method == 'POST':
        h._send(200, review_permission(conn, int(m.group(1)), h._body()))
        return True
    return False
