-- SignalDesk-Altdatenbank (fiktive Daten), PRAGMA user_version = 0
BEGIN TRANSACTION;
CREATE TABLE activities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      activity_type TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
INSERT INTO "activities" VALUES(1,1,'notiz','Erstes Gespräch vorbereitet','2026-11-05 01:04:28');
CREATE TABLE analysis_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      provider TEXT NOT NULL DEFAULT 'ollama', model TEXT NOT NULL DEFAULT 'qwen3:8b',
      status TEXT NOT NULL DEFAULT 'queued', summary TEXT DEFAULT '',
      pages_json TEXT DEFAULT '[]', warnings_json TEXT DEFAULT '[]', error TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      finished_at TEXT DEFAULT ''
    );
CREATE TABLE calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        outcome TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
        legal_note TEXT NOT NULL DEFAULT '', callback_date TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE contact_candidates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL REFERENCES contact_research_runs(id) ON DELETE CASCADE,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      full_name TEXT NOT NULL,job_title TEXT DEFAULT '',role_hint TEXT DEFAULT '',
      priority INTEGER DEFAULT 0,business_email TEXT DEFAULT '',business_phone TEXT DEFAULT '',
      phone_type TEXT DEFAULT '',source_url TEXT NOT NULL,evidence TEXT DEFAULT '',
      status TEXT DEFAULT 'ungeprueft'
    );
CREATE TABLE contact_research_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'queued',
      pages_json TEXT DEFAULT '[]', channels_json TEXT DEFAULT '[]',warnings_json TEXT DEFAULT '[]',
      error TEXT DEFAULT '',created_at TEXT NOT NULL DEFAULT (datetime('now')),
      finished_at TEXT DEFAULT ''
    );
CREATE TABLE decision_contacts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      full_name TEXT NOT NULL, job_title TEXT DEFAULT '', decision_role TEXT DEFAULT 'unbekannt',
      source_url TEXT DEFAULT '', linkedin_url TEXT DEFAULT '', note TEXT DEFAULT '',
      lusha_id TEXT DEFAULT '', preview_json TEXT DEFAULT '{}',
      business_phone TEXT DEFAULT '', phone_type TEXT DEFAULT '', do_not_call INTEGER DEFAULT 0,
      data_provider TEXT DEFAULT 'manuell',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    , business_email TEXT DEFAULT '', verification_status TEXT DEFAULT 'ungeprueft', verification_date TEXT DEFAULT '', source_excerpt TEXT DEFAULT '');
INSERT INTO "decision_contacts" VALUES(1,1,'Erika Altdaten','Leitung Marketing','unbekannt','https://altbestand-maschinenbau.example/team','','','','{}','','',0,'manuell','2026-11-05 01:04:28','2026-11-05 01:04:28','','ungeprueft','','');
CREATE TABLE discovery (
      lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
      problem TEXT NOT NULL DEFAULT '', impact TEXT NOT NULL DEFAULT '',
      current_solution TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '',
      timing TEXT NOT NULL DEFAULT '', decision_process TEXT NOT NULL DEFAULT '',
      budget_status TEXT NOT NULL DEFAULT 'offen', budget_note TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
INSERT INTO "discovery" VALUES(1,'Anfragen kommen nur telefonisch','','','Mehr qualifizierte Online-Anfragen','Q3','','offen','','2026-11-05 01:04:28');
CREATE TABLE findings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      category TEXT NOT NULL, observation TEXT NOT NULL, hypothesis TEXT NOT NULL,
      evidence TEXT NOT NULL, source_url TEXT NOT NULL,
      offer TEXT NOT NULL, question TEXT NOT NULL,
      review_status TEXT NOT NULL DEFAULT 'ungeprueft',
      reviewed_at TEXT DEFAULT ''
    );
CREATE TABLE leads (
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
INSERT INTO "leads" VALUES(1,'Altbestand Maschinenbau GmbH','https://altbestand-maschinenbau.example','Stuttgart','','','unbekannt','Industrie & B2B-Technik',120,'produktlaunch','2026-03-01','https://altbestand-maschinenbau.example/news','','conversion',8500,'qualifiziert','opt_in','Opt-in per Formular am 01.03.2026','Altdaten-Notiz äöü ß','','','2026-11-05 01:04:28','2026-11-05 01:04:28');
INSERT INTO "leads" VALUES(2,'Gesperrt Beispiel AG','https://gesperrt.example','','','','unbekannt','Sonstige',0,'kein_signal','','','','conversion',0,'gesperrt','nicht_kontaktieren','','','','','2026-11-05 01:04:28','2026-11-05 01:04:28');
CREATE TABLE mail_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        draft_type TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
        contact_basis TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        title TEXT NOT NULL, starts_at TEXT NOT NULL, duration_min INTEGER NOT NULL DEFAULT 30,
        location TEXT DEFAULT '', status TEXT DEFAULT 'geplant', notes TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'entwurf', internal_json TEXT NOT NULL,
        customer_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE quick_scans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      url TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'rules',model TEXT NOT NULL DEFAULT 'qwen3:8b',
      status TEXT NOT NULL DEFAULT 'queued',result_json TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT '',
      lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),finished_at TEXT DEFAULT ''
    );
CREATE TABLE tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
      title TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '',
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
INSERT INTO "tasks" VALUES(1,1,'Rückruf vereinbart','2026-03-10',0,'2026-11-05 01:04:28');
CREATE INDEX idx_quick_scans_date ON quick_scans(id DESC);
CREATE INDEX idx_contact_candidates_run ON contact_candidates(run_id);
CREATE INDEX idx_decision_contacts_lead ON decision_contacts(lead_id);
CREATE INDEX idx_analysis_lead ON analysis_runs(lead_id, id);
CREATE INDEX idx_findings_run ON findings(run_id);
CREATE INDEX idx_leads_stage ON leads(stage);
CREATE INDEX idx_tasks_due ON tasks(done, due_date);
CREATE INDEX idx_calls_lead ON calls(lead_id);
CREATE INDEX idx_meetings_time ON meetings(starts_at);
CREATE INDEX idx_proposals_lead ON proposals(lead_id);
CREATE INDEX idx_mail_lead ON mail_drafts(lead_id);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('leads',2);
INSERT INTO "sqlite_sequence" VALUES('activities',1);
INSERT INTO "sqlite_sequence" VALUES('tasks',1);
INSERT INTO "sqlite_sequence" VALUES('decision_contacts',1);
COMMIT;
