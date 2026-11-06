# Bericht v1.14 – Live-Test der Quellen

Laut Masterplan v3 war der nächste Schritt der **Live-Test der ganzen Kette**. Bisher liefen alle Tests mit Attrappen: nachgebaute Antworten, die so aussehen, wie die Quellen laut Dokumentation antworten sollten. Für v1.14 hat SignalDesk die Quellen am 06.11.2026 **wirklich** abgefragt. Abgefragt wurden nur lesend kleine Testanfragen und eine echte Sammelsuche „70173 Stuttgart, 30 km“. Niemand wurde kontaktiert.

Ergebnis: Mehrere Quellen verhalten sich heute anders, als die Attrappen angenommen hatten. Das erklärt deine Fehlermeldungen beim Startknopf und die vielen unpassenden Firmen.

## Befunde und Änderungen

| Quelle | Live-Befund | Änderung in v1.14 |
|---|---|---|
| **GLEIF** | Jeder Filter auf Ort oder PLZ wird abgelehnt (HTTP 400 „Filter should contain only allowed values“). Erlaubt sind nur noch Volltext, Land, Status und Kategorie. Bisher kostete das 2 Fehlversuche je Ort. | Die erlaubten Filter werden sofort genutzt (Volltext + DE + aktiv), der Ort wird lokal geprüft. Ortsteile („Stuttgart - Möhringen“, „Stuttgart Feuerbach“) werden mitgenommen, die gingen bisher verloren. |
| **GLEIF** | Jeder Datensatz trägt den amtlichen **Rechtsform-Code (ELF)**. Die Erkennung aus dem Namen war fehlerhaft („…Fliegergruppen e.V.“ → „gruppe“). | Rechtsform aus dem ELF-Code (alle 31 deutschen Codes). Neue Auswahl **„Wen suchst du?“**: Unternehmen (Standard), Vereine/Verbände/Stiftungen, öffentliche Einrichtungen. |
| **Wikidata** | Wikimedia drosselt wegen einer Störung: „Aggressively rate-limiting to **1 req / min**“. Schon die zweite Anfrage innerhalb einer Minute führt zu HTTP 429 mit **1000 s** Sperre. Auch danach kam jede neue Anfrage sofort wieder mit 429 zurück. | Eigene Taktung: normal 2 s, nach Störungshinweis 65 s. Während einer Sperre keine Anfrage. Lange Sperren brechen sofort mit klarer Meldung ab, statt die Suche aufzuhalten. Die Firmenabfrage hat Vorrang; die Website-Ergänzung per LEI kommt am Ende, mit ≥ 65 s Abstand und in 1 statt bis zu 5 Abfragen. |
| **Suchgebiet** | Die Umkreisabfrage hing an Wikidata bzw. OpenStreetMap. Beide fielen aus; nach **189 s** blieb nur „nur Mittelpunkt“. Diese Notlösung wurde bisher **dauerhaft gespeichert**, sodass spätere Suchen nie Nachbarorte bekamen. | **Mitgeliefertes Ortsverzeichnis:** 13,216 Orte mit PLZ und Koordinaten, Ortsdaten: GeoNames, CC BY 4.0. Großkunden-PLZ wie „Daimler AG“ oder „Finanzamt“ sind bereinigt. Das Suchgebiet entsteht sofort und offline; Notlösungen werden nicht mehr gespeichert. |
| **TED** | Liefert Ort und PLZ des Auftraggebers (`buyer-city`, `buyer-post-code`) und filtert serverseitig nach Ort (`buyer-city IN (…)`). | Ausschreibungen standardmäßig **nur von Auftraggebern im Suchgebiet** (letzte 90 Tage), mit Ort, PLZ und Entfernung. „Bundesweit“ bleibt als Option. Bei gemeinsamen Beschaffungen mehrerer Städte zählt der Ort im Suchgebiet. |
| **OpenStreetMap** | Aus dem Rechenzentrum des Tests ist kein Overpass-Server erreichbar: Ein Server bricht die Verbindung sofort ab, zwei laufen in die Zeitüberschreitung. Je Server wurde bis zu 90 s gewartet, über Teilabfragen und Wiederholungen hinweg viele Minuten. | Höchstens 45 s je Server. Nicht erreichbare Server werden 10 min übersprungen, solche mit Zeitüberschreitung 5 min. Antwortet keiner, bricht OSM sofort ab, ohne sinnlose Wiederholungen. Überlastete Server, die antworten (dein Fall: 502 „at capacity“), werden weiter wiederholt. |
| **Nominatim** | Funktioniert. | Wird nur noch als Rückfall für Orte gebraucht, die das Ortsverzeichnis nicht kennt. |

## Neu: „Quellen prüfen“

Das Feld sitzt in „Firmen finden“ unter dem Startknopf. Ein Klick schickt je Quelle eine winzige Testanfrage, höchstens einmal pro Minute. Für jede Quelle steht dann eines davon da:
- **erreichbar**;
- **überlastet** (mit Wartezeit);
- **blockiert**: Internet, Firewall, Proxy oder Virenscanner prüfen;
- **Format geändert**: Die Quelle liefert erwartete Felder nicht mehr, der Adapter muss angepasst werden.

So machst du den Live-Test bei dir selbst: Was hier im Rechenzentrum blockiert ist (OpenStreetMap), kann bei dir zu Hause erreichbar sein.

## Ergebnis der echten Sammelsuche „70173 Stuttgart, 30 km“

Die Suche lief zweimal mit allen vier Quellen: einmal mit dem alten Verhalten bei nicht erreichbaren Servern, einmal mit v1.14.

| | Lauf 1 (alt) | Lauf 2 (v1.14) |
|---|---|---|
| **Gesamtdauer** | **856 s** (14 min) | **285 s** (5 min) |
| davon OpenStreetMap (nicht erreichbar) | ≈ 670 s Warten über 3 Versuche | ≈ 100 s, dann klare Meldung |
| Wikidata (gesperrt) | sofortige Meldung | sofortige Meldung |
| neue Firmen (GLEIF) | 4,609 | 4,531 (78 Besitz-/Fondsgesellschaften weniger) |
| Ausschreibungen im Suchgebiet (TED) | 25 | 11 (Software-Gruppe ohne Lizenzkäufe) |


- **Suchgebiet:** sofort, offline, 60 Orte (größte zuerst: Stuttgart, Esslingen, Ludwigsburg, Sindelfingen …).
- **GLEIF:** 82 Abfragen statt bisher rund 3 je Ort mit Fehlversuchen, ≈ 3 Minuten, **4,609 neue Firmen**, 2,703 ausgefiltert.
  - **Alle** Treffer liegen im Suchgebiet, keiner hat eine fehlende Entfernung.
  - Stuttgart 1,857, Ludwigsburg 221, Tübingen 158, Esslingen 143 …
  - Rechtsformen: GmbH 3,368 · KG 646 · GbR 207 · AG 147 · gGmbH 47 · eG 42 · UG 39.
  - Registernummer bei **95 %**.
  - Vereine, Stiftungen und öffentliche Stellen kamen mit der Standardauswahl nicht mehr hinein.
- **Neuer Filter:** In den 4,609 Treffern fanden sich noch **78 Besitz- und Fondsgesellschaften**: Grundbesitz-GmbHs, Wind- und Solarparks, nummerierte Fonds-Vehikel („… III Management GmbH“, „Nr. 90 KG“). Sie werden ab v1.14 ebenfalls ausgefiltert. Echte Firmen wie „Studio 3 GmbH“ bleiben.
- **Wikidata:** Sofortige, klare Fehlermeldung (Sperre ≈ 17 min); die Suche lief ohne Wartezeit weiter.
- **Übernehmen:** Zwei Firmen wurden übernommen, „0711 Digital GmbH“ und „0711 Kreativagentur GmbH“.
  - Anschrift, Registernummer, Phase „Recherche“, Rechtsstatus „unbekannt“ und der Schritt „Firmen-Bericht erstellen“ ohne Termin kamen richtig an.
  - In den Aufgaben stehen sie gesammelt unter „Recherche“.
  - **Fehler gefunden:** Die Rechtsform kam nicht im Lead an. Ab v1.14 wird sie übernommen.
- **Websites:** Nur 6 der GLEIF-Firmen bringen eine Website mit, über Wikidata/LEI. Deshalb ist die **automatische Website-Suche** nach der Suche (seit v1.13) der entscheidende Schritt. Sie prüft Domain-Vorschläge gegen das Impressum. Firmen-Websites sind aus der Testumgebung gesperrt, deshalb lief sie hier nicht live. Bei dir läuft sie normal.

- **TED, Ausschreibungen im Suchgebiet (live, neuer Code):** 50 Treffer aus vier Leistungsgruppen, alle mit Auftraggeber im Suchgebiet. Beispiele:
  - Stuttgarter Straßenbahnen AG: „Werbe- und Marketingdienstleistungen – Agenturdienstleistungen“;
  - Ministerium für Ländlichen Raum: „Kreative Dienstleistungen“;
  - AOK Baden-Württemberg: Kundenbefragung;
  - Stadt Ludwigsburg.
- **Software-Gruppe:** Live zeigte sich, dass der Code 48000000 („Softwarepaket und Informationssysteme“) vor allem Lizenz- und Gerätekäufe liefert (36 Treffer, darunter Kopiergeräte). Ersetzt durch 72230000 („Entwicklung von kundenspezifischer Software“). Jetzt 7 echte Entwicklungsaufträge, z. B.:
  - Tourismus Marketing GmbH BW;
  - Wilhelma (Kassen-/Ticketsystem);
  - NVBW (digitales Parkplatzkataster);
  - Stuttgarter Straßenbahnen.

## Was der Live-Test nicht abdecken konnte

- **Firmen-Websites** (Website-Suche, Impressum, Firmen-Bericht): Die Testumgebung darf nur die Quellen-Server erreichen, keine beliebigen Firmen-Websites. Diese Schritte sind mit Attrappen getestet und laufen bei dir über deine normale Internetverbindung.
- **OpenStreetMap:** von hier nicht erreichbar. Bei dir war es überlastet, aber erreichbar. „Quellen prüfen“ zeigt dir den Stand.
- **Kontakt, Termin, Angebot, Rechnung:** Diese Schritte laufen lokal, ohne externe Quelle, und sind durch die bestehenden Tests abgedeckt.

## Deine Rolle beim Live-Test

1. **„Quellen prüfen“** klicken und notieren, welche Quellen bei dir erreichbar sind.
2. Eine Suche **„Stuttgart, 30 km, Unternehmen“** starten. Die automatische Website-Suche danach laufen lassen.
3. 20 Firmen durchklicken und auf „Übernehmen“ oder „Verwerfen“ entscheiden. Merken, was unpassend war (Branche, Größe, Art).
4. Für 5 übernommene Firmen **„Firmen-Berichte erstellen“** (Aufgaben → Recherche) und prüfen, ob Impressum und Paketvorschlag stimmen.
5. Rückmeldung in die nächste Runde geben, gern mit dem Ergebnis von „Quellen prüfen“.

## Tests

- **Neue Tests:** 19 neue automatische Tests in `tests/test_v114_livetest.py`.
  - Die Attrappen bilden jetzt die **echten** Antworten nach:
    - GLEIF lehnt Ortsfilter ab und liefert ELF-Codes und Ortsteile;
    - Wikidata-Seite mit „1 req / min“ und Retry-After 1000;
    - TED-Ortsfelder und Ortsfilter;
    - Overpass mit Verbindungsabbruch.
  - Bestehende Tests mit der alten GLEIF-Annahme sind entsprechend angepasst.
- **Gesamt:** 295 automatische Tests, alle grün.
- **Browser-Test (Chromium), ohne Konsolenfehler:**
  - Quellen-Check;
  - „Wen suchst du?“ mit Hinweis, wenn nichts gewählt ist;
  - Ausschreibungen im Suchgebiet;
  - Sammelsuche mit Offline-Suchgebiet;
  - Vereine zuschaltbar;
  - Handyansicht ohne seitliches Scrollen.

## Technik

- `sales_tool/legal_forms.py`: ELF-Codes und Organisationsart.
- `sales_tool/gemeinden.py` mit `sales_tool/data/gemeinden_de.json`: Ortsverzeichnis, gebaut mit `tools/build_gemeinden.py` aus GeoNames.
- `sales_tool/source_check.py` mit Endpunkt `POST /api/sources/check`. Er verlangt `{"run": true}`, weil er echte Anfragen auslöst.
- Neue Sammelsuche-Parameter: `org_kinds` (unternehmen/verein/oeffentlich) und `ted_nationwide`.
- Schema-Version 21: Spalte `discovery_candidates.org_kind`.
