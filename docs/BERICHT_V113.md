# Bericht v1.13 – Feedbackrunde nach dem ersten Praxistest

Ausgangspunkt war deine Rückmeldung zu v1.12. Die Katalogwerte passen, deshalb gibt es dort keine Änderung. Jede Kritik und was sich geändert hat:

## 1. „Sehr viele Unternehmen haben ihren Sitz nicht in Stuttgart“

Für die fremden Orte gab es zwei Ursachen:
- **TED-Ausschreibungen sind bundesweit.** Sie hängen nicht am Suchort. Die Quelle ist jetzt standardmäßig **aus** und heißt „Ausschreibungen (TED, bundesweit)“.
- **Der Umkreis holt Nachbarorte dazu.** Bei 30 km gehören Esslingen, Ludwigsburg, Böblingen usw. bewusst dazu.

Neu dazu:
- Umkreis **„nur dieser Ort“** (0 km): Es wird nur der Mittelpunkt abgefragt, ohne Umkreissuche.
- In der Sichtung kannst du filtern:
  - **Ort** als Auswahlliste mit Anzahl, z. B. „Stuttgart (212)“;
  - **Höchstentfernung**, z. B. „nur im Ort (≤ 0,5 km)“ oder „bis 5 km“;
  - **„ohne Ausschreibungen“**.

## 2. Fehler am Startknopf (Wikidata HTTP 429, OpenStreetMap HTTP 502 „at capacity“)

Beides sind Überlastungsmeldungen der kostenlosen Server. Sie liegen nicht an SignalDesk. Wie empfohlen, wiederholt SignalDesk die Abfrage jetzt mit **wachsender Pause**:
- **Automatische Wiederholung:** Eine überlastete Quelle wird nach 20 s und nach 60 s erneut abgefragt. Nennt der Server eine Wartezeit (`Retry-After`), wird sie beachtet, höchstens aber 2 Minuten. Der Fortschritt zeigt dann „neuer Versuch …“.
- **OpenStreetMap in kleinen Teilabfragen** (je 6 Merkmale statt einer großen Abfrage). Antwortet ein Teil nicht, bleiben die anderen Treffer erhalten. Der Status zeigt dann z. B. „1 von 2 Teilabfragen überlastet“.
- **Knopf „Fehlgeschlagene Quellen erneut abfragen“:** Er fragt später nur die fehlgeschlagenen Quellen nach. Schon gefundene Firmen bleiben erhalten, und es entstehen keine Dubletten.

## 3. „Firmenwebseite recherchieren und automatisieren – bisher muss man die Daten manuell einpflegen“

- **Nach jeder Suche startet die Website-Suche automatisch.** Sie läuft für bis zu 200 Firmen ohne Website, die nächsten zuerst. Abschalten kannst du sie mit der Checkbox „Websites danach automatisch suchen“. Eine Website gilt weiterhin nur mit Nachweis als gefunden: Registernummer oder Name und PLZ stehen im Impressum.
- **Impressumsdaten werden automatisch übernommen:**
  - Beim **Übernehmen** einer Firma mit „belegt“-Website werden Rechtsform, Anschrift, Registergericht, Registernummer, USt-IdNr. sowie geschäftliche Telefonnummer und E-Mail automatisch in **leere** Lead-Felder geschrieben.
  - Der **Firmen-Bericht** übernimmt das Impressum ebenfalls automatisch.
- Leitplanken dabei:
  - Vorhandene oder bestätigte Werte werden **nie überschrieben**.
  - Bei nur „wahrscheinlicher“ Zuordnung bleiben die Werte als ungeprüfte Belege zur Prüfung stehen.
  - **Personen werden nie automatisch angelegt.**
  - Die Kontakterlaubnis bleibt „unbekannt“.

## 4. Aufgaben überladen

Ursache war, dass jede übernommene Firma die Aufgabe „Website prüfen (URL-Recherche)“ mit Termin in 2 Tagen bekam. Behoben ist das an der Quelle und in der Ansicht:
- Neue Firmen bekommen nur noch den Schritt „Firmen-Bericht erstellen“, **ohne Termin**. TED-Ausschreibungen behalten ihre Frist.
- Ist ein Bericht fertig, wird der Schritt automatisch zu „Kontaktweg klären (Firmen-Bericht liegt vor)“.
- Die Aufgaben sind jetzt **gegliedert:**
  - Recherche;
  - Kontakt & Freigaben;
  - Termine & Gespräche;
  - Angebote & Abrechnung;
  - Sonstiges.

  Oben stehen Kacheln mit Anzahl und „überfällig“. Jede Gruppe lässt sich aufklappen, und dein Zustand wird gemerkt.
- **Die Recherche ist je Firma zusammengefasst** (eine Zeile pro Firma, mit Website- und Berichtsstatus):
  - **„Firmen-Berichte für alle mit Website erstellen“** – ein Klick für alle;
  - **„Erledigte Recherche-Schritte bereinigen“** für Altlasten aus v1.12.
- Auf „Heute“ steht die Recherche nur noch als **ein Sammelpunkt** („14 Firmen mit fälligem Recherche-Schritt“), nicht als 14 Einzelzeilen.

## 5. Deal-Pipeline zu lang – Drag & Drop, Click & Drop, kompakte Karten

- Die Karten zeigen nur **Name und Score**. Ein Klick klappt die Details auf: Anlass, nächster Schritt, Aktionsknopf, Phase und Lead öffnen.
- **Drag & Drop:** Eine Karte mit der Maus in eine andere Spalte ziehen.
- **Click & Drop:** ⇄ antippen und dann die Zielspalte anklicken. Das funktioniert auch auf Touch-Geräten und per Tastatur (Enter); Esc bricht ab.
- Die neue Spalte **„Verloren“** nimmt abgesagte Chancen auf.
- Wechselst du auf „Gewonnen“, kommt weiterhin eine Rückfrage.
- Die Spalten haben eine feste Höhe und scrollen in sich, sodass die Seite nicht mehr endlos lang wird.

## Tests

- **19 neue automatische Tests, insgesamt 276, alle grün:**
  - Wiederholung mit wachsender Pause, Obergrenze und Retry-After;
  - erneutes Abfragen fehlgeschlagener Quellen;
  - OSM-Teilerfolg;
  - Umkreis 0;
  - Orts-, Entfernungs- und TED-Filter;
  - automatische Website-Suche;
  - Impressums-Übernahme („belegt“ füllt nur leere Felder, „wahrscheinlich“ bleibt ungeprüft);
  - Gliederung der Aufgaben, Sammelpunkt und Bereinigung;
  - Bericht schließt den Recherche-Schritt;
  - HTTP-Endpunkte.
- **Netzwerk:** Alle Netzwerkantworten in den Tests sind Attrappen mit fiktiven Firmen. Sie stellen deine Fehlerbilder nach (429, 502 „at capacity“); echte Abfragen an Wikidata, OSM, GLEIF oder TED laufen in den Tests nicht.
- **Browser-Test (Chromium), ohne Konsolenfehler:**
  - Suche mit überlasteten Quellen → Knopf „erneut abfragen“ → alle Quellen fertig;
  - Ortsfilter;
  - Aufgaben-Gruppen mit „9 Firmen-Berichte gestartet“;
  - Pipeline: Drag & Drop, Click & Drop, Esc und Rückfrage bei „Gewonnen“;
  - Handyansicht ohne seitliches Scrollen der Seite.

## Technik

- Schema-Version 20 mit neuer Spalte `discovery_candidates.imprint_json`. Vor der Migration wird automatisch eine Sicherung angelegt.
- Neue Endpunkte:
  - `GET /api/tasks/overview`;
  - `POST /api/tasks/research-cleanup`;
  - `POST /api/sweeps/{id}/retry`.
- `GET /api/sweep-candidates` versteht zusätzlich `city`, `max_km` und `no_ted=1` und liefert die Ortsliste `cities`.
- Neue Dateien: `public/tasks.js`, `public/pipeline.js`.
