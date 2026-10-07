'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
process.env.TULDOK_SOURCE_ROOT='/workspace/Tuldok';
const {atomicIndexedDB,serializedLocks,recoveryHarness,faultStorage,flush,row,response,admitted}=require('./qualified-controller-helpers.cjs');
const key='tuldok.text-classification-proposals.admission.v1',root=__dirname;
const intent={source_id:row.id,revision:row.revision,source_revision:row.source_revision,server_url:'http://127.0.0.1:2000/',model:'fixture',instruction:'Exact cross-tab shared intent',seed:42,labels:['schedule','cancel']};
const frame=body=>JSON.stringify({schema_version:1,body});
const bounded=promise=>Promise.race([promise,new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('Bounded probe timed out')),4000);timer.unref();})]);
async function ready(page){page.resolveLists();await flush();assert.equal(page.run('textClassificationProposalAuthorityReady'),true);}
async function start(page){const done=page.get('text-classification-proposal-form').dispatch('submit');await flush();return {done,post:page.take('/text-classification-proposals','POST')};}
async function overlap(status,secondAckLost=false){
  const storage=faultStorage(),database=atomicIndexedDB(),locks=serializedLocks();
  const page=()=>recoveryHarness(storage,locks,{indexedDB:database});
  const left=page(),right=page();left.configure(intent);right.configure(intent);await ready(left);await ready(right);
  const a=await start(left),body=JSON.parse(a.post.options.body),raw=frame(body);assert.equal(database.data.get('attempt').generation,1);
  const b=await start(right);assert.deepEqual(JSON.parse(b.post.options.body),body);assert.equal(database.data.get('attempt').generation,2);
  a.post.resolve(response({error:'Controlled delayed initial refusal'},false,status));await bounded(a.done);
  assert.equal(database.data.get('pending'),raw);assert.equal(storage.getItem(key),raw);assert.equal(database.data.get('attempt').generation,2);
  assert.equal(database.data.get('initialized').resolved_raw,null);assert.equal(left.run('textClassificationProposalPendingRequest.request_id'),body.request_id);assert.equal(right.run('textClassificationProposalAdmissionRequest.request_id'),body.request_id);
  const retainedAfterRefusal={raw:database.data.get('pending'),mirror:storage.getItem(key),attempt:database.data.get('attempt'),leftRecoveryId:left.run('textClassificationProposalRecoveryId'),secondUnresolved:true};
  if(secondAckLost){b.post.reject(Error('Controlled lost second acknowledgment'));await bounded(b.done);}
  const reload=page();reload.configure({...intent,instruction:'Changed intent after older refusal'});await ready(reload);
  const exact=reload.take('/text-classification-proposals/'+body.request_id);exact.resolve(response({error:'Controlled early exact-ID 404'},false,404));await flush();
  await reload.get('text-classification-proposal-form').dispatch('submit');assert.equal(reload.posts().length,0);assert.equal(storage.getItem(key),raw);assert.equal(database.data.get('attempt').generation,2);
  reload.configure(intent);const c=await start(reload);assert.deepEqual(JSON.parse(c.post.options.body),body);assert.equal(database.data.get('attempt').generation,3);
  c.post.resolve(response({error:'Explicit repeat refusal cannot settle earlier admissions'},false,409));await bounded(c.done);assert.equal(database.data.get('pending'),raw);assert.equal(storage.getItem(key),raw);assert.equal(database.data.get('attempt').generation,3);
  // Parent permits an exact canonical admission receipt to settle the whole ID.
  const observer=page();observer.configure(intent);observer.resolveLists([admitted(body,{status:'cancelled'})]);await flush();
  assert.equal(database.data.get('pending'),undefined);assert.equal(database.data.get('attempt'),undefined);assert.equal(storage.getItem(key),null);
  observer.configure({...intent,instruction:'Fresh explicit intent after canonical receipt'});const fresh=await start(observer),newBody=JSON.parse(fresh.post.options.body);assert.notEqual(newBody.request_id,body.request_id);assert.equal(database.data.get('attempt').generation,1);
  if(!secondAckLost){b.post.resolve(response(admitted(body,{status:'cancelled'})));await flush();right.resolveLists();await bounded(b.done);}
  assert.equal(database.data.get('pending'),frame(newBody));assert.equal(storage.getItem(key),frame(newBody));assert.equal(database.data.get('attempt').raw,frame(newBody));
  fresh.post.reject(Error('End bounded fixture with retained new admission'));await bounded(fresh.done);
  const result={status,secondAckLost,original:body,retainedAfterRefusal,changedIntentPostCount:0,exactRetryGeneration:3,knownCanonicalReceiptRetiredWholeId:true,successor:newBody,staleReceiptPreservedSuccessor:true,providerCallsPerformed:0};
  fs.writeFileSync(path.join(root,'overlap-'+status+(secondAckLost?'-second-ack-lost':'-second-held')+'.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({status,secondAckLost,originalId:body.request_id,changedIntentPostCount:0,explicitRetrySameId:true,canonicalReceiptAllowsFreshId:true,lateReceiptPreservedSuccessor:true}));
}
async function counterBoundaries(){
  const body={...intent,request_id:'7'.repeat(32)},raw=frame(body);
  for(const generation of [0,1.5,'2']){
    const storage=faultStorage(raw),database=atomicIndexedDB(),locks=serializedLocks();database.data.set('pending',raw);database.data.set('initialized',{schema_version:1,resolved_raw:null});database.data.set('attempt',{schema_version:1,raw,generation});
    const page=recoveryHarness(storage,locks,{indexedDB:database});page.configure(intent);page.resolveLists();await flush();
    await page.get('text-classification-proposal-form').dispatch('submit');assert.equal(page.posts().length,0);assert.equal(database.data.get('pending'),raw);assert.equal(storage.getItem(key),raw);
    const exact=page.take('/text-classification-proposals/'+body.request_id);exact.resolve(response(admitted(body,{status:'failed'})));await flush();
    assert.equal(database.data.get('pending'),undefined);assert.equal(database.data.get('attempt'),undefined);assert.equal(storage.getItem(key),null);assert.equal(page.run('textClassificationProposalStorageBlocked'),'');
    console.log(JSON.stringify({badCounter:generation,preReceiptPosts:0,canonicalExactGetRecovered:true}));
  }
  for(const attempt of [null,{schema_version:2,raw,generation:0},{schema_version:1,raw:frame({...body,request_id:'8'.repeat(32)}),generation:0},{schema_version:1,raw,generation:0,extra:true}]){
    const storage=faultStorage(raw),database=atomicIndexedDB();database.data.set('pending',raw);database.data.set('initialized',{schema_version:1,resolved_raw:null});database.data.set('attempt',attempt);
    const page=recoveryHarness(storage,serializedLocks(),{indexedDB:database});page.configure(intent);page.resolveLists();await flush();const exact=page.take('/text-classification-proposals/'+body.request_id);exact.resolve(response(admitted(body,{status:'failed'})));await flush();
    assert.equal(database.data.get('pending'),raw);assert.deepEqual(database.data.get('attempt'),attempt);assert.equal(storage.getItem(key),raw);assert.ok(page.run('textClassificationProposalStorageBlocked'));await page.get('text-classification-proposal-form').dispatch('submit');assert.equal(page.posts().length,0);
    console.log(JSON.stringify({unsafeAttempt:attempt,canonicalReceiptPreserved:true,posts:0}));
  }
}
(async()=>{for(const status of [400,409,422])await overlap(status);await overlap(409,true);await counterBoundaries();console.log('PASS: four overlapping actual-form dispatch/reload regressions; three raw-bound bad-counter exact GET recoveries; four opaque/foreign evidence fail-closed cases.');})().catch(error=>{console.error(error);process.exitCode=1;});
