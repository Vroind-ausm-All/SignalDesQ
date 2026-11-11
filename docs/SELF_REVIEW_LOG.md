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

**Entscheid:** weiter, sobald die CI des Branches gelesen ist.

## Noch nicht erstellte Dokumente aus dem Auftrag

`SAAS_LAUNCH_PLAN.md`, `DATA_SOURCE_MATRIX.md`, `PRODUCT_ONBOARDING.md`, `SECURITY_PRIVACY_CHECKLIST.md` gehören zu späteren Sprints und sind bewusst noch nicht angelegt. Roadmap und README-Neufassung stehen ebenfalls aus.
