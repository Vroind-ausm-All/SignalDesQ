# Sprint-Bericht B – Firmen finden, die wirklich funktionieren (v1.10)

Gemäß `docs/MASTERPLAN_V3.md`, Sprint B, mit den Rückmeldungen des Nutzers vom 05.11.2026.

## Ausgangslage

| Quelle | Gemeldeter Fehler | Ursache (aus dem Code) | Lösung |
|---|---|---|---|
| GLEIF | `HTTP 400: Filter should contain only allowed values` | Eine der drei gleichzeitig gesendeten Filterangaben (Land, Ort, Status) wird von der API abgelehnt. Welche, lässt sich ohne Live-Zugang nicht feststellen. | **Fallback-Kette:** bei HTTP 400 automatisch mit weniger Filtern erneut fragen (Ort + Land → nur Ort → Volltext); den Rest (aktiv, keine Fonds, Land, Ort) **lokal filtern**. Die funktionierende Variante wird für die Folgeseiten gemerkt, damit nicht jede Seite neu fehlschlägt. Statt einer Seite mit 200 Treffern werden jetzt **bis zu 25 Seiten je Ort** abgefragt, in höflichem Abstand (~1 Anfrage/Sekunde). |
| Wikidata | `HTTP 502 Bad Gateway` | Die Abfrage suchte über alle Unterklassen von „Unternehmen“ (`P31/P279*`) und brach am Zeitlimit des Servers ab. | Leichte Abfrage ohne transitive Klassensuche, Personen ausgeschlossen, Branchen-Stichwort lokal gefiltert. Ein Wiederholversuch bei 502/503/504; danach eine verständliche Meldung („gerade überlastet“). |
| OpenStreetMap | `The read operation timed out` | Nur ein Overpass-Server mit 30 s Zeitlimit, und der ist häufig überlastet. | Drei Server nacheinander (overpass-api.de, overpass.private.coffee, overpass.kumi.systems), 90 s Zeitlimit. |
| TED | funktionierte | – | Unverändert, jetzt Teil der Sammelsuche. |

## Was ist tatsächlich implementiert?

### „Arbeitstag starten“ – alle Quellen mit einem Knopf (Firmen finden)
- **Eingabe:**
  - Ort **oder** fünfstellige PLZ und ein Umkreis von 5, 10, 20, **30** (Standard), 50 oder 75 km;
  - **Branchen** zum Anklicken: 65 Branchen in 8 Gruppen, mit Suchfeld;
  - **eigene Schlagwörter**, durch Komma getrennt;
  - Quellen einzeln abwählbar; Filter „nur operative Firmen“ (Standard) und „auch Einzelunternehmen“.
- **Suchgebiet:**
  - Der Mittelpunkt kommt aus Nominatim (OpenStreetMap). Es gibt eine Anfrage je neuem Ort oder neuer PLZ, die dauerhaft zwischengespeichert wird.
  - Die Gemeinden im Umkreis kommen aus Wikidata (Gemeinden mit Einwohnerzahl), ersatzweise aus OpenStreetMap, im Notfall bleibt nur der Mittelpunkt.
  - Bis zu 60 Gemeinden werden nach Größe sortiert. Das Ergebnis wird je (Ort, Umkreis) gespeichert.
- **Ablauf im Hintergrund**, mit Fortschritt je Quelle:
  - Je Quelle wird angezeigt: neu, zusammengeführt, schon bekannt, ausgefiltert und die Fehlermeldung.
  - **Fällt eine Quelle aus, laufen die anderen weiter.**
  - Die einzelnen Quellen:
    - **GLEIF:** alle Gemeinden des Umkreises, seitenweise.
    - **Wikidata:** eine Umkreisabfrage (Unternehmen mit Sitz im Umkreis) und zusätzlich die **Websites zu GLEIF-Firmen über die LEI**.
    - **OpenStreetMap:** Betriebe der gewählten Branchen (über OSM-Merkmale) im Umkreis, ohne Branchenwahl Firmen mit Website.
    - **TED:** Ausschreibungen (Web, Design, Software, Marketing).
- **Dubletten vermeiden:**
  - Zusammengeführt wird über **LEI, Registernummer + Ort, Domain und Name + Ort**. Dieselbe Firma aus GLEIF und Wikidata erscheint als **ein** Eintrag mit beiden Quellen.
  - Firmen, die schon Lead sind, werden als „schon Lead“ markiert und nicht als neu gezeigt. Einträge der Sperrliste bekommen den Status „Sperrliste“.
  - **Verworfene Firmen kommen nie wieder**, auch nicht über eine andere Quelle oder bei einer späteren Suche.
  - Eine erneute Suche im selben Gebiet erzeugt keine Doppelten.
- **Datensparsam:**
  - OSM- und Wikidata-Einträge ohne Rechtsform (möglicherweise Personen) bleiben standardmäßig weg.
  - Holding-, Verwaltungs-, Beteiligungs-, Fonds- und Vorratsgesellschaften werden als „nicht operativ“ ausgefiltert (abschaltbar).
- **Systematisch arbeiten:**
  - „Deine Gebiete & Suchläufe“ zeigt jede Suche mit offen, übernommen und verworfen.
  - „Sichten“ öffnet die Treffer eines Laufs, „Erneut suchen“ übernimmt die Parameter.
  - Die zuletzt benutzten Eingaben merkt sich der Browser.
- **Grenzen:** höchstens 20 Sammelsuchen am Tag und nur eine gleichzeitig.

### Sichtung zum Durchklicken
- **Liste mit 50 Firmen je Seite.** Pro Firma:
  - Name, Anschrift, Entfernung, Registernummer, Branche (geschätzt);
  - **Website als Link in neuem Tab** (`target=_blank`, `rel=noopener noreferrer`) mit Herkunft der Website;
  - Quellen als Links zum Originaldatensatz;
  - allgemeines Telefon und E-Mail sowie Impressum-Link, sobald das Impressum gelesen wurde.
- **Filter:** Status, Suchlauf/Import, mit oder ohne Website, Sortierung (Entfernung, mehrere Quellen zuerst, Website zuerst, Name), Suche nach Name, Ort oder PLZ.
- **Aktionen:** „Übernehmen“, „Verwerfen“, „Website suchen“, auch für mehrere Firmen auf einmal.
- **Tastatur:** ↑/↓ bzw. j/k zum Wechseln, **o** öffnet die Website, **b** übernimmt, **v** verwirft.
- **Übernahme** legt einen Lead an mit Firmenname, Anschrift, Registernummer, Website und – nur bei juristischen Personen – allgemeinem Telefon und E-Mail. Die Quellen werden protokolliert. **Rechtsstatus „unbekannt“**, Phase „Recherche“.

### Website-Suche mit Nachweis
- **Ohne Website:** SignalDesk prüft bis zu 7 naheliegende Domains aus dem Firmennamen (z. B. `reith-spezialkabel.de`, `dinkelacker.de`) und liest jeweils das Impressum. Dabei gelten dieselben Schutzregeln wie bei der Impressumsprüfung: robots.txt, SSRF-Schutz, Größenlimit.
- **Mit Website:** Die vorhandene Website wird über ihr Impressum geprüft.
- **Zuordnung:**

  | Status | Bedingung |
  |---|---|
  | **belegt** | Die Registernummer im Impressum stimmt überein. |
  | **wahrscheinlich** | Firmenname und PLZ stimmen überein. |
  | nicht eindeutig / nicht gefunden | Sonst; die geprüften Domains werden angezeigt. |

  Ein fremdes Impressum wird nie zugeordnet.
- Die Suche läuft im Hintergrund, bis 200 Firmen auf einmal, etwa 2–10 Sekunden je Firma. Die Liste aktualisiert sich selbst.

### Großer Import (deine `lei-records.csv` und eigene Listen)
- **Import-Knopf in „Firmen finden“:** Dateien **bis 60 MB**. Erkannt werden:
  - **GLEIF-Exporte** (Spalten wie `Entity.LegalName`);
  - **eigene Listen** (Firma/Name, Website, PLZ, Ort, Straße, Register, Branche), mit Komma, Semikolon oder Tab, in UTF-8 oder Windows-1252.
- **Filter:** aktiv, keine Fonds oder Einzelpersonen (wahlweise), nur operative Firmen, gewählte Branchen und Schlagwörter. Steht im Ortsfeld eine PLZ, wird zusätzlich auf deren PLZ-Region gefiltert (z. B. „70…“).
- **Deine Datei:**

  | | Anzahl |
  |---|---|
  | Zeilen in der Datei | 4.039 |
  | übersprungen: inaktiv | 327 |
  | übersprungen: Fonds/Einzel | 300 |
  | übersprungen: Ausland | 10 |
  | ausgefiltert: nicht operativ | 1.136 |
  | **neue Firmen zum Sichten** | **2.265** |

  Das Einlesen dauert etwa 0,4 Sekunden. Ein zweiter Import derselben Datei erzeugt **keine** Dubletten, und Import und Live-Suche werden über die LEI zusammengeführt.
- **Datenprüfung:** Wird dort ein GLEIF-Export oder eine Datei über 300 KB gewählt, landet sie automatisch im Import unter „Firmen finden“.

**Technik:**
- **Neue Module:** `industries.py` (Branchenkatalog), `area.py` (Suchgebiet), `sweep.py` (Sammelsuche, Zusammenführen, Import, Sichtung, Website-Suche), `public/sweep.js`.
- **Quellen-Reparatur** in `lead_finder.py`; die einzelne Quellenabfrage bleibt unter „Einzelne Quelle gezielt abfragen“.
- **Datenbank (Schema 18):**
  - neue Tabellen `sweeps`, `discovery_keys`, `discovery_dismissed`, `geo_cache`, `search_areas`;
  - neue Spalten in `discovery_candidates`;
  - automatische Sicherung vor der Migration.

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **239 Tests grün**, davon 16 neu in `tests/test_sprintB_sweep.py`.
- **Die Fehlerbilder des Nutzers wurden in Attrappen nachgestellt:**
  - GLEIF-HTTP-400: Fallback greift, Inaktive und Fonds werden lokal gefiltert, Folgeseiten ohne Fehlversuch.
  - Wikidata-502: Wiederholversuch und verständliche Meldung.
  - OSM-Timeout: der Ausweichserver antwortet.
- **Suchgebiet:** Umkreis (Ulm außerhalb von 30 km), Cache ohne zweite Netzanfrage, Rückfall auf den Mittelpunkt.
- **Sammelsuche:**
  - GLEIF und Wikidata werden über die LEI zusammengeführt; Website über LEI.
  - Nicht operative Firmen, Personen und Einträge ohne Rechtsform werden gefiltert.
  - Sperrliste, bestehender Lead (über die Domain), zweite Suche ohne Dubletten.
  - Verworfenes kommt über keine Quelle zurück; fällt eine Quelle aus, laufen die anderen weiter.
  - Branchen- und Schlagwortfilter für GLEIF (Name) und OSM (Merkmale).
  - Eingaben werden geprüft, Tageslimit und nur eine gleichzeitige Suche.
- **Import:** GLEIF-Export (Anführungszeichen, Großschreibung, PLZ-Region, Inaktive, Fonds, Holding), erneuter Import, Zusammenführung mit der Live-Suche, eigene Liste mit Semikolon, Datei ohne Namensspalte.
- **Übernahme und Verwerfen:** Lead mit Registernummer, PLZ, Rechtsstatus „unbekannt“; Stapelaktion; Sperrschlüssel.
- **Website-Suche:** „belegt“ über die Registernummer mit Kontaktweg, „wahrscheinlich“ über Name und PLZ, fremdes Impressum nicht zugeordnet, geprüfte Domains protokolliert.
- **HTTP-Endpunkte:** inklusive CSV-Upload und falschem Content-Type. Der Sicherheitstest aus Phase 6 prüft automatisch, dass auch die neuen GET-Routen nichts verändern und keine Route bei fehlerhaften Anfragen mit 500 antwortet.
- **Klickdurchlauf im Browser** (Chromium, Quellen nachgestellt), ohne Konsolenfehler:
  - Branchenwahl mit Suche; Sammelsuche mit Fortschritt je Quelle
  - Websites öffnen in neuem Tab; Tastatur v/b
  - **Import der echten `lei-records.csv` über die Oberfläche:** 2.185 neue Firmen in der PLZ-Region 70
  - Website-Suche mit Ergebnis „belegt (Registernr.)“ samt Telefon und Impressum-Link
  - Umleitung aus der Datenprüfung; Mobilansicht 390 px

## Was ist noch ungetestet?

- **Die echten Quellen.** In der Entwicklungsumgebung sind GLEIF, Wikidata, OpenStreetMap, Nominatim und TED gesperrt, alle Tests laufen gegen Attrappen.
  - Ob die GLEIF-Fallback-Kette den konkreten Filterfehler löst, zeigt erst dein Test. Falls nicht, steht die neue, genauere Fehlermeldung unter „Heute → Was funktioniert gerade?“.
- **Treffermengen und Laufzeiten im echten Umkreis**, z. B. wie viele OSM-Betriebe 30 km um Stuttgart liefern.
- **Die Website-Suche gegen echte Firmenwebsites**, also die Trefferquote der Domain-Vorschläge.

## Welche Grenzen bestehen?

- **Branchen:** GLEIF und importierte Listen enthalten keine Branche. Sie wird aus dem Firmennamen geschätzt; Firmen mit neutralem Namen erscheinen nur ohne Branchenfilter.
- **Kontaktdaten:** Die offenen Quellen liefern kaum welche. Allgemeine Firmenkontakte kommen erst aus dem Impressum (Website-Suche).
  - Personen werden in der Firmensuche nicht gesammelt; Ansprechpartner folgen wie bisher über den Lead-Dialog.
  - Ein Fund ist keine Einwilligung: Übernommene Firmen starten mit Rechtsstatus „unbekannt“.
- **Ergebnismengen:** Die Website-Suche über Domain-Vorschläge findet nur Websites mit naheliegendem Namen. Firmen mit Fantasie-Domains bleiben „nicht gefunden“. Dann hilft Selbersuchen über die verlinkten Quellen.
- **Fair Use:** GLEIF wird mit höchstens 150 Abfragen je Sammelsuche (~1/Sekunde) abgefragt, Nominatim einmal je Ort. Es gibt keine Massenabfragen bei Registern, Gelben Seiten, Google Maps oder LinkedIn.

## Was ist als Nächstes sinnvoll?

1. **Live-Test auf deinem Rechner:** Firmen finden → 70173 · 30 km → „Arbeitstag starten“. Danach unter „Heute → Was funktioniert gerade?“ nachsehen, ob alle vier Quellen grün sind, und eventuelle Fehlermeldungen schicken.
2. **Den GLEIF-Import sichten:** Filter „nur ohne Website“, 200 auswählen, „Websites suchen“, später „nur mit Website“ und durchklicken.
3. **Sprint C – Firmen-Bericht mit einem Klick:** Für übernommene Firmen laufen Impressum, Website-Scoring, Kaufsignale und Entscheider als ein Auftrag. Das Ergebnis ist ein Bericht pro Firma.
4. **Sprint D – Angebote & Preise** mit deinem Leistungskatalog (66 €/h, Festpreise, Anreise, Tagespauschale).
