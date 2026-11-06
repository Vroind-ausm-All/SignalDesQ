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
| 2 | Extraktion und einheitliche Belege (Trafilatura, extruct/JSON-LD) | ⬜ nächster Schritt; offene Testfälle: PDF-Impressum (PLZ), Fehlerkennung eines „One-Pagers“, JSON-LD Organization/JobPosting |
| 3 | Persistente Recherche-Aufträge (Pause, Fortsetzen, Abbrechen; Neustart ohne Verlust) | ⬜ Firmen-Berichte laufen schon nach einem Neustart weiter; Sammelsuchen werden noch abgebrochen |
| 4 | Große Firmendaten (DuckDB, GLEIF Golden Copy/Delta), RapidFuzz | ⬜ |
| 5 | Geführter Arbeitstag, CRM, Angebote | 🟡 weitgehend vorhanden (Sprints A–D, v1.9–v1.13), Abgleich mit dem Abnahmeablauf offen |
| 6 | Windows-Version, eingefrorene Paketversionen, Liste der Bestandteile, Tests Windows/Linux | ⬜ |

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
