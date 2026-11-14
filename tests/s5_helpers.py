"""Hilfen für Tests ab v1.18: Freigabe „Bedarf bestätigt“ so setzen, wie ein Nutzer es tut
(Bedarfsanalyse ausfüllen → Gespräch dokumentieren → Bedarf mit Leistungen aus dem Katalog bestätigen)."""
from sales_tool import workday
from sales_tool.model import connect


def confirm_need(db_or_conn, lead_id, needs=None, chance=None):
    """chance: ID einer weiteren Chance (2.0.0-dev19) – dann wird deren eigener Bedarf bestätigt."""
    def run(conn):
        if chance:
            conn.execute("UPDATE opportunities SET problem='Statusanfragen per Telefon', desired_outcome='Selbstauskunft im Portal' WHERE id=?", (chance,))
        else:
            if not conn.execute('SELECT 1 FROM discovery WHERE lead_id=?', (lead_id,)).fetchone():
                conn.execute('INSERT INTO discovery(lead_id) VALUES (?)', (lead_id,))
            conn.execute("UPDATE discovery SET problem='Anfragen gehen verloren', desired_outcome='Mehr qualifizierte Anfragen' WHERE lead_id=?", (lead_id,))
        conn.execute("INSERT INTO calls(lead_id, outcome, notes) VALUES (?, 'erreicht', 'Bedarf im Gespräch geklärt')", (lead_id,))
        conn.commit()
        body = {'via': 'gespraech', 'note': 'Kunde bestätigt Projekt im Telefonat', 'needs': needs or [{'service': 'website_analyse', 'size': 'M'}]}
        if chance:
            body['opportunity_id'] = chance
        return workday.confirm_need(conn, lead_id, body)
    if hasattr(db_or_conn, 'execute'):
        return run(db_or_conn)
    with connect(db_or_conn) as conn:
        return run(conn)


def release_offer(db_or_conn, proposal_id):
    """2.0.0-dev17: Versandfassung freigeben, wie ein Nutzer es tut (alle Prüfpunkte bestätigt)."""
    from sales_tool import offer_flow

    def run(conn):
        return offer_flow.release(conn, proposal_id, {'confirm': list(offer_flow.CONFIRMATIONS)})
    if hasattr(db_or_conn, 'execute'):
        return run(db_or_conn)
    with connect(db_or_conn) as conn:
        return run(conn)
