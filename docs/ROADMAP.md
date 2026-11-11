# Roadmap

Stand 2.0.0-dev7. Was erledigt ist, steht im [`CHANGELOG.md`](../CHANGELOG.md); die Lücken im Einzelnen in [`LAUNCH_AUDIT.md`](LAUNCH_AUDIT.md).

## Als Nächstes – lokaler Pilot

Reihenfolge nach dem Praxistest ([`PRAXISTEST_70191.md`](PRAXISTEST_70191.md)). Die Suche bleibt grundsätzlich ohne festgelegte Branche; Handwerk war nur der Probelauf.

| Nr. | Arbeitspaket | Warum jetzt | Voraussetzung |
|---|---|---|---|
| 1 | ~~OpenStreetMap lokal~~ – erledigt in 2.0.0-dev7 (lokaler Auszug, Handexport, online nur auf Wunsch) | – | – |
| 2 | **Praxistest auf dem eigenen Rechner:** echten Auszug einlesen, dann Website-Zuordnung und Firmen-Berichte an 50–100 Betrieben prüfen, mit von Hand geprüfter Referenzliste | in der Cloud-Umgebung nicht messbar | Eigentümer führt aus |
| 3 | **Telefon und Öffnungszeiten aus OpenStreetMap** in Firmenakte und Erreichbarkeitsprofil zeigen | liegen seit dev7 im lokalen Bestand | – |
| 4 | **Branche besser bestimmen:** OSM-Merkmale bevorzugen, Impressum und Website-Inhalt auswerten | 64 % der Treffer ohne Branche | – |
| 5 | **Viele Firmen in einem Zug übernehmen:** Sammelübernahme und Sichtung für große Trefferlisten prüfen und beschleunigen | Suche bleibt bewusst ohne Branche; ganze Städte liefern Tausende Treffer | Messung aus Nr. 2 |
| 6 | **Bewertung an echten Ergebnissen prüfen;** Gewichte einstellbar | – | genug gewonnene und verlorene Chancen |
| 7 | **Ein Leistungskatalog** statt drei Listen | – | – |
| 8 | **Zeiten je Leistung** in der Nachkalkulation; Katalogwerte aus Ist-Zeiten vorschlagen | – | genug abgeschlossene Aufträge |
| 9 | **Übrige Hintergrund-Module auf die neustartfeste Auftragsliste** | – | – |
| 10 | **Navigation auf sechs Bereiche** verdichten; alten Lead-Fit in der Anzeige ablösen | – | – |

## Danach – Buchhaltung

Bankumsatz-Import mit Abgleich, Belegupload mit Prüfsumme, GiroCode, Vorlage Verfahrensdokumentation, DATEV-Export nach Testimport mit der Steuerberatung.

## Später – SaaS

Erst nach einem bestandenen lokalen Piloten und nachgewiesener Zahlungsbereitschaft (Entscheidung E1 in [`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md)). Nötig sind dann: Trennung nach Organisation, PostgreSQL, getrennte Recherche-Worker mit Budgets, Anmeldung über OIDC, Überwachung, externe Sicherungen, Datenschutzprüfung, Abrechnung über einen etablierten Anbieter. Ein Plan dafür (`SAAS_LAUNCH_PLAN.md`) ist noch nicht geschrieben.

**Kein öffentlicher Start**, bevor Mandantentrennung, Rechteprüfung, Anmeldung, Sicherung und Wiederherstellung sowie die Datenschutzprüfung nachweislich bestanden sind.

## Absichtlich kein Feature

- Massenhafte Kalt-E-Mails, LinkedIn-Bots, gekaufte Kontaktlisten, WhatsApp-Spam
- Auslesen von Google Maps, LinkedIn oder Suchmaschinen; Umgehen von Sperren, Captchas oder robots.txt
- KI-Bewertung, die ihr Ergebnis ohne Quellenbeleg als Tatsache ausgibt
- Direkte ELSTER-Übermittlung, automatischer Versand von Rechnungen oder Mahnungen
