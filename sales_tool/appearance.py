"""2.0.0-dev11: Darstellung – Theme, Hell/Dunkel und Dichte.

Gespeichert wird in ``app_settings`` unter ``ui_appearance``; der Browser hält eine Kopie, damit
die Seite schon vor dem ersten Zeichnen richtig gefärbt ist (``public/theme.js``). Maßgeblich ist
der Wert hier: so bleibt die Wahl auch nach einem Portwechsel oder in einem anderen Browser erhalten.
"""

from .quality import get_setting, put_setting

KEY = 'ui_appearance'
THEMES = (
    {'id': 'klassisch', 'label': 'Klassisch', 'hint': 'Petrol und Mint – der bisherige Stand.'},
    {'id': 'schiefer', 'label': 'Schiefer', 'hint': 'Kühles Grau mit blauem Akzent, sehr ruhig.'},
    {'id': 'sand', 'label': 'Sand', 'hint': 'Warme Erdtöne mit Terrakotta-Akzent.'},
    {'id': 'kontrast', 'label': 'Kontrast', 'hint': 'Kräftige Linien, keine Pastelltöne – für helle Räume und müde Augen.'},
)
MODES = (
    {'id': 'system', 'label': 'Wie System'},
    {'id': 'hell', 'label': 'Hell'},
    {'id': 'dunkel', 'label': 'Dunkel'},
)
DENSITIES = (
    {'id': 'normal', 'label': 'Normal'},
    {'id': 'kompakt', 'label': 'Kompakt', 'hint': 'Weniger Abstand, mehr Zeilen auf dem Bildschirm.'},
)
DEFAULT = {'theme': 'klassisch', 'mode': 'system', 'density': 'normal'}
_ALLOWED = {'theme': {t['id'] for t in THEMES}, 'mode': {m['id'] for m in MODES},
            'density': {d['id'] for d in DENSITIES}}


def load(conn):
    stored = get_setting(conn, KEY, dict(DEFAULT))
    if not isinstance(stored, dict):
        return dict(DEFAULT)
    # Unbekannte Werte (etwa aus einer späteren Version) fallen still auf die Vorgabe zurück.
    return {k: stored.get(k) if stored.get(k) in _ALLOWED[k] else DEFAULT[k] for k in DEFAULT}


def save(conn, data):
    if not isinstance(data, dict):
        raise ValueError('Ungültige Darstellung.')
    current = load(conn)
    for key in DEFAULT:
        if key not in data:
            continue
        value = str(data[key] or '').strip().lower()
        if value not in _ALLOWED[key]:
            raise ValueError(f'Unbekannter Wert für {key}: {value or "leer"}.')
        current[key] = value
    put_setting(conn, KEY, current)
    return current


def payload(conn):
    return {'appearance': load(conn), 'themes': list(THEMES), 'modes': list(MODES), 'densities': list(DENSITIES)}


def route(h, conn, method, path):
    if path != '/api/ui/appearance':
        return False
    if method == 'GET':
        h._send(200, payload(conn))
        return True
    if method in ('PUT', 'POST'):
        save(conn, h._body(max_len=2048))
        h._send(200, payload(conn))
        return True
    return False
