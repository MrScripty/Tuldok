'use strict';
// Actual native authoring from a portable owner-prepared bound Project and CPU catalog.
// The fixture supplies real captured source/data/runtime, never a successful API response.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const auth=require('./auth_helpers.cjs').authenticatedFixture(),{waitForDebugger}=require('./browser_startup.cjs'),{qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-bound-model-browser-')),report=qaDirectory(root,'bound-model-author'),children=[],calls=[],errors=[],captures=[];
const hashes=Object.fromEntries(['static/workspace-service.js','static/workspace-projects.js','static/workspace-real.js','static/workspaces.js','static/workspaces.css','tests/browser_extension_model_author.cjs'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
let ws,send,evaluate,serverErrors='';
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,message='Timed out'){for(let i=0;i<1800;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  assert.ok(process.env.TULDOK_BOUND_MODEL_BROWSER_RECEIPT,'Provide a real bound Project/runtime receipt');
  const fixturePath=path.resolve(process.env.TULDOK_BOUND_MODEL_BROWSER_RECEIPT),fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
  const data=fixture.catalog_path;assert.ok(data&&fixture.project_id&&fixture.recipe_id&&fixture.project_roots,'Receipt needs catalog_path, project_id, recipe_id and project_roots');
  const server=launch('python3',['-u','app.py','--port','0','--data',data,...Object.entries(fixture.project_roots).flatMap(([alias,directory])=>['--project-root',alias+'='+directory])],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1],'Application did not start'),base='http://127.0.0.1:'+port;
  await auth.register(base,data,root);
  const before=await(await auth.fetch(base+'/api/workspace/runs')).json();
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const debug=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const target=await until(async()=>{const list=await(await globalThis.fetch('http://127.0.0.1:'+debug+'/json')).json();return list.find(item=>item.type==='page'&&item.url==='about:blank');});
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let sequence=0;const pending=new Map();send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},45000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const value=JSON.parse(event.data);if(value.id){const entry=pending.get(value.id);if(entry){pending.delete(value.id);value.error?entry.reject(value.error):entry.resolve(value.result);}}if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails);if(value.method==='Network.requestWillBeSent'){const request=value.params.request;if(request.method==='POST'&&request.url.includes('/api/workspace/'))calls.push({url:request.url,body:request.postData?JSON.parse(request.postData):null,wire:request.postData||null});}};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const el=selector=>'document.querySelector('+JSON.stringify(selector)+')';
  async function key(value,code=value){const vk={Enter:13,Tab:9,Escape:27,' ':32}[value]||0;for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key:value,code,windowsVirtualKeyCode:vk,...(value==='Enter'&&type==='keyDown'?{text:'\r',unmodifiedText:'\r'}:{})});}
  async function focus(selector){await until(()=>evaluate(`!!${el(selector)}&&!${el(selector)}.disabled`),'Control not ready: '+selector);await evaluate(`${el(selector)}.scrollIntoView({block:'center'});${el(selector)}.focus()`);assert.equal(await evaluate(`document.activeElement===${el(selector)}`),true,'Actual keyboard focus: '+selector);}
  async function activate(selector){await focus(selector);await key('Enter');}
  async function fill(selector,value){await focus(selector);const control=await evaluate(`({tag:${el(selector)}.tagName,type:${el(selector)}.type,checked:${el(selector)}.checked})`);if(control.type==='checkbox'){assert.equal(typeof value,'boolean');if(control.checked!==value)await key(' ','Space');return;}if(control.tag==='SELECT'){const option=await evaluate(`Array.from(${el(selector)}.options).find(option=>option.textContent===${JSON.stringify(String(value))})?.value`);assert.notEqual(option,undefined,'Declared enum option '+selector);await select(selector,option);return;}await send('Input.dispatchKeyEvent',{type:'keyDown',key:'a',code:'KeyA',modifiers:2,windowsVirtualKeyCode:65});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',modifiers:2,windowsVirtualKeyCode:65});await send('Input.insertText',{text:String(value)});await key('Tab');}
  async function select(selector,value){await evaluate(`(()=>{const node=${el(selector)};if(!node)throw Error('Missing native select');node.value=${JSON.stringify(value)};if(node.value!==${JSON.stringify(value)})throw Error('Unavailable option');node.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
  async function capture(name,width,height=900){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});if(name.includes('exact-review'))await evaluate('document.getElementById("extension-review-heading")?.scrollIntoView({block:"start"})');await evaluate('document.fonts.ready.then(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))');assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Page overflow '+name);const geometry=await evaluate(`(()=>{const node=document.getElementById('extension-model-dialog');if(!node?.open)return null;const box=node.getBoundingClientRect();return {left:box.left,right:box.right,top:box.top,bottom:box.bottom};})()`);if(geometry){assert.ok(geometry.left>=0&&geometry.right<=width+1&&geometry.top>=0&&geometry.bottom<=height+1,JSON.stringify(geometry));}const image=await send('Page.captureScreenshot',screenshotOptions),file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from(image.data,'base64'));captures.push({file,width,height});}
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await auth.browser(send,base);await send('Page.navigate',{url:base+'/workspaces'});
  await until(()=>evaluate('!!document.getElementById("fixture-label")'));await until(()=>evaluate(`Array.from(document.getElementById('dataset').options).some(option=>option.value===${JSON.stringify('project:'+fixture.project_id)})`),'Saved Project did not appear');
  await select('#dataset','project:'+fixture.project_id);await activate('#nav-pipeline');await until(()=>evaluate(`!!document.querySelector('[data-project-recipe="${fixture.recipe_id}"]')`));
  if(fixture.ordinary_recipe_id){
    await activate('[data-project-recipe="'+fixture.ordinary_recipe_id+'"]');
    await until(()=>evaluate('document.getElementById("external-create-dialog").open && !!document.querySelector("[data-external-input-kind]")'),'Ordinary current recipe did not reach graph inspector');
    assert.match(await evaluate('document.getElementById("external-create-dialog").textContent'),/managed_torch_python_v1/);
    assert.equal(await evaluate('document.getElementById("extension-model-dialog").open'),false);
    const ordinaryInputs=await evaluate('Array.from(document.querySelectorAll("#external-create-dialog [data-external-input-kind]")).map(node=>({name:node.dataset.externalInputKind,kinds:Array.from(node.options).map(item=>item.value)}))');
    assert.ok(ordinaryInputs.length && ordinaryInputs.every(item=>item.kinds.includes('run_artifact')));
    await capture('ordinary-current-managed-restore-1440',1440);
    await activate('#external-create-close');
    assert.equal(calls.length,0,'Ordinary inspection must not mutate or submit');
  }
  async function holdRecipeInspection(){
    await evaluate(`(()=>{const original=TuldokAuth.fetch;window.inspectionHeld=false;window.inspectionPolls=0;TuldokAuth.fetch=async(...args)=>{const response=await original(...args),url=String(args[0]);if(url==='/api/workspace/project-snapshots/${fixture.project_id}')window.inspectionPolls++;if(url.includes('/recipes/${fixture.recipe_id}?')&&!window.inspectionHeld){window.inspectionHeld=true;await new Promise(resolve=>window.releaseInspection=resolve);TuldokAuth.fetch=original;}return response;};})()`);
    await activate('[data-project-recipe="'+fixture.recipe_id+'"]');
    await until(()=>evaluate('window.inspectionHeld===true'),'Actual recipe inspection response was not held');
    await until(()=>evaluate('window.inspectionPolls>=2'),'Same-project activity polling did not cross held inspection');
  }
  if(fixture.activity_path&&fixture.mutable_recipe_path){
    await holdRecipeInspection();await select('#dataset','catalog');await evaluate('window.releaseInspection()');await pause(150);
    assert.equal(await evaluate('document.getElementById("extension-model-dialog").open'),false,'Changed project selection must fence held inspection');
    await select('#dataset','project:'+fixture.project_id);await activate('#nav-pipeline');await until(()=>evaluate(`!!document.querySelector('[data-project-recipe="${fixture.recipe_id}"]')`));
    const originalRecipe=fs.readFileSync(fixture.mutable_recipe_path);
    try{
      await holdRecipeInspection();fs.writeFileSync(fixture.mutable_recipe_path,Buffer.concat([originalRecipe,Buffer.from('\n')]));
      await until(()=>evaluate(`document.querySelector('[data-project-recipe="${fixture.recipe_id}"]')?.disabled===true&&document.querySelector('[data-project-reference="${fixture.recipe_id}"]').textContent.includes('mismatch')`),'Changed exact recipe hash was not observed');
      await evaluate('window.releaseInspection()');await pause(150);
      assert.equal(await evaluate('document.getElementById("extension-model-dialog").open'),false,'Changed recipe hash must fence held inspection');
    }finally{fs.writeFileSync(fixture.mutable_recipe_path,originalRecipe);}
    await until(()=>evaluate(`document.querySelector('[data-project-recipe="${fixture.recipe_id}"]')?.disabled===false`),'Restored fixture recipe did not become available');
    await holdRecipeInspection();await evaluate('window.releaseInspection()');
  }else await activate('[data-project-recipe="'+fixture.recipe_id+'"]');
  await until(()=>evaluate('!!document.getElementById("extension-prepare")'),'Bound recipe inspector did not enable native preparation');
  assert.equal(calls.length,0,'Opening and inspecting must not mutate records or execute');
  for(const [selector,value] of Object.entries(fixture.model_controls||{}))await fill(selector,value);
  for(const [selector,value] of Object.entries(fixture.trainer_controls||{}))await fill(selector,value);
  await fill('#extension-model-name',fixture.trial_name||'Native bound model browser trial');
  const choices=await evaluate('Array.from(document.querySelectorAll("[data-author-input]")).map(node=>({name:node.dataset.authorInput,values:Array.from(node.options).map(option=>option.value).filter(Boolean)}))');
  for(const choice of choices){const selected=fixture.inputs?.[choice.name]||(choice.values.length===1?choice.values[0]:null);assert.ok(selected,'Specify exact input choice for '+choice.name);await select('[data-author-input="'+choice.name+'"]',selected);}
  for(const [name,value] of Object.entries(fixture.budget_controls||{}))await fill('#extension-budget-'+name,value);
  await capture('native-configuration-1440',1440);await capture('native-configuration-390',390,844);
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});await activate('#extension-prepare');
  await until(()=>evaluate('!!document.getElementById("extension-reviewed")'),'Exact full-composition review did not become available');
  assert.ok(!calls.some(item=>/\/(approve|admit)$/.test(item.url)),'Preparation must not approve or admit');
  assert.match(await evaluate('document.getElementById("extension-model-dialog").textContent'),/Declared effects:.*Effective process permissions|Effective process permissions[\s\S]*trusted-local/);
  const journal=await evaluate('Object.values(history.state.extensionModelTrials).find(item=>item.trial&&!item.run)');assert.ok(journal&&journal.model&&journal.material&&journal.graph&&journal.study&&journal.trial&&journal.composition);
  const modelRequest=calls.find(item=>item.url.endsWith('/models')),preparedModel=modelRequest.body;assert.deepEqual(preparedModel.specification.configuration,journal.configuration);if(fixture.required_number_literal)assert.ok(modelRequest.wire.includes(fixture.required_number_literal),'Immutable inspected number spelling must survive browser transport');
  assert.deepEqual(calls.find(item=>item.url.endsWith('/graphs/external')).body.parameters,journal.parameters);
  for(const dark of [false,true]){await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:dark?'dark':'light'}]});for(const width of [1440,390]){await capture((dark?'dark-':'')+'exact-review-'+width,width,width===390?844:900);await focus('#extension-model-close');await key('Tab');const style=await evaluate('(()=>{const value=getComputedStyle(document.activeElement);return {id:document.activeElement.id,outline:value.outlineStyle,width:parseFloat(value.outlineWidth)};})()');assert.ok(style.outline!=='none'&&style.width>=2,JSON.stringify(style));}}
  if(process.argv.includes('--inspect-only')){
    await focus('#extension-reviewed');await key(' ','Space');
    assert.equal(await evaluate('document.getElementById("extension-approve").disabled'),false,'Exact managed trial approval must become enabled after review');
    assert.equal(await evaluate('Object.values(history.state.extensionModelTrials).find(item=>item.trial).study.open'),false);
    if(fixture.expected_runtime){
      assert.match(await evaluate('document.getElementById("extension-model-dialog").textContent'),new RegExp(fixture.expected_runtime));
      assert.match(await evaluate('document.getElementById("extension-model-dialog").textContent'),new RegExp(fixture.expected_runtime_snapshot));
    }
    assert.ok(!calls.some(item=>/\/(approve|admit)$/.test(item.url)));const after=await(await auth.fetch(base+'/api/workspace/runs')).json();assert.deepEqual(after.map(item=>item.id).sort(),before.map(item=>item.id).sort());assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
    fs.writeFileSync(path.join(report,'inspection-receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),source_sha256:hashes,command:'node tests/browser_extension_model_author.cjs --inspect-only',browser:(await send('Browser.getVersion')).product,source_receipt:fixturePath,catalog_path:data,native_numeric_transport:await evaluate('typeof JSON.rawJSON==="function"'),required_number_literal:fixture.required_number_literal||null,held_poll_and_selection_fences:!!fixture.mutable_recipe_path,ordinary_recipe_id:fixture.ordinary_recipe_id||null,approval_enabled:true,admission_open:journal.study.open,study_id:journal.study.id,trial_id:journal.trial.id,configuration:journal.configuration,trainer_parameters:journal.parameters,material_sha256:journal.trial.material.sha256,limits:journal.limits,requests:calls,captures,producer_execution:false,quality_claim:false,scope:'Actual HTTP/native immutable composition inspection and review only; approval/admission/producer/field acceptance pending'},null,2));
    console.log('PASS actual bound model preparation/review only:',report);return;
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});await focus('#extension-reviewed');await key(' ','Space');await activate('#extension-approve');await until(()=>evaluate('!!document.getElementById("extension-admit")'),'Exact trial approval not acknowledged');assert.ok(!calls.some(item=>item.url.endsWith('/admit')));
  await activate('#extension-admit');await until(()=>evaluate('Object.values(history.state.extensionModelTrials||{}).some(item=>item.run?.id)'),'Study admission not acknowledged');
  const admitted=await evaluate('Object.values(history.state.extensionModelTrials).find(item=>item.run?.id)'),sourceRun=admitted.run.id;
  await until(()=>evaluate('document.getElementById("real-run-state")?.textContent==="completed"'),'Actual admitted Run did not complete');await until(()=>evaluate('!!document.getElementById("field-prediction")'),'Admitted Run did not expose native retained fields');
  const run=await(await auth.fetch(base+'/api/workspace/runs/'+sourceRun)).json();assert.equal(run.state,'completed');assert.equal(run.study_membership.study_id,admitted.study.id);assert.equal(run.study_membership.trial_id,admitted.trial.id);
  const study=await(await auth.fetch(base+'/api/workspace/studies/'+admitted.study.id,{headers:{'Tuldok-Operation-Contract':'studies.get/1/'+await evaluate('WorkspaceExtensionAuthorContracts["studies.get"]')}})).json();assert.equal(study.charged.attempt_slots,1);assert.equal(study.reservations.filter(item=>item.run_id===sourceRun).length,1);
  const after=await(await auth.fetch(base+'/api/workspace/runs')).json();assert.equal(after.length,before.length+1);assert.equal(calls.filter(item=>item.url.endsWith('/admit')).length,1);assert.ok(!calls.some(item=>item.url.includes('/runs/submit-external')));
  await capture('automatic-native-fields-1440',1440);await capture('automatic-native-fields-390',390,844);assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  const fieldReceipt=path.join(report,'field-source.json');fs.writeFileSync(fieldReceipt,JSON.stringify({catalog_path:data,run_id:sourceRun,project_roots:fixture.project_roots,...(fixture.expected_fields?{expected_fields:fixture.expected_fields}:{})},null,2));
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),source_sha256:hashes,command:'node tests/browser_extension_model_author.cjs',browser:(await send('Browser.getVersion')).product,source_receipt:fixturePath,catalog_path:data,run_id:sourceRun,study_id:admitted.study.id,trial_id:admitted.trial.id,configuration:admitted.configuration,trainer_parameters:admitted.parameters,material_sha256:admitted.trial.material.sha256,limits:admitted.limits,charged:study.charged,requests:calls,captures,field_source_receipt:fieldReceipt,expected_fields:fixture.expected_fields||null,producer_execution:true,quality_claim:false,checks:['inspect does not execute','native typed Model configuration separated from trainer controls','exact composition/provider/ambient-permission review','separate owner approval','explicit finite Study admission charged once','automatic native retained field evidence','1440/390 light/dark bounded review and visible keyboard focus']},null,2));
  console.log('PASS actual native bound model browser:',report);console.log('Run read-only H3/H6 gate with TULDOK_FIELD_BROWSER_RECEIPT='+fieldReceipt+' node tests/browser_field_evidence.cjs');
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}process.exitCode=1;}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');});
