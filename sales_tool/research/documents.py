"""Isolierter Dokument-Parser (R3.1) und Fundstellen in Dokumenten (R3.2), 2.0.0-dev71.

Jedes Dokument (PDF, XML, CSV, Text, ZIP) wird in einem eigenen Prozess gelesen – nie im Server- oder Auftragsprozess:
``python -I -S sales_tool/docparse.py`` ohne Umgebungsvariablen, ohne Paketpfade, mit leerem Arbeitsverzeichnis.
- Zeitgrenze TIMEOUT: danach wird der Prozess beendet; Speichergrenze MAX_MEMORY und CPU-Grenze unter Linux/macOS.
- Eingabe nur als Bytes über stdin (kein Pfad – keine Pfadmanipulation), Ausgabe nur JSON über stdout mit Größengrenze.
- Im Kindprozess sperrt ein Prüf-Hook Netz, neue Prozesse und Schreibzugriffe (siehe docparse._sandbox).
- Ergebnis: ``Document`` mit Abschnitten und Fundstelle je Abschnitt (PDF-Seite, XML-Pfad, CSV-Zeile/Spalte, ZIP-Eintrag).
  ``document_ref`` baut daraus einen Beleg v2 (research.evidence) – nur wenn der Wert wörtlich in genau einem Abschnitt steht.

Ein abgewiesenes Dokument ist ein Teilergebnis mit Grund (``DocumentRejected``), nie ein Absturz und nie ein leerer Befund.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import evidence as ev

WORKER = Path(__file__).resolve().parent.parent / 'docparse.py'
TIMEOUT = 30            # Sekunden je Dokument
MAX_MEMORY = 768 * 1024 * 1024
MAX_CPU = 30
MAX_OUTPUT = 12_000_000  # Bytes JSON-Ausgabe
MAX_INPUT = 20_000_000


class DocumentRejected(ValueError):
    def __init__(self, message, reason='rejected'):
        super().__init__(message)
        self.reason = reason


@dataclass
class Document:
    kind: str
    segments: list
    warnings: list = field(default_factory=list)
    pages: int = 0
    content_hash: str = ''

    @property
    def text(self):
        return '\n'.join(s['text'] for s in self.segments)

    def page_text(self, page, member=None):
        return '\n'.join(s['text'] for s in self.segments if s['loc'].get('page') == page and s['loc'].get('member') == member)

    def find(self, value, kind=''):
        """Abschnitte, in denen der Wert steht (Vergleich wie beim Belegvalidator)."""
        return [s for s in self.segments if ev.found_in(value, s['text'], kind)]


def _env():
    env = {'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0'}
    for key in ('SYSTEMROOT', 'WINDIR'):  # Windows braucht diese für den Start des Interpreters
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def parse(data, kind=None, filename='', timeout=None, limits=None):
    """Dokument-Bytes im isolierten Prozess lesen → Document. Wirft DocumentRejected (Angriff, Grenze, Zeit, unlesbar)."""
    if not isinstance(data, (bytes, bytearray)):
        raise DocumentRejected('Keine Dokument-Bytes.')
    if len(data) > MAX_INPUT:
        raise DocumentRejected(f'Dokument größer als {MAX_INPUT // 1_000_000} MB.', 'size')
    opts = {'kind': kind, 'filename': os.path.basename(str(filename or ''))[:200],
            'limits': {'max_memory': MAX_MEMORY, 'max_cpu': MAX_CPU, 'max_input': MAX_INPUT, **(limits or {})}}
    with tempfile.TemporaryDirectory(prefix='sdq-doc-') as cwd:  # leeres Arbeitsverzeichnis, danach gelöscht
        try:
            proc = subprocess.run([sys.executable, '-I', '-S', str(WORKER), json.dumps(opts)], input=bytes(data), capture_output=True,
                                  timeout=timeout or TIMEOUT, cwd=cwd, env=_env(), check=False,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise DocumentRejected(f'Dokument-Parser nach {timeout or TIMEOUT} s abgebrochen – Teilergebnis ohne dieses Dokument.',
                                   'timeout') from exc
        except OSError as exc:
            raise DocumentRejected(f'Dokument-Parser nicht startbar ({exc}).', 'error') from exc
    if len(proc.stdout) > MAX_OUTPUT:
        raise DocumentRejected('Ausgabe des Dokument-Parsers zu groß – abgewiesen.', 'size')
    try:
        result = json.loads(proc.stdout.decode('utf-8') or '{}')
    except ValueError:
        result = {}
    if not result:
        reason = 'memory' if proc.returncode in (-9, 137) or b'MemoryError' in proc.stderr else 'error'
        raise DocumentRejected('Dokument-Parser ohne Ergebnis beendet' + (' (Speichergrenze)' if reason == 'memory' else '') + '.', reason)
    if not result.get('ok'):
        raise DocumentRejected(result.get('error') or 'Dokument abgewiesen.', result.get('reason') or 'rejected')
    return Document(kind=result['kind'], segments=result['segments'], warnings=result.get('warnings', []), pages=result.get('pages', 0),
                    content_hash=ev.content_hash(bytes(data)))


def _locator(segment, value):
    loc = segment['loc']
    text = segment['text']
    quote = value if value in text else text[:300]
    if loc.get('kind') == 'pdf':
        if not loc.get('page'):
            return None  # ohne Seitenangabe keine PDF-Fundstelle
        out = {'kind': 'pdf', 'page': loc['page'], 'quote': quote}
    elif loc.get('kind') == 'xml':
        out = {'kind': 'xml', 'path': loc['path'], 'quote': quote}
    elif loc.get('kind') == 'csv':
        out = {'kind': 'csv', 'row': loc['row'], 'column': loc['column'], 'quote': quote}
    elif loc.get('kind') == 'text':
        out = {'kind': 'doc_text', 'line': loc['line'], 'quote': quote}
    else:
        return None
    if loc.get('member'):
        out['member'] = loc['member']
    return out


def document_ref(field_name, value, doc, source_url, extractor, **kw):
    """Beleg v2 mit Fundstelle im Dokument – None, wenn der Wert in keinem Abschnitt wörtlich steht.
    Steht er in mehreren, gilt der erste (Lesereihenfolge); der Beleg nennt genau diese Stelle."""
    value = str(value or '').strip()
    if not value:
        return None
    for seg in doc.segments:
        if value in seg['text']:
            loc = _locator(seg, value)
            if loc:
                return ev.make_ref(field_name, value, source_url, extractor, loc, chash=doc.content_hash, **kw)
    return None


def verify_document_ref(ref, doc):
    """Gegenprüfung: Steht der Wert an der genannten Stelle desselben Dokuments (gleicher Hash)?"""
    if ev.check_ref(ref) or ref.get('content_hash') != doc.content_hash:
        return False
    loc = ref['locator']
    want = {k: loc[k] for k in ('page', 'path', 'row', 'column', 'line', 'member') if k in loc}
    kind = {'doc_text': 'text'}.get(loc['kind'], loc['kind'])
    for seg in doc.segments:
        sl = seg['loc']
        if sl.get('kind') == kind and all(sl.get(k) == v for k, v in want.items()) and sl.get('member') == loc.get('member'):
            if loc['quote'] in seg['text'] and str(ref['value']) in loc['quote']:
                return True
    return False
