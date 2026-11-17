'use strict';
// 2.0.0-dev17 (Roadmap M35, M36): Versandfassung freigeben, Versand und Zusage mit Weg, Zeitpunkt und Stand dokumentieren,
// danach den Projektstart festlegen. Ersetzt im gespeicherten Angebot die freie Statusauswahl. SignalDesk versendet nichts.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const today = () => new Date().toISOString().slice(0, 10);
  const plusDays = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const opt = (obj, sel) => Object.entries(obj).map(([k, v]) => `<option value="${esc(k)}" ${k === sel ? 'selected' : ''}>${esc(v)}</option>`).join('');
  let current = null;

  function mark(ok) { return `<span class="pill ${ok ? 'ok' : 'bad'}">${ok ? 'erfüllt' : 'fehlt'}</span>`; }
  // 2.0.0-dev52 (UX Schritt 4): spätere Phasen als Vorschau – Titel sichtbar, das noch gesperrte Formular eingeklappt
  const later = (id, title, note, body) => `<li class="of-step off" id="${id}"><details class="of-later"><summary><b>${title}</b> <small class="muted">${esc(note)}</small></summary>${body}</details></li>`;

  function stepRelease(s) {
    if (s.released) {
      return `<li class="of-step done" id="ofRelease"><b>1 · Versandfassung</b><span>✓ freigegeben am ${esc(fmtDate(s.released_at.slice(0, 10)))} · Stand <code>${esc(s.stand)}</code></span>
        ${s.stand_changed ? '<p class="qb-check warn">! Das gespeicherte Dokument weicht vom freigegebenen Stand ab. Bitte nicht versenden und neu erstellen.</p>' : ''}</li>`;
    }
    return `<li class="of-step" id="ofRelease"><b>1 · Versandfassung freigeben</b><p class="muted">Der Export trägt bis dahin sichtbar „Entwurf“. Freigeben heißt nicht versenden.</p>
      <ul class="of-checks">${s.checks.map(c => `<li>${mark(c.ok)} ${esc(c.label)}${c.detail ? ` <small class="muted">${esc(c.detail)}</small>` : ''}</li>`).join('')}</ul>
      ${s.hints.length ? `<div class="qb-check warn of-hints">${s.hints.map(h => '! ' + esc(h)).join('<br>')}</div>` : ''}
      <fieldset class="of-confirm" ${s.ready ? '' : 'disabled'}><legend>Vor dem Versand selbst geprüft</legend>
        ${Object.entries(s.confirmations).map(([k, v]) => `<label class="quote-addon"><input type="checkbox" data-of-confirm="${esc(k)}"><span>${esc(v)}</span></label>`).join('')}
        <button type="button" class="btn btn-ghost" data-of-release>Versandfassung freigeben</button></fieldset></li>`;
  }

  function stepSend(s) {
    if (s.sent_at || s.status === 'gesendet_manuell') {
      return `<li class="of-step done" id="ofSend"><b>2 · Versand</b><span>✓ ${s.sent_at ? `am ${esc(fmtDate(s.sent_at))} ${esc(s.channels[s.sent_channel] || '')} · Stand <code>${esc(s.sent_stand)}</code>` : 'als versendet dokumentiert (vor 2.0.0-dev17, ohne Stand)'}</span></li>`;
    }
    if (['angenommen', 'abgelehnt'].includes(s.status)) return '';
    const sendBody = `<p class="muted">Erst nachdem du die freigegebene Fassung selbst verschickt hast.</p>
      <div class="sales-row"><label>Weg<select data-of-channel ${s.released ? '' : 'disabled'}>${opt(s.channels, 'email')}</select></label>
      <label>Datum<input type="date" data-of-sentdate value="${today()}" max="${today()}" ${s.released ? '' : 'disabled'}></label></div>
      <div class="sales-row"><label>Nachfassen am<input type="date" data-of-followdate value="${plusDays(today(), 7)}" min="${today()}" ${s.released ? '' : 'disabled'}></label>
      <label>Anlass<input data-of-followreason maxlength="160" placeholder="z. B. Entscheidung nach der Gesellschafterrunde" ${s.released ? '' : 'disabled'}></label>
      <button type="button" class="btn btn-ghost" data-of-sent ${s.released ? '' : 'disabled'}>Als versendet dokumentieren</button></div>`;
    if (!s.released) return later('ofSend', '2 · Versand dokumentieren', 'folgt nach der Freigabe', sendBody);
    return `<li class="of-step" id="ofSend"><b>2 · Versand dokumentieren</b>${sendBody}</li>`;
  }

  // 2.0.0-dev23 (M16): Nachfassen mit Anlass, Frist und Ergebnis
  function stepFollow(s, f) {
    if (!f || !f.items.length) return '';
    const done = f.items.filter(i => i.done);
    const hist = done.length ? `<ul class="of-fu-done">${done.map(i => `<li><b>${esc(i.outcome_label || 'erledigt')}</b> · ${esc(i.reason)}${i.due_date ? ' · Frist ' + esc(fmtDate(i.due_date)) : ''}${i.outcome_note ? `<small>${esc(i.outcome_note)}</small>` : ''}</li>`).join('')}</ul>` : '';
    const live = s.status === 'gesendet_manuell';
    const open = f.open.map(i => `<div class="of-fu" data-of-fu-item="${i.id}"><p><b>${i.overdue ? '<span class="pill bad">überfällig</span> ' : ''}Fällig ${esc(fmtDate(i.due_date))}</b> · ${esc(i.reason)}</p>
      ${live ? `<div class="sales-row"><label>Ergebnis<select data-of-fu-outcome>${opt(f.outcomes, 'entscheidung_offen')}</select></label>
      <label>Nächstes Nachfassen<input type="date" data-of-fu-next value="${esc(f.default_next)}" min="${today()}"></label></div>
      <div class="sales-row"><label>Notiz<input data-of-fu-note maxlength="500" placeholder="Was wurde gesagt?"></label>
      <label>Nächster Anlass<input data-of-fu-reason maxlength="160" placeholder="optional"></label>
      <button type="button" class="btn btn-ghost" data-of-fu="${i.id}">Ergebnis festhalten</button></div>` : '<p class="muted">Nach der Entscheidung beim Projektstart bzw. Abschluss beenden.</p>'}</div>`).join('');
    const state = f.open.length ? '' : (live ? ' <span class="pill bad">kein nächster Schritt</span>' : '');
    return `<li class="of-step ${f.open.length ? '' : 'done'}" id="ofFollow"><b>Nachfassen${state}</b>${open}${hist}</li>`;
  }

  function stepDecision(s) {
    if (s.decided_at) {
      const who = [s.decision_channels[s.decision_channel] || '', s.decision_person ? 'von ' + s.decision_person : ''].filter(Boolean).join(', ');
      return `<li class="of-step done" id="ofDecision"><b>3 · Entscheidung</b><span>${s.status === 'angenommen' ? '✓ angenommen' : '– abgelehnt'} am ${esc(fmtDate(s.decided_at))}${who ? ' · ' + esc(who) : ''}</span>${s.decision_note ? `<small class="muted">${esc(s.decision_note)}</small>` : ''}</li>`;
    }
    if (['angenommen', 'abgelehnt'].includes(s.status)) return `<li class="of-step done" id="ofDecision"><b>3 · Entscheidung</b><span>${s.status === 'angenommen' ? '✓ angenommen' : '– abgelehnt'} (vor 2.0.0-dev17 dokumentiert)</span></li>`;
    const decBody = `<p class="muted">Eine positive Rückmeldung mit Änderungswünschen ist noch keine Zusage zu diesem Stand.</p>
      <div class="sales-row"><label>Weg<select data-of-dchannel ${s.released ? '' : 'disabled'}>${opt(s.decision_channels, 'email')}</select></label>
      <label>Person<input data-of-person maxlength="120" placeholder="Wer hat entschieden?" ${s.released ? '' : 'disabled'}></label>
      <label>Datum<input type="date" data-of-ddate value="${today()}" max="${today()}" ${s.released ? '' : 'disabled'}></label></div>
      <label>Notiz<input data-of-note maxlength="500" placeholder="z. B. Bestellnummer, Bedingungen" ${s.released ? '' : 'disabled'}></label>
      <div class="sales-row"><button type="button" class="btn btn-ghost" data-of-decide="angenommen" ${s.released ? '' : 'disabled'}>Zusage dokumentieren</button>
      <button type="button" class="btn btn-ghost" data-of-decide="abgelehnt" ${s.released ? '' : 'disabled'}>Absage dokumentieren</button></div>`;
    if (!s.released) return later('ofDecision', '3 · Zusage oder Absage dokumentieren', 'folgt nach Freigabe und Versand', decBody);
    return `<li class="of-step" id="ofDecision"><b>3 · Zusage oder Absage dokumentieren</b>${decBody}</li>`;
  }

  function stepStart(p, s) {
    if (!p || !['angenommen', 'abgelehnt'].includes(s.status)) return '';
    // Erledigt, sobald der Start übernommen ist (mindestens eine Startaufgabe; bewusst abgewählte bleiben weg) und nichts mehr nachgefasst wird
    const made = p.suggestions.filter(x => x.exists).length;
    if (!p.followups.length && (made || s.status !== 'angenommen')) {
      return `<li class="of-step done"><b>4 · ${s.status === 'angenommen' ? 'Projektstart' : 'Abschluss'}</b><span>✓ ${s.status === 'angenommen' ? `${made} Startaufgabe(n) angelegt, ` : ''}keine offenen Nachfassaufgaben</span></li>`;
    }
    return `<li class="of-step" id="ofStart"><b>4 · ${s.status === 'angenommen' ? 'Projektstart festlegen' : 'Nachfassen beenden'}</b>
      ${p.suggestions.length ? `<div class="sales-subhead">Startaufgaben</div>${p.suggestions.map(x => `<label class="quote-addon"><input type="checkbox" data-of-create="${esc(x.key)}" ${x.exists ? 'disabled' : 'checked'}><span>${esc(x.title)}<small>${x.exists ? (x.done ? 'bereits erledigt' : 'bereits angelegt') : (x.days ? `fällig in ${x.days} Tag(en)` : 'fällig heute')}</small></span></label>`).join('')}` : ''}
      ${p.followups.length ? `<div class="sales-subhead">Offene Nachfassaufgaben zu diesem Angebot – beenden?</div>${p.followups.map(f => `<label class="quote-addon"><input type="checkbox" data-of-close="${f.id}" checked><span>${esc(f.title)}<small>${f.due_date ? 'fällig ' + esc(fmtDate(f.due_date)) : ''}</small></span></label>`).join('')}` : ''}
      <button type="button" class="btn btn-ghost" data-of-start>${s.status === 'angenommen' ? 'Projektstart übernehmen' : 'Ausgewählte Aufgaben beenden'}</button></li>`;
  }

  // 2.0.0-dev28 (M38/M39): Projektkompass – Startvoraussetzungen mit Verantwortlichen, Frist und Auswirkung
  function stepKickoff(k) {
    if (!k) return '';
    const started = k.status === 'gestartet';
    const row = i => `<li class="ho-${esc(i.state)}" data-ko-row="${i.id}"><span><b>${esc(i.kind_label)}</b> ${esc(i.label)}
        <small>${esc(i.owner_name || i.owner_label)}${i.due_date ? ` · bis ${esc(fmtDate(i.due_date))}` : ''}${i.overdue ? ' <span class="pill bad">überfällig</span>' : ''}${i.impact ? ` · ohne: ${esc(i.impact)}` : ''}</small></span>
      <select data-ko-state="${i.id}" aria-label="Stand: ${esc(i.label)}">${k.states.map(s => `<option value="${s}" ${s === i.state ? 'selected' : ''}>${esc(ST_LABEL[s])}</option>`).join('')}</select>
      <select data-ko-owner="${i.id}" aria-label="Wer liefert">${opt(k.owners, i.owner)}</select>
      <input data-ko-name="${i.id}" maxlength="120" value="${esc(i.owner_name)}" placeholder="Name (optional)" aria-label="Name">
      <input type="date" data-ko-due="${i.id}" value="${esc(i.due_date)}" aria-label="Bis wann">
      <input data-ko-note="${i.id}" maxlength="300" value="${esc(i.note)}" placeholder="Notiz / Begründung" aria-label="Notiz"></li>`;
    return `<li class="of-step ${started ? 'done' : ''}" id="ofKickoff"><details class="of-fold" ${started ? '' : 'open'}><summary><b>Kick-off · Projektkompass</b> <span class="pill ${started || k.status === 'bereit' ? 'ok' : k.status === 'wartet' ? 'bad' : ''}" data-ko-status>${esc(k.status_label)}</span></summary>
      ${k.waiting.length && !started ? `<p class="qb-check warn">! Wartet auf: ${k.waiting.map(w => `${esc(w.owner)} – ${esc(w.label)}${w.due_date ? ' (bis ' + esc(fmtDate(w.due_date)) + ')' : ''}`).join('; ')}</p>` : ''}
      <ul class="ho-items ko-items">${k.items.map(row).join('')}</ul>
      <p class="muted">${esc(k.secret_hint)}</p>
      <div class="sales-row ho-add"><select data-ko-addkind aria-label="Art">${opt(k.kinds, 'material')}</select><select data-ko-addowner aria-label="Wer liefert">${opt(k.owners, 'kunde')}</select>
        <input data-ko-addlabel maxlength="300" placeholder="Weitere Voraussetzung, z. B. Bildrechte klären" aria-label="Weitere Voraussetzung">
        <input type="date" data-ko-adddue aria-label="Bis wann"><input data-ko-addimpact maxlength="300" placeholder="Was geht ohne nicht?" aria-label="Auswirkung">
        <button type="button" class="btn btn-ghost" data-ko-add>Ergänzen</button></div>
      ${started ? `<p>Gestartet am ${esc(fmtDate(k.started_at))}${k.start_note ? ' · ' + esc(k.start_note) : ''}</p>` : `<div class="sales-row"><label>Gestartet am<input type="date" data-ko-date value="${today()}" max="${today()}"></label>
        <label>Notiz<input data-ko-snote maxlength="300" placeholder="z. B. Kick-off per Video"></label>
        ${k.open ? '<label class="quote-addon"><input type="checkbox" data-ko-force><span>trotz offener Punkte starten</span></label>' : ''}
        <button type="button" class="btn btn-ghost" data-ko-start>Projektstart dokumentieren</button></div>`}</details></li>`;
  }

  // 2.0.0-dev24 (M17, T12): Übergabe und Abnahme des angenommenen Auftrags
  const ST_LABEL = {offen: 'offen', erledigt: 'erledigt', entfaellt: 'entfällt'};
  function stepHandover(h) {
    if (!h) return '';
    const finished = ['abgenommen', 'vorbehalt'].includes(h.status);
    const editable = ['in_arbeit', 'nachbesserung'].includes(h.status);
    const group = (kinds, title) => {
      const its = h.items.filter(i => kinds.includes(i.kind));
      if (!its.length) return '';
      return `<div class="sales-subhead">${esc(title)}</div><ul class="ho-items">${its.map(i => {
        const locked = finished && ['liefer', 'kriterium'].includes(i.kind);
        return `<li class="ho-${esc(i.state)}" data-ho-row="${i.id}"><span>${esc(i.label)}${i.due_date ? ` <small>bis ${esc(fmtDate(i.due_date))}</small>` : ''}${i.note ? ` <small class="muted">${esc(i.note)}</small>` : ''}</span>
          ${locked ? `<b>${esc(ST_LABEL[i.state])}</b>` : `<select data-ho-item="${i.id}" aria-label="Stand: ${esc(i.label)}">${h.states.map(s => `<option value="${s}" ${s === i.state ? 'selected' : ''}>${esc(ST_LABEL[s])}</option>`).join('')}</select>
          <input data-ho-note maxlength="300" placeholder="Begründung bei „entfällt“" value="${esc(i.note)}" aria-label="Notiz">`}</li>`;
      }).join('')}</ul>`;
    };
    const add = editable ? `<div class="sales-row ho-add"><select data-ho-addkind aria-label="Art"><option value="liefer">Liefergegenstand</option><option value="kriterium">Abnahmekriterium</option></select>
      <input data-ho-addlabel maxlength="300" placeholder="Eigenen Punkt ergänzen" aria-label="Eigener Punkt"><button type="button" class="btn btn-ghost" data-ho-add>Ergänzen</button></div>` : '';
    const hand = editable ? `<div class="sales-subhead">${h.round > 1 ? 'Erneut übergeben' : 'Übergabe dokumentieren'}</div>
      ${h.blocking ? `<p class="qb-check warn">! Noch ${h.blocking} Liefergegenstand/Nachbesserung offen – erledigen oder begründet entfallen lassen.</p>` : ''}
      <div class="sales-row"><label>Weg<select data-ho-channel>${opt(h.channels, 'email')}</select></label>
      <label>Datum<input type="date" data-ho-date value="${today()}" max="${today()}"></label>
      <label>Abnahme einholen bis<input type="date" data-ho-due value="${esc(h.default_due)}" min="${today()}"></label></div>
      <div class="sales-row"><label>Notiz<input data-ho-hnote maxlength="500" placeholder="z. B. Zugänge übergeben, Einweisung erfolgt"></label>
      <button type="button" class="btn btn-ghost" data-ho-handover ${h.can_hand_over ? '' : 'disabled'}>Übergabe dokumentieren</button></div>` : '';
    const acc = h.can_accept ? `<div class="sales-subhead">Abnahme dokumentieren</div>
      <p class="muted">Übergeben am ${esc(fmtDate(h.handed_at))}. Restpunkte und Nachbesserungen bitte einzeln, je Zeile einer.</p>
      <div class="sales-row"><label>Ergebnis<select data-ho-result>${opt(h.results, 'abgenommen')}</select></label>
      <label>Weg<select data-ho-achannel>${opt(h.channels, 'email')}</select></label>
      <label>Datum<input type="date" data-ho-adate value="${today()}" min="${esc(h.handed_at)}" max="${today()}"></label>
      <label>Person<input data-ho-person maxlength="120" placeholder="Wer hat abgenommen?"></label></div>
      <label>Restpunkte / Nachbesserungen<textarea data-ho-points rows="3" maxlength="3000" placeholder="leer lassen bei vollständiger Abnahme"></textarea></label>
      <div class="sales-row"><label>Frist für die Punkte<input type="date" data-ho-pdue value="${esc(h.default_due)}" min="${today()}"></label>
      <label>Notiz<input data-ho-anote maxlength="500"></label>
      <button type="button" class="btn btn-ghost" data-ho-accept>Abnahme dokumentieren</button></div>` : '';
    const result = finished ? `<p><b>${esc(h.result_label)}</b> am ${esc(fmtDate(h.accepted_at))}${h.accepted_person ? ' durch ' + esc(h.accepted_person) : ''}${h.rest_open ? ` · <span class="pill bad">${h.rest_open} Restpunkt(e) offen</span>` : ''}</p>
      ${h.final_invoice_due ? '<p class="qb-check warn">! Laut Zahlungsplan ist die Schlussrechnung fällig – unter „Abrechnen“ erstellen.</p>' : ''}` : '';
    return `<li class="of-step ${h.status === 'abgenommen' ? 'done' : ''}" id="ofHandover"><details class="of-fold" ${h.status === 'abgenommen' ? '' : 'open'}><summary><b>5 · Übergabe & Abnahme</b> <span class="pill ${finished ? 'ok' : ''}" data-ho-status>${esc(h.status_label)}</span></summary>
      ${result}${group(['liefer'], 'Liefergegenstände')}${group(['kriterium'], 'Abnahmekriterien')}${group(['nachbesserung'], 'Nachbesserungen')}${group(['restpunkt'], 'Restpunkte')}
      ${add}${hand}${acc}<div class="sales-row"><button type="button" class="btn btn-ghost" data-ho-protocol>${finished ? 'Abnahmeprotokoll herunterladen (.md)' : 'Protokoll-Entwurf zur Abnahme (.md)'}</button></div></details></li>`;
  }

  async function render(id) {
    const box = $('#quoteSaved');
    if (!box) return;
    let s, p = null, f = null, ho = null, ko = null;
    try {
      s = await api('/workspace/proposals/' + id + '/versand');
      if (['angenommen', 'abgelehnt'].includes(s.status)) p = await api('/workspace/proposals/' + id + '/start');
      if (s.status !== 'entwurf') f = await api('/workspace/proposals/' + id + '/nachfassen');
      if (s.status === 'angenommen' && !s.superseded_by) ho = await api('/workspace/proposals/' + id + '/abnahme');
      if (s.status === 'angenommen' && !s.superseded_by) ko = await api('/workspace/proposals/' + id + '/kompass');
    } catch (e) { toast(e.message, true); return; }
    current = {id, s, p};
    window.offerState = {id, s, p, f, ho, ko};  // 2.0.0-dev52: für Kopf, Kontextspalte und Verlauf des Arbeitsplatzes (angebote.js)
    box.querySelector('[data-quote-status]')?.closest('label')?.remove();
    const exp = box.querySelector('[data-quote-export]');
    if (exp) exp.textContent = s.released && !s.stand_changed ? 'Versandfassung herunterladen (.md)' : 'Entwurf herunterladen (.md)';
    const cp = box.querySelector('[data-quote-copy]');
    if (cp) cp.textContent = s.released && !s.stand_changed ? 'Versandfassung kopieren' : 'Entwurf kopieren';
    box.querySelector('#ofPanel')?.remove();
    box.querySelector('#ofRevisions')?.remove();
    const head = box.querySelector('h3');
    // 2.0.0-dev21 (M15): ersetzte Fassungen sind nur noch Nachweis; aktuelle Fassungen lassen sich überarbeiten
    const steps = s.superseded_by ? `<li class="of-step done"><b>Ersetzt</b><span>Diese Fassung ist durch ${esc(s.superseded_number)} ersetzt. Freigabe, Versand und Zusage gehen nur noch dort.</span>
        <button type="button" class="btn btn-ghost" data-quote-open="${s.superseded_by}">${esc(s.superseded_number)} öffnen</button></li>`
      : `${stepRelease(s)}${stepSend(s)}${stepFollow(s, f)}${stepDecision(s)}${stepStart(p, s)}${stepKickoff(ko)}${stepHandover(ho)}`;
    (head || box).insertAdjacentHTML(head ? 'afterend' : 'afterbegin', `<ol class="of-panel" id="ofPanel" data-of-id="${id}">${steps}</ol>
      <div class="of-revisions" id="ofRevisions">${s.revisable ? `<button type="button" class="btn btn-ghost" data-of-revise="${id}">Überarbeiten (neue Fassung)</button>` : ''}${s.addable ? `<button type="button" class="btn btn-ghost" data-of-addendum="${id}">Zusatzauftrag erstellen</button>` : ''}<div data-of-basis></div><div data-of-scope></div>${$('#qtHistVersions') ? '' : '<div data-of-history></div>'}</div>`);
    // 2.0.0-dev33 (M32): Grundlage je Position – nur intern
    try {
      const g = await api(`/workspace/proposals/${id}/grundlage`);
      const cls = {bedarf: 'ok', befund: 'ok', begleitend: '', ohne: 'bad'};
      box.querySelector('[data-of-basis]').innerHTML = `<details class="of-basis" ${g.without.length || g.open_hypotheses ? 'open' : ''}><summary>Grundlage je Position (nur intern)${g.without.length ? ` · <span class="pill bad">${g.without.length} ohne Grundlage</span>` : ''}</summary>
        <ol>${g.positions.map(i => `<li data-basis="${esc(i.basis)}"><b>${esc(i.title)}</b>${i.optional ? ' (optional)' : ''} <span class="pill ${cls[i.basis]}">${esc(i.label)}</span>
          ${i.evidence.length ? `<small>Beleg: ${i.evidence.map(e => esc(e.label)).join('; ')}</small>` : ''}
          ${i.hypotheses.length ? `<small class="rc-late">Offene Hypothese (ungeprüft): ${i.hypotheses.map(e => esc(e.label)).join('; ')}</small>` : ''}</li>`).join('')}</ol>
        <p class="muted">${esc(g.notice)}</p></details>`;
    } catch { /* Grundlage ist eine Zusatzinfo */ }
    // 2.0.0-dev25 (M18): Auftragsumfang – ursprünglicher Auftrag und Zusatzaufträge
    if (s.addendum_of || s.status === 'angenommen') {
      try {
        const u = await api(`/workspace/proposals/${id}/umfang`);
        if (u.addenda.length || s.addendum_of) {
          const row = (n, label, status, net, extra, pid) => `<li${pid === id ? ' class="of-current"' : ''}><button type="button" class="text-button" data-quote-open="${pid}">${esc(n)}</button> ${esc(label)} · ${esc(status.replaceAll('_', ' '))} · ${esc(euros(net))} netto${extra ? `<small>${esc(extra)}</small>` : ''}</li>`;
          box.querySelector('[data-of-scope]').innerHTML = `<details class="of-history of-scope" open><summary>Auftragsumfang</summary><ol>
            ${row(u.base.number, 'Auftrag' + (u.base.project_label ? ': ' + u.base.project_label : ''), u.base.status, u.base.net_eur, '', u.base.id)}
            ${u.addenda.map(a => row(a.number, `Zusatzauftrag ${a.no}` + (a.project_label ? ': ' + a.project_label : ''), a.status, a.net_eur, a.reason ? 'Anlass: ' + a.reason : '', a.id)).join('')}</ol>
            ${u.total_net_eur != null ? `<p><b>Beauftragt insgesamt: ${esc(euros(u.total_net_eur))} netto</b>${u.open_net_eur ? ` · offen angeboten: ${esc(euros(u.open_net_eur))}` : ''}</p>` : ''}</details>`;
        }
      } catch { /* Umfang ist eine Zusatzinfo */ }
    }
    // 2.0.0-dev52: Fassungen stehen im Reiter „Verlauf“ des Arbeitsplatzes (#qtHistVersions), sonst wie bisher unter den Schritten
    const histBox = $('#qtHistVersions') || box.querySelector('[data-of-history]');
    if (histBox) histBox.innerHTML = '';
    window.offerState.versions = null;
    try {
      const h = await api(`/workspace/proposals/${id}/fassungen`);
      window.offerState.versions = h.versions;
      if (h.versions.length > 1) histBox.innerHTML = `<details class="of-history"><summary>Fassungen (${h.versions.length})</summary><ol>${h.versions.map(v => `<li><b>${esc(v.number)}</b> · ${esc(v.offer_date ? fmtDate(v.offer_date) : '')} · ${v.net_eur != null ? esc(euros(v.net_eur)) + ' netto' : ''} · ${v.superseded ? 'ersetzt' : esc(v.status.replaceAll('_', ' '))}${v.reason ? `<small>Grund: ${esc(v.reason)}</small>` : ''}${v.changes.length ? `<ul>${v.changes.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}</li>`).join('')}</ol></details>`;
    } catch { /* Fassungen sind eine Zusatzinfo */ }
  }

  async function after(msg) {
    toast(msg);
    await window.refreshSalesQuotes?.();
    await window.wsOpenProposal(current.id);
    try { await window.reload?.(); } catch { /* Ansicht aktualisiert sich beim nächsten Wechsel */ }
  }

  function init() {
    if (!$('#quoteSaved') || !window.wsOpenProposal) return;
    const orig = window.wsOpenProposal;
    window.wsOpenProposal = async function (id) { await orig(id); await render(id); };
    document.addEventListener('click', async e => {
      // Export mit eindeutigem Dateinamen (Entwurf bzw. Versandfassung mit Stand)
      const ex = e.target.closest('[data-quote-export]');
      if (ex) {
        e.stopImmediatePropagation();
        try { const d = await api('/workspace/proposals/' + ex.dataset.quoteExport + '/customer'); wsDownload(d.filename, d.markdown, 'text/markdown;charset=utf-8'); }
        catch (err) { toast(err.message, true); }
        return;
      }
      const za = e.target.closest('[data-of-addendum]');
      if (za) { e.stopImmediatePropagation(); return window.quoteStartAddendum?.(Number(za.dataset.ofAddendum)); }
      const rv = e.target.closest('[data-of-revise]');
      if (rv) { e.stopImmediatePropagation(); return window.quoteStartRevision?.(Number(rv.dataset.ofRevise)); }
      const panel = e.target.closest('#ofPanel');
      if (!panel || !current) return;
      const id = current.id;
      try {
        if (e.target.closest('[data-of-release]')) {
          const confirm = Array.from(panel.querySelectorAll('[data-of-confirm]:checked')).map(x => x.dataset.ofConfirm);
          await api(`/workspace/proposals/${id}/freigabe`, 'POST', {confirm});
          return after('Versandfassung freigegeben – noch nichts versendet');
        }
        if (e.target.closest('[data-of-sent]')) {
          const r = await api('/workspace/proposals/' + id, 'PATCH', {status: 'gesendet_manuell', channel: panel.querySelector('[data-of-channel]').value, date: panel.querySelector('[data-of-sentdate]').value,
            follow_up: panel.querySelector('[data-of-followdate]').value, follow_reason: panel.querySelector('[data-of-followreason]').value});
          return after(r.notice);
        }
        const hoUrl = `/workspace/proposals/${id}/abnahme`;
        const val = sel => panel.querySelector(sel)?.value ?? '';
        const koUrl = `/workspace/proposals/${id}/kompass`;
        if (e.target.closest('[data-ko-add]')) {
          await api(koUrl, 'POST', {action: 'add', kind: val('[data-ko-addkind]'), owner: val('[data-ko-addowner]'), label: val('[data-ko-addlabel]'),
            due_date: val('[data-ko-adddue]'), impact: val('[data-ko-addimpact]')});
          return after('Voraussetzung ergänzt');
        }
        if (e.target.closest('[data-ko-start]')) {
          const r = await api(koUrl, 'POST', {action: 'start', date: val('[data-ko-date]'), note: val('[data-ko-snote]'), ...(panel.querySelector('[data-ko-force]')?.checked ? {trotz_offener_punkte: true} : {})});
          await after(r.notice);
          $('#ofKickoff')?.scrollIntoView({block: 'center'});
          return;
        }
        if (e.target.closest('[data-ho-protocol]')) {
          const d = await api(hoUrl + '/protokoll');
          wsDownload(d.filename, d.markdown, 'text/markdown;charset=utf-8');
          return;
        }
        if (e.target.closest('[data-ho-add]')) {
          await api(hoUrl, 'POST', {action: 'add', kind: val('[data-ho-addkind]'), label: val('[data-ho-addlabel]')});
          return after('Punkt ergänzt');
        }
        if (e.target.closest('[data-ho-handover]')) {
          const r = await api(hoUrl, 'POST', {action: 'uebergabe', channel: val('[data-ho-channel]'), date: val('[data-ho-date]'), due: val('[data-ho-due]'), note: val('[data-ho-hnote]')});
          await after(r.notice);
          $('#ofHandover')?.scrollIntoView({block: 'center'});
          return;
        }
        if (e.target.closest('[data-ho-accept]')) {
          const due = val('[data-ho-pdue]');
          const points = val('[data-ho-points]').split('\n').map(x => x.trim()).filter(Boolean).map(label => ({label, due}));
          const r = await api(hoUrl, 'POST', {action: 'abnahme', result: val('[data-ho-result]'), channel: val('[data-ho-achannel]'), date: val('[data-ho-adate]'),
            person: val('[data-ho-person]'), note: val('[data-ho-anote]'), points});
          await after(r.notice);
          $('#ofHandover')?.scrollIntoView({block: 'center'});
          return;
        }
        const fu = e.target.closest('[data-of-fu]');
        if (fu) {
          const box = fu.closest('[data-of-fu-item]');
          const outcome = box.querySelector('[data-of-fu-outcome]').value;
          const body = {outcome, note: box.querySelector('[data-of-fu-note]').value};
          if (['entscheidung_offen', 'rueckfragen', 'nicht_erreicht'].includes(outcome)) Object.assign(body, {next_date: box.querySelector('[data-of-fu-next]').value, next_reason: box.querySelector('[data-of-fu-reason]').value});
          const r = await api(`/tasks/${fu.dataset.ofFu}/ergebnis`, 'POST', body);
          await after(r.notice || 'Ergebnis festgehalten');
          $('#ofFollow')?.scrollIntoView({block: 'center'});
          return;
        }
        const dec = e.target.closest('[data-of-decide]');
        if (dec) {
          const r = await api('/workspace/proposals/' + id, 'PATCH', {status: dec.dataset.ofDecide, channel: panel.querySelector('[data-of-dchannel]').value,
            person: panel.querySelector('[data-of-person]').value, date: panel.querySelector('[data-of-ddate]').value, note: panel.querySelector('[data-of-note]').value});
          await after(r.notice);
          $('#ofStart')?.scrollIntoView({behavior: 'smooth', block: 'center'});
          return;
        }
        if (e.target.closest('[data-of-start]')) {
          const r = await api(`/workspace/proposals/${id}/start`, 'POST', {create: Array.from(panel.querySelectorAll('[data-of-create]:checked')).map(x => x.dataset.ofCreate),
            close: Array.from(panel.querySelectorAll('[data-of-close]:checked')).map(x => Number(x.dataset.ofClose))});
          return after(`${r.created} Startaufgabe(n) angelegt, ${r.closed} Nachfassaufgabe(n) beendet`);
        }
      } catch (err) { toast(err.message, true); }
    }, true);
    document.addEventListener('change', e => {
      const sd = e.target.closest('#ofPanel [data-of-sentdate]');
      const fd = sd && $('#ofPanel [data-of-followdate]');
      if (fd && !fd.dataset.touched && sd.value) fd.value = [plusDays(sd.value, 7), today()].sort().pop();
      if (e.target.matches?.('#ofPanel [data-of-followdate]')) e.target.dataset.touched = '1';
      const ke = e.target.closest('#ofPanel [data-ko-state],#ofPanel [data-ko-owner],#ofPanel [data-ko-name],#ofPanel [data-ko-due],#ofPanel [data-ko-note]');
      if (ke && current) {
        const rowEl = ke.closest('[data-ko-row]'), iid = Number(rowEl.dataset.koRow);
        const v = sel => rowEl.querySelector(sel).value;
        api(`/workspace/proposals/${current.id}/kompass`, 'POST', {action: 'item', item_id: iid, state: v('[data-ko-state]'), owner: v('[data-ko-owner]'),
          owner_name: v('[data-ko-name]'), due_date: v('[data-ko-due]'), note: v('[data-ko-note]')})
          .then(r => after(r.notice || 'Gespeichert')).catch(err => { toast(err.message, true); window.wsOpenProposal(current.id); });
        return;
      }
      const it = e.target.closest('#ofPanel [data-ho-item]');
      if (it && current) {
        const note = it.closest('[data-ho-row]').querySelector('[data-ho-note]').value;
        api(`/workspace/proposals/${current.id}/abnahme`, 'POST', {action: 'item', item_id: Number(it.dataset.hoItem), state: it.value, note})
          .then(r => after(r.notice || 'Stand gespeichert')).catch(err => { toast(err.message, true); window.wsOpenProposal(current.id); });
        return;
      }
      const oc = e.target.closest('[data-of-fu-outcome]');
      if (oc) {
        const needs = ['entscheidung_offen', 'rueckfragen', 'nicht_erreicht'].includes(oc.value);
        oc.closest('[data-of-fu-item]').querySelectorAll('[data-of-fu-next],[data-of-fu-reason]').forEach(x => { x.disabled = !needs; });
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
