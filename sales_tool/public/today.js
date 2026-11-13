'use strict';
// Sprint A: „Heute“ – Tagesplan, Wiedervorlage, offenes Potenzial aus Angeboten, klickbare Pipeline, Funktionsstatus.
// Jede Zeile führt direkt zur passenden Stelle (Lead, Kontakt & Termine, Angebot, Recherche).
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const KIND = {termin: 'Termin', rueckruf: 'Rückruf', aufgabe: 'Aufgabe', naechster_schritt: 'Nächster Schritt', nachfassen: 'Nachfassen',
    angebot_frist: 'Bindefrist', bedarfsanalyse: 'Bedarfsanalyse', angebot_entwurf: 'Angebotsentwurf', recherche: 'Recherche'};
  const STATUS = {entwurf: 'Entwurf', gesendet_manuell: 'beim Kunden', angenommen: 'angenommen'};
  // Aktion je Pipeline-Phase für einen einzelnen Lead
  const LEAD_ACTION = {
    recherche: {label: 'Bericht erstellen', view: 'report'}, qualifiziert: {label: 'Kontaktweg klären', view: 'lead'},
    kontakt: {label: 'Kontakt aufnehmen', view: 'workspace', section: 'contact'}, antwort: {label: 'Termin vereinbaren', view: 'workspace', section: 'meeting'},
    termin: {label: 'Bedarf klären', view: 'lead'}, angebot: {label: 'Angebot öffnen', view: 'quotes'}, gewonnen: {label: 'Rechnung schreiben', view: 'quotes'},
  };
  window.leadStageAction = LEAD_ACTION;
  let data = null, stageActions = {};

  const enc = o => esc(JSON.stringify(o));

  async function latestProposal(leadId) {
    try { const rows = await api('/workspace/proposals'); return rows.find(r => r.lead_id === leadId) || null; } catch { return null; }
  }

  function selectLead(sel, leadId) {
    const el = $(sel);
    if (!el || !leadId) return;
    el.value = String(leadId);
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }

  // Zentrale Sprungfunktion für alle „Los“-Knöpfe
  window.goAction = async function (a) {
    const lead = a.lead_id ? Number(a.lead_id) : null;
    if (a.view === 'lead') return lead ? showModal(lead) : switchView('leads');
    if (a.view === 'today') { switchView('dashboard'); return $('#' + (a.anchor || 'wiedervorlage'))?.scrollIntoView({behavior: 'smooth'}); }
    if (a.view === 'leads') {
      if (lead) return showModal(lead);
      switchView('leads');
      if (a.stage && $('#stageFilter')) { $('#stageFilter').value = a.stage; renderLeads(); }
      return;
    }
    if (a.view === 'workspace') {
      switchView('workspace');
      if (window.refreshSalesWorkspace) await window.refreshSalesWorkspace();
      if (window.refreshActionCenter) await window.refreshActionCenter();
      if (a.section === 'contact') { selectLead('#wsCallForm [name=lead_id]', lead); selectLead('#wsMailForm [name=lead_id]', lead); }
      if (a.section === 'meeting') { selectLead('#wsMeetingForm [name=lead_id]', lead); if (lead) setTimeout(() => $('#wsMeetingForm [name=title]')?.focus(), 400); }
      const target = $('#' + (a.section || 'permissions'));
      if (target) setTimeout(() => target.scrollIntoView({behavior: 'smooth', block: 'start'}), 150);
      return;
    }
    if (a.view === 'quotes') {
      switchView('quotes');
      if (window.refreshSalesQuotes) await window.refreshSalesQuotes();
      let pid = a.ref;
      if (!pid && lead && a.open_latest) pid = (await latestProposal(lead))?.id;
      if (pid) { const b = $(`[data-quote-open="${pid}"]`); if (b) { b.click(); setTimeout(() => $('#quoteSaved')?.scrollIntoView({behavior: 'smooth'}), 300); } return; }
      if (lead) { selectLead('#quoteForm [name=lead_id]', lead); toast('Firma vorausgewählt – Paket wählen und Festpreis berechnen'); }
      return;
    }
    if (a.view === 'report') return lead ? window.openReport(lead, {create: !a.open_only}) : switchView('center');
    if (a.view === 'center') {
      switchView('center');
      if (lead) setTimeout(() => $(`[data-rc-open="${lead}"]`)?.click(), 900);
      return;
    }
    switchView(a.view);
    // 2.0.0-dev14: Sprungziel innerhalb der Ansicht, z. B. Einstellungen → Zielkundenprofil
    if (a.anchor) setTimeout(() => $('#' + a.anchor)?.scrollIntoView({behavior: 'smooth', block: 'start'}), 80);
  };

  // ------------------------------------------------------------ Rendern
  function renderPlan(p) {
    // 2.0.0-dev13: nur zählen, was wirklich offen ist – ein leerer Schritt ist nicht „erledigt“
    const open = p.steps.filter(s => !s.done).length;
    $('#tdPlanState').textContent = open ? `${open} von ${p.steps.length} Schritten mit offenen Punkten` : 'Nichts offen';
    $('#tdSteps').innerHTML = p.steps.map((s, i) => `<li class="td-step ${s.state === 'erledigt' ? 'done' : s.done ? 'quiet' : ''} ${s.key === p.next_key ? 'next' : ''}">
      <span class="td-num" title="${s.state === 'erledigt' ? 'erledigt' : s.done ? 'nichts offen' : 'offen'}">${s.state === 'erledigt' ? '✓' : s.done ? '–' : i + 1}</span>
      <div><b>${esc(s.title)}</b><small>${s.done && s.state !== 'erledigt' ? 'Nichts offen. ' : ''}${esc(s.why)}</small></div>
      <span class="td-count">${s.count || ''}</span>
      <button type="button" class="btn ${s.key === p.next_key ? 'btn-primary' : 'btn-ghost'}" data-go-action="${enc({view: s.view, section: s.section, anchor: s.anchor})}">${s.done ? 'Ansehen' : 'Los →'}</button></li>`).join('');
    const nxt = p.steps.find(s => s.key === p.next_key);
    $('#tdNext').dataset.goAction = JSON.stringify(nxt ? {view: nxt.view, section: nxt.section, anchor: nxt.anchor} : {view: 'finder'});
    $('#tdNext').textContent = nxt ? `Weiter: ${nxt.title.split(' (')[0]} →` : 'Alles erledigt – neue Firmen finden →';
  }

  function renderWv(items, total) {
    $('#tdWvCount').textContent = total ? `${total} offen` : '';
    $('#tdWv').innerHTML = items.length ? items.map(i => `<div class="td-item ${i.overdue ? 'overdue' : ''}">
      <span class="td-kind ${esc(i.kind)}">${esc(KIND[i.kind] || i.kind)}</span>
      <div><b>${esc(i.title)}</b><small>${esc(i.company)}${i.due ? ' · ' + esc(fmtDate(i.due)) : ''}${i.overdue ? ' · <span class="late">überfällig</span>' : ''}${i.detail ? ' · ' + esc(i.detail) : ''}</small></div>
      <button type="button" class="btn btn-ghost" data-go-action="${enc({view: i.view, section: i.section, lead_id: i.lead_id, anchor: i.anchor, ref: i.view === 'quotes' ? i.ref : null})}">${esc(i.action)}</button></div>`).join('')
      : '<div class="empty">Nichts fällig. Gut so – weiter mit dem Tagesplan.</div>';
    const overdue = items.filter(i => i.overdue).length;
    $('#tdNavBadge').textContent = overdue ? String(overdue) : '';
  }

  function renderPotential(p) {
    $('#tdPotKpis').innerHTML = `<div><small>Offene Angebote</small><b>${euros(p.offers_sum)}</b><span>${p.offers.length} Angebot(e), davon ${euros(p.sent_sum)} beim Kunden</span></div>
      <div><small>Angenommen, noch nicht abgerechnet</small><b>${euros(p.accepted_sum)}</b><span>${p.accepted.length} Angebot(e)</span></div>
      <div><small>Nur geschätzt, ohne Angebot</small><b>${euros(p.estimates_sum)}</b><span>${p.estimates_count} Lead(s)</span></div>`;
    const offers = [...p.accepted.map(o => ({...o, accepted: true})), ...p.offers].slice(0, 8).map(o => `<div class="td-item">
      <span class="td-kind ${o.accepted ? 'won' : 'offer'}">${esc(o.accepted ? 'angenommen' : STATUS[o.status] || o.status)}</span>
      <div><b>${esc(o.company)} · ${euros(o.net_eur)}</b><small>${esc(o.number)} · ${esc(o.project_label)}${o.valid_until ? ' · gültig bis ' + esc(fmtDate(o.valid_until)) : ''}</small></div>
      <button type="button" class="btn btn-ghost" data-go-action="${enc({view: 'quotes', ref: o.proposal_id})}">${o.accepted ? 'Rechnung erstellen' : 'Angebot öffnen'}</button></div>`);
    const est = p.estimates.slice(0, 5).map(e => `<div class="td-item">
      <span class="td-kind est">Schätzung</span>
      <div><b>${esc(e.company)} · ca. ${euros(e.estimated_budget)}</b><small>${esc(stageNames[e.stage] || e.stage)} · noch kein kalkuliertes Angebot</small></div>
      <button type="button" class="btn btn-ghost" data-go-action="${enc({view: 'quotes', lead_id: e.lead_id})}">Angebot kalkulieren</button></div>`);
    $('#tdPot').innerHTML = offers.concat(est).join('') || '<div class="empty">Noch keine Angebote. Sobald du eines kalkulierst, erscheint es hier mit Festpreis.</div>';
    $('#tdPotNote').textContent = p.notice;
  }

  function renderStages(stages) {
    stageActions = Object.fromEntries(stages.map(s => [s.stage, s]));
    $('#tdStages').innerHTML = stages.map(s => `<button type="button" class="td-stage ${s.count ? '' : 'empty-stage'}" data-go-action="${enc({view: s.action_view, section: s.action_section, stage: s.stage})}" title="${esc(s.action_hint)}">
      <span class="td-stage-label">${esc(s.label)}</span><strong>${s.count}</strong>
      <small>${s.offer_value ? euros(s.offer_value) + ' in Angeboten' : '&nbsp;'}</small>
      <span class="td-stage-action">${esc(s.action_label)} →</span></button>`).join('');
  }

  async function renderStatus() {
    try {
      const c = await api('/system/capabilities');
      const bad = c.items.filter(i => i.ok === false);
      $('#tdStatusSummary').textContent = bad.length ? `${bad.length} Funktion(en) eingeschränkt` : 'alles bereit';
      $('#tdStatus').innerHTML = c.items.map(i => `<div class="td-item"><span class="td-cap ${i.ok === true ? 'ok' : i.ok === false ? 'off' : 'unknown'}">${i.ok === true ? '✓' : i.ok === false ? '!' : '?'}</span>
        <div><b>${esc(i.label)}</b><small>${esc(i.detail)}</small></div></div>`).join('');
      $('#aiNavBadge').textContent = c.ai_online ? '' : 'ohne KI';
    } catch (e) { $('#tdStatus').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  window.refreshToday = async function () {
    if (!$('#tdSteps')) return;
    try {
      data = await api('/today');
      const h = new Date().getHours();
      $('#tdGreeting').textContent = (h < 11 ? 'GUTEN MORGEN' : h < 17 ? 'GUTEN TAG' : 'GUTEN ABEND') + ' · ' + new Intl.DateTimeFormat('de-DE', {weekday: 'long', day: '2-digit', month: 'long'}).format(new Date()).toUpperCase();
      renderPlan(data.plan);
      renderWv(data.wiedervorlage, data.wiedervorlage_total);
      renderPotential(data.potential);
      renderStages(data.pipeline);
    } catch (e) { if (e.message !== 'Bitte anmelden.') toast(e.message, true); }
  };

  function init() {
    if (!$('#tdSteps')) return;
    document.body.addEventListener('click', e => {
      const b = e.target.closest('[data-go-action]');
      if (!b) return;
      e.preventDefault();
      try { window.goAction(JSON.parse(b.dataset.goAction)); } catch (err) { toast(err.message, true); }
    });
    $('.td-status')?.addEventListener('toggle', e => { if (e.target.open) renderStatus(); });
    renderStatus();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
