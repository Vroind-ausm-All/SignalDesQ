'use strict';
// 2.0.0-dev52 (UX Schritt 4): Bereich „Angebote“ auf dem UI-Baukasten.
// - Angebote (#/angebote): Liste mit Suche, Ansichten (Alle · Offen · Angenommen) und „Filter ▾“. Spalten Angebot · Nächster Schritt ·
//   Fällig · Status · Betrag netto · ›. „Nächster Schritt“ und „Fällig“ kommen nur aus vorhandenen Daten (Status, Freigabe, Bindefrist,
//   offenes Nachfassen, Kick-off- und Abnahmestand, Betreuung); wo nichts vorliegt, steht „–“.
// - „＋ Neues Angebot“ öffnet den vorhandenen Editor als eigene Ansicht (#/angebote?neu=1); Speichern führt ins geöffnete Angebot.
// - Ein geöffnetes Angebot (#/angebote?angebot=ID) ist ein Arbeitsplatz: Kopf mit „← Angebote“, Titel, Status und genau einer Hauptaktion
//   zur aktuellen Phase; Reiter Positionen · Kundenvorschau · Interne Kalkulation · Verlauf; rechts „Prüfung vor Freigabe“ und „Ablauf“.
//   Die Arbeitsschritte (Freigabe, Versand, Nachfassen, Entscheidung, Projektstart, Kick-off, Übergabe) bleiben die aus offerflow.js –
//   unverändert in ihren Regeln. Die Hauptaktion springt nur zum passenden Schritt; sie gibt nichts frei und dokumentiert nichts.
// - Aufträge & Betreuung (#/angebote/auftraege) listet angenommene Angebote mit Kick-off und Abnahme.
// Server und Datenmodell bleiben unverändert.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const money = v => euros(v).replace(/\s?€$/, ' €');
  const byId = id => document.getElementById(id);
  const isoToday = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const shortDate = iso => (iso ? new Date(`${String(iso).slice(0, 10)}T12:00:00`).toLocaleDateString('de-DE', {day: 'numeric', month: 'short'}) : '');
  const longDate = iso => (iso ? new Date(`${String(iso).slice(0, 10)}T12:00:00`).toLocaleDateString('de-DE', {day: 'numeric', month: 'short', year: 'numeric'}) : '');
  const PANES = {list: 'qtList', edit: 'qtEdit', offer: 'qtOffer'};
  const STATUS = {entwurf: ['Entwurf', ''], freigegeben: ['freigegeben', 'is-attention'], gesendet_manuell: ['gesendet', 'is-underway'],
    angenommen: ['angenommen', 'is-done'], abgelehnt: ['abgelehnt', 'is-overdue'], ersetzt: ['ersetzt', '']};
  let mode = 'list', opening = false, preset = 'alle', rows = [], facts = {versand: new Map(), follow: new Map(), project: new Map(), care: new Map()};
  let offerId = null, tab = 'positionen', seq = 0;

  // ------------------------------------------------------------ Ansicht innerhalb von „Angebote“
  function setMode(m) {
    mode = m;
    const page = byId('viewQuotes');
    if (!page) return;
    page.dataset.qtMode = m;
    Object.entries(PANES).forEach(([k, id]) => byId(id).classList.toggle('hidden', k !== m));
    // Kundenvorschau und Kalkulation gibt es einmal: im Editor neben dem Formular, im Angebot als Reiter
    const [c, i] = m === 'edit' ? ['qtSlotEditCustomer', 'qtSlotEditInternal'] : ['qtSlotCustomer', 'qtSlotInternal'];
    if (m !== 'list') { byId(c).append(byId('quoteCustomer')); byId(i).append(byId('quoteInternal')); }
  }
  const inQuotes = () => typeof currentView !== 'undefined' && currentView === 'quotes';
  function ensureView() {
    if (inQuotes()) return;
    opening = true;
    try { window.switchView('quotes'); } finally { opening = false; }
  }

  function showList() {
    offerId = null;
    setMode('list');
    renderList();
  }

  function editTitle() {
    const f = byId('quoteForm');
    if (!f) return;
    const rev = f.dataset.revisionOf, add = f.dataset.addendumOf;
    byId('qtEditTitle').textContent = rev ? 'Angebot überarbeiten' : add ? 'Zusatzauftrag' : 'Neues Angebot';
    byId('qtEditMeta').textContent = rev ? `Überarbeitung von ${byId('qbRevisionOf').textContent} – Entwurf` : add ? `Zusatzauftrag ${byId('qbAddendumOf').textContent} – Entwurf` : 'Entwurf – noch nicht gespeichert';
  }

  function showEdit(push = true) {
    ensureView();
    offerId = null;
    setMode('edit');
    editTitle();
    const target = window.signalNav ? window.signalNav.build('quotes', new URLSearchParams('neu=1')) : '#/angebote?neu=1';
    if (push && location.hash !== target) history.pushState(null, '', target);
    window.scrollTo({top: 0, behavior: 'instant'});
  }

  // ------------------------------------------------------------ Liste: nächster Schritt und Fälligkeit aus vorhandenen Daten
  async function gather(list) {
    const drafts = list.filter(r => r.status === 'entwurf' && !r.superseded);
    const [tasks, best, vs] = await Promise.all([
      api('/tasks').catch(() => []),
      api('/bestand').catch(() => ({firms: []})),
      Promise.all(drafts.map(r => api(`/workspace/proposals/${r.id}/versand`).catch(() => null))),
    ]);
    const f = {versand: new Map(), follow: new Map(), project: new Map(), care: new Map()};
    drafts.forEach((r, n) => { if (vs[n]) f.versand.set(r.id, vs[n]); });
    (tasks || []).filter(t => !t.done && t.proposal_id && t.action_type === 'followup').forEach(t => {
      const old = f.follow.get(t.proposal_id);
      if (!old || (t.due_date || '9999') < (old.due_date || '9999')) f.follow.set(t.proposal_id, t);
    });
    (best.firms || []).forEach(firm => {
      firm.projects.forEach(p => f.project.set(p.proposal_id, p));
      firm.care.forEach(k => f.care.set(k.proposal_id, k));
    });
    return f;
  }

  function info(r) {
    const v = facts.versand.get(r.id), fu = facts.follow.get(r.id), pr = facts.project.get(r.id), care = facts.care.get(r.id);
    if (r.superseded) return {step: '–', due: '', key: 'ersetzt'};
    if (r.status === 'entwurf') {
      const released = !!(v && v.released && !v.stand_changed);
      const open = v ? v.checks.filter(c => !c.ok).length : 0;
      return {step: released ? 'Als gesendet markieren' : open ? `Prüfpunkte klären: ${open} offen` : 'Zur Freigabe prüfen', due: r.valid_until, key: released ? 'freigegeben' : 'entwurf'};
    }
    if (r.status === 'gesendet_manuell') {
      if (fu) return {step: 'Nachfassen' + (fu.reason ? `: ${fu.reason}` : ''), due: fu.due_date, key: 'gesendet_manuell'};
      return {step: 'Entscheidung dokumentieren', due: r.valid_until, key: 'gesendet_manuell'};
    }
    if (r.status === 'angenommen') {
      if (care && !pr) return {step: care.due_months.length ? `Monatsrechnung ${care.due_labels[0]} offen` : 'Betreuung läuft', due: '', key: 'angenommen', monthly: care.monthly_net_eur};
      if (pr && pr.kickoff.status !== 'gestartet') return {step: `Kick-off: ${pr.kickoff.label}`, due: '', key: 'angenommen'};
      if (pr && pr.handover.status !== 'abgenommen') return {step: `Übergabe & Abnahme: ${pr.handover.label}`, due: '', key: 'angenommen'};
      // SDQ-001: Abschlag oder Entwurf heißt noch nicht abgerechnet
      if (!r.invoiced && r.billing?.state === 'teilweise') return {step: `Schlussrechnung: ${money(r.billing.remaining_net_cents / 100)} netto offen`, due: '', key: 'angenommen'};
      if (!r.invoiced && r.billing?.state === 'entwurf') return {step: 'Rechnungsentwurf festschreiben', due: '', key: 'angenommen'};
      if (!r.invoiced) return {step: 'Rechnung erstellen', due: '', key: 'angenommen'};
      return {step: '–', due: '', key: 'angenommen'};
    }
    return {step: '–', due: '', key: r.status in STATUS ? r.status : 'entwurf'};
  }

  function duePill(iso) {
    if (!iso) return '<span class="ui-small">–</span>';
    const t = isoToday();
    if (iso < t) return `<span class="ui-pill is-overdue" title="überfällig seit ${esc(longDate(iso))}">${esc(shortDate(iso))}</span>`;
    if (iso === t) return '<span class="ui-pill is-attention">heute</span>';
    return `<span class="ui-small qt-date">${esc(shortDate(iso))}</span>`;
  }
  const pill = key => { const [label, cls] = STATUS[key] || [key, '']; return `<span class="ui-pill ${cls}">${esc(label)}</span>`; };

  function matches(r, i) {
    const q = (byId('qtQ')?.value || '').trim().toLowerCase();
    if (q && ![r.project_label, r.company, r.number].some(x => String(x || '').toLowerCase().includes(q))) return false;
    if (preset === 'offen' && !(['entwurf', 'gesendet_manuell'].includes(r.status) && !r.superseded)) return false;
    if (preset === 'angenommen' && !(r.status === 'angenommen' && !r.superseded)) return false;
    const st = byId('qtStatus')?.value;
    if (st === 'gesendet' && i.key !== 'gesendet_manuell') return false;
    if (st && st !== 'gesendet' && i.key !== st) return false;
    if (byId('qtExpired')?.checked && !r.expired) return false;
    if (byId('qtUnbilled')?.checked && !(r.status === 'angenommen' && !r.superseded && !r.invoiced)) return false;
    if (byId('qtHideOld')?.checked && r.superseded) return false;
    return true;
  }

  function rowHtml(r) {
    const i = info(r);
    const amount = i.monthly ? `${money(i.monthly)} / Monat` : money(r.net_eur);
    return `<div class="ui-row qt-row" role="listitem" tabindex="0" data-quote-open="${r.id}" aria-label="${esc(`${r.project_label} · ${r.company} · ${r.number}`)}">
      <div class="ui-main"><b>${esc(r.project_label || r.number)}</b><small>${esc(r.company)} · ${esc(r.number)}${r.revision_no > 1 ? ` · Fassung ${r.revision_no}` : ''}${r.addendum_no ? ' · Zusatzauftrag' : ''}</small></div>
      <span class="ui-cut" data-qt-step>${esc(i.step)}</span>
      <span>${duePill(i.due)}</span>
      <span>${pill(i.key)}${r.expired ? ' <span class="ui-pill is-overdue">Bindefrist abgelaufen</span>' : ''}</span>
      <span class="ui-num">${esc(amount)}</span><span class="ui-chev" aria-hidden="true">›</span></div>`;
  }

  function renderList() {
    const box = byId('quoteHistory');
    if (!box) return;
    const live = rows.filter(r => !r.superseded);
    const cnt = {alle: rows.length, offen: live.filter(r => ['entwurf', 'gesendet_manuell'].includes(r.status)).length, angenommen: live.filter(r => r.status === 'angenommen').length};
    document.querySelectorAll('[data-qt-cnt]').forEach(s => { s.textContent = cnt[s.dataset.qtCnt] ?? ''; });
    document.querySelectorAll('[data-qt-view]').forEach(b => { const on = b.dataset.qtView === preset; b.classList.toggle('is-active', on); b.setAttribute('aria-pressed', String(on)); });
    const shown = rows.filter(r => matches(r, info(r)));
    const filtered = !!(byId('qtStatus')?.value || byId('qtExpired')?.checked || byId('qtUnbilled')?.checked || byId('qtHideOld')?.checked);
    byId('qtFilterBtn')?.classList.toggle('is-active', filtered);
    byId('qtCount').textContent = shown.length === rows.length ? `${rows.length} ${rows.length === 1 ? 'Angebot' : 'Angebote'}` : `${shown.length} von ${rows.length} Angeboten`;
    // 2.0.0-dev53: die Liste wird nach dem Laden bis zu dreimal neu gezeichnet – eine fokussierte Zeile behält den Fokus (Tastatur)
    const focused = document.activeElement?.closest?.('#quoteHistory [data-quote-open]')?.dataset.quoteOpen;
    box.innerHTML = shown.length ? shown.map(rowHtml).join('')
      : `<div class="ui-empty">${rows.length ? 'Kein Angebot passt zu dieser Ansicht.' : 'Noch keine Angebote gespeichert. „＋ Neues Angebot“ stellt eines aus deinem Leistungskatalog zusammen.'}</div>`;
    if (focused) box.querySelector(`[data-quote-open="${focused}"]`)?.focus({preventScroll: true});
  }

  // Sofort mit dem bekannten Stand zeichnen; Freigabe, Nachfassen und Auftragsstand kommen danach dazu. Der Aufrufer
  // (refreshSalesQuotes) wartet nicht darauf – „Angebot öffnen“ aus Heute oder der Akte findet die Zeile sofort.
  function list(data) {
    const my = ++seq;
    rows = data || [];
    renderList();
    renderOrders();
    return gather(rows).then(f => {
      if (my !== seq) return;
      facts = f;
      renderList();
      renderOrders();
    });
  }

  // ------------------------------------------------------------ Aufträge & Betreuung
  function renderOrders() {
    const box = byId('odRows');
    if (!box) return;
    const acc = rows.filter(r => r.status === 'angenommen' && !r.superseded);
    const label = (st, ok) => `<span class="ui-pill ${ok ? 'is-done' : st ? 'is-attention' : ''}">${esc(st || '–')}</span>`;
    byId('odCount').textContent = acc.length ? `${acc.length} ${acc.length === 1 ? 'Auftrag' : 'Aufträge'}${facts.care.size ? ` · ${facts.care.size} Betreuung(en)` : ''}` : '';
    box.innerHTML = acc.length ? acc.map(r => {
      const i = info(r), pr = facts.project.get(r.id), care = facts.care.get(r.id);
      return `<div class="ui-row od-row" role="listitem" tabindex="0" data-quote-open="${r.id}" data-od="${r.id}" aria-label="${esc(`${r.project_label} · ${r.company} · ${r.number}`)}">
        <div class="ui-main"><b>${esc(r.project_label || r.number)}</b><small>${esc(r.company)} · ${esc(r.number)}</small></div>
        <span class="ui-cut">${esc(i.step)}</span>
        <span data-od-kickoff>${pr ? label(pr.kickoff.label, pr.kickoff.status === 'gestartet') : care ? label('Betreuung', true) : label('')}</span>
        <span>${pr ? label(pr.handover.label, pr.handover.status === 'abgenommen') : label('')}</span>
        <span class="ui-num">${esc(i.monthly ? `${money(i.monthly)} / Monat` : money(r.net_eur))}</span><span class="ui-chev" aria-hidden="true">›</span></div>`;
    }).join('') : '<div class="ui-empty">Noch kein angenommenes Angebot. Nach der ersten Zusage stehen Aufträge mit Kick-off, Abnahme und Zeiten hier.</div>';
  }
  async function refreshOrders() {
    try { await list(await api('/workspace/proposals')); } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ Geöffnetes Angebot
  function setTab(name) {
    tab = name;
    document.querySelectorAll('#qtTabs [data-qt-tab]').forEach(b => { const on = b.dataset.qtTab === name; b.classList.toggle('is-active', on); b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; });
    document.querySelectorAll('#qtOffer [data-qt-panel]').forEach(p => p.classList.toggle('hidden', p.dataset.qtPanel !== name));
  }

  function phaseOf(s) {
    const need = s.checks.find(c => c.key === 'bedarf');
    if (s.status === 'angenommen' || s.status === 'abgelehnt') return 5;
    if (s.sent_at || s.status === 'gesendet_manuell') return 4;
    if (s.released && !s.stand_changed) return 3;
    if (need && !need.ok) return 0;
    return s.ready ? 2 : 1;
  }

  function mainAction(s, o) {
    if (!s || s.superseded_by) return null;
    const t = isoToday();
    if (s.status === 'entwurf') return s.released && !s.stand_changed ? {label: 'Als gesendet markieren', target: '#ofSend'} : {label: 'Zur Freigabe prüfen', target: '#ofRelease'};
    if (s.status === 'gesendet_manuell') {
      if ((o.f?.open || []).some(i => i.overdue || (i.due_date && i.due_date <= t))) return {label: 'Nachfassen festhalten', target: '#ofFollow'};
      return {label: 'Annahme dokumentieren', target: '#ofDecision'};
    }
    if (byId('ofStart')) return {label: s.status === 'angenommen' ? 'Projektstart festlegen' : 'Nachfassen beenden', target: '#ofStart'};
    if (s.status !== 'angenommen') return null;
    if (o.ko && o.ko.status !== 'gestartet') return {label: 'Kick-off vorbereiten', target: '#ofKickoff'};
    if (o.ho && o.ho.can_accept) return {label: 'Abnahme dokumentieren', target: '#ofHandover'};
    if (o.ho && ['in_arbeit', 'nachbesserung'].includes(o.ho.status)) return {label: 'Übergabe dokumentieren', target: '#ofHandover'};
    if (document.querySelector('#quoteSaved [data-quote-invoice]')) return {label: 'Rechnung erstellen', target: '#quoteSaved [data-quote-invoice]'};
    return null;
  }

  function jump(sel) {
    const el = document.querySelector(sel);
    if (!el) return;
    el.querySelectorAll('details:not([open])').forEach(d => { d.open = true; });
    if (el.matches('details')) el.open = true;
    el.scrollIntoView({behavior: 'smooth', block: 'center'});
    el.classList.add('qt-flash');
    setTimeout(() => el.classList.remove('qt-flash'), 1600);
    const ctl = el.matches('button,input,select,textarea') ? el : el.querySelector('input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),button:not([disabled])');
    if (ctl) ctl.focus({preventScroll: true});
    else { el.tabIndex = -1; el.focus({preventScroll: true}); }
  }

  function positionsHtml(d) {
    const c = d.customer || {}, internal = d.internal || {};
    const list = c.positions || [];
    if (!list.length) {  // Angebote aus dem früheren Paket-Rechner: Leistungen als Text
      return `<div class="ui-row-head" aria-hidden="true"><span>Leistung</span><span>Umfang</span><span>Art</span><span class="ui-num">Betrag</span><span></span></div>
        ${(c.included || []).map(x => `<div class="ui-row qt-pos-row"><div class="ui-main"><b>${esc(x)}</b></div><span></span><span><span class="ui-pill">fest</span></span><span class="ui-num"></span><span></span></div>`).join('')
        || `<div class="ui-empty">${esc(c.package_title || 'Paketangebot')} · ${esc(money(c.net_eur))} netto</div>`}`;
    }
    const kind = p => (p.optional ? '<span class="ui-pill is-underway">optional</span>' : p.billing === 'monatlich' ? '<span class="ui-pill is-attention">monatlich</span>' : '<span class="ui-pill">fest</span>');
    const scope = p => (p.unit === 'pauschal' ? String(p.scope || '').split(/[:·]/)[0].trim() : `${String(p.quantity).replace('.', ',')} × ${p.unit}`);
    const ip = internal.positions || [];
    return `<div class="ui-row-head" aria-hidden="true"><span>Leistung</span><span>Umfang</span><span>Art</span><span class="ui-num">Betrag</span><span></span></div>
      ${list.map((p, n) => `<details class="qt-pos" data-qt-pos="${n + 1}"><summary class="ui-row qt-pos-row">
        <div class="ui-main"><b>${esc(p.title)}</b><small>${esc(p.description || p.scope || '')}</small></div>
        <span class="ui-cut">${esc(scope(p))}</span><span>${kind(p)}</span>
        <span class="ui-num">${esc(money(p.price_eur))}${p.billing === 'monatlich' ? ' / Monat' : ''}</span><span class="ui-chev" aria-hidden="true">›</span></summary>
        <div class="ui-fold-body qt-pos-body"><p><b>Umfang:</b> ${esc(p.scope || '–')}${p.note ? ` · ${esc(p.note)}` : ''}</p>
          ${(p.deliverables || []).length ? `<p><b>Liefergegenstände:</b> ${p.deliverables.map(esc).join(' · ')}</p>` : ''}
          ${(p.excluded || []).length ? `<p><b>Nicht enthalten:</b> ${p.excluded.map(esc).join(' · ')}</p>` : ''}
          ${p.revisions_text ? `<p><b>Korrekturschleifen:</b> ${esc(p.revisions_text)}</p>` : ''}
          ${ip[n]?.formula ? `<p class="ui-small">Intern: ${esc(ip[n].formula)}${ip[n].effective_hourly != null ? ` · ${esc(money(ip[n].effective_hourly))}/h effektiv` : ''}</p>` : ''}</div></details>`).join('')}`;
  }

  function termsHtml(d, s) {
    const c = d.customer || {};
    const opt = (c.options || []).reduce((a, o) => a + (o.price_eur || 0), 0);
    const vat = c.tax_mode === 'regel_19';
    const sum = [c.once_net_eur ? `${money(c.once_net_eur)} netto` : (c.monthly_net_eur ? '' : `${money(c.net_eur)} netto`), vat && c.once_net_eur ? `${money(c.total_eur ?? c.once_net_eur * 1.19)} brutto` : '',
      c.monthly_net_eur ? `${money(c.monthly_net_eur)} / Monat` : '', opt ? `optional + ${money(opt)}` : ''].filter(Boolean).join(' · ');
    const pay = c.payment_plan || '–';
    return `<details class="ui-fold" id="qtSum"><summary><b>Summe</b><span>${esc(sum || money(c.net_eur))}</span></summary><div class="ui-fold-body">
        <p>${c.once_net_eur ? `Einmalig netto <b>${esc(money(c.once_net_eur))}</b>` : ''}${c.monthly_net_eur ? ` · monatlich netto <b>${esc(money(c.monthly_net_eur))}</b>` : ''}${c.vat_eur ? ` · USt. ${esc(money(c.vat_eur))}` : ''}</p>
        <p class="ui-small">${esc(c.tax_note || '')}${opt ? ` · ${esc(c.options_note || '')}` : ''}</p></div></details>
      <details class="ui-fold" id="qtPay"><summary><b>Zahlung &amp; Bedingungen</b><span>${esc(pay)}</span></summary><div class="ui-fold-body">
        <p><b>Zahlung:</b> ${esc(pay)}${c.weeks ? ` · <b>Zeitraum:</b> ${esc(c.weeks)}` : ''}</p>
        ${c.valid_until ? `<p><b>Gültig bis:</b> ${esc(longDate(c.valid_until))}${s && s.checks.some(x => x.key === 'frist' && !x.ok) ? ' <span class="ui-pill is-overdue">abgelaufen</span>' : ''}</p>` : ''}
        ${c.revision_note ? `<p><b>Korrekturschleifen:</b> ${esc(c.revision_note)}</p>` : ''}
        ${c.assumptions ? `<p><b>Voraussetzungen:</b> ${esc(c.assumptions)}</p>` : ''}
        ${c.change_requests ? `<p class="ui-small">${esc(c.change_requests)}</p>` : ''}</div></details>`;
  }

  function checksHtml(s, d) {
    const i = d.internal || {};
    let items = s.checks.map(c => ({ok: c.ok, text: c.label, small: c.detail}));
    if (typeof i.ok === 'boolean') items.push({ok: i.ok, text: i.ok ? 'Mindestverdienst erreicht' : 'Mindestverdienst nicht erreicht', small: i.ok ? '' : (i.warnings || []).join(' · ')});
    if (s.released && !s.stand_changed) {  // nach der Freigabe: nur noch, was heute nicht (mehr) erfüllt ist, dazu die Zahl der erfüllten
      const ok = items.filter(x => x.ok).length;
      items = [...items.filter(x => !x.ok), ...(ok ? [{ok: true, text: `${ok} von ${items.length} Prüfpunkten erfüllt`, small: ''}] : [])];
    }
    const head = s.released ? `<li class="qt-check ${s.stand_changed ? 'is-bad' : 'is-ok'}"><span class="qt-ico" aria-hidden="true">${s.stand_changed ? '!' : '✓'}</span><span><b>${s.stand_changed ? 'Dokument weicht vom freigegebenen Stand ab' : `Freigegeben am ${esc(longDate(s.released_at))}`}</b><small>Stand ${esc(s.stand)}</small></span></li>` : '';
    const hints = s.hints.length && !s.released ? `<li class="qt-check is-hint"><span class="qt-ico" aria-hidden="true">i</span><span><button type="button" class="ui-txt" data-qt-jump="#ofRelease">${s.hints.length} ${s.hints.length === 1 ? 'Hinweis' : 'Hinweise'} vor dem Versand</button></span></li>` : '';
    return head + items.map(x => `<li class="qt-check ${x.ok ? 'is-ok' : 'is-bad'}"><span class="qt-ico" aria-hidden="true">${x.ok ? '✓' : '!'}</span><span>${x.ok ? esc(x.text) : `<b>${esc(x.text)}</b>`}${x.small ? `<small>${esc(x.small)}</small>` : ''}</span></li>`).join('') + hints;
  }

  function phasesHtml(s) {
    const cur = phaseOf(s);
    const names = [['Bedarf', '#ofRelease'], ['Entwurf', '#qtPositions'], ['Freigabe', '#ofRelease'], ['Versand', '#ofSend'], ['Annahme', '#ofDecision']];
    const rejected = s.status === 'abgelehnt';
    return names.map(([n, target], k) => {
      const done = k < cur && !(rejected && k === 4), now = k === cur;
      const state = rejected && k === 4 ? 'is-bad' : done ? 'is-done' : now ? 'is-current' : '';
      const mark = rejected && k === 4 ? '–' : done ? '✓' : String(k + 1);
      return `<li class="qt-phase ${state}"${now ? ' aria-current="step"' : ''}><span class="qt-ico" aria-hidden="true">${mark}</span><button type="button" class="ui-txt" data-qt-jump="${target}">${n}${rejected && k === 4 ? ' (abgelehnt)' : ''}</button></li>`;
    }).join('') + (s.status === 'angenommen' ? '<li class="qt-phase is-current" aria-current="step"><span class="qt-ico" aria-hidden="true">6</span><button type="button" class="ui-txt" data-qt-jump="#ofKickoff">Auftrag: Kick-off, Übergabe, Abrechnung</button></li>' : '');
  }

  function historyHtml(d, o, drafts) {
    const s = o.s, ev = [];
    const c = d.customer || {};
    const add = (date, what, small = '') => { if (date) ev.push({date: String(date).slice(0, 10), what, small}); };
    add(c.offer_date || (rows.find(r => r.id === o.id) || {}).created_at, c.revision ? `Fassung ${c.revision.no} erstellt` : c.addendum ? `Zusatzauftrag ${c.addendum.no} erstellt` : 'Angebot erstellt',
      c.revision ? `ersetzt ${c.revision.replaces}` : c.addendum ? `zu ${c.addendum.base}` : '');
    add(s.released_at, 'Versandfassung freigegeben', `Stand ${s.stand}`);
    add(s.sent_at, 'Als versendet dokumentiert', [s.channels?.[s.sent_channel], s.sent_stand ? `Stand ${s.sent_stand}` : ''].filter(Boolean).join(' · '));
    (o.f?.items || []).forEach(i => add(i.done ? (i.done_at || i.due_date) : i.due_date, i.done ? `Nachgefasst: ${i.outcome_label || 'erledigt'}` : 'Nachfassen geplant', [i.reason, i.outcome_note].filter(Boolean).join(' · ')));
    add(s.decided_at, s.status === 'angenommen' ? 'Zusage dokumentiert' : 'Absage dokumentiert', [s.decision_channels?.[s.decision_channel], s.decision_person].filter(Boolean).join(' · '));
    if (o.ko?.started_at) add(o.ko.started_at, 'Projektstart dokumentiert', o.ko.start_note || '');
    if (o.ho?.handed_at) add(o.ho.handed_at, 'Übergabe dokumentiert');
    if (o.ho?.accepted_at) add(o.ho.accepted_at, o.ho.result_label || 'Abnahme dokumentiert', o.ho.accepted_person || '');
    if (s.superseded_by) ev.push({date: '', what: `Ersetzt durch ${s.superseded_number}`, small: ''});
    drafts.forEach(m => add(m.created_at, `Nachrichtenentwurf: ${m.subject}`, m.imap_saved_at ? 'im Postfach als Entwurf' : 'nicht versendet'));
    ev.sort((a, b) => (a.date || '9999').localeCompare(b.date || '9999'));
    return `<div class="ui-row-head" aria-hidden="true"><span>Verlauf</span></div><ol class="ui-rows qt-hist">${ev.map(e => `<li><span class="qt-hist-date">${esc(e.date ? longDate(e.date) : '–')}</span><span><b>${esc(e.what)}</b>${e.small ? `<small>${esc(e.small)}</small>` : ''}</span></li>`).join('')}</ol>
      ${(o.versions || []).length > 1 ? '' : '<p class="ui-small qt-hist-note">Nur eine Fassung – Überarbeitungen erscheinen hier als „Fassungen“.</p>'}`;
  }

  async function build(id) {
    const o = window.offerState && window.offerState.id === id ? window.offerState : null;
    let d, drafts = [];
    try {
      [d, drafts] = await Promise.all([api('/workspace/proposals/' + id), api('/workspace/mail-drafts').catch(() => [])]);
    } catch (e) { toast(e.message, true); return; }
    if (offerId !== id) return;
    const r = rows.find(x => x.id === id) || {};
    const company = r.company || (typeof leads !== 'undefined' ? (leads.find(l => l.id === d.lead_id) || {}).company : '') || '';
    const s = o?.s;
    byId('qtTitle').textContent = d.customer?.project_label || d.number;
    const key = s?.superseded_by ? 'ersetzt' : d.status === 'entwurf' && s?.released && !s.stand_changed ? 'freigegeben' : d.status;
    byId('qtPill').className = `ui-pill ${(STATUS[key] || ['', ''])[1]}`;
    byId('qtPill').textContent = (STATUS[key] || [d.status])[0];
    byId('qtMeta').textContent = [company, d.number].filter(Boolean).join(' · ');
    const main = byId('qtMain'), act = mainAction(s, o || {});
    main.classList.toggle('hidden', !act);
    main.textContent = act ? act.label : '';
    main.dataset.target = act ? act.target : '';
    byId('qtPositions').innerHTML = positionsHtml(d);
    byId('qtTerms').innerHTML = termsHtml(d, s);
    byId('qtCheckList').innerHTML = s ? checksHtml(s, d) : '';
    byId('qtPhases').innerHTML = s ? phasesHtml(s) : '';
    byId('qtChecks').classList.toggle('hidden', !s || !!s.superseded_by);
    byId('qtHistory').innerHTML = s ? historyHtml(d, o, (drafts || []).filter(m => m.proposal_id === id)) : '';
  }

  // ------------------------------------------------------------ Start
  function init() {
    if (!byId('viewQuotes') || !byId('qtList')) return;
    window.angebote = {list, showList, showEdit, editTitle, refreshOrders};
    // Ein Angebot öffnen: Arbeitsplatz zeigen, danach Kopf, Reiter und Kontext aufbauen. Die Ansicht wechselt, wer öffnet (Heute, Suche,
    // Akte tun das schon; Klicks unter „Aufträge & Betreuung“ siehe unten) – ein verspätetes Öffnen reißt so keine andere Ansicht an sich.
    const inner = window.wsOpenProposal;
    window.wsOpenProposal = async function (id) {
      id = Number(id);
      if (offerId !== id) {  // anderes Angebot: oben beginnen, Reiter „Positionen“
        setTab('positionen');
        byId('qtTitle').textContent = '…';
        byId('qtMain').classList.add('hidden');
        if (inQuotes()) window.scrollTo({top: 0, behavior: 'instant'});
      }
      offerId = id;
      setMode('offer');
      const res = await inner(id);
      if (offerId === id) await build(id);
      return res;
    };
    document.addEventListener('signaldesk:view', e => {
      if (e.detail.view === 'quotes' && !opening) showList();
      if (e.detail.view === 'orders') refreshOrders();
    });
    // Eine Firma im Angebotsformular vorbelegt (Heute, Recherche, Empfehlung, Überarbeitung …): der Editor öffnet sich
    document.addEventListener('change', e => {
      if (mode !== 'edit' && e.target.matches?.('#quoteForm [name=lead_id]') && e.target.value) showEdit(true);
    }, true);
    byId('qtNew').addEventListener('click', () => {
      if (!window.quoteHasUnsaved || !window.quoteHasUnsaved()) window.quoteReset?.();
      showEdit(true);
      byId('quoteForm')?.elements.lead_id?.focus();
    });
    document.addEventListener('click', e => {
      if (e.target.closest('#viewOrders [data-quote-open]')) ensureView();  // vor dem Öffnen (workspace.js) in „Angebote“ wechseln
    }, true);
    document.addEventListener('click', e => {
      if (e.target.closest('[data-qt-back]')) return window.switchView('quotes');  // Adresse #/angebote, die Liste zeigt sich über signaldesk:view
      const v = e.target.closest('[data-qt-view]');
      if (v) { preset = v.dataset.qtView; return renderList(); }
      const t = e.target.closest('[data-qt-tab]');
      if (t) return setTab(t.dataset.qtTab);
      const j = e.target.closest('[data-qt-jump]');
      if (j) { const sel = j.dataset.qtJump; if (sel === '#qtPositions') setTab('positionen'); return jump(sel); }
      if (e.target.closest('#qtMain') && byId('qtMain').dataset.target) return jump(byId('qtMain').dataset.target);
      if (e.target.closest('#qtReset')) {
        ['qtStatus'].forEach(i => { byId(i).value = ''; });
        ['qtExpired', 'qtUnbilled', 'qtHideOld'].forEach(i => { byId(i).checked = false; });
        byId('qtQ').value = '';
        preset = 'alle';
        renderList();
      }
    });
    // Tastatur: Enter oder Leertaste auf einer Zeile öffnet; Pfeiltasten zwischen den Reitern
    document.addEventListener('keydown', e => {
      const row = e.target.closest?.('.qt-row, .od-row');
      if (row && e.target === row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); row.click(); return; }
      const t = e.target.closest?.('#qtTabs [data-qt-tab]');
      if (t && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
        const all = [...document.querySelectorAll('#qtTabs [data-qt-tab]')];
        const next = all[(all.indexOf(t) + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
        setTab(next.dataset.qtTab);
        next.focus();
      }
    });
    byId('qtQ').addEventListener('input', renderList);
    ['qtStatus', 'qtExpired', 'qtUnbilled', 'qtHideOld'].forEach(i => byId(i).addEventListener('change', renderList));
    setTab('positionen');
    setMode('list');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
