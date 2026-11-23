# Produktreife-Audit – technische Baseline (Welle 1)

Stand: 23.11.2026 · geprüfter Commit `d927873d605de2f00124fd9d6c5c5abf63a50109` (main, 2.0.0-dev54, PR #37) · Fortschreibung je Arbeitspaket am Ende dieses Dokuments.

Dieses Dokument ist die Vergleichsbasis für alle weiteren Arbeitspakete (SDQ-…). Es übernimmt die Gewichte und Ausgangswerte des
Audits „SignalDesQ Produktreife-Audit 0–100 und SaaS-Roadmap 2026“ (Stand dev54) unverändert und prüft die dort genannten
Befunde erneut am aktuellen Code. Werte werden nur geändert, wenn ein Arbeitspaket nachweisbar etwas verbessert hat.

## 1. Bewertungsrubrik (eingefroren)

Formel unverändert aus dem Audit: Gesamtindex = Σ (Gewicht × Feldwert) / 100. Gewichte bleiben für Vorher-Nachher-Vergleiche fest.

| # | Dimension | Gewicht | Ausgangswert (Audit dev54) | Konfidenz |
|---|---|---:|---:|---|
| 1 | Firmenfindung und Datenabdeckung | 11 % | 45 | M |
| 2 | Unternehmensidentität und Quellenbelege | 10 % | 50 | M |
| 3 | Website- und KI-Analyse | 9 % | 64 | M |
| 4 | CRM und Kontaktarbeit | 9 % | 72 | M |
| 5 | Angebote und Projekte | 8 % | 78 | M |
| 6 | Rechnung und Steuer | 5 % | 51 | M |
| 7 | UX und Onboarding | 8 % | 62 | M |
| 8 | Tests und Zuverlässigkeit | 8 % | 65 | H |
| 9 | Sicherheit und Datenschutz | 10 % | 33 | H |
| 10 | Mandantenfähige SaaS-Architektur | 12 % | 10 | H |
| 11 | Betrieb und Integrationen | 6 % | 23 | H |
| 12 | Marktvalidierung | 4 % | 16 | N |
| | **Gesamt** | 100 % | **47,7 ≈ 48** | |

Regeln für jede spätere Änderung eines Werts (Phase H):

1. Ein Wert steigt nur mit Beleg: Commit, ausgeführter Test mit Ergebnis, und bei Qualitäts- oder Nutzenaussagen eine externe Prüfung.
2. Pläne, Dokumente und Architekturentwürfe allein verändern keinen Wert.
3. Je Dimension wird getrennt festgehalten: Funktionsabdeckung, Korrektheit, Zuverlässigkeit, Bedienbarkeit, Sicherheit, Nutzennachweis, Betriebsfähigkeit.
4. Dimensionen 1–3 und 12 können ohne echte Prüfer bzw. Pilotkunden nicht über ihre Ausgangswerte hinaus „mit hoher Konfidenz“ steigen.
5. Launch-Gates (Abschnitt 6) gelten unabhängig vom Gesamtwert.

## 2. Reproduzierbare Testbasis (in dieser Sitzung ausgeführt)

| Prüfung | Umgebung | Ergebnis auf main `d927873` |
|---|---|---|
| `python -m unittest discover -s tests` | Linux, Python 3.13.18, ohne Zusatzpakete | **714 Tests OK, 4 übersprungen** (Laufzeit 230 s) |
| Browser-Tests `tests/e2e` | Chromium 1243, Playwright 1.64.1 aus `requirements-lock-browser.txt` | siehe Arbeitspaket SDQ-001 (Lauf mit Änderung) |
| Python 3.10, Windows, macOS | nicht verfügbar in dieser Umgebung | **nicht geprüft** – CI-Matrix (`.github/workflows/tests.yml`) deckt Windows/Linux × 3.10/3.13 ab |
| Echte Websites, echte Quellen | bewusst nicht ausgeführt (keine Abrufe fremder Seiten) | **nicht geprüft** |

CI: vier Jobs (unit-Matrix, install-Matrix, e2e nur `test_ui_workday.py`, reproduzierbares Release mit SBOM-Abgleich). Die volle
Browser-Suite läuft in CI **nicht** – Befund T-1 unten.

## 3. Historische Befunde, am aktuellen Code geprüft

| Befund (Audit) | Prüfung | Stand dev54 | Priorität |
|---|---|---|---|
| **B1** Navigation aus offener Firmenakte: URL zeigt neuen Bereich, Akte bleibt sichtbar | Browser-Nachstellung: Akte `#/firmen/akte/1` öffnen, in der Seitenleiste „Abrechnen“ klicken | **besteht weiter.** Adresse `#/abrechnen`, Reiter „Rechnungen“ und Seitenleiste „Abrechnen“ aktiv, sichtbar ist aber weiter die Firmenakte (`#modal` offen, `body.akte-page`). Bei ungespeicherten Eingaben erscheint keine Rückfrage. | **P0** → SDQ-002 |
| **B2** Ungespeicherter Rechnungsentwurf geht beim Verlassen verloren | Code: `formguard.js` schützt Akte-Formulare, `einstellungen.js` die Einstellungen; `accounting.js` hat keinen Eingabeschutz und kein `beforeunload`. Browser: interner Wechsel behält die Eingaben im (versteckten) Editor, Neuladen/Schließen verwirft sie ohne Warnung. | **besteht teilweise** (kein Schutz bei Neuladen/Schließen, keine Rückfrage) | **P0** → SDQ-003 |
| **B3** Zugangsdaten (IMAP/CalDAV) bei „merken“ im Klartext | `sales_tool/credentials.py`: `zugangsdaten.json` neben der Datenbank, JSON im Klartext, Dateirechte 600 (unter Windows wirkungslos) | **besteht weiter** | **P0** → SDQ-004 |
| **B4** Angebot mit Abschlagsrechnung erscheint vollständig abgerechnet | Code: `accepted_without_invoice`, `today.potential`, `proposal_rows`, `workday._steps` werteten **jede** Rechnung (auch Entwurf, auch 40-%-Abschlag) als „berechnet“ | **bestand – behoben in SDQ-001** | **P0** ✓ |
| Fehlendes gestaltetes Angebots-PDF | `sales_workspace.py` exportiert Markdown; kein PDF | besteht | P1 |
| Keine externe KoSIT-Abnahme der XRechnung | `einvoice.py` verweist selbst auf den Validator; kein Prüfprotokoll im Repo | besteht | P1 (vor Bewerbung der Rechnungsfunktion: Gate) |
| Kein Recall-/Precision-Benchmark der Recherche | `docs/bench/` enthält Fixture-Messungen, keine unabhängige Referenzliste | besteht | P1 (Welle 2) |
| Keine Mandantentrennung | SQLite je Installation; `auth.py` ist optionaler Team-Login mit Rollen, keine Organisationen | besteht | P1 für SaaS (Welle 4), Launch-Gate |

## 4. Bestandsmatrix

| Modul | Ist-Zustand | Risiko | Nutzerwert | Nächste Änderung | Test |
|---|---|---|---|---|---|
| Navigation / Routing (`nav.js`, `app.js`, `aktepage.js`) | Hash-Router mit Bereichen; Akte als Detailseite über `#modal` | **hoch:** URL und sichtbare Ansicht widersprechen sich (B1) | hoch | SDQ-002: Seitenleiste/Reiter schließen die Akte mit Eingabeschutz | Browser-Test Akte → jeder Bereich, Zurück/Vor, Direktlink |
| Eingabeschutz (`formguard.js`, `einstellungen.js`) | Akte und Einstellungen geschützt | **hoch** für Rechnungs- und Angebotseditor (B2) | hoch | SDQ-003: gemeinsamer Schutz für Rechnungs- und Angebotseditor | Browser-Test: Wechsel, Neuladen |
| Zugangsdaten (`credentials.py`) | RAM oder Klartext-JSON | **hoch** (Geheimnis auf Datenträger, auch in Kopien des Datenordners) | mittel | SDQ-004: OS-Schlüsselbund (optional), sonst nur Arbeitsspeicher; Migration alter Datei | Unit-Tests ohne Klartext-Datei |
| Abrechnung (`accounting.py`, `einvoice.py`) | GoBD-Festschreibung, Storno, Zahlungen, Mahnungen, XRechnung | mittel; Restbetrag-Fehler behoben (SDQ-001); externe Fachprüfung fehlt | mittel | KoSIT-Validierung dokumentieren; Funktion bis dahin nicht als „produktionsreif“ bewerben | 39+ Unit-Tests, SDQ-001 |
| Angebote (`sales_workspace.py`, `pricing.py`, `catalog.py`, `revisions.py`) | Katalog, Revisionen, Nachträge, Kundenexport ohne Kalkulation | niedrig | hoch | Angebots-PDF (P1) | Unit + Browser |
| CRM, Kontaktsperre (`workday.py`, `qualification.py`, `company_data.py`) | Sperre zentral (`assert_contact_allowed`), Kontaktgrund-Dokumentation | niedrig | hoch | Kurzer Weg „5 Firmen recherchieren“ messen | Unit + Browser |
| Recherche-Quellen (`lead_finder.py`, `research/fetchers`, `osm_local.py`) | GLEIF, Wikidata, TED, OSM, Website | mittel (Abdeckung unbekannt) | hoch | Provider-Beschreibung (Lizenz, Frische, Kosten) und Benchmark (Welle 2) | Fixtures; **kein Realbenchmark** |
| Identität (`research/identity.py`, `duplicates.py`, `imprint.py`) | Namens-/Domain-/Registerregeln, Website-Vorschläge mit Bestätigung | mittel (Marken-Domains, Gruppen) | hoch | Identitätsstufen + harte Gegenbelege (Welle 2) | Unit |
| Evidenz / KI (`research/evidence.py`, `ai_provider.py`, `report.py`) | Belegpflicht, Beobachtung vs. Hypothese | mittel (reale Kalibrierung fehlt) | hoch | Evidence-Gate für KI-Aussagen | Unit |
| Website-Analyse (`website_scorer.py`, `expert_review.py`) | Rubriken, Fachreview, Kalibrierung | mittel | hoch | Branchenprofile, zwei externe Prüfer | Unit + Browser |
| Hintergrundaufträge (`research/jobs.py`, `bg_jobs.py`, `imprint_batch.py`) | persistente Aufträge, Fortsetzung nach Neustart, je Domain ein Abruf | niedrig lokal; Cloud-Entkopplung fehlt | mittel | Mandantenbudgets erst mit SaaS-Datenmodell | T14-Szenarien |
| Sicherheit lokal (`server.py`, `auth.py`, `research/safe_urls.py`, `netpolicy.py`) | Bindung an 127.0.0.1, Host-Prüfung, SSRF-/robots-Schutz, optionale Rollen | niedrig lokal; für Cloud unzureichend | – | Secrets (SDQ-004), danach Auth-Abstraktion | Unit |
| Sicherung (`backup_restore.py`, `backup_crypto.py`) | geprüfte Wiederherstellung, GoBD-Schutz, optionale Verschlüsselung | niedrig | hoch | Restore-Drill für Cloud (Welle 5) | T15-Szenario |
| Release (`tools/build_release.py`, `make_sbom.py`, `install_check.py`) | reproduzierbares ZIP, SBOM, Installationsprüfung | niedrig | – | volle Browser-Suite in CI (T-1) | CI |
| SaaS / Mandanten | nicht vorhanden (SQLite, Einzelplatz) | **Launch-Blocker** | – | Datenzugriffsschicht vor Postgres (Welle 4) | fehlt |
| Abos, Zahlungen, Onboarding für SaaS | nicht vorhanden | Launch-Blocker | – | Welle 5 | fehlt |

### Kopplung, die eine SaaS-Migration riskant macht

- **Rohes SQL in fast jedem Modul** (`conn.execute(...)` in 56 Python-Dateien) ohne Repository-Schicht. Eine Mandantenspalte müsste an
  Hunderten Stellen ergänzt werden; ohne zentrale Datenzugriffsschicht ist eine vergessene Bedingung wahrscheinlich. Vor jeder
  Postgres-/Mandanten-Arbeit braucht es eine Zugriffsschicht mit erzwungenem Organisationsfilter und Negativtests.
- **Globaler Prozesszustand:** `credentials._MEMORY`, Auftrags-Threads und Einstellungen hängen am Pfad der Datenbankdatei.
- **Server und Geschäftslogik** sind in `server.py` und den `route_*`-Funktionen eng verbunden; eine Cloud-API braucht eine
  Authentifizierungs- und Mandantenprüfung vor jeder Route.
- **Dateiablage** (Sicherungen, Exporte, Zugangsdaten) liegt neben der Datenbank im Benutzerordner.

## 5. Priorisierte Arbeitspakete (abhängigkeitssortiert)

| Kennung | Prio | Titel | Abhängig von | Stand |
|---|---|---|---|---|
| SDQ-001 | P0 | Abrechnungsstand je Angebot: Teilabrechnung, Entwurf, Storno, Zahlung getrennt | – | **implementiert** (PR, siehe unten) |
| SDQ-002 | P0 | Routing: Seitenleiste/Reiter schließen die Firmenakte; URL und sichtbare Ansicht immer gleich | – | offen (Fehler reproduziert) |
| SDQ-003 | P0 | Eingabeschutz für Rechnungs- und Angebotseditor (Wechsel, Neuladen, Schließen) | SDQ-002 (gleiche Navigationsstelle) | offen |
| SDQ-004 | P0 | Zugangsdaten ohne Klartext: OS-Schlüsselbund optional, Migration der Altdatei, keine Geheimnisse in Logs/Exporten | – | offen |
| SDQ-005 | P1 | Volle Browser-Suite in CI | – | offen |
| SDQ-006 | P1 | Recherche-Benchmark: Referenzliste, Messgrößen, Auswerteskript (Ergebnisse erst mit echten Prüfern) | – | offen |
| SDQ-007 | P1 | Identitätsstufen (bestätigt … keine Zuordnung) mit harten Gegenbelegen und Regressionen | SDQ-006 | offen |
| SDQ-008 | P1 | Provider-Beschreibung je Quelle (Lizenz, Frische, Limits, Fehlerrate, Kosten) | – | offen |
| SDQ-009 | P1 | Gestaltetes Angebots-PDF aus dem Kundenexport | – | offen |
| SDQ-010 | P1 | Datenzugriffsschicht mit Organisationsfilter (Vorbereitung Mandanten) | SDQ-002…004 | offen |

## 6. Launch-Gates (Stand)

| Gate | Stand |
|---|---|
| Keine offenen kritischen Sicherheitsbefunde | **offen** (B3) |
| Kein bekannter Datenverlust in Kernfunktionen | **offen** (B2) |
| Nachweisbare Mandantentrennung | **offen** (nicht vorhanden) |
| Backup und Restore geprüft | lokal ja (T15); Cloud offen |
| Release-Tests | lokal ja; volle Browser-Suite nicht in CI |
| Recherchequalität gemessen | **offen** |
| Externe Nutzertests | **offen** |
| Produktversprechen rechtlich geprüft | **offen** |
| Freigabe Produktionsbetrieb | **offen** |

## 7. Fortschreibung je Arbeitspaket

### SDQ-001 – Abrechnungsstand je Angebot (P0)

- **Ausgangsproblem:** Ein angenommenes Angebot galt als „berechnet“, sobald irgendeine Rechnung daran hing – auch ein nicht
  festgeschriebener Entwurf oder eine Abschlagsrechnung über 40 %. In „Abrechnen → Aus Angeboten berechnen“, „Heute → Potenzial“,
  der Angebotsliste und der Firmenakte verschwand damit der Rest des Auftrags (60 %). Risiko: vergessene Schlussrechnung.
- **Änderung:** `accounting.proposal_billing()` trennt Rechnungsstand (`offen`, `entwurf`, `teilweise`, `vollstaendig`, `storniert`,
  `monatlich`) und Zahlungsstand (`keine`, `ausstehend`, `teilbezahlt`, `bezahlt`) und liefert Zielbetrag, festgeschriebenen Betrag
  und Rest. Nur festgeschriebene Rechnungen zählen; Entwürfe, Stornorechnungen und stornierte Rechnungen nicht. Vollständig ist ein
  Angebot nach einer festgeschriebenen Gesamt- oder Schlussrechnung oder wenn Abschläge den Angebotsbetrag erreichen.
  Monatliche Leistungen bleiben bei `care.py`. Die vier Anzeigen nutzen diesen Stand; Oberfläche zeigt Rest und schlägt die
  Schlussrechnung vor (statt erneut „Abschlag 40 %“). Rein lesend, kein Schemawechsel.
- **Tests:** neu `tests/test_sdq001_billing_state.py` (10 Fälle, u. a. 40/60-Fall, Entwurf, bezahlter Abschlag, Storno, zwei Abschläge,
  „schreibt nichts“) und `tests/e2e/test_sdq001_billing_state_browser.py`. `test_accounting.py` geschärft: Die Schlussrechnung als
  Entwurf lässt den Rest sichtbar, erst festgeschrieben ist das Angebot abgerechnet (vorher hielt der Test den Fehler fest).
- **Restrisiko:** Gemischte Angebote (einmalig + monatlich) werten nur den einmaligen Teil; Nachlässe in einer Schlussrechnung gelten
  als „vollständig“. Keine externe Prüfung der Buchhaltungsfunktion.
- **Reifeauswirkung:** Dimension 6 (Rechnung und Steuer) – einer von drei im Audit genannten Abzügen ist behoben. Vorschlag 51 → 54,
  Konfidenz M; Gesamtindex 47,7 → 47,9. Bewusst klein, weil die externe Fachprüfung fehlt.
