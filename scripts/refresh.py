#!/usr/bin/env python3
"""Refresh each official port independently; preserve source years and prior good data."""
from datetime import date, datetime, timezone, timedelta
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from copy import deepcopy
from maritime import PendingSchedule, discover_pdf, parse_marine_pdf, parse_port_html
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
AGENT='PortWindow/1.0 (+https://coolcode.ca/portwindow/)'
DAY=re.compile(r'^(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+([A-Za-z]+)\s+(\d{1,2})$')
MONTHS={name:i+1 for i,name in enumerate('January February March April May June July August September October November December'.split())}
CLOCK=re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d|24:00')
EDITION=re.compile(r'(\d{2}:\d{2})\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Za-z]+)\s+(\d{2}),\s+(\d{4})')

class Links(HTMLParser):
    def __init__(self): super().__init__();self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            url=dict(attrs).get('href','')
            if url not in self.urls:self.urls.append(url)

def read_url(url,maximum=12_000_000):
    with urlopen(Request(url,headers={'User-Agent':AGENT,'Accept':'application/pdf,text/html,text/plain;q=0.9'}),timeout=45) as response:
        raw=response.read(maximum+1)
    if len(raw)>maximum:raise ValueError('Source exceeded the size limit')
    return raw

def source_url(html,port,season):
    parser=Links();parser.feed(html)
    matches=[url for url in parser.urls if url.startswith('https://claalaska.com/wp-content/uploads/')
             and re.search('/'+re.escape(port)+r'-[^/]+-'+str(season)+r'\.pdf$',url)]
    if len(matches)!=1:raise ValueError('Expected exactly one current PDF for '+port)
    return matches[0]

def parse_pdf(raw,port,season):
    import fitz
    if not raw.startswith(b'%PDF-'):raise ValueError('Source is not a PDF')
    with fitz.open(stream=raw,filetype='pdf') as document:
        if not 1<=len(document)<=100:raise ValueError('Unexpected PDF page count')
        cover=document[0].get_text()
        if 'Calendar for '+str(season) not in cover or 'FOR PORT(S) = '+port not in cover:
            raise ValueError('PDF season or port does not match its link')
        editions=EDITION.findall(cover)
        if len(editions)!=1:raise ValueError('Missing PDF edition')
        tm,month,day,year=editions[0]
        edition=date(int(year),MONTHS[month],int(day)).isoformat()+' '+tm+' (source-local)'
        calls=[]
        for page_index,page in enumerate(document):
            blocks=page.get_text('dict')['blocks'];headers=[]
            for block in blocks:
                for line in block.get('lines',[]):
                    value=''.join(s['text'] for s in line['spans']).strip();match=DAY.fullmatch(value)
                    if match:
                        weekday,month,day=match.groups();d=date(season,MONTHS[month],int(day))
                        if d.strftime('%A')!=weekday:raise ValueError('Calendar weekday does not match season')
                        headers.append((line['bbox'][0],line['bbox'][1],d.isoformat()))
            words=page.get_text('words')
            count_before=len(calls)
            for block in blocks:
                lines=[''.join(s['text'] for s in line['spans']).strip() for line in block.get('lines',[])]
                ships=[value[len(port)+1:].strip() for value in lines if value.startswith(port+' ')]
                ships += [lines[i+1] for i,value in enumerate(lines[:-1]) if value==port]
                if not ships:continue
                if len(ships)!=1 or not ships[0] or len(ships[0])>100:raise ValueError('Ambiguous ship block')
                x,y=block['bbox'][:2]
                candidates=[h for h in headers if abs(h[0]-x)<3 and h[1]<y]
                if not candidates:raise ValueError('Call has no matching calendar day')
                day=max(candidates,key=lambda h:h[1])[2]
                tokens=[w for w in words if w[5]==block['number']]
                dash=[w for w in tokens if w[4]=='-']
                times=[w for w in tokens if CLOCK.fullmatch(w[4])]
                if len(dash)!=1 or len(times)>2:raise ValueError('Ambiguous call time layout')
                arrival=[w[4] for w in times if w[0]<dash[0][0]]
                departure=[w[4] for w in times if w[0]>dash[0][0]]
                if len(arrival)>1 or len(departure)>1:raise ValueError('Ambiguous arrival/departure')
                calls.append({'date':day,'port':port,'ship':ships[0], 'arrival':arrival[0] if arrival else None,
                              'departure':departure[0] if departure else None,'page':page_index+1})
            if headers and sum(w[4]==port for w in words)!=len(calls)-count_before:
                raise ValueError('Unmatched port label: review the source calendar layout')
        if not calls:raise ValueError('No schedule calls extracted')
        unique={}
        for call in sorted(calls,key=lambda c:(c['date'],c['ship'],c['arrival'] or '',c['departure'] or '')):
            key=call['port']+'|'+call['date']+'|'+call['ship']
            unique[key]=unique.get(key,0)+1
            call['id']=hashlib.sha256((key+'|'+str(unique[key])).encode()).hexdigest()[:20]
        return edition,calls

def differences(old,new,checked):
    before={c['id']:c for c in old};after={c['id']:c for c in new};out=[]
    for key in sorted(before.keys()|after.keys()):
        a,b=before.get(key),after.get(key)
        fields=('date','port','ship','arrival','departure')
        if a is None or b is None or any(a[k]!=b[k] for k in fields):out.append({'detected_at':checked,'kind':'added' if not a else 'removed' if not b else 'updated','before':a,'after':b})
    return out

ALLOWED_HOSTS={'claalaska.com','www.porthalifax.ca','www.portofhalifax.ca','portcharlottetown.com','www.sjport.com','www.sydneyport.ca'}

def trusted(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port or '\\' in url:
        raise ValueError('Unreviewed official source URL')
    return url

def upgrade(data):
    result=deepcopy(data)
    if result.get('schema')==1:
        result['schema']=2;result['seasons']=[result['season']];result['attempted_at']=result['checked_at']
        for p in result['ports']:
            p.update(season=result['season'],status='ok',checked_at=result['checked_at'],attempted_at=result['checked_at'],availability_checked_at=result['checked_at'],message='',region='Pacific')
        result.pop('season',None)
    return result

def timestamp(value):
    if value is None:return None
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Source check needs a timezone')
    return value

def validate_public(value):
    data=upgrade(value)
    if data.get('schema')!=2 or not isinstance(data.get('calls'),list) or not data['calls']:raise ValueError('Invalid schedule capture')
    timestamp(data['checked_at']);timestamp(data['attempted_at'])
    ports={p['code']:p for p in data['ports']}
    if len(ports)!=len(data['ports']) or len({c['id'] for c in data['calls']})!=len(data['calls']):raise ValueError('Duplicate port or call identity')
    for p in ports.values():
        ZoneInfo(p['timezone']);trusted(p['url'])
        if p['status'] not in ('ok','pending','unavailable','retained'):raise ValueError('Unknown source status')
        timestamp(p['checked_at']);timestamp(p['attempted_at'])
        if p['count'] and (p['season'] is None or p['checked_at'] is None):raise ValueError('Schedule without verified year/check')
        if p['count']!=sum(c['port']==p['code'] for c in data['calls']):raise ValueError('Port count disagrees with rows')
    for c in data['calls']:
        d=date.fromisoformat(c['date'])
        if c['port'] not in ports or d.year!=ports[c['port']]['season'] or not c['ship']:raise ValueError('Call year does not match its own port schedule')
        if c.get('url'):trusted(c['url'])
        for key in ('arrival','departure'):
            if c[key] is not None and not CLOCK.fullmatch(c[key]):raise ValueError('Invalid call time')
    expected=sorted({p['season'] for p in ports.values() if p['count']})
    if data['seasons']!=expected:raise ValueError('Season list disagrees with verified port coverage')
    if data['checked_at']!=min(p['checked_at'] for p in ports.values() if p['count']):raise ValueError('Overall check must be the oldest available schedule check')
    return data

def identify(rows,entry):
    unique={}
    for row in sorted(rows,key=lambda c:(c['date'],c['ship'],c['arrival'] or '',c['departure'] or '')):
        key=row['port']+'|'+row['date']+'|'+row['ship']
        unique[key]=unique.get(key,0)+1
        row['id']=hashlib.sha256((key+'|'+str(unique[key])).encode()).hexdigest()[:20]
        for field in ('arrival','departure'):
            value=row[field]
            if value is None:row[field+'_at']=None
            else:
                minutes=int(value[:2])*60+int(value[3:])
                local=datetime.combine(date.fromisoformat(row['date']),datetime.min.time())+timedelta(minutes=minutes)
                row[field+'_at']=local.replace(tzinfo=ZoneInfo(entry['timezone'])).astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    return rows

def schedule_signature(ports):
    return [{k:p.get(k) for k in ('code','name','season','url','edition','sha256','count')} for p in ports]

def refresh(root=ROOT,fetch=read_url,now=None):
    config=json.loads((root/'config/ports.json').read_text())
    path=root/'web/data/index.json';original=json.loads(path.read_text()) if path.exists() else None
    old=validate_public(original) if original else None
    oldports={p['code']:p for p in old['ports']} if old else {}
    cache={};robots={}
    def get(url):
        trusted(url)
        if url not in cache:
            try:cache[url]=fetch(url)
            except (OSError,ValueError) as error:cache[url]=error
        if isinstance(cache[url],Exception):raise cache[url]
        return cache[url]
    def allowed(url):
        trusted(url);parts=urlsplit(url);origin=parts.scheme+'://'+parts.netloc
        if origin not in robots:
            parser=RobotFileParser()
            try:parser.parse(get(origin+'/robots.txt').decode().splitlines());robots[origin]=parser
            except HTTPError as error:
                if error.code==404:parser.parse([]);robots[origin]=parser
                else:robots[origin]=error
            except (OSError,ValueError) as error:robots[origin]=error
        if isinstance(robots[origin],Exception):raise robots[origin]
        if not robots[origin].can_fetch(AGENT,url):raise ValueError('Official robots policy does not permit this source')
        return get(url)
    ports=[];calls=[]
    for entry in config['ports']:
        code=entry['code'];prior=oldports.get(code);rows=[]
        base={k:entry[k] for k in ('code','name','timezone','region')}
        url=entry.get('url') or entry['index']
        try:
            if entry['adapter']=='claa':
                html=allowed(entry['index']).decode();url=source_url(html,code,entry['season'])
                raw=allowed(url);edition,rows=parse_pdf(raw,code,entry['season']);season=entry['season']
            elif entry['adapter']=='maritime_pdf':
                html=allowed(entry['index']).decode();url=discover_pdf(html,code)
                raw=allowed(url);season,edition,rows=parse_marine_pdf(raw,code)
            elif entry['adapter']=='html':
                raw=allowed(url);season,edition,rows=parse_port_html(raw,code)
            else:raise ValueError('Unknown source adapter')
            if len(rows)<entry['minimum_calls']:raise ValueError('Incomplete published schedule')
            if prior and prior['season']==season and len(rows)<prior['count']*.85:raise ValueError('Unexpected schedule loss; previous rows retained for review')
            identify(rows,entry)
            checked=now or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
            p=base|{'url':url,'season':season,'edition':edition,'sha256':hashlib.sha256(raw).hexdigest(),'count':len(rows),'status':'ok','checked_at':checked,'attempted_at':checked,'availability_checked_at':checked,'message':''}
        except (OSError,ValueError,KeyError,RuntimeError) as error:
            checked=now or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
            pending=isinstance(error,PendingSchedule)
            message=('Published schedule could not be parsed.' if isinstance(error,RuntimeError) else str(error)) if isinstance(error,(ValueError,RuntimeError)) else ('Official source returned HTTP '+str(error.code)+'.' if isinstance(error,HTTPError) else 'Official source could not be reached.')
            if prior and prior['count']:
                p=deepcopy(prior)|base|{'status':'retained','attempted_at':checked,'message':message}
                rows=[deepcopy(c) for c in old['calls'] if c['port']==code]
                if pending:p['availability_checked_at']=checked
            else:
                p=base|{'url':url,'season':None,'edition':None,'sha256':None,'count':0,'status':'pending' if pending else 'unavailable','checked_at':None,'attempted_at':checked,'availability_checked_at':checked if pending else None,'message':message}
            print(code+': '+p['status']+' — '+message)
        ports.append(p);calls.extend(rows)
    if not calls:raise ValueError('No valid schedule is available; existing published files preserved')
    attempted=now or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    checked=min(p['checked_at'] for p in ports if p['count'])
    seasons=sorted({p['season'] for p in ports if p['count']})
    history=old.get('history',[]) if old else []
    changes=(differences(old['calls'],calls,attempted) if old else [])+(old.get('changes',[]) if old else [])
    archive=None
    if old and (old['calls']!=calls or schedule_signature(old['ports'])!=schedule_signature(ports)):
        name='history/'+old['attempted_at'].replace(':','').replace('-','')+'.json'
        prior=deepcopy(old);prior['history']=[]
        archive=(name,json.dumps(prior,ensure_ascii=False,separators=(',',':'))+'\n')
        history=[{'path':name,'checked_at':old['checked_at'],'seasons':old['seasons'],'count':len(old['calls']),'ports':[p['name'] for p in old['ports'] if p['count']]}]+history
    capture={'schema':2,'seasons':seasons,'checked_at':checked,'attempted_at':attempted,'baseline_at':old['baseline_at'] if old else attempted,'ports':ports,'calls':calls,'changes':changes[:100],'history':history[:config['history_limit']]}
    validate_public(capture)
    payload=(json.dumps(capture,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    failed=sum(p['status'] in ('unavailable','retained') for p in ports)
    pending=sum(p['status']=='pending' for p in ports)
    status={'checked_at':checked,'attempted_at':attempted,'state':'partial' if failed or pending else 'ok','failed_count':failed,'pending_count':pending,'count':len(calls),'port_count':sum(p['count']>0 for p in ports),'configured_port_count':len(ports),'successful_count':sum(p['status']=='ok' for p in ports),'seasons':seasons,'sha256':hashlib.sha256(payload).hexdigest(),'ports':[{k:p[k] for k in ('code','season','count','status','checked_at','attempted_at')} for p in ports]}
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        staged=Path(directory);(staged/'index.json').write_bytes(payload);(staged/'status.json').write_text(json.dumps(status,indent=2)+'\n')
        if archive:
            destination=path.parent/archive[0];destination.parent.mkdir(exist_ok=True);destination.write_text(archive[1])
        (staged/'index.json').replace(path);(staged/'status.json').replace(path.parent/'status.json')
    keep={h['path'] for h in capture['history']}
    for file in (path.parent/'history').glob('*.json'):
        if 'history/'+file.name not in keep:file.unlink()
    print('Published '+str(len(calls))+' schedule entries; '+str(failed)+' unavailable/retained and '+str(pending)+' pending sources.')
    return status

if __name__=='__main__':refresh()
