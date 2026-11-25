"""Exercise schedule filters, private favourites, buffers and real ICS downloads."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def main():
    screenshots=ROOT/'browser-checks';screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        shutil.copytree(ROOT/'dist',Path(temporary)/'portwindow')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=temporary));threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                executable=os.environ.get('CHROMIUM_PATH')
                browser=p.chromium.launch(**({'executable_path':executable} if executable else {}))
                page=browser.new_page(viewport={'width':1280,'height':1000});errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port)+'/portwindow/')
                data=json.loads((ROOT/'web/data/index.json').read_text());sample=next(c for c in data['calls'] if c['arrival'] and c['departure'] and c['arrival']<c['departure'])
                expect(page.locator('#freshness')).to_contain_text(str(len(data['calls'])))
                page.locator('#port').select_option(sample['port']);page.locator('#ship').fill(sample['ship'])
                page.locator('#from').fill(sample['date']);page.locator('#to').fill(sample['date'])
                expect(page.locator('#call-list .call-card')).to_have_count(1)
                page.locator('.star').click();page.locator('#save').click()
                expect(page.locator('#status')).to_contain_text('Saved 1 favourites')
                page.reload();expect(page.locator('#freshness')).to_contain_text(str(len(data['calls'])))
                page.locator('#load').click();page.locator('#favourites-only').check()
                expect(page.locator('#call-list .call-card')).to_have_count(1)
                page.locator('.planner summary').click();page.locator('#after').fill('720');page.locator('#before').fill('720')
                expect(page.locator('.estimate')).to_contain_text('No usable time')
                page.locator('#after').fill('60');page.locator('#before').fill('90')
                with page.expect_download() as event:page.locator('#export').click()
                calendar=Path(event.value.path()).read_text().replace('\n ','')
                assert 'BEGIN:VEVENT' in calendar and 'DTSTART:' in calendar and 'Not an all-aboard' in calendar
                assert 'UID:'+sample['id']+'@portwindow.coolcode.ca' in calendar
                assert 'DTSTART:'+sample['arrival_at'].replace('-','').replace(':','') in calendar
                page.locator('#tab-calendar').click()
                expect(page.locator('#days .day-card')).to_have_count(1)
                page.get_by_role('button',name='View this day').click()
                expect(page.locator('#from')).to_have_value(sample['date'])
                page.locator('#reset').click();page.locator('#ship').fill('ASUKA2');page.locator('#from').fill('2027-05-14');page.locator('#to').fill('2027-05-15')
                expect(page.locator('#call-list .call-card')).to_have_count(2)
                expect(page.locator('.estimate').first).to_contain_text('unavailable')
                page.locator('#export').click();expect(page.locator('#status')).to_contain_text('No complete timed intervals')
                page.locator('#ship').fill('<img src=x onerror=alert(1)>')
                expect(page.locator('#call-list .call-card')).to_have_count(0);assert page.locator('img').count()==0
                page.locator('#reset').click()
                page.screenshot(path=str(screenshots/'desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(screenshots/'mobile.png'),full_page=True)
                page.locator('#forget').click();assert page.evaluate("localStorage.getItem('coolcode:portwindow:favourites')") is None
                assert not errors,errors;browser.close()
            print('Browser passed: source filters, favourites, buffers, unknown times, ICS download, calendar and mobile layout')
        finally:server.shutdown()
if __name__=='__main__':main()
