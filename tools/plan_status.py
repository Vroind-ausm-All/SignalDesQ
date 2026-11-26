"""Open-Intelligence-Plan (R0–R7): Planquelle prüfen und Dokumente daraus erzeugen.

    python tools/plan_status.py            # prüfen und Zusammenfassung ausgeben
    python tools/plan_status.py --write    # docs/MASTERPLAN_OPEN_INTELLIGENCE.md und den Plan-Abschnitt in docs/ROADMAP.md erzeugen
    python tools/plan_status.py --check    # Fehler, wenn die Planquelle ungültig oder ein erzeugtes Dokument veraltet ist

Quelle: docs/plan/open_intelligence.json (einzige Stelle, an der Status, Abhängigkeiten und Abnahmen gepflegt werden).
Nur Standardbibliothek; läuft unter Python 3.10 bis 3.14.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs' / 'plan' / 'open_intelligence.json'
MASTERPLAN = ROOT / 'docs' / 'MASTERPLAN_OPEN_INTELLIGENCE.md'
ROADMAP = ROOT / 'docs' / 'ROADMAP.md'
BEGIN, END = '<!-- plan:roadmap:begin (erzeugt von tools/plan_status.py) -->', '<!-- plan:roadmap:end -->'

PHASE_ORDER = {'R0': 0, 'R1': 1, 'R2': 2, 'R3': 2, 'R4': 3, 'R5': 4, 'R6': 5, 'R7': 6}  # R3 parallel zu R2; R6 schließt vor R7
STATUS = ('offen', 'teilweise', 'erledigt', 'blockiert')
PRIO = ('P0', 'P1', 'P2')
OWNERS = ('Engineering', 'Eigentümer', 'Betrieb', 'Extern', 'Recht', 'Steuerberatung')
PACKAGE_KEYS = {'id', 'titel', 'prio', 'status', 'verantwortlich', 'inhalt', 'basis', 'neu', 'abhaengig_von', 'abnahme'}
OPTIONAL_KEYS = {'nachweis', 'weich_abhaengig_von'}
PATH_PREFIXES = ('sales_tool/', 'tools/', 'tests/', 'docs/', '.claude/', '.github/', 'deploy/')


def load(path=SOURCE):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def phase_of(pid):
    return pid.split('.')[0]


def _path_of(entry):
    """„sales_tool/x.py (Erklärung)“ → „sales_tool/x.py“; None, wenn kein prüfbarer Pfad."""
    p = entry.split(' (')[0].strip()
    if not p.startswith(PATH_PREFIXES) or any(c in p for c in '*<>') or ' ' in p:
        return None
    return p


def _test_ref_problem(ref):
    """„tests/datei.py::Klasse::test_name“ → '' wenn vorhanden, sonst der Grund."""
    parts = ref.split('::')
    if len(parts) != 3 or not parts[0].startswith('tests/') or not parts[2].startswith('test_'):
        return 'Format tests/datei.py::Klasse::test_name'
    path = ROOT / parts[0]
    if not path.exists():
        return 'Datei fehlt'
    text = path.read_text(encoding='utf-8')
    if not re.search(rf'^class {re.escape(parts[1])}\b', text, re.M):
        return 'Klasse fehlt'
    if not re.search(rf'^    def {re.escape(parts[2])}\(', text, re.M):
        return 'Test fehlt'
    return ''


def validate(plan):
    """Gibt eine Liste von Fehlern zurück (leer = gültig)."""
    err = []
    phases = plan.get('phasen', [])
    ids = [p['id'] for p in phases]
    if ids != list(PHASE_ORDER):
        err.append(f'Phasen müssen genau {", ".join(PHASE_ORDER)} in dieser Reihenfolge sein, gefunden: {ids}')
    for ph in phases:
        for dep in ph.get('abhaengig_von', []):
            if dep not in PHASE_ORDER or PHASE_ORDER[dep] >= PHASE_ORDER.get(ph['id'], 99):
                err.append(f"{ph['id']}: Phasenabhängigkeit {dep} liegt nicht vor dieser Phase")
        if not ph.get('abnahme'):
            err.append(f"{ph['id']}: keine Abnahme")
    decisions = {d['id'] for d in plan.get('entscheidungen', [])}
    pkgs = plan.get('pakete', [])
    pid_list = [p.get('id') for p in pkgs]
    dup = {x for x in pid_list if pid_list.count(x) > 1}
    if dup:
        err.append(f'doppelte Paket-IDs: {sorted(dup)}')
    known = set(pid_list)
    for p in pkgs:
        pid = p.get('id', '?')
        missing = PACKAGE_KEYS - set(p)
        extra = set(p) - PACKAGE_KEYS - OPTIONAL_KEYS
        if missing:
            err.append(f'{pid}: fehlende Felder {sorted(missing)}')
            continue
        if extra:
            err.append(f'{pid}: unbekannte Felder {sorted(extra)}')
        if not re.fullmatch(r'R[0-7]\.\d+', pid):
            err.append(f'{pid}: ID muss „R<Phase>.<Nummer>“ sein')
            continue
        if p['status'] not in STATUS:
            err.append(f"{pid}: Status {p['status']!r} unbekannt")
        if p['prio'] not in PRIO:
            err.append(f"{pid}: Priorität {p['prio']!r} unbekannt")
        if p['verantwortlich'] not in OWNERS:
            err.append(f"{pid}: Verantwortlich {p['verantwortlich']!r} unbekannt")
        if not p['abnahme']:
            err.append(f'{pid}: keine Abnahme')
        if p['status'] in ('erledigt', 'teilweise') and not p.get('nachweis'):
            err.append(f"{pid}: Status {p['status']} ohne Nachweis")
        if p['status'] == 'erledigt' and not re.search(r'\d+\.\d+\.\d+-dev\d+|v1\.\d+', p.get('nachweis', '')):
            err.append(f'{pid}: erledigt ohne Version im Nachweis')
        for key in ('abhaengig_von', 'weich_abhaengig_von'):
            for dep in p.get(key, []):
                if dep in decisions:
                    continue
                if dep not in known:
                    err.append(f'{pid}: Abhängigkeit {dep} unbekannt')
                elif PHASE_ORDER[phase_of(dep)] > PHASE_ORDER[phase_of(pid)]:
                    err.append(f'{pid}: hängt von {dep} aus einer späteren Phase ab')
                elif dep == pid:
                    err.append(f'{pid}: hängt von sich selbst ab')
        for entry in p['basis'] + p['neu']:
            if not isinstance(entry, str) or not entry.strip():
                err.append(f'{pid}: leerer Eintrag in basis/neu')
        for entry in p['basis']:
            path = _path_of(entry)
            if path and not (ROOT / path).exists():
                err.append(f'{pid}: Grundlage {path} existiert nicht')
    # Zyklen in den harten Abhängigkeiten
    graph = {p['id']: [d for d in p.get('abhaengig_von', []) if d in known] for p in pkgs if 'id' in p}
    state = {}

    def visit(n, trail):
        if state.get(n) == 1:
            err.append('Zyklus: ' + ' → '.join(trail + [n]))
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for d in graph.get(n, []):
            visit(d, trail + [n])
        state[n] = 2
    for n in graph:
        visit(n, [])
    for ph in PHASE_ORDER:
        if not any(phase_of(p['id']) == ph for p in pkgs if 'id' in p):
            err.append(f'{ph}: keine Arbeitspakete')
    for f in plan.get('sicherheitsbefunde', []):
        if not f.get('pakete') or any(x not in known for x in f['pakete']):
            err.append(f"{f['id']}: kein oder unbekanntes Paket")
        if f.get('verantwortlich') not in OWNERS:
            err.append(f"{f['id']}: Verantwortlich fehlt oder unbekannt")
        if not f.get('gate_tests'):
            err.append(f"{f['id']}: kein Gate-Test")
        if not f.get('offen'):
            err.append(f"{f['id']}: offener Nachweis nicht beschrieben (sonst „–“)")
        for ref in f.get('gate_tests', []):
            problem = _test_ref_problem(ref)
            if problem:
                err.append(f"{f['id']}: Gate-Test {ref}: {problem}")
    if [f['id'] for f in plan.get('sicherheitsbefunde', [])] != [f'F{i:02d}' for i in range(1, 13)]:
        err.append('Sicherheitsbefunde müssen genau F01–F12 abdecken')
    for k in plan.get('kennzahlen', []):
        if k.get('gate') not in PHASE_ORDER:
            err.append(f"Kennzahl {k.get('name')}: Gate-Phase fehlt")
    for t in plan.get('technologien', []):
        if t.get('paket') not in known:
            err.append(f"Technologie {t.get('repo')}: Paket {t.get('paket')} unbekannt")
    for s in plan.get('skills', []):
        if s.get('paket') not in known:
            err.append(f"Skill {s.get('name')}: Paket {s.get('paket')} unbekannt")
        if s.get('status') == 'vorhanden' and not (ROOT / '.claude' / 'skills' / s['name'] / 'SKILL.md').exists():
            err.append(f"Skill {s['name']}: als vorhanden geführt, aber keine SKILL.md")
        if s.get('status') == 'offen' and (ROOT / '.claude' / 'skills' / s['name'] / 'SKILL.md').exists():
            err.append(f"Skill {s['name']}: SKILL.md existiert, Status noch „offen“")
    for d in plan.get('entscheidungen', []):
        if d.get('benoetigt_fuer') not in known:
            err.append(f"Entscheidung {d.get('id')}: Paket {d.get('benoetigt_fuer')} unbekannt")
        if d.get('verantwortlich') not in OWNERS:
            err.append(f"Entscheidung {d.get('id')}: Verantwortlich unbekannt")
    for r in plan.get('reifeprofil', []):
        if any(x not in PHASE_ORDER for x in r.get('phasen', [])):
            err.append(f"Reifeprofil {r.get('dimension')}: unbekannte Phase")
    for r in plan.get('roadmap_bezug', []):
        if any(x not in known and x not in PHASE_ORDER for x in r.get('jetzt', [])):
            err.append(f"Roadmap-Bezug {r.get('bisher')}: unbekanntes Ziel")
    return err


# ---------------------------------------------------------------- Ausgabe

def _cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def _join(items, empty='–'):
    return '<br>'.join(_cell(x) for x in items) if items else empty


def _ref(entry):
    """Datei in Code-Schrift, Erklärung in Klammern dahinter normal; reiner Text bleibt Text."""
    head, _, tail = entry.partition(' (')
    if head.startswith(('sales_tool/', 'tools/', 'tests/', 'docs/', '.claude/', '.github/', 'deploy/', 'CLAUDE.md', 'requirements')) or head.endswith(('.py', '.md', '.js')):
        return f'`{head}`' + (f' ({tail}' if tail else '')
    return _cell(entry)


def counts(pkgs):
    return {s: sum(1 for p in pkgs if p['status'] == s) for s in STATUS}


def _count_text(c):
    return ' · '.join(f'{n} {s}' for s, n in c.items() if n) or '–'


def _ready(all_pkgs, mine, n=3):
    """Startbereit: offen oder teilweise, alle harten Abhängigkeiten erledigt (Entscheidungen zählen als offen). P0 zuerst."""
    order = {'P0': 0, 'P1': 1, 'P2': 2}
    done = {p['id'] for p in all_pkgs if p['status'] == 'erledigt'}
    ready = [p for p in mine if p['status'] in ('offen', 'teilweise') and all(d in done for d in p['abhaengig_von'])]
    ready.sort(key=lambda p: (order[p['prio']], p['status'] != 'teilweise', int(p['id'].split('.')[1])))
    return ready[:n]


def mermaid(plan):
    lines = ['```mermaid', 'flowchart LR']
    for ph in plan['phasen']:
        lines.append(f'  {ph["id"]}["{ph["id"]} · {ph["name"]}<br>{ph["aufwand"]}"]')
    for ph in plan['phasen']:
        for dep in ph['abhaengig_von']:
            style = '-->' if ph['kritischer_pfad'] and dep != 'R6' and next(x for x in plan['phasen'] if x['id'] == dep)['kritischer_pfad'] else '-.->'
            lines.append(f'  {dep} {style} {ph["id"]}')
    lines.append('```')
    return '\n'.join(lines)


def render_masterplan(plan):
    pkgs = plan['pakete']
    by_phase = {ph['id']: [p for p in pkgs if phase_of(p['id']) == ph['id']] for ph in plan['phasen']}
    total = counts(pkgs)
    L = [f"# Masterplan: {plan['titel']}", '',
         '> **Erzeugt aus [`plan/open_intelligence.json`](plan/open_intelligence.json) mit `python tools/plan_status.py --write` – nicht von Hand ändern.**',
         f"> Quelle: [Architektur- und Masterplan vom 25.11.2026]({plan['quelle'].replace('docs/', '')}) · Referenzstand {plan['referenzstand']} · "
         f"eingearbeitet in {plan['eingearbeitet_in']}. Status je Paket: {', '.join(f'**{k}** = {v}' for k, v in plan['status_werte'].items())}.",
         '',
         f"**Empfohlener Kurs.** {plan['kurs']}", '',
         f"**Produktversprechen.** {plan['produktversprechen']}", '',
         f"**Wirtschaftlicher Kernindikator.** {plan['kernindikator']} **Priorisierung:** {plan['priorisierung']}", '',
         f"**Stand aller {len(pkgs)} Arbeitspakete:** {_count_text(total)}.", '',
         '## Inhalt', '',
         '1. [Unverhandelbare Regeln](#unverhandelbare-regeln)', '2. [Phasen und kritischer Pfad](#phasen-und-kritischer-pfad)',
         '3. [Arbeitspakete je Phase](#arbeitspakete-je-phase)', '4. [Sicherheitsbefunde F01–F12](#sicherheitsbefunde-f01f12)',
         '5. [Kennzahlen und Gates](#kennzahlen-und-gates)', '6. [Reifeprofil](#reifeprofil)', '7. [Technologieregister](#technologieregister)',
         '8. [Skills](#skills)', '9. [Entscheidungen außerhalb des Engineerings](#entscheidungen-außerhalb-des-engineerings)',
         '10. [Bezug zur bisherigen Roadmap](#bezug-zur-bisherigen-roadmap)', '11. [So wird der Plan gepflegt](#so-wird-der-plan-gepflegt)', '',
         '## Unverhandelbare Regeln', '']
    L += [f'{i}. {r}' for i, r in enumerate(plan['regeln'], 1)]
    L += ['', '## Phasen und kritischer Pfad', '',
          'Durchgezogene Pfeile: kritischer Pfad R0 → R1 → R2 → R4 → R5 → R7. Gestrichelt: parallel (R3 nach R1; R6 beginnt nach R0 und muss vor R7 abgeschlossen sein).', '',
          mermaid(plan), '',
          '| Phase | Name | Aufwand* | Beginnt nach | Ziel | Abnahme (Gate) | Pakete |', '|---|---|---|---|---|---|---|']
    for ph in plan['phasen']:
        L.append(f"| **{ph['id']}** | {_cell(ph['name'])} | {_cell(ph['aufwand'])} | {', '.join(ph['abhaengig_von']) or '–'} | {_cell(ph['ziel'])}"
                 f"{' ' + _cell(ph['hinweis']) if ph.get('hinweis') else ''} | {_join(ph['abnahme'])} | {_count_text(counts(by_phase[ph['id']]))} |")
    L += ['', '\\* Grobe Schätzung des Plans für einen Entwickler mit Claude-Unterstützung, ohne Garantie; R0–R6 seriell etwa 13–21 Wochen. '
          'Abhängigkeiten und Freigaben gehen vor Kalenderdaten.', '', '## Arbeitspakete je Phase', '']
    for ph in plan['phasen']:
        L += [f"### {ph['id']} – {ph['name']}", '', f"*{_cell(ph['ziel'])}*", '',
              '| ID | Paket | Prio | Status | Verantwortlich | Abhängig von | Abnahme |', '|---|---|---|---|---|---|---|']
        for p in by_phase[ph['id']]:
            deps = p['abhaengig_von'] + [f'({d}, weich)' for d in p.get('weich_abhaengig_von', [])]
            L.append(f"| **{p['id']}** | {_cell(p['titel'])} | {p['prio']} | {p['status']} | {p['verantwortlich']} | {', '.join(deps) or '–'} | {_join(p['abnahme'])} |")
        L.append('')
        for p in by_phase[ph['id']]:
            L.append(f"- **{p['id']} {_cell(p['titel'])}.** {_cell(p['inhalt'])}")
            if p['basis']:
                L.append(f"  Baut auf: {', '.join(_ref(b) for b in p['basis'])}.")
            if p['neu']:
                L.append(f"  Neu: {', '.join(_ref(n) for n in p['neu'])}.")
            if p.get('nachweis'):
                L.append(f"  Stand: {_cell(p['nachweis'])}.")
        L.append('')
    L += ['## Sicherheitsbefunde F01–F12', '',
          'Prüfbericht vom 24.11.2026 (geprüft auf dev64). Stand laut dev65-Dokumentation, nicht unabhängig nachgeprüft – das ist Paket R6.10.', '',
          'Gate-Tests laufen in jeder CI; die Planprüfung stellt sicher, dass jeder genannte Test existiert. Weg der Nachprüfung: '
          '[SICHERHEITS_NACHPRUEFUNG.md](SICHERHEITS_NACHPRUEFUNG.md).', '',
          '| Befund | Thema | Stand dev65 | Verantwortlich | Gate-Tests | Offener Nachweis | Pakete |', '|---|---|---|---|---|---|---|']
    L += [f"| {f['id']} | {_cell(f['thema'])} | {_cell(f['stand_dev65'])} | {f['verantwortlich']} | "
          f"{_join(['`' + t.split('::', 1)[0].replace('tests/', '') + '` ' + t.split('::')[-1] for t in f['gate_tests']])} | {_cell(f['offen'])} | {', '.join(f['pakete'])} |"
          for f in plan['sicherheitsbefunde']]
    L += ['', '**Release-Regel:** Keine öffentliche Registrierung oder Produktivfreigabe bei offenen hohen/kritischen Befunden, fehlender '
          'Gegenprüfung oder ungetesteter Wiederherstellung. SHA-256 allein authentifiziert keine Updates.', '',
          '## Kennzahlen und Gates', '', 'Vorgeschlagene Abnahmegrenzen, keine Ergebnisse; vom Eigentümer zu bestätigen (Entscheidung E4).', '',
          '| Kennzahl | Ziel für Pilot/Beta | Messmethode | Gate in Phase |', '|---|---|---|---|']
    L += [f"| {_cell(k['name'])} | {_cell(k['ziel'])} | {_cell(k['methode'])} | {k['gate']} |" for k in plan['kennzahlen']]
    L += ['', '## Reifeprofil', '', 'Arbeitsbewertung des Plans (0 = fehlt … 100 = produktiv unabhängig nachgewiesen), keine Gesamtnote.', '',
          '| Dimension | Ist (Schätzung) | Ziel Beta | Phasen |', '|---|---|---|---|']
    L += [f"| {_cell(r['dimension'])} | {r['ist'] if r['ist'] is not None else _cell(r.get('hinweis', '–'))} | "
          f"{r['ziel_beta'] if r['ziel_beta'] is not None else '–'} | {', '.join(r['phasen'])} |" for r in plan['reifeprofil']]
    L += ['', '## Technologieregister', '',
          'Kandidaten, keine Installationsliste. Jede neue Abhängigkeit braucht Lizenz-, Sicherheits-, Performance- und Plattformprüfung '
          '(Softwarelizenz, Modellgewicht-Lizenz und Datenrechte getrennt) und einen Eintrag in `docs/BESTANDTEILE.md`.', '',
          '| Repository (GitHub) | Verwendung | Prio | Paket |', '|---|---|---|---|']
    L += [f"| {_cell(t['repo'])} | {_cell(t['zweck'])} | {t['prio']} | {t['paket']} |" for t in plan['technologien']]
    L += ['', 'Bereits geprüft und verworfen bzw. optional: Scrapling und Trafilatura (optional, im Benchmark langsamer), Extruct (Installationsproblem '
          'unter Python 3.13), DuckDB (schnellerer Import, deutlich mehr Speicher). Änderung nur mit neuer Messung.', '',
          '## Skills', '', 'Skills steuern die Arbeit von Claude Code; sie sind keine Laufzeitfunktion und keine Sicherheitsgrenze.', '',
          '| Skill (`.claude/skills/`) | Status | Auslöser / Prüfung | Paket |', '|---|---|---|---|']
    L += [f"| {s['name']} | {s['status']} | {_cell(s['ausloeser'])} | {s['paket']} |" for s in plan['skills']]
    L += ['', '## Entscheidungen außerhalb des Engineerings', '', '| ID | Verantwortlich | Entscheidung / Nachweis | Benötigt für |', '|---|---|---|---|']
    L += [f"| {d['id']} | {d['verantwortlich']} | {_cell(d['thema'])} | {d['benoetigt_fuer']} |" for d in plan['entscheidungen']]
    L += ['', '## Bezug zur bisherigen Roadmap', '', '| Bisher | Jetzt |', '|---|---|']
    L += [f"| {_cell(r['bisher'])} | {', '.join(r['jetzt'])} |" for r in plan['roadmap_bezug']]
    L += ['', '## So wird der Plan gepflegt', '',
          '1. Status, Nachweis oder Abhängigkeit nur in `docs/plan/open_intelligence.json` ändern.',
          '2. `python tools/plan_status.py --write` erzeugt diese Datei und den Plan-Abschnitt in `docs/ROADMAP.md` neu.',
          '3. `tests/test_plan_structure.py` prüft Felder, Abhängigkeiten (keine späteren Phasen, keine Zyklen), Pfade der Grundlagen, '
          'F01–F12-Abdeckung, Skills, Versionsangaben und ob die erzeugten Dokumente aktuell sind.',
          '4. „erledigt“ verlangt einen Nachweis mit Version und Test; „teilweise“ einen Nachweis, was schon da ist.', '']
    return '\n'.join(L)


def render_roadmap_section(plan):
    pkgs = plan['pakete']
    L = [BEGIN, '', '## Open-Intelligence-Plan R0–R7 (ab 2.0.0-dev66)', '',
         f"Phasenplan aus dem Architektur- und Masterplan vom 25.11.2026. Vollständige Pakete, Abnahmen und Zuordnungen: "
         f"[MASTERPLAN_OPEN_INTELLIGENCE.md](MASTERPLAN_OPEN_INTELLIGENCE.md); Status wird in "
         f"[`plan/open_intelligence.json`](plan/open_intelligence.json) gepflegt. Stand aller {len(pkgs)} Pakete: {_count_text(counts(pkgs))}.", '',
         '| Phase | Name | Beginnt nach | Pakete | Startbereit (Abhängigkeiten erledigt, P0 zuerst) | Gate |', '|---|---|---|---|---|---|']
    for ph in plan['phasen']:
        mine = [p for p in pkgs if phase_of(p['id']) == ph['id']]
        nxt = ', '.join(f"{p['id']} {p['titel']}" for p in _ready(pkgs, mine)) or '– (wartet auf Vorphasen)'
        L.append(f"| **{ph['id']}** | {_cell(ph['name'])} | {', '.join(ph['abhaengig_von']) or '–'} | {_count_text(counts(mine))} | {_cell(nxt)} | {_cell(ph['abnahme'][0])} |")
    blocked = [p for p in pkgs if p['status'] == 'blockiert']
    L += ['', 'Kritischer Pfad: R0 → R1 → R2 → R4 → R5 → Freigabe. R3 läuft nach R1 parallel, R6-Betriebsmaßnahmen beginnen früh. '
          'Kein öffentlicher Start vor bestandener R6-Nachprüfung.', '',
          '**Wartet auf Entscheidungen oder Nachweise außerhalb des Engineerings:** '
          + '; '.join(f"{p['id']} ({p['verantwortlich']})" for p in blocked) + '.', '', END]
    return '\n'.join(L)


def apply_roadmap(text, section):
    if BEGIN in text and END in text:
        return text[:text.index(BEGIN)] + section + text[text.index(END) + len(END):]
    anchor = '\n## Status je Maßnahme'
    i = text.index(anchor)
    return text[:i] + '\n' + section + '\n' + text[i:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    plan = load()
    errors = validate(plan)
    if errors:
        print('Planquelle ungültig:')
        for e in errors:
            print(' -', e)
        return 1
    master = render_masterplan(plan)
    roadmap = apply_roadmap(ROADMAP.read_text(encoding='utf-8'), render_roadmap_section(plan))
    if a.write:
        MASTERPLAN.write_text(master, encoding='utf-8')
        ROADMAP.write_text(roadmap, encoding='utf-8')
        print('geschrieben:', MASTERPLAN.relative_to(ROOT), ROADMAP.relative_to(ROOT))
    elif a.check:
        stale = [str(p.relative_to(ROOT)) for p, want in ((MASTERPLAN, master), (ROADMAP, roadmap))
                 if not p.exists() or p.read_text(encoding='utf-8') != want]
        if stale:
            print('veraltet:', ', '.join(stale), '– python tools/plan_status.py --write')
            return 1
    c = counts(plan['pakete'])
    print(f"{len(plan['pakete'])} Pakete in {len(plan['phasen'])} Phasen: {_count_text(c)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
