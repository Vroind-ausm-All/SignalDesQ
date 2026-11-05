"""Lead-Finder (v1.1): neue Unternehmen aus offen lizenzierten Quellen finden.

Leitplanken
- Nur Quellen mit offener Lizenz und offizieller/geduldeter Schnittstelle werden automatisch
  abgefragt (Wikidata CC0, OpenStreetMap ODbL, GLEIF CC0, TED-Ausschreibungen).
  Register, Branchenbücher und soziale Netzwerke werden nicht automatisiert ausgelesen,
  sondern nur als manuell zu öffnende Links angeboten.
- Datensparsam: gespeichert werden ausschließlich Unternehmensdaten (Name, Website,
  Anschrift, Branche, Größe, Registerangabe). Keine Personennamen, keine E-Mail-Adressen,
  keine Telefonnummern. Einträge ohne Rechtsformzusatz (z. B. Einzelunternehmen, deren
  Name eine natürliche Person ist) werden standardmäßig ausgefiltert.
- Höfliche Nutzung: identifizierender User-Agent, Ergebnis-Cache (24 h), Mindestabstand
  und Tageslimit je Quelle.
- Ein gefundener Treffer ist keine Kontakterlaubnis. Übernommene Leads starten mit
  Rechtsstatus „unbekannt“.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

TIMEOUT = 30
CACHE_HOURS = 24
MIN_SECONDS_BETWEEN_RUNS = 10
DAILY_LIMIT_PER_SOURCE = 40
MAX_RESULTS = 200

LEGAL_FORM_RE = re.compile(
    r'\b(GmbH|gGmbH|AG|SE|KGaA|KG|OHG|oHG|UG|PartG|PartG mbB|eG|e\.\s?V\.|mbH|GbR|Ltd\.?|Limited|S\.?A\.?|B\.?V\.?|Inc\.?|LLC|S\.?à\s?r\.?l\.?)\b'
    r'|haftungsbeschränkt|Holding|Gruppe|Group', re.IGNORECASE)
PLACE_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9 .\-/()]{2,80}$")
KEYWORD_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9 &.\-]{0,60}$")

SOURCES = {
    'wikidata': {
        'title': 'Wikidata – Unternehmen nach Ort & Branche', 'license': 'CC0 1.0', 'ampel': 'gruen',
        'attribution': 'Daten: Wikidata (CC0)', 'url': 'https://query.wikidata.org/',
        'good_for': 'Bekanntere Mittelständler und Konzerne mit Website, Branche und Mitarbeiterzahl.',
        'limits': 'Kleine Firmen fehlen oft; Angaben teils veraltet – vor Nutzung auf der Firmenwebsite prüfen.',
    },
    'osm': {
        'title': 'OpenStreetMap – Firmen & Büros mit Website im Ort', 'license': 'ODbL 1.0', 'ampel': 'gruen',
        'attribution': '© OpenStreetMap-Mitwirkende (ODbL)', 'url': 'https://overpass-api.de/',
        'good_for': 'Lokale Firmen, Büros, Handwerk und Kanzleien in einer Stadt – gut für regionale Akquise.',
        'limits': 'Vollständigkeit schwankt je Region. Bei Weitergabe der Datenbank gilt ODbL (Namensnennung, Share-Alike).',
    },
    'gleif': {
        'title': 'GLEIF – amtlich geprüfte Firmendaten (LEI)', 'license': 'CC0 1.0', 'ampel': 'gruen',
        'attribution': 'Daten: GLEIF (CC0)', 'url': 'https://api.gleif.org/',
        'good_for': 'Exakter Firmenname, Rechtsform, Anschrift und Handelsregisternummer – ideal zum Verifizieren und für Rechnungsadressen.',
        'limits': 'Nur Firmen mit LEI (typisch: Firmen mit Bank-/Wertpapiergeschäft); keine Website, keine Branche.',
    },
    'ted': {
        'title': 'TED – öffentliche Ausschreibungen (Web, Design, Software)', 'license': 'CC BY 4.0 / Metadaten CC0', 'ampel': 'gruen',
        'attribution': 'Quelle: TED – Tenders Electronic Daily, © Europäische Union', 'url': 'https://ted.europa.eu/',
        'good_for': 'Konkrete, ausgeschriebene Aufträge öffentlicher Auftraggeber – kein Werbekontakt nötig, man bewirbt sich.',
        'limits': 'Nur EU-weite (oberschwellige) Verfahren. Unterschwellige Vergaben stehen auf oeffentlichevergabe.de bzw. Landesportalen.',
    },
}

CPV_PRESETS = {
    'web': ('Websites & Webentwicklung', ['72413000', '72212224', '72415000']),
    'design': ('Grafik- & Kommunikationsdesign', ['79822500', '79415200', '79342000']),
    'software': ('Software & Apps', ['72262000', '72212000', '48000000']),
    'marketing': ('Marketing & Werbung', ['79341000', '79342000', '79340000']),
}
OSM_CATEGORIES = {
    'alle_buero': ('Alle Büros / Firmen', [('office', None)]),
    'firmen': ('Unternehmen (office=company)', [('office', 'company')]),
    'it': ('IT & Software', [('office', 'it'), ('office', 'telecommunication')]),
    'ingenieur': ('Ingenieur- & Architekturbüros', [('office', 'engineer'), ('office', 'architect')]),
    'beratung': ('Beratung, Steuer, Recht', [('office', 'consulting'), ('office', 'tax_advisor'), ('office', 'lawyer'), ('office', 'accountant')]),
    'handwerk': ('Handwerk & Produktion', [('craft', None), ('industrial', None)]),
    'immobilien': ('Immobilien & Versicherungen', [('office', 'estate_agent'), ('office', 'insurance'), ('office', 'property_management')]),
}

# Nicht automatisieren – nur manuell nutzen (Begründung in docs/LEADQUELLEN_V11.md)
MANUAL_SOURCES = [
    {'name': 'Handelsregister', 'ampel': 'gelb', 'why': 'Einsicht für jeden frei, aber laut Nutzungsordnung höchstens 60 Abrufe pro Stunde und keine Massenabfragen. Gut zum Prüfen einzelner Firmen.',
     'link': 'https://www.handelsregister.de/rp_web/normalesuche/welcome.xhtml'},
    {'name': 'Unternehmensregister / Bundesanzeiger', 'ampel': 'gelb', 'why': 'Jahresabschlüsse liefern Größe und Entwicklung. Nur manuell und einzeln abrufen.',
     'link': 'https://www.unternehmensregister.de/'},
    {'name': 'Bekanntmachungsservice (unterschwellige Vergaben)', 'ampel': 'gruen', 'why': 'Offizielle Suche des Bundes über alle Vergaben, frei zugänglich. Eine offene Lese-API ist bislang nicht dokumentiert – daher manuell.',
     'link': 'https://www.oeffentlichevergabe.de/'},
    {'name': 'Jobbörse der Bundesagentur für Arbeit', 'ampel': 'gelb', 'why': 'Stellenanzeigen sind starke Signale (neue Marketing-/IT-Stelle). Die oft genutzte API ist inoffiziell – nur manuell suchen, Signal mit Quelle im Lead erfassen.',
     'link_template': 'https://www.arbeitsagentur.de/jobsuche/suche?was={keyword}&wo={place}'},
    {'name': 'North Data, Echobot, Implisense u. a.', 'ampel': 'gruen', 'why': 'Lizenzierte Anbieter: legal automatisierbar mit Vertrag/API-Key (kostenpflichtig). Für Skalierung die sauberste Option.',
     'link': 'https://www.northdata.de/'},
    {'name': 'OpenCorporates', 'ampel': 'gelb', 'why': 'API nur mit Key; kostenfrei nur für Open-Data-Projekte, sonst Lizenz. Share-Alike-Pflicht beachten.',
     'link': 'https://opencorporates.com/'},
    {'name': 'Gelbe Seiten, Das Örtliche, 11880', 'ampel': 'rot', 'why': 'AGB untersagen das Auslesen; Datenbanken sind durch das Datenbankherstellerrecht (§ 87b UrhG) geschützt. Nur einzeln nachschlagen.',
     'link': 'https://www.gelbeseiten.de/'},
    {'name': 'LinkedIn / XING', 'ampel': 'rot', 'why': 'Automatisiertes Auslesen verstößt gegen die Nutzungsbedingungen; Profile sind personenbezogene Daten. Nur manuell und gezielt.',
     'link_template': 'https://www.google.com/search?q=site%3Alinkedin.com%2Fcompany+{keyword}+{place}'},
    {'name': 'Google Maps', 'ampel': 'rot', 'why': 'Scraping untersagt. Die offizielle Places-API ist kostenpflichtig und erlaubt nur eingeschränkte Speicherung.',
     'link_template': 'https://www.google.com/maps/search/{keyword}+{place}'},
    {'name': 'Messe-Ausstellerverzeichnisse, IHK-Firmenlisten', 'ampel': 'gelb', 'why': 'Sehr gute Zielgruppen-Listen, aber meist AGB-/Datenbankschutz. Manuell auswählen, nicht massenhaft kopieren.',
     'link': None},
]


class SourceError(Exception):
    pass


# ---------------------------------------------------------------- Schema

def init_lead_finder(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS discovery_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL, params_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running',
        result_count INTEGER NOT NULL DEFAULT 0, filtered_count INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS discovery_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
        source TEXT NOT NULL, external_id TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL, website TEXT NOT NULL DEFAULT '', street TEXT NOT NULL DEFAULT '',
        zip TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT 'DE',
        industry TEXT NOT NULL DEFAULT '', employees INTEGER NOT NULL DEFAULT 0, legal_form TEXT NOT NULL DEFAULT '',
        register_id TEXT NOT NULL DEFAULT '', signal_type TEXT NOT NULL DEFAULT 'kein_signal',
        signal_note TEXT NOT NULL DEFAULT '', signal_date TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'neu', duplicate_lead_id INTEGER, lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_discovery_cand_run ON discovery_candidates(run_id);
      CREATE INDEX IF NOT EXISTS idx_discovery_runs_source ON discovery_runs(source, created_at);
    ''')


# ---------------------------------------------------------------- HTTP

def _user_agent(conn):
    contact = ''
    row = conn.execute('SELECT website, email FROM company_settings WHERE id=1').fetchone() if conn else None
    if row:
        contact = row['website'] or row['email'] or ''
    return f'SignalDesk/{__version__} (lokales B2B-Recherchetool{"; " + contact if contact else ""})'


def _http(url, user_agent, data=None, content_type=None, accept='application/json', timeout=None):
    headers = {'User-Agent': user_agent, 'Accept': accept}
    if content_type:
        headers['Content-Type'] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:
            raw = resp.read(8_000_001)
            if len(raw) > 8_000_000:
                raise SourceError('Antwort zu groß – Suche bitte eingrenzen.')
            return json.loads(raw.decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode('utf-8', 'replace')
        if exc.code == 429:
            raise SourceError('Die Quelle meldet zu viele Anfragen (HTTP 429). Bitte später erneut versuchen.') from exc
        raise SourceError(f'Quelle antwortet mit HTTP {exc.code}: {re.sub(r"<[^>]+>", " ", detail)[:300].strip()}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f'Quelle nicht erreichbar ({getattr(exc, "reason", exc)}). Internetverbindung/Firewall prüfen.') from exc
    except json.JSONDecodeError as exc:
        raise SourceError('Quelle lieferte keine gültigen JSON-Daten.') from exc


FETCH = _http  # in Tests ersetzbar
SLEEP = __import__('time').sleep


# ---------------------------------------------------------------- Normalisierung

def normalize_domain(url):
    if not url:
        return ''
    if '://' not in url:
        url = 'https://' + url
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return host[4:] if host.startswith('www.') else host


def normalize_name(name):
    s = (name or '').casefold()
    s = LEGAL_FORM_RE.sub(' ', s)
    s = re.sub(r'&\s*co\.?', ' ', s)
    return re.sub(r'[^a-z0-9äöüß]+', '', s)


def clean_website(url):
    url = (url or '').strip()
    if not url:
        return ''
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or '.' not in parsed.hostname:
        return ''
    return f'{parsed.scheme}://{parsed.hostname}{parsed.path if parsed.path not in ("", "/") else ""}'[:300]


def legal_form_of(name):
    match = LEGAL_FORM_RE.search(name or '')
    return match.group(0) if match else ''


def _place(value, key='Ort'):
    value = (value or '').strip()
    if not PLACE_RE.fullmatch(value):
        raise ValueError(f'{key}: 2–80 Zeichen, nur Buchstaben, Ziffern, Leerzeichen und - . / ( ).')
    return value


def _keyword(value):
    value = (value or '').strip()
    if not KEYWORD_RE.fullmatch(value):
        raise ValueError('Stichwort: höchstens 60 Zeichen, keine Sonderzeichen.')
    return value


def _limit(value, default=100):
    value = default if value in (None, '') else value
    if isinstance(value, bool) or type(value) is not int or not 1 <= value <= MAX_RESULTS:
        raise ValueError(f'Anzahl: 1–{MAX_RESULTS}.')
    return value


# ---------------------------------------------------------------- Quellen

def wikidata_query(city, keyword='', min_employees=0, limit=100):
    """Leichte Abfrage (v1.10): keine transitive Klassensuche mehr (führte zu Zeitüberschreitung/HTTP 502).
    Personen werden ausgeschlossen, Branchen-Stichwort wird lokal gefiltert."""
    employees = f'FILTER(BOUND(?employees) && ?employees >= {int(min_employees)})' if min_employees else ''
    city = city.replace('"', '')
    return f'''SELECT ?company ?companyLabel ?website ?employees ?industryLabel ?hqLabel ?lei WHERE {{
  {{ SELECT ?hq WHERE {{ ?hq rdfs:label "{city}"@de ; wdt:P17 wd:Q183 ; wdt:P625 [] . }} LIMIT 3 }}
  ?company wdt:P159 ?hq .
  FILTER NOT EXISTS {{ ?company wdt:P31 wd:Q5 }}
  FILTER NOT EXISTS {{ ?company wdt:P576 ?dissolved }}
  OPTIONAL {{ ?company wdt:P856 ?website }}
  OPTIONAL {{ ?company wdt:P1128 ?employees }}
  OPTIONAL {{ ?company wdt:P452 ?industry }}
  OPTIONAL {{ ?company wdt:P1278 ?lei }}
  {employees}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
}} LIMIT {int(limit) * 4}'''


def wikidata_sparql(query, ua, retries=1):
    """SPARQL-Abfrage mit einem Wiederholversuch bei Überlastung (HTTP 502/503/504)."""
    url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode({'query': query, 'format': 'json'})
    for attempt in range(retries + 1):
        try:
            return FETCH(url, ua, accept='application/sparql-results+json')
        except SourceError as exc:
            if attempt >= retries or not re.search(r'HTTP 50[234]|nicht erreichbar|timed out', str(exc)):
                if re.search(r'HTTP 50[234]', str(exc)):
                    raise SourceError('Wikidata ist gerade überlastet (HTTP 502/503/504). Bitte in einigen Minuten erneut versuchen.') from exc
                raise
            SLEEP(3)


def search_wikidata(params, ua):
    city = _place(params.get('place'))
    keyword = _keyword(params.get('keyword'))
    min_emp = params.get('min_employees') or 0
    if isinstance(min_emp, bool) or type(min_emp) is not int or not 0 <= min_emp <= 1_000_000:
        raise ValueError('Mindestgröße: ganze Zahl ≥ 0.')
    limit = _limit(params.get('limit'))
    query = wikidata_query(city, keyword, min_emp, limit)
    data = wikidata_sparql(query, ua)
    merged = {}
    for b in data.get('results', {}).get('bindings', []):
        qid = b.get('company', {}).get('value', '').rsplit('/', 1)[-1]
        if not qid:
            continue
        item = merged.setdefault(qid, {
            'external_id': qid, 'name': b.get('companyLabel', {}).get('value', ''), 'website': '',
            'city': b.get('hqLabel', {}).get('value', city), 'industry': '', 'employees': 0, 'lei': b.get('lei', {}).get('value', ''),
            'source_url': f'https://www.wikidata.org/wiki/{qid}'})
        if not item['website'] and b.get('website'):
            item['website'] = clean_website(b['website']['value'])
        if b.get('employees'):
            try:
                item['employees'] = max(item['employees'], int(float(b['employees']['value'])))
            except ValueError:
                pass
        label = b.get('industryLabel', {}).get('value', '')
        if label and label not in item['industry'] and not re.fullmatch(r'Q\d+', label):
            item['industry'] = (item['industry'] + ', ' + label).strip(', ')[:200]
    items = [i for i in merged.values() if i['name'] and not re.fullmatch(r'Q\d+', i['name'])]
    if keyword:
        kw = keyword.casefold()
        items = [i for i in items if kw in (i['industry'] + ' ' + i['name']).casefold()]
    return items[:limit]


def overpass_query(city, category, limit):
    selectors = OSM_CATEGORIES[category][1]
    parts = []
    for key, value in selectors:
        sel = f'["{key}"="{value}"]' if value else f'["{key}"]'
        parts.append(f'nwr{sel}["name"]["website"](area.a);')
        parts.append(f'nwr{sel}["name"]["contact:website"](area.a);')
    return (f'[out:json][timeout:60];\narea["boundary"="administrative"]["name"="{city}"]["admin_level"~"^(4|5|6|7|8)$"]->.a;\n'
            f'(\n  {chr(10).join(parts)}\n);\nout center tags {int(limit) * 3};')


OVERPASS_SERVERS = ('https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter',
                    'https://overpass.kumi.systems/api/interpreter')


def overpass(query, ua):
    """Overpass-Abfrage mit Ausweichservern (v1.10) – der Hauptserver ist häufig überlastet."""
    errors = []
    for server in OVERPASS_SERVERS:
        try:
            return FETCH(server, ua, data=urllib.parse.urlencode({'data': query}).encode(),
                         content_type='application/x-www-form-urlencoded', timeout=90)
        except SourceError as exc:
            errors.append(f"{urllib.parse.urlsplit(server).hostname}: {exc}")
    raise SourceError('Alle OpenStreetMap-Server überlastet oder nicht erreichbar – bitte später erneut versuchen. (' + ' | '.join(errors)[:400] + ')')


def search_osm(params, ua):
    city = _place(params.get('place'))
    category = params.get('category') or 'alle_buero'
    if category not in OSM_CATEGORIES:
        raise ValueError('Unbekannte Kategorie.')
    limit = _limit(params.get('limit'))
    query = overpass_query(city, category, limit)
    data = overpass(query, ua)
    items = []
    for el in data.get('elements', []):
        tags = el.get('tags', {})
        name = tags.get('name', '').strip()
        if not name:
            continue
        kind = tags.get('office') or tags.get('craft') or tags.get('industrial') or ''
        items.append({
            'external_id': f"{el.get('type', 'node')}/{el.get('id', '')}", 'name': name[:200],
            'website': clean_website(tags.get('website') or tags.get('contact:website')),
            'street': ' '.join(x for x in (tags.get('addr:street', ''), tags.get('addr:housenumber', '')) if x)[:200],
            'zip': tags.get('addr:postcode', '')[:10], 'city': (tags.get('addr:city') or city)[:120],
            'industry': kind.replace('_', ' ')[:200],
            'source_url': f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id', '')}"})
    return items[:limit * 3]


GLEIF_URL = 'https://api.gleif.org/api/v1/lei-records?'


def gleif_page(ua, city='', postcode='', keyword='', page=1, size=200, attempt_from=0):
    """Eine Seite GLEIF-Datensätze. Lehnt die API eine Filterkombination ab (HTTP 400 „Filter should contain only
    allowed values“), wird mit weniger Filtern erneut gefragt; der Rest wird lokal gefiltert."""
    base = {'page[size]': size, 'page[number]': page}
    place = {'filter[entity.legalAddress.postalCode]': postcode} if postcode else {'filter[entity.legalAddress.city]': city}
    attempts = [
        {**place, 'filter[entity.legalAddress.country]': 'DE', 'filter[entity.status]': 'ACTIVE'},
        {**place, 'filter[entity.legalAddress.country]': 'DE'},
        dict(place),
        {'filter[fulltext]': (postcode or city)},
    ]
    last = None
    for idx, filters in enumerate(attempts):
        if idx < attempt_from:
            continue
        q = {**filters, **base}
        if keyword:
            q['filter[fulltext]'] = (q.get('filter[fulltext]', '') + ' ' + keyword).strip()
        try:
            data = FETCH(GLEIF_URL + urllib.parse.urlencode(q), ua, accept='application/vnd.api+json')
            data['_filters'] = sorted(filters)
            data['_attempt'] = idx
            return data
        except SourceError as exc:
            last = exc
            if 'HTTP 400' not in str(exc):
                raise
    raise last


def gleif_items(data, city='', postcode=''):
    items = []
    for rec in data.get('data', []):
        attr = rec.get('attributes', {})
        entity = attr.get('entity', {})
        if (entity.get('status') or 'ACTIVE') != 'ACTIVE':
            continue
        if entity.get('category') not in (None, '', 'GENERAL', 'BRANCH'):
            continue  # Fonds, Einzelpersonen etc. auslassen
        addr = entity.get('legalAddress', {}) or {}
        if (addr.get('country') or 'DE') != 'DE':
            continue
        if postcode and (addr.get('postalCode') or '') != postcode:
            continue
        if city and not postcode and (addr.get('city') or '').casefold() != city.casefold():
            continue
        name = (entity.get('legalName') or {}).get('name', '')
        lei = attr.get('lei') or rec.get('id', '')
        register = entity.get('registeredAs') or ''
        ra = (entity.get('registeredAt') or {}).get('id', '')
        items.append({
            'external_id': lei, 'lei': lei, 'name': name[:200], 'street': ' '.join(addr.get('addressLines') or [])[:200],
            'zip': (addr.get('postalCode') or '')[:10], 'city': (addr.get('city') or city)[:120],
            'country': (addr.get('country') or 'DE')[:2], 'register_id': register[:60], 'register_authority': ra,
            'legal_form': legal_form_of(name),
            'signal_note': f"Initiale LEI-Registrierung {(attr.get('registration') or {}).get('initialRegistrationDate', '')[:10]}".strip(),
            'source_url': f'https://search.gleif.org/#/record/{lei}'})
    return items


def search_gleif(params, ua):
    city = _place(params.get('place'))
    keyword = _keyword(params.get('keyword'))
    limit = _limit(params.get('limit'))
    data = gleif_page(ua, city=city, keyword=keyword, size=min(limit, 200))
    return gleif_items(data, city=city)


def ted_query(cpvs, since):
    return f"classification-cpv IN ({' '.join(cpvs)}) AND place-of-performance IN (DEU) AND publication-date>={since.replace('-', '')}"


def search_ted(params, ua):
    preset = params.get('preset') or 'web'
    if preset not in CPV_PRESETS:
        raise ValueError('Unbekannte Leistungsgruppe.')
    days = params.get('days') or 30
    if isinstance(days, bool) or type(days) is not int or not 1 <= days <= 180:
        raise ValueError('Zeitraum: 1–180 Tage.')
    limit = _limit(params.get('limit'), 50)
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    body = {'query': ted_query(CPV_PRESETS[preset][1], since),
            'fields': ['publication-number', 'notice-title', 'buyer-name', 'publication-date', 'deadline-receipt-tender-date-lot'],
            'page': 1, 'limit': min(limit, 100), 'scope': 'ACTIVE', 'paginationMode': 'PAGE_NUMBER'}
    data = FETCH('https://api.ted.europa.eu/v3/notices/search', ua, data=json.dumps(body).encode(), content_type='application/json')
    items = []
    for n in data.get('notices', []):
        pub = str(n.get('publication-number', ''))
        title = _lang(n.get('notice-title'))
        buyer = _lang(n.get('buyer-name'))
        deadline = _first(n.get('deadline-receipt-tender-date-lot'))[:10]
        published = _first(n.get('publication-date'))[:10]
        if not buyer:
            continue
        items.append({
            'external_id': pub, 'name': buyer[:200], 'industry': 'Öffentlicher Auftraggeber',
            'signal_type': 'digitalprojekt', 'signal_date': published if re.fullmatch(r'\d{4}-\d{2}-\d{2}', published) else '',
            'signal_note': f"Ausschreibung {pub}: {title}"[:900] + (f" · Angebotsfrist {deadline}" if deadline else ''),
            'source_url': _ted_link(n, pub), 'legal_form': 'öffentlich'})
    return items


def _lang(value):
    """TED liefert mehrsprachige Felder als {'deu': '…'} oder {'deu': ['…']}."""
    if isinstance(value, dict):
        for key in ('deu', 'DEU', 'de', 'eng', 'ENG', 'en'):
            if key in value:
                return _first(value[key])
        return _first(next(iter(value.values()), ''))
    return _first(value)


def _first(value):
    if isinstance(value, list):
        return str(value[0]) if value else ''
    return str(value or '')


def _ted_link(notice, pub):
    links = notice.get('links') or {}
    html = links.get('html') or {}
    if isinstance(html, dict):
        for key in ('DEU', 'deu', 'ENG', 'eng'):
            if html.get(key):
                return html[key]
    return f'https://ted.europa.eu/de/notice/-/detail/{urllib.parse.quote(pub)}' if pub else 'https://ted.europa.eu/'


SEARCHERS = {'wikidata': search_wikidata, 'osm': search_osm, 'gleif': search_gleif, 'ted': search_ted}


# ---------------------------------------------------------------- Ablauf

def _known_leads(conn):
    names, domains = {}, {}
    for r in conn.execute('SELECT id, company, website FROM leads'):
        if r['company']:
            names.setdefault(normalize_name(r['company']), r['id'])
        if r['website']:
            domains.setdefault(normalize_domain(r['website']), r['id'])
    return names, domains


def run_search(conn, data):
    if not isinstance(data, dict) or set(data) - {'source', 'place', 'keyword', 'category', 'min_employees', 'limit',
                                                  'preset', 'days', 'legal_entities_only', 'force'}:
        raise ValueError('Ungültige Suchparameter.')
    source = data.get('source')
    if source not in SEARCHERS:
        raise ValueError('Unbekannte Quelle.')
    only_legal = data.get('legal_entities_only', True)
    if not isinstance(only_legal, bool):
        raise ValueError('legal_entities_only: true/false.')
    params = {k: v for k, v in data.items() if k not in ('source', 'force')}
    params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
    if not data.get('force'):
        cached = conn.execute(f"""SELECT id FROM discovery_runs WHERE source=? AND params_json=? AND status='done'
                                  AND created_at >= datetime('now', '-{CACHE_HOURS} hours') ORDER BY id DESC LIMIT 1""",
                              (source, params_json)).fetchone()
        if cached:
            result = run_detail(conn, cached['id'])
            result['cached'] = True
            return result
    last = conn.execute("SELECT created_at FROM discovery_runs WHERE source=? ORDER BY id DESC LIMIT 1", (source,)).fetchone()
    if last and conn.execute("SELECT (julianday('now') - julianday(?)) * 86400 < ?", (last['created_at'], MIN_SECONDS_BETWEEN_RUNS)).fetchone()[0]:
        raise ValueError(f'Bitte {MIN_SECONDS_BETWEEN_RUNS} Sekunden zwischen zwei Abfragen derselben Quelle warten (Fair Use).')
    today_runs = conn.execute("SELECT COUNT(*) FROM discovery_runs WHERE source=? AND created_at >= date('now')", (source,)).fetchone()[0]
    if today_runs >= DAILY_LIMIT_PER_SOURCE:
        raise ValueError(f'Tageslimit von {DAILY_LIMIT_PER_SOURCE} Abfragen für diese Quelle erreicht (Fair Use).')
    cur = conn.execute('INSERT INTO discovery_runs(source, params_json) VALUES (?,?)', (source, params_json))
    run_id = cur.lastrowid
    conn.commit()
    try:
        items = SEARCHERS[source](params, _user_agent(conn))
    except ValueError:
        conn.execute('DELETE FROM discovery_runs WHERE id=?', (run_id,))
        conn.commit()
        raise
    except SourceError as exc:
        conn.execute("UPDATE discovery_runs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?", (str(exc), run_id))
        conn.commit()
        raise
    names, domains = _known_leads(conn)
    seen, stored, filtered = set(), 0, 0
    license_text = SOURCES[source]['license']
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        legal = item.get('legal_form') or legal_form_of(name)
        if only_legal and source in ('osm', 'wikidata') and not legal:
            filtered += 1  # mögliche natürliche Person / Einzelunternehmen – datensparsam auslassen
            continue
        key = normalize_domain(item.get('website')) or normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        dup = domains.get(normalize_domain(item.get('website'))) if item.get('website') else None
        dup = dup or names.get(normalize_name(name))
        from .company_data import check_suppressed
        blocked = bool(check_suppressed(conn, website=item.get('website', ''), name=name))
        cols = {'run_id': run_id, 'source': source, 'external_id': str(item.get('external_id', ''))[:120], 'name': name[:200],
                'website': item.get('website', ''), 'street': item.get('street', ''), 'zip': item.get('zip', ''),
                'city': item.get('city', ''), 'country': item.get('country', 'DE'), 'industry': item.get('industry', ''),
                'employees': int(item.get('employees') or 0), 'legal_form': legal, 'register_id': item.get('register_id', ''),
                'signal_type': item.get('signal_type', 'kein_signal'), 'signal_note': item.get('signal_note', ''),
                'signal_date': item.get('signal_date', ''), 'source_url': item.get('source_url', ''), 'license': license_text,
                'status': 'gesperrt' if blocked else ('dublette' if dup else 'neu'), 'duplicate_lead_id': dup}
        conn.execute(f"INSERT INTO discovery_candidates ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(cols.values()))
        stored += 1
        if stored >= _limit(params.get('limit'), 50 if source == 'ted' else 100):
            break
    conn.execute("UPDATE discovery_runs SET status='done', result_count=?, filtered_count=?, finished_at=datetime('now') WHERE id=?",
                 (stored, filtered, run_id))
    conn.commit()
    result = run_detail(conn, run_id)
    result['cached'] = False
    return result


def run_detail(conn, run_id):
    run = conn.execute('SELECT * FROM discovery_runs WHERE id=?', (run_id,)).fetchone()
    if not run:
        raise LookupError('Suchlauf nicht gefunden.')
    out = dict(run)
    out['params'] = json.loads(out.pop('params_json'))
    out['source_info'] = SOURCES.get(run['source'], {})
    out['candidates'] = [dict(r) for r in conn.execute('SELECT * FROM discovery_candidates WHERE run_id=? ORDER BY status=\'dublette\', employees DESC, name', (run_id,))]
    return out


def run_rows(conn):
    return [dict(r) for r in conn.execute('''SELECT r.id, r.source, r.params_json, r.status, r.result_count, r.filtered_count, r.error, r.created_at,
        (SELECT COUNT(*) FROM discovery_candidates c WHERE c.run_id=r.id AND c.status='neu') AS open_count
        FROM discovery_runs r ORDER BY r.id DESC LIMIT 50''')]


def _map_industry(candidate):
    text = (candidate['industry'] + ' ' + candidate['name']).lower()
    if any(w in text for w in ('software', 'saas', 'it ', ' it', 'informations', 'telecommunication', 'digital')):
        return 'B2B-SaaS'
    if any(w in text for w in ('maschinen', 'industrie', 'engineer', 'ingenieur', 'technik', 'automat', 'produktion', 'manufactur', 'craft', 'industrial', 'anlagen')):
        return 'Industrie & B2B-Technik'
    if any(w in text for w in ('beratung', 'consult', 'lawyer', 'tax', 'steuer', 'recht', 'accountant', 'architect', 'architekt', 'insurance', 'versicher')):
        return 'Professionelle Dienstleistungen'
    return 'Sonstige'


def review_candidate(conn, candidate_id, decision):
    cand = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (candidate_id,)).fetchone()
    if not cand:
        raise LookupError('Treffer nicht gefunden.')
    if decision not in ('uebernehmen', 'verwerfen'):
        raise ValueError('Entscheidung: uebernehmen oder verwerfen.')
    if cand['status'] not in ('neu', 'dublette'):
        raise ValueError('Treffer wurde bereits bearbeitet.')
    if decision == 'verwerfen':
        conn.execute("UPDATE discovery_candidates SET status='verworfen' WHERE id=?", (candidate_id,))
        conn.commit()
        return {'status': 'verworfen'}
    if cand['status'] == 'gesperrt':
        raise ValueError('Firma steht auf der Sperrliste – keine Übernahme.')
    from .company_data import assert_not_suppressed
    assert_not_suppressed(conn, website=cand['website'], name=cand['name'])
    if cand['status'] == 'dublette' or cand['duplicate_lead_id']:
        raise ValueError('Firma ist bereits als Lead vorhanden – dort ergänzen statt doppelt anlegen.')
    names, domains = _known_leads(conn)
    dup = (domains.get(normalize_domain(cand['website'])) if cand['website'] else None) or names.get(normalize_name(cand['name']))
    if dup:
        conn.execute("UPDATE discovery_candidates SET status='dublette', duplicate_lead_id=? WHERE id=?", (dup, candidate_id))
        conn.commit()
        raise ValueError('Firma ist inzwischen als Lead vorhanden.')
    source = SOURCES[cand['source']]
    address = ', '.join(x for x in (cand['street'], ' '.join(y for y in (cand['zip'], cand['city']) if y)) if x)
    note_parts = [f"Gefunden über {source['title']} ({source['attribution']}).",
                  f"Anschrift: {address}" if address else '', f"Register: {cand['register_id']}" if cand['register_id'] else '',
                  f"Branche laut Quelle: {cand['industry']}" if cand['industry'] else '',
                  'Kein Kontakt ohne geprüfte Rechtsgrundlage – Fund ist keine Einwilligung.']
    lead = {
        'company': cand['name'][:200], 'website': cand['website'], 'location': ' '.join(y for y in (cand['zip'], cand['city']) if y)[:160],
        'industry': _map_industry(cand), 'employees': cand['employees'] or 0, 'signal_type': cand['signal_type'],
        'signal_date': cand['signal_date'], 'signal_source': cand['source_url'] if cand['source_url'].startswith('http') else '',
        'signal_note': cand['signal_note'][:2000], 'offer': 'conversion' if cand['source'] != 'ted' else 'pilot',
        'stage': 'recherche', 'permission': 'unbekannt', 'contact_route': 'ausschreibung' if cand['source'] == 'ted' else 'unbekannt',
        'note': ' '.join(p for p in note_parts if p)[:4000],
        'next_step': 'Vergabeunterlagen prüfen und Teilnahme entscheiden' if cand['source'] == 'ted' else 'Website prüfen (URL-Recherche) und Anlass/Signal belegen',
        'next_date': (dt.date.today() + dt.timedelta(days=2)).isoformat(),
    }
    cols = ','.join(lead)
    cur = conn.execute(f'INSERT INTO leads ({cols}) VALUES ({",".join("?" for _ in lead)})', tuple(lead.values()))
    conn.execute("UPDATE discovery_candidates SET status='uebernommen', lead_id=? WHERE id=?", (cur.lastrowid, candidate_id))
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (cur.lastrowid, 'notiz', f"Aus Lead-Finder übernommen: {source['title']} · {cand['source_url']}"))
    conn.commit()
    return {'status': 'uebernommen', 'lead_id': cur.lastrowid}


def manual_links(place='', keyword=''):
    q = {'place': urllib.parse.quote_plus(place or ''), 'keyword': urllib.parse.quote_plus(keyword or '')}
    out = []
    for src in MANUAL_SOURCES:
        link = src.get('link')
        if src.get('link_template'):
            link = src['link_template'].format(**q)
        out.append({'name': src['name'], 'ampel': src['ampel'], 'why': src['why'], 'link': link})
    return out


def catalog():
    return {'sources': SOURCES, 'cpv_presets': {k: {'label': v[0], 'codes': v[1]} for k, v in CPV_PRESETS.items()},
            'osm_categories': {k: v[0] for k, v in OSM_CATEGORIES.items()}, 'manual_sources': manual_links(),
            'limits': {'cache_hours': CACHE_HOURS, 'min_seconds': MIN_SECONDS_BETWEEN_RUNS, 'daily_per_source': DAILY_LIMIT_PER_SOURCE},
            'live_verified': False}


# ---------------------------------------------------------------- HTTP-Routen

def route_lead_finder(h, conn, method, route, query):
    if not route.startswith('/api/lead-finder'):
        return False
    import re as _re
    if route == '/api/lead-finder/catalog' and method == 'GET':
        h._send(200, catalog())
        return True
    if route == '/api/lead-finder/manual-links' and method == 'GET':
        place = query.get('place', [''])[0][:80]
        keyword = query.get('keyword', [''])[0][:60]
        h._send(200, manual_links(place, keyword))
        return True
    if route == '/api/lead-finder/search' and method == 'POST':
        try:
            h._send(201, run_search(conn, h._body()))
        except SourceError as exc:
            h._error(str(exc), 502)
        return True
    if route == '/api/lead-finder/runs' and method == 'GET':
        h._send(200, run_rows(conn))
        return True
    match = _re.fullmatch(r'/api/lead-finder/runs/(\d+)', route)
    if match and method == 'GET':
        h._send(200, run_detail(conn, int(match.group(1))))
        return True
    match = _re.fullmatch(r'/api/lead-finder/candidates/(\d+)/review', route)
    if match and method == 'POST':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'decision'}:
            raise ValueError('Erwartet: {decision}.')
        h._send(200, review_candidate(conn, int(match.group(1)), body['decision']))
        return True
    return False
