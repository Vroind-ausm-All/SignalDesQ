"""Zentraler Leistungskatalog (2.0.0-dev16, Produktreview M12).

Eine Kennung je Leistung. Bis dev15 gab es vier getrennte Listen: fünf Angebote (model.OFFERS), sechs Pakete und fünf
Zusatzleistungen für den früheren Paket-Rechner (sales_workspace.PACKAGES/ADDONS) und 26 Leistungen im Preisbaukasten.
Jetzt gilt:

- **Leistungen** (`SERVICES`) sind die einzige Quelle für Umfang, Aufwand, Liefergegenstände, Ausschlüsse, Abnahme,
  Korrekturschleifen und Leistungsbereich. Eigene Werte (Aufwand, Fremdkosten, fester Preis, Korrekturschleifen) stehen in
  den Einstellungen und gelten für alle künftigen Angebote und Empfehlungen.
- **Vorlagen** (`VORLAGEN`) sind Zusammenstellungen dieser Leistungen. Ihre Kennungen sind die bisherigen Paket- und
  Angebotskennungen, damit gespeicherte Firmen, Empfehlungen und Bewertungen gültig bleiben. Preis und Zeitraum einer
  Vorlage werden aus den Positionen berechnet – es gibt keine zweite Preisangabe mehr.
- **Herkunft** (`FRUEHER`) hält die Werte bis dev15 fest, damit die Zusammenführung nachvollziehbar bleibt. Sie werden
  nicht mehr zum Rechnen verwendet. Gespeicherte Angebote behalten ihren Text- und Preisstand.
"""
from __future__ import annotations

import hashlib
import json

GROUP_AREA = {'Analyse & Beratung': 'beratung', 'Design & Marke': 'medien', 'Text': 'medien', 'Web & Shop': 'software', 'Sichtbarkeit': 'sichtbarkeit',
              'Foto & Video': 'medien', 'Software & KI': 'software', 'Vor Ort & Aufwand': 'aufwand'}
AREAS = {'beratung': 'Analyse & Beratung', 'medien': 'Mediengestaltung', 'software': 'Software & Web-Technik',
         'sichtbarkeit': 'Sichtbarkeit & Kampagnen', 'aufwand': 'Vor Ort & Aufwand'}
# Vor dem Versand zu klären – je Leistungsbereich (Leitfaden Kundenonboarding 13.11.2026, Kap. 4; Bewertungsmodell Kap. 18).
# Nur interne Erinnerung im Angebot, nie im Kundendokument. Grundlage für die Briefing-Fragen in M14.
AREA_CHECKS = {
    'beratung': ['Abnahme ist die vereinbarte Prüfung bzw. der Bericht – eine spätere Wirkung wird bei Bedarf separat gemessen',
                 'Was nicht enthalten ist (z. B. Nutzerstudie, umfassende Technik- oder Barrierefreiheitsprüfung), ist benannt'],
    'medien': ['Liefergegenstände, Formate und Varianten sind konkret benannt', 'Nutzungsumfang und Übergabe von Quelldateien sind geklärt',
               'Produktion und Fremdkosten (Druck, Bild- und Schriftlizenzen) sind geklärt'],
    'software': ['Betrieb ist geklärt: wer hostet, aktualisiert, überwacht', 'Schnittstellen und Zugänge sind benannt (keine Passwörter in Mail oder Notizen)',
                 'Datenübernahme und Testdaten sind geklärt', 'Übergabe und Dokumentation sind vereinbart'],
    'sichtbarkeit': ['Ausgangsmessung und Zugänge (z. B. Search Console, Werbekonten) sind geklärt',
                     'Werbebudget und laufende Kosten zahlt der Kunde direkt an die Anbieter'],
    'aufwand': [],
}


def _svc(group, title, desc, kind='paket', sizes=None, unit=None, per_unit_hours=0, per_unit_external=0, min_qty=1, billing='einmalig',
         included=(), deliverables=(), excluded=(), acceptance=(), third_party=(), weeks='', area=None, korrekturen=False, revisions=None):
    """korrekturen=True: gestalterische Leistung, bei der Korrekturschleifen vor dem Versand festgelegt sein sollten.
    revisions: Korrekturschleifen je Einheit (nur Leistungen nach Menge); bei Paketen steht der Wert je Umfang."""
    areas = area if isinstance(area, tuple) else ((area,) if area else (GROUP_AREA[group],))
    return {'group': group, 'title': title, 'description': desc, 'kind': kind, 'sizes': sizes or {}, 'unit': unit, 'per_unit_hours': per_unit_hours,
            'per_unit_external': per_unit_external, 'min_qty': min_qty, 'billing': billing, 'included': list(included), 'deliverables': list(deliverables),
            'excluded': list(excluded), 'acceptance': list(acceptance), 'third_party': list(third_party), 'weeks': weeks,
            'areas': list(areas), 'korrekturen': korrekturen, 'revisions': revisions}


def _s(scope, hours, external=0, weeks='', revisions=None):
    return {'scope': scope, 'hours': hours, 'external': external, 'weeks': weeks, 'revisions': revisions}


SERVICES = {
    # ------------------------------------------------ Analyse & Beratung
    'website_analyse': _svc('Analyse & Beratung', 'Webseiten-Analyse & Handlungsbedarf',
        'Fachliche Prüfung der bestehenden Website durch eine Person aus vier Blickwinkeln (Gestaltung und Marke, Geschäftsziel, '
        'gestalterische Ausführung, Technik) mit belegten Befunden und priorisiertem Maßnahmenplan. Das Ergebnis kann auch sein, '
        'dass kein größerer Umbau nötig ist.', sizes={
            'S': _s('Fachlicher Kurzcheck: Startseite und ein Anfrageweg; dokumentierte Befunde, offene Fragen und priorisierte Kurzempfehlung', 3, weeks='3 Werktage'),
            'M': _s('Prüfung aus vier Blickwinkeln: bis 10 vereinbarte Seiten und ihre Kernaufgaben (Inhalte, Gestaltung, Anfrageweg, Technik, '
                    'Auffindbarkeit); Befunde mit Belegen, Maßnahmenplan, 45-Min.-Besprechung', 8, weeks='1 Woche'),
            'L': _s('Prüfung aus vier Blickwinkeln wie Standard, zusätzlich Wettbewerbsvergleich und Workshop zur Umsetzung', 16, weeks='2 Wochen')},
        deliverables=['Analysebericht (PDF) mit Fundstellen und Belegen', 'Priorisierter Maßnahmenplan mit offenen Fragen'],
        excluded=['Umsetzung der Maßnahmen', 'Tests mit Personen aus der Zielgruppe (Nutzerstudie)',
                  'Umfassende Technik-, Sicherheits- oder Barrierefreiheitsprüfung', 'Zusage einer Wirkung auf Anfragen, Umsatz oder Platzierung'],
        acceptance=['Bericht und Maßnahmenplan liegen vor und wurden besprochen (Abnahme ist die vereinbarte Prüfung, nicht eine spätere Wirkung)']),
    'workshop': _svc('Analyse & Beratung', 'Strategie- & Konzept-Workshop', 'Gemeinsamer Workshop zu Ziel, Zielgruppe und Umsetzungsplan.', sizes={
            'S': _s('Halbtag (bis 4 Std.) inkl. Vor- und Nachbereitung', 6), 'M': _s('Ganzer Tag (bis 8 Std.) inkl. Vor- und Nachbereitung', 11),
            'L': _s('Zwei Workshop-Tage inkl. Ergebnisdokumentation', 21)},
        deliverables=['Workshop-Dokumentation mit Entscheidungen und nächsten Schritten'], excluded=['Anreise (separate Position)']),
    # ------------------------------------------------ Design & Marke
    'logo': _svc('Design & Marke', 'Logogestaltung', 'Individuell entwickeltes Logo mit Nutzungsrechten für den vereinbarten Zweck.', sizes={
            'S': _s('2 Entwürfe, Druck- und Webdateien', 12, weeks='2 Wochen', revisions=1),
            'M': _s('3 Entwürfe, Farb-/Schwarzweiß-Varianten, Favicon', 22, weeks='3 Wochen', revisions=2),
            'L': _s('Logo inkl. Mini-Styleguide (Farben, Schriften, Anwendungsbeispiele)', 36, weeks='4 Wochen')},
        deliverables=['Logo-Dateien (SVG, PDF, PNG)', 'Einfache Nutzungsrechte für den vereinbarten Einsatz'], korrekturen=True,
        excluded=['Markenrechtliche Prüfung und Anmeldung'], acceptance=['Freigabe des finalen Entwurfs'],
        third_party=['Markenanmeldung/Recherche über eine Kanzlei bzw. das DPMA nach Bedarf.']),
    'grafik': _svc('Design & Marke', 'Grafikdesign', 'Gestaltung von Medien im bestehenden oder neuen Erscheinungsbild.', sizes={
            'S': _s('Einzelmedium, z. B. Anzeige, Social-Media-Vorlage oder Infografik', 6),
            'M': _s('Geschäftsausstattung: Visitenkarte, Briefbogen, E-Mail-Signatur', 14),
            'L': _s('Vorlagenpaket: Geschäftsausstattung, Präsentation, 5 Social-Media-Vorlagen', 28)},
        deliverables=['Offene und druckfertige Dateien'], excluded=['Druckkosten', 'Bildlizenzen außer frei verfügbaren'], korrekturen=True),
    'print': _svc('Design & Marke', 'Printdesign & Druckabwicklung', 'Gestaltung von Drucksachen inkl. Druckdatenprüfung und Abwicklung mit der Druckerei.', sizes={
            'S': _s('Flyer oder Plakat, inkl. Standard-Druck kleiner Auflage', 8, 150), 'M': _s('Broschüre bis 8 Seiten inkl. Druck kleiner Auflage', 20, 400),
            'L': _s('Broschüre/Katalog bis 24 Seiten inkl. Druck kleiner Auflage', 45, 900)},
        deliverables=['Druckfertige PDF-Dateien', 'Gedruckte Exemplare in der vereinbarten Auflage'],
        excluded=['Größere Auflagen und Sonderveredelungen (Angebot der Druckerei)'], korrekturen=True,
        third_party=['Abweichende Auflage oder Papier: Druckkosten nach Angebot der Druckerei, ohne Aufschlag.']),
    'kunst': _svc('Design & Marke', 'Handgestaltete Kunst (Auftragsarbeit)', 'Individuelles, handgefertigtes Kunstwerk nach Briefing – z. B. Bild, Illustration oder Wandgestaltung.', sizes={
            'S': _s('Kleines Format bis A3, inkl. Material', 10, 60, '2 Wochen'), 'M': _s('Mittleres Format bis 100 × 70 cm, inkl. Material', 24, 150, '3–4 Wochen'),
            'L': _s('Großes Format oder Wandgestaltung bis ca. 6 m², inkl. Material', 48, 400, '4–6 Wochen')},
        deliverables=['Fertiges Original', 'Digitale Fotografie des Werks'], excluded=['Rahmung und Transport, wenn nicht vereinbart'],
        acceptance=['Abnahme des Skizzenentwurfs vor Ausführung', 'Übergabe des fertigen Werks'], korrekturen=True),
    # ------------------------------------------------ Text
    'texte': _svc('Text', 'Website- & Werbetexte', 'Professionelle Texte je Seite bzw. Werbemittel, suchmaschinen- und KI-freundlich formuliert.', kind='menge',
                  unit='Seite/Text', per_unit_hours=3, included=['Kurz-Briefing'], deliverables=['Fertige Texte als Datei'], korrekturen=True, revisions=1),
    'fachartikel': _svc('Text', 'Fachartikel / Blogbeitrag', 'Fachartikel mit ca. 1.000 Wörtern inkl. Recherche und Überschriftenstruktur.', kind='menge',
                        unit='Artikel', per_unit_hours=5, deliverables=['Artikel als Datei, optional eingepflegt'], korrekturen=True),
    # ------------------------------------------------ Web & Shop
    'webdesign': _svc('Web & Shop', 'Webdesign & Website-Umsetzung', 'Gestaltung und Umsetzung einer responsiven Website mit Kontaktweg.', sizes={
            'S': _s('Onepager mit Kontaktformular', 24, weeks='2–3 Wochen'), 'M': _s('Unternehmenswebsite bis 8 Seiten', 60, weeks='4–6 Wochen'),
            'L': _s('Website bis 20 Seiten, mehrsprachig oder mit Blog', 110, weeks='6–10 Wochen')},
        included=['Konzept und Gestaltung', 'Responsive Umsetzung', 'Kontaktformular', 'Grundlegende SEO-Einstellungen', 'Einweisung'],
        deliverables=['Veröffentlichte Website', 'Zugangsdaten und Kurzanleitung'], excluded=['Texte (separate Position)', 'Fotografie (separate Position)'],
        acceptance=['Freigabe des Designs', 'Funktionstest auf Desktop und Smartphone'], area=('medien', 'software'), korrekturen=True,
        third_party=['Hosting und Domain: ca. 5–30 € pro Monat, Vertrag direkt mit dem Anbieter.', 'Kostenpflichtige Plugins/Themes nach Bedarf.']),
    'webshop': _svc('Web & Shop', 'Aufbau eines eigenen Webshops', 'Einrichtung eines Onlineshops mit Zahlungsarten, Versand und Rechtstext-Struktur.', sizes={
            'S': _s('Starter-Shop bis 50 Produkte', 50, weeks='4–6 Wochen'), 'M': _s('Shop bis 500 Produkte inkl. Varianten, Zahlungsarten und Versandregeln', 100, weeks='6–10 Wochen'),
            'L': _s('Shop bis 2.000 Produkte mit Import und Schnittstellen', 170, weeks='10–14 Wochen')},
        included=['Shop-Einrichtung und Gestaltung', 'Zahlungs- und Versandeinstellungen', 'Produktimport aus Vorlage', 'Testbestellung und Einweisung'],
        deliverables=['Einsatzbereiter Shop'], excluded=['Produktfotos und -texte (separate Positionen)', 'Rechtsberatung'],
        acceptance=['Testbestellung inkl. Zahlung und Bestellbestätigung erfolgreich'], area=('medien', 'software'),
        third_party=['Shop-System/Hosting: ca. 20–80 € pro Monat.', 'Gebühren der Zahlungsanbieter je Transaktion.', 'Rechtstexte-Service ca. 10–20 € pro Monat.']),
    'shop_anbindung': _svc('Web & Shop', 'Shop- & Marktplatz-Anbindung', 'Anbindung an einen weiteren Verkaufskanal oder ein System (z. B. Amazon, eBay, Warenwirtschaft, Buchhaltung).',
                           kind='menge', unit='Anbindung', per_unit_hours=16, included=['Einrichtung der Schnittstelle', 'Datenabgleich mit Testartikeln'],
                           acceptance=['Testartikel bzw. -bestellung wird korrekt übertragen'],
                           third_party=['Gebühren der Plattformen bzw. Connector-Abos nach Anbieter.']),
    'pflege': _svc('Web & Shop', 'Website-/Shop-Betreuung (monatlich)', 'Laufende Betreuung: Updates, Sicherungskontrolle und kleine Änderungen.', billing='monatlich', weeks='fortlaufend, monatlich', sizes={
            'S': _s('bis 2 Std. pro Monat', 2), 'M': _s('bis 5 Std. pro Monat', 5), 'L': _s('bis 10 Std. pro Monat', 10)},
        included=['Updates und Funktionskontrolle', 'Kleine inhaltliche Änderungen im Stundenrahmen'], excluded=['Nicht genutzte Stunden verfallen zum Monatsende']),
    # ------------------------------------------------ Sichtbarkeit
    'seo_geo': _svc('Sichtbarkeit', 'SEO- & GEO-Optimierung', 'Optimierung für Suchmaschinen und KI-Antwortsysteme (GEO): Technik, Inhalte, strukturierte Daten.', sizes={
            'S': _s('Audit und Basisoptimierung: Technik, Meta-Daten, Indexierung, strukturierte Daten', 10),
            'M': _s('Optimierung bis 10 Seiten inkl. lokaler Sichtbarkeit (Unternehmensprofil)', 24), 'L': _s('Umfassende Optimierung bis 30 Seiten inkl. Inhaltsplan', 45)},
        deliverables=['Umgesetzte Optimierungen mit Protokoll', 'Ausgangsmessung für den Vergleich'], excluded=['Garantie für Rankings oder Nennungen in KI-Antworten']),
    'seo_betreuung': _svc('Sichtbarkeit', 'SEO- & GEO-Betreuung (monatlich)', 'Laufende Optimierung, Monitoring und Monatsbericht.', billing='monatlich', weeks='fortlaufend, monatlich', sizes={
            'S': _s('bis 4 Std. pro Monat', 4), 'M': _s('bis 8 Std. pro Monat', 8), 'L': _s('bis 14 Std. pro Monat', 14)},
        deliverables=['Monatsbericht'], excluded=['Ranking-Garantie'], third_party=['SEO-Tool-Lizenzen, falls gewünscht, direkt beim Anbieter.']),
    'werbung': _svc('Sichtbarkeit', 'Werbekampagnen – Einrichtung', 'Konzeption und Einrichtung von Online-Werbung (z. B. Google, Meta, LinkedIn) inkl. Tracking.', sizes={
            'S': _s('1 Kanal, 1 Kampagne', 8), 'M': _s('2 Kanäle inkl. Conversion-Tracking', 16), 'L': _s('3 Kanäle, mehrere Zielgruppen, Landingpage-Abstimmung', 26)},
        excluded=['Werbebudget'], third_party=['Werbebudget wird direkt an die Plattformen gezahlt (nicht im Festpreis).']),
    'werbung_betreuung': _svc('Sichtbarkeit', 'Kampagnenbetreuung (monatlich)', 'Laufende Optimierung und Bericht.', billing='monatlich', weeks='fortlaufend, monatlich', sizes={
            'S': _s('bis 3 Std. pro Monat', 3), 'M': _s('bis 6 Std. pro Monat', 6), 'L': _s('bis 10 Std. pro Monat', 10)},
        third_party=['Werbebudget direkt an die Plattformen.']),
    # ------------------------------------------------ Foto & Video
    'foto': _svc('Foto & Video', 'Professionelle Fotografie', 'Fotoshooting vor Ort inkl. Bildauswahl und Bearbeitung.', sizes={
            'S': _s('Halbtag: bis 4 Std. Shooting, ca. 20 bearbeitete Bilder', 7), 'M': _s('Ganzer Tag: bis 8 Std. Shooting, ca. 40 bearbeitete Bilder', 14),
            'L': _s('Zwei Tage: bis 16 Std. Shooting, ca. 80 bearbeitete Bilder', 28)},
        deliverables=['Bearbeitete Bilder in Web- und Druckqualität', 'Nutzungsrechte für Website, Social Media und Print des Kunden'],
        excluded=['Anreise (separate Position)', 'Models, Studio- und Requisitenmiete']),
    'produktfoto': _svc('Foto & Video', 'Produktfotos (freigestellt)', 'Produktfotografie mit freigestelltem Hintergrund, je Produkt.', kind='menge',
                        unit='Produkt', per_unit_hours=0.4, min_qty=5, deliverables=['Freigestellte Produktfotos (Web und Druck)']),
    'video': _svc('Foto & Video', 'Videografie', 'Planung, Dreh und Schnitt eines Videos.', sizes={
            'S': _s('Social-Media-Clip bis 30 Sek.', 10, 50), 'M': _s('Imagefilm 60–90 Sek.', 32, 100), 'L': _s('Imagefilm bis 3 Min. inkl. Interviews', 60, 150)},
        deliverables=['Fertiges Video in gängigen Formaten', 'Musiklizenz für den vereinbarten Einsatz'], excluded=['Anreise (separate Position)', 'Sprecher, Darsteller'],
        korrekturen=True),
    # ------------------------------------------------ Software & KI
    'software': _svc('Software & KI', 'Individualsoftware für den Arbeitsalltag', 'Maßgeschneiderte Lösung, die wiederkehrende Arbeit vereinfacht.', sizes={
            'S': _s('Kleines Werkzeug oder Automatisierung eines Ablaufs', 24, weeks='2–3 Wochen'), 'M': _s('Web-Anwendung für einen Prozess mit Datenablage', 80, weeks='5–8 Wochen'),
            'L': _s('Mehrere Module mit Rollen und Rechten', 180, weeks='10–16 Wochen')},
        included=['Anforderungsaufnahme', 'Umsetzung und Tests', 'Einweisung und Dokumentation'], deliverables=['Lauffähige Software', 'Dokumentation'],
        acceptance=['Vereinbarte Abläufe sind mit Testdaten durchführbar'], third_party=['Hosting/Server ca. 10–80 € pro Monat je nach Umfang.']),
    'chatbot': _svc('Software & KI', 'KI-Chatbot-Integration', 'KI-Assistent auf der Website, der Fragen mit Ihren eigenen Inhalten beantwortet.', sizes={
            'S': _s('FAQ-Bot mit Website-Inhalten', 14), 'M': _s('Bot mit eigenen Dokumenten und Übergabe an einen Menschen', 30),
            'L': _s('Bot mit Schnittstelle (z. B. Terminbuchung, CRM)', 55)},
        included=['Einrichtung und Wissensbasis', 'Datenschutz-Hinweise und Einbindung', 'Testphase mit Anpassungen'], deliverables=['Eingebundener Chatbot', 'Kurzanleitung zur Pflege'],
        excluded=['Garantie für fehlerfreie Antworten'], third_party=['KI-/Plattformkosten nach Nutzung ca. 20–100 € pro Monat.', 'Auftragsverarbeitungsvertrag mit dem KI-Anbieter erforderlich.']),
    'voicebot': _svc('Software & KI', 'Telefon-Sprachbot-Integration', 'Sprachassistent am Telefon: Anrufe annehmen, Fragen beantworten, Anliegen weiterleiten.', sizes={
            'S': _s('Anrufannahme mit Nachricht und Weiterleitung', 20), 'M': _s('Häufige Fragen und Terminbuchung', 40), 'L': _s('Mit Schnittstelle zu Kalender/CRM und mehreren Abläufen', 70)},
        included=['Gesprächsablauf und Ansagen', 'Einrichtung und Tests'], deliverables=['Eingerichteter Sprachbot an der vereinbarten Rufnummer'],
        third_party=['Telefonie- und KI-Minutenpreise ca. 0,10–0,30 € pro Minute.', 'Rufnummer beim Telefonanbieter.']),
    'ki_betrieb': _svc('Software & KI', 'Betrieb & Optimierung Chat-/Sprachbot (monatlich)', 'Laufende Auswertung und Verbesserung der Antworten.', billing='monatlich', weeks='fortlaufend, monatlich', sizes={
            'S': _s('bis 1 Std. pro Monat', 1), 'M': _s('bis 3 Std. pro Monat', 3), 'L': _s('bis 6 Std. pro Monat', 6)}),
    # ------------------------------------------------ Vor Ort & Aufwand
    'tagessatz': _svc('Vor Ort & Aufwand', 'Tagespauschale vor Ort', 'Arbeitstag beim Kunden (z. B. Workshop, Shooting-Begleitung, Einweisung).', kind='tag', unit='Tag'),
    'anreise': _svc('Vor Ort & Aufwand', 'Anreise', 'Fahrtkosten und anteilige Fahrzeit für Termine vor Ort.', kind='anreise', unit='Fahrt'),
    'aufwand': _svc('Vor Ort & Aufwand', 'Leistung nach Aufwand', 'Für frei vereinbarte Leistungen ohne festen Umfang (Stundensatz).', kind='stunden', unit='Std.'),
}

# Vorlagen = Zusammenstellungen von Leistungen. Kennungen wie die bisherigen Pakete/Angebote (Firmenfeld „Leistung“,
# Empfehlungen, Website-Bewertung, Signal-Hypothesen). Titel und Ziel wie im bisherigen Paket; Preis und Zeitraum nur aus den Positionen.
VORLAGEN = {
    'pilot': {'title': 'Website- & Anfrage-Pilot', 'outcome': 'Ein konkreter Anfrageweg ist einfacher und überprüfbar nutzbar.',
              'positions': [{'service': 'website_analyse', 'size': 'M'}, {'service': 'aufwand', 'qty': 8, 'title': 'Umsetzung einer klar abgegrenzten Verbesserung'}]},
    'conversion': {'title': 'B2B Website- & Conversion-Sprint', 'outcome': 'Eine messbare Produkt-/Leistungsstrecke für qualifizierte Anfragen.',
                   'positions': [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 4}, {'service': 'seo_geo', 'size': 'S'}]},
    'brand': {'title': 'Brand- & Design-System', 'outcome': 'Ein konsistenter Markenauftritt mit wiederverwendbaren Vorlagen.',
              'positions': [{'service': 'logo', 'size': 'L'}, {'service': 'grafik', 'size': 'M'}]},
    'care': {'title': 'Growth Care – Website & Optimierung', 'outcome': 'Kontinuierliche Verbesserung eines bestehenden digitalen Anfragewegs.',
             'positions': [{'service': 'pflege', 'size': 'M'}]},
    'portal': {'title': 'Kundenportal-MVP', 'outcome': 'Ein klar definierter digitaler Kundenprozess als benutzbares MVP.',
               'positions': [{'service': 'workshop', 'size': 'S'}, {'service': 'software', 'size': 'L'}]},
    'automation': {'title': 'Automatisierungsprojekt – ein Prozess digital',
                   'outcome': 'Ein klar abgegrenzter manueller Ablauf läuft automatisiert, nachvollziehbar und mit weniger Doppelerfassung.',
                   'positions': [{'service': 'workshop', 'size': 'S'}, {'service': 'software', 'size': 'M'}]},
}
TEMPLATES = {k: v['positions'] for k, v in VORLAGEN.items()}  # Positionslisten (API /api/pricing/templates, Baukasten)

# Stand bis 2.0.0-dev15 – nur zur Nachvollziehbarkeit der Zusammenführung, nicht zum Rechnen.
FRUEHER = {
    'angebote': {  # model.OFFERS: Angebotskarten im Spielbuch, Auswahl „Leistung“ in der Firmenakte
        'pilot': {'title': 'Website- & Anfrage-Pilot', 'price_from': 990, 'price_to': 2500, 'period': '1–2 Wochen'},
        'conversion': {'title': 'Conversion- & Web-Sprint', 'price_from': 4500, 'price_to': 8500, 'period': '3–4 Wochen'},
        'portal': {'title': 'Kundenportal & Prozess-App', 'price_from': 12000, 'price_to': 30000, 'period': '6–10 Wochen'},
        'brand': {'title': 'Brand & Design-System', 'price_from': 3500, 'price_to': 7000, 'period': '2–4 Wochen'},
        'automation': {'title': 'Automatisierungsprojekt', 'price_from': 6900, 'price_to': 15000, 'period': '4–6 Wochen'},
    },
    'pakete': {  # sales_workspace.PACKAGES: früherer Paket-Rechner, „ab“-Preis der Empfehlungen
        'pilot': {'title': 'Website- & Anfrage-Pilot', 'minimum_eur': 1450, 'weeks': '1–2 Wochen', 'hours': 19, 'revision_rounds': 1},
        'conversion': {'title': 'B2B Website- & Conversion-Sprint', 'minimum_eur': 5900, 'weeks': '3–5 Wochen', 'hours': 78, 'revision_rounds': 2},
        'brand': {'title': 'Brand- & Design-System', 'minimum_eur': 4200, 'weeks': '2–4 Wochen', 'hours': 58, 'revision_rounds': 2},
        'care': {'title': 'Growth Care – Website & Optimierung', 'minimum_eur': 790, 'weeks': 'fortlaufend / monatlich', 'hours': 8, 'revision_rounds': 1},
        'portal': {'title': 'Kundenportal-MVP', 'minimum_eur': 18500, 'weeks': '8–12 Wochen', 'hours': 238, 'revision_rounds': 2},
        'automation': {'title': 'Automatisierungsprojekt – ein Prozess digital', 'minimum_eur': 6900, 'weeks': '4–6 Wochen', 'hours': 96, 'revision_rounds': 2},
    },
    'zusatz': {  # sales_workspace.ADDONS → Positionen aus dem Katalog (für ältere Aufrufe der Schnittstelle)
        'copy': {'title': 'Texte für bis zu 3 Kernseiten', 'hours': 12, 'price_floor': 700, 'positions': [{'service': 'texte', 'qty': 3}]},
        'analytics': {'title': 'Messkonzept & Dashboard', 'hours': 15, 'price_floor': 950,
                      'positions': [{'service': 'aufwand', 'qty': 15, 'title': 'Messkonzept & Dashboard'}]},
        'seo': {'title': 'Technisches SEO-Basispaket', 'hours': 12, 'price_floor': 750, 'positions': [{'service': 'seo_geo', 'size': 'S'}]},
        'integration': {'title': 'Eine Schnittstellen-Integration', 'hours': 28, 'price_floor': 2200,
                        'positions': [{'service': 'software', 'size': 'S', 'title': 'Eine Schnittstellen-Integration'}]},
        'training': {'title': 'Zusätzlicher Übergabe-Workshop', 'hours': 5, 'price_floor': 350,
                     'positions': [{'service': 'workshop', 'size': 'S', 'title': 'Zusätzlicher Übergabe-Workshop'}]},
    },
}
# Ausschlüsse, die nur gelten, solange die genannte Leistung nicht selbst als Position im Angebot steht (sonst Widerspruch im Kundendokument)
SEPARATE = {'Texte (separate Position)': ('texte',), 'Fotografie (separate Position)': ('foto',), 'Anreise (separate Position)': ('anreise',),
            'Produktfotos und -texte (separate Positionen)': ('produktfoto', 'texte')}
LEGACY_CALC_FIELDS = ('cost_rate_eur', 'risk_pct', 'target_margin_pct', 'custom_price_eur', 'margin_pct')


def revisions_text(n, unit=None):
    """„1 Korrekturschleife“, „2 Korrekturschleifen je Seite/Text“; None = nicht festgelegt."""
    if n is None:
        return ''
    text = 'keine Korrekturschleife' if n == 0 else f"{n:g} Korrekturschleife{'' if n == 1 else 'n'}"
    return text + (f' je {unit}' if unit and n else '')


def legacy_payload(data):
    """Aufruf des früheren Paket-Rechners ({package, addons, …}) → Angebot aus dem zentralen Katalog."""
    if not isinstance(data, dict):
        raise ValueError('Ungültige Kalkulation.')
    used = sorted(set(LEGACY_CALC_FIELDS) & set(data))
    if used:
        raise ValueError('Kostensatz, Risiko- und Margenaufschlag des früheren Paket-Rechners gibt es seit 2.0.0-dev16 nicht mehr. '
                         'Preise kommen aus dem zentralen Leistungskatalog (Einstellungen → Leistungen & Preise). Nicht verwendbar: ' + ', '.join(used) + '.')
    if set(data) - {'package', 'addons', 'tax_mode', 'project_label', 'customer_goal', 'assumptions'}:
        raise ValueError('Ungültige Kalkulation.')
    key = data.get('package')
    if key not in VORLAGEN:
        raise ValueError('Bitte eine Vorlage auswählen.')
    raw = data.get('addons', [])
    if not isinstance(raw, list) or any(not isinstance(x, str) or x not in FRUEHER['zusatz'] for x in raw) or len(set(raw)) != len(raw):
        raise ValueError('Ungültige Zusatzleistungen.')
    out = {k: data[k] for k in ('tax_mode', 'project_label', 'customer_goal', 'assumptions') if k in data}
    out['template'] = key
    out['positions'] = [dict(p) for p in VORLAGEN[key]['positions']] + [dict(p) for x in raw for p in FRUEHER['zusatz'][x]['positions']]
    return out


def vorlagen(conn):
    """Vorlagen mit Preis und Zeitraum aus den aktuellen Katalogwerten – dieselbe Rechnung wie im Angebot."""
    from .pricing import build_quote
    out = []
    for key, v in VORLAGEN.items():
        q = build_quote(conn, {'positions': v['positions'], 'template': key})['customer']
        out.append({'key': key, 'title': v['title'], 'outcome': v['outcome'], 'positions': v['positions'],
                    'services': [f"{p['title']} – {p['scope']}" for p in q['positions']],
                    'areas': sorted({a for p in v['positions'] for a in SERVICES[p['service']]['areas']} - {'aufwand'}),
                    'once_net_eur': q['once_net_eur'], 'monthly_net_eur': q['monthly_net_eur'], 'billing': q['billing'], 'weeks': q['weeks']})
    return out


def price_label(v):
    euro = lambda x: f"{x:,.0f} €".replace(',', '.')
    parts = ([f"{euro(v['once_net_eur'])} einmalig"] if v['once_net_eur'] else []) + ([f"{euro(v['monthly_net_eur'])} / Monat"] if v['monthly_net_eur'] else [])
    return ' + '.join(parts) + ' netto'


def offers_for_client(conn):
    """Vorlagen für die Oberfläche (Firmenfeld „Leistung“, Angebotskarten, Empfehlungen)."""
    return {v['key']: {'title': v['title'], 'outcome': v['outcome'], 'weeks': v['weeks'], 'billing': v['billing'],
                       'once_net_eur': v['once_net_eur'], 'monthly_net_eur': v['monthly_net_eur'], 'price_label': price_label(v)} for v in vorlagen(conn)}


def herkunft(conn=None, current=None):
    """Zuordnungstabelle 5 Angebote / 6 Pakete / 5 Zusatzleistungen → Vorlagen und Leistungen."""
    current = current if current is not None else ({v['key']: v for v in vorlagen(conn)} if conn is not None else {})
    rows = []
    for key, v in VORLAGEN.items():
        a, p = FRUEHER['angebote'].get(key), FRUEHER['pakete'].get(key)
        rows.append({'key': key, 'title': v['title'], 'positions': [SERVICES[x['service']]['title'] for x in v['positions']],
                     'price_now': price_label(current[key]) if key in current else '',
                     'former_offer': f"„{a['title']}“, {a['price_from']:,}–{a['price_to']:,} €".replace(',', '.') if a else '',
                     'former_package': f"„{p['title']}“, ab {p['minimum_eur']:,} €".replace(',', '.') if p else ''})
    addons = [{'key': k, 'title': z['title'], 'positions': [x.get('title') or SERVICES[x['service']]['title'] for x in z['positions']]}
              for k, z in FRUEHER['zusatz'].items()]
    return {'vorlagen': rows, 'zusatz': addons, 'leistungen': len(SERVICES),
            'note': 'Leistungskennungen sind unverändert. Firmen, Empfehlungen und Bewertungen behalten ihre Kennung; gespeicherte Angebote ihren Text- und Preisstand.'}


def fingerprint(conn):
    """Kurzer Stand des Katalogs inkl. eigener Werte – wird intern an neuen Angeboten gespeichert."""
    from .pricing import overrides, pricing_settings
    raw = json.dumps({'services': SERVICES, 'vorlagen': VORLAGEN, 'overrides': overrides(conn), 'settings': pricing_settings(conn)},
                     ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]


def _check():
    for key, v in VORLAGEN.items():
        for p in v['positions']:
            svc = SERVICES[p['service']]
            assert svc['kind'] != 'paket' or p.get('size') in svc['sizes'], (key, p)
    for z in FRUEHER['zusatz'].values():
        for p in z['positions']:
            assert p['service'] in SERVICES, p
    for text, keys in SEPARATE.items():
        assert all(k in SERVICES for k in keys) and any(text in s['excluded'] for s in SERVICES.values()), text
    for key, svc in SERVICES.items():
        assert set(svc['areas']) <= set(AREAS), key


_check()
