// Independent lifecycle checks; real DOM ownership is exercised in Chromium.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements=new Map(),listeners={},requests=[];
const $=id=>{if(!elements.has(id))elements.set(id,{value: id.endsWith('field')?'velocity_x':'0',files:[],textContent:'',addEventListener:(name,fn)=>elements.get(id).events[name]=fn,events:{}});return elements.get(id);};
const ctx=vm.createContext({$,AbortController,Uint8Array,btoa,encodeURIComponent,window:{addEventListener:(event,fn)=>listeners[event]=fn},fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/sequence-probe.js'),'utf8'),ctx);
const run=s=>vm.runInContext(s,ctx),flush=()=>new Promise(r=>setImmediate(r)),show=revision=>run(`sequenceProbeShown({id:'record',kind:'sequence',revision:${revision},source_revision:1})`);
const click=()=>$('sequence-probe-read').events.click(),reply=(q,result)=>q.resolve({ok:true,json:async()=>({id:'record',source_revision:1,...result})});
(async()=>{
  show(1);let p=click(),old=requests.shift();assert.equal(JSON.parse(old.options.body).revision,1);
  show(2);assert.equal(old.options.signal.aborted,true);let newer=click(),q=requests.shift();reply(q,{revision:2});await newer;reply(old,{revision:1});await p;assert.equal(JSON.parse($('sequence-probe-output').textContent).revision,2);
  p=click();q=requests.shift();let finishJson;q.resolve({ok:true,json:()=>new Promise(r=>finishJson=r)});await flush();$('sequence-probe-field').events.change();finishJson({late:true});await p;assert.equal($('sequence-probe-output').textContent,'');
  let fileResolve;$('sequence-probe-controls').files=[{size:2,arrayBuffer:()=>new Promise(r=>fileResolve=r)}];p=click();$('sequence-probe-controls').events.change();fileResolve(new Uint8Array([123,125]).buffer);await p;assert.equal(requests.length,0);
  $('sequence-probe-controls').files=[];p=click();q=requests.shift();run("sequenceProbeShown({kind:'text'})");assert.equal(q.options.signal.aborted,true);reply(q,{stale:true});await p;assert.equal($('sequence-probe').hidden,true);assert.equal($('sequence-probe-output').textContent,'');
  show(1);p=click();q=requests.shift();listeners.pagehide();assert.equal(q.options.signal.aborted,true);reply(q,{stale:true});await p;assert.equal($('sequence-probe-output').textContent,'');
  show(1);$('sequence-probe-controls').files=[{size:65537}];await click();assert.match($('sequence-probe-status').textContent,/65536/);assert.equal(requests.length,0);
  console.log('Native sequence inspector controller PASS: revision/record/input/file/departure/late JSON fencing, abort and size admission.');
})().catch(error=>{console.error(error);process.exitCode=1;});
