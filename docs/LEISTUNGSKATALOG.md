# Zentraler Leistungskatalog

Stand 2.0.0-dev16 (Produktreview M12). Code: [`sales_tool/catalog.py`](../sales_tool/catalog.py), Berechnung in
[`sales_tool/pricing.py`](../sales_tool/pricing.py). Bearbeiten unter *Einstellungen → Leistungen & Preise*.

## Grundsatz

- **Eine Kennung je Leistung.** Die 26 Leistungen des Baukastens (z. B. `logo`, `webdesign`, `software`) sind die einzige Quelle
  für Umfang, Aufwand, enthaltene Fremdkosten, Liefergegenstände, Ausschlüsse, Abnahme, Korrekturschleifen und Leistungsbereich.
- **Vorlagen sind Zusammenstellungen** dieser Leistungen. Ihr Preis und Zeitraum werden mit derselben Rechnung wie im Angebot aus
  den Positionen bestimmt. Es gibt keine zweite Preisangabe mehr.
- **Eigene Werte gelten überall.** Ein geänderter Aufwand, fester Preis oder eine geänderte Zahl an Korrekturschleifen wirkt auf
  neue Angebote, Vorlagenpreise, Paketempfehlungen in der Firmenakte, die Angebotskarten der Hilfe und die Auswahl „Leistung“.
- **Gespeicherte Angebote bleiben, wie sie sind.** Text und Preis stehen als Kopie im Angebot. Neue Angebote speichern intern
  den Katalogstand (kurze Kennung), damit später nachvollziehbar ist, mit welchen Werten gerechnet wurde.

## Zusammenführung der bisherigen Listen

Bis dev15 gab es vier getrennte Listen mit eigenen Titeln, Preisen und Zeiträumen:

| Liste bis dev15 | Anzahl | Wofür | Jetzt |
|---|---|---|---|
| `model.OFFERS` | 5 | Angebotskarten in der Hilfe, Auswahl „Leistung“ der Firma | Vorlagen des Katalogs (6, „Growth Care“ ist neu wählbar) |
| `sales_workspace.PACKAGES` | 6 | früherer Paket-Rechner, „ab“-Preis der Empfehlungen | Vorlagen des Katalogs |
| `sales_workspace.ADDONS` | 5 | Zusatzleistungen des früheren Paket-Rechners | Positionen aus dem Katalog (siehe unten) |
| `pricing.SERVICES` | 26 | Baukasten | unverändert die Leistungen des Katalogs |

Die Kennungen der Vorlagen sind die bisherigen Paketkennungen. Gespeicherte Firmen, Paketempfehlungen, Website-Bewertungen und
Signal-Hypothesen behalten dadurch ihre Zuordnung – es war keine Datenmigration nötig.

### Vorlagen (mit Startwerten des Katalogs, 66 €/h, 10 % Puffer)

| Kennung | Vorlage | Positionen | Preis jetzt | früher als Angebot | früher als Paket |
|---|---|---|---|---|---|
| `pilot` | Website- & Anfrage-Pilot | Webseiten-Analyse (Standard) + 8 Std. nach Aufwand | 1.118 € einmalig | 990–2.500 €, 1–2 Wochen | ab 1.450 €, 1–2 Wochen |
| `conversion` | B2B Website- & Conversion-Sprint | Webdesign (Standard) + 4 Texte + SEO/GEO (Basis) | 5.970 € einmalig | 4.500–8.500 €, 3–4 Wochen | ab 5.900 €, 3–5 Wochen |
| `brand` | Brand- & Design-System | Logogestaltung (Umfangreich) + Grafikdesign (Standard) | 3.640 € einmalig | 3.500–7.000 €, 2–4 Wochen | ab 4.200 €, 2–4 Wochen |
| `care` | Growth Care – Website & Optimierung | Website-/Shop-Betreuung (Standard) | 370 € / Monat | – | ab 790 € / Monat |
| `portal` | Kundenportal-MVP | Workshop (Halbtag) + Individualsoftware (Umfangreich) | 13.510 € einmalig | 12.000–30.000 €, 6–10 Wochen | ab 18.500 €, 8–12 Wochen |
| `automation` | Automatisierungsprojekt – ein Prozess digital | Workshop (Halbtag) + Individualsoftware (Standard) | 6.250 € einmalig | 6.900–15.000 €, 4–6 Wochen | ab 6.900 €, 4–6 Wochen |

**Bitte prüfen:** Die früheren Paketpreise waren eigene Zahlen und stimmten nicht mit dem überein, was der Baukasten für dieselbe
Vorlage berechnet hat – am deutlichsten bei „Kundenportal-MVP“ (Empfehlung „ab 18.500 €“, Angebot 13.510 €) und „Growth Care“
(„ab 790 €“, Angebot 370 € je Monat). Seit dev16 zeigt jede Stelle den Baukastenpreis. Wenn die früheren Zahlen deine tatsächlichen
Preise waren, passe die Katalogwerte der beteiligten Leistungen an (Aufwand oder fester Preis) – die Vorlagen folgen automatisch.

### Frühere Zusatzleistungen

Ältere Aufrufe der Schnittstelle mit `package` und `addons` werden in Positionen übersetzt:

| Zusatzleistung | wird zu |
|---|---|
| Texte für bis zu 3 Kernseiten | 3 × Website- & Werbetexte |
| Messkonzept & Dashboard | 15 Std. nach Aufwand mit diesem Titel |
| Technisches SEO-Basispaket | SEO- & GEO-Optimierung (Basis) |
| Eine Schnittstellen-Integration | Individualsoftware (Basis) mit diesem Titel |
| Zusätzlicher Übergabe-Workshop | Strategie- & Konzept-Workshop (Halbtag) mit diesem Titel |

Kostensatz, Risiko- und Margenaufschlag des früheren Paket-Rechners gibt es nicht mehr; solche Aufrufe werden mit einer
Erklärung abgelehnt, statt still anders zu rechnen.

## Was je Leistung neu festgelegt ist

**Korrekturschleifen** sind ein eigenes Feld je Leistung und Umfang (Prüffall K01 aus dem Review). Der Umfangstext enthält keine
Zahl mehr, die einem geänderten Wert widersprechen könnte; die Zahl wird angehängt und im Kundendokument je Position
zusammengeführt („Pos. 1 Logogestaltung: 1 Korrekturschleife; Pos. 2 Website- & Werbetexte: 1 Korrekturschleife je Seite/Text“).
Startwerte gibt es nur, wo der Katalog sie schon nannte (Logo Basis 1, Standard 2; Texte 1 je Text). Für andere gestalterische
Leistungen (Grafik, Print, Kunst, Fachartikel, Video, Webdesign) erscheint intern ein offener Punkt „nicht festgelegt“ – nie im
Kundendokument. Die Zahl legst du in den Einstellungen fest.

**Ausschlüsse ohne Widerspruch.** „Texte (separate Position)“, „Fotografie (separate Position)“, „Anreise (separate Position)“ und
„Produktfotos und -texte (separate Positionen)“ entfallen im Kundendokument, sobald die genannte Leistung selbst als Position im
Angebot steht.

**Leistungsbereich** je Leistung: Analyse & Beratung, Mediengestaltung, Software & Web-Technik, Sichtbarkeit & Kampagnen, Vor Ort
& Aufwand (Webdesign und Webshop gehören zu Medien und Software). Daraus entsteht intern im Angebot die Liste „Vor dem Versand
klären“, z. B. für Medien Nutzungsumfang und Quelldateien, für Software Betrieb, Schnittstellen, Datenübernahme und Übergabe.
Grundlage dafür ist der Leitfaden zum Kundenonboarding vom 13.11.2026 (Kapitel „Vor dem Versand richtig vorbereiten“). Die
Bereiche sind zugleich die Grundlage für die Briefing-Fragen in M14.

**Zahlungsplan** ist eine Einstellung („Anzahlung bei Beauftragung“, Startwert 40 %, 0–90 %). Das Angebot nennt den Plan, intern
steht der Hinweis, dass er mit dem Kunden ausdrücklich zu vereinbaren ist. Die Abschlagsrechnung übernimmt den Prozentsatz aus dem
Angebot (ältere Angebote: 40 % wie bisher); bei 0 % gibt es keinen Abschlag-Knopf.

**Webseiten-Analyse klar abgegrenzt** (Bewertungsmodell vom 13.11.2026, Maßnahme M31): Eine Person prüft aus vier Blickwinkeln –
es wird nicht als Prüfung durch vier Spezialisten beschrieben. Nicht enthalten sind ausdrücklich Tests mit Personen aus der
Zielgruppe (Nutzerstudie), eine umfassende Technik-, Sicherheits- oder Barrierefreiheitsprüfung und eine Wirkungszusage. Abgenommen
wird die vereinbarte Prüfung, nicht eine spätere Wirkung; das Ergebnis darf auch lauten, dass kein größerer Umbau nötig ist. Die
kalkulierten Stunden (3/8/16) sind unverändert.

## Grenzen

- Titel, Beschreibungen, Ausschlüsse und Vorlagen-Zusammenstellungen sind im Code festgelegt; in den Einstellungen änderbar sind
  Aufwand, enthaltene Fremdkosten, fester Preis und Korrekturschleifen. Eigene Leistungen anlegen oder Leistungen ausblenden geht
  noch nicht.
- Die Paketempfehlungen und die Website-Bewertung verweisen weiterhin auf Vorlagen, nicht auf einzelne Leistungen. Die Verbindung
  „Befund → Leistung“ ist Maßnahme M32.
- Eine Nutzerstudie gibt es bewusst noch nicht als Leistung; sie folgt erst nach einem Pilot (M30).
- Alle Aufwände sind Startwerte (Schätzungen), keine gemessenen Werte.
