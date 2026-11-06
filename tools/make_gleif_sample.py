"""Erzeugt eine synthetische GLEIF-Datei (Golden-Copy-Spalten, LEI-CDF CSV) mit fiktiven Firmen – für Tests und Messung.

python tools/make_gleif_sample.py <ziel.csv|ziel.zip> [anzahl] — schreibt zeilenweise (kein Aufbau im Arbeitsspeicher).
Alle Firmen, LEIs und Anschriften sind erfunden.
"""
import csv
import io
import random
import sys
import zipfile
from pathlib import Path

HEADER = ['LEI', 'Entity.LegalName', 'Entity.LegalAddress.FirstAddressLine', 'Entity.LegalAddress.AddressNumber', 'Entity.LegalAddress.City',
          'Entity.LegalAddress.PostalCode', 'Entity.LegalAddress.Country', 'Entity.RegistrationAuthority.RegistrationAuthorityEntityID',
          'Entity.LegalForm.EntityLegalFormCode', 'Entity.EntityCategory', 'Entity.EntityStatus', 'Entity.EntityCreationDate',
          'Registration.InitialRegistrationDate', 'Registration.LastUpdateDate', 'Registration.RegistrationStatus', 'Entity.LegalJurisdiction',
          'Entity.HeadquartersAddress.City', 'Entity.HeadquartersAddress.PostalCode', 'Entity.HeadquartersAddress.Country']
CITIES = [('Stuttgart', '70173'), ('Esslingen am Neckar', '73728'), ('Ludwigsburg', '71634'), ('Böblingen', '71032'), ('Ulm', '89073'),
          ('Hamburg', '20095'), ('München', '80331'), ('Köln', '50667'), ('Leipzig', '04109'), ('Mannheim', '68159')]
WORDS = ['Nord', 'Süd', 'Kabel', 'Werk', 'Licht', 'Stahl', 'Holz', 'Bau', 'Daten', 'Technik', 'Müller', 'Schmidt', 'Präzision', 'Feder',
         'Glas', 'Logistik', 'Druck', 'Medien', 'Energie', 'Wasser', 'Garten', 'Maschinen', 'Elektro', 'Kälte', 'Sonne']
FORMS = [('GmbH', '2HBR'), ('GmbH & Co. KG', '8Z6G'), ('AG', '6QQB'), ('UG (haftungsbeschränkt)', '2HBR'), ('e.V.', 'QZ3L')]


def lei(i):
    return f'5299{i:014d}XX'


def rows(n, seed=7, changed=None, inactive=(), skip=()):
    rnd = random.Random(seed)
    for i in range(n):
        if i in skip:
            continue
        city, zip_ = CITIES[i % len(CITIES)]
        form, elf = FORMS[i % len(FORMS)]
        name = f'{rnd.choice(WORDS)}{rnd.choice(WORDS).lower()} {rnd.choice(WORDS)} {i} {form}'
        if changed and i in changed:
            name = changed[i]
        country = 'AT' if i % 25 == 24 else 'DE'
        status = 'INACTIVE' if i in inactive else 'ACTIVE'
        upd = '2026-11-01T08:00:00Z' if (changed and i in changed) or i in inactive else '2025-03-01T08:00:00Z'
        yield [lei(i), name, f'Industriestraße {i % 90 + 1}', '', city.upper() if i % 7 == 0 else city, zip_, country, f'HRB {100000 + i}', elf,
               'GENERAL', status, '2001-01-01', '2019-05-01T00:00:00Z', upd, 'ISSUED', 'DE', city, zip_, country]


def write(path, n, seed=7, as_zip=None, **kw):
    path = Path(path)
    as_zip = path.suffix.lower() == '.zip' if as_zip is None else as_zip
    if as_zip:
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf, zf.open('20261101-gleif-concatenated-file-lei2.csv', 'w') as raw:
            f = io.TextIOWrapper(raw, encoding='utf-8', newline='')
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows(n, seed, **kw))
            f.flush()
            f.detach()
    else:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows(n, seed, **kw))
    return path


if __name__ == '__main__':
    target = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 100_000
    p = write(target, count)
    print(f'{p} · {count} Zeilen · {p.stat().st_size / 1e6:.1f} MB')
