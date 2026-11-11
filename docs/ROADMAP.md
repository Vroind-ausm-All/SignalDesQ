# Roadmap

Stand 2.0.0-dev6. Was erledigt ist, steht im [`CHANGELOG.md`](../CHANGELOG.md); die Lücken im Einzelnen in [`LAUNCH_AUDIT.md`](LAUNCH_AUDIT.md).

## Als Nächstes – lokaler Pilot

Reihenfolge nach dem Praxistest ([`PRAXISTEST_70191.md`](PRAXISTEST_70191.md)): erst die Quelle für Handwerksbetriebe, dann alles Weitere.

| Nr. | Arbeitspaket | Warum jetzt | Voraussetzung |
|---|---|---|---|
| 1 | **OpenStreetMap lokal:** Auszug für Baden-Württemberg laden, auf Betriebe vorfiltern, offline durchsuchen | einzige Handwerksquelle; öffentliche Server am Testtag in 4 von 4 Versuchen nicht verlässlich | Entscheidung zu Dateigröße und Lesewerkzeug (E5) |
| 2 | **Praxistest auf dem eigenen Rechner:** Website-Zuordnung und Firmen-Berichte an 50–100 Betrieben prüfen, mit von Hand geprüfter Referenzliste | in der Cloud-Umgebung nicht messbar | Eigentümer führt aus, Paket 1 hilft |
| 3 | **Handwerks-Suche als Voreinstellung:** Gewerke vorbelegt, Umgang mit Betrieben ohne Rechtsform bewusst entscheiden | 3 von 4 OSM-Einträgen wurden aussortiert | Entscheidung des Eigentümers (Datenschutz) |
| 4 | **Branche besser bestimmen:** OSM-Merkmale bevorzugen, Impressum und Website-Inhalt auswerten | 64 % der Treffer ohne Branche | – |
| 5 | **Geschäftszeiten und Telefon aus OpenStreetMap** in das Erreichbarkeitsprofil übernehmen | fällt mit Paket 1 fast nebenbei an | Paket 1 |
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
