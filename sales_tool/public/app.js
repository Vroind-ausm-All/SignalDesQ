'use strict';
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const euros = n => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(Number(n)||0);
const fmtDate = s => s ? new Intl.DateTimeFormat('de-DE',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(`${s}T12:00:00`)) : 'ohne Termin';
const short = (s,n=75) => String(s||'').length>n ? String(s).slice(0,n-1)+'…' : String(s||'');
const stageNames = {recherche:'Recherche',qualifiziert:'Qualifiziert',kontakt:'Kontakt geprüft',antwort:'Rückmeldung',termin:'Termin',angebot:'Angebot',gewonnen:'Gewonnen',verloren:'Verloren',gesperrt:'Gesperrt'};
const routeNames = {unbekannt:'Noch offen',persoenliche_empfehlung:'Persönliche Empfehlung',inbound:'Inbound / eigene Anfrage',veranstaltung:'Messe / Veranstaltung',netzwerk:'Bestehendes Netzwerk',brief:'Briefpost',ausschreibung:'Öffentliche Ausschreibung',sonstiges:'Anderer Weg'};
const permissionNames = {unbekannt:'Ungeklärt / keine Ansprache',opt_in:'Opt-in dokumentiert',bestandskunde_pruefen:'Bestandskunde – Voraussetzungen prüfen',telefon_einzelfall:'Telefon – Einzelfallprüfung',nicht_kontaktieren:'Nicht kontaktieren / Widerspruch'};
let config=null, leads=[], tasks=[], stats=null, currentLeadId=null, currentView='dashboard', analysisTimer=null, studioTimer=null;
async function api(path, method='GET', body){const opts={method,headers:{}};if(body!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}const resp=await fetch('/api'+path,opts);const data=await resp.json();if(resp.status===401&&data.auth_required&&window.showLogin)window.showLogin();if(!resp.ok)throw Error(data.error||'Anfrage fehlgeschlagen');return data}
function toast(message,error=false){const e=$('#toast');e.textContent=message;e.classList.toggle('toast-error',!!error);e.classList.add('show');setTimeout(()=>e.classList.remove('show'),3400)}
window.setOfflineBadge=function(s){let b=document.getElementById('offlineBadge');if(!b){b=document.createElement('div');b.id='offlineBadge';b.className='offline-badge hidden';b.setAttribute('role','status');document.querySelector('.side-bottom')?.prepend(b)}b.textContent=s&&s.offline?'⚡ Offline-Modus – keine Abrufe aus dem Internet':'';b.classList.toggle('hidden',!(s&&s.offline))};
document.addEventListener('DOMContentLoaded',()=>{fetch('/api/system/offline').then(r=>r.ok?r.json():null).then(s=>s&&window.setOfflineBadge(s)).catch(()=>{})});
async function reload(){[leads,tasks,stats]=await Promise.all([api('/leads'),api('/tasks'),api('/stats')]);renderAll()}
function switchView(view){currentView=view;$$('.content').forEach(e=>e.classList.add('hidden'));$('#view'+view[0].toUpperCase()+view.slice(1)).classList.remove('hidden');$$('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===view));$('#sectionBreadcrumb').textContent={dashboard:'Übersicht',leads:'Firmenliste',tasks:'Aufgaben',playbook:'Hilfe & Leitfaden',pipeline:'Pipeline',studio:'KI-Studio',research:'URL-Recherche',workspace:'Kontakt & Termine',quotes:'Angebote & Nachkalkulation',accounting:'Rechnungen & Buchhaltung',finder:'Suche & Sichtung',datacheck:'Import & Prüfung',scoring:'Website-Scoring',signals:'Kaufsignale',center:'Recherche & Berichte',quality:'Datenpflege',settings:'Profil & Arbeitsweise',report:'Firmen-Bericht'}[view]||'';if(view==='studio'){refreshAiHealth();loadArchive()}if(view==='research'){loadResearchHistory()}if(view==='workspace'&&window.refreshSalesWorkspace)window.refreshSalesWorkspace();if(view==='workspace'&&window.refreshActionCenter)window.refreshActionCenter();if(view==='quotes'&&window.refreshSalesQuotes)window.refreshSalesQuotes();if(view==='accounting'&&window.refreshAccounting)window.refreshAccounting();if(view==='finder'&&window.refreshLeadFinder)window.refreshLeadFinder();if(view==='datacheck'&&window.refreshDatacheck)window.refreshDatacheck();if(view==='scoring'&&window.refreshScoring)window.refreshScoring();if(view==='signals'&&window.refreshSignals)window.refreshSignals();if(view==='center'&&window.refreshCenter)window.refreshCenter();if(view==='center'&&window.refreshReportsList)window.refreshReportsList();if(['quality','settings','center'].includes(view)&&window.refreshQuality)window.refreshQuality();if(view==='settings'&&window.loadPricingSettings)window.loadPricingSettings();if(view==='dashboard'&&window.refreshToday)window.refreshToday();if(window.markResearchSubnav)window.markResearchSubnav(view);window.scrollTo({top:0,behavior:'smooth'})}
function renderAll(){renderDashboard();renderLeads();renderTasks();renderPipeline();renderStudioLeadOptions();$('#dueBadge').textContent=stats.tasks_due?stats.tasks_due:''}
function renderDashboard(){if(window.refreshToday)window.refreshToday()}
function renderLeads(){const q=$('#leadSearch').value.toLowerCase().trim();const stage=$('#stageFilter').value;const rank=window.leadGradeRank||(()=>2);const filtered=leads.filter(l=>(!stage||l.stage===stage)&&(!q||(l.company+' '+l.signal_note+' '+l.note).toLowerCase().includes(q))).sort((a,b)=>rank(a.id)-rank(b.id)||b.score-a.score||b.id-a.id);$('#leadRows').innerHTML=filtered.map(l=>`<tr data-lead="${l.id}" tabindex="0"><td><b>${escapeHTML(l.company)}</b><small>${escapeHTML(l.industry||'Branche unbekannt')} · ${l.employees||'?'} MA</small></td><td>${escapeHTML(short(config.signals[l.signal_type][1],46))}<small>${l.signal_source?'✓ Beleg vorhanden':'Ohne Beleg'} ${l.signal_date?'· '+fmtDate(l.signal_date):''}</small></td><td>${l.offer&&config.offers[l.offer]?escapeHTML(config.offers[l.offer].title):'<span class="muted">noch nicht gewählt</span>'}</td><td><span class="pill ${l.stage==='gewonnen'?'won':l.stage==='verloren'||l.stage==='gesperrt'?'lost':l.stage==='angebot'?'offer':''}">${stageNames[l.stage]}</span></td><td class="fit-cell">${window.leadGradeCell?window.leadGradeCell(l.id):''}</td><td class="row-arrow">↗</td></tr>`).join('')||'<tr><td colspan="6" class="empty">Keine passenden Leads gefunden.</td></tr>';applyDataWidths($('#leadRows'))}
// CSP erlaubt keine style-Attribute im HTML; Breiten werden daher per CSSOM gesetzt.
function applyDataWidths(root){root.querySelectorAll('[data-w]').forEach(el=>{el.style.width=Math.max(0,Math.min(100,Number(el.dataset.w)||0))+'%'})}
function taskLine(t,today){return `<div class="task-line ${t.done?'done':''}"><input type="checkbox" aria-label="Aufgabe erledigt" data-done="${t.id}" ${t.done?'checked':''} ${!t.done&&['zu_pruefen','abgelehnt'].includes(t.permission_status)?'disabled title="Kontaktaktion erst freigeben"':''}><span><b>${escapeHTML(t.title)}</b> ${t.company?'<small>· '+escapeHTML(t.company)+'</small>':''}${t.permission_status&&t.permission_status!=='nicht_erforderlich'?` <span class="si-perm ${escapeHTML(t.permission_status)}">${{zu_pruefen:'Freigabe offen',freigegeben:'freigegeben',abgelehnt:'abgelehnt'}[t.permission_status]||escapeHTML(t.permission_status)}${t.channel?' · '+escapeHTML(t.channel):''}</span>`:''}</span><small class="${!t.done&&t.due_date&&t.due_date<=today?'late':''}">${fmtDate(t.due_date)}</small><button class="del-task" aria-label="Löschen" data-del-task="${t.id}">✕</button></div>`}
// v1.13: offene Aufgaben gegliedert (tasks.js); hier nur die erledigten.
function renderTasks(){const today=new Date().toISOString().slice(0,10);const done=tasks.filter(t=>t.done);
 $('#taskRows').innerHTML=done.map(t=>taskLine(t,today)).join('')||'<div class="empty">Noch nichts erledigt.</div>';
 if(window.refreshTaskOverview)window.refreshTaskOverview()}
function renderOffers(){let idx=0;$('#offerCards').innerHTML=Object.entries(config.offers).map(([key,o])=>`<div class="offer-card"><small>ANGEBOT 0${++idx}</small><h3>${escapeHTML(o.title)}</h3><strong>${escapeHTML(o.price_label||'')}</strong><p>${escapeHTML(o.weeks||'')} · ${escapeHTML(o.outcome)}</p><small class="muted">Vorlage laut Leistungskatalog – Preis aus den Positionen</small><button class="text-button" data-offer="${key}">Damit Lead anlegen ↗</button></div>`).join('')}
/* 2.0.0-dev16 (M12): nach einer Katalogänderung Angebotskarten und Auswahl „Leistung“ ohne Neuladen auffrischen */
window.refreshOffers=async function(){const c=await api('/config');config.offers=c.offers;renderOffers();const sel=$('#offerSelect'),v=sel.value;sel.innerHTML=`<option value="">– noch keine Leistung gewählt –</option>`+Object.entries(config.offers).map(([k,x])=>`<option value="${escapeHTML(k)}">${escapeHTML(x.title)}</option>`).join('');sel.value=v};
function buildSelects(){const opt=(value,label)=>`<option value="${escapeHTML(value)}">${escapeHTML(label)}</option>`;$('#industrySelect').innerHTML=opt('','– unbekannt –')+config.industries.map(x=>opt(x,x)).join('');$('#signalSelect').innerHTML=Object.entries(config.signals).map(([k,x])=>opt(k,x[1])).join('');$('#offerSelect').innerHTML=opt('','– noch keine Leistung gewählt –')+Object.entries(config.offers).map(([k,x])=>opt(k,x.title)).join('');$('#stageSelect').innerHTML=config.stages.map(s=>opt(s,stageNames[s])).join('');$('#permissionSelect').innerHTML=config.permissions.map(s=>opt(s,permissionNames[s])).join('');$('#routeSelect').innerHTML=config.contact_routes.map(s=>opt(s,routeNames[s])).join('');$('#stageFilter').innerHTML='<option value="">Alle Phasen</option>'+config.stages.map(s=>opt(s,stageNames[s])).join('')}
function modalData(){const fd=new FormData($('#leadForm'));let obj={};for(const [k,v] of fd.entries()){if(k!=='id')obj[k]=v}obj.employees=Number(obj.employees)||0;obj.estimated_budget=Number(obj.estimated_budget)||0;return obj}
function previewScore(){const l=modalData();let score=0,why=[];if(l.permission==='nicht_kontaktieren'||l.stage==='gesperrt'){$('#modalScore').textContent='0';$('#scoreReasons').textContent='Kontakt-/Widerspruchssperre – keine Akquise';return}
let n=({'Industrie & B2B-Technik':25,'B2B-SaaS':21,'Professionelle Dienstleistungen':16,'Sonstige':6})[l.industry]||0;score+=n;why.push('Branchenfit +'+n);n=l.employees>=20&&l.employees<=200?16:l.employees>=10&&l.employees<=500?10:l.employees>0?5:0;score+=n;why.push('Größe +'+n);n=config.signals[l.signal_type][0];score+=n;why.push('Signal +'+n);if(/^https?:\/\//.test(l.signal_source)){score+=6;why.push('Quellenbeleg +6')};if(l.signal_date){const age=Math.floor((Date.now()-new Date(l.signal_date+'T12:00:00').getTime())/86400000);if(age>=0&&age<=30){score+=8;why.push('Aktualität +8')}else if(age>30&&age<=90){score+=4;why.push('Aktualität +4')}}n=l.estimated_budget>=5000?12:l.estimated_budget>=1000?5:0;score+=n;why.push('Budgetannahme +'+n);if((l.offer==='portal'&&l.signal_type==='prozessproblem')||(l.offer==='conversion'&&['produktlaunch','digitalprojekt'].includes(l.signal_type))||(l.offer==='brand'&&l.signal_type==='produktlaunch')){score+=8;why.push('Angebotsfit +8')}$('#modalScore').textContent=Math.min(100,score);$('#scoreReasons').textContent=why.join(' · ')}
async function showModal(id=null,offer=null){if(window.leadGuard){if(!$('#modal').classList.contains('hidden'))window.leadGuard.onClose();else window.leadGuard.remember()}currentLeadId=id;const form=$('#leadForm');form.reset();form.elements.industry.value='';form.elements.signal_type.value='kein_signal';form.elements.offer.value=offer||'';form.elements.stage.value='recherche';form.elements.permission.value='unbekannt';form.elements.contact_route.value='unbekannt';$('#leadExtras').classList.toggle('hidden',!id);$('#leadFile')?.classList.toggle('hidden',!id);if(!id&&$('#leadFile'))$('#leadFile').innerHTML='';$('#deleteLeadBtn').classList.toggle('hidden',!id);$('#modalTitle').textContent=id?'Lead bearbeiten':'Neuer Lead';window.leadTabs?.reset(!!id);if(id){const lead=leads.find(x=>x.id===id);if(!lead)return;for(const k of Object.keys(lead)){if(form.elements[k]&&!['score','score_reasons'].includes(k))form.elements[k].value=lead[k]??''}renderDraft(lead);renderActivities(id);await Promise.all([loadDiscovery(id),loadAnalyses(id),loadDecisionContacts(id),loadContactResearch(id),window.loadCompanyFacts?window.loadCompanyFacts(id):null,window.loadLeadScore?window.loadLeadScore(id):null,window.loadLeadSignals?window.loadLeadSignals(id):null,window.loadSalesIntegration?window.loadSalesIntegration(id):null,window.loadLeadFile?window.loadLeadFile(id):null])}previewScore();$('#modal').classList.remove('hidden');document.body.style.overflow='hidden';if(window.leadGuard)window.leadGuard.afterOpen(!!id);else form.elements.company.focus()}
// 2.0.0-dev13: Schließen durch den Nutzer fragt bei ungespeicherten Eingaben nach (formguard.js)
function requestCloseModal(){if(window.leadGuard)window.leadGuard.requestClose();else closeModal()}
function closeModal(){if(window.leadGuard&&!$('#modal').classList.contains('hidden'))window.leadGuard.onClose();if(analysisTimer)clearTimeout(analysisTimer);analysisTimer=null;$('#modal').classList.add('hidden');document.body.style.overflow=''}
function renderDraft(l){/* 2.0.0-dev13: kein Entwurf behauptet einen Anlass oder eine Leistung, die nicht dokumentiert ist */const good=l.permission==='opt_in';const note=(l.signal_note||'').trim();const sig=l.signal_type&&l.signal_type!=='kein_signal'?config.signals[l.signal_type]?.[1]:'';const offer=l.offer&&config.offers[l.offer];const anlass=note?`bei ${l.company} ist mir Folgendes aufgefallen: ${note}`:sig?`bei ${l.company} ist mir aufgefallen: ${sig}.`:'[Konkreter, geprüfter Anlass – noch keiner dokumentiert. Erst festhalten, dann den Entwurf verwenden.]';const fokus=offer?`Mögliche Leistung (erst nach Bedarfsklärung ansprechen): ${offer.title} – ${offer.outcome}`:'[Passende Leistung – noch nicht gewählt.]';$('#draftText').textContent=`${good?'GRUNDLAGE: Opt-in im CRM markiert; Inhalt/Umfang vor Kontakt prüfen.':'ACHTUNG: Keine Werbeansprache ohne gesondert geprüfte Rechtsgrundlage.'}${!note&&!sig?'\nHINWEIS: Noch kein dokumentierter Anlass – dieser Entwurf ist nur ein Gerüst.':''}\n\nGesprächsleitfaden / Textentwurf:\n\nGuten Tag${l.contact_name?' '+l.contact_name:''},\n\n${anlass}\n\n${fokus} Ich würde gern erst verstehen, welche Priorität das Thema bei Ihnen hat, bevor wir über eine mögliche Lösung sprechen.\n\nWäre ein kurzer Austausch dazu grundsätzlich relevant?\n\nBeste Grüße\n[Dein Name]\n\nNUR für zulässige, individuell geprüfte Kommunikationswege. Kein automatischer Versand.`}
async function renderActivities(id){const list=await api('/activities?lead_id='+id);if(currentLeadId!==id)return;$('#activityRows').innerHTML=list.map(a=>`<div class="activity"><b>${escapeHTML(a.activity_type)}</b><small>${escapeHTML(a.created_at)}</small><div>${escapeHTML(a.detail)}</div></div>`).join('')||'<div class="muted">Noch keine Aktivitäten.</div>'}
async function loadDiscovery(id){
  const form=$('#discoveryForm');form.reset();$('#discoveryProgress').textContent='Bedarfsanalyse wird geladen…';
  try {const d=await api('/leads/'+id+'/discovery');if(currentLeadId!==id)return;
    for(const key of ['problem','impact','current_solution','desired_outcome','timing','decision_process','budget_status','budget_note']){
      if(form.elements[key])form.elements[key].value=d[key]||'';
    }
    $('#discoveryProgress').textContent=`${d.completeness.answered} von ${d.completeness.total} Kernfragen erfasst · keine automatische Angebotsfreigabe`;
  }catch(err){toast('Bedarfsanalyse: '+err.message,true)}
}
async function saveDiscovery(e){e.preventDefault();if(!currentLeadId)return;
 const fields={};for(const [k,v] of new FormData(e.target).entries())fields[k]=v;
 try{const r=await api('/leads/'+currentLeadId+'/discovery','PUT',fields);
 $('#discoveryProgress').textContent=`${r.completeness.answered} von ${r.completeness.total} Kernfragen erfasst · keine automatische Angebotsfreigabe`;
 toast('Bedarfsanalyse gespeichert');}catch(err){toast(err.message,true)}
}

function setAuditStatus(message,isError=false){const el=$('#analysisStatus');el.textContent=message;el.classList.toggle('error',isError)}
const reviewText={ungeprueft:'Noch nicht geprüft',freigegeben:'Manuell freigegeben',verworfen:'Verworfen'};
function renderAnalyses(runs){
  const container=$('#analysisResults');
  if(!runs.length){container.innerHTML='<p class="muted">Hier erscheinen nach dem ersten Durchlauf belegte Website-Beobachtungen und mögliche Bedarfsfragen.</p>';return}
  container.innerHTML=runs.slice(0,5).map(run=>{
    const pageList=(run.pages||[]).map(p=>`<a href="${escapeHTML(p.url)}" target="_blank" rel="noopener noreferrer" class="audit-source">${escapeHTML(short(p.title||p.url,85))}</a>`).join(' · ');
    const warnings=run.warnings?.length?`<p class="audit-warnings">Hinweise: ${escapeHTML(run.warnings.join(' · '))}</p>`:'';
    const findings=(run.findings||[]).map(f=>`<article class="audit-finding">
      <h4>${escapeHTML(f.observation)}</h4><p><b>Möglicher Bedarf:</b> ${escapeHTML(f.hypothesis)}</p>
      <blockquote>„${escapeHTML(f.evidence)}“</blockquote>
      <a class="audit-source" href="${escapeHTML(f.source_url)}" target="_blank" rel="noopener noreferrer">Quelle selbst ansehen ↗</a>
      <p><b>Leistungsbereich:</b> ${escapeHTML(f.category)} · ${escapeHTML(config.offers[f.offer]?.title||f.offer)}</p>
      <p><b>Gesprächsfrage:</b> ${escapeHTML(f.question)}</p>
      <div class="audit-actions"><span class="pill">${reviewText[f.review_status]||'Unbekannt'}</span>
      ${f.review_status==='ungeprueft'?`<button type="button" class="btn btn-ghost" data-review-id="${f.id}" data-review-value="freigegeben">✓ Bestätigen</button><button type="button" class="btn btn-ghost" data-review-id="${f.id}" data-review-value="verworfen">✕ Verwerfen</button>`:''}
      ${f.review_status==='freigegeben'?`<button type="button" class="btn btn-ghost" data-promote-id="${f.id}">Als Lead-Beobachtung übernehmen</button>`:''}
      </div></article>`).join('');
    const condition=run.status==='done'?`Fertig · ${(run.pages||[]).length} Seiten · ${(run.findings||[]).length} belegte Befunde`:
                    run.status==='failed'?`Fehler: ${escapeHTML(run.error||'Unbekannt')}`:'Analyse läuft – Website und Modell werden ausgewertet';
    return `<div class="audit-result-header">Analyse #${run.id} · ${escapeHTML(run.provider)} <small>${escapeHTML(run.created_at)}</small></div><div class="muted">${condition}</div>
    ${run.summary?`<p class="muted">${escapeHTML(run.summary)}</p>`:''}${warnings}${pageList}
    ${run.status==='done'&&!run.findings.length?'<p class="muted">Keine verifizierbaren Befunde. Keine Bedarfsbehauptungen übernommen.</p>':''}${findings}`;
  }).join('');
}
async function loadAnalyses(id){
  if(analysisTimer)clearTimeout(analysisTimer);analysisTimer=null;
  try{
    const runs=await api(`/leads/${id}/analysis`);
    if(currentLeadId!==id)return;
    renderAnalyses(runs);
    if(runs.some(r=>['queued','running'].includes(r.status))){
      setAuditStatus('Analyse läuft. Der Browser ruft öffentliche Seiten ab; das lokale Modell erstellt anschließend Vorschläge.');
      analysisTimer=setTimeout(()=>loadAnalyses(id),2500);
    }else if(runs.length){setAuditStatus(runs[0].status==='failed'?'Letzte Analyse fehlgeschlagen. Ursache steht unten.':'Letzte Analyse abgeschlossen. Prüfe jeden Befund vor Übernahme.',runs[0].status==='failed');}
    else setAuditStatus('Noch keine Analyse. Zuerst Website speichern, anschließend starten.');
  }catch(error){if(currentLeadId===id)setAuditStatus(error.message,true)}
}
async function startAnalysis(){
  const id=currentLeadId;if(!id)return;
  const btn=$('#startAnalysis');btn.disabled=true;
  setAuditStatus('Analyse wird gestartet…');
  try{
    await api(`/leads/${id}/analysis`,'POST',{provider:$('#analysisProvider').value,model:$('#analysisModel').value.trim()||'qwen3:8b'});
    await loadAnalyses(id);toast('Websiteanalyse gestartet');
  }catch(error){setAuditStatus(error.message,true);toast(error.message,true)}finally{btn.disabled=false}
}
async function auditAction(button){
  const id=Number(button.dataset.reviewId||button.dataset.promoteId);
  if(!id||!currentLeadId)return;
  try{
    if(button.dataset.reviewId){await api(`/findings/${id}`,'PATCH',{review_status:button.dataset.reviewValue});toast('Manuelle Prüfung dokumentiert')}
    else {if(!confirm('Diese belegte Beobachtung als Lead-Signal übernehmen? Bestehende Signalangaben werden nicht überschrieben.'))return;
      await api(`/findings/${id}/promote`,'POST',{});
      await reload();const lead=leads.find(l=>l.id===currentLeadId);if(lead){for(const key of ['signal_source','signal_note','offer'])$('#leadForm').elements[key].value=lead[key]||'';previewScore()}
      toast('Beobachtung ins CRM übernommen');}
    await loadAnalyses(currentLeadId);
  }catch(error){toast(error.message,true)}
}

// Small RFC4180-compatible CSV parser: semicolons for German Excel, quotes and newlines supported.
function parseCSV(text){
 text=text.replace(/^\uFEFF/,''); const first=(text.split(/\r?\n/,1)[0]||'');const delim=(first.match(/;/g)||[]).length>(first.match(/,/g)||[]).length?';':',';
 let rows=[],line=[],cell='',quoted=false;
 for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){
   if(quoted&&text[i+1]==='"'){cell+='"';i++}else quoted=!quoted;
 }else if(ch===delim&&!quoted){line.push(cell);cell='';}
 else if((ch==='\r'||ch==='\n')&&!quoted){if(ch==='\r'&&text[i+1]==='\n')i++;line.push(cell);if(line.some(x=>x.trim()))rows.push(line);line=[];cell='';}
 else cell+=ch;}
 if(quoted)throw Error('CSV enthält ein nicht geschlossenes Anführungszeichen.');
 line.push(cell);if(line.some(x=>x.trim()))rows.push(line);
 if(rows.length<2)throw Error('CSV braucht Kopfzeile und mindestens einen Datensatz.');
 const headers=rows.shift().map(s=>s.trim());if(new Set(headers).size!==headers.length)throw Error('Doppelte Spalten in Kopfzeile.');
 return rows.map((row,i)=>{if(row.length!==headers.length)throw Error(`Spaltenzahl in Datenzeile ${i+2} passt nicht.`);return Object.fromEntries(headers.map((h,j)=>[h,row[j].trim()]))});
}
async function importCSV(e){const file=e.target.files?.[0];e.target.value='';if(!file)return;
 if(file.size>65536){toast('Maximal 64 KB CSV je Import.',true);return}
 try{const rows=parseCSV(await file.text());const result=await api('/leads/import','POST',{rows});await reload();
 toast(`${result.imported} importiert, ${result.duplicates} Dubletten, ${result.errors.length} fehlerhaft`);
 if(result.errors.length)alert('Bitte korrigieren:\n'+result.errors.slice(0,15).join('\n'));
 }catch(err){toast(err.message,true)}
}
async function handleLeadSave(e){e.preventDefault();let data=modalData();if(currentLeadId&&window.withLostReason){data=await window.withLostReason(leads.find(l=>l.id===currentLeadId),data);if(!data)return}try{if(currentLeadId)await api('/leads/'+currentLeadId,'PATCH',data);else await api('/leads','POST',data);closeModal();await reload();toast('Lead gespeichert')}catch(err){toast(err.message,true)}}
async function handleDelete(){if(!currentLeadId||!confirm('Lead und alle verknüpften Aktivitäten/Aufgaben unwiderruflich löschen?'))return;try{await api('/leads/'+currentLeadId,'DELETE');closeModal();await reload();toast('Lead endgültig gelöscht')}catch(e){toast(e.message,true)}}
async function handleTask(e){e.preventDefault();const d=new FormData(e.target);try{await api('/tasks','POST',{title:d.get('title'),due_date:d.get('due_date')});e.target.reset();await reload();toast('Aufgabe hinzugefügt')}catch(err){toast(err.message,true)}}
async function handleActivity(e){e.preventDefault();if(!currentLeadId)return;const d=new FormData(e.target);try{await api('/activities','POST',{lead_id:currentLeadId,activity_type:d.get('activity_type'),detail:d.get('detail')});e.target.reset();await renderActivities(currentLeadId);toast('Aktivität dokumentiert')}catch(err){toast(err.message,true)}}
function setupEvents(){ $$('.nav').forEach(e=>e.addEventListener('click',()=>switchView(e.dataset.view))); $$('[data-go]').forEach(e=>e.addEventListener('click',()=>switchView(e.dataset.go)));['#newLeadBtn','#newLeadBtn2'].forEach(s=>$(s).addEventListener('click',()=>showModal()));$('#closeModal').addEventListener('click',()=>requestCloseModal());$('#cancelLead').addEventListener('click',()=>requestCloseModal());$('#modal').addEventListener('mousedown',e=>{if(e.target.id==='modal')requestCloseModal()});document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(window.leadGuard&&window.leadGuard.dialogOpen())return window.leadGuard.cancel();if(!$('#modal').classList.contains('hidden'))requestCloseModal()});$('#leadForm').addEventListener('submit',handleLeadSave);$('#deleteLeadBtn').addEventListener('click',handleDelete);$('#taskForm').addEventListener('submit',handleTask);$('#activityForm').addEventListener('submit',handleActivity);$('#newContactForm').addEventListener('submit',saveDecisionContact);document.body.addEventListener('submit',e=>{if(e.target.matches('.finder-verify'))verifyDecisionContact(e)});$('#startContactResearch').addEventListener('click',startContactResearch);$('#discoveryForm').addEventListener('submit',saveDiscovery);$('#startAnalysis').addEventListener('click',startAnalysis);$('#analysisProvider').addEventListener('change',e=>{$('#analysisModel').disabled=e.target.value==='rules'});$('#csvImport').addEventListener('change',importCSV);$('#leadForm').addEventListener('input',previewScore);$('#leadForm').addEventListener('change',previewScore);$('#leadSearch').addEventListener('input',renderLeads);$('#stageFilter').addEventListener('change',renderLeads);$('#resetFilter').addEventListener('click',()=>{$('#leadSearch').value='';$('#stageFilter').value='';renderLeads()});$('#pipelineNewLead').addEventListener('click',()=>showModal());
 $('#refreshAiHealth').addEventListener('click',refreshAiHealth);
 $('#insertDemo').addEventListener('click',loadDemoText);
 $('#demoText').addEventListener('input',()=>{$('#demoCharacters').textContent=$('#demoText').value.length+' Zeichen · 80 erforderlich'});
 $('#demoProvider').addEventListener('change',()=>{$('#demoModel').disabled=$('#demoProvider').value==='rules'});
 $('#aiDemoForm').addEventListener('submit',runPreview);
 $('#studioStart').addEventListener('click',startStudioAnalysis);
 $('#refreshArchive').addEventListener('click',loadArchive);
 $('#exportBrief').addEventListener('click',exportLeadBrief);
 $('#copyDraft').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#draftText').textContent);toast('Entwurf kopiert – Rechtsgrundlage prüfen')}catch{toast('Kopieren nicht möglich',true)}});
 document.body.addEventListener('click',async e=>{
  const archiveAction=e.target.closest('[data-archive-review],[data-archive-promote]');
  if(archiveAction){await handleArchiveAction(archiveAction);return}
  const candidate=e.target.closest('[data-public-review]');if(candidate){await reviewPublicCandidate(candidate);return;}
  const contactButton=e.target.closest('[data-contact-delete]');if(contactButton){await contactAction(contactButton);return;}
  const audit=e.target.closest('[data-review-id],[data-promote-id]');if(audit){await auditAction(audit);return}const l=e.target.closest('[data-lead]');if(l)return showModal(Number(l.dataset.lead));const g=e.target.closest('[data-stage]');if(g){$('#stageFilter').value=g.dataset.stage;renderLeads();return switchView('leads')}const o=e.target.closest('[data-offer]');if(o)return showModal(null,o.dataset.offer);const del=e.target.closest('[data-del-task]');if(del){if(confirm('Aufgabe löschen?')){await api('/tasks/'+del.dataset.delTask,'DELETE');await reload()}return}const t=e.target.closest('[data-task]');if(t)return switchView('tasks')});document.body.addEventListener('change',async e=>{if(e.target.matches('[data-pipeline-update]')){await updatePipelineStage(e.target);return}if(e.target.matches('[data-done]')){try{await api('/tasks/'+e.target.dataset.done,'PATCH',{done:e.target.checked});await reload()}catch(err){e.target.checked=!e.target.checked;toast(err.message,true)}}});document.body.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-lead],[data-stage]')){e.preventDefault();e.target.click()}})
}
// v0.4 — KI Studio: visibly test the connector before touching live leads.
const demoSample = `FIKTIVES BEISPIEL – keine echte Firma. Die Beispiel Maschinenbau GmbH produziert Komponenten für den Anlagenbau. Auf unserer Website präsentieren wir Fertigung, Montage und industrielle Wartung. Unsere Produktblätter stehen im PDF-Format zum Download bereit. Für Projektanfragen verwenden Sie bitte das zentrale Kontaktformular. Nach dem Absenden kontaktiert unser Vertrieb Sie für eine individuelle Beratung. Unser Service-Team verwaltet Wartungstermine und Kundenanfragen derzeit über Telefon und E-Mail.`;
function loadDemoText(){
 $('#demoText').value=demoSample;
 $('#demoText').dispatchEvent(new Event('input'));
 toast('Fiktiver Beispieltext geladen');
}
async function refreshAiHealth(){
 const el=$('#aiHealth'); el.innerHTML='<div class="health-dot waiting"></div><div><b>Lokale Verbindung wird geprüft…</b><small>http://127.0.0.1:11434</small></div>';
 try{
   const data=await api('/ai/health');
   el.innerHTML=`<div class="health-dot ${data.online?'online':'offline'}"></div><div><b>${data.online?'Ollama verbunden':'Ollama derzeit offline'}</b><small>${escapeHTML(data.message)} ${data.online&&data.models.length?'· '+escapeHTML(data.models.join(', ')):''}</small></div>`;
   if(data.online&&data.models.length){const current=$('#demoModel').value;if(!data.models.includes(current))$('#demoModel').value=data.models[0]}
 }catch(e){el.innerHTML='<div class="health-dot offline"></div><div><b>Verbindungsprüfung fehlgeschlagen</b><small>'+escapeHTML(e.message)+'</small></div>'}
}
function demoResults(result){
 const box=$('#demoResult');
 const cards=(result.findings||[]).map((f,i)=>`<article class="lab-finding"><div class="lab-finding-meta"><span>BEFUND ${String(i+1).padStart(2,'0')} · ${escapeHTML(f.category)}</span><span class="pill">${escapeHTML(config.offers[f.offer]?.title||f.offer)}</span></div><h3>${escapeHTML(f.observation)}</h3><p class="source-evidence">„${escapeHTML(f.evidence)}“</p><p><b>Zu prüfende Hypothese:</b> ${escapeHTML(f.hypothesis)}</p><div class="lab-question"><span>FRAGE FÜR DAS ERSTGESPRÄCH</span>${escapeHTML(f.question)}</div></article>`).join('');
 box.innerHTML=`<div class="studio-result-title"><div><span class="eyebrow">ERGEBNIS · ${result.provider==='ollama'?'LOKALE KI':'OHNE KI'}</span><h3>${escapeHTML(result.summary||'Analyse abgeschlossen')}</h3></div><span class="pill">${result.findings.length} Befunde</span></div><div class="studio-notice">${escapeHTML(result.notice)}</div>${cards||'<div class="empty">Aus dem eingegebenen Text konnten keine belegten Befunde abgeleitet werden. Das ist ein gültiges Analyseergebnis.</div>'}${result.discarded?`<small class="muted">${result.discarded} nicht ausreichend belegte KI-Befunde wurden verworfen.</small>`:''}`;
}
async function runPreview(e){
 e.preventDefault();const btn=$('#runDemo');btn.disabled=true;btn.textContent='Analyse läuft …';
 $('#demoResult').innerHTML='<div class="studio-empty"><div class="studio-spinner"></div><b>Text wird ausgewertet …</b><p>Je nach Modell und Hardware kann die lokale KI etwas benötigen.</p></div>';
 try{
   const data=await api('/ai/preview','POST',{text:$('#demoText').value,provider:$('#demoProvider').value,model:$('#demoModel').value.trim()||'qwen3:8b'});
   demoResults(data);
 }catch(err){$('#demoResult').innerHTML=`<div class="studio-error"><b>Analyse nicht möglich</b><p>${escapeHTML(err.message)}</p><small>Du kannst den Regelmodus ohne Ollama verwenden.</small></div>`}
 finally{btn.disabled=false;btn.textContent='Analyse starten ↗'}
}
function renderStudioLeadOptions(){
 const select=$('#studioLead');const previous=select.value;
 const eligible=leads.filter(x=>x.website&&x.stage!=='gesperrt');
 select.innerHTML='<option value="">Unternehmen auswählen…</option>'+eligible.map(l=>`<option value="${l.id}">${escapeHTML(l.company)} · ${escapeHTML(short(l.website,38))}</option>`).join('');
 if(eligible.some(l=>String(l.id)===previous))select.value=previous;
}
async function startStudioAnalysis(){
 const id=Number($('#studioLead').value);if(!id){toast('Wähle zuerst eine Firma mit Website.',true);return}
 const btn=$('#studioStart');btn.disabled=true;$('#studioLiveStatus').textContent='Websiteanalyse gestartet; du siehst den Fortschritt im Analyseverlauf.';
 try{
   await api(`/leads/${id}/analysis`,'POST',{provider:$('#studioProvider').value,model:$('#demoModel').value.trim()||'qwen3:8b'});
   toast('Analyse gestartet');await loadArchive();
 }catch(e){$('#studioLiveStatus').textContent=e.message;toast(e.message,true)}finally{btn.disabled=false}
}
async function loadArchive(){
 if(studioTimer){clearTimeout(studioTimer);studioTimer=null}
 try{
  const runs=await api('/analyses');
  const box=$('#studioArchive');
  box.innerHTML=runs.length?runs.map(r=>{
   const status=r.status==='done'?'Abgeschlossen':r.status==='failed'?'Fehlgeschlagen':'In Bearbeitung';
   const cards=(r.findings||[]).map(f=>`<div class="archive-finding"><div><span class="pill">${escapeHTML(f.category)}</span><span class="muted">${escapeHTML(reviewText[f.review_status]||f.review_status)}</span></div><b>${escapeHTML(f.observation)}</b><p>${escapeHTML(f.hypothesis)}</p><blockquote>„${escapeHTML(f.evidence)}“</blockquote><a href="${escapeHTML(f.source_url)}" target="_blank" rel="noopener noreferrer">Beleg öffnen ↗</a><p><b>Gesprächsfrage:</b> ${escapeHTML(f.question)}</p><div class="archive-actions">${f.review_status==='ungeprueft'?`<button type="button" class="btn btn-ghost" data-archive-review="${f.id}" data-review-value="freigegeben">✓ Prüfen & freigeben</button><button type="button" class="btn btn-ghost" data-archive-review="${f.id}" data-review-value="verworfen">Verwerfen</button>`:''}${f.review_status==='freigegeben'?`<button type="button" class="btn btn-ghost" data-archive-promote="${f.id}">Ins Lead-Profil übernehmen</button>`:''}</div></div>`).join('');
   return `<article class="archive-run"><div class="archive-run-head"><div><b>${escapeHTML(r.company)}</b><small>#${r.id} · ${escapeHTML(r.created_at)} · ${escapeHTML(r.provider)}</small></div><span class="pill ${r.status==='done'?'won':r.status==='failed'?'lost':''}">${status}</span></div>${r.error?`<p class="studio-error">${escapeHTML(r.error)}</p>`:''}${r.summary?`<p>${escapeHTML(r.summary)}</p>`:''}${cards||((r.status==='done')?'<p class="muted">Keine ausreichend belegten Befunde.</p>':'') }<button type="button" class="text-button" data-lead="${r.lead_id}">Lead öffnen ↗</button></article>`;
  }).join(''):'<div class="empty">Noch keine Websiteanalysen gespeichert. Wähle oben eine Firma und starte die erste Recherche.</div>';
  if(runs.some(r=>['queued','running'].includes(r.status)))studioTimer=setTimeout(loadArchive,2500);
 }catch(e){$('#studioArchive').textContent='Analyseverlauf nicht verfügbar: '+e.message}
}
async function handleArchiveAction(button){
 const id=Number(button.dataset.archiveReview||button.dataset.archivePromote);if(!id)return;
 try{
  if(button.dataset.archiveReview){await api(`/findings/${id}`,'PATCH',{review_status:button.dataset.reviewValue});toast('Prüfentscheidung gespeichert')}
  else{if(!confirm('Freigegebenen Befund als Beobachtung ins Lead-Profil übernehmen? Vorhandene Signale werden nicht überschrieben.'))return;
   await api(`/findings/${id}/promote`,'POST',{});await reload();toast('Befund übernommen')}
  await loadArchive();
 }catch(e){toast(e.message,true)}
}
const pipelineStages=['recherche','qualifiziert','kontakt','antwort','termin','angebot','gewonnen'];
// renderPipeline: siehe pipeline.js (v1.13, kompakte Karten + Drag & Drop)
async function updatePipelineStage(select){
 const id=Number(select.dataset.pipelineUpdate);const lead=leads.find(l=>l.id===id);if(!lead)return;
 if(select.value==='gewonnen'&&!confirm('Ist der Auftrag tatsächlich verbindlich gewonnen?')){select.value=lead.stage;return}
 const data=window.withLostReason?await window.withLostReason(lead,{stage:select.value}):{stage:select.value};if(!data){select.value=lead.stage;return}
 try{await api(`/leads/${id}`,'PATCH',data);await reload();toast('Phase geändert')}catch(e){select.value=lead.stage;toast(e.message,true)}
}
async function exportLeadBrief(){
 if(!currentLeadId)return;
 try{
  const data=await api(`/leads/${currentLeadId}/brief`);
  const blob=new Blob([data.markdown],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=data.filename;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);toast('Bedarfsbriefing exportiert');
 }catch(e){toast(e.message,true)}
}

// 2.0.0-dev14: erst starten, wenn alle Skripte geladen sind (sonst fehlen z. B. renderPipeline oder die Hüllen anderer Module)
// Verzögerte Skripte laufen bei readyState 'interactive' – also vor DOMContentLoaded. Darum immer auf das Ereignis warten, außer die Seite ist schon fertig.
window.appReady=(async()=>{if(document.readyState!=='complete')await new Promise(r=>{document.addEventListener('DOMContentLoaded',r,{once:true});window.addEventListener('load',r,{once:true})});try{config=await api('/config');buildSelects();setupEvents();setupResearchEvents();renderOffers();$('#today').textContent=new Intl.DateTimeFormat('de-DE',{weekday:'short',day:'2-digit',month:'long',year:'numeric'}).format(new Date());await reload()}catch(e){(e.message==='Bitte anmelden.'||toast('Start fehlgeschlagen: '+e.message,true));console.error(e)}})();


// v0.6 – own source-led public-contact research, no third-party contact provider.
async function loadDecisionContacts(leadId){
 try{const data=await api(`/leads/${leadId}/contacts`);if(currentLeadId!==leadId)return;
  const e=escapeHTML;
  const plan=data.research_plan || {targets:[],checklist:[]};
  const guides=plan.targets.map(r=>`<div class="finder-target"><b>${e(r.role)}</b><div class="finder-links"><a href="${e(r.web_search_url)}" target="_blank" rel="noopener noreferrer">↗ Webquellen suchen</a><a href="${e(r.linkedin_search_url)}" target="_blank" rel="noopener noreferrer">↗ LinkedIn-Treffer manuell suchen</a></div></div>`).join('');
  $('#contactRoleHint').innerHTML='<b>Entscheider-Finder v2</b><p>Diese Links öffnen nur eine manuelle Suche. Keine automatische Abfrage bei Google oder LinkedIn.</p><div class="finder-targets">'+guides+'</div>'+
    '<details class="finder-checklist"><summary>5 Punkte vor einer Übernahme prüfen</summary><ol>'+plan.checklist.map(x=>'<li>'+e(x)+'</li>').join('')+'</ol></details>';
  const roles={fachlich:'Fachlich',budget:'Budget',entscheidung:'Entscheidungsbefugt',unbekannt:'Ungeklärt'};
  const statuses={ungeprueft:'Noch nicht geprüft',quelle_geprueft:'Quelle geprüft',rolle_bestaetigt:'Rolle bestätigt',veraltet:'Quelle veraltet'};
  const roleOptions=Object.entries(roles).map(([value,label])=>({value,label}));
  const statusOptions=Object.entries(statuses).map(([value,label])=>({value,label}));
  const options=(items,selected)=>items.map(x=>`<option value="${e(x.value)}" ${x.value===selected?'selected':''}>${e(x.label)}</option>`).join('');
  $('#contactResults').innerHTML=data.contacts.length?data.contacts.map(c=>`<article class="contact-card">
    <div class="contact-card-head"><div><strong>${e(c.full_name)}</strong><small>${e(c.job_title||'Funktion ungeklärt')} · ${e(c.decision_role==='entscheidung'&&c.verification_status!=='rolle_bestaetigt'?'Entscheidungsrolle noch unbestätigt':(roles[c.decision_role]||'Unklar'))}</small></div><span class="pill">${e(statuses[c.verification_status]||'Ungeprüft')}</span></div>
    ${c.business_phone?`<p>Veröffentlichte geschäftliche Nummer: ${e(c.business_phone)} (${e(c.phone_type||'Zuordnung offen')})</p>`:'<p>Persönliche Durchwahl nicht belegt</p>'}
    ${c.business_email?`<p>Geschäftliche E-Mail (Quelle prüfen): ${e(c.business_email)}</p>`:''}
    ${c.source_url?`<a href="${e(c.source_url)}" target="_blank" rel="noopener noreferrer">Belegquelle prüfen ↗</a>`:''}
    ${c.linkedin_url?`<a href="${e(c.linkedin_url)}" target="_blank" rel="noopener noreferrer">Hinterlegtes LinkedIn-Profil manuell öffnen ↗</a>`:''}
    <form class="finder-verify" data-verify-id="${c.id}">
      <div class="finder-form-row"><label>Recherche-Status<select name="verification_status">${options(statusOptions,c.verification_status||'ungeprueft')}</select></label>
      <label>Entscheidungsrolle<select name="decision_role">${options(roleOptions,c.decision_role||'unbekannt')}</select></label></div>
      <label>Quellen-URL (HTTPS)<input type="url" name="source_url" maxlength="500" value="${e(c.source_url||'')}"></label>
      <label>Beleg aus der Quelle<textarea name="source_excerpt" rows="2" maxlength="500" placeholder="Konkrete Passage, die den Arbeitgeber und die Rolle belegt">${e(c.source_excerpt||'')}</textarea></label>
      <label>LinkedIn-URL (nur manuell geprüft)<input type="url" name="linkedin_url" maxlength="500" value="${e(c.linkedin_url||'')}"></label>
      <label>Recherche-/Gesprächsnotiz<textarea name="note" rows="2" maxlength="1000">${e(c.note||'')}</textarea></label>
      <div class="contact-actions"><button type="submit" class="btn btn-primary">Prüfung speichern</button><button type="button" class="btn btn-ghost" data-contact-delete="${c.id}">Kontakt entfernen</button></div>
    </form><small class="muted">Letzte Prüfung: ${e(c.verification_date||'noch nie')} · Kontaktaufnahme nur nach separater Rechtsprüfung</small></article>`).join(''):'<p class="muted">Noch keine beruflichen Ansprechpartner übernommen. Nutze oben die Suchlinks und erfasse anschließend einen belegten Kontakt.</p>';
 }catch(err){if(currentLeadId===leadId)toast('Kontaktliste: '+err.message,true)}
}
async function verifyDecisionContact(e){e.preventDefault();if(!currentLeadId)return;
 const form=e.target, id=Number(form.dataset.verifyId), data=Object.fromEntries(new FormData(form));
 const btn=form.querySelector('button[type="submit"]');btn.disabled=true;
 try{await api(`/contacts/${id}`,'PATCH',data);await loadDecisionContacts(currentLeadId);toast('Rechercheprüfung gespeichert – keine Kontaktberechtigung vergeben')}
 catch(err){toast(err.message,true)}finally{btn.disabled=false}
}
async function saveDecisionContact(e){e.preventDefault();if(!currentLeadId)return;
 const data=Object.fromEntries(new FormData(e.target));
 try{await api(`/leads/${currentLeadId}/contacts`,'POST',data);e.target.reset();await loadDecisionContacts(currentLeadId);toast('Person gespeichert')}
 catch(e){toast(e.message,true)}
}
async function contactAction(btn){if(!currentLeadId)return;if(!confirm('Kontakt aus dem CRM löschen?'))return;
 btn.disabled=true;try{await api(`/contacts/${btn.dataset.contactDelete}`,'DELETE');await loadDecisionContacts(currentLeadId);toast('Kontakt entfernt')}
 catch(e){toast(e.message,true)}finally{btn.disabled=false}
}
async function loadContactResearch(leadId){
 try{const runs=await api(`/leads/${leadId}/contact-research`);if(currentLeadId!==leadId)return;
  if(!runs.length){$('#contactResearchStatus').textContent='Keine Recherche gestartet.';$('#contactResearchResults').innerHTML='';return;}
  const r=runs[0], busy=['queued','running'].includes(r.status);
  $('#contactResearchStatus').textContent=busy?'Öffentliche Seiten werden geprüft – bei größeren Websites kann das dauern.':
    r.status==='failed'?'Recherche fehlgeschlagen: '+r.error:
    `Recherche abgeschlossen · ${r.pages.length} Seiten · ${r.people.length} Namenskandidaten · ${r.channels.length} Kontaktpunkte`;
  const more=r.pages.map(p=>`<a href="${escapeHTML(p.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(p.title||p.url)}</a>`).join(' · ');
  const channelHTML=r.channels.length?r.channels.map(c=>`<div><small>${c.type==='email'?'Veröffentlichte E-Mail':'Veröffentlichte Telefonnummer (Zuordnung zur Person offen)'}</small> <strong>${escapeHTML(c.value)}</strong> · <a href="${escapeHTML(c.source_url)}" target="_blank" rel="noopener noreferrer">Quelle ↗</a></div>`).join(''):'<p class="muted">Keine öffentlich publizierten geschäftlichen Kontaktpunkte erkannt.</p>';
  const peopleHTML=r.people.length?r.people.map(p=>`<article class="contact-card"><div class="contact-card-head"><div><strong>${escapeHTML(p.full_name)}</strong><small>${escapeHTML(p.job_title)} · ${escapeHTML(p.role_hint)} · Priorität ${p.priority}/100 (keine Entscheidungsvollmacht)</small></div><span class="pill">${escapeHTML(p.status)}</span></div>
    ${p.business_email?`<p>Auf Person bezogene veröffentlichte E-Mail: ${escapeHTML(p.business_email)}</p>`:''}
    ${p.business_phone?`<p>Explizit veröffentlichte Durchwahl: ${escapeHTML(p.business_phone)}</p>`:''}
    <p><small>Beleg: ${escapeHTML(p.evidence)}</small></p><a href="${escapeHTML(p.source_url)}" target="_blank" rel="noopener noreferrer">Quelle prüfen ↗</a>
    ${p.status==='ungeprueft'?`<div class="contact-actions"><button type="button" class="btn btn-primary" data-public-review="${p.id}" data-review-decision="accept">Geprüft: ins CRM übernehmen</button><button type="button" class="btn btn-ghost" data-public-review="${p.id}" data-review-decision="reject">Verwerfen</button></div>`:''}
  </article>`).join(''):'<p class="muted">Kein Name mit klarer beruflicher Rollenangabe gefunden. Team/Impressum manuell prüfen oder Recherche erweitern.</p>';
  $('#contactResearchResults').innerHTML=(r.status==='done'?`<h4>Öffentliche Kontaktwege</h4>${channelHTML}<h4>Gefundene Personen (manuell prüfen)</h4>${peopleHTML}<p class="muted">Gelesene Seiten: ${more}</p>`:'')+
    (r.warnings?.length?`<p class="muted">Hinweise: ${escapeHTML(r.warnings.join(' · '))}</p>`:'');
  if(busy)setTimeout(()=>{if(currentLeadId===leadId)loadContactResearch(leadId)},2500);
 }catch(e){if(currentLeadId===leadId)$('#contactResearchStatus').textContent='Recherchefehler: '+e.message}
}
async function startContactResearch(){if(!currentLeadId)return;
 if(!confirm('Bis zu fünf öffentlich zugängliche Seiten des Unternehmens prüfen? Keine externen Kontaktdatenanbieter, keine Kontaktaufnahme.'))return;
 const btn=$('#startContactResearch');btn.disabled=true;
 try{await api(`/leads/${currentLeadId}/contact-research`,'POST',{confirm_public_research:true});toast('Öffentliche Kontaktrecherche gestartet');await loadContactResearch(currentLeadId)}
 catch(e){toast(e.message,true)}finally{btn.disabled=false}
}
async function reviewPublicCandidate(btn){if(!currentLeadId)return;
 const decision=btn.dataset.reviewDecision;
 if(decision==='accept'&&!confirm('Hast du Name, Firma und Funktion auf der verlinkten Website geprüft? Erst danach wird die Person ins CRM übernommen.'))return;
 btn.disabled=true;try{await api(`/contact-candidates/${btn.dataset.publicReview}/review`,'POST',{decision});await Promise.all([loadContactResearch(currentLeadId),loadDecisionContacts(currentLeadId)]);toast(decision==='accept'?'Überprüfter Kandidat ins CRM übernommen':'Kandidat verworfen')}
 catch(e){toast(e.message,true)}finally{btn.disabled=false}
}


// v0.7 – one-URL research report, deliberately separate from CRM writes.
let researchTimer=null, activeResearchId=null;
const researchSafeLink=u=>/^https?:\/\//i.test(String(u||''))?escapeHTML(u):'#';
function setupResearchEvents(){
 $('#researchForm').addEventListener('submit',startResearch);
 $('#researchDemo').addEventListener('click',async()=>{if(researchTimer)clearTimeout(researchTimer);activeResearchId=0;try{const r=await api('/research/demo');setResearchStatus('DEMO – vollständig fiktive Website und Personen, keine echte Recherche und keine CRM-Speicherung.');renderResearch(r)}catch(e){setResearchStatus(e.message,true)}});
 $('#researchProvider').addEventListener('change',e=>{$('#researchModel').disabled=e.target.value!=='ollama'});
 $('#researchRefresh').addEventListener('click',loadResearchHistory);
 $('#researchHistory').addEventListener('click',e=>{const btn=e.target.closest('[data-research-open]');if(btn)openResearch(Number(btn.dataset.researchOpen))});
 $('#researchReport').addEventListener('click',async e=>{
  const imp=e.target.closest('[data-research-import]');if(imp)await importResearch(Number(imp.dataset.researchImport));
  const copy=e.target.closest('[data-research-copy]');if(copy)exportResearchBrief();
  const lead=e.target.closest('[data-research-lead]');if(lead){await reload();switchView('leads');showModal(Number(lead.dataset.researchLead))}
 });
}
function setResearchStatus(message,isError=false){const el=$('#researchStatus');el.textContent=message;el.classList.toggle('error',isError)}
async function startResearch(event){
 event.preventDefault(); const url=$('#researchUrl').value.trim();
 if(!/^https?:\/\//i.test(url)){toast('Bitte eine vollständige https://-URL eingeben.',true);return}
 const btn=$('#researchStart');btn.disabled=true;
 setResearchStatus('Recherche gestartet: Bis zu fünf öffentliche Seiten werden gelesen, anschließend Quellen und Gesprächsfragen geprüft.');
 try{
  const r=await api('/research','POST',{url,provider:$('#researchProvider').value,model:$('#researchModel').value.trim()||'qwen3:8b'});
  activeResearchId=r.id;await loadResearchHistory();await pollResearch(r.id);
 }catch(e){setResearchStatus(e.message,true);toast(e.message,true)}finally{btn.disabled=false}
}
async function loadResearchHistory(){
 try{
  const runs=await api('/research'); const list=$('#researchHistory');
  list.innerHTML=runs.length?runs.map(r=>`<button type="button" class="research-history-item" data-research-open="${r.id}"><span><b>${escapeHTML(new URL(r.url).hostname)}</b><small>${escapeHTML(r.created_at)} · ${escapeHTML(r.provider==='ollama'?'Lokale KI':'Regelmodus')}</small></span><span class="pill ${r.status==='done'?'won':''}">${r.status==='done'?'Fertig':r.status==='failed'?'Fehler':'Läuft'}</span></button>`).join(''):'<p class="muted">Noch keine Recherchen gespeichert.</p>';
 }catch(e){$('#researchHistory').textContent='Verlauf konnte nicht geladen werden: '+e.message}
}
async function openResearch(id){
 if(researchTimer)clearTimeout(researchTimer);researchTimer=null;
 activeResearchId=id;switchView('research');await pollResearch(id);
}
async function pollResearch(id){
 if(researchTimer)clearTimeout(researchTimer);researchTimer=null;
 try{
  const r=await api('/research/'+id);
  if(activeResearchId!==id)return;
  if(r.status==='done'){
   setResearchStatus(`Recherche abgeschlossen · ${r.result.site.pages.length} Seiten · ${r.result.audit.findings.length} Quellenbefunde · ${r.result.decision_makers.people.length} Personenkandidaten`);
   renderResearch(r);await loadResearchHistory();return;
  }
  if(r.status==='failed'){
   setResearchStatus('Recherche fehlgeschlagen: '+r.error,true);
   $('#researchReport').innerHTML='<div class="research-welcome"><h2>Diese Recherche konnte nicht abgeschlossen werden.</h2><p>'+escapeHTML(r.error)+'</p><p>Prüfe die URL, den Websitezugriff, Chromium und gegebenenfalls Ollama. Starte danach einen neuen Durchlauf.</p></div>';
   await loadResearchHistory();return;
  }
  setResearchStatus('Recherche läuft · '+(r.status==='queued'?'in Warteschlange':'Website und Auswertung werden verarbeitet')+'…');
  $('#researchReport').innerHTML='<div class="research-welcome"><div class="research-welcome-icon">⌁</div><h2>Analyse läuft…</h2><p>Öffentliche Seiten abrufen → Inhalte prüfen → Bericht speichern.</p></div>';
  researchTimer=setTimeout(()=>pollResearch(id),2500);
 }catch(e){setResearchStatus(e.message,true)}
}
function renderResearch(r){
 const d=r.result, site=d.site,audit=d.audit,people=d.decision_makers.people,channels=d.contact_channels;
 const e=escapeHTML;
 const findings=audit.findings.map((f,i)=>`<article class="research-finding"><div class="research-item-heading"><span class="research-count">0${i+1}</span><div><small>${e(f.category)} · ${e(config.offers[f.offer]?.title||f.offer)}</small><h3>${e(f.observation)}</h3></div></div><p><strong>Zu prüfende Hypothese:</strong> ${e(f.hypothesis)}</p><blockquote>„${e(f.evidence)}“</blockquote><a href="${researchSafeLink(f.source_url)}" target="_blank" rel="noopener noreferrer">Belegseite öffnen ↗</a><p class="research-question-inline"><strong>Gesprächsfrage:</strong> ${e(f.question)}</p></article>`).join('') || '<p class="research-empty">Keine ausreichend belegten Bedarfshinweise gefunden. Das ist kein Nachweis einer perfekten Website.</p>';
 const peopleCards=people.map(p=>`<article class="research-person"><div class="research-person-avatar">${e(p.full_name.slice(0,1))}</div><div><strong>${e(p.full_name)}</strong><small>${e(p.job_title||'Rolle unbekannt')} · ${e(p.role_hint||'Zuständigkeit offen')}</small>${p.business_email?`<div>Geschäftliche E-Mail: ${e(p.business_email)}</div>`:''}${p.business_phone?`<div>Explizit veröffentlichte Durchwahl: ${e(p.business_phone)}</div>`:''}<a href="${researchSafeLink(p.source_url)}" target="_blank" rel="noopener noreferrer">Quelle prüfen ↗</a><p class="research-evidence">${e(p.evidence)}</p></div></article>`).join('') || '<p class="research-empty">Auf den geprüften Seiten wurde kein ausreichend belegter Name mit passender Funktion erkannt. Die Rollenempfehlung unten hilft bei der manuellen Recherche.</p>';
 const channelCards=channels.map(c=>`<div class="research-channel"><span>${c.type==='email'?'E-Mail':'Telefon · Zuordnung offen'}</span><strong>${e(c.value)}</strong><a href="${researchSafeLink(c.source_url)}" target="_blank" rel="noopener noreferrer">Quelle ↗</a></div>`).join('') || '<p class="research-empty">Keine veröffentlichten Geschäftskontaktdaten auf den geprüften Seiten erkannt.</p>';
 const plan=d.decision_makers.research_plan||{targets:[],checklist:[]};
 const researchTargets=plan.targets.map(t=>`<div class="finder-target"><strong>${e(t.role)}</strong><div class="finder-links"><a href="${e(t.web_search_url)}" target="_blank" rel="noopener noreferrer">Webquellen manuell prüfen ↗</a><a href="${e(t.linkedin_search_url)}" target="_blank" rel="noopener noreferrer">LinkedIn-Treffer über Suche ↗</a></div></div>`).join('');
 const warnings=(d.warnings||[]).map(w=>`<li>${e(w)}</li>`).join('');
 const imported=r.demo?'<span class="pill">Demo – keine CRM-Übernahme</span>':r.lead_id?`<button class="btn btn-primary" data-research-lead="${r.lead_id}">Lead #${r.lead_id} öffnen ↗</button>`:`<button class="btn btn-primary" data-research-import="${r.id}">Nach Prüfung ins CRM übernehmen ↗</button>`;
 $('#researchReport').innerHTML=`<div class="research-report-head"><div><span class="eyebrow">${r.demo?'DEMO · ALLE PERSONEN UND FIRMEN FIKTIV':'02 / DEIN RECHERCHEBERICHT'}</span><h2>${e(site.company_label)}</h2><a href="${researchSafeLink(site.url)}" target="_blank" rel="noopener noreferrer">${e(site.url)} ↗</a><p>${e(audit.summary)}</p></div><div class="research-report-actions">${imported}<button class="btn btn-ghost" data-research-copy="1">Bericht als Markdown exportieren ↓</button></div></div>
 <div class="research-metrics"><div><strong>${site.pages.length}</strong><span>Geprüfte Seiten</span></div><div><strong>${audit.findings.length}</strong><span>Belegte Beobachtungen</span></div><div><strong>${people.length}</strong><span>Personenkandidaten</span></div><div><strong>${channels.length}</strong><span>Kontaktpunkte</span></div></div>
 <div class="research-section-head"><span class="eyebrow">DIGITALE CHANCEN · NICHT BESTÄTIGTER BEDARF</span><h2>Website & mögliche Verbesserungen</h2></div><div class="research-findings">${findings}</div>
 <div class="research-section-head"><span class="eyebrow">RECHERCHEKANDIDATEN</span><h2>Wer könnte verantwortlich sein?</h2></div><p class="muted">Gesuchte Rollen: ${e(d.decision_makers.suggested_roles.join(' · '))}. Erkannte Namen sind weder bestätigte Entscheider noch nachgewiesene Budgetverantwortliche.</p><div class="research-people">${peopleCards}</div>
 <div class="finder-research-panel"><h3>Entscheider-Finder v2 · gezielte Zusatzrecherche</h3><p>Auch wenn die Website keinen Namen enthält, helfen diese Rollen und Suchwege weiter. Google und LinkedIn werden <b>nicht</b> automatisch ausgelesen. Verifiziere Treffer vor einer CRM-Übernahme.</p><div class="finder-targets">${researchTargets}</div><details class="finder-checklist"><summary>Quellen- und Rollenprüfung</summary><ol>${plan.checklist.map(x=>`<li>${e(x)}</li>`).join('')}</ol></details></div>
 <div class="research-section-head"><span class="eyebrow">ÖFFENTLICH PUBLIZIERTE KONTAKTE</span><h2>Geschäftliche Kontaktwege</h2></div><div class="research-channels">${channelCards}</div><p class="muted">Eine Nummer aus der Fußzeile wird nicht einer Person zugerechnet. Ein veröffentlichter Kontakt ist keine Erlaubnis zur Werbung.</p>
 <div class="research-section-head"><span class="eyebrow">DISCOVERY · ERSTGESPRÄCH</span><h2>Fragen, die du stellen kannst</h2></div><ol class="research-questions">${d.questions.map(q=>`<li>${e(q)}</li>`).join('')}</ol>
 <details class="research-details"><summary>Geprüfte Quellen & technische Hinweise</summary><div class="research-pages">${site.pages.map(p=>`<a href="${researchSafeLink(p.url)}" target="_blank" rel="noopener noreferrer">${e(p.title||p.url)} ↗</a>`).join('')}</div>${warnings?`<ul>${warnings}</ul>`:''}</details>
 <div class="legal-foot"><b>Vor jeder Kontaktaufnahme:</b> Die rechtliche Grundlage für den konkreten Kanal selbst prüfen. Diese Recherche verschickt keine Nachrichten und keine Anrufe. CRM-Übernahme speichert Befunde und Personen zunächst ungeprüft.</div>`;
}
async function importResearch(id){
 if(!confirm('Recherche als Lead übernehmen? Personen und Website-Befunde bleiben ungeprüft. Bestehende Kontaktberechtigungen und bestätigte Lead-Signale werden nicht überschrieben.'))return;
 try{const r=await api('/research/'+id+'/import','POST',{confirm:true});toast(r.already_imported?'Recherche ist bereits im CRM.':'Recherche ins CRM übernommen: prüfe '+r.findings_pending_review+' Befunde und '+r.contacts_pending_review+' Kontakte.');await reload();await pollResearch(id)}catch(e){toast(e.message,true)}
}
async function exportResearchBrief(){
 if(activeResearchId===null)return;
 try{const r=await api(activeResearchId===0?'/research/demo':'/research/'+activeResearchId);if(r.status!=='done')return;const d=r.result;
 const lines=['# SignalDesk – Recherchebericht', '',d.site.company_label,d.site.url,'','## Beobachtungen (ungeprüft)'];
 d.audit.findings.forEach(f=>lines.push('',`- ${f.observation}`,`  - Hypothese: ${f.hypothesis}`,`  - Beleg: ${f.evidence}`,`  - Quelle: ${f.source_url}`,`  - Frage: ${f.question}`));
 lines.push('','## Recherchekandidaten');d.decision_makers.people.forEach(p=>lines.push(`- ${p.full_name} – ${p.job_title} (${p.source_url})`));
 lines.push('','## Öffentliche Kontaktwege');d.contact_channels.forEach(c=>lines.push(`- ${c.type}: ${c.value} (${c.source_url})`));
 lines.push('','## Erstgesprächsfragen');d.questions.forEach(q=>lines.push('- '+q));
 lines.push('','## Einschränkungen','Keine automatisch bestätigten Kaufabsichten, Entscheiderbefugnisse oder Kontaktberechtigungen.');
 const blob=new Blob([lines.join('\n')],{type:'text/markdown;charset=utf-8'}),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='signaldesk-recherche-'+r.id+'.md';a.click();URL.revokeObjectURL(u);toast('Bericht exportiert');
 }catch(e){toast(e.message,true)}
}
