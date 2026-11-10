"""Stückliste aller Bestandteile (SBOM, CycloneDX 1.5 JSON) und Lizenzübersicht (Masterplan 2.0, Sprint 6).

python tools/make_sbom.py [--out sbom/signaldesk.cdx.json] [--md docs/BESTANDTEILE.md]

Liest nur Dateien aus dem Projekt (keine Netzabfrage): requirements-lock-*.txt, docs/bench/lock-resolution.json
(Versionen, Lizenzen, Veröffentlichungsdatum), sales_tool/data/*.json (mitgelieferte Daten) und LICENSE.
Ausgabe ist deterministisch (gleiche Eingabe → gleiche Datei), damit Releases vergleichbar bleiben.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Lizenzen, die PyPI nicht als SPDX-Ausdruck liefert (geprüft anhand der Projektseiten/Klassifikatoren)
LICENSE_FALLBACK = {'greenlet': 'MIT AND PSF-2.0', 'pyee': 'MIT', 'cffi': 'MIT-0', 'pycparser': 'BSD-3-Clause',
                    'cryptography': 'Apache-2.0 OR BSD-3-Clause', 'typing-extensions': 'PSF-2.0', 'playwright': 'Apache-2.0'}
RUNTIME = [
    {'name': 'CPython', 'version': '3.10–3.13', 'license': 'PSF-2.0', 'scope': 'required',
     'description': 'Python-Laufzeit (vom Nutzer installiert bzw. per winget/python.org)', 'type': 'platform'},
    {'name': 'Chromium (Playwright-Download)', 'version': 'zur Playwright-Version passend', 'license': 'BSD-3-Clause', 'scope': 'optional',
     'description': 'Nur Variante browser/team/voll: Browser für JavaScript-Seiten, lädt `playwright install chromium`', 'type': 'application'},
]
DATA_SOURCES = [
    ('GLEIF API / Golden Copy', 'https://api.gleif.org/', 'CC0-1.0'),
    ('Wikidata SPARQL', 'https://query.wikidata.org/', 'CC0-1.0'),
    ('OpenStreetMap Overpass', 'https://overpass-api.de/', 'ODbL-1.0'),
    ('OpenStreetMap Nominatim', 'https://nominatim.openstreetmap.org/', 'ODbL-1.0'),
    ('TED – Tenders Electronic Daily', 'https://api.ted.europa.eu/', 'CC-BY-4.0'),
    ('GeoNames Postal Codes', 'https://download.geonames.org/export/zip/', 'CC-BY-4.0'),
]


def parse_lock(path):
    pkgs, cur = [], None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'^([A-Za-z0-9_.-]+)==([^\s;\\]+)\s*(?:;\s*([^\\]+?))?\s*\\?$', line)
        if m:
            cur = {'name': m.group(1).lower(), 'version': m.group(2), 'marker': (m.group(3) or '').strip(), 'hashes': []}
            pkgs.append(cur)
            continue
        h = re.search(r'--hash=sha256:([0-9a-f]{64})', line)
        if h and cur:
            cur['hashes'].append(h.group(1))
    return pkgs


def build(version=None):
    from sales_tool import __version__
    version = version or __version__
    res_path = ROOT / 'docs' / 'bench' / 'lock-resolution.json'
    resolution = json.loads(res_path.read_text(encoding='utf-8')) if res_path.exists() else {'variants': {}}
    comps, refs = {}, []
    for lock in sorted(ROOT.glob('requirements-lock-*.txt')):
        variant = lock.stem.replace('requirements-lock-', '')
        info = resolution['variants'].get(variant, {})
        for p in parse_lock(lock):
            key = f"{p['name']}@{p['version']}"
            meta = info.get(p['name'], {})
            lic = meta.get('license') or LICENSE_FALLBACK.get(p['name']) or 'NOASSERTION'
            c = comps.setdefault(key, {
                'type': 'library', 'bom-ref': f"pkg:pypi/{p['name']}@{p['version']}", 'name': p['name'], 'version': p['version'],
                'purl': f"pkg:pypi/{p['name']}@{p['version']}", 'scope': 'optional',
                'licenses': [{'expression': lic}] if lic != 'NOASSERTION' else [{'license': {'name': 'NOASSERTION'}}],
                'hashes': [{'alg': 'SHA-256', 'content': h} for h in sorted(p['hashes'])],
                'properties': [], 'externalReferences': [{'type': 'distribution', 'url': f"https://pypi.org/project/{p['name']}/{p['version']}/"}]})
            c['properties'].append({'name': 'signaldesk:variant', 'value': variant})
            if p['marker']:
                c['properties'].append({'name': 'signaldesk:marker', 'value': p['marker']})
            if meta.get('uploaded'):
                c['properties'].append({'name': 'signaldesk:released', 'value': meta['uploaded']})
    for c in comps.values():  # Eigenschaften eindeutig und sortiert
        c['properties'] = sorted({(x['name'], x['value']) for x in c['properties']})
        c['properties'] = [{'name': n, 'value': v} for n, v in c['properties']]
    out = []
    for r in RUNTIME:
        out.append({'type': r['type'], 'bom-ref': 'runtime:' + r['name'].split()[0].lower(), 'name': r['name'], 'version': r['version'],
                    'scope': r['scope'], 'description': r['description'], 'licenses': [{'expression': r['license']}]})
    for f in sorted((ROOT / 'sales_tool' / 'data').glob('*.json')):
        head = json.loads(f.read_text(encoding='utf-8'))
        out.append({'type': 'data', 'bom-ref': f'data:{f.name}', 'name': f.name, 'version': head.get('retrieved', ''),
                    'description': head.get('source', ''), 'scope': 'required',
                    'licenses': [{'expression': 'CC-BY-4.0'}] if 'CC BY 4.0' in head.get('license', '') else [{'license': {'name': head.get('license', 'NOASSERTION')}}],
                    'hashes': [{'alg': 'SHA-256', 'content': hashlib.sha256(f.read_bytes()).hexdigest()}],
                    'properties': [{'name': 'signaldesk:attribution', 'value': head.get('license', '')}]})
    out += [comps[k] for k in sorted(comps)]
    refs = [c['bom-ref'] for c in out]
    lic_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
    own = 'MIT' if lic_text.startswith('MIT License') else 'NOASSERTION'
    bom = {
        'bomFormat': 'CycloneDX', 'specVersion': '1.5',
        'serialNumber': 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, f'signaldesk-{version}-' + hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest())),
        'version': 1,
        'metadata': {'tools': {'components': [{'type': 'application', 'name': 'tools/make_sbom.py', 'version': version}]},
                     'component': {'type': 'application', 'bom-ref': 'signaldesk', 'name': 'SignalDesk', 'version': version,
                                   'licenses': [{'license': {'id': own}}], 'description': 'Lokales Akquise- und Buchhaltungswerkzeug (Python-Standardbibliothek)'},
                     'properties': [{'name': 'signaldesk:core-dependencies', 'value': 'keine (nur Python-Standardbibliothek)'}]},
        'components': out,
        'services': [{'bom-ref': f'service:{i}', 'name': n, 'endpoints': [u], 'authenticated': False, 'x-trust-boundary': True,
                      'data': [{'flow': 'inbound', 'classification': 'public'}], 'licenses': [{'expression': lic}]}
                     for i, (n, u, lic) in enumerate(DATA_SOURCES, 1)],
        'dependencies': [{'ref': 'signaldesk', 'dependsOn': refs}],
    }
    return bom


def markdown(bom):
    rows = ['# Bestandteile und Lizenzen (SBOM)', '',
            f"Automatisch erzeugt mit `tools/make_sbom.py` für SignalDesk {bom['metadata']['component']['version']} "
            '(maschinenlesbar: `sbom/signaldesk.cdx.json`, CycloneDX 1.5). Nicht von Hand ändern.', '',
            '**SignalDesk selbst:** MIT-Lizenz, Kern ohne Fremdpakete (nur Python-Standardbibliothek).', '',
            '## Laufzeit und mitgelieferte Daten', '', '| Bestandteil | Version | Lizenz | Nötig? | Hinweis |', '|---|---|---|---|---|']
    lic = lambda c: c['licenses'][0].get('expression') or c['licenses'][0].get('license', {}).get('id') or c['licenses'][0].get('license', {}).get('name')
    for c in bom['components']:
        if c['type'] in ('platform', 'application', 'data'):
            rows.append(f"| {c['name']} | {c['version']} | {lic(c)} | {'ja' if c['scope'] == 'required' else 'optional'} | {c.get('description', '')} |")
    rows += ['', '## Python-Pakete je Installationsvariante', '',
             'Feste Versionen mit SHA-256-Prüfsummen in `requirements-lock-*.txt`; installiert nur, wenn die Variante es verlangt.', '',
             '| Paket | Version | Lizenz | Variante(n) | veröffentlicht |', '|---|---|---|---|---|']
    for c in bom['components']:
        if c['type'] == 'library':
            props = {}
            for p in c['properties']:
                props.setdefault(p['name'], []).append(p['value'])
            marker = f" ({props['signaldesk:marker'][0]})" if 'signaldesk:marker' in props else ''
            rows.append(f"| {c['name']} | {c['version']} | {lic(c)} | {', '.join(props.get('signaldesk:variant', []))}{marker} | {(props.get('signaldesk:released') or [''])[0]} |")
    rows += ['', '## Abgefragte Online-Quellen (zur Laufzeit, nur auf Auftrag)', '', '| Quelle | Adresse | Datenlizenz |', '|---|---|---|']
    for s in bom['services']:
        rows.append(f"| {s['name']} | {s['endpoints'][0]} | {s['licenses'][0]['expression']} |")
    rows += ['', '**Copyleft-Hinweis:** Keine Bibliothek verlangt GPL/AGPL. `tld` ist mehrfach lizenziert (MPL-1.1 ODER GPL-2.0 ODER '
             'LGPL-2.1+) – SignalDesk nutzt es unter MPL-1.1, und nur in der Variante „voll“. MPL-2.0 (certifi, orjson) betrifft nur '
             'Änderungen an diesen Dateien selbst. ODbL (OpenStreetMap) gilt für die abgefragten **Daten** (Namensnennung '
             '„© OpenStreetMap-Mitwirkende“, Share-Alike bei Weitergabe einer Datenbank), nicht für den Programmcode.', '']
    return '\n'.join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'sbom' / 'signaldesk.cdx.json'))
    ap.add_argument('--md', default=str(ROOT / 'docs' / 'BESTANDTEILE.md'))
    a = ap.parse_args(argv)
    bom = build()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(bom, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    Path(a.md).write_text(markdown(bom), encoding='utf-8')
    libs = [c for c in bom['components'] if c['type'] == 'library']
    unknown = [c['name'] for c in libs if c['licenses'][0].get('license', {}).get('name') == 'NOASSERTION']
    print(f"SBOM: {len(bom['components'])} Bestandteile ({len(libs)} Python-Pakete), {len(bom['services'])} Online-Quellen"
          + (f" · Lizenz unbekannt: {', '.join(unknown)}" if unknown else ''))
    return 1 if unknown else 0


if __name__ == '__main__':
    raise SystemExit(main())
