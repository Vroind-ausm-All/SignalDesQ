# Bericht Masterplan 2.0 – Sprint 5 (SignalDesk v1.18)

Auftrag: „den nächsten Sprint vollständig ausarbeiten“. Sprint 5 laut Plan: **Guided Workday, CRM & Angebote**.

**Aufgaben laut Plan:**
- Firmenakte mit Zeitleiste;
- Recherche → Kontakt → Termin → Angebot;
- Pipeline-Knöpfe und Folgeaufgaben;
- Scoring mit Belegabdeckung;
- Festpreis-Katalog nur aus bestätigtem Bedarf;
- interne Kosten bleiben verborgen.

**Fertig, wenn:**
- ein Nutzer den kompletten Beispieltag von der Recherche bis zum Angebotsentwurf ohne Sackgasse durchführt;
- Kontaktsperren und alle manuell erforderlichen Freigaben greifen.

**Abnahmeablauf (Plan, Abschnitt 12):** Profil auswählen → Session starten → Ergebnisliste öffnen → Originalsite öffnen → Gesamtbericht prüfen → Kontaktstatus dokumentieren → Firma im CRM → Gespräch/Termin (manuell) → bestätigter Bedarf → Festpreisangebot → Wiedervorlage → Tagesabschluss.

## Ausgangslage (Prüfung gegen den Ablauf)
Vieles war seit v1.9–v1.13 vorhanden: Tagesplan, Wiedervorlage, Pipeline mit Aktionsknöpfen, Kontakt & Termine, Bedarfsanalyse, Festpreis-Baukasten mit verborgener Kalkulation.

**Gefundene Lücken und Sackgassen:**

| Lücke | Folge |
|---|---|
| Kontaktsperre nur über Phase/Rechtsstatus geprüft | Firma auf der **Sperrliste** (z. B. Domain nach Widerspruch per Brief) bekam trotzdem Termine, Angebote, Mail-Entwürfe und Kontaktvorschläge |
| Phasenwechsel ungeprüft | ein gesperrter Lead ließ sich per Pipeline wieder in „Kontakt“ schieben |
| kein „bestätigter Bedarf“ | Angebote ließen sich ohne jede Bedarfsklärung als „beim Kunden“ oder „angenommen“ markieren |
| keine Firmenakte | Verlauf über 12 Module verteilt, kein „Was ist als Nächstes dran?“ je Firma |
| Folgeaufgaben lückenhaft | nach „Termin vereinbart“, nach dem Termin oder nach der Bedarfsklärung entstand nichts |
| kein Tagesabschluss | Firmen ohne nächsten Schritt blieben unbemerkt liegen |
| keine Suchprofile, kein Budget | der Ablauf des Plans beginnt mit „Profil auswählen“; Budgets je Lauf waren nicht sichtbar (Plan, Abschnitt 13) |
| Score ohne Belegabdeckung | nicht erkennbar, wie viel vom Score belegt ist |

## Umsetzung

### 1. Kontaktsperre zentral (`sales_tool/workday.py`)
- **Gesperrt** ist eine Firma bei Widerspruch, in der Phase „gesperrt“ oder bei einem **Treffer auf der Sperrliste** (Domain, Name, Firmenname laut Register, Registerangabe, E-Mail).
- **Gesperrt sind dann (Status 409 mit Grund):**
  - Gespräch dokumentieren, Termin eintragen, Mail-Entwurf, Angebot erstellen;
  - Angebot versenden oder annehmen, Bedarf bestätigen;
  - Kontaktvorschläge im Action Center und deren Freigabe;
  - Wechsel in die Phasen Kontakt, Rückmeldung, Termin, Angebot oder Gewonnen.
- **Ein Widerspruch lässt sich immer dokumentieren.**
- **Aufheben** geht nur über die Sperrliste, mit Begründung (Protokoll). Erst danach lässt sich der Rechtsstatus ändern. Die Prüfung sieht dabei den Zustand *nach* der Änderung an.

### 2. Bestätigter Bedarf als manuelle Freigabe
- **„Bedarf bestätigen“** in der Firmenakte. Voraussetzungen:
  - ein **dokumentiertes Gespräch** (Telefonat, erledigter Termin, Gesprächsnotiz) oder eine schriftliche Bestätigung des Kunden;
  - **Problem und gewünschtes Ergebnis** aus der Bedarfsanalyse;
  - eine kurze Notiz, *was* der Kunde bestätigt hat;
  - die **konkreten Leistungen aus dem Festpreis-Katalog** mit Umfang bzw. Menge (wie im Angebot geprüft).
- **„Angebot aus bestätigtem Bedarf“** übernimmt genau diese Leistungen, das Ziel und die Grundlage („Bedarf im Termin bestätigt am …“).
- **Ein Angebot gilt erst danach als „beim Kunden“ oder „angenommen“.** Entwürfe bleiben jederzeit möglich, z. B. aus dem Firmen-Bericht.
- **Die interne Kalkulation bleibt verborgen.** Der Test prüft das Kundendokument auf Stunden, Stundensatz, Puffer, effektiven Stundenlohn und den internen Freigabevermerk.
- **„Bedarf neu klären“** (mit Begründung) nimmt die Freigabe zurück.

### 3. Firmenakte im Lead-Fenster (`GET /api/leads/{id}/file`, `public/akte.js`)
- **Ablauf in 7 Schritten:** Recherche → Kontaktweg → Gespräch → Termin → Bedarf → Angebot → Abschluss. Jeder Schritt ist erledigt, begonnen oder offen und nennt den Grund.
- **„Als Nächstes“** mit Direktsprung, z. B. Bericht erstellen, Kontaktstatus dokumentieren, Gespräch dokumentieren, Termin, Bedarf bestätigen, Angebot aus Bedarf, Rechnung.
  - Bei Sperre steht dort die Sperre, **ohne Aktionsknopf**.
  - Ohne Kontaktweg kommt erst „Kontaktweg klären“, ohne Bedarf kein „Angebot“.
- **Belegabdeckung** des Scores, je Baustein belegt, teilweise oder fehlend, mit Knopf zum Beleg:

  | Baustein | Gewicht |
  |---|---|
  | Firmendaten | 20 |
  | Website-Bewertung (deren Abdeckung) | 25 |
  | Anlass mit Quelle | 20 |
  | Kontaktweg | 15 |
  | bestätigter Bedarf | 20 |

  Ausdrücklich gilt: kein Maß für Kaufwahrscheinlichkeit.
- **Zeitleiste aus allen Modulen**, filterbar: Fund aus der Sichtung, Notizen, Telefonate, Termine, Aufgaben, Firmen-Bericht, Belege, Website-Bewertung, Kaufsignale, Mail-Entwürfe, Angebote, Rechnungen.
- **Offene Aufgaben** mit „erledigt“.

### 4. Folgeaufgaben und Phasen
- **Nach jedem Schritt** wird eine Folgeaufgabe angelegt, ohne Dubletten:

  | Ereignis | Folgeaufgabe |
  |---|---|
  | „Termin vereinbart“ | Termin eintragen (erledigt sich mit dem Termin) |
  | Termin eingetragen | Termin vorbereiten (Tag davor) |
  | Termin erledigt | Bedarf bestätigen |
  | Bedarf bestätigt | Festpreisangebot erstellen (erledigt sich mit dem Angebot) |
  | Angebot versendet | Nachfassen nach 7 Tagen (wie bisher) |

- **Phasen nur vorwärts:** erreicht → Rückmeldung, Termin → Termin, versendet → Angebot. Nie aus „gesperrt“, „verloren“ oder „gewonnen“.
- **Ein selbst eingetragener nächster Schritt wird nie überschrieben.** Ersetzt werden nur leere oder automatisch gesetzte Schritte, so wie es die Abnahmeregel „keine ungewollten CRM-Änderungen“ verlangt.

### 5. Suchprofile mit Budget (`sales_tool/profiles.py`)
- **Profil:** Gebiet, Branchen, Quellen, Filter und **Budget je Lauf**:
  - höchstens neue Firmen (Standard 300);
  - höchstens Website-Suchen (100);
  - höchstens Minuten (30).
- **Angezeigt** wird außerdem: KI-Analysen nur auf Klick, keine externen Kosten (nur kostenlose offene Quellen).
- **Durchgesetzt** und im Fortschritt sichtbar:
  - „Budget 3 / 40 neue Firmen · höchstens 0 Website-Suchen · 0 / 15 Min.“;
  - nach Ablauf übersprungene Quellen bzw. Orte mit Grund;
  - Treffer über dem Budget werden gezählt („n wegen Budget nicht übernommen“), nicht still verworfen.
- **Bedienung** in „Firmen finden“: Profil wählen → Formular füllt sich → **„Profil starten“**. „Aktuelle Suche als Profil speichern“ und „Profil löschen“ gibt es ebenfalls. Das Budget gilt auch für Suchen ohne Profil.

### 6. Tagesabschluss („Heute“, `GET/POST /api/today/close`)
- **Erledigt heute:**
  - neue Leads, gesichtete Treffer, Berichte;
  - Telefonate, Termine;
  - bestätigte Bedarfe, Angebote, erledigte Aufgaben.
- **Morgen:** fällige Aufgaben, Termine, Überfälliges, Angebotsentwürfe.
- **Sackgassen:** offene Firmen in Kontaktphasen ohne nächsten Schritt mit Datum, ohne fällige Aufgabe und ohne Termin. Gesperrte zählen nicht.
  - Je Firma lassen sich Schritt und Datum direkt setzen.
  - Die Liste zeigt höchstens 100 Firmen und dann „100+“.
- **„Tag abschließen“:** setzt die Wiedervorlagen, erstellt optional eine **Datensicherung** und speichert Zusammenfassung und Notiz des Tages.

## Messung

| | Wert |
|---|---|
| Firmenakte (900 Ereignisse, 5.000 Leads) | 3,4 ms |
| Tagesabschluss-Übersicht (5.000 Leads) | 5,4 ms |
| Beispieltag im Browser | 10 Schritte, 0 Konsolenfehler, jeder Zwischenstand mit klickbarem nächstem Schritt |

## Abnahme

| Kriterium | Nachweis |
|---|---|
| Beispieltag ohne Sackgasse | `test_example_day_from_profile_to_offer_without_dead_end`: alle 12 Stationen des Plans über HTTP, an 7 Zwischenständen hat „Als Nächstes“ immer eine Aktion; Browser-Test derselbe Ablauf über die Oberfläche |
| Kontaktsperren greifen | `test_suppression_blocks_every_contact_path` (Sperrliste: 5 Wege, Phasenwechsel, Action Center, Freigabe → 409; Widerspruch bleibt möglich), `test_unlock_only_via_suppression_list` |
| manuelle Freigaben greifen | kein Bedarf ohne Gespräch, kein „beim Kunden/angenommen“ ohne Bedarf, kein Angebot aus Bedarf vor der Freigabe, Bedarf neu klären |
| interne Kosten verborgen | Kundendokument ohne Stunden, Satz, Puffer, effektiven Stundenlohn und Freigabevermerk |
| keine ungewollten CRM-Änderungen | eigener nächster Schritt bleibt; Phase nur vorwärts; Folgeaufgaben je einmal |

## Tests
- **Unit- und Integrationstests: 388, alle grün**, davon 12 neu in `tests/test_sprintS5_workday.py`.
- **Angepasste alte Tests** (gewollte Verhaltensänderung, je kommentiert):
  - 3 Tests markieren ein Angebot als gesendet bzw. angenommen und bestätigen vorher den Bedarf (`tests/s5_helpers.py`, so wie ein Nutzer es tut);
  - eine Sperre liefert 409 statt 400;
  - ein erledigter Termin erzeugt jetzt zusätzlich die Folgeaufgaben.
- **Zwei echte Fehler, die dabei auffielen und behoben sind:**
  1. Ein Angebots*entwurf* hätte die Phase auf „Angebot“ gesetzt.
  2. Ein selbst eingetragener nächster Schritt wäre überschrieben worden.
- **Browser-Test** (Chromium):
  - Profil speichern und starten (Budget sichtbar);
  - übernehmen, Akte, Bericht über den Akte-Knopf, Bedarf mit 2 Leistungen über das Formular bestätigen;
  - Angebot aus Bedarf (AN-2026-0001, 5.240 € netto);
  - gesperrte Firma ohne Aktionsknopf;
  - Tagesabschluss mit gesetzter Wiedervorlage und Sicherung;
  - Handy (390 px) ohne seitliches Scrollen in „Heute“, „Firmen finden“ und der Akte.

## Geänderte Dateien
- **Neu:**
  - `sales_tool/workday.py`, `sales_tool/profiles.py`;
  - `sales_tool/public/akte.js`, `sales_tool/public/workday.js`;
  - `tests/test_sprintS5_workday.py`, `tests/s5_helpers.py`.
- **Geändert:**
  - `sales_workspace.py` (Sperre und Folgeaufgaben bei Anruf, Termin, Mail, Angebot);
  - `server.py` (Routen, 409, Freigaben bei Angebotsstatus, Phasenwechsel, `done_at`);
  - `sweep.py` (Budget);
  - `sales_integration.py` (Sperrliste im Action Center);
  - `model.py` (Schema 24);
  - `index.html`, `app.js`, `sweep.js`, `style.css`.

## Lizenz- und Sicherheitsrisiken
- **Keine neuen Abhängigkeiten.**
- **Datenbank:** Schema 24 ergänzt nur Spalten bzw. Tabellen (`discovery.confirmed_*`, `discovery.needs_json`, `tasks.done_at`, `day_closings`, `search_profiles`). Vor der Migration wird automatisch gesichert.
- **Kein Versand, keine automatische Ansprache.** Alle Kontakte dokumentiert der Nutzer selbst.

## Offene Punkte
- **Rechtsstatus je Kanal** (E-Mail, Telefon, persönlich) prüft weiterhin die Freigabe im Action Center. Der Bedarf ist davon unabhängig.
- **Tagesabschluss:** Er sichert lokal; die externe Sicherung bleibt Sache des Nutzers (Hinweis wie bisher).
- **Nächster Sprint laut Plan: Sprint 6** – Windows-Installationsvarianten, Lockfile, Release-SBOM, automatische Tests Windows/Linux, Backup/Restore, Performancebericht.
