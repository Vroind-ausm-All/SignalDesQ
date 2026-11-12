"""Qualität & Skalierung (Phase 6): Einstellungen, Veraltung, Änderungserkennung, wiederkehrende Aufträge, Löschfristen.

- Einstellungen: Gewichte der Recherchepriorität und Veraltungsfristen je Datenart (konfigurierbar).
- Veraltungs-Kennzeichen: Impressum, bestätigte Feldbelege, Website-Bewertung, geprüfte Ansprechpartner,
  Kaufsignale und Karriereseiten werden nach Ablauf ihrer Frist als „veraltet“ markiert – gelöscht oder
  überschrieben wird dabei nichts.
- Änderungserkennung: erneut ausgelesene Impressen werden mit den übernommenen Firmendaten verglichen,
  neue Website-Bewertungen mit der vorigen, Registerbekanntmachungen (Umbenennung, Sitzverlegung) mit den
  Firmendaten. Jede Änderung ist ein Prüfpunkt; übernommen wird nur nach Bestätigung.
- Wiederkehrende Rechercheaufträge: nutzen ausschließlich die bestehenden Module mit deren Schutzmechanismen
  (SSRF-Schutz, robots.txt, Rate-Limits, Fair-Use-Grenzen, Sperrliste). Sie kontaktieren niemanden.
- Löschfristen: Personendaten mit abgelaufener Frist (Datenschutz-Nachweis) werden angezeigt und nach
  Bestätigung gelöscht.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading

from .company_data import FACT_FIELDS, LEAD_COMPANY_COLUMNS, _audit, add_fact, check_suppressed, normalize_domain, set_fact_status

OPEN_STAGES = ('recherche', 'qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot')
DEFAULT_WEIGHTS = {'website': 40, 'signal': 30, 'fit': 30}
STALE_LABELS = {
    'imprint': 'Impressum', 'facts': 'Bestätigte Firmendaten', 'website': 'Website-Bewertung',
    'contacts': 'Geprüfte Ansprechpartner', 'signals': 'Kaufsignale', 'career': 'Karriereseite',
}
DEFAULT_STALE_DAYS = {'imprint': 365, 'facts': 365, 'website': 180, 'contacts': 180, 'signals': 365, 'career': 90}
CHANGE_FIELDS = ('legal_name', 'legal_form', 'street', 'zip', 'city', 'register_court', 'register_number', 'vat_id',
                 'business_phone', 'business_email')
CHANGE_STATUSES = ('offen', 'uebernommen', 'erledigt', 'ignoriert')


def init_quality(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS change_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, field TEXT NOT NULL, old_value TEXT NOT NULL DEFAULT '', new_value TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '', excerpt TEXT NOT NULL DEFAULT '', ref TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'offen', detected_at TEXT NOT NULL DEFAULT (datetime('now')), decided_at TEXT NOT NULL DEFAULT '',
        UNIQUE(ref)
      );
      CREATE INDEX IF NOT EXISTS idx_change_events_lead ON change_events(lead_id, status);
      CREATE TABLE IF NOT EXISTS recurring_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, label TEXT NOT NULL, interval_days INTEGER NOT NULL, params_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 1, next_run_at TEXT NOT NULL, last_run_at TEXT NOT NULL DEFAULT '',
        last_status TEXT NOT NULL DEFAULT '', last_detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_signal_scans_lead ON signal_scans(lead_id, id);
      CREATE INDEX IF NOT EXISTS idx_website_findings_audit ON website_findings(audit_id);
      CREATE INDEX IF NOT EXISTS idx_tasks_lead ON tasks(lead_id, done);
      CREATE INDEX IF NOT EXISTS idx_offer_rec_lead ON offer_recommendations(lead_id, rank);
      CREATE INDEX IF NOT EXISTS idx_privacy_retention ON privacy_records(retention_until);
    ''')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(batch_items)')}
    if 'changes_checked' not in cols:
        conn.execute('ALTER TABLE batch_items ADD COLUMN changes_checked INTEGER NOT NULL DEFAULT 0')


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _age_days(ts, today=None):
    if not ts:
        return None
    try:
        d = dt.date.fromisoformat(str(ts)[:10])
    except ValueError:
        return None
    return ((today or dt.date.today()) - d).days


# ---------------------------------------------------------------- Einstellungen

def get_setting(conn, key, default):
    row = conn.execute('SELECT value_json FROM app_settings WHERE key=?', (key,)).fetchone()
    if not row:
        return default
    try:
        value = json.loads(row['value_json'])
    except ValueError:
        return default
    return {**default, **value} if isinstance(default, dict) and isinstance(value, dict) else value


def put_setting(conn, key, value):
    conn.execute('''INSERT INTO app_settings(key, value_json, updated_at) VALUES (?,?,datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at''',
                 (key, json.dumps(value, ensure_ascii=False)))


def priority_weights(conn):
    w = get_setting(conn, 'priority_weights', dict(DEFAULT_WEIGHTS))
    return {k: int(w.get(k, DEFAULT_WEIGHTS[k])) for k in DEFAULT_WEIGHTS}


def stale_days(conn):
    d = get_setting(conn, 'stale_days', dict(DEFAULT_STALE_DAYS))
    return {k: int(d.get(k, DEFAULT_STALE_DAYS[k])) for k in DEFAULT_STALE_DAYS}


def save_settings(conn, data):
    if not isinstance(data, dict) or not data or set(data) - {'priority_weights', 'stale_days'}:
        raise ValueError('Erwartet: {priority_weights?, stale_days?}.')
    if 'priority_weights' in data:
        w = data['priority_weights']
        if not isinstance(w, dict) or set(w) != set(DEFAULT_WEIGHTS) or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 100 for v in w.values()):
            raise ValueError('Gewichte: website, signal, fit als ganze Zahlen 0–100.')
        if sum(w.values()) != 100:
            raise ValueError(f'Die Gewichte müssen zusammen 100 ergeben (aktuell {sum(w.values())}).')
        if w['website'] + w['signal'] == 0:
            raise ValueError('Website oder Kaufsignale brauchen ein Gewicht > 0 – sonst ist keine Recherchepriorität möglich.')
    if 'stale_days' in data:
        s = data['stale_days']
        if not isinstance(s, dict) or not s or set(s) - set(DEFAULT_STALE_DAYS) or any(isinstance(v, bool) or not isinstance(v, int) or not 7 <= v <= 1095 for v in s.values()):
            raise ValueError('Veraltungsfristen: ' + ', '.join(DEFAULT_STALE_DAYS) + ' jeweils 7–1095 Tage.')
    before = settings_view(conn)
    if 'priority_weights' in data:
        put_setting(conn, 'priority_weights', data['priority_weights'])
    if 'stale_days' in data:
        put_setting(conn, 'stale_days', {**stale_days(conn), **data['stale_days']})
    _audit(conn, 'settings', 0, 'geaendert', json.dumps({'vorher': before, 'neu': data}, ensure_ascii=False))
    conn.commit()
    return settings_view(conn)


def settings_view(conn):
    return {'priority_weights': priority_weights(conn), 'stale_days': stale_days(conn), 'stale_labels': STALE_LABELS,
            'defaults': {'priority_weights': DEFAULT_WEIGHTS, 'stale_days': DEFAULT_STALE_DAYS}}


# ---------------------------------------------------------------- Veraltung

def lead_staleness(conn, lead, cfg=None, today=None):
    """Liste veralteter Datenarten eines Leads. Fehlende Daten sind nicht „veraltet“ (das zeigt der Recherchestand)."""
    cfg = cfg or stale_days(conn)
    lid, out = lead['id'], []

    def add(kind, age, detail, view):
        out.append({'kind': kind, 'label': STALE_LABELS[kind], 'age_days': age, 'limit_days': cfg[kind], 'detail': detail, 'view': view})

    age = _age_days(lead['imprint_checked_at'] if 'imprint_checked_at' in lead.keys() else '', today)
    if age is not None and age > cfg['imprint']:
        add('imprint', age, f'Zuletzt geprüft vor {age} Tagen', 'datacheck')
    old = conn.execute("""SELECT COUNT(*) AS n, MIN(checked_at) AS oldest FROM company_facts WHERE lead_id=? AND status='bestaetigt'
                          AND checked_at<>'' AND julianday(?) - julianday(checked_at) > ?""", (lid, (today or dt.date.today()).isoformat(), cfg['facts'])).fetchone()
    if old['n']:
        add('facts', _age_days(old['oldest'], today), f"{old['n']} bestätigte Feldbelege älter als {cfg['facts']} Tage", 'leads')
    audit = conn.execute("SELECT finished_at FROM website_audits WHERE lead_id=? AND status='done' ORDER BY id DESC LIMIT 1", (lid,)).fetchone()
    if audit:
        age = _age_days(audit['finished_at'], today)
        if age is not None and age > cfg['website']:
            add('website', age, f'Letzte Bewertung vor {age} Tagen', 'scoring')
    c = conn.execute("""SELECT COUNT(*) AS n, MIN(updated_at) AS oldest FROM decision_contacts WHERE lead_id=?
                        AND verification_status IN ('quelle_geprueft','rolle_bestaetigt') AND julianday(?) - julianday(updated_at) > ?""",
                     (lid, (today or dt.date.today()).isoformat(), cfg['contacts'])).fetchone()
    if c['n']:
        add('contacts', _age_days(c['oldest'], today), f"{c['n']} geprüfte Person(en) – Funktion erneut prüfen (Wechsel möglich)", 'leads')
    sig = conn.execute("""SELECT MAX(COALESCE(NULLIF(published_at,''), found_at)) AS latest FROM buying_signals
                          WHERE lead_id=? AND status<>'verworfen'""", (lid,)).fetchone()
    if sig['latest']:
        age = _age_days(sig['latest'], today)
        if age is not None and age > cfg['signals']:
            add('signals', age, f'Jüngstes Kaufsignal vor {age} Tagen', 'signals')
    scan = conn.execute("SELECT finished_at FROM signal_scans WHERE lead_id=? AND status='done' ORDER BY id DESC LIMIT 1", (lid,)).fetchone()
    if scan:
        age = _age_days(scan['finished_at'], today)
        if age is not None and age > cfg['career']:
            add('career', age, f'Karriereseite zuletzt vor {age} Tagen geprüft', 'signals')
    return out


def expired_privacy(conn, today=None):
    rows = conn.execute('''SELECT p.id, p.lead_id, p.contact_id, p.subject, p.retention_until, p.purpose, p.kind, l.company, l.stage
                           FROM privacy_records p LEFT JOIN leads l ON l.id=p.lead_id
                           WHERE p.retention_until<>'' AND p.retention_until < ? ORDER BY p.retention_until''',
                        ((today or dt.date.today()).isoformat(),))
    return [dict(r) for r in rows]


def staleness_report(conn, today=None):
    cfg = stale_days(conn)
    leads, counts = [], {k: 0 for k in STALE_LABELS}
    for lead in conn.execute(f"SELECT * FROM leads WHERE stage IN ({','.join('?' for _ in OPEN_STAGES)}) ORDER BY company", OPEN_STAGES):
        items = lead_staleness(conn, lead, cfg, today)
        for i in items:
            counts[i['kind']] += 1
        if items:
            leads.append({'lead_id': lead['id'], 'company': lead['company'], 'items': items})
    return {'config': cfg, 'labels': STALE_LABELS, 'counts': counts, 'leads': leads, 'privacy_expired': expired_privacy(conn, today),
            'notice': 'Veraltet heißt: erneut prüfen. Es wird nichts automatisch gelöscht oder überschrieben – außer nach deiner Bestätigung bei abgelaufenen Löschfristen.'}


def erase_expired_person(conn, record_id, data):
    """Löscht die Personendaten eines Datenschutz-Nachweises mit abgelaufener Frist (nach ausdrücklicher Bestätigung)."""
    if not isinstance(data, dict) or data.get('confirm') is not True or set(data) != {'confirm'}:
        raise ValueError('Löschen bitte mit {"confirm": true} bestätigen.')
    rec = conn.execute('SELECT * FROM privacy_records WHERE id=?', (record_id,)).fetchone()
    if not rec:
        raise LookupError('Nachweis nicht gefunden.')
    if not rec['retention_until'] or rec['retention_until'] >= dt.date.today().isoformat():
        raise ValueError('Die Löschfrist ist noch nicht abgelaufen.')
    if rec['kind'] == 'einzelunternehmen':
        return _erase_sole(conn, rec)
    removed = 0
    if rec['contact_id']:
        conn.execute('UPDATE tasks SET contact_id=NULL WHERE contact_id=?', (rec['contact_id'],))
        removed = conn.execute('DELETE FROM decision_contacts WHERE id=?', (rec['contact_id'],)).rowcount
    conn.execute('DELETE FROM privacy_records WHERE id=?', (record_id,))
    # Nachweis der Löschung ohne Personendaten (Rechenschaftspflicht, Art. 5 Abs. 2 DSGVO)
    _audit(conn, 'privacy', record_id, 'personendaten_geloescht', f"Lead {rec['lead_id']}, Kontakt {rec['contact_id'] or '–'}, Frist {rec['retention_until']}")
    conn.commit()
    return {'deleted_contacts': removed, 'deleted_record': record_id}


def _erase_sole(conn, rec):
    """Betrieb ohne Rechtsform mit abgelaufener Frist: den Lead mit allem, was daran hängt, löschen (2.0.0-dev10).
    - Kunden (Rechnungen oder Phase „gewonnen“) werden nicht gelöscht – dort gelten Aufbewahrungspflichten.
    - Firmen im laufenden Gespräch werden nicht stillschweigend gelöscht: erst Frist mit Grund verlängern oder Lead selbst löschen.
    - Eine Sperre bleibt bestehen (Sperrliste), ein Widerspruch wird nie durch Löschen aufgehoben.
    - Die Fundstellen in der Firmensuche werden anonymisiert; der Betrieb darf bei einer späteren Suche neu auftauchen."""
    lid = rec['lead_id']
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone() if lid else None
    if lead:
        if lead['stage'] == 'gewonnen' or conn.execute('SELECT 1 FROM invoices WHERE lead_id=? LIMIT 1', (lid,)).fetchone():
            raise ValueError('Kunde mit Rechnungen bzw. Auftrag: Aufbewahrungspflichten gehen vor. Bitte die Frist mit Grund verlängern.')
        if lead['stage'] in ('antwort', 'termin', 'angebot'):
            raise ValueError(f"Die Firma ist in der Phase „{lead['stage']}“. Bitte die Frist mit Grund verlängern oder den Lead bewusst selbst löschen.")
        if lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
            from .company_data import suppress_lead
            suppress_lead(conn, lid, 'Gesperrter Lead nach Ablauf der Löschfrist gelöscht – Sperre bleibt')
        for c in conn.execute('SELECT id FROM discovery_candidates WHERE lead_id=?', (lid,)).fetchall():
            conn.execute('DELETE FROM discovery_keys WHERE candidate_id=?', (c['id'],))
            conn.execute("""UPDATE discovery_candidates SET name='(gelöscht)', street='', website='', website_evidence='', contact_json='{}',
                            imprint_json='{}', signal_note='', external_id='', source_url='', status='verworfen', lead_id=NULL WHERE id=?""", (c['id'],))
        conn.execute('DELETE FROM leads WHERE id=?', (lid,))
    conn.execute('DELETE FROM privacy_records WHERE id=?', (rec['id'],))
    _audit(conn, 'privacy', rec['id'], 'einzelunternehmen_geloescht', f"Lead {lid or '–'}, Frist {rec['retention_until']}")
    conn.commit()
    return {'deleted_lead': lid if lead else None, 'deleted_record': rec['id']}


# ---------------------------------------------------------------- Änderungserkennung

def _norm(field, value):
    v = re.sub(r'\s+', ' ', str(value or '')).strip().casefold()
    if field == 'street':
        v = re.sub(r'stra(ss|ß)e\b', 'str', v).replace('str.', 'str')
    if field in ('business_phone',):
        v = re.sub(r'\D', '', v)[-9:]
    if field in ('register_number', 'vat_id', 'zip'):
        v = re.sub(r'[^0-9a-z]', '', v)
    return re.sub(r'[.,\-]', '', v).strip()


def _event(conn, lead_id, kind, field, old, new, ref, source_url='', excerpt=''):
    cur = conn.execute('''INSERT OR IGNORE INTO change_events(lead_id, kind, field, old_value, new_value, source_url, excerpt, ref)
                          VALUES (?,?,?,?,?,?,?,?)''', (lead_id, kind, field, str(old)[:500], str(new)[:500], (source_url or '')[:500], (excerpt or '')[:600], ref))
    return cur.rowcount


def detect_imprint_changes(conn):
    found = 0
    for item in conn.execute("""SELECT * FROM batch_items WHERE status='done' AND changes_checked=0 AND result_json<>''
                                AND COALESCE(lead_id, duplicate_lead_id) IS NOT NULL""").fetchall():
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (item['lead_id'] or item['duplicate_lead_id'],)).fetchone()
        if lead:
            result = json.loads(item['result_json'])
            fields = result.get('fields') or {}
            url = result.get('imprint_url') or (fields.get('imprint_url') or {}).get('value') or f"https://{item['domain']}"
            for f in CHANGE_FIELDS:
                new = (fields.get(f) or {}).get('value') or ''
                old = lead[f] or ''
                if new and old and _norm(f, new) != _norm(f, old):
                    found += _event(conn, lead['id'], 'impressum', f, old, new, f"impressum:{item['id']}:{f}", url, (fields.get(f) or {}).get('excerpt', ''))
        conn.execute('UPDATE batch_items SET changes_checked=1 WHERE id=?', (item['id'],))
    return found


def detect_website_changes(conn, threshold=10):
    found = 0
    for lead in conn.execute('SELECT DISTINCT lead_id FROM website_scores').fetchall():
        rows = conn.execute('SELECT * FROM website_scores WHERE lead_id=? ORDER BY id DESC LIMIT 2', (lead['lead_id'],)).fetchall()
        if len(rows) < 2 or rows[0]['audit_id'] == rows[1]['audit_id']:
            continue
        new, old = rows
        if new['overall'] is not None and old['overall'] is not None and abs(new['overall'] - old['overall']) >= threshold:
            found += _event(conn, lead['lead_id'], 'website', 'overall', old['overall'], new['overall'], f"website:{new['audit_id']}:overall")
        before = {r['rubric']: r['result'] for r in conn.execute('SELECT rubric, result FROM website_findings WHERE audit_id=?', (old['audit_id'],))}
        flips = []
        for r in conn.execute('SELECT rubric, label, result FROM website_findings WHERE audit_id=?', (new['audit_id'],)):
            prev = before.get(r['rubric'])
            if prev and prev != r['result'] and 'unbekannt' not in (prev, r['result']):
                flips.append(f"{r['label']}: {prev} → {r['result']}")
        if flips:
            found += _event(conn, lead['lead_id'], 'website', 'rubriken', f'{len(flips)} Rubrik(en) geändert', '; '.join(flips)[:500],
                            f"website:{new['audit_id']}:rubriken")
    return found


REGISTER_FIELD_HINT = {'umbenennung': ('legal_name', 'Register meldet Umbenennung – offiziellen Firmennamen prüfen'),
                       'sitzverlegung': ('street', 'Register meldet Sitzverlegung/neue Anschrift – Anschrift prüfen'),
                       'gf_wechsel': ('representative', 'Register meldet Wechsel der Vertretung – Ansprechpartner und Impressum prüfen'),
                       'aufloesung': ('legal_name', 'Register meldet Auflösung/Liquidation – Lead-Status prüfen')}


def detect_register_changes(conn):
    found = 0
    for ev in conn.execute("SELECT * FROM register_events WHERE lead_id IS NOT NULL AND event_type IN ('umbenennung','sitzverlegung','gf_wechsel','aufloesung')").fetchall():
        field, hint = REGISTER_FIELD_HINT[ev['event_type']]
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (ev['lead_id'],)).fetchone()
        old = (lead[field] if field in lead.keys() else '') or ''
        found += _event(conn, ev['lead_id'], 'register', field, old, hint, f"register:{ev['id']}", ev['source_url'], ev['text'][:600])
    return found


def detect_changes(conn):
    out = {'impressum': detect_imprint_changes(conn), 'website': detect_website_changes(conn), 'register': detect_register_changes(conn)}
    conn.commit()
    return out


def change_rows(conn, status='offen'):
    sql = '''SELECT e.*, l.company FROM change_events e JOIN leads l ON l.id=e.lead_id'''
    args = ()
    if status != 'alle':
        if status not in CHANGE_STATUSES:
            raise ValueError('Status: ' + ', '.join(CHANGE_STATUSES) + ' oder alle.')
        sql += ' WHERE e.status=?'
        args = (status,)
    rows = [dict(r) for r in conn.execute(sql + ' ORDER BY e.id DESC LIMIT 300', args)]
    for r in rows:
        r['label'] = FACT_FIELDS.get(r['field'], {'overall': 'Website-Gesamtwert', 'rubriken': 'Website-Rubriken'}.get(r['field'], r['field']))
        r['can_apply'] = r['kind'] == 'impressum' and r['status'] == 'offen'
    return rows


def decide_change(conn, event_id, data):
    if not isinstance(data, dict) or set(data) != {'decision'} or data['decision'] not in ('uebernehmen', 'erledigt', 'ignorieren'):
        raise ValueError('Erwartet: {decision: uebernehmen|erledigt|ignorieren}.')
    ev = conn.execute('SELECT * FROM change_events WHERE id=?', (event_id,)).fetchone()
    if not ev:
        raise LookupError('Änderung nicht gefunden.')
    if ev['status'] != 'offen':
        raise ValueError('Diese Änderung wurde bereits entschieden.')
    decision = data['decision']
    if decision == 'uebernehmen':
        if ev['kind'] != 'impressum' or ev['field'] not in LEAD_COMPANY_COLUMNS:
            raise ValueError('Übernehmen ist nur für Impressumsfelder möglich – sonst „erledigt“.')
        lead = conn.execute('SELECT stage FROM leads WHERE id=?', (ev['lead_id'],)).fetchone()
        if lead['stage'] == 'gesperrt':
            raise ValueError('Lead ist gesperrt.')
        now = _now()
        conn.execute("UPDATE company_facts SET status='veraltet', checked_at=? WHERE lead_id=? AND field=? AND status='bestaetigt'",
                     (now, ev['lead_id'], ev['field']))
        fid = add_fact(conn, ev['lead_id'], ev['field'], ev['new_value'], 'impressum_html', ev['source_url'], ev['excerpt'],
                       'aenderungserkennung-v1', 'hoch')
        set_fact_status(conn, fid, 'bestaetigt')
    status = {'uebernehmen': 'uebernommen', 'erledigt': 'erledigt', 'ignorieren': 'ignoriert'}[decision]
    conn.execute("UPDATE change_events SET status=?, decided_at=datetime('now') WHERE id=?", (status, event_id))
    _audit(conn, 'change_event', event_id, status, f"{ev['field']}: {ev['old_value'][:80]} → {ev['new_value'][:80]}")
    conn.commit()
    return dict(conn.execute('SELECT * FROM change_events WHERE id=?', (event_id,)).fetchone())


# ---------------------------------------------------------------- Wiederkehrende Rechercheaufträge

JOB_KINDS = {
    'impressum_aktualisieren': 'Impressen veralteter oder nie geprüfter Firmen erneut auslesen',
    'websites_neu_bewerten': 'Websites mit veralteter Bewertung neu bewerten',
    'karriereseiten_pruefen': 'Karriereseiten erneut auf Stellenanzeigen prüfen',
    'lead_finder_suche': 'Gespeicherte Firmensuche (Lead-Finder) wiederholen',
    'datenqualitaet_pruefen': 'Änderungen erkennen und Veraltung prüfen',
}
LEAD_FINDER_KEYS = {'source', 'place', 'keyword', 'category', 'min_employees', 'limit', 'preset', 'days', 'legal_entities_only'}
_SCHED = {'thread': None, 'stop': None}
_RUN_LOCK = threading.Lock()


def _validate_job(data, partial=False):
    allowed = {'kind', 'label', 'interval_days', 'params', 'enabled'}
    if not isinstance(data, dict) or set(data) - allowed or (not partial and 'kind' not in data):
        raise ValueError('Erwartet: {kind, label, interval_days, params, enabled}.')
    out = {}
    if 'kind' in data:
        if partial:
            raise ValueError('Die Art eines Auftrags lässt sich nicht ändern.')
        if data['kind'] not in JOB_KINDS:
            raise ValueError('Unbekannte Auftragsart.')
        out['kind'] = data['kind']
    if 'label' in data or not partial:
        label = str(data.get('label') or JOB_KINDS.get(data.get('kind'), '')).strip()
        if not label or len(label) > 120:
            raise ValueError('Bezeichnung: 1–120 Zeichen.')
        out['label'] = label
    if 'interval_days' in data or not partial:
        iv = data.get('interval_days', 30)
        if isinstance(iv, bool) or not isinstance(iv, int) or not 1 <= iv <= 365:
            raise ValueError('Intervall: 1–365 Tage.')
        out['interval_days'] = iv
    if 'enabled' in data:
        if not isinstance(data['enabled'], bool):
            raise ValueError('enabled: true/false.')
        out['enabled'] = int(data['enabled'])
    if 'params' in data or not partial:
        p = data.get('params') or {}
        if not isinstance(p, dict):
            raise ValueError('params muss ein Objekt sein.')
        kind = data.get('kind')
        if kind == 'lead_finder_suche' or (partial and 'source' in p):
            from .lead_finder import SEARCHERS
            if set(p) - LEAD_FINDER_KEYS or p.get('source') not in SEARCHERS:
                raise ValueError('Lead-Finder: Quelle und Suchparameter wie in „Firmen finden“.')
        else:
            if set(p) - {'limit'}:
                raise ValueError('Parameter: nur limit.')
            lim = p.get('limit', 20)
            if isinstance(lim, bool) or not isinstance(lim, int) or not 1 <= lim <= 50:
                raise ValueError('limit: 1–50 Firmen je Lauf.')
        out['params_json'] = json.dumps(p, ensure_ascii=False, sort_keys=True)
    return out


def create_job(conn, data):
    v = _validate_job(data)
    if conn.execute('SELECT COUNT(*) FROM recurring_jobs').fetchone()[0] >= 30:
        raise ValueError('Höchstens 30 wiederkehrende Aufträge.')
    start = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.execute('INSERT INTO recurring_jobs(kind, label, interval_days, params_json, enabled, next_run_at) VALUES (?,?,?,?,?,?)',
                       (v['kind'], v['label'], v['interval_days'], v['params_json'], v.get('enabled', 1), start))
    conn.commit()
    return job_view(conn.execute('SELECT * FROM recurring_jobs WHERE id=?', (cur.lastrowid,)).fetchone())


def update_job(conn, job_id, data):
    v = _validate_job(data, partial=True)
    if not v:
        raise ValueError('Keine Änderung.')
    if not conn.execute('SELECT 1 FROM recurring_jobs WHERE id=?', (job_id,)).fetchone():
        raise LookupError('Auftrag nicht gefunden.')
    conn.execute(f"UPDATE recurring_jobs SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), job_id))
    conn.commit()
    return job_view(conn.execute('SELECT * FROM recurring_jobs WHERE id=?', (job_id,)).fetchone())


def delete_job(conn, job_id):
    if not conn.execute('DELETE FROM recurring_jobs WHERE id=?', (job_id,)).rowcount:
        raise LookupError('Auftrag nicht gefunden.')
    conn.commit()
    return {'deleted': True}


def job_view(row):
    d = dict(row)
    d['params'] = json.loads(d.pop('params_json') or '{}')
    d['enabled'] = bool(d['enabled'])
    d['kind_label'] = JOB_KINDS.get(d['kind'], d['kind'])
    return d


def job_rows(conn):
    return {'jobs': [job_view(r) for r in conn.execute('SELECT * FROM recurring_jobs ORDER BY enabled DESC, next_run_at')], 'kinds': JOB_KINDS,
            'notice': 'Wiederkehrende Aufträge recherchieren nur. Sie nutzen die Schutzmechanismen der Module (robots.txt, Rate-Limits, Fair Use, Sperrliste) und kontaktieren niemanden. Ergebnisse landen in den Prüflisten.'}


def _open_leads(conn):
    return conn.execute(f"""SELECT * FROM leads WHERE stage IN ({','.join('?' for _ in OPEN_STAGES)}) AND website<>''
                            AND permission<>'nicht_kontaktieren' ORDER BY updated_at""", OPEN_STAGES).fetchall()


def candidates(conn, kind, limit, today=None, career_interval=None):
    cfg = stale_days(conn)
    out = []
    for lead in _open_leads(conn):
        if len(out) >= limit:
            break
        if check_suppressed(conn, website=lead['website'], name=lead['company']):
            continue
        if kind == 'impressum_aktualisieren':
            age = _age_days(lead['imprint_checked_at'], today)
            if age is not None and age <= cfg['imprint']:
                continue
            domain = normalize_domain(lead['website'])
            busy = conn.execute("""SELECT 1 FROM batch_items WHERE domain=? AND (status IN ('pending','running')
                                   OR (review_status='offen' AND status='done'))""", (domain,)).fetchone()
            if busy:
                continue
        elif kind == 'websites_neu_bewerten':
            a = conn.execute("SELECT status, finished_at FROM website_audits WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lead['id'],)).fetchone()
            if not a or a['status'] in ('queued', 'running'):
                continue
            age = _age_days(a['finished_at'], today)
            if age is not None and age <= cfg['website']:
                continue
        elif kind == 'karriereseiten_pruefen':
            s = conn.execute("SELECT status, finished_at FROM signal_scans WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lead['id'],)).fetchone()
            if s:
                if s['status'] in ('queued', 'running'):
                    continue
                age = _age_days(s['finished_at'], today)
                # Laufintervall steuert die Überwachung; Veraltungsfrist bleibt eine Anzeigeeinstellung.
                threshold = career_interval if career_interval is not None else cfg['career']
                if s['status'] == 'done' and age is not None and age < threshold:
                    continue
        out.append(lead)
    return out


def run_job(conn, job_id, db_path, start=True):
    """Führt einen Auftrag aus. start=False legt die Aufträge an, ohne Netzwerkzugriffe zu starten (Tests)."""
    with _RUN_LOCK:
        job = conn.execute('SELECT * FROM recurring_jobs WHERE id=?', (job_id,)).fetchone()
        if not job:
            raise LookupError('Auftrag nicht gefunden.')
        params = json.loads(job['params_json'] or '{}')
        status, detail = 'ok', ''
        try:
            if job['kind'] == 'datenqualitaet_pruefen':
                ch = detect_changes(conn)
                rep = staleness_report(conn)
                detail = (f"{sum(ch.values())} neue Änderung(en) · {len(rep['leads'])} Firma(en) mit veralteten Daten · "
                          f"{len(rep['privacy_expired'])} abgelaufene Löschfrist(en)")
            elif job['kind'] == 'lead_finder_suche':
                from .lead_finder import run_search
                r = run_search(conn, {**params, 'force': True})
                detail = f"{r.get('result_count', len(r.get('candidates', [])))} Treffer zur Prüfung im Lead-Finder"
            else:
                leads = candidates(conn, job['kind'], params.get('limit', 20), career_interval=job['interval_days'])
                if not leads:
                    status, detail = 'nichts_zu_tun', 'Keine Firma fällig.'
                elif job['kind'] == 'impressum_aktualisieren':
                    from .imprint_batch import create_run
                    r = create_run(conn, {'domains': '\n'.join(l['website'] for l in leads), 'label': f"Wiederkehrend: {job['label']}"[:120]}, db_path, start=start)
                    detail = f"Impressum-Lauf #{r['id']} mit {r['total']} Domain(s) – Ergebnisse in der Datenprüfung"
                else:
                    ids = [l['id'] for l in leads][:20]
                    if job['kind'] == 'websites_neu_bewerten':
                        from . import website_scorer as ws
                        r = ws.enqueue(conn, ids, db_path) if start else _queue_only(conn, 'website_audits', ids, with_url=True)
                    else:
                        from . import buying_signals as bs
                        r = bs.enqueue_scans(conn, ids, db_path) if start else _queue_only(conn, 'signal_scans', ids)
                    detail = f"{len(r['queued'])} Firma(en) eingereiht"
        except Exception as exc:  # Auftrag protokollieren, Scheduler läuft weiter
            status, detail = 'fehler', str(exc)[:400] or exc.__class__.__name__
        nxt = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=job['interval_days'])).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('UPDATE recurring_jobs SET last_run_at=?, last_status=?, last_detail=?, next_run_at=? WHERE id=?',
                     (_now(), status, detail, nxt, job_id))
        conn.commit()
        return job_view(conn.execute('SELECT * FROM recurring_jobs WHERE id=?', (job_id,)).fetchone())


def _queue_only(conn, table, ids, with_url=False):
    queued = []
    for lid in ids:
        if with_url:
            url = conn.execute('SELECT website FROM leads WHERE id=?', (lid,)).fetchone()['website']
            queued.append(conn.execute(f'INSERT INTO {table}(lead_id, url) VALUES (?,?)', (lid, url)).lastrowid)
        else:
            queued.append(conn.execute(f'INSERT INTO {table}(lead_id) VALUES (?)', (lid,)).lastrowid)
    conn.commit()
    return {'queued': queued, 'skipped': []}


def run_due(conn, db_path, start=True, now=None):
    now = now or _now()
    ran = []
    for job in conn.execute('SELECT id FROM recurring_jobs WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at', (now,)).fetchall():
        ran.append(run_job(conn, job['id'], db_path, start=start))
    return ran


def start_scheduler(db_path, every_seconds=300):
    """Hintergrund-Thread für fällige Aufträge (nur im laufenden Programm, nicht in Tests)."""
    from .model import connect
    if _SCHED['thread'] and _SCHED['thread'].is_alive():
        return _SCHED['thread']
    stop = threading.Event()

    def loop():
        while not stop.wait(60 if _SCHED.get('first', True) else every_seconds):
            _SCHED['first'] = False
            try:
                with connect(db_path) as conn:
                    run_due(conn, db_path)
            except Exception as exc:  # nie den Server mitreißen
                print('Wiederkehrende Aufträge:', repr(exc))
    t = threading.Thread(target=loop, daemon=True, name='recurring-jobs')
    _SCHED.update(thread=t, stop=stop, first=True)
    t.start()
    return t


# ---------------------------------------------------------------- HTTP

def route_quality(h, conn, method, route, query, db_path):
    if not route.startswith('/api/quality/'):
        return False
    if route == '/api/quality/settings':
        if method == 'GET':
            h._send(200, settings_view(conn))
            return True
        if method == 'PUT':
            h._send(200, save_settings(conn, h._body()))
            return True
    if route == '/api/quality/staleness' and method == 'GET':
        h._send(200, staleness_report(conn))
        return True
    if route == '/api/quality/changes':
        if method == 'GET':
            h._send(200, change_rows(conn, query.get('status', ['offen'])[0]))
            return True
    if route == '/api/quality/changes/detect' and method == 'POST':
        h._send(200, detect_changes(conn))
        return True
    m = re.fullmatch(r'/api/quality/changes/(\d+)', route)
    if m and method == 'POST':
        h._send(200, decide_change(conn, int(m.group(1)), h._body()))
        return True
    m = re.fullmatch(r'/api/quality/privacy/(\d+)/erase', route)
    if m and method == 'POST':
        h._send(200, erase_expired_person(conn, int(m.group(1)), h._body()))
        return True
    if route == '/api/quality/jobs':
        if method == 'GET':
            h._send(200, job_rows(conn))
            return True
        if method == 'POST':
            h._send(201, create_job(conn, h._body()))
            return True
    m = re.fullmatch(r'/api/quality/jobs/(\d+)(/run)?', route)
    if m:
        jid = int(m.group(1))
        if m.group(2) and method == 'POST':
            h._send(200, run_job(conn, jid, db_path))
            return True
        if not m.group(2) and method == 'PATCH':
            h._send(200, update_job(conn, jid, h._body()))
            return True
        if not m.group(2) and method == 'DELETE':
            h._send(200, delete_job(conn, jid))
            return True
    return False
