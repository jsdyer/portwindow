import {dateOnly,selectCalls,bufferWindow,clock,dayStats,calendar,validateFavourites} from './model.mjs';
const $=id=>document.getElementById(id),KEY='coolcode:portwindow:favourites';
let data,current,favourites=new Set(),limit=60,selected=[],loading=false;
function node(tag,value,cls){const n=document.createElement(tag);if(value!==undefined)n.textContent=value;if(cls)n.className=cls;return n;}
function button(label,fn,cls){const b=node('button',label,cls);b.type='button';b.addEventListener('click',fn);return b;}
function say(text){$('status').textContent=text;}
function port(code){return data.ports.find(p=>p.code===code);}
function when(value){return new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});}
function day(value){return new Date(value+'T12:00:00Z').toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});}
function source(c){const a=node('a','Original PDF · page '+c.page+' ↗');a.href=port(c.port).url+'#page='+c.page;a.target='_blank';a.rel='noopener';a.className='small';return a;}
function tab(name){for(const v of ['calls','calendar','changes']){$(v).hidden=v!==name;$('tab-'+v).setAttribute('aria-selected',String(v===name));}}
for(const name of ['calls','calendar','changes'])$('tab-'+name).addEventListener('click',()=>tab(name));
function filters(){const from=$('from').value,to=$('to').value;if((from&&!dateOnly(from))||(to&&!dateOnly(to))||(from&&to&&from>to))throw new Error('Choose an ordered range of real calendar dates.');return {port:$('port').value,query:$('ship').value,from,to,favourites:$('favourites-only').checked?favourites:null};}
function buffers(){const a=$('after').value,b=$('before').value;if(!a||!b)throw new Error('Enter both planning buffers.');return [Number(a),Number(b)];}
function render(){
 if(!data||loading)return;
 try{
  selected=selectCalls(data.calls,filters());const [after,before]=buffers();bufferWindow({arrival:'00:00',departure:'24:00'},after,before);
  $('result-count').textContent=selected.length+' matching schedule entries · '+new Set(selected.map(c=>c.ship)).size+' ships · '+new Set(selected.map(c=>c.date)).size+' dates';
  $('export').disabled=selected.length===0;
  const fragment=document.createDocumentFragment();
  for(const c of selected.slice(0,limit)){
   const article=node('article',undefined,'call-card'),top=node('div',undefined,'call-top');
   const favourite=button(favourites.has(c.id)?'★':'☆',()=>{favourites.has(c.id)?favourites.delete(c.id):favourites.add(c.id);render();say('Favourites changed in this tab. Save to keep them on this device.');},'star');favourite.setAttribute('aria-label','Favourite '+c.ship+' on '+c.date);favourite.setAttribute('aria-pressed',String(favourites.has(c.id)));
   top.append(node('span',day(c.date),'small'),favourite);article.append(top,node('h3',c.ship),node('p',port(c.port).name+' · '+port(c.port).timezone,'small'),node('p',(c.arrival||'Unknown')+' → '+(c.departure||'Unknown'),'times'));
   if(c.departure==='24:00')article.append(node('p','24:00 means midnight at the end of this date.','small'));
   const window=bufferWindow(c,after,before);
   article.append(node('p',window.kind==='unknown'?'Planning window unavailable: one or both times are unknown or do not form a same-day interval.':window.kind==='none'?'No usable time remains with your chosen buffers.':'Your estimate: '+clock(window.start)+'–'+clock(window.end)+' · '+Math.floor(window.minutes/60)+'h '+window.minutes%60+'m','estimate'),source(c));
   fragment.append(article);
  }
  $('call-list').replaceChildren(fragment);$('more').hidden=selected.length<=limit;renderDays();
 }catch(error){selected=[];$('call-list').replaceChildren();$('days').replaceChildren();$('export').disabled=true;say(error.message);}
}
function renderDays(){
 const grouped=new Map();for(const c of selected){if(!grouped.has(c.date))grouped.set(c.date,[]);grouped.get(c.date).push(c);}
 const fragment=document.createDocumentFragment();
 for(const [date,calls] of grouped){const stats=dayStats(calls),article=node('article',undefined,'day-card');article.append(node('h3',day(date)),node('p',stats.count+' entries','day-number'),node('p','Peak timed overlap: '+stats.peak,'small'));
  if(stats.unknown)article.append(node('p',stats.unknown+' incomplete intervals excluded','small'));
  article.append(button('View this day',()=>{$('from').value=date;$('to').value=date;limit=60;render();tab('calls');}));fragment.append(article);
 }$('days').replaceChildren(fragment);if(!grouped.size)$('days').append(node('p','No dates match the current filters.'));
}
function details(){
 $('freshness').textContent=data.season+' season · '+data.calls.length+' entries · checked '+when(data.checked_at);
 $('stale').hidden=Date.now()-Date.parse(data.checked_at)<72*3600000;
 $('stale').textContent=(data===current?'This capture is more than three days old.':'You are viewing a historical capture.')+' Confirm plans in the official source and with your operator.';
 if(data!==current)$('stale').hidden=false;
 const fragment=document.createDocumentFragment();
 for(const p of data.ports){const row=node('div'),link=node('a',p.name+' schedule ↗');link.href=p.url;link.target='_blank';link.rel='noopener';row.append(link,node('span',p.count+' entries · PDF edition '+p.edition,'small'));fragment.append(row);}
 $('source-links').replaceChildren(fragment);
 $('history-note').textContent='Observation began '+when(data.baseline_at)+'. Showing up to '+data.changes.length+' retained differences. Historical captures retain their original coverage. Date or ship-name changes may appear as a removal and an addition.';
 const changes=document.createDocumentFragment();
 for(const change of data.changes){const c=change.after||change.before,article=node('article',undefined,'change-card');article.append(node('h3',c.ship+' · '+c.port+' · '+c.date),node('p',change.kind+' · detected '+when(change.detected_at),'small'));
  for(const [name,v] of [['Before',change.before],['After',change.after]])if(v)article.append(node('p',name+': '+(v.arrival||'Unknown')+'–'+(v.departure||'Unknown')));
  changes.append(article);
 }$('change-list').replaceChildren(changes);if(!data.changes.length)$('change-list').append(node('p','This is the first capture, or no changes have been observed since it.','empty'));
}
function selectCapture(value){
 data=value;const previous=$('port').value;const fragment=document.createDocumentFragment();for(const p of data.ports){const option=node('option',p.name);option.value=p.code;fragment.append(option);}$('port').replaceChildren(fragment);if(data.ports.some(p=>p.code===previous))$('port').value=previous;
 $('port').disabled=false;$('load').disabled=false;details();reset();
}
function reset(){$('ship').value='';$('from').value='';$('to').value='';$('favourites-only').checked=false;limit=60;render();say('Showing all dates in this capture.');}
function checkedCapture(value){if(value.schema!==1||!Array.isArray(value.calls)||!value.calls.length||!Array.isArray(value.ports)||!Array.isArray(value.changes)||!Number.isFinite(Date.parse(value.checked_at)))throw new Error('Invalid schedule capture');return value;}
async function fetchCapture(path){const r=await fetch(path,{cache:'no-cache'});if(!r.ok)throw new Error('HTTP '+r.status);return checkedCapture(await r.json());}
for(const id of ['port','ship','from','to','favourites-only','after','before'])$(id).addEventListener('input',()=>{limit=60;render();});
$('reset').addEventListener('click',reset);$('more').addEventListener('click',()=>{limit+=60;render();});
$('save').addEventListener('click',()=>{try{validateFavourites([...favourites]);localStorage.setItem(KEY,JSON.stringify([...favourites]));say('Saved '+favourites.size+' favourites on this device.');}catch(error){say(error.message);}});
$('load').addEventListener('click',()=>{try{const raw=localStorage.getItem(KEY);if(!raw)throw new Error('No saved favourites on this device.');favourites=validateFavourites(JSON.parse(raw));render();const missing=[...favourites].filter(id=>!data.calls.some(c=>c.id===id)).length;say('Loaded '+favourites.size+' favourites.'+(missing?' '+missing+' are absent from this capture and retained for historical comparisons.':''));}catch(error){say(error.message);}});
$('forget').addEventListener('click',()=>{try{localStorage.removeItem(KEY);say('Deleted the saved copy. This tab still has your current favourites.');}catch(error){say(error.message);}});
$('export').addEventListener('click',()=>{try{const result=calendar(selected,data.ports,data.checked_at);if(!result.count)throw new Error('No complete timed intervals can be exported. Unknown times remain unknown.');const url=URL.createObjectURL(new Blob([result.text],{type:'text/calendar;charset=utf-8'})),a=node('a');a.href=url;a.download='portwindow-'+data.season+'.ics';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);say('Exported '+result.count+' published intervals. '+result.skipped+' incomplete intervals skipped. Your personal buffers are not calendar departure times.');}catch(error){say(error.message);}});
$('capture').addEventListener('change',async()=>{const previous=data;loading=true;$('export').disabled=true;try{const path=$('capture').value;if(path==='current')data=current;else{if(!/^history\/[0-9TZ]+\.json$/.test(path)||!current.history.some(h=>h.path===path))throw new Error('Invalid capture path');data=await fetchCapture('./data/'+path);}loading=false;selectCapture(data);}catch(error){loading=false;data=previous;$('capture').value=previous===current?'current':current.history.find(h=>h.checked_at===previous.checked_at)?.path||'current';render();say('Could not load that historical capture. Your previous view is retained.');}});
async function init(){try{current=await fetchCapture('./data/index.json');data=current;for(const h of current.history){const option=node('option',when(h.checked_at)+' · '+h.season+' · '+h.ports.join(', '));option.value=h.path;$('capture').append(option);}$('capture').disabled=false;selectCapture(data);}catch(error){$('freshness').textContent='Schedule capture unavailable. Open the official CLAA index above.';for(const id of ['export','load','capture'])$(id).disabled=true;}}
init();
