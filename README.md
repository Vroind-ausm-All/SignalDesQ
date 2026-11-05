# SignalDesk – Sales, Lead-Finder & Buchhaltung (lokal)

## Starten in zwei Schritten

1. **Herunterladen und entpacken**: auf GitHub *Code → Download ZIP*, danach Rechtsklick auf die ZIP-Datei → **„Alle extrahieren…“**.
2. **Doppelklick auf die Startdatei**:
   - **Windows:** `SignalDesk_starten.bat`
   - **macOS:** `SignalDesk_starten.command` (beim ersten Mal Rechtsklick → „Öffnen“, weil die Datei nicht von Apple signiert ist)
   - **Linux:** `./start.sh`

Beim **ersten Start** richtet SignalDesk alles selbst ein: Es sucht Python 3.10+ (unter Windows wird bei Bedarf die automatische Installation über winget angeboten), legt eine eigene Umgebung an, installiert den Website-Crawler und erstellt unter Windows eine **Desktop-Verknüpfung „SignalDesk“**. Danach **öffnet sich die Oberfläche automatisch im Browser**. Das dauert einmalig 1–3 Minuten.

**Ab dem zweiten Start** öffnet sich SignalDesk in wenigen Sekunden – per Desktop-Verknüpfung oder Startdatei. Läuft SignalDesk schon, öffnet ein weiterer Doppelklick nur das Browserfenster. Ist Port 8765 belegt, weicht SignalDesk auf den nächsten freien Port aus.

- Das schwarze Fenster offen lassen, solange du arbeitest. Schließen = SignalDesk beenden.
- Ohne Internet startet SignalDesk trotzdem; nur die Website-Recherche fehlt, bis der Crawler installiert ist (neuer Versuch einmal täglich oder mit `--reinstall`).
- Deine Daten liegen außerhalb des Programmordners (`%USERPROFILE%\.akquise-tool\`). Ein Update heißt: neue ZIP entpacken, alte Startdatei nicht mehr verwenden – die Daten bleiben erhalten. Vorher trotzdem ein Backup anlegen.

Ganz automatisch beim Herunterladen kann nichts starten: Browser und Betriebssystem führen heruntergeladene Dateien aus Sicherheitsgründen nie selbst aus. Ein Doppelklick ist das Minimum.

---

## v1.8 – Datenqualität, Sicherheit & Team-Vorbereitung

Neuer Bereich **„Datenqualität & System“**:
- **Änderungen erkennen:** Ein neu ausgelesenes Impressum, eine neue Website-Bewertung oder eine Registerbekanntmachung wird mit den vorhandenen Daten verglichen. Jede Abweichung wird zum Prüfpunkt; übernommen wird nur nach deiner Bestätigung.
- **Wiederkehrende Aufträge:** Impressen, Websites und Karriereseiten werden regelmäßig neu geprüft, gespeicherte Firmensuchen wiederholt. Alles läuft über die bestehenden Schutzmechanismen, ohne Kontaktaufnahme.
- **Veraltungs-Kennzeichen** mit einstellbaren Fristen und **Löschfristen für Personendaten** (Löschen auf Klick, Löschnachweis ohne Namen).
- **Gewichte der Recherchepriorität** sind einstellbar.
- **Team-Vorbereitung:** Optionaler Login mit Rollen (admin, vertrieb, buchhaltung, lesen) und **verschlüsselte Sicherungen** (`pip install -r requirements-team.txt`). Wie man SignalDesk sicher im Team betreibt, steht in [`docs/BETRIEB_UND_TEAM.md`](docs/BETRIEB_UND_TEAM.md).
- **Sicherheitsprüfung** mit behobenen Befunden (u. a. Schutz vor DNS-Rebinding und Einbetten): [`docs/SICHERHEITSPRUEFUNG_V18.md`](docs/SICHERHEITSPRUEFUNG_V18.md). Der Migrationstest läuft mit echten Altdatenbanken ab v0.9.
- Sprint-Bericht: [`docs/BERICHT_PHASE6.md`](docs/BERICHT_PHASE6.md)

## v1.7 – Sales-Integration

- **Angebots-Matching:** Pakete aus dem Leistungskatalog werden aus den **bestätigten Aussagen der Bedarfsanalyse** abgeleitet, mit wörtlichem Zitat. Hinweise aus Recherche und Website-Bewertung stehen getrennt daneben. Vor der dokumentierten Bedarfsklärung ist jede Empfehlung **unverbindlich**, danach kann sie mit einem Klick als **Angebotsgrundlage** ins Angebotsmodul übernommen werden.
- **Neues Paket „Automatisierungsprojekt“.** Das Kundenangebot zeigt jetzt auch Liefergegenstände, Abnahmekriterien und mögliche Drittanbieterkosten.
- **Entscheider v3:** Fachliche Zuständigkeit, Budget und finale Entscheidung werden je Person getrennt geführt (unbekannt / vermutet / bestätigt). Dazu kommen eine Rollenlandkarte mit Lücken, ein veröffentlichter Kontaktweg mit Fundstelle und **Kontaktbeschränkungen** (keine Anrufe, nur Brief, Widerspruch …).
- **Sales Action Center:** Aufgabenvorschläge aus deinen Rechercheergebnissen. **Jede Kontaktaktion braucht eine eigene, dokumentierte Freigabe** (Kanal, Rechtsgrundlage, Beschränkungen der Person) und lässt sich vorher nicht abhaken. Versendet wird nichts.
- Sprint-Bericht: [`docs/BERICHT_PHASE5.md`](docs/BERICHT_PHASE5.md)

## v1.6 – Research Command Center

Neuer Bereich **„Research Center“** – eine Arbeitsfläche über alle Recherche-Werkzeuge (Firmen finden, Datenprüfung, URL-Recherche, Website-Scoring, Kaufsignale):
- **Priorisierte Firmenübersicht** mit Recherchestand in 7 Schritten, Befunden, nächstem Schritt und einer transparenten **Recherchepriorität** (40/30/30 aus Website, Kaufsignalen und Lead-Fit; Grundlage aufklappbar). Ohne Website-Bewertung und Signale steht dort „Datenlage unzureichend“.
- **Laufende Aufträge** aller Module mit Fortschritt und eine gemeinsame **Prüfliste** für alles, was auf deine Entscheidung wartet.
- **Stapelaktionen:** Impressum prüfen, Websites bewerten, Karriereseiten prüfen, Signale verknüpfen.
- **Gesprächsvorbereitung** je Firma (Fakten getrennt von Hypothesen, Fragen, unverbindliche Pakete) als Markdown/JSON, eine **Quellenansicht** und ein **CSV-Export**.
- **Übergabe an CRM** (Phase „qualifiziert“ + Aufgabe, bei ungeklärtem Kontakt zuerst „Kontaktweg klären“) und **Angebot vorbereiten**.
- Sprint-Bericht: [`docs/BERICHT_PHASE4.md`](docs/BERICHT_PHASE4.md)

## v1.5 – Kaufsignale: Register, Stellen, Hypothesen

Neuer Bereich **„Kaufsignale“**:
- **Registerbekanntmachungen** (Neueintragung, Umbenennung, Geschäftsführerwechsel, Sitzverlegung, Strukturänderung, Auflösung) werden per Einfügen oder CSV importiert. Es gibt keinen Register-Scraper, Geburtsdaten werden entfernt.
- **Stellenanzeigen** kommen von der Karriereseite der Firma (inkl. schema.org-Stellendaten), aus dem offiziellen Personio-Feed oder per manuellem Import, nicht von Jobportalen. Jede Stelle erhält Pro- **und** Contra-Deutung (z. B. „Inhouse statt Agentur“).
- **Signal-Korrelation** pro Firma: Register-, Stellen- und Website-Signale werden zu Hypothesen („Möglicherweise …“) mit Stärke, Gegenhinweisen, Widersprüchen, fehlenden Bestätigungen und Gesprächsfragen verknüpft. Korrelation ist keine Kausalität.
- Dubletten über Quellen hinweg werden zusammengeführt. Alte Signale zählen weniger, gelöscht wird nichts.
- Der **Projektanlass** im Website-Scoring nutzt jetzt echte, datierte Signale.
- Sprint-Bericht: [`docs/BERICHT_PHASE3.md`](docs/BERICHT_PHASE3.md). Mit fiktiven Testdaten geprüft; der Live-Test mit echten Karriereseiten und Bekanntmachungen steht noch aus.

## v1.4 – Website-Bedarfs-Scorer v2

Neuer Bereich **„Website-Scoring“**: SignalDesk rendert die Website mit Chromium auf dem Desktop und als Smartphone, speichert Screenshots, misst Ladezeit und Datenmenge, prüft interne Links und bewertet 21 Rubriken in drei Bereichen (Design & UX, Web & Conversion, Prozess & App). Jede Rubrik erhält „auffällig“, „ok“ oder „unbekannt“ mit Messwert und Fundstelle.
- **Getrennte Werte** für Design, Web, Prozess, Passung, Projektanlass und Belegabdeckung. Der Gesamtwert (35/35/30, einstellbar) entsteht nur bei ausreichender Datenbasis, sonst „Datenlage unzureichend“.
- **Pro Firma:** priorisierte Beobachtungen, Screenshots, Unsicherheiten, passende Pakete (unverbindlich), 3–5 Bedarfsfragen, nächster Schritt.
- **Bewertungsraster konfigurierbar.** Jede Änderung ist eine eigene Version, damit Ergebnisse vergleichbar bleiben.
- Sprint-Bericht: [`docs/BERICHT_PHASE2.md`](docs/BERICHT_PHASE2.md). Mit echtem Chromium gegen lokale Testseiten geprüft; der Test mit öffentlichen Websites steht noch aus.

## v1.3 – Datenbasis: Impressumsprüfung, Feldbelege, Sperrliste

Neuer Bereich **„Datenprüfung“**: Bis zu 100 Firmendomains (Liste oder CSV) prüfen. SignalDesk findet das Impressum, liest Firmenname, Rechtsform, Anschrift, Handelsregister, USt-IdNr. (mit Prüfziffer), allgemeine Kontaktwege und vertretungsberechtigte Personen. Jeder Wert erscheint mit **wörtlichem Beleg**; übernommen wird nur, was du bestätigst. Aufträge lassen sich pausieren und fortsetzen, auch nach einem Neustart.
- **Sperrliste:** Widersprüche gelten für alle Importwege und bleiben, auch wenn der Lead gelöscht wird.
- **Feldbelege** im Lead („Firmendaten & Belege“) mit Prüfstatus je Feld. **Datenschutz-Nachweise** und Art.-14-Textbaustein für übernommene Personen.
- **Automatische Sicherung** der Datenbank vor jedem Schema-Update.
- Phasenplan: [`docs/MASTERPLAN_V2.md`](docs/MASTERPLAN_V2.md) · Sprint-Bericht: [`docs/BERICHT_PHASE1.md`](docs/BERICHT_PHASE1.md)

**Hinweis:** Mit fiktiven Testseiten geprüft; der Live-Test mit echten Websites steht noch aus.

## v1.1 – Lead-Finder

**Neu in v1.1 – Lead-Finder:** Neue Firmen und öffentliche Ausschreibungen aus offen lizenzierten Quellen finden: Wikidata (CC0), OpenStreetMap (ODbL), GLEIF (CC0) und EU-Ausschreibungen auf TED. Treffer prüfst du einzeln, Dubletten werden erkannt, und Übernahmen landen mit Quelle und Lizenz als Lead in Phase „Recherche“. Gespeichert werden nur Firmendaten, keine Personen, E-Mails oder Telefonnummern. Register, Branchenbücher und soziale Netzwerke sind mit Ampel und Begründung als manuelle Links eingebunden.

→ Welche Quellen sind erlaubt und welche Kontaktwege zulässig? [`docs/LEADQUELLEN_V11.md`](docs/LEADQUELLEN_V11.md)

**Hinweis:** Die Quellen-Adapter folgen den dokumentierten API-Formaten, konnten in der Entwicklungsumgebung aber nicht live abgefragt werden. Bitte beim ersten Start je Quelle eine Testsuche machen.

---

## v1.0 – Sales, Angebote & Buchhaltung

**Neu in v1.0:** Der Weg vom angenommenen Angebot bis zum Zahlungseingang ist jetzt im Tool: Rechnungen mit Pflichtangaben nach § 14 UStG, lückenlose Nummern, GoBD-Festschreibung mit Storno statt Löschen, Zahlungen, Mahnwesen, Ausgaben inkl. Reverse Charge, **E-Rechnung (XRechnung) erzeugen und empfangen**, UStVA-/EÜR-Vorbereitung, CSV-Exporte für die Steuerberatung und Backups per Knopfdruck.

- Menü **„Rechnungen & Buchhaltung“** → zuerst **Stammdaten & Sicherung** ausfüllen.
- Angebot auf **„angenommen“** setzen → Lead wird „Gewonnen“ → Abschlags-, Schluss- oder Monatsrechnung mit einem Klick.
- Festgeschriebene Rechnungen sind unveränderbar, Korrektur per Stornorechnung. Leads mit Rechnungen sind nicht löschbar (Aufbewahrungspflicht).
- Nichts wird automatisch versendet oder an ELSTER/DATEV übermittelt.

**Was fehlt noch / was ist Pflicht?** → [`docs/GAP_ANALYSE_V10.md`](docs/GAP_ANALYSE_V10.md)
**Bedienung, Regeln & API** → [`docs/BUCHHALTUNG_V10.md`](docs/BUCHHALTUNG_V10.md)

**Update von v0.9:** Vorher `%USERPROFILE%\.akquise-tool\akquise.sqlite3` sichern. Neue Tabellen und Spalten werden beim Start schonend ergänzt; bestehende Daten bleiben erhalten.

**Wichtig:** Keine Steuerberatung. Erzeugte XRechnungen vor dem ersten Kundenversand mit dem [KoSIT-Validator](https://github.com/itplr-kosit/validator) prüfen; UStVA-Werte sind eine Vorbereitung und müssen vor der Übermittlung geprüft werden.

**Tests:** `python -m unittest discover -s tests -q` (171 Tests).

---

# SignalDesk v0.9 – Sales Workspace & transparente Festpreisangebote

**Neu:** Die bestehende v0.8 Website- und Entscheider-Recherche ist jetzt mit einer vollständigen **lokalen Vertriebsarbeitsoberfläche** verbunden: Tagescockpit, manuelles Telefonprotokoll, Terminverwaltung mit .ics-Export, gespeicherte Mailentwürfe, automatische interne Wiedervorlagen und Produktpakete mit Kundendokumenten.

### Neu starten (Windows)

- `setup_windows.bat` einmalig ausführen, `start_windows.bat` starten, dann `http://127.0.0.1:8765` öffnen.
- Links **Mein Sales-Tag** und **Angebote & Preise** auswählen. Leg vorher über „Neuer Lead“ eine fiktive Testfirma an.
- **Keine E-Mail-/Kalender-/Telefonverbindung notwendig.** Ohne Ollama funktionieren die neuen Module vollständig offline. Für bestehende Website-Recherche wird Internet benötigt.
- **Datensicherung vor dem Wechsel:** `%USERPROFILE%\.akquise-tool\akquise.sqlite3` sichern. Neue Tabellen werden schonend ergänzt.

**Festpreislogik:** Kunde erhält einen ergebnisorientierten Festpreis mit klar definierten Liefergegenständen, Ausschlüssen, möglichen Fremdkosten und dem zutreffenden Steuerstatus. Interne Bearbeitungsstunden, Kosten und Deckungsbeitrag bleiben ausschließlich für deine Kalkulation sichtbar. Kein versteckter Aufpreis und keine Stundenabrechnung im Kundenangebot.

**Wichtige Grenzen:** Kein Cloud-Hosting, kein Mehrbenutzerbetrieb, keine Rechnung/E-Signatur, keine automatischen Anrufe oder E-Mails, keine echte Kalender-Synchronisierung. Angebots- und Preiswerte sind Annahmen und müssen an reale Kosten, Vertragsrecht und Steuersituation angepasst werden.

- [Neue Features, Bedienung und API](docs/VERTRIEBSZENTRALE_V09.md)
- [Produktisierte Leistungspakete](docs/PRODUKTISIERTE_ANGEBOTE_V09.md)
- [Mail-/Kalenderanbieter vergleichen](docs/MAIL_KALENDER_ANBIETERAUSWAHL.md)
- [30-Tage-Plan und Skalierungsphasen](docs/VERTRIEBSPROZESS_ZUM_ERSTEN_KUNDEN.md)

---

# SignalDesk v0.9 – Sales-Workspace und lösungsorientierte Festpreisangebote

**Neu:** „Mein Sales-Tag“ für Aufgaben, Gesprächsprotokolle, vereinbarte Rückrufe, Termine und Mailentwürfe sowie „Angebote & Preise“ für produktisierte Lösungen. Alles läuft lokal und ohne E-Mail-/Kalenderanbieter. Es gibt keinen Nachrichtenversand und keinen Telefonanruf aus der App.

**Kundenangebot und interne Kalkulation getrennt:** Du wählst aus fünf Ausgangslösungen (Website-Pilot, B2B-Conversion-Sprint, Marken-/Designsystem, Growth Care, Kundenportal-MVP) und konkreten Zusatzleistungen. Die interne Berechnung verwendet geschätzten Aufwand, interne Kalkulationskosten, Fremdkosten, Risikoaufschlag und Zielmarge. Im Kundenangebot stehen Ergebnis, vollständiger Leistungsumfang, Abgrenzungen, Lieferung, Korrekturrunden, ausgewiesene Zusatzleistungen, Zahlungsbedingungen, fest vereinbarter Gesamtpreis und gekennzeichneter Steuerstatus – **keine internen Stundenwerte**. Preise sind Muster-Hypothesen, keine Marktgarantien; vor Versand individuell prüfen. Keine versteckten verpflichtenden Kosten.

**Windows:** `setup_windows.bat` starten, danach `start_windows.bat` und `http://127.0.0.1:8765` öffnen. Menü „Mein Sales-Tag“ / „Angebote & Preise“ auswählen. Ohne Ollama können Angebotskalkulation, Nachfassmanagement und Entwürfe genutzt werden. Datenbank vor einem Versionswechsel sichern: `%USERPROFILE%\.akquise-tool\akquise.sqlite3`. Lokalhost-App ohne Authentifizierung, **nicht öffentlich hosten**.

**Produktgrenze:** Termine sind interne Einträge, keine synchronisierten Kalendereinladungen; Mails sind Entwürfe, keine versendeten Nachrichten; Call-Ergebnisse sind Gesprächsnotizen, keine Telefonintegration. Bei Opt-out blockieren und keine weitere Werbung. Anfragen oder bereits legitimierte Gesprächsfortsetzungen getrennt von Werbeansprache prüfen. Für den nächsten Ausbau: Microsoft 365 oder Google Workspace anbinden, OAuth/Tokens lokal geschützt verwalten, automatisches Aussenden nur nach separater rechtlicher und technischer Prüfung.

**Test:** `python -m unittest discover -s tests -q`. Testabdeckung einschließlich Migration, Festpreisvorschau, gespeicherte Angebote, Calls, Termine, Mailentwürfe und alte CRM-Module. Externer Websiteabruf und Ollama müssen weiterhin auf dem eigenen Rechner live geprüft werden.

---

# SignalDesk v0.8 – Firmenwebsite eingeben, Recherchebericht bekommen

**Lokale Windows-Web-App für eine junge Medienagentur.** Eine URL genügt: überprüfbare Website-Beobachtungen, mögliche Verantwortliche, öffentlich veröffentlichte Geschäftskontakte und Fragen für das Erstgespräch werden in einem zentralen Bericht angezeigt. **Ohne Lusha, ohne Massenansprache, optional mit lokalem Ollama.**

## Neu in v0.8 – Entscheider-Finder v2

**Was funktioniert:** Nach einer URL-Recherche erscheint im Bericht ein Abschnitt „Entscheider-Finder v2“. Er empfiehlt anhand des wahrscheinlich passenden Leistungsangebots konkrete Zielrollen und erzeugt *nur manuell zu öffnende* Suchlinks für zusätzliche Webquellen sowie Suchmaschinentreffer mit `site:linkedin.com/in/`. Dabei werden weder LinkedIn noch Suchmaschinen automatisiert ausgelesen. Klickst du anschließend auf „Nach Prüfung ins CRM übernehmen“, kannst du im Lead-Profil die Suchlinks erneut aufrufen und die recherchierten Personen mit Quellenbeleg überprüfen.

**Prüfschritte im Lead:** Person und Firma → Quellen-URL → wörtlicher Beleg → zuständige Funktion → tatsächliche Entscheidungsrolle. Im Kontaktformular kannst du zwischen „Ungeprüft“, „Quelle geprüft“, „Rolle bestätigt“ und „Quelle veraltet“ wählen. Für geprüfte/bestätigte Einträge ist ein konkreter Beleg erforderlich; eine als „entscheidung“ kategorisierte Rolle verlangt eine ausdrücklich bestätigte Rolle. Dies ist eine **menschliche Dokumentation**, keine automatische Verifikation. Quelle und Prüfdatum werden in SQLite gespeichert.

**Abgrenzung:** Kein LinkedIn-Scraping, kein Google-Scraping, keine personenbezogenen Telefonnummern aus Mustern, kein automatisierter Kontaktversand. Die neuen externen Suchlinks müssen per Klick geöffnet werden. Nur Website-Seiten derselben Domain werden von der bestehenden Rechercheautomatik gelesen. Ein Suchmaschinentreffer oder öffentliches Profil ist weder eine bestätigte Budgetvollmacht noch eine Kontaktberechtigung.

**Neue API:** `GET /api/leads/{id}/contacts` enthält zusätzlich `research_plan`; `PATCH /api/contacts/{id}` speichert `verification_status`, `decision_role`, `source_url`, `source_excerpt`, `linkedin_url` und `note`. Schema wird bei Programmstart schonend um `verification_status`, `verification_date`, `source_excerpt` erweitert. Vor dem Update eine Datenbanksicherung anlegen.

**In 3 Minuten testen:** SignalDesk starten → URL-Recherche → fiktiven Beispielbericht laden → unter „Entscheider-Finder v2“ die Zielrollen/Suchlinks ansehen (ohne öffnen zu müssen) → bei echtem Scan ins CRM übernehmen → Lead öffnen → „Entscheider & geschäftliche Durchwahlen“ → Kontakt und Quellenprüfung ausfüllen. Für ersten Test ist weder Ollama noch ein API-Key nötig.

## Schnellstart auf Windows

1. Python **3.10 oder neuer** installieren (Python Launcher `py` muss verfügbar sein).
2. Den Ordner `SignalDesk-v08` aus dem ZIP entpacken und **`setup_windows.bat`** einmalig ausführen. Das installiert Playwright und Chromium; Internet erforderlich.
3. **`start_windows.bat`** starten und im Browser **http://127.0.0.1:8765** öffnen.
4. Menüpunkt **„URL-Recherche“** wählen. Zuerst mit **„Fiktiven Beispielbericht ansehen“** die Oberfläche anschauen (keine echten Firmendaten).
5. Eine echte Website mit `https://` eingeben und im **Regelmodus ohne KI** recherchieren. Der Crawler prüft bis zu fünf öffentlich zugängliche verlinkte HTML-Seiten. Die Recherche wird gespeichert, aber noch **nicht** als Lead angelegt.
6. Optional für umfassendere Hypothesen lokal **Ollama** von https://ollama.com/download/windows installieren, im PowerShell-Fenster `ollama pull qwen3:8b` ausführen und im Formular „Lokale KI · Ollama“ auswählen.
7. Ergebnis prüfen, Quellen öffnen, auf Wunsch **„Nach Prüfung ins CRM übernehmen“** wählen. Befunde und Personen bleiben im CRM vorerst **ungeprüft**. Anschließend die Lead-Detailansicht öffnen und einzeln bestätigen oder verwerfen.

**Wichtige Grenzen:** Der Regelmodus erkennt nur explizite Textsignale – **keine echte Performance- oder UX-Messung**. Auch lokale KI kann aus einer Website keinen bestätigten Kaufbedarf ableiten. Rollen und Namen sind Vorschläge, keine nachgewiesenen Entscheidungsvollmachten. Die Recherche ermittelt keine unveröffentlichten persönlichen Durchwahlen. DSGVO und § 7 UWG gelten unabhängig von der Datenquelle.

**Wenn eine Websiteanalyse fehlschlägt:** URL prüfen, robots.txt und Nutzungsbedingungen respektieren, Chromium-Installation sicherstellen, bei Ollama-Modus prüfen ob Ollama läuft und `qwen3:8b` geladen ist. Viele dynamische Seiten sind bei ausgeschaltetem JavaScript eingeschränkt lesbar. Eine fehlende Antwort ist **kein** Beleg für fehlenden Bedarf.

**Migration:** Standard-Datenbank unter `%USERPROFILE%\.akquise-tool\akquise.sqlite3`. Vor dem Versionswechsel eine Sicherung erstellen. v0.7 ergänzt die Tabelle `quick_scans`; die bisherigen Leads und bestätigten Aussagen werden nicht überschrieben. CRM-Import erkennt bereits bekannte Firmendomains und übernimmt nur neue **ungeprüfte** Befunde/Kandidaten. Gesperrte Leads werden nicht importiert.

**Sicherheit:** Die App bindet nur `127.0.0.1`, hat keinen Login und ist **nicht für öffentliches Hosting** geeignet. Kein automatisches E-Mail-, Telefon- oder LinkedIn-Outreach. Die Website wird auf dem Rechner gecrawlt; der Ollama-Modus wertet Texte lokal aus und sendet sie nicht an OpenAI/Claude.

**API für den neuen Ablauf:** `POST /api/research` mit `{"url":"https://firma.de","provider":"rules"}` oder `"ollama"` → Hintergrundlauf-ID. `GET /api/research/{id}` → Status und Ergebnis. `GET /api/research` → Verlauf. `GET /api/research/demo` → fiktiver Bericht. `POST /api/research/{id}/import` mit `{"confirm":true}` → bewusste CRM-Übernahme. Alle bisherigen CRM-APIs bleiben erhalten.

**Tests:** `python -m unittest discover -s tests -v` (51 Tests). Der externe Crawl und Ollama müssen auf deinem Windows-PC noch mit realen Websites getestet werden; Browser-Klicktests waren in der Erstellungsumgebung durch Zugriffssperren eingeschränkt.

Weitere Details: [`docs/ENTSCHEIDER_FINDER_V2.md`](docs/ENTSCHEIDER_FINDER_V2.md), [`docs/AKQUISE_NAECHSTE_30_TAGE.md`](docs/AKQUISE_NAECHSTE_30_TAGE.md), [`docs/EIN_URL_WORKFLOW_V07.md`](docs/EIN_URL_WORKFLOW_V07.md).

---

## Bisheriger Funktionsumfang (bis v0.6)

**Lokale Windows-Web-App für eine Medienagentur**, mit überprüfbarer Website-, Entscheider- und Bedarfsanalyse. Keine API eines kommerziellen B2B-Datenhändlers und kein automatischer Nachrichtenversand.

## Neu in v0.6 – Eigene Kontakt-Recherche statt Lusha

- Im Firmenprofil **„Öffentliche Entscheider recherchieren“** wählen. Nach Bestätigung werden bis zu fünf öffentlich zugängliche Seiten der jeweiligen Firma geprüft (Team, Ansprechpartner, Kontakt, Über uns, Impressum, soweit verlinkt).
- Namen werden **nur als Kandidaten** vorgeschlagen, wenn eine berufsbezogene Rolle in unmittelbarer Nähe steht; keine behauptete Entscheidungsvollmacht.
- Allgemein veröffentlichte Telefonnummern und E-Mails werden als **Firmen-Kontaktwege** angezeigt und nicht ohne Beleg einer bestimmten Person zugeschrieben.
- Eine persönliche geschäftliche Durchwahl wird nur dann einem Kandidaten zugeordnet, wenn Name und Kennzeichnung als **Direktwahl/Durchwahl auf derselben Textzeile** vorkommen. Keine Nummernmuster, keine Vorhersage.
- Jeder Treffer zeigt die **Quellen-URL, einen Textausschnitt und den Prüfstatus**. Du öffnest die Quelle und wählst selbst **„Ins CRM übernehmen“** oder „Verwerfen“.
- Historie je Lead, verständliche Fehlermeldungen, dauerhafte Speicherung in SQLite. Alte Kontakte bleiben erhalten; die Lusha-Endpoints sind dauerhaft deaktiviert (HTTP 410). Kein Lusha-Key nötig.
- Kein LinkedIn-Scraping, keine Google-Ergebnisscrapes, kein Harvesting aus privaten Bereichen oder Umgehen von Sperren.

**Einrichten:** Python 3.10+ und `setup_windows.bat` einmalig ausführen (installiert Playwright + Chromium); dann `start_windows.bat` starten und im Browser `http://127.0.0.1:8765` öffnen. In einem gespeicherten Lead mit HTTPS-Website den neuen Rechercheknopf drücken. **Ollama wird für die Kontaktrecherche nicht benötigt**; das KI-Studio kann optional separat genutzt werden.

Wichtig: Fehlende Direktnummern werden nicht erfunden. Der Crawler kann nur öffentlich erkennbare HTML-Inhalte auslesen, die robots.txt und Nutzungsbedingungen zulassen; nicht jede Website liefert Personen oder Telefonnummern. Die Recherche stellt **keine Erlaubnis zur Werbung** dar.

Ausführliche technische Grenzen: [`docs/EIGENE_ENTSCHEIDER_RECHERCHE_V06.md`](docs/EIGENE_ENTSCHEIDER_RECHERCHE_V06.md).

## Neu in v0.4 – Website mit sichtbaren KI-Ergebnissen und Deal-Pipeline

- **KI-Studio** als eigenständige Seite: lokale Ollama-Verbindung prüfen, fiktiven Website-Text einfügen, ohne Ollama im Regelmodus testen und Ergebnisse direkt im Browser sehen. Keine CRM-Speicherung im Test.
- **Echte Websiteanalysen zentral ansehen**: Lead auswählen, bis zu fünf öffentliche Seiten prüfen, Analyseverlauf und belegte Befunde sichten und Freigabe/Ablehnung manuell dokumentieren.
- **Deal-Board**: Leads nach Pipeline-Phasen gruppieren, Status direkt ändern; Wiedervorlagen aus Lead-Profilen werden jetzt neben Einzelaufgaben angezeigt.
- **Bedarfsbriefing herunterladen**: Aufklärung von Hypothesen und bereits bestätigten Kundenantworten, als Markdown-Datei für deine persönliche Gesprächsvorbereitung.
- **Einstiegsangebot** für die ersten Kunden: klar abgegrenzter Website-/Anfrage-Pilot (990–2.500 € Preisidee; muss am Markt validiert werden).

**Für den ersten Test:** `setup_windows.bat` → `start_windows.bat` → `http://127.0.0.1:8765` → `KI-Studio` → `Fiktives Beispiel laden` → `Analyse starten`. Das funktioniert **auch ohne** Ollama. Für echte KI erst Ollama installieren und `ollama pull qwen3:8b` ausführen.

Bedienung und API: [`docs/KI_STUDIO_V04.md`](docs/KI_STUDIO_V04.md).

## Schnellstart (Python 3.10+, keine Pakete installieren)

```bash
cd SignalDesk-v06
python -m sales_tool
```

Danach [http://127.0.0.1:8765](http://127.0.0.1:8765) öffnen. Alternativ:

```bash
python -m sales_tool --port 8989 --db ./meine-leads.sqlite3
python -m unittest discover -s tests -v
```

Die Daten liegen standardmäßig in `~/.akquise-tool/akquise.sqlite3`. Firmenwebsites werden zum Abruf extern kontaktiert, die Kontaktdaten selbst nicht an einen Datenhändler gesendet; optionales Ollama läuft lokal. Das Tool ist für **eine einzelne Person auf dem eigenen Rechner** gebaut und bindet ausschließlich `127.0.0.1`. Bitte nicht ohne Authentifizierung, TLS, Benutzerrechte, CSRF/Rate-Limits und Datenschutzprüfung öffentlich betreiben.

## Basis-CRM-Funktionen (v0.2)

- Firmen, Branchen, Größen, öffentliche Veränderungssignale, Beleg-URLs und Signalalter verwalten.
- Transparenter **0–100-Prioritätsscore** aus Markt-Fit, Signal, Quellenbeleg, Aktualität, angenommenem Budget und Angebotsfit. **Keine Abschlusswahrscheinlichkeit.**
- CRM-Stufen: Recherche → Qualifiziert → Kontakt geprüft → Rückmeldung → Termin → Angebot → Gewonnen/Verloren; Sperrstatus.
- Aufgaben/Wiedervorlagen mit Fälligkeit, Aktivitäten als interner Gesprächsverlauf.
- Dashboard mit Pipeline-Zahlen und ungewichtetem **Budgetpotenzial** (nicht Umsatzprognose).
- Angebots-Playbook mit drei initialen Leistungspaketen und Preis**hypothesen**.
- Manuell nutzbarer Gesprächsleitfaden; **keine API für das automatische Versenden** von E-Mail, LinkedIn, WhatsApp oder Anrufen.
- Löschung eines Leads inklusive Aktivitäten und Aufgaben (SQLite CASCADE).
- Keine Test-Leads oder fingierten Pipeline-Ergebnisse vorbefüllt.

## Neu: Erstkontakt und Bedarfsanalyse (v0.2)

- Kontakte um **Standort, Funktion und Kontaktweg** ergänzt; vorhandene SQLite-Dateien werden beim Start schonend migriert.
- Je Lead gibt es ein separates **Bedarfsanalyse-Formular**, das fünf Kernfragen anhand tatsächlich bestätigter Kundenantworten erfasst. Eine Vollständigkeitsanzeige ist **keine KI-Prognose**.
- CSV-Import von bis zu 50 Firmen pro Schritt mit grundlegender Formatprüfung und Dublettenprüfung (Firmenname/Website). Keine importierten Kontakte werden automatisch angesprochen.
- Leere CSV-Vorlage: `vorlagen/leads_import_vorlage.csv`. Erläuterungen: `docs/DATENMODELL_UND_ERSTGESPRAECH.md`.
- **Wichtig**: Die Recherche-Priorität ist kein validierter Bedarf. Der Nachweis des Bedarfs entsteht erst im Discovery-Gespräch.

## Website- und KI-Bedarfsanalyse (v0.3)

Eine Website pro Lead wird auf Knopfdruck mit **Playwright** (maximal fünf öffentliche, robots.txt-geprüfte Seiten) gelesen. **Ollama** (`qwen3:8b`) erzeugt daraus höchstens drei Bedarfs**hypothesen** samt wörtlichem Textbeleg und neutraler Frage für das Erstgespräch. Die App verwirft Befunde mit fehlender oder ungültiger Quelle; du prüfst und bestätigst jeden Vorschlag selbst. Option **Regelmodus ohne KI**.

- Websiteanalyse im Lead-Modal, Hintergrundstatus und Rechercheverlauf
- Tabellen `analysis_runs` und `findings`, inkl. bestehende SQLite-Datenbank erhaltender Migration
- Quellennachweise, Freigeben/Verwerfen und explizites Übernehmen ohne Überschreiben existierender Signale
- Keine automatischen Nachrichten, keine Kontaktberechtigung aus öffentlich sichtbaren Daten abgeleitet
- Funktioniert auf Windows lokal; Ollama benötigt keinen ChatGPT-/Claude-Login.

Für Windows kannst du auch einmalig `setup_windows.bat` und danach `start_windows.bat` doppelklicken. Die Einrichtung lädt Playwright/Chromium, aber installiert Ollama **nicht automatisch**.

**Windows-Installation, vollständige Bedienung, technische Grenzen**: [`docs/WEBSITE_ANALYSE_V03.md`](docs/WEBSITE_ANALYSE_V03.md).

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
.\.venv\Scripts\python.exe -m playwright install chromium
# Ollama separat installieren: https://ollama.com/download/windows
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m sales_tool
```

Das bestehende CRM kann weiterhin **ohne Installation externer Python-Pakete** gestartet werden. Der Website-Crawler benötigt zwingend Playwright und Chromium; der KI-Modus zusätzlich ein laufendes Ollama mit installiertem Modell.

## Empfohlene Bedienung

1. Branchenfokus und erstes Angebotsformat festlegen (`docs/AKQUISE_STRATEGIE_2026.md`).
2. Pro Firma **einen realen Quellenbeleg** zu einem relevanten Veränderungssignal erfassen.
3. Annehmen, dass ein hoher Score eine **Recherchepriorität**, nicht die Erlaubnis zur Ansprache ist.
4. Kontaktstatus und Grundlage dokumentieren; zulässigen Kanal separat prüfen.
5. Discoverygespräch protokollieren, konkreten nächsten Schritt terminieren, Pipeline aktualisieren.
6. Wöchentlich nur echte Fortschritte und Gewinne messen.

## Repo auf GitHub veröffentlichen

Das Ziel `Sales/Akquise-Tool` bedeutet in GitHub **Owner/Repository**. `Sales` muss ein GitHub-Konto oder eine Organisation sein, für die du die nötigen Rechte hast. Einen bloßen GitHub-Ordner namens Sales gibt es auf dieser Ebene nicht.

Wenn `Sales` dein GitHub-Owner ist, z. B. mit [GitHub CLI](https://cli.github.com/) nach `gh auth login`:

```bash
gh repo create Sales/Akquise-Tool --private --source=. --remote=origin --push
```

Wenn `Sales` **nur ein Arbeitsbereich/Ordner** sein soll, nutze stattdessen dein eigenes GitHub-Konto als Owner und nenne das Repo z. B. `Akquise-Tool`. **Default: privat**, da das Tool personen-/unternehmensbezogene CRM-Arbeit unterstützt. Niemals deine SQLite-Datenbank mitpushen (`.gitignore`).

## Technik

Python-Standardbibliothek (`http.server`, `sqlite3`, `json`) + responsives, frameworkfreies HTML/CSS/JS. REST-Endpunkte: `/api/config`, `/api/leads`, `/api/leads/import`, `/api/leads/:id`, `/api/leads/:id/discovery`, `/api/tasks`, `/api/tasks/:id`, `/api/activities`, `/api/stats`. Die SQLite-Datenbank wird beim ersten Start erstellt.

## Dokumentation

- [`docs/ANALYSE_AGENTUR_CONSULTING.md`](docs/ANALYSE_AGENTUR_CONSULTING.md) – öffentlich überprüfbarer Produkt- und Funnel-Abbau
- [`docs/AKQUISE_STRATEGIE_2026.md`](docs/AKQUISE_STRATEGIE_2026.md) – konkreter 12-Wochen-Plan für Q4 2026
- [`docs/RECHTLICHES.md`](docs/RECHTLICHES.md) – deutsche Akquise-, Datenschutz- und Betriebsrisiken
- [`docs/ROADMAP.md`](docs/ROADMAP.md) – Folgeversionen, Integrationen und Nicht-Ziele

## Grenzen

Keine gekauften Lead-Datenbanken, keine Drittanbieter-Kontaktanreicherung, kein n8n-Workflow, keine Cloud-KI, keine automatische Sendefunktion, kein Nutzerlogin und keine Anbindung an externe CRMs. Der einzelne, streng begrenzte Website-Crawler dient nur der manuellen Recherche. Diese Funktionen sind bewusst nicht vorgetäuscht: Die Website des analysierten Anbieters beschreibt solche Prozesse, stellt deren internen Code jedoch nicht öffentlich verifizierbar bereit.

## Lizenz

MIT – eigener Quellcode. Fremde Marken, Screenshots und proprietäre Vorlagen sind **nicht** enthalten. Quellenlinks in der Analyse sind ausschließlich zur Nachprüfbarkeit aufgeführt.
