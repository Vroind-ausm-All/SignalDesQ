# Changelog

## 1.14.0 – Live-Test der Quellen: Anpassungen an die echten Schnittstellen

Ein Live-Test aller offenen Quellen (11/2026) hat gezeigt, wo die Attrappen-Tests von der Wirklichkeit abwichen. Behoben:

- **GLEIF:**
  - Die API lehnt inzwischen jeden Ortsfilter ab.
  - SignalDesk nutzt jetzt sofort die erlaubten Filter (Volltext + Land + aktiv), also ohne zwei Fehlversuche je Ort.
  - Ortsteile („Stuttgart - Möhringen“) werden mitgenommen.
  - Die Rechtsform kommt aus dem offiziellen ELF-Code (alle 31 deutschen Codes).
  - Neue Auswahl „Wen suchst du?“: Unternehmen (Standard), Vereine/Verbände/Stiftungen, öffentliche Einrichtungen.
- **Wikidata:**
  - Wikidata drosselt bei Störungen auf „1 Anfrage pro Minute“ und sperrt bis zu 1000 s.
  - SignalDesk taktet jetzt selbst (2 s, im Störungsmodus 65 s), fragt während einer Sperre nicht erneut an und bricht lange Sperren sofort mit klarer Meldung ab, statt zu warten.
  - Websites per LEI kommen in einer Abfrage statt bis zu fünf.
- **Suchgebiet ohne Netzwerk:**
  - Ein mitgeliefertes Ortsverzeichnis (13,216 Orte, GeoNames CC BY 4.0, Großkunden-PLZ bereinigt) ersetzt die Umkreisabfrage bei Wikidata/OpenStreetMap.
  - Eine früher gespeicherte Notlösung „nur Mittelpunkt“ wird nicht mehr dauerhaft verwendet.
- **TED:**
  - Ausschreibungen kommen jetzt standardmäßig nur von Auftraggebern im Suchgebiet (serverseitiger Ortsfilter), mit Ort, PLZ und Entfernung.
  - „Bundesweit“ bleibt als Option.
- **OpenStreetMap:** höchstens 45 s je Server; ein nicht erreichbarer Server wird 10 Minuten übersprungen.
- **Quellen-Check** in „Firmen finden“: eine winzige Testanfrage je Quelle. Ergebnis: erreichbar, überlastet (mit Wartezeit), blockiert oder Format geändert.
- Rechtsform-Erkennung: „Gruppe“, „Group“ und „Holding“ gelten nicht mehr als Rechtsform; e.K. wird erkannt.
- Schema-Version 21 (`discovery_candidates.org_kind`).
- Weitere Live-Befunde:
  - Besitz- und Fondsgesellschaften (Grundbesitz, Wind-/Solarparks, „… III Management“, „Nr. 90 KG“) werden ausgefiltert.
  - Die TED-Gruppe „Software“ enthält keine Lizenzkäufe mehr (48000000 → 72230000).
  - Die Rechtsform wird beim Übernehmen in den Lead geschrieben.
  - Der Status zeigt „läuft“ auch bei Wiederholversuchen.
- Echte Sammelsuche Stuttgart 30 km: **285 s statt 856 s**, alle Treffer im Suchgebiet.
- 295 Tests (19 neu). Bericht: `docs/BERICHT_V114_LIVETEST.md`.

## 1.13.0 – Feedbackrunde: Ortsbezug, Überlastung, automatische Website-Recherche, gegliederte Aufgaben, kompakte Pipeline

- Ortsbezug:
  - Umkreis „nur dieser Ort“ (0 km);
  - TED-Ausschreibungen standardmäßig aus und als „bundesweit“ gekennzeichnet;
  - Sichtungsfilter Ort (mit Anzahl), Höchstentfernung und „ohne Ausschreibungen“.
- Überlastete Quellen (HTTP 429/502/503/504, Zeitüberschreitung):
  - automatische Wiederholung nach 20 s und 60 s, Retry-After wird beachtet (höchstens 2 min);
  - OpenStreetMap in Teilabfragen mit Teilerfolg;
  - Knopf „Fehlgeschlagene Quellen erneut abfragen“ (`POST /api/sweeps/{id}/retry`).
- Automatisierung:
  - Website-Suche startet nach jeder Suche automatisch (bis 200 Firmen, abschaltbar);
  - Impressumsdaten werden beim Übernehmen („belegt“) und im Firmen-Bericht automatisch in leere Lead-Felder geschrieben;
  - nie überschreiben, keine Personen anlegen, „wahrscheinlich“ bleibt ungeprüfter Beleg.
- Aufgaben:
  - gegliedert nach Recherche, Kontakt & Freigaben, Termine & Gespräche, Angebote & Abrechnung und Sonstiges;
  - Recherche je Firma zusammengefasst, Firmen-Berichte für alle mit einem Klick, Bereinigung erledigter Recherche-Schritte;
  - übernommene Firmen bekommen keinen Termin-Druck mehr („Firmen-Bericht erstellen“ ohne Datum);
  - auf „Heute“ ein Sammelpunkt statt vieler Einzelzeilen.
- Deal-Pipeline:
  - kompakte Karten (Name + Score), Details per Klick;
  - Drag & Drop und Click & Drop (⇄, dann Zielspalte; Touch/Tastatur; Esc bricht ab);
  - Spalte „Verloren“, Spalten mit eigener Scrollhöhe.
- Schema-Version 20 (`discovery_candidates.imprint_json`).
- 276 Tests (19 neu). Bericht: `docs/BERICHT_V113.md`.

## 1.12.0 – Sprint D: Angebote & Preise

- Leistungskatalog mit 26 Leistungen in 8 Bereichen, basierend auf deinem Angebot:
  - Kunst, Texte, Web- und Grafikdesign, Print, Logo;
  - Individualsoftware, Shop-Anbindung, Webshop;
  - Foto und Video, Werbung, SEO und GEO;
  - KI-Chatbot, Telefon-Sprachbot, Website-Analyse;
  - Workshops, Betreuung, Tagespauschale, Anreise, Leistung nach Aufwand.

  Meist in den Größen Basis, Standard und Umfangreich.
- Nachvollziehbare Festpreise:
  - Preis = Aufwand × Stundensatz + Puffer + enthaltene Fremdkosten.
  - Intern siehst du die vollständige Herleitung mit effektivem Stundenlohn und eine Warnung unter dem Mindestverdienst.
  - Kalkulationsgrundlagen sind einstellbar: 66 €/h, Tagespauschale, km-Satz, Fahrzeitanteil, Rundung.
  - Eigene Katalogwerte oder feste Preise lassen sich je Umfang hinterlegen.
- Angebots-Baukasten mit Positionen und Vorlagen. Die bisherigen Pakete sind jetzt Vorlagen; die passende lädt beim Wählen der Firma bzw. aus der Recherche.
- Kundendokument:
  - Positionstabelle mit getrennten Summen für einmalig und monatlich;
  - Kosten Dritter als „nicht im Festpreis“;
  - keine Stunden oder Sätze.
- Rechnung mit einer Zeile je Position; Monatsrechnung für laufende Positionen.
- 257 Tests (10 neu).

## 1.11.0 – Sprint C: Firmen-Bericht mit einem Klick

- Ein Auftrag mit fünf Schritten: Impressum & Firmendaten → Website-Bewertung → Website-Inhalte & Ansprechpartner → Karriereseite & Kaufsignale → Verknüpfen & Pakete. Status je Schritt; ein Fehler stoppt die anderen nicht.
- Berichtsseite mit Fakten (mit Fundstelle) getrennt von Interpretationen.
  - Firmendaten übernehmen und Ansprechpartner prüfen direkt im Bericht.
  - Pakete unverbindlich; Übergabe an CRM und Angebot.
- Ein Klick von überall:
  - Website eintragen (legt bei Bedarf den Lead an);
  - Stapel „Berichte erstellen“ (bis 50);
  - „Übernehmen & Bericht erstellen“ in Firmen finden;
  - Lead-Dialog und Pipeline-Phase „Recherche“.
- Rückfall ohne Browser für URL-Recherche, Entscheider-Recherche und Website-Analyse (vorher Abbruch mit „Playwright fehlt“).
- Navigation: „Firmen-Berichte“ statt Research Center; URL-Recherche, Website-Scoring und Kaufsignale als Recherche-Details unter „Erweitert“.
- Schema 19. 247 Tests (8 neu).

## 1.10.0 – Sprint B: Firmen finden, die wirklich funktionieren

- „Arbeitstag starten“: Sammelsuche über GLEIF, Wikidata, OpenStreetMap und TED mit einem Knopf.
  - Eingabe: Ort oder PLZ + Umkreis (Standard 30 km), 65 Branchen zum Anklicken, eigene Schlagwörter.
  - Fortschritt je Quelle; fällt eine Quelle aus, laufen die anderen weiter.
- Quellen repariert:
  - GLEIF mit Fallback-Kette bei HTTP 400 und seitenweiser Abfrage je Gemeinde;
  - Wikidata mit leichter Abfrage und Wiederholversuch bei 502;
  - OpenStreetMap mit drei Ausweichservern und 90 s Zeitlimit.
- Dubletten vermeiden: Zusammenführen über LEI, Registernummer + Ort, Domain und Name + Ort. Bekannte Leads, Sperrliste und verworfene Firmen erscheinen nicht erneut.
- Sichtung zum Durchklicken: Website in neuem Tab, Quellen-Links, Übernehmen und Verwerfen (auch per Taste und als Stapel), Filter und Sortierung, Gebiete & Suchläufe.
- Website-Suche mit Nachweis: Domain-Vorschläge, Prüfung über das Impressum („belegt“ bei gleicher Registernummer), allgemeine Kontaktwege aus dem Impressum.
- Großer Import bis 60 MB: GLEIF-Export und eigene Listen. Filter für aktive und operative Firmen sowie die PLZ-Region; Weiterleitung aus der Datenprüfung.
- Schema-Version 18. 239 Tests (16 neu).

## 1.9.0 – Sprint A: Struktur & Tagesablauf

- Navigation nach Arbeitstag: Heute, Aufgaben · 1 Kunden finden · 2 Recherchieren · 3 Verkaufen · 4 Abrechnen · Erweitert (eingeklappt).
- Neue Startseite „Heute“:
  - Tagesplan in 6 Schritten mit Direktsprung;
  - Wiedervorlage (Termine, Rückrufe, fällige Aufgaben, nächste Schritte, Nachfassen, Bindefristen, begonnene Bedarfsanalysen, offene Freigaben);
  - offenes Potenzial aus kalkulierten Angeboten (Schätzungen getrennt);
  - klickbare Pipeline mit nächster Aktion je Phase;
  - Funktionsstatus („Was funktioniert gerade?“).
- Pipeline-Ansicht: Aktion je Spalte und Karte (Kontakt aufnehmen, Termin vereinbaren, Angebot öffnen, Rechnung schreiben …) mit vorausgewählter Firma.
- „Mein Sales-Tag“ heißt jetzt „Kontakt & Termine“, geordnet nach Freigeben → Kontakt aufnehmen → Termin vereinbaren.
- Endpunkte `GET /api/today`, `GET /api/system/capabilities`. Schema unverändert.
- 223 Tests (7 neu). Masterplan v3 (`docs/MASTERPLAN_V3.md`).

## 1.8.0 – Phase 6: Qualität & Skalierung

- Bereich „Datenqualität & System“.
- Änderungserkennung (Impressum, Website, Register) mit Prüfpunkt, Übernahme nur nach Bestätigung.
- Wiederkehrende Rechercheaufträge (Impressen, Websites, Karriereseiten, gespeicherte Lead-Finder-Suche, Datenqualität) mit Hintergrund-Thread; abschaltbar mit `--no-scheduler`.
- Veraltungs-Kennzeichen je Datenart mit einstellbaren Fristen; Löschfristen für Personendaten mit Löschung nach Bestätigung (Löschnachweis ohne Namen).
- Konfigurierbare Gewichte der Recherchepriorität.
- Optionaler Login mit Rollen (admin, vertrieb, buchhaltung, lesen):
  - scrypt-Passwörter, sichere Sitzungs-Cookies, Bremse gegen Fehlversuche;
  - `--host` nur mit Login-Pflicht, `--allowed-host`, Notfallzugang `--reset-login`.
- Verschlüsselte Sicherung (AES-256-GCM, optional `cryptography`).
- Sicherheit:
  - Host-Prüfung gegen DNS-Rebinding;
  - `frame-ancestors`, `X-Frame-Options`, `Referrer-Policy`;
  - Anfragekörper muss ein JSON-Objekt sein (vorher 500 bei Aufgaben und Aktivitäten);
  - Widerspruch ohne Namen im Audit-Log.
- Neue Indizes. `prepare_database()` für Sicherung und Migration.
- Schema-Version 17.
- Migrationstests mit echten Altdatenbanken aus v0.9, v1.2, v1.6. Last- und Nebenläufigkeitstests, Fehler-Fuzzing aller Routen.
- 216 Tests (29 neu).

## 1.7.0 – Phase 5: Sales-Integration

- Angebots-Matching aus der Bedarfsanalyse mit wörtlichen Kundenzitaten; Recherche-Hinweise getrennt. Status „unverbindlich“ bzw. „Angebotsgrundlage“ (erst nach dokumentierter Bedarfsklärung); Budgethinweis; Übernahme ins Angebotsmodul.
- Neues Paket „Automatisierungsprojekt – ein Prozess digital“. Kundendokument mit Liefergegenständen, Abnahmekriterien und möglichen Drittanbieterkosten.
- Entscheider v3: fachlich / Budget / Entscheidung getrennt (unbekannt, vermutet, bestätigt) mit Prüfregeln, Rollenlandkarte je Thema mit Lücken, veröffentlichter Kontaktweg mit Fundstelle, Kontaktbeschränkungen je Person, Widerspruch → Sperrliste.
- Sales Action Center: Aufgabenvorschläge aus Rechercheergebnissen (übernehmen/verwerfen), eigene Freigabe je Kontaktaktion mit Kanal- und Rechtsprüfung, Erledigen ohne Freigabe gesperrt, Audit-Log.
- Schema-Version 16 (zwei neue Tabellen, zusätzliche Spalten in Kontakten und Aufgaben).
- 187 Tests (16 neu).

## 1.6.0 – Phase 4: Research Command Center

- Bereich „Research Center“ mit Einstiegskarten, Recherche-Trichter, laufenden Aufträgen aller Module und gemeinsamer Prüfliste.
- Priorisierte Firmenübersicht: Recherchepriorität mit Grundlage, „Datenlage unzureichend“, Recherchestand in 7 Schritten, nächster Schritt, Filter und Suche.
- Stapelaktionen für ausgewählte Firmen; Quellenansicht; Gesprächs-Dossier (Markdown/JSON); CSV-Export.
- Übergabe an CRM (Phase, Aufgabe, Aktivität; gesperrte Leads ausgeschlossen) und Angebot vorbereiten mit unverbindlichem Paketvorschlag.
- Navigation: Recherche-Werkzeuge unter „Research Center“ gruppiert, gemeinsame Unter-Navigation in jedem Recherche-Bereich.
- 171 Tests (9 neu).

## 1.5.0 – Phase 3: Buying Signals

- Registerereignisse per manuellem Import (Text/CSV): Neueintragung, Umbenennung, Geschäftsführer-/Prokurawechsel, Sitzverlegung, Strukturänderung, Auflösung als Gegenhinweis; Datenminimierung.
- Job-Signale aus Karriereseiten (eigene Domain, schema.org-JobPosting), Personio-XML-Feed und manuellem Import; Bereiche Prozess, Web & Marketing, Software mit Pro/Contra, Alter und Ablaufdatum.
- Dubletten per Schlüssel und quellenübergreifende Zusammenführung; Veröffentlichungs- vs. Funddatum; Neu-Markierung; Aktualitätsgewichtung ohne Löschen.
- Signal-Korrelation mit Hypothesen, Stärke, Gegenhinweisen, Widersprüchen, fehlenden Bestätigungen, Fragen und Paketen.
- Website-Scoring: Projektanlass aus echten Signalen; Übernahme bestätigter Signale in den Lead.
- Bereich „Kaufsignale“ und „Kaufsignale & Hypothesen“ im Lead-Dialog.
- Fix: Tab-Steuerung der Buchhaltung reagierte auf alle Tabs der Seite.
- 162 Tests (13 neu).

## 1.4.0 – Phase 2: Website-Bedarfs-Scorer v2

- Gerenderte Erfassung mit Chromium (Desktop + Smartphone, Unterseiten), Screenshots, Ladezeit, Datenmenge, Konsolenfehler, DOM-Messwerte; Linkprüfung interner Links.
- Browser-seitiger SSRF-Schutz für alle Unterressourcen; keine fremde Hauptnavigation, keine Downloads.
- 21 Rubriken in Design & UX, Web & Conversion, Prozess & App (Hypothesen); Bereich Kampagnen inaktiv mangels Katalogpaket.
- Getrennte Teil-Scores, Passung, Anlass, Belegabdeckung; Gesamtwert nur bei ausreichender Datenbasis.
- Konfigurierbares Raster mit Bewertungsversionen und Vergleich zur vorherigen Bewertung.
- Ergebnis je Firma: Beobachtungen, Fundstellen, Screenshots, Unsicherheiten, Pakete, Bedarfsfragen, nächster Schritt.
- Bereich „Website-Scoring“ und „Website-Bewertung“ im Lead-Dialog; HTML-Rückfall ohne Browser.
- 149 Tests (11 neu, davon 2 mit echtem Chromium).

## 1.3.0 – Phase 1: Datenbasis

- Masterplan v2 mit Gap-Analyse und Phasen (`docs/MASTERPLAN_V2.md`), Sprint-Bericht (`docs/BERICHT_PHASE1.md`).
- Feldbelege `company_facts` mit Quelle, wörtlichem Beleg, Verfahren, Qualität, Prüfdatum und Status; neue Firmenspalten im Lead.
- Sperrliste `suppression_list` (Domain, Name, Register, E-Mail) für alle Importwege, bleibt nach Löschen erhalten, Aufheben nur mit Begründung.
- Dubletten über Domain, Register (Gericht + Nummer) und normalisierten Namen.
- Impressum-Extraktor (HTML und einfache PDF, mehrere Gesellschaften, Prüfziffer USt-IdNr., verschleierte E-Mails, Fax-Unterscheidung, `null` bei fehlenden Angaben).
- Batch-Impressumsprüfung (1–100 Domains, CSV, Parallelität 1–3, Pause/Fortsetzen/Abbrechen, Neustart-sicher, Fehlerprotokoll, Prüfwarteschlange, Übernahme neu/ergänzen ohne Überschreiben).
- Datenschutz-Nachweise `privacy_records` mit Art.-14-Textbaustein und Fristenhinweis.
- Automatisches Backup vor Schema-Migrationen; Rechnungsempfänger aus geprüften Firmendaten.
- 138 Tests (23 neu).

## 1.2.0 – Ein-Klick-Start

- Neue Startdateien `SignalDesk_starten.bat` (Windows), `SignalDesk_starten.command` (macOS), `start.sh` (Linux): Doppelklick richtet beim ersten Mal alles ein und öffnet die Oberfläche automatisch im Browser.
- `python -m sales_tool.bootstrap`: legt `.venv` an, installiert den Crawler nur bei Bedarf (Merker mit Hash der Anforderungen), bei Fehlschlag höchstens ein neuer Versuch pro Tag; Start auch ohne Internet.
- Windows: Suche nach Python (py-Launcher, PATH, Benutzerinstallation); falls nicht vorhanden, Angebot zur Installation per winget oder Download-Seite. Hinweis, wenn die ZIP nicht entpackt wurde. Einmalige Desktop-Verknüpfung mit eigenem Symbol.
- Server: `--open-browser`; läuft SignalDesk bereits, wird nur der Browser geöffnet; belegter Port → nächster freier Port.
- `setup_windows.bat`/`start_windows.bat` leiten auf den neuen Start um.
- 115 Tests (10 neu).

## 1.1.0 – Lead-Finder

- Neuer Bereich „Lead-Finder“: Suche in Wikidata (CC0), OpenStreetMap/Overpass (ODbL), GLEIF (CC0) und TED-Ausschreibungen (CPV-Gruppen Web, Design, Software, Marketing).
- Datensparsam: nur Unternehmensdaten, Filter „nur Firmen mit Rechtsform“, keine Personen-, E-Mail- oder Telefondaten.
- Fair Use: User-Agent, 24-h-Cache, Mindestabstand 10 s, Tageslimit 40 Abfragen je Quelle; strikte Eingabeprüfung gegen Query-Injection.
- Dublettenprüfung gegen das CRM (Domain und normalisierter Name); einzelne oder ausgewählte Übernahme mit Quelle, Lizenz und Aktivität.
- Manuelle Quellen mit Ampel und Begründung (Handelsregister, Bundesanzeiger, Bekanntmachungsservice, Jobbörse, Gelbe Seiten, LinkedIn …).
- Neuer Kontaktweg „Öffentliche Ausschreibung“.
- Dokumentation `docs/LEADQUELLEN_V11.md`; 105 Tests (10 neu).

## 1.0.0 – Rechnungen & Buchhaltung

- Neuer Bereich „Rechnungen & Buchhaltung“ mit Übersicht, Rechnungen, Ausgaben/E-Rechnungen, Auswertung und Stammdaten.
- Rechnungen nach § 14 UStG mit Pflichtfeldprüfung, lückenloser Nummer je Jahr, Abschlags-/Schluss-/Stornorechnungen, Druckansicht (PDF über Browser).
- GoBD: Festschreibung per SQLite-Trigger, unveränderbares Änderungsprotokoll, eingefrorene Verkäuferdaten, Storno statt Löschen, Lead-Löschsperre bei Rechnungen.
- Steuer: Regelbesteuerung 19/7/0 %, Kleinunternehmer § 19 inkl. Grenzwarnung (25.000/100.000 €), Reverse Charge für EU-Kunden und § 13b-Eingangsleistungen.
- Zahlungseingänge (Teil-/Vollzahlung, Rücknahme), Mahnwesen in drei Stufen mit Verzugszinsen/Pauschale nach § 288 BGB.
- Ausgaben mit SKR03-Kontenvorschlag, GWG-Warnung, Storno.
- E-Rechnung: XRechnung-3.0-Export (UBL); Import von XRechnung (UBL/CII) und ZUGFeRD-XML mit unveränderbarer Archivierung des Originals.
- Auswertungen: UStVA-Vorbereitung (Kz 81/86/21/46/47/66/67, Ist/Soll), vereinfachte EÜR, Vertriebskennzahlen; CSV-Exporte; Backup per Knopfdruck.
- Angebote: Angebotsnummer `AN-JJJJ-NNNN`, Bindefrist 30 Tage, „angenommen“ setzt Lead auf „Gewonnen“ und schlägt die Rechnung vor.
- Fix: Inline-Styles wurden von der eigenen Content-Security-Policy blockiert (u. a. Prioritätsbalken in der Lead-Liste waren unsichtbar).
- 95 automatisierte Tests (28 neu).

# SignalDesk v0.9 – Sales Workspace und Festpreisprodukte

- Neuer Sales-Arbeitsplatz: Tagesagenda, Rechtsstatus pro Lead, manuell dokumentierte Gespräche, interne Follow-up-Aufgaben.
- Lokale Terminverwaltung inkl. manuellem ICS-Export und Aufgabe nach abgeschlossenem Termin.
- Mailentwürfe für vereinbarte Kommunikation inkl. Speichern und Wiederöffnen; kein Versand.
- Preis-/Angebotsmodul: 4 Projektpakete + monatliches Growth-Care-Paket, 5 Zusätze, interne Kosten-, Risiko- und Deckungsbeitragsrechnung, öffentlich klare Liefergegenstände und Festpreis.
- Gespeicherte Angebotsversionen, Kunden-Markdown ohne interne Kalkulation, steuerlicher Freigabecheck, Prüferinnerung nach manuell gesendetem Angebot.
- Neue SQLite-Tabellen: `calls`, `meetings`, `proposals`, `mail_drafts` (schonende Migration).
- Regressionen und neue API-Tests; browserseitige Interaktion mit lokaler API-Bridge verifiziert.

---

## 0.9.0 – Sales-Arbeitsplatz und Festpreisangebote

- Tagescockpit für Follow-ups und Termine, Gesprächsprotokolle mit Sperrlogik und vereinbarten Rückrufen.
- Interne lokale Terminverwaltung (keine externe Kalendersynchronisation) und Mailentwürfe ohne Versand.
- Paketkatalog für Design-, Web-, App- und Pflegeleistungen, definierte Add-ons und anpassbare Projektziele.
- Interne Kalkulation mit Kosten-/Risiko-/Margenwerten getrennt vom kundenorientierten Festpreisangebot mit Leistungsumfang, Ausschlüssen und Steuerhinweis.
- Angebote speichern und Kundenansicht getrennt exportieren; keine automatisierten Kontakte, keine versteckten Zusatzkosten.
- 67 automatisierte Tests erfolgreich.


## 0.8.0 – Entscheider-Finder v2 (manuelle Quellenprüfung)

- Rollenbasierte Web-/LinkedIn-Suchvorschläge im Ein-URL-Bericht und im Lead-Profil; keine automatisierte Social-/Suchmaschinen-Abfrage.
- Prüfworkflow für Kontakte mit Status, Quelle, Belegzitat, Funktion und Datum.
- Nachvollziehbare SQLite-Schema-Migration und PATCH-API für manuelle Verifikation.
- Sperrprüfung und Trennung von verifizierter Funktion, vermuteter Rolle und Kontaktberechtigung.
- 51 automatisierte Tests einschließlich HTTP und Datenmigration.


## 0.7.0 – Ein-URL-Recherche und Gesamtbericht

- Neuer Menüpunkt **URL-Recherche** direkt ab Dashboard, ohne Lead anlegen zu müssen.
- Nur ein einziger kontrollierter Abruf für Website-Beobachtungen **und** öffentlich sichtbare Kontakt-/Personenhinweise.
- Report enthält Quellen, wörtliche Belege, überprüfbare Hypothesen, Ansprechpartner-Kandidaten, allgemeine geschäftliche Kontaktdaten und neutrale Discovery-Fragen.
- Lokale Ollama-KI optional; klare Alternative im Regelmodus ohne KI. Fiktiver Demo-Bericht ohne externen Netzwerkabruf.
- Recherchen in `quick_scans` dauerhaft gespeichert, Status und Fehler sichtbar, Export als Markdown.
- Bewusste CRM-Übernahme mit Domain-Dublettenprüfung; gespeicherte Rechte/Signale werden nicht überschrieben; Personen und Befunde bleiben ungeprüft.
- Automatische Werbenachrichten, kostenpflichtige Kontaktdatenanbieter und erfundene Durchwahlen weiterhin ausgeschlossen.
- 44 Tests inklusive HTTP-, CRM-, Quellen-, Duplikat- und Rechte-Regressionstests.

## v0.6 · Öffentliche Entscheider-Recherche ohne Lusha

- Ein eigener Hintergrund-Job durchsucht bis zu 5 Seiten der Lead-Website nach Team-/Kontakt-/Impressumsinformationen, soweit für Crawler zugänglich.
- Quellenbasierte Personen-Kandidaten und voneinander getrennte allgemeine Firmenkontaktpunkte, inklusive manueller Freigabe.
- Zusätzliche SQLite-Tabellen `contact_research_runs` und `contact_candidates`; schonende Migration `business_email` für vorhandene Personenkontakte.
- Lusha-Module und kostenpflichtige API-Abfragen entfernt/deaktiviert; alte Kontakt- und CRM-Daten erhalten.
- Neue Endpunkte `/api/leads/:id/contact-research` und `/api/contact-candidates/:id/review`.
- Keine KI-Inferenz, keine erfundenen Durchwahlen, kein Auto-Versand.
- Tests für Rollenabgleich, fehlende Durchwahlen, HTTPS-Quelle, Dubletten, Sperrstatus, Archivierung und Endpoint-Deaktivierung.


## 0.4.0 – KI-Studio, sichtbare Ergebnisse & Deal-Board

- Eigenständiger Bereich `KI-Studio`: lokaler Ollama-Verbindungsstatus, Testtextanalyse im Browser (optional KI), echte Ergebnisse sichtbar.
- Text-Test ohne Internet/Crawler/CRM-Speicherung; explizit als Test markiert.
- Regelmodus mit vorsichtigen und wörtlich belegten Textmustern statt beliebiger generischer Vorschläge.
- Analyseverlauf aller Firmen mit Freigabe/Ablehnung, Quellen und Gesprächsfragen.
- Deal-Board inklusive manueller Phasenwechsel; einfacher Angebots-Pilot für Agenturgründer.
- Wiedervorlagen aus Lead-Feldern sichtbar; exportierbares Gesprächsbriefing mit Trennung Hypothese/Bestätigung.
- Neue API-Endpunkte `/api/ai/health`, `/api/ai/preview`, `/api/analyses`, `/api/leads/{id}/brief`.
- Automatisierte Regressionstests erweitert auf 27.

## 0.3.0 – Websiteanalyse
- Optionales Playwright und Ollama, Analysehistorie, Quellenprüfung, manuelle Freigabe.

## 0.2.0 – CRM und Bedarfsgespräch
- Kontakte, Bedarfsermittlung, CSV-Import, Wiedervorlagen.

## v0.5 · Entscheider & berufliche Durchwahlen
- Berufliche Kontakte inklusive Quellenbeleg, Zuständigkeitsrolle und DSGVO-schonender Löschmöglichkeit.
- Rollenempfehlung je Agenturleistung und Firmengröße; Recherche-Abkürzung statt automatisch erfundener Personendaten.
- Optionale Lusha v3 API: Vorschau und gesonderte, kostenpflichtige Freischaltung geschäftlicher Rufnummern.
- Mobil- und unbekannte Nummerntypen werden nicht übernommen; Do-not-Call-Flag wird angezeigt.
- Kein Auto-Outreach, keine kostenlose Zusage für reale Durchwahlen, kein Name-zu-Firma-Scraping.
- 34 automatisierte Tests inklusive Mock-Lusha-Antworten und HTTP-Flow.
