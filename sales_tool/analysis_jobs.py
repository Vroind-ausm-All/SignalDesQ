"""Persisted local analysis job: browser -> provider -> source-validated findings."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .ai_provider import analyze
from .model import connect
from .website_analyzer import crawl_site


def run_job(db_path: str | Path, run_id: int, lead_id: int, url: str, provider: str, model: str):
    with connect(db_path) as conn:
        conn.execute("UPDATE analysis_runs SET status='running' WHERE id=? AND status='queued'", (run_id,))
        conn.commit()
    try:
        crawl = crawl_site(url)
        result = analyze(crawl, provider=provider, model=model)
        with connect(db_path) as conn:
            conn.execute("""UPDATE analysis_runs SET status='done',summary=?,pages_json=?,warnings_json=?,
                         finished_at=datetime('now') WHERE id=?""",
                         (result['summary'], json.dumps([{'url': p['url'], 'title': p['title']} for p in crawl['pages']], ensure_ascii=False),
                          json.dumps(crawl.get('warnings', []) +
                                     ([f"{result['discarded']} unbelegte KI-Befunde verworfen."] if result['discarded'] else []),
                                     ensure_ascii=False), run_id))
            for f in result['findings']:
                conn.execute("""INSERT INTO findings
                   (run_id,lead_id,category,observation,hypothesis,evidence,source_url,offer,question)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                   (run_id, lead_id, *(f[k] for k in ('category','observation','hypothesis','evidence','source_url','offer','question'))))
            conn.commit()
    except Exception as exc:
        # Do not leak internal paths or network details into the browser.
        msg = str(exc)[:300] if isinstance(exc, ValueError) else "Technischer Analysefehler. Serverkonsole prüfen."
        with connect(db_path) as conn:
            conn.execute("UPDATE analysis_runs SET status='failed',error=?,finished_at=datetime('now') WHERE id=?",
                         (msg, run_id))
            conn.commit()
        if not isinstance(exc, ValueError):
            print('Analysis job failed:', repr(exc))


def enqueue(db_path, run_id, lead_id, url, provider, model):
    worker = threading.Thread(target=run_job, args=(db_path, run_id, lead_id, url, provider, model),
                              daemon=True, name=f"signaldesk-audit-{run_id}")
    worker.start()


def list_analyses(conn, lead_id):
    runs = [dict(r) for r in conn.execute("SELECT * FROM analysis_runs WHERE lead_id=? ORDER BY id DESC LIMIT 10", (lead_id,))]
    for run in runs:
        run['pages'] = json.loads(run.pop('pages_json'))
        run['warnings'] = json.loads(run.pop('warnings_json'))
        run['findings'] = [dict(f) for f in conn.execute("SELECT * FROM findings WHERE run_id=? ORDER BY id", (run['id'],))]
    return runs
