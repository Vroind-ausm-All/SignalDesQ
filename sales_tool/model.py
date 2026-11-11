"""Transparent, human-reviewed sales prioritisation and SQLite persistence."""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

STAGES = ("recherche", "qualifiziert", "kontakt", "antwort", "termin", "angebot", "gewonnen", "verloren", "gesperrt")
INDUSTRIES = ("Industrie & B2B-Technik", "B2B-SaaS", "Professionelle Dienstleistungen", "Sonstige")
SIGNALS = {
    "produktlaunch": (24, "Produktlaunch oder neue Leistung"),
    "digitalprojekt": (23, "Digitalprojekt / Relaunch angekündigt"),
    "offene_stelle": (20, "Neue Marketing-, UX- oder IT-Stelle"),
    "prozessproblem": (22, "Manueller Prozess öffentlich erkennbar"),
    "expansion": (19, "Expansion / neuer Standort / Markt"),
    "event": (14, "Veranstaltung / konkreter persönlicher Kontakt"),
    "empfehlung": (21, "Persönliche Empfehlung / Einführung"),
    "kein_signal": (0, "Kein überprüftes Signal"),
}
OFFERS = {
    "pilot": {"title": "Website- & Anfrage-Pilot", "price_from": 990, "price_to": 2500, "period": "1–2 Wochen", "outcome": "Abgegrenzte Analyse und eine konkrete, kleine Verbesserung"},
    "conversion": {"title": "Conversion- & Web-Sprint", "price_from": 4500, "price_to": 8500, "period": "3–4 Wochen", "outcome": "Messbare Anfragen-/Demo-Strecke mit Tracking"},
    "portal": {"title": "Kundenportal & Prozess-App", "price_from": 12000, "price_to": 30000, "period": "6–10 Wochen", "outcome": "Ein manueller Prozess als benutzbare Web-App"},
    "brand": {"title": "Brand & Design-System", "price_from": 3500, "price_to": 7000, "period": "2–4 Wochen", "outcome": "Konsequenter Markenauftritt mit wiederverwendbaren Komponenten"},
    "automation": {"title": "Automatisierungsprojekt", "price_from": 6900, "price_to": 15000, "period": "4–6 Wochen", "outcome": "Ein manueller Ablauf läuft automatisiert und nachvollziehbar"},
}
PERMISSIONS = ("unbekannt", "opt_in", "bestandskunde_pruefen", "telefon_einzelfall", "nicht_kontaktieren")
CONTACT_ROUTES = ("unbekannt", "persoenliche_empfehlung", "inbound", "veranstaltung", "netzwerk", "brief", "ausschreibung", "sonstiges")


def score_lead(lead: dict) -> tuple[int, list[str]]:
    """Heuristic priority score, deliberately NOT a purchase probability."""
    score, reasons = 0, []
    industry = lead.get("industry", "Sonstige")
    b = {"Industrie & B2B-Technik": 25, "B2B-SaaS": 21, "Professionelle Dienstleistungen": 16, "Sonstige": 6}.get(industry, 0)
    score += b
    reasons.append(f"Branchen-Fit +{b}")
    size = int(lead.get("employees") or 0)
    b = 16 if 20 <= size <= 200 else (10 if 10 <= size < 20 or 200 < size <= 500 else (5 if size > 0 else 0))
    score += b
    reasons.append(f"Unternehmensgröße +{b}")
    signal = lead.get("signal_type", "kein_signal")
    b = SIGNALS.get(signal, (0, ""))[0]
    score += b
    reasons.append(f"Bedarfssignal +{b}")
    source_url = (lead.get("signal_source") or "").strip()
    if source_url.startswith(("https://", "http://")):
        score += 6
        reasons.append("Quellenbeleg +6")
    observed = lead.get("signal_date", "")
    if observed:
        try:
            age = (dt.date.today() - dt.date.fromisoformat(observed)).days
            if 0 <= age <= 30:
                score += 8
                reasons.append("Signal <=30 Tage +8")
            elif 30 < age <= 90:
                score += 4
                reasons.append("Signal <=90 Tage +4")
        except (TypeError, ValueError):
            pass
    budget = int(lead.get("estimated_budget") or 0)
    b = 12 if budget >= 5000 else (5 if budget >= 1000 else 0)
    score += b
    reasons.append(f"Budgethypothese +{b}")
    offer = lead.get("offer", "conversion")
    if (offer in ("portal", "automation") and signal == "prozessproblem") or (offer in ("conversion", "pilot") and signal in ("produktlaunch", "digitalprojekt")) or (offer == "brand" and signal == "produktlaunch"):
        score += 8
        reasons.append("Signal-Angebots-Passung +8")
    if lead.get("permission") == "nicht_kontaktieren" or lead.get("stage") == "gesperrt":
        return 0, ["Kontakt-/Widerspruchssperre – keine Akquise"]
    return min(100, score), reasons


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback and close when used via `with connect(...) as conn`."""
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


def connect(db_path: str | Path):
    conn = sqlite3.connect(str(db_path), timeout=8, check_same_thread=False, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      company TEXT NOT NULL, website TEXT DEFAULT '', location TEXT DEFAULT '',
      contact_name TEXT DEFAULT '', contact_role TEXT DEFAULT '', contact_route TEXT DEFAULT 'unbekannt',
      industry TEXT NOT NULL DEFAULT 'Sonstige', employees INTEGER DEFAULT 0,
      signal_type TEXT NOT NULL DEFAULT 'kein_signal', signal_date TEXT DEFAULT '',
      signal_source TEXT DEFAULT '', signal_note TEXT DEFAULT '',
      offer TEXT NOT NULL DEFAULT 'conversion', estimated_budget INTEGER DEFAULT 0,
      stage TEXT NOT NULL DEFAULT 'recherche', permission TEXT NOT NULL DEFAULT 'unbekannt',
      permission_evidence TEXT DEFAULT '', note TEXT DEFAULT '',
      next_step TEXT DEFAULT '', next_date TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS activities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      activity_type TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
      title TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '',
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS discovery (
      lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
      problem TEXT NOT NULL DEFAULT '', impact TEXT NOT NULL DEFAULT '',
      current_solution TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '',
      timing TEXT NOT NULL DEFAULT '', decision_process TEXT NOT NULL DEFAULT '',
      budget_status TEXT NOT NULL DEFAULT 'offen', budget_note TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS analysis_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      provider TEXT NOT NULL DEFAULT 'ollama', model TEXT NOT NULL DEFAULT 'qwen3:8b',
      status TEXT NOT NULL DEFAULT 'queued', summary TEXT DEFAULT '',
      pages_json TEXT DEFAULT '[]', warnings_json TEXT DEFAULT '[]', error TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      finished_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS findings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      category TEXT NOT NULL, observation TEXT NOT NULL, hypothesis TEXT NOT NULL,
      evidence TEXT NOT NULL, source_url TEXT NOT NULL,
      offer TEXT NOT NULL, question TEXT NOT NULL,
      review_status TEXT NOT NULL DEFAULT 'ungeprueft',
      reviewed_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS decision_contacts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      full_name TEXT NOT NULL, job_title TEXT DEFAULT '', decision_role TEXT DEFAULT 'unbekannt',
      source_url TEXT DEFAULT '', linkedin_url TEXT DEFAULT '', note TEXT DEFAULT '',
      lusha_id TEXT DEFAULT '', preview_json TEXT DEFAULT '{}',
      business_phone TEXT DEFAULT '', phone_type TEXT DEFAULT '', do_not_call INTEGER DEFAULT 0,
      data_provider TEXT DEFAULT 'manuell',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS contact_research_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'queued',
      pages_json TEXT DEFAULT '[]', channels_json TEXT DEFAULT '[]',warnings_json TEXT DEFAULT '[]',
      error TEXT DEFAULT '',created_at TEXT NOT NULL DEFAULT (datetime('now')),
      finished_at TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS contact_candidates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL REFERENCES contact_research_runs(id) ON DELETE CASCADE,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      full_name TEXT NOT NULL,job_title TEXT DEFAULT '',role_hint TEXT DEFAULT '',
      priority INTEGER DEFAULT 0,business_email TEXT DEFAULT '',business_phone TEXT DEFAULT '',
      phone_type TEXT DEFAULT '',source_url TEXT NOT NULL,evidence TEXT DEFAULT '',
      status TEXT DEFAULT 'ungeprueft'
    );
    CREATE TABLE IF NOT EXISTS quick_scans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      url TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'rules',model TEXT NOT NULL DEFAULT 'qwen3:8b',
      status TEXT NOT NULL DEFAULT 'queued',result_json TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT '',
      lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),finished_at TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_quick_scans_date ON quick_scans(id DESC);
    CREATE INDEX IF NOT EXISTS idx_contact_candidates_run ON contact_candidates(run_id);
    CREATE INDEX IF NOT EXISTS idx_decision_contacts_lead ON decision_contacts(lead_id);
    CREATE INDEX IF NOT EXISTS idx_analysis_lead ON analysis_runs(lead_id, id);
    CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);
    CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
    CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(done, due_date);
    """)
    # Non-destructive migration for existing v0.1 databases.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
    for col in ("location", "contact_role", "contact_route"):
        if col not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT DEFAULT 'unbekannt'" if col == "contact_route" else f"ALTER TABLE leads ADD COLUMN {col} TEXT DEFAULT ''")
    contact_columns = {r[1] for r in conn.execute("PRAGMA table_info(decision_contacts)")}
    for name, sql_type in (
        ('business_email', "TEXT DEFAULT ''"),
        ('verification_status', "TEXT DEFAULT 'ungeprueft'"),
        ('verification_date', "TEXT DEFAULT ''"),
        ('source_excerpt', "TEXT DEFAULT ''"),
    ):
        if name not in contact_columns:
            conn.execute(f"ALTER TABLE decision_contacts ADD COLUMN {name} {sql_type}")
    from .sales_workspace import init_workspace
    from .accounting import init_accounting
    from .einvoice import init_einvoice
    from .lead_finder import init_lead_finder
    from .company_data import init_company_data
    from .imprint_batch import init_imprint_batch
    from .website_scorer import init_website_scorer
    from .buying_signals import init_buying_signals
    from .sales_integration import init_sales_integration
    from .quality import init_quality
    from .auth import init_auth
    from .area import init_area
    from .sweep import init_sweep
    from .report import init_report
    init_workspace(conn)
    init_accounting(conn)
    init_einvoice(conn)
    init_lead_finder(conn)
    init_company_data(conn)
    init_imprint_batch(conn)
    init_website_scorer(conn)
    init_buying_signals(conn)
    init_sales_integration(conn)
    init_quality(conn)
    init_auth(conn)
    init_area(conn)
    from .research.jobs import init_jobs
    init_jobs(conn)  # v1.16: persistente Recherche-Aufträge
    init_sweep(conn)
    init_report(conn)
    from .duplicates import init_duplicates
    init_duplicates(conn)  # v1.17: „keine Dublette“-Entscheidungen
    from .workday import init_workday
    init_workday(conn)  # v1.18: bestätigter Bedarf, Tagesabschluss
    from .profiles import init_profiles
    init_profiles(conn)  # v1.18: Suchprofile mit Budget
    from .qualification import init_qualification
    init_qualification(conn)  # 2.0.0-dev2: Zeitfenster je Anrufversuch, Verlustgrund
    from .reach import init_reach
    init_reach(conn)  # 2.0.0-dev3: Eingang (verpasste Anrufe, Anfragen) mit Rückruffrist
    from .postcalc import init_postcalc
    init_postcalc(conn)  # 2.0.0-dev5: Nachkalkulation (Ist-Zeiten je Auftrag)
    conn.commit()


def discovery_summary(item: dict) -> dict:
    """Measures completeness, not deal value, truthfulness or purchase propensity."""
    fields = ("problem", "impact", "desired_outcome", "timing", "decision_process")
    answered = sum(bool(str(item.get(f) or "").strip()) for f in fields)
    return {"answered": answered, "total": len(fields),
            "missing": [f for f in fields if not str(item.get(f) or "").strip()]}


def as_lead(row):
    v = dict(row)
    v["score"], v["score_reasons"] = score_lead(v)
    return v


def stats(conn):
    today = dt.date.today().isoformat()
    rows = conn.execute("SELECT * FROM leads").fetchall()
    leads = [as_lead(x) for x in rows]
    counts = {s: sum(1 for l in leads if l["stage"] == s) for s in STAGES}
    task_due = conn.execute("SELECT COUNT(*) FROM tasks WHERE done = 0 AND due_date <= ? AND due_date != ''", (today,)).fetchone()[0]
    lead_due = conn.execute("""SELECT COUNT(*) FROM leads WHERE next_date != '' AND next_date <= ?
                AND next_step != '' AND stage NOT IN ('gewonnen', 'verloren', 'gesperrt')""", (today,)).fetchone()[0]
    due = task_due + lead_due
    open_value = sum(max(0, l["estimated_budget"]) for l in leads if l["stage"] in ("qualifiziert", "kontakt", "antwort", "termin", "angebot"))
    won_value = sum(max(0, l["estimated_budget"]) for l in leads if l["stage"] == "gewonnen")
    return {"total": len(leads), "by_stage": counts, "tasks_due": due,
            "open_value": open_value, "won_value": won_value,
            "priority_leads": sum(1 for l in leads if l["score"] >= 65 and l["stage"] not in ("gewonnen", "verloren", "gesperrt"))}
