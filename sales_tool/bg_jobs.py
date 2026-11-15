"""Einzelne Recherche-Läufe über das gemeinsame Auftragssystem (2.0.0-dev36, Produktreview M23 Teil 2).

KI-Analyse, Schnellprüfung und Suche nach öffentlichen Ansprechpartnern liefen als eigener Thread: Ein Neustart brach sie
ab, die Ansprechpartner-Suche blieb sogar dauerhaft auf „läuft“ stehen. Jetzt wird jeder Lauf ein Auftrag mit einem
Schritt – sichtbar unter den Aufträgen, je Domain höchstens ein Abruf gleichzeitig, nach einem Neustart fortgesetzt.
Läufe aus älteren Versionen (ohne Auftragsschritt) werden beim Neustart wie bisher als unterbrochen gekennzeichnet.
"""
from __future__ import annotations

from .research import jobs

TABLES = {  # Auftragsart → (Tabelle, Schlüsselpräfix, Hinweis für ältere Läufe)
    'ki_analyse': ('analysis_runs', 'analysis', 'Analyse durch Neustart unterbrochen.'),
    'schnellpruefung': ('quick_scans', 'quickscan', 'Recherche durch Neustart unterbrochen.'),
    'ansprechpartner': ('contact_research_runs', 'contacts', 'Ansprechpartner-Suche durch Neustart unterbrochen – bitte erneut starten.'),
}


def submit(db_path, kind, run_id, label, url, payload):
    from .company_data import normalize_domain
    from .model import connect
    _, prefix, _ = TABLES[kind]
    task = {'key': f'{prefix}:{run_id}', 'kind': kind, 'label': label[:120], 'domain': normalize_domain(url or '') or '',
            'payload': {'run_id': run_id, **payload}, 'max_attempts': 1}
    with connect(db_path) as conn:
        job, _ = jobs.submit(conn, kind, label[:200], [task], job_key=task['key'], db_path=db_path, start=True, priority=5)
    return job


def recover(conn):
    """Neustart: Läufe mit Auftragsschritt wieder auf „wartet“ (der Schritt wird fortgesetzt), ältere als unterbrochen."""
    out = {}
    for kind, (table, prefix, msg) in TABLES.items():
        resumed = conn.execute(f"""UPDATE {table} SET status='queued' WHERE status IN ('queued','running') AND EXISTS (
            SELECT 1 FROM research_tasks t WHERE t.kind=? AND t.task_key='{prefix}:' || {table}.id AND t.status IN ('queued','running'))""",
                               (kind,)).rowcount
        # übrig: laufend oder wartend ohne Auftragsschritt (ältere Versionen) → als unterbrochen kennzeichnen
        dropped = conn.execute(f"""UPDATE {table} SET status='failed', error=?, finished_at=datetime('now')
            WHERE status='running' OR (status='queued' AND NOT EXISTS (
                SELECT 1 FROM research_tasks t WHERE t.kind=? AND t.task_key='{prefix}:' || {table}.id AND t.status IN ('queued','running')))""",
                               (msg, kind)).rowcount
        out[kind] = {'resumed': resumed, 'dropped': dropped}
    return out


def finished(db_path, kind, run_id):
    """Ergebnis für den Auftragsschritt: fehlgeschlagener Lauf → fehlgeschlagener Schritt (mit Grund)."""
    from .model import connect
    table = TABLES[kind][0]
    with connect(db_path) as conn:
        r = conn.execute(f'SELECT status, error FROM {table} WHERE id=?', (run_id,)).fetchone()
    if not r:
        return {'_status': 'skipped', '_error': 'Lauf nicht mehr vorhanden.'}
    if r['status'] != 'done':
        return {'status': r['status'], '_status': 'failed', '_error': r['error'] or 'Lauf nicht abgeschlossen'}
    return {'status': 'done'}


def still_open(db_path, kind, run_id):
    from .model import connect
    table = TABLES[kind][0]
    with connect(db_path) as conn:
        r = conn.execute(f'SELECT status FROM {table} WHERE id=?', (run_id,)).fetchone()
    if not r or r['status'] not in ('queued', 'running'):
        raise jobs.Skip('Lauf ist nicht mehr offen.')
