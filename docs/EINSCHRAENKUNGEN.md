# Bekannte Einschränkungen (Stand 2.0.0-dev54)

**Ergänzung für 2.0.0-dev1:** Eine übereinstimmende Registernummer ohne Vergleich des Registergerichts gilt nur noch als Vorschlag. Die folgenden Aussagen dokumentieren den früheren Stand. Der aktuelle Entwicklungsstand und offene Prüfungen stehen in `V2_ENTWICKLUNGSSTAND.md` und `UEBERGABE_FABLE.md`.

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
- **Wikidata** hat keinen Offline-Ersatz. Für GLEIF gibt es den lokalen Katalog (v1.17), für OpenStreetMap den lokalen Auszug (2.0.0-dev7, siehe `OPENSTREETMAP_LOKAL.md`).
- **Dubletten-Abgleich:** Bei sehr häufigen Namensanfängen (z. B. „Autohaus …“) werden riesige Vergleichsgruppen übersprungen, solange eine genauere passt. Tippfehler im ersten Wort solcher Namen können dann unerkannt bleiben und erscheinen als zwei Einträge.

## Offline-Modus
- Der Offline-Modus verhindert Abrufe durch SignalDesk. Er ist **keine Firewall**: Andere Programme und der Browser des Nutzers gehen weiter ins Netz.
- Die lokale KI (Ollama auf 127.0.0.1) bleibt erlaubt.

## Kundenbewertung und Erreichbarkeit (2.0.0-dev2)
- **Die Bewertung ist ein Raster, keine Vorhersage.** Gewichte und Schwellen (A ab 70, B ab 45 Punkten) sind gesetzt, nicht aus echten Abschlüssen abgeleitet. Erst mit genug gewonnenen und verlorenen Chancen lässt sich prüfen, ob A-Firmen wirklich häufiger Kunden werden.
- **Branche oft nur geschätzt:** Ohne Angabe aus der Firmensuche wird die Branche aus dem Firmennamen abgeleitet. „Müller GmbH“ bleibt „unbekannt“.
- **Entfernung ist Luftlinie** zwischen den Gemeinden laut Ortsverzeichnis, keine Fahrzeit.
- **Geschäftszeiten der Firmen fehlen.** Der nächste Anrufversuch richtet sich nur nach den eigenen bisherigen Versuchen.
- **Zeitfenster eines Versuchs** ist die Uhrzeit des Eintrags, wenn du nichts anderes wählst. Wer abends nachträgt, sollte die Uhrzeit auswählen.
- **Ältere verlorene Leads** haben keinen Verlustgrund und erscheinen in der Übersicht als „ohne Grund“.

## Eigene Erreichbarkeit und Auslastung (2.0.0-dev3)
- **Kein Kalenderabgleich.** Terminvorschläge kennen nur deine eingestellten Zeiten und die in SignalDesk eingetragenen Termine. Private oder externe Termine musst du selbst ausschließen.
- **Keine Telefonanbindung.** Verpasste Anrufe trägst du selbst ein; SignalDesk liest keine Anrufliste.
- **Auslastung** rechnet mit verbleibenden Stunden, sobald du Zeiten erfasst (seit 2.0.0-dev5). Aufträge ohne erfasste Zeiten zählen weiter 8 Wochen lang mit der vollen Kalkulation und fallen danach heraus.
- **Feiertage** kennt SignalDesk nicht. Trag sie als Abwesenheit ein, sonst fallen Fristen und Terminvorschläge darauf.
- **Einträge im Eingang** können Namen und Telefonnummern enthalten. Erledigte Einträge werden nach der eingestellten Frist (Vorgabe 90 Tage) anonymisiert. Offene Einträge bleiben unbegrenzt stehen – bitte erledigen oder löschen.
- **Die Kontaktliste** zeigt nur Firmen in den Phasen Qualifiziert, Kontakt geprüft und Rückmeldung. Firmen in der Recherche erscheinen erst nach der Übergabe.

## Nachkalkulation (2.0.0-dev5)
- **Zeiten trägst du von Hand ein.** Es gibt keine Stoppuhr und keinen Import aus einer Zeiterfassung.
- **Je Auftrag, nicht je Leistung.** Welche Position eines Angebots länger gedauert hat, wird nicht unterschieden.
- **Aufträge ohne kalkulierte Stunden** (z. B. sehr alte Angebote) zeigen nur die erfassten Stunden, kein Soll/Ist.
- **Der Lernwert** („im Mittel X % mehr Zeit“) erscheint erst ab drei abgeschlossenen Aufträgen und bleibt bei wenigen Aufträgen eine grobe Zahl.
- **Zeiteinträge sind keine Buchhaltungsbelege** und nicht festgeschrieben; sie lassen sich ändern, solange der Auftrag offen ist.

## Firmensuche (Praxistest 70191, 2.0.0-dev6)
- **Handwerksbetriebe findet die Suche derzeit kaum** (1 von 56 in PLZ 70191). GLEIF enthält fast nur Kapitalgesellschaften mit LEI; OpenStreetMap ist die einzige Handwerksquelle und war am Testtag nicht verlässlich erreichbar. Einzelheiten: `PRAXISTEST_70191.md`.
- **Betriebe ohne Rechtsform im Namen** sind seit 2.0.0-dev9 standardmäßig dabei und gekennzeichnet (Entscheidung des Eigentümers, um die Zielgruppe zu vergrößern). Der Firmenname kann ein Personenname sein; für solche Leads gelten die Pflichten für personenbezogene Daten (Zweck, Information nach Art. 14 DSGVO, Löschfristen) besonders. SignalDesk kennzeichnet sie und legt seit 2.0.0-dev10 je Lead einen Nachweis mit Löschfrist (2 Jahre) und Art.-14-Hinweistext an. Ob die Rechtsgrundlage im Einzelfall trägt, prüft SignalDesk nicht. Abgelaufene Fristen werden angezeigt, gelöscht wird erst nach deiner Bestätigung.
- **PLZ-genaue Suche** gilt nur für „PLZ + nur dieser Ort“. Einträge ohne PLZ-Angabe aus GLEIF und Wikidata fallen dabei heraus; bei OpenStreetMap zählt das abgefragte PLZ-Gebiet.
- **Bei rund zwei Dritteln der GLEIF-Treffer bleibt die Branche unbekannt**, weil sie aus dem Firmennamen geschätzt wird.

## OpenStreetMap manuell (2.0.0-dev7)
- **Ohne eingelesene Datei liefert OpenStreetMap keine Treffer**, solange „online abfragen“ nicht angekreuzt ist. Das ist Absicht.
- **Der lokale Bestand veraltet.** Er ist so aktuell wie die eingelesene Datei.
- **Nicht an einem echten Geofabrik-Auszug geprüft** – der Download war in der Testumgebung nicht möglich. Geprüft gegen Dateien des offiziellen Werkzeugs `osmium`. PBF-Dateien mit anderer Kompression als zlib werden mit klarer Meldung abgelehnt.
- Weitere Grenzen (geschätzte PLZ, Lage der Gebäudeumrisse, ungeprüfte Öffnungszeiten) stehen in `OPENSTREETMAP_LOKAL.md`.

## Darstellung (2.0.0-dev11)

- Die Darstellung gilt für die ganze Installation, nicht je Nutzer: Im Team-Betrieb sehen alle dasselbe Theme. „Klassisch“ ist nicht pixelgleich mit dem Stand davor; Grautöne und Linien sind leicht vereinheitlicht, graue Nebentexte für bessere Lesbarkeit etwas dunkler. Durchscheinende Schatten sind im Dunkelmodus kaum sichtbar. Ausdrucke bleiben hell. Die Dichte „Kompakt“ blendet die Erklärtexte unter den Seitenüberschriften aus. Ohne Unterstützung für `color-mix()` (Browser vor etwa 2023) ist die Kopfleiste deckend statt leicht durchscheinend.

## Eingabeschutz und Bewertung (2.0.0-dev13)

- Der Schutz ungespeicherter Eingaben gilt im Lead-Dialog (Stammdaten, Aktivitätsprotokoll, Bedarfsanalyse, neue Ansprechperson). Andere Formulare – etwa Angebots- oder Rechnungseditor – haben ihn noch nicht.
- Zurückgehaltene Eingaben liegen nur im Arbeitsspeicher des Browserfensters. Nach einem Neuladen sind sie weg; der Browser warnt vorher.
- Die Passung ersetzt in Liste und Pipeline die alte Punktzahl. Der alte Lead-Fit wird weiter berechnet und ist unter „Stammdaten“ eingeklappt sichtbar; die Recherchepriorität unter „Firmen-Berichte“ ist ein eigener Wert und wird mit der neuen Navigation eingeordnet.
- Bestehende Firmen behalten Branche und Leistung, auch wenn diese früher automatisch vorbelegt wurden (z. B. „Conversion- & Web-Sprint“ bei übernommenen Suchtreffern). Das lässt sich unter „Stammdaten“ auf „noch keine Leistung gewählt“ zurücksetzen.

## Navigation und Adressen (2.0.0-dev14)

- Adressen gelten innerhalb einer SignalDesk-Installation; eine kopierte Adresse öffnet beim Empfänger nur dann dieselbe Firma, wenn er dieselbe Datenbank hat.
- Adressen gibt es für Ansichten, Firmen, Einstellungsabschnitte und die Filter der Firmenliste. Filter anderer Listen (Pipeline, Recherche, Buchhaltung) stehen noch nicht in der Adresse.
- Ein Firmen-Bericht hat noch keine eigene Adresse; nach dem Neuladen erscheint die Übersicht der Berichte.
- Die Firmenakte bleibt ein Dialog über der Liste. Ob sie eine eigene Seite wird, ist noch offen (Review U04).

## Fokusliste, Einstieg und Arbeitsansichten (2.0.0-dev15)

- Die Fokusliste ordnet nach festen Regeln (überfällige Zusagen, Termine, heute Zugesagtes, Nachfassen, dann neue Akquise). Externe Verpflichtungen außerhalb von SignalDesk kennt sie nicht; „nichts fällig“ heißt nur, dass in SignalDesk nichts fällig ist.
- „Letzter Kontakt“ zählt dokumentierte Gespräche, Anfragen, Angebote, Einwände, Abschlüsse, Anrufe und erledigte Termine – keine internen Notizen und keine E-Mails, die nicht in SignalDesk protokolliert wurden.
- Gespeicherte Ansichten gelten für die ganze Installation (wie die Darstellung). Die Wahl zusätzlicher Spalten merkt sich nur der jeweilige Browser.
- Stapelaktionen auf gefilterten Firmen (Review U09) gibt es noch nicht.
- „Erste Schritte“ prüft, ob Preise, Zielkunden (Region und Branche) und Zeiten gespeichert sind – nicht, ob die Werte stimmen.

## Zentraler Leistungskatalog (2.0.0-dev16)

- In den Einstellungen änderbar sind Aufwand, enthaltene Fremdkosten, fester Preis und Korrekturschleifen je Leistung. Titel, Beschreibungen, Ausschlüsse und die Zusammenstellung der Vorlagen stehen im Code; eigene Leistungen anlegen oder Leistungen ausblenden geht noch nicht.
- Die früheren Paketpreise weichen von den Baukastenpreisen ab (siehe `LEISTUNGSKATALOG.md`). Seit dev16 gilt überall der Baukastenpreis – ob er deinen tatsächlichen Preisen entspricht, prüfst du selbst.
- Ein leeres Feld „Korrekturschleifen“ heißt „Startwert“. Wo der Katalog einen Startwert hat (Logo, Texte), lässt sich „nicht festgelegt“ nicht wählen – nur eine Zahl ab 0.
- „Vor dem Versand klären“ ist eine Erinnerung ohne Abhaken; was geklärt wurde, wird nicht gespeichert (folgt mit den Briefings, M14).
- Paketempfehlungen und Website-Bewertung verweisen auf Vorlagen, nicht auf einzelne Leistungen; die Verbindung Befund → Leistung ist M32.
- (bis dev16) Der Hinweis „Dieses Dokument ist ein Angebotsentwurf“ stand in jedem Kundenexport – seit dev17 gibt es die freigegebene Versandfassung.

## Versandfassung, Versand, Zusage, Projektstart (2.0.0-dev17)

- Die Versandfassung ist ein Markdown-Dokument. Ein gestaltetes PDF in deinem Erscheinungsbild erstellst du weiterhin außerhalb von SignalDesk; die Stand-Kennung im Dateinamen hilft, Mail, PDF und gespeicherten Stand zuzuordnen.
- Die vier Prüfpunkte vor der Freigabe sind Selbstauskünfte; SignalDesk prüft automatisch nur Steuerstatus, Bedarf, Kontaktsperre, Bindefrist und interne Werte im Dokument.
- Ein freigegebenes Angebot lässt sich nicht mehr ändern. Für eine geänderte Fassung erstellst du ein neues Angebot; eine Revision mit sichtbarem Vorgänger ist M15.
- Dokumentierter Versand, Zusage oder Absage lassen sich nicht zurücknehmen. Bei einem Irrtum: Notiz in der Firmenakte und ggf. ein neues Angebot.
- Die Wiedervorlage nach dem Versand ist weiterhin fest auf 7 Kalendertage gesetzt (M16).
- Startaufgaben sind gewöhnliche Aufgaben mit Angebotsnummer im Titel; einen Projektstatus („wartet auf …“, „bereit“) und einen Projektkompass gibt es noch nicht (M38).
- Ältere, bereits als versendet oder angenommen markierte Angebote zeigen „vor 2.0.0-dev17, ohne Stand“; sie lassen sich nachträglich freigeben.
- Die Profilnähe der Website-Bewertung (Branche, Größe, Leistungsbezug) ist eine andere Zahl als die Passung A/B/C der Firmenakte. Beide bleiben bewusst getrennt.

## Verkaufschancen je Firma, Teil 1 (2.0.0-dev18)

- (bis dev18) Bedarfsanalyse und Freigabe galten für die ganze Firma – seit dev19 je Chance.
- (bis dev18) Pipeline und Heute zeigten nur Firmen – seit dev19 auch einzelne Chancen; die Firmenliste zeigt weiterhin Firmen.
- Paketempfehlungen, Website-Bewertung und Firmen-Bericht beziehen sich auf die Firma, nicht auf eine Chance.
- Eine automatisch mit dem ersten Angebot entstandene Chance hebt die Firmenphase mindestens auf „Rückmeldung“.
- Firmentermine ohne Chance bleiben möglich, solange keine Chance offen ist. Bei mehreren offenen Chancen muss ein Termin oder Angebot einer Chance zugeordnet werden.
- Aufgaben sind noch keiner Chance zugeordnet; die Startaufgaben nach einer Zusage tragen die Angebotsnummer im Titel.

## Bedarf und Freigabe je Chance, Pipeline und Heute (2.0.0-dev19)

- Die erste Chance einer Firma nutzt weiterhin die Bedarfsanalyse der Firma; ihre Freigabe steht im Überblick der Akte, die Freigabe weiterer Chancen direkt an der Chance.
- Die Freigabe an der Chance nimmt eine Leistung auf; weitere Leistungen ergänzt du im Angebot.
- Paketabgleich („Pakete abgleichen“), Website-Bewertung und Firmen-Bericht beziehen sich weiterhin auf die Firma.
- In der Pipeline lassen sich Chancen-Karten über die Phasenauswahl verschieben, nicht per Ziehen.
- Die Firmenliste und ihre Arbeitsansicht „Heute fällig“ zählen die nächsten Schritte der Firma, nicht die einzelner Chancen; in „Heute“ und der Fokusliste stehen beide.
- Aufgaben sind weiterhin keiner Chance zugeordnet.

## Briefing je Chance (2.0.0-dev20)

- Die Fragen sind feste Vorschläge aus dem Onboarding-Leitfaden und dem Bewertungsmodell; eigene Fragen lassen sich noch nicht ergänzen.
- Unbeantwortete Fragen blockieren die Versandfreigabe nicht, sie erscheinen als Hinweis. Ob ein Angebot ohne vollständiges Briefing verschickt wird, entscheidest du.
- Die Voraussetzungen im Angebot sind auf 1.000 Zeichen begrenzt; lange Briefings werden gekürzt übernommen.
- Antworten sind Arbeitsnotizen. Was davon im Angebot steht, sieht der Kunde – vor dem Übernehmen prüfen, ob eine Angabe dort hingehört.
- Materialien und Zugänge werden nur als Text erfasst (keine Dateiablage, keine Passwortfelder); die Material- und Entscheidungsliste ist M39.

## Angebotsrevisionen (2.0.0-dev21)

- Eine Revision wird immer aus der neuesten Fassung erstellt; Verzweigungen (zwei Revisionen desselben Vorgängers) gibt es bewusst nicht.
- Bei älteren Angeboten (vor dev21) wird der Bauplan aus dem Kundendokument rekonstruiert. Frei geänderte Positionstitel, Anreise-Kilometer und Minuten werden dabei nicht vollständig übernommen – vor dem Speichern prüfen.
- Die Änderungsliste vergleicht Positionen nach Leistung und Titel. Wird eine Position umbenannt, erscheint sie als „entfällt“ und „neu“.

## Optionale Positionen (2.0.0-dev22)

- Eine optionale Position steht mit Preis im Angebot, zählt aber weder zum Festpreis noch zu Laufzeit, Zahlungsplan, Abschlagsrechnung oder Rechnung „voll“. Wählt der Kunde sie, wird das Angebot als Revision mit fest übernommener Position neu gefasst.
- Varianten zur Wahl (Basis/Standard/Erweitert nebeneinander mit eigener Gesamtsumme) gibt es nicht. Abbilden lässt sich das über optionale Positionen oder getrennte Fassungen.
- Mindestens eine Position muss fest im Angebot stehen.
- Interne Stunden, Fremdkosten und der effektive Stundenlohn des Angebots zählen nur feste Positionen; der Hinweis zum Mindestverdienst erscheint weiterhin je Position, auch für optionale.

## Nachfassen von Angeboten (2.0.0-dev23)

- Das Nachfassen mit Frist, Anlass und Ergebnis gilt für versendete Angebote. Nachfassen nach Erstkontakt oder Rückrufen läuft weiter über Anrufprotokoll und Aufgaben.
- Ältere Angebote (vor dev23) haben keine verknüpfte Nachfassaufgabe. Für sie gilt weiterhin die feste Wiedervorlage 7 Tage nach der letzten Änderung.
- Eine Nachfassaufgabe, die in der allgemeinen Aufgabenliste einfach abgehakt wird, hat kein Ergebnis. Das Ergebnis lässt sich nur am Angebot festhalten.
- „Zusage angekündigt“ und „Absage angekündigt“ ändern den Angebotsstatus nicht. Die Entscheidung dokumentierst du weiterhin bewusst am Angebot.
- Längste Frist: 120 Tage. Längere Pausen gehören als Wiedervorlage an die Chance.

## Übergabe und Abnahme (2.0.0-dev24)

- Das Abnahmeprotokoll ist eine Markdown-Datei zum Ausdrucken oder Weiterverarbeiten, kein gestaltetes PDF und keine elektronische Unterschrift.
- Ob eine Abnahme rechtlich wirksam ist (z. B. stillschweigende Abnahme, Fristen nach Werkvertragsrecht), prüft SignalDesk nicht. Die Formulierung im Protokoll ist ein Vorschlag, keine Rechtsberatung.
- Die Schlussrechnung wird nicht automatisch erstellt; SignalDesk weist nur darauf hin, wenn der Zahlungsplan „nach Abnahme“ vorsieht.
- Dokumentierte Übergaben und Abnahmen lassen sich nicht zurücknehmen. Nach der Abnahme bleiben Liefergegenstände und Kriterien unverändert; neue Arbeit ist ein Restpunkt oder ein Zusatzauftrag.
- Liefergegenstände kommen aus den Katalogtexten des Angebots. Bei älteren Angeboten ohne diese Angaben werden die festen Positionen übernommen.

## Zusatzaufträge (2.0.0-dev25)

- Ein Zusatzauftrag ergänzt einen angenommenen Auftrag. Weniger Leistung oder ein Teilstorno nach der Zusage bildet SignalDesk nicht ab; das bitte als Notiz festhalten und bei der Rechnung berücksichtigen.
- Jeder angenommene Zusatzauftrag hat eigene Übergabe, Abnahme, Nachkalkulation und Rechnung. Eine gemeinsame Schlussrechnung über Auftrag und Zusatzaufträge gibt es nicht.
- Zusatzaufträge zu Zusatzaufträgen gibt es nicht: Sie beziehen sich immer auf den ursprünglichen Auftrag.
- Vor der Zusage wird ein Angebot überarbeitet, nicht ergänzt.

## Bestandskunden und Betreuung (2.0.0-dev26)

- Betreuung sind die monatlichen Positionen eines angenommenen Angebots. Beginn ist das Datum der Zusage; du kannst ihn anpassen, solange kein abgerechneter Monat herausfällt.
- Abgerechnet wird je Kalendermonat, immer der volle Monatsbetrag. Anteilige Monate, Quartals- oder Jahresabrechnung und automatische Preisanpassungen gibt es nicht.
- Eine Preisänderung der laufenden Betreuung ist ein neues Angebot (bzw. Zusatzauftrag). Die alte Betreuung bitte zum Stichtag beenden.
- Monatsrechnungen aus der Zeit vor dev26 haben keinen Leistungszeitraum. Für die offenen Monate zählen sie deshalb nicht; bitte die Laufzeit so setzen, dass bereits abgerechnete Monate davor liegen.
- Rechnungen entstehen weiterhin nur als Entwurf auf deinen Klick; „Heute“ erinnert an nicht abgerechnete Monate.

## Zeiten je Leistung (2.0.0-dev27)

- Die Zuordnung zu einer Position ist freiwillig. Zeiten ohne Position zählen zum Auftrag, aber nicht zur Auswertung je Leistung.
- Die Aussage je Leistung beruht nur auf abgeschlossenen Aufträgen mit zugeordneten Zeiten. Unter drei Stichproben gibt es keine Aussage; auch drei Aufträge sind eine kleine Stichprobe – die Spanne steht deshalb immer dabei.
- SignalDesk ändert Zeitansätze im Katalog nie selbst. Der Vorschlag verweist auf „Einstellungen → Leistungen & Preise“.
- Ältere Zeiteinträge (vor dev27) haben keine Position.

## Projektkompass (2.0.0-dev28)

- Die Voraussetzungen werden beim ersten Öffnen aus dem Angebot und den offenen Briefing-Punkten der Chance übernommen. Spätere Briefing-Änderungen kommen nicht automatisch nach; bitte selbst ergänzen.
- Materialien werden nur als Text erfasst, nicht als Datei. Es gibt keine Dateiablage.
- Die Erkennung von Zugangsdaten ist eine Schutzregel für typische Eingaben („Passwort:“, „Login =“, Token-Muster), keine Garantie. Bitte grundsätzlich keine Zugangsdaten eintragen.
- Der Startstatus „gestartet“ lässt sich nicht zurücknehmen; offene Punkte bleiben danach sichtbar.

## Nachrichtenvorlagen (2.0.0-dev29)

- Nur die festen Platzhalter sind erlaubt; Bedingungen, Schleifen oder Serienbriefe an mehrere Firmen gibt es nicht.
- Die Anrede „Frau/Herr“ erscheint nur, wenn sie an der Person hinterlegt ist. Titel (Dr., Prof.) werden nicht abgebildet; bei Bedarf den Text der Vorlage anpassen.
- Die Vorschau prüft Sperren der Firma und die Einschränkungen „keine E-Mails“, „nur Post“ und „Widerspruch“ der gewählten Person. Ob eine Nachricht werblich ist und eine Einwilligung braucht, prüfst du weiterhin selbst.
- SignalDesk versendet nichts. Die Endfassung wird kopiert und außerhalb verschickt; der Versand eines Angebots wird wie bisher am Angebot dokumentiert.

## Kurzbericht für den Kunden (2.0.0-dev30)

- Der Bericht übernimmt Beobachtung, Fundstelle und Frage so, wie sie beim Befund stehen. Formulierungen bitte vor der Weitergabe selbst lesen; SignalDesk glättet keine Texte.
- Screenshots werden nicht eingebunden (nur Markdown, kein gestaltetes PDF).
- Höchstens zwölf Befunde je Bericht. Die Einordnung am Ende ist ein Textvorschlag, keine Rechtsberatung.

## Grundlage je Position (2.0.0-dev33)

- Ein Befund belegt eine Position, wenn sein Paketvorschlag diese Leistung enthält (Zuordnung über die Vorlagen des Katalogs). Befunde ohne Paketvorschlag zählen nicht.
- Positionen ohne Grundlage blockieren den Versand nicht; sie erscheinen als Hinweis. Ob du sie begründest, streichst oder bewusst anbietest, entscheidest du.
- Die Grundlage wird beim Öffnen neu berechnet, nicht beim Erstellen gespeichert. Wird ein Befund später verworfen, ändert sich die Anzeige.

## Globale Suche (2.0.0-dev34)

- Durchsucht werden Firmenname, Firmierung, Website, Titel von Chancen, Angebotsnummer und Projekttitel sowie Rechnungsnummern. Personen, Notizen und Gesprächsprotokolle bewusst nicht.
- Die Suche ist eine einfache Teilwort-Suche ohne Tippfehler-Toleranz; je Gruppe höchstens acht Treffer.
- Ein Rechnungstreffer wechselt in die Rechnungsliste; die Rechnung selbst öffnest du dort.

## Hintergrundaufträge (2.0.0-dev35)

- Website-Bewertung, Karriereseiten-Scan (dev35), KI-Analyse, Schnellprüfung und Suche nach öffentlichen Ansprechpartnern (dev36) setzen nach einem Neustart fort. Läufe, die vor dem Update begonnen wurden, werden einmalig als „durch Neustart unterbrochen“ gekennzeichnet. Die Impressum-Sammelprüfung setzt seit dev39 nach einem Neustart automatisch fort – außer du hattest sie pausiert oder SignalDesk ist offline.
- Ein fortgesetzter Schritt beginnt von vorn (die Seite wird erneut gelesen); halbfertige Zwischenergebnisse werden nicht übernommen.

## Hinweise statt Urteile in der Website-Bewertung (2.0.0-dev37)

- Vier Faustregeln (Überschriftenzählung, Zahl der Schriftfamilien, Jahreszahl im Fußbereich, Zahl der Navigationslinks) liefern nur noch Hinweise. Die übrigen Rubriken beruhen auf Messungen (z. B. Ladezeit, defekte Links, Darstellung auf dem Smartphone) und bleiben „auffällig“, wenn die Schwelle überschritten ist – ihre Schwellen sind weiterhin Vorgaben, keine fachlich geprüften Grenzwerte.
- Bewertungen vor dev37 (Version 2.0) und danach (2.1) werden nicht miteinander verglichen; nach einer neuen Bewertung steht der Vergleich wieder zur Verfügung.

## Firmenakte als eigene Seite (2.0.0-dev40)

- Die Akte ersetzt beim Öffnen die aktuelle Ansicht; zwei Akten nebeneinander gibt es nicht.
- Lesezeichen mit der alten Form `?firma=ID` funktionieren weiter und öffnen die Akte als Seite.
- Escape schließt die Akte weiterhin (mit Rückfrage bei ungespeicherten Änderungen).

## Kalender-Abo (2.0.0-dev41)

- Die Abo-Adresse zeigt auf diesen Rechner (127.0.0.1). Kalenderprogramme auf demselben Rechner können sie abonnieren; Web-Kalender im Internet (z. B. Google im Browser) können sie nicht abrufen – dort die .ics-Datei importieren oder später CalDAV nutzen.
- Das Abo ist nur lesend; Änderungen im Kalender kommen nicht zurück.
- Wer die Abo-Adresse kennt, sieht Titel, Firma, Zeit und Ort deiner Termine. Bei Verdacht einen neuen Schlüssel erzeugen.

## Kalender-Abgleich über CalDAV (2.0.0-dev42)

- Geprüft nur gegen einen nachgebauten CalDAV-Server in den Tests, **noch nicht an einem echten Anbieter** (Google, iCloud, mailbox.org, IONOS, Nextcloud …). Abweichungen einzelner Server sind möglich; die Meldungen nennen dann den Status.
- Gebraucht wird die Adresse **eines einzelnen Kalenders**; eine automatische Suche nach Kalendern des Kontos gibt es nicht.
- Nur Anmeldung mit Benutzername und (App-)Passwort. Anbieter, die nur OAuth erlauben, gehen nicht.
- Der Abgleich läuft nur auf Knopfdruck („Jetzt abgleichen“), nicht automatisch. Ist er älter als 24 Stunden, erscheint ein Hinweis.
- Aus dem Kalender werden nur belegte Zeiten der nächsten 60 Tage gelesen. Wiederkehrende Termine (RRULE) zählen nur mit ihrem Eintrag, den der Server liefert – Server, die Wiederholungen nicht auflösen, melden nur das erste Vorkommen.
- Zeitzonen: Angaben mit Zeitzone werden als Ortszeit dieses Rechners verstanden (passend für Termine in Deutschland), UTC-Angaben werden umgerechnet.
- Termine, die im Kalender verschoben werden, kommen nicht in SignalDesk zurück; beim nächsten Abgleich gilt wieder der Stand aus SignalDesk.
- „Merken“ (seit 2.0.0-dev55, SDQ-004) legt das Passwort nur im Passwortspeicher des Betriebssystems ab: Paket `keyring`, falls installiert; sonst unter Windows DPAPI (verschlüsselt, an dein Windows-Konto gebunden, Datei `zugangsdaten.dpapi.json`), unter Linux `secret-tool`. Auf macOS ohne `keyring` und auf Linux ohne Schlüsselbund gibt es kein „merken“ – das Passwort gilt dann bis zum Neustart. Ein Klartext-Eintrag in `zugangsdaten.json` aus früheren Versionen wird in den sicheren Speicher übernommen; ohne sicheren Speicher wird er weiter gelesen, aber nie neu geschrieben, und verschwindet, sobald du das Passwort neu eingibst oder „vergessen“ wählst. Der Windows- und der Linux-Weg sind automatisch getestet (Windows in der CI), der macOS-Schlüsselbund über `keyring` nicht.

## Entwürfe ins Postfach über IMAP (2.0.0-dev43)

- Geprüft nur gegen einen nachgebauten IMAP-Server in den Tests, **noch nicht an einem echten Anbieter**.
- Nur Anmeldung mit Benutzername und (App-)Passwort über SSL (Port 993). STARTTLS (Port 143) und OAuth-only-Anbieter gehen nicht.
- Der Entwürfe-Ordner wird über die Markierung „Drafts“ oder übliche Namen gefunden. Fehlt beides, muss im Mailprogramm einmal ein Entwurf gespeichert werden.
- Der Entwurf ist reiner Text (keine Signatur mit Bild, kein Anhang); das Angebot als PDF im Mailprogramm anhängen.
- Als Empfänger wird nur die geschäftliche E-Mail-Adresse der Firma vorausgefüllt; eine Person als Empfänger trägst du im Mailprogramm ein.
- Ein Entwurf kann mehrfach abgelegt werden (z. B. nach dem Löschen im Mailprogramm); SignalDesk prüft nicht, ob er im Postfach noch liegt.

## Firmensuche mit OpenStreetMap-Auszug (2.0.0-dev44)

- Betriebe ohne Rechtsform im Namen (z. B. „Elektro Müller“) werden nur übernommen, wenn „auch Betriebe ohne Rechtsform“ angehakt ist. Bei Handwerk ist das der größte Teil. Die Ergebniszeile nennt jetzt, wie viele aus welchem Grund ausgefiltert wurden.
- Die Website-Suche läuft nur für übernommene neue Treffer (höchstens 100 je Suche). Ausgefilterte und schon bekannte Betriebe werden nicht gesucht.
- Die Website-Suche rät Domains aus Name und Ort, nutzt seit dev66 zusätzlich die E-Mail-Domain aus OpenStreetMap und prüft das Impressum. Betriebe mit ganz anderem Domainnamen (Abkürzung, Fantasiename) ohne E-Mail-Angabe in der Quelle findet sie nicht – dort hilft nur „Website eintragen“. E-Mail-Domain und Telefon gibt es nur aus OpenStreetMap, nicht aus GLEIF, Wikidata oder TED.
- Der Abgleich über Anschrift und Telefon (dev66) ist nur an fiktiven Firmen geprüft, nicht an deiner Referenzliste gemessen. Der Telefon-Prüfwert ist eine Pseudonymisierung, keine Anonymisierung.
- Firmen-Bericht ohne Website: Ohne gefundene oder bestätigte Website laufen nur Website-Suche und Paketabgleich; die übrigen Schritte stehen auf „übersprungen“.
- Wie viele Betriebe im Auszug eine Website eingetragen haben, hängt von OpenStreetMap ab; im Handwerk ist das oft nur ein kleiner Teil. Das ist noch nicht an deinem Auszug gemessen (M21).

## Recherchepilot – Stichprobe von Hand prüfen (2.0.0-dev45)

- Die Stichprobe kommt aus den **übernommenen** Treffern. Ausgefilterte Betriebe sind nicht darin – wie viele die Suche verpasst, misst sie nicht. Dafür die Gründe in der Ergebniszeile ansehen (dev44).
- Die Quoten sind so gut wie deine Angaben. „unklar“ zählt nirgends mit; unter 30 Angaben je Quote gibt es einen Hinweis.
- „Abdeckung Websites“ heißt: Unter den Zielbetrieben, die laut deiner Prüfung eine Website haben, zeigte SignalDesk die richtige an.

## Fachreview und Kalibrierung (2.0.0-dev46)

- Die Kalibrierung vergleicht dein Urteil mit der automatischen Bewertung. Ob zwei Prüfer untereinander übereinstimmen, wird noch nicht ausgewertet.
- Markiert werden Rubriken unter 70 % Übereinstimmung erst ab 5 Urteilen; darunter ist es nur ein erster Eindruck.
- Ist die automatische Bewertung „unbekannt“ und du urteilst eindeutig, zählt das als Abweichung – das zeigt Lücken der Messung, nicht unbedingt Fehler.
- Abgeschlossene Reviews lassen sich nicht ändern oder löschen; bei einem Irrtum ein neues Review anlegen.

## Erlebnisstudien und „Was du lernst“ (2.0.0-dev47)

- SignalDesk kann nicht prüfen, ob Angaben wirklich von einer Testperson stammen; die Bestätigung je Sitzung ist deine Zusage. Unbestätigte Sitzungen zählen nirgends.
- Kleine Studien (unter 5 Sitzungen) zeigen Probleme, aber keine belastbaren Quoten – das steht jeweils dabei.
- Vorher/Nachher vergleicht verschiedene Testpersonen und nur Studien derselben Firma; Unterschiede können auch an den Personen liegen.
- Die Projektart ist die Leistung mit den meisten kalkulierten Stunden im Angebot – gemischte Aufträge landen nur in einer Gruppe.
- Aussagen in „Was du lernst“ erst ab 3 Fällen; das sind Richtungen, keine gesicherten Zusammenhänge.

## UI-Baukasten und mobile Navigation (2.0.0-dev49)

- Die Bausteine aus [UI_BAUKASTEN.md](UI_BAUKASTEN.md) stehen in style.css bereit, die vorhandenen Ansichten nutzen sie aber noch nicht. Sie werden schrittweise umgestellt (Etappe E, Schritte 2–6); bis dahin sehen die Ansichten aus wie in dev48 und erreichen die Messwerte des Zielbilds nicht.
- Die Schublade mit den sechs Bereichen gibt es nur bis 520 px Breite. Zwischen 521 und 790 px bleibt die schmale Seitenleiste mit Symbolen wie bisher.
- Bei schmaler Breite zeigt die Kopfzeile nur den Bereich (nicht die Ansicht) und „Neuer Lead“ nur als „＋“; die Ansicht steht in den Reitern darunter.
- Geprüft in Chromium (Playwright) bei 390 × 844 und 1280 × 720; auf echten Smartphones und anderen Browsern nicht getestet.

## Firmen und Heute im neuen Aufbau (2.0.0-dev50)

- Nur Rahmen, Firmenliste und Heute sind auf den Baukasten umgestellt. Finden, Pipeline, Datenpflege, Aufgaben, Kontakt & Termine, Angebote, Abrechnen, Einstellungen und die Firmenakte haben noch den alten Aufbau (Schritte 3–6) und dort steht weiter „Lead“ (z. B. „Neuer Lead“ als Titel des Anlegens in der Akte, „Lead gespeichert“).
- „Erledigt“ in „Als Nächstes“ gibt es nur für Aufgaben und Eingänge/Rückrufe – nur dafür hat SignalDesk ein Abhaken. Nächste Schritte einer Firma, Termine und Angebote erledigst du wie bisher in der Akte bzw. im Angebot; dort steht in der Zeile das Ziel („Angebot öffnen“, „Anruf dokumentieren“) oder nichts, wenn die Zeile ohnehin die Akte öffnet.
- „Letzter Kontakt“ ist in der Firmenliste keine Standardspalte mehr, sondern unter „Spalten ▾“ zuschaltbar (gemerkt in diesem Browser).
- Bis 520 px Breite zeigen beide Listen nur Was · Fällig · ›; nächster Schritt, Phase, Passung und „Erledigt“ stehen dann in der Akte bzw. unter „Heute → Aufgaben“.
- Die Klappzeilen auf „Heute“ sind nach jedem Neuladen zu; welche du offen hattest, merkt sich SignalDesk nicht.
- Hell/Dunkel wechselst du nur noch unter Einstellungen → Darstellung (der Umschalter in der Kopfzeile entfiel).
- Geprüft in Chromium (Playwright) bei 1280 × 720 und 390 × 844; nicht auf echten Geräten und nicht in anderen Browsern.

## Finden im neuen Aufbau (2.0.0-dev51)

- Umgestellt sind „Sichten“ und „Neue Suche“. Die Unteransichten von „Analysen“ (Recherche & Berichte, URL-Recherche, Website-Scoring, Kaufsignale, Bericht) und „Import“ haben noch den alten Aufbau; neu ist dort nur die Reiterzeile bzw. der Abschnitt „Firmenliste importieren“. Auch „Einstellungen → Datenquellen“ steht im alten Aufbau der Einstellungen (Umbau in Schritt 5).
- „Sichten“ hat kein „Spalten ▾“ (das Zielbild zeigt es); Adresse, Kontakt und Quellen-Links stehen in der aufgeklappten Zeile. Welche Zeilen aufgeklappt waren, merkt sich SignalDesk nicht über ein Neuladen hinaus.
- Bis 520 px zeigt „Sichten“ nur Firma · Entfernung · ›; Website-Status, Quelle und „Übernehmen“ stehen dann in der aufgeklappten Zeile.
- Die Voreinstellung unter „Wen suchst du?“ wird nicht eigens gespeichert, sondern aus Quellen, „ohne Rechtsform“, Website-Suche und Budget abgelesen. Seit dev51 merkt sich der Browser bei einer gestarteten Suche auch Quellen, „ohne Rechtsform“ und „nur operative“; nach dem Neuladen gelten also die Quellen der letzten Suche, nicht mehr immer alle vier.
- Ob „Finden“ in der Seitenleiste „Sichten“ oder „Neue Suche“ öffnet, entscheidet die zuletzt geladene Zahl offener Treffer (sie wird bei jedem Laden der Treffer und beim Start aktualisiert); `#/finden` fragt jedes Mal neu.
- Der Zähler am Reiter „Analysen“ zählt wie bisher alle Punkte der Prüfliste aus „Recherche & Berichte“ – dazu gehören auch offene Treffer der Firmensuche, die unter „Sichten“ stehen.
- Einige Meldungen des Servers sagen weiter „Lead“ (z. B. Fehlermeldungen beim Übernehmen, „Lead-Finder-Treffer prüfen“ in der Prüfliste); die Oberfläche von Finden sagt „Firma“.
- Geprüft in Chromium (Playwright) bei 1280 × 720 und 390 × 844; nicht auf echten Geräten und nicht in anderen Browsern.


## Angebote im neuen Aufbau (2.0.0-dev52)

- Umgestellt sind die Angebotsliste, der Seitenkopf und die Reiter des geöffneten Angebots, die Kontextspalte sowie die Seiten „Aufträge & Betreuung“ und „Auswertung“. Die Arbeitsschritte im geöffneten Angebot (Freigabe, Versand, Nachfassen, Entscheidung, Projektstart, Kick-off, Übergabe), das Formular des Editors, die Karten der Nachkalkulation und die Bestandskunden stehen noch in ihren bisherigen Bausteinen – nur geordnet und eingebettet.
- „Nächster Schritt“ und „Fällig“ in der Liste werden aus vorhandenen Daten abgeleitet: Freigabe und Prüfpunkte (je offenem Entwurf eine Abfrage), das früheste offene Nachfassen, Kick-off- und Abnahmestand, Betreuung und „berechnet“. Für angenommene Angebote steht keine Fälligkeit, weil der Kick-off keine eigene Frist hat. „Rechnung erstellen“ erscheint, solange zu einem abgenommenen Auftrag gar keine Rechnung existiert – ob alle Teilrechnungen geschrieben sind, prüft die Liste nicht.
- Die Liste zeigt wie bisher die letzten 100 Angebote. Die Liste hat kein „Spalten ▾“ (das Zielbild zeigt es); Spalten sind fest.
- Die Hauptaktion im Kopf des geöffneten Angebots springt nur zum passenden Arbeitsschritt (und setzt den Fokus dorthin); freigeben, versenden oder dokumentieren musst du dort wie bisher selbst. Nach der Annahme wechselt sie zwischen Projektstart, Kick-off, Übergabe, Abnahme und Rechnung.
- „Ablauf“ zeigt „Freigabe“ als aktuelle Phase, sobald alle Prüfpunkte erfüllt sind, sonst „Entwurf“ (bzw. „Bedarf“, solange der Bedarf nicht bestätigt ist).
- „＋ Neues Angebot“ beginnt mit einem leeren Editor – außer der Editor enthält noch Positionen, die nicht gespeichert sind; dann geht es dort weiter. Ein Neuladen im Editor (`#/angebote?neu=1`) beginnt leer; ungespeicherte Positionen gehen dabei wie bisher verloren.
- Der Verlauf eines Angebots setzt sich aus vorhandenen Zeitpunkten zusammen (erstellt, freigegeben, versendet, Nachfassen, Entscheidung, Projektstart, Übergabe, Abnahme, Nachrichtenentwürfe mit Bezug auf das Angebot). Statuswechsel aus der Zeit vor dev17 haben kein Datum und erscheinen nicht.
- Seit dev52 behalten Erlebnisstudie, Fachreview und Stichprobe Eingaben in anderen Feldern, wenn nach einer Auswahl neu gezeichnet wird. Geprüft mit künstlich verzögerter Antwort; ein Feld, das man nach dem Neuzeichnen ohne weitere Eingabe verlässt, speichert über ein nachgereichtes „change“.
- Geprüft in Chromium (Playwright) bei 1280 × 720 und 390 × 844; nicht auf echten Geräten und nicht in anderen Browsern.

## Einstellungen und Abrechnen im neuen Aufbau (2.0.0-dev53)

- Umgestellt sind Rahmen und Aufbau: Abschnittsliste, Seitenkopf, Suche, Rechnungsliste, Reiter und Klappzeilen. Die Formulare in den Abschnitten (Stammdaten, Kalkulationsgrundlagen, Zielkundenprofil, Kalender, Sicherung …), das KI-Studio, das Playbook, der Rechnungseditor, Ausgaben, Auswertung und Steuer & Export stehen noch in ihren bisherigen Bausteinen (Karten mit Überschrift) – nur geordnet und eingebettet.
- Die Warnung „letzte Sicherung alt“ erscheint ab 7 Tagen; diese Grenze ist eine Festlegung der Oberfläche, keine gesetzliche Frist. Gezählt wird die jüngste Datei im Sicherungsordner (auch eine automatische vor einer Wiederherstellung).
- Den zuletzt benutzten Abschnitt merkt sich nur dieser Browser. Bis 1000 px Breite zeigt `#/einstellungen` die Abschnittsliste; der Abschnitt steht dann allein mit „← Einstellungen“ (das Zielbild nennt nur „schmal“, die Grenze 1000 px ist gewählt, weil Liste und Inhalt darunter nicht mehr nebeneinander passen).
- Der Eingabeschutz beim Abschnittswechsel gilt für die Formulare, die erst mit „Speichern“ gelten (Stammdaten, Kalkulationsgrundlagen, Leistungsprofil, Zielkundenprofil, Gewichte & Fristen, Deine Zeiten, CalDAV, IMAP, Website-Abruf). Werte im Leistungskatalog (je Zeile „Speichern“), Benutzerverwaltung, Passwortwechsel und das Passwort der verschlüsselten Sicherung sind nicht eingeschlossen. Wer die Einstellungen ganz verlässt, verliert nichts – die Eingaben bleiben im Abschnitt stehen, gefragt wird erst beim Wechsel des Abschnitts. Ein Neuladen der Seite fragt wie bisher nur über den Browser-Dialog.
- Die Suche durchsucht die Texte der Abschnitte (Beschriftungen, Überschriften, Platzhalter und einige Stichwörter); Werte, die erst beim Öffnen eines Abschnitts geladen werden (z. B. Themen des Leistungsprofils), findet sie erst nach dem ersten Laden.
- „Nächster Schritt“ in der Rechnungsliste kennt nur Entwurf, offen, überfällig und teilbezahlt. Ob eine erstellte Mahnung schon verschickt wurde, weiß SignalDesk nicht („Mahnstufe n erstellt“). Die Spalte „Rechnung“ zeigt Firma · Art und Datum, nicht den Leistungszweck – die Rechnungsliste des Servers liefert die Positionen nicht mit, und der Server wurde nicht geändert.
- Editor und geöffnete Rechnung haben keine eigene Adresse; Neuladen oder `#/abrechnen` zeigt die Liste. Ein ungespeicherter Rechnungsentwurf geht dabei wie bisher verloren.
- „Vertriebskennzahlen“ stehen unter „Auswertung“, ihr Zeitraum wird aber unter „Steuer & Export“ gewählt (vorgewählt: aktuelles Quartal). Einige Texte des Servers sagten bis dev53 weiter „Lead“ (z. B. „nach letzter Lead-Änderung“ unter den Vertriebskennzahlen) – seit dev54 „Firma“.
- Kein „Spalten ▾“ in der Rechnungsliste (das Zielbild zeigt es); die Spalten sind fest. Die Klappzeile „Steuer & Export“ zeigt die USt-Zahllast des Quartals statt „zuletzt exportiert“ – Exporte werden nicht protokolliert.
- Geprüft in Chromium (Playwright) bei 1280 × 720 und 390 × 844; nicht auf echten Geräten und nicht in anderen Browsern.

## Firmenakte im neuen Aufbau und Abschluss der Etappe E (2.0.0-dev54)

- Umgestellt sind Seitenkopf, Reiter, der Überblick (Vereinbart, Chancenliste, Klappzeilen, Kontextspalte) und der Rahmen der übrigen Reiter. Im **alten Aufbau** (in Karten bzw. Klappzeilen eingebettet) stehen in der Akte: die aufklappbaren Karten einer Chance mit Briefing und Bearbeitungsformular, die Bedarfsanalyse, Paketabgleich und Aufgabenvorschläge, Firmendaten & Belege, Website-Bewertung, Kaufsignale, die KI-Analyse, die Personenrecherche mit Rollen und Beschränkungen sowie das Stammdatenformular (zweispaltig, Felder nicht als `ui-field`). Die sieben Ablaufschritte in der Klappzeile „Empfehlung“ und die Belegabdeckung behalten ihre bisherige Darstellung.
- „Vereinbart“ zeigt den nächsten Schritt und das Datum aus den Stammdaten der Firma; gibt es keinen, die früheste offene Aufgabe mit Datum. Wann und in welchem Gespräch der Schritt vereinbart wurde, speichert SignalDesk nicht – die Herkunft lautet daher „eingetragen unter Stammdaten“ und nennt das letzte dokumentierte Gespräch, nicht „zugesagt im Gespräch am …“ wie im Zielbild.
- Die Hauptaktion ist eine feste Regel aus vorhandenen Aktionen: „Gespräch notieren“ (öffnet das Protokoll, ändert nichts von selbst), bei Sperre oder verlorener Firma „Notiz erfassen“, nach Gewinn ohne Rechnung „Rechnung schreiben“. „Gespräch notieren“ wählt nur die Art vor; das gilt nicht als ungespeicherte Eingabe, solange kein Text getippt ist.
- „← Firmen“ nennt die Ansicht, in die es zurückgeht („← Heute“, „← Pipeline“, „← Einstellungen“ …); das Zielbild zeigt nur „← Firmen“.
- „Wert“ in der Chancenliste ist der Nettobetrag des jüngsten Angebots der Chance; ohne Angebot bei der ersten Chance das geschätzte Projektbudget der Firma („ca. …“), sonst „–“. Die Zahl der „Auffälligkeiten“ der Website-Bewertung aus dem Zielbild gibt es nicht im Überblick (der Kurzstand nennt Bewertung und belegte Kriterien aus der Belegabdeckung).
- Der Kurzstand „Passung“ zählt die Kriterien, deren Stand nicht „unbekannt“ ist. „Telefon“ in der Kontextspalte stammt aus dem Firmenprofil (Impressum) oder einem belegten Kanal der Erreichbarkeit; geratene Nummern gibt es weiterhin nicht.
- Anruf erfassen, Termin eintragen und Mail-Entwurf führen wie bisher nach „Kontakt & Termine“ (die Akte schließt sich dabei); bei einer Sperre lehnt der Server diese Aktionen wie bisher ab, die Knöpfe sind nicht ausgegraut.
- Die Klappzeile „Quellen & Belege“ öffnet sich von selbst, wenn ein Website-Vorschlag auf Bestätigung wartet. Offene Klappzeilen bleiben beim Neuzeichnen offen, beim Öffnen einer anderen Firma sind alle zu.
- Begriffe: sichtbar „Firma“ statt „Lead“ in der Oberfläche und in den Meldungen des Servers. **Bewusst geblieben:** interne Namen (Funktionen, Variablen, Adressen wie `#/firmen/akte/ID`, Kennungen wie `#leadForm`, `data-lead`, Tabellen und API-Felder wie `lead_id`), Dateinamen (`leadfinder.js`, `leadlist.js`, `lead_finder.py` …), Kommentare und Docstrings, ältere Einträge im Änderungsprotokoll und gespeicherte Texte (z. B. „evtl. schon als Lead“ an alten Treffern – die Anzeige erkennt beide Fassungen). „Lead-Garantie“ im Kundenangebot heißt jetzt „Anfragen-Garantie“; das ist ein Text, der in neue Angebote übernommen wird.
- Etappe E ist damit abgeschlossen. Nicht umgebaut wurden Pipeline, Datenpflege, Kontakt & Termine, Kaufsignale, Recherche & Berichte, die Analysen-Unteransichten und Import; sie folgen den Regeln nur über Kopfzeile, Reiter und gemeinsame Klassen. „Spalten ▾“ fehlt in den Listen von Angeboten und Abrechnen.
- Geprüft in Chromium (Playwright) bei 1280 × 720 und 390 × 844; nicht auf echten Geräten und nicht in anderen Browsern.

