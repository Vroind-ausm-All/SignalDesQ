# Übergabe: SignalDesk 2.0-Entwicklungsstand

## Ziel
SignalDesk dient zunächst einer soloselbstständigen Medienagentur. Die wichtigste Kette ist: Handwerksbetriebe finden, die richtige Homepage zuordnen, Inhalte und Technik mit Quellen prüfen, mögliche Leistungen als Hypothesen darstellen und den nächsten Arbeitsschritt festhalten. Ein Fund ist weder bestätigter Bedarf noch Kontaktberechtigung.

## Stand und wichtigste Entscheidungen
Ausgangsbasis ist GitHub-Commit `ce3312f` (v1.19). Der Quellpaketinhalt enthält den Arbeitsstand einschließlich nicht eingecheckter Änderungen und Tests; er ist kein Git-Repository. Keine Datenbank, `.venv`, Backups oder Zugangsdaten sind enthalten. Nicht zurücksetzen oder bestehende Daten überschreiben. Vor einem Update bestehender Nutzerdaten eine externe Sicherung herstellen und deren Wiederherstellung erproben.

### Implementiert
- `sales_tool/sweep.py`: Ein fehlgeschlagener oder teilweise blockierter Website-Abruf gilt als unvollständig und ist über den Rechercheauftrag wiederholbar. Eigene Websites können in der Sichtung als ungeprüfter Vorschlag eingegeben und separat bestätigt werden. Syntaxprüfung erfolgt ohne Netzwerk; beim Abruf bleiben SSRF- und robots.txt-Prüfungen aktiv.
- Register-Zuordnung: Eine gleiche Nummer ohne belegten Vergleich des Registergerichts ist nur ein Vorschlag. Widersprechende Nummer, Name oder PLZ verhindern eine automatische Zuordnung. Die gegenwärtige Kandidatentabelle speichert kein Registergericht; die meisten solchen Treffer benötigen daher eine Bestätigung. Bereits bestehende Bewertungen aus älteren Versionen werden nicht rückwirkend geändert und sollten bei Nutzung geprüft werden.
- `sales_tool/research/service_profile.py`: Pro Datenbank gespeichertes Profil für die regelbasierte Inhaltsanalyse; bestehende Themen an-/abschaltbar und mit zusätzlichen wörtlichen Suchbegriffen ergänzbar. Profile wirken auf neue Firmenberichte und URL-Recherchen im Regelmodus; sie ändern weder technische Website-Scores, Recruiting-Klassifikation, KI-Modus noch historische Berichte. Profilversion und Snapshot sind im Ergebnis gespeichert. Redaktion unter „Datenqualität & System → Dein Leistungsprofil“.
- Inhaltsrecherche: mehr als drei belegte Befunde möglich; zusätzliche Hinweise zu Kampagnen und Foto/Video; thematisch verteilte Auswahl innerhalb des bestehenden Fünf-Seiten-Budgets. Ein Suchbegriff allein belegt keinen Bedarf. Die Erkennung ist regelbasiert und nicht vollständig.
- Firmenberichte: Bei Wiederholung werden erfolgreiche Schritte beibehalten; abhängige Empfehlungen werden erneut berechnet. Ein Bericht mit einzelnen Fehlern erhält den Status „teilweise“. Fehlgeschlagene und teilweise Karriereabrufe sind unterscheidbar. Die Überwachung berücksichtigt das konfigurierte Wiederholungsintervall.
- Website-Scorer: Kein öffentlich gefundener Portal-Link bedeutet „unbekannt“, nicht „Portal benötigt“. Die Bewertungslogik erhält eine neue Score-Version; ältere Ergebnisse und benutzerdefinierte Gewichte bleiben erhalten.

## Bekannte Grenzen und priorisierte Weiterarbeit
1. **Praxistest:** Zielgruppe Handwerk im Raum Stuttgart. In dieser Cloud-Umgebung lehnte der Proxy Abfragen an `api.gleif.org`, `query.wikidata.org`, `overpass-api.de` und `api.ted.europa.eu` mit HTTP 403 ab; der SignalDesk-Quellencheck meldete alle sieben Adapter blockiert. Deshalb wurden keine realen Firmen oder Trefferquoten gemessen. Erforderlich: gezielte Netzwerkfreigabe für benötigte Quellen und für die nach Auswahl bekannten Firmen-Domains. Auch den technischen Abruf mit IP-Pinning prüfen: Eine Proxyfreigabe allein belegt dessen Funktion nicht. Keine Schutzmechanismen zum Erzwingen eines Tests abschalten.
2. **50–100 echte Firmen:** Eine unabhängige Referenzliste samt Name, Ort, überprüfter Homepage und Quelle erstellen. Präzision, Abdeckung, falsche Zuordnungen, technische Blockaden, brauchbare Hinweise und manuellen Aufwand getrennt messen. Die Liste vor der Auswertung festlegen. Ergebnis nicht aus fiktiven Tests ableiten.
3. **Homepage-Findung:** Die Zuordnung per Firmenname und geratenen Domains ist weiterhin begrenzt. Wikidata-LEI-Quellen sind vorhandene Grundlage; ein Suchadapter für abweichende Marken-Domains braucht Kosten-/Lizenzprüfung, Rate-Limits, Quellenangabe und manuelle Prüfung bei Zweifeln. Registergericht muss gegebenenfalls als getrenntes, belegtes Feld übernommen und migriert werden; keine Ableitung aus Ortsnamen.
4. **Profil-Funktionsumfang:** Neue Themen und frei wählbare Angebotszuordnung sind noch nicht über die Oberfläche anlegbar. Die gespeicherten Einstellungen steuern bewusst nicht alle technischen oder KI-Analysen. Falls das erweitert wird: historische Snapshots erhalten, Eingaben validieren und Änderungen migrationssicher machen.
5. **Rechercheauftrag:** Firmenberichte nutzen persistente Aufträge; Quickscan, Impressumsstapel, Website-Scorer und Kaufsignal-Scan haben weiterhin eigene Worker. Eine Vereinheitlichung benötigt Idempotenz- und Absturztests, klare Zustände und verlässliche Wiederaufnahme. Die bisherige Änderung wiederholt nur fehlgeschlagene Berichtsschritte.
6. **Recruiting:** Stellenhistorie erkennt noch keine zuverlässige Schließung oder inhaltliche Änderung; nicht mehr gefunden ist bei Teilausfall keine geschlossene Stelle. Veröffentlichungsdatum und Funddatum trennen. Dynamische ATS-Seiten können unvollständig sein.
7. **Abnahme:** Browser- und Integrationstests auf Windows sowie frische Installation, Update und Wiederherstellung einer Kopie realer Nutzerdaten wiederholen. Ergebnisse hier nicht als erledigt eintragen, bevor sie wirklich ausgeführt wurden.

## Validierung
Python 3.10–3.13 gemäß Repository; bevorzugt frische virtuelle Umgebung. Aus dem Quellverzeichnis:

```sh
python -m unittest discover -s tests -v
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/pfad/zu/chromium python -m unittest discover -s tests/e2e -v
python tools/build_release.py --out dist
```

In proxybasierten Testumgebungen muss das ausschließlich lokal simulierte `rebind.example` zusätzlich in `NO_PROXY` und `no_proxy` stehen; vorhandene Einträge erhalten. Playwright und Chromium sind optional für den Kern, aber nötig für Browser-Tests und grafische Website-Prüfungen. Für den Workflow gelten die mitgelieferten Lockdateien und Installationsvarianten. Keine Netzwerkfreigaben, TLS-Prüfungen oder Prüfsummen umgehen.

`tools/build_release.py` baut das Anwendungspaket mit Prüfsummen. Das Quellpaket für die Übergabe enthält zusätzlich Tests und Werkzeuge. Nach Änderungen neue Paketprüfsummen erzeugen und aus einem frisch entpackten Paket starten.

Im Quellverzeichnis erstellt `python tools/build_handoff.py --out dist` das vollständige Übergabepaket. Dieses enthält ein Dateimanifest und den Zeitstempel für reproduzierbare Builds. Ohne `.git` verwendet der Release-Builder das Manifest als Dateiliste; der Inhalt darf für die Weiterarbeit verändert werden. Neue Dateien müssen in die Dateiliste beziehungsweise in die expliziten Ergänzungen der Builder aufgenommen werden. Keine persönlichen Daten in das Paket aufnehmen.

In dieser Umgebung bestand die vollständige Regression mit 425 Tests und zwei optionalen Überspringungen. Der bestehende Chromium-Arbeitstagstest und ein Browser-Test zum Speichern und Wiederherstellen des Leistungsprofils bestanden; der Linux-Installationstest der Basisvariante bestand mit 15/15 Prüfungen einschließlich Sicherung und Wiederherstellung. Zusätzliche gezielte Tests nach einzelnen späteren Builder- und Identitätsänderungen ergänzen diese Ergebnisse. Diese Angaben ersetzen weder den genannten Live-Test noch einen Windows-Test.

## Nächste Funktionsideen
Siehe `docs/MASTERPLAN_SOLOSELBSTAENDIGE.md`; sie sind ein nachgeordnetes Vorhaben und kein Beleg dafür, dass sie bereits existieren.
