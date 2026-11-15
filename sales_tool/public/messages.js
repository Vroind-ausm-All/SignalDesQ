'use strict';
// 2.0.0-dev29 (Roadmap M37): Eigene Nachrichtenvorlagen mit Platzhaltern. Werte nur aus bestätigten Daten, Fehlendes sichtbar,
// Endfassung zum Kopieren erst ohne Lücken. SignalDesk versendet nichts.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  let templates = [], placeholders = {}, last = null;
  const leadId = () => Number($('#wsMailForm [name=lead_id]')?.value) || null;

  async function loadTemplates() {
    const r = await api('/vorlagen');
    templates = r.templates;
    placeholders = r.placeholders;
    $('#msgTemplate').innerHTML = templates.map(t => `<option value="${t.id}">${esc(t.title)}</option>`).join('');
    $('#msgEditPick').innerHTML = '<option value="">Neue Vorlage</option>' + templates.map(t => `<option value="${t.id}">${esc(t.title)}${t.builtin ? ' (mitgeliefert)' : ''}</option>`).join('');
    $('#msgPlaceholders').innerHTML = 'Platzhalter: ' + Object.entries(placeholders).map(([k, v]) => `<code>{{${esc(k)}}}</code> ${esc(v)}`).join(' · ');
  }

  async function loadLeadOptions() {
    const id = leadId();
    $('#msgProposal').innerHTML = '<option value="">– kein Angebot –</option>';
    $('#msgContact').innerHTML = '<option value="">– keine Person (neutrale Anrede) –</option>';
    if (!id) return;
    try {
      const rows = (await api('/workspace/proposals')).filter(p => p.lead_id === id && !p.superseded);
      $('#msgProposal').innerHTML += rows.map(p => `<option value="${p.id}">${esc(p.number)} · ${esc(p.project_label)} (${esc(p.status.replaceAll('_', ' '))})</option>`).join('');
      const d = await api(`/leads/${id}/decision-map`);
      $('#msgContact').innerHTML += d.contacts.map(c => `<option value="${c.id}">${esc(c.full_name)}${c.contact_restrictions.length ? ' – eingeschränkt' : ''}</option>`).join('');
    } catch { /* Auswahl bleibt leer */ }
  }

  function body() {
    const f = $('#msgForm').elements;
    return {lead_id: leadId(), ...(f.proposal_id.value ? {proposal_id: Number(f.proposal_id.value)} : {}), ...(f.contact_id.value ? {contact_id: Number(f.contact_id.value)} : {})};
  }

  const mark = t => esc(t).replace(/\[FEHLT: ([^\]]+)\]/g, '<span class="msg-missing">[FEHLT: $1]</span>');

  async function preview() {
    if (!leadId()) return toast('Bitte oben eine Firma wählen', true);
    try {
      last = await api(`/vorlagen/${$('#msgTemplate').value}/vorschau`, 'POST', body());
      $('#msgPreview').innerHTML = `<b data-msg-subject>${mark(last.subject)}</b><pre data-msg-body>${mark(last.body)}</pre>
        ${last.missing.length ? `<p class="qb-check warn" data-msg-missing>! Es fehlt: ${last.missing.map(esc).join(', ')}</p>` : '<p class="qb-check ok">Alle Platzhalter aus bestätigten Daten gefüllt.</p>'}
        <button type="button" class="btn btn-ghost" id="msgCopy" ${last.complete ? '' : 'disabled'}>Endfassung kopieren</button><p class="muted">${esc(last.notice)}</p>`;
      $('#msgCopy').onclick = () => navigator.clipboard.writeText('Betreff: ' + last.subject + '\n\n' + last.body).then(() => toast('Endfassung kopiert – nicht versendet'));
    } catch (e) { $('#msgPreview').innerHTML = ''; toast(e.message, true); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#msgForm')) return;
    loadTemplates().catch(e => toast(e.message, true));
    $('#wsMailForm [name=lead_id]')?.addEventListener('change', () => { $('#msgPreview').innerHTML = ''; loadLeadOptions(); });
    $('#msgPreviewBtn').addEventListener('click', preview);
    $('#msgSaveBtn').addEventListener('click', async () => {
      const basis = $('#wsMailForm [name=contact_basis]').value.trim();
      if (!basis) return toast('Bitte oben den dokumentierten Anlass eintragen', true);
      try {
        const d = await api('/workspace/mail-drafts', 'POST', {...body(), template_id: Number($('#msgTemplate').value), contact_basis: basis});
        toast(d.notice);
        await preview();
      } catch (e) { toast(e.message, true); }
    });
    $('#msgEditPick').addEventListener('change', e => {
      const t = templates.find(x => String(x.id) === e.target.value), f = $('#msgEditForm').elements;
      f.title.value = t ? t.title : ''; f.subject.value = t ? t.subject : ''; f.body.value = t ? t.body : '';
      $('#msgDelete').hidden = !t || !!t.builtin;
    });
    $('#msgEditForm').addEventListener('submit', async e => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const f = e.target.elements, id = $('#msgEditPick').value;
      try {
        await api(id ? `/vorlagen/${id}` : '/vorlagen', id ? 'PATCH' : 'POST', {title: f.title.value, subject: f.subject.value, body: f.body.value});
        toast('Vorlage gespeichert');
        await loadTemplates();
      } catch (err) { toast(err.message, true); }
    }, true);
    $('#msgDelete').addEventListener('click', async () => {
      const id = $('#msgEditPick').value;
      if (!id) return;
      try { await api(`/vorlagen/${id}`, 'DELETE'); toast('Vorlage gelöscht'); await loadTemplates(); } catch (err) { toast(err.message, true); }
    });
  });
})();
