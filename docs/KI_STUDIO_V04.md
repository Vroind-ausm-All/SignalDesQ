# SignalDesk v0.4: KI-Studio und Deal-Pipeline (Windows)

## Was jetzt funktioniert

- **KI-Studio im Browser**: Ollama-Verbindungsstatus (lokal), verfügbare Modellnamen, Testtext-Analyse mit dem **Regelmodus** oder mit **Ollama**. Ergebnisse werden unmittelbar im Browser dargestellt. **Der Testtext wird nicht in der CRM-Datenbank gespeichert.**
- **Websiteanalyse mit Lead-Verknüpfung**: Unternehmen in `Leads & Signale` mit Website erfassen. Im `KI-Studio` Lead auswählen → Modus wählen → `Website prüfen`. Es läuft der bestehende konservative Playwright-Crawler (max. fünf öffentliche Seiten, robots.txt-Prüfung, keine Logins) und optional Ollama. Läufe und Befunde werden lokal in SQLite gespeichert.
- **Analyseverlauf**: alle Websiteanalysen mit Status und geprüften Quellen, KI-Hypothesen, Gesprächsfragen; Befund manuell freigeben/verwerfen, freigegebenen Befund ins CRM übernehmen. Bestehende Beobachtungen werden nicht automatisch überschrieben.
- **Deal-Pipeline**: CRM-Stufen auf einem Board verwalten. Phase und nächster Schritt sind echte, gespeicherte Daten.
- **Erstkontakt/Bedarf**: Gesprächsformulare und dokumentierte Kontaktgrundlage wie bisher. `Bedarfsbriefing als Markdown` exportiert Firmenprofil, bestätigte Kundenantworten und getrennt davon **freigegebene Hypothesen**.
- **Wiedervorlagen**: Zeigt nun auch Felder `Nächster Schritt` und `Nächster Termin` aus den Lead-Profilen, zusätzlich zu einzelnen Aufgaben.
- **Neues Einstiegsangebot**: `Website- & Anfrage-Pilot` (990–2.500 € **Preisidee**, noch nicht validiert).

## Installation

1. Python 3.10 oder neuer für Windows installieren (Häkchen *Python zu PATH hinzufügen* oder `py`-Launcher verfügbar).
2. `setup_windows.bat` ausführen: Python-Umgebung und Playwright Chromium. Internet notwendig für Setup.
3. `start_windows.bat` starten und `http://127.0.0.1:8765` im Browser öffnen. Das Fenster geöffnet lassen.
4. In der linken Navigation **KI-Studio** öffnen → `Fiktives Beispiel laden` → `Analyse starten` (Regelmodus). **Das funktioniert ohne Ollama und ohne Browser-Crawler**.
5. Für echte KI: Ollama für Windows von https://ollama.com/download/windows installieren, `ollama pull qwen3:8b` in PowerShell ausführen, KI-Studio `Verbindung prüfen` klicken, Modus `Ollama` auswählen und Beispiel erneut analysieren.
6. Für echte Websites: `Neuer Lead` → Firma und Website speichern → KI-Studio → Firma wählen → `Website prüfen`. Ergebnisse stehen im **Analyseverlauf** und im Lead-Dialog.

## Erste 20 Minuten sinnvoll nutzen

1. Demotext im **Regelmodus** analysieren und das Format verstehen: Fakten, Hypothesen und Fragen.
2. Falls Ollama installiert ist, denselben Text noch einmal analysieren und vergleichen.
3. Einen **eigenen Test-Lead** mit einer realen öffentlichen Website erfassen. Keine fingierten Daten als echte Firmenkontakte abspeichern.
4. Die Website (maximal fünf Seiten) analysieren, eine konkrete Beobachtung gegen die Quelle prüfen, freigeben und als Signal übernehmen.
5. In den Bedarfsfragen dokumentieren, welche Aspekte **noch nicht vom potenziellen Kunden bestätigt** sind. Nächsten Schritt festlegen.

## Technischer Aufbau

| Komponente | Aufgabe |
|---|---|
| `sales_tool/server.py` | REST API und lokaler Webserver (nur 127.0.0.1) |
| `sales_tool/ai_lab.py` | `/api/ai/health`, `/api/ai/preview`, exportierbares Briefing |
| `sales_tool/ai_provider.py` | Konservativer Regelmodus oder lokale Ollama-Chat-API samt Quellenvalidierung |
| `sales_tool/website_analyzer.py` | Playwright-Websiteabruf mit URL-/robots.txt-Prüfungen |
| `sales_tool/analysis_jobs.py` | Hintergrundaufträge und SQLite-Protokolle |
| `sales_tool/model.py` | SQLite, Prioritätsscore, Migrationsschema |
| `sales_tool/public/*` | Responsive Weboberfläche: Navigation, Labor, Pipeline, Ergebnisdarstellung |

## API-Schnittstellen

- `GET /api/ai/health` → lokale Ollama-Erreichbarkeit / installierte Modellnamen
- `POST /api/ai/preview` → `{"text":"mindestens 80 Zeichen", "provider":"rules|ollama", "model":"qwen3:8b"}`; Ergebnis **nicht gespeichert**.
- `GET /api/analyses` → bis zu 40 letzte Websiteprüfungen inklusive Befunde
- `POST /api/leads/{id}/analysis` → bestehende Websiteanalyse starten (HTTP 202)
- `GET /api/leads/{id}/analysis` → alle Läufe für einen Lead
- `PATCH /api/findings/{id}` → manuelle Freigabe/Ablehnung
- `POST /api/findings/{id}/promote` → freigegebenen Befund manuell übernehmen (ohne bestehende Signale zu überschreiben)
- `GET /api/leads/{id}/brief` → exportierbares Markdown-Briefing

## Wichtige Grenzen

- **Noch keine öffentliche gehostete Website**: die Web-App ist lokal auf deinem PC erreichbar. Für Hosting außerhalb deines Rechners fehlen Authentifizierung, TLS, Nutzer-/Rollenrechte, Backupkonzept, Serverhärtung und Datenschutzprüfung.
- **Ollama ist optional**: Wenn der Dienst nicht läuft, bleibt der Regelmodus verfügbar. Auf Windows mit 32 GB RAM lohnt das Testen von Qwen3 8B; die Geschwindigkeit hängt vor allem von GPU/VRAM ab.
- **Der Regelmodus ist keine KI** und prüft keine echten technischen Defekte. Er erkennt nur ausdrücklich genannte Themen (PDF, Kontaktformular, manuelle Abläufe, Bewerbungen, Produktinformationen). Fehlt ein Hinweis, wird keine negative Schlussfolgerung gezogen.
- **Der Testtext gehört nicht zu einer überprüften Website**. Die Belege darin stammen ausschließlich aus dem manuell eingefügten Text und beweisen keinen tatsächlichen Online-Auftritt.
- **KI-Irrtümer bleiben möglich**: Quellenvalidierung verhindert nicht jede falsche Interpretation. Vor Übernahme immer Quelle selbst überprüfen.
- **Kein automatischer Nachrichtenversand**. Kontaktgrundlage und Wettbewerbs-/UWG-/DSGVO-Prüfung bleiben beim Menschen. Keine gekauften Kontaktlisten.
- **Website-Recherche kann blockiert werden** (robots.txt, Captchas, Netzwerkeinstellungen, fehlender Browser). Die Fehler erscheinen im Verlauf. Keine Umgehung von Zugriffsbeschränkungen.
- **Ungetestete Kombination mit realem Ollama unter Windows**: lokale API-Tests wurden in isolierter Umgebung durchgeführt; Windows + GPU + öffentlicher Website-Abruf müssen auf dem Zielrechner validiert werden.

## Daten und Backup

SQLite liegt standardmäßig in `%USERPROFILE%\.akquise-tool\akquise.sqlite3`. Die Datenbank aus v0.3 wird beim Start nicht destruktiv migriert. **Vor dem Wechsel ein Backup der Datei erstellen und SignalDesk dabei beenden.** Keine Datenbankdateien, `.env` oder Kontaktdaten in GitHub hochladen.

## Qualitätssicherung v0.4

- Automatisierte Prüfungen: API, manuelle Textanalyse, Offline-Modus, Lead-Daten, Quellenbelege, Freigaben und Briefingexport.
- Statische Browserressourcen und HTTP-Endpunkte wurden lokal abgerufen; JavaScript wurde mit `node --check` geprüft.
- **Nicht verifiziert in dieser Umgebung:** kompletter End-to-End-Klicktest im echten Browser (die Testumgebung sperrt Browser-Navigation per Administratorrichtlinie), externe Website-Crawls und ein tatsächlich laufendes Ollama auf dem Windows-Zielsystem.
