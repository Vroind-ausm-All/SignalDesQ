// SDQ-014/021: zentrale Anmeldung einer Mehrmandanten-Installation – Konto anmelden (Passwort, ggf. Code aus der App),
// zweiten Faktor einrichten, Organisation wählen oder wechseln.
(function () {
  const $ = s => document.querySelector(s);
  const msg = t => { $('#zMsg').textContent = t || ''; };
  const views = ['#zLogin', '#zCode', '#zSetup', '#zOrgs'];
  const show = id => views.forEach(v => $(v).classList.toggle('hidden', v !== id));
  async function call(path, body) {
    const opts = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
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
    $('#zMfaState').textContent = s.two_factor ? 'an' : 'aus';
    $('#zMfaInfo').textContent = s.two_factor
      ? 'Noch ' + s.recovery_codes_left + ' Wiederherstellungscodes übrig.' + (s.require_2fa ? ' In dieser Installation Pflicht.' : '')
      : 'Schützt das Konto, wenn das Passwort bekannt wird.';
    $('#zMfaOn').classList.toggle('hidden', !!s.two_factor);
    $('#zMfaOff').classList.toggle('hidden', !s.two_factor || !!s.require_2fa);
  }
  async function refresh() {
    const s = await call('status');
    if (s.logged_in) return showOrgs(s);
    if (s.stage === 'zweitfaktor') return show('#zCode');
    if (s.stage === 'einrichtung') return showSetup(true);
    show('#zLogin');
  }
  function afterLogin(r) {
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
  refresh().catch(err => msg(err.message));
})();
