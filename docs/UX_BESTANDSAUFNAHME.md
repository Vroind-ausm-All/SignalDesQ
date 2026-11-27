# UX-Bestandsaufnahme und Funktionsmatrix (UX-Programm, Phase U1)

Stand 2.0.0-dev72, 26.11.2026. Grundlage: Auftrag „Product Design & UX Architecture 2.0“ (Phasen 1–10) und der Code auf `main`.
Alle Zahlen unten sind aus dem Repository gezählt bzw. gemessen; Bewertungen sind als solche gekennzeichnet.
Der im Auftrag genannte **separate Explorer-Designprompt liegt nicht vor** – visuelle Vorgaben stammen daher nur aus Phase 2 des Auftrags.

## 1. Architektur in Zahlen

| Bereich | Befund (gezählt) | Bedeutung für das UX-Programm |
|---|---|---|
| Frontend | Ein `index.html` (152 KB) mit 24 Ansichten (`id="view…"`), 46 Skriptdateien ohne Build-Schritt und ohne Framework, ein `style.css` (145 KB) | Umbau schrittweise in den vorhandenen Dateien; kein Framework-Wechsel (Auftrag: bestehende Komponenten bevorzugen) |
| Designsystem | Farb-Tokens als CSS-Variablen (`--bg`, `--ink`, `--accent` …), 4 Themes × Hell/Dunkel/System, 2 Dichten, Baukasten-Maße (`--s1…--s6`, `--row`) seit dev49 | Tragfähige Grundlage – neue Themes setzen nur Tokens |
| Typografie | Grundschrift Systemschrift 14 px; im CSS 136× 12 px, 96× 11 px, 70× 13 px, 47× ≤ 10 px | Phase 2 verlangt 13/16 px: Kleinstgrößen ≤ 10 px sind ein Barrierefreiheitsrisiko |
| Formen | `border-radius` in 9 verschiedenen Werten (7–12 px, 40 px), 22 Schatten, 3 Animationen, keine Verläufe, kein `backdrop-filter` | Vorgabe 6 px und „keine übermäßigen Schatten“ ist über Tokens nur teilweise erreichbar (Altwerte direkt im CSS) |
| Navigation | 6 Bereiche mit Reitern (`nav.js`), jede Ansicht mit Adresse, Strg+K-Suche (`search.js`), mobile Schublade bis 900 px | Einklappen auf dem Desktop fehlt |
| Schnittstellen | 214 unterschiedliche `/api/…`-Pfade | Ansichten können auf vorhandene Endpunkte aufsetzen |
| Personalisierung | Darstellung und Arbeitsansichten liegen in `app_settings` **je Installation**, nicht je Nutzer (`appearance.py`, `focus.py::lead_views`) | Phase 5 verlangt Nutzer- bzw. Workspace-Kontext |
| Große Datenmengen | `GET /api/leads` liefert alle Firmen ohne Seiten; Sichtung hat Seiten (50) und Server-Filter | Phase 9: Pagination/Virtualisierung für die Firmenliste fehlt |
| Tests | 119 Unit-Testdateien, 60 Browser-Tests; Kontrast- und Farbtest `test_v2_appearance.py`; Maße 1280 × 720 / 390 × 844 in den UI-Tests | Visuelle Regressionstests (Bildvergleich) fehlen |
| Barrierefreiheit | 158 `aria-`/`role`-Attribute in `index.html`, Fokus-Rückgabe und Tastatur in Akte/Strg+K getestet | WCAG 2.2 AA nicht systematisch geprüft (kein Prüfwerkzeug in der CI) |

## 2. Funktionsmatrix der Zielansichten

**vorhanden** = Funktion im Code und getestet · **teilweise** = Teile vorhanden, Lücke benannt · **fehlt** = keine Umsetzung.

| # | Zielansicht | Stand | Was es heute gibt (Datei) | Lücke laut Auftrag |
|---|---|---|---|---|
| 1 | Company Explorer | teilweise | Firmenliste mit Arbeitsansichten, Filterchips, Spalten (`leadlist.js`, `focus.py`), Sichtung der Treffer mit Seiten und Server-Filtern (`sweep.js`), Firmenkatalog-Suche (`catalog.py`) | Spaltenwahl/-breite/-fixierung, Zeilenhöhe je Tabelle, Gruppierung, Detailpanel rechts, Seiten für die Firmenliste |
| 2 | Contact Explorer | fehlt (Daten vorhanden) | Kontakte je Firma (`decision_contacts`), Kandidaten-Sichtung getrennt vom CRM (R2, `candidates.py`) | eigene Ansicht über alle Firmen, Filter nach Rolle/Prüfstatus |
| 3 | Research Workspace | teilweise | Recherche & Berichte, URL-Recherche, Firmen-Bericht mit Kurzfazit (`center.js`, `report.js`), Recherchemodi Quick/Deep/Org (R1.4) | Fortschritt/Teilfehler je Firma in einer Arbeitsfläche, Fortsetzen/Abbrechen an einer Stelle |
| 4 | Signal Intelligence | teilweise | Kaufsignale, Karriereseiten-Scan, Hypothesen (`signals.js`, `buying_signals.py`) | Signalrelevanz als eigene, erklärte Dimension; Änderungsmonitoring über Zeit |
| 5 | Smart Search | teilweise | Strg+K-Suche über Firma, Chance, Angebot, Rechnung (`search.js`); Suchprofile mit Budget (Neue Suche) | natürlichsprachliche Suche → sichtbare, editierbare Filter |
| 6 | Watchlists / Listen | teilweise | gespeicherte Arbeitsansichten der Firmenliste (M09) | geteilte Listen, persönliche Listen je Nutzer, Listen über Ansichten hinweg |
| 7 | Outreach Workspace | teilweise | Heute → Kontakt & Termine, Nachrichtenvorlagen mit Platzhaltern, IMAP-Entwürfe ohne Versand, Kontaktsperre (`workspace.js`, `messages.js`, `imap_drafts.py`) | durchgehender Ablauf „Prüfung des Kontaktwegs → Kontaktaufnahme“ in einer Ansicht |
| 8 | Call Workspace | teilweise | Anrufprotokoll, Rückruf mit Versuchen und Kanalwechsel (T06), Gesprächsnotiz (`workday.py`) | Anrufliste mit Gesprächsleitfaden und Ergebnis in einer Arbeitsfläche |
| 9 | Geo Explorer | teilweise | Umkreis-/PLZ-Suche, lokaler OSM-Auszug mit Koordinaten (`osm_local.py`, `area.py`) | Kartenansicht – **Achtung:** Kartenkacheln wären Abrufe nach außen; nur mit lokalen/lizenzierten Kacheln oder Offline-Rendering |
| 10 | Company Compare | fehlt | – | Vergleich 2–4 Firmen nebeneinander |
| 11 | Data & Source Intelligence | teilweise | Source Registry als Sperre (R1.1), Quellen-Check, Belegabdeckung, Datenpflege, Datenzugriffs-Inventar (`sources.js`, `quality.js`) | Metadaten je Feld (Lizenz, Ereignisdatum, Widersprüche, manuelle Änderungen) sichtbar; Nutzungsrechte ausdrücklich gekennzeichnet |
| 12 | Analytics | teilweise | Angebote → Auswertung, Abrechnen → Auswertung, Pipeline-Statistik, „Was du lernst“, Stichprobe | Recherche-Kennzahlen (Präzision, Kosten je geprüftem Kontakt, Plan R5.5) |
| 13 | Administration | teilweise | Einstellungen mit Abschnitten; Server für mehrere Organisationen mit Konten, Rollen, Einladungen, Protokoll (`zentral.html`, `accounts.py`) | Benutzer- und Workspace-Verwaltung in der Hauptanwendung; Einstellungen je Nutzer |

**Application Shell (Phase 3):** globale Suche + Strg+K **vorhanden**; Aufträge-Übersicht **vorhanden** (`jobs.js`), Benachrichtigungen **fehlen**;
einklappbare Hauptnavigation auf dem Desktop **fehlt**; Filter-Seitenleiste **fehlt**; rechtes Detailpanel **fehlt**.

**Sales Intelligence (Phase 6):** Zielkunden-Fit (Passung A/B/C, `qualification.py`) **vorhanden**; Signalrelevanz **teilweise**;
Datenqualität (Belegabdeckung) **teilweise**; Kontaktierbarkeit (Kontaktsperre, Rechtsstatus) **vorhanden**, aber nicht als eine Dimension
dargestellt. Trennung Fakt / Beobachtung / Hypothese / bestätigter Bedarf ist im Firmen-Bericht und in der Akte umgesetzt (dev13, dev19, dev66).

## 3. Konflikte mit bestehenden Entscheidungen

| Vorgabe aus dem Auftrag | Bestehende Entscheidung | Vorschlag |
|---|---|---|
| 13 Arbeitsansichten | ROADMAP-Regel: Zahl der Menüpunkte nicht unkontrolliert erhöhen; Masterplan: „keine neue Hauptnavigation ohne Nutzertest“ | Die 13 Ansichten als **Reiter in den sechs Bereichen** (Zuordnung unten); neue Hauptpunkte erst nach Pilot-Test (R5.2) |
| Rechtes Detailpanel 472 px | M07 Variante B (dev40, Eigentümer): Firmenakte als eigene Seite | Panel als **Schnellansicht** neben Listen (Kernfakten, Lücken, nächster Schritt); die Akte bleibt die Vollansicht |
| Darstellung je Nutzer | Darstellung je Installation (dev11) | Im Einzelplatz bleibt es je Installation; im Team/Mehrmandanten-Betrieb je Konto – braucht Datenmodell (Phase U5) |
| Schrift Geist / JetBrains Mono | keine Downloads zur Laufzeit, kein CDN | Schriftdateien **im Repository** mit Prüfsumme und Lizenz (OFL-1.1), über die eigene Auslieferung |
| Kartenansicht | kein ungeprüfter Abruf nach außen (Regel 7) | Karte erst mit Quellen-Freigabe in der Source Registry (R1.1) und Lizenzprüfung der Kacheln |

**Zuordnung der Zielansichten zu den sechs Bereichen:** Finden = Company Explorer (Sichten/Katalog), Smart Search, Research Workspace,
Signal Intelligence, Geo Explorer · Firmen = Company Explorer (Bestand), Contact Explorer, Watchlists, Company Compare · Heute = Outreach-
und Call Workspace · Angebote/Abrechnen = Analytics (Vertrieb, Umsatz) · Einstellungen = Data & Source Intelligence, Administration.

## 4. UX-Schwachstellen (gemessen bzw. aus Tests)

1. Kleinstschriften: 47 Regeln mit 9–10 px – unter WCAG-Empfehlung für Fließtext und schwer lesbar.
2. Uneinheitliche Radien (9 Werte) und 22 Schatten – Vorgabe 6 px / sparsame Schatten.
3. Firmenliste ohne Seiten: Antwortzeit wächst mit dem Bestand (Leistungsbericht v1.19: 5.000 Firmen in einer Antwort).
4. Einstellungen und Ansichten nicht je Nutzer – im Team-Betrieb sieht jeder die Darstellung des anderen.
5. Seltener Fehler im Browser-Test der Firmenakte (Rückweg zur Liste, offen, Plan R5.4).
6. Keine visuelle Regression und keine automatische WCAG-Prüfung.

## 5. Bewahrt bleibt

Alle 24 Ansichten, Adressen (`#/…`), Eingabeschutz (`formguard.js`), Kontaktsperre, Belegpflicht und Mandantentrennung. Neue Gestaltung
kommt als **zusätzliches Theme** – bestehende Themes bleiben wählbar; eine gespeicherte Wahl wird nicht überschrieben.

## 6. Programmstruktur

Die zehn Phasen des Auftrags sind als Pakete **U1–U10** in der Planquelle [`plan/open_intelligence.json`](plan/open_intelligence.json)
geführt (Status, Nachweis, Abnahme, Bezug zu R-Paketen) und im [Masterplan](MASTERPLAN_OPEN_INTELLIGENCE.md#ux-programm-u1u10)
dargestellt. Stand 2.0.0-dev72: U1 erledigt, U2 teilweise (Theme „Professionell“, Schriften, Dichten; Altwerte im CSS offen),
U3–U8 teilweise (Grundlagen vorhanden, siehe Abschnitt 2), U9 und U10 offen.
