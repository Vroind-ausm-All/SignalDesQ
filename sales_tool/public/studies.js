'use strict';
// 2.0.0-dev47 (Roadmap M30/M34): Erlebnisstudien mit echten Testpersonen und „Was du lernst“ (Aufwand und Wirkung mit Grenzen).
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const OUT = {geschafft: 'geschafft', mit_hilfe: 'mit Hilfe', nicht_geschafft: 'nicht geschafft', nicht_bearbeitet: 'nicht bearbeitet'};
  const DEV = {desktop: 'Desktop', smartphone: 'Smartphone', tablet: 'Tablet'};
  const PHASE = {vorher: 'vorher', nachher: 'nachher', einmalig: 'einmalig'};
  let current = null;
  const pct = (v, n) => (v === null || v === undefined ? '–' : `${v} %`) + (n !== undefined ? ` <small>(${n})</small>` : '');

  async function loadLearning() {
    if (!$('#lnBox')) return;
    try {
      const o = await api('/lernen');
      const few = n => `<small class="muted">erst ${n} – Aussage ab ${o.min_cases}</small>`;
      $('#lnEffort').innerHTML = o.effort.length ? `<ul>${o.effort.map(g => `<li data-ln-type="${esc(g.type)}"><b>${esc(g.title)}</b>: ${g.enough
        ? `im Mittel ${Math.abs(g.avg_variance_pct)} % ${g.avg_variance_pct > 0 ? 'mehr' : 'weniger'} Zeit als kalkuliert · Stundensatz (Median) ${g.median_hourly ?? '–'} € · ${g.below_minimum} unter Mindestverdienst <small>(${g.n} Aufträge)</small>` : few(g.n)}</li>`).join('')}</ul>` : '<p class="muted">Noch keine abgeschlossenen Aufträge mit Zeiten.</p>';
      $('#lnMethods').innerHTML = o.methods.length ? `<ul>${o.methods.map(m => `<li><b>${esc(m.method)}</b>: ${m.enough ? `Aufgabenerfolg im Mittel ${m.avg_success_pct} % <small>(${m.studies} Studien, ${m.sessions} Sitzungen)</small>` : few(m.studies)}</li>`).join('')}</ul>` : '<p class="muted">Noch keine Studie mit bestätigten Sitzungen.</p>';
      $('#lnBeforeAfter').innerHTML = o.before_after.length ? `<ul>${o.before_after.map(g => `<li><b>${esc(g.title)}</b>: ${g.enough ? `Aufgabenerfolg nach dem Projekt im Mittel ${g.avg_delta_points > 0 ? '+' : ''}${g.avg_delta_points} Prozentpunkte <small>(${g.pairs} Vorher/Nachher-Paare)</small>` : few(g.pairs)}</li>`).join('')}</ul>` : '<p class="muted">Noch kein Vorher/Nachher-Paar derselben Firma.</p>';
      $('#lnLimits').innerHTML = o.limits.map(l => `<li>${esc(l)}</li>`).join('');
    } catch (e) { $('#lnEffort').textContent = e.message; }
  }

  async function load() {
    if (!$('#stBox')) return;
    try {
      const o = await api('/studien');
      $('#stLead').innerHTML = o.leads.map(l => `<option value="${l.id}">${esc(l.company)}</option>`).join('');
      $('#stList').innerHTML = o.studies.length ? o.studies.map(s => `<div class="sales-item"><div><strong>${esc(s.title)} · ${esc(s.company)}</strong><small>${esc(PHASE[s.phase])} · ${esc(s.method)} · ${s.sessions} bestätigte Sitzung(en) · Aufgabenerfolg ${pct(s.overall_success_pct)}${s.status !== 'laeuft' ? ' · abgeschlossen' : ''}</small></div><button type="button" class="btn btn-ghost" data-st-open="${s.id}">Öffnen</button></div>`).join('') : '<div class="empty">Noch keine Studie.</div>';
      $('#stNotice').textContent = o.notice;
    } catch (e) { $('#stNotice').textContent = e.message; }
    loadLearning();
  }

  function sessionHtml(v, se) {
    const open = v.status === 'laeuft';
    const dis = open ? '' : 'disabled';
    return `<details class="st-session" data-st-session="${se.id}" ${se.confirmed ? '' : 'open'}><summary><b>${esc(se.code)}</b> · ${esc(DEV[se.device])} · Zielgruppe ${esc(se.target_group)}${se.held_on ? ' · ' + esc(se.held_on) : ''} ${se.confirmed ? '<span class="sw-web ok">bestätigt</span>' : '<span class="sw-web wait">zählt noch nicht</span>'}</summary>
      ${v.tasks.map(t => { const r = se.results[t.id] || {}; return `<div class="st-task"><small class="muted">${t.kind === 'aufgabe' ? 'Aufgabe' : 'Frage'} ${t.pos}: ${esc(t.text)}</small>
        ${t.kind === 'aufgabe' ? `<div class="st-row"><select data-st-s="${se.id}" data-st-t="${t.id}" data-st-k="outcome" ${dis} aria-label="Ergebnis ${esc(se.code)} Aufgabe ${t.pos}"><option value="">– Ergebnis –</option>${Object.entries(OUT).map(([k, l]) => `<option value="${k}" ${r.outcome === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <label>Sekunden<input type="number" min="0" max="7200" data-st-s="${se.id}" data-st-t="${t.id}" data-st-k="seconds" value="${r.seconds ?? ''}" ${dis}></label>
          <label class="st-wide">Beobachtung<input data-st-s="${se.id}" data-st-t="${t.id}" data-st-k="note" value="${esc(r.note || '')}" maxlength="500" ${dis}></label></div>`
          : `<label class="st-wide">Antwort der Testperson (wörtlich oder sinngemäß notiert)<textarea rows="2" data-st-s="${se.id}" data-st-t="${t.id}" data-st-k="answer" maxlength="2000" ${dis}>${esc(r.answer || '')}</textarea></label>`}</div>`; }).join('')}
      <label class="check st-confirm"><input type="checkbox" data-st-s="${se.id}" data-st-k="confirmed" ${se.confirmed ? 'checked' : ''} ${dis}> Die Angaben stammen von dieser Testperson (nicht ausgedacht, nicht von einer KI).</label>
      ${open ? `<button type="button" class="text-button" data-st-del="${se.id}">Sitzung löschen</button>` : ''}</details>`;
  }

  function render(v) {
    current = v;
    const a = v.analysis;
    const open = v.status === 'laeuft';
    $('#stDetail').innerHTML = `<div class="sales-subhead">${esc(v.title)} · ${esc(v.company)} · ${esc(PHASE[v.phase])} · ${esc(v.method)}${v.url ? ` · <a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">${esc(v.url)} ↗</a>` : ''}</div>
      <div class="pl-metrics"><div class="pl-metric" data-st-overall><span>Aufgabenerfolg gesamt</span><b>${pct(a.overall_success_pct)}</b></div>
        <div class="pl-metric"><span>Bestätigte Sitzungen</span><b>${a.sample.sessions}</b><small>${Object.entries(a.sample.devices).filter(([, n]) => n).map(([d, n]) => `${n} ${DEV[d]}`).join(' · ') || '–'}</small></div>
        <div class="pl-metric"><span>Zielgruppe</span><b>${a.sample.target_group.ja} ja</b><small>${a.sample.target_group.nein} nein · ${a.sample.target_group.unklar} unklar</small></div>
        ${v.compare ? `<div class="pl-metric" data-st-compare><span>${v.phase === 'nachher' ? 'Vorher' : 'Nachher'} (andere Studie)</span><b>${pct(v.compare.overall_success_pct)}</b><small>${v.compare.sessions} Sitzungen</small></div>` : ''}</div>
      ${a.notice ? `<p class="muted" data-st-notice>${esc(a.notice)}</p>` : ''}
      <div class="table-wrap"><table class="acc-table"><thead><tr><th>Aufgabe</th><th>Erfolg</th><th>mit Hilfe</th><th>Median Zeit</th></tr></thead><tbody>
        ${a.tasks.filter(t => t.kind === 'aufgabe').map(t => `<tr><td>${esc(t.text)}</td><td data-st-task="${t.id}">${pct(t.success_pct, `${t.success} von ${t.tried}`)}</td><td>${t.helped}</td><td>${t.median_seconds === null ? '–' : t.median_seconds + ' s'}</td></tr>`).join('')}</tbody></table></div>
      ${a.tasks.filter(t => t.kind === 'frage').map(t => `<details><summary>Antworten: ${esc(t.text)} (${t.answers.length})</summary><ul>${t.answers.map(x => `<li><b>${esc(x.code)}:</b> ${esc(x.text)}</li>`).join('')}</ul></details>`).join('')}
      <h4>Sitzungen</h4>${v.sessions.map(se => sessionHtml(v, se)).join('') || '<p class="muted">Noch keine Sitzung.</p>'}
      ${open ? `<form id="stSessionForm" class="sales-row"><label>Gerät<select name="device">${Object.entries(DEV).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select></label>
        <label>Zielgruppe<select name="target_group"><option value="ja">ja</option><option value="nein">nein</option><option value="unklar" selected>unklar</option></select></label>
        <label>Wie gewonnen<input name="recruited_via" maxlength="120" placeholder="z. B. Kundenkontakt, Bekanntenkreis"></label>
        <label>Datum<input name="held_on" type="date"></label><button class="btn btn-ghost" type="submit">Sitzung hinzufügen</button></form>
        <button type="button" class="btn btn-ghost" id="stClose">Studie abschließen</button>` : ''}`;
    $('#stSessionForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target));
      try { render(await api(`/studien/${v.id}/sitzungen`, 'POST', d)); toast('Sitzung angelegt – Testperson bekommt ein Kürzel, keinen Namen'); } catch (err) { toast(err.message, true); }
    });
    $('#stClose')?.addEventListener('click', async () => {
      if (!confirm('Studie abschließen? Danach sind keine Änderungen mehr möglich.')) return;
      try { render(await api(`/studien/${v.id}/abschliessen`, 'POST', {})); load(); } catch (err) { toast(err.message, true); }
    });
  }

  // 2.0.0-dev52: Speichern der Reihe nach; beim Neuzeichnen bleiben ungespeicherte Eingaben in anderen Feldern stehen (uiKeep).
  // Vorher ersetzte das Neuzeichnen nach einer Auswahl den Text, den man gerade in ein anderes Feld tippte.
  const queue = window.uiSerial ? window.uiSerial() : fn => fn();
  function save(el) {
    const k = el.dataset.stK, sid = el.dataset.stS;
    const body = k === 'confirmed' ? {confirmed: el.checked} : {task_id: Number(el.dataset.stT), [k]: k === 'seconds' ? (el.value === '' ? null : Number(el.value)) : el.value};
    return queue(async () => {
      try {
        const v = await api(`/studien/sitzung/${sid}`, 'POST', body);
        const openSessions = $$('#stDetail details[data-st-session][open]').map(d => d.dataset.stSession);
        const y = window.scrollY;
        const draw = () => { render(v); openSessions.forEach(id => { const d = $(`#stDetail details[data-st-session="${id}"]`); if (d) d.open = true; }); };
        if (window.uiKeep) window.uiKeep($('#stDetail'), '[data-st-s]', draw); else draw();
        window.scrollTo(0, y);
      } catch (e) { toast(e.message, true); }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#stBox')) return;
    $('#stCreate').addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target;
      const lines = v => v.split('\n').map(s => s.trim()).filter(Boolean);
      const body = {lead_id: Number(f.lead_id.value), title: f.title.value, url: f.url.value, phase: f.phase.value, method: f.method.value,
                    tasks: lines(f.tasks.value), questions: lines(f.questions.value)};
      try { render(await api('/studien', 'POST', body)); f.reset(); toast('Studie angelegt'); load(); } catch (err) { toast(err.message, true); }
    });
    document.addEventListener('click', async e => {
      const o = e.target.closest('[data-st-open]');
      if (o) { try { render(await api(`/studien/${o.dataset.stOpen}`)); } catch (err) { toast(err.message, true); } }
      const d = e.target.closest('[data-st-del]');
      if (d && confirm('Sitzung mit allen Angaben löschen?')) { try { render(await api(`/studien/sitzung/${d.dataset.stDel}`, 'DELETE')); } catch (err) { toast(err.message, true); } }
    });
    document.addEventListener('change', e => { const el = e.target.closest('[data-st-s]'); if (el && current) save(el); });
    $('#stBox').addEventListener('toggle', () => { if ($('#stBox').open) load(); });
    $('#lnBox').addEventListener('toggle', () => { if ($('#lnBox').open) loadLearning(); });
  });
})();
