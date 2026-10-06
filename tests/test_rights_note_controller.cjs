'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
 constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
 addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);} replaceChildren(...children){this.children=children;} append(...children){this.children.push(...children);} setAttribute(){}
 matches(selector){return selector==='form'&&['editor','filters'].includes(this.id);}querySelectorAll(){return [];}
 async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const windowListeners=new Map();
const beforeUnload=()=>{let prevented=false;const event={preventDefault(){prevented=true;}};for(const fn of windowListeners.get('beforeunload')||[])fn(event);return prevented;};
const requests=[],response=data=>({ok:true,json:async()=>data});
const emptyPage={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,confirm:()=>false,location:{hash:''},history:{pushState(){}},
 document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(name,fn){if(!windowListeners.has(name))windowListeners.set(name,[]);windowListeners.get(name).push(fn);}},
 fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(emptyPage)):url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise(resolve=>requests.push({url,options,resolve}))});
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
for(const file of ['workbench.js','saved-selections.js','rights-note.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const resolve=(suffix,data,ok=true)=>{const index=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(index,-1,suffix);requests.splice(index,1)[0].resolve({...response(data),ok});};
const row={id:'a'.repeat(32),name:'Fictional record',kind:'text',text:'fictional',task:'text_classification',annotation:{label:'intent'},review:'human_reviewed',revision:2,source_revision:1,groups:['g'],provenance:{rights:'Origin note'}};
const after={...row,revision:3,provenance:{...row.provenance,rights_note_correction:{note:'Corrected note',revision:3}}};
const fixed={id:'fixed',name:'Fixed',items:[row],member_count:1},loaded={selection:fixed,members:[{item:row,status:'ok'}],current:true};
(async()=>{
 resolve('/selections',{selections:[fixed]});await flush();context.row=row;context.after=after;
 run('showRecord(row);selected.set(row.id,row);selection(true)');element('saved-selection').value='';
 const pairs=run('JSON.stringify(releaseBody().items)');assert.equal(beforeUnload(),false,'unchanged loaded note does not warn');
 element('rights-note-value').value='  Origin note  ';await element('rights-note-value').dispatch('input');assert.equal(beforeUnload(),false,'normalized unchanged edit does not warn');
 element('rights-note-value').value='changed';await element('rights-note-value').dispatch('input');assert.equal(run('dirty'),false);assert.equal(run('rightsDirty'),true);assert.equal(beforeUnload(),true,'rights-only draft must prevent beforeunload');
 await run('openRecord("other")');assert.equal(requests.length,0,'note draft participates in navigation guard');
 await element('rights-note-cancel').dispatch('click');assert.equal(run('rightsDirty'),false);assert.equal(element('rights-note-value').value,'Origin note');assert.equal(requests.length,0);assert.equal(beforeUnload(),false,'canceled rights draft is clean');
 const unchanged=element('rights-note-form').dispatch('submit');resolve('/rights/'+row.id,{record:row,changed:false});await unchanged;assert.equal(run('current.revision'),2);assert.ok(element('rights-note-status').textContent.includes('unchanged'));
 run('dirty=true');assert.equal(beforeUnload(),true,'annotation draft remains guarded');await element('rights-note-form').dispatch('submit');assert.equal(requests.length,0,'annotation draft blocks note save');run('dirty=false');
 element('rights-note-value').value='Corrected note';await element('rights-note-value').dispatch('input');await element('editor').dispatch('submit');assert.equal(requests.length,0,'note draft blocks annotation save');
 run('releasePreview={eligible:true,preview_token:"old"}');const saving=element('rights-note-form').dispatch('submit');await element('rights-note-form').dispatch('submit');assert.equal(requests.length,1,'repeated submit admits once');
 resolve('/rights/'+row.id,{record:after,changed:true});await saving;assert.equal(run('current.revision'),3);assert.equal(beforeUnload(),false,'successful note save is clean');assert.equal(run('releasePreview'),null);assert.equal(run('JSON.stringify(releaseBody().items)'),pairs,'correction cannot adopt revision pairs');
 // A held saved-set response cannot claim known obsolete revisions are current.
 context.loaded=structuredClone(loaded);run('rightsValidateSavedResult(loaded)');assert.equal(context.loaded.current,false);assert.equal(context.loaded.members[0].status,'stale');
 // Later editor input owns the UI when an earlier correction completes.
 const next={...after,revision:4,provenance:{...after.provenance,rights_note_correction:{note:'Second note',revision:4}}};
 element('rights-note-value').value='Second note';await element('rights-note-value').dispatch('input');const delayed=element('rights-note-form').dispatch('submit');
 element('label').value='later annotation';await element('editor').dispatch('input');resolve('/rights/'+row.id,{record:next,changed:true});await delayed;
 assert.equal(run('current.revision'),3);assert.equal(run('dirty'),true);assert.equal(beforeUnload(),true,'late annotation edit stays guarded after older note completion');assert.equal(element('label').value,'later annotation');assert.equal(run('JSON.stringify(releaseBody().items)'),pairs);
 // Conflict keeps note draft and revision; no automatic replay.
 run('dirty=false');const stale=element('rights-note-form').dispatch('submit');resolve('/rights/'+row.id,{error:'This record or source changed. Reload before correcting the note.'},false);await stale;
 assert.equal(run('current.revision'),3);assert.equal(element('rights-note-value').value,'Second note');assert.equal(requests.length,0);
 // CR/LF must remain lossless in JSON mode; format switch cannot silently normalize.
 context.cr={...row,provenance:{rights:'first\r\nsecond\rthird\n😀'}};run('showRecord(cr)');assert.equal(element('rights-note-format').value,'json');assert.equal(run('rightsValue()'),'first\r\nsecond\rthird\n😀');
 element('rights-note-format').value='text';await element('rights-note-format').dispatch('change');assert.equal(element('rights-note-format').value,'json');
 element('rights-note-value').value='null';await element('rights-note-value').dispatch('input');await element('rights-note-form').dispatch('submit');assert.equal(requests.length,0);
 // Valid FEFF survives Python boundaries and must not silently change on untouched save.
 context.feff={...row,provenance:{rights:'\ufeffowner\ufeff'}};run('showRecord(feff)');
 assert.equal(element('rights-note-value').value,'\ufeffowner\ufeff');assert.equal(run('rightsValue()'),'\ufeffowner\ufeff');assert.equal(beforeUnload(),false);
 const untouched=element('rights-note-form').dispatch('submit');assert.equal(JSON.parse(requests[0].options.body).note,'\ufeffowner\ufeff');resolve('/rights/'+row.id,{record:context.feff,changed:false});await untouched;assert.equal(run('current.revision'),2);assert.equal(beforeUnload(),false);
 context.pythonOnly={...row,provenance:{rights:'\u0085owner\u001c\u001f'}};run('showRecord(pythonOnly)');assert.equal(element('rights-note-value').value,'owner');
 element('rights-note-value').value='\u0085owner\u001c\u001f';await element('rights-note-value').dispatch('input');assert.equal(run('rightsDirty'),false);assert.equal(beforeUnload(),false);
 const boundaryNoop=element('rights-note-form').dispatch('submit');assert.equal(JSON.parse(requests[0].options.body).note,'owner');resolve('/rights/'+row.id,{record:context.pythonOnly,changed:false});await boundaryNoop;assert.equal(run('current.provenance.rights'),'\u0085owner\u001c\u001f');
 // Compare actual Python against production JS for every server whitespace code point and valid FEFF/ZWSP/data controls.
 const {execFileSync}=require('node:child_process');const whitespace=JSON.parse(execFileSync('python3',['-c','import json;print(json.dumps([chr(n) for n in range(0x110000) if chr(n).isspace()]))'],{encoding:'utf8'}));
 const samples=whitespace.map(c=>c+'\ufeffowner\ufeff'+c).concat(['\ufeffowner\ufeff','\u200bowner\u200b','owner\u0085inside','\u001cowner\u001f']);
 const expected=JSON.parse(execFileSync('python3',['-c','import json,sys;print(json.dumps([s.strip() for s in json.load(sys.stdin)]))'],{input:JSON.stringify(samples),encoding:'utf8'}));
 context.stripSamples=samples;assert.deepEqual(JSON.parse(run('JSON.stringify(stripSamples.map(rightsStrip))')),expected);
 console.log('Rights-only beforeunload draft/unchanged/canceled/saved and annotation guards, rights-note cancellation/no-op, separate annotation drafts, repeated submits, fixed pairs/proof invalidation, known stale saved responses, delayed editor intent, conflict retention, CR/LF and Unicode controller checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
