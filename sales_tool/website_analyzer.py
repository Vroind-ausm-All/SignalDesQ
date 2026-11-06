"""Conservative public-website reader; never browse the local network.

Requires optional Playwright/Chromium. Public webpages are *untrusted input*.
This is a personal local research tool, not a high-volume crawler or SSRF sandbox.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

AGENT = "SignalDeskResearch/0.3 (+manual B2B site review)"
MAX_PAGES = 5
MAX_TEXT = 5500


class CrawlError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CrawlError("Automatische robots.txt-Weiterleitung verweigert.")


def public_url(url: str) -> str:
    """Accept DNS hostnames whose current addresses are globally routable (Implementierung: research.safe_urls).

    Seit v1.15 verbindet der HTTP-Abruf sich zusätzlich genau mit der hier geprüften Adresse (IP-Pinning), sodass eine
    zweite DNS-Antwort nicht mehr auf ein internes Ziel zeigen kann. Für den Team-Betrieb bleibt ein Netzwerkfilter sinnvoll.
    """
    from .research.safe_urls import public_url as _public_url
    return _public_url(url)


def same_company_host(a: str, b: str) -> bool:
    def base(x):
        h = urlsplit(x).hostname or ""
        return h[4:] if h.startswith("www.") else h
    return base(a) == base(b)


def robots_allowed(url: str) -> bool:
    """robots.txt nach RFC 9309 (Weiterleitungen geprüft, 4xx = erlaubt, 5xx = gesperrt, je Website zwischengespeichert)."""
    from .research import settings
    if settings.get()['fetcher'] == 'legacy':
        return legacy_robots_allowed(url)
    from .research.fetchers.http import robots_check
    return robots_check(url)[0]  # Verbindungsfehler werden als CrawlError gemeldet (nicht als robots-Verbot)


def legacy_robots_allowed(url: str) -> bool:
    """robots.txt-Prüfung bis v1.14 (ohne Weiterleitungen, 403 = Fehler) – nur für Vergleich/Rückfall."""
    p = urlsplit(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    opener = build_opener(NoRedirect)
    try:
        with opener.open(Request(robots_url, headers={"User-Agent": AGENT}), timeout=6) as response:
            content = response.read(200001)
            if len(content) > 200000:
                raise CrawlError("robots.txt ist zu groß.")
    except HTTPError as exc:
        if exc.code in (404, 410):
            return True
        raise CrawlError(f"robots.txt nicht abrufbar (HTTP {exc.code}); keine Analyse.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CrawlError("robots.txt nicht prüfbar; Analyse vorsorglich abgebrochen.") from exc
    parser = RobotFileParser()
    parser.parse(content.decode("utf-8", "replace").splitlines())
    return parser.can_fetch(AGENT, url)


def derive_links(origin: str, links: list[dict], purpose: str = "website") -> list[str]:
    """Deterministically prefer up to four high-value pages, no off-site crawling."""
    candidates = []
    for link in links:
        href = urljoin(origin, str(link.get("href", "")))
        if not same_company_host(origin, href) or urlsplit(href).scheme not in ("http", "https"):
            continue
        p = urlsplit(href)
        if p.path.lower().endswith((".pdf", ".zip", ".exe", ".jpg", ".png")):
            continue
        label = (str(link.get("text", "")) + " " + p.path).lower()
        groups = (("team", "people", "mitarbeiter", "ansprechpartner", "management", "geschaeftsfuehr", "geschäftsführ", "leadership"),
                  ("kontakt", "contact", "ansprech", "directory"),
                  ("ueber-uns", "über-uns", "about", "unternehmen", "impressum"),
                  ("marketing", "presse", "press", "leistungen", "services", "produkte", "solutions")) if purpose in ("contacts", "full") else (
                  ("leistung", "service", "solution", "angebot", "services"),
                  ("produkt", "product", "software", "plattform"),
                  ("kontakt", "contact", "anfrage", "demo"),
                  ("karriere", "career", "jobs", "about", "unternehmen"))
        rank = next((i for i, keys in enumerate(groups) if any(x in label for x in keys)), None)
        if rank is None:
            continue
        full = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
        if full != origin and full not in [x[1] for x in candidates]:
            candidates.append((rank, full))
    return [u for _, u in sorted(candidates)[:MAX_PAGES-1]]


MIN_STATIC_TEXT = 200  # Zeichen: darunter gilt eine Seite als „ohne ausreichenden statischen Inhalt“


def crawl_site(url: str, purpose: str = "website") -> dict:
    """Bis zu fünf Seiten derselben Firma lesen – seit v1.15 HTTP zuerst (Masterplan 2.0, Sprint 1).
    Der Browser (Playwright, JavaScript aus) wird nur genutzt, wenn er installiert und eingeschaltet ist UND der
    statische Abruf keinen ausreichenden Text liefert. Kein Klicken, Absenden oder Anmelden."""
    if purpose not in ('website', 'contacts', 'full'):
        raise CrawlError('Unbekannter Recherchetyp.')
    initial = public_url(url)
    if not robots_allowed(initial):
        raise CrawlError("Die Website untersagt diesen Abruf in robots.txt.")
    from .research import settings
    from .research.fetchers import browser
    static, static_error = None, None
    try:
        static = light_crawl(initial, purpose)
    except CrawlError as exc:
        static_error = exc
    thin = static is None or sum(len(p.get("text", "")) for p in static["pages"]) < MIN_STATIC_TEXT
    if thin and settings.get()["browser_fallback"] and browser.available():
        rendered = browser.crawl(initial, purpose, MAX_PAGES, MAX_TEXT, robots_allowed, public_url, same_company_host, derive_links, CrawlError)
        if rendered and rendered["pages"] and (static is None or sum(len(p["text"]) for p in rendered["pages"]) > sum(len(p["text"]) for p in static["pages"])):
            return {"source": initial, "pages": rendered["pages"], "renderer": "browser",
                    "warnings": ["Statischer Abruf lieferte zu wenig Text – mit dem Browser gelesen (JavaScript aus)."] + rendered["errors"][:9]}
    if static is None:
        raise static_error
    return static


def light_crawl(url: str, purpose: str = "website") -> dict:
    """Rückfall ohne Browser (v1.11): bis zu fünf Seiten derselben Firma per HTTP lesen – mit robots.txt, SSRF-Schutz
    und Größenlimit aus dem Impressums-Abruf. JavaScript-Inhalte fehlen; das steht in den Hinweisen."""
    from . import imprint
    pages, errors, queue, seen = [], [], [public_url(url)], set()
    while queue and len(pages) < MAX_PAGES:
        requested = queue.pop(0)
        if requested in seen:
            continue
        seen.add(requested)
        try:
            final, ctype, data = imprint.FETCH(requested, pages[0]["url"] if pages else None)
            if not same_company_host(url, final):
                raise CrawlError("Weiterleitung zu einer anderen Domain blockiert.")
            if "html" not in (ctype or "html"):
                raise CrawlError("Keine HTML-Seite.")
            from .research.fetchers.base import decode_html
            from .research.parse import parse_html
            parsed = parse_html(decode_html(data) if isinstance(data, bytes) else data, final)
            text, links = parsed["text"], parsed["links"]
            clean = re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]
            if not clean:
                raise CrawlError("Kein sichtbarer Seitentext.")
            from .research.extractors.content import main_text
            main = main_text(decode_html(data) if isinstance(data, bytes) else data, final)
            pages.append({"url": final, "title": parsed["title"], "text": clean, "main_text": main["text"][:MAX_TEXT], "content_engine": main["engine"],
                          "raw_text": text[:MAX_TEXT] if purpose in ("contacts", "full") else "",
                          "headings": parsed["headings"], "form_count": parsed["forms"], "parser": parsed["engine"]})
            if len(pages) == 1:
                queue.extend(derive_links(final, links, purpose))
        except Exception as exc:
            errors.append(f"{requested}: {str(exc)[:160]}")
    if not pages:
        raise CrawlError("Keine nutzbaren öffentlichen Inhalte gefunden. " + "; ".join(errors[:2]))
    return {"source": public_url(url), "pages": pages, "renderer": "html",
            "warnings": ["Ohne Browser gelesen (kein JavaScript) – dynamische Inhalte können fehlen."] + errors[:9]}
