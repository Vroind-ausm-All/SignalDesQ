"""Source Registry (R1.1, 2.0.0-dev69): jede Quelle, die SignalDesk selbst abruft, steht hier – sonst kein Abruf.

Je Quelle: ID, Betreiber, Zweck, Zugriffsart, erlaubte Felder, Lizenz/Nutzungsbedingungen, Prüfdatum, Freigabe, Rate/TTL,
Speicher- und Exportrechte, Rechtsgrundlage und Verantwortlicher.

Prüfstände (``review``):
- ``freigegeben``: geprüft und vom Eigentümer freigegeben (Entscheidung E2, mit Datum).
- ``vorlaeufig``: eingetragen, läuft, aber noch nicht vom Eigentümer freigegeben. Die Oberfläche sagt das.
- ``ungeprueft``: neu eingetragen, noch nicht geprüft – immer aus, auch nicht einschaltbar.
- ``gesperrt``: nur manuell im Browser der Nutzerin; SignalDesk ruft diese Hosts nie ab (CLAUDE.md, Regel 7).

Durchsetzung serverseitig an den beiden Abrufwegen:
- offene Schnittstellen über ``lead_finder.fetch_source`` (Host muss zu einer eingetragenen Schnittstelle gehören),
- Firmen-Websites über ``research.fetchers.fetch`` und den Browser-Abruf (``check_url``).
Je Organisation kann die Verwaltung eine erlaubte Quelle ausschalten und wieder einschalten (Einstellung ``source_policies``,
mit Audit-Eintrag). Einschalten geht nur bei ``freigegeben`` oder ``vorlaeufig``.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

SETTING = 'source_policies'
REVIEWS = ('freigegeben', 'vorlaeufig', 'ungeprueft', 'gesperrt')
ALLOWED_REVIEWS = ('freigegeben', 'vorlaeufig')
WEBSITE = 'firmenwebsite'


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    operator: str
    purpose: str
    access: str                 # 'api' (offene Schnittstelle), 'website' (öffentliche Firmen-Website) oder 'manuell'
    hosts: tuple                # Hosts, die zu dieser Quelle gehören (Subdomains eingeschlossen)
    fields: tuple               # Felder, die übernommen werden dürfen
    license: str
    terms_url: str
    checked: str                # Prüfdatum der Angaben (JJJJ-MM)
    review: str                 # Prüfstand, siehe oben
    approved_by: str            # wer freigegeben hat ('' solange E2 offen)
    rate: str                   # eigene Bremse und Grenze des Anbieters
    ttl_hours: int              # wie lange ein Ergebnis wiederverwendet wird
    storage: str                # Speicherrecht
    export: str                 # Exportrecht
    legal_basis: str            # Rechtsgrundlage
    owner: str                  # verantwortlich für die Pflege des Eintrags
    personal_data: str = 'keine'

    def view(self):
        d = asdict(self)
        d['hosts'], d['fields'] = list(self.hosts), list(self.fields)
        return d


_UNTERNEHMEN = 'Art. 6 Abs. 1 lit. f DSGVO, nur Unternehmensdaten; Personendaten werden verworfen'
_PRUEFUNG = 'Eigentümer (E2)'
_FREIGABE = 'Eigentümer, Entscheidung E2 vom 26.11.2026'

REGISTRY: dict[str, Source] = {s.id: s for s in (
    Source('wikidata', 'Wikidata (SPARQL)', 'Wikimedia Foundation', 'Firmen nach Ort und Branche finden', 'api',
           ('query.wikidata.org',), ('name', 'rechtsform', 'ort', 'website', 'branche', 'mitarbeiterzahl', 'wikidata_id'),
           'CC0 1.0', 'https://www.wikidata.org/wiki/Wikidata:Licensing', '2026-11', 'freigegeben', _FREIGABE,
           'eigene Bremse: 10 s Abstand, 40 Abfragen je Tag; Anbieter: 60 s Abfragezeit, 429/503 bei Überlast', 24,
           'erlaubt (CC0)', 'erlaubt (CC0)', _UNTERNEHMEN, _PRUEFUNG),
    Source('osm', 'OpenStreetMap (Overpass)', 'OpenStreetMap Foundation / Overpass-Betreiber', 'lokale Firmen mit Website finden', 'api',
           ('overpass-api.de', 'overpass.kumi.systems', 'overpass.private.coffee'),
           ('name', 'rechtsform', 'anschrift', 'website', 'kategorie', 'osm_id'),
           'ODbL 1.0', 'https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances', '2026-11', 'freigegeben', _FREIGABE,
           'eigene Bremse: 10 s Abstand, 40 Abfragen je Tag; Anbieter: Fair Use (< 10.000 Abfragen, < 1 GB je Tag)', 24,
           'erlaubt mit Namensnennung', 'nur mit ODbL-Hinweis (Namensnennung, Share-Alike)', _UNTERNEHMEN, _PRUEFUNG,
           'Einträge ohne Rechtsform werden ausgefiltert (mögliche Einzelpersonen)'),
    Source('nominatim', 'Nominatim (Ortssuche)', 'OpenStreetMap Foundation', 'Ort oder PLZ in Koordinaten für den Umkreis umrechnen', 'api',
           ('nominatim.openstreetmap.org',), ('ort', 'koordinaten', 'begrenzung'),
           'ODbL 1.0', 'https://operations.osmfoundation.org/policies/nominatim/', '2026-11', 'freigegeben', _FREIGABE,
           'Anbieter: höchstens 1 Anfrage je Sekunde, keine Massenabfragen; Ergebnis je Ort zwischengespeichert', 24,
           'nur Ortsangaben', 'nicht exportiert', 'keine Personendaten (nur Orte)', _PRUEFUNG),
    Source('gleif', 'GLEIF (LEI-Schnittstelle)', 'Global Legal Entity Identifier Foundation', 'amtlichen Namen, Anschrift, Register prüfen', 'api',
           ('api.gleif.org',), ('name', 'rechtsform', 'anschrift', 'registergericht', 'registernummer', 'lei'),
           'CC0 1.0', 'https://www.gleif.org/en/meta/lei-data-terms-of-use', '2026-11', 'freigegeben', _FREIGABE,
           'eigene Bremse: 10 s Abstand, 40 Abfragen je Tag; Anbieter: 60 Anfragen je Minute', 24,
           'erlaubt (CC0)', 'erlaubt (CC0)', 'keine Personendaten (nur juristische Personen)', _PRUEFUNG),
    Source('ted', 'TED (EU-Ausschreibungen)', 'Amt für Veröffentlichungen der EU', 'öffentliche Ausschreibungen finden', 'api',
           ('api.ted.europa.eu',), ('auftraggeber', 'titel', 'cpv', 'frist', 'ort', 'bekanntmachung'),
           'CC BY 4.0 / Metadaten CC0', 'https://ted.europa.eu/de/legal-notice', '2026-11', 'freigegeben', _FREIGABE,
           'eigene Bremse: 10 s Abstand, 40 Abfragen je Tag; Anbieter: Begrenzung möglich', 24,
           'erlaubt mit Quellenangabe', 'nur mit Quellenangabe © Europäische Union', _UNTERNEHMEN, _PRUEFUNG,
           'Kontaktpersonen der Vergabestelle werden nicht übernommen'),
    Source(WEBSITE, 'Öffentliche Firmen-Websites', 'die jeweilige Firma', 'Impressum, Website-Bewertung, Karriereseite, Ansprechpartner-Kandidaten',
           'website', (), ('impressumsangaben', 'seitentext_mit_beleg', 'stellenanzeigen', 'kandidaten_zur_pruefung'),
           'je Website; robots.txt nach RFC 9309 wird beachtet', 'https://www.rfc-editor.org/rfc/rfc9309', '2026-11', 'freigegeben', _FREIGABE,
           'einzelne Seiten, keine Voll-Scans; Pausen zwischen Abrufen; Größen- und Zeitgrenzen je Abruf', 0,
           'nur übernommene Werte mit Fundstelle', 'Firmendaten ja; Kandidaten nie ohne menschliche Prüfung',
           'Art. 6 Abs. 1 lit. f DSGVO; Personen nur als Kandidaten bis zur Prüfung (CLAUDE.md, Regel 5)', _PRUEFUNG,
           'Kandidaten bleiben außerhalb der CRM-Kontakte'),
    # Nur manuell: SignalDesk ruft diese Hosts nie ab (Begründungen in docs/LEADQUELLEN_V11.md)
    Source('linkedin_xing', 'LinkedIn / XING', 'LinkedIn Corp. / New Work SE', 'nur manuell im eigenen Browser', 'manuell',
           ('linkedin.com', 'xing.com'), (), 'Nutzungsbedingungen untersagen automatisches Auslesen', 'https://www.linkedin.com/legal/user-agreement',
           '2026-11', 'gesperrt', '', 'kein automatischer Abruf', 0, '–', '–', 'personenbezogene Profile', 'Engineering',
           'Profile sind Personendaten'),
    Source('suchmaschinen_karten', 'Suchmaschinen und Google Maps', 'Google, Microsoft u. a.', 'nur manuell im eigenen Browser', 'manuell',
           ('google.com', 'google.de', 'maps.google.com', 'bing.com', 'duckduckgo.com'), (),
           'Nutzungsbedingungen untersagen Scraping', 'https://policies.google.com/terms', '2026-11', 'gesperrt', '',
           'kein automatischer Abruf', 0, '–', '–', '–', 'Engineering'),
    Source('branchenbuecher', 'Gelbe Seiten, Das Örtliche, 11880', 'die jeweiligen Verlage', 'nur einzeln nachschlagen', 'manuell',
           ('gelbeseiten.de', 'dasoertliche.de', '11880.com'), (), 'AGB und Datenbankherstellerrecht (§ 87b UrhG)',
           'https://www.gelbeseiten.de/', '2026-11', 'gesperrt', '', 'kein automatischer Abruf', 0, '–', '–', '–', 'Engineering'),
    Source('handelsregister', 'Handelsregister / Unternehmensregister', 'Länderjustiz / Bundesanzeiger Verlag', 'einzelne Firmen manuell prüfen',
           'manuell', ('handelsregister.de', 'unternehmensregister.de', 'bundesanzeiger.de'), (),
           'Nutzungsordnung: höchstens 60 Abrufe je Stunde, keine Massenabfragen', 'https://www.handelsregister.de/', '2026-11', 'gesperrt', '',
           'kein automatischer Abruf', 0, '–', '–', '–', 'Engineering'),
)}

_LOCK = threading.Lock()
_BY_DB: dict[str, dict] = {}   # Datenbank → {quelle: False}; nur Abweichungen (ausgeschaltet) stehen drin
_CURRENT: dict = {}            # gilt, wo kein Mandant gesetzt ist (Einzelplatz, direkte Aufrufe in Tests)


class SourceBlocked(PermissionError):
    """Abruf einer Quelle, die nicht in der Registry steht, nicht freigegeben oder für diese Organisation aus ist."""

    def __init__(self, message, source=''):
        super().__init__(message)
        self.source = source


def _host_matches(host, pattern):
    return host == pattern or host.endswith('.' + pattern)


def source_for_host(host):
    host = (host or '').lower().rstrip('.')
    for src in REGISTRY.values():
        if any(_host_matches(host, p) for p in src.hosts):
            return src
    return None


def _disabled(key=None):
    from .. import tenancy
    key = key or tenancy.current()
    with _LOCK:
        if key is None or key in _BY_DB:
            return dict(_BY_DB.get(key, _CURRENT) if key else _CURRENT)
    # Mandant gesetzt, aber noch nicht geladen: aus seiner eigenen Datenbank lesen – nie den Stand einer anderen Organisation
    # übernehmen (Regel 8). Fehlt die Datei, gelten die Registry-Stände.
    return _load_key(key)


def _load_key(key):
    off = {}
    if not key.startswith(':memory:') and Path(key).exists():
        try:
            with contextlib.closing(sqlite3.connect(key, timeout=5)) as raw:
                row = raw.execute('SELECT value_json FROM app_settings WHERE key=?', (SETTING,)).fetchone()
            off = _clean(json.loads(row[0])) if row else {}
        except (sqlite3.Error, ValueError):
            off = {}
    with _LOCK:
        _BY_DB.setdefault(key, off)
        return dict(_BY_DB[key])


def enabled(source_id, key=None):
    src = REGISTRY.get(source_id)
    if src is None or src.review not in ALLOWED_REVIEWS:
        return False
    return _disabled(key).get(source_id, True) is not False


def _reason(src):
    if src is None:
        return 'Quelle steht nicht in der Source Registry – kein Abruf.'
    if src.review == 'gesperrt':
        return f'{src.title}: nur manuell nutzbar – SignalDesk ruft diese Quelle nie ab.'
    if src.review == 'ungeprueft':
        return f'{src.title}: noch nicht geprüft und freigegeben – kein Abruf.'
    return f'{src.title} ist für diese Organisation ausgeschaltet (Einstellungen → Datenquellen).'


def assert_allowed(source_id, key=None):
    src = REGISTRY.get(source_id)
    if not enabled(source_id, key):
        raise SourceBlocked(_reason(src), source_id)
    return src


def check_api_url(url, key=None):
    """Offene Schnittstellen: der Host muss zu einer eingetragenen Schnittstelle gehören, die erlaubt ist."""
    src = source_for_host(urlsplit(url).hostname)
    if src is None or src.access != 'api':
        raise SourceBlocked(_reason(src if src is not None and src.access == 'manuell' else None), src.id if src else '')
    return assert_allowed(src.id, key)


def check_url(url, key=None):
    """Firmen-Websites: gesperrte Hosts nie; Hosts einer Schnittstelle nach deren Regel; sonst die Regel „Firmen-Website“."""
    src = source_for_host(urlsplit(url).hostname)
    return assert_allowed(src.id if src is not None else WEBSITE, key)


# ---------------------------------------------------------------- je Organisation

def _clean(values):
    if not isinstance(values, dict):
        return {}
    return {k: False for k, v in values.items() if k in REGISTRY and isinstance(v, dict) and v.get('enabled') is False}


def load(conn):
    from .. import tenancy
    from ..quality import get_setting
    key = tenancy.conn_key(conn)
    off = _clean(get_setting(conn, SETTING, {}))
    with _LOCK:
        _BY_DB[key] = off
        _CURRENT.clear()
        _CURRENT.update(off)
    return off


def reset():
    with _LOCK:
        _BY_DB.clear()
        _CURRENT.clear()


def set_enabled(conn, source_id, value, by=''):
    from .. import tenancy
    from ..company_data import _audit
    from ..quality import get_setting, put_setting
    if not isinstance(value, bool):
        raise ValueError('enabled: true/false.')
    src = REGISTRY.get(source_id)
    if src is None:
        raise LookupError('Quelle steht nicht in der Source Registry.')
    if value and src.review not in ALLOWED_REVIEWS:
        raise SourceBlocked(_reason(src), source_id)
    stored = get_setting(conn, SETTING, {})
    stored = dict(stored) if isinstance(stored, dict) else {}
    stored[source_id] = {'enabled': value, 'by': str(by)[:80]}
    put_setting(conn, SETTING, {k: v for k, v in stored.items() if k in REGISTRY})
    _audit(conn, 'source_policy', 0, 'quelle_ein' if value else 'quelle_aus', f'{source_id} ({by or "ohne Anmeldung"})')
    conn.commit()
    load(conn)
    return view(conn, tenancy.conn_key(conn))


def view(conn=None, key=None):
    """Quellenstatus für Einstellungen → Datenquellen: Registry-Eintrag, Stand je Organisation, letzter Abruf."""
    from .. import tenancy
    key = key or (tenancy.conn_key(conn) if conn is not None else None)
    measured = {}
    if conn is not None:
        try:
            for r in conn.execute("""SELECT source, MAX(CASE WHEN status='done' THEN finished_at END) last_ok,
                                            MAX(CASE WHEN status='failed' THEN finished_at END) last_failed
                                     FROM discovery_runs GROUP BY source"""):
                measured[r['source']] = {'last_success': r['last_ok'] or '', 'last_failure': r['last_failed'] or ''}
        except Exception:  # noqa: BLE001 – Tabelle fehlt in sehr alten Datenbanken
            pass
    rows = []
    for src in REGISTRY.values():
        rows.append({**src.view(), 'enabled': enabled(src.id, key), 'switchable': src.review in ALLOWED_REVIEWS,
                     'measured': measured.get(src.id, {'last_success': '', 'last_failure': ''})})
    open_e2 = [s.id for s in REGISTRY.values() if s.review == 'vorlaeufig']
    return {'sources': rows, 'pending_approval': open_e2,
            'notice': ('Vorläufig heißt: Bestand vor der Source Registry, läuft weiter, bis der Eigentümer die Quelle freigibt (E2). '
                       'Nicht eingetragene oder gesperrte Quellen ruft SignalDesk nie ab.') if open_e2 else ''}


def route_sources(h, conn, method, route, user=None):
    import re
    if route == '/api/sources' and method == 'GET':
        h._send(200, view(conn))
        return True
    m = re.fullmatch(r'/api/sources/([a-z_]+)', route)
    if m and method == 'PUT':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'enabled'}:
            raise ValueError('Erwartet: {enabled: true/false}.')
        try:
            h._send(200, set_enabled(conn, m.group(1), body['enabled'], by=(user or {}).get('username', '') if isinstance(user, dict) else ''))
        except LookupError as exc:
            h._error(str(exc), 404)
        except SourceBlocked as exc:
            h._error(str(exc), 403)
        return True
    return False
