'use strict';
// 2.0.0-dev45 (Roadmap M21): Recherchepilot – Zufallsstichprobe aus den gefundenen Firmen ziehen, von Hand prüfen, Quoten sehen.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const Q = {target: ['ja', 'nein', 'unklar'], website: ['richtig', 'falsch', 'fehlt', 'unklar'], has_site: ['ja', 'nein', 'unklar'], industry: ['richtig', 'falsch', 'unklar']};
  const QL = {target: 'Zielbetrieb?', website: 'Website laut SignalDesk', has_site: 'Hat eine Website?', industry: 'Branche'};
  let current = null;

  const rate = r => (r.of ? `<b>${r.pct} %</b> <small>(${r.hit} von ${r.of})</small>` : '<small class="muted">noch keine Angaben</small>');
  function metricsHtml(m, labels) {
    return `<div class="pl-metrics">${Object.entries(labels).map(([k, l]) => `<div class="pl-metric" data-pl-metric="${k}"><span>${esc(l)}</span>${rate(m[k])}</div>`).join('')}</div>
      <p class="muted">${m.checked} von ${m.total} geprüft.${m.notice ? ' ' + esc(m.notice) : ''}</p>`;
  }

  function radios(item, key) {
    const values = key === 'website' && !item.snapshot.website ? ['fehlt', 'unklar'] : Q[key];
    return `<fieldset class="pl-q"><legend>${QL[key]}</legend>${values.map(v => `<label><input type="radio" name="pl${item.id}${key}" data-pl-item="${item.id}" data-pl-key="${key}" value="${v}" ${item[key] === v ? 'checked' : ''}> ${v}</label>`).join('')}</fieldset>`;
  }

  function renderSample(v) {
    current = v;
    $('#plSample').innerHTML = `<div class="sales-subhead">${esc(v.label)} · gezogen ${esc(v.created_at.slice(0, 16).replace('T', ' '))}</div>
      ${metricsHtml(v.metrics, v.labels)}
      <div class="sales-row"><a class="btn btn-ghost" href="/api/pilot/${v.id}/export.csv">Als CSV herunterladen</a>
        <button type="button" class="text-button" id="plDelete">Stichprobe löschen</button></div>
      <div class="pl-items">${v.items.map(i => `<article class="pl-item ${i.done ? 'pl-done' : ''}" data-pl-row="${i.id}">
        <div><strong>${esc(i.snapshot.name)}</strong> <small>${esc([i.snapshot.zip, i.snapshot.city].filter(Boolean).join(' '))} · ${esc(i.snapshot.source)} · ${esc(i.snapshot.industry || 'Branche unbekannt')}</small>
        <small>Website laut SignalDesk: ${i.snapshot.website ? `<a href="${esc(/^https?:/.test(i.snapshot.website) ? i.snapshot.website : 'https://' + i.snapshot.website)}" target="_blank" rel="noopener noreferrer">${esc(i.snapshot.website)} ↗</a> (${esc(i.snapshot.website_status || 'aus der Quelle')})` : '<i>keine</i>'}</small></div>
        <div class="pl-qs">${radios(i, 'target')}${i.target === 'nein' ? '' : radios(i, 'website') + radios(i, 'has_site') + radios(i, 'industry')}
          <label class="pl-url">Echte Website (falls bekannt)<input data-pl-item="${i.id}" data-pl-key="true_url" value="${esc(i.true_url)}" maxlength="300"></label></div>
      </article>`).join('')}</div>`;
    $('#plDelete').addEventListener('click', async () => {
      if (!confirm('Stichprobe mit allen Angaben löschen?')) return;
      try { await api(`/pilot/${v.id}`, 'DELETE'); $('#plSample').innerHTML = ''; current = null; load(); } catch (e) { toast(e.message, true); }
    });
  }

  async function load() {
    if (!$('#plBox')) return;
    try {
      const o = await api('/pilot');
      $('#plSource').innerHTML = '<option value="">alle Quellen</option>' + o.sources.map(s => `<option value="${esc(s.source)}">${esc(s.source)} (${s.n})</option>`).join('');
      $('#plList').innerHTML = o.samples.length ? o.samples.map(s => `<div class="sales-item"><div><strong>${esc(s.label)}</strong><small>${s.metrics.checked} von ${s.metrics.total} geprüft · Trefferquote Websites ${s.metrics.website_precision.of ? s.metrics.website_precision.pct + ' %' : '–'}</small></div><button type="button" class="btn btn-ghost" data-pl-open="${s.id}">Öffnen</button></div>`).join('') : '<div class="empty">Noch keine Stichprobe.</div>';
      $('#plNotice').textContent = o.notice;
    } catch (e) { $('#plNotice').textContent = e.message; }
  }

  async function save(id, key, value) {
    try {
      await api(`/pilot/eintrag/${id}`, 'POST', {[key]: value});
      const y = window.scrollY;
      renderSample(await api(`/pilot/${current.id}`));  // Quoten sofort neu; Scrollposition bleibt
      window.scrollTo(0, y);
    } catch (e) { toast(e.message, true); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#plBox')) return;
    $('#plDraw').addEventListener('submit', async e => {
      e.preventDefault();
      const body = {size: Number($('#plSize').value)};
      if ($('#plSource').value) body.source = $('#plSource').value;
      try { renderSample(await api('/pilot', 'POST', body)); toast('Stichprobe gezogen'); load(); } catch (err) { toast(err.message, true); }
    });
    document.addEventListener('click', async e => {
      const o = e.target.closest('[data-pl-open]');
      if (o) { try { renderSample(await api(`/pilot/${o.dataset.plOpen}`)); } catch (err) { toast(err.message, true); } }
    });
    document.addEventListener('change', e => {
      const t = e.target.closest('[data-pl-item]');
      if (t && current) save(t.dataset.plItem, t.dataset.plKey, t.value);
    });
    $('#plBox').addEventListener('toggle', () => { if ($('#plBox').open) load(); });
  });
})();
