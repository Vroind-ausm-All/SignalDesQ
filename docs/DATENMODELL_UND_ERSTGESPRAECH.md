# Vom 0-€-Start zur ersten bezahlten Kundenbeziehung

## Datenerfassung

1. **Vor dem Kontakt**: Firmenname, Website, Branche, Standort, Rolle, aktuelles überprüfbares Bedarfssignal, Originalquelle + Beobachtungsdatum, vermutetes Problem, Angebotshypothese. Personendaten nur soweit erforderlich. Schätzungen klar kennzeichnen.
2. **Kontaktfähigkeit**: Beziehungsweg und dokumentierter rechtlicher Kontaktstatus. **Öffentlich auffindbare E-Mail-Adresse = keine Einwilligung.** Bei ungeklärtem Status keine Werbung versenden. Bei Widerspruch gesperrt lassen.
3. **Erstgespräch** (im Lead → Bedarfsanalyse): Bestätigtes Problem, Auswirkungen, bisherige Lösung, konkretes Ziel, Zeitfenster, Entscheidung/Freigabe, Budgetstatus. Nächsten Schritt + Datum im Lead setzen.
4. **Angebot**: Nur für bestätigten Bedarf und passenden Entscheider. Kleine bezahlte Diagnose/Pilot statt langer kostenloser Vollkonzeption.

## 5 Kernfragen des Gesprächs

- Was funktioniert aktuell nicht? **Kundenaussage** festhalten.
- Welche Folgen hat das? Aufwand / entgangene Anfragen nur schätzen, wenn ausdrücklich als Schätzung gekennzeichnet.
- Was soll danach messbar anders sein?
- Warum jetzt, wann ist eine Lösung nötig?
- Wer entscheidet / welche anderen Personen sind beteiligt?

Separat: Wie lösen Sie es heute? Ist bereits Budget vorgesehen? Gibt es eine sinnvolle kleine erste Projektphase? Was ist ein verbindlicher nächster Schritt?

## CSV-Datenschema

Kopfzeilen in `vorlagen/leads_import_vorlage.csv` (Semikolon): `company;website;location;industry;employees;signal_type;signal_date;signal_source;signal_note;offer;contact_name;contact_role;contact_route;permission;permission_evidence;next_step;next_date`.

- `industry`: `Industrie & B2B-Technik`, `B2B-SaaS`, `Professionelle Dienstleistungen`, `Sonstige`.
- `signal_type`: `produktlaunch`, `digitalprojekt`, `offene_stelle`, `prozessproblem`, `expansion`, `event`, `empfehlung`, `kein_signal`.
- `offer`: `conversion`, `brand`, `portal`.
- `contact_route`: `unbekannt`, `persoenliche_empfehlung`, `inbound`, `veranstaltung`, `netzwerk`, `brief`, `sonstiges`. Kontaktweg und Rechtsstatus sind **unterschiedliche** Dinge.
- `permission`: `unbekannt`, `opt_in`, `bestandskunde_pruefen`, `telefon_einzelfall`, `nicht_kontaktieren`.
- Datum: `JJJJ-MM-TT`. `employees`: nichtnegative ganze Zahl, bei Unbekannt leer lassen.
- Import nur der Recherche-Felder, keine automatisierten Nachrichten oder ungeprüften personenbezogenen Massenlisten.
- Import meldet fehlerhafte Zeilen und Dubletten anhand von Firmenname/Website. Bitte Ergebnis prüfen.

## Start bei 0 € Umsatz (kein erfundener Funnel)

**Woche 1**: ein Angebot wählen, zwei Vorzeigeprojekte oder überzeugende Demos, eine kurze Angebotsseite und 10 Gespräche mit vorhandenen Kontakten/Empfehlern anbahnen.
**Woche 2–3**: 20 passende Firmen recherchieren, je eine echte Beobachtung dokumentieren, Einstieg über bestehende Beziehungen und andere zulässige Kanäle.
**Woche 3–4**: Erste Gespräche strukturiert protokollieren, nur reale Projekte mit Budget und Entscheider in Angebotsphase bringen. Keine Gewinnquoten behaupten, bevor echte Daten vorliegen.
**Wöchentlich messen**: identifizierte Firmen, überprüfte Signale, zulässige Intro-Anfragen, tatsächlich geführte Gespräche, bestätigte Probleme, kostenpflichtige Angebote, Abschlüsse. 3 bezahlte Pilotaufträge als erstes Ziel.

## Datenschutz

Nur notwendige personenbezogene Daten speichern, Quelle/Zweck und Informationspflichten beachten, Widersprüche sofort beachten, angemessene Löschfristen definieren. Betrieb nur lokal; öffentliches Hosting benötigt Auth, TLS, Backups, Rechte- und Sicherheitsprüfung. Briefpost, Telefon und E-Mail unterscheiden sich rechtlich. Keine Kontaktaufnahme allein aufgrund eines Lead-Scores.
