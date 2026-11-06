"""Datenbasis v2 (Phase 1): Feldbelege, Sperrliste, Dubletten und Datenschutz-Nachweise.

- `company_facts`: ein Datensatz je Feld und Quelle – Wert, Quelltyp, URL, wörtlicher Beleg,
  Verfahren, Fund-/Prüfdatum, Status und Belegqualität. Übernommene Werte stehen zusätzlich
  in den Firmenspalten des Leads (die Tabelle `leads` bleibt das Firmenobjekt).
- `suppression_list`: Widersprüche/Sperren unabhängig vom Lead. Gilt für alle Importwege und
  bleibt bestehen, wenn der Lead gelöscht wird.
- `privacy_records`: Nachweis je übernommener Person (Zweck, Rechtsgrundlage, Quelle,
  Löschfrist, Art.-14-Information).
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse

FACT_STATUSES = ('ungeprueft', 'bestaetigt', 'verworfen', 'veraltet')
FACT_FIELDS = {
    'legal_name': 'Offizieller Firmenname', 'legal_form': 'Rechtsform', 'street': 'Straße',
    'zip': 'PLZ', 'city': 'Ort', 'register_court': 'Registergericht', 'register_number': 'Registernummer',
    'vat_id': 'USt-IdNr.', 'business_phone': 'Allgemeine Telefonnummer', 'business_email': 'Allgemeine E-Mail',
    'representative': 'Vertretungsberechtigte Person', 'related_entity': 'Weitere Gesellschaft',
    'imprint_url': 'Impressums-URL',
}
LEAD_COMPANY_COLUMNS = ('legal_name', 'legal_form', 'street', 'zip', 'city', 'register_court', 'register_number',
                        'vat_id', 'business_phone', 'business_email', 'imprint_url', 'imprint_checked_at')
SUPPRESSION_KINDS = ('domain', 'name', 'register', 'email')
RETENTION_DAYS_PERSON = 365 * 2

LEGAL_SUFFIX_RE = re.compile(
    r'\b(gmbh\s*&\s*co\.?\s*kgaa|gmbh\s*&\s*co\.?\s*kg|ug\s*\(haftungsbeschränkt\)|haftungsbeschränkt|ggmbh|gmbh|mbh|kgaa|ag|se|kg|ohg|ug|e\.\s?k\.|eg|e\.\s?v\.|gbr|partg\s*mbb|partg|ltd\.?|limited|inc\.?|llc|b\.?v\.?|s\.?a\.?)(?=\W|$)',
    re.IGNORECASE)


def init_company_data(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS company_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        field TEXT NOT NULL, value TEXT NOT NULL,
        source_type TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', excerpt TEXT NOT NULL DEFAULT '',
        method TEXT NOT NULL DEFAULT '', quality TEXT NOT NULL DEFAULT 'mittel',
        found_at TEXT NOT NULL DEFAULT (datetime('now')), published_at TEXT NOT NULL DEFAULT '',
        checked_at TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'ungeprueft',
        batch_item_id INTEGER
      );
      CREATE INDEX IF NOT EXISTS idx_company_facts_lead ON company_facts(lead_id, field);
      CREATE TABLE IF NOT EXISTS suppression_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, value TEXT NOT NULL, display TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '', lead_id INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(kind, value)
      );
      CREATE TABLE IF NOT EXISTS privacy_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
        contact_id INTEGER REFERENCES decision_contacts(id) ON DELETE CASCADE,
        subject TEXT NOT NULL, data_categories TEXT NOT NULL,
        purpose TEXT NOT NULL, legal_basis TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '',
        collected_at TEXT NOT NULL DEFAULT (datetime('now')), retention_until TEXT NOT NULL,
        art14_informed_at TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT ''
      );
    ''')
    existing = {r[1] for r in conn.execute('PRAGMA table_info(leads)')}
    for col in LEAD_COMPANY_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT DEFAULT ''")
    conn.execute('CREATE INDEX IF NOT EXISTS idx_leads_register ON leads(register_number)')


# ---------------------------------------------------------------- Normalisierung & Dubletten

def normalize_domain(url):
    url = (url or '').strip().lower()
    if not url:
        return ''
    if '://' not in url:
        url = 'https://' + url
    host = (urllib.parse.urlparse(url).hostname or '').rstrip('.')
    return host[4:] if host.startswith('www.') else host


def normalize_name(name):
    s = LEGAL_SUFFIX_RE.sub(' ', (name or '').casefold())
    s = re.sub(r'&\s*co\.?', ' ', s)
    return re.sub(r'[^a-z0-9äöüß]+', '', s)


def normalize_register(court, number):
    number = re.sub(r'\s+', '', (number or '').upper())
    court = re.sub(r'^(amtsgerichts?|registergericht|ag)\s+', '', (court or '').strip().lower())
    court = re.sub(r'[^a-zäöüß]+', '', court)
    return f'{court}|{number}' if court and number else ''


def find_duplicate(conn, website='', name='', register_court='', register_number='', exclude_id=None, zip_code='', city=''):
    """Sucht einen bestehenden Lead über Domain, Registerangabe oder Name (v1.17: Identitätsregeln aus research/identity –
    verschiedene Rechtsform, Registernummer oder Orte gelten nicht als Dublette). Gibt (lead_id, 'domain'|'register'|'name') zurück."""
    from .duplicates import find_lead
    reg = normalize_register(register_court, register_number)
    if reg:  # gleiche Registerangabe inkl. Gericht bleibt ein harter Treffer
        for row in conn.execute('SELECT id, register_court, register_number FROM leads WHERE register_number<>?', ('',)):
            if (not exclude_id or row['id'] != exclude_id) and normalize_register(row['register_court'], row['register_number']) == reg:
                return row['id'], 'register'
    hit = find_lead(conn, {'name': name, 'website': website, 'register_id': register_number, 'zip': zip_code, 'city': city}, exclude_id)
    if hit and (hit[1] == 'same' or hit[3].startswith('gleiche Website')):  # eigene Domain bleibt starker Beleg
        return hit[0], ('register' if 'Register' in hit[3] else 'domain' if 'Website' in hit[3] else 'name')
    if not name and website:  # nur Domain bekannt (z. B. „Bericht für Website“): gleiche eigene Domain genügt
        from .research.identity import norm_domain
        dom = norm_domain(website)
        for row in (conn.execute('SELECT id, website FROM leads WHERE lower(website) LIKE ?', (f'%{dom}%',)) if dom else ()):
            if (not exclude_id or row['id'] != exclude_id) and norm_domain(row['website']) == dom:
                return row['id'], 'domain'
    return None, None


def _find_duplicate_exact(conn, website='', name='', register_court='', register_number='', exclude_id=None):
    """Bisheriger, exakter Abgleich (bis v1.16) – nur noch für Vergleiche/Tests."""
    domain = normalize_domain(website)
    reg = normalize_register(register_court, register_number)
    norm = normalize_name(name)
    for row in conn.execute('SELECT id, company, website, legal_name, register_court, register_number FROM leads'):
        if exclude_id and row['id'] == exclude_id:
            continue
        if domain and row['website'] and normalize_domain(row['website']) == domain:
            return row['id'], 'domain'
        if reg and normalize_register(row['register_court'], row['register_number']) == reg:
            return row['id'], 'register'
        if norm and len(norm) >= 3 and norm in (normalize_name(row['company']), normalize_name(row['legal_name'])):
            return row['id'], 'name'
    return None, None


# ---------------------------------------------------------------- Sperrliste

def _norm(kind, value):
    if kind == 'domain':
        return normalize_domain(value)
    if kind == 'name':
        return normalize_name(value)
    if kind == 'email':
        return (value or '').strip().lower()
    if kind == 'register':
        if isinstance(value, (tuple, list)):
            return normalize_register(*value)
        return value if '|' in (value or '') else ''
    raise ValueError('Unbekannte Sperrart.')


def add_suppression(conn, kind, value, reason='', lead_id=None, display=None):
    if kind not in SUPPRESSION_KINDS:
        raise ValueError('Sperrart: domain, name, register oder email.')
    norm = _norm(kind, value)
    if not norm or len(norm) < 3:
        return None
    disp = display or (' '.join(value) if isinstance(value, (tuple, list)) else str(value))
    conn.execute('INSERT OR IGNORE INTO suppression_list(kind, value, display, reason, lead_id) VALUES (?,?,?,?,?)',
                 (kind, norm, disp[:200], (reason or '')[:300], lead_id))
    return norm


def suppress_lead(conn, lead_id, reason='Widerspruch / Kontaktsperre'):
    """Überträgt alle Merkmale eines gesperrten Leads auf die Sperrliste."""
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        return []
    added = []
    if lead['website']:
        added.append(add_suppression(conn, 'domain', lead['website'], reason, lead_id))
    added.append(add_suppression(conn, 'name', lead['company'], reason, lead_id))
    if lead['legal_name']:
        added.append(add_suppression(conn, 'name', lead['legal_name'], reason, lead_id))
    if lead['register_number'] and lead['register_court']:
        added.append(add_suppression(conn, 'register', (lead['register_court'], lead['register_number']), reason, lead_id,
                                     display=f"{lead['register_court']} {lead['register_number']}"))
    if lead['business_email']:
        added.append(add_suppression(conn, 'email', lead['business_email'], reason, lead_id))
    _audit(conn, 'suppression', lead_id, 'lead_gesperrt', reason)
    return [a for a in added if a]


def check_suppressed(conn, website='', name='', register_court='', register_number='', email=''):
    hits = []
    probes = [('domain', normalize_domain(website)), ('name', normalize_name(name)),
              ('register', normalize_register(register_court, register_number)), ('email', (email or '').strip().lower())]
    for kind, value in probes:
        if value and len(value) >= 3:
            row = conn.execute('SELECT * FROM suppression_list WHERE kind=? AND value=?', (kind, value)).fetchone()
            if row:
                hits.append(dict(row))
    return hits


def assert_not_suppressed(conn, **probe):
    hits = check_suppressed(conn, **probe)
    if hits:
        what = ', '.join(f"{h['kind']} „{h['display']}“" for h in hits)
        raise ValueError(f'Auf der Sperrliste ({what}) – Widerspruch/Sperre bleibt bestehen, keine Übernahme.')


def suppression_rows(conn):
    return [dict(r) for r in conn.execute('SELECT * FROM suppression_list ORDER BY id DESC LIMIT 1000')]


def remove_suppression(conn, entry_id, reason):
    row = conn.execute('SELECT * FROM suppression_list WHERE id=?', (entry_id,)).fetchone()
    if not row:
        raise LookupError('Eintrag nicht gefunden.')
    reason = (reason or '').strip()
    if len(reason) < 5:
        raise ValueError('Begründung für das Aufheben einer Sperre angeben (z. B. „Einwilligung vom …“).')
    conn.execute('DELETE FROM suppression_list WHERE id=?', (entry_id,))
    _audit(conn, 'suppression', entry_id, 'aufgehoben', f"{row['kind']} {row['display']}: {reason}"[:500])
    conn.commit()
    return {'deleted': True}


def _audit(conn, entity, entity_id, action, detail=''):
    try:
        conn.execute('INSERT INTO audit_log(entity, entity_id, action, detail) VALUES (?,?,?,?)', (entity, entity_id, action, str(detail)[:2000]))
    except Exception:  # audit_log stammt aus dem Buchhaltungsmodul; fehlt es (alte Tests), nicht blockieren
        pass


# ---------------------------------------------------------------- Feldbelege

def add_fact(conn, lead_id, field, value, source_type, source_url='', excerpt='', method='', quality='mittel',
             status='ungeprueft', batch_item_id=None, published_at=''):
    if field not in FACT_FIELDS:
        raise ValueError(f'Unbekanntes Feld: {field}')
    if status not in FACT_STATUSES:
        raise ValueError('Ungültiger Prüfstatus.')
    value = str(value or '').strip()
    if not value:
        return None
    dup = conn.execute('''SELECT id FROM company_facts WHERE lead_id=? AND field=? AND value=? AND source_url=?
                          AND status IN ('ungeprueft','bestaetigt')''', (lead_id, field, value[:500], source_url)).fetchone()
    now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    if dup:
        conn.execute("UPDATE company_facts SET checked_at=?, status=CASE WHEN ?='bestaetigt' THEN 'bestaetigt' ELSE status END WHERE id=?",
                     (now, status, dup['id']))
        return dup['id']
    cur = conn.execute('''INSERT INTO company_facts(lead_id, field, value, source_type, source_url, excerpt, method, quality,
                          checked_at, status, batch_item_id, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (lead_id, field, value[:500], source_type, source_url[:500], (excerpt or '')[:600], method, quality,
                        now, status, batch_item_id, published_at))
    return cur.lastrowid


def facts_for_lead(conn, lead_id):
    rows = [dict(r) for r in conn.execute('SELECT * FROM company_facts WHERE lead_id=? ORDER BY field, status, id DESC', (lead_id,))]
    from .quality import stale_days, _age_days
    limit = stale_days(conn)['facts']
    for r in rows:
        r['label'] = FACT_FIELDS.get(r['field'], r['field'])
        age = _age_days(r['checked_at'])
        r['stale'] = bool(r['status'] == 'bestaetigt' and age is not None and age > limit)  # Veraltungs-Kennzeichen (Phase 6)
    return rows


def set_fact_status(conn, fact_id, status):
    if status not in FACT_STATUSES:
        raise ValueError('Status: ' + ', '.join(FACT_STATUSES))
    fact = conn.execute('SELECT * FROM company_facts WHERE id=?', (fact_id,)).fetchone()
    if not fact:
        raise LookupError('Beleg nicht gefunden.')
    conn.execute("UPDATE company_facts SET status=?, checked_at=datetime('now') WHERE id=?", (status, fact_id))
    if status == 'bestaetigt' and fact['field'] in LEAD_COMPANY_COLUMNS:
        conn.execute(f"UPDATE leads SET {fact['field']}=?, updated_at=datetime('now') WHERE id=?", (fact['value'], fact['lead_id']))
    if status in ('verworfen', 'veraltet') and fact['field'] in LEAD_COMPANY_COLUMNS:
        lead = conn.execute(f"SELECT {fact['field']} AS v FROM leads WHERE id=?", (fact['lead_id'],)).fetchone()
        if lead and lead['v'] == fact['value']:
            conn.execute(f"UPDATE leads SET {fact['field']}='', updated_at=datetime('now') WHERE id=?", (fact['lead_id'],))
    conn.commit()
    return dict(conn.execute('SELECT * FROM company_facts WHERE id=?', (fact_id,)).fetchone())


# ---------------------------------------------------------------- Datenschutz-Nachweise

def add_privacy_record(conn, lead_id, contact_id, subject, source_url, categories='Name, berufliche Funktion'):
    retention = (dt.date.today() + dt.timedelta(days=RETENTION_DAYS_PERSON)).isoformat()
    cur = conn.execute('''INSERT INTO privacy_records(lead_id, contact_id, subject, data_categories, purpose, legal_basis,
                          source_url, retention_until, note) VALUES (?,?,?,?,?,?,?,?,?)''',
                       (lead_id, contact_id, subject[:160], categories,
                        'B2B-Geschäftsanbahnung: Ansprechpartner eines Unternehmens für Leistungen der Agentur identifizieren',
                        'Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse); Quelle: Pflichtangabe im Impressum (§ 5 DDG)',
                        source_url[:500], retention,
                        'Art. 14 DSGVO: Information spätestens bei der ersten Kontaktaufnahme bzw. binnen eines Monats. Widerspruch nach Art. 21 sofort auf die Sperrliste.'))
    return cur.lastrowid


def privacy_rows(conn, lead_id=None):
    sql = 'SELECT p.*, l.company FROM privacy_records p LEFT JOIN leads l ON l.id=p.lead_id'
    params = ()
    if lead_id:
        sql += ' WHERE p.lead_id=?'
        params = (lead_id,)
    rows = [dict(r) for r in conn.execute(sql + ' ORDER BY p.id DESC LIMIT 500', params)]
    today = dt.date.today().isoformat()
    for r in rows:
        r['overdue_art14'] = not r['art14_informed_at'] and r['collected_at'][:10] <= (dt.date.today() - dt.timedelta(days=30)).isoformat()
        r['retention_expired'] = r['retention_until'] < today
    return rows


def mark_art14_informed(conn, record_id, informed_on=None):
    informed_on = informed_on or dt.date.today().isoformat()
    dt.date.fromisoformat(informed_on)
    cur = conn.execute('UPDATE privacy_records SET art14_informed_at=? WHERE id=?', (informed_on, record_id))
    if not cur.rowcount:
        raise LookupError('Nachweis nicht gefunden.')
    conn.commit()
    return {'saved': True}


ART14_TEMPLATE = (
    'Hinweis nach Art. 14 DSGVO: Ihren Namen und Ihre berufliche Funktion haben wir dem Impressum Ihres Unternehmens '
    '({source}) entnommen, um Sie als zuständigen Ansprechpartner für ein mögliches Projekt anzusprechen '
    '(Art. 6 Abs. 1 lit. f DSGVO). Verantwortlich: {controller}. Wir speichern die Angaben höchstens bis {retention}. '
    'Sie können der Verarbeitung jederzeit widersprechen (Art. 21 DSGVO) sowie Auskunft, Berichtigung und Löschung verlangen; '
    'außerdem besteht ein Beschwerderecht bei einer Datenschutzaufsichtsbehörde.')


def art14_text(conn, record_id):
    rec = conn.execute('SELECT * FROM privacy_records WHERE id=?', (record_id,)).fetchone()
    if not rec:
        raise LookupError('Nachweis nicht gefunden.')
    s = conn.execute('SELECT company_name, street, zip, city, email FROM company_settings WHERE id=1').fetchone()
    controller = ', '.join(x for x in ((s['company_name'] if s else ''), (s['street'] if s else ''),
                                       f"{s['zip']} {s['city']}".strip() if s else '', (s['email'] if s else '')) if x) or '[Ihre Firma, Anschrift, E-Mail]'
    return {'text': ART14_TEMPLATE.format(source=rec['source_url'] or 'öffentliche Quelle', controller=controller,
                                          retention=dt.date.fromisoformat(rec['retention_until']).strftime('%d.%m.%Y'))}
