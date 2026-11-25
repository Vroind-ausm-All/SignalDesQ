# Changelog

## 2.0.0-dev66 – Recherche: Website-Zuordnung mit mehreren Merkmalen, Firmen-Bericht auch ohne Website

- **Website-Suche – „Domain gibt es nicht“ ist kein Fehler mehr:** Geratene Domains ohne DNS-Eintrag zählen nicht mehr als fehlgeschlagener Abruf. Treffer landen dadurch seltener grundlos auf „Prüfung fehlgeschlagen“. Funktioniert die Namensauflösung gar nicht (z. B. Firmennetz nur mit Proxy), meldet SignalDesk das ausdrücklich, statt „nicht gefunden“ zu schließen.
- **Website-Suche – mehr und bessere Kandidaten:** Zuerst wird die Domain der E-Mail-Adresse aus OpenStreetMap geprüft (Freemail wie gmail.com oder web.de zählt nicht), danach weitere Schreibweisen: mit Rechtsform (`…-gmbh.de`), umgekehrte Wortfolge (`huber-elektro.de`), ohne „e“ bei Umlauten, Umlaut-Domain. Reine Gattungsbegriffe wie `elektro.de` werden nicht mehr abgefragt.
- **Website-Suche – Marke und Firmenname:** Zugeordnet wird jetzt über Name, Anschrift, Telefon, E-Mail-Domain und Registernummer. Heißt der Betrieb im Impressum anders (z. B. „Elektro Huber“ ↔ „Huber Elektrotechnik e.K.“), passen aber Anschrift und Telefon, gibt es einen **Vorschlag** zum Bestätigen. Betriebe ohne Handelsregister können jetzt **belegt** sein, wenn Name, vollständige Anschrift und Telefon oder E-Mail-Domain übereinstimmen. Andere Registernummer, Rechtsform, PLZ oder Ort schließen eine Zuordnung weiterhin aus.
- **Datensparsam:** Für den Abgleich speichert SignalDesk weder Telefonnummern noch E-Mail-Adressen, nur die E-Mail-Domain und einen Prüfwert der Telefonnummer. Für gesperrte Firmen nichts.
- **Firmen-Bericht auch ohne Website:** Neuer erster Schritt „Website finden & zuordnen“. Eine belegte Website wird in das leere Feld eingetragen, danach läuft der Bericht vollständig. Einen Vorschlag bestätigst du im Bericht oder in der Firmenakte mit „Passt“ oder „Passt nicht“. Abgelehnte Domains werden nicht erneut vorgeschlagen, Domains auf der Sperrliste nie eingetragen.
- **Firmen-Bericht „Auf einen Blick“:** Kurzfazit oben im Bericht mit Kernfakten und Herkunft, den wichtigsten Hinweisen mit Beleg, den Lücken (was fehlt und warum), dem Kontaktstatus („gefunden“ ist nicht „erlaubt“) und dem Alter des Berichts. Nach 90 Tagen gibt es den Hinweis „bitte neu erstellen“.
- Bericht: [BERICHT_RECHERCHE_DEV66.md](docs/BERICHT_RECHERCHE_DEV66.md). Tests: neu `test_v2_website_matching.py` (19, inkl. Migration Schema 48 → 49), `test_v2_report_glance.py` (13), `e2e/test_report_glance_browser.py`. Die Wirkung auf die Trefferquote ist noch nicht an echten Firmen gemessen (Recherche-Benchmark).

## 2.0.0-dev65 – Welle 6: Wiederherstellung, Leerlauf, Referenzliste; Befunde der Sicherheitsprüfung (SDQ-029 bis SDQ-043)

- **Neu für Betreiber – ganze Installation wiederherstellen:** `betreiber --root NEUER_ORDNER gesamt-wiederherstellen SATZ --ja` stellt Verzeichnis und alle Organisationen aus einem Sicherungssatz in einem leeren Ordner wieder her und prüft dabei Prüfsummen, Unversehrtheit und Zeilenzahlen. Ein Ordner mit Inhalt wird nie überschrieben.
- **Neu – Sicherung an einen zweiten Ort:** `betreiber sicherung-kopieren NAME --nach ORDNER` kopiert einen Satz z. B. auf einen eingehängten Datenträger und rechnet dort alle Prüfsummen nach. Vorhandenes wird nicht überschrieben.
- **Neu – Abmelden nach Leerlauf** (Server für mehrere Organisationen): Nach 60 Minuten ohne Aktivität ist eine neue Anmeldung nötig. Der Betreiber stellt die Zeit mit `einstellung leerlauf_minuten` ein (5 bis 720, 0 = aus). Einzelplatz und Team-Betrieb bleiben unverändert.
- **Tarif:** Solange eine Organisation nur lesbar ist, ruhen ihre wiederkehrenden Aufträge.
- **Recherche-Benchmark:** `research_benchmark.py import-table` wandelt die ausgefüllte Tabellenvorlage (xlsx oder CSV) in eine Referenzliste um und prüft sie.
- **Sicherheit – Befunde der externen Prüfung vom 24.11.2026** (Einzelheiten: [SICHERHEITSPRUEFUNG_2026-11-24.md](docs/SICHERHEITSPRUEFUNG_2026-11-24.md)):
  - Eine Einladung kann nur das Konto mit der eingeladenen E-Mail-Adresse annehmen.
  - Passwortwechsel, Sperre und Änderungen am zweiten Faktor beenden alle Sitzungen des Kontos, auch auf anderen Geräten und in anderen Organisationen.
  - Kalender- und Postfachzugänge richtet nur die Verwaltung ein; bei einem neuen Server oder Konto wird das gespeicherte Passwort verworfen.
  - Recherche-Einstellungen gelten je Organisation. Im Server für mehrere Organisationen sind der ältere Abruf, der Browser, lokale Kalender-/Postfachserver und das Wiederherstellen per Upload gesperrt.
  - Passwörter werden stärker gehasht und beim nächsten Login automatisch umgestellt.
  - DATEV-Export ohne Formelanfänge; Login-Bremse hinter dem Proxy je Client (`--vertrauter-proxy`); `/readyz` von außen zwischengespeichert; Protokoll-Anker (`protokoll-anker`, `protokoll-pruefen --anker`).
  - cryptography 50.0.2 im Team-Paket; ohne Lockdatei wird nichts installiert; CI-Aktionen fest gepinnt.
- **Fehlerbehebung (Windows):** Der Server für mehrere Organisationen liest bei abgelehnten Anfragen (z. B. fremde Herkunft) den Anfragekörper zu Ende, statt die Verbindung hart abzubrechen.
- Tests: neu `test_sdq029_betrieb_more.py` (18 Fälle) und `test_sdq033_pruefbericht.py` (21 Fälle).

## 2.0.0-dev64 – Welle 5: E-Rechnung prüfen, DATEV, Ersteinrichtung, Registrierung und Tarif (SDQ-024 bis SDQ-028)

- **Neu – E-Rechnung prüfen:** In jeder Rechnung prüft „E-Rechnung prüfen“ die XRechnung gegen 63 Regeln aus EN 16931 und XRechnung 3.0 (Pflichtangaben, Summen, Steuer, Codelisten, IBAN-Prüfziffer, Kontaktangaben). Auch importierte E-Rechnungen werden so geprüft. Die Prüfung ersetzt den offiziellen KoSIT-Validator nicht und sagt das auch.
- **Neu – DATEV-Buchungsstapel:** Unter „Steuer & Export“ Beraternummer und Mandantennummer eintragen, dann die Datei im DATEV-Format (EXTF 700, SKR03) herunterladen. Ein Probeimport in DATEV ist noch nicht erfolgt – bitte mit der Steuerberatung einen Testimport vereinbaren. Ausgaben nach § 13b sind als „prüfen“ markiert.
- **Ersteinrichtung:** Der erste Schritt unter „Erste Schritte“ heißt jetzt „Rechnungsdaten eintragen“ und nennt, was für eine gültige (E-)Rechnung noch fehlt.
- **Neu für Server mit mehreren Organisationen – Registrierung und Einladungen:** Wenn der Betreiber es freischaltet, kann sich eine neue Organisation unter `/anmelden` selbst registrieren (Bestätigung per Link). Die Verwaltung einer Organisation lädt Mitglieder per E-Mail-Adresse ein, zieht Einladungen zurück und entfernt Mitglieder. **SignalDesk verschickt dabei keine E-Mails:** Die Nachrichten liegen im Postausgang des Servers, der Betreiber gibt den Link weiter.
- **Neu – Testphase und Tarif:** Selbst registrierte Organisationen starten mit einer Testphase. Danach ist die Organisation nur lesbar (Ansehen und Export gehen weiter, nichts wird gelöscht), bis der Betreiber den Tarif freischaltet. Es gibt keinen Zahlungsanbieter und keine Preise im Programm.
- **Für Betreiber:** neue Befehle `einstellung`, `konto-email`, `tarif`, `postausgang` und `anlegen … --admin KONTO`.
- Tests: neu `test_sdq024_einvoice_check.py` (10), `test_sdq025_datev.py` (5), `test_sdq027_signup.py` (10), `e2e/test_sdq024_invoice_check_browser.py`, `e2e/test_sdq027_signup_browser.py`; Ersteinrichtung in `test_v2_focus.py` erweitert.

## 2.0.0-dev63 – Betrieb und Sicherheit für den Server mit mehreren Organisationen (SDQ-017 bis SDQ-023)

- **Neu – Zwei-Faktor-Anmeldung:** Unter `/anmelden` → „Zwei-Faktor-Anmeldung“ verbindest du dein Konto mit einer Authenticator-App (zeitbasierte Codes, RFC 6238). Danach fragt SignalDesk nach dem Passwort einen Code ab; vorher gibt es weder die Liste der Organisationen noch Zutritt. Jeder Code gilt nur einmal. Dazu gibt es zehn Wiederherstellungscodes für den Fall, dass das Telefon fehlt. Der Betreiber kann den zweiten Faktor für alle vorschreiben (`zwei-faktor-pflicht an`); wer ihn noch nicht hat, richtet ihn bei der nächsten Anmeldung ein.
- **Sperre nach Fehlversuchen bleibt bestehen:** Fünf falsche Passwörter oder Codes sperren das Konto für 15 Minuten, auch über einen Neustart des Servers hinweg.
- **Neu – Protokoll der Verwaltung:** Anmeldungen, Fehlversuche, Konten, Mitgliedschaften, Organisationen, Sicherungen, Exporte und Änderungen am zweiten Faktor werden mit Zeit, Handelndem und (bei Anmeldungen) IP-Adresse festgehalten. Eine Hash-Kette zeigt, wenn ein Eintrag verändert oder entfernt wurde (`protokoll-pruefen`).
- **Neu – Sicherung aller Organisationen mit Wiederherstellungstest:** `sichern --verschluesselt --pruefen` sichert das Verzeichnis und jede Organisation (auch archivierte) und prüft den Satz sofort: Prüfsummen, Entschlüsseln, Unversehrtheit, Zeilenzahlen und Migration auf das aktuelle Schema. Einzelne Organisationen lassen sich mit `zurueckspielen` wiederherstellen, ohne die anderen zu berühren. Es wird nichts automatisch gelöscht.
- **Neu – Verschlüsselter Export:** `export … --out name.zip.sdenc --verschluesselt` (AES-256-GCM). Entschlüsseln mit `python -m sales_tool.backup_crypto entschluesseln`.
- **Neu – Betrieb:** `/healthz` und `/readyz` für Überwachung und Proxy, ein Betriebsprotokoll mit einer JSON-Zeile je Anfrage (ohne Cookies, Abfragen und IP-Adressen) und eine Anfrage-Nummer in jeder Antwort. Der Dienst beendet sich bei `SIGTERM` sauber und weicht nicht still auf einen anderen Port aus.
- **Neu – Serverpaket:** `deploy/` mit gehärteter systemd-Dienstdatei, täglichem Sicherungs-Timer, Beispielen für Caddy und nginx, dazu das Betriebshandbuch [BETRIEB_SERVER.md](docs/BETRIEB_SERVER.md). Die Verwaltung heißt jetzt `python -m sales_tool.betreiber` und ist damit im Release-Paket enthalten; `tools/organisationen.py` funktioniert weiter.
- **Fehlerbehebung:** Kopien in Sicherungssätzen werden als einzelne Datei ohne Schreibprotokoll (WAL) abgelegt. Sonst wären spätere Änderungen an einer Kopie an der Prüfsumme vorbeigegangen.
- Die lokale Einzelplatz-Installation ist unverändert.
- Tests: neu `test_sdq017_operations.py` (16 Fälle), `test_sdq021_security.py` (20 Fälle), `test_sdq020_deploy.py` (6 Fälle) und `e2e/test_sdq021_two_factor_browser.py`.

## 2.0.0-dev62 – Mehrere Organisationen mit zentraler Anmeldung (SDQ-014 bis SDQ-016)

- **Neu – Betrieb für mehrere Organisationen:** `python -m sales_tool.multi_server --root …` bedient alle Organisationen eines Verzeichnisses, jede mit eigener Datenbank. Die Anmeldung erfolgt zentral unter `/anmelden`; wer zu mehreren Organisationen gehört, wählt dort und kann jederzeit wechseln („Organisation · wechseln“ unten in der Seitenleiste).
- **Sicher getrennt:** Jede Anfrage gilt nur mit einer Sitzung, die in der Datenbank genau dieser Organisation angelegt wurde und deren Mitgliedschaft noch besteht. Rollen (Administration, Vertrieb, Buchhaltung, Lesen) gelten je Organisation. Entzug einer Mitgliedschaft und Sperre eines Kontos wirken mit der nächsten Anfrage.
- **Für Betreiber:** Konten anlegen, Organisationen zuordnen, Rollen ändern, Zugang entziehen, Konten sperren über `tools/organisationen.py`. Es werden keine E-Mails verschickt.
- **Fehlerbehebung:** Hinter einem TLS-Proxy lehnte SignalDesk Änderungen ab, weil die Seite von `https://` kam. Jetzt wird `X-Forwarded-Proto: https` berücksichtigt.
- Die lokale Einzelplatz-Installation ist unverändert.
- Tests: neu `test_sdq014_multi_tenant.py` (15 Fälle über HTTP) und `e2e/test_sdq014_multi_tenant_browser.py`.

## 2.0.0-dev61 – Welle 3: Mandantenfähigkeit vorbereiten (SDQ-010 bis SDQ-013)

- **Entscheidung:** Organisationen werden später über je eine eigene Datenbank getrennt (Architektur E10). Für die lokale Installation ändert sich nichts; Schema und Daten bleiben, wie sie sind.
- **Fehlerbehebung – geteilter Zustand zwischen Datenbanken:** Liefen mehrere Datenbanken im selben Programm, galt der Offline-Schalter für alle, Fehlversuche bei der Anmeldung sperrten denselben Benutzernamen überall, ein Impressum-Lauf blockierte den gleich nummerierten Lauf einer anderen Datenbank, und wiederkehrende Aufträge liefen nur für die erste. Das ist jetzt je Datenbank getrennt.
- **Neu für Betreiber:** `tools/organisationen.py` legt Organisationen mit eigener Datenbank an, listet und archiviert sie und erstellt einen Datenexport (Datenbankkopie, Bildschirmfotos, Verzeichnis der Tabellen) – ohne Zugangsdaten, Sitzungen und Passwort-Hashes.
- **Neu für Entwicklung:** Tabellenregister (`sales_tool/data_map.py`) mit Personenbezug und Aufbewahrungspflicht je Tabelle und ein Inventar aller SQL-Zugriffe ([DATENZUGRIFF.md](docs/DATENZUGRIFF.md)). Tests verhindern, dass andere Module Rechnungs- oder Anmeldedaten schreiben, und dass eine neue Tabelle ohne Einordnung entsteht.
- Tests: neu `test_sdq010_data_map.py` (11 Fälle) und `test_sdq011_tenancy.py` (18 Fälle, 5 davon gegen den alten Stand rot).

## 2.0.0-dev60 – Angebot als gestaltetes PDF (SDQ-009)

- **Neu:** Im geöffneten Angebot öffnet „Angebot als PDF ↗“ eine gestaltete Druckfassung im Stil deiner Rechnungen: Absender, Anschrift der Kundenfirma, Angebotsnummer, Gültigkeit, Positionen mit Festpreisen, Summen mit Umsatzsteuer, Leistungsumfang, Abnahme und Zahlungsplan. Über „Drucken / als PDF speichern“ entsteht das PDF.
- **Sicher versenden:** Die Druckfassung enthält nur, was der Kunde sehen soll – keine Kalkulation, keine Stundensätze, keine internen Notizen und keine Ansprechpartner. Solange das Angebot nicht freigegeben oder seit der Freigabe geändert ist, trägt es die Marke „ENTWURF“ und kein Unterschriftsfeld. Die freigegebene Fassung nennt ihren Stand und hat ein Feld für die Auftragserteilung.
- Der Markdown-Export bleibt unverändert.
- Tests: neu `test_sdq009_offer_print.py` (9 Fälle) und `e2e/test_sdq009_offer_print_browser.py`.

## 2.0.0-dev59 – Website-Suche schlägt keine fremde Gesellschaft mehr vor (SDQ-007)

- **Fehlerbehebung – falsche Website-Vorschläge:** Die Website-Suche in „Finden“ schlug bisher auch Seiten vor, deren Impressum eine andere Gesellschaft nennt: „Müller Elektro e.K.“ für die „Müller Elektro GmbH“, die Verwaltungs-GmbH für die GmbH & Co. KG, ein Impressum in Hamburg für eine Firma in Stuttgart oder „Elektro Schmidt GmbH“ für die „Elektro GmbH“. Jetzt schließt jeder harte Gegenbeleg einen Vorschlag aus: andere Registernummer, anderes Registergericht, anderer Name, andere Rechtsform, andere PLZ oder anderer Ort.
- **Nachvollziehbar:** Wird eine geprüfte Domain abgelehnt, steht der Grund im Beleg, z. B. „Gegenbeleg: mueller-elektro.de: andere Rechtsform im Impressum (Müller Elektro e.K.)“.
- Unverändert: „belegt“ nur bei gleicher Registernummer, gleichem Registergericht und gleichem Namen; „wahrscheinlich“ bleibt ein Vorschlag, den du bestätigst.
- Test: neu `test_sdq007_identity_levels.py` (7 Fälle, 6 gegen den alten Stand rot).

## 2.0.0-dev58 – Jede Datenquelle mit Lizenz, Aktualität, Limits, Kosten und eigener Fehlerrate (SDQ-008)

- **Neu auf den Quellenkarten** (Finden → „Einzelne Quelle gezielt abfragen“): Aktualität, Kosten und was deine eigenen Abfragen der letzten 30 Tage ergeben haben, z. B. „4 Abfragen, 25 % fehlgeschlagen, zuletzt erfolgreich am 24.11.2026 · 2 von 8 geprüften Treffern übernommen“. Limits der Quelle, Umgang mit Personendaten und der letzte Fehler stehen im Tooltip.
- **Neu für Auswertungen:** `GET /api/lead-finder/providers?days=30` liefert dieselben Angaben je Quelle, die Fehlerrate mit Vertrauensbereich und das Datum des letzten lokalen OpenStreetMap-Imports.
- Gemessen wird nur aus den Abfragen dieser Installation; es wird nichts zusätzlich abgerufen. Lizenz- und Limitangaben sind Stand November 2026 und nicht live geprüft – das steht auch in der Antwort.
- Tests: neu `test_sdq008_providers.py` (6 Fälle) und `e2e/test_sdq008_providers_browser.py`.

## 2.0.0-dev57 – Werkzeug für den Recherche-Benchmark (SDQ-006)

- **Neu:** `tools/research_benchmark.py` misst, wie vollständig und wie richtig SignalDesk die Firmen eines Gebiets findet: Vollständigkeit, Genauigkeit, Dubletten und vor allem falsch zugeordnete Websites und Registernummern, jeweils mit Vertrauensbereich. Anleitung, Format und vorgeschlagene Zielwerte in [RECHERCHE_BENCHMARK.md](docs/RECHERCHE_BENCHMARK.md), Vorlage unter `docs/bench/research/`.
- **Noch kein Ergebnis:** Dafür braucht es eine von Menschen geprüfte Referenzliste. Die mitgelieferten Testdaten sind erfunden; ein Bericht daraus beginnt mit „Synthetische Testdaten – kein Messergebnis“.
- Datenschutz: Referenz- und Lauf-Dateien enthalten nur Firmendaten; Felder wie E-Mail oder Ansprechpartner werden abgelehnt. Der Export liest die Datenbank nur und ruft nichts im Netz ab.
- Keine Änderung an Recherche, Datenmodell oder Oberfläche.

## 2.0.0-dev56 – Alle Browser-Tests laufen in der CI (SDQ-005)

- **Prüfung bei jedem Push:** Die CI führte bisher nur einen der 51 Browser-Tests aus. Jetzt laufen alle, auch die Regressionstests zu Teilabrechnung, Akte-Navigation, Rechnungs-Eingabeschutz und Passwortspeicher.
- **Kein stilles Überspringen:** Fehlt Playwright oder Chromium, wurden die Browser-Tests bisher übersprungen und der Lauf blieb grün. Neues `tools/run_e2e.py` zählt gefundene, gelaufene und übersprungene Tests; in der CI ist jeder übersprungene Test ein Fehler, und es müssen mindestens 52 Tests gefunden werden.
- **Fehlerbehebung – Adresse sprang aus der Akte (gefunden durch die volle Suite):** Wer die Akte über die Seitenleiste verließ und im selben Augenblick wieder eine Akte aufrief (Zurück, Link, eingegebene Adresse), sah die Akte, in der Adresse stand aber „#/firmen“. Ursache: Der Schließ-Check läuft einen Augenblick verzögert und hat die inzwischen neue Adresse überschrieben. Jetzt lässt er eine neue Adresse in Ruhe. Test: neu `e2e/test_sdq005_akte_close_race_browser.py`, gegen den alten Stand rot.

## 2.0.0-dev55 – Welle 1: Teilabrechnung, Akte und Rechnungsentwurf beim Wechseln, Passwörter nie im Klartext (SDQ-001 bis SDQ-004)

Erstes Arbeitspaket der Welle „Kritische Fehler und Sicherheitsgrundlagen“; neuer technischer Ausgangsstand in [PRODUCT_MATURITY_AUDIT.md](docs/PRODUCT_MATURITY_AUDIT.md).

- **Fehlerbehebung – der Rest eines Auftrags verschwand:** Ein angenommenes Angebot galt als berechnet, sobald irgendeine Rechnung daran hing – auch ein noch nicht festgeschriebener Entwurf oder eine Abschlagsrechnung über 40 %. Die übrigen 60 % fehlten dann unter „Abrechnen → Aus Angeboten berechnen“, im Potenzial auf „Heute“, in der Angebotsliste und im Abschluss-Schritt der Firmenakte.
- **Jetzt getrennt:** noch nicht abgerechnet · Rechnungsentwurf vorhanden · teilweise abgerechnet · vollständig abgerechnet · Rechnung storniert, und davon unabhängig Zahlung ausstehend · teilweise bezahlt · bezahlt. Nur festgeschriebene Rechnungen zählen; Entwürfe, Stornorechnungen und stornierte Rechnungen nicht. Vollständig ist ein Angebot nach einer festgeschriebenen Gesamt- oder Schlussrechnung oder wenn die Abschläge den Angebotsbetrag erreichen. Monatliche Leistungen laufen wie bisher über „Betreuung“.
- **Was du siehst:** Unter „Aus Angeboten berechnen“ steht z. B. „teilweise abgerechnet: 4.000,00 € von 10.000,00 € netto · 6.000,00 € netto noch abzurechnen“ mit dem Knopf „Schlussrechnung über den Rest“; liegt schon ein Entwurf vor, „Entwurf öffnen“. „Heute“ zählt beim Potenzial nur den Rest. Die Angebotsliste nennt als nächsten Schritt „Schlussrechnung: … netto offen“, die Akte „teilweise abgerechnet, … € netto offen“.
- Rein lesend: kein Schemawechsel, keine Änderung an Rechnungen, Festschreibung, Storno oder E-Rechnung.
- Tests: neu `test_sdq001_billing_state.py` (10 Fälle) und `e2e/test_sdq001_billing_state_browser.py`; `test_accounting.py` prüft jetzt, dass eine nur als Entwurf angelegte Schlussrechnung den Rest nicht ausblendet.
- **Fehlerbehebung – Akte blieb stehen (SDQ-002):** Wer in einer geöffneten Firmenakte in der Seitenleiste z. B. „Abrechnen“ wählte, sah in der Adresse, der Seitenleiste und den Reitern schon „Abrechnen“ – auf dem Bildschirm aber weiter die Akte. Jetzt schließt jeder Wechsel des Bereichs (Seitenleiste, Reiter, Sprünge aus „Heute“ oder in die Einstellungen) die Akte; Adresse und sichtbarer Bereich stimmen immer überein. „Zurück“ öffnet die Akte wieder, „Vor“ führt wieder in den Bereich.
- **Eingabeschutz beim Bereichswechsel:** Hast du in der Akte etwas geändert und nicht gespeichert, fragt SignalDesk vorher: Speichern · Weiter bearbeiten · Verwerfen. „Weiter bearbeiten“ bricht den Wechsel ab, die Adresse bleibt bei der Akte. Wechselt ein Programmteil die Ansicht von selbst, bleiben ungespeicherte Eingaben wie bisher im Arbeitsspeicher und kommen beim nächsten Öffnen der Firma zurück.
- Test: neu `e2e/test_sdq002_akte_navigation_browser.py` (alle sechs Bereiche, Reiter, Zurück/Vor, Direktlink, die drei Antworten der Rückfrage); gegen den alten Stand rot.
- **Eingabeschutz im Rechnungseditor (SDQ-003):** Hast du einen Rechnungsentwurf geändert und nicht gespeichert, fragt SignalDesk vor dem Wechsel des Bereichs, bei „← Rechnungen“, beim Öffnen einer anderen Rechnung und bei „＋ Neue Rechnung“: Speichern · Weiter bearbeiten · Verwerfen. „Speichern“ legt nur einen Entwurf ab und schreibt nie fest; „Verwerfen“ stellt den gespeicherten Stand wieder her. Beim Neuladen oder Schließen des Fensters fragt der Browser nach. Zurück/Vor auf „Abrechnen“ schließt einen geänderten Entwurf nicht mehr stillschweigend.
- **Angebotseditor:** Neuladen oder Schließen des Fensters fragt nach, solange ein Angebot ungespeicherte Positionen hat. Innerhalb von SignalDesk bleiben sie wie bisher im Arbeitsspeicher.
- Test: neu `e2e/test_sdq003_invoice_guard_browser.py` (alle drei Antworten, „← Rechnungen“, unveränderter Editor ohne Rückfrage, beforeunload); gegen den alten Stand rot.
- **Sicherheit – Passwörter nie mehr im Klartext (SDQ-004):** „Merken“ legte Kalender- und Postfach-Passwörter bisher unverschlüsselt in `zugangsdaten.json` ab. Jetzt nur noch im Passwortspeicher des Betriebssystems (Paket `keyring`, falls installiert; sonst Windows-DPAPI bzw. Linux-`secret-tool`, Passwort über die Standardeingabe). Gibt es keinen, steht statt des Häkchens „gilt bis zum Neustart“ – geschrieben wird dann nichts.
- **Altbestand:** Ein Eintrag aus `zugangsdaten.json` wird beim ersten Lesen in den sicheren Speicher übernommen und aus der Datei entfernt (leere Datei wird gelöscht). Ohne sicheren Speicher funktioniert er weiter, die Einstellungen zeigen aber einen gelben Hinweis; sobald du das Passwort neu eingibst oder „Passwort vergessen“ wählst, verschwindet der Klartext-Eintrag. Neues Passwort ersetzt das alte überall, „vergessen“ löscht es aus allen Speichern.
- Tests: neu `test_sdq004_credentials.py` (u. a. „kein Klartext irgendwo im Datenordner“, Übernahme des Altbestands, Speicher verweigert, Passwort nicht auf der Befehlszeile, DPAPI-Rundlauf unter Windows in der CI) und `e2e/test_sdq004_credentials_browser.py`. `test_v2_caldav.py` erwartete bisher die Klartext-Datei; jetzt prüft er das Gegenteil. Tests nutzen einen Ersatz-Speicher (`tests/cred_fake.py`) und berühren nie den echten Schlüsselbund.

## 2.0.0-dev54 – Firmenakte als Detailseite, überall „Firma“ statt „Lead“

Schritt 6 und damit Abschluss der Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](docs/ROADMAP.md)). Keine Funktion entfällt – was umgezogen ist, steht in [UI_BAUKASTEN.md, Abschnitt „Was wohin zog (Schritt 6)“](docs/UI_BAUKASTEN.md). Datenmodell, Kontaktsperre, Personen-Einschränkungen, Löschfristen, Fokusführung und Eingabeschutz arbeiten unverändert; am Server wurden nur Meldungstexte geändert.

- **Kopf der Akte wie jede Detailseite:** „← Firmen“ (bzw. „← Heute“, „← Pipeline“ – dorthin, wo du herkamst, mit denselben Filtern), der Firmenname, die Phase als Pille, Ort · Branche und genau ein grüner Knopf. Der heißt meist **„Gespräch notieren“** und öffnet das Protokoll mit vorgewählter Art „Gespräch“; bei einer gesperrten oder verlorenen Firma „Notiz erfassen“, nach einem Gewinn ohne Rechnung „Rechnung schreiben“. Darunter die fünf Reiter; beim Öffnen hat „Überblick“ den Fokus wie bisher.
- **„Vereinbart“ steht oben:** der nächste Schritt aus den Stammdaten mit Fälligkeit (rot überfällig, gelb heute) und Herkunft (eingetragen unter Stammdaten, letztes Gespräch am …). „ändern“ springt ins Feld. Was das Programm vorschlägt („Firmen-Bericht erstellen“ usw.), steht getrennt darunter als Klappzeile **„Empfehlung“** – mit der Aktion als Textknopf und, aufgeklappt, den sieben Ablaufschritten.
- **Chancen im Überblick:** Liste Chance · nächster Schritt · fällig · Status · Wert; ein Klick öffnet die Chance im Reiter „Bedarf & Angebot“.
- **Klappzeilen mit Kurzstand:** Bedarf (bestätigen, Angebot aus bestätigtem Bedarf), Passung (vollständige Bewertung mit Qualifizierung und Erreichbarkeit), Website-Bewertung, Quellen & Belege (Impressumsdaten, Website-Vorschlag, Belegabdeckung – öffnet sich von selbst, wenn ein Vorschlag auf dich wartet), Kaufsignale, offene Aufgaben. Nach dem Speichern bleiben offene Klappzeilen offen.
- **Rechts die Kontextspalte (320 px):** Ansprechpartner, letzter Kontakt, Kontaktstatus mit Rechtsgrundlage, Website, Telefon und der Verlauf der Phasen Recherche → Qualifiziert → Termin → Angebot → Auftrag. **Eine Kontaktsperre ist immer sichtbar** – als rote Meldung in der Kontextspalte und als Pille „Kontaktsperre“ im Kopf, auf jedem Reiter.
- **Gemessen bei 1280 × 720:** „Vereinbart“ beginnt bei 184 px (vorher stand der Kasten bei 252 px), Kontextspalte und erste Chance liegen im ersten Bildschirm (Chance endet bei 407 px). Der Überblick ist 583 statt 1.454 px hoch, im Überblick ist ein grüner Knopf sichtbar statt drei. Reiter „Kontakt & Verlauf“ 815 statt 2.506 px. Auf dem Smartphone (390 × 844) beginnt „Vereinbart“ bei 281 statt 317 px, ohne waagerechtes Scrollen.
- **Kontakt & Verlauf:** oben vier benannte Knöpfe – Gespräch notieren · Anruf erfassen · Termin eintragen · Mail-Entwurf schreiben –, darunter das Protokoll-Formular und der **Verlauf als Liste** (die Zeitleiste mit Filter, bisher unten im Überblick). Protokoll, Gesprächsvorbereitung, Entscheider-Recherche und Rollen & Kontaktbeschränkungen sind Klappzeilen.
- **Bedarf & Angebot, Recherche, Stammdaten** stehen in Karten statt in Abschnitten mit englischer Überschrift und Trennlinien; Aktionen sind Nebenknöpfe, „Speichern“ in Formularen bleibt grün. Der alte Punktwert bleibt eingeklappt in den Stammdaten („Alter Punktwert“).
- **„＋ Neue Firma“** (Firmenliste, Strg+K) zeigt „Neue Firma“ und „Firma speichern“ statt „Neuer Lead“/„Lead speichern“. Ablauf, Pflichtfelder und Dublettenprüfung unverändert.
- **Überall „Firma“ statt „Lead“:** in der Akte, in Dialogen und Toasts („Firma gespeichert“, „Firma endgültig gelöscht“), Pipeline, Datenpflege, Kontakt & Termine, KI-Studio, Playbook und in den Meldungen des Servers („Firma nicht gefunden“, „Firma ist gesperrt“, „evtl. schon als Firma vorhanden“, Vertriebskennzahlen „nach letzter Änderung der Firma“, Quellen „Stammdaten“ und „Firmensuche“). Interne Namen, Adressen, Kennungen und API-Felder bleiben. Im Kundenangebot heißt die Klausel jetzt „Keine Umsatz-, Ranking- oder Anfragen-Garantie“.
- Kleine Korrektur im Baukasten: Bei einer Klappzeile mit Aktion stand das › auf dem Smartphone in einer eigenen Zeile.
- Tests: neu `test_ui_akte_browser.py`; fünf Tests an die neuen Orte bzw. Texte angepasst (siehe SELF_REVIEW_LOG, Arbeitspaket 53). Unit 714 Tests (4 übersprungen) unter Python 3.13 und 714 Tests (6 übersprungen) unter 3.10, Browser 47 von 47 und 47 von 47 (zwei Läufe hintereinander).
- Kein Schemawechsel, keine neuen Abhängigkeiten, keine neuen Dateien in der Anwendung.

## 2.0.0-dev53 – Einstellungen und Abrechnen aufgeräumt: Abschnittsliste und vier Reiter

Schritt 5 der Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](docs/ROADMAP.md)). Keine Funktion entfällt – was umgezogen ist, steht in [UI_BAUKASTEN.md, Abschnitt „Was wohin zog (Schritt 5)“](docs/UI_BAUKASTEN.md). Server, Datenmodell und Buchhaltungsregeln (Festschreibung, Storno, E-Rechnung, Belege, Steuerexport) sind unverändert; geändert wurden nur drei Hinweistexte des Servers, die noch „Einstellungen → Daten & Zugang“ nannten.

- **Einstellungen sind keine 13.700-px-Seite mehr.** Links steht eine Abschnittsliste (240 px) mit neun Abschnitten, rechts der gewählte Abschnitt: Meine Firma · Leistungen & Preise · Zielkunden · Darstellung · Kalender & Postfach · Datenquellen · Sicherung & Zugang · KI-Werkzeuge · Hilfe & Playbook. Jeder Abschnitt hat eine eigene Adresse (`#/einstellungen?abschnitt=kalender` usw.); `#/einstellungen` öffnet den Abschnitt, den du zuletzt benutzt hast.
- **Kurzstand je Abschnitt**, nur aus vorhandenen Daten: z. B. „66 €/h · 6 Vorlagen“, „Klassisch · hell“, „CalDAV abgeglichen 12. Nov.“. Gelb markiert ist, was du dir ansehen solltest: fehlende Pflichtangaben für Rechnungen, keine oder eine über 7 Tage alte Sicherung, ein Kalenderabgleich älter als 24 Stunden, ein Zielkundenprofil ohne Standort oder Branchen.
- **Suche über die Einstellungen:** „Einstellung suchen …“ filtert die Liste („IBAN“ → Meine Firma, „Overpass“ → Datenquellen); Enter öffnet den ersten Treffer und springt zur passenden Stelle.
- **Nichts geht beim Wechseln verloren:** Hast du in einem Abschnitt etwas geändert und nicht gespeichert, fragt SignalDesk vor dem Wechsel wie in der Firmenakte – Speichern, Weiter bearbeiten oder Verwerfen. Lädt ein Abschnitt seine Werte neu (z. B. nach dem Offline-Schalter), bleiben deine ungespeicherten Eingaben stehen.
- **Alle bisherigen Sprungziele funktionieren weiter** – aus „Heute“ (Erste Schritte), den Angeboten, „Finden“ und aus Lesezeichen wie `?abschnitt=targetProfile` oder `?abschnitt=ownTimes`. Sie öffnen den Abschnitt, der die Stelle enthält. KI-Studio (`#/einstellungen/ki-studio`) und Playbook (`#/einstellungen/hilfe`) haben dieselbe Abschnittsliste.
- **Stammdaten für Rechnungen** stehen jetzt unter Einstellungen → **Meine Firma** (mit Hinweis, was noch fehlt), das Buchhaltungs-Backup unter **Sicherung & Zugang**. Vorlagen und Leistungskatalog sind unter „Leistungen & Preise“ Klappzeilen mit Kurzstand; „Deine Zeiten“ steht bei „Kalender & Postfach“, „Gewichte & Fristen“ bei „Zielkunden“, „Website-Abruf & Auswertung“ bei „Datenquellen“.
- **Gemessen bei 1280 × 720:** der Inhalt der Einstellungen beginnt bei 184 statt 377 px; statt einer Seite mit 13.728 px ist jeder Abschnitt 1.026 px (Datenquellen) bis 2.847 px (Kalender & Postfach) lang. Auf dem Smartphone (390 px) ist die Abschnittsliste eine eigene Ansicht; ein Abschnitt hat „← Einstellungen“.
- **Abrechnen hat vier Reiter:** Rechnungen · Ausgaben · Auswertung · Steuer & Export (`#/abrechnen`, `#/abrechnen/ausgaben`, `#/abrechnen/auswertung`, `#/abrechnen/steuer`). Du landest direkt in den Rechnungen statt in der Übersicht.
- **Rechnungen als Liste:** Titel „Abrechnen“ mit Anzahl und genau einer Hauptaktion „＋ Neue Rechnung“; Suche nach Nummer oder Firma, Ansichten Alle · Offen · Überfällig · Bezahlt · Entwürfe, alle Status unter „Filter ▾“. Spalten Rechnung · Nächster Schritt · Fällig · Status · Betrag brutto. Den nächsten Schritt liest SignalDesk aus dem, was vorliegt: „Prüfen und festschreiben“ (oder erst „Stammdaten ergänzen“), „Zahlungseingang abwarten“, „Zahlung erinnern“ – sonst „–“. Überfällig ist rot.
- **Gemessen bei 1280 × 720 mit 4 Rechnungen:** die erste Rechnungszeile steht bei 221 px – vorher 436 px, und auch das erst nach dem Wechsel auf den inneren Reiter „Rechnungen“. Zeilen 56 statt 72 px. Auf dem Smartphone bei 374 statt 646 px.
- **Editor und geöffnete Rechnung als eigene Ansicht** mit „← Rechnungen“. Die geöffnete Rechnung hat „Drucken / PDF ↗“ als Hauptaktion; E-Rechnung, Kopieren, Stornieren, Zahlungen und Mahnwesen wie bisher. Aus der Suche (Strg+K) öffnet eine Rechnung jetzt direkt.
- **Fehlen Pflichtangaben**, steht unter der Liste die Klappzeile „Stammdaten“ mit „Stammdaten ergänzen“ – ein Klick führt nach Einstellungen → Meine Firma. Darunter „Aus Angeboten berechnen“ (angenommene Angebote ohne Rechnung) und „Steuer & Export“.
- **Fehlerbehebung Tastatur:** In der Angebotsliste ging der Fokus einer Zeile verloren, wenn die Liste nach dem Laden neu gezeichnet wurde (Enter öffnete dann nichts; sporadischer Testfehler). Jetzt bleibt der Fokus auf derselben Zeile – auch in der neuen Rechnungsliste.
- Sichtbar „Firma“ statt „Lead“ in Abrechnen (Rechnungseditor, Vertriebskennzahlen), im KI-Studio, im Playbook und in den Einstellungen.
- Neue Bausteine: Abschnittsliste mit Kurzstand, Klappzeile mit Aktion, `formGuard.ask` für den Eingabeschutz außerhalb der Akte.
- Tests: neu `test_ui_einstellungen_abrechnen_browser.py`; neun Browser-Tests und zwei Unit-Tests an die neuen Orte angepasst (öffnen zuerst den passenden Abschnitt bzw. Reiter). Unit 714 Tests (4 übersprungen) unter Python 3.13 und 714 Tests (6 übersprungen) unter 3.10, Browser 46 von 46 und 46 von 46 (zwei Läufe hintereinander).
- Kein Schemawechsel, keine neuen Abhängigkeiten.

## 2.0.0-dev52 – Angebote aufgeräumt: Liste, Editor, Arbeitsplatz je Angebot

Schritt 4 der Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](docs/ROADMAP.md)). Keine Funktion entfällt – was umgezogen ist, steht in [UI_BAUKASTEN.md, Abschnitt „Was wohin zog (Schritt 4)“](docs/UI_BAUKASTEN.md). Freigabe, Bedarfsprüfung, Fassungen, Sperren, Statusfolge, Mindestverdienst, Zusatzaufträge, optionale Positionen und Nachfassen arbeiten unverändert; Server und Datenmodell auch (geändert nur ein Hinweistext auf „Heute“, der auf den alten Ort der Nachkalkulation verwies).

- **Drei Reiter:** Angebote · Aufträge & Betreuung · Auswertung, mit eigenen Adressen (`#/angebote`, `#/angebote/auftraege`, `#/angebote/auswertung`). `#/angebote?angebot=ID` öffnet wie bisher ein Angebot – auch nach dem Neuladen, als Lesezeichen und mit „Zurück“.
- **Angebote beginnen mit der Liste:** Titel mit Anzahl, genau eine Hauptaktion „＋ Neues Angebot“, darunter Suche (Projekt, Firma, Nummer), Ansichten Alle · Offen · Angenommen und „Filter ▾“ (Status inkl. „freigegeben“ und „ersetzt“, abgelaufene Bindefrist, noch nicht berechnet, ersetzte Fassungen ausblenden). Spalten Angebot · Nächster Schritt · Fällig · Status · Betrag netto. Den nächsten Schritt liest SignalDesk aus dem, was vorliegt: „Zur Freigabe prüfen“ bzw. „Prüfpunkte klären: n offen“, „Als gesendet markieren“, „Nachfassen: Anlass“ mit Frist, „Entscheidung dokumentieren“, „Kick-off: …“, „Übergabe & Abnahme: …“, „Betreuung läuft“, „Rechnung erstellen“ – sonst „–“. Klick oder Enter öffnet.
- **Gemessen bei 1280 × 720 mit 5 Angeboten:** die erste Angebotszeile steht bei 221 px statt 2.221 px; die Seite ist 720 statt 3.550 px lang. Auf dem Smartphone (390 px) steht das erste Angebot bei 330 statt 4.144 px.
- **„＋ Neues Angebot“ öffnet den Editor als eigene Ansicht** (Firma, Chance, Vorlage, Positionen, Steuer; rechts die Kundenvorschau, darunter die Kalkulation). Er beginnt leer, außer du hast dort noch Ungespeichertes. Speichern führt direkt in das geöffnete Angebot. Wenn „Heute“, die Recherche, eine Empfehlung oder „Überarbeiten“/„Zusatzauftrag erstellen“ eine Firma vorbelegen, öffnet sich der Editor von selbst.
- **Ein geöffnetes Angebot ist ein Arbeitsplatz:** „← Angebote“, das Projekt als Titel, Status, Firma · Nummer und genau eine Hauptaktion zur aktuellen Phase („Zur Freigabe prüfen“, „Als gesendet markieren“, „Nachfassen festhalten“, „Annahme dokumentieren“, „Projektstart festlegen“, „Kick-off vorbereiten“, „Übergabe/Abnahme dokumentieren“, „Rechnung erstellen“). Sie springt zum passenden Schritt – freigeben oder dokumentieren tust du dort wie bisher selbst. Reiter Positionen · Kundenvorschau · Interne Kalkulation · Verlauf; Positionen als Liste (Leistung · Umfang · Art · Betrag, aufklappbar), Summe und Zahlung & Bedingungen als Klappzeilen. Titel bei 82 px, Reiter bei 132 px, erste Position bei 221 px (vorher lag „Gespeichertes Angebot“ bei 3.939 px).
- **Rechts die Kontextspalte:** „Prüfung vor Freigabe“ (die Prüfpunkte der Freigabe, Mindestverdienst, Zahl der Hinweise; nach der Freigabe Datum, Stand und nur noch Abweichungen) und „Ablauf“ (Bedarf → Entwurf → Freigabe → Versand → Annahme, die aktuelle Phase hervorgehoben, nach der Annahme „Auftrag“).
- **Die Arbeitsschritte bleiben vollständig darunter:** Versand und Entscheidung sind vor der Freigabe als eingeklappte Vorschau erkennbar; Kick-off und Übergabe & Abnahme sind Klappzeilen, offen solange sie laufen. Überarbeiten, Zusatzauftrag, Export, Rechnung, Grundlage je Position und Auftragsumfang wie bisher. Der Reiter „Verlauf“ zeigt die Fassungen und eine Zeitleiste (erstellt, freigegeben, versendet, Nachfassen, Entscheidung, Projektstart, Übergabe, Abnahme, Nachrichtenentwürfe zu diesem Angebot).
- **Aufträge & Betreuung:** angenommene Angebote als Liste mit nächstem Schritt, Kick-off- und Abnahmestand; darunter „Nachkalkulation & Zeiterfassung“ und „Bestandskunden & Betreuung“. **Auswertung:** Lehren der Nachkalkulation (gesamt und je Leistung), Erlebnisstudien, „Was du lernst“.
- **Fehlerbehebung – getippter Text ging verloren:** Erlebnisstudie, Fachreview und Stichprobe speichern jede Eingabe sofort und zeichnen danach neu. Hast du währenddessen in einem anderen Feld getippt, ersetzte das Neuzeichnen deinen Text, und der Fokus war weg (so entstand der sporadische Testfehler aus dev51). Jetzt bleiben ungespeicherte Eingaben in anderen Feldern samt Schreibmarke stehen, und gespeichert wird der Reihe nach. Nachgewiesen mit einem neuen Browser-Test, der die Antwort des Servers künstlich zurückhält: vor der Korrektur 3 von 3 Fällen rot, danach grün.
- Sichtbar „Firma“ statt „Lead“ im Angebotsformular und in der Statusmeldung.
- Neue Bausteine im UI-Baukasten: Reiter einer Detailseite, Zeile mit Vertiefung, Prüfliste/Ablauf in der Kontextspalte, `uiKeep`/`uiSerial` für Eingaben beim Neuzeichnen.
- Tests: neu `test_ui_angebote_browser.py` und `test_keep_input_browser.py`; elf Browser-Tests an die neuen Orte angepasst (öffnen zuerst Editor, Reiter oder neue Adresse). Unit 714 Tests (4 übersprungen) unter Python 3.13 und 714 Tests (6 übersprungen) unter 3.10, Browser 45 von 45 und 45 von 45 (zwei Läufe hintereinander).
- Kein Schemawechsel, keine neuen Abhängigkeiten.

## 2.0.0-dev51 – Finden aufgeräumt: Sichten, Neue Suche, Import, Analysen

Schritt 3 der Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](docs/ROADMAP.md)). Keine Funktion entfällt – was umgezogen ist, steht in [UI_BAUKASTEN.md, Abschnitt „Was wohin zog (Schritt 3)“](docs/UI_BAUKASTEN.md). Server, Datenmodell und Suchlogik sind unverändert; geändert wurden nur zwei Hinweistexte des Servers, die auf den alten Ort von „OpenStreetMap nutzbar machen“ verwiesen.

- **Vier Reiter statt sieben:** Sichten · Neue Suche · Import · Analysen. Recherche & Berichte, URL-Recherche, Website-Scoring und Kaufsignale findest du unter „Analysen“ in einer eigenen Reiterzeile. Alle bisherigen Adressen funktionieren weiter; neu sind `#/finden/sichten` und `#/finden/neue-suche`.
- **„Finden“ öffnet, was ansteht:** Warten offene Treffer, landest du in „Sichten“, sonst in „Neue Suche“ – über die Seitenleiste, `#/finden` und „Neue Firmen finden“.
- **Neue Suche kompakt:** oben „Suche starten“ (vorher 1.455 px tief, jetzt bei 78 px – ohne Scrollen sichtbar). Darunter eine Zeile mit dem Stand deiner Datenquellen und dem Verweis auf Einstellungen → Datenquellen, dann Ort, Umkreis und Branchen. Gewählte Branchen stehen als Marken im Feld (× entfernt sie); ein Klick klappt die Auswahl mit Suche und allen Branchen auf.
- **„Wen suchst du?“ mit vier Voreinstellungen:** Handwerk & lokale Betriebe (OpenStreetMap, Wikidata, GLEIF; Betriebe ohne Rechtsform und Website-Suche an), Größere Firmen (GLEIF, Wikidata; ohne Rechtsform aus), Öffentliche Aufträge (TED), Alles (wie bisher). Sie setzen nur vorhandene Felder. Änderst du danach etwas von Hand, bleibt deine Änderung und die Auswahl zeigt „Eigene Auswahl“. Gemerkt wird die Voreinstellung mit deinen Suchprofilen und der zuletzt gestarteten Suche – dafür merkt sich SignalDesk jetzt auch Quellen, „ohne Rechtsform“ und „nur operative“ der letzten Suche.
- **Quellen & Budget, Optionen, Suchprofile** als Klappzeilen mit Kurzstand („GLEIF · OpenStreetMap · Wikidata · bis 300 neue Firmen …“). Fortschritt der Suche mit den Gründen für „ausgefiltert“ wie bisher, dazu „n Treffer sichten →“ und die Liste „Letzte Suchen“.
- **Sichten als Liste:** Firma (mit Branche und „ohne Rechtsform“) · Website (belegt, Vorschlag prüfen, Suche läuft, keine) · Entfernung · Quelle · „Übernehmen“ · ›. Ein Klick oder Enter klappt Adresse, Website-Nachweis, Kontakt, Quellen, Dubletten-Hinweise und alle Aktionen auf (Verwerfen, Website passt / passt nicht, Website suchen oder eintragen). Ansichten Offen · Mit Website · Übernommen in der Werkzeugzeile, alle übrigen Filter unter „Filter ▾“, Massenaktionen (Ausgewählte übernehmen/verwerfen, Übernehmen & Bericht, Websites suchen, Alle Treffer übernehmen) unter „Auswahl ▾“. Tastatur wie bisher (j/k, o, b, v).
- **Gemessen bei 1280 × 720 mit 11 Treffern:** erste Trefferzeile bei 221 px statt 2.124 px, 8 statt 0 Zeilen ganz sichtbar, Zeile 56 statt 117 px. Auf dem Smartphone (390 px) steht „Suche starten“ bei 111 statt 2.179 px, der erste Treffer bei 374 statt 3.573 px.
- **Umgezogen:** „OpenStreetMap nutzbar machen“ (mit eigenem Ortsfeld für die Overpass-Turbo-Abfrage), „Großer Firmenkatalog“ und „Quellen prüfen“ nach Einstellungen → Datenquellen; „Messung: Stichprobe von Hand prüfen“ nach Firmen → Datenpflege; „Firmenliste importieren“ nach Finden → Import.
- Sichtbar „Firma“ statt „Lead“ in Finden, Import und Analysen („Als Firma übernommen“, „schon Firma“, „Firma öffnen“, „Firmen auswählen“).
- Neue Bausteine im UI-Baukasten: Karte, Feld, Auswahlgruppe, Marke (`ui-card`, `ui-field`, `ui-seg`, `ui-chip`).
- Tests: neu Browser-Test `test_ui_finden_browser.py`; fünf Browser-Tests an die neuen Orte angepasst, ein sporadisch scheiternder Browser-Test (Erlebnisstudien) wartet jetzt auf das Neuzeichnen statt auf einen schon erreichten Ladezustand. Je 714 Tests unter Python 3.13 und 3.10, 41 von 41 Browser-Tests (zweimal hintereinander).
- Kein Schemawechsel, keine neuen Abhängigkeiten.

## 2.0.0-dev50 – Firmen und Heute aufgeräumt: mehr Liste auf einen Blick

Schritt 2 der Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](docs/ROADMAP.md)). Keine Funktion entfällt – was umgezogen ist, steht in [UI_BAUKASTEN.md, Abschnitt „Was wohin zog“](docs/UI_BAUKASTEN.md).

- **Eine Kopfzeile statt zwei:** Oben links stehen jetzt die Reiter des Bereichs (z. B. Firmenliste · Pipeline · Datenpflege), rechts die Suche (Strg+K). Die Kopfzeile ist 52 statt 82 px hoch, die Reiterleiste darunter entfällt. Angebote und Abrechnen haben nur eine Ansicht und zeigen daher keine Reiter.
- **„＋ Neuer Lead“ oben entfällt.** Du legst eine Firma in der Firmenliste mit „＋ Neue Firma“ an – oder überall mit Strg+K → „Neue Firma anlegen“.
- **Hell/Dunkel** wechselst du unter Einstellungen → Darstellung (Wie System · Hell · Dunkel); der Umschalter in der Kopfzeile entfällt, ebenso das Datum (steht jetzt bei „Heute“).
- **Firmenliste:** Titel mit Anzahl und genau einer Hauptaktion; darunter Suche, die häufigen Ansichten als Reiter (Alle, Heute fällig, Ohne nächsten Schritt, deine eigenen), der Rest unter „Weitere ▾“ (auch „Ansicht speichern“), Phase, Zurücksetzen und CSV-Import unter „Filter ▾“, Kaufsignal, Leistung und Letzter Kontakt unter „Spalten ▾“. Die Liste hat feste 56-px-Zeilen mit Firma · Nächster Schritt · Fällig · Phase · Passung; überfällig ist rot, heute gelb. Klick oder Enter auf die Zeile öffnet die Akte wie bisher, Filter in der Adresse und „← Zurück“ bleiben.
- **Gemessen bei 1280 × 720 mit 9 Firmen:** die erste Firmenzeile beginnt bei 221 px statt 574 px, 8 statt 2 Zeilen sind ganz sichtbar, die Schrift ist 14 statt 12 px. Auf dem Smartphone (390 px) steht die erste Firma bei 342 px statt unter dem Bildrand.
- **Heute:** Titel mit Datum und „＋ Neuer Eingang“ (öffnet das Erfassen eines Anrufs oder einer Anfrage). Darunter eine Zeile mit dem Kurzstand (als Nächstes, Wiedervorlage, Kapazität; „Einrichtung: n Punkte offen“ nur, solange etwas offen ist). „Als Nächstes“ ist eine Liste: Schritt mit Firma · Warum jetzt · Fällig · Phase. Klick auf die Zeile öffnet die Akte; „Erledigt“ hakt eine Aufgabe oder einen Rückruf direkt ab, ohne die Akte zu öffnen. Die Liste beginnt bei 184 px statt 342 px.
- **Alles Weitere als Klappzeilen mit Kurzstand:** Eingang & Rückrufe, Wiedervorlage, Kapazität & Potenzial (mit Pipeline), Tagesplan & Tagesabschluss, Systemstatus. Inhalte unverändert; ein Sprung dorthin (z. B. „Zum Eingang“) klappt die Zeile auf.
- Sichtbar „Firma“ statt „Lead“ in Kopfzeile, Firmenliste und Heute („Firma öffnen“, „neue Firmen“). Die übrigen Bereiche folgen in den nächsten Schritten.
- Tests: neu Browser-Test `test_ui_firmen_heute_browser.py` (Abnahmemaße, Menüs, Strg+K, Akte und Zurück, Klappzeilen, „Erledigt“, 390 px); sieben bestehende Browser-Tests und drei Unit-Tests an die neuen Orte angepasst. Je 714 Tests unter Python 3.13 und 3.10, 40 von 40 Browser-Tests (zweimal hintereinander).
- Kein Schemawechsel, keine neuen Abhängigkeiten.

## 2.0.0-dev49 – Menü auf dem Smartphone und gemeinsamer Baukasten für die Oberfläche

Schritt 1 der neuen Etappe „Visuelle Konsolidierung und Aufgabenführung“ (siehe [ROADMAP](docs/ROADMAP.md)).

- **Menü auf schmalen Bildschirmen:** Bis 520 px Breite (z. B. Smartphone, 390 px) war die Seitenleiste ausgeblendet – du kamst nur an die Reiter des aktuellen Bereichs. Jetzt steht oben links „☰ Menü“. Es öffnet die Seitenleiste als Schublade von links mit allen sechs Bereichen; der aktuelle ist markiert. Schließen mit „✕ Schließen“, Escape, Klick auf den abgedunkelten Hintergrund oder durch Wahl eines Bereichs; danach steht der Fokus wieder auf „☰ Menü“. Für Bildschirmleser sind `aria-expanded` und `aria-controls` gesetzt, der Inhalt dahinter ist solange nicht bedienbar.
- Damit alles in eine Zeile passt, zeigt die Kopfzeile bei schmaler Breite nur den Bereich und „Neuer Lead“ als „＋“ (Name für Bildschirmleser bleibt „Neuer Lead“).
- **Auf breiten Bildschirmen ändert sich nichts** – der Menü-Knopf ist dort unsichtbar.
- **Neu für die nächsten Schritte: UI-Baukasten.** Sieben Bausteine (Seitenkopf, Werkzeugzeile, Liste, Klappzeile, Status, Knöpfe, Abstände und Schrift) als Klassen mit Präfix `ui-` in style.css, dazu Abstandsmaße 4–32 px, Zeile 56 px, Knopf 36 px, Kontextspalte 320 px. Regeln und Messwerte stehen in [docs/UI_BAUKASTEN.md](docs/UI_BAUKASTEN.md). Die vorhandenen Ansichten sind **noch nicht** umgestellt – das folgt ab Schritt 2 (Firmen und Heute).
- Tests: neu `test_v2_ui_baukasten.py` (6) und Browser-Test `test_mobile_nav_browser.py`; je 714 Tests unter Python 3.13 und 3.10, 39 von 39 Browser-Tests grün.
- Kein Schemawechsel.

## 2.0.0-dev48 – Fehlerbehebung: Budget wieder fair auf alle Quellen verteilt

Befund des Eigentümers (Bildschirmfoto, Stuttgart 50 km): GLEIF meldete 300 von 300 neuen Firmen, Wikidata, OpenStreetMap und TED
„übersprungen – Budget von 300 neuen Firmen erreicht“ – obwohl der lokale OpenStreetMap-Bestand 165.548 Betriebe (77.060 mit Website) hat.

- **Ursache:** Seit der Umstellung auf den gemeinsamen Auftragsdienst (v1.16) läuft jede Quelle als eigener Schritt. Die faire Aufteilung des Budgets rechnete dann nur mit der gerade laufenden Quelle – die erste bekam alles. Die vorhandene Prüfung rief die Suche ohne Auftragsdienst auf und sah das nicht.
- **Behoben:** Geteilt wird durch alle Quellen der Suche, die noch ausstehen. Bei 4 Quellen und 300 Firmen bekommt jede zunächst 75; was eine nicht braucht, geht an die nächste.
- **Neuer Test** über den echten Auftragsweg; er scheiterte vorher mit genau der Meldung aus dem Bildschirmfoto.
- Kein Schemawechsel. Bereits gelaufene Suchen bleiben, wie sie sind – für OpenStreetMap-Treffer die Suche neu starten.

## 2.0.0-dev47 – Erlebnisstudien und „Was du lernst“

Produktreview M30 und M34 (Entscheidung des Eigentümers: beides).

- **Neu unter „Angebote“: „Erlebnisstudien“.** Zu einer Firma eine Studie anlegen (vorher, nachher oder einmalig; moderiert oder unmoderiert) mit Aufgaben („Finden Sie die Telefonnummer“) und Fragen.
- **Sitzungen:** Testpersonen bekommen nur ein Kürzel (P1, P2 …); E-Mail-Adressen und Telefonnummern werden abgelehnt. Je Aufgabe: geschafft, mit Hilfe, nicht geschafft, nicht bearbeitet, Zeit und Beobachtung; je Frage die Antwort.
- **Nur echte Angaben:** Eine Sitzung zählt erst mit der Bestätigung „stammt von dieser Testperson, nicht ausgedacht, nicht von einer KI“. SignalDesk erzeugt keine Antworten.
- **Auswertung:** Erfolg je Aufgabe mit Anzahl und Median-Zeit, Stichprobe (Geräte, Zielgruppe, wie gewonnen) getrennt, Hinweis unter 5 Sitzungen, Vergleich mit der Vorher- bzw. Nachher-Studie derselben Firma.
- **Neu: „Was du lernst“.** Aufwand je Projektart (aus der Nachkalkulation), Aufgabenerfolg je Methode und Wirkung vorher/nachher – Aussage erst ab 3 Fällen, Grenzen immer sichtbar.
- Schema 48 (vier neue Tabellen).

## 2.0.0-dev46 – Fachreview und Kalibrierung der Website-Bewertung

Produktreview M29 und M33 (Entscheidung des Eigentümers: direkt in der App).

- **Neu unter „Finden → Website-Scoring“: „Fachreview & Kalibrierung“.** Zu einer abgeschlossenen Bewertung ein Review anlegen; alle Rubriken werden mit dem automatischen Ergebnis übernommen.
- **Je Rubrik:** auswählen oder abwählen, dein Urteil (ok, auffällig, Hinweis, unbekannt, offen), Beleg und Begründung. Jede Eingabe wird sofort gespeichert – Neuladen oder Schließen verliert nichts.
- **Abschließen** erst, wenn jede gewählte Rubrik ein Urteil mit Begründung hat und jede „auffällig“ einen Beleg; danach unveränderlich. Prüfer, Zeitpunkt und Bewertungsversion stehen dabei.
- **Kalibrierung:** Übereinstimmung zwischen dir und der Automatik je Rubrik und Version, mit Richtung der Abweichung (z. B. „auffällig → ok“). Rubriken unter 70 % ab 5 Urteilen sind markiert. SignalDesk ändert keine Gewichte selbst.
- Schema 47 (zwei neue Tabellen).

## 2.0.0-dev45 – Recherchepilot: Stichprobe von Hand prüfen

Produktreview M21 (Entscheidung des Eigentümers: Referenz durch Prüfung von Hand).

- **Neu unter „Finden“: „Messung: Stichprobe von Hand prüfen“.** Zieht 20, 50, 75 oder 100 zufällige Firmen aus deinen Treffern, wahlweise nur aus einer Quelle (z. B. OpenStreetMap).
- **Je Firma von Hand:** Zielbetrieb ja/nein, Website laut SignalDesk richtig/falsch/fehlt, hat die Firma eine Website, Branche richtig. „unklar“ ist immer erlaubt. Bei „kein Zielbetrieb“ entfallen die übrigen Fragen.
- **Kennzahlen mit Anzahl:** Anteil Zielbetriebe, Trefferquote der Websites, Abdeckung der Websites, Anteil mit Website, Branche richtig. Hinweis bei kleiner Basis.
- Der Stand beim Ziehen wird festgehalten, spätere Änderungen verfälschen die Messung nicht. Export als CSV. Nichts wird abgerufen.
- Schema 46 (zwei neue Tabellen).

## 2.0.0-dev44 – Firmensuche: Gründe sichtbar, mehr Websites

Befund des Eigentümers mit dem Stuttgart-Auszug: „sehr viele Betriebe im Bestand, aber nur 5 neue Treffer, viel ausgefiltert, kaum Websites“.

- **Warum ausgefiltert:** Die Ergebniszeile je Quelle nennt jetzt die Gründe (z. B. „412 ohne Rechtsform, 30 andere Branche“) statt nur einer Summe.
- **Hinweis bei Handwerk:** Fällt mindestens die Hälfte wegen fehlender Rechtsform heraus, erklärt ein Hinweis den Haken „auch Betriebe ohne Rechtsform“ – mit dem Datenschutz-Hinweis, dass dahinter eine Einzelperson stehen kann. Die Voreinstellung bleibt deine Entscheidung.
- **Website-Suche mit Ort:** Domain-Vorschläge enthalten jetzt auch Name und Ort (z. B. `elektro-mueller-stuttgart.de`); vorher fiel der Ort ganz heraus.
- **Firmenname im Impressum:** gleiche Wörter in anderer Reihenfolge („Malerbetrieb Huber“ / „Huber Malerbetrieb e.K.“) und Inhaberangaben („Inh. …“) verhindern den Vorschlag nicht mehr. Es bleibt ein Vorschlag zum Bestätigen; andere PLZ oder andere Namen passen weiterhin nicht.
- Kein Schemawechsel.

## 2.0.0-dev43 – Entwürfe ins Postfach (IMAP)

Produktreview M24 Stufe 3 – damit ist M24 umgesetzt.

- **Neu in „Einstellungen → Kalender & Postfach“:** Postfach-Server, Benutzername, Absender und Passwort. „Verbindung prüfen“ findet den Entwürfe-Ordner (Markierung „Drafts“ oder übliche Namen wie „Entwürfe“).
- **„In Entwürfe legen“** an jedem gespeicherten Entwurf: Der Entwurf erscheint im Entwürfe-Ordner deines Mailprogramms. Du prüfst Empfänger und Inhalt und versendest selbst. Die Liste zeigt, welche Entwürfe im Postfach liegen.
- **Nie Versand:** kein SMTP im ganzen Programm; die einzige schreibende Aktion ist das Ablegen als Entwurf. Nachrichten werden weder gelesen noch verschoben oder gelöscht (Test).
- **Sperren beim Ablegen erneut geprüft:** Kontaktsperre der Firma, Sperrliste und Einschränkungen der Person (z. B. „keine E-Mail“).
- Empfänger nur die geschäftliche Adresse der Firma. Passwort wie beim Kalender nie in der Datenbank. Im Offline-Modus keine Verbindung.
- Schema 45 (zwei neue Spalten an den Entwürfen). 691 Tests (5 neu) unter Python 3.10 und 3.13, 34 Browser-Tests (1 neu).

## 2.0.0-dev42 – Kalender-Abgleich über CalDAV

Produktreview M24 Stufe 2 (offener Standard statt Anbieter-APIs – eine Umsetzung für Google, iCloud, mailbox.org, IONOS, Nextcloud und andere).

- **SignalDesk → Kalender:** geplante, bestätigte, erledigte und abgesagte Termine werden angelegt bzw. aktualisiert (nur Titel, Firma, Zeit, Ort, Status – keine Notizen). Unveränderte Termine werden nicht erneut übertragen, in SignalDesk gelöschte entfernt. Fremde Kalendereinträge fasst SignalDesk nie an.
- **Kalender → SignalDesk:** nur „belegt von … bis …“ der nächsten 60 Tage, ohne Titel oder Teilnehmer. Abgesagte und als „frei“ markierte Einträge zählen nicht.
- **Konfliktwarnung** beim Anlegen eines Termins (belegte Kalenderzeit oder anderer SignalDesk-Termin); **freie Terminvorschläge** sparen belegte Zeiten aus.
- **Aktualität sichtbar:** letzter Abgleich mit Ergebnis, Hinweis bei mehr als 24 Stunden.
- **Zugangsdaten nie in der Datenbank:** Passwort nur im Arbeitsspeicher, auf Wunsch „auf diesem Rechner merken“ in einer eigenen Datei (Rechte 600). Die Oberfläche bekommt es nie zurück. App-Passwort empfohlen. Nur HTTPS; im Offline-Modus kein Abgleich.
- Schema 44 (zwei neue Tabellen). 686 Tests (6 neu) unter Python 3.10 und 3.13, 33 Browser-Tests (1 neu).

## 2.0.0-dev41 – Kalender-Abo und Termin-Export

Produktreview M24 Stufe 1 (Entscheidung des Eigentümers: offene Standards statt Anbieter-APIs).

- **Neuer Abschnitt „Einstellungen → Kalender & Postfach“.**
- **Kalender-Abo:** Eine Abo-Adresse mit zufälligem Schlüssel liefert alle geplanten, bestätigten und abgesagten Termine im iCalendar-Format, für Kalenderprogramme auf diesem Rechner. Das Abo lässt sich abschalten; ein neuer Schlüssel macht die alte Adresse sofort ungültig. Ohne gültigen Schlüssel gibt es nichts. Mit eingeschaltetem Login bleibt das Abo über den Schlüssel erreichbar, die Verwaltung nicht.
- **Export** aller Termine als .ics-Datei – für jeden Kalender, auch Web-Kalender.
- **Inhalt nur das Nötige:** Titel, Firma, Zeit, Ort, Status. Gesprächsnotizen und Personen bleiben in SignalDesk.
- Kein Schemawechsel. 680 Tests (2 neu) unter Python 3.10 und 3.13, 32 Browser-Tests (1 neu).

## 2.0.0-dev40 – Firmenakte als eigene Seite

Produktreview M07, Variante B (Entscheidung des Eigentümers) – damit abgeschlossen.

- **Die Firmenakte ist eine eigene Seite** in voller Breite statt eines Fensters über der Liste. Die Ansicht dahinter ist ausgeblendet, die Seite scrollt normal, die Kopfzeile zeigt „Firmenakte“.
- **Adresse `#/firmen/akte/ID`**, mit den Filtern der Firmenliste (z. B. `?suche=Kanzlei`). Neuladen öffnet die Akte wieder; „← Zurück“ bzw. Browser-Zurück führt dorthin, wo du herkamst – mit denselben Filtern. Ältere Adressen mit `?firma=ID` gelten weiter.
- Reiter, Schutz ungespeicherter Eingaben und alle Funktionen der Akte sind unverändert.
- Der Navigationstest prüft jetzt die neue Adresse statt `?firma=`. Kein Schemawechsel. 678 Tests unter Python 3.10 und 3.13, 31 Browser-Tests (1 neu).

## 2.0.0-dev39 – Impressum-Sammelprüfung setzt nach Neustart fort

Produktreview M23 – damit abgeschlossen.

- **Automatisch fortsetzen:** Lief eine Impressum-Sammelprüfung beim Neustart, setzt SignalDesk sie beim Start fort. Bisher wartete sie auf einen Klick.
- **Deine Pause gilt:** Hast du einen Lauf selbst pausiert, bleibt er pausiert. SignalDesk merkt sich dafür den Grund der Pause.
- **Offline wartet:** Im Offline-Modus wird nichts fortgesetzt; der Lauf steht in „Heute“ als „wartet auf Fortsetzen (offline)“.
- „Heute“ zeigt laufende Sammelprüfungen mit offenen Einträgen; von dort geht es zum Pausieren.
- Tests: Das Aufräumen temporärer Testdatenbanken wiederholt jetzt auch bei „NotADirectoryError“ – so meldet Python 3.10 unter Windows eine noch gesperrte Datei (CI-Fehler in `test_sprintB_sweep`).
- **Schemawechsel 42 → 43** (Grund einer Pause). 678 Tests (3 neu) unter Python 3.10 und 3.13, 30 Browser-Tests.

## 2.0.0-dev38 – Angebot mit eigener Adresse

Produktreview M07 (Teil).

- **Ein geöffnetes Angebot hat eine eigene Adresse** (`#/angebote?angebot=ID`). Neuladen, Lesezeichen und eine eingegebene Adresse öffnen dasselbe Angebot; „Zurück“ führt zum vorher geöffneten Angebot.
- Nur Oberfläche, kein Schemawechsel. 675 Tests unter Python 3.10 und 3.13, 30 Browser-Tests (1 neu).

## 2.0.0-dev37 – Faustregeln der Website-Bewertung als Hinweis statt Urteil

Produktreview M28.

- **Vier pauschale Regeln liefern „Hinweis (prüfen)“ statt „auffällig“:** Überschriften-Hierarchie (A3), Schriftfamilien (A6), Jahresangabe im Fußbereich (A7) und Hauptnavigation (B7). Jeder Hinweis nennt den Messwert und warum die Regel irren kann (z. B. „Gezählt werden auch Symbol- und Fallback-Schriften“).
- **Hinweise sind keine Mängel:** Sie zählen als geprüft (Belegabdeckung), aber nicht in den Anteil „auffällig“ und damit nicht in die Priorität. Sie belegen keine Angebotsposition (M32) und werden nicht als Kaufsignal-Beleg genutzt.
- **Bewertungsversion 2.1:** Ältere Bewertungen gelten als „andere Bewertungsversion“ und werden nicht still verglichen.
- Zwei bestehende Tests erwarteten für diese vier Regeln „auffällig“; ihre Erwartung folgt jetzt der Vorgabe aus dem Review. Kein Schemawechsel. 675 Tests (2 neu) unter Python 3.10 und 3.13, 29 Browser-Tests.

## 2.0.0-dev36 – KI-Analyse, Schnellprüfung und Ansprechpartner-Suche setzen nach Neustart fort

Produktreview M23 Teil 2, Abnahmefall T14 bestanden.

- **KI-Analyse, Schnellprüfung und Suche nach öffentlichen Ansprechpartnern** laufen über das gemeinsame Auftragssystem statt über eigene Threads: sichtbar unter den Aufträgen, je Domain höchstens ein Abruf gleichzeitig.
- **Neustart mitten im Lauf:** Der Lauf wird fortgesetzt. Bisher wurden KI-Analyse und Schnellprüfung verworfen; die Ansprechpartner-Suche blieb sogar dauerhaft auf „läuft“ stehen.
- **Ältere Läufe** ohne Auftragsschritt werden einmalig als „durch Neustart unterbrochen“ gekennzeichnet – nie mehr dauerhaft „läuft“.
- Ein fehlgeschlagener Lauf ist ein fehlgeschlagener Auftragsschritt mit Grund (z. B. „Abruf durch robots.txt untersagt“).
- Kein Schemawechsel. 673 Tests (3 neu) unter Python 3.10 und 3.13, 29 Browser-Tests.

## 2.0.0-dev35 – Website-Bewertung und Karriereseiten-Scan setzen nach Neustart fort

Produktreview M23 Teil 1, Abnahmefall T14.

- **Website-Bewertung und Karriereseiten-Scan laufen über das gemeinsame Auftragssystem** statt über eigene Threads – mit demselben Lebenszyklus wie Firmen-Bericht und Sammelsuche: sichtbar unter den Aufträgen, je Website-Domain höchstens ein Abruf gleichzeitig, Pausieren, Abbrechen, erneut ausführen.
- **Neustart mitten im Lauf:** Unterbrochene Bewertungen und Scans werden wieder eingereiht und fortgesetzt. Bisher wurden sie als „durch Neustart unterbrochen“ verworfen und mussten neu gestartet werden.
- **Ältere Einträge** (wartend oder laufend, aus der Zeit vor dev35) werden beim Start als Auftragsschritte übernommen, ohne Doppelung.
- **Nach einem Abruffehler** (z. B. Zeitüberschreitung) lässt sich genau dieser Schritt erneut ausführen; erfolgreiche Schritte bleiben unberührt.
- Kein Schemawechsel. 670 Tests (4 neu) unter Python 3.10 und 3.13, 29 Browser-Tests.

## 2.0.0-dev34 – Globale Suche mit Strg+K

Produktreview M10.

- **„⌕ Suchen“ oben rechts bzw. Strg+K (⌘K):** ein Suchfeld für Firmen (Name, Firmierung, Website), Chancen, Angebote (Nummer, Projekttitel) und Rechnungsnummern, nach Gruppen sortiert; Treffer am Namensanfang zuerst. Gesperrte Firmen sind gekennzeichnet.
- **Tastatur:** Pfeiltasten wählen, Enter öffnet (Firma bzw. Chance in der Firmenakte, Angebot im Angebotsbereich), Escape schließt und gibt den Fokus an die vorherige Stelle zurück.
- Personen und Notizen werden nicht durchsucht. % und _ im Suchbegriff wirken nicht als Platzhalter. Nur lesend, kein Schemawechsel.
- Auf schmalen Bildschirmen zeigt der Knopf nur das Lupensymbol, damit die Kopfzeile nicht seitlich scrollt.
- 666 Tests (2 neu) unter Python 3.10 und 3.13, 29 Browser-Tests (1 neu).

## 2.0.0-dev33 – Befund mit Angebot verbinden

Produktreview M32.

- **„Grundlage je Position (nur intern)“** am gespeicherten Angebot. Jede Position zeigt eine von vier Grundlagen:
  - **bestätigter Bedarf** der Chance bzw. Firma,
  - **geprüfter Befund**: ein bestätigter Website-Befund oder eine freigegebene Recherche-Beobachtung, deren Paketvorschlag die Leistung enthält,
  - **begleitend**: Anreise, Tagespauschale, Aufwand,
  - **ohne Grundlage**.
- **Ungeprüfte Hypothesen**, die auf eine Position zeigen, stehen ausdrücklich als „offen (ungeprüft)“ dabei und zählen nie als Grundlage. Verworfene Befunde zählen gar nicht.
- **Versandfreigabe:** Hinweise für Positionen ohne Grundlage (optionale Positionen ausgenommen) und für Positionen mit offenen Hypothesen. Kein Sperrgrund – die Entscheidung bleibt bei dir.
- Nichts davon erscheint im Kundendokument. Kein Schemawechsel. 664 Tests (2 neu) unter Python 3.10 und 3.13, 28 Browser-Tests (1 neu).

## 2.0.0-dev32 – Abnahmefälle T07, T09, T10, T13; Beträge im Festpreis-Abschnitt

- **Fehlerbehebung im Kundendokument:** Der Abschnitt „Festpreis“ schrieb Beträge mit Punkt („264.00 EUR netto“), die Tabelle darüber mit Komma („264,00 €“). Jetzt einheitlich in deutscher Schreibweise („264,00 € netto“, „Gesamtbetrag: 314,16 €“). Gefunden beim Szenario T13.
- **Abnahmefälle als Szenarien geprüft** (über die vorhandenen Funktionen, ohne weitere Codeänderung):
  - T07: Projektanfrage aufnehmen – Eingang mit Frist, Firma, Chance, bestätigter Bedarf, Angebot der Chance, Anfrage fristgerecht erledigt.
  - T09: Medienangebot – Prüfpunkte Mediengestaltung, Korrekturschleifen, Nutzungsrechte, Druckkosten außerhalb; Projektkompass fragt Material und Freigabeperson an.
  - T10: Softwareangebot – Prüfpunkte Betrieb, Zugänge, Testdaten und Übergabe; Betrieb als laufende Leistung; Testzugang ohne Passwörter.
  - T13: Zeitüberschreitung – Hinweis „Umfang mit dem Kunden prüfen“, keine Reststunden in der Auslastung; Mehrarbeit als Zusatzauftrag, der Auftrag bleibt unverändert.
  Damit sind die Abnahmefälle T01–T13 und T15 bestanden. T14 (Recherche nach einem Fehler wieder aufnehmen) bleibt offen, bis M23 umgesetzt ist.
- 662 Tests (4 neu) unter Python 3.10 und 3.13, 27 Browser-Tests. Kein Schemawechsel.

## 2.0.0-dev31 – Abnahmefälle T06 und T15 als Szenarien geprüft

Keine Funktionsänderung, kein Schemawechsel.

- **T15 – Sicherung in getrennte Testinstallation zurückspielen:** Eine Installation enthält alles, was Etappe C und D anlegen: Chance mit Briefing, Revision mit Option, Nachfassen mit Ergebnis, Übergabe und Abnahme mit Restpunkt, Zusatzauftrag, Betreuung mit Monatsrechnung, Zeit je Position, gestarteter Projektkompass, Entwurf aus eigener Vorlage und Kurzbericht. Ihre Sicherung wird in eine zweite Installation zurückgespielt. Dort sind alle 16 geprüften Tabellen vollständig, und die Abläufe laufen weiter. Der bereits abgerechnete Monat wird nicht doppelt abgerechnet, eine Revision des Zusatzauftrags ist möglich. Die Ausgangsinstallation bleibt unverändert. Eine Sicherung mit älterem Schemastand wird beim Zurückspielen auf den aktuellen Stand migriert.
- **T06 – Rückruf nach erfolglosem Versuch planen** (Browser): „Nicht erreicht“ am Vormittag plant den nächsten Versuch zu einer anderen Tageszeit mit Frist. Nach drei Versuchen schlägt SignalDesk Kanalwechsel oder Parken vor, statt weiter anzurufen.
- 658 Tests (2 neu) unter Python 3.10 und 3.13, 27 Browser-Tests (1 neu).

## 2.0.0-dev30 – Kundenfähiger Kurzbericht

Produktreview M25.

- **„04 / Kurzbericht“** in der Website-Bewertung: Firma wählen, einzelne Befunde ankreuzen, optional eine Einleitung, Vorschau und Download (.md).
- **Nur geprüfte Befunde wählbar:** Website-Befunde mit Prüfstatus „bestätigt“ und Recherche-Beobachtungen mit Status „freigegeben“. Der Server lehnt alles andere ab; die Zahl nicht wählbarer Befunde wird genannt.
- **Keine internen Angaben:** Der Bericht enthält Bezeichnung, Beobachtung, Fundstelle mit Stand und die Frage an den Kunden. Punktwerte, Prioritäten, Profilnähe, Angebotsideen, Hypothesen, Kaufsignale, Personen und Kalkulationen bleiben draußen.
- Abschließende Einordnung: Momentaufnahme, keine vollständige Prüfung, keine Rechtsberatung. Gesperrte Firmen bekommen keinen Bericht. Jeder Bericht wird mit den gezeigten Befunden gespeichert und im Verlauf vermerkt (nicht versendet).
- **Schemawechsel 41 → 42** (gespeicherte Kurzberichte). 656 Tests (2 neu) unter Python 3.10 und 3.13, 26 Browser-Tests (1 neu).

## 2.0.0-dev29 – Eigene Nachrichtenvorlagen mit Platzhaltern

Produktreview M37.

- **Vorlagen im Mail-Assistenten** (Heute → Kontakt & Termine): Vorlage, Angebot und Person wählen, Vorschau ansehen, als Entwurf speichern. Mitgeliefert sind vier neutrale Startvorlagen (nach dem Gespräch, Angebot versenden, vereinbartes Nachfassen, Terminbestätigung). Sie lassen sich ändern; eigene kommen dazu.
- **Platzhalter nur aus bestätigten Daten:** Firma, gewählte Person, Angebot mit Nummer, Projekt, Festpreis, Bindefrist und freigegebenem Stand, nächster Termin, nächste Nachfassfrist, eigene Stammdaten. Unbekannte Platzhalter werden beim Speichern abgelehnt.
- **Fehlende Werte sichtbar:** [FEHLT: …] im Text und als Liste; „Endfassung kopieren“ erst ohne Lücken. Der Angebotsstand fehlt, solange das Angebot nicht freigegeben ist.
- **Anrede:** neutral („Guten Tag Vorname Nachname,“ bzw. „Guten Tag,“). „Sehr geehrte Frau …/Sehr geehrter Herr …“ nur, wenn die Anrede an der Person ausdrücklich hinterlegt ist. Dafür gibt es ein neues Feld an der Person; nie aus dem Vornamen abgeleitet.
- **Kontaktregeln:** Vorschau und Entwurf scheitern bei gesperrter Firma und bei Personen mit „keine E-Mails“, „nur Post“ oder Widerspruch. Ein Entwurf braucht weiterhin den dokumentierten Anlass. Nichts wird versendet.
- **Schemawechsel 40 → 41** (Vorlagen, Anrede an der Person, Bezug der Entwürfe). 654 Tests (3 neu) unter Python 3.10 und 3.13, 25 Browser-Tests (1 neu).

## 2.0.0-dev28 – Projektkompass mit Material- und Entscheidungsliste

Etappe D, Produktreview M38 und M39.

- **Projektkompass** am angenommenen Auftrag, je Auftrag unabhängig (mehrere Projekte einer Firma laufen getrennt).
  - Vorbelegt mit dem Startgespräch, den offenen Briefing-Punkten der Chance und typischen Voraussetzungen je Leistungsbereich. Für Mediengestaltung sind das Material und Freigabeperson, für Software Testzugang und priorisierte Anforderungen, für Sichtbarkeit Kontozugang.
- **Je Punkt:** Art (Material, Zugang, Entscheidung, Termin, Sonstiges), wer liefert (ich, Kunde, Dritte, optional mit Namen), bis wann, was ohne den Punkt nicht geht, Stand. „Entfällt“ nur mit Begründung; eigene Punkte lassen sich ergänzen.
- **Startstatus:** „Vorbereitung“, „wartet auf …“ (mit Name, Punkt und Frist), „bereit zum Start“ oder „gestartet am …“. Start trotz offener Punkte geht nur bewusst und steht im Verlauf.
- **Heute** zeigt fällige Startvoraussetzungen mit Verantwortlichem und Auswirkung. In der Bestandsübersicht steht der Startstatus je Projekt.
- **Keine Passwörter:** Es gibt kein Passwortfeld. Eingaben wie „Passwort: …“, „Login = …“ oder Token-Muster werden abgelehnt, mit Hinweis auf sichere Übergabewege.
- **Schemawechsel 39 → 40** (Projektkompass). 651 Tests (3 neu) unter Python 3.10 und 3.13, 24 Browser-Tests (1 neu).

## 2.0.0-dev27 – Zeiten je Leistung und Lernhinweise

Etappe D, Produktreview M20.

- **Zeit einer Position zuordnen:** In der Nachkalkulation wählst du beim Erfassen die Angebotsposition (oder „Auftrag allgemein“). Optionale Positionen sind nicht wählbar.
- **Soll/Ist je Position:** Die Auftragskarte zeigt je Position kalkulierte und gebrauchte Stunden mit Abweichung, dazu Stunden ohne Position.
- **Lernhinweise je Leistung** aus abgeschlossenen Aufträgen: Ab drei Stichproben nennt SignalDesk die mittlere Abweichung und die Spanne. Darunter steht nur die Anzahl.
- **Vorschläge:** Ab 15 % Abweichung kommt der Hinweis, den Zeitansatz unter „Leistungen & Preise“ zu prüfen. Bei starker Streuung lautet der Rat, Umfang und Korrekturschleifen im Angebot zu schärfen. Werte werden nie automatisch geändert.
- **Schemawechsel 38 → 39** (Position an Zeiteinträgen). 648 Tests (2 neu) unter Python 3.10 und 3.13, 23 Browser-Tests (1 neu).

## 2.0.0-dev26 – Bestandskunden und Betreuung

Etappe D, Produktreview M19.

- **Neuer Abschnitt „Bestandskunden & Betreuung“** in der Angebotsansicht. Je Firma mit angenommenem Auftrag stehen getrennt nebeneinander:
  - Betreuung: monatliche Positionen mit Beginn, Ende und Abrechnungsstand,
  - Projekte: einmalige Leistungen mit Abnahmestand, auch Zusatzaufträge,
  - neue Projekte als eigene Chancen, direkt anlegbar.
- **Je Monat genau eine Monatsrechnung** mit Leistungszeitraum (z. B. „Leistungszeitraum 11/2026“). Ohne Angabe nimmt der Entwurf den ältesten offenen Monat. Abgelehnt werden doppelte Monate, Monate vor Beginn oder nach Ende und Monate in der Zukunft. Stornierte Rechnungen zählen nicht.
- **Laufzeit:** Beginn ist das Zusagedatum. Ein Ende (z. B. nach Kündigung) beendet die Abrechnung danach; das steht im Verlauf der Firma.
- **Heute** zeigt nicht abgerechnete Betreuungsmonate mit Anzahl und Monatsbetrag.
- **Schemawechsel 37 → 38** (Laufzeiten der Betreuung). 646 Tests (3 neu) unter Python 3.10 und 3.13, 22 Browser-Tests (1 neu).

## 2.0.0-dev25 – Zusatzaufträge mit erkennbarem Ursprungsumfang

Etappe D, Produktreview M18.

- **„Zusatzauftrag erstellen“** am angenommenen Auftrag öffnet den Angebotsbaukasten leer, mit fester Firma und Chance. Mit Anlass gespeichert, entsteht ein eigenes Angebot mit der Nummer des Auftrags und Zähler (z. B. AN-2026-0003-Z1).
- **Der Auftrag bleibt unverändert.** Das Kundendokument des Zusatzauftrags heißt „Zusatzauftrag“. Es nennt den Auftrag, den Anlass und den bisher beauftragten Umfang und stellt klar, dass die neuen Leistungen gesondert beauftragt, abgenommen und abgerechnet werden.
- **Auftragsumfang** am Auftrag und an jedem Zusatzauftrag: ursprünglicher Auftrag und alle Zusatzaufträge mit Stand und Betrag. Die Summe „beauftragt insgesamt“ zählt nur angenommene Zusatzaufträge; offene stehen getrennt daneben.
- Freigabe, Versand, Nachfassen, Zusage, Übergabe und Abnahme laufen wie bei jedem Angebot. Vor der Zusage lässt sich ein Zusatzauftrag überarbeiten (-Z1-R2) und bleibt dabei Zusatzauftrag.
- **Schemawechsel 36 → 37** (Bezug und Zähler am Angebot). 643 Tests (2 neu) unter Python 3.10 und 3.13, 21 Browser-Tests (1 neu).

## 2.0.0-dev24 – Auftragsübergabe und Abnahme

Etappe D, Produktreview M17 (Abnahmefall T12).

- **Schritt „Übergabe & Abnahme“** am angenommenen Angebot. Liefergegenstände und Abnahmekriterien werden aus dem Angebot übernommen (optionale Positionen nicht); eigene Punkte lassen sich ergänzen. Jeder Punkt ist offen, erledigt oder entfällt – „entfällt“ nur mit Begründung.
- **Übergabe dokumentieren** (Datum, Weg, Notiz) erst, wenn kein Liefergegenstand mehr offen ist. Dabei setzt du eine Frist, bis wann die Abnahme eingeholt wird; daraus wird eine Aufgabe.
- **Abnahme dokumentieren:** abgenommen, abgenommen mit Restpunkten oder Nachbesserung nötig. Restpunkte und Nachbesserungen werden einzeln zu Aufgaben mit Frist. Nach einer Nachbesserung folgt eine erneute Übergabe; sind alle Restpunkte erledigt, gilt der Auftrag als vollständig abgenommen.
- **Abnahmeprotokoll** zum Herunterladen: vor der Abnahme als Entwurf mit Ankreuzfeldern und Unterschriftszeilen, danach mit Ergebnis, Person und Restpunkten. Ohne Preise, Stunden oder interne Notizen.
- Hinweis auf die Schlussrechnung, wenn der Zahlungsplan „nach Abnahme“ vorsieht. Die Auftragskarte der Nachkalkulation zeigt den Abnahmestand.
- Übergabe- und Abnahmeaufgaben sind keine Nachfassaufgaben und erscheinen nicht im Schritt „Nachfassen“.
- **Schemawechsel 35 → 36** (Übergaben und ihre Punkte). 641 Tests (3 neu) unter Python 3.10 und 3.13, 20 Browser-Tests (1 neu).

## 2.0.0-dev23 – Nachfassen mit Anlass, Frist und Ergebnis

Etappe C, Produktreview M16. Damit ist Etappe C abgeschlossen.

- **Versand mit Nachfassfrist:** Beim Dokumentieren des Versands wählst du, wann nachgefasst wird (Vorgabe: 7 Tage nach dem Versanddatum, nicht nach heute) und kannst einen Anlass nennen. Die Nachfassaufgabe ist mit Angebot und Chance verknüpft; der nächste Schritt der Firma folgt dieser Frist.
- **Ergebnis festhalten** am Angebot (Schritt „Nachfassen“): erreicht/Entscheidung offen, Rückfragen oder Änderungswünsche, nicht erreicht, Zusage oder Absage angekündigt, nicht weiter nachfassen. Bleibt die Entscheidung offen, ist eine neue Frist Pflicht. Ohne offene Frist zeigt das Angebot „kein nächster Schritt“.
- Alle Ergebnisse stehen im Verlauf der Firma. Rückfragen verweisen auf „Überarbeiten“; angekündigte Entscheidungen ändern den Status nicht von selbst.
- **Heute:** zeigt die Nachfassaufgabe zur gewählten Frist statt pauschal nach 7 Tagen; derselbe Schritt erscheint nicht doppelt als nächster Schritt der Firma. Der Vorschlag „Follow-up bearbeiten“ entfällt für Angebote mit eigener Nachfassaufgabe.
- Revisionen beenden verknüpfte Nachfassaufgaben des Vorgängers mit „ersetzt“, der Projektstart bzw. Abschluss mit „Entscheidung dokumentiert“.
- Fehlerbehebung: Ein ungültiger Versandweg oder eine ungültige Frist hinterlässt keinen halb gespeicherten Versand mehr in der laufenden Verbindung.
- **Schemawechsel 34 → 35** (Nachfassbezug an Aufgaben). 638 Tests (7 neu) unter Python 3.10 und 3.13, 19 Browser-Tests (1 neu). Neuer Test: jedes Modul gehört ins Release-Paket.

## 2.0.0-dev22 – Optionale Positionen im Angebot

Etappe C, Produktreview M15 Teil 2. Damit ist M15 abgeschlossen.

- **Haken „optional (nicht im Festpreis)“** an jeder Position im Angebotsbaukasten. Die Vorschau markiert die Position als „optional“; die Summe bleibt unverändert.
- **Kundendokument:** optionale Positionen stehen mit Preis in der Tabelle („(optional) … – nicht im Festpreis“) und zusätzlich im Abschnitt „Optionale Positionen“ mit dem Hinweis, dass sie nur auf ausdrücklichen Wunsch beauftragt werden.
- **Keine Doppelkalkulation:** Festpreis, monatliche Summe, Laufzeit, Zahlungsplan, interne Stunden und Kosten sowie die Rechnung „voll“ zählen nur feste Positionen.
- **Revisionen** zeigen „Neu (optional)“, „Jetzt optional“ und „Option fest übernommen“; ältere Angebote behalten das Merkmal bei der Überarbeitung.
- Versandfreigabe nennt die Anzahl optionaler Positionen als Hinweis. Mindestens eine Position muss fest im Angebot stehen.
- Kein Schemawechsel. 631 Tests (2 neu) unter Python 3.10 und 3.13, 18 Browser-Tests (1 neu). Varianten zur Wahl nebeneinander gibt es bewusst nicht (siehe Einschränkungen).

## 2.0.0-dev21 – Angebotsrevisionen mit Vorgänger und Änderungen

Etappe C, Produktreview M15 Teil 1 (Abnahmefall T11). Optionale Positionen und Varianten folgen als Teil 2.

- **„Überarbeiten (neue Fassung)“** am gespeicherten Angebot lädt Firma, Chance, Positionen, Titel, Ziel und Voraussetzungen in den Baukasten. Mit einem Grund gespeichert, entsteht die neue Fassung mit Stammnummer und Zähler (z. B. AN-2026-0003-R2) für dieselbe Firma und Chance.
- **Vorgänger und Änderungen sichtbar:** Das Kundendokument nennt „Überarbeitete Fassung 2 – ersetzt Angebot …“ und listet die wesentlichen Änderungen (neue, geänderte und entfallene Positionen mit Preisen, Summen, Zeitraum, Zahlungsplan) samt Anlass. Intern zeigt „Fassungen“ die ganze Kette.
- **Der Vorgänger bleibt unverändert gespeichert**, gilt aber als ersetzt: keine Freigabe, kein Versand, keine Zusage mehr; seine offenen Nachfassaufgaben werden beendet, Erinnerungen und Angebotssummen zählen nur die aktuelle Fassung.
- **Angenommener Stand bleibt:** Angenommene oder abgelehnte Angebote lassen sich nicht überarbeiten (Änderungen nach einer Zusage sind ein Zusatzauftrag, M18).
- Neue Angebote speichern intern ihren Bauplan; ältere werden für eine Überarbeitung aus dem Kundendokument rekonstruiert.
- **Schemawechsel 33 → 34.** 629 Tests (4 neu) unter Python 3.10 und 3.13, 17 Browser-Tests (1 neu).

## 2.0.0-dev20 – Briefing je Chance und Leistungsbereich

Etappe C, Produktreview M14 („Briefings für Medien und Software“).

- **Briefing an jeder Chance** (Firmenakte → Bedarf & Angebot → Chance → „Briefing“): Die Fragen richten sich nach den Leistungsbereichen der Chance – erkannt aus bestätigten Leistungen, gewählter Vorlage und Angeboten, auf Wunsch selbst gewählt.
  - Mediengestaltung: Anwendung, Markenrahmen, Inhalte, Gestaltung, Produktion, Nutzung und Übergabe, Entscheidung.
  - Software: Kernprozess, Nutzer und Rollen, Daten, Schnittstellen, funktionaler Umfang, Betrieb, Prüfung.
  - Analyse: Hauptziel, Zielgruppe, wichtigste Aufgaben, Erfolgskriterium.
  - Sichtbarkeit: Suchanlässe, Ausgangsmessung, Budget und Kanäle.
  Zu jeder Frage steht, was zunächst angefordert wird.
- **Jede Frage bewusst beantwortet:** „geklärt“ (mit der Angabe des Kunden), „offen“ (was fehlt, wer liefert, bis wann) oder „entfällt“. Unbeantwortetes bleibt sichtbar; die Zusammenfassung steht an der Chance.
- **Angebote führen ihre Annahmen auf das Briefing zurück:** „Angebot aus bestätigtem Bedarf“ übernimmt geklärte Angaben als Grundlage und offene Punkte als „Offene Voraussetzungen, vor Projektstart zu klären“. Im Angebotsformular übernimmt „Voraussetzungen aus dem Briefing der Chance“ dasselbe. Neue Angebote speichern intern, welche Angaben beim Erstellen galten.
- **Hinweise bei der Versandfreigabe:** unbeantwortete Briefingfragen und offene Voraussetzungen, die noch nicht im Angebot stehen.
- **Schemawechsel 32 → 33** (Briefing-Antworten je Chance). 625 Tests (9 neu) unter Python 3.10 und 3.13, 16 Browser-Tests (1 neu). Das Aufräumen der Testdatenbanken wartet jetzt auch unter Linux auf Nachzügler-Dateien (CI-Fehler in `test_ui_workday.py`).

## 2.0.0-dev19 – Bedarf und Freigabe je Chance, Chancen in Pipeline und Heute

Etappe C, Produktreview M13 Teil 2 – damit ist M13 abgeschlossen.

- **Bedarfsanalyse je Chance:** Über der Bedarfsanalyse wählst du, zu welcher Chance sie gehört. Die erste Chance nutzt wie bisher die Bedarfsanalyse der Firma; jede weitere Chance hat ihre eigene (Problem, Auswirkung, bisherige Lösung, Ergebnis, Zeitrahmen, Entscheidungsweg, Budget). Der Wechsel lädt die passenden Angaben und gilt nicht als ungespeicherte Eingabe.
- **Freigabe je Chance:** „Bedarf dieser Chance bestätigen“ steht direkt an der Chance (Weg, was bestätigt wurde, Leistung aus dem Katalog). Die Freigabe einer Chance gilt nicht für eine andere. „Bedarf wieder öffnen“ ebenso je Chance.
- **Angebot aus dem Bedarf einer Chance:** übernimmt deren bestätigte Leistungen und ordnet das Angebot der Chance zu. Versandfreigabe, Versand und Zusage prüfen den Bedarf der Chance des Angebots – nicht mehr den der Firma.
- **Pipeline je Chance:** Offene Chancen erscheinen als eigene Karten mit Firmenname und Chancentitel in ihrer Spalte; ihre Phase lässt sich dort ändern („verloren“ mit Grund). Eine Firma mit offenen Chancen erscheint über diese Karten, Kunden bleiben zusätzlich in „Gewonnen“ sichtbar.
- **Heute:** Fällige nächste Schritte offener Chancen stehen in der Wiedervorlage und damit in der Fokusliste – ohne den Schritt der Firma doppelt zu zeigen.
- **Behoben vor dem Release:** Eine zweite Deklaration in `formguard.js` hätte das Skript und damit den Eingabeschutz stillgelegt; der Browser-Test hat es gefunden, ein Strukturtest verhindert die Wiederholung.
- **Schemawechsel 31 → 32** (Bedarfsfelder an der Chance). 616 Tests (6 neu) unter Python 3.10 und 3.13, 15 Browser-Tests (1 neu).

## 2.0.0-dev18 – Mehrere Verkaufschancen je Firma (Teil 1)

Etappe C, Produktreview M13 Teil 1. Eine Firma kann jetzt mehrere mögliche Projekte haben, ohne dass sie doppelt angelegt werden muss.

- **Chancen in der Firmenakte:** Im Reiter „Bedarf & Angebot“ stehen oben die Chancen der Firma. Jede hat eine eigene Phase (Bedarf klären, Termin, Angebot, Gewonnen, Verloren), eine Leistung aus dem Katalog, einen nächsten Schritt mit Datum, eigene Angebote und Termine. „＋ Neue Chance“ legt ein weiteres Projekt mit eigenem Anliegen, Ergebnis und Zeitrahmen an.
- **Verlust ohne Nebenwirkung:** „Verloren“ verlangt einen Grund. Der Verlust einer Chance beendet keine andere und ändert keine Rechnung.
- **Angebote und Termine gehören zu einer Chance:** Im Angebot und beim Termin wählst du die Chance. Bei einer offenen Chance ist sie vorausgewählt, bei mehreren musst du wählen; ein Angebot kann ausdrücklich eine neue Chance beginnen. Versand hebt die Chance auf „Angebot“, die Zusage macht nur diese Chance „gewonnen“.
- **Firmenphase folgt den Chancen:** Offene Chancen heben sie an. Eine gewonnene Chance macht die Firma zum Kunden, eine neue Chance stuft einen Kunden nicht zurück. Erst wenn alle Chancen verloren sind, gilt die Firma als verloren – mit dem Grund der zuletzt verlorenen Chance. Wird die Firma selbst auf „verloren“ gesetzt, schließen ihre offenen Chancen mit demselben Grund. Eine Sperre bleibt immer bestehen.
- **Bestand:** Beim ersten Start bekommt jede Firma mit Gespräch, Termin, Bedarf oder Angebot genau eine erste Chance; vorhandene Angebote und Termine werden ihr zugeordnet. Nichts wird gelöscht oder umgerechnet, die Firmenphase bleibt unverändert. Vor dem Update wird automatisch gesichert.
- **Noch nicht je Chance (Teil 2, dev19):** Die ausführliche Bedarfsanalyse und die Freigabe „Bedarf bestätigt“ gelten weiterhin für die Firma; die erste Chance zeigt sie an. Pipeline, Heute und Firmenliste zeigen weiter Firmen, nicht einzelne Chancen.
- **Schemawechsel 30 → 31.** 610 Tests (9 neu) unter Python 3.10 und 3.13, 14 Browser-Tests (1 neu).

## 2.0.0-dev17 – Versandfassung, Projektstart nach Zusage, klare Begriffe der Website-Bewertung

Das P0-Paket aus den Ergänzungen zum Produktreview (13.11.2026): Leitfaden Kundenonboarding (M35, M36) und Bewertungsmodell (M27). Vor dem Umbau auf mehrere Verkaufschancen (M13).

- **Versandfassung statt Dauer-Entwurf (M35):** Ein gespeichertes Angebot ist zunächst ein Entwurf – Export und Dateiname sagen das sichtbar. „Versandfassung freigeben“ prüft automatisch Steuerstatus, bestätigten Bedarf, zulässigen Kontakt, Bindefrist und ob interne Werte im Kundendokument stehen, und verlangt vier selbst bestätigte Prüfpunkte (Empfänger, Inhalt, Lesbarkeit, nächster Schritt). Danach gibt es den Export ohne Entwurfshinweis mit **Stand-Kennung** im Dokument und im Dateinamen (`Angebot_AN-…_Stand-xxxxxxxx.md`).
- **Versand und Zusage mit Ereignis, Zeitpunkt, Weg und Stand:** „Als versendet dokumentieren“ (E-Mail, Post, persönlich, Portal) und „Zusage/Absage dokumentieren“ (Weg, Person, Datum, Notiz) gehen nur für einen freigegebenen Stand. Die freie Statusauswahl ist ersetzt; dokumentierte Ereignisse lassen sich nicht zurückdrehen. SignalDesk versendet weiterhin nichts.
- **Projektstart nach der Zusage (M36):** SignalDesk schlägt Startaufgaben vor – Auftrag persönlich bestätigen, Startgespräch, Materialien und Nutzungsrechte (Medien), Zugänge und Testdaten (Software), Kurzüberblick, erster Zwischenstand – jeweils mit Angebotsnummer im Titel. Offene Nachfassaufgaben zu diesem Angebot werden aufgelistet und auf Wunsch beendet. Angelegt wird nur, was du bestätigst; ein zweiter Klick legt nichts doppelt an. Bei einer Absage lassen sich die Nachfassaufgaben ebenso beenden.
- **Begriffe der Website-Bewertung (M27):** Die Werte heißen jetzt „Auffällig: Design & UX“ usw. (in %, höher = mehr belegte Hinweise) und „Akquise-Priorität“ statt „Gesamt“ – eine Qualitätsnote für Websites gibt es bewusst nicht. „Passung zur Agentur“ im Scoring heißt „Profilnähe“, damit es nicht mit der Passung A/B/C der Firmenakte verwechselt wird. Eine kurze Leseanleitung steht unter den Werten.
- **Unbekannt zählt nicht als schlecht:** Eine Firma ohne Branche bekam bisher eine niedrige Profilnähe (25). Jetzt fällt die unbekannte Branche aus der Rechnung; fehlen Branche und Größe, bleibt die Profilnähe offen und die Priorität wird ohne sie berechnet.
- **Schemawechsel 29 → 30** (neue Spalten am Angebot; vor dem Update wird automatisch gesichert). Ältere Angebote bleiben unverändert und gelten als Entwurf, bis du sie freigibst. 601 Tests (16 neu) unter Python 3.10 und 3.13, 13 Browser-Tests (1 neu); ältere Tests dokumentieren den Versand jetzt nach einer Freigabe.

## 2.0.0-dev16 – Ein zentraler Leistungskatalog

Etappe C, Teil 1 aus dem Produktreview vom 13.11.2026 (Maßnahme M12), ergänzt um passende Teile aus dem Bewertungsmodell für Websites und dem Leitfaden zum Kundenonboarding vom selben Tag. Die übrigen Empfehlungen beider Dokumente stehen als M27–M39 in `docs/ROADMAP.md`.

- **Ein Katalog statt vier Listen:** Bisher gab es fünf Angebote, sechs Pakete mit fünf Zusatzleistungen und 26 Baukasten-Leistungen mit jeweils eigenen Titeln, Preisen und Zeiträumen. Jetzt sind die 26 Leistungen die einzige Quelle; die sechs Vorlagen (Pilot, Conversion-Sprint, Brand, Growth Care, Kundenportal, Automatisierung) sind Zusammenstellungen davon. Die Zuordnung steht in `docs/LEISTUNGSKATALOG.md` und unter *Einstellungen → Leistungen & Preise → Herkunft*.
- **Eine geänderte Leistung wirkt überall gleich:** Vorlagenpreis, Paketempfehlung in der Firmenakte, neues Angebot, Angebotskarten der Hilfe und die Auswahl „Leistung“ rechnen mit denselben Katalogwerten – auch ohne Neuladen. Die Vorlagen-Auswahl im Angebot zeigt den aktuellen Preis.
- **Gespeicherte Angebote bleiben unverändert** in Text und Preis. Neue Angebote merken sich intern den Katalogstand.
- **Bitte prüfen:** Die früheren Paketpreise („ab 18.500 €“ für das Kundenportal, „ab 790 €“ für Growth Care) stimmten nicht mit dem überein, was der Baukasten für dieselbe Vorlage berechnet (13.510 € bzw. 370 € je Monat). Alle Stellen zeigen jetzt den Baukastenpreis; abweichende eigene Preise bitte über die Katalogwerte festlegen.
- **Korrekturschleifen je Leistung:** eigenes Feld je Leistung und Umfang, in den Einstellungen änderbar, im Kundendokument je Position zusammengeführt. Für gestalterische Leistungen ohne festgelegte Zahl erscheint intern ein offener Punkt – nie im Kundendokument (Prüffall K01 dauerhaft gelöst).
- **Kein Widerspruch bei Ausschlüssen:** „Texte (separate Position)“ und ähnliche Hinweise entfallen, wenn die Leistung selbst im Angebot steht.
- **Vor dem Versand klären:** Intern listet das Angebot je Leistungsbereich die offenen Punkte – bei Medien Nutzungsumfang, Quelldateien und Produktion, bei Software Betrieb, Schnittstellen, Datenübernahme und Übergabe.
- **Zahlungsplan als Einstellung:** Anzahlung bei Beauftragung (Startwert 40 %) ist einstellbar, im Angebot sichtbar und intern als „mit dem Kunden vereinbaren“ markiert. Die Abschlagsrechnung übernimmt den Prozentsatz aus dem Angebot statt fester 40 %.
- **Webseiten-Analyse abgegrenzt:** eine Person prüft aus vier Blickwinkeln; Nutzerstudie, umfassende Technik- oder Barrierefreiheitsprüfung und Wirkungszusagen sind ausdrücklich nicht enthalten. Stunden unverändert.
- Der frühere Paket-Rechner ist entfernt; ältere Aufrufe mit Paket und Zusatzleistungen rechnen über den Katalog, Kostensatz-, Risiko- und Margenangaben werden mit Erklärung abgelehnt. Laufende Betreuungsleistungen nennen „fortlaufend, monatlich“ als Zeitraum.
- Kein Schemawechsel, keine Datenmigration nötig (Kennungen unverändert). 585 Tests (15 neu) unter Python 3.10 und 3.13, 12 Browser-Tests (1 neu); ältere Tests des Paket-Rechners rechnen jetzt über den Katalog.

## 2.0.0-dev15 – Heute als Fokusliste, Arbeitsansichten, geführter Einstieg

Etappe B, Teil 2 aus dem Produktreview vom 13.11.2026 (Maßnahmen M08, M09, M11) – damit ist Etappe B abgeschlossen.

- **Heute zeigt oben die drei nächsten Schritte** mit Grund und Frist („Warum jetzt: seit 2 Tagen überfällig“, „Termin morgen 09:00“, „heute zugesagt“). Reihenfolge: überfällige Zusagen, Termine, heute Zugesagtes, Nachfassen – erst danach neue Akquise. Eine Rückrufzusage wird nie von einer guten Passungsnote verdrängt. Ein Klick führt direkt zur Firma oder zum Angebot.
- **Tagesplan und Tagesabschluss** sind jetzt aufklappbar und stehen weiter unten.
- **„Erste Schritte“ für den Einstieg:** Leistungen & Preise, Zielkunden, Arbeitszeiten, erste Firma oder Anfrage – jeweils mit echter Prüfung und direktem Sprung in die Einstellungen. Ein Recherchelauf ist nicht nötig. Die Karte verschwindet, sobald alles eingerichtet ist, oder lässt sich ausblenden.
- **Firmenliste als Arbeitsmenge:** Spalten Firma, nächster Schritt mit Fälligkeit („heute“, „überfällig seit …“), Phase, Passung und letzter Kontakt. Kaufsignal und Leistung lassen sich zuschalten.
- **Arbeitsansichten als Chips** mit Trefferzahl: Heute fällig, Ohne nächsten Schritt, Angebote nachfassen, Recherche prüfen, Passung A/B, Bestandskunden. Aktive Filter und „x von y Firmen“ sind immer sichtbar. Die Ansicht steht in der Adresse (`?ansicht=heute`).
- **Eigene Ansichten speichern:** aktuelle Filterkombination unter einem Namen, wieder öffnen, löschen. Gespeichert werden nur die Filter.
- **Leerzustände mit nächstem Schritt:** „Noch keine Firmen“ unterscheidet sich von „Keine Firma passt zu diesen Filtern“ (mit „Filter zurücksetzen“); leere Pipeline, leere Kontaktliste und leere Wiedervorlage bieten den passenden Knopf. Der Knopf oben heißt bei leerem Tag „Nichts offen“ statt „Alles erledigt“.
- **Behoben:** Der Startfehler aus dev14 war nicht vollständig behoben – verzögerte Skripte laufen, wenn die Seite schon als „interaktiv“ gilt, die Prüfung griff deshalb nicht. Der Start wartet jetzt immer auf das vollständige Laden; ein Browser-Test lädt dafür ein Skript absichtlich verzögert.
- Kein Schemawechsel. 570 Tests (9 neu) unter Python 3.10 und 3.13, 11 Browser-Tests (1 neu); zwei ältere Browser-Tests öffnen jetzt den eingeklappten Tagesabschluss bzw. schalten die Spalte „Leistung“ zu.

## 2.0.0-dev14 – Sechs Bereiche, eigener Bereich Einstellungen, direkte Adressen

Etappe B, Teil 1 aus dem Produktreview vom 13.11.2026 (Maßnahmen M06 und M07).

- **Sechs Bereiche statt 16 Einträgen und „Erweitert“:** Heute · Finden · Firmen · Angebote · Abrechnen · Einstellungen. Jeder Bereich öffnet seine Standardansicht; die übrigen Ansichten stehen oben als Reiter (z. B. Firmen: Firmenliste · Pipeline · Datenpflege). Alle bisherigen Ziele bleiben erreichbar – die Zuordnung steht in `docs/ROADMAP.md`. „Hilfe & Gesprächsleitfaden“ ist ein kleines festes Ziel unten in der Seitenleiste.
- **Eigener Bereich „Einstellungen“:** Darstellung, Zeiten & Erreichbarkeit, Leistungsprofil, Zielkundenprofil, Leistungen & Preise (Stundensatz, Mindestverdienst, Katalog), Recherche (Gewichte, Fristen, Abruftechnik) und Daten & Zugang (Login, Sicherung, Offline) an einem Ort, mit Sprungleiste. Unter „Angebote“ führt ein Verweis zu den Preisen.
- **„Datenqualität & System“ aufgeteilt:** Änderungen, Veraltung, Löschfristen und Dubletten heißen jetzt *Datenpflege* (unter Firmen); wiederkehrende Recherche-Aufträge stehen unter *Finden → Recherche & Berichte*.
- **Direkte Adressen:** Jede Ansicht hat eine Adresse (z. B. `#/firmen/pipeline`), eine geöffnete Firma zusätzlich `?firma=…`, die Firmenliste ihre Filter (`?suche=…&phase=…`). Neuladen bleibt an derselben Stelle, Zurück und Vor wechseln zwischen Ansichten, Zurück schließt eine geöffnete Firma und zeigt die gefilterte Liste (Abnahmefall T05).
- **Behoben:** Beim langsamen Laden konnte der Start mit „renderPipeline is not defined“ abbrechen, weil die App vor allen Skripten loslief. Sie wartet jetzt, bis die Seite vollständig geladen ist.
- **Behoben:** Die Darstellung wurde erst nach der Antwort an den Browser festgeschrieben; eine sofort folgende Anfrage konnte noch den alten Stand lesen (in der CI aufgefallen). Jetzt wird vor der Antwort gespeichert.
- Kein Schemawechsel, keine Daten geändert. 561 Tests (7 neu) unter Python 3.10 und 3.13, 10 Browser-Tests (1 neu); fünf ältere Browser-Tests navigieren jetzt über die neuen Bereiche.

## 2.0.0-dev13 – Produktreview Etappe A: Eingabeschutz, Öffnungsfokus, eine Bewertung

Setzt die Etappe A aus dem externen Produktreview vom 13.11.2026 fort (Maßnahmen M01, M03, M04, Rest von M05, M26).

- **Nichts geht mehr still verloren (M01):** Wer im Lead-Dialog etwas ändert und ihn per ✕, „Abbrechen“, Escape oder Klick daneben schließt, wird gefragt: *Speichern*, *Weiter bearbeiten* oder *Verwerfen*. Im Kopf steht, welcher Bereich ungespeichert ist. Verlässt man den Dialog über einen Sprung in eine andere Ansicht, kommen die Eingaben beim nächsten Öffnen derselben Firma zurück – nur im Arbeitsspeicher, nicht im Browser-Speicher. Beim Schließen des Browserfensters warnt der Browser. Es gibt kein automatisches Speichern.
- **Richtiger Fokus (M03):** Eine bestehende Firma öffnet im Überblick (Fokus auf dem Reiter), nur eine neue Firma im Namensfeld. Nach dem Schließen steht der Fokus wieder auf der Zeile, von der aus geöffnet wurde.
- **Eine Bewertung statt zwei (M04):** Die Lead-Liste zeigt die Passung (A/B/C/?) mit demselben Erklärtext wie Akte und Pipeline und sortiert danach. Die alte Punktzahl („25/100“) erscheint nicht mehr in Liste und Pipeline; sie bleibt unter „Stammdaten“ eingeklappt nachvollziehbar.
- **Keine erfundenen Vorgaben (M04):** Neue Firmen bekommen keine vorbelegte Branche und keine vorgewählte Leistung mehr – im Formular, über die Schnittstelle, beim CSV-Import, über „Bericht für Website“, die Impressumsprüfung und die Übernahme aus der Firmensuche (bisher dort immer „Conversion- & Web-Sprint“). Bestehende Firmen behalten ihre Werte.
- **Verständliche Begriffe (M05, U11):** Phasen erscheinen mit Namen statt internem Schlüssel. Der Gesprächsentwurf behauptet keinen Anlass („… Kein überprüftes Signal aufgefallen“) und keine Leistung, die nicht dokumentiert ist, sondern zeigt Platzhalter. Der Tagesplan meldet auf einer leeren Installation nicht mehr „5 von 6 erledigt“, sondern unterscheidet „nichts offen“ von „erledigt“. Zwei Hinweistexte entsprechen jetzt dem tatsächlichen Verhalten.
- **Prüffall K01 behoben:** Ein Baukasten-Angebot nannte im Kundenteil pauschal „2 Korrekturschleifen“, auch wenn die Position „1 Korrekturschleife“ vorsah. Korrekturschleifen gelten jetzt je Leistung wie im Umfang angegeben. Ältere Angebote bleiben unverändert.
- **Roadmap abgeglichen (M26):** Status je Maßnahme M01–M26 mit Version, Abnahme und nächstem Hindernis; Abgleich mit jeder Empfehlung des Reviews; Launch-Audit und Praxistest 70191 tragen einen Versionsbezug.
- Kein Schemawechsel. 554 Tests (11 neu) unter Python 3.10 und 3.13, 9 Browser-Tests (1 neu).

## 2.0.0-dev12 – Firmenakte mit Reitern, einheitliche Statusmarken

- **Firmenakte mit fünf Reitern:** Überblick · Kontakt & Verlauf · Bedarf & Angebot · Recherche · Stammdaten. Der Dialog war rund 7.800 Pixel lang (etwa zehn Bildschirme); der längste Reiter hat jetzt rund 2.300 Pixel.
- **Kopf bleibt stehen:** Firmenname, Phase, Passung, Belegabdeckung und der Knopf für die nächste Aktion sind beim Scrollen und in jedem Reiter sichtbar.
- Im Reiter „Kontakt & Verlauf“ steht das Aktivitätsprotokoll oben, weil man es am häufigsten braucht.
- Sprünge aus „Als Nächstes“ öffnen den passenden Reiter, z. B. „Rechtsgrundlage klären“ die Stammdaten.
- Reiter per Tastatur: Pfeiltasten, Pos1 und Ende. Ein neuer Lead öffnet wie bisher nur das Formular.
- **Einheitliche Statusmarken:** fünf Stufen – erledigt ✓, Hinweis !, Problem ✕, offen ○, neutral –. Jede trägt ein Symbol, damit die Bedeutung nicht nur an der Farbe hängt. Bisher war „passt nicht“ an einer Stelle grau, an anderer rot; Probleme sind jetzt überall rot.
- Kein Schemawechsel, keine Daten geändert. 543 Tests (6 neu) unter Python 3.10 und 3.13, 8 Browser-Tests (1 neu).

## 2.0.0-dev11 – Darstellung: Themes, Hell/Dunkel, Kompakt

- **Vier Themes, jedes hell und dunkel:** Klassisch (bisheriger Stand), Schiefer (kühles Grau, blauer Akzent), Sand (warme Erdtöne, Terrakotta) und Kontrast (kräftige Linien, höchster Kontrast). Auswahl unter *Erweitert → Datenqualität & System → Darstellung*, mit Vorschau-Kacheln.
- **Hell, Dunkel oder „Wie System“**; oben rechts schaltet ein Knopf direkt zwischen Hell und Dunkel um. Die Seite erscheint gleich im richtigen Modus, ohne helles Aufblitzen.
- **Dichte „Kompakt“:** blendet die Erklärtexte unter den Überschriften aus und verringert Abstände. Bei 1366 × 768 Pixeln schrumpft der Seitenkopf von 255 auf 162 Pixel; in der Lead-Liste sind 8 statt 5 Zeilen ohne Scrollen sichtbar.
- Die Wahl wird in der Datenbank gespeichert und gilt für die ganze Installation, auch nach einem Portwechsel oder in einem anderen Browser.
- **Lesbarkeit geprüft:** Für jedes Theme in Hell und Dunkel prüft ein Test 24 Farbpaare gegen die WCAG-Kontrastwerte (AA, Theme Kontrast AAA). Graue Nebentexte sind dafür etwas dunkler geworden.
- Technisch: Die 284 festen Farbwerte im Stylesheet sind in 42 Rollen zusammengefasst. Ein Test verhindert neue feste Farben. „Klassisch“ behält die Markenfarben; einzelne Grautöne und Linien sind leicht verschoben.
- Vorschläge für mehr Übersicht mit Messwerten: `docs/UI_UX_VORSCHLAEGE.md`. Neue Roadmap: `docs/ROADMAP.md`.
- Kein Schemawechsel. 537 Tests (10 neu) unter Python 3.10 und 3.13, 7 Browser-Tests (1 neu).

## 2.0.0-dev10 – Datenschutz für Betriebe ohne Rechtsform

- **Nachweis mit Löschfrist:** Jede Übernahme eines Betriebs ohne Rechtsform legt einen Datenschutz-Nachweis an – Zweck, Rechtsgrundlage, Quelle, Löschfrist (2 Jahre). Auch bei „Alle Treffer übernehmen“. Bereits übernommene Betriebe bekommen ihn beim Update nachträglich, mit Frist ab dem Anlagedatum.
- **Passender Hinweistext nach Art. 14 DSGVO** für Betriebe (Name und Geschäftsanschrift statt Ansprechpartner und Funktion); zum Kopieren in der Firmenakte und unter „Import & Prüfung“.
- **Firmenakte:** Hinweis „Möglicher Personenbezug“ mit Löschfrist, Art.-14-Stand und den Knöpfen „Hinweistext kopieren“, „Als informiert vermerken“, „Frist verlängern“.
- **Frist verlängern nur mit Grund** (wird im Nachweis vermerkt), z. B. „Gespräch vereinbart“.
- **Nach Ablauf der Frist:** „Betrieb löschen“ entfernt den Lead mit Notizen, Aufgaben und Funden. Ausgenommen sind Kunden (Aufbewahrungspflichten) und Firmen im laufenden Gespräch. Eine Sperre bleibt bestehen; ohne Sperre darf der Betrieb bei einer späteren Suche neu auftauchen. Der Löschnachweis enthält keine Personendaten.
- Schema 29 (eine Spalte ergänzt). 527 Tests (9 neu) unter Python 3.10 und 3.13, 6 Browser-Tests.

## 2.0.0-dev9 – Größere Zielgruppe: Betriebe ohne Rechtsform, Branche aus OpenStreetMap, alle Treffer übernehmen

- **Betriebe ohne Rechtsform im Namen sind standardmäßig dabei** (z. B. „Elektro Müller“) und in der Trefferliste als „ohne Rechtsform“ gekennzeichnet. Bisher wurden sie ausgelassen. Abschaltbar im Suchformular; filterbar und gezählt.
- Übernommene Betriebe ohne Rechtsform tragen im Lead den Hinweis, dass der Firmenname ein Personenname sein kann. Der Rechtsstatus bleibt „unbekannt“.
- **Branche aus dem OpenStreetMap-Merkmal:** Ein Betrieb mit `craft=electrician` ist Elektroinstallation – auch ohne Branchenfilter und ohne Raten aus dem Namen. Unbekannte Merkmale bleiben ohne Branche.
- **„Alle Treffer übernehmen“:** übernimmt alle offenen Treffer des aktuellen Filters in einem Zug, auch über mehrere Seiten (je Durchgang bis 1.000). Gesperrte Firmen und Dubletten werden übersprungen – auch wenn der Widerspruch erst nach der Suche eingetragen wurde.
- **Öffnungszeiten steuern die Reihenfolge:** Unter „Als Nächstes kontaktieren“ rücken laut OpenStreetMap gerade geschlossene Betriebe nach hinten. Unbekannte Öffnungszeiten gelten nicht als geschlossen.
- 516 Tests (8 neu) unter Python 3.10 und 3.13, 6 Browser-Tests.

## 2.0.0-dev8 – OpenStreetMap ausgebaut: PLZ-Schätzung, Lage der Gebäude, Telefon und Öffnungszeiten

- **Betriebe ohne PLZ-Angabe fehlen nicht mehr:** Liegt höchstens 250 m entfernt ein Betrieb mit PLZ, bekommt der Eintrag dessen PLZ als Schätzung. In der PLZ-genauen Suche erscheinen solche Treffer und werden als geschätzt ausgewiesen. Die eigene Angabe eines Eintrags wird nie überschrieben.
- **Gebäudeumrisse haben eine Lage:** Betriebe, die in OpenStreetMap als Umriss erfasst sind, bekommen die Koordinaten ihres ersten Eckpunkts. Sie erscheinen damit auch in der Umkreissuche.
- **Telefon und Öffnungszeiten in der Firmenakte:** Stammt eine Firma aus dem lokalen OpenStreetMap-Bestand, zeigt die Erreichbarkeit ihre Öffnungszeiten mit „jetzt geöffnet / geschlossen“ und – wenn keine belegte Nummer vorliegt – die Telefonnummer. Beides ist als „OpenStreetMap (ungeprüft)“ gekennzeichnet; ins Firmenprofil wird nichts geschrieben.
- Öffnungszeiten werden nur ausgewertet, wenn sie eindeutig lesbar sind; sonst bleibt die Aussage „unbekannt“.
- 508 Tests (4 neu) unter Python 3.10 und 3.13, 6 Browser-Tests.

## 2.0.0-dev7 – OpenStreetMap manuell und offline

- **OpenStreetMap läuft manuell:** Die Firmensuche fragt die öffentlichen Server nicht mehr von selbst ab. Sie waren im Praxistest bei jedem Versuch überlastet. Online-Abfrage nur noch per Häkchen.
- **Lokaler Auszug:** Eine `.osm.pbf`-Datei (z. B. Regierungsbezirk Stuttgart von Geofabrik) einmal einlesen, danach sucht SignalDesk offline und sofort. Ohne Zusatzprogramm.
- **Handexport:** Für eine PLZ oder einen Ort öffnet ein Klick die fertige Abfrage in Overpass Turbo; die gespeicherte Datei (`.json`, `.geojson`) liest SignalDesk ein.
- **„OpenStreetMap nutzbar machen“** unter „Firmen finden“: Stand des lokalen Bestands, drei Wege mit Aufwand, Datei einlesen.
- **Ganze Stadt:** Ein Ortsname mit „nur dieser Ort“ deckt beim lokalen Bestand alle Postleitzahlen der Stadt ab.
- Gespeichert werden nur benannte Betriebe, dazu Telefon und Öffnungszeiten; keine E-Mail-Adressen, keine Betreibernamen.
- Die Suche bleibt ohne festgelegte Branche; die Roadmap sieht keine Branchen-Voreinstellung mehr vor.
- Schema 28. 504 Tests (13 neu) unter Python 3.10 und 3.13, 6 Browser-Tests (1 neu). Anleitung: `docs/OPENSTREETMAP_LOKAL.md`.

## 2.0.0-dev6 – Praxistest 70191: PLZ-genaue Suche, faires Budget

- **Behoben – PLZ wurde ignoriert:** „70191“ mit „nur dieser Ort“ lieferte ganz Stuttgart (300 Treffer, davon 2 in 70191). Jetzt gilt genau diese PLZ; nach der Behebung lagen 56 von 56 Treffern in 70191.
- **Behoben – die erste Quelle verbrauchte das ganze Budget:** OpenStreetMap lief dadurch nie. Das Budget wird jetzt auf die gewählten Quellen verteilt; Ungenutztes geht an die nächste Quelle.
- OpenStreetMap fragt bei einer PLZ das PLZ-Gebiet ab statt einen Umkreis um die Stadtmitte.
- Bericht mit allen Messwerten und Folgerungen: `docs/PRAXISTEST_70191.md`.
- 491 Tests (6 neu), geprüft unter Python 3.10 und 3.13.
- Website-Zuordnung und Handwerks-Abdeckung waren in der Testumgebung nicht messbar; siehe Bericht.

## 2.0.0-dev5 – Nachkalkulation

- **Nachkalkulation** unter „Angebote & Preise“: Für jedes angenommene Angebot erfasst du die tatsächlich gebrauchten Stunden (einzeln oder als Sammeleintrag) und siehst kalkuliert, gebraucht und übrig.
- **Auftrag abschließen** mit den tatsächlichen Fremdkosten. SignalDesk zeigt deinen Verdienst je Stunde und ob er über deinem Mindestverdienst liegt.
- **Überziehung fällt auf:** Sobald du mehr Stunden gebraucht hast als kalkuliert, steht der Auftrag oben.
- **Lernwert ab drei abgeschlossenen Aufträgen:** „Im Mittel brauchst du X % mehr Zeit als kalkuliert.“
- **Auslastung genauer:** Aufträge mit erfassten Zeiten zählen mit den verbleibenden Stunden, abgeschlossene gar nicht mehr. Bisher zählte jedes angenommene Angebot acht Wochen lang voll und fiel danach ganz heraus.
- Abgeschlossene Aufträge sind gegen Änderungen geschützt, bis du sie wieder öffnest. Angebote und Rechnungen bleiben unberührt; der Kunde sieht nichts davon.
- Schema 27 (zwei Tabellen ergänzt). 485 Tests (10 neu) und 5 Browser-Tests (1 neu).
- Kein abgeschlossenes Release. Nicht an echten Firmen geprüft.

## 2.0.0-dev4 – Läuft wieder auf Python 3.10/3.11 und unter Windows-CI; aufgeräumt

- **Behoben – SignalDesk startete unter Python 3.10 und 3.11 nicht** (Syntaxfehler in der Impressumserkennung, seit Anfang November). Ein Test verhindert die Wiederholung.
- **Behoben – Abbruch in Windows-Konsolen ohne UTF-8:** Einrichtung und Installationsprüfung scheiterten an Sonderzeichen in der Ausgabe.
- **Behoben – Datenbank blieb nach dem Start kurz gesperrt:** Beim Prüfen der Schema-Version wurde eine Verbindung nicht geschlossen. Unter Windows konnte die Datei dadurch nicht sofort gesichert, ersetzt oder gelöscht werden.
- **Behoben – Sicherheitskopie konnte überschrieben werden:** Zwei Wiederherstellungen in derselben Sekunde nutzten denselben Dateinamen. Jetzt bleibt jede Sicherheitskopie erhalten.
- Recherche-Worker lassen sich sauber beenden (`jobs.stop_workers`).
- **Eingang mit Löschfrist:** Erledigte Einträge verlieren nach 90 Tagen (einstellbar) Name, Kontakt und Notiz; die Antwortzeit-Statistik bleibt.
- **Note in den Firmen-Berichten.**
- **README neu:** 82 Zeilen statt 432; die Versionsgeschichte steht im Changelog. **Roadmap neu** auf dem heutigen Stand.
- Ordner `ausgabe/` mit alten Paketen entfernt.
- 475 Tests (6 neu), geprüft unter Python 3.10, 3.12 und 3.13.
- Kein abgeschlossenes Release. Nicht an echten Firmen geprüft.

## 2.0.0-dev3 – Eigene Erreichbarkeit und Auslastung

- **Eingang & Rückrufe** ganz oben auf „Heute“: verpassten Anruf oder Anfrage in einem Schritt festhalten, auch ohne angelegte Firma. Die Rückruffrist ergibt sich aus deinen Zeiten; Fälliges steht zusätzlich in der Wiedervorlage.
- **Als Nächstes kontaktieren:** Firmen mit Passung A oder B in den Phasen Qualifiziert bis Rückmeldung, A zuerst, „jetzt passendes Zeitfenster“ vorn. Gesperrte, ausgeschlossene und ausgeschöpfte Firmen erscheinen nicht.
- **Auslastung** aus den kalkulierten Stunden angenommener und offener Angebote gegen deine Wochenstunden.
- **Deine Zeiten** (Datenqualität & System): Arbeitstage, Rückruf- und Terminzeiten, Abwesenheiten. Daraus entstehen Terminvorschläge und Textbausteine (Mailbox-Ansage, Signaturzeile, Abwesenheitsnotiz) zum Kopieren.
- **Die Note steuert die Reihenfolge:** Pipeline-Karten sortieren nach Passung und zeigen die Note; die Firmenakte nennt die Passung statt des alten Scores.
- Antwortzeit als Kennzahl: mittlere Zeit bis zur Rückmeldung und Anteil innerhalb der Frist.
- Schema 26 (Tabelle für den Eingang). 469 Tests (15 neu) und 4 Browser-Tests (1 neu).
- Kein abgeschlossenes Release. Nicht an echten Firmen und nicht unter Windows geprüft.

## 2.0.0-dev2 – Kundenbewertung und Erreichbarkeit

- **Zielkundenprofil** (Datenqualität & System): Zielbranchen und Ausschlüsse aus dem Branchenkatalog, Wunschgröße, Standort und Einzugsgebiet, Mindestauftrag, Wochenstunden, Zahl der Anrufversuche.
- **Bewertung in drei getrennten Teilen** in der Firmenakte:
  - Passung vor dem Gespräch als A, B oder C mit Begründung je Kriterium;
  - Qualifizierung nach dem Gespräch (Bedarf, Budget, Zeitpunkt, Entscheider, Auftragswert) mit offenen Fragen fürs nächste Gespräch;
  - Erreichbarkeit mit belegten Kontaktwegen und bisherigen Versuchen.
- **Unbekannt ist nicht schlecht:** Fehlende Angaben senken die Note nicht. Bei zu dünner Datenlage gibt es keine Note.
- **K.-o.-Kriterien:** Kontaktsperre, Auflösung laut Register, ausgeschlossene Branche, kein Budget, kein Bedarf.
- **Behoben – „Nicht erreicht“ und „Mailbox“ blieben folgenlos:** Jetzt entsteht eine Wiedervorlage an einem Werktag zu einer anderen Tageszeit. Nach der eingestellten Zahl an Versuchen schlägt SignalDesk Kanalwechsel oder Parken vor.
- **„Verloren“ nur mit Grund**, dazu eine Übersicht der Verlustgründe und der Erreichbarkeit nach Tageszeit (erst ab 20 Versuchen).
- **Note in der Lead-Liste.** Der bisherige Lead-Fit bleibt unverändert bestehen.
- Schema 25 (Zeitfenster je Anrufversuch, Verlustgrund). 454 Tests (28 neu) und 3 Browser-Tests (1 neu).
- Neu: `docs/LAUNCH_AUDIT.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/SELF_REVIEW_LOG.md`, zwei Projekt-Skills unter `.claude/skills/`.
- Kein abgeschlossenes Release. Nicht an echten Firmen und nicht unter Windows geprüft.

## 2.0.0-dev1 – Entwicklungsstand für die Übergabe

- Regelbasierte Inhaltsrecherche mit gespeicherten Themenprofilen, zusätzlichen Suchbegriffen und Profilstand im Bericht.
- Manuell gefundene Website als ungeprüften Vorschlag eintragen; Registertreffer ohne Registergericht benötigen Bestätigung.
- Fehler und unvollständige Website- sowie Karriereprüfungen sichtbar machen; Website-Aufträge erneut ausführbar.
- Erfolgreiche Berichtsschritte bei Wiederholung erhalten, Empfehlungen anschließend neu verknüpfen.
- Karriere-Überwachung berücksichtigt das gewählte Intervall. Fehlgeschlagene Prüfungen gelten nicht als aktueller Erfolg.
- Unbekannter Portalbedarf wird nicht als Mangel bewertet; neue Bewertungslogik erhält eine eigene Score-Version.
- Kein abgeschlossenes Release: Live-Test und weitere Grenzen siehe `docs/UEBERGABE_FABLE.md` und `docs/V2_ENTWICKLUNGSSTAND.md`.

## 1.19.0 – Masterplan 2.0: Sprint 6 (Windows-Release, Offline, Wiederherstellung) + Firmendaten-Übertragung

- **Behoben – automatische Datenübertragung ins Firmenprofil:**
  - **Website-Vorschläge:** Die Website wurde bei „Übernehmen“ entfernt und die gelesenen Daten verworfen. Jetzt lässt sich der Vorschlag in der Firmenakte bestätigen, und die Daten werden übertragen.
  - **Websites „laut Quelle“ oder von Hand eingetragen:** Das Impressum wird jetzt automatisch im Hintergrund gelesen.
  - **„Impressum prüfen“** übernimmt jetzt automatisch statt manuell.
  - **OSM-Anzeigenamen** blockieren den Registernamen nicht mehr.
  - In der Akte steht, ob und warum (nicht) übertragen wurde.
- **Installationsvarianten** `basis` / `browser` / `team` / `voll`; beim ersten Einrichten wählbar, später mit `--variante`.
- **Feste Versionen mit SHA-256-Prüfsummen** (`requirements-lock-*.txt`): eine Version je Paket für Windows/Linux × Python 3.10–3.13, mitgezogene Pakete nur, wenn mindestens 14 Tage alt.
- **SBOM** (CycloneDX 1.5) und Lizenzübersicht `docs/BESTANDTEILE.md`.
- **Reproduzierbares Release-ZIP** (byte-gleich) mit Prüfsummenliste und Sicherheitsprüfung; optional Offline-Paket mit `wheels/`.
- **Offline-Modus:** keine Abrufe aus dem Internet; Aufträge warten. Einschaltbar in der Oberfläche oder mit `--offline` bzw. `SignalDesk_offline_starten.bat`.
- **Wiederherstellen** von Sicherungen (auch verschlüsselt, auch per Datei oder `SignalDesk_wiederherstellen.bat`):
  - Prüfung und Vorab-Sicherung des aktuellen Stands;
  - GoBD-Schutz für festgeschriebene Rechnungen;
  - Migration älterer Stände.
- **Automatische Prüfung (GitHub Actions):**
  - Tests unter Windows und Linux;
  - frische Installation aus dem Release-ZIP inkl. Sichern, Wiederherstellen und Neustart;
  - Oberflächen-Test in Chromium;
  - Reproduzierbarkeit.
- **Schneller:** Dubletten-Abgleich 27×, Migration großer Datenbanken 32×.
- **Behoben:** Die Server-Kennung zeigte seit v1.16 die falsche Version.
- 413 Tests (25 neu) + UI-E2E + Installationsprüfung. Berichte: `docs/BERICHT_SPRINT_S6.md`, `docs/EINSCHRAENKUNGEN.md`.

## 1.18.0 – Masterplan 2.0: Sprint 5 (geführter Arbeitstag, CRM, Angebote)

- **Beispieltag des Plans als Abnahmetest:** vom Suchprofil bis zum Tagesabschluss, über die Schnittstelle und im Browser, ohne Sackgasse.
- **Kontaktsperre zentral:**
  - Widerspruch, Phase „gesperrt“ oder ein Treffer auf der **Sperrliste** sperren Gespräch, Termin, Mail-Entwurf, Angebot, Bedarf, Kontaktvorschläge und Kontaktphasen (409 mit Grund).
  - Ein Widerspruch lässt sich immer dokumentieren; aufheben nur über die Sperrliste mit Begründung.
- **„Bedarf bestätigt“ als manuelle Freigabe:**
  - nur nach dokumentiertem Gespräch, mit Problem, Ziel und konkreten Leistungen aus dem Festpreis-Katalog;
  - erst danach gilt ein Angebot als „beim Kunden“ oder „angenommen“;
  - „Angebot aus bestätigtem Bedarf“ übernimmt genau diese Leistungen; die interne Kalkulation bleibt verborgen.
- **Firmenakte** im Lead-Fenster: Ablauf in 7 Schritten, „Als Nächstes“ mit Direktsprung, Belegabdeckung des Scores, Zeitleiste aus allen Modulen, offene Aufgaben.
- **Folgeaufgaben** nach Termin-Vereinbarung, Termin, Bedarf und Angebot. Phasen nur vorwärts; eigene nächste Schritte werden nie überschrieben.
- **Suchprofile mit Budget** (neue Firmen, Website-Suchen, Minuten), durchgesetzt und im Fortschritt sichtbar.
- **Tagesabschluss** auf „Heute“: Erledigtes, Morgen, Firmen ohne nächsten Schritt (direkt Wiedervorlage setzen), Datensicherung.
- **Schema 24.** 388 Tests (12 neu). Bericht: `docs/BERICHT_SPRINT_S5.md`.

## 1.17.0 – Masterplan 2.0: Sprint 4 (Dubletten, großer Firmenkatalog)

- **Dubletten zuverlässig erkennen** (`research/identity.py`, eine Regel für Sichtung, Import, Leads und CRM):
  - sicher gleich: gleiche LEI, gleiche Registernummer, gleiche eigene Website oder gleicher Kernname am gleichen Ort (Müller = Mueller, Wortfolge und Bindestriche egal);
  - möglich: ähnlicher Name, Ort fehlt oder passt zu mehreren Firmen;
  - nie zusammengeführt: andere Rechtsform (GmbH ≠ GmbH & Co. KG), andere Registernummer/LEI oder anderer Ort.
- **Nicht doppelt aufgeführt:**
  - Mögliche Dubletten erscheinen beim Haupteintrag mit „Gleiche Firma / Andere Firma“ bzw. „Ist dieser Lead“.
  - Dazu eine Prüfliste, der Knopf „Dubletten prüfen“ und eine einmalige Bereinigung des Bestands beim Update (Schema 23).
- **Behoben:** Die Übernahme einer „… GmbH & Co. KG“ wurde abgelehnt, wenn die „… GmbH“ schon Lead war (die Rechtsform wurde abgeschnitten).
- **Doppelte Firmen im CRM** (Datenqualität):
  - Vorschläge mit Grund; zusammengeführt wird nur per Klick, dabei wandern alle verknüpften Daten mit und leere Felder werden ergänzt.
  - Rechnungen bleiben unangetastet; „Keine Dublette“ wird gemerkt.
- **Großer GLEIF-Katalog offline** (`research/catalog.py`):
  - Golden Copy/Delta als CSV oder ZIP, Upload und Import per Streaming (gemessen: 300.000 Zeilen mit 31 MB Arbeitsspeicher);
  - je LEI ein Eintrag; Importprotokoll mit Lizenz;
  - Suche (Umlaute egal), Übernahme in die Sichtung mit Dubletten-Abgleich;
  - Ersatz bei Ausfall der GLEIF-API.
- **Gemessen:** DuckDB (schneller, aber 11× Arbeitsspeicher, nicht eingebaut) und RapidFuzz (optional, doppelt so schnell, gleiche Ergebnisse).
- **Fehlende Websites:** Zähler „ohne Website“ mit Filter.
- 376 Tests (32 neu). Bericht: `docs/BERICHT_SPRINT_S4.md`.

## 1.16.0 – Masterplan 2.0: Sprint 2 (Belege, strukturierte Daten) + Sprint 3 (persistente Aufträge)

- **Belegprüfung:**
  - Jeder Wert braucht einen Beleg im Originaltext, sonst bleibt er leer.
  - Jeder Beleg trägt Quelle, Auszug, Methode, Zeitpunkt und Inhalts-Hash.
  - Ergebnis im Testgelände: 103/103 Impressumsfelder, 187/187 Werte belegt.
- **Strukturierte Angaben** (JSON-LD, Microdata, OpenGraph; eigene Implementierung, da extruct nicht installierbar):
  - Organisation und Stellenanzeigen;
  - im Firmen-Bericht als ungeprüfte Fakten mit Beleg;
  - Kaufsignale nutzen dieselbe Implementierung.
- **Haupttext:** eingebauter Leser ohne Navigation, Kopf-/Fußbereich und Banner. Trafilatura ist schaltbar (gemessen: 23× langsamer, weniger Überschriften).
- **Behoben:** PLZ im PDF-Impressum; One-Pager-Fehlerkennung; http-Rückfall für Websites ohne HTTPS (nie bei Zertifikatsfehlern); „nicht erreichbar“ nicht mehr als robots-Verbot.
- **Recherche-Aufträge** (`research/jobs.py`, Schema 22) für Sammelsuche, Website-Suche und Firmen-Berichte:
  - Neustart ohne Verlust (Absturztest mit kill -9: 10/10 fertig, keine Dubletten);
  - Pausieren, Fortsetzen, Abbrechen, Fehlgeschlagene erneut;
  - Wartezeiten statt sofortiger Wiederholung;
  - höchstens 3 Worker, je Domain einer;
  - ein 403 stoppt nur seinen Schritt.
- **Oberfläche:** neues Feld „Recherche-Aufträge“ in „Firmen finden“ und „Firmen-Berichte“, mit Fortschritt je Firma und Fehlern.
- 344 Tests (24 neu). Bericht: `docs/BERICHT_SPRINT_S2_S3.md`.

## 1.15.0 – Masterplan 2.0: Sprint 0 + 1 (sicherer Website-Abruf) und Empfehlung A

- **Testgelände und Benchmark:** 33 fiktive Websites mit schwierigen Fällen, simuliertes Netz ohne echte Abrufe, `tools/bench_fetch.py`, Ausgangsmessung v1.14.
- **Neuer Website-Abruf** (`sales_tool/research/`):
  - IP-Pinning gegen DNS-Rebinding;
  - selbst geprüfte Weiterleitungen;
  - robots.txt nach RFC 9309 (Weiterleitungen, 4xx erlaubt, 5xx gesperrt, `*`/`$`, Zwischenspeicher);
  - gzip mit Bremse gegen gzip-Bomben, Größen- und Zeitgrenzen;
  - zuverlässige Zeichensatzerkennung, Seitentitel nicht mehr im Fließtext;
  - HTTP zuerst, Browser nur als Rückfall.
- **Gemessen:**
  - Impressumsfelder 99.0 % statt 79.6 %;
  - Crawl 33/33 statt 29/33;
  - P95 15 statt 103 ms;
  - 91 statt 123 Anfragen;
  - 0 statt 1 Verbindung zu ungeprüften Adressen.
- **Scrapling:**
  - Die HTML-Auswertung ist als Schalter eingebaut (Ergebnisse identisch, 2.4× langsamer, daher nicht Standard).
  - Der Scrapling-Abruf wurde gemessen und **nicht** eingebaut: Er tarnt sich standardmäßig als Chrome, setzt einen Google-Referer, braucht patchright (362 MB) und erlaubt kein IP-Pinning.
- **Schalter „Recherche-Technik“** in „Datenqualität & System“ (Abruf, Auswertung, Browser-Rückfall).
- **Empfehlung A:**
  - Website-Vorschläge heißen „Vorschlag – bitte prüfen“, mit den Knöpfen „Website passt / passt nicht“.
  - Automatisch gilt nur „belegt“ bzw. „laut Quelle“.
  - Abgelehnte Domains werden nicht erneut vorgeschlagen.
  - Aus einem bloßen Vorschlag wird keine Registernummer übernommen.
- Optional: `requirements-research.txt` mit fest gepinnten Versionen und Lizenzen.
- 320 Tests (25 neu). Berichte: `docs/BERICHT_SPRINT_S0_S1.md`, Plan: `docs/MASTERPLAN_2_0_SCRAPLING.md`.

## 1.14.0 – Live-Test der Quellen: Anpassungen an die echten Schnittstellen

Ein Live-Test aller offenen Quellen (11/2026) hat gezeigt, wo die Attrappen-Tests von der Wirklichkeit abwichen. Behoben:

- **GLEIF:**
  - Die API lehnt inzwischen jeden Ortsfilter ab.
  - SignalDesk nutzt jetzt sofort die erlaubten Filter (Volltext + Land + aktiv), also ohne zwei Fehlversuche je Ort.
  - Ortsteile („Stuttgart - Möhringen“) werden mitgenommen.
  - Die Rechtsform kommt aus dem offiziellen ELF-Code (alle 31 deutschen Codes).
  - Neue Auswahl „Wen suchst du?“: Unternehmen (Standard), Vereine/Verbände/Stiftungen, öffentliche Einrichtungen.
- **Wikidata:**
  - Wikidata drosselt bei Störungen auf „1 Anfrage pro Minute“ und sperrt bis zu 1000 s.
  - SignalDesk taktet jetzt selbst (2 s, im Störungsmodus 65 s), fragt während einer Sperre nicht erneut an und bricht lange Sperren sofort mit klarer Meldung ab, statt zu warten.
  - Websites per LEI kommen in einer Abfrage statt bis zu fünf.
- **Suchgebiet ohne Netzwerk:**
  - Ein mitgeliefertes Ortsverzeichnis (13,216 Orte, GeoNames CC BY 4.0, Großkunden-PLZ bereinigt) ersetzt die Umkreisabfrage bei Wikidata/OpenStreetMap.
  - Eine früher gespeicherte Notlösung „nur Mittelpunkt“ wird nicht mehr dauerhaft verwendet.
- **TED:**
  - Ausschreibungen kommen jetzt standardmäßig nur von Auftraggebern im Suchgebiet (serverseitiger Ortsfilter), mit Ort, PLZ und Entfernung.
  - „Bundesweit“ bleibt als Option.
- **OpenStreetMap:** höchstens 45 s je Server; ein nicht erreichbarer Server wird 10 Minuten übersprungen.
- **Quellen-Check** in „Firmen finden“: eine winzige Testanfrage je Quelle. Ergebnis: erreichbar, überlastet (mit Wartezeit), blockiert oder Format geändert.
- Rechtsform-Erkennung: „Gruppe“, „Group“ und „Holding“ gelten nicht mehr als Rechtsform; e.K. wird erkannt.
- Schema-Version 21 (`discovery_candidates.org_kind`).
- Weitere Live-Befunde:
  - Besitz- und Fondsgesellschaften (Grundbesitz, Wind-/Solarparks, „… III Management“, „Nr. 90 KG“) werden ausgefiltert.
  - Die TED-Gruppe „Software“ enthält keine Lizenzkäufe mehr (48000000 → 72230000).
  - Die Rechtsform wird beim Übernehmen in den Lead geschrieben.
  - Der Status zeigt „läuft“ auch bei Wiederholversuchen.
- Echte Sammelsuche Stuttgart 30 km: **285 s statt 856 s**, alle Treffer im Suchgebiet.
- 295 Tests (19 neu). Bericht: `docs/BERICHT_V114_LIVETEST.md`.

## 1.13.0 – Feedbackrunde: Ortsbezug, Überlastung, automatische Website-Recherche, gegliederte Aufgaben, kompakte Pipeline

- Ortsbezug:
  - Umkreis „nur dieser Ort“ (0 km);
  - TED-Ausschreibungen standardmäßig aus und als „bundesweit“ gekennzeichnet;
  - Sichtungsfilter Ort (mit Anzahl), Höchstentfernung und „ohne Ausschreibungen“.
- Überlastete Quellen (HTTP 429/502/503/504, Zeitüberschreitung):
  - automatische Wiederholung nach 20 s und 60 s, Retry-After wird beachtet (höchstens 2 min);
  - OpenStreetMap in Teilabfragen mit Teilerfolg;
  - Knopf „Fehlgeschlagene Quellen erneut abfragen“ (`POST /api/sweeps/{id}/retry`).
- Automatisierung:
  - Website-Suche startet nach jeder Suche automatisch (bis 200 Firmen, abschaltbar);
  - Impressumsdaten werden beim Übernehmen („belegt“) und im Firmen-Bericht automatisch in leere Lead-Felder geschrieben;
  - nie überschreiben, keine Personen anlegen, „wahrscheinlich“ bleibt ungeprüfter Beleg.
- Aufgaben:
  - gegliedert nach Recherche, Kontakt & Freigaben, Termine & Gespräche, Angebote & Abrechnung und Sonstiges;
  - Recherche je Firma zusammengefasst, Firmen-Berichte für alle mit einem Klick, Bereinigung erledigter Recherche-Schritte;
  - übernommene Firmen bekommen keinen Termin-Druck mehr („Firmen-Bericht erstellen“ ohne Datum);
  - auf „Heute“ ein Sammelpunkt statt vieler Einzelzeilen.
- Deal-Pipeline:
  - kompakte Karten (Name + Score), Details per Klick;
  - Drag & Drop und Click & Drop (⇄, dann Zielspalte; Touch/Tastatur; Esc bricht ab);
  - Spalte „Verloren“, Spalten mit eigener Scrollhöhe.
- Schema-Version 20 (`discovery_candidates.imprint_json`).
- 276 Tests (19 neu). Bericht: `docs/BERICHT_V113.md`.

## 1.12.0 – Sprint D: Angebote & Preise

- Leistungskatalog mit 26 Leistungen in 8 Bereichen, basierend auf deinem Angebot:
  - Kunst, Texte, Web- und Grafikdesign, Print, Logo;
  - Individualsoftware, Shop-Anbindung, Webshop;
  - Foto und Video, Werbung, SEO und GEO;
  - KI-Chatbot, Telefon-Sprachbot, Website-Analyse;
  - Workshops, Betreuung, Tagespauschale, Anreise, Leistung nach Aufwand.

  Meist in den Größen Basis, Standard und Umfangreich.
- Nachvollziehbare Festpreise:
  - Preis = Aufwand × Stundensatz + Puffer + enthaltene Fremdkosten.
  - Intern siehst du die vollständige Herleitung mit effektivem Stundenlohn und eine Warnung unter dem Mindestverdienst.
  - Kalkulationsgrundlagen sind einstellbar: 66 €/h, Tagespauschale, km-Satz, Fahrzeitanteil, Rundung.
  - Eigene Katalogwerte oder feste Preise lassen sich je Umfang hinterlegen.
- Angebots-Baukasten mit Positionen und Vorlagen. Die bisherigen Pakete sind jetzt Vorlagen; die passende lädt beim Wählen der Firma bzw. aus der Recherche.
- Kundendokument:
  - Positionstabelle mit getrennten Summen für einmalig und monatlich;
  - Kosten Dritter als „nicht im Festpreis“;
  - keine Stunden oder Sätze.
- Rechnung mit einer Zeile je Position; Monatsrechnung für laufende Positionen.
- 257 Tests (10 neu).

## 1.11.0 – Sprint C: Firmen-Bericht mit einem Klick

- Ein Auftrag mit fünf Schritten: Impressum & Firmendaten → Website-Bewertung → Website-Inhalte & Ansprechpartner → Karriereseite & Kaufsignale → Verknüpfen & Pakete. Status je Schritt; ein Fehler stoppt die anderen nicht.
- Berichtsseite mit Fakten (mit Fundstelle) getrennt von Interpretationen.
  - Firmendaten übernehmen und Ansprechpartner prüfen direkt im Bericht.
  - Pakete unverbindlich; Übergabe an CRM und Angebot.
- Ein Klick von überall:
  - Website eintragen (legt bei Bedarf den Lead an);
  - Stapel „Berichte erstellen“ (bis 50);
  - „Übernehmen & Bericht erstellen“ in Firmen finden;
  - Lead-Dialog und Pipeline-Phase „Recherche“.
- Rückfall ohne Browser für URL-Recherche, Entscheider-Recherche und Website-Analyse (vorher Abbruch mit „Playwright fehlt“).
- Navigation: „Firmen-Berichte“ statt Research Center; URL-Recherche, Website-Scoring und Kaufsignale als Recherche-Details unter „Erweitert“.
- Schema 19. 247 Tests (8 neu).

## 1.10.0 – Sprint B: Firmen finden, die wirklich funktionieren

- „Arbeitstag starten“: Sammelsuche über GLEIF, Wikidata, OpenStreetMap und TED mit einem Knopf.
  - Eingabe: Ort oder PLZ + Umkreis (Standard 30 km), 65 Branchen zum Anklicken, eigene Schlagwörter.
  - Fortschritt je Quelle; fällt eine Quelle aus, laufen die anderen weiter.
- Quellen repariert:
  - GLEIF mit Fallback-Kette bei HTTP 400 und seitenweiser Abfrage je Gemeinde;
  - Wikidata mit leichter Abfrage und Wiederholversuch bei 502;
  - OpenStreetMap mit drei Ausweichservern und 90 s Zeitlimit.
- Dubletten vermeiden: Zusammenführen über LEI, Registernummer + Ort, Domain und Name + Ort. Bekannte Leads, Sperrliste und verworfene Firmen erscheinen nicht erneut.
- Sichtung zum Durchklicken: Website in neuem Tab, Quellen-Links, Übernehmen und Verwerfen (auch per Taste und als Stapel), Filter und Sortierung, Gebiete & Suchläufe.
- Website-Suche mit Nachweis: Domain-Vorschläge, Prüfung über das Impressum („belegt“ bei gleicher Registernummer), allgemeine Kontaktwege aus dem Impressum.
- Großer Import bis 60 MB: GLEIF-Export und eigene Listen. Filter für aktive und operative Firmen sowie die PLZ-Region; Weiterleitung aus der Datenprüfung.
- Schema-Version 18. 239 Tests (16 neu).

## 1.9.0 – Sprint A: Struktur & Tagesablauf

- Navigation nach Arbeitstag: Heute, Aufgaben · 1 Kunden finden · 2 Recherchieren · 3 Verkaufen · 4 Abrechnen · Erweitert (eingeklappt).
- Neue Startseite „Heute“:
  - Tagesplan in 6 Schritten mit Direktsprung;
  - Wiedervorlage (Termine, Rückrufe, fällige Aufgaben, nächste Schritte, Nachfassen, Bindefristen, begonnene Bedarfsanalysen, offene Freigaben);
  - offenes Potenzial aus kalkulierten Angeboten (Schätzungen getrennt);
  - klickbare Pipeline mit nächster Aktion je Phase;
  - Funktionsstatus („Was funktioniert gerade?“).
- Pipeline-Ansicht: Aktion je Spalte und Karte (Kontakt aufnehmen, Termin vereinbaren, Angebot öffnen, Rechnung schreiben …) mit vorausgewählter Firma.
- „Mein Sales-Tag“ heißt jetzt „Kontakt & Termine“, geordnet nach Freigeben → Kontakt aufnehmen → Termin vereinbaren.
- Endpunkte `GET /api/today`, `GET /api/system/capabilities`. Schema unverändert.
- 223 Tests (7 neu). Masterplan v3 (`docs/MASTERPLAN_V3.md`).

## 1.8.0 – Phase 6: Qualität & Skalierung

- Bereich „Datenqualität & System“.
- Änderungserkennung (Impressum, Website, Register) mit Prüfpunkt, Übernahme nur nach Bestätigung.
- Wiederkehrende Rechercheaufträge (Impressen, Websites, Karriereseiten, gespeicherte Lead-Finder-Suche, Datenqualität) mit Hintergrund-Thread; abschaltbar mit `--no-scheduler`.
- Veraltungs-Kennzeichen je Datenart mit einstellbaren Fristen; Löschfristen für Personendaten mit Löschung nach Bestätigung (Löschnachweis ohne Namen).
- Konfigurierbare Gewichte der Recherchepriorität.
- Optionaler Login mit Rollen (admin, vertrieb, buchhaltung, lesen):
  - scrypt-Passwörter, sichere Sitzungs-Cookies, Bremse gegen Fehlversuche;
  - `--host` nur mit Login-Pflicht, `--allowed-host`, Notfallzugang `--reset-login`.
- Verschlüsselte Sicherung (AES-256-GCM, optional `cryptography`).
- Sicherheit:
  - Host-Prüfung gegen DNS-Rebinding;
  - `frame-ancestors`, `X-Frame-Options`, `Referrer-Policy`;
  - Anfragekörper muss ein JSON-Objekt sein (vorher 500 bei Aufgaben und Aktivitäten);
  - Widerspruch ohne Namen im Audit-Log.
- Neue Indizes. `prepare_database()` für Sicherung und Migration.
- Schema-Version 17.
- Migrationstests mit echten Altdatenbanken aus v0.9, v1.2, v1.6. Last- und Nebenläufigkeitstests, Fehler-Fuzzing aller Routen.
- 216 Tests (29 neu).

## 1.7.0 – Phase 5: Sales-Integration

- Angebots-Matching aus der Bedarfsanalyse mit wörtlichen Kundenzitaten; Recherche-Hinweise getrennt. Status „unverbindlich“ bzw. „Angebotsgrundlage“ (erst nach dokumentierter Bedarfsklärung); Budgethinweis; Übernahme ins Angebotsmodul.
- Neues Paket „Automatisierungsprojekt – ein Prozess digital“. Kundendokument mit Liefergegenständen, Abnahmekriterien und möglichen Drittanbieterkosten.
- Entscheider v3: fachlich / Budget / Entscheidung getrennt (unbekannt, vermutet, bestätigt) mit Prüfregeln, Rollenlandkarte je Thema mit Lücken, veröffentlichter Kontaktweg mit Fundstelle, Kontaktbeschränkungen je Person, Widerspruch → Sperrliste.
- Sales Action Center: Aufgabenvorschläge aus Rechercheergebnissen (übernehmen/verwerfen), eigene Freigabe je Kontaktaktion mit Kanal- und Rechtsprüfung, Erledigen ohne Freigabe gesperrt, Audit-Log.
- Schema-Version 16 (zwei neue Tabellen, zusätzliche Spalten in Kontakten und Aufgaben).
- 187 Tests (16 neu).

## 1.6.0 – Phase 4: Research Command Center

- Bereich „Research Center“ mit Einstiegskarten, Recherche-Trichter, laufenden Aufträgen aller Module und gemeinsamer Prüfliste.
- Priorisierte Firmenübersicht: Recherchepriorität mit Grundlage, „Datenlage unzureichend“, Recherchestand in 7 Schritten, nächster Schritt, Filter und Suche.
- Stapelaktionen für ausgewählte Firmen; Quellenansicht; Gesprächs-Dossier (Markdown/JSON); CSV-Export.
- Übergabe an CRM (Phase, Aufgabe, Aktivität; gesperrte Leads ausgeschlossen) und Angebot vorbereiten mit unverbindlichem Paketvorschlag.
- Navigation: Recherche-Werkzeuge unter „Research Center“ gruppiert, gemeinsame Unter-Navigation in jedem Recherche-Bereich.
- 171 Tests (9 neu).

## 1.5.0 – Phase 3: Buying Signals

- Registerereignisse per manuellem Import (Text/CSV): Neueintragung, Umbenennung, Geschäftsführer-/Prokurawechsel, Sitzverlegung, Strukturänderung, Auflösung als Gegenhinweis; Datenminimierung.
- Job-Signale aus Karriereseiten (eigene Domain, schema.org-JobPosting), Personio-XML-Feed und manuellem Import; Bereiche Prozess, Web & Marketing, Software mit Pro/Contra, Alter und Ablaufdatum.
- Dubletten per Schlüssel und quellenübergreifende Zusammenführung; Veröffentlichungs- vs. Funddatum; Neu-Markierung; Aktualitätsgewichtung ohne Löschen.
- Signal-Korrelation mit Hypothesen, Stärke, Gegenhinweisen, Widersprüchen, fehlenden Bestätigungen, Fragen und Paketen.
- Website-Scoring: Projektanlass aus echten Signalen; Übernahme bestätigter Signale in den Lead.
- Bereich „Kaufsignale“ und „Kaufsignale & Hypothesen“ im Lead-Dialog.
- Fix: Tab-Steuerung der Buchhaltung reagierte auf alle Tabs der Seite.
- 162 Tests (13 neu).

## 1.4.0 – Phase 2: Website-Bedarfs-Scorer v2

- Gerenderte Erfassung mit Chromium (Desktop + Smartphone, Unterseiten), Screenshots, Ladezeit, Datenmenge, Konsolenfehler, DOM-Messwerte; Linkprüfung interner Links.
- Browser-seitiger SSRF-Schutz für alle Unterressourcen; keine fremde Hauptnavigation, keine Downloads.
- 21 Rubriken in Design & UX, Web & Conversion, Prozess & App (Hypothesen); Bereich Kampagnen inaktiv mangels Katalogpaket.
- Getrennte Teil-Scores, Passung, Anlass, Belegabdeckung; Gesamtwert nur bei ausreichender Datenbasis.
- Konfigurierbares Raster mit Bewertungsversionen und Vergleich zur vorherigen Bewertung.
- Ergebnis je Firma: Beobachtungen, Fundstellen, Screenshots, Unsicherheiten, Pakete, Bedarfsfragen, nächster Schritt.
- Bereich „Website-Scoring“ und „Website-Bewertung“ im Lead-Dialog; HTML-Rückfall ohne Browser.
- 149 Tests (11 neu, davon 2 mit echtem Chromium).

## 1.3.0 – Phase 1: Datenbasis

- Masterplan v2 mit Gap-Analyse und Phasen (`docs/MASTERPLAN_V2.md`), Sprint-Bericht (`docs/BERICHT_PHASE1.md`).
- Feldbelege `company_facts` mit Quelle, wörtlichem Beleg, Verfahren, Qualität, Prüfdatum und Status; neue Firmenspalten im Lead.
- Sperrliste `suppression_list` (Domain, Name, Register, E-Mail) für alle Importwege, bleibt nach Löschen erhalten, Aufheben nur mit Begründung.
- Dubletten über Domain, Register (Gericht + Nummer) und normalisierten Namen.
- Impressum-Extraktor (HTML und einfache PDF, mehrere Gesellschaften, Prüfziffer USt-IdNr., verschleierte E-Mails, Fax-Unterscheidung, `null` bei fehlenden Angaben).
- Batch-Impressumsprüfung (1–100 Domains, CSV, Parallelität 1–3, Pause/Fortsetzen/Abbrechen, Neustart-sicher, Fehlerprotokoll, Prüfwarteschlange, Übernahme neu/ergänzen ohne Überschreiben).
- Datenschutz-Nachweise `privacy_records` mit Art.-14-Textbaustein und Fristenhinweis.
- Automatisches Backup vor Schema-Migrationen; Rechnungsempfänger aus geprüften Firmendaten.
- 138 Tests (23 neu).

## 1.2.0 – Ein-Klick-Start

- Neue Startdateien `SignalDesk_starten.bat` (Windows), `SignalDesk_starten.command` (macOS), `start.sh` (Linux): Doppelklick richtet beim ersten Mal alles ein und öffnet die Oberfläche automatisch im Browser.
- `python -m sales_tool.bootstrap`: legt `.venv` an, installiert den Crawler nur bei Bedarf (Merker mit Hash der Anforderungen), bei Fehlschlag höchstens ein neuer Versuch pro Tag; Start auch ohne Internet.
- Windows: Suche nach Python (py-Launcher, PATH, Benutzerinstallation); falls nicht vorhanden, Angebot zur Installation per winget oder Download-Seite. Hinweis, wenn die ZIP nicht entpackt wurde. Einmalige Desktop-Verknüpfung mit eigenem Symbol.
- Server: `--open-browser`; läuft SignalDesk bereits, wird nur der Browser geöffnet; belegter Port → nächster freier Port.
- `setup_windows.bat`/`start_windows.bat` leiten auf den neuen Start um.
- 115 Tests (10 neu).

## 1.1.0 – Lead-Finder

- Neuer Bereich „Lead-Finder“: Suche in Wikidata (CC0), OpenStreetMap/Overpass (ODbL), GLEIF (CC0) und TED-Ausschreibungen (CPV-Gruppen Web, Design, Software, Marketing).
- Datensparsam: nur Unternehmensdaten, Filter „nur Firmen mit Rechtsform“, keine Personen-, E-Mail- oder Telefondaten.
- Fair Use: User-Agent, 24-h-Cache, Mindestabstand 10 s, Tageslimit 40 Abfragen je Quelle; strikte Eingabeprüfung gegen Query-Injection.
- Dublettenprüfung gegen das CRM (Domain und normalisierter Name); einzelne oder ausgewählte Übernahme mit Quelle, Lizenz und Aktivität.
- Manuelle Quellen mit Ampel und Begründung (Handelsregister, Bundesanzeiger, Bekanntmachungsservice, Jobbörse, Gelbe Seiten, LinkedIn …).
- Neuer Kontaktweg „Öffentliche Ausschreibung“.
- Dokumentation `docs/LEADQUELLEN_V11.md`; 105 Tests (10 neu).

## 1.0.0 – Rechnungen & Buchhaltung

- Neuer Bereich „Rechnungen & Buchhaltung“ mit Übersicht, Rechnungen, Ausgaben/E-Rechnungen, Auswertung und Stammdaten.
- Rechnungen nach § 14 UStG mit Pflichtfeldprüfung, lückenloser Nummer je Jahr, Abschlags-/Schluss-/Stornorechnungen, Druckansicht (PDF über Browser).
- GoBD: Festschreibung per SQLite-Trigger, unveränderbares Änderungsprotokoll, eingefrorene Verkäuferdaten, Storno statt Löschen, Lead-Löschsperre bei Rechnungen.
- Steuer: Regelbesteuerung 19/7/0 %, Kleinunternehmer § 19 inkl. Grenzwarnung (25.000/100.000 €), Reverse Charge für EU-Kunden und § 13b-Eingangsleistungen.
- Zahlungseingänge (Teil-/Vollzahlung, Rücknahme), Mahnwesen in drei Stufen mit Verzugszinsen/Pauschale nach § 288 BGB.
- Ausgaben mit SKR03-Kontenvorschlag, GWG-Warnung, Storno.
- E-Rechnung: XRechnung-3.0-Export (UBL); Import von XRechnung (UBL/CII) und ZUGFeRD-XML mit unveränderbarer Archivierung des Originals.
- Auswertungen: UStVA-Vorbereitung (Kz 81/86/21/46/47/66/67, Ist/Soll), vereinfachte EÜR, Vertriebskennzahlen; CSV-Exporte; Backup per Knopfdruck.
- Angebote: Angebotsnummer `AN-JJJJ-NNNN`, Bindefrist 30 Tage, „angenommen“ setzt Lead auf „Gewonnen“ und schlägt die Rechnung vor.
- Fix: Inline-Styles wurden von der eigenen Content-Security-Policy blockiert (u. a. Prioritätsbalken in der Lead-Liste waren unsichtbar).
- 95 automatisierte Tests (28 neu).

# SignalDesk v0.9 – Sales Workspace und Festpreisprodukte

- Neuer Sales-Arbeitsplatz: Tagesagenda, Rechtsstatus pro Lead, manuell dokumentierte Gespräche, interne Follow-up-Aufgaben.
- Lokale Terminverwaltung inkl. manuellem ICS-Export und Aufgabe nach abgeschlossenem Termin.
- Mailentwürfe für vereinbarte Kommunikation inkl. Speichern und Wiederöffnen; kein Versand.
- Preis-/Angebotsmodul: 4 Projektpakete + monatliches Growth-Care-Paket, 5 Zusätze, interne Kosten-, Risiko- und Deckungsbeitragsrechnung, öffentlich klare Liefergegenstände und Festpreis.
- Gespeicherte Angebotsversionen, Kunden-Markdown ohne interne Kalkulation, steuerlicher Freigabecheck, Prüferinnerung nach manuell gesendetem Angebot.
- Neue SQLite-Tabellen: `calls`, `meetings`, `proposals`, `mail_drafts` (schonende Migration).
- Regressionen und neue API-Tests; browserseitige Interaktion mit lokaler API-Bridge verifiziert.

---

## 0.9.0 – Sales-Arbeitsplatz und Festpreisangebote

- Tagescockpit für Follow-ups und Termine, Gesprächsprotokolle mit Sperrlogik und vereinbarten Rückrufen.
- Interne lokale Terminverwaltung (keine externe Kalendersynchronisation) und Mailentwürfe ohne Versand.
- Paketkatalog für Design-, Web-, App- und Pflegeleistungen, definierte Add-ons und anpassbare Projektziele.
- Interne Kalkulation mit Kosten-/Risiko-/Margenwerten getrennt vom kundenorientierten Festpreisangebot mit Leistungsumfang, Ausschlüssen und Steuerhinweis.
- Angebote speichern und Kundenansicht getrennt exportieren; keine automatisierten Kontakte, keine versteckten Zusatzkosten.
- 67 automatisierte Tests erfolgreich.


## 0.8.0 – Entscheider-Finder v2 (manuelle Quellenprüfung)

- Rollenbasierte Web-/LinkedIn-Suchvorschläge im Ein-URL-Bericht und im Lead-Profil; keine automatisierte Social-/Suchmaschinen-Abfrage.
- Prüfworkflow für Kontakte mit Status, Quelle, Belegzitat, Funktion und Datum.
- Nachvollziehbare SQLite-Schema-Migration und PATCH-API für manuelle Verifikation.
- Sperrprüfung und Trennung von verifizierter Funktion, vermuteter Rolle und Kontaktberechtigung.
- 51 automatisierte Tests einschließlich HTTP und Datenmigration.


## 0.7.0 – Ein-URL-Recherche und Gesamtbericht

- Neuer Menüpunkt **URL-Recherche** direkt ab Dashboard, ohne Lead anlegen zu müssen.
- Nur ein einziger kontrollierter Abruf für Website-Beobachtungen **und** öffentlich sichtbare Kontakt-/Personenhinweise.
- Report enthält Quellen, wörtliche Belege, überprüfbare Hypothesen, Ansprechpartner-Kandidaten, allgemeine geschäftliche Kontaktdaten und neutrale Discovery-Fragen.
- Lokale Ollama-KI optional; klare Alternative im Regelmodus ohne KI. Fiktiver Demo-Bericht ohne externen Netzwerkabruf.
- Recherchen in `quick_scans` dauerhaft gespeichert, Status und Fehler sichtbar, Export als Markdown.
- Bewusste CRM-Übernahme mit Domain-Dublettenprüfung; gespeicherte Rechte/Signale werden nicht überschrieben; Personen und Befunde bleiben ungeprüft.
- Automatische Werbenachrichten, kostenpflichtige Kontaktdatenanbieter und erfundene Durchwahlen weiterhin ausgeschlossen.
- 44 Tests inklusive HTTP-, CRM-, Quellen-, Duplikat- und Rechte-Regressionstests.

## v0.6 · Öffentliche Entscheider-Recherche ohne Lusha

- Ein eigener Hintergrund-Job durchsucht bis zu 5 Seiten der Lead-Website nach Team-/Kontakt-/Impressumsinformationen, soweit für Crawler zugänglich.
- Quellenbasierte Personen-Kandidaten und voneinander getrennte allgemeine Firmenkontaktpunkte, inklusive manueller Freigabe.
- Zusätzliche SQLite-Tabellen `contact_research_runs` und `contact_candidates`; schonende Migration `business_email` für vorhandene Personenkontakte.
- Lusha-Module und kostenpflichtige API-Abfragen entfernt/deaktiviert; alte Kontakt- und CRM-Daten erhalten.
- Neue Endpunkte `/api/leads/:id/contact-research` und `/api/contact-candidates/:id/review`.
- Keine KI-Inferenz, keine erfundenen Durchwahlen, kein Auto-Versand.
- Tests für Rollenabgleich, fehlende Durchwahlen, HTTPS-Quelle, Dubletten, Sperrstatus, Archivierung und Endpoint-Deaktivierung.


## 0.4.0 – KI-Studio, sichtbare Ergebnisse & Deal-Board

- Eigenständiger Bereich `KI-Studio`: lokaler Ollama-Verbindungsstatus, Testtextanalyse im Browser (optional KI), echte Ergebnisse sichtbar.
- Text-Test ohne Internet/Crawler/CRM-Speicherung; explizit als Test markiert.
- Regelmodus mit vorsichtigen und wörtlich belegten Textmustern statt beliebiger generischer Vorschläge.
- Analyseverlauf aller Firmen mit Freigabe/Ablehnung, Quellen und Gesprächsfragen.
- Deal-Board inklusive manueller Phasenwechsel; einfacher Angebots-Pilot für Agenturgründer.
- Wiedervorlagen aus Lead-Feldern sichtbar; exportierbares Gesprächsbriefing mit Trennung Hypothese/Bestätigung.
- Neue API-Endpunkte `/api/ai/health`, `/api/ai/preview`, `/api/analyses`, `/api/leads/{id}/brief`.
- Automatisierte Regressionstests erweitert auf 27.

## 0.3.0 – Websiteanalyse
- Optionales Playwright und Ollama, Analysehistorie, Quellenprüfung, manuelle Freigabe.

## 0.2.0 – CRM und Bedarfsgespräch
- Kontakte, Bedarfsermittlung, CSV-Import, Wiedervorlagen.

## v0.5 · Entscheider & berufliche Durchwahlen
- Berufliche Kontakte inklusive Quellenbeleg, Zuständigkeitsrolle und DSGVO-schonender Löschmöglichkeit.
- Rollenempfehlung je Agenturleistung und Firmengröße; Recherche-Abkürzung statt automatisch erfundener Personendaten.
- Optionale Lusha v3 API: Vorschau und gesonderte, kostenpflichtige Freischaltung geschäftlicher Rufnummern.
- Mobil- und unbekannte Nummerntypen werden nicht übernommen; Do-not-Call-Flag wird angezeigt.
- Kein Auto-Outreach, keine kostenlose Zusage für reale Durchwahlen, kein Name-zu-Firma-Scraping.
- 34 automatisierte Tests inklusive Mock-Lusha-Antworten und HTTP-Flow.
