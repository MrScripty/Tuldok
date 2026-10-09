// Held transports exercise the actual collection refresh and dynamic-search controller.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
  constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
  replaceChildren(...rows){this.children=rows;} append(...rows){this.children.push(...rows);} setAttribute(){} querySelectorAll(){return [];} matches(){return false;}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const nodes=new Map(),element=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
const events={},requests=[],recordQueries=[],page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
let holdQuery=false,holdList=false,list=[];
const response=(data,ok=true)=>({ok,status:ok?200:409,json:async()=>data});
const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,location:{hash:'#selection=kept'},confirm:()=>true,
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(event,fn){(events[event]||=[]).push(fn);}},
  fetch:(url,options)=>{
    if(url.endsWith('/grounded/jobs'))return Promise.resolve(response({jobs:[]}));
    if(url.includes('/records?')){recordQueries.push(url);if(!holdQuery)return Promise.resolve(response(page));}
    else if(url.endsWith('/searches')&&!options?.method&&!holdList)return Promise.resolve(response({searches:list}));
    return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
  }
});
for(const file of ['workbench.js','saved-searches.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context,{filename:file});
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const pending=suffix=>{const index=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(index,-1,'Pending '+suffix);return requests.splice(index,1)[0];};
const complete=(suffix,data)=>pending(suffix).resolve(response(data));
const filters=(q='saved')=>({q,kind:'text',task:'text_classification',review:'draft',sort:'name',label:'first\r\nsecond',group:'first\rsecond',rights:'first\nsecond'});
const search=(id,q='saved')=>({id,name:'Search '+id,revision:1,criteria:filters(q),mode:'dynamic',schema_version:1,created_at:'2026-10-08T00:00:00+00:00',updated_at:'2026-10-08T00:00:00+00:00'});
const a='a'.repeat(32),b='b'.repeat(32),sa=search(a),sb=search(b,'newer');
function choose(id){element('saved-search').value=id;}
function unchanged(){assert.equal(run('dirty'),true);assert.equal(run('selected.get("kept").revision'),1);assert.equal(run('releasePreview.preview_token'),'kept-proof');assert.equal(context.location.hash,'#selection=kept');}
(async()=>{
  await flush();element('train').value='100';element('validation').value='0';element('test').value='0';element('split-seed').value='7';element('sort').value='newest';element('exact-filter-format').value='text';
  run('selected.set("kept",{id:"kept",revision:1,source_revision:1});selection();dirty=true;releasePreview={preview_token:"kept-proof"}');
  // No-event input replacement revokes a held Open before any field or query mutation.
  choose(a);const old=run('openSearch()');await run('openSearch()');assert.equal(requests.length,1);
  element('query').value='manual-without-event';const count=recordQueries.length;complete('/'+a,sa);await old;assert.equal(element('query').value,'manual-without-event');assert.equal(recordQueries.length,count);unchanged();
  // Explicit cancel permits a newer Open; old replies have no authority.
  const cancelled=run('openSearch()');await element('cancel-search-open').dispatch('click');choose(b);const newer=run('openSearch()');complete('/'+b,sb);await newer;complete('/'+a,sa);await cancelled;
  assert.equal(element('query').value,'newer');assert.equal(element('group-filter').value,JSON.stringify('first\rsecond'));assert.equal(run('exactFilterFormat'),'json');unchanged();
  // Guard the real refresh after fields have been restored, including no-event edits.
  choose(a);holdQuery=true;const refreshing=run('openSearch()');complete('/'+a,sa);await flush();const query=pending(requests.find(r=>r.url.includes('/records?')).url);
  element('query').value='changed-during-query';query.resolve(response({...page,total:77}));await refreshing;assert.equal(run('page.total'),0);unchanged();holdQuery=false;
  // Malformed/coercible receipts never restore fields or dispatch collection queries.
  const bad=[{...sa,id:7},{...sa,revision:'1'},{...sa,schema_version:true},{...sa,mode:'fixed'},{...sa,criteria:{...sa.criteria,q:'a\nb'}},{...sa,criteria:{...sa.criteria,rights:null}},{...sa,extra:1},{...sa,id:b}];
  for(const receipt of bad){const before=element('query').value,n=recordQueries.length;const opening=run('openSearch()');complete('/'+a,receipt);await opening;assert.equal(element('query').value,before);assert.equal(recordQueries.length,n);unchanged();}
  // Latest list wins; a stale failed list cannot overwrite later status.
  holdList=true;const early=run('refreshSearches()'),late=run('refreshSearches()');const r1=pending('/searches'),r2=pending('/searches');r2.resolve(response({searches:[sb]}));await late;run('searchStatus("newer status")');r1.reject(Error('old list error'));await early;assert.equal(element('saved-search-status').textContent,'newer status');assert.equal(run('savedSearches.has("'+b+'")'),true);
  const duplicated=run('refreshSearches()');complete('/searches',{searches:[sa,sa]});await assert.rejects(duplicated,/Duplicate/);assert.equal(run('savedSearches.has("'+b+'")'),true);holdList=false;
  // Save entered pre-casefold q and decoded exact metadata, never old page criteria.
  choose(b);element('query').value='ß'.repeat(200);element('search-name').value='Entered';element('label-filter').value=JSON.stringify('a\r\nb');element('group-filter').value='';element('rights-filter').value='';
  const writing=element('save-search-form').dispatch('submit');await element('save-search-form').dispatch('submit');assert.equal(requests.length,1);const post=pending('/searches'),body=JSON.parse(post.options.body);assert.equal(body.criteria.q,'ß'.repeat(200));assert.equal(body.criteria.label,'a\r\nb');
  post.reject(Error('lost acknowledgement'));await writing;assert.match(element('saved-search-status').textContent,/unknown/);assert.equal(requests.length,0);unchanged();
  const serverFailure=element('save-search-form').dispatch('submit');pending('/searches').resolve({ok:false,status:500,json:async()=>({error:'Server failure after admission may be uncertain'})});await serverFailure;assert.match(element('saved-search-status').textContent,/unknown.*inspect/);assert.equal(requests.length,0);unchanged();
  // Departure fences both a held write and Open, including control cleanup after return.
  const leavingWrite=element('save-search-form').dispatch('submit'),wp=pending('/searches');const leavingOpen=run('openSearch()'),gp=pending('/'+b);
  for(const fn of events.pagehide)fn({});run('searchStatus("after departure")');wp.resolve(response(sb));gp.resolve(response(sb));await Promise.all([leavingWrite,leavingOpen]);assert.equal(element('saved-search-status').textContent,'after departure');assert.equal(element('save-search').disabled,false);unchanged();
  for(const fn of events.pageshow)fn({persisted:true});await flush();assert.equal(requests.length,0);
  // Late admitted create cannot overwrite a newer dropdown choice or reapply filters.
  list=[sa,sb];await run('refreshSearches()');choose(a);const staleWrite=element('save-search-form').dispatch('submit');choose(b);await element('saved-search').dispatch('change');run('searchStatus("new choice")');complete('/searches',sa);await staleWrite;assert.equal(element('saved-search').value,b);assert.equal(element('saved-search-status').textContent,'new choice');unchanged();
  const deleting=element('delete-search').dispatch('click');list=[sa];complete('/'+b+'/delete',{deleted:b});await deleting;assert.equal(run('savedSearches.has("'+b+'")'),false);assert.match(element('saved-search-status').textContent,/deleted/);unchanged();
  console.log('Dynamic search held Open/list/write/query, strict receipts, raw-input/lifecycle fences and unchanged fixed selection/editor/proof passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
