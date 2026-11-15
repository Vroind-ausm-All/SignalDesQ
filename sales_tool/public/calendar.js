'use strict';
// 2.0.0-dev41 (Roadmap M24 Stufe 1): Kalender-Abo (iCalendar) und Termin-Export in „Einstellungen → Kalender & Postfach“.
(function () {
  const abs = path => (path ? location.origin + path : '');

  async function load() {
    if (!$('#calEnabled')) return;
    try {
      const v = await api('/kalender');
      $('#calEnabled').checked = v.enabled;
      $('#calUrl').value = abs(v.path);
      $('#calNotice').textContent = v.notice;
      $('#calCopy').disabled = !v.enabled;
      $('#calRegen').disabled = !v.enabled;
    } catch (e) { $('#calNotice').textContent = e.message; }
  }

  async function save(body, msg) {
    try { await api('/kalender', 'POST', body); toast(msg); await load(); } catch (e) { toast(e.message, true); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#calEnabled')) return;
    $('#calEnabled').addEventListener('change', e => save({enabled: e.target.checked}, e.target.checked ? 'Kalender-Abo eingeschaltet' : 'Kalender-Abo ausgeschaltet – die Adresse gilt nicht mehr'));
    $('#calRegen').addEventListener('click', () => save({regenerate: true}, 'Neuer Schlüssel – die alte Adresse gilt nicht mehr'));
    $('#calCopy').addEventListener('click', () => navigator.clipboard.writeText($('#calUrl').value).then(() => toast('Abo-Adresse kopiert')));
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'settings') load(); });
    load();
  });
  window.refreshCalendarSettings = load;
})();
