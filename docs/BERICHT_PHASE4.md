# Sprint-Bericht Phase 4 – Research Command Center (v1.6)

Gemäß Masterplan v2 und Master-Prompt v2.0, Abschnitt „Benutzeroberfläche“ und Sprint 4.

## Was ist tatsächlich implementiert?

Neuer Bereich **„Research Center“** als zentrale Arbeitsfläche. Die bisherigen Recherche-Bereiche liegen jetzt darunter, sowohl in der Seitennavigation als auch als gemeinsame Unter-Navigation in jedem Recherche-Bereich: Firmen finden, Datenprüfung, URL-Recherche, Website-Scoring, Kaufsignale. Die zehn Punkte aus dem Master-Prompt:

| Nr. | Anforderung | Umsetzung |
|---|---|---|
| 1 | Branchensuche und Firmenfindung | Einstiegskarte „Firmen finden“ führt in den Lead-Finder (offene Quellen, Ampel) |
| 2 | Domain- und CSV-Stapelimport | Einstiegskarte „Domains & CSV prüfen“ öffnet die Datenprüfung. Stapelaktion „Impressum prüfen“ für ausgewählte Firmen |
| 3 | Fortschritt laufender Rechercheaufträge | Liste „Laufende Aufträge“ über alle Module: Lead-Finder, Impressumsprüfung (mit Fortschrittsbalken), Website-Bewertung, Karriereseiten, URL-Recherche, Entscheider-Recherche. Aktualisiert sich, solange Aufträge laufen |
| 4 | Impressums- und Datenprüfung | Recherche-Schritt „Impressum geprüft“, Anteil der Firmendaten, Prüfliste für ungeprüfte Feldbelege und ausgelesene Impressen |
| 5 | Website-Bedarfs-Scoring | Website-Wert und Belegabdeckung je Firma (bzw. „unzureichend“), Stapelaktion „Websites bewerten“ |
| 6 | Register- und Stellenanzeigen-Signale | Pro, Contra und neue Signale je Firma, Stapelaktionen „Karriereseiten prüfen“ und „Signale verknüpfen“, Prüfliste für neue und nicht zugeordnete Signale |
| 7 | Entscheider-Recherche | Anzahl geprüfter bzw. bestätigter Entscheider je Firma, Prüfliste für Kandidaten, Sprung in den Lead-Dialog |
| 8 | Priorisierte Firmenübersicht | Tabelle mit **Recherchepriorität** samt aufklappbarer Grundlage (Gewichtung 40/30/30 aus Website-Wert, Kaufsignalen und Lead-Fit; fehlt ein Teil, werden die Gewichte neu verteilt und das wird angezeigt). Ohne Website-Bewertung **und** ohne Kaufsignale erscheint **„Datenlage unzureichend“**. Dazu der Recherchestand in 7 Schritten, die Befunde und der nächste sinnvolle Schritt als Direktsprung. Filter: bereit, unzureichend, neue Signale, inkl. abgeschlossener Firmen; Suche |
| 9 | Gesprächsvorbereitung | Dossier je Firma: geprüfte Firmendaten (Fakten mit Quelle), Website-Beobachtungen mit Unsicherheiten, Kaufsignale, Hypothesen mit Gegenhinweisen und Fehlendem, Ansprechpartner (ohne bestätigte Befugnis), bereits im Gespräch Bestätigtes, Fragen fürs Erstgespräch, mögliche Pakete (unverbindlich). Fakten und Interpretationen sind getrennte Abschnitte. Export als Markdown und als JSON mit allen Quellen |
| 10 | Übergabe ans CRM und Angebotsmodul | „An CRM übergeben“ setzt die Phase von Recherche auf Qualifiziert, legt eine Aufgabe an und protokolliert eine Aktivität. Ist der Kontaktstatus ungeklärt, heißt die Aufgabe „Kontaktweg klären“, nicht „Erstgespräch“. Gesperrte Leads werden abgewiesen. „Angebot vorbereiten“ öffnet das Angebotsmodul mit vorgewählter Firma und unverbindlichem Paketvorschlag |

**Zusätzlich:**
- **Prüfliste** „Wartet auf deine Entscheidung“: zählt offene Punkte aus allen Modulen und springt direkt hinein. Erfasst werden Lead-Finder-Treffer, Impressen, neue bzw. nicht zugeordnete Signale, auffällige Website-Befunde, Feldbelege, Entscheider-Kandidaten, Befunde der URL-Recherche und überfällige Art.-14-Informationen.
- **Quellenansicht** je Firma: alle Belege aus Lead, Firmendaten, Website-Bewertung (Seiten, Screenshots, Befunde), Kaufsignalen, Entscheidern und URL-Recherche, jeweils mit Auszug, Datum und Prüfstatus.
- **CSV-Export** der Übersicht (Excel-kompatibel, gegen Formel-Injection geschützt).
- Navigations-Badge mit der Zahl offener Prüfpunkte.

**Backend:** `research_center.py` mit den Endpunkten `/api/research-center/overview`, `jobs`, `review`, `export.csv`, `leads/{id}/sources`, `dossier`, `dossier.md`, `dossier.json`, `handoff`. Es gibt keine neuen Tabellen: Das Center liest die bestehenden Strukturen, wie es der Master-Prompt verlangt („keine redundanten Tabellen“).

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **171 Tests grün**, davon 9 neu in `tests/test_phase4_center.py`. Mit Playwright und Chromium laufen alle 171.
- Abgedeckt:
  - „Datenlage unzureichend“ ohne Datenbasis bzw. bei unzureichender Website-Bewertung; Neuverteilung der Gewichte; Gewichtung nachgerechnet
  - Recherchestand bis 100 % und „bereit“; nächster Schritt; Sortierung
  - gesperrte Firmen nicht in der Arbeitsliste
  - Auftragsfortschritt und Prüfliste
  - Quellen aus allen Modulen
  - Dossier mit getrennten Fakten und Hypothesen, ohne interne Kalkulation, nur Pakete aus dem Katalog
  - Übergaberegeln (Bestätigung nötig, Kontaktweg, Sperre)
  - CSV mit Schutz gegen Formel-Injection
  - alle HTTP-Endpunkte inkl. Downloads
- **Klickdurchlauf im Browser** mit fiktiven Daten:
  - Übersicht, Stapelaktionen Karriereseite und Verknüpfen, Dossier, Quellen
  - Übergabe (Lead danach „qualifiziert“), Angebot vorbereiten (Angebotsmodul mit Firma und Paket)
  - Unter-Navigation aus einem Recherche-Bereich, Mobilansicht 390 px
  - Keine Konsolenfehler, kein Überlauf. Die zu breite Firmentabelle ist kompakter umgebaut (Grundlage aufklappbar, Befunde in einer Spalte) und passt jetzt in 1366 px.

## Was ist noch ungetestet?

- Das Zusammenspiel mit **echten** Rechercheergebnissen. Die Teilmodule laufen weiterhin gegen Stubs bzw. lokale Testseiten; ihre Live-Tests stehen noch aus (siehe Berichte zu Phase 1–3).
- Performance bei mehreren hundert Leads. Die Übersicht berechnet den Stand je Lead mit einzelnen Abfragen. Für die lokale Einzelplatz-Nutzung ist das ausreichend; in Phase 6 kommt ein Lasttest.

## Welche technischen oder rechtlichen Grenzen bestehen?

- Die Recherchepriorität ist eine **Arbeitsreihenfolge**, keine Kaufwahrscheinlichkeit und keine Kontakterlaubnis. Das steht in der Oberfläche, im Dossier und im Export.
- Die Übergabe setzt nur die interne Phase und legt eine Aufgabe an. Es wird nichts versendet. Paketvorschläge bleiben bis zur Bedarfsklärung unverbindlich.
- Die Gewichte der Recherchepriorität (40/30/30) sind derzeit feste Werte, sichtbar in der Grundlage. Sie konfigurierbar zu machen ist für Phase 5/6 vorgemerkt.

## Was ist als Nächstes sinnvoll?

1. **Live-Durchlauf** über die ganze Kette mit 10–20 echten Zielfirmen: finden, Impressum, Bewertung, Karriereseiten, Verknüpfen, Dossier.
2. **Phase 5 – Sales-Integration:** Angebots-Matching aus bestätigten Problemen (aus der Bedarfsanalyse statt aus Hypothesen), Paket „Automatisierungsprojekt“, Aufgaben automatisch aus Rechercheergebnissen, Kontaktbeschränkungen je Person.
