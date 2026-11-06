"""Leistungskatalog & nachvollziehbare Festpreise (Sprint D).

Grundsatz
- Jede Leistung hat Startwerte (Aufwand je Umfang, enthaltene Fremdkosten). Diese Startwerte sind Schätzungen und
  lassen sich im Programm an die eigene Erfahrung anpassen – oder pro Umfang durch einen festen Preis ersetzen.
- Preis je Position = Aufwand × Stundensatz + Puffer + enthaltene Fremdkosten, aufgerundet. Die Herleitung ist intern
  vollständig sichtbar (inkl. effektivem Stundenlohn gegenüber dem Mindestverdienst). Der Kunde sieht Positionen,
  Leistungen, Liefergegenstände und Festpreise – keine Stunden, keine versteckten Aufschläge.
- Laufende Kosten Dritter (Hosting, Lizenzen, Werbebudget, KI-/Telefonminuten) sind nie im Festpreis versteckt,
  sondern werden als „nicht im Festpreis“ ausgewiesen.
"""
from __future__ import annotations

import json
import math
import re

DEFAULT_PRICING = {
    'hourly_rate': 66,         # Kalkulationsstundensatz (€/h)
    'min_hourly_earning': 66,  # Mindestverdienst je Stunde nach Abzug enthaltener Fremdkosten (€/h)
    'buffer_pct': 10,          # Puffer für Abstimmung/Unvorhergesehenes (% auf den Aufwand)
    'day_rate': 528,           # Tagespauschale vor Ort (8 h)
    'half_day_rate': 290,      # Halbtagespauschale vor Ort (4 h, inkl. Rüstzeit)
    'km_rate': 0.50,           # Fahrzeugkosten je km
    'travel_time_pct': 50,     # Anteil der Fahrzeit, der als Arbeitszeit berechnet wird
    'round_to': 10,            # Positionen auf volle … € aufrunden
    'experience_years': 13,
}
SIZE_LABELS = {'S': 'Basis', 'M': 'Standard', 'L': 'Umfangreich'}


def _svc(group, title, desc, kind='paket', sizes=None, unit=None, per_unit_hours=0, per_unit_external=0, min_qty=1, billing='einmalig',
         included=(), deliverables=(), excluded=(), acceptance=(), third_party=(), weeks=''):
    return {'group': group, 'title': title, 'description': desc, 'kind': kind, 'sizes': sizes or {}, 'unit': unit, 'per_unit_hours': per_unit_hours,
            'per_unit_external': per_unit_external, 'min_qty': min_qty, 'billing': billing, 'included': list(included), 'deliverables': list(deliverables),
            'excluded': list(excluded), 'acceptance': list(acceptance), 'third_party': list(third_party), 'weeks': weeks}


def _s(scope, hours, external=0, weeks=''):
    return {'scope': scope, 'hours': hours, 'external': external, 'weeks': weeks}


SERVICES = {
    # ------------------------------------------------ Analyse & Beratung
    'website_analyse': _svc('Analyse & Beratung', 'Webseiten-Analyse & Handlungsbedarf',
        'Unabhängige Analyse der bestehenden Website mit priorisiertem Maßnahmenplan.', sizes={
            'S': _s('Kurz-Check: Startseite und ein Anfrageweg, 1-seitiger Maßnahmenplan', 3, weeks='3 Werktage'),
            'M': _s('Analyse bis 10 Seiten (Technik, Inhalte, Conversion, SEO/GEO), priorisierter Maßnahmenplan, 45-Min.-Besprechung', 8, weeks='1 Woche'),
            'L': _s('Tiefenanalyse inkl. Wettbewerbsvergleich und Workshop zur Umsetzung', 16, weeks='2 Wochen')},
        deliverables=['Analysebericht (PDF) mit Fundstellen', 'Priorisierter Maßnahmenplan'], excluded=['Umsetzung der Maßnahmen'],
        acceptance=['Bericht und Maßnahmenplan liegen vor und wurden besprochen']),
    'workshop': _svc('Analyse & Beratung', 'Strategie- & Konzept-Workshop', 'Gemeinsamer Workshop zu Ziel, Zielgruppe und Umsetzungsplan.', sizes={
            'S': _s('Halbtag (bis 4 Std.) inkl. Vor- und Nachbereitung', 6), 'M': _s('Ganzer Tag (bis 8 Std.) inkl. Vor- und Nachbereitung', 11),
            'L': _s('Zwei Workshop-Tage inkl. Ergebnisdokumentation', 21)},
        deliverables=['Workshop-Dokumentation mit Entscheidungen und nächsten Schritten'], excluded=['Anreise (separate Position)']),
    # ------------------------------------------------ Design & Marke
    'logo': _svc('Design & Marke', 'Logogestaltung', 'Individuell entwickeltes Logo mit Nutzungsrechten für den vereinbarten Zweck.', sizes={
            'S': _s('2 Entwürfe, 1 Korrekturschleife, Druck- und Webdateien', 12, weeks='2 Wochen'),
            'M': _s('3 Entwürfe, 2 Korrekturschleifen, Farb-/Schwarzweiß-Varianten, Favicon', 22, weeks='3 Wochen'),
            'L': _s('Logo inkl. Mini-Styleguide (Farben, Schriften, Anwendungsbeispiele)', 36, weeks='4 Wochen')},
        deliverables=['Logo-Dateien (SVG, PDF, PNG)', 'Einfache Nutzungsrechte für den vereinbarten Einsatz'],
        excluded=['Markenrechtliche Prüfung und Anmeldung'], acceptance=['Freigabe des finalen Entwurfs'],
        third_party=['Markenanmeldung/Recherche über eine Kanzlei bzw. das DPMA nach Bedarf.']),
    'grafik': _svc('Design & Marke', 'Grafikdesign', 'Gestaltung von Medien im bestehenden oder neuen Erscheinungsbild.', sizes={
            'S': _s('Einzelmedium, z. B. Anzeige, Social-Media-Vorlage oder Infografik', 6),
            'M': _s('Geschäftsausstattung: Visitenkarte, Briefbogen, E-Mail-Signatur', 14),
            'L': _s('Vorlagenpaket: Geschäftsausstattung, Präsentation, 5 Social-Media-Vorlagen', 28)},
        deliverables=['Offene und druckfertige Dateien'], excluded=['Druckkosten', 'Bildlizenzen außer frei verfügbaren']),
    'print': _svc('Design & Marke', 'Printdesign & Druckabwicklung', 'Gestaltung von Drucksachen inkl. Druckdatenprüfung und Abwicklung mit der Druckerei.', sizes={
            'S': _s('Flyer oder Plakat, inkl. Standard-Druck kleiner Auflage', 8, 150), 'M': _s('Broschüre bis 8 Seiten inkl. Druck kleiner Auflage', 20, 400),
            'L': _s('Broschüre/Katalog bis 24 Seiten inkl. Druck kleiner Auflage', 45, 900)},
        deliverables=['Druckfertige PDF-Dateien', 'Gedruckte Exemplare in der vereinbarten Auflage'],
        excluded=['Größere Auflagen und Sonderveredelungen (Angebot der Druckerei)'],
        third_party=['Abweichende Auflage oder Papier: Druckkosten nach Angebot der Druckerei, ohne Aufschlag.']),
    'kunst': _svc('Design & Marke', 'Handgestaltete Kunst (Auftragsarbeit)', 'Individuelles, handgefertigtes Kunstwerk nach Briefing – z. B. Bild, Illustration oder Wandgestaltung.', sizes={
            'S': _s('Kleines Format bis A3, inkl. Material', 10, 60, '2 Wochen'), 'M': _s('Mittleres Format bis 100 × 70 cm, inkl. Material', 24, 150, '3–4 Wochen'),
            'L': _s('Großes Format oder Wandgestaltung bis ca. 6 m², inkl. Material', 48, 400, '4–6 Wochen')},
        deliverables=['Fertiges Original', 'Digitale Fotografie des Werks'], excluded=['Rahmung und Transport, wenn nicht vereinbart'],
        acceptance=['Abnahme des Skizzenentwurfs vor Ausführung', 'Übergabe des fertigen Werks']),
    # ------------------------------------------------ Text
    'texte': _svc('Text', 'Website- & Werbetexte', 'Professionelle Texte je Seite bzw. Werbemittel, suchmaschinen- und KI-freundlich formuliert.', kind='menge',
                  unit='Seite/Text', per_unit_hours=3, included=['Kurz-Briefing', 'Text inkl. einer Korrekturschleife'], deliverables=['Fertige Texte als Datei']),
    'fachartikel': _svc('Text', 'Fachartikel / Blogbeitrag', 'Fachartikel mit ca. 1.000 Wörtern inkl. Recherche und Überschriftenstruktur.', kind='menge',
                        unit='Artikel', per_unit_hours=5, deliverables=['Artikel als Datei, optional eingepflegt']),
    # ------------------------------------------------ Web & Shop
    'webdesign': _svc('Web & Shop', 'Webdesign & Website-Umsetzung', 'Gestaltung und Umsetzung einer responsiven Website mit Kontaktweg.', sizes={
            'S': _s('Onepager mit Kontaktformular', 24, weeks='2–3 Wochen'), 'M': _s('Unternehmenswebsite bis 8 Seiten', 60, weeks='4–6 Wochen'),
            'L': _s('Website bis 20 Seiten, mehrsprachig oder mit Blog', 110, weeks='6–10 Wochen')},
        included=['Konzept und Gestaltung', 'Responsive Umsetzung', 'Kontaktformular', 'Grundlegende SEO-Einstellungen', 'Einweisung'],
        deliverables=['Veröffentlichte Website', 'Zugangsdaten und Kurzanleitung'], excluded=['Texte (separate Position)', 'Fotografie (separate Position)'],
        acceptance=['Freigabe des Designs', 'Funktionstest auf Desktop und Smartphone'],
        third_party=['Hosting und Domain: ca. 5–30 € pro Monat, Vertrag direkt mit dem Anbieter.', 'Kostenpflichtige Plugins/Themes nach Bedarf.']),
    'webshop': _svc('Web & Shop', 'Aufbau eines eigenen Webshops', 'Einrichtung eines Onlineshops mit Zahlungsarten, Versand und Rechtstext-Struktur.', sizes={
            'S': _s('Starter-Shop bis 50 Produkte', 50, weeks='4–6 Wochen'), 'M': _s('Shop bis 500 Produkte inkl. Varianten, Zahlungsarten und Versandregeln', 100, weeks='6–10 Wochen'),
            'L': _s('Shop bis 2.000 Produkte mit Import und Schnittstellen', 170, weeks='10–14 Wochen')},
        included=['Shop-Einrichtung und Gestaltung', 'Zahlungs- und Versandeinstellungen', 'Produktimport aus Vorlage', 'Testbestellung und Einweisung'],
        deliverables=['Einsatzbereiter Shop'], excluded=['Produktfotos und -texte (separate Positionen)', 'Rechtsberatung'],
        acceptance=['Testbestellung inkl. Zahlung und Bestellbestätigung erfolgreich'],
        third_party=['Shop-System/Hosting: ca. 20–80 € pro Monat.', 'Gebühren der Zahlungsanbieter je Transaktion.', 'Rechtstexte-Service ca. 10–20 € pro Monat.']),
    'shop_anbindung': _svc('Web & Shop', 'Shop- & Marktplatz-Anbindung', 'Anbindung an einen weiteren Verkaufskanal oder ein System (z. B. Amazon, eBay, Warenwirtschaft, Buchhaltung).',
                           kind='menge', unit='Anbindung', per_unit_hours=16, included=['Einrichtung der Schnittstelle', 'Datenabgleich mit Testartikeln'],
                           acceptance=['Testartikel bzw. -bestellung wird korrekt übertragen'],
                           third_party=['Gebühren der Plattformen bzw. Connector-Abos nach Anbieter.']),
    'pflege': _svc('Web & Shop', 'Website-/Shop-Betreuung (monatlich)', 'Laufende Betreuung: Updates, Sicherungskontrolle und kleine Änderungen.', billing='monatlich', sizes={
            'S': _s('bis 2 Std. pro Monat', 2), 'M': _s('bis 5 Std. pro Monat', 5), 'L': _s('bis 10 Std. pro Monat', 10)},
        included=['Updates und Funktionskontrolle', 'Kleine inhaltliche Änderungen im Stundenrahmen'], excluded=['Nicht genutzte Stunden verfallen zum Monatsende']),
    # ------------------------------------------------ Sichtbarkeit
    'seo_geo': _svc('Sichtbarkeit', 'SEO- & GEO-Optimierung', 'Optimierung für Suchmaschinen und KI-Antwortsysteme (GEO): Technik, Inhalte, strukturierte Daten.', sizes={
            'S': _s('Audit und Basisoptimierung: Technik, Meta-Daten, Indexierung, strukturierte Daten', 10),
            'M': _s('Optimierung bis 10 Seiten inkl. lokaler Sichtbarkeit (Unternehmensprofil)', 24), 'L': _s('Umfassende Optimierung bis 30 Seiten inkl. Inhaltsplan', 45)},
        deliverables=['Umgesetzte Optimierungen mit Protokoll', 'Ausgangsmessung für den Vergleich'], excluded=['Garantie für Rankings oder Nennungen in KI-Antworten']),
    'seo_betreuung': _svc('Sichtbarkeit', 'SEO- & GEO-Betreuung (monatlich)', 'Laufende Optimierung, Monitoring und Monatsbericht.', billing='monatlich', sizes={
            'S': _s('bis 4 Std. pro Monat', 4), 'M': _s('bis 8 Std. pro Monat', 8), 'L': _s('bis 14 Std. pro Monat', 14)},
        deliverables=['Monatsbericht'], excluded=['Ranking-Garantie'], third_party=['SEO-Tool-Lizenzen, falls gewünscht, direkt beim Anbieter.']),
    'werbung': _svc('Sichtbarkeit', 'Werbekampagnen – Einrichtung', 'Konzeption und Einrichtung von Online-Werbung (z. B. Google, Meta, LinkedIn) inkl. Tracking.', sizes={
            'S': _s('1 Kanal, 1 Kampagne', 8), 'M': _s('2 Kanäle inkl. Conversion-Tracking', 16), 'L': _s('3 Kanäle, mehrere Zielgruppen, Landingpage-Abstimmung', 26)},
        excluded=['Werbebudget'], third_party=['Werbebudget wird direkt an die Plattformen gezahlt (nicht im Festpreis).']),
    'werbung_betreuung': _svc('Sichtbarkeit', 'Kampagnenbetreuung (monatlich)', 'Laufende Optimierung und Bericht.', billing='monatlich', sizes={
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
        deliverables=['Fertiges Video in gängigen Formaten', 'Musiklizenz für den vereinbarten Einsatz'], excluded=['Anreise (separate Position)', 'Sprecher, Darsteller']),
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
    'ki_betrieb': _svc('Software & KI', 'Betrieb & Optimierung Chat-/Sprachbot (monatlich)', 'Laufende Auswertung und Verbesserung der Antworten.', billing='monatlich', sizes={
            'S': _s('bis 1 Std. pro Monat', 1), 'M': _s('bis 3 Std. pro Monat', 3), 'L': _s('bis 6 Std. pro Monat', 6)}),
    # ------------------------------------------------ Vor Ort & Aufwand
    'tagessatz': _svc('Vor Ort & Aufwand', 'Tagespauschale vor Ort', 'Arbeitstag beim Kunden (z. B. Workshop, Shooting-Begleitung, Einweisung).', kind='tag', unit='Tag'),
    'anreise': _svc('Vor Ort & Aufwand', 'Anreise', 'Fahrtkosten und anteilige Fahrzeit für Termine vor Ort.', kind='anreise', unit='Fahrt'),
    'aufwand': _svc('Vor Ort & Aufwand', 'Leistung nach Aufwand', 'Für frei vereinbarte Leistungen ohne festen Umfang (Stundensatz).', kind='stunden', unit='Std.'),
}

# Vorlagen: Komplettpakete aus dem bisherigen Katalog als Baukasten-Positionen
TEMPLATES = {
    'pilot': [{'service': 'website_analyse', 'size': 'M'}, {'service': 'aufwand', 'qty': 8, 'title': 'Umsetzung einer klar abgegrenzten Verbesserung'}],
    'conversion': [{'service': 'webdesign', 'size': 'M'}, {'service': 'texte', 'qty': 4}, {'service': 'seo_geo', 'size': 'S'}],
    'brand': [{'service': 'logo', 'size': 'L'}, {'service': 'grafik', 'size': 'M'}],
    'care': [{'service': 'pflege', 'size': 'M'}],
    'portal': [{'service': 'workshop', 'size': 'S'}, {'service': 'software', 'size': 'L'}],
    'automation': [{'service': 'workshop', 'size': 'S'}, {'service': 'software', 'size': 'M'}],
}


# ---------------------------------------------------------------- Einstellungen & eigene Werte

def pricing_settings(conn):
    from .quality import get_setting
    s = get_setting(conn, 'pricing', dict(DEFAULT_PRICING))
    return {k: s.get(k, v) for k, v in DEFAULT_PRICING.items()}


def save_pricing_settings(conn, data):
    from .company_data import _audit
    from .quality import put_setting
    limits = {'hourly_rate': (20, 400), 'min_hourly_earning': (10, 400), 'buffer_pct': (0, 50), 'day_rate': (50, 4000), 'half_day_rate': (30, 2500),
              'km_rate': (0, 3), 'travel_time_pct': (0, 100), 'round_to': (1, 500), 'experience_years': (0, 60)}
    if not isinstance(data, dict) or not data or set(data) - set(limits):
        raise ValueError('Felder: ' + ', '.join(limits))
    for k, v in data.items():
        lo, hi = limits[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi or not math.isfinite(v):
            raise ValueError(f'{k}: Wert zwischen {lo} und {hi}.')
    new = {**pricing_settings(conn), **data}
    put_setting(conn, 'pricing', new)
    _audit(conn, 'pricing', 0, 'kalkulation_geaendert', json.dumps(data, ensure_ascii=False))
    conn.commit()
    return new


def overrides(conn):
    from .quality import get_setting
    return get_setting(conn, 'service_overrides', {})


def save_override(conn, data):
    """Eigene Werte je Leistung/Umfang: Aufwand (h), enthaltene Fremdkosten (€) oder fester Preis (€). None = Startwert."""
    from .company_data import _audit
    from .quality import put_setting
    if not isinstance(data, dict) or set(data) - {'service', 'size', 'hours', 'external', 'fixed_price', 'reset'}:
        raise ValueError('Erwartet: {service, size?, hours?, external?, fixed_price?, reset?}.')
    svc = SERVICES.get(data.get('service'))
    if not svc or svc['kind'] in ('tag', 'anreise', 'stunden'):
        raise ValueError('Für diese Leistung gibt es keine eigenen Katalogwerte (Werte stehen in den Kalkulationsgrundlagen).')
    size = data.get('size') or 'unit'
    if (svc['kind'] == 'paket' and size not in svc['sizes']) or (svc['kind'] == 'menge' and size != 'unit'):
        raise ValueError('Ungültiger Umfang.')
    ov = overrides(conn)
    entry = dict(ov.get(data['service'], {}).get(size, {}))
    if data.get('reset') is True:
        entry = {}
    for k, (lo, hi) in (('hours', (0.1, 2000)), ('external', (0, 100000)), ('fixed_price', (1, 1000000))):
        if k in data:
            v = data[k]
            if v is None:
                entry.pop(k, None)
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ValueError(f'{k}: Wert zwischen {lo} und {hi}.')
            entry[k] = v
    ov.setdefault(data['service'], {})[size] = entry
    if not entry:
        ov[data['service']].pop(size, None)
    put_setting(conn, 'service_overrides', ov)
    _audit(conn, 'pricing', 0, 'katalogwert_geaendert', f"{data['service']}/{size}: {json.dumps(entry, ensure_ascii=False)}")
    conn.commit()
    return catalog(conn)


def _values(conn_ov, key, size):
    svc = SERVICES[key]
    base = svc['sizes'][size] if svc['kind'] == 'paket' else {'hours': svc['per_unit_hours'], 'external': svc['per_unit_external']}
    ov = conn_ov.get(key, {}).get(size if svc['kind'] == 'paket' else 'unit', {})
    return {'hours': ov.get('hours', base['hours']), 'external': ov.get('external', base.get('external', 0)), 'fixed_price': ov.get('fixed_price'),
            'customized': bool(ov)}


def _ceil(value, step):
    return math.ceil(round(value, 6) / step) * step


# ---------------------------------------------------------------- Berechnung

def price_position(p, settings, ov):
    """Berechnet eine Position. Gibt (kunde, intern) zurück."""
    if not isinstance(p, dict) or p.get('service') not in SERVICES:
        raise ValueError('Unbekannte Leistung.')
    allowed = {'service', 'size', 'qty', 'title', 'note', 'km', 'minutes', 'trips', 'days'}
    if set(p) - allowed:
        raise ValueError('Ungültige Felder in einer Position.')
    key, svc = p['service'], SERVICES[p['service']]
    rate, buf, step = settings['hourly_rate'], settings['buffer_pct'] / 100, settings['round_to']
    title = str(p.get('title') or svc['title']).strip()[:140]
    note = str(p.get('note') or '').strip()[:300]
    fixed = None

    def num(name, lo, hi, default=None, integer=False):
        v = p.get(name, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi or (integer and int(v) != v):
            raise ValueError(f'{title}: {name} zwischen {lo} und {hi}.')
        return v

    if svc['kind'] == 'paket':
        size = p.get('size')
        if size not in svc['sizes']:
            raise ValueError(f'{title}: Umfang S, M oder L wählen.')
        v = _values(ov, key, size)
        hours, external, fixed = v['hours'], v['external'], v['fixed_price']
        scope = f"{SIZE_LABELS[size]}: {svc['sizes'][size]['scope']}"
        qty, unit = 1, 'pauschal'
        formula = f"{hours:g} h × {rate:g} €/h + {settings['buffer_pct']:g} % Puffer" + (f" + {external:g} € enthaltene Fremdkosten" if external else '')
    elif svc['kind'] == 'menge':
        qty = num('qty', svc['min_qty'], 10000, svc['min_qty'], integer=True)
        v = _values(ov, key, 'unit')
        hours, external, fixed = v['hours'] * qty, v['external'] * qty, (v['fixed_price'] * qty if v['fixed_price'] else None)
        scope, unit = f"{qty:g} × {svc['unit']}", svc['unit']
        formula = f"{qty:g} × {v['hours']:g} h × {rate:g} €/h + {settings['buffer_pct']:g} % Puffer" + (f" + {external:g} € Fremdkosten" if external else '')
        if v['fixed_price']:
            formula = f"{qty:g} × {v['fixed_price']:g} € fester Stückpreis"
    elif svc['kind'] == 'stunden':
        qty = num('qty', 0.5, 2000, 1)
        hours, external, buf = qty, 0, 0
        scope, unit = f'{qty:g} Std. nach Aufwand', 'Std.'
        formula = f"{qty:g} h × {rate:g} €/h (ohne Puffer, Abrechnung nach tatsächlichem Aufwand, höchstens wie angeboten)"
    elif svc['kind'] == 'tag':
        days = num('days', 0.5, 60, 1)
        if (days * 2) != int(days * 2):
            raise ValueError('Tage in halben Schritten angeben.')
        full, half = int(days), 1 if days % 1 else 0
        fixed = full * settings['day_rate'] + half * settings['half_day_rate']
        hours, external, qty, unit, buf = full * 8 + half * 4, 0, days, 'Tag', 0
        scope = f"{days:g} Tag(e) vor Ort"
        formula = ' + '.join(x for x in (f"{full} × {settings['day_rate']:g} € Tagespauschale" if full else '',
                                         f"1 × {settings['half_day_rate']:g} € Halbtagespauschale" if half else '') if x)
    else:  # anreise
        km = num('km', 1, 2000, None)
        minutes = num('minutes', 0, 1440, 0)
        trips = num('trips', 1, 100, 1, integer=True)
        external = trips * 2 * km * settings['km_rate']
        hours = trips * 2 * minutes / 60 * settings['travel_time_pct'] / 100
        buf = 0
        qty, unit = trips, 'Fahrt'
        scope = f"{trips:g} Fahrt(en) · je {km:g} km einfach · ca. {minutes:g} Min. Fahrzeit"
        formula = (f"{trips:g} × 2 × {km:g} km × {str(round(settings['km_rate'], 2)).replace('.', ',')} € + {trips:g} × 2 × {minutes:g} Min. × {rate:g} €/h × "
                   f"{settings['travel_time_pct']:g} % Fahrzeit")
    labor = hours * rate
    buffer = labor * buf
    calc = labor + buffer + external
    price = float(fixed) if fixed is not None else _ceil(calc, step)
    if svc['kind'] == 'anreise':
        price = _ceil(calc, 1)
    if svc['kind'] == 'stunden':
        price = round(calc, 2)  # nach Aufwand: exakt Stunden × Satz, nicht aufgerundet
    earning = (price - external) / hours if hours else None
    customer = {'service': key, 'title': title, 'scope': scope, 'note': note, 'quantity': qty, 'unit': unit, 'billing': svc['billing'],
                'price_eur': round(price, 2), 'description': svc['description'], 'included': svc['included'], 'deliverables': svc['deliverables'],
                'excluded': svc['excluded'], 'acceptance': svc['acceptance'], 'third_party': svc['third_party'],
                'weeks': (svc['sizes'].get(p.get('size'), {}).get('weeks') if svc['kind'] == 'paket' else '') or svc['weeks']}
    internal = {'service': key, 'title': title, 'hours': round(hours, 2), 'rate': rate, 'labor_eur': round(labor, 2), 'buffer_eur': round(buffer, 2),
                'external_eur': round(external, 2), 'calculated_eur': round(calc, 2), 'price_eur': round(price, 2),
                'fixed': fixed is not None and svc['kind'] != 'tag', 'formula': formula, 'effective_hourly': round(earning, 2) if earning is not None else None}
    return customer, internal


def build_quote(conn, data):
    allowed = {'positions', 'tax_mode', 'project_label', 'customer_goal', 'assumptions', 'template'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Ungültige Angebotsdaten.')
    positions = data.get('positions')
    if not isinstance(positions, list) or not 1 <= len(positions) <= 40:
        raise ValueError('Bitte 1–40 Positionen zusammenstellen.')
    mode = data.get('tax_mode', 'offen')
    if mode not in ('offen', 'regel_19', 'kleinunternehmer'):
        raise ValueError('Steuerstatus ungültig.')
    text = lambda k, n: re.sub(r'\s+', ' ', str(data.get(k) or '')).strip()[:n]
    settings, ov = pricing_settings(conn), overrides(conn)
    cust, intern = [], []
    for p in positions:
        c, i = price_position(p, settings, ov)
        cust.append(c)
        intern.append(i)
    once = round(sum(c['price_eur'] for c in cust if c['billing'] == 'einmalig'), 2)
    monthly = round(sum(c['price_eur'] for c in cust if c['billing'] == 'monatlich'), 2)
    billing = 'monatlich' if monthly and not once else ('gemischt' if monthly else 'einmalig')
    base = once if once else monthly
    if mode == 'regel_19':
        vat, tax_note = round(base * 0.19, 2), 'Zuzüglich 19 % Umsatzsteuer'
    elif mode == 'kleinunternehmer':
        vat, tax_note = 0.0, 'Keine Umsatzsteuer ausgewiesen (Anwendung § 19 UStG vor Verwendung prüfen)'
    else:
        vat, tax_note = 0.0, 'Umsatzsteuerstatus offen – Angebot vor Versand steuerlich vervollständigen'
    uniq = lambda key: list(dict.fromkeys(x for c in cust for x in c[key]))
    weeks = [c['weeks'] for c in cust if c['weeks']]
    from .sales_workspace import PACKAGES
    titles = list(dict.fromkeys(c['title'] for c in cust if c['service'] not in ('anreise', 'tagessatz', 'aufwand'))) or [cust[0]['title']]
    label = text('project_label', 140) or (PACKAGES[data['template']]['title'] if data.get('template') in PACKAGES else
                                           ' & '.join(titles[:2]) + (' u. a.' if len(titles) > 2 else ''))[:140]
    goal = text('customer_goal', 500) or cust[0]['description']
    customer = {
        'mode': 'baukasten', 'project_label': label, 'package': data.get('template') or 'baukasten', 'package_title': 'Individuelles Angebot', 'goal': goal,
        'positions': cust, 'included': [f"{c['title']} – {c['scope']}" for c in cust], 'deliverables': uniq('deliverables'),
        'excluded': uniq('excluded'), 'acceptance_criteria': uniq('acceptance'), 'third_party_costs': uniq('third_party'),
        'assumptions': text('assumptions', 1000), 'weeks': weeks[0] if len(set(weeks)) == 1 else ('nach Absprache' if not weeks else ' / '.join(dict.fromkeys(weeks))),
        'billing': billing, 'revision_rounds': 2, 'net_eur': base, 'once_net_eur': once, 'monthly_net_eur': monthly,
        'vat_eur': vat, 'total_eur': round(base + vat, 2), 'tax_mode': mode, 'tax_note': tax_note,
        'payment_plan': ('40 % bei Beauftragung, 60 % nach Abnahme' if once else '') + ('; ' if once and monthly else '') +
                        ('Monatliche Leistungen monatlich im Voraus, Laufzeit und Kündigungsfrist ausdrücklich vereinbaren' if monthly else ''),
        'change_requests': 'Zusätzliche Leistungen nur nach gesondertem, transparentem Angebot und Freigabe.',
        'guarantee': 'Keine Umsatz-, Ranking- oder Lead-Garantie; Abnahme nach den vereinbarten Liefergegenständen.',
    }
    hours = round(sum(i['hours'] for i in intern), 2)
    ext = round(sum(i['external_eur'] for i in intern), 2)
    total_price = round(sum(i['price_eur'] for i in intern), 2)
    earning = round((total_price - ext) / hours, 2) if hours else None
    de = lambda v: f"{v:.2f}".replace('.', ',')
    warn = [f"{i['title']}: {de(i['effective_hourly'])} €/h liegt unter deinem Mindestverdienst von {settings['min_hourly_earning']:g} €/h"
            for i in intern if i['effective_hourly'] is not None and i['effective_hourly'] < settings['min_hourly_earning'] - 0.005]
    internal = {'mode': 'baukasten', 'positions': intern, 'estimated_hours': hours, 'external_cost_eur': ext, 'total_price_eur': total_price,
                'effective_hourly': earning, 'min_hourly_earning': settings['min_hourly_earning'], 'hourly_rate': settings['hourly_rate'],
                'buffer_pct': settings['buffer_pct'], 'warnings': warn, 'ok': not warn,
                'basis': f"Stundensatz {settings['hourly_rate']:g} €/h · Puffer {settings['buffer_pct']:g} % · aufgerundet auf {settings['round_to']:g} € · "
                         f"Mindestverdienst {settings['min_hourly_earning']:g} €/h · {settings['experience_years']:g} Jahre Erfahrung"}
    return {'customer': customer, 'internal': internal}


def catalog(conn):
    settings, ov = pricing_settings(conn), overrides(conn)
    groups = {}
    for key, svc in SERVICES.items():
        entry = {'key': key, 'title': svc['title'], 'description': svc['description'], 'kind': svc['kind'], 'billing': svc['billing'],
                 'unit': svc['unit'], 'min_qty': svc['min_qty']}
        if svc['kind'] == 'paket':
            entry['sizes'] = {}
            for size, s in svc['sizes'].items():
                v = _values(ov, key, size)
                _, i = price_position({'service': key, 'size': size}, settings, ov)
                entry['sizes'][size] = {'label': SIZE_LABELS[size], 'scope': s['scope'], **v, 'price_eur': i['price_eur'], 'effective_hourly': i['effective_hourly']}
        elif svc['kind'] == 'menge':
            v = _values(ov, key, 'unit')
            _, i = price_position({'service': key, 'qty': 1 if svc['min_qty'] <= 1 else svc['min_qty']}, settings, ov)
            entry['unit_values'] = {**v, 'price_eur': i['price_eur'] / (1 if svc['min_qty'] <= 1 else svc['min_qty'])}
        groups.setdefault(svc['group'], []).append(entry)
    return {'groups': [{'group': g, 'services': items} for g, items in groups.items()], 'settings': settings, 'templates': TEMPLATES,
            'notice': 'Startwerte sind Schätzungen für eine erfahrene Einzelagentur. Passe Aufwand, enthaltene Fremdkosten oder feste Preise je Umfang an deine Erfahrung an.'}


def route_pricing(h, conn, method, route, query):
    if not route.startswith('/api/pricing/'):
        return False
    if route == '/api/pricing/catalog' and method == 'GET':
        h._send(200, catalog(conn))
        return True
    if route == '/api/pricing/settings' and method == 'PUT':
        h._send(200, save_pricing_settings(conn, h._body()))
        return True
    if route == '/api/pricing/overrides' and method == 'PUT':
        h._send(200, save_override(conn, h._body()))
        return True
    if route == '/api/pricing/preview' and method == 'POST':
        h._send(200, build_quote(conn, h._body()))
        return True
    m = re.fullmatch(r'/api/pricing/templates/(\w+)', route)
    if m and method == 'GET':
        if m.group(1) not in TEMPLATES:
            raise LookupError('Vorlage nicht gefunden.')
        h._send(200, {'template': m.group(1), 'positions': TEMPLATES[m.group(1)]})
        return True
    return False
