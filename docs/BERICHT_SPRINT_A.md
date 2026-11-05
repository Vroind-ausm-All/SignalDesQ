# Sprint-Bericht A – Struktur & Tagesablauf (v1.9)

Gemäß `docs/MASTERPLAN_V3.md`, Sprint A.

## Was ist tatsächlich implementiert?

### Navigation nach Tagesablauf

- **Heute** und **Aufgaben** stehen oben.
- Darunter **1 · Kunden finden** (Firmen finden, Import & Prüfung), **2 · Recherchieren** (Research Center mit URL-Recherche, Website-Scoring, Kaufsignale), **3 · Verkaufen** (Leads, Pipeline, Kontakt & Termine, Angebote & Preise) und **4 · Abrechnen**.
- **Erweitert** ist eingeklappt: Datenqualität & System, KI-Studio, Sales-Playbook. Ist Ollama nicht erreichbar, steht beim KI-Studio „ohne KI“.
- Die Unter-Navigation in den Bereichen ist nach denselben Gruppen getrennt.
- Die Seitenleiste ist kompakter und passt eingeklappt auf einen 1366 × 768-Bildschirm.

### „Heute“ (neue Startseite, `today.py`, `today.js`)

1. **Tagesplan** in 6 Schritten. Jeder Schritt zeigt eine Anzahl, eine Begründung und einen „Los“-Knopf, der nächste offene Schritt ist hervorgehoben:
   1. Termine heute/morgen
   2. Wiedervorlagen
   3. Angebote nachfassen
   4. Kontaktaktionen freigeben
   5. Rechercheergebnisse prüfen
   6. Neue Firmen finden

   Der Knopf oben rechts springt direkt zum nächsten offenen Schritt.
2. **Wiedervorlage** (Termine zuerst, dann Überfälliges). Jeder Eintrag hat einen Knopf zur passenden Stelle; der Navigationspunkt „Heute“ zeigt die Zahl der überfälligen Punkte.

   | Eintrag | Bedingung |
   |---|---|
   | Aufgaben | fällig |
   | Kontaktaktionen | Freigabe offen (→ Freigabe prüfen) |
   | Nächste Schritte aus dem Lead | fällig |
   | Vereinbarte Rückrufe | erledigt, sobald ein neueres Gespräch dokumentiert ist; nicht bei Widerspruch |
   | Angebote nachfassen | ab 7 Tagen beim Kunden |
   | Angebotsentwürfe | ab 2 Tagen |
   | Bindefristen | endet innerhalb von 7 Tagen |
   | Begonnene Bedarfsanalysen | 1–4 von 5 Kernfragen beantwortet |
   | Termine | heute und morgen |

3. **Offenes Potenzial aus kalkulierten Angeboten:**
   - offene, gültige Angebote (davon „beim Kunden“);
   - angenommene, noch nicht abgerechnete Angebote (→ Rechnung erstellen);
   - davon getrennt Schätzungen ohne Angebot (→ Angebot kalkulieren, Firma vorausgewählt).

   Jede Zeile öffnet das passende Angebot.
4. **Klickbare Pipeline:** Jede Phase zeigt Anzahl, Angebotswert und die nächste Aktion:

   | Phase | Aktion |
   |---|---|
   | Recherche | Firma recherchieren |
   | Qualifiziert | Kontaktweg klären |
   | Kontakt geprüft | **Kontakt aufnehmen** |
   | Rückmeldung | Termin vereinbaren |
   | Termin | **Termine vereinbaren & vorbereiten** |
   | Angebot | Angebot nachfassen |
   | Gewonnen | Rechnung schreiben |

5. **„Was funktioniert gerade?“** zeigt ehrlich, ob Browser-Prüfung, lokale KI, verschlüsselte Sicherung und jede Firmensuche-Quelle funktionieren, mit der letzten Fehlermeldung. „Noch nicht ausprobiert“ wird nicht als Fehler gewertet.

### Pipeline-Ansicht

- Jede Spalte hat einen Aktionslink, jede Karte einen Aktionsknopf.
  - Kontakt geprüft: „Kontakt aufnehmen“ → Anruf- und Mail-Formular mit vorausgewählter Firma und Rechtsstatus-Hinweis.
  - Rückmeldung: „Termin vereinbaren“ → Terminformular mit vorausgewählter Firma.
  - Angebot und Gewonnen: Das neueste Angebot öffnet sich.
- Gesperrte Leads bekommen keinen Kontaktknopf.

### „Kontakt & Termine“ (vorher „Mein Sales-Tag“)

- Neu geordnet: 1 · Freigeben (mit Vorschlägen), 2 · Kontakt aufnehmen (Anruf und Mail), 3 · Termin vereinbaren, danach Protokoll.
- Sprungmarken oben; Direktsprünge aus „Heute“ und der Pipeline landen an der richtigen Stelle.

Datenbank und Schema sind unverändert (Schema 17). Neue Endpunkte: `GET /api/today` und `GET /api/system/capabilities`.

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **223 Tests grün**, davon 7 neu in `tests/test_sprintA_today.py`.
  - Wiedervorlage aus allen Quellen, mit Sortierung und ohne gesperrte Leads; Freigabe-Sprung; Rückruf entfällt nach neuerem Gespräch und bei Widerspruch.
  - Potenzial nur aus gültigen Angeboten, angenommen und nicht abgerechnet getrennt, Schätzung nur ohne Angebot.
  - Pipeline-Aktionen und -Werte.
  - Reihenfolge des Tagesplans und nächster Schritt.
  - Funktionsstatus (Quelle mit Fehler, „noch nicht ausprobiert“, KI aus).
  - HTTP-Endpunkte.
- **Klickdurchlauf im Browser** (Chromium, fiktive Daten), ohne Konsolenfehler:
  - Tagesplan und Wiedervorlage
  - Rückruf → Anrufformular mit Firma und Rechtsstatus
  - Pipeline-Karte „Kontakt geprüft“ → Kontakt aufnehmen; „Termin“ → Terminbereich
  - Potenzial → Angebot öffnen; Schätzung → Angebotsformular mit Firma
  - Pipeline-Kartenaktion „Termin vereinbaren“ → Terminformular mit Firma
  - Funktionsstatus; Mobilansicht 390 px ohne Überlauf; Seitenleiste bei 1366 × 768

## Was ist noch ungetestet?

- Der Eindruck im echten Arbeitsalltag. Ob Reihenfolge und Begriffe passen, zeigt erst dein Einsatz.
- Die Firmensuche selbst ist unverändert. Das ist Sprint B.

## Welche Grenzen bestehen?

- „Offenes Potenzial“ ist die Summe der Netto-Festpreise offener Angebote, keine gewichtete Prognose.
- Die Wiedervorlage zeigt nur, was im Tool dokumentiert ist (Aufgaben, Rückrufdatum, Angebotsstatus). Externe Kalender oder Postfächer werden nicht gelesen.
- KI-Studio und URL-Recherche funktionieren weiter auch ohne Ollama im Regelmodus. Der Status sagt nur, was fehlt.

## Was ist als Nächstes sinnvoll?

**Sprint B – Firmen finden, die wirklich funktionieren.** Dafür bitte:
1. den Wortlaut der GLEIF-Fehlermeldung und, wenn möglich, was bei Wikidata und OSM angezeigt wurde;
2. Region und Zielbranchen als Voreinstellung für den Startknopf.
