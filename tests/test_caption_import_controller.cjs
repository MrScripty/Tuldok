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
  const context=vm.createContext({console,TextEncoder,TextDecoder,crypto:crypto.webcrypto,$,
    document:{createElement:()=>new Element()},notice:()=>{},refresh:async()=>refreshes++,
    readImportImage:async()=> 'authored image',
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  for(const file of ['bulk_import.js','caption_import.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context);
  const source=(relative,text='{}')=>({name:relative.split('/').at(-1),webkitRelativePath:'corpus/'+relative,size:Buffer.byteLength(text),arrayBuffer:async()=>new TextEncoder().encode(text).buffer});
  const rows=[1,2].map(number=>({asset:'train/'+String(number).repeat(32)+'.png',row_number:number,row_sha256:'c'.repeat(64),token:'prepared-row-'+number}));
  const files=['manifest.json','train/metadata.jsonl','val/metadata.jsonl','test/metadata.jsonl',...rows.map(row=>row.asset)].map(relative=>source(relative));
  $('caption-folder').files=files;
  const resolve=(request,data,status=200)=>request.resolve({ok:status>=200&&status<300,status,json:async()=>data});
  const prepared=()=>resolve(requests[0],{format:'image_caption_v1',rows});
  const receipt=request=>{const body=JSON.parse(request.options.body),row=rows.find(row=>row.token===body.token);return {record_id:'a'.repeat(32),request_id:body.request_id,row_number:row.row_number,row_sha256:row.row_sha256,kind:'image',review:'draft',name:'Caption image'};};
  return {$,context,requests,rows,files,source,resolve,prepared,receipt,refreshes:()=>refreshes};
}
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Missing expected controller barrier');}
(async()=>{
  {
    const f=fixture(),run=f.$('caption-form').dispatch('submit');await until(()=>f.requests.length===1);
    await f.$('caption-form').dispatch('submit');assert.equal(f.requests.length,1);
    f.prepared();await until(()=>f.requests.length===2);
    f.$('caption-folder').files=[];await f.$('caption-stop').dispatch('click');
    f.resolve(f.requests[1],f.receipt(f.requests[1]),201);await run;
    assert.equal(f.requests.length,2);assert.match(f.$('caption-status').textContent,/Stopped: 1 created.*1 not attempted/);
    assert.equal(f.refreshes(),1);
  }
  {
    const f=fixture();let release;
    f.files[0].arrayBuffer=()=>new Promise(resolve=>release=resolve);
    const run=f.$('caption-form').dispatch('submit');await until(()=>release);
    await f.$('caption-stop').dispatch('click');release(new TextEncoder().encode('{}').buffer);await run;
    assert.equal(f.requests.length,0,'Stop during source read precedes even preparation');
  }
  {
    const f=fixture(),run=f.$('caption-form').dispatch('submit');await until(()=>f.requests.length===1);
    await f.$('caption-stop').dispatch('click');f.prepared();await run;
    assert.equal(f.requests.length,1,'Read-only preparation response cannot schedule after stop');
  }
  {
    const f=fixture();let finish;f.context.readImportImage=()=>new Promise(resolve=>finish=resolve);
    const run=f.$('caption-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>finish);
    await f.$('caption-stop').dispatch('click');finish('bytes');await run;assert.equal(f.requests.length,1);
  }
  {
    const f=fixture();f.$('caption-folder').files=f.files.filter(file=>!file.webkitRelativePath.endsWith(f.rows[0].asset));
    const run=f.$('caption-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    assert.equal(JSON.parse(f.requests[1].options.body).asset,f.rows[1].asset);
    f.resolve(f.requests[1],f.receipt(f.requests[1]),201);await run;
    assert.match(f.$('caption-status').textContent,/Complete: 1 created, 1 rejected/);
  }
  {
    const f=fixture(),run=f.$('caption-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    const saved=f.receipt(f.requests[1]);f.requests[1].reject(Error('lost response'));await run;
    assert.match(f.$('caption-status').textContent,/Paused.*1 uncertain.*1 not attempted/);
    const check=f.$('caption-check').dispatch('click');await until(()=>f.requests.length===3);
    await f.$('caption-check').dispatch('click');assert.equal(f.requests.length,3);
    f.resolve(f.requests[2],{found:false});await check;
    assert.match(f.$('caption-status').textContent,/does not prove.*stopped/);
    const again=f.$('caption-check').dispatch('click');await until(()=>f.requests.length===4);
    f.resolve(f.requests[3],{found:true,...saved});await again;
    assert.match(f.$('caption-status').textContent,/saved result confirmed: 1 created.*0 uncertain/);
    assert.equal(f.requests.filter(request=>request.url.endsWith('/row')).length,1,'No automatic replay');
  }
  for(const status of [400,409,500]){
    const f=fixture(),run=f.$('caption-form').dispatch('submit');await until(()=>f.requests.length===1);f.prepared();await until(()=>f.requests.length===2);
    f.resolve(f.requests[1],{error:'controlled error'},status);
    if(status!==500){await until(()=>f.requests.length===3);f.resolve(f.requests[2],f.receipt(f.requests[2]),201);}
    await run;
    assert.match(f.$('caption-status').textContent,status===500?/Paused.*1 uncertain.*1 not attempted/:/Complete: 1 created, 1 rejected/);
  }
  for(const type of ['ambiguous','unsafe','missing','invalid-utf8']){
    const f=fixture();
    if(type==='ambiguous')f.files.push(f.files[0]);
    if(type==='unsafe')f.files[0].webkitRelativePath='corpus/../manifest.json';
    if(type==='missing')f.files.shift();
    if(type==='invalid-utf8'){f.files[0].size=1;f.files[0].arrayBuffer=async()=>Uint8Array.of(255).buffer;}
    await f.$('caption-form').dispatch('submit');assert.equal(f.requests.length,0);
  }
  console.log('Caption controller source/preparation/image/in-flight stop barriers, repeated controls, snapshots, paths, UTF-8, typed outcomes and lost-response lookup passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
