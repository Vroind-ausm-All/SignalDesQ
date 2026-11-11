# Roadmap

Stand 2.0.0-dev4. Was erledigt ist, steht im [`CHANGELOG.md`](../CHANGELOG.md); die Lücken im Einzelnen in [`LAUNCH_AUDIT.md`](LAUNCH_AUDIT.md).

## Als Nächstes – lokaler Pilot

| Nr. | Arbeitspaket | Voraussetzung |
|---|---|---|
| 1 | **Praxistest an 50–100 echten Betrieben** im Zielgebiet: Homepage-Zuordnung, Berichtsqualität und Bewertung messen | Freigabe und Suchgebiet vom Eigentümer |
| 2 | **Bewertung an echten Ergebnissen prüfen:** Werden A-Firmen häufiger Kunden? Gewichte einstellbar machen | genug gewonnene und verlorene Chancen |
| 3 | **Nachkalkulation:** Ist-Zeiten je Auftrag; macht die Auslastung verlässlich | – |
| 4 | **Ein Leistungskatalog** statt drei Listen (`model.OFFERS`, `sales_workspace.PACKAGES`, `pricing`) | – |
| 5 | **Geschäftszeiten der Firmen** aus OpenStreetMap und hinterlegten Website-Daten | – |
| 6 | **OpenStreetMap ohne öffentliche Server** (lokaler Auszug), falls der Praxistest häufige Ausfälle zeigt | Messung aus Nr. 1 |
| 7 | **Übrige Hintergrund-Module auf die neustartfeste Auftragsliste** (Quickscan, KI-Analyse, Kontakt-Recherche, Website-Scoring, Kaufsignal-Scan) | – |
| 8 | **Navigation auf sechs Bereiche** verdichten; alten Lead-Fit in der Anzeige ablösen | – |
| 9 | **Windows-Abnahme** auf einem echten Gerät: frische Installation, Update, Wiederherstellung | grüne CI |

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
