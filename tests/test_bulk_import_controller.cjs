// Owned bulk scheduling/proof tests. Real HTTP/browser coverage is separate.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const crypto=require('node:crypto');
class Element{
  constructor(){this.files=[];this.children=[];this.listeners={};this.disabled=false;this.textContent='';}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
  replaceChildren(){this.children=[];}
  append(item){this.children.push(item);}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){}});}
}
function fixture(){
  const elements=new Map(),requests=[],notices=[];let refreshes=0;
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const selected=new Map();let intents=0,invalidations=0;
  const context=vm.createContext({console,TextEncoder,TextDecoder,crypto:crypto.webcrypto,selected,
    selection:intent=>{if(intent)intents++;},invalidateRelease:()=>invalidations++,
    $,document:{createElement:()=>new Element()},notice:(...args)=>notices.push(args),refresh:async()=>{refreshes++;},
    readImportImage:async()=>Buffer.from('image fixture').toString('base64'),
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/bulk_import.js'),'utf8'),context);
  const manifest=(rows,name='assets.jsonl')=>({name,size:Buffer.byteLength(rows),arrayBuffer:async()=>new TextEncoder().encode(rows).buffer});
  const choose=(rows,images=[])=>{$('bulk-manifest').files=[manifest(rows)];$('bulk-images').files=images;};
  const row=text=>JSON.stringify({kind:'text',text,groups:['source']});
  const receipt=request=>{const body=JSON.parse(request.options.body),source=JSON.parse(body.line);return {record_id:body.request_id,request_id:body.request_id,row_number:body.row_number,
    row_sha256:crypto.createHash('sha256').update(body.line).digest('hex'),kind:source.kind,name:source.name||'Imported record',review:'draft',revision:1,source_revision:1};};
  const resolve=(request,data,status=201)=>request.resolve({ok:status>=200&&status<300,status,json:async()=>data});
  return {$,context,requests,notices,choose,row,manifest,receipt,resolve,selected,intents:()=>intents,invalidations:()=>invalidations,refreshes:()=>refreshes};
}
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Controller did not reach expected barrier');}
(async()=>{
  {
    const f=fixture();f.choose([f.row('first'),f.row('second')].join('\n'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    const request=f.requests[0];
    await f.$('bulk-select').dispatch('click');assert.equal(f.selected.size,0,'Programmatic click during acquisition is refused');
    await f.$('bulk-form').dispatch('submit');assert.equal(f.requests.length,1,'Repeated submit cannot start another loop');
    assert.equal(f.$('bulk-stop').disabled,false);
    await f.$('bulk-stop').dispatch('click');
    f.resolve(request,f.receipt(request));await importing;
    assert.equal(f.requests.length,1,'Stop after in-flight completion schedules no next admission');
    assert.match(f.$('bulk-status').textContent,/Stopped: 1 created.*1 not attempted/);
    assert.equal(f.$('bulk-start').disabled,false);assert.equal(f.refreshes(),1);
    assert.equal(f.selected.size,0,'Stop and successful admission never select implicitly');
    assert.equal(f.$('bulk-select').disabled,false,'Stopped batch retains confirmed successes');
    await f.$('bulk-select').dispatch('click');assert.equal(f.selected.size,1);
    const pair=f.selected.get(f.receipt(request).record_id);assert.equal(pair.revision,1);
    pair.revision=9;await f.$('bulk-select').dispatch('click');
    assert.equal(pair.revision,9,'Existing selected pair wins over repeated batch Add');
    assert.equal(vm.runInContext('[...bulkConfirmed.values()][0].revision',f.context),1,'Selected editor changes cannot mutate confirmed receipt Map');
    assert.equal(f.intents(),2);assert.equal(f.invalidations(),2,'Even all-overlap/repeated intent revokes release preview');
    f.selected.clear();await f.$('bulk-select').dispatch('click');assert.equal([...f.selected.values()][0].revision,1,'Confirmed pairs do not upgrade silently');
  }
  {
    const f=fixture();let finish;
    f.$('bulk-manifest').files=[{name:'assets.jsonl',size:1,arrayBuffer:()=>new Promise(resolve=>finish=resolve)}];
    const importing=f.$('bulk-form').dispatch('submit');await f.$('bulk-stop').dispatch('click');
    finish(new TextEncoder().encode(f.row('not admitted')).buffer);await importing;
    assert.equal(f.requests.length,0,'Cancel during manifest read must precede admission');
    assert.match(f.$('bulk-status').textContent,/Stopped: 0 created.*1 not attempted/);
  }
  {
    const f=fixture();let finish;
    f.context.readImportImage=()=>new Promise(resolve=>finish=resolve);
    f.choose(JSON.stringify({kind:'image',file:'chosen.png',groups:['s']}),[{name:'chosen.png',size:12}]);
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>finish);
    await f.$('bulk-stop').dispatch('click');finish('original bytes');await importing;
    assert.equal(f.requests.length,0,'Cancel during selected-file read must precede admission');
  }
  {
    const f=fixture();f.choose([f.row('unknown outcome'),f.row('later')].join('\n'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    const request=f.requests[0],saved=f.receipt(request);
    request.reject(Error('Response lost'));await importing;
    assert.match(f.$('bulk-status').textContent,/Paused.*1 uncertain.*1 not attempted/);
    assert.equal(f.requests.length,1,'Uncertain response must never auto-replay or start later rows');
    const checking=f.$('bulk-check').dispatch('click');await until(()=>f.requests.length===2);
    await f.$('bulk-check').dispatch('click');assert.equal(f.requests.length,2,'Repeated result checks are fenced');
    assert.equal(f.requests[1].url,'/api/workbench/import-result/'+saved.request_id);
    f.resolve(f.requests[1],{found:false},200);await checking;
    assert.match(f.$('bulk-status').textContent,/does not prove.*stopped/);
    assert.equal(vm.runInContext('bulkPending !== null',f.context),true);
    const confirmed=f.$('bulk-check').dispatch('click');await until(()=>f.requests.length===3);
    f.resolve(f.requests[2],{found:true,...saved,revision:3},200);await confirmed;
    assert.match(f.$('bulk-status').textContent,/saved result confirmed: 1 created.*0 uncertain.*1 not attempted/);
    assert.equal(vm.runInContext('bulkPending',f.context),null);
    assert.equal(f.requests.filter(request=>request.options?.method==='POST').length,1);
    assert.equal(f.selected.size,0);await f.$('bulk-select').dispatch('click');
    assert.equal(f.selected.get(saved.record_id).revision,3,'Saved-result confirmation observes its returned pair without replay');
  }
  {
    const f=fixture();f.choose([f.row('one'),f.row('two')].join('\n'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.resolve(f.requests[0],f.receipt(f.requests[0]));await until(()=>f.requests.length===2);
    f.resolve(f.requests[1],f.receipt(f.requests[1]));await importing;
    for(let i=0;i<4999;i++)f.selected.set('existing-'+i,{id:'existing-'+i,revision:7,source_revision:1});
    await f.$('bulk-select').dispatch('click');assert.equal(f.selected.size,4999,'Over-limit union rejects whole click before any writes');
    assert.equal(f.intents(),0);assert.match(f.$('bulk-selection-status').textContent,/5,000/);
    f.selected.delete('existing-0');await f.$('bulk-select').dispatch('click');assert.equal(f.selected.size,5000);
    const retained=JSON.stringify([...f.selected.values()]);
    f.choose(f.row('new failed batch'));const next=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===3);
    f.resolve(f.requests[2],{error:'rejected'},400);await next;
    assert.equal(f.$('bulk-select').disabled,true,'New batch retires previous confirmed results');
    await f.$('bulk-select').dispatch('click');assert.equal(JSON.stringify([...f.selected.values()]),retained);
  }
  for(const patch of [{revision:true},{revision:1.5},{revision:0},{revision:Number.MAX_SAFE_INTEGER+1},
    {source_revision:null},{source_revision:-1},{kind:'image'},{record_id:['a'.repeat(32)]}]){
    const f=fixture();f.choose(f.row('bad pair'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    const good=f.receipt(f.requests[0]);f.resolve(f.requests[0],{...good,...patch});await importing;
    assert.equal(f.$('bulk-select').disabled,true,'Invalid pair is uncertain, never selectable');
    const check=f.$('bulk-check').dispatch('click');await until(()=>f.requests.length===2);
    f.resolve(f.requests[1],{...good,found:'true'},200);await check;
    assert.equal(f.$('bulk-select').disabled,true,'Nonboolean found cannot establish confirmation');
    assert.equal(f.selected.size,0);
  }
  {
    const f=fixture();f.choose([f.row('original'),f.row('duplicate receipt ID')].join('\n'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    const first=f.receipt(f.requests[0]);f.resolve(f.requests[0],first);await until(()=>f.requests.length===2);
    const second={...f.receipt(f.requests[1]),record_id:first.record_id,revision:7};
    f.resolve(f.requests[1],second);await importing;
    assert.match(f.$('bulk-status').textContent,/1 created.*1 uncertain/);
    const checking=f.$('bulk-check').dispatch('click');await until(()=>f.requests.length===3);
    f.resolve(f.requests[2],{...second,found:true},200);await checking;
    assert.equal(vm.runInContext('bulkPending !== null',f.context),true,'Duplicate receipt ID remains uncertain');
    await f.$('bulk-select').dispatch('click');assert.equal(f.selected.size,1);
    assert.equal(f.selected.get(first.record_id).revision,1,'Duplicate ID cannot replace first confirmed pair');
  }
  {
    const f=fixture();f.choose([f.row('bad'),f.row('later')].join('\n'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.resolve(f.requests[0],{error:'storage failed'},500);await importing;
    assert.equal(f.requests.length,1,'Storage failure is fatal to scheduling');
    assert.match(f.$('bulk-status').textContent,/Paused after server failure: 0 created, 0 rejected, 1 uncertain.*1 not attempted/);
    assert.equal(vm.runInContext('bulkPending !== null',f.context),true,'A server failure is not proof of rollback');
  }
  {
    const f=fixture();
    f.choose(['{broken',JSON.stringify({kind:'image',file:'missing.png',groups:['s']}),JSON.stringify({kind:'image',file:'same.png',groups:['s']}),f.row('valid')].join('\n'),[{name:'same.png'},{name:'same.png'}]);
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    assert.equal(JSON.parse(f.requests[0].options.body).row_number,4,'Physical source numbering survives rejected rows');
    f.choose(f.row('changed controls'));
    f.resolve(f.requests[0],f.receipt(f.requests[0]));await importing;
    assert.match(f.$('bulk-status').textContent,/Complete: 1 created, 3 rejected/);
    assert.match(f.$('bulk-results').children[2].textContent,/ambiguous/);
  }
  {
    const f=fixture();
    assert.throws(()=>vm.runInContext('bulkManifest(new Uint8Array([255]).buffer)',f.context),/valid UTF-8/);
    assert.throws(()=>vm.runInContext('bulkManifest(new ArrayBuffer(8*1024*1024+1))',f.context),/8 MiB/);
    f.context.manyLines=new TextEncoder().encode('x\n'.repeat(1001)).buffer;
    assert.throws(()=>vm.runInContext('bulkManifest(manyLines)',f.context),/1,000 physical/);
    f.choose(f.row('invalid receipt'));
    const importing=f.$('bulk-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.resolve(f.requests[0],{...f.receipt(f.requests[0]),row_sha256:'f'.repeat(64)});await importing;
    assert.match(f.$('bulk-status').textContent,/1 uncertain/,'Wrong proof cannot claim a successful admission');
  }
  console.log('Bulk admission/stop/recovery plus explicit exact-pair selection, existing-pair precedence, atomic 5,000 limit, malformed confirmation, repeated invalidation and batch retirement passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
