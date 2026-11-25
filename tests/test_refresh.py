import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import ROOT, parse_pdf, refresh, source_url, differences

class Page:
    def __init__(self,fixture=None):self.fixture=fixture
    def get_text(self,kind=None):
        if self.fixture is None:
            if kind is None:return 'Cruise Ship Calendar for 2027\nFOR PORT(S) = VAN\n12:02 Friday, October 02, 2026'
            return {'blocks':[]} if kind=='dict' else []
        return {'blocks':self.fixture['blocks']} if kind=='dict' else self.fixture['words']
class Document(list):
    def __enter__(self):return self
    def __exit__(self,*_):pass

class ParserTests(unittest.TestCase):
    def test_real_positioned_overnight_cells_do_not_invent_missing_times(self):
        fixture=json.loads((ROOT/'tests/fixtures/overnight-layout.json').read_text())
        with patch('fitz.open',return_value=Document([Page(),Page(fixture)])):
            edition,calls=parse_pdf(b'%PDF-fixture','VAN',2027)
        self.assertEqual(edition,'2026-10-02 12:02 (source-local)')
        self.assertEqual([(c['date'],c['arrival'],c['departure']) for c in calls],[('2027-05-14','18:00',None),('2027-05-15',None,'17:00')])
    def test_wrong_season_and_unmatched_calendar_cell_rejected(self):
        fixture=json.loads((ROOT/'tests/fixtures/overnight-layout.json').read_text())
        with patch('fitz.open',return_value=Document([Page(),Page(fixture)])):
            with self.assertRaises(ValueError):parse_pdf(b'%PDF-fixture','VAN',2028)
        fixture['blocks']=[b for b in fixture['blocks'] if any('ASUKA2' in s['text'] for l in b.get('lines',[]) for s in l['spans'])]
        with patch('fitz.open',return_value=Document([Page(),Page(fixture)])):
            with self.assertRaisesRegex(ValueError,'calendar day'):parse_pdf(b'%PDF-fixture','VAN',2027)
    def test_link_discovery_follows_current_index_not_fixed_upload_month(self):
        url='https://claalaska.com/wp-content/uploads/2027/03/VAN-Vancouver-2027.pdf'
        self.assertEqual(source_url('<a href="'+url+'">Vancouver</a>','VAN',2027),url)
        with self.assertRaises(ValueError):source_url('<a href="https://evil.example/VAN-Vancouver-2027.pdf">x</a>','VAN',2027)
    def test_pagination_alone_is_not_a_sailing_change(self):
        a={'id':'a','date':'2027-05-14','port':'VAN','ship':'Ship','arrival':'07:00','departure':'16:00','page':2}
        self.assertEqual(differences([a],[dict(a,page=3)],'now'),[])
        self.assertEqual(differences([a],[dict(a,departure='17:00')],'now')[0]['kind'],'updated')

class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'config').mkdir()
        config=json.loads((ROOT/'config/ports.json').read_text());config['ports']=config['ports'][:1];config['ports'][0]['minimum_calls']=1;config['history_limit']=2
        (self.root/'config/ports.json').write_text(json.dumps(config))
        self.rows=[{'id':'0123456789abcdef0123','date':'2027-07-01','port':'VAN','ship':'A SHIP','arrival':'20:00','departure':'24:00','page':2}]
    def tearDown(self):self.tmp.cleanup()
    def fetch(self,url):
        if url.endswith('robots.txt'):return b'User-Agent: *\nDisallow:\n'
        if 'page_id' in url:return b'<a href="https://claalaska.com/wp-content/uploads/2026/10/VAN-Vancouver-2027.pdf">Vancouver</a>'
        return b'%PDF-source'
    def run_capture(self,now='2026-11-25T12:00:00Z'):
        with patch('refresh.parse_pdf',return_value=('2026-10-02 12:02 (source-local)',copy.deepcopy(self.rows))):
            refresh(self.root,self.fetch,now)
        return json.loads((self.root/'web/data/index.json').read_text())
    def test_midnight_rollover_uses_port_timezone_for_calendar_export(self):
        data=self.run_capture();c=data['calls'][0]
        self.assertEqual(c['arrival_at'],'2027-07-02T03:00:00Z')
        self.assertEqual(c['departure_at'],'2027-07-02T07:00:00Z')
    def test_failed_download_preserves_good_capture_and_probe(self):
        self.run_capture();before={p.name:p.read_bytes() for p in (self.root/'web/data').iterdir()}
        with self.assertRaises(OSError):refresh(self.root,lambda _: (_ for _ in ()).throw(OSError('HTTP 403')))
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'web/data').iterdir()})
    def test_unchanged_check_does_not_create_false_history(self):
        first=self.run_capture();second=self.run_capture('2026-11-26T12:00:00Z')
        self.assertEqual(second['history'],[]);self.assertEqual(second['changes'],[])
        self.assertEqual(first['ports'],second['ports']);self.assertNotEqual(first['checked_at'],second['checked_at'])
    def test_changed_times_retain_prior_capture(self):
        first=self.run_capture();self.rows[0]['departure']='23:00';second=self.run_capture('2026-11-26T12:00:00Z')
        self.assertEqual(len(second['history']),1)
        previous=json.loads((self.root/'web/data'/second['history'][0]['path']).read_text())
        self.assertEqual(previous['calls'],first['calls'])
        self.assertEqual(second['changes'][0]['before']['departure'],'24:00')
    def test_robots_disallow_stops_before_pdf_collection(self):
        with self.assertRaisesRegex(ValueError,'permit'):
            refresh(self.root,lambda _: b'User-Agent: *\nDisallow: /\n')
