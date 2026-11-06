"""Dubletten bei Leads erkennen und sicher zusammenführen (Masterplan 2.0, Sprint 4 – SignalDesk v1.17).

Grundsätze:
- Erkennen ist automatisch, Zusammenführen im CRM nie: Leads werden nur auf ausdrücklichen Klick zusammengeführt
  (keine ungewollten CRM-Änderungen). „Keine Dublette“ wird gespeichert und nicht wieder vorgeschlagen.
- Gleichheit nach `research.identity`: LEI/Registernummer, eigene Domain, Name + Rechtsform + Ort.
  Verschiedene Rechtsform, Registernummer oder Orte schließen eine Dublette aus (GmbH ≠ GmbH & Co. KG).
- Beim Zusammenführen bleibt nichts verloren: Aktivitäten, Aufgaben, Belege, Berichte, Signale … wandern zum
  behaltenen Lead; leere Felder werden ergänzt, nie überschrieben. Festgeschriebene Rechnungen sind unveränderbar –
  ein Lead mit Rechnungen kann daher nur der behaltene sein.
"""
from __future__ import annotations

import re

from .research import identity as ident

LEAD_FIELDS = ('company', 'legal_name', 'legal_form', 'website', 'register_court', 'register_number', 'zip', 'city', 'location')
FILL_FIELDS = ('website', 'location', 'contact_name', 'contact_role', 'industry', 'signal_source', 'signal_note', 'legal_name', 'legal_form',
               'street', 'zip', 'city', 'register_court', 'register_number', 'vat_id', 'business_phone', 'business_email', 'imprint_url',
               'imprint_checked_at', 'permission_evidence', 'next_step', 'next_date', 'signal_date')
# Spalten außerhalb von „lead_id“, die auf Leads zeigen
EXTRA_REFS = (('discovery_candidates', 'duplicate_lead_id'), ('discovery_candidates', 'possible_lead_id'), ('batch_items', 'duplicate_lead_id'))
NO_MOVE = {'leads', 'invoices', 'audit_log', 'einvoice_documents'}


def init_duplicates(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS lead_not_duplicate (a INTEGER NOT NULL, b INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (a, b))''')


def lead_item(r, name=None):
    """Lead-Zeile → Vergleichsdatensatz für identity.decide."""
    loc = (r['location'] or '').strip()
    zip_ = r['zip'] or (re.search(r'\b\d{5}\b', loc).group(0) if re.search(r'\b\d{5}\b', loc) else '')
    city = r['city'] or re.sub(r'^\d{5}\s*', '', loc).strip()
    return {'name': name or r['legal_name'] or r['company'], 'register_id': r['register_number'], 'website': r['website'],
            'zip': zip_, 'city': city, 'legal_form': r['legal_form'], 'lei': ''}


def _names(r):
    out = [r['legal_name'] or r['company']]
    if r['company'] and r['company'] != out[0]:
        out.append(r['company'])
    return [n for n in out if n]


def _variants(tok):
    out = {tok}
    for a, b in (('ae', 'ä'), ('oe', 'ö'), ('ue', 'ü'), ('ss', 'ß')):
        out |= {x.replace(a, b) for x in out}
    return out


def _prefilter(conn, item, exclude_id=None, limit=500):
    """Nur plausible Leads laden (Domain, Registernummer, markante Namenswörter) – statt jeden Lead zu vergleichen."""
    conds, args = [], []
    dom = ident.norm_domain(item.get('website'))
    if dom:
        conds.append('lower(website) LIKE ?')
        args.append(f'%{dom}%')
    reg = ident.norm_register(item.get('register_id'))
    if reg:
        conds.append("replace(upper(register_number),' ','') LIKE ?")
        args.append(f'%{reg}%')
    toks = ident.core_tokens(item.get('name'))
    for tok in {toks[0], max(toks, key=len)} if toks else ():
        for v in _variants(tok[:14]):
            conds.append('(company LIKE ? OR legal_name LIKE ?)')
            args += [f'%{v}%'] * 2
    if not conds:
        return []
    sql = f"SELECT * FROM leads WHERE ({' OR '.join(conds)})" + (' AND id<>?' if exclude_id else '') + f' LIMIT {int(limit)}'
    return conn.execute(sql, (*args, *([exclude_id] if exclude_id else []))).fetchall()


def find_lead(conn, item, exclude_id=None):
    """Bester Lead zu einem Datensatz: (lead_id, 'same'|'possible', score, reason) oder None."""
    best = None
    for r in _prefilter(conn, item, exclude_id):
        for nm in _names(r):
            verdict, score, reason = ident.decide(item, lead_item(r, nm))
            if verdict == 'different':
                continue
            rank = (verdict == 'same', score)
            if best is None or rank > (best[1] == 'same', best[2]):
                best = (r['id'], verdict, score, reason)
    return best


def _not_dup_pairs(conn):
    return {(r['a'], r['b']) for r in conn.execute('SELECT a, b FROM lead_not_duplicate')}


def _pair(a, b):
    return (a, b) if a < b else (b, a)


def _summary(r):
    return {'id': r['id'], 'company': r['company'], 'legal_name': r['legal_name'], 'legal_form': r['legal_form'], 'website': r['website'],
            'location': r['location'] or ' '.join(x for x in (r['zip'], r['city']) if x), 'register_number': r['register_number'],
            'stage': r['stage'], 'created_at': r['created_at']}


def lead_duplicates(conn, limit=200):
    """Alle vermuteten Dubletten im CRM (je Lead der beste ältere Treffer). Ändert nichts."""
    idx, rows, pairs = ident.Index(), {}, []
    skip = _not_dup_pairs(conn)
    for r in conn.execute('SELECT * FROM leads ORDER BY id'):
        rows[r['id']] = r
        best = None
        for nm in _names(r):
            item = lead_item(r, nm)
            excl = {k for k in idx.items if _pair(int(str(k).split(':')[0]), r['id']) in skip}
            hit = idx.best(item, exclude=excl)
            if hit and (best is None or (hit[0] == 'same', hit[2]) > (best[0] == 'same', best[2])):
                best = hit
        if best:
            other = int(str(best[1]).split(':')[0])
            pairs.append({'keep': _summary(rows[other]), 'drop': _summary(r), 'verdict': best[0], 'score': best[2], 'reason': best[3],
                          'invoices': {str(other): _invoice_count(conn, other), str(r['id']): _invoice_count(conn, r['id'])}})
        for i, nm in enumerate(_names(r)):
            idx.add(r['id'] if i == 0 else f"{r['id']}:{i}", lead_item(r, nm))
    pairs.sort(key=lambda p: (p['verdict'] != 'same', -p['score']))
    return {'pairs': pairs[:limit], 'total': len(pairs), 'same': sum(p['verdict'] == 'same' for p in pairs),
            'engine': ident.engine(),
            'notice': 'Vorschläge – nichts wird automatisch zusammengeführt. Rechnungen bleiben beim Lead, der sie hat.'}


def _invoice_count(conn, lead_id):
    return conn.execute('SELECT COUNT(*) FROM invoices WHERE lead_id=?', (lead_id,)).fetchone()[0]


def _ref_tables(conn):
    out = []
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t in NO_MOVE or t.startswith('sqlite_'):
            continue
        if any(r[1] == 'lead_id' for r in conn.execute(f'PRAGMA table_info("{t}")')):
            out.append((t, 'lead_id'))
    return out + [x for x in EXTRA_REFS if any(r[1] == x[1] for r in conn.execute(f'PRAGMA table_info("{x[0]}")'))]


def merge_leads(conn, keep, drop):
    """Führt Lead `drop` in `keep` zusammen. Gibt eine Zusammenfassung zurück. Nur auf ausdrücklichen Wunsch aufrufen."""
    from .company_data import _audit
    for v in (keep, drop):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError('keep/drop müssen Lead-IDs sein.')
    if keep == drop:
        raise ValueError('Ein Lead kann nicht mit sich selbst zusammengeführt werden.')
    k = conn.execute('SELECT * FROM leads WHERE id=?', (keep,)).fetchone()
    d = conn.execute('SELECT * FROM leads WHERE id=?', (drop,)).fetchone()
    if not k or not d:
        raise LookupError('Lead nicht gefunden.')
    inv_k, inv_d = _invoice_count(conn, keep), _invoice_count(conn, drop)
    if inv_d and inv_k:
        raise ValueError('Beide Leads haben Rechnungen – festgeschriebene Rechnungen sind unveränderbar, daher kein Zusammenführen.')
    if inv_d:
        raise ValueError(f'Lead #{drop} hat Rechnungen und muss erhalten bleiben – bitte umgekehrt zusammenführen (#{drop} behalten).')
    verdict, score, reason = ident.decide(lead_item(k), lead_item(d))
    moved = {}
    try:
        conn.execute('SAVEPOINT merge_leads')
        for table, col in _ref_tables(conn):
            n = conn.execute(f'UPDATE OR IGNORE "{table}" SET "{col}"=? WHERE "{col}"=?', (keep, drop)).rowcount
            if col == 'lead_id':  # Reste wegen Eindeutigkeit (z. B. eine Bewertung je Lead) – die des behaltenen Leads gilt
                conn.execute(f'DELETE FROM "{table}" WHERE lead_id=?', (drop,))
            if n:
                moved[table] = moved.get(table, 0) + n
        upd = {f: d[f] for f in FILL_FIELDS if not k[f] and d[f]}
        if (d['employees'] or 0) > (k['employees'] or 0):
            upd['employees'] = d['employees']
        note = (k['note'] or '') + (f"\n\n[Zusammengeführt aus #{drop} {d['company']}]\n{d['note']}" if d['note'] else '')
        upd['note'] = note.strip()[:8000]
        conn.execute(f"UPDATE leads SET {', '.join(f + '=?' for f in upd)}, updated_at=datetime('now') WHERE id=?", (*upd.values(), keep))
        conn.execute('DELETE FROM leads WHERE id=?', (drop,))
        conn.execute('DELETE FROM lead_not_duplicate WHERE a=? OR b=?', (drop, drop))
        detail = (f"Lead #{drop} „{d['company']}“ hierher zusammengeführt ({reason}). Übernommen: "
                  + (', '.join(f'{v} {t}' for t, v in sorted(moved.items())) or 'keine verknüpften Daten')
                  + (f"; ergänzte Felder: {', '.join(f for f in upd if f != 'note')}" if len(upd) > 1 else ''))
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)', (keep, 'notiz', detail[:900]))
        _audit(conn, 'lead', keep, 'zusammengefuehrt', {'drop': drop, 'drop_company': d['company'], 'verdict': verdict, 'reason': reason, 'moved': moved})
        conn.execute('RELEASE merge_leads')
    except Exception:
        conn.execute('ROLLBACK TO merge_leads')
        conn.execute('RELEASE merge_leads')
        raise
    conn.commit()
    return {'keep': keep, 'dropped': drop, 'moved': moved, 'filled': [f for f in upd if f != 'note'], 'verdict': verdict, 'reason': reason}


def mark_not_duplicate(conn, a, b):
    for v in (a, b):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError('IDs müssen Zahlen sein.')
    if a == b:
        raise ValueError('Zwei verschiedene Leads angeben.')
    if conn.execute('SELECT COUNT(*) FROM leads WHERE id IN (?,?)', (a, b)).fetchone()[0] != 2:
        raise LookupError('Lead nicht gefunden.')
    conn.execute('INSERT OR IGNORE INTO lead_not_duplicate(a, b) VALUES (?,?)', _pair(a, b))
    conn.commit()
    return {'ok': True}


def route_duplicates(h, conn, method, route, query):
    if route == '/api/leads/duplicates' and method == 'GET':
        h._send(200, lead_duplicates(conn))
        return True
    if route == '/api/leads/merge' and method == 'POST':
        b = h._body()
        if set(b) != {'keep', 'drop'}:
            raise ValueError('Erwartet: {keep, drop}.')
        h._send(200, merge_leads(conn, b['keep'], b['drop']))
        return True
    if route == '/api/leads/not-duplicate' and method == 'POST':
        b = h._body()
        if set(b) != {'a', 'b'}:
            raise ValueError('Erwartet: {a, b}.')
        h._send(200, mark_not_duplicate(conn, b['a'], b['b']))
        return True
    return False
