# Bericht Masterplan 2.0 – Sprint 6 (SignalDesk v1.19)

Auftrag: „Sprint 6 starten und fertigstellen“. Hinweis des Nutzers dazu: Unter Windows funktioniert alles, **außer der
automatischen Datenübertragung ins Firmenprofil**.

**Sprint 6 laut Plan:** Windows-Release und SaaS-Vorbereitung.
- **Aufgaben:**
  - Windows-Installationsvarianten, Browser-Abhängigkeiten optional;
  - Lockfile, Release-SBOM;
  - automatische Tests Windows/Linux;
  - Offline-Modus, Backup/Restore;
  - Integrationstest, UI-E2E, Performancebericht.
- **Fertig, wenn:**
  - eine reproduzierbare Installation auf einem frischen Windows-Rechner gelingt;
  - keine Datenbankverluste auftreten;
  - eine messbare Qualitätsverbesserung vorliegt;
  - die offenen Einschränkungen dokumentiert sind.

## 0. Fehlerbehebung: automatische Datenübertragung ins Firmenprofil (`sales_tool/lead_imprint.py`)

Im Code gefunden und mit Tests nachgestellt (`tests/test_v119_company_data.py`). Bis v1.18 kamen Firmendaten auf diesen Wegen nicht im Lead an:

| Ursache | Folge bis v1.18 | Jetzt |
|---|---|---|
| **Website-Vorschlag** (Empfehlung A, v1.15) – betrifft fast alle Firmen aus OpenStreetMap/Wikidata (keine Registernummer) | Bei „Übernehmen“ wurde die Website am Lead entfernt, die schon gelesenen Impressumsdaten verworfen; bestätigen ließ sich der Vorschlag danach nirgends, und der Firmen-Bericht lief mangels Website nicht | Die Firmenakte zeigt „Website-Vorschlag … ✓ Website passt – Daten übernehmen / ✕ passt nicht“, auch nach der Übernahme. Bestätigt → Website am Lead, Firmendaten sofort übertragen |
| **Website „laut Quelle“** (OSM, Wikidata) | Das Impressum wurde erst mit dem Firmen-Bericht gelesen | Bei „Übernehmen“ liest ein Hintergrund-Auftrag das Impressum und überträgt die Daten automatisch |
| **Website von Hand eingetragen** (neuer Lead oder geändert) | nichts geschah | Auftrag startet automatisch |
| **Knopf „Impressum prüfen“** im Lead-Fenster | führte in „Import & Prüfung“ zur manuellen Übernahme | „Impressum lesen & übernehmen“ – automatisch in leere Felder |
| **Anzeigename aus OSM** („Kesselwerk“) | wurde als *Firmenname laut Register* eingetragen und blockierte den echten Namen aus dem Impressum | Registername nur noch, wenn die Quelle ihn liefert (GLEIF oder Name mit Rechtsform) |

**Leitplanken (unverändert):**
- belegte Werte nur in **leere** Felder;
- nichts wird überschrieben;
- **keine Personen** automatisch;
- die Kontakterlaubnis bleibt unverändert;
- gesperrte Firmen werden nicht abgerufen.

**Sichtbarkeit:** Die Firmenakte zeigt „Firmendaten aus dem Impressum“ mit Zustand und Grund:
- übertragen (mit Liste der Felder);
- wird gelesen;
- Website bestätigen;
- keine Website;
- kein Impressum gefunden / nicht erreichbar.

Dazu „Impressum erneut lesen“. Unter „Datenqualität & System“ lässt sich die Automatik ausschalten. Der Firmen-Bericht nutzt dieselbe Funktion.

## 1. Installationsvarianten (`sales_tool/bootstrap.py`)

| Variante | Inhalt | Größe |
|---|---|---|
| `basis` | nur Python-Standardbibliothek; Website-Recherche per HTTP | 0 Zusatzpakete |
| `browser` (Standard, wie bisher) | + Browser-Prüfung für JavaScript-Seiten (Playwright + Chromium) | 4 Pakete + ca. 150 MB Chromium |
| `team` | + verschlüsselte Sicherungen (`cryptography`) | + 3 Pakete |
| `voll` | + Recherche-Extras (Scrapling-Auswertung, Trafilatura, RapidFuzz) | + 24 Pakete |

- **Auswahl:**
  - Beim ersten Einrichten fragt SignalDesk (Enter = Standard).
  - Später: `SignalDesk_starten.bat --variante team`.
  - Ein Wechsel installiert nach; die Wahl wird gemerkt.
- **Neue Doppelklick-Dateien:**
  - `SignalDesk_offline_starten.bat`: nichts installieren, keine Abrufe;
  - `SignalDesk_wiederherstellen.bat`: Sicherungsdatei per Maus darauf ziehen.
- **Offline-Paket:** Liegt ein Ordner `wheels/` neben dem Programm, installiert pip nur daraus (`--no-index`). Erzeugt wird es mit `tools/build_release.py --offline-wheels win_amd64:3.12:browser`.

## 2. Feste Versionen mit Prüfsummen (`tools/make_lock.py`, `requirements-lock-*.txt`)
- **Aufgelöst wird für 8 Ziele:** Windows x64 und Linux x64, jeweils Python 3.10, 3.11, 3.12 und 3.13.
  - Je Paket gilt **eine** Version, die auf **allen** Zielen installierbar ist.
  - Unterschiedliche Versionen je Ziel werden auf die gemeinsame älteste festgelegt, z. B. `pyee` 13 statt 14 und `cssselect`/`w3lib`, deren neueste Fassung Python 3.11 verlangt.
- **Wartezeit 14 Tage:** Mitgezogene Pakete werden erst genommen, wenn sie mindestens 14 Tage veröffentlicht sind (Schutz vor frisch kompromittierten Releases). Ausnahme sind nur die bewusst geprüften Hauptpakete mit `==` (Scrapling 0.5.1 aus Sprint 1).
  - Beispiel: `python-dateutil 4.0.0` (6 Tage alt) und das neue `frostwork` (2 Tage, Scrapy-Projekt) wurden dadurch ausgelassen.
- **Prüfsummen:** Jede Paketzeile trägt die SHA-256 aller Dateien dieser Version. Installiert wird mit `pip install --require-hashes`.
- **Gegenprobe:** Installation jeder Lockdatei in eine frische Umgebung. Scrapling, Trafilatura und RapidFuzz liefen danach.
- **Protokoll:** `docs/bench/lock-resolution.json`.

## 3. Stückliste (SBOM) und Lizenzen (`tools/make_sbom.py`)
- **CycloneDX 1.5** (`sbom/signaldesk.cdx.json`) mit 33 Bestandteilen:
  - 30 Python-Pakete mit Version, Lizenz, Prüfsummen, Variante und Veröffentlichungsdatum;
  - Python-Laufzeit, Chromium;
  - das mitgelieferte GeoNames-Ortsverzeichnis (CC BY 4.0, mit Prüfsumme);
  - die 6 abgefragten Online-Quellen mit ihrer Datenlizenz.
- **Lesbar:** `docs/BESTANDTEILE.md`. Deterministisch erzeugt; die CI prüft, dass beide aktuell sind.
- **Lizenzen:** Alle Pakete haben eine erkannte Lizenz. Keines verlangt GPL/AGPL (`tld` ist mehrfach lizenziert und wird unter MPL-1.1 genutzt).

## 4. Reproduzierbares Release (`tools/build_release.py`)
- **Inhalt:** ZIP mit allem, was git verwaltet, ohne Tests/Werkzeuge/CI, plus Lockdateien, SBOM und `MANIFEST.sha256` (Prüfsumme je Datei).
- **Reproduzierbar:** feste Reihenfolge, Zeitstempel des letzten Commits, feste Dateirechte. **Zweimal gebaut ergibt eine byte-gleiche Datei** (lokal und als CI-Prüfung).
- **Sicherheitsprüfung:** Abbruch, wenn Datenbanken, Sicherungen, `.env`, Schlüsseldateien oder etwas wie ein geheimer Schlüssel enthalten wären.
- **v1.19:** 150 Dateien, ca. 1,0 MB. Prüfsumme in `SignalDesk-1.19.0.zip.sha256`.

## 5. Offline-Modus (`sales_tool/netpolicy.py`)
- **Einschalten:** unter „Datenqualität & System“ (dauerhaft) oder mit `--offline` bzw. `SignalDesk_offline_starten.bat` (für eine Sitzung). In der Seitenleiste steht dann „⚡ Offline-Modus“.
- **Gesperrt ist jeder Abruf durch SignalDesk:**
  - offene Quellen;
  - Website- und Impressumsabrufe;
  - robots.txt;
  - Browser-Prüfung;
  - Sammelsuche und Quellen-Check.
- **Aufträge, die Internet brauchen, warten** statt fehlzuschlagen. Nach dem Ausschalten laufen sie weiter.
- **Erlaubt bleiben:** lokale Arbeit (CRM, Angebote, Buchhaltung, Katalog-Import und -Suche, Sicherungen) und die lokale KI.

## 6. Sicherung und Wiederherstellung (`sales_tool/backup_restore.py`)

Neu: die Wiederherstellung. Bisher gab es nur das Sichern.
1. **Prüfen:** echte SQLite-Datei, `integrity_check`, SignalDesk-Tabellen; ein Schema aus einer neueren Version wird abgelehnt. `.sdenc` wird mit Passwort entschlüsselt.
2. **GoBD-Schutz:** Fehlen in der Sicherung festgeschriebene Rechnungen, die es jetzt gibt, wird abgelehnt (mit Rechnungsnummern).
3. **Vorher sichern:** Der aktuelle Stand wird als „…-vor-wiederherstellung“ gesichert. Damit ist die Wiederherstellung selbst umkehrbar. Ist die aktuelle Datei beschädigt, wird sie unverändert beiseitegelegt.
4. **Einspielen und migrieren:**
   - atomar über die SQLite-Backup-Schnittstelle, auch während SignalDesk läuft;
   - danach Migration auf das aktuelle Schema, auch von älteren Versionen (getestet ab Stand v1.17).

**Bedienung:**
- Liste aller Sicherungen mit „Wiederherstellen“ und Upload einer Datei von anderem Ort (Datenqualität & System);
- `SignalDesk_wiederherstellen.bat`;
- auf der Kommandozeile: `python -m sales_tool.backup_restore wiederherstellen <datei>`.

## 7. Automatische Prüfung (`.github/workflows/tests.yml`)

| Job | Was | Wo |
|---|---|---|
| unit | alle Tests ohne Zusatzpakete | Windows + Linux × Python 3.10 und 3.13 |
| install | `tools/install_check.py`: Release-ZIP in „Mein Ordner – Übung“ entpacken, Prüfsummen, Einrichtung wie per Doppelklick, Start, Lead, Sichern, Wiederherstellen, Neustart ohne Datenverlust | **frische** Windows- und Linux-Maschine × Variante basis und browser |
| e2e | Oberflächen-Test in Chromium (`tests/e2e/test_ui_workday.py`) | Linux, Variante browser |
| release | ZIP zweimal bauen und vergleichen, SBOM und Bestandteile aktuell | Linux |

**Lokal geprüft** (Linux, Python 3.13):
- Installationsprüfung „basis“: **15/15** bestanden (Einrichtung 2 s, Start 0,4 s).
- Installationsprüfung „browser“: 15/16. Die Pakete mit Prüfsummen installieren sich und lassen sich importieren; nur der Chromium-Download ist in der Entwicklungsumgebung durch deren Netzregeln gesperrt. Auf GitHub prüft das der CI-Job.
- UI-E2E bestanden (23 s): Beispieltag, Firmendaten über Website-Vorschlag, Sperre, Tagesabschluss, Offline-Modus, Wiederherstellen-Liste, Handyansicht ohne seitliches Scrollen.

Das Ergebnis auf Windows steht im Pull Request (CI-Lauf).

## 8. Messung (`tools/perf_report.py`, `docs/bench/v1.19-performance.json`)

**Website-Abruf im Testgelände (33 fiktive Websites):**

| | v1.14 | v1.16 | **v1.19** |
|---|---|---|---|
| erwartetes Verhalten | 25/33 | 33/33 | **33/33** |
| Impressumsfelder korrekt | 79,6 % | 100 % | **100 %** |
| P50 / P95 je Website | 36,8 / 102,7 ms | 13,8 / 24,1 ms | **10,9 / 16,2 ms** |
| Abrufe gesamt | 123 | 91 | **91** |
| Verbindungen zu ungeprüften Adressen | 1 | 0 | **0** |
| Werte mit Beleg im Originaltext | – | 187/187 | **187/187** |

**Mit großem Bestand (5.000 Leads, 2.000 neue Treffer):**

| | Wert |
|---|---|
| Dubletten-Abgleich je Treffer | **1,05 ms** (vorher 28,9 ms) |
| Migration der großen Datenbank (einmalig, mit Bereinigung) | **0,7 s** (vorher 23,2 s) |
| Antwortzeit P50/P95: Leads (alle 5.000) | 101 / 115 ms |
| Heute | 18 / 20 ms |
| Sichtung (50 je Seite) | 6 / 7 ms |
| Firmenakte | 4 / 5 ms |
| Tagesabschluss | 9 / 11 ms |
| Sichern / Wiederherstellen (2,6 MB) | 9 ms / 55 ms |
| Spitze Arbeitsspeicher (alles zusammen) | 84 MB |

**Durch die Messung gefunden und behoben:**
1. **Optionaler Import bei jedem Vergleich:** Ohne RapidFuzz (Standard) versuchte Python bei *jedem* Namensvergleich erneut den Import. Das kostete ein Drittel der Zeit.
2. **Wiederholte Normalisierung:** Namen wurden für jeden Vergleich neu normalisiert, und die Ähnlichkeit wurde auch berechnet, wenn der Ort schon verschieden war.
   - Behoben durch Zwischenspeicher (begrenzt auf 50.000 Einträge; der Katalog-Import umgeht ihn, damit der Speicher-Nachweis aus Sprint 4 hält) und eine schnelle Obergrenze vor der vollen Berechnung.
   - Die Ergebnisse sind identisch; alle Dubletten-Tests sind mit beiden Engines grün.
3. **Falsche Server-Kennung:** Der Server meldete sich seit v1.16 im HTTP-Kopf als `SignalDesk/1.16`, weil die Version fest eingetragen war. Sie kommt jetzt zentral aus `__version__`, ein Test prüft alle Versionsstellen.

## 9. Abnahme

| Kriterium | Nachweis |
|---|---|
| reproduzierbare Installation auf frischem Windows-Rechner | CI-Job „install“ auf `windows-latest` (frische VM je Lauf) aus der byte-gleich reproduzierbaren ZIP, feste Versionen mit Prüfsummen; lokal Linux 15/15 |
| keine Datenbankverluste | Sichern → Wiederherstellen → Neustart in der Installationsprüfung; Vorab-Sicherung, GoBD-Schutz, beschädigte DB, alte Schemas, verschlüsselt (`tests/test_sprintS6_release.py`) |
| messbare Qualitätsverbesserung | Tabelle oben (v1.14 → v1.19), Leistungsfehler durch Messung gefunden und behoben |
| dokumentierte Einschränkungen | `docs/EINSCHRAENKUNGEN.md` |

## Tests
- **Unit- und Integrationstests: 413**, davon 25 neu:
  - 19 in `tests/test_sprintS6_release.py`;
  - 6 in `tests/test_v119_company_data.py`.
- **Dazu:** UI-E2E (`tests/e2e/test_ui_workday.py`, läuft separat mit der Variante „browser“) und Installationsprüfung (`tools/install_check.py`).

## Sicherheits- und Lizenzrisiken
- **Neue Abhängigkeiten im Kern:** keine; die Varianten installieren nur gesperrte Versionen mit Prüfsummen.
- **CI-Rechte:** Die Workflows haben nur Leserechte (`permissions: contents: read`).
- **Pinning der Actions:** Die GitHub-Actions sind per Versions-Tag eingebunden, nicht per Commit-Hash. Eine strengere Festlegung ist ein möglicher nächster Schritt.
- **Wiederherstellung:** nur mit ausdrücklicher Bestätigung und nur für die Rolle Administration (`/api/backup.*`).

## Nach diesem Sprint (laut Plan)
- **Mandantenarchitektur** (API/MCP, PostgreSQL, getrennte Worker) erst *spezifizieren*, nicht bauen.
- **Live-Test** der Quellen und echter Impressen mit deinen Daten (letzter Live-Test: v1.14).
