# UI-Baukasten (seit 2.0.0-dev49)

Verbindliche Grundlage für die Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](ROADMAP.md)).
Jede Ansicht wird aus denselben sieben Bausteinen gebaut. Die Klassen stehen in `sales_tool/public/style.css`
(Abschnitt „UI-Baukasten“, Präfix `ui-`, damit nichts Bestehendes kollidiert).

**Stand dev49:** Die Klassen und Maße stehen bereit; die vorhandenen Ansichten sind **noch nicht** umgestellt. Das geschieht
schrittweise ab Schritt 2 (Firmen und Heute). Neu gebaute oder umgebaute Ansichten verwenden ausschließlich diese Bausteine.

## Die sieben Bausteine

| Nr. | Baustein | Klassen | Regel |
|---|---|---|---|
| 1 | Seitenkopf | `.ui-head` mit `h1`, `.ui-meta`, `.ui-back`, `.ui-sp` | 40 px hoch: (← Zurück) Titel, Status, Zusatz – höchstens eine grüne Hauptaktion, oben rechts |
| 2 | Werkzeugzeile | `.ui-tool`, `.ui-search`, `.ui-tabs`/`.ui-tab` (Ansichten), `.ui-strip` | 36 px hoch; Reihenfolge immer: Suche, Ansichten, Filter, Spalten |
| 3 | Liste | `.ui-list`, `.ui-row-head`, `.ui-row`, `.ui-main`, `.ui-num`, `.ui-chev`, `.ui-group` | Zeile 56 px; Spalten Was · nächster Schritt · fällig · Status · Wert · ›; Klick auf die Zeile öffnet |
| 4 | Klappzeile | `<details class="ui-fold"><summary><b>Titel</b><span>Kurzstand</span></summary><div class="ui-fold-body">…` | Vertiefung immer als Klappzeile mit Kurzstand, nicht als weitere Karte |
| 5 | Status | `.ui-pill` und `.is-overdue`, `.is-attention`, `.is-done`, `.is-underway` | Farbe nur mit Bedeutung: rot überfällig/abgelehnt, gelb heute/prüfen, grün erledigt/belegt, blau unterwegs, grau neutral |
| 6 | Knöpfe | `.btn.btn-primary` (Hauptaktion), `.btn.btn-ghost` (Nebenaktion), `.ui-txt` (Zeilenaktion) | Knöpfe 36 px; in Zeilen nur Textaktionen |
| 7 | Abstände und Schrift | `--s1`…`--s6`, `--row`, `--ctl`, `--side`; `.ui-section`, `.ui-small` | Abstände 4/8/12/16/24/32; Schrift Titel 26 · Abschnitt 16 · Inhalt 14 · Zusatz 12 |

Dazu das **Kontextlayout** `.ui-with-side` mit `.ui-side`: Inhalt links, rechts eine 320 px breite Kontextspalte
(`--side`); unter 1081 px Breite untereinander. `.ui-page` stapelt Kopf, Werkzeugzeile und Inhalt mit 16 px Abstand.

## Regeln der Anwenderlogik

1. **Aufbau jeder Seite:** Seitenkopf (40 px) → Werkzeugzeile (36 px) → Inhalt. Keine Erklärtexte zwischen Kopf und Inhalt.
2. **Eine Hauptaktion:** höchstens ein grüner Knopf je Seite, oben rechts im Seitenkopf. Alles andere ist Neben- oder Textaktion.
3. **Werkzeugzeile:** Suche, Ansichten, Filter, Spalten – in dieser Reihenfolge, auch wenn Teile fehlen.
4. **Listen:** Spalten in der festen Reihenfolge Was · nächster Schritt · fällig · Status · Wert · ›. Die ganze Zeile öffnet;
   Aktionen in der Zeile nur als Text (`.ui-txt`). Schmal (bis 520 px) zeigt die Liste Was · fällig · › – die Spalten 2, 4 und 5
   treten zurück, gehören also nicht zu dem, was man unterwegs zwingend sehen muss.
5. **Detailseiten:** ← Zurück, Titel, Status, eine Hauptaktion, darunter Reiter; rechts 320 px Kontext (`.ui-with-side`).
6. **Vertiefung:** als Klappzeile mit Kurzstand (`.ui-fold`), damit man ohne Aufklappen sieht, ob sich das Öffnen lohnt.
7. **Farbe nur mit Bedeutung** (siehe Status) und nur über Theme-Variablen (`var(--…)`); keine festen Farbwerte in Regeln.
   Ein Test prüft das für das ganze Stylesheet.
8. **Abstände** nur aus der Reihe 4/8/12/16/24/32 (`--s1`…`--s6`); Seitenrand 32, zwischen Blöcken 16, in Karten 16.
9. **Navigation:** sechs Bereiche in der Seitenleiste, die Ansichten eines Bereichs als Reiter. Bei schmaler Breite (bis 520 px)
   öffnet „☰ Menü“ in der Kopfzeile die Seitenleiste als Schublade (seit dev49).

## Messwerte des Zielbilds

Gemessen am Prototyp bei 1280 × 720 px (Oberkante des Bausteins im Fenster, auf jeder Seite gleich):

| Baustein | Oberkante |
|---|---|
| Seitenkopf | 76 px |
| Werkzeugzeile | 132 px |
| Inhalt | 184 px |

Weitere Zielwerte: Listenzeile 56 px, Knöpfe und Felder 36 px, Kontextspalte 320 px, Abschnittsliste 240 px.
Diese Werte gelten als Abnahme für die umgebauten Ansichten ab Schritt 2; die heutigen Ansichten erreichen sie noch nicht
(die Kopfzeile der App ist z. B. 82 px hoch statt 52 px wie im Prototyp).
