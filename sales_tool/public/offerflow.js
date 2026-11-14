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

  function stepRelease(s) {
    if (s.released) {
      return `<li class="of-step done"><b>1 · Versandfassung</b><span>✓ freigegeben am ${esc(fmtDate(s.released_at.slice(0, 10)))} · Stand <code>${esc(s.stand)}</code></span>
        ${s.stand_changed ? '<p class="qb-check warn">! Das gespeicherte Dokument weicht vom freigegebenen Stand ab. Bitte nicht versenden und neu erstellen.</p>' : ''}</li>`;
    }
    return `<li class="of-step"><b>1 · Versandfassung freigeben</b><p class="muted">Der Export trägt bis dahin sichtbar „Entwurf“. Freigeben heißt nicht versenden.</p>
      <ul class="of-checks">${s.checks.map(c => `<li>${mark(c.ok)} ${esc(c.label)}${c.detail ? ` <small class="muted">${esc(c.detail)}</small>` : ''}</li>`).join('')}</ul>
      ${s.hints.length ? `<div class="qb-check warn of-hints">${s.hints.map(h => '! ' + esc(h)).join('<br>')}</div>` : ''}
      <fieldset class="of-confirm" ${s.ready ? '' : 'disabled'}><legend>Vor dem Versand selbst geprüft</legend>
        ${Object.entries(s.confirmations).map(([k, v]) => `<label class="quote-addon"><input type="checkbox" data-of-confirm="${esc(k)}"><span>${esc(v)}</span></label>`).join('')}
        <button type="button" class="btn btn-primary" data-of-release>Versandfassung freigeben</button></fieldset></li>`;
  }

  function stepSend(s) {
    if (s.sent_at || s.status === 'gesendet_manuell') {
      return `<li class="of-step done"><b>2 · Versand</b><span>✓ ${s.sent_at ? `am ${esc(fmtDate(s.sent_at))} ${esc(s.channels[s.sent_channel] || '')} · Stand <code>${esc(s.sent_stand)}</code>` : 'als versendet dokumentiert (vor 2.0.0-dev17, ohne Stand)'}</span></li>`;
    }
    if (['angenommen', 'abgelehnt'].includes(s.status)) return '';
    return `<li class="of-step ${s.released ? '' : 'off'}"><b>2 · Versand dokumentieren</b><p class="muted">Erst nachdem du die freigegebene Fassung selbst verschickt hast.</p>
      <div class="sales-row"><label>Weg<select data-of-channel ${s.released ? '' : 'disabled'}>${opt(s.channels, 'email')}</select></label>
      <label>Datum<input type="date" data-of-sentdate value="${today()}" max="${today()}" ${s.released ? '' : 'disabled'}></label></div>
      <div class="sales-row"><label>Nachfassen am<input type="date" data-of-followdate value="${plusDays(today(), 7)}" min="${today()}" ${s.released ? '' : 'disabled'}></label>
      <label>Anlass<input data-of-followreason maxlength="160" placeholder="z. B. Entscheidung nach der Gesellschafterrunde" ${s.released ? '' : 'disabled'}></label>
      <button type="button" class="btn btn-ghost" data-of-sent ${s.released ? '' : 'disabled'}>Als versendet dokumentieren</button></div></li>`;
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
      return `<li class="of-step done"><b>3 · Entscheidung</b><span>${s.status === 'angenommen' ? '✓ angenommen' : '– abgelehnt'} am ${esc(fmtDate(s.decided_at))}${who ? ' · ' + esc(who) : ''}</span>${s.decision_note ? `<small class="muted">${esc(s.decision_note)}</small>` : ''}</li>`;
    }
    if (['angenommen', 'abgelehnt'].includes(s.status)) return `<li class="of-step done"><b>3 · Entscheidung</b><span>${s.status === 'angenommen' ? '✓ angenommen' : '– abgelehnt'} (vor 2.0.0-dev17 dokumentiert)</span></li>`;
    return `<li class="of-step ${s.released ? '' : 'off'}"><b>3 · Zusage oder Absage dokumentieren</b>
      <p class="muted">Eine positive Rückmeldung mit Änderungswünschen ist noch keine Zusage zu diesem Stand.</p>
      <div class="sales-row"><label>Weg<select data-of-dchannel ${s.released ? '' : 'disabled'}>${opt(s.decision_channels, 'email')}</select></label>
      <label>Person<input data-of-person maxlength="120" placeholder="Wer hat entschieden?" ${s.released ? '' : 'disabled'}></label>
      <label>Datum<input type="date" data-of-ddate value="${today()}" max="${today()}" ${s.released ? '' : 'disabled'}></label></div>
      <label>Notiz<input data-of-note maxlength="500" placeholder="z. B. Bestellnummer, Bedingungen" ${s.released ? '' : 'disabled'}></label>
      <div class="sales-row"><button type="button" class="btn btn-primary" data-of-decide="angenommen" ${s.released ? '' : 'disabled'}>Zusage dokumentieren</button>
      <button type="button" class="btn btn-ghost" data-of-decide="abgelehnt" ${s.released ? '' : 'disabled'}>Absage dokumentieren</button></div></li>`;
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
      <button type="button" class="btn btn-primary" data-of-start>${s.status === 'angenommen' ? 'Projektstart übernehmen' : 'Ausgewählte Aufgaben beenden'}</button></li>`;
  }

  async function render(id) {
    const box = $('#quoteSaved');
    if (!box) return;
    let s, p = null, f = null;
    try {
      s = await api('/workspace/proposals/' + id + '/versand');
      if (['angenommen', 'abgelehnt'].includes(s.status)) p = await api('/workspace/proposals/' + id + '/start');
      if (s.status !== 'entwurf') f = await api('/workspace/proposals/' + id + '/nachfassen');
    } catch (e) { toast(e.message, true); return; }
    current = {id, s, p};
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
      : `${stepRelease(s)}${stepSend(s)}${stepFollow(s, f)}${stepDecision(s)}${stepStart(p, s)}`;
    (head || box).insertAdjacentHTML(head ? 'afterend' : 'afterbegin', `<ol class="of-panel" id="ofPanel" data-of-id="${id}">${steps}</ol>
      <div class="of-revisions" id="ofRevisions">${s.revisable ? `<button type="button" class="btn btn-ghost" data-of-revise="${id}">Überarbeiten (neue Fassung)</button>` : ''}<div data-of-history></div></div>`);
    try {
      const h = await api(`/workspace/proposals/${id}/fassungen`);
      if (h.versions.length > 1) box.querySelector('[data-of-history]').innerHTML = `<details class="of-history"><summary>Fassungen (${h.versions.length})</summary><ol>${h.versions.map(v => `<li><b>${esc(v.number)}</b> · ${esc(v.offer_date ? fmtDate(v.offer_date) : '')} · ${v.net_eur != null ? esc(euros(v.net_eur)) + ' netto' : ''} · ${v.superseded ? 'ersetzt' : esc(v.status.replaceAll('_', ' '))}${v.reason ? `<small>Grund: ${esc(v.reason)}</small>` : ''}${v.changes.length ? `<ul>${v.changes.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}</li>`).join('')}</ol></details>`;
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
      const oc = e.target.closest('[data-of-fu-outcome]');
      if (oc) {
        const needs = ['entscheidung_offen', 'rueckfragen', 'nicht_erreicht'].includes(oc.value);
        oc.closest('[data-of-fu-item]').querySelectorAll('[data-of-fu-next],[data-of-fu-reason]').forEach(x => { x.disabled = !needs; });
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
