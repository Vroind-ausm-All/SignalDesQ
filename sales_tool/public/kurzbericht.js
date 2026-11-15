'use strict';
// 2.0.0-dev30 (Roadmap M25): Kundenfähiger Kurzbericht aus ausgewählten, geprüften Befunden. Keine internen Werte, kein Versand.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));

  async function loadItems() {
    const id = Number($('#krLead').value), box = $('#krItems');
    $('#krPreview').innerHTML = '';
    if (!id) { box.innerHTML = ''; return; }
    try {
      const r = await api(`/leads/${id}/kurzbericht`);
      box.innerHTML = (r.items.length ? r.items.map(i => `<label class="quote-addon"><input type="checkbox" data-kr-item="${esc(i.id)}"><span><b>${esc(i.title)}</b>${i.area ? ` <small>${esc(i.area)}</small>` : ''}<small>${esc(i.observation)}</small></span></label>`).join('')
        : '<div class="empty">Noch kein geprüfter Befund. Befunde zuerst in der Bewertung bestätigen bzw. in der Recherche freigeben.</div>')
        + (r.not_selectable ? `<p class="muted" data-kr-hidden>${r.not_selectable} ungeprüfte oder verworfene Befunde sind nicht wählbar.</p>` : '');
    } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  async function fillLeads() {
    const sel = $('#krLead'), current = sel.value;
    try {
      const list = await api('/leads');
      const rows = Array.isArray(list) ? list : (list.leads || list.items || []);
      sel.innerHTML = '<option value="">Firma auswählen</option>' + rows.map(l => `<option value="${l.id}">${esc(l.company)}</option>`).join('');
      if (current && rows.some(l => String(l.id) === current)) sel.value = current;
    } catch { /* Auswahl bleibt leer */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#krForm')) return;
    fillLeads();
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'scoring') fillLeads(); });
    $('#krLead').addEventListener('change', loadItems);
    $('#krForm').addEventListener('submit', async e => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const items = [...document.querySelectorAll('[data-kr-item]:checked')].map(x => x.dataset.krItem);
      try {
        const r = await api(`/leads/${$('#krLead').value}/kurzbericht`, 'POST', {items, intro: e.target.elements.intro.value});
        $('#krPreview').innerHTML = `<pre data-kr-md>${esc(r.markdown)}</pre><button type="button" class="btn btn-ghost" id="krDownload">Kurzbericht herunterladen (.md)</button><p class="muted">${esc(r.notice)}</p>`;
        $('#krDownload').onclick = () => wsDownload(r.filename, r.markdown, 'text/markdown;charset=utf-8');
        toast(r.notice);
      } catch (err) { toast(err.message, true); }
    }, true);
  });
})();
