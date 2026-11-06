'use strict';
// v1.17 (Masterplan 2.0, Sprint 4): großer GLEIF-Firmenkatalog offline – Datei laden (Streaming, als Hintergrund-Auftrag),
// durchsuchen und Ausgewählte in die Sichtung übernehmen. Nichts wird automatisch Lead; Dubletten werden dort abgeglichen.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const KNOWN = {neu: 'schon in der Sichtung', uebernommen: 'schon Lead', dublette: 'schon Lead', verworfen: 'verworfen', gesperrt: 'Sperrliste', zusammengefuehrt: 'schon in der Sichtung'};
  const num = n => Number(n || 0).toLocaleString('de-DE');
  let results = [], chosen = new Set(), poll = null;

  async function loadStatus() {
    try {
      const s = await api('/catalog');
      const last = s.last_import;
      $('#catSummary').textContent = s.exists && s.entities
        ? `${num(s.active)} aktive Firmen im Katalog${last ? ` · Stand ${fmtDate(last.finished_at.slice(0, 10))}` : ''} · ${s.size_mb} MB`
        : 'Noch leer – GLEIF-Datei laden, dann alle deutschen Firmen mit LEI lokal durchsuchen (auch wenn die GLEIF-Schnittstelle ausfällt).';
      $('#catImports').innerHTML = (s.imports || []).length ? `<div class="sales-subhead">Importprotokoll</div>` + s.imports.map(i => `<div class="sw-src ${i.status === 'fertig' ? 'fertig' : i.status === 'fehler' ? 'fehler' : 'retry'}">
        <b>${esc(i.filename || 'Datei')} · ${i.kind === 'golden' ? 'Vollbestand' : 'Delta'}</b><span class="sw-st">${esc({laeuft: 'läuft', fertig: 'fertig', fehler: 'Fehler', abgebrochen: 'angehalten'}[i.status] || i.status)}</span>
        <small>${i.error ? `<span class="late">${esc(i.error)}</span>` : `${num(i.rows)} Zeilen · ${num(i.inserted)} neu · ${num(i.updated)} geändert · ${num(i.unchanged)} unverändert · ${num(i.deactivated)} nicht mehr aktiv · ${num(i.skipped?.ausland)} außerhalb ${esc(i.countries)} · ${i.seconds} s`}
        · ${esc(i.source)} · Lizenz ${esc(i.license)} · ${esc((i.finished_at || i.started_at).slice(0, 16))}</small></div>`).join('') : '';
      const running = (s.jobs || []).some(j => ['queued', 'running'].includes(j.status)) || (s.imports || []).some(i => i.status === 'laeuft');
      clearTimeout(poll);
      if (running) poll = setTimeout(() => { loadStatus(); if (window.refreshJobs) window.refreshJobs(); }, 3000);
    } catch (e) { $('#catSummary').textContent = e.message; }
  }

  async function upload(file) {
    const kind = $('#catKind').value;
    const note = $('#catUpNote');
    note.textContent = `${file.name} wird übertragen (${(file.size / 1e6).toFixed(1)} MB) …`;
    try {
      const qs = new URLSearchParams({filename: file.name.slice(0, 120), kind});
      const resp = await fetch('/api/catalog/upload?' + qs, {method: 'POST', headers: {'Content-Type': /\.zip$/i.test(file.name) ? 'application/zip' : 'text/csv'}, body: file});
      const r = await resp.json();
      if (!resp.ok) throw Error(r.error || 'Upload fehlgeschlagen');
      note.textContent = 'Übertragen – der Import läuft als Hintergrund-Auftrag (Fortschritt unten).';
      if (window.refreshJobs) window.refreshJobs();
      loadStatus();
    } catch (e) { note.textContent = ''; toast(e.message, true); }
  }

  function renderResults(r) {
    results = r.items;
    $('#catResults').innerHTML = results.length ? `<div class="cat-bar"><span class="muted">${r.capped ? 'mehr als 5.000' : num(r.total)} Treffer${r.total > results.length ? ` · die ersten ${results.length}` : ''}</span>
      <button type="button" class="btn btn-primary" id="catTake">Ausgewählte in die Sichtung übernehmen</button></div>` + results.map(x => `<label class="cat-row">
      <input type="checkbox" data-cat-lei="${esc(x.lei)}" ${x.known ? 'disabled' : ''} ${chosen.has(x.lei) ? 'checked' : ''}>
      <span><b>${esc(x.name)}</b><small>${esc([x.legal_form, [x.zip, x.city].filter(Boolean).join(' '), x.register_id, 'LEI ' + x.lei].filter(Boolean).join(' · '))}${x.active ? '' : ' · <span class="late">nicht mehr aktiv</span>'}</small></span>
      ${x.known ? `<span class="sw-web ok">${esc(KNOWN[x.known.status] || x.known.status)}</span>` : ''}</label>`).join('')
      : '<div class="empty">Keine Treffer im Katalog.</div>';
  }

  function init() {
    if (!$('#catBox')) return;
    $('#catBox').addEventListener('toggle', () => { if ($('#catBox').open) { loadStatus(); if (window.refreshJobs) window.refreshJobs(); } });
    $('#catFile').addEventListener('change', e => { const f = e.target.files[0]; e.target.value = ''; if (f) upload(f); });
    $('#catSearch').addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target.elements;
      const qs = new URLSearchParams({q: f.q.value.trim(), zip: f.zip.value.trim(), city: f.city.value.trim(), limit: '100'});
      [...qs.keys()].filter(k => !qs.get(k)).forEach(k => qs.delete(k));
      try { chosen.clear(); renderResults(await api('/catalog/search?' + qs)); } catch (err) { toast(err.message, true); }
    });
    $('#catResults').addEventListener('change', e => { const l = e.target.dataset.catLei; if (l) e.target.checked ? chosen.add(l) : chosen.delete(l); });
    $('#catResults').addEventListener('click', async e => {
      if (!e.target.closest('#catTake')) return;
      if (!chosen.size) return toast('Bitte Firmen auswählen', true);
      try {
        const r = await api('/catalog/take-over', 'POST', {leis: [...chosen].slice(0, 500)});
        toast(`${r.new} neu in der Sichtung · ${r.merged} mit vorhandenen Treffern zusammengeführt · ${r.known} schon bekannt${r.possible ? ` · ${r.possible} mögliche Dublette(n) zur Prüfung` : ''}`);
        chosen.clear();
        $('#catSearch').requestSubmit();
        if (window.refreshSweep) window.refreshSweep();
      } catch (err) { toast(err.message, true); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
