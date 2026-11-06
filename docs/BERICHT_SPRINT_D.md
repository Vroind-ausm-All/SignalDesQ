# Sprint-Bericht D – Angebote & Preise (v1.12)

Gemäß `docs/MASTERPLAN_V3.md`, Sprint D.

Ausgangspunkt war das Feedback: „Angebote & Preise sollen nachvollziehbar sein und wesentlich mehr Auswahl an Dienstleistungsspektrum bekommen.“

Angaben des Nutzers:
- **Leistungen:** handgestaltete Kunst, Texte, Webdesign, Grafikdesign, Print und Web, Logo, Individualsoftware, Shop-Anbindung, eigener Webshop, Fotografie und Videografie, Werbung, SEO und GEO, KI-Chatbot, Telefon-Sprachbot, Website-Analyse.
- **Kalkulation:** mindestens 66 €/h bei über 13 Jahren Erfahrung, teils Festpreise, dazu Anreise und Tagespauschale.

## Was ist tatsächlich implementiert?

### Leistungskatalog (`pricing.py`) – 26 Leistungen in 8 Bereichen
Alle genannten Leistungen sind enthalten, meist in drei Größen (**Basis / Standard / Umfangreich**) mit konkretem Umfang, Liefergegenständen, Ausschlüssen, Abnahmekriterien und möglichen Kosten Dritter. Hinzu kommen Mengenleistungen (je Text, Artikel, Produktfoto, Anbindung), monatliche Leistungen (Betreuung, SEO, Kampagnen, Bot-Betrieb) sowie Tagespauschale, Anreise und „nach Aufwand“.

**Startpreise** bei 66 €/h und 10 % Puffer, aufgerundet auf volle 10 €:

| Bereich | Leistung | Basis | Standard | Umfangreich |
|---|---|---|---|---|
| Analyse & Beratung | Webseiten-Analyse & Handlungsbedarf | 220 € (3 h) | 590 € (8 h) | 1.170 € (16 h) |
| Analyse & Beratung | Strategie- & Konzept-Workshop | 440 € (6 h) | 800 € (11 h) | 1.530 € (21 h) |
| Design & Marke | Logogestaltung | 880 € (12 h) | 1.600 € (22 h) | 2.620 € (36 h) |
| Design & Marke | Grafikdesign | 440 € (6 h) | 1.020 € (14 h) | 2.040 € (28 h) |
| Design & Marke | Printdesign & Druckabwicklung | 740 € (8 h) | 1.860 € (20 h) | 4.170 € (45 h) |
| Design & Marke | Handgestaltete Kunst (Auftragsarbeit) | 790 € (10 h) | 1.900 € (24 h) | 3.890 € (48 h) |
| Text | Website- & Werbetexte | je Seite/Text: 220 € (3 h) | | |
| Text | Fachartikel / Blogbeitrag | je Artikel: 370 € (5 h) | | |
| Web & Shop | Webdesign & Website-Umsetzung | 1.750 € (24 h) | 4.360 € (60 h) | 7.990 € (110 h) |
| Web & Shop | Aufbau eines eigenen Webshops | 3.630 € (50 h) | 7.260 € (100 h) | 12.350 € (170 h) |
| Web & Shop | Shop- & Marktplatz-Anbindung | je Anbindung: 1.170 € (16 h) | | |
| Web & Shop | Website-/Shop-Betreuung (monatlich) | 150 € / Monat (2 h) | 370 € / Monat (5 h) | 730 € / Monat (10 h) |
| Sichtbarkeit | SEO- & GEO-Optimierung | 730 € (10 h) | 1.750 € (24 h) | 3.270 € (45 h) |
| Sichtbarkeit | SEO- & GEO-Betreuung (monatlich) | 300 € / Monat (4 h) | 590 € / Monat (8 h) | 1.020 € / Monat (14 h) |
| Sichtbarkeit | Werbekampagnen – Einrichtung | 590 € (8 h) | 1.170 € (16 h) | 1.890 € (26 h) |
| Sichtbarkeit | Kampagnenbetreuung (monatlich) | 220 € / Monat (3 h) | 440 € / Monat (6 h) | 730 € / Monat (10 h) |
| Foto & Video | Professionelle Fotografie | 510 € (7 h) | 1.020 € (14 h) | 2.040 € (28 h) |
| Foto & Video | Produktfotos (freigestellt) | je Produkt: 30 € (0,4 h) · ab 5 | | |
| Foto & Video | Videografie | 780 € (10 h) | 2.430 € (32 h) | 4.510 € (60 h) |
| Software & KI | Individualsoftware für den Arbeitsalltag | 1.750 € (24 h) | 5.810 € (80 h) | 13.070 € (180 h) |
| Software & KI | KI-Chatbot-Integration | 1.020 € (14 h) | 2.180 € (30 h) | 4.000 € (55 h) |
| Software & KI | Telefon-Sprachbot-Integration | 1.460 € (20 h) | 2.910 € (40 h) | 5.090 € (70 h) |
| Software & KI | Betrieb & Optimierung Chat-/Sprachbot (monatlich) | 80 € / Monat (1 h) | 220 € / Monat (3 h) | 440 € / Monat (6 h) |
| Vor Ort & Aufwand | Tagespauschale vor Ort | 528 € pro Tag, 290 € pro Halbtag | | |
| Vor Ort & Aufwand | Anreise | 2 × km × 0,50 € + 50 % der Fahrzeit × 66 €/h | | |
| Vor Ort & Aufwand | Leistung nach Aufwand | Stunden × 66 €/h, nicht aufgerundet | | |

> Die Stundenwerte sind **Startwerte (Schätzungen)**. Unter „04 · Kalkulationsgrundlagen & Leistungskatalog“ lässt sich je Leistung und Umfang Folgendes anpassen: Aufwand, enthaltene Fremdkosten (z. B. Material, Druck) oder ein **fester Preis**. Ein Klick stellt den Startwert wieder her.

### Nachvollziehbare Festpreise
- **Formel je Position:** Aufwand × Stundensatz + Puffer + enthaltene Fremdkosten = Festpreis, aufgerundet. Bei festem Preis steht „fester Preis“ dabei.
- **Interne Herleitung** („03 · So setzt sich der Preis zusammen“): je Position Aufwand, Satz, Puffer, Fremdkosten, Festpreis und **effektiver Stundenlohn**, dazu die Summen.
  - Liegt eine Position unter dem **Mindestverdienst (Standard 66 €/h)**, erscheint eine Warnung mit Wert. Beispiel: Logo Standard zum Festpreis von 990 € ergibt 45,00 €/h.
  - Gesperrt wird nichts; die Entscheidung bleibt bei dir.
- **Kalkulationsgrundlagen** (einstellbar und protokolliert):
  - Stundensatz und Mindestverdienst je 66 €/h, Puffer 10 %;
  - Tagespauschale 528 € (8 h), Halbtag 290 €;
  - Fahrtkosten 0,50 €/km, Fahrzeit zu 50 % berechnet;
  - Rundung auf 10 €, Erfahrung 13 Jahre.
- **Anreise und Tagespauschale** sind eigene Positionen.
  - Anreise: km einfach, Minuten einfach und Anzahl Fahrten, z. B. 35 km und 40 Min. ergeben 79 €.
  - Tagespauschale in halben Tagen, z. B. 1,5 Tage ergeben 818 €.
- **„Nach Aufwand“:** exakt Stunden × Satz, ohne Puffer und ohne Aufrundung.

### Angebots-Baukasten (Angebote & Preise)
- **Zusammenstellen:**
  - Leistung, Umfang bzw. Menge wählen und hinzufügen; Schnellknöpfe für Anreise, Tagespauschale und nach Aufwand.
  - Positionen umbenennen, Umfang oder Menge ändern, sortieren und entfernen. Der Preis rechnet sich sofort neu.
- **Vorlagen:** Die sechs bisherigen Pakete sind jetzt Vorlagen aus Positionen, z. B. „B2B Website- & Conversion-Sprint“ = Webdesign Standard + 4 Texte + SEO/GEO Basis.
  - Beim Wählen der Firma lädt die zum Lead passende Vorlage automatisch.
  - „Angebot vorbereiten“ aus Bericht, Dossier oder Angebots-Matching übernimmt die Vorlage der empfohlenen Lösung.
  - Beim Firmenwechsel werden die alten Positionen nicht mitgenommen.
- **Kundenvorschau und Kundendokument (Markdown):**
  - **Positionstabelle mit Festpreisen**; einmalige und monatliche Summen getrennt, jeweils netto und brutto;
  - was enthalten ist, Liefergegenstände, Nicht enthalten, Abnahmekriterien;
  - **mögliche Kosten Dritter, ausdrücklich „nicht im Festpreis“**, z. B. Hosting, Werbebudget, KI- und Telefonminuten.
  - **Keine Stunden, kein Stundensatz, kein Puffer im Kundendokument** (per Test geprüft).
- **Rechnung:**
  - Aus einem angenommenen Baukasten-Angebot wird **je Position eine eigene Rechnungszeile**.
  - Bei gemischten Angeboten erzeugt „Schluss-/Gesamtrechnung“ die einmaligen Positionen und „**Monatsrechnung**“ die laufenden. Die Abschlagsrechnung bezieht sich auf die einmalige Summe.
- **Gespeicherte Angebote** aus dem alten Paket-Rechner werden unverändert angezeigt und abgerechnet.

**Technik:**
- Neue Dateien `pricing.py` und `public/quotes.js`.
- **Endpunkte:** `GET /api/pricing/catalog`, `POST /api/pricing/preview`, `PUT /api/pricing/settings`, `PUT /api/pricing/overrides`, `GET /api/pricing/templates/{key}`.
- `POST /api/workspace/proposals` nimmt jetzt auch `positions` an.
- Einstellungen und eigene Katalogwerte liegen in `app_settings`; das Schema ist unverändert (19).

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **257 Tests grün**, davon 10 neu in `tests/test_sprintD_pricing.py`.
- **Katalog:** alle genannten Leistungen vorhanden; jede Größe erreicht mit den Startwerten mindestens 66 €/h; auf 10 € gerundet.
- **Formeln nachgerechnet:**
  - Logo Standard: 22 h × 66 € + 10 % = 1.600 €
  - 4 Texte = 880 €
  - Kunstwerk mit Material = 1.900 €
  - Anreise = 79 €, 1,5 Tage = 818 €, Aufwand 3 h = 198 €
- **Prüfungen:** Validierung, Einstellungen (Stundensatz 80 € → Logo 1.940 €), eigene Werte, fester Preis mit Mindestverdienst-Warnung, Zurücksetzen.
- **Angebot:** gemischtes Angebot mit Summen und USt.; Kosten Dritter ausgewiesen; **keine internen Werte im Kundendokument**; alte Paket-Angebote unverändert; alle Vorlagen; Angebotsentwurf aus dem Matching mit Positionen.
- **Rechnung:** Zeilen je Position, Monatsrechnung, Abschlag auf die einmalige Summe, Fehler bei Monatsrechnung ohne Monatsposition.
- **HTTP:** alle neuen Endpunkte inklusive Fehlerfälle.
- **Klickdurchlauf im Browser** (Chromium, fiktive Daten), ohne Konsolenfehler:
  - Vorlage lädt beim Wählen der Firma; Positionen ergänzen (Logo, Anreise mit 35 km und 40 Min., Tagespauschale, Betreuung)
  - Kundenvorschau und interne Herleitung; fester Preis 990 € → Warnung, danach zurückgesetzt; Stundensatz 70 €
  - Speichern → angenommen → Knöpfe Abschlag, Schluss- und **Monatsrechnung**
  - „Angebot vorbereiten“ aus der Recherche lädt die Vorlage „Automatisierung“; Mobilansicht 390 px

## Was ist noch ungetestet?

- **Ob die Startwerte zu deiner Arbeitsweise passen.** Sie sind Schätzungen für eine erfahrene Einzelagentur. Bitte die häufigsten Leistungen einmal durchgehen und anpassen; jede Änderung wird protokolliert.
- **Das Zusammenspiel mit einer echten Steuerberatung beim Rechnungsexport (DATEV).** Das ist unverändert seit Version 1.0.

## Welche Grenzen bestehen?

- Der Mindestverdienst bezieht sich auf die **geplanten** Stunden. Ob er tatsächlich erreicht wird, zeigt erst eine Nachkalkulation mit Ist-Zeiten (in der Roadmap vorgemerkt).
- Rabatte und Express-Zuschläge gibt es bewusst nicht als versteckte Prozentsätze. Sie lassen sich bei Bedarf über einen festen Preis oder eine eigene Position „nach Aufwand“ abbilden.
- Fremdkosten im Festpreis (Material, Druck) sind Schätzwerte. Bei abweichender Auflage oder abweichendem Material steht im Angebot der Hinweis auf ein Angebot der Druckerei, ohne Aufschlag.

## Was ist als Nächstes sinnvoll?

1. **Katalog an deine Erfahrung anpassen:** für die 5–10 häufigsten Leistungen Aufwand oder feste Preise eintragen.
2. **Live-Durchlauf über die ganze Kette** mit echten Firmen: Firmen finden → Bericht → Kontakt → Termin → Bedarfsanalyse → Angebot → Rechnung.
3. **Danach sinnvoll:** eine Nachkalkulation, die die Ist-Zeit je Angebot erfasst und mit der Planung vergleicht.
