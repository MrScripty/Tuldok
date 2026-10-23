'use strict';
// Real browser authoring, keyboard actions and a cold process on another database.
// Inputs and runtime roots are disposable; project scripts are inert sentinels.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {once}=require('node:events');
const {authenticatedFixture}=require('./auth_helpers.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {cdpSession}=require('./browser_cdp_session.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..');
assert.ok(process.env.TULDOK_DATABASE_URL,'Use a disposable PostgreSQL TULDOK_DATABASE_URL');
assert.ok(process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL,'Cold proof requires a separate disposable database URL');
const sourceDsn=process.env.TULDOK_DATABASE_URL,coldDsn=process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL;
const gitOptions={env:{...process.env,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_TERMINAL_PROMPT:'0'}};
assert.notEqual(sourceDsn,coldDsn,'Source and cold connection configuration must differ');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-project-files-browser-'));
const report=qaDirectory(root,'project-files-m2');
const external=path.join(temporary,'external');fs.mkdirSync(external);
const sourceControl=path.join(temporary,'control'),coldControl=path.join(temporary,'cold-control');
const TEXT='Café 山 🧪 — browser-authored source\nThe scientist’s unique rationale stays exact.\n';
const name='Browser source 山',label='positive 山',corpusNote='Earlier corpus note café 山 — preserve this scientific rationale.';
const checks=[],errors=[],httpErrors=[],children=[],catalogs=[],responsiveFailures=[];
const observationHeaders=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;print(json.dumps({name:agent_api.selected_header('project_files.'+name) for name in ('status','query','get')}))"],{cwd:root,encoding:'utf8'}));
const material={head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8',...gitOptions}).trim(),files:Object.fromEntries(['app.py','metadata.py','access.py','workbench.py','agent_api.py','project_store.py','project_text.py','project_workspace.py','static/project-files.html','static/project-files.js','static/project-files.css','tests/browser_project_files_m2.cjs'].map(file=>[file,fs.existsSync(path.join(root,file))?crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'):null]))};
const freeze=JSON.parse(fs.readFileSync(process.env.TULDOK_M2_FREEZE_MANIFEST||'/workspace/scratch/tuldok-save-load-qa/m2-product-freeze.json','utf8'));
material.files=freeze.files;
for(const [file,sha] of Object.entries(material.files))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),sha,'Freeze mismatch '+file);
const testMaterial=Object.fromEntries(['tests/browser_project_files_m2.cjs','tests/test_project_files_m2_http.py'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
let socket,session,server,serverErrors='',origin,fixtureAuth,send,evaluate;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,message='Timed out'){
  for(let i=0;i<200;i++){const value=await fn();if(value)return value;await pause(100);}
  throw Error(message);
}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function snapshot(directory){
  const values={};
  function walk(current){for(const entry of fs.readdirSync(current,{withFileTypes:true})){
    if(['.git','.tuldok-local'].includes(entry.name))continue;
    const next=path.join(current,entry.name);
    if(entry.isDirectory())walk(next);
    else if(entry.isFile())values[path.relative(directory,next)]=crypto.createHash('sha256').update(fs.readFileSync(next)).digest('hex');
    else throw Error('Unexpected project special file '+entry.name);
  }}walk(directory);return values;
}
async function stop(child){
  if(!child||child.exitCode!==null||child.signalCode!==null)return;
  const exited=once(child,'exit');child.kill('SIGTERM');await exited;
}
async function start(control,configuredRoot,dsn){
  process.env.TULDOK_DATABASE_URL=dsn;
  serverErrors='';
  server=launch('python3',['-u','app.py','--port','0','--data',control,'--project-files-root','fixture='+configuredRoot],{cwd:root,stdio:['ignore','pipe','pipe'],env:{...process.env,TULDOK_DATABASE_URL:dsn}});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];},'Project-files server readiness: '+serverErrors);
  origin='http://127.0.0.1:'+port;
  catalogs.push({control,dsn});
  fixtureAuth=authenticatedFixture();
  await fixtureAuth.register(origin,control,root);
  return origin;
}
async function jsonApi(relative){
  const route=relative.split('?')[0],operation=route.endsWith('/records')?'query':route.includes('/records/')?'get':'status';
  const response=await fixtureAuth.fetch(origin+relative,{headers:{'Tuldok-Operation-Contract':observationHeaders[operation]}});
  const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;
}
async function state(){return jsonApi('/api/workspace/project-files');}
async function detail(recordId){
  const current=await state();
  return jsonApi('/api/workspace/project-files/records/'+recordId+'?'+new URLSearchParams({binding:current.binding,checkpoint:current.project.checkpoint,history_limit:'4'}));
}
async function key(key,code=key,modifiers=0){
  for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Tab:9,Escape:27,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});
}
async function focus(selector){
  await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});e.focus();return document.activeElement===e;})()`),'Focusable control '+selector);
}
async function fill(selector,value){await focus(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
async function activate(selector){await focus(selector);await key('Enter');}
async function choose(selector,value){
  await focus(selector);
  await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!Array.from(e.options).some(o=>o.value===${JSON.stringify(value)}))throw Error('Missing rendered option');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function ready(){await until(()=>evaluate('!!document.querySelector("#project-files-root option")&&!document.getElementById("project-files-new").disabled'),'Project files UI ready');}
async function navigate(){await fixtureAuth.browser(send,origin);await send('Page.navigate',{url:origin+'/project-files'});await ready();}
async function capture(filename,width,selector='#record-heading'){
  await send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const bounds=await evaluate(`(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,selectedValues:['project-scientific-reference','project-explore-kind','project-data-kind','project-files-root'].map(id=>({id,value:document.getElementById(id).value,text:document.getElementById(id).selectedOptions?.[0]?.textContent})),fieldsets:Array.from(document.querySelectorAll('fieldset')).filter(e=>e.getClientRects().length).map(e=>({id:e.id,width:Math.round(e.getBoundingClientRect().width),right:Math.round(e.getBoundingClientRect().right),minWidth:getComputedStyle(e).minWidth})),offenders:Array.from(document.querySelectorAll('body *')).filter(e=>e.getClientRects().length&&e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,className:e.className,width:Math.round(e.getBoundingClientRect().width),right:Math.round(e.getBoundingClientRect().right),scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,minWidth:getComputedStyle(e).minWidth,text:e.textContent.slice(0,100)})).slice(-25)}))()`);
  fs.writeFileSync(path.join(report,'bounds-'+width+'.json'),JSON.stringify(bounds,null,2)+'\n');
  fs.writeFileSync(path.join(report,filename),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  if(bounds.width>bounds.viewport+1){responsiveFailures.push({width,filename,bounds});console.error('RESPONSIVE_FAILURE '+JSON.stringify({width,viewport:bounds.viewport,scrollWidth:bounds.width,clientWidth:bounds.clientWidth,report:path.join(report,'bounds-'+width+'.json')}));}
}
function check(message){checks.push(message);console.log('PASS '+message);}

const routes=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;names=tuple(n.split('.')[1] for n in agent_api.PROJECT_FILES_M2);print(json.dumps({n:{**{k:agent_api.operation('project_files.'+n)[k] for k in ('path','method','query','side_effects')},'header':agent_api.selected_header('project_files.'+n)} for n in names}))"],{cwd:root,encoding:'utf8'}));
async function observe(action,fields={}){
  const current=await state(),route=routes[action],args={binding:current.binding,...(route.side_effects?{expected_checkpoint:current.project.checkpoint,request_key:crypto.randomUUID().replaceAll('-','')}:{checkpoint:current.project.checkpoint}),...fields};
  let target=route.path;for(const [key,value] of Object.entries(args))target=target.replace('{'+key+'}',encodeURIComponent(value));
  const query=new URLSearchParams(Object.entries(args).filter(([key])=>route.query.includes(key)));
  if(query.size)target+='?'+query;
  const body=Object.fromEntries(Object.entries(args).filter(([key])=>!route.query.includes(key)&&!route.path.includes('{'+key+'}')));
  const response=await fixtureAuth.fetch(origin+target,{method:route.method,headers:{'Content-Type':'application/json','Tuldok-Operation-Contract':route.header},...(route.method==='POST'?{body:JSON.stringify(body)}:{})});
  const envelope=await response.json();assert.equal(response.status,200,JSON.stringify(envelope));return envelope.value;
}
async function settled(){await until(()=>evaluate('!document.getElementById("project-files-save").disabled&&!document.getElementById("project-files-dirty").textContent.includes("unsent")'),'UI acknowledges saved operation');}
async function explore(kind,contains){
  await choose('#project-explore-kind',kind);await activate('#project-explore-load');await settled();
  await until(()=>evaluate(`Array.from(document.querySelectorAll('#project-explore-list button')).some(e=>e.textContent.includes(${JSON.stringify(contains)}))`),'Rendered saved record '+contains);
  await evaluate(`(()=>{for(const e of document.querySelectorAll('#project-explore-list button'))if(e.textContent.includes(${JSON.stringify(contains)})){e.dataset.qaSelected='yes';break;}})()`);
  await activate('#project-explore-list button[data-qa-selected="yes"]');await settled();
}
async function fileInput(selector,file){
  const document=await send('DOM.getDocument',{depth:1});const {nodeId}=await send('DOM.querySelector',{nodeId:document.root.nodeId,selector});
  assert.ok(nodeId,'Actual native file input exists');await send('DOM.setFileInputFiles',{nodeId,files:[file]});
}
(async()=>{
  // Cold runtime role must genuinely lack CONNECT to the source database.
  const isolation=JSON.parse(execFileSync('python3',['-c',
    "import json,os,psycopg;from psycopg.conninfo import conninfo_to_dict;source=conninfo_to_dict(os.environ['TULDOK_DATABASE_URL']);cold=conninfo_to_dict(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);assert source['dbname']!=cold['dbname'];c=psycopg.connect(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);row=c.execute('SELECT current_database(), current_user, has_database_privilege(current_user,%s,%s)',(source['dbname'],'CONNECT')).fetchone();assert not row[2], 'Cold role must not connect to source database';print(json.dumps({'database':row[0],'role':row[1],'source_connect':row[2]}));c.close()"
  ],{cwd:root,encoding:'utf8'}));
  await start(sourceControl,external,sourceDsn);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();
  const target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await once(socket,'open');
  session=cdpSession(socket,{onEvent:event=>{
    if(event.method==='Runtime.exceptionThrown')errors.push(event.params.exceptionDetails);
    if(event.method==='Network.responseReceived'&&event.params.response.status>=400)httpErrors.push({url:event.params.response.url,status:event.params.response.status});
  }});send=session.send;
  evaluate=async expression=>{const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');

  execFileSync('python3',['-c',"import pathlib,sys;sys.path.insert(0,'tests');from test_project_files_m2_http import authored_source;from PIL import Image;root=pathlib.Path(sys.argv[1]);authored_source(root);Image.new('RGB',(20,12),'#3355aa').save(root/'image.png','PNG')",external],{cwd:root});
  await navigate();
  await choose('#project-files-root','fixture');await fill('#project-files-directory','alpha');await fill('#project-files-name','Browser M2 authored project 山');
  await activate('#project-files-new');await until(async()=>((await state()).state==='open'));await settled();


  if(process.env.TULDOK_M2_RESPONSIVE_ONLY==='1'){
    const imported=await observe('data_import_image',{image:fs.readFileSync(path.join(external,'image.png')).toString('base64'),name:'Cold responsive image café 山',groups:['responsive-image'],rights:'Owned authored pixels'});
    const corrected=await observe('data_rights',{record_id:imported.id,revision:imported.revision,source_revision:imported.source_revision,note:'Exact cold responsive rights café 山'});
    const expected=await observe('data_get',{record_id:imported.id}),expectedHistory=await observe('data_history',{record_id:imported.id,limit:4});
    await activate('#project-files-refresh');await settled();await activate('#project-files-close');await until(async()=>((await state()).state==='no_project_open'));await stop(server);
    const source=path.join(external,'alpha'),before=snapshot(source),coldExternal=path.join(temporary,'cold-external');fs.mkdirSync(coldExternal);const clone=path.join(coldExternal,'clone');
    execFileSync('git',['init','-q','--template=',source],gitOptions);execFileSync('git',['-C',source,'add','.'],gitOptions);
    execFileSync('git',['-C',source,'-c','user.name=Disposable Responsive QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Cold history responsive fixture'],gitOptions);
    execFileSync('git',['-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',source,clone],gitOptions);fs.cpSync(path.join(source,'artifacts'),path.join(clone,'artifacts'),{recursive:true});
    await start(coldControl,coldExternal,coldDsn);await navigate();await choose('#project-files-root','fixture');await fill('#project-files-directory','clone');await activate('#project-files-open');await until(async()=>((await state()).state==='open'));await settled();
    assert.deepEqual(await observe('data_get',{record_id:imported.id}),expected);assert.deepEqual(await observe('data_history',{record_id:imported.id,limit:4}),expectedHistory);
    await choose('#project-data-kind','image');await explore('data_query','Cold responsive image café 山');await activate('#project-detail-history');
    await until(()=>evaluate('document.getElementById("project-detail-history-list").textContent.includes("Exact cold responsive rights café 山")'));
    await capture('focused-cold-history-390.jpg',390,'#project-detail-history-list');await capture('focused-cold-history-1440.jpg',1440,'#project-detail-history-list');
    assert.deepEqual(snapshot(clone),before);assert.deepEqual(errors,[]);assert.deepEqual(httpErrors,[]);
    for(const [file,digest] of Object.entries(material.files))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),digest,'Frozen product source changed '+file);
    for(const [file,digest] of Object.entries(testMaterial))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),digest,'Acceptance source changed '+file);
    fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:responsiveFailures.length?'failed':'pass',gate:'focused_cold_history_responsive',prior_functional_and_cold_receipt:'/workspace/scratch/tuldok-save-load-qa/artifacts/project-files-m2/run-DDH5l1/receipt.json',responsive_failures:responsiveFailures,isolation,material,test_material:testMaterial,image_id:imported.id,history_count:expectedHistory.items.length,browser_runtime_errors:errors,http_errors:httpErrors,canonical_sha256:before,fixture:'Real HTTP-authored image/rights history; real Git metadata clone and explicit untracked payload transfer; actual cold UI history'},null,2)+'\n');
    console.log('Focused responsive report '+path.join(report,'receipt.json'));if(responsiveFailures.length)throw Error('Focused cold history responsive overflow remains');return;
  }
  let imageId,fieldId,studyId,projectId,expectedImage,expectedField,expectedStudy,rights,scienceNote;
  if(process.env.TULDOK_M2_RESUME_HTTP==='1'){
    const seedImage=await observe('data_import_image',{image:fs.readFileSync(path.join(external,'image.png')).toString('base64'),name:'Browser image café 山',groups:['browser-image'],rights:'Owned authored synthetic pixels'});imageId=seedImage.id;
    rights='Browser corrected exact rights café 山';await observe('data_rights',{record_id:imageId,revision:seedImage.revision,source_revision:seedImage.source_revision,note:rights});expectedImage=await observe('data_get',{record_id:imageId});
    await observe('selection_create',{document:{name:'Browser fixed image revision 山',items:[{id:imageId,revision:expectedImage.revision,source_revision:expectedImage.source_revision}]}});
    await observe('search_create',{document:{name:'Browser entered search café 山',criteria:{q:'café',kind:'image',review:'',sort:'',task:'',label:'',group:'',rights:''}}});
    const unpinned=JSON.parse(fs.readFileSync(path.join(external,'source-project.json'),'utf8'));delete unpinned.data[0].sha256;fs.writeFileSync(path.join(external,'source-project.json'),JSON.stringify(unpinned));
    const registered=await observe('source_register',{root:'fixture',manifest_path:'source-project.json'}),snapshot=Object.fromEntries(['origin_catalog_id','project_id','manifest_sha256'].map(key=>[key,registered[key]]));
    const scientificRaw=fs.readFileSync(path.join(external,'observed-fields.zip'));
    const field=await observe('data_import_scientific',{snapshot,reference_id:'fields',expected_sha256:crypto.createHash('sha256').update(scientificRaw).digest('hex'),document:{name:'Browser exact field sequence 山',groups:['browser-science'],rights:'Owned authored scientific arrays'}});fieldId=field.id;
    scienceNote='Retained browser observation note café 山';await observe('data_annotate',{record_id:fieldId,revision:field.revision,source_revision:field.source_revision,task:field.task,annotation:{note:scienceNote},groups:field.groups,review:'draft'});expectedField=await observe('data_get',{record_id:fieldId});
    const mismatch={...unpinned,id:crypto.randomUUID().replaceAll('-',''),data:[{...unpinned.data[0],sha256:'0'.repeat(64)}]};fs.writeFileSync(path.join(external,'mismatch-project.json'),JSON.stringify(mismatch));
    const study=await observe('study_create',{name:'Browser Study hypothesis 山',limits:{attempt_slots:1,admitted_wall_seconds:60,retained_bytes:1048576,peak_staging_bytes:1048576},policy:{format:'selection_policy_v1',metric_definition_sha256:'b'.repeat(64),checkpoint_rule:'selected',replicate_reduce:'individual',required_capabilities:[],numerical_acceptance:'diagnostic',tie_break:'trial_id'}});
    const revised=await observe('study_save',{study_id:study.id,revision:study.revision,name:'Browser revised Study hypothesis 山',limits:study.limits,policy:study.policy});studyId=revised.id;projectId=(await state()).project.project_id;
    expectedStudy=await observe('study',{study_id:studyId,origin_catalog_id:projectId,limit:1});
    await activate('#project-files-refresh');await settled();
    await fill('#project-register-path','mismatch-project.json');await activate('#project-register-form button[type="submit"]');await settled();
    await explore('studies','Browser revised Study hypothesis 山');
    check('Equivalent authored fixture seeded through actual HTTP; prior4UIauthoringgroups retained, CSS and cold remainder are this targeted campaign');
  }else{
  await fill('#project-source-name','Browser image café 山');await fill('#project-source-groups','browser-image');await fill('#project-source-rights','Owned authored synthetic pixels');
  await fileInput('#project-source-file',path.join(external,'image.png'));await activate('#project-source-form button[type="submit"]');await settled();
  const rows=await observe('data_query',{kind:'image',limit:40});assert.equal(rows.items.length,1);imageId=rows.items[0].id;
  await choose('#project-data-kind','image');await explore('data_query','Browser image café 山');
  rights='Browser corrected exact rights café 山';await fill('#project-rights-note',rights);await activate('#project-rights-form button[type="submit"]');await settled();
  await explore('data_query','Browser image café 山');
  await fill('#project-selection-name','Browser fixed image revision 山');await activate('#project-selection-form button[type="submit"]');await settled();
  await fill('#project-data-search','café');await fill('#project-search-name','Browser entered search café 山');await activate('#project-search-form button[type="submit"]');await settled();
  await explore('data_query','Browser image café 山');await activate('#project-detail-history');
  await until(()=>evaluate('document.getElementById("project-detail-history-list").textContent.includes('+JSON.stringify(rights)+')'),'Exact corrected rights shown in actual history controls');
  await activate('#project-detail-availability');await settled();
  expectedImage=await observe('data_get',{record_id:imageId});assert.equal(expectedImage.task,'image_detection');assert.equal(expectedImage.provenance.rights_note_correction.note,rights);
  check('Actual native image upload, keyboard rights correction, fixed selection, saved search and visible revision history');
  // Explicit owner registration is a separate form from imported historical paths.
  const unpinned=JSON.parse(fs.readFileSync(path.join(external,'source-project.json'),'utf8'));delete unpinned.data[0].sha256;fs.writeFileSync(path.join(external,'source-project.json'),JSON.stringify(unpinned));
  await fill('#project-register-path','source-project.json');await activate('#project-register-form button[type="submit"]');await settled();
  await until(()=>evaluate('document.querySelectorAll("#project-scientific-reference option").length===1'),'Real source reference appears');
  await fill('#project-scientific-name','Browser exact field sequence 山');await fill('#project-scientific-groups','browser-science');await fill('#project-scientific-rights','Owned authored scientific arrays');
  await activate('#project-scientific-form button[type="submit"]');await settled();
  const mismatch={...unpinned,id:crypto.randomUUID().replaceAll('-',''),data:[{...unpinned.data[0],sha256:'0'.repeat(64)}]};fs.writeFileSync(path.join(external,'mismatch-project.json'),JSON.stringify(mismatch));
  await fill('#project-register-path','mismatch-project.json');await activate('#project-register-form button[type="submit"]');await settled();
  assert.equal(await evaluate('Array.from(document.querySelectorAll("#project-scientific-reference option")).filter(option=>!option.disabled).length'),0,'Declared hash mismatch must not be selectable for import');
  await fill('#project-data-search','');await choose('#project-data-kind','field_sequence');await explore('data_query','Browser exact field sequence 山');
  scienceNote='Retained browser observation note café 山';await fill('#project-data-note',scienceNote);await activate('#project-data-note-form button[type="submit"]');await settled();
  const fields=await observe('data_query',{kind:'field_sequence',limit:40});assert.equal(fields.items.length,1);fieldId=fields.items[0].id;
  expectedField=await observe('data_get',{record_id:fieldId});assert.equal(expectedField.annotation.note,scienceNote);
  await explore('data_query','Browser exact field sequence 山');await activate('#project-detail-availability');await settled();
  check('Actual unpinned source registration uses current observed hash; declared mismatch is unavailable; exact scientific import, note and availability controls');
  // A missing source remains metadata and is resolved only through an explicit
  // current-root file selection. No automatic search or source grant occurs.
  const artifactSha=expectedField.source_sha256,artifactPath=path.join(external,'alpha','artifacts','sha256',artifactSha);
  assert.ok(fs.existsSync(artifactPath),'Imported exact scientific artifact exists');
  const originalArtifact=fs.readFileSync(artifactPath);fs.unlinkSync(artifactPath);
  await explore('artifacts',artifactSha);await activate('#project-artifact-status');
  await until(()=>evaluate('!document.getElementById("project-artifact-resolve-form").hidden'),'Missing artifact resolution offered explicitly');
  await choose('#project-artifact-root','fixture');await fill('#project-artifact-path','observed-fields.zip');await activate('#project-artifact-resolve-form button[type="submit"]');await settled();
  await activate('#project-artifact-status');await settled();
  assert.equal((await observe('artifact_status',{sha256:artifactSha})).state,'verified');
  assert.deepEqual(fs.readFileSync(artifactPath),originalArtifact);
  check('Missing artifact survives as metadata and explicit current-root resolution restores verified exact bytes');
  await fill('#project-study-create-name','Browser Study hypothesis 山');await fill('#project-study-metric','b'.repeat(64));
  await activate('#project-study-create-form button[type="submit"]');await settled();
  await explore('studies','Browser Study hypothesis 山');
  await fill('#project-metadata-name','Browser revised Study hypothesis 山');await activate('#project-metadata-form button[type="submit"]');await settled();
  await explore('studies','Browser revised Study hypothesis 山');
  const studies=await observe('studies',{limit:40});assert.equal(studies.items.length,1);studyId=studies.items[0].study.id;
  projectId=(await state()).project.project_id;
  expectedStudy=await observe('study',{study_id:studyId,origin_catalog_id:projectId,limit:1});assert.equal(expectedStudy.study.revision,2);
  check('Study creation and metadata revision use actual named controls without execution');
  }
  await activate('#project-files-save');await settled();const beforeClose=await state();
  await capture('m2-authored-1440.jpg',1440,'#project-detail-title');await capture('m2-authored-390.jpg',390,'#project-detail-title');
  if(process.env.TULDOK_M2_LAYOUT_ONLY==='1'){console.log('Layout-only probe complete '+report);return;}
  await activate('#project-files-close');await until(async()=>((await state()).state==='no_project_open'));await stop(server);
  const source=path.join(external,'alpha');fs.mkdirSync(path.join(source,'scripts'),{recursive:true});
  fs.writeFileSync(path.join(source,'scripts','sentinel.py'),"from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('bad')\n");
  const before=snapshot(source),coldExternal=path.join(temporary,'cold-external');fs.mkdirSync(coldExternal);const clone=path.join(coldExternal,'clone');
  execFileSync('git',['init','-q','--template=',source],gitOptions);execFileSync('git',['-C',source,'add','.'],gitOptions);
  execFileSync('git',['-C',source,'-c','user.name=Disposable M2 QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Authored M2 browser fixture'],gitOptions);
  execFileSync('git',['-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',source,clone],gitOptions);fs.cpSync(path.join(source,'artifacts'),path.join(clone,'artifacts'),{recursive:true});assert.deepEqual(snapshot(clone),before);
  await start(coldControl,coldExternal,coldDsn);await navigate();await choose('#project-files-root','fixture');await fill('#project-files-directory','clone');await activate('#project-files-open');
  await until(async()=>((await state()).state==='open'));await settled();assert.deepEqual((await state()).project,beforeClose.project);
  assert.deepEqual(await observe('data_get',{record_id:imageId}),expectedImage);assert.deepEqual(await observe('data_get',{record_id:fieldId}),expectedField);
  assert.deepEqual(await observe('study',{study_id:studyId,origin_catalog_id:projectId,limit:1}),expectedStudy);
  await fill('#project-data-search','');await choose('#project-data-kind','image');await explore('data_query','Browser image café 山');
  assert.equal(await evaluate('document.getElementById("project-rights-note").value'),rights);
  await activate('#project-detail-history');await until(()=>evaluate('document.getElementById("project-detail-history-list").textContent.includes('+JSON.stringify(rights)+')'));
  await capture('m2-cold-image-390.jpg',390,'#project-detail-history-list');
  await choose('#project-data-kind','field_sequence');await explore('data_query','Browser exact field sequence 山');
  assert.equal(await evaluate('document.getElementById("project-data-note").value'),scienceNote);await activate('#project-detail-availability');await settled();
  await capture('m2-cold-science-1440.jpg',1440,'#project-detail-title');
  await activate('#project-files-save');await settled();assert.deepEqual(snapshot(clone),before);assert.ok(!fs.existsSync(path.join(clone,'scripts','EXECUTED')));
  check('Fresh process, fresh control, distinct PostgreSQL role denied source CONNECT and real Git metadata clone plus explicit untracked artifact transfer reconstruct exact data/history/Study; no-op Save changes no bytes; sentinel stays inert');
  assert.deepEqual(errors,[]);assert.deepEqual(httpErrors,[]);
  for(const [file,digest] of Object.entries(material.files))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),digest,'Frozen product source changed '+file);
  for(const [file,digest] of Object.entries(testMaterial))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),digest,'Acceptance test changed during campaign '+file);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:responsiveFailures.length?'failed':'pass',functional_gate_passed:true,cold_gate_passed:true,responsive_failures:responsiveFailures,checks,isolation,material,test_material:testMaterial,authoring:process.env.TULDOK_M2_RESUME_HTTP==='1'?'real HTTP equivalent fixture; prior UI evidence retained':'actual UI native authoring',project:beforeClose.project,image_id:imageId,field_id:fieldId,study_id:studyId,canonical_sha256:before,browser_runtime_errors:errors,http_errors:httpErrors,fixture:'Authored disposable synthetic fixtures; no training or scientific validity claim'},null,2)+'\n');
  console.log('Report '+path.join(report,'receipt.json'));if(responsiveFailures.length)throw Error('Responsive overflow remains after independently completed cold gate');
})().catch(async error=>{fs.writeFileSync(path.join(report,'failure-receipt.json'),JSON.stringify({status:'failed',error:error.message,checks,material,test_material:testMaterial,responsive_failures:responsiveFailures,browser_runtime_errors:errors,http_errors:httpErrors},null,2)+'\n');console.error('Failure receipt '+path.join(report,'failure-receipt.json'));console.error(error);console.error('Server diagnostics:',serverErrors);console.error('Browser runtime errors:',JSON.stringify(errors));console.error('HTTP errors:',JSON.stringify(httpErrors));if(evaluate)try{console.error('UI diagnostics:',await evaluate('document.body.innerText'));}catch(diagnostic){console.error('UI diagnostics unavailable:',diagnostic.message);}process.exitCode=1;}).finally(async()=>{
  session?.close();socket?.close();
  for(const child of children.reverse())await stop(child);
  // Drop only UUID catalog schemas whose manifests live under this owned root.
  for(const {control,dsn} of catalogs){
    try{execFileSync('python3',['-c',
      "import json,pathlib,os,psycopg;from psycopg import sql;root=pathlib.Path(os.environ['QA_CONTROL']);c=psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True);[(c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(('projection_'+v['projection_id']) if v['version']==2 else ('catalog_'+v['dataset_id']))))) for p in root.rglob('.tuldok.json') for v in [json.loads(p.read_text())]];c.close()"
    ],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn,QA_CONTROL:control},stdio:['ignore','pipe','pipe']});}catch(error){console.error('Owned schema cleanup failed:',error.message);process.exitCode=1;}
  }
  process.env.TULDOK_DATABASE_URL=sourceDsn;
  fs.rmSync(temporary,{recursive:true,force:true});
});
