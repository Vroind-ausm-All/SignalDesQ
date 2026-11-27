"""R3.1/R3.2 (2.0.0-dev71): isolierter Dokument-Parser und Fundstellen in PDF, XML, CSV und ZIP.

Abnahme laut Plan: Angriffsbeispiele (XXE, Bombe, Pfad) werden abgewiesen; korrekte Seiten-/Feldbelege auf Testdokumenten.
Alle Dokumente sind im Test erzeugt und erfunden.
"""
import io
import json
import subprocess
import sys
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool import docparse  # noqa: E402
from sales_tool.research import documents, evidence  # noqa: E402


def make_pdf(pages, compress=True, extra=b''):
    """Kleines gültiges PDF mit Seitenbaum: eine Textzeile je Seite."""
    objs = [b'<< /Type /Catalog /Pages 2 0 R ' + extra + b'>>',
            ('<< /Type /Pages /Kids [' + ' '.join(f'{3 + 2 * i} 0 R' for i in range(len(pages))) + f'] /Count {len(pages)} >>').encode()]
    for i, text in enumerate(pages):
        objs.append(f'<< /Type /Page /Parent 2 0 R /Contents {4 + 2 * i} 0 R >>'.encode())
        content = ('BT /F1 12 Tf 72 712 Td (' + text.replace('(', '\\(').replace(')', '\\)') + ') Tj ET').encode('cp1252')
        if compress:
            content = zlib.compress(content)
            objs.append(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(content) + content + b'\nendstream')
        else:
            objs.append(b'<< /Length %d >>\nstream\n' % len(content) + content + b'\nendstream')
    out = b'%PDF-1.4\n'
    for k, o in enumerate(objs, 1):
        out += b'%d 0 obj\n' % k + o + b'\nendobj\n'
    return out + b'trailer\n<< /Root 1 0 R >>\n%%EOF\n'


def make_zip(members, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class IsolationTests(unittest.TestCase):
    """R3.1: eigener Prozess, Grenzen, Angriffsbeispiele."""

    def rejected(self, data, kind=None, **kw):
        with self.assertRaises(documents.DocumentRejected) as err:
            documents.parse(data, kind, **kw)
        return err.exception

    def test_runs_in_a_separate_process(self):
        with mock.patch.object(docparse, 'parse', side_effect=AssertionError('im Hauptprozess gelesen')):
            doc = documents.parse(make_pdf(['Fiktiv Prozess GmbH']))
        self.assertEqual(doc.text, 'Fiktiv Prozess GmbH')

    def test_xxe_is_rejected(self):
        xxe = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
        self.assertIn('DTD', str(self.rejected(xxe, 'xml')))

    def test_entity_bomb_is_rejected(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><l>&b;</l>'
        self.rejected(bomb, 'xml')

    def test_pdf_flate_bomb_is_rejected(self):
        bomb = zlib.compress(b'\0' * 30_000_000, 9)  # etwa 30 KB gepackt, 30 MB entpackt
        pdf = (b'%PDF-1.4\n' + b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n'
               b'3 0 obj\n<< /Type /Page /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(bomb)
               + bomb + b'\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n')
        self.assertIn('Bombe', str(self.rejected(pdf)))

    def test_zip_bomb_is_rejected(self):
        self.assertIn('Bombe', str(self.rejected(make_zip({'a.txt': b'0' * 5_000_000}))))

    def test_oversized_member_is_rejected(self):
        data = make_zip({'a.txt': b'x' * 50_000}, zipfile.ZIP_STORED)  # gelesen wird höchstens bis zur Grenze, nie mehr
        with self.assertRaises(docparse.Rejected):
            docparse.parse(data, 'zip', limits={'max_stream': 20_000})

    def test_zip_path_traversal_is_rejected(self):
        for name in ('../../boese.txt', '/etc/boese', 'C:/Windows/boese.txt', 'ordner/../../x', '..\\..\\boese.txt'):
            with self.subTest(name):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w') as zf:
                    zf.writestr(zipfile.ZipInfo(name), b'Fiktiv')
                self.assertIn('Pfad', str(self.rejected(buf.getvalue(), 'zip')))

    def test_safe_member_names(self):
        self.assertTrue(docparse.safe_member('bericht/2026/teil-1.pdf'))
        for bad in ('../x', '/x', '\\x', 'C:x', 'a/../../b', 'a\nb', ''):
            self.assertFalse(docparse.safe_member(bad), bad)

    def test_nested_zip_is_not_read(self):
        inner = make_zip({'x.txt': b'Fiktiv'})
        doc = documents.parse(make_zip({'inner.zip': inner, 'liesmich.txt': b'Fiktiv Archiv GmbH'}))
        self.assertEqual(doc.text, 'Fiktiv Archiv GmbH')
        self.assertTrue(any('ZIP im ZIP' in w for w in doc.warnings))

    def test_encrypted_pdf_is_rejected(self):
        pdf = make_pdf(['Geheim']).replace(b'trailer\n<< /Root 1 0 R >>', b'trailer\n<< /Root 1 0 R /Encrypt 9 0 R >>')
        self.assertIn('Verschlüssel', str(self.rejected(pdf)))

    def test_active_content_is_reported_not_run(self):
        doc = documents.parse(make_pdf(['Fiktiv Aktiv GmbH'], extra=b'/OpenAction << /S /JavaScript /JS (app.alert(1)) >> '))
        self.assertEqual(doc.text, 'Fiktiv Aktiv GmbH')
        self.assertTrue(any('aktive Inhalte' in w for w in doc.warnings))

    def test_timeout_ends_the_process(self):
        err = self.rejected(make_pdf(['x']), timeout=0.001)
        self.assertEqual(err.reason, 'timeout')

    def test_too_large_input_is_refused_before_start(self):
        with mock.patch.object(subprocess, 'run', side_effect=AssertionError('gestartet')):
            self.assertEqual(self.rejected(b'x' * (documents.MAX_INPUT + 1)).reason, 'size')

    def test_garbage_is_a_rejection_not_a_crash(self):
        self.rejected(b'<r><unclosed>', 'xml')
        self.assertEqual(documents.parse(b'%PDF-1.4 kaputt').segments, [])

    def test_sandbox_blocks_network_processes_and_writes(self):
        code = ('import sys, json; sys.path.insert(0, sys.argv[1]); import docparse; docparse._sandbox({});\n'
                'res = {}\n'
                'for name, fn in (("socket", lambda: __import__("socket").create_connection(("203.0.113.1", 80), 1)),\n'
                '                 ("prozess", lambda: __import__("subprocess").run(["echo"])),\n'
                '                 ("schreiben", lambda: open("x.txt", "w")),\n'
                '                 ("lesen", lambda: open(sys.argv[2], "rb").read(1))):\n'
                '    try:\n'
                '        fn(); res[name] = "erlaubt"\n'
                '    except PermissionError:\n'
                '        res[name] = "gesperrt"\n'
                '    except Exception as exc:\n'
                '        res[name] = type(exc).__name__\n'
                'print(json.dumps(res))')
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(documents.WORKER.parent), str(documents.WORKER)],
                                 capture_output=True, cwd=tmp, timeout=30, check=True)
            self.assertFalse((Path(tmp) / 'x.txt').exists())
        res = json.loads(out.stdout)
        self.assertEqual(res, {'socket': 'gesperrt', 'prozess': 'gesperrt', 'schreiben': 'gesperrt', 'lesen': 'erlaubt'})

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Speichergrenze über resource nur unter Linux zuverlässig')
    def test_memory_limit_applies(self):
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import docparse; docparse._sandbox({"max_memory": 200 * 1024 * 1024});\n'
                'try:\n    b = bytearray(400 * 1024 * 1024); print("erlaubt")\nexcept MemoryError:\n    print("gesperrt")')
        out = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(documents.WORKER.parent)], capture_output=True, timeout=30)
        self.assertEqual(out.stdout.strip(), b'gesperrt')


class LocatorTests(unittest.TestCase):
    """R3.2: jeder Wert mit Seite bzw. Feldpfad; Belege v2 sind gegen das Dokument prüfbar."""

    def test_pdf_pages(self):
        doc = documents.parse(make_pdf(['Fiktiv Seiten GmbH', 'Registergericht: Amtsgericht Musterstadt', 'Geschäftsführerin: Erika Beispiel']))
        self.assertEqual((doc.kind, doc.pages), ('pdf', 3))
        self.assertEqual(doc.page_text(3), 'Geschäftsführerin: Erika Beispiel')
        ref = documents.document_ref('manager', 'Erika Beispiel', doc, 'https://fiktiv.example/bericht.pdf', 'test:v1')
        self.assertEqual(ref['locator'], {'kind': 'pdf', 'page': 3, 'quote': 'Erika Beispiel'})
        self.assertEqual(evidence.check_ref(ref), [])
        self.assertTrue(documents.verify_document_ref(ref, doc))
        self.assertTrue(evidence.verify_ref(ref, doc.page_text(3)))
        self.assertFalse(evidence.verify_ref(ref, doc.page_text(1)), 'andere Seite – kein Beleg')

    def test_uncompressed_and_object_stream_pdf(self):
        doc = documents.parse(make_pdf(['Fiktiv Ohne Packen GmbH'], compress=False))
        self.assertEqual(doc.segments[0]['loc'], {'kind': 'pdf', 'page': 1})
        # Seitenobjekte in einem Objektstrom (PDF 1.5)
        inner = b'3 0 << /Type /Page /Parent 2 0 R /Contents 4 0 R >>'
        header = b'3 0 '
        objstm = zlib.compress(header + inner[len(header):])
        content = zlib.compress(b'BT (Fiktiv Objektstrom AG) Tj ET')
        pdf = (b'%PDF-1.5\n' + b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n'
               b'5 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Length %d /Filter /FlateDecode >>\nstream\n' % len(objstm) + objstm
               + b'\nendstream\nendobj\n4 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(content) + content
               + b'\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n')
        doc = documents.parse(pdf)
        self.assertEqual([(s['text'], s['loc']['page']) for s in doc.segments], [('Fiktiv Objektstrom AG', 1)])

    def test_pdf_without_page_tree_has_no_page_ref(self):
        content = b'BT (Fiktiv Lose GmbH) Tj ET'
        pdf = b'%PDF-1.4\n' + b'4 0 obj << /Length %d >> stream\n' % len(content) + content + b'\nendstream endobj\n'
        doc = documents.parse(pdf)
        self.assertEqual(doc.text, 'Fiktiv Lose GmbH')
        self.assertIsNone(documents.document_ref('name', 'Fiktiv Lose GmbH', doc, 'https://fiktiv.example/x.pdf', 'test'),
                          'ohne Seite keine PDF-Fundstelle')

    def test_xml_paths(self):
        xml = ('<?xml version="1.0" encoding="UTF-8"?><unternehmen xmlns="urn:fiktiv"><name>Fiktiv XML GmbH</name>'
               '<organe><person rolle="GF">Erika Beispiel</person><person rolle="Prokura">Max Muster</person></organe></unternehmen>').encode()
        doc = documents.parse(xml)
        ref = documents.document_ref('manager', 'Max Muster', doc, 'upload:register.xml', 'test')
        self.assertEqual(ref['locator']['path'], '/unternehmen[1]/organe[1]/person[2]')
        self.assertIn({'text': 'Prokura', 'loc': {'kind': 'xml', 'path': '/unternehmen[1]/organe[1]/person[2]/@rolle'}}, doc.segments)
        self.assertTrue(documents.verify_document_ref(ref, doc))

    def test_csv_rows_and_columns(self):
        data = 'Firma;Ort;Telefon\nFiktiv Eins GmbH;Musterstadt;0123 45678\nFiktiv Zwei KG;Beispielhausen;\n'.encode('cp1252')
        doc = documents.parse(data, filename='liste.csv')
        ref = documents.document_ref('city', 'Beispielhausen', doc, 'upload:liste.csv', 'test')
        self.assertEqual((ref['locator']['row'], ref['locator']['column']), (3, 'Ort'))
        self.assertEqual(evidence.check_ref(ref), [])
        self.assertTrue(documents.verify_document_ref(ref, doc))

    def test_zip_members_carry_their_name(self):
        doc = documents.parse(make_zip({'register/auszug.pdf': make_pdf(['Fiktiv Zip GmbH']), 'liste.csv': b'Firma\nFiktiv Liste AG\n'}))
        ref = documents.document_ref('name', 'Fiktiv Zip GmbH', doc, 'upload:paket.zip', 'test')
        self.assertEqual(ref['locator'], {'kind': 'pdf', 'page': 1, 'quote': 'Fiktiv Zip GmbH', 'member': 'register/auszug.pdf'})
        self.assertTrue(documents.verify_document_ref(ref, doc))

    def test_invented_values_get_no_ref(self):
        doc = documents.parse(make_pdf(['Fiktiv Echt GmbH']))
        self.assertIsNone(documents.document_ref('name', 'Erfundene AG', doc, 'https://fiktiv.example/a.pdf', 'test'))
        ref = documents.document_ref('name', 'Fiktiv Echt GmbH', doc, 'https://fiktiv.example/a.pdf', 'test')
        other = documents.parse(make_pdf(['Fiktiv Echt GmbH', 'Zusatz']))
        self.assertFalse(documents.verify_document_ref(ref, other), 'anderes Dokument (anderer Hash) – kein Beleg')
        broken = {**ref, 'locator': {**ref['locator'], 'quote': 'Erfunden'}}
        self.assertIn('Wortlaut passt nicht zum Wert', evidence.check_ref(broken))

    def test_limits_give_partial_result(self):
        doc = documents.parse(make_pdf([f'Seite {i} Fiktiv' for i in range(1, 8)]), limits={'max_pages': 5})
        self.assertEqual(doc.pages, 5)
        self.assertTrue(any('Teilergebnis' in w for w in doc.warnings))

    def test_imprint_pdf_uses_the_isolated_parser(self):
        from sales_tool import imprint
        with mock.patch.object(documents, 'parse', wraps=documents.parse) as spy:
            text = imprint.pdf_to_text(make_pdf(['Impressum', 'Fiktiv Druck GmbH']))
        self.assertEqual(text, 'Impressum\nFiktiv Druck GmbH')
        spy.assert_called_once()
        bomb = zlib.compress(b'\0' * 30_000_000, 9)
        pdf = b'%PDF-1.4\n' + b'4 0 obj << /Length %d /Filter /FlateDecode >> stream\n' % len(bomb) + bomb + b'\nendstream endobj\n'
        self.assertEqual(imprint.pdf_to_text(pdf), '', 'PDF-Bombe im Impressum: leer statt Speicherüberlauf')


if __name__ == '__main__':
    unittest.main()
