# Datenzugriff – Inventar

Automatisch erzeugt mit `tools/sql_inventory.py` aus dem Quelltext (SDQ-010). Nicht von Hand ändern.

1474 SQL-Aufrufe in 71 Modulen: 1314 mit festem SQL-Text, 123 aus festen Teilen zusammengesetzt, 34 über eine Hilfsfunktion, 3 Hilfsfunktionen, die SQL nur weiterreichen, und 0 nicht statisch lesbar. 83 von 83 Tabellen der Hauptdatenbank werden im Quelltext namentlich angesprochen, dazu die Tabellen des Offline-Firmenkatalogs und des Mandantenverzeichnisses (je eigene Datei).

Einordnung der Tabellen (Organisation, Installation, Zugang; Personenbezug; Aufbewahrung): `sales_tool/data_map.py`. „nur lesen“ nennt Module, die eine Tabelle lesen, aber nicht schreiben.

## Tabellen

| Tabelle | Bereich | Bezug | Personen | Aufbewahrung | nur lesen | schreiben |
|---|---|---|---|---|---|---|
| `account_mfa` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | accounts.py |
| `account_recovery_codes` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | accounts.py |
| `account_sessions` | Mandantenverzeichnis (eigene Datei) | zugang | nein | kurz | – | accounts.py |
| `accounts` | Mandantenverzeichnis (eigene Datei) | zugang | ja | fachlich | einladungen.py | accounts.py |
| `action_dismissals` | Firmen und Kontakt | organisation | nein | kurz | – | sales_integration.py |
| `activities` | Firmen und Kontakt | organisation | nein | fachlich | – | briefing.py, care.py, chances.py, customer_report.py, duplicates.py, followups.py, handover.py, imprint_batch.py, kickoff.py, lead_finder.py, lead_imprint.py, offer_flow.py, report.py, research_center.py, revisions.py, server.py, sweep.py, website_scorer.py, workday.py |
| `analysis_runs` | Recherche | organisation | nein | kurz | ai_lab.py | analysis_jobs.py, quickscan.py, research/jobs.py, server.py |
| `app_settings` | Betrieb | organisation | nein | fachlich | focus.py, research/sources.py | quality.py |
| `audit_events` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | audit_trail.py |
| `audit_log` | Betrieb | organisation | nein | fachlich | – | accounting.py, company_data.py |
| `batch_items` | Firmenfindung | organisation | nein | kurz | lead_imprint.py, report.py, research_center.py | imprint_batch.py, quality.py |
| `batch_runs` | Firmenfindung | organisation | nein | kurz | research_center.py | imprint_batch.py |
| `briefing_answers` | Bedarf und Chancen | organisation | nein | fachlich | – | briefing.py |
| `buying_signals` | Recherche | organisation | nein | fachlich | qualification.py, quality.py, research_center.py, workday.py | buying_signals.py |
| `caldav_busy` | Firmen und Kontakt | organisation | nein | kurz | reach.py | caldav.py |
| `caldav_sync` | Firmen und Kontakt | organisation | nein | kurz | – | caldav.py |
| `calls` | Firmen und Kontakt | organisation | nein | fachlich | focus.py, qualification.py, server.py, today.py, workday.py | sales_workspace.py |
| `care_contracts` | Angebote und Projekte | organisation | nein | fachlich | – | care.py |
| `change_events` | Recherche | organisation | nein | fachlich | research_center.py | quality.py |
| `company_facts` | Recherche | organisation | nein | fachlich | research_center.py, workday.py | company_data.py, quality.py |
| `company_reports` | Recherche | organisation | nein | kurz | lead_imprint.py, research/homepage.py, research_center.py, today.py, workday.py | report.py |
| `company_settings` | Rechnung und Steuer | organisation | ja | gobd | company_data.py, lead_finder.py | accounting.py |
| `contact_candidates` | Firmen und Kontakt | organisation | ja | fachlich | research_center.py | public_contacts.py, quickscan.py, report.py |
| `contact_research_runs` | Firmen und Kontakt | organisation | nein | kurz | research_center.py | public_contacts.py, quickscan.py, report.py, research/jobs.py, server.py |
| `customer_reports` | Angebote und Projekte | organisation | nein | fachlich | – | customer_report.py |
| `day_closings` | Firmen und Kontakt | organisation | nein | fachlich | – | workday.py |
| `decision_contacts` | Firmen und Kontakt | organisation | ja | fachlich | messages.py, qualification.py, report.py, research_center.py | decision_finder.py, imprint_batch.py, public_contacts.py, quality.py, sales_integration.py, server.py |
| `directory_settings` | Mandantenverzeichnis (eigene Datei) | installation | nein | fachlich | – | accounts.py |
| `discovery` | Bedarf und Chancen | organisation | nein | fachlich | ai_lab.py, briefing.py, chances.py, qualification.py, research_center.py, sales_integration.py, today.py | server.py, workday.py |
| `discovery_candidates` | Firmenfindung | organisation | nein | kurz | company_data.py, lead_imprint.py, pilot.py, qualification.py, research/catalog.py, research/homepage.py, research_center.py, today.py, workday.py | lead_finder.py, quality.py, research/jobs.py, sweep.py |
| `discovery_dismissed` | Firmenfindung | organisation | nein | fachlich | – | sweep.py |
| `discovery_keys` | Firmenfindung | organisation | nein | kurz | research/catalog.py | quality.py, sweep.py |
| `discovery_not_same` | Firmenfindung | organisation | nein | fachlich | – | sweep.py |
| `discovery_runs` | Firmenfindung | organisation | nein | kurz | research/sources.py, research_center.py, today.py | lead_finder.py, sweep.py |
| `dunning_notices` | Rechnung und Steuer | organisation | nein | gobd | – | accounting.py |
| `einvoice_documents` | Rechnung und Steuer | organisation | nein | gobd | accounting.py | einvoice.py |
| `entities` | Firmenkatalog (eigene Datei) | installation | nein | kurz | – | research/catalog.py |
| `entities_fts` | Firmenkatalog (eigene Datei) | installation | nein | kurz | – | research/catalog.py |
| `expenses` | Rechnung und Steuer | organisation | nein | gobd | datev.py, einvoice.py | accounting.py |
| `expert_review_items` | Recherche | organisation | nein | fachlich | – | expert_review.py |
| `expert_reviews` | Recherche | organisation | ja | fachlich | – | expert_review.py |
| `findings` | Recherche | organisation | nein | fachlich | ai_lab.py, customer_report.py, offer_basis.py, research_center.py | analysis_jobs.py, quickscan.py, server.py |
| `geo_cache` | Firmenfindung | installation | nein | kurz | – | area.py |
| `handover_items` | Angebote und Projekte | organisation | nein | fachlich | – | handover.py |
| `handovers` | Angebote und Projekte | organisation | ja | fachlich | – | handover.py |
| `imports` | Firmenkatalog (eigene Datei) | installation | nein | kurz | – | research/catalog.py |
| `inbound` | Firmen und Kontakt | organisation | ja | fachlich | focus.py, today.py | reach.py |
| `invitations` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | einladungen.py |
| `invoice_lines` | Rechnung und Steuer | organisation | nein | gobd | – | accounting.py |
| `invoices` | Rechnung und Steuer | organisation | ja | gobd | accounting_api.py, backup_restore.py, care.py, datev.py, duplicates.py, quality.py, search.py, server.py, workday.py | accounting.py |
| `job_signals` | Recherche | organisation | nein | fachlich | – | buying_signals.py |
| `kickoff_items` | Angebote und Projekte | organisation | ja | fachlich | – | kickoff.py |
| `kickoffs` | Angebote und Projekte | organisation | nein | fachlich | – | kickoff.py |
| `lead_not_duplicate` | Firmen und Kontakt | organisation | nein | fachlich | – | duplicates.py |
| `leads` | Firmen und Kontakt | organisation | ja | fachlich | accounting.py, ai_lab.py, backup_restore.py, caldav.py, calendar_feed.py, care.py, customer_report.py, decision_finder.py, expert_review.py, focus.py, handover.py, imap_drafts.py, kickoff.py, messages.py, model.py, offer_print.py, postcalc.py, public_contacts.py, qualification.py, reach.py, research/jobs.py, sales_integration.py, search.py, studies.py, website_scorer.py | buying_signals.py, chances.py, company_data.py, duplicates.py, imprint_batch.py, lead_finder.py, lead_imprint.py, offer_flow.py, quality.py, quickscan.py, report.py, research_center.py, sales_workspace.py, server.py, sweep.py, today.py, workday.py |
| `login_failures` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | accounts.py |
| `mail_drafts` | Firmen und Kontakt | organisation | nein | fachlich | server.py, workday.py | imap_drafts.py, sales_workspace.py |
| `meetings` | Firmen und Kontakt | organisation | nein | fachlich | caldav.py, calendar_feed.py, focus.py, messages.py, reach.py, sales_integration.py, today.py, workday.py | chances.py, sales_workspace.py, server.py |
| `memberships` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | abrechnung.py, einladungen.py | accounts.py |
| `message_templates` | Firmen und Kontakt | organisation | nein | fachlich | – | messages.py |
| `number_sequences` | Rechnung und Steuer | organisation | nein | gobd | – | accounting.py |
| `offer_recommendations` | Bedarf und Chancen | organisation | nein | fachlich | – | sales_integration.py |
| `opportunities` | Bedarf und Chancen | organisation | nein | fachlich | care.py, search.py, today.py | briefing.py, chances.py, sales_workspace.py, server.py, workday.py |
| `organizations` | Mandantenverzeichnis (eigene Datei) | installation | nein | fachlich | accounts.py, einladungen.py, ops.py | tenancy.py |
| `osm_imports` | Firmenfindung | installation | nein | kurz | lead_finder.py | research/osm_local.py |
| `osm_places` | Firmenfindung | installation | nein | kurz | qualification.py | research/osm_local.py |
| `outbox` | Mandantenverzeichnis (eigene Datei) | installation | nein | fachlich | – | mailer.py |
| `payments` | Rechnung und Steuer | organisation | nein | gobd | datev.py | accounting.py |
| `pilot_items` | Firmenfindung | organisation | nein | fachlich | – | pilot.py |
| `pilot_samples` | Firmenfindung | organisation | nein | fachlich | – | pilot.py |
| `privacy_records` | Firmen und Kontakt | organisation | ja | fachlich | research_center.py, workday.py | company_data.py, quality.py |
| `project_closings` | Angebote und Projekte | organisation | nein | fachlich | – | postcalc.py |
| `proposals` | Angebote und Projekte | organisation | ja | fachlich | accounting.py, addenda.py, briefing.py, care.py, followups.py, handover.py, kickoff.py, learning.py, messages.py, offer_basis.py, offer_print.py, postcalc.py, qualification.py, reach.py, sales_integration.py, search.py, server.py, studies.py, today.py, workday.py | chances.py, offer_flow.py, revisions.py, sales_workspace.py |
| `quick_scans` | Recherche | organisation | nein | kurz | research_center.py | quickscan.py, report.py, research/jobs.py, server.py |
| `recurring_jobs` | Betrieb | organisation | nein | fachlich | – | quality.py |
| `register_events` | Recherche | organisation | nein | fachlich | qualification.py, quality.py | buying_signals.py |
| `research_jobs` | Betrieb | organisation | nein | kurz | – | research/jobs.py, sweep.py |
| `research_tasks` | Betrieb | organisation | nein | kurz | bg_jobs.py, buying_signals.py, lead_imprint.py, report.py, website_scorer.py | research/jobs.py, sweep.py |
| `score_versions` | Recherche | organisation | nein | fachlich | expert_review.py, research_center.py | website_scorer.py |
| `search_areas` | Firmenfindung | installation | nein | kurz | – | area.py |
| `search_profiles` | Firmenfindung | organisation | nein | fachlich | – | profiles.py |
| `sessions` | Anmeldung | zugang | nein | kurz | – | accounts.py, auth.py, multi_server.py, server.py, tenancy.py |
| `signal_correlations` | Recherche | organisation | nein | fachlich | report.py, research_center.py, sales_integration.py | buying_signals.py |
| `signal_scans` | Recherche | organisation | nein | kurz | quality.py, research_center.py | buying_signals.py, report.py, research/jobs.py |
| `signup_events` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | einladungen.py |
| `signup_requests` | Mandantenverzeichnis (eigene Datei) | zugang | nein | fachlich | – | einladungen.py |
| `studies` | Nutzerstudien | organisation | nein | fachlich | learning.py | studies.py |
| `study_results` | Nutzerstudien | organisation | nein | fachlich | – | studies.py |
| `study_sessions` | Nutzerstudien | organisation | nein | fachlich | – | studies.py |
| `study_tasks` | Nutzerstudien | organisation | nein | fachlich | – | studies.py |
| `subscriptions` | Mandantenverzeichnis (eigene Datei) | installation | nein | fachlich | – | abrechnung.py |
| `suppression_list` | Firmen und Kontakt | organisation | ja | fachlich | – | backup_restore.py, company_data.py |
| `sweeps` | Firmenfindung | organisation | nein | kurz | – | research/catalog.py, sweep.py |
| `tasks` | Firmen und Kontakt | organisation | nein | fachlich | messages.py, model.py, today.py | accounting.py, followups.py, handover.py, offer_flow.py, qualification.py, quality.py, research_center.py, revisions.py, sales_integration.py, sales_workspace.py, server.py, workday.py |
| `time_entries` | Angebote und Projekte | organisation | nein | fachlich | – | postcalc.py |
| `users` | Anmeldung | zugang | ja | fachlich | server.py | accounts.py, auth.py, multi_server.py, tenancy.py |
| `website_audits` | Recherche | organisation | nein | fachlich | buying_signals.py, customer_report.py, expert_review.py, quality.py, research_center.py, sales_integration.py | report.py, research/jobs.py, website_scorer.py |
| `website_findings` | Recherche | organisation | nein | fachlich | buying_signals.py, customer_report.py, expert_review.py, offer_basis.py, quality.py, research_center.py, sales_integration.py | website_scorer.py |
| `website_scores` | Recherche | organisation | nein | fachlich | buying_signals.py, qualification.py, quality.py, report.py, research_center.py, workday.py | website_scorer.py |
| `website_screenshots` | Recherche | organisation | nein | fachlich | report.py, research_center.py | website_scorer.py |

## Module

| Modul | Aufrufe | nicht lesbar | Tabellen |
|---|---:|---:|---:|
| `abrechnung.py` | 7 | 0 | 2 |
| `accounting.py` | 73 | 0 | 12 |
| `accounting_api.py` | 1 | 0 | 1 |
| `accounts.py` | 73 | 0 | 10 |
| `addenda.py` | 5 | 0 | 1 |
| `ai_lab.py` | 3 | 0 | 4 |
| `analysis_jobs.py` | 6 | 0 | 2 |
| `area.py` | 5 | 0 | 2 |
| `audit_trail.py` | 11 | 0 | 1 |
| `auth.py` | 28 | 0 | 2 |
| `backup_restore.py` | 12 | 0 | 3 |
| `bg_jobs.py` | 4 | 0 | 1 |
| `briefing.py` | 11 | 0 | 5 |
| `buying_signals.py` | 43 | 0 | 10 |
| `caldav.py` | 11 | 0 | 4 |
| `calendar_feed.py` | 1 | 0 | 2 |
| `care.py` | 12 | 0 | 6 |
| `chances.py` | 33 | 0 | 6 |
| `company_data.py` | 36 | 0 | 7 |
| `customer_report.py` | 8 | 0 | 6 |
| `data_map.py` | 2 | 0 | 0 |
| `datev.py` | 3 | 0 | 3 |
| `decision_finder.py` | 2 | 0 | 2 |
| `duplicates.py` | 22 | 0 | 4 |
| `einladungen.py` | 16 | 0 | 6 |
| `einvoice.py` | 8 | 0 | 2 |
| `expert_review.py` | 17 | 0 | 6 |
| `focus.py` | 8 | 0 | 5 |
| `followups.py` | 11 | 0 | 3 |
| `handover.py` | 23 | 0 | 6 |
| `imap_drafts.py` | 6 | 0 | 2 |
| `imprint_batch.py` | 47 | 0 | 5 |
| `kickoff.py` | 16 | 0 | 5 |
| `lead_finder.py` | 25 | 0 | 6 |
| `lead_imprint.py` | 14 | 0 | 6 |
| `learning.py` | 5 | 0 | 2 |
| `mailer.py` | 3 | 0 | 1 |
| `messages.py` | 19 | 0 | 7 |
| `model.py` | 10 | 0 | 10 |
| `multi_server.py` | 2 | 0 | 2 |
| `offer_basis.py` | 3 | 0 | 3 |
| `offer_flow.py` | 23 | 0 | 4 |
| `offer_print.py` | 3 | 0 | 2 |
| `ops.py` | 11 | 0 | 1 |
| `pilot.py` | 14 | 0 | 3 |
| `postcalc.py` | 16 | 0 | 4 |
| `profiles.py` | 12 | 0 | 1 |
| `public_contacts.py` | 11 | 0 | 4 |
| `qualification.py` | 25 | 0 | 11 |
| `quality.py` | 58 | 0 | 18 |
| `quickscan.py` | 12 | 0 | 6 |
| `reach.py` | 15 | 0 | 5 |
| `report.py` | 55 | 0 | 14 |
| `research/benchmark.py` | 2 | 0 | 0 |
| `research/catalog.py` | 22 | 0 | 6 |
| `research/homepage.py` | 2 | 0 | 2 |
| `research/jobs.py` | 47 | 0 | 9 |
| `research/osm_local.py` | 21 | 0 | 2 |
| `research/sources.py` | 2 | 0 | 2 |
| `research_center.py` | 51 | 0 | 25 |
| `revisions.py` | 7 | 0 | 3 |
| `sales_integration.py` | 42 | 0 | 11 |
| `sales_workspace.py` | 19 | 0 | 7 |
| `search.py` | 4 | 0 | 4 |
| `server.py` | 62 | 0 | 17 |
| `studies.py` | 26 | 0 | 6 |
| `sweep.py` | 126 | 0 | 10 |
| `tenancy.py` | 11 | 0 | 3 |
| `today.py` | 26 | 0 | 11 |
| `website_scorer.py` | 38 | 0 | 8 |
| `workday.py` | 66 | 0 | 17 |
