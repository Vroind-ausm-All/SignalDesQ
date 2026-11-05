-- SignalDesk-Altdatenbank (fiktive Daten), PRAGMA user_version = 15
BEGIN TRANSACTION;
CREATE TABLE activities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      activity_type TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
INSERT INTO "activities" VALUES(1,1,'notiz','Erstes Gespräch vorbereitet','2026-11-05 01:04:29');
CREATE TABLE analysis_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
      provider TEXT NOT NULL DEFAULT 'ollama', model TEXT NOT NULL DEFAULT 'qwen3:8b',
      status TEXT NOT NULL DEFAULT 'queued', summary TEXT DEFAULT '',
      pages_json TEXT DEFAULT '[]', warnings_json TEXT DEFAULT '[]', error TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      finished_at TEXT DEFAULT ''
    );
CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now')), entity TEXT NOT NULL, entity_id INTEGER,
        action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
      );
INSERT INTO "audit_log" VALUES(1,'2026-11-05 01:04:29','settings',1,'geaendert','bank_name, bic, city, company_name, email, iban, owner_name, phone, street, tax_number, vat_id, zip');
INSERT INTO "audit_log" VALUES(2,'2026-11-05 01:04:29','invoice',1,'entwurf_angelegt','7.021,00 EUR brutto');
INSERT INTO "audit_log" VALUES(3,'2026-11-05 01:04:29','invoice',1,'festgeschrieben','RE-2026-0001 · 7.021,00 EUR brutto');
CREATE TABLE batch_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES batch_runs(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, input TEXT NOT NULL, domain TEXT NOT NULL, company_hint TEXT NOT NULL DEFAULT '',
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'pending', error TEXT NOT NULL DEFAULT '', log_json TEXT NOT NULL DEFAULT '[]',
        result_json TEXT NOT NULL DEFAULT '', duplicate_lead_id INTEGER, duplicate_reason TEXT NOT NULL DEFAULT '',
        review_status TEXT NOT NULL DEFAULT 'offen', started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT ''
      );
CREATE TABLE batch_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'impressum',
        status TEXT NOT NULL DEFAULT 'running', label TEXT NOT NULL DEFAULT '', options_json TEXT NOT NULL DEFAULT '{}',
        total INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
CREATE TABLE buying_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE, company TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
        polarity TEXT NOT NULL DEFAULT 'pro', areas_json TEXT NOT NULL DEFAULT '[]', offers_json TEXT NOT NULL DEFAULT '[]',
        evidence TEXT NOT NULL DEFAULT '', pro_json TEXT NOT NULL DEFAULT '[]', contra_json TEXT NOT NULL DEFAULT '[]',
        questions_json TEXT NOT NULL DEFAULT '[]', uncertainties_json TEXT NOT NULL DEFAULT '[]',
        sources_json TEXT NOT NULL DEFAULT '[]', published_at TEXT NOT NULL DEFAULT '', found_at TEXT NOT NULL DEFAULT (date('now')),
        status TEXT NOT NULL DEFAULT 'ungeprueft', is_new INTEGER NOT NULL DEFAULT 1, suppressed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        outcome TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
        legal_note TEXT NOT NULL DEFAULT '', callback_date TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE company_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        field TEXT NOT NULL, value TEXT NOT NULL,
        source_type TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', excerpt TEXT NOT NULL DEFAULT '',
        method TEXT NOT NULL DEFAULT '', quality TEXT NOT NULL DEFAULT 'mittel',
        found_at TEXT NOT NULL DEFAULT (datetime('now')), published_at TEXT NOT NULL DEFAULT '',
        checked_at TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'ungeprueft',
        batch_item_id INTEGER
      );
CREATE TABLE company_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        company_name TEXT NOT NULL DEFAULT '', owner_name TEXT NOT NULL DEFAULT '',
        street TEXT NOT NULL DEFAULT '', zip TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT 'DE', tax_number TEXT NOT NULL DEFAULT '', vat_id TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
        iban TEXT NOT NULL DEFAULT '', bic TEXT NOT NULL DEFAULT '', bank_name TEXT NOT NULL DEFAULT '',
        small_business INTEGER NOT NULL DEFAULT 0, tax_basis TEXT NOT NULL DEFAULT 'ist',
        payment_days INTEGER NOT NULL DEFAULT 14, invoice_prefix TEXT NOT NULL DEFAULT 'RE',
        base_rate_pct TEXT NOT NULL DEFAULT '1.27', footer_note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
INSERT INTO "company_settings" VALUES(1,'Pixel & Prozess Studio','Alex Muster','Hafenstraße 1','20457','Hamburg','DE','22/123/45678','DE123456789','rechnung@pixel-prozess.example','+49 40 123456','','DE89370400440532013000','COBADEFFXXX','Commerzbank',0,'ist',14,'RE','1.27','','2026-11-05 01:04:29');
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
INSERT INTO "decision_contacts" VALUES(1,1,'Erika Altdaten','Leitung Marketing','unbekannt','https://altbestand-maschinenbau.example/team','','','','{}','','',0,'manuell','2026-11-05 01:04:29','2026-11-05 01:04:29','','ungeprueft','','');
CREATE TABLE discovery (
      lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
      problem TEXT NOT NULL DEFAULT '', impact TEXT NOT NULL DEFAULT '',
      current_solution TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '',
      timing TEXT NOT NULL DEFAULT '', decision_process TEXT NOT NULL DEFAULT '',
      budget_status TEXT NOT NULL DEFAULT 'offen', budget_note TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
INSERT INTO "discovery" VALUES(1,'Anfragen kommen nur telefonisch','','','Mehr qualifizierte Online-Anfragen','Q3','','offen','','2026-11-05 01:04:29');
CREATE TABLE discovery_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
        source TEXT NOT NULL, external_id TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL, website TEXT NOT NULL DEFAULT '', street TEXT NOT NULL DEFAULT '',
        zip TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT 'DE',
        industry TEXT NOT NULL DEFAULT '', employees INTEGER NOT NULL DEFAULT 0, legal_form TEXT NOT NULL DEFAULT '',
        register_id TEXT NOT NULL DEFAULT '', signal_type TEXT NOT NULL DEFAULT 'kein_signal',
        signal_note TEXT NOT NULL DEFAULT '', signal_date TEXT NOT NULL DEFAULT '',
        source_url TEXT NOT NULL DEFAULT '', license TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'neu', duplicate_lead_id INTEGER, lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE discovery_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL, params_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running',
        result_count INTEGER NOT NULL DEFAULT 0, filtered_count INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
CREATE TABLE dunning_notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        level INTEGER NOT NULL, created_on TEXT NOT NULL, new_due_date TEXT NOT NULL,
        outstanding_cents INTEGER NOT NULL, interest_cents INTEGER NOT NULL DEFAULT 0,
        fee_cents INTEGER NOT NULL DEFAULT 0, text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE einvoice_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, format TEXT NOT NULL DEFAULT '',
        number TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL DEFAULT '', xml BLOB NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_date TEXT NOT NULL, paid_on TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'sonstiges',
        net_cents INTEGER NOT NULL, vat_rate INTEGER NOT NULL DEFAULT 19, vat_cents INTEGER NOT NULL DEFAULT 0,
        gross_cents INTEGER NOT NULL, reverse_charge INTEGER NOT NULL DEFAULT 0,
        receipt_ref TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'aktiv', source TEXT NOT NULL DEFAULT 'manuell',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      , document_id INTEGER REFERENCES einvoice_documents(id));
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
CREATE TABLE invoice_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, description TEXT NOT NULL, quantity TEXT NOT NULL DEFAULT '1',
        unit TEXT NOT NULL DEFAULT 'pauschal', unit_price_cents INTEGER NOT NULL,
        vat_rate INTEGER NOT NULL DEFAULT 19, net_cents INTEGER NOT NULL
      );
INSERT INTO "invoice_lines" VALUES(1,1,1,'Conversion-Sprint','1','pauschal',590000,19,590000);
CREATE TABLE invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT UNIQUE, kind TEXT NOT NULL DEFAULT 'rechnung', status TEXT NOT NULL DEFAULT 'entwurf',
        lead_id INTEGER REFERENCES leads(id), proposal_id INTEGER REFERENCES proposals(id),
        corrects_invoice_id INTEGER REFERENCES invoices(id),
        tax_mode TEXT NOT NULL DEFAULT 'regel',
        issue_date TEXT NOT NULL DEFAULT '', service_from TEXT NOT NULL DEFAULT '', service_to TEXT NOT NULL DEFAULT '',
        payment_days INTEGER NOT NULL DEFAULT 14, due_date TEXT NOT NULL DEFAULT '',
        buyer_name TEXT NOT NULL DEFAULT '', buyer_contact TEXT NOT NULL DEFAULT '',
        buyer_street TEXT NOT NULL DEFAULT '', buyer_zip TEXT NOT NULL DEFAULT '', buyer_city TEXT NOT NULL DEFAULT '',
        buyer_country TEXT NOT NULL DEFAULT 'DE', buyer_vat_id TEXT NOT NULL DEFAULT '',
        buyer_reference TEXT NOT NULL DEFAULT '', buyer_email TEXT NOT NULL DEFAULT '',
        intro_text TEXT NOT NULL DEFAULT '', closing_text TEXT NOT NULL DEFAULT '',
        net_cents INTEGER NOT NULL DEFAULT 0, vat_cents INTEGER NOT NULL DEFAULT 0, gross_cents INTEGER NOT NULL DEFAULT 0,
        seller_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), finalized_at TEXT NOT NULL DEFAULT '',
        cancelled_at TEXT NOT NULL DEFAULT ''
      );
INSERT INTO "invoices" VALUES(1,'RE-2026-0001','rechnung','offen',1,NULL,NULL,'regel','2026-11-05','2026-03-15','',14,'2026-11-19','Altbestand Maschinenbau GmbH','','Werkstraße 5','70173','Stuttgart','DE','','','buchhaltung@altbestand.example','','',590000,112100,702100,'{"company_name": "Pixel & Prozess Studio", "owner_name": "Alex Muster", "street": "Hafenstraße 1", "zip": "20457", "city": "Hamburg", "country": "DE", "tax_number": "22/123/45678", "vat_id": "DE123456789", "email": "rechnung@pixel-prozess.example", "phone": "+49 40 123456", "website": "", "iban": "DE89370400440532013000", "bic": "COBADEFFXXX", "bank_name": "Commerzbank", "invoice_prefix": "RE", "footer_note": "", "small_business": false}','2026-11-05 01:04:29','2026-11-05 01:04:29','');
CREATE TABLE job_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL, company TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL,
        published_at TEXT NOT NULL DEFAULT '', valid_through TEXT NOT NULL DEFAULT '', excerpt TEXT NOT NULL DEFAULT '',
        first_seen_at TEXT NOT NULL DEFAULT (datetime('now')), last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    , legal_name TEXT DEFAULT '', legal_form TEXT DEFAULT '', street TEXT DEFAULT '', zip TEXT DEFAULT '', city TEXT DEFAULT '', register_court TEXT DEFAULT '', register_number TEXT DEFAULT '', vat_id TEXT DEFAULT '', business_phone TEXT DEFAULT '', business_email TEXT DEFAULT '', imprint_url TEXT DEFAULT '', imprint_checked_at TEXT DEFAULT '');
INSERT INTO "leads" VALUES(1,'Altbestand Maschinenbau GmbH','https://altbestand-maschinenbau.example','Stuttgart','','','unbekannt','Industrie & B2B-Technik',120,'produktlaunch','2026-03-01','https://altbestand-maschinenbau.example/news','','conversion',8500,'qualifiziert','opt_in','Opt-in per Formular am 01.03.2026','Altdaten-Notiz äöü ß','','','2026-11-05 01:04:29','2026-11-05 01:04:29','','','','','','','','','','','','');
INSERT INTO "leads" VALUES(2,'Gesperrt Beispiel AG','https://gesperrt.example','','','','unbekannt','Sonstige',0,'kein_signal','','','','conversion',0,'gesperrt','nicht_kontaktieren','','','','','2026-11-05 01:04:29','2026-11-05 01:04:29','','','','','','','','','','','','');
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
CREATE TABLE number_sequences (
        prefix TEXT NOT NULL, year INTEGER NOT NULL, last INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (prefix, year)
      );
INSERT INTO "number_sequences" VALUES('RE',2026,1);
CREATE TABLE payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        paid_on TEXT NOT NULL, amount_cents INTEGER NOT NULL, method TEXT NOT NULL DEFAULT 'ueberweisung',
        note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE privacy_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
        contact_id INTEGER REFERENCES decision_contacts(id) ON DELETE CASCADE,
        subject TEXT NOT NULL, data_categories TEXT NOT NULL,
        purpose TEXT NOT NULL, legal_basis TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '',
        collected_at TEXT NOT NULL DEFAULT (datetime('now')), retention_until TEXT NOT NULL,
        art14_informed_at TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT ''
      );
CREATE TABLE proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'entwurf', internal_json TEXT NOT NULL,
        customer_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      , number TEXT DEFAULT '', valid_until TEXT DEFAULT '');
CREATE TABLE quick_scans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      url TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'rules',model TEXT NOT NULL DEFAULT 'qwen3:8b',
      status TEXT NOT NULL DEFAULT 'queued',result_json TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT '',
      lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),finished_at TEXT DEFAULT ''
    );
CREATE TABLE register_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE,
        lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        company TEXT NOT NULL DEFAULT '', register_court TEXT NOT NULL DEFAULT '', register_number TEXT NOT NULL DEFAULT '',
        event_type TEXT NOT NULL, published_at TEXT NOT NULL DEFAULT '', text TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manuell',
        source_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE score_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT NOT NULL UNIQUE, config_json TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
INSERT INTO "score_versions" VALUES(1,'2ad0039bf900','{"area_weights": {"design": 1, "process": 1, "web": 1}, "min_area_coverage_pct": 50, "min_coverage_pct": 60, "overall_weights": {"fit": 35, "potential": 35, "signal": 30}, "rubrics": {"A1_mobile_overflow": {"area": "design", "enabled": true, "weight": 3}, "A2_small_text": {"area": "design", "enabled": true, "weight": 2}, "A3_heading_hierarchy": {"area": "design", "enabled": true, "weight": 2}, "A4_alt_texts": {"area": "design", "enabled": true, "weight": 1}, "A5_tap_targets": {"area": "design", "enabled": true, "weight": 2}, "A6_font_consistency": {"area": "design", "enabled": true, "weight": 1}, "A7_freshness": {"area": "design", "enabled": true, "weight": 1}, "B1_load_time": {"area": "web", "enabled": true, "weight": 3}, "B2_page_weight": {"area": "web", "enabled": true, "weight": 1}, "B3_cta_above_fold": {"area": "web", "enabled": true, "weight": 3}, "B4_contact_options": {"area": "web", "enabled": true, "weight": 2}, "B5_form_effort": {"area": "web", "enabled": true, "weight": 2}, "B6_broken_links": {"area": "web", "enabled": true, "weight": 2}, "B7_navigation": {"area": "web", "enabled": true, "weight": 1}, "B8_service_pages": {"area": "web", "enabled": true, "weight": 2}, "B9_technical": {"area": "web", "enabled": true, "weight": 1}, "C1_pdf_workflows": {"area": "process", "enabled": true, "weight": 3}, "C2_manual_requests": {"area": "process", "enabled": true, "weight": 2}, "C3_self_service": {"area": "process", "enabled": true, "weight": 2}, "C4_complex_forms": {"area": "process", "enabled": true, "weight": 2}, "C5_recurring_data_entry": {"area": "process", "enabled": true, "weight": 2}}, "thresholds": {"console_errors_warn": 3, "copyright_years_old": 2, "font_families_max": 4, "form_fields_warn": 8, "images_no_alt_pct": 30, "load_ms_warn": 4000, "nav_items_max": 15, "page_mb_warn": 5, "small_tap_targets": 6, "small_text_share_pct": 10}}',1,'2026-11-05 01:04:29');
CREATE TABLE signal_correlations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        theme TEXT NOT NULL, hypothesis TEXT NOT NULL, strength TEXT NOT NULL, score INTEGER NOT NULL,
        signal_ids_json TEXT NOT NULL, counter_json TEXT NOT NULL, contradictions_json TEXT NOT NULL,
        missing_json TEXT NOT NULL, questions_json TEXT NOT NULL, offers_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE signal_scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'queued', error TEXT NOT NULL DEFAULT '', found INTEGER NOT NULL DEFAULT 0,
        log_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT NOT NULL DEFAULT ''
      );
CREATE TABLE suppression_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, value TEXT NOT NULL, display TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '', lead_id INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(kind, value)
      );
CREATE TABLE tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
      title TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '',
      done INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
INSERT INTO "tasks" VALUES(1,1,'Rückruf vereinbart','2026-03-10',0,'2026-11-05 01:04:29');
CREATE TABLE website_audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', error TEXT NOT NULL DEFAULT '',
        renderer TEXT NOT NULL DEFAULT '', version_id INTEGER REFERENCES score_versions(id),
        capture_json TEXT NOT NULL DEFAULT '{}', summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT ''
      );
CREATE TABLE website_findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL REFERENCES website_audits(id) ON DELETE CASCADE,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        rubric TEXT NOT NULL, area TEXT NOT NULL, label TEXT NOT NULL, result TEXT NOT NULL, weight REAL NOT NULL,
        evidence TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', screenshot_id INTEGER,
        method TEXT NOT NULL, certainty TEXT NOT NULL, offer TEXT, question TEXT NOT NULL DEFAULT '',
        review_status TEXT NOT NULL DEFAULT 'ungeprueft'
      );
CREATE TABLE website_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL UNIQUE REFERENCES website_audits(id) ON DELETE CASCADE,
        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        version_id INTEGER NOT NULL REFERENCES score_versions(id),
        design INTEGER, web INTEGER, process INTEGER, potential INTEGER, fit INTEGER, signal INTEGER,
        coverage INTEGER NOT NULL, overall INTEGER, basis_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
CREATE TABLE website_screenshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id INTEGER NOT NULL REFERENCES website_audits(id) ON DELETE CASCADE,
        page_url TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, size_bytes INTEGER NOT NULL
      );
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
CREATE INDEX idx_invoices_status ON invoices(status, due_date);
CREATE INDEX idx_invoices_lead ON invoices(lead_id);
CREATE INDEX idx_invoice_lines_inv ON invoice_lines(invoice_id, position);
CREATE INDEX idx_payments_inv ON payments(invoice_id);
CREATE INDEX idx_payments_date ON payments(paid_on);
CREATE INDEX idx_expenses_date ON expenses(expense_date);
CREATE TRIGGER trg_invoice_immutable
      BEFORE UPDATE OF number, kind, lead_id, proposal_id, corrects_invoice_id, tax_mode, issue_date,
        service_from, service_to, payment_days, due_date, buyer_name, buyer_contact, buyer_street, buyer_zip,
        buyer_city, buyer_country, buyer_vat_id, buyer_reference, buyer_email, intro_text, closing_text,
        net_cents, vat_cents, gross_cents, seller_json, finalized_at ON invoices
      WHEN OLD.status <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Festgeschriebene Rechnung ist unveränderbar – Korrektur nur per Storno.'); END;
CREATE TRIGGER trg_invoice_no_delete
      BEFORE DELETE ON invoices WHEN OLD.status <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Festgeschriebene Rechnung darf nicht gelöscht werden.'); END;
CREATE TRIGGER trg_lines_insert_locked
      BEFORE INSERT ON invoice_lines
      WHEN (SELECT status FROM invoices WHERE id = NEW.invoice_id) <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Positionen festgeschriebener Rechnungen sind gesperrt.'); END;
CREATE TRIGGER trg_lines_update_locked
      BEFORE UPDATE ON invoice_lines
      WHEN (SELECT status FROM invoices WHERE id = OLD.invoice_id) <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Positionen festgeschriebener Rechnungen sind gesperrt.'); END;
CREATE TRIGGER trg_lines_delete_locked
      BEFORE DELETE ON invoice_lines
      WHEN (SELECT status FROM invoices WHERE id = OLD.invoice_id) <> 'entwurf'
      BEGIN SELECT RAISE(ABORT, 'Positionen festgeschriebener Rechnungen sind gesperrt.'); END;
CREATE TRIGGER trg_audit_no_update
      BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'Protokoll ist unveränderbar.'); END;
CREATE TRIGGER trg_audit_no_delete
      BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'Protokoll ist unveränderbar.'); END;
CREATE TRIGGER trg_einvoice_doc_immutable
      BEFORE UPDATE ON einvoice_documents BEGIN SELECT RAISE(ABORT, 'Archivierte E-Rechnung ist unveränderbar.'); END;
CREATE TRIGGER trg_einvoice_doc_no_delete
      BEFORE DELETE ON einvoice_documents BEGIN SELECT RAISE(ABORT, 'Archivierte E-Rechnung darf nicht gelöscht werden.'); END;
CREATE INDEX idx_discovery_cand_run ON discovery_candidates(run_id);
CREATE INDEX idx_discovery_runs_source ON discovery_runs(source, created_at);
CREATE INDEX idx_company_facts_lead ON company_facts(lead_id, field);
CREATE INDEX idx_leads_register ON leads(register_number);
CREATE INDEX idx_batch_items_run ON batch_items(run_id, status);
CREATE INDEX idx_website_audits_lead ON website_audits(lead_id, id);
CREATE INDEX idx_website_scores_lead ON website_scores(lead_id, id);
CREATE INDEX idx_buying_signals_lead ON buying_signals(lead_id, published_at);
CREATE INDEX idx_signal_corr_lead ON signal_correlations(lead_id);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('score_versions',1);
INSERT INTO "sqlite_sequence" VALUES('leads',2);
INSERT INTO "sqlite_sequence" VALUES('activities',1);
INSERT INTO "sqlite_sequence" VALUES('tasks',1);
INSERT INTO "sqlite_sequence" VALUES('decision_contacts',1);
INSERT INTO "sqlite_sequence" VALUES('audit_log',3);
INSERT INTO "sqlite_sequence" VALUES('invoices',1);
INSERT INTO "sqlite_sequence" VALUES('invoice_lines',1);
COMMIT;
