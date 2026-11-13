---
name: qa-release-gate
description: Prüft vor jedem Commit oder Release von SignalDesk, ob Tests, Browser-Tests, Migration und Release-Paket wirklich gelaufen sind. Verwenden bei "Tests laufen lassen", "ist das fertig?", "Release vorbereiten", vor jedem Push und nach Schemaänderungen.
---

# QA-Release-Gate für SignalDesk

Zweck: Nichts gilt als fertig, was nicht in dieser Sitzung ausgeführt wurde. Dieser Skill enthält nur das Prüfverfahren.
Die Regeln selbst (Kontaktsperre, Belegpflicht, GoBD-Schutz) stehen im Programmcode und in den Tests.

## Eingaben
- Arbeitsverzeichnis: Wurzel des Repositories.
- Optional: geänderte Dateien (`git status --short`).

## Ablauf

1. **Regression** (ohne Zusatzpakete, wie Variante „basis“). In Umgebungen mit Proxy muss der nur lokal simulierte Host ausgenommen sein:
   ```bash
   NO_PROXY="$NO_PROXY,rebind.example" no_proxy="$no_proxy,rebind.example" python -m unittest discover -s tests
   ```
   Erwartung: `OK`. Übersprungen werden dürfen nur optionale Pakete (Playwright, Scrapling, Trafilatura).
2. **Browser-Tests** mit den festgeschriebenen Paketen:
   ```bash
   python -m venv --system-site-packages /tmp/sd-venv
   /tmp/sd-venv/bin/pip install --require-hashes -r requirements-lock-browser.txt
   /tmp/sd-venv/bin/python -m unittest discover -s tests/e2e
   ```
   Ist Chromium schon vorhanden, den Pfad in `PLAYWRIGHT_CHROMIUM_EXECUTABLE` setzen statt neu zu laden.
   „Übersprungen“ zählt nicht als bestanden.
3. **Neue Dateien der Oberfläche**: Jede neue Datei unter `sales_tool/public/` muss in der Liste der statischen Dateien in `sales_tool/server.py` stehen. Sonst liefert der Server 404, und nur der Browser-Test bemerkt es. Jede neue Ansicht (`id="view…"`) gehört in `nav.js` (Bereich und Adresse) und bekommt einen Reiter; `tests/test_v2_navigation.py` prüft das und findet Abschnitte außerhalb einer Ansicht. Farben in `style.css` nur über `var(--…)`; neue Werte gehören in die Theme-Blöcke am Dateianfang, und zwar für Hell und Dunkel (`tests/test_v2_appearance.py` prüft feste Farben und Kontraste).
4. **Schemaänderung**: `SCHEMA_VERSION` in `sales_tool/server.py` erhöhen, Spalten nur mit `ALTER TABLE … ADD COLUMN` und Vorgabewert ergänzen, einen Migrationstest gegen `tests/fixtures/migration/*.sql` schreiben.
5. **Release-Belege** nach Versions- oder Abhängigkeitsänderung:
   ```bash
   python tools/make_sbom.py
   python tools/build_release.py --out dist
   ```
   Die erste Überschrift in `CHANGELOG.md` muss mit `sales_tool.__version__` beginnen. `dist/` nicht einchecken.
   Nach einem Versionswechsel `__pycache__` leeren – veralteter Bytecode kann die alte Versionsnummer vortäuschen.
6. **Weitere Python-Versionen**: Zugesagt ist 3.10 bis 3.13. Mindestens die älteste und die neueste ausführen, z. B. `uv python install 3.10` und dann die Regression mit diesem Interpreter. Syntax, die erst ab 3.12 gilt (Backslash oder gleiches Anführungszeichen im f-String-Ausdruck), fällt sonst nicht auf.
7. **CI lesen**: Nach dem Push das Ergebnis der GitHub-Actions-Läufe abrufen, auch für Windows. „Nicht abrufbar“ ist kein Ergebnis – erneut versuchen und im Bericht nennen. Raw-Verbindungen immer mit `contextlib.closing(sqlite3.connect(...))` öffnen, sonst bleibt die Datei unter Windows gesperrt.
8. **Bericht**: Zahl der Tests, Überspringungen mit Grund, Browser-Tests, was nicht geprüft werden konnte (Windows, macOS, echte Websites).

## Ausgabe
Eine Tabelle `Prüfung | Ergebnis | Beleg` und ein Urteil `weiter / nachbessern / blockiert`.

## Sicherheitsregeln
- Testlauf und Push nie in einem Befehl verketten. Erst das Ergebnis lesen, dann committen und pushen.
- Keine Tests abschalten, überspringen oder Erwartungen lockern, um ein grünes Ergebnis zu erhalten.
- Keine echten Firmen-Websites abrufen, keine TLS-Prüfung, robots.txt-Regel oder Prüfsumme umgehen.
- Keine Nutzerdatenbank (`~/.akquise-tool/`) anfassen; Tests arbeiten in temporären Ordnern.

## Beispiel
Anfrage: „Ich habe `assessment.js` hinzugefügt, ist das fertig?“
Vorgehen: Schritt 1 grün, Schritt 2 zeigt 404 für `/assessment.js` → Urteil „nachbessern“, Datei in die Liste eintragen, Schritt 2 wiederholen.
