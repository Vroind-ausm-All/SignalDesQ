---
name: ponytail
description: Arbeitsweise „kleinste vollständige Änderung“ für SignalDesk nach dem externen Original Ponytail (MIT, gepinnt). Verwenden bei jeder Code-Änderung, Fehlerbehebung, Umbau oder Paketwahl und wenn jemand „ponytail“, „einfachste Lösung“, „YAGNI“ oder „zu aufgebläht“ sagt. Stufen: lite, full (Standard), ultra.
---

# Ponytail – kleinste vollständige Änderung

Zweck: Eine Aufgabe ganz lösen, mit so wenig neuem Code wie möglich. Grundlage ist das unveränderte Original
[`ORIGINAL.md`](ORIGINAL.md) (Ponytail 5.3.3, Commit `ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10`, Lizenz in [`LICENSE`](LICENSE)).
Dieser Skill übernimmt nur die Arbeitsanweisung, **ohne** Plugin, Hooks, Statuszeile, Kosten-Tabelle oder Webhook
(Regel 3 in `docs/SKILLS_REGISTRY.md`). Wo das Original und SignalDesk voneinander abweichen, gilt SignalDesk.

## Eingaben
- Die Aufgabe und der Code, den sie berührt (Aufrufer, Tests, Fixtures, Konfiguration, Exporte).
- Optional die Stufe: `lite`, `full` (Standard) oder `ultra`.

## Ablauf

1. **Reichweite klären:** Alle Stellen auflisten, die die Änderung erreichen muss. Hilfe dabei:
   `python tools/code_graph.py affected <datei>` und `python tools/code_graph.py explain <funktion>`.
2. **Erste Lösung nehmen, die vollständig trägt** (Reihenfolge aus dem Original):
   braucht es das überhaupt → gibt es das schon in SignalDesk → Standardbibliothek → bereits installierte Abhängigkeit →
   eine lesbare Zeile → sonst das Minimum an Code.
3. **Keine neue Abhängigkeit für ein paar Zeilen.** Ist sie doch nötig: Skill `dependency-security`.
4. **Fehler an der Ursache beheben:** vorher alle Aufrufer suchen, im gemeinsamen Code einmal beheben – etwa in
   `sales_tool/workday.py::assert_contact_allowed` statt in jedem einzelnen Kontaktweg.
5. **Neue nicht-triviale Logik bekommt einen Test** (Verzweigung, Schleife, Parser, Geld, Sicherheit).
6. **Abschluss:** ein bis zwei Zeilen, was weggelassen oder nicht geprüft wurde und welches Risiko bleibt.

## Ausgabe
- Der kleinste vollständige Diff mit den Tests, die er braucht.
- Am Ende der Antwort: weggelassen / nicht geprüft / Risiko – auf Deutsch.

## Sicherheitsregeln
- **Nie gekürzt** werden die Regeln aus `CLAUDE.md`: Sperrprüfung (`workday.contact_lock`), Belegpflicht
  (`research/evidence.py::validate_fields`), kontrollierter Abruf (`research/safe_urls.py`), Mandantentrennung
  (`tenancy.py`), GoBD-Schutz, Validierung an Vertrauensgrenzen, Fehlerbehandlung gegen Datenverlust, Barrierefreiheit.
- „Kleiner“ heißt nie: Test, Gate oder Prüfliste (`qa-release-gate`) weglassen oder abschalten.
- Sprache in Antworten, Kommentaren und Doku bleibt Deutsch, auch wenn das Original englisch ist.
- Das Original wird nicht ungeprüft aktualisiert: neue Version nur mit neuem Pin und neuer Prüfsumme im Skills-Register.

## Beispiel
Aufgabe: „Im Angebotsdialog ein Datumsfeld für die Gültigkeit ergänzen.“
Ergebnis: kein Datepicker-Paket und kein eigener Kalender, sondern das vorhandene Formularmuster in
`sales_tool/public/quotes.js` mit `<input type="date">`; Prüfung des Datums im Server an der bestehenden Stelle; ein Test
für ein ungültiges Datum. Schlusszeile: „Weggelassen: Vorbelegung aus Vorlage. Risiko: keins bekannt.“
