# Baseline 2.0.0-dev67

> Erzeugt mit `python tools/baseline.py` am 2026-11-26. Commit `42ba3f049a11`, Linux x86_64.

Was hier steht, ist in diesem Lauf ausgeführt worden. CI-Ergebnis nur, wenn mit `--ci` angegeben.

## Testläufe

| Suite | gefunden | gelaufen | übersprungen | Ergebnis | Dauer |
|---|---|---|---|---|---|
| Unit (`tests/`, Python 3.13.18) | 997 | 997 | 2 | bestanden | 440.8 s |
| Unit (`tests/`, Python 3.10.20) | 997 | 997 | 13 | bestanden | 465.2 s |
| Browser (`tests/e2e/`, Python 3.13.18) | 60 | 60 | 0 | **1 nicht bestanden** | 297.5 s |

## Übersprungene Tests mit Grund

- Unit (`tests/`, Python 3.13.18): `test_baseline_report_exists_when_r01_done (test_plan_structure.GeneratedDocsTests.test_baseline_report_exists_when_r01_done)` – läuft innerhalb von tools/baseline.py – der Bericht entsteht erst am Ende dieses Laufs
- Unit (`tests/`, Python 3.13.18): `test_windows_dpapi_roundtrip (test_sdq004_credentials.CredentialStoreTests.test_windows_dpapi_roundtrip)` – nur unter Windows (CI)
- Unit (`tests/`, Python 3.10.20): `test_rendered_capture_contains_screenshots_and_measurements (test_phase2_scoring.RealBrowserTests)` – Playwright nicht installiert – Browser-Test übersprungen
- Unit (`tests/`, Python 3.10.20): `test_weak_site_is_flagged_from_real_rendering (test_phase2_scoring.RealBrowserTests)` – Playwright nicht installiert – Browser-Test übersprungen
- Unit (`tests/`, Python 3.10.20): `test_roundtrip_and_wrong_password (test_phase6_quality.EncryptedBackupTests)` – cryptography nicht installiert – verschlüsselte Sicherung übersprungen
- Unit (`tests/`, Python 3.10.20): `test_baseline_report_exists_when_r01_done (test_plan_structure.GeneratedDocsTests)` – läuft innerhalb von tools/baseline.py – der Bericht entsteht erst am Ende dieses Laufs
- Unit (`tests/`, Python 3.10.20): `test_windows_dpapi_roundtrip (test_sdq004_credentials.CredentialStoreTests)` – nur unter Windows (CI)
- Unit (`tests/`, Python 3.10.20): `test_encrypted_set (test_sdq017_operations.BackupTests)` – Paket cryptography fehlt
- Unit (`tests/`, Python 3.10.20): `test_roundtrip (test_sdq021_security.EncryptedExportTests)` – Paket cryptography fehlt (requirements-team.txt)
- Unit (`tests/`, Python 3.10.20): `test_rules (test_sdq021_security.EncryptedExportTests)` – Paket cryptography fehlt (requirements-team.txt)
- Unit (`tests/`, Python 3.10.20): `test_cli_xlsx (test_sdq029_betrieb_more.ReferenceTableTests)` – openpyxl nicht installiert – xlsx-Weg übersprungen (CSV ist getestet)
- Unit (`tests/`, Python 3.10.20): `test_encrypted_set_via_cli (test_sdq029_betrieb_more.RestoreInstallationTests)` – cryptography nicht installiert – verschlüsselter Satz übersprungen
- Unit (`tests/`, Python 3.10.20): `test_scrapling (test_sprintS1_fetch.ParseTests)` – Scrapling optional (requirements-research.txt)
- Unit (`tests/`, Python 3.10.20): `test_trafilatura_optional (test_sprintS2_extraction.ContentTests)` – Trafilatura optional
- Unit (`tests/`, Python 3.10.20): `test_encrypted_backup_roundtrip (test_sprintS6_release.RestoreTests)` – cryptography nicht installiert (Variante „team“)

## Nicht bestanden

- Browser (`tests/e2e/`, Python 3.13.18): `test_company_file_page (test_ui_akte_browser.UiAkteBrowserTests.test_company_file_page)` – - element is not visible | - retrying click action | - waiting 500ms

## Beobachtungen aus früheren Läufen

- Vorläufe auf diesem Stand fanden zwei Wettläufe in Tests (Prüfung vor dem Eintrag des Server-Threads): test_sdq029_betrieb_more.RejectedBodyTests und test_sdq017_operations.HealthAndLogTests.test_unauthorized_logged_as_warning – beide behoben und mit künstlicher Verzögerung nachgewiesen (alt rot, neu grün).
- Browser-Test test_ui_akte_browser.UiAkteBrowserTests.test_company_file_page schlug in 1 von 7 vollen Browser-Läufen fehl (Baseline-Lauf 3); einzeln 4/4 und in zwei weiteren Komplettläufen grün. Fehlermeldung wurde damals nicht aufgezeichnet – das Werkzeug zeichnet sie seitdem auf. Test nicht gelockert; offen.

## CI

nicht angegeben (in diesem Lauf nicht gelesen).

## Planstand (R0–R7)

| Phase | offen | teilweise | erledigt | blockiert |
|---|---|---|---|---|
| R0 | 0 | 0 | 8 | 0 |
| R1 | 3 | 3 | 0 | 1 |
| R2 | 3 | 3 | 0 | 0 |
| R3 | 4 | 1 | 0 | 0 |
| R4 | 5 | 2 | 0 | 0 |
| R5 | 1 | 2 | 0 | 3 |
| R6 | 2 | 8 | 0 | 2 |
| R7 | 1 | 1 | 0 | 3 |

## Nicht Teil dieser Baseline

- macOS; echte Websites (alle Tests nutzen Attrappen); Lastmessung; Trefferquote an echten Firmen.
