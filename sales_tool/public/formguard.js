'use strict';
// 2.0.0-dev13 (Produktreview M01/M03): Eingaben im Lead-Dialog gehen nie still verloren, und der Fokus landet beim Öffnen
// und Schließen an der richtigen Stelle.
// - Schließen per ✕, „Abbrechen“, Escape oder Klick daneben fragt bei Änderungen: Speichern · Weiter bearbeiten · Verwerfen.
// - Schließt der Dialog auf anderem Weg (Sprung in eine andere Ansicht), bleiben die Eingaben im Arbeitsspeicher und kommen
//   beim nächsten Öffnen derselben Firma zurück. Nichts davon landet im Browser-Speicher oder auf dem Server.
// - Gespeichert wird nur über die vorhandenen Formulare; es gibt kein automatisches Speichern.
(function () {
  const FORMS = ['leadForm', 'activityForm', 'discoveryForm', 'newContactForm'];
  const LABEL = {leadForm: 'Stammdaten', activityForm: 'Aktivitätsprotokoll', discoveryForm: 'Bedarfsanalyse', newContactForm: 'neue Ansprechperson'};
  const base = new Map();      // Formular-ID -> gespeicherter Stand
  const drafts = new Map();    // Firma -> nicht gespeicherte Eingaben (nur Arbeitsspeicher)
  let armed = false, pending = null, discard = false, lastTrigger = null, lastLead = null, onDecision = null;

  const byId = id => document.getElementById(id);
  const modalOpen = () => !byId('modal').classList.contains('hidden');
  const leadKey = () => (typeof currentLeadId !== 'undefined' && currentLeadId ? String(currentLeadId) : 'neu');

  function values(f) {
    const out = {};
    for (const el of f.elements) {
      if (!el.name || el.name === 'id' || ['submit', 'button', 'reset', 'file'].includes(el.type)) continue;
      if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; else if (!(el.name in out)) out[el.name] = ''; continue; }
      out[el.name] = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value;
    }
    return out;
  }

  function setValues(f, vals) {
    for (const [name, v] of Object.entries(vals)) {
      const item = f.elements.namedItem(name);
      if (!item) continue;
      const list = item instanceof RadioNodeList ? [...item] : [item];
      for (const el of list) {
        if (el.type === 'radio') el.checked = el.value === v;
        else if (el.type === 'checkbox') el.checked = v === '1';
        else el.value = v;
      }
    }
  }

  const snap = f => JSON.stringify(values(f));
  function rebase(id) { const f = byId(id); if (f) base.set(id, snap(f)); refresh(); }
  function dirty() {
    if (!armed || !modalOpen()) return [];
    return FORMS.filter(id => { const f = byId(id); return f && base.has(id) && snap(f) !== base.get(id) && !f.closest('.hidden'); });
  }
  function resetToBase(ids) { ids.forEach(id => { const f = byId(id); if (f && base.has(id)) setValues(f, JSON.parse(base.get(id))); }); }

  function refresh() {
    const d = dirty(), mark = byId('lfDirty');
    if (mark) { mark.classList.toggle('hidden', !d.length); mark.textContent = d.length ? `● Nicht gespeichert: ${d.map(id => LABEL[id]).join(', ')}` : ''; }
  }

  // ---- Öffnen: Stand merken, liegengebliebene Eingaben zurückholen, Fokus setzen
  function remember() {
    const a = document.activeElement;
    if (a && a !== document.body && !a.closest('#modal')) lastTrigger = a;
  }

  function afterOpen(existing) {
    FORMS.forEach(id => { const f = byId(id); if (f) base.set(id, snap(f)); });
    armed = true;
    lastLead = leadKey();
    const rec = drafts.get(lastLead);
    if (rec) {
      drafts.delete(lastLead);
      for (const [id, vals] of Object.entries(rec)) { const f = byId(id); if (f) { setValues(f, vals); f.dispatchEvent(new Event('input', {bubbles: true})); } }
      const first = Object.keys(rec)[0];
      if (window.leadTabs && first) window.leadTabs.reveal(byId(first));
      if (typeof toast === 'function') toast('Nicht gespeicherte Eingaben wiederhergestellt – bitte speichern oder verwerfen.');
    }
    refresh();
    // M03: eine bestehende Firma startet im Überblick (Fokus auf den Reiter), nur eine neue Firma im Namensfeld.
    const tab = existing && document.querySelector('[data-lf-tab][aria-selected="true"]');
    if (tab && !rec) tab.focus({preventScroll: true});
    else if (!existing) byId('leadForm')?.elements.company.focus();
  }

  // ---- Schließen: auf jedem Weg nichts still verlieren, Fokus zurückgeben
  function onClose() {
    const d = dirty();
    if (d.length && !discard) {
      const rec = {};
      d.forEach(id => { rec[id] = values(byId(id)); });
      drafts.set(lastLead || leadKey(), rec);
      resetToBase(d);  // damit die Eingaben nicht in der nächsten Firma auftauchen
    } else if (discard) {
      resetToBase(d);
      drafts.delete(lastLead || leadKey());
    }
    discard = false;
    armed = false;
    hideDialog();
    refresh();
    const back = lastTrigger && lastTrigger.isConnected && lastTrigger.offsetParent !== null ? lastTrigger
      : (lastLead && lastLead !== 'neu' ? document.querySelector(`.content:not(.hidden) [data-lead="${lastLead}"]`) : null);
    lastTrigger = null;
    if (back) setTimeout(() => back.focus({preventScroll: false}), 0);
  }

  function requestClose(after) {
    const proceed = () => { if (modalOpen()) closeModal(); if (after) after(); };
    const d = dirty();
    if (!d.length) return proceed();
    ask(d, proceed);
  }

  // ---- Rückfrage
  function ask(d, proceed) {
    const box = byId('lfGuard');
    if (!box) return proceed();
    byId('lfGuardText').textContent = `Nicht gespeichert: ${d.map(id => LABEL[id]).join(', ')}. Was soll damit passieren?`;
    box.classList.remove('hidden');
    onDecision = async choice => {
      if (choice === 'edit') { hideDialog(); return focusDirty(d); }
      if (choice === 'discard') { hideDialog(); discard = true; return proceed(); }
      hideDialog();
      const ok = await saveAll(d);
      if (ok) proceed();
      else focusDirty(dirty());
    };
    box.querySelector('[data-guard="save"]').focus();
  }

  function hideDialog() { byId('lfGuard')?.classList.add('hidden'); onDecision = null; }
  const dialogOpen = () => !!byId('lfGuard') && !byId('lfGuard').classList.contains('hidden');

  function focusDirty(d) {
    const f = byId(d[0]);
    if (!f) return;
    if (window.leadTabs) window.leadTabs.reveal(f);
    const changed = JSON.parse(base.get(d[0]) || '{}'), now = values(f);
    const name = Object.keys(now).find(n => now[n] !== changed[n]);
    const el = name ? f.elements.namedItem(name) : null;
    (el instanceof RadioNodeList ? el[0] : el || f.querySelector('input,textarea,select'))?.focus();
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function saveAll(d) {
    for (const id of d) {
      const f = byId(id);
      if (!f || !modalOpen()) continue;
      if (window.leadTabs) window.leadTabs.reveal(f);
      if (!f.reportValidity()) return false;
      f.requestSubmit();
      // Warten, bis der vorhandene Speicher-Ablauf fertig ist (auch nach einer Rückfrage wie dem Verlustgrund).
      for (let t = 0; t < 600 && modalOpen() && dirty().includes(id); t++) await sleep(100);
      if (modalOpen() && dirty().includes(id)) return false;  // Fehler: Eingaben bleiben stehen, Meldung kam vom Formular
    }
    return true;
  }

  // ---- Erfolgreiches Speichern erkennen: nach einer schreibenden Anfrage gilt der aktuelle Stand als gespeichert.
  document.addEventListener('submit', e => { if (FORMS.includes(e.target.id) && e.target.closest('#modal')) pending = e.target.id; }, true);
  document.addEventListener('reset', e => { if (FORMS.includes(e.target.id)) setTimeout(() => rebase(e.target.id), 0); }, true);
  const plainApi = window.api;
  if (typeof plainApi === 'function') {
    window.api = async function (path, method = 'GET', body) {
      const form = method !== 'GET' ? pending : null;
      if (form) pending = null;
      const result = await plainApi(path, method, body);
      if (form) rebase(form);
      return result;
    };
  }

  document.addEventListener('input', e => { if (e.target.closest && e.target.closest('#modal')) refresh(); }, true);
  document.addEventListener('change', e => { if (e.target.closest && e.target.closest('#modal')) refresh(); }, true);
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-guard]');
    if (b && onDecision) onDecision(b.dataset.guard);
  });
  window.addEventListener('beforeunload', e => { if (dirty().length) { e.preventDefault(); e.returnValue = ''; } });

  window.leadGuard = {remember, afterOpen, onClose, requestClose, dirty, dialogOpen, cancel: () => { hideDialog(); focusDirty(dirty()); }};
})();
