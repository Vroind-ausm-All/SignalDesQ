# Externe Sicherheitsprüfung vom 24.11.2026 – Auswertung und Stand der Behebung

Grundlage: Technischer Prüfbericht „Sicherheitsprüfung vor dem Livegang“ (Stand main 2.0.0-dev64, Commit 9509761).
Ergebnis des Berichts: **öffentlichen SaaS-Start zurückstellen**, Freigabereife 28/100, 12 Befunde (8 hoch, 4 erhöht).
Die Bewertung der Prüfung wird hier nicht neu berechnet: Ob die Behebungen tragen, entscheidet eine Nachprüfung.

Behoben in 2.0.0-dev65 (SDQ-033 bis SDQ-043), Abnahmetests in `tests/test_sdq033_pruefbericht.py`.

| Befund | Schwere | Stand | Was geändert ist | Was offen bleibt (und wer) |
|---|---|---|---|---|
| F01 Einladung an Identität binden | hoch | **behoben** | Annahme nur durch das Konto mit der eingeladenen Adresse (gleiche Normalisierung wie beim Kontoabgleich); Ablehnung verbraucht nichts und nennt keine Kontodaten; Verbrauch und Rolle in einer Transaktion | – |
| F02 Sitzungen nach Sicherheitsänderung widerrufen | hoch | **behoben** | Widerrufsstand je Konto; jede Organisationssitzung trägt ihn und endet bei Abweichung. Eigener Passwortwechsel, Betreiber-Reset, Sperre, zweiter Faktor ein/aus/zurückgesetzt: gleiche Regel. Pflicht zum zweiten Faktor wirkt sofort auch in offenen Organisationssitzungen | – |
| F03 Kalender-/Postfachzugänge an Ziel binden | hoch | **behoben** | Einrichten/Ändern nur durch die Verwaltung (Vertrieb: ansehen, testen, abgleichen, Entwürfe ablegen); bei neuem Host, Port, Schema oder Konto wird das gespeicherte Passwort verworfen | Geheimnis kryptografisch an Ziel binden (heute: Verwerfen beim Wechsel) |
| F04 Recherchekonfiguration isolieren | hoch | **behoben** | Schalter je Datenbank; Speichern geht vom Eintrag der eigenen Organisation aus | – |
| F05 Ausgehende Verbindungen begrenzen | hoch | **teilweise** | Im Mehrmandanten-Server serverseitig gesperrt: älterer Abruf ohne IP-Pinning, Browser (Recherche und Website-Bewertung); Kalender/Postfach nur öffentliche Namen, nur 443/993, Ziel bei jeder Verwendung erneut geprüft | Ausgangsregeln/Netztrennung auf dem Server (Betrieb); CalDAV/IMAP lösen den Namen nach der Prüfung erneut auf – ohne Egress-Regel bleibt DNS-Rebinding möglich |
| F06 Restore auf vertrauenswürdige Sicherungen begrenzen | hoch | **teilweise** | Wiederherstellen per Upload oder Dateiname über die Weboberfläche im Mehrmandanten-Server gesperrt; nur `betreiber zurueckspielen` mit Prüfsummen und Organisationszuordnung | Manifest signieren (Schlüsselverwaltung, Entscheidung), Sitzungen/Aufträge nach Restore in Quarantäne |
| F07 Lieferkette | hoch | **teilweise** | cryptography 50.0.2 (≥ 48.0.1) im Team-Lock; Installation ohne Lockdatei wird abgelehnt; GitHub Actions per Commit gepinnt | Release signieren/attestieren (Schlüssel, Entscheidung); Python 3.10 nicht mehr unterstützen (Entscheidung, betrifft Kunden) |
| F08 Login-Bremse hinter dem Proxy | hoch | **behoben (Code)** | `--vertrauter-proxy IP`: nur dessen X-Forwarded-For zählt (rechter Eintrag); sonst direkte Verbindung; Vorlagen für systemd und nginx angepasst | Nachweis in Staging hinter dem echten Proxy |
| F09 Passwort-Hashes, MFA-Geheimnisse | erhöht | **teilweise** | scrypt N=2^14, r=8, p=5 (OWASP-Profil); alte Hashes werden beim richtigen Login neu gebildet, beim falschen bleibt der Datensatz | Mindestlänge 15 bei nur einem Faktor, Zwei-Faktor-Pflicht für Verwaltung, TOTP-Seeds mit getrennt verwaltetem Schlüssel (Entscheidungen) |
| F10 Betriebsgrenzen | erhöht | **teilweise** | Öffentliche `/readyz`-Antwort höchstens alle 30 s neu berechnet (lokal immer frisch); Caddy-Vorlage mit 64-MB-Grenze | Kontingente für Importe je Organisation, Lasttest |
| F11 Formeln in Exporten | erhöht | **behoben (DATEV)** | DATEV-Stapel: Formelanfänge (= + - @, Tab) am Feldanfang entfernt; Hinweis „für DATEV, nicht für Excel“ | Probeimport in DATEV und Prüfung in Excel/LibreOffice (Steuerberatung) |
| F12 Protokollintegrität, Wiederanlauf | erhöht | **teilweise** | `betreiber protokoll-anker` gibt den Kettenstand aus; `protokoll-pruefen --anker DATEI` erkennt ein gekürztes Protokoll; Wiederherstellung der ganzen Installation und Kopie an zweiten Ort (dev65) | Anker regelmäßig extern ablegen, Alarm bei fehlender Sicherung, Übung auf leerem Ersatzsystem (Betrieb) |

## Ohne Entscheidung nicht änderbar

- **Python 3.10** aus den unterstützten Versionen nehmen (betrifft bestehende Installationen).
- **Mindestlänge 15 Zeichen** für Passwörter ohne zweiten Faktor und **Zwei-Faktor-Pflicht für die Verwaltung**.
- **Schlüsselverwaltung** für TOTP-Seeds, signierte Sicherungsmanifeste und signierte Releases (wer verwahrt welchen Schlüssel).
- **Betrieb:** Ausgangsregeln der Firewall, Staging hinter dem echten Proxy, externer Ablageort für Protokoll-Anker, Alarmierung.

## Nachprüfung

Der Bericht verlangt je Befund Release-Commit, Artefakt-Digest, verantwortliche Person und Gegenprüfung (Seite 13). Die
Abnahmetests dieses Standes stehen in `tests/test_sdq033_pruefbericht.py`; eine unabhängige Nachprüfung steht aus.
