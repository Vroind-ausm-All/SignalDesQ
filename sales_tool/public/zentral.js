// SDQ-014/021: zentrale Anmeldung einer Mehrmandanten-Installation – Konto anmelden (Passwort, ggf. Code aus der App),
// zweiten Faktor einrichten, Organisation wählen oder wechseln. SDQ-027: registrieren, Einladung annehmen, Mitglieder verwalten.
(function () {
  const $ = s => document.querySelector(s);
  const msg = t => { $('#zMsg').textContent = t || ''; };
  const views = ['#zLogin', '#zCode', '#zSetup', '#zSuggest', '#zOrgs', '#zRegister', '#zInvite', '#zTeam'];
  const KEY = 'sd_einladung';
  const store = {get: () => { try { return sessionStorage.getItem(KEY) || ''; } catch (e) { return ''; } },
    set: v => { try { v ? sessionStorage.setItem(KEY, v) : sessionStorage.removeItem(KEY); } catch (e) { /* ohne Speicher */ } }};
  let teamSlug = '';
  const show = id => views.forEach(v => $(v).classList.toggle('hidden', v !== id));
  async function call(path, body) {
    const del = body === null;
    const opts = body === undefined ? {} : del ? {method: 'DELETE'} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
    const r = await fetch('/api/zentral/' + path, opts);
    const data = await r.json();
    if (!r.ok) throw Error(data.error || 'Anfrage fehlgeschlagen');
    return data;
  }
  function showSetup(required) {
    $('#zSetupWhy').textContent = required ? 'Für dieses Konto ist ein zweiter Faktor vorgeschrieben.'
      : 'Nach dem Passwort fragt SignalDesk dann zusätzlich einen Code aus der App ab.';
    $('#zSetupStart').classList.remove('hidden');
    $('#zSetupConfirm').classList.add('hidden');
    $('#zCodes').classList.add('hidden');
    show('#zSetup');
  }
  function showOrgs(s) {
    show('#zOrgs');
    $('#zWho').textContent = 'Angemeldet als ' + (s.user.display_name || s.user.username) + '.';
    const list = $('#zOrgList');
    list.textContent = '';
    for (const o of s.organizations) {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn ' + (o.slug === s.current ? 'btn-primary' : 'btn-ghost');
      b.dataset.zOrg = o.slug;
      b.textContent = o.name + ' · ' + o.role + (o.slug === s.current ? ' (aktuell)' : '');
      li.appendChild(b);
      list.appendChild(li);
    }
    $('#zNone').classList.toggle('hidden', s.organizations.length > 0);
    $('#zMfaState').textContent = s.two_factor ? 'an' : 'aus (empfohlen: einrichten)';
    $('#zMfaInfo').textContent = s.two_factor
      ? 'Noch ' + s.recovery_codes_left + ' Wiederherstellungscodes übrig.' + (s.require_2fa ? ' In dieser Installation Pflicht.' : '')
      : 'Empfohlen: schützt das Konto, wenn das Passwort bekannt wird. Freiwillig, solange die Installation ihn nicht vorschreibt.';
    $('#zMfaOn').classList.toggle('hidden', !!s.two_factor);
    $('#zMfaOff').classList.toggle('hidden', !s.two_factor || !!s.require_2fa);
    const admin = $('#zAdminOrgs');
    admin.textContent = '';
    for (const o of s.organizations.filter(x => x.role === 'admin')) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-ghost';
      b.dataset.zTeam = o.slug;
      b.dataset.zName = o.name;
      b.textContent = 'Mitglieder und Einladungen: ' + o.name;
      admin.appendChild(b);
    }
  }
  const li = (text, btn) => {
    const el = document.createElement('li');
    const t = document.createElement('span');
    t.textContent = text;
    el.appendChild(t);
    if (btn) { const b = document.createElement('button'); b.type = 'button'; b.className = 'text-button'; Object.assign(b.dataset, btn.data); b.textContent = btn.label; el.append(' ', b); }
    return el;
  };
  async function showTeam(slug, name) {
    teamSlug = slug || teamSlug;
    if (name) $('#zTeamTitle').textContent = 'Mitglieder · ' + name;
    const t = await call(`orgs/${teamSlug}/mitglieder`);
    const sub = t.subscription;
    $('#zTeamPlan').textContent = sub.managed ? sub.notice : `${sub.plan_label}: ${sub.notice} Mitglieder ${sub.members}${sub.members_limit ? ' von ' + sub.members_limit : ''}.`;
    const list = $('#zTeamList');
    list.textContent = '';
    for (const m of t.members) list.appendChild(li(`${m.display_name || m.username} (${m.username}) · ${m.role}${m.active ? '' : ' · gesperrt'}`, {label: 'Entfernen', data: {zRemove: m.username}}));
    const inv = $('#zTeamInvites');
    inv.textContent = '';
    for (const i of t.invitations) inv.appendChild(li(`${i.email} · ${i.role} · bis ${i.expires_at.slice(0, 10)}`, {label: 'Zurückziehen', data: {zRevoke: String(i.id)}}));
    if (!t.invitations.length) inv.appendChild(li('Keine.'));
    show('#zTeam');
  }
  async function showInvite(token) {
    const i = await call('einladung', {token});
    $('#zInviteInfo').textContent = `Einladung zu „${i.organization}“ als ${i.role} (für ${i.email}).` + (i.logged_in ? ` Angemeldet als ${i.username}.` : '');
    $('#zInviteAccept').classList.toggle('hidden', !i.logged_in);
    $('#zInviteNew').classList.toggle('hidden', i.logged_in || i.has_account);
    if (!i.logged_in && i.has_account) { msg('Für diese Adresse gibt es schon ein Konto: bitte anmelden, die Einladung wird danach angezeigt.'); show('#zLogin'); return; }
    show('#zInvite');
  }
  async function refresh() {
    const s = await call('status');
    if (store.get() && (s.logged_in || !s.stage)) {
      try { return await showInvite(store.get()); } catch (err) { store.set(''); msg(err.message); }
    }
    if (s.logged_in) return showOrgs(s);
    $('#zRegisterHint').classList.toggle('hidden', !s.registration_open);
    if (s.stage === 'zweitfaktor') return show('#zCode');
    if (s.stage === 'einrichtung') return showSetup(true);
    show('#zLogin');
  }
  // dev68: Nach der Anmeldung ohne zweiten Faktor wird er empfohlen (nicht verpflichtend). „Später“ geht weiter wie bisher.
  let suggestNext = null;
  function afterLogin(r) {
    if (r.stage === 'voll' && r.suggest_2fa) {
      suggestNext = r.entered ? () => { location.href = '/'; } : () => refresh();
      show('#zSuggest');
      $('#zSuggestYes').focus();
      return null;
    }
    if (r.entered) { location.href = '/'; return null; }
    if (r.stage === 'zweitfaktor') { show('#zCode'); $('#zCode').code.focus(); return null; }
    if (r.stage === 'einrichtung') { showSetup(true); return null; }
    return refresh();
  }
  $('#zLogin').addEventListener('submit', async e => {
    e.preventDefault();
    msg('');
    const f = e.target;
    try {
      const r = await call('login', {username: f.username.value, password: f.password.value});
      f.password.value = '';
      await afterLogin(r);
    } catch (err) { msg(err.message); }
  });
  $('#zCode').addEventListener('submit', async e => {
    e.preventDefault();
    msg('');
    const f = e.target;
    try {
      const r = await call('code', {code: f.code.value.trim()});
      f.code.value = '';
      await afterLogin(r);
    } catch (err) {
      f.code.value = '';
      msg(err.message);
      if (/abgelaufen|neu anmelden/i.test(err.message)) show('#zLogin');
    }
  });
  document.querySelector('[data-z-restart]').addEventListener('click', async () => {
    try { await call('logout', {}); } catch (err) { /* schon abgemeldet */ }
    msg('');
    show('#zLogin');
  });
  $('#zSetupStart').addEventListener('submit', async e => {
    e.preventDefault();
    msg('');
    const f = e.target;
    try {
      const r = await call('2fa/start', {password: f.password.value});
      f.password.value = '';
      $('#zSecret').textContent = r.secret;
      $('#zUri').textContent = r.uri;
      f.classList.add('hidden');
      $('#zSetupConfirm').classList.remove('hidden');
      $('#zSetupConfirm').code.focus();
    } catch (err) { msg(err.message); }
  });
  $('#zSetupConfirm').addEventListener('submit', async e => {
    e.preventDefault();
    msg('');
    const f = e.target;
    try {
      const r = await call('2fa/confirm', {code: f.code.value.trim()});
      f.reset();
      f.classList.add('hidden');
      $('#zSecret').textContent = '';
      $('#zUri').textContent = '';
      const list = $('#zCodeList');
      list.textContent = '';
      for (const c of r.recovery_codes) { const li = document.createElement('li'); li.textContent = c; list.appendChild(li); }
      $('#zCodes').classList.remove('hidden');
    } catch (err) { msg(err.message); }
  });
  $('#zCodesDone').addEventListener('click', async () => {
    $('#zCodeList').textContent = '';
    msg('');
    await refresh();
  });
  $('#zMfaOn').addEventListener('click', () => { msg(''); showSetup(false); });
  // Nach der Einrichtung enden die ohne zweiten Faktor geöffneten Sitzungen; „Gespeichert – weiter“ zeigt die Organisationen.
  $('#zSuggestYes').addEventListener('click', () => { msg(''); suggestNext = null; showSetup(false); });
  $('#zSuggestLater').addEventListener('click', async () => {
    msg('');
    const next = suggestNext || (() => refresh());
    suggestNext = null;
    try { await next(); } catch (err) { msg(err.message); }
  });
  $('#zMfaOff').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    try {
      await call('2fa/off', {password: f.password.value, code: f.code.value.trim()});
      f.reset();
      await refresh();
      msg('Zwei-Faktor-Anmeldung abgeschaltet.');
    } catch (err) { msg(err.message); }
  });
  $('#zOrgList').addEventListener('click', async e => {
    const b = e.target.closest('[data-z-org]');
    if (!b) return;
    try { await call('enter', {slug: b.dataset.zOrg}); location.href = '/'; } catch (err) { msg(err.message); }
  });
  $('#zPw').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    try {
      const r = await call('password', {old: f.old.value, new: f.new.value});
      f.reset();
      await refresh();
      msg(r.notice);
    } catch (err) { msg(err.message); }
  });
  $('#zLogout').addEventListener('click', async () => {
    try { await call('logout', {}); } catch (err) { /* schon abgemeldet */ }
    location.reload();
  });
  $('#zToRegister').addEventListener('click', () => { msg(''); show('#zRegister'); });
  document.querySelectorAll('[data-z-back]').forEach(b => b.addEventListener('click', () => { msg(''); show('#zLogin'); }));
  $('#zRegister').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    try {
      const r = await call('registrieren', {email: f.email.value.trim(), org_name: f.org_name.value.trim(), username: f.username.value.trim(),
        display_name: f.display_name.value.trim(), password: f.password.value});
      f.reset();
      show('#zLogin');
      msg(r.notice);
    } catch (err) { msg(err.message); }
  });
  $('#zInviteAccept').addEventListener('click', async () => {
    try { const r = await call('einladung/annehmen', {token: store.get()}); store.set(''); await refresh(); msg(`Beigetreten: ${r.organization.name}.`); } catch (err) { msg(err.message); }
  });
  $('#zInviteNew').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    try {
      const r = await call('einladung/annehmen', {token: store.get(), username: f.username.value.trim(), display_name: f.display_name.value.trim(), password: f.password.value});
      f.reset();
      store.set('');
      show('#zLogin');
      msg(`Konto angelegt und „${r.organization.name}“ beigetreten. Bitte jetzt anmelden.`);
    } catch (err) { msg(err.message); }
  });
  $('#zAdminOrgs').addEventListener('click', e => {
    const b = e.target.closest('[data-z-team]');
    if (b) { msg(''); showTeam(b.dataset.zTeam, b.dataset.zName).catch(err => msg(err.message)); }
  });
  document.querySelector('[data-z-orgs]').addEventListener('click', () => { msg(''); refresh().catch(err => msg(err.message)); });
  $('#zTeamInvite').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target;
    try { const r = await call(`orgs/${teamSlug}/einladungen`, {email: f.email.value.trim(), role: f.role.value}); f.reset(); await showTeam(); msg(`Einladung an ${r.email} liegt im Postausgang (${r.outbox}).`); } catch (err) { msg(err.message); }
  });
  $('#zTeam').addEventListener('click', async e => {
    const rv = e.target.closest('[data-z-revoke]'), rm = e.target.closest('[data-z-remove]');
    try {
      if (rv) { await call(`orgs/${teamSlug}/einladungen/${rv.dataset.zRevoke}`, null); await showTeam(); msg('Einladung zurückgezogen.'); }
      if (rm) { await call(`orgs/${teamSlug}/mitglieder/${encodeURIComponent(rm.dataset.zRemove)}`, null); await showTeam(); msg(`${rm.dataset.zRemove} entfernt – der Zugang endet sofort.`); }
    } catch (err) { msg(err.message); }
  });
  // Links aus dem Postausgang: #bestaetigen=… (Registrierung) und #einladung=… (Einladung). Danach aus der Adresszeile entfernen.
  async function fromHash() {
    const hash = new URLSearchParams(location.hash.slice(1));
    if (hash.has('bestaetigen') || hash.has('einladung')) history.replaceState(null, '', location.pathname);
    if (hash.get('bestaetigen')) {
      try { const r = await call('registrieren/bestaetigen', {token: hash.get('bestaetigen')}); show('#zLogin'); msg(`${r.notice} Organisation: ${r.organization.name}.`); $('#zLogin').username.value = r.username; return; }
      catch (err) { msg(err.message); }
    }
    if (hash.get('einladung')) store.set(hash.get('einladung'));
    await refresh();
  }
  window.addEventListener('hashchange', () => fromHash().catch(err => msg(err.message)));  // Link in schon offener Seite
  fromHash().catch(err => msg(err.message));
})();
