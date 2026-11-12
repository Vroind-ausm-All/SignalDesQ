# Roadmap

Stand 2.0.0-dev11. Was erledigt ist, steht im [`CHANGELOG.md`](../CHANGELOG.md); die Lücken im Einzelnen in [`LAUNCH_AUDIT.md`](LAUNCH_AUDIT.md),
die Oberflächen-Vorschläge mit Messwerten in [`UI_UX_VORSCHLAEGE.md`](UI_UX_VORSCHLAEGE.md).

Die Suche bleibt grundsätzlich ohne festgelegte Branche. Jede Stufe endet mit einem lauffähigen Stand, Tests unter Python 3.10
und 3.13, Browser-Tests und einem Eintrag im [`SELF_REVIEW_LOG.md`](SELF_REVIEW_LOG.md).

## Erledigt seit dem Praxistest 70191

| Stand | Inhalt |
|---|---|
| dev6 | PLZ-genaue Suche, Budget fair auf die Quellen verteilt |
| dev7 | OpenStreetMap manuell und offline: lokaler Auszug, Handexport, online nur auf Wunsch |
| dev8 | PLZ-Schätzung, Lage von Gebäudeumrissen, Telefon und Öffnungszeiten |
| dev9 | Betriebe ohne Rechtsform einbezogen und gekennzeichnet, Branche aus OSM-Merkmal, „Alle Treffer übernehmen“ |
| dev10 | Datenschutz-Nachweis mit Löschfrist für Betriebe ohne Rechtsform, Hinweistext nach Art. 14 DSGVO, Löschen nach Fristablauf |
| dev11 | Themes (Klassisch, Schiefer, Sand, Kontrast), Hell/Dunkel, Dichte „Kompakt“; geprüfte Kontraste |

## Als Nächstes – lokaler Pilot

| Nr. | Arbeitspaket | Warum | Voraussetzung |
|---|---|---|---|
| 1 | **Praxistest auf dem eigenen Rechner:** echten OSM-Auszug einlesen, danach Website-Zuordnung und Firmen-Berichte an 50–100 Betrieben gegen eine von Hand geprüfte Referenzliste messen | Website-Zuordnung, Tempo bei tausenden Treffern und Branchenabdeckung sind in der Cloud-Umgebung nicht messbar | Eigentümer führt aus; parallel zu allem anderen |
| 2 | **Firmenakte mit Reitern** (Vorschlag V2): Überblick, Kontakt & Erreichbarkeit, Bewertung, Verlauf, Stammdaten; stehender Kopf mit nächster Aktion | Der Lead-Dialog ist heute rund zehn Bildschirme lang | – |
| 3 | **Einheitliche Statusmarken** (V6) für Passung, Phase, Frist und Quelle – mit Symbol, nicht nur Farbe | elf Varianten; Farbe allein trägt Bedeutung | – |
| 4 | **Bereich „Einstellungen“** (V3), danach **Navigation auf sechs Bereiche** (V4); alten Lead-Fit in der Anzeige ablösen | Einstellungen liegen in fünf Ansichten verstreut; 16 Navigationseinträge | – |
| 5 | **Lead-Liste mit Filterchips und gespeicherten Ansichten** (V5) | Filtern geht nur nach Phase | Nr. 3 |
| 6 | **Branche für GLEIF-Treffer** aus Impressum und Website-Inhalt | 64 % der GLEIF-Treffer ohne Branche | Praxistest (Nr. 1) |
| 7 | **Bewertung an echten Ergebnissen prüfen;** Gewichte einstellbar | Passung soll sich an gewonnenen und verlorenen Chancen messen | genug abgeschlossene Chancen |
| 8 | **Ein Leistungskatalog** statt drei Listen | doppelte Pflege | – |
| 9 | **Zeiten je Leistung** in der Nachkalkulation; Katalogwerte aus Ist-Zeiten vorschlagen | Kalkulation lernt aus der Praxis | Nr. 8, genug abgeschlossene Aufträge |
| 10 | **Übrige Hintergrund-Module auf die neustartfeste Auftragsliste** | fünf Module laufen noch als einfacher Thread | – |

Vorgeschlagener Zuschnitt der nächsten Stufen: **dev12** = Nr. 2 + 3, **dev13** = Nr. 4, **dev14** = Nr. 5 + 8.
Nr. 6 und 7 folgen, sobald der Praxistest Daten liefert.

## Danach – Buchhaltung

Bankumsatz-Import mit Abgleich, Belegupload mit Prüfsumme, GiroCode, Vorlage Verfahrensdokumentation, DATEV-Export nach Testimport mit der Steuerberatung.

## Später – SaaS

Erst nach einem bestandenen lokalen Piloten und nachgewiesener Zahlungsbereitschaft (Entscheidung E1 in [`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md)). Nötig sind dann: Trennung nach Organisation, PostgreSQL, getrennte Recherche-Worker mit Budgets, Anmeldung über OIDC, Überwachung, externe Sicherungen, Datenschutzprüfung, Abrechnung über einen etablierten Anbieter, Darstellung je Nutzer statt je Installation. Ein Plan dafür (`SAAS_LAUNCH_PLAN.md`) ist noch nicht geschrieben.

**Kein öffentlicher Start**, bevor Mandantentrennung, Rechteprüfung, Anmeldung, Sicherung und Wiederherstellung sowie die Datenschutzprüfung nachweislich bestanden sind.

## Absichtlich kein Feature

- Massenhafte Kalt-E-Mails, LinkedIn-Bots, gekaufte Kontaktlisten, WhatsApp-Spam
- Auslesen von Google Maps, LinkedIn oder Suchmaschinen; Umgehen von Sperren, Captchas oder robots.txt
- KI-Bewertung, die ihr Ergebnis ohne Quellenbeleg als Tatsache ausgibt
- Direkte ELSTER-Übermittlung, automatischer Versand von Rechnungen oder Mahnungen
