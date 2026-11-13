# Roadmap

Stand 2.0.0-dev14. Abgeglichen mit dem externen Produktreview vom 13.11.2026 (geprüft auf dev11, Maßnahmen M01–M26 in vier
Etappen A–D; das Review liegt nicht im Repository). Rollen der Dokumente: **diese Datei** führt den Status jeder künftigen
Maßnahme, [`CHANGELOG.md`](../CHANGELOG.md) beschreibt Änderungen, [`SELF_REVIEW_LOG.md`](SELF_REVIEW_LOG.md) die Nachweise,
[`LAUNCH_AUDIT.md`](LAUNCH_AUDIT.md) ist eine **historische** Bestandsaufnahme von dev1.

Die Suche bleibt grundsätzlich ohne festgelegte Branche. Jede Stufe endet mit einem lauffähigen Stand, Tests unter Python 3.10
und 3.13 und Browser-Tests. **Regel nach jeder Etappe (aus dem Review):** nur erweitern, wenn die vereinbarten Abnahmefälle
bestehen; neue Funktionen dürfen weder die Zahl der Menüpunkte noch die Länge der Firmenakte unkontrolliert wachsen lassen.

## Abgleich mit dem Review

| Empfehlung des Reviews | Entscheidung | Begründung |
|---|---|---|
| Erst Bedienungssicherheit (Etappe A: M01–M05), dann Menüumbau | **übernommen** | dev12 und dev13 bilden Etappe A. Der bisher für dev13 geplante Bereich „Einstellungen“ rückt auf dev14. |
| Eingabeschutz und Öffnungsfokus zusammen mit der Firmenakte | **übernommen** in dev13 | Die Reiter aus dev12 hätten den Eingabeverlust sonst nur anders verpackt. |
| Alte Prioritätsanzeige ablösen, keine erfundenen Vorgaben | **übernommen** in dev13 | Liste und Pipeline zeigen die Passung; neue Firmen ohne vorbelegte Branche und Leistung. |
| Firmenakte als eigene Seite mit direkter Adresse | **teilweise** | dev12 hat Reiter im Dialog. Eine eigene Adresse je Firma folgt mit M07 (dev14); dann wird entschieden, ob die Akte eine Seite wird. |
| Optional lokal gesicherte Entwürfe | **abgewandelt** | Nicht gespeicherte Eingaben bleiben nur im Arbeitsspeicher, nicht im Browser-Speicher – Gesprächsnotizen sollen nicht unbemerkt auf der Festplatte liegen. |
| Sechs Hauptbereiche, Zielstruktur und Zuordnungstabelle | **übernommen** für dev14/dev15 | Die Zuordnung aller 16 heutigen Ziele aus dem Review dient als Abnahme. |
| V7 (Heute als Fokusliste) und V9 (Leerzustände) in die Roadmap | **übernommen** als M08 und M11 | – |
| Mehrere Verkaufschancen je Firma | **übernommen** als Etappe C | Eigenes Datenmodell mit Migration, Sicherung und Wiederherstellungstest – nicht nebenbei im Menüumbau. |
| Keine weitere Theme-Runde, kein zusätzlicher KI-Bereich, SaaS nachrangig | **übernommen** | – |
| Prüffall K01 (Korrekturschleifen widersprechen sich) | **vorgezogen** in dev13 | Kleiner, eindeutiger Fehler im Kundenangebot. |
| Status in einer Quelle (M26) | **übernommen** in dev13 | Diese Tabelle; Launch-Audit als historisch gekennzeichnet. |

## Status je Maßnahme

Status: **erledigt** (mit Version und Test), **teilweise**, **offen**. „Erledigt“ heißt technisch umgesetzt und automatisch
geprüft – nicht praxisvalidiert; das leistet erst der Pilot (M21).

| ID | Maßnahme | Prio | Status | Version | Abnahme | Nächstes Hindernis |
|---|---|---|---|---|---|---|
| M01 | Ungespeicherte Eingaben schützen | P0 | erledigt | dev13 | T04 im Browser-Test: Rückfrage Speichern / Weiter bearbeiten / Verwerfen | Eingaben außerhalb des Lead-Dialogs (Angebots-, Rechnungsformulare) noch ohne Schutz |
| M02 | Firmenakte mit Reitern und stehendem Kontext | P0 | erledigt | dev12 | Fünf Reiter, Kopf mit Name und nächster Aktion; längster Reiter 2.322 px statt rund 7.800 px | Eigene Adresse je Firma (M07) |
| M03 | Öffnungsfokus und Rückkehr | P0 | erledigt | dev13 | T03 im Browser-Test: Überblick mit Fokus auf dem Reiter, nach dem Schließen Fokus auf der Zeile | – |
| M04 | Bewertung und neutrale Vorgaben vereinheitlichen | P0 | erledigt | dev13 | T02: neue Firma ohne Branche und Leistung; gleiche Passung mit gleichem Text in Liste, Pipeline, Akte | Recherchepriorität unter „Recherche & Berichte“ ist ein dritter Wert (Recherche-Reihenfolge, keine Kundenbewertung) – Beschriftung mit M09 klären |
| M05 | Statusmarken und verständliche Begriffe | P1 | erledigt | dev12, dev13 | Fünf Stufen mit Symbol; Phasenschlüssel übersetzt | Filter- und Zählerchips angleichen (mit M09) |
| M06 | Einstellungen zusammenführen | P1 | erledigt | dev14 | Eigener Bereich mit Darstellung, Zeiten, Zielkunden, Leistungen & Preise, Recherche, Daten & Zugang; Preise aus Angeboten verlinkt (Browser- und Strukturtest) | Einstellungen je Nutzer im Team-Betrieb |
| M07 | Sechs Hauptbereiche mit direkter Navigation | P1 | teilweise | dev14 | Sechs Bereiche, Reiter, Adressen für Ansicht, Firma, Abschnitt und Listenfilter; T05 bestanden | Adressen für Filter weiterer Listen und für Firmen-Berichte; Entscheidung Akte als eigene Seite |
| M08 | Heute auf nächste Aktionen ausrichten (V7) | P1 | teilweise | dev13 | „Nichts offen“ ≠ „erledigt“ im Tagesplan; offen: drei nächste Aktionen mit Grund und Frist oben | Prioritätsregeln abstimmen |
| M09 | Filterchips und gespeicherte Arbeitsansichten (V5) | P1 | offen | → dev15 | Ansicht „Heute fällig“ wieder öffnen; Spalten nächste Aktion und Datum | M05, einheitliche Felder |
| M10 | Globale Suche und Strg+K (V8) | P2 | offen | später | Firma, Chance, Angebotsnummer über ein Suchfeld | M07 |
| M11 | Geführter Einstieg und Leerzustände (V9) | P1 | offen | → dev15 | Einrichtung ohne vollständigen Recherchelauf | M06–M08 |
| M12 | Zentraler Leistungskatalog | P1 | offen | Etappe C | Eine Kennung je Leistung; alte Angebote unverändert; K01 behoben (dev13) | Migrationskonzept für 5/6/26 Einträge |
| M13 | Mehrere Verkaufschancen je Firma | P1 | offen | Etappe C | T08: zwei Chancen mit getrennten Phasen, Bedarf, Terminen | Datenmodell, Migration mit Prüfliste |
| M14 | Briefings für Medien und Software | P1 | offen | Etappe C | Fragen je Leistungsbereich; Annahme auf bestätigte Angaben rückführbar | M13 |
| M15 | Angebotsrevisionen und Varianten | P1 | offen | Etappe C | T11: Revision mit Vorgänger; angenommene Fassung bleibt | M12, M13 |
| M16 | Nachfassen mit Anlass, Frist und Ergebnis | P1 | teilweise | dev3 | Rückrufe, Wiederholversuche, Parken vorhanden; offen: Bezug zu Chance und Angebot | M13 |
| M17 | Schlanke Auftragsübergabe und Abnahme | P2 | offen | Etappe D | T12 | M13, M15 |
| M18 | Zusatzaufträge und Leistungsänderungen | P2 | offen | Etappe D | Ursprungsumfang bleibt erkennbar | M15, M17 |
| M19 | Bestandskunden und Betreuungsleistungen | P2 | offen | Etappe D | Betreuung und neue Projekte getrennt | M13 |
| M20 | Zeiten je Leistung und Lernvorschläge | P2 | teilweise | dev5 | Ist-Zeiten je Auftrag vorhanden; offen: je Position | M12 |
| M21 | Lokaler Recherchepilot | P0 | offen | – | 50–100 Firmen gegen Referenzliste; Messgrößen aus dem Review | **Eigentümer:** echter OSM-Auszug und Referenzliste auf dem eigenen Rechner |
| M22 | Quellenstatus und Datenqualität | P1 | teilweise | dev6–dev9 | „Keine Website gefunden“ ≠ „hat keine Website“ | Ergebnisse aus M21 |
| M23 | Gemeinsame Hintergrundaufträge vervollständigen | P1 | teilweise | Masterplan 2.0 | Alle Module mit gleichem Lebenszyklus nach Neustart | fünf Module laufen noch als Thread |
| M24 | Kalender und dokumentierte Exporte | P2 | offen | Etappe D | Aktualität und Konflikte geprüft | Anbieterwahl |
| M25 | Kundenfähiger Kurzbericht | P2 | offen | Etappe D | Nur ausgewählte, geprüfte Befunde; keine internen Kalkulationen | Auswahl- und Vorschaukonzept |
| M26 | Aktuellen Status in einer Quelle pflegen | P1 | erledigt | dev13 | Diese Tabelle; Launch-Audit als historisch gekennzeichnet | bei jeder Stufe nachführen |

## Etappen

| Etappe | Inhalt | Stand |
|---|---|---|
| A – verlässliche tägliche Bedienung | M01–M05, Beginn M21 | **erledigt** in dev12/dev13; M21 wartet auf den Eigentümer |
| B – klare Navigation und Arbeitslisten | **dev14** = M06 Einstellungen + M07 Teil 1 (sechs Bereiche, direkte Adressen, Zurück mit Filtern) – erledigt; **dev15** = M08-Rest, M09, M11 | dev15 als Nächstes |
| C – mehrere Projekte je Firma | M12 Katalog (mit Migration), danach M13 Chancen, M14 Briefings, M15 Revisionen, M16 | nach B; Modellumbau separat abgenommen, mit Kopie vorhandener Daten geprüft |
| D – Auftrag, Lernen, Anbindung | M17–M20, M24/M25 nach Pilotbedarf; M22/M23 parallel nach Fehlerbild; M10 bei wachsendem Bestand | später |

## Zuordnung der bisherigen Menüziele (M07, Stand dev14)

| Bisheriges Ziel | Neuer Ort | Adresse |
|---|---|---|
| Heute | Heute → Übersicht | `#/heute` |
| Aufgaben | Heute → Aufgaben | `#/heute/aufgaben` |
| Kontakt & Termine | Heute → Kontakt & Termine (Einzelfälle zusätzlich in der Firmenakte) | `#/heute/kontakt-termine` |
| Firmen finden | Finden → Suche & Sichtung | `#/finden` |
| Import & Prüfung | Finden → Import & Prüfung | `#/finden/import` |
| Firmen-Berichte | Finden → Recherche & Berichte; je Firma im Reiter „Recherche“ der Akte | `#/finden/recherche` |
| URL-Recherche, Website-Scoring, Kaufsignale | Finden → eigene Reiter | `#/finden/url-recherche` usw. |
| Leads | Firmen → Firmenliste | `#/firmen` (Filter: `?suche=…&phase=…`, Firma: `?firma=…`) |
| Pipeline | Firmen → Pipeline | `#/firmen/pipeline` |
| Datenqualität & System | aufgeteilt: Firmen → Datenpflege (`#/firmen/datenpflege`); wiederkehrende Recherche unter Finden → Recherche & Berichte; alles Übrige unter Einstellungen | – |
| Angebote & Preise | Angebote; Kalkulationsgrundlagen und Katalog unter Einstellungen → Leistungen & Preise | `#/angebote`, `#/einstellungen?abschnitt=preise` |
| Rechnungen & Buchhaltung | Abrechnen | `#/abrechnen` |
| KI-Studio | Einstellungen → Erweiterte Werkzeuge | `#/einstellungen/ki-studio` |
| Sales-Playbook | „Hilfe & Gesprächsleitfaden“ unten in der Seitenleiste | `#/einstellungen/hilfe` |

## Abnahmefälle aus dem Review

| Nr. | Aufgabe | Stand |
|---|---|---|
| T01 | Nach dem Start die wichtigste Aufgabe finden | teilweise – Tagesplan ehrlicher (dev13); Fokusliste mit M08 |
| T02 | Neue Firma nur mit Namen erfassen | **bestanden** (dev13, Browser-Test) |
| T03 | Bestehende Firma öffnen | **bestanden** (dev13, Browser-Test) |
| T04 | Notiz eingeben und Escape drücken | **bestanden** (dev13, Browser-Test) |
| T05 | Aus gefilterter Liste in die Firma und zurück | **bestanden** (dev14, Browser-Test: Filter und Firma in der Adresse, Zurück schließt die Firma) |
| T06 | Rückruf nach erfolglosem Versuch planen | Funktion seit dev3; als Szenario noch nicht geprüft |
| T07–T13 | Projektanfrage, zwei Chancen, Medien-/Softwareangebot, Revision, Übergabe, Zeitüberschreitung | offen (Etappen C und D) |
| T14 | Recherche während eines Fehlers wieder aufnehmen | Kernabläufe seit Masterplan 2.0; vollständig mit M23 |
| T15 | Sicherung in getrennte Testinstallation zurückspielen | Wiederherstellung vorhanden; als Szenario mit Etappe C prüfen |

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
