'use strict';
// 2.0.0-dev14 (Produktreview M07/U01/U03): sechs Bereiche mit Reitern und direkten Adressen.
// - Seitenleiste: Heute · Finden · Firmen · Angebote · Abrechnen · Einstellungen; die Ansichten eines Bereichs stehen oben als Reiter.
// - Jede Ansicht hat eine Adresse (#/firmen/pipeline), eine Firma zusätzlich ?firma=ID, ein Einstellungsabschnitt ?abschnitt=…,
//   die Firmenliste ihre Filter (?suche=…&phase=…). Zurück/Vor und Neuladen führen an dieselbe Stelle.
// Keine Datenmigration: es ändern sich nur Anordnung und Adressen; alle bisherigen Ansichten bleiben erreichbar.
(function () {
  const AREAS = [
    {key: 'heute', label: 'Heute', views: ['dashboard', 'tasks', 'workspace']},
    // 2.0.0-dev51 (UX Schritt 3): Finden hat vier Reiter – Sichten · Neue Suche · Import · Analysen (Recherche, URL-Recherche,
    // Website-Scoring, Kaufsignale, Bericht als Unteransichten). Alle bisherigen Adressen gelten weiter.
    {key: 'finden', label: 'Finden', views: ['sichten', 'finder', 'datacheck', 'center', 'research', 'scoring', 'signals', 'report']},
    {key: 'firmen', label: 'Firmen', views: ['leads', 'pipeline', 'quality']},
    // 2.0.0-dev52 (UX Schritt 4): Angebote hat drei Reiter – Angebote · Aufträge & Betreuung · Auswertung
    {key: 'angebote', label: 'Angebote', views: ['quotes', 'orders', 'insights']},
    // 2.0.0-dev53 (UX Schritt 5): Abrechnen hat vier Reiter – Rechnungen · Ausgaben · Auswertung · Steuer & Export
    {key: 'abrechnen', label: 'Abrechnen', views: ['accounting', 'expenses', 'revenue', 'tax']},
    // 2.0.0-dev53: Einstellungen ohne Reiter – Abschnittsliste mit Kurzstand (einstellungen.js); KI-Studio und Hilfe sind Abschnitte daraus
    {key: 'einstellungen', label: 'Einstellungen', views: ['settings', 'studio', 'playbook']},
  ];
  const SLUG = {dashboard: 'heute', tasks: 'heute/aufgaben', workspace: 'heute/kontakt-termine',
    sichten: 'finden/sichten', finder: 'finden/neue-suche', datacheck: 'finden/import', center: 'finden/recherche', research: 'finden/url-recherche',
    scoring: 'finden/website-scoring', signals: 'finden/kaufsignale', report: 'finden/bericht',
    leads: 'firmen', pipeline: 'firmen/pipeline', quality: 'firmen/datenpflege',
    quotes: 'angebote', orders: 'angebote/auftraege', insights: 'angebote/auswertung',
    accounting: 'abrechnen', expenses: 'abrechnen/ausgaben', revenue: 'abrechnen/auswertung', tax: 'abrechnen/steuer',
    settings: 'einstellungen', studio: 'einstellungen/ki-studio', playbook: 'einstellungen/hilfe'};
  const BY_SLUG = Object.fromEntries(Object.entries(SLUG).map(([v, s]) => [s, v]));
  const AREA_OF = Object.fromEntries(AREAS.flatMap(a => a.views.map(v => [v, a.key])));
  const ANALYSEN = ['center', 'research', 'scoring', 'signals', 'report'];  // 2.0.0-dev51: Unteransichten des Reiters „Analysen“
  const scrollOf = {};
  let fromHistory = false, pushedLead = false, ignorePop = 0, restoringOffer = null;

  const areaOf = view => AREA_OF[view] || 'heute';
  const modalOpen = () => !!document.getElementById('modal') && !document.getElementById('modal').classList.contains('hidden');

  function parse(hash) {
    const h = String(hash || '').replace(/^#\/?/, '');
    const [path, query = ''] = h.split('?');
    const params = new URLSearchParams(query);
    // 2.0.0-dev40 (M07 B): Firmenakte als eigene Seite – #/firmen/akte/ID (ältere Adressen mit ?firma=ID gelten weiter)
    const akte = path.replace(/\/+$/, '').match(/^firmen\/akte\/(\d+)$/);
    if (akte) { params.set('firma', akte[1]); return {view: 'leads', params, akte: true}; }
    // 2.0.0-dev51: #/finden führt zu „Sichten“, wenn offene Treffer warten, sonst zu „Neue Suche“ (Entscheidung in apply)
    if (path.replace(/\/+$/, '') === 'finden') return {view: 'finder', params, entry: true};
    return {view: BY_SLUG[path.replace(/\/+$/, '')] || null, params};
  }
  // Filter der Firmenliste wandern mit, damit Neuladen und „← Zurück“ wieder die gefilterte Liste zeigen
  const akteHash = id => { const q = (typeof currentView !== 'undefined' && currentView === 'leads') ? listParams().toString() : ''; return '#/firmen/akte/' + id + (q ? '?' + q : ''); };
  function build(view, params) {
    const q = params ? params.toString() : '';
    return '#/' + (SLUG[view] || 'heute') + (q ? '?' + q : '');
  }
  function listParams() {
    const p = new URLSearchParams();
    const q = document.getElementById('leadSearch')?.value.trim(), st = document.getElementById('stageFilter')?.value;
    if (q) p.set('suche', q);
    if (st) p.set('phase', st);
    if (window.leadList && window.leadList.preset !== 'alle') p.set('ansicht', window.leadList.preset);  // 2.0.0-dev15
    return p;
  }
  // Angebot: siehe wrapOffer; 2.0.0-dev53: Einstellungen tragen ihren Abschnitt in der Adresse
  const viewParams = view => (view === 'leads' ? listParams() : view === 'settings' && window.einstellungen ? window.einstellungen.params() : new URLSearchParams());

  // ---- Darstellung des aktiven Bereichs
  function markArea(view) {
    const area = areaOf(view);
    document.querySelectorAll('.sidebar .nav[data-area]').forEach(b => {
      const on = b.dataset.area === area;
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    // 2.0.0-dev50: Reiter stehen in der Kopfzeile; ein Bereich mit nur einer Ansicht zeigt keine Reiterleiste
    document.querySelectorAll('#areaBar .area-tabs').forEach(n => n.classList.toggle('hidden', n.dataset.area !== area || n.querySelectorAll('[data-area-view]').length < 2));
    document.querySelectorAll('#areaBar [data-area-view]').forEach(b => {
      const on = b.dataset.areaView === view || (ANALYSEN.includes(view) && b.dataset.areaGroup === 'analysen');
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    // Reiterzeile „Analysen“ (steht in der sichtbaren Analyse-Ansicht): Bericht gehört zu „Recherche & Berichte“
    document.querySelectorAll('.fd-an [data-area-view]').forEach(b => {
      const on = b.dataset.areaView === view || (view === 'report' && b.dataset.areaView === 'center');
      b.classList.toggle('is-active', on);
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
      const {params} = parse(location.hash);
      if (params.get('firma') !== String(id)) {
        history.pushState(null, '', akteHash(id));  // 2.0.0-dev40: eigene Adresse der Akte
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
      else { params.delete('firma'); history.replaceState(null, '', build(view || currentView, params)); }  // direkt geöffnete Akte → Liste
    }, 0);
    return r;
  };

  // ---- Adresse anwenden (Neuladen, Zurück/Vor, eingegebene Adresse)
  async function apply(route) {
    let view = route.view || 'dashboard';
    if (view === 'report') view = 'center';  // Bericht ohne Firma: Übersicht der Berichte
    // 2.0.0-dev53: ?abschnitt=ki-werkzeuge bzw. hilfe öffnet die Ansicht KI-Studio bzw. Playbook
    if (view === 'settings' && window.einstellungen) view = window.einstellungen.viewFor(route.params);
    if (route.entry && window.findenEntry) {  // 2.0.0-dev51: Einstieg in „Finden“ nach offenen Treffern
      view = await window.findenEntry(true);
      history.replaceState(null, '', build(view, route.params));
    }
    fromHistory = true;
    try {
      if (view === 'leads') {
        const q = route.params.get('suche') || '', st = route.params.get('phase') || '';
        if (document.getElementById('leadSearch')) document.getElementById('leadSearch').value = q;
        if (document.getElementById('stageFilter')) document.getElementById('stageFilter').value = st;
        if (window.leadList) window.leadList.setPreset(route.params.get('ansicht') || 'alle', false);
        else if (typeof renderLeads === 'function') renderLeads();
      }
      // Akte direkt aufgerufen (Adresse, Neuladen): die Ansicht dahinter nicht wechseln, wenn schon eine sichtbar ist
      const keep = route.akte && typeof currentView !== 'undefined' && currentView && currentView !== 'dashboard';
      if (!keep && (view !== currentView || document.getElementById('view' + view[0].toUpperCase() + view.slice(1)).classList.contains('hidden'))) window.switchView(view);
      else markArea(route.akte ? 'leads' : view);
      const firma = Number(route.params.get('firma')) || null;
      if (firma && (!modalOpen() || currentLeadId !== firma)) {
        if (leads.some(l => l.id === firma)) await window.showModal(firma);
        else if (typeof toast === 'function') toast('Diese Firma gibt es nicht (mehr).', true);
      } else if (!firma && modalOpen()) {
        if (window.leadGuard) window.leadGuard.requestClose(); else closeModal();
        if (modalOpen()) {  // Rückfrage offen: Adresse wieder auf die Firma stellen
          history.pushState(null, '', akteHash(currentLeadId));
          pushedLead = true;
        }
      }
      // 2.0.0-dev38 (M07): geöffnetes Angebot als Adresse (#/angebote?angebot=ID)
      const offer = Number(route.params.get('angebot')) || null;
      if (view === 'quotes' && offer && window.wsOpenProposal) {
        restoringOffer = offer;  // nur dieses Öffnen schreibt keinen neuen Verlaufseintrag
        try { await window.wsOpenProposal(offer); } finally { restoringOffer = null; }
      } else if (view === 'quotes' && window.angebote) {
        // 2.0.0-dev52: ohne Angebot die Liste, mit ?neu=1 der Editor für ein neues Angebot
        if (route.params.get('neu')) window.angebote.showEdit(false); else window.angebote.showList();
      }
      // 2.0.0-dev53: die Adresse #/abrechnen zeigt die Rechnungsliste (Editor und geöffnete Rechnung haben keine eigene Adresse)
      if (view === 'accounting' && window.accShowList) window.accShowList();
      // 2.0.0-dev53: Abschnitt der Einstellungen (Name oder bisherige Element-ID); ohne Abschnitt der zuletzt benutzte, schmal die Liste
      if (route.view === 'settings' && window.einstellungen) {
        if (view === 'settings') await window.einstellungen.route(route.params);
        else if (route.params.get('abschnitt')) await window.einstellungen.open(route.params.get('abschnitt'), {history: true});
      }
    } finally { fromHistory = false; }
  }

  window.addEventListener('popstate', () => {
    if (ignorePop) { ignorePop--; return; }
    apply(parse(location.hash));
  });

  // ---- Klicks
  document.addEventListener('click', e => {
    // 2.0.0-dev53: Abschnittsliste und Verweise in die Einstellungen öffnen den Abschnitt (mit Eingabeschutz, einstellungen.js)
    const es = e.target.closest('#esNav .es-item');
    if (es && window.einstellungen) { e.preventDefault(); return window.einstellungen.pick(es.dataset.esKey); }
    const tab = e.target.closest('[data-area-view], [data-view-link]');
    if (tab) { if (tab.closest('summary')) e.preventDefault(); return window.switchView(tab.dataset.areaView || tab.dataset.viewLink); }
    const jump = e.target.closest('[data-settings-jump], [data-settings-link]');
    if (jump) {
      if (jump.closest('summary')) e.preventDefault();  // Aktion in einer Klappzeile: nur springen, nicht aufklappen
      const id = jump.dataset.settingsJump || jump.dataset.settingsLink;
      if (window.einstellungen) return window.einstellungen.open(id);
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
  document.addEventListener('signaldesk:leadfilter', syncList);  // Arbeitsansicht gewechselt

  // ---- Punkt am Bereich, wenn ein Reiter darin etwas Neues zählt
  function dots() {
    for (const a of AREAS) {
      const btn = document.querySelector(`.sidebar .nav[data-area="${a.key}"] .nav-dot`);
      if (!btn) continue;
      // nur Zähler („neu“, fällige Aufgaben), nicht Statusangaben wie die KI-Verfügbarkeit
      const any = [...document.querySelectorAll(`#areaBar .area-tabs[data-area="${a.key}"] small.nav-new, #areaBar .area-tabs[data-area="${a.key}"] #dueBadge`)].some(s => s.textContent.trim())
        || (a.key === 'finden' && !!document.getElementById('sgNavBadge')?.textContent.trim());  // 2.0.0-dev51: Kaufsignale stehen unter „Analysen“
      btn.textContent = any ? '•' : '';
    }
  }

  // ---- 2.0.0-dev38 (M07): geöffnetes Angebot in die Adresse schreiben (ohne neuen Verlaufseintrag beim Neuladen)
  function wrapOffer() {
    const plainOpen = window.wsOpenProposal;
    if (typeof plainOpen !== 'function' || plainOpen.__nav) return;
    const wrapped = async function (id) {
      const r = await plainOpen(id);
      if (id && id !== restoringOffer && currentView === 'quotes') {
        const {params} = parse(location.hash);
        if (params.get('angebot') !== String(id)) {
          params.delete('neu');  // 2.0.0-dev52: aus dem Editor gespeichert → Adresse des Angebots
          params.set('angebot', String(id));
          history.pushState(null, '', build('quotes', params));
        }
      }
      return r;
    };
    wrapped.__nav = true;
    window.wsOpenProposal = wrapped;
  }

  function start() {
    wrapOffer();
    const bar = document.getElementById('areaBar');
    if (bar) new MutationObserver(dots).observe(bar, {subtree: true, childList: true, characterData: true});
    const sg = document.getElementById('sgNavBadge');
    if (sg) new MutationObserver(dots).observe(sg, {subtree: true, childList: true, characterData: true});
    dots();
    const route = parse(location.hash);
    if (!route.view) history.replaceState(null, '', build(typeof currentView !== 'undefined' ? currentView : 'dashboard'));
    markArea(route.view || 'dashboard');
    if (route.view) apply(route);
  }
  // ---- 2.0.0-dev49: Hauptnavigation bei schmaler Breite als Schublade
  // Unter 521 px ist die Seitenleiste ausgeblendet; „☰ Menü“ in der Kopfzeile öffnet sie von links. Schließen per Knopf,
  // Escape, Klick auf den abgedunkelten Hintergrund oder Wahl eines Bereichs; der Fokus kehrt dann auf den Menü-Knopf zurück.
  // Auf breiten Bildschirmen ist der Knopf unsichtbar und die Seitenleiste unverändert.
  function drawer() {
    const btn = document.getElementById('navMenuBtn'), side = document.getElementById('sideNav');
    const main = document.querySelector('.main');
    if (!btn || !side) return;
    const narrow = window.matchMedia('(max-width: 520px)');
    const isOpen = () => document.body.classList.contains('nav-open');
    function open() {
      document.body.classList.add('nav-open');
      btn.setAttribute('aria-expanded', 'true');
      if (main) main.inert = true;  // Tab bleibt in der Schublade, der Inhalt dahinter ist nicht bedienbar
      const target = side.querySelector('.nav[aria-current="page"]') || side.querySelector('.nav[data-area]');
      if (target) target.focus();
    }
    function close(focusButton = true) {
      if (!isOpen()) return;
      document.body.classList.remove('nav-open');
      btn.setAttribute('aria-expanded', 'false');
      if (main) main.inert = false;
      if (focusButton && narrow.matches) btn.focus();
    }
    btn.addEventListener('click', () => (isOpen() ? close() : open()));
    document.getElementById('navClose')?.addEventListener('click', () => close());
    document.getElementById('navScrim')?.addEventListener('click', () => close());
    // Bereich oder Hilfe gewählt: der Wechsel selbst läuft über die vorhandenen Klick-Handler (app.js, oben)
    side.addEventListener('click', e => { if (isOpen() && e.target.closest('.nav[data-area], .nav-help, [data-view-link]')) close(); });
    document.addEventListener('keydown', e => {
      if (e.key !== 'Escape' || !isOpen()) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      close();
    }, true);
    // Fenster wieder breit: Schublade ohne Fokuswechsel schließen
    const onChange = () => { if (!narrow.matches) close(false); };
    if (narrow.addEventListener) narrow.addEventListener('change', onChange); else narrow.addListener(onChange);
  }
  drawer();

  const ready = window.appReady && typeof window.appReady.then === 'function' ? window.appReady : Promise.resolve();
  ready.then(() => (document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start()));

  window.signalNav = {AREAS, SLUG, areaOf, parse, build};
})();
