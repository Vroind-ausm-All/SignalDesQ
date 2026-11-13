# Praxistest: Firmensuche in Stuttgart, PLZ 70191

Durchgeführt am 11.11.2026 mit Freigabe des Eigentümers, gegen die echten Quellen. Es wurde niemand kontaktiert.

> **Versionsbezug:** Gemessen mit Stand 2.0.0-dev6. Die späteren OpenStreetMap-Erweiterungen (lokaler Auszug dev7, PLZ-Schätzung und Öffnungszeiten dev8, Branche aus OSM-Merkmal dev9) sind in diesen Zahlen nicht enthalten. Die Zahlen sind keine aktuelle Erfolgsquote; die belastbare Messung ist Maßnahme M21 in `ROADMAP.md`.
Dieser Bericht enthält nur Zahlen, keine Firmennamen – das Repository ist öffentlich.

**Einordnung:** Das ist eine erste Messung der Suche, noch nicht der in `UEBERGABE_FABLE.md` verlangte Test an 50–100 Betrieben mit
unabhängig geprüfter Referenzliste. Website-Zuordnung und Berichtsqualität ließen sich von der Testumgebung aus nicht messen (siehe Abschnitt 4).

## 1. Ausgangslage (Stand 2.0.0-dev5)

Suche „70191“, Umkreis „nur dieser Ort“, Budget 300 Firmen, Quellen GLEIF, Wikidata, OpenStreetMap.

| Messgröße | Ergebnis |
|---|---|
| Von GLEIF gemeldet | 3.281 Firmen – aus ganz Stuttgart |
| Übernommen (Budget) | 300 |
| davon mit Sitz in 70191 | **2 (0,7 %)** |
| davon Handwerk (aus dem Namen geschätzt) | 11 (3,7 %) |
| ohne erkennbare Branche | 195 (65 %) |
| mit Website | 0 |
| Wikidata, OpenStreetMap | **nicht gelaufen** – „Budget von 300 neuen Firmen erreicht“ |

Zwei Programmfehler:

1. **Die PLZ wurde ignoriert.** Eine PLZ wurde in die Gemeinde übersetzt; „nur dieser Ort“ hieß ganz Stuttgart.
2. **Die erste Quelle verbrauchte das ganze Budget.** OpenStreetMap – die einzige Quelle mit Handwerksbetrieben – kam nie an die Reihe.

## 2. Behebung (2.0.0-dev6)

- Eine fünfstellige PLZ mit „nur dieser Ort“ gilt jetzt als genau diese PLZ. GLEIF wird per Volltext nach der PLZ gefragt (live geprüft: 112 Treffer, 110 mit Sitz in 70191), OpenStreetMap über das PLZ-Gebiet statt über einen Umkreis um die Stadtmitte. Einträge mit anderer PLZ werden aussortiert.
- Das Budget wird auf die gewählten Quellen verteilt; was eine Quelle nicht nutzt, geht an die nächste.
- Ein Ortsname („Stuttgart“) oder eine PLZ mit Umkreis verhalten sich wie bisher.

## 3. Wiederholung nach der Behebung

| Messgröße | vorher | nachher |
|---|---|---|
| Kandidaten | 300 | 56 |
| mit Sitz in 70191 | 2 (0,7 %) | **56 (100 %)** |
| Quellen gelaufen | 1 von 3 | 3 von 3 |
| GLEIF | 300 übernommen | 110 gefunden, 55 übernommen, 55 aussortiert (z. B. reine Verwaltungs- und Beteiligungsgesellschaften) |
| OpenStreetMap | übersprungen | 4 Einträge, 1 übernommen; 1 von 2 Teilabfragen überlastet |
| Wikidata | übersprungen | 0 Unternehmen |
| Handwerk | 11 | **1** |
| ohne erkennbare Branche | 65 % | 64 % (36 von 56) |
| Rechtsformen | – | 41 GmbH, 7 KG, 3 AG, 2 PartG mbB, 1 GbR |
| Laufzeit | 53 s | 202 s (mit Website-Stichprobe) |

Eine gezielte Handwerks-Abfrage nur über OpenStreetMap (zwölf Gewerke, mit und ohne Betriebe ohne Rechtsform im Namen) scheiterte zweimal: alle Server überlastet oder nicht erreichbar.

## 4. Was nicht messbar war

- **Website-Zuordnung und Impressum:** 15 von 15 Website-Prüfungen schlugen fehl. Ursache ist die Testumgebung, nicht das Programm: Dort gibt es keine Namensauflösung (DNS), und der sichere Abruf löst Adressen absichtlich selbst auf, um sich nur mit der geprüften Adresse zu verbinden. Dieser Schutz wurde nicht umgangen. **Die Messung muss auf deinem Rechner laufen.**
- **Abdeckung des Handwerks in OpenStreetMap:** nicht messbar, weil die Server nicht antworteten.
- **Richtigkeit der Treffer:** Es gibt keine unabhängige Referenzliste. „Sitz in 70191“ stammt aus den Quellen selbst.

## 5. Was die Messung zeigt

1. **Für „Handwerk in 70191“ liefert die Suche heute praktisch nichts** – 1 Betrieb von 56. Das liegt an den Quellen, nicht mehr an der Suche: GLEIF enthält nur Firmen mit LEI (Kapitalgesellschaften, Finanz- und Beteiligungsfirmen), kaum Handwerk. OpenStreetMap ist die einzige Handwerksquelle und war in vier von vier Versuchen an diesem Tag überlastet oder nur teilweise erreichbar.
2. **Die Branche bleibt bei zwei Dritteln unbekannt**, weil sie bei GLEIF aus dem Firmennamen geschätzt wird.
3. **Handwerksbetriebe ohne Rechtsform im Namen** („Elektro Müller“) werden bei OpenStreetMap vorsorglich aussortiert, weil dahinter eine Einzelperson stehen kann. In der Stichprobe betraf das 3 von 4 Einträgen. Für die Zielgruppe Handwerk ist diese Voreinstellung zu streng; sie lässt sich je Suche abschalten („auch Betriebe ohne Rechtsform“), sollte aber mit Blick auf den Datenschutz bewusst entschieden werden.

## 6. Folgerungen

| Nr. | Maßnahme | Begründung aus der Messung |
|---|---|---|
| 1 | **OpenStreetMap-Auszug lokal nutzen** (Baden-Württemberg, vorgefiltert auf Betriebe) | einzige Handwerksquelle, öffentliche Server in 4 von 4 Versuchen nicht verlässlich (Entscheidung E5) |
| 2 | **Praxistest auf dem eigenen Rechner wiederholen**, inklusive Website-Suche und Firmen-Bericht | Website-Zuordnung hier nicht messbar |
| 3 | **Voreinstellung „Betriebe ohne Rechtsform“ für Handwerks-Suchen klären** | 3 von 4 OSM-Einträgen aussortiert |
| 4 | **Branche besser bestimmen** (OSM-Merkmale bevorzugen, Impressum und Website-Inhalt auswerten) | 64 % ohne Branche |

## 7. So wiederholst du die Messung bei dir

1. SignalDesk starten, unter „Einstellungen → Zielkunden“ (bis dev13: „Datenqualität & System“) das Zielkundenprofil einstellen (Standort 70191, Handwerks-Branchen).
2. „Firmen finden“: Ort `70191`, Umkreis „nur dieser Ort“, Handwerks-Branchen anklicken, Website-Suche an.
3. Notieren: Treffer je Quelle, wie viele ein Handwerksbetrieb sind, bei wie vielen die Website stimmt (von Hand prüfen), wie viele Firmen-Berichte brauchbar sind.
4. Zeigt „Quellen prüfen“ OpenStreetMap als überlastet: später wiederholen und die Uhrzeit notieren.
