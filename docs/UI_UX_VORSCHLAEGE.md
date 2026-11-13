# UI/UX – Vorschläge für mehr Übersicht

Stand 2.0.0-dev15. Grundlage: Screenshots aller Hauptansichten in allen Themes und eine Messung im Browser bei 1366 × 768 Pixeln
(häufigste Laptop-Auflösung) mit zwölf fiktiven Leads. Alle Vorschläge bauen auf den Farbrollen aus dev11 auf und funktionieren
damit ohne Zusatzaufwand in jedem Theme, hell wie dunkel.

## Was gemessen wurde

| Befund | Normal | Kompakt (dev11) |
|---|---|---|
| Seitenkopf bis zum ersten Inhalt („Heute“, „Leads“, „Pipeline“) | 233–255 px, also ein Drittel des Bildschirms | 158–162 px |
| Seitenkopf „Firmen finden“ | 329 px | 210 px |
| Lead-Zeilen ohne Scrollen sichtbar | 5 | 8 |
| Länge des Lead-Dialogs | rund 7.800 px, etwa zehn Bildschirmhöhen | unverändert |
| Einträge in der Navigation | 10 sichtbar, 6 unter „Erweitert“; die Einstellungen liegen unter „Erweitert → Datenqualität & System“ | – |

## Umgesetzt in dev11

**V1 – Themes, Hell/Dunkel, Dichte (umgesetzt).** Unter *Einstellungen → Darstellung* (bis dev13: *Erweitert → Datenqualität & System*) gibt es vier Themes:
Klassisch (bisheriger Stand), Schiefer (kühles Grau, blauer Akzent), Sand (warme Erdtöne) und Kontrast (kräftige Linien, AAA-Kontrast).
Jedes gibt es hell und dunkel; „Wie System“ folgt dem Betriebssystem. Die Dichte „Kompakt“ blendet die Erklärtexte unter den
Überschriften aus und verringert Abstände. Oben rechts schaltet ein Knopf zwischen Hell und Dunkel um.
Technisch: Alle 284 festen Farbwerte im Stylesheet sind in 42 Rollen zusammengefasst. Ein Test verhindert neue feste Farben
und prüft für jedes Theme in Hell und Dunkel 24 Farbpaare gegen die WCAG-Kontrastwerte.

## Vorschläge zur Auswahl

Aufwand: S = bis ein halber Tag, M = ein bis zwei Tage, L = mehrere Tage. Alle Vorschläge ändern nur die Oberfläche, nicht die Daten.

| Nr. | Vorschlag | Problem heute | Aufwand | Nutzen |
|---|---|---|---|---|
| V2 | ✓ **umgesetzt in dev12:** **Firmenakte mit Reitern** – Überblick · Kontakt & Erreichbarkeit · Bewertung · Verlauf · Stammdaten; Kopf mit Name, Phase, Passung und den zwei wichtigsten Knöpfen bleibt beim Scrollen stehen | Der Lead-Dialog ist zehn Bildschirme lang; die nächste Aktion verschwindet beim Scrollen | M | sehr hoch – die meistgenutzte Ansicht |
| V3 | ✓ **umgesetzt in dev14:** **Eigener Bereich „Einstellungen“** unten in der Navigation: Darstellung, Leistungsprofil, Zielkundenprofil, eigene Erreichbarkeit, Gewichte & Fristen, Sicherheit an einem Ort. „Datenqualität“ bleibt reine Arbeitsansicht | Einstellungen liegen verstreut in fünf Ansichten, die Darstellung unter „Erweitert“ | S–M | hoch – man findet Einstellungen dort, wo man sie sucht |
| V4 | ✓ **umgesetzt in dev14** (Teil 1, mit direkten Adressen): **Navigation auf sechs Bereiche:** Heute · Finden · Firmen (Leads, Berichte, Pipeline als Umschalter) · Angebote · Abrechnen · Einstellungen. Die Detailseiten (URL-Recherche, Scoring, Signale) werden Reiter in „Firmen-Berichte“ | 16 Einträge, davon drei Gruppen mit nur einem oder zwei Einträgen | M | hoch – schon in der Roadmap; V3 ist der erste Schritt |
| V5 | ✓ **umgesetzt in dev15:** **Lead-Liste mit Filterchips und gespeicherten Ansichten:** Passung A/B/C, Erreichbarkeit, „ohne Rechtsform“, „Frist läuft ab“, „heute fällig“ als Chips; Spalten ein- und ausblendbar | Die Spalten „Kaufsignal“ und „Angebot“ zeigen bei den meisten Firmen denselben Platzhalter; filtern geht nur nach Phase | M | mittel bis hoch |
| V6 | ✓ **umgesetzt in dev12:** **Einheitliche Statusmarken:** eine Komponente für Passung, Phase, Frist und Datenquelle mit festen Rollenfarben (Erfolg, Hinweis, Warnung, Fehler, Info) und Symbol, damit Farbe nie allein trägt | Heute elf verschiedene Klassen für „Pill“, „Badge“ und „Chip“ | S | mittel – ruhigeres Bild, besser für Farbsehschwäche |
| V7 | ✓ **umgesetzt in dev15:** **Heute als Fokusliste:** oben nur die drei nächsten Schritte mit je einem Knopf; Eingang, Auslastung und Tagesplan klappen darunter auf und merken sich ihren Zustand | Die Heute-Seite ist 2.800 px lang | S–M | mittel |
| V8 | **Schnellsuche mit Strg+K:** Firma, Ansicht oder Aktion tippen und mit Enter hin | Firma öffnen heißt heute: Leads → suchen → Zeile anklicken | M | hoch für Tastaturnutzer |
| V9 | ✓ **umgesetzt in dev15:** **Leere Zustände mit einem nächsten Schritt:** statt „Noch keine Recherche-Aufträge“ ein Knopf zur passenden Stelle | Viele Kästen sind beim Start leer und erklären nur | S | mittel – vor allem für den Einstieg |

## Umgesetzt in dev12

**V2 – Firmenakte mit Reitern.** Fünf Reiter: Überblick (Akte, Bewertung, Erreichbarkeit, Zeitleiste), Kontakt & Verlauf
(Aktivitätsprotokoll zuerst, dann Gesprächsvorbereitung, Entscheider, Rollen), Bedarf & Angebot (Bedarfsanalyse, Pakete,
vorgeschlagene Aufgaben), Recherche (Firmen-Bericht, Firmendaten, Website-Bewertung, Kaufsignale, Website-Analyse) und Stammdaten.
Der Kopf mit Name, Phase, Passung, Belegabdeckung, nächster Aktion und den Reitern steht beim Scrollen. Gemessen bei 1366 × 768
mit einer Beispielfirma: Überblick 1.756 px, Kontakt 2.322 px, Bedarf 1.577 px, Recherche 1.541 px, Stammdaten 1.494 px –
vorher ein Dialog mit rund 7.800 px.

**V6 – Einheitliche Statusmarken.** `.pill`, `.sw-web` und `.as-grade` teilen fünf Tonstufen mit Symbol: erledigt ✓, Hinweis !,
Problem ✕, offen ○, neutral –. „off“ heißt jetzt nur noch neutral; Probleme (passt nicht, gesperrt, fehlgeschlagen, überzogen,
voll ausgelastet) heißen überall „bad“. Filter- und Zählerchips sind bewusst noch nicht angeglichen.

## Empfehlung

Stand dev13, abgeglichen mit dem externen Produktreview vom 13.11.2026: V2 und V6 sind umgesetzt (dev12), dazu Eingabeschutz,
Öffnungsfokus und eine einheitliche Passungsanzeige (dev13, Review-Maßnahmen M01, M03, M04). V3 und V4 folgten in dev14 (Review M06/M07, mit direkten Adressen je Ansicht und Firma). V5, V7 und V9 folgten in dev15 (Review M09, M08, M11). Offen bleibt V8 (Strg+K), sobald der Bestand wächst.
V8 (Strg+K) folgt, wenn der Bestand wächst. Den Status je Maßnahme führt `ROADMAP.md`.

## Bekannte Grenzen von V1

- „Klassisch“ ist nicht pixelgleich mit dem Stand vor dev11. 284 Farbtöne wurden zu 42 Rollen zusammengefasst; die Markenfarben
  (Petrol, Mint, Grün, Creme, Schrift) sind unverändert. Leicht verschoben sind vor allem Grautöne und Linien. Graue Nebentexte sind
  bewusst dunkler geworden, damit sie den WCAG-AA-Kontrast erreichen.
- Durchscheinende Schatten und Flächen (`rgba(…)`, 48 Stellen) sind nicht in Rollen überführt. Sie sind im Dunkelmodus kaum sichtbar,
  stören aber nicht.
- Die Darstellung gilt für die ganze Installation. Im Team-Betrieb wählen alle Nutzer dasselbe Theme; eine Wahl je Nutzer wäre ein
  eigener Schritt.
- Ausdrucke von Rechnungen und Angeboten bleiben immer hell (eigenes Stylesheet).
