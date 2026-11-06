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
from .research import catalog
from .research import identity as ident
from .research import jobs
from . import legal_forms as lfm
from .company_data import check_suppressed, normalize_domain, normalize_name

SWEEP_SOURCES = {'gleif': 'GLEIF', 'wikidata': 'Wikidata', 'osm': 'OpenStreetMap', 'ted': 'TED-Ausschreibungen'}
ORG_KIND_CHOICES = (lfm.UNTERNEHMEN, lfm.VEREIN, lfm.OEFFENTLICH)
ORG_KINDS_DEFAULT = (lfm.UNTERNEHMEN,)
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
                       ('contact_json', "TEXT NOT NULL DEFAULT '{}'"), ('updated_at', "TEXT NOT NULL DEFAULT ''"),
                       ('imprint_json', "TEXT NOT NULL DEFAULT '{}'"), ('org_kind', "TEXT NOT NULL DEFAULT ''"),
                       ('dup_of', 'INTEGER'), ('dup_score', 'REAL'), ('dup_reason', "TEXT NOT NULL DEFAULT ''"), ('possible_lead_id', 'INTEGER'),
                       ('merged_into', 'INTEGER')):
        if name not in cols:
            conn.execute(f'ALTER TABLE discovery_candidates ADD COLUMN {name} {decl}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_discovery_cand_sweep ON discovery_candidates(sweep_id, status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_discovery_cand_dup ON discovery_candidates(dup_of)')
    conn.execute('''CREATE TABLE IF NOT EXISTS discovery_not_same (a TEXT NOT NULL, b TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (a, b))''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_cand_web ON discovery_candidates(website_status)")


for _key, _title in (('gleif_csv', 'GLEIF-Export (CSV-Import)'), ('liste', 'Eigene Firmenliste (CSV-Import)')):
    lf.SOURCES.setdefault(_key, {'title': _title, 'license': 'CC0 1.0' if _key == 'gleif_csv' else 'eigene Liste', 'ampel': 'gruen',
                                 'attribution': 'Daten: GLEIF (CC0)' if _key == 'gleif_csv' else 'eigene Datei', 'url': '',
                                 'good_for': 'Große Firmenlisten offline einlesen.', 'limits': 'Keine Website/Branche in GLEIF-Daten.'})


def recover_sweeps(conn):
    """v1.16: Suchen mit persistentem Auftrag laufen nach einem Neustart weiter; nur alte Suchen ohne Auftrag gelten als abgebrochen."""
    for r in conn.execute("SELECT id FROM sweeps WHERE status IN ('queued','running')").fetchall():
        job = conn.execute("SELECT status FROM research_jobs WHERE job_key=? ORDER BY id DESC LIMIT 1", (f'sweep:{r["id"]}',)).fetchone()
        if job and job['status'] in jobs.JOB_ACTIVE:
            conn.execute("UPDATE sweeps SET status='queued' WHERE id=?", (r['id'],))
        else:
            conn.execute("UPDATE sweeps SET status='abgebrochen', finished_at=datetime('now') WHERE id=?", (r['id'],))
    conn.execute("UPDATE discovery_candidates SET website_status='wartet' WHERE website_status='laeuft'")
    adopt_waiting_websites(conn)


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


def _ident_item(r, website_ok=True):
    keys = r.keys() if hasattr(r, 'keys') else r
    g = (lambda k: (r[k] if k in keys else '') or '')
    return {'name': g('name') or g('company'), 'lei': g('lei'), 'register_id': g('register_id') or g('register_number'),
            'website': g('website') if website_ok else '', 'zip': g('zip'), 'city': g('city'), 'legal_form': g('legal_form')}


def not_same_pairs(conn):
    """„Andere Firma“-Entscheidungen zwischen Treffern als Paare von IDs (kleinere zuerst)."""
    out = set()
    for r in conn.execute("SELECT a, b FROM discovery_not_same WHERE a LIKE 'c%' AND b LIKE 'c%'"):
        try:
            out.add((int(r['a'][1:]), int(r['b'][1:])))
        except ValueError:
            continue
    return out


def _ns_pair(a, b):
    return (f'c{min(a, b)}', f'c{max(a, b)}')


class CandidateIndex:
    """Dubletten-Abgleich über alle bisherigen Treffer (Masterplan 2.0, Sprint 4) – blockiert, damit auch große Mengen schnell sind."""

    def __init__(self, conn):
        self.idx = ident.Index()
        self.status = {}
        self.not_same = not_same_pairs(conn)
        for r in conn.execute("SELECT * FROM discovery_candidates WHERE status<>'zusammengefuehrt' AND dup_of IS NULL"):
            self.add(r)

    def add(self, r):
        web_ok = (r['website_status'] or '') in ('', 'quelle', 'belegt', 'bestaetigt')
        self.idx.add(r['id'], _ident_item(r, web_ok))
        self.status[r['id']] = r['status']

    def match(self, item, exclude=(), for_id=None):
        excl = set(exclude)
        if for_id is not None:
            excl |= {b for a, b in self.not_same if a == for_id} | {a for a, b in self.not_same if b == for_id} | {for_id}
        return self.idx.best(item, exclude=excl)


class LeadIndex:
    """Einmal aufgebauter Index der bestehenden Leads (Domain, Registernummer+Ort, Name) – plus unscharfer Abgleich (v1.17)."""
    def __init__(self, conn):
        self.domains, self.registers, self.names = {}, {}, {}
        self.fuzzy = ident.Index()
        for r in conn.execute('SELECT id, company, legal_name, legal_form, website, register_number, city, location, zip FROM leads'):
            item = {'name': r['legal_name'] or r['company'], 'register_id': r['register_number'], 'website': r['website'], 'zip': r['zip'],
                    'city': r['city'] or (r['location'] or '').split(' ')[-1], 'legal_form': r['legal_form']}
            self.fuzzy.add(r['id'], item)
            if r['legal_name'] and r['company'] and r['company'] != r['legal_name']:
                self.fuzzy.add(f"{r['id']}:alias", {**item, 'name': r['company']})
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
        hit = self.names.get(normalize_name(item.get('name')))
        if hit:
            best = self.fuzzy.best(item)
            if best and best[0] == 'same':
                return int(str(best[1]).split(':')[0])
            verdict = ident.decide(item, self.fuzzy.items.get(hit, {}))[0] if hit in self.fuzzy.items else 'same'
            return hit if verdict != 'different' else None
        best = self.fuzzy.best(item)
        return int(str(best[1]).split(':')[0]) if best and best[0] == 'same' else None

    def possible(self, item):
        best = self.fuzzy.best(item)
        return (int(str(best[1]).split(':')[0]), best[2], best[3]) if best and best[0] == 'possible' else None


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def store_items(conn, sweep_id, run_id, source, items, ctx, index=None, cindex=None):
    """Filtert, führt zusammen und speichert Treffer. Gibt Zähler zurück.
    v1.17: Dubletten zuverlässig erkennen – sicher gleiche Firmen werden zusammengeführt, mögliche Dubletten nicht doppelt
    aufgeführt, sondern beim Haupteintrag zur Prüfung gezeigt; fremde Firmen (andere Rechtsform/Register/Ort) bleiben getrennt."""
    index = index or LeadIndex(conn)
    cindex = cindex or ctx.get('_cindex') or CandidateIndex(conn)
    ctx['_cindex'] = cindex
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
        kind = item.get('org_kind') or lfm.kind_of(name, item.get('elf', ''), legal)
        if source != 'ted' and (kind if kind != lfm.SONSTIGE else lfm.UNTERNEHMEN) not in ctx.get('org_kinds', ORG_KINDS_DEFAULT):
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
        existing, possible, match_reason = None, None, ''
        probe = {**item, 'name': name, 'legal_form': legal}
        for k in keys:
            row = conn.execute('SELECT d.* FROM discovery_keys k JOIN discovery_candidates d ON d.id=k.candidate_id WHERE k.key=?', (k,)).fetchone()
            if row:
                if row['merged_into']:
                    row = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (row['merged_into'],)).fetchone() or row
                verdict, _, why = ident.decide(probe, _ident_item(row))
                if verdict == 'different' and not k.startswith('lei:'):
                    continue  # z. B. alter Namensschlüssel: „Müller GmbH“ ≠ „Müller GmbH & Co. KG“
                existing, match_reason = row, f'Schlüssel {k.split(":")[0]}'
                break
        if not existing:
            hit = cindex.match(probe)
            if hit and hit[0] == 'same':
                existing = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (hit[1],)).fetchone()
                match_reason = hit[3]
            elif hit:
                possible = hit
        src_entry = {'source': source, 'url': item.get('source_url', '')}
        if match_reason:
            src_entry['match'] = match_reason[:120]
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
            item.setdefault('org_kind', kind)
            for f in ('website', 'register_id', 'street', 'zip', 'city', 'legal_form', 'lei', 'industry_key', 'org_kind'):
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
            cindex.add(conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (existing['id'],)).fetchone())
            c['merged'] += 1
            continue
        dup = index.find(probe)
        blocked = bool(check_suppressed(conn, website=item.get('website', ''), name=name))
        status = 'gesperrt' if blocked else ('dublette' if dup else 'neu')
        maybe_lead = index.possible(probe) if not dup else None
        if possible and cindex.status.get(possible[1]) != 'neu':
            # ähnlich zu einem schon entschiedenen Treffer: übernommen → Hinweis auf dessen Lead, sonst nur Hinweis
            prow = conn.execute('SELECT lead_id, duplicate_lead_id, status FROM discovery_candidates WHERE id=?', (possible[1],)).fetchone()
            plead = prow and (prow['lead_id'] or prow['duplicate_lead_id'])
            if plead and not dup and not maybe_lead:
                maybe_lead = (plead, possible[2], possible[3])
            possible = None
        cols = {'run_id': run_id, 'sweep_id': sweep_id, 'source': source, 'external_id': str(item.get('external_id', ''))[:120],
                'name': name[:200], 'website': item.get('website', ''), 'street': item.get('street', ''), 'zip': item.get('zip', ''),
                'city': item.get('city', ''), 'country': item.get('country', 'DE'), 'industry': item.get('industry', '')[:200],
                'employees': int(item.get('employees') or 0), 'legal_form': legal, 'register_id': item.get('register_id', ''),
                'signal_type': item.get('signal_type', 'kein_signal'), 'signal_note': item.get('signal_note', ''),
                'signal_date': item.get('signal_date', ''), 'source_url': item.get('source_url', ''), 'license': license_text,
                'status': status, 'duplicate_lead_id': dup, 'sources_json': json.dumps([src_entry], ensure_ascii=False),
                'distance_km': dist, 'industry_key': item.get('industry_key', ''), 'lei': item.get('lei', ''), 'org_kind': kind,
                'website_status': 'quelle' if item.get('website') else '',
                'website_evidence': f"Website laut {lf.SOURCES.get(source, {}).get('title', source)}" if item.get('website') else '',
                'updated_at': _now(),
                'dup_of': possible[1] if possible and status == 'neu' else None,
                'dup_score': (possible[2] if possible else (maybe_lead[1] if maybe_lead else None)),
                'dup_reason': (possible[3] if possible else (f'evtl. schon als Lead: {maybe_lead[2]}' if maybe_lead else ''))[:200],
                'possible_lead_id': maybe_lead[0] if maybe_lead else None}
        cur = conn.execute(f"INSERT INTO discovery_candidates ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", tuple(cols.values()))
        _add_keys(conn, cur.lastrowid, keys)
        if not cols['dup_of']:
            cindex.add(conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cur.lastrowid,)).fetchone())
        else:
            c['possible'] = c.get('possible', 0) + 1
        c['new' if status == 'neu' else ('suppressed' if blocked else 'known')] += 1
    conn.commit()
    return c


def _add_keys(conn, cid, keys):
    for k in keys:
        conn.execute('INSERT OR IGNORE INTO discovery_keys(key, candidate_id) VALUES (?,?)', (k, cid))


# ---------------------------------------------------------------- Sammelsuche

def validate_params(data):
    allowed = {'place', 'radius_km', 'industries', 'keywords', 'sources', 'operative', 'include_sole', 'ted_presets', 'find_websites',
               'org_kinds', 'ted_nationwide'}
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
    kinds = data.get('org_kinds', list(ORG_KINDS_DEFAULT))
    if not isinstance(kinds, list) or not kinds or any(k not in ORG_KIND_CHOICES for k in kinds):
        raise ValueError('Organisationsart: ' + ', '.join(ORG_KIND_CHOICES) + '.')
    for flag in ('operative', 'include_sole', 'find_websites', 'ted_nationwide'):
        if flag in data and not isinstance(data[flag], bool):
            raise ValueError(f'{flag}: true/false.')
    return {'place': place, 'radius_km': radius, 'industries': ind.validate_keys(data.get('industries', [])),
            'keywords': ind.parse_keywords(data.get('keywords', '')), 'sources': sources, 'operative': data.get('operative', True),
            'include_sole': data.get('include_sole', False), 'ted_presets': presets, 'find_websites': data.get('find_websites', True),
            'org_kinds': kinds, 'ted_nationwide': data.get('ted_nationwide', False)}


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
    # v1.16 (Sprint 3): persistenter Auftrag – je Quelle ein Schritt, danach Abschluss. Gleiche „Domain“ = nacheinander,
    # damit sich die Quellen derselben Suche nicht beim Zusammenführen überholen. Übersteht einen Neustart.
    tasks = [{'key': f'source:{s}', 'kind': 'sweep_source', 'label': SWEEP_SOURCES[s], 'domain': f'sweep-{sid}',
              'payload': {'sid': sid, 'source': s}, 'max_attempts': 1} for s in p['sources']]
    tasks.append({'key': 'finish', 'kind': 'sweep_finish', 'label': 'Abschluss & Website-Suche', 'domain': f'sweep-{sid}',
                  'payload': {'sid': sid}, 'max_attempts': 2})
    job, _ = jobs.submit(conn, 'sweep', f'Sammelsuche {label}', tasks, job_key=f'sweep:{sid}', params={'sid': sid},
                         priority=3, db_path=db_path, start=start)
    _THREADS[sid] = jobs.JobWaiter(db_path, job['id'])
    return sweep_detail(conn, sid)


def _sweep_job(conn, sid):
    return conn.execute("SELECT * FROM research_jobs WHERE job_key=? ORDER BY id DESC LIMIT 1", (f'sweep:{sid}',)).fetchone()


@jobs.handler('sweep_source')
def _job_source(db_path, payload, ctx):
    from .model import connect
    run_sweep(db_path, payload['sid'], only=[payload['source']], finalize=False)
    with connect(db_path) as conn:
        prog = json.loads(conn.execute('SELECT progress_json FROM sweeps WHERE id=?', (payload['sid'],)).fetchone()['progress_json'])
    st = prog.get(payload['source'], {})
    if st.get('status') == 'fehler':
        return {'_status': 'failed', '_error': st.get('error', 'Quelle fehlgeschlagen')}
    return {k: st.get(k) for k in ('new', 'merged', 'known', 'filtered')}


@jobs.handler('sweep_finish')
def _job_finish(db_path, payload, ctx):
    from .model import connect
    with connect(db_path) as conn:
        return _finalize_sweep(conn, payload['sid'], db_path)


@jobs.handler('sweep_source:cancel')
def _job_source_cancel(conn, payload):
    conn.execute("UPDATE sweeps SET status='abgebrochen', finished_at=datetime('now') WHERE id=? AND status IN ('queued','running')", (payload['sid'],))


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


RETRY_DELAYS = (20, 60)   # Sekunden – Überlastung der offenen Quellen abwarten (exponentielles Zurückweichen)
AUTO_WEBSITES = 200      # nach der Suche automatisch Websites suchen (Anzahl Firmen ohne Website, nächste zuerst)
AUTO_WEB_START = True    # in Tests ausgeschaltet


def run_sweep(db_path, sid, only=None, finalize=True):
    from .model import connect
    with connect(db_path) as conn:
        sw = conn.execute('SELECT * FROM sweeps WHERE id=?', (sid,)).fetchone()
        p = json.loads(sw['params_json'])
        conn.execute("UPDATE sweeps SET status='running', finished_at='' WHERE id=?", (sid,))
        conn.commit()
        ua = lf._user_agent(conn)
        sources = [s for s in p['sources'] if not only or s in only]
        try:
            area = ar.resolve(conn, p['place'], p['radius_km'])
        except (lf.SourceError, ValueError) as exc:
            for s in sources:
                _progress(conn, sid, s, status='fehler', error=f'Suchgebiet nicht bestimmbar: {exc}')
            conn.execute("UPDATE sweeps SET status='fehler', finished_at=datetime('now') WHERE id=?", (sid,))
            conn.commit()
            return
        ctx = {**p, 'center': area['center'], 'place_distance': {pl['name'].casefold(): pl['distance_km'] for pl in area['places']}}
        _progress(conn, sid, '_area', places=len(area['places']), center=area['center']['label'], via=area['source'])
        index = LeadIndex(conn)
        ctx['_cindex'] = CandidateIndex(conn)
        ctx['_catalog'] = catalog.catalog_path(db_path)
        for source in sources:
            _progress(conn, sid, source, status='läuft', error='', detail='')
            run_id = _run_record(conn, source, sid, {'place': p['place'], 'radius_km': p['radius_km']})
            for attempt in range(len(RETRY_DELAYS) + 1):
                if attempt:
                    _progress(conn, sid, source, status='läuft', detail=f'{attempt + 1}. Versuch läuft …')
                try:
                    counts, detail = SOURCE_RUNNERS[source](conn, sid, run_id, ctx, area, ua, index)
                    _finish_run(conn, run_id, counts)
                    _progress(conn, sid, source, status='fertig', error='', detail=detail + (f' (im {attempt + 1}. Versuch)' if attempt else ''), **counts)
                    break
                except lf.SourceError as exc:
                    if exc.retryable and attempt < len(RETRY_DELAYS):
                        wait = min(max(exc.retry_after or 0, RETRY_DELAYS[attempt]), 120)
                        _progress(conn, sid, source, status='wartet', error='',
                                  detail=f'Quelle gerade überlastet – neuer Versuch in {wait} s ({attempt + 2}. von {len(RETRY_DELAYS) + 1} Versuchen)')
                        lf.SLEEP(wait)
                        continue
                    _finish_run(conn, run_id, error=str(exc))
                    _progress(conn, sid, source, status='fehler', retryable=exc.retryable,
                              error=str(exc)[:400] + (' – nach mehreren Versuchen. „Fehlgeschlagene Quellen erneut abfragen“ später nutzen.' if exc.retryable else ''))
                    break
                except ValueError as exc:
                    _finish_run(conn, run_id, error=str(exc))
                    _progress(conn, sid, source, status='fehler', error=str(exc)[:400])
                    break
                except Exception as exc:  # eine Quelle darf die anderen nicht stoppen
                    _finish_run(conn, run_id, error=f'Unerwarteter Fehler: {exc.__class__.__name__}')
                    _progress(conn, sid, source, status='fehler', error=f'Unerwarteter Fehler: {exc.__class__.__name__}')
                    break
        if finalize:
            _finalize_sweep(conn, sid, db_path)


def _finalize_sweep(conn, sid, db_path):
    """Abschluss einer Sammelsuche (idempotent): Websites über LEI ergänzen, Website-Suche einplanen, Status setzen."""
    sw = conn.execute('SELECT * FROM sweeps WHERE id=?', (sid,)).fetchone()
    p = json.loads(sw['params_json'])
    prog = json.loads(sw['progress_json'])
    if 'gleif' in p['sources'] and prog.get('gleif', {}).get('status') == 'fertig' and not prog.get('_lei'):
        leis = [r['lei'] for r in conn.execute("SELECT lei FROM discovery_candidates WHERE sweep_id=? AND lei<>'' AND website='' ORDER BY id", (sid,))]
        found = _websites_by_lei(conn, leis, lf._user_agent(conn)) if leis else 0
        _progress(conn, sid, '_lei', checked=len(leis), found=found)
        if found:
            gp = prog.get('gleif', {})
            _progress(conn, sid, 'gleif', detail=(gp.get('detail', '') + f', {found} Websites über Wikidata (LEI)').strip(', '))
    prog = json.loads(conn.execute('SELECT progress_json FROM sweeps WHERE id=?', (sid,)).fetchone()['progress_json'])
    ok = any(v.get('status') == 'fertig' for k, v in prog.items() if not k.startswith('_'))
    queued = 0
    if ok and p.get('find_websites', True):
        ids = [r['id'] for r in conn.execute("""SELECT id FROM discovery_candidates WHERE sweep_id=? AND status='neu' AND website=''
                                                AND website_status='' AND source<>'ted' ORDER BY distance_km IS NULL, distance_km LIMIT ?""", (sid, AUTO_WEBSITES))]
        if ids:
            queued = queue_websites(conn, {'ids': ids}, db_path, start=AUTO_WEB_START)['queued']
            _progress(conn, sid, '_web', queued=queued + (prog.get('_web') or {}).get('queued', 0))
    conn.execute("UPDATE sweeps SET status=?, finished_at=datetime('now') WHERE id=?", ('fertig' if ok else 'fehler', sid))
    conn.commit()
    return {'status': 'fertig' if ok else 'fehler', 'websites_queued': queued}


def retry_sweep(conn, sid, db_path, start=True):
    sw = conn.execute('SELECT * FROM sweeps WHERE id=?', (sid,)).fetchone()
    if not sw or sw['kind'] != 'suche':
        raise LookupError('Suche nicht gefunden.')
    if sw['status'] in ('queued', 'running'):
        raise ValueError('Die Suche läuft noch.')
    prog = json.loads(sw['progress_json'])
    failed = [k for k, v in prog.items() if not k.startswith('_') and v.get('status') == 'fehler']
    if not failed:
        raise ValueError('Keine fehlgeschlagene Quelle in dieser Suche.')
    job = _sweep_job(conn, sid)
    if job:
        keys = [f'source:{s}' for s in failed] + ['finish']
        conn.execute(f"""UPDATE research_tasks SET status='queued', attempts=0, next_attempt_at=0, last_error='', note='erneut angefordert'
                         WHERE job_id=? AND task_key IN ({','.join('?' * len(keys))})""", (job['id'], *keys))
        conn.execute("UPDATE research_jobs SET status='queued', finished_at='' WHERE id=?", (job['id'],))
        conn.execute("UPDATE sweeps SET status='queued', finished_at='' WHERE id=?", (sid,))
        jobs._refresh(conn, job['id'])
        conn.commit()
        if start:
            jobs.ensure_workers(db_path)
            _THREADS[sid] = jobs.JobWaiter(db_path, job['id'])
    elif start:
        t = threading.Thread(target=run_sweep, args=(db_path, sid, failed), daemon=True, name=f'sweep-retry-{sid}')
        _THREADS[sid] = t
        t.start()
    return {'retrying': failed}


def _run_gleif(conn, sid, run_id, ctx, area, ua, index):
    """GLEIF-API; fällt sie aus und liegt ein lokaler GLEIF-Katalog vor (v1.17), kommen die übrigen Orte aus dem Katalog."""
    state = {'total': {'found': 0, 'new': 0, 'merged': 0, 'known': 0, 'dismissed': 0, 'suppressed': 0, 'filtered': 0}, 'places_done': 0}
    try:
        return _run_gleif_api(conn, sid, run_id, ctx, area, ua, index, state)
    except lf.SourceError as exc:
        cat = ctx.get('_catalog')
        if not cat or not catalog.has_data(cat):
            raise
        rest = area['places'][state['places_done']:]
        items = catalog.area_items(cat, rest)
        c = store_items(conn, sid, run_id, 'gleif', items, ctx, index)
        total = {k: state['total'][k] + c.get(k, 0) for k in state['total']}
        last = (catalog.status(cat).get('last_import') or {}).get('finished_at', '')[:10]
        return total, (f"GLEIF-API nicht erreichbar ({str(exc)[:120]}) – {len(rest)} Orte aus dem lokalen GLEIF-Katalog"
                       f"{f' (Stand {last})' if last else ''}" + (f", {state['places_done']} Orte vorher live" if state['places_done'] else ''))


def _run_gleif_api(conn, sid, run_id, ctx, area, ua, index, state):
    total = state['total']
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
        state['places_done'] = places_done
        _progress(conn, sid, 'gleif', status='läuft', detail=f'{places_done}/{len(area["places"])} Orte', **total)
    return total, f'{places_done} Orte, {requests} Abfragen{filters_note}'


def _websites_by_lei(conn, leis, ua):
    """Ergänzt Websites zu GLEIF-Firmen über Wikidata (Eigenschaft LEI → offizielle Website)."""
    found = 0
    if lf.wikidata_status()['blocked_s']:
        return 0  # Wikidata hat um Pause gebeten: Zusatzabfrage auslassen
    for i in range(0, min(len(leis), 1000), 1000):
        chunk = [l for l in dict.fromkeys(leis[i:i + 1000]) if re.fullmatch(r'[A-Z0-9]{20}', l)]
        if not chunk:
            continue
        q = 'SELECT ?lei ?website WHERE { VALUES ?lei { ' + ' '.join(f'"{l}"' for l in chunk) + ' } ?c wdt:P1278 ?lei ; wdt:P856 ?website . }'
        try:
            # Live-Befund: Bei Störungen ist schon die 2. Anfrage pro Minute zu viel (→ 1000 s Sperre). Daher ≥ 65 s Abstand.
            data = lf.wikidata_sparql(q, ua, retries=0, min_gap=lf.WIKIDATA_OUTAGE_GAP)
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


def _osm_sel(key, value):
    return f'["{key}"="{value}"]' if value else f'["{key}"]'


def _run_osm(conn, sid, run_id, ctx, area, ua, index):
    """OpenStreetMap im Umkreis – in kleinen Teilabfragen (je 6 Merkmale), damit überlastete Server eher antworten."""
    c = area['center']
    selectors = ind.osm_selectors(ctx['industries']) or DEFAULT_OSM
    r = int(max(ctx['radius_km'], 3) * 1000)
    need_web = '' if ctx['industries'] else '["website"]'
    elements, errors, chunks = {}, [], [selectors[i:i + 6] for i in range(0, min(len(selectors), 36), 6)]
    for n, chunk in enumerate(chunks):
        if n:
            lf.SLEEP(2)
        parts = [f'nwr{_osm_sel(key, value)}["name"]{need_web}(around:{r},{c["lat"]},{c["lon"]});' for key, value in chunk]
        query = f'[out:json][timeout:60];\n(\n  {chr(10).join(parts)}\n);\nout center tags 1500;'
        try:
            for el in lf.overpass(query, ua).get('elements', []):
                elements[f"{el.get('type')}/{el.get('id')}"] = el
        except lf.SourceError as exc:
            errors.append(exc)
            if not elements and exc.retryable is False:
                break  # kein Server erreichbar: restliche Teilabfragen nicht abwarten
    if errors and not elements:
        raise errors[0]
    items = []
    for el in elements.values():
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
    return counts, f'{len(items)} Einträge im Umkreis' + (f' ({len(errors)} von {len(chunks)} Teilabfragen überlastet)' if errors else '')


def _run_ted(conn, sid, run_id, ctx, area, ua, index):
    """Ausschreibungen: standardmäßig nur Auftraggeber im Suchgebiet (serverseitiger Ortsfilter), wahlweise bundesweit."""
    total = {'found': 0, 'new': 0, 'merged': 0, 'known': 0, 'dismissed': 0, 'suppressed': 0, 'filtered': 0}
    regional = not ctx.get('ted_nationwide')
    places = sorted(area['places'], key=lambda p: p['distance_km'])[:120] if regional else []
    for preset in ctx['ted_presets']:
        items = lf.search_ted({'preset': preset, 'days': 90 if regional else 30, 'limit': 100 if regional else 50,
                               'cities': [p['name'] for p in places]}, ua)
        for it in items:
            pl = next((p for p in places if lf.city_matches(it.get('city'), p['name'])), None)
            if pl:
                it['distance_km'] = pl['distance_km']
        if regional:
            items = [it for it in items if it.get('distance_km') is not None]
        cnt = store_items(conn, sid, run_id, 'ted', items, ctx, index)
        for k in total:
            total[k] += cnt[k]
    where = f'Auftraggeber im Suchgebiet ({len(places)} Orte), letzte 90 Tage' if regional else 'bundesweit, letzte 30 Tage'
    return total, where + ' (Ausschreibungen sind öffentliche Aufträge – man bewirbt sich)'


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
                    'elf': (row.get('Entity.LegalForm.EntityLegalFormCode') or '').upper(),
                    'signal_note': f"LEI seit {(row.get('Registration.InitialRegistrationDate') or '')[:10]}, Gründung {(row.get('Entity.EntityCreationDate') or '')[:10] or 'unbekannt'}",
                    'source_url': f"https://search.gleif.org/#/record/{row.get('LEI', '')}"}
            hit = lfm.from_elf(item['elf'])
            if hit:
                item['legal_form'], item['org_kind'] = hit
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
    dups_only = get('dups') == '1'
    if dups_only:  # Prüfliste: Einträge mit möglicher Dublette (beim Treffer oder als Lead)
        where.append("status='neu' AND (dup_of IS NOT NULL OR possible_lead_id IS NOT NULL)")
    elif status != 'alle':
        if status not in ('neu', 'uebernommen', 'verworfen', 'dublette', 'gesperrt', 'zusammengefuehrt'):
            raise ValueError('Unbekannter Status.')
        where.append('status=?')
        args.append(status)
    if not dups_only and status != 'zusammengefuehrt':
        # v1.17: mögliche Dubletten erscheinen nicht als eigener Eintrag, sondern beim Haupteintrag
        where.append('dup_of IS NULL')
        if status == 'alle':
            where.append("status<>'zusammengefuehrt'")
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
    if get('no_ted') == '1':
        where.append("source<>'ted'")
    if get('max_km'):
        try:
            km = float(get('max_km'))
        except ValueError as exc:
            raise ValueError('max_km ungültig.') from exc
        where.append('distance_km IS NOT NULL AND distance_km<=?')
        args.append(km)
    facet_sql, facet_args = 'FROM discovery_candidates WHERE ' + ' AND '.join(where), list(args)
    if get('city'):
        where.append('city=? COLLATE NOCASE')
        args.append(get('city')[:120])
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
    _attach_duplicates(conn, rows)
    counts = {r['status']: r['n'] for r in conn.execute('SELECT status, COUNT(*) AS n FROM discovery_candidates WHERE sweep_id IS NOT NULL AND dup_of IS NULL GROUP BY status')}
    counts['moegliche_dubletten'] = conn.execute('''SELECT COUNT(*) FROM discovery_candidates WHERE sweep_id IS NOT NULL AND status='neu'
                                                   AND (dup_of IS NOT NULL OR possible_lead_id IS NOT NULL)''').fetchone()[0]
    counts['ohne_website'] = conn.execute("""SELECT COUNT(*) FROM discovery_candidates WHERE sweep_id IS NOT NULL AND status='neu'
                                             AND dup_of IS NULL AND website=''""").fetchone()[0]
    counts['zusammengefuehrt'] = conn.execute("SELECT COUNT(*) FROM discovery_candidates WHERE sweep_id IS NOT NULL AND status='zusammengefuehrt'").fetchone()[0]
    cities = [{'city': r['city'], 'n': r['n']} for r in conn.execute(f"SELECT city, COUNT(*) AS n {facet_sql} AND city<>'' GROUP BY city COLLATE NOCASE ORDER BY n DESC LIMIT 40", facet_args)]
    return {'total': total, 'offset': offset, 'limit': limit, 'items': rows, 'counts': counts, 'cities': cities,
            'notice': 'Fund ≠ Kontakterlaubnis. Übernommene Firmen starten mit Rechtsstatus „unbekannt“.'}


def _brief(r):
    return {'id': r['id'], 'name': r['name'], 'legal_form': r['legal_form'], 'zip': r['zip'], 'city': r['city'], 'street': r['street'],
            'website': r['website'], 'register_id': r['register_id'], 'lei': r['lei'], 'status': r['status'],
            'sources': [s['source'] for s in json.loads(r['sources_json'] or '[]')], 'dup_score': r['dup_score'], 'dup_reason': r['dup_reason']}


def _attach_duplicates(conn, rows):
    """Hängt an jeden Haupteintrag seine möglichen Dubletten (zur Entscheidung) und den evtl. schon vorhandenen Lead."""
    ids = [r['id'] for r in rows]
    by = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for d in conn.execute(f"SELECT * FROM discovery_candidates WHERE status='neu' AND dup_of IN ({','.join('?' * len(chunk))}) ORDER BY dup_score DESC",
                              chunk):
            by.setdefault(d['dup_of'], []).append(_brief(d))
    for r in rows:
        r['possible_duplicates'] = by.get(r['id'], [])
        if r.get('dup_of'):
            p = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (r['dup_of'],)).fetchone()
            r['duplicate_primary'] = _brief(p) if p else None
        if r.get('possible_lead_id'):
            ld = conn.execute('SELECT id, company, website, location FROM leads WHERE id=?', (r['possible_lead_id'],)).fetchone()
            r['possible_lead'] = dict(ld) if ld else None


MERGE_FIELDS = ('website', 'register_id', 'street', 'zip', 'city', 'legal_form', 'lei', 'industry_key', 'org_kind', 'signal_note', 'source_url')


def merge_candidate(conn, keep_id, drop_id, reason=''):
    """Führt Treffer `drop` in `keep` zusammen: Quellen, Schlüssel und fehlende Angaben wandern mit; nichts geht verloren.
    `drop` bleibt als „zusammengeführt“ (mit Verweis) erhalten, damit die Entscheidung nachvollziehbar ist."""
    keep = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (keep_id,)).fetchone()
    drop = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (drop_id,)).fetchone()
    if not keep or not drop or keep_id == drop_id:
        raise LookupError('Treffer nicht gefunden.')
    sources = json.loads(keep['sources_json'] or '[]')
    for src in json.loads(drop['sources_json'] or '[]'):
        if not any(x['source'] == src['source'] and x.get('url') == src.get('url') for x in sources):
            sources.append({**src, 'match': (reason or src.get('match') or '')[:120]})
    upd = {'sources_json': json.dumps(sources, ensure_ascii=False), 'updated_at': _now()}
    for f in MERGE_FIELDS:
        if not keep[f] and drop[f]:
            upd[f] = drop[f]
    if drop['website'] and not keep['website']:
        for f in ('website_status', 'website_evidence', 'imprint_json', 'contact_json'):
            upd[f] = drop[f]
    if (drop['employees'] or 0) > (keep['employees'] or 0):
        upd['employees'] = drop['employees']
    if drop['distance_km'] is not None and (keep['distance_km'] is None or drop['distance_km'] < keep['distance_km']):
        upd['distance_km'] = drop['distance_km']
    if drop['industry'] and drop['industry'] not in (keep['industry'] or ''):
        upd['industry'] = ((keep['industry'] or '') + ', ' + drop['industry']).strip(', ')[:200]
    conn.execute(f"UPDATE discovery_candidates SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), keep_id))
    conn.execute('UPDATE discovery_keys SET candidate_id=? WHERE candidate_id=?', (keep_id, drop_id))
    conn.execute('UPDATE discovery_candidates SET dup_of=? WHERE dup_of=?', (keep_id, drop_id))
    conn.execute('UPDATE discovery_candidates SET merged_into=? WHERE merged_into=?', (keep_id, drop_id))
    conn.execute("""UPDATE discovery_candidates SET status='zusammengefuehrt', merged_into=?, dup_of=NULL, dup_reason=?, updated_at=?
                    WHERE id=?""", (keep_id, (reason or 'zusammengeführt')[:200], _now(), drop_id))
    if drop['website_status'] in ('wartet', 'laeuft'):
        conn.execute("UPDATE discovery_candidates SET website_status='' WHERE id=?", (drop_id,))
    return keep_id


def review_duplicate(conn, cid, decision):
    """Entscheidung zu einer möglichen Dublette.
    gleich → in den Haupteintrag zusammenführen · verschieden → als eigene Firma behalten (wird nicht wieder vorgeschlagen)
    lead_gleich → ist schon Lead (Status „schon Lead“) · lead_verschieden → Hinweis auf den Lead entfernen."""
    cand = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone()
    if not cand:
        raise LookupError('Treffer nicht gefunden.')
    if cand['status'] != 'neu':
        raise ValueError('Treffer wurde bereits bearbeitet.')
    if decision in ('gleich', 'verschieden'):
        if not cand['dup_of']:
            raise ValueError('Für diesen Treffer ist keine mögliche Dublette vermerkt.')
        primary = cand['dup_of']
        if decision == 'gleich':
            merge_candidate(conn, primary, cid, 'von dir bestätigt: gleiche Firma')
        else:
            conn.execute('INSERT OR IGNORE INTO discovery_not_same(a, b) VALUES (?,?)', _ns_pair(primary, cid))
            conn.execute("UPDATE discovery_candidates SET dup_of=NULL, dup_score=NULL, dup_reason=?, updated_at=? WHERE id=?",
                         (f'von dir: andere Firma als #{primary}', _now(), cid))
        conn.commit()
        return {'status': 'zusammengefuehrt' if decision == 'gleich' else 'neu', 'primary': primary}
    if decision in ('lead_gleich', 'lead_verschieden'):
        lid = cand['possible_lead_id']
        if not lid:
            raise ValueError('Für diesen Treffer ist kein möglicher Lead vermerkt.')
        if decision == 'lead_gleich':
            conn.execute("""UPDATE discovery_candidates SET status='dublette', duplicate_lead_id=?, possible_lead_id=NULL, dup_of=NULL,
                            dup_reason='von dir bestätigt: schon als Lead vorhanden', updated_at=? WHERE id=?""", (lid, _now(), cid))
            conn.execute('UPDATE discovery_candidates SET dup_of=NULL, possible_lead_id=? WHERE dup_of=?', (lid, cid))
        else:
            conn.execute('INSERT OR IGNORE INTO discovery_not_same(a, b) VALUES (?,?)', (f'c{cid}', f'l{lid}'))
            conn.execute("UPDATE discovery_candidates SET possible_lead_id=NULL, dup_reason=?, updated_at=? WHERE id=?",
                         (f'von dir: anderer Lead als #{lid}', _now(), cid))
        conn.commit()
        return {'status': 'dublette' if decision == 'lead_gleich' else 'neu', 'lead_id': lid}
    raise ValueError('Entscheidung: gleich, verschieden, lead_gleich oder lead_verschieden.')


def dedupe_candidates(conn):
    """Bereinigt den Bestand (auch Daten aus älteren Versionen): sicher gleiche offene Treffer werden zusammengeführt,
    mögliche Dubletten zur Prüfung beim Haupteintrag einsortiert. Bereits entschiedene Treffer bleiben unverändert –
    sie dienen nur als Anker. Gibt Zähler zurück."""
    rows = conn.execute("""SELECT * FROM discovery_candidates WHERE status<>'zusammengefuehrt'
                           ORDER BY CASE status WHEN 'neu' THEN 1 ELSE 0 END, id""").fetchall()
    idx, ns, status = ident.Index(), not_same_pairs(conn), {}
    leads = LeadIndex(conn)
    lead_ns = {(r['a'], r['b']) for r in conn.execute("SELECT a, b FROM discovery_not_same WHERE b LIKE 'l%'")}
    out = {'checked': len(rows), 'merged': 0, 'possible': 0, 'known_lead': 0, 'possible_lead': 0}
    for r in rows:
        web_ok = (r['website_status'] or '') in ('', 'quelle', 'belegt', 'bestaetigt')
        item = _ident_item(r, web_ok)
        if r['status'] != 'neu' or r['dup_of']:
            if not r['dup_of']:
                idx.add(r['id'], item)
                status[r['id']] = r['status']
            continue
        excl = {b for a, b in ns if a == r['id']} | {a for a, b in ns if b == r['id']}
        hit = idx.best(item, exclude=excl)
        if hit and hit[0] == 'same':
            merge_candidate(conn, hit[1], r['id'], f'automatisch: {hit[3]}')
            out['merged'] += 1
            continue
        if hit and status.get(hit[1]) == 'neu':
            conn.execute('UPDATE discovery_candidates SET dup_of=?, dup_score=?, dup_reason=? WHERE id=?', (hit[1], hit[2], hit[3][:200], r['id']))
            out['possible'] += 1
            continue
        lid = r['duplicate_lead_id'] or leads.find(item)
        if lid and not r['duplicate_lead_id'] and (f"c{r['id']}", f'l{lid}') not in lead_ns:
            conn.execute("UPDATE discovery_candidates SET status='dublette', duplicate_lead_id=? WHERE id=?", (lid, r['id']))
            out['known_lead'] += 1
            continue
        if not r['possible_lead_id']:
            maybe = leads.possible(item)
            if maybe and (f"c{r['id']}", f'l{maybe[0]}') not in lead_ns:
                conn.execute('UPDATE discovery_candidates SET possible_lead_id=?, dup_score=?, dup_reason=? WHERE id=?',
                             (maybe[0], maybe[1], f'evtl. schon als Lead: {maybe[2]}'[:200], r['id']))
                out['possible_lead'] += 1
        idx.add(r['id'], item)
        status[r['id']] = 'neu'
    conn.commit()
    return out


def _rehome_duplicates(conn, cid, decision, lead_id=None):
    """Nach der Entscheidung über einen Haupteintrag dessen mögliche Dubletten wieder sichtbar machen – mit Hinweis."""
    if decision == 'uebernehmen' and lead_id:
        conn.execute("""UPDATE discovery_candidates SET dup_of=NULL, possible_lead_id=?, dup_reason=? WHERE dup_of=? AND status='neu'""",
                     (lead_id, f'evtl. dieselbe Firma wie der übernommene Treffer #{cid}', cid))
    else:
        conn.execute("""UPDATE discovery_candidates SET dup_of=NULL, dup_reason=? WHERE dup_of=? AND status='neu'""",
                     (f'ähnlich zum verworfenen Treffer #{cid}', cid))


def decide(conn, cid, decision):
    cand = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone()
    if not cand:
        raise LookupError('Treffer nicht gefunden.')
    if decision == 'verwerfen':
        res = lf.review_candidate(conn, cid, 'verwerfen')
        _rehome_duplicates(conn, cid, 'verwerfen')
        for k in [r['key'] for r in conn.execute('SELECT key FROM discovery_keys WHERE candidate_id=?', (cid,))]:
            conn.execute('INSERT OR IGNORE INTO discovery_dismissed(key) VALUES (?)', (k,))
        conn.commit()
        return res
    if decision != 'uebernehmen':
        raise ValueError('Entscheidung: uebernehmen oder verwerfen.')
    res = lf.review_candidate(conn, cid, 'uebernehmen')
    lid = res['lead_id']
    conn.execute('UPDATE discovery_candidates SET dup_of=NULL, possible_lead_id=NULL WHERE id=?', (cid,))
    _rehome_duplicates(conn, cid, 'uebernehmen', lid)
    contact = json.loads(cand['contact_json'] or '{}')
    upd = {'legal_name': cand['name'], 'legal_form': cand['legal_form'] if cand['source'] != 'ted' else '', 'street': cand['street'],
           'zip': cand['zip'], 'city': cand['city'],
           'register_number': cand['register_id'] if register_key(cand['register_id'], 'x') else ''}
    if cand['legal_form'] and contact:
        upd['business_phone'] = contact.get('business_phone', '')[:60]
        upd['business_email'] = contact.get('business_email', '')[:160]
    upd = {k: v for k, v in upd.items() if v}
    if upd:
        conn.execute(f"UPDATE leads SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), lid))
    if cand['website'] and cand['website_status'] not in CONFIRMED_WEB and cand['website_status'] not in ('', 'wartet', 'laeuft'):
        # Empfehlung A: ein nicht bestätigter Vorschlag wird nicht zur Website der Firma
        conn.execute("UPDATE leads SET website='' WHERE id=? AND website=?", (lid, cand['website']))
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (lid, 'notiz', f"Website-Vorschlag {cand['website']} noch nicht bestätigt ({cand['website_evidence']}). Bitte prüfen."[:900]))
    auto = _apply_imprint(conn, lid, cand)
    srcs = ', '.join(lf.SOURCES.get(s['source'], {}).get('title', s['source']) for s in json.loads(cand['sources_json'] or '[]'))
    conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                 (lid, 'notiz', (f"Quellen: {srcs}. Website: {cand['website_evidence'] or 'noch nicht gefunden'}."
                                 + (f" Aus dem Impressum automatisch übernommen: {', '.join(auto)}." if auto else ''))[:900]))
    conn.commit()
    res['auto_applied'] = auto
    return res


AUTO_FIELDS = ('legal_name', 'legal_form', 'street', 'zip', 'city', 'register_court', 'register_number', 'vat_id', 'business_phone', 'business_email')


def _apply_imprint(conn, lead_id, cand):
    """Übernimmt Firmendaten aus dem bei der Website-Suche gelesenen Impressum in LEERE Lead-Felder (nie überschreiben).
    Bei „belegt“ (Registernummer stimmt überein) gelten die Werte als bestätigt, sonst bleiben sie als ungeprüfte Belege stehen."""
    from .company_data import add_fact
    imp = json.loads(cand['imprint_json'] or '{}')
    fields = imp.get('fields') or {}
    if not fields:
        return []
    confirmed = cand['website_status'] in ('belegt', 'bestaetigt')
    lead = dict(conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone())
    src, stype = imp.get('imprint_url') or cand['website'], imp.get('source_type') or 'impressum_html'
    applied = []
    for key in AUTO_FIELDS:
        v = (fields.get(key) or {}).get('value')
        if not v:
            continue
        add_fact(conn, lead_id, key, v, stype, src, (fields.get(key) or {}).get('excerpt', ''), 'website-suche-v1', 'hoch' if confirmed else 'mittel',
                 'bestaetigt' if confirmed else 'ungeprueft')
        if confirmed and not lead.get(key):
            conn.execute(f'UPDATE leads SET {key}=? WHERE id=?', (v[:300], lead_id))
            applied.append(key)
    if confirmed and src:
        conn.execute("""UPDATE leads SET imprint_url=CASE WHEN imprint_url='' THEN ? ELSE imprint_url END, imprint_checked_at=?,
                        updated_at=datetime('now') WHERE id=?""", (src, imp.get('checked_at') or _now(), lead_id))
    return applied


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
    rejected = set(json.loads(cand['imprint_json'] or '{}').get('rejected_domains', []))
    targets = [cand['website']] if cand['website'] else [d for d in domain_guesses(cand['name'], cand['city']) if d not in rejected]
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
            imp = {'imprint_url': res.get('imprint_url') or '', 'source_type': res.get('source_type') or 'impressum_html', 'checked_at': res.get('checked_at', ''),
                   'fields': {k: {'value': v.get('value'), 'excerpt': (v.get('excerpt') or '')[:300]} for k, v in f.items() if v and v.get('value')},
                   'rejected_domains': sorted(rejected), 'guessed': not cand['website']}
            if status == 'wahrscheinlich':  # Empfehlung A: nur ein Vorschlag – nichts aus dem Impressum in die Firma schreiben
                why = f'Vorschlag: {why} – bitte prüfen'
            conn.execute('''UPDATE discovery_candidates SET website=?, website_status=?, website_evidence=?, contact_json=?, imprint_json=?,
                            register_id=CASE WHEN register_id='' AND ?='belegt' THEN ? ELSE register_id END, updated_at=? WHERE id=?''',
                         (web, status, why, json.dumps(contact, ensure_ascii=False), json.dumps(imp, ensure_ascii=False), status,
                          (f.get('register_number') or {}).get('value') or '', _now(), cid))
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


CONFIRMED_WEB = ('quelle', 'belegt', 'bestaetigt')


def review_website(conn, cid, data):
    """Website-Vorschlag („wahrscheinlich“ / „nicht eindeutig“) von Hand bestätigen oder ablehnen (Empfehlung A)."""
    if not isinstance(data, dict) or set(data) != {'decision'} or data['decision'] not in ('bestaetigen', 'ablehnen'):
        raise ValueError('Erwartet: {decision: bestaetigen | ablehnen}.')
    cand = conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone()
    if not cand:
        raise LookupError('Treffer nicht gefunden.')
    if not cand['website'] or cand['website_status'] not in ('wahrscheinlich', 'nicht_bestaetigt'):
        raise ValueError('Nur offene Website-Vorschläge können bestätigt oder abgelehnt werden.')
    imp = json.loads(cand['imprint_json'] or '{}')
    if data['decision'] == 'bestaetigen':
        conn.execute("UPDATE discovery_candidates SET website_status='bestaetigt', website_evidence=?, updated_at=? WHERE id=?",
                     ((cand['website_evidence'].replace('Vorschlag: ', '').replace(' – bitte prüfen', '') + ' – von dir bestätigt')[:300], _now(), cid))
        if cand['lead_id']:
            conn.execute("UPDATE leads SET website=CASE WHEN website='' THEN ? ELSE website END WHERE id=?", (cand['website'], cand['lead_id']))
            _apply_imprint(conn, cand['lead_id'], conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone())
    else:
        dom = lf.normalize_domain(cand['website'])
        imp['rejected_domains'] = sorted(set(imp.get('rejected_domains', [])) | {dom})
        imp.pop('fields', None)
        conn.execute("""UPDATE discovery_candidates SET website='', website_status='abgelehnt', website_evidence=?, contact_json='{}', imprint_json=?,
                        updated_at=? WHERE id=?""", (f'Vorschlag {dom} von dir abgelehnt', json.dumps(imp, ensure_ascii=False), _now(), cid))
    conn.commit()
    return _cand_view(conn.execute('SELECT * FROM discovery_candidates WHERE id=?', (cid,)).fetchone())


def queue_websites(conn, data, db_path, start=True):
    if not isinstance(data, dict) or set(data) != {'ids'} or not isinstance(data['ids'], list) or not 1 <= len(data['ids']) <= 200:
        raise ValueError('Erwartet: {ids: [...]} (1–200).')
    ids = [i for i in data['ids'] if isinstance(i, int) and not isinstance(i, bool)]
    marked = []
    for cid in ids:
        if conn.execute("""UPDATE discovery_candidates SET website_status='wartet' WHERE id=? AND status='neu'
                           AND website_status IN ('', 'quelle', 'nicht_gefunden', 'nicht_bestaetigt', 'abgelehnt')""", (cid,)).rowcount:
            marked.append(cid)
    conn.commit()
    job = None
    if marked:
        job = _website_job(conn, marked, db_path, start)
    return {'queued': len(marked), 'job_id': job['id'] if job else None,
            'notice': 'Die Website-Suche läuft im Hintergrund (etwa 2–10 Sekunden je Firma). Ergebnisse erscheinen in der Liste.'}


def _website_job(conn, cids, db_path, start):
    names = {r['id']: r['name'] for r in conn.execute(f"SELECT id, name FROM discovery_candidates WHERE id IN ({','.join('?' * len(cids))})", cids)}
    tasks = [{'key': f'cand:{cid}', 'kind': 'website', 'label': names.get(cid, f'#{cid}')[:120], 'payload': {'cid': cid}, 'max_attempts': 2}
             for cid in cids]
    job, _ = jobs.submit(conn, 'website', f'Website-Suche ({len(cids)} Firmen)', tasks, db_path=db_path, start=start, priority=6)
    _WEB['db'] = db_path
    return job


def adopt_waiting_websites(conn, db_path=None, start=False):
    """Firmen mit „Suche wartet“, aber ohne offenen Auftragsschritt (z. B. aus älteren Versionen), in einen Auftrag übernehmen."""
    rows = [r['id'] for r in conn.execute("""SELECT d.id FROM discovery_candidates d WHERE d.website_status='wartet' AND NOT EXISTS (
        SELECT 1 FROM research_tasks t WHERE t.kind='website' AND t.task_key='cand:' || d.id AND t.status IN ('queued','running'))""")]
    for i in range(0, len(rows), 200):
        _website_job(conn, rows[i:i + 200], db_path, start)
    return len(rows)


@jobs.handler('website')
def _job_website(db_path, payload, ctx):
    from .model import connect
    with connect(db_path) as conn:
        cand = conn.execute('SELECT status, website_status FROM discovery_candidates WHERE id=?', (payload['cid'],)).fetchone()
        if not cand or cand['website_status'] not in ('wartet', 'laeuft'):
            raise jobs.Skip('Nicht mehr in der Website-Suche.')
        conn.execute("UPDATE discovery_candidates SET website_status='laeuft' WHERE id=?", (payload['cid'],))
        conn.commit()
        try:
            return find_website(conn, payload['cid'])
        except Exception as exc:  # nie hängen bleiben – Fehler gehört zu genau dieser Firma
            conn.execute("UPDATE discovery_candidates SET website_status='nicht_gefunden', website_evidence=? WHERE id=?",
                         (f'Fehler bei der Suche: {exc.__class__.__name__}', payload['cid']))
            conn.commit()
            return {'_status': 'failed', '_error': f'{exc.__class__.__name__}: {exc}'}


@jobs.handler('website:retry')
def _job_website_retry(conn, job_id):
    for t in conn.execute("SELECT payload_json FROM research_tasks WHERE job_id=? AND status='queued'", (job_id,)).fetchall():
        conn.execute("UPDATE discovery_candidates SET website_status='wartet' WHERE id=? AND status='neu' AND website_status IN ('nicht_gefunden','')",
                     (json.loads(t['payload_json'])['cid'],))


@jobs.handler('website:cancel')
def _job_website_cancel(conn, payload):
    conn.execute("UPDATE discovery_candidates SET website_status='' WHERE id=? AND website_status='wartet'", (payload['cid'],))


def _web_worker(db_path):
    """Kompatibel zu früher: Website-Suche synchron abarbeiten (Tests, Werkzeuge)."""
    from .model import connect
    with connect(db_path) as conn:
        adopt_waiting_websites(conn, db_path, start=False)
    jobs.run_until_idle(db_path, kinds=('website',))


def wait_websites(timeout=60):
    if _WEB.get('db'):
        jobs.wait_idle(_WEB['db'], timeout, kinds=('website',))


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
    m = re.fullmatch(r'/api/sweeps/(\d+)/retry', route)
    if m and method == 'POST':
        h._send(202, retry_sweep(conn, int(m.group(1)), db_path))
        return True
    m = re.fullmatch(r'/api/sweeps/(\d+)', route)
    if m and method == 'GET':
        h._send(200, sweep_detail(conn, int(m.group(1))))
        return True
    if route == '/api/sweep-candidates' and method == 'GET':
        h._send(200, candidates(conn, query))
        return True
    if route == '/api/sweep-candidates/dedupe' and method == 'POST':
        if h._body() != {'run': True}:
            raise ValueError('Erwartet: {"run": true}.')
        h._send(200, dedupe_candidates(conn))
        return True
    m = re.fullmatch(r'/api/sweep-candidates/(\d+)/duplicate', route)
    if m and method == 'POST':
        b = h._body()
        if set(b) != {'decision'}:
            raise ValueError('Erwartet: {decision}.')
        h._send(200, review_duplicate(conn, int(m.group(1)), b['decision']))
        return True
    if route == '/api/sweep-candidates/bulk' and method == 'POST':
        h._send(200, bulk(conn, h._body()))
        return True
    if route == '/api/sweep-candidates/find-websites' and method == 'POST':
        h._send(202, queue_websites(conn, h._body(), db_path))
        return True
    m = re.fullmatch(r'/api/sweep-candidates/(\d+)/website', route)
    if m and method == 'POST':
        h._send(200, review_website(conn, int(m.group(1)), h._body()))
        return True
    m = re.fullmatch(r'/api/sweep-candidates/(\d+)/decision', route)
    if m and method == 'POST':
        b = h._body()
        if set(b) != {'decision'}:
            raise ValueError('Erwartet: {decision}.')
        h._send(200, decide(conn, int(m.group(1)), b['decision']))
        return True
    return False
