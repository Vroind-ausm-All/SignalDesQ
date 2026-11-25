# Bericht 2.0.0-dev66 – Recherche: Website-Zuordnung und Firmen-Berichte

Stand: 25.11.2026. Alle Prüfungen mit fiktiven Firmen und Attrappen der Websites; keine Abfragen an echte Firmen.

## 1. Ausgangslage

| Befund | Ursache im Code (bis dev65) | Auswirkung |
|---|---|---|
| Viele Treffer standen auf „Prüfung fehlgeschlagen“, obwohl nichts kaputt war | Eine geratene Domain ohne DNS-Eintrag löste „Domain konnte nicht aufgelöst werden“ aus und zählte als Abruffehler (`sweep.find_website`) | Falsches Signal „später erneut versuchen“, Wiederholungen ohne Nutzen |
| Websites mit abweichendem Domainnamen wurden nicht gefunden | Kandidaten nur aus dem Firmennamen geraten (9 Varianten) | E-Mail-Domain aus OpenStreetMap blieb ungenutzt |
| Marke ≠ Firmenname wurde immer abgelehnt | Zuordnung nur über Name/Registernummer; abweichender Name war harter Gegenbeleg | „Elektro Huber“ ↔ „Huber Elektrotechnik e.K.“ bei gleicher Anschrift und Telefonnummer: keine Zuordnung |
| Kleine Betriebe ohne Register konnten nie „belegt“ sein | „belegt“ verlangte Registernummer + Gericht | Jede Website eines Einzelunternehmens musste von Hand bestätigt werden |
| Firmen-Bericht für Firmen ohne Website ging nicht | `create_reports` wies sie ab („zuerst Website ergänzen“) | Gerade bei den Firmen, für die Recherche am meisten bringt, blieb der Bericht leer |
| Bericht ohne Gesamtbild | Fünf Schritt-Abschnitte, aber kein Fazit, keine Liste der Lücken, kein Alter | Was fehlt und was als Nächstes zu tun ist, musste man sich zusammensuchen |

## 2. Umsetzung

### Website-Zuordnung (`sales_tool/research/homepage.py`, neu)

- **„Domain gibt es nicht“ ist kein Fehler:** `safe_urls.resolve_public` unterscheidet `DomainMissing` (NXDOMAIN/NODATA, auch Windows-Codes 11001/11004) von `DnsUnavailable` (Störung). Nur Störungen zählen als Abruffehler. Meldet *jeder* Name „unbekannt“, prüft `dns_available()` zwei bekannte Namen (`denic.de`, `example.com`, keine Firmendaten, 5 Minuten gemerkt) – ohne funktionierende Namensauflösung wird nichts geschlossen und „Prüfung fehlgeschlagen: DNS nicht verfügbar“ gemeldet.
- **Mehr Kandidaten:** zuerst die E-Mail-Domain der Quelle (OpenStreetMap `email`/`contact:email`, Freemail-Anbieter zählen nicht), dann die bisherigen Namensvarianten und neu: Rechtsform angehängt (`…-gmbh.de`), umgekehrte Wortfolge (`huber-elektro.de`), ohne „e“ (`muller`), Umlaut-Domain als Punycode. Gattungsbegriffe allein (`elektro.de`) werden nicht geprüft. Höchstens 12 Domains je Firma.
- **Mehr-Merkmal-Abgleich (`assess`):** Name, PLZ, Straße, Telefon, E-Mail-Domain, Registernummer.
  - Harte Gegenbelege bleiben: andere Registernummer/-gericht, Rechtsform, PLZ, Ort.
  - Abweichender Name ist kein harter Gegenbeleg mehr, wenn PLZ **und** Straße **und** Telefon oder E-Mail-Domain passen → immer nur **Vorschlag**.
  - **Belegt** (automatisch übernommen) neu auch ohne Register: Name + vollständige Anschrift + Telefon oder E-Mail-Domain (drei unabhängige Merkmale).
- **Gespeichert werden keine Kontaktdaten:** In `discovery_candidates.match_hints_json` stehen nur E-Mail-Domain und ein Prüfwert der Telefonnummer (gekürzter SHA-256 der Ziffern). Der Prüfwert ist eine Pseudonymisierung, keine Anonymisierung; er wird nie angezeigt oder exportiert. Im lokalen OSM-Bestand kommt nur die Spalte `email_domain` dazu. Für gesperrte Firmen wird nichts gespeichert.
- **Angegebene Website gibt es nicht mehr:** Dann werden die Namensvarianten geprüft; die tote Adresse wird entfernt und im Beleg genannt.

### Firmen-Bericht (`sales_tool/report.py`)

- **Neuer erster Schritt „Website finden & zuordnen“:** Firmen ohne Website werden nicht mehr abgewiesen. Der Bericht sucht mit denselben Regeln (Abgleich gegen Name, Anschrift, Register, Telefon und E-Mail der Firma).
  - *belegt* → Website wird in das **leere** Feld eingetragen (Notiz in der Zeitleiste), danach laufen Impressum, Bewertung, Inhalte und Signale.
  - *Vorschlag* → nichts wird eingetragen; „Passt – Website übernehmen / Passt nicht“ im Bericht **und** in der Firmenakte (gleicher Weg `POST /api/leads/{id}/website-suggestion`). Abgelehnte Domains werden nicht erneut vorgeschlagen.
  - Domain auf der Sperrliste → wird nicht eingetragen.
  - Schritte, die eine Website brauchen, stehen ohne Website auf „übersprungen“; der Bericht heißt dann „teilweise“, der nächste Schritt „Website-Vorschlag im Firmen-Bericht prüfen“ bzw. „Website der Firma recherchieren“.
- **„Auf einen Blick“:** Kernfakten (Name, Anschrift, Registernummer, Telefon, E-Mail) mit Herkunft (Impressum/Firmendaten), wichtigste Hinweise mit Beleg, Lücken (z. B. „Registernummer fehlt, obwohl die Rechtsform eine Eintragung erwarten lässt“, „Website ohne Browser bewertet“, „Kontakterlaubnis ungeklärt – ein gefundener Kontaktweg ist keine Erlaubnis“), Kontaktstatus und Alter des Berichts (älter als 90 Tage → Hinweis „neu erstellen“). Die Übersicht ist rein lesend.
- Ältere Berichte ohne den neuen Schritt werden weiter angezeigt und können neu erstellt werden.

## 3. Datenschutz- und Kontakt-Leitplanken (Prüfliste)

| Punkt | Ergebnis |
|---|---|
| 1 Sperre | eingehalten – kein neuer Kontaktweg; Bericht prüft Sperre je Schritt, Vorschlag auf gesperrter Firma/Domain wird abgewiesen (`test_suggestion_on_blocked_company_is_refused`, `test_suppressed_domain_is_not_entered`, `test_blocked_company_report_does_nothing`) |
| 2 Reimport | eingehalten – gesperrte Treffer bleiben gesperrt, ohne Merkmale (`test_suppressed_company_gets_no_hints_and_no_search`) |
| 3 Keine Erlaubnis aus Daten | eingehalten – `permission` unverändert; Übersicht nennt „gefunden ≠ erlaubt“ |
| 4 Kein Versand | nicht betroffen |
| 5 Personen | eingehalten – keine Personen angelegt; Telefon/E-Mail nicht gespeichert, nur Domain bzw. Prüfwert (`test_hints_stored_without_plain_contact_data`) |
| 6 Datensparsamkeit | eingehalten – neue Felder betreffen Firmen, nicht Personen; nur Domain/Prüfwert; Löschung mit dem Treffer |
| 7 Lesende Auswertungen | eingehalten – `summary()` ändert nichts (`test_view_is_read_only`) |
| 8 Test | vorhanden (siehe oben) |

Rechtlich offen bleibt wie bisher: Ob ein Telefon-Prüfwert bei Einzelunternehmern als personenbezogenes Datum gilt, ist nicht abschließend geklärt; deshalb die vorsichtige Auslegung (nur Prüfwert, nur zum Abgleich, keine Anzeige).

## 4. Tests

- Neu: `tests/test_v2_website_matching.py` (19 Fälle, davon 1 Migration Schema 48 → 49), `tests/test_v2_report_glance.py` (13 Fälle), `tests/e2e/test_report_glance_browser.py` (Desktop und 390 px, Ablehnen eines Vorschlags, keine Abrufe nach außen).
- Angepasst: `test_sprintC_report.test_queue_rules` (Firmen ohne Website werden jetzt eingereiht).
- Ergebnisse dieses Stands: siehe Abschnitt 6.

## 5. Grenzen (ehrlich)

- **Nicht an echten Firmen gemessen.** Im Entwicklungscontainer gibt es keine Namensauflösung; die Wirkung auf die Trefferquote muss die Recherche-Messung (`docs/RECHERCHE_BENCHMARK.md`) an deiner Referenzliste zeigen.
- Domains, die weder aus dem Namen noch aus einer E-Mail-Adresse der Quelle folgen (Abkürzungen, Fantasienamen), findet die Suche weiterhin nicht. Eine Suchmaschinen-Abfrage ist bewusst nicht eingebaut (Kosten, Lizenz, Datenschutz).
- E-Mail-Domain und Telefon kommen nur aus OpenStreetMap; GLEIF, Wikidata und TED liefern sie nicht.
- Mehr Kandidaten heißt bei existierenden Domains mehr Abrufe (höchstens 12 statt 9 je Firma); nicht existierende Domains kosten nur eine DNS-Abfrage.

## 6. Prüfläufe (25.11.2026, Linux-Container)

| Prüfung | Ergebnis |
|---|---|
| Unit-Tests `python -m unittest discover -s tests` (Python 3.13) | 954 Tests; 1 Fehler im Lauf ohne Chromium-Pfad (`test_phase2_scoring.RealBrowserTests`, Umgebung), mit `SIGNALDESK_CHROMIUM_PATH` wiederholt: 12/12 grün; 1 übersprungen (optionales Paket) |
| Browser-Tests `tools/run_e2e.py --no-skips --min-tests 59` | 59 gefunden, 59 gelaufen, 0 übersprungen, 0 nicht bestanden |
| Python 3.10.20 (älteste zugesagte Version) | geänderte Module kompiliert; 57 betroffene Tests grün |
| Schema | `SCHEMA_VERSION` 48 → 49, Spalten per `ADD COLUMN` mit Vorgabewert, Migrationstest mit Sicherung |
| Release-ZIP | `SignalDesk-2.0.0-dev66.zip`, 248 Dateien, enthält `research/homepage.py` |
| Nicht geprüft | Windows/macOS (CI nach dem Push), echte Websites, Trefferquote an echter Referenzliste |

### Nachtrag: CI-Fehler in `test_appearance_browser` (nicht durch diese Änderung, aber behoben)

Die CI meldete beim ersten Lauf `('sand', 'dark', 'normal') != ('sand', 'dark', 'kompakt')`. Ursache: `theme.js` speicherte jede
Änderung sofort; bei zwei schnellen Klicks überholte die Antwort der älteren Anfrage die neuere und setzte die Dichte zurück.
Nachgestellt mit absichtlich verzögerter Antwort (`e2e/test_appearance_race_browser.py`): alter Code `['sand', 'normal']`,
neuer Code `['sand', 'kompakt']`. Änderungen werden jetzt nacheinander gespeichert; nur die Antwort der letzten Anfrage wird übernommen.
