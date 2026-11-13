# Betrieb, Datensicherung und Team-Vorbereitung (ab v1.8)

## Datensicherung

- **Normale Sicherung:** „Einstellungen → Daten & Zugang“ → „Sicherung jetzt anlegen“ (oder Buchhaltung → Backup). Die Kopie liegt im Ordner `backups` neben der Datenbank (Standard: `%USERPROFILE%\.akquise-tool\backups`).
- **Automatisch:** Vor jedem Schema-Update legt SignalDesk selbst eine Sicherung an.
- **Verschlüsselte Sicherung:** Das optionale Paket einmalig installieren:
  ```
  pip install -r requirements-team.txt
  ```
  Danach „Verschlüsselt sichern“ mit einem Passwort von mindestens 12 Zeichen. Das Passwort wird nicht gespeichert: Ohne Passwort ist keine Wiederherstellung möglich.
- **Wiederherstellen einer verschlüsselten Sicherung:**
  ```
  python -m sales_tool.backup_crypto entschluesseln signaldesk-JJJJMMTT-HHMMSS.sdenc wiederhergestellt.sqlite3
  ```
  Danach SignalDesk mit `--db wiederhergestellt.sqlite3` starten oder die Datei an die Stelle der alten Datenbank kopieren (SignalDesk vorher beenden).
- **Extern sichern:** USB-Stick oder Cloud-Speicher, dort nur `.sdenc`-Dateien ablegen. Zusätzlich die **Laufwerksverschlüsselung** einschalten (BitLocker, FileVault, LUKS), denn die laufende Datenbank ist unverschlüsselt.

## Update und Migration

1. SignalDesk beenden.
2. Neue Version entpacken.
3. Starten.

Beim Start erkennt SignalDesk eine ältere Datenbank (`PRAGMA user_version`), sichert sie und ergänzt das Schema schonend: Es kommen nur neue Tabellen und Spalten hinzu, nichts wird gelöscht. Getestet ist die Migration von v0.9, v1.2 und v1.6 (`tests/fixtures/migration`).

## Wiederkehrende Aufträge

- Sie laufen nur, solange SignalDesk geöffnet ist. Geprüft wird alle 5 Minuten; fällige Aufträge laufen nach dem nächsten Start.
- Mit `--no-scheduler` werden sie gar nicht automatisch ausgeführt.
- Alle Zeiten sind UTC.
- **Empfehlung:**
  - „Änderungen erkennen und Veraltung prüfen“ wöchentlich
  - „Impressen aktualisieren“ monatlich mit 20 Firmen
  - „Karriereseiten prüfen“ monatlich
  - „Websites neu bewerten“ vierteljährlich
  - eine gespeicherte TED-Suche wöchentlich

## Team-Betrieb (Vorbereitung)

Standard ist der lokale Einzelplatz ohne Login, erreichbar nur unter 127.0.0.1.

So geht es für ein kleines Team:

1. Lokal starten → „Einstellungen → Daten & Zugang“ → **Administration anlegen** (meldet direkt an).
2. **Benutzer anlegen** mit Rolle (admin, vertrieb, buchhaltung, lesen).
3. **Login einschalten.** Ab dann braucht jede Anfrage eine Anmeldung.
4. SignalDesk auf dem gemeinsamen Rechner bzw. Server **hinter einem TLS-Proxy** starten, zum Beispiel so:
   ```
   python -m sales_tool.server --host 127.0.0.1 --allowed-host signaldesk.firma.intern
   ```
   Der Proxy (Caddy oder nginx) nimmt HTTPS auf `signaldesk.firma.intern` an und leitet an `127.0.0.1:8765` weiter. Er muss den Host-Header unverändert durchreichen und `X-Forwarded-Proto: https` setzen, damit das Sitzungs-Cookie als `Secure` markiert wird.
   - `--host 0.0.0.0` (direkt im Netz) ist möglich, aber nur mit eingeschalteter Login-Pflicht. Ohne TLS gehen Passwörter dann im Klartext übers Netz – nicht empfohlen.
5. Mitarbeitende über die Verarbeitung ihrer Kontodaten informieren (Benutzername, Anzeigename, letzter Login, Protokoll von Anmeldungen).

**Passwort vergessen:** Die Administration setzt in der Benutzerverwaltung ein neues Startpasswort. Ist die einzige Administration ausgesperrt: SignalDesk beenden und auf dem Rechner mit der Datenbank einmal
```
python -m sales_tool.server --reset-login
```
ausführen (bei abweichendem Speicherort zusätzlich `--db PFAD`). Das schaltet die Login-Pflicht aus, beendet alle Sitzungen und wird protokolliert. Danach normal starten, anmelden bzw. neu einrichten und den Login wieder einschalten. Wer an die Datenbankdatei kommt, hat ohnehin vollen Zugriff; der Notfallzugang ist deshalb an den lokalen Rechner gebunden.

## Was für echten Cloud-Betrieb noch fehlt

Bewusst nicht Teil von Phase 6:

- Server-Datenbank (z. B. PostgreSQL) statt einer SQLite-Datei, Verbindungs-Pool, Migrationen mit Rücknahme
- Mandantentrennung, falls mehrere Firmen dieselbe Installation nutzen
- 2FA, Single Sign-on (OIDC), Leerlauf-Timeout, Sperre nach Fehlversuchen über Neustarts hinweg
- Verschlüsselung der Datenbank im Ruhezustand bzw. verschlüsselter Speicher beim Hoster
- Hosting in der EU mit Auftragsverarbeitungsvertrag (Art. 28 DSGVO), technisch-organisatorische Maßnahmen, Verzeichnis der Verarbeitungstätigkeiten
- Monitoring, zentrales Logging, automatische externe Backups mit Wiederherstellungstest
- Externer Penetrationstest
