"""Branchenkatalog für die Firmensuche (Sprint B).

Jede Branche hat
- `words`: Wortstämme, die im Firmennamen bzw. in der Branchenangabe vorkommen (für GLEIF, Wikidata, CSV-Import –
  diese Quellen liefern keine oder nur grobe Branchen; die Zuordnung ist deshalb eine Schätzung aus dem Namen),
- `osm`: OpenStreetMap-Merkmale (key, value|None) für die Umkreissuche.
Eigene Schlagwörter des Nutzers werden zusätzlich auf Name und Branche angewendet.
"""
from __future__ import annotations

import re

_I = lambda label, words, osm=(): {'label': label, 'words': tuple(words), 'osm': tuple(osm)}

INDUSTRY_GROUPS = {
    'Handwerk & Bau': {
        'bau': _I('Bauunternehmen & Hochbau', ['bau', 'hochbau', 'tiefbau', 'rohbau', 'bauunternehm'], [('craft', 'builder'), ('office', 'construction_company')]),
        'elektro': _I('Elektroinstallation & Elektrotechnik', ['elektro', 'elektrik', 'electric'], [('craft', 'electrician')]),
        'shk': _I('Sanitär, Heizung, Klima', ['sanitär', 'sanitaer', 'heizung', 'klima', 'haustechnik', 'gebäudetechnik', 'shk'], [('craft', 'plumber'), ('craft', 'hvac')]),
        'dach': _I('Dachdecker & Zimmerei', ['dach', 'zimmerei', 'holzbau'], [('craft', 'roofer'), ('craft', 'carpenter')]),
        'maler': _I('Maler, Lackierer, Stuckateur', ['maler', 'lackier', 'stuck', 'farbe'], [('craft', 'painter'), ('craft', 'plasterer')]),
        'schreiner': _I('Schreinerei & Tischlerei', ['schreiner', 'tischler', 'möbelbau', 'innenausbau'], [('craft', 'joiner'), ('craft', 'cabinet_maker')]),
        'metallbau': _I('Metallbau & Schlosserei', ['metallbau', 'schlosser', 'stahlbau', 'schweiß'], [('craft', 'metal_construction')]),
        'garten': _I('Garten- & Landschaftsbau', ['garten', 'landschaftsbau', 'galabau', 'grün'], [('craft', 'gardener')]),
        'fliesen': _I('Fliesen, Boden, Parkett', ['fliesen', 'parkett', 'boden', 'estrich'], [('craft', 'tiler'), ('craft', 'floorer')]),
        'fenster': _I('Fenster, Türen, Glas', ['fenster', 'glaserei', 'glas', 'rolladen', 'tore'], [('craft', 'glaziery'), ('craft', 'window_construction')]),
        'kfz': _I('Kfz-Werkstatt & Autohaus', ['auto', 'kfz', 'karosserie', 'reifen', 'fahrzeug'], [('shop', 'car'), ('shop', 'car_repair')]),
        'reinigung': _I('Gebäudereinigung & Facility', ['reinigung', 'facility', 'gebäudeservice', 'hausmeister'], [('office', 'cleaning'), ('craft', 'cleaning')]),
    },
    'Industrie & Produktion': {
        'maschinenbau': _I('Maschinen- & Anlagenbau', ['maschinen', 'anlagenbau', 'sondermaschin', 'apparatebau'], [('industrial', None), ('office', 'company')]),
        'automotive': _I('Automobilzulieferer', ['automotive', 'zuliefer', 'fahrzeugteile'], [('industrial', None)]),
        'elektronik': _I('Elektronik & Elektrotechnik (Industrie)', ['elektronik', 'electronic', 'sensor', 'steuerung', 'leiterplatt'], [('industrial', 'electrical')]),
        'kunststoff': _I('Kunststoff & Chemie', ['kunststoff', 'chemie', 'chemical', 'polymer', 'beschicht'], [('industrial', 'chemical')]),
        'metall': _I('Metallverarbeitung & Präzisionsteile', ['metall', 'präzision', 'cnc', 'dreh', 'fräs', 'stanz', 'blech'], [('industrial', 'metal')]),
        'medizintechnik': _I('Medizintechnik', ['medizintechnik', 'medtech', 'medical'], []),
        'lebensmittelind': _I('Lebensmittelherstellung', ['lebensmittel', 'nahrung', 'brauerei', 'bräu', 'molkerei', 'getränke', 'kellerei', 'weingut'], [('craft', 'brewery'), ('craft', 'winery')]),
        'druck': _I('Druckerei & Verpackung', ['druck', 'print', 'verpackung', 'packaging'], [('craft', 'printer'), ('shop', 'copyshop')]),
        'textil': _I('Textil & Bekleidung', ['textil', 'mode', 'bekleidung', 'fashion'], [('shop', 'clothes')]),
        'energie': _I('Energie, Solar, Umwelttechnik', ['energie', 'solar', 'photovoltaik', 'umwelt', 'recycling', 'wasser'], [('office', 'energy_supplier')]),
    },
    'Handel & E-Commerce': {
        'grosshandel': _I('Großhandel & Vertrieb', ['handel', 'großhandel', 'vertrieb', 'trading', 'distribution'], [('office', 'company'), ('shop', 'wholesale')]),
        'einzelhandel': _I('Einzelhandel & Fachgeschäfte', ['shop', 'laden', 'fachgeschäft', 'boutique', 'store'], [('shop', None)]),
        'onlinehandel': _I('Onlinehandel & Versand', ['online', 'versand', 'e-commerce', 'ecommerce', 'webshop'], []),
        'moebel': _I('Möbel, Küchen & Einrichtung', ['möbel', 'küche', 'einricht', 'interior', 'wohn'], [('shop', 'furniture'), ('shop', 'kitchen'), ('shop', 'interior_decoration')]),
        'optik': _I('Optiker, Hörakustik, Juwelier', ['optik', 'brille', 'hörakustik', 'juwelier', 'schmuck', 'uhren'], [('shop', 'optician'), ('shop', 'hearing_aids'), ('shop', 'jewelry')]),
        'blumen': _I('Blumen, Garten, Floristik', ['blumen', 'florist', 'gärtnerei'], [('shop', 'florist'), ('shop', 'garden_centre')]),
        'fahrrad': _I('Fahrrad & Sport', ['fahrrad', 'bike', 'sport', 'outdoor'], [('shop', 'bicycle'), ('shop', 'sports')]),
    },
    'Gastronomie, Hotel & Freizeit': {
        'restaurant': _I('Restaurant, Café, Bar', ['restaurant', 'gaststätte', 'café', 'cafe', 'bistro', 'pizzeria', 'gastro', ' bar '], [('amenity', 'restaurant'), ('amenity', 'cafe'), ('amenity', 'bar')]),
        'hotel': _I('Hotel & Pension', ['hotel', 'pension', 'gasthof', 'hostel', 'apartment'], [('tourism', 'hotel'), ('tourism', 'guest_house')]),
        'baeckerei': _I('Bäckerei, Metzgerei, Konditorei', ['bäcker', 'backhaus', 'metzger', 'fleisch', 'konditor', 'confiserie'], [('shop', 'bakery'), ('shop', 'butcher'), ('shop', 'confectionery')]),
        'catering': _I('Catering & Event', ['catering', 'event', 'veranstalt', 'messe'], [('craft', 'caterer'), ('office', 'event_management')]),
        'fitness': _I('Fitness, Yoga, Sportstudio', ['fitness', 'yoga', 'pilates', 'sportstudio', 'gym'], [('leisure', 'fitness_centre')]),
        'tourismus': _I('Reisebüro & Tourismus', ['reise', 'touristik', 'travel', 'tours'], [('shop', 'travel_agency'), ('office', 'travel_agent')]),
        'kultur': _I('Kultur, Galerie, Theater', ['galerie', 'theater', 'kultur', 'museum', 'kunst'], [('shop', 'art'), ('amenity', 'theatre')]),
    },
    'Gesundheit & Soziales': {
        'arzt': _I('Arztpraxis & MVZ', ['praxis', 'arzt', 'ärzt', 'mvz', 'medizin'], [('amenity', 'doctors'), ('healthcare', 'doctor')]),
        'zahnarzt': _I('Zahnarzt & Kieferorthopädie', ['zahn', 'dental', 'kieferorthop'], [('amenity', 'dentist'), ('healthcare', 'dentist')]),
        'therapie': _I('Physiotherapie & Heilpraktik', ['physio', 'therapie', 'ergotherap', 'logopäd', 'heilprakt', 'osteopath'], [('healthcare', 'physiotherapist'), ('healthcare', 'alternative')]),
        'pflege': _I('Pflegedienst & Seniorenheim', ['pflege', 'senioren', 'betreuung', 'altenheim'], [('amenity', 'nursing_home'), ('healthcare', 'nursing_home')]),
        'apotheke': _I('Apotheke & Sanitätshaus', ['apotheke', 'sanitätshaus', 'orthopädie'], [('amenity', 'pharmacy'), ('shop', 'medical_supply')]),
        'tierarzt': _I('Tierarzt & Tierbedarf', ['tierarzt', 'tierklinik', 'veterinär', 'tierbedarf'], [('amenity', 'veterinary'), ('shop', 'pet')]),
        'kosmetik': _I('Kosmetik, Friseur, Wellness', ['kosmetik', 'friseur', 'beauty', 'wellness', 'nagel', 'hair', 'spa'], [('shop', 'hairdresser'), ('shop', 'beauty'), ('leisure', 'spa')]),
        'sozial': _I('Soziale Träger & Vereine', ['verein', 'e.v.', 'stiftung', 'diakon', 'caritas', 'hilfe'], [('office', 'association'), ('office', 'ngo')]),
    },
    'Dienstleistung & Beratung': {
        'steuer': _I('Steuerberatung & Wirtschaftsprüfung', ['steuer', 'wirtschaftsprüf', 'tax', 'buchhaltung', 'lohn'], [('office', 'tax_advisor'), ('office', 'accountant')]),
        'recht': _I('Rechtsanwälte & Notare', ['rechtsanw', 'anwalt', 'kanzlei', 'notar', 'law', 'legal'], [('office', 'lawyer'), ('office', 'notary')]),
        'beratung': _I('Unternehmensberatung', ['beratung', 'consult', 'management', 'coaching', 'strategie'], [('office', 'consulting')]),
        'personal': _I('Personaldienstleister & Recruiting', ['personal', 'recruit', 'zeitarbeit', 'staffing', 'job'], [('office', 'employment_agency')]),
        'versicherung': _I('Versicherung & Finanzberatung', ['versicher', 'finanz', 'vermögensberat', 'insurance'], [('office', 'insurance'), ('office', 'financial_advisor')]),
        'immobilien': _I('Immobilienmakler & Hausverwaltung', ['immobilien', 'makler', 'hausverwalt', 'real estate', 'wohnbau'], [('office', 'estate_agent'), ('office', 'property_management')]),
        'architektur': _I('Architektur & Innenarchitektur', ['architekt', 'architektur', 'planungsbüro'], [('office', 'architect')]),
        'ingenieur': _I('Ingenieurbüro & Gutachter', ['ingenieur', 'engineering', 'gutacht', 'sachverständ', 'vermessung', 'statik'], [('office', 'engineer'), ('office', 'surveyor')]),
        'logistik': _I('Logistik, Spedition, Umzug', ['logistik', 'spedition', 'transport', 'umzug', 'kurier', 'lager'], [('office', 'logistics'), ('office', 'moving_company')]),
        'sicherheit': _I('Sicherheitsdienst & Gebäudesicherheit', ['sicherheit', 'security', 'wach', 'alarm'], [('office', 'security')]),
        'bildung': _I('Bildung, Schule, Weiterbildung', ['akademie', 'schule', 'bildung', 'training', 'seminar', 'institut', 'fahrschule'], [('amenity', 'driving_school'), ('office', 'educational_institution')]),
        'bestattung': _I('Bestattung', ['bestattung', 'pietät'], [('shop', 'funeral_directors')]),
    },
    'IT, Medien & Kreativ': {
        'software': _I('Software & IT-Dienstleister', ['software', 'it-', ' it ', 'systemhaus', 'informatik', 'digital', 'data', 'cloud', 'tech'], [('office', 'it'), ('office', 'telecommunication')]),
        'agentur': _I('Werbe- & Marketingagentur', ['agentur', 'werbung', 'marketing', 'media', 'kommunikation'], [('office', 'advertising_agency')]),
        'verlag': _I('Verlag, Presse, Medien', ['verlag', 'medien', 'presse', 'publishing', 'redaktion'], [('office', 'publisher'), ('office', 'newspaper')]),
        'foto': _I('Fotografie & Film', ['foto', 'film', 'video', 'studio', 'produktion'], [('craft', 'photographer'), ('shop', 'photo')]),
        'design': _I('Design & Kunsthandwerk', ['design', 'kunsthandwerk', 'atelier', 'manufaktur'], [('craft', None)]),
        'telekom': _I('Telekommunikation & Internet', ['telekom', 'telecom', 'netz', 'internet', 'mobilfunk'], [('office', 'telecommunication')]),
    },
    'Öffentlich & Verbände': {
        'kommune': _I('Kommunen & öffentliche Einrichtungen', ['stadt', 'gemeinde', 'landratsamt', 'verwaltung', 'zweckverband'], [('office', 'government')]),
        'verband': _I('Kammern, Verbände, Innungen', ['kammer', 'verband', 'innung', 'bund ', 'vereinigung'], [('office', 'association')]),
        'kirche': _I('Kirchen & Religionsgemeinschaften', ['kirche', 'kirchengemeinde', 'gemeinde', 'diözese'], [('office', 'religion')]),
    },
}

INDUSTRIES = {k: {**v, 'group': g} for g, items in INDUSTRY_GROUPS.items() for k, v in items.items()}

# Gesellschaften ohne eigenes operatives Geschäft (für die Vorauswahl „nur operative Firmen“)
NON_OPERATIVE_RE = re.compile(
    r'verwaltung|beteiligung|holding|vermögen|vermoegen|grundst|immobilienfonds|fonds|invest|capital|kapital|topco|midco|bidco|holdco|'
    r'treuhand|komplement|stiftung|asset|propert|projekt\s*\d|objekt|vorrats|ventures|equity|\bspv\b|\bsicav\b|portfolio|'
    # v1.14 (Live-Test GLEIF Stuttgart): Besitz-/Grundstücksgesellschaften, Wind-/Solarparks, nummerierte Fonds-Vehikel
    r'grundbesitz|\bbesitz\b|besitzgesellschaft|liegenschaften\s+gmbh|solarpark|windpark|bürgerwind|buergerwind|'
    r'\b(?:II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV)\s+(?:management|verwaltungs|gmbh|kg)\b|\bnr\.\s*\d+\s+kg\b|'
    r'\bvv\s+(?:gmbh|kg)\b|\bfund\b|\.vc\b', re.I)


def catalog():
    return {'groups': [{'group': g, 'items': [{'key': k, 'label': v['label']} for k, v in items.items()]} for g, items in INDUSTRY_GROUPS.items()],
            'notice': 'GLEIF, Wikidata und importierte Listen enthalten kaum Branchenangaben. Dort wird die Branche aus dem Firmennamen geschätzt – '
                      'Firmen mit neutralem Namen (z. B. „Müller GmbH“) erscheinen deshalb nur ohne Branchenfilter.'}


def validate_keys(keys):
    if not isinstance(keys, list) or len(keys) > 40 or any(k not in INDUSTRIES for k in keys):
        raise ValueError('Unbekannte Branche ausgewählt.')
    return list(dict.fromkeys(keys))


def parse_keywords(text):
    if not isinstance(text, str) or len(text) > 400:
        raise ValueError('Schlagwörter: höchstens 400 Zeichen.')
    words = [w.strip().casefold() for w in re.split(r'[,;\n]+', text) if w.strip()]
    if any(not re.fullmatch(r"[\wäöüß .&+\-/]{2,40}", w) for w in words):
        raise ValueError('Schlagwörter: je 2–40 Zeichen, durch Komma getrennt.')
    return words[:20]


def match(text, industry_keys, keywords):
    """Gibt (passt, branchen_key) zurück. Ohne Branchen und Schlagwörter passt alles."""
    if not industry_keys and not keywords:
        return True, ''
    low = f' {(text or "").casefold()} '
    for k in industry_keys:
        if any(w in low for w in INDUSTRIES[k]['words']):
            return True, k
    if any(w in low for w in keywords):
        return True, ''
    return False, ''


def guess(text):
    low = f' {(text or "").casefold()} '
    for k, v in INDUSTRIES.items():
        if any(w in low for w in v['words']):
            return k
    return ''


def osm_selectors(industry_keys):
    sel = []
    for k in industry_keys:
        sel.extend(INDUSTRIES[k]['osm'])
    return list(dict.fromkeys(sel))
