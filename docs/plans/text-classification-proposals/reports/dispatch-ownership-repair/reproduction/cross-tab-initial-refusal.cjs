'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
process.env.TULDOK_SOURCE_ROOT='/workspace/Tuldok';
const {atomicIndexedDB,serializedLocks,recoveryHarness,faultStorage,flush,row,response}=require('./qualified-controller-helpers.cjs');
const out=__dirname,key='tuldok.text-classification-proposals.admission.v1';
const intent={source_id:row.id,revision:row.revision,source_revision:row.source_revision,server_url:'http://127.0.0.1:2000/',model:'fixture',instruction:'Exact cross-tab shared intent',seed:42,labels:['schedule','cancel']};
const frame=body=>JSON.stringify({schema_version:1,body});
async function ready(page){page.resolveLists();await flush();assert.equal(page.run('textClassificationProposalAuthorityReady'),true);}
async function submit(page){const done=page.get('text-classification-proposal-form').dispatch('submit');await flush();return {done,post:page.take('/text-classification-proposals','POST')};}
async function scenario(status,losesSecondAck=false){
  const storage=faultStorage(),database=atomicIndexedDB(),locks=serializedLocks();
  const first=recoveryHarness(storage,locks,{indexedDB:database}),second=recoveryHarness(storage,locks,{indexedDB:database});
  first.configure(intent);second.configure(intent);await ready(first);await ready(second);
  const a=await submit(first),abody=JSON.parse(a.post.options.body),b=await submit(second),bbody=JSON.parse(b.post.options.body);
  assert.deepEqual(abody,bbody,'Both pages explicitly dispatch the identical reserved ID/body');
  assert.equal(database.data.get('pending'),frame(abody));assert.equal(storage.getItem(key),frame(abody));
  assert.equal(first.run('textClassificationProposalAdmissionRequest.request_id'),abody.request_id);
  assert.equal(second.run('textClassificationProposalAdmissionRequest.request_id'),abody.request_id);
  a.post.resolve(response({error:'Controlled definite first-dispatch refusal before admission'},false,status));await a.done;
  const afterRefusal={pending:database.data.get('pending')??null,mirror:storage.getItem(key),retired:database.data.get('initialized')?.resolved_raw??null,secondBusy:second.run('textClassificationProposalBusy'),secondInFlight:second.run('textClassificationProposalAdmissionRequest?.request_id')};
  assert.equal(afterRefusal.pending,null,'DEFECT: first 4xx cleared shared authority while another exact dispatch is unresolved');
  assert.equal(afterRefusal.mirror,null);assert.equal(afterRefusal.retired,frame(abody));assert.equal(afterRefusal.secondBusy,true);assert.equal(afterRefusal.secondInFlight,abody.request_id);
  if(losesSecondAck){b.post.reject(Error('Controlled lost second-dispatch acknowledgement; its server admission may still arrive'));await b.done;}
  // A full replacement context starts from the same durable stores and sees no
  // pending request. There are no manually reconstructed form settings or IDs.
  const reload=recoveryHarness(storage,locks,{indexedDB:database});reload.configure({...intent,instruction:'Changed intent after other tab refusal'});await ready(reload);
  assert.equal(reload.run('textClassificationProposalPendingRequest'),null);
  const c=await submit(reload),cbody=JSON.parse(c.post.options.body);
  assert.notEqual(cbody.request_id,abody.request_id,'DEFECT: changed intent dispatches a second admission ID');
  assert.equal(cbody.instruction,'Changed intent after other tab refusal');
  const result={status,losesSecondAck,original:abody,duplicate:bbody,afterRefusal,newAdmission:cbody,sharedStrictSerializableTransactionHistory:database.history,distinctPotentialAdmissions:[abody.request_id,cbody.request_id],providerCallsPerformed:0};
  fs.writeFileSync(path.join(out,'scenario-'+status+(losesSecondAck?'-lost-second-ack':'-second-held')+'.json'),JSON.stringify(result,null,2)+'\n');
  // Close synthetic transport promises after recording the unsafe outcome.
  if(!losesSecondAck){b.post.reject(Error('End bounded fixture without provider execution'));await b.done;}
  c.post.reject(Error('End bounded fixture without provider execution'));await c.done;
  console.log(JSON.stringify({status,losesSecondAck,firstId:abody.request_id,newId:cbody.request_id,unresolvedSecondAtRefusal:true,authorityCleared:true,changedIntentPosted:true,providerCallsPerformed:0}));
  return result;
}
(async()=>{for(const status of [400,409,422])await scenario(status);await scenario(409,true);console.log('Confirmed four bounded cross-tab initial-refusal retirement reproductions against exact unchanged controller.');})().catch(error=>{console.error(error);process.exitCode=1;});
