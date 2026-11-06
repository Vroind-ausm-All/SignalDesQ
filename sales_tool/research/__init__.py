"""SignalDesk-Recherchetechnik (Masterplan 2.0, Sprint 1): sicherer Abruf, robots.txt, Auswertung – austauschbar.

Einstieg:
    from sales_tool.research import fetch, parse_html
    res = fetch('https://firma.example/impressum')   # FetchResult (IP-Pinning, robots.txt, Grenzen)
    page = parse_html(res.text(), res.final_url)      # Scrapling-Selector, falls installiert – sonst eingebaut
"""
from .fetchers import FetchError, FetchResult, fetch, get_fetcher  # noqa: F401
from .parse import parse_html, scrapling_available  # noqa: F401
from .policy import DEFAULT_POLICY, ROBOTS, FetchPolicy  # noqa: F401
