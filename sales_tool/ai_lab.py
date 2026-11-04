"""Local-only connection test and demo text analysis for the SignalDesk browser UI."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_provider import AnalysisError, analyze

OLLAMA_TAGS = 'http://127.0.0.1:11434/api/tags'
DEMO_SOURCE = 'urn:signaldesk:manual-input'


def ollama_health(timeout: float = 1.5):
    """Return a truthful, non-throwing snapshot. No cloud service is contacted."""
    try:
        with urlopen(Request(OLLAMA_TAGS, headers={'Accept':'application/json'}), timeout=timeout) as response:
            payload = json.loads(response.read(250_000))
        models = [str(m.get('name', ''))[:100] for m in payload.get('models', []) if isinstance(m, dict) and m.get('name')]
        return {'online': True, 'models': models, 'message': 'Ollama erreichbar.' if models else 'Ollama erreichbar; noch keine Modelle installiert.'}
    except (URLError, TimeoutError, OSError, ValueError, KeyError, HTTPError):
        return {'online': False, 'models': [], 'message': 'Ollama nicht erreichbar. Anwendung funktioniert weiterhin im Regelmodus.'}


def demo_analysis(body):
    """Analyze user-pasted public website text without crawling or saving any CRM data."""
    if not isinstance(body, dict) or set(body) - {'text', 'provider', 'model'}:
        raise ValueError('Erwarte Text, Anbieter und optional Modell.')
    text = body.get('text', '')
    provider = body.get('provider', 'rules')
    model = body.get('model', 'qwen3:8b')
    if not isinstance(text, str) or not (80 <= len(text.strip()) <= 12000):
        raise ValueError('Bitte 80 bis 12.000 Zeichen Website-Text eingeben.')
    if provider not in ('rules', 'ollama'):
        raise ValueError('Unbekannter Analysemodus.')
    if not isinstance(model, str):
        raise ValueError('Ungültiger Modellname.')
    crawl = {'pages': [{'url': DEMO_SOURCE, 'title': 'Manuell eingegebener Testtext', 'text': text.strip()}]}
    result = analyze(crawl, provider=provider, model=model)
    return {
        'mode': 'preview_only', 'saved': False, 'provider': provider,
        'model': model if provider == 'ollama' else 'regelmodus',
        'summary': result['summary'], 'findings': result['findings'],
        'discarded': result.get('discarded', 0),
        'notice': 'Testeingabe: kein Live-Website-Abruf, kein CRM-Eintrag und keine nachgewiesene Kundennachfrage.'
    }


def lead_brief(conn, lead_id: int):
    """Human-readable export; manually confirmed discovery and reviewed findings stay distinct."""
    row = conn.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        return None
    lead = dict(row)
    discovery = conn.execute('SELECT * FROM discovery WHERE lead_id=?', (lead_id,)).fetchone()
    findings = conn.execute('''SELECT f.* FROM findings f JOIN analysis_runs r ON r.id=f.run_id
                               WHERE f.lead_id=? AND f.review_status='freigegeben' AND r.status='done'
                               ORDER BY f.id DESC LIMIT 8''', (lead_id,)).fetchall()
    def safe(v):
        return str(v or 'Nicht dokumentiert').replace('\r',' ').replace('\n', ' ').strip()[:2000]
    lines = [f'# Recherche- und Gesprächsbriefing: {safe(lead["company"])}', '',
             '## Unternehmensprofil', f'- Website: {safe(lead["website"])}',
             f'- Branche: {safe(lead["industry"])}', f'- Standort: {safe(lead["location"])}',
             f'- Ansprechpartner / Rolle: {safe(lead["contact_name"])} / {safe(lead["contact_role"])}', '',
             '## Öffentliche Beobachtung (manuell prüfen)',
             f'- Beobachtung: {safe(lead["signal_note"])}', f'- Quelle: {safe(lead["signal_source"])}', '',
             '## Freigegebene KI-Hypothesen (kein bestätigter Bedarf)']
    if not findings:
        lines += ['- Keine freigegebenen Analysebefunde.']
    for f in findings:
        lines += [f'- Beobachtung: {safe(f["observation"])}', f'  - Textbeleg: {safe(f["evidence"])}',
                  f'  - Quelle: {safe(f["source_url"])}', f'  - Möglicher Bedarf: {safe(f["hypothesis"])}',
                  f'  - Frage: {safe(f["question"])}']
    lines += ['', '## Bestätigte Antworten aus dem Erstgespräch']
    d = dict(discovery) if discovery else {}
    for k, label in (('problem','Problem'),('impact','Auswirkungen'),('current_solution','Bisherige Lösung'),
                     ('desired_outcome','Gewünschtes Ergebnis'),('timing','Zeitrahmen'),
                     ('decision_process','Entscheidungsprozess'),('budget_status','Budgetstatus'),
                     ('budget_note','Budgetdetails')):
        lines += [f'- {label}: {safe(d.get(k))}']
    lines += ['', '## Nächster Schritt / Kontaktgrundlage',
              f'- Nächster Schritt: {safe(lead["next_step"])}', f'- Datum: {safe(lead["next_date"])}',
              f'- Kontaktweg: {safe(lead["contact_route"])}', f'- Kontaktberechtigung: {safe(lead["permission"])}',
              '', '> Nicht für automatisierte Kontaktaufnahme verwenden. Vor jeder Ansprache Rechtsgrundlage prüfen.', '']
    return {'filename': f'signaldesk-briefing-{lead_id}.md', 'markdown': '\n'.join(lines)}
