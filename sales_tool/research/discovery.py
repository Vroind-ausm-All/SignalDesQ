"""Discovery auf bekannten Websites (R1.3, 2.0.0-dev69).

Gezielte Seitensuche auf der Website einer Firma, die schon bekannt ist – keine Voll-Scans:
- Kandidaten kommen aus den Links der Startseite und aus der Sitemap (``/sitemap.xml``, höchstens eine Unter-Sitemap) bzw.
  einem RSS/Atom-Feed, der auf der Startseite verlinkt ist. Jede dieser Dateien ist ein gewöhnlicher Abruf über
  ``research.fetchers.fetch`` (Source Registry, robots.txt, IP-Pinning, Größengrenze, Jobbudget).
- Reihenfolge: Impressum, Management/Geschäftsführung, Team, Presse, Kontakt, Karriere, Berichte – vor Produktseiten.
- XML wird mit der Standardbibliothek gelesen; jede DTD (``<!DOCTYPE``/``<!ENTITY``) wird abgewiesen. Damit gibt es weder
  externe Entitäten (XXE) noch Entitäten-Bomben. Eine neue Abhängigkeit (defusedxml, feedparser) ist dafür nicht nötig.
"""
from __future__ import annotations

import gzip
import io
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_XML = 2_000_000          # Bytes je Sitemap/Feed (nach dem Entpacken)
MAX_ENTRIES = 5_000          # Einträge, die höchstens gelesen werden
SKIP_EXT = ('.pdf', '.zip', '.exe', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.mp4', '.mp3', '.css', '.js', '.xml', '.gz')

# Bereich → Schlüsselwörter (Pfad oder Linktext). Kleinere Zahl = früher abrufen.
CATEGORIES = (
    ('impressum', ('impressum', 'imprint', 'legal-notice', 'rechtliches', 'anbieterkennzeichnung')),
    ('management', ('geschaeftsfuehrung', 'geschäftsführung', 'geschaeftsleitung', 'management', 'vorstand', 'leadership', 'fuehrung', 'inhaber')),
    ('team', ('team', 'mitarbeiter', 'ansprechpartner', 'people', 'unser-team', 'wir-ueber-uns', 'ueber-uns', 'über-uns', 'about')),
    ('presse', ('presse', 'press', 'news', 'aktuelles', 'neuigkeiten', 'blog', 'meldungen')),
    ('kontakt', ('kontakt', 'contact', 'standorte', 'anfahrt')),
    ('karriere', ('karriere', 'career', 'jobs', 'stellen', 'stellenangebote', 'ausbildung')),
    ('berichte', ('bericht', 'report', 'nachhaltigkeit', 'investor', 'jahresabschluss', 'geschaeftsbericht')),
)
RANK = {name: i for i, (name, _) in enumerate(CATEGORIES)}
OTHER = len(CATEGORIES)  # Produkt- und sonstige Seiten zuletzt


class XmlRejected(ValueError):
    pass


def _site(url):
    host = (urlsplit(url).hostname or '').lower()
    return host[4:] if host.startswith('www.') else host


def same_site(a, b):
    return _site(a) == _site(b) and bool(_site(a))


def safe_xml(data):
    """Bytes → ElementTree-Wurzel. Lehnt DTDs, zu große und kaputte Dateien ab; entpackt gzip mit Größenbremse."""
    if not isinstance(data, (bytes, bytearray)):
        raise XmlRejected('keine Bytes')
    if data[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
            data = gz.read(MAX_XML + 1)
    if len(data) > MAX_XML:
        raise XmlRejected('XML zu groß')
    head = bytes(data[:4096]).lower()
    if b'<!doctype' in head or b'<!entity' in bytes(data).lower():
        raise XmlRejected('XML mit DTD/Entitäten abgewiesen (Schutz vor XXE und Entitäten-Bomben)')
    try:
        return ET.fromstring(bytes(data))
    except ET.ParseError as exc:
        raise XmlRejected(f'kein gültiges XML: {exc}') from exc


def _local(tag):
    return tag.rsplit('}', 1)[-1].lower() if isinstance(tag, str) else ''


def _clean(url, origin):
    href = urljoin(origin, (url or '').strip())
    p = urlsplit(href)
    if p.scheme not in ('http', 'https') or not same_site(origin, href) or p.path.lower().endswith(SKIP_EXT):
        return ''
    return urlunsplit((p.scheme, p.netloc, p.path or '/', p.query, ''))


def parse_sitemap(data, origin):
    """Sitemap oder Sitemap-Index → (Seiten, Unter-Sitemaps); nur dieselbe Website."""
    root = safe_xml(data)
    pages, subs, n = [], [], 0
    kind = _local(root.tag)
    for el in root.iter():
        if _local(el.tag) != 'loc' or not (el.text or '').strip():
            continue
        n += 1
        if n > MAX_ENTRIES:
            break
        raw = el.text.strip()
        if kind == 'sitemapindex':
            href = urljoin(origin, raw)
            if same_site(origin, href) and urlsplit(href).scheme in ('http', 'https'):
                subs.append(href)
        else:
            url = _clean(raw, origin)
            if url:
                pages.append(url)
    return list(dict.fromkeys(pages)), list(dict.fromkeys(subs))


def parse_feed(data, origin):
    """RSS 2.0 oder Atom → Links der Einträge (nur dieselbe Website)."""
    root = safe_xml(data)
    out = []
    for el in root.iter():
        name = _local(el.tag)
        if name == 'link':
            url = el.get('href') or (el.text or '')
            url = _clean(url, origin)
            if url:
                out.append(url)
        if len(out) >= MAX_ENTRIES:
            break
    return list(dict.fromkeys(out))


def category(url, text=''):
    label = (urlsplit(url).path + ' ' + (text or '')).lower()
    for name, keys in CATEGORIES:
        if any(k in label for k in keys):
            return name
    return ''


def plan(origin, candidates, limit):
    """Kandidaten (Liste von (url, linktext)) → höchstens ``limit`` Adressen: je Bereich zuerst eine, dann weitere."""
    best = {}
    for url, text in candidates:
        url = _clean(url, origin)
        if not url or url.rstrip('/') == origin.rstrip('/'):
            continue
        cat = category(url, text)
        rank = RANK.get(cat, OTHER)
        depth = urlsplit(url).path.strip('/').count('/')
        key = (rank, depth, len(url))
        if url not in best or key < best[url][0]:
            best[url] = (key, cat)
    ordered = sorted(best.items(), key=lambda kv: kv[1][0])
    first, seen = [], set()
    for url, (key, cat) in ordered:
        if cat and cat not in seen:
            seen.add(cat)
            first.append(url)
    rest = [u for u, (key, cat) in ordered if u not in first and cat]
    tail = [u for u, (key, cat) in ordered if not cat]
    return (first + rest + tail)[:max(0, limit)]


def feed_links_in(links, origin):
    """Feed-Adressen unter den Links der Startseite (rss/atom/feed im Pfad oder Text)."""
    out = []
    for link in links or []:
        href = urljoin(origin, str(link.get('href', '')))
        label = (urlsplit(href).path + ' ' + str(link.get('text', ''))).lower()
        if same_site(origin, href) and re.search(r'\b(rss|atom|feed)\b|/feed/?$|\.rss$', label):
            out.append(href)
    return list(dict.fromkeys(out))[:1]


def discover(origin, links, fetch, limit, sitemap=True):
    """Gezielte Kandidaten für ``limit`` Seiten. ``fetch(url) -> (final_url, content_type, bytes)`` (wirft bei Fehlern).
    Gibt (urls, hinweise) zurück; Fehler beim Lesen von Sitemap oder Feed sind Hinweise, kein Abbruch."""
    candidates = [(urljoin(origin, str(l.get('href', ''))), str(l.get('text', ''))) for l in (links or [])]
    notes = []
    if sitemap and limit > 0:
        try:
            _, _, data = fetch(urljoin(origin, '/sitemap.xml'))
            pages, subs = parse_sitemap(data, origin)
            if not pages and subs:  # Index: nur die eine Unter-Sitemap, die nach Seiten klingt – kein Voll-Scan
                sub = next((s for s in subs if re.search(r'page|seite', s, re.I)), subs[0])
                _, _, data = fetch(sub)
                pages, _ = parse_sitemap(data, origin)
            candidates += [(u, '') for u in pages]
            notes.append(f'Sitemap: {len(pages)} Adressen')
        except Exception as exc:  # noqa: BLE001 – fehlende Sitemap ist normal
            notes.append(f'Sitemap nicht genutzt: {str(exc)[:120]}')
        for feed in feed_links_in(links, origin):
            try:
                _, _, data = fetch(feed)
                candidates += [(u, '') for u in parse_feed(data, origin)]
                notes.append('Feed gelesen')
            except Exception as exc:  # noqa: BLE001
                notes.append(f'Feed nicht genutzt: {str(exc)[:120]}')
    return plan(origin, candidates, limit), notes
