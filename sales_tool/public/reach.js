'use strict';
// 2.0.0-dev3: eigene Erreichbarkeit – Eingang mit Rückruffrist, „als Nächstes kontaktieren“, Auslastung, eigene Zeiten,
// Terminvorschläge und Textbausteine. Nichts wird versendet; Texte werden nur zum Kopieren angezeigt.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const when = s => s ? `${fmtDate(s.slice(0, 10))} ${s.slice(11, 16)}` : '';
  const LEVEL = {frei: 'wait', luft: 'ok', gut: 'mid', voll: 'bad'};
  let weekdays = [];

  function renderInbound(v, window_) {
    $('#rcInCount').textContent = v.open.length ? `${v.open.length} offen${v.overdue ? `, ${v.overdue} überfällig` : ''}` : `Rückrufzeit ${window_}`;
    $('#rcInList').innerHTML = v.open.length ? v.open.map(i => `<div class="td-item rc-item ${i.overdue ? 'overdue' : ''}">
      <div><b>${esc(i.who)}</b>${i.company && i.company !== i.who ? ` <small>· ${esc(i.company)}</small>` : ''}
        <small>${esc(i.channel_label)} · ${esc(when(i.received_at))}${i.contact ? ' · ' + esc(i.contact) : ''}${i.note ? ' · ' + esc(i.note) : ''}</small>
        <small class="${i.overdue ? 'rc-late' : ''}">Rückruf bis ${esc(when(i.due_at))}${i.overdue ? ' – überfällig' : ''}</small></div>
      <span class="acc-btn-group">${i.lead_id ? `<button type="button" class="text-button" data-go-action='${esc(JSON.stringify({view: 'lead', lead_id: i.lead_id}))}'>Akte</button>` : ''}
        <button type="button" class="btn btn-primary" data-rc-done="${i.id}">Erledigt</button><button type="button" class="text-button" data-rc-del="${i.id}" aria-label="Eintrag löschen">✕</button></span></div>`).join('')
      : '<div class="empty">Kein offener Rückruf. Verpasste Anrufe und Anfragen hier sofort festhalten.</div>';
    const s = v.stats;
    $('#rcInStats').textContent = s.done ? `Letzte ${s.done} Rückmeldungen: im Mittel nach ${String(s.median_hours).replace('.', ',')} Stunden, ${s.in_time_pct} % innerhalb der Frist.` : '';
  }

  function renderList(c) {
    $('#rcListCount').textContent = c.total ? `${c.items.length} von ${c.total} · jetzt: ${c.slot_now}` : '';
    $('#rcList').innerHTML = c.items.length ? c.items.map(i => `<div class="td-item rc-item">
      <div>${window.leadGradeChip ? window.leadGradeChip(i.lead_id) : ''}<b>${esc(i.company)}</b>${i.fits_now ? ' <span class="sw-web ok">jetzt passendes Zeitfenster</span>' : ''}${i.open_now === true ? ' <span class="sw-web ok">jetzt geöffnet</span>' : i.open_now === false ? ' <span class="sw-web off">jetzt geschlossen</span>' : ''}
        <small>${esc(i.hint)}</small></div>
      <button type="button" class="text-button" data-go-action='${esc(JSON.stringify({view: 'lead', lead_id: i.lead_id}))}'>Akte öffnen</button></div>`).join('')
      : '<div class="empty">Keine Firma mit Passung A oder B in den Phasen Qualifiziert bis Rückmeldung. Zielkundenprofil einstellen und Firmen-Berichte erstellen.</div>';
    $('#rcListNote').textContent = c.notice;
  }

  function renderCapacity(c, absentToday) {
    $('#rcCap').innerHTML = `<span class="sw-web ${LEVEL[c.level]}">Auslastung</span> <b>${esc(c.hint)}</b>
      <small>Zugesagt ${c.accepted_hours} h · angeboten ${c.offered_hours} h in ${c.offers_open} Angebot(en) · ${c.delivery_hours_per_week} h je Woche für Kundenprojekte. ${esc(c.notice)}</small>
      ${absentToday ? `<small class="rc-late">Heute als abwesend eingetragen${absentToday.note ? ': ' + esc(absentToday.note) : ''}.</small>` : ''}`;
  }

  async function refresh() {
    if (!$('#rcInList')) return;
    try {
      const r = await api('/reach/today');
      renderInbound(r.inbound, r.callback_window);
      renderList(r.contact_list);
      renderCapacity(r.capacity, r.absent_today);
      const sel = $('#rcInForm [name=channel]');
      if (!sel.options.length) sel.innerHTML = Object.entries(r.inbound.channels).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
      const ls = $('#rcInForm [name=lead_id]');
      if (typeof leads !== 'undefined') ls.innerHTML = '<option value="">– keine bekannte Firma –</option>' + leads.map(l => `<option value="${l.id}">${esc(l.company)}</option>`).join('');
    } catch (e) { $('#rcInList').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }
  window.refreshReach = refresh;

  function absenceRow(a = {}) {
    return `<div class="rc-abs"><input type="date" data-abs="from" value="${esc(a.from || '')}" aria-label="Abwesend von"><input type="date" data-abs="to" value="${esc(a.to || '')}" aria-label="Abwesend bis">
      <input data-abs="note" maxlength="120" placeholder="Notiz, z. B. Urlaub" value="${esc(a.note || '')}" aria-label="Notiz"><button type="button" class="text-button" data-abs-del aria-label="Abwesenheit entfernen">✕</button></div>`;
  }

  function renderHelpers(r) {
    $('#avSlots').textContent = r.slots.text || 'In den nächsten drei Wochen ist kein freier Termin in deinen Zeiten.';
    $('#avTemplates').innerHTML = r.templates.map(t => `<div class="rc-tpl"><b>${esc(t.title)}</b><pre>${esc(t.text)}</pre><button type="button" class="text-button" data-copy="${esc(t.text)}">Kopieren</button></div>`).join('');
  }

  async function loadAvailability() {
    const form = $('#availabilityForm');
    if (!form) return;
    const r = await api('/availability'), a = r.availability;
    weekdays = r.weekdays;
    $('#avDays').innerHTML = weekdays.map((d, i) => `<label class="rc-day"><input type="checkbox" data-day="${i}" ${a.days.includes(i) ? 'checked' : ''}> ${esc(d)}</label>`).join('');
    for (const k of ['callback_from', 'callback_to', 'meeting_from', 'meeting_to', 'meeting_minutes', 'delivery_share_pct', 'display_name', 'inbound_keep_days']) form.elements[k].value = a[k];
    $('#avAbsences').innerHTML = a.absences.map(absenceRow).join('');
    renderHelpers(r);
  }

  async function saveAvailability(e) {
    e.preventDefault();
    const f = e.target.elements;
    const body = {days: [...document.querySelectorAll('#avDays [data-day]')].filter(c => c.checked).map(c => Number(c.dataset.day)),
      callback_from: f.callback_from.value, callback_to: f.callback_to.value, meeting_from: f.meeting_from.value, meeting_to: f.meeting_to.value,
      meeting_minutes: Number(f.meeting_minutes.value), delivery_share_pct: Number(f.delivery_share_pct.value), display_name: f.display_name.value.trim(), inbound_keep_days: Number(f.inbound_keep_days.value),
      absences: [...document.querySelectorAll('#avAbsences .rc-abs')].map(r => ({from: r.querySelector('[data-abs=from]').value, to: r.querySelector('[data-abs=to]').value, note: r.querySelector('[data-abs=note]').value.trim()})).filter(a => a.from || a.to)};
    try { renderHelpers(await api('/availability', 'POST', body)); toast('Deine Zeiten sind gespeichert'); await refresh(); }
    catch (err) { toast(err.message, true); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#availabilityForm')?.addEventListener('submit', saveAvailability);
    $('#avAddAbsence')?.addEventListener('click', () => $('#avAbsences').insertAdjacentHTML('beforeend', absenceRow()));
    $('#rcInForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target.elements;
      const body = {who: f.who.value.trim(), channel: f.channel.value, contact: f.contact.value.trim(), note: f.note.value.trim()};
      if (f.lead_id.value) body.lead_id = Number(f.lead_id.value);
      try {
        const r = await api('/inbound', 'POST', body);
        e.target.reset();
        toast(r.warning || `Festgehalten – Rückruf bis ${when(r.due_at)}`, Boolean(r.warning));
        await refresh();
      } catch (err) { toast(err.message, true); }
    });
    document.body.addEventListener('click', async e => {
      const done = e.target.closest('[data-rc-done]'), del = e.target.closest('[data-rc-del]'), copy = e.target.closest('[data-copy]');
      try {
        if (done) { const r = await api(`/inbound/${done.dataset.rcDone}/done`, 'POST', {result: ''}); toast(r.in_time ? 'Erledigt – innerhalb der Frist' : 'Erledigt'); await refresh(); }
        if (del && confirm('Eintrag löschen?')) { await api(`/inbound/${del.dataset.rcDel}`, 'DELETE'); await refresh(); }
        if (copy) { await navigator.clipboard.writeText(copy.dataset.copy); toast('In die Zwischenablage kopiert'); }
        if (e.target.closest('#avCopySlots')) { await navigator.clipboard.writeText($('#avSlots').textContent); toast('Terminvorschläge kopiert'); }
        if (e.target.closest('[data-abs-del]')) e.target.closest('.rc-abs').remove();
      } catch (err) { toast(err.message, true); }
    });
    const orig = window.reload;
    if (typeof orig === 'function') window.reload = async function (...args) { const r = await orig.apply(this, args); await refresh(); return r; };
    loadAvailability().catch(() => {});
    refresh();
  });
})();
