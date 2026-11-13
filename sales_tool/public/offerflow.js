'use strict';
// 2.0.0-dev17 (Roadmap M35, M36): Versandfassung freigeben, Versand und Zusage mit Weg, Zeitpunkt und Stand dokumentieren,
// danach den Projektstart festlegen. Ersetzt im gespeicherten Angebot die freie Statusauswahl. SignalDesk versendet nichts.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const today = () => new Date().toISOString().slice(0, 10);
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
      <label>Datum<input type="date" data-of-sentdate value="${today()}" max="${today()}" ${s.released ? '' : 'disabled'}></label>
      <button type="button" class="btn btn-ghost" data-of-sent ${s.released ? '' : 'disabled'}>Als versendet dokumentieren</button></div></li>`;
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
    let s, p = null;
    try {
      s = await api('/workspace/proposals/' + id + '/versand');
      if (['angenommen', 'abgelehnt'].includes(s.status)) p = await api('/workspace/proposals/' + id + '/start');
    } catch (e) { toast(e.message, true); return; }
    current = {id, s, p};
    box.querySelector('[data-quote-status]')?.closest('label')?.remove();
    const exp = box.querySelector('[data-quote-export]');
    if (exp) exp.textContent = s.released && !s.stand_changed ? 'Versandfassung herunterladen (.md)' : 'Entwurf herunterladen (.md)';
    const cp = box.querySelector('[data-quote-copy]');
    if (cp) cp.textContent = s.released && !s.stand_changed ? 'Versandfassung kopieren' : 'Entwurf kopieren';
    box.querySelector('#ofPanel')?.remove();
    const head = box.querySelector('h3');
    (head || box).insertAdjacentHTML(head ? 'afterend' : 'afterbegin', `<ol class="of-panel" id="ofPanel" data-of-id="${id}">${stepRelease(s)}${stepSend(s)}${stepDecision(s)}${stepStart(p, s)}</ol>`);
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
          const r = await api('/workspace/proposals/' + id, 'PATCH', {status: 'gesendet_manuell', channel: panel.querySelector('[data-of-channel]').value, date: panel.querySelector('[data-of-sentdate]').value});
          return after(r.notice);
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
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
