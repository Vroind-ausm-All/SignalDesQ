"""Briefing je Chance (2.0.0-dev20, Produktreview M14).

Das Briefing blendet je Leistungsbereich der Chance passende Fragen ein. Jede Frage wird bewusst beantwortet:
**geklärt** (mit der Angabe des Kunden), **offen** (ausdrücklich offene Voraussetzung: was fehlt, wer liefert, bis wann) oder
**entfällt** (für diesen Auftrag ohne Bedeutung). Unbeantwortet bleibt sichtbar.

Daraus entstehen die Voraussetzungen eines Angebots: geklärte Angaben als Grundlage, offene Punkte als ausdrücklich offene
Voraussetzungen. Neue Angebote speichern intern einen Schnappschuss des Briefings, damit jede Annahme auf eine bestätigte
Angabe oder eine offene Voraussetzung zurückführbar bleibt.

Quellen der Fragen: Leitfaden Kundenonboarding vom 13.11.2026 (Kapitel „Onboarding für Mediengestaltung“ und
„Onboarding für Softwareentwicklung“) und Bewertungsmodell vom selben Tag (Kapitel „Erst Kontext, dann Kriterien“).
Die Bereiche sind die Leistungsbereiche des zentralen Katalogs (dev16).
"""
from __future__ import annotations

import json
import re

# (Schlüssel, Thema, Frage an den Kunden, was zunächst anfordern)
QUESTIONS = {
    'beratung': [
        ('ziel', 'Hauptziel', 'Welches Ergebnis soll die Prüfung bzw. Beratung ermöglichen?', 'Anlass und Entscheidung, die davon abhängt'),
        ('zielgruppe', 'Zielgruppe', 'Für wen ist die Website bzw. das Angebot gedacht?', 'Wichtigste Kundengruppen in eigenen Worten'),
        ('aufgaben', 'Wichtigste Aufgaben', 'Welche drei Aufgaben sollen Besucher erledigen können?', 'Seiten oder Wege, die geprüft werden sollen'),
        ('erfolg', 'Erfolgskriterium', 'Woran würde der Kunde eine Verbesserung erkennen?', 'Vorhandene Zahlen nur mit Freigabe'),
    ],
    'medien': [
        ('anwendung', 'Anwendung', 'Wo erscheint das Ergebnis, wer sieht es und was soll passieren?', 'Beispiele tatsächlicher Anwendungen und benötigte Formate'),
        ('markenrahmen', 'Markenrahmen', 'Was steht fest, was darf sich verändern?', 'Vorhandene Logos, Gestaltungsregeln und freigegebene Basistexte'),
        ('inhalte', 'Inhalte', 'Wer erstellt, prüft und genehmigt Texte und Bilder?', 'Nur Materialien für den ersten Arbeitsschritt'),
        ('gestaltung', 'Gestaltung', 'Welche Wirkung ist gewünscht, welche ausdrücklich unpassend?', 'Wenige Beispiele mit Begründung'),
        ('produktion', 'Produktion', 'Druck, Verarbeitung, Auflage, Lieferort, Termine und externe Partner?', 'Bekannte Produktionsvorgaben und Kontaktperson'),
        ('nutzung', 'Nutzung und Übergabe', 'Welche Formate und Nutzungen sind vereinbart?', 'Rechteinformationen, benötigte Export- und Quelldateien'),
        ('freigabe_medien', 'Entscheidung', 'Wer beurteilt fachlich, wer gibt final frei?', 'Eine Person für gebündeltes Feedback'),
    ],
    'software': [
        ('kernprozess', 'Kernprozess', 'Welcher Ablauf soll zuerst zuverlässig funktionieren?', 'Einfaches Prozessbild mit Anfang, Ergebnis und Ausnahmen'),
        ('rollen', 'Nutzer und Rollen', 'Wer arbeitet damit, wer administriert, wer entscheidet?', 'Rollenübersicht und zuständige Fachperson'),
        ('daten', 'Daten', 'Welche Daten werden benötigt, wie entstehen sie und wie gut sind sie?', 'Geeignete Testdaten und dokumentierte Herkunft'),
        ('schnittstellen', 'Schnittstellen', 'Welche Systeme müssen verbunden werden, wer ermöglicht den Zugriff?', 'Ansprechpartner, Dokumentation, freigegebener Testzugang (keine Passwörter per Mail)'),
        ('umfang', 'Funktionaler Umfang', 'Was ist für die erste Lieferung nötig, was folgt später?', 'Priorisierte Anforderungen mit klaren Grenzen'),
        ('betrieb', 'Betrieb', 'Wer hostet, aktualisiert, überwacht und reagiert auf Fehler?', 'Verantwortlichkeiten und beauftragter Betriebsumfang'),
        ('pruefung', 'Prüfung', 'Woran erkennt der Kunde eine erfolgreiche Umsetzung?', 'Verständliche Testfälle mit erwartetem Ergebnis'),
    ],
    'sichtbarkeit': [
        ('suchanlass', 'Ziel und Suchanlässe', 'Wofür und von wem soll das Unternehmen gefunden werden?', 'Wichtigste Leistungen und Region'),
        ('ausgang', 'Ausgangsmessung', 'Welche Zahlen gibt es heute, und darf ich sie sehen?', 'Zugang zu Search Console bzw. Werbekonto mit passender Rolle'),
        ('budget_kanal', 'Budget und Kanäle', 'Welches Werbebudget zahlt der Kunde direkt, auf welchen Kanälen?', 'Budgetrahmen und Zahlungsweg'),
    ],
}
STATUS = {'geklaert': 'geklärt', 'offen': 'offen', 'entfaellt': 'entfällt'}
BY_KEY = {k: (area, label, q, req) for area, items in QUESTIONS.items() for k, label, q, req in items}


def init_briefing(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS briefing_answers (
        opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
        key TEXT NOT NULL, status TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (opportunity_id, key)
      );
    ''')
    cols = {r[1] for r in conn.execute('PRAGMA table_info(opportunities)')}
    if 'briefing_areas' not in cols:
        conn.execute("ALTER TABLE opportunities ADD COLUMN briefing_areas TEXT NOT NULL DEFAULT ''")


def _chance(conn, oid):
    row = conn.execute('SELECT * FROM opportunities WHERE id=?', (oid,)).fetchone()
    if not row:
        raise LookupError('Chance nicht gefunden.')
    return row


def derived_areas(conn, row):
    """Leistungsbereiche der Chance: bestätigte Leistungen, Vorlage und Positionen ihrer Angebote."""
    from .catalog import SERVICES, VORLAGEN
    keys = []
    needs = row['needs_json'] if not row['is_first'] else (conn.execute('SELECT needs_json FROM discovery WHERE lead_id=?', (row['lead_id'],)).fetchone() or {'needs_json': '[]'})['needs_json']
    keys += [n.get('service') for n in json.loads(needs or '[]')]
    keys += [p['service'] for p in VORLAGEN.get(row['offer'], {}).get('positions', [])]
    for p in conn.execute('SELECT customer_json FROM proposals WHERE opportunity_id=?', (row['id'],)):
        keys += [x.get('service') for x in json.loads(p['customer_json']).get('positions') or []]
    return [a for a in QUESTIONS if any(a in SERVICES[k]['areas'] for k in keys if k in SERVICES)]


def areas_of(conn, row):
    picked = set((row['briefing_areas'] or '').split(','))
    chosen = [a for a in QUESTIONS if a in picked]  # feste Reihenfolge wie im Katalog
    return chosen or derived_areas(conn, row)


def get(conn, oid):
    row = _chance(conn, oid)
    areas = areas_of(conn, row)
    answers = {r['key']: dict(r) for r in conn.execute('SELECT * FROM briefing_answers WHERE opportunity_id=?', (oid,))}
    items = []
    for area in areas:
        for key, label, question, request in QUESTIONS[area]:
            a = answers.get(key, {})
            items.append({'area': area, 'key': key, 'label': label, 'question': question, 'request': request,
                          'status': a.get('status', ''), 'answer': a.get('answer', ''), 'updated_at': a.get('updated_at', '')})
    count = lambda s: sum(1 for i in items if i['status'] == s)
    from .catalog import AREAS
    return {'opportunity_id': oid, 'title': row['title'], 'areas': [{'key': a, 'label': AREAS.get(a, a)} for a in areas],
            'chosen': bool((row['briefing_areas'] or '').strip()), 'all_areas': {a: AREAS.get(a, a) for a in QUESTIONS},
            'items': items, 'summary': {'geklaert': count('geklaert'), 'offen': count('offen'), 'entfaellt': count('entfaellt'),
                                        'unbeantwortet': count('')}, 'statuses': STATUS}


def save(conn, oid, data):
    if not isinstance(data, dict) or set(data) - {'answers', 'areas'}:
        raise ValueError('Erwartet: {answers: [{key, status, answer}], areas?}.')
    row = _chance(conn, oid)
    if 'areas' in data:
        areas = data['areas']
        if not isinstance(areas, list) or any(a not in QUESTIONS for a in areas):
            raise ValueError('Bereiche: ' + ', '.join(QUESTIONS))
        conn.execute("UPDATE opportunities SET briefing_areas=?, updated_at=datetime('now') WHERE id=?", (','.join(dict.fromkeys(areas)), oid))
    answers = data.get('answers', [])
    if not isinstance(answers, list):
        raise ValueError('answers: Liste erwartet.')
    for a in answers:
        if not isinstance(a, dict) or set(a) - {'key', 'status', 'answer'} or a.get('key') not in BY_KEY:
            raise ValueError('Unbekannte Briefingfrage.')
        status, text = a.get('status', ''), re.sub(r'\s+', ' ', str(a.get('answer') or '')).strip()
        if len(text) > 1000:
            raise ValueError('Antworten höchstens 1000 Zeichen.')
        label = BY_KEY[a['key']][1]
        if status == '':
            conn.execute('DELETE FROM briefing_answers WHERE opportunity_id=? AND key=?', (oid, a['key']))
            continue
        if status not in STATUS:
            raise ValueError('Status: geklärt, offen oder entfällt.')
        if status == 'geklaert' and len(text) < 3:
            raise ValueError(f'„{label}“: als geklärt nur mit der Angabe des Kunden.')
        if status == 'offen' and len(text) < 3:
            raise ValueError(f'„{label}“: bei offen kurz notieren, was fehlt und wer es liefert.')
        conn.execute("""INSERT INTO briefing_answers(opportunity_id, key, status, answer) VALUES (?,?,?,?)
                        ON CONFLICT(opportunity_id, key) DO UPDATE SET status=excluded.status, answer=excluded.answer, updated_at=datetime('now')""",
                     (oid, a['key'], status, text))
    if answers:
        conn.execute('INSERT INTO activities(lead_id, activity_type, detail) VALUES (?,?,?)',
                     (row['lead_id'], 'notiz', f"Briefing der Chance „{row['title']}“ aktualisiert ({len(answers)} Angabe(n))."))
    conn.commit()
    return get(conn, oid)


def assumptions(conn, oid):
    """Voraussetzungen fürs Angebot: geklärte Angaben als Grundlage, offene Punkte ausdrücklich offen."""
    b = get(conn, oid)
    done = [f"{i['label']}: {i['answer']}" for i in b['items'] if i['status'] == 'geklaert']
    open_ = [f"{i['label']}: {i['answer']}" for i in b['items'] if i['status'] == 'offen']
    parts = []
    if done:
        parts.append('Grundlage laut Briefing – ' + '; '.join(done) + '.')
    if open_:
        parts.append('Offene Voraussetzungen, vor Projektstart zu klären – ' + '; '.join(open_) + '.')
    return ' '.join(parts)[:1000], b


def snapshot(conn, oid):
    """Intern am Angebot: welche Angaben galten beim Erstellen (Rückverfolgbarkeit der Annahmen)."""
    if not oid:
        return None
    b = get(conn, oid)
    return {'summary': b['summary'], 'areas': [a['key'] for a in b['areas']],
            'items': [{k: i[k] for k in ('key', 'label', 'status', 'answer')} for i in b['items'] if i['status']]}


def route_briefing(h, conn, method, route):
    m = re.fullmatch(r'/api/chances/(\d+)/briefing(/voraussetzungen)?', route)
    if not m:
        return False
    oid = int(m.group(1))
    if m.group(2) and method == 'GET':
        text, b = assumptions(conn, oid)
        h._send(200, {'text': text, 'summary': b['summary']})
    elif method == 'GET':
        h._send(200, get(conn, oid))
    elif method == 'PUT':
        h._send(200, save(conn, oid, h._body()))
    else:
        return False
    return True
