# Bestandteile und Lizenzen (SBOM)

Automatisch erzeugt mit `tools/make_sbom.py` für SignalDesk 2.0.0-dev12 (maschinenlesbar: `sbom/signaldesk.cdx.json`, CycloneDX 1.5). Nicht von Hand ändern.

**SignalDesk selbst:** MIT-Lizenz, Kern ohne Fremdpakete (nur Python-Standardbibliothek).

## Laufzeit und mitgelieferte Daten

| Bestandteil | Version | Lizenz | Nötig? | Hinweis |
|---|---|---|---|---|
| CPython | 3.10–3.13 | PSF-2.0 | ja | Python-Laufzeit (vom Nutzer installiert bzw. per winget/python.org) |
| Chromium (Playwright-Download) | zur Playwright-Version passend | BSD-3-Clause | optional | Nur Variante browser/team/voll: Browser für JavaScript-Seiten, lädt `playwright install chromium` |
| gemeinden_de.json | 2026-11-06 | CC-BY-4.0 | ja | GeoNames Postal Codes DE (https://download.geonames.org/export/zip/) |

## Python-Pakete je Installationsvariante

Feste Versionen mit SHA-256-Prüfsummen in `requirements-lock-*.txt`; installiert nur, wenn die Variante es verlangt.

| Paket | Version | Lizenz | Variante(n) | veröffentlicht |
|---|---|---|---|---|
| babel | 2.18.0 | BSD-3-Clause | research | 2026-02-01 |
| certifi | 2026.10.23 | MPL-2.0 | research | 2026-10-23 |
| cffi | 2.1.1 | MIT-0 | team | 2026-08-03 |
| charset-normalizer | 3.5.2 | MIT | research | 2026-09-30 |
| courlan | 1.4.0 | Apache-2.0 | research | 2026-06-01 |
| cryptography | 46.0.7 | Apache-2.0 OR BSD-3-Clause | team | 2026-04-08 |
| cssselect | 1.5.0 | BSD-3-Clause | research | 2026-07-27 |
| dateparser | 1.4.3 | BSD-3-Clause | research | 2026-09-03 |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | browser | 2026-09-14 |
| htmldate | 1.11.0 | Apache-2.0 | research | 2026-10-02 |
| justext | 3.0.2 | BSD-3-Clause | research | 2025-02-25 |
| lxml-html-clean | 0.4.5 | BSD-3-Clause | research | 2026-05-20 |
| lxml | 6.1.3 | BSD-3-Clause | research | 2026-09-02 |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) | research | 2026-10-07 |
| playwright | 1.64.1 | Apache-2.0 | browser | 2026-10-22 |
| pycparser | 3.11 | BSD-3-Clause | team | 2026-10-09 |
| pyee | 13.0.1 | MIT | browser | 2026-02-14 |
| python-dateutil | 3.0.0 | BSD-3-Clause | research | 2026-10-21 |
| pytz | 2026.5 | MIT | research | 2026-10-04 |
| rapidfuzz | 3.14.5 | MIT | research | 2026-04-07 |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python | research | 2026-09-29 |
| scrapling | 0.5.1 | BSD-3-Clause | research | 2026-11-04 |
| six | 1.17.0 | MIT | research | 2024-12-04 |
| tld | 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later | research | 2026-03-06 |
| trafilatura | 2.3.1 | Apache-2.0 | research | 2026-10-06 |
| typing-extensions | 4.16.0 | PSF-2.0 | browser, research | 2026-07-02 |
| tzdata | 2026.5 | Apache-2.0 | research | 2026-10-03 |
| tzlocal | 5.4.5 | MIT | research | 2026-10-22 |
| urllib3 | 2.8.0 | MIT | research | 2026-09-15 |
| w3lib | 2.5.0 | BSD-3-Clause | research | 2026-09-30 |

## Abgefragte Online-Quellen (zur Laufzeit, nur auf Auftrag)

| Quelle | Adresse | Datenlizenz |
|---|---|---|
| GLEIF API / Golden Copy | https://api.gleif.org/ | CC0-1.0 |
| Wikidata SPARQL | https://query.wikidata.org/ | CC0-1.0 |
| OpenStreetMap Overpass | https://overpass-api.de/ | ODbL-1.0 |
| OpenStreetMap Nominatim | https://nominatim.openstreetmap.org/ | ODbL-1.0 |
| TED – Tenders Electronic Daily | https://api.ted.europa.eu/ | CC-BY-4.0 |
| GeoNames Postal Codes | https://download.geonames.org/export/zip/ | CC-BY-4.0 |

**Copyleft-Hinweis:** Keine Bibliothek verlangt GPL/AGPL. `tld` ist mehrfach lizenziert (MPL-1.1 ODER GPL-2.0 ODER LGPL-2.1+) – SignalDesk nutzt es unter MPL-1.1, und nur in der Variante „voll“. MPL-2.0 (certifi, orjson) betrifft nur Änderungen an diesen Dateien selbst. ODbL (OpenStreetMap) gilt für die abgefragten **Daten** (Namensnennung „© OpenStreetMap-Mitwirkende“, Share-Alike bei Weitergabe einer Datenbank), nicht für den Programmcode.
