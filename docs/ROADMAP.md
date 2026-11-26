# Roadmap

Stand 2.0.0-dev69. **Ab dev66 gilt für die Weiterentwicklung der Open-Intelligence-Plan mit den Phasen R0–R7** (Architektur- und
Masterplan vom 25.11.2026, [`MASTERPLAN_OPEN_INTELLIGENCE.md`](MASTERPLAN_OPEN_INTELLIGENCE.md)); sein Status wird in
[`plan/open_intelligence.json`](plan/open_intelligence.json) gepflegt und unten als Abschnitt erzeugt. Die Maßnahmen M01–M39
stammen aus dem externen Produktreview vom 13.11.2026 (geprüft auf dev11, Etappen A–E) und seinen zwei Ergänzungen
(Bewertungsmodell M27–M34, Leitfaden Kundenonboarding M35–M39); offene M-Maßnahmen sind den R-Paketen zugeordnet (M21 → R1.6/R5.1/R5.2,
M22 → R1.1/R1.5). Rollen der Dokumente: **diese Datei** zusammen mit der Planquelle führt den Status, [`CHANGELOG.md`](../CHANGELOG.md)
beschreibt Änderungen, [`SELF_REVIEW_LOG.md`](SELF_REVIEW_LOG.md) die Nachweise, [`LAUNCH_AUDIT.md`](LAUNCH_AUDIT.md) ist eine
**historische** Bestandsaufnahme von dev1.

Die Suche bleibt grundsätzlich ohne festgelegte Branche. Jede Stufe endet mit einem lauffähigen Stand, Tests unter Python 3.10
und 3.13 und Browser-Tests. **Regel nach jeder Etappe (aus dem Review):** nur erweitern, wenn die vereinbarten Abnahmefälle
bestehen; neue Funktionen dürfen weder die Zahl der Menüpunkte noch die Länge der Firmenakte unkontrolliert wachsen lassen.

## Abgleich mit dem Review

| Empfehlung des Reviews | Entscheidung | Begründung |
|---|---|---|
| Erst Bedienungssicherheit (Etappe A: M01–M05), dann Menüumbau | **übernommen** | dev12 und dev13 bilden Etappe A. Der bisher für dev13 geplante Bereich „Einstellungen“ rückt auf dev14. |
| Eingabeschutz und Öffnungsfokus zusammen mit der Firmenakte | **übernommen** in dev13 | Die Reiter aus dev12 hätten den Eingabeverlust sonst nur anders verpackt. |
| Alte Prioritätsanzeige ablösen, keine erfundenen Vorgaben | **übernommen** in dev13 | Liste und Pipeline zeigen die Passung; neue Firmen ohne vorbelegte Branche und Leistung. |
| Firmenakte als eigene Seite mit direkter Adresse | **teilweise** | dev12 hat Reiter im Dialog. Eine eigene Adresse je Firma folgt mit M07 (dev14); dann wird entschieden, ob die Akte eine Seite wird. |
| Optional lokal gesicherte Entwürfe | **abgewandelt** | Nicht gespeicherte Eingaben bleiben nur im Arbeitsspeicher, nicht im Browser-Speicher – Gesprächsnotizen sollen nicht unbemerkt auf der Festplatte liegen. |
| Sechs Hauptbereiche, Zielstruktur und Zuordnungstabelle | **übernommen** für dev14/dev15 | Die Zuordnung aller 16 heutigen Ziele aus dem Review dient als Abnahme. |
| V7 (Heute als Fokusliste) und V9 (Leerzustände) in die Roadmap | **übernommen** als M08 und M11 | – |
| Mehrere Verkaufschancen je Firma | **übernommen** als Etappe C | Eigenes Datenmodell mit Migration, Sicherung und Wiederherstellungstest – nicht nebenbei im Menüumbau. |
| Keine weitere Theme-Runde, kein zusätzlicher KI-Bereich, SaaS nachrangig | **übernommen** | – |
| Prüffall K01 (Korrekturschleifen widersprechen sich) | **vorgezogen** in dev13 | Kleiner, eindeutiger Fehler im Kundenangebot. |
| Status in einer Quelle (M26) | **übernommen** in dev13 | Diese Tabelle; Launch-Audit als historisch gekennzeichnet. |
| Bewertungsmodell: Leistungen und Befunde über eine gemeinsame Kennung verbinden | **übernommen** in dev16 (M12) | Stabile Leistungskennungen; die Verbindung Befund → Leistung selbst ist M32. |
| Bewertungsmodell: Analyseangebote abgrenzen (M31, „zusammen mit M12/M14“) | **teilweise** in dev16 | Webseiten-Analyse grenzt Nutzerstudie, Barrierefreiheits-/Technikprüfung und Wirkungszusage aus; eine Person, vier Blickwinkel. Eine Nutzerstudie als Leistung erst nach Pilot (M30). |
| Bewertungsmodell: erst Begriffe korrigieren (M27), dann außerhalb der App pilotieren, erst danach M29/M30 einbauen | **übernommen** | M27 (P0) ist in dev17 erledigt; 48 Kriterien werden nicht als Pflichtformular in die Firmenakte gebaut. |
| Leitfaden Onboarding: Umfang je Leistung (Korrekturen, Nutzungsrechte, Quelldateien, Betrieb, Schnittstellen), 40/60 nur Vorgabe | **übernommen** in dev16 (M12) | Korrekturschleifen als Feld je Leistung, Prüfpunkte je Leistungsbereich intern im Angebot, Anzahlung als Einstellung. |
| Leitfaden Onboarding: Versandfassung, Übergang nach Annahme (P0) | **übernommen** als M35, M36 (erledigt in dev17) | Beide vor dem Modellumbau M13, weil sie heute schon falsche Signale geben können (Entwurfshinweis im Export, weiterlaufende Nachfassaufgaben). |
| Leitfaden Onboarding: eigene Kundenansicht | **zurückgestellt** | Erst bei echtem Bedarf; ein verständlicher Export bleibt die Alternative. |

<!-- plan:roadmap:begin (erzeugt von tools/plan_status.py) -->

## Open-Intelligence-Plan R0–R7 (ab 2.0.0-dev66)

Phasenplan aus dem Architektur- und Masterplan vom 25.11.2026. Vollständige Pakete, Abnahmen und Zuordnungen: [MASTERPLAN_OPEN_INTELLIGENCE.md](MASTERPLAN_OPEN_INTELLIGENCE.md); Status wird in [`plan/open_intelligence.json`](plan/open_intelligence.json) gepflegt. Stand aller 56 Pakete: 17 offen · 19 teilweise · 11 erledigt · 9 blockiert.

| Phase | Name | Beginnt nach | Pakete | Startbereit (Abhängigkeiten erledigt, P0 zuerst) | Gate |
|---|---|---|---|---|---|
| **R0** | Baseline & Governance | – | 8 erledigt | – (wartet auf Vorphasen) | Reproduzierbare Baseline (Unit, Browser, Python 3.10/3.13, CI-Matrix) mit Commit dokumentiert |
| **R1** | Quellen, Discovery & Identität | R0 | 1 offen · 2 teilweise · 3 erledigt · 1 blockiert | R1.4 Recherchemodi und Jobbudgets, R1.5 Firmenidentität: Rechtsträger, Marke, Domain | Source Registry sperrt ungeprüfte Quellen |
| **R2** | Extraktion & Kandidaten-Sichtung | R1 | 3 offen · 3 teilweise | R2.3 Evidence-Vertrag v2, R2.6 Skill contact-entity-evidence | Präzision und Recall der Rollen auf der Referenzliste gemessen |
| **R3** | Dokumente & Konzernbeziehungen | R1 | 4 offen · 1 teilweise | R3.1 Isolierter Dokument-Parser, R3.5 Skill document-intelligence | Dokumentgrenzen (Größe, Zeit, Seiten) erzwungen |
| **R4** | Organisationsgraph, Buying Center & Dossier | R2 | 5 offen · 2 teilweise | R4.7 Skill organization-graph | Null unbelegte bestätigte Kanten |
| **R5** | Lokaler Pilot (M21) | R4 | 1 offen · 2 teilweise · 3 blockiert | – (wartet auf Vorphasen) | Referenzmessung an ≥ 100 Firmen gegen die Zielwerte |
| **R6** | Staging & Sicherheit | R0 | 2 offen · 8 teilweise · 2 blockiert | R6.1 Egress Default-Deny und Fetch-Gateway (F05), R6.2 Signierte Restore-Manifeste und Quarantäne (F06), R6.4 Staging hinter TLS-Proxy (F08) | Unabhängige Security-Nachprüfung je Commit/Artefaktdigest bestanden |
| **R7** | Öffentlicher Start | R5, R6 | 1 offen · 1 teilweise · 3 blockiert | – (wartet auf Vorphasen) | Alle Gates erfüllt |

Kritischer Pfad: R0 → R1 → R2 → R4 → R5 → Freigabe. R3 läuft nach R1 parallel, R6-Betriebsmaßnahmen beginnen früh. Kein öffentlicher Start vor bestandener R6-Nachprüfung.

**Wartet auf Entscheidungen oder Nachweise außerhalb des Engineerings:** R1.6 (Eigentümer); R5.1 (Eigentümer); R5.2 (Eigentümer); R5.6 (Steuerberatung); R6.10 (Extern); R6.12 (Eigentümer); R7.2 (Eigentümer); R7.3 (Recht); R7.5 (Eigentümer).

<!-- plan:roadmap:end -->

## Status je Maßnahme

Status: **erledigt** (mit Version und Test), **teilweise**, **offen**. „Erledigt“ heißt technisch umgesetzt und automatisch
geprüft – nicht praxisvalidiert; das leistet erst der Pilot (M21).

| ID | Maßnahme | Prio | Status | Version | Abnahme | Nächstes Hindernis |
|---|---|---|---|---|---|---|
| M01 | Ungespeicherte Eingaben schützen | P0 | erledigt | dev13 | T04 im Browser-Test: Rückfrage Speichern / Weiter bearbeiten / Verwerfen | Eingaben außerhalb des Lead-Dialogs (Angebots-, Rechnungsformulare) noch ohne Schutz |
| M02 | Firmenakte mit Reitern und stehendem Kontext | P0 | erledigt | dev12 | Fünf Reiter, Kopf mit Name und nächster Aktion; längster Reiter 2.322 px statt rund 7.800 px | Eigene Adresse je Firma (M07) |
| M03 | Öffnungsfokus und Rückkehr | P0 | erledigt | dev13 | T03 im Browser-Test: Überblick mit Fokus auf dem Reiter, nach dem Schließen Fokus auf der Zeile | – |
| M04 | Bewertung und neutrale Vorgaben vereinheitlichen | P0 | erledigt | dev13 | T02: neue Firma ohne Branche und Leistung; gleiche Passung mit gleichem Text in Liste, Pipeline, Akte | Recherchepriorität unter „Recherche & Berichte“ ist ein dritter Wert (Recherche-Reihenfolge, keine Kundenbewertung) – Beschriftung mit M09 klären |
| M05 | Statusmarken und verständliche Begriffe | P1 | erledigt | dev12, dev13 | Fünf Stufen mit Symbol; Phasenschlüssel übersetzt | Filter- und Zählerchips angleichen (mit M09) |
| M06 | Einstellungen zusammenführen | P1 | erledigt | dev14 | Eigener Bereich mit Darstellung, Zeiten, Zielkunden, Leistungen & Preise, Recherche, Daten & Zugang; Preise aus Angeboten verlinkt (Browser- und Strukturtest) | Einstellungen je Nutzer im Team-Betrieb |
| M07 | Sechs Hauptbereiche mit direkter Navigation | P1 | erledigt | dev14, dev38, dev40 | Sechs Bereiche, Reiter, Adressen für Ansicht, Firma, Abschnitt und Listenfilter; dev38: geöffnetes Angebot als Adresse (#/angebote?angebot=ID, Neuladen und Zurück); T05 bestanden ; dev40: Firmenakte als eigene Seite (#/firmen/akte/ID mit den Listenfiltern; Entscheidung des Eigentümers: Variante B) | Adressen für Filter weiterer Listen bei Bedarf |
| M08 | Heute auf nächste Aktionen ausrichten (V7) | P1 | erledigt | dev13, dev15 | Drei nächste Schritte mit Grund und Frist; überfällige Zusagen vor Terminen vor Nachfassen vor Akquise; Rückrufzusage vor Passungsnote (Test); Tagesplan und Tagesabschluss eingeklappt | Prioritätsregeln am Pilot prüfen |
| M09 | Filterchips und gespeicherte Arbeitsansichten (V5) | P1 | erledigt | dev15 | Arbeitsansichten mit Trefferzahl, aktive Filter sichtbar, eigene Ansicht speichern und wieder öffnen, Ansicht in der Adresse; Spalten nächster Schritt, Phase, Passung, letzter Kontakt | Stapelaktionen (Review U09) noch offen |
| M10 | Globale Suche und Strg+K (V8) | P2 | erledigt | dev34 | Firma (Name, Firmierung, Website), Chance, Angebot (Nummer, Projekt), Rechnungsnummer über ein Suchfeld; Strg+K/⌘K, Pfeiltasten, Enter, Escape mit Fokus-Rückgabe; Personen nicht durchsucht (Unit- und Browser-Test) | Rechnungstreffer öffnen die Rechnungsliste, nicht die einzelne Rechnung |
| M11 | Geführter Einstieg und Leerzustände (V9) | P1 | erledigt | dev15 | „Erste Schritte“ mit echter Prüfung (Preise, Zielkunden, Zeiten, erste Firma oder Anfrage), ohne Recherchelauf; Leerzustände mit Knopf zum nächsten Schritt | Beispieldaten gibt es bewusst nicht |
| M12 | Zentraler Leistungskatalog | P1 | erledigt | dev16 | Eine Kennung je Leistung; 5/6/26 (+5 Zusatzleistungen) nachvollziehbar zusammengeführt ([`LEISTUNGSKATALOG.md`](LEISTUNGSKATALOG.md)); geänderte Leistung wirkt gleich auf Vorlage, Empfehlung, Angebot und Oberfläche; gespeicherte Angebote unverändert (Unit- und Browser-Test); Korrekturschleifen je Leistung ohne Widerspruch (K01) | Eigene Leistungen anlegen/ausblenden; frühere Paketpreise weichen von den Baukastenpreisen ab – vom Eigentümer zu prüfen |
| M13 | Mehrere Verkaufschancen je Firma | P1 | erledigt | dev18, dev19 | T08: zwei Chancen mit getrennten Phasen, Bedarfsanalysen, Freigaben und Terminen; Verlust einer Chance beendet keine andere, keine Rechnung ändert sich; Angebote prüfen den Bedarf ihrer Chance; Pipeline und Heute je Chance; Bestand mit genau einer ersten Chance (Migration an Kopie geprüft) | Aufgaben je Chance; Paketabgleich je Chance |
| M14 | Briefings für Medien und Software | P1 | erledigt | dev20 | Fragen je Leistungsbereich der Chance (Medien, Software, Analyse, Sichtbarkeit), jede geklärt/offen/entfällt; Angebot übernimmt Grundlage und offene Voraussetzungen, Schnappschuss intern (Unit- und Browser-Test) | Eigene Fragen; Materialliste (M39) |
| M15 | Angebotsrevisionen und Varianten | P1 | erledigt | dev21, dev22 | T11: Revision mit Vorgänger, Grund und Änderungsliste; Vorgänger ersetzt und unverändert; angenommene Fassung bleibt; optionale Positionen ausgewiesen, nicht im Festpreis, nicht in der Rechnung (Unit- und Browser-Test) | Varianten zur Wahl = optionale Positionen oder Revision; kein Variantenvergleich nebeneinander |
| M16 | Nachfassen mit Anlass, Frist und Ergebnis | P1 | erledigt | dev3, dev23 | Versand mit selbst gewählter Frist (Vorgabe 7 Tage ab Versanddatum) und Anlass; Nachfassaufgabe mit Bezug zu Angebot und Chance; Ergebnis Pflicht, bei offener Entscheidung neue Frist; Revision und Entscheidung beenden mit Ergebnis (Unit- und Browser-Test) | Nachfassen ohne Angebot (Erstkontakt, Rückruf) bleibt bei Anruf- und Aufgabenprotokoll |
| M17 | Schlanke Auftragsübergabe und Abnahme | P2 | erledigt | dev24 | T12: Liefergegenstände und Abnahmekriterien aus dem angenommenen Angebot; Übergabe erst ohne offene Liefergegenstände; Abnahme, Abnahme mit Restpunkten oder Nachbesserung mit Aufgaben und Frist; Protokoll für den Kunden ohne interne Zahlen (Unit- und Browser-Test) | Schlussrechnung nur als Hinweis; Zusatzaufträge M18 |
| M18 | Zusatzaufträge und Leistungsänderungen | P2 | erledigt | dev25 | Zusatzauftrag nur zu angenommenem Auftrag (-Z1, gleiche Firma und Chance, Anlass Pflicht); Auftrag bleibt unverändert; Kundendokument nennt Bezug, Anlass und bisherigen Umfang; Auftragsumfang mit Summe beauftragt/offen (Unit- und Browser-Test) | Minderungen und Stornos einzelner Leistungen nach der Zusage nicht abgebildet |
| M19 | Bestandskunden und Betreuungsleistungen | P2 | erledigt | dev26 | Monatliche Positionen als Betreuung mit Beginn und Ende; je Monat genau eine Rechnung mit Leistungszeitraum; offene Monate in „Heute“; Bestandsübersicht trennt Betreuung, Projekte und neue Chancen (Unit- und Browser-Test) | Preisanpassung einer laufenden Betreuung nur über neues Angebot |
| M20 | Zeiten je Leistung und Lernvorschläge | P2 | erledigt | dev5, dev27 | Ist-Zeiten je Angebotsposition; Soll/Ist je Position; Aussage je Leistung erst ab drei abgeschlossenen Aufträgen, mit Spanne und Vorschlag (Unit- und Browser-Test) | Katalogwerte werden nie automatisch geändert; Wirkung nach Methode bleibt M34 |
| M21 | Lokaler Recherchepilot | P0 | teilweise | dev45 | Werkzeug fertig: Zufallsstichprobe (20–100) aus den gefundenen Firmen, Stand beim Ziehen festgehalten, Prüfung von Hand, Quoten mit Anzahl, CSV-Export (Unit- und Browser-Test) | **Eigentümer:** Stichprobe am Stuttgart-Auszug prüfen (Entscheidung: von Hand); Ergebnisse dann in `docs/PRAXISTEST_70191.md` |
| M22 | Quellenstatus und Datenqualität | P1 | teilweise | dev6–dev9, dev44, dev48 | „Keine Website gefunden“ ≠ „hat keine Website“ | Ergebnisse aus M21 |
| M23 | Gemeinsame Hintergrundaufträge vervollständigen | P1 | erledigt | Masterplan 2.0, dev35, dev36, dev39 | Alle Module mit gleichem Lebenszyklus nach Neustart | dev35: Website-Bewertung und Karriereseiten-Scan; dev36: KI-Analyse, Schnellprüfung, öffentliche Ansprechpartner – jeweils im gemeinsamen Auftragssystem, nach Neustart fortgesetzt. dev39: Impressum-Sammelprüfung setzt nach Neustart automatisch fort (von dir pausierte Läufe bleiben pausiert; offline wartet sie sichtbar). Die Einzelquellen-Wiederholung der Sammelsuche nutzt das Auftragssystem; ein Thread nur noch für Suchen aus Versionen davor |
| M24 | Kalender und dokumentierte Exporte | P2 | erledigt | dev41, dev42, dev43 | Stufe 1: Kalender-Abo (iCalendar, geheimer Schlüssel, abschaltbar) und .ics-Export. Stufe 2: CalDAV-Abgleich in beide Richtungen (Termine hin, nur „belegt“ zurück), Konfliktwarnung, freie Vorschläge sparen belegte Zeiten aus, Aktualität sichtbar; Passwort nie in der Datenbank (Unit-Tests gegen nachgebauten CalDAV-Server, Browser-Test). Stufe 3: Entwurf per IMAP in den Entwürfe-Ordner, nie Versand, Sperren beim Ablegen erneut geprüft (Unit-Tests gegen nachgebauten IMAP-Server, Browser-Test) | an einem echten Anbieter noch nicht gemessen; Entscheidung des Eigentümers: Standards statt Anbieter-APIs |
| M25 | Kundenfähiger Kurzbericht | P2 | erledigt | dev30 | Auswahl nur aus bestätigten bzw. freigegebenen Befunden (serverseitig geprüft); Bericht ohne Punktwerte, Prioritäten, Angebotsideen, Hypothesen; gesperrte Firma ohne Bericht; gezeigte Befunde gespeichert (Unit- und Browser-Test) | Nur Markdown, kein gestaltetes PDF |
| M26 | Aktuellen Status in einer Quelle pflegen | P1 | erledigt | dev13 | Diese Tabelle; Launch-Audit als historisch gekennzeichnet | bei jeder Stufe nachführen |

**Ergänzung aus dem Bewertungsmodell (M27–M34).** Die Kriterien (48), Diagnosefragen und Stufen 0–4 sind dort ausdrücklich ein
noch zu validierender Vorschlag, kein geprüftes Messinstrument; entsprechend wird nichts davon als „Qualitätsnote“ eingebaut,
bevor M27 erledigt und ein Pilot außerhalb der App gelaufen ist.

| ID | Maßnahme | Prio | Status | Version | Abnahme | Nächstes Hindernis |
|---|---|---|---|---|---|---|
| M27 | Begriffe und Richtung der Website-Bewertung korrigieren | P0 | erledigt | dev17 | „Auffällig“ (in %, höher = mehr Hinweise) und „Akquise-Priorität“ statt Gesamtnote in Scoring, Akte, Bericht, Recherche; „Profilnähe“ getrennt von der Passung A/B/C; unbekannte Branche/Größe zählt nicht als schlecht (Unit-Test) | Rubriken selbst (M28) |
| M28 | Rubriken fachlich überarbeiten | P1 | erledigt | dev37 | Überschriften (A3), Schriftfamilien (A6), Jahresangabe (A7), Navigation (B7) liefern „Hinweis (prüfen)“ mit Begründung statt „auffällig“; zählen als geprüft, nie als Mangel, belegen kein Angebot; Bewertungsversion 2.1 (Unit- und Browser-Rendering-Test) | Weitere Rubriken nach den ersten Fachreviews (M29/M33) |
| M29 | Fachreview erfassen | P1 | erledigt | dev46 | Kriterienauswahl, Urteil, Beleg, Begründung, Prüfer, Version und „offen“ speicherbar; jede Eingabe sofort gespeichert; Abschluss nur vollständig, danach unveränderlich (Unit- und Browser-Test) | Entscheidung des Eigentümers: direkt in der App |
| M30 | Erlebnisstudien ermöglichen | P2 | erledigt | dev47 | Aufgabenergebnisse, Antworten und Stichprobe getrennt; nur von dir bestätigte Sitzungen zählen; Testpersonen nur mit Kürzel, E-Mail/Telefon abgelehnt; Vorher/Nachher je Firma (Unit- und Browser-Test) | Entscheidung des Eigentümers: direkt in der App statt externer Vorlage |
| M31 | Analyseangebote abgrenzen | P1 | teilweise | dev16 | Expertenprüfung und Nutzerstudie mit unterschiedlichem Umfang, Kosten und Abnahme; Korrekturrunden widerspruchsfrei | Nutzerstudie als Leistung nach M30 |
| M32 | Befund mit Angebot verbinden | P1 | erledigt | dev33 | Jede Position zeigt ihre Grundlage (bestätigter Bedarf, geprüfter Befund, begleitend, ohne); Lücken und ungeprüfte Hypothesen als Hinweis bei der Versandfreigabe; nie im Kundendokument (Unit- und Browser-Test) | Hinweis, keine Sperre – Entscheidung bleibt beim Nutzer |
| M33 | Bewertung kalibrieren | P2 | teilweise | dev46 | Übereinstimmung je Version und Rubrik aus abgeschlossenen Reviews, Richtung der Abweichung, Markierung unter 70 % ab 5 Urteilen; keine automatische Gewichtsänderung (Test) | Vergleich mehrerer unabhängiger Prüfer je Website fehlt noch; braucht erste echte Reviews |
| M34 | Wirkung und Aufwand lernen | P2 | erledigt | dev47 | „Was du lernst“: Aufwand je Projektart, Aufgabenerfolg je Methode, Wirkung vorher/nachher – Aussage erst ab 3 Fällen, Grenzen sichtbar (Test) | aussagekräftig erst mit echten Aufträgen und Studien |

**Ergänzung aus dem Leitfaden Kundenonboarding (M35–M39).** Persönliche Mail- und Dokumentvorlagen des Leitfadens bleiben beim
Eigentümer; in die App kommen nur die Abläufe.

| ID | Maßnahme | Prio | Status | Version | Abnahme | Nächstes Hindernis |
|---|---|---|---|---|---|---|
| M35 | Versandfassung und Dokumentstand | P0 | erledigt | dev17 | Freigabe mit automatischen Prüfungen und vier Prüfpunkten; Export ohne Entwurfshinweis mit Stand-Kennung im Dokument und Dateinamen; Versand und Zusage nur für freigegebenen Stand, mit Zeitpunkt, Weg und Stand (Unit- und Browser-Test) | Gestaltetes PDF bleibt außerhalb; Revisionen M15 |
| M36 | Übergang nach Annahme | P0 | erledigt | dev17 | Startaufgaben je Leistungsbereich vorgeschlagen, nur Bestätigtes angelegt; offene Nachfassaufgaben zum Angebot bewusst beendet (auch nach Absage); zweiter Klick ohne Duplikate (Unit- und Browser-Test) | Projektstatus und Projektkompass (M38) |
| M37 | Eigene Nachrichtenvorlagen mit Platzhaltern | P1 | erledigt | dev29 | Eigene Vorlagen mit festen Platzhaltern; Werte nur aus Firma, Person, Angebot (freigegebener Stand), Termin, Nachfassfrist, Stammdaten; Anrede nur wenn an der Person hinterlegt; [FEHLT: …] sichtbar, Endfassung erst ohne Lücken; Sperre und Personen-Einschränkungen gelten (Unit- und Browser-Test) | Kein Versand; keine Serienbriefe |
| M38 | Projektkompass und Startstatus je Auftrag | P1 | erledigt | dev28 | Aus Angebot und offenen Briefing-Punkten vorbelegt; „Vorbereitung“, „wartet auf …“ (mit Name), „bereit“, „gestartet“ (auch bewusst trotz offener Punkte) je Auftrag; mehrere Projekte einer Firma unabhängig (Unit- und Browser-Test) | – |
| M39 | Material- und Entscheidungsliste | P2 | erledigt | dev28 | Material, Zugang, Entscheidung, Termin je Punkt mit Verantwortlichem, Frist, Auswirkung; überfällige Punkte in „Heute“; kein Passwortfeld, Zugangsdaten-Eingaben abgelehnt (Unit- und Browser-Test) | Keine Dateiablage |

## Etappen

| Etappe | Inhalt | Stand |
|---|---|---|
| A – verlässliche tägliche Bedienung | M01–M05, Beginn M21 | **erledigt** in dev12/dev13; M21 wartet auf den Eigentümer |
| B – klare Navigation und Arbeitslisten | dev14 = M06 Einstellungen + M07 Teil 1; dev15 = M08, M09, M11 | **erledigt**; offen aus M07: Adressen für weitere Listen und Berichte |
| C – mehrere Projekte je Firma | M12 Katalog (dev16), P0-Paket M27/M35/M36 (dev17), M13 Chancen (dev18/dev19) – **erledigt**; M14 Briefings (dev20, **erledigt**); M15 Revisionen und optionale Positionen (dev21/dev22, **erledigt**); M16 Nachfassen (dev23, **erledigt**); Etappe D begonnen | **erledigt**; Migrationen an einer Kopie vorhandener Daten geprüft |
| C′ – Bewertung fundieren | M28, M29 nach Pilot außerhalb der App; M32 nach M13 | M27 erledigt (dev17); Pilot außerhalb der App liegt beim Eigentümer |
| D – Auftrag, Lernen, Anbindung | M17 Übergabe und Abnahme (dev24), M18 Zusatzaufträge (dev25), M19 Bestand und Betreuung (dev26), M20 Zeiten je Leistung (dev27), M38/M39 Projektkompass (dev28), M37 Nachrichtenvorlagen (dev29), M25 Kurzbericht (dev30) – **erledigt**; offen in D: M24 Kalender (Anbieterwahl), M30/M33/M34 nach ersten Reviews; M24/M25, M37–M39 nach Pilotbedarf; M30, M33, M34 nach ersten Reviews; M22/M23 parallel nach Fehlerbild; M10 bei wachsendem Bestand | später |
| E – Visuelle Konsolidierung und Aufgabenführung | Ein Baukasten für alle Ansichten (sieben Bausteine, [UI_BAUKASTEN.md](UI_BAUKASTEN.md)); sechs Schritte, siehe unten | **erledigt** – Schritte 1 bis 6 (dev49 bis dev54); verbleibende Altteile im alten Aufbau siehe [EINSCHRAENKUNGEN.md](EINSCHRAENKUNGEN.md) |

## Etappe E – Visuelle Konsolidierung und Aufgabenführung

Ziel: jede Ansicht folgt demselben Aufbau (Seitenkopf → Werkzeugzeile → Inhalt) und denselben Regeln (eine Hauptaktion,
feste Listenspalten, Vertiefung als Klappzeile, Farbe nur mit Bedeutung). Grundlage und Messwerte: [UI_BAUKASTEN.md](UI_BAUKASTEN.md).
Je Schritt ein lauffähiger Stand; bestehende Adressen, Zurück-Verhalten, Filter und Eingabeschutz bleiben unverändert.

| Schritt | Inhalt | Stand | Nachweis |
|---|---|---|---|
| 1 | Baukasten und mobile Navigation: Bausteinklassen und Maße in style.css, Dokument UI_BAUKASTEN.md; „☰ Menü“ öffnet bei schmaler Breite die Seitenleiste als Schublade | **erledigt** (dev49) | Unit-Test `test_v2_ui_baukasten.py`, Browser-Test `test_mobile_nav_browser.py` (390 px und 1280 px) |
| 2 | Firmen und Heute auf die Bausteine umstellen; Kopfzeile mit den Reitern des Bereichs und der Suche (ohne Datum, Hell/Dunkel und „Neuer Lead“); „Neue Firma“ zusätzlich als Befehl in Strg+K | **erledigt** (dev50) | Browser-Test `test_ui_firmen_heute_browser.py` (Abnahmemaße 1280 × 720, 390 × 844), Abschnitt „Was wohin zog“ in [UI_BAUKASTEN.md](UI_BAUKASTEN.md) |
| 3 | Finden umstellen: vier Reiter (Sichten · Neue Suche · Import · Analysen), kompakte neue Suche mit Voreinstellungen „Wen suchst du?“, Treffer als Liste; Datenquellen nach Einstellungen, Stichprobe nach Firmen → Datenpflege | **erledigt** (dev51) | Browser-Test `test_ui_finden_browser.py` (Abnahmemaße 1280 × 720, 390 × 844, alle Adressen, Voreinstellungen), Abschnitt „Was wohin zog (Schritt 3)“ in [UI_BAUKASTEN.md](UI_BAUKASTEN.md) |
| 4 | Angebote umstellen: drei Reiter (Angebote · Aufträge & Betreuung · Auswertung), Angebotsliste mit nächstem Schritt und Fälligkeit, „＋ Neues Angebot“ als eigener Editor, geöffnetes Angebot als Arbeitsplatz (Reiter Positionen · Kundenvorschau · Interne Kalkulation · Verlauf, Kontextspalte „Prüfung vor Freigabe“ und „Ablauf“, eine Hauptaktion je Phase); Fehlerbehebung: Eingaben gehen beim Neuzeichnen von Erlebnisstudie, Fachreview und Stichprobe nicht mehr verloren | **erledigt** (dev52) | Browser-Tests `test_ui_angebote_browser.py` (Abnahmemaße 1280 × 720, 390 × 844, Adressen, Phasen Entwurf → angenommen) und `test_keep_input_browser.py` (vorher rot, nachher grün), Abschnitt „Was wohin zog (Schritt 4)“ in [UI_BAUKASTEN.md](UI_BAUKASTEN.md) |
| 5 | Einstellungen und Abrechnen umstellen: Einstellungen als Abschnittsliste (240 px) mit Kurzstand und Warnungen, Suche und Eingabeschutz beim Abschnittswechsel, je Abschnitt eine Adresse (alle bisherigen Sprungziele gelten weiter); Abrechnen mit vier Reitern (Rechnungen · Ausgaben · Auswertung · Steuer & Export), Rechnungsliste mit nächstem Schritt, Editor und geöffnete Rechnung als eigene Ansicht, Stammdaten-Warnung mit Sprung nach Einstellungen → Meine Firma | **erledigt** (dev53) | Browser-Test `test_ui_einstellungen_abrechnen_browser.py` (Abnahmemaße 1280 × 720, 390 × 844, alle Abschnitte und Sprungziele, Eingabeschutz, Suche, Reiter), Abschnitt „Was wohin zog (Schritt 5)“ in [UI_BAUKASTEN.md](UI_BAUKASTEN.md) |
| 6 | Firmenakte umstellen: Detailseite mit Seitenkopf („← Firmen“, Firmenname, Phase, Ort · Branche, eine Hauptaktion je Lage) und fünf Reitern in der Werkzeugzeile; Überblick mit „Vereinbart“ (getrennt von der Empfehlung des Programms), Chancenliste, Klappzeilen (Empfehlung, Bedarf, Passung, Website-Bewertung, Quellen & Belege, Kaufsignale, Aufgaben) und Kontextspalte (Ansprechpartner, letzter Kontakt, Kontaktstatus mit Sperre, Website, Telefon, Phasen); Kontakt & Verlauf mit benannten Aktionen und Verlauf als Liste; „Neue Firma“ statt „Neuer Lead“; sichtbar „Firma“ statt „Lead“ in der ganzen Oberfläche und in den Meldungen des Servers | **erledigt** (dev54) | Browser-Test `test_ui_akte_browser.py` (Abnahmemaße 1280 × 720, 390 × 844, Sperre, eine Hauptaktion, Zurück mit Filter, Neue Firma, kein sichtbares „Lead“ in sechs Bereichen), Abschnitt „Was wohin zog (Schritt 6)“ in [UI_BAUKASTEN.md](UI_BAUKASTEN.md) |

## Zuordnung der bisherigen Menüziele (M07, Stand dev14)

| Bisheriges Ziel | Neuer Ort | Adresse |
|---|---|---|
| Heute | Heute → Übersicht | `#/heute` |
| Aufgaben | Heute → Aufgaben | `#/heute/aufgaben` |
| Kontakt & Termine | Heute → Kontakt & Termine (Einzelfälle zusätzlich in der Firmenakte) | `#/heute/kontakt-termine` |
| Firmen finden | Finden → Sichten (Treffer) und Finden → Neue Suche (Formular); seit dev51 | `#/finden` (öffnet Sichten, wenn offene Treffer warten), `#/finden/sichten`, `#/finden/neue-suche` |
| Import & Prüfung | Finden → Import (auch Firmenliste/GLEIF-Export) | `#/finden/import` |
| Firmen-Berichte | Finden → Analysen → Recherche & Berichte; je Firma im Reiter „Recherche“ der Akte | `#/finden/recherche` |
| URL-Recherche, Website-Scoring, Kaufsignale | Finden → Analysen (Reiterzeile) | `#/finden/url-recherche` usw. |
| Leads | Firmen → Firmenliste | `#/firmen` (Filter: `?suche=…&phase=…`, Firma: `?firma=…`) |
| Pipeline | Firmen → Pipeline | `#/firmen/pipeline` |
| Datenqualität & System | aufgeteilt: Firmen → Datenpflege (`#/firmen/datenpflege`); wiederkehrende Recherche unter Finden → Analysen → Recherche & Berichte; Datenquellen (OpenStreetMap, GLEIF-Katalog, Quellen prüfen) unter Einstellungen → Datenquellen; Stichprobe unter Firmen → Datenpflege; alles Übrige unter Einstellungen | – |
| Angebote & Preise | Angebote → Angebote (Liste, „＋ Neues Angebot“, geöffnetes Angebot); Bestandskunden, Kick-off, Übergabe und Nachkalkulation unter Angebote → Aufträge & Betreuung; Erlebnisstudien und „Was du lernst“ unter Angebote → Auswertung (seit dev52); Kalkulationsgrundlagen und Katalog unter Einstellungen → Leistungen & Preise | `#/angebote`, `#/angebote?neu=1`, `#/angebote?angebot=ID`, `#/angebote/auftraege`, `#/angebote/auswertung`, `#/einstellungen?abschnitt=preise` |
| Rechnungen & Buchhaltung | Abrechnen → Rechnungen · Ausgaben · Auswertung · Steuer & Export (seit dev53); Stammdaten unter Einstellungen → Meine Firma, Backup unter Einstellungen → Sicherung & Zugang | `#/abrechnen`, `#/abrechnen/ausgaben`, `#/abrechnen/auswertung`, `#/abrechnen/steuer` |
| KI-Studio | Einstellungen → KI-Werkzeuge (seit dev53; vorher Reiter „Erweiterte Werkzeuge“) | `#/einstellungen/ki-studio`, `#/einstellungen?abschnitt=ki-werkzeuge` |
| Sales-Playbook | „Hilfe & Gesprächsleitfaden“ unten in der Seitenleiste | `#/einstellungen/hilfe` |

## Abnahmefälle aus dem Review

| Nr. | Aufgabe | Stand |
|---|---|---|
| T01 | Nach dem Start die wichtigste Aufgabe finden | **bestanden** (dev15, Browser-Test: überfällige Zusage oben, ein Klick öffnet die Firma) |
| T02 | Neue Firma nur mit Namen erfassen | **bestanden** (dev13, Browser-Test) |
| T03 | Bestehende Firma öffnen | **bestanden** (dev13, Browser-Test) |
| T04 | Notiz eingeben und Escape drücken | **bestanden** (dev13, Browser-Test) |
| T05 | Aus gefilterter Liste in die Firma und zurück | **bestanden** (dev14, Browser-Test: Filter und Firma in der Adresse, Zurück schließt die Firma) |
| T06 | Rückruf nach erfolglosem Versuch planen | **bestanden** (dev31, Browser-Szenario: neuer Versuch zu anderer Tageszeit mit Frist, nach drei Versuchen Kanalwechsel oder Parken) |
| T08 | Zwei Chancen einer Firma mit getrennten Phasen, Bedarf, Terminen | **bestanden** (dev18: Phase, Anliegen, Termine; dev19: Bedarfsanalyse und Freigabe je Chance – Unit- und Browser-Tests) |
| T12 | Übergabe und Abnahme eines Auftrags | **bestanden** (dev24: Liefergegenstände, Übergabe, Abnahme mit Restpunkt, Protokoll – Unit- und Browser-Test) |
| T07 | Projektanfrage aufnehmen | **bestanden** (dev32: Eingang mit Frist → Firma, Chance, bestätigter Bedarf, Angebot der Chance; fristgerecht erledigt) |
| T09 | Medienangebot | **bestanden** (dev32: Prüfpunkte Mediengestaltung, Korrekturschleifen, Nutzungsrechte, Druckkosten außerhalb; Kompass mit Material und Freigabeperson) |
| T10 | Softwareangebot | **bestanden** (dev32: Prüfpunkte Betrieb, Zugänge, Testdaten, Übergabe; Betrieb als laufende Leistung; Testzugang ohne Passwörter) |
| T11 | Revision eines Angebots | **bestanden** (dev21: Vorgänger, Grund, Änderungsliste; Unit- und Browser-Test) |
| T13 | Zeitüberschreitung | **bestanden** (dev32: Ist über Kalkulation → Hinweis „Umfang prüfen“, Rest 0; Mehrarbeit als Zusatzauftrag, Auftrag unverändert) |
| T14 | Recherche während eines Fehlers wieder aufnehmen | **bestanden** (dev35/dev36: Firmen-Bericht, Sammelsuche, Website-Bewertung, Karriereseiten-Scan, KI-Analyse, Schnellprüfung, Ansprechpartner setzen nach Neustart fort; Abruffehler gezielt wiederholbar; Impressum-Sammelprüfung pausiert und wird von Hand fortgesetzt) |
| T15 | Sicherung in getrennte Testinstallation zurückspielen | **bestanden** (dev31, Szenario mit allen Daten aus Etappe C und D: vollständig wiederhergestellt, Abläufe laufen weiter, Ausgangsinstallation unverändert; ältere Sicherung wird migriert) |

## Danach – Buchhaltung

Bankumsatz-Import mit Abgleich, Belegupload mit Prüfsumme, GiroCode, Vorlage Verfahrensdokumentation, DATEV-Export nach Testimport mit der Steuerberatung.

## Später – SaaS

Seit dev66 als Phasen R6 (Staging & Sicherheit) und R7 (öffentlicher Start) im Open-Intelligence-Plan geführt; die Liste unten ist der ältere Stand. Erst nach einem bestandenen lokalen Piloten und nachgewiesener Zahlungsbereitschaft (Entscheidung E1 in [`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md)). Nötig sind dann: Trennung nach Organisation, PostgreSQL, getrennte Recherche-Worker mit Budgets, Anmeldung über OIDC, Überwachung, externe Sicherungen, Datenschutzprüfung, Abrechnung über einen etablierten Anbieter, Darstellung je Nutzer statt je Installation. Ein Plan dafür (`SAAS_LAUNCH_PLAN.md`) ist noch nicht geschrieben.

**Kein öffentlicher Start**, bevor Mandantentrennung, Rechteprüfung, Anmeldung, Sicherung und Wiederherstellung sowie die Datenschutzprüfung nachweislich bestanden sind.

## Absichtlich kein Feature

- Massenhafte Kalt-E-Mails, LinkedIn-Bots, gekaufte Kontaktlisten, WhatsApp-Spam
- Auslesen von Google Maps, LinkedIn oder Suchmaschinen; Umgehen von Sperren, Captchas oder robots.txt
- KI-Bewertung, die ihr Ergebnis ohne Quellenbeleg als Tatsache ausgibt
- Direkte ELSTER-Übermittlung, automatischer Versand von Rechnungen oder Mahnungen
