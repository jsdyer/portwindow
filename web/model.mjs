export function dateOnly(value){if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const d=new Date(value+'T12:00:00Z');return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===value;}
export function minutes(value){if(value===null)return null;if(typeof value!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$|^24:00$/.test(value))throw new Error('Invalid schedule time');return Number(value.slice(0,2))*60+Number(value.slice(3));}
export function selectCalls(calls,{port='',season='',query='',from='',to='',favourites=null}={}){const q=query.trim().toUpperCase();return calls.filter(c=>(!port||c.port===port)&&(!season||c.date.slice(0,4)===String(season))&&(!q||c.ship.toUpperCase().includes(q))&&(!from||c.date>=from)&&(!to||c.date<=to)&&(!favourites||favourites.has(c.id))).sort((a,b)=>a.date.localeCompare(b.date)||(a.arrival||'99:99').localeCompare(b.arrival||'99:99')||a.ship.localeCompare(b.ship));}
export function duration(c){const a=minutes(c.arrival),b=minutes(c.departure);return a===null||b===null||b<=a?null:b-a;}
export function bufferWindow(c,after,before){if(!Number.isInteger(after)||!Number.isInteger(before)||after<0||before<0||after>720||before>720)throw new Error('Enter whole-minute buffers from 0 to 720.');const d=duration(c);if(d===null)return {kind:'unknown'};const start=minutes(c.arrival)+after,end=minutes(c.departure)-before;return end<=start?{kind:'none'}:{kind:'window',start,end,minutes:end-start};}
export function clock(m){return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0')+(m===1440?' (next midnight)':'');}
export function dayStats(calls){const events=[];let unknown=0;for(const c of calls){if(duration(c)===null){unknown++;continue;}events.push([minutes(c.arrival),1],[minutes(c.departure),-1]);}events.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);let current=0,peak=0;for(const [,step] of events){current+=step;peak=Math.max(peak,current);}return {count:calls.length,peak,unknown};}
export function validateFavourites(value){if(!Array.isArray(value)||value.length>500||value.some(v=>typeof v!=='string'||!/^[0-9a-f]{20}$/.test(v)))throw new Error('Saved favourites are invalid.');return new Set(value);}
function escapeICS(text){return String(text).replace(/\\/g,'\\\\').replace(/\r?\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,');}
function fold(line){const out=[];let current='',bytes=0;for(const c of line){const size=new TextEncoder().encode(c).length;if(bytes+size>75){out.push(current);current=' ';bytes=1;}current+=c;bytes+=size;}out.push(current);return out.join('\r\n');}
const utc=value=>new Date(value).toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,'');
export function calendar(calls,ports,checked,exported=new Date().toISOString()){
  const lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//CoolCode//Port Window//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH'];let count=0;
  for(const c of calls){const p=ports.find(p=>p.code===c.port);if(!p||duration(c)===null||!Number.isFinite(Date.parse(c.arrival_at))||!Number.isFinite(Date.parse(c.departure_at))||Date.parse(c.departure_at)<=Date.parse(c.arrival_at))continue;
    lines.push('BEGIN:VEVENT','UID:'+c.id+'@portwindow.coolcode.ca','DTSTAMP:'+utc(exported),'DTSTART:'+utc(c.arrival_at),'DTEND:'+utc(c.departure_at),'SUMMARY:'+escapeICS(c.ship+' · '+p.name),'LOCATION:'+escapeICS(p.name),'DESCRIPTION:'+escapeICS('Published schedule only. Verify with your operator. Not an all-aboard time. Schedule year '+(p.season||c.date.slice(0,4))+'. Source last successfully checked '+(p.checked_at||checked)+'.'+(p.status==='retained'?' Latest source refresh failed; these are retained rows.':'')+' Local timezone '+p.timezone+'.'),'URL:'+(c.url||p.url)+(c.page?'#page='+c.page:''),'END:VEVENT');count++;}
  lines.push('END:VCALENDAR');return {text:lines.map(fold).join('\r\n')+'\r\n',count,skipped:calls.length-count};
}

export function upgradeCapture(value){
 if(value?.schema===1){value={...value,schema:2,seasons:[value.season],attempted_at:value.checked_at,ports:value.ports.map(p=>({...p,season:value.season,status:'ok',checked_at:value.checked_at,attempted_at:value.checked_at,availability_checked_at:value.checked_at,message:'',region:'Pacific'}))};}
 if(value?.schema!==2||!Array.isArray(value.calls)||!value.calls.length||!Array.isArray(value.ports)||!Array.isArray(value.changes)||!Array.isArray(value.seasons)||!Number.isFinite(Date.parse(value.checked_at)))throw new Error('Invalid schedule capture');
 return value;
}
export function coverageMessage(port,now=new Date().toISOString()){
 if(!port.count)return {kind:'warning',text:port.status==='pending'?'No published call table is available. '+port.message:'The official source could not be downloaded. No verified schedule rows are available here. '+port.message};
 const end=port.last_date;
 const historical=end?end<now.slice(0,10):port.season<Number(now.slice(0,4));
 const seasonText=historical?'All published '+port.season+' dates have passed. This is a prior sailing season, not an upcoming schedule.':port.season>Number(now.slice(0,4))?'Upcoming '+port.season+' published season.':port.season+' published season.';
 const retained=port.status==='retained'?' Latest refresh failed. Previously verified rows and their original check time are retained. '+port.message:'';
 return {kind:historical||retained?'warning':'coverage-ok',text:seasonText+retained};
}
