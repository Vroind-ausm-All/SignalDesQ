'use strict';
// 2.0.0-dev69 (R1.1): Source Registry unter Einstellungen → Datenquellen – je Quelle Prüfstand, Lizenz, Rechtsgrundlage,
// Grenzen, letzter Abruf; erlaubte Quellen kann die Verwaltung je Organisation aus- und wieder einschalten. Gesperrte oder
// nicht eingetragene Quellen ruft SignalDesk nie ab; das prüft der Server, nicht diese Seite.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const REVIEW = {freigegeben: ['fertig', 'freigegeben'], vorlaeufig: ['retry', 'vorläufig – Freigabe offen (E2)'],
    ungeprueft: ['fehler', 'ungeprüft – aus'], gesperrt: ['fehler', 'nur manuell – nie abgerufen']};
  const day = t => (t ? fmtDate(String(t).slice(0, 10)) : '–');

  function row(s) {
    const [cls, label] = REVIEW[s.review] || ['', s.review];
    const who = s.review === 'freigegeben' && s.approved_by ? ` · ${esc(s.approved_by)}` : '';
    const state = s.switchable ? (s.enabled ? 'an' : 'aus') : 'aus';
    const btn = s.switchable ? `<button type="button" class="text-button" data-src-toggle="${esc(s.id)}" data-src-on="${s.enabled ? '0' : '1'}">${s.enabled ? 'Ausschalten' : 'Einschalten'}</button>` : '';
    const m = s.measured || {};
    return `<div class="sw-src ${s.enabled ? cls : 'fehler'}" data-src-row="${esc(s.id)}"><b>${esc(s.title)}</b><span class="sw-st ${cls}">${esc(label)}</span>
      <small>${state === 'an' ? 'an' : '<span class="late">aus</span>'} · ${esc(s.license)} · Stand ${esc(s.checked)} · ${esc(s.legal_basis)}
      ${who} · ${esc(s.rate)}${s.access === 'api' ? ` · letzter Erfolg ${day(m.last_success)} · letzter Fehler ${day(m.last_failure)}` : ''} ${btn}</small></div>`;
  }

  async function load() {
    const box = $('#srcRows');
    if (!box) return;
    try {
      const r = await api('/sources');
      const on = r.sources.filter(s => s.enabled).length;
      $('#srcSummary').textContent = `${on} von ${r.sources.length} Quellen an` + (r.pending_approval.length ? ` · ${r.pending_approval.length} vorläufig, Freigabe offen` : '');
      $('#srcNotice').textContent = r.notice || '';
      box.innerHTML = r.sources.map(row).join('');
    } catch (e) { $('#srcSummary').textContent = e.message; }
  }

  function init() {
    if (!$('#srcBox')) return;
    $('#srcBox').addEventListener('toggle', () => { if ($('#srcBox').open) load(); });
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'settings') load(); });
    $('#srcRows').addEventListener('click', async e => {
      const b = e.target.closest('[data-src-toggle]');
      if (!b) return;
      b.disabled = true;
      try { await api('/sources/' + b.dataset.srcToggle, 'PUT', {enabled: b.dataset.srcOn === '1'}); toast('Gespeichert.'); }
      catch (err) { toast(err.message, true); }
      load();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
