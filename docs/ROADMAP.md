# Roadmap – nicht mit dem MVP verwechseln

## V0.1 – tatsächlich implementiert
- [x] Lokale SQLite-Persistenz, CRUD Leads
- [x] Beleg-/Signal-Erfassung mit Heuristik-Score
- [x] Pipeline, Filter, Kennzahlen
- [x] Aktivitäten und fällige Aufgaben
- [x] Zielgruppenspezifische Angebote und manuell nutzbare Gesprächsentwürfe
- [x] Opt-in-/Sperrstatus, **kein Nachrichtenversand**
- [x] Unit-Tests und Dokumentation

## V0.2 – implementiert für den Start bei 0 € Umsatz
- [x] CSV-Import (bis 50 Zeilen, Formatvalidierung, einfache Dublettenprüfung)
- [x] Getrennte strukturierte Bedarfsanalyse pro Lead mit fünf Kernfragen
- [x] Standort, Kontaktrolle und Kontaktweg im Lead, inklusive Alt-Datenbank-Migration

## V0.3 – nach ersten 30 echten Leads
- [ ] Erweiterter CSV-Import mit Rechtsgrundlagenprüfung und Import-Audit-Log
- [ ] Angebotsvorlagen und Opportunity-Werte **getrennt** von Lead-Budget-Hypothesen
- [ ] Audit-Trail, Datenexport/-löschung und Aufbewahrungsfristen
- [ ] Branchenspezifische Score-Gewichte konfigurierbar machen, echte Outcome-Daten zur Kalibrierung
- [ ] Weekly Review: Deals nach Herkunft, Segment, Abschlussgründen und Deckungsbeitrag
- [ ] Customer Delivery-SOPs und Time-to-first-value

## V0.4 – optional, erst nach Nachweis der Nachfrage
- [ ] n8n-Workflow für **Zulieferung öffentlich verifizierter, erlaubter Firmensignale**, erst menschliche Freigabe, dann Speicherung
- [ ] Quellenadapter für lizenzierte Datenquellen (ohne Scraping persönlicher Profile)
- [ ] LLM für Vorschläge zur Signal- und Angebotszuordnung nur auf freigegebenen Daten, Quellenverweise, Fehlerkontrolle
- [ ] Inbound-Formulare und Terminbuchung
- [ ] ggf. CRM-Integration über offizielle APIs mit Consent-/Opt-out-Synchronisation
- [ ] Separates Multi-User-Produkt mit Login, Rollen, Verschlüsselung, Backups, TLS, Limits, Datenschutz-/Sicherheitsanalyse

## Absichtlich kein Feature
- Massenhafte Kalt-E-Mails, LinkedIn-Bots, gekaufte unqualifizierte Leadlisten oder WhatsApp-Spam
- Blindes Kopieren eines Wettbewerber-Templates oder dessen Markenauftritt
- KI-Bewertung, die ihr eigenes Ergebnis ohne Quellenbeleg als Fakt ausgibt

## Definition of Done für ein mögliches kommerzielles Release
- mindestens 30 anonymisiert ausgewertete echte Leads, ein klarer ICP, messbarer Delivery-Nutzen
- Rechtsprüfung für Kanäle und Datenquellen, Datenschutzkonzept und Verträge
- Vulnerability-Test / Security Review, Backup- und Restore-Test, Benutzerrollen
- klarer Produktumfang, Support- und Datenlöschprozess
