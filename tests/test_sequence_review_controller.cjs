// Source-derived response projection of retained recorded bytes; no server/browser execution.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const script=`import sys,json,tempfile;sys.path.insert(0,'tests');from app import Dataset;from test_sequences import body;from test_producer_v2_controls import body as v2body;from fixtures.rheon_synthetic_v2 import fixture;from pathlib import Path;import rheon_sequences as r;import sequence_inspection as p\nwith tempfile.TemporaryDirectory() as tmp:\n d=Dataset(tmp);src=Path('tests/fixtures/rheon_actual_fee7b4a');row=r.admit(d.workbench,body((src/'run.json').read_bytes(),(src/'frames.jsonl').read_bytes()));request=dict(revision=1,source_revision=1,field='velocity_y',index=[0,1,0],plane_axis='z');result=p.review(d.workbench,row['id'],request);v2=r.admit(d.workbench,v2body(fixture()));other=p.review(d.workbench,v2['id'],request);print(json.dumps(dict(record=row,data=result,v2record=v2,v2data=other)));d.close()`;
const produced=spawnSync(process.env.PYTHON||'python3',['-c',script],{cwd:root,encoding:'utf8',timeout:30000});assert.equal(produced.status,0,produced.stderr);
const fixtures=JSON.parse(produced.stdout),elements=new Map(),events={},requests=[],timers=new Map();let timer=0,marks=0;
function element(){return {value:'0',dataset:{},hidden:false,disabled:false,textContent:'',events:{},children:[],addEventListener(name,fn){this.events[name]=fn;},setAttribute(name,value){this[name]=value;},append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;}};}
const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
const context=vm.createContext({$,AbortController,structuredClone,Uint8Array,TextDecoder,TextEncoder,JSON,Math,Number,Object,Array,String,Error,encodeURIComponent,
 current:fixtures.record,markDirty:()=>{marks++;$('record-review').value='draft';},
 window:{addEventListener:(name,fn)=>events[name]=fn},document:{createElementNS:()=>element()},
 setInterval:fn=>{timers.set(++timer,fn);return timer;},clearInterval:id=>timers.delete(id),
 fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
vm.runInContext(fs.readFileSync(path.join(root,'static/sequence-review.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context),clone=x=>structuredClone(x),flush=()=>new Promise(r=>setImmediate(r));
function show(record=fixtures.record){context.current=record;$('task').value='sequence_transport';run('sequenceReviewShown(current)');$('sequence-review-field').value='velocity_y';$('sequence-review-axis').value='z';$('sequence-review-j').value='1';}
const click=id=>$(id).events.click(),load=()=>click('sequence-review-load');
const reply=(q,value=fixtures.data,status=200)=>q.resolve(new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}}));
(async()=>{
  show();let promise=load(),q=requests.shift();assert.equal(JSON.parse(q.options.body).plane_axis,'z');await load();assert.equal(requests.length,0,'Repeated active Load refused');reply(q);await promise;
  assert.equal($('sequence-review-view').hidden,false);assert.equal($('sequence-review-append').disabled,false);assert.equal(marks,0);
  click('sequence-review-next');assert.match($('sequence-review-label').textContent,/Frame 1/);assert.equal(requests.length,0);
  click('sequence-review-play');for(let k=0;k<7;k++)[...timers.values()][0]?.();assert.match($('sequence-review-label').textContent,/Frame 8/);assert.equal(timers.size,0);assert.equal(requests.length,0);
  $('sequence-note').value='Retain 🦋 existing note';$('record-review').value='human_reviewed';click('sequence-review-append');assert.equal(marks,1);assert.match($('sequence-note').value,/Retain 🦋 existing note\nNative inspection/);assert.match($('sequence-note').value,/frame 8/);assert.equal($('record-review').value,'draft');
  click('sequence-review-append');assert.equal(marks,1,'Exact duplicate reference is a no-op');
  $('sequence-note').value='🦋'.repeat(4000);click('sequence-review-append');assert.equal([...$('sequence-note').value].length,4000);assert.equal(marks,1);assert.match($('sequence-review-status').textContent,/Nothing appended/);
  $('sequence-note').value='\ud800';click('sequence-review-append');assert.equal(marks,1);
  $('sequence-note').value='Keep';$('editor').dataset.busy='true';click('sequence-review-append');assert.equal($('sequence-note').value,'Keep');delete $('editor').dataset.busy;
  for(const owner of ['rightsBusy','responseBusy','preferenceBusy']){context[owner]=true;click('sequence-review-append');assert.equal(marks,1);context[owner]=false;}
  $('task').value='other';click('sequence-review-append');assert.equal(marks,1);$('task').value='sequence_transport';
  show();promise=load();const old=requests.shift();$('sequence-review-j').events.input();assert.equal(old.options.signal.aborted,true);
  const newer=load(),next=requests.shift();reply(old);await promise;assert.equal($('sequence-review-load').disabled,true,'Old finally cannot release newer owner');reply(next);await newer;assert.equal($('sequence-review-view').hidden,false);
  promise=load();q=requests.shift();click('sequence-review-cancel');reply(q);await promise;assert.equal($('sequence-review-view').hidden,true);
  show();promise=load();q=requests.shift();events.pagehide();assert.equal(q.options.signal.aborted,true);reply(q);await promise;assert.equal($('sequence-review-view').hidden,true);
  $('sequence-note').value='Dirty note survives restored page';events.pageshow({persisted:true});assert.equal($('sequence-note').value,'Dirty note survives restored page');assert.equal($('sequence-review-load').disabled,false);
  promise=load();q=requests.shift();reply(q);await promise;assert.equal($('sequence-review-view').hidden,false);
  for(const mutate of [d=>d.revision++,d=>d.geometry.axis_order.reverse(),d=>d.field.shape[0]++,d=>d.plane.axes.reverse(),d=>d.frames.pop(),d=>d.frames[1].metadata.carrier_stamp.version='01',d=>d.frames[1].plane_values.pop(),d=>d.frames[1].value=null,d=>d.frames[1].value='0',d=>d.frames[1].value=1e300,d=>d.frames[0].accepted_interval={},d=>d.controls.scope='producer_controls_validated',d=>d.extra=1]){
    show();const bad=clone(fixtures.data);mutate(bad);promise=load();q=requests.shift();reply(q,bad);await promise;assert.equal($('sequence-review-view').hidden,true);assert.equal($('sequence-review-append').disabled,true);assert.match($('sequence-review-status').textContent,/Invalid trajectory response/);
  }
  show();promise=load();q=requests.shift();q.resolve(new Response('x'.repeat(128*1024+1)));await promise;assert.match($('sequence-review-status').textContent,/128 KiB/);assert.equal($('sequence-review-view').hidden,true);
  show();promise=load();q=requests.shift();q.resolve(new Response(new Uint8Array([0xff])));await promise;assert.equal($('sequence-review-view').hidden,true);
  show();promise=load();q=requests.shift();reply(q,{error:'Conflict'},409);await promise;assert.match($('sequence-review-status').textContent,/Conflict/);
  show();$('sequence-review-i').value='16';$('sequence-review-field').value='fraction';$('sequence-review-field').events.change();await load();assert.equal(requests.length,0);assert.equal($('sequence-review-i').value,'16','Changing field cannot silently move native index');assert.match($('sequence-review-status').textContent,/0 to 15/);$('sequence-review-i').value='0';
  show(fixtures.v2record);promise=load();q=requests.shift();reply(q,fixtures.v2data);await promise;assert.equal($('sequence-review-view').hidden,false);click('sequence-review-next');assert.match($('sequence-review-details').textContent,/producer_emitted/);
  for(const mutate of [d=>d.controls.sha256='0'.repeat(64),d=>d.controls.units.source_rate='m/s',d=>d.frames[1].emitted_control.carrier_after.version='02',d=>d.frames[0].emitted_control=d.frames[1].emitted_control]){
    show(fixtures.v2record);const bad=clone(fixtures.v2data);mutate(bad);promise=load();q=requests.shift();reply(q,bad);await promise;assert.equal($('sequence-review-view').hidden,true);
  }
  assert.equal(run('sequenceReviewNumber(-0)'),'-0');assert.equal(run('sequenceReviewNumber(5e-324)'),'5e-324');
  for(const source of ['sequenceReviewScale(0,-1e308,1e308)','sequenceReviewScale(5e-324,0,1e-323)','sequenceReviewScale(1,1,1)'])assert.ok(Number.isFinite(run(source)));
  console.log('Native trajectory controller PASS: all-nine local navigation, typed/hash/axis/stamp/control validation, byte caps, append Unicode/ownership/draft reset, cancellation/newer owner/BFcache, native display and finite extreme scaling.');
})().catch(error=>{console.error(error);process.exitCode=1;});
