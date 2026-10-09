// Ordering/proof controls; native parser/persistence and real browser are separate.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
class Element {
  constructor(){this.files=[];this.value='';this.children=[];this.listeners={};this.disabled=false;this.textContent='';}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
  replaceChildren(){this.children=[];}
  append(item){this.children.push(item);}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){}});}
}
function fixture() {
  const elements=new Map(),requests=[],notices=[],listeners=new Map();let reads=0,refreshes=0;
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({console,Uint8Array,atob,btoa,crypto:crypto.webcrypto,$,
    document:{createElement:()=>new Element()},window:{addEventListener:(event,fn)=>listeners.set(event,fn)},
    notice:(...args)=>notices.push(args),refresh:async()=>{refreshes++;},
    sequenceFile:async(file,maximum,name)=>{
      if(!file || file.name!==name || !file.size || file.size>maximum)throw Error('Choose '+name+' within its per-file limit.');
      return Buffer.from(await file.arrayBuffer()).toString('base64');
    },fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/sequence-batch.js'),'utf8'),context);
  const file=(name,raw)=>({name:name.split('/').at(-1),webkitRelativePath:name,size:Buffer.byteLength(raw),arrayBuffer:async()=>{reads++;return Buffer.from(raw);}});
  const pair=(name,root='corpus')=>[file(`${root}/${name}/run.json`,'run '+name),file(`${root}/${name}/frames.jsonl`,'frames '+name)];
  const choose=(...names)=>{$('sequence-batch-folder').files=names.flatMap(name=>pair(name));};
  const receipt=request=>{
    const body=JSON.parse(request.options.body),digest=raw=>crypto.createHash('sha256').update(Buffer.from(raw,'base64')).digest('hex');
    return {format:'tuldok_rheon_batch_v1',record_id:'a'.repeat(32),kind:'sequence',name:body.name,
      ...Object.fromEntries(['request_id','batch_name','item_name','item_index'].map(key=>[key,body[key]])),
      run_sha256:digest(body.files['run.json']),frames_sha256:digest(body.files['frames.jsonl'])};
  };
  const resolve=(request,data,status=201)=>request.resolve({ok:status>=200&&status<300,status,json:async()=>data});
  return {$,context,requests,notices,file,pair,choose,receipt,resolve,hide:()=>listeners.get('pagehide')(),reads:()=>reads,refreshes:()=>refreshes,
    state:expression=>vm.runInContext(expression,context)};
}
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Controller barrier not reached');}
(async()=>{
  {
    const f=fixture();
    for(const files of [[],f.pair('one').slice(0,1),[...f.pair('one'),f.pair('one')[0]],
      [...f.pair('one'),...f.pair('two','other')],f.pair('..'),[f.file('corpus/one/extra.json','x')],
      Array.from({length:33},(_,i)=>f.pair(String(i))).flat(),
      [{...f.pair('one')[0],size:41*1024*1024},f.pair('one')[1]],
      [...f.pair('a-valid'),{...f.pair('b-oversized')[0],size:65537},f.pair('b-oversized')[1]],
      [...f.pair('a-valid'),f.pair('b-oversized')[0],{...f.pair('b-oversized')[1],size:2097153}],
      f.pair('\ud800'),
      [{...f.pair('one')[0],size:0},f.pair('one')[1]]]) {
      f.$('sequence-batch-folder').files=files;await f.$('sequence-batch-form').dispatch('submit');
      assert.equal(f.requests.length,0);assert.equal(f.reads(),0,'Pairing/count/aggregate bounds precede all contents reads');
    }
  }
  {
    const f=fixture();f.choose('a','b');const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    await f.$('sequence-batch-form').dispatch('submit');assert.equal(f.requests.length,1);
    await f.$('sequence-batch-stop').dispatch('click');f.resolve(f.requests[0],f.receipt(f.requests[0]));await running;
    assert.equal(f.requests.length,1);assert.match(f.$('sequence-batch-status').textContent,/Stopped: 1 created.*1 not attempted/);
  }
  for(const holdName of ['run.json','frames.jsonl']) {
    const f=fixture();f.choose('a','b');let finish;
    const file=f.$('sequence-batch-folder').files.find(file=>file.name===holdName);file.arrayBuffer=()=>new Promise(resolve=>finish=resolve);
    const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>finish);
    await f.$('sequence-batch-stop').dispatch('click');finish(Buffer.from('held file'));await running;
    assert.equal(f.requests.length,0,'Stop after '+holdName+' read precedes every POST');
  }
  {
    const f=fixture();f.choose('a','b');f.$('sequence-batch-rights').value='Frozen permission';
    const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.choose('changed');f.$('sequence-batch-rights').value='Changed controls';
    f.resolve(f.requests[0],{error:'Malformed native bundle'},400);await until(()=>f.requests.length===2);
    const second=JSON.parse(f.requests[1].options.body);assert.equal(second.item_name,'b');assert.equal(second.rights,'Frozen permission');
    f.resolve(f.requests[1],f.receipt(f.requests[1]));await running;
    assert.match(f.$('sequence-batch-status').textContent,/Complete: 1 created, 1 rejected/);
  }
  {
    const f=fixture();f.choose('a','b');const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    const saved=f.receipt(f.requests[0]);f.requests[0].reject(Error('Committed response lost'));await running;
    assert.equal(f.requests.length,1);assert.match(f.$('sequence-batch-status').textContent,/Paused.*1 uncertain.*1 not attempted/);
    await f.$('sequence-batch-form').dispatch('submit');assert.equal(f.requests.length,1);
    for(const data of [{found:false},{found:'false',...saved},{found:true,...saved,record_id:[saved.record_id]},
      {found:true,...saved,frames_sha256:'f'.repeat(64)},{found:true,...saved}]) {
      const check=f.$('sequence-batch-check').dispatch('click');await until(()=>f.requests.at(-1).options===undefined);
      const request=f.requests.at(-1);await f.$('sequence-batch-check').dispatch('click');
      assert.ok(request.url.endsWith(saved.request_id));f.resolve(request,data,200);await check;
      if(data.found===false)assert.match(f.$('sequence-batch-status').textContent,/does not prove.*stopped/);
      if(data.frames_sha256==='f'.repeat(64))assert.equal(f.state('!!sequenceBatchPending'),true);
      if(typeof data.found!=='boolean' || Array.isArray(data.record_id))assert.equal(f.state('!!sequenceBatchPending'),true);
    }
    assert.equal(f.state('sequenceBatchPending'),null);
    assert.equal(f.requests.filter(request=>request.options?.method==='POST').length,1,'GET confirmation never replays/resumes');
  }
  for(const mode of ['server','proof']) {
    const f=fixture();f.choose('a','b');const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.resolve(f.requests[0],mode==='server'?{error:'storage failed'}:{...f.receipt(f.requests[0]),run_sha256:'f'.repeat(64)},mode==='server'?500:201);
    await running;assert.equal(f.requests.length,1);assert.equal(f.state('!!sequenceBatchPending'),true);
    await f.$('sequence-batch-dismiss').dispatch('click');assert.equal(f.state('sequenceBatchPending'),null);
    assert.match(f.$('sequence-batch-status').textContent,/no rollback/);
  }
  {
    const f=fixture();f.choose('old');let finish;
    f.$('sequence-batch-folder').files[0].arrayBuffer=()=>new Promise(resolve=>finish=resolve);
    const old=f.$('sequence-batch-form').dispatch('submit');await until(()=>finish);f.hide();
    f.choose('new');const newer=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    finish(Buffer.from('old read'));await old;assert.equal(f.requests.length,1);
    f.resolve(f.requests[0],f.receipt(f.requests[0]));await newer;
    assert.match(f.$('sequence-batch-results').children[0].textContent,/\(new\).*created/);
  }
  {
    const f=fixture();f.choose('a','b');const old=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    const saved=f.receipt(f.requests[0]);f.hide();f.resolve(f.requests[0],saved);await old;
    assert.equal(f.requests.length,1);assert.equal(f.state('!!sequenceBatchPending'),true);
    assert.match(f.$('sequence-batch-status').textContent,/1 uncertain/);
    const oldCheck=f.$('sequence-batch-check').dispatch('click');await until(()=>f.requests.length===2);
    f.hide();f.resolve(f.requests[1],{found:true,...saved},200);await oldCheck;
    assert.equal(f.state('!!sequenceBatchPending'),true,'Late departed check cannot clear pending identity');
    const check=f.$('sequence-batch-check').dispatch('click');await until(()=>f.requests.length===3);
    f.resolve(f.requests[2],{found:true,...saved},200);await check;
    assert.equal(f.state('sequenceBatchPending'),null);assert.equal(f.requests.length,3);
  }
  {
    const f=fixture();f.choose('a');f.context.refresh=async()=>{throw Error('collection unavailable');};
    const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.resolve(f.requests[0],f.receipt(f.requests[0]));await running;
    assert.match(f.$('sequence-batch-status').textContent,/1 created, 0 rejected, 0 uncertain/);
    assert.equal(f.state('sequenceBatchPending'),null);assert.match(f.notices.at(-1)[0],/remain retained/);
  }
  {
    const f=fixture();f.choose('a');let finish,guard;
    f.context.refresh=callback=>new Promise(resolve=>{guard=callback;finish=resolve;});
    const running=f.$('sequence-batch-form').dispatch('submit');await until(()=>f.requests.length===1);
    f.resolve(f.requests[0],f.receipt(f.requests[0]));await until(()=>finish);assert.equal(guard(),true);
    f.hide();assert.equal(guard(),false,'Departed refresh has no publication authority');finish();await running;
  }
  {
    // The actual shared refresh must retire query ownership even if its batch departs.
    const f=fixture();let finish;
    Object.assign(f.context,{URLSearchParams,exactFilters:[],offset:0,queryEpoch:0,page:null,
      allowed:true,curationPending:false,curationInvalidate:()=>{f.context.curationPending=true;},
      curationQueryFinished:()=>{f.context.curationPending=false;},api:()=>new Promise(resolve=>finish=resolve)});
    const source=fs.readFileSync(path.join(__dirname,'../static/workbench.js'),'utf8');
    vm.runInContext(source.match(/async function refresh[\s\S]*?\n}\n/)[0],f.context);
    const running=vm.runInContext('refresh(()=>allowed)',f.context);await until(()=>finish);
    f.context.allowed=false;finish({items:[],total:0,analysis:{}});await running;
    assert.equal(f.context.curationPending,false,'Departed query still retires its diagnostics ownership');
    assert.equal(f.context.page,null,'Departed query cannot publish its collection');
  }
  console.log('Sequence batch controller: bounded pairing, frozen files/metadata, stop/departure/read/POST/check/refresh fences, partial outcomes and exact GET-only recovery passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
