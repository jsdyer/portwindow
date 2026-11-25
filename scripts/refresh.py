#!/usr/bin/env python3
"""Normalize dated facts from public CLAA calendars without guessing missing times."""
from datetime import date, datetime, timezone, timedelta
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
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

def validate_public(data):
    if data.get('schema')!=1 or not isinstance(data.get('calls'),list) or not data['calls']:raise ValueError('Invalid schedule capture')
    datetime.fromisoformat(data['checked_at'].replace('Z','+00:00'))
    ports={p['code']:p for p in data['ports']}
    if len({c['id'] for c in data['calls']})!=len(data['calls']):raise ValueError('Duplicate call ID')
    for p in ports.values():
        ZoneInfo(p['timezone'])
        if not p['url'].startswith('https://claalaska.com/wp-content/uploads/') or not p['url'].endswith('.pdf'):raise ValueError('Untrusted source link')
    for c in data['calls']:
        d=date.fromisoformat(c['date'])
        if d.year!=data['season'] or c['port'] not in ports or not c['ship']:raise ValueError('Invalid call')
        for key in ('arrival','departure'):
            if c[key] is not None and not CLOCK.fullmatch(c[key]):raise ValueError('Invalid call time')
    return data

def differences(old,new,checked):
    before={c['id']:c for c in old};after={c['id']:c for c in new};out=[]
    for key in sorted(before.keys()|after.keys()):
        a,b=before.get(key),after.get(key)
        fields=('date','port','ship','arrival','departure')
        if a is None or b is None or any(a[k]!=b[k] for k in fields):out.append({'detected_at':checked,'kind':'added' if not a else 'removed' if not b else 'updated','before':a,'after':b})
    return out

def refresh(root=ROOT,fetch=read_url,now=None):
    config=json.loads((root/'config/ports.json').read_text())
    if config['schedule_index']!='https://claalaska.com/?page_id=1250':raise ValueError('Review any replacement source index')
    robot=RobotFileParser();robot.parse(fetch('https://claalaska.com/robots.txt').decode().splitlines())
    if not robot.can_fetch(AGENT,config['schedule_index']):raise ValueError('Source does not permit this crawler')
    html=fetch(config['schedule_index']).decode()
    calls=[];ports=[]
    for entry in config['ports']:
        url=source_url(html,entry['code'],config['season'])
        if not robot.can_fetch(AGENT,url):raise ValueError('Source disallows calendar collection')
        raw=fetch(url);edition,rows=parse_pdf(raw,entry['code'],config['season'])
        if len(rows)<entry['minimum_calls']:raise ValueError('Incomplete calendar for '+entry['code'])
        for row in rows:
            for field in ('arrival','departure'):
                value=row[field]
                if value is None:row[field+'_at']=None
                else:
                    minutes=int(value[:2])*60+int(value[3:])
                    local=datetime.combine(date.fromisoformat(row['date']),datetime.min.time())+timedelta(minutes=minutes)
                    row[field+'_at']=local.replace(tzinfo=ZoneInfo(entry['timezone'])).astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        ports.append({k:entry[k] for k in ('code','name','timezone')}|{'url':url,'edition':edition,'sha256':hashlib.sha256(raw).hexdigest(),'count':len(rows)})
        calls.extend(rows)
    checked=now or datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    path=root/'web/data/index.json';old=json.loads(path.read_text()) if path.exists() else None
    if old and config['season']==old['season']:
        for port in ports:
            previous=sum(c['port']==port['code'] for c in old['calls'])
            if port['count']<previous*.85:raise ValueError('Unexpected schedule loss; retain previous capture')
    history=old.get('history',[]) if old else []
    changes=(differences(old['calls'],calls,checked) if old else [])+(old.get('changes',[]) if old else [])
    archive=None
    if old and (old['calls']!=calls or old['ports']!=ports or old['season']!=config['season']):
        name='history/'+old['checked_at'].replace(':','').replace('-','')+'.json'
        prior={k:v for k,v in old.items() if k!='history'};prior['history']=[]
        archive=(name,json.dumps(prior,ensure_ascii=False,separators=(',',':'))+'\n')
        history=[{'path':name,'checked_at':old['checked_at'],'season':old['season'],'count':len(old['calls']),'ports':[p['name'] for p in old['ports']]}]+history
    capture={'schema':1,'season':config['season'],'checked_at':checked,'baseline_at':old['baseline_at'] if old else checked,'ports':ports,'calls':calls,'changes':changes[:100],'history':history[:config['history_limit']]}
    validate_public(capture)
    payload=(json.dumps(capture,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    status={'checked_at':checked,'count':len(calls),'port_count':len(ports),'season':config['season'],'sha256':hashlib.sha256(payload).hexdigest()}
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        staged=Path(directory);(staged/'index.json').write_bytes(payload);(staged/'status.json').write_text(json.dumps(status,indent=2)+'\n')
        if archive:
            destination=path.parent/archive[0];destination.parent.mkdir(exist_ok=True);destination.write_text(archive[1])
        (staged/'index.json').replace(path);(staged/'status.json').replace(path.parent/'status.json')
    keep={h['path'] for h in capture['history']}
    for file in (path.parent/'history').glob('*.json'):
        if 'history/'+file.name not in keep:file.unlink()
    print('Checked '+str(len(calls))+' schedule entries across '+str(len(ports))+' ports at '+checked)

if __name__=='__main__':refresh()
