'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),'static/caption-proposals.js'),'utf8');
const key='tuldok.caption-proposal-recovery.v1',row={id:'a'.repeat(32),kind:'image',revision:2,source_revision:1};
const body={source_id:row.id,revision:2,source_revision:1,server_url:'http://127.0.0.1:8765',model:'fixture',instruction:'Original exact guidance',seed:42,request_id:'0'.repeat(31)+'1'};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function storage() {return {data:new Map(),fail:'',getItem(k){if(this.fail==='read')throw Error('SecurityError');return this.data.get(k)??null;},setItem(k,v){if(this.fail==='write')throw Error('QuotaExceeded');this.data.set(k,v);},removeItem(k){if(this.fail==='remove')throw Error('SecurityError');this.data.delete(k);}};}
function page(store) {
  const elements=new Map(),requests=[],listeners={};
  class Element {
    constructor(){this.value='';this.children=[];this.dataset={};this.listeners={};}
    addEventListener(e,fn){(this.listeners[e]||=[]).push(fn);}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}
    async dispatch(e){for(const fn of this.listeners[e]||[])await fn({preventDefault(){},currentTarget:this});}
  }
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({URL,sessionStorage:store,crypto:{randomUUID:()=> '1'.repeat(32)},current:row,editorEpoch:0,
    $,document:{createElement:()=>new Element()},window:{addEventListener(e,fn){listeners[e]=fn;}},
    hasUnsavedEdits:()=>false,responseIntentEpoch:()=>0,clearTimeout(){},setTimeout:()=>1,
    action:(id,fn)=>$(id).addEventListener('click',fn),
    api:(url,request)=>new Promise((resolve,reject)=>requests.push({url,body:request,resolve,reject}))});
  vm.runInContext(source,context);const run=code=>vm.runInContext(code,context);
  function intent(value=body){for(const [id,v] of [['url',value.server_url],['model',value.model],['guidance',value.instruction],['seed',value.seed]])$('caption-proposal-'+id).value=v;}
  function take(url,post=false){const i=requests.findIndex(r=>r.url===url && (r.body!==undefined)===post);assert.notEqual(i,-1,url);return requests.splice(i,1)[0];}
  const submit=()=>$('caption-proposal-form').dispatch('submit'),refresh=()=>$('caption-proposal-refresh').dispatch('click');
  return {$,run,requests,intent,take,submit,refresh,listeners};
}
const persisted=(id,status='completed')=>({id,status,source:row,config:{model:'fixture'},annotation:{caption:'Fixture'},error:''});
(async()=>{
  for(const instruction of ['a'.repeat(2001),'\u{1f600}'.repeat(2001),'a'.repeat(2000)+'\u{1f600}']) {
    const freshStore=storage(),form=page(freshStore);form.intent({...body,instruction});await form.submit();
    assert.equal(form.requests.length,0);assert.equal(freshStore.data.size,0,'Invalid fresh guidance must not create recovery evidence');
    assert.equal(form.run('captionProposalStorageError'),'','Invalid form input must not latch a durable-storage failure');
    assert.equal(form.$('caption-proposal-submit').disabled,false);assert.ok(form.$('caption-proposal-status').textContent.includes('2,000 Unicode code points'));
    form.intent({...body,instruction:'Corrected guidance'});const refresh=form.refresh();form.take('caption-proposals').resolve({jobs:[]});await refresh;
    const corrected=form.submit(),post=form.take('caption-proposals',true);assert.equal(post.body.instruction,'Corrected guidance');
    post.reject(Object.assign(Error('Fixture first-attempt refusal'),{status:409}));await corrected;assert.equal(freshStore.data.size,0);
  }
  for(const instruction of ['a'.repeat(2000),'\u{1f600}'.repeat(2000),'a'.repeat(1999)+'\u{1f600}']) {
    const validStore=storage(),form=page(validStore);form.intent({...body,instruction});const started=form.submit(),post=form.take('caption-proposals',true);
    assert.equal(post.body.instruction,instruction,'Guidance counts code points and preserves exact non-BMP text');
    assert.equal(JSON.parse(validStore.data.get(key)).instruction,instruction);post.reject(Object.assign(Error('Fixture first-attempt refusal'),{status:409}));await started;
  }
  for(const instruction of ['a'.repeat(2001),'\u{1f600}'.repeat(2001)]) {
    const corrupt=storage(),data=JSON.stringify({...body,instruction});corrupt.data.set(key,data);const blocked=page(corrupt);blocked.intent();await blocked.submit();
    assert.equal(blocked.requests.length,0);assert.equal(corrupt.data.get(key),data);assert.ok(blocked.run('captionProposalStorageError'));assert.equal(blocked.$('caption-proposal-submit').disabled,true);
  }
  const whitespace=['',' ','\t\r\n','\u0085','\u001c\u001f','\u00a0\u1680\u2000\u200a\u2028\u2029\u202f\u205f\u3000'];
  const invalidSettings=[
    ...whitespace.map(instruction=>({instruction})),...whitespace.map(model=>({model})),
    ...['\u0000','\u001f','\ud800','\udfff','fixture\n'].map(model=>({model})),
    ...['\ud800','\udfff','visible\ud800text'].map(instruction=>({instruction})),
    ...['http:///v1','http:/host','http:host','https://','file://host','ftp://host','//host',
      'http:/\\host','http://host:0','http://host:00000','http://host:65536','http://host:-1',
      'http://host:abc','http://host/a b','http://host/a\tb','http://host/a\u0085b','http://host/\u0000',
      'http://@host','http://user@host','http://:pass@host','http://host?q=1','http://host#frag',
      'http://host/\ud800','http://host/\udfff','http://ho\uff1ast',
      'http://host/'+'a'.repeat(2048), 'http://host/'+'\u{1f600}'.repeat(2048)].map(server_url=>({server_url})),
    {model:'a'.repeat(201)},{model:'\u{1f600}'.repeat(201)},{model:' '+'a'.repeat(200)}
  ];
  for(const changes of invalidSettings) {
    const freshStore=storage(),form=page(freshStore);form.intent({...body,...changes});await form.submit();
    assert.equal(form.requests.length,0,'Invalid fresh settings must never reach admission: '+JSON.stringify(changes));
    assert.equal(freshStore.data.size,0);assert.equal(form.run('captionProposalStorageError'),'');assert.equal(form.$('caption-proposal-submit').disabled,false);
    form.intent();const corrected=form.submit(),post=form.take('caption-proposals',true);
    assert.deepEqual(JSON.parse(JSON.stringify(post.body)),{...body,request_id:'1'.repeat(32)});
    post.reject(Object.assign(Error('Definite first-attempt refusal'),{status:400}));await corrected;assert.equal(freshStore.data.size,0);
    // Preexisting invalid evidence has an unknown history; retain it instead of granting a new intent.
    const stored=storage(),raw=JSON.stringify({...body,...changes});stored.data.set(key,raw);const blocked=page(stored);blocked.intent();await blocked.submit();
    assert.equal(blocked.requests.length,0);assert.equal(stored.data.get(key),raw);assert.ok(blocked.run('captionProposalStorageError'));
  }
  const urlPrefix='http://host/';
  const acceptedSettings=[
    {instruction:'\ufeff'},{instruction:'\u180e'},{instruction:'\u0000Visible\u0000'},
    {instruction:'\u0085 Visible \u001c'}, {instruction:'\u{1f600}'.repeat(2000)},
    {model:'m'.repeat(200)},{model:'\u{1f600}'.repeat(200)},{model:'\u0085fixture\u00a0'},
    {server_url:' \u0085HTTP://host:80/base/v1///\u00a0 '},
    {server_url:'http://[::1]:8765/v1'}, {server_url:'http://host:'}, {server_url:'http://host:65535'},
    {server_url:urlPrefix+'a'.repeat(2048-urlPrefix.length)},
    {server_url:urlPrefix+'\u{1f600}'.repeat(2048-urlPrefix.length)},
    {server_url:urlPrefix+'a'.repeat(2048-urlPrefix.length)+'/v1///'},
    {seed:0},{seed:4294967295}
  ];
  for(const changes of acceptedSettings) {
    const validStore=storage(),form=page(validStore);form.intent({...body,...changes});const started=form.submit(),post=form.take('caption-proposals',true);
    assert.deepEqual(JSON.parse(JSON.stringify(post.body)),{...body,...changes,request_id:'1'.repeat(32)},'Validation must preserve exact raw intent');
    assert.deepEqual(JSON.parse(validStore.data.get(key)),JSON.parse(JSON.stringify(post.body)));
    post.reject(Object.assign(Error('Definite first-attempt refusal'),{status:400}));await started;
  }
  const shapeCases=[{request_id:'a'.repeat(32)+'\n'},{source_id:'a'.repeat(32)+'\n'},{request_id:'A'.repeat(32)},
    {source_id:''},{revision:true},{revision:0},{revision:1.5},{source_revision:'1'},{source_revision:0},
    {seed:true},{seed:-1},{seed:4294967296},{seed:1.5},{seed:'42'},
    {server_url:null},{model:null},{instruction:null},{extra:'unrequested'}];
  const validator=page(storage());
  for(const changes of shapeCases){validator.run('globalThis.probe='+JSON.stringify({...body,...changes}));assert.throws(()=>validator.run('captionProposalRecoveryBody(probe)'),JSON.stringify(changes));}
  // Use the real Python validators as an independent oracle for the entire static contract.
  const candidates=[body,...invalidSettings.map(change=>({...body,...change})),...acceptedSettings.map(change=>({...body,...change})),...shapeCases.map(change=>({...body,...change}))];
  const oracle=require('node:child_process').spawnSync(process.env.PYTHON||'python',['-c',`
import json,sys,ai_http
from workbench import IDENTIFIER,text_value
out=[]
for body in json.load(sys.stdin):
 try:
  assert set(body)=={'source_id','revision','source_revision','server_url','model','instruction','seed','request_id'}
  for key in ('request_id','source_id'): assert isinstance(body[key],str) and IDENTIFIER.fullmatch(body[key])
  for key in ('revision','source_revision'): assert type(body[key]) is int and body[key]>=1
  assert type(body['seed']) is int and 0<=body['seed']<=2**32-1
  text_value(ai_http.validate_url('llamacpp',body['server_url']),'Server URL',2048)
  text_value(ai_http.validate_model(body['model']),'Model ID',200)
  text_value(body['instruction'],'Caption guidance',2000)
  out.append(True)
 except (AssertionError,ValueError,TypeError): out.append(False)
json.dump(out,sys.stdout)
`],{cwd:process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),input:JSON.stringify(candidates),encoding:'utf8'});
  assert.equal(oracle.status,0,oracle.stderr);const verdicts=JSON.parse(oracle.stdout);
  for(const [index,candidate] of candidates.entries()) {
    validator.run('globalThis.probe='+JSON.stringify(candidate));let accepted=true;
    try{validator.run('captionProposalRecoveryBody(probe)');}catch{accepted=false;}
    assert.equal(accepted,verdicts[index],'Backend admission parity: '+JSON.stringify(candidate));
  }
  // A lost error reply after a valid POST still cannot prove no admission occurred.
  const lostStore=storage(),lostPage=page(lostStore);lostPage.intent();const lost=lostPage.submit(),lostPost=lostPage.take('caption-proposals',true);
  const lostBody=JSON.parse(JSON.stringify(lostPost.body));lostPost.reject(Error('Lost 400 error response'));await lost;
  const reloaded=page(lostStore);const lostLookup=reloaded.refresh();reloaded.take('caption-proposals').resolve({jobs:[]});await flush();
  reloaded.take('caption-proposals/'+lostBody.request_id).reject(Object.assign(Error('Not visible'),{status:404}));await lostLookup;
  reloaded.intent({...body,instruction:'Corrected after unknown error'});await reloaded.submit();assert.equal(reloaded.requests.length,0);
  assert.deepEqual(JSON.parse(lostStore.data.get(key)),lostBody,'Unknown error response and 404 retain exact identity');
  reloaded.intent(lostBody);const repeated=reloaded.submit(),repeatPost=reloaded.take('caption-proposals',true);
  assert.deepEqual(JSON.parse(JSON.stringify(repeatPost.body)),lostBody);repeatPost.reject(Object.assign(Error('Repeat refused'),{status:400}));await repeated;
  assert.deepEqual(JSON.parse(lostStore.data.get(key)),lostBody,'A refused repeat cannot disprove an earlier unknown outcome');
  console.log('Static admission parity: '+candidates.length+' cases across every field; exact normalization/Unicode boundaries, fresh correction, legacy invalid evidence and lost-error/404/reload fencing passed.');
  console.log('Fresh guidance ASCII/non-BMP 2000/2001 boundaries and correction/refresh without reload passed; invalid stored evidence remains fail-closed.');
  if(process.env.CAPTION_RELOAD_CASE==='input')return;
  if(process.env.CAPTION_RELOAD_CASE==='restore') {
    const prior=storage();prior.data.set(key,JSON.stringify(body));const restored=page(prior);
    const reconciliation=restored.refresh(),held=restored.take('caption-proposals');
    restored.intent({...body,instruction:'Changed while reload GET is held'});const changed=restored.submit();
    assert.equal(restored.requests.length,0,'A full reload must refuse a changed POST while initial reconciliation is held');await changed;
    assert.equal(restored.run('captionProposalPendingRequest?.request_id'),body.request_id);
    held.resolve({jobs:[persisted(body.request_id)]});await reconciliation;console.log('Full-reload held-reconciliation negative/positive probe passed.');return;
  }
  const store=storage();let p=page(store);p.intent();const initial=p.submit(),post=p.take('caption-proposals',true);
  assert.equal(JSON.parse(store.data.get(key)).request_id,post.body.request_id,'Exact retry evidence must commit before POST');
  const original=JSON.parse(JSON.stringify(post.body));post.reject(Error('Lost acknowledgement'));await initial;
  // A new JS document, sharing only the real tab storage, restores before held GET.
  p=page(store);assert.deepEqual(JSON.parse(p.run('JSON.stringify(captionProposalPendingRequest)')),original);
  const lookup=p.refresh(),held=p.take('caption-proposals');p.intent({...body,instruction:'Changed after reload'});await p.submit();
  assert.equal(p.requests.length,0,'Held initial reconciliation cannot permit a changed POST');
  held.resolve({jobs:[]});await flush();p.take('caption-proposals/'+original.request_id).reject(Object.assign(Error('Not visible'),{status:404}));await lookup;
  await p.submit();assert.equal(p.requests.length,0);assert.ok(store.data.has(key),'Ambiguous 404 must retain storage');
  // Explicit unchanged repeat only; refused repeats survive another full reload.
  p.intent(original);const refused=p.submit(),repeat=p.take('caption-proposals',true);
  assert.deepEqual(JSON.parse(JSON.stringify(repeat.body)),original);repeat.reject(Object.assign(Error('Busy'),{status:409}));await refused;
  p=page(store);p.intent(original);const retry=p.submit(),retryPost=p.take('caption-proposals',true);
  assert.deepEqual(JSON.parse(JSON.stringify(retryPost.body)),original);
  retryPost.resolve(persisted(original.request_id));await flush();p.take('caption-proposals').resolve({jobs:[persisted(original.request_id)]});await retry;
  assert.equal(store.data.has(key),false);assert.equal(p.run('captionProposalPendingRequest'),null);
  for(const status of ['cancelled','completed','failed','interrupted','generating']) {
    store.data.set(key,JSON.stringify(body));p=page(store);p.intent({...body,instruction:'Later intent'});
    const reconciliation=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(body.request_id,status)]});await reconciliation;
    assert.equal(store.data.has(key),false);const fresh=p.submit(),next=p.take('caption-proposals',true);
    assert.notEqual(next.body.request_id,body.request_id);assert.equal(next.body.instruction,'Later intent');
    next.resolve(persisted(next.body.request_id));await flush();p.take('caption-proposals').resolve({jobs:[persisted(next.body.request_id)]});await fresh;
  }
  // Acknowledged POST + failing GET does not become a definite start refusal.
  p=page(store);p.intent();const accepted=p.submit(),acceptedPost=p.take('caption-proposals',true);
  acceptedPost.resolve(persisted(acceptedPost.body.request_id));await flush();p.take('caption-proposals').reject(Object.assign(Error('GET denied'),{status:403}));await accepted;
  assert.ok(store.data.has(key));store.data.clear();
  for(const failure of ['read','write']) {
    const bad=storage();bad.fail=failure;p=page(bad);p.intent();await p.submit();assert.equal(p.requests.length,0,failure+' failure must prevent any POST');assert.equal(p.$('caption-proposal-submit').disabled,true);
  }
  // A failed removal retains the ID even after authoritative GET; retry clearing is safe.
  store.data.set(key,JSON.stringify(body));p=page(store);store.fail='remove';const failedClear=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await failedClear;
  assert.equal(p.run('captionProposalPendingRequest.request_id'),body.request_id);assert.ok(store.data.has(key));p.intent();await p.submit();assert.equal(p.requests.length,0);
  store.fail='';const clear=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await clear;assert.equal(store.data.has(key),false);
  for(const value of ['{broken',JSON.stringify({...body,credentials:'forbidden'}),'x'.repeat(32769),JSON.stringify({...body,server_url:'http://secret:token@localhost:8765'})]) {
    const bad=storage();bad.data.set(key,value);p=page(bad);p.intent();await p.submit();assert.equal(p.requests.length,0);assert.equal(bad.data.get(key),value,'Invalid recovery evidence must not be silently discarded');
  }
  const privateStore=storage();p=page(privateStore);p.intent({...body,server_url:'http://secret:token@localhost:8765'});await p.submit();assert.equal(p.requests.length,0);assert.equal(privateStore.data.size,0);
  // Shared tab storage belongs to the current intent, including history-restored documents.
  for(const mode of ['history-clear','history-repeat','late-refusal','late-success','held-get']) {
    const shared=storage(),older=page(shared);older.intent();
    const originalStart=older.submit(),oldPost=older.take('caption-proposals',true),oldBody=JSON.parse(JSON.stringify(oldPost.body));
    if(mode!=='late-refusal' && mode!=='late-success'){oldPost.reject(Error('Lost old acknowledgement'));await originalStart;}
    const heldOldLookup=mode==='held-get'?older.refresh():null;
    const heldOldList=heldOldLookup?older.take('caption-proposals'):null;
    older.listeners.pagehide();const newer=page(shared),knownOld=newer.refresh();
    newer.take('caption-proposals').resolve({jobs:[persisted(oldBody.request_id)]});await knownOld;
    newer.run('crypto.randomUUID=()=>"2".repeat(32)');newer.intent({...body,instruction:'Newer unresolved admission'});
    const nextStart=newer.submit(),nextPost=newer.take('caption-proposals',true),nextBody=JSON.parse(JSON.stringify(nextPost.body));nextPost.reject(Error('Lost newer acknowledgement'));await nextStart;
    if(mode==='late-refusal') {
      oldPost.reject(Object.assign(Error('Late first-attempt refusal'),{status:409}));await originalStart;
    } else {
      if(mode==='held-get') {
        heldOldList.resolve({jobs:[persisted(oldBody.request_id)]});await heldOldLookup;
      }
      newer.listeners.pagehide();older.listeners.pageshow();
      assert.equal(older.run('captionProposalPendingRequest.request_id'),nextBody.request_id,'pageshow must synchronously adopt live storage');
      const oldSummary=older.take('caption-proposals');
      if(mode==='history-repeat') {
        older.intent(oldBody);await older.submit();assert.equal(older.requests.length,0,'Stale original repeat cannot overwrite a newer identity');
      }
      if(mode==='late-success') {
        oldPost.resolve(persisted(oldBody.request_id));await flush();
        const afterOldAck=older.take('caption-proposals');
        oldSummary.resolve({jobs:[persisted(oldBody.request_id)]});await flush();
        afterOldAck.resolve({jobs:[persisted(oldBody.request_id)]});await flush();
      } else {oldSummary.resolve({jobs:[persisted(oldBody.request_id)]});await flush();}
      older.take('caption-proposals/'+nextBody.request_id).reject(Object.assign(Error('New admission not visible'),{status:404}));await flush();
      if(mode==='late-success')await originalStart;
    }
    assert.deepEqual(JSON.parse(shared.data.get(key)),nextBody,mode+' must preserve newer exact evidence');
    const fullReload=page(shared);fullReload.intent({...body,instruction:'Changed again'});await fullReload.submit();assert.equal(fullReload.requests.length,0,mode+' must continue blocking changed intent across another reload');
  }
  const pageshowStore=storage();pageshowStore.data.set(key,JSON.stringify(body));p=page(pageshowStore);p.listeners.pagehide();pageshowStore.fail='read';p.listeners.pageshow();await p.submit();assert.equal(p.requests.length,0);assert.equal(p.$('caption-proposal-submit').disabled,true);
  console.log('Caption reload: durable before POST, synchronous restore/held GET, changed-intent refusal, 404/refused repeat retention, exact retry, terminal/active reconciliation, storage read/write/remove/corruption bounds and credential exclusion passed.');
  console.log('Shared tab recovery: history restore/held lookup, stale repeat overwrite, late first-refusal and success ownership, and pageshow storage failure passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
