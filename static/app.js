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
async function refresh(){const s=await api('/api/status');$('#start').style.display=s.loaded?'none':'block';$('#workspace').style.display=s.loaded?'block':'none';for(const id of ['#exportbtn','#tvimportbtn'])$(id).hidden=!s.loaded;if(s.loaded){groups=s.groups;currentCounts=s.counts;renderGroups(s.counts);await loadChannels();}else if(s.error)$('#tv-error').textContent=s.error;}
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
const RECEPTION_LABEL={satellite:'reception.satellite',cable:'reception.cable',terrestrial:'reception.terrestrial',ip:'reception.ip'};
// Sort order of the list of other channels (dropdown #allSort, remembered per browser).
class ChannelSort{
 static STORAGE='lg-favoriten-editor-sort';
 static RECEPTION=['satellite','cable','terrestrial','ip','other'];
 static ACCESS=['free','encrypted','unknown'];
 static number(c){const n=parseInt(c.number,10);return Number.isFinite(n)?n:null;}
 static byName(a,b,dir=1){return (!a.name)-(!b.name)||String(a.name).localeCompare(String(b.name),undefined,{sensitivity:'base',numeric:true})*dir;} // unnamed always last
 // Channels without a number always last, then by name.
 static byNumber(a,b,dir=1){const x=ChannelSort.number(a),y=ChannelSort.number(b);if(x===null||y===null)return (x===null)-(y===null)||ChannelSort.byName(a,b);return (x-y)*dir||ChannelSort.byName(a,b);}
 static rank(list,value){const i=list.indexOf(value);return i<0?list.length:i;}
 static COMPARE={
   name_asc:(a,b)=>ChannelSort.byName(a,b),
   name_desc:(a,b)=>ChannelSort.byName(a,b,-1),
   number_asc:(a,b)=>ChannelSort.byNumber(a,b),
   number_desc:(a,b)=>ChannelSort.byNumber(a,b,-1),
   reception:(a,b)=>ChannelSort.rank(ChannelSort.RECEPTION,a.reception)-ChannelSort.rank(ChannelSort.RECEPTION,b.reception)||ChannelSort.byNumber(a,b),
   satellite:(a,b)=>(!a.satellite)-(!b.satellite)||String(a.satellite).localeCompare(String(b.satellite),undefined,{numeric:true})||ChannelSort.byName(a,b),
   access:(a,b)=>ChannelSort.rank(ChannelSort.ACCESS,a.access)-ChannelSort.rank(ChannelSort.ACCESS,b.access)||ChannelSort.byName(a,b),
 };
 static apply(list,key){return list.sort(ChannelSort.COMPARE[key]||ChannelSort.COMPARE.name_asc);}
 static restore(select){try{const v=localStorage.getItem(ChannelSort.STORAGE);if(v&&ChannelSort.COMPARE[v])select.value=v;}catch{}}
 static remember(value){try{localStorage.setItem(ChannelSort.STORAGE,value)}catch{}}
}
const KIND_LABEL={radio:'kind.radio',tv:'kind.tv'},ACCESS_LABEL={encrypted:'access.encrypted',free:'access.free'};
function row(c,favorite){const div=document.createElement('div');div.className='item';div.dataset.id=c.id;div.draggable=favorite;div.innerHTML=`${favorite?`<span class="handle" title="${esc(t('row.drag'))}">⠿</span>`:''}${c.numberLocked?`<span class="number number-locked" title="${esc(t('row.ip_number_locked'))}">${esc(c.number)}</span>`:`<button type="button" class="number number-button" title="${esc(t('row.change_number'))}">${esc(c.number)} ✎</button>`}<span class="item-name" title="${esc(c.name)}">${esc(c.name)}<div class="item-meta">${esc([t(RECEPTION_LABEL[c.reception]||'reception.other'),c.satellite].filter(Boolean).join(' '))} · ${esc(t(KIND_LABEL[c.kind]||'kind.unknown'))} · ${esc(t(ACCESS_LABEL[c.access]||'access.unknown'))}</div></span><button class="item-actions ${favorite?'danger':''}" title="${esc(t(favorite?'row.remove_title':'row.add_title'))}">${esc(t(favorite?'row.remove':'row.add'))}</button>`;
if(!c.numberLocked)div.querySelector('.number-button').onclick=async()=>{const newNumber=await askProgrammeNumber(t('number.dialog.title'),c.number,c.name);if(newNumber===null)return;try{const result=await api('/api/channel-number',{id:c.id,number:newNumber});await sync();note(result.numberChange?.swappedWith?t('status.swapped',{name:result.numberChange.swappedWith}):t('status.number_changed'))}catch(e){note(e.message,true)}};
div.querySelector('.item-actions').onclick=async()=>{try{await api('/api/member',{group:selected,id:c.id,enabled:!favorite});await sync();note(t('status.saved'));}catch(e){note(e.message,true)}};
if(favorite){div.addEventListener('dragstart',e=>{dragged=c.id;e.dataTransfer.effectAllowed='move';div.classList.add('dragging')});div.addEventListener('dragend',()=>{dragged=null;document.querySelectorAll('.item').forEach(e=>e.classList.remove('dragging','over'))});div.addEventListener('dragover',e=>{e.preventDefault();div.classList.add('over')});div.addEventListener('dragleave',()=>div.classList.remove('over'));div.addEventListener('drop',async e=>{e.preventDefault();div.classList.remove('over');if(!dragged||dragged===c.id)return;const ids=favorites.map(x=>x.id);ids.splice(ids.indexOf(dragged),1);ids.splice(ids.indexOf(c.id),0,dragged);try{await api('/api/reorder',{group:selected,ids});await sync();note(t('status.order_saved'))}catch(e){note(e.message,true)}})}return div;}
function renderChannels(){const f=$('#favSearch').value.toLowerCase().trim(),q=$('#allSearch').value.toLowerCase().trim();const matches=(c,p)=>Object.entries(FILTERS).every(([id,field])=>{const v=$('#'+p+id).value;return v==='all'||c[field]===v});let fav=favorites.filter(x=>(x.name+' '+x.number).toLowerCase().includes(f)&&matches(x,'fav'));let oth=others.filter(x=>(x.name+' '+x.number).toLowerCase().includes(q)&&matches(x,'all'));ChannelSort.apply(oth,$('#allSort').value);$('#favorites').replaceChildren(...fav.map(c=>row(c,true)));$('#others').replaceChildren(...oth.map(c=>row(c,false)));if(!fav.length)$('#favorites').innerHTML=`<div class="empty">${esc(t('empty.favorites'))}</div>`;if(!oth.length)$('#others').innerHTML=`<div class="empty">${esc(t('empty.others'))}</div>`;$('#favoriteCount').textContent=t('count.favorites',{count:favorites.length});$('#otherCount').textContent=t('count.others',{count:others.length});}
async function sync(){const s=await api('/api/status');groups=s.groups;currentCounts=s.counts;renderGroups(s.counts);await loadChannels();}
ChannelSort.restore($('#allSort'));$('#allSort').addEventListener('change',()=>{ChannelSort.remember($('#allSort').value);renderChannels();});
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
// Result of /api/tv-sync-report: counts plus the affected channels.
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
     `<p class="report-meta">${esc(r.warning)}</p>`+
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
const PORT_KEY='lg-favoriten-editor-tv-ports';
// Same default as tv_address.SshPort.DEFAULT (test_ssh_port_062 checks it).
const DEFAULT_SSH_PORT=22;
function knownPorts(){try{const v=JSON.parse(localStorage.getItem(PORT_KEY)||'{}');return v&&typeof v==='object'&&!Array.isArray(v)?v:{}}catch{return {}}}
function knownPort(host){const port=knownPorts()[host];return Number.isInteger(port)&&port>=1&&port<=65535?port:DEFAULT_SSH_PORT;}
function rememberHost(host,port=DEFAULT_SSH_PORT){if(!host)return;try{localStorage.setItem(HOST_KEY,JSON.stringify([host,...knownHosts().filter(h=>h!==host)].slice(0,12)));const ports=knownPorts();ports[host]=port;localStorage.setItem(PORT_KEY,JSON.stringify(ports))}catch{}}
// TV login for this page view: host and password live only in this object
// (memory) until the page is reloaded or the user logs out. The server checks
// the connection (/api/tv-login) but stores nothing.
class TvSession{
 // Reachability of the TV (SSH port only, never with the password).
 static PING_INTERVAL=30000;
 constructor(){this.host=null;this.password=null;this.port=DEFAULT_SSH_PORT;this.tv=null;this.state='disconnected';this.checked=null;this.timer=null;}
 get active(){return !!(this.host&&this.password);}
 // Credentials for a TV action; asks for a login first if there is none.
 async credentials(){if(!this.active&&!await this.login())return null;return {host:this.host,password:this.password,port:this.port};}
 login(){return new Promise(resolve=>{
   const form=document.createElement('form');form.className='login-form';
   form.innerHTML=`<p class="login-intro">${esc(t('login.intro'))}</p><div class="login-address"><div><label for="login-host">${esc(t('tv.dialog.host'))}</label><input class="search" id="login-host" list="login-hosts" required autocomplete="off"><datalist id="login-hosts"></datalist></div><div><label for="login-port">${esc(t('tv.dialog.port'))}</label><input class="search" id="login-port" type="number" min="1" max="65535" step="1" value="${DEFAULT_SSH_PORT}" required autocomplete="off"></div></div><label for="login-pass">${esc(t('tv.dialog.password'))}</label><input class="search" id="login-pass" type="password" required autocomplete="off"><p class="login-status" role="status" aria-live="polite"></p><button type="submit" hidden></button>`;
   const host=form.querySelector('#login-host'),port=form.querySelector('#login-port'),password=form.querySelector('#login-pass'),status=form.querySelector('.login-status');
   host.value=knownHosts()[0]||'';port.value=knownPort(host.value);
   form.querySelector('#login-hosts').replaceChildren(...knownHosts().map(h=>{const o=document.createElement('option');o.value=h;return o}));
   const dialog=new ModalDialog(t('login.title'),form,{dismissible:false});
   dialog.open().then(()=>resolve(this.active));
   const busy=on=>{for(const el of [host,port,password,...dialog.actions.querySelectorAll('button')])el.disabled=on;};
   // Unknown SSH host key (e.g. first login from the Docker container): show
   // the fingerprint; only an explicit second click trusts exactly that key.
   let trust=null;
   const connectLabel=label=>{dialog.actions.querySelector('.primary').textContent=label;};
   // The stored host key depends on host and port: changing either drops a pending trust.
   const untrust=()=>{if(trust){trust=null;connectLabel(t('login.connect'));status.textContent='';}};
   host.addEventListener('input',untrust);port.addEventListener('input',untrust);
   host.addEventListener('change',()=>{if(knownHosts().includes(host.value.trim()))port.value=knownPort(host.value.trim());});
   form.onsubmit=async e=>{
     e.preventDefault();
     const candidate={host:host.value.trim(),port:Number(port.value),password:password.value};
     if(trust&&trust.host===candidate.host&&trust.port===candidate.port)candidate.trust=trust.fingerprint;
     status.className='login-status';status.textContent=t('login.checking',{host:candidate.host});busy(true);
     try{
       const r=await api('/api/tv-login',candidate);
       if(r.unknownHostKey){trust={host:candidate.host,port:candidate.port,fingerprint:r.unknownHostKey.fingerprint};busy(false);status.className='login-status warn';status.textContent=t('login.host_key_unknown',{host:candidate.host,fingerprint:r.unknownHostKey.fingerprint,type:r.unknownHostKey.keyType});connectLabel(t('login.trust_connect'));return;}
       this.host=candidate.host;this.port=candidate.port;this.password=candidate.password;this.tv=r.tv||null;rememberHost(this.host,this.port);this.watch();dialog.close();
     }
     catch(err){status.className='login-status error';status.textContent=err.message;busy(false);password.select();}
   };
   dialog.setActions([{label:t('login.skip'),onclick:()=>dialog.close()},{label:t('login.connect'),primary:true,onclick:()=>form.requestSubmit()}]);
   (host.value?password:host).focus();
 });}
 logout(){this.host=null;this.password=null;this.tv=null;this.watch();return this.login();}
 watch(){
   clearInterval(this.timer);this.timer=null;this.checked=null;
   this.state=this.active?'checking':'disconnected';this.render();
   if(this.active){this.ping();this.timer=setInterval(()=>this.ping(),TvSession.PING_INTERVAL);}
 }
 async ping(){
   const host=this.host;let online=false;
   try{online=(await api('/api/tv-ping?host='+encodeURIComponent(host)+'&port='+this.port)).online;}catch{}
   if(host!==this.host)return;
   this.state=online?'online':'offline';this.checked=new Date();this.render();
 }
 render(){
   const time=this.checked?this.checked.toLocaleTimeString(document.documentElement.lang):'';
   const address=this.port===DEFAULT_SSH_PORT?this.host:`${this.host}:${this.port}`;
   const title=!this.active?t('session.disconnected'):this.state==='online'?t('session.online',{host:address,time}):this.state==='offline'?t('session.offline',{host:address,time}):t('session.checking');
   const label=this.active?t('session.connected',{host:address}):t('session.disconnected');
   $('#tvsession').innerHTML=`<span class="session-chip" data-state="${this.state}" title="${esc(title)}" role="status"><svg class="icon" aria-hidden="true"><use href="#i-tv"/></svg><span>${esc(label)}</span><span class="status-dot" aria-hidden="true"></span></span>`;
   const button=(id,icon,label)=>`<button class="btn icon-btn" type="button" id="${id}" title="${esc(label)}" aria-label="${esc(label)}"><svg class="icon" aria-hidden="true"><use href="#${icon}"/></svg></button>`;
   const area=$('#tvsessionbtn');
   if(this.active){area.innerHTML=button('logout','i-logout',t('session.logout'));$('#logout').onclick=()=>this.logout();}
   else{area.innerHTML=button('login','i-login',t('session.login'));$('#login').onclick=()=>this.login();}
 }
}
const session=new TvSession();session.render();
$('#tvcheck').onclick=async()=>{const credentials=await session.credentials();if(!credentials)return;$('#tvcheck').disabled=true;note(t('tv.check.progress'));try{const r=await api('/api/tv-sync-report',credentials);note(t('tv.check.done'));new SyncReport(r).show();}catch(e){note(e.message,true)}finally{$('#tvcheck').disabled=false;}};
// Reload from the TV: a short progress dialog while the TV snapshot is read.
async function withTvRead(text,action,detail=t('reload.detail')){const waiting=new ProgressDialog(t('reload.title')).open();waiting.update({step:text,text:detail});try{return await action();}finally{waiting.close();}}
function adoptedNote(result){return [result.adoptedChannels?.length?t('reload.adopted',{count:result.adoptedChannels.length}):'',result.removedChannels?.length?t('reload.removed',{count:result.removedChannels.length,channels:result.removedChannels.join(', ')}):''].filter(Boolean).join(' ');}
$('#allreload').onclick=async()=>{
 const credentials=await session.credentials();if(!credentials)return;
 try{const r=await withTvRead(t('reload.channels_step'),()=>api('/api/tv-reload-channels',credentials));await sync();note(adoptedNote(r)||t('reload.channels_unchanged'));}
 catch(e){note(e.message,true)}
};
// Confirmation before all differing favorite lists are replaced by the TV version.
class GroupsReloadDialog{
 constructor(differences){this.differences=differences;}
 describe(d){
   const onlyLocal=d.local.filter(n=>!d.tv.includes(n)),onlyTv=d.tv.filter(n=>!d.local.includes(n));
   const sameMembers=!onlyLocal.length&&!onlyTv.length,list=names=>names.join(', ');
   return [onlyLocal.length?t('reload.lists_only_local',{count:onlyLocal.length,channels:list(onlyLocal)}):'',
     onlyTv.length?t('reload.lists_only_tv',{count:onlyTv.length,channels:list(onlyTv)}):'',
     sameMembers&&d.local.join('\n')!==d.tv.join('\n')?t('reload.lists_order'):'',
     d.localName!==d.tvName?t('reload.lists_name',{local:d.localName,tv:d.tvName}):''].filter(Boolean);
 }
 open(){return new Promise(resolve=>{
   const body=document.createElement('div');
   body.innerHTML=`<p class="choice-intro">${esc(t('reload.lists_confirm_intro',{count:this.differences.length}))}</p>`+this.differences.map(d=>`<div class="restore-list"><p class="choice-intro"><strong>${esc(d.group)}</strong> · ${esc(d.localName)}</p><ul class="reload-diff">${this.describe(d).map(line=>`<li>${esc(line)}</li>`).join('')}</ul></div>`).join('');
   const dialog=new ModalDialog(t('reload.lists_confirm_title'),body,{wide:true});let answer=false;
   dialog.open().then(()=>resolve(answer));
   dialog.setActions([{label:t('common.cancel'),onclick:()=>dialog.close()},{label:t('reload.lists_replace'),primary:true,onclick:()=>{answer=true;dialog.close();}}]);
 });}
}
$('#listsreload').onclick=async()=>{
 const credentials=await session.credentials();if(!credentials)return;
 try{
   let r=await withTvRead(t('reload.lists_step'),()=>api('/api/tv-reload-groups',credentials));
   if(r.needsConfirm){
     await sync();
     if(!await new GroupsReloadDialog(r.differences).open()){note(t('reload.group_kept'));return;}
     r=await withTvRead(t('reload.lists_step'),()=>api('/api/tv-reload-groups',{...credentials,confirm:true}));
   }
   await sync();note([adoptedNote(r),r.changed.length?t('reload.lists_replaced',{groups:r.changed.join(', ')}):t('reload.lists_unchanged')].filter(Boolean).join(' '));
 }catch(e){note(e.message,true)}
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
 const btn=$('#tvwrite');btn.disabled=true;
 const waiting=new ProgressDialog(t('tv.progress.title')).open();
 waiting.update({step:t('tv.progress.previewing'),text:t('tv.progress.previewing_detail')});
 try{
   let preview;try{preview=await api('/api/tv-write-preview',credentials);}finally{waiting.close();}
   const adopted=(preview.adoptedChannels?.length?t('tv.write.adopted',{count:preview.adoptedChannels.length,channels:preview.adoptedChannels.map(n=>n||t('tv.write.unnamed')).join(', ')})+'\n\n':'')+
     (preview.removedChannels?.length?t('tv.write.removed',{count:preview.removedChannels.length,channels:preview.removedChannels.map(n=>n||t('tv.write.unnamed')).join(', ')})+'\n\n':'');
   if(adopted)await refresh();
   if(!preview.total){alert(adopted+t('tv.write.nothing',{backup:preview.backup}));note(t('status.tv_in_sync'));return;}
   const lines=preview.operations.slice(0,35).map(describeOperation);
   const cautions=preview.operations.filter(o=>o.warning).map(o=>`${o.channel}: ${o.warning}`).join('\n');
   const copyNote=preview.operations.some(o=>['copy_favorite','reuse_copy_favorite'].includes(o.type))?'\n'+t('tv.write.copy_note')+'\n':'';
   const msg=adopted+t('tv.write.backup_line',{backup:preview.backup})+'\n\n'+t('tv.write.planned',{total:preview.total})+'\n'+lines.join('\n')+(preview.total>35?'\n…':'')+'\n\n'+(cautions?t('tv.write.cautions')+'\n'+cautions+'\n\n':'')+preview.warning+copyNote+'\n\n'+t('tv.write.question');
   if(!confirm(msg)){note(t('status.tv_write_cancelled'));return;}
   const {job}=await api('/api/tv-write-commit',{...credentials,token:preview.token});
   const result=await new TvWriteProgress(job).run();
   if(result.reimport==='ok')await refresh();
 }catch(e){note(e.message,true);alert(t('tv.write.failed',{error:e.message}))}finally{btn.disabled=false;}
};
const FORMAT_TEXT={
 sqlite:{label:t('format.sqlite'),desc:t('export.desc_sqlite'),file:t('export.filename.sqlite')},
 csv:{label:t('format.csv'),desc:t('export.desc_csv'),file:t('export.filename.csv')},
 json:{label:t('format.json'),desc:t('export.desc_json'),file:t('export.filename.json')},
 zip:{label:t('format.zip')},
};
// Export: format plus selection of the contents. Dependencies: SQLite is
// always complete; LG raw data includes everything else; list names need a
// list; "only channels of the selected lists" needs a list.
class ExportDialog{
 // preset {lists:['C'],channels:'lists'}: export of one list. Only CSV/JSON,
 // list names and numbers are offered; every other option is not shown (the
 // content is built per dialog, so the general export always shows all).
 constructor({lists=null,channels='all'}={}){this.lists=lists;this.channels=channels;this.single=!!lists;this.format=lists?'json':'sqlite';}
 open(){
   const form=document.createElement('form');form.className='choice-form';
   const kinds=this.single?['json','csv']:['sqlite','csv','json'],hide=this.single?' hidden':'';
   const formats=kinds.map(kind=>`<label class="choice"><input type="radio" name="format" value="${kind}"${kind===this.format?' checked':''}><span><strong>${esc(FORMAT_TEXT[kind].label)}</strong><small>${esc(FORMAT_TEXT[kind].desc)}</small></span></label>`).join('');
   const lists=groups.map(g=>`<label class="check"><input type="checkbox" name="list" value="${esc(g.id)}"${!this.lists||this.lists.includes(g.id)?' checked':''}><span><strong>${esc(g.id)}</strong> · ${esc(g.name)}</span></label>`).join('');
   form.innerHTML=`<p class="choice-intro">${esc(t('export.intro'))}</p>${formats}<fieldset class="restore-apply export-options"><legend>${esc(t('export.options'))}</legend>${this.single?`<p class="choice-hint export-single">${esc(t('export.single_list',{list:ListFillDialog.label(this.lists[0],groups.find(g=>g.id===this.lists[0])?.name)}))}</p>`:''}<p class="choice-hint export-sqlite"${hide}>${esc(t('export.sqlite_complete'))}</p><div class="export-lists export-channels"${hide}><label class="check"><input type="radio" name="channels" value="all"${this.channels==='all'?' checked':''}><span>${esc(t('export.channels_all'))}</span></label><label class="check"><input type="radio" name="channels" value="lists"${this.channels==='lists'?' checked':''}><span>${esc(t('export.channels_lists'))}</span></label></div><div class="export-list-choice"${hide}><p class="choice-hint">${esc(t('export.lists'))}</p><div class="export-lists">${lists}</div></div><label class="check"><input type="checkbox" name="names" checked><span>${esc(t('export.names'))}</span></label><label class="check"><input type="checkbox" name="numbers" checked><span>${esc(t('export.numbers'))}</span></label><label class="check export-raw"${hide}><input type="checkbox" name="raw"><span>${esc(t('export.raw'))}<small>${esc(t('export.raw_hint'))}</small></span></label></fieldset><div class="restore-summary export-summary" role="status" aria-live="polite"></div>`;
   this.form=form;this.dialog=new ModalDialog(this.single?t('export.list_title',{group:this.lists[0]}):t('export.title'),form,{wide:true});const done=this.dialog.open();
   this.dialog.setActions([{label:t('common.cancel'),onclick:()=>this.dialog.close()},{label:t('export.download'),primary:true,onclick:()=>this.download()}]);
   form.onchange=()=>this.update();form.onsubmit=e=>{e.preventDefault();this.download();};this.update();
   return done;
 }
 input(name){return this.form.querySelector(`input[name=${name}]`);}
 get kind(){return this.form.querySelector('input[name=format]:checked').value;}
 selection(){
   const lists=[...this.form.querySelectorAll('input[name=list]:checked')].map(i=>i.value).join('');
   return {lists,channels:this.form.querySelector('input[name=channels]:checked').value,names:this.input('names').checked,numbers:this.input('numbers').checked,raw:this.input('raw').checked};
 }
 update(){
   const sqlite=this.kind==='sqlite',raw=this.input('raw').checked,box=this.form.querySelector('.export-options');
   box.disabled=sqlite;this.form.querySelector('.export-sqlite').hidden=!sqlite;
   // Raw data is a complete backup: everything else is included and locked.
   for(const el of box.querySelectorAll('input:not([name=raw])')){el.disabled=raw;if(raw)el.checked=el.name!=='channels'||el.value==='all';}
   const sel=this.selection(),names=this.input('names');
   if(!raw){names.disabled=!sel.lists;if(!sel.lists)names.checked=false;}
   const ok=sqlite||sel.channels==='all'||!!sel.lists;
   this.dialog.actions.querySelector('.primary').disabled=!ok;
   this.form.querySelector('.export-summary').innerHTML=ok?this.describe(sqlite,this.selection()):`<p>${esc(t('export.nothing_selected'))}</p>`;
 }
 describe(sqlite,sel){
   const line=(label,items)=>`<p><b>${esc(label)}</b> ${esc(items.length?items.join(' · '):t('export.none'))}</p>`;
   const file=sqlite?FORMAT_TEXT.sqlite.file:this.kind==='json'?FORMAT_TEXT.json.file:sel.raw?t('export.filename.zip'):FORMAT_TEXT.csv.file;
   if(sqlite)return line(t('export.contains_label'),[t('export.item.everything')])+line(t('export.missing_label'),[])+`<p class="choice-hint">${esc(t('export.file',{file}))}</p>`;
   if(this.single){
     const contains=[t('export.item.lists',{lists:this.lists.join(', ')}),t('export.item.basics')],missing=[];
     (sel.numbers?contains:missing).push(t('export.item.numbers'));(sel.names?contains:missing).push(t('export.item.names'));
     return line(t('export.contains_label'),contains)+line(t('export.missing_label'),missing)+`<p class="choice-hint">${esc(t('export.file',{file}))}</p>`;
   }
   const all=groups.map(g=>g.id),chosen=sel.lists.split(''),others=all.filter(g=>!chosen.includes(g));
   const contains=[t(sel.channels==='all'?'export.item.channels_all':'export.item.channels_lists'),t('export.item.basics')];
   const missing=[];
   (sel.numbers?contains:missing).push(t('export.item.numbers'));
   if(chosen.length)contains.push(t('export.item.lists',{lists:chosen.join(', ')}));
   if(others.length)missing.push(t('export.item.lists',{lists:others.join(', ')}));
   if(chosen.length)(sel.names?contains:missing).push(t('export.item.names'));else missing.push(t('export.item.names'));
   if(sel.channels==='lists')missing.push(t('export.item.other_channels'));
   if(sel.raw)contains.push(t(this.kind==='json'?'export.item.raw_json':'export.item.raw_csv'));else missing.push(t('export.item.raw_missing'));
   return line(t('export.contains_label'),contains)+line(t('export.missing_label'),missing)+`<p class="choice-hint">${esc(t('export.file',{file}))}</p>`;
 }
 download(){
   const sel=this.selection(),query=this.kind==='sqlite'?'':'?'+new URLSearchParams({lists:sel.lists,channels:sel.channels,names:sel.names?'1':'0',numbers:sel.numbers?'1':'0',raw:sel.raw?'1':'0'});
   ExportDialog.download(this.kind,query);this.dialog.close();
 }
 static download(kind,query=''){const a=document.createElement('a');a.href='/download/'+encodeURIComponent(kind)+query;a.download='';document.body.append(a);a.click();a.remove();}
}
// Step 1 of a file import: choose/drop a file, the server detects its format.
class ImportDialog{
 // target: import one list of the file into this list (ListImportDialog).
 constructor({target=null}={}){this.target=target;}
 open(){
   const form=document.createElement('form');form.className='choice-form';
   form.innerHTML=`<p class="choice-intro">${esc(t('import.intro'))}</p><label class="dropzone"><input type="file" id="import-file" accept=".sqlite,.db,.sql,.csv,.json,.zip,application/vnd.sqlite3,text/csv,application/json,application/zip"><span class="dropzone-text">${esc(t('import.drop'))}</span><span class="dropzone-file"></span></label><p class="choice-hint">${esc(t('import.formats',{formats:Object.values(FORMAT_TEXT).map(f=>f.label).join(', ')}))}</p><p class="login-status" role="status" aria-live="polite"></p>`;
   const input=form.querySelector('input'),zone=form.querySelector('.dropzone'),status=form.querySelector('.login-status');
   const show=()=>{form.querySelector('.dropzone-file').textContent=input.files[0]?.name||'';status.textContent='';};
   input.onchange=show;
   zone.ondragover=e=>{e.preventDefault();zone.classList.add('over')};zone.ondragleave=()=>zone.classList.remove('over');
   zone.ondrop=e=>{e.preventDefault();zone.classList.remove('over');if(e.dataTransfer.files.length){input.files=e.dataTransfer.files;show();}};
   const dialog=new ModalDialog(this.target?t('listfill.import_title',{group:this.target}):t('import.title'),form);const done=dialog.open();
   const upload=async button=>{
     const file=input.files[0];if(!file){status.className='login-status error';status.textContent=t('import.choose_file');return;}
     const data=new FormData();data.append('file',file);button.disabled=true;status.className='login-status';status.textContent=t('import.progress');
     try{const r=await fetch('/api/import',{method:'POST',body:data});const j=await r.json();if(!r.ok)throw Error(j.error||t('common.error'));dialog.close();if(this.target)await new ListImportDialog(j,this.target).open();else await new RestoreDialog(j).open();}
     catch(e){status.className='login-status error';status.textContent=e.message;button.disabled=false;}
   };
   form.onsubmit=e=>{e.preventDefault();upload(dialog.actions.querySelector('.primary'));};
   dialog.setActions([{label:t('common.cancel'),onclick:()=>dialog.close()},{label:t('import.upload'),primary:true,onclick:upload}]);
   return done;
 }
}
// Step 2: choose what to restore. Dependencies: numbers only for channels of
// the chosen lists (so they need a list); "replace" (SQLite) excludes the rest.
class RestoreDialog{
 constructor(analysis){this.a=analysis;this.plan=null;this.seq=0;}
 open(){
   const a=this.a,form=document.createElement('form');form.className='choice-form restore-form';
   const lists=(a.lists||[]).map(l=>`<div class="restore-list"><label class="check"><input type="checkbox" name="list" value="${l.id}"${l.differs&&l.count?' checked':''}><span><strong>${esc(l.id)}</strong> · ${esc(t('restore.list_count',{count:l.count}))}${l.differs?'':` <em>${esc(t('restore.list_same'))}</em>`}</span></label>${l.skipped.length?`<p class="choice-hint warn">${esc(t('restore.skipped',{count:l.skipped.length,channels:l.skipped.join(', ')}))}</p>`:''}${l.name?`<label class="check sub"><input type="checkbox" name="name" value="${l.id}"><span>${esc(t('restore.name',{name:l.name,current:l.currentName||''}))}</span></label>`:''}</div>`).join('');
   form.innerHTML=`<p class="choice-intro">${esc(t('restore.detected',{format:FORMAT_TEXT[a.format]?.label||a.format}))}</p>`
     +(a.canReplace?`<label class="choice"><input type="radio" name="mode" value="apply"${a.canApply?' checked':' disabled'}><span><strong>${esc(t('restore.mode_apply'))}</strong><small>${esc(t('restore.mode_apply_hint'))}</small></span></label><label class="choice"><input type="radio" name="mode" value="replace"${a.canApply?'':' checked'}><span><strong>${esc(t('restore.mode_replace'))}</strong><small>${esc(t('restore.mode_replace_hint'))}</small></span></label>`:'')
     +(a.canApply?`<fieldset class="restore-apply"><legend>${esc(t('restore.lists'))}</legend>${lists}<label class="check numbers"><input type="checkbox" name="numbers"${a.numbers?'':' disabled'}><span>${esc(t(a.numbers?'restore.numbers':'restore.numbers_same'))}<small>${esc(t('restore.numbers_hint'))}</small></span></label></fieldset><div class="restore-summary" role="status" aria-live="polite"></div>`:'');
   this.form=form;this.dialog=new ModalDialog(t('restore.title'),form,{wide:true});const done=this.dialog.open();
   this.dialog.setActions([{label:t('common.cancel'),onclick:()=>this.dialog.close()},{label:t('restore.apply'),primary:true,onclick:b=>this.apply(b)}]);
   form.onchange=()=>this.update();form.onsubmit=e=>e.preventDefault();this.update();
   return done;
 }
 get replace(){return this.form.querySelector('input[name=mode]:checked')?.value==='replace';}
 selection(){const values=name=>[...this.form.querySelectorAll(`input[name=${name}]:checked`)].map(i=>i.value);return {lists:values('list'),names:values('name'),numbers:!!this.form.querySelector('input[name=numbers]:checked')};}
 async update(){
   const box=this.form.querySelector('.restore-apply'),summary=this.form.querySelector('.restore-summary'),apply=this.dialog.actions.querySelector('.primary');
   if(box)box.disabled=this.replace;
   const numbers=this.form.querySelector('input[name=numbers]');
   if(numbers&&this.a.numbers){const none=!this.selection().lists.length;numbers.disabled=none;if(none)numbers.checked=false;}
   // Every change invalidates a preview request still in flight.
   this.plan=null;const seq=++this.seq;
   if(this.replace||!summary){apply.disabled=false;if(summary)summary.textContent=t('restore.replace_summary');return;}
   const sel=this.selection();
   if(!sel.lists.length&&!sel.names.length){apply.disabled=true;summary.textContent=t('restore.nothing');return;}
   apply.disabled=true;summary.textContent=t('restore.calculating');
   try{const plan=await api('/api/import-plan',{token:this.a.token,...sel});if(seq!==this.seq)return;this.plan=plan;summary.innerHTML=this.describe(plan);apply.disabled=false;}
   catch(e){if(seq===this.seq)summary.textContent=e.message;}
 }
 describe(plan){
   const n=plan.numbers,lines=[t('restore.summary',{lists:Object.keys(plan.lists).join(', ')||t('common.none'),names:Object.keys(plan.names).join(', ')||t('common.none'),numbers:n.changes.length})];
   if(n.kept.length)lines.push(t('restore.kept',{channels:n.kept.join(', ')}));
   if(n.locked.length)lines.push(t('restore.ip_locked',{channels:n.locked.join(', ')}));
   if(n.conflicts.length)lines.push(t('restore.conflicts',{channels:n.conflicts.join(', ')}));
   if(n.displacedFavorites.length)lines.push(t('restore.displaced',{channels:n.displacedFavorites.map(d=>t('renumber.other_lists_line',{name:d.name,groups:d.groups.join(', '),old:d.old,new:d.new}).trim()).join('; ')}));
   const details=n.changes.length?`<details><summary>${esc(t('restore.number_details'))}</summary><ul>${n.changes.map(c=>`<li>${esc(c.name)}: ${esc(c.old)} → ${esc(c.new)}</li>`).join('')}</ul></details>`:'';
   return lines.map(l=>`<p>${esc(l)}</p>`).join('')+details+`<p class="choice-hint">${esc(t('restore.tv_hint'))}</p>`;
 }
 async apply(button){
   if(!this.replace&&!this.plan)return;
   button.disabled=true;
   try{
     const body=this.replace?{token:this.a.token,mode:'replace'}:{token:this.a.token,...this.selection(),confirmedChanges:this.plan.numbers.changes};
     const r=await api('/api/import-apply',body);this.dialog.close();await refresh();
     note(r.mode==='replace'?t('restore.done_replace'):t('restore.done_apply',{lists:Object.keys(r.lists).join(', ')||t('common.none'),names:r.names.join(', ')||t('common.none'),numbers:r.numbers}));
   }catch(e){const summary=this.form.querySelector('.restore-summary');if(summary)summary.textContent=e.message;else alert(e.message);button.disabled=false;}
 }
}
// Copy/paste of favorite lists. The clipboard is a snapshot of the list at
// copy time (IDs in list order), kept in memory for this page view.
class ListClipboard{
 static entry=null;
 static copy(){
   const g=groups.find(x=>x.id===selected);
   ListClipboard.entry={source:selected,name:g?.name||'',ids:favorites.map(c=>c.id)};
   ListClipboard.render();note(t('lists.copied',{group:selected,count:favorites.length}));
 }
 static render(){const b=$('#listpaste');b.disabled=!ListClipboard.entry;b.title=t(ListClipboard.entry?'lists.paste_title':'lists.paste_empty_title');}
}
// Paste or import into the selected list: replace it or append the channels
// it does not hold yet. Subclasses provide the source (sourceHtml,
// updateSource) and the request (send).
class ListFillDialog{
 static MODES={replace:['listfill.mode_replace','listfill.mode_replace_hint'],append:['listfill.mode_append','listfill.mode_append_hint']};
 constructor(target){this.target=target;this.name=null;}
 static label(id,name){return name?`${id} · ${name}`:id;}
 open(title,applyLabel){
   const g=groups.find(x=>x.id===this.target),form=document.createElement('form');form.className='choice-form';
   form.innerHTML=`<div class="list-fill-source">${this.sourceHtml()}</div><p class="choice-hint">${esc(t('listfill.target',{list:ListFillDialog.label(this.target,g?.name),count:currentCounts[this.target]??0}))}</p>`
     +Object.entries(ListFillDialog.MODES).map(([mode,[label,hint]],i)=>`<label class="choice"><input type="radio" name="mode" value="${mode}"${i?'':' checked'}><span><strong>${esc(t(label,{group:this.target}))}</strong><small>${esc(t(hint,{group:this.target}))}</small></span></label>`).join('')
     +`<label class="check list-fill-name" hidden><input type="checkbox" name="name"><span></span></label><p class="choice-hint">${esc(t('listfill.hint'))}</p><p class="login-status" role="status" aria-live="polite"></p>`;
   this.form=form;this.status=form.querySelector('.login-status');
   this.dialog=new ModalDialog(title,form,{wide:true});const done=this.dialog.open();
   this.dialog.setActions([{label:t('common.cancel'),onclick:()=>this.dialog.close()},{label:applyLabel,primary:true,onclick:b=>this.apply(b)}]);
   form.onsubmit=e=>{e.preventDefault();this.apply(this.dialog.actions.querySelector('.primary'));};
   form.onchange=e=>{if(e.target.name==='source')this.updateSource();};
   this.updateSource();
   return done;
 }
 // The source list name is offered only if it differs from the target's name.
 offerName(name){
   const current=groups.find(x=>x.id===this.target)?.name||'',box=this.form.querySelector('.list-fill-name'),offer=!!name&&name!==current;
   box.hidden=!offer;if(!offer)box.querySelector('input').checked=false;
   box.querySelector('span').textContent=offer?t('listfill.name',{name,current}):'';this.name=offer?name:null;
 }
 get mode(){return this.form.querySelector('input[name=mode]:checked').value;}
 get takeName(){return !!this.name&&this.form.querySelector('input[name=name]').checked;}
 async apply(button){
   button.disabled=true;this.status.className='login-status';this.status.textContent='';
   try{const r=await this.send();this.dialog.close();await sync();note(ListFillDialog.done(r));}
   catch(e){this.status.className='login-status error';this.status.textContent=e.message;button.disabled=false;}
 }
 static done(r){return [t('listfill.done',{group:r.group,count:r.count,added:r.added,removed:r.removed,present:r.present}),r.skipped?t('listfill.skipped',{count:r.skipped}):''].filter(Boolean).join(' ');}
}
class ListPasteDialog extends ListFillDialog{
 open(){const c=ListClipboard.entry;return super.open(t('listfill.paste_title',{source:c.source,group:this.target}),t('listfill.apply_paste'));}
 sourceHtml(){const c=ListClipboard.entry;return `<p class="choice-intro">${esc(t('listfill.source_clipboard',{list:ListFillDialog.label(c.source,c.name),count:c.ids.length}))}</p>`;}
 updateSource(){const c=ListClipboard.entry;this.offerName(c.name===t('group.default_name',{group:c.source})?null:c.name);}
 send(){const c=ListClipboard.entry;return api('/api/list-paste',{group:this.target,ids:c.ids,mode:this.mode,...(this.takeName?{name:this.name}:{})});}
}
// One list of an uploaded file (any of its lists) into the selected list.
class ListImportDialog extends ListFillDialog{
 constructor(analysis,target){super(target);this.a=analysis;this.lists=analysis.lists||[];}
 open(){
   if(!this.lists.length){note(t('listfill.no_lists'),true);return Promise.resolve();}
   return super.open(t('listfill.import_title',{group:this.target}),t('listfill.apply_import'));
 }
 sourceHtml(){
   const chosen=this.lists.find(l=>l.id===this.target&&l.count)||this.lists.find(l=>l.count)||this.lists[0];
   return `<p class="choice-intro">${esc(t('restore.detected',{format:FORMAT_TEXT[this.a.format]?.label||this.a.format}))}</p><label class="choice-hint" for="list-fill-source">${esc(t('listfill.source_file'))}</label><select class="search" id="list-fill-source" name="source">${this.lists.map(l=>`<option value="${esc(l.id)}"${l===chosen?' selected':''}>${esc(t('listfill.source_option',{list:ListFillDialog.label(l.id,l.listName),count:l.count}))}</option>`).join('')}</select><p class="choice-hint warn list-fill-skipped" hidden></p>`;
 }
 get source(){return this.lists.find(l=>l.id===this.form.querySelector('select[name=source]').value);}
 updateSource(){
   const l=this.source,skipped=this.form.querySelector('.list-fill-skipped');
   skipped.hidden=!l.skipped.length;skipped.textContent=l.skipped.length?t('restore.skipped',{count:l.skipped.length,channels:l.skipped.join(', ')}):'';
   this.offerName(l.listName===t('group.default_name',{group:l.id})?null:l.listName);
 }
 send(){return api('/api/list-import',{token:this.a.token,source:this.source.id,group:this.target,mode:this.mode,name:this.takeName});}
}
$('#listcopy').onclick=()=>ListClipboard.copy();
$('#listpaste').onclick=()=>{if(ListClipboard.entry)new ListPasteDialog(selected).open();};
$('#listexport').onclick=()=>new ExportDialog({lists:[selected],channels:'lists'}).open();
$('#listimport').onclick=()=>new ImportDialog({target:selected}).open();
ListClipboard.render();
$('#exportbtn').onclick=()=>new ExportDialog().open();
$('#importbtn').onclick=()=>new ImportDialog().open();
// Import from the TV replaces the working copy (previous one: data/previous.sqlite).
class TvImport{
 static async run(){
   const credentials=await session.credentials();if(!credentials)return false;
   await withTvRead(t('tv.import.progress'),()=>api('/api/import-tv',credentials),t('tv.import.detail'));
   await refresh();return true;
 }
}
class TvImportDialog{
 open(){
   const text=document.createElement('p');text.className='choice-intro';text.textContent=t('tv.import.confirm');
   const dialog=new ModalDialog(t('tv.import.title'),text);const done=dialog.open();
   dialog.setActions([{label:t('common.cancel'),onclick:()=>dialog.close()},{label:t('toolbar.tv_import'),primary:true,onclick:async()=>{dialog.close();try{if(await TvImport.run())note(t('tv.import.done'));}catch(e){note(e.message,true)}}}]);
   return done;
 }
}
$('#tvimportbtn').onclick=()=>new TvImportDialog().open();
// After the startup login: load the current TV data or keep the local working copy.
class StartupChoice{
 async open(){
   let status;try{status=await api('/api/status');}catch{return;}
   const text=document.createElement('div');
   const when=status.modified?new Date(status.modified*1000).toLocaleString(document.documentElement.lang):'';
   text.innerHTML=status.loaded?`<p class="choice-intro">${esc(t('startup.intro'))}</p><p class="choice-hint">${esc(t('startup.local',{date:when}))}</p>`:`<p class="choice-intro">${esc(t('startup.empty'))}</p>`;
   const dialog=new ModalDialog(t('startup.title'),text);const done=dialog.open();
   const load=async()=>{dialog.close();try{if(await TvImport.run())note(t('tv.import.done'));}catch(e){note(e.message,true);$('#tv-error').textContent=e.message;}};
   dialog.setActions([{label:status.loaded?t('startup.keep'):t('startup.later'),onclick:()=>dialog.close()},{label:t('startup.load'),primary:true,onclick:load}]);
   return done;
 }
}
// Settings are stored server-side in data/settings.json (valid for every browser).
class SettingsDialog{
 async open(){
   let current;try{current=await api('/api/settings');}catch(e){note(e.message,true);return;}
   const [low,high]=current.range,perTv=current.backups.perTv||[];
   const form=document.createElement('form');form.className='login-form settings-form';
   form.innerHTML=`<label for="settings-keep">${esc(t('settings.backups_keep'))}</label><input class="search" id="settings-keep" name="tvBackupsKeep" type="number" min="${low}" max="${high}" step="1" required value="${Number(current.settings.tvBackupsKeep)}"><p class="choice-hint">${esc(t('settings.backups_hint',{count:current.backups.count,size:(current.backups.bytes/1048576).toFixed(1)}))}</p><p class="login-status" role="status" aria-live="polite"></p><button type="submit" hidden></button>`;
   const input=form.querySelector('input'),status=form.querySelector('.login-status');
   // The limit applies per TV: count what saving would delete in every TV folder.
   const preview=()=>{const keep=Number(input.value),drop=Number.isInteger(keep)&&keep>=low?perTv.reduce((sum,n)=>sum+Math.max(0,n-keep),0):0;status.className='login-status'+(drop?' warn':'');status.textContent=drop?t('settings.will_delete',{count:drop}):'';};
   input.oninput=preview;preview();
   const dialog=new ModalDialog(t('settings.title'),form);const done=dialog.open();
   form.onsubmit=async e=>{
     e.preventDefault();
     try{const r=await api('/api/settings',{tvBackupsKeep:Number(input.value)});dialog.close();note(t('settings.saved',{count:r.deleted}));}
     catch(err){status.className='login-status error';status.textContent=err.message;}
   };
   dialog.setActions([{label:t('common.cancel'),onclick:()=>dialog.close()},{label:t('settings.save'),primary:true,onclick:()=>form.requestSubmit()}]);
   input.focus();
   return done;
 }
}
$('#settingsbtn').onclick=()=>new SettingsDialog().open();
// Backup history: stored TV backups of one TV (one folder per TV), newest
// first; the chosen backup goes into the usual restore dialog.
class BackupHistoryDialog{
 static label(tv){
   const name=tv.id==='unassigned'?t('backups.unassigned'):tv.model&&tv.serial?`${tv.model} · ${tv.serial}`:`${tv.host||tv.id}${tv.port?':'+tv.port:''}`;
   return session.tv&&session.tv.id===tv.id?t('backups.current',{name}):name;
 }
 async open(){
   let tvs;try{tvs=(await api('/api/tv-backups')).tvs;}catch(e){note(e.message,true);return;}
   const form=document.createElement('form');form.className='login-form backups-form';
   const current=tvs.find(tv=>session.tv&&tv.id===session.tv.id)||tvs.find(tv=>tv.count)||tvs[0];
   form.innerHTML=`<label for="backups-tv">${esc(t('backups.tv'))}</label><select class="search" id="backups-tv">${tvs.map(tv=>`<option value="${esc(tv.id)}"${tv===current?' selected':''}>${esc(BackupHistoryDialog.label(tv))} (${Number(tv.count)})</option>`).join('')}</select><div class="backups-list" role="radiogroup"></div><p class="choice-hint">${esc(t('backups.hint'))}</p><p class="login-status" role="status" aria-live="polite"></p>`;
   this.form=form;this.select=form.querySelector('#backups-tv');this.status=form.querySelector('.login-status');
   this.dialog=new ModalDialog(t('backups.title'),form,{wide:true});const done=this.dialog.open();
   this.dialog.setActions([{label:t('common.cancel'),onclick:()=>this.dialog.close()},{label:t('backups.restore'),primary:true,onclick:()=>this.restore()}]);
   this.select.onchange=()=>this.list();form.onsubmit=e=>{e.preventDefault();this.restore();};
   await this.list();
   return done;
 }
 async list(){
   const box=this.form.querySelector('.backups-list'),button=this.dialog.actions.querySelector('.primary');
   const tv=this.select.value;let backups=[];
   if(tv){try{backups=(await api('/api/tv-backups?tv='+encodeURIComponent(tv))).backups;}catch(e){this.status.className='login-status error';this.status.textContent=e.message;}}
   if(tv!==this.select.value)return;
   const time=iso=>new Date(iso).toLocaleString(document.documentElement.lang,{dateStyle:'medium',timeStyle:'short'});
   box.innerHTML=backups.length?backups.map((b,i)=>`<label class="check backup-item"><input type="radio" name="backup" value="${esc(b.file)}"${i?'':' checked'}><span>${esc(time(b.time))}<small>${esc(t('backups.item',{channels:b.channels??'?',ip:b.ipChannels??0,size:(b.bytes/1048576).toFixed(1)}))}</small></span></label>`).join(''):`<p class="report-empty">${esc(t('backups.empty'))}</p>`;
   button.disabled=!backups.length;
 }
 async restore(){
   const chosen=this.form.querySelector('input[name=backup]:checked');if(!chosen)return;
   const button=this.dialog.actions.querySelector('.primary');button.disabled=true;
   try{const analysis=await api('/api/tv-backups/restore',{tv:this.select.value,file:chosen.value});this.dialog.close();await new RestoreDialog(analysis).open();}
   catch(e){this.status.className='login-status error';this.status.textContent=e.message;button.disabled=false;}
 }
}
$('#backupsbtn').onclick=()=>new BackupHistoryDialog().open();
$('#tvimport').onclick=async()=>{const button=$('#tvimport');button.disabled=true;$('#tv-error').textContent='';try{await TvImport.run();}catch(e){$('#tv-error').textContent=e.message}finally{button.disabled=false;}};
// After a page reload during a transfer, show its progress again before loading data.
// Then ask once for the TV login of this page view.
// After a page load: show a running transfer again, load the data, ask once
// for the TV login of this page view and then whether to load the TV state.
TvWriteProgress.resume().finally(()=>refresh().catch(e=>{$('#tv-error').textContent=e.message}).finally(()=>session.login().then(ok=>{if(ok)new StartupChoice().open();})));
