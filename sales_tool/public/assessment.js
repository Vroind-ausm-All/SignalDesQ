'use strict';
// 2.0.0-dev2: Zielkundenprofil, Bewertung (Passung vor / Qualifizierung nach dem Gespräch), Erreichbarkeit, Verlustgrund.
// Nur Anzeige und Einstellungen – nichts wird versendet, keine Firmendaten werden geändert.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const ST = {passt: 'ok', teilweise: 'mid', passt_nicht: 'bad', unbekannt: 'wait'};
  const GRADE = {A: ['A', 'ok', 'passt gut'], B: ['B', 'mid', 'passt teilweise'], C: ['C', 'bad', 'passt kaum'], X: ['✕', 'bad', 'Ausschluss']};
  const REACH = {bereit: ['Kontaktweg belegt', 'ok'], versuch_offen: ['Versuch offen', 'mid'], ausgeschoepft: ['Kanal wechseln', 'mid'],
    kein_weg: ['kein Kontaktweg', 'wait'], gesperrt: ['gesperrt', 'bad']};
  const QUAL = {offen: 'wait', teilweise: 'mid', qualifiziert: 'ok', nicht_qualifiziert: 'bad'};
  let grades = {}, meta = null;

  const gradeChip = g => {
    const x = GRADE[g];
    return x ? `<span class="as-grade ${x[1]}" title="Passung: ${x[2]}">${x[0]}</span>` : '<span class="as-grade wait" title="Datenlage unzureichend">?</span>';
  };

  function criteria(list) {
    return `<ul class="as-crit">${list.map(c => `<li class="${ST[c.status]}"><span><b>${esc(c.label)}</b> <em class="sw-web ${ST[c.status]}">${esc(c.status_label)}</em></span>
      <small>${esc(c.detail)}</small>${c.action ? `<button type="button" class="text-button" ${c.action.view === 'quality' ? 'data-as-profile' : `data-lf-go='${esc(JSON.stringify(c.action))}'`}>${esc(c.action.label)}</button>` : ''}</li>`).join('')}</ul>`;
  }

  const kos = list => list.map(k => `<div class="as-ko" role="alert">⛔ <b>${esc(k.label)}</b> – ${esc(k.detail)}</div>`).join('');

  // Block für die Firmenakte
  window.renderAssessment = function (a) {
    if (!a) return '';
    const f = a.fit, q = a.qualification, r = a.reachability, rs = REACH[r.status] || [r.status, 'wait'];
    return `<div class="as-box" id="lfAssessment"><div class="as-head"><span class="eyebrow">BEWERTUNG</span><b>${esc(a.headline)}</b></div>
      <div class="as-cols">
        <section><h4>${gradeChip(f.grade)} Passung <small>vor dem Gespräch${f.score !== null ? ` · ${f.score} von 100` : ''} · ${f.coverage_pct} % bekannt</small></h4>
          <p>${esc(f.verdict)}</p>${kos(f.knockouts)}${f.warnings.map(w => `<div class="as-warn">⚠ ${esc(w)}</div>`).join('')}
          ${criteria(f.criteria)}<small class="muted">Profil „${esc(f.profile_name)}“. ${esc(f.notice)}</small></section>
        <section><h4><span class="sw-web ${QUAL[q.status]}">${esc(q.status_label)}</span> Qualifizierung <small>nach dem Gespräch</small></h4>
          <p>${esc(q.verdict)}</p>${kos(q.knockouts)}${q.criteria.length ? criteria(q.criteria) : ''}
          ${q.questions.length ? `<div class="as-q"><b>Fragen fürs nächste Gespräch</b><ul>${q.questions.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
          <small class="muted">${esc(q.notice)}</small></section>
        <section><h4><span class="sw-web ${rs[1]}">${esc(rs[0])}</span> Erreichbarkeit <small>${r.attempts_total} Versuche, ${r.reached_total}× erreicht</small></h4>
          <p>${esc(r.hint)}</p>
          <ul class="as-crit">${r.channels.map(c => `<li class="${c.blocked ? 'bad' : c.known ? 'ok' : 'wait'}"><span><b>${esc(c.label)}</b> <em class="sw-web ${c.known ? 'ok' : 'wait'}">${c.known ? 'belegt' : 'unbekannt'}</em></span>
            <small>${c.known ? esc(c.value) + ' · ' : ''}${c.source && c.source.startsWith('OpenStreetMap') ? esc(c.source) + ' · ' : ''}${esc(c.note)}</small></li>`).join('')}</ul>
          ${r.hours ? `<div class="as-q"><b>Öffnungszeiten:</b> ${esc(r.hours.text)} <span class="sw-web ${r.hours.open_now ? 'ok' : r.hours.open_now === false ? 'off' : 'wait'}">${esc(r.hours.label)}</span> <small>${esc(r.hours.source)}</small></div>` : ''}
          ${r.next_slot && r.attempts_open ? `<div class="as-q"><b>Nächster Versuch:</b> ${esc(r.next_slot.label)} <small>(${esc(r.next_slot.why)})</small></div>` : ''}
          <small class="muted">${esc(r.notice)}</small></section>
      </div></div>`;
  };

  // Verlustgrund: Phase „verloren“ nur mit Grund. Gibt {lost_reason, lost_note} oder null (abgebrochen) zurück.
  window.askLostReason = function (company) {
    return new Promise(resolve => {
      const dlg = $('#lostDialog'), form = $('#lostForm');
      if (!dlg || typeof dlg.showModal !== 'function') {
        const note = prompt(`Woran lag es bei ${company}? (kurze Notiz)`);
        return resolve(note && note.trim() ? {lost_reason: 'sonstiges', lost_note: note.trim()} : null);
      }
      form.reset();
      $('#lostCompany').textContent = company;
      let done = false;
      const finish = v => { if (done) return; done = true; form.removeEventListener('submit', onSubmit); dlg.removeEventListener('close', onClose); if (dlg.open) dlg.close(); resolve(v); };
      const onSubmit = e => {
        e.preventDefault();
        const reason = form.elements.lost_reason.value, note = form.elements.lost_note.value.trim();
        if (reason === 'sonstiges' && !note) { form.elements.lost_note.focus(); return toast('Bei „Sonstiges“ bitte kurz notieren, woran es lag.', true); }
        finish({lost_reason: reason, lost_note: note});
      };
      const onClose = () => finish(null);
      form.addEventListener('submit', onSubmit);
      dlg.addEventListener('close', onClose);
      dlg.showModal();
    });
  };

  // Ergänzt eine Phasenänderung um den Verlustgrund. Gibt null zurück, wenn der Nutzer abbricht.
  window.withLostReason = async function (lead, data) {
    if (data.stage !== 'verloren' || (lead && lead.stage === 'verloren')) return data;
    const r = await window.askLostReason(lead ? lead.company : 'dieser Firma');
    return r ? {...data, ...r} : null;
  };

  window.leadGradeChip = id => (id in grades ? gradeChip(grades[id].grade) : '');
  const RANK = {A: 0, B: 1, C: 3, X: 4};
  // Reihenfolge für Listen: A, B, unbekannt, C, Ausschluss
  window.leadGradeRank = id => (id in grades ? (RANK[grades[id].grade] ?? 2) : 2);

  async function loadGrades() {
    try {
      meta = await api('/assessment');
      grades = Object.fromEntries(meta.leads.map(l => [l.lead_id, l]));
    } catch (_) { grades = {}; }
    const hint = $('#asProfileHint');
    if (hint && meta) hint.classList.toggle('hidden', meta.profile_complete);
    renderStats();
  }

  function renderStats() {
    const box = $('#asStats');
    if (!box || !meta) return;
    const lost = meta.lost_reasons, s = meta.slot_stats;
    box.innerHTML = `<div><b>Verlustgründe</b>${lost.length ? `<ul>${lost.map(l => `<li>${esc(l.label)}: ${l.count}</li>`).join('')}</ul>` : '<small class="muted">Noch keine verlorenen Chancen.</small>'}</div>
      <div><b>Erreicht nach Tageszeit</b>${s.enough ? `<ul>${s.slots.map(x => `<li>${esc(x.label)}: ${x.rate_pct === null ? '–' : x.rate_pct + ' %'} (${x.reached} von ${x.calls})</li>`).join('')}</ul>` : ''}<small class="muted">${esc(s.notice)}</small></div>`;
  }

  async function loadProfile() {
    const form = $('#targetProfileForm');
    if (!form) return;
    const r = await api('/profile/target'), p = r.profile;
    for (const k of ['name', 'home', 'employees_min', 'employees_max', 'radius_km', 'min_order_eur', 'weekly_hours', 'max_attempts', 'retry_days', 'park_days']) form.elements[k].value = p[k];
    form.elements.prefer_owner_led.checked = p.prefer_owner_led;
    $('#targetIndustries').innerHTML = r.industries.map(g => `<fieldset class="tp-group"><legend>${esc(g.group)}</legend>${g.items.map(i => `<div class="tp-row"><span>${esc(i.label)}</span>
      <select data-tp="${esc(i.key)}" aria-label="${esc(i.label)}"><option value="">–</option><option value="ziel" ${p.industries.includes(i.key) ? 'selected' : ''}>Zielbranche</option><option value="aus" ${p.excluded_industries.includes(i.key) ? 'selected' : ''}>nicht bedienen</option></select></div>`).join('')}</fieldset>`).join('');
    const lost = $('#lostForm [name=lost_reason]');
    if (lost && !lost.options.length) lost.innerHTML = Object.entries(r.lost_reasons).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
  }

  async function saveProfile(e) {
    e.preventDefault();
    const f = e.target.elements, sel = [...document.querySelectorAll('#targetIndustries [data-tp]')];
    const num = k => Number(f[k].value);
    const body = {name: f.name.value.trim(), home: f.home.value.trim(), prefer_owner_led: f.prefer_owner_led.checked,
      industries: sel.filter(s => s.value === 'ziel').map(s => s.dataset.tp), excluded_industries: sel.filter(s => s.value === 'aus').map(s => s.dataset.tp)};
    for (const k of ['employees_min', 'employees_max', 'radius_km', 'min_order_eur', 'weekly_hours', 'max_attempts', 'retry_days', 'park_days']) body[k] = num(k);
    try {
      await api('/profile/target', 'POST', body);
      toast('Zielkundenprofil gespeichert – die Bewertung aller Firmen ist neu berechnet');
      await loadGrades();
      if (typeof renderLeads === 'function') renderLeads();
    } catch (err) { toast(err.message, true); }
  }

  function openProfile() {
    if (typeof closeModal === 'function') closeModal();
    switchView('quality');
    setTimeout(() => $('#targetProfile')?.scrollIntoView({behavior: 'smooth'}), 50);
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#targetProfileForm')?.addEventListener('submit', saveProfile);
    $('#lostCancel')?.addEventListener('click', () => $('#lostDialog').close());
    document.body.addEventListener('click', e => { if (e.target.closest('[data-as-profile]')) openProfile(); });
    const orig = window.reload;
    if (typeof orig === 'function') window.reload = async function (...args) { const r = await orig.apply(this, args); await loadGrades(); if (typeof renderLeads === 'function') renderLeads(); if (typeof window.renderPipeline === 'function') window.renderPipeline(); return r; };
    loadProfile().catch(() => {});
    loadGrades().then(() => { if (typeof renderLeads === 'function' && typeof leads !== 'undefined' && leads.length) renderLeads(); });
  });
})();
