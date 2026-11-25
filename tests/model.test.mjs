import test from 'node:test';
import assert from 'node:assert/strict';
import {dateOnly,minutes,selectCalls,duration,bufferWindow,clock,dayStats,calendar,validateFavourites} from '../web/model.mjs';
const call={id:'0123456789abcdef0123',date:'2027-07-01',port:'VAN',ship:'ANY NEW SHIP',arrival:'07:00',departure:'16:00',arrival_at:'2027-07-01T14:00:00Z',departure_at:'2027-07-01T23:00:00Z',page:2};
test('arbitrary ships and data-derived ports filter without presets',()=>{assert.equal(selectCalls([call,{...call,port:'NEW',ship:'BEYOND THE DEFAULTS'}],{port:'NEW',query:'defaults'}).length,1);assert.equal(selectCalls([call],{from:'2027-07-02'}).length,0);});
test('date and time validation includes midnight without rollover guesses',()=>{assert.ok(dateOnly('2028-02-29'));assert.ok(!dateOnly('2027-02-29'));assert.equal(minutes('24:00'),1440);assert.throws(()=>minutes('24:01'));assert.equal(duration({...call,arrival:null}),null);assert.equal(duration({...call,arrival:'22:00',departure:'03:00'}),null);});
test('personal buffers reduce only known same-day intervals',()=>{assert.deepEqual(bufferWindow(call,60,90),{kind:'window',start:480,end:870,minutes:390});assert.equal(bufferWindow(call,500,500).kind,'none');assert.equal(bufferWindow({...call,departure:null},60,90).kind,'unknown');assert.throws(()=>bufferWindow(call,1.5,30));assert.throws(()=>bufferWindow(call,-1,30));assert.match(clock(1440),/next midnight/);});
test('overlap handles simultaneous departure and arrival and excludes missing times',()=>{assert.deepEqual(dayStats([call,{...call,arrival:'16:00',departure:'20:00'},{...call,arrival:null}]),{count:3,peak:1,unknown:1});assert.equal(dayStats([call,{...call,arrival:'15:00',departure:'18:00'}]).peak,2);});
test('ICS uses source UTC intervals, escaped text and skips unknown time',()=>{const result=calendar([{...call,ship:'Ship; name,\nnext'}, {...call,arrival:null}],[{code:'VAN',name:'Vancouver',timezone:'America/Vancouver',url:'https://claalaska.com/source.pdf'}],'2026-11-25T00:00:00Z','2026-11-25T01:00:00Z');assert.equal(result.count,1);assert.equal(result.skipped,1);assert.match(result.text,/DTSTART:20270701T140000Z/);assert.match(result.text,/Ship\\; name\\,\\nnext/);assert.ok(result.text.endsWith('\r\n'));for(const line of result.text.split('\r\n'))assert.ok(new TextEncoder().encode(line).length<=75);});
test('favourites import is bounded and validates identities',()=>{assert.equal(validateFavourites([call.id,call.id]).size,1);assert.throws(()=>validateFavourites(['<script>']));});

import {upgradeCapture,coverageMessage} from '../web/model.mjs';
test('port years cannot be mixed by the year filter',()=>{const old={...call,date:'2026-07-01',port:'SYD'};assert.equal(selectCalls([call,old],{season:'2026'})[0].port,'SYD');assert.equal(selectCalls([call,old],{port:'SYD',season:'2027'}).length,0);});
test('prior, upcoming, pending and retained sources have explicit meanings',()=>{
 const base={season:2026,count:90,status:'ok',message:'',last_date:'2026-11-03'};
 assert.match(coverageMessage(base,'2026-11-25T00:00:00Z').text,/prior sailing season/);
 assert.match(coverageMessage({...base,season:2027,last_date:'2027-11-03'},'2026-11-25T00:00:00Z').text,/Upcoming 2027/);
 assert.match(coverageMessage({...base,status:'retained',message:'HTTP 403'},'2026-11-25T00:00:00Z').text,/original check time/);
 assert.match(coverageMessage({count:0,status:'pending',message:'Coming in January'}).text,/No published call table/);
});
test('legacy Pacific captures keep their original year and check time',()=>{
 const legacy={schema:1,season:2027,checked_at:'2026-11-25T00:00:00Z',calls:[call],changes:[],ports:[{code:'VAN',count:1}],history:[]};
 const upgraded=upgradeCapture(legacy);assert.equal(upgraded.ports[0].season,2027);assert.equal(upgraded.ports[0].checked_at,legacy.checked_at);assert.equal(legacy.schema,1);
});
test('ICS uses each retained port check rather than a fresher global attempt',()=>{
 const out=calendar([call],[{code:'VAN',name:'Vancouver',timezone:'America/Vancouver',url:'https://claalaska.com/source.pdf',season:2027,status:'retained',checked_at:'2026-11-20T00:00:00Z'}],'2026-11-25T00:00:00Z').text.replace(/\r\n /g,'');
 assert.match(out,/last successfully checked 2026-11-20/);assert.match(out,/refresh failed/);assert.match(out,/Schedule year 2027/);
});
