# Selbstprüfung je Arbeitspaket

Jede Note (1 = schwach, 5 = stark) nennt den Messwert oder Test, auf den sie sich stützt. Noten ohne Beleg gibt es nicht.
Stufen: implementiert → lokal getestet → live verifiziert → pilotfähig → öffentlich launchfähig.

## Sprint 0 – Wahrheitscheck (11.11.2026)

- **Ergebnis:** `docs/LAUNCH_AUDIT.md`, `docs/ARCHITECTURE_DECISIONS.md`.
- **Wichtigster Befund:** Der neueste Stand lag nicht auf `main`, sondern auf `codex/signaldesk-2.0-dev` (2.0.0-dev1, mit Übergabe). Die Arbeit baut darauf auf.
- **Abweichung von älteren Angaben:** 426 statt 425 Tests auf dev1; 4 statt 2 Überspringungen.
- **Entscheid:** weiter. Größter überprüfbarer Nutzen: Kundenbewertung und Erreichbarkeit (Matrix: zwei Einträge „Defekt“).

## Arbeitspaket 1 – Kundenbewertung und Erreichbarkeit (2.0.0-dev2)

Entspricht aus dem Auftrag: Abschnitt 6 (Zielkundenprofil, Passung vor / Qualifizierung nach dem Gespräch, Gesprächsergebnisse, Zeitfenster, Verlustgründe), Sprint 3 (K.-o.- und Warnkriterien) und Abschnitt 7 (zwei Projekt-Skills).

### Tatsächlich ausgeführt

| Prüfung | Ergebnis |
|---|---|
| Regression `python -m unittest discover -s tests` (Python 3.13, Linux) | 454 Tests bestanden, 4 übersprungen (optionale Pakete) |
| davon neu: `tests/test_v2_qualification.py` | 28 Tests |
| Browser-Tests `tests/e2e` (Chromium, festgeschriebene Pakete) | 3 von 3 bestanden, davon 1 neu (Profil → Note in der Liste → Firmenakte → „nicht erreicht“ → „verloren“ mit Grund) |
| Migration einer Altdatenbank (Stand v1.6) | bestanden; alle Altdaten lassen sich bewerten |
| Release-Paket | 159 Dateien, 1,0 MB, zweimal gebaut und byte-gleich |
| Übersicht für 500 Firmen und 300 Sperreinträge | 0,04 s (vor der Nachbesserung 1,38 s) |
| Windows, macOS, echte Firmen | **nicht geprüft** |

### Bewertung

| Kriterium | Note | Beleg |
|---|---|---|
| Nutzen | 4 | Zwei als „Defekt“ geführte Punkte des Audits sind behoben (Bewertung am Zielmarkt vorbei; „nicht erreicht“ folgenlos). Ob die Noten im Alltag stimmen, ist ungeprüft. |
| Bedienbarkeit | 3 | Browser-Test durchläuft den Weg ohne Anleitung. Die Branchenwahl ist eine Liste mit 60 Auswahlfeldern; die Note steuert noch nicht die Reihenfolge in „Heute“ und Pipeline. |
| Quellenqualität | 4 | Jedes Kriterium nennt seine Grundlage („aus Firmenname geschätzt“, „laut Firmensuche“). Kontaktwege zeigen nur belegte Werte. |
| Robustheit | 4 | Kaputtes gespeichertes Profil fällt auf die Vorgaben zurück; fehlendes Ortsverzeichnis ergibt „unbekannt“ statt Fehler (Tests). |
| Sicherheit | 4 | Auswertung ändert keine Daten (Test); Sperre wirkt als K.-o. und entfernt den Vorschlag für den nächsten Versuch (Test); keine neue Abhängigkeit, kein neuer Netzabruf. |
| Kostenkontrolle | 5 | Keine Netzabfragen, keine KI, keine Fremdpakete. |
| Erweiterbarkeit | 3 | Modul ohne globalen Zustand außer einem Orts-Zwischenspeicher; Gewichte stehen noch fest im Code. |
| Testabdeckung | 4 | 28 Unit-/API-Tests, 1 Browser-Test, 1 Migrationstest. Kein Test auf Windows. |

### Nachbesserungsschleife 1

Auslöser: der neue Browser-Test und die Bildschirmfotos.

1. **Skript wurde nicht ausgeliefert.** `/assessment.js` fehlte in der Liste der statischen Dateien; der Server antwortete mit 404. Alle Unit-Tests waren grün – nur der Browser-Test fiel auf. Behoben; als Regel in den Skill `qa-release-gate` aufgenommen.
2. **Übersicht zu langsam:** 1,38 s für 500 Firmen bei jedem Neuladen. Ursache: Ortssuche je Firma und doppelte Sperrprüfung. Behoben (0,04 s).
3. **Darstellung:** Überschriften der Statistik klebten am Text, das Ankreuzfeld stand über seiner Beschriftung. Behoben.

### Nachbesserungsschleife 2

Auslöser: der vollständige Testlauf nach Schleife 1.

1. **Zwischenspeicher merkte sich Fehlschläge.** War das Ortsverzeichnis einmal nicht verfügbar, blieb die Entfernung dauerhaft „unbekannt“. Im Einzeltest unsichtbar, im Gesamtlauf rot. Jetzt werden nur Treffer gemerkt.
2. **Release-Paket enthielt alte Pakete.** Der Ordner `ausgabe/` (zwei ZIP-Dateien) wanderte in jedes neue Paket: 3,3 MB statt 1,0 MB. `ausgabe/` und `.claude/` sind jetzt ausgeschlossen. Dieser Fehler bestand schon in dev1.
3. **Veralteter Bytecode** täuschte nach dem Versionswechsel die alte Versionsnummer vor (Testumgebung, kein Programmfehler). In den Skill aufgenommen: nach Versionswechsel `__pycache__` leeren.

Schleife beendet, weil alle Prüfungen bestehen und die verbleibenden Schwächen neue Arbeitspakete sind, keine Korrekturen.

### Die drei wichtigsten verbleibenden Schwachstellen

1. **Die Bewertung ist nicht an echten Ergebnissen geprüft.** Gewichte und Schwellen sind gesetzt. Belegbar wird sie erst mit dem Praxistest (50–100 Firmen) und ausreichend gewonnenen und verlorenen Chancen.
2. **Die Note steuert den Arbeitstag noch nicht.** „Heute“, Pipeline und Firmen-Berichte sortieren weiter nach dem alten Lead-Fit. Es stehen jetzt fünf Kennzahlen nebeneinander statt vier; der alte Lead-Fit sollte in der Anzeige ersetzt werden.
3. **Erreichbarkeit ist nur zur Hälfte gelöst.** Geschäftszeiten der Firmen und die eigene Erreichbarkeit (verpasste Anrufe, Rückrufzeiten, Auslastung) fehlen.

### Stufe

| Stufe | Stand |
|---|---|
| Implementiert | ja |
| Lokal getestet (Linux, Chromium) | ja |
| Live verifiziert (echte Firmen, Windows) | nein |
| Pilotfähig | nein – erst nach Praxistest und Windows-Prüfung |
| Öffentlich launchfähig | nein |

**Entscheid:** weiter mit Arbeitspaket 2 (Note in „Heute“ und Pipeline, eigene Erreichbarkeit), sobald freigegeben.

## Arbeitspaket 2 – Eigene Erreichbarkeit und Auslastung (2.0.0-dev3)

Entspricht aus dem Auftrag: Abschnitt 3 („Heute“ mit priorisierten nächsten Aktionen), Abschnitt 6 (Rückrufzusagen, Zeitfenster, verfügbare Kapazität). Behebt die Schwachstellen 2 und 3 aus Arbeitspaket 1 zum Teil.

### Tatsächlich ausgeführt

| Prüfung | Ergebnis |
|---|---|
| Regression (Python 3.13, Linux) | 469 Tests bestanden, 4 übersprungen (optionale Pakete) |
| davon neu: `tests/test_v2_reach.py` | 15 Tests |
| Browser-Tests `tests/e2e` | 4 von 4 bestanden, davon 1 neu (Eingang festhalten und erledigen, Kontaktliste, Auslastung, Note in der Pipeline, eigene Zeiten) |
| Release-Paket | zweimal gebaut, byte-gleich |
| Prüfliste `privacy-and-contact-guardrails` | Punkte 2–5 und 7 eingehalten (Tests: gesperrte Firma nie auf der Kontaktliste, Liste legt nichts an, kein Versand). Punkt 1 bewusst abweichend: ein Eingang lässt sich auch bei gesperrter Firma festhalten, mit Warnhinweis. Punkt 6 verletzt, siehe Schwachstelle 1. |
| Windows, macOS, echte Firmen | **nicht geprüft** |

### Bewertung

| Kriterium | Note | Beleg |
|---|---|---|
| Nutzen | 4 | Ein verpasster Anruf ist in einem Schritt mit Frist festgehalten (Browser-Test). Ob die Fristen im Alltag passen, zeigt erst die Nutzung. |
| Bedienbarkeit | 4 | Eingang und Kontaktliste stehen ganz oben auf „Heute“; ein Feld genügt. Bildschirmfotos geprüft. |
| Quellenqualität | 3 | Die Auslastung nennt ihre Grundlage, bleibt aber eine Schätzung aus kalkulierten Stunden. |
| Robustheit | 4 | Kaputte Einstellungen fallen auf Vorgaben zurück; Fristen überspringen Wochenenden und Abwesenheiten (Tests). Feiertage fehlen. |
| Sicherheit | 4 | Kein Versand, keine Netzabfrage. Gesperrte Firmen erscheinen nie als Kontaktvorschlag (Test). |
| Kostenkontrolle | 5 | Keine Netzabfragen, keine KI, keine Fremdpakete. |
| Erweiterbarkeit | 3 | Modul ohne globalen Zustand; Kalender- und Telefonanbindung hätten klare Anschlussstellen, existieren aber nicht. |
| Testabdeckung | 4 | 15 Unit-/API-Tests, 1 Browser-Test. Kein Test auf Windows. |

### Nachbesserungsschleife 1

Auslöser: Bildschirmfoto von „Heute“.

1. Das Eingabeformular war ungestaltet und klebte am Rand. Behoben.
2. Der Eingang stand unter dem sechszeiligen Tagesplan – für „in zehn Sekunden festhalten“ zu weit unten. Jetzt ganz oben.
3. Listenzeilen nutzten ein dreispaltiges Raster mit zwei Elementen. Behoben.

### Nachbesserungsschleife 2

Auslöser: zweites Bildschirmfoto.

1. **Widerspruch im Tagesplan:** „Wiedervorlagen erledigen“ galt als erledigt, obwohl ein Rückruf offen war. Fällige Rückrufe aus dem Eingang stehen jetzt in der Wiedervorlage (Test).
2. Die Auslastung meldete „Zugesagt sind rund 0 Wochen“, obwohl 40 Stunden angeboten waren. Text korrigiert.
3. Das Etikett „Auslastung“ zog sich über die ganze Breite. Behoben.

Schleife beendet: alle Prüfungen bestehen, die verbleibenden Punkte sind neue Arbeit.

### Die drei wichtigsten verbleibenden Schwachstellen

1. **Einträge im Eingang haben keine Löschfrist.** Sie können Namen und Telefonnummern enthalten und müssen bisher von Hand gelöscht werden. Sollte als Nächstes an die Löschfristen in `quality.py` angeschlossen werden.
2. **Die Auslastung ist grob.** Ohne erfasste Ist-Zeiten zählt jedes angenommene Angebot 8 Wochen lang voll. Verlässlich wird sie erst mit der Nachkalkulation.
3. **Weiterhin ungemessen an echten Firmen und ungetestet unter Windows.** Das gilt für beide Arbeitspakete; der Praxistest braucht eine Freigabe.

Offen aus Arbeitspaket 1 bleibt: „Heute → Offenes Potenzial“ und die Firmen-Berichte sortieren noch nach dem alten Lead-Fit; Geschäftszeiten der Firmen fehlen.

### Stufe

Implementiert und lokal getestet (Linux, Chromium). Nicht live verifiziert, nicht pilotfähig, nicht öffentlich launchfähig.

**Entscheid:** weiter. Vorschlag für Arbeitspaket 3: Praxistest an echten Firmen (nach Freigabe) oder, ohne Freigabe, Löschfrist für den Eingang und README-Neufassung.

## Arbeitspaket 3 – Plattformfestigkeit und Aufräumen (2.0.0-dev4)

Auslöser: Die CI des Pull Requests #19 war rot. Die Prüfung zeigte, dass sie schon bei v1.19 auf `main` rot war – die Fehler waren älter als die Arbeitspakete 1 und 2, wurden aber bisher nicht bemerkt. Im Audit stand dazu nur „Ergebnis des letzten Laufs konnte nicht abgerufen werden“; das war eine Lücke im Wahrheitscheck.

### Befunde und Behebung

| Befund | Wirkung | Behebung | Schutz |
|---|---|---|---|
| Backslash im Ausdruck eines f-Strings (`imprint.py`, seit 04.11.) | **SignalDesk startet unter Python 3.10 und 3.11 nicht**, obwohl 3.10+ zugesagt ist | Ausdruck in eine Variable gelegt | Test durchsucht alle Dateien nach diesem Muster |
| Sonderzeichen (②, ←, ✓) in der Konsolenausgabe | Abbruch von Einrichtung und Installationsprüfung in Windows-Konsolen ohne UTF-8 | Ausgabe ersetzt nicht darstellbare Zeichen | Test mit cp1252-Konsole |
| `with sqlite3.connect(...)` schließt die Verbindung nicht | Datenbankdatei bleibt nach dem Start gesperrt, bis Python aufräumt; unter Windows scheitern Löschen und Ersetzen | Verbindung wird ausdrücklich geschlossen (1 Stelle im Programm, 8 in Tests und Werkzeugen) | Test: keine offene Verbindung nach der Datenbank-Vorbereitung |
| Test baute unter Python < 3.12 einen Windows-Pfad auf Linux | 1 Testfehler unter 3.10 | Pfad vor dem Umschalten angelegt | – |

### Tatsächlich ausgeführt

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13, 3.12 und 3.10 (Linux) | je 473 Tests bestanden; 4 bzw. 6 übersprungen (optionale Pakete) |
| Warnungen „unclosed database“ im Gesamtlauf | 0 (vorher 27) |
| Die drei neuen Schutz-Tests ohne die Behebungen | schlagen fehl – sie prüfen also wirklich |
| Browser-Tests | 4 von 4 |
| Python 3.11 in dieser Umgebung | 4 Fehler durch ein defektes System-Paket `cryptography` der Testmaschine, nicht durch SignalDesk; ohne dieses Paket nicht nachgeprüft |
| Windows | **hier nicht ausführbar.** Die Ursachen wurden aus den CI-Protokollen abgelesen und unter Linux nachgestellt. Ob die Windows-CI jetzt grün ist, zeigt erst der Lauf nach dem Push. |

### Außerdem erledigt

- Eingang: erledigte Einträge werden nach 90 Tagen (einstellbar) anonymisiert – Schwachstelle 1 aus Arbeitspaket 2.
- Note in den Firmen-Berichten.
- README neu (82 statt 432 Zeilen), Roadmap neu.
- Ordner `ausgabe/` entfernt. Die Dateien bleiben im Git-Verlauf abrufbar; sie ganz zu tilgen hieße den Verlauf umzuschreiben und wurde nicht gemacht.

### Bewertung

| Kriterium | Note | Beleg |
|---|---|---|
| Nutzen | 5 | Ohne die erste Behebung startet das Programm auf zwei von vier zugesagten Python-Versionen nicht. |
| Robustheit | 4 | Drei Fehlerklassen mit Schutz-Test abgedeckt; Windows selbst nur über die CI prüfbar. |
| Testabdeckung | 4 | Jetzt lokal auf drei Python-Versionen ausgeführt statt auf einer. |
| Bedienbarkeit | 4 | README führt in 82 Zeilen zum Start und zu den Dokumenten. |

### Die drei wichtigsten verbleibenden Schwachstellen

1. **Windows bleibt unbewiesen, bis die CI grün ist.** Weitere Windows-Fehler können hinter den jetzt behobenen liegen (der Lauf zeigte 19 Fehler; nicht alle Protokollzeilen waren abrufbar).
2. **Der Wahrheitscheck in Sprint 0 war unvollständig:** Der CI-Zustand wurde nicht geklärt. Künftig gehört „CI-Ergebnis gelesen“ zum Prüfverfahren (im Skill ergänzt).
3. **Weiterhin keine Messung an echten Firmen.**

### Nachtrag: CI-Ergebnis für Commit `352d7c8` gelesen

8 von 10 Jobs grün (vorher 4): beide Windows-Installationen, Python 3.10 und 3.13 unter Linux, Browser-Test, Release. Die Unit-Tests unter Windows fielen von 19 auf 2 Fehler. Beide sind in einer zweiten Nachbesserung behoben:

| Befund | Wirkung | Behebung | Schutz |
|---|---|---|---|
| Zwei Wiederherstellungen in derselben Sekunde erzeugten denselben Namen für die Sicherheitskopie | Unter Windows Abbruch; **unter Linux wurde die erste Sicherheitskopie stillschweigend überschrieben** | eindeutiger Name, nie überschreiben | Test: beide Sicherheitskopien bleiben erhalten |
| Recherche-Worker fragen die Datenbank noch Sekunden nach dem letzten Auftrag ab | Unter Windows blieb die Datei beim Aufräumen eines Tests gesperrt | `jobs.stop_workers()` beendet die Worker sauber; laufende Schritte werden zu Ende geführt, offene bleiben eingereiht | Test: Beenden und Neustart der Worker |

Danach lokal: 475 Tests unter Python 3.13 und 3.10 bestanden. Ob Windows damit vollständig grün ist, zeigt der nächste CI-Lauf.

**Entscheid:** nachbessern abgeschlossen; CI des neuen Commits lesen.

### Nachtrag: CI-Ergebnis für Commit `cc584f2` gelesen

9 von 10 Jobs grün. **Die Unit-Tests unter Windows mit Python 3.13 sind erstmals vollständig grün.** Unter Windows mit Python 3.10 blieb 1 Fehler: derselbe Sammelsuche-Test konnte seine Datenbankdatei beim Aufräumen nicht löschen (unter 3.13 im selben Lauf bestanden – ein Zeitproblem, kein fester Fehler). Der Test versucht das Aufräumen jetzt bis zu zehn Sekunden lang erneut; die Worker enden beim Beenden sofort statt nach bis zu fünf Sekunden. Die Prüfungen des Tests selbst sind unverändert. Ob das reicht, zeigt der nächste Lauf; die eigentliche Ursache (welcher Hintergrund-Thread die Datei kurz hält) ist nicht nachgewiesen.

### Nachtrag: CI-Ergebnis für Commit `5db25ba` – Ursache belegt

Wieder 1 Fehler unter Windows, diesmal in einem **anderen** Test (`test_sprintS3_jobs`, startet echte Recherche-Worker). Damit ist die Ursache belegt statt vermutet: Die Worker fragen die Datenbank weiter ab, während der Test sie löscht. Welcher Test es trifft, hängt vom Zeitpunkt ab. Behebung an einer Stelle statt Test für Test: `tests/tmpclean.py` beendet vor dem Löschen alle Worker (`jobs.stop_all_workers`) und wird von allen 27 Testdateien mit temporärer Datenbank verwendet. Laufzeit unverändert (137 s). Prüfungen der Tests unverändert.

**Eigener Fehler in dieser Runde:** Commit `02a3a0d` wurde gepusht, bevor das Testergebnis gelesen war. Er wartete auch auf Sammelsuchen früherer Tests und brach 20 Tests. Im Folge-Commit behoben; der erste Versuch der Korrektur verdreifachte außerdem die Laufzeit (400 statt 140 Sekunden) und wurde zurückgenommen. Regel im Prüfverfahren ergänzt: Commit und Push nie im selben Befehl wie den Testlauf ausführen.

## Arbeitspaket 4 – Nachkalkulation (2.0.0-dev5)

Entspricht aus dem Auftrag: Abschnitt 6 („verfügbare Kapazität, Nachkalkulation bei abgeschlossenen Projekten“). Behebt Schwachstelle 2 aus Arbeitspaket 2 (grobe Auslastung).

### Tatsächlich ausgeführt

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 (Linux) | je 485 Tests bestanden; 4 bzw. 6 übersprungen (optionale Pakete) |
| davon neu: `tests/test_v2_postcalc.py` | 10 Tests |
| Browser-Tests | 5 von 5, davon 1 neu (Zeit erfassen → Rest sichtbar → abschließen → Urteil → Auslastung auf „Heute“ folgt) |
| Release-Paket | zweimal gebaut, byte-gleich |
| Windows, echte Firmen | nicht geprüft; Windows nur über die CI |

### Bewertung

| Kriterium | Note | Beleg |
|---|---|---|
| Nutzen | 4 | Beantwortet erstmals „Hat sich der Festpreis gelohnt?“ (Test: 74,00 € je Stunde gegen 66 € Mindestverdienst). Wert hängt davon ab, dass Zeiten wirklich eingetragen werden. |
| Bedienbarkeit | 4 | Ein Feld und ein Knopf je Auftrag; Sammeleinträge erlaubt. Bildschirmfoto geprüft. |
| Quellenqualität | 4 | Soll kommt aus der gespeicherten Kalkulation des Angebots, Ist aus den Einträgen; der Lernwert erscheint erst ab drei Aufträgen. |
| Robustheit | 4 | Abgeschlossene Aufträge sind geschützt; Angebote ohne kalkulierte Stunden führen nicht zu Fehlern (Tests). |
| Sicherheit | 5 | Keine Netzabfrage; Angebote und Rechnungen bleiben unverändert (Test); nichts davon erscheint im Kundendokument. |
| Kostenkontrolle | 5 | Keine Fremdpakete, keine KI. |
| Erweiterbarkeit | 3 | Zeiten hängen am Auftrag, nicht an der einzelnen Leistung. |
| Testabdeckung | 4 | 10 Unit-/API-Tests, 1 Browser-Test. |

### Nachbesserungsschleife 1

Auslöser: der neue Browser-Test.

1. **Das Stundenfeld lehnte „12,5“ ab.** Der Browser erlaubte wegen der eingestellten Schrittweite nur Werte wie 0,1 / 0,35 / 0,6. Das Formular ließ sich nicht absenden – ohne Fehlermeldung. Alle Unit-Tests waren grün. Behoben.
2. Meldungen nutzten den Dezimalpunkt („7.5 von 20“). Jetzt deutsche Schreibweise.
3. Die Grenze von 24 Stunden je Eintrag verhinderte Sammeleinträge („diese Woche 30 Stunden“). Auf 200 angehoben.

### Nachbesserungsschleife 2

1. „1 Einträge“ → „1 Eintrag“.
2. Der bestehende Auslastungs-Test prüfte einen Hinweistext, der sich mit der neuen Rechnung geändert hat; die Prüfung wurde auf die neue Aussage umgestellt und um die Zahl der Aufträge ohne Zeiten ergänzt.

Schleife beendet: alle Prüfungen bestehen.

### Die drei wichtigsten verbleibenden Schwachstellen

1. **Zeiten je Auftrag, nicht je Leistung.** Welche Katalogleistung regelmäßig länger dauert, lässt sich noch nicht ablesen – genau das würde die Preise verbessern.
2. **Aufträge ohne erfasste Zeiten** fallen nach acht Wochen weiterhin still aus der Auslastung.
3. **Weiterhin keine Messung an echten Firmen**; Windows nur über die CI belegt.

### Stufe

Implementiert und lokal getestet (Linux, Python 3.10 und 3.13, Chromium). Nicht live verifiziert, nicht pilotfähig, nicht öffentlich launchfähig.

**Entscheid:** weiter.

## Arbeitspaket 5 – Praxistest 70191 (2.0.0-dev6)

Erste Messung gegen die echten Quellen, mit Freigabe des Eigentümers. Vollständiger Bericht: `PRAXISTEST_70191.md`.

- **Stufe „live verifiziert“ erstmals für einen Teil erreicht:** die Firmensuche gegen GLEIF (und teilweise OpenStreetMap). Website-Zuordnung, Impressum und Firmen-Bericht bleiben ungemessen.
- **Zwei Programmfehler gefunden, die kein Test mit Attrappen zeigen konnte:** PLZ wurde ignoriert (2 von 300 Treffern in der gewünschten PLZ); die erste Quelle verbrauchte das ganze Budget. Beide behoben, mit 6 neuen Tests; Wiederholung live: 56 von 56 Treffern in 70191, alle drei Quellen gelaufen.
- **Wichtigste Erkenntnis:** Für die Zielgruppe Handwerk liefert die Suche heute praktisch nichts (1 von 56). Ursache sind die Quellen, nicht die Bewertung oder die Oberfläche. Die Arbeitspakete 1 und 2 haben damit an einem Teil gearbeitet, der erst nach einer brauchbaren Quelle Wert entfaltet – die Reihenfolge der Roadmap ist entsprechend umgestellt.
- **Ausgeführt:** 491 Tests unter Python 3.13 und 3.10 bestanden.
- **Nicht umgangen:** Der sichere Website-Abruf scheiterte in der Testumgebung an fehlender Namensauflösung. Der Schutz (Verbindung nur zur selbst geprüften Adresse) wurde nicht gelockert, um ein Messergebnis zu erzwingen.

**Die drei wichtigsten Schwachstellen:** (1) keine verlässliche Quelle für Handwerksbetriebe; (2) Website-Zuordnung weiter ungemessen; (3) Branche bei zwei Dritteln der Treffer unbekannt.

**Entscheid:** weiter mit dem lokalen OpenStreetMap-Auszug.

## Arbeitspaket 6 – OpenStreetMap manuell und offline (2.0.0-dev7)

Vorgabe des Eigentümers: Suche ohne festgelegte Branche; OpenStreetMap auf „manuell“; Wege mit geringem Aufwand zeigen, die Quelle nutzbar zu machen.

### Tatsächlich ausgeführt

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 504 Tests bestanden |
| davon neu: `tests/test_v2_osm_local.py` | 13 Tests |
| Browser-Tests | 6 von 6, davon 1 neu: Anleitung, Datei einlesen, Suche in einer PLZ – **ohne einen einzigen Abruf außerhalb des eigenen Rechners** |
| Leser gegen das offizielle Werkzeug `osmium` | Knoten, Koordinaten (auch negative), Umlaute, Gebäudeumrisse stimmen überein |
| Tempo an erzeugter Datei (3 Mio. Knoten, 200.000 Wege) | 4,5 s, 59 MB Arbeitsspeicher |
| Echter Geofabrik-Auszug | **nicht geprüft** – Download in der Testumgebung nach Freigabe des Hosts weiterhin abgebrochen |

### Bewertung

| Kriterium | Note | Beleg |
|---|---|---|
| Nutzen | 4 | Die einzige Quelle mit kleinen Betrieben ist nicht mehr von überlasteten Servern abhängig. Der Nachweis an echten Daten fehlt. |
| Bedienbarkeit | 4 | Ein Kasten mit Stand, drei Wegen samt Aufwand und einem Knopf; Bildschirmfoto geprüft. |
| Quellenqualität | 4 | Lizenz und Stand des Bestands werden genannt; Einträge ohne PLZ werden bei PLZ-genauer Suche ehrlich als fehlend gemeldet. |
| Robustheit | 4 | Kaputte, abgeschnittene und fremde Dateien führen zu einer Meldung (Tests). |
| Sicherheit | 4 | Obergrenzen für Block- und Dateigröße; keine E-Mail-Adressen und Betreibernamen gespeichert (Test). |
| Kostenkontrolle | 5 | Keine Abhängigkeit, kein Netz nötig. |
| Erweiterbarkeit | 3 | Gebäudeumrisse ohne Koordinaten; PLZ-Zuordnung nur über die Adressangabe. |
| Testabdeckung | 4 | Echtes Dateiformat als Testdatei, aber kein großer echter Auszug. |

### Nachbesserung

1. Sieben bestehende Tests prüften den Online-Abruf, der jetzt nur noch auf Wunsch läuft; sie fordern ihn nun ausdrücklich an. Ihre Prüfungen sind unverändert.
2. Gebäudeumrisse fielen in der Umkreissuche ganz heraus; sie zählen jetzt über den Ortsnamen.
3. Bei widersprüchlicher PLZ-Angabe am Eintrag gilt die Angabe, nicht das abgefragte Gebiet.

### Die drei wichtigsten verbleibenden Schwachstellen

1. **Kein Test an einem echten Auszug.** Der erste Lauf beim Eigentümer ist der eigentliche Nachweis.
2. **Einträge ohne PLZ** fehlen bei PLZ-genauer Suche; wie viele das sind, ist ungemessen.
3. **Telefon und Öffnungszeiten** liegen im Bestand, erscheinen aber noch nirgends.

**Entscheid:** weiter; Praxistest mit echtem Auszug durch den Eigentümer.

## Arbeitspaket 7 – OpenStreetMap ausgebaut (2.0.0-dev8)

Behebt die Schwachstellen 2 und 3 aus Arbeitspaket 6.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 508 Tests bestanden |
| Browser-Tests | 6 von 6 |
| Einlesen mit zweitem Durchlauf (3 Mio. Punkte, 4.000 Umrisse) | 4,9 s, 41 MB Arbeitsspeicher |
| Echter Geofabrik-Auszug | weiterhin nicht geprüft |

- **PLZ-Schätzung:** 250 m zum nächsten Betrieb mit PLZ; Test belegt, dass ein weit entfernter Nachbar nicht zählt und eine eigene Angabe nie überschrieben wird. Die Trefferquote an echten Daten ist ungemessen.
- **Lage der Umrisse:** gegen die mit `osmium` erzeugte Datei geprüft.
- **Öffnungszeiten:** bewusst enger Leser; sechs unklare Schreibweisen ergeben „unbekannt“ statt einer falschen Aussage (Test).
- **Nachbesserung:** Der Browser-Test wartete nicht auf das Ende der Suche und bestand deshalb zufällig mit einem Zwischenstand. Er prüft jetzt den fertigen Lauf und die erwarteten vier Treffer.

**Verbleibende Schwachstellen:** (1) kein Test an einem echten Auszug; (2) Güte der PLZ-Schätzung an PLZ-Grenzen ungemessen; (3) Öffnungszeiten steuern die Kontaktreihenfolge noch nicht.

**Entscheid:** weiter; der echte Auszug beim Eigentümer ist der nächste Nachweis.

## Arbeitspaket 8 – Größere Zielgruppe (2.0.0-dev9)

Vorgabe des Eigentümers: Betriebe ohne Rechtsform einbeziehen und kennzeichnen. Dazu die nächsten Roadmap-Punkte.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 516 Tests bestanden |
| Browser-Tests | 6 von 6; der OpenStreetMap-Test prüft jetzt auch die Kennzeichnung und „Alle Treffer übernehmen“ |
| Sperrliste bei der Sammelübernahme | Widerspruch nach der Suche eingetragen → Treffer wird übersprungen (Test) |

**Fehler während der Arbeit:** Ein Kommentar, den ich mitten in eine Zeile setzte, schaltete die Einstellung „Websites automatisch suchen“ ab. Ein bestehender Test fiel sofort auf; behoben vor dem Commit.

**Bewertung:** Nutzen 4 (mehr Treffer, ohne Messung an echten Daten), Bedienbarkeit 4 (Bildschirmfoto der Trefferliste geprüft), Sicherheit 3 – die Zielgruppe enthält jetzt bewusst Einträge mit möglichem Personenbezug; SignalDesk kennzeichnet sie, prüft aber keine Rechtsgrundlage.

**Die drei wichtigsten Schwachstellen:** (1) Personenbezug bei Betrieben ohne Rechtsform: Kennzeichnung ja, aber keine eigene Löschfrist und kein Art.-14-Baustein für diese Leads; (2) Tempo der Sammelübernahme bei mehreren tausend Treffern ungemessen; (3) weiterhin kein Lauf mit echtem OpenStreetMap-Auszug.

**Entscheid:** weiter.

### Nachtrag: CI-Ergebnis für Commit `a08c5d1`

Unter Windows mit Python 3.13 schlug `test_malformed_requests_never_500` fehl: Bei einer absichtlich kaputten Anfrage brach die Verbindung ab (`WinError 10053`), statt dass eine Fehlermeldung ankam. Ursache: Lehnt der Server eine Anfrage ab, bevor er ihren Körper gelesen hat, und schließt dann die Verbindung, bricht Windows sie hart ab. Unter Linux kommt die Antwort trotzdem an; deshalb fiel es nur dort auf.

Behebung im Server, nicht im Test: Nach jeder Anfrage liest der Server den ungelesenen Rest des Körpers (bis 1 MB) ein; bei größeren Körpern wird die Verbindung nicht weiterverwendet. Zwei neue Tests: einer prüft den Mechanismus direkt und schlägt ohne die Behebung fehl, einer prüft das Verhalten von außen. Der Nachweis unter Windows steht mit dem nächsten CI-Lauf aus. 518 Tests unter Python 3.13 und 3.10 bestanden.

## Arbeitspaket 9 – Datenschutz für Betriebe ohne Rechtsform (2.0.0-dev10)

Behebt Schwachstelle 1 aus Arbeitspaket 8.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 527 Tests bestanden (9 neu) |
| Browser-Tests | 6 von 6; der OpenStreetMap-Test prüft jetzt auch Hinweis und Verlängerung in der Firmenakte |
| Migration einer Datenbank mit Schema 28 | Nachweise für bereits übernommene Betriebe nachgezogen, einmalig (Test) |

- **Löschen ist bewusst eng gefasst:** Kunden und Firmen im laufenden Gespräch werden nie still gelöscht; eine Sperre überlebt die Löschung (Test); der Löschnachweis enthält keinen Namen (Test).
- **Fehlersuche im Browser-Test:** Er schlug nur im Bildschirmfoto-Modus fehl, weil die Firmenakte nach dem Verlängern neu gezeichnet wurde, während das Foto entstand. Mein erster Erklärungsversuch (Klick auf eine neu gezeichnete Listenzeile) war falsch und wurde zurückgenommen.

**Verbleibende Schwachstellen:** (1) Die Rechtsgrundlage wird nicht im Einzelfall geprüft; (2) der Art.-14-Hinweis muss von Hand versendet und vermerkt werden; (3) weiterhin kein Lauf mit echtem OpenStreetMap-Auszug.

**Entscheid:** weiter mit Roadmap und Oberfläche.

## Arbeitspaket 10 – Darstellung: Themes, Hell/Dunkel, Kompakt (2.0.0-dev11)

Auftrag: Oberfläche übersichtlicher machen, Vorschläge in Hell und Dunkel, mehrere Themes in den Einstellungen wählbar; danach Roadmap.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 537 Tests bestanden (10 neu) |
| Browser-Tests | 7 von 7 (1 neu: umschalten, nach Neuladen erhalten, frischer Browser übernimmt die Wahl vom Server, „Wie System“ folgt dem Betriebssystem, keine Abrufe nach außen) |
| Kontrast | 4 Themes × 2 Modi × 24 Farbpaare gegen WCAG; anfangs 21 Verstöße, nach Anpassung 0 (Test) |
| Feste Farben | 284 Farbwerte in 42 Rollen; Test schlägt bei jeder neuen festen Farbe fehl (mit eingebautem Fehler geprüft) |
| Abweichung „Klassisch“ zum Stand davor | Farbwert für Farbwert gegen das alte Stylesheet verglichen: Markenfarben gleich, 67 sichtbar verschobene Töne, vor allem Grautöne und Linien |
| Messung bei 1366 × 768 | Kompakt: Seitenkopf 255 → 162 px, sichtbare Lead-Zeilen 5 → 8 |
| Release-Paket | enthält `theme.js`, `appearance.py`, Vorschlagsdokument |

**Selbstbewertung 4 von 5.** Abzug, weil „Klassisch“ nicht pixelgleich geblieben ist und durchscheinende Schatten (48 Stellen) noch feste Werte tragen.

Nachbesserungen innerhalb des Pakets:
1. Der erste Rollenentwurf hatte die Markenfarbe Mint durch ein helleres Mint ersetzt und Texte in der dunklen Seitenleiste an das Grau für helle Flächen gekoppelt. Gefunden durch den Farbvergleich gegen die alte Datei; behoben mit eigener Rolle für Nebentexte in der Seitenleiste.
2. „Kompakt“ vergrößerte versehentlich die Abstände der Seitenleiste, weil die Regel spezifischer war als die vorhandene. Im Bildschirmfoto gefunden und entfernt. Danach brachte Kompakt nur 37 px; erst das Ausblenden der Erklärtexte ergab die gemessenen 93 px.

**Verbleibende Schwachstellen:** (1) Darstellung je Installation, nicht je Nutzer; (2) der Lead-Dialog ist rund 7.800 px lang – Vorschlag V2 in `UI_UX_VORSCHLAEGE.md`; (3) weiterhin kein Lauf mit echtem OpenStreetMap-Auszug.

**Entscheid:** Vorschläge V2–V9 dem Eigentümer zur Auswahl vorlegen; Empfehlung V2 → V3 → V6.

## Arbeitspaket 11 – Firmenakte mit Reitern, einheitliche Statusmarken (2.0.0-dev12)

Auftrag: weitermachen nach dem Merge von dev10/dev11; umgesetzt wurden die empfohlenen Vorschläge V2 und V6 aus `UI_UX_VORSCHLAEGE.md`.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 543 Tests bestanden (6 neu) |
| Browser-Tests | 8 von 8 (1 neu: Kopf, jeder Reiter zeigt genau seinen Bereich, Tastatur, Sprung in verdeckten Reiter, neuer Lead ohne Reiter); die älteren Tests, die in der Firmenakte klicken, laufen unverändert |
| Kein Element verloren | alle 27 IDs des Dialogs vor dev12 vorhanden, jedes im fachlich richtigen Reiter (Test) |
| Länge | längster Reiter 2.322 px statt rund 7.800 px für den ganzen Dialog (1366 × 768, Test verlangt unter 4.000 px) |
| Statusmarken | jede der fünf Stufen mit Symbol; negative Zustände in sechs Skripten von „off“ auf „bad“ umgestellt (Test) |

**Selbstbewertung 4 von 5.** Abzug, weil Filter- und Zählerchips noch eigene Formen haben und die Reiter keine Zähler zeigen (etwa offene Aufgaben).

Nachbesserung innerhalb des Pakets: Im ersten Entwurf stand im Reiter „Kontakt & Verlauf“ das Aktivitätsprotokoll ganz unten unter der Entscheider-Recherche – im Bildschirmfoto gesehen und nach oben gezogen, weil es die häufigste Handlung ist.

**Verbleibende Schwachstellen:** (1) Einstellungen weiter verstreut (V3 offen); (2) Darstellung je Installation; (3) weiterhin kein Lauf mit echtem OpenStreetMap-Auszug.

**Entscheid:** als Nächstes V3 (Bereich Einstellungen), dann V4 (Navigation).

## Arbeitspaket 12 – Produktreview Etappe A (2.0.0-dev13)

Auftrag: nächsten Sprint umsetzen und die Roadmap mit dem externen Produktreview vom 13.11.2026 abgleichen. Das Review prüfte
dev11 und empfahl, vor dem Menüumbau zuerst Eingabeschutz, Öffnungsfokus und eine eindeutige Bewertung umzusetzen. Deshalb
wurde der geplante Bereich „Einstellungen“ auf dev14 verschoben.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 554 Tests bestanden (11 neu in `tests/test_v2_review_etappe_a.py`) |
| Browser-Tests | 9 von 9 (neu `test_formguard_browser.py`: Abnahmefälle T02, T03, T04 des Reviews); zwei ältere Tests prüfen jetzt die korrigierten Texte |
| Erstellungswege ohne erfundene Werte | Formular, Schnittstelle, CSV-Import, „Bericht für Website“, Firmensuche (Test), Impressumsprüfung (Code) |
| Prüffall K01 | Logo „Basis“: Kundenteil nennt keine widersprechende Pauschalzahl mehr (Test) |
| Release-Paket | gebaut, enthält `formguard.js` |

**Selbstbewertung 4 von 5.** Abzug: Der Eingabeschutz gilt nur im Lead-Dialog, und M21 (Pilot mit echter Referenzliste) bleibt offen – er lässt sich in dieser Umgebung nicht ausführen.

Nachbesserungen innerhalb des Pakets:
1. Leere Schritte im Tagesplan wurden zunächst weiter durchgestrichen dargestellt und dann wegen eines gleichnamigen CSS-Klassennamens („empty“) zentriert – beides im Bildschirmfoto gesehen und mit eigener Klasse behoben.
2. Bei der Suche nach Erstellungswegen fielen zwei weitere Stellen auf, die die Leistung still vorbelegten (Impressumsprüfung, „Bericht für Website“); beide mitbehoben.

**Abweichungen vom Review, bewusst:** Nicht gespeicherte Eingaben bleiben nur im Arbeitsspeicher (keine lokal gespeicherten Entwürfe), weil Gesprächsnotizen nicht unbemerkt auf der Festplatte liegen sollen. Die Firmenakte bleibt vorerst ein Dialog mit Reitern; ob sie eine eigene Seite wird, entscheidet sich mit den direkten Adressen in dev14.

**Entscheid:** weiter mit Etappe B (dev14: Einstellungen und sechs Bereiche mit direkten Adressen).

## Arbeitspaket 13 – Sechs Bereiche und Einstellungen (2.0.0-dev14)

Auftrag: nächsten Sprint fertigstellen – laut abgeglichener Roadmap Etappe B, Teil 1 (Review M06, M07).

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 560 Tests bestanden (6 neu in `tests/test_v2_navigation.py`) |
| Browser-Tests | 10 von 10 (neu `test_navigation_browser.py`: Bereiche, Adressen, Neuladen, Zurück/Vor, Firma per Adresse, Filter in der Adresse, Einstellungen, schmaler Bildschirm; Abnahmefall **T05**). Fünf ältere Tests navigieren jetzt über die Bereiche statt über „Erweitert“. |
| Zuordnung | alle 16 bisherigen Menüziele als Reiter oder Hilfe-Verweis erreichbar (Test), Tabelle in `ROADMAP.md` |
| Struktur | keine doppelten IDs, kein Abschnitt außerhalb einer Ansicht (Test, mit eingebautem Fehler geprüft) |
| Release-Paket | gebaut, enthält `nav.js` |

**Selbstbewertung 4 von 5.** Abzug: Adressen fehlen noch für Filter weiterer Listen und für Firmen-Berichte; die Frage „Firmenakte als eigene Seite“ ist bewusst offen.

Gefunden und behoben während des Pakets:
1. Der Abschnitt „Wiederkehrende Recherche“ landete beim Verschieben hinter statt in der Ansicht „Recherche & Berichte“ und wäre auf jeder Seite erschienen. Der Browser-Test fiel darüber; ein Strukturtest verhindert es künftig.
2. Ein Klick auf einen Bereich öffnete zunächst die zuletzt benutzte Unteransicht. Das Review verlangt eine klare Standardansicht je Bereich – geändert.
3. Am Bereich „Einstellungen“ erschien ein Hinweispunkt, weil der KI-Status als Zähler galt – nur echte Zähler setzen den Punkt.
4. Die Einstellungen luden zunächst die ganze Angebotsansicht nach; dabei kam eine 400-Antwort der Angebotsliste bei unvollständigen Testdaten zum Vorschein. Geladen werden jetzt nur Katalog und Kalkulationsgrundlagen.
5. **Bestehender Fehler:** Der App-Start lief los, bevor alle Skripte geladen waren („renderPipeline is not defined“ beim Neuladen). Durch zwei weitere Skripte trat das häufiger auf; der Start wartet jetzt auf das vollständige Laden.

**Entscheid:** weiter mit dev15 (Review M08-Rest, M09, M11: Heute als Fokusliste, Filterchips und gespeicherte Ansichten, geführter Einstieg).

## Arbeitspaket 14 – Fokusliste, Arbeitsansichten, Einstieg (2.0.0-dev15)

Auftrag: nächsten Schritt ausarbeiten – laut Roadmap Etappe B, Teil 2 (Review M08, M09, M11).

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 570 Tests bestanden (9 neu in `tests/test_v2_focus.py`) |
| Browser-Tests | 11 von 11 (neu `test_focus_leadlist_browser.py`: Fokus, Erste Schritte, Arbeitsansichten, gespeicherte Ansicht, Leerzustand, Spalten, Start mit verzögertem Skript; Abnahmefall **T01**) |
| Reihenfolge | überfällige Zusage vor Termin vor heute Fälligem vor Nachfassen; Rückrufzusage vor A-Passung (Test) |
| Release-Paket | gebaut, enthält `focus.py` und `leadlist.js` |

**Selbstbewertung 4 von 5.** Abzug: Stapelaktionen fehlen noch, und die Fokus-Reihenfolge ist eine feste Regel, die erst der Pilot bestätigen muss.

Korrektur eines früheren Eintrags: In Arbeitspaket 13 stand der Startfehler („renderPipeline is not defined“) als behoben. Er war es nicht vollständig – die Prüfung `readyState === 'loading'` greift bei verzögerten Skripten nie, drei grüne Läufe waren Zufall. Jetzt wartet der Start immer auf `DOMContentLoaded`; ein Browser-Test lädt ein Skript absichtlich verzögert. Mit der alten Prüfung schlägt dieser Test fehl (geprüft).

**Entscheid:** Etappe B ist abgeschlossen. Weiter mit Etappe C – zuerst M12 (ein gemeinsamer Leistungskatalog mit Migration), danach M13 (mehrere Verkaufschancen je Firma).

## Arbeitspaket 15 – Zentraler Leistungskatalog (2.0.0-dev16)

Auftrag: zwei zusätzliche Dokumente vom 13.11.2026 (Bewertungsmodell für Websites, Leitfaden Kundenonboarding) auf Relevanz für M12 prüfen und passend einbauen. Ergebnis der Prüfung: Für M12 relevant sind die gemeinsame Leistungskennung, der Umfang je Leistung (Korrekturschleifen, Nutzungsrechte/Quelldateien, Betrieb/Schnittstellen), der Zahlungsplan als Vorgabe und die Abgrenzung der Analyseangebote (M31). Alles Übrige gehört zu anderen Maßnahmen und steht als M27–M39 in der Roadmap.

| Prüfung | Ergebnis |
|---|---|
| Regression unter Python 3.13 und 3.10 | je 585 Tests bestanden (15 neu in `tests/test_v2_catalog.py`; ältere Tests des Paket-Rechners in sechs Dateien rechnen jetzt über den Katalog) |
| Browser-Tests | 12 von 12 (neu `test_catalog_browser.py`: Vorlagen und Herkunft, geänderter Katalogwert in Vorlage, Hilfe-Karte und Angebot, Korrekturschleifen, Prüfpunkte nur intern, gespeichertes Angebot unverändert) |
| M12-Abnahme | geänderte Leistung gleich in Vorlage, Empfehlung, Angebot, Oberfläche; gespeicherte Angebote (auch im Format bis dev15) unverändert nach Katalog- und Grundlagenänderung und Neustart; Zuordnung 5/6/26 (+5) vollständig; K01 |
| Release-Paket | gebaut, enthält `catalog.py` und `LEISTUNGSKATALOG.md` |

Fehlerschleifen: (1) Der Browser-Test zeigte, dass die Angebotskarten der Hilfe nach einer Katalogänderung bis zum Neuladen den alten Preis behielten – behoben (Karten und Auswahl werden nach dem Speichern neu geladen). (2) Beim Prüfen der Vorlage „Conversion“ fiel ein bestehender Widerspruch auf: „Nicht enthalten: Texte (separate Position)“ neben einer Textposition – behoben.

**Selbstbewertung 4 von 5.** Abzug: Titel, Ausschlüsse und Vorlagen sind noch nicht in der Oberfläche änderbar, und die Abweichung der früheren Paketpreise kann nur der Eigentümer fachlich bewerten.

**Entscheid:** Vor dem Modellumbau M13 kommt ein P0-Paket aus den Ergänzungen (dev17): M27 Begriffe der Website-Bewertung, M35 Versandfassung, M36 Übergang nach Annahme.

## Noch nicht erstellte Dokumente aus dem Auftrag

`SAAS_LAUNCH_PLAN.md`, `DATA_SOURCE_MATRIX.md`, `PRODUCT_ONBOARDING.md`, `SECURITY_PRIVACY_CHECKLIST.md` gehören zu späteren Sprints und sind bewusst noch nicht angelegt. Die Roadmap ist mit 2.0.0-dev11 neu gefasst.
