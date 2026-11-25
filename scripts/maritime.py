"""Reviewed public Maritime schedule adapters; never fill in unpublished times."""
from datetime import date, datetime
from html.parser import HTMLParser
import re

MONTHS={name:i+1 for i,name in enumerate('January February March April May June July August September October November December'.split())}
DATE_LINE=re.compile(r'(?:(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*)?([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})')
TIME=re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d|24:00')

class PendingSchedule(ValueError): pass

class PublicHTML(HTMLParser):
    def __init__(self):
        super().__init__();self.tables=[];self.table=None;self.row=None;self.cell=None;self.text=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag=='table':self.table=[]
        if tag=='tr' and self.table is not None:self.row=[]
        if tag in ('th','td') and self.row is not None:self.cell=[]
        if tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,value):
        if not self.skip:self.text.append(value)
        if self.cell is not None:self.cell.append(value)
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
        if tag in ('th','td') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:
            self.table.append(self.row);self.row=None
        if tag=='table' and self.table is not None:
            self.tables.append(self.table);self.table=None

def clock(value):
    value=value.strip()
    if value.upper() in ('','TBD','TBA','N/A','—','-'):return None
    if re.fullmatch(r'\d{4}',value):value=value[:2]+':'+value[2:]
    if TIME.fullmatch(value):return value
    for pattern in ('%I:%M %p','%I %p'):
        try:return datetime.strptime(value.upper(),pattern).strftime('%H:%M')
        except ValueError:pass
    raise ValueError('Unrecognized published time')

def parse_marine_pdf(raw,port):
    import fitz
    if not raw.startswith(b'%PDF-'):raise ValueError('Source is not a PDF')
    rows=[];texts=[]
    with fitz.open(stream=raw,filetype='pdf') as document:
        if not 1<=len(document)<=20:raise ValueError('Unexpected Maritime calendar size')
        for page_index,page in enumerate(document):
            text=page.get_text();texts.append(text);lines=[v.strip() for v in text.splitlines() if v.strip()]
            for i,line in enumerate(lines):
                match=DATE_LINE.fullmatch(line)
                if not match:continue
                weekday,month,day,year=match.groups()
                d=date(int(year),MONTHS[month],int(day))
                if weekday and d.strftime('%A')!=weekday:raise ValueError('Published weekday mismatch')
                if i+2>=len(lines):raise ValueError('Incomplete published row')
                ship=lines[i+1].upper();interval=lines[i+2].replace('–','-').replace('—','-')
                if not re.fullmatch(r'(?:\d{4}|TBD|TBA)?\s*-\s*(?:\d{4}|TBD|TBA)?',interval):raise ValueError('Unrecognized published interval')
                start,end=interval.split('-')
                rows.append({'date':d.isoformat(),'port':port,'ship':ship,'arrival':clock(start),'departure':clock(end),'page':page_index+1})
    full='\n'.join(texts)
    expected='Port of Sydney Cruise Schedule' if port=='SYD' else 'Louisbourg Schedule'
    title=re.search(re.escape(expected)+r'\s+(20\d{2})',full)
    if not title or not rows:raise ValueError('Missing named schedule and year')
    season=int(title[1])
    if any(int(r['date'][:4])!=season for r in rows):raise ValueError('Mixed or mismatched PDF year')
    match=re.search(r'As of\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(20\d{2})',full)
    edition=date(int(match[3]),MONTHS[match[1]],int(match[2])).isoformat() if match else None
    return season,edition,rows

def parse_port_html(raw,port):
    parser=PublicHTML();parser.feed(raw.decode('utf-8'))
    text=' '.join(' '.join(parser.text).split())
    for phrase in ('The Cruise Schedule will be coming soon','check back in January for our 2027 cruise season schedule'):
        if phrase.casefold() in text.casefold():raise PendingSchedule(phrase)
    titles=re.findall(r'(20\d{2})\s+(?:Cruise\s+)?Schedule|(?:Cruise\s+)?Schedule\s+(20\d{2})',text,re.I)
    years={int(a or b) for a,b in titles}
    if len(years)!=1:raise ValueError('Published schedule year is missing or ambiguous')
    season=years.pop();rows=[]
    for table in parser.tables:
        header=None
        for cells in table:
            lowered=[v.casefold() for v in cells]
            if 'date' in lowered and any(v in lowered for v in ('vessel','ship','cruise ship')) and any('arrival' in v for v in lowered) and any('departure' in v for v in lowered):
                header={'date':lowered.index('date'),'ship':next(i for i,v in enumerate(lowered) if v in ('vessel','ship','cruise ship')),'arrival':next(i for i,v in enumerate(lowered) if 'arrival' in v),'departure':next(i for i,v in enumerate(lowered) if 'departure' in v)}
                continue
            if not header or not cells:continue
            if len(cells)<=max(header.values()):raise ValueError('Incomplete HTML schedule row')
            source_date=cells[header['date']]
            if re.fullmatch(r'\d{2}-\d{2}',source_date):d=date.fromisoformat(str(season)+'-'+source_date)
            elif re.fullmatch(r'20\d{2}-\d{2}-\d{2}',source_date):d=date.fromisoformat(source_date)
            else:
                match=DATE_LINE.fullmatch(source_date)
                if not match:raise ValueError('Unrecognized HTML schedule date')
                weekday,month,day,year=match.groups();d=date(int(year),MONTHS[month],int(day))
                if weekday and d.strftime('%A')!=weekday:raise ValueError('Published weekday mismatch')
            if d.year!=season:raise ValueError('HTML year mismatch')
            ship=cells[header['ship']].strip().upper()
            if not ship:raise ValueError('Missing vessel name')
            rows.append({'date':d.isoformat(),'port':port,'ship':ship,'arrival':clock(cells[header['arrival']]),'departure':clock(cells[header['departure']]),'page':None})
    if not rows:raise ValueError('No dated arrival/departure table is published')
    edition=re.search(r'Last Updated:\s*([A-Za-z]+ \d{1,2}, 20\d{2}(?: \d{2}:\d{2})?)',text)
    return season,edition[1]+' (source-local)' if edition else None,rows

def discover_pdf(html,port):
    wanted={'SYD':'DOWNLOAD','LOU':'LOUISBOURG CRUISE SCHEDULE'}[port]
    class Anchors(HTMLParser):
        def __init__(self):super().__init__();self.matches=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='a' and a.get('aria-label')==wanted:self.matches.append(a.get('href',''))
    parser=Anchors();parser.feed(html)
    urls=set(parser.matches)
    if len(urls)!=1:raise ValueError('Official download link is missing or ambiguous')
    url=urls.pop()
    if not re.fullmatch(r'https://www\.sydneyport\.ca/_files/ugd/[A-Za-z0-9_]+\.pdf',url):raise ValueError('Unreviewed schedule download host or path')
    return url
