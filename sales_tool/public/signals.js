'use strict';
// v1.5 Kaufsignale: Import, Signal-Feed, Zuordnung, Korrelation – alles mit Belegen, nichts automatisch übernommen.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const KIND = {register: 'Register', job: 'Stelle', manual: 'Lead-Signal', website: 'Website'};
  const POL = {pro: 'Pro-Hinweis', contra: 'Gegenhinweis', neutral: 'neutral'};
  const STRENGTH = {'mehrere unabhängige Hinweise': 'stark', 'einzelner Hinweis': 'einzeln', schwach: 'schwach'};
  let csv = {reg: '', job: ''}, careerSel = new Set(), currentLead = null, scanPoll = null;

  const date = s => s ? fmtDate(s.slice(0, 10)) : 'unbekannt';

  function signalCard(s, opts = {}) {
    const src = s.sources.map(x => x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.type)}</a>` : esc(x.type)).join(' · ');
    const assign = !s.lead_id && !opts.compact ? `<label class="dc-inline">Lead zuordnen <select data-sg-assign="${s.id}"><option value="">–</option>${leads.filter(l => l.stage !== 'gesperrt').map(l => `<option value="${l.id}">${esc(l.company)}</option>`).join('')}</select></label>` : '';
    return `<article class="sg-card ${s.polarity === 'contra' ? 'sg-contra' : ''} ${s.is_new ? 'sg-new' : ''}">
      <div class="dc-item-head"><div><span class="sg-kind ${esc(s.kind)}">${esc(KIND[s.kind] || s.kind)}</span> <b>${esc(s.title)}</b>${s.is_new ? ' <span class="nav-new">NEU</span>' : ''}
        <small>${esc(s.lead_company || s.company || 'nicht zugeordnet')} · veröffentlicht ${esc(date(s.published_at))} · gefunden ${esc(date(s.found_at))}${s.old ? ' · <b class="late">älter als 1 Jahr</b>' : ''}${s.suppressed ? ' · <b class="late">Sperrliste</b>' : ''}</small></div>
        <span class="sc-res ${s.polarity === 'contra' ? 'auffaellig' : 'ok'}">${esc(POL[s.polarity])}</span></div>
      <p class="sg-evidence">„${esc(s.evidence)}“</p>
      ${opts.compact ? '' : `<div class="sg-two"><div><b>Mögliche Relevanz</b><ul>${s.pro.map(x => `<li>${esc(x)}</li>`).join('') || '<li>–</li>'}</ul></div><div><b>Gegenargumente</b><ul>${s.contra.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></div>
      ${s.questions.length ? `<p><b>Gesprächsfrage:</b> ${esc(s.questions.join(' · '))}</p>` : ''}${s.uncertainties.length ? `<small class="muted">Unsicher: ${esc(s.uncertainties.join(' · '))}</small>` : ''}`}
      <div class="acc-btn-group"><small class="muted">Quelle(n): ${src}</small><select data-sg-status="${s.id}" aria-label="Prüfstatus">${['ungeprueft', 'bestaetigt', 'verworfen'].map(x => `<option value="${x}" ${x === s.status ? 'selected' : ''}>${{ungeprueft: 'ungeprüft', bestaetigt: 'bestätigt', verworfen: 'verworfen'}[x]}</option>`).join('')}</select>${s.status === 'bestaetigt' && s.lead_id && s.polarity === 'pro' ? `<button type="button" class="btn btn-ghost" data-sg-promote="${s.id}">Als Projektanlass im Lead übernehmen</button>` : ''}${assign}</div></article>`;
  }

  function hypothesisCard(h, showContra = true) {
    const ev = (h.evidence || h.signal_ids || []).map(e => `<li><span class="sg-kind ${esc(e.kind)}">${esc(KIND[e.kind] || e.kind)}</span> ${esc(e.title)} <small>(${esc(e.date)})</small></li>`).join('');
    return `<article class="sg-hyp"><div class="dc-item-head"><div><span class="eyebrow">${esc(h.label)}</span><b>${esc(h.hypothesis)}</b></div><span class="sg-strength ${esc(STRENGTH[h.strength] || 'schwach')}">${esc(h.strength)} · ${h.score}</span></div>
      <div class="sg-two"><div><b>Zusammenhängende Hinweise</b><ul>${ev}</ul></div><div><b>Gegenhinweise</b><ul>${(h.counter || []).map(c => `<li>${esc(c)}</li>`).join('') || '<li>–</li>'}</ul></div></div>
      ${showContra && (h.contradictions || []).length ? `<div class="sales-banner sales-warning"><b>Widerspruch:</b> ${esc(h.contradictions.join(' '))}</div>` : ''}
      <div class="sg-two"><div><b>Zur Bestätigung fehlt</b><ul>${(h.missing || []).map(m => `<li>${esc(m)}</li>`).join('')}</ul></div><div><b>Gesprächsfragen</b><ol>${(h.questions || []).map(q => `<li>${esc(q)}</li>`).join('') || '<li>Welche Veränderungen stehen bei Ihnen in diesem Jahr an?</li>'}</ol></div></div></article>`;
  }

  // ------------------------------------------------------------ Übersicht
  window.refreshSignals = async function () {
    try {
      const sum = await api('/signals/summary');
      $('#sgTotal').textContent = sum.total; $('#sgNew').textContent = sum.new; $('#sgUnassigned').textContent = sum.unassigned; $('#sgLeads').textContent = sum.leads.length;
      $('#sgNavBadge').textContent = sum.new ? String(sum.new) : '';
      $('#sgJobLead').innerHTML = '<option value="">– Firma laut Text/Feld –</option>' + leads.filter(l => l.stage !== 'gesperrt').map(l => `<option value="${l.id}">${esc(l.company)}</option>`).join('');
      $('#sgLeadList').innerHTML = sum.leads.length ? sum.leads.map(l => `<div class="sales-item"><div><strong>${esc(l.company)}</strong><small>${l.signals} Signal(e)${l.new ? ` · ${l.new} neu` : ''} · ${l.hypotheses} Hypothese(n)</small></div><button type="button" class="btn btn-ghost" data-sg-corr="${l.id}">Verknüpfen</button></div>`).join('') : '<div class="empty">Noch keine zugeordneten Signale.</div>';
      $('#sgScans').innerHTML = sum.scans.length ? sum.scans.slice(0, 8).map(s => `<div class="sales-item"><div><strong>${esc(s.company)}</strong><small>${esc({queued: 'wartet', running: 'läuft …', done: `${s.found} neue Stellen-Signal(e)`, failed: 'Fehler: ' + s.error}[s.status] || s.status)} · ${esc(s.created_at)}</small></div></div>`).join('') : '';
      renderCareerPicker();
      await loadFeed();
      clearTimeout(scanPoll);
      if (sum.scans.some(s => ['queued', 'running'].includes(s.status))) scanPoll = setTimeout(() => { if (currentView === 'signals') window.refreshSignals(); }, 2500);
    } catch (e) { toast(e.message, true); }
  };

  async function loadFeed() {
    const f = $('#sgFilter').value;
    const qs = {new: 'only_new=1', unassigned: 'unassigned=1', register: 'kind=register', job: 'kind=job', bestaetigt: 'status=bestaetigt'}[f] || '';
    const list = await api('/signals' + (qs ? '?' + qs : ''));
    $('#sgFeed').innerHTML = list.length ? list.slice(0, 80).map(s => signalCard(s)).join('') : '<div class="empty">Noch keine Signale. Bekanntmachungen einfügen, Stellenanzeigen erfassen oder Karriereseiten prüfen.</div>';
  }

  function renderCareerPicker() {
    const q = ($('#sgCareerSearch').value || '').toLowerCase();
    const list = leads.filter(l => l.website && l.stage !== 'gesperrt' && (!q || l.company.toLowerCase().includes(q))).slice(0, 60);
    $('#sgCareerPicker').innerHTML = list.length ? list.map(l => `<label class="sc-pick"><input type="checkbox" data-sg-career="${l.id}" ${careerSel.has(l.id) ? 'checked' : ''}> <span>${esc(l.company)}<small>${esc(l.website)}</small></span></label>`).join('') : '<div class="empty">Keine Leads mit Website.</div>';
    $('#sgCareerStart').disabled = !careerSel.size;
  }

  async function correlate(leadId, target) {
    try {
      const r = await api(`/leads/${leadId}/correlation`, 'POST', {});
      const html = `${r.contradictions.length ? `<div class="sales-banner sales-warning">${esc(r.contradictions.join(' '))}</div>` : ''}${r.hypotheses.length ? r.hypotheses.map(h => hypothesisCard(h, false)).join('') : '<div class="empty">Keine Hypothese: zu wenige passende Signale.</div>'}<p class="muted">${esc(r.notice)} Berücksichtigt: ${r.signals_considered} Signal(e)${r.website_considered ? ' + letzte Website-Bewertung' : ''}.</p>`;
      $(target).innerHTML = html;
      return r;
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Lead-Dialog
  window.loadLeadSignals = async function (leadId) {
    try {
      const d = await api(`/leads/${leadId}/correlation`);
      const timeline = d.signals.length ? `<div class="sg-timeline">${d.signals.map(s => signalCard(s, {compact: true})).join('')}</div>` : '<div class="empty">Noch keine Kaufsignale zu dieser Firma.</div>';
      const hyps = d.hypotheses.length ? `<h4>Hypothesen</h4>${d.hypotheses.map(h => hypothesisCard(h)).join('')}` : '';
      $('#leadSignals').innerHTML = timeline + `<div id="leadCorrelation">${hyps}</div>`;
    } catch (e) { $('#leadSignals').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  };

  function init() {
    if (!$('#viewSignals')) return;
    $$('[data-sg-tab]').forEach(b => b.addEventListener('click', () => {
      $$('[data-sg-tab]').forEach(x => x.classList.toggle('active', x === b));
      $$('.sg-pane').forEach(p => p.classList.toggle('hidden', p.dataset.sgPane !== b.dataset.sgTab));
    }));
    for (const [id, key] of [['#sgRegCsv', 'reg'], ['#sgJobCsv', 'job']]) {
      $(id).addEventListener('change', async e => { const f = e.target.files[0]; e.target.value = ''; if (!f) return; if (f.size > 2000000) return toast('CSV zu groß', true); csv[key] = await f.text(); toast(`${f.name} geladen – wird beim Import mitgeschickt`); });
    }
    $('#sgRegForm').addEventListener('submit', async e => {
      e.preventDefault();
      const body = {text: e.target.elements.text.value, source_url: e.target.elements.source_url.value};
      if (csv.reg) body.csv = csv.reg;
      try { const r = await api('/signals/register-import', 'POST', body); csv.reg = ''; e.target.reset(); toast(`${r.imported} Ereignis(se) importiert · ${r.duplicates} Dublette(n) · ${r.unassigned} ohne Lead${r.suppressed ? ` · ${r.suppressed} auf Sperrliste` : ''}`); window.refreshSignals(); }
      catch (err) { toast(err.message, true); }
    });
    $('#sgJobForm').addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target.elements, body = {};
      if (f.text.value.trim()) { body.text = f.text.value; body.source_url = f.source_url.value; if (f.published_at.value) body.published_at = f.published_at.value; if (f.lead_id.value) body.lead_id = Number(f.lead_id.value); }
      if (csv.job) body.csv = csv.job;
      try { const r = await api('/signals/job-import', 'POST', body); csv.job = ''; e.target.reset(); toast(`${r.imported} Anzeige(n) erfasst · ${r.unclassified} ohne Agenturbezug · ${r.duplicates} Dublette(n)`); window.refreshSignals(); }
      catch (err) { toast(err.message, true); }
    });
    $('#sgCareerSearch').addEventListener('input', renderCareerPicker);
    $('#sgCareerStart').addEventListener('click', async () => {
      try { const r = await api('/signals/career-scan', 'POST', {lead_ids: [...careerSel]}); careerSel.clear(); toast(`${r.queued.length} Karriereseite(n) werden geprüft${r.skipped.length ? ` · ${r.skipped.length} übersprungen` : ''}`); window.refreshSignals(); }
      catch (err) { toast(err.message, true); }
    });
    $('#sgFilter').addEventListener('change', loadFeed);
    $('#leadCorrelateBtn').addEventListener('click', async () => { if (!currentLeadId) return; await correlate(currentLeadId, '#leadCorrelation'); toast('Signale verknüpft'); });
    document.body.addEventListener('change', async e => {
      if (e.target.matches('[data-sg-career]')) {
        const id = Number(e.target.dataset.sgCareer);
        if (e.target.checked) { if (careerSel.size >= 20) { e.target.checked = false; return toast('Höchstens 20 Leads', true); } careerSel.add(id); } else careerSel.delete(id);
        return renderCareerPicker();
      }
      const st = e.target.closest('[data-sg-status]');
      if (st) { try { await api('/signals/' + st.dataset.sgStatus, 'PATCH', {status: st.value}); toast('Prüfstatus gespeichert'); if (currentView === 'signals') loadFeed(); } catch (err) { toast(err.message, true); } return; }
      const as = e.target.closest('[data-sg-assign]');
      if (as && as.value) { try { await api('/signals/' + as.dataset.sgAssign, 'PATCH', {lead_id: Number(as.value)}); toast('Signal zugeordnet'); window.refreshSignals(); } catch (err) { toast(err.message, true); } }
    });
    document.body.addEventListener('click', async e => {
      const c = e.target.closest('[data-sg-corr]');
      if (c) { currentLead = Number(c.dataset.sgCorr); await correlate(currentLead, '#sgCorrelation'); $('#sgCorrelation').scrollIntoView({behavior: 'smooth', block: 'start'}); return; }
      const p = e.target.closest('[data-sg-promote]');
      if (p) { try { await api(`/signals/${p.dataset.sgPromote}/promote`, 'POST', {}); toast('Als Projektanlass im Lead gespeichert'); await reload(); } catch (err) { toast(err.message, true); } }
    });
  }
  init();
})();
