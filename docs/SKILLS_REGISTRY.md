# Skills- und Werkzeugregister (R0.4)

Stand 2.0.0-dev70. Skills steuern die Arbeit von Claude Code; sie sind **keine Laufzeitfunktion und keine Sicherheitsgrenze** –
die Regeln setzt das Programm durch (siehe [`CLAUDE.md`](../CLAUDE.md)). Dieses Register ist die einzige Stelle, an der
Skills, externe Skill-Sammlungen und Entwicklungswerkzeuge aufgenommen werden. `tests/test_skills_registry.py` prüft, dass jeder
Skill unter `.claude/skills/` hier steht und das vorgeschriebene Format hat.

## Regeln für die Aufnahme

1. Nur bei konkretem Bedarf mit Plan-Eintrag (`docs/plan/open_intelligence.json`, Abschnitte „Skills“ und „Technologien“).
2. Externe Originale: Repository, **gepinnter Commit oder Version mit Prüfsumme**, Lizenz, Ausführungsrechte (welche Skripte, welche
   Netz-/Schreibzugriffe) – alles vor der Aufnahme hier eintragen. Skripte vorher lesen.
3. Keine blind installierten Marketplaces, Hooks, MCP-Server oder Plugin-Sammlungen; keine erhöhten Rechte.
4. Projekt-Skills haben Auslöser (Frontmatter `description`), Eingaben, Prüfliste oder Ablauf, Ausgabe, Sicherheitsregeln und ein Beispiel.
5. Ein Skill ersetzt keinen Test: Jede Regel, die ein Skill prüft, hat einen Test im Repository.

## Projekt-Skills (`.claude/skills/`)

| Skill | Auslöser | Prüft gegen | Plan-Paket | Stand |
|---|---|---|---|---|
| `privacy-and-contact-guardrails` | Kontaktwege, Personen, Sperren, Importe, Entwürfe | `tests/test_sprintS5_workday.py`, `tests/test_gate_isolation.py` | R0.4 | vorhanden |
| `qa-release-gate` | vor jedem Commit, Release, nach Schemaänderung | Unit-, Browser-, Release-Tests, CI | R0.4 | vorhanden |
| `dependency-security` | neue/geänderte Abhängigkeit, Lockdatei, CI-Werkzeug | `tests/test_ci_gates.py`, CI-Job „audit“, SBOM | R0.4 | vorhanden (dev67) |
| `research-source-policy` | neue Quelle oder Abruflogik | `tests/test_r1_source_registry.py` (Source Registry) | R1.2 | vorhanden (dev69) |
| `research-benchmark` | neue Extraktion oder Zuordnung | `tools/research_benchmark.py`, `tests/test_sdq006_research_benchmark.py` | R1.7 | vorhanden (dev69) |
| `contact-entity-evidence` | Person/Rolle → Identität, Beleg, Kandidatenstatus, Sperren | `tests/test_r2_candidates.py`, `tests/test_r2_persons.py`, `tests/test_r2_evidence.py` | R2.6 | vorhanden (dev70) |
| `document-intelligence` | PDF/XML/CSV/ZIP lesen, Werte aus Dokumenten | `tests/test_r3_documents.py` (isolierter Parser, Fundstellen) | R3.5 | vorhanden (dev71) |
| `organization-graph` | Beziehungen, Graph | Invarianten R4.2 | R4.7 | geplant |
| `saas-operations` | Deployment, Betrieb | Restore-, Mandanten-, Sicherheitstests | R6.11 | geplant |

## Entwicklungswerkzeuge (in Gebrauch)

| Werkzeug | Original | Version / Pin | Lizenz | Zweck | Läuft wo |
|---|---|---|---|---|---|
| pip-audit | github.com/pypa/pip-audit | `tools/requirements-lock-dev.txt` (Hashes) | Apache-2.0 | bekannte Schwachstellen in allen Lockdateien | CI-Job „audit“ |
| Ruff | github.com/astral-sh/ruff | `tools/requirements-lock-dev.txt` (Hashes) | MIT | Fehlerklassen E9, F63, F7, F82 | CI-Job „audit“ |
| Gitleaks | github.com/gitleaks/gitleaks | 8.28.0, SHA-256 im Workflow | MIT | Geheimnisse in Code und Historie (`.gitleaks.toml`) | CI-Job „audit“ |
| Playwright | github.com/microsoft/playwright-python | `requirements-lock-browser.txt` (Hashes) | Apache-2.0 | Browser-Tests, Variante „browser“ | CI-Job „e2e“ |

## Kandidaten (nicht installiert)

Aus dem Architektur- und Masterplan (Kapitel 10). Aufnahme nur nach den Regeln oben; Lizenz und Ausführungsrechte vor Aufnahme prüfen.

| Original | Auswahl laut Plan | Wann | Stand |
|---|---|---|---|
| github.com/anthropics/skills | skill-creator, webapp-testing, frontend-design, pdf | bei konkretem Bedarf | nicht installiert |
| github.com/obra/superpowers | writing-plans, test-driven-development, systematic-debugging | Workflow prüfen | nicht installiert |
| github.com/trailofbits/skills | audit-context-building, differential-review, testing-handbook-skills, supply-chain-risk-auditor | vor R6.10 | nicht installiert |
| github.com/anthropics/claude-plugins-official | kuratierten Katalog prüfen, keine Komplettinstallation | bei Bedarf | nicht installiert |
| github.com/HypothesisWorks/hypothesis | Property-Tests für Parser, Identität, Graph | R4.2 | nicht installiert |
| github.com/google/osv-scanner | zweite Advisory-Quelle neben pip-audit | bei Bedarf | nicht installiert |
| github.com/zaproxy/zaproxy | nur gegen eigene Staging-Systeme | R6.4/R6.9 | nicht installiert |

Plugins und MCP-Server, die eine einzelne Claude-Code-Sitzung mitbringt, gehören nicht zum Repository und werden für die Arbeit an
SignalDesk nicht verwendet, solange sie hier nicht aufgenommen sind.
