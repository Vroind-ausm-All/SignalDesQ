'use strict';
// 2.0.0-dev53 (UX Schritt 5): Einstellungen als Abschnittsliste mit Kurzstand statt einer langen Seite.
// - Neun Abschnitte; sieben stehen in #viewSettings, „KI-Werkzeuge“ (KI-Studio) und „Hilfe & Playbook“ sind eigene Ansichten. Seitenkopf,
//   Suche (#esTop) und Abschnittsliste (#esNav) wandern in die jeweils sichtbare der drei Ansichten – es gibt sie nur einmal.
// - Adresse #/einstellungen?abschnitt=<name>. Bisherige Sprungziele sind Element-IDs (kalender, targetProfile, ownTimes, zugang …):
//   geöffnet wird der Abschnitt, der das Element enthält, und dorthin gescrollt. #/einstellungen öffnet den zuletzt benutzten Abschnitt
//   (sonst „Meine Firma“); schmal (bis 1000 px) zeigt es die Abschnittsliste als eigene Ansicht, ein Abschnitt hat dann „← Einstellungen“.
// - Kurzstand je Abschnitt nur aus vorhandenen Daten; Warnungen gelb (Pflichtangaben für Rechnungen fehlen, keine oder alte Sicherung,
//   Kalenderabgleich veraltet, Zielkundenprofil ohne Standort oder Branchen).
// - Eingabeschutz beim Abschnittswechsel: ungespeicherte Formulare fragen über formguard.js (Speichern · Weiter bearbeiten · Verwerfen).
//   Laden die Module ihre Formulare neu (z. B. nach einer Sofort-Speicherung), bleiben ungespeicherte Eingaben stehen.
(function () {
  const SECTIONS = [
    {key: 'firma', label: 'Meine Firma'}, {key: 'preise', label: 'Leistungen & Preise'}, {key: 'zielkunden', label: 'Zielkunden'},
    {key: 'darstellung', label: 'Darstellung'}, {key: 'kalender', label: 'Kalender & Postfach'}, {key: 'datenquellen', label: 'Datenquellen'},
    {key: 'sicherung', label: 'Sicherung & Zugang'}, {key: 'ki-werkzeuge', label: 'KI-Werkzeuge', view: 'studio'},
    {key: 'hilfe', label: 'Hilfe & Playbook', view: 'playbook'}];
  // Namen, die kein Element sind: frühere Ansichten und naheliegende Schreibweisen
  const ALIAS = {studio: 'ki-werkzeuge', 'ki-studio': 'ki-werkzeuge', ki: 'ki-werkzeuge', playbook: 'hilfe', leitfaden: 'hilfe',
    'meine-firma': 'firma', stammdaten: 'firma', 'leistungen-preise': 'preise', 'sicherung-zugang': 'sicherung'};
  const VIEWS = {settings: 'viewSettings', studio: 'viewStudio', playbook: 'viewPlaybook'};
  // Formulare, die erst mit „Speichern“ gelten (Eingabeschutz); Sofort-Formulare (Darstellung, Offline, Kalender-Abo) brauchen ihn nicht
  const FORMS = {accSettingsForm: 'Stammdaten für Rechnungen', qbSettings: 'Kalkulationsgrundlagen', serviceProfileForm: 'Leistungsprofil',
    targetProfileForm: 'Zielkundenprofil', qSettingsForm: 'Gewichte & Fristen', availabilityForm: 'Deine Zeiten', cdForm: 'Kalender-Abgleich (CalDAV)',
    imForm: 'Postfach (IMAP)', rtForm: 'Website-Abruf & Auswertung'};
  const KEY = 'signaldesk.einstellungen.abschnitt';
  const narrow = window.matchMedia('(max-width: 1000px)');
  const byId = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const info = key => SECTIONS.find(s => s.key === key);
  const box = key => document.querySelector(`#viewSettings .es-sec[data-es="${key}"]`);
  const item = key => document.querySelector(`#esNav [data-es-key="${key}"]`);
  const view = () => (typeof currentView !== 'undefined' ? currentView : '');
  let current = null, list = false;

  function recall() { try { const k = localStorage.getItem(KEY); return info(k) && !info(k).view ? k : null; } catch { return null; } }
  function remember(k) { try { localStorage.setItem(KEY, k); } catch { /* privates Fenster: dann eben ohne */ } }

  // Ziel (Abschnittsname, Element-ID oder frühere Ansicht) → {key, anchor}
  function resolve(target) {
    const t = String(target || '').trim();
    if (!t) return null;
    const k = ALIAS[t] || t;
    if (info(k)) return {key: k, anchor: null};
    const el = byId(t);
    const sec = el && el.closest('#viewSettings .es-sec');
    if (sec) return {key: sec.dataset.es, anchor: el === sec ? null : el};
    const v = el && el.closest('#viewStudio, #viewPlaybook');
    if (v) return {key: v.id === 'viewStudio' ? 'ki-werkzeuge' : 'hilfe', anchor: el};
    return null;
  }

  // ------------------------------------------------------------ Eingabeschutz
  const state = new Map();  // Formular-ID → {base, touched}
  let pending = null;
  const fields = f => [...f.querySelectorAll('input, select, textarea')].filter(el => !['submit', 'button', 'reset', 'file', 'hidden'].includes(el.type));
  const values = f => fields(f).map(el => (el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value));
  const snap = f => JSON.stringify(values(f));
  function setValues(f, vals) {
    const els = fields(f);
    if (els.length !== vals.length) return false;
    els.forEach((el, i) => { if (el.type === 'checkbox' || el.type === 'radio') el.checked = vals[i]; else el.value = vals[i]; });
    return true;
  }
  const formOf = el => { const f = el && el.closest && el.closest('form'); return f && FORMS[f.id] ? f : null; };
  function isDirty(f) { const s = f && state.get(f.id); return !!(s && s.touched && snap(f) !== s.base); }
  function dirtyIn(root) { return root ? [...root.querySelectorAll('form')].filter(f => FORMS[f.id] && isDirty(f)) : []; }
  const allDirty = () => dirtyIn(byId('viewSettings'));

  document.addEventListener('focusin', e => {
    const f = formOf(e.target);
    if (!f) return;
    const s = state.get(f.id);
    if (!s || !s.touched) state.set(f.id, {base: snap(f), touched: false});
  }, true);
  const touch = e => {
    const f = e.isTrusted ? formOf(e.target) : null;
    if (!f) return;
    const s = state.get(f.id) || {base: null, touched: false};
    if (s.base === null) s.base = snap(f);
    s.touched = true;
    state.set(f.id, s);
  };
  document.addEventListener('input', touch, true);
  document.addEventListener('change', touch, true);
  document.addEventListener('submit', e => { if (FORMS[e.target.id]) pending = e.target.id; }, true);
  // Erfolgreich gespeichert = die nächste schreibende Anfrage nach dem Absenden gelingt (wie formguard.js für die Akte)
  const plainApi = window.api;
  if (typeof plainApi === 'function') {
    window.api = async function (path, method = 'GET', body) {
      const form = method !== 'GET' ? pending : null;
      if (form) pending = null;
      const result = await plainApi(path, method, body);
      if (form) state.delete(form);
      if (method !== 'GET' && ['settings', 'studio', 'playbook'].includes(view())) later();
      return result;
    };
  }
  window.addEventListener('beforeunload', e => { if (allDirty().length) { e.preventDefault(); e.returnValue = ''; } });

  // Module laden ihre Formulare neu (nach Sofort-Speichern, beim Öffnen): ungespeicherte Eingaben danach zurückschreiben
  async function keep(fn, args) {
    const saved = allDirty().map(f => [f.id, values(f)]);
    const r = await fn.apply(this, args);
    for (const [id, vals] of saved) { const f = byId(id); if (f && setValues(f, vals)) { const s = state.get(id); if (s) s.touched = true; } }
    return r;
  }
  function wrapKeep(name) {
    const fn = window[name];
    if (typeof fn !== 'function' || fn.__keep) return;
    const w = function (...args) { return keep.call(this, fn, args); };
    w.__keep = true;
    window[name] = w;
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function saveAll(forms) {
    for (const f of forms) {
      if (!f.reportValidity()) return false;
      f.requestSubmit();
      for (let t = 0; t < 300 && f.isConnected && isDirty(f) && state.get(f.id)?.touched; t++) await sleep(100);
      const now = byId(f.id);
      if (now && isDirty(now)) return false;  // Fehler: Meldung kam vom Formular, Eingaben bleiben
    }
    return true;
  }
  // true = wechseln, false = bleiben
  async function guard(forms) {
    if (!forms.length) return true;
    if (!window.formGuard) return true;
    const choice = await window.formGuard.ask(forms.map(f => FORMS[f.id]));
    if (choice === 'discard') {
      forms.forEach(f => { const s = state.get(f.id); if (s && s.base) setValues(f, JSON.parse(s.base)); state.delete(f.id); });
      return true;
    }
    if (choice === 'save' && await saveAll(forms)) return true;
    const f = forms.find(x => x.isConnected && isDirty(x)) || forms[0];
    const el = f && fields(f).find(x => !x.disabled);
    if (el) el.focus();
    return false;
  }

  // ------------------------------------------------------------ Seitenkopf, Liste, Abschnitt
  function place(v) {
    const page = byId(VIEWS[v]);
    if (!page) return;
    const top = page.querySelector('[data-es-slot="top"]'), nav = page.querySelector('[data-es-slot="nav"]');
    if (top && byId('esTop').parentNode !== top) top.appendChild(byId('esTop'));
    if (nav && byId('esNav').parentNode !== nav) nav.appendChild(byId('esNav'));
  }
  function mark(key) {
    document.querySelectorAll('#esNav .es-item').forEach(b => {
      const on = b.dataset.esKey === key;
      b.classList.toggle('is-active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    byId('esMeta').textContent = key ? info(key).label : `${SECTIONS.length} Abschnitte`;
  }
  function mode(v, asList) {
    const page = byId(VIEWS[v]);
    if (page) page.dataset.esMode = asList ? 'list' : 'section';
  }
  function paint(key) {
    current = key;
    list = false;
    remember(key);
    document.querySelectorAll('#viewSettings .es-sec').forEach(s => s.classList.toggle('hidden', s.dataset.es !== key));
    mode('settings', false);
    mark(key);
    if (key === 'datenquellen') window.refreshOsmLocal?.();
    if (key === 'firma') window.accLoadSettings?.();
  }
  function showList() {
    list = true;
    mode('settings', true);
    mark(null);
  }
  // Sprungziel im Abschnitt: Klappzeilen darüber öffnen; liegt es nicht im oberen Teil des Fensters, dorthin scrollen und kurz markieren
  function flash(el, always) {
    if (!el) return;
    for (let d = el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
    setTimeout(() => {
      if (!always && el.getBoundingClientRect().top < window.innerHeight * 0.6) return;
      el.classList.add('es-flash');
      setTimeout(() => el.classList.remove('es-flash'), 1600);
      el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, 60);
  }
  const address = key => { const p = new URLSearchParams(); if (key) p.set('abschnitt', key); return window.signalNav ? window.signalNav.build('settings', p) : '#/einstellungen' + (key ? '?abschnitt=' + key : ''); };

  // Ein Ziel öffnen (Liste, Verweis aus einer anderen Seite, Adresse). opts.history: aus Zurück/Vor oder Neuladen (keine neue Adresse)
  async function open(target, opts = {}) {
    const r = resolve(target) || {key: current || recall() || 'firma', anchor: null};
    const s = info(r.key);
    const here = view();
    // Abschnittswechsel innerhalb der Einstellungen: erst fragen, wenn etwas ungespeichert ist
    if (here === 'settings' && !list && current && current !== r.key) {
      if (!await guard(dirtyIn(box(current)))) {
        if (opts.history) history.pushState(null, '', address(current));
        return false;
      }
    }
    if (s.view) {
      if (here !== s.view) window.switchView(s.view);
      if (r.anchor) flash(r.anchor);
      return true;
    }
    paint(r.key);
    if (here !== 'settings') window.switchView('settings');  // schreibt die Adresse mit dem neuen Abschnitt (params)
    else if (!opts.history) {
      const target2 = address(r.key);
      if (location.hash !== target2) history.pushState(null, '', target2);
    }
    if (r.anchor) flash(r.anchor);
    else if (here === 'settings' && !opts.history) window.scrollTo({top: 0, behavior: 'instant'});
    return true;
  }

  // Adresse anwenden (nav.js apply): #/einstellungen ohne Abschnitt → zuletzt benutzter oder Liste (schmal)
  function route(params) {
    const a = params && params.get('abschnitt');
    if (a) return open(a, {history: true});
    if (narrow.matches) { showList(); return true; }
    paint(current || recall() || 'firma');
    history.replaceState(null, '', address(current));
    return true;
  }
  // Welche Ansicht gehört zu ?abschnitt=… (KI-Werkzeuge und Hilfe sind eigene Ansichten)
  function viewFor(params) {
    const r = resolve(params && params.get('abschnitt'));
    return r && info(r.key).view ? info(r.key).view : 'settings';
  }

  // ------------------------------------------------------------ Suche über die Einstellungen
  const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  function textOf(key) {
    const s = info(key);
    const el = s.view ? byId(VIEWS[s.view])?.querySelector('.es-body') : box(key);
    if (!el) return s.label;
    const extra = [...el.querySelectorAll('input[placeholder], textarea[placeholder]')].map(x => x.placeholder).join(' ');
    return `${s.label} ${el.dataset.esWords || ''} ${el.textContent} ${extra}`;
  }
  function search() {
    const term = norm(byId('esQ').value.trim());
    const hits = [];
    SECTIONS.forEach(s => {
      const ok = !term || norm(textOf(s.key)).includes(term);
      item(s.key)?.classList.toggle('hidden', !ok);
      if (ok && term) hits.push(s.key);
    });
    byId('esHits').textContent = term ? (hits.length ? `${hits.length} von ${SECTIONS.length} Abschnitten – Enter öffnet „${info(hits[0]).label}“` : 'Keine Einstellung gefunden') : '';
    if (term && narrow.matches && view() === 'settings') showList();
    return hits;
  }
  // Erste Stelle im Abschnitt, die den Begriff enthält (Beschriftung, Überschrift, Klappzeile)
  function firstMatch(key, term) {
    const s = info(key);
    const root = s.view ? byId(VIEWS[s.view])?.querySelector('.es-body') : box(key);
    if (!root || !term) return null;
    const cands = root.querySelectorAll('h2, h3, summary, label, .sales-subhead, b, p, button');
    return [...cands].find(el => norm(el.textContent).includes(term) && !el.closest('.hidden')) || null;
  }
  async function searchGo() {
    const hits = search();
    if (!hits.length) return;
    const term = norm(byId('esQ').value.trim());
    if (await open(hits[0])) {
      const el = firstMatch(hits[0], term);
      if (el) setTimeout(() => flash(el, true), 80);
    }
  }

  // ------------------------------------------------------------ Kurzstand je Abschnitt (nur vorhandene Daten)
  const fmtDay = iso => new Date(iso).toLocaleDateString('de-DE', {day: 'numeric', month: 'short'});
  function setState(key, text, warn) {
    const el = document.querySelector(`[data-es-state="${key}"]`);
    if (!el) return;
    el.innerHTML = warn ? `<span class="ui-pill is-attention">${esc(text)}</span>` : esc(text);
    el.title = text;
    item(key)?.classList.toggle('is-warn', !!warn);
  }
  let busy = false, timer = null;
  function later() { clearTimeout(timer); timer = setTimeout(states, 400); }
  async function states() {
    if (busy || typeof window.api !== 'function') return;
    busy = true;
    const get = p => plainApi(p).catch(() => null);
    try {
      const [acc, price, target, cal, cd, im, osm, cat, bk, off, auth] = await Promise.all([get('/accounting/settings'), get('/pricing/catalog'),
        get('/profile/target'), get('/kalender'), get('/caldav'), get('/imap'), get('/osm?place=&radius=0'), get('/catalog'), get('/backups/all'),
        get('/system/offline'), get('/auth/status')]);
      if (acc) {
        const miss = acc.missing || [];
        const shortName = m => m.replace('Steuernummer oder USt-IdNr.', 'Steuernr./USt-IdNr.').replace(' (für E-Rechnung)', '');  // passt in 240 px
        setState('firma', miss.length ? `${miss.length === 1 ? shortName(miss[0]) : miss.length + ' Pflichtangaben'} fehlt${miss.length === 1 ? '' : 'en'}` : acc.company_name, miss.length > 0);
        if (miss.length) document.querySelector('[data-es-state="firma"]').title = `Fehlt: ${miss.join(', ')}`;
        const m = byId('esFirmaMissing');
        if (m) { m.classList.toggle('hidden', !miss.length); m.textContent = miss.length ? `Für Rechnungen fehlt noch: ${miss.join(', ').replace(/\.$/, '')}. Ohne diese Angaben lässt sich keine Rechnung festschreiben.` : ''; }
      }
      if (price) {
        const services = (price.groups || []).reduce((n, g) => n + (g.services || []).length, 0);
        setState('preise', `${price.settings.hourly_rate} €/h · ${(price.vorlagen || []).length} Vorlagen`);
        if (byId('qbVorlagenState')) byId('qbVorlagenState').textContent = `${(price.vorlagen || []).length} Vorlagen mit Preis und Zeitraum`;
        if (byId('qbCatalogState') && services) byId('qbCatalogState').textContent = `${services} Leistungen in ${(price.groups || []).length} Gruppen – Aufwand, Fremdkosten, feste Preise, Korrekturschleifen`;
      }
      if (target) {
        const p = target.profile || {}, inds = p.industries && Object.keys(p.industries).length;
        const gaps = [!p.home && 'Standort', !inds && 'Branchen'].filter(Boolean);
        setState('zielkunden', gaps.length ? `${gaps.join(' und ')} fehlen` : `${p.name || 'Profil'} · ${p.home} · ${p.radius_km} km`, gaps.length > 0);
      }
      const ap = window.SignalAppearance && window.SignalAppearance.get();
      if (ap) {
        const t = byId('apPanel')?.querySelector(`[data-ap-theme="${ap.theme}"] b`)?.textContent || ap.theme[0].toUpperCase() + ap.theme.slice(1);
        setState('darstellung', `${t} · ${{system: 'wie System', hell: 'hell', dunkel: 'dunkel'}[ap.mode] || ap.mode}${ap.density === 'kompakt' ? ' · kompakt' : ''}`);
      }
      if (cd || cal || im) {
        const parts = [cd && cd.configured ? `CalDAV ${cd.last_sync ? 'abgeglichen ' + fmtDay(cd.last_sync) : 'eingerichtet'}` : '', cal && cal.enabled ? 'Abo an' : '', im && im.configured ? 'IMAP' : ''].filter(Boolean);
        if (cd && cd.stale) setState('kalender', 'Abgleich älter als 24 h', true);
        else setState('kalender', parts.length ? parts.join(' · ') : 'nicht verbunden');
      }
      if (osm || cat) {
        const n = (osm && osm.places ? 1 : 0) + (cat && cat.entities ? 1 : 0);
        setState('datenquellen', n ? `${n} von 2 eingerichtet${osm && osm.places ? ' · ' + Number(osm.places).toLocaleString('de-DE') + ' Betriebe' : ''}` : 'OSM und GLEIF noch nicht eingelesen');
      }
      if (bk) {
        const last = (bk.backups || [])[0];
        const days = last ? Math.floor((Date.now() - new Date(last.modified).getTime()) / 864e5) : null;
        const extra = [off && off.offline ? 'offline' : '', auth && auth.auth_required ? 'Login an' : ''].filter(Boolean).join(' · ');
        if (!last) setState('sicherung', 'noch keine Sicherung', true);
        else if (days > 7) setState('sicherung', `letzte Sicherung vor ${days} Tagen`, true);
        else setState('sicherung', `gesichert ${days === 0 ? 'heute' : days === 1 ? 'gestern' : 'vor ' + days + ' Tagen'}${extra ? ' · ' + extra : ''}`);
      }
      setState('ki-werkzeuge', 'lokal, nur auf Klick');
      setState('hilfe', 'Gesprächsleitfaden');
    } finally { busy = false; }
  }

  // ------------------------------------------------------------ Ereignisse
  function init() {
    if (!byId('viewSettings') || !byId('esNav')) return;
    byId('esQ').addEventListener('input', search);
    byId('esQ').addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); searchGo(); }
      if (e.key === 'Escape' && byId('esQ').value) { e.preventDefault(); e.stopPropagation(); byId('esQ').value = ''; search(); }
    });
    byId('esBack').addEventListener('click', async () => {
      if (view() === 'settings' && current && !await guard(dirtyIn(box(current)))) return;
      if (view() !== 'settings') window.switchView('settings');
      showList();
      const a = address(null);
      if (location.hash !== a) history.pushState(null, '', a);
    });
    document.addEventListener('signaldesk:view', e => {
      const v = e.detail.view;
      if (!VIEWS[v]) return;
      place(v);
      if (v === 'settings') {
        if (!current && !list) { if (narrow.matches) showList(); else paint(recall() || 'firma'); }
        else mark(list ? null : current);
      } else {
        mark(v === 'studio' ? 'ki-werkzeuge' : 'hilfe');
        mode(v, false);
      }
      states();
    });
    // Breit → schmal: im Listenzustand bleibt die Liste; schmal → breit: Liste nur noch als Spalte, Abschnitt daneben
    const onChange = () => { if (!narrow.matches && list) paint(current || recall() || 'firma'); };
    if (narrow.addEventListener) narrow.addEventListener('change', onChange); else narrow.addListener(onChange);
    ['refreshQuality', 'loadPricingSettings', 'refreshCalendarSettings', 'accLoadSettings'].forEach(wrapKeep);
    document.addEventListener('click', e => { if (e.target.closest('[data-ap-theme], [data-ap-mode], [data-ap-density]')) later(); });
  }

  window.einstellungen = {
    open, route, viewFor, states, resolve,
    params: () => { const p = new URLSearchParams(); if (!list && current) p.set('abschnitt', current); return p; },
    pick: key => open(key),
    current: () => current, dirty: () => allDirty().map(f => f.id), keep: fn => keep(fn, []),
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
