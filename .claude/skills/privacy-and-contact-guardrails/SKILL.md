---
name: privacy-and-contact-guardrails
description: Prüfliste für jede Änderung an SignalDesk, die Kontaktwege, Personen, Gesprächsprotokolle, Sperren, Importe oder Entwürfe berührt. Verwenden bei Arbeiten an sales_workspace.py, workday.py, sales_integration.py, qualification.py, company_data.py, Importen und Mail-/Anruf-Funktionen.
---

# Kontakt- und Datenschutz-Leitplanken

Zweck: verhindern, dass eine Änderung unbemerkt eine Schutzregel aufweicht. Durchgesetzt werden die Regeln im Code
(`workday.contact_lock`, `assert_contact_allowed`, `company_data.check_suppressed`) – dieser Skill prüft nur, ob neuer Code sie benutzt.

## Eingaben
- Der Diff der Änderung.

## Prüfliste

1. **Sperre:** Jeder neue Weg, der Gespräch, Termin, Entwurf, Angebot oder Kontaktvorschlag anlegt, ruft `assert_contact_allowed` auf. Ein Widerspruch lässt sich immer dokumentieren.
2. **Reimport:** Kein Import, keine Zusammenführung und keine automatische Übertragung hebt `nicht_kontaktieren`, die Phase `gesperrt` oder einen Eintrag der Sperrliste auf.
3. **Keine Erlaubnis aus Daten:** Ein gefundener Kontaktweg, eine gute Bewertung oder ein Kaufsignal setzt nie `permission`. Texte in der Oberfläche nennen „belegt“ und „erlaubt“ getrennt.
4. **Kein Versand:** Kein Code öffnet eine Verbindung zu Mail-, Telefon- oder Nachrichtendiensten. Entwürfe bleiben Entwürfe.
5. **Personen:** Personen werden nie automatisch angelegt. Telefonnummern und E-Mail-Adressen werden nie aus Mustern erzeugt; jeder Wert braucht eine Fundstelle.
6. **Datensparsamkeit:** Neue Felder zu Personen brauchen einen Zweck und fallen unter die Löschfristen in `quality.py`.
7. **Lesende Auswertungen** (Bewertung, Statistik) ändern keine Firmendaten und legen keine Aufgaben an.
8. **Test:** Zu jeder berührten Regel gibt es einen Test, der mit einer gesperrten Firma scheitern würde, wenn die Regel fehlt.

## Ausgabe
Je Punkt `eingehalten / verletzt / nicht betroffen` mit Datei und Zeile. Bei „verletzt“: konkrete Korrektur und fehlender Test.

## Sicherheitsregeln
- Bei rechtlicher Unsicherheit (z. B. § 7 UWG, Art. 14 DSGVO) die vorsichtigere Auslegung umsetzen und fachliche Prüfung als offene Voraussetzung nennen. Keine Rechtsberatung formulieren.

## Beispiel
Änderung: „Nach ‚nicht erreicht‘ automatisch eine Wiedervorlage anlegen.“
Ergebnis: Punkt 1 eingehalten (`create_call` prüft die Sperre vor dem Eintrag), Punkt 3 eingehalten (nur Aufgabe, `permission` unverändert), Punkt 4 eingehalten, Punkt 8: Test `test_suppressed_company_is_excluded` vorhanden.
