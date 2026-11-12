/* 2.0.0-dev11: Darstellung. Läuft im <head> ohne defer, damit Theme und Hell/Dunkel vor dem ersten
   Zeichnen feststehen (kein weißes Aufblitzen im Dunkelmodus). Maßgeblich ist die Einstellung auf dem
   Server (/api/ui/appearance); localStorage ist nur die schnelle Kopie für den Seitenstart. */
(function(){
  const KEY='signaldesk.appearance';
  const DEFAULT={theme:'klassisch',mode:'system',density:'normal'};
  const root=document.documentElement;
  const media=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;
  let current=Object.assign({},DEFAULT,readLocal());
  let options=null;

  function readLocal(){try{const v=JSON.parse(localStorage.getItem(KEY)||'null');return v&&typeof v==='object'?v:{}}catch(e){return{}}}
  function writeLocal(v){try{localStorage.setItem(KEY,JSON.stringify(v))}catch(e){/* privates Fenster: dann eben ohne Kopie */}}
  function dark(){return current.mode==='dunkel'||(current.mode==='system'&&!!(media&&media.matches))}

  function apply(){
    root.dataset.theme=current.theme;
    root.dataset.mode=dark()?'dark':'light';
    root.dataset.density=current.density;
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta&&document.body){const c=getComputedStyle(root).getPropertyValue('--nav-bg').trim();if(c)meta.setAttribute('content',c)}
    syncControls();
  }

  async function request(method,body){
    const opts={method,headers:{}};
    if(body){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}
    const resp=await fetch('/api/ui/appearance',opts);
    const data=await resp.json().catch(()=>({}));
    if(!resp.ok)throw Error(data.error||'Darstellung konnte nicht gespeichert werden.');
    return data;
  }

  function take(data){
    if(!data||!data.appearance)return;
    options=data;current=Object.assign({},DEFAULT,data.appearance);writeLocal(current);apply();render();
  }

  async function set(change){
    const before=current;
    current=Object.assign({},current,change);apply();writeLocal(current);
    try{take(await request('PUT',change))}
    catch(e){current=before;apply();writeLocal(current);if(window.toast)window.toast(e.message,true)}
  }

  function label(list,id){const f=(list||[]).find(x=>x.id===id);return f?f.label:id}

  function syncControls(){
    const btn=document.getElementById('modeToggle');
    if(btn){const d=dark();btn.textContent=d?'☀ Hell':'☾ Dunkel';btn.setAttribute('aria-label',d?'Zum hellen Modus wechseln':'Zum dunklen Modus wechseln');btn.title='Darstellung: '+label(options&&options.themes,current.theme)+' · '+label(options&&options.modes,current.mode)}
    document.querySelectorAll('[data-ap-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.apTheme===current.theme)));
    document.querySelectorAll('[data-ap-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.apMode===current.mode)));
    document.querySelectorAll('[data-ap-density]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.apDensity===current.density)));
  }

  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c])}

  function render(){
    const box=document.getElementById('apPanel');
    if(!box||!options)return;
    const themes=options.themes.map(t=>`<button type="button" class="ap-theme" data-ap-theme="${esc(t.id)}" aria-pressed="false">
      <span class="ap-swatch" data-swatch="${esc(t.id)}" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
      <b>${esc(t.label)}</b><small>${esc(t.hint||'')}</small></button>`).join('');
    const modes=options.modes.map(m=>`<button type="button" class="ap-seg" data-ap-mode="${esc(m.id)}" aria-pressed="false">${esc(m.label)}</button>`).join('');
    const dens=options.densities.map(d=>`<button type="button" class="ap-seg" data-ap-density="${esc(d.id)}" aria-pressed="false" title="${esc(d.hint||'')}">${esc(d.label)}</button>`).join('');
    box.innerHTML=`<div class="ap-themes" role="group" aria-label="Theme">${themes}</div>
      <div class="ap-row"><div><div class="sales-subhead">Hell oder dunkel</div><div class="ap-segs" role="group" aria-label="Hell oder dunkel">${modes}</div></div>
      <div><div class="sales-subhead">Dichte</div><div class="ap-segs" role="group" aria-label="Dichte">${dens}</div></div></div>
      <p class="muted ap-note">Gilt für diese SignalDesk-Installation und wird sofort gespeichert. „Wie System“ folgt der Einstellung deines Betriebssystems.</p>`;
    syncControls();
  }

  document.addEventListener('click',e=>{
    const t=e.target.closest('[data-ap-theme],[data-ap-mode],[data-ap-density],#modeToggle');
    if(!t)return;
    if(t.id==='modeToggle')set({mode:dark()?'hell':'dunkel'});
    else if(t.dataset.apTheme)set({theme:t.dataset.apTheme});
    else if(t.dataset.apMode)set({mode:t.dataset.apMode});
    else if(t.dataset.apDensity)set({density:t.dataset.apDensity});
  });
  if(media){const onChange=()=>{if(current.mode==='system')apply()};media.addEventListener?media.addEventListener('change',onChange):media.addListener(onChange)}

  apply();
  document.addEventListener('DOMContentLoaded',()=>{apply();request('GET').then(take).catch(()=>{/* Anmeldung nötig oder offline: lokale Kopie bleibt */})});
  window.SignalAppearance={get:()=>Object.assign({},current),set,isDark:dark};
})();
