---
name: research-source-policy
description: Prüfliste für jede neue Datenquelle oder geänderte Abruflogik von SignalDesk (neue Schnittstelle, neuer Host, neuer Abrufweg, Änderung an lead_finder.py, area.py, source_check.py, research/fetchers, research/sources.py, policy.py, safe_urls.py). Verwenden bei „Quelle hinzufügen“, „neue API anbinden“, „Abruf ändern“, „Crawler erweitern“.
---

# Quellen und Abrufe nach Regel aufnehmen (R1.2)

Zweck: Jede Quelle ist in der Source Registry (`sales_tool/research/sources.py`) beschrieben, geprüft und freigegeben, bevor
SignalDesk sie abruft – und jeder Abruf läuft über die Wege, die Registry, SSRF-Schutz, robots.txt und Grenzen durchsetzen.
Durchgesetzt wird das im Code (`lead_finder.fetch_source`, `research.fetchers.fetch`, `website_analyzer.public_url`,
`sources.check_api_url`, `sources.check_url`) und in `tests/test_r1_source_registry.py`. Dieser Skill prüft, ob eine
Änderung diese Wege benutzt.

## Eingaben
- Der Diff der Änderung.
- Für eine neue Quelle: Betreiber, Nutzungsbedingungen (URL), Lizenz der Daten, dokumentierte Grenzen des Anbieters.

## Prüfliste

1. **Registry-Eintrag vollständig:** ID, Betreiber, Zweck, Zugriffsart (`api` / `website` / `manuell`), Hosts, erlaubte Felder,
   Lizenz, Nutzungsbedingungen, Prüfdatum, Prüfstand, Rate/TTL, Speicher- und Exportrecht, Rechtsgrundlage, Verantwortlicher.
   Eine neue Quelle startet mit `ungeprueft` (aus). `freigegeben` setzt nur der Eigentümer (Entscheidung E2) und nennt
   sich in `approved_by` mit Datum.
2. **Ein Abrufweg:** Schnittstellen nur über `lead_finder.fetch_source` (nie `FETCH`, `urllib` oder `requests` direkt),
   Websites nur über `research.fetchers.fetch` bzw. `website_analyzer.public_url` für den Browser. Kein zweiter HTTP-Client.
3. **Rechte:** Nutzungsbedingungen erlauben automatischen Abruf und Speicherung der übernommenen Felder; Lizenzpflichten
   (Namensnennung, Share-Alike) stehen beim Export. Plattformen mit Verbot (LinkedIn, XING, Google Maps, Suchmaschinen,
   Branchenbücher) bleiben `gesperrt` – keine Umgehung von Sperren, CAPTCHAs oder Anmeldungen (CLAUDE.md, Regel 7).
4. **Grenzen:** eigene Bremse (Abstand, Tageslimit, Cache), Zeit- und Größengrenze je Abruf, `Retry-After` beachtet, keine
   endlosen Wiederholungen; eine Sperre durch die Registry ist nicht wiederholbar (`retryable=False`).
5. **SSRF und robots.txt:** öffentliche Ziele mit IP-Pinning (`safe_urls.resolve_public`), Weiterleitungen geprüft,
   robots.txt nach RFC 9309 (`fetchers/http.robots_check`) für Websites.
6. **Offline-Modus:** Der neue Weg prüft `netpolicy.offline()` und wartet im Offline-Modus statt fehlzuschlagen.
7. **Mandant:** Ausschalten wirkt nur in der eigenen Organisation (`sources.load`, Einstellung `source_policies`).
8. **Personendaten:** keine Personen aus Schnittstellen übernehmen; Kontaktwege nie aus Mustern erzeugen (Regel 5).
9. **Test:** Abruf der Quelle bei ausgeschalteter Quelle wird abgewiesen, bevor eine Verbindung entsteht (Attrappe für `FETCH`).

## Ausgabe
Je Punkt `eingehalten / verletzt / nicht betroffen` mit Datei und Zeile. Bei „verletzt“: konkrete Korrektur und fehlender Test.

## Sicherheitsregeln
- Nie eine Quelle selbst auf `freigegeben` setzen: das ist eine Entscheidung des Eigentümers (E2).
- Netzwerk in Tests nur über Attrappen; keine echten Firmen-Websites oder Schnittstellen abrufen.
- Unklare Nutzungsbedingungen = `ungeprueft` lassen und als offene Frage melden.

## Beispiel
Änderung: „Nominatim als Rückfall für unbekannte Orte.“
Ergebnis: Punkt 1 eingehalten (Eintrag `nominatim`, Prüfstand `vorlaeufig`, Rate „höchstens 1 Anfrage je Sekunde“), Punkt 2
zunächst verletzt (`area.py` rief `lf.FETCH` direkt) → Korrektur: `lf.fetch_source`; Punkt 9 eingehalten
(`tests/test_r1_source_registry.py::RegistryContentTests::test_every_automated_source_is_registered`).
