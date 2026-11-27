"""Dokument-Parser für den isolierten Prozess (R3.1/R3.2, 2.0.0-dev71) – nur Standardbibliothek, keine Paket-Importe.

Diese Datei läuft als eigener Prozess (``python -I -S docparse.py``, gestartet von ``sales_tool.research.documents``):
- Eingabe: Dokument-Bytes über stdin, Art und Grenzen als JSON im ersten Argument. Kein Pfad, kein Netz, keine Dateien.
- Ausgabe: JSON auf stdout – Abschnitte mit Fundstelle (PDF-Seite, XML-Pfad, CSV-Zeile/Spalte, ZIP-Eintrag), Warnungen.
- Schutz: Prüf-Hook (``sys.addaudithook``) sperrt Netz, neue Prozesse, Schreiben und Löschen von Dateien; unter Linux/macOS
  zusätzlich Speicher- und CPU-Grenze (``resource``). Zeitgrenze und Abbruch setzt der aufrufende Prozess.
- PDF: Inhaltsströme nur Flate (mit Größenbremse je Strom und gesamt – PDF-Bomben), Objektströme, Seitenbaum mit Tiefen- und
  Seitengrenze; verschlüsselte PDFs werden abgewiesen; JavaScript, Aktionen und eingebettete Dateien werden nie ausgeführt,
  nur als Warnung gemeldet.
- XML: jede DTD wird abgewiesen (keine externen Entitäten, keine Entitäten-Bomben), Elementgrenze.
- CSV: Zeilen-, Spalten- und Feldgrenzen; Trennzeichen , ; Tab |.
- ZIP: nie entpackt auf die Platte; Einträge mit absolutem Pfad, „..“, Laufwerksbuchstaben oder Steuerzeichen werden
  abgewiesen; Anzahl, Gesamtgröße und Packrate begrenzt (ZIP-Bomben); kein ZIP im ZIP.

Die Funktionen sind auch direkt aufrufbar (Tests); im Programm laufen sie nur im Kindprozess.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import zlib

LIMITS = {
    'max_input': 20_000_000,      # Bytes Eingabe
    'max_stream': 10_000_000,     # Bytes je entpacktem PDF-Strom
    'max_decoded': 60_000_000,    # Bytes entpackt insgesamt (PDF-Ströme, ZIP-Einträge)
    'max_pages': 500,
    'max_segments': 20_000,
    'max_text': 5_000_000,        # Zeichen Text insgesamt in der Ausgabe
    'max_xml_elements': 200_000,
    'max_csv_rows': 100_000,
    'max_csv_columns': 200,
    'max_zip_members': 200,
    'max_zip_ratio': 100,         # entpackt / gepackt je Eintrag
    'max_depth': 50,              # Seitenbaum
}
KINDS = ('pdf', 'xml', 'csv', 'txt', 'zip')
ACTIVE = (b'/JavaScript', b'/JS', b'/Launch', b'/OpenAction', b'/AA', b'/EmbeddedFile', b'/RichMedia', b'/XFA', b'/SubmitForm')


class Rejected(ValueError):
    """Dokument abgewiesen (Angriffsmuster, Grenze überschritten oder unlesbar)."""


class Out:
    def __init__(self, limits):
        self.limits, self.segments, self.warnings, self.chars, self.decoded, self.pages = limits, [], [], 0, 0, 0

    def add(self, text, loc):
        text = (text or '').strip()
        if not text:
            return
        if len(self.segments) >= self.limits['max_segments'] or self.chars + len(text) > self.limits['max_text']:
            self.warn('Textgrenze erreicht – Rest nicht gelesen (Teilergebnis).')
            raise _Full()
        self.chars += len(text)
        self.segments.append({'text': text, 'loc': loc})

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def spend(self, n):
        self.decoded += n
        if self.decoded > self.limits['max_decoded']:
            raise Rejected(f'Entpackt mehr als {self.limits["max_decoded"] // 1_000_000} MB – mögliche Bombe.')


class _Full(Exception):
    pass


def detect(data, filename=''):
    name = (filename or '').lower()
    head = data[:1024].lstrip()
    if b'%PDF-' in data[:1024]:
        return 'pdf'
    if data[:4] == b'PK\x03\x04' or name.endswith('.zip'):
        return 'zip'
    if head.startswith(b'<?xml') or head.startswith(b'<') or name.endswith('.xml'):
        return 'xml'
    if name.endswith(('.csv', '.tsv')):
        return 'csv'
    return 'txt'


# ---------------------------------------------------------------- PDF

def inflate(data, out, limit=None):
    limit = limit or out.limits['max_stream']
    d = zlib.decompressobj()
    try:
        res = d.decompress(data, limit + 1)
    except zlib.error:
        d = zlib.decompressobj(-zlib.MAX_WBITS)
        try:
            res = d.decompress(data, limit + 1)
        except zlib.error as exc:
            raise ValueError('Flate-Daten beschädigt') from exc
    if len(res) > limit or d.unconsumed_tail:
        raise Rejected(f'PDF-Strom entpackt größer als {limit // 1_000_000} MB – mögliche PDF-Bombe.')
    out.spend(len(res))
    return res


OBJ_RE = re.compile(rb'(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b')
REF_RE = re.compile(rb'(\d{1,10})\s+\d{1,5}\s+R\b')


def _split_stream(body):
    """Objektinhalt → (Wörterbuch-Bytes, Strom-Bytes oder None)."""
    pos = body.find(b'stream')
    while pos >= 0 and body[pos - 3:pos] == b'end':
        pos = body.find(b'stream', pos + 6)
    if pos < 0:
        return body, None
    head = body[:pos]
    start = pos + 6
    if body[start:start + 2] == b'\r\n':
        start += 2
    elif body[start:start + 1] in (b'\n', b'\r'):
        start += 1
    end = body.rfind(b'endstream')
    if end < start:
        return head, None
    m = re.search(rb'/Length\s+(\d{1,10})(?!\s+\d+\s+R)', head)
    if m and start + int(m.group(1)) <= end:
        return head, body[start:start + int(m.group(1))]
    return head, body[start:end].rstrip(b'\r\n')


def _filters(head):
    m = re.search(rb'/Filter\s*(\[[^\]]*\]|/\w+)', head)
    return re.findall(rb'/(\w+)', m.group(1)) if m else []


def _decode_stream(head, raw, out):
    filters = _filters(head)
    if not filters:
        return raw
    if all(f in (b'FlateDecode', b'Fl') for f in filters):
        data = raw
        for _ in filters:
            data = inflate(data, out)
        return data
    return None  # Bild- oder andere Filter: nicht ausgewertet


def pdf_objects(data, out):
    """Alle Objekte {Nummer: (Wörterbuch, Strom|None)} inkl. Objektströme. Spätere Fassungen überschreiben frühere."""
    objs = {}
    matches = list(OBJ_RE.finditer(data))
    for i, m in enumerate(matches):
        end = data.find(b'endobj', m.end())
        nxt = matches[i + 1].start() if i + 1 < len(matches) else len(data)
        if end < 0 or end > nxt:
            end = nxt
        head, raw = _split_stream(data[m.end():end])
        objs[int(m.group(1))] = (head, raw)
    for num, (head, raw) in list(objs.items()):
        if raw is None or b'/ObjStm' not in head:
            continue
        try:
            dec = _decode_stream(head, raw, out)
        except ValueError:
            continue
        n = re.search(rb'/N\s+(\d+)', head)
        first = re.search(rb'/First\s+(\d+)', head)
        if dec is None or not n or not first:
            continue
        nums = re.findall(rb'\d+', dec[:int(first.group(1))])
        pairs = [(int(nums[k]), int(nums[k + 1])) for k in range(0, min(len(nums), 2 * int(n.group(1))) - 1, 2)]
        base = int(first.group(1))
        for k, (onum, off) in enumerate(pairs):
            stop = base + pairs[k + 1][1] if k + 1 < len(pairs) else len(dec)
            objs.setdefault(onum, (dec[base + off:stop], None))
    return objs


def _refs(value):
    return [int(x) for x in REF_RE.findall(value or b'')]


def _entry(head, key):
    """Wert eines Schlüssels im Wörterbuch: Verweis(e) oder Array-Inhalt (vereinfacht, genügt für /Kids, /Contents, /Pages)."""
    m = re.search(rb'/' + key + rb'\s*(\[[^\]]*\]|\d+\s+\d+\s+R)', head)
    return m.group(1) if m else b''


def pdf_pages(objs, out):
    """Seiten in Lesereihenfolge über den Seitenbaum (Catalog → Pages → Kids). Leer, wenn kein Baum gefunden wird."""
    root = next((h for h, _ in objs.values() if re.search(rb'/Type\s*/Catalog\b', h)), None)
    if root is None:
        return []
    pages, seen = [], set()

    def walk(num, depth):
        if num in seen or num not in objs:
            return
        if depth > out.limits['max_depth']:
            raise Rejected('Seitenbaum zu tief – beschädigt oder Angriff.')
        seen.add(num)
        head = objs[num][0]
        if re.search(rb'/Type\s*/Pages\b', head):
            for kid in _refs(_entry(head, b'Kids')):
                walk(kid, depth + 1)
        elif re.search(rb'/Type\s*/Page\b', head):
            if len(pages) >= out.limits['max_pages']:
                out.warn(f'Mehr als {out.limits["max_pages"]} Seiten – Rest nicht gelesen (Teilergebnis).')
                return
            pages.append(num)

    for start in _refs(_entry(root, b'Pages'))[:1]:
        walk(start, 0)
    return pages


def _content_of(objs, page, out):
    refs = _refs(_entry(objs[page][0], b'Contents'))
    chunks = []
    for r in refs:
        if r not in objs:
            continue
        head, raw = objs[r]
        if raw is None:  # Array-Objekt mit weiteren Verweisen
            for rr in _refs(head):
                if rr in objs and objs[rr][1] is not None:
                    dec = _decode_stream(objs[rr][0], objs[rr][1], out)
                    if dec:
                        chunks.append(dec)
            continue
        dec = _decode_stream(head, raw, out)
        if dec:
            chunks.append(dec)
    return b'\n'.join(chunks)


ESC = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f', b'(': b'(', b')': b')', b'\\': b'\\'}


def pdf_string(s):
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i:i + 1]
        if c == b'\\' and i + 1 < len(s):
            nxt = s[i + 1:i + 2]
            if nxt in ESC:
                out += ESC[nxt]
                i += 2
                continue
            m = re.match(rb'[0-7]{1,3}', s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            i += 1
            continue
        out += c
        i += 1
    try:
        return out.decode('utf-8')
    except UnicodeDecodeError:
        return out.decode('cp1252', 'replace')


TOKEN_RE = re.compile(rb'\((?:\\.|[^\\)])*\)|\[(?:[^\]]*)\]\s*TJ|T\*|Td|TD|ET|\'|"', re.S)


def content_text(body):
    """Text aus einem Inhaltsstrom (Literal-Strings in Tj/TJ; Zeilenwechsel bei Td/TD/T*/ET)."""
    if b'BT' not in body:
        return ''
    lines, current = [], []
    for tok in TOKEN_RE.finditer(body):
        t = tok.group(0)
        if t.startswith(b'('):
            current.append(pdf_string(t[1:-1]))
        elif t.startswith(b'['):
            current.append(''.join(pdf_string(x[1:-1]) for x in re.findall(rb'\((?:\\.|[^\\)])*\)', t)))
        elif current:
            lines.append(''.join(current))
            current = []
    if current:
        lines.append(''.join(current))
    return '\n'.join(l.strip() for l in lines if l.strip())


def parse_pdf(data, out, loc=None):
    if b'%PDF-' not in data[:1024]:
        raise Rejected('Kein PDF.')
    tail = data[-4096:]
    if re.search(rb'/Encrypt\s+\d+\s+\d+\s+R', data) or b'/Encrypt' in tail:
        raise Rejected('Verschlüsseltes PDF – wird nicht gelesen.')
    if any(a + b' ' in data or a + b'(' in data or a + b'<' in data or a + b'/' in data for a in ACTIVE):
        out.warn('PDF enthält aktive Inhalte (JavaScript, Aktionen oder eingebettete Dateien) – nicht ausgeführt.')
    objs = pdf_objects(data, out)
    pages = pdf_pages(objs, out)
    base = dict(loc or {})
    for i, num in enumerate(pages, 1):
        try:
            text = content_text(_content_of(objs, num, out))
        except ValueError as exc:
            if isinstance(exc, Rejected):
                raise
            out.warn(f'Seite {i}: Inhalt beschädigt.')
            continue
        out.pages = max(out.pages, i)
        out.add(text, {**base, 'kind': 'pdf', 'page': i})
    if not pages or not out.segments:
        # Kein Seitenbaum (oder ohne Text): alle Inhaltsströme in Dateireihenfolge, ohne Seitenangabe
        found = False
        for head, raw in objs.values():
            if raw is None or b'/ObjStm' in head or b'/XRef' in head:
                continue
            try:
                dec = _decode_stream(head, raw, out)
            except ValueError as exc:
                if isinstance(exc, Rejected):
                    raise
                continue
            text = content_text(dec or b'')
            if text:
                found = True
                out.add(text, {**base, 'kind': 'pdf', 'page': None})
        if found and pages:
            out.warn('Seitenzuordnung nicht möglich – Text ohne Seitenangabe.')
        elif found:
            out.warn('Kein Seitenbaum gefunden – Text ohne Seitenangabe.')
    if not out.segments:
        out.warn('PDF ohne auslesbaren Text (z. B. Scan oder eingebettete Schrift) – bitte manuell prüfen.')


# ---------------------------------------------------------------- XML

def parse_xml(data, out, loc=None):
    import xml.etree.ElementTree as ET
    low = data.lower()
    if b'<!doctype' in low or b'<!entity' in low:
        raise Rejected('XML mit DTD/Entitäten wird abgewiesen (Schutz vor XXE und Entitäten-Bomben).')
    base = dict(loc or {})
    count = 0
    stack, counters = [], [{}]
    try:
        for event, el in ET.iterparse(io.BytesIO(data), events=('start', 'end')):
            tag = el.tag.split('}', 1)[-1] if isinstance(el.tag, str) else str(el.tag)
            if event == 'start':
                count += 1
                if count > out.limits['max_xml_elements']:
                    out.warn('Elementgrenze erreicht – Rest nicht gelesen (Teilergebnis).')
                    break
                n = counters[-1].get(tag, 0) + 1
                counters[-1][tag] = n
                stack.append(f'{tag}[{n}]')
                counters.append({})
                path = '/' + '/'.join(stack)
                for k, v in el.attrib.items():
                    out.add(v, {**base, 'kind': 'xml', 'path': f'{path}/@{k.split("}", 1)[-1]}'})
            else:
                path = '/' + '/'.join(stack)
                if el.text and el.text.strip():
                    out.add(el.text, {**base, 'kind': 'xml', 'path': path})
                stack.pop()
                counters.pop()
                el.clear()
    except ET.ParseError as exc:
        raise Rejected(f'XML nicht lesbar ({exc}).') from exc


# ---------------------------------------------------------------- CSV / Text

def _text(data):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', 'replace')


def parse_csv(data, out, loc=None):
    text = _text(data)
    sample = text[:20_000]
    counts = {d: sample.count(d) for d in (';', ',', '\t', '|')}
    delim = max(counts, key=counts.get) if any(counts.values()) else ','
    csv.field_size_limit(100_000)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    base = dict(loc or {})
    header = None
    try:
        for i, row in enumerate(reader, 1):
            if header is None:
                header = [h.strip() or f'Spalte {k + 1}' for k, h in enumerate(row[:out.limits['max_csv_columns']])]
                if len(row) > out.limits['max_csv_columns']:
                    out.warn(f'Mehr als {out.limits["max_csv_columns"]} Spalten – Rest nicht gelesen.')
                continue
            if i - 1 > out.limits['max_csv_rows']:
                out.warn(f'Mehr als {out.limits["max_csv_rows"]} Zeilen – Rest nicht gelesen (Teilergebnis).')
                break
            for k, value in enumerate(row[:len(header)]):
                out.add(value, {**base, 'kind': 'csv', 'row': i, 'column': header[k]})
    except csv.Error as exc:
        raise Rejected(f'CSV nicht lesbar ({exc}).') from exc


def parse_txt(data, out, loc=None):
    base = dict(loc or {})
    for i, line in enumerate(_text(data).splitlines(), 1):
        out.add(line, {**base, 'kind': 'text', 'line': i})


# ---------------------------------------------------------------- ZIP

BAD_NAME = re.compile(r'(^[/\\])|(^[A-Za-z]:)|(^|[/\\])\.\.([/\\]|$)|[\x00-\x1f]')


def safe_member(name):
    return bool(name) and not BAD_NAME.search(name) and len(name) <= 255


def parse_zip(data, out, loc=None):
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise Rejected('ZIP nicht lesbar.') from exc
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > out.limits['max_zip_members']:
        raise Rejected(f'ZIP mit mehr als {out.limits["max_zip_members"]} Einträgen – abgewiesen.')
    for info in infos:
        if not safe_member(info.filename):
            raise Rejected(f'ZIP-Eintrag mit unzulässigem Pfad („{info.filename[:80]}“) – Pfadmanipulation, abgewiesen.')
        if info.flag_bits & 0x1:
            raise Rejected('Verschlüsselter ZIP-Eintrag – wird nicht gelesen.')
    if sum(i.file_size for i in infos) > out.limits['max_decoded']:
        raise Rejected('ZIP entpackt zu groß – mögliche ZIP-Bombe.')
    for info in infos:
        if info.compress_size and info.file_size / info.compress_size > out.limits['max_zip_ratio']:
            raise Rejected(f'ZIP-Eintrag „{info.filename[:80]}“ mit auffälliger Packrate – mögliche ZIP-Bombe.')
        with zf.open(info) as fh:  # angegebene Größe kann lügen: gelesen wird nur bis zur Grenze
            content = fh.read(out.limits['max_stream'] + 1)
        if len(content) > out.limits['max_stream']:
            raise Rejected(f'ZIP-Eintrag „{info.filename[:80]}“ größer als angegeben oder erlaubt – abgewiesen.')
        out.spend(len(content))
        kind = detect(content, info.filename)
        if kind == 'zip':
            out.warn(f'ZIP im ZIP („{info.filename[:80]}“) – nicht gelesen.')
            continue
        member_loc = {**(loc or {}), 'member': info.filename}
        try:
            PARSERS[kind](content, out, member_loc)
        except Rejected as exc:
            out.warn(f'{info.filename[:80]}: {exc}')


PARSERS = {'pdf': parse_pdf, 'xml': parse_xml, 'csv': parse_csv, 'txt': parse_txt, 'zip': parse_zip}


def parse(data, kind=None, filename='', limits=None):
    """Bytes → {'kind', 'pages', 'segments': [{'text', 'loc'}], 'warnings'}. Wirft Rejected bei Angriff oder Grenze."""
    lim = {**LIMITS, **(limits or {})}
    if len(data) > lim['max_input']:
        raise Rejected(f'Dokument größer als {lim["max_input"] // 1_000_000} MB.')
    kind = kind or detect(data, filename)
    if kind not in PARSERS:
        raise Rejected(f'Dokumentart „{kind}“ wird nicht gelesen.')
    out = Out(lim)
    try:
        PARSERS[kind](data, out)
    except _Full:
        pass
    return {'kind': kind, 'pages': out.pages, 'segments': out.segments, 'warnings': out.warnings}


# ---------------------------------------------------------------- Kindprozess

def _sandbox(limits):
    """Im Kindprozess: Netz, neue Prozesse und Schreibzugriffe sperren; Speicher/CPU begrenzen, wo das System es erlaubt."""
    try:
        import resource
        mem = int(limits.get('max_memory') or 0)
        if mem:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        cpu = int(limits.get('max_cpu') or 0)
        if cpu:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    except (ImportError, ValueError, OSError):
        pass  # Windows: keine Speichergrenze über resource – Zeitgrenze und Größenbremsen gelten trotzdem
    import os
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
    blocked = ('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn', 'os.posix_spawn', 'os.fork', 'os.forkpty', 'os.kill',
               'os.remove', 'os.unlink', 'os.rename', 'os.replace', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.chown', 'os.truncate',
               'os.symlink', 'os.link', 'shutil.', 'ctypes.', 'urllib.', 'http.', 'webbrowser.', 'winreg.', 'msvcrt.', '_winapi.',
               'sqlite3.')  # Netzprotokolle (Mail, FTP …) laufen alle über „socket.“ und sind damit gesperrt

    def hook(event, args):
        if event.startswith(blocked):
            raise PermissionError(f'Im Dokument-Parser gesperrt: {event}')
        if event == 'open' and len(args) >= 3:
            mode, flags = args[1], args[2] or 0
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & write_flags):
                raise PermissionError('Im Dokument-Parser gesperrt: Datei schreiben')

    sys.addaudithook(hook)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        opts = json.loads(argv[0]) if argv else {}
    except ValueError:
        opts = {}
    limits = {**LIMITS, **(opts.get('limits') or {})}
    data = sys.stdin.buffer.read(limits['max_input'] + 1)
    _sandbox(limits)
    try:
        result = {'ok': True, **parse(data, opts.get('kind'), opts.get('filename', ''), limits)}
    except Rejected as exc:
        result = {'ok': False, 'error': str(exc), 'reason': 'rejected'}
    except MemoryError:
        result = {'ok': False, 'error': 'Speichergrenze des Dokument-Parsers erreicht – abgewiesen.', 'reason': 'memory'}
    except RecursionError:
        result = {'ok': False, 'error': 'Dokument zu tief verschachtelt – abgewiesen.', 'reason': 'rejected'}
    except Exception as exc:  # noqa: BLE001 – jeder andere Fehler: unlesbar, kein Absturz des Hauptprogramms
        result = {'ok': False, 'error': f'Dokument nicht lesbar ({exc.__class__.__name__}).', 'reason': 'error'}
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
