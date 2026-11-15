'use strict';
// 2.0.0-dev26 (Roadmap M19): Bestandskunden – Betreuung (monatlich, mit Laufzeit und Monatsrechnungen), Projekte und neue
// Chancen getrennt. SignalDesk erstellt keine Rechnung von selbst: Der Knopf öffnet den Rechnungsentwurf für den ältesten offenen Monat.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const eur = v => Number(v || 0).toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' €';

  function careRow(k) {
    return `<li class="cr-care" data-cr-care="${k.proposal_id}"><div><b>${esc(k.number)}</b> ${esc(k.project_label)} · ${esc(eur(k.monthly_net_eur))} netto je Monat
        <span class="sw-web ${k.status === 'laufend' ? 'ok' : 'wait'}">${esc(k.status_label)}</span>
        <small>${esc(k.positions.join(' · '))} · seit ${esc(fmtDate(k.start_date))}${k.note ? ' · ' + esc(k.note) : ''}</small></div>
      ${k.due_months.length ? `<p class="rc-late">Nicht abgerechnet: ${esc(k.due_labels.join(', '))}</p>
        <button type="button" class="btn btn-primary" data-quote-invoice="${k.proposal_id}" data-mode="monat">Monatsrechnung ${esc(k.due_labels[0])} erstellen</button>` : '<p class="muted">Alle Monate bis heute abgerechnet.</p>'}
      <form class="sales-row cr-term" data-cr-term="${k.proposal_id}"><label>Beginn<input type="date" name="start_date" value="${esc(k.start_date)}" required></label>
        <label>Ende (optional)<input type="date" name="end_date" value="${esc(k.end_date)}"></label>
        <label>Notiz<input name="note" maxlength="300" value="${esc(k.note)}" placeholder="z. B. Kündigung per Mail vom …"></label>
        <button type="submit" class="btn btn-ghost">Laufzeit speichern</button></form></li>`;
  }

  function firm(f) {
    return `<article class="cr-firm" data-cr-firm="${f.lead_id}"><h3><button type="button" class="text-button" data-ws-lead="${f.lead_id}">${esc(f.company)}</button></h3>
      <div class="cr-cols">
        <div><div class="sales-subhead">Betreuung</div>${f.care.length ? `<ul class="cr-list">${f.care.map(careRow).join('')}</ul>` : '<p class="muted">Keine laufende Betreuung.</p>'}</div>
        <div><div class="sales-subhead">Projekte</div>${f.projects.length ? `<ul class="cr-list">${f.projects.map(p => `<li><button type="button" class="text-button" data-quote-open="${p.proposal_id}">${esc(p.number)}</button> ${esc(p.project_label)}${p.addendum_no ? ' (Zusatzauftrag)' : ''} · ${esc(eur(p.net_eur))} · <span class="sw-web ${p.handover.status === 'abgenommen' ? 'ok' : 'wait'}">${esc(p.handover.label)}</span></li>`).join('')}</ul>` : '<p class="muted">Kein einmaliges Projekt.</p>'}
          <div class="sales-subhead">Neue Projekte (Chancen)</div>${f.chances.length ? `<ul class="cr-list">${f.chances.map(c => `<li>${esc(c.title)} <small>${esc(c.stage)}</small></li>`).join('')}</ul>` : ''}
          <form class="sales-row" data-cr-chance="${f.lead_id}"><input name="title" maxlength="140" placeholder="Neues Projekt, z. B. Online-Shop" aria-label="Titel des neuen Projekts" required><button type="submit" class="btn btn-ghost">Als neue Chance anlegen</button></form></div>
      </div></article>`;
  }

  async function refresh() {
    const box = $('#crList');
    if (!box) return;
    try {
      const r = await api('/bestand');
      $('#crCount').textContent = r.firms.length ? `${r.firms.length} Firma(en) · ${r.care_count} Betreuung(en) · ${eur(r.monthly_net_eur)} netto je Monat${r.due_count ? ` · ${r.due_count} Monat(e) nicht abgerechnet` : ''}` : '';
      box.innerHTML = r.firms.length ? r.firms.map(firm).join('') : '<div class="empty">Noch kein angenommener Auftrag. Bestandskunden erscheinen hier nach der ersten Zusage.</div>';
    } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }
  window.refreshCare = refresh;

  document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('submit', async e => {
      const term = e.target.closest('[data-cr-term]'), ch = e.target.closest('[data-cr-chance]');
      if (!term && !ch) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const f = e.target.elements;
      try {
        if (term) {
          const k = await api(`/bestand/betreuung/${term.dataset.crTerm}`, 'PATCH', {start_date: f.start_date.value, end_date: f.end_date.value, note: f.note.value});
          toast(`Laufzeit gespeichert – ${k.status_label}`);
        } else {
          await api(`/leads/${ch.dataset.crChance}/chances`, 'POST', {title: f.title.value.trim()});
          toast('Neue Chance angelegt – getrennt von der Betreuung');
        }
        await refresh();
      } catch (err) { toast(err.message, true); }
    }, true);
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'quotes') refresh(); });
    const orig = window.reload;
    if (typeof orig === 'function') window.reload = async function (...args) { const r = await orig.apply(this, args); await refresh(); return r; };
    refresh();
  });
})();
