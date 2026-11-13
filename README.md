# SignalDesk – Kunden finden, bewerten, erreichen, abrechnen (lokal)

> **Stand 2.0.0-dev15: Entwicklungsstand, kein fertiges Release.** Geprüft mit automatischen Tests unter Linux (Python 3.10, 3.12, 3.13) und im Browser. Erste Messung an echten Quellen: [`docs/PRAXISTEST_70191.md`](docs/PRAXISTEST_70191.md); Website-Zuordnung noch ungemessen. Vor der Nutzung vorhandener Daten eine Sicherung erstellen.

SignalDesk ist ein Vertriebsarbeitsplatz für Soloselbstständige und kleine Dienstleister. Es läuft auf deinem Rechner, speichert alles in einer lokalen Datei und versendet nichts.

**Der Ablauf:** Firmen finden → Website und Impressum mit Beleg prüfen → Firma bewerten → erlaubten Kontaktweg klären → Gespräch und Bedarf festhalten → Festpreisangebot → Rechnung.

## Starten in zwei Schritten

1. **Herunterladen und entpacken**: auf GitHub *Code → Download ZIP*, danach Rechtsklick auf die ZIP-Datei → **„Alle extrahieren…“**.
2. **Doppelklick auf die Startdatei**:
   - **Windows:** `SignalDesk_starten.bat`
   - **macOS:** `SignalDesk_starten.command` (beim ersten Mal Rechtsklick → „Öffnen“, weil die Datei nicht von Apple signiert ist)
   - **Linux:** `./start.sh`

Beim **ersten Start** richtet SignalDesk alles selbst ein: Es sucht Python 3.10+ (unter Windows wird bei Bedarf die automatische Installation über winget angeboten), legt eine eigene Umgebung an, installiert den Website-Crawler und erstellt unter Windows eine **Desktop-Verknüpfung „SignalDesk“**. Danach **öffnet sich die Oberfläche automatisch im Browser**. Das dauert einmalig 1–3 Minuten.

**Ab dem zweiten Start** öffnet sich SignalDesk in wenigen Sekunden – per Desktop-Verknüpfung oder Startdatei. Läuft SignalDesk schon, öffnet ein weiterer Doppelklick nur das Browserfenster. Ist Port 8765 belegt, weicht SignalDesk auf den nächsten freien Port aus.

- Das schwarze Fenster offen lassen, solange du arbeitest. Schließen = SignalDesk beenden.
- Ohne Internet startet SignalDesk trotzdem; nur die Website-Recherche fehlt, bis der Crawler installiert ist (neuer Versuch einmal täglich oder mit `--reinstall`).
- Deine Daten liegen außerhalb des Programmordners (`%USERPROFILE%\.akquise-tool\`). Ein Update heißt: neue ZIP entpacken, alte Startdatei nicht mehr verwenden – die Daten bleiben erhalten. Vorher trotzdem ein Backup anlegen.

Ganz automatisch beim Herunterladen kann nichts starten: Browser und Betriebssystem führen heruntergeladene Dateien aus Sicherheitsgründen nie selbst aus. Ein Doppelklick ist das Minimum.

## Was SignalDesk kann

| Bereich | Inhalt |
|---|---|
| **Heute** | Die drei nächsten Schritte mit Grund und Frist; Eingang für verpasste Anrufe mit Rückruffrist, „als Nächstes kontaktieren“, Auslastung, Wiedervorlage; Tagesplan und Tagesabschluss zum Aufklappen; „Erste Schritte“ für den Einstieg |
| **Firmen finden** | GLEIF, Wikidata und TED gleichzeitig, OpenStreetMap offline aus einem lokalen Auszug; ohne Dubletten; PLZ-genau, ganze Stadt oder Umkreis; großer GLEIF-Katalog offline; Suchprofile mit Budget |
| **Recherchieren** | Firmen-Bericht mit einem Klick: Impressum, Website-Bewertung, Inhalte, Karriereseite, Kaufsignale – jede Angabe mit Fundstelle |
| **Bewerten** | Zielkundenprofil; Passung vor dem Gespräch (A, B, C), Qualifizierung danach, K.-o.-Kriterien; Unbekanntes zählt nicht als schlecht |
| **Erreichen** | Belegte Kontaktwege, Anrufversuche mit Zeitfenster, Wiedervorlage nach „nicht erreicht“, eigene Zeiten, Terminvorschläge, Textbausteine |
| **Verkaufen** | Pipeline, Firmenakte mit Reitern, Bedarf bestätigen, Festpreisangebote aus einem Katalog mit 26 Leistungen, Verlustgründe, Nachkalkulation mit tatsächlichen Stunden |
| **Abrechnen** | Rechnungen nach § 14 UStG, GoBD-Festschreibung, Zahlungen, Mahnwesen, Ausgaben, XRechnung, UStVA- und EÜR-Vorbereitung |
| **Einstellungen** | Darstellung (vier Themes hell und dunkel, Dichte „Kompakt“), Zeiten, Zielkunden, Leistungen & Preise, Recherche, Sicherung und Wiederherstellung, Offline-Modus, optionaler Login mit Rollen |
| **Bedienung** | Sechs Bereiche mit Reitern; jede Ansicht und jede Firma hat eine direkte Adresse, Zurück und Neuladen führen an dieselbe Stelle; Firmenliste mit Arbeitsansichten und eigenen gespeicherten Ansichten |

## Was SignalDesk bewusst nicht tut

- Keine automatischen E-Mails, Anrufe oder Nachrichten. Entwürfe bleiben Entwürfe.
- Kein Auslesen von LinkedIn, Google Maps oder Suchmaschinen, keine gekauften Kontaktlisten.
- Keine erfundenen Kontaktdaten: Was nicht wörtlich in der Quelle steht, bleibt leer.
- Keine Kaufwahrscheinlichkeit. Bewertungen sind nachvollziehbare Arbeitshilfen.
- Ein gefundener Kontaktweg ist **keine Werbeerlaubnis** (§ 7 UWG). Widersprüche gelten überall und überstehen jeden Import.
- Keine Steuer- oder Rechtsberatung. XRechnungen vor dem ersten Versand prüfen, UStVA-Werte vor der Übermittlung kontrollieren.

## Für Entwickler

```bash
python -m sales_tool
```

```bash
python -m unittest discover -s tests
```

- Der Kern braucht nur die Python-Standardbibliothek (3.10 bis 3.13). Zusatzpakete je Variante stehen mit Prüfsummen in `requirements-lock-*.txt`.
- Daten liegen außerhalb des Programmordners in `~/.akquise-tool/`.
- SignalDesk bindet nur `127.0.0.1`. Nicht ohne TLS-Proxy und Login öffentlich betreiben, siehe [`docs/BETRIEB_UND_TEAM.md`](docs/BETRIEB_UND_TEAM.md).
- Prüfverfahren vor jedem Commit: `.claude/skills/qa-release-gate/SKILL.md`.

## Dokumentation

| Frage | Dokument |
|---|---|
| Was ist neu? | [`CHANGELOG.md`](CHANGELOG.md) |
| Wo steht das Projekt, was fehlt? | [`docs/LAUNCH_AUDIT.md`](docs/LAUNCH_AUDIT.md), [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| Was geht nicht oder nur eingeschränkt? | [`docs/EINSCHRAENKUNGEN.md`](docs/EINSCHRAENKUNGEN.md) |
| Warum wurde etwas so entschieden? | [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) |
| Was wurde wirklich getestet? | [`docs/SELF_REVIEW_LOG.md`](docs/SELF_REVIEW_LOG.md) |
| Wie nutze ich OpenStreetMap? | [`docs/OPENSTREETMAP_LOKAL.md`](docs/OPENSTREETMAP_LOKAL.md) |
| Wie wird die Oberfläche übersichtlicher? | [`docs/UI_UX_VORSCHLAEGE.md`](docs/UI_UX_VORSCHLAEGE.md) |
| Welche Quellen sind erlaubt? | [`docs/LEADQUELLEN_V11.md`](docs/LEADQUELLEN_V11.md), [`docs/RECHTLICHES.md`](docs/RECHTLICHES.md) |
| Buchhaltung | [`docs/BUCHHALTUNG_V10.md`](docs/BUCHHALTUNG_V10.md), [`docs/GAP_ANALYSE_V10.md`](docs/GAP_ANALYSE_V10.md) |
| Bestandteile und Lizenzen | [`docs/BESTANDTEILE.md`](docs/BESTANDTEILE.md) |
| Pläne | [`docs/MASTERPLAN_SOLOSELBSTAENDIGE.md`](docs/MASTERPLAN_SOLOSELBSTAENDIGE.md), [`docs/MASTERPLAN_2_0_SCRAPLING.md`](docs/MASTERPLAN_2_0_SCRAPLING.md) |

Die Berichte der einzelnen Sprints liegen unter `docs/BERICHT_*.md`.

## Lizenz

MIT – eigener Quellcode. Ortsdaten: GeoNames (CC BY 4.0). Fremde Marken und Vorlagen sind nicht enthalten.
