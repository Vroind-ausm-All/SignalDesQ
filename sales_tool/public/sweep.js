'use strict';
// Sprint B: „Arbeitstag starten“ – Sammelsuche über alle offenen Quellen, großer Import, Sichtung zum Durchklicken,
// Website-Suche mit Nachweis. Nichts wird kontaktiert; übernommene Firmen starten mit Rechtsstatus „unbekannt“.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const SRC = {gleif: 'GLEIF', gleif_csv: 'GLEIF-Import', liste: 'Eigene Liste', wikidata: 'Wikidata', osm: 'OSM', ted: 'TED'};
  // Empfehlung A (v1.15): nur „belegt“, „laut Quelle“ oder von dir bestätigt gilt als Website der Firma – alles andere ist ein Vorschlag
  const WEB = {quelle: ['laut Quelle', 'ok'], belegt: ['belegt: Registernr. im Impressum', 'ok'], bestaetigt: ['von dir bestätigt', 'ok'],
    wahrscheinlich: ['Vorschlag – bitte prüfen', 'mid'], nicht_bestaetigt: ['Vorschlag – nicht eindeutig', 'mid'], abgelehnt: ['Vorschlag abgelehnt', 'off'],
    wartet: ['Suche wartet …', 'wait'], laeuft: ['wird gesucht …', 'wait'], nicht_gefunden: ['nicht gefunden', 'off']};
  const SUGGESTION = ['wahrscheinlich', 'nicht_bestaetigt'];
  const PAGE = 50;
  const KIND = {verein: 'Verein/Stiftung', oeffentlich: 'öffentlich'};
  const CHECK = {ok: ['erreichbar', 'ok'], ueberlastet: ['überlastet', 'mid'], blockiert: ['blockiert', 'off'], fehler: ['Fehler', 'off'], format: ['Format geändert', 'off']};
  let catalog = null, selectedInd = new Set(), offset = 0, data = null, cursor = 0, chosen = new Set(), pollSweep = null, pollWeb = null;
  const store = {get: k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch { return null; } },
                 set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privat */ } }};

  // ------------------------------------------------------------ Branchen
  function renderIndustries() {
    const q = ($('#swIndSearch').value || '').toLowerCase();
    $('#swIndustries').innerHTML = catalog.groups.map(g => {
      const items = g.items.filter(i => !q || i.label.toLowerCase().includes(q) || g.group.toLowerCase().includes(q));
      if (!items.length) return '';
      return `<fieldset class="sw-group"><legend>${esc(g.group)}</legend>${items.map(i => `<label class="sw-chip ${selectedInd.has(i.key) ? 'on' : ''}"><input type="checkbox" data-ind="${esc(i.key)}" ${selectedInd.has(i.key) ? 'checked' : ''}> ${esc(i.label)}</label>`).join('')}</fieldset>`;
    }).join('') || '<div class="empty">Keine Branche gefunden – eigenes Schlagwort oben eintragen.</div>';
    $('#swIndCount').textContent = selectedInd.size ? `${selectedInd.size} ausgewählt` : 'alle Branchen (kein Filter)';
  }

  // ------------------------------------------------------------ Sammelsuche
  function formParams() {
    const f = $('#swForm').elements;
    return {place: f.place.value.trim(), radius_km: Number(f.radius_km.value), industries: [...selectedInd], keywords: f.keywords.value.trim(),
      sources: $$('#swForm [name=src]:checked').map(x => x.value), operative: f.operative.checked, include_sole: f.include_sole.checked,
      find_websites: f.find_websites.checked, ted_nationwide: f.ted_nationwide.checked,
      org_kinds: $$('#swForm [name=org]:checked').map(x => x.value)};
  }

  function renderProgress(sw) {
    const box = $('#swProgress');
    box.classList.remove('hidden');
    const area = sw.progress._area, web = sw.progress._web;
    const failed = Object.entries(sw.progress).filter(([k, p]) => !k.startsWith('_') && p.status === 'fehler').length;
    const done = !['queued', 'running'].includes(sw.status);
    const rows = Object.entries(sw.progress).filter(([k]) => !k.startsWith('_')).map(([k, p]) => `<div class="sw-src ${esc(p.status)}">
      <b>${esc(p.label || SRC[k] || k)}</b><span class="sw-st ${p.status === 'wartet' && p.detail ? 'retry' : ''}">${esc(p.status === 'wartet' && p.detail ? 'neuer Versuch …' : p.status || 'wartet')}</span>
      <small>${p.error ? `<span class="${p.status === 'fehler' ? 'late' : 'muted'}">${esc(p.error)}</span>` : `${p.new ?? 0} neu · ${p.merged ?? 0} zusammengeführt · ${p.known ?? 0} schon bekannt · ${p.filtered ?? 0} ausgefiltert${p.detail ? ' · ' + esc(p.detail) : ''}`}</small></div>`).join('');
    box.innerHTML = `<div class="sw-prog-head"><b>${esc(sw.label)}</b> <span class="muted">${area ? `Mittelpunkt ${esc(area.center)} · ${area.places} Orte im Umkreis (${esc(area.via)})` : 'Suchgebiet wird bestimmt …'}</span>
      <span class="sw-st ${esc(sw.status)}">${esc({queued: 'wartet', running: 'läuft', fertig: 'fertig', fehler: 'Fehler', abgebrochen: 'abgebrochen'}[sw.status] || sw.status)}</span></div>${rows}
      ${web && web.queued ? `<div class="sw-src fertig"><b>Website-Suche</b><span class="sw-st">automatisch</span><small>${web.queued} Firmen ohne Website werden nacheinander gesucht (Nachweis per Impressum) – Status siehe Liste unten.</small></div>` : ''}
      ${done && failed ? `<div class="sw-retry"><button type="button" class="btn btn-primary" data-sw-retry="${sw.id}">↻ Fehlgeschlagene Quellen erneut abfragen</button><span class="muted">Die Server von Wikidata/OpenStreetMap sind zeitweise überlastet – ein neuer Versuch einige Minuten später hilft meist. Schon gefundene Firmen bleiben erhalten.</span></div>` : ''}`;
  }

  async function watchSweep(id) {
    clearTimeout(pollSweep);
    try {
      const sw = await api(`/sweeps/${id}`);
      renderProgress(sw);
      if (['queued', 'running'].includes(sw.status)) { pollSweep = setTimeout(() => watchSweep(id), 2000); if (sw.counts?.neu) loadList(); }
      else { $('#swGo').disabled = false; if (window.refreshJobs) window.refreshJobs(); await loadHistory(); $('#swSweep').value = String(id); offset = 0; loadList(); toast(`Suche fertig: ${sw.counts?.neu || 0} neue Firmen zum Sichten`); }
    } catch (e) { $('#swGo').disabled = false; toast(e.message, true); }
  }

  async function importFile(file) {
    if (file.size > 60_000_000) return toast('Datei größer als 60 MB.', true);
    const p = formParams();
    const qs = new URLSearchParams({filename: file.name.slice(0, 120), operative: p.operative ? '1' : '0', include_sole: p.include_sole ? '1' : '0',
      industries: p.industries.join(','), keywords: p.keywords, plz: /^\d{5}$/.test(p.place) ? p.place.slice(0, 2) : ''});
    toast(`${file.name} wird eingelesen …`);
    try {
      const resp = await fetch('/api/sweeps/import?' + qs, {method: 'POST', headers: {'Content-Type': 'text/csv'}, body: await file.text()});
      const r = await resp.json();
      if (!resp.ok) throw Error(r.error || 'Import fehlgeschlagen');
      const sk = r.skipped || {};
      toast(`${r.rows} Zeilen gelesen: ${r.new} neu, ${r.merged} zusammengeführt, ${r.known} schon bekannt, ${r.filtered} ausgefiltert` +
        (sk.inaktiv || sk.fonds_einzel ? ` · übersprungen: ${sk.inaktiv || 0} inaktiv, ${sk.fonds_einzel || 0} Fonds/Einzel` : ''));
      await loadHistory(); $('#swSweep').value = String(r.sweep_id); $('#swStatus').value = 'neu'; offset = 0; loadList();
    } catch (e) { toast(e.message, true); }
  }
  window.importCompanyFile = file => { switchView('finder'); importFile(file); };

  // ------------------------------------------------------------ Sichtung
  function webCell(c) {
    const st = WEB[c.website_status] || (c.website ? WEB.quelle : null);
    const link = c.website ? `<a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer" data-sw-open>${esc(c.website.replace(/^https?:\/\//, ''))} ↗</a>` : '<span class="muted">keine Website bekannt</span>';
    const review = c.website && SUGGESTION.includes(c.website_status)
      ? ` <span class="sw-suggest"><button type="button" class="text-button" data-sw-web="bestaetigen" data-id="${c.id}">✓ Website passt</button><button type="button" class="text-button" data-sw-web="ablehnen" data-id="${c.id}">✕ passt nicht</button></span>` : '';
    return `${link}${st ? ` <span class="sw-web ${st[1]}" title="${esc(c.website_evidence)}">${esc(st[0])}</span>` : ''}${review}`;
  }

  function row(c, i) {
    const addr = [c.street, [c.zip, c.city].filter(Boolean).join(' ')].filter(Boolean).join(', ');
    const contact = c.contact || {};
    const srcs = (c.sources || []).map(s => s.url ? `<a class="sw-srcchip" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(SRC[s.source] || s.source)}</a>` : `<span class="sw-srcchip">${esc(SRC[s.source] || s.source)}</span>`).join('');
    const open = c.status === 'neu';
    return `<article class="sw-item ${i === cursor ? 'cur' : ''}" data-sw-idx="${i}" data-id="${c.id}">
      <input type="checkbox" data-sw-sel="${c.id}" ${chosen.has(c.id) ? 'checked' : ''} aria-label="${esc(c.name)} auswählen">
      <div class="sw-main"><b>${esc(c.name)}</b>
        <small>${KIND[c.org_kind] && c.source !== 'ted' ? `<span class="sw-web mid">${esc(KIND[c.org_kind])}</span> ` : ''}${c.legal_form && c.source !== 'ted' && !c.name.toLowerCase().includes(c.legal_form.toLowerCase().replace(/\s*\(.*$/, '')) ? esc(c.legal_form) + ' · ' : ''}${esc(addr || c.city || '')}${c.distance_km != null ? ` · ${c.distance_km.toLocaleString('de-DE')} km` : ''}${c.register_id ? ' · ' + esc(c.register_id) : ''}${c.industry_label ? ` · <i>${esc(c.industry_label)}</i>` : c.industry ? ' · ' + esc(c.industry) : ''}</small>
        <div class="sw-web-line">${webCell(c)}${contact.business_phone ? ` · ☎ ${esc(contact.business_phone)}` : ''}${contact.business_email ? ` · ✉ ${esc(contact.business_email)}` : ''}${contact.imprint_url ? ` · <a href="${esc(contact.imprint_url)}" target="_blank" rel="noopener noreferrer">Impressum ↗</a>` : ''}</div>
        <div class="sw-srcs">${srcs}${c.signal_note ? `<small>${esc(c.signal_note.slice(0, 140))}</small>` : ''}</div></div>
      <div class="sw-btns">${open ? `<button type="button" class="btn btn-primary" data-sw-do="uebernehmen" data-id="${c.id}">Übernehmen</button><button type="button" class="btn btn-ghost" data-sw-do="verwerfen" data-id="${c.id}">Verwerfen</button>${['belegt', 'quelle', 'bestaetigt', 'wartet', 'laeuft'].includes(c.website_status) ? '' : `<button type="button" class="text-button" data-sw-do="website" data-id="${c.id}">Website suchen</button>`}` :
        `<span class="sw-st">${esc({uebernommen: 'übernommen', verworfen: 'verworfen', dublette: 'schon Lead', gesperrt: 'Sperrliste'}[c.status] || c.status)}</span>${c.lead_id || c.duplicate_lead_id ? `<button type="button" class="text-button" data-lead="${c.lead_id || c.duplicate_lead_id}">Lead öffnen</button>` : ''}`}</div>
    </article>`;
  }

  async function loadList() {
    const qs = new URLSearchParams({status: $('#swStatus').value, sweep_id: $('#swSweep').value, website: $('#swWeb').value, sort: $('#swSort').value,
      q: $('#swQ').value.trim(), offset: String(offset), limit: String(PAGE), city: $('#swCity').value, max_km: $('#swKm').value,
      no_ted: $('#swNoTed').checked ? '1' : ''});
    [...qs.keys()].filter(k => !qs.get(k)).forEach(k => qs.delete(k));
    try {
      data = await api('/sweep-candidates?' + qs);
      cursor = Math.min(cursor, Math.max(0, data.items.length - 1));
      $('#swList').innerHTML = data.items.length ? data.items.map(row).join('') : `<div class="empty">${$('#swStatus').value === 'neu' ? 'Nichts mehr zu sichten. Starte oben eine Suche oder importiere eine Firmenliste.' : 'Keine Einträge.'}</div>`;
      const cur = $('#swCity').value;
      $('#swCity').innerHTML = '<option value="">alle Orte</option>' + (data.cities || []).map(x => `<option value="${esc(x.city)}">${esc(x.city)} (${x.n})</option>`).join('')
        + (cur && !(data.cities || []).some(x => x.city.toLowerCase() === cur.toLowerCase()) ? `<option value="${esc(cur)}">${esc(cur)}</option>` : '');
      $('#swCity').value = cur;
      const c = data.counts || {};
      $('#swCounts').textContent = `${c.neu || 0} neu · ${c.uebernommen || 0} übernommen · ${c.verworfen || 0} verworfen · ${c.dublette || 0} schon als Lead`;
      $('#swPage').textContent = data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} von ${data.total}` : '';
      $('#swPrev').disabled = offset === 0;
      $('#swNext').disabled = offset + PAGE >= data.total;
      clearTimeout(pollWeb);
      if (data.items.some(x => ['wartet', 'laeuft'].includes(x.website_status))) pollWeb = setTimeout(loadList, 4000);
    } catch (e) { $('#swList').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  async function loadHistory() {
    try {
      const rows = await api('/sweeps');
      const cur = $('#swSweep').value;
      $('#swSweep').innerHTML = '<option value="">Alle Suchläufe & Importe</option>' + rows.map(r => `<option value="${r.id}">${esc(r.label)} (${r.open} offen)</option>`).join('');
      $('#swSweep').value = cur;
      $('#swHistory').innerHTML = rows.length ? rows.slice(0, 12).map(r => `<div class="sales-item"><div><strong>${esc(r.label)}</strong>
        <small>${esc(fmtDate(r.created_at.slice(0, 10)))} · ${r.open} offen · ${r.taken} übernommen · ${r.dismissed} verworfen · ${esc(r.status)}</small></div>
        <div class="acc-btn-group"><button type="button" class="btn btn-ghost" data-sw-show="${r.id}">Sichten</button>${r.kind === 'suche' ? `<button type="button" class="text-button" data-sw-again="${r.id}">Erneut suchen</button>` : ''}</div></div>`).join('')
        : '<div class="empty">Noch keine Suche. Tipp: Arbeite dich systematisch durch PLZ-Gebiete – z. B. 70173, dann 71032, 71634 … jeweils 30 km.</div>';
      store.set('sw_history', rows.slice(0, 12).map(r => ({id: r.id, params: r.params})));
    } catch { /* ignoriert */ }
  }

  async function decideOne(id, decision) {
    try {
      const r = await api(`/sweep-candidates/${id}/decision`, 'POST', {decision});
      toast(decision === 'uebernehmen' ? `Als Lead übernommen (Rechtsstatus „unbekannt“)${r.auto_applied?.length ? ` · aus dem Impressum ergänzt: ${r.auto_applied.length} Feld(er)` : ''}` : 'Verworfen – erscheint nicht erneut');
      chosen.delete(id);
      if (decision === 'uebernehmen' && typeof reload === 'function') reload();
      await loadList();
      return r;
    } catch (e) { toast(e.message, true); }
  }

  function setCursor(i) {
    if (!data || !data.items.length) return;
    cursor = Math.max(0, Math.min(data.items.length - 1, i));
    $$('.sw-item').forEach(el => el.classList.toggle('cur', Number(el.dataset.swIdx) === cursor));
    $(`.sw-item[data-sw-idx="${cursor}"]`)?.scrollIntoView({block: 'nearest'});
  }

  window.refreshSweep = async function () {
    if (!$('#swForm')) return;
    if (!catalog) {
      catalog = await api('/industries');
      const last = store.get('sw_last');
      if (last) {
        const f = $('#swForm').elements;
        f.place.value = last.place || ''; f.radius_km.value = String(last.radius_km ?? 30); f.keywords.value = last.keywords || '';
        if (last.find_websites === false) f.find_websites.checked = false;
        if (last.ted_nationwide) f.ted_nationwide.checked = true;
        if (Array.isArray(last.org_kinds) && last.org_kinds.length) $$('#swForm [name=org]').forEach(x => { x.checked = last.org_kinds.includes(x.value); });
        (last.industries || []).forEach(k => selectedInd.add(k));
      }
      $('#swIndNotice').textContent = catalog.notice;
      renderIndustries();
    }
    await loadHistory();
    loadList();
    const running = (await api('/sweeps')).find(s => ['queued', 'running'].includes(s.status));
    if (running) { $('#swGo').disabled = true; watchSweep(running.id); }
  };

  function init() {
    if (!$('#swForm')) return;
    const orig = window.refreshLeadFinder;
    window.refreshLeadFinder = async function () { if (orig) orig(); window.refreshSweep(); };
    $('#swIndSearch').addEventListener('input', renderIndustries);
    $('#swIndClear').addEventListener('click', () => { selectedInd.clear(); renderIndustries(); });
    $('#swIndustries').addEventListener('change', e => { const k = e.target.dataset.ind; if (!k) return; e.target.checked ? selectedInd.add(k) : selectedInd.delete(k); renderIndustries(); });
    $('#swForm').addEventListener('submit', async e => {
      e.preventDefault();
      const p = formParams();
      if (!p.sources.length) return toast('Mindestens eine Quelle wählen', true);
      if (!p.org_kinds.length) return toast('Bitte wählen, wen du suchst (z. B. Unternehmen)', true);
      store.set('sw_last', p);
      $('#swGo').disabled = true;
      try { const sw = await api('/sweeps', 'POST', p); renderProgress(sw); watchSweep(sw.id); if (window.refreshJobs) window.refreshJobs(); }
      catch (err) { $('#swGo').disabled = false; toast(err.message, true); }
    });
    $('#swCheck').addEventListener('click', async () => {
      const b = $('#swCheck');
      b.disabled = true; $('#swCheckNote').textContent = 'Prüfe … (bis zu 20 Sekunden)';
      try {
        const r = await api('/sources/check', 'POST', {run: true});
        $('#swCheckRows').innerHTML = r.rows.map(x => `<div class="sw-src ${x.status === 'ok' ? 'fertig' : x.status === 'ueberlastet' ? 'retry' : 'fehler'}">
          <b>${esc(x.label)}</b><span class="sw-web ${(CHECK[x.status] || ['', 'off'])[1]}">${esc((CHECK[x.status] || [x.status])[0])}</span>
          <small>${esc(x.detail)}${x.hint ? ` – <i>${esc(x.hint)}</i>` : ''} · ${x.ms} ms</small></div>`).join('');
        $('#swCheckNote').textContent = `${r.ok} von ${r.total} erreichbar · ${r.checked_at}${r.cached ? ' (Ergebnis von eben – höchstens eine Prüfung pro Minute)' : ''}${r.osm_any ? '' : ' · kein OpenStreetMap-Server erreichbar: die Suche läuft dann ohne OSM'}`;
      } catch (e) { $('#swCheckNote').textContent = e.message; }
      b.disabled = false;
    });
    $('#swFile').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) importFile(f); });
    ['#swStatus', '#swSweep', '#swWeb', '#swSort', '#swCity', '#swKm', '#swNoTed'].forEach(s => $(s).addEventListener('change', () => { offset = 0; cursor = 0; loadList(); }));
    let qt = null;
    $('#swQ').addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { offset = 0; loadList(); }, 300); });
    $('#swPrev').addEventListener('click', () => { offset = Math.max(0, offset - PAGE); cursor = 0; loadList(); });
    $('#swNext').addEventListener('click', () => { offset += PAGE; cursor = 0; loadList(); });
    $('#swAll').addEventListener('change', e => { (data?.items || []).forEach(c => e.target.checked ? chosen.add(c.id) : chosen.delete(c.id)); loadList(); });
    $('#swList').addEventListener('change', e => { const id = Number(e.target.dataset.swSel); if (id) e.target.checked ? chosen.add(id) : chosen.delete(id); });
    document.body.addEventListener('click', async e => {
      const d = e.target.closest('[data-sw-do]');
      if (d) {
        const id = Number(d.dataset.id);
        if (d.dataset.swDo === 'website') { try { await api('/sweep-candidates/find-websites', 'POST', {ids: [id]}); loadList(); } catch (err) { toast(err.message, true); } return; }
        return decideOne(id, d.dataset.swDo);
      }
      const wv = e.target.closest('[data-sw-web]');
      if (wv) {
        try {
          await api(`/sweep-candidates/${wv.dataset.id}/website`, 'POST', {decision: wv.dataset.swWeb});
          toast(wv.dataset.swWeb === 'bestaetigen' ? 'Website bestätigt – Impressumsdaten gelten jetzt als belegt' : 'Vorschlag abgelehnt – diese Domain wird nicht wieder vorgeschlagen');
          loadList();
        } catch (err) { toast(err.message, true); }
        return;
      }
      const rt = e.target.closest('[data-sw-retry]');
      if (rt) {
        rt.disabled = true;
        try { const r = await api(`/sweeps/${rt.dataset.swRetry}/retry`, 'POST', {}); toast(`Neuer Versuch: ${r.retrying.map(k => SRC[k] || k).join(', ')}`); $('#swGo').disabled = true; watchSweep(Number(rt.dataset.swRetry)); }
        catch (err) { rt.disabled = false; toast(err.message, true); }
        return;
      }
      const b = e.target.closest('[data-sw-bulk]');
      if (b) {
        const ids = chosen.size ? [...chosen] : (b.dataset.swBulk === 'websites' ? (data?.items || []).filter(c => c.status === 'neu' && !['belegt', 'quelle', 'bestaetigt'].includes(c.website_status)).map(c => c.id) : []);
        if (!ids.length) return toast('Bitte Firmen auswählen', true);
        try {
          if (b.dataset.swBulk === 'websites') { const r = await api('/sweep-candidates/find-websites', 'POST', {ids: ids.slice(0, 200)}); toast(`${r.queued} Firmen in der Website-Suche. ${r.notice}`); if (window.refreshJobs) window.refreshJobs(); }
          else if (b.dataset.swBulk === 'bericht') {
            const r = await api('/sweep-candidates/bulk', 'POST', {ids: ids.slice(0, 50), decision: 'uebernehmen'});
            chosen.clear(); if (typeof reload === 'function') reload();
            if (!r.lead_ids.length) { toast(r.errors[0] || 'Nichts übernommen', true); }
            else { const q = await api('/reports', 'POST', {lead_ids: r.lead_ids}); toast(`${r.done} übernommen · ${q.queued.length} Firmen-Bericht(e) gestartet${q.skipped.length ? ` · ${q.skipped.length} ohne Website übersprungen` : ''}`); }
          }
          else { const r = await api('/sweep-candidates/bulk', 'POST', {ids: ids.slice(0, 200), decision: b.dataset.swBulk}); toast(`${r.done} erledigt${r.errors.length ? ` · ${r.errors.length} Hinweise: ${r.errors[0]}` : ''}`); chosen.clear(); if (typeof reload === 'function') reload(); }
          loadList();
        } catch (err) { toast(err.message, true); }
        return;
      }
      const sh = e.target.closest('[data-sw-show]');
      if (sh) { $('#swSweep').value = sh.dataset.swShow; $('#swStatus').value = 'neu'; offset = 0; loadList(); $('#swReview').scrollIntoView({behavior: 'smooth'}); return; }
      const ag = e.target.closest('[data-sw-again]');
      if (ag) {
        const h = (store.get('sw_history') || []).find(x => String(x.id) === ag.dataset.swAgain);
        if (h) { const f = $('#swForm').elements; f.place.value = h.params.place; f.radius_km.value = String(h.params.radius_km ?? 30); f.keywords.value = (h.params.keywords || []).join(', '); selectedInd = new Set(h.params.industries || []); renderIndustries(); $('#swForm').scrollIntoView({behavior: 'smooth'}); }
        return;
      }
      const it = e.target.closest('.sw-item');
      if (it && !e.target.closest('a,button,input')) setCursor(Number(it.dataset.swIdx));
    });
    document.addEventListener('keydown', e => {
      if (currentView !== 'finder' || !data || e.target.matches('input,textarea,select') || e.ctrlKey || e.metaKey || e.altKey) return;
      const c = data.items[cursor];
      if (['ArrowDown', 'j'].includes(e.key)) { e.preventDefault(); setCursor(cursor + 1); }
      else if (['ArrowUp', 'k'].includes(e.key)) { e.preventDefault(); setCursor(cursor - 1); }
      else if (e.key === 'o' && c?.website) window.open(c.website, '_blank', 'noopener,noreferrer');
      else if (e.key === 'b' && c?.status === 'neu') decideOne(c.id, 'uebernehmen');
      else if (e.key === 'v' && c?.status === 'neu') decideOne(c.id, 'verwerfen');
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
