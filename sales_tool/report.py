"""Firmen-Bericht mit einem Klick (Sprint C).

Ein Auftrag je Firma erledigt nacheinander, was bisher in fünf Bereichen einzeln angestoßen werden musste:
1. Impressum & Firmendaten (Impressumsprüfung – Übernahme bleibt eine bewusste Entscheidung),
2. Website-Bewertung (Scorer v2; mit Browser inkl. Screenshots, sonst HTML-Rückfall),
3. Website-Inhalte & Ansprechpartner (URL-Recherche: belegte Beobachtungen, Fragen, öffentliche Ansprechpartner),
4. Karriereseite & Kaufsignale,
5. Signale verknüpfen & passende Pakete (unverbindlich bis zur Bedarfsklärung).
Jeder Schritt hat einen eigenen Status; ein Fehler stoppt die anderen Schritte nicht.
Es wird niemand kontaktiert. Ergebnisse sind Hinweise mit Fundstelle, keine Tatsachenbehauptungen über Kaufbereitschaft.
"""
from __future__ import annotations

import json
import re
import threading

from . import buying_signals as bs
from . import website_analyzer as wa
from . import website_scorer as ws
from .research import jobs
from .company_data import find_duplicate, normalize_domain, check_suppressed

STEPS = (('impressum', 'Impressum & Firmendaten'), ('website', 'Website-Bewertung'), ('inhalte', 'Website-Inhalte & Ansprechpartner'),
         ('signale', 'Karriereseite & Kaufsignale'), ('verknuepfen', 'Signale verknüpfen & passende Pakete'))
MAX_BATCH = 50
_LAST = {}
_WORKER = {'thread': None}
_LOCK = threading.Lock()


def init_report(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS company_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'queued', steps_json TEXT NOT NULL DEFAULT '{}', refs_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_company_reports_lead ON company_reports(lead_id, id);
    ''')


def recover_reports(conn):
    """Neustart: laufende Berichte wieder einreihen; Berichte ohne Auftragsschritt (ältere Versionen) übernehmen."""
    conn.execute("UPDATE company_reports SET status='queued', started_at='' WHERE status='running'")
    adopt_queued_reports(conn)


# ---------------------------------------------------------------- Aufträge anlegen

def lead_for_url(conn, url):
    """Findet den Lead zu einer Website oder legt ihn an (Phase Recherche, Rechtsstatus unbekannt)."""
    from .lead_finder import clean_website
    web = clean_website(url)
    if not web:
        raise ValueError('Bitte eine gültige Website angeben, z. B. https://firma.de')
    dup, _ = find_duplicate(conn, website=web)
    if dup:
        return dup, False
    if check_suppressed(conn, website=web):
        raise ValueError('Diese Domain steht auf der Sperrliste.')
    name = normalize_domain(web)
    cur = conn.execute("""INSERT INTO leads(company, website, industry, stage, permission, note) VALUES (?,?,?,?,?,?)""",
                       (name, web, 'Sonstige', 'recherche', 'unbekannt', 'Angelegt über „Bericht für Website“. Firmenname aus dem Impressum übernehmen.'))
    conn.commit()
    return cur.lastrowid, True


def create_reports(conn, data, db_path, start=True):
    if not isinstance(data, dict) or set(data) - {'lead_ids', 'url'} or not (data.get('lead_ids') or data.get('url')):
        raise ValueError('Erwartet: {lead_ids: [...]} oder {url}.')
    created_lead = None
    if data.get('url'):
        if not isinstance(data['url'], str):
            raise ValueError('url muss Text sein.')
        lid, new = lead_for_url(conn, data['url'])
        ids, created_lead = [lid], (lid if new else None)
    else:
        ids = data['lead_ids']
        if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_BATCH or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
            raise ValueError(f'1–{MAX_BATCH} Lead-IDs angeben.')
    queued, skipped = [], []
    for lid in dict.fromkeys(ids):
        lead = conn.execute('SELECT id, website, stage, permission FROM leads WHERE id=?', (lid,)).fetchone()
        if not lead:
            skipped.append({'lead_id': lid, 'reason': 'nicht gefunden'})
        elif lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
            skipped.append({'lead_id': lid, 'reason': 'gesperrt'})
        elif not lead['website']:
            skipped.append({'lead_id': lid, 'reason': 'keine Website – zuerst Website ergänzen oder in „Firmen finden“ suchen'})
        elif conn.execute("SELECT 1 FROM company_reports WHERE lead_id=? AND status IN ('queued','running')", (lid,)).fetchone():
            skipped.append({'lead_id': lid, 'reason': 'Bericht läuft bereits'})
        else:
            steps = {k: {'label': v, 'status': 'wartet'} for k, v in STEPS}
            cur = conn.execute('INSERT INTO company_reports(lead_id, steps_json) VALUES (?,?)', (lid, json.dumps(steps, ensure_ascii=False)))
            queued.append({'report_id': cur.lastrowid, 'lead_id': lid})
    conn.commit()
    job = _report_job(conn, [q['report_id'] for q in queued], db_path, start) if queued else None
    return {'queued': queued, 'skipped': skipped, 'created_lead': created_lead, 'job_id': job['id'] if job else None}


def _report_job(conn, rids, db_path, start):
    """v1.16 (Sprint 3): ein persistenter Auftrag, ein Schritt je Firma; je Website-Domain höchstens ein Schritt gleichzeitig."""
    rows = conn.execute(f'''SELECT r.id, l.company, l.website FROM company_reports r JOIN leads l ON l.id=r.lead_id
                            WHERE r.id IN ({','.join('?' * len(rids))})''', rids).fetchall()
    tasks = [{'key': f'report:{r["id"]}', 'kind': 'report', 'label': r['company'][:120], 'domain': normalize_domain(r['website']) or '',
              'payload': {'report_id': r['id']}, 'max_attempts': 2} for r in rows]
    job, _ = jobs.submit(conn, 'report', f'Firmen-Berichte ({len(tasks)} Firma/Firmen)' if len(tasks) != 1 else f'Firmen-Bericht: {rows[0]["company"]}'[:200],
                         tasks, db_path=db_path, start=start, priority=4)
    _LAST['db'] = db_path
    return job


def adopt_queued_reports(conn, db_path=None, start=False):
    rows = [r['id'] for r in conn.execute("""SELECT r.id FROM company_reports r WHERE r.status='queued' AND NOT EXISTS (
        SELECT 1 FROM research_tasks t WHERE t.kind='report' AND t.task_key='report:' || r.id AND t.status IN ('queued','running'))""")]
    for i in range(0, len(rows), MAX_BATCH):
        _report_job(conn, rows[i:i + MAX_BATCH], db_path, start)
    return len(rows)


@jobs.handler('report')
def _job_report(db_path, payload, ctx):
    from .model import connect
    rid = payload['report_id']
    with connect(db_path) as conn:
        row = conn.execute('SELECT status FROM company_reports WHERE id=?', (rid,)).fetchone()
        if not row or row['status'] not in ('queued', 'running'):
            raise jobs.Skip('Bericht ist nicht mehr offen.')
        conn.execute("UPDATE company_reports SET status='running', started_at=datetime('now') WHERE id=?", (rid,))
        conn.commit()
    run_report(db_path, rid)
    with connect(db_path) as conn:
        r = conn.execute('SELECT status, steps_json FROM company_reports WHERE id=?', (rid,)).fetchone()
    steps = json.loads(r['steps_json'] or '{}')
    failed = [v.get('label', k) for k, v in steps.items() if v.get('status') == 'fehler']
    out = {'status': r['status'], 'failed_steps': failed}
    if r['status'] != 'fertig' or failed:  # Schritt mit Fehler (z. B. HTTP 403) → im Auftrag sichtbar und erneut ausführbar
        out.update(_status='failed', _error='Bericht unvollständig: ' + ', '.join(failed))
    return out


@jobs.handler('report:retry')
def _job_report_retry(conn, job_id):
    """„Fehlgeschlagene erneut“: betroffene Berichte wieder einreihen (Schritte laufen idempotent erneut)."""
    for t in conn.execute("SELECT payload_json FROM research_tasks WHERE job_id=? AND status='queued'", (job_id,)).fetchall():
        rid = json.loads(t['payload_json'])['report_id']
        steps = {k: {'label': v, 'status': 'wartet'} for k, v in STEPS}
        conn.execute("UPDATE company_reports SET status='queued', started_at='', finished_at='', steps_json=? WHERE id=? AND status<>'running'",
                     (json.dumps(steps, ensure_ascii=False), rid))


@jobs.handler('report:cancel')
def _job_report_cancel(conn, payload):
    conn.execute("UPDATE company_reports SET status='abgebrochen', finished_at=datetime('now') WHERE id=? AND status='queued'", (payload['report_id'],))


def _worker(db_path):
    """Kompatibel zu früher: Berichte synchron abarbeiten (Tests, Werkzeuge) – jetzt über die Auftragsverwaltung."""
    from .model import connect
    with connect(db_path) as conn:
        adopt_queued_reports(conn, db_path, start=False)
    jobs.run_until_idle(db_path, kinds=('report',))


def wait_idle(timeout=120):
    if _LAST.get('db'):
        jobs.wait_idle(_LAST['db'], timeout, kinds=('report',))


# ---------------------------------------------------------------- Ausführung

def _set(conn, rid, key, **kw):
    row = conn.execute('SELECT steps_json, refs_json FROM company_reports WHERE id=?', (rid,)).fetchone()
    steps = json.loads(row['steps_json'])
    refs = json.loads(row['refs_json'])
    ref = kw.pop('ref', None)
    steps[key].update(kw)
    if ref:
        refs.update(ref)
    conn.execute('UPDATE company_reports SET steps_json=?, refs_json=? WHERE id=?', (json.dumps(steps, ensure_ascii=False), json.dumps(refs, ensure_ascii=False), rid))
    conn.commit()


def _step_impressum(conn, db_path, lead):
    # v1.19: gemeinsame Übertragung ins Firmenprofil (lead_imprint) – Firmendaten in LEERE Felder, Personen nie automatisch
    from .lead_imprint import apply_for_lead
    status, note, refs, _ = apply_for_lead(conn, db_path, lead)
    return status, note, refs


def _step_website(conn, db_path, lead):
    cur = conn.execute("INSERT INTO website_audits(lead_id, url, status, started_at) VALUES (?, ?, 'running', datetime('now'))", (lead['id'], lead['website']))
    conn.commit()
    ws.run_audit(db_path, cur.lastrowid)
    a = conn.execute('SELECT status, error, renderer FROM website_audits WHERE id=?', (cur.lastrowid,)).fetchone()
    if a['status'] != 'done':
        return 'fehler', a['error'] or 'Website nicht erreichbar.', {'audit': cur.lastrowid}
    s = conn.execute('SELECT overall, coverage FROM website_scores WHERE audit_id=?', (cur.lastrowid,)).fetchone()
    note = f"Gesamt {s['overall']}" if s and s['overall'] is not None else 'Datenlage unzureichend'
    note += f" · Belegabdeckung {s['coverage']} %" if s else ''
    if a['renderer'] == 'html':
        note += ' · ohne Browser (keine Screenshots, Gestaltung nicht bewertet)'
    return 'fertig', note, {'audit': cur.lastrowid}


def _step_inhalte(conn, db_path, lead):
    from . import quickscan
    crawl = wa.crawl_site(lead['website'], purpose='full')
    result = quickscan.research(crawl, 'rules')
    cur = conn.execute("INSERT INTO quick_scans(url, provider, status, result_json, lead_id, finished_at) VALUES (?, 'rules', 'done', ?, ?, datetime('now'))",
                       (lead['website'], json.dumps(result, ensure_ascii=False), lead['id']))
    scan_id = cur.lastrowid
    run = conn.execute("""INSERT INTO contact_research_runs(lead_id, status, pages_json, channels_json, warnings_json, finished_at)
                          VALUES (?, 'done', ?, ?, ?, datetime('now'))""",
                       (lead['id'], json.dumps(result['site']['pages'], ensure_ascii=False), json.dumps(result['contact_channels'], ensure_ascii=False),
                        json.dumps(result['warnings'], ensure_ascii=False))).lastrowid
    new_people = 0
    for p in result['decision_makers']['people']:
        known = conn.execute('''SELECT 1 FROM decision_contacts WHERE lead_id=? AND lower(full_name)=lower(?)
                                UNION SELECT 1 FROM contact_candidates WHERE lead_id=? AND lower(full_name)=lower(?) AND status<>'abgelehnt' ''',
                             (lead['id'], p['full_name'], lead['id'], p['full_name'])).fetchone()
        if known:
            continue
        conn.execute("""INSERT INTO contact_candidates (run_id, lead_id, full_name, job_title, role_hint, priority, business_email, business_phone,
                        phone_type, source_url, evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (run, lead['id'], *(p.get(k, '') for k in ('full_name', 'job_title', 'role_hint', 'priority', 'business_email', 'business_phone',
                                                                  'phone_type', 'source_url', 'evidence'))))
        new_people += 1
    conn.commit()
    mode = 'ohne Browser' if crawl.get('renderer') == 'html' else 'mit Browser'
    return 'fertig', (f"{len(result['site']['pages'])} Seiten {mode} gelesen · {len(result['audit']['findings'])} belegte Beobachtungen · "
                      f"{new_people} neue Ansprechpartner-Kandidaten"), {'scan': scan_id}


def _step_signale(conn, db_path, lead):
    jobs, log = bs.scan_career(lead['website'], lead['company'])
    found = 0
    for j in jobs:
        res = bs.store_job(conn, j, lead['id'])
        found += bool(res and not res['duplicate'] and res.get('classified'))
    conn.execute("INSERT INTO signal_scans(lead_id, status, found, log_json, finished_at) VALUES (?, 'done', ?, ?, datetime('now'))",
                 (lead['id'], found, json.dumps(log, ensure_ascii=False)))
    conn.commit()
    return 'fertig', f"{len(jobs)} Stellenanzeige(n) gefunden, {found} mit Bezug zu deinen Leistungen" if jobs else 'Keine Stellenanzeigen auf der Website gefunden.', {}


def _step_verknuepfen(conn, db_path, lead):
    from .sales_integration import match_offers
    bs.correlate(conn, lead['id'])
    hyps = conn.execute('SELECT COUNT(*) FROM signal_correlations WHERE lead_id=?', (lead['id'],)).fetchone()[0]
    m = match_offers(conn, lead['id'])
    return 'fertig', f"{hyps} Hypothese(n) · {len(m['recommendations'])} passende Paket(e), unverbindlich bis zur Bedarfsklärung", {}


RUNNERS = {'impressum': _step_impressum, 'website': _step_website, 'inhalte': _step_inhalte, 'signale': _step_signale, 'verknuepfen': _step_verknuepfen}


def run_report(db_path, rid):
    from .model import connect
    with connect(db_path) as conn:
        rep = conn.execute('SELECT * FROM company_reports WHERE id=?', (rid,)).fetchone()
        for key, _ in STEPS:
            lead = conn.execute('SELECT * FROM leads WHERE id=?', (rep['lead_id'],)).fetchone()
            if not lead or lead['stage'] == 'gesperrt':
                _set(conn, rid, key, status='übersprungen', detail='Lead gesperrt oder gelöscht.')
                continue
            _set(conn, rid, key, status='läuft')
            try:
                status, detail, ref = RUNNERS[key](conn, db_path, lead)
                _set(conn, rid, key, status=status, detail=detail[:300], ref=ref)
            except (wa.CrawlError, ValueError) as exc:
                _set(conn, rid, key, status='fehler', detail=str(exc)[:300])
            except Exception as exc:  # ein Schritt darf den Bericht nicht abbrechen
                print('Firmen-Bericht:', key, repr(exc))
                _set(conn, rid, key, status='fehler', detail=f'Unerwarteter Fehler: {exc.__class__.__name__}')
        steps = json.loads(conn.execute('SELECT steps_json FROM company_reports WHERE id=?', (rid,)).fetchone()['steps_json'])
        ok = sum(1 for s in steps.values() if s['status'] == 'fertig')
        conn.execute("UPDATE company_reports SET status=?, finished_at=datetime('now') WHERE id=?", ('fertig' if ok else 'fehler', rid))
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (rep['lead_id'], 'notiz', f'Firmen-Bericht erstellt: {ok} von {len(STEPS)} Schritten erfolgreich.'))
        if ok:  # v1.13: Recherche-Schritt ist erledigt → nächster Schritt Kontaktweg
            from .today import RESEARCH_RE
            lead = conn.execute('SELECT next_step FROM leads WHERE id=?', (rep['lead_id'],)).fetchone()
            if lead and (not lead['next_step'] or RESEARCH_RE.search(lead['next_step'])):
                conn.execute("UPDATE leads SET next_step='Kontaktweg klären (Firmen-Bericht liegt vor)', next_date='' WHERE id=?", (rep['lead_id'],))
        conn.commit()


# ---------------------------------------------------------------- Lesen

def report_view(conn, rid=None, lead_id=None):
    from .research_center import dossier
    if rid is None:
        row = conn.execute('SELECT * FROM company_reports WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lead_id,)).fetchone()
        if not row:
            lead = conn.execute('SELECT id FROM leads WHERE id=?', (lead_id,)).fetchone()
            if not lead:
                raise LookupError('Lead nicht gefunden.')
            return {'report': None, 'lead_id': lead_id, 'dossier': dossier(conn, lead_id)}
    else:
        row = conn.execute('SELECT * FROM company_reports WHERE id=?', (rid,)).fetchone()
        if not row:
            raise LookupError('Bericht nicht gefunden.')
    lid = row['lead_id']
    refs = json.loads(row['refs_json'])
    out = {'report': {'id': row['id'], 'status': row['status'], 'created_at': row['created_at'], 'finished_at': row['finished_at'],
                      'steps': json.loads(row['steps_json'])}, 'lead_id': lid, 'dossier': dossier(conn, lid)}
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
    out['lead'] = {k: lead[k] for k in ('company', 'website', 'stage', 'permission', 'legal_name', 'street', 'zip', 'city', 'register_number',
                                         'business_phone', 'business_email', 'imprint_url')}
    if refs.get('imprint_item'):
        it = conn.execute('SELECT * FROM batch_items WHERE id=?', (refs['imprint_item'],)).fetchone()
        if it and it['result_json']:
            res = json.loads(it['result_json'])
            out['imprint'] = {'item_id': it['id'], 'review_status': it['review_status'], 'status': it['status'], 'url': res.get('imprint_url'),
                              'fields': {k: {'value': v.get('value'), 'excerpt': v.get('excerpt', ''),
                                             'method': (v.get('evidence') or {}).get('method', ''), 'checked_at': (v.get('evidence') or {}).get('checked_at', '')}
                                         for k, v in (res.get('fields') or {}).items() if v and v.get('value')},
                              'structured': {'organizations': (res.get('structured') or {}).get('organizations', [])[:2],
                                             'evidence': (res.get('structured') or {}).get('evidence', [])[:12]},
                              'representatives': [r.get('name') for r in res.get('representatives', []) if r.get('name')][:5],
                              'warnings': res.get('warnings', [])[:4]}
    if refs.get('audit'):
        a = conn.execute('SELECT * FROM website_audits WHERE id=?', (refs['audit'],)).fetchone()
        sc = conn.execute('SELECT * FROM website_scores WHERE audit_id=?', (refs['audit'],)).fetchone()
        if a and a['status'] == 'done':
            summ = json.loads(a['summary_json'] or '{}')
            out['website'] = {'audit_id': a['id'], 'renderer': a['renderer'],
                              'scores': {k: sc[k] for k in ('overall', 'design', 'web', 'process', 'coverage')} if sc else {},
                              'observations': summ.get('observations', [])[:6], 'uncertainties': summ.get('uncertainties', [])[:5],
                              'screenshots': [r['id'] for r in conn.execute('SELECT id FROM website_screenshots WHERE audit_id=? ORDER BY id LIMIT 2', (a['id'],))]}
    if refs.get('scan'):
        q = conn.execute('SELECT result_json FROM quick_scans WHERE id=?', (refs['scan'],)).fetchone()
        r = json.loads(q['result_json'] or '{}') if q else {}
        out['inhalte'] = {'findings': [{'category': f.get('category'), 'observation': f.get('observation'), 'hypothesis': f.get('hypothesis'),
                                        'evidence': f.get('evidence'), 'source_url': f.get('source_url'), 'offer': f.get('offer')}
                                       for f in (r.get('audit') or {}).get('findings', [])[:6]],
                          'channels': r.get('contact_channels', [])[:8], 'pages': (r.get('site') or {}).get('pages', [])[:6],
                          'warnings': r.get('warnings', [])[:5]}
    out['candidates'] = [dict(c) for c in conn.execute("""SELECT id, full_name, job_title, role_hint, source_url, evidence, business_email, business_phone
                                                          FROM contact_candidates WHERE lead_id=? AND status='ungeprueft' ORDER BY priority DESC, id LIMIT 12""", (lid,))]
    out['contacts'] = [dict(c) for c in conn.execute('SELECT id, full_name, job_title, verification_status, source_url FROM decision_contacts WHERE lead_id=?', (lid,))]
    from .sales_integration import stored_recommendations
    out['offers'] = [{'package': r['package'], 'title': r['title'], 'status': r['status'], 'hints': r['hints'][:3], 'confirmed': r['confirmed'][:3]}
                     for r in stored_recommendations(conn, lid)][:5]
    out['notice'] = ('Hinweise mit Fundstelle, keine Tatsachen über Bedarf oder Kaufbereitschaft. Pakete sind unverbindlich bis zur '
                     'dokumentierten Bedarfsklärung. Ein Fund ist keine Kontakterlaubnis.')
    return out


def report_rows(conn, limit=60):
    return [dict(r) for r in conn.execute('''SELECT r.id, r.lead_id, r.status, r.created_at, r.finished_at, l.company FROM company_reports r
                                             JOIN leads l ON l.id=r.lead_id ORDER BY r.id DESC LIMIT ?''', (limit,))]


# ---------------------------------------------------------------- HTTP

def route_report(h, conn, method, route, query, db_path):
    if route == '/api/reports':
        if method == 'GET':
            h._send(200, report_rows(conn))
            return True
        if method == 'POST':
            h._send(202, create_reports(conn, h._body(), db_path))
            return True
    m = re.fullmatch(r'/api/reports/(\d+)', route)
    if m and method == 'GET':
        h._send(200, report_view(conn, rid=int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/leads/(\d+)/report', route)
    if m and method == 'GET':
        h._send(200, report_view(conn, lead_id=int(m.group(1))))
        return True
    return False
