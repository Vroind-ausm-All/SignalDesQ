# OpenStreetMap nutzbar machen – manuell und offline

Stand 2.0.0-dev9. Hintergrund: Im Praxistest ([`PRAXISTEST_70191.md`](PRAXISTEST_70191.md)) waren die öffentlichen OpenStreetMap-Server bei jedem Versuch überlastet oder nicht erreichbar. Deshalb fragt SignalDesk sie nicht mehr von selbst ab.

## Wie es jetzt läuft

- **OpenStreetMap ist auf „manuell“ gestellt.** Eine Firmensuche fragt keinen öffentlichen OpenStreetMap-Server mehr ab, außer du kreuzt „OpenStreetMap jetzt online abfragen“ an.
- **Mit eingelesener Datei** nutzt jede Suche den lokalen Bestand: offline, sofort, ohne Fehlversuche.
- **Ohne Datei** meldet die Suche bei OpenStreetMap „läuft manuell“ und zeigt, was zu tun ist.

Alles dazu steht unter „Firmen finden → OpenStreetMap nutzbar machen“.

## Drei Wege, nach Aufwand

| Weg | Aufwand | Geeignet für |
|---|---|---|
| **Lokaler Auszug** (`.osm.pbf` von download.geofabrik.de) | einmal etwa 10 Minuten: laden, einlesen | ganze Stadt, Landkreis, Region; danach beliebig viele Suchen offline |
| **Handexport aus Overpass Turbo** (`.json` oder `.geojson`) | etwa 2 Minuten je Gebiet | eine PLZ oder ein Ort, wenn du nichts Großes laden willst |
| **Online abfragen** (wie bisher) | keiner | Ausnahme; scheitert oft |

### Lokaler Auszug, Schritt für Schritt

1. `download.geofabrik.de` öffnen: Europe → Germany → Baden-Württemberg → Regierungsbezirk Stuttgart.
2. Die Datei `stuttgart-regbez-latest.osm.pbf` laden (ein Regierungsbezirk hat meist 100–300 MB).
3. In SignalDesk „Datei einlesen“ wählen. Gespeichert werden nur benannte Betriebe, nicht die ganze Karte.
4. Suchen wie gewohnt. Für frische Daten später einen neuen Auszug einlesen; gleiche Einträge werden ersetzt, nicht verdoppelt.

SignalDesk braucht dafür kein Zusatzprogramm.

### Handexport, Schritt für Schritt

1. Ort oder PLZ in die Suche eintragen.
2. „Abfrage in Overpass Turbo öffnen“ anklicken – die Abfrage ist schon fertig eingetragen.
3. Im Browser „Ausführen“, dann „Export“ → „Rohdaten“ oder „GeoJSON“ speichern.
4. Die Datei in SignalDesk einlesen.

## Ganze Stadt oder nur eine PLZ?

| Eingabe | Umkreis | Ergebnis |
|---|---|---|
| `70191` | nur dieser Ort | genau diese PLZ |
| `Stuttgart` | nur dieser Ort | die ganze Stadt mit allen ihren Postleitzahlen |
| `70191` oder `Stuttgart` | 5 bis 75 km | alles im Umkreis um die Ortsmitte |

Für die ganze Stadt gilt beim lokalen Bestand: Ein Betrieb zählt dazu, wenn seine PLZ zur Stadt gehört oder sein Ortsname passt. Betriebe ganz ohne Adresse zählen nur, wenn sie höchstens 5 km von der Ortsmitte liegen.

**Viele Firmen übernehmen:** Der Knopf „Alle Treffer übernehmen“ übernimmt alle offenen Treffer des aktuellen Filters, je Durchgang bis 1.000.

**Viele Firmen auf einmal:** Das Budget je Lauf steht auf 300 neue Firmen und lässt sich im Suchformular bis 5.000 hochsetzen. Es wird auf die gewählten Quellen verteilt. Für ganz Stuttgart meldete GLEIF im Praxistest allein 3.281 Firmen.

## Was gespeichert wird

Name, Art des Betriebs, Anschrift, Website, allgemeine Telefonnummer, Öffnungszeiten, Lage. Keine E-Mail-Adressen, keine Betreibernamen, keine Wohnadressen. Nicht aufgenommen werden öffentliche Einrichtungen, Spielplätze, Parkplätze, Stillgelegtes und alles ohne Namen.

Daten: © OpenStreetMap-Mitwirkende, ODbL 1.0. Die Quelle wird bei jeder übernommenen Firma genannt.

## Grenzen

- **PLZ-Schätzung:** Betriebe ohne PLZ-Angabe bekommen die PLZ des nächsten Betriebs mit PLZ, wenn er höchstens 250 m entfernt liegt. An PLZ-Grenzen kann das danebenliegen; solche Treffer sind in der Suche als geschätzt ausgewiesen. Ohne Nachbarn in 250 m bleibt die PLZ unbekannt und der Betrieb fehlt in der PLZ-genauen Suche.
- **Lage der Gebäudeumrisse** ist der erste Eckpunkt des Umrisses, nicht die Gebäudemitte – auf Gebäudegröße genau.
- **Betriebe ohne Rechtsform im Namen** sind seit 2.0.0-dev9 standardmäßig dabei und als „ohne Rechtsform“ gekennzeichnet. Dahinter kann ein Einzelunternehmen stehen, der Firmenname kann ein Personenname sein – solche Daten haben Personenbezug. Im Suchformular abschaltbar.
- **Telefon und Öffnungszeiten** stammen ungeprüft aus OpenStreetMap und sind so gekennzeichnet. Feiertage, Zeiten über Mitternacht und Sonderformen („nach Vereinbarung“) werden nicht ausgewertet; dann steht „nicht sicher lesbar“.
- **Geprüft** wurde der Leser gegen Dateien, die das offizielle Werkzeug `osmium` erzeugt hat. Ein echter Geofabrik-Auszug ließ sich in der Testumgebung nicht laden; die Einlesezeit für einen ganzen Regierungsbezirk ist deshalb eine Schätzung (gemessen an einer erzeugten Datei mit 3 Millionen Punkten: 5 Sekunden, 41 MB Arbeitsspeicher).
