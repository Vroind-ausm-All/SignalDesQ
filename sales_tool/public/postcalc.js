'use strict';
// 2.0.0-dev5: Nachkalkulation – tatsächliche Stunden je angenommenem Angebot, Soll/Ist, Auftragsabschluss.
// Nur für dich: Der Kunde sieht weder Stunden noch diese Auswertung.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const num = v => (v === null || v === undefined ? '–' : String(v).replace('.', ','));
  const eur = v => (v === null || v === undefined ? '–' : Number(v).toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' €');
  const ST = {nicht_begonnen: ['keine Zeiten', 'wait'], laeuft: ['läuft', 'ok'], ueberzogen: ['über Kalkulation', 'bad'], abgeschlossen: ['abgeschlossen', 'mid']};

  // 2.0.0-dev27 (M20): Soll/Ist je Angebotsposition
  function posTable(p) {
    if (!p.positions || p.positions.length < 2) return '';
    return `<table class="pk-pos"><thead><tr><th>Position</th><th>kalkuliert</th><th>gebraucht</th><th>Abweichung</th></tr></thead><tbody>
      ${p.positions.map(x => `<tr><td>Pos. ${x.n} ${esc(x.title)}</td><td>${num(x.estimated_hours)} h</td><td>${num(x.actual_hours)} h</td><td class="${x.variance_pct > 15 ? 'rc-late' : ''}">${x.variance_pct == null ? '–' : (x.variance_pct > 0 ? '+' : '') + x.variance_pct + ' %'}</td></tr>`).join('')}
      ${p.unassigned_hours ? `<tr><td class="muted">ohne Position</td><td></td><td>${num(p.unassigned_hours)} h</td><td></td></tr>` : ''}</tbody></table>`;
  }

  function card(p) {
    const st = ST[p.status] || [p.status, 'wait'];
    const pct = p.estimated_hours ? Math.min(100, Math.round(100 * p.actual_hours / p.estimated_hours)) : 0;
    return `<article class="pk-card ${p.done ? 'done' : ''}" data-pk="${p.proposal_id}">
      <div class="pk-head"><div><b>${esc(p.company)}</b> <span class="sw-web ${st[1]}">${esc(st[0])}</span>${p.handover ? ` <span class="sw-web ${p.handover.status === 'abgenommen' ? 'ok' : 'wait'}">Abnahme: ${esc(p.handover.label)}</span>` : ''}<small>${esc(p.number)}${p.label ? ' · ' + esc(p.label) : ''} · ${eur(p.net_eur)} netto</small></div>
        <div class="pk-nums"><span><small>kalkuliert</small><b>${num(p.estimated_hours)} h</b></span><span><small>gebraucht</small><b>${num(p.actual_hours)} h</b></span>
          <span><small>${p.done ? 'Verdienst je Stunde' : 'übrig'}</small><b class="${p.below_minimum ? 'rc-late' : ''}">${p.done ? eur(p.actual_hourly) : num(p.remaining_hours) + ' h'}</b></span></div></div>
      <div class="priority-bar pk-bar ${p.status === 'ueberzogen' ? 'over' : ''}"><i data-w="${pct}"></i></div>
      <p class="${p.below_minimum || p.status === 'ueberzogen' ? 'rc-late' : ''}">${esc(p.verdict)}${p.closing_note ? ' · ' + esc(p.closing_note) : ''}</p>
      ${p.done ? `<button type="button" class="text-button" data-pk-reopen="${p.proposal_id}">Wieder öffnen</button>` : `
      ${posTable(p)}
      <form class="pk-form" data-pk-form="${p.proposal_id}"><input type="date" name="work_date" aria-label="Datum" max="${new Date().toISOString().slice(0, 10)}">
        ${p.positions.length > 1 ? `<select name="position" aria-label="Position"><option value="">Auftrag allgemein</option>${p.positions.map(x => `<option value="${x.n}">Pos. ${x.n} ${esc(x.title)}</option>`).join('')}</select>` : ''}
        <input type="number" name="hours" min="0.1" max="200" step="any" placeholder="Stunden" aria-label="Stunden" required>
        <input name="note" maxlength="300" placeholder="Was? (optional)" aria-label="Notiz"><button type="submit" class="btn btn-primary">Zeit erfassen</button></form>
      ${p.entries.length ? `<details class="pk-entries"><summary>${p.entries.length} ${p.entries.length === 1 ? 'Eintrag' : 'Einträge'}</summary>${p.entries.map(e => `<div><span>${esc(fmtDate(e.work_date))} · ${num(e.hours)} h${e.note ? ' · ' + esc(e.note) : ''}</span>
        <button type="button" class="text-button" data-pk-del="${e.id}" aria-label="Eintrag löschen">✕</button></div>`).join('')}</details>
        <form class="pk-form pk-close" data-pk-close="${p.proposal_id}"><input type="number" name="ext" min="0" step="0.01" placeholder="Fremdkosten tatsächlich (${num(p.estimated_external_eur)} € kalkuliert)" aria-label="Tatsächliche Fremdkosten">
          <input name="note" maxlength="500" placeholder="Was lief anders? (optional)" aria-label="Notiz zum Abschluss"><button type="submit" class="btn btn-ghost">Auftrag abschließen</button></form>` : ''}`}
    </article>`;
  }

  async function refresh() {
    const box = $('#pkList');
    if (!box) return;
    try {
      const r = await api('/postcalc');
      $('#pkCount').textContent = r.projects.length ? `${r.open} laufend · ${r.projects.length - r.open} abgeschlossen` : '';
      $('#pkLesson').textContent = r.lesson ? r.lesson.text : '';
      const sl = $('#pkServiceLessons');
      if (sl) sl.innerHTML = r.service_lessons?.length ? `<div class="sales-subhead">Je Leistung (aus abgeschlossenen Aufträgen)</div><ul>${r.service_lessons.map(x => `<li>${esc(x.text)}${x.suggestion ? `<small>${esc(x.suggestion)}</small>` : ''}</li>`).join('')}</ul>` : '';
      box.innerHTML = r.projects.length ? r.projects.map(card).join('') : '<div class="empty">Noch kein angenommenes Angebot. Sobald ein Angebot angenommen ist, erfasst du hier deine Zeiten.</div>';
      $('#pkNotice').textContent = r.notice;
      if (typeof applyDataWidths === 'function') applyDataWidths(box);
    } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }
  window.refreshPostcalc = refresh;

  document.addEventListener('DOMContentLoaded', () => {
    // Einfangphase: andere Formular-Behandler der Angebotsseite dürfen diese Formulare nicht als Angebot deuten
    document.addEventListener('submit', async e => {
      const add = e.target.closest('[data-pk-form]'), close = e.target.closest('[data-pk-close]');
      if (!add && !close) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const f = e.target.elements;
      try {
        if (add) {
          const body = {proposal_id: Number(add.dataset.pkForm), hours: Number(f.hours.value), note: f.note.value.trim()};
          if (f.position && f.position.value) body.position = Number(f.position.value);
          if (f.work_date.value) body.work_date = f.work_date.value;
          await api('/postcalc/entries', 'POST', body);
          toast('Zeit erfasst');
        } else {
          const body = {note: f.note.value.trim()};
          if (f.ext.value !== '') body.actual_external_eur = Number(f.ext.value);
          const p = await api(`/postcalc/${close.dataset.pkClose}/close`, 'POST', body);
          toast(p.verdict, p.below_minimum);
        }
        await refresh();
        if (window.refreshReach) await window.refreshReach();
      } catch (err) { toast(err.message, true); }
    }, true);
    document.body.addEventListener('click', async e => {
      const del = e.target.closest('[data-pk-del]'), re = e.target.closest('[data-pk-reopen]');
      if (!del && !re) return;
      try {
        if (del) await api(`/postcalc/entries/${del.dataset.pkDel}`, 'DELETE');
        if (re) await api(`/postcalc/${re.dataset.pkReopen}/reopen`, 'POST', {});
        await refresh();
        if (window.refreshReach) await window.refreshReach();
      } catch (err) { toast(err.message, true); }
    });
    document.querySelectorAll('[data-go="quotes"]').forEach(b => b.addEventListener('click', refresh));
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'quotes') refresh(); });  // 2.0.0-dev14: Bereichsreiter
    const orig = window.reload;
    if (typeof orig === 'function') window.reload = async function (...args) { const r = await orig.apply(this, args); await refresh(); return r; };
    refresh();
  });
})();
