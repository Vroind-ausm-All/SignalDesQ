"""Großer Firmenkatalog offline: GLEIF Golden Copy / Delta als Datei (Masterplan 2.0, Sprint 4 – SignalDesk v1.17).

- Liest CSV oder ZIP **zeilenweise** (Streaming) – auch mehrere GB, ohne die Datei in den Arbeitsspeicher zu laden.
  Hochladen ebenfalls in Blöcken direkt auf die Platte.
- Eigene SQLite-Datei neben der Hauptdatenbank (`<name>.katalog.sqlite3`), damit Millionen Zeilen die
  Arbeitsdatenbank nicht aufblähen. Volltextsuche über FTS5 (in Python enthalten), sonst LIKE.
  DuckDB wurde gemessen (tools/bench_catalog.py) und ist optional – siehe Bericht.
- Je LEI genau ein Eintrag (Upsert): Golden Copy = Vollbestand (nicht mehr enthaltene LEIs gelten als „nicht mehr
  aktiv“), Delta = nur Änderungen. Inaktive bzw. eingezogene Registrierungen werden markiert, nicht gelöscht.
- Jeder Import wird mit Quelle, Lizenz (CC0 1.0), Datei, Zählern und Dauer protokolliert.
- Aus dem Katalog wird nichts automatisch zum Lead: Treffer gehen über die Sichtung (mit Dubletten-Abgleich).
- Fällt die GLEIF-API aus, nutzt die Sammelsuche den Katalog als Ersatz (GLEIF-Fallback).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path

from . import identity as ident
from . import jobs

SUFFIX = '.katalog.sqlite3'
BATCH = 2000
MAX_UPLOAD = 3 * 1024 ** 3  # Golden Copy als ZIP ≈ 0,5 GB, entpackt ≈ 4 GB (wird entpackt nur gestreamt)
CHUNK = 1024 * 1024
LICENSE = 'CC0 1.0 (GLEIF)'
SOURCE = 'GLEIF Golden Copy / Delta (LEI-CDF, CSV)'
INACTIVE_REG = {'RETIRED', 'ANNULLED', 'DUPLICATE', 'MERGED', 'CANCELLED'}
REQUIRED = ('LEI', 'Entity.LegalName')
csv.field_size_limit(1024 * 1024)


def catalog_path(db_path):
    p = Path(db_path)
    return p.with_name(p.stem + SUFFIX)


def upload_dir(db_path):
    p = Path(db_path)
    return p.with_name(p.stem + '.katalog-uploads')


def connect_catalog(path):
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    init_catalog(conn)
    return conn


def _has_fts(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='entities_fts'").fetchone())


def init_catalog(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS entities (
        lei TEXT NOT NULL UNIQUE, name TEXT NOT NULL, name_norm TEXT NOT NULL DEFAULT '', legal_form TEXT NOT NULL DEFAULT '',
        elf TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '', street TEXT NOT NULL DEFAULT '', zip TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '', city_norm TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT '', register_id TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL DEFAULT '', registered TEXT NOT NULL DEFAULT '', last_update TEXT NOT NULL DEFAULT '',
        reg_status TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, seen_import INTEGER, changed_import INTEGER
      );
      CREATE INDEX IF NOT EXISTS idx_ent_zip ON entities(country, zip);
      CREATE INDEX IF NOT EXISTS idx_ent_city ON entities(country, city_norm);
      CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL, countries TEXT NOT NULL DEFAULT 'DE',
        status TEXT NOT NULL DEFAULT 'laeuft', rows INTEGER NOT NULL DEFAULT 0, inserted INTEGER NOT NULL DEFAULT 0,
        updated INTEGER NOT NULL DEFAULT 0, unchanged INTEGER NOT NULL DEFAULT 0, deactivated INTEGER NOT NULL DEFAULT 0,
        skipped_json TEXT NOT NULL DEFAULT '{}', bytes INTEGER NOT NULL DEFAULT 0, seconds REAL NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
    ''')
    if not _has_fts(conn):
        try:
            conn.executescript('''
              CREATE VIRTUAL TABLE entities_fts USING fts5(name_norm, content='entities', content_rowid='rowid');
              CREATE TRIGGER ent_ai AFTER INSERT ON entities BEGIN INSERT INTO entities_fts(rowid, name_norm) VALUES (new.rowid, new.name_norm); END;
              CREATE TRIGGER ent_ad AFTER DELETE ON entities BEGIN
                INSERT INTO entities_fts(entities_fts, rowid, name_norm) VALUES ('delete', old.rowid, old.name_norm); END;
              CREATE TRIGGER ent_au AFTER UPDATE OF name_norm ON entities BEGIN
                INSERT INTO entities_fts(entities_fts, rowid, name_norm) VALUES ('delete', old.rowid, old.name_norm);
                INSERT INTO entities_fts(rowid, name_norm) VALUES (new.rowid, new.name_norm); END;
            ''')
        except sqlite3.OperationalError:  # SQLite ohne FTS5 – Suche dann per LIKE
            pass
    conn.commit()


# ---------------------------------------------------------------- Einlesen (Streaming)

def _open_text(path):
    """Öffnet CSV oder ZIP (größte CSV darin) als Text-Strom. Gibt (stream, roher Dateiobjekt, Gesamtbytes) zurück."""
    path = Path(path)
    size = path.stat().st_size
    if zipfile.is_zipfile(path):
        zf = zipfile.ZipFile(path)
        members = [m for m in zf.infolist() if m.filename.lower().endswith('.csv') and not m.is_dir()]
        if not members:
            zf.close()
            raise ValueError('ZIP enthält keine CSV-Datei.')
        m = max(members, key=lambda x: x.file_size)
        raw = zf.open(m)
        return io.TextIOWrapper(raw, encoding='utf-8-sig', newline='', errors='replace'), zf, size
    raw = open(path, 'rb')  # noqa: SIM115 – wird vom Aufrufer geschlossen
    return io.TextIOWrapper(raw, encoding='utf-8-sig', newline='', errors='replace'), raw, size


def _title_city(city):
    return city.title() if city.isupper() else city


def _row(r):
    """GLEIF-CSV-Zeile → Katalogeintrag (nur die Felder, die SignalDesk braucht)."""
    from .. import legal_forms as lfm
    name = (r.get('Entity.LegalName') or '').strip()
    elf = (r.get('Entity.LegalForm.EntityLegalFormCode') or '').strip().upper()
    hit = lfm.from_elf(elf)
    street = ' '.join(x for x in ((r.get('Entity.LegalAddress.FirstAddressLine') or '').strip(),
                                  (r.get('Entity.LegalAddress.AddressNumber') or '').strip()) if x)
    city = _title_city((r.get('Entity.LegalAddress.City') or '').strip())
    reg = (r.get('Registration.RegistrationStatus') or '').strip().upper()
    active = (r.get('Entity.EntityStatus') or 'ACTIVE').strip().upper() == 'ACTIVE' and reg not in INACTIVE_REG
    return {'lei': (r.get('LEI') or '').strip().upper(), 'name': name[:300], 'name_norm': ident.core_name(name, cache=False)[:300],
            'legal_form': hit[0] if hit else '', 'elf': elf[:8], 'category': (r.get('Entity.EntityCategory') or '').strip()[:30],
            'street': street[:200], 'zip': (r.get('Entity.LegalAddress.PostalCode') or '').strip()[:12], 'city': city[:120],
            'city_norm': ident.norm_city.__wrapped__(city), 'country': (r.get('Entity.LegalAddress.Country') or '').strip().upper()[:2],
            'register_id': (r.get('Entity.RegistrationAuthority.RegistrationAuthorityEntityID') or '').strip()[:60],
            'created': (r.get('Entity.EntityCreationDate') or '')[:10], 'registered': (r.get('Registration.InitialRegistrationDate') or '')[:10],
            'last_update': (r.get('Registration.LastUpdateDate') or '')[:25], 'reg_status': reg[:20], 'active': 1 if active else 0}


COLS = ('lei', 'name', 'name_norm', 'legal_form', 'elf', 'category', 'street', 'zip', 'city', 'city_norm', 'country', 'register_id',
        'created', 'registered', 'last_update', 'reg_status', 'active')
UPSERT = (f"INSERT INTO entities ({', '.join(COLS)}, seen_import, changed_import) VALUES ({', '.join('?' * len(COLS))}, ?, ?) "
          f"ON CONFLICT(lei) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in COLS if c != 'lei')}, "
          "seen_import=excluded.seen_import, changed_import=excluded.changed_import")
TOUCH = 'UPDATE entities SET seen_import=? WHERE lei=?'


def import_file(cat_path, src_path, kind='golden', countries=('DE',), filename='', progress=None, cancelled=None):
    """Streamt eine GLEIF-CSV/ZIP in den Katalog. Gibt das Importprotokoll zurück.
    progress(info) wird je Block aufgerufen; cancelled() → True bricht sauber ab (bisher Eingelesenes bleibt)."""
    if kind not in ('golden', 'delta'):
        raise ValueError('Art: golden (Vollbestand) oder delta (Änderungen).')
    countries = tuple(sorted({c.strip().upper() for c in countries if re.fullmatch(r'[A-Za-z]{2}', c.strip())})) or ('DE',)
    t0 = time.perf_counter()
    conn = connect_catalog(cat_path)
    imp = conn.execute('INSERT INTO imports(filename, kind, countries, source, license, bytes) VALUES (?,?,?,?,?,?)',
                       (filename[:200], kind, ','.join(countries), SOURCE, LICENSE, Path(src_path).stat().st_size)).lastrowid
    conn.commit()
    stats = {'rows': 0, 'inserted': 0, 'updated': 0, 'unchanged': 0, 'deactivated': 0}
    skipped = {'ausland': 0, 'ohne_lei': 0}
    status, error = 'fertig', ''
    stream = raw = None
    try:
        stream, raw, size = _open_text(src_path)
        first = stream.readline()
        delimiter = max(',;\t', key=first.count)
        header = next(csv.reader([first], delimiter=delimiter))
        if not all(c in header for c in REQUIRED):
            raise ValueError('Keine GLEIF-Datei: Spalten „LEI“ und „Entity.LegalName“ fehlen (Golden Copy/Delta im CSV-Format laden).')
        reader = csv.DictReader(stream, fieldnames=header, delimiter=delimiter)
        batch = []

        def flush():
            if not batch:
                return
            have = {r['lei']: (r['last_update'], r['active']) for r in conn.execute(
                f"SELECT lei, last_update, active FROM entities WHERE lei IN ({','.join('?' * len(batch))})", [b['lei'] for b in batch])}
            rows, touch = [], []
            for b in batch:
                old = have.get(b['lei'])
                changed = old is None or old != (b['last_update'], b['active'])
                if old is None:
                    stats['inserted'] += 1
                elif changed:
                    stats['updated'] += 1
                    if old[1] and not b['active']:
                        stats['deactivated'] += 1
                else:
                    stats['unchanged'] += 1
                    touch.append((imp, b['lei']))  # unverändert: nur „gesehen“ vermerken (kein Neuschreiben, kein Volltext-Update)
                    continue
                rows.append((*(b[c] for c in COLS), imp, imp))
            conn.executemany(UPSERT, rows)
            conn.executemany(TOUCH, touch)
            conn.commit()
            batch.clear()
            if progress:
                progress({'rows': stats['rows'], 'bytes': raw.tell() if hasattr(raw, 'tell') and not isinstance(raw, zipfile.ZipFile) else 0,
                          'size': size, **stats})

        for r in reader:
            stats['rows'] += 1
            row = _row(r)
            if not row['lei']:
                skipped['ohne_lei'] += 1
                continue
            if row['country'] not in countries:
                skipped['ausland'] += 1
                continue
            batch.append(row)
            if len(batch) >= BATCH:
                flush()
                if cancelled and cancelled():
                    status, error = 'abgebrochen', 'Import angehalten – bereits Eingelesenes bleibt erhalten; erneut starten setzt fort (je LEI ein Eintrag).'
                    break
        if status == 'fertig':
            flush()
            if kind == 'golden':  # Vollbestand: was nicht mehr enthalten ist, gilt als nicht mehr aktiv (nicht gelöscht)
                n = conn.execute(f"""UPDATE entities SET active=0, changed_import=? WHERE active=1 AND (seen_import IS NULL OR seen_import<>?)
                                     AND country IN ({','.join('?' * len(countries))})""", (imp, imp, *countries)).rowcount
                stats['deactivated'] += n
                conn.commit()
    except (ValueError, csv.Error, zipfile.BadZipFile, UnicodeError, OSError) as exc:
        status, error = 'fehler', str(exc)[:400]
    finally:
        for f in (stream, raw):
            try:
                f and f.close()
            except Exception:  # noqa: BLE001
                pass
    conn.execute('''UPDATE imports SET status=?, rows=?, inserted=?, updated=?, unchanged=?, deactivated=?, skipped_json=?, seconds=?,
                    error=?, finished_at=datetime('now') WHERE id=?''',
                 (status, stats['rows'], stats['inserted'], stats['updated'], stats['unchanged'], stats['deactivated'],
                  json.dumps(skipped), round(time.perf_counter() - t0, 2), error, imp))
    conn.commit()
    out = dict(conn.execute('SELECT * FROM imports WHERE id=?', (imp,)).fetchone())
    conn.close()
    out['skipped'] = json.loads(out.pop('skipped_json'))
    return out


# ---------------------------------------------------------------- Suche & Übernahme

def status(cat_path):
    if not Path(cat_path).exists():
        return {'exists': False, 'entities': 0, 'active': 0, 'imports': [], 'fts': None, 'license': LICENSE, 'source': SOURCE}
    conn = connect_catalog(cat_path)
    try:
        n, act = conn.execute('SELECT COUNT(*), COALESCE(SUM(active), 0) FROM entities').fetchone()
        imports = [dict(r) for r in conn.execute('SELECT * FROM imports ORDER BY id DESC LIMIT 10')]
        for i in imports:
            i['skipped'] = json.loads(i.pop('skipped_json') or '{}')
        last = next((i for i in imports if i['status'] == 'fertig'), None)
        return {'exists': True, 'entities': n, 'active': act, 'imports': imports, 'last_import': last, 'fts': _has_fts(conn),
                'size_mb': round(Path(cat_path).stat().st_size / 1e6, 1), 'license': LICENSE, 'source': SOURCE}
    finally:
        conn.close()


def _fts_query(q):
    toks = [t for t in ident.core_tokens(q) if len(t) >= 2][:6]
    return ' '.join(f'"{t}"*' for t in toks)


def search(cat_path, q='', zip_prefix='', city='', include_inactive=False, limit=50, offset=0):
    if not Path(cat_path).exists():
        return {'total': 0, 'items': [], 'capped': False}
    limit, offset = max(1, min(200, int(limit))), max(0, int(offset))
    where, args, join = [], [], ''
    conn = connect_catalog(cat_path)
    try:
        if q.strip():
            fq = _fts_query(q)
            if not fq:
                raise ValueError('Suchbegriff zu kurz.')
            if _has_fts(conn):
                join = 'JOIN entities_fts f ON f.rowid=e.rowid'
                where.append('entities_fts MATCH ?')
                args.append(fq)
            else:
                for t in ident.core_tokens(q)[:6]:
                    where.append('e.name_norm LIKE ?')
                    args.append(f'%{t}%')
        if zip_prefix:
            if not re.fullmatch(r'\d{1,5}', zip_prefix):
                raise ValueError('PLZ: Ziffern bzw. Anfang, z. B. „70“.')
            where.append('e.zip LIKE ?')
            args.append(zip_prefix + '%')
        if city.strip():
            where.append('e.city_norm=?')
            args.append(ident.norm_city(city))
        if not include_inactive:
            where.append('e.active=1')
        if not (q.strip() or zip_prefix or city.strip()):
            raise ValueError('Bitte Name, PLZ oder Ort angeben.')
        sql = f"FROM entities e {join} WHERE {' AND '.join(where)}"
        total = conn.execute(f'SELECT COUNT(*) FROM (SELECT 1 {sql} LIMIT 5001)', args).fetchone()[0]
        rows = [dict(r) for r in conn.execute(f'SELECT e.* {sql} ORDER BY e.name LIMIT ? OFFSET ?', (*args, limit, offset))]
        for r in rows:
            r.pop('name_norm', None)
            r.pop('city_norm', None)
        return {'total': min(total, 5000), 'capped': total > 5000, 'items': rows}
    finally:
        conn.close()


def to_item(r):
    """Katalogeintrag → Treffer für die Sichtung (gleiches Format wie der GLEIF-Import)."""
    return {'name': r['name'], 'lei': r['lei'], 'external_id': r['lei'], 'street': r['street'], 'zip': r['zip'], 'city': r['city'],
            'register_id': r['register_id'], 'elf': r['elf'], 'legal_form': r['legal_form'],
            'signal_note': f"LEI seit {r['registered'] or 'unbekannt'}, Gründung {r['created'] or 'unbekannt'} (lokaler GLEIF-Katalog)",
            'source_url': f"https://search.gleif.org/#/record/{r['lei']}"}


def items_for(cat_path, leis):
    leis = [str(x).upper() for x in leis if re.fullmatch(r'[A-Za-z0-9]{20}', str(x))][:500]
    if not leis or not Path(cat_path).exists():
        return []
    conn = connect_catalog(cat_path)
    try:
        return [to_item(r) for r in conn.execute(f"SELECT * FROM entities WHERE lei IN ({','.join('?' * len(leis))})", leis)]
    finally:
        conn.close()


def area_items(cat_path, places, limit_per_place=3000):
    """GLEIF-Ersatz für die Sammelsuche: aktive deutsche Firmen in den Orten des Suchgebiets."""
    if not Path(cat_path).exists():
        return []
    conn = connect_catalog(cat_path)
    out = []
    try:
        for pl in places:
            cn = ident.norm_city(pl['name'])
            for r in conn.execute("SELECT * FROM entities WHERE country='DE' AND city_norm=? AND active=1 LIMIT ?", (cn, limit_per_place)):
                out.append({**to_item(r), 'distance_km': pl.get('distance_km')})
        return out
    finally:
        conn.close()


def has_data(cat_path):
    if not Path(cat_path).exists():
        return False
    conn = connect_catalog(cat_path)
    try:
        return bool(conn.execute('SELECT 1 FROM entities WHERE active=1 LIMIT 1').fetchone())
    finally:
        conn.close()


def take_over(conn, db_path, leis, opts=None):
    """Ausgewählte Katalogfirmen in die Sichtung übernehmen – mit Dubletten-Abgleich, nie direkt als Lead."""
    from .. import sweep as sw
    from .. import legal_forms as lfm
    items = items_for(catalog_path(db_path), leis)
    if not items:
        raise ValueError('Keine gültigen LEIs aus dem Katalog gewählt (höchstens 500).')
    opts = opts or {}
    # bewusst ausgewählt: kein Branchen-/Art-Filter (auch Vereine/Einrichtungen), Holding-Filter nur auf Wunsch
    ctx = {'industries': [], 'keywords': [], 'operative': bool(opts.get('operative', False)), 'include_sole': True,
           'org_kinds': tuple(lfm.KIND_LABELS)}
    for it in items:
        it['_industry_matched'] = True  # bewusst ausgewählt – kein Branchenfilter
    label = f'Aus GLEIF-Katalog übernommen · {len(items)} Firmen'
    sid = conn.execute("INSERT INTO sweeps(label, kind, params_json, status, progress_json, finished_at) VALUES (?, 'import', ?, 'fertig', '{}', datetime('now'))",
                       (label, json.dumps({'source': 'gleif_csv', 'catalog': True}, ensure_ascii=False))).lastrowid
    run_id = sw._run_record(conn, 'gleif_csv', sid, {'catalog': len(items)})
    counts = sw.store_items(conn, sid, run_id, 'gleif_csv', items, ctx)
    sw._finish_run(conn, run_id, counts)
    conn.execute('UPDATE sweeps SET progress_json=? WHERE id=?',
                 (json.dumps({'gleif_csv': {'status': 'fertig', 'label': 'GLEIF-Katalog', **counts}}, ensure_ascii=False), sid))
    conn.commit()
    return {'sweep_id': sid, **counts}


def known_leis(conn, leis):
    """Welche LEIs sind schon in der Sichtung (bzw. als Lead übernommen)?"""
    out = {}
    for lei in leis:
        r = conn.execute('''SELECT d.status, d.lead_id, d.duplicate_lead_id FROM discovery_keys k JOIN discovery_candidates d ON d.id=k.candidate_id
                            WHERE k.key=?''', ('lei:' + lei,)).fetchone()
        if r:
            out[lei] = {'status': r['status'], 'lead_id': r['lead_id'] or r['duplicate_lead_id']}
    return out


# ---------------------------------------------------------------- Auftrag & Hochladen

@jobs.handler('catalog_import')
def _job_import(db_path, payload, ctx):
    path = Path(payload['path'])
    if not path.exists():
        return {'_status': 'failed', '_error': 'Hochgeladene Datei fehlt (schon verarbeitet oder gelöscht).'}
    last = [0.0]

    def progress(info):
        if time.monotonic() - last[0] > 2:
            last[0] = time.monotonic()
            ctx.heartbeat(f"{info['rows']:,} Zeilen gelesen · {info['inserted']:,} neu · {info['updated']:,} geändert".replace(',', '.'))
    res = import_file(catalog_path(db_path), path, payload.get('kind', 'golden'), payload.get('countries', ['DE']),
                      payload.get('filename', ''), progress, ctx.cancelled)
    if res['status'] != 'abgebrochen':
        try:
            path.unlink()
        except OSError:
            pass
    if res['status'] == 'fehler':
        return {'_status': 'failed', '_error': res['error'], 'import_id': res['id']}
    return {k: res[k] for k in ('id', 'rows', 'inserted', 'updated', 'unchanged', 'deactivated', 'status', 'seconds')}


@jobs.handler('catalog_import:cancel')
def _job_import_cancel(conn, payload):
    try:
        Path(payload['path']).unlink()
    except OSError:
        pass


def receive_upload(h, db_path, filename):
    """Nimmt den Upload blockweise entgegen und schreibt direkt auf die Platte (nie komplett im Arbeitsspeicher)."""
    raw_len = h.headers.get('Content-Length', '0')
    if not raw_len.isdigit() or not 0 < int(raw_len) <= MAX_UPLOAD:
        raise ValueError(f'Datei leer oder größer als {MAX_UPLOAD // 1024 ** 3} GB.')
    ctype = h.headers.get('Content-Type', '').split(';')[0].strip()
    if ctype not in ('application/zip', 'application/x-zip-compressed', 'text/csv', 'application/octet-stream'):
        raise ValueError('Bitte CSV oder ZIP senden.')
    length = int(raw_len)
    d = upload_dir(db_path)
    d.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(d).free < length * 2 + 200 * 1024 ** 2:
        raise ValueError('Zu wenig freier Speicherplatz für Datei und Katalog.')
    ext = '.zip' if filename.lower().endswith('.zip') or 'zip' in ctype else '.csv'
    target = d / f'{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}{ext}'
    left = length
    try:
        with open(target, 'wb') as f:
            while left:
                chunk = h.rfile.read(min(CHUNK, left))
                if not chunk:
                    raise ValueError('Übertragung abgebrochen.')
                f.write(chunk)
                left -= len(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def start_import(conn, db_path, path, filename, kind, countries, start=True):
    job, _ = jobs.submit(conn, 'catalog_import', f'GLEIF-Katalog: {filename or Path(path).name} ({"Vollbestand" if kind == "golden" else "Delta"})',
                         [{'key': f'import:{Path(path).name}', 'kind': 'catalog_import', 'label': filename or Path(path).name,
                           'payload': {'path': str(path), 'filename': filename, 'kind': kind, 'countries': countries}}],
                         job_key=f'catalog:{Path(path).name}', db_path=db_path, start=start, max_attempts=1)
    return job


def route_catalog(h, conn, method, route, query, db_path):
    if not route.startswith('/api/catalog'):
        return False
    get = lambda k, d='': (query.get(k, [d]) or [d])[0]
    cat = catalog_path(db_path)
    if route == '/api/catalog' and method == 'GET':
        h._send(200, {**status(cat), 'jobs': jobs.list_jobs(conn, kind='catalog_import', limit=5)})
        return True
    if route == '/api/catalog/upload' and method == 'POST':
        kind = get('kind', 'golden')
        if kind not in ('golden', 'delta'):
            raise ValueError('Art: golden oder delta.')
        countries = [c for c in get('countries', 'DE').split(',') if re.fullmatch(r'[A-Za-z]{2}', c.strip())] or ['DE']
        filename = re.sub(r'[^\w.\- ]', '_', get('filename'))[:120]
        path = receive_upload(h, db_path, filename)
        h._send(202, {'job': start_import(conn, db_path, path, filename, kind, countries), 'notice': 'Import läuft als Recherche-Auftrag im Hintergrund.'})
        return True
    if route == '/api/catalog/search' and method == 'GET':
        try:
            res = search(cat, get('q')[:120], get('zip')[:5], get('city')[:80], get('inactive') == '1', get('limit', '50'), get('offset', '0'))
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc) or 'Ungültige Suche.') from exc
        known = known_leis(conn, [r['lei'] for r in res['items']])
        for r in res['items']:
            r['known'] = known.get(r['lei'])
        h._send(200, res)
        return True
    if route == '/api/catalog/take-over' and method == 'POST':
        b = h._body()
        if set(b) - {'leis', 'operative'} or not isinstance(b.get('leis'), list):
            raise ValueError('Erwartet: {leis: [...]}.')
        h._send(200, take_over(conn, db_path, b['leis'], {'operative': b.get('operative') is True}))
        return True
    return False


def main(argv=None):
    """Kommandozeile für sehr große Dateien: python -m sales_tool.research.catalog <datei.zip|csv> --db <signaldesk.sqlite3> [--delta]"""
    import argparse
    ap = argparse.ArgumentParser(description='GLEIF Golden Copy/Delta in den lokalen SignalDesk-Katalog einlesen (Streaming).')
    ap.add_argument('file')
    ap.add_argument('--db', required=True, help='Pfad zur SignalDesk-Datenbank (Katalog liegt daneben)')
    ap.add_argument('--delta', action='store_true')
    ap.add_argument('--countries', default='DE')
    a = ap.parse_args(argv)

    def progress(info):
        print(f"\r{info['rows']:>10,} Zeilen · {info['inserted']:,} neu · {info['updated']:,} geändert", end='', flush=True)
    res = import_file(catalog_path(a.db), a.file, 'delta' if a.delta else 'golden', a.countries.split(','), os.path.basename(a.file), progress)
    print(f"\n{res['status']}: {res['rows']:,} Zeilen in {res['seconds']} s · neu {res['inserted']:,} · geändert {res['updated']:,} · "
          f"unverändert {res['unchanged']:,} · nicht mehr aktiv {res['deactivated']:,} {res['error']}")
    return 0 if res['status'] == 'fertig' else 1


if __name__ == '__main__':
    raise SystemExit(main())
