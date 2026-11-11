'use strict';
// v1.13: Kompakte Deal-Pipeline. Karten zeigen nur Name + Score; Klick klappt Details auf.
// Verschieben per Drag & Drop (Maus) oder Click & Drop (⇄ antippen, dann Zielspalte anklicken – auch auf Touch/Tastatur).
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const expanded = new Set();
  let moving = null, dragId = null;
  const COLS = [...pipelineStages, 'verloren'];
  const label = s => s === 'verloren' ? 'Verloren' : stageNames[s];

  function card(l, sa) {
    const isOpen = expanded.has(l.id);
    return `<article class="pipeline-card pc ${isOpen ? 'open' : ''} ${moving === l.id ? 'moving' : ''}" draggable="true" data-pcard="${l.id}">
      <div class="pc-head"><button type="button" class="pc-toggle" data-pc-toggle="${l.id}" aria-expanded="${isOpen}" title="Details ${isOpen ? 'zuklappen' : 'aufklappen'}">
        <span class="pc-name">${esc(short(l.company, 34))}</span><span class="score ${l.score < 40 ? 'low' : ''}">${l.score}</span><span class="pc-chev" aria-hidden="true">▾</span></button>
        <button type="button" class="pc-move" data-pc-move="${l.id}" aria-label="${esc(l.company)} verschieben" title="Verschieben: antippen, dann Zielspalte anklicken">⇄</button></div>
      ${isOpen ? `<div class="pc-body">
        <small>${esc(short(l.signal_note || config.signals[l.signal_type][1], 120))}</small>
        <div class="pipeline-card-bottom"><span>${l.next_step ? esc(short(l.next_step, 60)) + ' · ' : ''}${l.next_date ? esc(fmtDate(l.next_date)) : 'Nächsten Schritt festlegen'}</span><button type="button" data-lead="${l.id}" aria-label="Lead öffnen" title="Lead öffnen">↗</button></div>
        ${sa && l.permission !== 'nicht_kontaktieren' ? `<button type="button" class="btn btn-primary pipeline-action" data-go-action="${esc(JSON.stringify({view: sa.view, section: sa.section, lead_id: l.id, open_latest: l.stage === 'angebot' || l.stage === 'gewonnen'}))}">${esc(sa.label)} →</button>` : ''}
        <label class="pipeline-change-label">PHASE ÄNDERN<select aria-label="Phase für ${esc(l.company)}" data-pipeline-update="${l.id}">${pipelineStages.map(st => `<option value="${st}" ${st === l.stage ? 'selected' : ''}>${stageNames[st]}</option>`).join('')}<option value="verloren">Verloren</option></select></label>
      </div>` : ''}</article>`;
  }

  window.renderPipeline = function () {
    const open = leads.filter(l => !['gesperrt', 'verloren'].includes(l.stage));
    const lost = leads.filter(l => l.stage === 'verloren').length;
    $('#pipelineSummary').innerHTML = `<div><small>AKTIVE CHANCEN</small><b>${open.filter(l => l.stage !== 'gewonnen').length}</b></div><div><small>GESPRÄCHE / RÜCKMELDUNGEN</small><b>${open.filter(l => ['antwort', 'termin'].includes(l.stage)).length}</b></div><div><small>OFFENE ANGEBOTE</small><b>${open.filter(l => l.stage === 'angebot').length}</b></div><div><small>GEWONNEN</small><b>${open.filter(l => l.stage === 'gewonnen').length}</b></div>`;
    const board = $('#pipelineBoard');
    board.classList.toggle('pc-moving', moving != null);
    const mv = moving != null ? leads.find(l => l.id === moving) : null;
    if ($('#pipelineHint')) $('#pipelineHint').innerHTML = mv ? `<b>${esc(mv.company)}</b> verschieben: Zielspalte anklicken · <button type="button" class="text-button" data-pc-cancel>Abbrechen (Esc)</button>`
      : 'Karte anklicken für Details · ziehen oder ⇄ antippen und Zielspalte wählen, um die Phase zu ändern';
    board.innerHTML = COLS.map(stage => {
      if (stage === 'verloren') {
        return `<section class="pipeline-column pc-lost" data-pcol="verloren" ${mv ? 'tabindex="0" role="button"' : ''} aria-label="Spalte Verloren"><div class="pipeline-col-head"><span>Verloren</span><b>${lost}</b></div><div class="pipeline-empty">Hierher ziehen, wenn eine Chance nicht weiterverfolgt wird</div></section>`;
      }
      const cards = open.filter(l => l.stage === stage).sort((a, b) => b.score - a.score);
      const sa = (window.leadStageAction || {})[stage];
      return `<section class="pipeline-column" data-pcol="${stage}" ${mv ? 'tabindex="0" role="button"' : ''} aria-label="Spalte ${esc(stageNames[stage])}"><div class="pipeline-col-head"><span>${stageNames[stage]}</span><b>${cards.length}</b></div>${sa ? `<button type="button" class="text-button pipeline-col-action" data-go-action="${esc(JSON.stringify({view: sa.view === 'lead' ? 'leads' : sa.view, section: sa.section, stage}))}">${esc(sa.label)} ↗</button>` : ''}<div class="pipeline-cards">${cards.map(l => card(l, sa)).join('') || '<div class="pipeline-empty">Noch keine Firma in dieser Phase</div>'}</div></section>`;
    }).join('');
  };

  async function moveTo(id, stage) {
    const lead = leads.find(l => l.id === id);
    moving = null;
    if (!lead || lead.stage === stage) { window.renderPipeline(); return; }
    if (stage === 'gewonnen' && !confirm('Ist der Auftrag tatsächlich verbindlich gewonnen?')) { window.renderPipeline(); return; }
    const data = window.withLostReason ? await window.withLostReason(lead, {stage}) : {stage};  // 2.0.0-dev2: „verloren“ nur mit Grund
    if (!data) { window.renderPipeline(); return; }
    try { await api(`/leads/${id}`, 'PATCH', data); await reload(); toast(`${lead.company} → ${label(stage)}`); }
    catch (e) { window.renderPipeline(); toast(e.message, true); }
  }

  function init() {
    const board = $('#pipelineBoard');
    if (!board) return;
    board.addEventListener('click', e => {
      const t = e.target.closest('[data-pc-toggle]');
      if (t) { const id = Number(t.dataset.pcToggle); expanded.has(id) ? expanded.delete(id) : expanded.add(id); window.renderPipeline(); return; }
      const m = e.target.closest('[data-pc-move]');
      if (m) { const id = Number(m.dataset.pcMove); moving = moving === id ? null : id; window.renderPipeline(); return; }
      if (e.target.closest('button,select,a,label,input')) return;
      if (moving != null) { const col = e.target.closest('[data-pcol]'); if (col) moveTo(moving, col.dataset.pcol); return; }
      const c = e.target.closest('[data-pcard]');
      if (c) { const id = Number(c.dataset.pcard); expanded.has(id) ? expanded.delete(id) : expanded.add(id); window.renderPipeline(); }
    });
    board.addEventListener('keydown', e => {
      if (moving != null && (e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-pcol]')) { e.preventDefault(); moveTo(moving, e.target.dataset.pcol); }
    });
    document.addEventListener('click', e => { if (e.target.closest('[data-pc-cancel]')) { moving = null; window.renderPipeline(); } });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && moving != null) { moving = null; window.renderPipeline(); } });
    board.addEventListener('dragstart', e => {
      const c = e.target.closest('[data-pcard]');
      if (!c) return;
      dragId = Number(c.dataset.pcard);
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', String(dragId));
      c.classList.add('dragging');
      board.classList.add('pc-dragging');
    });
    board.addEventListener('dragend', () => { dragId = null; board.classList.remove('pc-dragging'); $$('.pc.dragging, .pipeline-column.drop').forEach(x => x.classList.remove('dragging', 'drop')); });
    board.addEventListener('dragover', e => {
      const col = e.target.closest('[data-pcol]');
      if (!col || dragId == null) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      $$('.pipeline-column.drop').forEach(x => x !== col && x.classList.remove('drop'));
      col.classList.add('drop');
    });
    board.addEventListener('dragleave', e => { const col = e.target.closest('[data-pcol]'); if (col && !col.contains(e.relatedTarget)) col.classList.remove('drop'); });
    board.addEventListener('drop', e => {
      const col = e.target.closest('[data-pcol]');
      if (!col) return;
      e.preventDefault();
      const id = Number(e.dataTransfer.getData('text/plain')) || dragId;
      col.classList.remove('drop');
      if (id) moveTo(id, col.dataset.pcol);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
