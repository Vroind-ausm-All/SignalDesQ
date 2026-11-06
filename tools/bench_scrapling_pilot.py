"""Scrapling-Abruf-Pilot (Sprint 1) – NUR Messung, nicht im Produkt.

Läuft in einer eigenen Umgebung mit ``pip install "scrapling[fetchers]==0.5.1"`` und vergleicht den statischen
Scrapling-Fetcher (curl_cffi) mit dem SignalDesk-HTTP-Abruf auf denselben lokalen Testseiten:
Ladezeit des Pakets, Speicher, Antwortzeit, gesendete Kopfzeilen (Tarnung?) und Verhalten bei Weiterleitungen.
Der Pilot verbindet sich direkt mit 127.0.0.1 (Host-Kopfzeile), weil curl eigene DNS-Auflösung nutzt.

Aufruf (Pilot-Umgebung):  <venv>/bin/python tools/bench_scrapling_pilot.py --out docs/bench/scrapling_pilot.json
"""
from __future__ import annotations

import argparse
import http.client
import json
import resource
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from webfixtures import FixtureServer  # noqa: E402

UA = 'SignalDeskResearch/1.15 (+public company data research; single pages, no bulk crawling)'


def rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def stdlib_get(port, host, path):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    c.request('GET', path, headers={'Host': host, 'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate'})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, len(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    out = {'python': sys.version.split()[0], 'rss_start_mb': rss_mb()}
    t = time.perf_counter()
    from scrapling.fetchers import Fetcher  # noqa: E402 – bewusst gemessen
    import scrapling
    out['scrapling'] = scrapling.__version__
    out['import_s'] = round(time.perf_counter() - t, 2)
    out['rss_after_import_mb'] = rss_mb()
    with FixtureServer() as srv:
        hosts = [h for h, s in srv.manifest['sites'].items() if '/' in s['pages'] and not s['routes'].get('/') and not s['routes'].get('*')]
        timings = {'scrapling_default': [], 'scrapling_ohne_tarnung': [], 'stdlib': []}
        headers = {}
        for mode in timings:
            for h in hosts:
                n0 = len(srv.headers_log)
                t = time.perf_counter()
                if mode == 'stdlib':
                    stdlib_get(srv.port, h, '/')
                else:
                    kw = {} if mode == 'scrapling_default' else {'stealthy_headers': False, 'impersonate': None, 'follow_redirects': False,
                                                                'headers': {'User-Agent': UA}}
                    Fetcher.get(f'http://127.0.0.1:{srv.port}/', headers={**kw.pop('headers', {}), 'Host': h}, timeout=10, retries=1, **kw)
                timings[mode].append((time.perf_counter() - t) * 1000)
                if mode not in headers and len(srv.headers_log) > n0:
                    headers[mode] = srv.headers_log[n0][2]
        # Weiterleitung auf lokale Adresse: folgt der Standard-Fetcher ungeprüft?
        n0 = len(srv.log)
        try:
            Fetcher.get(f'http://127.0.0.1:{srv.port}/', headers={'Host': 'boese-weiterleitung.example'}, timeout=5, retries=1)
            out['redirect_to_local_ip'] = 'gefolgt (ohne Prüfung)'
        except Exception as exc:  # noqa: BLE001
            out['redirect_to_local_ip'] = f'Fehler beim Folgen: {exc.__class__.__name__}'
    out['latency_ms'] = {m: {'p50': round(statistics.median(v), 2), 'max': round(max(v), 2), 'n': len(v)} for m, v in timings.items()}
    out['request_headers'] = headers
    out['rss_end_mb'] = rss_mb()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
