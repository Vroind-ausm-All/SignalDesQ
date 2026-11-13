"""Website-Bedarfs-Scorer v2 (Phase 2): gerenderte Seiten, Messwerte, Rubriken, transparente Scores.

Grundsätze (Master-Prompt v2.0, Modul 3)
- Gestalterische Rubriken werden nur mit echt gerenderten Seiten (Playwright/Chromium, Desktop
  und Mobil, mit Screenshots) bewertet. Ohne Renderer bleiben sie „unbekannt“.
- Jede Rubrik liefert „auffällig“, „ok“ oder „unbekannt“ mit Messwert/Beleg und Fundstelle.
  Ein fehlender Beleg ist unbekannt, nicht schlecht.
- Teil-Scores je Bereich, Passung, Aktualität und Belegabdeckung werden getrennt ausgewiesen.
  Der Gesamtwert entsteht nur bei ausreichender Datenbasis, sonst „Datenlage unzureichend“.
- Prozess-/App-Rubriken sind Hypothesen. Kein Score sagt etwas über Kaufbereitschaft, Budget
  oder Werbeeinwilligung aus.
- Rubriken und Gewichte sind konfigurierbar; jede Konfiguration ist eine eigene Bewertungs-
  version, damit Ergebnisse vergleichbar bleiben.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener

from .website_analyzer import CrawlError, derive_links, public_url, robots_allowed, same_company_host

AGENT_SUFFIX = 'SignalDeskResearch/1.4 (+einmalige Website-Bewertung)'
MOBILE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
             'Version/17.0 Mobile/15E148 Safari/604.1 ' + AGENT_SUFFIX)
MAX_SUBPAGES = 3
MAX_LINK_CHECKS = 25
PAGE_TIMEOUT_MS = 25_000
SCREENSHOT_MAX_HEIGHT = 3000
CTA_WORDS = r'kontakt|anfrage|anfragen|angebot|demo|termin|beratung|rückruf|rueckruf|jetzt|contact|request|quote|get started|kostenlos'

# ---------------------------------------------------------------- Konfiguration (Bewertungsversion)

DEFAULT_CONFIG = {
    'overall_weights': {'potential': 35, 'fit': 35, 'signal': 30},
    'area_weights': {'design': 1, 'web': 1, 'process': 1},
    'min_coverage_pct': 60,
    'min_area_coverage_pct': 50,
    'thresholds': {'load_ms_warn': 4000, 'page_mb_warn': 5, 'small_text_share_pct': 10, 'small_tap_targets': 6,
                   'images_no_alt_pct': 30, 'font_families_max': 4, 'form_fields_warn': 8, 'nav_items_max': 15,
                   'copyright_years_old': 2, 'console_errors_warn': 3},
    'rubrics': {
        # Bereich A – Corporate Design und UX (nur mit gerenderten Seiten)
        'A1_mobile_overflow': {'area': 'design', 'weight': 3, 'enabled': True},
        'A2_small_text': {'area': 'design', 'weight': 2, 'enabled': True},
        'A3_heading_hierarchy': {'area': 'design', 'weight': 2, 'enabled': True},
        'A4_alt_texts': {'area': 'design', 'weight': 1, 'enabled': True},
        'A5_tap_targets': {'area': 'design', 'weight': 2, 'enabled': True},
        'A6_font_consistency': {'area': 'design', 'weight': 1, 'enabled': True},
        'A7_freshness': {'area': 'design', 'weight': 1, 'enabled': True},
        # Bereich B – Webentwicklung und Conversion
        'B1_load_time': {'area': 'web', 'weight': 3, 'enabled': True},
        'B2_page_weight': {'area': 'web', 'weight': 1, 'enabled': True},
        'B3_cta_above_fold': {'area': 'web', 'weight': 3, 'enabled': True},
        'B4_contact_options': {'area': 'web', 'weight': 2, 'enabled': True},
        'B5_form_effort': {'area': 'web', 'weight': 2, 'enabled': True},
        'B6_broken_links': {'area': 'web', 'weight': 2, 'enabled': True},
        'B7_navigation': {'area': 'web', 'weight': 1, 'enabled': True},
        'B8_service_pages': {'area': 'web', 'weight': 2, 'enabled': True},
        'B9_technical': {'area': 'web', 'weight': 1, 'enabled': True},
        # Bereich C – Appentwicklung und Prozessautomatisierung (Hypothesen)
        'C1_pdf_workflows': {'area': 'process', 'weight': 3, 'enabled': True},
        'C2_manual_requests': {'area': 'process', 'weight': 2, 'enabled': True},
        'C3_self_service': {'area': 'process', 'weight': 2, 'enabled': True},
        'C4_complex_forms': {'area': 'process', 'weight': 2, 'enabled': True},
        'C5_recurring_data_entry': {'area': 'process', 'weight': 2, 'enabled': True},
        # Bereich D – Kampagnen/Content: nur aktiv, wenn ein passendes Paket im Leistungskatalog existiert
    },
}
AREA_LABELS = {'design': 'Design & UX', 'web': 'Web & Conversion', 'process': 'Prozess & App'}
RUBRIC_TEXT = {
    'A1_mobile_overflow': ('Responsive mobile Darstellung (kein Verkleinern, kein seitliches Scrollen)', 'brand',
                           'Wie wichtig ist Ihnen die Darstellung auf Smartphones, z. B. für Außendienst oder Messebesucher?'),
    'A2_small_text': ('Lesbare Schriftgrößen auf dem Smartphone', 'brand',
                      'Bekommen Sie Rückmeldungen, dass Inhalte auf mobilen Geräten schwer lesbar sind?'),
    'A3_heading_hierarchy': ('Klare typografische Hierarchie (eine H1, Zwischenüberschriften)', 'brand',
                             'Wie schnell sollen Besucher erfassen, was Sie anbieten und für wen?'),
    'A4_alt_texts': ('Bildbeschreibungen (Alt-Texte) vorhanden', 'conversion',
                     'Spielt Barrierefreiheit (z. B. ab 2025 gesetzlich für viele B2C-Angebote) für Sie eine Rolle?'),
    'A5_tap_targets': ('Ausreichend große Touch-Ziele auf dem Smartphone', 'brand',
                       'Wie viele Ihrer Besucher kommen über das Smartphone?'),
    'A6_font_consistency': ('Einheitliche Schriftverwendung (≤ 4 Schriftfamilien)', 'brand',
                            'Gibt es ein verbindliches Corporate Design, das auf allen Kanälen gleich umgesetzt wird?'),
    'A7_freshness': ('Aktuelle Copyright-/Stand-Angabe', 'care',
                     'Wer pflegt die Website heute, und wie oft werden Inhalte aktualisiert?'),
    'B1_load_time': ('Ladezeit der Startseite', 'conversion',
                     'Ist die Geschwindigkeit der Website schon einmal Thema gewesen, z. B. bei Anzeigen oder SEO?'),
    'B2_page_weight': ('Datenmenge der Startseite', 'care',
                       'Werden Bilder und Medien heute vor dem Hochladen optimiert?'),
    'B3_cta_above_fold': ('Sichtbarer Anfrage-/Kontaktaufruf im ersten Bildschirm', 'conversion',
                          'Wie kommen heute qualifizierte Anfragen über die Website zu Ihnen?'),
    'B4_contact_options': ('Kontaktmöglichkeiten (Formular, Telefon-, E-Mail-Link)', 'pilot',
                           'Welche Kontaktwege nutzen Ihre Kunden am liebsten?'),
    'B5_form_effort': ('Formularaufwand (Anzahl Felder)', 'conversion',
                       'Wie viele Angaben brauchen Sie wirklich, um eine Anfrage zu bearbeiten?'),
    'B6_broken_links': ('Keine defekten internen Links', 'care',
                        'Gibt es einen festen Prozess, um Website-Inhalte regelmäßig zu prüfen?'),
    'B7_navigation': ('Übersichtliche Hauptnavigation', 'conversion',
                      'Welche drei Seiten sollen Besucher auf jeden Fall sehen?'),
    'B8_service_pages': ('Erkennbare Leistungs-/Produktseiten', 'conversion',
                         'Welche Leistung oder welches Produkt soll die Website derzeit vor allem verkaufen?'),
    'B9_technical': ('Technische Grundlagen (HTTPS, Viewport, Beschreibung, Konsolenfehler)', 'care',
                     'Wer betreut die Website technisch, und gibt es bekannte Probleme?'),
    'C1_pdf_workflows': ('Hinweise auf PDF-basierte Abläufe (Formulare/Bestellungen als PDF)', 'portal',
                         'Wie werden die herunterladbaren Formulare bei Ihnen weiterverarbeitet?'),
    'C2_manual_requests': ('Hinweise auf manuelle Anfrage-/Freigabeschritte', 'portal',
                           'Welche Schritte zwischen Anfrage und Angebot passieren heute per E-Mail oder Telefon?'),
    'C3_self_service': ('Digitaler Self-Service für Kunden (Login/Portal)', 'portal',
                        'Welche Informationen fragen Kunden immer wieder bei Ihnen an?'),
    'C4_complex_forms': ('Aufwendige Formulare (> 12 Felder oder Datei-Uploads)', 'portal',
                         'Werden Formulareingaben heute manuell in andere Systeme übertragen?'),
    'C5_recurring_data_entry': ('Hinweise auf wiederkehrende Datenerfassung (Vorlagen zum Ausfüllen)', 'portal',
                                'Wo erfassen Ihre Mitarbeitenden heute dieselben Daten mehrfach?'),
}
RUBRIC_ISSUE = {  # Formulierung, wenn eine Rubrik auffällig ist
    'A1_mobile_overflow': 'Smartphone-Darstellung nicht responsiv', 'A2_small_text': 'Zu kleine Schrift auf dem Smartphone',
    'A3_heading_hierarchy': 'Unklare Überschriften-Hierarchie', 'A4_alt_texts': 'Bilder ohne Beschreibung (Alt-Text)',
    'A5_tap_targets': 'Zu kleine Touch-Ziele auf dem Smartphone', 'A6_font_consistency': 'Uneinheitliche Schriftverwendung',
    'A7_freshness': 'Veraltete Copyright-/Stand-Angabe', 'B1_load_time': 'Lange Ladezeit', 'B2_page_weight': 'Hohe Datenmenge der Startseite',
    'B3_cta_above_fold': 'Kein sichtbarer Anfrageaufruf im ersten Bildschirm', 'B4_contact_options': 'Keine direkten Kontaktmöglichkeiten gefunden',
    'B5_form_effort': 'Aufwendiges Anfrageformular', 'B6_broken_links': 'Defekte interne Links', 'B7_navigation': 'Navigation fehlt oder ist überladen',
    'B8_service_pages': 'Leistungs-/Produktseiten nicht erkennbar', 'B9_technical': 'Technische Auffälligkeiten',
    'C1_pdf_workflows': 'Hinweis: PDF-basierte Abläufe', 'C2_manual_requests': 'Hinweis: manuelle Anfrage-/Freigabeschritte',
    'C3_self_service': 'Hinweis: kein digitaler Self-Service', 'C4_complex_forms': 'Hinweis: aufwendige Formulare',
    'C5_recurring_data_entry': 'Hinweis: wiederkehrende Datenerfassung',
}
GENERIC_QUESTIONS = ['Welches Ziel soll die Website in den nächsten zwölf Monaten vor allem erfüllen?',
                     'Woran würden Sie merken, dass sich eine Verbesserung gelohnt hat?',
                     'Wer entscheidet bei Ihnen über Website- und Digitalprojekte, und wer muss zustimmen?']


def validate_config(cfg):
    if not isinstance(cfg, dict) or set(cfg) - set(DEFAULT_CONFIG):
        raise ValueError('Ungültige Konfiguration.')
    out = copy.deepcopy(DEFAULT_CONFIG)
    for key in ('overall_weights', 'area_weights'):
        if key in cfg:
            vals = cfg[key]
            if not isinstance(vals, dict) or set(vals) != set(DEFAULT_CONFIG[key]):
                raise ValueError(f'{key}: alle Schlüssel angeben.')
            for k, v in vals.items():
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
                    raise ValueError(f'{key}.{k}: 0–100.')
            if sum(vals.values()) <= 0:
                raise ValueError(f'{key}: Summe muss größer 0 sein.')
            out[key] = {k: float(v) for k, v in vals.items()}
    for key in ('min_coverage_pct', 'min_area_coverage_pct'):
        if key in cfg:
            v = cfg[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 10 <= v <= 100:
                raise ValueError(f'{key}: 10–100.')
            out[key] = float(v)
    if 'thresholds' in cfg:
        if not isinstance(cfg['thresholds'], dict) or set(cfg['thresholds']) - set(DEFAULT_CONFIG['thresholds']):
            raise ValueError('Ungültige Schwellenwerte.')
        for k, v in cfg['thresholds'].items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100000:
                raise ValueError(f'Schwellenwert {k} ungültig.')
            out['thresholds'][k] = v
    if 'rubrics' in cfg:
        if not isinstance(cfg['rubrics'], dict) or set(cfg['rubrics']) - set(DEFAULT_CONFIG['rubrics']):
            raise ValueError('Unbekannte Rubrik.')
        for rid, r in cfg['rubrics'].items():
            if not isinstance(r, dict) or set(r) - {'weight', 'enabled'}:
                raise ValueError(f'Rubrik {rid}: nur weight/enabled.')
            if 'weight' in r and (isinstance(r['weight'], bool) or not isinstance(r['weight'], (int, float)) or not 0 <= r['weight'] <= 10):
                raise ValueError(f'Rubrik {rid}: Gewicht 0–10.')
            if 'enabled' in r and not isinstance(r['enabled'], bool):
                raise ValueError(f'Rubrik {rid}: enabled true/false.')
            out['rubrics'][rid].update(r)
    return out


SCORE_ENGINE_VERSION = '2.0-no-portal-inference'


def config_hash(cfg):
    # Gleiches Regelgewicht mit anderer Bewertungslogik darf nicht vergleichbar erscheinen.
    return hashlib.sha256((SCORE_ENGINE_VERSION + ':' + json.dumps(cfg, sort_keys=True)).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- Erfassung: gerenderte Seiten

DOM_FACTS_JS = r"""
() => {
  const CTA = new RegExp(%CTA%, 'i');
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 400).map(a => ({href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80)}));
  const navRoot = document.querySelector('nav') || document.querySelector('header');
  const navLinks = navRoot ? Array.from(navRoot.querySelectorAll('a[href]')).filter(vis).length : 0;
  const forms = Array.from(document.querySelectorAll('form')).slice(0, 10).map(f => {
    const fields = Array.from(f.querySelectorAll('input,select,textarea')).filter(i => !['hidden','submit','button','reset','image'].includes((i.type||'').toLowerCase()));
    return {fields: fields.length, required: fields.filter(i => i.required || i.getAttribute('aria-required') === 'true').length,
            file: fields.some(i => (i.type||'') === 'file'), search: !!f.querySelector('input[type=search]') || /such|search/i.test(f.getAttribute('role')||f.action||'')};
  });
  const ctas = Array.from(document.querySelectorAll('a,button,[role=button],input[type=submit]')).filter(vis)
    .filter(el => CTA.test((el.innerText || el.value || el.getAttribute('aria-label') || '').trim()));
  const fold = window.innerHeight;
  const ctaAbove = ctas.filter(el => el.getBoundingClientRect().top < fold).map(el => (el.innerText || el.value || '').trim().slice(0, 40));
  const imgs = Array.from(document.images).filter(vis);
  const textEls = Array.from(document.querySelectorAll('p,li,a,span,td,label,h1,h2,h3,h4,button')).filter(el => vis(el) && (el.innerText||'').trim().length > 2).slice(0, 600);
  const fams = new Set(), small = [];
  for (const el of textEls) { const s = getComputedStyle(el); fams.add((s.fontFamily||'').split(',')[0].replace(/["']/g,'').trim().toLowerCase()); if (parseFloat(s.fontSize) < 12) small.push(el); }
  const taps = Array.from(document.querySelectorAll('a[href],button')).filter(vis).filter(el => { const r = el.getBoundingClientRect(); return r.width < 32 || r.height < 32; });
  const footer = document.querySelector('footer') ? document.querySelector('footer').innerText : document.body.innerText.slice(-3000);
  const years = (footer.match(/(?:©|\(c\)|copyright|stand)[^0-9]{0,12}((?:19|20)\d{2})(?:\s*[-–]\s*((?:19|20)\d{2}))?/gi) || [])
    .map(m => Math.max(...(m.match(/(?:19|20)\d{2}/g) || []).map(Number)));
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const res = performance.getEntriesByType('resource');
  return {
    url: location.href, title: document.title, metaDescription: (document.querySelector('meta[name=description]')||{}).content || '',
    lang: document.documentElement.lang || '', viewportMeta: !!document.querySelector('meta[name=viewport]'),
    h1: document.querySelectorAll('h1').length, h2: document.querySelectorAll('h2').length,
    headings: Array.from(document.querySelectorAll('h1,h2')).slice(0, 12).map(h => h.innerText.trim().slice(0, 80)),
    navLinks, links, forms, tel: document.querySelectorAll('a[href^="tel:"]').length, mailto: document.querySelectorAll('a[href^="mailto:"]').length,
    ctaTotal: ctas.length, ctaAboveFold: ctaAbove.slice(0, 6), images: imgs.length, imagesNoAlt: imgs.filter(i => !(i.getAttribute('alt')||'').trim()).length,
    fontFamilies: Array.from(fams).filter(Boolean).slice(0, 12), textElements: textEls.length, smallText: small.length,
    smallTapTargets: taps.length, overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
    layoutWidth: window.innerWidth, deviceWidth: screen.width, scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight, copyrightYear: years.length ? Math.max(...years) : null,
    loginLinks: links.filter(l => /login|anmelden|kundenportal|kundenbereich|mein konto|my account|portal|self.?service/i.test(l.text + ' ' + l.href)).length,
    pdfLinks: links.filter(l => /\.pdf($|\?)/i.test(l.href)).slice(0, 30),
    text: (document.body.innerText || '').slice(0, 15000),
    timing: {dcl: Math.round(nav.domContentLoadedEventEnd || 0), load: Math.round(nav.loadEventEnd || 0),
             transfer: Math.round((nav.transferSize || 0) + res.reduce((a, r) => a + (r.transferSize || 0), 0)), requests: res.length + 1},
  };
}
""".replace('%CTA%', json.dumps(CTA_WORDS))

URL_GUARD = public_url          # in Tests für lokale Testseiten ersetzbar
ROBOTS = robots_allowed         # dto.
_DNS_CACHE: dict[str, bool] = {}


def _host_allowed(host):
    """Blockiert Anfragen des Browsers an lokale/private Ziele (SSRF-Schutz auch für Unterressourcen)."""
    if URL_GUARD is not public_url:
        return True
    host = (host or '').rstrip('.').lower()
    if not host or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        return False
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    try:
        ip = ipaddress.ip_address(host)
        ok = ip.is_global
    except ValueError:
        try:
            ok = all(ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except (socket.gaierror, ValueError):
            ok = False
    _DNS_CACHE[host] = ok
    return ok


def chromium_path():
    env = os.environ.get('SIGNALDESK_CHROMIUM_PATH')
    return env if env and Path(env).exists() else None


def playwright_available():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def capture_site(url):
    """Rendert Startseite (Desktop + Mobil) und bis zu drei Unterseiten. Gibt Messwerte und Screenshots zurück."""
    from playwright.sync_api import Error as PWError, sync_playwright
    start_url = URL_GUARD(url)
    if not ROBOTS(start_url):
        raise CrawlError('robots.txt untersagt den Abruf der Startseite.')
    out = {'url': start_url, 'renderer': 'playwright', 'pages': [], 'screenshots': [], 'errors': [], 'console_errors': 0,
           'captured_at': _now(), 'https': start_url.startswith('https://')}
    console = {'n': 0}

    def guard(route):
        req = route.request
        host = urlsplit(req.url).hostname
        if req.url.startswith(('data:', 'blob:')):
            return route.continue_()
        if urlsplit(req.url).scheme not in ('http', 'https') or not _host_allowed(host) or req.resource_type in ('media', 'websocket'):
            return route.abort()
        if req.is_navigation_request() and req.frame == req.frame.page.main_frame and not same_company_host(start_url, req.url):
            return route.abort()  # keine Hauptnavigation auf fremde Domains
        return route.continue_()

    def on_console(msg):
        if msg.type == 'error':
            console['n'] += 1

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium_path()) if chromium_path() else p.chromium.launch()
        try:
            desk = browser.new_context(viewport={'width': 1366, 'height': 900}, locale='de-DE', accept_downloads=False)
            desk.route('**/*', guard)
            page = desk.new_page()
            page.on('console', on_console)
            t0 = time.monotonic()
            resp = page.goto(start_url, wait_until='load', timeout=PAGE_TIMEOUT_MS)
            wall = int((time.monotonic() - t0) * 1000)
            page.wait_for_timeout(800)
            final = page.url
            if not same_company_host(start_url, final):
                raise CrawlError('Startseite leitet auf eine fremde Domain um.')
            out['final_url'] = final
            out['https'] = final.startswith('https://')
            facts = page.evaluate(DOM_FACTS_JS)
            facts['timing']['wall'] = wall
            facts['status'] = resp.status if resp else None
            height = min(facts['scrollHeight'] or 900, SCREENSHOT_MAX_HEIGHT)
            out['screenshots'].append({'page_url': final, 'kind': 'desktop', 'bytes': page.screenshot(type='jpeg', quality=70, clip={'x': 0, 'y': 0, 'width': 1366, 'height': height}, full_page=True)})
            home = {'url': final, 'kind': 'home', 'desktop': facts}
            mob = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, user_agent=MOBILE_UA,
                                      locale='de-DE', accept_downloads=False)
            mob.route('**/*', guard)
            mpage = mob.new_page()
            mpage.goto(final, wait_until='load', timeout=PAGE_TIMEOUT_MS)
            mpage.wait_for_timeout(800)
            home['mobile'] = mpage.evaluate(DOM_FACTS_JS)
            out['screenshots'].append({'page_url': final, 'kind': 'mobile', 'bytes': mpage.screenshot(type='jpeg', quality=70)})
            mob.close()
            out['pages'].append(home)
            for sub in derive_links(final, facts['links'], 'website')[:MAX_SUBPAGES]:
                try:
                    sub = URL_GUARD(sub)
                    if not ROBOTS(sub):
                        out['errors'].append(f'{sub}: durch robots.txt ausgeschlossen')
                        continue
                    time.sleep(0.5)
                    r = page.goto(sub, wait_until='load', timeout=PAGE_TIMEOUT_MS)
                    page.wait_for_timeout(500)
                    if not same_company_host(start_url, page.url):
                        out['errors'].append(f'{sub}: Weiterleitung auf fremde Domain')
                        continue
                    sf = page.evaluate(DOM_FACTS_JS)
                    sf['status'] = r.status if r else None
                    out['pages'].append({'url': page.url, 'kind': 'sub', 'desktop': sf})
                    out['screenshots'].append({'page_url': page.url, 'kind': 'unterseite', 'bytes': page.screenshot(type='jpeg', quality=65)})
                except (PWError, CrawlError) as exc:
                    out['errors'].append(f'{sub}: {str(exc).splitlines()[0][:160]}')
            desk.close()
        except PWError as exc:
            raise CrawlError(f'Seite konnte nicht gerendert werden: {str(exc).splitlines()[0][:200]}') from exc
        finally:
            browser.close()
    out['console_errors'] = console['n']
    out['link_check'] = check_links(out)
    return out


def capture_html_only(url):
    """Rückfall ohne Browser: nur HTML-Struktur. Design-Rubriken und Ladezeit bleiben unbekannt."""
    from .imprint import http_fetch, html_to_text
    final, ctype, data = http_fetch(url, None)
    text, links, mailtos = html_to_text(data)
    raw = data.decode('utf-8', 'replace')
    forms = [{'fields': len(re.findall(r'<(?:input(?![^>]*type=["\']?(?:hidden|submit|button))|select|textarea)\b', f, re.I)),
              'required': len(re.findall(r'\brequired\b', f, re.I)), 'file': 'type="file"' in f.lower(), 'search': 'search' in f.lower()}
             for f in re.findall(r'<form\b.*?</form>', raw, re.I | re.S)[:10]]
    abs_links = [{'href': urljoin(final, l['href']), 'text': l['text']} for l in links]
    facts = {'url': final, 'title': (re.search(r'<title>(.*?)</title>', raw, re.I | re.S) or [None, ''])[1].strip()[:120],
             'metaDescription': 'x' if re.search(r'<meta[^>]+name=["\']description', raw, re.I) else '',
             'viewportMeta': bool(re.search(r'<meta[^>]+name=["\']viewport', raw, re.I)),
             'h1': len(re.findall(r'<h1\b', raw, re.I)), 'h2': len(re.findall(r'<h2\b', raw, re.I)), 'headings': [],
             'navLinks': None, 'links': abs_links[:400], 'forms': forms, 'tel': raw.lower().count('href="tel:'), 'mailto': len(mailtos),
             'ctaTotal': None, 'ctaAboveFold': None, 'images': None, 'imagesNoAlt': None, 'fontFamilies': None,
             'smallText': None, 'textElements': None, 'smallTapTargets': None, 'overflowX': None, 'copyrightYear': None,
             'loginLinks': sum(1 for l in abs_links if re.search(r'login|anmelden|kundenportal|kundenbereich|mein konto|portal', l['text'] + l['href'], re.I)),
             'pdfLinks': [l for l in abs_links if re.search(r'\.pdf($|\?)', l['href'], re.I)][:30], 'text': text[:15000], 'timing': None, 'status': 200}
    years = [int(y) for y in re.findall(r'(?:©|copyright)\D{0,12}((?:19|20)\d{2})', text, re.I)]
    facts['copyrightYear'] = max(years) if years else None
    out = {'url': url, 'final_url': final, 'renderer': 'html', 'pages': [{'url': final, 'kind': 'home', 'desktop': facts}],
           'screenshots': [], 'errors': ['Kein Browser-Rendering verfügbar – Gestaltung, Mobilansicht und Ladezeit nicht bewertet.'],
           'console_errors': None, 'captured_at': _now(), 'https': final.startswith('https://')}
    out['link_check'] = check_links(out)
    return out


def check_links(capture):
    """Prüft bis zu 25 interne Links derselben Domain (HEAD, notfalls GET), respektiert robots.txt."""
    origin = capture.get('final_url') or capture['url']
    seen, targets = set(), []
    for page in capture['pages']:
        for link in page['desktop'].get('links') or []:
            href = link.get('href', '')
            p = urlsplit(href)
            if p.scheme not in ('http', 'https') or not same_company_host(origin, href):
                continue
            clean = urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))
            if clean in seen or re.search(r'logout|abmelden|\.(zip|exe|dmg|mp4|mov)$', clean, re.I):
                continue
            seen.add(clean)
            targets.append((clean, page['url']))
    targets = targets[:MAX_LINK_CHECKS]
    broken, checked, skipped = [], 0, 0
    from .imprint import _SafeRedirect
    for url, found_on in targets:
        opener = build_opener(_SafeRedirect(origin)) if URL_GUARD is public_url else build_opener()
        try:
            URL_GUARD(url)
            if not ROBOTS(url):
                skipped += 1
                continue
        except CrawlError:
            skipped += 1
            continue
        status = None
        for method in ('HEAD', 'GET'):
            try:
                with opener.open(Request(url, method=method, headers={'User-Agent': AGENT_SUFFIX}), timeout=8) as resp:
                    status = resp.status
                    if method == 'GET':
                        resp.read(1024)
                break
            except HTTPError as exc:
                status = exc.code
                if exc.code not in (403, 405, 501):
                    break
            except (URLError, TimeoutError, OSError, CrawlError):
                status = 'nicht erreichbar'
                break
        checked += 1
        if status == 'nicht erreichbar' or (isinstance(status, int) and status >= 400 and status not in (401, 403, 429)):
            broken.append({'url': url, 'status': status, 'found_on': found_on})
        time.sleep(0.2)
    return {'checked': checked, 'broken': broken, 'skipped': skipped, 'candidates': len(targets)}


CAPTURE = capture_site
CAPTURE_FALLBACK = capture_html_only


# ---------------------------------------------------------------- Rubriken

def _r(result, evidence, url=None, shot=None, method='messung', certainty='gemessen'):
    return {'result': result, 'evidence': evidence, 'source_url': url, 'screenshot_kind': shot, 'method': method, 'certainty': certainty}


UNKNOWN_RENDER = 'Nur mit gerenderter Seite bewertbar – Renderer nicht verfügbar oder Seite nicht darstellbar.'


def rubric_results(cap, cfg):
    th = cfg['thresholds']
    home = cap['pages'][0] if cap.get('pages') else None
    if not home:
        return {rid: _r('unbekannt', 'Startseite nicht erfasst.') for rid in DEFAULT_CONFIG['rubrics']}
    d, m = home['desktop'], home.get('mobile')
    url = home['url']
    rendered = cap.get('renderer') == 'playwright'
    allp = [p['desktop'] for p in cap['pages']]
    text_all = '\n'.join(p.get('text') or '' for p in allp)
    res = {}
    # A – Design & UX
    if m and rendered:
        shrunk = (m.get('layoutWidth') or 0) > (m.get('deviceWidth') or 390) + 20  # Desktop-Layout wird verkleinert dargestellt
        if m['overflowX']:
            a1 = _r('auffaellig', f'Inhalt breiter als der Bildschirm ({m.get("scrollWidth")} px bei {m.get("layoutWidth")} px) – seitliches Scrollen.', url, 'mobile')
        elif shrunk:
            a1 = _r('auffaellig', f'Nicht responsiv: Seite wird auf dem Smartphone mit {m.get("layoutWidth")} px Layoutbreite gerendert und auf {m.get("deviceWidth")} px verkleinert.', url, 'mobile')
        else:
            a1 = _r('ok', f'Responsive Darstellung: Layoutbreite {m.get("layoutWidth") or 390} px entspricht der Gerätebreite, kein seitliches Scrollen.', url, 'mobile')
        res['A1_mobile_overflow'] = a1
        share = round(100 * m['smallText'] / m['textElements']) if m.get('textElements') else None
        res['A2_small_text'] = _r('unbekannt', 'Zu wenig Textelemente.') if share is None else _r(
            'auffaellig' if share > th['small_text_share_pct'] else 'ok', f'{share} % der Textelemente mobil kleiner als 12 px (Schwelle {th["small_text_share_pct"]} %).', url, 'mobile')
        res['A5_tap_targets'] = _r('auffaellig' if m['smallTapTargets'] >= th['small_tap_targets'] else 'ok',
                                   f'{m["smallTapTargets"]} Links/Buttons kleiner als 32 × 32 px (Schwelle {th["small_tap_targets"]}).', url, 'mobile')
        fams = d.get('fontFamilies') or []
        res['A6_font_consistency'] = _r('auffaellig' if len(fams) > th['font_families_max'] else 'ok',
                                        f'{len(fams)} Schriftfamilien im Einsatz: {", ".join(fams[:6])}.', url, 'desktop', 'messung', 'beobachtet')
        if d.get('images'):
            pct = round(100 * d['imagesNoAlt'] / d['images'])
            res['A4_alt_texts'] = _r('auffaellig' if pct > th['images_no_alt_pct'] else 'ok', f'{d["imagesNoAlt"]} von {d["images"]} sichtbaren Bildern ohne Alt-Text ({pct} %).', url, 'desktop')
        else:
            res['A4_alt_texts'] = _r('unbekannt', 'Keine sichtbaren Bilder auf der Startseite.')
    else:
        for rid in ('A1_mobile_overflow', 'A2_small_text', 'A4_alt_texts', 'A5_tap_targets', 'A6_font_consistency'):
            res[rid] = _r('unbekannt', UNKNOWN_RENDER)
    hierarchy_ok = d.get('h1') == 1 and (d.get('h2') or 0) >= 1
    res['A3_heading_hierarchy'] = _r('ok' if hierarchy_ok else 'auffaellig',
                                     f'{d.get("h1")} H1-Überschrift(en), {d.get("h2")} H2-Überschrift(en) auf der Startseite.', url, 'desktop' if rendered else None, 'dom', 'beobachtet')
    year = d.get('copyrightYear')
    now_year = dt.date.today().year
    res['A7_freshness'] = _r('unbekannt', 'Keine Copyright-/Stand-Jahreszahl gefunden.', method='dom') if not year else _r(
        'auffaellig' if now_year - year > th['copyright_years_old'] else 'ok', f'Jüngste Jahresangabe im Fußbereich: {year}.', url, None, 'dom', 'beobachtet')
    # B – Web & Conversion
    timing = d.get('timing')
    if timing and timing.get('load'):
        res['B1_load_time'] = _r('auffaellig' if timing['load'] > th['load_ms_warn'] else 'ok',
                                 f'Vollständig geladen nach {timing["load"] / 1000:.1f} s (einmalige Messung ohne Cache, Schwelle {th["load_ms_warn"] / 1000:.1f} s).', url)
        mb = timing.get('transfer', 0) / 1_000_000
        res['B2_page_weight'] = _r('unbekannt', 'Übertragene Datenmenge nicht messbar (Server liefert keine Größenangaben).') if not timing.get('transfer') else _r(
            'auffaellig' if mb > th['page_mb_warn'] else 'ok', f'{mb:.1f} MB in {timing.get("requests")} Anfragen übertragen (mindestens; Schwelle {th["page_mb_warn"]} MB).', url)
    else:
        res['B1_load_time'] = _r('unbekannt', UNKNOWN_RENDER)
        res['B2_page_weight'] = _r('unbekannt', UNKNOWN_RENDER)
    if d.get('ctaAboveFold') is None:
        res['B3_cta_above_fold'] = _r('unbekannt', UNKNOWN_RENDER)
    else:
        res['B3_cta_above_fold'] = _r('ok' if d['ctaAboveFold'] else 'auffaellig',
                                      ('Im ersten Bildschirm sichtbar: ' + ', '.join(f'„{c}“' for c in d['ctaAboveFold'][:3])) if d['ctaAboveFold'] else 'Kein Kontakt-/Anfrage-Element im ersten Bildschirm (1366 × 900 px) sichtbar.', url, 'desktop')
    forms = [f for p in allp for f in (p.get('forms') or []) if not f.get('search')]
    tel = sum(p.get('tel') or 0 for p in allp)
    mail = sum(p.get('mailto') or 0 for p in allp)
    res['B4_contact_options'] = _r('ok' if (forms or tel or mail) else 'auffaellig',
                                   f'{len(forms)} Formular(e), {tel} Telefon-Link(s), {mail} E-Mail-Link(s) auf {len(allp)} geprüften Seiten.', url, None, 'dom', 'beobachtet')
    if forms:
        biggest = max(forms, key=lambda f: f['fields'])
        res['B5_form_effort'] = _r('auffaellig' if biggest['fields'] > th['form_fields_warn'] else 'ok',
                                   f'Größtes Formular: {biggest["fields"]} Felder, davon {biggest["required"]} Pflichtfelder (Schwelle {th["form_fields_warn"]}).', url, None, 'dom', 'beobachtet')
    else:
        res['B5_form_effort'] = _r('unbekannt', 'Kein Formular auf den geprüften Seiten.', method='dom')
    lc = cap.get('link_check') or {}
    if lc.get('checked'):
        b = lc['broken']
        res['B6_broken_links'] = _r('auffaellig' if b else 'ok', (f'{len(b)} von {lc["checked"]} geprüften internen Links defekt, z. B. {b[0]["url"]} (Status {b[0]["status"]}).' if b else f'{lc["checked"]} interne Links geprüft, keiner defekt.'),
                                    b[0]['found_on'] if b else url)
    else:
        res['B6_broken_links'] = _r('unbekannt', 'Keine internen Links prüfbar.')
    nav = d.get('navLinks')
    res['B7_navigation'] = _r('unbekannt', UNKNOWN_RENDER) if nav is None else _r(
        'auffaellig' if nav == 0 or nav > th['nav_items_max'] else 'ok',
        'Keine erkennbare Navigation im Kopfbereich.' if nav == 0 else f'{nav} sichtbare Links in der Hauptnavigation (Schwelle {th["nav_items_max"]}).', url, 'desktop', 'dom', 'beobachtet')
    service = [l for l in (d.get('links') or []) if re.search(r'leistung|produkt|service|lösung|loesung|solution|angebot|portfolio|branchen|products', l['text'] + ' ' + l['href'], re.I)]
    res['B8_service_pages'] = _r('ok' if service else 'auffaellig', (f'{len(service)} Links zu Leistungs-/Produktseiten, z. B. „{service[0]["text"] or service[0]["href"]}“.' if service else 'Keine Links zu Leistungs- oder Produktseiten auf der Startseite erkannt.'), url, None, 'dom', 'beobachtet')
    issues = []
    if not cap.get('https'):
        issues.append('keine HTTPS-Verbindung')
    if d.get('viewportMeta') is False:
        issues.append('kein Viewport-Meta-Tag (mobil)')
    if not d.get('metaDescription'):
        issues.append('keine Meta-Beschreibung')
    if cap.get('console_errors') is not None and cap['console_errors'] > th['console_errors_warn']:
        issues.append(f'{cap["console_errors"]} JavaScript-Fehler in der Konsole')
    res['B9_technical'] = _r('auffaellig' if issues else 'ok', ('Auffällig: ' + ', '.join(issues) + '.') if issues else 'HTTPS, Viewport und Meta-Beschreibung vorhanden.', url, None, 'messung', 'gemessen')
    # C – Prozess & App (Hypothesen, nie Beweis)
    pdf_flow = [l for p in allp for l in (p.get('pdfLinks') or []) if re.search(r'formular|antrag|bestell|auftrag|anmeld|reklamation|order|form|registrier|vollmacht', l['text'] + ' ' + l['href'], re.I)]
    res['C1_pdf_workflows'] = _r('auffaellig' if pdf_flow else 'ok', (f'{len(pdf_flow)} PDF-Formular(e) zum Herunterladen, z. B. „{pdf_flow[0]["text"] or pdf_flow[0]["href"]}“. Hypothese: Weiterverarbeitung erfolgt manuell.' if pdf_flow else 'Keine PDF-Formulare verlinkt.'),
                                 url, None, 'heuristik', 'hypothese')
    manual = re.search(r'(per (?:e-?mail|fax|post) (?:an|zu)?(?:fragen|senden|schicken|zurück)|ausdrucken|ausgefüllt[^.]{0,40}(?:zurück|senden|faxen)|per fax|rufen sie uns an, um)', text_all, re.I)
    res['C2_manual_requests'] = _r('auffaellig' if manual else 'ok', (f'Textstelle: „{_ctx(text_all, manual)}“. Hypothese: manueller Zwischenschritt.' if manual else 'Keine Hinweise auf manuelle Anfrage-/Freigabeschritte im Seitentext.'), url, None, 'heuristik', 'hypothese')
    login = sum(p.get('loginLinks') or 0 for p in allp)
    res['C3_self_service'] = _r('ok', f'{login} Link(s) zu Login/Portal/Kundenbereich gefunden.', url, None, 'dom', 'beobachtet') if login else _r(
        'unbekannt', 'Auf den geprüften Seiten kein Login gefunden. Daraus lässt sich kein Bedarf für ein Portal ableiten.', url, None, 'dom', 'beobachtet')
    complex_forms = [f for f in forms if f['fields'] > 12 or f.get('file')]
    res['C4_complex_forms'] = _r('unbekannt', 'Kein Formular auf den geprüften Seiten.', method='dom') if not forms else _r(
        'auffaellig' if complex_forms else 'ok', (f'Formular mit {complex_forms[0]["fields"]} Feldern{" und Datei-Upload" if complex_forms[0].get("file") else ""}. Hypothese: Daten werden anschließend manuell übertragen.' if complex_forms else 'Keine aufwendigen Formulare.'),
        url, None, 'heuristik', 'hypothese')
    recurring = re.search(r'(excel-?vorlage|vorlage herunterladen|bitte füllen sie[^.]{0,60}aus|tabelle ausfüllen|checkliste herunterladen)', text_all, re.I)
    res['C5_recurring_data_entry'] = _r('auffaellig' if recurring else 'ok', (f'Textstelle: „{_ctx(text_all, recurring)}“. Hypothese: wiederkehrende manuelle Datenerfassung.' if recurring else 'Keine Hinweise auf Ausfüll-Vorlagen.'), url, None, 'heuristik', 'hypothese')
    return res


def _ctx(text, match):
    a, b = max(0, match.start() - 50), min(len(text), match.end() + 50)
    return re.sub(r'\s+', ' ', text[a:b]).strip()


# ---------------------------------------------------------------- Scores

INDUSTRY_FIT = {'Industrie & B2B-Technik': 100, 'B2B-SaaS': 85, 'Professionelle Dienstleistungen': 65, 'Sonstige': 25}


def _size_fit(employees):
    n = int(employees or 0)
    if n <= 0:
        return None
    if 20 <= n <= 200:
        return 100
    if 10 <= n < 20 or 200 < n <= 500:
        return 60
    return 30 if n < 10 else 40


def _signal_score(lead):
    bs = lead.get('_buying_signal')  # Phase 3: echte, datierte Kaufsignale haben Vorrang vor dem manuellen Lead-Feld
    if bs and bs[0] is not None:
        return bs
    if (lead.get('signal_type') or 'kein_signal') == 'kein_signal':
        return None, 'Kein dokumentierter Projektanlass – unbekannt, nicht schlecht.'
    if not lead.get('signal_date'):
        return 50, 'Anlass dokumentiert, Datum unbekannt.'
    try:
        age = (dt.date.today() - dt.date.fromisoformat(lead['signal_date'])).days
    except ValueError:
        return 50, 'Anlass dokumentiert, Datum unlesbar.'
    score = 100 if age <= 30 else 70 if age <= 90 else 40 if age <= 180 else 15
    return score, f'Anlass vor {age} Tagen dokumentiert.'


def score(cap, lead, cfg, catalog_keys):
    results = rubric_results(cap, cfg)
    findings, area = [], {}
    total_w = evaluated_w = 0.0
    for rid, rcfg in cfg['rubrics'].items():
        if not rcfg.get('enabled') or rcfg.get('weight', 0) <= 0:
            continue
        label, offer, question = RUBRIC_TEXT[rid]
        r = results[rid]
        w = float(rcfg['weight'])
        a = area.setdefault(rcfg['area'], {'total': 0.0, 'evaluated': 0.0, 'flagged': 0.0})
        a['total'] += w
        total_w += w
        if r['result'] != 'unbekannt':
            a['evaluated'] += w
            evaluated_w += w
        if r['result'] == 'auffaellig':
            a['flagged'] += w
        findings.append({'rubric': rid, 'area': rcfg['area'], 'label': label, 'issue': RUBRIC_ISSUE[rid], 'weight': w, 'offer': offer if offer in catalog_keys else None,
                         'question': question, **r})
    area_scores = {}
    for key, a in area.items():
        cov = a['evaluated'] / a['total'] if a['total'] else 0
        area_scores[key] = {'score': round(100 * a['flagged'] / a['evaluated']) if a['evaluated'] and cov * 100 >= cfg['min_area_coverage_pct'] else None,
                            'coverage_pct': round(100 * cov)}
    aw = cfg['area_weights']
    avail = [(aw[k], v['score']) for k, v in area_scores.items() if v['score'] is not None and aw.get(k, 0) > 0]
    potential = round(sum(w * s for w, s in avail) / sum(w for w, _ in avail)) if avail else None
    # 2.0.0-dev17 (M27): Unbekanntes zählt nie als schlecht – fehlt die Branche, fällt sie aus der Rechnung heraus;
    # fehlen Branche und Größe, bleibt die Profilnähe offen statt niedrig.
    ind = INDUSTRY_FIT.get(lead.get('industry')) if lead.get('industry') else None
    size = _size_fit(lead.get('employees'))
    related = 100 if any(f['result'] == 'auffaellig' and f['offer'] for f in findings) else 0
    parts = ([(0.4, ind)] if ind is not None else []) + [(0.3, related)] + ([(0.3, size)] if size is not None else [])
    fit = round(sum(w * v for w, v in parts) / sum(w for w, _ in parts)) if ind is not None or size is not None else None
    fit_basis = (f'Branche {"unbekannt" if ind is None else ind}, Größe {"unbekannt" if size is None else size}, Leistungsbezug {related}'
                 + (' – Profilnähe offen, bis Branche oder Größe bekannt sind' if fit is None else ''))
    signal, signal_basis = _signal_score(lead)
    coverage = round(100 * evaluated_w / total_w) if total_w else 0
    ow = cfg['overall_weights']
    components = {'potential': potential, 'fit': fit, 'signal': signal}
    overall, reason = None, ''
    if potential is None or coverage < cfg['min_coverage_pct']:
        reason = f'Datenlage unzureichend: Belegabdeckung {coverage} % (mindestens {cfg["min_coverage_pct"]:.0f} % nötig).'
    else:
        known = [(ow[k], v) for k, v in components.items() if v is not None and ow[k] > 0]
        overall = round(sum(w * v for w, v in known) / sum(w for w, _ in known))
        missing = [x for x, v in (('Anlass', signal), ('Profilnähe', fit)) if v is None]
        if missing:
            reason = f"Priorität ohne {' und '.join(missing)} berechnet (nicht bekannt – zählt nicht als schlecht)."
    return {'findings': findings, 'area_scores': area_scores, 'potential': potential, 'fit': fit, 'fit_basis': fit_basis,
            'signal': signal, 'signal_basis': signal_basis, 'coverage': coverage, 'overall': overall, 'overall_note': reason,
            'weights': ow}


def summarize(result, cap, lead, packages):
    flagged = sorted([f for f in result['findings'] if f['result'] == 'auffaellig'],
                     key=lambda f: (-f['weight'], {'gemessen': 0, 'beobachtet': 1, 'hypothese': 2}[f['certainty']]))
    unknown = [f for f in result['findings'] if f['result'] == 'unbekannt']
    uncert = [f'{f["label"]}: {f["evidence"]}' for f in unknown]
    if cap.get('renderer') != 'playwright':
        uncert.insert(0, 'Ohne Browser-Rendering erfasst: Gestaltung, Mobilansicht und Ladezeit sind nicht bewertet.')
    if any(f['rubric'] == 'B1_load_time' and f['result'] != 'unbekannt' for f in result['findings']):
        uncert.append('Ladezeit ist eine einmalige Messung von diesem Rechner ohne Cache – nur ein Richtwert.')
    if any(f['certainty'] == 'hypothese' and f['result'] == 'auffaellig' for f in flagged):
        uncert.append('Prozess-Hinweise (Bereich C) sind Hypothesen: Ein PDF-Download beweist keinen ineffizienten internen Prozess.')
    uncert += [e for e in cap.get('errors', [])]
    offers = {}
    for f in flagged:
        if f['offer']:
            o = offers.setdefault(f['offer'], {'key': f['offer'], 'title': packages[f['offer']]['title'], 'reasons': [], 'weight': 0})
            o['reasons'].append(f['issue'])
            o['weight'] += f['weight']
    questions = []
    for f in flagged:
        if f['question'] not in questions:
            questions.append(f['question'])
    for q in GENERIC_QUESTIONS:
        if len(questions) >= 3:
            break
        questions.append(q)
    if result['overall'] is None:
        next_step = 'Datenlage unzureichend: Website manuell ansehen bzw. Bewertung mit Browser-Rendering wiederholen.'
    elif lead.get('permission') not in ('opt_in', 'bestandskunde_pruefen'):
        next_step = 'Belegte Beobachtungen für das Erstgespräch vormerken und zuerst einen zulässigen Kontaktweg klären (Empfehlung, Messe, Brief).'
    else:
        next_step = 'Bedarfsfragen im vereinbarten Gespräch stellen und Hypothesen bestätigen oder verwerfen.'
    return {'observations': flagged[:10], 'uncertainties': uncert[:15],
            'offers': sorted(offers.values(), key=lambda o: -o['weight']),
            'questions': questions[:5], 'next_step': next_step,
            'disclaimer': 'Auffälligkeiten aus öffentlich sichtbaren Merkmalen: ein höherer Wert heißt mehr belegte Hinweise, nicht „schlechte Website“ – '
                          'SignalDesk vergibt keine Qualitätsnote. Keine Aussage über Kaufbereitschaft, Budget oder Werbeeinwilligung. '
                          'Paketempfehlungen sind vor der Bedarfsklärung unverbindlich.'}


def _now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------- Speicherung & Auftragslauf

def init_website_scorer(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS score_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT NOT NULL UNIQUE, config_json TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS website_audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', error TEXT NOT NULL DEFAULT '',
        renderer TEXT NOT NULL DEFAULT '', version_id INTEGER REFERENCES score_versions(id),
        capture_json TEXT NOT NULL DEFAULT '{}', summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS website_findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL REFERENCES website_audits(id) ON DELETE CASCADE,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        rubric TEXT NOT NULL, area TEXT NOT NULL, label TEXT NOT NULL, result TEXT NOT NULL, weight REAL NOT NULL,
        evidence TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', screenshot_id INTEGER,
        method TEXT NOT NULL, certainty TEXT NOT NULL, offer TEXT, question TEXT NOT NULL DEFAULT '',
        review_status TEXT NOT NULL DEFAULT 'ungeprueft'
      );
      CREATE TABLE IF NOT EXISTS website_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL UNIQUE REFERENCES website_audits(id) ON DELETE CASCADE,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        version_id INTEGER NOT NULL REFERENCES score_versions(id),
        design INTEGER, web INTEGER, process INTEGER, potential INTEGER, fit INTEGER, signal INTEGER,
        coverage INTEGER NOT NULL, overall INTEGER, basis_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS website_screenshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL REFERENCES website_audits(id) ON DELETE CASCADE,
        page_url TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, size_bytes INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_website_audits_lead ON website_audits(lead_id, id);
      CREATE INDEX IF NOT EXISTS idx_website_scores_lead ON website_scores(lead_id, id);
    ''')
    active = conn.execute('SELECT hash, config_json FROM score_versions WHERE active=1').fetchone()
    if not active:
        activate_config(conn, DEFAULT_CONFIG)
    else:
        cfg = json.loads(active['config_json'])
        if active['hash'] != config_hash(cfg):
            activate_config(conn, cfg)


def activate_config(conn, cfg):
    h = config_hash(cfg)
    conn.execute('INSERT OR IGNORE INTO score_versions(hash, config_json) VALUES (?,?)', (h, json.dumps(cfg, sort_keys=True)))
    conn.execute('UPDATE score_versions SET active = (hash = ?)', (h,))
    return conn.execute('SELECT * FROM score_versions WHERE hash=?', (h,)).fetchone()


def active_version(conn):
    row = conn.execute('SELECT * FROM score_versions WHERE active=1').fetchone()
    return row['id'], json.loads(row['config_json'])


def recover_audits(conn):
    conn.execute("UPDATE website_audits SET status='failed', error='Durch Neustart unterbrochen – bitte erneut starten.', finished_at=datetime('now') WHERE status IN ('queued','running')")


def screenshot_dir(db_path):
    return Path(db_path).resolve().parent / 'screenshots'


_QUEUE_LOCK = threading.Lock()
_WORKER = {'thread': None}


def enqueue(conn, lead_ids, db_path):
    if not isinstance(lead_ids, list) or not 1 <= len(lead_ids) <= 20 or any(isinstance(i, bool) or not isinstance(i, int) for i in lead_ids):
        raise ValueError('1–20 Lead-IDs angeben.')
    created, skipped = [], []
    for lid in dict.fromkeys(lead_ids):
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        if not lead:
            skipped.append({'lead_id': lid, 'reason': 'nicht gefunden'})
        elif not lead['website']:
            skipped.append({'lead_id': lid, 'reason': 'keine Website'})
        elif lead['stage'] == 'gesperrt' or lead['permission'] == 'nicht_kontaktieren':
            skipped.append({'lead_id': lid, 'reason': 'gesperrt'})
        elif conn.execute("SELECT 1 FROM website_audits WHERE lead_id=? AND status IN ('queued','running')", (lid,)).fetchone():
            skipped.append({'lead_id': lid, 'reason': 'läuft bereits'})
        else:
            cur = conn.execute('INSERT INTO website_audits(lead_id, url) VALUES (?,?)', (lid, lead['website']))
            created.append(cur.lastrowid)
    conn.commit()
    if created:
        _ensure_worker(db_path)
    return {'queued': created, 'skipped': skipped}


def _ensure_worker(db_path):
    with _QUEUE_LOCK:
        t = _WORKER['thread']
        if t and t.is_alive():
            return
        t = threading.Thread(target=_worker, args=(db_path,), daemon=True, name='website-scorer')
        _WORKER['thread'] = t
        t.start()


def wait_idle(timeout=60):
    t = _WORKER['thread']
    if t:
        t.join(timeout)


def _worker(db_path):
    from .model import connect
    while True:
        with connect(db_path) as conn:
            row = conn.execute("SELECT id FROM website_audits WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
            if not row:
                return
            conn.execute("UPDATE website_audits SET status='running', started_at=datetime('now') WHERE id=?", (row['id'],))
            conn.commit()
        run_audit(db_path, row['id'])


def run_audit(db_path, audit_id):
    from .model import connect
    from .catalog import VORLAGEN
    with connect(db_path) as conn:
        audit = conn.execute('SELECT * FROM website_audits WHERE id=?', (audit_id,)).fetchone()
        lead = dict(conn.execute('SELECT * FROM leads WHERE id=?', (audit['lead_id'],)).fetchone())
        from .buying_signals import signal_strength_for_scoring
        lead['_buying_signal'] = signal_strength_for_scoring(conn, lead['id'])
        version_id, cfg = active_version(conn)
    try:
        if playwright_available():
            cap = CAPTURE(audit['url'])
        else:
            cap = CAPTURE_FALLBACK(audit['url'])
    except CrawlError as exc:
        with connect(db_path) as conn:
            conn.execute("UPDATE website_audits SET status='failed', error=?, finished_at=datetime('now') WHERE id=?", (str(exc)[:500], audit_id))
            conn.commit()
        return
    except Exception as exc:  # unerwartet: protokollieren statt Absturz des Auftragslaufs
        with connect(db_path) as conn:
            conn.execute("UPDATE website_audits SET status='failed', error=?, finished_at=datetime('now') WHERE id=?",
                         (f'Unerwarteter Fehler: {exc.__class__.__name__}: {str(exc)[:200]}', audit_id))
            conn.commit()
        return
    result = score(cap, lead, cfg, set(VORLAGEN))
    summary = summarize(result, cap, lead, VORLAGEN)
    folder = screenshot_dir(db_path) / f'audit-{audit_id}'
    folder.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        shot_ids = {}
        for n, shot in enumerate(cap.get('screenshots', []), 1):
            path = folder / f'{n:02d}-{shot["kind"]}.jpg'
            path.write_bytes(shot['bytes'])
            cur = conn.execute('INSERT INTO website_screenshots(audit_id, page_url, kind, path, size_bytes) VALUES (?,?,?,?,?)',
                               (audit_id, shot['page_url'], shot['kind'], str(path), len(shot['bytes'])))
            shot_ids.setdefault(shot['kind'], cur.lastrowid)
        for f in result['findings']:
            conn.execute('''INSERT INTO website_findings(audit_id, lead_id, rubric, area, label, result, weight, evidence, source_url,
                            screenshot_id, method, certainty, offer, question) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (audit_id, lead['id'], f['rubric'], f['area'], f['label'], f['result'], f['weight'], f['evidence'][:800],
                          f['source_url'] or '', shot_ids.get(f['screenshot_kind']), f['method'], f['certainty'], f['offer'], f['question']))
        a = result['area_scores']
        basis = {k: result[k] for k in ('fit_basis', 'signal_basis', 'overall_note', 'weights', 'area_scores')}
        conn.execute('''INSERT INTO website_scores(audit_id, lead_id, version_id, design, web, process, potential, fit, signal, coverage, overall, basis_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                     (audit_id, lead['id'], version_id, a.get('design', {}).get('score'), a.get('web', {}).get('score'), a.get('process', {}).get('score'),
                      result['potential'], result['fit'], result['signal'], result['coverage'], result['overall'], json.dumps(basis, ensure_ascii=False)))
        slim = {k: v for k, v in cap.items() if k not in ('screenshots',)}
        for p in slim.get('pages', []):
            for view in ('desktop', 'mobile'):
                if view in p:
                    p[view] = {k: v for k, v in p[view].items() if k not in ('text', 'links')}
        conn.execute("""UPDATE website_audits SET status='done', renderer=?, version_id=?, capture_json=?, summary_json=?, finished_at=datetime('now') WHERE id=?""",
                     (cap.get('renderer', ''), version_id, json.dumps(slim, ensure_ascii=False), json.dumps(summary, ensure_ascii=False), audit_id))
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (lead['id'], 'notiz', f"Website-Bewertung v2: {'Gesamt ' + str(result['overall']) if result['overall'] is not None else 'Datenlage unzureichend'} · Belegabdeckung {result['coverage']} %"))
        conn.commit()


# ---------------------------------------------------------------- Lesen

def audit_detail(conn, audit_id):
    a = conn.execute('SELECT * FROM website_audits WHERE id=?', (audit_id,)).fetchone()
    if not a:
        raise LookupError('Bewertung nicht gefunden.')
    out = dict(a)
    out['capture'] = json.loads(out.pop('capture_json') or '{}')
    out['summary'] = json.loads(out.pop('summary_json') or '{}')
    out['findings'] = [dict(r) for r in conn.execute('SELECT * FROM website_findings WHERE audit_id=? ORDER BY area, result, -weight', (audit_id,))]
    out['screenshots'] = [dict(r) | {'path': None} for r in conn.execute('SELECT id, page_url, kind, size_bytes, path FROM website_screenshots WHERE audit_id=? ORDER BY id', (audit_id,))]
    s = conn.execute('SELECT * FROM website_scores WHERE audit_id=?', (audit_id,)).fetchone()
    out['score'] = (dict(s) | {'basis': json.loads(s['basis_json'])}) if s else None
    if s:
        out['score'].pop('basis_json')
        prev = conn.execute('SELECT * FROM website_scores WHERE lead_id=? AND id<? ORDER BY id DESC LIMIT 1', (s['lead_id'], s['id'])).fetchone()
        if prev:
            same = prev['version_id'] == s['version_id']
            out['comparison'] = {'previous_audit_id': prev['audit_id'], 'previous_overall': prev['overall'], 'comparable': same,
                                 'delta': (s['overall'] - prev['overall']) if same and s['overall'] is not None and prev['overall'] is not None else None,
                                 'note': None if same else 'Nicht direkt vergleichbar: andere Bewertungsversion (Rubriken/Gewichte geändert).'}
    v = conn.execute('SELECT hash, created_at FROM score_versions WHERE id=?', (out['version_id'],)).fetchone() if out['version_id'] else None
    out['version'] = dict(v) if v else None
    return out


def lead_audits(conn, lead_id):
    return [dict(r) for r in conn.execute('''SELECT a.id, a.status, a.error, a.renderer, a.created_at, a.finished_at, s.overall, s.coverage, v.hash AS version
                                             FROM website_audits a LEFT JOIN website_scores s ON s.audit_id=a.id
                                             LEFT JOIN score_versions v ON v.id=a.version_id WHERE a.lead_id=? ORDER BY a.id DESC LIMIT 20''', (lead_id,))]


def ranking(conn):
    rows = conn.execute('''SELECT l.id AS lead_id, l.company, l.website, l.stage, l.permission, s.audit_id, s.design, s.web, s.process,
                              s.potential, s.fit, s.signal, s.coverage, s.overall, s.created_at, v.hash AS version, v.active
                           FROM leads l JOIN website_scores s ON s.id = (SELECT MAX(id) FROM website_scores WHERE lead_id=l.id)
                           JOIN score_versions v ON v.id=s.version_id
                           WHERE l.stage NOT IN ('gesperrt') ORDER BY (s.overall IS NULL), s.overall DESC, s.coverage DESC''').fetchall()
    queue = [dict(r) for r in conn.execute("""SELECT a.id, a.lead_id, l.company, a.status, a.error, a.created_at FROM website_audits a
                                              JOIN leads l ON l.id=a.lead_id WHERE a.status IN ('queued','running') OR (a.status='failed' AND a.finished_at >= datetime('now','-1 day'))
                                              ORDER BY a.id DESC LIMIT 30""")]
    return {'ranking': [dict(r) for r in rows], 'queue': queue}


def screenshot_file(conn, shot_id, db_path):
    row = conn.execute('SELECT path FROM website_screenshots WHERE id=?', (shot_id,)).fetchone()
    if not row:
        raise LookupError('Screenshot nicht gefunden.')
    path = Path(row['path']).resolve()
    root = screenshot_dir(db_path).resolve()
    if root not in path.parents or not path.exists():
        raise LookupError('Screenshot nicht verfügbar.')
    return path.read_bytes()


# ---------------------------------------------------------------- HTTP-Routen

def route_scoring(h, conn, method, route, query, db_path):
    if route == '/api/scoring/config':
        if method == 'GET':
            vid, cfg = active_version(conn)
            h._send(200, {'config': cfg, 'version_id': vid, 'hash': config_hash(cfg), 'rubric_text': {k: v[0] for k, v in RUBRIC_TEXT.items()},
                          'area_labels': AREA_LABELS, 'renderer_available': playwright_available(), 'defaults': DEFAULT_CONFIG})
            return True
        if method == 'PUT':
            cfg = validate_config(h._body())
            row = activate_config(conn, cfg)
            conn.commit()
            h._send(200, {'version_id': row['id'], 'hash': row['hash'], 'config': cfg,
                          'notice': 'Neue Bewertungsversion aktiv. Ältere Ergebnisse bleiben erhalten, sind aber nicht direkt vergleichbar.'})
            return True
    if route == '/api/scoring/audits' and method == 'POST':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'lead_ids'}:
            raise ValueError('Erwartet: {lead_ids: [...]}.')
        h._send(202, enqueue(conn, body['lead_ids'], db_path))
        return True
    if route == '/api/scoring/overview' and method == 'GET':
        h._send(200, ranking(conn))
        return True
    m = re.fullmatch(r'/api/scoring/audits/(\d+)', route)
    if m and method == 'GET':
        h._send(200, audit_detail(conn, int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/leads/(\d+)/website-scores', route)
    if m and method == 'GET':
        h._send(200, lead_audits(conn, int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/scoring/findings/(\d+)', route)
    if m and method == 'PATCH':
        body = h._body()
        if not isinstance(body, dict) or set(body) != {'review_status'} or body['review_status'] not in ('ungeprueft', 'bestaetigt', 'verworfen'):
            raise ValueError("review_status: ungeprueft, bestaetigt oder verworfen.")
        cur = conn.execute('UPDATE website_findings SET review_status=? WHERE id=?', (body['review_status'], int(m.group(1))))
        if not cur.rowcount:
            raise LookupError('Befund nicht gefunden.')
        conn.commit()
        h._send(200, {'saved': True})
        return True
    m = re.fullmatch(r'/api/screenshots/(\d+)', route)
    if m and method == 'GET':
        h._send_raw(200, screenshot_file(conn, int(m.group(1)), db_path), 'image/jpeg')
        return True
    return False
