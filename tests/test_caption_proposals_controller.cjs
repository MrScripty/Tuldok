'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
class Element {
  constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}replaceChildren(...children){this.children=children;}append(...children){this.children.push(...children);}setAttribute(){}
  matches(selector){return selector==='form'&&['editor','filters'].includes(this.id);}querySelectorAll(){return [];}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const listeners={},requests=[],timers=new Map();let timerId=0;
const response=(data,ok=true,status=200)=>({ok,status,json:async()=>data});
const empty={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const context=vm.createContext({console,URLSearchParams,structuredClone,crypto,confirm:()=>false,location:{hash:''},history:{pushState(){}},
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(name,fn){(listeners[name]||=[]).push(fn);}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(empty)):url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
for(const file of ['workbench.js','caption-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const take=suffix=>{const index=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(index,-1,suffix);return requests.splice(index,1)[0];};
const resolve=(suffix,data)=>take(suffix).resolve(response(data));
const row={id:'a'.repeat(32),name:'Image A',kind:'image',task:'image_caption',annotation:{caption:'Earlier'},review:'human_reviewed',revision:2,source_revision:1,groups:['g'],provenance:{rights:'Authored'}};
const other={...row,id:'b'.repeat(32),name:'Image B'};
const after={...row,revision:3,annotation:{caption:'Proposed'},review:'draft'};
let job={id:'c'.repeat(32),revision:3,status:'completed',source:row,annotation:{caption:'Proposed'},config:{model:'fixture'},error:''};
context.row=row;context.other=other;context.after=after;
const button=label=>element('caption-proposal-jobs').children.flatMap(section=>section.children).find(child=>child.textContent===label);
(async()=>{
  await flush();run('showRecord(row);selected.set(row.id,row);selection(true)');resolve('/caption-proposals',{jobs:[job]});await flush();
  assert.equal(button('Apply as draft').type,'button');const pairs=run('JSON.stringify(releaseBody().items)');
  // URL changes revoke a pending catalog response.
  element('caption-proposal-url').value='http://127.0.0.1:1000';const models=element('caption-proposal-models').dispatch('click');
  element('caption-proposal-url').value='http://127.0.0.1:2000';await element('caption-proposal-url').dispatch('input');resolve('/api/generation/prompt-models',{models:[{id:'old',name:'Old'}]});await models;
  assert.equal(element('caption-proposal-model').children.length,0);
  // Two starts share one pending action; a lost start is reconciled by GET only.
  element('caption-proposal-model').value='fixture';element('caption-proposal-guidance').value='Visible pixels';element('caption-proposal-seed').value='42';
  const start=element('caption-proposal-form').dispatch('submit');await element('caption-proposal-form').dispatch('submit');
  assert.equal(requests.length,1);const request=take('/caption-proposals'),body=JSON.parse(request.options.body);request.reject(Error('Lost start acknowledgement'));await start;
  assert.equal(run('captionProposalPendingRequest.request_id'),body.request_id);
  const reconcile=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[{...job,id:body.request_id,status:'generating'}]});await reconcile;
  assert.equal(run('captionProposalPendingRequest'),null);assert.equal(requests.length,0);assert.equal(timers.size,1);
  const completed=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[job]});await completed;assert.equal(timers.size,0);
  // Application acknowledgement cannot discard newer local editor input or replace fixed pairs.
  run('releasePreview={eligible:true,preview_token:"old"}');const apply=button('Apply as draft').dispatch('click');await button('Apply as draft').dispatch('click');
  assert.equal(requests.length,1);element('caption').value='Later local edit';await element('editor').dispatch('input');
  resolve('/caption-proposals/decide/'+job.id,{record:after,job:{...job,status:'applied'},changed:true});await flush();resolve('/caption-proposals',{jobs:[{...job,status:'applied'}]});await apply;
  assert.equal(run('current.revision'),2);assert.equal(run('dirty'),true);assert.equal(element('caption').value,'Later local edit');assert.equal(run('releasePreview'),null);assert.equal(run('JSON.stringify(releaseBody().items)'),pairs);
  // Apply is blocked while there are unsaved edits.
  run('captionProposalJobs=[];captionProposalRendered="";dirty=false;showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();run('dirty=true');await button('Apply as draft').dispatch('click');assert.equal(requests.length,0);run('dirty=false');
  // Navigating to another image owns the editor when an earlier application finishes.
  const navigationApply=button('Apply as draft').dispatch('click');run('showRecord(other)');const heldRefresh=take('/caption-proposals');
  resolve('/caption-proposals/decide/'+job.id,{record:after,job:{...job,status:'applied'},changed:true});await flush();heldRefresh.resolve(response({jobs:[job]}));await flush();resolve('/caption-proposals',{jobs:[{...job,status:'applied'}]});await navigationApply;
  assert.equal(run('current.id'),other.id);assert.equal(run('current.annotation.caption'),'Earlier');
  // A lost application is never replayed automatically. Refresh exposes the persisted receipt.
  run('showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();const lost=button('Apply as draft').dispatch('click');take('/caption-proposals/decide/'+job.id).reject(Error('Lost application acknowledgement'));await lost;
  assert.equal(requests.length,0);assert.ok(element('caption-proposal-status').textContent.includes('acknowledgement'));
  const receipt=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[{...job,status:'applied',application:{revision:3}}]});await receipt;assert.equal(button('Apply as draft'),undefined);assert.ok(button('Open applied caption'));
  // Page exit fences late polling and model responses, and removes the poll timer.
  const pendingPoll=element('caption-proposal-refresh').dispatch('click');for(const fn of listeners.pagehide||[])fn();resolve('/caption-proposals',{jobs:[{...job,status:'generating'}]});await pendingPoll;
  assert.equal(timers.size,0);assert.equal(run('captionProposalJobs[0].status'),'applied');
  for(const fn of listeners.pageshow||[])fn();resolve('/caption-proposals',{jobs:[{...job,status:'generating'}]});await flush();assert.equal(timers.size,1);
  for(const fn of listeners.pagehide||[])fn();assert.equal(timers.size,0);assert.equal(requests.length,0);
  console.log('Caption controller duplicate actions, exact request recovery, editor/selection/navigation ownership and polling lifecycle passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
