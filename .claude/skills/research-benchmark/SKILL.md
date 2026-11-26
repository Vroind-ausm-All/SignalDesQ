---
name: research-benchmark
description: Verlangt eine reproduzierbare Messung vor und nach jeder neuen oder geänderten Extraktions-, Zuordnungs- oder Discovery-Regel von SignalDesk (identity.py, homepage.py, sweep.py, imprint.py, Extraktoren, Discovery). Verwenden bei „Regel verbessern“, „Treffer erhöhen“, „Zuordnung ändern“, „neuen Extraktor einbauen“.
---

# Erst messen, dann freigeben (R1.7)

Zweck: Eine Regel gilt erst als Verbesserung, wenn sie auf derselben Testmenge vor und nach der Änderung gemessen wurde und
nichts Wichtiges schlechter wird. Werkzeug: `tools/research_benchmark.py` (Format und Messgrößen: `docs/RECHERCHE_BENCHMARK.md`);
für Abruf-Laufzeiten `tools/bench_fetch.py`. Die Reihenfolge der Schritte prüft `tests/test_skills_registry.py` nicht – der
Bericht im PR muss sie belegen.

## Eingaben
- Der Diff der Regel.
- Eine Testmenge: die private Referenzliste des Eigentümers (R1.6, außerhalb des Repositorys) oder, solange sie fehlt, die
  erfundenen Fälle unter `tests/fixtures/research_benchmark/` und die Regressionstests der Regel.

## Ablauf

1. **Frage festlegen:** Welche Messgröße soll besser werden (Recall, Präzision, Website falsch zugeordnet, Registernummer,
   Company Match Precision), und welche darf nicht schlechter werden?
2. **Vorher messen:** auf dem Stand ohne Änderung `export-run` und `evaluate` mit derselben Referenz; Version, Datum und Befehl notieren.
3. **Abstimm- und Testmenge trennen:** Regeln nur an der Abstimmmenge entwickeln; die Testmenge erst für die Endmessung öffnen.
4. **Nachher messen:** gleicher Befehl, gleiche Referenz, gleiche Datenbank-Ausgangslage.
5. **Vergleichen:** Zähler, Nenner und 95-%-Vertrauensbereich je Messgröße; jede neue Fehlklassifikation einzeln ansehen.
   Überlappen die Bereiche vollständig, ist die Verbesserung nicht belegt – so berichten.
6. **Regressionstest:** jeden gefundenen Fehlerfall als erfundenen Fall in die Tests aufnehmen (mit altem Code rot).
7. **Ablegen:** Ergebnis unter `docs/bench/research/` (ohne Personendaten), im PR mit Vorher/Nachher-Tabelle.

## Ausgabe
Tabelle Vorher/Nachher je Messgröße mit Zähler/Nenner und Vertrauensbereich, Liste neuer Fehlklassifikationen, Urteil
„belegt besser / nicht belegt / schlechter“.

## Sicherheitsregeln
- Ergebnisse aus erfundenen Fixtures sind keine Messung an echten Firmen; das steht in der ersten Zeile des Berichts.
- Keine echten Personendaten und keine Referenzliste im öffentlichen Repository; keine echten Websites in Tests abrufen.
- Eine schlechtere Messgröße wird nicht weggelassen, sondern berichtet und begründet.

## Beispiel
Änderung: „Marke und Firmenname getrennt abgleichen (homepage.py).“
Ergebnis (erfundenes Beispiel, keine Messung): Vorher auf `tests/fixtures/research_benchmark/` Website falsch zugeordnet 2/18, nachher 0/18 (Bereiche überlappen,
daher „nicht belegt“ an echten Firmen); zwei neue Regressionsfälle in `tests/test_v2_website_matching.py`; Messung an der
Referenzliste steht aus, bis R1.6 vorliegt.
