"""OpenStreetMap ohne öffentliche Server (2.0.0-dev7): Betriebe aus einer selbst geladenen Datei.

Praxistest 70191: Die öffentlichen Overpass-Server waren bei jedem Versuch überlastet oder nicht erreichbar. Deshalb:

1. Lokaler Auszug (.osm.pbf, z. B. von download.geofabrik.de): einmal laden, einmal einlesen, danach offline suchen.
2. Handexport aus Overpass Turbo (.json / .geojson): Abfrage im Browser ausführen, Ergebnis speichern, hier einlesen.

Gelesen wird ohne Zusatzpaket (PBF ist Protobuf + zlib; beides lässt sich mit der Standardbibliothek lesen).
Gespeichert werden nur benannte Betriebe mit Firmenmerkmal – keine Personen, keine Wohnadressen.
Lizenz der Daten: © OpenStreetMap-Mitwirkende, ODbL 1.0 – die Quelle wird bei jeder Übernahme genannt.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import struct
import zlib
from pathlib import Path

from .. import gemeinden as gm
from .. import industries as ind

BUSINESS_KEYS = ('craft', 'office', 'shop', 'amenity', 'healthcare', 'industrial', 'tourism', 'leisure')
# benannte Orte, die keine Betriebe sind
SKIP = {'amenity': {'parking', 'parking_space', 'parking_entrance', 'bench', 'shelter', 'toilets', 'drinking_water', 'fountain', 'place_of_worship',
                    'school', 'kindergarten', 'university', 'college', 'library', 'townhall', 'police', 'fire_station', 'post_box', 'recycling',
                    'waste_basket', 'bicycle_parking', 'grave_yard', 'hunting_stand', 'vending_machine', 'atm', 'telephone', 'clock', 'bbq',
                    'community_centre', 'social_facility', 'public_bookcase', 'charging_station', 'taxi', 'bus_station', 'ferry_terminal',
                    'courthouse', 'prison', 'embassy', 'monastery', 'public_building', 'parcel_locker', 'post_office', 'waste_disposal'},
        'tourism': {'information', 'viewpoint', 'artwork', 'picnic_site', 'attraction', 'memorial', 'museum', 'zoo', 'theme_park', 'camp_pitch'},
        'leisure': {'playground', 'park', 'pitch', 'garden', 'nature_reserve', 'picnic_table', 'firepit', 'track', 'common', 'dog_park',
                    'bird_hide', 'outdoor_seating', 'slipway', 'swimming_area', 'bandstand'},
        'office': {'government', 'diplomatic', 'political_party', 'religion', 'association', 'ngo'},
        'shop': {'vacant'}}
MAX_BLOB = 64 * 1024 * 1024
INSERT_PLACE = ('INSERT OR REPLACE INTO osm_places(osm_id, name, kind_key, kind, street, zip, city, website, phone, opening_hours, lat, lon, import_id) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')
LICENSE = '© OpenStreetMap-Mitwirkende, ODbL 1.0'


def init_osm_local(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS osm_places (
        osm_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind_key TEXT NOT NULL, kind TEXT NOT NULL,
        street TEXT NOT NULL DEFAULT '', zip TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
        website TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', opening_hours TEXT NOT NULL DEFAULT '',
        lat REAL, lon REAL, import_id INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_osm_places_zip ON osm_places(zip);
      CREATE INDEX IF NOT EXISTS idx_osm_places_geo ON osm_places(lat, lon);
      CREATE TABLE IF NOT EXISTS osm_imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'läuft',
        elements INTEGER NOT NULL DEFAULT 0, places INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT '', seconds REAL NOT NULL DEFAULT 0
      );
    ''')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(osm_places)')}
    if 'zip_guess' not in cols:  # 2.0.0-dev8: PLZ aus der Nachbarschaft geschätzt (für Einträge ohne PLZ-Angabe)
        conn.execute("ALTER TABLE osm_places ADD COLUMN zip_guess TEXT NOT NULL DEFAULT ''")
    conn.execute('CREATE INDEX IF NOT EXISTS idx_osm_places_guess ON osm_places(zip_guess)')


# ---------------------------------------------------------------- Protobuf (nur was PBF braucht)

def _varint(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, pos
        shift += 7


def _fields(buf):
    """Felder einer Protobuf-Nachricht: (Nummer, Drahttyp, Wert). Längenbegrenzte Werte als memoryview-Ausschnitt."""
    pos, end = 0, len(buf)
    while pos < end:
        key, pos = _varint(buf, pos)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, pos = _varint(buf, pos)
        elif wire == 2:
            ln, pos = _varint(buf, pos)
            val = buf[pos:pos + ln]
            pos += ln
        elif wire == 1:
            val = buf[pos:pos + 8]
            pos += 8
        elif wire == 5:
            val = buf[pos:pos + 4]
            pos += 4
        else:
            raise ValueError('Unbekanntes Protobuf-Feld – keine gültige PBF-Datei.')
        yield num, wire, val


def _packed(buf):
    out, pos, end = [], 0, len(buf)
    while pos < end:
        v, pos = _varint(buf, pos)
        out.append(v)
    return out


def _zigzag(v):
    return (v >> 1) ^ -(v & 1)


def _blobs(fh):
    """(Typ, entpackte Daten) je Block der PBF-Datei."""
    while True:
        head = fh.read(4)
        if not head:
            return
        if len(head) < 4:
            raise ValueError('Datei endet mitten in einem Block.')
        (hlen,) = struct.unpack('>I', head)
        if not 0 < hlen <= 64 * 1024:
            raise ValueError('Keine gültige PBF-Datei (Kopf zu groß).')
        btype, size = '', 0
        for num, _w, val in _fields(memoryview(fh.read(hlen))):
            if num == 1:
                btype = bytes(val).decode('ascii', 'replace')
            elif num == 3:
                size = val
        if not 0 < size <= MAX_BLOB:
            raise ValueError('Keine gültige PBF-Datei (Blockgröße).')
        raw = fh.read(size)
        if len(raw) < size:
            raise ValueError('Datei endet mitten in einem Block.')
        data = None
        for num, _w, val in _fields(memoryview(raw)):
            if num == 1:
                data = bytes(val)
            elif num == 3:
                data = zlib.decompress(bytes(val))
            elif num in (4, 5, 6, 7):
                raise ValueError('Diese PBF-Datei nutzt eine Kompression, die SignalDesk nicht liest (nur zlib). Bitte den Auszug von Geofabrik verwenden.')
        if data is None:
            raise ValueError('Block ohne Daten.')
        if len(data) > MAX_BLOB:
            raise ValueError('Block zu groß.')
        yield btype, data


def iter_pbf(path, progress=None, way_refs=None):
    """Alle Knoten und Wege mit Merkmalen: (art, id, tags, lat, lon). Wege haben keine Koordinaten (lat/lon None).
    Mit way_refs (dict) wird je benanntem Weg die Kennung seines ersten Knotens notiert – für die Lage des Umrisses."""
    seen = 0
    with open(path, 'rb') as fh:
        for btype, data in _blobs(fh):
            if btype != 'OSMData':
                continue
            block = memoryview(data)
            strings, groups, gran, lat_off, lon_off = [], [], 100, 0, 0
            for num, _w, val in _fields(block):
                if num == 1:
                    strings = [bytes(v) for n, _x, v in _fields(val) if n == 1]
                elif num == 2:
                    groups.append(val)
                elif num == 17:
                    gran = val
                elif num == 19:
                    lat_off = val
                elif num == 20:
                    lon_off = val
            if b'name' not in strings:  # ohne das Wort „name“ enthält der Block keinen benannten Betrieb
                seen += 1
                continue
            text = [s.decode('utf-8', 'replace') for s in strings]
            for group in groups:
                for num, _w, val in _fields(group):
                    if num == 2:  # DenseNodes
                        ids = lats = lons = kv = None
                        for n, _x, v in _fields(val):
                            if n == 1:
                                ids = v
                            elif n == 8:
                                lats = v
                            elif n == 9:
                                lons = v
                            elif n == 10:
                                kv = v
                        if not kv or not ids:
                            continue
                        kvs = _packed(kv)
                        if not any(kvs):
                            continue
                        idl, latl, lonl = _packed(ids), _packed(lats), _packed(lons)
                        nid = lat = lon = 0
                        p = 0
                        for i in range(len(idl)):
                            nid += _zigzag(idl[i])
                            lat += _zigzag(latl[i])
                            lon += _zigzag(lonl[i])
                            if p < len(kvs) and kvs[p]:
                                tags = {}
                                while p < len(kvs) and kvs[p]:
                                    tags[text[kvs[p]]] = text[kvs[p + 1]]
                                    p += 2
                                if 'name' in tags:
                                    yield 'node', nid, tags, 1e-9 * (lat_off + gran * lat), 1e-9 * (lon_off + gran * lon)
                            p += 1
                    elif num == 1:  # einzelner Knoten
                        nid = lat = lon = 0
                        keys = vals = ()
                        for n, _x, v in _fields(val):
                            if n == 1:
                                nid = _zigzag(v)
                            elif n == 2:
                                keys = _packed(v)
                            elif n == 3:
                                vals = _packed(v)
                            elif n == 8:
                                lat = _zigzag(v)
                            elif n == 9:
                                lon = _zigzag(v)
                        tags = {text[k]: text[v] for k, v in zip(keys, vals)}
                        if 'name' in tags:
                            yield 'node', nid, tags, 1e-9 * (lat_off + gran * lat), 1e-9 * (lon_off + gran * lon)
                    elif num == 3:  # Weg (z. B. Gebäudeumriss eines Betriebs)
                        wid, keys, vals, refs = 0, (), (), None
                        for n, _x, v in _fields(val):
                            if n == 1:
                                wid = v
                            elif n == 2:
                                keys = _packed(v)
                            elif n == 3:
                                vals = _packed(v)
                            elif n == 8:
                                refs = v
                        if keys:
                            tags = {text[k]: text[v] for k, v in zip(keys, vals)}
                            if 'name' in tags:
                                if way_refs is not None and refs is not None and len(refs):
                                    way_refs[wid] = _zigzag(_varint(refs, 0)[0])
                                yield 'way', wid, tags, None, None
            seen += 1
            if progress and seen % 200 == 0:
                progress(seen)


def node_coords(path, wanted):
    """Koordinaten der gewünschten Knoten (zweiter Durchlauf durch die Datei): {knoten_id: (lat, lon)}."""
    found, wanted = {}, set(wanted)
    if not wanted:
        return found
    with open(path, 'rb') as fh:
        for btype, data in _blobs(fh):
            if btype != 'OSMData':
                continue
            groups, gran, lat_off, lon_off = [], 100, 0, 0
            for num, _w, val in _fields(memoryview(data)):
                if num == 2:
                    groups.append(val)
                elif num == 17:
                    gran = val
                elif num == 19:
                    lat_off = val
                elif num == 20:
                    lon_off = val
            for group in groups:
                for num, _w, val in _fields(group):
                    if num != 2:
                        continue
                    ids = lats = lons = None
                    for n, _x, v in _fields(val):
                        if n == 1:
                            ids = v
                        elif n == 8:
                            lats = v
                        elif n == 9:
                            lons = v
                    if not ids:
                        continue
                    nid, hits = 0, []
                    for i, d in enumerate(_packed(ids)):
                        nid += _zigzag(d)
                        if nid in wanted:
                            hits.append((i, nid))
                    if not hits:
                        continue
                    latl, lonl = _packed(lats), _packed(lons)
                    lat = lon = 0
                    it = iter(hits)
                    nxt = next(it)
                    for i in range(len(latl)):
                        lat += _zigzag(latl[i])
                        lon += _zigzag(lonl[i])
                        if i == nxt[0]:
                            found[nxt[1]] = (1e-9 * (lat_off + gran * lat), 1e-9 * (lon_off + gran * lon))
                            nxt = next(it, None)
                            if nxt is None:
                                break
            if len(found) == len(wanted):
                break
    return found


def guess_postcodes(conn, max_km=0.25):
    """Einträge ohne PLZ-Angabe bekommen die PLZ des nächsten Eintrags mit PLZ, wenn er höchstens 250 m entfernt liegt.
    Das ist eine Schätzung (an PLZ-Grenzen kann sie danebenliegen) und wird überall als solche gekennzeichnet."""
    grid = {}
    for r in conn.execute("SELECT lat, lon, zip FROM osm_places WHERE zip<>'' AND lat IS NOT NULL"):
        grid.setdefault((int(r['lat'] * 400), int(r['lon'] * 400)), []).append((r['lat'], r['lon'], r['zip']))
    conn.execute("UPDATE osm_places SET zip_guess='' WHERE zip_guess<>''")
    updates = []
    for r in conn.execute("SELECT osm_id, lat, lon FROM osm_places WHERE zip='' AND lat IS NOT NULL").fetchall():
        cy, cx = int(r['lat'] * 400), int(r['lon'] * 400)
        best, best_d = '', max_km
        for dy in (-1, 0, 1):
            for dx in (-2, -1, 0, 1, 2):
                for lat, lon, z in grid.get((cy + dy, cx + dx), ()):
                    d = gm.haversine(r['lat'], r['lon'], lat, lon)
                    if d <= best_d:
                        best, best_d = z, d
        if best:
            updates.append((best, r['osm_id']))
    conn.executemany('UPDATE osm_places SET zip_guess=? WHERE osm_id=?', updates)
    conn.commit()
    return len(updates)


def iter_json(path):
    """Overpass-Export (JSON mit „elements“) oder GeoJSON aus Overpass Turbo."""
    if Path(path).stat().st_size > 300 * 1024 * 1024:
        raise ValueError('JSON-Datei größer als 300 MB – für so große Gebiete bitte den PBF-Auszug verwenden.')
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('Datei ist kein gültiges JSON.') from exc
    if isinstance(data, dict) and isinstance(data.get('elements'), list):
        for el in data['elements']:
            if isinstance(el, dict) and isinstance(el.get('tags'), dict):
                c = el.get('center') or {}
                yield str(el.get('type', 'node')), el.get('id', 0), el['tags'], el.get('lat', c.get('lat')), el.get('lon', c.get('lon'))
    elif isinstance(data, dict) and isinstance(data.get('features'), list):
        for f in data['features']:
            props = (f or {}).get('properties') or {}
            tags = props.get('tags') if isinstance(props.get('tags'), dict) else {k: v for k, v in props.items() if not k.startswith('@') and isinstance(v, str)}
            ident = str(props.get('@id') or f.get('id') or '')
            typ, _, num = ident.partition('/')
            geo = (f or {}).get('geometry') or {}
            lat = lon = None
            if geo.get('type') == 'Point' and isinstance(geo.get('coordinates'), list) and len(geo['coordinates']) >= 2:
                lon, lat = geo['coordinates'][0], geo['coordinates'][1]
            yield typ or 'node', num or ident, tags, lat, lon
    else:
        raise ValueError('Unbekanntes Format: erwartet wird der Export „Rohdaten (OSM JSON)“ oder „GeoJSON“ aus Overpass Turbo.')


# ---------------------------------------------------------------- Betrieb aus Merkmalen

def _clean(v, n):
    return re.sub(r'[\x00-\x1f]+', ' ', str(v or '')).strip()[:n]


def place_from_tags(typ, ident, tags, lat, lon):
    """Benannter Betrieb oder None. Keine Personen, keine reinen Adressen, keine öffentlichen Einrichtungen."""
    name = _clean(tags.get('name'), 200)
    if not name:
        return None
    key = next((k for k in BUSINESS_KEYS if tags.get(k) and tags[k] != 'no' and tags[k] not in SKIP.get(k, ())), None)
    if not key:
        return None
    if tags.get('disused') == 'yes' or tags.get('abandoned') == 'yes' or any(k.startswith(('disused:', 'abandoned:', 'was:')) for k in tags):
        return None
    from ..lead_finder import clean_website
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    zip_ = _clean(tags.get('addr:postcode'), 10)
    return {'osm_id': f'{typ}/{ident}', 'name': name, 'kind_key': key, 'kind': _clean(tags[key], 80),
            'street': ' '.join(x for x in (_clean(tags.get('addr:street'), 150), _clean(tags.get('addr:housenumber'), 20)) if x),
            'zip': zip_ if re.fullmatch(r'\d{5}', zip_) else '', 'city': _clean(tags.get('addr:city'), 120),
            'website': clean_website(tags.get('website') or tags.get('contact:website')) or '',
            'phone': _clean(tags.get('phone') or tags.get('contact:phone'), 60), 'opening_hours': _clean(tags.get('opening_hours'), 200),
            'lat': lat, 'lon': lon}


def detect_kind(path, filename=''):
    name = (filename or str(path)).lower()
    with open(path, 'rb') as fh:
        head = fh.read(64)
    if b'OSMHeader' in head or name.endswith('.pbf'):
        return 'pbf'
    if head.lstrip()[:1] in (b'{', b'[') or name.endswith(('.json', '.geojson')):
        return 'json'
    raise ValueError('Unbekanntes Dateiformat. Erwartet: .osm.pbf (Auszug) oder .json / .geojson (Export aus Overpass Turbo).')


def import_file(conn, path, filename='', progress=None, cancelled=None):
    """Liest Betriebe aus der Datei in den lokalen Bestand. Vorhandene Einträge mit gleicher OSM-Kennung werden ersetzt."""
    started = dt.datetime.now()
    kind = detect_kind(path, filename)
    imp = conn.execute('INSERT INTO osm_imports(filename, kind) VALUES (?,?)', (filename or Path(path).name, kind)).lastrowid
    conn.commit()
    elements = places = located = guessed = 0
    try:
        rows = []
        way_refs, way_first = {}, {}
        source = iter_pbf(path, way_refs=way_refs) if kind == 'pbf' else iter_json(path)
        for typ, ident, tags, lat, lon in source:
            elements += 1
            p = place_from_tags(typ, ident, tags, lat, lon)
            if typ == 'way' and ident in way_refs:
                ref = way_refs.pop(ident)
                if p:
                    way_first[p['osm_id']] = ref
            if p:
                places += 1
                rows.append((p['osm_id'], p['name'], p['kind_key'], p['kind'], p['street'], p['zip'], p['city'], p['website'], p['phone'],
                             p['opening_hours'], p['lat'], p['lon'], imp))
            if len(rows) >= 2000:
                conn.executemany(INSERT_PLACE, rows)
                conn.commit()
                rows = []
                if progress:
                    progress({'elements': elements, 'places': places})
                if cancelled and cancelled():
                    raise InterruptedError
        conn.executemany(INSERT_PLACE, rows)
        conn.commit()
        located = 0
        if way_first:  # Gebäudeumrisse: Lage aus dem ersten Punkt des Umrisses (zweiter Durchlauf durch die Datei)
            if progress:
                progress({'elements': elements, 'places': places, 'phase': 'Lage der Gebäudeumrisse'})
            coords = node_coords(path, way_first.values())
            upd = [(coords[ref][0], coords[ref][1], oid) for oid, ref in way_first.items() if ref in coords]
            conn.executemany('UPDATE osm_places SET lat=?, lon=? WHERE osm_id=? AND lat IS NULL', upd)
            located = len(upd)
        guessed = guess_postcodes(conn)
        status, error = 'fertig', ''
    except InterruptedError:
        status, error = 'abgebrochen', ''
    except (ValueError, zlib.error, struct.error, IndexError, KeyError, UnicodeDecodeError) as exc:
        status = 'fehler'
        error = str(exc) if isinstance(exc, ValueError) else 'Datei beschädigt oder kein gültiger OpenStreetMap-Auszug.'
    secs = round((dt.datetime.now() - started).total_seconds(), 1)
    conn.execute("UPDATE osm_imports SET status=?, elements=?, places=?, error=?, finished_at=datetime('now'), seconds=? WHERE id=?",
                 (status, elements, places, error, secs, imp))
    conn.commit()
    return {'id': imp, 'kind': kind, 'status': status, 'elements': elements, 'places': places, 'ways_located': located,
            'postcodes_guessed': guessed, 'error': error, 'seconds': secs}


# ---------------------------------------------------------------- Suche im lokalen Bestand

def has_data(conn):
    return bool(conn.execute('SELECT 1 FROM osm_places LIMIT 1').fetchone())


def status(conn):
    n = conn.execute("SELECT COUNT(*) AS n, SUM(zip<>'') AS z, SUM(website<>'') AS w, SUM(phone<>'') AS p, SUM(opening_hours<>'') AS o FROM osm_places").fetchone()
    imports = [dict(r) for r in conn.execute('SELECT * FROM osm_imports ORDER BY id DESC LIMIT 5')]
    g = conn.execute("SELECT SUM(zip_guess<>'') AS g, SUM(lat IS NULL) AS nolat FROM osm_places").fetchone()
    return {'places': n['n'] or 0, 'with_zip_guess': g['g'] or 0, 'without_location': g['nolat'] or 0, 'with_zip': n['z'] or 0, 'with_website': n['w'] or 0, 'with_phone': n['p'] or 0, 'with_hours': n['o'] or 0,
            'imports': imports, 'license': LICENSE,
            'notice': 'Der lokale Bestand ist so aktuell wie die eingelesene Datei. Für frische Daten einen neuen Auszug einlesen.'}


def _matches_industry(row, keys):
    if not keys:
        return True, ''
    for k in keys:
        for a, b in ind.INDUSTRIES[k]['osm']:
            if row['kind_key'] == a and (b is None or row['kind'] == b):
                return True, k
    return False, ''


def _plz_ranges(place_name):
    try:
        g = gm.by_name(place_name)
    except Exception:  # noqa: BLE001 – Ortsverzeichnis fehlt
        g = None
    return [(lo, hi) for lo, hi in (g or {}).get('plz', [])]


def area_items(conn, ctx, area, haversine, limit=20000):
    """Betriebe des Suchgebiets aus dem lokalen Bestand, im Format der Sammelsuche.

    - PLZ + „nur dieser Ort“: genau diese PLZ (Einträge ohne PLZ-Angabe lassen sich keiner PLZ zuordnen und fehlen).
    - Ortsname + „nur dieser Ort“: alle PLZ der Gemeinde, dazu Einträge mit passendem Ortsnamen; Einträge ganz ohne Adresse
      nur, wenn sie höchstens 5 km von der Ortsmitte liegen.
    - Umkreis: nach Entfernung von der Mitte.
    Gibt (items, zähler) zurück."""
    c = area['center']
    radius = ctx['radius_km']
    counts = {'no_address': 0}
    if ctx.get('postcode_only'):
        rows = conn.execute("SELECT * FROM osm_places WHERE zip=? OR (zip='' AND zip_guess=?) LIMIT ?",
                            (ctx['postcode_only'], ctx['postcode_only'], limit)).fetchall()
        counts['guessed'] = sum(1 for r in rows if not r['zip'])
    else:
        r = radius if radius else 12  # „nur dieser Ort“: grob vorfiltern, genau wird unten geprüft
        dlat, dlon = r / 111.0, r / (111.0 * max(0.2, math.cos(math.radians(c['lat']))))
        ranges = _plz_ranges(c.get('name') or '') if not radius else []
        where, args = '(lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?)', [c['lat'] - dlat, c['lat'] + dlat, c['lon'] - dlon, c['lon'] + dlon]
        for lo, hi in ranges[:40]:
            where += ' OR (zip BETWEEN ? AND ?)'
            args += [f'{lo:05d}', f'{hi:05d}']
        # Wege (Gebäudeumrisse) haben im Auszug keine Koordinaten – sie zählen über ihren Ortsnamen
        names_sql = sorted({p['name'] for p in area['places']})[:200]
        if names_sql:
            where += f" OR (lat IS NULL AND city IN ({','.join('?' * len(names_sql))}))"
            args += names_sql
        rows = conn.execute(f'SELECT * FROM osm_places WHERE {where} LIMIT ?', (*args, limit)).fetchall()
    names = {p['name'].casefold() for p in area['places']}
    items = []
    for row in rows:
        ok, ikey = _matches_industry(row, ctx.get('industries') or [])
        if not ok:
            continue
        dist = round(haversine(c['lat'], c['lon'], row['lat'], row['lon']), 1) if row['lat'] is not None else None
        if not ctx.get('postcode_only'):
            if radius:
                if (dist is None and row['city'].casefold() not in names) or (dist is not None and dist > radius):
                    continue
            else:
                in_plz = bool(row['zip']) and any(lo <= int(row['zip']) <= hi for lo, hi in ranges)
                in_city = bool(row['city']) and row['city'].casefold() in names
                bare = not row['zip'] and not row['city']
                if not (in_plz or in_city or (bare and dist is not None and dist <= 5)):
                    continue
                if bare:
                    counts['no_address'] += 1
        items.append({'external_id': row['osm_id'], 'name': row['name'], 'website': row['website'], 'street': row['street'], 'zip': row['zip'],
                      'city': row['city'], 'industry': row['kind'].replace('_', ' '), 'industry_key': ikey, '_industry_matched': bool(ikey),
                      '_in_postcode': bool(ctx.get('postcode_only')) and not row['zip'],  # PLZ aus der Nachbarschaft geschätzt
                      'distance_km': dist, 'source_url': f"https://www.openstreetmap.org/{row['osm_id']}"})
    return items, counts


def turbo_query(place, postcode_only='', radius_km=0, lat=None, lon=None):
    """Fertige Abfrage für Overpass Turbo (im Browser ausführen, dann exportieren) samt Link."""
    import urllib.parse
    sel = ''.join(f'  nwr["{k}"]["name"]{{w}};\n' for k in ('craft', 'office', 'shop', 'healthcare', 'industrial', 'amenity'))
    if postcode_only:
        head, where = f'area["boundary"="postal_code"]["postal_code"="{postcode_only}"]->.a;\n', '(area.a)'
    elif radius_km and lat is not None:
        head, where = '', f'(around:{int(radius_km * 1000)},{lat:.5f},{lon:.5f})'
    else:
        safe = re.sub(r'["\\\\\n\r]', '', place)[:80]
        head, where = f'area["boundary"="administrative"]["name"="{safe}"]["admin_level"~"^(6|8)$"]->.a;\n', '(area.a)'
    query = f'[out:json][timeout:120];\n{head}(\n{sel.replace("{w}", where)});\nout center tags;'
    return {'query': query, 'url': 'https://overpass-turbo.eu/?Q=' + urllib.parse.quote(query) + '&R'}


# ---------------------------------------------------------------- Einlesen als Hintergrund-Auftrag, Routen

def _register():
    from . import jobs

    @jobs.handler('osm_import')
    def _job_import(db_path, payload, ctx):
        from ..model import connect
        path = Path(payload['path'])
        if not path.exists():
            return {'_status': 'failed', '_error': 'Hochgeladene Datei fehlt (schon verarbeitet oder gelöscht).'}
        with connect(db_path) as conn:
            res = import_file(conn, path, payload.get('filename', ''),
                              lambda i: ctx.heartbeat(f"{i['elements']:,} benannte Einträge gelesen · {i['places']:,} Betriebe".replace(',', '.')),
                              ctx.cancelled)
        path.unlink(missing_ok=True)
        if res['status'] == 'fehler':
            return {'_status': 'failed', '_error': res['error'], 'import_id': res['id']}
        return res

    @jobs.handler('osm_import:cancel')
    def _job_cancel(conn, payload):
        Path(payload['path']).unlink(missing_ok=True)


_register()
MAX_UPLOAD = 4 * 1024 ** 3


def receive_upload(h, db_path, filename):
    """Upload blockweise auf die Platte (nie ganz im Arbeitsspeicher)."""
    import shutil
    import uuid
    from .catalog import upload_dir
    raw_len = h.headers.get('Content-Length', '0')
    if not raw_len.isdigit() or not 0 < int(raw_len) <= MAX_UPLOAD:
        raise ValueError('Datei leer oder größer als 4 GB.')
    low = filename.lower()
    ext = '.osm.pbf' if low.endswith('.pbf') else ('.json' if low.endswith(('.json', '.geojson')) else '')
    if not ext:
        raise ValueError('Bitte eine .osm.pbf-Datei (Auszug) oder .json / .geojson (Export aus Overpass Turbo) wählen.')
    length = int(raw_len)
    d = upload_dir(db_path)
    d.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(d).free < length + 300 * 1024 ** 2:
        raise ValueError('Zu wenig freier Speicherplatz.')
    target = d / f'osm-{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}{ext}'
    left = length
    try:
        with open(target, 'wb') as f:
            while left:
                chunk = h.rfile.read(min(1024 * 1024, left))
                if not chunk:
                    raise ValueError('Übertragung abgebrochen.')
                f.write(chunk)
                left -= len(chunk)
        detect_kind(target, filename)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def start_import(conn, db_path, path, filename, start=True):
    from . import jobs
    job, _ = jobs.submit(conn, 'osm_import', f'OpenStreetMap-Auszug: {filename or Path(path).name}',
                         [{'key': f'osm:{Path(path).name}', 'kind': 'osm_import', 'label': filename or Path(path).name,
                           'payload': {'path': str(path), 'filename': filename}}],
                         job_key=f'osm:{Path(path).name}', db_path=db_path, start=start, max_attempts=1)
    return job


HOWTO = [
    {'key': 'auszug', 'title': 'Lokaler Auszug (empfohlen für eine ganze Stadt oder Region)', 'effort': 'einmal etwa 10 Minuten, danach offline',
     'steps': ['Auf download.geofabrik.de die Region öffnen: Europe → Germany → dein Bundesland → Regierungsbezirk.',
               'Die Datei „…-latest.osm.pbf“ herunterladen (ein Regierungsbezirk hat meist 100–300 MB).',
               'Hier unter „Datei einlesen“ auswählen. SignalDesk liest nur benannte Betriebe heraus; das dauert einige Minuten.',
               'Fertig: Jede Firmensuche nutzt ab jetzt diesen Bestand – ohne Internet, ohne Wartezeit. Für frische Daten später neu einlesen.']},
    {'key': 'turbo', 'title': 'Handexport aus Overpass Turbo (für eine PLZ oder einen Ort)', 'effort': 'etwa 2 Minuten je Gebiet',
     'steps': ['Ort oder PLZ oben eintragen und unten „Abfrage in Overpass Turbo öffnen“ anklicken.',
               'Im Browser auf „Ausführen“ klicken. Meldet die Seite Überlastung: einen Moment warten und erneut ausführen.',
               'Über „Export“ → „Rohdaten“ oder „GeoJSON“ die Datei speichern.',
               'Die Datei hier unter „Datei einlesen“ auswählen.']},
    {'key': 'online', 'title': 'Online abfragen (wie bisher)', 'effort': 'kein Aufwand, aber oft überlastet',
     'steps': ['Bei den Quellen „OpenStreetMap jetzt online abfragen“ ankreuzen. Antwortet kein Server, bleibt die Suche ohne OpenStreetMap-Treffer.']},
]


def route(h, conn, method, path, query, db_path):
    if not path.startswith('/api/osm'):
        return False
    get = lambda k, d='': (query.get(k, [d]) or [d])[0]
    if path == '/api/osm' and method == 'GET':
        from . import jobs
        from .. import area as ar
        place, radius = get('place')[:80].strip(), get('radius', '0')
        turbo = None
        if place:
            try:
                r = int(radius) if radius.isdigit() else 0
                pc = place if re.fullmatch(r'\d{5}', place) and not r else ''
                center = ar.geocode(conn, place) if r and not pc else {}
                turbo = turbo_query(center.get('name') or place, pc, r, center.get('lat'), center.get('lon'))
            except Exception:  # noqa: BLE001 – Ort nicht bestimmbar: Anleitung ohne fertige Abfrage
                turbo = None
        h._send(200, {**status(conn), 'howto': HOWTO, 'turbo': turbo, 'jobs': jobs.list_jobs(conn, kind='osm_import', limit=3)})
        return True
    if path == '/api/osm/upload' and method == 'POST':
        filename = re.sub(r'[^\w.\- ]', '_', get('filename'))[:120]
        target = receive_upload(h, db_path, filename)
        h._send(202, {'job': start_import(conn, db_path, target, filename), 'notice': 'Die Datei wird im Hintergrund eingelesen.'})
        return True
    if path == '/api/osm/places' and method == 'DELETE':
        n = conn.execute('DELETE FROM osm_places').rowcount
        conn.commit()
        h._send(200, {'deleted': n})
        return True
    return False
