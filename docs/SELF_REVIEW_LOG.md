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

## Noch nicht erstellte Dokumente aus dem Auftrag

`SAAS_LAUNCH_PLAN.md`, `DATA_SOURCE_MATRIX.md`, `PRODUCT_ONBOARDING.md`, `SECURITY_PRIVACY_CHECKLIST.md` gehören zu späteren Sprints und sind bewusst noch nicht angelegt. Roadmap und README-Neufassung stehen ebenfalls aus.
