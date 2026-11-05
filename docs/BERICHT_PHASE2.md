# Sprint-Bericht Phase 2 – Website-Bedarfs-Scorer v2 (v1.4)

Gemäß Masterplan v2 und Master-Prompt v2.0, Modul 3 / Sprint 2.

## Was ist tatsächlich implementiert?

| Baustein | Umsetzung |
|---|---|
| **Gerenderte Erfassung** | Chromium über Playwright: Startseite auf dem Desktop (1366 × 900) und als Smartphone (390 × 844, Touch, mobiler User-Agent), dazu bis zu drei Unterseiten (Leistungen, Produkte, Kontakt, Karriere). Gespeichert werden JPEG-Screenshots je Ansicht, die Ladezeit (Navigation Timing), die übertragene Datenmenge und Anzahl der Anfragen sowie Konsolenfehler. Aus dem DOM erfasst werden Überschriften, Navigation, Formulare, Telefon- und E-Mail-Links, Handlungsaufrufe (CTAs) im ersten Bildschirm, Alt-Texte, Schriftfamilien, kleine Schrift, kleine Touch-Ziele, Layout- und Gerätebreite, Copyright-Jahr, Login-/Portal-Links und PDF-Links. |
| **Linkprüfung** | Bis zu 25 interne Links derselben Domain, per HEAD und notfalls GET. robots.txt wird beachtet, Weiterleitungen werden sicher geprüft, zwischen den Abrufen liegt eine Pause. |
| **Sicherheit** | Die Start-URL wird wie bisher geprüft: nur öffentliche Adressen, robots.txt. Zusätzlich blockiert der Browser jede Anfrage – auch für Unterressourcen – an lokale oder private Adressen, mit DNS-Prüfung. Es gibt keine Hauptnavigation auf fremde Domains und keine Downloads. Medien und Websockets werden blockiert. Es wird nichts geklickt und nichts abgeschickt. |
| **Rückfall ohne Browser** | Nur die HTML-Struktur wird erfasst. Design-, Smartphone- und Ladezeit-Rubriken bleiben „unbekannt“. So verlangt es das Masterprompt: Reiner HTML-Text reicht für gestalterische Bewertungen nicht aus. |
| **21 Rubriken** | **A Design & UX (7):** responsive Smartphone-Darstellung (seitliches Scrollen *oder* verkleinertes Desktop-Layout), Lesbarkeit, Überschriften-Hierarchie, Alt-Texte, Touch-Ziele, Schriftkonsistenz, Aktualität. **B Web & Conversion (9):** Ladezeit, Datenmenge, Handlungsaufruf im ersten Bildschirm, Kontaktwege, Formularaufwand, defekte Links, Navigation, Leistungsseiten, technische Grundlagen. **C Prozess & App (5, als Hypothesen gekennzeichnet):** PDF-Formulare, manuelle Anfrageschritte, fehlender Self-Service, aufwendige Formulare, Ausfüllvorlagen. **D Kampagnen** ist inaktiv, weil der Leistungskatalog kein passendes Paket enthält. |
| **Befunde** | Jede Rubrik liefert „auffällig“, „ok“ oder „unbekannt“. Dazu gehören Messwert bzw. Beleg, Fundstelle, ein zugeordneter Screenshot, das Verfahren (Messung/DOM/Heuristik) und die Sicherheit (gemessen/beobachtet/Hypothese). Befunde lassen sich einzeln als bestätigt oder verworfen markieren. |
| **Scores** | Teil-Scores für Design, Web und Prozess sind der Anteil der auffälligen an den bewertbaren Rubrikgewichten. Bei zu geringer Abdeckung bleibt der Teil-Score leer. Getrennt ausgewiesen werden außerdem: Potenzial (gewichtetes Mittel der Bereiche), Passung (Branche, Größe, Leistungsbezug), Projektanlass (Alter des dokumentierten Anlasses; ohne Anlass „unbekannt“) und Belegabdeckung. Der **Gesamtwert** ist das konfigurierbare Mittel 35/35/30 und wird nur ab 60 % Belegabdeckung berechnet, sonst „Datenlage unzureichend“. Fehlt der Anlass, wird das ausdrücklich vermerkt. |
| **Ergebnis je Firma** | Priorisierte Beobachtungen mit Fundstellen, Screenshots, Unsicherheiten, passende Pakete aus dem tatsächlichen Leistungskatalog (unverbindlich), 3–5 Bedarfsfragen, empfohlener nächster Schritt (berücksichtigt den Rechtsstatus), Hinweis „keine Aussage über Kaufbereitschaft, Budget oder Werbeeinwilligung“. |
| **Vergleichbarkeit** | Jede Konfiguration aus Rubriken, Gewichten und Schwellen ist eine eigene Bewertungsversion (`score_versions`, Hash). Neue Ergebnisse werden mit dem vorherigen verglichen: bei gleicher Version mit Veränderungswert, sonst mit dem Hinweis „nicht direkt vergleichbar“. |
| **Auftragslauf** | Bis zu 20 Leads nacheinander im Hintergrund. Gesperrte Leads, Leads ohne Website und bereits laufende Bewertungen werden übersprungen. Ein Neustart markiert unterbrochene Bewertungen als fehlgeschlagen. |
| **Datenmodell** | `website_audits`, `website_findings`, `website_scores`, `score_versions`, `website_screenshots`. Screenshots liegen neben der Datenbank im Ordner `screenshots`; der Dateizugriff ist gegen Pfadmanipulation geschützt. Vor der Migration wird automatisch ein Backup angelegt (Schema 14). |
| **Oberfläche** | Neuer Bereich „Website-Scoring“: Lead-Auswahl, Warteschlange, Priorisierungstabelle, Detailansicht, Raster- und Gewichtungseditor. Im Lead-Dialog gibt es die „Website-Bewertung“ mit allen Kacheln, Belegen und Screenshots. |

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **149 Tests grün**, davon 11 neu in `tests/test_phase2_scoring.py`. Ohne Playwright werden 2 Browser-Tests übersprungen; mit Playwright und Chromium laufen alle 149.
- **Echter Browser-Test:** Chromium rendert zwei fiktive Testwebsites, die über einen lokalen HTTP-Server bereitgestellt werden, eine gute und eine schwache. Geprüft werden Screenshots (JPEG), Ladezeit > 0, CTA-Erkennung, responsive Darstellung, das verkleinerte Desktop-Layout ohne Viewport-Angabe, die Erkennung des defekten Links sowie PDF- und Fax-Hinweise. Außerdem muss das Potenzial der schwachen Seite deutlich über dem der guten liegen. Dieser Test hat einen echten Regelfehler aufgedeckt: Smartphones verkleinern Seiten ohne Viewport-Angabe, statt seitlich zu scrollen. Der Fehler ist behoben.
- **Logiktests mit festen Erfassungsdaten:**
  - Reproduzierbarkeit (identische Eingabe ergibt identisches Ergebnis)
  - Erfassung nur per HTML ergibt „Datenlage unzureichend“
  - Gewichte, Versionen und Validierung des Rasters
  - Anlass und Passung, Fragen, Pakete und Hinweistext
  - keine Kaufbereitschafts-Formulierungen, Bereich D inaktiv
  - Warteschlange mit gesperrten Leads und Leads ohne Website
  - Vergleichbarkeit über Versionen
  - Fehlschlag und Neustart
  - Schutz des Screenshot-Pfads
- **Klickdurchlauf in der App** mit echtem Chromium gegen die lokalen Testseiten: Bewertung starten, Warteschlange, Ranking, Details, Lead-Dialog, neue Gewichtungsversion, Screenshot-Abruf (image/jpeg), Mobilansicht 390 px. Keine Konsolenfehler, kein horizontaler Überlauf.

## Was funktioniert?

Alles oben Genannte, inklusive echtem Rendering, Screenshots und Messungen gegen lokal bereitgestellte Seiten.

## Was ist noch ungetestet?

- **Öffentliche Websites:** Die Cloud-Umgebung erreicht keine beliebigen Internetseiten. Das ist **kein Live-Test** realer Firmenwebsites. Bitte lokal 5–10 Leads mit echten Websites bewerten und auffällige Fehleinschätzungen melden.
- Seiten mit Cookie-Bannern, die den ersten Bildschirm verdecken: Der Handlungsaufruf kann dahinter liegen. Ein Banner wird bewusst nicht weggeklickt.
- Sehr langsame Server und Seiten, die erst nach Nutzerinteraktion Inhalte laden.

## Welche technischen oder rechtlichen Grenzen bestehen?

- Die Ladezeit ist eine einmalige Messung vom eigenen Rechner ohne Cache, also ein Richtwert und kein Lighthouse- oder Core-Web-Vitals-Wert.
- Schwellenwerte (z. B. 4 s Ladezeit, 8 Formularfelder, 4 Schriftfamilien) sind begründete Startwerte und im Raster einstellbar.
- Prozess-Rubriken sind Hypothesen: Ein PDF-Download beweist keinen ineffizienten internen Prozess.
- Ein hoher Wert bedeutet belegbares Verbesserungspotenzial, **nicht** Kaufbereitschaft, Budget oder eine Erlaubnis zur Kontaktaufnahme.
- Gerendert wird mit aktivem JavaScript. Interne und private Adressen sind gesperrt; SignalDesk bleibt trotzdem ein lokales Werkzeug für einen vertrauenswürdigen Rechner.

## Was ist als Nächstes sinnvoll?

1. **Live-Kalibrierung:** 5–10 echte Websites bewerten, dann Schwellen bzw. Gewichte im Raster anpassen. Jede Anpassung wird zu einer neuen Version.
2. **Phase 3 – Buying Signals:** Stellenanzeigen von den Karriereseiten der Firmen (die Bewertung erkennt Karriereseiten bereits), manueller Import von Registerbekanntmachungen, Ereignishistorie und Signal-Verknüpfung. Der Wert „Projektanlass“ im Scoring speist sich dann aus echten, datierten Signalen statt nur aus dem manuellen Lead-Feld.
