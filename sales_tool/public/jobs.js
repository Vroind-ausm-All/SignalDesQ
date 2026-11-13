'use strict';
// v1.16 (Masterplan 2.0, Sprint 3): Recherche-Aufträge – Fortschritt je Firma/Quelle, Pause, Fortsetzen, Abbrechen,
// Fehlgeschlagene erneut. Aufträge laufen im Hintergrund weiter und überstehen einen Neustart von SignalDesk.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const STATUS = {queued: ['wartet', 'wait'], running: ['läuft', 'wait'], paused: ['pausiert', 'mid'], done: ['fertig', 'ok'],
    partial: ['teilweise fertig', 'mid'], failed: ['fehlgeschlagen', 'bad'], cancelled: ['abgebrochen', 'off'], skipped: ['übersprungen', 'off']};
  const KIND = {sweep: 'Sammelsuche', website: 'Website-Suche', report: 'Firmen-Berichte', catalog_import: 'GLEIF-Katalog'};
  const open = new Set();
  let timer = null;

  function pill(st) {
    const s = STATUS[st] || [st, 'off'];
    return `<span class="sw-web ${s[1]}">${esc(s[0])}</span>`;
  }

  function taskRow(t) {
    const info = t.status === 'queued' && t.retry_in ? `neuer Versuch in ${t.retry_in} s` : (t.note || '');
    return `<div class="jb-task ${esc(t.status)}"><span>${esc(t.label || t.task_key)}</span>${pill(t.status)}
      <small>${t.attempts > 1 ? `${t.attempts}. Versuch · ` : ''}${esc(info)}${t.last_error ? ` <span class="late">${esc(t.last_error)}</span>` : ''}</small></div>`;
  }

  function jobRow(j, detail) {
    const finished = j.done + j.failed + j.skipped;
    const pct = j.total ? Math.round(100 * finished / j.total) : 0;
    const active = ['queued', 'running', 'paused'].includes(j.status);
    const btns = [
      ['queued', 'running'].includes(j.status) ? `<button type="button" class="text-button" data-jb="pause" data-id="${j.id}">Pausieren</button>` : '',
      j.status === 'paused' ? `<button type="button" class="text-button" data-jb="resume" data-id="${j.id}">Fortsetzen</button>` : '',
      active ? `<button type="button" class="text-button" data-jb="cancel" data-id="${j.id}">Abbrechen</button>` : '',
      j.failed ? `<button type="button" class="text-button" data-jb="retry" data-id="${j.id}">Fehlgeschlagene erneut</button>` : '',
      `<button type="button" class="text-button" data-jb="toggle" data-id="${j.id}">${open.has(j.id) ? 'Details zu' : 'Details'}</button>`].join('');
    return `<article class="jb-job ${esc(j.status)}"><div class="jb-head"><div><b>${esc(j.label)}</b><small>${esc(KIND[j.kind] || j.kind)} · ${finished}/${j.total}
      ${j.failed ? ` · <span class="late">${j.failed} mit Fehler</span>` : ''}${j.skipped ? ` · ${j.skipped} übersprungen` : ''}</small></div>${pill(j.status)}</div>
      <div class="jb-bar"><i data-w="${pct}"></i></div><div class="jb-btns">${btns}</div>
      ${detail ? `<div class="jb-tasks">${detail.tasks.map(taskRow).join('')}</div>` : ''}</article>`;
  }

  async function render(box) {
    const kind = box.dataset.jobsPanel || '';
    try {
      const r = await api('/research/jobs' + (kind ? `?kind=${encodeURIComponent(kind)}` : ''));
      const list = r.jobs.filter(j => ['queued', 'running', 'paused'].includes(j.status) || open.has(j.id)).concat(
        r.jobs.filter(j => !['queued', 'running', 'paused'].includes(j.status) && !open.has(j.id)).slice(0, 4));
      const details = {};
      await Promise.all([...open].filter(id => list.some(j => j.id === id)).map(async id => { details[id] = await api(`/research/jobs/${id}`); }));
      box.innerHTML = list.length ? `<div class="jb-meta muted">Hintergrund-Aufträge laufen weiter, auch nach einem Neustart von SignalDesk. Gleichzeitig: höchstens ${r.max_workers} Websites, je Domain eine.</div>`
        + list.map(j => jobRow(j, details[j.id])).join('') : '<div class="empty">Noch keine Recherche-Aufträge.</div>';
      applyDataWidths(box);
      return list.some(j => ['queued', 'running'].includes(j.status));
    } catch (e) {
      box.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
      return false;
    }
  }

  window.refreshJobs = async function () {
    clearTimeout(timer);
    const boxes = $$('[data-jobs-panel]').filter(b => b.offsetParent !== null);
    const busy = (await Promise.all(boxes.map(render))).some(Boolean);
    if (busy) timer = setTimeout(window.refreshJobs, 3000);
  };

  function init() {
    if (!$$('[data-jobs-panel]').length) return;
    document.body.addEventListener('click', async e => {
      const b = e.target.closest('[data-jb]');
      if (!b) return;
      const id = Number(b.dataset.id);
      if (b.dataset.jb === 'toggle') { open.has(id) ? open.delete(id) : open.add(id); return window.refreshJobs(); }
      if (b.dataset.jb === 'cancel' && !confirm('Auftrag abbrechen? Bereits erledigte Schritte bleiben erhalten.')) return;
      try {
        await api(`/research/jobs/${id}/${b.dataset.jb}`, 'POST', {});
        toast({pause: 'Auftrag pausiert', resume: 'Auftrag läuft weiter', cancel: 'Auftrag abgebrochen', retry: 'Fehlgeschlagene Schritte laufen erneut'}[b.dataset.jb]);
      } catch (err) { toast(err.message, true); }
      window.refreshJobs();
    });
    const orig = window.switchView;
    if (typeof orig === 'function') {
      window.switchView = function (view) { orig(view); if (['finder', 'center'].includes(view)) setTimeout(window.refreshJobs, 50); };
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
