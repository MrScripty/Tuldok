// M4 controller fault boundaries. This small DOM substitute proves requests and
// inert projection; keyboard/layout and actual storage require real browser QA.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const html=fs.readFileSync(path.join(__dirname,'../static/project-files.html'),'utf8'),source=fs.readFileSync(path.join(__dirname,'../static/project-files.js'),'utf8');
const pins=JSON.parse(source.match(/PROJECT_FILES_CONTRACTS_START \*\/\s*([\s\S]*?)\s*\/\* PROJECT_FILES_CONTRACTS_END/)[1]);
const versionPins=JSON.parse(source.match(/PROJECT_FILES_VERSIONS_START \*\/\s*([\s\S]*?)\s*\/\* PROJECT_FILES_VERSIONS_END/)[1]);
const B='b'.repeat(32),P='c'.repeat(32),ACTOR='d'.repeat(32),FORK='a'.repeat(32),C='e'.repeat(64),NEXT='f'.repeat(64);
const actions=['new','open','save','close','query','get','import_text','annotate'];
const capabilities={format:'agent_capabilities_v1',envelope_version:1,catalog_id:'a'.repeat(32),operations:Object.entries(pins).map(([id,sha256])=>({id,availability:'available',contracts:[{version:1,sha256,input_schema:{},output_schema:{},scopes:['inspect'],authority:'agent',effects:'read',retry:'read',bounds:{request_bytes:1048576,response_bytes:16777216,inline_decoded_bytes:524288,json_depth:64}}]})),limits:{request_bytes:1048576,response_bytes:16777216,max_operations:256}};
const state=(binding=B,checkpoint=C,project=P,name='Text project')=>({format:'project_files_state_v1',binding,state:'open',roots:['fixture'],project:{project_id:project,name,checkpoint},available_actions:actions});
const records=(binding=B,checkpoint=C,project=P)=>({binding,project_id:project,checkpoint,items:[],next_after_id:null});
const bound=(value,checkpoint=C)=>({binding:B,project_id:P,checkpoint,value});
const response=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const tick=async()=>{for(let n=0;n<4;n++)await new Promise(done=>setImmediate(done));};
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex'),fileID=hash(P+'\0script\0scripts/inert.py');
const version=(text='print("only text")\0Ω\r\n',revision=1)=>({revision,sha256:hash(Buffer.from(text)),bytes:Buffer.byteLength(text),adopted_at:'2026-10-22T12:00:00+00:00',actor_id:ACTOR,text});
const selected=(text,revision)=>({id:fileID,project_id:P,kind:'script',path:'scripts/inert.py',version:version(text,revision)});
function mount(capabilityValue=capabilities){
  const nodes=new Map(),requests=[],answers=[response(state()),response(records())];let focused=null;
  class Element{
    constructor(tag){Object.assign(this,{tagName:tag,value:'',children:[],dataset:{},attrs:{},listeners:new Map(),disabled:false,hidden:false,textContent:''});}
    append(...children){this.children.push(...children);if(this.tagName==='select'&&!this.value)this.value=children[0]?.value??'';}
    replaceChildren(...children){this.children=children;if(this.tagName==='select')this.value=children[0]?.value??'';}
    setAttribute(key,value){this.attrs[key]=value;}
    addEventListener(name,handler){this.listeners.set(name,handler);}
    focus(){focused=this;}
    querySelectorAll(tag){return this.children.flatMap(child=>[...(child.tagName===tag?[child]:[]),...child.querySelectorAll(tag)]);}
  }
  for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
    const node=new Element(match[1]);node.value=match[2].match(/\bvalue="([^"]*)"/)?.[1]??'';nodes.set(match[3],node);
  }
  for(const [id,value] of Object.entries({'annotation-task':'text_classification','record-review':'draft','project-explore-kind':'data_query','project-source-kind':'image','project-data-review':'draft','project-working-kind':'script'}))nodes.get(id).value=value;
  const context={document:{getElementById:id=>{assert.ok(nodes.has(id),id);return nodes.get(id);},createElement:tag=>new Element(tag)},URLSearchParams,TextEncoder,TextDecoder,crypto,console,window:null};context.window=context;
  context.addEventListener=()=>{};
  context.TuldokAuth={canReview:()=>true,fetch:async(url,options)=>{
    if(url==='/api/agent/capabilities')return response(capabilityValue);
    const [operation,version,digest]=options.headers['Tuldok-Operation-Contract'].split('/');assert.equal(digest,versionPins[operation]?.[version]??pins[operation]);
    const request={url,options};requests.push(request);assert.ok(answers.length,'Unexpected fetch '+url);
    const next=answers.shift();return typeof next==='function'?next(request):next;
  }};
  vm.createContext(context);vm.runInContext(source,context);
  return {nodes,requests,answers,focused:()=>focused,
    input(id,value){const node=nodes.get(id);node.value=value;node.listeners.get('input')?.({target:node});},
    async click(id){await nodes.get(id).onclick();await tick();},
    async submit(id){nodes.get(id).onsubmit({preventDefault(){}});await tick();for(let n=0;n<100&&nodes.get('project-save-as-fields').disabled&&!nodes.get('project-files-error').textContent;n++)await new Promise(done=>setTimeout(done,2));},
    async row(id,index=0){await nodes.get(id).querySelectorAll('button')[index].onclick();await tick();}};
}
const inspection=()=>{const v=version();return {id:fileID,kind:'script',path:'scripts/inert.py',revision:1,expected_sha256:v.sha256,expected_bytes:v.bytes,observed_sha256:v.sha256,observed_bytes:v.bytes,state:'unchanged',reason:null};};
module.exports={mount,state,records,bound,response,tick,B,P,ACTOR,C,NEXT,capabilities,versionPins};
if(require.main===module)(async()=>{
  // Save As changes only after a correlated independent selection receipt.
  {
    const h=mount();await tick();h.input('project-save-as-directory','independent');h.input('project-save-as-name','Fork Ω');
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.equal(body.binding,B);assert.equal(body.expected_checkpoint,C);assert.equal(body.root,'fixture');return response({state:state(ACTOR,NEXT,FORK,'Fork Ω'),fork:{source_project_id:P,source_checkpoint:C,project_id:FORK,checkpoint:NEXT,root:body.root,directory:body.directory,request_key:body.request_key,reconciled:false,mapping_count:2,copied_count:1,missing_regenerable_count:1}});},response(records(ACTOR,NEXT,FORK)));
    await h.submit('project-save-as-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-save-as-summary').textContent,/2 editable mappings/);assert.equal(h.focused(),h.nodes.get('project-fork-load'));
    assert.ok(h.requests.at(-1).url.includes('binding='+ACTOR));assert.ok(h.requests.at(-1).url.includes('checkpoint='+NEXT));
  }
  // Lost acknowledgement retains the exact source/destination/key for explicit
  // retry, even after status refresh observes a different selection.
  {
    const h=mount();await tick();h.input('project-save-as-directory','pending');h.input('project-save-as-name','Pending');
    h.answers.push(()=>Promise.reject(Error('lost reply')));await h.submit('project-save-as-form');const original=JSON.parse(h.requests.at(-1).options.body);
    assert.match(h.nodes.get('project-files-error').textContent,/may already be saved/);assert.equal(h.nodes.get('project-save-as-directory').value,'pending');
    h.answers.push(response(state(ACTOR,NEXT,FORK,'Pending')),response(records(ACTOR,NEXT,FORK)));await h.click('project-files-refresh');
    h.input('project-save-as-directory','different');const before=h.requests.length;await h.submit('project-save-as-form');assert.equal(h.requests.length,before);assert.match(h.nodes.get('project-files-error').textContent,/pending Save As destination/);
    h.input('project-save-as-directory','pending');h.answers.push(({options})=>{assert.deepEqual(JSON.parse(options.body),original);return response({error:'Inspect original source before recovery.',code:'stale_binding'},409);});await h.submit('project-save-as-form');assert.equal(h.requests.length,before+1);
  }
  // Captured scripts render only after exact byte/revision checks. A corrupt
  // reply cannot replace the prior visible revision, and no script is evaluated.
  {
    const h=mount();await tick();h.answers.push(response(bound({items:[inspection()],offset:0,limit:40,total:1})));await h.click('project-working-load');
    h.answers.push(response(bound(selected())));await h.row('project-working-list');assert.equal(h.nodes.get('project-working-text').value,version().text);assert.equal(h.nodes.get('project-working-path').value,'scripts/inert.py');
    const meta=version();delete meta.text;h.answers.push(response(bound({id:fileID,items:[meta],offset:0,limit:40,total:1})));await h.click('project-working-history');
    assert.equal(h.nodes.get('project-working-history-list').children.length,1);assert.equal(h.nodes.get('project-working-history-more').hidden,true);
    const corrupt=selected('changed',1);corrupt.version.sha256=C;h.answers.push(response(bound(corrupt)));await h.row('project-working-history-list');
    assert.equal(h.nodes.get('project-working-text').value,version().text);assert.match(h.nodes.get('project-files-error').textContent,/exact bytes/);
  }
  // Explicit adoption transports the reviewed SHA and optimistic revision. The
  // current file is read by the server owner; the browser sends no source text.
  {
    const h=mount();await tick();const v=version('new exact text',1);
    for(const [id,value] of Object.entries({'project-working-path':'scripts/inert.py','project-working-revision':'0','project-working-sha':v.sha256}))h.input(id,value);
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.equal(body.expected_checkpoint,C);assert.equal(body.expected_revision,0);assert.equal(body.expected_sha256,v.sha256);assert.equal(body.path,'scripts/inert.py');assert.ok(!Object.hasOwn(body,'text'));return response(bound({id:fileID,project_id:P,kind:'script',path:body.path,revision:1,sha256:v.sha256,bytes:v.bytes,adopted_at:v.adopted_at,changed:true},NEXT));},response(bound({items:[],offset:0,limit:40,total:0},NEXT)),response(bound(selected('new exact text',1),NEXT)));
    await h.submit('project-working-adopt-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-working-text').value,'new exact text');assert.equal(h.nodes.get('project-working-revision').value,'1');assert.match(h.nodes.get('project-files-status').textContent,/remains inert/);
  }
  // Fork metadata pages and unresolved binding details remain read-only. The
  // original definition is fetched only after a user selects that exact row.
  {
    const h=mount();await tick();const origin={project_id:FORK,checkpoint:NEXT,family:'model_definition',id:ACTOR,revision:2,created_at:'2026-10-22T12:00:00+00:00'},current={format:'project_material_fork_intent_v1',catalog_id:P,id:ACTOR,revision:1,name:'Retained <script>',definition_family:'model_definition',definition:{source_selector:{catalog_id:FORK},specification:{width:17}},required_reselection:['source_selector']};
    const item={family:'model_definition',id:P+'.'+ACTOR,catalog_id:P,definition_id:ACTOR,name:current.name,revision:1,required_reselection:current.required_reselection,fork_origin:origin};
    h.answers.push(response(bound({items:[item],offset:0,limit:40,total:1})));await h.click('project-intents-load');assert.equal(h.nodes.get('project-intent-detail').textContent,'');
    h.answers.push(response(bound({family:'model_definition',id:item.id,current,fork_origin:origin})));await h.row('project-intents-list');assert.match(h.nodes.get('project-intent-detail').textContent,/"width": 17/);assert.equal(h.nodes.get('project-intent-detail').children.length,0);assert.equal(h.nodes.get('project-intent-title').textContent,'Retained <script>');
    h.answers.push(response(bound({source:null,project_id:P,mapping:{items:[],offset:1,limit:40,total:0},archived_count:0,copied_count:0,missing_regenerable_count:0})));await h.click('project-fork-load');assert.match(h.nodes.get('project-files-error').textContent,/selected identity/);
  }
  console.log('M4 controller: 5 selected groups PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
