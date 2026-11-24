"""Tabellenregister (SDQ-010): Jede Tabelle der Datenbank ist hier eingeordnet.

Wozu: Mandantenfähigkeit, Datenschutz und Aufbewahrung brauchen eine vollständige Antwort auf „welche Daten liegen wo“.
Ein Test hält das Register vollständig: Legt ein Modul eine neue Tabelle an, ohne sie hier einzutragen, wird die Suite rot.

Felder je Tabelle:
- ``scope``: ``organisation`` – gehört einer Organisation (Kunden, Angebote, Rechnungen, Recherche);
  ``installation`` – aus öffentlichen Quellen abgeleitete Nachschlagedaten, die mehrere Organisationen teilen könnten;
  ``zugang`` – Anmeldung (Nutzer, Sitzungen).
- ``area``: fachlicher Bereich, für Übersicht und Export.
- ``personal``: Die Tabelle hat Spalten, die für Angaben zu Personen gedacht sind (Name, persönliche Kontaktwege).
  Freitextfelder (Notizen) können überall Personenbezug enthalten; das ist hier nicht gesondert markiert.
- ``retention``: ``gobd`` – steuerlich aufbewahrungspflichtig (§ 147 AO, bis zu 10 Jahre), darf nicht vorzeitig gelöscht werden;
  ``fachlich`` – löschbar nach fachlicher Regel; ``kurz`` – technischer Zwischenstand (Aufträge, Zwischenspeicher).
"""
from __future__ import annotations

from dataclasses import dataclass

SCOPES = ('organisation', 'installation', 'zugang')
RETENTION = ('gobd', 'fachlich', 'kurz')


@dataclass(frozen=True)
class Table:
    name: str
    scope: str
    area: str
    personal: bool
    retention: str


# name | scope | Bereich | Personen | Aufbewahrung
_REGISTER = """
leads                 | organisation | Firmen und Kontakt     | ja   | fachlich
activities            | organisation | Firmen und Kontakt     | nein | fachlich
action_dismissals     | organisation | Firmen und Kontakt     | nein | kurz
calls                 | organisation | Firmen und Kontakt     | nein | fachlich
tasks                 | organisation | Firmen und Kontakt     | nein | fachlich
meetings              | organisation | Firmen und Kontakt     | nein | fachlich
inbound               | organisation | Firmen und Kontakt     | ja   | fachlich
mail_drafts           | organisation | Firmen und Kontakt     | nein | fachlich
message_templates     | organisation | Firmen und Kontakt     | nein | fachlich
decision_contacts     | organisation | Firmen und Kontakt     | ja   | fachlich
contact_candidates    | organisation | Firmen und Kontakt     | ja   | fachlich
contact_research_runs | organisation | Firmen und Kontakt     | nein | kurz
privacy_records       | organisation | Firmen und Kontakt     | ja   | fachlich
suppression_list      | organisation | Firmen und Kontakt     | ja   | fachlich
lead_not_duplicate    | organisation | Firmen und Kontakt     | nein | fachlich
day_closings          | organisation | Firmen und Kontakt     | nein | fachlich
caldav_busy           | organisation | Firmen und Kontakt     | nein | kurz
caldav_sync           | organisation | Firmen und Kontakt     | nein | kurz
opportunities         | organisation | Bedarf und Chancen     | nein | fachlich
discovery             | organisation | Bedarf und Chancen     | nein | fachlich
briefing_answers      | organisation | Bedarf und Chancen     | nein | fachlich
offer_recommendations | organisation | Bedarf und Chancen     | nein | fachlich
proposals             | organisation | Angebote und Projekte  | ja   | fachlich
kickoffs              | organisation | Angebote und Projekte  | nein | fachlich
kickoff_items         | organisation | Angebote und Projekte  | ja   | fachlich
handovers             | organisation | Angebote und Projekte  | ja   | fachlich
handover_items        | organisation | Angebote und Projekte  | nein | fachlich
project_closings      | organisation | Angebote und Projekte  | nein | fachlich
time_entries          | organisation | Angebote und Projekte  | nein | fachlich
care_contracts        | organisation | Angebote und Projekte  | nein | fachlich
customer_reports      | organisation | Angebote und Projekte  | nein | fachlich
invoices              | organisation | Rechnung und Steuer    | ja   | gobd
invoice_lines         | organisation | Rechnung und Steuer    | nein | gobd
payments              | organisation | Rechnung und Steuer    | nein | gobd
dunning_notices       | organisation | Rechnung und Steuer    | nein | gobd
expenses              | organisation | Rechnung und Steuer    | nein | gobd
einvoice_documents    | organisation | Rechnung und Steuer    | nein | gobd
number_sequences      | organisation | Rechnung und Steuer    | nein | gobd
company_settings      | organisation | Rechnung und Steuer    | ja   | gobd
company_facts         | organisation | Recherche              | nein | fachlich
company_reports       | organisation | Recherche              | nein | kurz
change_events         | organisation | Recherche              | nein | fachlich
register_events       | organisation | Recherche              | nein | fachlich
job_signals           | organisation | Recherche              | nein | fachlich
buying_signals        | organisation | Recherche              | nein | fachlich
signal_correlations   | organisation | Recherche              | nein | fachlich
signal_scans          | organisation | Recherche              | nein | kurz
findings              | organisation | Recherche              | nein | fachlich
analysis_runs         | organisation | Recherche              | nein | kurz
quick_scans           | organisation | Recherche              | nein | kurz
website_audits        | organisation | Recherche              | nein | fachlich
website_findings      | organisation | Recherche              | nein | fachlich
website_scores        | organisation | Recherche              | nein | fachlich
website_screenshots   | organisation | Recherche              | nein | fachlich
expert_reviews        | organisation | Recherche              | ja   | fachlich
expert_review_items   | organisation | Recherche              | nein | fachlich
score_versions        | organisation | Recherche              | nein | fachlich
discovery_runs        | organisation | Firmenfindung          | nein | kurz
discovery_candidates  | organisation | Firmenfindung          | nein | kurz
discovery_keys        | organisation | Firmenfindung          | nein | kurz
discovery_dismissed   | organisation | Firmenfindung          | nein | fachlich
discovery_not_same    | organisation | Firmenfindung          | nein | fachlich
search_profiles       | organisation | Firmenfindung          | nein | fachlich
sweeps                | organisation | Firmenfindung          | nein | kurz
batch_runs            | organisation | Firmenfindung          | nein | kurz
batch_items           | organisation | Firmenfindung          | nein | kurz
pilot_samples         | organisation | Firmenfindung          | nein | fachlich
pilot_items           | organisation | Firmenfindung          | nein | fachlich
osm_places            | installation | Firmenfindung          | nein | kurz
osm_imports           | installation | Firmenfindung          | nein | kurz
search_areas          | installation | Firmenfindung          | nein | kurz
geo_cache             | installation | Firmenfindung          | nein | kurz
studies               | organisation | Nutzerstudien          | nein | fachlich
study_sessions        | organisation | Nutzerstudien          | nein | fachlich
study_tasks           | organisation | Nutzerstudien          | nein | fachlich
study_results         | organisation | Nutzerstudien          | nein | fachlich
research_jobs         | organisation | Betrieb                | nein | kurz
research_tasks        | organisation | Betrieb                | nein | kurz
recurring_jobs        | organisation | Betrieb                | nein | fachlich
audit_log             | organisation | Betrieb                | nein | fachlich
app_settings          | organisation | Betrieb                | nein | fachlich
users                 | zugang       | Anmeldung              | ja   | fachlich
sessions              | zugang       | Anmeldung              | nein | kurz
"""


def _parse(text):
    out = {}
    for line in text.strip().splitlines():
        name, scope, area, personal, retention = (p.strip() for p in line.split('|'))
        if scope not in SCOPES or retention not in RETENTION or personal not in ('ja', 'nein') or name in out:
            raise ValueError(f'Tabellenregister: ungültige Zeile {line!r}')
        out[name] = Table(name, scope, area, personal == 'ja', retention)
    return out


TABLES: dict[str, Table] = _parse(_REGISTER)

# Spalten, die nach ihrem Namen für Personenangaben gedacht sind. Eine Tabelle mit einer dieser Spalten muss ``personal`` tragen.
PERSON_COLUMNS = frozenset({
    'contact_name', 'full_name', 'buyer_contact', 'buyer_email', 'owner_name', 'accepted_person', 'decision_person',
    'reviewer', 'who', 'contact', 'username', 'display_name', 'linkedin_url', 'salutation',
})


def tables(scope=None, *, personal=None, retention=None):
    """Tabellennamen nach Merkmalen, sortiert."""
    return sorted(t.name for t in TABLES.values()
                  if (scope is None or t.scope == scope) and (personal is None or t.personal == personal)
                  and (retention is None or t.retention == retention))


def db_tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def check_register(conn):
    """Abweichungen zwischen Datenbank und Register als Liste lesbarer Meldungen (leer = vollständig)."""
    errors = []
    present = db_tables(conn)
    for name in sorted(present - TABLES.keys()):
        errors.append(f'Tabelle {name} fehlt im Tabellenregister (sales_tool/data_map.py)')
    for name in sorted(TABLES.keys() - present):
        errors.append(f'Tabelle {name} steht im Register, existiert aber nicht')
    for name in sorted(present & TABLES.keys()):
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')}
        hits = sorted(cols & PERSON_COLUMNS)
        if hits and not TABLES[name].personal:
            errors.append(f'Tabelle {name} hat Personenspalten ({", ".join(hits)}), ist aber nicht als personenbezogen markiert')
    return errors

# Tabellen des Offline-Firmenkatalogs (GLEIF) – eigene Datei neben der Hauptdatenbank (`<name>.katalog.sqlite3`),
# öffentliche Daten (CC0), von mehreren Organisationen teilbar.
CATALOG_TABLES = {'entities': 'installation', 'imports': 'installation', 'entities_fts': 'installation'}

# Tabellen des Mandantenverzeichnisses (SDQ-011, 014, 021, 022) – eigene Datei `organisationen.sqlite3` im Wurzelordner
# einer Mehrmandanten-Installation, nicht in der Datenbank einer Organisation.
DIRECTORY_TABLES = {'organizations': 'installation', 'accounts': 'zugang', 'memberships': 'zugang', 'account_sessions': 'zugang',
                    'account_mfa': 'zugang', 'account_recovery_codes': 'zugang', 'login_failures': 'zugang',
                    'directory_settings': 'installation', 'audit_events': 'zugang'}
