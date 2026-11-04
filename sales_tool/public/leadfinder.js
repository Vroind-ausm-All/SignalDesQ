'use strict';
// v1.1 Lead-Finder: offene Quellen durchsuchen, Treffer einzeln prüfen und bewusst ins CRM übernehmen.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const ampelNames = {gruen: 'Grün · automatisierbar', gelb: 'Gelb · nur manuell / eingeschränkt', rot: 'Rot · nicht automatisieren'};
  const ampelShort = {gruen: 'Grün', gelb: 'Gelb', rot: 'Rot'};
  const statusNames = {neu: 'Neu', dublette: 'Schon im CRM', uebernommen: 'Übernommen', verworfen: 'Verworfen'};
  let cat = null, source = null, current = null;

  window.refreshLeadFinder = async function () {
    try {
      if (!cat) {
        cat = await api('/lead-finder/catalog');
        $('#lfSources').innerHTML = Object.entries(cat.sources).map(([k, s]) => `<button type="button" class="lf-card" data-lf-source="${esc(k)}"><span class="lf-ampel ${esc(s.ampel)}">${esc(ampelNames[s.ampel])}</span><b>${esc(s.title)}</b><small>${esc(s.good_for)}</small><small class="muted">${esc(s.limits)}</small><small class="lf-license">Lizenz: ${esc(s.license)}</small></button>`).join('');
        $('#lfCategory').innerHTML = Object.entries(cat.osm_categories).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
        $('#lfPreset').innerHTML = Object.entries(cat.cpv_presets).map(([k, v]) => `<option value="${esc(k)}">${esc(v.label)} (${esc(v.codes.join(', '))})</option>`).join('');
        selectSource(null);
      }
      await Promise.all([loadRuns(), loadManual()]);
    } catch (e) { toast(e.message, true); }
  };

  function selectSource(key) {
    source = key;
    $$('.lf-card').forEach(c => c.classList.toggle('active', c.dataset.lfSource === key));
    $$('#lfForm .lf-field').forEach(f => f.classList.toggle('hidden', !key || !f.dataset.for.split(' ').includes(key)));
    $('#lfSubmit').disabled = !key;
    $('#lfFormTitle').textContent = key ? cat.sources[key].title : 'Quelle wählen';
    $('#lfStatus').textContent = key ? `Fair Use: Ergebnisse werden ${cat.limits.cache_hours} h zwischengespeichert, max. ${cat.limits.daily_per_source} Abfragen pro Tag und Quelle.` : 'Wähle oben eine Quelle.';
  }

  function payload() {
    const f = $('#lfForm'), d = {source, limit: Number(f.elements.limit.value || 50)};
    if (source !== 'ted') d.place = f.elements.place.value.trim();
    if (source === 'wikidata') { d.keyword = f.elements.keyword.value.trim(); if (f.elements.min_employees.value) d.min_employees = Number(f.elements.min_employees.value); }
    if (source === 'gleif') d.keyword = f.elements.gleif_keyword.value.trim();
    if (source === 'osm') d.category = f.elements.category.value;
    if (source === 'wikidata' || source === 'osm') d.legal_entities_only = f.elements.legal_entities_only.checked;
    if (source === 'ted') { d.preset = f.elements.preset.value; d.days = Number(f.elements.days.value || 30); }
    return d;
  }

  async function search(e) {
    e.preventDefault();
    if (!source) return;
    const btn = $('#lfSubmit');
    btn.disabled = true;
    $('#lfStatus').textContent = 'Quelle wird abgefragt … (bis zu 30 Sekunden)';
    try {
      const run = await api('/lead-finder/search', 'POST', payload());
      render(run);
      $('#lfStatus').textContent = `${run.result_count} Treffer${run.filtered_count ? ` · ${run.filtered_count} ohne Rechtsform ausgefiltert` : ''}${run.cached ? ' · aus dem Zwischenspeicher (heute schon abgefragt)' : ''}.`;
      loadRuns();
      loadManual();
    } catch (err) {
      $('#lfStatus').textContent = err.message;
      toast(err.message, true);
    } finally { btn.disabled = false; }
  }

  function render(run) {
    current = run;
    const info = run.source_info || {};
    $('#lfResultTitle').textContent = `Treffer · ${info.title || run.source}`;
    $('#lfAttribution').textContent = info.attribution ? `${info.attribution} · Lizenz ${info.license}. Angaben vor Nutzung auf der Firmenwebsite prüfen.` : '';
    $('#lfRows').innerHTML = run.candidates.length ? run.candidates.map(c => `<tr class="${c.status !== 'neu' ? 'lf-done' : ''}"><td>${c.status === 'neu' ? `<input type="checkbox" data-lf-check="${c.id}" aria-label="${esc(c.name)} auswählen">` : ''}</td>
      <td><b>${esc(c.name)}</b>${c.website ? `<small><a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">${esc(c.website.replace(/^https?:\/\//, ''))}</a></small>` : '<small>keine Website in der Quelle</small>'}${c.register_id ? `<small>${esc(c.register_id)}</small>` : ''}</td>
      <td>${esc([c.zip, c.city].filter(Boolean).join(' '))}${c.street ? `<small>${esc(c.street)}</small>` : ''}</td>
      <td>${esc(c.industry || '–')}${c.employees ? `<small>${c.employees} Mitarbeitende</small>` : ''}${c.signal_note ? `<small>${esc(c.signal_note)}</small>` : ''}</td>
      <td>${c.source_url ? `<a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">Beleg ↗</a>` : ''}<small>${esc(c.license)}</small></td>
      <td>${actions(c)}</td></tr>`).join('') : '<tr><td colspan="6" class="empty">Keine Treffer. Ort anders schreiben (z. B. „München“ statt „Muenchen“) oder Filter lockern.</td></tr>';
    $('#lfSelectAll').checked = false;
    updateSelected();
  }

  function actions(c) {
    if (c.status === 'neu') return `<div class="acc-btn-group"><button type="button" class="btn btn-primary" data-lf-review="${c.id}" data-decision="uebernehmen">Übernehmen</button><button type="button" class="btn btn-ghost" data-lf-review="${c.id}" data-decision="verwerfen">Verwerfen</button>${c.website ? `<button type="button" class="btn btn-ghost" data-lf-research="${esc(c.website)}">Website prüfen</button>` : ''}</div>`;
    if (c.status === 'dublette') return `<span class="pill">${statusNames.dublette}</span>${c.duplicate_lead_id ? ` <button type="button" class="text-button" data-lf-lead="${c.duplicate_lead_id}">Lead öffnen</button>` : ''}`;
    if (c.status === 'uebernommen') return `<span class="pill won">${statusNames.uebernommen}</span>${c.lead_id ? ` <button type="button" class="text-button" data-lf-lead="${c.lead_id}">Lead öffnen</button>` : ''}`;
    return `<span class="pill lost">${statusNames[c.status] || esc(c.status)}</span>`;
  }

  function updateSelected() {
    $('#lfImportSelected').disabled = !$$('[data-lf-check]:checked').length;
  }

  async function review(id, decision, quiet = false) {
    const res = await api(`/lead-finder/candidates/${id}/review`, 'POST', {decision});
    const c = current?.candidates.find(x => x.id === id);
    if (c) { c.status = res.status; c.lead_id = res.lead_id || null; }
    if (!quiet) toast(decision === 'uebernehmen' ? 'Als Lead übernommen – Rechtsstatus „unbekannt“, nächster Schritt: Website prüfen' : 'Verworfen');
    return res;
  }

  async function loadRuns() {
    const runs = await api('/lead-finder/runs');
    $('#lfRuns').innerHTML = runs.length ? runs.slice(0, 12).map(r => {
      const p = JSON.parse(r.params_json || '{}');
      const label = cat?.sources[r.source]?.title || r.source;
      const what = r.source === 'ted' ? (cat?.cpv_presets[p.preset]?.label || p.preset) : [p.place, p.keyword, p.category && cat?.osm_categories[p.category]].filter(Boolean).join(' · ');
      return `<div class="sales-item"><div><strong>${esc(label)}</strong><small>${esc(what)} · ${esc(r.created_at)} UTC · ${r.status === 'failed' ? 'Fehler: ' + esc(r.error) : `${r.result_count} Treffer, ${r.open_count} offen`}</small></div>${r.status === 'done' ? `<button type="button" class="btn btn-ghost" data-lf-run="${r.id}">Öffnen</button>` : ''}</div>`;
    }).join('') : '<div class="empty">Noch keine Suchläufe.</div>';
  }

  async function loadManual() {
    const f = $('#lfForm');
    const place = f.elements.place.value.trim(), keyword = (f.elements.keyword.value || f.elements.gleif_keyword.value || '').trim();
    const links = await api('/lead-finder/manual-links?' + new URLSearchParams({place, keyword}).toString());
    $('#lfManual').innerHTML = links.map(l => `<div class="sales-item"><div><strong><span class="lf-ampel ${esc(l.ampel)}">${esc(ampelShort[l.ampel] || l.ampel)}</span> ${esc(l.name)}</strong><small>${esc(l.why)}</small></div>${l.link ? `<a class="btn btn-ghost" href="${esc(l.link)}" target="_blank" rel="noopener noreferrer">Öffnen ↗</a>` : ''}</div>`).join('');
  }

  function init() {
    if (!$('#viewFinder')) return;
    $('#lfForm').addEventListener('submit', search);
    $('#lfForm').addEventListener('change', e => { if (['place', 'keyword', 'gleif_keyword'].includes(e.target.name)) loadManual().catch(() => {}); });
    $('#lfSelectAll').addEventListener('change', e => { $$('[data-lf-check]').forEach(c => { c.checked = e.target.checked; }); updateSelected(); });
    $('#lfImportSelected').addEventListener('click', async () => {
      const ids = $$('[data-lf-check]:checked').map(c => Number(c.dataset.lfCheck));
      if (!ids.length || !confirm(`${ids.length} Treffer als Leads übernehmen? Jeder startet mit Rechtsstatus „unbekannt“.`)) return;
      let ok = 0;
      for (const id of ids) { try { await review(id, 'uebernehmen', true); ok++; } catch (err) { toast(err.message, true); } }
      toast(`${ok} Lead(s) übernommen`);
      render(current); await reload(); loadRuns();
    });
    $('#viewFinder').addEventListener('change', e => { if (e.target.matches('[data-lf-check]')) updateSelected(); });
    $('#viewFinder').addEventListener('click', async e => {
      const card = e.target.closest('[data-lf-source]');
      if (card) return selectSource(card.dataset.lfSource);
      const rev = e.target.closest('[data-lf-review]');
      if (rev) { try { await review(Number(rev.dataset.lfReview), rev.dataset.decision); render(current); await reload(); loadRuns(); } catch (err) { toast(err.message, true); } return; }
      const res = e.target.closest('[data-lf-research]');
      if (res) { switchView('research'); $('#researchUrl').value = res.dataset.lfResearch; $('#researchUrl').focus(); toast('URL übernommen – Recherche mit „Recherche starten“ auslösen'); return; }
      const lead = e.target.closest('[data-lf-lead]');
      if (lead) { switchView('leads'); showModal(Number(lead.dataset.lfLead)); return; }
      const run = e.target.closest('[data-lf-run]');
      if (run) { try { render(await api('/lead-finder/runs/' + run.dataset.lfRun)); $('#lfRows').scrollIntoView({behavior: 'smooth', block: 'start'}); } catch (err) { toast(err.message, true); } }
    });
  }
  init();
})();
