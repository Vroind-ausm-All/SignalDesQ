"""Suchgebiet (Sprint B): Ort oder Postleitzahl + Umkreis → Mittelpunkt und Gemeinden im Umkreis.

v1.14 (Live-Test): zuerst das mitgelieferte Ortsverzeichnis (offline, GeoNames CC BY 4.0) – ohne Netzwerk, sofort.
Nur unbekannte Orte/PLZ gehen wie bisher an Nominatim bzw. Wikidata/OpenStreetMap.

- Mittelpunkt: OpenStreetMap-Nominatim (eine Anfrage je neuem Ort/PLZ, dauerhaft zwischengespeichert –
  entspricht der Nominatim-Nutzungsrichtlinie: kein Massen-Geocoding, identifizierender User-Agent).
- Gemeinden im Umkreis: Wikidata (Gemeinden in Deutschland mit Koordinaten), ersatzweise OpenStreetMap (place-Knoten).
- Das Ergebnis wird je (Ort, Umkreis) gespeichert, damit wiederholte Suchen ohne Netzwerk auskommen.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse

from . import gemeinden as gm
from . import lead_finder as lf

NOMINATIM = 'https://nominatim.openstreetmap.org/search?'
RADII = (0, 5, 10, 20, 30, 50, 75)  # 0 = nur der Ort selbst
MAX_PLACES = 60


def init_area(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS geo_cache (
        query TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, label TEXT NOT NULL DEFAULT '',
        postcode TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS search_areas (
        key TEXT PRIMARY KEY, center_json TEXT NOT NULL, places_json TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
    ''')


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_place(text):
    text = (text or '').strip()
    if re.fullmatch(r'\d{5}', text):
        return {'postcode': text, 'city': ''}
    m = re.fullmatch(r'(\d{5})\s+(.{2,60})', text)
    if m:
        return {'postcode': m.group(1), 'city': m.group(2).strip()}
    lf._place(text, 'Ort oder PLZ')
    return {'postcode': '', 'city': text}


def _offline_center(p):
    g = None
    if p['postcode']:
        g = gm.by_postcode(p['postcode'])
        if p['city'] and (not g or gm._norm(g['name']) != gm._norm(p['city'])):
            g = gm.by_name(p['city'], p['postcode']) or g
    elif p['city']:
        g = gm.by_name(p['city'])
    if not g:
        return None
    label = ', '.join(x for x in (p['postcode'], g['name']) if x)
    return {'lat': g['lat'], 'lon': g['lon'], 'label': label, 'postcode': p['postcode'], 'cached': False, 'offline': True, 'name': g['name']}


def geocode(conn, text, ua=None):
    p = parse_place(text)
    off = _offline_center(p)
    if off:
        return off
    key = (p['postcode'] + ' ' + p['city']).strip().casefold()
    row = conn.execute('SELECT * FROM geo_cache WHERE query=?', (key,)).fetchone()
    if row:
        return {'lat': row['lat'], 'lon': row['lon'], 'label': row['label'], 'postcode': row['postcode'], 'cached': True}
    q = {'format': 'json', 'countrycodes': 'de', 'limit': 1, 'addressdetails': 1}
    if p['postcode']:
        q['postalcode'] = p['postcode']
    if p['city']:
        q['city'] = p['city']
    data = lf.FETCH(NOMINATIM + urllib.parse.urlencode(q), ua or lf._user_agent(conn))
    if not isinstance(data, list) or not data:
        raise ValueError(f'„{text}“ wurde nicht gefunden. Bitte Ort oder fünfstellige PLZ prüfen.')
    hit = data[0]
    addr = hit.get('address') or {}
    label = ', '.join(x for x in (addr.get('postcode') or p['postcode'], addr.get('city') or addr.get('town') or addr.get('village') or p['city']) if x) or hit.get('display_name', text)[:80]
    lat, lon = float(hit['lat']), float(hit['lon'])
    conn.execute('INSERT OR REPLACE INTO geo_cache(query, lat, lon, label, postcode) VALUES (?,?,?,?,?)',
                 (key, lat, lon, label[:120], (addr.get('postcode') or p['postcode'])[:10]))
    conn.commit()
    return {'lat': lat, 'lon': lon, 'label': label, 'postcode': addr.get('postcode') or p['postcode'], 'cached': False}


def _wikidata_places(lat, lon, km, ua):
    query = f'''SELECT ?place ?placeLabel ?pop ?coord WHERE {{
  SERVICE wikibase:around {{ ?place wdt:P625 ?coord . bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "{km}" . }}
  ?place wdt:P31/wdt:P279? wd:Q262166 .
  OPTIONAL {{ ?place wdt:P1082 ?pop }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de". }}
}} LIMIT 400'''
    data = lf.wikidata_sparql(query, ua, retries=0)
    out = {}
    for b in data.get('results', {}).get('bindings', []):
        name = b.get('placeLabel', {}).get('value', '')
        m = re.match(r'Point\(([-\d.]+) ([-\d.]+)\)', b.get('coord', {}).get('value', ''))
        if not name or re.fullmatch(r'Q\d+', name) or not m:
            continue
        pop = int(float(b.get('pop', {}).get('value', 0) or 0))
        if name not in out or pop > out[name]['population']:
            out[name] = {'name': name, 'lat': float(m.group(2)), 'lon': float(m.group(1)), 'population': pop}
    return list(out.values())


def _osm_places(lat, lon, km, ua):
    query = f'[out:json][timeout:40];node["place"~"^(city|town|village)$"]["name"](around:{int(km * 1000)},{lat},{lon});out tags center 400;'
    data = lf.overpass(query, ua)
    out = []
    for el in data.get('elements', []):
        t = el.get('tags', {})
        try:
            pop = int(re.sub(r'\D', '', t.get('population', '') or '0') or 0)
        except ValueError:
            pop = 0
        if el.get('lat') is not None:
            out.append({'name': t['name'], 'lat': el['lat'], 'lon': el['lon'], 'population': pop})
    return out


def resolve(conn, place, radius_km):
    if radius_km not in RADII:
        raise ValueError('Umkreis: ' + ', '.join(f'{r} km' for r in RADII) + '.')
    center = geocode(conn, place)
    if gm.available():
        if radius_km:
            places = gm.within(center['lat'], center['lon'], radius_km)
            names = {p['name'] for p in places}  # Ortsteile („Stuttgart Feuerbach“) stecken schon im Ort
            places = [p for p in places if not any(p['name'].startswith(n + ' ') for n in names if n != p['name'])]
        else:
            own = gm.by_name(center.get('name') or parse_place(place)['city'] or center['label'].split(', ')[-1])
            places = [{'name': own['name'], 'lat': own['lat'], 'lon': own['lon'], 'population': 0, 'size': own['size'], 'distance_km': 0.0,
                       'kreis': own['kreis']}] if own else []
        if places:
            places.sort(key=lambda p: (-p['size'], p['distance_km']))  # größere Orte (mehr PLZ) zuerst, dann die nächsten
            total = len(places)
            places = places[:MAX_PLACES]
            return {'center': {**center, 'query': place}, 'radius_km': radius_km, 'places': places, 'places_total': total,
                    'source': 'Ortsverzeichnis offline (GeoNames, CC BY 4.0)' if radius_km else 'nur dieser Ort', 'errors': [], 'cached': False}
    key = f"{round(center['lat'], 3)},{round(center['lon'], 3)}:{radius_km}"
    row = conn.execute("SELECT * FROM search_areas WHERE key=? AND source NOT IN ('nur Mittelpunkt')", (key,)).fetchone()
    if row:
        return {'center': json.loads(row['center_json']), 'radius_km': radius_km, 'places': json.loads(row['places_json']), 'source': row['source'], 'cached': True}
    ua = lf._user_agent(conn)
    places, source, errors = [], '', []
    for name, fn in ((('Wikidata', _wikidata_places), ('OpenStreetMap', _osm_places)) if radius_km else ()):
        try:
            places = fn(center['lat'], center['lon'], radius_km, ua)
            source = name
            if places:
                break
        except lf.SourceError as exc:
            errors.append(f'{name}: {exc}')
    for p in places:
        p['distance_km'] = round(haversine(center['lat'], center['lon'], p['lat'], p['lon']), 1)
    places = [p for p in places if p['distance_km'] <= radius_km]
    places.sort(key=lambda p: (-p['population'], p['distance_km']))
    places = places[:MAX_PLACES]
    if not places:  # ohne Umkreisdaten wenigstens den Ort selbst durchsuchen
        name = parse_place(place)['city'] or center['label'].split(', ')[-1]
        places = [{'name': name, 'lat': center['lat'], 'lon': center['lon'], 'population': 0, 'distance_km': 0.0}]
        source = 'nur dieser Ort' if not radius_km else 'nur Mittelpunkt'
    center_out = {**center, 'query': place}
    if source != 'nur Mittelpunkt':  # v1.14: Notlösung nicht dauerhaft speichern – sonst fehlen später die Nachbarorte
        conn.execute('INSERT OR REPLACE INTO search_areas(key, center_json, places_json, source) VALUES (?,?,?,?)',
                     (key, json.dumps(center_out, ensure_ascii=False), json.dumps(places, ensure_ascii=False), source))
        conn.commit()
    return {'center': center_out, 'radius_km': radius_km, 'places': places, 'source': source, 'errors': errors, 'cached': False}
