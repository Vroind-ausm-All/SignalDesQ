"""Sammelsuche „Arbeitstag starten“ (Sprint B): alle offenen Quellen auf einmal, zusammengeführt, ohne Dubletten.

Ablauf
1. Suchgebiet: Ort oder PLZ + Umkreis → Mittelpunkt und Gemeinden (area.py).
2. Quellen (je Quelle eigener Fehlerstatus, die anderen laufen weiter):
   - GLEIF: amtliche Firmendaten je Gemeinde, seitenweise (höflich: ~1 Anfrage/Sekunde),
   - Wikidata: Unternehmen mit Sitz im Umkreis (eine Umkreisabfrage) + Websites zu GLEIF-Firmen über die LEI,
   - OpenStreetMap: Firmen/Betriebe der gewählten Branchen im Umkreis (Ausweichserver),
   - TED: öffentliche Ausschreibungen (Web, Design, Software, Marketing).
3. Zusammenführen über LEI, Registernummer, Domain und Name+Ort. Bereits bekannte Leads, verworfene Treffer
   und Einträge der Sperrliste erscheinen nicht erneut als neu.
4. Sichtung: Website zum Durchklicken, übernehmen oder verwerfen; Website-Suche mit Nachweis (Registernummer im
   Impressum) für Treffer ohne Website.

Datensparsam: gespeichert werden Unternehmensangaben. Allgemeine Kontaktwege (Telefon, E-Mail) kommen nur aus dem
Impressum einer juristischen Person und gelten als Firmenkontakt – ein Fund ist keine Einwilligung (§ 7 UWG).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import threading
import unicodedata

from . import area as ar
from . import industries as ind
from . import lead_finder as lf
from .company_data import check_suppressed, normalize_domain, normalize_name

SWEEP_SOURCES = {'gleif': 'GLEIF', 'wikidata': 'Wikidata', 'osm': 'OpenStreetMap', 'ted': 'TED-Ausschreibungen'}
MAX_GLEIF_PAGES_PER_PLACE = 25
MAX_GLEIF_REQUESTS = 150
GLEIF_DELAY = 1.1
DAILY_SWEEPS = 20
MAX_IMPORT_BYTES = 60_000_000
_THREADS = {}
_WEB = {'thread': None}
_LOCK = threading.Lock()


def init_sweep(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS sweeps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'suche',
        params_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', progress_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS discovery_keys (
        key TEXT PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES discovery_candidates(id) ON DELETE CASCADE
      );
      CREATE TABLE IF NOT EXISTS discovery_dismissed (
        key TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
    ''')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(discovery_candidates)')}
    for name, decl in (('sweep_id', 'INTEGER'), ('sources_json', "TEXT NOT NULL DEFAULT '[]'"), ('distance_km', 'REAL'),
                       ('industry_key', "TEXT NOT NULL DEFAULT ''"), ('lei', "TEXT NOT NULL DEFAULT ''"),
                       ('website_status', "TEXT NOT NULL DEFAULT ''"), ('website_evidence', "TEXT NOT NULL DEFAULT ''"),
                       ('contact_json', "TEXT NOT NULL DEFAULT '{}'"), ('updated_at', "TEXT NOT NULL DEFAULT ''")):
        if name not in cols:
            conn.execute(f'ALTER TABLE discovery_candidates ADD COLUMN {name} {decl}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_discovery_cand_sweep ON discovery_candidates(sweep_id, status)')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_cand_web ON discovery_candidates(website_status)")


for _key, _title in (('gleif_csv', 'GLEIF-Export (CSV-Import)'), ('liste', 'Eigene Firmenliste (CSV-Import)')):
    lf.SOURCES.setdefault(_key, {'title': _title, 'license': 'CC0 1.0' if _key == 'gleif_csv' else 'eigene Liste', 'ampel': 'gruen',
                                 'attribution': 'Daten: GLEIF (CC0)' if _key == 'gleif_csv' else 'eigene Datei', 'url': '',
                                 'good_for': 'Große Firmenlisten offline einlesen.', 'limits': 'Keine Website/Branche in GLEIF-Daten.'})


def recover_sweeps(conn):
    conn.execute("UPDATE sweeps SET status='abgebrochen', finished_at=datetime('now') WHERE status IN ('queued','running')")
    conn.execute("UPDATE discovery_candidates SET website_status='' WHERE website_status='laeuft'")


# ---------------------------------------------------------------- Schlüssel & Zusammenführen

def _translit(s):
    s = (s or '').casefold().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()


def register_key(register, city):
    num = re.sub(r'\s+', '', (register or '').upper())
    if not re.fullmatch(r'(HRA|HRB|GNR|GSR|PR|VR)\d{1,7}[A-Z]?', num):
        return ''
    return f"reg:{num}:{re.sub(r'[^a-z]', '', _translit(city))}"


def keys_for(item):
    keys = []
    if item.get('lei'):
        keys.append('lei:' + item['lei'].upper())
    rk = register_key(item.get('register_id'), item.get('city'))
    if rk:
        keys.append(rk)
    dom = normalize_domain(item.get('website'))
    if dom:
        keys.append('dom:' + dom)
    nm = normalize_name(item.get('name'))
    if len(nm) >= 3:
        keys.append(f"name:{nm}:{re.sub(r'[^a-z]', '', _translit(item.get('city')))}")
    return keys


class LeadIndex:
    """Einmal aufgebauter Index der bestehenden Leads (Domain, Registernummer+Ort, Name)."""
    def __init__(self, conn):
        self.domains, self.registers, self.names = {}, {}, {}
        for r in conn.execute('SELECT id, company, legal_name, website, register_number, city, location FROM leads'):
            if r['website']:
                self.domains.setdefault(normalize_domain(r['website']), r['id'])
            rk = register_key(r['register_number'], r['city'] or (r['location'] or '').split(' ')[-1])
            if rk:
                self.registers.setdefault(rk, r['id'])
            for n in (r['company'], r['legal_name']):
                nm = normalize_name(n)
                if len(nm) >= 3:
                    self.names.setdefault(nm, r['id'])

    def find(self, item):
        dom = normalize_domain(item.get('website'))
        if dom and dom in self.domains:
            return self.domains[dom]
        rk = register_key(item.get('register_id'), item.get('city'))
        if rk and rk in self.registers:
            return self.registers[rk]
        return self.names.get(normalize_name(item.get('name')))


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def store_items(conn, sweep_id, run_id, source, items, ctx, index=None):
    """Filtert, führt zusammen und speichert Treffer. Gibt Zähler zurück."""
    index = index or LeadIndex(conn)
    c = {'found': len(items), 'new': 0, 'merged': 0, 'known': 0, 'dismissed': 0, 'suppressed': 0, 'filtered': 0}
    license_text = lf.SOURCES.get(source, {}).get('license', '')
    for item in items:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        legal = item.get('legal_form') or lf.legal_form_of(name)
        if source in ('osm', 'wikidata') and not legal and not ctx.get('include_sole'):
            c['filtered'] += 1  # möglicherweise natürliche Person – datensparsam auslassen
            continue
        if ctx.get('operative', True) and source != 'ted' and ind.NON_OPERATIVE_RE.search(name):
            c['filtered'] += 1
            continue
        if source != 'ted':
            ok, ikey = ind.match(f"{name} {item.get('industry', '')}", ctx.get('industries', []), ctx.get('keywords', []))
            if not ok and not item.get('_industry_matched'):
                c['filtered'] += 1
                continue
            item['industry_key'] = ikey or item.get('industry_key') or ind.guess(f"{name} {item.get('industry', '')}")
        dist = item.get('distance_km')
        if dist is None and ctx.get('place_distance'):
            dist = ctx['place_distance'].get((item.get('city') or '').casefold())
        if dist is not None and ctx.get('radius_km') and dist > ctx['radius_km'] + 2:
            c['filtered'] += 1
            continue
        keys = keys_for(item)
        if any(conn.execute('SELECT 1 FROM discovery_dismissed WHERE key=?', (k,)).fetchone() for k in keys):
            c['dismissed'] += 1
            continue
        existing = None
        for k in keys:
            row = conn.execute('SELECT d.* FROM discovery_keys k JOIN discovery_candidates d ON d.id=k.candidate_id WHERE k.key=?', (k,)).fetchone()
            if row:
                existing = row
                break
        src_entry = {'source': source, 'url': item.get('source_url', '')}
        if existing:
            if existing['status'] in ('verworfen',):
                c['dismissed'] += 1
                continue
            if existing['status'] in ('uebernommen', 'dublette', 'gesperrt'):
                c['known'] += 1
                _add_keys(conn, existing['id'], keys)
                continue
            sources = json.loads(existing['sources_json'] or '[]')
            if not any(s['source'] == source for s in sources):
                sources.append(src_entry)
            upd = {'sources_json': json.dumps(sources, ensure_ascii=False), 'updated_at': _now()}
            for f in ('website', 'register_id', 'street', 'zip', 'city', 'legal_form', 'lei', 'industry_key'):
                if not existing[f] and item.get(f):
                    upd[f] = str(item[f])[:300]
            if item.get('website') and not existing['website']:
                upd['website_status'] = 'quelle'
                upd['website_evidence'] = f"Website laut {lf.SOURCES.get(source, {}).get('title', source)}"
            if item.get('employees') and int(item['employees']) > (existing['employees'] or 0):
                upd['employees'] = int(item['employees'])
            if item.get('industry') and item['industry'] not in (existing['industry'] or ''):
                upd['industry'] = ((existing['industry'] or '') + ', ' + item['industry']).strip(', ')[:200]
            if dist is not None and (existing['distance_km'] is None or dist < existing['distance_km']):
                upd['distance_km'] = dist
            conn.execute(f"UPDATE discovery_candidates SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), existing['id']))
            _add_keys(conn, existing['id'], keys)
            c['merged'] += 1
            continue
        dup = index.find(item)
        blocked = bool(check_suppressed(conn, website=item.get('website', ''), name=name))
        status = 'gesperrt' if blocked else ('dublette' if dup else 'neu')
        cols = {'run_id': run_id, 'sweep_id': sweep_id, 'source': source, 'external_id': str(item.get('external_id', ''))[:120],
                'name': name[:200], 'website': item.get('website', ''), 'street': item.get('street', ''), 'zip': item.get('zip', ''),
                'city': item.get('city', ''), 'country': item.get('country', 'DE'), 'industry': item.get('industry', '')[:200],
                'employees': int(item.get('employees') or 0), 'legal_form': legal, 'register_id': item.get('register_id', ''),
                'signal_type': item.get('signal_type', 'kein_signal'), 'signal_note': item.get('signal_note', ''),
                'signal_date': item.get('signal_date', ''), 'source_url': item.get('source_url', ''), 'license': license_text,
                'status': status, 'duplicate_lead_id': dup, 'sources_json': json.dumps([src_entry], ensure_ascii=False),
                'distance_km': dist, 'industry_key': item.get('industry_key', ''), 'lei': item.get('lei', ''),
                'website_status': 'quelle' if item.get('website') else '',
                'website_evidence': f"Website laut {lf.SOURCES.get(source, {}).get('title', source)}" if item.get('website') else '',
                'updated_at': _now()}
        cur = conn.execute(f"INSERT INTO discovery_candidates ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(cols.values()))
        _add_keys(conn, cur.lastrowid, keys)
        c['new' if status == 'neu' else ('suppressed' if blocked else 'known')] += 1
    conn.commit()
    return c


def _add_keys(conn, cid, keys):
    for k in keys:
        conn.execute('INSERT OR IGNORE INTO discovery_keys(key, candidate_id) VALUES (?,?)', (k, cid))


# ---------------------------------------------------------------- Sammelsuche

def validate_params(data):
    allowed = {'place', 'radius_km', 'industries', 'keywords', 'sources', 'operative', 'include_sole', 'ted_presets'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Ungültige Suchparameter.')
    place = str(data.get('place') or '').strip()
    ar.parse_place(place)
    radius = data.get('radius_km', 30)
    if radius not in ar.RADII:
        raise ValueError('Umkreis: ' + ', '.join(map(str, ar.RADII)) + ' km.')
    sources = data.get('sources', list(SWEEP_SOURCES))
    if not isinstance(sources, list) or not sources or any(s not in SWEEP_SOURCES for s in sources):
        raise ValueError('Mindestens eine Quelle wählen.')
    presets = data.get('ted_presets', ['web', 'design', 'software', 'marketing'])
    if not isinstance(presets, list) or any(p not in lf.CPV_PRESETS for p in presets):
        raise ValueError('Unbekannte Ausschreibungsgruppe.')
    for flag in ('operative', 'include_sole'):
        if flag in data and not isinstance(data[flag], bool):
            raise ValueError(f'{flag}: true/false.')
    return {'place': place, 'radius_km': radius, 'industries': ind.validate_keys(data.get('industries', [])),
            'keywords': ind.parse_keywords(data.get('keywords', '')), 'sources': sources, 'operative': data.get('operative', True),
            'include_sole': data.get('include_sole', False), 'ted_presets': presets}


def start_sweep(conn, data, db_path, start=True):
    p = validate_params(data)
    today_count = conn.execute("SELECT COUNT(*) FROM sweeps WHERE kind='suche' AND created_at >= date('now')").fetchone()[0]
    if today_count >= DAILY_SWEEPS:
        raise ValueError(f'Höchstens {DAILY_SWEEPS} Sammelsuchen pro Tag (Fair Use der offenen Quellen).')
    if conn.execute("SELECT 1 FROM sweeps WHERE status IN ('queued','running') AND kind='suche'").fetchone():
        raise ValueError('Es läuft bereits eine Sammelsuche – bitte warten, bis sie fertig ist.')
    label = f"{p['place']} · {p['radius_km']} km" + (f" · {len(p['industries'])} Branche(n)" if p['industries'] else '') + (f" · {', '.join(p['keywords'][:3])}" if p['keywords'] else '')
    progress = {s: {'status': 'wartet', 'label': SWEEP_SOURCES[s]} for s in p['sources']}
    cur = conn.execute('INSERT INTO sweeps(label, params_json, progress_json) VALUES (?,?,?)',
                       (label[:200], json.dumps(p, ensure_ascii=False), json.dumps(progress, ensure_ascii=False)))
    conn.commit()
    sid = cur.lastrowid
    if start:
        t = threading.Thread(target=run_sweep, args=(db_path, sid), daemon=True, name=f'sweep-{sid}')
        _THREADS[sid] = t
        t.start()
    return sweep_detail(conn, sid)


def _progress(conn, sid, source, **kw):
    row = conn.execute('SELECT progress_json FROM sweeps WHERE id=?', (sid,)).fetchone()
    prog = json.loads(row['progress_json'])
    prog.setdefault(source, {}).update(kw)
    conn.execute('UPDATE sweeps SET progress_json=? WHERE id=?', (json.dumps(prog, ensure_ascii=False), sid))
    conn.commit()


def _run_record(conn, source, sid, params):
    cur = conn.execute('INSERT INTO discovery_runs(source, params_json) VALUES (?,?)',
                       (source, json.dumps({'sweep': sid, **params}, ensure_ascii=False, sort_keys=True)))
    conn.commit()
    return cur.lastrowid


def _finish_run(conn, run_id, counts=None, error=''):
    if error:
        conn.execute("UPDATE discovery_runs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?", (error[:500], run_id))
    else:
        conn.execute("UPDATE discovery_runs SET status='done', result_count=?, filtered_count=?, finished_at=datetime('now') WHERE id=?",
                     (counts['new'] + counts['merged'], counts['filtered'], run_id))
    conn.commit()


def run_sweep(db_path, sid):
    from .model import connect
    with connect(db_path) as conn:
        sw = conn.execute('SELECT * FROM sweeps WHERE id=?', (sid,)).fetchone()
        p = json.loads(sw['params_json'])
        conn.execute("UPDATE sweeps SET status='running' WHERE id=?", (sid,))
        conn.commit()
        ua = lf._user_agent(conn)
        try:
            area = ar.resolve(conn, p['place'], p['radius_km'])
        except (lf.SourceError, ValueError) as exc:
            for s in p['sources']:
                _progress(conn, sid, s, status='fehler', error=f'Suchgebiet nicht bestimmbar: {exc}')
            conn.execute("UPDATE sweeps SET status='fehler', finished_at=datetime('now') WHERE id=?", (sid,))
            conn.commit()
            return
        ctx = {**p, 'center': area['center'], 'place_distance': {pl['name'].casefold(): pl['distance_km'] for pl in area['places']}}
        _progress(conn, sid, '_area', places=len(area['places']), center=area['center']['label'], via=area['source'])
        index = LeadIndex(conn)
        for source in p['sources']:
            _progress(conn, sid, source, status='läuft')
            run_id = _run_record(conn, source, sid, {'place': p['place'], 'radius_km': p['radius_km']})
            try:
                counts, detail = SOURCE_RUNNERS[source](conn, sid, run_id, ctx, area, ua, index)
                _finish_run(conn, run_id, counts)
                _progress(conn, sid, source, status='fertig', detail=detail, **counts)
            except (lf.SourceError, ValueError) as exc:
                _finish_run(conn, run_id, error=str(exc))
                _progress(conn, sid, source, status='fehler', error=str(exc)[:400])
            except Exception as exc:  # eine Quelle darf die anderen nicht stoppen
                _finish_run(conn, run_id, error=f'Unerwarteter Fehler: {exc.__class__.__name__}')
                _progress(conn, sid, source, status='fehler', error=f'Unerwarteter Fehler: {exc.__class__.__name__}')
        prog = json.loads(conn.execute('SELECT progress_json FROM sweeps WHERE id=?', (sid,)).fetchone()['progress_json'])
        ok = any(v.get('status') == 'fertig' for k, v in prog.items() if not k.startswith('_'))
        conn.execute("UPDATE sweeps SET status=?, finished_at=datetime('now') WHERE id=?", ('fertig' if ok else 'fehler', sid))
        conn.commit()


def _run_gleif(conn, sid, run_id, ctx, area, ua, index):
    total = {'found': 0, 'new': 0, 'merged': 0, 'known': 0, 'dismissed': 0, 'suppressed': 0, 'filtered': 0}
    requests, places_done, filters_note, attempt = 0, 0, '', 0
    leis = []
    for pl in area['places']:
        for page in range(1, MAX_GLEIF_PAGES_PER_PLACE + 1):
            if requests >= MAX_GLEIF_REQUESTS:
                break
            if requests:
                lf.SLEEP(GLEIF_DELAY)
            data = lf.gleif_page(ua, city=pl['name'], page=page, attempt_from=attempt)
            requests += 1
            attempt = data.get('_attempt', attempt)
            if attempt:
                filters_note = ' (GLEIF-Filter vereinfacht, Rest lokal gefiltert)'
            items = lf.gleif_items(data, city=pl['name'])
            for it in items:
                it['distance_km'] = pl['distance_km']
            c = store_items(conn, sid, run_id, 'gleif', items, ctx, index)
            for k in total:
                total[k] += c[k]
            leis += [it['lei'] for it in items if it.get('lei')]
            last = (data.get('meta', {}).get('pagination') or {}).get('lastPage', page)
            if page >= last or not data.get('data'):
                break
        places_done += 1
        _progress(conn, sid, 'gleif', status='läuft', detail=f'{places_done}/{len(area["places"])} Orte', **total)
    found_web = _websites_by_lei(conn, leis, ua) if leis else 0
    detail = f'{places_done} Orte, {requests} Abfragen{filters_note}' + (f', {found_web} Websites über Wikidata (LEI)' if found_web else '')
    return total, detail


def _websites_by_lei(conn, leis, ua):
    """Ergänzt Websites zu GLEIF-Firmen über Wikidata (Eigenschaft LEI → offizielle Website)."""
    found = 0
    for i in range(0, min(len(leis), 1000), 200):
        chunk = [l for l in leis[i:i + 200] if re.fullmatch(r'[A-Z0-9]{20}', l)]
        if not chunk:
            continue
        q = 'SELECT ?lei ?website WHERE { VALUES ?lei { ' + ' '.join(f'"{l}"' for l in chunk) + ' } ?c wdt:P1278 ?lei ; wdt:P856 ?website . }'
        try:
            data = lf.wikidata_sparql(q, ua, retries=0)
        except lf.SourceError:
            return found
        for b in data.get('results', {}).get('bindings', []):
            lei, web = b.get('lei', {}).get('value'), lf.clean_website(b.get('website', {}).get('value'))
            if lei and web:
                found += conn.execute("""UPDATE discovery_candidates SET website=?, website_status='quelle', website_evidence='Website laut Wikidata (über LEI)'
                                         WHERE lei=? AND website=''""", (web, lei)).rowcount
        conn.commit()
    return found


def _run_wikidata(conn, sid, run_id, ctx, area, ua, index):
    c = area['center']
    q = f'''SELECT ?company ?companyLabel ?website ?employees ?industryLabel ?lei ?coord ?placeLabel WHERE {{
  SERVICE wikibase:around {{ ?place wdt:P625 ?coord . bd:serviceParam wikibase:center "Point({c['lon']} {c['lat']})"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "{ctx['radius_km']}" . }}
  ?company wdt:P159 ?place .
  FILTER NOT EXISTS {{ ?company wdt:P31 wd:Q5 }}
  FILTER NOT EXISTS {{ ?company wdt:P576 ?dissolved }}
  OPTIONAL {{ ?company wdt:P856 ?website }}
  OPTIONAL {{ ?company wdt:P1128 ?employees }}
  OPTIONAL {{ ?company wdt:P452 ?industry }}
  OPTIONAL {{ ?company wdt:P1278 ?lei }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
}} LIMIT 3000'''
    data = lf.wikidata_sparql(q, ua)
    merged = {}
    for b in data.get('results', {}).get('bindings', []):
        qid = b.get('company', {}).get('value', '').rsplit('/', 1)[-1]
        name = b.get('companyLabel', {}).get('value', '')
        if not qid or not name or re.fullmatch(r'Q\d+', name):
            continue
        m = re.match(r'Point\(([-\d.]+) ([-\d.]+)\)', b.get('coord', {}).get('value', ''))
        item = merged.setdefault(qid, {'external_id': qid, 'name': name[:200], 'website': '', 'city': b.get('placeLabel', {}).get('value', ''),
                                       'industry': '', 'employees': 0, 'lei': b.get('lei', {}).get('value', ''),
                                       'distance_km': round(ar.haversine(c['lat'], c['lon'], float(m.group(2)), float(m.group(1))), 1) if m else None,
                                       'source_url': f'https://www.wikidata.org/wiki/{qid}'})
        if not item['website'] and b.get('website'):
            item['website'] = lf.clean_website(b['website']['value'])
        try:
            item['employees'] = max(item['employees'], int(float(b.get('employees', {}).get('value', 0) or 0)))
        except ValueError:
            pass
        lab = b.get('industryLabel', {}).get('value', '')
        if lab and not re.fullmatch(r'Q\d+', lab) and lab not in item['industry']:
            item['industry'] = (item['industry'] + ', ' + lab).strip(', ')[:200]
    counts = store_items(conn, sid, run_id, 'wikidata', list(merged.values()), ctx, index)
    return counts, f'{len(merged)} Unternehmen mit Sitz im Umkreis'


DEFAULT_OSM = [('office', 'company'), ('office', 'it'), ('office', 'consulting'), ('office', 'engineer'), ('office', 'architect'),
               ('office', 'tax_advisor'), ('office', 'lawyer'), ('office', 'advertising_agency'), ('craft', None), ('industrial', None)]


def _run_osm(conn, sid, run_id, ctx, area, ua, index):
    c = area['center']
    selectors = ind.osm_selectors(ctx['industries']) or DEFAULT_OSM
    r = int(ctx['radius_km'] * 1000)
    need_web = '' if ctx['industries'] else '["website"]'
    parts = []
    for key, value in selectors[:30]:
        sel = f'["{key}"="{value}"]' if value else f'["{key}"]'
        parts.append(f'nwr{sel}["name"]{need_web}(around:{r},{c["lat"]},{c["lon"]});')
    query = f'[out:json][timeout:80];\n(\n  {chr(10).join(parts)}\n);\nout center tags 3000;'
    data = lf.overpass(query, ua)
    items = []
    for el in data.get('elements', []):
        tags = el.get('tags', {})
        name = tags.get('name', '').strip()
        lat, lon = el.get('lat') or (el.get('center') or {}).get('lat'), el.get('lon') or (el.get('center') or {}).get('lon')
        kind = next((tags.get(k) for k in ('office', 'craft', 'shop', 'amenity', 'healthcare', 'industrial', 'tourism', 'leisure') if tags.get(k)), '')
        ikey = next((k for k in ctx['industries'] if any(tags.get(a) == b or (b is None and tags.get(a)) for a, b in ind.INDUSTRIES[k]['osm'])), '')
        items.append({'external_id': f"{el.get('type', 'node')}/{el.get('id', '')}", 'name': name[:200],
                      'website': lf.clean_website(tags.get('website') or tags.get('contact:website')),
                      'street': ' '.join(x for x in (tags.get('addr:street', ''), tags.get('addr:housenumber', '')) if x)[:200],
                      'zip': tags.get('addr:postcode', '')[:10], 'city': (tags.get('addr:city') or '')[:120],
                      'industry': kind.replace('_', ' ')[:200], 'industry_key': ikey, '_industry_matched': bool(ikey),
                      'distance_km': round(ar.haversine(c['lat'], c['lon'], lat, lon), 1) if lat and lon else None,
                      'source_url': f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id', '')}"})
    counts = store_items(conn, sid, run_id, 'osm', items, ctx, index)
    return counts, f'{len(items)} Einträge im Umkreis'


def _run_ted(conn, sid, run_id, ctx, area, ua, index):
    total = {'found': 0, 'new': 0, 'merged': 0, 'known': 0, 'dismissed': 0, 'suppressed': 0, 'filtered': 0}
    for preset in ctx['ted_presets']:
        items = lf.search_ted({'preset': preset, 'days': 30, 'limit': 50}, ua)
        cnt = store_items(conn, sid, run_id, 'ted', items, ctx, index)
        for k in total:
            total[k] += cnt[k]
    return total, 'bundesweit, letzte 30 Tage (Ausschreibungen sind öffentliche Aufträge – man bewirbt sich)'


SOURCE_RUNNERS = {'gleif': _run_gleif, 'wikidata': _run_wikidata, 'osm': _run_osm, 'ted': _run_ted}


def sweep_detail(conn, sid):
    row = conn.execute('SELECT * FROM sweeps WHERE id=?', (sid,)).fetchone()
    if not row:
        raise LookupError('Suche nicht gefunden.')
    d = dict(row)
    d['params'] = json.loads(d.pop('params_json'))
    d['progress'] = json.loads(d.pop('progress_json'))
    d['counts'] = {r['status']: r['n'] for r in conn.execute('SELECT status, COUNT(*) AS n FROM discovery_candidates WHERE sweep_id=? GROUP BY status', (sid,))}
    return d


def sweep_rows(conn):
    out = []
    for r in conn.execute('SELECT * FROM sweeps ORDER BY id DESC LIMIT 40'):
        d = dict(r)
        d['params'] = json.loads(d.pop('params_json'))
        d.pop('progress_json')
        counts = {x['status']: x['n'] for x in conn.execute('SELECT status, COUNT(*) AS n FROM discovery_candidates WHERE sweep_id=? GROUP BY status', (r['id'],))}
        d['open'] = counts.get('neu', 0)
        d['taken'] = counts.get('uebernommen', 0)
        d['dismissed'] = counts.get('verworfen', 0)
        out.append(d)
    return out


# ---------------------------------------------------------------- Großer Import (GLEIF-Export oder eigene Liste)

GENERIC_COLUMNS = {
    'name': ('firma', 'firmenname', 'unternehmen', 'name', 'company', 'legal name', 'entity.legalname'),
    'website': ('website', 'webseite', 'url', 'homepage', 'domain', 'internet'),
    'street': ('straße', 'strasse', 'adresse', 'street', 'anschrift'),
    'zip': ('plz', 'postleitzahl', 'zip', 'postal code', 'postcode'),
    'city': ('ort', 'stadt', 'city', 'gemeinde'),
    'register_id': ('register', 'registernummer', 'hrb', 'handelsregister'),
    'industry': ('branche', 'industry', 'kategorie', 'tätigkeit'),
}


def _pick(row, names):
    low = {k.strip().casefold(): v for k, v in row.items() if k}
    for n in names:
        if low.get(n):
            return low[n].strip()
    return ''


def parse_import(text, opts):
    """Liest einen GLEIF-Export (Spalten wie „Entity.LegalName“) oder eine eigene Liste (Firma/Name, Website, PLZ, Ort …)."""
    if text.startswith('﻿'):
        text = text[1:]
    sample = text[:5000]
    first = sample.split('\n', 1)[0]
    delimiter = max(',;\t', key=first.count)  # nur das Trennzeichen erkennen; Anführungszeichen nach Excel-Standard ("" = ")
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, quotechar='"', doublequote=True)
    fields = [f or '' for f in (reader.fieldnames or [])]
    gleif = 'LEI' in fields and 'Entity.LegalName' in fields
    if not gleif and not any(f.strip().casefold() in GENERIC_COLUMNS['name'] for f in fields):
        raise ValueError('Spalte mit dem Firmennamen nicht gefunden (z. B. „Firma“, „Name“ oder GLEIF-Export „Entity.LegalName“).')
    prefixes = [p for p in re.split(r'[,;\s]+', opts.get('plz', '')) if p]
    if any(not re.fullmatch(r'\d{1,5}', p) for p in prefixes):
        raise ValueError('PLZ-Filter: Ziffern bzw. Anfänge, z. B. „70, 71“.')
    items, skipped = [], {'inaktiv': 0, 'fonds_einzel': 0, 'plz': 0, 'ausland': 0}
    for row in reader:
        if gleif:
            if row.get('Entity.EntityStatus', 'ACTIVE') != 'ACTIVE':
                skipped['inaktiv'] += 1
                continue
            cat = row.get('Entity.EntityCategory', 'GENERAL')
            if cat not in ('GENERAL', 'BRANCH') and not (cat == 'SOLE_PROPRIETOR' and opts.get('include_sole')):
                skipped['fonds_einzel'] += 1
                continue
            if (row.get('Entity.LegalAddress.Country') or 'DE') != 'DE':
                skipped['ausland'] += 1
                continue
            street = ' '.join(x for x in (row.get('Entity.LegalAddress.FirstAddressLine', ''), row.get('Entity.LegalAddress.AddressNumber', '')) if x)
            item = {'name': row.get('Entity.LegalName', ''), 'lei': row.get('LEI', ''), 'external_id': row.get('LEI', ''),
                    'street': street, 'zip': row.get('Entity.LegalAddress.PostalCode', ''), 'city': (row.get('Entity.LegalAddress.City') or '').title() if (row.get('Entity.LegalAddress.City') or '').isupper() else row.get('Entity.LegalAddress.City', ''),
                    'register_id': row.get('Entity.RegistrationAuthority.RegistrationAuthorityEntityID', ''),
                    'signal_note': f"LEI seit {(row.get('Registration.InitialRegistrationDate') or '')[:10]}, Gründung {(row.get('Entity.EntityCreationDate') or '')[:10] or 'unbekannt'}",
                    'source_url': f"https://search.gleif.org/#/record/{row.get('LEI', '')}"}
        else:
            item = {k: _pick(row, cols) for k, cols in GENERIC_COLUMNS.items()}
            item['website'] = lf.clean_website(item['website'])
        if prefixes and not any((item.get('zip') or '').startswith(p) for p in prefixes):
            skipped['plz'] += 1
            continue
        items.append(item)
    return ('gleif_csv' if gleif else 'liste'), items, skipped


def import_file(conn, text, opts):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Leere Datei.')
    source, items, skipped = parse_import(text, opts)
    ctx = {'industries': ind.validate_keys(opts.get('industries', [])), 'keywords': ind.parse_keywords(opts.get('keywords', '')),
           'operative': opts.get('operative', True), 'include_sole': opts.get('include_sole', False)}
    label = f"Import {opts.get('filename') or 'CSV'} · {len(items)} Zeilen" + (f" · PLZ {opts['plz']}" if opts.get('plz') else '')
    cur = conn.execute("INSERT INTO sweeps(label, kind, params_json, status, progress_json, finished_at) VALUES (?, 'import', ?, 'fertig', '{}', datetime('now'))",
                       (label[:200], json.dumps({**opts, 'source': source}, ensure_ascii=False)))
    sid = cur.lastrowid
    run_id = _run_record(conn, source, sid, {'import': opts.get('filename', '')})
    counts = store_items(conn, sid, run_id, source, items, ctx)
    _finish_run(conn, run_id, counts)
    prog = {source: {'status': 'fertig', 'label': lf.SOURCES[source]['title'], **counts, 'skipped': skipped}}
    conn.execute('UPDATE sweeps SET progress_json=? WHERE id=?', (json.dumps(prog, ensure_ascii=False), sid))
    conn.commit()
    return {'sweep_id': sid, 'source': source, 'rows': len(items), 'skipped': skipped, **counts}


# ---------------------------------------------------------------- Sichtung

def _cand_view(r):
    d = dict(r)
    d['sources'] = json.loads(d.pop('sources_json') or '[]')
    d['contact'] = json.loads(d.pop('contact_json') or '{}')
    d['industry_label'] = ind.INDUSTRIES.get(d.get('industry_key') or '', {}).get('label', '')
    return d


def candidates(conn, q):
    get = lambda k, default='': (q.get(k, [default]) or [default])[0]
    status = get('status', 'neu')
    where, args = [], []
    if status != 'alle':
        if status not in ('neu', 'uebernommen', 'verworfen', 'dublette', 'gesperrt'):
            raise ValueError('Unbekannter Status.')
        where.append('status=?')
        args.append(status)
    if get('sweep_id'):
        if not get('sweep_id').isdigit():
            raise ValueError('sweep_id ungültig.')
        where.append('sweep_id=?')
        args.append(int(get('sweep_id')))
    else:
        where.append('sweep_id IS NOT NULL')
    if get('website') == '1':
        where.append("website<>''")
    if get('website') == '0':
        where.append("website=''")
    if get('source'):
        where.append('sources_json LIKE ?')
        args.append(f'%"source": "{re.sub(r"[^a-z_]", "", get("source"))}"%')
    if get('q'):
        where.append('(name LIKE ? OR city LIKE ? OR zip LIKE ?)')
        args += [f"%{get('q')[:60]}%"] * 3
    sql = 'FROM discovery_candidates WHERE ' + ' AND '.join(where)
    total = conn.execute('SELECT COUNT(*) ' + sql, args).fetchone()[0]
    nm = "ltrim(name, '\" ') COLLATE NOCASE"
    order = {'distanz': f'distance_km IS NULL, distance_km, {nm}', 'name': nm, 'quellen': f'length(sources_json) DESC, {nm}',
             'website': f"website='', {nm}"}.get(get('sort', 'distanz'), f'distance_km IS NULL, distance_km, {nm}')
    try:
        limit = max(1, min(200, int(get('limit', '100'))))
        offset = max(0, int(get('offset', '0')))
    except ValueError as exc:
        raise ValueError('limit/offset ungültig.') from exc
    rows = [_cand_view(r) for r in conn.execute(f'SELECT * {sql} ORDER BY {order} LIMIT ? OFFSET ?', (*args, limit, offset))]
    counts = {r['status']: r['n'] for r in conn.execute('SELECT status, COUNT(*) AS n FROM discovery_candidates WHERE sweep_id IS NOT NULL GROUP BY status')}
    return {'total': total, 'offset': offset, 'limit': limit, 'items': rows, 'counts': counts,
            'notice': 'Fund ≠ Kontakterlaubnis. Übernommene Firmen starten mit Rechtsstatus „unbekannt“.'}


def decide(conn, cid, decision):
    cand = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone()
    if not cand:
        raise LookupError('Treffer nicht gefunden.')
    if decision == 'verwerfen':
        res = lf.review_candidate(conn, cid, 'verwerfen')
        for k in [r['key'] for r in conn.execute('SELECT key FROM discovery_keys WHERE candidate_id=?', (cid,))]:
            conn.execute('INSERT OR IGNORE INTO discovery_dismissed(key) VALUES (?)', (k,))
        conn.commit()
        return res
    if decision != 'uebernehmen':
        raise ValueError('Entscheidung: uebernehmen oder verwerfen.')
    res = lf.review_candidate(conn, cid, 'uebernehmen')
    lid = res['lead_id']
    contact = json.loads(cand['contact_json'] or '{}')
    upd = {'legal_name': cand['name'], 'street': cand['street'], 'zip': cand['zip'], 'city': cand['city'],
           'register_number': cand['register_id'] if register_key(cand['register_id'], 'x') else ''}
    if cand['legal_form'] and contact:
        upd['business_phone'] = contact.get('business_phone', '')[:60]
        upd['business_email'] = contact.get('business_email', '')[:160]
    upd = {k: v for k, v in upd.items() if v}
    if upd:
        conn.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), lid))
    srcs = ', '.join(lf.SOURCES.get(s['source'], {}).get('title', s['source']) for s in json.loads(cand['sources_json'] or '[]'))
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lid, 'notiz', f"Quellen: {srcs}. Website: {cand['website_evidence'] or 'noch nicht gefunden'}."[:900]))
    conn.commit()
    return res


def bulk(conn, data):
    if not isinstance(data, dict) or set(data) != {'ids', 'decision'} or not isinstance(data['ids'], list) or not 1 <= len(data['ids']) <= 200:
        raise ValueError('Erwartet: {ids: [...] (1–200), decision}.')
    done, errors, lead_ids = 0, [], []
    for cid in data['ids']:
        if isinstance(cid, bool) or not isinstance(cid, int):
            raise ValueError('IDs müssen Zahlen sein.')
        try:
            res = decide(conn, cid, data['decision'])
            done += 1
            if res.get('lead_id'):
                lead_ids.append(res['lead_id'])
        except (ValueError, LookupError) as exc:
            errors.append(f'#{cid}: {exc}')
    return {'done': done, 'errors': errors[:20], 'lead_ids': lead_ids}


# ---------------------------------------------------------------- Website-Suche mit Nachweis

STOP_WORDS = {'gmbh', 'co', 'kg', 'ag', 'mbh', 'ug', 'haftungsbeschraenkt', 'ohg', 'gbr', 'ev', 'e', 'v', 'se', 'kgaa', 'und', 'der', 'die', 'das',
              'fuer', 'von', 'gesellschaft', 'mit', 'beschraenkter', 'haftung', 'the', 'and', 'of', 'deutschland', 'germany', 'stuttgart'}


def domain_guesses(name, city=''):
    words = [w for w in re.split(r'[^a-z0-9]+', _translit(name)) if w and w not in STOP_WORDS and w not in _translit(city).split()]
    if not words:
        return []
    joined, hyph = ''.join(words[:3]), '-'.join(words[:3])
    bases = [b for b in dict.fromkeys([joined, hyph, words[0], ''.join(words[:2])]) if 3 <= len(b) <= 40]
    if len(words) > 1 and len(words[0]) < 4:  # zu allgemeine Kurzformen nicht einzeln prüfen
        bases = [b for b in bases if b != words[0]]
    return ([f'{b}.de' for b in bases] + [f'{b}.com' for b in bases[:2]])[:7]


def _match(cand, fields):
    val = lambda k: ((fields.get(k) or {}).get('value') or '')
    reg = re.sub(r'\s+', '', val('register_number').upper())
    if reg and cand['register_id'] and reg == re.sub(r'\s+', '', cand['register_id'].upper()):
        return 'belegt', f"Registernummer {val('register_number')} im Impressum stimmt überein"
    nm, nm2 = normalize_name(cand['name']), normalize_name(val('legal_name'))
    if nm and nm2 and (nm == nm2 or nm in nm2 or nm2 in nm) and (not cand['zip'] or val('zip') == cand['zip']):
        return 'wahrscheinlich', f"Firmenname{' und PLZ' if cand['zip'] else ''} im Impressum stimmen überein"
    return None, ''


def find_website(conn, cid):
    """Prüft naheliegende Domains über das Impressum. Nur öffentliche Seiten, mit robots.txt und SSRF-Schutz."""
    from . import imprint
    cand = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone()
    tried = []
    targets = [cand['website']] if cand['website'] else domain_guesses(cand['name'], cand['city'])
    for dom in targets:
        tried.append(dom)
        try:
            res = imprint.research_domain(dom, include_persons=False)
        except Exception:  # Domain existiert nicht, gesperrt durch robots.txt o. Ä.
            continue
        if res.get('status') != 'ok':
            continue
        status, why = _match(cand, res.get('fields') or {})
        if status:
            f = res['fields']
            contact = {k: (f.get(k) or {}).get('value') for k in ('business_phone', 'business_email') if (f.get(k) or {}).get('value')}
            if res.get('imprint_url'):
                contact['imprint_url'] = res['imprint_url']
            web = lf.clean_website(res.get('home_url') or dom)
            conn.execute('''UPDATE discovery_candidates SET website=?, website_status=?, website_evidence=?, contact_json=?,
                            register_id=CASE WHEN register_id='' THEN ? ELSE register_id END, updated_at=? WHERE id=?''',
                         (web, status, why, json.dumps(contact, ensure_ascii=False), (f.get('register_number') or {}).get('value') or '', _now(), cid))
            conn.commit()
            return {'status': status, 'website': web, 'evidence': why}
    if cand['website']:
        conn.execute("UPDATE discovery_candidates SET website_status='nicht_bestaetigt', website_evidence=? WHERE id=?",
                     ('Impressum gefunden, aber Firma nicht eindeutig zuzuordnen – bitte selbst prüfen', cid))
    else:
        conn.execute("UPDATE discovery_candidates SET website_status='nicht_gefunden', website_evidence=? WHERE id=?",
                     (('Geprüft: ' + ', '.join(tried))[:300] if tried else 'Kein sinnvoller Domainname ableitbar', cid))
    conn.commit()
    return {'status': 'nicht_gefunden', 'tried': tried}


def queue_websites(conn, data, db_path, start=True):
    if not isinstance(data, dict) or set(data) != {'ids'} or not isinstance(data['ids'], list) or not 1 <= len(data['ids']) <= 200:
        raise ValueError('Erwartet: {ids: [...]} (1–200).')
    ids = [i for i in data['ids'] if isinstance(i, int) and not isinstance(i, bool)]
    n = 0
    for cid in ids:
        n += conn.execute("""UPDATE discovery_candidates SET website_status='wartet' WHERE id=? AND status='neu'
                             AND website_status IN ('', 'quelle', 'nicht_gefunden', 'nicht_bestaetigt')""", (cid,)).rowcount
    conn.commit()
    if n and start:
        _ensure_web_worker(db_path)
    return {'queued': n, 'notice': 'Die Website-Suche läuft im Hintergrund (etwa 2–10 Sekunden je Firma). Ergebnisse erscheinen in der Liste.'}


def _ensure_web_worker(db_path):
    with _LOCK:
        t = _WEB['thread']
        if t and t.is_alive():
            return
        t = threading.Thread(target=_web_worker, args=(db_path,), daemon=True, name='website-finder')
        _WEB['thread'] = t
        t.start()


def _web_worker(db_path):
    from .model import connect
    while True:
        with connect(db_path) as conn:
            row = conn.execute("SELECT id FROM discovery_candidates WHERE website_status='wartet' ORDER BY id LIMIT 1").fetchone()
            if not row:
                return
            conn.execute("UPDATE discovery_candidates SET website_status='laeuft' WHERE id=?", (row['id'],))
            conn.commit()
            try:
                find_website(conn, row['id'])
            except Exception as exc:  # nie hängen bleiben
                conn.execute("UPDATE discovery_candidates SET website_status='nicht_gefunden', website_evidence=? WHERE id=?",
                             (f'Fehler bei der Suche: {exc.__class__.__name__}', row['id']))
                conn.commit()


def wait_websites(timeout=60):
    t = _WEB['thread']
    if t:
        t.join(timeout)


# ---------------------------------------------------------------- HTTP

def _read_raw(h, limit=MAX_IMPORT_BYTES):
    raw_len = h.headers.get('Content-Length', '0')
    if not raw_len.isdigit() or not 0 < int(raw_len) <= limit:
        raise ValueError(f'Datei leer oder größer als {limit // 1_000_000} MB.')
    if h.headers.get('Content-Type', '').split(';')[0].strip() not in ('text/csv', 'text/plain'):
        raise ValueError('Bitte als text/csv senden.')
    data = h.rfile.read(int(raw_len))
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError('Datei ist weder UTF-8 noch Windows-1252.')


def route_sweep(h, conn, method, route, query, db_path):
    if route == '/api/industries' and method == 'GET':
        h._send(200, ind.catalog())
        return True
    if not route.startswith(('/api/sweeps', '/api/sweep-candidates', '/api/area')):
        return False
    get = lambda k, d='': (query.get(k, [d]) or [d])[0]
    if route == '/api/area/resolve' and method == 'POST':
        b = h._body()
        if set(b) - {'place', 'radius_km'}:
            raise ValueError('Erwartet: {place, radius_km}.')
        try:
            h._send(200, ar.resolve(conn, str(b.get('place', '')), b.get('radius_km', 30)))
        except lf.SourceError as exc:
            h._error(str(exc), 502)
        return True
    if route == '/api/sweeps':
        if method == 'GET':
            h._send(200, sweep_rows(conn))
            return True
        if method == 'POST':
            h._send(202, start_sweep(conn, h._body(), db_path))
            return True
    if route == '/api/sweeps/import' and method == 'POST':
        opts = {'filename': get('filename')[:120], 'plz': get('plz')[:60], 'operative': get('operative', '1') == '1',
                'include_sole': get('include_sole') == '1', 'industries': [x for x in get('industries').split(',') if x], 'keywords': get('keywords')[:400]}
        h._send(201, import_file(conn, _read_raw(h), opts))
        return True
    m = re.fullmatch(r'/api/sweeps/(\d+)', route)
    if m and method == 'GET':
        h._send(200, sweep_detail(conn, int(m.group(1))))
        return True
    if route == '/api/sweep-candidates' and method == 'GET':
        h._send(200, candidates(conn, query))
        return True
    if route == '/api/sweep-candidates/bulk' and method == 'POST':
        h._send(200, bulk(conn, h._body()))
        return True
    if route == '/api/sweep-candidates/find-websites' and method == 'POST':
        h._send(202, queue_websites(conn, h._body(), db_path))
        return True
    m = re.fullmatch(r'/api/sweep-candidates/(\d+)/decision', route)
    if m and method == 'POST':
        b = h._body()
        if set(b) != {'decision'}:
            raise ValueError('Erwartet: {decision}.')
        h._send(200, decide(conn, int(m.group(1)), b['decision']))
        return True
    return False
