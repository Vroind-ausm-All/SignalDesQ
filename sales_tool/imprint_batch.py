"""Batch-Impressumsprüfung (Phase 1): 1–100 Domains mit Pause/Fortsetzen und Prüfwarteschlange.

- Begrenzte Parallelität (1–3), je Domain nacheinander mit Pause zwischen den Abrufen.
- Fehler einer Website brechen den Lauf nie ab; sie landen im Fehlerprotokoll des Eintrags.
- Sperrliste und Dubletten (Domain, Register, Name) werden vor und nach der Extraktion geprüft.
- Ins CRM gelangt nur, was in der Prüfwarteschlange ausdrücklich übernommen wird.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from . import imprint
from .company_data import (add_fact, add_privacy_record, assert_not_suppressed, check_suppressed, find_duplicate,
                           normalize_domain, _audit)
from .model import connect
from .website_analyzer import CrawlError

MAX_ITEMS = 100
_RUNNERS: dict[int, threading.Thread] = {}
_LOCK = threading.Lock()
APPLY_FIELDS = ('legal_name', 'legal_form', 'street', 'zip', 'city', 'register_court', 'register_number', 'vat_id',
                'business_phone', 'business_email')


def init_imprint_batch(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS batch_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'impressum',
        status TEXT NOT NULL DEFAULT 'running', label TEXT NOT NULL DEFAULT '', options_json TEXT NOT NULL DEFAULT '{}',
        total INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS batch_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES batch_runs(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, input TEXT NOT NULL, domain TEXT NOT NULL, company_hint TEXT NOT NULL DEFAULT '',
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '', log_json TEXT NOT NULL DEFAULT '[]',
        result_json TEXT NOT NULL DEFAULT '', duplicate_lead_id INTEGER, duplicate_reason TEXT NOT NULL DEFAULT '',
        review_status TEXT NOT NULL DEFAULT 'offen', started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_batch_items_run ON batch_items(run_id, status);
    ''')


def recover_batches(conn):
    """Nach Neustart: laufende Einträge zurücksetzen, Läufe pausieren (Fortsetzen per Klick)."""
    conn.execute("UPDATE batch_items SET status='pending', started_at='' WHERE status='running'")
    conn.execute("UPDATE batch_runs SET status='paused' WHERE status='running'")


# ---------------------------------------------------------------- Eingabe

def parse_input(text='', csv_text='', lead_id=None):
    """Akzeptiert eine Domainliste (eine pro Zeile) oder CSV mit Spalte website/url/domain (+ optional company)."""
    items = []
    if csv_text:
        csv_text = csv_text.lstrip('﻿')
        header = csv_text.splitlines()[0] if csv_text.strip() else ''
        delimiter = max((';', ',', '\t'), key=header.count)  # Excel (DE) nutzt meist „;“
        reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
        keys = {k.lower().strip(): k for k in (reader.fieldnames or []) if k}
        col = next((keys[k] for k in ('website', 'url', 'domain', 'webseite', 'homepage') if k in keys), None)
        name_col = next((keys[k] for k in ('company', 'firma', 'unternehmen', 'name') if k in keys), None)
        if not col:
            raise ValueError('CSV braucht eine Spalte „website“, „url“ oder „domain“.')
        for row in reader:
            items.append(((row.get(col) or '').strip(), (row.get(name_col) or '').strip() if name_col else ''))
    for line in (text or '').splitlines():
        line = line.strip().strip(',;')
        if line and not line.startswith('#'):
            items.append((line, ''))
    out, seen, rejected = [], set(), []
    for raw, hint in items:
        if not raw:
            continue
        domain = normalize_domain(raw)
        if not domain or '.' not in domain or not re.fullmatch(r'[a-z0-9äöüß.\-]+', domain):
            rejected.append(raw[:80])
            continue
        if domain in seen:
            continue
        seen.add(domain)
        out.append({'input': raw[:300], 'domain': domain, 'company_hint': hint[:200]})
    if not out:
        raise ValueError('Keine gültigen Domains gefunden.')
    if len(out) > MAX_ITEMS:
        raise ValueError(f'Höchstens {MAX_ITEMS} Domains pro Lauf ({len(out)} angegeben).')
    return out, rejected


def create_run(conn, data, db_path, start=True):
    if not isinstance(data, dict) or set(data) - {'domains', 'csv', 'label', 'parallel', 'include_persons', 'lead_id'}:
        raise ValueError('Ungültige Batch-Optionen.')
    parallel = data.get('parallel', 2)
    if isinstance(parallel, bool) or parallel not in (1, 2, 3):
        raise ValueError('Parallelität: 1, 2 oder 3.')
    include_persons = data.get('include_persons', True)
    if not isinstance(include_persons, bool):
        raise ValueError('include_persons: true/false.')
    lead_id = data.get('lead_id')
    if lead_id is not None:
        lead = conn.execute('SELECT id, website FROM leads WHERE id=?', (lead_id,)).fetchone() if isinstance(lead_id, int) else None
        if not lead or not lead['website']:
            raise ValueError('Lead nicht gefunden oder ohne Website.')
        items, rejected = parse_input(lead['website'])
    else:
        text, csv_text = data.get('domains') or '', data.get('csv') or ''
        if not isinstance(text, str) or not isinstance(csv_text, str) or len(text) + len(csv_text) > 300_000:
            raise ValueError('Eingabe ungültig oder zu groß.')
        items, rejected = parse_input(text, csv_text)
    label = str(data.get('label') or '').strip()[:120] or f"{len(items)} Domain(s) vom {dt.date.today().strftime('%d.%m.%Y')}"
    cur = conn.execute('INSERT INTO batch_runs(label, options_json, total) VALUES (?,?,?)',
                       (label, json.dumps({'parallel': parallel, 'include_persons': include_persons}), len(items)))
    run_id = cur.lastrowid
    skipped = 0
    for pos, item in enumerate(items, 1):
        hits = check_suppressed(conn, website=item['domain'], name=item['company_hint'])
        status, error = ('gesperrt', 'Auf der Sperrliste – nicht abgerufen.') if hits else ('pending', '')
        skipped += bool(hits)
        dup, reason = find_duplicate(conn, website=item['domain'], name=item['company_hint'])
        conn.execute('''INSERT INTO batch_items(run_id, position, input, domain, company_hint, lead_id, status, error, duplicate_lead_id, duplicate_reason)
                        VALUES (?,?,?,?,?,?,?,?,?,?)''',
                     (run_id, pos, item['input'], item['domain'], item['company_hint'], lead_id, status, error, dup or lead_id, reason or ('lead' if lead_id else '')))
    conn.commit()
    if start:
        start_runner(db_path, run_id)
    return {**run_detail(conn, run_id), 'rejected': rejected, 'skipped_suppressed': skipped}


# ---------------------------------------------------------------- Ausführung

def start_runner(db_path, run_id):
    with _LOCK:
        t = _RUNNERS.get(run_id)
        if t and t.is_alive():
            return False
        t = threading.Thread(target=_run, args=(db_path, run_id), daemon=True, name=f'impressum-batch-{run_id}')
        _RUNNERS[run_id] = t
        t.start()
        return True


def wait_for(run_id, timeout=30):
    t = _RUNNERS.get(run_id)
    if t:
        t.join(timeout)


def _next_item(db_path, run_id):
    with connect(db_path) as conn:
        run = conn.execute('SELECT status FROM batch_runs WHERE id=?', (run_id,)).fetchone()
        if not run or run['status'] != 'running':
            return None
        row = conn.execute("SELECT id FROM batch_items WHERE run_id=? AND status='pending' ORDER BY position LIMIT 1", (run_id,)).fetchone()
        if not row:
            return None
        cur = conn.execute("UPDATE batch_items SET status='running', started_at=datetime('now') WHERE id=? AND status='pending'", (row['id'],))
        conn.commit()
        return row['id'] if cur.rowcount else 'retry'


def _process(db_path, item_id, include_persons):
    with connect(db_path) as conn:
        item = conn.execute('SELECT * FROM batch_items WHERE id=?', (item_id,)).fetchone()
    status, error, result, log = 'done', '', None, []
    try:
        result = imprint.research_domain(item['domain'], include_persons=include_persons)
        log = result.get('log', [])
        if result['status'] != 'ok':
            status, error = 'kein_impressum', result['warnings'][0]
    except CrawlError as exc:
        status, error = 'failed', str(exc)
    except Exception as exc:  # unerwartete Fehler: protokollieren, Lauf fortsetzen
        status, error = 'failed', f'Unerwarteter Fehler: {exc.__class__.__name__}'
    with connect(db_path) as conn:
        dup, reason = item['duplicate_lead_id'], item['duplicate_reason']
        suppressed = []
        if result and result.get('fields'):
            f = result['fields']
            val = lambda k: (f.get(k) or {}).get('value') or ''
            if not dup:
                dup, reason = find_duplicate(conn, website=item['domain'], name=val('legal_name'),
                                             register_court=val('register_court'), register_number=val('register_number'))
            suppressed = check_suppressed(conn, name=val('legal_name'), register_court=val('register_court'),
                                          register_number=val('register_number'), email=val('business_email'))
            if suppressed:
                status, error = 'gesperrt', 'Firma steht auf der Sperrliste (Name/Register/E-Mail) – keine Übernahme möglich.'
        conn.execute('''UPDATE batch_items SET status=?, error=?, result_json=?, log_json=?, duplicate_lead_id=?, duplicate_reason=?,
                        finished_at=datetime('now') WHERE id=?''',
                     (status, error[:500], json.dumps(result, ensure_ascii=False) if result else '', json.dumps(log, ensure_ascii=False),
                      dup, reason or '', item_id))
        conn.commit()


def _run(db_path, run_id):
    with connect(db_path) as conn:
        run = conn.execute('SELECT options_json FROM batch_runs WHERE id=?', (run_id,)).fetchone()
    opts = json.loads(run['options_json']) if run else {}
    parallel, include_persons = opts.get('parallel', 2), opts.get('include_persons', True)

    def worker():
        while True:
            item_id = _next_item(db_path, run_id)
            if item_id is None:
                return
            if item_id == 'retry':
                continue
            _process(db_path, item_id, include_persons)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for _ in range(parallel):
            pool.submit(worker)
    with connect(db_path) as conn:
        left = conn.execute("SELECT COUNT(*) FROM batch_items WHERE run_id=? AND status IN ('pending','running')", (run_id,)).fetchone()[0]
        if not left:
            conn.execute("UPDATE batch_runs SET status='done', finished_at=datetime('now') WHERE id=? AND status IN ('running','paused')", (run_id,))
            conn.commit()


def control_run(conn, run_id, action, db_path):
    run = conn.execute('SELECT * FROM batch_runs WHERE id=?', (run_id,)).fetchone()
    if not run:
        raise LookupError('Lauf nicht gefunden.')
    if action == 'pause':
        if run['status'] != 'running':
            raise ValueError('Nur laufende Aufträge können pausiert werden.')
        conn.execute("UPDATE batch_runs SET status='paused' WHERE id=?", (run_id,))
    elif action == 'resume':
        if run['status'] != 'paused':
            raise ValueError('Nur pausierte Aufträge können fortgesetzt werden.')
        conn.execute("UPDATE batch_runs SET status='running' WHERE id=?", (run_id,))
        conn.commit()
        start_runner(db_path, run_id)
    elif action == 'cancel':
        if run['status'] in ('done', 'cancelled'):
            raise ValueError('Auftrag ist bereits beendet.')
        conn.execute("UPDATE batch_runs SET status='cancelled', finished_at=datetime('now') WHERE id=?", (run_id,))
        conn.execute("UPDATE batch_items SET status='abgebrochen' WHERE run_id=? AND status='pending'", (run_id,))
    elif action == 'retry_failed':
        conn.execute("UPDATE batch_items SET status='pending', error='' WHERE run_id=? AND status='failed'", (run_id,))
        conn.execute("UPDATE batch_runs SET status='running', finished_at='' WHERE id=?", (run_id,))
        conn.commit()
        start_runner(db_path, run_id)
    else:
        raise ValueError('Aktion: pause, resume, cancel oder retry_failed.')
    conn.commit()
    return run_detail(conn, run_id)


# ---------------------------------------------------------------- Ansicht

def _item_view(row):
    item = dict(row)
    item['result'] = json.loads(item.pop('result_json')) if item.get('result_json') else None
    item['log'] = json.loads(item.pop('log_json') or '[]')
    return item


def run_detail(conn, run_id):
    run = conn.execute('SELECT * FROM batch_runs WHERE id=?', (run_id,)).fetchone()
    if not run:
        raise LookupError('Lauf nicht gefunden.')
    out = dict(run)
    out['options'] = json.loads(out.pop('options_json'))
    items = [_item_view(r) for r in conn.execute('SELECT * FROM batch_items WHERE run_id=? ORDER BY position', (run_id,))]
    counts = {}
    for i in items:
        counts[i['status']] = counts.get(i['status'], 0) + 1
    out['counts'] = counts
    out['processed'] = sum(v for k, v in counts.items() if k not in ('pending', 'running'))
    out['review_open'] = sum(1 for i in items if i['status'] == 'done' and i['review_status'] == 'offen')
    out['items'] = items
    return out


def run_rows(conn):
    rows = []
    for r in conn.execute('SELECT * FROM batch_runs ORDER BY id DESC LIMIT 50'):
        counts = {x['status']: x['n'] for x in conn.execute('SELECT status, COUNT(*) AS n FROM batch_items WHERE run_id=? GROUP BY status', (r['id'],))}
        review = conn.execute("SELECT COUNT(*) FROM batch_items WHERE run_id=? AND status='done' AND review_status='offen'", (r['id'],)).fetchone()[0]
        rows.append({**dict(r), 'counts': counts, 'review_open': review,
                     'processed': sum(v for k, v in counts.items() if k not in ('pending', 'running'))})
    return rows


# ---------------------------------------------------------------- Übernahme

def review_item(conn, item_id, data):
    allowed = {'decision', 'lead_id', 'fields', 'include_representatives', 'overwrite', 'entity_index'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Ungültige Prüfentscheidung.')
    item = conn.execute('SELECT * FROM batch_items WHERE id=?', (item_id,)).fetchone()
    if not item:
        raise LookupError('Eintrag nicht gefunden.')
    if item['review_status'] != 'offen':
        raise ValueError('Eintrag wurde bereits geprüft.')
    decision = data.get('decision')
    if decision == 'verwerfen':
        conn.execute("UPDATE batch_items SET review_status='verworfen' WHERE id=?", (item_id,))
        conn.commit()
        return {'review_status': 'verworfen'}
    if decision not in ('neu', 'ergaenzen'):
        raise ValueError('Entscheidung: neu, ergaenzen oder verwerfen.')
    if item['status'] != 'done' or not item['result_json']:
        raise ValueError('Nur erfolgreich ausgelesene Impressen können übernommen werden.')
    result = json.loads(item['result_json'])
    fields = result.get('fields') or {}
    entity_index = data.get('entity_index', 0)
    entities = result.get('entities') or []
    if entity_index and (isinstance(entity_index, bool) or not isinstance(entity_index, int) or not 0 <= entity_index < len(entities)):
        raise ValueError('Ungültige Gesellschaft gewählt.')
    if entity_index:
        chosen = entities[entity_index]
        fields = dict(fields, legal_name={'value': chosen['name'], 'excerpt': chosen['excerpt'], 'method': imprint.METHOD, 'quality': 'mittel'},
                      legal_form={'value': chosen['legal_form'], 'excerpt': chosen['excerpt'], 'method': imprint.METHOD, 'quality': 'mittel'} if chosen.get('legal_form') else None)
    selected = data.get('fields', [k for k in APPLY_FIELDS if fields.get(k)])
    if not isinstance(selected, list) or any(k not in APPLY_FIELDS for k in selected):
        raise ValueError('Ungültige Feldauswahl.')
    overwrite = data.get('overwrite', False)
    include_reps = data.get('include_representatives', True)
    if not isinstance(overwrite, bool) or not isinstance(include_reps, bool):
        raise ValueError('overwrite/include_representatives: true/false.')
    val = lambda k: (fields.get(k) or {}).get('value') or ''
    website = 'https://' + item['domain']
    assert_not_suppressed(conn, website=website, name=val('legal_name'), register_court=val('register_court'),
                          register_number=val('register_number'), email=val('business_email'))
    if decision == 'neu':
        dup, reason = find_duplicate(conn, website=website, name=val('legal_name'),
                                     register_court=val('register_court'), register_number=val('register_number'))
        if dup:
            raise ValueError(f'Firma existiert bereits als Lead #{dup} (Treffer über {reason}) – bitte „ergänzen“ wählen.')
        cur = conn.execute('''INSERT INTO leads(company, website, location, industry, offer, stage, permission, contact_route, next_step, next_date, note)
                              VALUES (?,?,?,'','',?,?,?,?,?,?)''',  # 2.0.0-dev13: Branche und Leistung unbekannt statt vorbelegt
                           (val('legal_name') or item['company_hint'] or item['domain'], website,
                            ' '.join(x for x in (val('zip'), val('city')) if x)[:160], 'recherche', 'unbekannt', 'unbekannt',
                            'Website prüfen und belegbaren Anlass dokumentieren', (dt.date.today() + dt.timedelta(days=2)).isoformat(),
                            'Aus Impressumsprüfung übernommen. Fund ist keine Kontakterlaubnis.'))
        lead_id = cur.lastrowid
    else:
        lead_id = data.get('lead_id') or item['duplicate_lead_id'] or item['lead_id']
        if not isinstance(lead_id, int) or not conn.execute('SELECT 1 FROM leads WHERE id=?', (lead_id,)).fetchone():
            raise ValueError('Zu ergänzenden Lead angeben.')
        lead = conn.execute('SELECT permission, stage FROM leads WHERE id=?', (lead_id,)).fetchone()
        if lead['permission'] == 'nicht_kontaktieren' or lead['stage'] == 'gesperrt':
            raise ValueError('Lead ist gesperrt – keine Anreicherung.')
    source_type, source_url = result.get('source_type') or 'impressum_html', result.get('imprint_url') or ''
    lead = dict(conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone())
    applied, kept = [], []
    for key in APPLY_FIELDS:
        f = fields.get(key)
        if not f or not f.get('value'):
            continue
        chosen = key in selected
        add_fact(conn, lead_id, key, f['value'], source_type, source_url, f.get('excerpt', ''), f.get('method', imprint.METHOD),
                 f.get('quality', 'mittel'), 'bestaetigt' if chosen else 'ungeprueft', item_id)
        if not chosen:
            continue
        if lead.get(key) and lead[key] != f['value'] and not overwrite:
            kept.append(key)
            continue
        conn.execute(f'UPDATE leads SET {key}=? WHERE id=?', (f['value'], lead_id))
        applied.append(key)
    for ent in (result.get('entities') or [])[1:]:
        add_fact(conn, lead_id, 'related_entity', f"{ent['name']}{' (' + ent['role'] + ')' if ent.get('role') else ''}{' – ' + ent['register'] if ent.get('register') else ''}",
                 source_type, source_url, ent.get('excerpt', ''), imprint.METHOD, 'mittel', 'ungeprueft', item_id)
    add_fact(conn, lead_id, 'imprint_url', source_url, source_type, source_url, '', imprint.METHOD, 'hoch', 'bestaetigt', item_id)
    location_update = ' '.join(x for x in (lead.get('zip') or val('zip'), lead.get('city') or val('city')) if x)
    conn.execute("""UPDATE leads SET imprint_url=?, imprint_checked_at=?, location=CASE WHEN location='' OR location IS NULL THEN ? ELSE location END,
                    updated_at=datetime('now') WHERE id=?""", (source_url, result.get('checked_at', ''), location_update[:160], lead_id))
    persons = 0
    if include_reps:
        for rep in result.get('representatives') or []:
            exists = conn.execute('SELECT id FROM decision_contacts WHERE lead_id=? AND lower(full_name)=lower(?)', (lead_id, rep['name'])).fetchone()
            add_fact(conn, lead_id, 'representative', f"{rep['name']} ({rep['role']})", source_type, source_url, rep['excerpt'], rep['method'], 'mittel', 'bestaetigt', item_id)
            if exists:
                continue
            cur = conn.execute('''INSERT INTO decision_contacts(lead_id, full_name, job_title, decision_role, source_url, note, data_provider,
                                  verification_status, verification_date, source_excerpt) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                               (lead_id, rep['name'], f"{rep['role']} (laut Impressum)", 'unbekannt', source_url,
                                'Vertretungsberechtigt laut Impressum. Fachliche Zuständigkeit für das Projekt separat klären.',
                                'impressum', 'quelle_geprueft', dt.date.today().isoformat(), rep['excerpt'][:500]))
            add_privacy_record(conn, lead_id, cur.lastrowid, rep['name'], source_url)
            persons += 1
    conn.execute("UPDATE batch_items SET review_status='uebernommen', lead_id=? WHERE id=?", (lead_id, item_id))
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lead_id, 'notiz', f"Impressum geprüft ({source_url}): {len(applied)} Feld(er) übernommen" + (f", {persons} Person(en) mit Datenschutz-Nachweis" if persons else '')))
    _audit(conn, 'imprint', item_id, 'uebernommen', f'Lead {lead_id}: {", ".join(applied)}')
    conn.commit()
    return {'review_status': 'uebernommen', 'lead_id': lead_id, 'applied': applied, 'kept_existing': kept, 'persons_added': persons}


# ---------------------------------------------------------------- HTTP-Routen

def route_imprint(h, conn, method, route, query, db_path):
    if route == '/api/imprint/runs':
        if method == 'GET':
            h._send(200, run_rows(conn))
            return True
        if method == 'POST':
            h._send(202, create_run(conn, h._body(max_len=400_000), db_path))
            return True
    m = re.fullmatch(r'/api/imprint/runs/(\d+)(?:/(pause|resume|cancel|retry_failed))?', route)
    if m:
        run_id = int(m.group(1))
        if method == 'GET' and not m.group(2):
            h._send(200, run_detail(conn, run_id))
            return True
        if method == 'POST' and m.group(2):
            h._send(200, control_run(conn, run_id, m.group(2), db_path))
            return True
    m = re.fullmatch(r'/api/imprint/items/(\d+)/review', route)
    if m and method == 'POST':
        h._send(200, review_item(conn, int(m.group(1)), h._body()))
        return True
    m = re.fullmatch(r'/api/leads/(\d+)/imprint', route)
    if m and method == 'POST':
        lid = int(m.group(1))
        lead = conn.execute('SELECT permission, stage FROM leads WHERE id=?', (lid,)).fetchone()
        if not lead:
            raise LookupError('Lead nicht gefunden.')
        if lead['permission'] == 'nicht_kontaktieren' or lead['stage'] == 'gesperrt':
            raise ValueError('Lead ist gesperrt.')
        h._send(202, create_run(conn, {'lead_id': lid, 'label': f'Lead #{lid}', 'parallel': 1}, db_path))
        return True
    return False


def route_company_data(h, conn, method, route, query):
    """Feldbelege, Sperrliste und Datenschutz-Nachweise."""
    from .company_data import (SUPPRESSION_KINDS, add_suppression, art14_text, facts_for_lead, mark_art14_informed,
                               privacy_rows, remove_suppression, set_fact_status, suppression_rows)
    m = re.fullmatch(r'/api/leads/(\d+)/facts', route)
    if m and method == 'GET':
        lid = int(m.group(1))
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        if not lead:
            raise LookupError('Lead nicht gefunden.')
        h._send(200, {'facts': facts_for_lead(conn, lid), 'privacy': privacy_rows(conn, lid),
                      'company': {k: lead[k] for k in ('legal_name', 'legal_form', 'street', 'zip', 'city', 'register_court',
                                                        'register_number', 'vat_id', 'business_phone', 'business_email',
                                                        'imprint_url', 'imprint_checked_at')}})
        return True
    m = re.fullmatch(r'/api/facts/(\d+)', route)
    if m and method == 'PATCH':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'status'}:
            raise ValueError('Erwartet: {status}.')
        h._send(200, set_fact_status(conn, int(m.group(1)), body['status']))
        return True
    if route == '/api/suppression':
        if method == 'GET':
            h._send(200, suppression_rows(conn))
            return True
        if method == 'POST':
            body = h._body()
            if not isinstance(body, dict) or set(body) - {'kind', 'value', 'reason'} or body.get('kind') not in SUPPRESSION_KINDS:
                raise ValueError('Erwartet: {kind: domain|name|email, value, reason}.')
            if body['kind'] == 'register':
                raise ValueError('Registersperren entstehen automatisch beim Sperren eines Leads.')
            value = str(body.get('value') or '').strip()[:200]
            norm = add_suppression(conn, body['kind'], value, str(body.get('reason') or 'manuell')[:300])
            if not norm:
                raise ValueError('Wert zu kurz oder ungültig.')
            _audit(conn, 'suppression', None, 'manuell_gesperrt', f"{body['kind']} {value}")
            conn.commit()
            h._send(201, {'saved': True, 'value': norm})
            return True
    m = re.fullmatch(r'/api/suppression/(\d+)', route)
    if m and method == 'DELETE':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'reason'}:
            raise ValueError('Begründung angeben: {reason}.')
        h._send(200, remove_suppression(conn, int(m.group(1)), str(body['reason'])))
        return True
    if route == '/api/privacy' and method == 'GET':
        lid = query.get('lead_id', [''])[0]
        h._send(200, privacy_rows(conn, int(lid) if lid.isdigit() else None))
        return True
    m = re.fullmatch(r'/api/privacy/(\d+)/extend', route)
    if m and method == 'POST':
        from .company_data import extend_retention
        h._send(200, extend_retention(conn, int(m.group(1)), h._body()))
        return True
    m = re.fullmatch(r'/api/privacy/(\d+)/(informed|art14)', route)
    if m:
        if m.group(2) == 'informed' and method == 'POST':
            body = h._body()
            if not isinstance(body, dict) or set(body) - {'date'}:
                raise ValueError('Erwartet: {date}.')
            h._send(200, mark_art14_informed(conn, int(m.group(1)), body.get('date')))
            return True
        if m.group(2) == 'art14' and method == 'GET':
            h._send(200, art14_text(conn, int(m.group(1))))
            return True
    return False
