# Masterplan SignalDesk 2.0 – Scrapling und ergänzende Open-Source-Bausteine

Quelle: „SignalDesk 2.0 – Scrapling- und GitHub-Masterplan“ vom 06.11.2026. Das Dokument beruhte auf dem Stand v1.0 und wurde mit v1.14 abgeglichen.

## Leitlinie
- SignalDesk bleibt das Produkt.
- Scrapling ist ein **austauschbarer Baustein** für Abruf und HTML-Auswertung öffentlicher Firmenseiten. Es ist kein neues CRM, kein Lead-Finder und keine rechtliche Erlaubnis.
- **Ausgeschlossen:**
  - Google-Maps- und LinkedIn-Scraping;
  - Captcha-Umgehung, Tarnung (Stealth) und Proxy-Rotation;
  - automatische Kaltakquise;
  - erfundene Kontaktdaten.
- **Entscheidungen** fallen nach Messung, Lizenz, Wartung und Ressourcenbedarf, nicht nach GitHub-Sternen.

## Sprints und Stand

| Sprint | Inhalt | Stand |
|---|---|---|
| 0 | Testbasis, Ausgangsmessung, Testgelände | ✅ v1.15: 33 fiktive Websites (`tests/fixtures/web`), Benchmark (`tools/bench_fetch.py`), Ausgangsmessung v1.14 |
| 1 | Sichere Fetcher-Schnittstelle, Scrapling-Pilot | ✅ v1.15: `sales_tool/research/` mit IP-Pinning, robots.txt nach RFC 9309 und Grenzen; Scrapling-Parser schaltbar; Scrapling-Abruf gemessen und **nicht** eingebaut (Begründung im Bericht) |
| 2 | Extraktion und einheitliche Belege (Trafilatura, extruct/JSON-LD) | ✅ v1.16: Belegprüfung (Wert muss im Originaltext stehen), JSON-LD/Microdata/OpenGraph ohne Fremdpaket (extruct nicht installierbar), Haupttext eingebaut, Trafilatura schaltbar; 103/103 Felder, 187/187 Werte mit Beleg |
| 3 | Persistente Recherche-Aufträge (Pause, Fortsetzen, Abbrechen; Neustart ohne Verlust) | ✅ v1.16: `research/jobs.py` für Sammelsuche, Website-Suche und Firmen-Berichte; Absturztest (SIGKILL) ohne Verlust; noch auf eigenen Threads: Quickscan/KI-Analyse, Impressums-Stapel, Kaufsignal-Scan, Website-Scoring |
| 4 | Große Firmendaten (DuckDB, GLEIF Golden Copy/Delta), RapidFuzz | ✅ v1.17: Dubletten-Regeln (`research/identity.py`) für Sichtung, Leads und CRM – mögliche Dubletten beim Haupteintrag statt doppelt, GmbH ≠ GmbH & Co. KG; Lead-Zusammenführung per Klick; GLEIF-Katalog per Streaming (CSV/ZIP, Golden Copy/Delta, Protokoll, GLEIF-Ersatz); DuckDB gemessen und **nicht** eingebaut (11× Arbeitsspeicher), RapidFuzz optional |
| 5 | Geführter Arbeitstag, CRM, Angebote | ✅ v1.18: Beispieltag des Plans als Abnahmetest (API + Browser) ohne Sackgasse; Kontaktsperre zentral inkl. Sperrliste; „Bedarf bestätigt“ als Freigabe vor Angebotsversand, Angebot aus bestätigtem Bedarf; Firmenakte mit Ablauf, nächstem Schritt, Belegabdeckung und Zeitleiste; Folgeaufgaben; Suchprofile mit Budget; Tagesabschluss |
| 6 | Windows-Version, eingefrorene Paketversionen, Liste der Bestandteile, Tests Windows/Linux | ✅ v1.19: Installationsvarianten (basis/browser/team/voll), Lockdateien mit Prüfsummen für Windows/Linux × Python 3.10–3.13, SBOM (CycloneDX), byte-gleich reproduzierbares Release-ZIP, Offline-Modus, Wiederherstellung mit GoBD-Schutz, CI Windows/Linux mit Installationsprüfung auf frischer Maschine, UI-E2E, Leistungsbericht; dazu Fehlerbehebung „Firmendaten ins Firmenprofil“ |

## Entscheidung „Empfehlung A“ (Website-Zuordnung)
- Der Plan sagt: „Niemals automatisch firmenname.de raten.“
- SignalDesk prüft weiterhin Domain-**Vorschläge**, kennzeichnet sie aber klar.
- Als Website der Firma gilt nur:
  - „belegt“ (die Registernummer im Impressum stimmt);
  - „laut Quelle“;
  - von dir bestätigt.
- „Wahrscheinliche“ Treffer bleiben Vorschläge mit den Knöpfen „Website passt / passt nicht“. Aus ihnen wird nichts automatisch übernommen, abgelehnte Domains werden nicht erneut vorgeschlagen.

## Abnahmeregeln (aus dem Plan)
- **Grundregeln:** keine erfundenen Kontakte, keine ungewollten CRM-Änderungen.
- **Sicherheit:** 100 % der gesperrten URLs werden abgelehnt.
- **Tests:** alle Regressionstests grün; mindestens 95 % korrekt extrahierte Belege in deutschen Testseiten.
- **Nachvollziehbarkeit:** jeder Recherchefehler je Firma ist sichtbar.
- **Neustart:** keine offenen Aufträge ohne Status.
- **Messen statt behaupten:** Verbesserungen werden gemessen, nicht behauptet.
