'use strict';
// v1.13: Aufgaben gegliedert – Recherche je Firma zusammengefasst (ein Klick = Firmen-Berichte), danach Kontakt,
// Termine, Angebote, Sonstiges. Erledigt-Haken, Freigabesperre und Löschen funktionieren wie bisher (app.js).
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const REPORT = {fertig: ['Bericht fertig', 'ok'], running: ['Bericht läuft …', 'wait'], queued: ['Bericht wartet …', 'wait'], fehler: ['Bericht mit Fehler', 'off'], '': ['noch kein Bericht', 'off']};
  const SHOW = 10;
  let data = null, showAllFirms = false, timer = null;
  const open = {};
  const store = {get: k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch { return null; } },
                 set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privat */ } }};

  function itemLine(it) {
    const today = new Date().toISOString().slice(0, 10);
    if (it.type === 'task') {
      return taskLine({id: it.id, done: 0, title: it.title, company: it.company === 'Allgemein' ? '' : it.company, permission_status: it.permission_status,
        channel: it.channel, due_date: it.due}, today);
    }
    return `<div class="task-line tk-step"><span class="tk-dot" aria-hidden="true">›</span><span><b>${esc(it.title)}</b><small> · ${esc(it.company)}</small></span>
      <small class="${it.overdue || (it.due && it.due <= today) ? 'late' : ''}">${it.due ? fmtDate(it.due) : 'ohne Termin'}</small>
      <button type="button" class="btn btn-ghost" data-lead="${it.lead_id}">Öffnen</button></div>`;
  }

  function firmLine(f) {
    const r = REPORT[f.report] || [f.report, 'mid'];
    const btn = f.report === 'fertig' ? `<button type="button" class="btn btn-ghost" data-report-open="${f.lead_id}">Bericht öffnen</button>`
      : f.website ? `<button type="button" class="btn btn-ghost" data-tk-report="${f.lead_id}" ${['queued', 'running'].includes(f.report) ? 'disabled' : ''}>Bericht erstellen</button>`
      : `<button type="button" class="btn btn-ghost" data-lead="${f.lead_id}" title="Ohne Website kein Bericht – Website im Lead ergänzen">Website ergänzen</button>`;
    return `<div class="task-line tk-firm"><span><b>${esc(f.company)}</b>${f.steps.length ? `<small> · ${esc(f.steps[0])}${f.steps.length > 1 ? ` (+${f.steps.length - 1})` : ''}</small>` : ''}</span>
      <span class="tk-chips"><span class="sw-web ${f.website ? 'ok' : 'off'}">${f.website ? 'Website' : 'ohne Website'}</span><span class="sw-web ${r[1]}">${esc(r[0])}</span></span>${btn}</div>`;
  }

  function groupBody(g) {
    if (g.key !== 'recherche') return g.items.map(itemLine).join('') || '<div class="empty">Nichts offen.</div>';
    const firms = g.firms || [];
    const pending = firms.filter(f => f.website && !['fertig', 'queued', 'running'].includes(f.report));
    const shown = showAllFirms ? firms : firms.slice(0, SHOW);
    return `<div class="tk-bar"><button type="button" class="btn btn-primary" data-tk-bulk ${pending.length ? '' : 'disabled'}>▶ Firmen-Berichte für ${pending.length} Firma/Firmen mit Website erstellen</button>
        <button type="button" class="btn btn-ghost" data-tk-cleanup>Erledigte Recherche-Schritte bereinigen</button>
        <span class="muted">Ein Bericht erledigt Impressum, Website-Bewertung, Inhalte, Kaufsignale und Paketvorschlag – leere Felder werden automatisch aus dem Impressum gefüllt.</span></div>
      ${shown.map(firmLine).join('') || '<div class="empty">Keine Firma in der Recherche.</div>'}
      ${firms.length > SHOW ? `<button type="button" class="text-button" data-tk-more>${showAllFirms ? 'weniger anzeigen' : `alle ${firms.length} Firmen anzeigen`}</button>` : ''}
      ${g.items.length ? `<div class="sales-subhead">Weitere Recherche-Aufgaben</div>${g.items.map(itemLine).join('')}` : ''}`;
  }

  function render() {
    if (!data || !$('#tkGroups')) return;
    const groups = data.groups.filter(g => g.count);
    $('#tkSummary').innerHTML = data.groups.map(g => `<button type="button" class="tk-sum ${g.count ? '' : 'zero'}" data-tk-jump="${esc(g.key)}"><small>${esc(g.label.toUpperCase())}</small><b>${g.count}</b>${g.overdue ? `<span class="late">${g.overdue} überfällig</span>` : ''}</button>`).join('');
    $('#tkGroups').innerHTML = groups.length ? groups.map(g => {
      const isOpen = open[g.key] ?? true;
      const unit = g.key === 'recherche' ? `${(g.firms || []).length} Firmen${g.items.length ? ` · ${g.items.length} Aufgaben` : ''}` : `${g.count} offen`;
      return `<details class="panel tk-group" data-tk-group="${esc(g.key)}" id="tk-${esc(g.key)}" ${isOpen ? 'open' : ''}><summary><b>${esc(g.label)}</b><span class="muted">${unit}</span>${g.overdue ? `<span class="late">${g.overdue} überfällig</span>` : ''}</summary>
        <div class="tasks">${groupBody(g)}</div></details>`;
    }).join('') : '<div class="panel empty">Alles erledigt – keine offenen Aufgaben oder nächsten Schritte.</div>';
    applyDataWidths($('#tkGroups'));
    clearTimeout(timer);
    if (currentView === 'tasks' && (data.groups.find(g => g.key === 'recherche')?.firms || []).some(f => ['queued', 'running'].includes(f.report))) timer = setTimeout(window.refreshTaskOverview, 5000);
  }

  window.refreshTaskOverview = async function () {
    if (!$('#tkGroups')) return;
    try { data = await api('/tasks/overview'); render(); }
    catch (e) { $('#tkGroups').innerHTML = `<div class="panel empty">${esc(e.message)}</div>`; }
  };

  async function startReports(ids) {
    let queued = 0, skipped = 0;
    for (let i = 0; i < ids.length; i += 50) {
      const r = await api('/reports', 'POST', {lead_ids: ids.slice(i, i + 50)});
      queued += r.queued.length; skipped += r.skipped.length;
    }
    toast(`${queued} Firmen-Bericht(e) gestartet${skipped ? ` · ${skipped} übersprungen` : ''}`);
    await window.refreshTaskOverview();
  }

  function init() {
    if (!$('#tkGroups')) return;
    Object.assign(open, store.get('tk_open') || {});
    $('#tkGroups').addEventListener('toggle', e => {
      const g = e.target.closest?.('[data-tk-group]');
      if (g) { open[g.dataset.tkGroup] = g.open; store.set('tk_open', open); }
    }, true);
    document.body.addEventListener('click', async e => {
      const one = e.target.closest('[data-tk-report]');
      if (one) { one.disabled = true; try { await startReports([Number(one.dataset.tkReport)]); } catch (err) { one.disabled = false; toast(err.message, true); } return; }
      const bulk = e.target.closest('[data-tk-bulk]');
      if (bulk) {
        const firms = (data?.groups.find(g => g.key === 'recherche')?.firms || []).filter(f => f.website && !['fertig', 'queued', 'running'].includes(f.report));
        if (!firms.length) return;
        if (firms.length > 20 && !confirm(`${firms.length} Firmen-Berichte nacheinander erstellen? Das dauert je Firma etwa eine Minute und läuft im Hintergrund.`)) return;
        bulk.disabled = true;
        try { await startReports(firms.map(f => f.lead_id)); } catch (err) { bulk.disabled = false; toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-tk-cleanup]')) {
        try { const r = await api('/tasks/research-cleanup', 'POST', {}); toast(`${r.updated} Recherche-Schritt(e) erledigt – nächster Schritt: Kontaktweg klären`); if (typeof reload === 'function') await reload(); else window.refreshTaskOverview(); }
        catch (err) { toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-tk-more]')) { showAllFirms = !showAllFirms; render(); return; }
      const j = e.target.closest('[data-tk-jump]');
      if (j) { const d = $(`#tk-${j.dataset.tkJump}`); if (d) { d.open = true; d.scrollIntoView({behavior: 'smooth', block: 'start'}); } }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
