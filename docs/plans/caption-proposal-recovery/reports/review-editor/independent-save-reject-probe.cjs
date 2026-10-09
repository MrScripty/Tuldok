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

const trace=[];
(async()=>{
  await flush();run('showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();
  element('caption').value='Independent saved caption';await element('editor').dispatch('input');
  const save=element('editor').dispatch('submit'),post=take('/records/'+row.id);
  trace.push({phase:'save_pending',parent:JSON.parse(post.options.body).revision,current:run('current.revision'),dirty:run('dirty')});
  const reject=button('Reject caption proposal').dispatch('click');
  resolve('/caption-proposals/decide/'+job.id,{job:{...job,status:'rejected'},record:null,changed:true});await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await reject;
  const acknowledged={...row,revision:3,annotation:{caption:'Independent saved caption'},review:'draft'};
  post.resolve(response(acknowledged));await flush();
  const refreshQuery=requests.findIndex(r=>r.url.endsWith('/caption-proposals'));
  if(refreshQuery>=0)requests.splice(refreshQuery,1)[0].resolve(response({jobs:[{...job,status:'rejected'}]}));
  await save;
  trace.push({phase:'save_ack_after_reject',current:run('current.revision'),dirty:run('dirty'),caption:element('caption').value});
  assert.equal(run('current.revision'),3,'Successful annotation save ACK must adopt committed revision after Reject');assert.equal(run('dirty'),false);
  element('caption').value='Independent subsequent save';await element('editor').dispatch('input');
  const next=element('editor').dispatch('submit'),nextPost=take('/records/'+row.id),nextBody=JSON.parse(nextPost.options.body);
  trace.push({phase:'next_save_parent',revision:nextBody.revision,caption:nextBody.annotation.caption});assert.equal(nextBody.revision,3);
  nextPost.resolve(response({...acknowledged,revision:4,annotation:{caption:nextBody.annotation.caption}}));await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await next;
  assert.equal(run('current.revision'),4);assert.equal(run('dirty'),false);
  // Reverse ACK order: annotation success arrives while Reject is still pending.
  run('showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();element('caption').value='Reverse-order caption';await element('editor').dispatch('input');
  const earlier=element('editor').dispatch('submit'),earlierPost=take('/records/'+row.id),rejectHeld=button('Reject caption proposal').dispatch('click'),held=take('/caption-proposals/decide/'+job.id);
  earlierPost.resolve(response({...acknowledged,annotation:{caption:'Reverse-order caption'}}));await flush();resolve('/caption-proposals',{jobs:[job]});await earlier;
  trace.push({phase:'save_ack_before_reject',current:run('current.revision'),dirty:run('dirty'),reject_pending:run('captionProposalBusy')});assert.equal(run('current.revision'),3);assert.equal(run('dirty'),false);
  held.resolve(response({job:{...job,status:'rejected'},record:null,changed:true}));await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await rejectHeld;
  assert.equal(run('current.revision'),3);assert.equal(run('dirty'),false);assert.equal(requests.length,0);
  for(const fn of listeners.pagehide||[])fn();
  console.log(JSON.stringify({result:'PASS',trace}));
})().catch(error=>{console.error(JSON.stringify({result:'FAIL',trace,error:error.message}));process.exitCode=1;});
