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
| `ponytail` | jede Code-Änderung, Fehlerbehebung, Paketwahl; „einfachste Lösung“ | `tests/test_skills_registry.py` (Format, Pin des Originals); Regeln selbst über die Gate-Tests aus `CLAUDE.md` | R0.4 | vorhanden (dev70, externes Original) |
| `document-intelligence` | PDF/XML/CSV | isolierter Parser | R3.5 | geplant |
| `organization-graph` | Beziehungen, Graph | Invarianten R4.2 | R4.7 | geplant |
| `saas-operations` | Deployment, Betrieb | Restore-, Mandanten-, Sicherheitstests | R6.11 | geplant |

## Entwicklungswerkzeuge (in Gebrauch)

| Werkzeug | Original | Version / Pin | Lizenz | Zweck | Läuft wo |
|---|---|---|---|---|---|
| pip-audit | github.com/pypa/pip-audit | `tools/requirements-lock-dev.txt` (Hashes) | Apache-2.0 | bekannte Schwachstellen in allen Lockdateien | CI-Job „audit“ |
| Ruff | github.com/astral-sh/ruff | `tools/requirements-lock-dev.txt` (Hashes) | MIT | Fehlerklassen E9, F63, F7, F82 | CI-Job „audit“ |
| Gitleaks | github.com/gitleaks/gitleaks | 8.28.0, SHA-256 im Workflow | MIT | Geheimnisse in Code und Historie (`.gitleaks.toml`) | CI-Job „audit“ |
| Playwright | github.com/microsoft/playwright-python | `requirements-lock-browser.txt` (Hashes) | Apache-2.0 | Browser-Tests, Variante „browser“ | CI-Job „e2e“ |
| Graphify | github.com/Graphify-Labs/graphify | 0.9.106, `tools/requirements-lock-graphify.txt` (Hashes) | Apache-2.0 | Code-Graph: Aufrufer, Auswirkungen, Pfade (nur Quelltext, ohne KI) | lokal, nur über `tools/code_graph.py` |

## Externe Originale (Ausführungsrechte)

| Original | Pin | Prüfsumme (SHA-256) | Lizenz | Im Repository | Ausführungsrechte |
|---|---|---|---|---|---|
| github.com/DietrichGebert/ponytail | Commit `ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10` (5.3.3), Datei `skills/ponytail/SKILL.md` | `9badd22a32e19cb884e46dfa8d3aae82bb81dfa5484105b8b4f0262df823a509` | MIT | `.claude/skills/ponytail/ORIGINAL.md` (unverändert), `LICENSE`; deutscher Rahmen in `SKILL.md` | nur Text. **Nicht** übernommen: Plugin, Hooks (SessionStart, UserPromptSubmit, Stop), Statuszeile, Kosten-Tabelle unter `~/.config/ponytail/`, Webhook |
| github.com/Graphify-Labs/graphify | PyPI `graphifyy==0.9.106` mit Hashes; geprüft am Quelltext von Commit `02c27dc246cd7bc359d0f4acaf53a3fce595bc1e` (0.9.120) und am installierten Paket 0.9.106 | je Datei in `tools/requirements-lock-graphify.txt` | Apache-2.0 | `tools/requirements-graphify.txt`, Lock, `tools/code_graph.py` | liest den Quelltext, schreibt nur `graphify-out/` (in `.gitignore`); kein Netz im Code-Pfad. `code_graph.py` sperrt `install`/`hook`/`watch` (Hooks auf Bash/Grep/Read/Glob, Block in `CLAUDE.md`), setzt `GRAPHIFY_BACKEND=none` und `--code-only` und gibt keine API-Keys an den Prozess weiter |

Geprüft und **nicht** aufgenommen (26.11.2026): github.com/JuliusBrussee/caveman (Telemetrie standardmäßig an, Installer greift
auf Agenten-Logins zu, Hooks, englischer Telegrammstil gegen „Antworten auf Deutsch“) und github.com/morluto/rea (Reverse
Engineering fremder Software und Websites, kein Bezug zu SignalDesk, widerspricht Regel 7).

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
