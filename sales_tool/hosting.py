"""Betriebsgrenzen im Server für mehrere Organisationen (SDQ-037, Prüfbericht F05/F06).

Im Einzelplatz und im Team-Betrieb gilt nichts davon. ``register(db_path)`` ruft der Mehrmandanten-Server je Organisation auf;
für deren Anfragen und Aufträge sind serverseitig (nicht nur in der Oberfläche) gesperrt:

- der ältere Website-Abruf ohne IP-Pinning (``fetcher=legacy``),
- der Browser (Chromium) für Website-Recherche und Website-Bewertung – er baut Verbindungen selbst auf,
- Kalender- und Postfachserver auf lokalen, privaten oder nicht öffentlichen Adressen, unverschlüsseltes HTTP/IMAP und
  Sonderports,
- das Wiederherstellen einer hochgeladenen oder lokalen Sicherungsdatei über die Weboberfläche (Betreiber: ``zurueckspielen``).

Die Netzgrenze selbst (Ausgangsregeln, Metadaten-Adressen) gehört zusätzlich in die Firewall des Servers.
"""
from __future__ import annotations

# Datenbanken (Schlüssel aus ``tenancy.db_key``), die der Mehrmandanten-Server bedient. Die Grenzen gelten für Anfragen und
# Aufträge dieser Organisationen – ein Einzelplatz im selben Prozess (Tests) bleibt unberührt.
_HOSTED: set = set()
RESTORE_MESSAGE = ('Wiederherstellen aus einer Datei ist im Server für mehrere Organisationen gesperrt. Der Betreiber spielt '
                   'geprüfte Sicherungssätze mit „betreiber … zurueckspielen“ zurück.')
CALDAV_PORTS = (443,)
IMAP_PORTS = (993,)


LIMITS = {'fetcher': ('http',), 'browser_fallback': (False,), 'nlp': (False,)}  # R2.5: kein Sprachmodell im Server für mehrere Organisationen


def register(db_path):
    """Organisation als gehostet kennzeichnen (Mehrmandanten-Server, je Organisation einmal)."""
    from . import tenancy
    _HOSTED.add(tenancy.db_key(db_path))


def unregister_all():  # Tests
    _HOSTED.clear()


def hosted(key=None):
    from . import tenancy
    key = key or tenancy.current()
    return bool(key) and key in _HOSTED


def browser_allowed():
    return not hosted()


def check_service_host(host, port, ports, what):
    """Kalender-/Postfachserver im gehosteten Betrieb: öffentlicher Name, nur übliche verschlüsselte Ports, jede Adresse
    öffentlich. Wirft ValueError (Einzelplatz: keine Prüfung)."""
    if not hosted():
        return
    from .research.safe_urls import UnsafeURL, check_url, resolve_public
    from .website_analyzer import CrawlError
    if port not in ports:
        raise ValueError(f'{what}: im Server nur Port {", ".join(map(str, ports))} (verschlüsselt).')
    try:
        check_url(f'https://{host}/', ports=(443,))
        resolve_public(host, port)
    except (UnsafeURL, CrawlError) as exc:
        raise ValueError(f'{what}: nur öffentliche Server erlaubt ({exc}).') from exc
