'use strict';
// 2.0.0-dev41 (Roadmap M24 Stufe 1): Kalender-Abo (iCalendar) und Termin-Export in „Einstellungen → Kalender & Postfach“.
// 2.0.0-dev42 (Roadmap M24 Stufe 2): Kalender-Abgleich über CalDAV – Adresse, Benutzername, Passwort (nie in der Datenbank),
// Verbindung prüfen, jetzt abgleichen, letzter Abgleich mit Hinweis bei veralteten Daten.
// 2.0.0-dev43 (Roadmap M24 Stufe 3): Postfach über IMAP – nur Entwürfe in den Entwürfe-Ordner, nie Versand.
(function () {
  const abs = path => (path ? location.origin + path : '');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const when = iso => (iso ? new Date(iso).toLocaleString('de-DE', {dateStyle: 'short', timeStyle: 'short'}) : 'noch nie');

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
    await loadCaldav();
  }

  async function save(body, msg) {
    try { await api('/kalender', 'POST', body); toast(msg); await load(); } catch (e) { toast(e.message, true); }
  }

  function renderCaldav(v) {
    const pw = v.password.stored ? (v.password.remembered ? 'hinterlegt (auf diesem Rechner gemerkt)' : 'hinterlegt (bis zum Neustart)') : 'nicht hinterlegt';
    $('#calCaldav').innerHTML = `
      <div class="sales-subhead">2 · Kalender-Abgleich (CalDAV, beide Richtungen)</div>
      <p class="muted">Termine aus SignalDesk erscheinen in deinem Kalender (nur Titel, Firma, Zeit, Ort). Aus dem Kalender liest SignalDesk nur „belegt von … bis …“ der nächsten 60 Tage – für Konfliktwarnungen und freie Vorschläge. Fremde Einträge werden nie geändert.</p>
      <form id="cdForm" class="sales-form" autocomplete="off">
        <label>Kalender-Adresse (HTTPS)<input name="url" id="cdUrl" type="url" placeholder="https://dav.anbieter.de/calendars/name/kalender/" value="${esc(v.url)}"></label>
        <label>Benutzername<input name="username" id="cdUser" value="${esc(v.username)}" autocomplete="off"></label>
        <label>Passwort (am besten App-Passwort)<input name="password" id="cdPass" type="password" autocomplete="new-password" placeholder="${v.password.stored ? '•••••• hinterlegt' : ''}"></label>
        <label class="check"><input type="checkbox" id="cdRemember" ${v.password.remembered ? 'checked' : ''}> auf diesem Rechner merken (eigene Datei, nicht in der Datenbank)</label>
        <div class="sales-row"><button class="btn" type="submit">Speichern</button>
          <button class="btn btn-ghost" type="button" id="cdTest" ${v.configured ? '' : 'disabled'}>Verbindung prüfen</button>
          <button class="btn btn-ghost" type="button" id="cdSync" ${v.configured ? '' : 'disabled'}>Jetzt abgleichen</button>
          ${v.password.stored ? '<button class="btn btn-ghost" type="button" id="cdForget">Passwort vergessen</button>' : ''}</div>
      </form>
      <p class="muted" id="cdStatus">Passwort: ${esc(pw)} · Letzter Abgleich: <span data-cd-last>${esc(when(v.last_sync))}</span>${v.last_result ? ' · ' + esc(v.last_result) : ''} · ${v.busy_count} belegte Zeit(en) bekannt</p>
      ${v.stale ? '<div class="sales-banner sales-warning" data-cd-stale>Der letzte Abgleich ist älter als 24 Stunden – belegte Zeiten können veraltet sein.</div>' : ''}
      <p class="muted">${esc(v.notice)}</p>`;
    $('#cdForm').addEventListener('submit', async e => {
      e.preventDefault();
      const body = {url: $('#cdUrl').value.trim(), username: $('#cdUser').value.trim(), remember: $('#cdRemember').checked};
      if ($('#cdPass').value) body.password = $('#cdPass').value;
      try { renderCaldav(await api('/caldav', 'POST', body)); toast('Kalender-Zugang gespeichert'); } catch (err) { toast(err.message, true); }
    });
    $('#cdTest').addEventListener('click', async () => {
      try { const r = await api('/caldav/test', 'POST', {}); toast(r.notice, !r.calendar); } catch (err) { toast(err.message, true); }
    });
    $('#cdSync').addEventListener('click', async () => {
      $('#cdSync').disabled = true;
      try { const r = await api('/caldav/sync', 'POST', {}); renderCaldav(r); toast('Abgleich fertig: ' + r.last_result); } catch (err) { toast(err.message, true); $('#cdSync').disabled = false; }
    });
    $('#cdForget')?.addEventListener('click', async () => {
      try { renderCaldav(await api('/caldav', 'POST', {forget: true})); toast('Passwort vergessen'); } catch (err) { toast(err.message, true); }
    });
  }

  function renderImap(v) {
    const pw = v.password.stored ? (v.password.remembered ? 'hinterlegt (auf diesem Rechner gemerkt)' : 'hinterlegt (bis zum Neustart)') : 'nicht hinterlegt';
    $('#calImap').innerHTML = `
      <div class="sales-subhead">3 · Postfach (IMAP, nur Entwürfe)</div>
      <p class="muted">SignalDesk legt einen fertigen Entwurf in den Entwürfe-Ordner deines Postfachs. Du prüfst ihn im Mailprogramm und versendest selbst. SignalDesk versendet nie und liest keine Nachrichten.</p>
      <form id="imForm" class="sales-form" autocomplete="off">
        <label>Postfach-Server (IMAP)<input name="host" id="imHost" placeholder="imap.anbieter.de" value="${esc(v.host)}"></label>
        <label>Port<input name="port" id="imPort" type="number" min="1" max="65535" value="${esc(v.port)}"></label>
        <label>Benutzername<input name="username" id="imUser" value="${esc(v.username)}" autocomplete="off"></label>
        <label>Absender (deine Adresse)<input name="sender" id="imSender" type="email" placeholder="hallo@deine-agentur.de" value="${esc(v.sender)}"></label>
        <label>Passwort (am besten App-Passwort)<input name="password" id="imPass" type="password" autocomplete="new-password" placeholder="${v.password.stored ? '•••••• hinterlegt' : ''}"></label>
        <label class="check"><input type="checkbox" id="imRemember" ${v.password.remembered ? 'checked' : ''}> auf diesem Rechner merken (eigene Datei, nicht in der Datenbank)</label>
        <div class="sales-row"><button class="btn" type="submit">Speichern</button>
          <button class="btn btn-ghost" type="button" id="imTest" ${v.configured ? '' : 'disabled'}>Verbindung prüfen</button>
          ${v.password.stored ? '<button class="btn btn-ghost" type="button" id="imForget">Passwort vergessen</button>' : ''}</div>
      </form>
      <p class="muted" id="imStatus">Passwort: ${esc(pw)} · Entwürfe-Ordner: ${esc(v.folder_label || 'noch nicht gesucht')}${v.last_result ? ' · ' + esc(v.last_result) : ''}</p>
      <p class="muted">${esc(v.notice)}</p>`;
    $('#imForm').addEventListener('submit', async e => {
      e.preventDefault();
      const body = {host: $('#imHost').value.trim(), port: Number($('#imPort').value || 993), username: $('#imUser').value.trim(),
                    sender: $('#imSender').value.trim(), remember: $('#imRemember').checked};
      if ($('#imPass').value) body.password = $('#imPass').value;
      try { renderImap(await api('/imap', 'POST', body)); toast('Postfach-Zugang gespeichert'); } catch (err) { toast(err.message, true); }
    });
    $('#imTest').addEventListener('click', async () => {
      try { const r = await api('/imap/test', 'POST', {}); renderImap(r); toast(r.last_result); } catch (err) { toast(err.message, true); }
    });
    $('#imForget')?.addEventListener('click', async () => {
      try { renderImap(await api('/imap', 'POST', {forget: true})); toast('Passwort vergessen'); } catch (err) { toast(err.message, true); }
    });
  }

  async function loadCaldav() {
    if (!$('#calCaldav')) return;
    try { renderCaldav(await api('/caldav')); } catch (e) { $('#calCaldav').textContent = e.message; }
    if ($('#calImap')) { try { renderImap(await api('/imap')); } catch (e) { $('#calImap').textContent = e.message; } }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#calEnabled')) return;
    $('#calEnabled').addEventListener('change', e => save({enabled: e.target.checked}, e.target.checked ? 'Kalender-Abo eingeschaltet' : 'Kalender-Abo ausgeschaltet – die Adresse gilt nicht mehr'));
    $('#calRegen').addEventListener('click', () => save({regenerate: true}, 'Neuer Schlüssel – die alte Adresse gilt nicht mehr'));
    $('#calCopy').addEventListener('click', () => navigator.clipboard.writeText($('#calUrl').value).then(() => toast('Abo-Adresse kopiert')));
    document.addEventListener('signaldesk:view', e => { if (e.detail.view === 'settings') load(); });
    // 2.0.0-dev43: Entwurf in den Entwürfe-Ordner legen (aus der Entwurfsliste)
    document.addEventListener('click', async e => {
      const b = e.target.closest('[data-ws-imap]');
      if (!b) return;
      b.disabled = true;
      try { const r = await api(`/workspace/mail-drafts/${b.dataset.wsImap}/postfach`, 'POST', {}); toast(r.notice); await window.refreshSalesWorkspace?.(); }
      catch (err) { toast(err.message, true); b.disabled = false; }
    });
    load();
  });
  window.refreshCalendarSettings = load;
})();
