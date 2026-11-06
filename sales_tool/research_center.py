"""Research Command Center (Phase 4): eine Arbeitsfläche über alle Recherche-Module.

- Priorisierte Firmenübersicht mit Recherchestand je Schritt (Website, Impressum, Bewertung,
  Signale, Hypothesen, Entscheider, Kontaktweg) und transparenter Recherchepriorität. Fehlen
  Website-Bewertung und Kaufsignale, lautet der Status „Datenlage unzureichend“.
- Fortschritt aller laufenden Aufträge (Lead-Finder, Impressum-Batch, Website-Scoring,
  Karriereseiten, URL-Recherche, Kontakt- und Website-Analyse).
- Gemeinsame Prüfliste: alles, was auf eine menschliche Entscheidung wartet.
- Quellenansicht je Firma, Gesprächsvorbereitung (Dossier als Markdown/JSON), CSV-Export und
  bewusste Übergabe an CRM und Angebotsmodul – ohne automatische Kontaktaufnahme.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re

from .model import as_lead

PRIORITY_WEIGHTS = {'website': 40, 'signal': 30, 'fit': 30}
STEP_LABELS = {
    'website': 'Website hinterlegt', 'imprint': 'Impressum geprüft', 'scored': 'Website bewertet', 'signals': 'Kaufsignale erfasst',
    'hypotheses': 'Signale verknüpft', 'decision': 'Entscheider recherchiert', 'channel': 'Kontaktweg geklärt',
}
NEXT_STEPS = {
    'website': ('Website im Lead ergänzen', 'leads'), 'imprint': ('Impressum prüfen', 'datacheck'),
    'scored': ('Website bewerten', 'scoring'), 'signals': ('Karriereseite prüfen oder Bekanntmachungen importieren', 'signals'),
    'hypotheses': ('Signale verknüpfen', 'signals'), 'decision': ('Entscheider recherchieren (Lead öffnen)', 'leads'),
    'channel': ('Zulässigen Kontaktweg klären und dokumentieren', 'leads'),
}
OPEN_STAGES = ('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot')


# ---------------------------------------------------------------- Übersicht

def _lead_rows(conn, include_closed=False):
    sql = 'SELECT * FROM leads' + ('' if include_closed else f" WHERE stage IN ({','.join('?' for _ in OPEN_STAGES)})")
    return [as_lead(r) for r in conn.execute(sql, () if include_closed else OPEN_STAGES)]


def lead_status(conn, lead, weights=None, stale_cfg=None):
    from .buying_signals import signal_strength_for_scoring
    from .quality import lead_staleness, priority_weights
    weights = weights or priority_weights(conn)
    lid = lead['id']
    ws = conn.execute('''SELECT s.overall, s.potential, s.coverage, s.audit_id, v.hash, v.active, a.finished_at FROM website_scores s
                         JOIN website_audits a ON a.id=s.audit_id JOIN score_versions v ON v.id=s.version_id
                         WHERE s.lead_id=? ORDER BY s.id DESC LIMIT 1''', (lid,)).fetchone()
    running = conn.execute("SELECT 1 FROM website_audits WHERE lead_id=? AND status IN ('queued','running')", (lid,)).fetchone()
    sig = conn.execute("""SELECT COUNT(*) AS n, SUM(polarity='pro') AS pro, SUM(polarity='contra') AS contra, SUM(is_new) AS new,
                          MAX(COALESCE(NULLIF(published_at,''), found_at)) AS latest FROM buying_signals WHERE lead_id=? AND status<>'verworfen'""", (lid,)).fetchone()
    scans = conn.execute("SELECT COUNT(*) FROM signal_scans WHERE lead_id=? AND status='done'", (lid,)).fetchone()[0]
    hyp = conn.execute('SELECT strength, score, hypothesis FROM signal_correlations WHERE lead_id=? ORDER BY score DESC LIMIT 1', (lid,)).fetchone()
    dm = conn.execute("""SELECT COUNT(*) AS n, SUM(verification_status IN ('quelle_geprueft','rolle_bestaetigt')) AS checked,
                         SUM(verification_status='rolle_bestaetigt') AS confirmed FROM decision_contacts WHERE lead_id=?""", (lid,)).fetchone()
    facts = conn.execute("SELECT SUM(status='bestaetigt') AS ok, SUM(status='ungeprueft') AS open FROM company_facts WHERE lead_id=?", (lid,)).fetchone()
    key_fields = ('legal_name', 'street', 'zip', 'city', 'register_number')
    data_pct = round(100 * sum(1 for k in key_fields if lead.get(k)) / len(key_fields))
    signal_score, signal_basis = signal_strength_for_scoring(conn, lid)
    steps = {
        'website': bool(lead.get('website')),
        'imprint': bool(lead.get('imprint_checked_at')),
        'scored': ws is not None,
        'signals': bool(sig['n']) or scans > 0 or (lead.get('signal_type') not in (None, '', 'kein_signal')),
        'hypotheses': hyp is not None,
        'decision': bool(dm['checked']),
        'channel': lead.get('permission') not in (None, '', 'unbekannt') or lead.get('contact_route') not in (None, '', 'unbekannt'),
    }
    open_steps = [k for k, done in steps.items() if not done]
    if lead['stage'] == 'gesperrt' or lead.get('permission') == 'nicht_kontaktieren':
        next_step = {'label': 'Gesperrt – keine weitere Recherche zur Ansprache', 'view': 'leads', 'step': None}
    elif open_steps:
        k = open_steps[0]
        next_step = {'label': NEXT_STEPS[k][0], 'view': NEXT_STEPS[k][1], 'step': k}
    else:
        next_step = {'label': 'Gesprächsvorbereitung ansehen und an CRM/Angebot übergeben', 'view': 'center', 'step': 'ready'}
    website_value = None
    if ws is not None:
        website_value = ws['overall'] if ws['overall'] is not None else None
    components = {'website': website_value, 'signal': signal_score, 'fit': lead['score']}
    priority, basis = research_priority(components, ws, signal_basis, weights)
    lead_row = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
    stale = lead_staleness(conn, lead_row, stale_cfg) if lead_row else []
    return {
        'lead_id': lid, 'company': lead['company'], 'website': lead.get('website', ''), 'stage': lead['stage'],
        'permission': lead.get('permission'), 'contact_route': lead.get('contact_route'), 'fit_score': lead['score'],
        'data_pct': data_pct, 'facts_confirmed': facts['ok'] or 0, 'facts_open': facts['open'] or 0,
        'website_overall': ws['overall'] if ws else None, 'website_coverage': ws['coverage'] if ws else None,
        'website_version': (ws['hash'] + ('' if ws['active'] else ' (alt)')) if ws else None, 'website_running': bool(running),
        'website_audit_id': ws['audit_id'] if ws else None,
        'signals': sig['n'] or 0, 'signals_pro': sig['pro'] or 0, 'signals_contra': sig['contra'] or 0, 'signals_new': sig['new'] or 0,
        'signal_latest': sig['latest'] or '', 'signal_score': signal_score,
        'hypothesis': dict(hyp) if hyp else None,
        'decision_makers': dm['n'] or 0, 'decision_checked': dm['checked'] or 0, 'decision_confirmed': dm['confirmed'] or 0,
        'steps': steps, 'readiness_pct': round(100 * sum(steps.values()) / len(steps)), 'next_step': next_step,
        'priority': priority, 'priority_basis': basis,
        'stale': [{'kind': x['kind'], 'label': x['label'], 'detail': x['detail']} for x in stale],
        'changes_open': conn.execute("SELECT COUNT(*) FROM change_events WHERE lead_id=? AND status='offen'", (lid,)).fetchone()[0],
    }


def research_priority(components, ws, signal_basis, weights=None):
    """Transparente Recherchepriorität (keine Kaufwahrscheinlichkeit). Gewichte sind einstellbar (Phase 6)."""
    weights = weights or PRIORITY_WEIGHTS
    if components['website'] is None and components['signal'] is None:
        reason = 'Datenlage unzureichend: weder belastbare Website-Bewertung noch Kaufsignale.'
        if ws is not None and ws['overall'] is None:
            reason = 'Datenlage unzureichend: Website-Bewertung ohne ausreichende Belege, keine Kaufsignale.'
        return None, reason
    known = {k: v for k, v in components.items() if v is not None}
    total_w = sum(weights[k] for k in known)
    if not total_w:
        return None, 'Datenlage unzureichend für die eingestellte Gewichtung (vorhandene Werte haben das Gewicht 0).'
    value = round(sum(weights[k] * v for k, v in known.items()) / total_w)
    parts = [f"Website {components['website'] if components['website'] is not None else 'unbekannt'}",
             f"Kaufsignale {components['signal'] if components['signal'] is not None else 'unbekannt'}",
             f"Lead-Fit {components['fit']}"]
    missing = [k for k, v in components.items() if v is None]
    note = f" · ohne {', '.join({'website': 'Website', 'signal': 'Signale'}[m] for m in missing)} (Gewichte neu verteilt)" if missing else ''
    return value, f"Gewichtung {weights['website']}/{weights['signal']}/{weights['fit']}: " + ', '.join(parts) + note + (f' · {signal_basis}' if signal_basis else '')


def overview(conn, include_closed=False):
    from .quality import priority_weights, stale_days
    weights, cfg = priority_weights(conn), stale_days(conn)
    rows = [lead_status(conn, l, weights, cfg) for l in _lead_rows(conn, include_closed)]
    rows.sort(key=lambda r: (r['priority'] is None, -(r['priority'] or 0), -r['readiness_pct'], r['company'].lower()))
    funnel = {k: sum(1 for r in rows if r['steps'][k]) for k in STEP_LABELS}
    return {'leads': rows, 'funnel': funnel, 'step_labels': STEP_LABELS, 'weights': weights, 'stale_leads': sum(1 for r in rows if r['stale']),
            'ready': sum(1 for r in rows if r['next_step']['step'] == 'ready'),
            'insufficient': sum(1 for r in rows if r['priority'] is None),
            'notice': 'Recherchepriorität = wo sich weitere Recherche und ein Gesprächsversuch am ehesten lohnen. Keine Kaufwahrscheinlichkeit, kein Budget, keine Kontakterlaubnis.'}


# ---------------------------------------------------------------- Aufträge

def jobs(conn):
    out = []

    def add(kind, label, status, created, view, progress=None, detail=''):
        out.append({'kind': kind, 'label': label, 'status': status, 'created_at': created, 'view': view, 'progress': progress, 'detail': detail})

    recent = "datetime('now','-3 day')"
    for r in conn.execute(f"SELECT * FROM discovery_runs WHERE status='running' OR created_at>={recent} ORDER BY id DESC LIMIT 10"):
        add('Lead-Finder', r['source'], r['status'], r['created_at'], 'finder', None, f"{r['result_count']} Treffer" if r['status'] == 'done' else r['error'])
    for r in conn.execute(f"SELECT * FROM batch_runs WHERE status IN ('running','paused') OR created_at>={recent} ORDER BY id DESC LIMIT 10"):
        done = conn.execute("SELECT COUNT(*) FROM batch_items WHERE run_id=? AND status NOT IN ('pending','running')", (r['id'],)).fetchone()[0]
        add('Impressumsprüfung', r['label'], r['status'], r['created_at'], 'datacheck', round(100 * done / r['total']) if r['total'] else 100, f'{done}/{r["total"]} geprüft')
    for r in conn.execute(f"""SELECT a.*, l.company FROM website_audits a JOIN leads l ON l.id=a.lead_id
                              WHERE a.status IN ('queued','running') OR a.created_at>={recent} ORDER BY a.id DESC LIMIT 15"""):
        add('Website-Bewertung', r['company'], r['status'], r['created_at'], 'scoring', None, r['error'])
    for r in conn.execute(f"""SELECT s.*, l.company FROM signal_scans s JOIN leads l ON l.id=s.lead_id
                              WHERE s.status IN ('queued','running') OR s.created_at>={recent} ORDER BY s.id DESC LIMIT 15"""):
        add('Karriereseite', r['company'], r['status'], r['created_at'], 'signals', None, r['error'] or (f"{r['found']} Signal(e)" if r['status'] == 'done' else ''))
    for r in conn.execute(f"SELECT * FROM quick_scans WHERE status IN ('queued','running') OR created_at>={recent} ORDER BY id DESC LIMIT 10"):
        add('URL-Recherche', r['url'], r['status'], r['created_at'], 'research', None, r['error'])
    for r in conn.execute(f"""SELECT r.*, l.company FROM company_reports r JOIN leads l ON l.id=r.lead_id
                              WHERE r.status IN ('queued','running') OR r.created_at>={recent} ORDER BY r.id DESC LIMIT 10"""):
        steps = json.loads(r['steps_json'] or '{}')
        done = sum(1 for x in steps.values() if x.get('status') not in ('wartet', 'läuft'))
        add('report', f"Firmen-Bericht: {r['company']}", r['status'], r['created_at'], 'center', round(100 * done / max(1, len(steps))), f"{done}/{len(steps)} Schritte")
    for r in conn.execute(f"""SELECT c.*, l.company FROM contact_research_runs c JOIN leads l ON l.id=c.lead_id
                              WHERE c.status IN ('queued','running') OR c.created_at>={recent} ORDER BY c.id DESC LIMIT 10"""):
        add('Entscheider-Recherche', r['company'], r['status'], r['created_at'], 'leads', None, r['error'])
    active = [j for j in out if j['status'] in ('queued', 'running', 'paused')]
    out.sort(key=lambda j: (j['status'] not in ('queued', 'running', 'paused'), -_ts(j['created_at'] or '')))
    return {'active': len(active), 'jobs': out[:40]}


def _ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace(' ', 'T')).timestamp()
    except ValueError:
        return 0


# ---------------------------------------------------------------- Prüfliste

def review_queue(conn):
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0] or 0
    items = [
        {'key': 'finder', 'label': 'Lead-Finder-Treffer prüfen', 'count': q("SELECT COUNT(*) FROM discovery_candidates WHERE status='neu'"), 'view': 'finder'},
        {'key': 'imprint', 'label': 'Ausgelesene Impressen übernehmen oder verwerfen', 'count': q("SELECT COUNT(*) FROM batch_items WHERE status='done' AND review_status='offen'"), 'view': 'datacheck'},
        {'key': 'signals_new', 'label': 'Neue Kaufsignale sichten', 'count': q("SELECT COUNT(*) FROM buying_signals WHERE is_new=1 AND status<>'verworfen'"), 'view': 'signals'},
        {'key': 'signals_unassigned', 'label': 'Kaufsignale einer Firma zuordnen', 'count': q("SELECT COUNT(*) FROM buying_signals WHERE lead_id IS NULL AND status<>'verworfen'"), 'view': 'signals'},
        {'key': 'website_findings', 'label': 'Auffällige Website-Befunde bestätigen (letzte Bewertung je Firma)',
         'count': q("""SELECT COUNT(*) FROM website_findings f WHERE f.result='auffaellig' AND f.review_status='ungeprueft'
                       AND f.audit_id IN (SELECT MAX(id) FROM website_audits WHERE status='done' GROUP BY lead_id)"""), 'view': 'scoring'},
        {'key': 'facts', 'label': 'Ungeprüfte Feldbelege (Firmendaten)', 'count': q("SELECT COUNT(*) FROM company_facts WHERE status='ungeprueft'"), 'view': 'leads'},
        {'key': 'contacts', 'label': 'Entscheider-Kandidaten prüfen', 'count': q("SELECT COUNT(*) FROM contact_candidates WHERE status='ungeprueft'")
         + q("SELECT COUNT(*) FROM decision_contacts WHERE verification_status='ungeprueft'"), 'view': 'leads'},
        {'key': 'website_hypotheses', 'label': 'KI-/Regel-Befunde der URL-Recherche freigeben', 'count': q("SELECT COUNT(*) FROM findings WHERE review_status='ungeprueft'"), 'view': 'studio'},
        {'key': 'privacy', 'label': 'Art.-14-Information überfällig', 'count': q("""SELECT COUNT(*) FROM privacy_records WHERE art14_informed_at=''
                     AND collected_at <= datetime('now','-30 day')"""), 'view': 'datacheck'},
        {'key': 'changes', 'label': 'Erkannte Änderungen prüfen (Impressum, Website, Register)', 'count': q("SELECT COUNT(*) FROM change_events WHERE status='offen'"), 'view': 'quality'},
        {'key': 'retention', 'label': 'Löschfrist für Personendaten abgelaufen', 'count': q("SELECT COUNT(*) FROM privacy_records WHERE retention_until<>'' AND retention_until < date('now')"), 'view': 'quality'},
    ]
    return {'items': items, 'total': sum(i['count'] for i in items)}


# ---------------------------------------------------------------- Quellen & Dossier

def sources(conn, lead_id):
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    out = []

    def add(module, kind, url, excerpt='', date='', status='', note=''):
        out.append({'module': module, 'type': kind, 'url': url or '', 'excerpt': (excerpt or '')[:400], 'date': date or '', 'status': status, 'note': note})

    if lead['website']:
        add('Lead', 'Website', lead['website'])
    if lead['signal_source']:
        add('Lead', 'Signal (manuell)', lead['signal_source'], lead['signal_note'], lead['signal_date'])
    for f in conn.execute('SELECT * FROM company_facts WHERE lead_id=? ORDER BY field', (lead_id,)):
        add('Firmendaten', f['field'], f['source_url'], f"{f['value']} – „{f['excerpt']}“" if f['excerpt'] else f['value'], f['checked_at'], f['status'], f['method'])
    a = conn.execute("SELECT * FROM website_audits WHERE lead_id=? AND status='done' ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone()
    if a:
        cap = json.loads(a['capture_json'] or '{}')
        for p in cap.get('pages', []):
            add('Website-Bewertung', 'Gerenderte Seite' if a['renderer'] == 'playwright' else 'HTML-Seite', p.get('url'), '', a['finished_at'], '', a['renderer'])
        for s in conn.execute('SELECT id, page_url, kind FROM website_screenshots WHERE audit_id=?', (a['id'],)):
            add('Website-Bewertung', f"Screenshot ({s['kind']})", f"/api/screenshots/{s['id']}", s['page_url'], a['finished_at'])
        for f in conn.execute("SELECT * FROM website_findings WHERE audit_id=? AND result='auffaellig' ORDER BY weight DESC LIMIT 8", (a['id'],)):
            add('Website-Bewertung', f"Befund: {f['label']}", f['source_url'], f['evidence'], a['finished_at'], f['review_status'], f['certainty'])
    for s in conn.execute("SELECT * FROM buying_signals WHERE lead_id=? AND status<>'verworfen' ORDER BY id DESC", (lead_id,)):
        for src in json.loads(s['sources_json'] or '[]'):
            add('Kaufsignale', f"{s['title']} ({src.get('type')})", src.get('url'), s['evidence'], s['published_at'] or s['found_at'], s['status'])
    for c in conn.execute('SELECT * FROM decision_contacts WHERE lead_id=?', (lead_id,)):
        add('Entscheider', f"{c['full_name']} – {c['job_title']}", c['source_url'] or c['linkedin_url'], c['source_excerpt'], c['verification_date'], c['verification_status'])
    for q in conn.execute("SELECT id, url, finished_at FROM quick_scans WHERE lead_id=? AND status='done'", (lead_id,)):
        add('URL-Recherche', 'Recherchebericht', q['url'], '', q['finished_at'])
    return out


def dossier(conn, lead_id):
    """Gesprächsvorbereitung: belegte Fakten, Beobachtungen und Hypothesen – Interpretationen getrennt von Fakten."""
    from .sales_workspace import PACKAGES
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    st = lead_status(conn, as_lead(lead))
    facts = {r['field']: r for r in conn.execute("SELECT * FROM company_facts WHERE lead_id=? AND status='bestaetigt' ORDER BY id DESC", (lead_id,))}
    a = conn.execute("SELECT * FROM website_audits WHERE lead_id=? AND status='done' ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone()
    summary = json.loads(a['summary_json']) if a else {}
    hyps = [dict(r) for r in conn.execute('SELECT * FROM signal_correlations WHERE lead_id=? ORDER BY score DESC', (lead_id,))]
    signals = [dict(r) for r in conn.execute("SELECT title, published_at, found_at, polarity, status, evidence FROM buying_signals WHERE lead_id=? AND status<>'verworfen' ORDER BY COALESCE(NULLIF(published_at,''), found_at) DESC LIMIT 10", (lead_id,))]
    contacts = [dict(r) for r in conn.execute('SELECT full_name, job_title, decision_role, verification_status, source_url FROM decision_contacts WHERE lead_id=?', (lead_id,))]
    disc = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lead_id,)).fetchone()
    questions = []
    for h in hyps:
        questions += [q for q in json.loads(h['questions_json']) if q not in questions]
    questions += [q for q in summary.get('questions', []) if q not in questions]
    offers = []
    for h in hyps:
        offers += [o for o in json.loads(h['offers_json']) if o not in offers]
    offers += [o['key'] for o in summary.get('offers', []) if o['key'] not in offers]
    data = {
        'company': lead['company'], 'website': lead['website'], 'stage': lead['stage'], 'permission': lead['permission'], 'contact_route': lead['contact_route'],
        'facts': {k: {'value': v['value'], 'source': v['source_url'], 'excerpt': v['excerpt']} for k, v in facts.items()},
        'priority': st['priority'], 'priority_basis': st['priority_basis'], 'readiness_pct': st['readiness_pct'], 'next_step': st['next_step']['label'],
        'website': {'overall': st['website_overall'], 'coverage': st['website_coverage'], 'observations': [{'issue': o.get('issue') or o['label'], 'evidence': o['evidence'], 'certainty': o['certainty'], 'source': o.get('source_url')} for o in summary.get('observations', [])[:6]],
                    'uncertainties': summary.get('uncertainties', [])[:6]} if a else None,
        'signals': signals, 'hypotheses': [{'hypothesis': h['hypothesis'], 'strength': h['strength'], 'counter': json.loads(h['counter_json'])[:3], 'missing': json.loads(h['missing_json'])[:4]} for h in hyps],
        'decision_makers': contacts, 'discovery': {k: disc[k] for k in ('problem', 'impact', 'desired_outcome', 'timing', 'decision_process', 'budget_status')} if disc else None,
        'questions': questions[:7] or ['Welches Ziel soll die Website in den nächsten zwölf Monaten vor allem erfüllen?'],
        'offers': [{'key': o, 'title': PACKAGES[o]['title']} for o in offers if o in PACKAGES][:3],
        'generated_at': dt.datetime.now().strftime('%d.%m.%Y %H:%M'),
    }
    data['markdown'] = _dossier_md(data)
    return data


def _md(s):
    return re.sub(r'[\r\n]+', ' ', str(s or '')).strip()


def _dossier_md(d):
    perm = {'unbekannt': 'ungeklärt – keine Ansprache ohne Prüfung', 'opt_in': 'Opt-in dokumentiert', 'bestandskunde_pruefen': 'Bestandskunde – Voraussetzungen prüfen',
            'telefon_einzelfall': 'Telefon – Einzelfallprüfung', 'nicht_kontaktieren': 'GESPERRT – nicht kontaktieren'}.get(d['permission'], d['permission'])
    L = [f"# Gesprächsvorbereitung: {_md(d['company'])}", f"Erstellt {d['generated_at']} · Website: {_md(d['website']) or '–'}", '',
         f"**Rechtsstatus Kontakt:** {perm} · **Kontaktweg:** {_md(d['contact_route'])}",
         f"**Recherchepriorität:** {d['priority'] if d['priority'] is not None else 'Datenlage unzureichend'} ({_md(d['priority_basis'])})",
         f"**Recherchestand:** {d['readiness_pct']} % · **Nächster Schritt:** {_md(d['next_step'])}", '', '## Geprüfte Firmendaten (Fakten)']
    labels = {'legal_name': 'Firmenname', 'legal_form': 'Rechtsform', 'street': 'Straße', 'zip': 'PLZ', 'city': 'Ort', 'register_court': 'Registergericht',
              'register_number': 'Registernummer', 'vat_id': 'USt-IdNr.', 'business_phone': 'Telefon (allgemein)', 'business_email': 'E-Mail (allgemein)'}
    facts = [f"- {labels[k]}: {_md(v['value'])} (Quelle: {_md(v['source'])})" for k, v in d['facts'].items() if k in labels]
    L += facts or ['- Noch keine bestätigten Firmendaten.']
    L += ['', '## Website-Beobachtungen (belegt, aber Interpretation)']
    if d['website']:
        L.append(f"Gesamtwert {d['website']['overall'] if d['website']['overall'] is not None else 'Datenlage unzureichend'} · Belegabdeckung {d['website']['coverage']} %")
        L += [f"- {_md(o['issue'])} [{o['certainty']}]: {_md(o['evidence'])}" for o in d['website']['observations']] or ['- Keine auffälligen Befunde.']
        if d['website']['uncertainties']:
            L += ['', '*Unsicherheiten:* ' + _md('; '.join(d['website']['uncertainties']))]
    else:
        L.append('- Noch nicht bewertet.')
    L += ['', '## Kaufsignale']
    L += [f"- {_md(s['title'])} ({s['published_at'] or s['found_at']}, {'Gegenhinweis' if s['polarity'] == 'contra' else 'Pro-Hinweis'}, {s['status']}): „{_md(s['evidence'])[:200]}“" for s in d['signals']] or ['- Keine.']
    L += ['', '## Hypothesen (zu bestätigen – keine Fakten)']
    for h in d['hypotheses']:
        L += [f"- **{_md(h['hypothesis'])}** ({h['strength']})", f"  - Gegenhinweise: {_md('; '.join(h['counter'])) or '–'}", f"  - Zur Bestätigung fehlt: {_md('; '.join(h['missing']))}"]
    if not d['hypotheses']:
        L.append('- Noch keine verknüpften Hypothesen.')
    L += ['', '## Ansprechpartner (Recherche, keine bestätigte Entscheidungsbefugnis)']
    L += [f"- {_md(c['full_name'])}, {_md(c['job_title'])} – {c['verification_status']} (Quelle: {_md(c['source_url']) or '–'})" for c in d['decision_makers']] or ['- Noch keine.']
    if d['discovery']:
        L += ['', '## Bereits im Gespräch bestätigt']
        L += [f"- {k}: {_md(v)}" for k, v in d['discovery'].items() if v and v != 'offen'] or ['- Noch nichts bestätigt.']
    L += ['', '## Fragen fürs Erstgespräch'] + [f"{i}. {_md(q)}" for i, q in enumerate(d['questions'], 1)]
    L += ['', '## Mögliche Pakete (unverbindlich bis zur Bedarfsklärung)'] + ([f"- {_md(o['title'])}" for o in d['offers']] or ['- Noch keine Zuordnung.'])
    L += ['', '---', 'Hinweis: Rechercheergebnisse sind keine Einwilligung in Werbung (§ 7 UWG) und keine Aussage über Kaufbereitschaft oder Budget. Hypothesen im Gespräch bestätigen oder verwerfen.']
    return '\n'.join(L) + '\n'


# ---------------------------------------------------------------- Export & Übergabe

def export_csv(conn):
    rows = overview(conn, include_closed=True)['leads']
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', lineterminator='\r\n')
    w.writerow(['Firma', 'Website', 'Phase', 'Rechtsstatus', 'Recherchepriorität', 'Grundlage', 'Recherchestand %', 'Nächster Schritt', 'Website-Gesamt',
                'Belegabdeckung %', 'Kaufsignale', 'davon Gegenhinweise', 'Top-Hypothese', 'Entscheider geprüft', 'Firmendaten %'])
    for r in rows:
        vals = [r['company'], r['website'], r['stage'], r['permission'], '' if r['priority'] is None else r['priority'], r['priority_basis'], r['readiness_pct'],
                r['next_step']['label'], '' if r['website_overall'] is None else r['website_overall'], '' if r['website_coverage'] is None else r['website_coverage'],
                r['signals'], r['signals_contra'], (r['hypothesis'] or {}).get('hypothesis', ''), r['decision_checked'], r['data_pct']]
        w.writerow(["'" + v if isinstance(v, str) and v[:1] in '=+-@' else v for v in vals])
    return '﻿' + buf.getvalue()


def handoff(conn, lead_id, data):
    """Bewusste Übergabe: Phase „qualifiziert“ + Aufgabe „Erstgespräch vorbereiten“. Kein Versand, keine Kontaktaufnahme."""
    if not isinstance(data, dict) or set(data) - {'confirm', 'note'} or data.get('confirm') is not True:
        raise ValueError('Übergabe ausdrücklich bestätigen.')
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    if lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
        raise ValueError('Lead ist gesperrt – keine Übergabe zur Ansprache.')
    st = lead_status(conn, as_lead(lead))
    d = dossier(conn, lead_id)
    stage = lead['stage']
    if stage == 'recherche':
        conn.execute("UPDATE leads SET stage='qualifiziert', updated_at=datetime('now') WHERE id=?", (lead_id,))
        stage = 'qualifiziert'
    perm_ok = lead['permission'] not in ('unbekannt', '')
    task = ('Erstgespräch vorbereiten: Fragen aus dem Recherche-Dossier nutzen' if perm_ok
            else 'Zulässigen Kontaktweg klären (Empfehlung, Messe, Brief) – vorher keine Ansprache')
    due = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    conn.execute('INSERT INTO tasks(lead_id, title, due_date) VALUES (?,?,?)', (lead_id, task, due))
    note = str(data.get('note') or '').strip()[:500]
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lead_id, 'notiz', f"Recherche übergeben (Stand {st['readiness_pct']} %, Priorität {st['priority'] if st['priority'] is not None else 'Datenlage unzureichend'})." + (f' {note}' if note else '')))
    conn.commit()
    return {'stage': stage, 'task': task, 'due_date': due, 'suggested_offers': d['offers'], 'questions': d['questions'],
            'notice': 'Paketvorschläge sind unverbindlich, bis der Bedarf im Gespräch bestätigt ist. Es wurde nichts versendet.'}


# ---------------------------------------------------------------- HTTP-Routen

def route_center(h, conn, method, route, query):
    if not route.startswith('/api/research-center'):
        return False
    if route == '/api/research-center/overview' and method == 'GET':
        h._send(200, overview(conn, query.get('closed', [''])[0] == '1'))
        return True
    if route == '/api/research-center/jobs' and method == 'GET':
        h._send(200, jobs(conn))
        return True
    if route == '/api/research-center/review' and method == 'GET':
        h._send(200, review_queue(conn))
        return True
    if route == '/api/research-center/export.csv' and method == 'GET':
        h._send_raw(200, export_csv(conn).encode('utf-8'), 'text/csv', f'signaldesk-recherche-{dt.date.today().isoformat()}.csv')
        return True
    m = re.fullmatch(r'/api/research-center/leads/(\d+)/(sources|dossier|dossier\.md|dossier\.json|handoff)', route)
    if m:
        lid, what = int(m.group(1)), m.group(2)
        if what == 'sources' and method == 'GET':
            h._send(200, sources(conn, lid))
        elif what == 'dossier' and method == 'GET':
            h._send(200, dossier(conn, lid))
        elif what == 'dossier.md' and method == 'GET':
            d = dossier(conn, lid)
            h._send_raw(200, d['markdown'].encode('utf-8'), 'text/markdown', f"dossier-{re.sub(r'[^A-Za-z0-9]+', '-', d['company'])[:40]}.md")
        elif what == 'dossier.json' and method == 'GET':
            d = dossier(conn, lid)
            d['sources'] = sources(conn, lid)
            h._send_raw(200, json.dumps(d, ensure_ascii=False, indent=2).encode('utf-8'), 'application/json', f'dossier-{lid}.json')
        elif what == 'handoff' and method == 'POST':
            h._send(200, handoff(conn, lid, h._body()))
        else:
            return False
        return True
    return False
