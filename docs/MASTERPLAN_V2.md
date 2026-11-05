# SignalDesk Masterplan v2 – Phasen, Gap-Analyse, Abnahmekriterien

Grundlage: „Claude Code Master-Prompt v2.0“ (10 Module, gemeinsame technische Anforderungen, 6 Sprints).
Stand der Codebasis bei Planerstellung: v1.2 (`main` nach PR #2), November 2026.

## Zielprozess

**Company Discovery → Datenanreicherung → Website-Audit → Signal-Erkennung → Lead-Scoring → Entscheider-Finder → Erstgespräch → Bedarfsklärung → Festpreisangebot → Follow-up**

Leitplanken für alle Phasen:
- **Belegbarkeit:** Unternehmens-ID, Quelltyp, URL, Originalbeleg, Fund-/Veröffentlichungsdatum, Verfahren, Prüfstatus und Belegqualität. KI-Interpretationen werden getrennt von geprüften Fakten gespeichert.
- **Sicherheit:** URL-Validierung, Schutz vor SSRF, DNS- und Redirect-Prüfung, Größenlimits, Rate-Limits je Domain, robots.txt beachten, keine Umgehung technischer Sperren, keine API-Schlüssel im Repository.
- **Recht:** keine Scraper für Google Maps, LinkedIn, Indeed, StepStone oder das Handelsregister. Ein Fund ist keine Einwilligung (§ 7 UWG). Bei Personendaten gelten Art. 6 und 14 DSGVO.
- **KI:** Ollama ist optional. Extraktion und Basisanalyse funktionieren ohne Sprachmodell. Die KI erfindet keine Personen, Kontakte, Budgets oder Probleme.
- **Abschluss jeder Phase:** lauffähiger Code, Tests und ein kurzer Bericht (implementiert / getestet / ungetestet / Grenzen / nächster Schritt). Netzwerk-Mocks gelten nicht als Live-Test.

## Gap-Analyse (Ausgangsstand v1.2)

| Modul | Stand | Vorhanden | Fehlt |
|---|---|---|---|
| 1 Company Discovery | teilweise | Lead-Finder: Wikidata, OSM/Overpass, GLEIF, TED; CSV-Import (≤ 50); Dubletten über Domain und Name | Manuelle Domainliste, PLZ und Radius, Google Places (bleibt aus); Live-Test der Quellen |
| 2 Impressum Intelligence | Ansatz | Kontakt-Crawler liest das Impressum, sucht dort aber nur Personen und Kontaktwege | Strukturierte Felder (Rechtsform, Anschrift, Register, USt-IdNr., Vertretung), PDF, mehrere Gesellschaften, Batch mit Pause/Fortsetzen, Prüfwarteschlange |
| 3 Website-Scorer v2 | Ansatz | Regelmodus bzw. Ollama mit ≤ 3 belegten Hypothesen; Lead-Score aus Branche und Signal | Rubriken, Screenshots, Ladezeit, defekte Links, Mobilprüfung, Teil-Scores, „Datenlage unzureichend“, Score-Versionen |
| 4 Register-Monitor | fehlt | manueller Link | Ereignismodell, manueller Import von Bekanntmachungen, Historie |
| 5 Job-Signale | fehlt | Signaltyp „offene Stelle“ (manuell) | Karriereseiten der Firmen, Import, Pro/Contra-Bewertung |
| 6 Decision Maker v3 | weitgehend | Rollen je Leistung, Team-Recherche, Beleg, Prüfstatus, Trennung fachlich/Budget/Entscheidung, keine geratenen Durchwahlen | Kontaktbeschränkungen je Person |
| 7 Signal-Korrelation | fehlt | – | Zusammenführung, Deduplizierung, Widersprüche |
| 8 Offer Matching | teilweise | Paketkatalog, Festpreis, Kunden-/Internsicht getrennt | Empfehlung aus bestätigten Problemen, Status unverbindlich/Grundlage, Paket „Automatisierung“ |
| 9 Datenqualität | teilweise | Dubletten über Domain und Name, Sperrstatus im Lead, Audit-Log (Buchhaltung) | Dubletten über Register, Prüfdatum je Feld, Sperrliste unabhängig vom Lead, Veraltungs-Kennzeichen, Datenschutz-Nachweise |
| 10 Sales Action Center | weitgehend | Tagescockpit, Gesprächsprotokoll mit Berechtigung, Wiedervorlagen, kein Versand | Aufgaben automatisch aus Rechercheergebnissen |

## Phasen

### Phase 0 – Fundament absichern ✅
- v1.1/v1.2 gemergt (PR #2), Branch auf `main` aktualisiert.
- Noch durch den Nutzer: Ein-Klick-Start unter Windows testen, Lead-Finder-Quellen live testen.

### Phase 1 – Datenbasis (Sprint 1; Module 2, 9 und Teile von 1) ✅ v1.3 – Bericht: `docs/BERICHT_PHASE1.md`
**Umfang**
1. **Belegmodell `company_facts`:** ein Datensatz je Feld mit Wert, Quelltyp, URL, Textbeleg, Verfahren, Fund-/Prüfdatum, Status (ungeprüft/bestätigt/verworfen/veraltet) und Belegqualität. Neue Firmenspalten im Lead für übernommene Werte.
2. **Sperrliste `suppression_list`:** Domain, Firmenname, Registernummer, E-Mail. Sie wird bei jeder Sperre automatisch gefüllt, gilt bei allen Importwegen und bleibt auch nach Löschen des Leads bestehen.
3. **Impressum-Extraktor:** Impressum-Link erkennen (nicht nur `/impressum`). HTML und einfache PDF-Dokumente. Mehrere Gesellschaften erkennen. Fehlende Felder bleiben `null`. Deterministische Regeln mit wörtlichen Belegen, Prüfsumme der USt-IdNr.
4. **Batch-Modus:** 1–100 Domains als Liste oder CSV. Begrenzte Parallelität, Rate-Limit je Domain, Pause/Fortsetzen (auch nach Neustart), Fehlerprotokoll, Ergebnis je Domain, Sperrlisten- und Dublettenprüfung, Prüfwarteschlange, manuelle Übernahme (neuer Lead oder bestehenden ergänzen).
5. **Datenschutz-Nachweise `privacy_records`:** Werden Vertretungsberechtigte übernommen, entsteht ein Nachweis mit Zweck, Rechtsgrundlage, Quelle, Löschfrist und Status der Art.-14-Information.
6. **Oberfläche:** Bereich „Datenprüfung“ (Batch, Fortschritt, Prüfwarteschlange, Sperrliste); im Lead „Firmendaten & Belege“ mit Feldstatus.

**Abnahme:** Tests für verschiedene Impressumsformate (GmbH & Co. KG mit Komplementärin, UG, e.K., verschleierte E-Mail, englisches Imprint, PDF, fehlende Angaben), Batch mit fehlerhaften/unerreichbaren Sites, Pause/Fortsetzen, Dubletten (Domain/Name/Register), Sperrliste bei allen Importwegen, Übernahme ohne Überschreiben bestätigter Werte, Regression aller bisherigen Tests.

### Phase 2 – Website-Bedarfs-Scorer v2 (Modul 3) ✅ v1.4 – Bericht: `docs/BERICHT_PHASE2.md`
Rubriken als Konfiguration; gerenderte Seiten und Screenshots (Desktop/Mobil) über Playwright; Ladezeit, defekte Links, Formulare und Kontaktwege; Teil-Scores Design/UX, Web/Conversion, Prozess/App, Passung, Signalaktualität, Belegabdeckung; Gewichtung 35/35/30 konfigurierbar; „Datenlage unzureichend“ statt Score; `score_versions` für Vergleichbarkeit; 3–5 Bedarfsfragen.
**Abnahme:** reproduzierbare Scores, Scoring mit fehlenden Daten, keine Kaufbereitschafts-Aussagen.

### Phase 3 – Buying Signals (Module 4, 5, 7) ✅ v1.5 – Bericht: `docs/BERICHT_PHASE3.md`
Job-Signale von Karriereseiten der Firmen und per manuellem Import (keine Portal-Scraper); Registerereignisse per manuellem Import von Bekanntmachungen; Ereignishistorie je Firma ohne Doppelmeldung; Signal-Korrelation mit Pro/Contra, Veröffentlichungs- vs. Funddatum, Widersprüchen und fehlenden Belegen.
**Abnahme:** alte Stellenanzeigen, doppelte Registerereignisse, widersprüchliche Signale.

### Phase 4 – Research Command Center (Oberfläche) ✅ v1.6 – Bericht: `docs/BERICHT_PHASE4.md`
Eine Arbeitsfläche für Suche, Batch-Aufträge mit Fortschritt, Prüflisten, priorisierte Firmen, Quellenansicht. URL-Recherche, Lead-Finder und Datenprüfung gehen darin auf. Alle Ergebnisse bearbeitbar, prüfbar, exportierbar.

### Phase 5 – Sales-Integration (Module 6, 8, 10) ✅ v1.7 – Bericht: `docs/BERICHT_PHASE5.md`
Angebots-Matching aus bestätigten Problemen (unverbindlich vor, Angebotsgrundlage nach Bedarfsklärung); Paket „Automatisierungsprojekt“; Rechercheaufgaben automatisch; Kontaktbeschränkungen je Person; Übergabe an Angebot und CRM.

### Phase 6 – Qualität & Skalierung ← nächster Schritt
Datenaktualisierung und Änderungserkennung, wiederkehrende Rechercheaufgaben, Veraltungs-Kennzeichen, konfigurierbare Gewichte der Recherchepriorität, Last- und Fehlertests, Sicherheitsprüfung, Migrationstest, Dokumentation; Vorbereitung Team/Cloud (Login, Rollen, Verschlüsselung).

## Offene Entscheidungen
- **Vertretungsberechtigte Personen speichern:** umgesetzt als abschaltbare Option (Standard: an) mit Datenschutz-Nachweis und Art.-14-Hinweis. Rechtliche Endabstimmung beim Nutzer.
- **Google Places:** bleibt deaktiviert, bis die EWR-Bedingungen geprüft sind und ein eigener Schlüssel vorliegt.
