# Bericht Masterplan 2.0 – Sprint 4 (SignalDesk v1.17)

Auftrag: „Sprint 4 umsetzen – Dubletten unbedingt erkennen und nicht doppelt aufführen“.

**Abnahme laut Plan:**
- ein großer synthetischer CSV-Test läuft ohne vollständiges Laden in den Arbeitsspeicher;
- identische LEIs werden nicht dupliziert;
- fremde Firmen werden nicht versehentlich zusammengeführt;
- fehlende Websites sind sichtbar.

## 1. Dubletten erkennen (`sales_tool/research/identity.py`)

Eine Regel für alle Stellen: Sammelsuche, Import, Katalog-Übernahme, Lead-Abgleich und CRM-Dubletten. Je Paar gibt es eines von drei Ergebnissen:

| Ergebnis | Wann | Folge |
|---|---|---|
| **sicher gleich** | gleiche LEI · gleiche Registernummer (Ort passt) · gleiche eigene Website (Name ähnlich oder gleicher Ort) · **gleicher Kernname** am gleichen Ort | automatisch zu **einem** Eintrag zusammengeführt (Sichtung) |
| **möglich** | Name ≥ 85 % ähnlich · gleicher Name, aber Ort fehlt · passt zu mehreren Firmen | **nicht doppelt aufgeführt**: erscheint beim Haupteintrag mit „Gleiche Firma / Andere Firma“ |
| **verschieden** | andere LEI · andere Registernummer · **andere Rechtsform** · anderer Ort · Name zu verschieden | bleibt getrennt |

**„Gleicher Kernname“** heißt: gleicher Name nach Abzug der Rechtsform, unabhängig von Umlaut-Schreibweise, Groß-/Kleinschreibung, Wortreihenfolge und Bindestrichen. Beispiele:
- Müller = Mueller;
- „Reith-Spezialkabel“ = „Reith Spezialkabel“;
- „Kabelwerk Reith“ = „Reith Kabelwerk“;
- „GmbH“ = „Gesellschaft mit beschränkter Haftung“.

**Was bewusst getrennt bleibt (Fehler der alten Logik behoben):**
- **GmbH ≠ GmbH & Co. KG ≠ Verwaltungs-GmbH.** Der alte Abgleich schnitt die Rechtsform ab, dadurch galt die KG als „schon Lead“, wenn die GmbH existierte. Steht im Rechtsform-Feld „GmbH“, im Namen aber „& Co. KG“, gewinnt die genauere Angabe.
- **Gleicher Name in Hamburg und Stuttgart** sind zwei Firmen. Ein Eintrag ohne Ort, der zu beiden passt, wird **nicht** automatisch zugeordnet („passt zu mehreren Firmen“).
- **Ähnlich, aber nicht gleich** (z. B. „Maschinenbau“ / „Maschinenbauer“) wird nie automatisch zusammengeführt, nur zur Prüfung gezeigt.
- **Plattform-Adressen** (facebook.com, jimdo, gelbeseiten …) zählen nicht als gemeinsame Website.
- **Website-Vorschläge** (Empfehlung A, noch nicht bestätigt) zählen für den Abgleich nicht.

**Schnell auch bei großen Mengen:**
- Verglichen wird nur innerhalb von Blöcken: Kernname, Namenswörter, Domain, Register, LEI.
- Sehr häufige Namensanfänge („Autohaus …“) werden übersprungen, solange ein genauerer Block passt.
- Gemessen bei 20.000 Firmen: 1,5 ms (RapidFuzz) bzw. 2,9 ms (difflib) je Abgleich. Gesucht waren 400 abgewandelte Namen („ue“ statt „ü“, ausgeschriebene Rechtsform); alle 400 wurden richtig zugeordnet.

**RapidFuzz** (Plan) ist **optional** (MIT, 12 MB). Ohne RapidFuzz rechnet SignalDesk mit Pythons difflib. Alle 32 Sprint-4-Tests liefern mit beiden dasselbe Ergebnis; RapidFuzz ist nur etwa doppelt so schnell.

## 2. Nicht doppelt aufführen – Sichtung (`sweep.py`)

- **Neue Treffer:**
  - „Sicher gleich“ wird beim Speichern sofort zusammengeführt: Quellen werden gebündelt und fehlende Angaben ergänzt.
  - „Möglich“ wird gespeichert, aber **beim Haupteintrag** angezeigt, nicht als eigener Eintrag. Zähler und Seitenzahl stimmen damit.
- **Entscheiden:**
  - **Gleiche Firma:** zusammenführen. Quellen, Schlüssel und fehlende Angaben wandern mit. Derselbe Fund im nächsten Suchlauf landet direkt beim Haupteintrag.
  - **Andere Firma:** eigener Eintrag; das Paar wird **nicht wieder vorgeschlagen**.
  - **Evtl. schon Lead:** ein Hinweis mit Link zum Lead und den Knöpfen „Ist dieser Lead“ / „Andere Firma“.
- **Prüfliste:** Status „Mögliche Dubletten prüfen“ im Filter, dazu ein Zähler in der Kopfzeile.
- **Übernehmen oder Verwerfen des Haupteintrags:** Seine möglichen Dubletten werden wieder sichtbar, mit Hinweis auf den übernommenen bzw. verworfenen Eintrag. Nichts geht verloren.
- **Bestand bereinigen:**
  - Beim Update auf Schema 23 läuft die Bereinigung einmal automatisch, mit Sicherung vorher.
  - Danach jederzeit über **„Dubletten prüfen“**.
  - Bereits Entschiedenes bleibt unverändert und dient nur als Anker.
- **Eintrag „Zusammengeführt“:** Er bleibt als eigener Status mit Verweis erhalten, damit jede Zusammenführung nachvollziehbar ist.
- **Fehlende Websites:** Jede Zeile zeigt „keine Website bekannt“. Die Kopfzeile zählt „n ohne Website“; ein Klick filtert die Liste auf diese Firmen.

## 3. Dubletten im CRM (`sales_tool/duplicates.py`)

- **Abgleich mit Leads** bei Übernahme, Impressums-Stapel, Kaufsignalen und „Bericht für Website“. Gezählt wird nur „sicher gleich“; die eigene Domain bleibt ein starker Beleg.
- **„Doppelte Firmen im CRM“** (Datenqualität & System) zeigt Paare mit Grund. **Zusammengeführt wird nie automatisch**, nur per Klick mit Rückfrage.
- **Beim Zusammenführen:**
  - Alle verknüpften Daten (30 Tabellen) wandern zum behaltenen Lead: Aktivitäten, Aufgaben, Belege, Berichte, Signale, Angebote, Sichtung und weitere.
  - Leere Felder werden ergänzt, nie überschrieben; die Notizen bleiben beide erhalten.
  - Bei eindeutigen Daten (z. B. eine Bewertung je Lead) gilt die des behaltenen Leads.
  - Die Aktivität und das unveränderbare Protokoll halten fest, was übernommen wurde.
- **Rechnungen:**
  - Festgeschriebene Rechnungen sind unveränderbar. Deshalb muss der Lead mit Rechnungen der behaltene sein; die Oberfläche wählt ihn automatisch.
  - Haben beide Leads Rechnungen, ist kein Zusammenführen möglich.
- **„Keine Dublette“** wird gespeichert und nicht wieder vorgeschlagen.

## 4. Großer Firmenkatalog offline (`sales_tool/research/catalog.py`)

- **GLEIF Golden Copy oder Delta** (LEI-CDF, CSV oder ZIP) lädst du im Bereich „Großer Firmenkatalog“:
  - Das Hochladen geht blockweise direkt auf die Platte (bis 3 GB, mit Prüfung des freien Speichers).
  - Der Import läuft als **Recherche-Auftrag** (Sprint 3): mit Fortschritt, abbrechbar und nach einem Neustart erneut ausführbar.
- **Streaming:** Die Datei wird zeilenweise gelesen, auch eine entpackte Golden Copy von mehreren GB. ZIPs werden nicht entpackt gespeichert.
- **Je LEI genau ein Eintrag** (Upsert):
  - **Vollbestand:** LEIs, die nicht mehr enthalten sind, gelten als „nicht mehr aktiv“; sie werden nicht gelöscht.
  - **Delta:** nur Änderungen.
  - Inaktive oder eingezogene Registrierungen werden markiert.
  - Ein unveränderter erneuter Import schreibt nichts neu.
- **Importprotokoll:** Datei, Art, Zeilen, neu / geändert / unverändert / nicht mehr aktiv, außerhalb Deutschlands, Dauer, Quelle und **Lizenz CC0 1.0**.
- **Suche:** Name (Umlaute egal, Volltextindex FTS5 in SQLite), PLZ-Anfang, Ort. Bereits Übernommenes ist markiert.
- **Übernahme:** Ausgewählte Firmen gehen **in die Sichtung**, mit Dubletten-Abgleich, nie direkt als Lead.
- **GLEIF-Ersatz:** Fällt die GLEIF-Schnittstelle aus, holt die Sammelsuche die übrigen Orte aus dem Katalog. Der Fortschritt sagt das ausdrücklich („aus dem lokalen GLEIF-Katalog, Stand …“). Ohne Katalog bleibt der Fehler sichtbar wie bisher.
- **Kommandozeile** für sehr große Dateien:

  ```bash
  python -m sales_tool.research.catalog datei.zip --db <SignalDesk-Datenbank>
  ```

- **Datensparsam:** Der Katalog liegt in einer eigenen Datei neben der Datenbank (`*.katalog.sqlite3`), damit die Arbeitsdatenbank klein bleibt.

### Messung DuckDB gegen SQLite (`tools/bench_catalog.py`, `docs/bench/v1.17-catalog.json`)

Synthetische GLEIF-Datei: 300.000 Zeilen, 63 MB, davon 288.000 deutsch.

| | SQLite (eingebaut) | DuckDB 1.5.6 (optional) |
|---|---|---|
| Import | 15,3 s | **1,1 s** |
| erneuter Import (unverändert) | 9,9 s | 0,35 s |
| Suche Name / PLZ / Ort | 11 / 36 / 37 ms | 9 / 0,9 / 0,9 ms |
| Größe | 95 MB (mit Volltext) | 18 MB |
| **Spitze Arbeitsspeicher** | **31 MB** | 343 MB |
| Umschrift Müller = Mueller | ja | nein (müsste nachgebaut werden) |
| Zusatzpaket | – | 58 MB |

**Entscheidung:** SQLite bleibt eingebaut.
- **Für SQLite spricht:**
  - Die Abnahme verlangt, große Dateien zu verarbeiten, ohne den Arbeitsspeicher zu füllen; DuckDB braucht dafür das Elffache.
  - SQLite ist in Python enthalten (kein Paket für Windows), und die Suche bleibt für die Bedienung schnell genug.
- **Für DuckDB spräche:** der deutlich schnellere Import.
- **Stand:** DuckDB ist gemessen, aber nicht eingebaut. Ein späterer Einbau als Schalter ist möglich, falls Importe über 1 Mio. Zeilen häufig werden.

Speicher im Testlauf (tracemalloc): 45.000 Zeilen bzw. 9,5 MB bleiben unter 6 MB Spitze. Eine 12,6-MB-Datei mit 60.000 Zeilen lag bei 3,2 MB.

## 5. Abnahme

| Kriterium | Nachweis |
|---|---|
| großer CSV-Test ohne vollständiges Laden | `test_large_csv_streams_with_bounded_memory` (Spitze < 6 MB und < 60 % der Datei); Messung mit 300.000 Zeilen: 31 MB RSS |
| identische LEIs nicht dupliziert | `test_same_lei_never_duplicated` (vier Quellen → ein Eintrag), `test_zip_and_identical_leis_not_duplicated`, `test_take_over_goes_through_dedupe` |
| fremde Firmen nicht zusammengeführt | `test_foreign_firms_not_merged` (GmbH / GmbH & Co. KG / Verwaltungs-GmbH / andere Stadt / andere HRB, LEI), Identitätsmatrix, `test_ambiguous_match_is_only_possible` |
| fehlende Websites sichtbar | `test_missing_websites_visible` (Filter „nur ohne Website“, Zähler „ohne Website“) |
| nicht doppelt aufgeführt (Nutzerwunsch) | `test_possible_duplicates_grouped_not_listed_twice`, Entscheidungen, Bereinigung des Bestands, Migration |

## Tests
- **Unit- und Integrationstests:** 376, alle grün.
  - 22 neu in `tests/test_sprintS4_dedupe.py`;
  - 10 neu in `tests/test_sprintS4_catalog.py`.
  - Die Sprint-4-Tests laufen zusätzlich mit RapidFuzz grün.
- **Browser-Test** (Chromium), ohne Konsolenfehler:
  - mögliche Dublette beim Haupteintrag, „Gleiche Firma“ → ein Eintrag mit 2 Quellen;
  - Prüfliste leer, „Dubletten prüfen“;
  - Katalog: ZIP laden → Auftrag → 2.880 Firmen, Suche „Mueller“ + PLZ 70, 3 übernommen und markiert;
  - CRM-Dubletten zusammenführen;
  - Handyansicht ohne seitliches Scrollen.

## Noch offen aus Sprint 4 / nächste Schritte
- **Website-Belege aus dem Katalog:** GLEIF liefert keine Websites. Sie kommen weiter über Wikidata (LEI → Website) und die Website-Suche mit Impressumsnachweis.
- **OSM/Wikidata-Ersatz bei Ausfall:** Es gibt keinen Offline-Bestand, der Quellen-Check zeigt den Ausfall. Ein OSM-Extrakt (ODbL) wäre ein eigener Schritt.
- **DuckDB als Schalter** nur bei Bedarf (siehe Messung).
