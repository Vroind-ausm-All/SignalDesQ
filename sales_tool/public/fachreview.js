'use strict';
// 2.0.0-dev46 (Roadmap M29/M33): Fachreview zu einer Website-Bewertung erfassen (sofort gespeichert) und Übereinstimmung
// zwischen deinem Urteil und der automatischen Bewertung je Rubrik und Version sehen. Keine automatische Gewichtsänderung.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const AREA = {design: 'Design & UX', web: 'Web & Conversion', process: 'Prozess & App'};
  let current = null;

  function calibrationHtml(c) {
    if (!c.rows.length) return `<p class="muted">Noch keine abgeschlossenen Reviews. ${esc(c.notice)}</p>`;
    return `<div class="table-wrap"><table class="acc-table fr-cal"><thead><tr><th>Version</th><th>Rubrik</th><th>Übereinstimmung</th><th>Abweichungen</th></tr></thead><tbody>
      ${c.rows.map(r => `<tr class="${r.flag ? 'fr-flag' : ''}" data-fr-cal="${esc(r.rubric)}"><td><small>${esc(r.version.slice(0, 8) || '–')}</small></td><td>${esc(r.label)}</td>
        <td><b>${r.pct} %</b> <small>(${r.agree} von ${r.n}${r.enough ? '' : ', wenige Urteile'})</small></td>
        <td><small>${esc(Object.entries(r.directions).map(([k, n]) => `${n}× ${k}`).join(' · ') || '–')}</small></td></tr>`).join('')}
      </tbody></table></div><p class="muted">${esc(c.notice)}</p>`;
  }

  async function load() {
    if (!$('#frBox')) return;
    try {
      const o = await api('/fachreview');
      $('#frAudit').innerHTML = o.audits.length ? o.audits.map(a => `<option value="${a.id}">${esc([a.company, (a.finished_at || '').slice(0, 10), a.version ? 'Version ' + a.version.slice(0, 8) : ''].filter(Boolean).join(' · '))}</option>`).join('') : '<option value="">keine abgeschlossene Bewertung</option>';
      $('#frStart').disabled = !o.audits.length;
      $('#frList').innerHTML = o.reviews.length ? o.reviews.map(r => `<div class="sales-item"><div><strong>${esc(r.company)}</strong><small>${esc(r.reviewer)} · ${r.status === 'abgeschlossen' ? 'abgeschlossen ' + esc(r.completed_at.slice(0, 10)) : 'Entwurf'} · Version ${esc(r.version_hash.slice(0, 8))}</small></div><button type="button" class="btn btn-ghost" data-fr-open="${r.id}">Öffnen</button></div>`).join('') : '<div class="empty">Noch kein Review.</div>';
      $('#frCalibration').innerHTML = calibrationHtml(o.calibration);
    } catch (e) { $('#frList').textContent = e.message; }
  }

  function render(v) {
    current = v;
    const locked = v.status !== 'entwurf';
    const dis = locked ? 'disabled' : '';
    $('#frReview').innerHTML = `<div class="sales-subhead">${esc(v.company)} · ${esc(v.reviewer)} · ${locked ? 'abgeschlossen ' + esc(v.completed_at) : 'Entwurf – jede Eingabe ist sofort gespeichert'}</div>
      <p class="muted">${v.progress.decided} von ${v.progress.chosen} gewählten Rubriken beurteilt · ${v.progress.agree} stimmen mit der automatischen Bewertung überein. Bewertungsversion ${esc(v.version_hash.slice(0, 8))}.</p>
      <div class="fr-items">${v.items.map(i => `<article class="fr-item ${i.included ? '' : 'fr-off'}" data-fr-row="${i.id}">
        <div class="fr-head"><label class="check"><input type="checkbox" data-fr-item="${i.id}" data-fr-key="included" ${i.included ? 'checked' : ''} ${dis}> <b>${esc(i.label)}</b></label>
          <small>${esc(AREA[i.area] || i.area)} · automatisch: <span class="sc-res ${esc(i.auto_result)}">${esc(v.labels[i.auto_result] || i.auto_result)}</span></small>
          <small class="muted">${esc(i.auto_evidence)}</small></div>
        ${i.included ? `<div class="fr-fields"><label>Dein Urteil<select data-fr-item="${i.id}" data-fr-key="verdict" ${dis}>${v.verdicts.map(x => `<option value="${x}" ${x === i.verdict ? 'selected' : ''}>${esc(v.labels[x])}</option>`).join('')}</select></label>
          <label>Beleg (Fundstelle, Messwert, Bildschirm)<input data-fr-item="${i.id}" data-fr-key="evidence" value="${esc(i.evidence)}" maxlength="500" ${dis}></label>
          <label>Begründung<textarea data-fr-item="${i.id}" data-fr-key="reason" rows="2" maxlength="1000" ${dis}>${esc(i.reason)}</textarea></label></div>` : ''}
      </article>`).join('')}</div>
      ${locked ? (v.note ? `<p>Notiz: ${esc(v.note)}</p>` : '') : `${v.missing.length ? `<div class="sales-banner sales-warning" data-fr-missing>Zum Abschließen fehlt noch: ${esc(v.missing.slice(0, 6).join('; '))}${v.missing.length > 6 ? ' …' : ''}</div>` : ''}
      <div class="sales-row"><label class="fr-note">Gesamtnotiz (optional)<input id="frNote" maxlength="1000"></label>
        <button type="button" class="btn btn-primary" id="frComplete" ${v.missing.length ? 'disabled' : ''}>Review abschließen</button>
        <button type="button" class="text-button" id="frDelete">Entwurf löschen</button></div>`}`;
    $('#frComplete')?.addEventListener('click', async () => {
      try { render(await api(`/fachreview/${v.id}/abschliessen`, 'POST', {note: $('#frNote').value})); toast('Review abgeschlossen'); load(); } catch (e) { toast(e.message, true); }
    });
    $('#frDelete')?.addEventListener('click', async () => {
      if (!confirm('Entwurf mit allen Eingaben löschen?')) return;
      try { await api(`/fachreview/${v.id}`, 'DELETE'); $('#frReview').innerHTML = ''; current = null; load(); } catch (e) { toast(e.message, true); }
    });
  }

  async function save(el) {
    const key = el.dataset.frKey;
    const value = key === 'included' ? el.checked : el.value;
    try {
      const v = await api(`/fachreview/rubrik/${el.dataset.frItem}`, 'POST', {[key]: value});
      const y = window.scrollY;
      const a = document.activeElement;  // Fokus ist evtl. schon im nächsten Feld – nach dem Neuaufbau dorthin zurück
      const back = a?.dataset?.frItem ? `[data-fr-item="${a.dataset.frItem}"][data-fr-key="${a.dataset.frKey}"]` : null;
      render(v);
      if (back) $(back)?.focus();
      window.scrollTo(0, y);
    } catch (e) { toast(e.message, true); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#frBox')) return;
    $('#frStartForm').addEventListener('submit', async e => {
      e.preventDefault();
      try { render(await api('/fachreview', 'POST', {audit_id: Number($('#frAudit').value), reviewer: $('#frReviewer').value})); toast('Review angelegt'); load(); }
      catch (err) { toast(err.message, true); }
    });
    document.addEventListener('click', async e => {
      const o = e.target.closest('[data-fr-open]');
      if (o) { try { render(await api(`/fachreview/${o.dataset.frOpen}`)); } catch (err) { toast(err.message, true); } }
    });
    document.addEventListener('change', e => { const el = e.target.closest('[data-fr-item]'); if (el && current) save(el); });
    $('#frBox').addEventListener('toggle', () => { if ($('#frBox').open) load(); });
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'scoring' && $('#frBox').open) load(); });
  });
})();
