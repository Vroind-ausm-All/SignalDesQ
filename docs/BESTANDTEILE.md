# Bestandteile und Lizenzen (SBOM)

Automatisch erzeugt mit `tools/make_sbom.py` für SignalDesk 2.0.0-dev72 (maschinenlesbar: `sbom/signaldesk.cdx.json`, CycloneDX 1.5). Nicht von Hand ändern.

**SignalDesk selbst:** MIT-Lizenz, Kern ohne Fremdpakete (nur Python-Standardbibliothek).

## Laufzeit und mitgelieferte Daten

| Bestandteil | Version | Lizenz | Nötig? | Hinweis |
|---|---|---|---|---|
| CPython | 3.10–3.14 | PSF-2.0 | ja | Python-Laufzeit (vom Nutzer installiert bzw. per winget/python.org) |
| Chromium (Playwright-Download) | zur Playwright-Version passend | BSD-3-Clause | optional | Nur Variante browser/team/voll: Browser für JavaScript-Seiten, lädt `playwright install chromium` |
| de_core_news_sm (spaCy-Modell) | 3.8.0 | MIT | optional | Nur Profil „nlp“ (R2.5): requirements-nlp-model.txt mit SHA-256; Trainingsdaten TIGER, Tiger2Dep, WikiNER – Rechte für gewerblichen Einsatz ungeklärt (E8) |
| gemeinden_de.json | 2026-11-06 | CC-BY-4.0 | ja | GeoNames Postal Codes DE (https://download.geonames.org/export/zip/) |
| Geist 400 (geist-400.woff2) | 5.3.0 | OFL-1.1 | ja | @fontsource/geist-sans 5.3.0, files/geist-sans-latin-400-normal.woff2 |
| Geist 500 (geist-500.woff2) | 5.3.0 | OFL-1.1 | ja | @fontsource/geist-sans 5.3.0, files/geist-sans-latin-500-normal.woff2 |
| Geist 600 (geist-600.woff2) | 5.3.0 | OFL-1.1 | ja | @fontsource/geist-sans 5.3.0, files/geist-sans-latin-600-normal.woff2 |
| JetBrains Mono 400 (jetbrains-mono-400.woff2) | 5.3.0 | OFL-1.1 | ja | @fontsource/jetbrains-mono 5.3.0, files/jetbrains-mono-latin-400-normal.woff2 |
| JetBrains Mono 500 (jetbrains-mono-500.woff2) | 5.3.0 | OFL-1.1 | ja | @fontsource/jetbrains-mono 5.3.0, files/jetbrains-mono-latin-500-normal.woff2 |

## Python-Pakete je Installationsvariante

Feste Versionen mit SHA-256-Prüfsummen in `requirements-lock-*.txt`; installiert nur, wenn die Variante es verlangt.

| Paket | Version | Lizenz | Variante(n) | veröffentlicht |
|---|---|---|---|---|
| annotated-doc | 0.0.6 | MIT | nlp | 2026-11-10 |
| annotated-types | 0.8.0 | MIT | nlp | 2026-07-23 |
| anyio | 4.16.0 | MIT | nlp | 2026-11-01 |
| babel | 2.18.0 | BSD-3-Clause | research | 2026-02-01 |
| blis | 1.3.4 | BSD-3-Clause | nlp | 2026-10-25 |
| catalogue | 2.0.10 | MIT | nlp | 2023-09-25 |
| certifi | 2026.10.23 | MPL-2.0 | nlp, research | 2026-10-23 |
| cffi | 2.1.1 | MIT-0 | team | 2026-08-03 |
| charset-normalizer | 3.5.2 | MIT | nlp, research | 2026-09-30 |
| click | 8.5.1 | BSD-3-Clause | nlp | 2026-11-06 |
| cloudpathlib | 0.26.0 | MIT | nlp | 2026-10-02 |
| colorama | 0.4.6 | BSD-3-Clause | nlp (sys_platform == "win32") | 2022-10-25 |
| confection | 1.3.4 | MIT | nlp | 2026-10-26 |
| courlan | 1.4.0 | Apache-2.0 | research | 2026-06-01 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | team | 2026-09-30 |
| cssselect | 1.5.0 | BSD-3-Clause | research | 2026-07-27 |
| cymem | 2.0.16 | MIT | nlp | 2026-10-24 |
| dateparser | 1.4.3 | BSD-3-Clause | research | 2026-09-03 |
| exceptiongroup | 1.3.1 | MIT | nlp (python_version < "3.11") | 2025-11-21 |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | browser | 2026-09-14 |
| h11 | 0.16.0 | MIT | nlp | 2025-04-24 |
| htmldate | 1.11.0 | Apache-2.0 | research | 2026-10-02 |
| httpcore | 1.0.9 | BSD-3-Clause | nlp | 2025-04-24 |
| httpx | 0.28.1 | BSD-3-Clause | nlp | 2024-12-06 |
| idna | 3.20 | BSD-3-Clause | nlp | 2026-09-17 |
| jinja2 | 3.1.6 | BSD-3-Clause | nlp | 2025-03-05 |
| justext | 3.0.2 | BSD-3-Clause | research | 2025-02-25 |
| lxml-html-clean | 0.4.5 | BSD-3-Clause | research | 2026-05-20 |
| lxml | 6.1.3 | BSD-3-Clause | research | 2026-09-02 |
| markdown-it-py | 4.3.0 | MIT | nlp | 2026-11-10 |
| markupsafe | 3.0.4 | BSD-3-Clause | nlp | 2026-10-02 |
| mdurl | 0.1.2 | MIT | nlp | 2022-08-14 |
| murmurhash | 1.0.16 | MIT | nlp | 2026-10-24 |
| numpy | 2.2.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | nlp | 2025-05-17 |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) | research | 2026-10-07 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | nlp | 2026-08-04 |
| playwright | 1.64.1 | Apache-2.0 | browser | 2026-10-22 |
| preshed | 3.0.15 | MIT | nlp | 2026-10-25 |
| pycparser | 3.11 | BSD-3-Clause | team | 2026-10-09 |
| pydantic-core | 2.50.4 | MIT | nlp | 2026-11-05 |
| pydantic | 2.14.3 | MIT | nlp | 2026-11-05 |
| pyee | 13.0.1 | MIT | browser | 2026-02-14 |
| pygments | 2.21.0 | BSD-2-Clause | nlp | 2026-08-17 |
| python-dateutil | 3.0.0 | BSD-3-Clause | research | 2026-10-21 |
| pytz | 2026.5 | MIT | research | 2026-10-04 |
| rapidfuzz | 3.14.5 | MIT | research | 2026-04-07 |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python | research | 2026-09-29 |
| requests | 2.34.2 | Apache-2.0 | nlp | 2026-05-14 |
| rich | 15.0.0 | MIT | nlp | 2026-04-12 |
| scrapling | 0.5.1 | BSD-3-Clause | research | 2026-11-04 |
| setuptools | 84.2.1 | MIT | nlp | 2026-10-20 |
| shellingham | 1.5.4 | ISC | nlp | 2023-10-24 |
| six | 1.17.0 | MIT | research | 2024-12-04 |
| smart-open | 9.0.3 | MIT | nlp | 2026-11-09 |
| spacy-legacy | 3.0.12 | MIT | nlp | 2023-01-23 |
| spacy-loggers | 1.0.5 | MIT | nlp | 2023-09-11 |
| spacy | 3.8.18 | MIT | nlp | 2026-10-26 |
| srsly | 2.5.6 | MIT | nlp | 2026-11-03 |
| thinc | 8.3.14 | MIT | nlp | 2026-10-25 |
| tld | 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later | research | 2026-03-06 |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | nlp | 2026-09-11 |
| trafilatura | 2.3.1 | Apache-2.0 | research | 2026-10-06 |
| typer | 0.29.1 | MIT | nlp | 2026-11-11 |
| typing-extensions | 4.16.0 | PSF-2.0 | browser, nlp, research, team (python_version < "3.11") | 2026-07-02 |
| typing-inspection | 0.4.5 | MIT | nlp | 2026-11-04 |
| tzdata | 2026.5 | Apache-2.0 | research | 2026-10-03 |
| tzlocal | 5.4.5 | MIT | research | 2026-10-22 |
| urllib3 | 2.8.0 | MIT | nlp, research | 2026-09-15 |
| w3lib | 2.5.0 | BSD-3-Clause | research | 2026-09-30 |
| wasabi | 1.1.3 | MIT | nlp | 2024-05-31 |
| weasel | 1.0.1 | MIT | nlp | 2026-10-26 |
| wrapt | 2.5.2 | BSD-2-Clause | nlp | 2026-10-29 |

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
