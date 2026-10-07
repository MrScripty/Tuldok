from pathlib import Path
old=Path('/workspace/Tuldok/docs/plans/text-classification-proposals/reports/admission-authority-repair/independent-review/backend/native_idb_probe.cjs').read_text()
prefix=old[:old.index(" await check('native shared authority")]
cleanup=old[old.index('})().catch(error=>'):]
cases=r'''
 async function records(p){return p.evaluate(`(async()=>{const db=await new Promise((r,j)=>{const q=indexedDB.open('${recoveryKey}',1);q.onsuccess=()=>r(q.result);q.onerror=()=>j(q.error);});const result=await new Promise((r,j)=>{const tx=db.transaction('recovery','readonly'),s=tx.objectStore('recovery'),result={};let n=0;for(const key of ['pending','attempt','initialized','legacy_blocker']){const q=s.get(key);q.onsuccess=()=>{result[key]=q.result;if(++n===4)r(result);};q.onerror=()=>j(q.error);} });db.close();return result;})()`);}
 for(const counter of [0,-1,1.25,'2',null,Number.MAX_SAFE_INTEGER+1])await check('same raw invalid counter '+JSON.stringify(counter)+' exact admitted GET recovers without POST',async()=>{
  const p=await newPage();await ready(p);await configure(p);const exact=(await submit(p))[0],raw=frame(exact);
  await metadata(p,{attempt:{schema_version:1,raw,generation:counter}});await p.evaluate(`window.reviewKnownJob=${JSON.stringify(known(exact))};true`);
  await p.evaluate('refreshTextClassificationProposals()');await until(()=>p.evaluate('textClassificationProposalPendingRequest===null'),'counter exact receipt recovery');
  const snapshot=await records(p);assert.equal(snapshot.pending,undefined);assert.equal(snapshot.attempt,undefined);assert.equal(snapshot.initialized.resolved_raw,raw);assert.equal(await mirror(p),null);assert.equal((await p.evaluate('reviewPostedBodies')).length,1);receipts.push({case:'counter-receipt',counter,exact,snapshot});
 });
 for(const kind of ['foreign-raw','foreign-schema','opaque','array','extra'])await check(kind+' attempt remains failclosed despite known pending receipt',async()=>{
  const p=await newPage();await ready(p);await configure(p);const exact=(await submit(p))[0],raw=frame(exact);
  const attempt=kind==='foreign-raw'?{schema_version:1,raw:frame({...exact,request_id:'f'.repeat(32)}),generation:0}:kind==='foreign-schema'?{schema_version:2,raw,generation:0}:kind==='opaque'?null:kind==='array'?[]:{schema_version:1,raw,generation:0,extra:true};
  await metadata(p,{attempt});const before=await records(p);await p.evaluate(`window.reviewKnownJob=${JSON.stringify(known(exact))};true`);await p.evaluate('refreshTextClassificationProposals()');await configure(p,'Changed blocked admission');await forceSubmit(p);
  assert.deepEqual(await records(p),before);assert.equal(await mirror(p),raw);assert.equal((await p.evaluate('reviewPostedBodies')).length,1);assert.ok(await p.evaluate('textClassificationProposalStorageBlocked'));receipts.push({case:kind,before,status:await p.evaluate('textClassificationProposalStorageBlocked')});
 });
 await check('older refusal generation CAS preserves exact body memory mirror and durable next attempt',async()=>{
  const a=await newPage(),b=await newPage();await Promise.all([ready(a),ready(b)]);await configure(a);await configure(b);const exact=(await submit(a))[0];assert.deepEqual((await submit(b))[0],exact);
  const before=await records(a);assert.equal(before.attempt.generation,2);assert.equal(await a.evaluate('textClassificationProposalClearStorage(textClassificationProposalPendingRequest.request_id,textClassificationProposalPendingRequest,1)'),false);
  assert.deepEqual(await records(a),before);assert.equal(await mirror(a),frame(exact));assert.deepEqual(await a.evaluate('textClassificationProposalPendingRequest'),exact);receipts.push({case:'stale-refusal-CAS',exact,before});
 });
 await check('matching admission proof retires whole ID but stale proof preserves successor attempt',async()=>{
  const a=await newPage(),b=await newPage();await Promise.all([ready(a),ready(b)]);await configure(a);await configure(b);const exact=(await submit(a))[0];assert.deepEqual((await submit(b))[0],exact);assert.equal((await records(a)).attempt.generation,2);
  await a.evaluate(`window.reviewKnownJob=${JSON.stringify(known(exact))};true`);await a.evaluate('refreshTextClassificationProposals()');assert.equal((await records(a)).attempt,undefined);
  await configure(a,'Successor after whole ID admission receipt');const fresh=(await submit(a))[1];assert.notEqual(fresh.request_id,exact.request_id);const before=await records(a);assert.equal(before.attempt.generation,1);
  assert.equal(await b.evaluate('textClassificationProposalClearStorage(textClassificationProposalPendingRequest.request_id,textClassificationProposalPendingRequest)'),false);assert.deepEqual(await records(a),before);assert.equal(await mirror(a),frame(fresh));receipts.push({case:'whole-ID-positive-successor-CAS',exact,fresh,before});
 });
 await check('real asynchronous attempt put ConstraintError blocks retry before HTTP and preserves generation',async()=>{
  const p=await newPage();await ready(p);await configure(p);const exact=(await submit(p))[0];await collision(p);const before=await records(p);
  await p.evaluate(`window.reviewPut=IDBObjectStore.prototype.put;window.reviewAttemptErrors=[];IDBObjectStore.prototype.put=function(value,key){if(key==='attempt'){const r=this.add({fixture:'attempt failure'},'${collisionKey}');this.transaction.addEventListener('error',e=>reviewAttemptErrors.push({name:e.target.error?.name,prevented:e.defaultPrevented}));return r;}return reviewPut.call(this,value,key);};true`);
  await submit(p);assert.equal((await p.evaluate('reviewPostedBodies')).length,1);assert.deepEqual(await records(p),before);assert.equal(await mirror(p),frame(exact));const errors=await p.evaluate('reviewAttemptErrors');assert.ok(errors.some(e=>e.name==='ConstraintError'&&e.prevented));
  await p.evaluate('IDBObjectStore.prototype.put=reviewPut;true');const repeats=await submit(p);assert.equal(repeats.length,2);assert.deepEqual(repeats[1],exact);assert.equal((await records(p)).attempt.generation,2);receipts.push({case:'attempt-native-constraint',before,errors,after:await records(p)});
 });
 await check('attempt put success then transaction abort cannot send or advance durable generation',async()=>{
  const p=await newPage();await ready(p);await configure(p);const exact=(await submit(p))[0],before=await records(p);
  await p.evaluate(`window.reviewPut=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(value,key){const r=reviewPut.call(this,value,key);if(key==='attempt'){const tx=this.transaction;r.addEventListener('success',()=>tx.abort());}return r;};true`);await submit(p);
  assert.equal((await p.evaluate('reviewPostedBodies')).length,1);assert.deepEqual(await records(p),before);assert.equal(await mirror(p),frame(exact));await p.evaluate('IDBObjectStore.prototype.put=reviewPut;true');const repeats=await submit(p);assert.deepEqual(repeats[1],exact);assert.equal((await records(p)).attempt.generation,2);receipts.push({case:'attempt-put-success-abort',before,after:await records(p)});
 });
 await check('attempt generation exhaustion blocks POST and exact positive receipt remains live',async()=>{
  const p=await newPage();await ready(p);await configure(p);const exact=(await submit(p))[0],raw=frame(exact);await metadata(p,{attempt:{schema_version:1,raw,generation:Number.MAX_SAFE_INTEGER}});const before=await records(p);await submit(p);assert.equal((await p.evaluate('reviewPostedBodies')).length,1);assert.deepEqual(await records(p),before);assert.ok((await p.evaluate('textClassificationProposalStorageBlocked')).includes('exhausted'));
  await p.evaluate(`window.reviewKnownJob=${JSON.stringify(known(exact))};true`);await p.evaluate('refreshTextClassificationProposals()');const snapshot=await records(p);assert.equal(snapshot.pending,undefined);assert.equal(snapshot.attempt,undefined);assert.equal(snapshot.initialized.resolved_raw,raw);receipts.push({case:'exhausted-receipt',before,snapshot});
 });
 console.log(JSON.stringify({passed}));
'''
Path('/workspace/scratch/tuldok-classification-dispatch-repair/review-backend/native_generation_probe.cjs').write_text(prefix+cases+cleanup)
