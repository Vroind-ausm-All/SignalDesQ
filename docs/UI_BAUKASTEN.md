# UI-Baukasten (seit 2.0.0-dev49)

Verbindliche Grundlage für die Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](ROADMAP.md)).
Jede Ansicht wird aus denselben sieben Bausteinen gebaut. Die Klassen stehen in `sales_tool/public/style.css`
(Abschnitt „UI-Baukasten“, Präfix `ui-`, damit nichts Bestehendes kollidiert).

**Stand dev53:** Rahmen (Kopfzeile), Firmenliste und Heute (Schritt 2), „Finden → Sichten“ und „Finden → Neue Suche“ (Schritt 3),
der Bereich „Angebote“ (Schritt 4) sowie Einstellungen und Abrechnen (Schritt 5) sind umgestellt. Die übrigen Ansichten sind **noch nicht**
umgestellt – auch die Unteransichten von „Finden → Analysen“ und „Import“ haben nur die neue Reiterzeile bzw. einen neuen ersten Abschnitt;
die Firmenakte folgt in Schritt 6. Innerhalb der Angebote stehen die Arbeitsschritte, die Nachkalkulation, die Bestandskunden und das
Formular des Editors noch in ihren bisherigen Bausteinen – nur geordnet und eingebettet; ebenso in den Einstellungen die Formulare der
Abschnitte (Karten mit Überschrift), im KI-Studio und Playbook der Inhalt und in Abrechnen das Rechnungsformular, Ausgaben, Auswertung und
Steuer & Export. Neu gebaute oder umgebaute Ansichten verwenden ausschließlich diese Bausteine.

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

### Ergänzungen seit dev51 (Schritt 3): Formular-Bausteine

| Baustein | Klassen | Regel |
|---|---|---|
| Karte | `.ui-card` | ein Block zusammengehöriger Eingaben (z. B. Ort · Umkreis · Branchen · „Wen suchst du?“), 16 px Innenabstand; keine Karten in Karten |
| Feld | `<label class="ui-field">Beschriftung<input …></label>` | Beschriftung 12 px darüber, Feld 36 px hoch |
| Auswahlgruppe | `.ui-seg` mit `<button aria-pressed>`; aktiv `.is-active` | eine Wahl aus wenigen Voreinstellungen; keine aktiv heißt „eigene Auswahl“ |
| Marke | `.ui-chip` mit `<button>×</button>` | gewählter Wert in einem Feld (z. B. Branche), × entfernt ihn |

### Ergänzungen seit dev52 (Schritt 4): Detailseite und Eingaben

| Baustein | Klassen | Regel |
|---|---|---|
| Reiter einer Detailseite | `.ui-tabs` mit `role="tablist"`, `.ui-tab` mit `role="tab"`/`aria-selected`, Inhalte mit `role="tabpanel"` | in der Werkzeugzeile der Detailseite; Pfeiltasten wechseln den Reiter |
| Zeile mit Vertiefung | `<details><summary class="ui-row">…</summary><div class="ui-fold-body">…` | Listenzeile, die aufklappt statt zu öffnen (Positionen eines Angebots); das › dreht sich |
| Prüfliste und Ablauf in der Kontextspalte | `.ui-card` mit `<ul class="qt-checks">`/`<ol class="qt-phases">`, Zeichen `.qt-ico` (✓ grün, ! rot, i gelb, Ziffer grau, aktuelle Phase gefüllt) | höchstens eine Zeile je Punkt, Zusatz 12 px darunter; jede Phase springt zu ihrem Arbeitsschritt |
| Eingaben beim Neuzeichnen erhalten | `uiKeep(root, selector, draw)` und `uiSerial()` in `uikit.js` | jede Ansicht, die nach dem Speichern neu zeichnet, schreibt ungespeicherte Eingaben anderer Felder samt Fokus zurück und speichert der Reihe nach |

### Ergänzungen seit dev53 (Schritt 5): Abschnittsliste und Klappzeile mit Aktion

| Baustein | Klassen | Regel |
|---|---|---|
| Abschnittsliste | `.es-layout` mit `.es-nav-slot` (`nav.ui-list.es-nav`, darin `button.es-item` mit `.es-txt` = `<b>` Name + `.es-state` Kurzstand) und `.es-body` | links 240 px (`--list`), rechts der Abschnitt; Kurzstand nur aus vorhandenen Daten, eine Warnung als gelbe Pille (`.ui-pill.is-attention`), sonst grauer Text; aktiver Abschnitt `.is-active`/`aria-current`. Bis 1000 px eine Spalte: die Liste ist eine eigene Ansicht (`data-es-mode="list"`), ein Abschnitt zeigt „← Einstellungen“ (`.es-back`). Bisher nur in den Einstellungen (`einstellungen.js`) |
| Klappzeile mit Aktion | `<details class="ui-fold ui-fold-act"><summary><b>…</b><span>Kurzstand</span><button class="ui-txt">Aktion</button></summary>` | eine Textaktion rechts in der Klappzeile (z. B. „Stammdaten ergänzen“); ein Klick darauf springt, ohne die Zeile aufzuklappen |
| Sprungziel markieren | `.es-flash` | ein Sprung zu einem Element weiter unten im Abschnitt (bisherige Element-Adresse, Treffer der Suche) öffnet die Klappzeilen darüber, scrollt dorthin und umrandet es kurz |
| Eingabeschutz außerhalb der Akte | `window.formGuard.ask(namen)` in `formguard.js` | dieselbe Rückfrage wie in der Akte (Speichern · Weiter bearbeiten · Verwerfen); die Einstellungen fragen beim Abschnittswechsel, wenn ein Formular, das erst mit „Speichern“ gilt, Ungespeichertes enthält |

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

### Messwerte Finden (dev51)

Gemessen bei 1280 × 720 mit 11 fiktiven Treffern (Schiefer dunkel und Klassisch hell gleich):

| Messung | dev50 | dev51 | Abnahme |
|---|---|---|---|
| Neue Suche: Oberkante „Suche starten“ | 1.455 px (unter dem Bildrand) | 78 px | ≤ 140 px |
| Neue Suche: Unterkante Ort · Umkreis · Branchen / „Wen suchst du?“ | Ort 558 px, Branchen 977 px; „Wen suchst du?“ gab es nicht | 260 px / 336 px | im ersten Bildschirm (≤ 720 px) |
| Sichten: Oberkante der ersten Trefferzeile | 2.124 px | 221 px | ≤ 280 px |
| Sichten: Trefferzeilen ganz sichtbar | 0 (Zeile 117 px hoch) | 8 (Zeile 56 px) | ≥ 7 |
| 390 × 844: „Suche starten“ / erste Trefferzeile | 2.179 px / 3.573 px | 111 px / 374 px | kein waagerechtes Scrollen |
| Seitenlänge der Finden-Seite | 4.346 px (Suche und Sichtung auf einer Seite) | Neue Suche 1.022 px, Sichten 947 px | – |

Prüffall: `tests/e2e/test_ui_finden_browser.py`.

### Messwerte Angebote (dev52)

Gemessen bei 1280 × 720 mit 5 fiktiven Angeboten (Entwurf, gesendet mit Nachfassen, angenommen, abgelehnt, zweiter Entwurf);
Klassisch hell und Schiefer dunkel gleich:

| Messung | dev51 | dev52 | Abnahme |
|---|---|---|---|
| Liste: Oberkante der ersten Angebotszeile | 2.221 px (unter Formular, Vorschau, Kalkulation, Betreuung, Nachkalkulation, Studien) | 221 px | ≤ 280 px |
| Liste: Seitenlänge | 3.550 px | 720 px (eine Bildschirmseite) | – |
| Geöffnetes Angebot: Titel / Reiter / erste Position | Titel und Status gab es nicht; Arbeitsschritte („Gespeichertes Angebot“) bei 3.939 px | 82 px / 132 px / 221 px (Kopf der Positionen 184 px) | Positionen ≤ 260 px |
| Geöffnetes Angebot: Hauptaktion | keine (Freigabe, Versand, Zusage als Knöpfe in den Schritten) | eine, je Phase („Zur Freigabe prüfen“ … „Kick-off vorbereiten“) | genau eine |
| 390 × 844: erste Angebotszeile | 4.144 px | 330 px | kein waagerechtes Scrollen (390 px) |

Prüffall: `tests/e2e/test_ui_angebote_browser.py`.

## Was wohin zog (Schritt 3, dev51)

Keine Funktion entfiel. Alle bisherigen Adressen gelten weiter (`#/finden`, `#/finden/import`, `#/finden/recherche`, `#/finden/url-recherche`,
`#/finden/website-scoring`, `#/finden/kaufsignale`, `#/finden/bericht`); neu sind `#/finden/sichten` und `#/finden/neue-suche`.
`#/finden`, „Finden“ in der Seitenleiste und „Neue Firmen finden“ öffnen „Sichten“, solange offene Treffer warten, sonst „Neue Suche“.

| Funktion | Bisher | Jetzt | Prüffall |
|---|---|---|---|
| Reiter des Bereichs | sieben: Suche & Sichtung · Import & Prüfung · Recherche & Berichte · URL-Recherche · Website-Scoring · Kaufsignale (Bericht ohne Reiter) | vier: Sichten · Neue Suche · Import · Analysen; „Analysen“ hat eine eigene Reiterzeile (Recherche & Berichte · URL-Recherche · Website-Scoring · Kaufsignale, der Bericht gehört zu „Recherche & Berichte“) | `test_ui_finden_browser`, `test_navigation_browser` |
| Suchformular | obere Hälfte der Finden-Seite | „Finden → Neue Suche“ | `test_ui_finden_browser`, `test_osm_local_browser` |
| „▶ Arbeitstag starten – alle Quellen abfragen“ | Knopf unter dem Formular (1.455 px) | Hauptaktion „Suche starten“ im Seitenkopf (`#swGo`) | `test_ui_finden_browser` |
| Branchen | alle Gruppen mit Kästchen offen sichtbar, Suchfeld, „Auswahl leeren“ | Feld mit den gewählten Branchen als Marken (× entfernt); Klick klappt die Auswahl mit Suchfeld, allen Gruppen und „Auswahl leeren“ auf | `test_ui_finden_browser` |
| Quellen (GLEIF, Wikidata, OpenStreetMap, online abfragen, TED), Budget je Lauf | Kästchen unter dem Formular | Klappzeile „Quellen & Budget“ mit Kurzstand; zusätzlich Voreinstellungen unter „Wen suchst du?“ | `test_ui_finden_browser`, `test_osm_local_browser`, `test_ui_workday` |
| „Wen suchst du?“ (Unternehmen, Vereine, öffentliche Einrichtungen) | eigener Kasten | Klappzeile „Optionen“ als „Organisationsarten“; „Wen suchst du?“ heißt jetzt die Wahl der Voreinstellung (Handwerk & lokale Betriebe · Größere Firmen · Öffentliche Aufträge · Alles) | `test_ui_finden_browser` |
| Filter (nur operative, ohne Rechtsform, Websites automatisch suchen), TED bundesweit, eigene Schlagwörter | Kasten „Filter“, Quellen-Kasten, Formularzeile | Klappzeile „Optionen“ mit Kurzstand | `test_ui_finden_browser`, `test_osm_filter_reasons_browser` |
| Suchprofile | Zeile über dem Formular | Klappzeile „Suchprofile“ („▶ Profil starten“ ist Nebenaktion) | `test_ui_workday`, `test_ui_finden_browser` |
| Fortschritt der laufenden Suche (mit Gründen für „ausgefiltert“) | unter dem Formular | unter den Klappzeilen der neuen Suche, mit Zugang „n Treffer sichten →“ | `test_osm_filter_reasons_browser`, `test_ui_workday` |
| „Deine Gebiete & Suchläufe“ (Sichten, Erneut suchen) | Liste unter den Treffern | Liste „Letzte Suchen“ in „Neue Suche“; Klick auf die Zeile öffnet „Sichten“ für diese Suche | `test_ui_finden_browser` |
| Recherche-Aufträge | unter den Treffern | Klappzeile „Recherche-Aufträge“ in „Neue Suche“ | – (Anzeige der Auftragsliste, unverändert) |
| Einzelne Quelle gezielt abfragen (Lead-Finder, manuelle Quellen) | Klappkarte unter den Treffern | Klappzeile in „Neue Suche“ | – (unverändert) |
| Firmenliste / GLEIF-Export importieren (`#swFile`) | Knopf neben „Arbeitstag starten“ | „Finden → Import“, erster Abschnitt; Ergebnis öffnet „Sichten“ | `test_ui_finden_browser` |
| Gefundene Firmen | Karten mit allen Angaben und Knöpfen, untere Hälfte der Finden-Seite | „Finden → Sichten“: Liste Firma · Website · Entfernung · Quelle · „Übernehmen“ · ›; Klick oder Enter klappt Adresse, Website-Nachweis, Kontakt, Quellen, Dubletten und alle Aktionen auf | `test_ui_finden_browser`, `test_osm_local_browser` |
| Verwerfen, Website suchen, Website eintragen, ✓ Website passt / ✕ passt nicht, Dubletten (Gleiche Firma / Andere Firma / Ist diese Firma), Firma öffnen | Knöpfe je Karte | in der aufgeklappten Zeile; bis 520 px dort auch „Übernehmen“ | `test_ui_finden_browser` |
| Status-Auswahl Neu/Übernommen/… | Auswahlliste | Ansichten Offen · Mit Website · Übernommen (mit Anzahl) in der Werkzeugzeile; alle Status unter „Filter ▾“ | `test_ui_finden_browser` |
| Suchlauf, Website, Sortierung, Ort, Entfernung, ohne Ausschreibungen, Dubletten prüfen | Werkzeugleiste | „Filter ▾“ (dazu „Filter zurücksetzen“) | `test_ui_finden_browser`, `test_ui_workday` |
| Ausgewählte übernehmen / verwerfen, Übernehmen & Bericht, Websites suchen, Alle Treffer übernehmen | Knopfleiste über den Treffern | „Auswahl ▾“ in der Werkzeugzeile; Auswahl über die Kästchen vor dem Namen, „alle auf dieser Seite“ im Spaltenkopf | `test_osm_local_browser`, `test_ui_finden_browser` |
| Zählerzeile (neu · übernommen · verworfen · schon als Firma · mögliche Dubletten · ohne Website) | über den Treffern | Zusatz im Seitenkopf (Suche · n offen · Dubletten/ohne Website als Sprung), Summen unter der Liste | `test_ui_finden_browser` |
| OpenStreetMap nutzbar machen (Auszug einlesen, Stand, Anleitung, Overpass-Turbo-Abfrage, Bestand löschen) | Klappkasten auf der Finden-Seite | Einstellungen → Datenquellen (`#/einstellungen?abschnitt=datenquellen`); eigenes Ortsfeld für die Overpass-Abfrage, vorbelegt mit dem Ort der neuen Suche; „Neue Suche“ zeigt den Stand in der Statuszeile mit Verweis | `test_osm_local_browser`, `test_osm_filter_reasons_browser`, `test_ui_finden_browser` |
| Großer Firmenkatalog (GLEIF, offline) | Klappkasten auf der Finden-Seite | Einstellungen → Datenquellen | `test_ui_finden_browser` |
| Quellen prüfen | Klappkasten auf der Finden-Seite | Einstellungen → Datenquellen | `test_ui_finden_browser` |
| Messung: Stichprobe von Hand prüfen | Klappkasten auf der Finden-Seite | Firmen → Datenpflege (`#/firmen/datenpflege`) | `test_pilot_browser`, `test_ui_finden_browser` |
| Erklärtext, Hinweis „Fund ≠ Kontakterlaubnis“ | über dem Formular | `title` der Überschrift „Finden“ und Hinweis unter den Klappzeilen; rechtlicher Rahmen unverändert am Ende | – (Text) |
| Begriffe | „Lead“ in Treffern, Import, Analysen | sichtbar „Firma“ („Als Firma übernommen“, „schon Firma“, „Firma öffnen“, „Firmen auswählen“); interne Namen unverändert | `test_ui_finden_browser` |

## Was wohin zog (Schritt 4, dev52)

Keine Funktion entfiel. Fachliche Regeln (Bedarfsprüfung, Freigabe, Fassungen, Sperren, Statusfolge, Mindestverdienst, Zusatzaufträge,
optionale Positionen, Nachfassen) sind unverändert; Server und Datenmodell auch. Alle bisherigen Adressen gelten weiter (`#/angebote`,
`#/angebote?angebot=ID`); neu sind `#/angebote?neu=1` (Editor), `#/angebote/auftraege` und `#/angebote/auswertung`.

| Funktion | Bisher | Jetzt | Prüffall |
|---|---|---|---|
| Reiter des Bereichs | keiner (eine Ansicht „Angebote & Nachkalkulation“) | drei: Angebote · Aufträge & Betreuung · Auswertung | `test_ui_angebote_browser`, `test_ui_firmen_heute_browser` (Bereich ohne Reiter ist jetzt „Abrechnen“) |
| Gespeicherte Angebote (`#quoteHistory`, `[data-quote-open]`) | Abschnitt „05 / Angebotsverlauf“ am Seitenende (2.221 px) | Einstieg der Seite: Liste Angebot · Nächster Schritt · Fällig · Status · Betrag netto · ›, Klick oder Enter öffnet | `test_ui_angebote_browser`, alle Angebots-Tests |
| Nummer, Status, „gültig bis“, „Bindefrist abgelaufen“, „berechnet“ | Textzeile je Angebot | Zusatz unter dem Projekt, Status-Pille, Spalte „Fällig“ (Bindefrist bzw. Nachfassen), rote Pille bei abgelaufener Bindefrist; „noch nicht berechnet“ unter „Filter ▾“ | `test_ui_angebote_browser` |
| „Aktualisieren ↻“ (`#quoteRefresh`) | Kopf des Angebotsverlaufs | „Filter ▾“ | – (Knopf unverändert) |
| Angebotsformular (`#quoteForm`, Positionen, Vorlage, Steuer, Überarbeitung, Zusatzauftrag) | immer sichtbar oben auf der Seite | Editor als eigene Ansicht über „＋ Neues Angebot“ (`#/angebote?neu=1`); öffnet sich auch, wenn „Heute“, Recherche, Empfehlung oder „Überarbeiten“/„Zusatzauftrag erstellen“ eine Firma vorbelegen; „＋ Neues Angebot“ beginnt leer, außer der Editor enthält noch Ungespeichertes | `test_ui_angebote_browser`, `test_briefing_browser`, `test_catalog_browser`, `test_chances_browser`, `test_options_browser`, `test_revision_browser`, `test_addendum_browser` |
| „Festpreise berechnen“ / „Angebot als Entwurf speichern“ | grün / Nebenaktion | Nebenaktion / grün (die eine Hauptaktion des Editors); „＋ Hinzufügen“ Nebenaktion | `test_ui_angebote_browser` |
| Kundenvorschau (`#quoteCustomer`), Interne Kalkulation (`#quoteInternal`) | Karten „02“ und „03“ neben bzw. unter dem Formular | im Editor rechts bzw. darunter; im geöffneten Angebot als Reiter „Kundenvorschau“ und „Interne Kalkulation“ (dieselben Elemente wandern) | `test_catalog_browser`, `test_options_browser`, `test_ui_angebote_browser` |
| Grundsatz „Keine versteckten Aufschläge“, Verweis auf Einstellungen → Leistungen & Preise | Fußnote und eigene Karte | Hinweis unter der Liste und unter der Kalkulation im Editor | `test_navigation_browser` |
| Geöffnetes Angebot | „Gespeichertes Angebot …“ unter dem Angebotsverlauf, Positionen nur in der Kundenvorschau oben | Arbeitsplatz: „← Angebote“, Projekt als Titel, Status-Pille, Firma · Nummer, eine Hauptaktion je Phase; Reiter Positionen (Liste Leistung · Umfang · Art · Betrag, aufklappbar; Summe und Zahlung & Bedingungen als Klappzeilen) · Kundenvorschau · Interne Kalkulation · Verlauf | `test_ui_angebote_browser`, `test_offer_address_browser` |
| Freigabe, Versand, Nachfassen, Zusage/Absage, Projektstart, Kick-off/Projektkompass, Übergabe & Abnahme, Export, Rechnung, Überarbeiten, Zusatzauftrag, Grundlage je Position, Auftragsumfang (`#ofPanel`, `#ofStart`, `#ofKickoff`, `#ofHandover`, `#ofFollow`, `.of-basis`, `.of-scope`) | Liste unter „Gespeichertes Angebot“ | Karte „Arbeitsschritte“ unter dem Reiterinhalt (`#quoteSaved`, immer sichtbar); Versand und Entscheidung vor der Freigabe als eingeklappte Vorschau; Kick-off und Übergabe als Klappzeilen (offen, solange sie laufen); Knöpfe in den Schritten sind Nebenaktionen, die Hauptaktion im Kopf springt zum passenden Schritt | `test_offer_flow_browser`, `test_followup_browser`, `test_kickoff_browser`, `test_handover_browser`, `test_offer_basis_browser`, `test_addendum_browser`, `test_ui_angebote_browser` |
| Fassungen (`.of-history`) | unter den Arbeitsschritten | Reiter „Verlauf“, dazu eine Zeitleiste (erstellt, freigegeben, versendet, Nachfassen, Zusage/Absage, Projektstart, Übergabe, Abnahme, Nachrichtenentwürfe zu diesem Angebot) | `test_revision_browser`, `test_ui_angebote_browser` |
| Prüfpunkte der Freigabe | nur im Schritt „Versandfassung freigeben“ | zusätzlich rechts „Prüfung vor Freigabe“ (Prüfpunkte, Mindestverdienst, Zahl der Hinweise); nach der Freigabe Datum, Stand und nur noch Abweichungen | `test_ui_angebote_browser` |
| Ablauf | – | rechts „Ablauf“: Bedarf → Entwurf → Freigabe → Versand → Annahme, aktuelle Phase hervorgehoben, nach Annahme „Auftrag“ | `test_ui_angebote_browser` |
| Bestandskunden & Betreuung (`#crList`, `[data-cr-firm]`) | Abschnitt unter der Kalkulation | Angebote → Aufträge & Betreuung, Klappzeile (offen) | `test_care_browser` |
| Nachkalkulation mit Zeiterfassung (`#pkList`, `.pk-card`) | Abschnitt unter Bestandskunden | Angebote → Aufträge & Betreuung, Klappzeile „Nachkalkulation & Zeiterfassung“ (offen); darüber die Liste der angenommenen Aufträge mit Kick-off- und Abnahmestand | `test_postcalc_browser`, `test_service_times_browser`, `test_ui_angebote_browser` |
| Lehren der Nachkalkulation (`#pkLesson`, `#pkServiceLessons`) | im Abschnitt Nachkalkulation | Angebote → Auswertung, Klappzeile „Lehren der Nachkalkulation“ | `test_ui_angebote_browser` |
| Erlebnisstudien (`#stBox`), „Was du lernst“ (`#lnBox`) | Klappkarten auf der Angebotsseite | Angebote → Auswertung, Klappzeilen | `test_studies_browser`, `test_keep_input_browser`, `test_ui_angebote_browser` |
| Begriffe | „Interessent / Unternehmen“ im Formular, „Lead“ in einer Statusmeldung | „Firma“; interne Namen unverändert | – (Text) |

### Messwerte Einstellungen und Abrechnen (dev53)

Gemessen bei 1280 × 720 (Klassisch hell und Schiefer dunkel gleich), Abrechnen mit 4 fiktiven Rechnungen (Entwurf, überfällig, offen, bezahlt):

| Messung | dev52 | dev53 | Abnahme |
|---|---|---|---|
| Einstellungen: Oberkante des Inhalts | 377 px (erster Block „Darstellung“ unter Titel, Erklärtext und Sprungleiste) | 184 px (Abschnittsliste und Abschnitt) | ≤ 200 px |
| Einstellungen: Seitenlänge | 13.728 px (eine Seite) | je Abschnitt 1.026 px (Datenquellen) bis 2.847 px (Kalender & Postfach); Meine Firma 1.306 px | kein Abschnitt länger als nötig |
| Abrechnen: Oberkante der ersten Rechnungszeile | 436 px (erst nach Wechsel auf den inneren Reiter „Rechnungen“; Einstieg war die Übersicht) | 221 px (Einstieg) | ≤ 280 px |
| Abrechnen: Zeilenhöhe | 72 px (Tabelle) | 56 px | 56 px |
| Abrechnen: Hauptaktionen im Seitenkopf | – (kein Seitenkopf; „＋ Neue Rechnung“ grün in der Werkzeugleiste des Reiters) | genau eine („＋ Neue Rechnung“); geöffnete Rechnung: „Drucken / PDF ↗“ | genau eine |
| 390 × 844: erste Rechnungszeile | 646 px | 374 px | kein waagerechtes Scrollen |

Prüffall: `tests/e2e/test_ui_einstellungen_abrechnen_browser.py`.

## Was wohin zog (Schritt 5, dev53)

Keine Funktion entfiel. Server, Datenmodell und Buchhaltungsregeln (Festschreibung, Storno, E-Rechnung, Belege, Steuerexport) sind
unverändert; geändert wurden nur drei Hinweistexte des Servers, die „Einstellungen → Daten & Zugang“ nannten (jetzt „Sicherung & Zugang“).
Alle bisherigen Adressen gelten weiter: `#/einstellungen`, `#/einstellungen/ki-studio`, `#/einstellungen/hilfe`, `#/abrechnen` und jede
bisherige Sprungadresse `#/einstellungen?abschnitt=<Element-ID>` (z. B. `kalender`, `datenquellen`, `preise`, `targetProfile`, `ownTimes`,
`zugang`) – sie öffnet den Abschnitt, der das Element enthält, und scrollt dorthin, wenn es weiter unten steht. Neu sind die Abschnittsadressen
`#/einstellungen?abschnitt=firma|preise|zielkunden|darstellung|kalender|datenquellen|sicherung|ki-werkzeuge|hilfe` sowie
`#/abrechnen/ausgaben`, `#/abrechnen/auswertung` und `#/abrechnen/steuer`. `#/einstellungen` öffnet den zuletzt benutzten Abschnitt (in
diesem Browser gemerkt), sonst „Meine Firma“; schmal (bis 1000 px) die Abschnittsliste.

### Einstellungen: Zuordnung Block → Abschnitt

| Block | Bisher | Jetzt (Abschnitt) | Prüffall |
|---|---|---|---|
| Sprungleiste (`data-settings-jump`) | Knopfreihe über der langen Seite | Abschnittsliste links mit Kurzstand (`#esNav`, die Knöpfe tragen weiter `data-settings-jump`) | `test_ui_einstellungen_abrechnen_browser`, `test_catalog_browser` |
| Eyebrow, Titel „Einstellungen.“, Erklärtext | über der Seite | Seitenkopf „Einstellungen“ mit dem Abschnitt als Zusatz, Erklärtext als `title`; Werkzeugzeile mit „Einstellung suchen …“ | `test_ui_einstellungen_abrechnen_browser` |
| Reiter „Profil & Arbeitsweise · Erweiterte Werkzeuge: KI-Studio · Hilfe & Leitfaden“ | Kopfzeile | entfallen; KI-Studio und Playbook sind die Abschnitte „KI-Werkzeuge“ und „Hilfe & Playbook“ (eigene Ansichten mit derselben Liste) | `test_navigation_browser`, `test_ui_firmen_heute_browser` |
| Stammdaten für Rechnungen (`#accSettingsForm`) | Abrechnen → Stammdaten & Sicherung | **Meine Firma** (mit Hinweis, welche Pflichtangaben fehlen) | `test_ui_einstellungen_abrechnen_browser` |
| Kalkulationsgrundlagen (`#qbSettingsBox`, `#qbSettings`) | Gruppe „Leistungen & Preise“, eine offene Klappkarte mit Vorlagen und Katalog | **Leistungen & Preise**, Klappzeile „Kalkulationsgrundlagen“ (offen) | `test_navigation_browser`, `test_catalog_browser` |
| Vorlagen (`#qbVorlagen`), Leistungskatalog (`#qbCatalog`) | in derselben Klappkarte | **Leistungen & Preise**, Klappzeilen „Vorlagen“ und „Leistungskatalog“ (zu, mit Kurzstand) | `test_catalog_browser` |
| Dein Leistungsprofil (`#leistungsprofil`) | Gruppe „Arbeitsweise“ | **Leistungen & Preise** | `test_service_profile_browser` |
| Dein Zielkundenprofil (`#targetProfile`, Passungsstatistik) | Gruppe „Zielkunden“ | **Zielkunden** | `test_ui_einstellungen_abrechnen_browser` |
| Gewichte & Fristen (`#gewichte`) | Gruppe „Recherche“ | **Zielkunden** | `test_v2_navigation` |
| Theme, Hell/Dunkel, Dichte (`#darstellung`) | Gruppe „Darstellung“ | **Darstellung** | `test_appearance_browser`, `test_ui_firmen_heute_browser` |
| Kalender-Abo, CalDAV, IMAP (`#kalender`) | Gruppe „Arbeitsweise“ | **Kalender & Postfach** | `test_calendar_browser`, `test_caldav_browser`, `test_imap_browser` |
| Deine Zeiten (`#ownTimes`) | Gruppe „Arbeitsweise“ | **Kalender & Postfach** | `test_reach_browser` |
| OpenStreetMap, GLEIF-Katalog, Quellen prüfen (`#datenquellen`) | Gruppe „Datenquellen“ | **Datenquellen** | `test_osm_local_browser`, `test_ui_finden_browser` |
| Website-Abruf & Auswertung (`#rtPanel`) | Gruppe „Recherche“ | **Datenquellen** | `test_ui_einstellungen_abrechnen_browser` |
| Zugang, Rollen, Sicherung, Wiederherstellen (`#zugang`) | Gruppe „Daten & Zugang“ | **Sicherung & Zugang** | `test_ui_workday` |
| Offline-Modus, Impressum automatisch lesen (`#offline`) | Gruppe „Daten & Zugang“ | **Sicherung & Zugang** | `test_ui_workday` |
| Backup der Buchhaltung (`#accBackup`, `#accBackupInfo`, Hinweis zur Aufbewahrung) | Abrechnen → Stammdaten & Sicherung | **Sicherung & Zugang**, Karte „Backup für die Aufbewahrung“ | `test_ui_einstellungen_abrechnen_browser` |
| KI-Studio (Analyse-Labor, Website eines Leads untersuchen, Analyseverlauf) | Reiter „Erweiterte Werkzeuge: KI-Studio“ | **KI-Werkzeuge** (`#/einstellungen/ki-studio`) | `test_navigation_browser` |
| Sales-Playbook | Reiter „Hilfe & Leitfaden“, „? Hilfe“ in der Seitenleiste | **Hilfe & Playbook** (`#/einstellungen/hilfe`), „? Hilfe“ unverändert | `test_catalog_browser`, `test_navigation_browser` |

### Abrechnen

| Funktion | Bisher | Jetzt | Prüffall |
|---|---|---|---|
| Reiter des Bereichs | keiner (eine Ansicht mit fünf inneren Reitern Übersicht · Rechnungen · Ausgaben & E-Rechnungen · Auswertung & Export · Stammdaten & Sicherung) | vier Reiter in der Kopfzeile: Rechnungen · Ausgaben · Auswertung · Steuer & Export | `test_ui_einstellungen_abrechnen_browser`, `test_ui_firmen_heute_browser` |
| Einstieg | innerer Reiter „Übersicht“ | „Rechnungen“ (`#/abrechnen`) | `test_ui_einstellungen_abrechnen_browser` |
| Titel „Vom Auftrag zum Zahlungseingang.“, Erklärtext, „Kein Versand · keine ELSTER-Übermittlung“ | über den Reitern | Seitenkopf „Abrechnen“ mit Anzahl; Erklärtext als `title`, Hinweis unter der Liste | – (Text) |
| Rechnungstabelle (Nummer · Kunde · Datum/fällig · Brutto · Offen · Status) | innerer Reiter „Rechnungen“ | Liste Rechnung (Nummer, Firma · Art vom Datum) · Nächster Schritt · Fällig · Status · Betrag brutto (bei Teilzahlung „offen …“) · ›; Klick oder Enter öffnet | `test_ui_einstellungen_abrechnen_browser` |
| Status-Auswahl | Auswahlliste neben „＋ Neue Rechnung“ | Ansichten Alle · Offen · Überfällig · Bezahlt · Entwürfe (mit Anzahl); alle Status unter „Filter ▾“ (dazu „Filter zurücksetzen“, „Aktualisieren ↻“); Suche nach Nummer oder Firma | `test_ui_einstellungen_abrechnen_browser` |
| „＋ Neue Rechnung“ | grüner Knopf über der Tabelle | Hauptaktion im Seitenkopf | `test_ui_einstellungen_abrechnen_browser` |
| Rechnungseditor (`#accEditor`, `#accInvoiceForm`) | unter der Tabelle, „Schließen ✕“ | eigene Ansicht mit „← Rechnungen“ (gleiche Kennung `#accEditorClose`), Formular in einer Karte; Festschreiben, Vorschau, Entwurf löschen unverändert | `test_ui_einstellungen_abrechnen_browser` |
| Geöffnete Rechnung (`#accDetail`) | unter der Tabelle, „Schließen ✕“ | eigene Ansicht: „← Rechnungen“, Nummer, Status, Firma · Art; Hauptaktion „Drucken / PDF ↗“; E-Rechnung, Kopieren, Stornieren, Zahlungen (jetzt Nebenaktion „Zahlung erfassen“), Mahnwesen unverändert | `test_ui_einstellungen_abrechnen_browser` |
| Warnungen (Stammdaten unvollständig, Kleinunternehmer-Grenzen, `#accWarnings`) | Reiter „Übersicht“ oben | Rechnungen, Klappzeile „Stammdaten“ mit Kurzstand und „Stammdaten ergänzen“ (→ Einstellungen → Meine Firma); nur sichtbar, wenn es eine Warnung gibt | `test_ui_einstellungen_abrechnen_browser` |
| Angenommen, noch nicht berechnet (`#accUnbilled`) | Reiter „Übersicht“ | Rechnungen, Klappzeile „Aus Angeboten berechnen“ | – (Inhalt unverändert) |
| Kennzahlen, Überfällige Rechnungen, 12 Monate | Reiter „Übersicht“ | Reiter „Auswertung“ | `test_ui_einstellungen_abrechnen_browser` |
| Vertriebskennzahlen (`#accSalesKpis`) | Reiter „Auswertung & Export“ | Reiter „Auswertung“ (Zeitraum wie unter Steuer & Export) | – |
| Zeitraum, USt-Voranmeldung, EÜR, CSV-Exporte, Änderungsprotokoll | Reiter „Auswertung & Export“ | Reiter „Steuer & Export“ | `test_ui_einstellungen_abrechnen_browser` |
| Ausgabe buchen, E-Rechnung einlesen, erfasste Ausgaben | Reiter „Ausgaben & E-Rechnungen“ | Reiter „Ausgaben“ | `test_ui_einstellungen_abrechnen_browser` |
| Stammdaten, Backup | Reiter „Stammdaten & Sicherung“ | Einstellungen → Meine Firma bzw. Sicherung & Zugang | `test_ui_einstellungen_abrechnen_browser` |
| Rechnung aus der Suche (Strg+K) | wechselte nur zu Abrechnen („in der Rechnungsliste öffnen“) | öffnet die Rechnung direkt | – |
| Begriffe | „Lead / Kunde“, „– ohne Lead –“, „Leads gewonnen / verloren“, „Zahlungen mit Lead-Zuordnung“ | „Firma / Kunde“, „– ohne Firma –“, „Firmen gewonnen / verloren“, „Firmen-Zuordnung“; interne Namen unverändert | – (Text) |

