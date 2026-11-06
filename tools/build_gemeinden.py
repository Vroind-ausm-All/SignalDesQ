"""Baut sales_tool/data/gemeinden_de.json aus dem GeoNames-Postleitzahlen-Export für Deutschland.

Quelle: https://download.geonames.org/export/zip/DE.zip – Lizenz CC BY 4.0, Namensnennung „GeoNames (www.geonames.org)“.
Aufruf:  python tools/build_gemeinden.py DE.zip

Je Ort: Name, Kreisschlüssel, mittlere Koordinate, Anzahl Postleitzahlen (als Größenmaß – GeoNames enthält keine
Einwohnerzahlen) und die Postleitzahlen. Ortsteil-Einträge wie „Stuttgart Stuttgart-Mitte“ werden dem Ort zugeordnet.
"""
import collections
import datetime as dt
import json
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'sales_tool' / 'data' / 'gemeinden_de.json'


def build(zip_path):
    text = zipfile.ZipFile(zip_path).read('DE.txt').decode('utf-8')
    rows = [line.split('\t') for line in text.splitlines() if line.strip()]
    # Echte Orte haben eine Genauigkeitsangabe (1/4/6). Zeilen ohne Angabe sind entweder Ortsteile („Stuttgart Stuttgart-Mitte“)
    # oder Großkunden-Postleitzahlen („Daimler AG“, „Stadtverwaltung“, „Finanzamt“) – Letztere werden ausgelassen.
    by_kreis = collections.defaultdict(set)
    for r in rows:
        if (r[11] if len(r) > 11 else '').strip():
            by_kreis[r[8]].add(r[2])
    places = collections.OrderedDict()
    skipped = 0
    for r in rows:
        plz, name, kreis, lat, lon = r[1], r[2], r[8], float(r[9]), float(r[10])
        base = name if name in by_kreis[kreis] else None
        if base is None:  # Ortsteil eines bekannten Orts im selben Kreis?
            base = next((c for c in sorted(by_kreis[kreis], key=len, reverse=True) if name.startswith(c + ' ')), None)
        if base is None:
            skipped += 1
            continue
        p = places.setdefault((base, kreis), {'plz': set(), 'pts': []})
        p['plz'].add(plz)
        if base == name:
            p['pts'].append((lat, lon))
        elif not p['pts']:
            p.setdefault('sub', []).append((lat, lon))
    out = []
    for (name, kreis), p in places.items():
        pts = p['pts'] or p.get('sub') or []
        if not pts:
            continue
        lat = round(sum(x for x, _ in pts) / len(pts), 4)
        lon = round(sum(y for _, y in pts) / len(pts), 4)
        out.append([name, kreis, lat, lon, len(p['plz']), ','.join(sorted(p['plz']))])
    out.sort(key=lambda x: (x[0].casefold(), x[1]))
    print(skipped, 'Großkunden-/Sonderzeilen ausgelassen')
    return {'source': 'GeoNames Postal Codes DE (https://download.geonames.org/export/zip/)',
            'license': 'CC BY 4.0 – Ortsdaten: GeoNames (www.geonames.org)',
            'retrieved': dt.date.today().isoformat(),
            'fields': ['name', 'kreis', 'lat', 'lon', 'plz_count', 'plz'], 'rows': out}


if __name__ == '__main__':
    data = build(sys.argv[1])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(len(data['rows']), 'Orte →', OUT, f'({OUT.stat().st_size // 1024} KB)')
