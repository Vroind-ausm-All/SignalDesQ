'use strict';
// 2.0.0-dev14 (Produktreview M07/U01/U03): sechs Bereiche mit Reitern und direkten Adressen.
// - Seitenleiste: Heute · Finden · Firmen · Angebote · Abrechnen · Einstellungen; die Ansichten eines Bereichs stehen oben als Reiter.
// - Jede Ansicht hat eine Adresse (#/firmen/pipeline), eine Firma zusätzlich ?firma=ID, ein Einstellungsabschnitt ?abschnitt=…,
//   die Firmenliste ihre Filter (?suche=…&phase=…). Zurück/Vor und Neuladen führen an dieselbe Stelle.
// Keine Datenmigration: es ändern sich nur Anordnung und Adressen; alle bisherigen Ansichten bleiben erreichbar.
(function () {
  const AREAS = [
    {key: 'heute', label: 'Heute', views: ['dashboard', 'tasks', 'workspace']},
    {key: 'finden', label: 'Finden', views: ['finder', 'datacheck', 'center', 'research', 'scoring', 'signals', 'report']},
    {key: 'firmen', label: 'Firmen', views: ['leads', 'pipeline', 'quality']},
    {key: 'angebote', label: 'Angebote', views: ['quotes']},
    {key: 'abrechnen', label: 'Abrechnen', views: ['accounting']},
    {key: 'einstellungen', label: 'Einstellungen', views: ['settings', 'studio', 'playbook']},
  ];
  const SLUG = {dashboard: 'heute', tasks: 'heute/aufgaben', workspace: 'heute/kontakt-termine',
    finder: 'finden', datacheck: 'finden/import', center: 'finden/recherche', research: 'finden/url-recherche',
    scoring: 'finden/website-scoring', signals: 'finden/kaufsignale', report: 'finden/bericht',
    leads: 'firmen', pipeline: 'firmen/pipeline', quality: 'firmen/datenpflege',
    quotes: 'angebote', accounting: 'abrechnen',
    settings: 'einstellungen', studio: 'einstellungen/ki-studio', playbook: 'einstellungen/hilfe'};
  const BY_SLUG = Object.fromEntries(Object.entries(SLUG).map(([v, s]) => [s, v]));
  const AREA_OF = Object.fromEntries(AREAS.flatMap(a => a.views.map(v => [v, a.key])));
  const scrollOf = {};
  let fromHistory = false, pushedLead = false, ignorePop = 0;

  const areaOf = view => AREA_OF[view] || 'heute';
  const modalOpen = () => !!document.getElementById('modal') && !document.getElementById('modal').classList.contains('hidden');

  function parse(hash) {
    const h = String(hash || '').replace(/^#\/?/, '');
    const [path, query = ''] = h.split('?');
    return {view: BY_SLUG[path.replace(/\/+$/, '')] || null, params: new URLSearchParams(query)};
  }
  function build(view, params) {
    const q = params ? params.toString() : '';
    return '#/' + (SLUG[view] || 'heute') + (q ? '?' + q : '');
  }
  function listParams() {
    const p = new URLSearchParams();
    const q = document.getElementById('leadSearch')?.value.trim(), st = document.getElementById('stageFilter')?.value;
    if (q) p.set('suche', q);
    if (st) p.set('phase', st);
    return p;
  }
  const viewParams = view => (view === 'leads' ? listParams() : new URLSearchParams());

  // ---- Darstellung des aktiven Bereichs
  function markArea(view) {
    const area = areaOf(view);
    document.querySelectorAll('.sidebar .nav[data-area]').forEach(b => {
      const on = b.dataset.area === area;
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    document.querySelectorAll('#areaBar .area-tabs').forEach(n => n.classList.toggle('hidden', n.dataset.area !== area));
    document.querySelectorAll('#areaBar [data-area-view]').forEach(b => {
      const on = b.dataset.areaView === view || (view === 'report' && b.dataset.areaView === 'center');
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    const crumb = document.getElementById('areaCrumb');
    if (crumb) crumb.textContent = AREAS.find(a => a.key === area).label;
  }

  // ---- switchView erweitern: Bereich markieren, Adresse schreiben, Scrollstand merken
  const plainSwitch = window.switchView;
  window.switchView = function (view) {
    if (typeof currentView !== 'undefined' && currentView) scrollOf[currentView] = window.scrollY;
    plainSwitch(view);
    markArea(view);
    document.dispatchEvent(new CustomEvent('signaldesk:view', {detail: {view}}));
    if (fromHistory) {
      const y = scrollOf[view] || 0;
      setTimeout(() => window.scrollTo({top: y, behavior: 'instant'}), 0);
      return;
    }
    const target = build(view, viewParams(view));
    if (location.hash !== target) history.pushState(null, '', target);
  };

  // ---- Firma als Adresse: ?firma=ID an die aktuelle Ansicht hängen
  const plainShow = window.showModal;
  window.showModal = async function (id = null, offer = null) {
    const r = await plainShow(id, offer);
    if (id && modalOpen() && !fromHistory) {
      const {view, params} = parse(location.hash);
      if (params.get('firma') !== String(id)) {
        params.set('firma', String(id));
        history.pushState(null, '', build(view || currentView, params));
        pushedLead = true;
      }
    }
    return r;
  };
  const plainClose = window.closeModal;
  window.closeModal = function () {
    const r = plainClose();
    // Erst nach dem aktuellen Ablauf entscheiden: Springt der Aufrufer gleich in eine andere Ansicht, bleibt die Firma im
    // Verlauf – „Zurück“ öffnet sie dann wieder. Wurde nur geschlossen, wird der Verlaufseintrag der Firma zurückgenommen.
    setTimeout(() => {
      const {view, params} = parse(location.hash);
      if (!params.has('firma') || modalOpen()) { if (!params.has('firma')) pushedLead = false; return; }
      if (pushedLead) { pushedLead = false; ignorePop++; history.back(); }
      else { params.delete('firma'); history.replaceState(null, '', build(view || currentView, params)); }
    }, 0);
    return r;
  };

  // ---- Adresse anwenden (Neuladen, Zurück/Vor, eingegebene Adresse)
  async function apply(route) {
    let view = route.view || 'dashboard';
    if (view === 'report') view = 'center';  // Bericht ohne Firma: Übersicht der Berichte
    fromHistory = true;
    try {
      if (view === 'leads') {
        const q = route.params.get('suche') || '', st = route.params.get('phase') || '';
        if (document.getElementById('leadSearch')) document.getElementById('leadSearch').value = q;
        if (document.getElementById('stageFilter')) document.getElementById('stageFilter').value = st;
        if (typeof renderLeads === 'function') renderLeads();
      }
      if (view !== currentView || document.getElementById('view' + view[0].toUpperCase() + view.slice(1)).classList.contains('hidden')) window.switchView(view);
      else markArea(view);
      const firma = Number(route.params.get('firma')) || null;
      if (firma && (!modalOpen() || currentLeadId !== firma)) {
        if (leads.some(l => l.id === firma)) await window.showModal(firma);
        else if (typeof toast === 'function') toast('Diese Firma gibt es nicht (mehr).', true);
      } else if (!firma && modalOpen()) {
        if (window.leadGuard) window.leadGuard.requestClose(); else closeModal();
        if (modalOpen()) {  // Rückfrage offen: Adresse wieder auf die Firma stellen
          const p = new URLSearchParams(route.params); p.set('firma', String(currentLeadId));
          history.pushState(null, '', build(view, p));
          pushedLead = true;
        }
      }
      const section = route.params.get('abschnitt');
      if (view === 'settings' && section) setTimeout(() => document.getElementById(section)?.scrollIntoView({behavior: 'smooth', block: 'start'}), 60);
    } finally { fromHistory = false; }
  }

  window.addEventListener('popstate', () => {
    if (ignorePop) { ignorePop--; return; }
    apply(parse(location.hash));
  });

  // ---- Klicks
  document.addEventListener('click', e => {
    const tab = e.target.closest('[data-area-view], [data-view-link]');
    if (tab) return window.switchView(tab.dataset.areaView || tab.dataset.viewLink);
    const jump = e.target.closest('[data-settings-jump], [data-settings-link]');
    if (jump) {
      const id = jump.dataset.settingsJump || jump.dataset.settingsLink;
      if (currentView !== 'settings') window.switchView('settings');
      const p = new URLSearchParams(); p.set('abschnitt', id);
      history.replaceState(null, '', build('settings', p));
      setTimeout(() => document.getElementById(id)?.scrollIntoView({behavior: 'smooth', block: 'start'}), 60);
    }
  }, true);

  // ---- Filter der Firmenliste in der Adresse (ohne neue Verlaufseinträge)
  const syncList = () => { if (currentView === 'leads') history.replaceState(null, '', build('leads', listParams())); };
  document.addEventListener('input', e => { if (e.target.id === 'leadSearch') syncList(); });
  document.addEventListener('change', e => { if (e.target.id === 'stageFilter') syncList(); });

  // ---- Punkt am Bereich, wenn ein Reiter darin etwas Neues zählt
  function dots() {
    for (const a of AREAS) {
      const btn = document.querySelector(`.sidebar .nav[data-area="${a.key}"] .nav-dot`);
      if (!btn) continue;
      // nur Zähler („neu“, fällige Aufgaben), nicht Statusangaben wie die KI-Verfügbarkeit
      const any = [...document.querySelectorAll(`#areaBar .area-tabs[data-area="${a.key}"] small.nav-new, #areaBar .area-tabs[data-area="${a.key}"] #dueBadge`)].some(s => s.textContent.trim());
      btn.textContent = any ? '•' : '';
    }
  }

  function start() {
    const bar = document.getElementById('areaBar');
    if (bar) new MutationObserver(dots).observe(bar, {subtree: true, childList: true, characterData: true});
    dots();
    const route = parse(location.hash);
    if (!route.view) history.replaceState(null, '', build(typeof currentView !== 'undefined' ? currentView : 'dashboard'));
    markArea(route.view || 'dashboard');
    if (route.view) apply(route);
  }
  const ready = window.appReady && typeof window.appReady.then === 'function' ? window.appReady : Promise.resolve();
  ready.then(() => (document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start()));

  window.signalNav = {AREAS, SLUG, areaOf, parse, build};
})();
