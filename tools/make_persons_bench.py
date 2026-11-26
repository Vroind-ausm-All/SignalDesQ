"""Erzeugt die erfundenen Testseiten für tools/bench_persons.py (R2.1/R2.2/R2.5). Alle Namen, Firmen und Domains sind erfunden."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'persons_bench' / 'pages.json'


def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'


def page(pid, split, body, gold, head=''):
    return {'id': pid, 'split': split, 'url': f'https://www.{pid}.example/team',
            'html': f'<html><head><title>Team</title>{head}</head><body><nav>Startseite Leistungen Kontakt</nav>{body}'
                    f'<footer>Impressum Datenschutz info@{pid}.example</footer></body></html>', 'gold': gold}


PAGES = [
    # ---------------- Abstimmmenge
    page('holzbau-ried', 'abstimmung',
         '<h1>Unser Team</h1><p>Geschäftsführer: Tobias Ried</p><p>Marketingleitung: Sandra Ried</p><p>Zentrale: 0711 000001</p>',
         [['Tobias Ried', 'geschaeftsfuehrung'], ['Sandra Ried', 'marketing_leitung']]),
    page('kanzlei-mertens', 'abstimmung',
         '<h1>Ansprechpartner</h1><div class="team-member"><h3>Dr. Helga Mertens</h3><p>Inhaberin</p></div>'
         '<div class="team-member"><h3>Jonas Albers</h3><p>Leitung Personal</p></div>'
         '<div class="team-member"><h3>Mira Sommer</h3><p>Einkauf</p></div>',
         [['Helga Mertens', 'inhaber'], ['Jonas Albers', 'personal_leitung'], ['Mira Sommer', 'einkauf']]),
    page('metallform-weiss', 'abstimmung', '<h1>Management</h1><p>Wir sind ein Familienunternehmen.</p>',
         [['Clara Weiss', 'geschaeftsfuehrung'], ['Ole Brandt', 'it_leitung']],
         head=ld({'@context': 'https://schema.org', '@type': 'Organization', 'name': 'Metallform Weiss GmbH',
                  'employee': [{'@type': 'Person', 'name': 'Clara Weiss', 'jobTitle': 'Geschäftsführerin'},
                               {'@type': 'Person', 'name': 'Ole Brandt', 'jobTitle': 'Head of IT'}]})),
    page('druckerei-vogt', 'abstimmung',
         '<table><tr><th>Name</th><th>Funktion</th></tr><tr><td>Paul Vogt</td><td>Geschäftsführer</td></tr>'
         '<tr><td>Lina Hahn</td><td>Vertriebsleiterin</td></tr><tr><td>Eva Lorenz</td><td>Prokuristin</td></tr></table>',
         [['Paul Vogt', 'geschaeftsfuehrung'], ['Lina Hahn', 'vertrieb_leitung'], ['Eva Lorenz', 'prokura']]),
    page('agentur-blau', 'abstimmung',
         '<p>Seit 2019 führt Nina Blau als Geschäftsführerin die Agentur. Unterstützt wird sie von Timo Kraft, unserem Head of Marketing.</p>'
         '<blockquote>„Großartige Zusammenarbeit!“ – Peter Klein, Geschäftsführer der Fremdfirma AG</blockquote>',
         [['Nina Blau', 'geschaeftsfuehrung'], ['Timo Kraft', 'marketing_leitung']]),
    page('elektro-sand', 'abstimmung',
         '<div class="mitarbeiter"><strong>Ralf Sand</strong><br>Inhaber und Elektromeister</div>'
         '<div class="mitarbeiter"><strong>Unsere Leistungen</strong><br>Vertrieb und Service</div>',
         [['Ralf Sand', 'inhaber']]),
    # ---------------- Testmenge (erst für die Endmessung)
    page('praezision-lang', 'test',
         '<h2>Geschäftsleitung</h2><p>Martin Lang</p><p>Geschäftsführer</p><h2>Vertrieb</h2><p>Leitung Vertrieb: Anke Busch</p>',
         [['Martin Lang', 'geschaeftsfuehrung'], ['Anke Busch', 'vertrieb_leitung']]),
    page('logistik-nord', 'test',
         '<div itemscope itemtype="https://schema.org/Person"><span itemprop="name">Sven Nord</span>'
         '<span itemprop="jobTitle">Vorstandsvorsitzender</span></div>'
         '<div itemscope itemtype="https://schema.org/Person"><span itemprop="name">Kira Wolff</span>'
         '<span itemprop="jobTitle">Chief Financial Officer</span></div>',
         [['Sven Nord', 'vorstand'], ['Kira Wolff', 'finanzen_leitung']]),
    page('software-pfeil', 'test',
         '<ul class="team"><li class="person"><h4>Dana Pfeil</h4><span>Gründerin &amp; CEO</span></li>'
         '<li class="person"><h4>Felix Roth</h4><span>CTO</span></li><li class="person"><h4>Jana von Berg</h4><span>Marketing Managerin</span></li></ul>',
         [['Dana Pfeil', 'vorstand'], ['Felix Roth', 'it_leitung'], ['Jana von Berg', 'marketing']]),
    page('bau-kern', 'test',
         '<p>Ihr Ansprechpartner für Großprojekte ist Bernd Kern, Betriebsleiter am Standort Süd.</p>'
         '<p>Die Buchhaltung erreichen Sie unter buchhaltung@bau-kern.example.</p>',
         [['Bernd Kern', 'betrieb_leitung']]),
    page('optik-stern', 'test',
         '<table><tr><td>Lea Stern</td><td>Inhaberin, Augenoptikermeisterin</td></tr><tr><td>Tom Stern</td><td>Einkaufsleiter</td></tr></table>'
         '<p>Kundenstimme: „Sehr gute Beratung“ – Marta Fink</p>',
         [['Lea Stern', 'inhaber'], ['Tom Stern', 'einkauf_leitung']]),
    page('reinigung-klar', 'test',
         '<h1>Wir über uns</h1><p>Geschäftsführung</p><p>Olga Klar</p><p>Personalleitung</p><p>Ben Yilmaz</p>',
         [['Olga Klar', 'geschaeftsfuehrung'], ['Ben Yilmaz', 'personal_leitung']]),
]

if __name__ == '__main__':
    OUT.write_text(json.dumps(PAGES, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(OUT, len(PAGES))
