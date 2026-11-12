'use strict';
// v1.18 (Masterplan 2.0, Sprint 5): Firmenakte – Ablauf Recherche → Kontaktweg → Gespräch → Termin → Bedarf → Angebot → Abschluss,
// nächster Schritt mit Direktsprung, Belegabdeckung, Freigabe „Bedarf bestätigt“ und Zeitleiste aus allen Modulen.
// Nichts wird versendet; Kontaktsperren gelten überall.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const qa = (sel, root) => [...root.querySelectorAll(sel)];
  const KIND_ICON = {aktivitaet: '✎', anruf: '☎', termin: '◷', angebot: '€', mail: '✉', aufgabe: '☐', bericht: '◎', beleg: '§', bewertung: '★',
    signal: '⚑', rechnung: '₠', fund: '⌕'};
  const NEED_SKIP = ['anreise', 'aufwand', 'tagessatz'];
  let catalog = null, file = null, filter = '', cdPoll = null;
  const CD_STATE = {uebernommen: ['übertragen', 'ok'], laeuft: ['wird gelesen …', 'wait'], vorschlag: ['Website bestätigen', 'mid'],
    ohne_website: ['keine Website', 'off'], kein_impressum: ['kein Impressum gefunden', 'mid'], fehler: ['nicht gelesen', 'off'], offen: ['noch nicht gelesen', 'mid']};
  const CD_FIELDS = {legal_name: 'Firmenname', street: 'Straße', zip: 'PLZ', city: 'Ort', register_number: 'Registernr.', vat_id: 'USt-IdNr.',
    business_phone: 'Telefon', business_email: 'E-Mail'};

  // v1.19: Firmendaten aus dem Impressum – übertragen? wenn nein: warum, und was hilft
  function companyData(cd) {
    const st = CD_STATE[cd.state] || [cd.state, 'off'];
    const sug = cd.suggestion;
    return `<div class="lf-cd" id="lfCd"><div class="lf-cd-head"><b>Firmendaten aus dem Impressum</b><span class="sw-web ${st[1]}">${esc(st[0])}</span></div>
      <small>${esc(cd.detail)}</small>
      ${cd.filled.length ? `<small class="muted">Im Firmenprofil: ${cd.filled.map(k => esc(CD_FIELDS[k] || k)).join(', ')}${cd.imprint_url ? ` · <a href="${esc(cd.imprint_url)}" target="_blank" rel="noopener noreferrer">Impressum ↗</a>` : ''}</small>` : ''}
      ${sug ? `<div class="lf-cd-sug"><span>Website-Vorschlag: <a href="${esc(sug.website)}" target="_blank" rel="noopener noreferrer">${esc(sug.website.replace(/^https?:\/\//, ''))} ↗</a>
        <small>${esc(sug.evidence || '')}${sug.fields.length ? ` · ${sug.fields.length} Firmendaten schon gelesen` : ''}</small></span>
        <span class="acc-btn-group"><button type="button" class="btn btn-primary" data-lf-sug="bestaetigen">✓ Website passt – Daten übernehmen</button><button type="button" class="text-button" data-lf-sug="ablehnen">✕ passt nicht</button></span></div>` : ''}
      ${cd.can_run && cd.state !== 'laeuft' ? `<button type="button" class="text-button" data-lf-read>${cd.checked_at ? 'Impressum erneut lesen' : 'Impressum jetzt lesen'}</button>` : ''}
      ${cd.auto ? '' : '<small class="muted">Automatische Übertragung ist ausgeschaltet (Datenqualität & System).</small>'}</div>`;
  }

  async function services() {
    if (!catalog) catalog = await api('/pricing/catalog');
    return catalog.groups.flatMap(g => g.services.filter(s => !NEED_SKIP.includes(s.key)).map(s => ({...s, group: g.group})));
  }

  function needRow(svcs, n = {}) {
    const opts = svcs.map(s => `<option value="${esc(s.key)}" ${n.service === s.key ? 'selected' : ''}>${esc(s.group)} · ${esc(s.title)}</option>`).join('');
    return `<div class="lf-need-row"><select data-need="service" aria-label="Leistung">${opts}</select>
      <select data-need="size" aria-label="Umfang"><option value="S">Basis</option><option value="M" selected>Standard</option><option value="L">Umfangreich</option></select>
      <input data-need="qty" type="number" min="1" max="500" value="${n.qty || 1}" aria-label="Menge" class="hidden">
      <button type="button" class="text-button" data-need-del aria-label="Leistung entfernen">✕</button></div>`;
  }

  function syncRow(row, svcs) {
    const s = svcs.find(x => x.key === row.querySelector('[data-need=service]').value);
    row.querySelector('[data-need=size]').classList.toggle('hidden', s?.kind !== 'paket');
    const q = row.querySelector('[data-need=qty]');
    q.classList.toggle('hidden', s?.kind !== 'menge');
    if (s?.kind === 'menge' && Number(q.value) < s.min_qty) q.value = s.min_qty;
  }

  function stepBar(steps) {
    return `<ol class="lf-steps">${steps.map(s => `<li class="${s.done ? 'done' : s.partial ? 'part' : ''}" title="${esc(s.detail)}"><span>${s.done ? '✓' : s.partial ? '◐' : '○'}</span><b>${esc(s.label)}</b><small>${esc(s.detail)}</small></li>`).join('')}</ol>`;
  }

  function coverage(c) {
    return `<div class="lf-cov"><div class="lf-cov-head"><b>Belegabdeckung ${c.pct} %</b><div class="lf-cov-bar"><i data-w="${c.pct}"></i></div></div>
      <ul>${c.items.map(i => `<li class="${i.value >= 1 ? 'ok' : i.value > 0 ? 'mid' : 'off'}"><span>${esc(i.label)}</span><small>${esc(i.detail)}</small>${i.value < 1 ? `<button type="button" class="text-button" data-lf-go='${esc(JSON.stringify(i.action))}'>${esc(i.action.label)}</button>` : ''}</li>`).join('')}</ul>
      <small class="muted">${esc(c.notice)}</small></div>`;
  }

  function timeline(t) {
    const items = t.filter(e => !filter || e.kind === filter);
    const kinds = [...new Set(t.map(e => e.kind))];
    return `<div class="lf-tl-head"><b>Zeitleiste</b><select id="lfFilter" aria-label="Zeitleiste filtern"><option value="">alles (${t.length})</option>${kinds.map(k => `<option value="${k}" ${k === filter ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select></div>
      <ol class="lf-tl">${items.slice(0, 80).map(e => `<li><span class="lf-ic" aria-hidden="true">${KIND_ICON[e.kind] || '•'}</span><div><b>${esc(e.title)}</b><small>${esc(e.at)}${e.detail ? ' · ' + esc(e.detail) : ''}</small></div></li>`).join('') || '<li class="muted">Noch nichts dokumentiert.</li>'}</ol>`;
  }

  async function render(id) {
    const box = $('#leadFile');
    try {
      file = await api(`/leads/${id}/file`);
      if (currentLeadId !== id) return;
      const n = file.next, need = file.need;
      const svcs = await services();
      box.innerHTML = `<div class="lf-head"><div><span class="eyebrow">FIRMENAKTE</span><h3>${esc(file.lead.company)}</h3>
          <small class="muted">Passung ${file.assessment?.fit.grade === 'X' ? 'Ausschluss' : (file.assessment?.fit.grade || 'offen')} · Belege ${file.coverage.pct} % · Phase ${esc(file.lead.stage)}${file.lead.next_step ? ` · nächster Schritt: ${esc(file.lead.next_step)}${file.lead.next_date ? ' (' + esc(fmtDate(file.lead.next_date)) + ')' : ''}` : ''}</small></div>
        <div class="lf-next ${n.blocked ? 'blocked' : ''}"><small>${n.blocked ? 'Gesperrt' : 'Als Nächstes'}</small><b>${esc(n.label)}</b><small>${esc(n.detail || '')}</small>
          ${n.action ? `<button type="button" class="btn btn-primary" data-lf-go='${esc(JSON.stringify(n.action))}'>${esc(n.action.label)} ▶</button>` : ''}</div></div>
        ${file.lock ? `<div class="lf-lock" role="alert">⛔ Kontaktsperre: Firma ist ${esc(file.lock)}. Anruf, Termin, Mail-Entwurf und Angebot sind gesperrt. Ein Widerspruch lässt sich immer dokumentieren.</div>` : ''}
        ${stepBar(file.steps)}
        ${(file.privacy || []).map(p => `<div class="lf-privacy"><span class="sw-web wait">ohne Rechtsform</span> <b>Möglicher Personenbezug.</b>
          <small>Löschfrist bis ${esc(fmtDate(p.retention_until))} · ${p.art14_informed_at ? 'nach Art. 14 informiert am ' + esc(fmtDate(p.art14_informed_at)) : 'Art.-14-Hinweis spätestens beim ersten Kontakt'}</small>
          <span class="acc-btn-group"><button type="button" class="text-button" data-dc-art14="${p.id}">Hinweistext kopieren</button>${p.art14_informed_at ? '' : `<button type="button" class="text-button" data-dc-informed="${p.id}">Als informiert vermerken</button>`}<button type="button" class="text-button" data-dc-extend="${p.id}">Frist verlängern</button></span></div>`).join('')}
        ${window.renderAssessment ? window.renderAssessment(file.assessment) : ''}
        ${companyData(file.company_data)}
        <div class="lf-cols">${coverage(file.coverage)}
          <div class="lf-need" id="lfNeed"><b>Bedarf ${need.confirmed ? `bestätigt <span class="sw-web ok">am ${esc(fmtDate(need.confirmed_at.slice(0, 10)))}</span>` : '<span class="sw-web mid">noch nicht bestätigt</span>'}</b>
            ${need.confirmed ? `<small>${esc(need.note)}</small><ul class="lf-need-list">${need.needs.map(x => `<li>${esc(svcs.find(s => s.key === x.service)?.title || x.service)}${x.size ? ' · ' + esc({S: 'Basis', M: 'Standard', L: 'Umfangreich'}[x.size]) : ''}${x.qty ? ' · ' + x.qty + '×' : ''}</li>`).join('')}</ul>
              <div class="acc-btn-group"><button type="button" class="btn btn-primary" data-lf-quote>Angebot aus bestätigtem Bedarf</button><button type="button" class="text-button" data-lf-reopen>Bedarf neu klären</button></div>`
            : `<small class="muted">Manuelle Freigabe: erst nach einem dokumentierten Gespräch (${need.talks} vorhanden) und mit Problem und Ziel aus der Bedarfsanalyse unten. Ein Angebot gilt erst danach als „beim Kunden“.</small>
              ${file.lock ? '' : `<details class="lf-need-form"><summary>Bedarf bestätigen …</summary><form id="lfNeedForm">
                <label>Bestätigt<select name="via"><option value="gespraech">im Telefonat</option><option value="termin">im Termin</option><option value="schriftlich">schriftlich vom Kunden</option></select></label>
                <label>Was hat der Kunde bestätigt?<textarea name="note" rows="2" maxlength="1000" required placeholder="z. B. Website-Relaunch mit Anfrageformular bis März, Budget freigegeben"></textarea></label>
                <div class="lf-need-rows">${needRow(svcs)}</div><button type="button" class="text-button" data-need-add>+ weitere Leistung</button>
                <button type="submit" class="btn btn-primary">Bedarf bestätigen</button></form></details>`}`}
          </div></div>
        ${file.open_tasks.length ? `<div class="lf-tasks"><b>Offene Aufgaben</b>${file.open_tasks.map(t => `<div><span>${esc(t.title)}</span><small>${t.due_date ? esc(fmtDate(t.due_date)) : 'ohne Termin'}</small><button type="button" class="text-button" data-lf-done="${t.id}">erledigt</button></div>`).join('')}</div>` : ''}
        ${timeline(file.timeline)}`;
      box.classList.remove('hidden');
      applyDataWidths(box);
      qa('.lf-need-row', box).forEach(r => syncRow(r, svcs));
      clearTimeout(cdPoll);
      if (file.company_data.state === 'laeuft') cdPoll = setTimeout(() => { if (currentLeadId === id && !$('#modal').classList.contains('hidden')) render(id).then(() => { if (file.company_data.state !== 'laeuft' && typeof reload === 'function') reload(); }); }, 3000);
    } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; box.classList.remove('hidden'); }
  }

  window.loadLeadFile = function (id) { filter = ''; return render(id); };
  window.refreshLeadFile = function () { if (currentLeadId && !$('#modal').classList.contains('hidden')) return render(currentLeadId); };

  async function go(action) {
    if (action.view === 'quote_from_need') return quoteFromNeed();
    if (action.focus === 'permission') { $('#leadForm [name=permission]')?.focus(); $('#leadForm [name=permission]')?.scrollIntoView({behavior: 'smooth', block: 'center'}); return; }
    if (action.focus === 'need') { const d = $('#lfNeed details'); if (d) { d.open = true; d.scrollIntoView({behavior: 'smooth', block: 'center'}); } else $('#discoveryForm')?.scrollIntoView({behavior: 'smooth'}); return; }
    if (action.view === 'signals' || action.view === 'accounting') { closeModal(); return switchView(action.view); }
    closeModal();
    return window.goAction(action);
  }

  async function quoteFromNeed() {
    try {
      const r = await api(`/leads/${currentLeadId}/quote-from-need`, 'POST', {});
      toast(`Angebotsentwurf ${r.number} aus bestätigtem Bedarf erstellt – prüfen, Steuerstatus setzen, manuell versenden`);
      closeModal();
      if (typeof reload === 'function') reload();
      window.goAction({view: 'quotes', ref: r.id, lead_id: currentLeadId});
    } catch (e) { toast(e.message, true); }
  }

  function init() {
    if (!$('#leadFile')) return;
    const box = $('#leadFile');
    box.addEventListener('click', async e => {
      const g = e.target.closest('[data-lf-go]');
      if (g) return go(JSON.parse(g.dataset.lfGo));
      if (e.target.closest('[data-lf-quote]')) return quoteFromNeed();
      const sg = e.target.closest('[data-lf-sug]');
      if (sg) {
        try {
          const r = await api(`/leads/${currentLeadId}/website-suggestion`, 'POST', {decision: sg.dataset.lfSug});
          toast(sg.dataset.lfSug === 'bestaetigen' ? (r.queued ? 'Website bestätigt – Impressum wird gelesen und ins Firmenprofil übertragen' : 'Website bestätigt – Firmendaten übertragen')
            : 'Vorschlag abgelehnt – diese Domain wird nicht wieder vorgeschlagen');
          if (typeof reload === 'function') await reload();
          const lead = leads.find(x => x.id === currentLeadId);
          if (lead && $('#leadForm')) for (const k of ['website', 'location']) if ($('#leadForm').elements[k]) $('#leadForm').elements[k].value = lead[k] || '';
          render(currentLeadId);
          if (window.loadCompanyFacts) window.loadCompanyFacts(currentLeadId);
        } catch (err) { toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-lf-read]')) {
        try { await api(`/leads/${currentLeadId}/company-data/read`, 'POST', {}); toast('Impressum wird gelesen – Firmendaten kommen in leere Felder'); render(currentLeadId); }
        catch (err) { toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-need-add]')) { const svcs = await services(); box.querySelector('.lf-need-rows').insertAdjacentHTML('beforeend', needRow(svcs)); qa('.lf-need-row', box).forEach(r => syncRow(r, svcs)); return; }
      const del = e.target.closest('[data-need-del]');
      if (del) { if (qa('.lf-need-row', box).length > 1) del.closest('.lf-need-row').remove(); return; }
      if (e.target.closest('[data-lf-reopen]')) {
        const reason = prompt('Warum wird der Bedarf neu geklärt?');
        if (!reason) return;
        try { await api(`/leads/${currentLeadId}/need/reopen`, 'POST', {reason}); toast('Bedarf wieder offen'); render(currentLeadId); } catch (err) { toast(err.message, true); }
        return;
      }
      const d = e.target.closest('[data-lf-done]');
      if (d) { try { await api(`/tasks/${d.dataset.lfDone}`, 'PATCH', {done: true}); render(currentLeadId); } catch (err) { toast(err.message, true); } }
    });
    box.addEventListener('change', async e => {
      if (e.target.id === 'lfFilter') { filter = e.target.value; render(currentLeadId); return; }
      if (e.target.dataset.need === 'service') syncRow(e.target.closest('.lf-need-row'), await services());
    });
    box.addEventListener('submit', async e => {
      if (e.target.id !== 'lfNeedForm') return;
      e.preventDefault();
      const f = e.target.elements, svcs = await services();
      const needs = qa('.lf-need-row', e.target).map(r => {
        const key = r.querySelector('[data-need=service]').value, s = svcs.find(x => x.key === key);
        return s.kind === 'paket' ? {service: key, size: r.querySelector('[data-need=size]').value} : s.kind === 'menge' ? {service: key, qty: Number(r.querySelector('[data-need=qty]').value)} : {service: key};
      });
      try {
        await api(`/leads/${currentLeadId}/need/confirm`, 'POST', {via: f.via.value, note: f.note.value.trim(), needs});
        toast('Bedarf bestätigt – Folgeaufgabe „Festpreisangebot erstellen“ angelegt');
        render(currentLeadId);
        if (typeof reload === 'function') reload();
      } catch (err) { toast(err.message, true); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
