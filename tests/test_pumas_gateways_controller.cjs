// Held-response ownership evidence; the browser suite exercises production HTTP.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
  constructor(value=''){this.value=value;this.listeners={};this.children=[];this.disabled=false;}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);}
  async fire(type){for(const fn of this.listeners[type]||[])await fn({type});}
  replaceChildren(...values){this.children=values;this.value=values[0]?.value||'';}
}
const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const requests=[],events={};
const context=vm.createContext({console,$,textClassificationProposalModelEpoch:0,textClassificationProposalFormEpoch:0,captionProposalModelEpoch:0,modelEpoch:0,Option:class{constructor(text,value){this.textContent=text;this.value=value;}},Event:class{constructor(type){this.type=type;}},
  window:{addEventListener:(name,fn)=>events[name]=fn},api:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
vm.runInContext(fs.readFileSync(path.join(root,'static/pumas-gateways.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context),value=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/pumas-http-pr51/advertisement.json')));
const row={advertisement:value,server_url:value.endpoint,observed_sha256:'a'.repeat(64)};
function next(){assert.ok(requests.length);return requests.shift();}
async function scan(){const p=$('pumas-gateway-scan').fire('click');next().resolve({gateways:[row]});await p;$('pumas-gateway-choice').value=row.server_url;await $('pumas-gateway-choice').fire('change');}
(async()=>{
  $('pumas-gateway-target').value='caption';
  const first=$('pumas-gateway-scan').fire('click');await $('pumas-gateway-scan').fire('click');assert.equal(requests.length,1);
  next().resolve({gateways:[row]});await first;assert.equal($('caption-proposal-url').value,'');
  $('pumas-gateway-choice').value=row.server_url;await $('pumas-gateway-choice').fire('change');
  assert.equal($('pumas-gateway-use').disabled,false);
  for(const [kind,url] of [['caption','caption-proposal-url'],['classification','text-classification-proposal-url'],['rewrite','grounded-url']]){
    $('pumas-gateway-target').value=kind;await $('pumas-gateway-target').fire('change');
    const held=$('pumas-gateway-use').fire('click'),request=next();
    $(url).value='http://127.0.0.1:30000';await $(url).fire('input');request.resolve(row);await held;
    assert.equal($(url).value,'http://127.0.0.1:30000','Later URL input owns configuration');
    const model=$(url.replace(/-url$/,'-model'));model.value='later-model';
    const heldModel=$('pumas-gateway-use').fire('click'),modelRequest=next();await model.fire('change');modelRequest.resolve(row);await heldModel;
    assert.equal($(url).value,'http://127.0.0.1:30000');assert.equal(model.value,'later-model');
    const restored=$('pumas-gateway-use').fire('click'),restoredRequest=next();
    $(url).value='http://127.0.0.1:33333';model.value='restored-frozen-model';restoredRequest.resolve(row);await restored;
    assert.equal($(url).value,'http://127.0.0.1:33333','Programmatic no-event restore owns configuration');assert.equal(model.value,'restored-frozen-model');
    if(kind==='classification'){
      const same=$('pumas-gateway-use').fire('click'),sameRequest=next();run('++textClassificationProposalFormEpoch');sameRequest.resolve(row);await same;
      assert.equal($(url).value,'http://127.0.0.1:33333','Same-value frozen settings restoration fences the old choice');
    }
    let inputEvents=0;$(url).addEventListener('input',()=>inputEvents++);
    const using=$('pumas-gateway-use').fire('click');await $('pumas-gateway-use').fire('click');assert.equal(requests.length,1);
    next().resolve(row);await using;assert.equal($(url).value,row.server_url);assert.equal(inputEvents,1);
  }
  const stale=$('pumas-gateway-use').fire('click'),staleRequest=next();
  const changed=structuredClone(row);changed.advertisement.service_generation='different-service';staleRequest.resolve(changed);await stale;
  assert.equal(run('pumasGateways.length'),0);assert.match($('pumas-gateway-status').textContent,/changed/);
  await scan();const old=$('pumas-gateway-use').fire('click'),oldRequest=next();
  events.pagehide();events.pageshow();const newer=$('pumas-gateway-scan').fire('click'),newerRequest=next();
  oldRequest.resolve(row);await old;assert.equal($('pumas-gateway-scan').disabled,true,'Old finally cannot release a newer operation');
  newerRequest.resolve({gateways:[row]});await newer;assert.equal($('pumas-gateway-scan').disabled,false);
  $('pumas-gateway-choice').value=row.server_url;await $('pumas-gateway-choice').fire('change');
  const purpose=$('pumas-gateway-use').fire('click'),purposeRequest=next();$('pumas-gateway-target').value='caption';await $('pumas-gateway-target').fire('change');
  $('grounded-url').value='retain';purposeRequest.resolve(row);await purpose;assert.equal($('grounded-url').value,'retain');
  const failed=$('pumas-gateway-use').fire('click');next().reject(Error('Unavailable descriptor'));await failed;
  assert.match($('pumas-gateway-status').textContent,/Unavailable/);assert.equal(requests.length,0);
  console.log('Gateway chooser: explicit configuration only; three URL/model and no-event restore fences, same-value owner epoch, generation drift, later purpose, duplicate clicks and pagehide/new-operation ownership pass.');
})().catch(error=>{console.error(error);process.exitCode=1;});
