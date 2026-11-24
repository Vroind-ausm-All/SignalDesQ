# Recherche-Benchmark (SDQ-006)

Die Frage hinter dem Benchmark: Findet SignalDesk in einem Gebiet die Firmen, die es dort wirklich gibt, und ordnet es ihnen die richtige Website und Registernummer zu? Bisher gab es dazu nur Fixture-Messungen (`docs/bench/`), aber keine unabhängige Referenz (Audit, Abschnitt 3).

Mit SDQ-006 gibt es ein **Werkzeug**, aber **noch kein Ergebnis**. Ein Ergebnis entsteht erst, wenn Menschen eine Referenzliste geprüft haben. Werte aus synthetischen Listen sind keine Messung, und der Bericht schreibt das in seine erste Zeile.

## Ablauf

1. **Referenzliste anlegen.** Vorlage: [`docs/bench/research/vorlage-referenz.json`](bench/research/vorlage-referenz.json). Prüfen mit
   `python tools/research_benchmark.py validate referenz.json`.
   Wer lieber in einer Tabelle arbeitet (ab dev65): Tabellenvorlage ausfüllen (Spalten Suche, Ref-Nr, Firmenname, Rechtsform,
   PLZ, Ort, Website, Registernummer, Status, Beleg 1/2, Prüfer 1/2, Prüfdatum, Notiz), Beispielzeile löschen, dann
   `python tools/research_benchmark.py import-table liste.xlsx --out referenz.json --suche q1="Steuerberater 70173–70199" --vollstaendig q1 --methode q1="Kammerverzeichnis, Stichtag …"`.
   CSV mit `;` oder `,` geht auch (für `.xlsx` wird `openpyxl` gebraucht). In der Tabelle heißt eine leere Zelle bei Website
   oder Registernummer „nicht geprüft“, `keine` heißt „geprüft, gibt es nicht“. Andere Spalten werden abgelehnt.
2. **In SignalDesk recherchieren**, wie es eine Nutzerin tun würde: dieselbe Branche, dasselbe Gebiet, eine frische Datenbank.
3. **Lauf exportieren:**
   `python tools/research_benchmark.py export-run --db signaldesk.sqlite3 --query q1 --out lauf.json`.
   Exportiert werden nur Firmendaten (Name, Rechtsform, PLZ, Ort, Website, Registernummer), keine Ansprechpartner und keine Kontaktwege.
4. **Auswerten:**
   `python tools/research_benchmark.py evaluate referenz.json lauf.json --out ergebnis.json --md ergebnis.md`.
5. **Ergebnis ablegen** unter `docs/bench/research/`, zusammen mit Referenz, Lauf, Version und Datum. Im Reifeindex zählt es erst danach.

## So entsteht eine belastbare Referenzliste

- **Gebiete:** 3 bis 5 Suchen, wie sie Kundinnen stellen würden, z. B. „Steuerberater, PLZ 70173–70199“ oder „Schreinereien im Landkreis X“. Klein genug, um sie vollständig zu prüfen (etwa 20 bis 80 Firmen je Suche).
- **Unabhängig von SignalDesk:** Die Liste entsteht aus Quellen, die SignalDesk nicht nutzt oder die es nur teilweise abdeckt: Kammerverzeichnisse (Handwerkskammer, Steuerberaterkammer, IHK), Handelsregister, Branchenverbände, eine Begehung vor Ort. Wer die Liste aus SignalDesk-Ergebnissen baut, misst nur, ob SignalDesk sich selbst wiederfindet.
- **`complete: true` nur bei abschließender Erfassung.** Nur dann ist ein Fund außerhalb der Liste sicher falsch und die Präzision echt. Sonst gibt der Bericht eine obere und eine untere Schranke an.
- **Je Eintrag:** mindestens ein Beleg (`evidence`), Kürzel der Prüfenden (`checked_by`) und Prüfdatum (`checked_on`). Ziel sind zwei unabhängige Prüfende je Eintrag; der Bericht zählt, wie viele Einträge doppelt geprüft sind.
- **Website und Registernummer:** Text heißt „geprüfter Wert“, `null` heißt „geprüft, gibt es nicht“. Ein weggelassenes Feld heißt „nicht geprüft“ und wird nicht bewertet. Eine Seite auf Facebook, Instagram oder in einem Branchenbuch gilt nicht als eigene Website.
- **`status`:** `aktiv` gehört zur Suche. `geschlossen` und `ausser_bereich` (falsche Branche oder falscher Ort) stehen in der Liste, damit ein Fund dieser Firmen sicher als Fehler zählt.
- **Keine Personendaten.** Die Prüfung lehnt Felder wie E-Mail oder Ansprechpartner ab.

## Messgrößen

| Messgröße | Bedeutung |
|---|---|
| Vollständigkeit (Recall) | Anteil der aktiven Referenzfirmen, die SignalDesk gefunden hat |
| Genauigkeit (Präzision) | Anteil der Funde, die eine aktive Referenzfirma sind. Bei nicht abschließender Liste ist das eine obere Schranke |
| Präzision, ungünstigster Fall | Jeder nicht zugeordnete Fund gilt als falsch (untere Schranke) |
| Dubletten | Funde, die eine schon gefundene Firma ein zweites Mal liefern |
| Website richtig | bei Treffern mit geprüfter Website: gleiche Domain, oder beide ohne Website |
| **Website falsch zugeordnet** | Anteil der von SignalDesk genannten Websites, die falsch sind oder zu einer Firma ohne Website gehören. Das ist der teuerste Fehler, weil er zu falscher Ansprache führt |
| Registernummer richtig / falsch | wie bei der Website |

Jede Quote steht mit Zähler, Nenner und 95-%-Vertrauensbereich (Wilson) im Bericht. Bei 20 Firmen ist der Bereich breit, und das soll sichtbar bleiben.

**Zuordnung:** Ein Fund ist ein Treffer, wenn `identity.decide()` ihn für sicher dieselbe Firma hält. Dafür zählen Name, Rechtsform, Ort, Registernummer und LEI, **nicht die Website**. Sonst könnte eine falsch zugeordnete Website die Zuordnung selbst verfälschen. Eine Zuordnung, die nur „möglich“ ist, zählt nicht als Treffer. Verschiedene Registernummern schließen eine Zuordnung immer aus.

## Zielwerte (Vorschlag, Entscheidung offen)

Vorgeschlagene Hürde für das Launch-Gate „Recherchequalität gemessen“. Festgelegt sind die Werte erst, wenn die Produktverantwortung sie bestätigt.

| Messgröße | Vorschlag |
|---|---|
| Recall je Suche | ≥ 70 % |
| Präzision (abschließende Listen) | ≥ 85 % |
| Website falsch zugeordnet | ≤ 3 % |
| Dubletten | ≤ 2 % |
| doppelt geprüfte Referenzeinträge | ≥ 80 % |

## Noch nicht abgedeckt

- Es gibt keine echte Referenzliste. Die Datei unter `tests/fixtures/research_benchmark/` ist erfunden und prüft nur das Werkzeug.
- Telefon, Anschrift und Branche werden nicht bewertet, nur Firma, Website und Registernummer.
- Bewertet wird das Ergebnis, nicht der Weg: welche Quelle einen Fund geliefert hat, steht nicht in der Auswertung (siehe SDQ-008, Provider-Beschreibung).
