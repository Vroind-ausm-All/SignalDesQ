'use strict';
// v1.18 (Masterplan 2.0, Sprint 5): Firmenakte – Ablauf Recherche → Kontaktweg → Gespräch → Termin → Bedarf → Angebot → Abschluss,
// nächster Schritt mit Direktsprung, Belegabdeckung, Freigabe „Bedarf bestätigt“ und Zeitleiste aus allen Modulen.
// Nichts wird versendet; Kontaktsperren gelten überall.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const qa = (sel, root) => [...root.querySelectorAll(sel)];
  const KIND_ICON = {aktivitaet: '✎', anruf: '☎', termin: '◷', angebot: '€', mail: '✉', aufgabe: '☐', bericht: '◎', beleg: '§', bewertung: '★',
    signal: '⚑', rechnung: '₠', fund: '⌕'};
  const NEED_SKIP = ['anreise', 'aufwand', 'tagessatz'];
  let catalog = null, file = null, filter = '', cdPoll = null;
  const CD_STATE = {uebernommen: ['übertragen', 'ok'], laeuft: ['wird gelesen …', 'wait'], vorschlag: ['Website bestätigen', 'mid'],
    ohne_website: ['keine Website', 'off'], kein_impressum: ['kein Impressum gefunden', 'mid'], fehler: ['nicht gelesen', 'bad'], offen: ['noch nicht gelesen', 'mid']};
  const CD_FIELDS = {legal_name: 'Firmenname', street: 'Straße', zip: 'PLZ', city: 'Ort', register_number: 'Registernr.', vat_id: 'USt-IdNr.',
    business_phone: 'Telefon', business_email: 'E-Mail'};

  // v1.19: Firmendaten aus dem Impressum – übertragen? wenn nein: warum, und was hilft
  function companyData(cd) {
    const st = CD_STATE[cd.state] || [cd.state, 'off'];
    const sug = cd.suggestion;
    return `<div class="lf-cd" id="lfCd"><div class="lf-cd-head"><b>Firmendaten aus dem Impressum</b><span class="sw-web ${st[1]}">${esc(st[0])}</span></div>
      <small>${esc(cd.detail)}</small>
      ${cd.filled.length ? `<small class="muted">Im Firmenprofil: ${cd.filled.map(k => esc(CD_FIELDS[k] || k)).join(', ')}${cd.imprint_url ? ` · <a href="${esc(cd.imprint_url)}" target="_blank" rel="noopener noreferrer">Impressum ↗</a>` : ''}</small>` : ''}
      ${sug ? `<div class="lf-cd-sug"><span>Website-Vorschlag: <a href="${esc(sug.website)}" target="_blank" rel="noopener noreferrer">${esc(sug.website.replace(/^https?:\/\//, ''))} ↗</a>
        <small>${esc(sug.evidence || '')}${sug.fields.length ? ` · ${sug.fields.length} Firmendaten schon gelesen` : ''}</small></span>
        <span class="acc-btn-group"><button type="button" class="btn btn-primary" data-lf-sug="bestaetigen">✓ Website passt – Daten übernehmen</button><button type="button" class="text-button" data-lf-sug="ablehnen">✕ passt nicht</button></span></div>` : ''}
      ${cd.can_run && cd.state !== 'laeuft' ? `<button type="button" class="text-button" data-lf-read>${cd.checked_at ? 'Impressum erneut lesen' : 'Impressum jetzt lesen'}</button>` : ''}
      ${cd.auto ? '' : '<small class="muted">Automatische Übertragung ist ausgeschaltet (Einstellungen → Sicherung & Zugang).</small>'}</div>`;
  }

  async function services() {
    if (!catalog) catalog = await api('/pricing/catalog');
    return catalog.groups.flatMap(g => g.services.filter(s => !NEED_SKIP.includes(s.key)).map(s => ({...s, group: g.group})));
  }

  function needRow(svcs, n = {}) {
    const opts = svcs.map(s => `<option value="${esc(s.key)}" ${n.service === s.key ? 'selected' : ''}>${esc(s.group)} · ${esc(s.title)}</option>`).join('');
    return `<div class="lf-need-row"><select data-need="service" aria-label="Leistung">${opts}</select>
      <select data-need="size" aria-label="Umfang"><option value="S">Basis</option><option value="M" selected>Standard</option><option value="L">Umfangreich</option></select>
      <input data-need="qty" type="number" min="1" max="500" value="${n.qty || 1}" aria-label="Menge" class="hidden">
      <button type="button" class="text-button" data-need-del aria-label="Leistung entfernen">✕</button></div>`;
  }

  function syncRow(row, svcs) {
    const s = svcs.find(x => x.key === row.querySelector('[data-need=service]').value);
    row.querySelector('[data-need=size]').classList.toggle('hidden', s?.kind !== 'paket');
    const q = row.querySelector('[data-need=qty]');
    q.classList.toggle('hidden', s?.kind !== 'menge');
    if (s?.kind === 'menge' && Number(q.value) < s.min_qty) q.value = s.min_qty;
  }

  function stepBar(steps) {
    return `<ol class="lf-steps">${steps.map(s => `<li class="${s.done ? 'done' : s.partial ? 'part' : ''}" title="${esc(s.detail)}"><span>${s.done ? '✓' : s.partial ? '◐' : '○'}</span><b>${esc(s.label)}</b><small>${esc(s.detail)}</small></li>`).join('')}</ol>`;
  }

  function coverage(c) {
    return `<div class="lf-cov"><div class="lf-cov-head"><b>Belegabdeckung ${c.pct} %</b><div class="lf-cov-bar"><i data-w="${c.pct}"></i></div></div>
      <ul>${c.items.map(i => `<li class="${i.value >= 1 ? 'ok' : i.value > 0 ? 'mid' : 'off'}"><span>${esc(i.label)}</span><small>${esc(i.detail)}</small>${i.value < 1 ? `<button type="button" class="text-button" data-lf-go='${esc(JSON.stringify(i.action))}'>${esc(i.action.label)}</button>` : ''}</li>`).join('')}</ul>
      <small class="muted">${esc(c.notice)}</small></div>`;
  }

  // 2.0.0-dev54 (UX Schritt 6): Verlauf als Liste im Reiter „Kontakt & Verlauf“ (bisher Zeitleiste im Überblick)
  function timeline(t) {
    const items = t.filter(e => !filter || e.kind === filter);
    const kinds = [...new Set(t.map(e => e.kind))];
    return `<div class="lf-tl-head"><h2 class="ui-section">Verlauf</h2><select id="lfFilter" aria-label="Verlauf filtern"><option value="">alles (${t.length})</option>${kinds.map(k => `<option value="${k}" ${k === filter ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select></div>
      <ol class="ui-list lf-tl">${items.slice(0, 80).map(e => `<li><span class="lf-ic" aria-hidden="true">${KIND_ICON[e.kind] || '•'}</span><div><b>${esc(e.title)}</b><small>${esc(e.at)}${e.detail ? ' · ' + esc(e.detail) : ''}</small></div></li>`).join('') || '<li class="ui-empty">Noch nichts dokumentiert.</li>'}</ol>`;
  }
  function drawTimeline() { const el = $('#lfTimeline'); if (el && file) el.innerHTML = timeline(file.timeline); }

  // 2.0.0-dev12: Firmenakte mit Reitern. 2.0.0-dev54: Kopf nach der Detailseiten-Regel (← Zurück, Titel, Phase, Zusatz, eine Hauptaktion).
  const TABS = ['ueberblick', 'kontakt', 'bedarf', 'recherche', 'stammdaten'];
  const panel = name => document.querySelector(`[data-lf-panel="${name}"]`);
  let headAction = null;
  const todayIso = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const shortDate = d => new Intl.DateTimeFormat('de-DE', {day: 'numeric', month: 'short'}).format(new Date(`${String(d).slice(0, 10)}T12:00:00`));
  const STAGE_TONE = s => (s === 'gewonnen' ? ' is-done' : ['verloren', 'gesperrt'].includes(s) ? ' is-overdue' : s === 'angebot' ? ' is-underway' : '');
  const stageName = s => (typeof stageNames !== 'undefined' && stageNames[s]) || s;

  function setTab(name, focus = false) {
    if (!TABS.includes(name)) name = 'ueberblick';
    for (const t of TABS) {
      const on = t === name, b = document.querySelector(`[data-lf-tab="${t}"]`);
      panel(t)?.classList.toggle('lf-panel-off', !on);
      if (b) { b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; if (on && focus) b.focus(); }
    }
    const scroller = $('#modal .modal');
    if (scroller) scroller.scrollTop = 0;
  }

  function resetTabs(existing) {
    const tabs = $('#leadTabs');
    if (!tabs) return;
    tabs.classList.toggle('hidden', !existing);
    tabs.closest('header')?.classList.toggle('with-tabs', !!existing);
    $('#lfHeadNext')?.classList.add('hidden');
    $('#modalPhase')?.classList.add('hidden');
    $('#modalLock')?.classList.add('hidden');
    headAction = null;
    if ($('#modalMeta')) $('#modalMeta').textContent = '';
    if ($('#modalEyebrow')) $('#modalEyebrow').textContent = existing ? 'Firmenakte' : 'Neue Firma';
    if (existing) setTab('ueberblick');
    else for (const t of TABS) panel(t)?.classList.toggle('lf-panel-off', t !== 'stammdaten');
  }

  // Hauptaktion passend zur Lage – nur vorhandene Aktionen: Gespräch ins Protokoll, bei Sperre/Verlust eine Notiz, nach Gewinn die Rechnung
  function mainAction(f) {
    const close = f.steps.find(s => s.key === 'abschluss');
    if (f.lock || f.lead.stage === 'verloren') return {act: 'notiz', label: 'Notiz erfassen'};
    if (close && close.partial && !close.done) return {action: close.action, label: close.action.label};
    return {act: 'gespraech', label: 'Gespräch notieren'};
  }

  function head(f, lead) {
    $('#modalTitle').textContent = f.lead.company;
    const ph = $('#modalPhase');
    if (ph) { ph.textContent = stageName(f.lead.stage); ph.className = 'ui-pill' + STAGE_TONE(f.lead.stage); ph.title = 'Phase'; }
    $('#modalLock')?.classList.toggle('hidden', !f.lock);
    $('#modalMeta').textContent = [f.lead.location, lead?.industry].filter(Boolean).join(' · ');
    headAction = mainAction(f);
    const btn = $('#lfHeadNext');
    if (btn) { btn.classList.remove('hidden'); btn.textContent = headAction.label; btn.title = f.lock ? 'Kontaktsperre: nur dokumentieren, nicht ansprechen' : ''; }
  }

  function noteAct(type) {
    setTab('kontakt');
    const form = $('#activityForm');
    if (!form) return;
    form.elements.activity_type.value = type;
    // nur vorbelegt, noch nichts eingegeben: gilt nicht als ungespeicherte Eingabe (Eingabeschutz fragt erst nach Text)
    if (!form.elements.detail.value.trim()) window.leadGuard?.rebase?.('activityForm');
    form.elements.detail.focus();
    form.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  window.leadTabs = {reset: resetTabs, show: setTab, reveal(el) { const p = el && el.closest('[data-lf-panel]'); if (p) setTab(p.dataset.lfPanel); }};

  function initTabs() {
    const tabs = $('#leadTabs');
    if (!tabs) return;
    tabs.addEventListener('click', e => { const b = e.target.closest('[data-lf-tab]'); if (b) setTab(b.dataset.lfTab); });
    tabs.addEventListener('keydown', e => {
      const cur = TABS.indexOf(document.activeElement?.dataset?.lfTab);
      if (cur < 0) return;
      const next = {ArrowRight: cur + 1, ArrowLeft: cur - 1, Home: 0, End: TABS.length - 1}[e.key];
      if (next === undefined) return;
      e.preventDefault();
      setTab(TABS[(next + TABS.length) % TABS.length], true);
    });
    $('#lfHeadNext')?.addEventListener('click', () => {
      if (!headAction) return;
      if (headAction.act) return noteAct(headAction.act);
      go(headAction.action);
    });
    // Kontakt & Verlauf: klar benannte Aktionen (Gespräch im Protokoll, Anruf/Mail/Termin unter Kontakt & Termine wie bisher)
    $('#lfPanelKontakt')?.addEventListener('click', e => {
      const b = e.target.closest('[data-lf-act]');
      if (!b || !currentLeadId) return;
      const a = b.dataset.lfAct;
      if (a === 'gespraech') return noteAct('gespraech');
      return go({view: 'workspace', section: a === 'termin' ? 'meeting' : 'contact', lead_id: currentLeadId});
    });
    $('#lfTimeline')?.addEventListener('change', e => { if (e.target.id === 'lfFilter') { filter = e.target.value; drawTimeline(); } });
  }

  // ---- Überblick: Vereinbart · Chancen · Klappzeilen; rechts Kontext und Phasen
  function dueText(d) {
    const t = todayIso();
    if (!d) return '<span class="muted">ohne Datum</span>';
    if (d < t) return `<span class="ui-pill is-overdue">überfällig seit ${esc(shortDate(d))}</span>`;
    if (d === t) return '<span class="ui-pill is-attention">fällig heute</span>';
    return `<span>fällig am ${esc(fmtDate(d))}</span>`;
  }

  function lastTalk(f) {
    return f.timeline.find(e => e.kind === 'anruf' || (e.kind === 'aktivitaet' && ['Gespräch', 'Anfrage'].includes(e.title)) || (e.kind === 'termin' && /erledigt/.test(e.detail)));
  }

  function agreed(f) {
    const step = f.lead.next_step, date = f.lead.next_date, talk = lastTalk(f);
    const task = f.open_tasks.find(t => t.due_date);
    let title, bits;
    if (step || date) {
      title = step || 'Termin ohne Beschreibung';
      bits = [dueText(date), 'eingetragen unter Stammdaten', talk ? `letztes Gespräch am ${esc(fmtDate(talk.at.slice(0, 10)))}` : 'noch kein Gespräch dokumentiert'];
    } else if (task) {
      title = task.title;
      bits = [dueText(task.due_date), 'offene Aufgabe zu dieser Firma'];
    } else {
      title = 'Noch nichts vereinbart';
      bits = [f.lead.stage === 'recherche' ? 'Nach dem ersten Kontakt hier den nächsten Schritt festhalten' : 'Nächsten Schritt mit Datum festhalten, damit die Firma nicht liegen bleibt'];
    }
    return `<section class="ui-card lf-agreed${step || date || task ? '' : ' is-empty'}" id="lfAgreed" aria-labelledby="lfAgreedK">
      <span class="ui-small" id="lfAgreedK">Vereinbart</span><b class="lf-agreed-t">${esc(title)}</b>
      <span class="lf-agreed-d">${bits.map(b => `<span>${b}</span>`).join('')}<button type="button" class="ui-txt" data-lf-next-edit>${step || date ? 'ändern' : 'Nächsten Schritt eintragen'}</button></span></section>`;
  }

  function chanceValue(c, lead) {
    const p = [...c.proposals].reverse().find(x => x.net_eur != null);
    if (p) return esc(euros(p.net_eur));
    if (c.is_first && lead && Number(lead.estimated_budget) > 0) return 'ca. ' + esc(euros(Number(lead.estimated_budget)));
    return '<span class="muted">–</span>';
  }

  function chanceList(list, lead) {
    const tone = s => (s === 'gewonnen' ? ' is-done' : s === 'verloren' ? ' is-overdue' : ' is-underway');
    const rows = list.map(c => `<div class="ui-row lf-ch-row" role="button" tabindex="0" data-lf-ch="${c.id}" aria-label="Chance ${esc(c.title)} öffnen">
        <span class="ui-main"><b>${esc(c.title)}</b><small>${c.need_confirmed && c.confirmed_at ? 'Bedarf bestätigt am ' + esc(fmtDate(String(c.confirmed_at).slice(0, 10))) : esc(c.offer_title || 'Bedarf noch offen')}</small></span>
        <span class="ui-cut">${c.next_step ? esc(c.next_step) : '<span class="muted">–</span>'}</span>
        <span>${c.next_date ? (c.next_date < todayIso() ? `<span class="ui-pill is-overdue">${esc(shortDate(c.next_date))}</span>` : c.next_date === todayIso() ? '<span class="ui-pill is-attention">heute</span>' : esc(shortDate(c.next_date))) : '<span class="muted">–</span>'}</span>
        <span><span class="ui-pill${tone(c.stage)}">${esc(c.stage_label)}</span></span><span class="ui-num">${chanceValue(c, lead)}</span><span class="ui-chev" aria-hidden="true">›</span></div>`).join('');
    return `<div class="ui-list lf-chances" id="lfChances" aria-label="Chancen"><div class="ui-row-head"><span>Chance</span><span>Nächster Schritt</span><span>Fällig</span><span>Status</span><span class="ui-num">Wert</span><span class="ui-sr">Öffnen</span></div>
      ${rows || '<div class="ui-empty">Noch keine Chance – sie entsteht mit dem ersten Angebot oder über „＋ Neue Chance“ im Reiter „Bedarf &amp; Angebot“. <button type="button" class="ui-txt" data-lf-tabjump="bedarf">Zu Bedarf &amp; Angebot</button></div>'}</div>`;
  }

  function needFold(need, svcs) {
    const state = need.confirmed ? `bestätigt am ${esc(fmtDate(need.confirmed_at.slice(0, 10)))}` : `noch nicht bestätigt · ${need.talks} Gespräch${need.talks === 1 ? '' : 'e'} dokumentiert`;
    return `<details class="ui-fold lf-need" id="lfNeed"><summary><b>Bedarf</b><span>${need.confirmed ? '<span class="sw-web ok">bestätigt</span> ' : ''}${state}</span></summary><div class="ui-fold-body">
      ${need.confirmed ? `<small>${esc(need.note)}</small><ul class="lf-need-list">${need.needs.map(x => `<li>${esc(svcs.find(s => s.key === x.service)?.title || x.service)}${x.size ? ' · ' + esc({S: 'Basis', M: 'Standard', L: 'Umfangreich'}[x.size]) : ''}${x.qty ? ' · ' + x.qty + '×' : ''}</li>`).join('')}</ul>
        <div class="acc-btn-group"><button type="button" class="btn btn-ghost" data-lf-quote>Angebot aus bestätigtem Bedarf</button><button type="button" class="text-button" data-lf-reopen>Bedarf neu klären</button></div>`
      : `<small class="muted">Manuelle Freigabe: erst nach einem dokumentierten Gespräch (${need.talks} vorhanden) und mit Problem und Ziel aus der Bedarfsanalyse (Reiter „Bedarf &amp; Angebot“). Ein Angebot gilt erst danach als „beim Kunden“.</small>
        ${file.lock ? '' : `<form id="lfNeedForm" class="lf-need-form">
          <label class="ui-field">Bestätigt<select name="via" id="lfNeedVia"><option value="gespraech">im Telefonat</option><option value="termin">im Termin</option><option value="schriftlich">schriftlich vom Kunden</option></select></label>
          <label class="ui-field">Was hat der Kunde bestätigt?<textarea name="note" id="lfNeedNote" rows="2" maxlength="1000" required placeholder="z. B. Website-Relaunch mit Anfrageformular bis März, Budget freigegeben"></textarea></label>
          <div class="lf-need-rows">${needRow(svcs)}</div><button type="button" class="text-button" data-need-add>+ weitere Leistung</button>
          <button type="submit" class="btn btn-ghost">Bedarf bestätigen</button></form>`}`}</div></details>`;
  }

  function folds(f, svcs) {
    const n = f.next, cov = f.coverage, item = k => cov.items.find(i => i.key === k) || {detail: ''};
    const fit = f.assessment?.fit, q = f.assessment?.qualification;
    const fitLabel = grade => (window.gradeLabel ? window.gradeLabel(grade) : (grade || 'offen'));
    const known = fit ? fit.criteria.filter(c => c.status !== 'unbekannt').length : 0;
    const cd = f.company_data, cdHint = cd.suggestion || cd.state === 'vorschlag';
    const sources = cov.items.filter(i => i.value >= 1).length;
    return `<div class="ui-list lf-folds">
      <details class="ui-fold${n.action ? ' ui-fold-act' : ''} lf-next${n.blocked ? ' blocked' : ''}" id="lfNext"><summary><b>Empfehlung</b><span>${esc(n.label)}${n.detail && !n.blocked ? ': ' + esc(n.detail) : ''}</span>${n.action ? `<button type="button" class="ui-txt" data-lf-go='${esc(JSON.stringify(n.action))}'>${esc(n.action.label)}</button>` : ''}</summary>
        <div class="ui-fold-body"><p class="ui-small">Vorschlag des Programms aus dem Ablauf – nicht mit dem Kunden vereinbart.${n.blocked ? ' ' + esc(n.detail) : ''}</p>${stepBar(f.steps)}</div></details>
      ${needFold(f.need, svcs)}
      ${f.assessment ? `<details class="ui-fold" id="lfFit"><summary><b>Passung ${fit.grade && fit.grade !== 'X' ? esc(fit.grade) : fit.grade === 'X' ? '✕' : '?'}</b><span>${esc(fitLabel(fit.grade))} · ${known} von ${fit.criteria.length} Kriterien bekannt · Qualifizierung: ${esc(q.status_label)}</span></summary>
        <div class="ui-fold-body">${window.renderAssessment ? window.renderAssessment(f.assessment) : ''}</div></details>` : ''}
      <details class="ui-fold" id="lfWeb"><summary><b>Website-Bewertung</b><span>${esc(item('website').detail)}</span></summary>
        <div class="ui-fold-body"><p class="ui-small">${f.lead.website ? `Website: <a href="${esc(f.lead.website)}" target="_blank" rel="noopener noreferrer">${esc(f.lead.website.replace(/^https?:\/\//, ''))} ↗</a> · ` : 'Noch keine Website eingetragen. '}Die vollständige Bewertung mit Kriterien und Belegen steht im Reiter „Recherche“.</p>
          <button type="button" class="ui-txt" data-lf-jump="leadScoreResult">Zur Website-Bewertung →</button></div></details>
      <details class="ui-fold" id="lfSrc"${cdHint ? ' open' : ''}><summary><b>Quellen &amp; Belege</b><span>${cdHint ? '<span class="ui-pill is-attention">Website bestätigen</span> ' : ''}Belegabdeckung ${cov.pct} % · ${sources} von ${cov.items.length} Bereichen belegt</span></summary>
        <div class="ui-fold-body lf-src">${companyData(cd)}${coverage(cov)}</div></details>
      <details class="ui-fold" id="lfSig"><summary><b>Kaufsignale</b><span>${esc(item('anlass').detail)}</span></summary>
        <div class="ui-fold-body"><p class="ui-small">Anlässe und Hypothesen mit Quelle – im Reiter „Recherche“ prüfen und verknüpfen.</p><button type="button" class="ui-txt" data-lf-jump="leadSignals">Zu den Kaufsignalen →</button></div></details>
      ${f.open_tasks.length ? `<details class="ui-fold" id="lfTasks"><summary><b>Offene Aufgaben</b><span>${f.open_tasks.length} offen${f.open_tasks[0].due_date ? ' · nächste ' + esc(fmtDate(f.open_tasks[0].due_date)) : ''}</span></summary>
        <div class="ui-fold-body lf-tasks">${f.open_tasks.map(t => `<div><span>${esc(t.title)}</span><small>${t.due_date ? esc(fmtDate(t.due_date)) : 'ohne Termin'}</small><button type="button" class="text-button" data-lf-done="${t.id}">erledigt</button></div>`).join('')}</div></details>` : ''}
    </div>`;
  }

  const PHASES = [['Recherche', ['recherche'], 'recherche'], ['Qualifiziert', ['qualifiziert', 'kontakt', 'antwort'], 'ueberblick'],
    ['Termin', ['termin'], 'kontakt'], ['Angebot', ['angebot'], 'bedarf'], ['Auftrag', ['gewonnen'], 'bedarf']];

  function side(f, lead) {
    const perm = f.lead.permission, route = f.lead.contact_route;
    const permTxt = (typeof permissionNames !== 'undefined' && permissionNames[perm]) || perm;
    const routeTxt = route && route !== 'unbekannt' ? ((typeof routeNames !== 'undefined' && routeNames[route]) || route) : '';
    const phone = lead?.business_phone || (f.assessment?.reachability?.channels || []).find(c => /telefon/i.test(c.label) && c.known)?.value || '';
    const talk = lastTalk(f);
    const last = lead?.last_contact || (talk ? talk.at.slice(0, 10) : '');
    const who = [lead?.contact_name, lead?.contact_role].filter(Boolean).join(', ');
    const cur = PHASES.findIndex(p => p[1].includes(f.lead.stage));
    const ended = ['verloren', 'gesperrt'].includes(f.lead.stage);
    const phases = PHASES.map(([label, , tab], i) => {
      const done = f.lead.stage === 'gewonnen' ? true : cur > i, now = cur === i && f.lead.stage !== 'gewonnen';
      return `<li class="qt-phase${done ? ' is-done' : ''}${now ? ' is-current' : ''}"${now ? ' aria-current="step"' : ''}><span class="qt-ico" aria-hidden="true">${done ? '✓' : i + 1}</span><button type="button" class="ui-txt" data-lf-tabjump="${tab}">${label}</button></li>`;
    }).join('') + (ended ? `<li class="qt-phase is-bad" aria-current="step"><span class="qt-ico" aria-hidden="true">✕</span><span>${esc(stageName(f.lead.stage))}</span></li>` : '');
    return `<aside class="ui-side" id="lfSide" aria-label="Kontext">
      <section class="ui-card lf-ctx" aria-labelledby="lfCtxTitle"><h2 class="ui-section" id="lfCtxTitle">Kontext</h2>
        ${f.lock ? `<div class="lf-lock" role="alert"><b>⛔ Kontaktsperre</b> Firma ist ${esc(f.lock)}. Anruf, Termin, Mail-Entwurf und Angebot sind gesperrt. Ein Widerspruch lässt sich immer dokumentieren.</div>` : ''}
        <dl class="lf-dl">
          <dt>Ansprechpartner</dt><dd>${who ? esc(who) : '<span class="muted">noch niemand eingetragen</span>'}</dd>
          <dt>Letzter Kontakt</dt><dd>${last ? esc(fmtDate(last)) + (talk && talk.at.slice(0, 10) === last ? ', ' + esc(talk.kind === 'anruf' ? 'Telefon' : talk.kind === 'termin' ? 'Termin' : talk.title) : '') : '<span class="muted">noch keiner</span>'}</dd>
          <dt>Kontaktstatus</dt><dd class="lf-perm">${f.lock ? '<span class="ui-pill is-overdue">gesperrt</span> ' : ''}${esc(permTxt)}${routeTxt ? ', ' + esc(routeTxt) : ''}${f.steps[1]?.done ? ' · <span class="sw-web ok">dokumentiert</span>' : ' · <span class="sw-web mid">Grundlage offen</span>'}
            <button type="button" class="ui-txt" data-lf-go='${esc(JSON.stringify({focus: 'permission'}))}'>prüfen</button></dd>
          <dt>Website</dt><dd>${f.lead.website ? `<a href="${esc(f.lead.website)}" target="_blank" rel="noopener noreferrer">${esc(f.lead.website.replace(/^https?:\/\//, '').replace(/\/$/, ''))}</a>` : '<span class="muted">–</span>'}</dd>
          <dt>Telefon</dt><dd>${phone ? esc(phone) : '<span class="muted">–</span>'}</dd>
        </dl></section>
      <section class="ui-card" aria-labelledby="lfPhTitle"><h2 class="ui-section" id="lfPhTitle">Verlauf</h2><ol class="qt-phases lf-phases">${phases}</ol></section>
    </aside>`;
  }

  function privacy(list) {
    return (list || []).map(p => `<div class="lf-privacy ui-card"><span><span class="sw-web wait">ohne Rechtsform</span> <b>Möglicher Personenbezug.</b></span>
          <small>Löschfrist bis ${esc(fmtDate(p.retention_until))} · ${p.art14_informed_at ? 'nach Art. 14 informiert am ' + esc(fmtDate(p.art14_informed_at)) : 'Art.-14-Hinweis spätestens beim ersten Kontakt'}</small>
          <span class="acc-btn-group"><button type="button" class="text-button" data-dc-art14="${p.id}">Hinweistext kopieren</button>${p.art14_informed_at ? '' : `<button type="button" class="text-button" data-dc-informed="${p.id}">Als informiert vermerken</button>`}<button type="button" class="text-button" data-dc-extend="${p.id}">Frist verlängern</button></span></div>`).join('');
  }

  let keepOpen = null;
  async function render(id) {
    const box = $('#leadFile');
    try {
      const [f, ch, svcs] = await Promise.all([api(`/leads/${id}/file`), api(`/leads/${id}/chances`).catch(() => ({chances: []})), services()]);
      if (currentLeadId !== id) return;
      file = f;
      const lead = (typeof leads !== 'undefined' ? leads : []).find(x => x.id === id);
      head(file, lead);
      const open = keepOpen === id ? new Set([...box.querySelectorAll('details[open][id]')].map(d => d.id)) : null;
      keepOpen = id;
      window.uiKeep(box, '#lfNeedForm textarea, #lfNeedForm select[name=via]', () => {
        box.innerHTML = `<div class="ui-with-side lf-over"><div class="lf-main">
            ${agreed(file)}${privacy(file.privacy)}${chanceList(ch.chances || [], lead)}${folds(file, svcs)}
          </div>${side(file, lead)}</div>`;
        if (open) for (const d of box.querySelectorAll('details[id]')) if (open.has(d.id)) d.open = true;
      });
      drawTimeline();
      box.classList.remove('hidden');
      applyDataWidths(box);
      qa('.lf-need-row', box).forEach(r => syncRow(r, svcs));
      clearTimeout(cdPoll);
      if (file.company_data.state === 'laeuft') cdPoll = setTimeout(() => { if (currentLeadId === id && !$('#modal').classList.contains('hidden')) render(id).then(() => { if (file.company_data.state !== 'laeuft' && typeof reload === 'function') reload(); }); }, 3000);
    } catch (e) { box.innerHTML = `<div class="ui-empty">${esc(e.message)}</div>`; box.classList.remove('hidden'); }
  }

  window.loadLeadFile = function (id) { filter = ''; keepOpen = null; return render(id); };
  window.refreshLeadFile = function () { if (currentLeadId && !$('#modal').classList.contains('hidden')) return render(currentLeadId); };

  function jumpTo(id) {
    const el = document.getElementById(id);
    if (!el) return;
    window.leadTabs.reveal(el);
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  async function go(action) {
    if (action.view === 'quote_from_need') return quoteFromNeed();
    if (action.focus === 'permission') { setTab('stammdaten'); $('#leadForm [name=permission]')?.focus(); $('#leadForm [name=permission]')?.scrollIntoView({behavior: 'smooth', block: 'center'}); return; }
    if (action.focus === 'need') { const d = $('#lfNeedForm')?.closest('details'); if (d) { setTab('ueberblick'); d.open = true; d.scrollIntoView({behavior: 'smooth', block: 'center'}); } else { setTab('bedarf'); $('#discoveryForm')?.scrollIntoView({behavior: 'smooth'}); } return; }
    if (action.view === 'signals' || action.view === 'accounting') { closeModal(); return switchView(action.view); }
    closeModal();
    return window.goAction(action);
  }

  async function quoteFromNeed() {
    try {
      const r = await api(`/leads/${currentLeadId}/quote-from-need`, 'POST', {});
      toast(`Angebotsentwurf ${r.number} aus bestätigtem Bedarf erstellt – prüfen, Steuerstatus setzen, manuell versenden`);
      closeModal();
      if (typeof reload === 'function') reload();
      window.goAction({view: 'quotes', ref: r.id, lead_id: currentLeadId});
    } catch (e) { toast(e.message, true); }
  }

  // Zeile der Chancenliste: Reiter „Bedarf & Angebot“ mit aufgeklappter Chance
  function openChance(cid) {
    setTab('bedarf');
    const d = document.querySelector(`#chList [data-ch="${cid}"]`);
    if (d) { d.open = true; d.scrollIntoView({behavior: 'smooth', block: 'start'}); }
  }

  function init() {
    initTabs();
    if (!$('#leadFile')) return;
    const box = $('#leadFile');
    box.addEventListener('click', async e => {
      const g = e.target.closest('[data-lf-go]');
      if (g) { e.preventDefault(); return go(JSON.parse(g.dataset.lfGo)); }
      const tj = e.target.closest('[data-lf-tabjump]');
      if (tj) { if (tj.dataset.lfTabjump === 'ueberblick') { const d = $('#lfFit'); if (d) { d.open = true; d.scrollIntoView({behavior: 'smooth', block: 'center'}); } } else setTab(tj.dataset.lfTabjump); return; }
      const j = e.target.closest('[data-lf-jump]');
      if (j) return jumpTo(j.dataset.lfJump);
      if (e.target.closest('[data-lf-next-edit]')) { setTab('stammdaten'); const i = $('#leadForm [name=next_step]'); i?.focus(); i?.scrollIntoView({behavior: 'smooth', block: 'center'}); return; }
      const row = e.target.closest('[data-lf-ch]');
      if (row) return openChance(row.dataset.lfCh);
      if (e.target.closest('[data-lf-quote]')) return quoteFromNeed();
      const sg = e.target.closest('[data-lf-sug]');
      if (sg) {
        try {
          const r = await api(`/leads/${currentLeadId}/website-suggestion`, 'POST', {decision: sg.dataset.lfSug});
          toast(sg.dataset.lfSug === 'bestaetigen' ? (r.queued ? 'Website bestätigt – Impressum wird gelesen und ins Firmenprofil übertragen' : 'Website bestätigt – Firmendaten übertragen')
            : 'Vorschlag abgelehnt – diese Domain wird nicht wieder vorgeschlagen');
          if (typeof reload === 'function') await reload();
          const lead = leads.find(x => x.id === currentLeadId);
          if (lead && $('#leadForm')) for (const k of ['website', 'location']) if ($('#leadForm').elements[k]) $('#leadForm').elements[k].value = lead[k] || '';
          render(currentLeadId);
          if (window.loadCompanyFacts) window.loadCompanyFacts(currentLeadId);
        } catch (err) { toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-lf-read]')) {
        try { await api(`/leads/${currentLeadId}/company-data/read`, 'POST', {}); toast('Impressum wird gelesen – Firmendaten kommen in leere Felder'); render(currentLeadId); }
        catch (err) { toast(err.message, true); }
        return;
      }
      if (e.target.closest('[data-need-add]')) { const svcs = await services(); box.querySelector('.lf-need-rows').insertAdjacentHTML('beforeend', needRow(svcs)); qa('.lf-need-row', box).forEach(r => syncRow(r, svcs)); return; }
      const del = e.target.closest('[data-need-del]');
      if (del) { if (qa('.lf-need-row', box).length > 1) del.closest('.lf-need-row').remove(); return; }
      if (e.target.closest('[data-lf-reopen]')) {
        const reason = prompt('Warum wird der Bedarf neu geklärt?');
        if (!reason) return;
        try { await api(`/leads/${currentLeadId}/need/reopen`, 'POST', {reason}); toast('Bedarf wieder offen'); render(currentLeadId); } catch (err) { toast(err.message, true); }
        return;
      }
      const d = e.target.closest('[data-lf-done]');
      if (d) { try { await api(`/tasks/${d.dataset.lfDone}`, 'PATCH', {done: true}); render(currentLeadId); } catch (err) { toast(err.message, true); } }
    });
    box.addEventListener('keydown', e => {
      const row = e.target.closest?.('[data-lf-ch]');
      if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openChance(row.dataset.lfCh); }
    });
    box.addEventListener('change', async e => {
      if (e.target.dataset.need === 'service') syncRow(e.target.closest('.lf-need-row'), await services());
    });
    box.addEventListener('submit', async e => {
      if (e.target.id !== 'lfNeedForm') return;
      e.preventDefault();
      const f = e.target.elements, svcs = await services();
      const needs = qa('.lf-need-row', e.target).map(r => {
        const key = r.querySelector('[data-need=service]').value, s = svcs.find(x => x.key === key);
        return s.kind === 'paket' ? {service: key, size: r.querySelector('[data-need=size]').value} : s.kind === 'menge' ? {service: key, qty: Number(r.querySelector('[data-need=qty]').value)} : {service: key};
      });
      try {
        await api(`/leads/${currentLeadId}/need/confirm`, 'POST', {via: f.via.value, note: f.note.value.trim(), needs});
        toast('Bedarf bestätigt – Folgeaufgabe „Festpreisangebot erstellen“ angelegt');
        render(currentLeadId);
        if (typeof reload === 'function') reload();
      } catch (err) { toast(err.message, true); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
