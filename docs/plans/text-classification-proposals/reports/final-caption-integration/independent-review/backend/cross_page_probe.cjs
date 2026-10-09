'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const source=fs.readFileSync('/workspace/Tuldok/static/text-classification-proposals.js','utf8');
const helpers=source.slice(0,source.indexOf('function textClassificationProposalsShown(record)'));
const submit=source.slice(source.indexOf("$('text-classification-proposal-form').addEventListener('submit'"),source.indexOf("action('text-classification-proposal-refresh'"));
const key='tuldok.text-classification-proposals.admission.v1',row={id:'1'.repeat(32),kind:'text',revision:1,source_revision:1,annotation:null};
function shared(){let queue=Promise.resolve();const state={raw:null};return {state,storage:{getItem(k){assert.equal(k,key);return state.raw;},setItem(k,value){assert.equal(k,key);state.raw=value;},removeItem(k){assert.equal(k,key);state.raw=null;}},locks:{request(name,options,fn){assert.equal(name,key);const next=queue.then(fn);queue=next.catch(()=>{});return next;}}};}
function page(shared,guidance='same exact guidance'){
 const nodes=new Map(),requests=[];
 const element=id=>{if(!nodes.has(id))nodes.set(id,{value:'',dataset:{},listeners:{},addEventListener(event,fn){this.listeners[event]=fn;}});return nodes.get(id);};
 for(const [id,value] of [['url','http://127.0.0.1:9000/v1/'],['model','fixture'],['guidance',guidance],['seed','42'],['labels','["Keep","keep"]']])element('text-classification-proposal-'+id).value=value;
 const c=vm.createContext({console,JSON,URL,crypto,navigator:{locks:shared.locks},localStorage:shared.storage,$:element,current:{...row},hasUnsavedEdits:()=>false,
 api(route,body){assert.equal(route,'text-classification-proposals');assert.deepEqual(JSON.parse(shared.state.raw),{schema_version:1,body:JSON.parse(JSON.stringify(body))},'Exact body must be durable before POST');return new Promise((resolve,reject)=>requests.push({body:JSON.parse(JSON.stringify(body)),resolve,reject}));},refreshTextClassificationProposals:async()=>{}});
 vm.runInContext(helpers+submit,c);
 return {c,requests,element,run:text=>vm.runInContext(text,c),submit:()=>element('text-classification-proposal-form').listeners.submit({preventDefault(){}})};
}
const receipt=body=>({id:body.request_id,source:{id:body.source_id,revision:body.revision,source_revision:body.source_revision},config:{requested_server_url:body.server_url,requested_model:body.model,instruction:body.instruction,seed:body.seed,labels:body.labels}});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const first=shared(),a=page(first),b=page(first);const pa=a.submit(),pb=b.submit();await flush();
 assert.equal(a.requests.length,1);assert.equal(b.requests.length,1);assert.deepEqual(a.requests[0].body,b.requests[0].body,'Concurrent unchanged explicit submissions must share the durable original ID and body');
 a.requests[0].reject(Error('lost acknowledgement'));b.requests[0].reject(Error('lost acknowledgement'));await Promise.all([pa,pb]);assert.equal(JSON.parse(first.state.raw).body.request_id,a.requests[0].body.request_id);console.log('PASS concurrent cross-page unchanged submissions reuse one exact durable admission');
 const different=shared(),c=page(different),d=page(different,'different new intent');const pc=c.submit(),pd=d.submit();await flush();
 assert.equal(c.requests.length,1);assert.equal(d.requests.length,0);await pd;assert.ok(d.run('textClassificationProposalStorageBlocked')||d.element('text-classification-proposal-status').textContent.includes('unknown acknowledgement'));c.requests[0].reject(Error('lost acknowledgement'));await pc;assert.equal(JSON.parse(different.state.raw).body.request_id,c.requests[0].body.request_id);console.log('PASS concurrent cross-page changed intent is blocked before POST');
 const overlap=shared(),e=page(overlap),f=page(overlap);const pe=e.submit();await flush();const old=e.requests[0].body;
 assert.equal(f.run('textClassificationProposalRestoreStorage()'),true);
 assert.equal(await f.run('textClassificationProposalClearStorage(textClassificationProposalPendingRequest.request_id,textClassificationProposalPendingRequest)'),true); // Synthetic authoritative exact GET of old admission in the other page.
 f.element('text-classification-proposal-guidance').value='explicit fresh intent after authoritative receipt';const pf=f.submit();await flush();assert.equal(f.requests.length,1);const fresh=f.requests[0].body;assert.notEqual(fresh.request_id,old.request_id);
 e.requests[0].resolve(receipt(old));await pe;assert.equal(JSON.parse(overlap.state.raw).body.request_id,fresh.request_id,'Old acknowledgement cannot erase a newer persisted request');assert.equal(e.run('textClassificationProposalPendingRequest.request_id'),old.request_id);assert.ok(e.run('textClassificationProposalStorageBlocked'));f.requests[0].reject(Error('lost new acknowledgement'));await pf;console.log('PASS old cross-page POST acknowledgement cannot clear newer durable identity');
 console.log(JSON.stringify({passed:3,failed:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
