// Local controller/lifecycle checks; the separate browser test supplies actual HTTP/ZIP evidence.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
class Element {
  constructor(){this.children=[];this.listeners={};this.attrs={};this.dataset={};this.value='';this.files=[];this.textContent='';this.disabled=false;}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(key,value){this.attrs[key]=value;}
  querySelectorAll(){return this.controls||[];}
  emit(name){return Promise.all((this.listeners[name]||[]).map(fn=>fn({preventDefault(){}})));}
}
const elements=new Map(),el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const requests=[],events={};let refreshes=0;
const context=vm.createContext({AbortController,TextEncoder,Uint8Array,crypto:crypto.webcrypto,console,structuredClone,
  btoa:value=>Buffer.from(value,'binary').toString('base64'),$:el,current:null,editorEpoch:0,dirty:false,rightsBusy:false,
  document:{createElement:()=>new Element()},window:{addEventListener:(name,fn)=>events[name]=fn},
  markDirty:()=>{context.dirty=true;context.editorEpoch++;el('record-review').value='draft';},
  fetch:(route,options)=>new Promise(resolve=>requests.push({route,options,resolve})),
  refresh:async live=>{if(!live||live())refreshes++;}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/retrieval-binary.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
async function until(check){for(let i=0;i<50;i++){if(check())return;await flush();}throw Error('Controller wait failed');}
const id=c=>c.repeat(32),reference=(c,revision=2)=>({id:id(c),revision,source_revision:1});
const row={id:id('c'),kind:'text',task:'text_retrieval_binary',revision:2,source_revision:1,review:'human_reviewed',parents:[id('a'),id('b')],annotation:{role:'query',note:'Owned query note',judgments:[{document:reference('a'),relevance:'relevant'},{document:reference('b'),relevance:'unjudged'}]},provenance:{rights:'unknown'}};
function show(value){context.current=value;context.fixture=value;el('task').value=value.task;context.dirty=false;run('retrievalBinaryShown(fixture)');}
function reply(request,value,status=200){request.resolve({ok:status<400,json:async()=>value});}
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
function queryFields(){for(const [key,value] of Object.entries({name:' Query QA ',text:'  Cafe\u0301\r\n query ',group:' source-family ',rights:' unknown ',judgments:JSON.stringify(row.annotation.judgments)}))el('retrieval-binary-query-'+key).value=value;}
function rawAck(request){const body=JSON.parse(request.options.body),canonical=body.text.replace(/\r\n?/g,'\n').normalize('NFC');return {id:id('d'),kind:'text',task:'text_classification',annotation:null,review:'draft',revision:1,source_revision:1,source_available:true,text:canonical,content_hash:hash(canonical),source_sha256:hash(body.text),name:body.name.trim(),groups:body.groups,parents:body.judgments.map(v=>v.document.id),provenance:{rights:body.rights.trim(),acquisition:{format:'text_retrieval_binary_query_v2',declared_judgments:body.judgments}}};}
function nativeAck(request){
  const body=JSON.parse(request.options.body),oldDoc=id('a'),oldQuery=id('b'),newDoc=id('e'),newQuery=id('f');
  const oldRows=[{id:oldDoc,name:'Doc',text:'Native doc',content_hash:hash('Native doc'),parents:[],annotation:{role:'document',note:'Original doc note'}},{id:oldQuery,name:'Query',text:'Native query',content_hash:hash('Native query'),parents:[oldDoc],annotation:{role:'query',note:'Original query note',judgments:[{document:reference('a',4),relevance:'not_relevant'}]}}];
  const records=oldRows.map((original,i)=>({id:i?newQuery:newDoc,name:original.name,text:original.text,content_hash:original.content_hash,source_sha256:original.content_hash,kind:'text',task:'text_retrieval_binary',review:'draft',revision:1,source_revision:1,source_available:true,source_lineage_known:true,source_split:'train',parents:i?[newDoc]:[],annotation:i?{role:'query',note:original.annotation.note,judgments:[{document:{id:newDoc,revision:1,source_revision:1},relevance:'not_relevant'}]}:original.annotation,provenance:{rights:'unknown',acquisition:{format:'native_retrieval_binary_v2',release_sha256:body.sha256,upstream_record:original,source_family:oldDoc,source_split:'train'}}}));
  return {records,id_map:{[oldDoc]:newDoc,[oldQuery]:newQuery},release_sha256:body.sha256};
}
(async()=>{
  context.value=row.annotation.judgments;assert.equal(run('retrievalBinaryJudgments(value).length'),2);
  for(const malformed of [[],[{document:reference('a'),relevance:0}],[{document:{...reference('a'),revision:true},relevance:'relevant'}],[{document:{...reference('a'),revision:Number.MAX_SAFE_INTEGER+1},relevance:'relevant'}],[...row.annotation.judgments,row.annotation.judgments[0]],[{document:reference('a'),relevance:'negative'}],[{document:{...reference('a'),extra:1},relevance:'unjudged'}]]){context.value=malformed;assert.throws(()=>run('retrievalBinaryJudgments(value)'));}
  show(row);assert.equal(el('retrieval-binary-judgments').children.length,2);assert.equal(el('retrieval-binary-note').value,'Owned query note');
  const select=el('retrieval-binary-judgments').children[0].children[1];select.value='not_relevant';await select.emit('change');assert.equal(run('retrievalBinaryRows[0].relevance'),'not_relevant');assert.equal(row.annotation.judgments[0].relevance,'relevant');assert.equal(el('record-review').value,'draft');
  el('retrieval-binary-note').value='😀'.repeat(4000);assert.equal(run('Array.from(retrievalBinaryAnnotation().note).length'),4000);el('retrieval-binary-note').value='😀'.repeat(4001);assert.throws(()=>run('retrievalBinaryAnnotation()'));el('retrieval-binary-note').value='  ';assert.throws(()=>run('retrievalBinaryAnnotation()'));
  show({...row,task:'text_retrieval',annotation:{role:'query',note:'V1',positive_refs:[reference('a')]}});assert.equal(run('retrievalBinaryRows.length'),0);assert.equal(el('retrieval-binary-controls').hidden,true);
  show({...row,task:'text_classification',annotation:null,provenance:{acquisition:{format:'text_retrieval_binary_query_v2',declared_judgments:row.annotation.judgments}}});assert.equal(run('retrievalBinaryRows.length'),2);assert.equal(el('retrieval-binary-role').value,'query');
  show(row);run('retrievalBinaryRefresh(retrievalBinaryRows[0])');const read=requests.shift();assert.throws(()=>run('retrievalBinaryAnnotation()'));const document={...row,id:id('a'),annotation:{role:'document',note:'Reviewed doc'},revision:3,source_available:true,source_lineage_known:true};reply(read,document);await flush();assert.equal(run('retrievalBinaryRows[0].document.revision'),3);assert.equal(run('retrievalBinaryRows[0].relevance'),'relevant');assert.equal(el('record-review').value,'draft');
  show(row);run('retrievalBinaryRefresh(retrievalBinaryRows[0])');reply(requests.shift(),{...document,source_lineage_known:false});await flush();assert.equal(run('retrievalBinaryRows[0].document.revision'),2);assert.match(el('retrieval-binary-status').textContent,/known source lineage/);
  show(row);run('retrievalBinaryRefresh(retrievalBinaryRows[0])');const stale=requests.shift();el('retrieval-binary-note').value='Later note';await el('retrieval-binary-note').emit('input');assert.equal(stale.options.signal.aborted,true);assert.equal(run('retrievalBinaryReads.size'),0);reply(stale,document);await flush();assert.equal(run('retrievalBinaryRows[0].document.revision'),2);assert.equal(el('retrieval-binary-note').value,'Later note');
  show(row);run('retrievalBinaryRefresh(retrievalBinaryRows[0])');const old=requests.shift();show({...document,id:id('b')});reply(old,{error:'Late error'},404);await flush();assert.equal(el('retrieval-binary-note').value,'Reviewed doc');assert.ok(!el('retrieval-binary-status').textContent.includes('Late error'));
  show(row);queryFields();context.dirty=true;await el('retrieval-binary-query-form').emit('submit');await until(()=>requests.length);await el('retrieval-binary-query-form').emit('submit');assert.equal(requests.length,1);const admission=requests.shift();reply(admission,rawAck(admission));await until(()=>!run('retrievalBinaryImports.query.busy'));assert.equal(refreshes,1);assert.equal(context.current,row);assert.equal(context.dirty,true);
  await el('retrieval-binary-query-form').emit('submit');await until(()=>requests.length);const invalid=requests.shift(),wrong=rawAck(invalid);wrong.source_sha256='0'.repeat(64);reply(invalid,wrong);await until(()=>!run('retrievalBinaryImports.query.busy'));assert.equal(refreshes,1);assert.match(el('retrieval-binary-query-status').textContent,/Uncertain.*not replayed/);
  await el('retrieval-binary-query-form').emit('submit');await until(()=>requests.length);const departed=requests.shift();events.pagehide();events.pageshow();reply(departed,rawAck(departed));await flush();await flush();assert.equal(refreshes,1);assert.equal(run('retrievalBinaryImports.query.busy'),false);assert.match(el('retrieval-binary-query-status').textContent,/Earlier admission may have completed/);
  const opaque=Buffer.from('Opaque controller bytes; real ZIP validation is server/browser-owned.');el('retrieval-binary-native-archive').files=[{size:opaque.length,arrayBuffer:async()=>opaque}];await el('retrieval-binary-native-form').emit('submit');await until(()=>requests.length);const native=requests.shift();reply(native,nativeAck(native));await until(()=>!run('retrievalBinaryImports.native.busy'));assert.equal(refreshes,2);assert.match(el('retrieval-binary-native-evidence').textContent,/native_retrieval_binary_v2/);assert.equal(context.current,row);
  await el('retrieval-binary-native-form').emit('submit');await until(()=>requests.length);const corrupt=requests.shift(),bad=nativeAck(corrupt);bad.records[1].annotation.judgments[0].relevance='unjudged';reply(corrupt,bad);await until(()=>!run('retrievalBinaryImports.native.busy'));assert.equal(refreshes,2);assert.match(el('retrieval-binary-native-status').textContent,/Uncertain.*not replayed/);
  await el('retrieval-binary-native-form').emit('submit');await until(()=>requests.length);const unknown=requests.shift(),unknownAck=nativeAck(unknown);unknownAck.records[0].source_lineage_known=false;reply(unknown,unknownAck);await until(()=>!run('retrievalBinaryImports.native.busy'));assert.equal(refreshes,2);assert.match(el('retrieval-binary-native-status').textContent,/Uncertain.*not replayed/);
  console.log('Binary relevance controller: explicit states/exact safe refs/notes, isolated adoption, deliberate guarded refresh, held/departed/query/native proof/busy preservation PASS.');
})().catch(error=>{console.error(error);process.exitCode=1;});
