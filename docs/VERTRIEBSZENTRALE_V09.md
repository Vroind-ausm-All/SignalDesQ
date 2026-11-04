# SignalDesk v0.9 – Dein lokaler Vertriebsarbeitsplatz

**Für eine Medienagentur ohne bestehende Kundenbasis.** Die Anwendung soll zuerst die tägliche Vertriebsarbeit strukturieren, nicht unkontrolliert automatisieren.

## Was jetzt integriert ist

- **Mein Sales-Tag:** priorisierte offene Aufgaben und nächste Schritte, Termine, Anrufhistorie und Kontaktrechts-Hinweise. Gesperrte Leads erscheinen nicht in der Kontakt-Wiedervorlage.
- **Call-Arbeitsplatz:** manuelle Gesprächsergebnisse, Gesprächsnotizen, Rechtsnotizen und ein ausdrücklich vereinbarter Rückruf. Rückruf-Termin wird nur bei dokumentierter Vereinbarung automatisch als interne Aufgabe angelegt. Ein dokumentierter Widerspruch sperrt weitere Ansprache im CRM.
- **Termine:** lokale Termindatensätze mit Beginn, Dauer, Ort und Agenda, Kalenderexport (.ics) auf dem Windows-Rechner. Der Kalender wird **nicht** automatisch synchronisiert und keine Einladung wird versendet. Bei manuell auf „erledigt“ gesetzten Terminen wird eine interne Nachbereitungsaufgabe erstellt.
- **Mail-Assistent:** editierbare Textvorlagen für **vorher vereinbarte** Kommunikation. Der Entwurf wird lokal gespeichert und kann kopiert werden. **Kein Versand, keine SMTP/IMAP/OAuth-Verbindung.** Rechtliche Grundlage ist manuell zu prüfen.
- **Angebote & Preise:** vier einmalige Leistungspakete + monatliches Betreuungspaket; fünf optionale Zusatzmodule. Ein Paket kann anhand des beim Lead gewählten Angebots vorausgewählt werden. Bestätigte Discovery-Ergebnisse können das Kundenziel befüllen.
- **Interne Kalkulation:** angenommene Lieferstunden, interne Kosten, Fremdkosten, Risikoaufschlag, Ziel-Deckungsbeitrag, Preisvorschlag und optionale manuelle Festpreisanpassung (nicht unter kalkulierte Kosten). Werte sind Annahmen und müssen an deine echte Wirtschaftlichkeit angepasst werden.
- **Kundenangebot:** konkrete Ziele, Leistungsbestandteile, Grenzen/Ausschlüsse, Korrekturrunden, Zeitrahmen, steuerlicher Status, vollständiger netto/ggf. brutto ausgewiesener Festpreis, Zahlungsplan und Änderungsregeln. Keine Stundenpreise oder internen Kosten im Kundenexport. Export als Markdown, weiterbearbeitbar und druckbar aus einem Text-/Dokumenteneditor.
- **Angebotsverlauf:** unveränderliche Angebots-Snapshots (neue Konditionen = neuer Entwurf), manuelle Statuspflege. Wenn ein Angebot als „gesendet (manuell)“ dokumentiert wird, erfolgt **keine Nachricht**, sondern eine interne Wiedervorlage zur *Prüfung*, ob und wie ein Follow-up zulässig ist.

## Windows-Start

1. Bestehende SQLite-Datei unter `%USERPROFILE%\.akquise-tool\akquise.sqlite3` sichern.
2. `setup_windows.bat` ausführen (Python 3.10+, Installation Playwright/Chromium für bestehende Websiteanalyse).
3. `start_windows.bat` ausführen und `http://127.0.0.1:8765` im Browser öffnen.
4. Einen Lead anlegen oder eine bestehende Firma öffnen und eine passende Leistung auswählen.
5. Links **Mein Sales-Tag** für Anrufe, Termine und E-Mail-Entwürfe benutzen.
6. Links **Angebote & Preise**: Firma auswählen → Paket und optionale Leistungen prüfen → intern kalkulieren → steuerlichen Status bestätigen → Entwurf speichern → Kundendokument exportieren.

Bei fehlendem Ollama funktioniert Sales Workspace ohne KI. Website-Recherche im Regelmodus benötigt Playwright, nicht Ollama.

## Technische API v0.9

- `GET /api/workspace` – Tagesagenda, Aufgaben, Termine, Angebotsübersicht, Telefon-Hinweise
- `GET /api/workspace/catalog` – Pakete, optionale Module, Enum-Werte
- `GET|POST /api/workspace/calls` – manueller Anrufverlauf
- `GET|POST /api/workspace/meetings`, `PATCH /api/workspace/meetings/:id` – Termine, Status
- `GET|POST /api/workspace/mail-drafts` – lokale Entwürfe, **kein Senden**
- `POST /api/workspace/quote-preview` – getrennte interne und externe Vorschau
- `GET|POST /api/workspace/proposals`, `GET|PATCH /api/workspace/proposals/:id` – gespeicherte Angebotsversionen
- `GET /api/workspace/proposals/:id/customer` – Kundenansicht + Markdown **ohne** interne Zahlen

Migration läuft schonend bei Datenbankinitialisierung. Neue Tabellen `calls`, `meetings`, `proposals`, `mail_drafts`. Bestehende v0.8-Daten werden nicht gelöscht.

## Grenzen (wichtig vor dem Geschäftsstart)

- **Einzelplatz-Software:** Bindung nur an `127.0.0.1`, kein Login, keine Mehrbenutzer-Rechte, keine Cloud-Datensicherung. Nicht öffentlich hosten.
- Weder Call-Dialer noch Kalender-/E-Mail-Konnektor; keine automatische E-Mail, keine Sprachaufzeichnung, keine Serien-Werbeansprache.
- Angebots-Mindestpreise und Aufwandannahmen sind **Startwerte, keine Marktpreise oder Garantie für Gewinn**. Der interne Verrechnungskostensatz ist eine Planungsannahme, nicht dein Kunden-Stundensatz.
- Steuerbehandlung (regulär 19% oder § 19 UStG) ist eine bewusste Auswahl; bei „offen“ verhindert SignalDesk das Markieren als versendet/angenommen. Steuerliche und juristische Prüfung bleiben erforderlich.
- `angebot_begleiten` erzeugt nur einen unverbindlichen Entwurf, keine Rechnung, keine E-Signatur und keinen Zahlungslink.
- Ein als „gesendet“ markiertes Angebot wird dadurch **nicht** versendet. Ohne E-Mail-Anbieter ist der Versand derzeit extern zu erledigen.

## Praxistest

- Echte Website über `URL-Recherche` prüfen, Befund manuell bestätigen und Lead übernehmen.
- Unter `Mein Sales-Tag` Gesprächsergebnis und ausdrücklich vereinbarten Rückruf dokumentieren.
- Einen Termin anlegen, .ics herunterladen und lokal in einen Kalender importieren.
- Unter `Angebote & Preise` Produktpaket, Ergebnis und Zusatzmodul konfigurieren, Kosten und Marge prüfen, finalen Festpreis kontrollieren.
- Kundendokument exportieren, auf Steuern/Ausschlüsse/Voraussetzungen prüfen und erst nach Freigabe extern verschicken.
- Das erste Angebot als gesendet markieren; die interne Prüferinnerung ist anschließend in `Aufgaben` sichtbar.

Tests: `python -m unittest discover -s tests -v`. Browseransicht und Interaktionen wurden mit Chromium und einer lokalen API-Bridge überprüft. Öffentlicher Browserzugriff auf `127.0.0.1` war in der Erstellungsumgebung administrativ gesperrt; ein vollständiger Windows-Praxistest steht noch aus.
