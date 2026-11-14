"""Nachvollziehbare Festpreise aus dem zentralen Leistungskatalog (Sprint D, seit 2.0.0-dev16 mit catalog.py).

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

# 2.0.0-dev16 (M12): Leistungen und Vorlagen stehen im zentralen Katalog (catalog.py); hier nur die Kalkulation.
from .catalog import SEPARATE, SERVICES, TEMPLATES, VORLAGEN, revisions_text  # noqa: F401

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
    'deposit_pct': 40,         # 2.0.0-dev16: Anzahlung bei Beauftragung (%), Rest nach Abnahme – eine Vorgabe, keine Vereinbarung
}
SIZE_LABELS = {'S': 'Basis', 'M': 'Standard', 'L': 'Umfangreich'}


# ---------------------------------------------------------------- Einstellungen & eigene Werte

def pricing_settings(conn):
    from .quality import get_setting
    s = get_setting(conn, 'pricing', dict(DEFAULT_PRICING))
    return {k: s.get(k, v) for k, v in DEFAULT_PRICING.items()}


def save_pricing_settings(conn, data):
    from .company_data import _audit
    from .quality import put_setting
    limits = {'hourly_rate': (20, 400), 'min_hourly_earning': (10, 400), 'buffer_pct': (0, 50), 'day_rate': (50, 4000), 'half_day_rate': (30, 2500),
              'km_rate': (0, 3), 'travel_time_pct': (0, 100), 'round_to': (1, 500), 'experience_years': (0, 60), 'deposit_pct': (0, 90)}
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
    """Eigene Werte je Leistung/Umfang: Aufwand (h), enthaltene Fremdkosten (€), fester Preis (€) oder Korrekturschleifen
    (2.0.0-dev16). None = Startwert."""
    from .company_data import _audit
    from .quality import put_setting
    if not isinstance(data, dict) or set(data) - {'service', 'size', 'hours', 'external', 'fixed_price', 'revisions', 'reset'}:
        raise ValueError('Erwartet: {service, size?, hours?, external?, fixed_price?, revisions?, reset?}.')
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
    for k, (lo, hi) in (('hours', (0.1, 2000)), ('external', (0, 100000)), ('fixed_price', (1, 1000000)), ('revisions', (0, 10))):
        if k in data:
            v = data[k]
            if v is None:
                entry.pop(k, None)
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi or (k == 'revisions' and int(v) != v):
                raise ValueError(f'{k}: Wert zwischen {lo} und {hi}' + (' (ganze Zahl).' if k == 'revisions' else '.'))
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
    base = svc['sizes'][size] if svc['kind'] == 'paket' else {'hours': svc['per_unit_hours'], 'external': svc['per_unit_external'], 'revisions': svc['revisions']}
    ov = conn_ov.get(key, {}).get(size if svc['kind'] == 'paket' else 'unit', {})
    return {'hours': ov.get('hours', base['hours']), 'external': ov.get('external', base.get('external', 0)), 'fixed_price': ov.get('fixed_price'),
            'revisions': ov.get('revisions', base.get('revisions')), 'customized': bool(ov)}


def _ceil(value, step):
    return math.ceil(round(value, 6) / step) * step


# ---------------------------------------------------------------- Berechnung

def price_position(p, settings, ov):
    """Berechnet eine Position. Gibt (kunde, intern) zurück."""
    if not isinstance(p, dict) or p.get('service') not in SERVICES:
        raise ValueError('Unbekannte Leistung.')
    allowed = {'service', 'size', 'qty', 'title', 'note', 'km', 'minutes', 'trips', 'days', 'optional'}
    if set(p) - allowed:
        raise ValueError('Ungültige Felder in einer Position.')
    if not isinstance(p.get('optional', False), bool):
        raise ValueError('optional: ja oder nein.')
    optional = p.get('optional', False)  # 2.0.0-dev22 (M15): optionale Position – nie im Festpreis, nie in einer Rechnung
    key, svc = p['service'], SERVICES[p['service']]
    rate, buf, step = settings['hourly_rate'], settings['buffer_pct'] / 100, settings['round_to']
    title = str(p.get('title') or svc['title']).strip()[:140]
    note = str(p.get('note') or '').strip()[:300]
    fixed = None
    revisions, rev_unit = None, None

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
        hours, external, fixed, revisions = v['hours'], v['external'], v['fixed_price'], v['revisions']
        scope = f"{SIZE_LABELS[size]}: {svc['sizes'][size]['scope']}"
        qty, unit = 1, 'pauschal'
        formula = f"{hours:g} h × {rate:g} €/h + {settings['buffer_pct']:g} % Puffer" + (f" + {external:g} € enthaltene Fremdkosten" if external else '')
    elif svc['kind'] == 'menge':
        qty = num('qty', svc['min_qty'], 10000, svc['min_qty'], integer=True)
        v = _values(ov, key, 'unit')
        hours, external, fixed = v['hours'] * qty, v['external'] * qty, (v['fixed_price'] * qty if v['fixed_price'] else None)
        scope, unit = f"{qty:g} × {svc['unit']}", svc['unit']
        revisions, rev_unit = v['revisions'], svc['unit']
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
    rev = revisions_text(revisions, rev_unit)
    if rev:
        scope = f'{scope} · {rev}'
    customer = {'service': key, 'title': title, 'scope': scope, 'note': note, 'quantity': qty, 'unit': unit, 'billing': svc['billing'],
                'price_eur': round(price, 2), 'description': svc['description'], 'included': svc['included'], 'deliverables': svc['deliverables'],
                'excluded': svc['excluded'], 'acceptance': svc['acceptance'], 'third_party': svc['third_party'],
                'weeks': (svc['sizes'].get(p.get('size'), {}).get('weeks') if svc['kind'] == 'paket' else '') or svc['weeks'], 'optional': optional,
                'revisions': revisions, 'revisions_text': rev}
    internal = {'service': key, 'title': title, 'hours': round(hours, 2), 'rate': rate, 'labor_eur': round(labor, 2), 'buffer_eur': round(buffer, 2),
                'external_eur': round(external, 2), 'calculated_eur': round(calc, 2), 'price_eur': round(price, 2),
                'fixed': fixed is not None and svc['kind'] != 'tag', 'formula': formula, 'effective_hourly': round(earning, 2) if earning is not None else None,
                'areas': svc['areas'], 'revisions_open': svc['korrekturen'] and revisions is None, 'optional': optional}
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
    # 2.0.0-dev22 (M15 Teil 2): optionale Positionen stehen im Angebot, zählen aber weder im Festpreis noch in Summen
    every = cust
    opts = [(n, c) for n, c in enumerate(cust, 1) if c['optional']]
    cust_core = [c for c in cust if not c['optional']]
    if not cust_core:
        raise ValueError('Mindestens eine Position muss fest im Angebot stehen – optionale Positionen ergänzen nur.')
    once = round(sum(c['price_eur'] for c in cust_core if c['billing'] == 'einmalig'), 2)
    monthly = round(sum(c['price_eur'] for c in cust_core if c['billing'] == 'monatlich'), 2)
    billing = 'monatlich' if monthly and not once else ('gemischt' if monthly else 'einmalig')
    base = once if once else monthly
    if mode == 'regel_19':
        vat, tax_note = round(base * 0.19, 2), 'Zuzüglich 19 % Umsatzsteuer'
    elif mode == 'kleinunternehmer':
        vat, tax_note = 0.0, 'Keine Umsatzsteuer ausgewiesen (Anwendung § 19 UStG vor Verwendung prüfen)'
    else:
        vat, tax_note = 0.0, 'Umsatzsteuerstatus offen – Angebot vor Versand steuerlich vervollständigen'
    uniq = lambda key: list(dict.fromkeys(x for c in cust_core for x in c[key]))
    weeks = [c['weeks'] for c in cust_core if c['weeks']]
    present = {c['service'] for c in cust_core}
    tpl = VORLAGEN.get(data.get('template'))
    titles = list(dict.fromkeys(c['title'] for c in cust if c['service'] not in ('anreise', 'tagessatz', 'aufwand'))) or [cust[0]['title']]
    label = text('project_label', 140) or (tpl['title'] if tpl else ' & '.join(titles[:2]) + (' u. a.' if len(titles) > 2 else ''))[:140]
    goal = text('customer_goal', 500) or (tpl['outcome'] if tpl else cust[0]['description'])
    # 2.0.0-dev16: Korrekturschleifen je Position zusammengeführt (K01); fehlende Angaben nur intern als offener Punkt
    revisions = [{'position': n, 'title': c['title'], 'text': c['revisions_text']} for n, c in enumerate(cust, 1) if c['revisions_text'] and not c['optional']]
    deposit = settings['deposit_pct']
    once_plan = ('Zahlung nach Abnahme' if not deposit else f'{deposit:g} % bei Beauftragung, {100 - deposit:g} % nach Abnahme')
    customer = {
        'mode': 'baukasten', 'project_label': label, 'package': data.get('template') or 'baukasten', 'package_title': 'Individuelles Angebot', 'goal': goal,
        'positions': every, 'included': [f"{c['title']} – {c['scope']}" for c in cust_core], 'deliverables': uniq('deliverables'),
        'options': [{'position': n, 'title': c['title'], 'scope': c['scope'], 'price_eur': c['price_eur'], 'billing': c['billing']} for n, c in opts],
        'options_note': ('Optionale Positionen sind nicht im Festpreis enthalten. Gewünschte Optionen nehmen wir vor der Beauftragung '
                         'in eine überarbeitete Fassung auf – so wird nichts doppelt berechnet.') if opts else '',
        'excluded': [x for x in uniq('excluded') if not (x in SEPARATE and all(k in present for k in SEPARATE[x]))],
        'acceptance_criteria': uniq('acceptance'), 'third_party_costs': uniq('third_party'),
        'assumptions': text('assumptions', 1000), 'weeks': weeks[0] if len(set(weeks)) == 1 else ('nach Absprache' if not weeks else ' / '.join(dict.fromkeys(weeks))),
        # 2.0.0-dev13 (Review K01): Korrekturschleifen stehen je Leistung im Umfang – keine pauschale Zahl, die ihm widerspricht
        'billing': billing, 'revision_rounds': None, 'revisions': revisions,
        'revision_note': '; '.join(f"Pos. {r['position']} {r['title']}: {r['text']}" for r in revisions),
        'net_eur': base, 'once_net_eur': once, 'monthly_net_eur': monthly,
        'vat_eur': vat, 'total_eur': round(base + vat, 2), 'tax_mode': mode, 'tax_note': tax_note,
        'deposit_pct': deposit if once else None,
        'payment_plan': (once_plan if once else '') + ('; ' if once and monthly else '') +
                        ('Monatliche Leistungen monatlich im Voraus, Laufzeit und Kündigungsfrist ausdrücklich vereinbaren' if monthly else ''),
        'change_requests': 'Zusätzliche Leistungen nur nach gesondertem, transparentem Angebot und Freigabe.',
        'guarantee': 'Keine Umsatz-, Ranking- oder Lead-Garantie; Abnahme nach den vereinbarten Liefergegenständen.',
    }
    core = [i for i in intern if not i['optional']]
    hours = round(sum(i['hours'] for i in core), 2)
    ext = round(sum(i['external_eur'] for i in core), 2)
    total_price = round(sum(i['price_eur'] for i in core), 2)
    earning = round((total_price - ext) / hours, 2) if hours else None
    de = lambda v: f"{v:.2f}".replace('.', ',')
    warn = [f"{i['title']}: {de(i['effective_hourly'])} €/h liegt unter deinem Mindestverdienst von {settings['min_hourly_earning']:g} €/h"
            for i in intern if i['effective_hourly'] is not None and i['effective_hourly'] < settings['min_hourly_earning'] - 0.005]
    from .catalog import AREAS, AREA_CHECKS, fingerprint
    areas = list(dict.fromkeys(a for i in intern for a in i['areas'] if AREA_CHECKS.get(a)))
    open_points = [f"Korrekturschleifen für Pos. {n} {i['title']} sind nicht festgelegt – im Katalog ergänzen oder im Umfang vereinbaren."
                   for n, i in enumerate(intern, 1) if i['revisions_open']]
    if once:
        open_points.append(f'Zahlungsplan „{once_plan}“ ist die Vorgabe aus deinen Kalkulationsgrundlagen – mit dem Kunden ausdrücklich vereinbaren.')
    internal = {'mode': 'baukasten', 'positions': intern, 'estimated_hours': hours, 'external_cost_eur': ext, 'total_price_eur': total_price,
                'effective_hourly': earning, 'min_hourly_earning': settings['min_hourly_earning'], 'hourly_rate': settings['hourly_rate'],
                'buffer_pct': settings['buffer_pct'], 'warnings': warn, 'ok': not warn, 'open_points': open_points,
                'checks': [{'area': a, 'label': AREAS[a], 'items': AREA_CHECKS[a]} for a in areas], 'catalog_version': fingerprint(conn),
                'basis': f"Stundensatz {settings['hourly_rate']:g} €/h · Puffer {settings['buffer_pct']:g} % · aufgerundet auf {settings['round_to']:g} € · "
                         f"Mindestverdienst {settings['min_hourly_earning']:g} €/h · {settings['experience_years']:g} Jahre Erfahrung"}
    return {'customer': customer, 'internal': internal}


def catalog(conn):
    settings, ov = pricing_settings(conn), overrides(conn)
    groups = {}
    for key, svc in SERVICES.items():
        entry = {'key': key, 'title': svc['title'], 'description': svc['description'], 'kind': svc['kind'], 'billing': svc['billing'],
                 'unit': svc['unit'], 'min_qty': svc['min_qty'], 'areas': svc['areas'], 'korrekturen': svc['korrekturen']}
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
    from .catalog import AREAS, herkunft, vorlagen, fingerprint
    tpl = vorlagen(conn)
    return {'groups': [{'group': g, 'services': items} for g, items in groups.items()], 'settings': settings, 'templates': TEMPLATES,
            'vorlagen': tpl, 'herkunft': herkunft(current={v['key']: v for v in tpl}), 'areas': AREAS, 'version': fingerprint(conn),
            'notice': 'Startwerte sind Schätzungen für eine erfahrene Einzelagentur. Passe Aufwand, enthaltene Fremdkosten, feste Preise oder '
                      'Korrekturschleifen je Umfang an deine Erfahrung an. Änderungen gelten für alle künftigen Angebote und Empfehlungen; '
                      'gespeicherte Angebote bleiben unverändert.'}


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
