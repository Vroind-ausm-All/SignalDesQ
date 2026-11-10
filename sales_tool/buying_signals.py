"""Buying Signals (Phase 3): Registerereignisse, Stellenanzeigen und Signal-Korrelation.

Datenwege – bewusst ohne Scraper geschützter Portale oder Register:
- Handelsregister: nur manueller Import von Bekanntmachungen (Text einfügen oder CSV). Eine
  kostenlose Einsicht ist keine Erlaubnis zur automatisierten Massenauswertung.
- Stellenanzeigen: Karriereseite der Firma (eigene Domain), schema.org-JobPosting, offizielle
  Bewerbermanagement-Feeds (Personio-XML) und manueller Import. Keine Indeed-/StepStone-Scraper.

Auswertung – deterministisch, mit Belegen:
- Jedes Signal hat Quelle, Veröffentlichungs- und Funddatum, Beleg, Relevanz, Pro- und Contra-
  Deutungen sowie Gesprächsfragen. Eine Stelle beweist keinen externen Dienstleistungsbedarf.
- Gleiche Ereignisse werden über einen Schlüssel bzw. über Titel + Zeitfenster zusammengeführt.
- Die Korrelation verbindet unabhängige Hinweise zu Hypothesen, nennt Gegenhinweise, Widersprüche
  und fehlende Bestätigungen. Korrelation ist keine Kausalität.
- Personendaten aus Bekanntmachungen werden minimiert (Geburtsdaten und Wohnorte entfernt).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import threading
from urllib.parse import urljoin, urlsplit

from .company_data import check_suppressed, find_duplicate, normalize_name, normalize_register, _audit

SIGNAL_STATUSES = ('ungeprueft', 'bestaetigt', 'verworfen')
MAX_IMPORT = 200
STALE_JOB_DAYS = 60
OLD_SIGNAL_DAYS = 365
ATS_HOSTS = ('jobs.personio.de', 'jobs.personio.com', 'softgarden.io', 'join.com', 'recruitee.com', 'jobs.lever.co',
             'boards.greenhouse.io', 'smartrecruiters.com', 'onlyfy.jobs', 'rexx-systems.com', 'concludis.de')

# ---------------------------------------------------------------- Schema

def init_buying_signals(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS register_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        company TEXT NOT NULL DEFAULT '', register_court TEXT NOT NULL DEFAULT '', register_number TEXT NOT NULL DEFAULT '',
        event_type TEXT NOT NULL, published_at TEXT NOT NULL DEFAULT '', text TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manuell',
        source_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS job_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL, company TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL,
        published_at TEXT NOT NULL DEFAULT '', valid_through TEXT NOT NULL DEFAULT '', excerpt TEXT NOT NULL DEFAULT '',
        first_seen_at TEXT NOT NULL DEFAULT (datetime('now')), last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS buying_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE, company TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
        polarity TEXT NOT NULL DEFAULT 'pro', areas_json TEXT NOT NULL DEFAULT '[]', offers_json TEXT NOT NULL DEFAULT '[]',
        evidence TEXT NOT NULL DEFAULT '', pro_json TEXT NOT NULL DEFAULT '[]', contra_json TEXT NOT NULL DEFAULT '[]',
        questions_json TEXT NOT NULL DEFAULT '[]', uncertainties_json TEXT NOT NULL DEFAULT '[]',
        sources_json TEXT NOT NULL DEFAULT '[]', published_at TEXT NOT NULL DEFAULT '', found_at TEXT NOT NULL DEFAULT (date('now')),
        status TEXT NOT NULL DEFAULT 'ungeprueft', is_new INTEGER NOT NULL DEFAULT 1, suppressed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS signal_correlations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        theme TEXT NOT NULL, hypothesis TEXT NOT NULL, strength TEXT NOT NULL, score INTEGER NOT NULL,
        signal_ids_json TEXT NOT NULL, counter_json TEXT NOT NULL, contradictions_json TEXT NOT NULL,
        missing_json TEXT NOT NULL, questions_json TEXT NOT NULL, offers_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS signal_scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'queued', error TEXT NOT NULL DEFAULT '', found INTEGER NOT NULL DEFAULT 0,
        log_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS idx_buying_signals_lead ON buying_signals(lead_id, published_at);
      CREATE INDEX IF NOT EXISTS idx_signal_corr_lead ON signal_correlations(lead_id);
    ''')


def recover_scans(conn):
    conn.execute("UPDATE signal_scans SET status='failed', error='Durch Neustart unterbrochen.', finished_at=datetime('now') WHERE status IN ('queued','running')")


# ---------------------------------------------------------------- Hilfen

def _today():
    return dt.date.today()


def parse_date(value):
    """dd.mm.yyyy, yyyy-mm-dd oder ISO-Zeitstempel → yyyy-mm-dd (sonst '')."""
    value = (value or '').strip()
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', value)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', value)
        if not m:
            return ''
        d, mo, y = m.groups()
    try:
        return dt.date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return ''


def age_days(iso):
    try:
        return (_today() - dt.date.fromisoformat(iso)).days
    except (TypeError, ValueError):
        return None


def recency_weight(iso):
    a = age_days(iso)
    if a is None:
        return 0.5
    return 1.0 if a <= 30 else 0.7 if a <= 90 else 0.4 if a <= 180 else 0.15


def _key(*parts):
    return hashlib.sha256('|'.join(str(p or '').strip().lower() for p in parts).encode()).hexdigest()[:24]


def _norm_title(t):
    t = re.sub(r'\((?:m|w|d|f|x|div|all genders?)(?:\s*/\s*(?:m|w|d|f|x|div))*\)|\*in\b|:in\b', ' ', (t or '').lower())
    return re.sub(r'[^a-z0-9äöüß]+', ' ', t).strip()


def minimize_personal(text):
    """Entfernt Geburtsdaten und Wohnorte aus Registertexten (Datenminimierung)."""
    text = re.sub(r',?\s*\*\s?\d{1,2}\.\d{1,2}\.\d{4}', '', text)
    text = re.sub(r'(?i)geb(?:oren)?\.?\s*(?:am)?\s*\d{1,2}\.\d{1,2}\.\d{4}', '', text)
    text = re.sub(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', '[E-Mail entfernt]', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


# ---------------------------------------------------------------- Registerereignisse

REGISTER_TYPES = {
    # Typ: (Muster, Titel, Polarität, Bereiche, Pakete, Relevanz, Gegenhinweis, Frage)
    'neueintragung': (r'neueintragung|neu eingetragen|erstmals eingetragen',
                      'Neueintragung', 'pro', ['design', 'web'], ['brand', 'pilot'],
                      'Neu gegründete Gesellschaft – möglicherweise Bedarf an Markenauftritt und Website.',
                      'Neugründungen haben oft knappe Budgets oder sind reine Holding-/Verwaltungsgesellschaften.',
                      'Ist die Gesellschaft operativ tätig, und gibt es schon einen Außenauftritt?'),
    'umbenennung': (r'firma\s+geändert|neue firma|firmenänderung|änderung der firma|geänderte firma|umfirmier',
                    'Firmenumbenennung', 'pro', ['design', 'web'], ['brand', 'conversion'],
                    'Neue Firmierung – möglicherweise Bedarf an Markenanpassung, Website und Unterlagen.',
                    'Umbenennung kann rein rechtlich sein (z. B. Rechtsformzusatz) ohne neuen Markenauftritt.',
                    'Wird mit der neuen Firmierung auch der Markenauftritt angepasst – und bis wann?'),
    'gf_wechsel': (r'nicht mehr (?:geschäftsführer|vorstand)|(?:zum|als) (?:geschäftsführer|vorstand)\w* bestellt|bestellt (?:als|zum) (?:geschäftsführer|vorstand)|'
                   r'(?:geschäftsführer|vorstand)\w*[^.\n]{0,60}(?:bestellt|abberufen|ausgeschieden)|ausgeschieden als|prokura (?:erteilt|erloschen)|(?:einzel|gesamt)prokura',
                   'Wechsel in der Geschäftsführung/Vertretung', 'pro', ['design', 'web', 'process'], ['conversion', 'portal'],
                   'Neue Entscheider bringen oft neue Prioritäten – möglicher Anlass für Neuausrichtung.',
                   'Personelle Änderung ohne erkennbare strategische Folgen; Prokura-Änderungen sind meist intern.',
                   'Welche Schwerpunkte setzt die neue Geschäftsführung in den nächsten Monaten?'),
    'sitzverlegung': (r'sitzverlegung|sitz (?:verlegt|nach|von)|neuer sitz|neue geschäftsanschrift|geschäftsanschrift (?:geändert|neu)|geänderte geschäftsanschrift',
                      'Sitzverlegung / neue Geschäftsanschrift', 'pro', ['web'], ['care', 'pilot'],
                      'Umzug oder neue Anschrift – Website, Impressum und Unterlagen müssen angepasst werden; evtl. Expansion.',
                      'Reine Adressänderung ohne Wachstum ist möglich.',
                      'Ist mit dem neuen Standort auch eine Erweiterung verbunden?'),
    'struktur': (r'verschmelzung|verschmolzen|formwechsel|spaltung|ausgliederung|beherrschungs|gewinnabführung|kapitalerhöhung|stammkapital|grundkapital|umwandlung',
                 'Änderung der Unternehmensstruktur', 'pro', ['design', 'process'], ['brand', 'portal'],
                 'Strukturänderung (z. B. Verschmelzung, Kapitalerhöhung) – möglicher Bedarf an Markenkonsolidierung oder Systemintegration.',
                 'Strukturänderungen sind oft steuerlich/rechtlich motiviert und ändern das operative Geschäft nicht.',
                 'Wie wirkt sich die Umstrukturierung auf Marken, Websites und Systeme aus?'),
    'aufloesung': (r'löschung|gelöscht|aufgelöst|auflösung|liquidation|liquidator|insolvenz',
                   'Auflösung / Löschung / Insolvenz', 'contra', [], [],
                   'Gegenhinweis: Gesellschaft wird aufgelöst oder gelöscht.',
                   'Keine Akquise empfohlen, solange der Status unklar ist.',
                   'Besteht das operative Geschäft unter anderer Firma weiter?'),
}
REGISTER_ORDER = ('aufloesung', 'neueintragung', 'umbenennung', 'struktur', 'sitzverlegung', 'gf_wechsel')
REG_NUM = re.compile(r'\b(HRB|HRA|GnR|PR|VR)\s*(\d{1,6}(?:\s?[A-Z]{1,2}\b)?)')
COURT = re.compile(r'Amtsgericht\s+([A-ZÄÖÜ][\wäöüß\-]+(?:\s(?:am|an der|im|in der|i\.)\s?[A-ZÄÖÜ]?[\wäöüß.()\-]+)?)')


def classify_register(text):
    low = text.lower()
    types = [t for t in REGISTER_ORDER if re.search(REGISTER_TYPES[t][0], low)]
    if 'neueintragung' in types:  # Neueintragungen nennen Geschäftsführung, Anschrift und Kapital – das sind keine Änderungen
        types = [t for t in types if t in ('neueintragung', 'aufloesung')]
    return types


def split_announcements(text):
    """Trennt eingefügte Bekanntmachungen an Leerzeilen-Blöcken mit Registernummer bzw. Datum."""
    blocks = [b.strip() for b in re.split(r'\n\s*\n|^-{3,}$', text or '', flags=re.M) if b.strip()]
    merged = []
    for b in blocks:
        if merged and not REG_NUM.search(b) and not re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', b):
            merged[-1] += '\n' + b
        else:
            merged.append(b)
    return merged


def parse_announcement(block):
    from .imprint import COMPANY_RE, _clean_company
    reg = REG_NUM.search(block)
    court = COURT.search(block)
    comp = None
    for line in block.splitlines():
        m = COMPANY_RE.search(line)
        if m and not re.match(r'^(Amtsgericht|Registergericht)', line.strip()):
            comp = _clean_company(m.group(1))
            break
    return {'company': comp or '', 'register_court': ('Amtsgericht ' + court.group(1).strip()) if court else '',
            'register_number': f'{reg.group(1)} {reg.group(2).strip()}' if reg else '',
            'published_at': parse_date(block), 'types': classify_register(block), 'text': minimize_personal(block)[:3000]}


def import_register(conn, data):
    if not isinstance(data, dict) or set(data) - {'text', 'csv', 'source_url'}:
        raise ValueError('Erwartet: {text} oder {csv}.')
    items = []
    if data.get('csv'):
        rows = _read_csv(data['csv'])
        for r in rows:
            text = r.get('text') or r.get('bekanntmachung') or r.get('inhalt') or ''
            p = parse_announcement('\n'.join(x for x in (r.get('firma', ''), text) if x))
            p['company'] = r.get('firma') or p['company']
            p['register_court'] = r.get('gericht') or r.get('registergericht') or p['register_court']
            p['register_number'] = r.get('registernummer') or r.get('register') or p['register_number']
            p['published_at'] = parse_date(r.get('datum') or r.get('veroeffentlicht') or '') or p['published_at']
            p['source_url'] = r.get('url') or r.get('quelle') or ''
            items.append(p)
    for block in split_announcements(data.get('text') or ''):
        p = parse_announcement(block)
        p['source_url'] = str(data.get('source_url') or '')[:500]
        items.append(p)
    if not items:
        raise ValueError('Keine Bekanntmachung erkannt.')
    if len(items) > MAX_IMPORT:
        raise ValueError(f'Höchstens {MAX_IMPORT} Bekanntmachungen pro Import.')
    out = {'imported': 0, 'duplicates': 0, 'unassigned': 0, 'suppressed': 0, 'unclassified': 0, 'signals': []}
    for p in items:
        if not p['types']:
            out['unclassified'] += 1
            p['types'] = ['sonstige']
        lead_id, _ = find_duplicate(conn, name=p['company'], register_court=p['register_court'], register_number=p['register_number'])
        suppressed = bool(check_suppressed(conn, name=p['company'], register_court=p['register_court'], register_number=p['register_number']))
        for etype in p['types']:
            key = _key('reg', normalize_register(p['register_court'], p['register_number']) or normalize_name(p['company']),
                       p['published_at'], etype, re.sub(r'\W+', '', p['text'].lower())[:300])
            try:
                cur = conn.execute('''INSERT INTO register_events(dedupe_key, lead_id, company, register_court, register_number, event_type,
                                      published_at, text, source, source_url) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                                   (key, lead_id, p['company'], p['register_court'], p['register_number'], etype, p['published_at'],
                                    p['text'], 'manuell', p.get('source_url', '')))
            except Exception as exc:
                if 'UNIQUE' in str(exc):
                    out['duplicates'] += 1
                    continue
                raise
            out['imported'] += 1
            out['unassigned'] += lead_id is None
            out['suppressed'] += suppressed
            sig = _register_signal(conn, cur.lastrowid, p, etype, lead_id, suppressed)
            if sig:
                out['signals'].append(sig)
    _audit(conn, 'signals', None, 'register_import', f"{out['imported']} Ereignisse, {out['duplicates']} Dubletten")
    conn.commit()
    return out


def _register_signal(conn, event_id, p, etype, lead_id, suppressed):
    if etype == 'sonstige':
        spec = ('', 'Sonstige Registerbekanntmachung', 'neutral', [], [], 'Bekanntmachung ohne erkannten Ereignistyp – manuell prüfen.',
                'Bedeutung unklar.', 'Was hat sich bei Ihnen zuletzt organisatorisch verändert?')
    else:
        spec = REGISTER_TYPES[etype]
    _, title, polarity, areas, offers, relevance, contra, question = spec
    excerpt = _excerpt(p['text'], spec[0]) if spec[0] else p['text'][:240]
    uncert = ['Bekanntmachung manuell importiert – Originalquelle (Registerportal) zur Bestätigung öffnen.']
    if not p['published_at']:
        uncert.append('Veröffentlichungsdatum nicht erkannt.')
    if not p['register_number']:
        uncert.append('Keine Registernummer erkannt – Zuordnung nur über den Firmennamen.')
    return upsert_signal(conn, {
        'lead_id': lead_id, 'company': p['company'], 'kind': 'register', 'category': etype, 'title': title,
        'summary': relevance, 'polarity': polarity, 'areas': areas, 'offers': offers, 'evidence': excerpt,
        'pro': [relevance] if polarity == 'pro' else [], 'contra': [contra], 'questions': [question],
        'uncertainties': uncert, 'published_at': p['published_at'],
        'source': {'type': 'registerbekanntmachung', 'ref': f'register_events:{event_id}', 'url': p.get('source_url', ''),
                   'register': f"{p['register_court']} {p['register_number']}".strip()},
        'suppressed': suppressed, 'dedupe_title': f"{etype}|{p['published_at']}"})


def _excerpt(text, pattern):
    m = re.search(pattern, text, re.I)
    if not m:
        return text[:240]
    a, b = max(0, m.start() - 90), min(len(text), m.end() + 150)
    return ('…' if a else '') + re.sub(r'\s+', ' ', text[a:b]).strip() + ('…' if b < len(text) else '')


# ---------------------------------------------------------------- Stellenanzeigen

JOB_AREAS = {
    'process': {
        'label': 'Prozessdigitalisierung',
        'terms': ['digitalisierung', 'prozessmanag', 'prozessoptimier', 'prozesskoordin', 'automatisierung', 'workflow', 'excel', 'erp', 'sap',
                  'datenpflege', 'stammdaten', 'business analyst', 'it-koordinat', 'digital transformation', 'low-code', 'power automate',
                  'dokumentenmanagement', 'mehreren systemen', 'einführung neuer software', 'verwaltungsprozess'],
        'offers': ['portal'],
        'pro': 'Digitalisierungsrolle deutet auf laufende Prozessprojekte – möglicher Bedarf an einer individuellen Anwendung oder einem Kundenportal.',
        'contra': 'Eine interne Prozessrolle kann die Digitalisierung selbst steuern; eine Agentur käme eher als Umsetzungspartner infrage.',
        'question': 'Welche Abläufe sollen als Erstes digitalisiert werden, und wer setzt sie technisch um?'},
    'web': {
        'label': 'Web & Marketing',
        'terms': ['marketing', 'online-marketing', 'digital marketing', 'performance', 'seo', 'content', 'social media', 'e-commerce', 'ecommerce',
                  'onlineshop', 'webshop', 'produktmarketing', 'product marketing', 'brand', 'marken', 'kommunikation', 'growth', 'website',
                  'webredakt', 'ux', 'ui/ux', 'grafikdesign', 'mediengestalt', 'vertrieb', 'sales', 'key account', 'online-vertrieb'],
        'offers': ['conversion', 'brand', 'care'],
        'pro': 'Ausbau von Marketing/Vertrieb – möglicher Bedarf an Website, Anfrage-/Conversion-Strecke, Inhalten oder Designvorlagen.',
        'contra': 'Eine neue Marketing- oder Webrolle kann bedeuten, dass Website und Kampagnen künftig intern betreut werden.',
        'question': 'Welche Aufgaben soll die neue Rolle übernehmen, und wo wäre externe Unterstützung sinnvoll?'},
    'software': {
        'label': 'Software & Anwendungen',
        'terms': ['software', 'entwickler', 'developer', 'engineer', 'it-projekt', 'systemintegration', 'schnittstelle', 'api', 'plattform',
                  'portal', 'app-', ' app ', 'anwendungsentwicklung', 'product owner', 'scrum', 'cloud', 'devops', 'data engineer',
                  'kundenplattform', 'digitale services', 'interne anwendung'],
        'offers': ['portal'],
        'pro': 'Technische Rolle deutet auf geplante Systemintegrationen, Plattformen oder digitale Services.',
        'contra': 'Eigene Entwicklerstellen sprechen für Inhouse-Entwicklung; externe Unterstützung eher für Lastspitzen oder Spezialthemen.',
        'question': 'Welche Anwendungen oder Integrationen stehen auf der Roadmap, und wie ist das Team aufgestellt?'},
}
JOB_TITLE_RE = re.compile(r'\((?:m|w|d|f|x)\s*/\s*(?:m|w|d|f|x)(?:\s*/\s*(?:m|w|d|f|x))?\)|\b(?:all genders|m/w/d|w/m/d)\b|'
                          r'\b(?:manager|managerin|entwickler|developer|engineer|referent|spezialist|specialist|berater|consultant|leiter|leitung|'
                          r'koordinator|sachbearbeiter|mitarbeiter|assistent|designer|redakteur|analyst|werkstudent|praktikant|ausbildung|trainee)\w*', re.I)


def classify_job(title, text=''):
    low_title, low = f' {title.lower()} ', f' {title.lower()} {text.lower()} '
    hits = {}
    for key, spec in JOB_AREAS.items():
        terms = [t for t in spec['terms'] if t in low]
        if terms:
            score = sum(3 if t in low_title else 1 for t in terms)
            hits[key] = {'terms': terms[:6], 'score': score}
    return dict(sorted(hits.items(), key=lambda x: -x[1]['score']))


def job_signal_payload(job, lead_id, suppressed=False):
    hits = classify_job(job['title'], job.get('text', ''))
    if not hits:
        return None
    areas = list(hits)
    pro = [JOB_AREAS[a]['pro'] for a in areas]
    contra = ['Eine ausgeschriebene Stelle beweist keinen externen Dienstleistungsbedarf.'] + [JOB_AREAS[a]['contra'] for a in areas]
    uncert = []
    published = job.get('published_at') or ''
    age = age_days(published)
    if not published:
        uncert.append('Veröffentlichungsdatum unbekannt – nur Funddatum vorhanden.')
    elif age is not None and age > STALE_JOB_DAYS:
        contra.append(f'Anzeige ist {age} Tage alt – Stelle ist möglicherweise bereits besetzt oder das Vorhaben verschoben.')
    expired = job.get('valid_through') and job['valid_through'] < _today().isoformat()
    if expired:
        contra.append(f"Ausschreibung ist seit {job['valid_through']} abgelaufen.")
    if re.search(r'werkstudent|praktik|ausbildung|azubi|trainee', job['title'], re.I):
        uncert.append('Einstiegs-/Ausbildungsstelle – geringe Aussagekraft für Projektbudgets.')
    offers = []
    for a in areas:
        offers += [o for o in JOB_AREAS[a]['offers'] if o not in offers]
    evidence = f"„{job['title']}“ – erkannt: " + '; '.join(f"{JOB_AREAS[a]['label']} ({', '.join(hits[a]['terms'][:4])})" for a in areas)
    return {'lead_id': lead_id, 'company': job.get('company', ''), 'kind': 'job', 'category': 'job_' + areas[0],
            'title': f"Stellenanzeige: {job['title'][:140]}", 'summary': pro[0], 'polarity': 'contra' if expired else 'pro',
            'areas': areas, 'offers': offers, 'evidence': evidence[:600], 'pro': pro, 'contra': contra,
            'questions': [JOB_AREAS[a]['question'] for a in areas], 'uncertainties': uncert, 'published_at': published,
            'source': {'type': job['source_type'], 'ref': f"job_signals:{job.get('id', '')}", 'url': job.get('source_url', '')},
            'suppressed': suppressed, 'dedupe_title': _norm_title(job['title'])}


def store_job(conn, job, lead_id):
    """Speichert eine Stellenanzeige (Rohdaten) und erzeugt/aktualisiert das Signal."""
    title = re.sub(r'\s+', ' ', job['title']).strip()[:200]
    if len(title) < 4:
        return None
    job = dict(job, title=title)
    key = _key('job', lead_id or normalize_name(job.get('company', '')), _norm_title(title), job.get('source_url', ''))
    row = conn.execute('SELECT id FROM job_signals WHERE dedupe_key=?', (key,)).fetchone()
    if row:
        conn.execute("UPDATE job_signals SET last_seen_at=datetime('now') WHERE id=?", (row['id'],))
        return {'duplicate': True, 'job_id': row['id']}
    excerpt = re.sub(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\+?\d[\d\s/()-]{7,}\d', '[entfernt]', job.get('text', ''))[:600]
    cur = conn.execute('''INSERT INTO job_signals(dedupe_key, lead_id, company, title, source_url, source_type, published_at, valid_through, excerpt)
                          VALUES (?,?,?,?,?,?,?,?,?)''', (key, lead_id, job.get('company', ''), title, job.get('source_url', ''),
                                                          job['source_type'], job.get('published_at', ''), job.get('valid_through', ''), excerpt))
    job['id'] = cur.lastrowid
    suppressed = bool(check_suppressed(conn, name=job.get('company', ''))) if not lead_id else False
    payload = job_signal_payload(job, lead_id, suppressed)
    sig = upsert_signal(conn, payload) if payload else None
    return {'duplicate': False, 'job_id': cur.lastrowid, 'signal': sig, 'classified': bool(payload)}


def import_jobs(conn, data):
    if not isinstance(data, dict) or set(data) - {'csv', 'text', 'lead_id', 'company', 'source_url', 'published_at'}:
        raise ValueError('Erwartet: {csv} oder {text, lead_id|company, source_url, published_at}.')
    jobs = []
    if data.get('csv'):
        for r in _read_csv(data['csv']):
            title = r.get('titel') or r.get('title') or r.get('stelle') or ''
            jobs.append({'company': r.get('firma') or r.get('company') or '', 'title': title, 'text': r.get('text') or r.get('beschreibung') or '',
                         'source_url': r.get('url') or r.get('quelle') or '', 'published_at': parse_date(r.get('datum') or r.get('veroeffentlicht') or ''),
                         'valid_through': parse_date(r.get('gueltig_bis') or ''), 'source_type': 'manuell'})
    if data.get('text'):
        text = data['text'].strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        jobs.append({'company': data.get('company') or '', 'title': lines[0] if lines else '', 'text': '\n'.join(lines[1:])[:8000],
                     'source_url': str(data.get('source_url') or '')[:500], 'published_at': parse_date(data.get('published_at') or '') or parse_date(text[:400]),
                     'source_type': 'manuell'})
    if not jobs:
        raise ValueError('Keine Stellenanzeige übergeben.')
    if len(jobs) > MAX_IMPORT:
        raise ValueError(f'Höchstens {MAX_IMPORT} Anzeigen pro Import.')
    out = {'imported': 0, 'duplicates': 0, 'unclassified': 0, 'unassigned': 0, 'suppressed': 0}
    for job in jobs:
        lead_id = data.get('lead_id')
        if lead_id is not None:
            if isinstance(lead_id, bool) or not isinstance(lead_id, int) or not conn.execute('SELECT 1 FROM leads WHERE id=?', (lead_id,)).fetchone():
                raise ValueError('Lead nicht gefunden.')
        else:
            lead_id, _ = find_duplicate(conn, website=job['source_url'] if job['source_url'] else '', name=job['company'])
        if not job['title']:
            continue
        if lead_id is None and check_suppressed(conn, name=job['company']):
            out['suppressed'] += 1
        res = store_job(conn, job, lead_id)
        if not res:
            continue
        if res['duplicate']:
            out['duplicates'] += 1
            continue
        out['imported'] += 1
        out['unclassified'] += not res['classified']
        out['unassigned'] += lead_id is None
    _audit(conn, 'signals', None, 'job_import', f"{out['imported']} Anzeigen")
    conn.commit()
    return out


# ---- Karriereseiten (eigene Domain + offizielle ATS-Feeds)

CAREER_WORDS = ('karriere', 'jobs', 'stellen', 'career', 'offene positionen', 'join us', 'arbeiten bei', 'stellenangebote', 'vacancies')


def _career_links(origin, links):
    from .website_analyzer import same_company_host
    out = []
    for l in links:
        href = urljoin(origin, l.get('href', ''))
        label = (l.get('text', '') + ' ' + urlsplit(href).path).lower()
        if not any(w in label for w in CAREER_WORDS):
            continue
        host = (urlsplit(href).hostname or '').lower()
        if same_company_host(origin, href) or any(host == h or host.endswith('.' + h) for h in ATS_HOSTS):
            if href not in out:
                out.append(href.split('#')[0])
    return out[:3]


def _jsonld_jobs(raw):
    """Stellenanzeigen aus JSON-LD/Microdata (JobPosting) – seit v1.16 über research.extractors.structured (eine Implementierung)."""
    from .research.extractors import structured
    jobs = []
    for j in structured.extract(raw)['jobpostings']:
        jobs.append({'title': j['title'], 'published_at': parse_date(j['date_posted']), 'valid_through': parse_date(j['valid_through']),
                     'text': re.sub(r'\s+', ' ', j['description'])[:4000], 'city': j['city'], 'remote': j['remote'],
                     'source_type': 'karriereseite_jsonld' if j['method'] == 'jsonld' else 'karriereseite_microdata'})
    return jobs


def _personio_jobs(raw):
    import xml.etree.ElementTree as ET
    if b'<!DOCTYPE' in raw[:2000].upper() or b'<!ENTITY' in raw.upper():
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    jobs = []
    for pos in root.iter('position'):
        name = (pos.findtext('name') or '').strip()
        dept = (pos.findtext('department') or '').strip()
        desc = ' '.join((d.findtext('value') or '') for d in pos.iter('jobDescription'))
        jobs.append({'title': name, 'published_at': parse_date(pos.findtext('createdAt') or ''), 'text': f'{dept} {re.sub(r"<[^>]+>", " ", desc)}'[:4000],
                     'source_type': 'ats_feed_personio'})
    return jobs


def _listed_jobs(text):
    jobs = []
    for line in text.splitlines():
        line = line.strip()
        if 6 <= len(line) <= 140 and JOB_TITLE_RE.search(line) and not re.search(r'bewerb|datenschutz|cookie|newsletter|initiativ', line, re.I):
            jobs.append({'title': line, 'published_at': '', 'text': '', 'source_type': 'karriereseite'})
    return jobs[:40]


def scan_career(website, company=''):
    """Liest Karriereseite(n) einer Firma. Rückgabe: (jobs, log). Wirft CrawlError bei Totalausfall."""
    from . import imprint
    from .website_analyzer import CrawlError
    log, jobs = [], []
    successful = 0
    failed = 0
    url = website if '://' in website else 'https://' + website
    home, ctype, data = imprint.FETCH(url, None)
    _, links, _ = imprint.html_to_text(data)
    candidates = _career_links(home, links)
    if not candidates:
        root = f'{urlsplit(home).scheme}://{urlsplit(home).netloc}'
        candidates = [root + p for p in ('/karriere', '/jobs')]
        log.append('Kein Karriere-Link auf der Startseite – Standardpfade geprüft.')
    for cand in candidates:
        imprint.SLEEP(imprint.REQUEST_DELAY)
        host = (urlsplit(cand).hostname or '').lower()
        try:
            if 'jobs.personio' in host:
                feed = f'{urlsplit(cand).scheme}://{urlsplit(cand).netloc}/xml'
                _, _, raw = imprint.FETCH(feed, None)
                found = _personio_jobs(raw)
                successful += 1
                for j in found:
                    j['source_url'] = cand
                jobs += found
                log.append(f'Personio-XML-Feed: {len(found)} Stelle(n).')
                continue
            final, ctype, raw = imprint.FETCH(cand, home if not any(host.endswith(h) for h in ATS_HOSTS) else None)
            successful += 1
        except CrawlError as exc:
            failed += 1
            log.append(f'{cand}: {exc}')
            continue
        from .research.fetchers.base import decode_html
        html = decode_html(raw)
        found = _jsonld_jobs(html)
        if not found:
            text, sublinks, _ = imprint.html_to_text(raw)
            found = _listed_jobs(text)
        for j in found:
            j['source_url'] = final
        log.append(f'{final}: {len(found)} Stelle(n) erkannt.')
        jobs += found
        if found:
            break
    if candidates and not successful:
        raise CrawlError('Karriereseiten konnten nicht geprüft werden: ' + '; '.join(log)[-700:])
    if failed:
        log.append(f'Unvollständige Prüfung: {failed} Karriereseite(n) nicht abrufbar.')
    seen, unique = set(), []
    for j in jobs:
        k = _norm_title(j['title'])
        if k and k not in seen:
            seen.add(k)
            unique.append(dict(j, company=company))
    return unique, log


SCAN_LOCK = threading.Lock()
_SCAN_WORKER = {'thread': None}


def enqueue_scans(conn, lead_ids, db_path):
    if not isinstance(lead_ids, list) or not 1 <= len(lead_ids) <= 20 or any(isinstance(i, bool) or not isinstance(i, int) for i in lead_ids):
        raise ValueError('1–20 Lead-IDs angeben.')
    queued, skipped = [], []
    for lid in dict.fromkeys(lead_ids):
        lead = conn.execute('SELECT website, stage, permission FROM leads WHERE id=?', (lid,)).fetchone()
        if not lead or not lead['website']:
            skipped.append({'lead_id': lid, 'reason': 'keine Website'})
        elif lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
            skipped.append({'lead_id': lid, 'reason': 'gesperrt'})
        else:
            queued.append(conn.execute('INSERT INTO signal_scans(lead_id) VALUES (?)', (lid,)).lastrowid)
    conn.commit()
    if queued:
        with SCAN_LOCK:
            t = _SCAN_WORKER['thread']
            if not (t and t.is_alive()):
                t = threading.Thread(target=_scan_worker, args=(db_path,), daemon=True, name='career-scan')
                _SCAN_WORKER['thread'] = t
                t.start()
    return {'queued': queued, 'skipped': skipped}


def wait_scans(timeout=60):
    t = _SCAN_WORKER['thread']
    if t:
        t.join(timeout)


def _scan_worker(db_path):
    from .model import connect
    from .website_analyzer import CrawlError
    while True:
        with connect(db_path) as conn:
            row = conn.execute("SELECT s.id, s.lead_id, l.website, l.company FROM signal_scans s JOIN leads l ON l.id=s.lead_id WHERE s.status='queued' ORDER BY s.id LIMIT 1").fetchone()
            if not row:
                return
            conn.execute("UPDATE signal_scans SET status='running' WHERE id=?", (row['id'],))
            conn.commit()
        try:
            jobs, log = scan_career(row['website'], row['company'])
            status, error = 'done', ''
        except CrawlError as exc:
            jobs, log, status, error = [], [], 'failed', str(exc)
        except Exception as exc:
            jobs, log, status, error = [], [], 'failed', f'Unerwarteter Fehler: {exc.__class__.__name__}'
        with connect(db_path) as conn:
            found = 0
            for j in jobs:
                res = store_job(conn, j, row['lead_id'])
                found += bool(res and not res['duplicate'] and res.get('classified'))
            conn.execute("UPDATE signal_scans SET status=?, error=?, found=?, log_json=?, finished_at=datetime('now') WHERE id=?",
                         (status, error[:500], found, json.dumps(log, ensure_ascii=False), row['id']))
            conn.commit()


# ---------------------------------------------------------------- Signale speichern & zusammenführen

def upsert_signal(conn, s):
    """Neues Signal oder – bei gleichem Ereignis aus weiterer Quelle – Quelle am bestehenden Signal ergänzen."""
    window = 30
    if s.get('lead_id') or s.get('company'):
        cond, params = ('lead_id=?', [s['lead_id']]) if s.get('lead_id') else ('lead_id IS NULL AND company=?', [s['company']])
        cat_cond = '' if s['kind'] == 'job' else ' AND category=?'
        cat_args = () if s['kind'] == 'job' else (s['category'],)
        for row in conn.execute(f"SELECT * FROM buying_signals WHERE {cond} AND kind=?{cat_cond} AND status<>'verworfen'",
                                (*params, s['kind'], *cat_args)):
            same_title = json.loads(row['sources_json'] or '[]') and row['title'] and _same_event(row, s)
            if not same_title:
                continue
            a, b = row['published_at'] or row['found_at'], s['published_at'] or _today().isoformat()
            try:
                close = abs((dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days) <= window
            except ValueError:
                close = True
            if close:
                sources = json.loads(row['sources_json'])
                if not any(x.get('ref') == s['source'].get('ref') for x in sources):
                    sources.append(s['source'])
                published = min(x for x in (row['published_at'], s['published_at']) if x) if (row['published_at'] or s['published_at']) else ''
                conn.execute('UPDATE buying_signals SET sources_json=?, published_at=? WHERE id=?', (json.dumps(sources, ensure_ascii=False), published, row['id']))
                return {'id': row['id'], 'merged': True}
    cur = conn.execute('''INSERT INTO buying_signals(lead_id, company, kind, category, title, summary, polarity, areas_json, offers_json, evidence,
                          pro_json, contra_json, questions_json, uncertainties_json, sources_json, published_at, suppressed)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (s.get('lead_id'), s.get('company', ''), s['kind'], s['category'], s['title'], s.get('summary', ''), s.get('polarity', 'pro'),
                        json.dumps(s.get('areas', [])), json.dumps(s.get('offers', [])), s.get('evidence', ''), json.dumps(s.get('pro', []), ensure_ascii=False),
                        json.dumps(s.get('contra', []), ensure_ascii=False), json.dumps(s.get('questions', []), ensure_ascii=False),
                        json.dumps(s.get('uncertainties', []), ensure_ascii=False), json.dumps([s['source']], ensure_ascii=False),
                        s.get('published_at', ''), int(bool(s.get('suppressed')))))
    return {'id': cur.lastrowid, 'merged': False}


def _same_event(row, s):
    if s['kind'] == 'job':
        return _norm_title(row['title'].replace('Stellenanzeige:', '')) == s['dedupe_title']
    return row['title'] == s['title']


def signal_view(row):
    d = dict(row)
    for k in ('areas', 'offers', 'pro', 'contra', 'questions', 'uncertainties', 'sources'):
        d[k] = json.loads(d.pop(k + '_json') or '[]')
    d['age_days'] = age_days(d['published_at']) if d['published_at'] else None
    d['recency'] = recency_weight(d['published_at'])
    d['old'] = d['age_days'] is not None and d['age_days'] > OLD_SIGNAL_DAYS
    return d


def list_signals(conn, params):
    sql, args = 'SELECT s.*, l.company AS lead_company FROM buying_signals s LEFT JOIN leads l ON l.id=s.lead_id WHERE 1=1', []
    if params.get('lead_id'):
        sql += ' AND s.lead_id=?'
        args.append(int(params['lead_id']))
    if params.get('kind') in ('register', 'job', 'manual'):
        sql += ' AND s.kind=?'
        args.append(params['kind'])
    if params.get('status') in SIGNAL_STATUSES:
        sql += ' AND s.status=?'
        args.append(params['status'])
    if params.get('only_new') == '1':
        sql += ' AND s.is_new=1'
    if params.get('unassigned') == '1':
        sql += ' AND s.lead_id IS NULL'
    sql += " ORDER BY s.is_new DESC, COALESCE(NULLIF(s.published_at,''), s.found_at) DESC, s.id DESC LIMIT 300"
    return [signal_view(r) for r in conn.execute(sql, args)]


def update_signal(conn, signal_id, data):
    if not isinstance(data, dict) or set(data) - {'status', 'lead_id', 'seen'}:
        raise ValueError('Erlaubt: status, lead_id, seen.')
    row = conn.execute('SELECT * FROM buying_signals WHERE id=?', (signal_id,)).fetchone()
    if not row:
        raise LookupError('Signal nicht gefunden.')
    if 'status' in data:
        if data['status'] not in SIGNAL_STATUSES:
            raise ValueError('Status: ' + ', '.join(SIGNAL_STATUSES))
        conn.execute('UPDATE buying_signals SET status=?, is_new=0 WHERE id=?', (data['status'], signal_id))
    if 'lead_id' in data:
        lid = data['lead_id']
        lead = conn.execute('SELECT stage, permission FROM leads WHERE id=?', (lid,)).fetchone() if isinstance(lid, int) and not isinstance(lid, bool) else None
        if not lead:
            raise ValueError('Lead nicht gefunden.')
        conn.execute('UPDATE buying_signals SET lead_id=?, suppressed=? WHERE id=?', (lid, int(lead['stage'] == 'gesperrt'), signal_id))
        ref = json.loads(row['sources_json'] or '[{}]')[0].get('ref', '')
        table, _, rid = ref.partition(':')
        if table in ('register_events', 'job_signals') and rid.isdigit():
            conn.execute(f'UPDATE {table} SET lead_id=? WHERE id=?', (lid, int(rid)))
    if data.get('seen') is True:
        conn.execute('UPDATE buying_signals SET is_new=0 WHERE id=?', (signal_id,))
    conn.commit()
    return signal_view(conn.execute('SELECT * FROM buying_signals WHERE id=?', (signal_id,)).fetchone())


LEAD_SIGNAL_MAP = {'job_web': 'offene_stelle', 'job_software': 'offene_stelle', 'job_process': 'offene_stelle', 'umbenennung': 'digitalprojekt',
                   'neueintragung': 'expansion', 'struktur': 'expansion', 'sitzverlegung': 'expansion', 'gf_wechsel': 'expansion'}


def promote_to_lead(conn, signal_id):
    """Überträgt ein bestätigtes Signal in die Lead-Felder (Signaltyp/-datum/-quelle), ohne Bestehendes zu überschreiben."""
    row = conn.execute('SELECT * FROM buying_signals WHERE id=?', (signal_id,)).fetchone()
    if not row:
        raise LookupError('Signal nicht gefunden.')
    if row['status'] != 'bestaetigt' or not row['lead_id']:
        raise ValueError('Nur bestätigte, einem Lead zugeordnete Signale übernehmen.')
    if row['polarity'] != 'pro' or row['category'] not in LEAD_SIGNAL_MAP:
        raise ValueError('Dieses Signal eignet sich nicht als Projektanlass.')
    lead = conn.execute('SELECT signal_type, signal_note FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
    if lead['signal_type'] not in ('kein_signal', '') or lead['signal_note']:
        raise ValueError('Lead hat bereits ein dokumentiertes Signal – bestehende Daten werden nicht überschrieben.')
    src = next((x.get('url') for x in json.loads(row['sources_json']) if x.get('url')), '')
    conn.execute("""UPDATE leads SET signal_type=?, signal_date=?, signal_source=?, signal_note=?, updated_at=datetime('now') WHERE id=?""",
                 (LEAD_SIGNAL_MAP[row['category']], row['published_at'] or row['found_at'], src if src.startswith('http') else '',
                  f"{row['title']} – {row['summary']}"[:2000], row['lead_id']))
    conn.commit()
    return {'saved': True}


# ---------------------------------------------------------------- Korrelation

THEMES = {
    'brand': {'label': 'Markenauftritt & Corporate Design',
              'hypothesis': 'Möglicherweise besteht Bedarf, Markenauftritt und Gestaltung an die veränderte Unternehmenssituation anzupassen.',
              'signals': {'umbenennung', 'neueintragung', 'struktur', 'gf_wechsel'}, 'job_areas': {'web'}, 'site_area': 'design', 'offers': ['brand']},
    'web': {'label': 'Website, Produktpräsentation & Anfragen',
            'hypothesis': 'Möglicherweise besteht Potenzial, die digitale Produktpräsentation und die Verarbeitung eingehender Anfragen zu verbessern.',
            'signals': {'produktlaunch', 'digitalprojekt', 'sitzverlegung', 'umbenennung'}, 'job_areas': {'web'}, 'site_area': 'web', 'offers': ['conversion', 'pilot']},
    'process': {'label': 'Digitalisierung von Kunden- oder Verwaltungsprozessen',
                'hypothesis': 'Möglicherweise besteht Interesse, einen manuellen Kunden- oder Verwaltungsprozess als Portal oder Anwendung zu digitalisieren.',
                'signals': {'prozessproblem', 'struktur'}, 'job_areas': {'process', 'software'}, 'site_area': 'process', 'offers': ['portal']},
    'growth': {'label': 'Wachstum & skalierbare Vertriebsprozesse',
               'hypothesis': 'Möglicherweise befindet sich das Unternehmen in einer Wachstumsphase, in der skalierbare Anfrage- und Vertriebsprozesse wichtiger werden.',
               'signals': {'expansion', 'sitzverlegung', 'struktur', 'neueintragung'}, 'job_areas': {'web', 'process'}, 'site_area': None, 'offers': ['conversion', 'care']},
}
MISSING_DEFAULT = ['Bestätigung des Bedarfs im Gespräch (Problem, Auswirkung, gewünschtes Ergebnis)', 'Zuständige Person und Entscheidungsweg',
                   'Zeitrahmen und Budgetstatus', 'Ob die Leistung intern oder extern erbracht werden soll']


def correlate(conn, lead_id):
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise LookupError('Lead nicht gefunden.')
    sigs = [signal_view(r) for r in conn.execute("SELECT * FROM buying_signals WHERE lead_id=? AND status<>'verworfen'", (lead_id,))]
    # Lead-eigenes Signalfeld und Website-Befunde als zusätzliche, unabhängige Hinweise
    extra = []
    if lead['signal_type'] and lead['signal_type'] != 'kein_signal':
        extra.append({'id': None, 'kind': 'manual', 'category': lead['signal_type'], 'title': f"Lead-Signal: {lead['signal_type']}",
                      'polarity': 'pro', 'areas': [], 'published_at': lead['signal_date'] or '', 'recency': recency_weight(lead['signal_date'] or ''),
                      'evidence': lead['signal_note'] or '', 'contra': [], 'questions': []})
    site = conn.execute('''SELECT s.design, s.web, s.process, s.audit_id, a.finished_at FROM website_scores s JOIN website_audits a ON a.id=s.audit_id
                           WHERE s.lead_id=? ORDER BY s.id DESC LIMIT 1''', (lead_id,)).fetchone()
    site_findings = []
    if site:
        site_findings = [dict(r) for r in conn.execute("""SELECT rubric, area, label, evidence FROM website_findings WHERE audit_id=? AND result='auffaellig'
                                                          AND review_status<>'verworfen' ORDER BY weight DESC""", (site['audit_id'],))]
    contradictions = []
    stops = [s for s in sigs if s['category'] == 'aufloesung']
    pros = [s for s in sigs if s['polarity'] == 'pro'] + extra
    if stops:
        contradictions.append(f"Gegenhinweis „{stops[0]['title']}“ ({stops[0]['published_at'] or 'Datum unbekannt'}) widerspricht den übrigen Signalen – Status klären, keine Akquise bis dahin.")
    expired = [s for s in sigs if s['kind'] == 'job' and s['polarity'] == 'contra']
    if expired:
        contradictions.append(f'{len(expired)} Stellenanzeige(n) bereits abgelaufen – Signal möglicherweise überholt.')
    results = []
    for key, theme in THEMES.items():
        support = []
        for s in pros:
            if s['kind'] in ('register', 'manual') and s['category'] in theme['signals']:
                support.append(s)
            elif s['kind'] == 'job' and set(s['areas']) & theme['job_areas']:
                support.append(s)
        site_support = []
        if site and theme['site_area'] and (site[theme['site_area']] or 0) >= 50:
            site_support = [f for f in site_findings if f['area'] == theme['site_area']][:3]
        kinds = {s['kind'] for s in support} | ({'website'} if site_support else set())
        if not support and not site_support:
            continue
        score = round(sum(25 * s['recency'] for s in support) + (25 if site_support else 0))
        counter = []
        for s in support:
            counter += [c for c in s.get('contra', []) if c not in counter][:2]
        if site and theme['site_area'] and site[theme['site_area']] is not None and site[theme['site_area']] < 20:
            counter.append(f"Website-Bewertung zeigt im Bereich „{theme['label']}“ wenig belegbares Potenzial ({site[theme['site_area']]}).")
        if stops:
            score = min(score, 10)
        strength = 'mehrere unabhängige Hinweise' if len(kinds) >= 2 and score >= 40 else ('einzelner Hinweis' if len(support) + bool(site_support) == 1 else 'schwach')
        if len(kinds) < 2:
            counter.append('Nur eine Quellenart – unabhängige Bestätigung fehlt.')
        old = [s for s in support if age_days(s['published_at']) and age_days(s['published_at']) > 180]
        missing = list(MISSING_DEFAULT)
        if old:
            missing.insert(0, f'Aktualität: {len(old)} Hinweis(e) älter als 6 Monate – ist das Thema noch aktuell?')
        if any(s['kind'] == 'job' for s in support):
            missing.insert(0, 'Ob die ausgeschriebene Stelle schon besetzt ist und welche Aufgaben sie übernimmt')
        questions = []
        for s in support:
            questions += [q for q in s.get('questions', []) if q not in questions]
        offers = list(theme['offers'])
        evidence = [{'id': s['id'], 'kind': s['kind'], 'title': s['title'], 'date': s['published_at'] or 'unbekannt'} for s in support]
        evidence += [{'id': None, 'kind': 'website', 'title': f"Website-Befund: {f['label']}", 'date': (site['finished_at'] or '')[:10]} for f in site_support]
        results.append({'theme': key, 'label': theme['label'], 'hypothesis': theme['hypothesis'], 'strength': strength, 'score': min(100, score),
                        'evidence': evidence, 'counter': counter[:6], 'contradictions': contradictions, 'missing': missing[:6],
                        'questions': questions[:5], 'offers': offers})
    results.sort(key=lambda r: -r['score'])
    conn.execute('DELETE FROM signal_correlations WHERE lead_id=?', (lead_id,))
    for r in results:
        conn.execute('''INSERT INTO signal_correlations(lead_id, theme, hypothesis, strength, score, signal_ids_json, counter_json, contradictions_json,
                        missing_json, questions_json, offers_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                     (lead_id, r['theme'], r['hypothesis'], r['strength'], r['score'], json.dumps(r['evidence'], ensure_ascii=False),
                      json.dumps(r['counter'], ensure_ascii=False), json.dumps(r['contradictions'], ensure_ascii=False),
                      json.dumps(r['missing'], ensure_ascii=False), json.dumps(r['questions'], ensure_ascii=False), json.dumps(r['offers'])))
    conn.execute('UPDATE buying_signals SET is_new=0 WHERE lead_id=?', (lead_id,))
    conn.commit()
    return {'lead_id': lead_id, 'hypotheses': results, 'contradictions': contradictions,
            'signals_considered': len(sigs) + len(extra), 'website_considered': bool(site),
            'notice': 'Korrelation ist keine Kausalität: Die Hypothesen verbinden öffentlich sichtbare Hinweise und müssen im Gespräch bestätigt werden. Keine Aussage über Kaufbereitschaft oder Budget.'}


def signal_strength_for_scoring(conn, lead_id):
    """Projektanlass für das Website-Scoring aus echten Signalen (jüngstes bestätigtes/ungeprüftes Pro-Signal)."""
    rows = [signal_view(r) for r in conn.execute("SELECT * FROM buying_signals WHERE lead_id=? AND status<>'verworfen'", (lead_id,))]
    if any(r['category'] == 'aufloesung' for r in rows):
        return 0, 'Gegenhinweis: Auflösung/Löschung im Register.'
    pros = [r for r in rows if r['polarity'] == 'pro']
    if not pros:
        return None, None
    best = max(pros, key=lambda r: (r['recency'], r['status'] == 'bestaetigt'))
    score = round(100 * best['recency'])
    when = f"vor {best['age_days']} Tagen" if best['age_days'] is not None else 'Datum unbekannt'
    return score, f"{len(pros)} Kaufsignal(e), jüngstes: {best['title']} ({when}{', bestätigt' if best['status'] == 'bestaetigt' else ', ungeprüft'})."


# ---------------------------------------------------------------- CSV

def _read_csv(text):
    if not isinstance(text, str) or len(text) > 2_000_000:
        raise ValueError('CSV ungültig oder zu groß.')
    text = text.lstrip('﻿')
    header = text.splitlines()[0] if text.strip() else ''
    delim = max((';', ',', '\t'), key=header.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    return [{(k or '').strip().lower(): (v or '').strip() for k, v in r.items()} for r in reader]


# ---------------------------------------------------------------- HTTP-Routen

def route_signals(h, conn, method, route, query, db_path):
    if route == '/api/signals' and method == 'GET':
        h._send(200, list_signals(conn, {k: v[0] for k, v in query.items()}))
        return True
    if route == '/api/signals/summary' and method == 'GET':
        row = conn.execute("SELECT COUNT(*) AS total, SUM(is_new) AS new, SUM(lead_id IS NULL) AS unassigned FROM buying_signals WHERE status<>'verworfen'").fetchone()
        leads = [dict(r) for r in conn.execute('''SELECT l.id, l.company, COUNT(s.id) AS signals, SUM(s.is_new) AS new,
                                                  (SELECT COUNT(*) FROM signal_correlations c WHERE c.lead_id=l.id) AS hypotheses
                                                  FROM leads l JOIN buying_signals s ON s.lead_id=l.id AND s.status<>'verworfen'
                                                  GROUP BY l.id ORDER BY new DESC, signals DESC LIMIT 100''')]
        scans = [dict(r) for r in conn.execute('''SELECT s.id, s.lead_id, l.company, s.status, s.error, s.found, s.created_at FROM signal_scans s
                                                  JOIN leads l ON l.id=s.lead_id ORDER BY s.id DESC LIMIT 20''')]
        h._send(200, {'total': row['total'] or 0, 'new': row['new'] or 0, 'unassigned': row['unassigned'] or 0, 'leads': leads, 'scans': scans})
        return True
    if route == '/api/signals/register-import' and method == 'POST':
        h._send(201, import_register(conn, h._body(max_len=2_500_000)))
        return True
    if route == '/api/signals/job-import' and method == 'POST':
        h._send(201, import_jobs(conn, h._body(max_len=2_500_000)))
        return True
    if route == '/api/signals/career-scan' and method == 'POST':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'lead_ids'}:
            raise ValueError('Erwartet: {lead_ids}.')
        h._send(202, enqueue_scans(conn, body['lead_ids'], db_path))
        return True
    m = re.fullmatch(r'/api/signals/(\d+)(/promote)?', route)
    if m:
        if method == 'PATCH' and not m.group(2):
            h._send(200, update_signal(conn, int(m.group(1)), h._body()))
            return True
        if method == 'POST' and m.group(2):
            h._send(200, promote_to_lead(conn, int(m.group(1))))
            return True
    m = re.fullmatch(r'/api/leads/(\d+)/correlation', route)
    if m:
        lid = int(m.group(1))
        if method == 'POST':
            h._send(200, correlate(conn, lid))
            return True
        if method == 'GET':
            rows = [dict(r) for r in conn.execute('SELECT * FROM signal_correlations WHERE lead_id=? ORDER BY score DESC', (lid,))]
            for r in rows:
                for k in ('signal_ids', 'counter', 'contradictions', 'missing', 'questions', 'offers'):
                    r[k] = json.loads(r.pop(k + '_json'))
                r['label'] = THEMES.get(r['theme'], {}).get('label', r['theme'])
            h._send(200, {'hypotheses': rows, 'signals': list_signals(conn, {'lead_id': lid})})
            return True
    return False
