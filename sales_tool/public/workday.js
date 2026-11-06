'use strict';
// v1.18 (Masterplan 2.0, Sprint 5): Suchprofile mit Budget („Profil auswählen → Session starten“) und Tagesabschluss
// (Erledigtes, Morgen, Sackgassen ohne nächsten Schritt, Sicherung). Nichts wird versendet.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const DONE = {neue_leads: 'neue Leads', gesichtet: 'Treffer gesichtet', berichte: 'Firmen-Berichte', telefonate: 'Telefonate dokumentiert',
    termine_eingetragen: 'Termine eingetragen', bedarf_bestaetigt: 'Bedarfe bestätigt', angebote: 'Angebote erstellt', aufgaben_erledigt: 'Aufgaben erledigt'};
  const STAGE = {qualifiziert: 'Qualifiziert', kontakt: 'Kontakt geprüft', antwort: 'Rückmeldung', termin: 'Termin', angebot: 'Angebot'};
  let profiles = [];
  const plusDays = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

  // ------------------------------------------------------------ Suchprofile
  async function loadProfiles(select) {
    try {
      const r = await api('/search-profiles');
      profiles = r.profiles;
      const sel = $('#swProfile'), cur = select ?? sel.value;
      sel.innerHTML = '<option value="">– ohne Profil –</option>' + profiles.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
      sel.value = profiles.some(p => String(p.id) === String(cur)) ? String(cur) : '';
      showProfile();
    } catch (e) { $('#swProfileInfo').textContent = e.message; }
  }

  function showProfile() {
    const p = profiles.find(x => String(x.id) === $('#swProfile').value);
    $('#swProfileStart').disabled = !p;
    $('#swProfileDel').classList.toggle('hidden', !p);
    $('#swProfileInfo').textContent = p ? `${p.summary} · ${p.costs}${p.runs ? ` · ${p.runs}× gestartet` : ''}` : 'Ein Profil speichert Gebiet, Branchen, Quellen und das Budget je Lauf.';
    if (p && window.swApplyParams) window.swApplyParams(p.params, p.budget);
  }

  // ------------------------------------------------------------ Tagesabschluss
  async function loadClose() {
    const box = $('#tdCloseBody');
    if (!box) return;
    try {
      const s = await api('/today/close');
      $('#tdCloseState').textContent = s.closed ? `abgeschlossen ${s.closed.closed_at.slice(11, 16)} Uhr (UTC)` : '';
      const done = Object.entries(s.done).filter(([, n]) => n).map(([k, n]) => `<span class="td-chip"><b>${n}</b> ${esc(DONE[k] || k)}</span>`).join('') || '<span class="muted">Heute noch nichts dokumentiert.</span>';
      box.innerHTML = `<div class="td-close-done">${done}</div>
        <div class="td-close-cols"><div><b>Morgen</b><small>${s.open.morgen_faellig} Aufgabe(n) fällig · ${s.meetings_tomorrow.length} Termin(e)${s.open.ueberfaellig ? ` · <span class="late">${s.open.ueberfaellig} überfällig</span>` : ''} · ${s.open.angebotsentwuerfe} Angebotsentwurf/-entwürfe</small>
          ${s.meetings_tomorrow.map(m => `<small>◷ ${esc(m.starts_at.slice(11, 16))} ${esc(m.company)} – ${esc(m.title)}</small>`).join('')}</div>
          <div><b>Sicherung</b><small>${s.backup_today ? '✓ heute gesichert' : s.last_backup ? 'letzte Sicherung ' + esc(s.last_backup.replace('T', ' ').slice(0, 16)) : 'noch keine Sicherung'}</small></div></div>
        ${s.dead_ends.length ? `<div class="td-dead"><b>⚠ ${s.dead_ends.length}${s.dead_ends_capped ? '+' : ''} Firma(en) ohne nächsten Schritt mit Datum</b><small>Sonst bleiben sie liegen – Wiedervorlage setzen:</small>
          ${s.dead_ends.map(d => `<div class="td-dead-row" data-dead="${d.lead_id}"><span><button type="button" class="text-button" data-lead="${d.lead_id}">${esc(d.company)}</button> <small>${esc(STAGE[d.stage] || d.stage)}</small></span>
            <input type="text" value="${esc(d.next_step || 'Wiedervorlage')}" maxlength="300" aria-label="Nächster Schritt für ${esc(d.company)}" data-dead-step>
            <input type="date" value="${plusDays(1)}" aria-label="Datum für ${esc(d.company)}" data-dead-date></div>`).join('')}</div>` : '<div class="td-dead ok">✓ Jede offene Firma hat einen nächsten Schritt mit Datum.</div>'}
        <div class="td-close-actions"><label><input type="checkbox" id="tdCloseBackup" ${s.backup_today ? '' : 'checked'}> Datensicherung erstellen</label>
          <input type="text" id="tdCloseNote" maxlength="1000" placeholder="Notiz zum Tag (optional)" value="${esc(s.closed?.note || '')}">
          <button type="button" class="btn btn-primary" id="tdCloseBtn">Tag abschließen</button></div>`;
    } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }
  window.refreshDayClose = loadClose;

  function init() {
    if ($('#swProfile')) {
      $('#swProfile').addEventListener('change', showProfile);
      $('#swProfileSave').addEventListener('click', async () => {
        const params = window.swFormParams ? window.swFormParams() : null;
        if (!params) return;
        const cur = profiles.find(x => String(x.id) === $('#swProfile').value);
        const name = prompt('Name des Suchprofils', cur ? cur.name : `${params.place || 'Gebiet'} · ${params.radius_km} km`);
        if (!name) return;
        const {budget, ...rest} = params;
        try {
          const p = cur && cur.name === name ? await api(`/search-profiles/${cur.id}`, 'PUT', {name, params: rest, budget})
            : await api('/search-profiles', 'POST', {name, params: rest, budget});
          toast(`Profil „${p.name}“ gespeichert`);
          loadProfiles(p.id);
        } catch (e) { toast(e.message, true); }
      });
      $('#swProfileDel').addEventListener('click', async () => {
        const p = profiles.find(x => String(x.id) === $('#swProfile').value);
        if (!p || !confirm(`Profil „${p.name}“ löschen? Bisherige Suchläufe bleiben erhalten.`)) return;
        try { await api(`/search-profiles/${p.id}`, 'DELETE'); loadProfiles(''); } catch (e) { toast(e.message, true); }
      });
      $('#swProfileStart').addEventListener('click', async () => {
        const p = profiles.find(x => String(x.id) === $('#swProfile').value);
        if (!p) return;
        try {
          const sw = await api(`/search-profiles/${p.id}/start`, 'POST', {});
          toast(`Profil „${p.name}“ gestartet – Budget ${p.budget.max_companies} Firmen / ${p.budget.max_minutes} Min.`);
          if (window.swWatch) window.swWatch(sw.id);
          if (window.refreshJobs) window.refreshJobs();
          loadProfiles(p.id);
        } catch (e) { toast(e.message, true); }
      });
      const orig = window.refreshSweep;
      window.refreshSweep = async function () { const r = orig ? await orig() : null; loadProfiles(); return r; };
    }
    if ($('#tdCloseBody')) {
      const origToday = window.refreshToday;
      window.refreshToday = async function () { const r = origToday ? await origToday() : null; loadClose(); return r; };
      $('#tdCloseBody').addEventListener('click', async e => {
        if (!e.target.closest('#tdCloseBtn')) return;
        const followups = $$('#tdCloseBody [data-dead]').map(r => ({lead_id: Number(r.dataset.dead), step: r.querySelector('[data-dead-step]').value.trim() || 'Wiedervorlage',
          date: r.querySelector('[data-dead-date]').value})).filter(f => f.date);
        try {
          const r = await api('/today/close', 'POST', {note: $('#tdCloseNote').value.trim(), backup: $('#tdCloseBackup').checked, followups});
          toast(`Tag abgeschlossen${followups.length ? ` · ${followups.length} Wiedervorlage(n) gesetzt` : ''}${r.backup_path ? ' · Sicherung erstellt' : ''}`);
          if (typeof reload === 'function') reload();
          loadClose();
        } catch (err) { toast(err.message, true); }
      });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
