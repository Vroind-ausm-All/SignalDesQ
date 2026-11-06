"""Rechtsformen nach ISO 20275 (ELF-Codes, wie GLEIF sie je Datensatz liefert) – alle 31 deutschen Codes.

Stand: Live-Abfrage der GLEIF-Codeliste (api.gleif.org/api/v1/entity-legal-forms) für SignalDesk v1.14.
Je Code: Kurzform für die Anzeige und Organisationsart für den Filter „Wen suchst du?“.
"""
import re

UNTERNEHMEN, VEREIN, OEFFENTLICH, SONSTIGE = 'unternehmen', 'verein', 'oeffentlich', 'sonstige'
KIND_LABELS = {UNTERNEHMEN: 'Unternehmen', VEREIN: 'Vereine, Verbände & Stiftungen', OEFFENTLICH: 'Öffentliche Einrichtungen',
               SONSTIGE: 'Sonstige'}

ELF_DE = {
    '2HBR': ('GmbH', UNTERNEHMEN), 'SCE1': ('gGmbH', UNTERNEHMEN), '63KS': ('UG (haftungsbeschränkt)', UNTERNEHMEN),
    '6QQB': ('AG', UNTERNEHMEN), 'YA01': ('gAG', UNTERNEHMEN), 'AMKW': ('REIT-AG', UNTERNEHMEN), 'JMVF': ('InvAG', UNTERNEHMEN),
    'SGST': ('SE', UNTERNEHMEN), 'T0YJ': ('KGaA', UNTERNEHMEN), '8Z6G': ('KG', UNTERNEHMEN), '40DB': ('OHG', UNTERNEHMEN),
    'FR3V': ('GbR', UNTERNEHMEN), 'PDNU': ('eGbR', UNTERNEHMEN), '8CM0': ('PartG', UNTERNEHMEN), '2YZO': ('PartG mbB', UNTERNEHMEN),
    'OL20': ('e.K.', UNTERNEHMEN), 'AZFE': ('eG', UNTERNEHMEN), 'US8E': ('Genossenschaft', UNTERNEHMEN), 'SUA1': ('SCE', UNTERNEHMEN),
    'JNDX': ('EWIV', UNTERNEHMEN), '13AV': ('VVaG', UNTERNEHMEN), '7J3S': ('wirtschaftlicher Verein', UNTERNEHMEN),
    'QZ3L': ('e.V.', VEREIN), '79H0': ('nicht eingetragener Verein', VEREIN), 'D40E': ('Verein alten Rechts', VEREIN),
    'V2YH': ('Stiftung', VEREIN), '9JGX': ('Landesinnungsverband', VEREIN),
    'SQKS': ('Körperschaft d. ö. R.', OEFFENTLICH), 'XLWA': ('Anstalt d. ö. R.', OEFFENTLICH), 'FEBD': ('Stiftung d. ö. R.', OEFFENTLICH),
    'YJ4C': ('kirchliche Stiftung d. ö. R.', OEFFENTLICH),
}

_NAME_RULES = (
    (re.compile(r'\be\.\s?V\.|\bVerein\b|verband\b|Stiftung|\bInnung\b', re.I), VEREIN),
    (re.compile(r'Körperschaft des öffentlichen|Anstalt des öffentlichen|Kirchengemeinde|kammer\b|\bLandkreis\b|\bGemeinde\b|'
                r'\bZweckverband\b|\bUniversität\b|\bHochschule\b|\bLandratsamt\b|\bStadtverwaltung\b', re.I), OEFFENTLICH),
)


def from_elf(code):
    """(Kurzform, Organisationsart) für einen ELF-Code oder None (z. B. „8888“ = nicht gelistet)."""
    return ELF_DE.get((code or '').strip().upper())


def kind_of(name='', elf='', legal_form=''):
    """Organisationsart: ELF-Code zuerst; sonst erkannte Rechtsform (GmbH … → Unternehmen, e.V. → Verein); sonst Namensregeln."""
    hit = from_elf(elf)
    if hit:
        return hit[1]
    lf_ = (legal_form or '').strip()
    if re.fullmatch(r'e\.\s?V\.?', lf_, re.I):
        return VEREIN
    if lf_:
        return UNTERNEHMEN
    for rx, kind in _NAME_RULES:
        if rx.search(name or ''):
            return kind
    return SONSTIGE
