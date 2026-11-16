# UI-Baukasten (seit 2.0.0-dev49)

Verbindliche Grundlage für die Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](ROADMAP.md)).
Jede Ansicht wird aus denselben sieben Bausteinen gebaut. Die Klassen stehen in `sales_tool/public/style.css`
(Abschnitt „UI-Baukasten“, Präfix `ui-`, damit nichts Bestehendes kollidiert).

**Stand dev50:** Rahmen (Kopfzeile), Firmenliste und Heute sind umgestellt (Schritt 2). Die übrigen Ansichten sind **noch nicht**
umgestellt; sie folgen in den Schritten 3–6. Neu gebaute oder umgebaute Ansichten verwenden ausschließlich diese Bausteine.

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
(`--side`); unter 1081 px Breite untereinander. `.ui-page` stapelt Kopf, Werkzeugzeile und Inhalt mit 16 px Abstand und setzt den Seitenrand
(oben 24, seitlich 32 px; schmal 16 px).

### Ergänzungen seit dev50 (Schritt 2)

| Baustein | Klassen | Regel |
|---|---|---|
| Menü in der Werkzeugzeile | `<details class="ui-menu"><summary class="btn btn-ghost">Filter ▾</summary><div class="ui-menu-body">…`, darin `.ui-menu-item`, `.ui-menu-field`, `.ui-menu-sep`, `.ui-menu-split` | für „Weitere ▾“, „Filter ▾“, „Spalten ▾“; höchstens ein Menü offen, Klick daneben oder Escape schließt, ein Knopf im Menü schließt es, Häkchen nicht; das Menü bleibt im Fenster (`uikit.js`) |
| Liste als Tabelle | `<table class="ui-table">` mit `<tr class="ui-row-head">` und `<tr class="ui-row">` | gleiche Maße wie `.ui-list`/`.ui-row`, wenn Tests oder Tastaturführung an Tabellenzeilen hängen (Firmenliste) |
| Liste als Aufzählung | `<ol class="ui-rows">` mit `<li class="ui-row">` | ohne Aufzählungszeichen und Einzug (Heute → Als Nächstes) |
| Leerzustand | `.ui-empty` | eine Zeile über die volle Breite, z. B. „Keine Firma passt zu diesen Filtern.“ |
| Spalten einer Liste | `--ui-cols` (Grundwert: Was · nächster Schritt · fällig · Status · Wert · ›) | eine Liste mit zuschaltbaren Spalten setzt `--ui-cols` per CSSOM an der Liste (die CSP erlaubt keine `style`-Attribute) |
| Nur für Bildschirmleser | `.ui-sr` | z. B. Spaltenkopf „Öffnen“ über dem › |

**Schmal (bis 520 px)** zeigt jede Liste nur die erste Spalte (Was), die dritte (fällig) und das ›.

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
Diese Werte gelten als Abnahme für die umgebauten Ansichten ab Schritt 2. Seit dev50 ist die Kopfzeile der App 52 px hoch
(vorher 82 px); Firmen und Heute erreichen die Werte (gemessen bei 1280 × 720 mit 9 fiktiven Firmen):

| Messung | dev49 | dev50 | Abnahme |
|---|---|---|---|
| Firmen: Oberkante der ersten Firmenzeile | 574 px | 221 px | ≤ 280 px |
| Firmen: Zeilen ganz sichtbar | 2 | 8 | ≥ 7 |
| Firmen: Zeilenhöhe / Inhaltsschrift | 73 px / 12 px | 56 px / 14 px | 56 px, nicht kleiner |
| Heute: Oberkante der Liste „Als Nächstes“ | 342 px | 184 px | ≤ 200 px |
| 390 × 844: Firmen, erste Firmenzeile | 846 px (unter dem Bildrand) | 342 px | kein waagerechtes Scrollen |

Prüffall: `tests/e2e/test_ui_firmen_heute_browser.py`.

## Was wohin zog (Schritt 2, dev50)

Keine Funktion entfiel. Je verschobener Funktion: bisheriger Ort, neuer Ort, Prüffall.

| Funktion | Bisher | Jetzt | Prüffall |
|---|---|---|---|
| Reiter des Bereichs (z. B. Firmenliste · Pipeline · Datenpflege) | eigene Leiste unter der Kopfzeile | links in der Kopfzeile; Bereiche mit nur einer Ansicht (Angebote, Abrechnen) ohne Reiter; schmal als zweite Zeile der Kopfzeile | `test_ui_firmen_heute_browser`, `test_navigation_browser`, `test_mobile_nav_browser` |
| Brotkrumen „Bereich / Ansicht“ | Kopfzeile | entfällt breit (die Reiter zeigen die Ansicht); schmal steht der Bereich neben „☰ Menü“ | `test_mobile_nav_browser` |
| Datum | Kopfzeile | Zusatz im Seitenkopf von „Heute“ („Montag, 16. November“) | `test_ui_firmen_heute_browser` |
| Hell/Dunkel-Umschalter | Kopfzeile | Einstellungen → Darstellung (Wie System · Hell · Dunkel) | `test_appearance_browser`, `test_ui_firmen_heute_browser` |
| „＋ Neuer Lead“ | Kopfzeile, auf jeder Seite | „＋ Neue Firma“ als Hauptaktion der Firmenliste und Befehl „Neue Firma anlegen“ in Strg+K | `test_ui_firmen_heute_browser`, `test_akte_tabs_browser`, `test_formguard_browser` |
| Erklärtext der Firmenliste und Eyebrow | über der Liste | Hinweis unter der Liste und `title` der Überschrift | – (Text) |
| Trefferzahl und aktive Filter | Leiste über der Tabelle | Zusatz im Seitenkopf („2 von 9 Firmen · Phase Angebot · Filter zurücksetzen“) | `test_focus_leadlist_browser`, `test_ui_firmen_heute_browser` |
| Arbeitsansichten Alle · Heute fällig · Ohne nächsten Schritt | Chips über der Tabelle | Reiter in der Werkzeugzeile | `test_focus_leadlist_browser` |
| Angebote nachfassen · Recherche prüfen · Passung A/B · Bestandskunden | Chips | „Weitere ▾“ (gewählte Ansicht steht dann auf dem Knopf) | `test_ui_firmen_heute_browser` |
| Eigene Ansichten | Chips mit ✕ | als Reiter (★ Name); „Ansicht speichern“ und Löschen unter „Weitere ▾“ | `test_focus_leadlist_browser` |
| Phase, Zurücksetzen, CSV importieren | Werkzeugleiste | „Filter ▾“ | `test_ui_firmen_heute_browser` |
| Spalten Kaufsignal, Leistung | Häkchen „Weitere Spalten“ | „Spalten ▾“ | `test_focus_leadlist_browser`, `test_formguard_browser` |
| Spalte Letzter Kontakt | Standardspalte | zuschaltbar unter „Spalten ▾“ | `test_ui_firmen_heute_browser` |
| Fälligkeit des nächsten Schritts | kleine Zeile unter dem Schritt | eigene Spalte „Fällig“ als Status-Pille (überfällig rot, heute gelb) | `test_ui_firmen_heute_browser` |
| Heute: Begrüßung, Erklärtext | über „Als Nächstes“ | Begrüßung entfällt (Datum im Seitenkopf); Erklärtext als Hinweis unter den Klappzeilen | – (Text) |
| Heute: „Weiter: … →“ (nächster Schritt des Tagesplans) | grüner Knopf oben rechts | im Tagesplan (Klappzeile „Tagesplan & Tagesabschluss“), gleiche Kennung `#tdNext`; Hauptaktion ist jetzt „＋ Neuer Eingang“ | `test_ui_firmen_heute_browser` |
| Heute: Knopf je Schritt („Lead öffnen“) | Knopf in jeder Zeile von „Als Nächstes“ | Klick auf die Zeile (oder Enter) öffnet die Akte; „Erledigt“ für Aufgaben und Rückrufe; besonderes Ziel („Angebot öffnen“) als Textaktion | `test_focus_leadlist_browser`, `test_ui_firmen_heute_browser` |
| Heute: Erste Schritte | Karte unter „Als Nächstes“ | Hinweis „Einrichtung: n Punkte offen“ in der Statuszeile, springt in die Klappzeile „Erste Schritte“ | `test_focus_leadlist_browser`, `test_ui_firmen_heute_browser` |
| Heute: Eingang & Rückrufe, Als Nächstes kontaktieren | zwei Karten nebeneinander | Klappzeile „Eingang & Rückrufe“ (beide wie bisher darin) | `test_reach_browser` |
| Heute: Wiedervorlage | Karte | Klappzeile „Wiedervorlage“ | `test_ui_firmen_heute_browser` |
| Heute: Auslastung, Offenes Potenzial, Pipeline | Karte, Karte, Kachelreihe | Klappzeile „Kapazität & Potenzial“ | `test_reach_browser`, `test_postcalc_browser` |
| Heute: Tagesplan, Tagesabschluss | zwei Klappkarten | eine Klappzeile „Tagesplan & Tagesabschluss“ (`#tagesabschluss`) | `test_ui_workday` |
| Heute: „Was funktioniert gerade?“ | Klappkarte | Klappzeile „Systemstatus“ | `test_ui_firmen_heute_browser` |
