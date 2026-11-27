---
name: document-intelligence
description: Prüfliste für jede Änderung von SignalDesk, die Dokumente liest (PDF, XML, CSV, ZIP, Text) oder Werte aus Dokumenten übernimmt (docparse.py, research/documents.py, imprint.py PDF-Impressum, Importe, Uploads in die Firmenakte). Verwenden bei „PDF auswerten“, „XML/CSV einlesen“, „Upload von Registerdokumenten“, „neues Dokumentformat“, „Fundstelle im Dokument“.
---

# Dokumente isoliert lesen und mit Fundstelle belegen (R3.5)

Zweck: Kein Dokument wird im Server- oder Auftragsprozess geparst, und jeder Wert aus einem Dokument trägt eine prüfbare
Fundstelle (PDF-Seite, XML-Pfad, CSV-Zeile/Spalte, ZIP-Eintrag). Durchgesetzt im Code: `sales_tool/research/documents.py::parse`
(eigener Prozess `python -I -S sales_tool/docparse.py`, Zeitgrenze, Bytes nur über stdin), `sales_tool/docparse.py::_sandbox`
(Prüf-Hook gegen Netz, Prozesse, Schreiben; Speicher/CPU unter Linux/macOS), `documents.document_ref` / `verify_document_ref`
und `research/evidence.py::check_ref`. Tests: `tests/test_r3_documents.py`.

## Eingaben
- Der Diff der Änderung.
- Für ein neues Format: Beispiel-Dokument (erfunden, im Test erzeugt) und die Grenzen, die dafür gelten sollen.

## Prüfliste

1. **Ein Weg:** Dokument-Bytes gehen nur über `research.documents.parse`. Kein `zlib.decompress`, `zipfile.extractall`,
   `xml.etree.ElementTree.fromstring`, `pypdf` oder `csv` auf fremden Dokumenten im Hauptprozess.
2. **Isolation:** Parser-Code liegt in `sales_tool/docparse.py` (nur Standardbibliothek, keine Paket-Importe). Neue Bibliotheken
   (z. B. pypdf, pdfplumber) laufen nur im Kindprozess und brauchen den Skill `dependency-security`.
3. **Grenzen:** Eingabegröße, Zeit, entpackte Bytes je Strom und gesamt, Seiten, Abschnitte, Textlänge, Elemente, Zeilen,
   Spalten und ZIP-Einträge sind begrenzt (`docparse.LIMITS`). Eine Grenze ergibt ein Teilergebnis mit Warnung oder eine
   Abweisung mit Grund – nie einen Absturz und nie einen leeren „negativen Befund“ (CLAUDE.md, Regel 11).
4. **Angriffsmuster:** XML mit DTD/Entitäten abweisen (XXE, Entitäten-Bombe); Flate- und ZIP-Bomben über Größe und Packrate;
   ZIP-Pfade mit `..`, absolutem Pfad, Laufwerk oder Steuerzeichen abweisen und nie auf die Platte entpacken; verschlüsselte
   PDFs abweisen; JavaScript, Aktionen und eingebettete Dateien nie ausführen, nur melden.
5. **Fundstelle:** Jeder übernommene Wert hat einen Beleg v2 aus `documents.document_ref` – PDF nur mit Seite, XML mit Pfad,
   CSV mit Zeile und Spalte, ZIP zusätzlich mit Eintrag. Ohne Fundstelle wird der Wert verworfen (Regel 6).
6. **Gegenprüfung:** `verify_document_ref` gegen dasselbe Dokument (gleicher SHA-256) ergibt `True`; ein anderes Dokument oder
   eine andere Seite ergibt `False`.
7. **Personen und Kontakte:** Namen aus Dokumenten werden nur Kandidaten (Skill `contact-entity-evidence`), nie CRM-Kontakte;
   Telefonnummern und E-Mail-Adressen nie aus Mustern erzeugen (Regel 5). Sperren gelten vor der Übernahme (Regel 1).
8. **Upload und Herkunft:** Hochgeladene Registerdokumente landen nur im Parser-Prozess; kein automatisches Abrufen von
   Registerportalen (Regel 7). Die Herkunft (`source_url`, z. B. `upload:<Dateiname>`) steht im Beleg.
9. **Test:** Für jedes neue Format ein Angriffsbeispiel (Bombe, Pfad, Entität o. Ä.) und ein Fundstellen-Test mit erfundenen Daten.

## Ausgabe
Je Punkt `eingehalten / verletzt / nicht betroffen` mit Datei und Zeile. Bei „verletzt“: konkrete Korrektur und fehlender Test.

## Sicherheitsregeln
- Keine echten Dokumente mit Personendaten im Repository; Testdokumente werden im Test erzeugt.
- Eine Grenze nie erhöhen, um einen Test grün zu bekommen, ohne den Grund im Commit zu nennen.
- Der Prüf-Hook ist eine zusätzliche Bremse, keine Sicherheitsgrenze gegen Code-Ausführung im Parser: deshalb bleibt der
  Parser bei der Standardbibliothek und führt nie Inhalte aus.

## Beispiel
Änderung: „Impressum als PDF auswerten.“
Ergebnis: Punkt 1 zunächst verletzt (`imprint.pdf_to_text` entpackte Flate-Ströme ohne Grenze mit `zlib.decompress`) →
Korrektur: `research.documents.parse(raw, 'pdf')`; Punkt 4 eingehalten
(`tests/test_r3_documents.py::LocatorTests::test_imprint_pdf_uses_the_isolated_parser` mit 30-MB-Bombe);
Punkt 5 eingehalten (`tests/test_r3_documents.py::LocatorTests::test_pdf_pages`).
