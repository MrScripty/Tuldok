'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const code=fs.readFileSync(path.join(__dirname,'../static/retrieval.js'),'utf8');
const hash=text=>crypto.createHash('sha256').update(text).digest('hex');
const tick=()=>new Promise(r=>setImmediate(r));
function setup(digest=crypto.webcrypto.subtle.digest.bind(crypto.webcrypto.subtle)) {
 const els=new Map(),events={},requests=[],controls=[{disabled:false}],refreshes=[];
 const $=id=>{if(!els.has(id))els.set(id,{value:'',textContent:'',events:{},addEventListener:(n,f)=>els.get(id).events[n]=f,querySelectorAll:()=>controls});return els.get(id);};
 const context=vm.createContext({$,TextEncoder,Uint8Array,crypto:{subtle:{digest}},window:{addEventListener:(n,f)=>events[n]=f},markDirty:()=>{throw Error('Import mutated editor');},refresh:async live=>{if(live())refreshes.push(true);},fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
 vm.runInContext(code,context);
 const refs=[{id:'a'.repeat(32),revision:2,source_revision:1}];
 $('retrieval-import-text').value=' Frozen cafe\u0301 query\r\n';$('retrieval-import-name').value='\u0085query\u001c';$('retrieval-import-group').value='\u0085source\u001c';$('retrieval-import-rights').value='\u0085unknown\u001c';$('retrieval-import-refs').value=JSON.stringify(refs);
 const submit=()=>$('retrieval-import-form').events.submit({preventDefault(){}});
 const receipt=body=>{const text=body.text.replace(/\r\n?/g,'\n').normalize('NFC');return {id:'b'.repeat(32),kind:'text',task:'text_classification',source_available:true,review:'draft',annotation:null,revision:1,source_revision:1,text,content_hash:hash(text),source_sha256:hash(body.text),name:'query',groups:['source'],parents:refs.map(r=>r.id),provenance:{rights:'unknown',acquisition:{format:'text_retrieval_query_v1',declared_positive_refs:refs}}};};
 const busy=()=>vm.runInContext('retrievalImportBusy',context);
 return {$,events,requests,controls,refreshes,context,refs,submit,receipt,busy};
}
async function queued(t){for(let i=0;i<40;i++){if(t.requests.length)return t.requests.shift();await tick();}throw Error('No request');}
(async()=>{
 let t=setup(),p=t.submit();await t.submit();let q=await queued(t);const captured=JSON.parse(q.options.body);assert.equal(captured.text,t.$('retrieval-import-text').value);t.$('retrieval-import-text').value='Changed after capture';q.resolve({ok:true,json:async()=>t.receipt(captured)});await p;assert.equal(t.refreshes.length,1);assert.equal(t.busy(),false);assert.match(t.$('retrieval-import-status').textContent,/UNJUDGED/);
 for(const mutate of [r=>r.parents=[],r=>r.content_hash='0'.repeat(64),r=>r.source_sha256=r.content_hash,r=>r.task='text_retrieval',r=>r.review='human_reviewed',r=>r.annotation={},r=>r.source_available=false,r=>r.groups=['other'],r=>r.name='other',r=>r.provenance.rights='known',r=>r.provenance.acquisition.declared_positive_refs[0].revision++,r=>r.id='bad']) {
  t=setup();p=t.submit();q=await queued(t);const r=t.receipt(JSON.parse(q.options.body));mutate(r);q.resolve({ok:true,json:async()=>r});await p;assert.equal(t.refreshes.length,0);assert.match(t.$('retrieval-import-status').textContent,/uncertain/i);assert.equal(t.requests.length,0);
 }
 for(const refs of [[],[{},{}],[{id:'a'.repeat(32),revision:9007199254740992,source_revision:1}],[{id:'a'.repeat(32),revision:true,source_revision:1}],[{id:'A'.repeat(32),revision:1,source_revision:1}],[{id:'a'.repeat(32),revision:1,source_revision:1,extra:1}]]) {
  t=setup();t.$('retrieval-import-refs').value=JSON.stringify(refs);await t.submit();assert.equal(t.requests.length,0);assert.equal(t.busy(),false);
 }
 t=setup();t.$('retrieval-import-refs').value=JSON.stringify([t.refs[0],t.refs[0]]);await t.submit();assert.equal(t.requests.length,0);
 // An old JSON completion cannot clear a newer BFCache owner's busy controls.
 t=setup();p=t.submit();q=await queued(t);let finish;q.resolve({ok:true,json:()=>new Promise(r=>finish=r)});await tick();t.events.pagehide();const prior=t.$('retrieval-import-status').textContent;await t.submit();assert.equal(t.requests.length,0);t.events.pageshow({persisted:true});assert.equal(t.busy(),false);
 const newer=t.submit(),q2=await queued(t);finish(t.receipt(JSON.parse(q.options.body)));await p;assert.equal(t.busy(),true);assert.equal(t.controls[0].disabled,true);assert.equal(t.refreshes.length,0);assert.equal(t.$('retrieval-import-status').textContent,prior);q2.resolve({ok:true,json:async()=>t.receipt(JSON.parse(q2.options.body))});await newer;assert.equal(t.busy(),false);assert.equal(t.refreshes.length,1);
 // Departing during async hashing must not issue a POST or reset a newer owner.
 const digests=[];t=setup((algorithm,bytes)=>new Promise(resolve=>digests.push({bytes,resolve})));p=t.submit();assert.equal(digests.length,2);t.events.pagehide();t.events.pageshow({persisted:false});const newerHash=t.submit();assert.equal(digests.length,4);for(const d of digests.slice(0,2))d.resolve(crypto.createHash('sha256').update(d.bytes).digest());await p;assert.equal(t.requests.length,0);assert.equal(t.busy(),true);for(const d of digests.slice(2))d.resolve(crypto.createHash('sha256').update(d.bytes).digest());q=await queued(t);q.resolve({ok:true,json:async()=>t.receipt(JSON.parse(q.options.body))});await newerHash;assert.equal(t.refreshes.length,1);
 console.log('Retrieval controller PASS: exact raw/canonical receipts, safe refs, snapshot/no replay, stale JSON/hash completion and restored-page ownership.');
})().catch(e=>{console.error(e);process.exitCode=1;});
