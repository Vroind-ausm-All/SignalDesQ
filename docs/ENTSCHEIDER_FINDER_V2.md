# Entscheider-Finder v2 – Workflow und Grenzen

## Datenfluss

1. URL-Recherche mit derselben Unternehmensdomain, höchstens 5 abrufbaren Seiten.
2. Websitebefunde und berufsbezogene Personenkandidaten (nicht automatisch als Entscheider behaupten).
3. `research_plan()` erzeugt Zielrollen nach Angebot und Unternehmensgröße, mit **nur manuellen** externen Suchlinks.
4. Im CRM Name, Position, Quellenlink und Beleg manuell prüfen.
5. `PATCH /api/contacts/{id}` dokumentiert `verification_status`, `source_excerpt`, `decision_role`, `verification_date`.
6. Kontaktkanal und Art. 6 / 14 DSGVO sowie § 7 UWG vor einer Ansprache separat prüfen.

## Rollenheuristik

- Pilot/Conversion/Marke: Marketing bzw. in kleinen Firmen Geschäftsführung.
- Portal/Prozess-App: IT/Digitalisierung oder Operations; Größe/Zuständigkeit prüfen.
- Eine passende Funktion ist **keine** bestätigte Budget- oder Entscheidungsbefugnis.

## Verifikationsstatus

- `ungeprueft`: nur Hinweis oder Kandidat
- `quelle_geprueft`: Mensch hat HTTPS-Quelle und konkreten Beleg eingetragen
- `rolle_bestaetigt`: Mensch hat berufliche Rolle anhand Belegs überprüft
- `veraltet`: Quelle oder Person ist nicht mehr aktuell

`entscheidung` wird über PATCH nur zusammen mit `rolle_bestaetigt` akzeptiert; die tatsächliche Entscheidungsbefugnis muss inhaltlich separat geprüft werden.

## Nicht enthalten

- Kein LinkedIn- oder Google-Scraping, keine Umgehung von Logins/Zugangsbeschränkungen.
- Keine automatisierte Recherche über externe Websites mittels Suchmaschinen-API, keine externe Datenanbieter-API.
- Keine unbekannten Durchwahlen und keine automatischen E-Mails oder Anrufe.
- Diese App ohne Authentifizierung **nicht** öffentlich im Netz verfügbar machen.

## Datenpflege und Datenschutz

Speichere ausschließlich berufsbezogene, erforderliche Angaben mit prüfbarer Quelle, Zweck und Aktualität. Beachte Datenschutzhinweise/Informationspflichten und Widersprüche. Gesperrte Kontakte/Leads nicht anreichern. Sichere die SQLite-Datei vor Updates. Lege Löschregeln fest und ziehe bei konkreten Kampagnen rechtlichen Rat hinzu.

## Windows-Praxistest

- Fiktiver Bericht funktioniert ohne Internet und ohne Ollama.
- Echter Websitecrawl braucht Playwright/Chromium, Internet und einen zulässigen öffentlichen Domainabruf.
- Quellenfreigaben und Datenmigration werden per Tests geprüft.
- Live-LinkedIn-Auslesen ist absichtlich nicht möglich.
