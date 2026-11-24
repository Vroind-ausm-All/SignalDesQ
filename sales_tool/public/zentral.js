// SDQ-014: zentrale Anmeldung einer Mehrmandanten-Installation – Konto anmelden, Organisation wählen oder wechseln.
(function () {
  const $ = s => document.querySelector(s);
  const msg = t => { $('#zMsg').textContent = t || ''; };
  async function call(path, body) {
    const opts = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
    const r = await fetch('/api/zentral/' + path, opts);
    const data = await r.json();
    if (!r.ok) throw Error(data.error || 'Anfrage fehlgeschlagen');
    return data;
  }
  function showOrgs(s) {
    $('#zLogin').classList.add('hidden');
    $('#zOrgs').classList.remove('hidden');
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
  }
  async function refresh() {
    const s = await call('status');
    if (!s.logged_in) { $('#zLogin').classList.remove('hidden'); $('#zOrgs').classList.add('hidden'); return; }
    showOrgs(s);
  }
  $('#zLogin').addEventListener('submit', async e => {
    e.preventDefault();
    msg('');
    const f = e.target;
    try {
      const r = await call('login', {username: f.username.value, password: f.password.value});
      f.password.value = '';
      if (r.entered) { location.href = '/'; return; }
      await refresh();
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
