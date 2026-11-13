'use strict';
// v1.4 Website-Scoring: Bewertung anstoßen, Ergebnisse mit Belegen anzeigen, Raster konfigurieren.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const RESULT = {auffaellig: 'auffällig', ok: 'ok', unbekannt: 'unbekannt'};
  const CERT = {gemessen: 'gemessen', beobachtet: 'beobachtet', hypothese: 'Hypothese'};
  const AREA = {design: 'Design & UX', web: 'Web & Conversion', process: 'Prozess & App'};
  const SHOT = {desktop: 'Desktop', mobile: 'Smartphone', unterseite: 'Unterseite'};
  let meta = null, selected = new Set(), pollTimer = null, leadPoll = null;
  const val = v => (v === null || v === undefined) ? '<span class="sc-unknown">unbekannt</span>' : esc(v);

  async function loadMeta() {
    if (!meta) meta = await api('/scoring/config');
    return meta;
  }

  // ------------------------------------------------------------ Ergebnisdarstellung (Lead-Dialog und Übersicht)
  function renderAudit(a) {
    if (a.status !== 'done') {
      return `<div class="sales-banner ${a.status === 'failed' ? 'sales-warning' : ''}">${a.status === 'failed' ? 'Bewertung fehlgeschlagen: ' + esc(a.error) : 'Bewertung läuft … (Seiten werden gerendert, ca. 20–60 Sekunden)'}</div>`;
    }
    const s = a.score, sum = a.summary;
    // 2.0.0-dev17 (M27): Werte heißen, was sie sind – Auffälligkeiten (höher = mehr Hinweise), keine Qualitätsnote
    const tile = (label, v, note, unit = '') => `<div class="sc-tile"><small>${esc(label)}</small><b>${val(v)}${v === null || v === undefined ? '' : unit}</b>${note ? `<small>${note}</small>` : ''}</div>`;
    const ar = s.basis.area_scores || {};
    const tiles = `<div class="sc-tiles">
      ${tile('Akquise-Priorität', s.overall, esc(s.basis.overall_note || `aus Auffälligkeiten, Profilnähe und Anlass (${s.basis.weights.potential}/${s.basis.weights.fit}/${s.basis.weights.signal})`))}
      ${tile('Auffällig: Design & UX', s.design, `Belege ${ar.design ? ar.design.coverage_pct : 0} %`, ' %')}
      ${tile('Auffällig: Web & Conversion', s.web, `Belege ${ar.web ? ar.web.coverage_pct : 0} %`, ' %')}
      ${tile('Auffällig: Prozess & App', s.process, 'nur Hypothesen', ' %')}
      ${tile('Profilnähe (für die Priorität)', s.fit, esc(s.basis.fit_basis))}
      ${tile('Projektanlass', s.signal, esc(s.basis.signal_basis))}
      ${tile('Belegabdeckung', s.coverage + ' %', 'Anteil bewertbarer Rubriken')}</div>
      <p class="muted sc-legend">So lesen: <b>Auffällig</b> = Anteil der geprüften Rubriken mit Hinweis – höher heißt mehr belegte Hinweise, keine schlechte Website. <b>Unbekannt</b> zählt nie als schlecht. <b>Akquise-Priorität</b> ordnet nur deine Recherche. Die <b>Passung</b> A/B/C der Firma und eine <b>Verkaufschance</b> (Bedarf, Zeitpunkt, Budget) stehen getrennt in der Firmenakte; eine Qualitätsnote für Websites gibt SignalDesk bewusst nicht.</p>`;
    const cmp = a.comparison ? `<p class="muted">${a.comparison.comparable ? `Vorherige Bewertung: ${val(a.comparison.previous_overall)} → Veränderung ${a.comparison.delta === null ? '–' : (a.comparison.delta > 0 ? '+' : '') + a.comparison.delta}` : esc(a.comparison.note)}</p>` : '';
    const shots = a.screenshots.length ? `<div class="sc-shots">${a.screenshots.map(sh => `<a href="/api/screenshots/${sh.id}" target="_blank" rel="noopener"><img src="/api/screenshots/${sh.id}" alt="Screenshot ${esc(SHOT[sh.kind] || sh.kind)} ${esc(sh.page_url)}" loading="lazy"><small>${esc(SHOT[sh.kind] || sh.kind)}</small></a>`).join('')}</div>` : '<p class="muted">Keine Screenshots (ohne Browser-Rendering erfasst).</p>';
    const obs = sum.observations.length ? sum.observations.map(f => `<li><b>${esc(f.issue || f.label)}</b> <span class="sc-cert ${esc(f.certainty)}">${esc(CERT[f.certainty])}</span><br><small>${esc(f.evidence)}${f.source_url ? ` · <a href="${esc(f.source_url)}" target="_blank" rel="noopener noreferrer">Fundstelle ↗</a>` : ''}</small></li>`).join('') : '<li>Keine auffälligen Rubriken.</li>';
    const rows = a.findings.map(f => `<tr class="sc-${esc(f.result)}"><td>${esc(AREA[f.area] || f.area)}</td><td>${esc(f.label)}</td><td><span class="sc-res ${esc(f.result)}">${esc(RESULT[f.result])}</span></td><td><small>${esc(f.evidence)}</small></td><td><small>${esc(CERT[f.certainty])} · Gewicht ${f.weight}</small></td><td>${f.screenshot_id ? `<a href="/api/screenshots/${f.screenshot_id}" target="_blank" rel="noopener">Bild</a>` : ''}</td><td><select data-sc-finding="${f.id}" aria-label="Prüfstatus">${['ungeprueft', 'bestaetigt', 'verworfen'].map(x => `<option value="${x}" ${x === f.review_status ? 'selected' : ''}>${{ungeprueft: 'ungeprüft', bestaetigt: 'bestätigt', verworfen: 'verworfen'}[x]}</option>`).join('')}</select></td></tr>`).join('');
    return `${tiles}${cmp}
      <div class="sc-grid"><div><h4>Priorisierte Beobachtungen</h4><ol class="sc-obs">${obs}</ol></div>
      <div><h4>Passende Agenturleistungen <small class="muted">(unverbindlich bis zur Bedarfsklärung)</small></h4>${sum.offers.length ? `<ul>${sum.offers.map(o => `<li><b>${esc(o.title)}</b><br><small>${esc(o.reasons.join(' · '))}</small></li>`).join('')}</ul>` : '<p class="muted">Keine Zuordnung.</p>'}
      <h4>Bedarfsfragen fürs Erstgespräch</h4><ol>${sum.questions.map(q => `<li>${esc(q)}</li>`).join('')}</ol>
      <h4>Empfohlener nächster Schritt</h4><p>${esc(sum.next_step)}</p></div></div>
      <h4>Screenshots</h4>${shots}
      <details class="sc-unc"><summary>Unsicherheiten (${sum.uncertainties.length})</summary><ul>${sum.uncertainties.map(u => `<li>${esc(u)}</li>`).join('')}</ul></details>
      <details><summary>Alle Rubriken mit Belegen (${a.findings.length})</summary><div class="table-wrap"><table class="acc-table sc-table"><thead><tr><th>Bereich</th><th>Rubrik</th><th>Ergebnis</th><th>Beleg / Messwert</th><th>Art</th><th></th><th>Prüfung</th></tr></thead><tbody>${rows}</tbody></table></div></details>
      <p class="muted sc-disclaimer">${esc(sum.disclaimer)} Bewertungsversion ${esc(a.version ? a.version.hash : '–')} · erfasst ${esc(a.finished_at)} UTC · Renderer: ${esc(a.renderer === 'playwright' ? 'Chromium (Desktop + Smartphone)' : 'nur HTML')}.</p>`;
  }

  // ------------------------------------------------------------ Lead-Dialog
  window.loadLeadScore = async function (leadId) {
    clearTimeout(leadPoll);
    try {
      const list = await api(`/leads/${leadId}/website-scores`);
      if (!list.length) { $('#leadScoreStatus').textContent = 'Noch keine Bewertung. „Website bewerten“ rendert die Seite und prüft alle Rubriken.'; $('#leadScoreResult').innerHTML = ''; return; }
      const latest = list[0];
      $('#leadScoreStatus').textContent = `${list.length} Bewertung(en) · zuletzt ${latest.created_at}`;
      const a = await api('/scoring/audits/' + latest.id);
      $('#leadScoreResult').innerHTML = renderAudit(a);
      if (['queued', 'running'].includes(a.status)) leadPoll = setTimeout(() => { if (currentLeadId === leadId && !$('#modal').classList.contains('hidden')) window.loadLeadScore(leadId); }, 3000);
    } catch (e) { $('#leadScoreStatus').textContent = e.message; }
  };

  // ------------------------------------------------------------ Übersicht
  window.refreshScoring = async function () {
    try {
      const m = await loadMeta();
      $('#scRenderer').innerHTML = m.renderer_available ? '' : '<div class="sales-banner sales-warning">Browser-Rendering ist nicht installiert (Playwright/Chromium). Bewertungen laufen nur auf HTML-Basis: Design, Smartphone-Ansicht und Ladezeit bleiben „unbekannt“, der Gesamtwert meist „Datenlage unzureichend“. Abhilfe: SignalDesk über die Startdatei starten (installiert den Crawler automatisch).</div>';
      renderPicker();
      const ov = await api('/scoring/overview');
      $('#scQueue').innerHTML = ov.queue.length ? ov.queue.map(q => `<div class="sales-item"><div><strong>${esc(q.company)}</strong><small>${esc({queued: 'wartet', running: 'läuft …', failed: 'fehlgeschlagen'}[q.status] || q.status)}${q.error ? ' · ' + esc(q.error) : ''}</small></div></div>`).join('') : '<div class="empty">Keine laufenden Bewertungen.</div>';
      const pct = v => v === null || v === undefined ? val(v) : esc(v) + ' %';
      $('#scRanking').innerHTML = ov.ranking.length ? ov.ranking.map(r => `<tr><td><b>${esc(r.company)}</b><small>${esc(r.website)}</small></td><td><b>${val(r.overall)}</b></td><td>${pct(r.design)}</td><td>${pct(r.web)}</td><td>${pct(r.process)}</td><td>${val(r.fit)}</td><td>${val(r.signal)}</td><td>${r.coverage} %</td><td><small>${esc(r.version)}${r.active ? '' : ' (alt)'}</small></td><td><button type="button" class="btn btn-ghost" data-sc-open="${r.audit_id}">Details</button></td></tr>`).join('') : '<tr><td colspan="10" class="empty">Noch keine Website bewertet.</td></tr>';
      renderConfig();
      clearTimeout(pollTimer);
      if (ov.queue.some(q => ['queued', 'running'].includes(q.status))) pollTimer = setTimeout(() => { if (currentView === 'scoring') window.refreshScoring(); }, 3000);
    } catch (e) { toast(e.message, true); }
  };

  function renderPicker() {
    const q = ($('#scLeadSearch').value || '').toLowerCase();
    const list = leads.filter(l => l.website && l.stage !== 'gesperrt' && (!q || l.company.toLowerCase().includes(q))).slice(0, 60);
    $('#scLeadPicker').innerHTML = list.length ? list.map(l => `<label class="sc-pick"><input type="checkbox" data-sc-lead="${l.id}" ${selected.has(l.id) ? 'checked' : ''}> <span>${esc(l.company)}<small>${esc(l.website)}</small></span></label>`).join('') : '<div class="empty">Keine Leads mit Website.</div>';
    $('#scStart').disabled = !selected.size;
    $('#scStart').textContent = selected.size ? `${selected.size} Lead(s) bewerten ↗` : 'Ausgewählte bewerten ↗';
  }

  async function openAudit(id) {
    try {
      const a = await api('/scoring/audits/' + id);
      const lead = leads.find(l => l.id === a.lead_id);
      $('#scDetailTitle').textContent = 'Bewertung · ' + (lead ? lead.company : a.url);
      $('#scDetail').innerHTML = renderAudit(a);
      $('#scDetailPanel').classList.remove('hidden');
      $('#scDetailPanel').scrollIntoView({behavior: 'smooth', block: 'start'});
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Konfiguration
  function renderConfig() {
    const c = meta.config;
    const num = (name, v, min, max, step = 1) => `<input type="number" name="${name}" value="${v}" min="${min}" max="${max}" step="${step}">`;
    $('#scConfigForm').innerHTML = `<p class="muted">Aktive Version <b>${esc(meta.hash)}</b>. Akquise-Priorität = gewichtetes Mittel aus Auffälligkeiten (belegbares Verbesserungspotenzial), Profilnähe und aktuellem Anlass (Vorschlag 35/35/30); Unbekanntes fällt heraus statt niedrig zu zählen. Teil-Scores werden nur bei ausreichender Belegabdeckung berechnet.</p>
      <div class="acc-row3"><label>Gewicht Auffälligkeiten ${num('ow_potential', c.overall_weights.potential, 0, 100)}</label><label>Gewicht Profilnähe ${num('ow_fit', c.overall_weights.fit, 0, 100)}</label><label>Gewicht Anlass ${num('ow_signal', c.overall_weights.signal, 0, 100)}</label></div>
      <div class="acc-row3"><label>Bereich Design ${num('aw_design', c.area_weights.design, 0, 100, 0.5)}</label><label>Bereich Web ${num('aw_web', c.area_weights.web, 0, 100, 0.5)}</label><label>Bereich Prozess ${num('aw_process', c.area_weights.process, 0, 100, 0.5)}</label></div>
      <div class="sales-row"><label>Mindest-Belegabdeckung für Gesamtwert (%) ${num('min_coverage_pct', c.min_coverage_pct, 10, 100)}</label><label>Mindest-Abdeckung je Bereich (%) ${num('min_area_coverage_pct', c.min_area_coverage_pct, 10, 100)}</label></div>
      <div class="table-wrap"><table class="acc-table"><thead><tr><th>Aktiv</th><th>Rubrik</th><th>Bereich</th><th>Gewicht</th></tr></thead><tbody>${Object.entries(c.rubrics).map(([id, r]) => `<tr><td><input type="checkbox" data-rub-on="${id}" ${r.enabled ? 'checked' : ''}></td><td>${esc(meta.rubric_text[id])}</td><td>${esc(AREA[r.area])}</td><td><input type="number" data-rub-w="${id}" value="${r.weight}" min="0" max="10" step="0.5"></td></tr>`).join('')}</tbody></table></div>
      <div class="acc-btn-group"><button type="submit" class="btn btn-primary">Als neue Version speichern</button><button type="button" class="btn btn-ghost" id="scConfigReset">Standard wiederherstellen</button></div>`;
  }

  async function saveConfig(e, cfg) {
    e?.preventDefault();
    const f = $('#scConfigForm');
    const n = k => Number(f.elements[k].value);
    const body = cfg || {
      overall_weights: {potential: n('ow_potential'), fit: n('ow_fit'), signal: n('ow_signal')},
      area_weights: {design: n('aw_design'), web: n('aw_web'), process: n('aw_process')},
      min_coverage_pct: n('min_coverage_pct'), min_area_coverage_pct: n('min_area_coverage_pct'),
      rubrics: Object.fromEntries($$('[data-rub-w]').map(i => [i.dataset.rubW, {weight: Number(i.value), enabled: $(`[data-rub-on="${i.dataset.rubW}"]`).checked}])),
    };
    try { const r = await api('/scoring/config', 'PUT', body); meta = null; await loadMeta(); toast(r.notice); window.refreshScoring(); }
    catch (err) { toast(err.message, true); }
  }

  function init() {
    if (!$('#viewScoring')) return;
    $('#scLeadSearch').addEventListener('input', renderPicker);
    $('#scRefresh').addEventListener('click', () => window.refreshScoring());
    $('#scDetailClose').addEventListener('click', () => $('#scDetailPanel').classList.add('hidden'));
    $('#scConfigForm').addEventListener('submit', saveConfig);
    $('#scStart').addEventListener('click', async () => {
      try {
        const r = await api('/scoring/audits', 'POST', {lead_ids: [...selected]});
        toast(`${r.queued.length} Bewertung(en) gestartet${r.skipped.length ? ` · ${r.skipped.length} übersprungen (${r.skipped.map(s => s.reason).join(', ')})` : ''}`);
        selected.clear(); window.refreshScoring();
      } catch (err) { toast(err.message, true); }
    });
    $('#leadScoreBtn').addEventListener('click', async () => {
      if (!currentLeadId) return;
      try {
        const r = await api('/scoring/audits', 'POST', {lead_ids: [currentLeadId]});
        if (!r.queued.length) return toast('Nicht gestartet: ' + (r.skipped[0]?.reason || 'unbekannt'), true);
        toast('Website wird gerendert und bewertet …');
        window.loadLeadScore(currentLeadId);
      } catch (err) { toast(err.message, true); }
    });
    document.body.addEventListener('change', async e => {
      if (e.target.matches('[data-sc-lead]')) {
        const id = Number(e.target.dataset.scLead);
        if (e.target.checked) { if (selected.size >= 20) { e.target.checked = false; return toast('Höchstens 20 Leads pro Durchgang', true); } selected.add(id); } else selected.delete(id);
        renderPicker();
      }
      if (e.target.matches('[data-sc-finding]')) {
        try { await api('/scoring/findings/' + e.target.dataset.scFinding, 'PATCH', {review_status: e.target.value}); toast('Prüfstatus gespeichert'); } catch (err) { toast(err.message, true); }
      }
    });
    $('#viewScoring').addEventListener('click', e => {
      const o = e.target.closest('[data-sc-open]');
      if (o) openAudit(Number(o.dataset.scOpen));
      if (e.target.id === 'scConfigReset' && confirm('Standardraster als neue aktive Version setzen?')) saveConfig(null, meta.defaults);
    });
  }
  init();
})();
