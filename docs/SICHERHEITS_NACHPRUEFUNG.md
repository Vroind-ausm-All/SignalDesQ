# Unabhängige Sicherheits-Nachprüfung – Ablauf (R0.6, Paket R6.10)

Stand 2.0.0-dev67. Grundlage: externer Prüfbericht vom 24.11.2026 (geprüft auf dev64, Befunde F01–F12,
[SICHERHEITSPRUEFUNG_2026-11-24.md](SICHERHEITSPRUEFUNG_2026-11-24.md)) und der Open-Intelligence-Plan
([MASTERPLAN_OPEN_INTELLIGENCE.md](MASTERPLAN_OPEN_INTELLIGENCE.md), Abschnitt „Sicherheitsbefunde“).

Dieses Dokument legt fest, **wie** nachgeprüft wird. **Wann und durch wen** ist eine Entscheidung außerhalb des Engineerings
(E7 im Plan) und steht noch aus. Bis dahin gilt: „behoben laut Doku“ ist kein bestandener Befund.

## 1. Gegenstand der Nachprüfung

| Gegenstand | Wie er festgehalten wird |
|---|---|
| Release-Commit | Commit-Hash auf `main`, aus dem das Paket gebaut wurde |
| Artefakt | `SignalDesk-<version>.zip` aus `tools/build_release.py` (reproduzierbar, gleiche Prüfsumme bei gleichem Stand) |
| Artefakt-Digest | Inhalt von `<zip>.sha256` – der CI-Job „release“ baut zweimal und vergleicht |
| Abhängigkeiten | `requirements-lock-*.txt` mit Hashes, `sbom/signaldesk.cdx.json`; Advisory-Prüfung im CI-Job „audit“ (R0.5) |
| Abnahmetests | Gate-Tests je Befund (Matrix im Masterplan); sie laufen in jeder CI, die Planprüfung stellt sicher, dass es sie gibt |
| Betrieb | Staging-Umgebung hinter echtem TLS-Proxy (R6.4) – Voraussetzung für F05, F08, F10, F12 |

## 2. Je Befund vorzulegen

1. Commit und Artefakt-Digest des geprüften Stands.
2. Verantwortliche Rolle (Engineering, Betrieb oder Eigentümer) aus der Matrix.
3. Gate-Tests mit Ergebnis aus der CI dieses Commits (Linux und Windows).
4. Beschreibung des noch offenen Nachweises (Matrix-Spalte „Offener Nachweis“) und ob er inzwischen erbracht ist.
5. Für Befunde mit Betriebsanteil (F05, F08, F10, F12): Protokoll aus dem Staging (Netzregeln, Proxy, Lastprofil, Alarm, Restore auf leerem System).

## 3. Zusätzlich zu prüfen (neue Angriffsflächen der Intelligence Engine)

SSRF/DNS-Rebinding, HTML-/Markdown-XSS, Prompt Injection, XML-XXE, PDF-/ZIP-Bomben, Pfadmanipulation, falsche Personen-Merges,
Datenabfluss über Modelle, mandantenübergreifende Caches (Paket R6.9). Bis R2/R3 umgesetzt sind, betrifft das vor allem den
vorhandenen Abruf (`sales_tool/research/safe_urls.py`, `sales_tool/research/fetchers/http.py`) und die Importe.

## 4. Bestanden heißt

- Kein offener Befund mit Schwere „hoch“ oder „kritisch“.
- Jeder Befund gegen denselben Commit und denselben Artefakt-Digest geprüft.
- Wiederherstellung auf leerem System geübt (F12, R6.8).

Erst dann darf Paket R6.12 (geschlossene Beta) beginnen; ein öffentlicher Start (R7.5) braucht zusätzlich die übrigen Gates.

## 5. Was das Engineering vorbereitet

| Schritt | Werkzeug | Stand |
|---|---|---|
| Gate-Tests je Befund | `tests/test_sdq033_pruefbericht.py`, `tests/test_gate_isolation.py`, weitere laut Matrix | vorhanden |
| Advisory- und Geheimnisprüfung | CI-Job „audit“ (R0.5) | ab dev67 |
| Baseline mit Zählern und Laufzeiten | `tools/baseline.py` → `docs/BASELINE_<version>.md` (R0.1) | ab dev67 |
| Signiertes Release | R6.3 | offen (Schlüsselverwahrung ist Entscheidung) |
| Staging | R6.4 | offen (Betrieb) |
