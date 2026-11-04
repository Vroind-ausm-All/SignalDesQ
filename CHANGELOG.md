# Changelog

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
