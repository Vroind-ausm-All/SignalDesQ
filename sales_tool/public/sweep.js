'use strict';
// 2.0.0-dev44: Gründe für „ausgefiltert“ je Quelle und Hinweis, wenn Betriebe ohne Rechtsform den Großteil ausmachen.
const SW_WHY = {ohne_rechtsform: 'ohne Rechtsform', branche: 'andere Branche', plz: 'andere/unbekannte PLZ', entfernung: 'außerhalb des Umkreises',
  organisationsart: 'Organisationsart', nicht_operativ: 'Verwaltung/Holding'};
function whyText(why) {
  const parts = Object.entries(why || {}).filter(([, n]) => n).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${SW_WHY[k] || k}`);
  return parts.length ? ` (${escapeHTML(parts.join(', '))})` : '';
}
function soleHint(p) {
  const n = (p.filtered_why || {}).ohne_rechtsform || 0;
  return n && n >= (p.filtered || 0) / 2 ? `<div class="sales-banner sales-warning sw-sole-hint" data-sw-sole-hint>${n} Betriebe wurden ausgelassen, weil im Namen keine Rechtsform steht (z. B. „Elektro Müller“). Das betrifft vor allem Handwerk. Wenn du sie sehen willst: unter „Optionen“ „auch Betriebe ohne Rechtsform“ anhaken (oder „Handwerk &amp; lokale Betriebe“ wählen) und erneut suchen. Hinter solchen Namen kann eine Einzelperson stehen – nur geschäftlich nutzen.</div>` : '';
}
// Sprint B: „Arbeitstag starten“ – Sammelsuche über alle offenen Quellen, großer Import, Sichtung zum Durchklicken,
// Website-Suche mit Nachweis. Nichts wird kontaktiert; übernommene Firmen starten mit Rechtsstatus „unbekannt“.
// 2.0.0-dev51 (UX Schritt 3): Suchformular unter „Finden → Neue Suche“ (Branchen als Marken), Treffer unter „Finden → Sichten“ als
// Liste aus dem UI-Baukasten: Firma · Website · Entfernung · Quelle · Übernehmen · ›; ein Klick klappt alle weiteren Angaben und Aktionen auf.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const SRC = {gleif: 'GLEIF', gleif_csv: 'GLEIF-Import', liste: 'Eigene Liste', wikidata: 'Wikidata', osm: 'OpenStreetMap', ted: 'TED'};
  // Empfehlung A (v1.15): nur „belegt“, „laut Quelle“ oder von dir bestätigt gilt als Website der Firma – alles andere ist ein Vorschlag
  const WEB = {quelle: ['laut Quelle', 'ok'], belegt: ['belegt: Register und Gericht', 'ok'], bestaetigt: ['von dir bestätigt', 'ok'],
    wahrscheinlich: ['Vorschlag – bitte prüfen', 'mid'], nicht_bestaetigt: ['Vorschlag – nicht eindeutig', 'mid'], abgelehnt: ['Vorschlag abgelehnt', 'off'],
    wartet: ['Suche wartet …', 'wait'], laeuft: ['wird gesucht …', 'wait'], nicht_gefunden: ['nicht gefunden', 'off'], pruefung_fehlgeschlagen: ['Prüfung fehlgeschlagen – erneut versuchen', 'off']};
  // Kurzform für die Spalte „Website“: belegt (grün) · Vorschlag prüfen (gelb) · Suche läuft (blau) · keine
  const PILL = {ok: ['belegt', ' is-done'], mid: ['Vorschlag prüfen', ' is-attention'], wait: ['Suche läuft', ' is-underway']};
  const SUGGESTION = ['wahrscheinlich', 'nicht_bestaetigt'];
  const PAGE = 50;
  const KM = {minimumFractionDigits: 1, maximumFractionDigits: 1};
  const KIND = {verein: 'Verein/Stiftung', oeffentlich: 'öffentlich'};
  const CHECK = {ok: ['erreichbar', 'ok'], ueberlastet: ['überlastet', 'mid'], blockiert: ['blockiert', 'off'], fehler: ['Fehler', 'off'], format: ['Format geändert', 'off']};
  const COLS = 'minmax(0,2fr) 136px 88px minmax(0,1fr) 96px 12px';  // Firma · Website · Entfernung · Quelle · Übernehmen · ›
  const HIST_COLS = 'minmax(0,2fr) minmax(0,1.4fr) 96px 104px 168px 12px';  // Letzte Suchen · Ergebnis · Wann · Status · Aktionen · ›
  let catalog = null, labels = {}, selectedInd = new Set(), offset = 0, data = null, cursor = 0, chosen = new Set(), opened = new Set(), pollSweep = null, pollWeb = null;
  const store = {get: k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch { return null; } },
                 set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privat */ } }};
  const changed = () => document.dispatchEvent(new CustomEvent('signaldesk:swform'));  // Kurzstand und Voreinstellung neu zeigen (finden.js)

  // ------------------------------------------------------------ Branchen: gewählte als Marken, Auswahl im Menü darunter
  function renderIndustries() {
    const q = ($('#swIndSearch').value || '').toLowerCase();
    $('#swIndustries').innerHTML = catalog.groups.map(g => {
      const items = g.items.filter(i => !q || i.label.toLowerCase().includes(q) || g.group.toLowerCase().includes(q));
      if (!items.length) return '';
      return `<fieldset class="sw-group"><legend>${esc(g.group)}</legend>${items.map(i => `<label class="sw-chip ${selectedInd.has(i.key) ? 'on' : ''}"><input type="checkbox" data-ind="${esc(i.key)}" ${selectedInd.has(i.key) ? 'checked' : ''}> ${esc(i.label)}</label>`).join('')}</fieldset>`;
    }).join('') || '<div class="empty">Keine Branche gefunden – eigenes Stichwort unter „Optionen“ eintragen.</div>';
    const keys = [...selectedInd];
    $('#swIndChips').innerHTML = keys.slice(0, 4).map(k => `<span class="ui-chip">${esc(labels[k] || k)}<button type="button" class="fd-chip-x" data-ind-remove="${esc(k)}" aria-label="${esc(labels[k] || k)} entfernen">×</button></span>`).join('')
      + (keys.length > 4 ? `<span class="ui-chip fd-chip-more">+${keys.length - 4}</span>` : '');
    $('#swIndCount').textContent = keys.length ? '+ Branche' : 'alle Branchen – auswählen …';
    $('#swIndCount').title = keys.length ? `${keys.length} ausgewählt: ${keys.map(k => labels[k] || k).join(', ')}` : 'kein Filter nach Branche';
    changed();
  }

  // ------------------------------------------------------------ Sammelsuche
  function formParams() {
    const f = $('#swForm').elements;
    return {place: f.place.value.trim(), radius_km: Number(f.radius_km.value), industries: [...selectedInd], keywords: f.keywords.value.trim(),
      sources: $$('#swForm [name=src]:checked').map(x => x.value), operative: f.operative.checked, include_sole: f.include_sole.checked,
      find_websites: f.find_websites.checked, ted_nationwide: f.ted_nationwide.checked, osm_online: f.osm_online.checked,
      org_kinds: $$('#swForm [name=org]:checked').map(x => x.value),
      budget: {max_companies: Number(f.max_companies.value), max_websites: Number(f.max_websites.value), max_minutes: Number(f.max_minutes.value)}};
  }
  window.swFormParams = formParams;

  function renderProgress(sw) {
    const box = $('#swProgress');
    box.classList.remove('hidden');
    const area = sw.progress._area, web = sw.progress._web, bud = sw.progress._budget;
    const failed = Object.entries(sw.progress).filter(([k, p]) => !k.startsWith('_') && p.status === 'fehler').length;
    const done = !['queued', 'running'].includes(sw.status);
    const rows = Object.entries(sw.progress).filter(([k]) => !k.startsWith('_')).map(([k, p]) => `<div class="sw-src ${esc(p.status)}">
      <b>${esc(p.label || SRC[k] || k)}</b><span class="sw-st ${p.status === 'wartet' && p.detail ? 'retry' : ''}">${esc(p.status === 'wartet' && p.detail ? 'neuer Versuch …' : p.status || 'wartet')}</span>
      <small>${p.error ? `<span class="${p.status === 'fehler' ? 'late' : 'muted'}">${esc(p.error)}</span>` : `${p.new ?? 0} neu · ${p.merged ?? 0} zusammengeführt${p.possible ? ` · ${p.possible} mögliche Dublette(n)` : ''}${p.budget ? ` · <b>${p.budget} wegen Budget nicht übernommen</b>` : ''} · ${p.known ?? 0} schon bekannt · ${p.filtered ?? 0} ausgefiltert${whyText(p.filtered_why)}${p.detail ? ' · ' + esc(p.detail) : ''}`}</small>${soleHint(p)}</div>`).join('');
    const open = (sw.counts || {}).neu || 0;
    box.innerHTML = `<div class="sw-prog-head"><b>${esc(sw.label)}</b> <span class="muted">${area ? `Mittelpunkt ${esc(area.center)} · ${area.places} Orte im Umkreis (${esc(area.via)})` : 'Suchgebiet wird bestimmt …'}</span>
      <span class="sw-st ${esc(sw.status)}">${esc({queued: 'wartet', running: 'läuft', fertig: 'fertig', fehler: 'Fehler', abgebrochen: 'abgebrochen'}[sw.status] || sw.status)}</span>
      <span class="ui-sp"></span><button type="button" class="ui-txt" data-sw-show="${sw.id}">${open ? `${open} Treffer sichten →` : 'Sichten →'}</button></div>
      ${bud ? `<div class="sw-budget-line"><b>Budget</b> <span>${bud.companies ?? 0} / ${bud.max_companies} neue Firmen</span> · <span>höchstens ${bud.max_websites} Website-Suchen</span> · <span>${bud.minutes ?? 0} / ${bud.max_minutes} Min.</span> · <span class="muted">KI-Analysen nur auf Klick · keine externen Kosten</span></div>` : ''}${rows}
      ${web && web.queued ? `<div class="sw-src fertig"><b>Website-Suche</b><span class="sw-st">automatisch</span><small>${web.queued} Firmen ohne Website werden nacheinander gesucht (Nachweis per Impressum) – Status unter „Sichten“.</small></div>` : ''}
      ${done && failed ? `<div class="sw-retry"><button type="button" class="btn btn-ghost" data-sw-retry="${sw.id}">↻ Fehlgeschlagene Quellen erneut abfragen</button><span class="muted">Die Server von Wikidata/OpenStreetMap sind zeitweise überlastet – ein neuer Versuch einige Minuten später hilft meist. Schon gefundene Firmen bleiben erhalten.</span></div>` : ''}`;
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
      await loadHistory(); $('#swSweep').value = String(r.sweep_id); $('#swStatus').value = 'neu'; $('#swWeb').value = ''; offset = 0;
      if (currentView !== 'sichten') switchView('sichten'); else loadList();  // 2.0.0-dev51: Ergebnis gleich unter „Sichten“
    } catch (e) { toast(e.message, true); }
  }
  window.importCompanyFile = file => importFile(file);
  // v1.18: Formular aus einem Suchprofil füllen (Gebiet, Branchen, Quellen, Filter, Budget)
  window.swApplyParams = function (p, budget) {
    const f = $('#swForm').elements;
    f.place.value = p.place || ''; f.radius_km.value = String(p.radius_km ?? 30);
    f.keywords.value = Array.isArray(p.keywords) ? p.keywords.join(', ') : (p.keywords || '');
    $$('#swForm [name=src]').forEach(x => { x.checked = (p.sources || []).includes(x.value); });
    $$('#swForm [name=org]').forEach(x => { x.checked = (p.org_kinds || ['unternehmen']).includes(x.value); });
    f.operative.checked = p.operative !== false; f.include_sole.checked = p.include_sole !== false; f.find_websites.checked = p.find_websites !== false; f.osm_online.checked = !!p.osm_online;
    f.ted_nationwide.checked = !!p.ted_nationwide;
    if (budget) { f.max_companies.value = budget.max_companies; f.max_websites.value = budget.max_websites; f.max_minutes.value = budget.max_minutes; }
    selectedInd = new Set(p.industries || []);
    if (catalog) renderIndustries(); else changed();
  };
  window.swWatch = id => { $('#swGo').disabled = true; watchSweep(id); };

  // ------------------------------------------------------------ Sichtung
  function webCell(c) {
    const st = WEB[c.website_status] || (c.website ? WEB.quelle : null);
    const link = c.website ? `<a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer" data-sw-open>${esc(c.website.replace(/^https?:\/\//, ''))} ↗</a>` : '<span class="muted">keine Website bekannt</span>';
    const review = c.website && SUGGESTION.includes(c.website_status)
      ? ` <span class="sw-suggest"><button type="button" class="text-button" data-sw-web="bestaetigen" data-id="${c.id}">✓ Website passt</button><button type="button" class="text-button" data-sw-web="ablehnen" data-id="${c.id}">✕ passt nicht</button></span>` : '';
    return `${link}${st ? ` <span class="sw-web ${st[1]}" title="${esc(c.website_evidence)}">${esc(st[0])}</span>` : ''}${review}${c.website_evidence ? `<small> ${esc(c.website_evidence)}</small>` : ''}`;
  }
  function webPill(c) {
    const st = WEB[c.website_status] || (c.website ? WEB.quelle : null);
    const p = st && PILL[st[1]];
    if (p) return `<span class="ui-pill${p[1]}" title="${esc(st[0])}">${p[0]}</span>`;
    if (c.website_status === 'pruefung_fehlgeschlagen') return `<span class="ui-pill is-overdue" title="${esc(st[0])}">Prüfung fehlgeschlagen</span>`;
    return `<span class="muted"${st ? ` title="${esc(st[0])}"` : ''}>keine</span>`;
  }

  // v1.17: mögliche Dubletten stehen beim Haupteintrag – nie als eigener, doppelter Eintrag
  const addrOf = d => [d.street, [d.zip, d.city].filter(Boolean).join(' ')].filter(Boolean).join(', ');
  function dupLine(d, primaryName) {
    const facts = [d.legal_form && !d.name.toLowerCase().includes(String(d.legal_form).toLowerCase().replace(/\s*\(.*$/, '')) ? d.legal_form : '', addrOf(d) || 'ohne Ort',
      d.register_id, d.website ? d.website.replace(/^https?:\/\//, '') : '', (d.sources || []).map(s => SRC[s] || s).join(', ')].filter(Boolean);
    return `<div class="sw-dup" data-dup-id="${d.id}"><div><b>${esc(d.name)}</b> <small>${esc(facts.join(' · '))}</small>
      <small class="sw-dup-why">${esc(d.dup_reason || '')}${d.dup_score && !String(d.dup_reason || '').includes('%') ? ` · ${Math.round(d.dup_score * 100)} %` : ''}</small></div>
      <span class="sw-dup-btns"><button type="button" class="btn btn-ghost" data-sw-dup="gleich" data-id="${d.id}" title="${esc(d.name)} gehört zu ${esc(primaryName)} – zusammenführen">Gleiche Firma</button><button type="button" class="text-button" data-sw-dup="verschieden" data-id="${d.id}">Andere Firma</button></span></div>`;
  }
  const hasDup = c => c.status === 'neu' && (c.possible_duplicates?.length || c.duplicate_primary || c.possible_lead);
  function dupBlock(c) {
    if (c.status !== 'neu') return '';
    let out = '';
    if (c.possible_duplicates?.length) {
      out += `<div class="sw-dups"><span class="sw-dups-head">⚠ ${c.possible_duplicates.length === 1 ? 'Mögliche Dublette' : c.possible_duplicates.length + ' mögliche Dubletten'} – bitte entscheiden (nicht doppelt gelistet):</span>${c.possible_duplicates.map(d => dupLine(d, c.name)).join('')}</div>`;
    }
    if (c.duplicate_primary) {
      const p = c.duplicate_primary;
      out += `<div class="sw-dups"><span class="sw-dups-head">⚠ Evtl. dieselbe Firma wie <b>${esc(p.name)}</b> (${esc(addrOf(p) || 'ohne Ort')}) – ${esc(c.dup_reason || '')}</span>
        <span class="sw-dup-btns"><button type="button" class="btn btn-ghost" data-sw-dup="gleich" data-id="${c.id}">Gleiche Firma – zusammenführen</button><button type="button" class="text-button" data-sw-dup="verschieden" data-id="${c.id}">Andere Firma</button></span></div>`;
    }
    if (c.possible_lead) {
      out += `<div class="sw-dups lead"><span class="sw-dups-head">⚠ Evtl. schon als Firma vorhanden: <button type="button" class="text-button" data-lead="${c.possible_lead.id}">${esc(c.possible_lead.company)}</button> ${esc(c.possible_lead.location || '')} – ${esc((c.dup_reason || '').replace(/^evtl\. schon als Lead: /, ''))}</span>
        <span class="sw-dup-btns"><button type="button" class="btn btn-ghost" data-sw-dup="lead_gleich" data-id="${c.id}">Ist diese Firma</button><button type="button" class="text-button" data-sw-dup="lead_verschieden" data-id="${c.id}">Andere Firma</button></span></div>`;
    }
    return out;
  }

  // Zeile: Firma (+ Branche, „ohne Rechtsform“) · Website-Status · Entfernung · Quelle · „Übernehmen“ · ›; darunter die aufgeklappten Angaben
  function row(c, i) {
    const addr = addrOf(c);
    const contact = c.contact || {};
    const srcs = (c.sources || []).map(s => s.url ? `<a class="sw-srcchip" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(SRC[s.source] || s.source)}</a>` : `<span class="sw-srcchip">${esc(SRC[s.source] || s.source)}</span>`).join('');
    const names = [...new Set((c.sources || []).map(s => SRC[s.source] || s.source))];
    if (!names.length && c.source) names.push(SRC[c.source] || c.source);
    const open = c.status === 'neu', isOpen = opened.has(c.id);
    const branche = c.industry_label || c.industry || '';
    const sub = [KIND[c.org_kind] && c.source !== 'ted' ? KIND[c.org_kind] : '', branche, c.sole ? 'ohne Rechtsform' : '', c.city && !branche ? c.city : ''].filter(Boolean);
    const legal = c.legal_form && c.source !== 'ted' && !c.name.toLowerCase().includes(c.legal_form.toLowerCase().replace(/\s*\(.*$/, '')) ? c.legal_form : '';
    const facts = [legal, addr || c.city || '', c.distance_km != null ? `${c.distance_km.toLocaleString('de-DE', KM)} km` : '', c.register_id || '', branche].filter(Boolean);
    const state = {uebernommen: 'übernommen', verworfen: 'verworfen', dublette: 'schon Firma', gesperrt: 'Sperrliste', zusammengefuehrt: 'zusammengeführt'}[c.status] || c.status;
    const acts = open
      ? `<button type="button" class="btn btn-ghost fd-take-alt" data-sw-take="${c.id}">Übernehmen</button><button type="button" class="btn btn-ghost" data-sw-do="verwerfen" data-id="${c.id}">Verwerfen</button>${['belegt', 'quelle', 'bestaetigt', 'wartet', 'laeuft'].includes(c.website_status) ? '' : `<button type="button" class="text-button" data-sw-do="website" data-id="${c.id}">Website suchen</button>`}${['belegt', 'bestaetigt', 'wartet', 'laeuft'].includes(c.website_status) ? '' : `<button type="button" class="text-button" data-sw-do="website-eintragen" data-id="${c.id}">Website eintragen</button>`}`
      : `<span class="sw-st">${esc(state)}</span>${c.lead_id || c.duplicate_lead_id ? `<button type="button" class="text-button" data-lead="${c.lead_id || c.duplicate_lead_id}">Firma öffnen</button>` : ''}`;
    return `<article class="sw-item ${i === cursor ? 'cur' : ''} ${isOpen ? 'is-open' : ''}" data-sw-idx="${i}" data-id="${c.id}">
      <div class="ui-row fd-row" tabindex="0" aria-expanded="${isOpen}" aria-controls="swMore${c.id}">
        <div class="fd-firm"><input type="checkbox" data-sw-sel="${c.id}" ${chosen.has(c.id) ? 'checked' : ''} aria-label="${esc(c.name)} auswählen">
          <div class="ui-main sw-main"><b>${esc(c.name)}</b><small>${esc(sub.join(' · ') || ' ')}${hasDup(c) ? ' · <span class="fd-warn">⚠ mögliche Dublette</span>' : ''}</small></div></div>
        <div>${webPill(c)}</div>
        <div class="ui-num">${c.distance_km != null ? `${c.distance_km.toLocaleString('de-DE', KM)} km` : '<span class="muted">–</span>'}</div>
        <div class="ui-cut">${names.length ? `<span class="ui-pill">${esc(names[0])}</span>${names.length > 1 ? ` <small class="fd-more-src">+${names.length - 1}</small>` : ''}` : ''}</div>
        <div>${open ? `<button type="button" class="ui-txt" data-sw-do="uebernehmen" data-id="${c.id}">Übernehmen</button>` : `<span class="ui-small">${esc(state)}</span>`}</div>
        <div class="ui-chev" aria-hidden="true">›</div>
      </div>
      <div class="fd-more ${isOpen ? '' : 'hidden'}" id="swMore${c.id}">
        <small class="fd-facts">${esc(facts.join(' · '))}</small>
        <div class="sw-web-line">${webCell(c)}${contact.business_phone ? ` · ☎ ${esc(contact.business_phone)}` : ''}${contact.business_email ? ` · ✉ ${esc(contact.business_email)}` : ''}${contact.imprint_url ? ` · <a href="${esc(contact.imprint_url)}" target="_blank" rel="noopener noreferrer">Impressum ↗</a>` : ''}</div>
        <div class="sw-srcs">${srcs}${c.signal_note ? `<small>${esc(c.signal_note.slice(0, 140))}</small>` : ''}</div>${dupBlock(c)}
        <div class="sw-btns fd-acts">${acts}</div>
      </div>
    </article>`;
  }

  const activeView = () => {
    const st = $('#swStatus').value, web = $('#swWeb').value;
    return st === 'neu' && !web ? 'offen' : st === 'neu' && web === '1' ? 'website' : st === 'uebernommen' && !web ? 'uebernommen' : '';
  };
  function markViews() {
    const v = activeView();
    $$('#swViews [data-sw-view]').forEach(b => { const on = b.dataset.swView === v; b.classList.toggle('is-active', on); b.setAttribute('aria-pressed', String(on)); });
    // weitere Filter aktiv: „Filter ▾“ hervorheben
    const more = !v || $('#swSweep').value || $('#swCity').value || $('#swKm').value || $('#swNoTed').checked || $('#swSort').value !== 'distanz';
    $('#swFilterBtn').classList.toggle('is-active', !!more);
    $('#swSelInfo').textContent = `Ausgewählte (${chosen.size})`;
    $('#swBulkBtn').textContent = chosen.size ? `Auswahl (${chosen.size}) ▾` : 'Auswahl ▾';
  }

  async function loadList() {
    const dups = $('#swStatus').value === 'dups';
    const qs = new URLSearchParams({status: dups ? 'neu' : $('#swStatus').value, dups: dups ? '1' : '', sweep_id: $('#swSweep').value, website: $('#swWeb').value, sort: $('#swSort').value,
      q: $('#swQ').value.trim(), offset: String(offset), limit: String(PAGE), city: $('#swCity').value, max_km: $('#swKm').value,
      no_ted: $('#swNoTed').checked ? '1' : ''});
    [...qs.keys()].filter(k => !qs.get(k)).forEach(k => qs.delete(k));
    try {
      data = await api('/sweep-candidates?' + qs);
      cursor = Math.min(cursor, Math.max(0, data.items.length - 1));
      $('#swReview').style.setProperty('--ui-cols', COLS);  // Spalten per CSSOM (die CSP erlaubt keine style-Attribute)
      $('#swList').innerHTML = data.items.length ? data.items.map(row).join('')
        : `<div class="ui-empty">${$('#swStatus').value === 'neu' ? 'Nichts mehr zu sichten. Starte eine neue Suche oder importiere eine Firmenliste.' : 'Keine Einträge in diesem Filter.'}</div>`;
      const cur = $('#swCity').value;
      $('#swCity').innerHTML = '<option value="">alle Orte</option>' + (data.cities || []).map(x => `<option value="${esc(x.city)}">${esc(x.city)} (${x.n})</option>`).join('')
        + (cur && !(data.cities || []).some(x => x.city.toLowerCase() === cur.toLowerCase()) ? `<option value="${esc(cur)}">${esc(cur)}</option>` : '');
      $('#swCity').value = cur;
      const c = data.counts || {};
      window.findenOpen = c.neu || 0;  // Einstieg in „Finden“ (finden.js)
      const sweepOpt = $('#swSweep').selectedOptions[0];
      const label = $('#swSweep').value && sweepOpt ? sweepOpt.textContent.replace(/\s*\(\d+ offen\)$/, '') : 'Alle Suchen';
      $('#swCounts').innerHTML = `${esc(label)} · <b>${(c.neu || 0).toLocaleString('de-DE')}</b> offen`
        + (c.moegliche_dubletten ? ` · <button type="button" class="ui-txt" data-sw-dupview>${c.moegliche_dubletten} mögliche Dublette(n) prüfen</button>` : '')
        + (c.ohne_website ? ` · <button type="button" class="ui-txt" data-sw-noweb>${c.ohne_website} ohne Website</button>` : '');
      $('#swCountsAll').textContent = `Insgesamt: ${c.neu || 0} neu · ${c.uebernommen || 0} übernommen · ${c.verworfen || 0} verworfen · ${c.dublette || 0} schon als Firma`
        + (c.zusammengefuehrt ? ` · ${c.zusammengefuehrt} zusammengeführt` : '') + '.';
      $('#swCntOpen').textContent = String(c.neu || 0);
      $('#swCntWeb').textContent = String(Math.max(0, (c.neu || 0) - (c.ohne_website || 0)));
      $('#swCntTaken').textContent = String(c.uebernommen || 0);
      $('#swPage').textContent = data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} von ${data.total}` : '';
      $('#swPrev').disabled = offset === 0;
      $('#swNext').disabled = offset + PAGE >= data.total;
      $('#swPrev').closest('.sw-pager').classList.toggle('hidden', data.total <= PAGE);
      markViews();
      clearTimeout(pollWeb);
      if (data.items.some(x => ['wartet', 'laeuft'].includes(x.website_status))) pollWeb = setTimeout(loadList, 4000);
    } catch (e) { $('#swList').innerHTML = `<div class="ui-empty">${esc(e.message)}</div>`; }
  }
  window.swReloadList = () => loadList();

  async function loadHistory() {
    try {
      const rows = await api('/sweeps');
      const cur = $('#swSweep').value;
      $('#swSweep').innerHTML = '<option value="">Alle Suchläufe &amp; Importe</option>' + rows.map(r => `<option value="${r.id}">${esc(r.label)} (${r.open} offen)</option>`).join('');
      $('#swSweep').value = cur;
      $('#fdHist').style.setProperty('--ui-cols', HIST_COLS);
      const STATE = {queued: ['wartet', ' is-underway'], running: ['läuft', ' is-underway'], fertig: ['fertig', ' is-done'], fehler: ['Fehler', ' is-overdue'], abgebrochen: ['abgebrochen', '']};
      const srcOf = r => (r.params?.sources || (r.params?.source ? [r.params.source] : [])).map(s => SRC[s] || s).join(' · ');
      $('#swHistory').innerHTML = rows.length ? rows.slice(0, 12).map(r => `<div class="ui-row fd-hist-row" data-sw-show="${r.id}" tabindex="0">
        <div class="ui-main"><b>${esc(r.label)}</b><small>${esc(r.kind === 'import' ? 'Import' : srcOf(r) || 'Suche')}</small></div>
        <div class="ui-cut">${r.open} offen · ${r.taken} übernommen · ${r.dismissed} verworfen</div>
        <div class="ui-small">${esc(fmtDate(r.created_at.slice(0, 10)))}</div>
        <div><span class="ui-pill${(STATE[r.status] || ['', ''])[1]}">${esc((STATE[r.status] || [r.status])[0])}</span></div>
        <div class="fd-hist-acts"><button type="button" class="ui-txt" data-sw-show="${r.id}">Sichten</button>${r.kind === 'suche' ? ` <button type="button" class="ui-txt" data-sw-again="${r.id}">Erneut suchen</button>` : ''}</div>
        <div class="ui-chev" aria-hidden="true">›</div></div>`).join('')
        : '<div class="ui-empty">Noch keine Suche. Tipp: Arbeite dich systematisch durch PLZ-Gebiete – z. B. 70173, dann 71032, 71634 … jeweils 30 km.</div>';
      store.set('sw_history', rows.slice(0, 12).map(r => ({id: r.id, params: r.params})));
    } catch { /* ignoriert */ }
  }

  async function decideOne(id, decision) {
    try {
      const r = await api(`/sweep-candidates/${id}/decision`, 'POST', {decision});
      toast(decision === 'uebernehmen' ? `Als Firma übernommen (Rechtsstatus „unbekannt“)${r.auto_applied?.length ? ` · aus dem Impressum ergänzt: ${r.auto_applied.length} Feld(er)` : ''}` : 'Verworfen – erscheint nicht erneut');
      chosen.delete(id);
      opened.delete(id);
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
  function toggleRow(item) {
    const id = Number(item.dataset.id), more = item.querySelector('.fd-more'), on = !opened.has(id);
    on ? opened.add(id) : opened.delete(id);
    more.classList.toggle('hidden', !on);
    item.classList.toggle('is-open', on);
    item.querySelector('.fd-row').setAttribute('aria-expanded', String(on));
  }
  function showSweep(id) {
    $('#swSweep').value = String(id || ''); $('#swStatus').value = 'neu'; $('#swWeb').value = ''; offset = 0; cursor = 0;
    if (currentView !== 'sichten') switchView('sichten'); else loadList();
  }

  window.refreshSweep = async function () {
    if (!$('#swForm')) return;
    if (!catalog) {
      catalog = await api('/industries');
      catalog.groups.forEach(g => g.items.forEach(i => { labels[i.key] = i.label; }));
      const last = store.get('sw_last');
      if (last) {
        const f = $('#swForm').elements;
        f.place.value = last.place || ''; f.radius_km.value = String(last.radius_km ?? 30); f.keywords.value = last.keywords || '';
        if (last.find_websites === false) f.find_websites.checked = false;
        if (last.budget) { f.max_companies.value = last.budget.max_companies; f.max_websites.value = last.budget.max_websites; f.max_minutes.value = last.budget.max_minutes; }
        if (last.ted_nationwide) f.ted_nationwide.checked = true;
        if (Array.isArray(last.org_kinds) && last.org_kinds.length) $$('#swForm [name=org]').forEach(x => { x.checked = last.org_kinds.includes(x.value); });
        // 2.0.0-dev51: Quellen und Filter werden mitgemerkt – damit auch die gewählte Voreinstellung („Wen suchst du?“)
        if (Array.isArray(last.sources) && last.sources.length) $$('#swForm [name=src]').forEach(x => { x.checked = last.sources.includes(x.value); });
        if (last.include_sole === false) f.include_sole.checked = false;
        if (last.operative === false) f.operative.checked = false;
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
    $('#swIndChips').addEventListener('click', e => {
      const x = e.target.closest('[data-ind-remove]');
      if (!x) return;
      e.preventDefault();  // Marke entfernen, ohne die Auswahl aufzuklappen
      selectedInd.delete(x.dataset.indRemove); renderIndustries();
    });
    $('#swIndMenu').addEventListener('toggle', () => { if ($('#swIndMenu').open) setTimeout(() => $('#swIndSearch').focus(), 0); });
    $('#swForm').addEventListener('submit', async e => {
      e.preventDefault();
      const p = formParams();
      if (!p.sources.length) return toast('Mindestens eine Quelle wählen (unter „Quellen & Budget“)', true);
      if (!p.org_kinds.length) return toast('Bitte unter „Optionen“ wählen, wen du suchst (z. B. Unternehmen)', true);
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
        $('#swCheckSummary').textContent = `${r.ok} von ${r.total} erreichbar · geprüft ${r.checked_at}`;
      } catch (e) { $('#swCheckNote').textContent = e.message; }
      b.disabled = false;
    });
    $('#swDedupe').addEventListener('click', async () => {
      try {
        const r = await api('/sweep-candidates/dedupe', 'POST', {run: true});
        toast(`${r.checked} Treffer geprüft: ${r.merged} sicher gleiche zusammengeführt, ${r.possible} mögliche Dubletten zur Prüfung, ${r.known_lead + r.possible_lead} Bezug zu bestehenden Firmen`);
        loadList();
      } catch (e) { toast(e.message, true); }
    });
    $('#swFile').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) importFile(f); });
    ['#swStatus', '#swSweep', '#swWeb', '#swSort', '#swCity', '#swKm', '#swNoTed'].forEach(s => $(s).addEventListener('change', () => { offset = 0; cursor = 0; loadList(); }));
    $('#swFilterReset').addEventListener('click', () => {
      $('#swStatus').value = 'neu'; $('#swSweep').value = ''; $('#swWeb').value = ''; $('#swSort').value = 'distanz'; $('#swCity').value = ''; $('#swKm').value = '';
      $('#swNoTed').checked = false; $('#swQ').value = ''; offset = 0; cursor = 0; loadList();
    });
    $('#swViews').addEventListener('click', e => {
      const b = e.target.closest('[data-sw-view]');
      if (!b) return;
      const [st, web] = {offen: ['neu', ''], website: ['neu', '1'], uebernommen: ['uebernommen', '']}[b.dataset.swView];
      $('#swStatus').value = st; $('#swWeb').value = web; offset = 0; cursor = 0; loadList();
    });
    $('#fdNewSearch').addEventListener('click', () => switchView('finder'));
    let qt = null;
    $('#swQ').addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { offset = 0; loadList(); }, 300); });
    $('#swPrev').addEventListener('click', () => { offset = Math.max(0, offset - PAGE); cursor = 0; loadList(); });
    $('#swNext').addEventListener('click', () => { offset += PAGE; cursor = 0; loadList(); });
    $('#swAll').addEventListener('change', e => { (data?.items || []).forEach(c => e.target.checked ? chosen.add(c.id) : chosen.delete(c.id)); loadList(); });
    $('#swList').addEventListener('change', e => { const id = Number(e.target.dataset.swSel); if (id) { e.target.checked ? chosen.add(id) : chosen.delete(id); markViews(); } });
    $('#swList').addEventListener('keydown', e => {
      const r = e.target.closest('.fd-row');
      if (r && (e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); toggleRow(r.closest('.sw-item')); }
    });
    $('#swList').addEventListener('focusin', e => { const it = e.target.closest('.sw-item'); if (it && e.target.matches('.fd-row')) setCursor(Number(it.dataset.swIdx)); });
    $('#swHistory').addEventListener('keydown', e => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.fd-hist-row')) { e.preventDefault(); showSweep(e.target.dataset.swShow); }
    });
    document.body.addEventListener('click', async e => {
      const tk = e.target.closest('[data-sw-take]');
      if (tk) return decideOne(Number(tk.dataset.swTake), 'uebernehmen');
      const d = e.target.closest('[data-sw-do]');
      if (d) {
        const id = Number(d.dataset.id);
        if (d.dataset.swDo === 'website') { try { await api('/sweep-candidates/find-websites', 'POST', {ids: [id]}); loadList(); } catch (err) { toast(err.message, true); } return; }
        if (d.dataset.swDo === 'website-eintragen') {
          const url = prompt('Website-Adresse eingeben. Die Zuordnung bleibt bis zur Bestätigung ungeprüft:');
          if (url === null) return;
          try { await api(`/sweep-candidates/${id}/website`, 'POST', {url}); toast('Website eingetragen – bitte Zuordnung prüfen und bestätigen.'); loadList(); }
          catch (err) { toast(err.message, true); }
          return;
        }
        return decideOne(id, d.dataset.swDo);
      }
      const dp = e.target.closest('[data-sw-dup]');
      if (dp) {
        dp.disabled = true;
        try {
          await api(`/sweep-candidates/${dp.dataset.id}/duplicate`, 'POST', {decision: dp.dataset.swDup});
          toast({gleich: 'Zusammengeführt – Quellen und Angaben sind jetzt in einem Eintrag', verschieden: 'Als eigene Firma behalten – wird nicht wieder als Dublette vorgeschlagen',
            lead_gleich: 'Als „schon als Firma vorhanden“ markiert', lead_verschieden: 'Hinweis entfernt – eigene Firma'}[dp.dataset.swDup]);
          loadList();
        } catch (err) { dp.disabled = false; toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-sw-noweb]')) { $('#swStatus').value = 'neu'; $('#swWeb').value = '0'; offset = 0; cursor = 0; loadList(); return; }
      if (e.target.closest('[data-sw-dupview]')) { $('#swStatus').value = 'dups'; $('#swWeb').value = ''; offset = 0; cursor = 0; loadList(); return; }
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
      if (e.target.closest('#swTakeAll')) {
        const dups = $('#swStatus').value === 'dups';
        if (dups || $('#swStatus').value !== 'neu') return toast('Bitte zuerst die Ansicht „Offen“ wählen', true);
        const total = data?.total || 0;
        if (!total) return toast('Keine offenen Treffer in diesem Filter', true);
        const max = Math.min(total, 1000);
        if (!confirm(`${max.toLocaleString('de-DE')} Treffer des aktuellen Filters als Firmen übernehmen?${total > max ? ` (von ${total.toLocaleString('de-DE')}; je Durchgang höchstens 1.000)` : ''}\n\nGesperrte Firmen und Dubletten werden übersprungen. Übernommene Firmen starten mit Rechtsstatus „unbekannt“.`)) return;
        const filter = {sweep_id: $('#swSweep').value, website: $('#swWeb').value, q: $('#swQ').value.trim(), city: $('#swCity').value, max_km: $('#swKm').value, no_ted: $('#swNoTed').checked ? '1' : ''};
        Object.keys(filter).forEach(k => { if (!filter[k]) delete filter[k]; });
        try {
          const r = await api('/sweep-candidates/bulk-all', 'POST', {filter, decision: 'uebernehmen', max});
          toast(`${r.done.toLocaleString('de-DE')} übernommen${r.skipped ? ` · ${r.skipped} übersprungen (${r.errors[0] || ''})` : ''}${r.remaining ? ` · ${r.remaining.toLocaleString('de-DE')} noch offen` : ''}`);
          chosen.clear(); if (typeof reload === 'function') reload(); loadList();
        } catch (err) { toast(err.message, true); }
        return;
      }
      const b = e.target.closest('[data-sw-bulk]');
      if (b) {
        const ids = chosen.size ? [...chosen] : (b.dataset.swBulk === 'websites' ? (data?.items || []).filter(c => c.status === 'neu' && !['belegt', 'quelle', 'bestaetigt'].includes(c.website_status)).map(c => c.id) : []);
        if (!ids.length) return toast('Bitte Firmen auswählen (Kästchen vor dem Namen)', true);
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
      const ag = e.target.closest('[data-sw-again]');
      if (ag) {
        const h = (store.get('sw_history') || []).find(x => String(x.id) === ag.dataset.swAgain);
        if (h) { const f = $('#swForm').elements; f.place.value = h.params.place; f.radius_km.value = String(h.params.radius_km ?? 30); f.keywords.value = (h.params.keywords || []).join(', '); selectedInd = new Set(h.params.industries || []); renderIndustries(); window.scrollTo({top: 0, behavior: 'smooth'}); f.place.focus(); }
        return;
      }
      const sh = e.target.closest('[data-sw-show]');
      if (sh) return showSweep(sh.dataset.swShow);
      const it = e.target.closest('.sw-item');
      if (it && !e.target.closest('a,button,input,label')) { setCursor(Number(it.dataset.swIdx)); if (e.target.closest('.fd-row')) toggleRow(it); }
    });
    document.addEventListener('keydown', e => {
      if (currentView !== 'sichten' || !data || e.target.matches('input,textarea,select') || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.target.closest && e.target.closest('details.ui-menu')) return;
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
