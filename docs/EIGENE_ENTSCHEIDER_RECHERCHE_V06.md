# SignalDesk 0.6: Eigenständige B2B-Entscheider-Recherche

## Ziel und ehrliche Grenzen

Das Tool ersetzt den **Workflow** einer Kontaktdatenplattform, nicht ihren proprietären Datenbestand. Es recherchiert aus öffentlich zugänglichen Unternehmensseiten. Unveröffentlichte persönliche Telefonnummern lassen sich nicht zuverlässig und rechtmäßig aus einer Firmendomain rekonstruieren. Die Quellenlage ist besonders bei KMU lückenhaft.

## Datenquellen und Verarbeitungsweg

1. Im Lead eine HTTPS-Unternehmenswebsite erfassen.
2. Bei manueller Bestätigung startet ein lokaler Hintergrundjob (`public_contacts.py`).
3. `website_analyzer.crawl_site(..., purpose="contacts")` beschränkt sich auf dieselbe Domain, bis zu fünf öffentlich erreichbare Seiten, prüft robots.txt und schließt interne Ziele aus. Dynamische Loginseiten, externe Profile und Social-Media-Scraping sind ausgeschlossen.
4. Die regelbasierte Textanalyse sucht nur **Namen mit unmittelbarer Berufsbezeichnung** (z. B. Geschäftsführung, Marketing-/IT-Leitung). Das sind **Kandidaten**, keine gesichert budgetverantwortlichen Entscheider.
5. Allgemeine Firmenrufnummern und E-Mail-Adressen erscheinen getrennt von Personen. Ein Telefonkontakt ist nur personengebunden, wenn ein eindeutiger Name und „Durchwahl“/„Direktwahl“ in unmittelbarer und eindeutiger Verbindung veröffentlicht sind.
6. Die Weboberfläche zeigt originale URL, Textbeleg, Prüfschritt und mögliche Rollenpriorität. Der Benutzer prüft und gibt die Übernahme ins CRM frei.
7. SQLite speichert `contact_research_runs`, `contact_candidates` und freigegebene `decision_contacts`. Lead-Löschung entfernt die Recherchekandidaten ebenfalls.

### REST-Endpunkte

- `GET /api/leads/{id}/contact-research` zeigt die letzten 10 Recherchen.
- `POST /api/leads/{id}/contact-research` mit `{"confirm_public_research":true}` startet Recherche nach Bestätigung (HTTP 202).
- `POST /api/contact-candidates/{id}/review` mit `{"decision":"accept"}` oder `{"decision":"reject"}` übernimmt bzw. verwirft einen Kandidaten einmalig.
- Die ehemaligen Lusha-Endpunkte liefern HTTP 410 und führen keinerlei Drittanbieter-Anfragen aus.

## Datenschutz und Akquise-Recht

Ein beruflicher Name, eine persönlich zugeordnete geschäftliche E-Mail oder Durchwahl sind personenbezogene Daten. Eine öffentliche Quelle allein macht deren Verarbeitung nicht automatisch zulässig. Es braucht einen tragfähigen Zweck und eine geprüfte Rechtsgrundlage (etwa Art. 6 Abs. 1 lit. f DSGVO nach dokumentierter Interessenabwägung), gegebenenfalls Informationspflichten nach Art. 14 DSGVO und die Möglichkeit zur Auskunft, Berichtigung, Löschung und zum Widerspruch (Art. 21 DSGVO). Selbst gespeicherte Daten können veralten: Quelle und Prüftag sollten daher regelmäßig aktualisiert werden.

Die Zulässigkeit einer Werbe-E-Mail oder eines B2B-Telefonanrufs richtet sich **zusätzlich** nach § 7 UWG. Ein Telefonfund oder ein passender Berufstitel begründet keine mutmaßliche Einwilligung. Die App verschickt keine Nachrichten und führt keine Anrufe aus. Ein Datenschutzprozess für einen eventuellen öffentlichen Mehrnutzerbetrieb ist ausdrücklich nicht enthalten.

Rechtsquellen:
- https://www.gesetze-im-internet.de/uwg_2004/__7.html
- https://dsgvo-gesetz.de/art-6-dsgvo/
- https://dsgvo-gesetz.de/art-14-dsgvo/
- https://dsgvo-gesetz.de/art-21-dsgvo/

## Fehlerszenarien

- Seite blockiert robots.txt: keine automatische Umgehung; Status „failed“.
- JS-basierte Teamseite: möglicherweise keine Treffer, weil Skripte im konservativen Browsermodus deaktiviert sind.
- Nur Firmenzentrale: wird als Firmenkontakt angezeigt, nicht als Durchwahl eines Managers.
- Rolle nicht erkannt oder fremder Quellenhost: Kandidat fehlt oder wird nicht übernommen.
- Keine Playwright-/Chromium-Installation: Setup-Befehl wird in der Fehlermeldung angezeigt.
- Große CRM-Datenmengen, massenhaftes Crawling oder Mehrnutzerbetrieb: nicht vom MVP gedeckt.

## Qualitätsprüfung vor echtem Einsatz

Mit 10 Websites beginnen und kontrollieren: richtiger Name, aktuelle Funktion, Quelle, korrektes Unternehmen, keine Telefon-Fehlzuordnung, ob die Rolle fachlich passt und ob die Person aus Datenschutzsicht gespeichert werden darf. Erst danach den Rechercheumfang weiterentwickeln.
