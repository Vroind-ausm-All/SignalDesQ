'use strict';
// Sprint D: Angebots-Baukasten mit nachvollziehbaren Festpreisen. Positionen aus dem Leistungskatalog, Anreise und
// Tagespauschale; intern die vollständige Herleitung inkl. effektivem Stundenlohn. Ersetzt den bisherigen Paket-Rechner
// (gespeicherte alte Angebote werden weiterhin korrekt angezeigt).
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const money = v => euros(v).replace(/\s?€$/, ' €');
  const SIZE = {S: 'Basis', M: 'Standard', L: 'Umfangreich'};
  let cat = null, services = {}, positions = [], last = null, timer = null, posLead = null;

  // ------------------------------------------------------------ Katalog
  async function loadCatalog() {
    cat = await api('/pricing/catalog');
    services = {};
    cat.groups.forEach(g => g.services.forEach(s => { services[s.key] = {...s, group: g.group}; }));
    $('#qbService').innerHTML = cat.groups.map(g => `<optgroup label="${esc(g.group)}">${g.services.map(s => `<option value="${esc(s.key)}">${esc(s.title)}</option>`).join('')}</optgroup>`).join('');
    $('#qbRatePill').textContent = `${cat.settings.hourly_rate} €/h · Tag ${cat.settings.day_rate} €`;
    syncAddRow();
    renderSettings();
    renderCatalog();
  }

  function syncAddRow(rebuild = true) {
    const s = services[$('#qbService').value];
    if (!s) return;
    const sizeSel = $('#qbSize'), qty = $('#qbQty');
    sizeSel.classList.toggle('hidden', s.kind !== 'paket');
    qty.classList.toggle('hidden', !['menge', 'stunden', 'tag'].includes(s.kind));
    if (s.kind === 'paket' && rebuild) sizeSel.innerHTML = Object.entries(s.sizes).map(([k, v]) => `<option value="${k}" ${k === 'M' ? 'selected' : ''}>${SIZE[k]} · ${money(v.price_eur)}</option>`).join('');
    if (rebuild && ['menge'].includes(s.kind)) { qty.min = s.min_qty; qty.step = 1; qty.value = Math.max(s.min_qty, 1); }
    if (rebuild && s.kind === 'stunden') { qty.min = 0.5; qty.step = 0.5; qty.value = 4; }
    if (rebuild && s.kind === 'tag') { qty.min = 0.5; qty.step = 0.5; qty.value = 1; }
    const hint = s.kind === 'paket' ? s.sizes[sizeSel.value || 'M']?.scope : s.kind === 'menge' ? `je ${s.unit}: ${money(s.unit_values.price_eur)}` : s.description;
    $('#qbHint').textContent = (s.billing === 'monatlich' ? 'Monatliche Leistung · ' : '') + (hint || '');
  }

  function newPosition(key, opts = {}) {
    const s = services[key];
    const p = {service: key};
    if (s.kind === 'paket') p.size = opts.size || 'M';
    if (s.kind === 'menge') p.qty = opts.qty || Math.max(1, s.min_qty);
    if (s.kind === 'stunden') p.qty = opts.qty || 4;
    if (s.kind === 'tag') p.days = opts.days || 1;
    if (s.kind === 'anreise') Object.assign(p, {km: opts.km || 25, minutes: opts.minutes || 30, trips: opts.trips || 1});
    if (opts.title) p.title = opts.title;
    return p;
  }

  // ------------------------------------------------------------ Positionen
  function renderPositions() {
    const prices = last?.internal?.positions || [];
    $('#qbPositions').innerHTML = positions.length ? positions.map((p, i) => {
      const s = services[p.service] || {title: p.service, kind: ''};
      const pr = prices[i];
      let fields = '';
      if (s.kind === 'paket') fields = `<select data-qb-f="size" data-i="${i}" aria-label="Umfang">${Object.entries(s.sizes).map(([k, v]) => `<option value="${k}" ${p.size === k ? 'selected' : ''}>${SIZE[k]} – ${esc(v.scope.slice(0, 60))}</option>`).join('')}</select>`;
      if (['menge', 'stunden'].includes(s.kind)) fields = `<label>${esc(s.kind === 'stunden' ? 'Stunden' : s.unit)}<input type="number" data-qb-f="qty" data-i="${i}" value="${p.qty}" min="${s.kind === 'stunden' ? 0.5 : s.min_qty}" step="${s.kind === 'stunden' ? 0.5 : 1}"></label>`;
      if (s.kind === 'tag') fields = `<label>Tage<input type="number" data-qb-f="days" data-i="${i}" value="${p.days}" min="0.5" step="0.5"></label>`;
      if (s.kind === 'anreise') fields = `<label>km einfach<input type="number" data-qb-f="km" data-i="${i}" value="${p.km}" min="1" step="1"></label><label>Min. einfach<input type="number" data-qb-f="minutes" data-i="${i}" value="${p.minutes}" min="0" step="5"></label><label>Fahrten<input type="number" data-qb-f="trips" data-i="${i}" value="${p.trips}" min="1" step="1"></label>`;
      return `<div class="qb-pos"><span class="qb-n">${i + 1}</span><div class="qb-pos-main"><input class="qb-title" data-qb-f="title" data-i="${i}" value="${esc(p.title || s.title)}" maxlength="140" aria-label="Bezeichnung">
        <div class="qb-fields">${fields}</div>${pr ? `<small class="muted">${esc(pr.formula)}</small>` : ''}</div>
        <div class="qb-price">${pr ? `<b>${money(pr.price_eur)}</b>${s.billing === 'monatlich' ? '<small>/ Monat</small>' : ''}` : '<small>–</small>'}</div>
        <div class="qb-tools"><button type="button" class="text-button" data-qb-up="${i}" aria-label="nach oben" ${i ? '' : 'disabled'}>↑</button><button type="button" class="text-button" data-qb-del="${i}" aria-label="entfernen">✕</button></div></div>`;
    }).join('') : '<div class="empty">Noch keine Positionen. Leistung oben auswählen oder eine Vorlage laden.</div>';
  }

  function changed() {
    posLead = $('#quoteForm [name=lead_id]').value || posLead;
    renderPositions();
    clearTimeout(timer);
    timer = setTimeout(preview, 350);
  }

  function payload() {
    const f = $('#quoteForm').elements;
    const d = {positions, tax_mode: f.tax_mode.value, project_label: f.project_label.value.trim(), customer_goal: f.customer_goal.value.trim(), assumptions: f.assumptions.value.trim()};
    if (f.package.value) d.template = f.package.value;
    return d;
  }

  async function preview() {
    if (!positions.length) { last = null; renderPositions(); $('#quoteCustomer').innerHTML = '<p class="muted">Positionen hinzufügen.</p>'; return null; }
    try { last = await api('/pricing/preview', 'POST', payload()); renderPositions(); renderQuote(last); return last; }
    catch (e) { toast(e.message, true); return null; }
  }

  // ------------------------------------------------------------ Anzeige
  function renderQuote(q) {
    const c = q.customer, i = q.internal;
    const rows = c.positions.map((p, n) => `<tr><td>${n + 1}</td><td><b>${esc(p.title)}</b><small>${esc(p.scope)}${p.note ? ' · ' + esc(p.note) : ''}</small></td><td class="num">${money(p.price_eur)}${p.billing === 'monatlich' ? '<small>/ Monat</small>' : ''}</td></tr>`).join('');
    const vatOnce = c.tax_mode === 'regel_19';
    $('#quoteCustomer').innerHTML = `<div class="eyebrow">ENTWURF · FESTPREISE</div><h3>${esc(c.project_label)}</h3><p><strong>Ergebnis:</strong> ${esc(c.goal)}</p>
      <table class="qb-table"><thead><tr><th>Pos.</th><th>Leistung</th><th class="num">Festpreis netto</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="quote-total">${c.once_net_eur ? `<small>Einmalig netto</small><strong>${money(c.once_net_eur)}</strong>${vatOnce ? `<b>brutto ${money(c.once_net_eur * 1.19)}</b>` : ''}` : ''}
      ${c.monthly_net_eur ? `<small>Monatlich netto</small><strong>${money(c.monthly_net_eur)} / Monat</strong>${vatOnce ? `<b>brutto ${money(c.monthly_net_eur * 1.19)} / Monat</b>` : ''}` : ''}<small>${esc(c.tax_note)}</small></div>
      ${c.deliverables.length ? `<h4>Liefergegenstände</h4><ul>${c.deliverables.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${c.excluded.length ? `<h4>Nicht enthalten</h4><ul>${c.excluded.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${c.third_party_costs.length ? `<h4>Mögliche Kosten Dritter (nicht im Festpreis)</h4><ul>${c.third_party_costs.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${c.revision_note ? `<p class="muted"><b>Korrekturschleifen:</b> ${esc(c.revision_note)}</p>` : ''}
      <p class="muted">${esc(c.weeks)} · ${esc(c.payment_plan)}</p>`;
    $('#quoteInternal').innerHTML = `<div class="table-wrap"><table class="qb-table qb-internal"><thead><tr><th>Position</th><th class="num">Aufwand</th><th class="num">× Satz</th><th class="num">+ Puffer</th><th class="num">+ Fremdkosten</th><th class="num">= Festpreis</th><th class="num">€/h effektiv</th></tr></thead><tbody>
      ${i.positions.map(p => `<tr class="${p.effective_hourly !== null && p.effective_hourly < i.min_hourly_earning - 0.005 ? 'warn' : ''}"><td><b>${esc(p.title)}</b><small>${esc(p.formula)}${p.fixed ? ' · fester Preis' : ''}</small></td>
        <td class="num">${p.hours.toLocaleString('de-DE')} h</td><td class="num">${money(p.labor_eur)}</td><td class="num">${money(p.buffer_eur)}</td><td class="num">${money(p.external_eur)}</td><td class="num"><b>${money(p.price_eur)}</b></td><td class="num">${p.effective_hourly === null ? '–' : money(p.effective_hourly)}</td></tr>`).join('')}
      <tr class="sum"><td>Summe</td><td class="num">${i.estimated_hours.toLocaleString('de-DE')} h</td><td></td><td></td><td class="num">${money(i.external_cost_eur)}</td><td class="num">${money(i.total_price_eur)}</td><td class="num"><b>${i.effective_hourly === null ? '–' : money(i.effective_hourly)}</b></td></tr></tbody></table></div>
      <div class="qb-check ${i.ok ? 'ok' : 'warn'}">${i.ok ? `✓ Alle Positionen erreichen deinen Mindestverdienst von ${money(i.min_hourly_earning)} je Stunde.` : '! ' + i.warnings.map(esc).join('<br>! ')}</div>
      ${(i.open_points || []).length ? `<div class="qb-check warn qb-open">${i.open_points.map(x => '! ' + esc(x)).join('<br>')}</div>` : ''}
      ${(i.checks || []).length ? `<details class="qb-checks" open><summary>Vor dem Versand klären (je Leistungsbereich)</summary>${i.checks.map(c2 => `<h5>${esc(c2.label)}</h5><ul>${c2.items.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`).join('')}</details>` : ''}
      <p class="muted">${esc(i.basis)}. Monatliche Positionen sind je Monat gerechnet.${i.catalog_version ? ` Katalogstand ${esc(i.catalog_version)}.` : ''}</p>`;
  }

  // Gespeicherte Angebote: Baukasten-Angebote mit Positionen anzeigen, alte Paket-Angebote wie bisher
  const legacyRender = window.wsRenderQuote;
  window.wsRenderQuote = function (p) {
    if (p?.customer?.positions) { quoteLatest = p; return renderQuote(p); }
    return legacyRender(p);
  };
  const legacyOpen = window.wsOpenProposal;
  window.wsOpenProposal = async function (id) {
    await legacyOpen(id);
    try {
      const d = await api('/workspace/proposals/' + id);
      if (d.status === 'angenommen' && d.customer.billing === 'gemischt' && !$('#quoteSaved [data-mode=monat]')) {
        $('#quoteSaved').insertAdjacentHTML('beforeend', `<div class="sales-row"><button type="button" class="btn btn-ghost" data-quote-invoice="${id}" data-mode="monat">Monatsrechnung für die laufenden Positionen</button></div>`);
      }
    } catch { /* still */ }
  };

  window.quoteApplyTemplate = function (pkg, list) {
    const tpl = list && list.length ? list : (cat?.templates || {})[pkg];
    if (!tpl) return;
    positions = tpl.map(t => newPosition(t.service, t)).filter(Boolean);
    if (pkg && $('#quotePackage')) $('#quotePackage').value = pkg;
    changed();
  };

  // ------------------------------------------------------------ Grundlagen & Katalog bearbeiten
  const SETTINGS = [['hourly_rate', 'Kalkulations-Stundensatz (€/h)', 1], ['min_hourly_earning', 'Mindestverdienst (€/h)', 1], ['buffer_pct', 'Puffer (% auf Aufwand)', 1],
    ['day_rate', 'Tagespauschale vor Ort (€)', 1], ['half_day_rate', 'Halbtagespauschale (€)', 1], ['km_rate', 'Fahrtkosten je km (€)', 0.01],
    ['travel_time_pct', 'Fahrzeit berechnen zu (%)', 1], ['round_to', 'Aufrunden auf volle (€)', 1], ['experience_years', 'Jahre Erfahrung', 1],
    ['deposit_pct', 'Anzahlung bei Beauftragung (%, Vorgabe)', 1]];
  function renderSettings() {
    $('#qbSettings').innerHTML = `<div class="qb-set-grid">${SETTINGS.map(([k, l, step]) => `<label>${esc(l)}<input type="number" name="${k}" value="${cat.settings[k]}" step="${step}" min="0"></label>`).join('')}</div>
      <button type="submit" class="btn btn-primary">Grundlagen speichern</button>`;
  }
  function renderVorlagen() {
    const box = $('#qbVorlagen');
    if (!box || !cat.vorlagen) return;
    const price = v => [v.once_net_eur ? `${money(v.once_net_eur)} einmalig` : '', v.monthly_net_eur ? `${money(v.monthly_net_eur)} / Monat` : ''].filter(Boolean).join(' + ');
    const area = a => esc((cat.areas || {})[a] || a);
    box.innerHTML = `<div class="table-wrap"><table class="qb-table qb-tpl-table"><thead><tr><th>Vorlage</th><th>Positionen</th><th class="num">Preis netto</th><th>Zeitraum</th></tr></thead><tbody>
      ${cat.vorlagen.map(v => `<tr data-qb-vorlage="${esc(v.key)}"><td><b>${esc(v.title)}</b><small>${esc(v.outcome)}</small><small>${v.areas.map(area).join(' · ')}</small></td><td><ul class="qb-mini">${v.services.map(x => `<li>${esc(x)}</li>`).join('')}</ul></td><td class="num"><b>${price(v)}</b></td><td>${esc(v.weeks)}</td></tr>`).join('')}</tbody></table></div>
      ${cat.herkunft ? `<details class="qb-herkunft"><summary>Herkunft: bis 2.0.0-dev15 gab es vier getrennte Listen</summary><p class="muted">${esc(cat.herkunft.note)}</p>
        <div class="table-wrap"><table class="qb-table"><thead><tr><th>Vorlage heute</th><th>früher als Angebot</th><th>früher als Paket</th><th class="num">heute</th></tr></thead><tbody>
        ${cat.herkunft.vorlagen.map(r => `<tr><td><b>${esc(r.title)}</b><small>${esc(r.positions.join(' + '))}</small></td><td>${esc(r.former_offer || '–')}</td><td>${esc(r.former_package || '–')}</td><td class="num">${esc(r.price_now)}</td></tr>`).join('')}
        </tbody></table></div><p class="muted">Frühere Zusatzleistungen: ${cat.herkunft.zusatz.map(z => `${esc(z.title)} → ${esc(z.positions.join(' + '))}`).join(' · ')}. ${cat.herkunft.leistungen} Leistungen mit unveränderter Kennung.</p></details>` : ''}`;
  }
  function syncTemplateLabels() {  // Vorlagen-Auswahl im Angebot zeigt den aktuellen Katalogpreis
    (cat.vorlagen || []).forEach(v => {
      const opt = $('#quotePackage')?.querySelector(`option[value="${v.key}"]`);
      if (opt) opt.textContent = `${v.title} · ${[v.once_net_eur ? money(v.once_net_eur) + ' einmalig' : '', v.monthly_net_eur ? money(v.monthly_net_eur) + ' / Monat' : ''].filter(Boolean).join(' + ')} netto`;
    });
  }
  function renderCatalog() {
    $('#qbCatalogNotice').textContent = cat.notice;
    renderVorlagen();
    syncTemplateLabels();
    const revCell = (s, v) => s.korrekturen || v.revisions != null
      ? `<input type="number" name="revisions" value="${v.revisions ?? ''}" step="1" min="0" max="10" placeholder="offen" aria-label="Korrekturschleifen">` : '<span class="muted">–</span>';
    $('#qbCatalog').innerHTML = cat.groups.map(g => `<h4>${esc(g.group)}</h4><div class="table-wrap"><table class="qb-table qb-cat"><thead><tr><th>Leistung / Umfang</th><th class="num">Aufwand (h)</th><th class="num">Fremdkosten im Preis (€)</th><th class="num">Fester Preis (€, optional)</th><th class="num">Korrektur&shy;schleifen</th><th class="num">Preis</th><th class="num">€/h</th><th></th></tr></thead><tbody>
      ${g.services.filter(s => ['paket', 'menge'].includes(s.kind)).map(s => (s.kind === 'paket' ? Object.entries(s.sizes) : [['unit', {...s.unit_values, label: 'je ' + s.unit, scope: ''}]]).map(([size, v]) => `<tr data-qb-row="${esc(s.key)}" data-size="${size}" class="${v.customized ? 'custom' : ''}">
        <td><b>${esc(s.title)}</b> · ${esc(v.label)}<small>${esc(v.scope)}</small></td>
        <td class="num"><input type="number" name="hours" value="${v.hours}" step="0.5" min="0.1"></td><td class="num"><input type="number" name="external" value="${v.external}" step="10" min="0"></td>
        <td class="num"><input type="number" name="fixed_price" value="${v.fixed_price ?? ''}" step="10" min="1" placeholder="–"></td><td class="num">${revCell(s, v)}</td><td class="num">${money(v.price_eur)}</td><td class="num">${v.effective_hourly != null ? money(v.effective_hourly) : ''}</td>
        <td><button type="button" class="text-button" data-qb-save>Speichern</button>${v.customized ? '<button type="button" class="text-button" data-qb-reset>Startwert</button>' : ''}</td></tr>`).join('')).join('') || '<tr><td colspan="8" class="muted">Preise aus den Kalkulationsgrundlagen.</td></tr>'}</tbody></table></div>`).join('');
  }

  // ------------------------------------------------------------ Start
  function init() {
    if (!$('#qbPositions')) return;
    // 2.0.0-dev14: Kalkulationsgrundlagen und Katalog stehen unter Einstellungen – nur diese laden, nicht die ganze Angebotsansicht
    window.loadPricingSettings = async function () {
      try { if (!cat) await loadCatalog(); else { renderSettings(); renderCatalog(); } } catch (e) { toast(e.message, true); }
    };
    const origRefresh = window.refreshSalesQuotes;
    window.refreshSalesQuotes = async function () {
      await origRefresh();
      if (!cat) { try { await loadCatalog(); } catch (e) { toast(e.message, true); } }
      if (!$('#quotePackage').querySelector('option[value=""]')) $('#quotePackage').insertAdjacentHTML('afterbegin', '<option value="">– ohne Vorlage –</option>');
      renderPositions();
    };
    $('#qbService').addEventListener('change', () => syncAddRow(true));
    $('#qbSize').addEventListener('change', () => syncAddRow(false));
    $('#qbAdd').addEventListener('click', () => {
      const key = $('#qbService').value, s = services[key];
      const q = Number($('#qbQty').value);
      positions.push(newPosition(key, {size: $('#qbSize').value, qty: q, days: q}));
      changed();
    });
    $('#qbTemplate').addEventListener('click', () => { const v = $('#quotePackage').value; if (!v) return toast('Bitte eine Vorlage wählen', true); window.quoteApplyTemplate(v); });
    document.addEventListener('click', e => {
      const q = e.target.closest('[data-qb-quick]');
      if (q) { positions.push(newPosition(q.dataset.qbQuick)); return changed(); }
      const del = e.target.closest('[data-qb-del]');
      if (del) { positions.splice(Number(del.dataset.qbDel), 1); return changed(); }
      const up = e.target.closest('[data-qb-up]');
      if (up) { const i = Number(up.dataset.qbUp); [positions[i - 1], positions[i]] = [positions[i], positions[i - 1]]; return changed(); }
      const sv = e.target.closest('[data-qb-save],[data-qb-reset]');
      if (sv) {
        const row = sv.closest('[data-qb-row]');
        const num = n => { const el = row.querySelector(`[name=${n}]`); if (!el) return undefined; const v = el.value; return v === '' ? null : Number(v); };
        const body = {service: row.dataset.qbRow, size: row.dataset.size === 'unit' ? undefined : row.dataset.size};
        if (sv.matches('[data-qb-reset]')) body.reset = true; else Object.assign(body, {hours: num('hours'), external: num('external'), fixed_price: num('fixed_price'), revisions: num('revisions')});
        if (body.revisions === undefined) delete body.revisions;
        if (body.size === undefined) delete body.size;
        api('/pricing/overrides', 'PUT', body).then(c => { cat = c; renderCatalog(); syncAddRow(); toast('Katalogwert gespeichert – gilt für künftige Angebote und Empfehlungen'); preview(); window.refreshOffers?.().catch(() => {}); }).catch(err => toast(err.message, true));
      }
    });
    document.addEventListener('change', e => {
      const f = e.target.closest('[data-qb-f]');
      if (!f) return;
      const p = positions[Number(f.dataset.i)], k = f.dataset.qbF;
      p[k] = k === 'title' || k === 'size' ? f.value : Number(f.value);
      changed();
    });
    // Speichern/Berechnen des Formulars übernimmt der Baukasten (vor den Handlern des alten Paket-Rechners)
    document.addEventListener('click', e => {
      if (!e.target.closest('#quoteCalculate')) return;
      e.stopImmediatePropagation();
      preview();
    }, true);
    document.addEventListener('submit', async e => {
      if (e.target.id !== 'quoteForm') return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const leadId = Number($('#quoteForm [name=lead_id]').value);
      if (!leadId) return toast('Bitte Firma auswählen', true);
      if (!positions.length) return toast('Bitte mindestens eine Position hinzufügen', true);
      try {
        const ch = $('#quoteForm [name=opportunity_id]')?.value;  // 2.0.0-dev18: Chance des Angebots
        const saved = await api('/workspace/proposals', 'POST', {lead_id: leadId, ...payload(), ...(ch ? {opportunity_id: ch} : {})});
        toast('Angebotsentwurf gespeichert – noch nicht versendet');
        await window.refreshSalesQuotes();
        await window.wsOpenProposal(saved.id);
      } catch (err) { toast(err.message, true); }
    }, true);
    $('#quoteForm').addEventListener('change', e => { if (['tax_mode', 'project_label', 'customer_goal'].includes(e.target.name) && positions.length) changed(); });
    $('#quoteForm [name=lead_id]').addEventListener('change', e => {
      // Neue Firma: Positionen des vorherigen Angebots nicht übernehmen, sondern die passende Vorlage laden
      if (posLead && e.target.value && posLead !== e.target.value) { positions = []; last = null; renderPositions(); }
      setTimeout(() => { const pkg = $('#quotePackage').value; if (!positions.length && pkg && cat?.templates[pkg]) window.quoteApplyTemplate(pkg); }, 50);
    });
    $('#qbSettings').addEventListener('submit', async e => {
      e.preventDefault();
      const body = Object.fromEntries(SETTINGS.map(([k]) => [k, Number(e.target.elements[k].value)]));
      try { await api('/pricing/settings', 'PUT', body); await loadCatalog(); preview(); toast('Kalkulationsgrundlagen gespeichert'); window.refreshOffers?.().catch(() => {}); }
      catch (err) { toast(err.message, true); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
