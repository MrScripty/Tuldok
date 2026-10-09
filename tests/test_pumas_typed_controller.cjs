'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(value=''){this.value=value;this.hidden=true;this.listeners={};this.textContent='';}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
  async fire(event){for(const fn of this.listeners[event]||[])await fn();}
}
const elements=new Map(),events={},prefix=process.env.PUMAS_TYPED_PREFIX||'text-classification-proposal';
for(const name of ['url','model','profile','protocol','seed','capabilities','capability-metadata'])elements.set(prefix+'-'+name,new Element());
const get=name=>elements.get(prefix+'-'+name);
get('url').value='http://127.0.0.1:39019';get('model').value='controlled-text';get('protocol').value='pumas_typed_v1';
let held;
const context=vm.createContext({document:{getElementById:id=>elements.get(id)},window:{addEventListener:(event,fn)=>(events[event]||=[]).push(fn)},
  fetch:()=>new Promise(resolve=>held=resolve),JSON,Error});
vm.runInContext(fs.readFileSync('static/pumas-typed.js','utf8'),context);
const evaluate=source=>vm.runInContext(source,context);
events.DOMContentLoaded.forEach(fn=>fn());
(async()=>{
  assert.equal(get('seed').disabled,true);assert.equal(evaluate('pumasTypedSettings("'+prefix+'").profile'),null);
  let pending=get('capabilities').fire('click');assert.ok(held);
  // No-event catalog mutation must fence both a held success and a held error.
  get('model').value='another-model';held({ok:true,json:async()=>({old:'manifest'})});await pending;
  assert.equal(get('capability-metadata').textContent,'Inspecting selected model capabilities…');
  pending=get('capabilities').fire('click');get('model').value='controlled-text';held({ok:false,json:async()=>({error:'old error'})});await pending;
  assert.notEqual(get('capability-metadata').textContent,'old error');
  pending=get('capabilities').fire('click');await get('profile').fire('input');held({ok:true,json:async()=>({old:'same-value edit'})});await pending;
  assert.equal(get('capability-metadata').hidden,true);
  pending=get('capabilities').fire('click');events.pagehide.forEach(fn=>fn());held({ok:false,json:async()=>({error:'after exit'})});await pending;
  assert.notEqual(get('capability-metadata').textContent,'after exit');events.pageshow.forEach(fn=>fn());
  pending=get('capabilities').fire('click');held({ok:true,json:async()=>({fresh:'manifest'})});await pending;
  assert.deepEqual(JSON.parse(get('capability-metadata').textContent),{fresh:'manifest'});
  get('protocol').value='legacy';await get('protocol').fire('change');assert.equal(get('seed').disabled,false);
  assert.deepEqual(JSON.parse(JSON.stringify(evaluate('pumasTypedSettings("'+prefix+'")'))),{});
  console.log('Typed capabilities exact settings, no-event catalog changes, same-value edits, pagehide, error/success fences and text seed availability passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
