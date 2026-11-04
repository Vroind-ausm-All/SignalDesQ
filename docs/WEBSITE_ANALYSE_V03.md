# Website- und Bedarfsanalyse – SignalDesk v0.3

## Architektur

- Backend: bestehender Python-HTTP-Server + SQLite, nur `127.0.0.1`.
- Crawling: optional installiertes Playwright mit Chromium; max. 5 Seiten **pro manuellem Klick**.
- KI: lokal per Ollama-HTTP-API (`127.0.0.1:11434/api/chat`, JSON-Schema, Standardmodell `qwen3:8b`). Kein OpenAI- oder Claude-Account nötig.
- Fallback: **Regelmodus ohne KI** mit einer bewusst einfachen, klar markierten manuellen Prüffrage.
- Persistenz: `analysis_runs` und `findings` zusätzlich zu bisherigen Tabellen; bestehende lokale SQLite-Dateien bleiben erhalten.
- Eine Analyse gleichzeitig, Hintergrund-Worker im **lokal laufenden Programm**. Nach Serverneustart werden abgebrochene Durchläufe als Fehler ausgewiesen.

## Windows: Installation und Start

PowerShell öffnen; Python 3.10+ und die entpackten Projektdateien müssen vorhanden sein.

```powershell
cd <PFAD-ZUM-ORDNER>\Akquise-Tool
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Optional KI installieren: https://ollama.com/download/windows

```powershell
ollama pull qwen3:8b
```

Programm starten:

```powershell
.\.venv\Scripts\python.exe -m sales_tool
```

Browser: http://127.0.0.1:8765

## Erstes Nutzungsszenario

1. Einen Lead mit `Firmenname` und vollständiger `https://...`-Website im CRM speichern.
2. Lead erneut öffnen → **Website- & KI-Bedarfsanalyse**.
3. **Ollama · lokale KI** auswählen, optional anderes bereits installiertes Modell eintragen; **Website analysieren** klicken.
4. Statusanzeige im Modal beobachten; Analyse erfolgt lokal, kann gerade auf CPU länger dauern.
5. Ergebnisse vor Übernahme selbst prüfen: Quelltext/Quelle öffnen, Hypothese von bestätigtem Bedarf unterscheiden.
6. Jeden Befund **Bestätigen** oder **Verwerfen**; optional explizit **Als Lead-Beobachtung übernehmen**.
7. Ist das Feld `Signal-Beobachtung` bereits befüllt, wird es **nicht überschrieben**. Prüfe den Lead dann manuell.
8. Erst im echten Kundengespräch das separate Discovery-Formular mit bestätigten Antworten füllen.

Für die Entwicklung ohne Ollama kann **Ohne KI · Regelmodus** gewählt werden. Auch hier ist Chromium notwendig; der Regelmodus erzeugt keine versteckte KI-Antwort.

## Endpoint-Übersicht

- `POST /api/leads/{id}/analysis` mit JSON `{"provider":"ollama","model":"qwen3:8b"}` oder `{"provider":"rules"}`: neue Analyse, HTTP 202.
- `GET /api/leads/{id}/analysis`: letzte 10 Durchläufe, Status (`queued|running|done|failed`), Seitenliste, Warnungen, validierte Befunde.
- `PATCH /api/findings/{id}` mit JSON `{"review_status":"freigegeben"}` oder `"verworfen"`.
- `POST /api/findings/{id}/promote` mit JSON `{}`: übernimmt nach manueller Freigabe die Beobachtung/Quellen-URL und Angebotskategorie, falls Lead bisher keine Beobachtung hat.

## Grenzen und Schutzmaßnahmen

- **Kein Marketingversand**: keine E-Mail-, DM-, LinkedIn-, Anruf- oder Auto-Follow-up-Funktion. Öffentliche Daten sind **keine Einwilligung** zur Ansprache.
- Öffentliche `http(s)`-Domains, keine IP-Literale, Loopback-, privaten oder internen Adressen, keine speziellen Ports. Zusätzlich werden Domains vor Abruf über DNS auf nicht-private Adressen geprüft.
- `robots.txt` wird vor dem Abruf geprüft; bei Verbot oder nicht verifizierbarer robots.txt wird abgebrochen. Maximal fünf Seiten, keine Logins, keine Formularabschickung, keine Fremddomain-Folgelinks, keine Downloads, blockierte Bilder und sonstige schwere Assets. Kein massenhaftes Crawling.
- **Keine vollständige SSRF-Sandbox:** DNS-Rebinding, Browser- und OS-spezifische Netzwerkumgebungen erfordern in öffentlich zugänglichen Deployments weitere Egress-Firewall/Container-Isolation. SignalDesk deshalb nur lokal und nicht für fremde Nutzer betreiben.
- JavaScript der Zielseite ist deaktiviert. Reine SPA-Websites können dadurch unvollständige Texte liefern; Analyse bricht ggf. sauber ab. **Keine vollständige visuelle Screenshot-Analyse in v0.3**.
- Die KI erhält ausschließlich aufbereitete öffentliche Seitentexte. Websiteinhalte sind als untrusted markiert. Eingebaute Quellenvalidierung verwirft Befunde, deren Textauszug/URL nicht zu den gelesenen Seiten passen. Das beweist **nicht**, dass die Interpretation zutrifft: menschliche Prüfung bleibt erforderlich.
- Keine Tatsachenbehauptung über Budget, Kaufabsicht, Conversion oder Bedarf aus alleiniger Websitebeobachtung. Websitebewertung ist keine Rechtsgrundlage für Kontakte.
- Das Programm speichert ausgewählte geprüfte Fundstellen und Seiten-URLs; keine vollständigen Websiteinhalte/Screenshots oder externen API-Schlüssel in der DB.
- Noch kein KI-Provider-Wechsler zu Cloud-APIs. Provider-Schnittstelle ist dafür vorbereitet.

## Qualitätscheck

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Die automatisierten Tests simulieren den Netzabruf und die Modellantwort; dafür brauchen sie kein Ollama und keinen Chromium-Download. Eine tatsächliche Analyse fremder öffentlicher Websites ist erst auf dem Windows-PC mit Playwright/Chromium und optional Ollama ausführbar.
