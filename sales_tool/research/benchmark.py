"""Recherche-Benchmark (SDQ-006): Wie vollständig und wie richtig findet SignalDesk Firmen?

Zwei Dateien, beide JSON:

Referenzliste (`signaldesk-research-reference/1`) – von Menschen geprüft, nie von SignalDesk erzeugt:
    {"format": "signaldesk-research-reference/1", "name": "...", "synthetic": false,
     "queries": [{"id": "q1", "description": "Steuerberater, PLZ 70173–70199", "complete": true, "method": "...",
                  "companies": [{"ref_id": "r1", "name": "Muster Steuerberatung GmbH", "zip": "70173", "city": "Stuttgart",
                                 "website": "muster-stb.de", "register_id": "HRB 12345", "lei": "", "status": "aktiv",
                                 "evidence": ["https://..."], "checked_by": ["AB", "CD"], "checked_on": "2026-11-20"}]}]}

    website/register_id: Text = geprüfter Wert · null = geprüft, gibt es nicht · Feld fehlt = nicht geprüft (zählt nicht).
    status: aktiv (gehört dazu) · geschlossen · ausser_bereich (falsche Branche/Ort) – wer diese findet, hat sicher falsch gefunden.
    complete: true nur, wenn die Liste das Gebiet abschließend erfasst. Sonst ist die Präzision nur eine untere Schranke.

Lauf (`signaldesk-research-run/1`) – was SignalDesk gefunden hat, z. B. per `export_run()` aus einer Datenbank:
    {"format": "signaldesk-research-run/1", "system": "SignalDesk 2.0.0-dev57",
     "queries": [{"id": "q1", "candidates": [{"cand_id": "c1", "name": "...", "zip": "...", "city": "...",
                                               "website": "...", "register_id": "...", "lei": "..."}]}]}

Zuordnung Lauf ↔ Referenz über `identity.decide()` OHNE Website – sonst würde eine falsch zugeordnete Website die Zuordnung
selbst verfälschen. Die Website wird danach getrennt bewertet. Nur „sicher dieselbe Firma“ zählt als Treffer; „möglich“ wird
gezählt, aber nicht als Treffer gewertet.

Grundsatz: Dieses Modul rechnet nur. Ergebnisse gibt es erst mit einer Referenzliste echter Prüfer; synthetische Listen
(`"synthetic": true`) prüfen nur das Werkzeug, und der Bericht sagt das in der ersten Zeile.
Personendaten gehören nicht in die Dateien: unbekannte Felder (z. B. E-Mail, Ansprechpartner) werden abgelehnt.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import sqlite3

from . import identity

REF_FORMAT = 'signaldesk-research-reference/1'
RUN_FORMAT = 'signaldesk-research-run/1'
STATUSES = ('aktiv', 'geschlossen', 'ausser_bereich')
REF_FIELDS = {'ref_id', 'name', 'legal_form', 'street', 'zip', 'city', 'website', 'register_id', 'lei', 'status', 'evidence',
              'checked_by', 'checked_on', 'note'}
CAND_FIELDS = {'cand_id', 'name', 'legal_form', 'street', 'zip', 'city', 'website', 'register_id', 'lei', 'source', 'lead_id'}
QUERY_FIELDS = {'id', 'description', 'complete', 'method', 'area', 'industry', 'companies'}
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


# ---------------------------------------------------------------- Prüfen der Dateien

def _reviewers(entry):
    cb = entry.get('checked_by')
    if isinstance(cb, str):
        cb = [cb]
    return [c.strip() for c in (cb or []) if isinstance(c, str) and c.strip()]


def validate_reference(ref):
    """Gibt eine Liste von Fehlern zurück (leer = in Ordnung)."""
    errs = []
    if not isinstance(ref, dict) or ref.get('format') != REF_FORMAT:
        return [f'format muss "{REF_FORMAT}" sein']
    queries = ref.get('queries')
    if not isinstance(queries, list) or not queries:
        return ['queries fehlt oder ist leer']
    seen_q = set()
    for qi, q in enumerate(queries):
        where = f'queries[{qi}]'
        if not isinstance(q, dict):
            errs.append(f'{where}: kein Objekt')
            continue
        qid = q.get('id')
        if not isinstance(qid, str) or not qid:
            errs.append(f'{where}: id fehlt')
        elif qid in seen_q:
            errs.append(f'{where}: id "{qid}" doppelt')
        seen_q.add(qid)
        for k in sorted(set(q) - QUERY_FIELDS):
            errs.append(f'{where}: unbekanntes Feld "{k}"')
        if not isinstance(q.get('complete'), bool):
            errs.append(f'{where}: complete muss true oder false sein')
        comps = q.get('companies')
        if not isinstance(comps, list):
            errs.append(f'{where}: companies fehlt')
            continue
        seen_r = set()
        for ci, c in enumerate(comps):
            w = f'{where}.companies[{ci}]'
            if not isinstance(c, dict):
                errs.append(f'{w}: kein Objekt')
                continue
            for k in sorted(set(c) - REF_FIELDS):
                errs.append(f'{w}: unbekanntes Feld "{k}" (Personendaten gehören nicht in die Referenzliste)')
            rid = c.get('ref_id')
            if not isinstance(rid, str) or not rid:
                errs.append(f'{w}: ref_id fehlt')
            elif rid in seen_r:
                errs.append(f'{w}: ref_id "{rid}" doppelt')
            seen_r.add(rid)
            if not (c.get('name') or '').strip():
                errs.append(f'{w}: name fehlt')
            if c.get('status') not in STATUSES:
                errs.append(f'{w}: status muss einer von {", ".join(STATUSES)} sein')
            if not _reviewers(c):
                errs.append(f'{w}: checked_by fehlt (wer hat geprüft?)')
            if not _DATE.match(str(c.get('checked_on') or '')):
                errs.append(f'{w}: checked_on fehlt oder ist kein Datum JJJJ-MM-TT')
            ev = c.get('evidence')
            if not isinstance(ev, list) or not [e for e in ev if isinstance(e, str) and e.strip()]:
                errs.append(f'{w}: evidence fehlt (mindestens ein Beleg)')
            for key in ('website', 'register_id'):
                if key in c and c[key] is not None and not isinstance(c[key], str):
                    errs.append(f'{w}: {key} muss Text oder null sein')
    return errs


def validate_run(run):
    errs = []
    if not isinstance(run, dict) or run.get('format') != RUN_FORMAT:
        return [f'format muss "{RUN_FORMAT}" sein']
    queries = run.get('queries')
    if not isinstance(queries, list):
        return ['queries fehlt']
    for qi, q in enumerate(queries):
        if not isinstance(q, dict) or not isinstance(q.get('id'), str):
            errs.append(f'queries[{qi}]: id fehlt')
            continue
        cands = q.get('candidates')
        if not isinstance(cands, list):
            errs.append(f'queries[{qi}]: candidates fehlt')
            continue
        for ci, c in enumerate(cands):
            if not isinstance(c, dict) or not (c.get('name') or '').strip():
                errs.append(f'queries[{qi}].candidates[{ci}]: name fehlt')
                continue
            for k in sorted(set(c) - CAND_FIELDS):
                errs.append(f'queries[{qi}].candidates[{ci}]: unbekanntes Feld "{k}"')
    return errs


# ---------------------------------------------------------------- Rechnen

def wilson(k, n, z=1.96):
    """95-%-Vertrauensbereich (Wilson) für k Treffer aus n. None bei n = 0."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def _rate(k, n):
    return {'value': round(k / n, 3) if n else None, 'k': k, 'n': n, 'ci95': wilson(k, n)}


def _ident(item):
    """Für die Zuordnung: alles außer der Website."""
    return {'name': item.get('name') or '', 'legal_form': item.get('legal_form') or '', 'zip': item.get('zip') or '',
            'city': item.get('city') or '', 'register_id': item.get('register_id') or '', 'lei': item.get('lei') or ''}


def _match(refs, cands):
    """Eins-zu-eins-Zuordnung, beste Paare zuerst. Gibt (pairs, dup_cands, possible_cands, unmatched_cands) zurück."""
    scored, possible = [], set()
    for ci, c in enumerate(cands):
        for ri, r in enumerate(refs):
            verdict, score, reason = identity.decide(_ident(r), _ident(c))
            if verdict == 'same':
                scored.append((-score, ri, ci, reason))
            elif verdict == 'possible':
                possible.add(ci)
    scored.sort()
    used_r, used_c, pairs = set(), set(), []
    for neg, ri, ci, reason in scored:
        if ri in used_r or ci in used_c:
            continue
        used_r.add(ri)
        used_c.add(ci)
        pairs.append((ri, ci, reason))
    dup = sorted({ci for _, ri, ci, _ in scored if ci not in used_c and ri in used_r})
    rest = [ci for ci in range(len(cands)) if ci not in used_c and ci not in dup]
    poss = [ci for ci in rest if ci in possible]
    unmatched = [ci for ci in rest if ci not in possible]
    return pairs, dup, poss, unmatched


def _field_verdict(ref_val_present, ref_val, cand_val, norm):
    """'nicht_geprueft' | 'richtig' | 'falsch' | 'fehlt' | 'ueberfluessig' | 'richtig_leer'"""
    if not ref_val_present:
        return 'nicht_geprueft'
    rv, cv = norm(ref_val or ''), norm(cand_val or '')
    if ref_val is None or not rv:
        return 'ueberfluessig' if cv else 'richtig_leer'
    if not cv:
        return 'fehlt'
    return 'richtig' if rv == cv else 'falsch'


_FIELDS = (('website', identity.norm_domain), ('register_id', identity.norm_register))


def _blank_counts():
    return {'refs_in_scope': 0, 'refs_out_of_scope': 0, 'found': 0, 'true_pos': 0, 'false_pos_known': 0, 'duplicates': 0,
            'possible_only': 0, 'unmatched': 0, 'unmatched_judgeable': 0,
            'fields': {f: {k: 0 for k in ('richtig', 'falsch', 'fehlt', 'ueberfluessig', 'richtig_leer', 'nicht_geprueft')}
                       for f, _ in _FIELDS}}


def _add(total, part):
    for k, v in part.items():
        if k == 'fields':
            for f, d in v.items():
                for kk, vv in d.items():
                    total['fields'][f][kk] += vv
        else:
            total[k] += v


def _metrics(c, complete):
    m = {'recall': _rate(c['true_pos'], c['refs_in_scope'])}
    judged_fp = c['false_pos_known'] + c['duplicates'] + c['unmatched_judgeable']
    m['precision'] = _rate(c['true_pos'], c['true_pos'] + judged_fp)
    m['precision_kind'] = 'abschliessend' if complete else 'obere_schranke'
    # ohne abschließende Liste: im ungünstigsten Fall ist jeder nicht zugeordnete Kandidat falsch
    m['precision_lower_bound'] = _rate(c['true_pos'], c['found'])
    m['duplicate_rate'] = _rate(c['duplicates'], c['found'])
    for f, _ in _FIELDS:
        d = c['fields'][f]
        scored = d['richtig'] + d['falsch'] + d['fehlt'] + d['ueberfluessig'] + d['richtig_leer']
        given = d['richtig'] + d['falsch'] + d['ueberfluessig']
        m[f] = {'accuracy': _rate(d['richtig'] + d['richtig_leer'], scored),
                'wrong_assignment_rate': _rate(d['falsch'] + d['ueberfluessig'], given),
                'coverage': _rate(d['richtig'] + d['falsch'], d['richtig'] + d['falsch'] + d['fehlt'])}
    return m


def evaluate(ref, run):
    """Wertet einen Lauf gegen die Referenz aus. Wirft ValueError bei ungültigen Dateien."""
    errs = validate_reference(ref) + validate_run(run)
    if errs:
        raise ValueError('; '.join(errs[:10]) + (f' (und {len(errs) - 10} weitere)' if len(errs) > 10 else ''))
    run_by_id = {q['id']: q.get('candidates') or [] for q in run['queries']}
    total, per_query, details = _blank_counts(), [], []
    all_complete = True
    reviewers_2 = refs_n = 0
    for q in ref['queries']:
        refs = q['companies']
        cands = run_by_id.get(q['id'], [])
        complete = bool(q.get('complete'))
        all_complete = all_complete and complete
        pairs, dup, poss, unmatched = _match(refs, cands)
        c = _blank_counts()
        c['refs_in_scope'] = sum(1 for r in refs if r['status'] == 'aktiv')
        c['refs_out_of_scope'] = len(refs) - c['refs_in_scope']
        c['found'] = len(cands)
        c['duplicates'] = len(dup)
        c['possible_only'] = len(poss)
        c['unmatched'] = len(unmatched) + len(poss)
        c['unmatched_judgeable'] = c['unmatched'] if complete else 0
        rows = []
        for ri, ci, reason in pairs:
            r, cand = refs[ri], cands[ci]
            if r['status'] != 'aktiv':
                c['false_pos_known'] += 1
                rows.append({'ref_id': r['ref_id'], 'cand_id': cand.get('cand_id', str(ci)), 'result': 'falsch_' + r['status'], 'reason': reason})
                continue
            c['true_pos'] += 1
            row = {'ref_id': r['ref_id'], 'cand_id': cand.get('cand_id', str(ci)), 'result': 'treffer', 'reason': reason}
            for f, norm in _FIELDS:
                v = _field_verdict(f in r, r.get(f), cand.get(f), norm)
                c['fields'][f][v] += 1
                row[f] = v
            rows.append(row)
        matched_refs = {ri for ri, _, _ in pairs}
        for ri, r in enumerate(refs):
            refs_n += 1
            reviewers_2 += len(set(_reviewers(r))) >= 2
            if ri not in matched_refs and r['status'] == 'aktiv':
                rows.append({'ref_id': r['ref_id'], 'cand_id': '', 'result': 'nicht_gefunden'})
        for ci in dup:
            rows.append({'ref_id': '', 'cand_id': cands[ci].get('cand_id', str(ci)), 'result': 'dublette'})
        for ci in poss:
            rows.append({'ref_id': '', 'cand_id': cands[ci].get('cand_id', str(ci)), 'result': 'nur_moeglich'})
        for ci in unmatched:
            rows.append({'ref_id': '', 'cand_id': cands[ci].get('cand_id', str(ci)),
                         'result': 'falsch_gefunden' if complete else 'nicht_beurteilbar'})
        _add(total, c)
        per_query.append({'id': q['id'], 'description': q.get('description', ''), 'complete': complete, 'counts': c,
                          'metrics': _metrics(c, complete)})
        details.append({'id': q['id'], 'rows': rows})
    missing_runs = sorted(set(q['id'] for q in ref['queries']) - set(run_by_id))
    return {
        'reference': ref.get('name', ''), 'synthetic': bool(ref.get('synthetic')), 'system': run.get('system', ''),
        'match_engine': identity.engine(), 'evaluated_on': dt.date.today().isoformat(),
        'reviewer_coverage': {'entries': refs_n, 'two_or_more_reviewers': reviewers_2},
        'queries_without_run': missing_runs,
        'total': {'counts': total, 'metrics': _metrics(total, all_complete)},
        'queries': per_query, 'details': details,
    }


# ---------------------------------------------------------------- Bericht

def _pct(rate):
    if rate['value'] is None:
        return '–'
    ci = rate['ci95']
    value = f"{rate['value'] * 100:.1f}".replace('.', ',')
    return f"{value} % ({rate['k']}/{rate['n']}; 95 %: {ci[0] * 100:.0f}–{ci[1] * 100:.0f} %)"


def report_markdown(res):
    lines = []
    if res['synthetic']:
        lines += ['> **Synthetische Testdaten – kein Messergebnis.** Diese Auswertung prüft nur das Werkzeug.', '']
    lines += [f"# Recherche-Benchmark: {res['reference'] or 'ohne Namen'}", '',
              f"System: {res['system'] or 'unbekannt'} · Abgleich: {res['match_engine']} · ausgewertet am {res['evaluated_on']}", '',
              f"Referenzeinträge: {res['reviewer_coverage']['entries']}, davon von mindestens zwei Personen geprüft: "
              f"{res['reviewer_coverage']['two_or_more_reviewers']}", '']
    if res['queries_without_run']:
        lines += [f"Ohne Lauf (zählen mit 0 gefunden): {', '.join(res['queries_without_run'])}", '']
    t, m = res['total']['counts'], res['total']['metrics']
    prec_note = '' if m['precision_kind'] == 'abschliessend' else \
        ' – nicht abschließende Liste: obere Schranke, untere Schranke siehe nächste Zeile'
    lines += ['## Gesamt', '', '| Messgröße | Wert |', '|---|---|',
              f"| Vollständigkeit (Recall) | {_pct(m['recall'])} |",
              f"| Genauigkeit (Präzision){prec_note} | {_pct(m['precision'])} |",
              f"| Präzision, ungünstigster Fall | {_pct(m['precision_lower_bound'])} |",
              f"| Dubletten im Ergebnis | {_pct(m['duplicate_rate'])} |",
              f"| Website richtig (bei geprüften Treffern) | {_pct(m['website']['accuracy'])} |",
              f"| **Website falsch zugeordnet** | {_pct(m['website']['wrong_assignment_rate'])} |",
              f"| Registernummer richtig | {_pct(m['register_id']['accuracy'])} |",
              f"| Registernummer falsch zugeordnet | {_pct(m['register_id']['wrong_assignment_rate'])} |", '',
              f"Gefunden {t['found']} · Treffer {t['true_pos']} · sicher falsch (geschlossen/außerhalb) {t['false_pos_known']} · "
              f"Dubletten {t['duplicates']} · nur „möglich“ {t['possible_only']} · nicht zugeordnet {t['unmatched']}", '',
              '## Je Suche', '', '| Suche | abschließend | Recall | Präzision | Website falsch |', '|---|---|---|---|---|']
    for q in res['queries']:
        qm = q['metrics']
        lines.append(f"| {q['id']} {q['description']} | {'ja' if q['complete'] else 'nein'} | {_pct(qm['recall'])} | "
                     f"{_pct(qm['precision'])} | {_pct(qm['website']['wrong_assignment_rate'])} |")
    lines += ['', 'Treffer = sicher dieselbe Firma nach Name, Rechtsform, Ort, Register oder LEI (ohne Website). '
                  '„Nur möglich“ zählt nicht als Treffer.', '']
    return '\n'.join(lines)


# ---------------------------------------------------------------- Lauf aus einer SignalDesk-Datenbank

def export_run(db_path, query_id, system='', since='', lead_ids=None):
    """Firmen einer Datenbank als Lauf-Datei. Nur Firmendaten – keine Personen, keine Kontaktwege."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        cols = {r[1] for r in conn.execute('PRAGMA table_info(leads)')}
        want = [c for c in ('legal_name', 'legal_form', 'zip', 'city', 'register_number') if c in cols]
        sql = f"SELECT id, company, website, location{''.join(', ' + c for c in want)} FROM leads WHERE 1=1"
        args = []
        if since:
            sql += ' AND created_at >= ?'
            args.append(since)
        if lead_ids:
            sql += f" AND id IN ({','.join('?' * len(lead_ids))})"
            args += list(lead_ids)
        cands = []
        for row in conn.execute(sql + ' ORDER BY id', args):
            d = dict(zip(['id', 'company', 'website', 'location', *want], row))
            zip_code, city = (d.get('zip') or '').strip(), (d.get('city') or '').strip()
            if not (zip_code or city):
                m = re.match(r'^\s*(\d{5})?\s*(.*)$', d.get('location') or '')
                zip_code, city = (m.group(1) or ''), m.group(2).strip()
            reg = (d.get('register_number') or '').strip()
            cands.append({'cand_id': f"lead-{d['id']}", 'lead_id': d['id'], 'name': d.get('legal_name') or d['company'],
                          'legal_form': d.get('legal_form') or '', 'zip': zip_code, 'city': city,
                          'website': d.get('website') or '', 'register_id': reg})
    finally:
        conn.close()
    return {'format': RUN_FORMAT, 'system': system, 'created_at': dt.datetime.now().isoformat(timespec='seconds'),
            'queries': [{'id': query_id, 'candidates': cands}]}


# ---------------------------------------------------------------- Referenzliste aus einer Tabelle (Vorlage referenzliste-vorlage.xlsx)

# Spaltenkopf (Anfang, klein geschrieben) → Feld. Die Vorlage nennt die Spalten auf Deutsch.
TABLE_COLUMNS = (('suche', 'query'), ('ref', 'ref_id'), ('firmenname', 'name'), ('name', 'name'), ('rechtsform', 'legal_form'),
                 ('straße', 'street'), ('strasse', 'street'), ('plz', 'zip'), ('ort', 'city'), ('website', 'website'),
                 ('registernummer', 'register_id'), ('lei', 'lei'), ('status', 'status'), ('beleg', 'evidence'),
                 ('prüfer', 'checked_by'), ('pruefer', 'checked_by'), ('prüfdatum', 'checked_on'), ('pruefdatum', 'checked_on'),
                 ('notiz', 'note'))
NONE_WORDS = {'keine', 'kein', 'keine website', '-', 'null', 'none'}


def _column(header):
    h = str(header or '').strip().lower()
    for prefix, field in TABLE_COLUMNS:
        if h.startswith(prefix):
            return field
    return None


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime('%Y-%m-%d')
    return str(value).strip()


def reference_from_table(rows, queries=None, name=''):
    """Referenzliste aus Tabellenzeilen (erste Zeile = Spaltenköpfe). ``queries``: {id: {description, complete, method}}.

    Leere Website/Registernummer = nicht geprüft (Feld fehlt), „keine“ = geprüft und gibt es nicht (null).
    Unbekannte Spalten werden abgelehnt, damit keine Personendaten in die Liste rutschen."""
    rows = [list(r) for r in rows]
    if not rows:
        raise ValueError('Tabelle ist leer.')
    fields = [_column(h) for h in rows[0]]
    unknown = [str(h) for h, f in zip(rows[0], fields) if f is None and str(h or '').strip()]
    if unknown:
        raise ValueError('Unbekannte Spalten (Personendaten gehören nicht in die Liste): ' + ', '.join(unknown))
    queries = dict(queries or {})
    by_query = {}
    for n, row in enumerate(rows[1:], start=2):
        values = {}
        for field, raw in zip(fields, row):
            if field:
                values.setdefault(field, []).append(_cell(raw))
        if not any(v for vs in values.values() for v in vs):
            continue  # Leerzeile
        one = {k: next((v for v in vs if v), '') for k, vs in values.items()}
        if 'zeile löschen' in one.get('name', '').lower():
            raise ValueError(f'Zeile {n}: Beispielzeile der Vorlage bitte löschen.')
        qid = one.pop('query', '') or 'q1'
        entry = {'ref_id': one.get('ref_id') or f'z{n}'}
        for key in ('name', 'legal_form', 'street', 'zip', 'city', 'lei', 'note', 'status', 'checked_on'):
            if one.get(key):
                entry[key] = one[key]
        for key in ('website', 'register_id'):
            if one.get(key):
                entry[key] = None if one[key].lower() in NONE_WORDS else one[key]
        entry['evidence'] = [v for v in values.get('evidence', []) if v]
        entry['checked_by'] = [v for v in values.get('checked_by', []) if v]
        by_query.setdefault(qid, []).append(entry)
    out = []
    for qid in sorted(set(by_query) | set(queries)):
        meta = queries.get(qid, {})
        out.append({'id': qid, 'description': meta.get('description', ''), 'complete': bool(meta.get('complete', False)),
                    'method': meta.get('method', ''), 'companies': by_query.get(qid, [])})
    return {'format': REF_FORMAT, 'name': name or 'Referenzliste aus Tabelle', 'synthetic': False, 'queries': out}
