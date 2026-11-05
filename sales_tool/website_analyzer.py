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
    """Accept DNS hostnames whose current addresses are globally routable.

    DNS rebinding cannot be fully prevented at application level: run only on a
    trusted PC and never expose this research server to an untrusted network.
    """
    if not isinstance(url, str) or len(url) > 2048:
        raise CrawlError("Ungültige URL.")
    url = url.strip()
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or
            parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 80, 443)):
        raise CrawlError("Nur öffentliche HTTP(S)-Websites ohne Login, Fragment oder Sonderport erlaubt.")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
        raise CrawlError("Lokale und interne Hostnamen sind gesperrt.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            raise CrawlError("Bitte einen öffentlichen Domainnamen verwenden.")
    else:
        raise CrawlError("IP-Adressen sind als Analyseziel gesperrt.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CrawlError("Domain konnte nicht aufgelöst werden.") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise CrawlError("Interne, private oder nicht öffentliche IP-Adresse erkannt.")
    # Drop fragments; normalize hostname, leave path and query untouched.
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def same_company_host(a: str, b: str) -> bool:
    def base(x):
        h = urlsplit(x).hostname or ""
        return h[4:] if h.startswith("www.") else h
    return base(a) == base(b)


def robots_allowed(url: str) -> bool:
    p = urlsplit(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    # A deliberately small, non-redirecting robots request, max 200 KB.
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


def crawl_site(url: str, purpose: str = "website") -> dict:
    """Browse up to five same-company pages; don't click, submit or authenticate."""
    if purpose not in ('website','contacts','full'):
        raise CrawlError('Unbekannter Recherchetyp.')
    initial = public_url(url)
    if not robots_allowed(initial):
        raise CrawlError("Die Website untersagt diesen Abruf in robots.txt.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return light_crawl(initial, purpose)  # v1.11: ohne Browser weiterarbeiten statt abzubrechen
    pages, errors = [], []
    # Avoid parallel requests and third-party trackers/assets; no screenshots stored.
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("SIGNALDESK_CHROMIUM_PATH") or None)
        except Exception:
            browser = None
        if browser is None:
            return light_crawl(initial, purpose)
        try:
            context = browser.new_context(java_script_enabled=False, service_workers="block", accept_downloads=False,
                                          user_agent=AGENT, ignore_https_errors=False)
            def route_request(route):
                request_url = route.request.url
                try:
                    # Fail closed for subresource redirects and off-domain content.
                    if not same_company_host(initial, request_url):
                        return route.abort()
                    public_url(request_url)
                    if route.request.resource_type in ("image", "font", "media", "websocket"):
                        return route.abort()
                    route.continue_()
                except (ValueError, OSError):
                    route.abort()
            context.route("**/*", route_request)
            queue = [initial]
            seen = set()
            while queue and len(pages) < MAX_PAGES:
                requested = queue.pop(0)
                requested = public_url(requested)
                if requested in seen:
                    continue
                seen.add(requested)
                if not robots_allowed(requested):
                    errors.append(f"robots.txt sperrt {requested}")
                    continue
                page = context.new_page()
                try:
                    response = page.goto(requested, wait_until="domcontentloaded", timeout=13000)
                    final = public_url(page.url)
                    if not same_company_host(initial, final):
                        raise CrawlError("Weiterleitung zu einer anderen Domain blockiert.")
                    if response is None or response.status >= 400:
                        raise CrawlError(f"HTTP {response.status if response else 'keine Antwort'}")
                    data = page.evaluate("""() => {
                        const b = document.body;
                        return {
                          title: document.title || '',
                          text: (b?.innerText || '').slice(0, 5500),
                          headings: Array.from(document.querySelectorAll('h1,h2,h3')).slice(0,25).map(x=>x.innerText.trim()).filter(Boolean),
                          forms: document.querySelectorAll('form').length,
                          links: Array.from(document.querySelectorAll('a[href]')).slice(0,150).map(a=>({href:a.href,text:(a.innerText||'').trim().slice(0,80)}))
                        };
                    }""")
                    clean = re.sub(r"\s+", " ", str(data.get("text", ""))).strip()[:MAX_TEXT]
                    if not clean:
                        raise CrawlError("Kein sichtbarer Seitentext.")
                    pages.append({"url": final, "title": str(data.get("title", ""))[:220],
                                  "text": clean, "raw_text": str(data.get("text", ""))[:MAX_TEXT] if purpose in ('contacts', 'full') else '',
                                  "headings": data.get("headings", [])[:25],
                                  "form_count": int(data.get("forms", 0))})
                    if len(pages) == 1:
                        queue.extend(derive_links(final, data.get("links", []), purpose))
                except Exception as exc:
                    errors.append(f"{requested}: {str(exc)[:160]}")
                finally:
                    page.close()
            context.close()
        finally:
            browser.close()
    if not pages:
        raise CrawlError("Keine nutzbaren öffentlichen Inhalte gefunden. " + "; ".join(errors[:2]))
    return {"source": initial, "pages": pages, "warnings": errors[:10]}


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
            raw = data.decode("utf-8", "replace")
            text, links, _ = imprint.html_to_text(data)
            clean = re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]
            if not clean:
                raise CrawlError("Kein sichtbarer Seitentext.")
            title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
            headings = [re.sub(r"<[^>]+>|\s+", " ", h).strip() for h in re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", raw, re.I | re.S)][:25]
            pages.append({"url": final, "title": re.sub(r"\s+", " ", title.group(1)).strip()[:220] if title else "",
                          "text": clean, "raw_text": text[:MAX_TEXT] if purpose in ("contacts", "full") else "",
                          "headings": [h for h in headings if h], "form_count": len(re.findall(r"<form\b", raw, re.I))})
            if len(pages) == 1:
                queue.extend(derive_links(final, links, purpose))
        except Exception as exc:
            errors.append(f"{requested}: {str(exc)[:160]}")
    if not pages:
        raise CrawlError("Keine nutzbaren öffentlichen Inhalte gefunden. " + "; ".join(errors[:2]))
    return {"source": public_url(url), "pages": pages, "renderer": "html",
            "warnings": ["Ohne Browser gelesen (kein JavaScript) – dynamische Inhalte können fehlen."] + errors[:9]}
