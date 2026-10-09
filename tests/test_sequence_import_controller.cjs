// Synthetic receipt and lifecycle controls. Real DOM/API ownership has a separate gate.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
function fixture(){
 const elements=new Map(),listeners={},requests=[],refreshes=[];
 const $=id=>{if(!elements.has(id))elements.set(id,{files:[],value:'',textContent:'',disabled:false,events:{},addEventListener(e,f){this.events[e]=f;},querySelectorAll(){return [$('sequence-import-start')];}});return elements.get(id);};
 const ctx=vm.createContext({$,console,Uint8Array,atob,btoa,crypto:crypto.webcrypto,window:{addEventListener:(e,f)=>listeners[e]=f},api:(route,body)=>new Promise(resolve=>requests.push({route,body,resolve})),refresh:async live=>refreshes.push(live())});
 vm.runInContext(fs.readFileSync('static/sequences.js','utf8'),ctx);
 const file=(name,raw)=>({name,size:raw.length,arrayBuffer:async()=>Uint8Array.from(raw).buffer});
 $('sequence-run').files=[file('run.json',Buffer.from('run'))];$('sequence-frames').files=[file('frames.jsonl',Buffer.from('frames'))];$('sequence-controls').files=[file('controls.json',Buffer.from('controls'))];$('sequence-name').value='Original name';$('sequence-group').value=' original ';$('sequence-rights').value='Original rights';
 const submit=()=>$('sequence-import-form').events.submit({preventDefault(){}});
 const receipt=q=>({id:'a'.repeat(32),kind:'sequence',review:'draft',annotation:null,revision:1,source_revision:1,name:q.body.name,sequence:{run_sha256:crypto.createHash('sha256').update(Buffer.from(q.body.files['run.json'],'base64')).digest('hex'),manifest:{version:2,frames_sha256:crypto.createHash('sha256').update(Buffer.from(q.body.files['frames.jsonl'],'base64')).digest('hex')},controls:{sha256:crypto.createHash('sha256').update(Buffer.from(q.body.files['controls.json'],'base64')).digest('hex')}}});
 return {$,listeners,requests,refreshes,submit,receipt,ctx};
}
async function until(fn){const deadline=Date.now()+2000;while(Date.now()<deadline){if(fn())return;await new Promise(r=>setTimeout(r,5));}assert.fail('Bounded controller await timed out');}
async function request(f){await until(()=>f.requests.length===1);return f.requests[0];}
(async()=>{
 let f=fixture(),p=f.submit(),q=await request(f);await f.submit();assert.equal(f.requests.length,1);q.resolve(f.receipt(q));await p;assert.deepEqual(f.refreshes,[true]);assert.match(f.$('sequence-import-status').textContent,/9 frames, unreviewed/);
 f=fixture();let finish;f.$('sequence-run').files[0].arrayBuffer=()=>new Promise(r=>finish=r);p=f.submit();f.$('sequence-controls').files=[];f.$('sequence-name').value='Changed';f.$('sequence-group').value='Changed';f.$('sequence-rights').value='Changed';finish(Uint8Array.from(Buffer.from('run')).buffer);q=await request(f);assert.equal(q.body.name,'Original name');assert.equal(q.body.groups[0],'original');assert.equal(q.body.rights,'Original rights');assert.ok(q.body.files['controls.json']);q.resolve(f.receipt(q));await p;
 f=fixture();f.$('sequence-run').files[0].arrayBuffer=()=>new Promise(r=>finish=r);p=f.submit();f.listeners.pagehide();finish(Uint8Array.from(Buffer.from('run')).buffer);await p;assert.equal(f.requests.length,0);assert.equal(f.refreshes.length,0);
 f=fixture();p=f.submit();q=await request(f);f.listeners.pagehide();const status=f.$('sequence-import-status').textContent;q.resolve(f.receipt(q));await p;assert.equal(f.$('sequence-import-status').textContent,status);assert.equal(f.refreshes.length,0);
 f=fixture();p=f.submit();q=await request(f);f.listeners.pagehide();f.listeners.pageshow({persisted:true});assert.equal(f.$('sequence-import-start').disabled,false);let newer=f.submit();await until(()=>f.requests.length===2);const fresh=f.requests[1];q.resolve(f.receipt(q));await p;assert.equal(vm.runInContext('sequenceImportBusy',f.ctx),true);assert.equal(f.refreshes.length,0);fresh.resolve(f.receipt(fresh));await newer;assert.deepEqual(f.refreshes,[true]);
 for(const mutate of [r=>r.review='human_reviewed',r=>r.sequence.controls.sha256='0'.repeat(64),r=>r.sequence.manifest.frames_sha256='0'.repeat(64),r=>r.sequence.run_sha256='0'.repeat(64),r=>r.sequence.manifest.version=1,r=>r.revision=2]){
  f=fixture();p=f.submit();q=await request(f);const r=f.receipt(q);mutate(r);q.resolve(r);await p;assert.match(f.$('sequence-import-status').textContent,/Uncertain/);assert.equal(f.refreshes.length,0);assert.equal(f.requests.length,1);
 }
 f=fixture();f.$('sequence-controls').files[0].size=65537;await f.submit();assert.equal(f.requests.length,0);assert.match(f.$('sequence-import-status').textContent,/65536/);
 console.log('Single trajectory import controller PASS: three-file hashes, typed receipt, snapshot before reads, duplicate submit, departure before POST and late response, no automatic replay. Synthetic receipts only.');
})().catch(e=>{console.error(e);process.exitCode=1;});
