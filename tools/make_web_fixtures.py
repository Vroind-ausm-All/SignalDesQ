"""Erzeugt das Testgelände für Sprint 0/1/2: fiktive Firmen-Websites als lokale Dateien + manifest.json.

Alle Firmen, Personen, Nummern und Adressen sind erfunden (.example-Domains, Telefonnummern +49 … 000…).
Aufruf: python tools/make_web_fixtures.py  → tests/fixtures/web/
Das Verhalten (Statuscodes, Weiterleitungen, Verzögerungen, Größen) beschreibt manifest.json; tools/fixture_server.py setzt es um.
"""
import gzip
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'web'


def page(title, body, head='', charset='utf-8'):
    meta = f'<meta charset="{charset}">' if charset else ''
    return f'<!doctype html><html lang="de"><head>{meta}<title>{title}</title>{head}</head><body>{body}</body></html>'


NAV = '<nav><a href="/">Start</a> <a href="/leistungen">Leistungen</a> <a href="/kontakt">Kontakt</a> <a href="/impressum">Impressum</a></nav>'


def imprint_html(name, street, zip_, city, court, reg, vat, phone, email, ceo='Erika Beispiel', extra=''):
    return page(f'Impressum – {name}', f'''{NAV}<main><h1>Impressum</h1><p>Angaben gemäß § 5 DDG</p>
<address>{name}<br>{street}<br>{zip_} {city}</address>
<p>Vertreten durch die Geschäftsführerin: {ceo}</p>
<p>Registergericht: {court}<br>Registernummer: {reg}</p>
<p>Umsatzsteuer-Identifikationsnummer gemäß § 27a UStG: {vat}</p>
<p>Telefon: {phone}<br>E-Mail: <a href="mailto:{email}">{email}</a></p>{extra}</main>''')


def home(name, claim, extra=''):
    return page(name, f'{NAV}<main><h1>{name}</h1><p>{claim}</p><h2>Leistungen</h2><p>Beratung, Planung und Umsetzung für den Mittelstand in der Region.</p>{extra}</main>'
                      '<footer><a href="/impressum">Impressum</a> · <a href="/datenschutz">Datenschutz</a></footer>')


SITES = {}
FILES = {}


def site(host, pages, expect=None, robots='User-agent: *\nAllow: /\n', routes=None, note=''):
    SITES[host] = {'pages': {}, 'robots': robots, 'routes': routes or {}, 'expect': expect or {}, 'note': note}
    for path, content in pages.items():
        fname = f'{host}{path if path != "/" else "/index"}'.strip('/').replace('/', '__') + ('.bin' if isinstance(content, bytes) else '.html')
        FILES[fname] = content
        SITES[host]['pages'][path] = fname


def std(host, name, street, zip_, city, court, reg, vat, phone, email, **kw):
    expect = {'legal_name': name, 'zip': zip_, 'city': city, 'register_number': reg, 'vat_id': vat,
              'business_phone': phone, 'business_email': email}
    extra_pages = kw.pop('extra_pages', {})
    site(host, {'/': home(name, kw.pop('claim', 'Ihr Partner seit 1998.')), '/impressum': imprint_html(name, street, zip_, city, court, reg, vat, phone, email),
                '/kontakt': page('Kontakt', f'{NAV}<h1>Kontakt</h1><p>Schreiben Sie uns: {email}</p><form><input name="n"></form>'),
                '/leistungen': page('Leistungen', f'{NAV}<h1>Leistungen</h1><p>Metallbau, Blechbearbeitung, Montage.</p>'), **extra_pages},
         expect={**expect, **kw.pop('expect_extra', {})}, **kw)


# 1–3 Standardfälle
std('mueller-metall.example', 'Müller Metallbau GmbH', 'Industriestraße 12', '70565', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700001',
    'DE999000001', '+49 711 0000001', 'info@mueller-metall.example', note='Klassisches GmbH-Impressum, verlinkt')
std('schmid-kg.example', 'Schmid Anlagenbau GmbH & Co. KG', 'Neckarweg 3', '73728', 'Esslingen am Neckar', 'Amtsgericht Stuttgart', 'HRA 700002',
    'DE999000002', '+49 711 0000002', 'kontakt@schmid-kg.example', note='GmbH & Co. KG')
std('weber-ug.example', 'Weber Digital UG (haftungsbeschränkt)', 'Marktplatz 1', '71634', 'Ludwigsburg', 'Amtsgericht Stuttgart', 'HRB 700003',
    'DE999000003', '+49 7141 0000003', 'hallo@weber-ug.example', note='UG')

# 4 Weiterleitung auf www (Startseite UND robots.txt leiten um – häufigster Fall im Netz)
std('www.kanzlei-berg.example', 'Berg Steuerberatung GmbH', 'Königstraße 20', '70173', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700004',
    'DE999000004', '+49 711 0000004', 'office@kanzlei-berg.example', note='Ziel der www-Weiterleitung')
SITES['kanzlei-berg.example'] = {'pages': {}, 'robots': None, 'expect': SITES['www.kanzlei-berg.example']['expect'],
                                 'routes': {'*': {'status': 301, 'location': 'http://www.kanzlei-berg.example{path}'}},
                                 'note': 'Domain ohne www leitet ALLES (auch robots.txt) auf www um'}

# 5–8 robots.txt-Varianten
std('geschlossen.example', 'Geschlossen GmbH', 'Weg 1', '70173', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700005', 'DE999000005',
    '+49 711 0000005', 'info@geschlossen.example', robots='User-agent: *\nDisallow: /\n', note='robots.txt sperrt alles → kein Abruf')
SITES['geschlossen.example']['expect'] = {'blocked': 'robots'}
std('robots403.example', 'Robots Vierhundertdrei GmbH', 'Weg 3', '70174', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700006', 'DE999000006',
    '+49 711 0000006', 'info@robots403.example', routes={'/robots.txt': {'status': 403}},
    note='robots.txt antwortet 403 → laut RFC 9309 „nicht verfügbar“ = Abruf erlaubt')
std('robots500.example', 'Robots Fünfhundert GmbH', 'Weg 5', '70176', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700007', 'DE999000007',
    '+49 711 0000007', 'info@robots500.example', routes={'/robots.txt': {'status': 503}},
    note='robots.txt 5xx → laut RFC 9309 vollständig gesperrt')
SITES['robots500.example']['expect'] = {'blocked': 'robots'}
std('teilgesperrt.example', 'Teilgesperrt GmbH', 'Weg 7', '70178', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700008', 'DE999000008',
    '+49 711 0000008', 'info@teilgesperrt.example', robots='User-agent: *\nDisallow: /kontakt\nDisallow: /*.pdf$\n',
    note='robots sperrt nur /kontakt und PDFs (Wildcard-Regel)')

# 9–10 Statuscodes
site('gesperrt403.example', {'/': page('x', 'x')}, expect={'error': 'http'}, routes={'/': {'status': 403}}, note='Startseite 403')
site('drossel429.example', {'/': page('x', 'x')}, expect={'error': 'http'}, routes={'/': {'status': 429, 'headers': {'Retry-After': '120'}}},
     note='429 mit Retry-After – kein aggressives Wiederholen')

# 11–12 Kodierung
latin = imprint_html('Größle Feinwerk KG', 'Hauptstraße 8', '73033', 'Göppingen', 'Amtsgericht Ulm', 'HRA 700009', 'DE999000009',
                     '+49 7161 0000009', 'info@groessle.example').replace('<meta charset="utf-8">', '')
site('groessle.example', {'/': home('Größle Feinwerk KG', 'Präzision aus Göppingen.').replace('<meta charset="utf-8">', '').replace('–', '-').encode('latin-1'),
                          '/impressum': latin.replace('–', '-').encode('latin-1')},
     expect={'legal_name': 'Größle Feinwerk KG', 'zip': '73033', 'city': 'Göppingen', 'register_number': 'HRA 700009', 'vat_id': 'DE999000009',
             'business_phone': '+49 7161 0000009', 'business_email': 'info@groessle.example'},
     routes={'*': {'headers': {'Content-Type': 'text/html'}}}, note='ISO-8859-1 ohne Zeichensatzangabe')
cp = imprint_html('Bäckerei Süß GmbH', 'Brückenstraße 2', '72764', 'Reutlingen', 'Amtsgericht Stuttgart', 'HRB 700010', 'DE999000010',
                  '+49 7121 0000010', 'info@baeckerei-suess.example').replace('charset="utf-8"', 'charset="windows-1252"')
site('baeckerei-suess.example', {'/': home('Bäckerei Süß GmbH', 'Frisch – täglich.').replace('charset="utf-8"', 'charset="windows-1252"').encode('cp1252'),
                                 '/impressum': cp.encode('cp1252')},
     expect={'legal_name': 'Bäckerei Süß GmbH', 'zip': '72764', 'city': 'Reutlingen', 'register_number': 'HRB 700010', 'vat_id': 'DE999000010',
             'business_phone': '+49 7121 0000010', 'business_email': 'info@baeckerei-suess.example'},
     note='windows-1252 per meta charset')

# 13 Impressum als PDF
pdf_text = 'Impressum Muster PDF GmbH Pfad 4 70180 Stuttgart Amtsgericht Stuttgart HRB 700011'
pdf = (b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
       b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R>>endobj\n'
       b'4 0 obj<</Length ' + str(len(pdf_text) + 30).encode() + b'>>stream\nBT /F1 12 Tf 50 800 Td (' + pdf_text.encode() + b') Tj ET\nendstream endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n')
site('pdf-impressum.example', {'/': home('Muster PDF GmbH', 'Wir machen PDFs.').replace('<a href="/impressum">Impressum</a> ·', '<a href="/impressum.pdf">Impressum (PDF)</a> ·'),
                               '/impressum.pdf': pdf},
     expect={'register_number': 'HRB 700011', 'zip': '70180'}, routes={'/impressum.pdf': {'headers': {'Content-Type': 'application/pdf'}}},
     note='Impressum nur als PDF verlinkt')

# 14 Reine JavaScript-Seite
site('nur-javascript.example', {'/': page('App', '<div id="app"></div><script>document.getElementById("app").innerText="Impressum: JS GmbH"</script>')},
     expect={'error': 'no_text'}, note='Inhalt nur per JavaScript – statischer Abruf findet nichts')

# 15–17 gefährliche bzw. fremde Weiterleitungen
site('boese-weiterleitung.example', {'/': page('x', 'x')}, expect={'blocked': 'ssrf'},
     routes={'/': {'status': 302, 'location': 'http://127.0.0.1:9/admin'}}, note='Weiterleitung auf eine lokale IP-Adresse')
site('intern-weiterleitung.example', {'/': page('x', 'x')}, expect={'blocked': 'ssrf'},
     routes={'/': {'status': 302, 'location': 'http://router.intern-weiterleitung.example/'}},
     note='Weiterleitung auf einen Namen, der auf eine private Adresse (10.0.0.1) zeigt')
std('fremd-weiterleitung.example', 'Fremd Weiterleitung GmbH', 'Weg 9', '70182', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700012',
    'DE999000012', '+49 711 0000012', 'info@fremd-weiterleitung.example',
    routes={'/impressum': {'status': 301, 'location': 'http://mueller-metall.example/impressum'}},
    note='Impressum leitet auf eine andere Firma um → nicht folgen')
SITES['fremd-weiterleitung.example']['expect'] = {'no_imprint': True}
site('schleife.example', {'/': page('x', 'x')}, expect={'error': 'redirects'},
     routes={'/': {'status': 302, 'location': '/a'}, '/a': {'status': 302, 'location': '/b'}, '/b': {'status': 302, 'location': '/a'}},
     note='Weiterleitungsschleife')

# 18–20 Größe, Kompression, Zeit
site('riesig.example', {'/': page('x', 'x')}, expect={'error': 'size'}, routes={'/': {'size': 10_000_000}}, note='10-MB-Antwort')
bomb = gzip.compress(b'<p>' + b'A' * 60_000_000 + b'</p>', 9)
site('gzip-bombe.example', {'/': bomb}, expect={'error': 'size'},
     routes={'/': {'headers': {'Content-Encoding': 'gzip', 'Content-Type': 'text/html'}}}, note='gzip-Bombe: 60 MB entpackt, ~60 KB übertragen')
gz = gzip.compress(home('Gzip Technik GmbH', 'Komprimiert ausgeliefert.').encode())
gzi = gzip.compress(imprint_html('Gzip Technik GmbH', 'Weg 11', '70184', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700013', 'DE999000013',
                                 '+49 711 0000013', 'info@gzip-technik.example').encode())
site('gzip-technik.example', {'/': gz, '/impressum': gzi},
     expect={'legal_name': 'Gzip Technik GmbH', 'register_number': 'HRB 700013', 'zip': '70184', 'vat_id': 'DE999000013'},
     routes={'*': {'headers': {'Content-Encoding': 'gzip', 'Content-Type': 'text/html; charset=utf-8'}}},
     note='Server liefert gzip, obwohl nicht angefragt')
site('langsam.example', {'/': page('x', 'x')}, expect={'error': 'timeout'}, routes={'/': {'delay': 25}}, note='Antwort nach 25 s')
site('kein-html.example', {'/': b'\x89PNG\r\n\x1a\n' + b'0' * 200}, expect={'error': 'content_type'},
     routes={'/': {'headers': {'Content-Type': 'image/png'}}}, note='Startseite ist ein Bild')

# 21–28 Impressumsvarianten
std('widerspruch.example', 'Widerspruch Bau GmbH & Co. KG', 'Talstraße 4', '70186', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRA 700014',
    'DE999000014', '+49 711 0000014', 'info@widerspruch.example',
    extra_pages={'/kontakt': page('Kontakt', f'{NAV}<p>Zentrale: +49 711 0000099 · Vertrieb: vertrieb@widerspruch.example</p>')},
    note='Kontaktseite nennt andere Nummer als das Impressum')
SITES['widerspruch.example']['pages']['/impressum'] = 'widerspruch.example__impressum.html'
FILES['widerspruch.example__impressum.html'] = imprint_html(
    'Widerspruch Bau GmbH & Co. KG', 'Talstraße 4', '70186', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRA 700014', 'DE999000014', '+49 711 0000014',
    'info@widerspruch.example', extra='<p>Persönlich haftende Gesellschafterin: Widerspruch Verwaltungs GmbH, Amtsgericht Stuttgart HRB 799999</p>')
std('social.example', 'Social Media Agentur GmbH', 'Weg 13', '70188', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700015', 'DE999000015',
    '+49 711 0000015', 'hallo@social.example', claim='<a href="https://www.linkedin.com/company/x">LinkedIn</a> <a href="https://facebook.com/x">Facebook</a>',
    note='Links zu sozialen Netzwerken dürfen nicht verfolgt werden')
site('rechtliches.example', {'/': home('Rechtlich GmbH', 'Alles geregelt.').replace('href="/impressum">Impressum', 'href="/rechtliches.html">Rechtliche Hinweise'),
                             '/rechtliches.html': imprint_html('Rechtlich GmbH', 'Weg 15', '70190', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700016',
                                                               'DE999000016', '+49 711 0000016', 'info@rechtliches.example')},
     expect={'legal_name': 'Rechtlich GmbH', 'register_number': 'HRB 700016', 'zip': '70190', 'vat_id': 'DE999000016',
             'business_phone': '+49 711 0000016', 'business_email': 'info@rechtliches.example'}, note='Link heißt „Rechtliche Hinweise“')
site('onepager.example', {'/': page('Onepager GmbH', '<h1>Onepager GmbH</h1><p>Alles auf einer Seite.</p>' + imprint_html(
    'Onepager GmbH', 'Weg 17', '70191', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700017', 'DE999000017', '+49 711 0000017', 'info@onepager.example'))},
     expect={'legal_name': 'Onepager GmbH', 'register_number': 'HRB 700017', 'zip': '70191'}, note='Impressum steht auf der Startseite')
site('ohne-link.example', {'/': page('Ohne Link GmbH', '<h1>Ohne Link GmbH</h1><p>Kein Footer.</p>'),
                           '/impressum': imprint_html('Ohne Link GmbH', 'Weg 19', '70192', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700018',
                                                      'DE999000018', '+49 711 0000018', 'info@ohne-link.example')},
     expect={'legal_name': 'Ohne Link GmbH', 'register_number': 'HRB 700018', 'zip': '70192'}, note='Kein Link, aber /impressum existiert')
site('english-ltd.example', {'/': home('Example Robotics GmbH', 'Robots for everyone.').replace('>Impressum<', '>Legal notice<'),
                             '/impressum': page('Legal notice', '<h1>Legal notice / Impressum</h1><p>Example Robotics GmbH<br>Weg 21<br>70193 Stuttgart</p>'
                                                '<p>Register court: Amtsgericht Stuttgart, HRB 700019</p><p>VAT ID: DE999000019</p>'
                                                '<p>Phone: +49 711 0000019, Email: info@english-ltd.example</p>')},
     expect={'register_number': 'HRB 700019', 'vat_id': 'DE999000019', 'zip': '70193'}, note='Englisches Impressum')
site('obfusk.example', {'/': home('Obfusk IT GmbH', 'Sicher ist sicher.'),
                        '/impressum': imprint_html('Obfusk IT GmbH', 'Weg 23', '70195', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700020', 'DE999000020',
                                                   '+49 711 0000020', 'X').replace('<a href="mailto:X">X</a>', 'info [at] obfusk [dot] example')},
     expect={'legal_name': 'Obfusk IT GmbH', 'register_number': 'HRB 700020', 'business_email': 'info@obfusk.example'}, note='E-Mail verschleiert')

# 29–30 strukturierte Daten (für Sprint 2) und Karriere
ld = json.dumps({'@context': 'https://schema.org', '@type': 'Organization', 'name': 'Strukturiert Daten GmbH', 'url': 'http://strukturiert.example/',
                 'telephone': '+49 711 0000021', 'email': 'info@strukturiert.example', 'vatID': 'DE999000021',
                 'address': {'@type': 'PostalAddress', 'streetAddress': 'Weg 25', 'postalCode': '70197', 'addressLocality': 'Stuttgart', 'addressCountry': 'DE'},
                 'sameAs': ['https://www.linkedin.com/company/strukturiert']}, ensure_ascii=False)
site('strukturiert.example', {'/': home('Strukturiert Daten GmbH', 'Daten mit Struktur.', '').replace('</head>', f'<script type="application/ld+json">{ld}</script></head>'),
                              '/impressum': imprint_html('Strukturiert Daten GmbH', 'Weg 25', '70197', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700021',
                                                         'DE999000021', '+49 711 0000021', 'info@strukturiert.example')},
     expect={'legal_name': 'Strukturiert Daten GmbH', 'register_number': 'HRB 700021', 'jsonld_type': 'Organization', 'jsonld_phone': '+49 711 0000021'},
     note='JSON-LD Organization auf der Startseite')
job = json.dumps({'@context': 'https://schema.org', '@type': 'JobPosting', 'title': 'Webentwickler (m/w/d)', 'datePosted': '2026-10-20',
                  'hiringOrganization': {'@type': 'Organization', 'name': 'Karriere Werke AG'},
                  'jobLocation': {'@type': 'Place', 'address': {'@type': 'PostalAddress', 'addressLocality': 'Stuttgart', 'postalCode': '70199'}}},
                 ensure_ascii=False)
std('karriere-werke.example', 'Karriere Werke AG', 'Weg 27', '70199', 'Stuttgart', 'Amtsgericht Stuttgart', 'HRB 700022', 'DE999000022',
    '+49 711 0000022', 'info@karriere-werke.example',
    extra_pages={'/karriere': page('Karriere', '<h1>Karriere</h1><p>Wir suchen Webentwickler (m/w/d).</p>', head=f'<script type="application/ld+json">{job}</script>')},
    expect_extra={'jobposting_title': 'Webentwickler (m/w/d)'}, note='Karriereseite mit JSON-LD JobPosting')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.html'):
        old.unlink()
    for old in OUT.glob('*.bin'):
        old.unlink()
    for name, content in FILES.items():
        (OUT / name).write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
    manifest = {'note': 'Fiktive Testwebsites (Sprint 0). Hosts *.example werden im Test auf 127.0.0.1 abgebildet; '
                        'router.intern-weiterleitung.example auf 10.0.0.1 (privat).',
                'resolve': {'router.intern-weiterleitung.example': '10.0.0.1'}, 'sites': SITES}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(len(SITES), 'Hosts,', len(FILES), 'Dateien →', OUT)


if __name__ == '__main__':
    main()
