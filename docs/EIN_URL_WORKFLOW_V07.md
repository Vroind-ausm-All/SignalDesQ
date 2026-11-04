# v0.7 – Ein-URL-Recherche für SignalDesk

## Ziel

Ohne bestehenden Lead eine Firmenwebsite eingeben; einen **prüfbaren** Bericht bekommen; erst danach optional einen CRM-Lead erstellen. Nicht mit einem bezahlten Lusha-Service verbunden.

## Pipeline

`POST /api/research` → SQLite `quick_scans` → Hintergrundjob → `website_analyzer.crawl_site(purpose=full)` (max. fünf Seiten mit robots.txt-Prüfung, Schutz gegen private IPs, same-host) → `ai_provider.analyze` (Ollama oder Regelmodus; strikte Quellenvalidierung) → `public_contacts.extract_public_contacts` (Rollen mit Namenskontext, Kontaktpunkte separat) → Gesprächsfragen → JSON-Report → Verlauf und Oberfläche.

Leads werden **nicht** bei der Analyse angelegt. Eine ausdrückliche CRM-Übernahme über `/api/research/:id/import` erzeugt oder nutzt einen Lead und überträgt Befunde in `analysis_runs/findings` sowie Ansprechpartner in `contact_research_runs/contact_candidates`; beide bleiben auf `ungeprueft`.

## Was ist Beleg, was Vermutung?

| Feld | Bedeutung |
|---|---|
| `audit.findings[*].evidence` | Tatsächliche wörtliche Passage aus exakt einer geprüften HTML-Seite |
| `audit.findings[*].observation` | Beobachtung am Text; gegebenenfalls durch KI formuliert, **manuell prüfen** |
| `audit.findings[*].hypothesis` | Vermuteter Anknüpfungspunkt für eine Agenturleistung |
| `decision_makers.people[*].job_title` | In unmittelbarer Nähe eines Namens erkannte Berufsrolle – nur Kandidat |
| `contact_channels` | Von geprüften Seiten übernommene öffentlich sichtbare Telefonnummern/E-Mail-Adressen; **keine automatische Personenzuordnung** |
| `questions` | Gesprächsvorbereitung, nicht als Tatsachenbehauptung verstehen |

Die Anwendung errät keine Kaufbereitschaft, Projektbudgets, internen Verantwortlichkeiten oder privaten Rufnummern. Eine Managerrolle sagt nichts darüber aus, ob die Person alleine entscheiden darf.

## Grenzen / Security

- Keine Login-Zugriffe, keine Suchmaschinen-Scrapes, keine LinkedIn-Automation oder Massenimports; maximal fünf überprüfte Seiten pro Scan.
- Website-eigene Inhalte sind untrusted data; LLM-Antworten werden auf Format und wortwörtliche URL/Belege validiert.
- Skriptbasierte Websites können leer bleiben, da JS deaktiviert wird. Das ist kein Beweis für einen Fehler der Unternehmenswebsite.
- SSRF-Validierung blockiert lokale/private IPs, Ports, Benutzerinfo und andere Hosts; ein DNS-Rebinding-Rest-Risiko besteht. Nur vertrauenswürdige lokale Installation, nicht öffentlich deployen.
- Es wird nur auf `127.0.0.1` gehostet und standardmäßig in `~/.akquise-tool/akquise.sqlite3` gespeichert. Bei personenbezogenen Daten Datenschutzpflichten beachten.
- Die Einwilligung / Rechtsgrundlage für den konkreten Werbekanal muss separat geprüft werden. Die App sendet keine Nachrichten.
- Der Demo-Bericht ist FIKTIV und nicht in SQLite gespeichert.

## Teststrategie

44 automatisierte Tests (einschließlich bereits bestehender). Die v0.7-Tests mocken externe Crawls und prüfen JSON-Report, echte Quellenausschnitte, Nichtzuordnung von Zentralrufnummern, CRM-Übernahme ohne Überschreiben, Sperrstatus, einmaligen Import und API. Browserinteraktionen auf realen Windows-Installationen und echtes Ollama müssen gesondert abgenommen werden.
