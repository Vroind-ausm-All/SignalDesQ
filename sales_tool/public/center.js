'use strict';
// v1.6 Research Command Center: Übersicht über alle Recherche-Schritte, Prüfliste, Quellen, Dossier und Übergabe.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  // Sprint A: zwei Gruppen im Tagesablauf – „Kunden finden“ und „Recherchieren“
  const FIND_VIEWS = [['finder', 'Firmen finden'], ['datacheck', 'Import & Prüfung']];
  const RESEARCH_VIEWS = [['center', 'Firmen-Berichte'], ['research', 'URL-Recherche'], ['scoring', 'Website-Scoring'], ['signals', 'Kaufsignale']];
  const STEP_SHORT = {website: 'Web', imprint: 'Impressum', scored: 'Bewertet', signals: 'Signale', hypotheses: 'Verknüpft', decision: 'Entscheider', channel: 'Kontaktweg'};
  const STATUS = {queued: 'wartet', running: 'läuft', paused: 'pausiert', done: 'fertig', failed: 'Fehler', cancelled: 'abgebrochen'};
  let data = null, selected = new Set(), pollTimer = null, detailLead = null, detailTab = 'prep';

  // ------------------------------------------------------------ gemeinsame Unter-Navigation der Recherche-Bereiche
  function injectSubnav() {
    for (const group of [FIND_VIEWS, RESEARCH_VIEWS]) {
      for (const [view] of group) {
        const el = $('#view' + view[0].toUpperCase() + view.slice(1));
        if (!el || el.querySelector('.rc-subnav')) continue;
        el.insertAdjacentHTML('afterbegin', `<nav class="rc-subnav" aria-label="${group === FIND_VIEWS ? 'Kunden finden' : 'Recherchieren'}">${group.map(([v, l]) => `<button type="button" data-rc-sub="${v}">${esc(l)}</button>`).join('')}</nav>`);
      }
    }
  }
  window.markResearchSubnav = function (view) {
    $$('.rc-subnav button').forEach(b => b.classList.toggle('active', b.dataset.rcSub === view));
    const inResearch = RESEARCH_VIEWS.some(([v]) => v === view);
    $('.nav[data-view="center"]').classList.toggle('active', inResearch);
  };

  // ------------------------------------------------------------ Laden
  window.refreshCenter = async function () {
    try {
      const closed = $('#rcFilter').value === 'closed';
      const [ov, jobs, review] = await Promise.all([api('/research-center/overview' + (closed ? '?closed=1' : '')), api('/research-center/jobs'), api('/research-center/review')]);
      data = ov;
      $('#rcNotice').textContent = ov.notice;
      const total = ov.leads.length;
      $('#rcFunnel').innerHTML = Object.entries(ov.step_labels).map(([k, label]) => `<div class="rc-step"><small>${esc(label)}</small><b>${ov.funnel[k]}<span>/${total}</span></b><div class="priority-bar"><i data-w="${total ? Math.round(100 * ov.funnel[k] / total) : 0}"></i></div></div>`).join('') +
        `<div class="rc-step rc-ready"><small>Bereit fürs Gespräch</small><b>${ov.ready}</b></div><div class="rc-step rc-insufficient"><small>Datenlage unzureichend</small><b>${ov.insufficient}</b></div>`;
      applyDataWidths($('#rcFunnel'));
      $('#rcJobs').innerHTML = jobs.jobs.length ? jobs.jobs.slice(0, 14).map(j => `<div class="sales-item"><div><strong>${esc(j.kind)} · ${esc(j.label)}</strong><small>${esc(STATUS[j.status] || j.status)}${j.detail ? ' · ' + esc(j.detail) : ''} · ${esc(j.created_at)}</small>${j.progress !== null ? `<div class="priority-bar dc-bar"><i data-w="${j.progress}"></i></div>` : ''}</div><button type="button" class="btn btn-ghost" data-go-view="${esc(j.view)}">Öffnen</button></div>`).join('') : '<div class="empty">Keine Aufträge in den letzten drei Tagen.</div>';
      applyDataWidths($('#rcJobs'));
      $('#rcReview').innerHTML = review.items.filter(i => i.count).map(i => `<div class="sales-item"><div><strong>${esc(i.label)}</strong><small>${i.count} offen</small></div><button type="button" class="btn btn-ghost" data-go-view="${esc(i.view)}">Prüfen</button></div>`).join('') || '<div class="empty">Alles geprüft.</div>';
      $('#rcNavBadge').textContent = review.total ? String(review.total) : '';
      renderRows();
      clearTimeout(pollTimer);
      if (jobs.active) pollTimer = setTimeout(() => { if (currentView === 'center') window.refreshCenter(); }, 4000);
    } catch (e) { toast(e.message, true); }
  };

  function renderRows() {
    const q = ($('#rcSearch').value || '').toLowerCase(), f = $('#rcFilter').value;
    const rows = data.leads.filter(r => (!q || r.company.toLowerCase().includes(q)) &&
      (f !== 'ready' || r.next_step.step === 'ready') && (f !== 'insufficient' || r.priority === null) && (f !== 'new' || r.signals_new));
    $('#rcRows').innerHTML = rows.length ? rows.map(r => {
      const steps = Object.entries(r.steps).map(([k, v]) => `<span class="rc-chip ${v ? 'done' : ''}" title="${esc(data.step_labels[k])}">${v ? '✓' : '○'} ${esc(STEP_SHORT[k])}</span>`).join('');
      const web = r.website_running ? 'Website: läuft …' : r.website_overall !== null ? `Website <b>${r.website_overall}</b>` : r.website_coverage !== null ? 'Website <span class="sc-unknown">unzureichend</span>' : 'Website –';
      const sig = r.signals ? `Signale ${r.signals_pro} pro${r.signals_contra ? ` · <b class="late">${r.signals_contra} contra</b>` : ''}${r.signals_new ? ` · <span class="rc-new">${r.signals_new} neu</span>` : ''}` : 'Signale –';
      const hyp = r.hypothesis ? `Hypothese: ${esc(r.hypothesis.strength)}` : 'Hypothese –';
      return `<tr><td><input type="checkbox" data-rc-sel="${r.lead_id}" ${selected.has(r.lead_id) ? 'checked' : ''} aria-label="${esc(r.company)} auswählen"></td>
        <td>${window.leadGradeChip ? window.leadGradeChip(r.lead_id) : ''}<b>${esc(r.company)}</b><small>${esc(r.website || 'keine Website')}${r.permission === 'nicht_kontaktieren' ? ' · <b class="late">gesperrt</b>' : ''}</small></td>
        <td>${r.priority === null ? '<span class="sc-unknown">Datenlage unzureichend</span>' : `<b class="rc-prio">${r.priority}</b>`}<details class="rc-basis"><summary>Grundlage</summary><small>${esc(r.priority_basis)}</small></details></td>
        <td><div class="rc-ready-bar"><div class="priority-bar"><i data-w="${r.readiness_pct}"></i></div><small>${r.readiness_pct} %</small></div><div class="rc-chips">${steps}</div></td>
        <td class="rc-findings"><span>${web}${r.website_coverage !== null ? ` <small>Belege ${r.website_coverage} %</small>` : ''}</span><span>${sig}</span><span>${hyp}</span><span>Entscheider ${r.decision_checked}/${r.decision_makers} geprüft</span>${(r.stale || []).length ? `<span class="rc-stale" title="${esc(r.stale.map(x => x.detail).join(' · '))}">veraltet: ${esc(r.stale.map(x => x.label).join(', '))}</span>` : ''}${r.changes_open ? `<span class="rc-new">${r.changes_open} Änderung(en) erkannt</span>` : ''}</td>
        <td><button type="button" class="text-button rc-next" data-rc-next="${r.lead_id}" data-view-target="${esc(r.next_step.view)}">${esc(r.next_step.label)} ↗</button></td>
        <td class="rc-actions"><button type="button" class="btn btn-primary" data-report-open="${r.lead_id}">Bericht</button><button type="button" class="btn btn-ghost" data-rc-open="${r.lead_id}">Details</button></td></tr>`;
    }).join('') : '<tr><td colspan="7" class="empty">Keine Firmen in dieser Auswahl.</td></tr>';
    applyDataWidths($('#rcRows'));
    updateSelection();
  }

  function updateSelection() {
    $('#rcSelInfo').textContent = `${selected.size} ausgewählt`;
    $$('[data-rc-bulk]').forEach(b => { b.disabled = !selected.size; });
  }

  // ------------------------------------------------------------ Stapelaktionen über bestehende Module
  async function bulk(kind) {
    const ids = [...selected].slice(0, 20);
    const rows = data.leads.filter(r => ids.includes(r.lead_id));
    try {
      if (kind === 'imprint') {
        const domains = rows.filter(r => r.website).map(r => r.website).join('\n');
        if (!domains) return toast('Keine Websites in der Auswahl', true);
        const run = await api('/imprint/runs', 'POST', {domains, label: `Research Center: ${rows.length} Firma(en)`, parallel: 2});
        toast(`Impressumsprüfung gestartet (${run.total} Domains) – Ergebnisse in der Prüfwarteschlange`);
      } else if (kind === 'score') {
        const r = await api('/scoring/audits', 'POST', {lead_ids: ids});
        toast(`${r.queued.length} Website-Bewertung(en) gestartet${r.skipped.length ? ` · ${r.skipped.length} übersprungen` : ''}`);
      } else if (kind === 'career') {
        const r = await api('/signals/career-scan', 'POST', {lead_ids: ids});
        toast(`${r.queued.length} Karriereseite(n) werden geprüft${r.skipped.length ? ` · ${r.skipped.length} übersprungen` : ''}`);
      } else if (kind === 'report') {
        const r = await api('/reports', 'POST', {lead_ids: [...selected].slice(0, 50)});
        toast(`${r.queued.length} Firmen-Bericht(e) gestartet${r.skipped.length ? ` · ${r.skipped.length} übersprungen (${r.skipped[0].reason})` : ''}`);
        if (window.refreshReportsList) window.refreshReportsList();
      } else if (kind === 'correlate') {
        let n = 0;
        for (const id of ids) { const r = await api(`/leads/${id}/correlation`, 'POST', {}); n += r.hypotheses.length; }
        toast(`Signale verknüpft: ${n} Hypothese(n) bei ${ids.length} Firma(en)`);
      }
      if (selected.size > 20 && kind !== 'report') toast('Es wurden die ersten 20 ausgewählten Firmen verarbeitet', true);
      window.refreshCenter();
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Detail: Gesprächsvorbereitung & Quellen
  async function openDetail(leadId, tab) {
    detailLead = leadId;
    detailTab = tab || detailTab;
    $$('[data-rc-tab]').forEach(b => b.classList.toggle('active', b.dataset.rcTab === detailTab));
    const row = data.leads.find(r => r.lead_id === leadId);
    $('#rcDetailTitle').textContent = row ? row.company : 'Firma';
    $('#rcDetail').classList.remove('hidden');
    try {
      if (detailTab === 'sources') {
        const src = await api(`/research-center/leads/${leadId}/sources`);
        $('#rcDetailBody').innerHTML = src.length ? `<div class="table-wrap"><table class="acc-table"><thead><tr><th>Modul</th><th>Art</th><th>Beleg</th><th>Datum</th><th>Status</th></tr></thead><tbody>${src.map(s => `<tr><td>${esc(s.module)}</td><td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.type)} ↗</a>` : esc(s.type)}</td><td><small>${esc(s.excerpt)}</small></td><td><small>${esc(s.date)}</small></td><td><small>${esc(s.status || '–')}${s.note ? ' · ' + esc(s.note) : ''}</small></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Noch keine Quellen.</div>';
      } else {
        const d = await api(`/research-center/leads/${leadId}/dossier`);
        $('#rcDetailBody').innerHTML = `<div class="acc-btn-group"><a class="btn btn-ghost" href="/api/research-center/leads/${leadId}/dossier.md" download>Dossier (.md) ↓</a><a class="btn btn-ghost" href="/api/research-center/leads/${leadId}/dossier.json" download>Daten & Quellen (.json) ↓</a><button type="button" class="btn btn-ghost" data-rc-lead="${leadId}">Lead bearbeiten</button><button type="button" class="btn btn-primary" data-rc-handoff="${leadId}">An CRM übergeben</button><button type="button" class="btn btn-ghost" data-rc-offer="${leadId}">Angebot vorbereiten</button></div>
          <p class="muted">Nächster Schritt: ${esc(d.next_step)} · Recherchestand ${d.readiness_pct} % · Priorität ${d.priority === null ? 'Datenlage unzureichend' : d.priority}</p>
          <pre class="rc-dossier">${esc(d.markdown)}</pre>`;
      }
      $('#rcDetail').scrollIntoView({behavior: 'smooth', block: 'start'});
    } catch (e) { toast(e.message, true); }
  }

  async function handoff(leadId) {
    if (!confirm('Recherche an CRM übergeben? Der Lead wird auf „Qualifiziert“ gesetzt und eine Aufgabe angelegt. Es wird nichts versendet.')) return;
    try {
      const r = await api(`/research-center/leads/${leadId}/handoff`, 'POST', {confirm: true});
      toast(`Übergeben: ${r.task} (fällig ${fmtDate(r.due_date)})`);
      await reload(); window.refreshCenter(); openDetail(leadId, 'prep');
    } catch (e) { toast(e.message, true); }
  }

  async function prepareOffer(leadId) {
    try {
      const d = await api(`/research-center/leads/${leadId}/dossier`);
      switchView('quotes');
      if (window.refreshSalesQuotes) await window.refreshSalesQuotes();
      const sel = $('#quoteForm [name=lead_id]');
      sel.value = String(leadId);
      sel.dispatchEvent(new Event('change'));
      if (d.offers[0]) $('#quotePackage').value = d.offers[0].key;
      toast(d.offers[0] ? `Paketvorschlag „${d.offers[0].title}“ – unverbindlich bis zur Bedarfsklärung` : 'Lead übernommen – Paket bitte wählen');
    } catch (e) { toast(e.message, true); }
  }

  function init() {
    if (!$('#viewCenter')) return;
    injectSubnav();
    $('#rcRefresh').addEventListener('click', () => window.refreshCenter());
    $('#rcSearch').addEventListener('input', () => data && renderRows());
    $('#rcFilter').addEventListener('change', () => ($('#rcFilter').value === 'closed' || data?.include_closed) ? window.refreshCenter() : renderRows());
    $('#rcAll').addEventListener('change', e => { $$('[data-rc-sel]').forEach(c => { c.checked = e.target.checked; const id = Number(c.dataset.rcSel); e.target.checked ? selected.add(id) : selected.delete(id); }); updateSelection(); });
    $('#rcDetailClose').addEventListener('click', () => $('#rcDetail').classList.add('hidden'));
    $$('[data-rc-tab]').forEach(b => b.addEventListener('click', () => detailLead && openDetail(detailLead, b.dataset.rcTab)));
    document.body.addEventListener('click', e => {
      const sub = e.target.closest('[data-rc-sub]');
      if (sub) return switchView(sub.dataset.rcSub);
      const go = e.target.closest('[data-go-view]');
      if (go) return switchView(go.dataset.goView);
      const b = e.target.closest('[data-rc-bulk]');
      if (b) return bulk(b.dataset.rcBulk);
      const o = e.target.closest('[data-rc-open]');
      if (o) return openDetail(Number(o.dataset.rcOpen));
      const n = e.target.closest('[data-rc-next]');
      if (n) { const id = Number(n.dataset.rcNext), v = n.dataset.viewTarget; if (v === 'leads') { switchView('leads'); return showModal(id); } if (v === 'center') return openDetail(id, 'prep'); return switchView(v); }
      const l = e.target.closest('[data-rc-lead]');
      if (l) { switchView('leads'); return showModal(Number(l.dataset.rcLead)); }
      const h = e.target.closest('[data-rc-handoff]');
      if (h) return handoff(Number(h.dataset.rcHandoff));
      const of = e.target.closest('[data-rc-offer]');
      if (of) return prepareOffer(Number(of.dataset.rcOffer));
    });
    document.body.addEventListener('change', e => {
      if (!e.target.matches('[data-rc-sel]')) return;
      const id = Number(e.target.dataset.rcSel);
      e.target.checked ? selected.add(id) : selected.delete(id);
      updateSelection();
    });
  }
  init();
})();
