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
   const sample=plan.changes.filter(c=>c.displaced).slice(0,6).map(c=>t('renumber.displaced_line',{name:c.name,old:c.old,new:c.new})).join('\n');
   const merges=plan.mergedFavorites||[];
   const mergePreview=merges.map(x=>t('renumber.merge_line',{name:x.name,original:x.originalNumber,copy:x.copyNumber})).join('\n');
   const message=t('renumber.summary',{count:plan.favorites,group:selected,start})+
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
 constructor(title,content,{wide=false}={}){this.title=title;this.content=content;this.wide=wide;this.layer=null;this.resolve=null;}
 open(){return new Promise(resolve=>{
   this.resolve=resolve;
   const layer=document.createElement('div');layer.className='host-dialog';
   const box=document.createElement('div');box.className='host-dialog-inner modal'+(this.wide?' modal-wide':'');
   box.setAttribute('role','dialog');box.setAttribute('aria-modal','true');box.setAttribute('aria-labelledby','modal-title');
   const heading=document.createElement('h2');heading.id='modal-title';heading.textContent=this.title;
   const body=document.createElement('div');body.className='modal-body';body.append(this.content);
   const actions=document.createElement('div');actions.className='host-dialog-actions';
   const closeButton=document.createElement('button');closeButton.type='button';closeButton.className='btn primary';closeButton.textContent=t('common.close');
   closeButton.onclick=()=>this.close();actions.append(closeButton);
   box.append(heading,body,actions);layer.append(box);
   layer.addEventListener('click',e=>{if(e.target===layer)this.close()});
   layer.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();this.close()}});
   document.body.appendChild(layer);this.layer=layer;closeButton.focus();
 });}
 close(){if(!this.layer)return;this.layer.remove();this.layer=null;this.resolve();}
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
function showHosts(){const list=$('#tvhost-history');list.replaceChildren(...knownHosts().map(h=>{const opt=document.createElement('option');opt.value=h;return opt}))}
function rememberHost(host){if(!host)return;try{localStorage.setItem(HOST_KEY,JSON.stringify([host,...knownHosts().filter(h=>h!==host)].slice(0,12)))}catch{}$('#tvhost').value=host;showHosts()}
function tvCredentials(){return new Promise(resolve=>{const layer=document.createElement('div');layer.className='host-dialog';layer.innerHTML=`<form class="host-dialog-inner"><h2>${esc(t('tv.dialog.title'))}</h2><label for="dialog-tvhost">${esc(t('tv.dialog.host'))}</label><input class="search" id="dialog-tvhost" list="dialog-hosts" required autocomplete="off"><datalist id="dialog-hosts"></datalist><label for="dialog-tvpass">${esc(t('tv.dialog.password'))}</label><input class="search" id="dialog-tvpass" type="password" required autocomplete="off"><div class="host-dialog-actions"><button class="btn" type="button" id="dialog-cancel">${esc(t('common.cancel'))}</button><button class="btn primary" type="submit">${esc(t('common.next'))}</button></div></form>`;document.body.appendChild(layer);
const host=layer.querySelector('#dialog-tvhost');host.value=$('#tvhost').value||knownHosts()[0]||'';layer.querySelector('#dialog-hosts').replaceChildren(...knownHosts().map(s=>{const o=document.createElement('option');o.value=s;return o}));let finished=false;function close(result){if(finished)return;finished=true;layer.remove();resolve(result)}layer.querySelector('#dialog-cancel').onclick=()=>close(null);layer.addEventListener('click',e=>{if(e.target===layer)close(null)});layer.querySelector('form').onsubmit=e=>{e.preventDefault();close({host:host.value.trim(),password:layer.querySelector('#dialog-tvpass').value})};host.focus();});}
showHosts();
$('#tvimport').onclick=async()=>{const button=$('#tvimport');const host=$('#tvhost').value.trim();const password=$('#tvpass').value;if(!host||!password){$('#tv-error').textContent=t('tv.import.missing');return;}button.disabled=true;$('#tv-error').textContent=t('tv.import.progress');try{await api('/api/import-tv',{host,password});rememberHost(host);$('#tvpass').value='';$('#tv-error').textContent='';await refresh();}catch(e){$('#tv-error').textContent=e.message}finally{button.disabled=false;$('#tvpass').value='';}};
$('#tvcheck').onclick=async()=>{const credentials=await tvCredentials();if(!credentials)return;const {host,password}=credentials;$('#tvcheck').disabled=true;note(t('tv.check.progress'));try{const r=await api('/api/tv-sync-preflight',{host,password});rememberHost(host);note(t('tv.check.done'));new SyncReport(r).show();}catch(e){note(e.message,true)}finally{$('#tvcheck').disabled=false;}};
$('#helpbtn').onclick=()=>new ModalDialog(t('help.title'),$('#help-text').content.cloneNode(true)).open();
const OPERATION_LABEL={add:t('tv.write.kind.add'),remove:t('tv.write.kind.remove'),number:t('tv.write.kind.number')};
function describeOperation(o){
 if(o.type==='order')return t('tv.write.op_order',{group:o.group,count:o.count});
 if(o.type==='swap')return t('tv.write.op_swap',{channel:o.channel,from:o.from,other:o.otherChannel,to:o.to});
 if(o.type==='reuse_copy_favorite')return t('tv.write.op_reuse',{channel:o.channel,from:o.from,to:o.to,groups:o.existingGroups?.filter(g=>g!=='A').join(', ')||t('common.none')});
 if(o.type==='copy_favorite')return t('tv.write.op_copy',{channel:o.channel,from:o.from,to:o.to});
 return `${OPERATION_LABEL[o.type]||o.type}: ${o.channel} ${o.group||''} ${o.from||''}→${o.to||''}`;
}
$('#tvwrite').onclick=async()=>{
 const credentials=await tvCredentials();if(!credentials)return;
 const {host,password}=credentials;
 const btn=$('#tvwrite');btn.disabled=true;note(t('tv.write.progress'));
 try{
   const preview=await api('/api/tv-write-preview',{host,password});rememberHost(host);
   if(!preview.total){alert(t('tv.write.nothing',{backup:preview.backup}));note(t('status.tv_in_sync'));return;}
   const lines=preview.operations.slice(0,35).map(describeOperation);
   const cautions=preview.operations.filter(o=>o.warning).map(o=>`${o.channel}: ${o.warning}`).join('\n');
   const copyNote=preview.operations.some(o=>['copy_favorite','reuse_copy_favorite'].includes(o.type))?'\n'+t('tv.write.copy_note')+'\n':'';
   const msg=t('tv.write.backup_line',{backup:preview.backup})+'\n\n'+t('tv.write.planned',{total:preview.total})+'\n'+lines.join('\n')+(preview.total>35?'\n…':'')+'\n\n'+(cautions?t('tv.write.cautions')+'\n'+cautions+'\n\n':'')+preview.warning+copyNote+'\n\n'+t('tv.write.question');
   if(!confirm(msg)){note(t('status.tv_write_cancelled'));return;}
   note(t('tv.write.running'));
   const result=await api('/api/tv-write-commit',{host,password,token:preview.token});
   alert(t('tv.write.done',{count:result.count,backup:result.backup}));note(t('status.tv_write_done'));
 }catch(e){note(e.message,true);alert(t('tv.write.failed',{error:e.message}))}finally{btn.disabled=false;}
};
$('#reload').onclick=()=>{$('#start').style.display='block';$('#workspace').style.display='none';};
$('#import').onclick=async()=>{const file=$('#file').files[0];if(!file){$('#upload-error').textContent=t('import.choose_file');return;}const form=new FormData();form.append('file',file);$('#import').disabled=true;$('#upload-error').textContent=t('import.progress');try{const r=await fetch('/api/import',{method:'POST',body:form});const j=await r.json();if(!r.ok)throw Error(j.error);$('#upload-error').textContent='';await refresh()}catch(e){$('#upload-error').textContent=e.message}finally{$('#import').disabled=false}};
refresh().catch(e=>{$('#upload-error').textContent=e.message});
