"""Tarif und Abrechnungsstand je Organisation – hinter einer Schnittstelle, ohne echten Zahlungsanbieter (SDQ-028).

Tabelle ``subscriptions`` im Verzeichnis, eine Zeile je Organisation:
``plan`` (Tarif), ``status`` (``test``, ``aktiv``, ``gekuendigt``, ``abgelaufen``), ``trial_ends`` (Ende der Testphase),
``paid_until`` (bezahlt bis, bei ``gekuendigt`` das Ende), ``provider`` (heute nur ``manuell``).

- Organisationen, die der Betreiber anlegt, haben keine Zeile und keine Einschränkung („vom Betreiber verwaltet“).
- Eine selbst registrierte Organisation beginnt mit ``test``. Läuft die Testphase ab (oder eine Kündigung), wird sie
  **nur lesbar**: Ansehen und Exportieren gehen weiter, Ändern nicht (HTTP 402). Daten werden nie gelöscht.
- Preise stehen hier bewusst nicht. Die Tarife und ihre Grenzen sind Platzhalter, bis die Preise festgelegt sind.
- ``ManuellProvider`` ist der einzige Anbieter: Der Betreiber setzt den Stand per Kommandozeile, nachdem eine Zahlung auf
  anderem Weg eingegangen ist. Ein echter Anbieter (z. B. Stripe) braucht eine eigene Klasse mit denselben Methoden und eine
  ausdrückliche Freigabe.
"""
from __future__ import annotations

import datetime as dt

from . import audit_trail

PLANS = {  # Grenzen sind Platzhalter; Preise legt der Betreiber fest (nicht im Code)
    'test': {'label': 'Testphase', 'members': 3},
    'solo': {'label': 'Solo', 'members': 1},
    'team': {'label': 'Team', 'members': 10},
}
STATUSES = ('test', 'aktiv', 'gekuendigt', 'abgelaufen')
DEFAULT_TRIAL_DAYS = 30
WRITE_ALLOWED = {('POST', '/api/auth/logout')}


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        slug TEXT PRIMARY KEY REFERENCES organizations(slug), plan TEXT NOT NULL, status TEXT NOT NULL,
        trial_ends TEXT NOT NULL DEFAULT '', paid_until TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT 'manuell',
        provider_ref TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT (datetime('now')))''')


def _today():
    return dt.date.today()


class ManuellProvider:
    """Kein Zahlungsverkehr: Der Betreiber trägt den Stand ein. Bezahlen im Browser gibt es mit diesem Anbieter nicht."""
    name = 'manuell'

    def checkout(self, slug, plan):
        raise PermissionError('Bezahlen im Browser ist noch nicht eingerichtet. Bitte an den Betreiber wenden.')

    def cancel(self, slug):
        raise PermissionError('Kündigen bitte beim Betreiber.')


def provider():
    return ManuellProvider()


def start_trial(directory, slug, days=None, actor=None):
    days = int(days or DEFAULT_TRIAL_DAYS)
    ends = (_today() + dt.timedelta(days=days)).isoformat()
    with directory._connect() as conn:
        init(conn)
        conn.execute("INSERT INTO subscriptions(slug, plan, status, trial_ends) VALUES (?, 'test', 'test', ?)", (slug, ends))
    audit_trail.record(directory, actor or audit_trail.operator(), 'testphase_begonnen', slug, f'bis {ends}')
    return state(directory, slug)


def state(directory, slug):
    """Stand der Organisation. ``read_only`` sagt, ob Änderungen gesperrt sind."""
    with directory._connect() as conn:
        init(conn)
        row = conn.execute('SELECT * FROM subscriptions WHERE slug=?', (slug,)).fetchone()
        members = conn.execute('SELECT COUNT(*) FROM memberships WHERE slug=?', (slug,)).fetchone()[0]
    if not row:
        return {'managed': True, 'plan': '', 'status': 'betreiber', 'read_only': False, 'members': members,
                'members_limit': None, 'notice': 'Vom Betreiber verwaltet.'}
    today = _today().isoformat()
    status = row['status']
    if status == 'test' and row['trial_ends'] and row['trial_ends'] < today:
        status = 'abgelaufen'
    if status == 'gekuendigt' and (not row['paid_until'] or row['paid_until'] < today):
        status = 'abgelaufen'
    if status == 'aktiv' and row['paid_until'] and row['paid_until'] < today:
        status = 'abgelaufen'
    days_left = None
    if status == 'test' and row['trial_ends']:
        days_left = (dt.date.fromisoformat(row['trial_ends']) - _today()).days
    plan = PLANS.get(row['plan'], {'label': row['plan'], 'members': None})
    notice = {'test': f'Testphase bis {row["trial_ends"]}.', 'aktiv': 'Tarif aktiv.',
              'gekuendigt': f'Gekündigt zum {row["paid_until"]}.',
              'abgelaufen': 'Abgelaufen: Ansehen und Export sind möglich, Änderungen nicht. Bitte an den Betreiber wenden.'}[status]
    return {'managed': False, 'plan': row['plan'], 'plan_label': plan['label'], 'status': status, 'stored_status': row['status'],
            'trial_ends': row['trial_ends'], 'paid_until': row['paid_until'], 'days_left': days_left,
            'read_only': status == 'abgelaufen', 'members': members, 'members_limit': plan['members'],
            'provider': row['provider'], 'notice': notice}


def set_subscription(directory, slug, plan=None, status=None, paid_until=None, actor=None):
    """Stand von Hand setzen (Betreiber, Anbieter ``manuell``)."""
    directory.get(slug)
    if plan is not None and plan not in PLANS:
        raise ValueError('Tarif: ' + ', '.join(PLANS))
    if status is not None and status not in STATUSES:
        raise ValueError('Status: ' + ', '.join(STATUSES))
    if paid_until:
        dt.date.fromisoformat(paid_until)
    with directory._connect() as conn:
        init(conn)
        row = conn.execute('SELECT * FROM subscriptions WHERE slug=?', (slug,)).fetchone()
        if not row:
            conn.execute("INSERT INTO subscriptions(slug, plan, status) VALUES (?,?,?)", (slug, plan or 'team', status or 'aktiv'))
        conn.execute('''UPDATE subscriptions SET plan=COALESCE(?, plan), status=COALESCE(?, status),
                        paid_until=COALESCE(?, paid_until), updated_at=datetime('now') WHERE slug=?''',
                     (plan, status, paid_until, slug))
    audit_trail.record(directory, actor or audit_trail.operator(), 'tarif_gesetzt', slug,
                       ' '.join(f'{k}={v}' for k, v in (('plan', plan), ('status', status), ('bis', paid_until)) if v))
    return state(directory, slug)


def check_member_limit(directory, slug, adding=1):
    s = state(directory, slug)
    if s['members_limit'] is not None and s['members'] + adding > s['members_limit']:
        raise PermissionError(f"Tarif {s['plan_label']}: höchstens {s['members_limit']} Mitglieder.")
    return s


def blocks(directory, slug, method, route):
    """True, wenn diese Anfrage wegen des Abrechnungsstands nicht ausgeführt werden darf (nur lesbar)."""
    if method in ('GET', 'HEAD') or (method, route) in WRITE_ALLOWED:
        return None
    s = state(directory, slug)
    return s if s['read_only'] else None
