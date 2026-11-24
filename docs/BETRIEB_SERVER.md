# Betriebshandbuch: SignalDesk als Server für mehrere Organisationen (ab 2.0.0-dev63)

Dieses Handbuch beschreibt den Betrieb auf einem eigenen Linux-Server: ein Dienst, eine Datenbank je Organisation, zentrale
Anmeldung mit zweitem Faktor, tägliche geprüfte Sicherung. Für den Einzelplatz und das kleine Team auf einem Rechner gilt
weiterhin [BETRIEB_UND_TEAM.md](BETRIEB_UND_TEAM.md).

**Stand:** Alles hier ist umgesetzt und automatisch getestet (`tests/test_sdq017_operations.py`,
`tests/test_sdq021_security.py`, `tests/test_sdq020_deploy.py`). Es ist **nicht** auf einem echten Server mit echten
Organisationen erprobt und nicht extern sicherheitsgeprüft. Vor dem ersten Kunden: Probebetrieb, Wiederherstellung einmal
von Hand durchspielen, externe Prüfung.

## 1. Bausteine

| Datei | Zweck |
|---|---|
| `deploy/signaldesk-mandanten.service` | Dienst (systemd), gehärtet, nur Datenordner und Protokollordner beschreibbar |
| `deploy/signaldesk-sicherung.service` + `.timer` | täglich 02:15 Uhr: verschlüsselter Sicherungssatz und Wiederherstellungstest |
| `deploy/umgebung.beispiel` | Pfade und öffentlicher Hostname (keine Passwörter) |
| `deploy/Caddyfile.beispiel`, `deploy/nginx.beispiel.conf` | TLS-Proxy davor |
| `python -m sales_tool.betreiber` | Verwaltung: Organisationen, Konten, Sicherungen, Protokoll |

## 2. Einrichten (einmalig)

```
sudo useradd --system --home /opt/signaldesk --shell /usr/sbin/nologin signaldesk
sudo mkdir -p /opt/signaldesk /srv/signaldesk /var/log/signaldesk /var/backups/signaldesk /etc/signaldesk
# Release entpacken nach /opt/signaldesk, dann:
cd /opt/signaldesk && sudo python3 -m venv .venv && sudo .venv/bin/pip install --require-hashes -r requirements-lock-team.txt
sudo cp deploy/umgebung.beispiel /etc/signaldesk/umgebung        # Hostnamen eintragen
sudo install -m 0640 -o root -g signaldesk /dev/null /etc/signaldesk/sicherung.geheim
sudoedit /etc/signaldesk/sicherung.geheim                           # SIGNALDESK_SICHERUNG_PASSWORT=… (mind. 12 Zeichen)
sudo chown -R signaldesk:signaldesk /srv/signaldesk /var/log/signaldesk /var/backups/signaldesk
sudo chmod 0700 /srv/signaldesk /var/backups/signaldesk
sudo cp deploy/signaldesk-*.service deploy/signaldesk-sicherung.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now signaldesk-mandanten signaldesk-sicherung.timer
```

Das Passwort der Sicherung **zusätzlich getrennt vom Server aufbewahren** (Passwort-Manager, Tresor). Ohne es ist keine
Sicherung wiederherstellbar.

Proxy: `deploy/Caddyfile.beispiel` nach `/etc/caddy/Caddyfile` (oder die nginx-Datei) und Hostnamen anpassen. Der Proxy
muss den Host-Header unverändert weiterreichen und `X-Forwarded-Proto: https` setzen; Caddy macht beides von selbst.

Bricht der Dienst mit `MemoryDenyWriteExecute` ab (nur bei zusätzlich installierten Paketen mit JIT denkbar), diese eine Zeile
entfernen.

## 3. Erste Organisation und erstes Konto

Alle Befehle als Benutzer `signaldesk`, `R=/srv/signaldesk`:

```
sudo -u signaldesk .venv/bin/python -m sales_tool.betreiber --root $R anlegen studio-nord "Studio Nord"
sudo -u signaldesk .venv/bin/python -m sales_tool.betreiber --root $R konto-anlegen erika "Erika Beispiel"   # fragt Passwort ab
sudo -u signaldesk .venv/bin/python -m sales_tool.betreiber --root $R mitglied erika studio-nord admin
sudo -u signaldesk .venv/bin/python -m sales_tool.betreiber --root $R zwei-faktor-pflicht an
sudo systemctl restart signaldesk-mandanten   # neue Organisation laden (Migration, Planer)
```

Mit eingeschalteter Pflicht richtet jede Person bei der ersten Anmeldung den zweiten Faktor ein (Authenticator-App,
Schlüssel abtippen) und bekommt zehn Wiederherstellungscodes. Ohne Pflicht kann jede Person ihn unter „Zwei-Faktor-Anmeldung“
selbst einschalten.

## 4. Überwachen

| Prüfung | Aufruf | Erwartung |
|---|---|---|
| Prozess lebt | `curl -fsS http://127.0.0.1:8765/healthz` | `{"status": "ok", …}` |
| Bereit | `curl -sS http://127.0.0.1:8765/readyz` | HTTP 200, `bereit`; 503 bei Fehler (Verzeichnis nicht beschreibbar, Organisation nicht lesbar oder falsches Schema, < 512 MB frei) |
| Sicherung | `/readyz` → `sicherung` | Warnung, wenn die letzte **geprüfte** Sicherung älter als 26 Stunden ist |
| Sicherungslauf | `systemctl status signaldesk-sicherung` | `status=0/SUCCESS`; 1 heißt: Wiederherstellungstest fehlgeschlagen |
| Gesamt | `sudo -u signaldesk … betreiber --root $R zustand --ziel /var/backups/signaldesk` | Rückgabewert 0 |

Von außen (über den Proxy) liefert `/readyz` nur das Ergebnis, keine Einzelheiten. Ein externer Überwachungsdienst kann
`https://app.example.org/healthz` und `/readyz` abfragen.

## 5. Protokolle

- **Betriebsprotokoll** `/var/log/signaldesk/betrieb.jsonl`: eine JSON-Zeile je Anfrage (`ts`, `rid`, `method`, `route`,
  `status`, `ms`, `org`) sowie `start`, `stopp`, `beendet` und `serverfehler`. Zahlen und lange Kennungen im Pfad sind durch
  `:id` ersetzt; Abfrageparameter, Cookies, IP-Adressen und Inhalte stehen nicht darin. Rotation: 10 Dateien × 10 MB.
  Jede Antwort trägt die Anfrage-Nummer im Kopf `X-Request-ID`. Bei einer Fehlermeldung „Interner Serverfehler“ steht sie
  auch in der Antwort, damit ein Fall im Protokoll gefunden wird.
- **Verwaltungs- und Anmeldeprotokoll** (im Verzeichnis, Tabelle `audit_events`): wer wann Konten, Mitgliedschaften,
  Organisationen, Sicherungen, Exporte und den zweiten Faktor geändert hat, dazu Anmeldungen und Fehlversuche (mit IP).
  Ansehen: `betreiber … protokoll --anzahl 50 [--konto erika]`. Hash-Kette nachrechnen: `betreiber … protokoll-pruefen`
  (Rückgabewert 1, wenn ein Eintrag verändert oder entfernt wurde). Die Kette erkennt Änderungen an einzelnen Einträgen,
  nicht das Austauschen der ganzen Datei – dagegen helfen die Sicherungssätze an einem getrennten Ort.

## 6. Sicherung und Wiederherstellung

Ein **Sicherungssatz** ist ein Ordner `JJJJMMTT-HHMMSS` mit dem Verzeichnis (`organisationen.sqlite3`), jeder Organisation
(auch archivierte) unter `orgs/` und `manifest.json` (Prüfsumme und Zeilenzahl jeder Tabelle). Mit `--verschluesselt` ist
jede Datei mit AES-256-GCM verschlüsselt (`.sdenc`).

Der **Wiederherstellungstest** (`--pruefen` bzw. `sicherung-pruefen NAME`) entschlüsselt jede Datei in einen
temporären Ordner, prüft Prüfsumme, `integrity_check` und alle Zeilenzahlen gegen das Manifest und migriert eine Kopie
auf das aktuelle Schema. Das Ergebnis steht in `pruefung.json` und im Protokoll.

Eine Organisation zurückspielen (die anderen bleiben unberührt):

```
sudo -u signaldesk … betreiber --root $R sicherungen --ziel /var/backups/signaldesk
sudo -u signaldesk … betreiber --root $R zurueckspielen 20261124-021500 studio-nord --ziel /var/backups/signaldesk --ja
```

Dabei gelten die Regeln der lokalen Wiederherstellung: Der aktuelle Stand wird vorher gesichert
(`…-vor-wiederherstellung`), und eine Sicherung ohne inzwischen festgeschriebene Rechnungen wird abgelehnt (GoBD).

**Ganze Installation** (Server verloren): Release und Umgebung wie in Abschnitt 2 einrichten, dann den letzten Satz
entschlüsseln (`python -m sales_tool.backup_crypto entschluesseln DATEI.sdenc ZIEL.sqlite3`) und
`organisationen.sqlite3` nach `/srv/signaldesk/`, jede `orgs/<kennung>.sqlite3` nach
`/srv/signaldesk/orgs/<kennung>/signaldesk.sqlite3` legen. Dienst starten, `/readyz` prüfen. Dieser Ablauf ist **nicht**
automatisiert und sollte vor dem ersten Kunden einmal geübt werden.

**Aufbewahrung:** Sätze werden nicht automatisch gelöscht. `betreiber … sicherungen-aufraeumen --behalten 30` entfernt
ältere Sätze nur auf ausdrücklichen Aufruf; der neueste geprüfte Satz bleibt immer. Sicherungen sollten zusätzlich an einen
zweiten Ort (anderer Datenträger oder Anbieter) kopiert werden – das übernimmt SignalDesk nicht.

## 7. Häufige Fälle

| Fall | Vorgehen |
|---|---|
| Passwort vergessen | `betreiber … passwort-setzen erika` (beendet alle Sitzungen des Kontos) |
| Telefon verloren, keine Codes | Person zweifelsfrei erkennen, dann `betreiber … zwei-faktor-zuruecksetzen erika`; bei Pflicht richtet sie ihn bei der nächsten Anmeldung neu ein |
| Person verlässt eine Organisation | `betreiber … entziehen erika studio-nord` (wirkt sofort) |
| Verdacht auf fremden Zugriff | `betreiber … konto-sperren erika`, dann `protokoll --konto erika` ansehen |
| Organisation kündigt | `betreiber … export studio-nord --out studio-nord.zip.sdenc --verschluesselt`, Passwort getrennt übergeben, danach `archivieren` |
| Update | Dienst stoppen, Sicherung mit Prüfung von Hand (`sichern --verschluesselt --pruefen`), Release ersetzen, Dienst starten (migriert alle Organisationen), `/readyz` prüfen |

## 8. Was noch fehlt

- Kein Betrieb mit echten Organisationen, keine externe Sicherheitsprüfung, kein Lasttest.
- Sicherungen gehen nicht automatisch an einen zweiten Ort; Wiederherstellung der ganzen Installation nur von Hand.
- Das Geheimnis des zweiten Faktors liegt unverschlüsselt im Verzeichnis (geschützt durch Dateirechte und die
  verschlüsselten Sicherungen). Kein WebAuthn/Passkey, kein OIDC/Single Sign-on.
- Kein Leerlauf-Abmelden; Sitzungen enden nach 12 Stunden.
- Kein Container-Abbild und keine Metriken im Prometheus-Format; Überwachung über `/healthz`, `/readyz` und die Protokolle.
- Für Datenschutz und Vertrag (Auftragsverarbeitung, TOMs, Verzeichnis der Verarbeitungstätigkeiten, Aufbewahrungsfristen
  für Protokolle) gibt es Bausteine, aber keine geprüften Unterlagen.
