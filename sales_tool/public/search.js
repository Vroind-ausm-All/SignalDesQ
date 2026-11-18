'use strict';
// 2.0.0-dev34 (Roadmap M10): Globale Suche – Firma, Chance, Angebot, Rechnungsnummer. Strg+K bzw. ⌘K öffnet, Pfeiltasten und
// Enter wählen, Escape schließt; der Fokus kehrt an die vorherige Stelle zurück. Nur lesend.
// 2.0.0-dev50: dazu Befehle – „Neue Firma anlegen“ öffnet das vorhandene Anlegen (der globale Knopf in der Kopfzeile entfiel).
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  let items = [], active = -1, back = null, timer = null, seq = 0;
  const COMMANDS = [{kind: 'befehl', cmd: 'neue_firma', title: 'Neue Firma anlegen', detail: 'Firma oder Anfrage erfassen', words: 'neue neu firma anlegen erfassen hinzufügen lead kunde anfrage'}];
  const NOTE = 'Mindestens zwei Zeichen. Personen werden nicht durchsucht.';
  // Befehl passt, wenn jedes eingegebene Wort am Anfang eines seiner Stichwörter steht („neu fi“, „firma anl“)
  const fits = (c, q) => q.toLowerCase().split(/\s+/).filter(Boolean).every(w => c.words.split(' ').some(k => k.startsWith(w)));
  function option(i) {
    const n = items.push(i) - 1;
    return `<li role="option" id="gs-opt-${n}" data-gs="${n}" data-gs-kind="${esc(i.kind)}" aria-selected="false">${esc(i.title)}${i.detail ? `<small>${esc(i.detail)}</small>` : ''}</li>`;
  }
  const commandGroup = list => (list.length ? '<li class="gs-group" role="presentation">Befehle</li>' + list.map(option).join('') : '');
  function showCommands() {
    items = [];
    $('#gsResults').innerHTML = commandGroup(COMMANDS);
    $('#gsNotice').textContent = NOTE;
    active = -1;
    select(0);
  }

  function build() {
    document.body.insertAdjacentHTML('beforeend', `<div class="gs-backdrop hidden" id="gsBackdrop"><div class="gs-dialog" role="dialog" aria-modal="true" aria-label="Suchen">
      <input id="gsInput" type="search" maxlength="80" autocomplete="off" placeholder="Firma, Chance, Angebots- oder Rechnungsnummer …" role="combobox" aria-expanded="true" aria-controls="gsResults" aria-autocomplete="list">
      <ul class="gs-results" id="gsResults" role="listbox" aria-label="Treffer"></ul><p class="muted" id="gsNotice">Mindestens zwei Zeichen. Personen werden nicht durchsucht.</p></div></div>`);
    $('#gsBackdrop').addEventListener('mousedown', e => { if (e.target.id === 'gsBackdrop') close(); });
    $('#gsInput').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 150); });
    $('#gsInput').addEventListener('keydown', e => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); select(active + (e.key === 'ArrowDown' ? 1 : -1)); }
      else if (e.key === 'Enter') { e.preventDefault(); if (items[active]) go(items[active]); }
      else if (e.key === 'Escape') { e.preventDefault(); close(); }
      else if (e.key === 'Tab') e.preventDefault();  // Fokus bleibt im Dialog
    });
    $('#gsResults').addEventListener('click', e => { const o = e.target.closest('[data-gs]'); if (o) go(items[Number(o.dataset.gs)]); });
  }

  function select(i) {
    if (!items.length) return;
    active = (i + items.length) % items.length;
    $$('#gsResults [role=option]').forEach((o, n) => o.setAttribute('aria-selected', String(n === active)));
    const cur = $(`#gsResults [data-gs="${active}"]`);
    if (cur) { cur.scrollIntoView({block: 'nearest'}); $('#gsInput').setAttribute('aria-activedescendant', cur.id); }
  }

  async function run() {
    const q = $('#gsInput').value.trim(), mine = ++seq;
    if (q.length < 2) { showCommands(); return; }
    try {
      const r = await api('/suche?q=' + encodeURIComponent(q));
      if (mine !== seq) return;  // veraltete Antwort
      items = [];
      const cmds = COMMANDS.filter(c => fits(c, q));
      $('#gsResults').innerHTML = r.groups.map(g => `<li class="gs-group" role="presentation">${esc(g.label)}</li>` + g.items.map(option).join('')).join('') + commandGroup(cmds);
      $('#gsNotice').textContent = r.notice || `${r.total} Treffer – Enter öffnet, Escape schließt.`;
      active = -1;
      if (items.length) select(0);
    } catch (e) { $('#gsNotice').textContent = e.message; }
  }

  function open() {
    if (!$('#gsBackdrop')) build();
    back = document.activeElement;
    $('#gsBackdrop').classList.remove('hidden');
    $('#gsInput').value = '';
    showCommands();
    $('#gsInput').focus();
  }

  function close(keepFocus) {
    $('#gsBackdrop')?.classList.add('hidden');
    if (!keepFocus && back && document.contains(back)) back.focus();
  }

  async function go(i) {
    close(true);
    try {
      if (i.kind === 'befehl' && i.cmd === 'neue_firma') await showModal();
      else if (i.kind === 'firma' || i.kind === 'chance') { switchView('leads'); await showModal(i.lead_id); }
      else if (i.kind === 'angebot') { switchView('quotes'); await window.wsOpenProposal?.(i.id); $('#quoteSaved')?.scrollIntoView({block: 'start'}); }
      else if (i.kind === 'rechnung') {  // 2.0.0-dev53: Rechnung direkt öffnen (Entwurf im Editor, sonst die geöffnete Rechnung)
        switchView('accounting');
        if (window.accOpenInvoice) await window.accOpenInvoice(i.id); else toast(`Rechnung ${i.title}: in der Rechnungsliste öffnen`);
      }
    } catch (e) { toast(e.message, true); }
  }

  window.openGlobalSearch = open;
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); open(); }
  });
  document.addEventListener('DOMContentLoaded', () => $('#gsOpen')?.addEventListener('click', open));
})();
