# SignalDesk v1.0 – Rechnungen & Buchhaltung

Neuer Menüpunkt **„Rechnungen & Buchhaltung“** mit fünf Bereichen. Alles läuft lokal; es wird nichts versendet und nichts an ELSTER, DATEV oder Banken übertragen.

## Erste Schritte

1. **Stammdaten & Sicherung**: Firmenname, Anschrift, Steuernummer *oder* USt-IdNr., E-Mail, Telefon, IBAN eintragen. Kleinunternehmer nur aktivieren, wenn § 19 UStG wirklich gilt. Ist- oder Soll-Versteuerung wählen.
2. **Backup jetzt erstellen**: legt eine konsistente Kopie im Ordner `backups` neben der Datenbank an (Standard: `%USERPROFILE%\.akquise-tool\backups`). Zusätzlich extern sichern.
3. **Angebot annehmen** (Angebote & Preise → Status „angenommen“): Lead wird auf „Gewonnen“ gesetzt, eine Aktivität protokolliert. Darunter erscheinen die Knöpfe „Abschlagsrechnung 40 %“ und „Schluss-/Gesamtrechnung“ (bei Growth Care: „Monatsrechnung“).
4. Im Rechnungsentwurf die **vollständige Kundenanschrift** und das **Leistungsdatum** ergänzen, „Entwurf speichern“, „Vorschau“ prüfen.
5. **Festschreiben**: Erst jetzt wird die fortlaufende Nummer vergeben. Danach ist die Rechnung unveränderbar.
6. **Drucken / PDF** (Browser-Druckdialog → „Als PDF speichern“) und/oder **E-Rechnung (XRechnung XML)** herunterladen und selbst versenden.
7. Zahlungseingang erfassen, bei Überfälligkeit Mahnschreiben entwerfen.

## Rechnungslogik

| Thema | Verhalten |
|---|---|
| Beträge | intern in ganzen Cent; USt je Steuersatz auf die Nettosumme (EN 16931) |
| Nummernkreis | `<Präfix>-<Jahr>-<lfd. Nr.>`, lückenlos je Jahr, Entwürfe verbrauchen keine Nummer |
| Rechnungsdatum | leer = Tag der Festschreibung; Zukunftsdatum und Rückdatierung vor die letzte Rechnung werden abgelehnt |
| Unveränderbarkeit | Datenbank-Trigger verhindern Änderung/Löschung festgeschriebener Rechnungen, Positionen, archivierter E-Rechnungen und des Protokolls |
| Korrektur | „Stornieren“ erzeugt eine Stornorechnung mit eigener Nummer und negativen Beträgen; nur ohne Zahlungseingang |
| Verkäuferdaten | werden bei Festschreibung eingefroren – spätere Stammdatenänderungen ändern alte Rechnungen nicht |
| Steuerbehandlung | Regelbesteuerung (19/7/0 %), Kleinunternehmer (§ 19), Reverse Charge für EU-Geschäftskunden (USt-IdNr. Pflicht) |
| Abschlag/Schluss | Schlussrechnung zieht alle festgeschriebenen, nicht stornierten Abschläge desselben Angebots ab |
| Wiederkehrend | „Als neuen Entwurf kopieren“ übernimmt Kunde und Positionen ohne Datum |
| Leads | Leads mit Rechnungen können nicht gelöscht werden (Aufbewahrungspflicht) |

## Mahnwesen

Drei Stufen (Zahlungserinnerung, 1. Mahnung, letzte Mahnung) mit neuer Frist und Wiedervorlage im Lead. Optional:
- **Verzugszinsen** nach § 288 Abs. 2 BGB: Basiszinssatz + 9 Prozentpunkte (Geschäftskunden). Basiszinssatz in den Stammdaten pflegen – er ändert sich zum 1.1. und 1.7.
- **Verzugspauschale** 40 € nach § 288 Abs. 5 BGB.

Beides nur, wenn tatsächlich Verzug vorliegt. Texte sind Entwürfe.

## Ausgaben & E-Rechnungen

- Manuelle Erfassung mit Brutto (USt wird herausgerechnet) oder optional manuellem USt-Betrag.
- **Reverse Charge § 13b** ankreuzen bei Rechnungen ohne USt aus dem EU-Ausland (z. B. Google/Meta Ads Irland, viele SaaS-Tools). Dann gilt der Betrag als Netto; die USt wird in Kz 46/47 und – außer bei Kleinunternehmern – als Vorsteuer in Kz 67 angesetzt.
- **E-Rechnung einlesen**: XRechnung (UBL oder CII) bzw. die XML aus einer ZUGFeRD/Factur-X-PDF. Die Original-XML wird mit SHA-256 unveränderbar archiviert und ist jederzeit herunterladbar. Werte füllen das Formular vor; Dubletten werden erkannt. XML mit DOCTYPE/ENTITY wird aus Sicherheitsgründen abgelehnt.
- Stornieren statt Löschen; GWG-Warnung > 800 € netto; fehlende Belegnummer oder fehlendes Zahlungsdatum werden markiert.

## Auswertung & Export

- **UStVA-Vorbereitung** für Monat/Quartal/Jahr, Ist- oder Soll-Basis, Kennzahlen 81, 86, 21, 46/47, 66, 67 und voraussichtliche Zahllast.
- **EÜR vereinfacht**: Einnahmen nach Zufluss, Ausgaben nach Abfluss, Aufteilung nach Kategorien. Keine AfA, keine Privatanteile.
- **Vertriebskennzahlen**: Angebote je Status, Annahmequote, Ø Auftragswert, Zahlungseingang je Kontaktweg.
- **CSV-Exporte** (Excel-kompatibel, `;`, deutsches Zahlenformat, Schutz gegen Formel-Injection): Rechnungsausgangsbuch, Ausgaben, Buchungsliste mit SKR03-Kontenvorschlägen. Kein DATEV-Format.
- **Änderungsprotokoll** aller buchhalterisch relevanten Aktionen.

## API (lokal, JSON)

| Methode & Pfad | Zweck |
|---|---|
| `GET/PUT /api/accounting/settings` | Stammdaten |
| `GET /api/accounting/overview` | KPIs, überfällige Rechnungen, unberechnete Aufträge, 12-Monats-Verlauf |
| `GET/POST /api/accounting/invoices` | Liste (`?status=`) / Entwurf anlegen |
| `POST /api/accounting/invoices/from-proposal` | `{proposal_id, mode: voll|abschlag|schluss, percent}` |
| `GET/PUT/DELETE /api/accounting/invoices/{id}` | Detail / Entwurf ändern / Entwurf löschen |
| `POST /api/accounting/invoices/{id}/finalize` | `{confirm: true}` |
| `POST /api/accounting/invoices/{id}/cancel` | `{confirm: true, reason}` |
| `POST /api/accounting/invoices/{id}/duplicate` | Kopie als Entwurf |
| `POST /api/accounting/invoices/{id}/payments` · `DELETE /api/accounting/payments/{id}` | Zahlung erfassen / zurücknehmen |
| `POST /api/accounting/invoices/{id}/dunning` | `{level, include_interest, include_fee}` |
| `GET /api/accounting/invoices/{id}/xrechnung` | XRechnung-XML |
| `GET /rechnung/{id}` | Druckansicht |
| `GET/POST /api/accounting/expenses` · `POST …/expenses/{id}/paid|cancel` | Ausgaben |
| `POST /api/accounting/einvoice/import` · `GET /api/accounting/documents[/{id}/xml]` | E-Rechnung empfangen / Archiv |
| `GET /api/accounting/report?from&to&basis` · `GET /api/accounting/sales-kpis?from&to` | Auswertungen |
| `GET /api/accounting/export/{rechnungen|ausgaben|buchungen}.csv?from&to` | Exporte |
| `GET /api/accounting/audit` | Änderungsprotokoll |
| `POST /api/backup` · `GET /api/backups` | Datensicherung |

## Grenzen & Prüfbedarf

- Die XRechnung folgt XRechnung 3.0 / EN 16931 (UBL), wurde aber **nicht mit dem offiziellen KoSIT-Validator geprüft** (in der Entwicklungsumgebung nicht erreichbar). Vor dem ersten Kundenversand eine Datei validieren.
- Keine ZUGFeRD-PDF, kein GiroCode, kein Bankimport, kein DATEV-Format, keine ELSTER-Übermittlung.
- Keine Verfahrensdokumentation – die musst du (ggf. mit Vorlage der Steuerberatung) selbst erstellen.
- Kontenvorschläge SKR03 sind Vorschläge, keine verbindliche Kontierung.
