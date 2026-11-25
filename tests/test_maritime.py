import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import ROOT, refresh, validate_public
from maritime import parse_marine_pdf, parse_port_html, discover_pdf, PendingSchedule
class Page:
    def __init__(self,text):self.text=text
    def get_text(self):return self.text
class Document(list):
    def __enter__(self):return self
    def __exit__(self,*_):pass
def pdf_fixture(name,port):
    pages=(ROOT/'tests/fixtures'/name).read_text().split('\n\f\n')
    with patch('fitz.open',return_value=Document([Page(s) for s in pages])):
        return parse_marine_pdf(b'%PDF-fixture',port)
class MaritimeTests(unittest.TestCase):
    def test_current_sydney_source_is_2026_with_ninety_real_rows(self):
        season,edition,rows=pdf_fixture('sydney-2026-text.txt','SYD')
        self.assertEqual((season,edition,len(rows)),(2026,'2026-04-29',90))
        self.assertEqual(rows[0]['date'],'2026-04-09');self.assertEqual(rows[0]['arrival'],'08:00')
        self.assertEqual(max(c['date'] for c in rows),'2026-11-03')
    def test_louisbourg_keeps_actual_year_and_no_invented_edition(self):
        season,edition,rows=pdf_fixture('louisbourg-2026-text.txt','LOU')
        self.assertEqual((season,edition,len(rows)),(2026,None,6))
        self.assertEqual(rows[0]['ship'],'SCENIC ECLIPSE')
    def test_current_pdf_links_are_discovered_by_official_labels(self):
        html=(ROOT/'tests/fixtures/maritime-links.html').read_text()
        self.assertIn('c32bc8179ab24',discover_pdf(html,'SYD'));self.assertIn('a4f8478aed4',discover_pdf(html,'LOU'))
        with self.assertRaises(ValueError):discover_pdf(html.replace('www.sydneyport.ca','evil.example'),'SYD')
    def test_halifax_blank_overnight_cells_stay_unknown(self):
        season,edition,rows=parse_port_html((ROOT/'tests/fixtures/halifax-table-excerpt.html').read_bytes(),'HAL')
        self.assertEqual(season,2026);self.assertIsNone(rows[0]['departure']);self.assertIsNone(rows[1]['arrival'])
        self.assertEqual(rows[1]['date'],'2026-04-08')
    def test_ambiguous_html_year_cannot_relabel_prior_season(self):
        raw=b'<nav>2027 Cruise Schedule</nav>'+(ROOT/'tests/fixtures/halifax-table-excerpt.html').read_bytes()
        with self.assertRaisesRegex(ValueError,'ambiguous'):parse_port_html(raw,'HAL')
    def test_pending_is_explicit_and_vendor_hours_cannot_be_vessel_times(self):
        for notice in ['The Cruise Schedule will be coming soon','check back in January for our 2027 cruise season schedule']:
            with self.assertRaises(PendingSchedule):parse_port_html(('<h1>Cruise</h1><p>'+notice+'</p>').encode(),'CHT')
        with self.assertRaises(ValueError):parse_port_html(b'<h1>2026 Cruise Schedule</h1><table><tr><th>Date</th><th>Ship</th><th>Retail hours</th></tr><tr><td>09-01</td><td>A ship</td><td>9-5</td></tr></table>','CHT')

class PartialRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'config').mkdir()
        allports=json.loads((ROOT/'config/ports.json').read_text())['ports']
        self.config={'history_limit':3,'ports':[copy.deepcopy(p) for p in allports if p['code'] in ('VAN','SYD','CHT')]}
        for p in self.config['ports']:p['minimum_calls']=1
        (self.root/'config/ports.json').write_text(json.dumps(self.config))
        self.pacific=[{'port':'VAN','date':'2027-07-01','ship':'A SHIP','arrival':'20:00','departure':'24:00','page':2}]
        self.atlantic=[{'port':'SYD','date':'2026-09-01','ship':'ANOTHER SHIP','arrival':'08:00','departure':'18:00','page':1}]
        self.broken=False
    def tearDown(self):self.tmp.cleanup()
    def fetch(self,url):
        if url.endswith('/robots.txt'):return b'User-agent: *\nDisallow:\n'
        if 'page_id' in url:return b'<a href="https://claalaska.com/wp-content/uploads/2026/10/VAN-Vancouver-2027.pdf">Vancouver</a>'
        if url.endswith('/cruiseschedule'):return (ROOT/'tests/fixtures/maritime-links.html').read_bytes()
        if 'portcharlottetown' in url:return b'<h1>Cruise schedule</h1><p>The Cruise Schedule will be coming soon</p>'
        return b'%PDF-broken' if 'sydneyport' in url and self.broken else b'%PDF-source'
    def capture(self,now,marine=None):
        def parser(raw,port):
            if raw==b'%PDF-broken':raise RuntimeError('Failed to open damaged PDF')
            return 2026,'2026-04-29',copy.deepcopy(self.atlantic)
        with patch('refresh.parse_pdf',return_value=('2026-10-02',copy.deepcopy(self.pacific))),patch('refresh.parse_marine_pdf',side_effect=parser):
            status=refresh(self.root,self.fetch,now)
        return json.loads((self.root/'web/data/index.json').read_text()),status
    def test_mixed_years_and_pending_source_keep_each_port_truthful(self):
        data,status=self.capture('2026-11-25T12:00:00Z')
        self.assertEqual(data['seasons'],[2026,2027]);self.assertEqual(status['pending_count'],1)
        syd=next(p for p in data['ports'] if p['code']=='SYD');cht=next(p for p in data['ports'] if p['code']=='CHT')
        self.assertEqual(syd['season'],2026);self.assertIsNone(cht['season']);self.assertIsNone(cht['checked_at'])
        self.assertEqual(cht['availability_checked_at'],'2026-11-25T12:00:00Z')
        row=next(c for c in data['calls'] if c['port']=='SYD')
        self.assertEqual(row['arrival_at'],'2026-09-01T11:00:00Z')
        self.assertEqual(row['departure_at'],'2026-09-01T21:00:00Z')
    def test_broken_optional_pdf_retains_only_its_old_capture_while_others_advance(self):
        first,_=self.capture('2026-11-25T12:00:00Z');self.broken=True
        second,status=self.capture('2026-11-26T12:00:00Z')
        ports={p['code']:p for p in second['ports']}
        self.assertEqual(ports['SYD']['status'],'retained')
        self.assertEqual(ports['SYD']['checked_at'],'2026-11-25T12:00:00Z')
        self.assertEqual(ports['VAN']['checked_at'],'2026-11-26T12:00:00Z')
        self.assertEqual(status['checked_at'],'2026-11-25T12:00:00Z');self.assertEqual(status['failed_count'],1)
        self.assertEqual(first['calls'],second['calls'])
    def test_invalid_source_year_is_rejected_before_publication(self):
        data,_=self.capture('2026-11-25T12:00:00Z')
        next(p for p in data['ports'] if p['code']=='SYD')['season']=2027
        with self.assertRaisesRegex(ValueError,'year'):validate_public(data)
    def test_real_malformed_pdf_raises_known_failure_class(self):
        with self.assertRaises((RuntimeError,ValueError)):parse_marine_pdf(b'%PDF-broken','SYD')
