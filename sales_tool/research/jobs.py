"""Persistente Recherche-Aufträge (Masterplan 2.0, Sprint 3) – ersetzt die einzelnen Daemon-Threads schrittweise.

Modell:
- research_jobs: ein Auftrag (z. B. „Firmen-Berichte für 12 Firmen“) mit Zustand
  queued → running → done | partial | failed, jederzeit paused / cancelled; optional idempotenter Schlüssel.
- research_tasks: ein Arbeitsschritt je Firma bzw. Quelle, mit lease_until (Heartbeat), Versuchszähler, next_attempt_at
  (Wartezeit nach Fehler), eigener Fehlerliste und eindeutigem task_key je Auftrag.
- Worker: höchstens MAX_WORKERS gleichzeitig (Start: 3), je Domain höchstens EIN laufender Schritt.
- Neustart: laufende Schritte gehen zurück in die Warteschlange (recover) – kein Datenverlust; die Schritte selbst sind
  idempotent (Dubletten-Schlüssel, add_fact-Abgleich), ein zweiter Lauf erzeugt keine doppelten Fakten oder Leads.
- Ein Fehler (403, Zeitüberschreitung …) betrifft nur seinen Schritt; der Auftrag läuft weiter und endet ggf. „partial“.
"""
from __future__ import annotations

import json
import threading
import time

JOB_ACTIVE = ('queued', 'running', 'paused')
TASK_TERMINAL = ('done', 'failed', 'skipped', 'cancelled')
MAX_WORKERS = 3
LEASE_SECONDS = 900
BACKOFF = (30, 120, 600)
POLL = 1.0
CLOCK = time.time  # in Tests ersetzbar

HANDLERS = {}
_LOCK = threading.Lock()
_WORKERS = {}  # Datenbankpfad → Worker-Threads (je Datenbank eigene Worker)
_STOP = {}  # Datenbankpfad → Ereignis „Worker beenden“ (sauberes Beenden; unter Windows gibt das die Datei frei)


def _stop_event(key):
    with _LOCK:
        return _STOP.setdefault(key, threading.Event())


class Retry(Exception):
    """Vorübergehender Fehler: später erneut versuchen (``delay`` Sekunden, sonst BACKOFF)."""

    def __init__(self, message, delay=None):
        super().__init__(message)
        self.delay = delay


class Skip(Exception):
    """Schritt ist nicht ausführbar (z. B. keine Website) – kein Fehler des Auftrags."""


def handler(kind):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def init_jobs(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS research_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, job_key TEXT NOT NULL DEFAULT '', label TEXT NOT NULL DEFAULT '',
        params_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'queued', priority INTEGER NOT NULL DEFAULT 5,
        total INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), started_at TEXT NOT NULL DEFAULT '',
        finished_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status, kind);
      CREATE UNIQUE INDEX IF NOT EXISTS ux_research_jobs_active_key ON research_jobs(job_key)
        WHERE job_key<>'' AND status IN ('queued','running','paused');
      CREATE TABLE IF NOT EXISTS research_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
        task_key TEXT NOT NULL, kind TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', domain TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3, lease_until REAL NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '', errors_json TEXT NOT NULL DEFAULT '[]', result_json TEXT NOT NULL DEFAULT '{}',
        note TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT '',
        UNIQUE(job_id, task_key)
      );
      CREATE INDEX IF NOT EXISTS idx_research_tasks_claim ON research_tasks(status, next_attempt_at, job_id);
      CREATE INDEX IF NOT EXISTS idx_research_tasks_domain ON research_tasks(domain, status);
    ''')


def _now_txt():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())


# ---------------------------------------------------------------- Aufträge anlegen und steuern

def submit(conn, kind, label, tasks, job_key='', params=None, priority=5, db_path=None, start=True, max_attempts=3):
    """Legt einen Auftrag an. Gibt (job, created) zurück. Läuft schon ein Auftrag mit gleichem Schlüssel, wird dieser
    zurückgegeben (idempotent) – Doppelklicks oder ein zweiter Start erzeugen keinen zweiten Auftrag."""
    if job_key:
        row = conn.execute(f"SELECT id FROM research_jobs WHERE job_key=? AND status IN ({','.join('?' * len(JOB_ACTIVE))})",
                           (job_key, *JOB_ACTIVE)).fetchone()
        if row:
            return job_view(conn, row['id'], tasks=False), False
    cur = conn.execute('INSERT INTO research_jobs(kind, job_key, label, params_json, priority) VALUES (?,?,?,?,?)',
                       (kind, job_key, label[:200], json.dumps(params or {}, ensure_ascii=False), priority))
    job_id = cur.lastrowid
    add_tasks(conn, job_id, tasks, max_attempts=max_attempts)
    conn.commit()
    if start and db_path:
        ensure_workers(db_path)
    return job_view(conn, job_id, tasks=False), True


def add_tasks(conn, job_id, tasks, max_attempts=3):
    n = 0
    for t in tasks:
        n += conn.execute('''INSERT OR IGNORE INTO research_tasks(job_id, task_key, kind, label, domain, payload_json, max_attempts)
                             VALUES (?,?,?,?,?,?,?)''', (job_id, str(t['key'])[:200], t['kind'], str(t.get('label', ''))[:200],
                                                         (t.get('domain') or '').lower()[:200], json.dumps(t.get('payload') or {}, ensure_ascii=False),
                                                         int(t.get('max_attempts') or max_attempts))).rowcount
    _refresh(conn, job_id)
    return n


def _refresh(conn, job_id):
    c = {r['status']: r['n'] for r in conn.execute('SELECT status, COUNT(*) AS n FROM research_tasks WHERE job_id=? GROUP BY status', (job_id,))}
    total = sum(c.values())
    job = conn.execute('SELECT status FROM research_jobs WHERE id=?', (job_id,)).fetchone()
    if not job:
        return
    status = job['status']
    open_ = c.get('queued', 0) + c.get('running', 0)
    if status not in ('paused', 'cancelled'):
        if open_:
            status = 'running' if (c.get('running') or c.get('done') or c.get('failed') or c.get('skipped')) else 'queued'
        elif total:
            status = 'done' if not c.get('failed') else ('partial' if c.get('done') or c.get('skipped') else 'failed')
    finished = _now_txt() if status in ('done', 'partial', 'failed', 'cancelled') else ''
    conn.execute('''UPDATE research_jobs SET total=?, done=?, failed=?, skipped=?, status=?, updated_at=datetime('now'),
                    started_at=CASE WHEN started_at='' AND ? IN ('running','done','partial','failed') THEN datetime('now') ELSE started_at END,
                    finished_at=CASE WHEN ?<>'' THEN ? ELSE '' END WHERE id=?''',
                 (total, c.get('done', 0), c.get('failed', 0), c.get('skipped', 0), status, status, finished, finished, job_id))


def pause(conn, job_id):
    _require(conn, job_id, ('queued', 'running'), 'Nur laufende oder wartende Aufträge können pausiert werden.')
    conn.execute("UPDATE research_jobs SET status='paused', updated_at=datetime('now') WHERE id=?", (job_id,))
    conn.commit()
    return job_view(conn, job_id)


def resume(conn, job_id, db_path=None):
    _require(conn, job_id, ('paused',), 'Nur pausierte Aufträge können fortgesetzt werden.')
    conn.execute("UPDATE research_jobs SET status='queued' WHERE id=?", (job_id,))
    _refresh(conn, job_id)
    conn.commit()
    if db_path:
        ensure_workers(db_path)
    return job_view(conn, job_id)


def cancel(conn, job_id):
    _require(conn, job_id, JOB_ACTIVE, 'Auftrag ist bereits beendet.')
    queued = [dict(r) for r in conn.execute("SELECT * FROM research_tasks WHERE job_id=? AND status='queued'", (job_id,))]
    conn.execute("UPDATE research_tasks SET status='cancelled', finished_at=? WHERE job_id=? AND status='queued'", (_now_txt(), job_id))
    conn.execute("UPDATE research_jobs SET status='cancelled' WHERE id=?", (job_id,))
    _refresh(conn, job_id)
    conn.commit()
    for t in queued:  # Fachliche Aufräumarbeiten je Art (z. B. Bericht als „abgebrochen“ markieren)
        hook = HANDLERS.get(t['kind'] + ':cancel')
        if hook:
            hook(conn, json.loads(t['payload_json']))
    conn.commit()
    return job_view(conn, job_id)


def retry_failed(conn, job_id, db_path=None, kinds=None):
    job = conn.execute('SELECT * FROM research_jobs WHERE id=?', (job_id,)).fetchone()
    if not job:
        raise LookupError('Auftrag nicht gefunden.')
    q = "UPDATE research_tasks SET status='queued', attempts=0, next_attempt_at=0, last_error='' WHERE job_id=? AND status='failed'"
    args = [job_id]
    if kinds:
        q += f" AND kind IN ({','.join('?' * len(kinds))})"
        args += list(kinds)
    n = conn.execute(q, args).rowcount
    if not n:
        raise ValueError('Keine fehlgeschlagenen Schritte in diesem Auftrag.')
    conn.execute("UPDATE research_jobs SET status='queued', finished_at='' WHERE id=?", (job_id,))
    hook = HANDLERS.get(job['kind'] + ':retry')
    if hook:
        hook(conn, job_id)
    _refresh(conn, job_id)
    conn.commit()
    if db_path:
        ensure_workers(db_path)
    return job_view(conn, job_id)


def _require(conn, job_id, states, msg):
    job = conn.execute('SELECT status FROM research_jobs WHERE id=?', (job_id,)).fetchone()
    if not job:
        raise LookupError('Auftrag nicht gefunden.')
    if job['status'] not in states:
        raise ValueError(msg)


def recover(conn):
    """Nach einem Neustart: unterbrochene Schritte wieder einreihen (Zähler bleibt), Aufträge wieder „wartend“."""
    n = conn.execute("""UPDATE research_tasks SET status='queued', lease_until=0, note='nach Neustart erneut eingereiht'
                        WHERE status='running'""").rowcount
    for r in conn.execute("SELECT id FROM research_jobs WHERE status IN ('queued','running')").fetchall():
        conn.execute("UPDATE research_jobs SET status='queued' WHERE id=?", (r['id'],))
        _refresh(conn, r['id'])
    conn.commit()
    return n


# ---------------------------------------------------------------- Ausführen

def claim(conn, kinds=None):
    """Nächsten ausführbaren Schritt reservieren (atomar). Beachtet Pause/Abbruch, Wartezeiten und „je Domain einer“."""
    now = CLOCK()
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    try:
        sql = '''SELECT t.* FROM research_tasks t JOIN research_jobs j ON j.id=t.job_id
                 WHERE t.status='queued' AND t.next_attempt_at<=? AND j.status IN ('queued','running')
                 AND (t.domain='' OR t.domain NOT IN (SELECT domain FROM research_tasks WHERE status='running' AND domain<>'' AND lease_until>?))'''
        args = [now, now]
        if kinds:
            sql += f" AND t.kind IN ({','.join('?' * len(kinds))})"
            args += list(kinds)
        from .. import netpolicy
        if netpolicy.offline():  # v1.19: Aufträge mit Internetbedarf warten im Offline-Modus
            sql += f" AND t.kind NOT IN ({','.join('?' * len(netpolicy.NETWORK_KINDS))})"
            args += list(netpolicy.NETWORK_KINDS)
        row = conn.execute(sql + ' ORDER BY j.priority, t.id LIMIT 1', args).fetchone()
        if not row:
            conn.commit()
            return None
        conn.execute("""UPDATE research_tasks SET status='running', attempts=attempts+1, lease_until=?, started_at=?, note='' WHERE id=?""",
                     (now + LEASE_SECONDS, _now_txt(), row['id']))
        _refresh(conn, row['job_id'])
        conn.commit()
        return conn.execute('SELECT * FROM research_tasks WHERE id=?', (row['id'],)).fetchone()
    except Exception:
        conn.rollback()
        raise


class Context:
    def __init__(self, db_path, task):
        self.db_path, self.task_id, self.job_id, self.attempt = db_path, task['id'], task['job_id'], task['attempts']

    def heartbeat(self, note=''):
        from ..model import connect
        with connect(self.db_path) as c:
            c.execute('UPDATE research_tasks SET lease_until=?, note=? WHERE id=?', (CLOCK() + LEASE_SECONDS, note[:300], self.task_id))
            c.commit()

    def cancelled(self):
        from ..model import connect
        with connect(self.db_path) as c:
            row = c.execute('SELECT status FROM research_jobs WHERE id=?', (self.job_id,)).fetchone()
            return not row or row['status'] in ('cancelled', 'paused')


def _finish(conn, task, status, result=None, error='', retry_delay=None):
    errors = json.loads(task['errors_json'] or '[]')
    if error:
        errors = (errors + [{'at': _now_txt(), 'attempt': task['attempts'], 'error': error[:400]}])[-10:]
    if status == 'retry':
        delay = retry_delay if retry_delay is not None else BACKOFF[min(task['attempts'] - 1, len(BACKOFF) - 1)]
        conn.execute("""UPDATE research_tasks SET status='queued', lease_until=0, next_attempt_at=?, last_error=?, errors_json=?,
                        note=? WHERE id=?""", (CLOCK() + delay, error[:400], json.dumps(errors, ensure_ascii=False),
                                               f'neuer Versuch in {int(delay)} s', task['id']))
    else:
        conn.execute("""UPDATE research_tasks SET status=?, lease_until=0, last_error=?, errors_json=?, result_json=?, finished_at=?
                        WHERE id=?""", (status, error[:400], json.dumps(errors, ensure_ascii=False),
                                        json.dumps(result or {}, ensure_ascii=False, default=str), _now_txt(), task['id']))
    _refresh(conn, task['job_id'])
    conn.commit()


def run_one(db_path, kinds=None):
    """Einen Schritt ausführen. Gibt True zurück, wenn etwas zu tun war."""
    from ..model import connect
    with connect(db_path) as conn:
        task = claim(conn, kinds)
        if not task:
            return False
    fn = HANDLERS.get(task['kind'])
    payload = json.loads(task['payload_json'] or '{}')
    status, result, error, delay = 'done', None, '', None
    try:
        if not fn:
            raise ValueError(f'Unbekannte Auftragsart „{task["kind"]}“.')
        result = fn(db_path, payload, Context(db_path, task)) or {}
        if isinstance(result, dict) and result.get('_status') in ('failed', 'skipped'):
            status, error = result.pop('_status'), str(result.pop('_error', ''))
    except Retry as exc:
        status, error, delay = ('retry' if task['attempts'] < task['max_attempts'] else 'failed'), str(exc), exc.delay
    except Skip as exc:
        status, error = 'skipped', str(exc)
    except Exception as exc:  # noqa: BLE001 – ein Schritt darf den Auftrag nie stoppen
        status, error = 'failed', f'{exc.__class__.__name__}: {exc}'
    with connect(db_path) as conn:
        _finish(conn, conn.execute('SELECT * FROM research_tasks WHERE id=?', (task['id'],)).fetchone(), status, result, error, delay)
    return True


def pending(conn, kinds=None):
    sql = """SELECT MIN(t.next_attempt_at) AS nxt, COUNT(*) AS n FROM research_tasks t JOIN research_jobs j ON j.id=t.job_id
             WHERE t.status IN ('queued','running') AND j.status IN ('queued','running')"""
    args = []
    if kinds:
        sql += f" AND t.kind IN ({','.join('?' * len(kinds))})"
        args = list(kinds)
    row = conn.execute(sql, args).fetchone()
    return row['n'], row['nxt']


def run_until_idle(db_path, kinds=None, max_tasks=10_000):
    """Synchron abarbeiten, bis nichts sofort Ausführbares mehr da ist (für Tests und Kompatibilitätsfunktionen)."""
    n = 0
    while n < max_tasks and run_one(db_path, kinds):
        n += 1
    return n


def _worker_loop(db_path):
    from ..model import connect
    idle_since = None
    stop = _stop_event(db_path)
    while True:
        if stop.is_set():
            return
        try:
            if run_one(db_path):
                idle_since = None
                continue
        except Exception:  # noqa: BLE001 – Datenbank kurz gesperrt o. Ä.: kurz warten, nicht abstürzen
            stop.wait(POLL)
            continue
        with connect(db_path) as conn:
            n, nxt = pending(conn)
        if not n:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since > 5:
                return
        stop.wait(POLL if not nxt else max(0.2, min(POLL * 5, (nxt or 0) - CLOCK())))  # wacht beim Beenden sofort auf


def ensure_workers(db_path):
    key = str(db_path)
    _stop_event(key).clear()
    with _LOCK:
        alive = [t for t in _WORKERS.get(key, []) if t.is_alive()]
        for _ in range(MAX_WORKERS - len(alive)):
            t = threading.Thread(target=_worker_loop, args=(key,), daemon=True, name=f'research-worker-{len(alive) + 1}')
            alive.append(t)
            t.start()
        _WORKERS[key] = alive


def stop_workers(db_path, timeout=10):
    """Worker dieser Datenbank beenden und warten. Laufende Schritte werden zu Ende geführt; offene bleiben eingereiht
    und laufen beim nächsten Start weiter. Gibt True zurück, wenn alle Worker beendet sind."""
    key = str(db_path)
    _stop_event(key).set()
    with _LOCK:
        threads = list(_WORKERS.get(key, []))
    end = time.monotonic() + timeout
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    alive = [t for t in threads if t.is_alive()]
    with _LOCK:
        _WORKERS[key] = alive
    return not alive


def ensure_workers_all():
    """Nach dem Ausschalten des Offline-Modus: Worker aller bekannten Datenbanken wieder anwerfen."""
    for key in list(_WORKERS):
        ensure_workers(key)


def workers_alive(db_path):
    return sum(t.is_alive() for t in _WORKERS.get(str(db_path), []))


def wait_idle(db_path, timeout=60, kinds=None):
    """Warten, bis keine Schritte der Art(en) mehr offen sind (für Kompatibilität/Tests)."""
    from ..model import connect
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with connect(db_path) as conn:
            n, _ = pending(conn, kinds)
        if not n:
            return True
        time.sleep(0.1)
    return False


class JobWaiter:
    """Kompatibel zu threading.Thread.join – wartet, bis der Auftrag beendet ist."""

    def __init__(self, db_path, job_id):
        self.db_path, self.job_id = db_path, job_id

    def join(self, timeout=None):
        from ..model import connect
        end = time.monotonic() + (timeout or 3600)
        while time.monotonic() < end:
            with connect(self.db_path) as conn:
                row = conn.execute('SELECT status FROM research_jobs WHERE id=?', (self.job_id,)).fetchone()
            if not row or row['status'] not in ('queued', 'running'):
                return
            time.sleep(0.1)

    def is_alive(self):
        from ..model import connect
        with connect(self.db_path) as conn:
            row = conn.execute('SELECT status FROM research_jobs WHERE id=?', (self.job_id,)).fetchone()
        return bool(row and row['status'] in ('queued', 'running'))


# ---------------------------------------------------------------- Ansicht und HTTP

def job_view(conn, job_id, tasks=True):
    row = conn.execute('SELECT * FROM research_jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        raise LookupError('Auftrag nicht gefunden.')
    d = dict(row)
    d['params'] = json.loads(d.pop('params_json') or '{}')
    if tasks:
        d['tasks'] = [{**{k: r[k] for k in ('id', 'task_key', 'kind', 'label', 'domain', 'status', 'attempts', 'max_attempts', 'last_error',
                                             'note', 'started_at', 'finished_at')},
                       'retry_in': max(0, int(r['next_attempt_at'] - CLOCK())) if r['status'] == 'queued' and r['next_attempt_at'] else 0,
                       'errors': json.loads(r['errors_json'] or '[]')}
                      for r in conn.execute('SELECT * FROM research_tasks WHERE job_id=? ORDER BY id', (job_id,))]
    return d


def list_jobs(conn, kind=None, limit=20):
    q, args = 'SELECT id FROM research_jobs', []
    if kind:
        q += ' WHERE kind=?'
        args.append(kind)
    rows = conn.execute(q + ' ORDER BY (status IN (\'queued\',\'running\',\'paused\')) DESC, id DESC LIMIT ?', (*args, int(limit))).fetchall()
    return [job_view(conn, r['id'], tasks=False) for r in rows]


def route_jobs(h, conn, method, route, query, db_path):
    import re
    if route == '/api/research/jobs' and method == 'GET':
        kind = (query.get('kind') or [''])[0] or None
        h._send(200, {'jobs': list_jobs(conn, kind, 30), 'workers': workers_alive(db_path), 'max_workers': MAX_WORKERS})
        return True
    m = re.fullmatch(r'/api/research/jobs/(\d+)', route)
    if m and method == 'GET':
        h._send(200, job_view(conn, int(m.group(1))))
        return True
    m = re.fullmatch(r'/api/research/jobs/(\d+)/(pause|resume|cancel|retry)', route)
    if m and method == 'POST':
        jid, action = int(m.group(1)), m.group(2)
        out = {'pause': lambda: pause(conn, jid), 'resume': lambda: resume(conn, jid, db_path), 'cancel': lambda: cancel(conn, jid),
               'retry': lambda: retry_failed(conn, jid, db_path)}[action]()
        h._send(200, out)
        return True
    return False
