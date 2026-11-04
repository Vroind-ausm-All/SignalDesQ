'use strict';
// v1.0 Rechnungen & Buchhaltung: lokale Rechnungsstellung, Zahlungen, Ausgaben, UStVA-/EÜR-Vorbereitung.
// Nutzt die Helfer aus app.js ($, $$, api, toast, escapeHTML, leads, switchView, showModal, reload, fmtDate).
(function () {
  const money = c => new Intl.NumberFormat('de-DE', {style: 'currency', currency: 'EUR'}).format((Number(c) || 0) / 100);
  const esc = v => escapeHTML(String(v ?? ''));
  const deDate = s => s ? new Intl.DateTimeFormat('de-DE').format(new Date(`${s}T12:00:00`)) : '–';
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const statusNames = {entwurf: 'Entwurf', offen: 'Offen', teilbezahlt: 'Teilbezahlt', bezahlt: 'Bezahlt', storniert: 'Storniert'};
  const kindNames = {rechnung: 'Rechnung', abschlag: 'Abschlag', schluss: 'Schlussrechnung', storno: 'Storno'};
  const methodNames = {ueberweisung: 'Überweisung', lastschrift: 'Lastschrift', paypal: 'PayPal', bar: 'Bar', sonstiges: 'Sonstiges'};
  let catalog = null, settings = null, currentTab = 'overview', editingId = null;

  async function loadCatalog() {
    if (catalog) return;
    catalog = await api('/accounting/catalog');
    $('#accCategory').innerHTML = Object.entries(catalog.expense_categories)
      .map(([k, c]) => `<option value="${esc(k)}">${esc(c.label)} (${esc(c.account)})</option>`).join('');
  }

  function showTab(tab) {
    currentTab = tab;
    $$('.acc-tab').forEach(b => { b.classList.toggle('active', b.dataset.accTab === tab); b.setAttribute('aria-selected', b.dataset.accTab === tab); });
    $$('.acc-pane').forEach(p => p.classList.toggle('hidden', p.dataset.accPane !== tab));
    ({overview: loadOverview, invoices: loadInvoices, expenses: loadExpenses, report: loadReport, settings: loadSettings})[tab]();
  }

  window.refreshAccounting = async function () {
    try { await loadCatalog(); settings = await api('/accounting/settings'); showTab(currentTab); }
    catch (e) { toast(e.message, true); }
  };

  // ------------------------------------------------------------ Übersicht
  async function loadOverview() {
    try {
      const o = await api('/accounting/overview');
      $('#accOpen').textContent = money(o.open_cents);
      $('#accOpenCount').textContent = `${o.open_count} Rechnung(en) · ${o.drafts} Entwürfe`;
      $('#accOverdue').textContent = money(o.overdue_cents);
      $('#accOverdueCount').textContent = `${o.overdue_count} überfällig`;
      $('#accPaidYear').textContent = money(o.paid_year_cents);
      $('#accInvoicedYear').textContent = `Berechnet netto: ${money(o.invoiced_year_net_cents)}`;
      $('#accQuarter').textContent = money(o.quarter.payable_cents);
      $('#accQuarterRange').textContent = `${deDate(o.quarter.from)} – ${deDate(o.quarter.to)} · Vorbereitung`;
      $('#accWarnings').innerHTML = o.warnings.map(w => `<div class="sales-banner sales-warning acc-warning">${esc(w)}</div>`).join('');
      $('#accOverdueList').innerHTML = o.overdue.length ? o.overdue.map(r => `<div class="sales-item"><div><strong>${esc(r.number)} · ${esc(r.buyer_name)}</strong><small>${money(r.outstanding_cents)} offen · ${r.overdue_days} Tage überfällig${r.dunning_level ? ' · Mahnstufe ' + r.dunning_level : ''}</small></div><button type="button" class="btn btn-ghost" data-acc-open="${r.id}">Öffnen</button></div>`).join('') : '<div class="empty">Keine überfälligen Rechnungen.</div>';
      $('#accUnbilled').innerHTML = o.accepted_without_invoice.length ? o.accepted_without_invoice.map(p => `<div class="sales-item"><div><strong>${esc(p.company)} · ${esc(p.project_label)}</strong><small>Angebot ${esc(p.number)} angenommen</small></div><div class="acc-btn-group"><button type="button" class="btn btn-ghost" data-acc-from-proposal="${p.id}" data-mode="abschlag">Abschlag 40 %</button><button type="button" class="btn btn-primary" data-acc-from-proposal="${p.id}" data-mode="voll">Rechnung</button></div></div>`).join('') : '<div class="empty">Alle angenommenen Angebote sind berechnet.</div>';
      const max = Math.max(1, ...o.months.flatMap(m => [m.invoiced_net_cents, m.paid_cents]));
      $('#accMonths').innerHTML = o.months.map(m => `<div class="acc-bar-col" title="${esc(m.month)}: berechnet ${money(m.invoiced_net_cents)}, bezahlt ${money(m.paid_cents)}"><div class="acc-bar-pair"><i class="inv" data-h="${Math.round(100 * m.invoiced_net_cents / max)}"></i><i class="paid" data-h="${Math.round(100 * m.paid_cents / max)}"></i></div><small>${esc(m.month.slice(5))}/${esc(m.month.slice(2, 4))}</small></div>`).join('');
      // CSP: keine style-Attribute im HTML – Höhen per CSSOM setzen.
      $$('#accMonths [data-h]').forEach(el => { el.style.height = el.dataset.h + '%'; });
    } catch (e) { toast(e.message, true); }
  }

  async function fromProposal(id, mode) {
    try {
      const inv = await api('/accounting/invoices/from-proposal', 'POST', {proposal_id: id, mode, ...(mode === 'abschlag' ? {percent: 40} : {})});
      toast('Rechnungsentwurf aus Angebot erstellt – Empfängeradresse prüfen');
      showTab('invoices');
      openEditor(inv);
    } catch (e) { toast(e.message, true); }
  }
  window.accInvoiceFromProposal = async function (id, mode) { switchView('accounting'); await window.refreshAccounting(); await fromProposal(id, mode); };

  // ------------------------------------------------------------ Rechnungen
  async function loadInvoices() {
    try {
      const status = $('#accInvoiceFilter').value;
      const rows = await api('/accounting/invoices' + (status ? '?status=' + encodeURIComponent(status) : ''));
      $('#accInvoiceRows').innerHTML = rows.length ? rows.map(r => `<tr data-acc-open="${r.id}" tabindex="0"><td><b>${esc(r.number || 'Entwurf #' + r.id)}</b><small>${esc(kindNames[r.kind] || r.kind)}</small></td><td>${esc(r.buyer_name || '–')}</td><td>${deDate(r.issue_date)}<small>${r.due_date ? 'fällig ' + deDate(r.due_date) : ''}</small></td><td>${money(r.gross_cents)}</td><td>${r.outstanding_cents ? money(r.outstanding_cents) : '–'}${r.overdue_days ? `<small class="late">${r.overdue_days} Tage überfällig</small>` : ''}</td><td><span class="pill ${r.status === 'bezahlt' ? 'won' : r.status === 'storniert' ? 'lost' : r.status === 'entwurf' ? '' : 'offer'}">${esc(statusNames[r.status])}</span></td></tr>`).join('') : '<tr><td colspan="6" class="empty">Noch keine Rechnungen. Lege Stammdaten an und erstelle die erste Rechnung – oder übernimm ein angenommenes Angebot.</td></tr>';
    } catch (e) { toast(e.message, true); }
  }

  function leadOptions(selected) {
    return '<option value="">– ohne Lead –</option>' + leads.map(l => `<option value="${l.id}" ${String(l.id) === String(selected ?? '') ? 'selected' : ''}>${esc(l.company)}</option>`).join('');
  }

  function lineRow(line = {}) {
    const units = Object.entries(catalog.units).map(([k, v]) => `<option value="${esc(k)}" ${k === (line.unit || 'pauschal') ? 'selected' : ''}>${esc(v)}</option>`).join('');
    const rates = catalog.vat_rates.map(r => `<option value="${r}" ${r === (line.vat_rate ?? 19) ? 'selected' : ''}>${r} %</option>`).join('');
    const price = line.unit_price_cents !== undefined ? (line.unit_price_cents / 100).toFixed(2).replace('.', ',') : '';
    const qty = String(line.quantity ?? '1').replace('.', ',');
    return `<tr class="acc-line"><td><textarea data-f="description" rows="2" maxlength="1000" required aria-label="Beschreibung">${esc(line.description || '')}</textarea></td><td><input data-f="quantity" value="${esc(qty)}" inputmode="decimal" aria-label="Menge"></td><td><select data-f="unit" aria-label="Einheit">${units}</select></td><td><input data-f="unit_price_eur" value="${esc(price)}" inputmode="decimal" placeholder="0,00" aria-label="Einzelpreis"></td><td><select data-f="vat_rate" aria-label="Steuersatz">${rates}</select></td><td class="num" data-net>–</td><td><button type="button" class="del-task" data-acc-del-line aria-label="Position entfernen">✕</button></td></tr>`;
  }

  const parseNum = v => { const s = String(v ?? '').trim().replace(/\s|€/g, ''); return Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s); };

  function collectLines() {
    return $$('#accLines .acc-line').map(tr => {
      const get = f => tr.querySelector(`[data-f="${f}"]`).value;
      return {description: get('description'), quantity: get('quantity').replace(',', '.'), unit: get('unit'), unit_price_eur: get('unit_price_eur'), vat_rate: Number(get('vat_rate'))};
    });
  }

  function updateTotals() {
    const mode = $('#accTaxMode').value;
    const groups = {};
    $$('#accLines .acc-line').forEach(tr => {
      const q = parseNum(tr.querySelector('[data-f="quantity"]').value), p = parseNum(tr.querySelector('[data-f="unit_price_eur"]').value);
      const rate = mode === 'regel' ? Number(tr.querySelector('[data-f="vat_rate"]').value) : 0;
      tr.querySelector('[data-f="vat_rate"]').disabled = mode !== 'regel';
      const net = Number.isFinite(q * p) ? Math.round(q * p * 100) : 0;
      tr.querySelector('[data-net]').textContent = money(net);
      groups[rate] = (groups[rate] || 0) + net;
    });
    let net = 0, vat = 0, rows = '';
    Object.keys(groups).map(Number).sort((a, b) => b - a).forEach(rate => {
      const v = Math.round(groups[rate] * rate / 100); net += groups[rate]; vat += v;
      if (mode === 'regel') rows += `<small>zzgl. ${rate} % USt. auf ${money(groups[rate])}: ${money(v)}</small>`;
    });
    const note = mode === 'kleinunternehmer' ? '<small>Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.</small>' : mode === 'reverse_charge' ? '<small>Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge).</small>' : '';
    $('#accTotals').innerHTML = `<small>Summe netto ${money(net)}</small>${rows}${note}<strong>${money(net + vat)}</strong><small>Rechnungsbetrag (Vorschau, Server rechnet verbindlich)</small>`;
  }

  function openEditor(inv) {
    editingId = inv?.id || null;
    $('#accDetail').classList.add('hidden');
    $('#accEditor').classList.remove('hidden');
    const f = $('#accInvoiceForm');
    f.reset();
    $('#accLeadSelect').innerHTML = leadOptions(inv?.lead_id);
    const defaults = {buyer_country: 'DE', payment_days: settings?.payment_days ?? 14, tax_mode: settings?.small_business ? 'kleinunternehmer' : 'regel', kind: 'rechnung'};
    const data = {...defaults, ...(inv || {})};
    for (const key of ['kind', 'buyer_name', 'buyer_contact', 'buyer_street', 'buyer_zip', 'buyer_city', 'buyer_country', 'buyer_vat_id', 'buyer_reference', 'buyer_email', 'issue_date', 'service_from', 'service_to', 'tax_mode', 'payment_days', 'intro_text', 'closing_text']) {
      if (f.elements[key] && data[key] !== undefined && data[key] !== null) f.elements[key].value = data[key];
    }
    $('#accLines').innerHTML = (inv?.lines?.length ? inv.lines : [{}]).map(lineRow).join('');
    $('#accEditorTitle').textContent = inv?.id ? `Entwurf #${inv.id} bearbeiten` : 'Neue Rechnung';
    $('#accEditorKicker').textContent = inv?.kind ? (kindNames[inv.kind] || 'Rechnung').toUpperCase() + ' · ENTWURF' : 'ENTWURF';
    ['#accDeleteDraft', '#accPreview', '#accFinalize'].forEach(s => $(s).classList.toggle('hidden', !editingId));
    $('#accChecks').innerHTML = inv?.checks?.length ? `<div class="sales-banner sales-warning"><b>Vor der Festschreibung fehlt:</b><ul>${inv.checks.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>` : (editingId ? '<div class="sales-banner">Pflichtangaben vollständig. Nach der Festschreibung ist die Rechnung unveränderbar.</div>' : '');
    updateTotals();
    $('#accEditor').scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  function invoicePayload() {
    const f = $('#accInvoiceForm'), d = Object.fromEntries(new FormData(f).entries());
    d.lead_id = d.lead_id ? Number(d.lead_id) : null;
    d.payment_days = Number(d.payment_days || 0);
    d.lines = collectLines();
    return d;
  }

  async function saveDraft(e) {
    e?.preventDefault();
    try {
      const inv = await api('/accounting/invoices' + (editingId ? '/' + editingId : ''), editingId ? 'PUT' : 'POST', invoicePayload());
      toast('Entwurf gespeichert');
      openEditor(inv);
      loadInvoices();
      return inv;
    } catch (err) { toast(err.message, true); return null; }
  }

  async function finalize() {
    const inv = await saveDraft();
    if (!inv) return;
    if (inv.checks.length) { toast('Pflichtangaben fehlen – siehe Hinweis', true); return; }
    if (!confirm('Rechnung festschreiben? Danach erhält sie eine fortlaufende Nummer und ist unveränderbar. Korrekturen nur per Storno.')) return;
    try {
      const final = await api(`/accounting/invoices/${inv.id}/finalize`, 'POST', {confirm: true});
      toast(`Rechnung ${final.number} festgeschrieben – nichts wurde versendet`);
      $('#accEditor').classList.add('hidden');
      loadInvoices();
      showDetail(final);
    } catch (err) { toast(err.message, true); }
  }

  async function openInvoice(id) {
    try {
      const inv = await api('/accounting/invoices/' + id);
      if (inv.status === 'entwurf') openEditor(inv); else showDetail(inv);
    } catch (e) { toast(e.message, true); }
  }

  function showDetail(inv) {
    editingId = null;
    $('#accEditor').classList.add('hidden');
    const el = $('#accDetail');
    el.classList.remove('hidden');
    const open = ['offen', 'teilbezahlt'].includes(inv.status);
    const payments = inv.payments.length ? inv.payments.map(p => `<div class="sales-item"><div><strong>${money(p.amount_cents)} · ${deDate(p.paid_on)}</strong><small>${esc(methodNames[p.method] || p.method)}${p.note ? ' · ' + esc(p.note) : ''}</small></div><button type="button" class="btn btn-ghost" data-acc-del-payment="${p.id}">Zurücknehmen</button></div>`).join('') : '<div class="empty">Noch kein Zahlungseingang.</div>';
    const dunning = inv.dunning.map(d => `<details class="acc-dunning"><summary>${esc(catalog.dunning_levels[d.level])} vom ${deDate(d.created_on)} · neue Frist ${deDate(d.new_due_date)}</summary><pre>${esc(d.text)}</pre></details>`).join('');
    el.innerHTML = `<div class="studio-section-head"><div><span class="eyebrow">${esc((kindNames[inv.kind] || '').toUpperCase())} · ${esc(statusNames[inv.status].toUpperCase())}</span><h2>${esc(inv.number)} · ${esc(inv.buyer_name)}</h2></div><button type="button" class="text-button" data-acc-close-detail>Schließen ✕</button></div>
      <div class="acc-detail-grid"><div><small>Rechnungsdatum</small><b>${deDate(inv.issue_date)}</b></div><div><small>Fällig</small><b>${deDate(inv.due_date)}</b></div><div><small>Brutto</small><b>${money(inv.gross_cents)}</b></div><div><small>Offen</small><b>${money(inv.outstanding_cents)}</b>${inv.overdue_days ? `<small class="late">${inv.overdue_days} Tage überfällig</small>` : ''}</div></div>
      ${inv.corrects ? `<p class="muted">Storniert Rechnung ${esc(inv.corrects.number)} vom ${deDate(inv.corrects.issue_date)}.</p>` : ''}${inv.corrected_by.length ? `<p class="muted">Storniert durch ${inv.corrected_by.map(c => `<button type="button" class="text-button" data-acc-open="${c.id}">${esc(c.number)}</button>`).join(', ')}.</p>` : ''}
      <div class="acc-btn-group"><a class="btn btn-primary" href="/rechnung/${inv.id}" target="_blank" rel="noopener">Drucken / PDF ↗</a><a class="btn btn-ghost" href="/api/accounting/invoices/${inv.id}/xrechnung" download>E-Rechnung (XRechnung XML) ↓</a>${inv.kind !== 'storno' ? `<button type="button" class="btn btn-ghost" data-acc-duplicate="${inv.id}">Als neuen Entwurf kopieren</button>` : ''}${inv.status === 'offen' && inv.kind !== 'storno' ? `<button type="button" class="btn btn-danger" data-acc-cancel="${inv.id}">Stornieren</button>` : ''}</div>
      <p class="muted">Die XRechnung ist die rechtlich maßgebliche E-Rechnung für Geschäftskunden; das PDF ist eine Ansichtskopie. Nichts wird automatisch versendet.</p>
      <div class="sales-cols acc-detail-cols">
        <div><div class="sales-subhead">Zahlungseingänge</div><div class="sales-list">${payments}</div>
          ${open ? `<form class="sales-form" id="accPaymentForm"><div class="acc-row3"><label>Betrag €<input name="amount_eur" inputmode="decimal" value="${(inv.outstanding_cents / 100).toFixed(2).replace('.', ',')}"></label><label>Datum<input type="date" name="paid_on" value="${iso(new Date())}"></label><label>Art<select name="method">${catalog.payment_methods.map(m => `<option value="${m}">${esc(methodNames[m])}</option>`).join('')}</select></label></div><label>Notiz (z. B. Kontoauszug-Nr.)<input name="note" maxlength="300"></label><button type="submit" class="btn btn-primary">Zahlung erfassen</button></form>` : ''}</div>
        <div><div class="sales-subhead">Mahnwesen</div>${dunning || '<div class="empty">Keine Mahnungen.</div>'}
          ${open && inv.overdue_days ? `<form class="sales-form" id="accDunningForm"><label>Stufe<select name="level">${Object.entries(catalog.dunning_levels).map(([k, v]) => `<option value="${k}" ${Number(k) === Math.min(3, (inv.dunning.at(-1)?.level || 0) + 1) ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label><label class="quote-addon"><input type="checkbox" name="include_interest"><span>Verzugszinsen (§ 288 Abs. 2 BGB)<small>Basiszins + 9 Prozentpunkte, nur bei Verzug eines Geschäftskunden</small></span></label><label class="quote-addon"><input type="checkbox" name="include_fee"><span>Verzugspauschale 40 € (§ 288 Abs. 5 BGB)</span></label><button type="submit" class="btn btn-ghost">Mahnschreiben entwerfen</button></form><div id="accDunningPreview"></div>` : (open ? '<p class="muted">Noch nicht fällig.</p>' : '')}</div>
      </div>`;
    el.dataset.invoiceId = inv.id;
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  async function submitPayment(form) {
    const id = Number($('#accDetail').dataset.invoiceId), d = Object.fromEntries(new FormData(form).entries());
    try { const inv = await api(`/accounting/invoices/${id}/payments`, 'POST', d); toast('Zahlung erfasst'); showDetail(inv); loadInvoices(); }
    catch (e) { toast(e.message, true); }
  }

  async function submitDunning(form) {
    const id = Number($('#accDetail').dataset.invoiceId);
    const d = {level: Number(form.elements.level.value), include_interest: form.elements.include_interest.checked, include_fee: form.elements.include_fee.checked};
    try {
      const n = await api(`/accounting/invoices/${id}/dunning`, 'POST', d);
      const inv = await api('/accounting/invoices/' + id);
      showDetail(inv);
      $('#accDunningPreview').innerHTML = `<div class="sales-mail-preview"><b>${esc(n.title)} · Gesamt ${money(n.total_cents)}</b><pre>${esc(n.text)}</pre><button type="button" class="btn btn-ghost" data-acc-copy>Text kopieren</button><p class="muted">${esc(n.notice)}</p></div>`;
      $('#accDunningPreview [data-acc-copy]').onclick = () => navigator.clipboard.writeText(n.text).then(() => toast('Mahntext kopiert'));
      toast('Mahnschreiben erstellt – nicht versendet. Wiedervorlage angelegt.');
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Ausgaben
  async function loadExpenses() {
    try {
      const [rows, docs] = await Promise.all([api('/accounting/expenses' + ($('#accShowCancelled').checked ? '?all=1' : '')), api('/accounting/documents')]);
      const f = $('#accExpenseForm');
      if (!f.elements.expense_date.value) f.elements.expense_date.value = iso(new Date());
      $('#accExpenseList').innerHTML = rows.length ? rows.map(x => `<div class="sales-item ${x.status === 'storniert' ? 'acc-cancelled' : ''}"><div><strong>${esc(x.supplier)} · ${money(x.gross_cents)}${x.reverse_charge ? ' · §13b' : ''}</strong><small>${deDate(x.expense_date)} · ${esc(x.category_label)} (${esc(x.account_skr03)}) · ${x.vat_cents ? 'USt. ' + money(x.vat_cents) : 'ohne USt.'} · ${x.paid_on ? 'bezahlt ' + deDate(x.paid_on) : 'unbezahlt'}${x.receipt_ref ? ' · ' + esc(x.receipt_ref) : ''}${x.status === 'storniert' ? ' · STORNIERT' : ''}</small>${x.warnings.map(w => `<small class="late">${esc(w)}</small>`).join('')}</div><div class="acc-btn-group">${x.status === 'aktiv' && !x.paid_on ? `<button type="button" class="btn btn-ghost" data-acc-exp-paid="${x.id}">Heute bezahlt</button>` : ''}${x.document_id ? `<a class="btn btn-ghost" href="/api/accounting/documents/${x.document_id}/xml" download>XML</a>` : ''}${x.status === 'aktiv' ? `<button type="button" class="btn btn-ghost" data-acc-exp-cancel="${x.id}">Storno</button>` : ''}</div></div>`).join('') : '<div class="empty">Noch keine Ausgaben erfasst.</div>';
      $('#accDocuments').innerHTML = docs.length ? docs.slice(0, 15).map(d => `<div class="sales-item"><div><strong>${esc(d.supplier || '?')} · ${esc(d.number || '?')}</strong><small>${esc(d.format)} · ${esc(d.created_at)} · ${d.expense_id ? 'gebucht' : 'noch nicht gebucht'}</small></div><a class="btn btn-ghost" href="/api/accounting/documents/${d.id}/xml" download>Original ↓</a></div>`).join('') : '<div class="empty">Noch keine E-Rechnung importiert.</div>';
    } catch (e) { toast(e.message, true); }
  }

  async function saveExpense(e) {
    e.preventDefault();
    const f = e.target, d = Object.fromEntries(new FormData(f).entries());
    d.reverse_charge = f.elements.reverse_charge.checked;
    d.vat_rate = Number(d.vat_rate);
    if (d.reverse_charge) { d.net_eur = d.gross_eur; delete d.gross_eur; }
    if (!d.document_id) delete d.document_id; else d.document_id = Number(d.document_id);
    for (const k of ['vat_eur', 'paid_on']) if (!d[k]) delete d[k];
    try {
      const x = await api('/accounting/expenses', 'POST', d);
      toast('Ausgabe gespeichert' + (x.warnings.length ? ' – bitte Hinweise beachten' : ''));
      f.reset(); f.elements.document_id.value = ''; f.elements.expense_date.value = iso(new Date()); $('#accEinvoiceResult').innerHTML = '';
      loadExpenses();
    } catch (err) { toast(err.message, true); }
  }

  async function importEinvoice(e) {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 3000000) { toast('Datei zu groß (max. 3 MB)', true); return; }
    try {
      const r = await api('/accounting/einvoice/import', 'POST', {filename: file.name, xml: await file.text()});
      const p = r.parsed, s = r.expense_suggestion, f = $('#accExpenseForm');
      $('#accEinvoiceResult').innerHTML = `<div class="sales-banner"><b>${esc(p.format)}</b> · ${esc(p.supplier)} · Nr. ${esc(p.number)} · ${deDate(p.issue_date)}<br>Netto ${esc(p.net)} · USt. ${esc(p.vat)} · Brutto ${esc(p.gross)} ${esc(p.currency)}${p.due_date ? ' · fällig ' + deDate(p.due_date) : ''}${p.iban ? '<br>IBAN ' + esc(p.iban) : ''}</div>${p.warnings.map(w => `<div class="sales-banner sales-warning">${esc(w)}</div>`).join('')}${r.duplicate ? '<div class="sales-banner sales-warning">Diese Datei wurde bereits importiert.</div>' : ''}${r.already_booked_expense_id ? '<div class="sales-banner sales-warning">Bereits als Ausgabe gebucht.</div>' : ''}<p class="muted">${esc(r.notice)}</p>`;
      if (!r.already_booked_expense_id) {
        f.elements.document_id.value = r.document_id;
        for (const k of ['supplier', 'expense_date', 'receipt_ref', 'description']) f.elements[k].value = s[k] || '';
        f.elements.gross_eur.value = s.reverse_charge ? s.net_eur : s.gross_eur;
        f.elements.vat_eur.value = s.reverse_charge ? '' : s.vat_eur;
        f.elements.vat_rate.value = String(s.vat_rate);
        f.elements.reverse_charge.checked = s.reverse_charge;
        toast('E-Rechnung gelesen – Formular vorausgefüllt, bitte prüfen und speichern');
      }
      loadExpenses();
    } catch (err) { toast(err.message, true); }
  }

  // ------------------------------------------------------------ Auswertung
  function presetRange(kind) {
    const t = new Date(), y = t.getFullYear(), m = t.getMonth(), q = Math.floor(m / 3);
    const r = {
      month: [new Date(y, m, 1), new Date(y, m + 1, 0)], prev_month: [new Date(y, m - 1, 1), new Date(y, m, 0)],
      quarter: [new Date(y, q * 3, 1), new Date(y, q * 3 + 3, 0)], prev_quarter: [new Date(y, q * 3 - 3, 1), new Date(y, q * 3, 0)],
      year: [new Date(y, 0, 1), new Date(y, 11, 31)], prev_year: [new Date(y - 1, 0, 1), new Date(y - 1, 11, 31)],
    }[kind];
    return r ? r.map(iso) : null;
  }

  function applyPreset() {
    const r = presetRange($('#accPreset').value), f = $('#accReportForm');
    if (r) { f.elements.from.value = r[0]; f.elements.to.value = r[1]; }
  }

  async function loadReport(e) {
    e?.preventDefault();
    const f = $('#accReportForm');
    if (!f.elements.from.value) applyPreset();
    const qs = new URLSearchParams({from: f.elements.from.value, to: f.elements.to.value, ...(f.elements.basis.value ? {basis: f.elements.basis.value} : {})}).toString();
    try {
      const [r, k, audit] = await Promise.all([api('/accounting/report?' + qs), api('/accounting/sales-kpis?' + qs), api('/accounting/audit')]);
      $('#accUstva').innerHTML = `<p class="muted">${deDate(r.period.from)} – ${deDate(r.period.to)} · ${r.period.basis === 'ist' ? 'Ist-Versteuerung' : 'Soll-Versteuerung'}</p><table class="acc-table"><thead><tr><th>Kz</th><th>Bezeichnung</th><th class="num">Bemessung</th><th class="num">Steuer</th></tr></thead><tbody>${r.ustva.map(x => `<tr><td><b>${esc(x.kz)}</b></td><td>${esc(x.label)}</td><td class="num">${x.value_eur === null ? '' : x.value_eur.toLocaleString('de-DE') + ' €'}</td><td class="num">${x.tax_cents ? money(x.tax_cents) : ''}</td></tr>`).join('')}</tbody></table><div class="quote-total"><small>Umsatzsteuer ${money(r.output_tax_cents)} − Vorsteuer ${money(r.input_tax_cents)}</small><strong>${money(r.payable_cents)}</strong><small>${r.payable_cents >= 0 ? 'voraussichtliche Zahllast' : 'voraussichtliches Guthaben'}</small></div>${r.hints.map(h => `<div class="sales-banner">${esc(h)}</div>`).join('')}`;
      const eu = r.euer;
      $('#accEuer').innerHTML = `<div class="sales-internal-grid"><span>Betriebseinnahmen (netto, zugeflossen)</span><b>${money(eu.income_net_cents)}</b><span>Vereinnahmte USt.</span><b>${money(eu.income_vat_cents)}</b><span>Betriebsausgaben${r.small_business ? ' (brutto)' : ' (netto)'}</span><b>${money(eu.expenses_cents)}</b><span>Gezahlte Vorsteuer</span><b>${money(eu.input_vat_cents)}</b><span><b>Überschuss (vereinfacht)</b></span><b>${money(eu.profit_cents)}</b></div><div class="sales-subhead">Ausgaben nach Kategorie</div>${eu.by_category.length ? `<div class="sales-internal-grid">${eu.by_category.map(c => `<span>${esc(c.label)}</span><b>${money(c.cents)}</b>`).join('')}</div>` : '<div class="empty">Keine Ausgaben im Zeitraum.</div>'}<p class="muted">${esc(eu.note)}</p>`;
      const route = Object.entries(k.paid_by_contact_route_cents);
      $('#accSalesKpis').innerHTML = `<div class="sales-internal-grid"><span>Angebote erstellt</span><b>${k.proposals_total}</b>${Object.entries(k.proposals_by_status).map(([s, n]) => `<span>· ${esc(s.replaceAll('_', ' '))}</span><b>${n}</b>`).join('')}<span>Annahmequote (angenommen / entschieden)</span><b>${k.acceptance_rate_pct === null ? '–' : k.acceptance_rate_pct + ' %'}</b><span>Ø angenommener Auftragswert netto</span><b>${k.avg_accepted_net_eur === null ? '–' : money(k.avg_accepted_net_eur * 100)}</b><span>Leads gewonnen / verloren</span><b>${k.leads_won} / ${k.leads_lost}</b></div><div class="sales-subhead">Zahlungseingang nach Kontaktweg</div>${route.length ? `<div class="sales-internal-grid">${route.map(([r, c]) => `<span>${esc(r === 'unbekannt' ? 'Kontaktweg nicht erfasst' : ((typeof routeNames !== 'undefined' && routeNames[r]) || r))}</span><b>${money(c)}</b>`).join('')}</div>` : '<div class="empty">Noch keine Zahlungen mit Lead-Zuordnung.</div>'}<p class="muted">${esc(k.note)}</p>`;
      $('#accExports').innerHTML = [['rechnungen', 'Rechnungsausgangsbuch'], ['ausgaben', 'Ausgaben / Belege'], ['buchungen', 'Buchungsliste (SKR03-Vorschlag)']].map(([kind, label]) => `<a class="btn btn-ghost" href="/api/accounting/export/${kind}.csv?${qs}" download>${esc(label)} ↓</a>`).join('');
      $('#accAudit').innerHTML = audit.length ? audit.slice(0, 60).map(a => `<div class="sales-item"><div><strong>${esc(a.entity)} #${esc(a.entity_id)} · ${esc(a.action.replaceAll('_', ' '))}</strong><small>${esc(a.ts)} UTC · ${esc(a.detail)}</small></div></div>`).join('') : '<div class="empty">Noch keine Einträge.</div>';
    } catch (err) { toast(err.message, true); }
  }

  // ------------------------------------------------------------ Stammdaten & Backup
  async function loadSettings() {
    try {
      settings = await api('/accounting/settings');
      const f = $('#accSettingsForm');
      for (const el of f.elements) {
        if (!el.name || !(el.name in settings)) continue;
        if (el.type === 'checkbox') el.checked = !!settings[el.name]; else el.value = settings[el.name] ?? '';
      }
      const b = await api('/backups');
      $('#accBackupInfo').innerHTML = `<small class="muted">Ordner: ${esc(b.folder)}</small>` + (b.backups.length ? b.backups.slice(0, 8).map(x => `<div class="sales-item"><div><strong>${esc(x.name)}</strong><small>${esc(x.modified)} · ${(x.size_bytes / 1024).toFixed(0)} KB</small></div></div>`).join('') : '<div class="empty">Noch kein Backup erstellt.</div>');
    } catch (e) { toast(e.message, true); }
  }

  async function saveSettings(e) {
    e.preventDefault();
    const f = e.target, d = Object.fromEntries(new FormData(f).entries());
    d.small_business = f.elements.small_business.checked;
    d.payment_days = Number(d.payment_days || 0);
    try { settings = await api('/accounting/settings', 'PUT', d); toast(settings.missing.length ? 'Gespeichert – noch fehlend: ' + settings.missing.join(', ') : 'Stammdaten gespeichert'); loadSettings(); }
    catch (err) { toast(err.message, true); }
  }

  // ------------------------------------------------------------ Events
  function init() {
    if (!$('#viewAccounting')) return;
    $$('.acc-tab').forEach(b => b.addEventListener('click', () => showTab(b.dataset.accTab)));
    $('#accInvoiceFilter').addEventListener('change', loadInvoices);
    $('#accNewInvoice').addEventListener('click', () => openEditor(null));
    $('#accEditorClose').addEventListener('click', () => { $('#accEditor').classList.add('hidden'); editingId = null; });
    $('#accAddLine').addEventListener('click', () => { $('#accLines').insertAdjacentHTML('beforeend', lineRow()); updateTotals(); });
    $('#accInvoiceForm').addEventListener('input', updateTotals);
    $('#accInvoiceForm').addEventListener('change', updateTotals);
    $('#accInvoiceForm').addEventListener('submit', saveDraft);
    $('#accFinalize').addEventListener('click', finalize);
    $('#accPreview').addEventListener('click', () => editingId && window.open('/rechnung/' + editingId, '_blank', 'noopener'));
    $('#accDeleteDraft').addEventListener('click', async () => {
      if (!editingId || !confirm('Entwurf löschen?')) return;
      try { await api('/accounting/invoices/' + editingId, 'DELETE'); toast('Entwurf gelöscht'); $('#accEditor').classList.add('hidden'); editingId = null; loadInvoices(); }
      catch (e) { toast(e.message, true); }
    });
    $('#accLeadSelect').addEventListener('change', async e => {
      if (!e.target.value) return;
      try {
        const d = await api('/accounting/buyer-defaults?lead_id=' + e.target.value), f = $('#accInvoiceForm');
        for (const [k, v] of Object.entries(d)) if (f.elements[k] && !f.elements[k].value.trim()) f.elements[k].value = v ?? '';
        if (!f.elements.buyer_name.value.trim() && d.buyer_name) f.elements.buyer_name.value = d.buyer_name;
      } catch (err) { toast(err.message, true); }
    });
    $('#accExpenseForm').addEventListener('submit', saveExpense);
    $('#accEinvoiceFile').addEventListener('change', importEinvoice);
    $('#accShowCancelled').addEventListener('change', loadExpenses);
    $('#accPreset').addEventListener('change', () => { applyPreset(); loadReport(); });
    $('#accReportForm').addEventListener('submit', loadReport);
    $('#accReportForm').addEventListener('input', e => { if (e.target.type === 'date') $('#accPreset').value = 'custom'; });
    $('#accSettingsForm').addEventListener('submit', saveSettings);
    $('#accBackup').addEventListener('click', async () => {
      try { const b = await api('/backup', 'POST', {}); toast('Backup erstellt: ' + b.path); loadSettings(); } catch (e) { toast(e.message, true); }
    });
    $('#viewAccounting').addEventListener('submit', e => {
      if (e.target.id === 'accPaymentForm') { e.preventDefault(); submitPayment(e.target); }
      if (e.target.id === 'accDunningForm') { e.preventDefault(); submitDunning(e.target); }
    });
    $('#viewAccounting').addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-acc-open]')) { e.preventDefault(); openInvoice(Number(e.target.dataset.accOpen)); } });
    $('#viewAccounting').addEventListener('click', async e => {
      const t = e.target;
      const open = t.closest('[data-acc-open]');
      if (open) { if (currentTab !== 'invoices') showTab('invoices'); return openInvoice(Number(open.dataset.accOpen)); }
      const fp = t.closest('[data-acc-from-proposal]');
      if (fp) return fromProposal(Number(fp.dataset.accFromProposal), fp.dataset.mode);
      if (t.closest('[data-acc-del-line]')) { const rows = $$('#accLines .acc-line'); if (rows.length > 1) t.closest('tr').remove(); updateTotals(); return; }
      if (t.closest('[data-acc-close-detail]')) { $('#accDetail').classList.add('hidden'); return; }
      const dup = t.closest('[data-acc-duplicate]');
      if (dup) { try { const inv = await api(`/accounting/invoices/${dup.dataset.accDuplicate}/duplicate`, 'POST', {}); toast('Kopie als Entwurf angelegt – Leistungsdatum ergänzen'); loadInvoices(); openEditor(inv); } catch (err) { toast(err.message, true); } return; }
      const cancel = t.closest('[data-acc-cancel]');
      if (cancel) {
        const reason = prompt('Rechnung stornieren? Es wird eine Stornorechnung mit eigener Nummer erzeugt.\nGrund (optional):');
        if (reason === null) return;
        try { const s = await api(`/accounting/invoices/${cancel.dataset.accCancel}/cancel`, 'POST', {confirm: true, reason}); toast(`Stornorechnung ${s.number} erstellt`); loadInvoices(); showDetail(s); } catch (err) { toast(err.message, true); }
        return;
      }
      const delPay = t.closest('[data-acc-del-payment]');
      if (delPay) { if (!confirm('Zahlung zurücknehmen? Der Vorgang wird protokolliert.')) return; try { const inv = await api('/accounting/payments/' + delPay.dataset.accDelPayment, 'DELETE'); showDetail(inv); loadInvoices(); } catch (err) { toast(err.message, true); } return; }
      const paid = t.closest('[data-acc-exp-paid]');
      if (paid) { try { await api(`/accounting/expenses/${paid.dataset.accExpPaid}/paid`, 'POST', {paid_on: iso(new Date())}); loadExpenses(); } catch (err) { toast(err.message, true); } return; }
      const ec = t.closest('[data-acc-exp-cancel]');
      if (ec) { const reason = prompt('Ausgabe stornieren? Grund:'); if (reason === null) return; try { await api(`/accounting/expenses/${ec.dataset.accExpCancel}/cancel`, 'POST', {confirm: true, reason}); toast('Ausgabe storniert'); loadExpenses(); } catch (err) { toast(err.message, true); } }
    });
  }
  init();
})();
