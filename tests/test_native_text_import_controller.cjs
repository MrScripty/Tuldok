'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
class Element{
  constructor(){this.files=[];this.children=[];this.listeners={};this.disabled=false;this.textContent='';}
  addEventListener(type,fn){(this.listeners[type]||=[]).push(fn);}
  replaceChildren(){this.children=[];}append(item){this.children.push(item);}
  async dispatch(type){for(const fn of this.listeners[type]||[])await fn({preventDefault(){}});}
}
function fixture(){
  const elements=new Map(),requests=[];let refreshes=0;
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({console,TextEncoder,TextDecoder,Uint8Array,btoa,crypto:crypto.webcrypto,$,
    document:{createElement:()=>new Element()},notice:()=>{},refresh:async()=>refreshes++,
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  for(const file of ['bulk_import.js','native_text_import.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context);
  const file={name:'native.zip',size:3,arrayBuffer:async()=>Uint8Array.of(1,2,3).buffer};
  $('native-text-archive').files=[file];
  const rows=[1,2].map(number=>({metadata_path:'train/records.jsonl',row_number:number,row_sha256:String(number).repeat(64),token:'prepared-'+number}));
  const resolve=(request,data,status=200)=>request.resolve({ok:status>=200&&status<300,status,json:async()=>data});
  const prepared=()=>resolve(requests[0],{format:'canonical_v1',schema_version:1,archive_sha256:'a'.repeat(64),input_basis:'consumed_exported_text',upstream_original:'unavailable',rows});
  const receipt=request=>{const body=JSON.parse(request.options.body),row=rows.find(row=>row.token===body.token);return {record_id:'a'.repeat(32),request_id:body.request_id,row_number:row.row_number,row_sha256:row.row_sha256,kind:'text',review:'draft',name:'Imported label'};};
  return {$,context,requests,rows,file,resolve,prepared,receipt,refreshes:()=>refreshes};
}
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Missing expected controller barrier');}
(async()=>{
  {
    const f=fixture(),run=f.$('native-text-form').dispatch('submit');await until(()=>f.requests.length===1);
    await f.$('native-text-form').dispatch('submit');assert.equal(f.requests.length,1);
    f.prepared();await until(()=>f.requests.length===2);
    f.$('native-text-archive').files=[];await f.$('native-text-stop').dispatch('click');
    f.resolve(f.requests[1],f.receipt(f.requests[1]),201);await run;
    assert.equal(f.requests.length,2);assert.match(f.$('native-text-status').textContent,/Stopped: 1 created.*1 not attempted/);
    assert.equal(f.refreshes(),1);
  }
  for(const barrier of ['source','preparation']){
    const f=fixture();let release;
    if(barrier==='source')f.file.arrayBuffer=()=>new Promise(resolve=>release=resolve);
    const run=f.$('native-text-form').dispatch('submit');await until(()=>barrier==='source'?release:f.requests.length===1);
    await f.$('native-text-stop').dispatch('click');
    if(barrier==='source')release(Uint8Array.of(1,2,3).buffer);else f.prepared();
    await run;assert.equal(f.requests.length,barrier==='source'?0:1,'Stop precedes admission');
  }
  {
    const f=fixture();let finishRefresh;f.context.refresh=()=>new Promise(resolve=>finishRefresh=resolve);
    const run=f.$('native-text-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();
    await until(()=>f.requests.length===2);f.resolve(f.requests[1],f.receipt(f.requests[1]),201);
    await until(()=>f.requests.length===3);f.resolve(f.requests[2],f.receipt(f.requests[2]),201);
    await until(()=>finishRefresh);assert.equal(f.$('native-text-start').disabled,true,'Refresh is part of completion');
    await f.$('native-text-form').dispatch('submit');assert.equal(f.requests.length,3);
    finishRefresh();await run;assert.equal(f.$('native-text-start').disabled,false);
  }
  {
    const f=fixture(),run=f.$('native-text-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    const saved=f.receipt(f.requests[1]);f.requests[1].reject(Error('lost acknowledgement'));await run;
    await f.$('native-text-form').dispatch('submit');assert.equal(f.requests.length,2,'Uncertain outcome prevents replay');
    const check=f.$('native-text-check').dispatch('click');await until(()=>f.requests.length===3);
    await f.$('native-text-check').dispatch('click');assert.equal(f.requests.length,3);
    f.resolve(f.requests[2],{found:false});await check;
    assert.match(f.$('native-text-status').textContent,/does not prove.*stopped/);
    const again=f.$('native-text-check').dispatch('click');await until(()=>f.requests.length===4);
    f.resolve(f.requests[3],{found:true,...saved});await again;
    assert.match(f.$('native-text-status').textContent,/saved result confirmed: 1 created.*0 uncertain/);
    assert.equal(f.requests.filter(request=>request.url.endsWith('/row')).length,1);
  }
  for(const status of [400,409,500]){
    const f=fixture(),run=f.$('native-text-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    f.resolve(f.requests[1],{error:'controlled failure'},status);
    if(status!==500){await until(()=>f.requests.length===3);f.resolve(f.requests[2],f.receipt(f.requests[2]),201);}
    await run;assert.match(f.$('native-text-status').textContent,status===500?/Paused.*1 uncertain.*1 not attempted/:/Complete: 1 created, 1 rejected/);
  }
  {
    const f=fixture();f.rows[0]={...f.rows[0],error:'Unsupported native task'};
    const run=f.$('native-text-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    assert.equal(JSON.parse(f.requests[1].options.body).token,f.rows[1].token);
    f.resolve(f.requests[1],f.receipt(f.requests[1]),201);await run;
    assert.match(f.$('native-text-status').textContent,/Complete: 1 created, 1 rejected/);
  }
  console.log('Native classification controller: source/preparation/in-flight Stop, repeated actions, snapshot, refresh barrier, partial outcomes and response-loss reconciliation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
