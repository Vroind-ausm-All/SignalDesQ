'use strict';
// 2.0.0-dev18 (Produktreview M13 Teil 1): Verkaufschancen je Firma – eigene Phase, Anliegen, nächster Schritt, Angebote
// und Termine. Abschnitt im Reiter „Bedarf & Angebot“ der Firmenakte; Auswahl der Chance beim Angebot und beim Termin.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const TONE = {bedarf: 'wait', termin: 'mid', angebot: 'mid', gewonnen: 'ok', verloren: 'bad'};
  const STATUS = {entwurf: 'Entwurf', gesendet_manuell: 'versendet', angenommen: 'angenommen', abgelehnt: 'abgelehnt'};
  let leadId = null, data = null, svcOptions = '';
  const DISC = ['problem', 'impact', 'current_solution', 'desired_outcome', 'timing', 'decision_process', 'budget_status', 'budget_note'];

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
        ${needBlock(c)}
        <details class="ch-brief" data-ch-brief="${c.id}"><summary>Briefing <small>${esc(briefLine(c.briefing))}</small></summary><div class="ch-brief-body"><div class="muted">wird geladen …</div></div></details>
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

  // 2.0.0-dev19 (Teil 2): Bedarf und Freigabe je Chance – die erste Chance nutzt die Bedarfsanalyse der Firma
  function needBlock(c) {
    const status = c.need_confirmed ? `<span class="pill ok">Bedarf bestätigt am ${esc(fmtDate(String(c.confirmed_at).slice(0, 10)))}</span>` : '<span class="pill wait">Bedarf noch nicht bestätigt</span>';
    if (c.is_first) return `<div class="ch-need">${status} <small class="muted">Bedarfsanalyse unten, Freigabe im Überblick der Akte.</small></div>`;
    if (!c.open) return `<div class="ch-need">${status}</div>`;
    return `<div class="ch-need">${status} <button type="button" class="text-button" data-ch-analysis="${c.id}">Bedarfsanalyse dieser Chance ↓</button>
      ${c.need_confirmed ? `<div class="sales-row"><button type="button" class="btn btn-primary" data-ch-quote="${c.id}">Angebot aus bestätigtem Bedarf</button>
        <button type="button" class="text-button" data-ch-reopen="${c.id}">Bedarf wieder öffnen</button></div>`
      : `<details class="ch-confirm"><summary>Bedarf dieser Chance bestätigen</summary><form class="sales-form" data-ch-confirm="${c.id}">
        <label>Bestätigt<select name="via"><option value="gespraech">im Telefonat</option><option value="termin">im Termin</option><option value="schriftlich">schriftlich vom Kunden</option></select></label>
        <label>Was hat der Kunde bestätigt?<textarea name="note" rows="2" maxlength="1000" required></textarea></label>
        <div class="sales-row"><label>Leistung<select name="service">${svcOptions}</select></label><label>Umfang<select name="size"><option value="S">Basis</option><option value="M" selected>Standard</option><option value="L">Umfangreich</option></select></label><label>Menge<input type="number" name="qty" min="1" step="1" value="1"></label></div>
        <small class="muted">Weitere Leistungen ergänzt du später im Angebot.</small>
        <button type="submit" class="btn btn-primary">Bedarf bestätigen</button></form></details>`}</div>`;
  }

  async function services() {
    if (svcOptions) return;
    try {
      const cat = await api('/pricing/catalog');
      svcOptions = cat.groups.map(g => `<optgroup label="${esc(g.group)}">${g.services.filter(s => ['paket', 'menge'].includes(s.kind)).map(s => `<option value="${esc(s.key)}" data-kind="${s.kind}" data-min="${s.min_qty}">${esc(s.title)}</option>`).join('')}</optgroup>`).join('');
    } catch { svcOptions = ''; }
  }

  function fillNeedSelect() {
    const wrap = $('#discoveryChanceWrap'), sel = $('#discoveryChance'), form = $('#discoveryForm');
    if (!wrap || !sel) return;
    const others = (data?.chances || []).filter(c => !c.is_first);
    wrap.classList.toggle('hidden', !others.length);
    const first = (data?.chances || []).find(c => c.is_first);
    sel.innerHTML = `<option value="">${esc(first ? first.title + ' – ' : '')}Bedarfsanalyse der Firma</option>` + others.map(c => `<option value="${c.id}">${esc(c.title)}${c.open ? '' : ' (abgeschlossen)'}</option>`).join('');
    sel.value = '';
    if (form) delete form.dataset.chance;
  }

  async function showNeed(chance) {
    const form = $('#discoveryForm');
    if (!form || !leadId) return;
    if (!chance) { delete form.dataset.chance; await loadDiscovery(leadId); window.leadGuard?.rebase?.('discoveryForm'); return; }
    const d = await api(`/leads/${leadId}/discovery?chance=${chance}`);
    form.dataset.chance = chance;
    for (const k of DISC) if (form.elements[k]) form.elements[k].value = d[k] || (k === 'budget_status' ? 'offen' : '');
    $('#discoveryProgress').textContent = `Chance „${(data.chances.find(c => String(c.id) === String(chance)) || {}).title || ''}“: ${d.completeness.answered} von ${d.completeness.total} Kernfragen erfasst`;
    window.leadGuard?.rebase?.('discoveryForm');
  }

  // 2.0.0-dev20 (M14): Briefing je Chance – Fragen je Leistungsbereich, jede bewusst geklärt, offen oder entfällt
  function briefLine(s) {
    if (!s) return '';
    const total = s.geklaert + s.offen + s.entfaellt + s.unbeantwortet;
    return total ? `${s.geklaert} geklärt · ${s.offen} offen · ${s.entfaellt} entfällt · ${s.unbeantwortet} unbeantwortet` : 'Leistungsbereich wählen, dann passende Fragen klären';
  }
  async function renderBrief(box) {
    const id = box.dataset.chBrief, body = box.querySelector('.ch-brief-body');
    try {
      const b = await api(`/chances/${id}/briefing`);
      const areaBoxes = Object.entries(b.all_areas).map(([k, l]) => `<label class="ch-area"><input type="checkbox" name="area" value="${esc(k)}" ${b.areas.some(a => a.key === k) ? 'checked' : ''}>${esc(l)}</label>`).join('');
      const groups = b.areas.map(a => `<fieldset class="ch-brief-area"><legend>${esc(a.label)}</legend>${b.items.filter(i => i.area === a.key).map(i => `
        <div class="ch-q" data-q="${esc(i.key)}"><div><b>${esc(i.label)}</b> <small>${esc(i.question)}</small><small class="muted">Zunächst anfordern: ${esc(i.request)}</small></div>
          <div class="sales-row"><select name="status" aria-label="Status ${esc(i.label)}"><option value="">– unbeantwortet –</option>${Object.entries(b.statuses).map(([k, l]) => `<option value="${k}" ${k === i.status ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
          <input name="answer" maxlength="1000" value="${esc(i.answer)}" placeholder="Angabe des Kunden bzw. was fehlt, wer liefert, bis wann" aria-label="Antwort ${esc(i.label)}"></div></div>`).join('')}</fieldset>`).join('');
      body.innerHTML = `<form class="sales-form" data-ch-brief-form="${id}">
        <div class="ch-areas"><span class="muted">Leistungsbereiche${b.chosen ? '' : ' (aus Bedarf, Leistung und Angeboten erkannt)'}:</span> ${areaBoxes}</div>
        ${groups || '<p class="muted">Noch kein Leistungsbereich erkannt – oben wählen und speichern.</p>'}
        <p class="muted">${esc(briefLine(b.summary))}. Geklärte Angaben und offene Voraussetzungen übernimmt das Angebot unter „Voraussetzungen“.</p>
        <button type="submit" class="btn btn-primary">Briefing speichern</button></form>`;
    } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
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
    try { [data] = await Promise.all([api(`/leads/${id}/chances`), services()]); render(); fillNeedSelect(); } catch (e) { toast(e.message, true); }
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
    // 2.0.0-dev19: offene Chancen aller Firmen für Pipeline (und Zähler) mit jedem Neuladen holen
    window.openChances = [];
    const origReload = window.reload;
    if (origReload) window.reload = async function (...a) { try { window.openChances = await api('/chances'); } catch { /* Pipeline zeigt dann Firmen */ } return origReload.apply(this, a); };
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
    $('#qbBriefing')?.addEventListener('click', async () => {
      const v = $('#quoteForm [name=opportunity_id]')?.value, ta = $('#quoteForm [name=assumptions]');
      if (!/^\d+$/.test(v || '')) return toast('Erst Firma und Chance wählen – das Briefing gehört zu einer Chance.', true);
      try {
        const r = await api(`/chances/${v}/briefing/voraussetzungen`);
        if (!r.text) return toast('Im Briefing dieser Chance ist noch nichts als geklärt oder offen markiert.', true);
        ta.value = (ta.value.trim() ? ta.value.trim() + ' ' : '') + r.text;
        ta.dispatchEvent(new Event('change', {bubbles: true}));
        toast(`Übernommen: ${r.summary.geklaert} geklärte Angabe(n), ${r.summary.offen} offene Voraussetzung(en)`);
      } catch (err) { toast(err.message, true); }
    });
    $('#discoveryChance')?.addEventListener('change', e => showNeed(e.target.value).catch(err => toast(err.message, true)));
    document.addEventListener('click', async e => {
      const an = e.target.closest('[data-ch-analysis]');
      if (an) { const sel = $('#discoveryChance'); sel.value = an.dataset.chAnalysis; await showNeed(sel.value).catch(err => toast(err.message, true)); $('#discoveryForm').scrollIntoView({behavior: 'smooth', block: 'start'}); return; }
      const q = e.target.closest('[data-ch-quote]');
      if (q) {
        try {
          const r = await api(`/leads/${leadId}/quote-from-need`, 'POST', {opportunity_id: Number(q.dataset.chQuote)});
          toast(`Angebotsentwurf ${r.number} aus dem Bedarf der Chance erstellt – prüfen und freigeben`);
          closeModal(); window.reload?.(); window.goAction?.({view: 'quotes', ref: r.id, lead_id: leadId});
        } catch (err) { toast(err.message, true); }
        return;
      }
      const ro = e.target.closest('[data-ch-reopen]');
      if (ro) {
        const reason = prompt('Warum wird der Bedarf dieser Chance neu geklärt?');
        if (!reason) return;
        try { await api(`/leads/${leadId}/need/reopen`, 'POST', {reason, opportunity_id: Number(ro.dataset.chReopen)}); toast('Bedarf wieder offen'); await load(leadId); } catch (err) { toast(err.message, true); }
      }
    });
    document.addEventListener('toggle', e => { const b = e.target.closest?.('[data-ch-brief]'); if (b && b.open) renderBrief(b); }, true);
    document.addEventListener('submit', async e => {
      const bf = e.target.closest('[data-ch-brief-form]');
      if (bf) {
        e.preventDefault();
        const areas = Array.from(bf.querySelectorAll('[name=area]:checked')).map(x => x.value);
        const answers = Array.from(bf.querySelectorAll('[data-q]')).map(q => ({key: q.dataset.q, status: q.querySelector('[name=status]').value, answer: q.querySelector('[name=answer]').value}));
        try {
          await api(`/chances/${bf.dataset.chBriefForm}/briefing`, 'PUT', {areas, answers});
          toast('Briefing gespeichert');
          const box = bf.closest('[data-ch-brief]');
          await renderBrief(box);
          const c = data.chances.find(x => String(x.id) === bf.dataset.chBriefForm);
          if (c) { c.briefing = (await api(`/chances/${c.id}/briefing`)).summary; box.querySelector('summary small').textContent = briefLine(c.briefing); }
        } catch (err) { toast(err.message, true); }
        return;
      }
      // Bedarfsanalyse einer weiteren Chance speichern (die erste Chance speichert wie bisher die Firma)
      if (e.target.id === 'discoveryForm' && e.target.dataset.chance) {
        e.preventDefault(); e.stopImmediatePropagation();
        const f = e.target, body = Object.fromEntries(DISC.filter(k => f.elements[k]).map(k => [k, f.elements[k].value]));
        try { await api(`/leads/${leadId}/discovery?chance=${f.dataset.chance}`, 'PUT', body); toast('Bedarfsanalyse der Chance gespeichert'); const keep = f.dataset.chance; await load(leadId); $('#discoveryChance').value = keep; await showNeed(keep); }
        catch (err) { toast(err.message, true); }
        return;
      }
      const cf = e.target.closest('[data-ch-confirm]');
      if (cf) {
        e.preventDefault();
        const opt = cf.elements.service.selectedOptions[0];
        const need = opt?.dataset.kind === 'menge' ? {service: opt.value, qty: Math.max(Number(cf.elements.qty.value) || 1, Number(opt.dataset.min) || 1)} : {service: opt?.value, size: cf.elements.size.value};
        try { await api(`/leads/${leadId}/need/confirm`, 'POST', {via: cf.elements.via.value, note: cf.elements.note.value.trim(), needs: [need], opportunity_id: Number(cf.dataset.chConfirm)});
          toast('Bedarf der Chance bestätigt – Angebot kann erstellt werden'); await load(leadId); window.reload?.(); }
        catch (err) { toast(err.message, true); }
        return;
      }
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
