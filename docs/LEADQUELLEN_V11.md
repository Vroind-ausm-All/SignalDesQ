# Lead-Quellen: Was darf SignalDesk automatisch nutzen? (v1.1, Stand November 2026)

> Keine Rechtsberatung. Zusammenfassung nach bestem Wissen; Nutzungsbedingungen ändern sich – vor produktivem Einsatz die aktuellen Bedingungen der jeweiligen Quelle prüfen.

## Drei Fragen pro Quelle

1. **Darf ich die Daten abrufen und speichern?** Lizenz, Nutzungsbedingungen/AGB, Datenbankherstellerrecht (§ 87b UrhG), Text-und-Data-Mining-Vorbehalt (§ 44b UrhG, z. B. per robots.txt).
2. **Sind es personenbezogene Daten?** Firmendaten juristischer Personen sind es nicht. Namen von Geschäftsführern, Einzelunternehmen und persönliche E-Mail-Adressen dagegen schon. Dann gelten Art. 6 Abs. 1 lit. f (berechtigtes Interesse, Abwägung), Art. 14 DSGVO (Information der Person spätestens beim ersten Kontakt bzw. binnen eines Monats) und Art. 21 (Widerspruch).
3. **Darf ich die Firma damit kontaktieren?** Das ist eine **separate** Frage (§ 7 UWG) – siehe unten. Eine Quelle zu nutzen heißt nie, dass man werben darf.

## Ampel

### Grün – automatisch im Lead-Finder

| Quelle | Lizenz / Regeln | Was sie liefert | Grenzen |
|---|---|---|---|
| **Wikidata** (SPARQL) | CC0 – frei, auch kommerziell; identifizierender User-Agent erwünscht | Firmen nach Sitz, Branche, Mitarbeiterzahl, Website | Lückenhaft bei kleinen Firmen |
| **OpenStreetMap** (Overpass API) | ODbL – Namensnennung „© OpenStreetMap-Mitwirkende“; Share-Alike nur bei Weitergabe einer abgeleiteten Datenbank. Fair Use: Richtwert < 10.000 Abfragen und < 1 GB pro Tag | Lokale Büros, Firmen, Handwerk mit Website und Adresse | Vollständigkeit regional unterschiedlich; enthält auch Einzelunternehmen → werden standardmäßig ausgefiltert |
| **GLEIF** (LEI-API) | CC0, ohne Key | Exakter Name, Rechtsform, Anschrift, Handelsregisternummer | Nur Firmen mit LEI; keine Website/Branche |
| **TED** (EU-Ausschreibungen, API v3) | Suche anonym ohne Key; Inhalte CC BY 4.0 bzw. Metadaten CC0 (Wiederverwendung erlaubt) | Konkrete Ausschreibungen für Web, Design, Software, Marketing | Nur oberschwellige Verfahren |
| **Lizenzierte Anbieter** (North Data, Echobot, Implisense …) | Vertrag/API-Key, kostenpflichtig | Firmendaten, Signale, teils Entscheider | Nicht eingebaut; sauberste Option zum Skalieren |

### Gelb – nur manuell oder eingeschränkt (Links im Lead-Finder)

| Quelle | Warum nicht automatisch |
|---|---|
| **Handelsregister** | Einsicht ist für jeden frei (§ 9 HGB), die Nutzungsordnung erlaubt aber höchstens 60 Abrufe pro Stunde und keine Massenabfragen; bei Missbrauch droht der Ausschluss. Gut zum Prüfen einzelner Firmen. |
| **Unternehmensregister / Bundesanzeiger** | Einzelabruf von Jahresabschlüssen (Größe, Entwicklung) ok; Captchas und AGB sprechen gegen eine Automatisierung. |
| **Bekanntmachungsservice** (oeffentlichevergabe.de) | Offizielle, frei zugängliche Vergabesuche des Bundes (auch unterschwellig). Eine offene Lese-API für Dritte ist nicht dokumentiert, daher manuell. |
| **Jobbörse der Bundesagentur** | Stellenanzeigen sind starke Signale. Die verbreitete „Jobsuche-API“ ist inoffiziell (Community-Dokumentation, öffentliche Client-ID) und ohne veröffentlichte Nutzungsbedingungen, daher nur manuell. Das Signal mit Quelle im Lead erfassen. |
| **OpenCorporates** | API nur mit Key, kostenfrei nur für Open-Data-Projekte; Share-Alike. |
| **Messe-Aussteller, IHK-/Verbandslisten** | Sehr passende Zielgruppen, aber meist AGB- und Datenbankschutz: gezielt auswählen, nicht komplett kopieren. |

### Rot – nicht automatisieren

| Quelle | Grund |
|---|---|
| **Gelbe Seiten, Das Örtliche, 11880** | AGB verbieten das Auslesen; Datenbankherstellerrecht § 87b UrhG. |
| **LinkedIn, XING** | Nutzungsbedingungen verbieten Scraping; Profile sind personenbezogen. Nur manuell und gezielt nutzen (der Entscheider-Finder erzeugt dafür Suchlinks). |
| **Google Maps / Google-Suchergebnisse** | Scraping untersagt; die Places-API ist kostenpflichtig und schränkt das Speichern ein. |
| **Gekaufte Adresslisten unklarer Herkunft** | Herkunft und Einwilligungen meist nicht belegbar. |

**Firmenwebsites** (bestehende URL-Recherche): zulässig, soweit robots.txt es erlaubt. Ein Verbot in der robots.txt gilt als maschinenlesbarer Vorbehalt nach § 44b UrhG; SignalDesk bricht dann ab. Es werden höchstens 5 Seiten derselben Domain gelesen.

## Kontaktaufnahme (§ 7 UWG, B2B)

| Kanal | Regel | In SignalDesk |
|---|---|---|
| **E-Mail-Werbung** | Nur mit vorheriger ausdrücklicher Einwilligung – auch gegenüber Unternehmen. Ausnahme § 7 Abs. 3 UWG für Bestandskunden nur unter engen Voraussetzungen. | Mailentwürfe nur für vereinbarte Kommunikation |
| **Telefon** | Gegenüber Unternehmen nur bei mindestens mutmaßlicher Einwilligung (konkretes, belegbares Interesse). Gerichte legen das eng aus. | Anruf-Protokoll mit Rechtsprüfung |
| **Brief** | Grundsätzlich zulässig, solange kein Widerspruch vorliegt und keine Sperrvermerke bestehen. DSGVO-Information beilegen, wenn Personendaten genutzt werden. | Kontaktweg „Briefpost“ |
| **Ausschreibung** | Keine Werbung, sondern Teilnahme am Verfahren über die Vergabeplattform. | Kontaktweg „Öffentliche Ausschreibung“ |
| **Empfehlung / Messe / Netzwerk** | Beste Wege für den Erstkontakt. | Kontaktwege vorhanden |

## Umsetzung im Lead-Finder (v1.1)

- **Datensparsam**: gespeichert werden nur Firmenname, Website, Anschrift, Branche, Größe, Registernummer, Quelle und Lizenz. Telefonnummern, E-Mail-Adressen und Personennamen aus den Quellen werden verworfen. Einträge ohne Rechtsformzusatz werden standardmäßig ausgefiltert.
- **Fair Use**: identifizierender User-Agent (mit Website/E-Mail aus den Stammdaten, falls gepflegt), 24-h-Ergebniscache, mindestens 10 Sekunden Abstand, höchstens 40 Abfragen pro Quelle und Tag.
- **Nachvollziehbar**: Jeder Treffer behält Beleg-Link und Lizenzhinweis. Bei Übernahme schreibt SignalDesk Quelle und Hinweis „Fund ist keine Einwilligung“ in den Lead und protokolliert eine Aktivität.
- **Bewusste Übernahme**: Dubletten werden über Domain und normalisierten Namen erkannt. Neue Leads starten mit Phase „Recherche“, Rechtsstatus „unbekannt“ und dem nächsten Schritt „Website prüfen“.
- **Sicher**: Eingaben werden streng geprüft (keine Abfrage-Injection in SPARQL/Overpass), Antworten sind größenbegrenzt.

### Noch nicht live geprüft

In der Entwicklungsumgebung waren die Quellen durch die Netzwerkrichtlinie gesperrt (`query.wikidata.org`, `overpass-api.de`, `api.gleif.org`, `api.ted.europa.eu`). Die Adapter folgen den dokumentierten Antwortformaten und sind mit Testdaten abgedeckt. Beim ersten Einsatz auf deinem Rechner bitte je Quelle eine Suche ausführen. Lehnt eine Quelle ein Feld ab, zeigt SignalDesk die Fehlermeldung der Quelle an (bei TED etwa HTTP 400 bei unbekannten Feldnamen).

## Quellen

- Handelsregister – Nutzungsgrenze 60 Abrufe/Stunde: [bundesAPI/handelsregister](https://github.com/bundesAPI/handelsregister), [§ 52 HRV](https://www.gesetze-im-internet.de/hdlregvfg/__52.html), [§ 9a HGB](https://lexetius.com/HGB/9a,5)
- Jobsuche-API (inoffiziell): [bundesAPI/jobsuche-api](https://github.com/bundesAPI/jobsuche-api)
- TED-API anonym: [docs.ted.europa.eu](https://docs.ted.europa.eu/api/latest/index.html), [TED Reuse](https://op.europa.eu/documents/d/ted-together/ted-together-ted-website-for-users-and-data-reusers)
- Datenservice Öffentlicher Einkauf: [vergabeblog.de](https://vergabeblog.de/2023-10-31/bescha-erfolgreicher-start-des-datenservice-oeffentlicher-einkauf/)
- Overpass Fair Use: [Overpass API User's Manual](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)
- § 44b UrhG: [gesetze-im-internet.de](https://www.gesetze-im-internet.de/urhg/__44b.html), [activemind.legal](https://www.activemind.legal/de/guides/urteil-data-mining)
- Werbung per E-Mail/Telefon/Brief: [IHK München](https://www.ihk-muenchen.de/ratgeber/recht/werbung-fairer-wettbewerb/marketing-per-email-telefon-brief-etc/), [Händlerbund](https://www.haendlerbund.de/de/news/aktuelles/wissenssnack/kaltakquise-b2b)
