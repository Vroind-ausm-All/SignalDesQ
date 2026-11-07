# Bekannte Einschränkungen (Stand v1.19)

Der Masterplan verlangt für Sprint 6 „dokumentierte offene Einschränkungen“. Diese Liste nennt sie ehrlich, mit Grund und
Ausweg. Sie wird mit jeder Version aktualisiert.

## Installation und Betrieb
- **Python muss vorhanden sein.** Die Startdatei findet Python 3.10–3.13 und bietet unter Windows die Installation über winget an. Ein eigenständiges Paket mit eingebautem Python (z. B. PyInstaller) gibt es nicht.
  - Grund: Größe, Virenscanner-Fehlalarme bei gepackten Programmen, und Updates wären schwerer.
- **Chromium ist nicht über Prüfsummen gesperrt.** Die Python-Pakete stehen mit festen Versionen und Prüfsummen in `requirements-lock-*.txt`. Chromium für die Browser-Prüfung lädt dagegen `playwright install chromium` beim ersten Start. Playwright prüft diesen Download selbst; er braucht aber Internet, auch beim Offline-Paket.
  - Ausweg: Variante „basis“. Website-Recherche per HTTP funktioniert ohne Browser.
- **Nicht signiert:** Startdateien und ZIP tragen keine Signatur. Windows SmartScreen bzw. macOS Gatekeeper fragen beim ersten Start nach.
  - Ausweg: die Prüfsumme `SignalDesk-<version>.zip.sha256` vergleichen.
- **Nur x64 geprüft:** Windows on ARM und Linux auf ARM sind nicht in der automatischen Prüfung. Die Lockdateien enthalten zwar die Prüfsummen aller Plattformen, aber ungetestet.
- **macOS wird nicht automatisch geprüft.** Die Startdatei `.command` gibt es; Installation und Tests laufen in der CI nur unter Windows und Linux.
- **Einzelplatz:** Eine SQLite-Datei je Nutzer. Team-Betrieb mit Login ist vorbereitet (v1.8), aber nur hinter einem TLS-Proxy und ohne gleichzeitige Bearbeitung derselben Datensätze. Mandantenfähigkeit (PostgreSQL, Worker getrennt) ist laut Plan erst nach diesem Sprint dran.

## Sicherung und Wiederherstellung
- **Sicherungen liegen neben der Datenbank** (`backups/`). Gegen Festplattenausfall hilft nur eine zusätzliche Kopie auf einem anderen Datenträger. Darauf weist SignalDesk nach jeder Sicherung hin.
- **Wiederherstellen verweigert ältere Stände mit fehlenden festgeschriebenen Rechnungen (GoBD).**
  - Das ist Absicht. Ausweg: eine neuere Sicherung wählen.
  - Bei einer beschädigten aktuellen Datenbank greift die Sperre nicht, weil nichts mehr lesbar ist.
- **Verschlüsselte Sicherungen** (`.sdenc`) lassen sich nur mit der Variante „team“ (Paket `cryptography`) und dem Passwort zurückholen. Ohne Passwort ist die Sicherung verloren.

## Daten und Recherche
- **Alle Tests laufen mit fiktiven Websites und Attrappen der Quellen.** Die Live-Schnittstellen wurden zuletzt mit v1.14 geprüft. Formatänderungen der Quellen fallen erst im „Quellen-Check“ oder beim Nutzer auf.
- **Website-Vorschläge ohne Registernummer-Treffer brauchen deine Bestätigung** (Empfehlung A). Erst danach werden Firmendaten automatisch übertragen.
  - Ab v1.19 geht das in der Firmenakte, auch nach der Übernahme.
- **Impressumserkennung:** In 33 kuratierten Testseiten stimmen 100 % der Felder. Bei echten Seiten mit ungewöhnlichem Aufbau (Bild statt Text, nur per JavaScript, mehrere Firmen) bleiben Felder leer und werden als Grund angezeigt; erfunden wird nichts.
- **OpenStreetMap/Wikidata** haben keinen Offline-Ersatz. Für GLEIF gibt es den lokalen Katalog (v1.17).
- **Dubletten-Abgleich:** Bei sehr häufigen Namensanfängen (z. B. „Autohaus …“) werden riesige Vergleichsgruppen übersprungen, solange eine genauere passt. Tippfehler im ersten Wort solcher Namen können dann unerkannt bleiben und erscheinen als zwei Einträge.

## Offline-Modus
- Der Offline-Modus verhindert Abrufe durch SignalDesk. Er ist **keine Firewall**: Andere Programme und der Browser des Nutzers gehen weiter ins Netz.
- Die lokale KI (Ollama auf 127.0.0.1) bleibt erlaubt.
