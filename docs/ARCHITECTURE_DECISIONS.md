# Architekturentscheidungen

Jede Entscheidung nennt die verglichenen Varianten, die Wahl und den Weg zurück. Bewertet nach Nutzermehrwert,
Wiederverwendung, Sicherheit, Lizenz, Wartung, Laufzeitkosten und Rückbaubarkeit.

## Kritische Prüfung des Auftrags (Phase A)

Optimierungsliste zum Master-Prompt – höchstens zehn Punkte, jeder überprüfbar:

1. **Reihenfolge.** Der Auftrag führt in acht Sprints zum SaaS. Die eigene Übergabe (`UEBERGABE_FABLE.md`, `MASTERPLAN_SOLOSELBSTAENDIGE.md`) verlangt zuerst Nutzen im eigenen Arbeitsalltag und eine Messung an echten Firmen. Beides widerspricht sich nicht, wenn SaaS-Arbeit erst nach einem bestandenen lokalen Piloten beginnt. So wird es gehandhabt.
2. **Umfang.** PostgreSQL, OIDC, Abrechnung, Worker-Trennung und MCP sind in einer Arbeitssitzung nicht prüfbar umzusetzen. Sie werden geplant (`SAAS_LAUNCH_PLAN.md`, noch zu schreiben), nicht vorgetäuscht.
3. **Doppelte Dokumente.** Sieben neue Dokumente überschneiden sich mit vorhandenen (`LEADQUELLEN_V11`, `SICHERHEITSPRUEFUNG_V18`, `BETRIEB_UND_TEAM`, `ROADMAP`). Neue Dokumente verweisen auf die alten oder ersetzen sie; nichts wird zweimal gepflegt.
4. **Acht Skills.** Der Auftrag verlangt sie nur, „wo sie konkret Entwicklungsqualität verbessern“. Angelegt werden zunächst zwei (siehe E6).
5. **Selbstbewertung 1–5** ist ohne Maßstab beliebig. Jede Note im `SELF_REVIEW_LOG.md` nennt den Messwert oder Test, auf den sie sich stützt.
6. **Live-Tests.** Der Auftrag erlaubt sie „nur wo zulässig und freigegeben“. Der Abruf echter Firmen-Websites wird nicht ohne ausdrückliche Freigabe einer Firmenliste gestartet.
7. **Zielwert „100 % der aktiven Deals mit nächster Aktion“** ist messbar über `workday.dead_ends` und wird als Test geführt.
8. **Version.** Der Stand heißt 2.0.0-dev1. Jedes Arbeitspaket erhöht die dev-Nummer; „2.0“ ohne Zusatz erst nach Abnahme.
9. **Öffentliches Repository.** „Nichts veröffentlichen ohne Freigabe“ und „in den Entwicklungsbranch committen“ treffen in einem öffentlichen Repo aufeinander. Gewählt: Commits nur auf dem Arbeitsbranch, kein Pull Request, kein Merge, kein Release – und der Hinweis im Bericht.
10. **Kennzahl statt Funktionszahl.** Der Auftrag nennt viele Funktionen. Priorisiert wird, was die Kette „finden → bewerten → erreichen → Bedarf → Angebot“ an der schwächsten Stelle verbessert.

## E1 – Weg zum SaaS

- **Variante A:** lokaler Kern bleibt, SaaS als zweite Betriebsart hinter klaren Grenzen (Speicher, Aufträge, Anmeldung), eingeführt erst nach einem lokalen Piloten.
- **Variante B:** sofortige Umstellung auf PostgreSQL mit `organization_id` in allen Tabellen.
- **Gewählt: A.** B bricht die lokale Installation ohne Fremdpakete, kostet ab dem ersten Tag Betrieb und löst kein heutiges Nutzerproblem. A hält die Kosten bei null, bis zahlende Pilotkunden feststehen.
- **Rückbau:** A legt nichts fest. Vorbereitung ohne Risiko: neue Module erhalten die Verbindung als Parameter und halten keinen globalen Zustand (so wie `service_profile.py`).

## E2 – Hintergrundaufträge

- **Variante A:** vorhandene `research/jobs.py` weiterverwenden und die fünf übrigen Thread-Module schrittweise umziehen.
- **Variante B:** Framework (Celery, RQ, Dramatiq) mit Redis.
- **Gewählt: A.** B bringt einen zweiten Dienst auf den Einzelplatz und neue Lizenzen in die Stückliste. A ist gemessen (Absturztest aus Sprint 3). Für SaaS lässt sich dieselbe Auftragstabelle später von getrennten Prozessen abarbeiten.
- **Rückbau:** je Modul ein Schalter auf den alten Thread, bis der Absturztest für dieses Modul grün ist.

## E3 – Kundenbewertung

- **Variante A:** `score_lead` um weitere Punkte erweitern.
- **Variante B:** eigenes Modul mit Kriterien, die jeweils „passt / teilweise / passt nicht / unbekannt“ tragen, getrennt in Passung (vor dem Gespräch) und Qualifizierung (danach), mit K.-o.- und Warnkriterien.
- **Gewählt: B.** A kann „unbekannt“ nicht von „schlecht“ unterscheiden und bleibt eine Zahl ohne Urteil. Der alte Lead-Fit bleibt für Sortierung und alte Tests unverändert bestehen.
- **Rückbau:** das neue Modul ist rein lesend; entfernt man die Anzeige, ändert sich an den Daten nichts.

## E4 – Speicherort des Zielkundenprofils

- **Variante A:** `app_settings` unter einem versionierten Schlüssel, wie das Leistungsprofil aus dev1.
- **Variante B:** eigene Tabellen mit Versionen und Import/Export.
- **Gewählt: A.** Ein Nutzer, ein Profil. B wird nötig, sobald mehrere Profile oder Organisationen existieren (Masterplan Solo, Punkt 4).
- **Rückbau:** Schlüssel löschen stellt die Vorgaben wieder her.

## E5 – OpenStreetMap-Daten

- **Variante A:** öffentliche Overpass-Server mit Wiederholung (heutiger Stand).
- **Variante B:** lokaler Extrakt eines Bundeslands (Geofabrik, ODbL).
- **Gewählt (2.0.0-dev7): B, ergänzt um einen Handexport – und A nur noch auf ausdrücklichen Wunsch.** Die Messung liegt vor: Im Praxistest waren die öffentlichen Server bei jedem Versuch überlastet oder nicht erreichbar.
- **Zum Lesewerkzeug** wurden zwei Wege verglichen: ein Zusatzpaket (`osmium`, schnell, aber eine weitere Abhängigkeit mit Binärdateien je Plattform) gegen einen eigenen Leser mit der Standardbibliothek (PBF ist Protobuf und zlib). Gewählt: eigener Leser. Er hält die Variante „basis“ ohne Fremdpakete; geprüft wird er gegen Dateien, die `osmium` erzeugt hat. Gemessen: rund 700.000 Einträge je Sekunde, 59 MB Arbeitsspeicher.
- **Gespeichert** werden nur benannte Betriebe, nicht die Karte – ein Regierungsbezirk bleibt damit im einstelligen MB-Bereich in der Datenbank.
- **Rückbau:** Lokalen Bestand löschen und „online abfragen“ ankreuzen stellt das alte Verhalten her.

## E6 – Projekt-Skills

- **Variante A:** alle acht Skills aus dem Auftrag anlegen.
- **Variante B:** nur Skills, für die es heute einen wiederkehrenden Arbeitsgang gibt.
- **Gewählt: B.** Zwei Skills: `qa-release-gate` (exakte Testbefehle, Umgebung, Abnahmeregeln – wurde in dieser Sitzung mühsam neu ermittelt) und `privacy-and-contact-guardrails` (Prüfliste für Änderungen an Kontaktwegen). Die Regeln selbst stehen weiter im Programmcode und in Tests. Die übrigen sechs entstehen, wenn ihr Arbeitsgang ansteht.

## E7 – Themes und Dunkelmodus

- **Variante A:** CSS-Variablen für Farbrollen; Theme und Modus als Attribute am `<html>`-Element, gesetzt von einem kleinen Skript vor dem ersten Zeichnen.
- **Variante B:** je Theme ein eigenes Stylesheet.
- **Variante C:** ein CSS-Framework mit Theme-Unterstützung.
- **Gewählt: A.** B verdoppelt bei jeder Änderung die Pflege und lädt beim Umschalten neu. C bringt eine Abhängigkeit und einen Umbau aller Ansichten. A ist eine Datei, ohne Build-Schritt, verträgt die Inhaltssicherheitsrichtlinie (`script-src 'self'`) und erlaubt neue Themes mit rund 20 Werten.
- **Gespeichert** wird in `app_settings` (wie Gewichte und Profile); der Browser hält eine Kopie nur für den Seitenstart.
- **Rückbau:** Darstellung auf „Klassisch, Hell“ stellen. Die Rollen selbst bleiben; sie kosten nichts.


## E8 – Zentraler Leistungskatalog (2.0.0-dev16, Review M12)

- **Variante A:** die 26 Baukasten-Leistungen als einzige Quelle; Pakete und Angebote werden zu Vorlagen (Zusammenstellungen), deren Preis aus den Positionen berechnet wird.
- **Variante B:** eine neue Tabelle `services` in der Datenbank mit Migration aller vier Listen und frei anlegbaren Leistungen.
- **Variante C:** die Pakete behalten eigene Preise, der Baukasten rechnet daneben weiter.
- **Gewählt: A.** C ist genau der Zustand, den das Review bemängelt (Empfehlung „ab 18.500 €“, Angebot 13.510 € für dieselbe Vorlage). B bringt Migration und Rückbaurisiko für eine Eigenschaft (eigene Leistungen anlegen), die noch niemand gebraucht hat. A behält alle Kennungen, braucht deshalb keine Datenmigration, und eigene Werte liegen wie bisher in `app_settings` (`service_overrides`).
- **Gespeicherte Angebote** sind Kopien (Kunden- und interner Teil als JSON) und werden nie umgerechnet; neue Angebote speichern intern einen Katalogstand (Prüfsumme aus Katalog, eigenen Werten und Grundlagen).
- **Rückbau:** Vorlagen-Positionen in `catalog.VORLAGEN` ändern oder eigene Werte zurücksetzen. Die früheren Zahlen stehen in `catalog.FRUEHER` (nur zur Nachvollziehbarkeit).

## E9 – Verkaufschancen je Firma (2.0.0-dev18, Review M13)

- **Variante A:** neue Tabelle `opportunities`; Angebote und Termine verweisen auf eine Chance; die Firmenphase (`leads.stage`) bleibt als Spalte und wird aus den Chancen abgeleitet (nur nach oben bzw. zum Abschluss).
- **Variante B:** Phase, Bedarf und nächster Schritt vollständig von der Firma in die Chance verschieben und alle rund 30 lesenden Stellen auf einmal umstellen.
- **Variante C:** Chancen nur als Notizen ohne eigene Phase.
- **Gewählt: A, in zwei Teilen.** B ist ein großer Umbau ohne Zwischenstand, der sich nicht sicher abnehmen lässt. C erfüllt die Abnahme nicht. Mit A lesen alle bisherigen Ansichten weiter die Firmenphase, die nun aus den Chancen folgt; neue Ereignisse (Termin, Versand, Zusage) schreiben auf ihre Chance. Teil 2 verschiebt Bedarfsanalyse und Freigabe in die Chance und zeigt Chancen in Pipeline und Heute.
- **Erste Chance:** nutzt bis Teil 2 die Bedarfsanalyse der Firma (Tabelle `discovery`), damit kein Bedarf doppelt gespeichert wird.
- **Rückbau:** Die Spalten `opportunity_id` dürfen leer sein; ohne Chancen verhält sich SignalDesk wie vorher. Die Tabelle kann bleiben.
- **Teil 2 (dev19):** Weitere Chancen speichern ihre Bedarfsanalyse und Freigabe in eigenen Spalten derselben Tabelle; `workday.need_status`, `confirm_need`, `reopen_need` und `quote_from_need` nehmen optional die Chance. Die Versandfreigabe prüft den Bedarf der Chance des Angebots.
