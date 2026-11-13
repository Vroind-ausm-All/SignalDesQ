'use strict';
// v1.3 Datenprüfung: Impressum-Batch, Prüfwarteschlange, Sperrliste, Datenschutz-Nachweise, Feldbelege im Lead.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const FIELD_LABELS = {legal_name: 'Firmenname', legal_form: 'Rechtsform', street: 'Straße', zip: 'PLZ', city: 'Ort',
    register_court: 'Registergericht', register_number: 'Registernummer', vat_id: 'USt-IdNr.', business_phone: 'Telefon (allgemein)',
    business_email: 'E-Mail (allgemein)', representative: 'Vertretungsberechtigt', related_entity: 'Weitere Gesellschaft', imprint_url: 'Impressum'};
  const ITEM_STATUS = {pending: 'Wartet', running: 'Läuft …', done: 'Ausgelesen', failed: 'Fehler', kein_impressum: 'Kein Impressum',
    gesperrt: 'Gesperrt', abgebrochen: 'Abgebrochen'};
  const RUN_STATUS = {running: 'läuft', paused: 'pausiert', done: 'fertig', cancelled: 'abgebrochen'};
  const QUALITY = {hoch: 'hoch', mittel: 'mittel', niedrig: 'prüfen'};
  let currentRun = null, pollTimer = null, csvText = '';

  window.refreshDatacheck = async function () {
    await Promise.all([loadRuns(), loadSuppression(), loadPrivacy()]).catch(e => toast(e.message, true));
    if (currentRun) openRun(currentRun, true);
  };

  // ------------------------------------------------------------ Aufträge
  async function loadRuns() {
    const runs = await api('/imprint/runs');
    $('#dcRuns').innerHTML = runs.length ? runs.slice(0, 15).map(r => {
      const pct = r.total ? Math.round(100 * r.processed / r.total) : 0;
      return `<div class="sales-item"><div><strong>${esc(r.label)}</strong><small>${r.processed}/${r.total} geprüft · ${esc(RUN_STATUS[r.status] || r.status)}${r.review_open ? ` · <b>${r.review_open} zu prüfen</b>` : ''}${r.counts.failed ? ` · ${r.counts.failed} Fehler` : ''}</small><div class="priority-bar dc-bar"><i data-w="${pct}"></i></div></div><button type="button" class="btn btn-ghost" data-dc-run="${r.id}">Öffnen</button></div>`;
    }).join('') : '<div class="empty">Noch keine Prüfung gestartet.</div>';
    applyDataWidths($('#dcRuns'));
  }

  async function startRun(e) {
    e.preventDefault();
    const f = e.target;
    const body = {domains: f.elements.domains.value, label: f.elements.label.value, parallel: Number(f.elements.parallel.value),
      include_persons: f.elements.include_persons.checked};
    if (csvText) body.csv = csvText;
    try {
      const run = await api('/imprint/runs', 'POST', body);
      toast(`${run.total} Domain(s) werden geprüft${run.skipped_suppressed ? ` · ${run.skipped_suppressed} auf der Sperrliste übersprungen` : ''}${run.rejected.length ? ` · ${run.rejected.length} ungültige Zeile(n) ignoriert` : ''}`);
      f.reset(); csvText = ''; $('#dcCsvInfo').textContent = '';
      await loadRuns();
      openRun(run.id);
    } catch (err) { toast(err.message, true); }
  }

  async function openRun(id, quiet) {
    currentRun = id;
    clearTimeout(pollTimer);
    try {
      const run = await api('/imprint/runs/' + id);
      renderRun(run);
      if (run.status === 'running') pollTimer = setTimeout(() => { if (currentView === 'datacheck') { openRun(id, true); loadRuns(); } }, 2000);
      if (!quiet) $('#dcRunPanel').scrollIntoView({behavior: 'smooth', block: 'start'});
    } catch (err) { toast(err.message, true); }
  }

  function renderRun(run) {
    $('#dcRunTitle').textContent = run.label;
    const pct = run.total ? Math.round(100 * run.processed / run.total) : 0;
    const c = run.counts;
    $('#dcProgress').innerHTML = `<div class="dc-progress"><div class="priority-bar dc-bar"><i data-w="${pct}"></i></div><small>${run.processed}/${run.total} · ${esc(RUN_STATUS[run.status] || run.status)} · ausgelesen ${c.done || 0} · kein Impressum ${c.kein_impressum || 0} · Fehler ${c.failed || 0} · gesperrt ${c.gesperrt || 0} · offen zur Prüfung ${run.review_open}</small></div>`;
    applyDataWidths($('#dcProgress'));
    const act = [];
    if (run.status === 'running') act.push(`<button type="button" class="btn btn-ghost" data-dc-ctl="pause">Pausieren</button>`);
    if (run.status === 'paused') act.push(`<button type="button" class="btn btn-primary" data-dc-ctl="resume">Fortsetzen</button>`);
    if (['running', 'paused'].includes(run.status)) act.push(`<button type="button" class="btn btn-ghost" data-dc-ctl="cancel">Abbrechen</button>`);
    if (c.failed && run.status !== 'running') act.push(`<button type="button" class="btn btn-ghost" data-dc-ctl="retry_failed">Fehlgeschlagene erneut</button>`);
    $('#dcRunActions').innerHTML = act.join('');
    $('#dcItems').innerHTML = run.items.map(renderItem).join('') || '<div class="empty">Keine Einträge.</div>';
  }

  function renderItem(i) {
    const head = `<div class="dc-item-head"><div><b>${esc(i.domain)}</b>${i.company_hint ? ` <small>· ${esc(i.company_hint)}</small>` : ''}<small>${esc(ITEM_STATUS[i.status] || i.status)}${i.error ? ' · ' + esc(i.error) : ''}${i.review_status !== 'offen' ? ' · ' + esc(i.review_status) : ''}</small></div>${i.duplicate_lead_id ? `<span class="pill offer">Bereits im CRM (#${i.duplicate_lead_id}, über ${esc(i.duplicate_reason || 'Domain')})</span>` : ''}</div>`;
    if (i.status !== 'done' || !i.result) {
      return `<article class="dc-item dc-item-muted">${head}${i.log.length ? `<details><summary>Protokoll</summary><ul>${i.log.map(l => `<li>${esc(l)}</li>`).join('')}</ul></details>` : ''}</article>`;
    }
    const r = i.result, open = i.review_status === 'offen';
    const rows = Object.entries(r.fields).filter(([, v]) => v).map(([k, v]) => `<tr><td>${open ? `<input type="checkbox" data-dc-field="${esc(k)}" checked aria-label="${esc(FIELD_LABELS[k])} übernehmen">` : ''}</td><td>${esc(FIELD_LABELS[k] || k)}</td><td><b>${esc(v.value)}</b>${v.note ? `<small>${esc(v.note)}</small>` : ''}</td><td><small class="dc-excerpt">„${esc(v.excerpt)}“</small></td><td><span class="dc-q ${esc(v.quality)}">${esc(QUALITY[v.quality] || v.quality)}</span></td></tr>`).join('');
    const missing = Object.entries(r.fields).filter(([, v]) => !v).map(([k]) => FIELD_LABELS[k] || k);
    const entities = r.entities.length > 1 ? `<div class="dc-entities"><b>Gesellschaften auf dieser Domain:</b>${r.entities.map((e, n) => `<label><input type="radio" name="dc-ent-${i.id}" value="${n}" ${n === 0 ? 'checked' : ''} ${open ? '' : 'disabled'}> ${esc(e.name)}${e.role ? ` <small>(${esc(e.role)})</small>` : ''}${e.register ? ` <small>· ${esc(e.register)}</small>` : ''}</label>`).join('')}</div>` : '';
    const persons = r.representatives.length ? `<div class="dc-persons"><b>Vertretungsberechtigt laut Impressum:</b> ${r.representatives.map(p => `${esc(p.name)} <small>(${esc(p.role)})</small>`).join(', ')}${open ? `<label class="dc-inline"><input type="checkbox" data-dc-persons checked> als Kontakte übernehmen (mit Datenschutz-Nachweis)</label>` : ''}</div>` : '';
    const actions = open ? `<div class="acc-btn-group">${i.duplicate_lead_id ? `<button type="button" class="btn btn-primary" data-dc-review="${i.id}" data-decision="ergaenzen">Lead #${i.duplicate_lead_id} ergänzen</button>` : `<button type="button" class="btn btn-primary" data-dc-review="${i.id}" data-decision="neu">Als neuen Lead übernehmen</button>`}<label class="dc-inline"><input type="checkbox" data-dc-overwrite> bestehende Werte überschreiben</label><button type="button" class="btn btn-ghost" data-dc-review="${i.id}" data-decision="verwerfen">Verwerfen</button><a class="btn btn-ghost" href="${esc(r.imprint_url)}" target="_blank" rel="noopener noreferrer">Impressum öffnen ↗</a></div>` : (i.lead_id ? `<button type="button" class="text-button" data-dc-lead="${i.lead_id}">Lead öffnen ↗</button>` : '');
    return `<article class="dc-item" data-dc-item="${i.id}">${head}${r.warnings.map(w => `<div class="sales-banner sales-warning">${esc(w)}</div>`).join('')}${entities}<div class="table-wrap"><table class="acc-table dc-table"><thead><tr><th></th><th>Feld</th><th>Wert</th><th>Beleg (wörtlich)</th><th>Qualität</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="empty">Keine Felder erkannt.</td></tr>'}</tbody></table></div>${missing.length ? `<small class="muted">Nicht gefunden (bleibt leer): ${esc(missing.join(', '))}</small>` : ''}${persons}${actions}</article>`;
  }

  async function review(btn) {
    const id = Number(btn.dataset.dcReview), card = btn.closest('[data-dc-item]'), decision = btn.dataset.decision;
    const body = {decision};
    if (decision !== 'verwerfen') {
      body.fields = $$(`[data-dc-item="${id}"] [data-dc-field]:checked`).map(c => c.dataset.dcField);
      const ent = card.querySelector(`input[name="dc-ent-${id}"]:checked`);
      if (ent) body.entity_index = Number(ent.value);
      const persons = card.querySelector('[data-dc-persons]');
      body.include_representatives = persons ? persons.checked : false;
      body.overwrite = !!card.querySelector('[data-dc-overwrite]')?.checked;
    }
    try {
      const res = await api(`/imprint/items/${id}/review`, 'POST', body);
      toast(decision === 'verwerfen' ? 'Verworfen' : `Übernommen in Lead #${res.lead_id}: ${res.applied.length} Feld(er)${res.kept_existing.length ? `, ${res.kept_existing.length} bestehende Werte behalten` : ''}${res.persons_added ? `, ${res.persons_added} Person(en)` : ''}`);
      await reload(); openRun(currentRun, true); loadRuns(); loadPrivacy();
    } catch (err) { toast(err.message, true); }
  }

  // ------------------------------------------------------------ Sperrliste & Datenschutz
  async function loadSuppression() {
    const rows = await api('/suppression');
    const kinds = {domain: 'Domain', name: 'Name', register: 'Register', email: 'E-Mail'};
    $('#dcSuppression').innerHTML = rows.length ? rows.slice(0, 50).map(r => `<div class="sales-item"><div><strong>${esc(kinds[r.kind] || r.kind)}: ${esc(r.display || r.value)}</strong><small>${esc(r.reason || '–')} · ${esc(r.created_at)}</small></div><button type="button" class="btn btn-ghost" data-dc-unsup="${r.id}">Aufheben</button></div>`).join('') : '<div class="empty">Sperrliste ist leer.</div>';
  }

  async function loadPrivacy() {
    const rows = await api('/privacy');
    $('#dcPrivacy').innerHTML = rows.length ? rows.slice(0, 50).map(r => `<div class="sales-item"><div><strong>${r.kind === 'einzelunternehmen' ? '<span class="sw-web wait">ohne Rechtsform</span> ' : ''}${esc(r.subject)}${r.kind === 'einzelunternehmen' ? '' : ' · ' + esc(r.company || 'Lead gelöscht')}</strong><small>${esc(r.data_categories)} · Löschfrist ${esc(fmtDate(r.retention_until))} · ${r.art14_informed_at ? 'informiert am ' + esc(fmtDate(r.art14_informed_at)) : (r.overdue_art14 ? '<b class="late">Art.-14-Information überfällig</b>' : 'noch nicht informiert')}</small></div><div class="acc-btn-group"><button type="button" class="btn btn-ghost" data-dc-art14="${r.id}">Hinweistext</button>${r.art14_informed_at ? '' : `<button type="button" class="btn btn-ghost" data-dc-informed="${r.id}">Informiert</button>`}<button type="button" class="btn btn-ghost" data-dc-extend="${r.id}">Frist verlängern</button></div></div>`).join('') : '<div class="empty">Noch keine Personen oder Betriebe ohne Rechtsform übernommen.</div>';
  }

  // ------------------------------------------------------------ Lead-Dialog
  window.loadCompanyFacts = async function (leadId) {
    try {
      const d = await api(`/leads/${leadId}/facts`);
      const c = d.company;
      const addr = [c.street, [c.zip, c.city].filter(Boolean).join(' ')].filter(Boolean).join(', ');
      const rows = [['Firmenname', c.legal_name], ['Rechtsform', c.legal_form], ['Anschrift', addr], ['Register', [c.register_court, c.register_number].filter(Boolean).join(' ')],
        ['USt-IdNr.', c.vat_id], ['Telefon (allgemein)', c.business_phone], ['E-Mail (allgemein)', c.business_email]];
      $('#leadCompanyData').innerHTML = `<div class="sales-internal-grid">${rows.map(([k, v]) => `<span>${esc(k)}</span><b>${v ? esc(v) : '<span class="muted">unbekannt</span>'}</b>`).join('')}</div><small class="muted">${c.imprint_checked_at ? `Impressum geprüft am ${esc(c.imprint_checked_at)} · <a href="${esc(c.imprint_url)}" target="_blank" rel="noopener noreferrer">Quelle ↗</a>` : 'Impressum noch nicht geprüft.'} Allgemeine Kontaktdaten sind keine Werbeeinwilligung.</small>`;
      $('#leadFacts').innerHTML = d.facts.length ? d.facts.map(f => `<div class="sales-item"><div><strong>${esc(f.label)}: ${esc(f.value)}</strong><small>„${esc(f.excerpt || '–')}“ · ${esc(f.source_type)} · ${esc(f.method)} · Qualität ${esc(QUALITY[f.quality] || f.quality)} · geprüft ${esc(f.checked_at)}</small></div><select data-dc-fact="${f.id}" aria-label="Prüfstatus">${['ungeprueft', 'bestaetigt', 'verworfen', 'veraltet'].map(s => `<option value="${s}" ${s === f.status ? 'selected' : ''}>${{ungeprueft: 'ungeprüft', bestaetigt: 'bestätigt', verworfen: 'verworfen', veraltet: 'veraltet'}[s]}</option>`).join('')}</select></div>`).join('') : '<div class="empty">Noch keine Feldbelege.</div>';
    } catch (e) { $('#leadCompanyData').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };

  function init() {
    if (!$('#viewDatacheck')) return;
    $('#dcForm').addEventListener('submit', startRun);
    $('#dcRefresh').addEventListener('click', () => window.refreshDatacheck());
    $('#dcCsv').addEventListener('change', async e => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      const head = await file.slice(0, 2000).text();
      if (/"?LEI"?[,;]"?Entity\.LegalName/.test(head) || file.size > 300000) {
        // GLEIF-Export oder große Firmenliste: als Firmenliste importieren (Sichtung unter „Firmen finden“)
        toast('Große Firmenliste erkannt – wird unter „Finden → Suche & Sichtung“ zum Sichten importiert');
        return window.importCompanyFile ? window.importCompanyFile(file) : toast('Import nicht verfügbar', true);
      }
      csvText = await file.text();
      $('#dcCsvInfo').textContent = `${file.name}: ${Math.max(0, csvText.trim().split(/\r?\n/).length - 1)} Zeilen geladen – wird beim Start mitgeschickt.`;
    });
    $('#dcSupForm').addEventListener('submit', async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target).entries());
      try { await api('/suppression', 'POST', d); e.target.reset(); toast('Sperre gespeichert'); loadSuppression(); } catch (err) { toast(err.message, true); }
    });
    $('#leadImprintBtn').addEventListener('click', async () => {
      if (!currentLeadId) return;
      // v1.19: liest das Impressum im Hintergrund und überträgt belegte Firmendaten automatisch in leere Felder
      try { await api(`/leads/${currentLeadId}/company-data/read`, 'POST', {}); toast('Impressum wird gelesen – Firmendaten kommen automatisch in leere Felder'); if (window.refreshLeadFile) window.refreshLeadFile(); }
      catch (err) { toast(err.message, true); }
    });
    document.body.addEventListener('change', async e => {
      if (!e.target.matches('[data-dc-fact]')) return;
      try { await api('/facts/' + e.target.dataset.dcFact, 'PATCH', {status: e.target.value}); toast('Prüfstatus gespeichert'); await reload(); if (currentLeadId) window.loadCompanyFacts(currentLeadId); }
      catch (err) { toast(err.message, true); }
    });
    // 2.0.0-dev10: Datenschutz-Knöpfe gelten auch in der Firmenakte (Lead-Fenster), daher am Dokument
    document.body.addEventListener('click', async e => {
      const t = e.target;
      const refresh = async () => { if ($('#dcPrivacy')) await loadPrivacy().catch(() => {}); if (window.refreshLeadFile) await window.refreshLeadFile(); };
      const a14 = t.closest('[data-dc-art14]');
      if (a14) { try { const r = await api(`/privacy/${a14.dataset.dcArt14}/art14`); await navigator.clipboard.writeText(r.text).catch(() => {}); alert(r.text + '\n\n(In die Zwischenablage kopiert, falls erlaubt.)'); } catch (err) { toast(err.message, true); } return; }
      const inf = t.closest('[data-dc-informed]');
      if (inf) { try { await api(`/privacy/${inf.dataset.dcInformed}/informed`, 'POST', {}); toast('Als informiert vermerkt'); await refresh(); } catch (err) { toast(err.message, true); } return; }
      const ext = t.closest('[data-dc-extend]');
      if (ext) {
        const reason = prompt('Frist um 12 Monate verlängern. Grund (wird im Nachweis vermerkt), z. B. „Gespräch am 12.11. vereinbart“:');
        if (!reason) return;
        try { const r = await api(`/privacy/${ext.dataset.dcExtend}/extend`, 'POST', {months: 12, reason: reason.trim()}); toast('Frist verlängert bis ' + fmtDate(r.retention_until)); await refresh(); } catch (err) { toast(err.message, true); }
      }
    });
    $('#viewDatacheck').addEventListener('click', async e => {
      const t = e.target;
      const run = t.closest('[data-dc-run]');
      if (run) return openRun(Number(run.dataset.dcRun));
      const ctl = t.closest('[data-dc-ctl]');
      if (ctl && currentRun) { try { renderRun(await api(`/imprint/runs/${currentRun}/${ctl.dataset.dcCtl}`, 'POST', {})); openRun(currentRun, true); loadRuns(); } catch (err) { toast(err.message, true); } return; }
      const rev = t.closest('[data-dc-review]');
      if (rev) return review(rev);
      const lead = t.closest('[data-dc-lead]');
      if (lead) { switchView('leads'); return showModal(Number(lead.dataset.dcLead)); }
      const un = t.closest('[data-dc-unsup]');
      if (un) { const reason = prompt('Sperre wirklich aufheben? Bitte Grund angeben (z. B. „schriftliche Einwilligung vom …“):'); if (!reason) return; try { await api('/suppression/' + un.dataset.dcUnsup, 'DELETE', {reason}); toast('Sperre aufgehoben – im Protokoll vermerkt'); loadSuppression(); } catch (err) { toast(err.message, true); } return; }
    });
  }
  init();
})();
