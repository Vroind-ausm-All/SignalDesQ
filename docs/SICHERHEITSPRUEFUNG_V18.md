# Sicherheitsprüfung SignalDesk v1.8 (Phase 6)

Stand: November 2026.

**Vorgehen:**
- Code-Durchsicht aller HTTP-Routen, SQL-Aufrufe, Dateizugriffe und Netzwerkzugriffe.
- Automatische Tests in `tests/test_phase6_quality.py`:
  - alle Routen werden aus dem Code ermittelt;
  - GET-Anfragen ohne Seiteneffekte;
  - fehlerhafte Anfragen ohne Serverfehler;
  - Host-, Origin- und Header-Prüfungen.
- Geheimnis-Scan des Repositorys.

Diese Prüfung ersetzt keinen externen Penetrationstest.

## Bedrohungsmodell

| Betriebsart | Annahmen |
|---|---|
| **Lokaler Einzelplatz (Standard)** | Server nur an 127.0.0.1, kein Login. Angreifer sind fremde Webseiten im selben Browser (CSRF, DNS-Rebinding, Clickjacking) und manipulierte Inhalte gecrawlter Websites (SSRF, XSS über Fundstellen). |
| **Kleines Team (optional)** | Login-Pflicht, Betrieb hinter einem TLS-Proxy im internen Netz. Zusätzlich: Passwort-Raten und Rechteausweitung zwischen Rollen. |

## Befunde und Maßnahmen

| # | Befund | Schwere | Status |
|---|---|---|---|
| 1 | **DNS-Rebinding:** Der Host-Header wurde nicht geprüft. Eine fremde Seite hätte nach Umbiegen ihres DNS-Namens auf 127.0.0.1 die API lesen und, da Origin und Host dann übereinstimmen, auch schreiben können. | hoch | **behoben:** nur 127.0.0.1, localhost, ::1 und per `--allowed-host` freigegebene Namen, sonst 421 |
| 2 | **Clickjacking:** Die Oberfläche ließ sich in fremde Seiten einbetten. | mittel | **behoben:** `frame-ancestors 'none'`, `X-Frame-Options: DENY` |
| 3 | **Referrer:** Lokale URLs konnten beim Öffnen externer Links übertragen werden (Links nutzen bereits `noreferrer`). | niedrig | **behoben:** `Referrer-Policy: no-referrer`, zusätzlich `Cross-Origin-Opener-Policy` und `Permissions-Policy` |
| 4 | **Robustheit:** Ein JSON-Array oder JSON-String als Anfragekörper führte bei `/api/tasks` und `/api/activities` zu HTTP 500 (gefunden durch den neuen Fehlertest). | niedrig | **behoben:** Anfragekörper muss ein JSON-Objekt sein, sonst 400; auch ungültiges UTF-8 und zu tiefe Verschachtelung führen zu 400 |
| 5 | **Audit-Log mit Personendaten:** Ein Widerspruch schrieb den Namen der Person ins unveränderbare Audit-Log. Er wäre damit auch nach Ablauf der Löschfrist erhalten geblieben. | mittel (DSGVO) | **behoben:** Eintrag nur mit Lead- und Kontakt-ID; der Löschnachweis ist ebenfalls ohne Namen |
| 6 | **Content-Length** nicht numerisch oder negativ | niedrig | war bereits 400, jetzt ausdrücklich geprüft |
| 7 | **GET mit Seiteneffekten** (Cross-Site-GET über `<img>` ohne Origin-Header) | – | **kein Befund:** alle rund 100 GET-Routen verändern die Datenbank nicht (Test) |
| 8 | **SQL-Injection** | – | **kein Befund:** alle Werte sind parametrisiert. Spalten- und Tabellennamen in f-Strings kommen ausschließlich aus festen Listen (geprüft: `accounting`, `buying_signals`, `company_data`, `imprint_batch`, `sales_integration`, `quality`, `server`) |
| 9 | **Pfad-Traversal** | – | **kein Befund:** statische Dateien nur über eine feste Liste; Screenshots nur innerhalb des Screenshot-Ordners (aufgelöster Pfad) |
| 10 | **SSRF** | – | unverändert geschützt: öffentliche Ziel-IP, DNS- und Redirect-Prüfung, Größen- und Ratenlimits, robots.txt. Wiederkehrende Aufträge nutzen genau diese Wege. |
| 11 | **XSS über gecrawlte Inhalte** | – | CSP ohne Inline-Skripte und Inline-Styles; alle Ausgaben laufen über `escapeHTML` |
| 12 | **Geheimnisse im Repository** | – | **kein Befund** (Scan nach API-Schlüsseln, privaten Schlüsseln, Tokens) |
| 13 | **Kein Login** im lokalen Betrieb | Design | bewusst so. Der Start im Netzwerk (`--host`) wird ohne Login-Pflicht verweigert |
| 14 | **Kein HTTPS** | Design | für den Team-Betrieb einen TLS-Proxy verwenden (Hinweis in Oberfläche und Doku) |
| 15 | **Datenbank im Klartext** | Design | Laufwerksverschlüsselung empfehlen; optionale verschlüsselte Sicherungen (AES-256-GCM) |

## Login und Sitzungen (neu)

- **Passwörter:** scrypt (n=2^14, r=8, p=1), 16 Byte Salt, Vergleich in konstanter Zeit. Bei unbekanntem Benutzer wird trotzdem ein Hash berechnet, damit die Antwortzeit nichts verrät.
- **Passwortregeln:** mindestens 10 Zeichen, nicht der Benutzername, nicht trivial.
- **Sitzungen:** 32-Byte-Zufallstoken; gespeichert wird nur der SHA-256-Hash. Cookie mit `HttpOnly`, `SameSite=Strict` und `Path=/`, hinter einem TLS-Proxy zusätzlich `Secure`. Laufzeit 12 Stunden. Abmelden, Passwortwechsel und Deaktivieren beenden die Sitzungen.
- **CSRF:** `SameSite=Strict` plus Origin-Prüfung plus „nur JSON“ (ein Cross-Site-Formular kann kein `application/json` senden).
- **Brute-Force:** höchstens 5 Fehlversuche in 15 Minuten je Benutzer und je IP-Adresse (HTTP 429). Fehlversuche werden protokolliert.
- **Rollen:** serverseitig je Route geprüft. Benutzerverwaltung, Einstellungen, Backups und Buchhaltungs-Stammdaten sind der Administration vorbehalten. Die letzte aktive Administration lässt sich nicht entfernen.

## Restrisiken

- Die Bremse gegen Fehlversuche liegt im Arbeitsspeicher und wird beim Neustart zurückgesetzt.
- Kein zweiter Faktor (2FA), kein Leerlauf-Timeout für Sitzungen.
- Wer Zugriff auf das Benutzerkonto des Rechners hat, hat Zugriff auf die SQLite-Datei. Login schützt nur den Zugriff über den Browser.
- Abhängigkeiten: Der Kern nutzt nur die Standardbibliothek. Playwright und `cryptography` sind optional und auf Versionsbereiche festgelegt; vor produktivem Einsatz auf konkrete Versionen festlegen und regelmäßig aktualisieren.
