'use strict';
// 2.0.0-dev18 (Produktreview M13 Teil 1): Verkaufschancen je Firma – eigene Phase, Anliegen, nächster Schritt, Angebote
// und Termine. Abschnitt im Reiter „Bedarf & Angebot“ der Firmenakte; Auswahl der Chance beim Angebot und beim Termin.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const TONE = {bedarf: 'wait', termin: 'mid', angebot: 'mid', gewonnen: 'ok', verloren: 'bad'};
  const STATUS = {entwurf: 'Entwurf', gesendet_manuell: 'versendet', angenommen: 'angenommen', abgelehnt: 'abgelehnt'};
  let leadId = null, data = null;

  const offerOptions = sel => '<option value="">– offen –</option>' + Object.entries(config.offers || {}).map(([k, o]) => `<option value="${esc(k)}" ${k === sel ? 'selected' : ''}>${esc(o.title)}</option>`).join('');

  function card(c) {
    const stages = Object.entries(data.stages).filter(([k]) => c.stage !== 'gewonnen' || k === 'gewonnen');
    const need = [c.problem && `Anliegen: ${c.problem}`, c.desired_outcome && `Ergebnis: ${c.desired_outcome}`, c.timing && `Zeitrahmen: ${c.timing}`].filter(Boolean);
    const props = c.proposals.map(p => `<li>${esc(p.number)} · ${esc(STATUS[p.status] || p.status)}${p.net_eur != null ? ' · ' + esc(euros(p.net_eur)) + ' netto' : ''}</li>`).join('');
    const meets = c.meetings.map(m => `<li>${esc(fmtDate(m.starts_at.slice(0, 10)))} · ${esc(m.title)}</li>`).join('');
    const own = !c.is_first && c.stage !== 'gewonnen';
    return `<details class="ch-item" data-ch="${c.id}" ${c.open ? 'open' : ''}>
      <summary><b>${esc(c.title)}</b> <span class="pill ${TONE[c.stage]}">${esc(c.stage_label)}</span>
        <small>${[c.offer_title, c.next_step && `nächster Schritt: ${c.next_step}${c.next_date ? ' (' + fmtDate(c.next_date) + ')' : ''}`, c.lost_label && `Grund: ${c.lost_label}`,
          c.proposals.length && `${c.proposals.length} Angebot(e)`].filter(Boolean).map(esc).join(' · ')}</small></summary>
      <div class="ch-body">
        <p class="muted">${need.length ? need.map(esc).join('<br>') : (c.is_first ? 'Bedarf: in der Bedarfsanalyse unten (gilt für die erste Chance).' : 'Noch kein Anliegen festgehalten.')}${need.length ? `<br><small>Quelle: ${esc(c.need_source)}</small>` : ''}</p>
        ${props ? `<div class="sales-subhead">Angebote</div><ul class="ch-mini">${props}</ul>` : ''}
        ${meets ? `<div class="sales-subhead">Termine</div><ul class="ch-mini">${meets}</ul>` : ''}
        ${c.stage === 'gewonnen' ? '<p class="muted">Gewonnen – für ein weiteres Projekt eine neue Chance anlegen.</p>' : `<form class="sales-form ch-edit" data-ch-form="${c.id}">
          <div class="sales-row"><label>Phase<select name="stage">${stages.map(([k, l]) => `<option value="${k}" ${k === c.stage ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
          <label>Leistung<select name="offer">${offerOptions(c.offer)}</select></label></div>
          <div class="sales-row ch-lost ${c.stage === 'verloren' ? '' : 'hidden'}"><label>Verlustgrund<select name="lost_reason"><option value="">– bitte wählen –</option>${Object.entries(data.lost_reasons).map(([k, l]) => `<option value="${k}" ${k === c.lost_reason ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
          <label>Notiz<input name="lost_note" maxlength="500" value="${esc(c.lost_note)}"></label></div>
          <div class="sales-row"><label>Nächster Schritt<input name="next_step" maxlength="300" value="${esc(c.next_step)}"></label><label>Datum<input type="date" name="next_date" value="${esc(c.next_date)}"></label></div>
          ${own ? `<label>Anliegen laut Kunde<textarea name="problem" rows="2" maxlength="1000">${esc(c.problem)}</textarea></label>
          <div class="sales-row"><label>Gewünschtes Ergebnis<input name="desired_outcome" maxlength="1000" value="${esc(c.desired_outcome)}"></label><label>Zeitrahmen<input name="timing" maxlength="200" value="${esc(c.timing)}"></label></div>` : ''}
          <div class="form-actions"><button type="submit" class="btn btn-primary">Chance speichern</button></div></form>`}
      </div></details>`;
  }

  function render() {
    const list = $('#chList');
    if (!list || !data) return;
    list.innerHTML = data.chances.length ? data.chances.map(card).join('')
      : '<div class="empty">Noch keine Chance. Sie entsteht mit dem ersten Angebot oder über „Neue Chance“.</div>';
  }

  async function load(id) {
    leadId = id;
    if (!id) { data = null; if ($('#chList')) $('#chList').innerHTML = ''; return; }
    try { data = await api(`/leads/${id}/chances`); render(); } catch (e) { toast(e.message, true); }
  }
  window.loadChances = load;

  // Auswahl der Chance in Angebot und Termin
  async function fillSelect(sel, lid) {
    if (!sel) return;
    const offer = sel.dataset.chSelect === 'angebot';
    const none = offer ? '<option value="">neue Chance (aus dem Projekttitel)</option>' : '<option value="">ohne Chance (Firmentermin)</option>';
    if (!lid) { sel.innerHTML = none; return; }
    try {
      const open = (await api(`/leads/${lid}/chances`)).chances.filter(c => c.open);
      const item = c => `<option value="${c.id}">${esc(c.title)} · ${esc(c.stage_label)}</option>`;
      sel.innerHTML = !open.length ? none
        : (open.length > 1 ? '<option value="">– bitte Chance wählen –</option>' : '') + open.map(item).join('')
          + (offer ? '<option value="neu">＋ als neue Chance anlegen</option>' : '');
    } catch { sel.innerHTML = none; }
  }

  function init() {
    if (!$('#chList')) return;
    const origSI = window.loadSalesIntegration;
    window.loadSalesIntegration = async function (id) { await Promise.all([origSI ? origSI(id) : null, load(id)]); };
    const origModal = window.showModal;  // neue Firma: keine Chancen der zuvor geöffneten Firma stehen lassen
    window.showModal = async function (id = null, offer = null) { if (!id) { leadId = null; data = null; if ($('#chList')) $('#chList').innerHTML = '<div class="empty">Erst die Firma speichern – dann lassen sich Chancen anlegen.</div>'; } return origModal(id, offer); };
    $('#chNewBtn').addEventListener('click', () => {
      const f = $('#chNewForm');
      f.elements.offer.innerHTML = offerOptions('');
      f.classList.toggle('hidden');
      if (!f.classList.contains('hidden')) f.elements.title.focus();
    });
    $('#chNewCancel').addEventListener('click', () => { $('#chNewForm').reset(); $('#chNewForm').classList.add('hidden'); });
    $('#chNewForm').addEventListener('submit', async e => {
      e.preventDefault();
      if (!leadId) return toast('Erst die Firma speichern', true);
      const f = e.target, body = {};
      for (const k of ['title', 'offer', 'problem', 'desired_outcome', 'timing']) if (f.elements[k].value.trim() || k === 'title') body[k] = f.elements[k].value.trim();
      try { await api(`/leads/${leadId}/chances`, 'POST', body); f.reset(); f.classList.add('hidden'); toast('Chance angelegt'); await load(leadId); window.reload?.(); }
      catch (err) { toast(err.message, true); }
    });
    document.addEventListener('change', e => {
      const st = e.target.closest('.ch-edit [name=stage]');
      if (st) st.closest('form').querySelector('.ch-lost').classList.toggle('hidden', st.value !== 'verloren');
      const lead = e.target.closest('#quoteForm [name=lead_id], #wsMeetingForm [name=lead_id]');
      if (lead) fillSelect(lead.form.querySelector('[data-ch-select]'), lead.value);
    });
    document.addEventListener('submit', async e => {
      const f = e.target.closest('[data-ch-form]');
      if (!f) return;
      e.preventDefault();
      const c = data.chances.find(x => String(x.id) === f.dataset.chForm);
      const body = {};
      for (const el of f.elements) {
        if (!el.name) continue;
        if (['lost_reason', 'lost_note'].includes(el.name) && f.elements.stage.value !== 'verloren') continue;
        if (String(c[el.name] ?? '') !== el.value) body[el.name] = el.value;
      }
      if (body.stage === 'verloren' || (f.elements.stage.value === 'verloren' && c.stage !== 'verloren')) {
        body.lost_reason = f.elements.lost_reason.value; body.lost_note = f.elements.lost_note.value;
      }
      if (!Object.keys(body).length) return toast('Nichts geändert');
      try { await api(`/chances/${c.id}`, 'PATCH', body); toast('Chance gespeichert'); await load(leadId); window.reload?.(); }
      catch (err) { toast(err.message, true); }
    }, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
