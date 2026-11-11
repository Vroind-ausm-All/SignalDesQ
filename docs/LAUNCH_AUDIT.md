# Launch-Audit (Sprint 0 – Wahrheitscheck)

Stand: 11.11.2026. Geprüft wurde der tatsächlich ausgecheckte Code, nicht die Beschreibung in älteren Berichten.
Alles, was hier nicht selbst ausgeführt wurde, ist als „laut Doku“ gekennzeichnet.

## 1. Tatsächlicher Stand des Repositories

| Punkt | Befund |
|---|---|
| `main` | Commit `ce3312f`, v1.19.0 |
| Neuester Stand | Branch `codex/signaldesk-2.0-dev`, Commit `2f6785f`, **2.0.0-dev1** (ein Commit vor `main`, nicht zusammengeführt). Enthält die Übergabe `docs/UEBERGABE_FABLE.md` und `docs/MASTERPLAN_SOLOSELBSTAENDIGE.md`. |
| Arbeitsbranch | `claude/magical-sagan-wyimyr`, auf `2f6785f` vorgespult – die Arbeit baut auf dem Übergabestand auf, nicht auf v1.19 |
| Offene Pull Requests / Issues | keine |
| Sichtbarkeit | Das Repository ist **öffentlich**. Jeder Push ist damit öffentlich lesbar. |
| Skills im Projekt | keine (`.claude/skills`, `.agents/skills` fehlen) |
| Repo `Claude-Skills` | Commit `42a6229`: ausschließlich UI-, Animations-, Design- und Prototyp-Skills (shadcn, impeccable, animate, apple-design, prototype …). Nichts zu Recherche, Vertrieb, Datenschutz oder Release. Keine Überschneidung mit den im Auftrag genannten Skills. |

## 2. Tatsächliche Testergebnisse (in dieser Sitzung ausgeführt)

| Prüfung | Ergebnis |
|---|---|
| `python -m unittest discover -s tests` auf v1.19 (`ce3312f`), Python 3.13, Linux | 413 Tests, bestanden, 4 übersprungen |
| dasselbe auf 2.0.0-dev1 (`2f6785f`) | **426 Tests, bestanden, 4 übersprungen**. Die Übergabe nennt 425 Tests und 2 Überspringungen – die Zahl dort stimmt nicht mit dem Commit überein. |
| Übersprungen | 2 Browser-Tests des Website-Scorings (Playwright fehlt in der Grundausstattung), Scrapling, Trafilatura (beide optional) |
| Browser-Tests `tests/e2e` mit den festgeschriebenen Paketen (`requirements-lock-browser.txt`, Chromium vorinstalliert) | 2 von 2 bestanden (Arbeitstag, Leistungsprofil) |
| Quellen-Check des Programms, live | GLEIF ok, Nominatim ok, TED ok; **Wikidata HTTP 429** (Sperre ca. 17 min); **alle drei OpenStreetMap-Server überlastet oder nicht erreichbar** |
| Windows, macOS | hier nicht ausführbar. **Nachtrag 2.0.0-dev4:** Die CI war schon bei v1.19 rot (Python 3.10 und Windows); Ursachen und Behebung stehen im `SELF_REVIEW_LOG.md`, Arbeitspaket 3. |
| Reale Firmen-Websites | **nicht getestet.** Alle automatischen Tests nutzen fiktive Seiten. Der in der Übergabe verlangte Praxistest (50–100 Handwerksbetriebe, Raum Stuttgart) steht weiter aus. |

## 3. Matrix: Vorhanden / Teilweise / Defekt / Fehlt / Nicht erforderlich

| Bereich (Abschnitt im Auftrag) | Status | Beleg / Anmerkung |
|---|---|---|
| **UX (3)** „Heute“ mit Tagesplan, Wiedervorlage, Tagesabschluss | Vorhanden | `today.py`, `workday.py`; Browser-Test Arbeitstag grün |
| Navigation in 6 Bereichen | Teilweise | 9 Hauptpunkte + „Erweitert“ mit 6 weiteren (`public/index.html`) |
| Firmenakte | Vorhanden | `workday.lead_file`, `public/akte.js` |
| Pipeline-Karten anklickbar, nächster Schritt | Vorhanden | `public/pipeline.js`; Sackgassen-Liste `workday.dead_ends` |
| Neustartfeste Aufträge | Teilweise | `research/jobs.py` für Sammelsuche, Website-Suche, Firmen-Berichte. Eigene Threads ohne Wiederaufnahme: Quickscan, KI-Analyse, Kontakt-Recherche, Website-Scoring, Kaufsignal-Scan; Impressums-Stapel hat eigene Wiederaufnahme. |
| **Recherche (4)** Quellen GLEIF, Wikidata, OSM, TED | Vorhanden | `lead_finder.py`, `sweep.py`; Ausfall einer Quelle stoppt den Lauf nicht (Tests Sprint B) |
| `SourceProvider`-Schnittstelle | Teilweise | Quellen sind in `lead_finder.SOURCES` mit Lizenz und Hinweis beschrieben, die Abfrage selbst ist je Quelle eine eigene Funktion – keine gemeinsame Klasse mit Status, Limits und Datenalter |
| Großer GLEIF-Katalog offline (Streaming) | Vorhanden | `research/catalog.py`, Tests Sprint 4 |
| CSV-Import mit Spaltenzuordnung, Quarantäne, Wiederaufnahme | Teilweise | Import vorhanden (laut Doku bis 60 MB), keine freie Spaltenzuordnung, keine Quarantäne-Liste |
| OSM ohne öffentliche Server | Fehlt | kein lokaler Extrakt; heute live alle Server überlastet |
| Sicherer Website-Abruf (IP-Pinning, robots.txt, Grenzen) | Vorhanden | `research/fetchers`, `research/policy.py`, Tests Sprint 1 |
| Scrapling als schaltbarer Parser | Vorhanden | Messung v1.15; Abruf bewusst nicht eingebaut |
| Google Places | Nicht erforderlich | bleibt aus (Kosten, Bedingungen) |
| **Daten (5)** Beleg je Feld, Prüfstatus | Vorhanden | `company_facts`, `research/evidence.py` |
| Beobachtung / Hypothese / Frage / bestätigter Bedarf getrennt | Vorhanden | Firmen-Bericht, `workday.confirm_need` |
| Mehrere Rechtsträger und Standorte je Firmenakte | Fehlt | ein Lead = ein Rechtsträger; Dubletten-Regeln halten GmbH und GmbH & Co. KG getrennt, verknüpfen sie aber nicht |
| Score zeigt Kriterien und Belegabdeckung | Teilweise | Belegabdeckung vorhanden; der Lead-Fit selbst rechnet Unbekanntes als 0 |
| **Vertrieb (6)** Konfigurierbares Zielkundenprofil | **Defekt** | `model.score_lead` ist fest auf vier Agentur-Branchen, 20–200 Mitarbeiter und Budget ab 5.000 € verdrahtet. Handwerksbetriebe fallen in „Sonstige“. Das Leistungsprofil aus dev1 steuert nur die Inhaltsrecherche. |
| Passung vor / Qualifizierung nach dem Gespräch | Fehlt | Bedarfsanalyse wird erfasst, fließt aber in keine Bewertung |
| K.-o.- und Warnkriterien | Teilweise | Sperre setzt den Score auf 0; Auflösung laut Register, Ausschlussbranchen, Budget „keines“ wirken nicht |
| Gesprächsergebnisse, Rückrufzusagen | Vorhanden | `sales_workspace.create_call` |
| Folge nach „nicht erreicht“ / „Mailbox“ | **Defekt** | `workday.after_call` reagiert nicht; kein Versuchszähler, kein Zeitfenster |
| Verlustgründe | Fehlt | Phase „verloren“ ohne Grund |
| Einheitlicher Leistungskatalog | Teilweise | drei Listen: `model.OFFERS` (5), `sales_workspace.PACKAGES` (6), `pricing`-Katalog (26 Leistungen) |
| Festpreis mit interner Kalkulation, Kunde sieht keine Stunden | Vorhanden | `pricing.py`, Tests Sprint D |
| Verfügbare Kapazität, Nachkalkulation | Fehlt | |
| Kontaktsperre zentral, Widerspruch übersteht Reimport | Vorhanden | `workday.contact_lock`, Sperrliste; Tests Sprint 5 |
| Kein automatischer Versand | Vorhanden | keine Sendefunktion im Code |
| **Skills (7)** Projekt-Skills | Fehlt | siehe Abschnitt 1 |
| **SaaS (8)** Login mit Rollen | Teilweise | `auth.py`, optional, Einzelplatz |
| Mandantentrennung, PostgreSQL, getrennte Worker, Queue mit Dead-Letter, OIDC, Abrechnung, Monitoring | Fehlt | kein `organization_id` im Code; SQLite-Datei je Nutzer |
| Sicherung und Wiederherstellung | Vorhanden | `backup_restore.py`, Installationsprüfung in der CI |
| REST-Schnittstelle | Teilweise | über 100 Routen in einer Datei (`server.py`), keine OpenAPI-Beschreibung, keine Webhooks |
| ICS-Export, CSV-Exporte | Vorhanden | Termine, Buchhaltung |
| **Produkt (9)** Fiktiver Beispielbericht | Vorhanden | `/api/research/demo` |
| Geführter Erststart, Demo-Datensatz, Tarife, Landingpage, Nutzungsmessung | Fehlt | |

## 4. Die zehn wichtigsten Nutzungsprobleme

Grundlage ist die Code- und Ablaufprüfung. **Tests mit echten Nutzern gab es nicht** – die Reihenfolge ist eine begründete Einschätzung.

1. **Die Bewertung passt nicht zum Zielmarkt.** Ein Elektrobetrieb mit 8 Leuten bekommt wenige Punkte, weil Branche und Größe auf eine B2B-Agentur zugeschnitten sind.
2. **Vier Kennzahlen, kein Urteil.** Lead-Fit, Website-Score, Recherchepriorität und Belegabdeckung stehen nebeneinander; „lohnt sich der Anruf?“ beantwortet keine.
3. **„Nicht erreicht“ bleibt folgenlos.** Kein neuer Versuch, kein Zeitfenster, kein Abbruch nach mehreren Versuchen.
4. **Was im Gespräch geklärt wurde, ändert die Bewertung nicht.** Budget, Zeitpunkt und Entscheider stehen im Formular und sonst nirgends.
5. **Kein Verlustgrund.** Aus verlorenen Chancen lässt sich nichts lernen.
6. **Die wichtigste Quelle für Handwerksbetriebe ist unzuverlässig.** OpenStreetMap war beim Live-Check auf allen drei Servern überlastet.
7. **Homepage-Zuordnung** bei abweichender Marken-Domain bleibt begrenzt (Übergabe, Punkt 3) und ist an echten Firmen nicht gemessen.
8. **Drei Leistungslisten.** Empfehlungen, Angebotsvorlagen und Kalkulation nennen unterschiedliche Pakete.
9. **Eigene Erreichbarkeit und Kapazität fehlen.** Verpasste Anrufe, Rückrufzeiten und Auslastung haben keinen Ort.
10. **Einstieg.** Die README ist eine 430-Zeilen-Versionsgeschichte mit überholten Anleitungen; die Navigation hat 15 Einträge.

## 5. Die fünf größten technischen Risiken

1. **Keine Messung an echten Firmen.** Alle Qualitätszahlen stammen von 33 fiktiven Seiten.
2. **Öffentliches Repository mit Paketen im Verlauf.** `ausgabe/` enthielt zwei ZIP-Dateien (2,3 MB). Mit 2.0.0-dev4 entfernt; im Git-Verlauf bleiben sie abrufbar.
3. **Ein Prozess, eine SQLite-Datei, eine Datei mit allen Routen.** Für den Einzelplatz richtig; für SaaS fehlt jede Trennung nach Organisation.
4. **Fünf Hintergrund-Module ohne Wiederaufnahme** (siehe Matrix). Bei einem Absturz bleiben Läufe hängen.
5. **Abhängigkeit von überlasteten öffentlichen Diensten** (Overpass, Wikidata) ohne lokalen Ersatz.

## 6. Abhängigkeiten und Lizenzen

Unverändert gegenüber v1.19 laut `docs/BESTANDTEILE.md` und `sbom/signaldesk.cdx.json`: Kern ohne Fremdpakete; Varianten `browser`, `team`, `voll` mit festgeschriebenen Versionen und Prüfsummen. In dieser Sitzung wurde `requirements-lock-browser.txt` mit `--require-hashes` frisch installiert – erfolgreich. Neue Abhängigkeiten sind für das erste Arbeitspaket nicht nötig.

## 7. Einstufung

| Stufe | Stand |
|---|---|
| Implementiert und lokal getestet | lokaler Einzelplatz 2.0.0-dev1 |
| Live verifiziert | nur der Quellen-Check (3 von 7 Quellen erreichbar) |
| Pilotfähig (lokal, ein Nutzer) | bedingt: nach Praxistest an echten Firmen und Korrektur der Bewertung |
| Pilotfähig (SaaS) | nein |
| Öffentlich launchfähig | nein |
