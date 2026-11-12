'use strict';
// 2.0.0-dev7: OpenStreetMap manuell – Stand des lokalen Bestands, drei Wege mit Aufwand, Datei einlesen, fertige Abfrage für
// Overpass Turbo. Es wird nur auf Klick etwas geladen oder gesendet.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const de = n => Number(n || 0).toLocaleString('de-DE');
  let poll = null;

  async function refresh() {
    const box = $('#osmBox');
    if (!box) return;
    const f = $('#swForm')?.elements;
    const qs = new URLSearchParams({place: f?.place.value.trim() || '', radius: f?.radius_km.value || '0'});
    try {
      const r = await api('/osm?' + qs);
      const last = r.imports[0];
      const running = r.jobs.some(j => ['queued', 'running'].includes(j.status));
      $('#osmState').innerHTML = r.places
        ? `<span class="sw-web ok">lokaler Bestand</span> <b>${de(r.places)} Betriebe</b> <small>${de(r.with_zip)} mit PLZ, ${de(r.with_zip_guess)} weitere über Nachbarn geschätzt · ${de(r.without_location)} ohne Lage · ${de(r.with_website)} mit Website · ${de(r.with_phone)} mit Telefon · ${de(r.with_hours)} mit Öffnungszeiten${last ? ` · eingelesen am ${esc(fmtDate((last.finished_at || last.started_at).slice(0, 10)))} aus ${esc(last.filename)}` : ''}</small>`
        : '<span class="sw-web wait">noch kein lokaler Bestand</span> <small>Ohne Auszug liefert OpenStreetMap keine Treffer, solange du nicht „online abfragen“ ankreuzt.</small>';
      $('#osmJob').textContent = running ? 'Datei wird eingelesen … ' + (r.jobs[0].tasks?.[0]?.note || '') : (last && last.status === 'fehler' ? 'Letzter Versuch fehlgeschlagen: ' + last.error : '');
      $('#osmHowto').innerHTML = r.howto.map(h => `<details class="osm-how" ${h.key === 'auszug' && !r.places ? 'open' : ''}><summary><b>${esc(h.title)}</b> <small>${esc(h.effort)}</small></summary><ol>${h.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol></details>`).join('');
      const t = $('#osmTurbo');
      t.classList.toggle('hidden', !r.turbo);
      if (r.turbo) { t.href = r.turbo.url; t.textContent = `Abfrage für „${f.place.value.trim()}“ in Overpass Turbo öffnen ↗`; }
      $('#osmClear').classList.toggle('hidden', !r.places);
      $('#osmNotice').textContent = `${r.notice} Daten: ${r.license}.`;
      clearTimeout(poll);
      if (running) poll = setTimeout(refresh, 2500);
    } catch (e) { $('#osmState').textContent = e.message; }
  }
  window.refreshOsmLocal = refresh;

  async function upload(file) {
    const note = $('#osmJob');
    note.textContent = `${file.name} wird übertragen (${(file.size / 1e6).toFixed(1)} MB) …`;
    try {
      const resp = await fetch('/api/osm/upload?' + new URLSearchParams({filename: file.name.slice(0, 120)}), {method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file});
      const r = await resp.json();
      if (!resp.ok) throw Error(r.error || 'Upload fehlgeschlagen');
      toast('Übertragen – die Datei wird im Hintergrund eingelesen');
      if (window.refreshJobs) window.refreshJobs();
      refresh();
    } catch (e) { note.textContent = ''; toast(e.message, true); }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#osmBox')) return;
    $('#osmFile').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) upload(f); });
    $('#osmClear').addEventListener('click', async () => {
      if (!confirm('Lokalen OpenStreetMap-Bestand löschen? Bereits gefundene Firmen bleiben erhalten.')) return;
      try { await api('/osm/places', 'DELETE'); toast('Lokaler Bestand gelöscht'); refresh(); } catch (e) { toast(e.message, true); }
    });
    $('#osmBox').addEventListener('toggle', () => { if ($('#osmBox').open) refresh(); });
    for (const n of ['place', 'radius_km']) $('#swForm')?.elements[n]?.addEventListener('change', () => { if ($('#osmBox').open) refresh(); });
    document.querySelectorAll('[data-view="finder"], [data-go="finder"]').forEach(b => b.addEventListener('click', refresh));
    refresh();
  });
})();
