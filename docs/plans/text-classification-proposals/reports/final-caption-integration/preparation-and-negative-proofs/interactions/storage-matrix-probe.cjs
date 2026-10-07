'use strict';
const assert=require('node:assert/strict');
const {harness,storage,row,flush}=require('./tuldok-recovery-review-storage-harness.cjs');
const key='tuldok.text-classification-proposals.admission.v1';
class Locks{
 constructor(){this.queue=[];this.active=false;this.hold=false;this.calls=0;}
 request(name,options,fn){assert.equal(name,key);assert.equal(options.mode,'exclusive');this.calls++;return new Promise((resolve,reject)=>{this.queue.push({fn,resolve,reject});this.drain();});}
 async drain(){if(this.active||this.hold||!this.queue.length)return;this.active=true;const entry=this.queue.shift();try{entry.resolve(await entry.fn());}catch(error){entry.reject(error);}finally{this.active=false;this.drain();}}
 release(){this.hold=false;this.drain();}
}
function faultyStorage(){const base=storage(),get=base.getItem.bind(base),set=base.setItem.bind(base),remove=base.removeItem.bind(base);base.fail={};base.getItem=key=>{if(base.fail.read)throw Error('Synthetic storage read refusal');return get(key);};base.setItem=(key,value)=>{if(base.fail.write)throw Error('Synthetic storage write refusal');return set(key,value);};base.removeItem=key=>{if(base.fail.remove)throw Error('Synthetic storage remove refusal');return remove(key);};return base;}
const job=body=>({id:body.request_id,revision:3,status:'completed',source:{...row,id:body.source_id,revision:body.revision,source_revision:body.source_revision},config:{server_url:'http://127.0.0.1:9999',requested_server_url:body.server_url,model:'fixture',requested_model:body.model,instruction:body.instruction,seed:body.seed,labels:body.labels},annotation:{label:body.labels[0]},error:''});
const posts=h=>h.requests.filter(request=>request.body!==undefined);
async function loseStart(h,guidance){h.fill(guidance);const submitting=h.element('text-classification-proposal-form').dispatch('submit');await flush();const request=h.take('text-classification-proposals','POST'),body=structuredClone(request.body);request.reject(Error('Synthetic lost admission acknowledgement'));await submitting;return body;}
async function poll(h,body,jobs=[job(body)]){const refreshing=h.run('refreshTextClassificationProposals()');h.take('text-classification-proposals','GET').resolve({jobs});await refreshing;}
async function reloadDelayed404AndSameBody(){
 const persistence=faultyStorage(),locks=new Locks(),first=harness(persistence,locks),body=await loseStart(first,'Original exact guidance');const raw=persistence.values.get(key);assert.deepEqual(JSON.parse(raw).body,body);
 const next=harness(persistence,locks);assert.equal(next.run('textClassificationProposalPendingRequest.request_id'),body.request_id);assert.equal(posts(next).length,0);
 next.fill('Changed after reload');await next.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(next).length,0);
 next.take('text-classification-proposals','GET').resolve({jobs:[]});await flush();const absence=next.take('text-classification-proposals/'+body.request_id,'GET');const error=Error('Early absence');error.status=404;absence.reject(error);await flush();assert.equal(persistence.values.get(key),raw);
 next.fill('Original exact guidance');const submitting=next.element('text-classification-proposal-form').dispatch('submit');await flush();const repeat=next.take('text-classification-proposals','POST');assert.deepEqual(repeat.body,body);const refusal=Error('Refused repeat while original unknown');refusal.status=409;repeat.reject(refusal);await submitting;assert.equal(persistence.values.get(key),raw);
}
async function storageReadWriteRemoveFailClosed(){
 const reading=faultyStorage();reading.fail.read=true;const noRead=harness(reading,new Locks());noRead.fill();await noRead.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(noRead).length,0);
 const writing=faultyStorage();writing.fail.write=true;const noWrite=harness(writing,new Locks());noWrite.fill();await noWrite.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(noWrite).length,0);assert.equal(writing.values.size,0);
 const persistence=faultyStorage(),h=harness(persistence,new Locks()),body=await loseStart(h);const raw=persistence.values.get(key);persistence.fail.remove=true;await poll(h,body);assert.equal(persistence.values.get(key),raw);assert.equal(h.run('textClassificationProposalPendingRequest.request_id'),body.request_id);
 h.fill('Different intent after remove refusal');await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(h).length,0);persistence.fail.remove=false;await poll(h,body);assert.equal(persistence.values.size,0);assert.equal(h.run('textClassificationProposalPendingRequest'),null);
 h.fill('Fresh terminal intent');const next=h.element('text-classification-proposal-form').dispatch('submit');await flush();const fresh=h.take('text-classification-proposals','POST');assert.notEqual(fresh.body.request_id,body.request_id);fresh.reject(Error('Synthetic lost fresh acknowledgement'));await next;
}
async function malformedOrUnsupportedStorageNeverPosts(){
 for(const raw of ['{','null','x'.repeat(64001),JSON.stringify({schema_version:2,body:{request_id:'d'.repeat(32)}}),JSON.stringify({schema_version:1,body:{request_id:'d'.repeat(32)}})]){
  const persistence=faultyStorage();persistence.values.set(key,raw);const h=harness(persistence,new Locks());h.fill();await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(h).length,0);assert.equal(persistence.values.get(key),raw);
 }
 const h=harness(faultyStorage(),null);h.fill();await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(h).length,0);
}
async function credentialsNeverPersist(){
 for(const url of ['http://user:secret@127.0.0.1:9999/v1/','https://host.invalid/path?token=secret','file:///tmp/model']){
  const persistence=faultyStorage(),h=harness(persistence,new Locks());h.fill();h.element('text-classification-proposal-url').value=url;await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(posts(h).length,0);assert.equal(persistence.values.size,0);
 }
}
async function simultaneousPagesReceiveOneIdentity(){
 const persistence=faultyStorage(),locks=new Locks();locks.hold=true;const first=harness(persistence,locks),second=harness(persistence,locks);first.fill('First intent');second.fill('Changed second page intent');
 const one=first.element('text-classification-proposal-form').dispatch('submit'),two=second.element('text-classification-proposal-form').dispatch('submit');await flush();assert.equal(posts(first).length+posts(second).length,0);locks.release();await flush();assert.equal(posts(first).length+posts(second).length,1);
 const firstPost=first.take('text-classification-proposals','POST');assert.equal(JSON.parse(persistence.values.get(key)).body.request_id,firstPost.body.request_id);firstPost.reject(Error('Synthetic unknown first acknowledgement'));await one;await two;assert.equal(posts(second).length,0);
}
async function staleAcknowledgementCannotEraseNewAdmission(){
 const persistence=faultyStorage(),locks=new Locks(),older=harness(persistence,locks);older.fill();const oldSubmitting=older.element('text-classification-proposal-form').dispatch('submit');await flush();const oldPost=older.take('text-classification-proposals','POST'),oldBody=structuredClone(oldPost.body);
 const newer=harness(persistence,locks);newer.take('text-classification-proposals','GET').resolve({jobs:[job(oldBody)]});await flush();assert.equal(persistence.values.size,0);
 newer.fill('New authorized intent after recovery');const newSubmitting=newer.element('text-classification-proposal-form').dispatch('submit');await flush();const newPost=newer.take('text-classification-proposals','POST'),newBody=structuredClone(newPost.body);assert.notEqual(newBody.request_id,oldBody.request_id);
 oldPost.resolve(job(oldBody));await oldSubmitting;assert.equal(JSON.parse(persistence.values.get(key)).body.request_id,newBody.request_id);const reload=harness(persistence,locks);assert.equal(reload.run('textClassificationProposalPendingRequest.request_id'),newBody.request_id);assert.equal(posts(reload).length,0);newPost.reject(Error('Synthetic new acknowledgement lost'));await newSubmitting;
}
(async()=>{let failures=0;for(const test of [reloadDelayed404AndSameBody,storageReadWriteRemoveFailClosed,malformedOrUnsupportedStorageNeverPosts,credentialsNeverPersist,simultaneousPagesReceiveOneIdentity,staleAcknowledgementCannotEraseNewAdmission]){try{await test();console.log(test.name+' passed');}catch(error){failures++;console.error(test.name+': '+error.stack);}}if(failures)process.exitCode=1;})().catch(error=>{console.error(error.stack);process.exitCode=1;});
