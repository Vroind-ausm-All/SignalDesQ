"""HTTP-Routen für Rechnungen, Ausgaben, E-Rechnung, Auswertungen und Datensicherung."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

from . import accounting as acc
from .einvoice import document_row, document_rows, import_document, xrechnung_xml
from .invoice_print import invoice_html

INVOICE_RE = re.compile(r'/api/accounting/invoices/(\d+)(/finalize|/cancel|/duplicate|/payments|/dunning|/xrechnung)?')


def _q(query, key):
    return query.get(key, [''])[0]


def route_accounting(h, conn, method, route, query, db_path):
    """Gibt True zurück, wenn die Route behandelt wurde."""
    if route == '/api/backup' and method == 'POST':
        h._send(201, create_backup(db_path))
        return True
    if route == '/api/backups' and method == 'GET':
        h._send(200, list_backups(db_path))
        return True
    if not route.startswith('/api/accounting/'):
        return False

    if route == '/api/accounting/catalog' and method == 'GET':
        h._send(200, {
            'units': {k: v[0] for k, v in acc.UNITS.items()}, 'vat_rates': acc.VAT_RATES, 'tax_modes': acc.TAX_MODES,
            'expense_categories': {k: {'label': v[0], 'account': v[1]} for k, v in acc.EXPENSE_CATEGORIES.items()},
            'payment_methods': acc.PAYMENT_METHODS, 'dunning_levels': acc.DUNNING_LEVELS,
            'invoice_statuses': acc.INVOICE_STATUSES,
        })
        return True
    if route == '/api/accounting/overview' and method == 'GET':
        h._send(200, acc.overview(conn))
        return True
    if route == '/api/accounting/settings':
        if method == 'GET':
            h._send(200, acc.get_settings(conn))
            return True
        if method == 'PUT':
            h._send(200, acc.save_settings(conn, h._body()))
            return True
    if route == '/api/accounting/buyer-defaults' and method == 'GET':
        h._send(200, acc.buyer_defaults(conn, _q(query, 'lead_id')))
        return True
    if route == '/api/accounting/invoices':
        if method == 'GET':
            h._send(200, acc.invoice_rows(conn, _q(query, 'status') or None))
            return True
        if method == 'POST':
            h._send(201, acc.create_invoice(conn, h._body()))
            return True
    if route == '/api/accounting/invoices/from-proposal' and method == 'POST':
        h._send(201, acc.invoice_from_proposal(conn, h._body()))
        return True
    match = INVOICE_RE.fullmatch(route)
    if match:
        ident, action = int(match.group(1)), match.group(2)
        if not action:
            if method == 'GET':
                h._send(200, acc.invoice_detail(conn, ident))
            elif method == 'PUT':
                h._send(200, acc.update_invoice(conn, ident, h._body()))
            elif method == 'DELETE':
                h._send(200, acc.delete_draft(conn, ident))
            else:
                return False
            return True
        if action == '/finalize' and method == 'POST':
            if h._body() != {'confirm': True}:
                raise ValueError('Festschreibung ausdrücklich bestätigen: Danach ist die Rechnung unveränderbar.')
            h._send(200, acc.finalize_invoice(conn, ident))
            return True
        if action == '/cancel' and method == 'POST':
            body = h._body()
            if not isinstance(body, dict) or body.get('confirm') is not True or set(body) - {'confirm', 'reason'}:
                raise ValueError('Storno ausdrücklich bestätigen.')
            h._send(201, acc.cancel_invoice(conn, ident, str(body.get('reason') or '')))
            return True
        if action == '/duplicate' and method == 'POST':
            h._send(201, acc.duplicate_invoice(conn, ident))
            return True
        if action == '/payments' and method == 'POST':
            h._send(201, acc.add_payment(conn, ident, h._body()))
            return True
        if action == '/dunning' and method == 'POST':
            h._send(201, acc.create_dunning(conn, ident, h._body()))
            return True
        if action == '/xrechnung' and method == 'GET':
            data, warnings = xrechnung_xml(conn, ident)
            number = conn.execute('SELECT number FROM invoices WHERE id=?', (ident,)).fetchone()['number']
            h._send_raw(200, data, 'application/xml', f'xrechnung-{number}.xml',
                        extra_headers={'X-SignalDesk-Warnings': str(len(warnings))})
            return True
        return False
    pay = re.fullmatch(r'/api/accounting/payments/(\d+)', route)
    if pay and method == 'DELETE':
        h._send(200, acc.delete_payment(conn, int(pay.group(1))))
        return True
    if route == '/api/accounting/expenses':
        if method == 'GET':
            h._send(200, acc.expense_rows(conn, _q(query, 'all') == '1'))
            return True
        if method == 'POST':
            h._send(201, acc.create_expense(conn, h._body()))
            return True
    exp = re.fullmatch(r'/api/accounting/expenses/(\d+)/(paid|cancel)', route)
    if exp and method == 'POST':
        body = h._body()
        if exp.group(2) == 'paid':
            if not isinstance(body, dict) or set(body) != {'paid_on'}:
                raise ValueError('Erwartet: {paid_on}.')
            h._send(200, acc.set_expense_paid(conn, int(exp.group(1)), body['paid_on']))
        else:
            if not isinstance(body, dict) or body.get('confirm') is not True:
                raise ValueError('Storno ausdrücklich bestätigen.')
            h._send(200, acc.cancel_expense(conn, int(exp.group(1)), str(body.get('reason') or '')))
        return True
    if route == '/api/accounting/einvoice/import' and method == 'POST':
        h._send(200, import_document(conn, h._body(max_len=4_500_000)))
        return True
    if route == '/api/accounting/documents' and method == 'GET':
        h._send(200, document_rows(conn))
        return True
    doc = re.fullmatch(r'/api/accounting/documents/(\d+)/xml', route)
    if doc and method == 'GET':
        row = document_row(conn, int(doc.group(1)))
        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', row['filename'])[:120] or 'e-rechnung.xml'
        h._send_raw(200, bytes(row['xml']), 'application/xml', safe_name)
        return True
    if route == '/api/accounting/report' and method == 'GET':
        h._send(200, acc.tax_report(conn, {'from': _q(query, 'from'), 'to': _q(query, 'to'), 'basis': _q(query, 'basis')}))
        return True
    if route == '/api/accounting/sales-kpis' and method == 'GET':
        h._send(200, acc.sales_kpis(conn, {'from': _q(query, 'from'), 'to': _q(query, 'to')}))
        return True
    export = re.fullmatch(r'/api/accounting/export/(rechnungen|ausgaben|buchungen)\.csv', route)
    if export and method == 'GET':
        params = {'from': _q(query, 'from'), 'to': _q(query, 'to')}
        start, end = acc._period(params)
        body = acc.export_csv(conn, export.group(1), params).encode('utf-8')
        h._send_raw(200, body, 'text/csv', f'signaldesk-{export.group(1)}-{start}-bis-{end}.csv')
        return True
    if route == '/api/accounting/audit' and method == 'GET':
        h._send(200, acc.audit_rows(conn))
        return True
    return False


def route_print(h, route, db_path, connect):
    match = re.fullmatch(r'/rechnung/(\d+)', route)
    if not match:
        return False
    with connect(db_path) as conn:
        html = invoice_html(conn, int(match.group(1)))
    h._send_raw(200, html.encode('utf-8'), 'text/html')
    return True


# ---------------------------------------------------------------- Datensicherung

def _backup_dir(db_path):
    return Path(db_path).resolve().parent / 'backups'


def create_backup(db_path):
    target_dir = _backup_dir(db_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    target = target_dir / f'signaldesk-{stamp}.sqlite3'
    counter = 1
    while target.exists():
        target = target_dir / f'signaldesk-{stamp}-{counter}.sqlite3'
        counter += 1
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return {'saved': True, 'path': str(target), 'size_bytes': target.stat().st_size,
            'notice': 'Lokale Kopie erstellt. Zusätzlich extern sichern (USB-Stick, verschlüsselter Cloud-Speicher).'}


def list_backups(db_path):
    folder = _backup_dir(db_path)
    if not folder.exists():
        return {'folder': str(folder), 'backups': []}
    items = sorted(folder.glob('signaldesk-*.sqlite3'), reverse=True)[:50]
    return {'folder': str(folder), 'backups': [{'name': p.name, 'size_bytes': p.stat().st_size,
                                                 'modified': dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')}
                                                for p in items]}
