# Sprint-Bericht Phase 3 – Buying Signals (v1.5)

Grundlage: Masterplan v2 und Master-Prompt v2.0, Module 4 (Handelsregister-Monitor), 5 (Job-Signal-Analyzer) und 7 (Signal-Korrelation), Sprint 3.

## Was ist tatsächlich implementiert?

| Baustein | Umsetzung |
|---|---|
| **Registerereignisse** | Bekanntmachungen werden **manuell importiert**: Text einfügen (mehrere Bekanntmachungen durch Leerzeilen getrennt) oder CSV mit den Spalten datum, gericht, registernummer, firma, text, url. Es gibt **keinen Register-Scraper**, denn eine kostenlose Einsicht erlaubt keine automatisierte Massenauswertung. Erkannt werden Gericht, Registernummer, Firma, Veröffentlichungsdatum und der Typ: Neueintragung, Umbenennung, Wechsel in Geschäftsführung oder Prokura, Sitzverlegung bzw. neue Anschrift, Strukturänderung (Verschmelzung, Formwechsel, Kapital) sowie Auflösung, Löschung oder Insolvenz als Gegenhinweis. Bei Neueintragungen gelten genannte Geschäftsführer, Anschrift und Kapital nicht als „Änderung“. |
| **Datenminimierung** | Geburtsdaten und E-Mail-Adressen werden vor dem Speichern aus den Bekanntmachungstexten entfernt. Aus Stellenanzeigen werden E-Mail-Adressen und Telefonnummern entfernt. |
| **Zuordnung** | Firmen werden über Registergericht und Nummer oder den normalisierten Namen einem Lead zugeordnet. Signale ohne Lead bleiben sichtbar und lassen sich manuell zuordnen. Firmen auf der Sperrliste werden gekennzeichnet. |
| **Stellenanzeigen** | Drei Quellen: (1) die **Karriereseite** auf der eigenen Domain der Firma, bevorzugt mit strukturierten schema.org-Stellendaten (JobPosting) inklusive Veröffentlichungs- und Ablaufdatum, ersatzweise mit erkennbaren Stellentiteln; (2) der **offizielle Personio-XML-Feed**; (3) **manueller Import** als Text oder CSV. Fremde Jobportale werden nicht gelesen, Indeed- oder StepStone-Scraper gibt es nicht. Bekannte Bewerbermanagement-Domains sind nur erlaubt, wenn die Karriereseite der Firma auf sie verlinkt. |
| **Job-Analyse** | Drei Bereiche mit Begriffslisten: Prozessdigitalisierung, Web & Marketing, Software & Anwendungen. Ein Begriff im Titel zählt stärker als im Text. Jedes Job-Signal enthält Stellentitel, Quelle, Veröffentlichungsdatum, erkannte Begriffe als Beleg, mögliche Relevanz, **Gegenargumente** und Gesprächsfragen. Gegenargumente sind immer „Eine Stelle beweist keinen externen Bedarf“ und „Inhouse statt Agentur“, außerdem bei Bedarf „Anzeige älter als 60 Tage“ oder „Ausschreibung abgelaufen“ (dann als Gegenhinweis). Stellen ohne Agenturbezug (z. B. Lager) erzeugen kein Signal. |
| **Dubletten & Zeitlogik** | Jede Bekanntmachung bzw. Anzeige erhält einen Schlüssel; ein erneuter Import zählt als Dublette, ein erneuter Scan aktualisiert nur „zuletzt gesehen“. **Dasselbe Ereignis aus mehreren Quellen** (z. B. Text und CSV, oder Karriereseite und manuelle Anzeige) wird innerhalb von 30 Tagen zu einem Signal mit mehreren Quellen zusammengeführt. Veröffentlichungs- und Funddatum sind getrennt. Neue Signale sind markiert. Alte Signale werden nie automatisch gelöscht, sondern geringer gewichtet und ab einem Jahr als „älter als 1 Jahr“ gekennzeichnet. |
| **Korrelation** | Pro Lead werden Register- und Stellen-Signale, das manuelle Lead-Signal und die letzte Website-Bewertung (Bereich ≥ 50, mit auffälligen Befunden) zu vier Themen verknüpft: Markenauftritt, Website/Anfragen, Prozessdigitalisierung, Wachstum. Jede Hypothese ist als „Möglicherweise …“ formuliert und enthält Stärke („mehrere unabhängige Hinweise“ nur ab zwei Quellenarten), einen nach Aktualität gewichteten Wert, die zusammenhängenden Hinweise mit Datum, Gegenhinweise, Widersprüche, was zur Bestätigung fehlt, Gesprächsfragen und passende Pakete. **Widersprüche:** Auflösung oder Löschung begrenzt alle Hypothesen auf höchstens 10; abgelaufene Anzeigen werden genannt; geringes Website-Potenzial erscheint als Gegenhinweis. Ausdrücklicher Hinweis: Korrelation ist keine Kausalität. |
| **Anbindung Scoring** | Der Wert „Projektanlass“ der Website-Bewertung nutzt jetzt echte, datierte Kaufsignale: das jüngste Pro-Signal, gewichtet nach Aktualität. Liegt eine Auflösung vor, ist der Wert 0. Bestätigte Signale lassen sich als Projektanlass in den Lead übernehmen; vorhandene Angaben werden dabei nicht überschrieben. |
| **Datenmodell** | `register_events`, `job_signals`, `buying_signals` (normalisiert, mit Quellenliste), `signal_correlations` und `signal_scans`. Vor der Migration wird automatisch ein Backup angelegt (Schema 15). |
| **Oberfläche** | Neuer Bereich „Kaufsignale“ mit Kennzahlen, Import von Registerbekanntmachungen und Stellenanzeigen, Prüfung von Karriereseiten (bis zu 20 Leads), Signal-Feed mit Filter, Prüfstatus und Zuordnung sowie Hypothesen je Firma. Im Lead-Dialog: „Kaufsignale & Hypothesen“. |

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **162 Tests grün**, davon 13 neu in `tests/test_phase3_signals.py`. Ohne Playwright werden 2 Browser-Tests aus Phase 2 übersprungen.
- **Abgedeckt:**
  - Register: Erkennung und Klassifikation, Neueintragung ohne falschen Geschäftsführerwechsel, Zuordnung über das Register, entfernte Geburtsdaten
  - doppelte Registerereignisse beim erneuten Import, dasselbe Ereignis aus Text und CSV zusammengeführt, Sperrliste
  - Jobs: Klassifikation mit Pro und Contra, alte, abgelaufene und undatierte Anzeigen, Karriereseite mit JSON-LD, Personio-Feed, Rückfall auf Standardpfade, fremdes Portal ignoriert
  - Scan-Warteschlange, Kontaktdaten entfernt, Dublette über Karriereseite und manuellen Import, erneuter Scan ohne neue Signale
  - Korrelation: unabhängige Quellen mit Gegenhinweisen und fehlender Bestätigung, Widerspruch durch Auflösung, Einzelquelle schwach, alte Signale schwächer gewichtet, kein Kausalitätsanspruch
  - Anbindung ans Scoring, Übernahme nur bestätigter Signale, Zuordnung zu einem Lead, HTTP-Ablauf
- **Klickdurchlauf im Browser:** Bekanntmachungen einfügen, Karriereseiten prüfen, manuelle Anzeige erfassen (mit Zusammenführung), Hypothesen, Lead-Dialog, Mobilansicht 390 px. Der Durchlauf hat einen echten Fehler gefunden und er ist behoben: Die Tab-Steuerung der Buchhaltung reagierte auf alle Tabs der Seite. Danach keine Konsolenfehler und kein horizontaler Überlauf mehr.

## Was ist noch ungetestet?

- **Echte Karriereseiten und echte Bekanntmachungstexte.** Die Abrufe liefen gegen einen Stub mit fiktiven Seiten; das ist **kein Live-Test**. Bitte lokal einige Leads per „Karriereseiten prüfen“ durchlaufen lassen und 5–10 echte Bekanntmachungen aus dem Registerportal einfügen. Abweichende Formate schärfe ich dann nach.
- Karriereseiten, die Stellen nur per JavaScript nachladen (z. B. eingebettete Widgets), werden ohne strukturierte Daten nicht erkannt. Dann bleibt der manuelle Import.
- Personio ist als einziger Bewerbermanagement-Feed angebunden. Andere Anbieter (softgarden, join.com u. a.) werden nur gelesen, wenn ihre Seite strukturierte Stellendaten enthält.

## Welche technischen oder rechtlichen Grenzen bestehen?

- Kein automatisierter Abruf aus Handelsregister oder Unternehmensregister; die Bekanntmachungen müssen aktiv kopiert werden. Der Grund ist die Nutzungsordnung (laut Sekundärquelle höchstens 60 Abrufe pro Stunde, keine Massenabfragen).
- Die Erkennung arbeitet regelbasiert. Ungewöhnliche Formulierungen fallen unter „Sonstige Bekanntmachung“ und erfordern eine manuelle Prüfung.
- Namen der Geschäftsführung bleiben im Bekanntmachungstext erhalten (Geburtsdatum und Wohnort werden entfernt). Für eine Übernahme als Kontakt gelten weiter die Regeln aus Phase 1: Datenschutz-Nachweis und Art.-14-Information.
- Signale und Hypothesen sind **keine Kontakterlaubnis** und keine Aussage über Kaufbereitschaft oder Budget.

## Was ist als Nächstes sinnvoll?

1. **Live-Test** mit echten Karriereseiten und Bekanntmachungen, danach die Begriffslisten nachschärfen.
2. **Phase 4 – Research Command Center:** URL-Recherche, Lead-Finder, Datenprüfung, Website-Scoring und Kaufsignale in einer gemeinsamen Arbeitsfläche zusammenführen, mit einer Ansicht der priorisierten Firmen und einer zentralen Quellenansicht.
