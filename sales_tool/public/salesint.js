'use strict';
// v1.7 Sales-Integration: Angebots-Matching aus bestätigten Kundenaussagen, Entscheider v3 (Rollen,
// Befugnisse, Kontaktbeschränkungen) und Sales Action Center (Aufgabenvorschläge, Freigabe je Kontaktaktion).
// Es wird nichts automatisch versendet oder ausgeführt.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const ROLE_STATE = {unbekannt: 'unbekannt', vermutet: 'vermutet', bestaetigt: 'bestätigt'};
  const ROLE_LABEL = {fachlich: 'Fachlich zuständig', budget: 'Budgetverantwortung', entscheidung: 'Finale Entscheidung'};
  const VERIFY = {ungeprueft: 'ungeprüft', quelle_geprueft: 'Quelle geprüft', rolle_bestaetigt: 'Rolle bestätigt', veraltet: 'veraltet', verworfen: 'verworfen'};
  const CHANNEL = {email: 'E-Mail', telefon: 'Telefon', brief: 'Brief', persoenlich: 'Persönlich'};
  const PERM = {zu_pruefen: 'Freigabe offen', freigegeben: 'freigegeben', abgelehnt: 'abgelehnt'};
  let leadId = null, restrictionLabels = {};

  // ------------------------------------------------------------ Angebots-Matching
  function recCard(r) {
    const basis = r.status === 'angebotsgrundlage';
    const confirmed = r.confirmed.length ? `<div><b>Bestätigt im Gespräch</b><ul>${r.confirmed.map(c => `<li><small>${esc(c.field)}:</small> „${esc(c.quote)}“</li>`).join('')}</ul></div>` : '';
    const hints = r.hints.length ? `<div><b>Hinweise aus der Recherche (nicht bestätigt)</b><ul>${r.hints.map(h => `<li><small>${esc(h.source)}:</small> ${esc(h.text)}</li>`).join('')}</ul></div>` : '';
    const notes = r.notes.length ? `<p class="muted">${r.notes.map(esc).join(' ')}</p>` : '';
    return `<article class="si-rec ${basis ? 'si-basis' : ''}">
      <div class="dc-item-head"><div><b>${esc(r.rank)}. ${esc(r.title)}</b><small>ab ${euros(r.minimum_eur)} netto · Festpreis nach Kalkulation</small></div>
        <span class="si-status ${esc(r.status)}">${basis ? 'Angebotsgrundlage' : 'unverbindlich'}</span></div>
      <div class="sg-two">${confirmed}${hints}</div>${notes}
      ${basis ? `<div class="form-actions"><button type="button" class="btn btn-primary" data-si-quote="${r.id}">Als Angebotsgrundlage verwenden →</button></div>` : ''}
    </article>`;
  }

  function renderMatching(d) {
    const st = d.discovery || {};
    $('#siMatchNotice').textContent = d.notice || (st.complete ? 'Bedarfsklärung dokumentiert.' : `Bedarfsklärung unvollständig (${st.answered || 0}/${st.total || 5} beantwortet) – Empfehlungen sind unverbindlich.`);
    $('#siMatchList').innerHTML = d.recommendations.length ? d.recommendations.map(recCard).join('')
      : '<div class="empty">Noch keine passenden Pakete – Bedarfsanalyse ausfüllen oder Signale verknüpfen, dann abgleichen.</div>';
  }

  async function computeMatching() {
    if (!leadId) return;
    try { renderMatching(await api(`/leads/${leadId}/offer-matching`, 'POST', {})); loadSuggestions(); }
    catch (e) { toast(e.message, true); }
  }

  async function useAsQuote(recId) {
    try {
      const d = await api(`/offer-recommendations/${recId}/quote-draft`);
      if (typeof closeModal === 'function') closeModal();
      switchView('quotes');
      if (window.refreshSalesQuotes) await window.refreshSalesQuotes();
      const f = $('#quoteForm');
      f.elements.lead_id.value = String(d.lead_id);
      f.elements.lead_id.dispatchEvent(new Event('change'));
      $('#quotePackage').value = d.package;
      f.elements.project_label.value = d.project_label;
      f.elements.customer_goal.value = d.customer_goal;
      f.elements.assumptions.value = d.assumptions;
      if (window.quoteApplyTemplate) window.quoteApplyTemplate(d.package, d.positions);
      toast(d.notice);
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Entscheider v3
  function roleSelect(c, key) {
    return `<label>${esc(ROLE_LABEL[key])}<select data-si-role="${key}">${Object.entries(ROLE_STATE).map(([k, v]) => `<option value="${k}" ${c.roles[key] === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label>`;
  }

  function contactCard(c) {
    const restr = Object.entries(restrictionLabels).map(([k, v]) => `<label class="si-check"><input type="checkbox" data-si-restr="${k}" ${c.contact_restrictions.includes(k) ? 'checked' : ''}> ${esc(v)}</label>`).join('');
    return `<form class="si-contact" data-si-contact="${c.id}">
      <div class="dc-item-head"><div><b>${esc(c.full_name)}</b><small>${esc(c.job_title || 'Funktion unbekannt')} · Prüfstatus: ${esc(VERIFY[c.verification_status] || c.verification_status || 'ungeprüft')}${c.source_url ? ` · <a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">Quelle</a>` : ''}</small></div>
        ${c.contact_restrictions.length ? `<span class="si-status gesperrt">${c.contact_restrictions.map(k => esc(restrictionLabels[k] || k)).join(' · ')}</span>` : ''}</div>
      <div class="si-roles">${['fachlich', 'budget', 'entscheidung'].map(k => roleSelect(c, k)).join('')}</div>
      <div class="si-restr"><b>Kontaktbeschränkungen</b>${restr}</div>
      <details class="si-more" ${c.business_channel || c.restriction_note ? 'open' : ''}><summary>Geschäftlicher Kontaktweg & Notiz</summary><div class="field-grid">
        <label>Veröffentlichter geschäftlicher Kontaktweg<input name="business_channel" maxlength="200" value="${esc(c.business_channel)}" placeholder="persönliche Geschäftsadresse oder Durchwahl"></label>
        <label>Art<select name="business_channel_kind"><option value="">–</option><option value="email" ${c.business_channel_kind === 'email' ? 'selected' : ''}>E-Mail</option><option value="telefon" ${c.business_channel_kind === 'telefon' ? 'selected' : ''}>Telefon</option></select></label>
        <label class="field-wide">Fundstelle (HTTPS)<input name="business_channel_source" type="url" maxlength="500" value="${esc(c.business_channel_source)}" placeholder="https://firma.de/team"></label>
        <label class="field-wide">Notiz zur Beschränkung<input name="restriction_note" maxlength="500" value="${esc(c.restriction_note)}" placeholder="z. B. bat am 04.11. um Kontakt nur über Assistenz"></label>
      </div></details>
      <div class="form-actions"><button type="submit" class="btn btn-ghost">Rollen & Beschränkungen speichern</button></div>
    </form>`;
  }

  function renderDecisionMap(d) {
    restrictionLabels = d.restriction_labels;
    const roles = d.roles.map(r => `<div class="si-role ${r.gap ? 'gap' : ''}"><b>${esc(r.role)}</b><small>Thema: ${esc(r.topic_label || r.topic)}</small>
      <span>${r.persons.length ? r.persons.map(p => `${esc(p.name)}${p.verified ? ' ✓' : ' (ungeprüft)'}`).join(', ') : 'noch niemand erfasst'}</span></div>`).join('');
    $('#siRoleMap').innerHTML = `<p class="muted">${esc(d.note)}</p><div class="si-rolegrid">${roles}</div>`;
    $('#siContacts').innerHTML = d.contacts.length ? d.contacts.map(contactCard).join('')
      : '<div class="empty">Noch keine Ansprechpartner erfasst – oben recherchieren oder manuell anlegen.</div>';
  }

  async function loadDecisionMap() {
    if (!leadId) return;
    try { renderDecisionMap(await api(`/leads/${leadId}/decision-map`)); }
    catch (e) { $('#siRoleMap').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  async function saveContact(form) {
    const body = {contact_restrictions: [...form.querySelectorAll('[data-si-restr]:checked')].map(x => x.dataset.siRestr)};
    form.querySelectorAll('[data-si-role]').forEach(s => { body['role_' + s.dataset.siRole] = s.value; });
    for (const k of ['business_channel', 'business_channel_kind', 'business_channel_source', 'restriction_note']) body[k] = form.elements[k].value;
    if (body.contact_restrictions.includes('widerspruch') && !confirm('Widerspruch eintragen? Offene Kontaktaktionen zu dieser Person werden abgelehnt, eine bekannte E-Mail kommt auf die Sperrliste.')) return;
    try { await api(`/contacts/${form.dataset.siContact}/roles`, 'PATCH', body); toast('Gespeichert'); loadDecisionMap(); loadSuggestions(); }
    catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Aufgabenvorschläge
  function suggestionItem(a, withCompany) {
    return `<div class="sales-item si-suggest"><div><strong>${esc(a.title)}${a.requires_permission ? ' <span class="si-perm zu_pruefen">Kontaktaktion · Freigabe nötig</span>' : ''}</strong>
      <small>${withCompany ? esc(a.company) + ' · ' : ''}${esc(a.reason)}</small></div>
      <div class="acc-btn-group"><button type="button" class="btn btn-primary" data-si-accept="${a.lead_id}" data-key="${esc(a.key)}">Übernehmen</button><button type="button" class="btn btn-ghost" data-si-dismiss="${a.lead_id}" data-key="${esc(a.key)}">Verwerfen</button></div></div>`;
  }

  async function loadSuggestions() {
    if (!leadId || !$('#siSuggestions')) return;
    try {
      const list = await api(`/leads/${leadId}/action-suggestions`);
      $('#siSuggestions').innerHTML = list.length ? list.map(a => suggestionItem(a, false)).join('') : '<div class="empty">Keine offenen Vorschläge.</div>';
    } catch (e) { $('#siSuggestions').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  async function act(btn, accept) {
    const body = {lead_id: Number(accept ? btn.dataset.siAccept : btn.dataset.siDismiss), key: btn.dataset.key};
    try {
      const r = await api(`/action-suggestions/${accept ? 'accept' : 'dismiss'}`, 'POST', body);
      toast(accept ? (r.requires_permission ? 'Aufgabe angelegt – Kontaktaktion erst nach Freigabe ausführen' : 'Aufgabe angelegt') : 'Vorschlag verworfen');
      if (typeof reload === 'function') await reload();
      loadSuggestions();
      window.refreshActionCenter();
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Sales-Tag: Freigaben
  function permissionItem(t) {
    const form = t.permission_status === 'zu_pruefen' ? `<form class="si-permform" data-si-perm="${t.id}">
        <label>Kanal<select name="channel">${Object.entries(CHANNEL).map(([k, v]) => `<option value="${k}" ${t.channel === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>Rechtsgrundlage / Dokumentation<input name="basis" maxlength="500" required minlength="15" placeholder="z. B. Opt-in per Formular am 03.11.2026, Umfang: Projektinfos"></label>
        <div class="acc-btn-group"><button type="submit" class="btn btn-primary">Freigeben</button><button type="button" class="btn btn-ghost" data-si-reject="${t.id}">Ablehnen</button></div>
      </form>` : `<small>${esc(t.permission_basis || '')}</small>`;
    return `<div class="sales-item si-permitem"><div><strong>${esc(t.title)} <span class="si-perm ${esc(t.permission_status)}">${esc(PERM[t.permission_status] || t.permission_status)}${t.channel ? ' · ' + esc(CHANNEL[t.channel] || t.channel) : ''}</span></strong>
      <small>${esc(t.company || 'Allgemein')} · fällig ${esc(fmtDate(t.due_date))}</small>${form}</div></div>`;
  }

  window.refreshActionCenter = async function () {
    if (!$('#siDaySuggestions')) return;
    try {
      const [sugg, all] = await Promise.all([api('/action-suggestions'), api('/tasks')]);
      $('#siDaySuggestions').innerHTML = sugg.length ? sugg.map(a => suggestionItem(a, true)).join('') : '<div class="empty">Keine offenen Vorschläge.</div>';
      const perms = all.filter(t => !t.done && t.permission_status && t.permission_status !== 'nicht_erforderlich');
      $('#siPermissions').innerHTML = perms.length ? perms.map(permissionItem).join('') : '<div class="empty">Keine Kontaktaktionen geplant.</div>';
    } catch (e) { toast(e.message, true); }
  };

  async function decide(taskId, body) {
    try {
      const r = await api(`/tasks/${taskId}/permission`, 'POST', body);
      toast(r.notice || (r.permission_status === 'abgelehnt' ? 'Kontaktaktion abgelehnt' : 'Freigegeben'));
      if (typeof reload === 'function') await reload();
      window.refreshActionCenter();
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Lead-Dialog
  window.loadSalesIntegration = async function (id) {
    leadId = id;
    if (!id) return;
    try { renderMatching(await api(`/leads/${id}/offer-matching`)); } catch (e) { $('#siMatchNotice').textContent = e.message; }
    await Promise.all([loadDecisionMap(), loadSuggestions()]);
  };

  function init() {
    if (!$('#siMatchBtn')) return;
    $('#siMatchBtn').addEventListener('click', computeMatching);
    $('#siDayRefresh').addEventListener('click', () => window.refreshActionCenter());
    // Nach dem Speichern der Bedarfsanalyse neu abgleichen (der Speicher-Handler aus app.js läuft zuerst).
    $('#discoveryForm').addEventListener('submit', () => setTimeout(() => { if (leadId) computeMatching(); }, 500));
    document.body.addEventListener('click', e => {
      const q = e.target.closest('[data-si-quote]'); if (q) return useAsQuote(q.dataset.siQuote);
      const a = e.target.closest('[data-si-accept]'); if (a) return act(a, true);
      const d = e.target.closest('[data-si-dismiss]'); if (d) return act(d, false);
      const r = e.target.closest('[data-si-reject]');
      if (r) { const basis = prompt('Grund für die Ablehnung (optional):') ?? ''; return decide(r.dataset.siReject, {decision: 'ablehnen', basis}); }
    });
    document.body.addEventListener('submit', e => {
      const c = e.target.closest('[data-si-contact]');
      if (c) { e.preventDefault(); return saveContact(c); }
      const p = e.target.closest('[data-si-perm]');
      if (p) { e.preventDefault(); return decide(p.dataset.siPerm, {decision: 'freigeben', channel: p.elements.channel.value, basis: p.elements.basis.value}); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
