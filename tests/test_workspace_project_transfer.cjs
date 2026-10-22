// Controlled browser logic only. Actual layout, authentication and HTTP evidence
// require the separately admitted Chromium gate on fixed source fingerprints.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const file=path.join(__dirname,'../static/project-transfer.js'),source=fs.readFileSync(file,'utf8'),html=fs.readFileSync(path.join(__dirname,'../static/project-transfer.html'),'utf8');
const pure=require(file),pins=JSON.parse(source.match(/PROJECT_TRANSFER_CONTRACTS_START \*\/\s*([\s\S]*?)\s*\/\* PROJECT_TRANSFER_CONTRACTS_END/)[1]);
const S='a'.repeat(32),H='b'.repeat(32),B='c'.repeat(32),N='d'.repeat(32),P='e'.repeat(32),R='f'.repeat(32),D='1'.repeat(64),C='2'.repeat(64),Q='3'.repeat(64);
const sections=['included','required','unassigned','excluded','blockers','warnings','artifacts','working_files'];
const ref=stopped=>({catalog_id:S,schema_version:10,catalog_signature:D,snapshot_sha256:C,backup_receipt_sha256:stopped?D:null,external_inventory_sha256:Q});
const report=stopped=>({report_sha256:stopped?Q:D,selection_sha256:C,source:ref(stopped),can_extract:stopped,counts:Object.fromEntries(sections.map(s=>[s,s==='included'||!stopped&&s==='blockers'?1:0]))});
function state(phase='source_live',withReport=false){const stopped=phase!=='source_live';return {format:'project_transfer_state_v1',binding:stopped?N:B,phase,source_catalog_id:S,control_catalog_id:H,roots:['fixture'],available_actions:phase==='source_fenced'?['status']:['status','preview','report_page',...(withReport?[stopped?'extract':'stop']:[])],report:withReport?report(stopped):null,backup:stopped?{root:'fixture',directory:'backup',receipt_sha256:D}:null,destination:stopped?{root:'fixture',directory:'independent'}:null,failure:null,last_receipt:null};}
const page=(stopped=false,section='blockers',offset=0,items=null,total=null)=>({format:'project_transfer_report_page_v1',binding:stopped?N:B,report_sha256:stopped?Q:D,section,items:items??(stopped?[]:[{family:'source',id:S,code:'cessation_proof_unavailable',detail:'Stop through the current source owner.'}]),offset,limit:40,total:total??(stopped?0:1)});
const receipt=()=>({format:'project_transfer_receipt_v1',committed:true,project_id:P,checkpoint:C,request_key:'extract-key',input_sha256:D,report_sha256:Q,source:ref(true),artifacts:{copied_count:2,missing_regenerable_count:0},verification:{checkpoint:C,active_data_records:1},replayed:false});
const result=()=>({format:'project_transfer_extraction_result_v1',binding:N,receipt:receipt(),selection:{selected:true,state:{project:{project_id:P,checkpoint:C}},error:null}});
const response=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const defer=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const tick=async()=>{await new Promise(done=>setImmediate(done));await new Promise(done=>setImmediate(done));};
function mount(initial=[response(state())],options={}){
  const nodes=new Map(),events=new Map(),requests=[],answers=[...initial],discoveries=[],sentEvents=[];let focused=null,identity={catalog_id:S,kind:'owner',scopes:['admin'],label:'Source owner'};
  class Node{
    constructor(tag='div'){this.tagName=tag;this.value='';this.children=[];this.disabled=false;this.hidden=false;this.checked=false;this.textContent='';this.listeners=new Map();this.attrs={};}
    append(...items){this.children.push(...items);if(this.tagName==='select'&&!this.value&&items.length)this.value=items[0].value;}
    replaceChildren(...items){this.children=[...items];if(this.tagName==='select')this.value=items[0]?.value??'';}
    addEventListener(name,handler){this.listeners.set(name,handler);}
    setAttribute(name,value){this.attrs[name]=value;}
    focus(){focused=this;}
    click(){if(!this.disabled)return this.onclick?.();}
  }
  for(const m of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){const node=new Node(m[1]);node.value=m[2].match(/\bvalue="([^"]*)"/)?.[1]??'';node.disabled=/\bdisabled\b/.test(m[2]);node.hidden=/\bhidden\b/.test(m[2]);nodes.set(m[3],node);}
  for(const name of ['session-form','session-open'])nodes.set(name,new Node());let signinClicks=0;nodes.get('session-open').onclick=()=>signinClicks++;
  nodes.get('report-section').value='blockers';nodes.get('producer-kind').value='generation';nodes.get('working-kind').value='script';nodes.get('decision-include').value='include';
  const context={document:{getElementById:id=>nodes.get(id)??null,createElement:tag=>new Node(tag)},TextEncoder,URLSearchParams,crypto,console,location:{origin:'http://fixture.local'},MessageEvent:class{constructor(type,fields){this.type=type;Object.assign(this,fields);}},window:null};
  context.window=context;context.addEventListener=(name,handler)=>events.set(name,handler);context.dispatchEvent=event=>{sentEvents.push(event);events.get(event.type)?.(event);};
  context.TuldokAuth={identity:()=>identity,fetch:(url,request={})=>{
    if(url==='/api/agent/capabilities'){discoveries.push({url,request});const operations=Object.entries(pins).map(([id,sha256])=>({id,availability:'available',contracts:[{version:1,sha256,input_schema:{},output_schema:{},scopes:['admin'],authority:'owner',effects:'read',retry:'read',bounds:{request_bytes:1048576,response_bytes:1048576,inline_decoded_bytes:524288,json_depth:64}}]}));if(options.mismatch)operations.find(v=>v.id==='project_transfer.status').contracts[0].sha256='0'.repeat(64);return Promise.resolve(response({format:'agent_capabilities_v1',envelope_version:1,catalog_id:identity.catalog_id,operations,limits:{request_bytes:1048576,response_bytes:16777216,max_operations:256}}));}
    const header=request.headers?.['Tuldok-Operation-Contract'];assert.ok(header,'Every transfer call selects an installed contract');const [name,version,sha256]=header.split('/');assert.equal(version,'1');assert.equal(sha256,pins[name]);requests.push({url,request,name});assert.ok(answers.length,'Unexpected fetch '+url);return Promise.resolve(answers.shift());
  }};
  vm.createContext(context);vm.runInContext(source,context);
  return {nodes,requests,answers,discoveries,events,sentEvents,focused:()=>focused,signinClicks:()=>signinClicks,
    input(name,value){const n=nodes.get(name);n.value=value;n.listeners.get('input')?.({target:n});},
    change(name,value){const n=nodes.get(name);if(typeof value==='boolean')n.checked=value;else n.value=value;n.listeners.get('change')?.({target:n});},
    async click(name){await nodes.get(name).click();await tick();},
    async submit(name){await nodes.get(name).onsubmit({preventDefault(){}});await tick();},
    async session(catalog=H,{submit=true}={}){if(submit)nodes.get('session-form').listeners.get('submit')?.({});identity={catalog_id:catalog,kind:'owner',scopes:['admin'],label:'Current host owner'};events.get('tuldok-session')?.({});await tick();},
    async file(value){nodes.get('selection-file').files=[value];await nodes.get('selection-file').onchange();await tick();}};
}
async function preview(h,stopped=false){h.answers.push(response(state(stopped?'source_stopped':'source_live',true)),response(page(stopped)));await h.submit('transfer-preview-form');}
async function sourcePreview(){const h=mount();await tick();h.input('snapshot-id',P);h.input('snapshot-sha',D);h.input('selection-ids',R);await h.click('selection-add');await preview(h);return h;}
async function stop(h){h.input('backup-directory','backup');h.input('destination-directory','independent');h.change('report-reviewed',true);h.change('stop-confirm',true);h.answers.push(response(state('source_stopped')));await h.submit('transfer-stop-form');}
async function stoppedPreview(){const h=await sourcePreview();await stop(h);h.answers.push(response(state('source_stopped')));await h.session();await preview(h,true);h.change('report-reviewed',true);h.change('extract-confirm',true);h.input('destination-name','Independent project');h.input('extraction-key','extract-key');return h;}
async function controlledCampaign(){
  // Only a finite business selection is admitted. Commands, authority and paths
  // outside the named working roots never reach a request.
  {
    assert.equal(Object.keys(pins).length,5);assert.ok(Object.values(pins).every(v=>/^[a-f0-9]{64}$/.test(v)));
    const good={project_snapshot:{id:P,manifest_sha256:D},roots:{records:[R],working_files:[{kind:'script',path:'scripts/inert.py'}]},decisions:[]};
    assert.equal(pure.normalizeSelection(good).roots.records[0],R);
    for(const bad of [{...good,operation:'runs.submit'},{...good,credential:'secret'},{...good,roots:{unknown:[R]}},{...good,roots:{working_files:[{kind:'script',path:'scripts/../outside.py'}]}},{...good,decisions:[{family:'access_credentials',id:R,include:true,reason:'Not portable'}]}])assert.throws(()=>pure.normalizeSelection(bad));
    const h=mount();await tick();await h.file({size:50,text:async()=>JSON.stringify(good)});assert.match(h.nodes.get('selection-summary').textContent+JSON.stringify(h.nodes.get('selection-summary').children.map(v=>v.textContent)),/Data records: 1/);assert.equal(h.requests.length,1);
    await h.file({size:30,text:async()=>JSON.stringify({...good,operation:'runs.submit'})});assert.match(h.nodes.get('transfer-error').textContent,/refused/);assert.equal(h.requests.length,1);
  }
  // Preview is a pinned read; Stop needs both report review and explicit backup
  // confirmation. No hidden mutation or automatic Stop follows a preview.
  {
    const h=await sourcePreview();assert.equal(h.requests.length,3);assert.equal(h.requests[1].name,'project_transfer.preview');assert.equal(h.requests[2].name,'project_transfer.report_page');
    const body=JSON.parse(h.requests[1].request.body);assert.equal(body.binding,B);assert.deepEqual(body.selection.roots.records,[R]);assert.equal(body.selection.project_snapshot.manifest_sha256,D);
    assert.equal(h.nodes.get('transfer-stop').disabled,true);assert.equal(h.nodes.get('report-reviewed').disabled,false);h.change('report-reviewed',true);h.change('stop-confirm',true);assert.equal(h.nodes.get('transfer-stop').disabled,false);
    h.input('backup-directory','backup');h.input('destination-directory','backup');const count=h.requests.length;await h.submit('transfer-stop-form');assert.equal(h.requests.length,count);assert.match(h.nodes.get('transfer-error').textContent,/different new backup/);
  }
  // A fresh control-host identity without a new standard sign-in form submit
  // cannot unlock extraction. The source token is never read or transported.
  {
    const h=await sourcePreview();await stop(h);assert.equal(h.nodes.get('selection-fields').disabled,true);assert.equal(h.nodes.get('control-signin-panel').hidden,false);assert.ok(h.sentEvents.some(v=>v.type==='message'));
    assert.equal(h.requests.at(-1).name,'project_transfer.stop');assert.equal(JSON.parse(h.requests.at(-1).request.body).report_sha256,D);
    h.answers.push(response(state('source_stopped')));await h.session(H,{submit:false});assert.equal(h.nodes.get('selection-fields').disabled,true);
    h.answers.push(response(state('source_stopped')));await h.session(H);assert.equal(h.nodes.get('selection-fields').disabled,false);assert.equal(h.nodes.get('transfer-extract').disabled,true);
    assert.equal(h.nodes.get('snapshot-id').value,P);assert.equal(h.nodes.get('snapshot-sha').value,D);assert.ok(h.requests.every(r=>!String(r.request.body??'').includes('token')));
  }
  // Stopped-source preview is explicit. Extraction pins its digest, retains its
  // receipt, checks selected identity/checkpoint, and never invokes a Run.
  {
    const h=await stoppedPreview();h.answers.push(response(result()));await h.submit('transfer-extract-form');const body=JSON.parse(h.requests.at(-1).request.body);
    assert.equal(body.binding,N);assert.equal(body.report_sha256,Q);assert.equal(body.directory,'independent');assert.equal(body.request_key,'extract-key');assert.equal(h.requests.at(-1).name,'project_transfer.extract');
    assert.match(h.nodes.get('transfer-receipt').textContent,/Publication recorded/);assert.equal(h.nodes.get('project-files-link').hidden,false);assert.equal(h.focused(),h.nodes.get('outcome-title'));assert.equal(h.nodes.get('transfer-extract').disabled,true);
    assert.ok(h.requests.every(r=>r.name.startsWith('project_transfer.')));
  }
  // Network loss retains one exact request. Status refresh is read-only and an
  // explicit reconcile button repeats that exact key/body, without a new name.
  {
    const h=await stoppedPreview();h.answers.push(Promise.reject(Error('lost reply')));await h.submit('transfer-extract-form');const original=JSON.parse(h.requests.at(-1).request.body);assert.match(h.nodes.get('transfer-error').textContent,/Acknowledgement unavailable/);assert.equal(h.nodes.get('transfer-reconcile').hidden,false);assert.equal(h.nodes.get('extract-fields').disabled,true);
    h.answers.push(response(state('source_stopped',true)));const n=h.requests.length;await h.click('transfer-refresh');assert.equal(h.requests.length,n+1);assert.equal(h.requests.at(-1).name,'project_transfer.status');
    h.answers.push(response({...result(),receipt:{...receipt(),replayed:true}}));await h.click('transfer-reconcile');assert.deepEqual(JSON.parse(h.requests.at(-1).request.body),original);assert.match(h.nodes.get('transfer-receipt').textContent,/reconciled/);
  }
  // A committed unknown receipt and a failed inert selection remain visible.
  {
    const h=await stoppedPreview(),known={committed:true,selected:false,project_id:P,checkpoint:C,request_key:'extract-key',directory:'independent'};h.answers.push(response({code:'unknown',error:'Publication acknowledgement lost.',receipt:known},503));await h.submit('transfer-extract-form');assert.match(h.nodes.get('transfer-receipt').textContent,new RegExp(P));assert.equal(h.nodes.get('project-files-link').hidden,false);
    h.answers.push(response({...result(),selection:{selected:false,state:null,error:{code:'project_selection_unavailable',detail:'Existing selection requires attention.'}}}));await h.click('transfer-reconcile');assert.match(h.nodes.get('selection-outcome').textContent,/Selection was unavailable/);assert.match(h.nodes.get('transfer-receipt').textContent,/Publication recorded/);
  }
  // Source fencing is terminal for this controller. No status refresh or login
  // silently retries Stop or makes an extraction capability from unknown state.
  {
    const h=await sourcePreview();h.change('report-reviewed',true);h.change('stop-confirm',true);h.input('backup-directory','backup');h.input('destination-directory','independent');h.answers.push(response({error:'Owner drainage is unknown.',code:'unknown'},409));await h.submit('transfer-stop-form');
    const fenced={...state('source_fenced'),failure:{action:'stop',code:'unknown',detail:'No stopped-source lease was issued.'}};h.answers.push(response(fenced));await h.session();assert.equal(h.nodes.get('transfer-extract').disabled,true);assert.equal(h.nodes.get('transfer-stop').disabled,true);assert.equal(h.nodes.get('transfer-fence').hidden,false);assert.equal(h.requests.filter(r=>r.name==='project_transfer.stop').length,1);
  }
  // Full pages contain forty named business facts; continuation is bound to the
  // same report. Malicious detail text is plain text and unknown rows are errors.
  {
    const h=await sourcePreview(),items=Array.from({length:40},(_,i)=>({family:'workbench_record',id:i.toString(16).padStart(32,'0'),revision:1}));
    const newer=state('source_live',true);newer.report.counts.unassigned=41;h.answers.push(response(newer));await h.click('transfer-refresh');
    h.change('report-section','unassigned');h.answers.push(response(page(false,'unassigned',0,items,41)));await h.click('report-load');assert.equal(h.nodes.get('report-items').children.length,40);assert.equal(h.nodes.get('report-next').disabled,false);
    h.answers.push(response(page(false,'unassigned',40,[{family:'workbench_record',id:R,revision:1}],41)));await h.click('report-next');assert.ok(h.requests.at(-1).url.includes('offset=40'));assert.equal(h.nodes.get('report-next').disabled,true);
    h.change('report-section','blockers');h.answers.push(response(page(false,'blockers',0,[{family:'source',id:S,code:'cessation_proof_unavailable',detail:'<img src=x onerror=execute()> never run'}],1)));await h.click('report-load');assert.match(h.nodes.get('report-items').children[0].children[0].textContent,/<img/);
    h.answers.push(response({...page(false),future:true}));await h.click('report-load');assert.match(h.nodes.get('transfer-error').textContent,/stale or unsupported/);assert.equal(h.nodes.get('transfer-stop').disabled,true);
  }
  // Session changes supersede delayed reads; old report facts cannot be adopted.
  {
    const h=await sourcePreview(),delayed=defer();h.answers.push(delayed.promise);const loading=h.click('report-load');await tick();h.answers.push(response(state()));await h.session(S);delayed.resolve(response(page(false)));await loading;await tick();assert.equal(h.nodes.get('report-items').children.length,0);assert.equal(h.nodes.get('transfer-stop').disabled,true);
  }
  // A mismatched selected checkpoint cannot turn a publication receipt into a
  // false selection acknowledgement; the exact request remains recoverable.
  {
    const h=await stoppedPreview();h.answers.push(response({...result(),selection:{selected:true,state:{project:{project_id:P,checkpoint:D}},error:null}}));await h.submit('transfer-extract-form');assert.match(h.nodes.get('transfer-error').textContent,/checkpoint differs/);assert.match(h.nodes.get('transfer-receipt').textContent,/Publication recorded/);assert.equal(h.nodes.get('transfer-reconcile').hidden,false);
  }
  {
    const h=mount([],{mismatch:true});await tick();assert.equal(h.requests.length,0);assert.match(h.nodes.get('transfer-error').textContent,/No compatible extraction/);assert.equal(h.nodes.get('transfer-stop').disabled,true);
    const h2=mount([response({...state(),future:true})]);await tick();assert.match(h2.nodes.get('transfer-error').textContent,/Unsupported extraction controller/);
  }
  console.log('project-transfer controlled UI: 12 scenarios passed');
}

async function browserCampaign(){
  const os=require('node:os'),{spawn,execFileSync}=require('node:child_process'),{once}=require('node:events');
  const {waitForDebugger}=require('./browser_startup.cjs'),{cdpSession}=require('./browser_cdp_session.cjs'),{stopOwnedChildren}=require('./browser_owned_cleanup.cjs'),{qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
  const root=path.resolve(__dirname,'..'),hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
  assert.equal(process.env.TULDOK_M5_UI_BROWSER_GO,'1','Lead GO is required before actual browser execution');
  assert.ok(process.env.TULDOK_M5_UI_FREEZE_MANIFEST,'Lead immutable-source manifest is required');
  assert.ok(process.env.TULDOK_DATABASE_URL&&process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL,'Use separate disposable PostgreSQL source/cold configurations');
  const freezeRaw=fs.readFileSync(process.env.TULDOK_M5_UI_FREEZE_MANIFEST),freeze=JSON.parse(freezeRaw),material={manifest_sha256:hash(freezeRaw),files:freeze.files};
  function verifySource(){for(const [name,sha] of Object.entries(material.files))assert.equal(hash(fs.readFileSync(path.join(root,name))),sha,'Frozen source changed: '+name);}
  verifySource();
  for(const name of ['static/project-transfer.html','static/project-transfer.js','static/project-transfer.css','tests/test_workspace_project_transfer.cjs'])assert.ok(Object.hasOwn(material.files,name),'Freeze must include '+name);
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-m5-ui-')),output=qaDirectory(root,'project-transfer'),sourceDsn=process.env.TULDOK_DATABASE_URL,coldDsn=process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL;
  assert.notEqual(sourceDsn,coldDsn);
  const sourceRoot=path.join(temporary,'source'),controlRoot=path.join(temporary,'control'),coldRoot=path.join(temporary,'cold-control'),registered=path.join(temporary,'registered'),publication=path.join(temporary,'publication');
  fs.mkdirSync(registered);fs.mkdirSync(publication);
  const children=[],catalogs=[{control:sourceRoot,dsn:sourceDsn},{control:controlRoot,dsn:sourceDsn},{control:publication,dsn:sourceDsn},{control:coldRoot,dsn:coldDsn}],checks=[],errors=[],httpFailures=[],transferRequests=[],screenshots=[];
  let socket,session,send,evaluate,server,origin,serverErrors='',dropExtract=false,dropped=false,succeeded=false;
  const pause=ms=>new Promise(done=>setTimeout(done,ms));
  async function until(work,label){for(let i=0;i<250;i++){const result=await work();if(result)return result;await pause(100);}throw Error('Timed out: '+label);}
  function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
  function check(label){checks.push(label);console.log('PASS '+label);}
  async function stop(child){if(!child||child.exitCode!==null||child.signalCode!==null)return;await stopOwnedChildren([child]);}
  const headers=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;print(json.dumps({name:agent_api.selected_header(name) for name in (*agent_api.PROJECT_TRANSFER_OPERATIONS,'project_files.status')}))"],{cwd:root,encoding:'utf8'}));
  const author=String.raw`
import hashlib,json,os,pathlib,uuid
from types import SimpleNamespace
from metadata import Metadata
from access import Access
from projects import Projects
from workbench import Workbench
root=pathlib.Path(os.environ['M5_SOURCE']);registered=pathlib.Path(os.environ['M5_REGISTERED'])
(registered/'scripts').mkdir()
(registered/'scripts'/'must-not-run.py').write_text("from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('forbidden')\n")
manifest=dict(schema_version=1,id=uuid.uuid4().hex,name='Browser selected source λ',data=[],recipes=[],evidence=[],requirements=[])
raw=(json.dumps(manifest,ensure_ascii=False,indent=3)+'\n\n').encode();(registered/'source.json').write_bytes(raw)
db=Metadata(root);access=Access(db,root);token=access.exchange(access._local_owner_token())['token']
context=SimpleNamespace(db=db,lock=db.lock,path=root,access=access);workbench=Workbench(context);projects=Projects(context,{'input':registered})
with access.bind(token):
 projects.register_snapshot(dict(root='input',manifest_path='source.json'))
 current=workbench.import_asset(dict(kind='text',name='Unique browser source',text='Browser original e\u0301\r\nλ',groups=['browser-source'],parents=[],rights='Disposable authored source'))
 others=[workbench.import_asset(dict(kind='text',name='Unassigned '+str(i),text='Unassigned source '+str(i),groups=['other-scope'],parents=[],rights='Other fixture scope'))['id'] for i in range(41)]
print(json.dumps(dict(project_id=manifest['id'],manifest_sha256=hashlib.sha256(raw).hexdigest(),record_id=current['id'],normalized_text=current['text'],source_catalog_id=db.dataset_id,other_id=others[0])))
projects.close();db.close()
`;
  const fixture=JSON.parse(execFileSync('python3',['-c',author],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:sourceDsn,M5_SOURCE:sourceRoot,M5_REGISTERED:registered},encoding:'utf8'}));
  const business={project_snapshot:{id:fixture.project_id,manifest_sha256:fixture.manifest_sha256},roots:{records:[fixture.record_id],working_files:[{kind:'script',path:'scripts/must-not-run.py'}]},decisions:[]};
  function privateCode(directory,dsn){const file=path.join(temporary,'login-'+crypto.randomUUID()+'.private');try{execFileSync('python3',['access.py','login','--data',directory,'--out',file],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn},stdio:['ignore','pipe','pipe']});return fs.readFileSync(file,'utf8').trim();}finally{if(fs.existsSync(file))fs.unlinkSync(file);}}
  async function start(cold=false){serverErrors='';let stdout='';server=launch('python3',['-u','app.py','--port','0','--data',cold?coldRoot:sourceRoot,...(cold?['--project-files-root','output='+publication]:['--project-root','input='+registered,'--project-transfer-control',controlRoot,'--project-transfer-root','output='+publication])],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:cold?coldDsn:sourceDsn},stdio:['ignore','pipe','pipe']});server.stdout.on('data',value=>stdout+=value);server.stderr.on('data',value=>serverErrors+=value);const port=await until(()=>{if(server.exitCode!==null)throw Error('Fixture server exited: '+serverErrors);return stdout.match(/127\.0\.0\.1:(\d+)/)?.[1];},'fixture readiness');origin='http://127.0.0.1:'+port;}
  async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Tab:9,' ':32,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
  async function focus(selector){await until(()=>evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)});if(!element||element.disabled||!element.getClientRects().length)return false;element.scrollIntoView({block:'center'});element.focus();return document.activeElement===element;})()`),'focus '+selector);}
  async function fill(selector,value){await focus(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
  async function activate(selector){await focus(selector);await key('Enter');}
  async function choose(selector,value){await focus(selector);await evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)});if(!Array.from(element.options).some(option=>option.value===${JSON.stringify(value)}))throw Error('Missing named option');element.value=${JSON.stringify(value)};element.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
  async function toggle(selector){await focus(selector);await key(' ','Space');assert.equal(await evaluate(`document.querySelector(${JSON.stringify(selector)}).checked`),true);}
  async function signin(directory,dsn){await until(()=>evaluate('document.getElementById("session-dialog")?.open'),'standard login dialog');let code=privateCode(directory,dsn);await fill('#session-token',code);code=null;await activate('#session-submit');await until(()=>evaluate('!document.getElementById("session-dialog").open'),'standard sign-in acknowledgement');}
  async function api(name,args={}){const definition={status:['GET',''],preview:['POST','/preview'],report_page:['GET','/report'],stop:['POST','/stop'],extract:['POST','/extract']}[name],operation='project_transfer.'+name;return evaluate(`(async()=>{const response=await window.TuldokAuth.fetch(${JSON.stringify('/api/workspace/project-transfer'+definition[1]+(definition[0]==='GET'&&Object.keys(args).length?'?'+new URLSearchParams(args):''))},{method:${JSON.stringify(definition[0])},headers:{'Content-Type':'application/json','Tuldok-Operation-Contract':${JSON.stringify(headers[operation])}},${definition[0]==='POST'?'body:'+JSON.stringify(JSON.stringify(args))+',':''}cache:'no-store'});return {status:response.status,value:await response.json()};})()`);}
  async function capture(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'No horizontal overflow at '+width);fs.writeFileSync(path.join(output,name),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));screenshots.push(name);}
  try{
    const isolation=JSON.parse(execFileSync('python3',['-c',"import json,os,psycopg;from psycopg.conninfo import conninfo_to_dict;s=conninfo_to_dict(os.environ['M5_SOURCE_DSN']);c=psycopg.connect(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);r=c.execute('SELECT current_database(),current_user,has_database_privilege(current_user,%s,%s)',(s['dbname'],'CONNECT')).fetchone();assert not r[2];print(json.dumps(dict(database=r[0],role=r[1],source_connect=r[2])));c.close()"],{cwd:root,env:{...process.env,M5_SOURCE_DSN:sourceDsn},encoding:'utf8'}));
    await start();const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
    const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort')),tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
    socket=new WebSocket(target.webSocketDebuggerUrl);await once(socket,'open');session=cdpSession(socket,{onEvent:event=>{
      if(event.method==='Runtime.exceptionThrown')errors.push(event.params.exceptionDetails);
      if(event.method==='Network.responseReceived'&&event.params.response.status>=400)httpFailures.push({url:event.params.response.url,status:event.params.response.status});
      if(event.method==='Network.requestWillBeSent'&&event.params.request.url.includes('/api/workspace/project-transfer'))transferRequests.push({url:event.params.request.url,method:event.params.request.method,body:event.params.request.postData??null});
      if(event.method==='Fetch.requestPaused'){const own=dropExtract&&new URL(event.params.request.url).pathname==='/api/workspace/project-transfer/extract';if(own){dropExtract=false;dropped=true;void send('Fetch.failRequest',{requestId:event.params.requestId,errorReason:'ConnectionClosed'});}else void send('Fetch.continueRequest',{requestId:event.params.requestId});}
    }});send=session.send;evaluate=async expression=>{const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
    await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Page.navigate',{url:origin+'/project-transfer'});await signin(sourceRoot,sourceDsn);await until(()=>evaluate('!document.getElementById("selection-fields").disabled'),'source controller ready');
    await fill('#snapshot-id',fixture.project_id);await fill('#snapshot-sha',fixture.manifest_sha256);await fill('#selection-ids',fixture.record_id);await activate('#selection-add');
    await evaluate('document.getElementById("working-add").closest("details").open=true');await choose('#working-kind','script');await fill('#working-path','scripts/must-not-run.py');await activate('#working-add');await activate('#transfer-preview');await until(()=>evaluate('document.getElementById("report-summary").textContent.includes("unassigned 41")'),'actual source preview');
    await choose('#report-section','unassigned');await activate('#report-load');await until(()=>evaluate('document.getElementById("report-items").children.length===40'),'forty-row report page');await activate('#report-next');await until(()=>evaluate('document.getElementById("report-page-status").textContent.includes("41–41 of 41")'),'explicit last report page');
    await capture('preview-1440.jpg',1440,'#report-title');await capture('preview-390.jpg',390,'#report-title');
    // A second actual owner request changes the controller report. The UI must
    // reject its stale hash and require review, not silently reattach the draft.
    const live=await api('status'),other=clone(business);other.roots.records=[fixture.other_id];assert.equal((await api('preview',{binding:live.value.binding,selection:other})).status,200);await activate('#report-load');await until(()=>evaluate('document.getElementById("transfer-error").textContent.includes("stale")'),'actual stale report error');assert.ok(await evaluate('document.getElementById("transfer-stop").disabled'));await activate('#transfer-refresh');await until(()=>evaluate('!document.getElementById("transfer-refresh").disabled'));await activate('#transfer-preview');await until(()=>evaluate('!document.getElementById("report-reviewed").disabled'));check('Real named controls preview exact selection, page41 unassigned facts and reject a stale report');
    await toggle('#report-reviewed');await fill('#backup-directory','verified-backup');await fill('#destination-directory','independent');await toggle('#stop-confirm');await activate('#transfer-stop');await until(()=>evaluate('document.getElementById("control-signin-panel").hidden===false'),'explicit stop handoff');await signin(controlRoot,sourceDsn);await until(()=>evaluate('!document.getElementById("selection-fields").disabled'),'fresh control sign-in');
    const identities=await evaluate('({catalog:window.TuldokAuth.identity().catalog_id,source:document.getElementById("transfer-context").textContent,ready:document.getElementById("transfer-extract").disabled})');assert.notEqual(identities.catalog,fixture.source_catalog_id);assert.equal(identities.ready,true);await activate('#transfer-preview');await until(()=>evaluate('document.getElementById("report-summary").textContent.includes("Complete stopped-source closure")'),'fresh stopped-source preview');await toggle('#report-reviewed');await fill('#destination-name','Browser independent project λ');await fill('#extraction-key','browser-extract-key');await toggle('#extract-confirm');check('Explicit stop requires new standard control-host sign-in and a fresh reviewed report');
    // Lose the response only AFTER the actual backend published and attempted
    // inert selection. The page must preserve its exact request without retry.
    await send('Fetch.enable',{patterns:[{urlPattern:'*/api/workspace/project-transfer/extract',requestStage:'Response'}]});dropExtract=true;await activate('#transfer-extract');await until(()=>evaluate('document.getElementById("transfer-error").textContent.includes("Acknowledgement unavailable")'),'real lost acknowledgement');assert.ok(dropped);assert.ok(await evaluate('document.getElementById("transfer-reconcile").hidden===false'));await capture('unknown-1440.jpg',1440,'#outcome-title');await capture('unknown-390.jpg',390,'#outcome-title');await send('Fetch.disable');
    const effectsBefore=transferRequests.filter(r=>r.method==='POST'&&r.url.endsWith('/extract')).length;await activate('#transfer-refresh');await until(()=>evaluate('!document.getElementById("transfer-refresh").disabled'));assert.equal(transferRequests.filter(r=>r.method==='POST'&&r.url.endsWith('/extract')).length,effectsBefore);await activate('#transfer-reconcile');await until(()=>evaluate('document.getElementById("transfer-receipt").textContent.includes("reconciled")'),'explicit exact-key reconciliation');
    const attempts=transferRequests.filter(r=>r.method==='POST'&&r.url.endsWith('/extract'));assert.equal(attempts.length,2);assert.deepEqual(JSON.parse(attempts[0].body),JSON.parse(attempts[1].body));assert.ok(await evaluate('document.getElementById("selection-outcome").textContent.includes("was selected")'));await capture('selected-1440.jpg',1440,'#outcome-title');await capture('selected-390.jpg',390,'#outcome-title');check('Actual lost publication acknowledgement retains request; read-only refresh never retries; explicit reconciliation selects the same current destination');
    const verified=await api('status');assert.equal(verified.status,200);const project=verified.value.last_receipt;assert.ok(project&&project.committed);
    // Release the selected Store before independent canonical reading.
    await stop(server);server=null;
    const canonical=JSON.parse(execFileSync('python3',['-c',"import json,os;from project_store import ProjectStore;s=ProjectStore.open(os.environ['M5_DEST']);print(json.dumps(s.snapshot()));s.close()"],{cwd:root,env:{...process.env,M5_DEST:path.join(publication,'independent')},encoding:'utf8'}));
    assert.equal(canonical.project_id,project.project_id);
    const beforeCold=fs.readFileSync(path.join(publication,'independent','.tuldok','project.json'));
    await start(true);await send('Page.navigate',{url:origin+'/project-files'});await signin(coldRoot,coldDsn);await until(()=>evaluate('document.querySelector("#project-files-root option")&&!document.getElementById("project-files-open").disabled'),'cold file workspace');await choose('#project-files-root','output');await fill('#project-files-directory','independent');await activate('#project-files-open');await until(()=>evaluate('document.querySelectorAll("#records-list [data-record-id]").length===1'),'cold reconstructed source');await activate('#records-list [data-record-id]');await until(()=>evaluate('document.getElementById("record-text").value==='+JSON.stringify(fixture.normalized_text)),'cold exact normalized text');
    const current=await evaluate(`(async()=>{const response=await window.TuldokAuth.fetch('/api/workspace/project-files',{headers:{'Tuldok-Operation-Contract':${JSON.stringify(headers['project_files.status'])}}});return await response.json();})()`);assert.equal(current.project.project_id,project.project_id);assert.equal(current.project.checkpoint,project.checkpoint);assert.deepEqual(fs.readFileSync(path.join(publication,'independent','.tuldok','project.json')),beforeCold);assert.ok(!fs.existsSync(path.join(publication,'independent','scripts','EXECUTED')));await capture('cold-1440.jpg',1440,'#record-heading');await capture('cold-390.jpg',390,'#record-heading');
    const preservation=JSON.parse(execFileSync('python3',['-c',"import json,os,pathlib;from types import SimpleNamespace;from project_transfer import ReadonlyCatalog,_snapshot;from backup_metadata import tree_manifest;root=pathlib.Path(os.environ['M5_SOURCE']);m=json.loads((root/'.tuldok.json').read_text());db=ReadonlyCatalog(os.environ['M5_SOURCE_DSN'],'catalog_'+m['dataset_id'],m['dataset_id'],root);_,_,actual=_snapshot(SimpleNamespace(db=db));db.close();backup=json.loads((pathlib.Path(os.environ['M5_BACKUP'])/'backup-receipt.json').read_text());assert tree_manifest(root)==backup['files'];print(json.dumps(dict(source_sql_sha256=actual,source_files_unchanged=True)))"],{cwd:root,env:{...process.env,M5_SOURCE:sourceRoot,M5_SOURCE_DSN:sourceDsn,M5_BACKUP:path.join(publication,'verified-backup')},encoding:'utf8'}));assert.equal(preservation.source_sql_sha256,project.source.snapshot_sha256);check('Different PostgreSQL role without source access cold-opens identical project/checkpoint; source baseline and inert script preserved');
    assert.deepEqual(errors,[],'No browser runtime exceptions');for(const failed of httpFailures)assert.ok([401,409].includes(failed.status),'Unexpected failed HTTP request '+failed.status+' '+failed.url);verifySource();
    fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify({status:'pass',checks,material,test_sha256:hash(fs.readFileSync(__filename)),screenshots,source_catalog_id:fixture.source_catalog_id,control_catalog_id:identities.catalog,project_id:project.project_id,checkpoint:project.checkpoint,isolation,preservation,expected_http_failures:httpFailures,browser_runtime_errors:errors,fixture:'Disposable authored metadata and exact bytes; no model/provider execution or user lab'},null,2)+'\n');succeeded=true;console.log('Report '+path.join(output,'receipt.json'));
  }catch(error){fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({status:'fail',error:error.message,checks,material,screenshots,fixture_root:temporary,browser_runtime_errors:errors,http_failures:httpFailures},null,2)+'\n');if(evaluate)try{console.error('UI diagnostics:',await evaluate('document.body.innerText'));}catch(_){}console.error('Fixture server:',serverErrors);throw error;}
  finally{
    session?.close();socket?.close();await stopOwnedChildren(children.reverse());
    for(const {control,dsn} of catalogs)if(fs.existsSync(control))try{execFileSync('python3',['-c',"import json,os,pathlib,re,psycopg;from psycopg import sql;root=pathlib.Path(os.environ['M5_CLEAN']);values=[json.loads(p.read_text()) for p in root.rglob('.tuldok.json')];names={('projection_'+v['projection_id']) if v['version']==2 else ('catalog_'+v['dataset_id']) for v in values};assert all(re.fullmatch(r'(catalog|projection)_[a-f0-9]{32}',n) for n in names);c=psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True);[c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(n))) for n in names];c.close()"],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn,M5_CLEAN:control},stdio:['ignore','pipe','pipe']});}catch(error){console.error('Owned fixture schema cleanup failed:',error.message);succeeded=false;}
    if(succeeded)fs.rmSync(temporary,{recursive:true,force:true});else console.error('Retained owned fixture directory:',temporary);
  }
}
if(process.argv.includes('--browser'))browserCampaign().catch(error=>{console.error(error);process.exitCode=1;});
else controlledCampaign().catch(error=>{console.error(error);process.exitCode=1;});
