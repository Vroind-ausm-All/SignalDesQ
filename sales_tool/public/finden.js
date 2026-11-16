'use strict';
// 2.0.0-dev51 (UX Schritt 3): Bereich „Finden“ mit vier Reitern – Sichten · Neue Suche · Import · Analysen.
// - Einstieg: „Finden“ (Seitenleiste, #/finden, „Neue Firmen finden“) öffnet „Sichten“, wenn offene Treffer warten, sonst „Neue Suche“.
// - „Wen suchst du?“: vier Voreinstellungen, die nur vorhandene Felder setzen (Quellen, Betriebe ohne Rechtsform, Website-Suche, Budget).
//   Welche gerade gilt, ergibt sich aus dem Formular: Wer danach etwas von Hand ändert, behält die Änderung, die Auswahl zeigt „Eigene“.
//   Gemerkt wird sie dadurch mit den übrigen Suchparametern (zuletzt gestartete Suche, Suchprofile) – ohne neue Server-Schnittstelle.
// - Klappzeilen der neuen Suche zeigen ihren Kurzstand; die Statuszeile nennt den Stand der Datenquellen (Einstellungen → Datenquellen).
// - Analysen: eine Reiterzeile für Recherche & Berichte, URL-Recherche, Website-Scoring und Kaufsignale; sie wandert in die sichtbare Ansicht.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const num = n => Number(n || 0).toLocaleString('de-DE');
  const ANALYSEN = ['center', 'research', 'scoring', 'signals', 'report'];
  const SRC = {gleif: 'GLEIF', wikidata: 'Wikidata', osm: 'OpenStreetMap', ted: 'TED'};
  const BUDGET = {max_companies: 300, max_websites: 100, max_minutes: 30};  // wie die bisherige Voreinstellung des Formulars
  // Jede Voreinstellung nennt nur die Felder, die sie setzt; alle übrigen bleiben, wie sie sind.
  const PRESETS = {
    handwerk: {label: 'Handwerk & lokale Betriebe', sources: ['osm', 'wikidata', 'gleif'], include_sole: true, find_websites: true},
    gross: {label: 'Größere Firmen', sources: ['gleif', 'wikidata'], include_sole: false},
    oeffentlich: {label: 'Öffentliche Aufträge', sources: ['ted']},
    alles: {label: 'Alles', sources: ['gleif', 'wikidata', 'osm', 'ted'], include_sole: true, find_websites: true, budget: BUDGET},
  };
  window.findenOpen = window.findenOpen ?? null;

  // ------------------------------------------------------------ Einstieg in „Finden“
  window.areaEntry = view => (view === 'finder' && window.findenOpen > 0 ? 'sichten' : view);
  window.findenEntry = async function () {
    try { window.findenOpen = (await api('/sweep-candidates?status=neu&limit=1')).counts?.neu || 0; } catch { /* ohne Zahl: neue Suche */ }
    return window.areaEntry('finder');
  };

  // ------------------------------------------------------------ Voreinstellungen
  const form = () => $('#swForm');
  const el = n => form().elements[n];
  const sources = () => $$('#swForm [name=src]').filter(x => x.checked).map(x => x.value).sort();
  function matches(p) {
    if (p.sources && sources().join() !== [...p.sources].sort().join()) return false;
    if ('include_sole' in p && el('include_sole').checked !== p.include_sole) return false;
    if ('find_websites' in p && el('find_websites').checked !== p.find_websites) return false;
    if (p.budget && Object.entries(p.budget).some(([k, v]) => Number(el(k).value) !== v)) return false;
    return true;
  }
  const activePreset = () => Object.keys(PRESETS).find(k => matches(PRESETS[k])) || '';
  window.findenPreset = activePreset;
  function applyPreset(key) {
    const p = PRESETS[key];
    if (!p) return;
    if (p.sources) $$('#swForm [name=src]').forEach(x => { x.checked = p.sources.includes(x.value); });
    if ('include_sole' in p) el('include_sole').checked = p.include_sole;
    if ('find_websites' in p) el('find_websites').checked = p.find_websites;
    if (p.budget) Object.entries(p.budget).forEach(([k, v]) => { el(k).value = String(v); });
    sync();
  }

  // ------------------------------------------------------------ Kurzstand der Klappzeilen und Voreinstellung zeigen
  function sync() {
    if (!form()) return;
    const key = activePreset();
    $$('#fdPresets [data-fd-preset]').forEach(b => { const on = b.dataset.fdPreset === key; b.classList.toggle('is-active', on); b.setAttribute('aria-pressed', String(on)); });
    $('#fdPresetState').textContent = key ? '' : 'Eigene Auswahl';
    const src = sources();
    const online = el('osm_online').checked && src.includes('osm') ? ' (online)' : '';
    $('#fdSrcState').textContent = `${src.length ? src.map(s => SRC[s] + (s === 'osm' ? online : '')).join(' · ') : 'keine Quelle gewählt'} · bis ${num(el('max_companies').value)} neue Firmen · ${num(el('max_websites').value)} Website-Suchen · ${num(el('max_minutes').value)} Min.`;
    const yn = b => (b ? 'ja' : 'nein');
    const orgs = $$('#swForm [name=org]').filter(x => x.checked).map(x => x.parentElement.textContent.trim().split(/[ ,(]/)[0]);
    const kw = el('keywords').value.trim();
    $('#fdOptState').textContent = [`Nur operative: ${yn(el('operative').checked)}`, `ohne Rechtsform: ${yn(el('include_sole').checked)}`,
      `Websites automatisch suchen: ${yn(el('find_websites').checked)}`, orgs.length ? orgs.join(', ') : 'keine Organisationsart',
      el('ted_nationwide').checked ? 'TED bundesweit' : '', kw ? `Stichwörter: ${kw}` : ''].filter(Boolean).join(' · ');
    const sel = $('#swProfile');
    const n = sel ? sel.options.length - 1 : 0;
    $('#fdProfState').textContent = sel && sel.value ? `aktiv: ${sel.selectedOptions[0].textContent}` : (n ? `${n} gespeichert` : 'noch keins gespeichert');
  }
  window.findenSync = sync;

  // ------------------------------------------------------------ Statuszeile: Stand der Datenquellen
  async function sourcesLine() {
    const box = $('#fdSources');
    if (!box) return;
    const [osm, cat] = await Promise.all([api('/osm').catch(() => null), api('/catalog').catch(() => null)]);
    const osmTxt = !osm ? 'Stand unbekannt' : osm.places ? `<b>${num(osm.places)} Betriebe ✓</b>` : '<b>noch nicht eingelesen</b>';
    const catTxt = !cat ? 'Stand unbekannt' : cat.exists && cat.entities ? `<b>${num(cat.active)} Firmen ✓</b>` : '<b>leer</b>';
    box.innerHTML = `Datenquellen: OpenStreetMap-Auszug ${osmTxt} · GLEIF-Katalog ${catTxt} · <button type="button" class="ui-txt" data-settings-link="datenquellen">Einrichten unter Einstellungen → Datenquellen</button>`;
    if ($('#osmSummary') && osm) $('#osmSummary').textContent = osm.places ? `${num(osm.places)} Betriebe im lokalen Bestand` : 'noch kein lokaler Bestand – Auszug einlesen';
  }
  window.refreshFindenSources = sourcesLine;

  // ------------------------------------------------------------ Analysen: Reiterzeile in die sichtbare Ansicht setzen
  function placeAnalysenBar(view) {
    const bar = $('#fdAnBar');
    if (!bar || !ANALYSEN.includes(view)) return;
    const host = $('#view' + view[0].toUpperCase() + view.slice(1));
    if (host && bar.parentElement !== host) host.insertBefore(bar, host.firstChild);
  }

  function init() {
    if (!form()) return;
    $('#fdPresets').addEventListener('click', e => { const b = e.target.closest('[data-fd-preset]'); if (b) applyPreset(b.dataset.fdPreset); });
    form().addEventListener('change', sync);
    form().addEventListener('input', sync);
    document.addEventListener('signaldesk:swform', sync);
    $('#swProfile')?.addEventListener('change', () => setTimeout(sync, 0));
    // Suchprofile werden nachgeladen: Kurzstand danach neu
    if ($('#swProfile')) new MutationObserver(sync).observe($('#swProfile'), {childList: true});
    document.addEventListener('signaldesk:view', e => {
      const v = e.detail.view;
      placeAnalysenBar(v);
      if (v === 'finder') { sync(); sourcesLine(); }
    });
    sync();
    window.findenEntry();  // Zahl der offenen Treffer für den Einstieg
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
