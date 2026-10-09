// Production controller with deterministic delayed HTTP, no duplicate implementation.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
 constructor(){this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
 addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
 replaceChildren(...children){this.children=children;} append(...children){this.children.push(...children);} setAttribute(){}
 matches(){return false;} querySelectorAll(){return [];} async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const requests=[],response=data=>({ok:true,json:async()=>data});
const emptyPage={items:[],total:0,criteria:{q:''},analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,confirm:()=>false,
 document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(){}},
 fetch:(url,options)=>url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise(resolve=>requests.push({url,options,resolve}))});
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
for(const file of ['workbench.js','curation.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const resolve=(suffix,data,ok=true)=>{const index=requests.findIndex(r=>r.url.includes(suffix));assert.notEqual(index,-1,suffix);requests.splice(index,1)[0].resolve({...response(data),ok});};
const row={id:'a'.repeat(32),name:'Fictional record',kind:'text',task:'text_classification',review:'draft',revision:1,source_revision:1,groups:['g'],rights_note:'unknown',annotation:null,text:'fictional',provenance:{}};
const report={scope:'filtered',filters:{q:''},category:'unlabeled',items:[row],total:41,offset:0,limit:40,view_token:'x'.repeat(64),analysis:{records:41,duplicate_content_records:0,unlabeled:41,missing_sources:0,unknown_rights:41},reference_counts:{stale:0,source_deleted:0,missing_record:0}};
(async()=>{
 element('curation-scope').value='filtered';element('curation-category').value='unlabeled';
 resolve('/records?',emptyPage);await flush();context.row=row;run('selected.set(row.id,row);selection(true)');
 const fixed=run('JSON.stringify(releaseBody().items)');
 const first=run('curationLoad(0,true)');await run('curationLoad(0,true)');assert.equal(requests.length,1,'repeat fence');
 element('curation-category').value='unknown_rights';await element('curation-category').dispatch('change');
 const second=run('curationLoad(0,true)');
 // Resolve newer response before obsolete request.
 requests.pop().resolve(response({...report,category:'unknown_rights'}));await second;
 resolve('/curation',report);await first;assert.equal(run('curationReport.category'),'unknown_rights');
 assert.equal(run('JSON.stringify(releaseBody().items)'),fixed);
 const paging=run('curationLoad(40)');assert.equal(JSON.parse(requests[0].options.body).view_token,report.view_token);
 resolve('/curation',{error:'Diagnostic facts changed. Refresh diagnostics before paging.'},false);await paging;
 assert.equal(run('curationReport'),null);assert.equal(element('curation-next').disabled,true);
 const delayed=run('curationLoad(0,true)');run('selected.clear();selection(true)');
 assert.equal(run('curationBusy'),true,'filtered scope independent of selection');resolve('/curation',report);await delayed;
 element('curation-scope').value='selected';await element('curation-scope').dispatch('change');run('selected.set(row.id,row);selection(true)');
 const selectionRead=run('curationLoad(0,true)');run('selected.clear();selection(true)');resolve('/curation',{...report,scope:'selected'});await selectionRead;
 assert.equal(run('curationReport'),null,'late previous selected IDs ignored');
 element('curation-scope').value='filtered';await element('curation-scope').dispatch('change');
 const old=run('curationLoad(0,true)');const querying=run('refresh()');assert.equal(element('curation-refresh').disabled,true);
 await run('curationLoad(0,true)');assert.equal(requests.length,2,'pending collection query fences diagnostic start');
 resolve('/records?',{...emptyPage,criteria:{q:'new'}});await querying;
 resolve('/curation',report);await old;assert.equal(run('curationReport'),null);
 const refreshed=run('curationLoad(0,true)');assert.deepEqual(JSON.parse(requests[0].options.body).filters,{q:'new'});
 resolve('/curation',report);await refreshed;
 run('showRecord(row);dirty=true');await run('curationInspect(row,curationEpoch)');assert.equal(requests.length,0,'dirty cancellation sends no inspection');
 run('dirty=false');const inspection=run('curationInspect(row,curationEpoch)');
 resolve('/records/',{...row,revision:2});await inspection;assert.equal(run('current.revision'),1);assert.equal(run('curationReport'),null,'changed record requires refresh');
 const read=run('curationLoad(0,true)');resolve('/curation',report);await read;
 const inspect=run('curationInspect(row,curationEpoch)');run('markDirty()');resolve('/records/',row);await inspect;
 assert.equal(run('dirty'),true,'late inspect cannot replace later edit');
 assert.equal(requests.length,0);
 console.log('Curation repeat/delayed category and selected scope, filtered independence, pending collection query, freshness paging, dirty cancellation, changed record and later edit fences passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
