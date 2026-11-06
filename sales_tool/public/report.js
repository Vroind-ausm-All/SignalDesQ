'use strict';
// Sprint C: Firmen-Bericht mit einem Klick – Impressum, Website-Bewertung, Inhalte & Ansprechpartner, Karriereseite & Signale,
// Pakete. Fakten (mit Fundstelle) und Interpretationen (Hypothesen) stehen getrennt. Nichts wird versendet.
(function () {
  const esc = v => escapeHTML(String(v ?? ''));
  const ST = {wartet: 'wartet', 'läuft': 'läuft …', fertig: 'fertig', fehler: 'Fehler', hinweis: 'Hinweis', 'übersprungen': 'übersprungen'};
  const FIELD = {legal_name: 'Offizieller Name', legal_form: 'Rechtsform', street: 'Straße', zip: 'PLZ', city: 'Ort', register_court: 'Registergericht',
    register_number: 'Registernummer', vat_id: 'USt-IdNr.', business_phone: 'Telefon (allgemein)', business_email: 'E-Mail (allgemein)'};
  let current = null, poll = null;

  const link = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t || u.replace(/^https?:\/\//, ''))} ↗</a>` : '';

  function stepsHtml(rep) {
    return `<ol class="rp-steps">${Object.entries(rep.steps).map(([k, s]) => `<li class="rp-step ${esc(s.status)}"><span class="rp-dot"></span>
      <div><b>${esc(s.label)}</b><small>${esc(ST[s.status] || s.status)}${s.detail ? ' · ' + esc(s.detail) : ''}</small></div></li>`).join('')}</ol>`;
  }

  function section(title, eyebrow, body, extra = '') {
    return `<section class="panel rp-sec"><div class="studio-section-head"><div><span class="eyebrow">${esc(eyebrow)}</span><h2>${esc(title)}</h2></div>${extra}</div>${body}</section>`;
  }

  function render(d) {
    const rep = d.report, lead = d.lead || {}, ds = d.dossier || {};
    const running = rep && ['queued', 'running'].includes(rep.status);
    const head = `<div class="eyebrow">FIRMEN-BERICHT${rep ? ' · ' + esc(fmtDate((rep.finished_at || rep.created_at).slice(0, 10))) : ''}</div>
      <div class="page-title"><div><h1>${esc(lead.company || ds.company || 'Firma')}</h1><p>${link(lead.website || ds.website)} ${ds.priority != null ? `· Recherchepriorität <b>${ds.priority}</b>` : '· Datenlage noch unzureichend'} · Recherchestand ${esc(ds.readiness_pct ?? 0)} %</p></div>
      <div class="acc-btn-group"><button type="button" class="btn btn-primary" data-rp-run="${d.lead_id}" ${running ? 'disabled' : ''}>${rep ? 'Bericht neu erstellen' : 'Bericht erstellen'} ▶</button>
      <button type="button" class="btn btn-ghost" data-rc-lead="${d.lead_id}">Lead öffnen</button>
      <a class="btn btn-ghost" href="/api/research-center/leads/${d.lead_id}/dossier.md" download>Dossier (.md) ↓</a></div></div>`;
    if (!rep) {
      $('#rpBody').innerHTML = head + `<div class="panel rp-sec"><p>Für diese Firma gibt es noch keinen Bericht. Ein Klick erledigt Impressum, Website-Bewertung, Website-Inhalte & Ansprechpartner, Karriereseite & Kaufsignale und die Paketempfehlung.</p></div>`;
      return;
    }
    const imp = d.imprint;
    const impBody = imp ? `<div class="rp-grid">${Object.entries(imp.fields).map(([k, v]) => `<div><small>${esc(FIELD[k] || k)}</small><b>${esc(v.value)}</b>${lead[k] && lead[k] !== v.value ? `<small class="late">im Lead: ${esc(lead[k])}</small>` : ''}</div>`).join('')}</div>
        ${imp.representatives.length ? `<p class="muted">Vertretungsberechtigt laut Impressum: ${imp.representatives.map(esc).join(', ')}</p>` : ''}
        <p class="muted">Fundstelle: ${link(imp.url, 'Impressum')} ${imp.warnings.map(esc).join(' · ')}</p>
        ${imp.review_status === 'offen' && imp.status === 'done' ? `<div class="acc-btn-group"><button type="button" class="btn btn-primary" data-rp-imprint="${imp.item_id}">Firmendaten in den Lead übernehmen</button><span class="muted">Bestätigte Werte werden nicht überschrieben.</span></div>` : imp.review_status === 'uebernommen' ? `<p class="rp-auto">✓ Automatisch in leere Lead-Felder übernommen. Vorhandene oder bestätigte Werte wurden nicht überschrieben; Personen werden nicht automatisch angelegt.</p>`
          : `<p class="muted">Status: ${esc(imp.review_status === 'offen' ? 'noch nicht übernommen' : imp.review_status)}</p>`}`
      : '<div class="empty">Kein Impressum ausgelesen.</div>';
    const w = d.website;
    const webBody = w ? `<div class="rp-scores">${[['overall', 'Gesamt'], ['design', 'Design & UX'], ['web', 'Web & Conversion'], ['process', 'Prozess & App'], ['coverage', 'Belegabdeckung %']].map(([k, l]) => `<div><small>${l}</small><b>${w.scores[k] ?? '–'}</b></div>`).join('')}</div>
        ${w.screenshots.length ? `<div class="rp-shots">${w.screenshots.map(id => `<img src="/api/screenshots/${id}" alt="Screenshot der Website" loading="lazy">`).join('')}</div>` : ''}
        <h4>Beobachtungen (gemessen bzw. beobachtet)</h4><ul class="rp-list">${w.observations.map(o => `<li><b>${esc(o.issue || o.label)}</b> – ${esc(o.evidence)} <small>${esc(o.certainty || '')}</small> ${link(o.source_url, 'Fundstelle')}</li>`).join('') || '<li>Keine auffälligen Beobachtungen.</li>'}</ul>
        ${w.uncertainties.length ? `<p class="muted">Unsicherheiten: ${w.uncertainties.map(esc).join(' · ')}</p>` : ''}
        <div class="acc-btn-group"><button type="button" class="text-button" data-rp-audit="${w.audit_id}">Alle Rubriken in der Website-Bewertung ansehen ↗</button></div>`
      : '<div class="empty">Keine Website-Bewertung.</div>';
    const inh = d.inhalte;
    const inhBody = inh ? `<h4>Hypothesen zum Bedarf (Interpretation, mit Beleg)</h4><ul class="rp-list">${inh.findings.map(f => `<li><b>${esc(f.hypothesis)}</b><br><small>Beobachtung: ${esc(f.observation)} · Beleg: „${esc((f.evidence || '').slice(0, 160))}“ ${link(f.source_url, 'Quelle')}</small></li>`).join('') || '<li>Keine belegten Hinweise gefunden.</li>'}</ul>
        ${inh.channels.length ? `<h4>Öffentliche Kontaktwege der Firma</h4><ul class="rp-list">${inh.channels.map(c => `<li>${esc(c.label || c.type || '')}: ${esc(c.value || '')} ${link(c.source_url, 'Quelle')}</li>`).join('')}</ul>` : ''}
        <p class="muted">Gelesen: ${inh.pages.map(p => link(p.url, p.title || p.url)).join(' · ')}</p>${inh.warnings.length ? `<p class="muted">${inh.warnings.map(esc).join(' · ')}</p>` : ''}`
      : '<div class="empty">Website-Inhalte nicht gelesen.</div>';
    const cand = d.candidates.length ? `<h4>Neue Kandidaten – bitte prüfen</h4>${d.candidates.map(c => `<div class="sales-item"><div><strong>${esc(c.full_name)}</strong><small>${esc(c.job_title || 'Funktion unbekannt')} · ${esc(c.role_hint || '')} ${link(c.source_url, 'Fundstelle')}${c.evidence ? ` · „${esc(c.evidence.slice(0, 120))}“` : ''}</small></div>
        <div class="acc-btn-group"><button type="button" class="btn btn-primary" data-rp-cand="${c.id}" data-d="accept">Übernehmen</button><button type="button" class="btn btn-ghost" data-rp-cand="${c.id}" data-d="reject">Verwerfen</button></div></div>`).join('')}` : '';
    const known = d.contacts.length ? `<h4>Im CRM</h4><ul class="rp-list">${d.contacts.map(c => `<li>${esc(c.full_name)} – ${esc(c.job_title || '')} <small>(${esc(c.verification_status || 'ungeprüft')})</small></li>`).join('')}</ul>` : '';
    const sig = ds.signals?.length ? `<ul class="rp-list">${ds.signals.map(s => `<li><b>${esc(s.title)}</b> <small>${esc(s.polarity === 'contra' ? 'Gegenhinweis' : 'Hinweis')} · ${esc(fmtDate((s.published_at || s.found_at || '').slice(0, 10)))}</small><br><small>„${esc((s.evidence || '').slice(0, 160))}“</small></li>`).join('')}</ul>` : '<div class="empty">Keine Kaufsignale gefunden.</div>';
    const hyp = ds.hypotheses?.length ? `<h4>Verknüpfte Hypothesen</h4><ul class="rp-list">${ds.hypotheses.map(h => `<li><b>${esc(h.hypothesis)}</b> <small>(${esc(h.strength)})</small>${h.counter.length ? `<br><small>Dagegen spricht: ${h.counter.map(esc).join('; ')}</small>` : ''}${h.missing.length ? `<br><small>Fehlt noch: ${h.missing.map(esc).join('; ')}</small>` : ''}</li>`).join('')}</ul>` : '';
    const qs = (ds.questions || []).slice(0, 6);
    const offers = d.offers.length ? `<ul class="rp-list">${d.offers.map(o => `<li><b>${esc(o.title)}</b> <span class="si-status ${esc(o.status)}">${o.status === 'angebotsgrundlage' ? 'Angebotsgrundlage' : 'unverbindlich'}</span>${o.hints.length ? `<br><small>${o.hints.map(h => esc(h.source + ': ' + h.text)).join(' · ')}</small>` : ''}</li>`).join('')}</ul>` : '<div class="empty">Noch keine Paketempfehlung.</div>';
    $('#rpBody').innerHTML = head + `<div class="panel rp-sec"><div class="studio-section-head"><div><span class="eyebrow">ABLAUF</span><h2>${running ? 'Bericht wird erstellt …' : 'Was geprüft wurde'}</h2></div></div>${stepsHtml(rep)}</div>`
      + `<div class="rp-cols">` + section('Firmendaten & Impressum', '1 · FAKTEN MIT FUNDSTELLE', impBody)
      + section('Ansprechpartner', '2 · PERSONEN (FUNKTION ≠ BEFUGNIS)', (cand + known) || '<div class="empty">Keine Ansprechpartner auf der Website gefunden. Tipp: Team-Seite oder Impressum (Geschäftsführung) prüfen.</div>') + `</div>`
      + section('Website-Bewertung', '3 · GEMESSEN', webBody)
      + `<div class="rp-cols">` + section('Website-Inhalte & Bedarfshinweise', '4 · INTERPRETATION', inhBody)
      + section('Kaufsignale', '5 · SIGNALE', sig + hyp) + `</div>`
      + `<div class="rp-cols">` + section('Fragen fürs Erstgespräch', '6 · GESPRÄCH', qs.length ? `<ol class="rp-list">${qs.map(q => `<li>${esc(q)}</li>`).join('')}</ol>` : '<div class="empty">–</div>')
      + section('Passende Pakete', '7 · ANGEBOT (UNVERBINDLICH)', offers, `<button type="button" class="btn btn-ghost" data-rc-offer="${d.lead_id}">Angebot vorbereiten</button>`) + `</div>`
      + `<div class="panel rp-sec rp-next"><div><b>Nächster Schritt:</b> ${esc(ds.next_step || '')}</div><div class="acc-btn-group"><button type="button" class="btn btn-primary" data-rc-handoff="${d.lead_id}">An CRM übergeben</button><button type="button" class="btn btn-ghost" data-rc-lead="${d.lead_id}">Kontaktweg im Lead klären</button></div></div>`
      + `<div class="legal-foot">${esc(d.notice)}</div>`;
  }

  async function load(leadId) {
    clearTimeout(poll);
    try {
      const d = await api(`/leads/${leadId}/report`);
      current = leadId;
      render(d);
      if (d.report && ['queued', 'running'].includes(d.report.status)) poll = setTimeout(() => { if (currentView === 'report' && current === leadId) load(leadId); }, 2500);
    } catch (e) { $('#rpBody').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  window.openReport = async function (leadId, opts = {}) {
    if (typeof closeModal === 'function' && !$('#modal').classList.contains('hidden')) closeModal();
    switchView('report');
    $('#rpBody').innerHTML = '<div class="empty">Lade Bericht …</div>';
    if (opts.create) {
      try {
        const r = await api('/reports', 'POST', {lead_ids: [Number(leadId)]});
        if (r.skipped.length) toast(r.skipped[0].reason, true);
      } catch (e) { toast(e.message, true); }
    }
    load(Number(leadId));
  };

  window.refreshReportsList = async function () {
    try {
      const rows = await api('/reports');
      const show = rows.slice(0, 8);
      $('#rpRecent').classList.toggle('hidden', !show.length);
      $('#rpRecentList').innerHTML = show.map(r => `<button type="button" class="rp-chip ${esc(r.status)}" data-report-open="${r.lead_id}">${esc(r.company)} <small>${esc({queued: 'wartet', running: 'läuft', fertig: 'fertig', fehler: 'Fehler'}[r.status] || r.status)}</small></button>`).join('');
      if (rows.some(r => ['queued', 'running'].includes(r.status)) && currentView === 'center') setTimeout(window.refreshReportsList, 4000);
    } catch { /* still */ }
  };

  function init() {
    if (!$('#viewReport')) return;
    $('#leadReportBtn').addEventListener('click', () => { if (currentLeadId) window.openReport(currentLeadId); });
    $('#rpUrlForm').addEventListener('submit', async e => {
      e.preventDefault();
      try {
        const r = await api('/reports', 'POST', {url: e.target.elements.url.value.trim()});
        if (!r.queued.length) return toast(r.skipped[0]?.reason || 'Kein Bericht gestartet', true);
        e.target.reset();
        if (typeof reload === 'function') reload();
        window.openReport(r.queued[0].lead_id);
      } catch (err) { toast(err.message, true); }
    });
    document.body.addEventListener('click', async e => {
      const o = e.target.closest('[data-report-open]');
      if (o) { e.preventDefault(); return window.openReport(Number(o.dataset.reportOpen)); }
      const r = e.target.closest('[data-rp-run]');
      if (r) return window.openReport(Number(r.dataset.rpRun), {create: true});
      const im = e.target.closest('[data-rp-imprint]');
      if (im) {
        try { await api(`/imprint/items/${im.dataset.rpImprint}/review`, 'POST', {decision: 'ergaenzen', lead_id: Number(current)}); toast('Firmendaten übernommen'); if (typeof reload === 'function') reload(); load(current); }
        catch (err) { toast(err.message, true); }
        return;
      }
      const c = e.target.closest('[data-rp-cand]');
      if (c) {
        try { await api(`/contact-candidates/${c.dataset.rpCand}/review`, 'POST', {decision: c.dataset.d}); toast(c.dataset.d === 'accept' ? 'Ansprechpartner übernommen – Funktion und Befugnis noch prüfen' : 'Verworfen'); load(current); }
        catch (err) { toast(err.message, true); }
        return;
      }
      const a = e.target.closest('[data-rp-audit]');
      if (a) { switchView('scoring'); if (window.openAudit) window.openAudit(Number(a.dataset.rpAudit)); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
