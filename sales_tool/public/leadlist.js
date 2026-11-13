'use strict';
// 2.0.0-dev15 (Produktreview M09/U09): Firmenliste als bearbeitbare Arbeitsmenge.
// - Standardspalten: Firma, nächster Schritt mit Fälligkeit, Phase, Passung, letzter Kontakt; Kaufsignal und Leistung zuschaltbar.
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

  function nextCell(l) {
    if (!l.next_step && !l.next_date) return CONTACT.includes(l.stage) ? '<span class="sw-web mid">kein nächster Schritt</span>' : '<span class="muted">–</span>';
    const t = todayIso(), d = l.next_date || '';
    const due = !d ? '' : d < t ? `<span class="late">überfällig seit ${esc(fmtDate(d))}</span>` : d === t ? '<b class="ll-today">heute</b>' : esc(fmtDate(d));
    return `${esc(short(l.next_step || 'Termin ohne Beschreibung', 60))}<small>${due || 'ohne Datum'}</small>`;
  }

  function head() {
    return `<tr><th>FIRMA</th><th>NÄCHSTER SCHRITT</th><th>PHASE</th><th>PASSUNG</th><th>LETZTER KONTAKT</th>${extra.includes('signal') ? '<th>KAUFSIGNAL</th>' : ''}${extra.includes('offer') ? '<th>LEISTUNG</th>' : ''}<th> </th></tr>`;
  }

  function row(l) {
    const pill = `<span class="pill ${l.stage === 'gewonnen' ? 'won' : l.stage === 'verloren' || l.stage === 'gesperrt' ? 'lost' : l.stage === 'angebot' ? 'offer' : ''}">${esc(stageNames[l.stage] || l.stage)}</span>`;
    const signal = extra.includes('signal') ? `<td>${esc(short(config.signals[l.signal_type]?.[1] || '', 46))}<small>${l.signal_source ? '✓ Beleg vorhanden' : 'Ohne Beleg'}</small></td>` : '';
    const offer = extra.includes('offer') ? `<td>${l.offer && config.offers[l.offer] ? esc(config.offers[l.offer].title) : '<span class="muted">noch nicht gewählt</span>'}</td>` : '';
    return `<tr data-lead="${l.id}" tabindex="0"><td><b>${esc(l.company)}</b><small>${esc(l.industry || 'Branche unbekannt')} · ${l.employees || '?'} MA</small></td>
      <td class="ll-next">${nextCell(l)}</td><td>${pill}</td><td class="fit-cell">${window.leadGradeCell ? window.leadGradeCell(l.id) : ''}</td>
      <td>${l.last_contact ? esc(fmtDate(l.last_contact)) : '<span class="muted">noch keiner</span>'}</td>${signal}${offer}<td class="row-arrow">↗</td></tr>`;
  }

  function chips(q, stage) {
    const count = p => leads.filter(l => matches(l, '', '', p)).length;
    const pre = PRESETS.map(p => `<button type="button" class="ll-chip ${p.key === preset ? 'on' : ''}" data-ll-preset="${p.key}" aria-pressed="${p.key === preset}">${esc(p.label)} <small>${count(p.key)}</small></button>`).join('');
    const own = saved.map((v, i) => `<span class="ll-saved ${v.preset === preset && v.q === q && v.stage === stage ? 'on' : ''}"><button type="button" class="ll-chip" data-ll-view="${i}">★ ${esc(v.name)}</button><button type="button" class="ll-del" data-ll-del="${i}" aria-label="Ansicht ${esc(v.name)} löschen">✕</button></span>`).join('');
    return `${pre}${own}<button type="button" class="ll-chip ll-add" data-ll-save>＋ Ansicht speichern</button>`;
  }

  window.renderLeads = function () {
    const q = $('#leadSearch').value.toLowerCase().trim(), stage = $('#stageFilter').value;
    let list = leads.filter(l => matches(l, q, stage, preset));
    list.sort(preset === 'heute' ? (a, b) => (a.next_date || '').localeCompare(b.next_date || '') || rank(a.id) - rank(b.id)
      : (a, b) => rank(a.id) - rank(b.id) || b.score - a.score || b.id - a.id);
    $('#leadViews').innerHTML = chips($('#leadSearch').value.trim(), stage);
    $('#leadHead').innerHTML = head();
    const active = [preset !== 'alle' ? PRESETS.find(p => p.key === preset).label : '', stage ? 'Phase ' + (stageNames[stage] || stage) : '', q ? `Suche „${$('#leadSearch').value.trim()}“` : ''].filter(Boolean);
    $('#leadFilterInfo').innerHTML = `<b>${list.length} von ${leads.length} Firmen</b>${active.length ? ' · ' + active.map(esc).join(' · ') + ' <button type="button" class="text-button" data-ll-reset>Filter zurücksetzen</button>' : ''}`;
    const span = 6 + extra.length;
    $('#leadRows').innerHTML = list.map(row).join('') || (leads.length
      ? `<tr><td colspan="${span}" class="ll-empty"><b>Keine Firma passt zu diesen Filtern.</b> ${active.map(esc).join(' · ')} <button type="button" class="btn btn-ghost" data-ll-reset>Filter zurücksetzen</button></td></tr>`
      : `<tr><td colspan="${span}" class="ll-empty"><b>Noch keine Firmen.</b> Finde Firmen in offenen Quellen oder erfasse eine Anfrage direkt. <button type="button" class="btn btn-primary" data-go-action='${esc(JSON.stringify({view: 'finder'}))}'>Firmen finden</button> <button type="button" class="btn btn-ghost" data-go-action='${esc(JSON.stringify({view: 'new_lead'}))}'>Firma erfassen</button></td></tr>`);
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
