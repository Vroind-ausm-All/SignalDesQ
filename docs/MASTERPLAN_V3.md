# SignalDesk Masterplan v3 – vom Funktionsumfang zum Arbeitstag

Grundlage: Nutzer-Feedback nach dem ersten Praxiseinsatz (November 2026). Ausgangsstand: v1.8, alle sechs Phasen aus Masterplan v2 umgesetzt.

## Feedback in Kürze

- **Struktur:** zu viele Funktionen, teils ohne erkennbare Wirkung. Der Tag eines Agenturinhabers soll von oben nach unten geführt werden.
- **Übersicht:** Sie soll den Tagesbeginn erklären, angefangene Aufgaben zur Wiedervorlage bringen und das offene Potenzial mit den kalkulierten Angeboten verknüpfen.
- **Pipeline:** soll klickbar sein. „Termin“ führt zu „Termin vereinbaren“, „Kontakt geprüft“ zu „Kontakt aufnehmen“.
- **Firmensuche:** Bisher wenig nutzbar.
  - GLEIF meldet einen Fehler, Wikidata liefert nichts, OpenStreetMap ist überlastet.
  - Gewünscht: ein Knopf zu Beginn der Arbeitssitzung, viele Ergebnisse zum Durchklicken, Websites als Link in neuem Tab.
- **Import:** CSV nur bis 300 KB nutzbar. Ein manueller GLEIF-Export mit 5,7 MB und 4.039 Einträgen soll verarbeitet werden.
- **Recherche:** URL-Recherche, Website-Scoring und Kaufsignale sollen zu einem Bericht mit einem Klick zusammengelegt werden.
- **Angebote & Preise:** nachvollziehbare Preise und ein deutlich größeres Leistungsspektrum.

## Zielstruktur (Navigation nach Tagesablauf)

1. **Heute:** Tagesplan, Wiedervorlage, offenes Potenzial, klickbare Pipeline, Funktionsstatus
2. **Kunden finden:** Sammelsuche und Import, sichten per Klick
3. **Recherchieren:** Firmen-Bericht mit einem Klick (Research Center mit Detailansichten)
4. **Verkaufen:** Leads, Pipeline, Kontakt & Termine, Angebote & Preise
5. **Abrechnen:** Rechnungen & Buchhaltung
6. **Erweitert:** Datenqualität & System, KI-Studio, Sales-Playbook

## Sprints

### Sprint A – Struktur & Tagesablauf ✅ v1.9 – Bericht: `docs/BERICHT_SPRINT_A.md`

- **Navigation** in der Reihenfolge des Arbeitstags. Selten genutzte Bereiche liegen unter „Erweitert“; ein ehrlicher Funktionsstatus zeigt, was eine Voraussetzung braucht.
- **„Heute“:**
  - Tagesplan in 6 Schritten mit Direktsprung;
  - Wiedervorlage: fällige Aufgaben, nächste Schritte, Rückrufe, Nachfassen, Bindefristen, begonnene Bedarfsanalysen, Termine;
  - offenes Potenzial aus kalkulierten Angeboten statt aus Schätzungen.
- **Klickbare Pipeline:** jede Phase und jede Karte mit der nächsten Aktion.
- **„Kontakt & Termine“** in der Reihenfolge Freigeben → Kontakt aufnehmen → Termin vereinbaren.

### Sprint B – Firmen finden, die wirklich funktionieren ✅ v1.10 – Bericht: `docs/BERICHT_SPRINT_B.md`

- **Quellen reparieren:**
  - GLEIF: seitenweise Abfrage und Fehlertext anzeigen. Dafür wird der Wortlaut der Fehlermeldung des Nutzers gebraucht.
  - Wikidata: leichtere Abfrage, zusätzlich Suche per LEI.
  - OpenStreetMap: Ausweichserver, Wiederholversuche, kleinere Abfragen.
- **„Arbeitstag starten“:** alle Quellen gemeinsam im Hintergrund abfragen, mit Fortschritt, und die Treffer zusammenführen (LEI, Registernummer, Domain, Name).
- **GLEIF-CSV-Import in beliebiger Größe** mit Vorfilter für aktive Firmen ohne Fonds und Holdings. Beim Beispiel-Export bleiben von 4.039 Einträgen ca. 2.236 operative Firmen übrig.
- **Website-Suche mit Nachweis:** Wikidata (per LEI), OSM und naheliegende Domains. Belegt ist eine Website erst, wenn die Registernummer im Impressum übereinstimmt.
- **Sichtungsliste:** Website als Link in neuem Tab, Behalten oder Verwerfen per Klick bzw. Taste, „Behaltene analysieren“ als Stapel.
- **Live-Test durch den Nutzer**, weil die Quellen in der Entwicklungsumgebung gesperrt sind.

### Sprint C – Firmen-Bericht mit einem Klick ✅ v1.11 – Bericht: `docs/BERICHT_SPRINT_C.md`

- Impressum, Website-Scoring, Kaufsignale, Entscheider und Hypothesen laufen in einem Auftrag.
- Ergebnis ist ein Bericht pro Firma, auch für viele Firmen am Stück.
- Die bisherigen Einzelbereiche bleiben als Detailansichten.

### Sprint D – Angebote & Preise ✅ v1.12 – Bericht: `docs/BERICHT_SPRINT_D.md`

- **Leistungskatalog:** etwa 20 Leistungen in den Bereichen Strategie, Marke, Website/Shop, Sichtbarkeit, Barrierefreiheit (BFSG), Datenschutz-Check, Portal/App, Automatisierung/KI, Betreuung und Schulung.
- **Größen S, M und L** mit Liefergegenständen.
- **Nachvollziehbarer Preis:** Aufwand × Satz + Puffer + Fremdkosten = Festpreis. Die Aufschlüsselung bleibt intern; der Kunde sieht Leistungen und Festpreis.
- **Angaben des Nutzers (November 2026):**
  - **Leistungen:**
    - handgestaltete Kunst
    - Texten
    - Webdesign
    - Grafikdesign
    - Print- und Web-Angebote
    - Logogestaltung
    - Individualsoftware zur Verbesserung des Arbeitsalltags
    - Anbindung an verschiedene Shops
    - Aufbau eigener Webshops
    - professionelle Fotografie und Videografie
    - Werbung und SEO-/GEO-Optimierung
    - KI-Chatbot-Integration
    - Telefon-Sprachbot-Integration
    - Webseiten-Analyse mit Handlungsbedarf
  - **Kalkulation:**
    - mindestens 66 €/h Zielverdienst (über 13 Jahre Erfahrung);
    - teils Festpreise, dazu Anreise und Tagespauschale als eigene Positionen.

## Danach ← nächster Schritt
Masterplan v3 ist damit umgesetzt. Als Nächstes steht der Live-Test der ganzen Kette beim Nutzer an:
- Firmen finden → Bericht → Kontakt → Termin → Angebot → Rechnung;
- Katalogwerte an die eigene Erfahrung anpassen;
- Rückmeldung als Grundlage für die nächste Runde.

## Leitplanken (unverändert)

Es gelten weiter alle Leitplanken aus Masterplan v2:
- keine Scraper für Google Maps, LinkedIn oder Jobportale;
- kein automatischer Versand; jede Kontaktaktion braucht eine eigene Freigabe;
- Fund ≠ Einwilligung;
- Fakten getrennt von Interpretationen;
- interne Kalkulation bleibt intern.
