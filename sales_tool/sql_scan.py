"""Statische Auswertung der SQL-Aufrufe im Quelltext (SDQ-010) – Grundlage für das Inventar und die Schreibschutz-Tests.

Liest Python-Dateien als AST; nichts wird ausgeführt. Ein Aufruf gilt als SQL-Aufruf, wenn eine Methode ``execute``,
``executemany`` oder ``executescript`` aufgerufen wird. Der SQL-Text wird aus festen Textteilen gelesen (auch aus f-Strings und
„+“-Verkettungen; eingesetzte Ausdrücke zählen als Lücke). Ist kein Textteil fest, gilt der Aufruf als dynamisch.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from . import data_map

METHODS = {'execute', 'executemany', 'executescript'}
_TABLE_RE = re.compile(r'\b(FROM|JOIN|INTO|UPDATE|TABLE(?:\s+IF\s+(?:NOT\s+)?EXISTS)?)\s+["`]?([A-Za-z_][A-Za-z0-9_]*)', re.I)
_WRITE_TARGET_RE = re.compile(r'\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+["`]?([A-Za-z_][A-Za-z0-9_]*)', re.I)
_SCHEMA_TARGET_RE = re.compile(r'\b(?:ALTER\s+TABLE|DROP\s+TABLE(?:\s+IF\s+EXISTS)?|CREATE\s+(?:VIRTUAL\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?)'
                               r'\s+["`]?([A-Za-z_][A-Za-z0-9_]*)', re.I)
_VARIABLE_TARGET_RE = re.compile(r'\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+\?', re.I)
VARIABLE = '<variabel>'  # Schreibziel wird zur Laufzeit eingesetzt (Tabellenname aus einer Variablen)
_KEYWORDS = {'SET', 'OF', 'ON', 'OR'}  # „DO UPDATE SET“ (Upsert), „UPDATE OF … ON“ (Trigger)
_IGNORE = {'sqlite_master', 'sqlite_sequence', 'pragma_table_info', 'select', 'json_each', 'values'}


def _text(node):
    """(Text, vollständig fest?) aus einem AST-Ausdruck; None, wenn kein Textteil fest ist."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.JoinedStr):
        parts = [v.value if isinstance(v, ast.Constant) else ' ? ' for v in node.values]
        return ''.join(parts), all(isinstance(v, ast.Constant) for v in node.values)
    if isinstance(node, ast.IfExp):
        a, b = _text(node.body), _text(node.orelse)
        if a is None and b is None:
            return None
        return ((a[0] if a else '') + ' ; ' + (b[0] if b else '')), bool(a and a[1] and b and b[1])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        if left is None and right is None:
            return None
        return (left[0] if left else ' ? ') + (right[0] if right else ' ? '), bool(left and left[1] and right and right[1])
    return None


_SQL_START = re.compile(r'\s*(SELECT|INSERT|UPDATE|DELETE|WITH|REPLACE)\s')  # nur Großschreibung: kein Treffer auf „Update fehlgeschlagen“


def _scopes(tree):
    """Jedem Knoten die umschließende Funktion (oder das Modul) zuordnen."""
    owner = {}

    def walk(node, scope):
        for child in ast.iter_child_nodes(node):
            owner[child] = scope
            walk(child, child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else scope)
    walk(tree, tree)
    return owner


def _params(fn):
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = fn.args
        return {x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, *([a.vararg] if a.vararg else []), *([a.kwarg] if a.kwarg else []))}
    return set()


def _assigned(scope, name, tree):
    """Feste Textteile aller Zuweisungen an ``name`` in der Funktion, sonst auf Modulebene."""
    parts = []
    for where in ((scope, tree) if scope is not tree else (tree,)):
        for node in ast.walk(where):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
            if any(isinstance(t, ast.Name) and t.id == name for t in targets) and getattr(node, 'value', None) is not None:
                got = _text(node.value)
                if got:
                    parts.append(got[0])
        if parts:
            break
    return ' '.join(parts)


def _record(rel, line, sql, kind):
    sql_flat = re.sub(r'--[^\n]*', ' ', sql)
    names = [m.group(2) for m in _TABLE_RE.finditer(sql_flat)]
    tables = sorted({n for n in names if n.lower() not in _IGNORE and n.upper() not in _KEYWORDS})
    writes = sorted({m.group(1) for m in _WRITE_TARGET_RE.finditer(sql_flat) if m.group(1).upper() not in _KEYWORDS})
    if _VARIABLE_TARGET_RE.search(sql_flat):
        writes = sorted({*writes, VARIABLE})
    schema = sorted({m.group(1) for m in _SCHEMA_TARGET_RE.finditer(sql_flat)})
    return {'module': rel, 'line': line, 'sql': ' '.join(sql.split())[:300], 'kind': kind, 'dynamic': kind == 'dynamisch',
            'tables': tables, 'writes': writes, 'schema': schema}


def statements(path, rel):
    """Alle SQL-Aufrufe einer Datei. ``kind``: fest | zusammengesetzt | durchgereicht (SQL kommt als Parameter, die Aufrufer
    mit festem Text sind als ``indirekt`` erfasst) | indirekt | dynamisch (nicht statisch lesbar)."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    owner = _scopes(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        is_exec = isinstance(node.func, ast.Attribute) and node.func.attr in METHODS
        arg = node.args[0]
        if not is_exec:
            got = _text(arg)
            if got and _SQL_START.match(got[0]):
                rec = _record(rel, node.lineno, got[0], 'indirekt')
                if rec['tables']:
                    out.append(rec)
            continue
        got = _text(arg)
        if got:
            out.append(_record(rel, node.lineno, got[0], 'fest' if got[1] else 'zusammengesetzt'))
            continue
        if isinstance(arg, ast.Name):
            scope = owner.get(node, tree)
            while scope is not tree and arg.id not in _params(scope) and not _assigned(scope, arg.id, scope):
                scope = owner.get(scope, tree)
            if scope is not tree and arg.id in _params(scope) and not _assigned(scope, arg.id, scope):
                out.append(_record(rel, node.lineno, '', 'durchgereicht'))
                continue
            sql = _assigned(scope, arg.id, tree)
            if sql:
                out.append(_record(rel, node.lineno, sql, 'zusammengesetzt'))
                continue
        out.append(_record(rel, node.lineno, '', 'dynamisch'))
    return out


def scan(root):
    root = Path(root)
    rows = []
    for path in sorted(root.rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        rows.extend(statements(path, path.relative_to(root.parent).as_posix()))
    return rows


def inventory(root):
    rows = scan(root)
    known = set(data_map.TABLES) | set(data_map.CATALOG_TABLES) | set(data_map.DIRECTORY_TABLES)
    tables, modules, unknown = {}, {}, set()
    for r in rows:
        mod = modules.setdefault(r['module'], {'calls': 0, 'dynamic': 0, 'tables': set()})
        mod['calls'] += 1
        mod['dynamic'] += r['dynamic']
        for name in r['tables']:
            if name not in known:
                unknown.add(name)
                continue
            mod['tables'].add(name)
            t = tables.setdefault(name, {'read': set(), 'write': set(), 'schema': set()})
            (t['write'] if name in r['writes'] else t['schema'] if name in r['schema'] else t['read']).add(r['module'])
    return {
        'totals': {'calls': len(rows), 'dynamic': sum(r['dynamic'] for r in rows), 'kinds': {k: sum(r['kind'] == k for r in rows) for k in ('fest', 'zusammengesetzt', 'durchgereicht', 'indirekt', 'dynamisch')}, 'modules': len(modules), 'tables': len(tables)},
        'tables': {k: {'read': sorted(v['read'] - v['write']), 'write': sorted(v['write']), 'schema': sorted(v['schema'])}
                   for k, v in sorted(tables.items())},
        'modules': {k: {'calls': v['calls'], 'dynamic': v['dynamic'], 'tables': sorted(v['tables'])} for k, v in sorted(modules.items())},
        'unknown': sorted(unknown),
    }


def writers(root, table):
    """Module, die Zeilen einer Tabelle schreiben (INSERT/UPDATE/DELETE/REPLACE); Schemaänderungen zählen nicht."""
    return sorted({r['module'] for r in scan(root) if table in r['writes']})
