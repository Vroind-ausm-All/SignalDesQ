# Sprint-Bericht C – Firmen-Bericht mit einem Klick (v1.11)

Gemäß `docs/MASTERPLAN_V3.md`, Sprint C.

Ausgangspunkt war das Feedback: „URL-Recherche, Website-Scoring und Kaufsignale zusammenlegen in einem Bericht mit einem Klick.“ Außerdem war die URL-Recherche „ohne Funktion“.

## Warum die URL-Recherche bisher nicht funktionierte

Sie brauchte zwingend Playwright und Chromium. Fehlte das, etwa weil die Einrichtung des Crawlers beim ersten Start ohne Internet lief, brach sie mit „Playwright fehlt“ ab.

**Neu:** Ohne Browser liest SignalDesk bis zu fünf Seiten derselben Firma per HTTP. Es gelten dieselben Schutzregeln wie bei der Impressumsprüfung: robots.txt, SSRF-Schutz, Größenlimit. Der Hinweis „ohne Browser gelesen – dynamische Inhalte können fehlen“ steht dabei. Das gilt für die **URL-Recherche, die Entscheider-Recherche im Lead und die Website-Analyse**. Mit installiertem Browser ändert sich nichts.

## Was ist tatsächlich implementiert?

### Ein Auftrag, fünf Schritte (`report.py`)
Je Schritt gibt es einen eigenen Status: wartet, läuft, fertig, Fehler oder Hinweis. **Ein Fehler stoppt die anderen Schritte nicht.**

| Schritt | Was passiert | Ergebnis im Bericht |
|---|---|---|
| 1 · Impressum & Firmendaten | Impressum finden und auslesen (wie Datenprüfung) | Name, Rechtsform, Anschrift, Register, USt-IdNr., allgemeine Kontakte, Vertretung, jeweils mit Fundstelle. **„Firmendaten übernehmen“ mit einem Klick**; bestätigte Werte werden nicht überschrieben. |
| 2 · Website-Bewertung | Scorer v2, mit Browser inkl. Screenshots, sonst HTML | Teil-Scores, Belegabdeckung, Beobachtungen mit Fundstelle, Unsicherheiten, Sprung zu allen Rubriken |
| 3 · Website-Inhalte & Ansprechpartner | URL-Recherche im Regelmodus (keine KI nötig) | Bedarfshypothesen **mit Beleg**, öffentliche Kontaktwege, gelesene Seiten; **Ansprechpartner-Kandidaten** zum Übernehmen oder Verwerfen (ohne Doppelte, auch bei erneutem Bericht) |
| 4 · Karriereseite & Kaufsignale | Karriereseite und Stellenanzeigen | Signale mit Datum und Beleg |
| 5 · Verknüpfen & Pakete | Signal-Korrelation und Angebots-Matching | Hypothesen mit Gegenhinweisen und Fehlendem, Fragen fürs Erstgespräch, passende Pakete (**unverbindlich** bis zur Bedarfsklärung) |

Die Berichtsseite trennt **Fakten mit Fundstelle** (1, 3) von **Interpretationen** (4, 5). Unten stehen der nächste Schritt und die Knöpfe „An CRM übergeben“, „Angebot vorbereiten“, „Lead öffnen“ und „Dossier (.md)“.

### Ein Klick – von überall
- **Firmen-Berichte** (vorher Research Center): Website eintragen → **„Bericht erstellen“**. Ist die Firma noch kein Lead, wird sie angelegt (Phase Recherche, Rechtsstatus „unbekannt“). Sobald das Impressum gelesen ist, ersetzt der Name laut Impressum den Platzhalter.
- **Stapel:** Firmen in der Tabelle auswählen → **„Berichte erstellen“** (bis 50). Jede Zeile hat einen Knopf „Bericht“. Die Einzelschritte liegen eingeklappt unter „Einzelschritte …“.
- **Firmen finden:** **„Übernehmen & Bericht erstellen“** für die ausgewählten Treffer.
- **Lead-Dialog:** „Bericht öffnen / erstellen“.
- **Pipeline:** Die Phase „Recherche“ führt zu „Bericht erstellen“.
- „Laufende & letzte Berichte“ und die Auftragsliste zeigen den Fortschritt.

### Navigation
- „2 · Recherchieren“ enthält jetzt nur noch **Firmen-Berichte**.
- URL-Recherche, Website-Scoring und Kaufsignale liegen als **Recherche-Details** unter „Erweitert“. Sie bleiben für Einzelfälle erreichbar.

**Technik:**
- **Neue Dateien:** `report.py` und `public/report.js`.
- **Schema 19:** neue Tabelle `company_reports`, mit automatischer Sicherung vor der Migration.
- **Endpunkte:** `POST /api/reports` (Lead-IDs oder URL), `GET /api/reports`, `GET /api/reports/{id}`, `GET /api/leads/{id}/report`.
- **Wiederverwendet:** Impressumsprüfung, Scorer, URL-Recherche, Karriereseitenprüfung, Korrelation und Matching. Es gibt keine doppelte Logik.

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **247 Tests grün**, davon 8 neu in `tests/test_sprintC_report.py`. Die bisherigen Tests der URL-Recherche, Entscheider-Recherche und Website-Analyse laufen unverändert.
- **Fiktive Firma „Kesselwerk Anlagenbau GmbH“** mit Startseite, Impressum, Team, Kontakt und Karriere, alle als Attrappen:
  - **alle 5 Schritte „fertig“**;
  - Registernummer aus dem Impressum; nichts automatisch in den Lead übernommen, außer dem Platzhalter-Namen;
  - Website-Bewertung ohne Browser;
  - Ansprechpartner-Kandidaten; nach Übernahme kein Doppelter beim nächsten Bericht;
  - Stellenanzeige als Kaufsignal;
  - Pakete „unverbindlich“; Aktivität protokolliert.
- **Fehlerfall:** Die Website-Bewertung schlägt fehl, Impressum und Verknüpfung laufen trotzdem.
- **Warteschlange:** ohne Website, gesperrt, unbekannt, läuft bereits, ungültige Eingaben.
- **Bericht für URL:** Lead wird angelegt, gleiche Domain mit `www` und Slash wiederverwendet, Sperrliste.
- **Rückfall ohne Browser:** mehrere Seiten, Titel und Hinweis; sauberer Fehler, wenn nichts erreichbar ist.
- **HTTP:** Bericht für URL, Abruf, Liste, Firmendaten übernehmen (Name und Register im Lead), 404 und 400.
- **Klickdurchlauf im Browser** (Chromium, fiktive Daten), ohne Konsolenfehler:
  - URL eingeben → Bericht mit Live-Fortschritt → alle Abschnitte
  - Firmendaten übernehmen; Ansprechpartner übernehmen; an CRM übergeben (Phase „qualifiziert“)
  - Stapel „Berichte erstellen“ (Lead ohne Website mit Hinweis übersprungen)
  - Bericht aus dem Lead-Dialog; Pipeline-Aktion; Mobilansicht 390 px

## Was ist noch ungetestet?

- **Echte Firmenwebsites.** In der Entwicklungsumgebung ist kein Internet verfügbar. Die Qualität der Regelauswertung, also Ansprechpartner-Erkennung und Bedarfshinweise, zeigt sich erst an echten Seiten.
- **Laufzeit eines Berichts im echten Netz.** Geschätzt 20–60 Sekunden je Firma (mehrere Seiten mit Pausen); ein Stapel mit 50 Firmen läuft entsprechend länger im Hintergrund.

## Welche Grenzen bestehen?

- **Ohne Browser:** keine Screenshots, keine Bewertung von Gestaltung, Mobilansicht und Ladezeit, keine Inhalte, die nur per JavaScript erscheinen. Der Bericht sagt das jeweils dazu.
- **Ohne lokale KI:** Die Bedarfshinweise kommen aus festen Regeln (immer mit Beleg). Mit Ollama wären sie ausführlicher. Das KI-Studio bleibt deshalb unter „Erweitert“ und ist optional.
- **Ansprechpartner** sind Kandidaten von der Website: Funktion ist nicht gleich Befugnis, und Übernehmen ist keine Kontakterlaubnis.

## Was ist als Nächstes sinnvoll?

1. **Live-Test:** 5–10 übernommene Firmen auswählen → „Berichte erstellen“, Berichte durchklicken und Rückmeldung geben, was fehlt oder zu viel ist.
2. **Sprint D – Angebote & Preise:** Leistungskatalog nach deinen Angaben (Kunst, Text, Web- und Grafikdesign, Print, Logo, Individualsoftware, Shop-Anbindung und Webshop, Foto und Video, Werbung und SEO/GEO, KI-Chatbot, Telefon-Sprachbot, Website-Analyse). Kalkulation ab 66 €/h mit Festpreisen, Anreise und Tagespauschale, nachvollziehbar aufgeschlüsselt.
