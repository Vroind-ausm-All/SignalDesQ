"""Browser-Rückfall (Sprint 1): der bisherige Playwright-Abruf als Adapter – nur wenn installiert, erlaubt und nötig.

Unverändert vorsichtig: JavaScript aus, keine Service-Worker, keine Downloads, keine Bilder/Schriften/Medien, nur
dieselbe Firma, jede Anfrage über die Adressprüfung, robots.txt je Seite. Kein Stealth, keine Proxys, keine Captchas.
"""
from __future__ import annotations

import os
import re

NAME = 'browser'


def available():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def crawl(initial, purpose, max_pages, max_text, robots_allowed, public_url, same_company_host, derive_links, CrawlError):
    from playwright.sync_api import sync_playwright
    pages, errors = [], []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('SIGNALDESK_CHROMIUM_PATH') or None)
        except Exception:  # noqa: BLE001
            return None
        try:
            context = browser.new_context(java_script_enabled=False, service_workers='block', accept_downloads=False,
                                          user_agent='SignalDeskResearch/1.15 (+manual B2B site review)', ignore_https_errors=False)

            def route_request(route):
                request_url = route.request.url
                try:
                    if not same_company_host(initial, request_url):
                        return route.abort()
                    public_url(request_url)
                    if route.request.resource_type in ('image', 'font', 'media', 'websocket'):
                        return route.abort()
                    route.continue_()
                except (ValueError, OSError):
                    route.abort()
            context.route('**/*', route_request)
            queue, seen = [initial], set()
            while queue and len(pages) < max_pages:
                requested = public_url(queue.pop(0))
                if requested in seen:
                    continue
                seen.add(requested)
                if not robots_allowed(requested):
                    errors.append(f'robots.txt sperrt {requested}')
                    continue
                page = context.new_page()
                try:
                    response = page.goto(requested, wait_until='domcontentloaded', timeout=13000)
                    final = public_url(page.url)
                    if not same_company_host(initial, final):
                        raise CrawlError('Weiterleitung zu einer anderen Domain blockiert.')
                    if response is None or response.status >= 400:
                        raise CrawlError(f"HTTP {response.status if response else 'keine Antwort'}")
                    data = page.evaluate("""() => {
                        const b = document.body;
                        return {title: document.title || '', text: (b?.innerText || '').slice(0, 5500),
                          headings: Array.from(document.querySelectorAll('h1,h2,h3')).slice(0,25).map(x=>x.innerText.trim()).filter(Boolean),
                          forms: document.querySelectorAll('form').length,
                          links: Array.from(document.querySelectorAll('a[href]')).slice(0,150).map(a=>({href:a.href,text:(a.innerText||'').trim().slice(0,80)}))};
                    }""")
                    clean = re.sub(r'\s+', ' ', str(data.get('text', ''))).strip()[:max_text]
                    if not clean:
                        raise CrawlError('Kein sichtbarer Seitentext.')
                    pages.append({'url': final, 'title': str(data.get('title', ''))[:220], 'text': clean,
                                  'raw_text': str(data.get('text', ''))[:max_text] if purpose in ('contacts', 'full') else '',
                                  'headings': data.get('headings', [])[:25], 'form_count': int(data.get('forms', 0))})
                    if len(pages) == 1:
                        queue.extend(derive_links(final, data.get('links', []), purpose))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f'{requested}: {str(exc)[:160]}')
                finally:
                    page.close()
            context.close()
        finally:
            browser.close()
    return {'pages': pages, 'errors': errors}
