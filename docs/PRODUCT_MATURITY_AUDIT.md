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
Browser-Suite lief in CI **nicht** – Befund T-1 unten; seit SDQ-005 laufen alle Browser-Tests in CI, übersprungene gelten als Fehler.

## 3. Historische Befunde, am aktuellen Code geprüft

| Befund (Audit) | Prüfung | Stand dev54 | Priorität |
|---|---|---|---|
| **B1** Navigation aus offener Firmenakte: URL zeigt neuen Bereich, Akte bleibt sichtbar | Browser-Nachstellung: Akte `#/firmen/akte/1` öffnen, in der Seitenleiste „Abrechnen“ klicken | **besteht weiter.** Adresse `#/abrechnen`, Reiter „Rechnungen“ und Seitenleiste „Abrechnen“ aktiv, sichtbar ist aber weiter die Firmenakte (`#modal` offen, `body.akte-page`). Bei ungespeicherten Eingaben erscheint keine Rückfrage. | **P0** → SDQ-002 ✓ |
| **B2** Ungespeicherter Rechnungsentwurf geht beim Verlassen verloren | Code: `formguard.js` schützt Akte-Formulare, `einstellungen.js` die Einstellungen; `accounting.js` hat keinen Eingabeschutz und kein `beforeunload`. Browser: interner Wechsel behält die Eingaben im (versteckten) Editor, Neuladen/Schließen verwirft sie ohne Warnung. | **besteht teilweise** (kein Schutz bei Neuladen/Schließen, keine Rückfrage) | **P0** → SDQ-003 ✓ |
| **B3** Zugangsdaten (IMAP/CalDAV) bei „merken“ im Klartext | `sales_tool/credentials.py`: `zugangsdaten.json` neben der Datenbank, JSON im Klartext, Dateirechte 600 (unter Windows wirkungslos) | **besteht weiter** | **P0** → SDQ-004 ✓ |
| **B4** Angebot mit Abschlagsrechnung erscheint vollständig abgerechnet | Code: `accepted_without_invoice`, `today.potential`, `proposal_rows`, `workday._steps` werteten **jede** Rechnung (auch Entwurf, auch 40-%-Abschlag) als „berechnet“ | **bestand – behoben in SDQ-001** | **P0** ✓ |
| Fehlendes gestaltetes Angebots-PDF | `sales_workspace.py` exportiert Markdown; kein PDF | **bestand – behoben in SDQ-009** (Druckseite, PDF über den Browser) | P1 ✓ |
| Keine externe KoSIT-Abnahme der XRechnung | `einvoice.py` verweist selbst auf den Validator; kein Prüfprotokoll im Repo | besteht | P1 (vor Bewerbung der Rechnungsfunktion: Gate) |
| Kein Recall-/Precision-Benchmark der Recherche | `docs/bench/` enthält Fixture-Messungen, keine unabhängige Referenzliste | besteht | P1 (Welle 2) |
| Keine Mandantentrennung | SQLite je Installation; `auth.py` ist optionaler Team-Login mit Rollen, keine Organisationen | besteht | P1 für SaaS (Welle 4), Launch-Gate |

## 4. Bestandsmatrix

| Modul | Ist-Zustand | Risiko | Nutzerwert | Nächste Änderung | Test |
|---|---|---|---|---|---|
| Navigation / Routing (`nav.js`, `app.js`, `aktepage.js`) | Hash-Router mit Bereichen; Akte als Detailseite über `#modal` | vor SDQ-002 **hoch:** URL und sichtbare Ansicht widersprachen sich (B1); behoben | hoch | SDQ-002: Seitenleiste/Reiter schließen die Akte mit Eingabeschutz | Browser-Test Akte → jeder Bereich, Zurück/Vor, Direktlink |
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
| SDQ-002 | P0 | Routing: Seitenleiste/Reiter schließen die Firmenakte; URL und sichtbare Ansicht immer gleich | – | **implementiert** |
| SDQ-003 | P0 | Eingabeschutz für Rechnungs- und Angebotseditor (Wechsel, Neuladen, Schließen) | SDQ-002 (gleiche Navigationsstelle) | **implementiert** |
| SDQ-004 | P0 | Zugangsdaten ohne Klartext: OS-Schlüsselbund optional, Migration der Altdatei, keine Geheimnisse in Logs/Exporten | – | **implementiert** |
| SDQ-005 | P1 | Volle Browser-Suite in CI | – | erledigt (2.0.0-dev56) |
| SDQ-006 | P1 | Recherche-Benchmark: Referenzliste, Messgrößen, Auswerteskript (Ergebnisse erst mit echten Prüfern) | – | Werkzeug erledigt (2.0.0-dev57), Messung offen |
| SDQ-007 | P1 | Identitätsstufen (bestätigt … keine Zuordnung) mit harten Gegenbelegen und Regressionen | SDQ-006 | Website-Zuordnung in „Finden“ erledigt (2.0.0-dev59) |
| SDQ-008 | P1 | Provider-Beschreibung je Quelle (Lizenz, Frische, Limits, Fehlerrate, Kosten) | – | erledigt (2.0.0-dev58) |
| SDQ-009 | P1 | Gestaltetes Angebots-PDF aus dem Kundenexport | – | **implementiert** (2.0.0-dev60) |
| SDQ-010 | P1 | Tabellenregister und Inventar aller SQL-Zugriffe (statt Organisationsfilter, siehe E10) | SDQ-002…004 | **implementiert** (2.0.0-dev61) |
| SDQ-011 | P1 | Mandantenverzeichnis: eine Datenbank je Organisation, Pfadregeln, Archivierung | SDQ-010 | **implementiert** (2.0.0-dev61) |
| SDQ-012 | P1 | Prozesszustand je Organisation (Offline, Anmeldesperre, Läufe, Planer) | SDQ-011 | **implementiert** (2.0.0-dev61) |
| SDQ-013 | P1 | Dateien je Organisation und Datenexport ohne Zugangsdaten | SDQ-011 | **implementiert** (2.0.0-dev61) |
| SDQ-014 | P1 | Zentrale Anmeldung: Konten, Mitgliedschaften, Rollen je Organisation | SDQ-011 | **implementiert** (2.0.0-dev62) |
| SDQ-015 | P1 | Server für mehrere Organisationen (Sitzung → genau eine Organisation) | SDQ-014 | **implementiert** (2.0.0-dev62) |
| SDQ-016 | P1 | Organisation wechseln, Abmelden, Entzug und Sperre wirken sofort | SDQ-015 | **implementiert** (2.0.0-dev62) |
| SDQ-017 | P1 | Zustand des Servers: `/healthz`, `/readyz` | SDQ-015 | **implementiert** (2.0.0-dev63) |
| SDQ-018 | P1 | Sicherung aller Organisationen, Wiederherstellungstest, Zurückspielen einer Organisation | SDQ-011 | **implementiert** (2.0.0-dev63) |
| SDQ-019 | P1 | Betriebsprotokoll (JSON-Zeilen, Anfrage-Nummer), sauberes Beenden | SDQ-015 | **implementiert** (2.0.0-dev63) |
| SDQ-020 | P1 | Serverpaket: systemd-Dienst, Sicherungs-Timer, Proxy-Beispiele, Betriebshandbuch | SDQ-017…019 | **implementiert** (2.0.0-dev63), nicht auf echtem Server erprobt |
| SDQ-021 | P1 | Zweiter Faktor (TOTP), Wiederherstellungscodes, Pflicht, Sperre über Neustarts | SDQ-014 | **implementiert** (2.0.0-dev63) |
| SDQ-022 | P1 | Verwaltungs- und Anmeldeprotokoll mit Hash-Kette | SDQ-014 | **implementiert** (2.0.0-dev63) |
| SDQ-023 | P1 | Verschlüsselter Datenexport einer Organisation | SDQ-013 | **implementiert** (2.0.0-dev63) |
| SDQ-024 | P1 | E-Rechnung gegen EN 16931/XRechnung 3.0 prüfen (Teilmenge der Regeln, kein KoSIT-Ersatz) | – | **implementiert** (2.0.0-dev64) |
| SDQ-025 | P1 | DATEV-Buchungsstapel (EXTF 700, SKR03) | – | **implementiert** (2.0.0-dev64), ohne Probeimport in DATEV |
| SDQ-026 | P2 | Ersteinrichtung: Rechnungsdaten als erster Schritt; `anlegen --admin` | – | **implementiert** (2.0.0-dev64) |
| SDQ-027 | P1 | Selbstregistrierung und Einladungen mit austauschbarem Postausgang (kein Versand) | SDQ-014 | **implementiert** (2.0.0-dev64), Versand braucht Freigabe |
| SDQ-028 | P1 | Tarif je Organisation: Testphase, nur lesen nach Ablauf, Anbieter-Schnittstelle („manuell“) | SDQ-027 | **implementiert** (2.0.0-dev64), kein Zahlungsanbieter, keine Preise |
| SDQ-029 | P1 | Referenzliste aus der ausgefüllten Tabellenvorlage (xlsx/CSV) umwandeln und prüfen | SDQ-006 | **implementiert** (2.0.0-dev65), Liste selbst offen |
| SDQ-030 | P2 | Wiederkehrende Aufträge ruhen, solange eine Organisation nur lesbar ist | SDQ-028 | **implementiert** (2.0.0-dev65) |
| SDQ-031 | P1 | Sicherungssatz an zweiten Ort kopieren; ganze Installation in leeren Ordner wiederherstellen | SDQ-018 | **implementiert** (2.0.0-dev65), nicht auf echtem Server geübt |
| SDQ-032 | P1 | Abmelden nach Leerlauf (Mehrmandanten-Betrieb, einstellbar) | SDQ-015 | **implementiert** (2.0.0-dev65) |

## 6. Launch-Gates (Stand)

| Gate | Stand |
|---|---|
| Keine offenen kritischen Sicherheitsbefunde | B3 behoben (SDQ-004); zweiter Faktor, dauerhafte Sperre und Verwaltungsprotokoll ergänzt (SDQ-021/022); externes Security Assessment fehlt – Gate bleibt **offen** |
| Kein bekannter Datenverlust in Kernfunktionen | B2 behoben (SDQ-003); Angebotseditor nur beforeunload, kein Browser-Test mit Positionen |
| Nachweisbare Mandantentrennung | **technisch nachgewiesen** (E10, SDQ-011 bis SDQ-016: eine Datenbank je Organisation, zentrale Anmeldung, Negativtests per HTTP und im Browser); **offen** bis zur externen Sicherheitsprüfung und einem Betrieb mit echten Organisationen |
| Backup und Restore geprüft | lokal ja (T15); Server: Sicherungssatz aller Organisationen mit automatischem Wiederherstellungstest und Zurückspielen je Organisation (SDQ-018), Kopie an einen zweiten Ort mit Prüfsummen und Wiederherstellung der ganzen Installation (SDQ-031), jeweils getestet; **offen** bis zu einer geübten Wiederherstellung auf einem echten Server |
| Release-Tests | Unit-Matrix, Installation, alle Browser-Tests (Mindestzahl 58, SDQ-005) und reproduzierbares Release in CI; macOS nicht |
| Recherchequalität gemessen | **offen** – Werkzeug und Format vorhanden (SDQ-006), keine geprüfte Referenzliste |
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
  Konfidenz M; Gesamtindex 47,7 → 47,8 (genau 47,66 → 47,81). Bewusst klein, weil die externe Fachprüfung fehlt.

### SDQ-002 – Bereichswechsel schließt die Firmenakte (P0, Audit B1)

- **Ausgangsproblem (nachgestellt):** Akte `#/firmen/akte/1` offen, Seitenleiste „Abrechnen“ → Adresse `#/abrechnen`, Seitenleiste und
  Reiter „Abrechnen“ aktiv, sichtbar weiter die Akte. Ursache: `switchView` wechselte die Ansicht hinter der Akte, schloss sie aber nicht.
- **Änderung (`nav.js`):** (1) Jeder Ansichtswechsel, der nicht aus der Adresse kommt (Zurück/Vor/Neuladen entscheidet `apply()`),
  schließt die Akte; ungespeicherte Eingaben bleiben wie bei bisherigen Sprüngen im Arbeitsspeicher. (2) Klicks auf Navigation
  (Seitenleiste, Hilfe, Reiter, `data-view-link`, `data-go`, Sprünge in die Einstellungen) fragen bei ungespeicherten Eingaben vorher
  über den vorhandenen Dialog: Speichern · Weiter bearbeiten (Wechsel abgebrochen, Adresse unverändert) · Verwerfen.
- **Tests:** `tests/e2e/test_sdq002_akte_navigation_browser.py` – alle sechs Bereiche, ein Bereichsreiter, Zurück/Vor, Direktlink,
  alle drei Antworten der Rückfrage mit Prüfung über die API, ob gespeichert wurde. Gegen den alten `nav.js` rot (Akte bleibt sichtbar).
- **Restrisiko:** Zurück aus einem Bereich in die Akte zeigt die Akte über dem zuletzt sichtbaren Bereich (Adresse = Akte, sichtbar = Akte;
  Seitenleiste markiert „Firmen“) – konsistent, aber die Liste dahinter ist nicht die Firmenliste. Mobile Schublade nur über den
  bestehenden Navigationstest abgedeckt.
- **Reifeauswirkung:** Dimension 4 (CRM) und 7 (UX) nannten diesen Fehler als Abzug. Vorschlag 7: 62 → 64, 4: 72 → 73 (Konfidenz M,
  ohne Nutzertest). Gesamtindex 47,8 → 48,1 (genau 47,81 → 48,06).

### SDQ-003 – Eingabeschutz im Rechnungseditor (P0, Audit B2)

- **Ausgangsproblem:** Der Rechnungseditor hatte keinen Eingabeschutz. Beim Neuladen/Schließen gingen Eingaben ohne Warnung verloren;
  Zurück/Vor auf `#/abrechnen` schaltete auf die Liste (`accShowList`) und verwarf den Editorinhalt still. Der Angebotseditor hielt
  Positionen nur im Arbeitsspeicher, ebenfalls ohne Warnung beim Neuladen.
- **Änderung:** `accounting.js` merkt den gespeicherten Stand des Editors; bei Änderungen fragen Bereichswechsel, „← Rechnungen“,
  „＋ Neue Rechnung“, das Öffnen einer anderen Rechnung und Sprünge aus „Heute“ über den vorhandenen Dialog (`formGuard.ask`).
  „Speichern“ legt einen Entwurf ab (nie Festschreibung), „Verwerfen“ lädt den gespeicherten Stand. `beforeunload` für Rechnungs- und
  Angebotseditor; `accShowList` lässt einen geänderten Entwurf offen.
- **Tests:** `tests/e2e/test_sdq003_invoice_guard_browser.py`, gegen den alten Stand rot.
- **Restrisiko:** Angebotseditor ohne Browser-Test mit echten Positionen; Formularfelder ohne Positionen zählen dort nicht als ungespeichert.
  Kein gemeinsamer Eingabeschutz für alle Formulare – drei Umsetzungen (Akte, Einstellungen, Rechnung) mit demselben Dialog.
- **Reifeauswirkung:** Abzug „ungeschützter Rechnungsentwurf“ in Dimension 6 behoben: 54 → 56; Dimension 7 (UX) 64 → 65.
  Gesamtindex 48,06 → 48,24 (≈ 48,2).

### SDQ-004 – Zugangsdaten nie im Klartext (P0, Audit B3)

- **Ausgangsproblem:** „Merken“ schrieb IMAP-/CalDAV-Passwörter als JSON im Klartext neben die Datenbank (Rechte 600 nur unter
  POSIX). Jede Kopie des Datenordners trug das Passwort mit.
- **Änderung (`credentials.py`, Schnittstelle unverändert):** Speicher-Abstraktion mit `keyring` (falls installiert), Windows-DPAPI
  (stdlib, `ctypes`), Linux-`secret-tool` (Passwort über stdin). Ohne sicheren Speicher nur Arbeitsspeicher. Je Installation eigener
  Schlüssel (Hash des Datenbankpfads). Altbestand: Übernahme + Entfernen; ohne sicheren Speicher nur lesen, Abbau bei Neu-Eingabe oder
  „vergessen“ (keine Löschung ohne Nutzerhandlung). Oberfläche nennt den Speicher und zeigt den Altbestand an.
- **Tests:** `tests/test_sdq004_credentials.py` (9, davon 1 nur Windows), `tests/e2e/test_sdq004_credentials_browser.py`;
  `test_v2_caldav.py` von „Klartext-Datei erwartet“ auf „keine Klartext-Datei“ umgestellt.
- **Nicht geprüft:** echter macOS-Schlüsselbund und echter Secret-Service-Dienst (kein Desktop in CI); DPAPI nur in der Windows-CI.
  Für SaaS braucht es ein serverseitiges Secret Management (Welle 4/5) – dieses Paket betrifft die lokale Installation.
- **Reifeauswirkung:** Dimension 9 (Sicherheit) nannte diesen Befund als Hauptabzug: 33 → 38 (Konfidenz M, ohne externe Prüfung).
  Gesamtindex 48,24 → 48,74 (≈ 48,7).

### SDQ-005 – Volle Browser-Suite in der CI (P1, Befund T-1)

- **Ausgangsproblem:** Der CI-Job `e2e` führte nur `tests/e2e/test_ui_workday.py` aus; die übrigen 50 Browser-Tests (darunter die
  Regressionstests zu SDQ-001 bis SDQ-004) liefen nur lokal. Zusätzlich überspringen sich alle Browser-Tests still, wenn Playwright
  fehlt – ein kaputter Installationsschritt hätte einen grünen Lauf ohne einen einzigen Browser-Test ergeben.
- **Änderung:** neues `tools/run_e2e.py` (führt `tests/e2e` vollständig aus, zählt gefunden/gelaufen/übersprungen/nicht bestanden).
  Der CI-Job ruft es mit `--no-skips --min-tests 52` auf: ein übersprungener Test oder weniger als 52 gefundene Tests machen den
  Lauf rot. Zeitlimit des Jobs 25 → 30 Minuten.
- **Gleich beim ersten CI-Lauf gefunden:** `test_sdq002_akte_navigation_browser` scheiterte in einem von zwei Läufen
  (Adresse „#/firmen“ bei offener Akte). Ursache war kein Testfehler, sondern ein Wettlauf in `nav.js`: `closeModal()` prüft die
  Adresse per `setTimeout(0)` und nahm „?firma“ zurück – auch wenn inzwischen eine neue Adresse (wieder eine Akte) gekommen war.
  Behoben über einen Zähler der Adresswechsel (`popstate`); Regressionstest `e2e/test_sdq005_akte_close_race_browser.py`
  stellt den Ablauf gezielt nach und ist gegen den alten Stand rot. Lokal nie aufgetreten – genau dafür braucht es die CI.
- **Zweiter CI-Lauf:** `test_sdq001_billing_state_browser` prüfte die Angebotsliste, bevor der Projektstand nachgeladen war.
  Mit Projektstand heißt der nächste Schritt dort richtigerweise „Kick-off …“ (Reihenfolge Kick-off → Abnahme → Schlussrechnung);
  der Rest bleibt unter Abrechnen und Heute sichtbar. Testfehler, kein Produktfehler: Der Test startet und nimmt das Projekt
  jetzt ab und prüft den Endstand nach dem Nachladen.
- **Dritter CI-Lauf:** `test_catalog_browser` (älterer Test) prüfte die Angebotskarte im Playbook sofort nach dem Speichern eines
  Katalogpreises. Die Karte wird im Hintergrund neu geladen (`refreshOffers`); der Adresswechsel lädt die Seite nicht neu.
  Testfehler: Der Test wartet jetzt auf den neuen Preis und prüft zusätzlich nach echtem Neuladen.
- **Folgerung:** Mehrere Browser-Tests prüften Zwischenstände, die lokal schnell genug fertig waren. Solche Stellen zeigen sich
  erst unter CI-Last; jede gefundene wird einzeln auf Ursache geprüft (Produktfehler oder Testfehler), nicht wiederholt oder
  übersprungen.
- **Tests:** lokal 52 gefunden, 52 gelaufen, 0 übersprungen, 0 nicht bestanden (Chromium 1243, Playwright 1.64.1).
  CI-Ergebnis siehe Pull Request. `--min-tests 52`.
- **Nicht abgedeckt:** Browser-Tests nur unter Linux/Chromium; kein Firefox/WebKit, kein Windows-Browserlauf.
- **Reifeauswirkung (Vorschlag, gilt erst mit grünem CI-Lauf):** Dimension 8 (Tests) 65 → 67, weil Regressionen der
  Oberfläche jetzt bei jedem Push geprüft werden. Gesamtindex 48,74 → 48,90 (≈ 48,9).

### SDQ-006 – Gerüst für den Recherche-Benchmark (P1)

- **Ausgangsproblem:** Kein Recall-/Präzisions-Benchmark. `docs/bench/` enthält nur Fixture-Messungen; ob SignalDesk die Firmen
  eines Gebiets findet und ihnen die richtige Website zuordnet, ist unbekannt (Dimension 1 und 2 nur mit Konfidenz M/N bewertet).
- **Änderung:** `sales_tool/research/benchmark.py` und `tools/research_benchmark.py` (validate, export-run, evaluate).
  Referenzformat mit Belegen, Prüfenden und Prüfdatum je Eintrag, Status aktiv/geschlossen/außerhalb und Kennzeichen
  „abschließend“. Zuordnung über `identity.decide()` ohne Website. Messgrößen: Recall, Präzision (bei offener Liste als
  Schranken), Dubletten, Website und Registernummer richtig/falsch zugeordnet, jeweils mit 95-%-Wilson-Bereich. Synthetische
  Listen tragen im Bericht den Vermerk „kein Messergebnis“. Personendaten werden abgelehnt, der Export enthält nur Firmendaten.
  Anleitung und vorgeschlagene Zielwerte: [RECHERCHE_BENCHMARK.md](RECHERCHE_BENCHMARK.md).
- **Tests:** `tests/test_sdq006_research_benchmark.py` (18 Fälle, fiktive Daten): Prüfung der Dateien, Zählung, falsche
  Website lenkt die Zuordnung nicht, Plattformseite ist keine Website, verschiedene Registernummer nie ein Treffer, nicht
  geprüfte Felder zählen nicht, Bericht und Export.
- **Nicht erledigt:** keine echte Referenzliste, keine Messung. Dafür braucht es Menschen, die 3 bis 5 Gebiete unabhängig von
  SignalDesk erfassen, möglichst doppelt geprüft.
- **Reifeauswirkung:** keine. Ein Messwerkzeug verbessert die Recherche nicht; Dimension 1 und 2 ändern sich erst mit einem
  Messergebnis. Gesamtindex bleibt 48,90 (nach SDQ-005).

### SDQ-008 – Beschreibung je Datenquelle (P1)

- **Ausgangsproblem:** Lizenz, Grenzen und Fair-Use-Regeln standen in `docs/LEADQUELLEN_V11.md` und teils auf den Quellenkarten.
  Aktualität, Kosten, Limits der Quelle selbst und vor allem **wie oft eine Quelle in der Praxis versagt** waren nirgends
  sichtbar (Praxistest 70191: Overpass mehrfach überlastet – das wusste nur, wer den Bericht kannte).
- **Änderung:** Jede Quelle (Wikidata, OpenStreetMap, GLEIF, TED, GLEIF-CSV, eigene Liste) beschreibt Lizenz, Namensnennung,
  Aktualität, Limits der Quelle, Kosten und Umgang mit Personendaten. Neu `lead_finder.provider_report()` und
  `GET /api/lead-finder/providers?days=30`: je Quelle Abfragen, erfolgreiche und fehlgeschlagene, Fehlerrate mit
  95-%-Wilson-Bereich, letzter Erfolg und letzter Fehler, Treffer je Abfrage, geprüfte und übernommene Treffer; dazu Datum des
  letzten lokalen OSM-Imports (nur Dateiname). Gemessen wird nur aus den Abfragen dieser Installation, nichts wird abgerufen.
  Die Quellenkarten unter „Einzelne Quelle gezielt abfragen“ zeigen Aktualität, Kosten und die Messwerte; Limits,
  Personendaten und letzter Fehler stehen im Tooltip.
- **Tests:** `tests/test_sdq008_providers.py` (6 Fälle: jede Quelle vollständig beschrieben, Fehlerrate, Zeitraum, laufende
  Abfrage zählt nicht in die Fehlerrate, Übernahmequote, OSM-Import ohne Pfad, Route mit Fehlerfall) und
  `tests/e2e/test_sdq008_providers_browser.py`.
- **Nicht geprüft:** Die Angaben zu Lizenz und Limits der Quellen sind Stand 2026-11 nach Dokumentation, nicht live gegen die
  Quellen geprüft; die Antwort sagt das (`live_verified: false`). Kostenpflichtige Anbieter sind nicht angebunden.
- **Reifeauswirkung (Vorschlag):** Dimension 1 (Firmenfindung) 45 → 46: Herkunft und Zuverlässigkeit jeder Quelle sind jetzt
  sichtbar und messbar; die Abdeckung selbst ist unverändert. Gesamtindex 48,90 → 49,01 (≈ 49,0).

### SDQ-007 – Website-Zuordnung: Stufen und harte Gegenbelege (P1)

- **Ausgangsproblem:** Die Website-Suche in „Finden“ (`sweep.find_website` → `_match`) kannte die Stufen „belegt“,
  „wahrscheinlich“ (Vorschlag) und keine Zuordnung, prüfte als Gegenbeleg aber nur Registernummer, Registergericht, Name und
  PLZ. Nachgestellt: „Müller Elektro GmbH“ ↔ Impressum „Müller Elektro e.K.“, „Muster Bau GmbH & Co. KG“ ↔ „Muster Bau
  Verwaltungs GmbH“, Firma in Stuttgart ↔ Impressum in Hamburg (wenn eine Seite keine PLZ hat) und „Elektro GmbH“ ↔
  „Elektro Schmidt GmbH“ wurden alle als „wahrscheinlich“ vorgeschlagen. Das widersprach dem Grundsatz in
  `research/identity.py` (Rechtsform und Ort sind harte Gegenbelege; Verwaltungs-GmbH und KG bleiben getrennt).
- **Änderung:** neue `sweep.counter_evidence()` – andere Registernummer, anderes Registergericht, anderer Name, andere
  Rechtsform (`identity.legal_family`), andere PLZ, anderer Ort (`identity.norm_city`, nur wenn die PLZ nicht ohnehin
  übereinstimmt). Jeder Gegenbeleg schließt die Zuordnung aus, auch als Vorschlag. Namensabgleich: Ein Name, der im anderen
  steckt, zählt nur noch, wenn er aus mindestens zwei Wörtern besteht. Abgelehnte Domains stehen mit Grund im Beleg
  („Gegenbeleg: domain.de: andere Rechtsform im Impressum (…)“).
- **Tests:** `tests/test_sdq007_identity_levels.py` (7 Fälle, 6 davon gegen den alten Stand rot); bestehende Tests zu
  Website-Suche und OSM-Funden unverändert grün.
- **Nicht umgesetzt:** Die Impressumsübernahme für eine vom Nutzer selbst eingetragene Website (`lead_imprint.py`) nutzt die
  Gegenbelege noch nicht. Eine Messung, wie viele Fehlzuordnungen das verhindert, steht aus (SDQ-006, Referenzliste).
- **Reifeauswirkung (Vorschlag):** Dimension 2 (Identität) 50 → 52 (Konfidenz M, ohne Messung). Gesamtindex 49,01 → 49,21.

### SDQ-009 – Gestaltetes Angebot als PDF (P1)

- **Ausgangsproblem:** Ein Angebot ließ sich nur als Markdown exportieren. Zum Versand musste man es selbst in ein Dokument
  übertragen – mit dem Risiko, dass Stand, Preise oder Umfang nicht mehr zur Freigabe passen.
- **Änderung:** neue Druckseite `/angebot/ID` (`sales_tool/offer_print.py`, `public/offer.css`) im Stil der Rechnung, die der
  Browser als PDF speichert („Angebot als PDF ↗“ im geöffneten Angebot). Sie liest ausschließlich den Kundenteil
  (`proposal_detail(customer_only=True)`); Kalkulation, Stundensätze, Puffer, Bedarfsnotizen und Freigabegrundlage können
  nicht erscheinen. Empfänger ist die Firma mit Anschrift aus der Akte, nie eine Person. Ein nicht freigegebenes oder nach der
  Freigabe geändertes Angebot trägt die Marke „ENTWURF“ und kein Unterschriftsfeld; die Versandfassung nennt Stand und
  Freigabedatum und hat ein Feld „Auftrag erteilt – Unterschrift und Firmenstempel“. Unbekannte Angebote: 404.
- **Tests:** `tests/test_sdq009_offer_print.py` (9 Fälle: Entwurf, Versandfassung, Änderung nach Freigabe, Empfänger ohne
  Person, keine internen Werte, Summen mit USt., HTML-Escaping, Route und 404) und
  `tests/e2e/test_sdq009_offer_print_browser.py` (Knopf öffnet die Seite, Entwurfsmarke, keine Abrufe nach außen);
  CI-Mindestzahl Browser-Tests 53 → 54.
- **Nicht umgesetzt:** Kein serverseitig erzeugtes PDF (das PDF entsteht im Druckdialog des Browsers); kein Logo des
  Anbieters; der Seitenumbruch ist nur mit Chromium geprüft. Keine Rückmeldung von Kunden zur Gestaltung.
- **Reifeauswirkung (Vorschlag):** Dimension 5 (Angebote) 78 → 79 (Konfidenz M): der im Audit genannte P1-Mangel ist behoben,
  die PDF-Erzeugung hängt aber am Browser. Gesamtindex 49,21 → 49,29.

### Welle 3 – Mandantenfähigkeit vorbereiten (SDQ-010 bis SDQ-013, 2.0.0-dev61)

- **Entscheidung:** eine Datenbank je Organisation (Architektur E10, Entscheidung Vasco 24.11.2026) statt `org_id` in allen
  Tabellen. Damit entfällt der im Audit geforderte „erzwungene Organisationsfilter“ im SQL: Die Grenze ist die Datei. Was
  diese Variante stattdessen verlangt – kein geteilter Prozesszustand, alle Dateien im Ordner der Organisation – ist
  umgesetzt und getestet.
- **SDQ-010 – Tabellenregister und Datenzugriffs-Inventar.** `sales_tool/data_map.py` ordnet alle 83 Tabellen ein
  (Organisation / Installation / Zugang, Personenbezug, Aufbewahrung: GoBD, fachlich, kurz). `sales_tool/sql_scan.py` liest
  alle SQL-Aufrufe aus dem Quelltext (AST, ohne Ausführung); `tools/sql_inventory.py` erzeugt `docs/DATENZUGRIFF.md`.
  Ergebnis: rund 1.300 Aufrufe in 61 Modulen, alle statisch lesbar. Tests (`tests/test_sdq010_data_map.py`, 11 Fälle) halten
  fest: jede Tabelle registriert; jede Spalte mit Personenbezug in einer als personenbezogen markierten Tabelle;
  Rechnungs- und Steuerdaten schreiben nur `accounting.py` und `einvoice.py`; Anmeldedaten nur `auth.py`, `server.py` und die
  Exportkopie; SQL-Text bleibt statisch lesbar; das Inventar-Dokument ist aktuell.
- **SDQ-011 – Mandantenverzeichnis.** `sales_tool/tenancy.py`: `Directory` legt Organisationen mit eigener, migrierter
  Datenbank in eigenem Ordner an, prüft Kennungen (kein `../`, keine Verknüpfung aus dem Verzeichnis heraus, keine
  reservierten Namen), überschreibt nie eine vorhandene Datei und archiviert statt zu löschen. Kommandozeile
  `tools/organisationen.py`.
- **SDQ-012 – Prozesszustand je Organisation.** Gefunden durch Durchsicht aller Modul-Variablen: Der Offline-Schalter galt
  für alle Datenbanken im Prozess; fünf Fehlversuche für „admin“ bei einer Organisation sperrten „admin“ bei allen; ein
  Impressum-Lauf Nr. 1 blockierte Lauf Nr. 1 jeder anderen Datenbank; der Planer für wiederkehrende Aufträge lief nur für
  die erste Datenbank. Jetzt je Datenbank getrennt; Anfragen und Auftragsschritte laufen mit gesetztem Mandanten.
  Bewusst geteilt bleiben Recherche-Technik-Schalter, Abruf-Bremsen und öffentliche Nachschlagedaten (E10).
- **SDQ-013 – Dateien und Export.** `tenancy.org_files` nennt alle Dateien einer Organisation (Datenbank, Sicherungen,
  Bildschirmfotos, Firmenkatalog, Altdatei Zugangsdaten); alle liegen im Ordner der Organisation. `export_organization`
  erzeugt eine ZIP-Datei mit konsistenter Datenbankkopie, Bildschirmfotos und Verzeichnis (Zeilen, Personenbezug,
  Aufbewahrung je Tabelle) – ohne Zugangsdaten, Sitzungen und Passwort-Hashes.
- **Tests:** `tests/test_sdq011_tenancy.py` (18 Fälle, davon 5 gegen den alten Stand rot: Offline-Schalter, wartende
  Netzschritte, Anmeldesperre, Lauf-Nummern, Planer). Drei ältere Tests warten jetzt über `sweep.join_sweep(..., db_path)`
  statt über die interne Liste, weil Suchnummern nur je Datenbank eindeutig sind.
- **Nicht umgesetzt:** Der Server bedient weiterhin eine Datenbank je Prozess; es gibt keine zentrale Anmeldung, die eine
  Person ihrer Organisation zuordnet, und keine Oberfläche für das Verzeichnis. Hilfsfunktionen für Tests
  (`wait_websites`, `wait_scans`, `report.wait_idle`) merken sich weiterhin nur die zuletzt benutzte Datenbank. Der Export ist
  unverschlüsselt. Löschen einer Organisation gibt es nicht (Aufbewahrungspflicht, braucht eine freigegebene Regel).
- **Reifeauswirkung (Vorschlag):** Dimension 10 (Mandantenfähige SaaS-Architektur) 10 → 13: Trennmodell entschieden,
  Verzeichnis und Isolation im Prozess getestet, aber kein Mehrmandanten-Betrieb. Dimension 9 (Sicherheit und Datenschutz)
  38 → 39: vollständige Einordnung personenbezogener und aufbewahrungspflichtiger Daten, Schreibgrenzen als Test,
  Datenexport ohne Geheimnisse. Gesamtindex 49,29 → 49,75.

### Welle 3, Teil 2 – Zentrale Anmeldung und Server für mehrere Organisationen (SDQ-014 bis SDQ-016, 2.0.0-dev62)

- **SDQ-014 – Zentrale Anmeldung.** `sales_tool/accounts.py`: Konten (scrypt-Hash wie bisher), Mitgliedschaften mit Rolle
  (admin, vertrieb, buchhaltung, lesen) und zentrale Sitzungen im Verzeichnis `organisationen.sqlite3`. Betritt eine Person
  eine Organisation, entsteht dort ein Benutzer **ohne eigenes Passwort** (Anmeldung nur zentral) und eine Sitzung in deren
  Datenbank; die Login-Pflicht wird dort eingeschaltet, damit die Rollenrechte immer gelten. Anmeldeseite `/anmelden`
  (`public/zentral.*`) mit Auswahl, Wechsel und Passwortänderung; Konten und Mitgliedschaften über `tools/organisationen.py`.
- **SDQ-015 – Server für mehrere Organisationen.** `python -m sales_tool.multi_server --root …`. Jede Anfrage wird nur
  weitergereicht, wenn (1) das Cookie eine aktive Organisation nennt, (2) die Sitzung in **deren** Datenbank gültig ist und
  (3) das Konto im Verzeichnis noch Mitglied ist. Sonst: Seiten → `/anmelden`, API → 401. Danach übernimmt der unveränderte
  Handler genau dieser Datenbank. Örtliche Anmeldung, Benutzerverwaltung und Login-Schalter sind in der Organisation gesperrt
  (zentral). Nebenbei behoben: Der Herkunftscheck lehnte Anfragen hinter einem TLS-Proxy (`Origin: https://…`) ab.
- **SDQ-016 – Wechsel, Abmelden, Entzug.** Wechsel beendet die Sitzung der bisherigen Organisation; Abmelden beendet zentrale
  und Organisationssitzung; Rollenänderung gilt mit der nächsten Anfrage; Entzug der Mitgliedschaft oder Sperre des Kontos
  beendet den Zugang sofort – auch wenn nur das Verzeichnis geändert wurde.
- **Tests:** `tests/test_sdq014_multi_tenant.py` (15 Fälle per HTTP: ohne Anmeldung nur Anmeldeseite, gefälschte
  Organisation im Cookie, Sitzung einer anderen Organisation, `../` als Kennung, Rollen je Organisation, Rollenänderung,
  Entzug, Entzug nur im Verzeichnis, gesperrtes Konto, archivierte Organisation, Konto ohne Mitgliedschaft, örtliche
  Anmeldung gesperrt, Abmelden und Wiederverwendung alter Sitzungen, Passwortänderung, Sperre nach Fehlversuchen, fremde
  Herkunft, unbekannter Host) und `tests/e2e/test_sdq014_multi_tenant_browser.py` (Anmelden, falsches Passwort, wählen,
  nur eigene Firmen, wechseln, abmelden). CI-Mindestzahl Browser-Tests 54 → 55.
- **Nicht umgesetzt:** Selbstregistrierung, Einladungen per E-Mail und Passwort-Zurücksetzen per E-Mail (es gibt bewusst
  keinen Mailversand ohne Freigabe; der Betreiber setzt Passwörter über die Kommandozeile). Keine Zwei-Faktor-Anmeldung, kein
  OIDC/SSO. Das Kalender-Abo (`/kalender/…`) braucht im Mehrmandanten-Betrieb eine Sitzung und ist dort für Kalender-Programme
  noch nicht nutzbar. Hintergrundaufträge einer Organisation laufen im selben Prozess (Trennung über den Mandantenkontext,
  SDQ-012), nicht in getrennten Prozessen. Keine externe Sicherheitsprüfung; kein Betrieb mit echten Organisationen.
- **Reifeauswirkung (Vorschlag):** Dimension 10 (Mandantenfähige SaaS-Architektur) 13 → 30: Mehrmandanten-Betrieb mit
  zentraler Anmeldung ist lauffähig und an den Grenzen getestet; es fehlen Abrechnung, Betrieb, Selbstregistrierung und
  Prüfung. Dimension 9 (Sicherheit und Datenschutz) 39 → 41: Zugriffsentzug wirkt sofort, Sitzungen sind an die Datenbank
  der Organisation gebunden, Proxy-Herkunftscheck korrigiert. Gesamtindex 49,75 → 51,99.

### Welle 4 – Betrieb und Sicherheit (SDQ-017 bis SDQ-023, 2.0.0-dev63)

- **SDQ-017 – Zustand.** `/healthz` (Prozess lebt) und `/readyz` (Verzeichnis beschreibbar, jede aktive Organisation lesbar
  und auf aktuellem Schema, mindestens 512 MB frei; Warnung, wenn die letzte geprüfte Sicherung älter als 26 h ist). Ohne
  Anmeldung; Einzelheiten nur bei lokalem Aufruf ohne `X-Forwarded-For`. HTTP 503, wenn nicht bereit.
- **SDQ-018 – Sicherungssatz.** `sales_tool/ops.py`, `python -m sales_tool.betreiber sichern [--verschluesselt] [--pruefen]`:
  Verzeichnis und jede Organisation (auch archivierte) als konsistente SQLite-Kopie, optional AES-256-GCM, Manifest mit
  Prüfsumme und Zeilenzahl je Tabelle, Ordner erst nach dem Manifest umbenannt. **Wiederherstellungstest**: Prüfsumme,
  Entschlüsseln, `integrity_check`, Zeilenzahlen gegen das Manifest, Migration einer Kopie. `zurueckspielen` stellt eine
  Organisation wieder her (GoBD-Schutz und Vorher-Sicherung aus `backup_restore`). Gefunden und behoben: Kopien blieben im
  WAL-Modus – Änderungen an einer Kopie landeten in einer `-wal`-Datei und gingen an der Prüfsumme vorbei.
- **SDQ-019 – Protokolle.** JSON-Zeilen je Anfrage (`rid`, Methode, Pfad mit `:id` statt Zahlen und Kennungen, Status,
  Dauer, Organisation), Rotation 10 × 10 MB, `X-Request-ID` in jeder Antwort. Keine Cookies, Abfragen, IP-Adressen,
  Inhalte (Test). `SIGTERM` beendet den Dienst sauber; belegter Port führt zu einem Fehler statt zu stillem Ausweichen.
- **SDQ-020 – Serverpaket.** `deploy/`: gehärtete systemd-Unit (`ProtectSystem=strict`, eigener Benutzer, nur Daten- und
  Protokollordner beschreibbar), täglicher Timer für Sicherung mit Prüfung, Caddy- und nginx-Beispiel, Umgebungsdatei
  ohne Geheimnisse; Betriebshandbuch `docs/BETRIEB_SERVER.md`. Ein Test löst die Units mit der Beispiel-Umgebung auf und
  prüft die Aufrufe mit den echten Parsern. Die Verwaltung liegt jetzt in `sales_tool/betreiber.py` (im Release enthalten).
- **SDQ-021 – Zweiter Faktor.** TOTP nach RFC 6238 (Standardbibliothek, Testvektoren aus dem RFC), Anmeldung in Stufen:
  ohne Code keine Organisationsliste und kein Zutritt, neues Token nach dem Code, jeder Code nur einmal, zehn
  Wiederherstellungscodes (nur Hash gespeichert, je einmal gültig). Pflicht für die Installation (`zwei-faktor-pflicht an`)
  beendet laufende Sitzungen ohne zweiten Faktor und erzwingt die Einrichtung. Abschalten nur mit Passwort und Code und nicht
  bei Pflicht; Zurücksetzen durch den Betreiber beendet alle Sitzungen. Fehlversuche (Passwort und Code) stehen im
  Verzeichnis: Die Sperre gilt auch nach einem Neustart.
- **SDQ-022 – Verwaltungsprotokoll.** `sales_tool/audit_trail.py`: Konten, Mitgliedschaften, Organisationen, Sicherungen,
  Exporte, zweiter Faktor, Anmeldungen und Fehlversuche (mit IP) mit Handelndem (`konto:…` oder `betreiber:<OS-Benutzer>`).
  Hash-Kette (SHA-256) erkennt veränderte, entfernte und fehlende erste Einträge; gleichzeitige Schreiber bleiben eine Kette
  (Test mit 12 Threads). Nur Anhängen, im Code abgesichert. Unbekannte Benutzernamen werden nicht gespeichert.
- **SDQ-023 – Verschlüsselter Export.** `export … --verschluesselt` → `.zip.sdenc` (AES-256-GCM, scrypt), Klartext nur im
  temporären Ordner; Entschlüsseln mit `backup_crypto`.
- **Tests:** `tests/test_sdq017_operations.py` (16), `tests/test_sdq021_security.py` (20), `tests/test_sdq020_deploy.py` (6),
  `tests/e2e/test_sdq021_two_factor_browser.py` (Pflicht-Einrichtung bei Telefonbreite, falscher Code, Wiederherstellungscodes,
  Anmeldung mit Code). CI-Mindestzahl Browser-Tests 55 → 56.
- **Nicht umgesetzt:** kein Betrieb auf einem echten Server, keine geübte Wiederherstellung der ganzen Installation, keine
  Kopie an einen zweiten Ort, keine Alarmierung, keine Metriken (Prometheus). Kein WebAuthn/Passkey, kein OIDC, kein
  Leerlauf-Abmelden; das TOTP-Geheimnis liegt unverschlüsselt im Verzeichnis (E11). Keine Aufbewahrungsfrist für das
  Verwaltungsprotokoll (wächst unbegrenzt). Keine externe Sicherheitsprüfung.
- **Reifeauswirkung (Vorschlag):** Dimension 11 (Betrieb und Integrationen) 23 → 34: Zustand, Protokolle, geprüfte
  Sicherung, Wiederherstellung je Organisation und Serverpaket sind vorhanden und getestet, aber nie im echten Betrieb
  gelaufen. Dimension 9 (Sicherheit und Datenschutz) 41 → 47: zweiter Faktor mit Pflicht, dauerhafte Sperre,
  manipulationssicheres Verwaltungsprotokoll, verschlüsselte Exporte und Sicherungen; ohne externe Prüfung bleibt die
  Konfidenz begrenzt. Dimension 10 (Mandantenfähige SaaS-Architektur) 30 → 32: Sicherung und Wiederherstellung je
  Organisation. Gesamtindex 51,99 → 53,49.

### Welle 5 – Rechnung, Einrichtung, Registrierung und Tarif (SDQ-024 bis SDQ-028, 2.0.0-dev64)

- **SDQ-024 – E-Rechnung prüfen.** `sales_tool/einvoice_check.py`: 63 Regeln aus EN 16931 und XRechnung 3.0 (BR-01 bis
  BR-16, Parteien BR-06 bis BR-11, BR-DE-1 bis BR-DE-26, Positionen BR-21 bis BR-27, Summen BR-CO-10 bis BR-CO-16,
  Steueraufschlüsselung je Kategorie, Codelisten, IBAN-Prüfziffer, Dezimalstellen). Route `…/xrechnung/check`, Knopf in der
  Rechnungsansicht, Ergebnis auch beim Import. Platzhalter des Generators (`unbekannt@invalid`, Telefon `-`) gelten als
  fehlend. XML mit DOCTYPE/ENTITY wird abgelehnt; CII wird als „nicht geprüft“ gemeldet, nicht als gültig. Tests: alle
  Steuerarten und Storno bestehen; verfälschte Summe, Steuer, IBAN, Platzhalter-Adresse, Währung, Rechnungsnummer fallen auf.
  **Grenze:** Teilmenge der Schematron-Regeln, kein Schema-Check (XSD), nicht gegen den KoSIT-Validator abgeglichen.
- **SDQ-025 – DATEV.** `sales_tool/datev.py`: Kopfzeile EXTF 700/21/13 mit Berater, Mandant, WJ-Beginn, Sachkontenlänge 4,
  Zeitraum, SKR 03; Kernspalten Umsatz bis Buchungstext; Windows-1252, CRLF, Dezimalkomma, Belegdatum TTMM, Belegfeld 1
  bereinigt, Texte ohne Trennzeichen. Kontierung: Debitor 10000 an 8400/8300/8195/8338/8200, Bank an Debitor, Ausgaben mit
  BU 9/8; § 13b ohne Schlüssel und markiert. Zeitraum muss in einem Wirtschaftsjahr liegen. **Grenze:** kein Probeimport in
  DATEV, keine Personenkonten je Kunde, keine Belegbilder, nur die 14 Kernspalten belegt (die übrigen Spalten des Formats fehlen).
- **SDQ-026 – Ersteinrichtung.** Schritt „Rechnungsdaten eintragen“ zuerst, nennt die fehlenden Angaben (inkl. Telefon für
  XRechnung); `betreiber anlegen … --admin KONTO` (Organisation entsteht nicht, wenn das Konto fehlt).
- **SDQ-027 – Registrierung und Einladungen.** `sales_tool/einladungen.py`, `sales_tool/mailer.py`, Oberfläche unter
  `/anmelden`. Registrierung nur bei `registrierung=offen`, zweistufig, gleiche Antwort für vorhandene Adressen, Grenzen je IP
  und Adresse; Einladungen nur durch `admin`, 7 Tage, einmalig, zurückziehbar; letzte Verwaltung bleibt. Tokens nur als Hash,
  Links nie im Protokoll. **Kein Versand:** Postausgang als Datei (E12).
- **SDQ-028 – Tarif.** `sales_tool/abrechnung.py`: Testphase (Standard 30 Tage, einstellbar), Mitgliedergrenze je Tarif,
  nach Ablauf nur lesen (402, Ansehen geht, Abmelden geht), Freischalten durch den Betreiber (`tarif`). Vom Betreiber angelegte
  Organisationen bleiben unbeschränkt. **Grenze:** kein Zahlungsanbieter, keine Preise, keine Rechnungsstellung an Kunden,
  geplante Aufträge einer abgelaufenen Organisation laufen weiter.
- **Tests:** `test_sdq024_einvoice_check.py` (10), `test_sdq025_datev.py` (5), `test_sdq027_signup.py` (10),
  `test_v2_focus.py` erweitert, `e2e/test_sdq024_invoice_check_browser.py` (Ersteinrichtung, Prüfknopf, DATEV-Download),
  `e2e/test_sdq027_signup_browser.py` (Registrierung, Bestätigung, Einladung, Annahme bei Telefonbreite). CI-Mindestzahl
  Browser-Tests 56 → 58.
- **Reifeauswirkung (Vorschlag):** Dimension 6 (Rechnung und Steuer) 56 → 62: eigene E-Rechnungen werden vor dem Versand
  geprüft, Übergabe an die Steuerberatung im DATEV-Format; beides ohne externen Abgleich (KoSIT, DATEV-Import). Dimension 7
  (UX und Onboarding) 65 → 67: Ersteinrichtung führt zu gültigen Rechnungsdaten, Registrierung und Einladung im Browser.
  Dimension 10 (Mandantenfähige SaaS-Architektur) 32 → 40: Organisationen entstehen und wachsen ohne Betreiber, Testphase
  und Tarifgrenzen greifen serverseitig; ohne E-Mail-Versand und Zahlungsanbieter ist es noch kein Self-Service-SaaS.
  Gesamtindex 53,49 → 54,91.

### Welle 6 – offene Punkte ohne Freigabe (SDQ-029 bis SDQ-032, 2.0.0-dev65)

- **SDQ-029 – Referenzliste aus der Tabelle.** `benchmark.reference_from_table` und `research_benchmark.py import-table`
  wandeln die ausgefüllte Vorlage (`referenzliste-vorlage.xlsx` oder CSV mit `;`/`,`) in das Format von SDQ-006 um und prüfen
  es. Leere Website/Registernummer = nicht geprüft, „keine“ = geprüft, gibt es nicht. Unbekannte Spalten (z. B.
  Ansprechpartner) und die Beispielzeile der Vorlage werden abgelehnt; eine fehlerhafte Liste wird nicht geschrieben.
  **Grenze:** Es gibt weiterhin keine geprüfte Liste und damit keine Messung; das Gate „Recherchequalität gemessen“ bleibt offen.
- **SDQ-030 – Planer bei „nur lesbar“.** `quality.scheduler_tick(…, paused)`: Im Server für mehrere Organisationen ruhen
  wiederkehrende Aufträge einer Organisation, deren Testphase oder Tarif abgelaufen ist (schließt die Grenze aus SDQ-028).
- **SDQ-031 – Zweiter Ort und ganze Installation.** `betreiber sicherung-kopieren NAME --nach ORDNER` kopiert über einen
  Zwischenordner, rechnet alle Prüfsummen nach und überschreibt nichts. `betreiber --root NEU gesamt-wiederherstellen SATZ --ja`
  prüft alle Prüfsummen vorab, stellt Verzeichnis und alle Organisationen (auch archivierte) in einen leeren Ordner her,
  prüft `integrity_check` und Zeilenzahlen und migriert; Passwort nur bei verschlüsselten Sätzen. Test: wiederhergestellter
  Server meldet `bereit`, Anmeldung mit dem alten Konto und Lesen der Firmen per HTTP gehen; nicht leeres Ziel und
  veränderte Datei werden abgelehnt. **Grenze:** kein Hochladen zu einem Speicheranbieter, nicht auf echtem Server geübt.
- **SDQ-032 – Abmelden nach Leerlauf.** Spalte `last_seen` an `sessions` und `account_sessions` (Migration beim Start),
  Einstellung `leerlauf_minuten` (Standard 60, 5 bis 720, 0 = aus). Eine zu lange unbenutzte Sitzung wird gelöscht, nicht
  nur abgelehnt; geschrieben wird höchstens einmal je Minute. Arbeit in einer Organisation hält die zentrale Sitzung mit
  am Leben. Einzelplatz und Team-Betrieb ohne Verzeichnis unverändert.
- **Tests:** `test_sdq029_betrieb_more.py` (17 Fälle).
- **Reifeauswirkung (Vorschlag):** Dimension 11 (Betrieb und Integrationen) 34 → 37: Wiederherstellung der ganzen
  Installation und Kopie an einen zweiten Ort sind Befehle mit Prüfung statt Handarbeit, aber weiterhin nicht im echten
  Betrieb geübt. Dimension 9 (Sicherheit und Datenschutz) 47 → 48: Leerlauf-Abmelden; ohne externe Prüfung bleibt die
  Konfidenz begrenzt. Dimension 1 bleibt bei 46, weil ohne geprüfte Liste nichts gemessen ist. Gesamtindex 54,91 → 55,19.
