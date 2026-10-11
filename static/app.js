// UI texts come from the server-rendered catalog (locales/<lang>/messages.json).
// Keys ending in _html contain trusted markup; escape every value passed into them.
class Translator{
 constructor(catalog){this.catalog=catalog||{};}
 static fromPage(){try{return new Translator(JSON.parse(document.getElementById('i18n').textContent))}catch{return new Translator({})}}
 t(key,params={}){const text=this.catalog[key]??key;return text.replace(/\{(\w+)\}/g,(match,name)=>name in params?String(params[name]):match);}
}
const translator=Translator.fromPage();const t=(key,params)=>translator.t(key,params);
let selected='A',groups=[],favorites=[],others=[],dragged=null,busy=false;
const $=s=>document.querySelector(s);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const j=await r.json();if(!r.ok)throw Error(j.error||t('common.error'));return j;}
function note(message,error=false){const x=$('#status');x.textContent=message;x.className='status'+(error?' error':'');}
function renderGroups(counts){$('#groups').innerHTML=groups.map(g=>`<button class="group ${selected===g.id?'active':''}" data-group="${g.id}"><span><strong>${esc(g.id)}</strong> · ${esc(g.name)}</span><b>${counts[g.id]??0}</b></button>`).join('');document.querySelectorAll('.group').forEach(b=>b.onclick=()=>{selected=b.dataset.group;$('#favSearch').value='';renderGroups(currentCounts);loadChannels();});$('#currentname').textContent=`${selected} · ${groups.find(g=>g.id===selected)?.name||''}`;}
let currentCounts={};
async function refresh(){const s=await api('/api/status');$('#start').style.display=s.loaded?'none':'block';$('#workspace').style.display=s.loaded?'block':'none';for(const el of ['dbexport','csvexport','jsonexport'])document.getElementById(el).style.display=s.loaded?'inline-block':'none';if(s.loaded){groups=s.groups;currentCounts=s.counts;renderGroups(s.counts);await loadChannels();}else if(s.error)$('#upload-error').textContent=s.error;}
async function loadChannels(){const data=await api('/api/channels?group='+selected);favorites=data.favorites;others=data.others;renderChannels();}
// Use an inline, live-validated input instead of window.prompt. A value above
// 99 is rejected as the user types or pastes it, never silently truncated.
function askProgrammeNumber(title,current,detail){return new Promise(resolve=>{
 const layer=document.createElement('div');layer.className='host-dialog';
 layer.innerHTML=`<form class="host-dialog-inner number-dialog" role="dialog" aria-modal="true" aria-labelledby="number-dialog-title">
 <h2 id="number-dialog-title"></h2><p id="number-dialog-detail"></p>
 <label for="number-dialog-input">${t('number.dialog.label_html')}</label>
 <input class="search" id="number-dialog-input" type="text" inputmode="numeric" pattern="[1-9][0-9]?" autocomplete="off" required aria-describedby="number-dialog-limit number-dialog-error">
 <small id="number-dialog-limit">${esc(t('number.dialog.limit'))}</small>
 <div id="number-dialog-error" class="number-dialog-error" role="status" aria-live="polite"></div>
 <div class="host-dialog-actions"><button class="btn" type="button" id="number-dialog-cancel">${esc(t('common.cancel'))}</button><button class="btn primary" type="submit" id="number-dialog-save">${esc(t('number.dialog.apply'))}</button></div></form>`;
 document.body.appendChild(layer);
 layer.querySelector('#number-dialog-title').textContent=title;
 layer.querySelector('#number-dialog-detail').textContent=t('number.dialog.current',{detail,current});
 const input=layer.querySelector('#number-dialog-input');const message=layer.querySelector('#number-dialog-error');
 const save=layer.querySelector('#number-dialog-save');
 const permitted=s=>/^(?:[1-9]|[1-9][0-9])$/.test(s);
 let previous=permitted(String(current))?String(current):'';input.value=previous;
 function update(){save.disabled=!permitted(input.value);}
 input.addEventListener('input',()=>{
   if(input.value!==''&&!permitted(input.value)){
     input.value=previous;message.textContent=t('number.dialog.error');
   }else{previous=input.value;message.textContent='';}
   update();
 });
 let done=false;function close(value){if(done)return;done=true;layer.remove();resolve(value)}
 layer.querySelector('#number-dialog-cancel').onclick=()=>close(null);
 layer.addEventListener('click',e=>{if(e.target===layer)close(null)});
 layer.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();close(null)}});
 layer.querySelector('form').onsubmit=e=>{e.preventDefault();if(!permitted(input.value)){message.textContent=t('number.dialog.error');return;}close(Number(input.value));};
 update();input.focus();input.select();
});}
const FILTERS={Kind:'kind',Access:'access',Reception:'reception'};
const RECEPTION_LABEL={satellite:'reception.satellite',cable:'reception.cable',terrestrial:'reception.terrestrial'};
const KIND_LABEL={radio:'kind.radio',tv:'kind.tv'},ACCESS_LABEL={encrypted:'access.encrypted',free:'access.free'};
function row(c,favorite){const div=document.createElement('div');div.className='item';div.dataset.id=c.id;div.draggable=favorite;div.innerHTML=`${favorite?`<span class="handle" title="${esc(t('row.drag'))}">⠿</span>`:''}<button type="button" class="number number-button" title="${esc(t('row.change_number'))}">${esc(c.number)} ✎</button><span class="item-name" title="${esc(c.name)}">${esc(c.name)}<div class="item-meta">${esc([t(RECEPTION_LABEL[c.reception]||'reception.other'),c.satellite].filter(Boolean).join(' '))} · ${esc(t(KIND_LABEL[c.kind]||'kind.unknown'))} · ${esc(t(ACCESS_LABEL[c.access]||'access.unknown'))}</div></span><button class="item-actions ${favorite?'danger':''}" title="${esc(t(favorite?'row.remove_title':'row.add_title'))}">${esc(t(favorite?'row.remove':'row.add'))}</button>`;
div.querySelector('.number-button').onclick=async()=>{const newNumber=await askProgrammeNumber(t('number.dialog.title'),c.number,c.name);if(newNumber===null)return;try{const result=await api('/api/channel-number',{id:c.id,number:newNumber});await sync();note(result.numberChange?.swappedWith?t('status.swapped',{name:result.numberChange.swappedWith}):t('status.number_changed'))}catch(e){note(e.message,true)}};
div.querySelector('.item-actions').onclick=async()=>{try{await api('/api/member',{group:selected,id:c.id,enabled:!favorite});await sync();note(t('status.saved'));}catch(e){note(e.message,true)}};
if(favorite){div.addEventListener('dragstart',e=>{dragged=c.id;e.dataTransfer.effectAllowed='move';div.classList.add('dragging')});div.addEventListener('dragend',()=>{dragged=null;document.querySelectorAll('.item').forEach(e=>e.classList.remove('dragging','over'))});div.addEventListener('dragover',e=>{e.preventDefault();div.classList.add('over')});div.addEventListener('dragleave',()=>div.classList.remove('over'));div.addEventListener('drop',async e=>{e.preventDefault();div.classList.remove('over');if(!dragged||dragged===c.id)return;const ids=favorites.map(x=>x.id);ids.splice(ids.indexOf(dragged),1);ids.splice(ids.indexOf(c.id),0,dragged);try{await api('/api/reorder',{group:selected,ids});await sync();note(t('status.order_saved'))}catch(e){note(e.message,true)}})}return div;}
function renderChannels(){const f=$('#favSearch').value.toLowerCase().trim(),q=$('#allSearch').value.toLowerCase().trim();const matches=(c,p)=>Object.entries(FILTERS).every(([id,field])=>{const v=$('#'+p+id).value;return v==='all'||c[field]===v});let fav=favorites.filter(x=>(x.name+' '+x.number).toLowerCase().includes(f)&&matches(x,'fav'));let oth=others.filter(x=>(x.name+' '+x.number).toLowerCase().includes(q)&&matches(x,'all'));$('#favorites').replaceChildren(...fav.map(c=>row(c,true)));$('#others').replaceChildren(...oth.map(c=>row(c,false)));if(!fav.length)$('#favorites').innerHTML=`<div class="empty">${esc(t('empty.favorites'))}</div>`;if(!oth.length)$('#others').innerHTML=`<div class="empty">${esc(t('empty.others'))}</div>`;$('#favoriteCount').textContent=t('count.favorites',{count:favorites.length});$('#otherCount').textContent=t('count.others',{count:others.length});}
async function sync(){const s=await api('/api/status');groups=s.groups;currentCounts=s.counts;renderGroups(s.counts);await loadChannels();}
$('#favSearch').addEventListener('input',renderChannels);$('#allSearch').addEventListener('input',renderChannels);['fav','all'].flatMap(p=>Object.keys(FILTERS).map(f=>p+f)).forEach(id=>$('#'+id).addEventListener('change',renderChannels));
$('#rename').onclick=async()=>{const old=groups.find(g=>g.id===selected)?.name;const name=prompt(t('rename.prompt',{group:selected}),old);if(name===null)return;try{await api('/api/rename',{group:selected,name});await sync();note(t('status.name_saved'))}catch(e){note(e.message,true)}};
$('#renumber').onclick=async()=>{
 const start=await askProgrammeNumber(t('renumber.start_title',{group:selected}),'1',t('renumber.start_detail'));
 if(start===null)return;
 try{
   const plan=await api('/api/renumber/preview?group='+encodeURIComponent(selected)+'&start='+start);
   const warned=new Set((plan.displacedFavorites||[]).map(c=>c.name+'|'+c.old));
   const sample=plan.changes.filter(c=>c.displaced&&!warned.has(c.name+'|'+c.old)).slice(0,6).map(c=>t('renumber.displaced_line',{name:c.name,old:c.old,new:c.new})).join('\n');
   const merges=plan.mergedFavorites||[];
   const mergePreview=merges.map(x=>t('renumber.merge_line',{name:x.name,original:x.originalNumber,copy:x.copyNumber})).join('\n');
   const conflicts=plan.displacedFavorites||[];
   const conflictWarning=conflicts.length?t('renumber.other_lists_warning',{count:conflicts.length})+'\n'+
     conflicts.slice(0,10).map(c=>t('renumber.other_lists_line',{name:c.name,groups:c.groups.join(', '),old:c.old,new:c.new})).join('\n')+(conflicts.length>10?'\n…':'')+'\n'+
     (plan.suggestedStart?t('renumber.suggest_start',{start:plan.suggestedStart}):t('renumber.no_free_start'))+'\n\n':'';
   const message=conflictWarning+t('renumber.summary',{count:plan.favorites,group:selected,start})+
     (merges.length?'\n'+t('renumber.merge_summary',{before:plan.originalFavorites,merges:merges.length}):'')+'\n'+
     (merges.length?'\n'+t('renumber.merge_header')+'\n'+mergePreview+'\n':'')+
     t('renumber.changes',{changes:plan.changes.length,displaced:plan.displaced})+'\n'+
     (sample?'\n'+t('renumber.sample_header')+'\n'+sample+'\n':'')+
     '\n'+t('renumber.footer');
   if(!plan.changes.length&&!merges.length){note(t('status.already_sequential'));return;}
   if(!confirm(message))return;
   await api('/api/renumber',{group:selected,start,confirmedChanges:plan.changes,confirmedMerges:merges});
   await sync();note(t('status.renumbered'));
 }catch(e){note(e.message,true)}
};
// Generic modal layer (reuses the .host-dialog look). Content is a DOM node;
// callers must escape any data they put into HTML themselves.
class ModalDialog{
 // dismissible=false: no close button, Escape and outside clicks are ignored
 // (e.g. while the TV is being written); actions are then set via setActions().
 constructor(title,content,{wide=false,dismissible=true}={}){this.title=title;this.content=content;this.wide=wide;this.dismissible=dismissible;this.layer=null;this.resolve=null;this.actions=null;}
 open(){return new Promise(resolve=>{
   this.resolve=resolve;
   const layer=document.createElement('div');layer.className='host-dialog';
   const box=document.createElement('div');box.className='host-dialog-inner modal'+(this.wide?' modal-wide':'');
   box.setAttribute('role','dialog');box.setAttribute('aria-modal','true');box.setAttribute('aria-labelledby','modal-title');box.tabIndex=-1;
   this.heading=document.createElement('h2');this.heading.id='modal-title';this.heading.textContent=this.title;
   const body=document.createElement('div');body.className='modal-body';body.append(this.content);
   this.actions=document.createElement('div');this.actions.className='host-dialog-actions';
   box.append(this.heading,body,this.actions);layer.append(box);
   layer.addEventListener('click',e=>{if(e.target===layer&&this.dismissible)this.close()});
   layer.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();if(this.dismissible)this.close()}});
   document.body.appendChild(layer);this.layer=layer;
   if(this.dismissible)this.setActions([{label:t('common.close'),primary:true,onclick:()=>this.close()}]);else box.focus();
 });}
 setTitle(title){if(this.heading)this.heading.textContent=title;}
 setActions(buttons){
   this.actions.replaceChildren(...buttons.map(b=>{const el=document.createElement('button');el.type='button';el.className='btn'+(b.primary?' primary':'')+(b.danger?' danger':'');el.textContent=b.label;el.onclick=()=>b.onclick(el);return el;}));
   this.actions.querySelector('button')?.focus();
 }
 finish(){this.dismissible=true;this.setActions([{label:t('common.close'),primary:true,onclick:()=>this.close()}]);}
 close(){if(!this.layer)return;this.layer.remove();this.layer=null;this.resolve();}
}
// Non-dismissible modal with a progress bar and a status line. Without max the
// bar is indeterminate (e.g. while backups are created).
class ProgressDialog{
 constructor(title){
   this.root=document.createElement('div');this.root.className='tv-progress';
   this.root.innerHTML='<p class="tv-progress-step"></p><progress class="tv-progress-bar"></progress><p class="tv-progress-text" role="status" aria-live="polite"></p><p class="tv-progress-hint"></p>';
   this.dialog=new ModalDialog(title,this.root,{dismissible:false});
 }
 open(){this.closed=this.dialog.open();return this;}
 update({step='',text='',value=null,max=null,hint=''}){
   const bar=this.root.querySelector('progress');
   if(max){bar.max=max;bar.value=value;}else{bar.removeAttribute('value');bar.removeAttribute('max');}
   this.root.querySelector('.tv-progress-step').textContent=step;
   this.root.querySelector('.tv-progress-text').textContent=text;
   this.root.querySelector('.tv-progress-hint').textContent=hint;
 }
 close(){this.dialog.close();}
}
// Follows a background TV write (/api/tv-write-status) until it has finished,
// including the automatic re-import, and offers cancelling between steps.
class TvWriteProgress{
 constructor(job){this.job=job;this.progress=new ProgressDialog(t('tv.progress.title'));}
 static async resume(){
   let s;try{s=await api('/api/tv-write-status')}catch{return false}
   if(s.state!=='running')return false;
   $('#start').style.display='none';
   await new TvWriteProgress(s.job).run();return true;
 }
 async run(){
   this.progress.open();this.cancelButton();
   let s;
   for(;;){
     try{s=await api('/api/tv-write-status?job='+encodeURIComponent(this.job));}
     catch(e){this.progress.update({step:t('tv.progress.connection_lost'),text:e.message});await TvWriteProgress.sleep(2000);continue;}
     if(s.state!=='running')break;
     this.show(s);await TvWriteProgress.sleep(500);
   }
   this.summary(s);
   await this.progress.closed;
   return s;
 }
 static sleep(ms){return new Promise(r=>setTimeout(r,ms));}
 cancelButton(){
   this.progress.dialog.setActions([{label:t('tv.progress.cancel'),danger:true,onclick:async button=>{
     button.disabled=true;button.textContent=t('tv.progress.cancelling');
     try{await api('/api/tv-write-cancel',{job:this.job})}catch(e){button.disabled=false;button.textContent=t('tv.progress.cancel');note(e.message,true);}
   }}]);
 }
 show(s){
   const hint=s.cancelRequested?t('tv.progress.cancel_pending'):t('tv.progress.hint');
   if(s.phase==='writing')this.progress.update({step:t('tv.progress.step',{step:s.step,total:s.total}),text:describeOperation(s.current),value:s.step-1,max:s.total,hint});
   else if(s.phase==='verifying')this.progress.update({step:t('tv.progress.step',{step:s.total,total:s.total}),text:t('tv.progress.verifying'),value:s.total,max:s.total,hint});
   else if(s.phase==='reimporting')this.progress.update({step:t('tv.progress.reimporting'),text:t('tv.progress.reimport_detail'),hint});
   else this.progress.update({step:t('tv.progress.preparing'),text:t('tv.progress.preparing_detail'),hint});
   if(s.phase==='reimporting'||s.phase==='verifying')this.progress.dialog.setActions([]);
 }
 summary(s){
   const lines=[];
   if(s.state==='done')lines.push(t('tv.progress.done',{count:s.result?.count??s.completed,backup:s.result?.backup??''}));
   else if(s.state==='cancelled')lines.push(t('tv.progress.cancelled',{completed:s.completed,total:s.total}));
   else lines.push(t('tv.progress.failed',{completed:s.completed,total:s.total||'?',error:s.error||t('common.error')}));
   if(s.reimport==='ok')lines.push(t('tv.progress.reimport_ok'));
   else if(s.reimport==='skipped')lines.push(t('tv.progress.reimport_skipped'));
   else if(s.reimport)lines.push(t('tv.progress.reimport_failed',{error:s.reimport}));
   this.progress.dialog.setTitle(t(s.state==='done'?'tv.progress.title_done':s.state==='cancelled'?'tv.progress.title_cancelled':'tv.progress.title_failed'));
   this.progress.update({step:lines[0],text:lines.slice(1).join(' '),value:s.completed,max:s.total||1});
   this.progress.root.classList.toggle('error',s.state!=='done');
   this.progress.dialog.finish();
   note(lines[0],s.state!=='done');
 }
}
// Result of /api/tv-sync-preflight: counts plus the affected channels.
class SyncReport{
 constructor(result){this.result=result;}
 static favoriteList(groups){return groups.length?groups.join(', '):'–';}
 section(title,items,head,cells){
   const open=items.length&&items.length<=200?' open':'';
   const rows=items.map(item=>`<tr data-search="${esc((item.name+' '+(item.number??item.tvNumber)+' '+(item.localNumber??'')).toLowerCase())}">${cells(item).map(c=>`<td>${c}</td>`).join('')}</tr>`).join('');
   return `<details class="report-section"${open}><summary>${esc(title)} (${items.length})</summary>`+
     (items.length?`<table class="report-table"><thead><tr>${head.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`:`<p class="report-empty">${esc(t('report.none'))}</p>`)+'</details>';
 }
 render(){
   const r=this.result,d=r.details||{changed:[],added:[],removed:[]};
   const root=document.createElement('div');root.className='sync-report';
   const total=r.changed+r.added+r.removed;
   const listing=[t('report.col.channel'),t('report.col.number'),t('report.col.favorites')];
   root.innerHTML=`<p class="report-summary">${total?t('report.summary_html',{total:Number(total)}):esc(t('report.in_sync'))}</p>`+
     `<p class="report-meta">${esc(t('report.backup'))} <code>${esc(r.backedUp)}</code><br>${esc(r.warning)}</p>`+
     (total?`<input class="search report-filter" type="search" placeholder="${esc(t('report.filter'))}" aria-label="${esc(t('report.filter_label'))}">`:'')+
     this.section(t('report.changed'),d.changed,[t('report.col.channel'),t('report.col.tv'),t('report.col.local'),t('report.col.difference')],c=>[esc(c.name),esc(c.tvNumber),esc(c.localNumber),c.changes.map(esc).join('<br>')])+
     this.section(t('report.only_local'),d.added,listing,c=>[esc(c.name),esc(c.number),esc(SyncReport.favoriteList(c.favorites))])+
     this.section(t('report.only_tv'),d.removed,listing,c=>[esc(c.name),esc(c.number),esc(SyncReport.favoriteList(c.favorites))]);
   const filter=root.querySelector('.report-filter');
   if(filter)filter.addEventListener('input',()=>{const q=filter.value.toLowerCase().trim();root.querySelectorAll('tbody tr').forEach(tr=>tr.hidden=!!q&&!tr.dataset.search.includes(q));});
   return root;
 }
 show(){return new ModalDialog(t('report.title'),this.render(),{wide:true}).open();}
}
// Device history stays on this browser only. Never persist passwords.
const HOST_KEY='lg-favoriten-editor-tv-hosts';
function knownHosts(){try{const v=JSON.parse(localStorage.getItem(HOST_KEY)||'[]');return Array.isArray(v)?v.filter(s=>typeof s==='string').slice(0,12):[]}catch{return []}}
function rememberHost(host){if(!host)return;try{localStorage.setItem(HOST_KEY,JSON.stringify([host,...knownHosts().filter(h=>h!==host)].slice(0,12)))}catch{}}
// TV login for this page view: host and password live only in this object
// (memory) until the page is reloaded or the user logs out. The server checks
// the connection (/api/tv-login) but stores nothing.
class TvSession{
 constructor(){this.host=null;this.password=null;}
 get active(){return !!(this.host&&this.password);}
 // Credentials for a TV action; asks for a login first if there is none.
 async credentials(){if(!this.active&&!await this.login())return null;return {host:this.host,password:this.password};}
 login(){return new Promise(resolve=>{
   const form=document.createElement('form');form.className='login-form';
   form.innerHTML=`<p class="login-intro">${esc(t('login.intro'))}</p><label for="login-host">${esc(t('tv.dialog.host'))}</label><input class="search" id="login-host" list="login-hosts" required autocomplete="off"><datalist id="login-hosts"></datalist><label for="login-pass">${esc(t('tv.dialog.password'))}</label><input class="search" id="login-pass" type="password" required autocomplete="off"><p class="login-status" role="status" aria-live="polite"></p><button type="submit" hidden></button>`;
   const host=form.querySelector('#login-host'),password=form.querySelector('#login-pass'),status=form.querySelector('.login-status');
   host.value=knownHosts()[0]||'';
   form.querySelector('#login-hosts').replaceChildren(...knownHosts().map(h=>{const o=document.createElement('option');o.value=h;return o}));
   const dialog=new ModalDialog(t('login.title'),form,{dismissible:false});
   dialog.open().then(()=>resolve(this.active));
   const busy=on=>{for(const el of [host,password,...dialog.actions.querySelectorAll('button')])el.disabled=on;};
   form.onsubmit=async e=>{
     e.preventDefault();
     const candidate={host:host.value.trim(),password:password.value};
     status.className='login-status';status.textContent=t('login.checking',{host:candidate.host});busy(true);
     try{await api('/api/tv-login',candidate);this.host=candidate.host;this.password=candidate.password;rememberHost(this.host);this.render();dialog.close();}
     catch(err){status.className='login-status error';status.textContent=err.message;busy(false);password.select();}
   };
   dialog.setActions([{label:t('login.skip'),onclick:()=>dialog.close()},{label:t('login.connect'),primary:true,onclick:()=>form.requestSubmit()}]);
   (host.value?password:host).focus();
 });}
 logout(){this.host=null;this.password=null;this.render();return this.login();}
 render(){
   const area=$('#tvsession');
   if(this.active){area.innerHTML=`<span class="session-chip" title="${esc(t('session.connected_title'))}">${esc(t('session.connected',{host:this.host}))}</span><button class="btn" type="button" id="logout">${esc(t('session.logout'))}</button>`;$('#logout').onclick=()=>this.logout();}
   else{area.innerHTML=`<button class="btn" type="button" id="login">${esc(t('session.login'))}</button>`;$('#login').onclick=()=>this.login();}
 }
}
const session=new TvSession();session.render();
$('#tvimport').onclick=async()=>{const credentials=await session.credentials();if(!credentials)return;const button=$('#tvimport');button.disabled=true;$('#tv-error').textContent=t('tv.import.progress');try{await api('/api/import-tv',credentials);$('#tv-error').textContent='';await refresh();}catch(e){$('#tv-error').textContent=e.message}finally{button.disabled=false;}};
$('#tvcheck').onclick=async()=>{const credentials=await session.credentials();if(!credentials)return;$('#tvcheck').disabled=true;note(t('tv.check.progress'));try{const r=await api('/api/tv-sync-preflight',credentials);note(t('tv.check.done'));new SyncReport(r).show();}catch(e){note(e.message,true)}finally{$('#tvcheck').disabled=false;}};
// Reload from the TV: a short progress dialog while the TV snapshot is read.
async function withTvRead(text,action){const waiting=new ProgressDialog(t('reload.title')).open();waiting.update({step:text,text:t('reload.detail')});try{return await action();}finally{waiting.close();}}
function adoptedNote(result){return result.adoptedChannels?.length?t('reload.adopted',{count:result.adoptedChannels.length}):'';}
$('#allreload').onclick=async()=>{
 const credentials=await session.credentials();if(!credentials)return;
 try{const r=await withTvRead(t('reload.channels_step'),()=>api('/api/tv-reload-channels',credentials));await sync();note(adoptedNote(r)||t('reload.channels_unchanged'));}
 catch(e){note(e.message,true)}
};
$('#favreload').onclick=async()=>{
 const credentials=await session.credentials();if(!credentials)return;
 const group=selected;
 try{
   let r=await withTvRead(t('reload.group_step',{group}),()=>api('/api/tv-reload-group',{...credentials,group}));
   if(r.needsConfirm){
     await sync();
     const list=names=>names.length?names.join(', '):t('common.none');
     if(!confirm(t('reload.group_confirm',{group,local:t('reload.group_version',{name:r.localName,members:list(r.local)}),tv:t('reload.group_version',{name:r.tvName,members:list(r.tv)})}))){note(t('reload.group_kept'));return;}
     r=await withTvRead(t('reload.group_step',{group}),()=>api('/api/tv-reload-group',{...credentials,group,confirm:true}));
   }
   await sync();note([adoptedNote(r),t(r.changed?'reload.group_replaced':'reload.group_unchanged',{group})].filter(Boolean).join(' '));
 }catch(e){note(e.message,true)}
};
$('#helpbtn').onclick=()=>new ModalDialog(t('help.title'),$('#help-text').content.cloneNode(true)).open();
const OPERATION_LABEL={add:t('tv.write.kind.add'),remove:t('tv.write.kind.remove'),number:t('tv.write.kind.number')};
function describeOperation(o){
 if(o.type==='order')return t('tv.write.op_order',{group:o.group,count:o.count});
 if(o.type==='rename_group')return t('tv.write.op_rename',{group:o.group,from:o.from,to:o.to});
 if(o.type==='swap')return t('tv.write.op_swap',{channel:o.channel,from:o.from,other:o.otherChannel,to:o.to});
 if(o.type==='reuse_copy_favorite')return t('tv.write.op_reuse',{channel:o.channel,from:o.from,to:o.to,groups:o.existingGroups?.filter(g=>g!=='A').join(', ')||t('common.none')});
 if(o.type==='copy_favorite')return t('tv.write.op_copy',{channel:o.channel,from:o.from,to:o.to});
 return `${OPERATION_LABEL[o.type]||o.type}: ${o.channel} ${o.group||''} ${o.from||''}→${o.to||''}`;
}
$('#tvwrite').onclick=async()=>{
 const credentials=await session.credentials();if(!credentials)return;
 const {host,password}=credentials;
 const btn=$('#tvwrite');btn.disabled=true;
 const waiting=new ProgressDialog(t('tv.progress.title')).open();
 waiting.update({step:t('tv.progress.previewing'),text:t('tv.progress.previewing_detail')});
 try{
   let preview;try{preview=await api('/api/tv-write-preview',{host,password});}finally{waiting.close();}
   const adopted=preview.adoptedChannels?.length?t('tv.write.adopted',{count:preview.adoptedChannels.length,channels:preview.adoptedChannels.map(n=>n||t('tv.write.unnamed')).join(', ')})+'\n\n':'';
   if(adopted)await refresh();
   if(!preview.total){alert(adopted+t('tv.write.nothing',{backup:preview.backup}));note(t('status.tv_in_sync'));return;}
   const lines=preview.operations.slice(0,35).map(describeOperation);
   const cautions=preview.operations.filter(o=>o.warning).map(o=>`${o.channel}: ${o.warning}`).join('\n');
   const copyNote=preview.operations.some(o=>['copy_favorite','reuse_copy_favorite'].includes(o.type))?'\n'+t('tv.write.copy_note')+'\n':'';
   const msg=adopted+t('tv.write.backup_line',{backup:preview.backup})+'\n\n'+t('tv.write.planned',{total:preview.total})+'\n'+lines.join('\n')+(preview.total>35?'\n…':'')+'\n\n'+(cautions?t('tv.write.cautions')+'\n'+cautions+'\n\n':'')+preview.warning+copyNote+'\n\n'+t('tv.write.question');
   if(!confirm(msg)){note(t('status.tv_write_cancelled'));return;}
   const {job}=await api('/api/tv-write-commit',{host,password,token:preview.token});
   const result=await new TvWriteProgress(job).run();
   if(result.reimport==='ok')await refresh();
 }catch(e){note(e.message,true);alert(t('tv.write.failed',{error:e.message}))}finally{btn.disabled=false;}
};
$('#reload').onclick=()=>{$('#start').style.display='block';$('#workspace').style.display='none';};
$('#import').onclick=async()=>{const file=$('#file').files[0];if(!file){$('#upload-error').textContent=t('import.choose_file');return;}const form=new FormData();form.append('file',file);$('#import').disabled=true;$('#upload-error').textContent=t('import.progress');try{const r=await fetch('/api/import',{method:'POST',body:form});const j=await r.json();if(!r.ok)throw Error(j.error);$('#upload-error').textContent='';await refresh()}catch(e){$('#upload-error').textContent=e.message}finally{$('#import').disabled=false}};
// After a page reload during a transfer, show its progress again before loading data.
// Then ask once for the TV login of this page view.
TvWriteProgress.resume().finally(()=>refresh().catch(e=>{$('#upload-error').textContent=e.message}).finally(()=>session.login()));
