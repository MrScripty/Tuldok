'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
class Element{
  constructor(){this.files=[];this.children=[];this.listeners={};this.disabled=false;this.textContent='';}
  addEventListener(type,fn){(this.listeners[type]||=[]).push(fn);}
  replaceChildren(){this.children=[];}append(item){this.children.push(item);}
  async dispatch(type){for(const fn of this.listeners[type]||[])await fn({preventDefault(){}});}
}
function fixture(){
  const elements=new Map(),requests=[],lifecycle={};let refreshes=0;
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({console,TextEncoder,TextDecoder,Uint8Array,btoa,crypto:crypto.webcrypto,$,window:{addEventListener:(event,fn)=>lifecycle[event]=fn},
    document:{createElement:()=>new Element()},notice:()=>{},refresh:async()=>refreshes++,
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  for(const file of ['native_detection_import.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context);
  const file={name:'native.zip',size:3,arrayBuffer:async()=>Uint8Array.of(1,2,3).buffer};
  $('native-detection-archive').files=[file];
  const rows=[1,2].map(number=>({metadata_path:'manifest.json',row_number:number,row_sha256:String(number).repeat(64),token:'prepared-'+number}));
  const resolve=(request,data,status=200)=>request.resolve({ok:status>=200&&status<300,status,json:async()=>data});
  const prepared=()=>resolve(requests[0],{format:'canonical_v1',schema_version:1,archive_sha256:'a'.repeat(64),input_basis:'consumed_exported_png',upstream_original:'unavailable',upstream_graph:'selected_declared_links_only',rows});
  const receipt=request=>{const body=JSON.parse(request.options.body),row=rows.find(row=>row.token===body.token);return {record_id:'a'.repeat(32),request_id:body.request_id,row_number:row.row_number,row_sha256:row.row_sha256,kind:'image',review:'draft',name:'Imported label'};};
  return {$,context,requests,rows,file,resolve,prepared,receipt,lifecycle,refreshes:()=>refreshes};
}
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Missing expected controller barrier');}
(async()=>{
  {
    const f=fixture(),run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);
    await f.$('native-detection-form').dispatch('submit');assert.equal(f.requests.length,1);
    f.prepared();await until(()=>f.requests.length===2);
    f.$('native-detection-archive').files=[];await f.$('native-detection-stop').dispatch('click');
    f.resolve(f.requests[1],f.receipt(f.requests[1]),201);await run;
    assert.equal(f.requests.length,2);assert.match(f.$('native-detection-status').textContent,/Stopped: 1 created.*1 not attempted/);
    assert.equal(f.refreshes(),1);
  }
  for(const barrier of ['source','preparation']){
    const f=fixture();let release;
    if(barrier==='source')f.file.arrayBuffer=()=>new Promise(resolve=>release=resolve);
    const run=f.$('native-detection-form').dispatch('submit');await until(()=>barrier==='source'?release:f.requests.length===1);
    await f.$('native-detection-stop').dispatch('click');
    if(barrier==='source')release(Uint8Array.of(1,2,3).buffer);else f.prepared();
    await run;assert.equal(f.requests.length,barrier==='source'?0:1,'Stop precedes admission');
  }
  {
    const f=fixture();let finishRefresh;f.context.refresh=()=>new Promise(resolve=>finishRefresh=resolve);
    const run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();
    await until(()=>f.requests.length===2);f.resolve(f.requests[1],f.receipt(f.requests[1]),201);
    await until(()=>f.requests.length===3);f.resolve(f.requests[2],f.receipt(f.requests[2]),201);
    await until(()=>finishRefresh);assert.equal(f.$('native-detection-start').disabled,true,'Refresh is part of completion');
    await f.$('native-detection-form').dispatch('submit');assert.equal(f.requests.length,3);
    finishRefresh();await run;assert.equal(f.$('native-detection-start').disabled,false);
  }
  {
    const f=fixture(),run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    const saved=f.receipt(f.requests[1]);f.requests[1].reject(Error('lost acknowledgement'));await run;
    await f.$('native-detection-form').dispatch('submit');assert.equal(f.requests.length,2,'Uncertain outcome prevents replay');
    const check=f.$('native-detection-check').dispatch('click');await until(()=>f.requests.length===3);
    await f.$('native-detection-check').dispatch('click');assert.equal(f.requests.length,3);
    f.resolve(f.requests[2],{found:false});await check;
    assert.match(f.$('native-detection-status').textContent,/does not prove.*stopped/);
    const again=f.$('native-detection-check').dispatch('click');await until(()=>f.requests.length===4);
    f.resolve(f.requests[3],{found:true,...saved});await again;
    assert.match(f.$('native-detection-status').textContent,/saved admission confirmed: 1 created.*0 uncertain/);
    assert.equal(f.requests.filter(request=>request.url.endsWith('/row')).length,1);
  }
  for(const status of [400,409,500]){
    const f=fixture(),run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    f.resolve(f.requests[1],{error:'controlled failure'},status);
    if(status!==500){await until(()=>f.requests.length===3);f.resolve(f.requests[2],f.receipt(f.requests[2]),201);}
    await run;assert.match(f.$('native-detection-status').textContent,status===500?/Paused.*1 uncertain.*1 not attempted/:/Complete: 1 created, 1 rejected/);
  }
  for(const barrier of ['source','preparation','admission']){
    const f=fixture();let release;
    if(barrier==='source')f.file.arrayBuffer=()=>new Promise(resolve=>release=resolve);
    const run=f.$('native-detection-form').dispatch('submit');
    await until(()=>barrier==='source'?release:f.requests.length===1);
    if(barrier==='admission'){f.prepared();await until(()=>f.requests.length===2);}
    f.lifecycle.pagehide();
    if(barrier==='source')release(Uint8Array.of(1,2,3).buffer);
    else if(barrier==='preparation')f.prepared();
    else f.resolve(f.requests[1],f.receipt(f.requests[1]),201);
    await run;
    assert.equal(f.refreshes(),0,'Departed work cannot refresh the collection');
    assert.equal(f.requests.length,barrier==='source'?0:barrier==='preparation'?1:2);
    if(barrier==='admission'){
      assert.match(f.$('native-detection-status').textContent,/Paused.*1 uncertain/);
      await f.$('native-detection-form').dispatch('submit');assert.equal(f.requests.length,2,'Departed POST remains uncertain without replay');
      const check=f.$('native-detection-check').dispatch('click');await until(()=>f.requests.length===3);
      f.resolve(f.requests[2],{found:true,...f.receipt(f.requests[1])});await check;
      assert.match(f.$('native-detection-status').textContent,/saved admission confirmed/);
    }
  }
  {
    const f=fixture(),run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    const saved=f.receipt(f.requests[1]);f.requests[1].reject(Error('lost'));await run;
    const check=f.$('native-detection-check').dispatch('click');await until(()=>f.requests.length===3);
    f.lifecycle.pagehide();f.resolve(f.requests[2],{found:true,...saved});await check;
    assert.equal(f.$('native-detection-start').disabled,true,'Departed GET cannot resolve pending creation');
    assert.match(f.$('native-detection-status').textContent,/uncertain after page departure/);
  }
  {
    const f=fixture();f.file.arrayBuffer=async()=>Uint8Array.of(1,2).buffer;
    await f.$('native-detection-form').dispatch('submit');assert.equal(f.requests.length,0);
    assert.match(f.$('native-detection-status').textContent,/size changed/);
  }
  {
    const f=fixture();f.rows[1].row_number=99;
    const run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await run;
    assert.equal(f.requests.length,1,'Validate all prepared rows before the first admission');
  }
  {
    const f=fixture(),run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    let finishJson;f.requests[1].resolve({ok:true,status:201,json:()=>new Promise(resolve=>finishJson=resolve)});
    await until(()=>finishJson);f.lifecycle.pagehide();finishJson(f.receipt(f.requests[1]));await run;
    assert.match(f.$('native-detection-status').textContent,/Paused.*1 uncertain/);
    assert.equal(f.requests.length,2);assert.equal(f.refreshes(),0);
  }
  {
    const f=fixture();let finishRefresh,guard;
    f.context.refresh=value=>{guard=value;return new Promise(resolve=>finishRefresh=resolve);};
    const run=f.$('native-detection-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    f.resolve(f.requests[1],f.receipt(f.requests[1]),201);await until(()=>f.requests.length===3);f.resolve(f.requests[2],f.receipt(f.requests[2]),201);
    await until(()=>finishRefresh);assert.equal(guard(),true);f.lifecycle.pagehide();assert.equal(guard(),false,'Lifecycle guard fences an already held refresh');
    finishRefresh();await run;assert.match(f.$('native-detection-status').textContent,/Stopped after page departure/);
  }
  console.log('Native detection controller: source/preparation/in-flight Stop, repeated actions, snapshot, refresh barrier, partial outcomes and response-loss reconciliation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
