# Sprint-Bericht Phase 1 – Datenbasis (v1.3)

Gemäß Masterplan v2 (`docs/MASTERPLAN_V2.md`) und Master-Prompt v2.0, Sprint 1.

## Was ist tatsächlich implementiert?

| Baustein | Umsetzung | Dateien |
|---|---|---|
| Belegmodell | Tabelle `company_facts` (Wert, Quelltyp, URL, wörtlicher Beleg, Verfahren, Qualität, Fund-/Prüfdatum, Status ungeprüft/bestätigt/verworfen/veraltet). Firmenspalten im Lead: offizieller Name, Rechtsform, Anschrift, Register, USt-IdNr., allgemeine Telefonnummer/E-Mail, Impressums-URL, Prüfzeitpunkt. Statuswechsel aktualisiert den Lead; „veraltet“/„verworfen“ entfernt den Wert wieder. | `company_data.py` |
| Sperrliste | Tabelle `suppression_list` (Domain, Firmenname, Register, E-Mail). Wird automatisch gefüllt, wenn ein Lead gesperrt wird, ein Widerspruch im Gespräch protokolliert wird oder ein gesperrter Lead gelöscht wird. Geprüft bei: Lead anlegen, CSV-Import, URL-Recherche-Übernahme, Lead-Finder, Impressumsprüfung (vor dem Abruf und nach der Extraktion). Aufheben nur mit Begründung, protokolliert. | `company_data.py`, `server.py`, `quickscan.py`, `lead_finder.py`, `sales_workspace.py` |
| Dubletten | Über Domain, Registergericht + Nummer und normalisierten Namen (Rechtsform-unabhängig). | `company_data.find_duplicate` |
| Impressum-Extraktor | Impressumslink über Linktext/Pfad (auch „Legal Notice“, „Rechtliches“, PDF-Links), Standardpfade als Rückfall, nur dieselbe Firmen-Domain. HTML und einfache PDF (Flate, ohne Zusatzpakete). Felder mit wörtlichem Beleg; fehlende Angaben `null`. Erkennt mehrere Gesellschaften (z. B. Komplementär-GmbH samt eigener Registernummer), prüft die USt-IdNr.-Prüfziffer, löst „[at]/[dot]“ auf, unterscheidet Telefon und Fax, kennzeichnet allgemeine Nummern als „keine Durchwahl, keine Werbeeinwilligung“. Script-/Style-Inhalte werden ignoriert. | `imprint.py` |
| Sicherheit beim Abruf | Bestehende Prüfungen wiederverwendet: nur öffentliche DNS-Ziele (keine internen/privaten IPs), robots.txt je URL, jede Weiterleitung neu geprüft und nur innerhalb der Firmen-Domain, max. 4 Weiterleitungen, Größenlimit 2 MB (HTML) / 5 MB (PDF), Timeout, Pause zwischen Abrufen derselben Domain. | `imprint.http_fetch` |
| Batch-Modus | 1–100 Domains als Liste oder CSV (Spalte website/url/domain, optional firma), Eingabe-Dubletten entfernt, ungültige Zeilen gemeldet. Parallelität 1–3, Pausieren/Fortsetzen/Abbrechen/Fehlgeschlagene erneut. Nach Neustart werden laufende Aufträge pausiert und sind fortsetzbar. Einzelfehler brechen den Lauf nicht ab (Fehlerprotokoll je Eintrag). | `imprint_batch.py` |
| Prüfwarteschlange & Übernahme | Pro Domain: Felder mit Beleg und Qualität, Feldauswahl, Wahl der Gesellschaft, Personen optional. „Als neuen Lead“ (mit Dublettensperre) oder „Lead ergänzen“ (bestehende Werte bleiben, außer „überschreiben“ ist gewählt). Nicht gewählte Felder werden als ungeprüfte Belege gespeichert. Aktivität und Audit-Eintrag. | `imprint_batch.review_item` |
| Datenschutz-Nachweise | Je übernommener Person: Datenkategorien, Zweck, Rechtsgrundlage (Art. 6 Abs. 1 lit. f), Quelle, Löschfrist (2 Jahre), Art.-14-Status; Textbaustein für die Art.-14-Information; Kennzeichnung „überfällig“ nach 30 Tagen. Personen werden als Kontakt „Quelle geprüft, Rolle laut Impressum“ angelegt, nicht als bestätigte Entscheider. | `company_data.py` |
| Automatische Sicherung | Erkennt der Start eine ältere Datenbankversion, wird vor der Migration automatisch ein Backup angelegt (`PRAGMA user_version`). | `server.backup_before_migration` |
| Oberfläche | Neuer Bereich „Datenprüfung“: Eingabe, Auftragsliste mit Fortschritt, Prüfwarteschlange, Sperrliste, Datenschutz-Nachweise. Im Lead: „Firmendaten & Belege“ mit Prüfstatus je Feld und Knopf „Impressum prüfen“. | `public/datacheck.js`, `index.html`, `style.css` |
| Rechnungsanbindung | Rechnungsempfänger werden aus geprüften Firmendaten vorbelegt (Name, Straße, PLZ, Ort, USt-IdNr.). | `accounting.buyer_defaults` |

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **138 Tests grün** (22 neu in `tests/test_phase1_datenbasis.py`, 1 neu in `tests/test_launcher.py`, alle bisherigen weiter grün).
- Abgedeckt: verschiedene Impressumsformate (GmbH & Co. KG mit Komplementärin, UG im Fließtext mit mailto, e.K. mit Inhaber, englisches Imprint mit Aufsichtsrat, Minimal-Impressum), PDF-Impressum, Prüfziffer, Linkerkennung ohne `/impressum`, fremde Domains ignoriert, Website nicht erreichbar, kein Impressum, Batch mit gemischten Ergebnissen, CSV-Varianten, Limits, Pause/Fortsetzen/Neustart, Dubletten über Register, Übernahme ohne Überschreiben, Wahl einer anderen Gesellschaft, Verwerfen, Sperrliste über alle Importwege und nach Löschen, Register-Treffer erst nach Extraktion, Aufheben nur mit Begründung, Feldstatus, HTTP-Ablauf, Backup vor Migration.
- Browser-Durchlauf (Playwright) mit denselben fiktiven Testseiten: Auftrag mit 5 Domains, Übernahme, Firmendaten im Lead, Sperren → Sperrliste, Datenschutz-Nachweise, Mobilansicht 390 px. Keine Konsolenfehler, kein horizontaler Überlauf.

## Was funktioniert?

Alles oben Genannte mit fiktiven Testdaten und einer simulierten Netzwerkschicht.

## Was ist noch ungetestet?

- **Echte Websites.** Die Abrufe liefen gegen einen Stub, das ist **kein Live-Test**. Die Cloud-Entwicklungsumgebung sperrt ausgehende Verbindungen zu beliebigen Websites. Bitte auf dem eigenen Rechner einen Batch mit 10–20 echten Firmendomains laufen lassen; abweichende Impressumsformate werden dann gezielt nachgeschärft.
- Websites, deren Impressum nur per JavaScript nachgeladen oder als Bild dargestellt wird, werden als „kein Impressum“ gemeldet (kein Browser-Rendering im Batch, bewusst schnell und schonend).
- PDFs mit eingebetteten Spezialschriften liefern oft keinen lesbaren Text („PDF ohne auslesbaren Text – manuell prüfen“).

## Welche technischen oder rechtlichen Grenzen bestehen?

- Regeln statt KI: sehr ungewöhnliche Impressumsformate können Felder verfehlen. Ein fehlendes Feld ist „unbekannt“, nicht „falsch“. Ollama-Ergänzung ist für eine spätere Phase vorgesehen.
- Impressumsangaben dienen der Erreichbarkeit – **keine Einwilligung** in Werbe-E-Mails oder -Anrufe (§ 7 UWG).
- Personendaten: Rechtsgrundlage berechtigtes Interesse ist eine Abwägung im Einzelfall; Art.-14-Information ist Pflicht. Die rechtliche Endabstimmung liegt beim Nutzer.
- Registernummern sind nur zusammen mit dem Gericht eindeutig; Registerabgleich ohne Gericht findet daher nicht statt.

## Was ist als Nächstes sinnvoll?

1. **Live-Batch auf dem eigenen Rechner** mit echten Zieldomains und Rückmeldung der Fehlerkennungen (kurzer Zyklus).
2. **Phase 2 – Website-Bedarfs-Scorer v2:** gerenderte Seiten und Screenshots (Desktop/Mobil), Ladezeit, defekte Links, Rubriken mit Teil-Scores und „Datenlage unzureichend“. Baut direkt auf den Firmendaten und Belegen aus Phase 1 auf.
