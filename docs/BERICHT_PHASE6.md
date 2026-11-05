# Sprint-Bericht Phase 6 – Qualität & Skalierung (v1.8)

Gemäß Masterplan v2, Phase 6. Ergänzend: [`SICHERHEITSPRUEFUNG_V18.md`](SICHERHEITSPRUEFUNG_V18.md) (Befunde und Maßnahmen) und [`BETRIEB_UND_TEAM.md`](BETRIEB_UND_TEAM.md) (Backup, Update, Team-Betrieb, Cloud-Vorbereitung).

## Was ist tatsächlich implementiert?

Neuer Bereich **„Datenqualität & System“** und Modul `quality.py`.

### Datenaktualisierung und Änderungserkennung
- **Impressum:** Ein erneut ausgelesenes Impressum wird Feld für Feld mit den übernommenen Firmendaten verglichen. Verglichen werden Name, Rechtsform, Anschrift, Register, USt-IdNr., Telefon und E-Mail. Reine Schreibweisen zählen nicht als Änderung, etwa „Hafenstraße“ und „Hafenstr.“ oder Groß-/Kleinschreibung.
- **Website:** Eine neue Bewertung wird mit der vorigen verglichen. Gemeldet werden ein Gesamtwert, der sich um mindestens 10 Punkte ändert, und Rubriken, die zwischen „ok“ und „auffällig“ wechseln. „Unbekannt“ zählt nicht als Änderung.
- **Register:** Umbenennung, Sitzverlegung, Wechsel der Vertretung und Auflösung aus importierten Bekanntmachungen werden als Hinweis zu den Firmendaten gemeldet.
- **Jede Änderung ist ein Prüfpunkt** mit altem und neuem Wert, Quelle und Auszug. Sie erscheint nur einmal und wird nie automatisch übernommen.
  - *Übernehmen* gibt es nur für Impressumsfelder: Der alte Beleg wird „veraltet“, der neue „bestätigt“, der Lead wird aktualisiert und der Vorgang protokolliert.
  - Sonst bleiben *erledigt* oder *ignorieren*. Bei gesperrten Leads ist keine Übernahme möglich.

### Wiederkehrende Rechercheaufträge
- Es gibt fünf Auftragsarten:
  - Impressen veralteter oder nie geprüfter Firmen erneut auslesen
  - Websites mit veralteter Bewertung neu bewerten
  - Karriereseiten erneut prüfen
  - gespeicherte Lead-Finder-Suche wiederholen
  - Änderungen erkennen und Veraltung prüfen
- **Zeitplan:** Intervall 1–365 Tage, höchstens 50 Firmen je Lauf. Jeder Auftrag lässt sich pausieren, löschen oder sofort ausführen; Status und Ergebnis des letzten Laufs werden angezeigt.
- **Auswahl der Firmen:** nur offene Leads mit Website. Ausgenommen sind gesperrte Leads, Leads mit Widerspruch, Einträge auf der Sperrliste, Firmen mit frischen Daten und solche mit laufender oder noch ungeprüfter Recherche.
- **Ausführung über die bestehenden Module** mit deren Schutzmechanismen: SSRF-Schutz, robots.txt, Rate-Limits, Fair-Use-Grenzen der offenen Quellen. Die Ergebnisse landen in den Prüflisten. Es wird niemand kontaktiert.
- **Hintergrund-Thread** im laufenden Programm, alle 5 Minuten, erster Lauf frühestens 5 Minuten nach dem Anlegen. Abschaltbar mit `--no-scheduler`. Fehler werden protokolliert, der Server läuft weiter.

### Veraltungs-Kennzeichen
- Fristen je Datenart, einstellbar zwischen 7 und 1095 Tagen:

  | Datenart | Standardfrist |
  |---|---|
  | Impressum | 365 Tage |
  | Bestätigte Feldbelege | 365 Tage |
  | Website-Bewertung | 180 Tage |
  | Geprüfte Ansprechpartner | 180 Tage |
  | Kaufsignale | 365 Tage |
  | Karriereseite | 90 Tage |

- Angezeigt wird das in der Liste „Veraltete Daten“, als Kennzeichen in der Research-Center-Tabelle und am einzelnen Feldbeleg.
- **„Veraltet“ heißt „erneut prüfen“.** Prüfstatus und Werte bleiben unverändert, gelöscht wird nichts. Fehlende Daten gelten nicht als veraltet; sie zeigt weiterhin der Recherchestand.

### Löschfristen (DSGVO)
- Datenschutz-Nachweise mit abgelaufener Löschfrist werden aufgelistet. „Personendaten löschen“ entfernt nach Bestätigung den Ansprechpartner und den Nachweis und löst die Verknüpfung offener Aufgaben.
- Der Löschnachweis im Audit-Log enthält **keine** Personendaten (Rechenschaftspflicht ohne erneute Speicherung).

### Konfigurierbare Gewichte
- **Recherchepriorität:** Website, Kaufsignale und Lead-Fit sind einstellbar (Standard 40/30/30). Die Summe muss 100 ergeben, und Website oder Kaufsignale brauchen ein Gewicht über 0.
- Jede Änderung wird mit altem und neuem Wert protokolliert. Die Grundlage in Übersicht, Dossier und Export zeigt die aktuellen Gewichte.

### Last- und Fehlertests, Sicherheitsprüfung, Migrationstest
Siehe unten und [`SICHERHEITSPRUEFUNG_V18.md`](SICHERHEITSPRUEFUNG_V18.md).
- **Behoben:**
  - **DNS-Rebinding:** Fremde Host-Header werden jetzt mit 421 abgewiesen.
  - **Clickjacking:** `frame-ancestors 'none'`, `X-Frame-Options`, `Referrer-Policy`.
  - **Fehlerhafte Anfragen:** Ein JSON-Array oder JSON-String als Anfragekörper führte bei Aufgaben und Aktivitäten zu Serverfehlern (500). Gefunden hat das der neue Fehlertest.
  - **Audit-Log:** Ein Widerspruch schrieb den Namen der Person ins unveränderbare Audit-Log.
- **Indizes** für Karriereseiten-Prüfungen, Website-Befunde, Aufgaben, Paketempfehlungen und Löschfristen.
- `prepare_database()` bündelt Sicherung, Migration und Wiederaufnahme. Sie wird beim Start und im Migrationstest genutzt.

### Vorbereitung Team/Cloud
- **Login (optional, Standard: aus).** Benutzer mit vier Rollen:

  | Rolle | Rechte |
  |---|---|
  | admin | alles inkl. Benutzer, Einstellungen und Backups |
  | vertrieb | Leads, Recherche, Angebote; Buchhaltung nur lesen |
  | buchhaltung | Rechnungen und Ausgaben; Vertrieb nur lesen |
  | lesen | nur lesen |

- **Passwörter und Sitzungen:**
  - Passwörter werden mit scrypt gehasht, mindestens 10 Zeichen.
  - Die Sitzung läuft über ein Cookie mit `HttpOnly` und `SameSite=Strict` (hinter einem TLS-Proxy zusätzlich `Secure`). Gespeichert wird nur der SHA-256-Hash des Tokens; eine Sitzung gilt 12 Stunden.
  - Nach 5 Fehlversuchen in 15 Minuten wird gebremst, je Benutzer und je IP-Adresse.
  - Login, Fehlversuche und Benutzeränderungen werden protokolliert.
  - Die letzte Administration lässt sich nicht entfernen.
- **Login-Pflicht** lässt sich nur mit angemeldeter Administration einschalten. Danach braucht jede API- und Druckanfrage eine Sitzung, und die Oberfläche zeigt einen Anmeldedialog.
- **Netzwerkbetrieb:**
  - `--host` mit einer anderen Adresse als 127.0.0.1 startet nur bei eingeschalteter Login-Pflicht.
  - `--allowed-host` gibt zusätzliche Hostnamen frei.
  - Die Oberfläche weist darauf hin, dass SignalDesk dann hinter einem TLS-Proxy laufen muss.
- **Verschlüsselte Sicherung** (AES-256-GCM, Schlüssel per scrypt aus dem Passwort) über das optionale Paket `cryptography` (`requirements-team.txt`). Wiederherstellen mit `python -m sales_tool.backup_crypto entschluesseln`. Fehlt das Paket, gibt es eine klare Meldung; die normale Sicherung bleibt verfügbar.
- **Notfallzugang** auf dem Rechner selbst: `python -m sales_tool.server --reset-login` schaltet die Login-Pflicht aus, beendet alle Sitzungen und wird protokolliert.
- **Sicherheits-Selbstauskunft** in der Oberfläche: welche Schutzmaßnahmen aktiv sind und was für den Team-Betrieb fehlt.

**Schema-Version 17**, mit automatischer Sicherung vor der Migration. Neue Tabellen: `app_settings`, `change_events`, `recurring_jobs`, `users`, `sessions`; dazu die Spalte `batch_items.changes_checked`.

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **216 Tests grün**, davon 29 neu in `tests/test_phase6_quality.py`. Mit Playwright, Chromium und `cryptography` laufen alle 216. Fehlt `cryptography`, wird nur der Verschlüsselungs-Test übersprungen; fehlt Playwright, wie bisher die 2 Browser-Tests.
- **Einstellungen:** Validierung, Einfluss auf die Priorität (nachgerechnet), Gewicht 0, Fristen.
- **Veraltung:** alle sechs Datenarten, Werte und Prüfstatus bleiben unverändert, gesperrte Leads ausgenommen, fehlende Daten gelten nicht als veraltet.
- **Löschfrist:** Löschen nur nach Bestätigung und nur nach Fristablauf, Aufgaben entkoppelt, Löschnachweis ohne Namen.
- **Änderungen:** Impressum (inkl. Schreibweisen-Toleranz und keiner Doppelmeldung), Übernahme mit Belegwechsel, Website-Gesamtwert und Rubriken, Register, gesperrter Lead.
- **Aufträge:**
  - Validierung (z. B. keine unbekannten Arten wie „spam_versand“, keine Quelle „google_maps“)
  - Auswahl nur fälliger Firmen (Sperrliste, Sperre, Widerspruch, frische Daten, laufende Prüfung)
  - Bewertungs- und Karriere-Auftrag, Fehlerprotokoll, Fälligkeit, Pausieren
- **Login und Rollen:** Hash und Passwortregeln, Ersteinrichtung nur einmal, Bremse nach Fehlversuchen, Notfallzugang, letzte Administration, Rollenmatrix, kompletter HTTP-Ablauf mit Cookie-Attributen, 401/403, Abmelden, geschützte Druckansicht.
- **Sicherheit:**
  - DNS-Rebinding (421), Sicherheits-Header, fremder Origin, Formular-Content-Type, negative Content-Length, Pfad-Traversal
  - **alle rund 100 GET-Routen** (automatisch aus dem Code ermittelt) ohne Seiteneffekte auf die Datenbank und ohne 500
  - **alle Routen × POST/PUT/PATCH/DELETE × 7 fehlerhafte Anfragekörper** ohne einen einzigen 500
- **Last:**
  - 1.000 Firmen: Übersicht, Veraltung, CSV-Export, Prüfliste und Vorschläge jeweils unter 10 s; lokal gemessen deutlich darunter, die Übersicht mit 2.000 Firmen in etwa 0,13 s.
  - 8 parallele Schreiber × 25 Leads plus 3 parallele Leser: keine Fehler, 200 Leads, Integritätsprüfung ok.
- **Migration** von echten Altdatenbanken, erzeugt mit dem Code von **v0.9, v1.2 und v1.6** aus dem Git-Verlauf (fiktive Daten, `tests/fixtures/migration`):
  - Sicherung mit dem Altstand und Schema 17
  - `integrity_check` und `foreign_key_check` ohne Befund
  - Umlaute, Einwilligungsnachweis und Bedarfsanalyse erhalten; neue Spalten mit Standardwerten
  - GoBD-Schutz der festgeschriebenen Rechnung weiter aktiv
  - Research Center läuft auf der migrierten Datenbank; ein zweiter Start migriert nicht erneut
- **Verschlüsselte Sicherung:** Klartext nicht in der Datei, Wiederherstellung, falsches Passwort, Ziel existiert schon, zu kurzes Passwort, fehlendes Paket.
- **Klickdurchlauf im Browser** (Chromium, fiktive Daten), ohne Konsolenfehler:
  - Änderungen erkennen und übernehmen (Lead-Anschrift aktualisiert), Personendaten nach Fristablauf löschen
  - Auftrag anlegen und ausführen, Gewichte auf 60/20/20 (in der Research-Center-Grundlage sichtbar), verschlüsselte Sicherung
  - Administration anlegen, Login einschalten; zweiter Browser: Anmeldedialog, Fehlversuch, Anmeldung, Abmelden
  - Mobilansicht 390 px ohne Überlauf

## Was ist noch ungetestet?

- **Wiederkehrende Aufträge gegen echte Websites und Quellen.** Die Tests legen die Aufträge an, ohne Netzwerkzugriffe (`start=False` bzw. Stubs). Der Netzwerkteil ist derselbe wie in Phase 1–3 und dort ebenfalls nur gegen lokale Testseiten geprüft.
- **Dauerbetrieb des Hintergrund-Threads über Tage**, inklusive Standby des Rechners. Läuft SignalDesk nicht, wird nichts ausgeführt; fällige Aufträge laufen nach dem nächsten Start.
- **Team-Betrieb hinter einem echten TLS-Proxy** (Caddy, nginx) mit mehreren Personen gleichzeitig.
- **Migration sehr großer Altdatenbanken** (mehrere 100 MB) und von Datenbanken anderer Zwischenstände als v0.9, v1.2 und v1.6.

## Welche technischen oder rechtlichen Grenzen bestehen?

- **Kein eigenes HTTPS.** Im Netzwerk nur hinter einem TLS-Proxy betreiben, sonst gehen Passwörter im Klartext über das Netz.
- **Die Datenbank selbst ist unverschlüsselt.** Schutz bieten Laufwerksverschlüsselung (BitLocker, FileVault, LUKS) und verschlüsselte Sicherungen.
- **SQLite** ist für ein kleines Team ausreichend, aber kein Mehrmandanten-Server. Für einen echten Cloud-Betrieb fehlen unter anderem eine Server-Datenbank, Mandantentrennung, ein Auftragsverarbeitungsvertrag, EU-Hosting, Monitoring und 2FA (siehe `BETRIEB_UND_TEAM.md`).
- Die Bremse gegen Fehlversuche liegt im Arbeitsspeicher und wird beim Neustart zurückgesetzt. Sitzungen haben eine feste Laufzeit von 12 Stunden, keinen Leerlauf-Timeout.
- **Benutzerkonten enthalten Namen von Mitarbeitenden.** Diese sind über die Verarbeitung zu informieren (Beschäftigtendatenschutz).
- **Löschfristen** werden angezeigt und auf Klick umgesetzt, aber nicht automatisch vollzogen. Das ist bewusst so, damit nichts versehentlich verloren geht. Deshalb regelmäßig in „Datenqualität & System“ nachsehen.

## Was ist als Nächstes sinnvoll?

1. **Live-Durchlauf** mit 10–20 echten Zielfirmen über die ganze Kette, danach einen wiederkehrenden Auftrag „Änderungen erkennen“ (wöchentlich) und „Impressen aktualisieren“ (monatlich) anlegen.
2. **Ein-Klick-Start unter Windows** und **Lead-Finder-Quellen** live testen; beides steht seit Phase 0 aus.
3. Erst bei echtem Team-Bedarf: Betrieb hinter einem TLS-Proxy testen. Danach lässt sich über eine Server-Datenbank und Mandantenfähigkeit entscheiden.
