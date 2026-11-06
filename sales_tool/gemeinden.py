"""Offline-Ortsverzeichnis (v1.14): deutsche Orte mit Koordinate, Kreisschlüssel und Postleitzahlen.

Quelle: GeoNames-Postleitzahlen (CC BY 4.0, Namensnennung „GeoNames (www.geonames.org)“), gebaut mit
``tools/build_gemeinden.py`` → ``data/gemeinden_de.json``. GeoNames enthält keine Einwohnerzahlen; als Größenmaß dient die
Anzahl der Postleitzahlen (Stuttgart 35, Esslingen 5, kleine Gemeinden 1). Wikidata war im Live-Test für Abfragen gesperrt.
Live-Befund 11/2026: Wikidata erlaubt bei Störungen nur 1 Anfrage pro Minute, und die OpenStreetMap-Server sind oft
überlastet. Das Suchgebiet (welche Orte liegen im Umkreis?) braucht deshalb kein Netzwerk mehr.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

DATA = Path(__file__).parent / 'data' / 'gemeinden_de.json'
_STATE = {'rows': None, 'meta': {}}


def _norm(text):
    t = (text or '').casefold().replace('ß', 'ss')
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue')):
        t = t.replace(a, b)
    return re.sub(r'[^a-z0-9]+', ' ', t).strip()


def _ranges(plz):
    out = []
    for part in re.split(r'[,;/]\s*', plz or ''):
        nums = re.findall(r'\d{5}', part)
        if len(nums) == 1:
            out.append((int(nums[0]), int(nums[0])))
        elif len(nums) >= 2 and re.search(r'\d{5}\s*[–\-−]\s*\d{5}', part):
            lo, hi = sorted((int(nums[0]), int(nums[1])))
            if hi - lo <= 2000:  # Unsinnige Spannen (Datenfehler) ignorieren
                out.append((lo, hi))
    return out


def load():
    if _STATE['rows'] is None:
        rows = []
        if DATA.exists():
            raw = json.loads(DATA.read_text(encoding='utf-8'))
            _STATE['meta'] = {k: v for k, v in raw.items() if k != 'rows'}
            for name, kreis, lat, lon, size, plz in raw['rows']:
                rows.append({'name': name, 'kreis': kreis, 'lat': lat, 'lon': lon, 'size': size or 1, 'plz': _ranges(plz), 'key': _norm(name)})
        _STATE['rows'] = rows
    return _STATE['rows']


def available():
    return bool(load())


def meta():
    load()
    return {**_STATE['meta'], 'count': len(_STATE['rows'] or [])}


def by_postcode(plz):
    """Gemeinde zu einer fünfstelligen PLZ (genaue Angabe vor Spanne; bei mehreren die einwohnerstärkste)."""
    if not re.fullmatch(r'\d{5}', plz or ''):
        return None
    n = int(plz)
    hits = [(hi - lo, -g['size'], i, g) for i, g in enumerate(load()) for lo, hi in g['plz'] if lo <= n <= hi]
    return min(hits)[3] if hits else None


def by_name(name, plz=''):
    """Gemeinde zu einem Namen. Gleichnamige Orte (Neustadt …) werden über die PLZ unterschieden, sonst die größte."""
    key = _norm(name)
    if not key:
        return None
    hits = [g for g in load() if g['key'] == key]
    if not hits:
        short = _norm(re.sub(r'\s+(am|an der|an den|bei|im|in der|ob der)\s.*$|\s*\(.*$', '', name or '', flags=re.I))
        hits = [g for g in load() if g['key'] == short or g['key'].startswith(short + ' ')] if short else []
    if plz and len(hits) > 1 and re.fullmatch(r'\d{5}', plz):
        n = int(plz)
        exact = [g for g in hits if any(lo <= n <= hi for lo, hi in g['plz'])]
        near = [g for g in hits if any(abs(lo - n) < 1000 for lo, _ in g['plz'])]
        hits = exact or near or hits
    return max(hits, key=lambda g: g['size']) if hits else None


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def within(lat, lon, km):
    """Alle Gemeinden, deren Mittelpunkt höchstens ``km`` entfernt liegt, mit Entfernung."""
    out = []
    dlat = km / 111.0 + 0.05
    for g in load():
        if abs(g['lat'] - lat) > dlat:
            continue
        d = haversine(lat, lon, g['lat'], g['lon'])
        if d <= km:
            out.append({'name': g['name'], 'lat': g['lat'], 'lon': g['lon'], 'population': 0, 'size': g['size'], 'distance_km': round(d, 1),
                        'kreis': g['kreis'], 'plz': [f'{lo:05d}' if lo == hi else f'{lo:05d}-{hi:05d}' for lo, hi in g['plz']][:6]})
    return out
