'use strict';
// v1.8 Datenqualität & System: Änderungen, Veraltung, Löschfristen, wiederkehrende Aufträge, Einstellungen,
// Login/Rollen und Datensicherung. Nichts wird ohne Bestätigung überschrieben, gelöscht oder versendet.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const KIND = {impressum: 'Impressum', website: 'Website', register: 'Register'};
  const JOB_STATUS = {ok: 'ok', fehler: 'Fehler', nichts_zu_tun: 'nichts fällig', '': 'noch nicht gelaufen'};
  let auth = null;

  const dateTime = s => s ? s.replace('T', ' ').slice(0, 16) : '–';

  async function loadChanges() {
    const rows = await api('/quality/changes');
    $('#qChanges').innerHTML = rows.length ? rows.map(c => `<div class="sales-item q-change"><div>
        <strong>${esc(c.company)} · ${esc(KIND[c.kind] || c.kind)}: ${esc(c.label)}</strong>
        <small>bisher: <b>${esc(c.old_value || '–')}</b> → neu: <b>${esc(c.new_value)}</b>${c.source_url ? ` · <a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">Quelle</a>` : ''} · erkannt ${esc(dateTime(c.detected_at))} (UTC)</small>
        ${c.excerpt ? `<small class="q-excerpt">„${esc(c.excerpt.slice(0, 220))}“</small>` : ''}</div>
      <div class="acc-btn-group">${c.can_apply ? `<button type="button" class="btn btn-primary" data-q-change="${c.id}" data-d="uebernehmen">Übernehmen</button>` : ''}<button type="button" class="btn btn-ghost" data-q-change="${c.id}" data-d="erledigt">Erledigt</button><button type="button" class="btn btn-ghost" data-q-change="${c.id}" data-d="ignorieren">Ignorieren</button></div></div>`).join('')
      : '<div class="empty">Keine offenen Änderungen.</div>';
    return rows.length;
  }

  async function loadStale() {
    const d = await api('/quality/staleness');
    $('#qStaleNotice').textContent = d.notice;
    $('#qStale').innerHTML = d.leads.length ? d.leads.map(l => `<div class="sales-item"><div><strong>${esc(l.company)}</strong>
        ${l.items.map(i => `<small><span class="rc-stale">${esc(i.label)}</span> ${esc(i.detail)} (Frist ${i.limit_days} Tage)</small>`).join('')}</div>
        <button type="button" class="btn btn-ghost" data-q-lead="${l.lead_id}">Lead öffnen</button></div>`).join('')
      : '<div class="empty">Keine veralteten Daten.</div>';
    $('#qPrivacy').innerHTML = d.privacy_expired.length ? d.privacy_expired.map(p => `<div class="sales-item"><div><strong>${esc(p.subject)}</strong>
        <small>${esc(p.company || 'ohne Lead')} · Frist abgelaufen am ${esc(fmtDate(p.retention_until))} · ${esc(p.purpose)}</small></div>
        <button type="button" class="btn btn-danger" data-q-erase="${p.id}">Personendaten löschen</button></div>`).join('')
      : '<div class="empty">Keine abgelaufenen Löschfristen.</div>';
    return d;
  }

  async function loadJobs() {
    const d = await api('/quality/jobs');
    $('#qJobsNotice').textContent = d.notice;
    if (!$('#qJobKind').options.length) $('#qJobKind').innerHTML = Object.entries(d.kinds).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
    $('#qJobs').innerHTML = d.jobs.length ? d.jobs.map(j => `<div class="sales-item"><div><strong>${esc(j.label)} ${j.enabled ? '' : '<span class="si-perm abgelehnt">pausiert</span>'}</strong>
        <small>${esc(j.kind_label)} · alle ${j.interval_days} Tage · nächster Lauf ${esc(dateTime(j.next_run_at))} (UTC)</small>
        <small>Letzter Lauf: ${esc(dateTime(j.last_run_at))} · <span class="q-status ${esc(j.last_status)}">${esc(JOB_STATUS[j.last_status] || j.last_status)}</span>${j.last_detail ? ' · ' + esc(j.last_detail) : ''}</small></div>
      <div class="acc-btn-group"><button type="button" class="btn btn-primary" data-q-run="${j.id}">Jetzt ausführen</button><button type="button" class="btn btn-ghost" data-q-toggle="${j.id}" data-on="${j.enabled ? 0 : 1}">${j.enabled ? 'Pausieren' : 'Aktivieren'}</button><button type="button" class="btn btn-ghost" data-q-del="${j.id}">Löschen</button></div></div>`).join('')
      : '<div class="empty">Noch keine wiederkehrenden Aufträge.</div>';
  }

  async function loadSettings() {
    const d = await api('/quality/settings');
    const f = $('#qSettingsForm');
    f.elements.w_website.value = d.priority_weights.website;
    f.elements.w_signal.value = d.priority_weights.signal;
    f.elements.w_fit.value = d.priority_weights.fit;
    $('#qStaleInputs').innerHTML = Object.entries(d.stale_days).map(([k, v]) => `<label>${esc(d.stale_labels[k])}<input name="s_${esc(k)}" type="number" min="7" max="1095" value="${v}" required></label>`).join('');
  }

  async function loadSecurity() {
    const d = await api('/system/security');
    $('#qSecurity').innerHTML = d.checks.map(c => `<div class="sales-item q-check"><div><strong>${c.ok ? '✓' : '!'} ${esc(c.label)}</strong>${c.detail ? `<small>${esc(c.detail)}</small>` : ''}</div></div>`).join('')
      + `<small class="muted">Schema-Version ${d.schema_version} · ${esc(d.server_version)}</small>`;
  }

  async function loadAuth() {
    auth = await api('/auth/status');
    renderAuthBar();
    const box = $('#qAuth');
    if (!auth.has_users) {
      box.innerHTML = `<p class="muted">${esc(auth.notice)}</p><form id="qSetupForm" class="sales-form"><b>Administration anlegen</b>
        <div class="sales-row"><label>Benutzername<input name="username" required minlength="3" maxlength="40" autocomplete="username"></label><label>Anzeigename<input name="display_name" maxlength="80"></label></div>
        <label>Passwort (mind. 10 Zeichen)<input name="password" type="password" required minlength="10" maxlength="200" autocomplete="new-password"></label>
        <button type="submit" class="btn btn-ghost">Administration anlegen & anmelden</button></form>`;
      return;
    }
    const me = auth.user;
    let html = `<p class="muted">Login ist <b>${auth.auth_required ? 'eingeschaltet' : 'ausgeschaltet'}</b>. ${me ? `Angemeldet als <b>${esc(me.display_name || me.username)}</b> (${esc(me.role)}).` : 'Nicht angemeldet.'}</p>`;
    if (!me) html += '<button type="button" class="btn btn-ghost" data-q-login>Anmelden</button>';
    if (me && me.role === 'admin') {
      const users = await api('/auth/users');
      html += `<div class="acc-btn-group"><button type="button" class="btn ${auth.auth_required ? 'btn-ghost' : 'btn-primary'}" data-q-authreq="${auth.auth_required ? 0 : 1}">${auth.auth_required ? 'Login ausschalten' : 'Login einschalten'}</button></div>
        <div class="sales-list">${users.map(u => `<div class="sales-item"><div><strong>${esc(u.display_name || u.username)} <small>@${esc(u.username)}</small></strong><small>${esc(auth.roles[u.role] || u.role)}${u.active ? '' : ' · deaktiviert'} · letzter Login ${esc(dateTime(u.last_login_at))}</small></div>
          <div class="acc-btn-group"><select data-q-role="${u.id}" aria-label="Rolle">${Object.keys(auth.roles).map(r => `<option value="${r}" ${u.role === r ? 'selected' : ''}>${r}</option>`).join('')}</select>
          <button type="button" class="btn btn-ghost" data-q-active="${u.id}" data-on="${u.active ? 0 : 1}">${u.active ? 'Deaktivieren' : 'Aktivieren'}</button></div></div>`).join('')}</div>
        <form id="qUserForm" class="sales-form"><b>Benutzer anlegen</b><div class="sales-row"><label>Benutzername<input name="username" required minlength="3" maxlength="40"></label><label>Rolle<select name="role">${Object.entries(auth.roles).map(([k, v]) => `<option value="${k}" ${k === 'vertrieb' ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label></div>
        <div class="sales-row"><label>Anzeigename<input name="display_name" maxlength="80"></label><label>Startpasswort (mind. 10 Zeichen)<input name="password" type="password" required minlength="10" maxlength="200" autocomplete="new-password"></label></div>
        <button type="submit" class="btn btn-ghost">Benutzer anlegen</button></form>`;
    }
    if (me) html += `<form id="qPwForm" class="sales-form"><b>Eigenes Passwort ändern</b><div class="sales-row"><label>Bisher<input name="old_password" type="password" required autocomplete="current-password"></label><label>Neu (mind. 10 Zeichen)<input name="new_password" type="password" required minlength="10" autocomplete="new-password"></label></div><button type="submit" class="btn btn-ghost">Passwort ändern</button></form>`;
    box.innerHTML = html;
  }

  function renderAuthBar() {
    const bar = $('#authBar');
    if (!bar || !auth) return;
    bar.classList.toggle('hidden', !auth.user);
    bar.innerHTML = auth.user ? `${esc(auth.user.display_name || auth.user.username)} · ${esc(auth.user.role)} <button type="button" class="text-button" data-q-logout>Abmelden</button>` : '';
  }

  async function loadResearchTech() {
    if (!$('#rtForm')) return;
    const r = await api('/research/settings');
    const f = $('#rtForm').elements;
    f.fetcher.value = r.settings.fetcher; f.parser.value = r.settings.parser; f.browser_fallback.value = String(r.settings.browser_fallback);
    f.content.value = r.settings.content || 'stdlib';
    $('#rtNotice').textContent = r.notice;
    $('#rtStatus').textContent = `In Benutzung: Auswertung ${r.parser_in_use === 'scrapling' ? 'Scrapling ' + r.scrapling.version : 'eingebaut'}`
      + ` · Scrapling ${r.scrapling.installed ? 'installiert' : 'nicht installiert (optional: requirements-research.txt)'}`
      + ` · Trafilatura ${r.trafilatura && r.trafilatura.installed ? 'installiert' : 'nicht installiert'}`
      + ` · Browser ${r.browser.installed ? 'installiert' : 'nicht installiert'}`;
  }

  // v1.17: doppelte Firmen im CRM – nur Vorschläge, zusammengeführt wird erst auf Klick
  let dupPairs = [];
  async function loadDups() {
    const d = await api('/leads/duplicates');
    dupPairs = d.pairs;
    const side = (l, inv) => `<div class="q-dup-side"><b>#${l.id} ${esc(l.company)}</b><small>${esc([l.legal_form, l.location, l.register_number, (l.website || '').replace(/^https?:\/\//, '')].filter(Boolean).join(' · ') || '–')}</small>
      <small>Phase ${esc(l.stage)} · seit ${esc(fmtDate((l.created_at || '').slice(0, 10)))}${inv ? ` · <b>${inv} Rechnung(en)</b>` : ''}</small></div>`;
    $('#qDups').innerHTML = d.pairs.length ? d.pairs.map((p, i) => {
      const invK = p.invoices[String(p.keep.id)], invD = p.invoices[String(p.drop.id)];
      const [keep, drop] = invD && !invK ? [p.drop, p.keep] : [p.keep, p.drop];
      return `<div class="sales-item q-dup"><div class="q-dup-pair">${side(keep, p.invoices[String(keep.id)])}<span class="q-dup-arrow" aria-hidden="true">⟵</span>${side(drop, p.invoices[String(drop.id)])}</div>
        <small><span class="sw-web ${p.verdict === 'same' ? 'ok' : 'mid'}">${p.verdict === 'same' ? 'sicher gleich' : 'möglich'}</span> ${esc(p.reason)}</small>
        <div class="acc-btn-group">${invK && invD ? '<span class="muted">Beide haben Rechnungen – nicht zusammenführbar</span>' : `<button type="button" class="btn btn-primary" data-q-merge="${i}" data-keep="${keep.id}" data-drop="${drop.id}">Zusammenführen (#${keep.id} behalten)</button>`}
        <button type="button" class="btn btn-ghost" data-q-notdup="${i}">Keine Dublette</button></div></div>`;
    }).join('') : '<div class="empty">Keine doppelten Firmen gefunden.</div>';
    return d.total;
  }

  // v1.19: Wiederherstellen, Offline-Modus, automatische Firmendaten
  async function loadRestore() {
    const [b, off, ai] = await Promise.all([api('/backups/all'), api('/system/offline'), api('/settings/auto-imprint')]);
    $('#qBackups').innerHTML = b.backups.length ? b.backups.slice(0, 12).map(x => `<div class="sales-item"><div><strong>${esc(x.name)}</strong>
      <small>${esc(x.modified.replace('T', ' '))} · ${(x.size_bytes / 1e6).toFixed(1)} MB${x.encrypted ? ' · verschlüsselt' : ''}${x.before_restore ? ' · Stand vor einer Wiederherstellung' : ''}</small></div>
      <button type="button" class="btn btn-ghost" data-q-restore="${esc(x.name)}" data-enc="${x.encrypted ? 1 : 0}">Wiederherstellen</button></div>`).join('')
      : `<div class="empty">Noch keine Sicherung in ${esc(b.folder)}.</div>`;
    $('#qOffline').checked = off.offline;
    $('#qOffline').disabled = off.forced;
    $('#qOfflineState').textContent = off.forced ? 'für diese Sitzung beim Start eingeschaltet (--offline)' : off.offline ? 'eingeschaltet' : '';
    $('#qAutoImprint').checked = ai.enabled;
    window.setOfflineBadge?.(off);
  }

  async function doRestore(name, encrypted, file) {
    const what = file ? `die Datei „${file.name}“` : `„${name}“`;
    if (!confirm(`${what} wiederherstellen?\n\nDer aktuelle Stand wird vorher automatisch gesichert. Danach lädt SignalDesk neu.`)) return;
    const password = encrypted ? prompt('Passwort der verschlüsselten Sicherung') : null;
    if (encrypted && !password) return;
    try {
      let r;
      if (file) {
        const resp = await fetch('/api/backups/restore-upload?confirm=1', {method: 'POST', body: file,
          headers: {'Content-Type': 'application/octet-stream', ...(password ? {'X-Backup-Password': password} : {})}});
        r = await resp.json();
        if (!resp.ok) throw Error(r.error || 'Wiederherstellung fehlgeschlagen');
      } else r = await api('/backups/restore', 'POST', {name, confirm: true, ...(password ? {password} : {})});
      alert(`Wiederhergestellt: ${r.after.leads} Leads, ${r.after.invoices} Rechnungen.\nVorheriger Stand gesichert: ${r.safety_backup || '–'}`);
      location.reload();
    } catch (e) { toast(e.message, true); }
  }

  window.refreshQuality = async function () {
    if (!$('#viewQuality')) return;
    try {
      const [changes, stale] = await Promise.all([loadChanges(), loadStale(), loadJobs(), loadSettings(), loadSecurity(), loadAuth(), loadResearchTech(), loadDups(), loadRestore()]);
      $('#qMetrics').innerHTML = `<div class="panel"><small>Offene Änderungen</small><strong>${changes}</strong></div><div class="panel"><small>Firmen mit veralteten Daten</small><strong>${stale.leads.length}</strong></div><div class="panel"><small>Abgelaufene Löschfristen</small><strong>${stale.privacy_expired.length}</strong></div>`;
      const badge = changes + stale.privacy_expired.length;
      $('#qNavBadge').textContent = badge ? String(badge) : '';
    } catch (e) { toast(e.message, true); }
  };

  window.showLogin = function () {
    const o = $('#loginOverlay');
    if (!o || !o.classList.contains('hidden')) return;
    o.classList.remove('hidden');
    setTimeout(() => $('#loginForm [name=username]').focus(), 50);
  };

  async function act(fn, ok) {
    try { const r = await fn(); if (ok) toast(typeof ok === 'function' ? ok(r) : ok); await window.refreshQuality(); }
    catch (e) { toast(e.message, true); }
  }

  function init() {
    if (!$('#viewQuality')) return;
    $('#qDupsReload').addEventListener('click', () => loadDups().then(n => toast(`${n} mögliche Dublette(n)`)).catch(e => toast(e.message, true)));
    $('#qDetect').addEventListener('click', () => act(() => api('/quality/changes/detect', 'POST', {}), r => `${r.impressum + r.website + r.register} neue Änderung(en) erkannt`));
    $('#qRestoreFile').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) doRestore('', /\.sdenc$/i.test(f.name), f); });
    $('#qOffline').addEventListener('change', e => act(() => api('/system/offline', 'PUT', {enabled: e.target.checked}), r => r.offline ? 'Offline-Modus an – keine Abrufe aus dem Internet' : 'Wieder online – wartende Aufträge laufen weiter'));
    $('#qAutoImprint').addEventListener('change', e => act(() => api('/settings/auto-imprint', 'PUT', {enabled: e.target.checked}), r => r.enabled ? 'Firmendaten werden automatisch übertragen' : 'Automatische Übertragung aus'));
    $('#qBackup').addEventListener('click', () => act(() => api('/backup', 'POST', {}), r => 'Gesichert: ' + r.path));
    $('#qEncForm').addEventListener('submit', e => { e.preventDefault(); const pw = e.target.elements.password.value; e.target.reset(); act(() => api('/backup/encrypted', 'POST', {password: pw}), r => r.notice); });
    $('#qJobKind').addEventListener('change', e => {
      const finder = e.target.value === 'lead_finder_suche', dq = e.target.value === 'datenqualitaet_pruefen';
      $('.q-finder').classList.toggle('hidden', !finder);
      $('.q-limit').classList.toggle('hidden', finder || dq);
    });
    $('#qJobForm').addEventListener('submit', e => {
      e.preventDefault();
      const f = e.target.elements, kind = f.kind.value;
      let params = {};
      if (kind === 'lead_finder_suche') {
        params = {source: f.source.value};
        if (f.source.value !== 'ted') params.place = f.place.value.trim();
        if (['wikidata', 'gleif'].includes(f.source.value) && f.keyword.value.trim()) params.keyword = f.keyword.value.trim();
      } else if (kind !== 'datenqualitaet_pruefen') params = {limit: Number(f.limit.value)};
      const body = {kind, interval_days: Number(f.interval_days.value), params};
      if (f.label.value.trim()) body.label = f.label.value.trim();
      act(() => api('/quality/jobs', 'POST', body), 'Auftrag angelegt – erster Lauf in etwa 5 Minuten oder über „Jetzt ausführen“');
    });
    $('#rtForm')?.addEventListener('submit', e => {
      e.preventDefault();
      const f = e.target.elements;
      act(() => api('/research/settings', 'POST', {fetcher: f.fetcher.value, parser: f.parser.value, content: f.content.value, browser_fallback: f.browser_fallback.value === 'true'}),
        'Recherche-Technik gespeichert');
    });
    $('#qSettingsForm').addEventListener('submit', e => {
      e.preventDefault();
      const f = e.target.elements;
      const stale = {};
      $$('#qStaleInputs input').forEach(i => { stale[i.name.slice(2)] = Number(i.value); });
      act(() => api('/quality/settings', 'PUT', {priority_weights: {website: Number(f.w_website.value), signal: Number(f.w_signal.value), fit: Number(f.w_fit.value)}, stale_days: stale}), 'Einstellungen gespeichert');
    });
    $('#loginForm').addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target.elements;
      try { await api('/auth/login', 'POST', {username: f.username.value, password: f.password.value}); location.reload(); }
      catch (err) { $('#loginError').textContent = err.message; $('#loginError').classList.remove('hidden'); f.password.value = ''; }
    });
    document.body.addEventListener('click', e => {
      const t = e.target;
      const c = t.closest('[data-q-change]'); if (c) return act(() => api(`/quality/changes/${c.dataset.qChange}`, 'POST', {decision: c.dataset.d}), 'Gespeichert');
      const l = t.closest('[data-q-lead]'); if (l) return showModal(Number(l.dataset.qLead));
      const rs = t.closest('[data-q-restore]'); if (rs) return doRestore(rs.dataset.qRestore, rs.dataset.enc === '1');
      const mg = t.closest('[data-q-merge]');
      if (mg) {
        const p = dupPairs[Number(mg.dataset.qMerge)];
        const keep = Number(mg.dataset.keep), drop = Number(mg.dataset.drop);
        const dn = (p.keep.id === drop ? p.keep : p.drop).company;
        if (confirm(`„${dn}“ (#${drop}) in #${keep} zusammenführen?\n\nAktivitäten, Aufgaben, Belege, Berichte und Signale wandern mit, leere Felder werden ergänzt. #${drop} wird danach gelöscht.`))
          act(() => api('/leads/merge', 'POST', {keep, drop}), r => { const n = Object.values(r.moved).reduce((a, b) => a + b, 0); return `Zusammengeführt: ${n} verknüpfte${n === 1 ? 'r Eintrag' : ' Einträge'} übernommen${r.filled.length ? ` · ${r.filled.length === 1 ? '1 leeres Feld' : r.filled.length + ' leere Felder'} ergänzt` : ''}`; }).then(() => { if (typeof reload === 'function') reload(); });
        return;
      }
      const nd = t.closest('[data-q-notdup]');
      if (nd) { const p = dupPairs[Number(nd.dataset.qNotdup)]; return act(() => api('/leads/not-duplicate', 'POST', {a: p.keep.id, b: p.drop.id}), 'Gemerkt – wird nicht wieder vorgeschlagen'); }
      const er = t.closest('[data-q-erase]');
      if (er) { if (confirm('Personendaten dieses Ansprechpartners endgültig löschen? Der Löschnachweis enthält keine Personendaten.')) act(() => api(`/quality/privacy/${er.dataset.qErase}/erase`, 'POST', {confirm: true}), 'Gelöscht'); return; }
      const r = t.closest('[data-q-run]'); if (r) return act(() => api(`/quality/jobs/${r.dataset.qRun}/run`, 'POST', {}), j => `${j.label}: ${j.last_detail || j.last_status}`);
      const tg = t.closest('[data-q-toggle]'); if (tg) return act(() => api(`/quality/jobs/${tg.dataset.qToggle}`, 'PATCH', {enabled: tg.dataset.on === '1'}));
      const d = t.closest('[data-q-del]'); if (d) { if (confirm('Auftrag löschen?')) act(() => api(`/quality/jobs/${d.dataset.qDel}`, 'DELETE'), 'Gelöscht'); return; }
      const ar = t.closest('[data-q-authreq]'); if (ar) return act(() => api('/auth/settings', 'PUT', {auth_required: ar.dataset.qAuthreq === '1'}), r2 => r2.auth_required ? 'Login ist jetzt Pflicht' : 'Login ausgeschaltet');
      const ac = t.closest('[data-q-active]'); if (ac) return act(() => api(`/auth/users/${ac.dataset.qActive}`, 'PATCH', {active: ac.dataset.on === '1'}), 'Gespeichert');
      if (t.closest('[data-q-login]')) return window.showLogin();
      if (t.closest('[data-q-logout]')) return api('/auth/logout', 'POST', {}).then(() => location.reload()).catch(err => toast(err.message, true));
    });
    document.body.addEventListener('change', e => {
      const r = e.target.closest('[data-q-role]'); if (r) act(() => api(`/auth/users/${r.dataset.qRole}`, 'PATCH', {role: r.value}), 'Rolle geändert');
    });
    document.body.addEventListener('submit', e => {
      const f = e.target;
      if (f.id === 'qSetupForm') { e.preventDefault(); act(() => api('/auth/setup', 'POST', {username: f.elements.username.value, password: f.elements.password.value, display_name: f.elements.display_name.value}), 'Administration angelegt und angemeldet'); }
      if (f.id === 'qUserForm') { e.preventDefault(); act(() => api('/auth/users', 'POST', {username: f.elements.username.value, password: f.elements.password.value, display_name: f.elements.display_name.value, role: f.elements.role.value}), 'Benutzer angelegt'); }
      if (f.id === 'qPwForm') { e.preventDefault(); act(() => api('/auth/password', 'POST', {old_password: f.elements.old_password.value, new_password: f.elements.new_password.value}), 'Passwort geändert – bitte neu anmelden').then(() => location.reload()); }
    });
    api('/auth/status').then(s => { auth = s; renderAuthBar(); if (s.auth_required && !s.user) window.showLogin(); }).catch(() => {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
