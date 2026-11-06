# Bericht Masterplan 2.0 – Sprint 0 und 1 (SignalDesk v1.15)

Grundlage: `docs/MASTERPLAN_2_0_SCRAPLING.md`, mitgeliefertes `Scrapling-main.zip` (Version 0.5.1, BSD-3-Clause).
Dazu Empfehlung A zur Website-Zuordnung.

## Sprint 0 – Testgelände und Ausgangsmessung

- **Testgelände** (`tests/fixtures/web`, erzeugt mit `tools/make_web_fixtures.py`): 33 fiktive Websites mit erwarteten Fakten.
  - **Impressumsvarianten:** GmbH, GmbH & Co. KG, UG, PDF, One-Pager, ohne Link, englisch, verschleierte E-Mail, widersprüchliche Angaben, JSON-LD Organization/JobPosting.
  - **robots.txt:** sperrt alles, sperrt nur Teile (`*`, `$`), leitet weiter, antwortet 403 oder 503.
  - **Netz und Sicherheit:**
    - Weiterleitungen auf eine lokale IP, einen internen Namen, eine fremde Firma und im Kreis;
    - Antworten 403/429;
    - 10-MB-Antwort, gzip-Bombe, gzip ohne Anfrage;
    - 25 s Verzögerung;
    - Bild statt HTML;
    - ISO-8859-1 ohne Angabe, windows-1252;
    - reine JavaScript-Seite;
    - DNS-Rebinding.
- **Simuliertes Netz** (`tests/webfixtures.py`): Die `.example`-Domains lösen auf eine öffentliche Adresse auf und landen beim lokalen Server. Die Sicherheitsprüfungen von SignalDesk bleiben dabei **voll aktiv**.
  - Verbindungsversuche zu ungeprüften Adressen werden protokolliert.
  - Es gibt keine echten Netzabfragen.
- **Benchmark** (`tools/bench_fetch.py`): Impressums-Recherche und Light-Crawl für jede Website. Gemessen werden:
  - erwartetes Verhalten und Feldtreffer;
  - P50/P95, Anfragen, robots.txt-Abrufe, DNS-Abfragen;
  - ungeprüfte Verbindungen, Spitzenspeicher.

  Die Ergebnisse liegen in `docs/bench/*.json`.

### Ausgangsmessung v1.14 – gefundene Fehler

| Befund | Wirkung |
|---|---|
| robots.txt mit Weiterleitung (`firma.de` → `www.firma.de`) | ganze Website abgelehnt (sehr häufiger Fall) |
| robots.txt antwortet 403 | abgelehnt, obwohl RFC 9309 das als „erlaubt“ wertet |
| **DNS-Rebinding** | der Abruf **verband sich mit der ungeprüften Adresse 10.0.0.2**, weil die Adresse beim Verbinden ein zweites Mal aufgelöst wurde |
| Server liefert gzip | Impressum nicht gefunden bzw. Datensalat als „ok“ gelesen |
| `<title>` im Fließtext | Firmenname wurde „Impressum – Schmid Anlagenbau GmbH & Co. KG“ |
| robots.txt vor jeder Seite neu geladen | 62 von 123 Anfragen nur für robots.txt |
| ISO-8859-1 ohne Angabe | wurde nur über einen Umweg erkannt |

## Sprint 1 – sichere Fetcher-Schnittstelle

Neues Paket `sales_tool/research/` (nur Standardbibliothek):

| Modul | Aufgabe |
|---|---|
| `policy.py` | Grenzen (10 s je Schritt, 25 s gesamt, 5 Weiterleitungen, 2 MB HTML / 5 MB PDF / 4 MB entpackt). robots.txt nach **RFC 9309**: `*` und `$`, längster Treffer, eigene Agent-Gruppe, 4xx erlaubt, 429/5xx/unerreichbar gesperrt, Weiterleitungen, 1 h Zwischenspeicher je Website |
| `safe_urls.py` | URL-Prüfung (nur http/https, Ports 80/443, keine Zugangsdaten, keine IP-Literale/internen Namen). `resolve_public` löst **einmal** auf und prüft jede Adresse |
| `fetchers/http.py` | **IP-Pinning**: Die Verbindung geht genau zur geprüften Adresse (TLS prüft weiterhin das Zertifikat auf den Namen). Weiterleitungen werden selbst ausgewertet und je Schritt neu geprüft. Außerdem: Content-Length-Vorprüfung, gestreamtes Lesen mit Höchstgröße, gzip/deflate mit Bremse gegen gzip-Bomben, Inhaltstyp-Liste, Gesamtzeit. Keine Tarnung, keine Wiederholungsschleifen |
| `fetchers/base.py` | `FetchResult` nach dem Datenvertrag „Normalisierte Seite“ (URL, Endadresse, Abrufzeit, Fetcher, Status, robots, Inhalts-Hash, Weiterleitungen, geprüfte IP). Zeichensatz: BOM → HTTP → `<meta charset>` → UTF-8 → Windows-1252 |
| `fetchers/legacy.py` | bisheriger Abruf als Adapter – nur für Vergleich und Rückfall |
| `fetchers/browser.py` | Playwright als **Rückfall**: nur wenn installiert, eingeschaltet und der statische Abruf zu wenig Text liefert. JavaScript bleibt aus, wie bisher |
| `parse.py` | HTML-Auswertung: eingebaut oder **Scrapling-Selector** (schaltbar), mit automatischem Rückfall |
| `settings.py` | Schalter `fetcher` (http/legacy), `parser` (stdlib/auto/scrapling), `browser_fallback`. Gespeichert in `app_settings`; Oberfläche: „Datenqualität & System → Recherche-Technik“ |

**Angeschlossen, nicht dupliziert:**
- `imprint.http_fetch` und damit die Impressums-Recherche, die Website-Suche, die Kaufsignale und das Website-Scoring;
- `website_analyzer.robots_allowed` und `light_crawl`.
- `crawl_site` liest jetzt **HTTP zuerst** und nutzt den Browser nur als Rückfall.

### Ergebnis (gleiches Testgelände)

| | v1.14 | **v1.15** |
|---|---|---|
| Impressum: erwartetes Verhalten | 25/33 | **31/33** |
| Impressumsfelder korrekt | 79.6 % | **99.0 %** (102/103) |
| Crawl: erwartetes Verhalten | 29/33 | **33/33** |
| P50 / P95 Impressum | 36.8 / 102.7 ms | **8.7 / 14.9 ms** |
| Anfragen (davon robots.txt) | 123 (62) | **91 (35)** |
| Verbindungen zu ungeprüften Adressen | **1** | **0** |
| Spitzenspeicher Messlauf | 2.9 MB | 9.0 MB (Entpacken mit 4-MB-Bremse, gestreamte Größenprüfung) |

Die zwei offenen Fälle betreffen die Auswertung, nicht den Abruf; sie kommen in Sprint 2:
- PDF-Impressum ohne PLZ;
- „One-Pager“-Erkennung durch das Wort „Impressum“ im Fußbereich.

### Scrapling – gemessen, nicht behauptet

**HTML-Auswertung (Scrapling-Selector, lxml):**
- Auf 69 Testseiten ist der Text **identisch** zum eingebauten Parser (Übereinstimmung 1.0), mit denselben Links und demselben erwarteten Verhalten.
- Kosten: **2.4× langsamer** (50 vs. 21 ms gesamt) und rund 3 MB mehr Speicher.
- Deshalb Voreinstellung „Eingebaut“; Scrapling bleibt per Schalter verfügbar (`requirements-research.txt`).
- In Sprint 2 (CSS-Auswahl, strukturierte Daten) wird das neu bewertet.

**Scrapling-Abruf (Pilot in eigener Umgebung, `tools/bench_scrapling_pilot.py`, Ergebnis `docs/bench/scrapling_pilot.json`):**
- Voreinstellung **mit Tarnung**:
  - Chrome-Windows-User-Agent und `sec-ch-ua`-Kopfzeilen;
  - **`Referer: https://www.google.com/`**;
  - HTTP/2-Upgrade.
- Schon der statische Abruf importiert **`patchright`**, einen für Tarnung veränderten Playwright-Fork. `scrapling[fetchers]` bringt **362 MB** mit, darunter `patchright`, `browserforge` und Fingerprint-Daten.
- Nach dem Import +35 MB Arbeitsspeicher. Die eigene DNS-Auflösung von curl lässt sich nicht an unsere Adressprüfung binden, also kein IP-Pinning.
- Positiv: curl lehnt Weiterleitungen auf interne IPs selbst ab.
- **Entscheidung:** nicht eingebaut. Das widerspräche den Abnahmekriterien des Plans (kein Stealth, Fetcher nicht automatisch sicher).

## Empfehlung A – Website-Vorschläge

- Als Website der Firma gilt nur:
  - **„belegt: Registernr. im Impressum“**;
  - „laut Quelle“;
  - „von dir bestätigt“.
- „Wahrscheinliche“ Treffer heißen jetzt „**Vorschlag – bitte prüfen**“, mit den Knöpfen „✓ Website passt“ und „✕ passt nicht“.
- **Nebenbefund behoben:** Bei einem bloßen Vorschlag wurde bisher die Registernummer aus dem (vielleicht fremden) Impressum in den Treffer geschrieben.
- **Beim Übernehmen** wird ein unbestätigter Vorschlag **nicht** zur Firmen-Website. Es entsteht nur eine Notiz, und Impressumsdaten werden nicht übernommen.
- **Bestätigen** gibt die Website frei und übernimmt die Impressumsdaten in leere Felder.
- **Ablehnen** merkt sich die Domain, sie wird nicht wieder vorgeschlagen.

## Abhängigkeiten und Lizenzen

- **Ohne Zusatzpakete:** SignalDesk läuft weiterhin ausschließlich mit der Python-Standardbibliothek.
- **Optional** (`requirements-research.txt`, fest gepinnt):

| Paket | Version | Lizenz |
|---|---|---|
| scrapling | 0.5.1 | BSD-3-Clause |
| lxml | 6.1.3 | BSD-3-Clause |
| cssselect | 1.6.0 | BSD-3-Clause |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| tld | 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later |
| w3lib | 2.6.0 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |

Hinweis für einen späteren SaaS-Betrieb: MPL-lizenzierte Bausteine (orjson, tld) sind als unveränderte Bibliotheken unproblematisch. Bei Änderungen an ihren Dateien gelten Offenlegungspflichten für diese Dateien.

## Tests
- **Unit- und Integrationstests:** 320, alle grün.
  - 20 neu für Sprint 1 (`tests/test_sprintS1_fetch.py`): robots.txt RFC 9309, URL-Prüfung, DNS-Rebinding, Weiterleitungen, Grenzen, gzip, Zeit, Zeichensätze, beide Parser, Browser-Rückfall, Schalter, Endpunkt.
  - 5 neu für Empfehlung A (`tests/test_v115_website_suggestions.py`).
- **Browser-Test** (Chromium), ohne Konsolenfehler:
  - Vorschlag sichtbar, „Website passt“ und Status „von dir bestätigt“;
  - Recherche-Technik laden und speichern;
  - Handyansicht ohne seitliches Scrollen.
- **Rückweg:** Schalter „Abruf → Bisheriger Abruf“ (gemessen: `docs/bench/v1.15-legacy-flag.json`).
