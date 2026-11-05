# Sprint-Bericht Phase 5 – Sales-Integration (v1.7)

Gemäß Masterplan v2 und Master-Prompt v2.0, Module 6 (Decision Maker Finder v3), 8 (Offer Matching) und 10 (Sales Action Center), Sprint 5.

## Was ist tatsächlich implementiert?

### Modul 8 – Angebots-Matching aus bestätigten Problemen

- **Grundlage sind Kundenaussagen, keine Hypothesen.** Die Pakete werden aus den Feldern der Bedarfsanalyse abgeleitet: bestätigtes Problem, Auswirkung, bisherige Lösung, gewünschtes Ergebnis, Zeitrahmen, Entscheidungsweg und Budget. Jede Zuordnung enthält das **wörtliche Zitat** mit Feldname.
- **Hinweise aus der Recherche** (Signal-Hypothesen, Website-Bewertung) erscheinen getrennt als „nicht bestätigt“. Sie machen ein Paket nie zur Angebotsgrundlage.
- **Zwei Status:**
  - **unverbindlich:** solange die Bedarfsklärung unvollständig ist oder für ein Paket nur Recherche-Hinweise vorliegen.
  - **Angebotsgrundlage:** Die Bedarfsklärung ist dokumentiert (Problem und gewünschtes Ergebnis ausgefüllt, mindestens 4 von 5 Kernfragen beantwortet) **und** es gibt eine bestätigte Kundenaussage zu diesem Paket.
- **Budgethinweis:** Bei „kein Budget“ oder „Freigabe offen“ wird bei Paketen über 3.000 € der Einstieg über den Pilot vorgeschlagen.
- **„Als Angebotsgrundlage verwenden“** öffnet das Angebotsmodul vorausgefüllt mit Firma, Paket, Projekttitel, Kundenziel (= gewünschtes Ergebnis laut Gespräch) und Voraussetzungen (Zeitrahmen, Entscheidungsweg, bisherige Lösung). Bei unverbindlichen Empfehlungen lehnt der Server das ab.
- **Neues Paket „Automatisierungsprojekt – ein Prozess digital“** (ab 6.900 €, 4–6 Wochen), auch in Lead-Angebot, Score-Bonus bei Prozessproblem und Rollenvorschlägen.
- **Kundendokument** um drei Abschnitte erweitert (für alle Pakete):
  - Liefergegenstände
  - Abnahmekriterien
  - Mögliche Drittanbieter- und Folgekosten (nicht im Festpreis)

  Interne Kalkulation (Stunden, Kostensatz, Deckungsbeitrag) bleibt draußen.

### Modul 6 – Decision Maker Finder v3

- **Drei getrennte Rollenfragen je Person:** fachlich zuständig, Budgetverantwortung, finale Entscheidung. Jede steht auf *unbekannt*, *vermutet* oder *bestätigt*.
- **Regeln für „bestätigt“:**
  - fachlich bzw. Budget nur mit Prüfstatus „Quelle geprüft“ oder „Rolle bestätigt“;
  - finale Entscheidung nur mit „Rolle bestätigt“, also z. B. im Gespräch bestätigt.
- **Rollenlandkarte je Thema** (Website & Anfragen, Marke & Design, Portal/Software, Prozess & Automatisierung). Das Thema wird aus Hypothesen, Paketempfehlungen und Lead-Angebot abgeleitet. Rollen ohne Person mit geprüfter Quelle sind als Lücke markiert.
- **Veröffentlichter geschäftlicher Kontaktweg** je Person nur mit Art (E-Mail/Telefon) und HTTPS-Fundstelle. Abgewiesen werden:
  - die allgemeine Firmennummer als „Durchwahl“;
  - allgemeine Adressen (info@, kontakt@ …) als persönlicher Kontaktweg.
- **Kontaktbeschränkungen je Person:** keine Anrufe, keine E-Mails, nur Briefpost, nur über Zentrale/Assistenz, Widerspruch. Ein **Widerspruch** bewirkt:
  - die bekannte E-Mail kommt auf die Sperrliste;
  - offene Kontaktaktionen zu dieser Person werden abgelehnt;
  - ein Eintrag im Audit-Log.

### Modul 10 – Sales Action Center

- **Aufgabenvorschläge aus Rechercheergebnissen** je Lead und gesammelt in „Mein Sales-Tag“:
  - Website manuell prüfen (ungeprüfte auffällige Befunde)
  - Ansprechpartner verifizieren / zuständige Person recherchieren (Rollenlücke)
  - Bedarfsfragen vorbereiten (Hypothese ohne Bedarfsklärung)
  - persönliche Empfehlung anfragen (kein dokumentierter Kontaktweg)
  - Kundentermin vorbereiten (Termin in den nächsten 7 Tagen)
  - Angebot kalkulieren (Angebotsgrundlage, noch kein Angebot)
  - vereinbarten Follow-up bearbeiten (Angebot länger als 7 Tage beim Kunden)
  - Erstkontakt vorbereiten (nur bei dokumentiertem Rechtsstatus)
- **Übernehmen oder verwerfen:** Übernehmen legt eine Aufgabe an. Ein Vorschlag mit offener Aufgabe oder ein verworfener Vorschlag erscheint nicht erneut. Gesperrte, gewonnene, verlorene oder „nicht kontaktieren“-Leads erhalten keine Vorschläge.
- **Eigene Freigabe je Kontaktaktion:** Erstkontakt und Follow-up starten als „Freigabe offen“. Die Freigabe prüft:
  - Mindestens 15 Zeichen konkrete Rechtsgrundlage.
  - **E-Mail:** nur mit Opt-in oder geprüfter Bestandskunden-Ausnahme, jeweils mit Dokumentation (§ 7 Abs. 2 Nr. 3, Abs. 3 UWG).
  - **Telefon:** nur mit Opt-in oder Einzelfallprüfung samt Dokumentation (§ 7 Abs. 2 Nr. 1 UWG).
  - **Persönlich:** nur über dokumentierte Empfehlung, Veranstaltung, Netzwerk oder eigene Anfrage.
  - Gesperrte Leads werden abgewiesen.
  - Die Beschränkungen der Person gelten, z. B. „keine Anrufe“ oder „nur Briefpost“.

  Jede Freigabe wird im Audit-Log festgehalten.
- **Ohne Freigabe nicht erledigt:** Eine Kontaktaktion mit offener oder abgelehnter Freigabe lässt sich nicht abhaken. Der Server antwortet mit 409, in der Aufgabenliste ist das Kästchen gesperrt.
- **Es wird nichts versendet.** Nach der Freigabe kontaktierst du selbst und protokollierst das Ergebnis.

**Backend:** `sales_integration.py`.
- **Zwei neue Tabellen:**
  - `offer_recommendations` (Empfehlung mit Status, Rang und Belegen);
  - `action_dismissals` (verworfene Vorschläge).
- **Zusätzliche Spalten in bestehenden Tabellen:** Rollen, Beschränkungen und Kontaktweg in `decision_contacts`; Aktionstyp, Quelle, Kanal, Person und Freigabestatus in `tasks`.
- **Schema-Version 16** mit automatischem Backup vor der Migration.
- **Endpunkte:**
  - `/api/leads/{id}/offer-matching`, `/api/leads/{id}/decision-map`, `/api/leads/{id}/action-suggestions`
  - `/api/offer-recommendations/{id}/quote-draft`
  - `/api/contacts/{id}/roles`
  - `/api/action-suggestions` (mit `/accept` und `/dismiss`)
  - `/api/tasks/{id}/permission`

**Oberfläche:**
- Im Lead-Dialog die neuen Bereiche:
  - „Rollen, Befugnisse & Kontaktbeschränkungen“
  - „Passende Pakete aus dem Leistungskatalog“ (wird nach dem Speichern der Bedarfsanalyse neu abgeglichen)
  - „Vorgeschlagene Aufgaben“
- In „Mein Sales-Tag“: „Vorgeschlagene Aufgaben“ und „Kontaktaktionen – Freigabe“.
- In der Aufgabenliste ein Freigabe-Badge je Kontaktaktion.

## Welche Tests wurden ausgeführt?

- `python -m unittest discover -s tests -q`: **187 Tests grün**, davon 16 neu in `tests/test_phase5_sales.py`. Mit Playwright und Chromium laufen alle 187; ohne Playwright werden wie bisher 2 Browser-Tests übersprungen.
- Abgedeckt:
  - **Matching:**
    - nur Hinweise → unverbindlich und kein Angebotsentwurf
    - unvollständige Bedarfsklärung bleibt trotz Kundenzitat unverbindlich
    - vollständige Bedarfsklärung → Angebotsgrundlage mit wörtlichen Zitaten; ein Paket nur aus Recherche bleibt unverbindlich
    - Vorbelegung des Angebots, Budgethinweis
    - ohne Daten keine Empfehlung
  - **Paket „Automatisierung“:** im Kundendokument mit Liefergegenständen, Abnahmekriterien und Drittkosten, ohne interne Kalkulation
  - **Rollen:**
    - „bestätigt“ nur mit geprüfter Quelle, finale Entscheidung nur mit bestätigter Rolle
    - ungültige Werte und Felder werden abgewiesen
    - Firmennummer als Durchwahl, allgemeine Adresse, fehlende Fundstelle und fehlende Art werden abgewiesen
    - Rollenlandkarte mit Lücken
  - **Widerspruch:** Sperrliste, offene Kontaktaktionen abgelehnt
  - **Vorschläge:** aus Recherche, Bedarfsklärung, Angebot und Follow-up; keine Kontaktaktion ohne Rechtsstatus; keine doppelten Vorschläge; Verwerfen; keine Vorschläge für gesperrte Leads oder Leads mit Widerspruch
  - **Freigabe:** Regeln je Kanal, Mindestbegründung, Personenbeschränkung, Ablehnung, gesperrter Lead, Audit-Eintrag, Erledigt-Sperre
  - **HTTP:** alle Endpunkte inkl. 400/404/409 und Auslieferung von `salesint.js`
- **Klickdurchlauf im Browser** (Chromium, fiktive Firma „Fiktiv Antriebstechnik GmbH“):
  - Bedarfsanalyse → Abgleich mit Angebotsgrundlage und unverbindlichem Zweitpaket
  - Rollenlandkarte, Firmennummer als Durchwahl abgewiesen, Beschränkung „keine Anrufe“ gespeichert
  - Vorschlag „Erstkontakt per E-Mail“ übernommen
  - „Als Angebotsgrundlage verwenden“ → Angebotsmodul mit Firma, Paket, Titel, Ziel und Voraussetzungen
  - in „Mein Sales-Tag“: Erledigen vor der Freigabe blockiert (409), Freigabe dokumentiert, Badge in der Aufgabenliste
  - Mobilansicht 390 px ohne Überlauf; keine Konsolenfehler außer den bewusst ausgelösten 400/409-Antworten

## Was ist noch ungetestet?

- **Echte Gesprächsdaten.** Die Zuordnung zu Paketen arbeitet mit Stichwortregeln auf Deutsch. Ob sie bei echten, frei formulierten Gesprächsnotizen trifft, zeigt erst der Einsatz. Fehlzuordnungen sind sichtbar, weil das Zitat danebensteht, und sie werden nie automatisch zur Angebotsgrundlage, solange die Bedarfsklärung fehlt.
- Das Zusammenspiel mit echten Rechercheergebnissen (siehe Berichte Phase 1–4). Die Live-Tests der Quellen stehen weiter aus.
- Performance der gesammelten Vorschläge bei mehreren hundert Leads (Berechnung je Lead, begrenzt auf 200 aktive Leads und 30 Vorschläge); Lasttest in Phase 6.

## Welche technischen oder rechtlichen Grenzen bestehen?

- **Die Freigabe ist eine Dokumentationshilfe, keine Rechtsberatung.** SignalDesk prüft, ob die Voraussetzungen *dokumentiert* sind. Ob eine Einwilligung wirksam ist oder ein mutmaßliches Interesse im B2B-Einzelfall trägt, entscheidest du selbst bzw. deine Rechtsberatung.
- **Briefpost** gilt nach § 7 UWG als grundsätzlich zulässig, solange kein erkennbarer Widerspruch vorliegt. Sie braucht deshalb nur die dokumentierte Begründung und die Beachtung der Personenbeschränkungen.
- Rollen „vermutet“ sind Arbeitshypothesen. Die KI und die Regeln setzen niemals „bestätigt“; das geht nur manuell mit geprüfter Quelle.
- Die Paketempfehlung ersetzt keine Kalkulation: Leistungsumfang, Festpreis und Steuerstatus müssen vor dem Versand geprüft werden.

## Was ist als Nächstes sinnvoll?

1. **Live-Durchlauf** mit 10–20 echten Zielfirmen über die ganze Kette, ab Phase 5 inklusive echtem Erstgespräch, Bedarfsanalyse, Matching und Angebot.
2. **Phase 6 – Qualität & Skalierung:**
   - Datenaktualisierung und Änderungserkennung, wiederkehrende Rechercheaufgaben, Veraltungs-Kennzeichen
   - Last- und Fehlertests, Sicherheitsprüfung, Migrationstest
   - konfigurierbare Gewichte der Recherchepriorität
   - Vorbereitung Team/Cloud (Login, Rollen, Verschlüsselung)
