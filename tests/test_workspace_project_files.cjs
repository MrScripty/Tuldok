// Deterministic projection/lifecycle evidence; real keyboard/layout evidence is
// owned by browser_project_files.cjs, not this deliberately small DOM substitute.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const html=fs.readFileSync(path.join(__dirname,'../static/project-files.html'),'utf8');
const source=fs.readFileSync(path.join(__dirname,'../static/project-files.js'),'utf8');
const pins=JSON.parse(source.match(/PROJECT_FILES_CONTRACTS_START \*\/\s*([\s\S]*?)\s*\/\* PROJECT_FILES_CONTRACTS_END/)[1]);
const capabilities={format:'agent_capabilities_v1',envelope_version:1,catalog_id:'a'.repeat(32),operations:Object.entries(pins).map(([id,sha256])=>({id,availability:'available',contracts:[{version:1,sha256,input_schema:{},output_schema:{},scopes:['inspect'],authority:'agent',effects:'read',retry:'read',bounds:{request_bytes:1048576,response_bytes:16777216,inline_decoded_bytes:524288,json_depth:64}}]})),limits:{request_bytes:1048576,response_bytes:16777216,max_operations:256}};
const B='b'.repeat(32),P='c'.repeat(32),R='d'.repeat(32),C='e'.repeat(64),N='f'.repeat(64);
const actions=['new','open','save','close','query','get','import_text','annotate'];
const state=(binding=B,checkpoint=C,opened=true)=>({format:'project_files_state_v1',binding,state:opened?'open':'no_project_open',roots:['fixture'],project:opened?{project_id:P,name:'Text project',checkpoint}:null,available_actions:opened?actions:['new','open']});
const record=(name='Greeting',revision=1)=>({id:R,kind:'text',name,text:'Hello world',groups:['source'],parents:[],provenance:{method:'import',rights:'unknown',normalization:'NFC; LF newlines'},task:'text_classification',annotation:{label:'greeting'},review:'draft',revision,source_revision:1,created_at:'2026-10-22T12:00:00+00:00',updated_at:'2026-10-22T12:00:00+00:00'});
const summary=value=>Object.fromEntries(Object.entries(value).filter(([key])=>['id','kind','name','task','review','revision','source_revision','created_at','updated_at'].includes(key)));
const records=(binding=B,checkpoint=C,items=[record()],next_after_id=null)=>({binding,project_id:P,checkpoint,items:items.map(summary),next_after_id});
const result=(binding=B,checkpoint=C,value=record())=>({binding,project_id:P,checkpoint,record:value,history:[value],next_history_before_revision:null});
const reply=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const defer=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const tick=async()=>{await new Promise(done=>setImmediate(done));await new Promise(done=>setImmediate(done));};
function mount(initial=[reply(state()),reply(records())],capabilityValue=capabilities){
  const nodes=new Map(),events=new Map(),requests=[],answers=[...initial],discoveries=[];let focused=null;
  class Node{
    constructor(tag='div'){this.tagName=tag;this.value='';this.children=[];this.dataset={};this.attrs={};this.listeners=new Map();this.disabled=false;this.hidden=false;this.textContent='';}
    append(...values){this.children.push(...values);if(this.tagName==='select'&&!this.value&&values.length)this.value=values[0].value;}
    replaceChildren(...values){this.children=[...values];if(this.tagName==='select')this.value=values[0]?.value??'';}
    setAttribute(name,value){this.attrs[name]=value;}
    addEventListener(name,handler){this.listeners.set(name,handler);}
    focus(){focused=this;}
    querySelectorAll(tag){return this.children.flatMap(child=>[...(child.tagName===tag?[child]:[]),...child.querySelectorAll(tag)]);}
  }
  for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
    const node=new Node(match[1]);node.value=match[2].match(/\bvalue="([^"]*)"/)?.[1]??'';node.disabled=/\bdisabled\b/.test(match[2]);nodes.set(match[3],node);
  }
  nodes.get('annotation-task').value='text_classification';nodes.get('record-review').value='draft';
  const context={document:{getElementById:id=>{assert.ok(nodes.has(id),'Unknown node '+id);return nodes.get(id);},createElement:tag=>new Node(tag)},URLSearchParams,crypto,console,window:null};
  context.window=context;context.TuldokAuth={canReview:()=>true,fetch:(url,options)=>{if(url==='/api/agent/capabilities'){discoveries.push({url,options});return Promise.resolve(reply(capabilityValue));}const header=options.headers?.['Tuldok-Operation-Contract'];assert.ok(header,'Every project call selects an exact contract');const [operation,version,digest]=header.split('/');assert.equal(version,'1');assert.equal(digest,pins[operation]);requests.push({url,options});assert.ok(answers.length,'Unexpected fetch '+url);return Promise.resolve(answers.shift());}};
  context.addEventListener=(name,handler)=>events.set(name,handler);
  vm.createContext(context);vm.runInContext(source,context);
  return {nodes,requests,answers,events,discoveries,focused:()=>focused,
    input(id,value){const node=nodes.get(id);node.value=value;node.listeners.get('input')?.({target:node});},
    async click(id){await nodes.get(id).onclick();await tick();},
    async submit(id){nodes.get(id).onsubmit({preventDefault(){}});await tick();}};
}
(async()=>{
  // The actual browser controller transports the current binding and checkpoint
  // on every read/edit, then adopts only the acknowledged checkpoint.
  {
    const h=mount();await tick();assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.discoveries.length,1);assert.equal(h.nodes.get('text-import-fields').disabled,false);
    h.input('text-name','Authored note');h.input('text-content','<script>do not execute</script>');
    h.answers.push(reply(result(B,N,record('Authored note'))),reply(records(B,N,[record('Authored note')])));
    await h.submit('text-import-form');
    assert.ok(h.requests[2],h.nodes.get('project-files-error').textContent+' '+JSON.stringify(h.requests));const sent=JSON.parse(h.requests[2].options.body);
    assert.equal(sent.binding,B);assert.equal(sent.expected_checkpoint,C);assert.equal(sent.asset.text,'<script>do not execute</script>');assert.match(sent.request_key,/^[a-f0-9]{32}$/);
    assert.equal(h.nodes.get('text-content').value,'');assert.equal(h.nodes.get('project-files-dirty').textContent,'No unsubmitted edits.');
    assert.ok(h.requests[3].url.includes('checkpoint='+N));assert.equal(h.nodes.get('record-heading').textContent,'Authored note');
    assert.equal(h.focused(),h.nodes.get('record-heading'));
    h.input('annotation-value','revised');h.answers.push(reply(result(B,C,{...record('Authored note',2),annotation:{label:'revised'}})),reply(records(B,C)));
    await h.submit('annotation-form');
    const annotation=JSON.parse(h.requests[4].options.body);assert.equal(annotation.expected_checkpoint,N);assert.equal(annotation.annotation.revision,1);assert.equal(annotation.annotation.source_revision,1);assert.equal(annotation.annotation.annotation.label,'revised');
    h.answers.push(reply(state()),reply(records()));await h.click('project-files-save');
    assert.equal(JSON.parse(h.requests[6].options.body).expected_checkpoint,C);assert.equal(h.nodes.get('record-heading').textContent,'Authored note');assert.equal(h.focused(),h.nodes.get('project-files-save'));assert.equal(h.nodes.get('project-files-save').disabled,false);
    h.answers.push(reply(state(P,C,false)));await h.click('project-files-close');
    assert.equal(h.nodes.get('text-import-fields').disabled,true);
    h.nodes.get('project-files-directory').value='copied-project';h.answers.push(reply(state(B,C,true)),reply(records()));await h.click('project-files-open');
    const opening=JSON.parse(h.requests[9].options.body);assert.equal(opening.binding,P);assert.equal(opening.expected_checkpoint,null);assert.equal(opening.directory,'copied-project');
  }
  // Unsubmitted drafts cannot disappear through lifecycle actions and warn on
  // navigation; explicit discard is the only local destructive transition.
  {
    const h=mount();await tick();h.input('text-content','Keep this draft');
    const count=h.requests.length;await h.click('project-files-close');assert.equal(h.requests.length,count);assert.equal(h.nodes.get('text-content').value,'Keep this draft');
    assert.equal(h.focused(),h.nodes.get('project-files-error'));assert.match(h.nodes.get('project-files-error').textContent,/unsent or unacknowledged/);
    let prevented=false;const event={preventDefault(){prevented=true;}};h.events.get('beforeunload')(event);assert.ok(prevented);assert.equal(event.returnValue,'');
    await h.click('project-files-discard');assert.equal(h.nodes.get('text-content').value,'');assert.equal(h.nodes.get('project-files-discard').disabled,true);
  }
  // A session replacement supersedes a delayed response. It cannot display the
  // old record even when the old request later succeeds with a valid payload.
  {
    const h=mount();await tick();const delayed=defer();h.answers.push(delayed.promise);
    const button=h.nodes.get('records-list').querySelectorAll('button')[0],old=button.onclick();await tick();
    h.answers.push(reply(state(P,N)),reply(records(P,N,[record('New session record')])));h.events.get('tuldok-session')();await tick();
    delayed.resolve(reply(result(B,C,record('Obsolete record'))));await old;await tick();
    assert.equal(h.nodes.get('record-text').value,'');assert.notEqual(h.nodes.get('record-heading').textContent,'Obsolete record');
    assert.match(h.nodes.get('records-list').querySelectorAll('button')[0].textContent,/New session record/);
  }
  // Unknown acknowledgement retains edits, fences writes, and exposes recovery.
  {
    const h=mount();await tick();h.input('text-name','Draft');h.input('text-content','Unique draft');
    h.answers.push(Promise.reject(Error('connection lost')));await h.submit('text-import-form');
    assert.equal(h.nodes.get('text-content').value,'Unique draft');assert.match(h.nodes.get('project-files-error').textContent,/may already be saved/);assert.equal(h.nodes.get('import-text').disabled,true);
    h.answers.push(reply(state()),reply(records()));await h.click('project-files-refresh');assert.equal(h.nodes.get('text-content').value,'Unique draft');assert.equal(h.nodes.get('import-text').disabled,false);
  }
  // History and record continuation are explicit, checkpoint-bound reads.
  // Loading an older history page never rewrites an unsubmitted annotation.
  {
    const h=mount([reply(state()),reply(records(B,C,[record()],R))]);await tick();
    const other={...record('Second record'),id:'e'.repeat(32)};h.answers.push(reply(records(B,C,[other])));await h.click('records-more');
    assert.equal(h.nodes.get('records-list').querySelectorAll('button').length,2);assert.ok(h.requests.at(-1).url.includes('after_id='+R));assert.equal(h.nodes.get('records-more').hidden,true);
    const latest=record('Greeting',2);h.answers.push(reply({...result(B,C,latest),next_history_before_revision:2}),reply(records()));await h.nodes.get('records-list').querySelectorAll('button')[0].onclick();await tick();
    h.input('annotation-value','Unsaved annotation');h.answers.push(reply({...result(B,C,latest),history:[record()]}));await h.click('record-history-more');
    assert.ok(h.requests.at(-1).url.includes('before_revision=2'));assert.equal(h.nodes.get('record-history').children.length,2);assert.equal(h.nodes.get('record-history-more').hidden,true);assert.equal(h.nodes.get('annotation-value').value,'Unsaved annotation');
  }
  // A committed outcome receipt survives the error projection. Recovery Open
  // targets only the declared directory and preserves the in-tab source draft.
  {
    const h=mount();await tick();h.input('text-name','Retained draft');h.input('text-content','May be committed');
    const receipt={committed:true,selected:true,project_id:P,checkpoint:N,request_key:'file-request-0001'};
    h.answers.push(reply({code:'projection_unavailable',error:'Saved; local view unavailable.',receipt},503));await h.submit('text-import-form');
    assert.match(h.nodes.get('project-files-receipt').textContent,/Saved to project/);assert.equal(h.nodes.get('text-content').value,'May be committed');
    const recovery={...state(),state:'recovery_required',available_actions:['open'],recovery:{action:'open',root:'fixture',directory:'original-project',reason:'projection_unavailable',request_key:'file-request-0001'}};
    h.answers.push(reply(recovery));await h.click('project-files-refresh');assert.equal(h.nodes.get('project-files-open').disabled,false);assert.equal(h.nodes.get('project-files-directory').disabled,true);assert.equal(h.nodes.get('project-files-directory').value,'original-project');
    h.answers.push(reply(state(P,N)),reply(records(P,N)));await h.click('project-files-open');assert.equal(h.nodes.get('text-content').value,'May be committed');assert.equal(JSON.parse(h.requests.at(-2).options.body).directory,'original-project');assert.equal(h.nodes.get('project-files-discard').disabled,false);
    h.answers.push(reply(result(P,N)),reply(records(P,N)));await h.nodes.get('records-list').querySelectorAll('button')[0].onclick();await tick();assert.equal(h.nodes.get('record-text').value,'Hello world');assert.equal(h.nodes.get('text-content').value,'May be committed');
  }
  // Incompatible capability pins stop dispatch rather than trusting remote
  // schemas or silently downgrading the operation selection.
  {
    const incompatible=JSON.parse(JSON.stringify(capabilities));incompatible.operations.find(item=>item.id==='project_files.status').contracts[0].sha256='0'.repeat(64);
    const h=mount([],incompatible);await tick();assert.equal(h.requests.length,0);assert.match(h.nodes.get('project-files-error').textContent,/No compatible project status contract/);assert.equal(h.nodes.get('project-files-open').disabled,true);
  }
  // Invalid future/unknown fields are errors, never an empty successful project.
  {
    const h=mount([reply({...state(),future:true})]);await tick();assert.match(h.nodes.get('project-files-error').textContent,/Unsupported project response/);assert.equal(h.nodes.get('project-files-new').disabled,true);
  }
  // A stale checkpoint error retains annotation text and focuses its recovery
  // message. Refresh can update identity without silently reattaching the draft.
  {
    const h=mount();await tick();h.answers.push(reply(result()),reply(records()));await h.nodes.get('records-list').querySelectorAll('button')[0].onclick();await tick();
    h.input('annotation-value','Never lose this label');h.answers.push(reply({code:'stale_checkpoint',error:'Reload current checkpoint.'},409));await h.submit('annotation-form');
    assert.equal(h.nodes.get('annotation-value').value,'Never lose this label');assert.equal(h.nodes.get('annotation-save').disabled,true);assert.match(h.nodes.get('project-files-error').textContent,/stale_checkpoint/);
    h.answers.push(reply(state(B,N)),reply(records(B,N)));await h.click('project-files-refresh');assert.equal(h.nodes.get('annotation-value').value,'Never lose this label');assert.equal(h.nodes.get('annotation-fields').disabled,true);
  }
  console.log('PASS project-files controller: checkpoint requests, submit/history projection, dirty preservation, superseded replies, typed errors, unknown acknowledgements');
})().catch(error=>{console.error(error);process.exitCode=1;});
