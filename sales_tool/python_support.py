"""Unterstützte Python-Versionen und Ankündigung des Endes von Python 3.10 (2.0.0-dev68).

Entscheidung vom 26.11.2026: Python 3.10 wird erst angekündigt, im darauf folgenden Release gestrichen. Python 3.10 bekommt seit
Oktober 2026 keine Sicherheitskorrekturen mehr. Nur Standardbibliothek; wird vom Starter (``bootstrap``) vor der Einrichtung
der Umgebung und von beiden Servern beim Start verwendet.
"""
from __future__ import annotations

import sys

MIN_PYTHON = (3, 10)          # heute noch unterstützt
NEXT_MIN_PYTHON = (3, 11)     # ab dem nächsten Release Pflicht
RECOMMENDED_PYTHON = (3, 14)  # für neue Installationen


def notice(version_info=None):
    """Hinweistext, wenn die laufende Version im nächsten Release nicht mehr unterstützt wird – sonst ''."""
    v = tuple((version_info or sys.version_info)[:2])
    if v >= NEXT_MIN_PYTHON or v < MIN_PYTHON:
        return ''
    return (f'Hinweis: SignalDesk läuft mit Python {v[0]}.{v[1]}. Diese Version bekommt seit Oktober 2026 keine '
            f'Sicherheitskorrekturen mehr; die nächste Version von SignalDesk braucht Python {NEXT_MIN_PYTHON[0]}.{NEXT_MIN_PYTHON[1]} '
            f'oder neuer (empfohlen: {RECOMMENDED_PYTHON[0]}.{RECOMMENDED_PYTHON[1]}). Jetzt eine neuere Version installieren – '
            'die Daten bleiben erhalten, SignalDesk richtet seine Umgebung beim nächsten Start neu ein.')
