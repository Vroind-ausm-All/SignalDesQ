# Bericht Masterplan 2.0 – Sprint 2 und 3 (SignalDesk v1.16)

## Sprint 2 – Extraktion und einheitliche Belege

**Abnahme laut Plan:**
- alle Fakten in den Testseiten belegbar;
- fehlende Daten bleiben leer;
- kein erdachter Entscheider, keine erdachte Domain, kein erdachtes Telefon;
- die manuelle Prüffreigabe funktioniert.

### Belegprüfung (`sales_tool/research/evidence.py`)
- **Grundregel:** Jeder Wert braucht einen Beleg im **abgerufenen Originaltext**. Wert und Auszug müssen dort stehen, sonst wird der Wert **verworfen** und bleibt leer. Der Grund steht in den Hinweisen.
- **Erlaubte Normalisierungen:**
  - Telefon ziffernweise (+49 und 0-Vorwahl gleichwertig);
  - USt-IdNr./Registernummer ohne Leerzeichen;
  - Registergericht ohne das ergänzte „Amtsgericht“;
  - verschleierte E-Mail („info [at] …“).
- **Jeder Beleg trägt den Datenvertrag des Plans:** `source_url`, `evidence` (Auszug), `method`, `confidence: source_observed`, `review_status: unverified`, `checked_at`, `content_hash`.
- **Gilt für jede Herkunft.**
  - Regeln (Impressum) und strukturierte Daten werden jetzt geprüft.
  - KI-Befunde werden schon seit v0.3 nur mit wörtlichem Zitat übernommen (`ai_provider.validate_analysis`).

### Strukturierte Angaben (`research/extractors/structured.py`)
- **extruct** (im Plan vorgesehen) **ließ sich nicht installieren**: Die Abhängigkeit `jstyleson` baut unter Python 3.13 nicht.
- Deshalb gibt es eine eigene, kleine Implementierung ohne Fremdpakete:
  - **JSON-LD:** auch `@graph`, Typlisten und abschließende Kommata; Größenbremse 200 KB je Block; ungültige Blöcke werden übersprungen.
  - **Microdata** (`itemscope`/`itemprop`) und **OpenGraph**.
  - Vereinheitlicht auf **Organisation** (Name, Telefon, E-Mail, USt-IdNr., Adresse, Profile) und **Stellenanzeige** (Titel, Datum, Ort, Remote).
- **Im Firmen-Bericht** erscheinen sie als „Strukturierte Angaben der Website (ungeprüft)“.
  - Sie werden als **ungeprüfte Fakten** gespeichert (Quellentyp `website_strukturiert`), sodass die manuelle Prüffreigabe nötig bleibt.
  - Abweichungen zum Impressum werden markiert.
- **Die Kaufsignal-Suche** (Karriereseiten) nutzt jetzt dieselbe Implementierung, statt einer zweiten. Neu dabei: Microdata-Stellenanzeigen.

### Haupttext (`research/extractors/content.py`)
Der eingebaute Leser bevorzugt `<main>`/`<article>` und entfernt Navigation, Kopf- und Fußbereich, Seitenleisten und Cookie-Banner. Trafilatura ist per Schalter verfügbar.

| 69 Testseiten | eingebaut | Trafilatura 2.3.1 |
|---|---|---|
| Navigation entfernt | 58/58 | 58/58 |
| Fußbereich entfernt | 17/17 | 17/17 |
| Hauptüberschrift erhalten | **60/60** | 48/60 |
| Zeit | **16 ms** | 378 ms |

Deshalb bleibt „eingebaut“ die Voreinstellung (`docs/bench/v1.16-content.json`).

### Behobene Auswertungsfehler
- **PDF-Impressum:** Die PLZ wurde im Fließtext nicht erkannt.
- **One-Pager:** Das Wort „Impressum“ im Fußbereich galt als Impressum. Jetzt sind echte Merkmale nötig (§ 5, Registergericht, USt-Id).
- **Website ohne HTTPS:** Ohne angegebenes Schema kommt jetzt ein http-Rückfall – nur bei Verbindungsfehlern, **nie bei Zertifikatsfehlern**.
- **Nicht erreichbare Website:** Das wird als Verbindungsfehler gemeldet, nicht mehr als „robots.txt-Verbot“, und nicht zwischengespeichert.

### Messung (`tools/bench_fetch.py`)

| | v1.14 | v1.15 | **v1.16** |
|---|---|---|---|
| Impressum: erwartetes Verhalten | 25/33 | 31/33 | **33/33** |
| Impressumsfelder korrekt | 79.6 % | 99.0 % | **100 %** (103/103) |
| Werte mit Beleg im Originaltext | – | – | **187/187** |
| JSON-LD-Organisation erkannt | – | – | 1/1 |
| P50 / P95 Impressum | 36.8 / 102.7 ms | 8.7 / 14.9 ms | 13.8 / 24.1 ms (Belegprüfung + strukturierte Daten) |

## Sprint 3 – Persistente Recherche-Aufträge

**Abnahme laut Plan:**
- ein Neustart während eines Auftrags verliert keine Daten;
- mehrfacher Start erzeugt keine doppelten Fakten oder Leads;
- die Sitzung bricht bei 403 oder Zeitüberschreitung nicht ab.

### Auftragsverwaltung (`sales_tool/research/jobs.py`)
- **Tabellen** `research_jobs` und `research_tasks` (Schema-Version 22).
- **Zustände:**
  - Auftrag: `queued → running → done | partial | failed`, jederzeit `paused` oder `cancelled`;
  - Schritt: `queued/running/done/failed/skipped/cancelled`.
- **Je Schritt** werden gespeichert:
  - `lease_until` (Reservierung mit Heartbeat);
  - Versuchszähler mit Höchstzahl;
  - `next_attempt_at`, also eine Wartezeit 30/120/600 s statt sofort erneut;
  - eigene Fehlerliste (letzte 10) und Ergebnis.
- **Idempotent:**
  - Ein Auftragsschlüssel startet nur einmal, solange der Auftrag aktiv ist (eindeutiger Teilindex).
  - Schritt-Schlüssel sind je Auftrag eindeutig.
- **Grenzen:** höchstens **3 Worker** gleichzeitig, **je Domain ein laufender Schritt**. Abgelaufene Reservierungen blockieren nicht. Jede Datenbank hat ihre eigenen Worker.
- **Neustart:** Laufende Schritte gehen zurück in die Warteschlange, Hinweis „nach Neustart erneut eingereiht“. Der Server setzt offene Aufträge beim Start fort.
- **Steuerung:** Pausieren, Fortsetzen, Abbrechen (fachliches Aufräumen, z. B. Bericht „abgebrochen“) und „Fehlgeschlagene erneut“ (betroffene Berichte und Website-Suchen werden zurückgesetzt).
- **Endpunkte:** `GET /api/research/jobs`, `GET /api/research/jobs/{id}`, `POST /api/research/jobs/{id}/pause|resume|cancel|retry`.

### Umgestellt (alte Einstiege bleiben kompatibel)

| Ablauf | Vorher | Jetzt |
|---|---|---|
| **Sammelsuche** | ein Thread je Suche; Neustart → „abgebrochen“; Wiederholungen nur per neuem Thread | Auftrag mit einem Schritt je Quelle plus Abschluss. Die Schritte einer Suche laufen nacheinander, damit es keine Wettläufe beim Zusammenführen gibt. **Nach einem Neustart läuft sie weiter.** „Fehlgeschlagene Quellen erneut abfragen“ arbeitet über den Auftrag. Die LEI-Ergänzung liest aus der Datenbank und übersteht damit einen Neustart |
| **Website-Suche** | ein Thread, Status nur an der Firma | Auftrag mit einem Schritt je Firma; ältere „wartet“-Firmen werden übernommen |
| **Firmen-Berichte** | ein Thread für alle | Auftrag mit einem Schritt je Firma, je Website-Domain einer gleichzeitig. Berichte mit fehlgeschlagenem Schritt (z. B. 403) erscheinen als „fehlgeschlagen“ und sind erneut ausführbar; der Auftrag endet ehrlich als „teilweise fertig“ |

**Noch auf eigenen Threads** (nächste Umstellungen): Quickscan/KI-Analyse, Impressums-Stapel, Kaufsignal-Scan, Website-Scoring.

### Oberfläche
Das Feld **„Recherche-Aufträge“** steht in „Firmen finden“ (alle Arten) und in „Firmen-Berichte“ (nur Berichte). Es zeigt:
- Fortschrittsbalken und Zähler (fertig / mit Fehler / übersprungen);
- Knöpfe Pausieren, Fortsetzen, Abbrechen, Fehlgeschlagene erneut;
- Details je Firma oder Quelle: Status, Versuch, Fehlertext, „neuer Versuch in … s“.

Es aktualisiert sich automatisch, solange etwas läuft.

### Absturztest (echter Server, `kill -9`)
1. Website-Suche für 10 Firmen gestartet. Nach 3.5 s laufen 3 Schritte, 7 warten.
2. **Harter Absturz** mit SIGKILL. In der Datenbank stehen 3 als „läuft“, 7 als „wartet“.
3. Neustart über den normalen Startweg (`server.main`). Ausgabe: „Offene Recherche-Aufträge werden fortgesetzt.“
4. Ergebnis: **10/10 fertig, 0 Fehler**. Die 3 unterbrochenen Schritte wurden neu eingereiht, **je Firma genau ein Schritt**, keine Dubletten.

## Tests
- **Unit- und Integrationstests:** 344, alle grün.
  - 10 neu für Sprint 2 (`tests/test_sprintS2_extraction.py`).
  - 14 neu für Sprint 3 (`tests/test_sprintS3_jobs.py`): Ablauf, Idempotenz, Pause/Abbruch, Wartezeiten und „teilweise“, je Domain einer (auch mit echten Threads), Neustart, Bericht mit Absturz ohne Verlust und ohne Dubletten, 403 ohne Abbruch inkl. „erneut“, Sammelsuche mit Neustart und Wiederholung, Website-Suche, Endpunkte.
- **Browser-Test** (Chromium), ohne Konsolenfehler:
  - Website-Suche starten, pausieren, fortsetzen;
  - Details je Firma, Abschluss „fertig 2/2“;
  - Feld in „Firmen-Berichte“;
  - Handyansicht ohne seitliches Scrollen.
