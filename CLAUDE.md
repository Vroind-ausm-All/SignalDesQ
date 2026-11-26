# SignalDesQ – verbindliche Regeln für die Arbeit mit Claude Code

SignalDesk ist ein lokaler B2B-Recherche- und Vertriebsarbeitsplatz mit optionalem Server für mehrere Organisationen.
Weiterentwicklung nach dem Open-Intelligence-Plan R0–R7: [`docs/MASTERPLAN_OPEN_INTELLIGENCE.md`](docs/MASTERPLAN_OPEN_INTELLIGENCE.md).
Sprache in Code-Kommentaren, Oberfläche, Doku und Antworten: Deutsch.

Diese Datei ist **keine Sicherheitsgrenze**. Jede Regel unten wird im Programm durchgesetzt; die Verweise nennen die Stelle und den
Test, der rot wird, wenn die Regel fehlt. `tests/test_claude_rules.py` prüft, dass es alle genannten Stellen und Tests gibt.

## Unverhandelbare Regeln

1. **Kontaktsperre gilt überall.** Jeder Weg, der Gespräch, Termin, Entwurf, Angebot oder Kontaktvorschlag anlegt, ruft die Sperrprüfung auf.
   Durchgesetzt: `sales_tool/workday.py::assert_contact_allowed`, `sales_tool/workday.py::contact_lock`.
   Test: `tests/test_sprintS5_workday.py::LockTests::test_suppression_blocks_every_contact_path`.
2. **Keine Sperre geht verloren** – nicht durch Import, Zusammenführung, wartende Aufträge, Export oder Wiederherstellung.
   Durchgesetzt: `sales_tool/company_data.py::check_suppressed`, `sales_tool/research/jobs.py::blocked_reason`,
   `sales_tool/backup_restore.py::keep_suppressions`.
   Tests: `tests/test_gate_isolation.py::RestoreGateTests::test_restore_keeps_later_suppressions`,
   `tests/test_gate_isolation.py::JobGateTests::test_website_audit_blocked_after_queueing`,
   `tests/test_sprintS5_workday.py::LockTests::test_unlock_only_via_suppression_list`.
3. **Gefunden ist nicht erlaubt.** Ein Kontaktweg, eine Rolle, ein Bedarfssignal oder eine gute Bewertung setzt nie die Kontakterlaubnis;
   ein Angebot braucht einen bestätigten Bedarf.
   Durchgesetzt: `sales_tool/workday.py::check_stage_change`.
   Test: `tests/test_sprintS5_workday.py::NeedAndGuideTests::test_proposal_send_needs_confirmed_need`.
4. **Kein Versand.** Kein SMTP, keine Telefon- oder Nachrichtendienste. Einzige Ausnahme: ein Entwurf per IMAP-APPEND in den Entwürfe-Ordner.
   Durchgesetzt: `sales_tool/imap_drafts.py::put_draft`.
   Tests: `tests/test_v2_imap_drafts.py::ImapDraftTests::test_no_sending_anywhere`, `tests/test_claude_rules.py::RuleReferenceTests::test_no_mail_sending_library`.
5. **Personen werden nie automatisch angelegt.** Kandidaten bleiben bis zur menschlichen Prüfung außerhalb der CRM-Kontakte;
   Telefonnummern und E-Mail-Adressen werden nie aus Mustern erzeugt.
   Test: `tests/test_sprintC_report.py::ReportTests::test_one_click_report_runs_all_steps`.
6. **Kein Wert ohne Beleg.** Jeder übernommene Wert braucht eine Fundstelle im Originaltext; erfundene Werte werden verworfen.
   Durchgesetzt: `sales_tool/research/evidence.py::validate_fields`.
   Tests: `tests/test_sprintS2_extraction.py::EvidenceTests::test_invented_values_are_rejected`,
   `tests/test_sprintS2_extraction.py::FixtureExtractionTests::test_every_value_has_evidence`.
7. **Nur kontrollierter Abruf.** Öffentliche Ziele mit IP-Pinning, robots.txt nach RFC 9309, Größen- und Zeitgrenzen; keine Umgehung von
   Sperren, CAPTCHAs oder Plattformbedingungen; kein Auslesen von LinkedIn, XING, Google Maps oder Suchmaschinen.
   Durchgesetzt: `sales_tool/research/safe_urls.py::resolve_public`, `sales_tool/research/fetchers/http.py::robots_check`.
   Tests: `tests/test_sprintS1_fetch.py::FetchTests::test_ssrf_redirects_never_connect`,
   `tests/test_sprintS1_fetch.py::FetchTests::test_dns_rebinding_blocked_by_pinning`.
8. **Mandanten sind getrennt.** Eine Datenbank je Organisation; Sitzung, Auftrag, Sperre, Export und Wiederherstellung wirken nur in ihr.
   Durchgesetzt: `sales_tool/tenancy.py::use`, `sales_tool/tenancy.py::export_organization`.
   Tests: `tests/test_gate_isolation.py::TenantGateTests::test_job_of_one_org_never_runs_in_the_other`,
   `tests/test_sdq014_multi_tenant.py::MultiTenantTests::test_without_login_only_login_page_and_program_files`.
9. **Festgeschriebene Rechnungen bleiben** (GoBD) – auch eine Wiederherstellung darf sie nicht entfernen.
   Durchgesetzt: `sales_tool/backup_restore.py::restore`.
   Test: `tests/test_sprintS6_release.py::RestoreTests::test_gobd_refuses_losing_final_invoices`.
10. **Keine Geheimnisse im Repository oder Paket.** Keine API-Keys, Zugangsdaten oder echten Personendaten; Testdaten sind erfunden.
    Durchgesetzt: `tools/build_release.py::check_safe`, Gitleaks im CI-Job „audit“ (`.gitleaks.toml`).
    Test: `tests/test_ci_gates.py::CiGateTests::test_audit_job_runs_all_checks`.
11. **Ehrlicher Status.** Nichts gilt als fertig, was nicht in dieser Sitzung gelaufen ist; rote Gates werden behoben, nicht abgeschaltet;
    ein Fehler ist ein Teilergebnis, kein negativer Befund. Status steht nur in `docs/plan/open_intelligence.json` und `docs/ROADMAP.md`.
    Durchgesetzt: `tools/plan_status.py::validate`.
    Test: `tests/test_plan_structure.py::PlanSourceTests::test_plan_is_valid`.

## Arbeitsweise

- **Vor jedem Commit** die Prüfliste `.claude/skills/qa-release-gate` abarbeiten: Unit-Tests (`python -m unittest discover -s tests`),
  Browser-Tests (`python tools/run_e2e.py --no-skips`), bei Schemaänderung `SCHEMA_VERSION` erhöhen und Migrationstest schreiben.
- Änderungen an Kontaktwegen, Personen, Sperren, Importen oder Entwürfen: Skill `privacy-and-contact-guardrails`.
- Neue oder geänderte Abhängigkeiten: Skill `dependency-security`. Externe Skills nur nach `docs/SKILLS_REGISTRY.md`.
- Planstatus ändern: `docs/plan/open_intelligence.json` bearbeiten, dann `python tools/plan_status.py --write`.
- Version in `sales_tool/__init__.py`, erster Eintrag in `CHANGELOG.md`, README/ROADMAP/EINSCHRAENKUNGEN gleich halten
  (`tests/test_plan_structure.py` prüft das). Nach Versionswechsel `python tools/make_sbom.py`.
- Netzwerk in Tests nur über Attrappen; keine echten Firmen-Websites abrufen.
- Keine Modellkennungen in Commits, Kommentaren oder Doku.
