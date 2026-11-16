'use strict';
// 2.0.0-dev15 (Produktreview M09/U09): Firmenliste als bearbeitbare Arbeitsmenge.
// - Standardspalten: Firma, nächster Schritt mit Fälligkeit, Phase, Passung, letzter Kontakt; Kaufsignal und Leistung zuschaltbar.
// - 2.0.0-dev50: Spalten Firma · Nächster Schritt · Fällig · Phase · Passung · ›; Letzter Kontakt, Kaufsignal, Leistung unter „Spalten ▾“.
// - Arbeitsansichten als Chips (Heute fällig, Ohne nächsten Schritt, …) und eigene, gespeicherte Ansichten.
// - Aktive Filter und Trefferzahl sind immer sichtbar; ein leeres Ergebnis sagt, ob es noch keine Firmen gibt oder nur der Filter nichts liefert.
// Ersetzt renderLeads aus app.js; Filter wirken nur in der Anzeige, an den Firmendaten ändert sich nichts.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const PRESETS = [
    {key: 'alle', label: 'Alle'},
    {key: 'heute', label: 'Heute fällig'},
    {key: 'ohne_schritt', label: 'Ohne nächsten Schritt'},
    {key: 'angebote', label: 'Angebote nachfassen'},
    {key: 'recherche', label: 'Recherche prüfen'},
    {key: 'passung_ab', label: 'Passung A/B'},
    {key: 'kunden', label: 'Bestandskunden'},
  ];
  const CLOSED = ['gewonnen', 'verloren', 'gesperrt'];
  const CONTACT = ['qualifiziert', 'kontakt', 'antwort', 'termin', 'angebot'];
  const COLS_KEY = 'signaldesk.leadlist.cols';
  let preset = 'alle', saved = [], extra = readCols();

  function readCols() { try { const v = JSON.parse(localStorage.getItem(COLS_KEY) || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function writeCols() { try { localStorage.setItem(COLS_KEY, JSON.stringify(extra)); } catch (e) { /* ohne Speicher: nur für diese Sitzung */ } }
  const todayIso = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
  const rank = id => (window.leadGradeRank ? window.leadGradeRank(id) : 2);

  const TEST = {
    alle: () => true,
    heute: l => !!l.next_date && l.next_date <= todayIso() && !CLOSED.includes(l.stage),
    ohne_schritt: l => CONTACT.includes(l.stage) && !l.next_date,
    angebote: l => l.stage === 'angebot',
    recherche: l => l.stage === 'recherche',
    passung_ab: l => rank(l.id) <= 1 && !CLOSED.includes(l.stage),
    kunden: l => l.stage === 'gewonnen',
  };

  function matches(l, q, stage, p) {
    return TEST[p](l) && (!stage || l.stage === stage) && (!q || (l.company + ' ' + l.signal_note + ' ' + l.note + ' ' + (l.next_step || '')).toLowerCase().includes(q));
  }

  // 2.0.0-dev50: häufige Ansichten als Reiter, die übrigen unter „Weitere ▾“; eigene Ansichten ebenfalls als Reiter
  const FREQUENT = ['alle', 'heute', 'ohne_schritt'];
  // Spalten der Liste: Firma · Nächster Schritt · Fällig · Phase · Passung · (zuschaltbar) · ›
  const COLS = {last: ['LETZTER KONTAKT', '120px'], signal: ['KAUFSIGNAL', 'minmax(0,1.2fr)'], offer: ['LEISTUNG', 'minmax(0,1fr)']};
  const OPTIONAL = ['last', 'signal', 'offer'];
  const shown = () => OPTIONAL.filter(k => extra.includes(k));
  const shortDate = d => new Intl.DateTimeFormat('de-DE', {day: 'numeric', month: 'short'}).format(new Date(`${d}T12:00:00`));

  function nextCell(l) {
    if (!l.next_step && !l.next_date) return CONTACT.includes(l.stage) ? '<span class="ui-pill is-attention">kein nächster Schritt</span>' : '<span class="muted">–</span>';
    return `<span class="ui-cut">${esc(short(l.next_step || 'Termin ohne Beschreibung', 80))}</span>`;
  }

  // Fälligkeit als Status-Pille: rot überfällig, gelb heute, sonst das Datum ohne Farbe
  function dueCell(l) {
    const t = todayIso(), d = l.next_date || '';
    if (!d) return l.next_step ? '<span class="muted">ohne Datum</span>' : '<span class="muted">–</span>';
    if (d < t) return `<span class="ui-pill is-overdue" title="überfällig seit ${esc(fmtDate(d))}">überfällig</span><small>seit ${esc(shortDate(d))}</small>`;
    if (d === t) return '<span class="ui-pill is-attention">heute</span>';
    return `<span title="${esc(fmtDate(d))}">${esc(shortDate(d))}</span>`;
  }

  function stagePill(stage) {
    const tone = stage === 'gewonnen' ? ' is-done' : ['verloren', 'gesperrt'].includes(stage) ? ' is-overdue' : stage === 'angebot' ? ' is-underway' : '';
    return `<span class="ui-pill${tone}">${esc(stageNames[stage] || stage)}</span>`;
  }

  function head() {
    return `<tr class="ui-row-head"><th>FIRMA</th><th>NÄCHSTER SCHRITT</th><th>FÄLLIG</th><th>PHASE</th><th>PASSUNG</th>${shown().map(k => `<th>${COLS[k][0]}</th>`).join('')}<th><span class="ui-sr">Öffnen</span></th></tr>`;
  }

  // Spaltenbreiten folgen den zugeschalteten Spalten (CSSOM, die CSP erlaubt keine style-Attribute im HTML)
  function columns() {
    const tpl = ['minmax(0,2fr)', 'minmax(0,1.6fr)', '112px', '128px', '172px', ...shown().map(k => COLS[k][1]), '12px'].join(' ');
    $('#leadTable')?.style.setProperty('--ui-cols', tpl);
  }

  function row(l) {
    const cells = {
      last: () => `<td>${l.last_contact ? esc(fmtDate(l.last_contact)) : '<span class="muted">noch keiner</span>'}</td>`,
      signal: () => `<td class="ui-main"><b>${esc(short(config.signals[l.signal_type]?.[1] || '', 46))}</b><small>${l.signal_source ? '✓ Beleg vorhanden' : 'Ohne Beleg'}</small></td>`,
      offer: () => `<td class="ui-cut">${l.offer && config.offers[l.offer] ? esc(config.offers[l.offer].title) : '<span class="muted">noch nicht gewählt</span>'}</td>`,
    };
    return `<tr class="ui-row" data-lead="${l.id}" tabindex="0" title="Akte öffnen"><td class="ui-main"><b>${esc(l.company)}</b><small>${esc(l.industry || 'Branche unbekannt')} · ${l.employees || '?'} MA</small></td>
      <td class="ll-next">${nextCell(l)}</td><td class="ll-due">${dueCell(l)}</td><td>${stagePill(l.stage)}</td><td class="fit-cell">${window.leadGradeCell ? window.leadGradeCell(l.id) : ''}</td>
      ${shown().map(k => cells[k]()).join('')}<td class="ui-chev" aria-hidden="true">›</td></tr>`;
  }

  const isSaved = (v, q, stage) => v.preset === preset && v.q === q && v.stage === stage;

  function tabs(q, stage) {
    const count = p => leads.filter(l => matches(l, '', '', p)).length;
    const savedOn = saved.some(v => isSaved(v, q, stage));
    const pre = PRESETS.filter(p => FREQUENT.includes(p.key)).map(p => {
      const on = p.key === preset && !savedOn;
      return `<button type="button" class="ui-tab ${on ? 'is-active' : ''}" data-ll-preset="${p.key}" aria-pressed="${on}">${esc(p.label)} <small class="ui-count">${count(p.key)}</small></button>`;
    }).join('');
    const own = saved.map((v, i) => `<button type="button" class="ui-tab ${isSaved(v, q, stage) ? 'is-active' : ''}" data-ll-view="${i}" aria-pressed="${isSaved(v, q, stage)}">★ ${esc(v.name)}</button>`).join('');
    return pre + own;
  }

  function more(q, stage) {
    const count = p => leads.filter(l => matches(l, '', '', p)).length;
    const savedOn = saved.some(v => isSaved(v, q, stage));
    const rest = PRESETS.filter(p => !FREQUENT.includes(p.key)).map(p => {
      const on = p.key === preset && !savedOn;
      return `<button type="button" class="ui-menu-item ${on ? 'is-active' : ''}" data-ll-preset="${p.key}" aria-pressed="${on}">${esc(p.label)} <small class="ui-count">${count(p.key)}</small></button>`;
    }).join('');
    const del = saved.length ? `<div class="ui-menu-sep">Eigene Ansichten</div>` + saved.map((v, i) => `<div class="ui-menu-item ui-menu-split"><span>★ ${esc(v.name)}</span><button type="button" class="ui-txt" data-ll-del="${i}" aria-label="Ansicht ${esc(v.name)} löschen">Löschen</button></div>`).join('') : '';
    return `${rest}<div class="ui-menu-sep"></div><button type="button" class="ui-menu-item" data-ll-save>＋ Ansicht speichern</button>${del}`;
  }

  window.renderLeads = function () {
    const q = $('#leadSearch').value.toLowerCase().trim(), stage = $('#stageFilter').value;
    let list = leads.filter(l => matches(l, q, stage, preset));
    list.sort(preset === 'heute' ? (a, b) => (a.next_date || '').localeCompare(b.next_date || '') || rank(a.id) - rank(b.id)
      : (a, b) => rank(a.id) - rank(b.id) || b.score - a.score || b.id - a.id);
    $('#leadViews').innerHTML = tabs($('#leadSearch').value.trim(), stage);
    if ($('#leadMoreBody')) $('#leadMoreBody').innerHTML = more($('#leadSearch').value.trim(), stage);
    // „Weitere ▾“ nennt die gewählte Ansicht, wenn sie dort liegt – so bleibt sichtbar, was gerade filtert
    const inMore = !FREQUENT.includes(preset) && !saved.some(v => isSaved(v, $('#leadSearch').value.trim(), stage));
    if ($('#leadMoreBtn')) { $('#leadMoreBtn').textContent = inMore ? `${PRESETS.find(p => p.key === preset).label} ▾` : 'Weitere ▾'; $('#leadMoreBtn').classList.toggle('is-active', inMore); }
    $('#leadHead').innerHTML = head();
    columns();
    const active = [preset !== 'alle' ? PRESETS.find(p => p.key === preset).label : '', stage ? 'Phase ' + (stageNames[stage] || stage) : '', q ? `Suche „${$('#leadSearch').value.trim()}“` : ''].filter(Boolean);
    $('#leadFilterInfo').innerHTML = active.length ? `<b>${list.length} von ${leads.length} Firmen</b> · ${active.map(esc).join(' · ')} <button type="button" class="ui-txt" data-ll-reset>Filter zurücksetzen</button>`
      : `<b>${leads.length} ${leads.length === 1 ? 'Firma' : 'Firmen'}</b>`;
    $('#leadRows').innerHTML = list.map(row).join('') || (leads.length
      ? `<tr class="ui-empty"><td class="ll-empty"><b>Keine Firma passt zu diesen Filtern.</b> ${active.map(esc).join(' · ')} <button type="button" class="btn btn-ghost" data-ll-reset>Filter zurücksetzen</button></td></tr>`
      : `<tr class="ui-empty"><td class="ll-empty"><b>Noch keine Firmen.</b> Finde Firmen in offenen Quellen oder erfasse eine Anfrage direkt. <button type="button" class="btn btn-ghost" data-go-action='${esc(JSON.stringify({view: 'finder'}))}'>Firmen finden</button> <button type="button" class="btn btn-ghost" data-go-action='${esc(JSON.stringify({view: 'new_lead'}))}'>Firma erfassen</button></td></tr>`);
    document.querySelectorAll('[data-ll-col]').forEach(c => { c.checked = extra.includes(c.dataset.llCol); });
  };

  function setPreset(p, sync = true) {
    preset = TEST[p] ? p : 'alle';
    if (typeof leads !== 'undefined') window.renderLeads();
    if (sync) document.dispatchEvent(new CustomEvent('signaldesk:leadfilter'));
  }

  async function storeViews(views) {
    const r = await api('/lead-views', 'PUT', {views});
    saved = r.views;
    window.renderLeads();
  }

  function reset() {
    $('#leadSearch').value = '';
    $('#stageFilter').value = '';
    setPreset('alle');
  }

  function init() {
    if (!$('#leadViews')) return;
    document.addEventListener('click', async e => {
      const p = e.target.closest('[data-ll-preset]');
      if (p) return setPreset(p.dataset.llPreset);
      const v = e.target.closest('[data-ll-view]');
      if (v) { const s = saved[Number(v.dataset.llView)]; $('#leadSearch').value = s.q; $('#stageFilter').value = s.stage; return setPreset(s.preset); }
      if (e.target.closest('[data-ll-reset]') || e.target.closest('#resetFilter')) return reset();
      const d = e.target.closest('[data-ll-del]');
      if (d) {
        const s = saved[Number(d.dataset.llDel)];
        if (!confirm(`Ansicht „${s.name}“ löschen? Die Firmen bleiben unverändert.`)) return;
        try { await storeViews(saved.filter((_, i) => i !== Number(d.dataset.llDel))); toast('Ansicht gelöscht'); } catch (err) { toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-ll-save]')) {
        const name = (prompt('Name der Ansicht (z. B. „Heute fällig in Stuttgart“):') || '').trim();
        if (!name) return;
        try { await storeViews([...saved, {name, preset, stage: $('#stageFilter').value, q: $('#leadSearch').value.trim()}]); toast(`Ansicht „${name}“ gespeichert`); }
        catch (err) { toast(err.message, true); }
      }
    });
    document.addEventListener('change', e => {
      const c = e.target.closest('[data-ll-col]');
      if (!c) return;
      extra = extra.filter(x => x !== c.dataset.llCol).concat(c.checked ? [c.dataset.llCol] : []);
      writeCols();
      window.renderLeads();
    });
    api('/lead-views').then(r => { saved = r.views; if (typeof leads !== 'undefined' && leads.length) window.renderLeads(); }).catch(() => {});
  }

  window.leadList = {PRESETS, get preset() { return preset; }, setPreset};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
