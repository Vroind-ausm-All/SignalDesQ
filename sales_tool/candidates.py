"""Kandidaten-Sichtung getrennt vom CRM (Plan R2.4).

Ein Personen-Kandidat ist ein Rechercheergebnis, kein Kontakt. Er gelangt nur durch eine menschliche Freigabe
(``review(..., 'accept')``) nach ``decision_contacts``. Jeder Weg, der Kandidaten anlegt, läuft über ``store``:

- Sperre: keine Kandidaten für gesperrte Firmen (``workday.contact_lock`` – Phase, Widerspruch und Sperrliste) und keine
  Kandidaten mit gesperrter E-Mail-Adresse. Wird eine Firma später gesperrt, löscht ``purge_locked`` ihre Kandidaten.
- Beleg: Name und Funktion brauchen je einen Beleg v2 mit Fundstelle (``research.evidence.check_ref``), sonst verworfen.
- Arbeitgeber: nennt die Quelle ausdrücklich einen anderen Arbeitgeber als die Firma, ist der Kandidat „widersprüchlich“.
- TTL: Kandidaten laufen nach einer Frist ab (Vorgabe 180 Tage, Einstellung ``candidate_ttl_days``) und werden gelöscht.

Status: kandidat, bestaetigt, widerspruechlich, historisch, verworfen.
Export: Kandidaten liegen in der Datenbank der Organisation und sind damit im Organisations-Export enthalten (data_map).
"""
from __future__ import annotations

import datetime as dt
import json

STATUSES = ('kandidat', 'bestaetigt', 'widerspruechlich', 'historisch', 'verworfen')
LEGACY = {'ungeprueft': 'kandidat', 'freigegeben': 'bestaetigt', 'abgelehnt': 'verworfen'}
OPEN = ('kandidat', 'widerspruechlich')
REQUIRED_REFS = ('full_name', 'job_title')
DEFAULT_TTL_DAYS = 180
COLUMNS = (
    ('role_key', "TEXT DEFAULT ''"), ('department', "TEXT DEFAULT ''"), ('method', "TEXT DEFAULT ''"),
    ('employer', "TEXT DEFAULT ''"), ('evidence_json', "TEXT DEFAULT '{}'"), ('status_reason', "TEXT DEFAULT ''"),
    ('created_at', "TEXT DEFAULT ''"), ('expires_at', "TEXT DEFAULT ''"), ('reviewed_at', "TEXT DEFAULT ''"),
)


def init_candidates(conn):
    """Nicht zerstörende Migration: Spalten ergänzen, alte Status abbilden, Frist für Bestand setzen."""
    have = {r[1] for r in conn.execute('PRAGMA table_info(contact_candidates)')}
    for name, sql in COLUMNS:
        if name not in have:
            conn.execute(f'ALTER TABLE contact_candidates ADD COLUMN {name} {sql}')
    dc = {r[1] for r in conn.execute('PRAGMA table_info(decision_contacts)')}
    if 'evidence_json' not in dc:
        conn.execute("ALTER TABLE decision_contacts ADD COLUMN evidence_json TEXT DEFAULT '{}'")
    for old, new in LEGACY.items():
        conn.execute('UPDATE contact_candidates SET status=? WHERE status=?', (new, old))
    conn.execute("UPDATE contact_candidates SET status='kandidat' WHERE status IS NULL OR status=''")
    conn.execute("UPDATE contact_candidates SET created_at=datetime('now') WHERE created_at IS NULL OR created_at=''")
    conn.execute("UPDATE contact_candidates SET expires_at=datetime(created_at, ?) WHERE expires_at IS NULL OR expires_at=''",
                 (f'+{ttl_days(conn)} days',))
    conn.execute('CREATE INDEX IF NOT EXISTS idx_contact_candidates_lead ON contact_candidates(lead_id, status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_contact_candidates_expiry ON contact_candidates(expires_at)')


def ttl_days(conn):
    try:
        row = conn.execute("SELECT value_json FROM app_settings WHERE key='candidate_ttl_days'").fetchone()
        days = int(json.loads(row[0])) if row else DEFAULT_TTL_DAYS
    except Exception:  # noqa: BLE001 – Einstellungstabelle fehlt (frühe Migration) oder Wert kaputt
        days = DEFAULT_TTL_DAYS
    return days if 30 <= days <= 730 else DEFAULT_TTL_DAYS


def set_ttl_days(conn, days):
    if not isinstance(days, int) or isinstance(days, bool) or not 30 <= days <= 730:
        raise ValueError('Frist für Kandidaten: 30–730 Tage.')
    conn.execute("INSERT INTO app_settings(key, value_json) VALUES ('candidate_ttl_days', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json", (json.dumps(days),))
    return days


def _norm_name(name):
    from .company_data import normalize_name
    return normalize_name(name)


def employer_conflict(lead, employer):
    """Nennt die Quelle einen anderen Arbeitgeber als die Firma (Name/Rechtsträger)? Leerer Arbeitgeber ist kein Konflikt."""
    e = _norm_name(employer)
    if not e:
        return False
    for name in (lead['company'], lead['legal_name'] if 'legal_name' in lead.keys() else ''):
        n = _norm_name(name)
        if n and (n in e or e in n):
            return False
    return True


def lock_reason(conn, lead, email=''):
    from .company_data import check_suppressed
    from .workday import contact_lock
    reason = contact_lock(conn, lead)
    if not reason and email and check_suppressed(conn, email=email):
        reason = 'E-Mail-Adresse auf der Sperrliste'
    return reason


def evidence_problems(person):
    from .research.evidence import check_ref
    refs = person.get('evidence_refs') or {}
    out = []
    for name in REQUIRED_REFS:
        errs = check_ref(refs.get(name))
        if errs:
            out.append(f'{name}: {", ".join(errs)}')
    return out


def store(conn, run_id, lead_id, person):
    """Einziger Weg, einen Kandidaten anzulegen. → (id | None, Grund). Legt nie einen CRM-Kontakt an."""
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        return None, 'Firma nicht gefunden'
    reason = lock_reason(conn, lead, person.get('business_email', ''))
    if reason:
        return None, f'gesperrt: {reason}'
    problems = evidence_problems(person)
    if problems:
        return None, 'ohne Fundstelle: ' + '; '.join(problems)
    name = person['full_name']
    if conn.execute('''SELECT 1 FROM decision_contacts WHERE lead_id=? AND lower(full_name)=lower(?)
                       UNION SELECT 1 FROM contact_candidates WHERE lead_id=? AND lower(full_name)=lower(?)''',
                    (lead_id, name, lead_id, name)).fetchone():
        return None, 'bereits bekannt'
    status, why = 'kandidat', ''
    if employer_conflict(lead, person.get('employer', '')):
        status, why = 'widerspruechlich', f"Quelle nennt anderen Arbeitgeber: {person['employer'][:120]}"
    evidence = {'refs': person.get('evidence_refs') or {}, 'group': person.get('locator_group') or {}, 'method': person.get('method', '')}
    cur = conn.execute('''INSERT INTO contact_candidates (run_id, lead_id, full_name, job_title, role_hint, priority, business_email,
                          business_phone, phone_type, source_url, evidence, status, role_key, department, method, employer, evidence_json,
                          status_reason, created_at, expires_at)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now',?))''',
                       (run_id, lead_id, name, person.get('job_title', ''), person.get('role_hint', ''), int(person.get('priority') or 0),
                        person.get('business_email', ''), person.get('business_phone', ''), person.get('phone_type', ''),
                        person.get('source_url', ''), str(person.get('evidence', ''))[:350], status, person.get('role_key', ''),
                        person.get('department', ''), person.get('method', ''), person.get('employer', '')[:200],
                        json.dumps(evidence, ensure_ascii=False), why, f'+{ttl_days(conn)} days'))
    return cur.lastrowid, status


def store_all(conn, run_id, lead_id, people):
    """→ {'stored': n, 'skipped': {grund: anzahl}}"""
    stored, skipped = 0, {}
    for p in people:
        cid, why = store(conn, run_id, lead_id, p)
        if cid:
            stored += 1
        else:
            key = why.split(':')[0]
            skipped[key] = skipped.get(key, 0) + 1
    return {'stored': stored, 'skipped': skipped}


DECISIONS = {'accept': 'bestaetigt', 'reject': 'verworfen', 'historic': 'historisch'}


def review(conn, candidate_id, decision, confirm_conflict=False):
    """Menschliche Sichtung. Nur ``accept`` legt einen CRM-Kontakt an – mit Beleg, ohne Entscheidungsbefugnis."""
    if decision not in DECISIONS:
        raise ValueError('Entscheidung muss accept, reject oder historic sein.')
    r = conn.execute('SELECT * FROM contact_candidates WHERE id=?', (candidate_id,)).fetchone()
    if not r:
        raise ValueError('Recherchekandidat nicht gefunden.')
    if LEGACY.get(r['status'], r['status']) not in OPEN:  # ältere Datenbank: Spaltenvorgabe noch „ungeprueft“
        raise ValueError('Dieser Recherchekandidat wurde bereits bearbeitet.')
    lead = conn.execute('SELECT * FROM leads WHERE id=?', (r['lead_id'],)).fetchone()
    reason = lock_reason(conn, lead, r['business_email']) if lead else 'Firma fehlt'
    if decision == 'accept':
        if reason:
            raise ValueError(f'Diese Firma ist gesperrt ({reason}). Keine Übernahme möglich.')
        if r['status'] == 'widerspruechlich' and confirm_conflict is not True:
            raise ValueError('Widersprüchlicher Kandidat: erst den Arbeitgeber an der Quelle prüfen und ausdrücklich bestätigen.')
        evidence = json.loads(r['evidence_json'] or '{}')
        if evidence_problems({'evidence_refs': evidence.get('refs')}):
            raise ValueError('Beleg ohne Fundstelle (ältere Recherche) – bitte die Firma erneut recherchieren; keine Übernahme ohne Beleg.')
        if conn.execute('SELECT id FROM decision_contacts WHERE lead_id=? AND lower(full_name)=lower(?)', (r['lead_id'], r['full_name'])).fetchone():
            raise ValueError('Diese Person ist bereits im CRM vorhanden. Keine Dublette angelegt.')
        quote = r['evidence'][:300]
        conn.execute('''INSERT INTO decision_contacts (lead_id, full_name, job_title, decision_role, source_url, note, business_phone, phone_type,
                        data_provider, business_email, source_excerpt, evidence_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                     (r['lead_id'], r['full_name'], r['job_title'], 'unbekannt', r['source_url'],
                      'Quelle manuell freigegeben; Entscheidungsbefugnis noch nicht bestätigt. ' + quote,
                      r['business_phone'], r['phone_type'], 'eigene_recherche', r['business_email'], quote, r['evidence_json']))
    status = DECISIONS[decision]
    conn.execute("UPDATE contact_candidates SET status=?, reviewed_at=datetime('now') WHERE id=?", (status, candidate_id))
    return {'status': status}


def purge_expired(conn, now=None):
    """Abgelaufene Kandidaten löschen (TTL). Bestätigte stehen dann nur noch im CRM."""
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime('%Y-%m-%d %H:%M:%S')
    n = conn.execute("DELETE FROM contact_candidates WHERE expires_at<>'' AND expires_at < ?", (stamp,)).rowcount
    if n:
        _audit(conn, None, 'kandidaten_abgelaufen', f'{n} Kandidat(en) nach Ablauf der Frist gelöscht')
    return n


def purge_lead(conn, lead_id, why='Sperre'):
    n = conn.execute('DELETE FROM contact_candidates WHERE lead_id=?', (lead_id,)).rowcount
    if n:
        _audit(conn, lead_id, 'kandidaten_geloescht', f'{n} Kandidat(en) gelöscht: {why}')
    return n


def purge_locked(conn):
    """Nach einer neuen Sperre: Kandidaten gesperrter Firmen und gesperrter E-Mail-Adressen löschen."""
    from .company_data import check_suppressed
    removed = 0
    for lid in [r[0] for r in conn.execute('SELECT DISTINCT lead_id FROM contact_candidates')]:
        lead = conn.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
        if lead is not None and lock_reason(conn, lead):
            removed += purge_lead(conn, lid)
    for r in conn.execute("SELECT id, business_email FROM contact_candidates WHERE business_email<>''").fetchall():
        if check_suppressed(conn, email=r['business_email']):
            removed += conn.execute('DELETE FROM contact_candidates WHERE id=?', (r['id'],)).rowcount
    return removed


def purge_person(conn, lead_id, full_name):
    """Löschung einer Person (z. B. abgelaufene Löschfrist eines CRM-Kontakts) erreicht auch ihre Kandidaten-Einträge."""
    return conn.execute('DELETE FROM contact_candidates WHERE lead_id=? AND lower(full_name)=lower(?)', (lead_id, full_name)).rowcount


def view_row(row):
    d = dict(row)
    try:
        ev = json.loads(d.pop('evidence_json', '') or '{}')
    except ValueError:
        ev = {}
    refs = ev.get('refs') or {}
    d['evidence_v2'] = not evidence_problems({'evidence_refs': refs})
    d['evidence_fields'] = sorted(refs)
    d['locator'] = {k: (v.get('locator') or {}) for k, v in refs.items() if isinstance(v, dict)}
    return d


def _audit(conn, lead_id, action, detail):
    from .company_data import _audit as audit
    audit(conn, 'candidates', lead_id, action, detail)
