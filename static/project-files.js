'use strict';
// One page owns this projection. The server owns project state and every edit.
(()=>{
  const $=id=>document.getElementById(id), base='/api/workspace/project-files';
  const actions=['new','open','save','close','query','get','import_text','annotate'];
  const tasks=['text_classification','text_entities','text_corpus'];
  // Generated from agent_api; freshness is checked by the client contract tests.
  const pins = /* PROJECT_FILES_CONTRACTS_START */ {
  "project_files.status": "1d0c4b64caaab8369d4addefd72e53cc8c7d0be4c07729fa04b358febe643b6a",
  "project_files.new": "672373f8ddc0b89fea15165798aab97cf4ac2cdf678a04d96839512cc8976b6f",
  "project_files.open": "fd4b9f97c03cd7050981cfafd1177bff8c86351bb603b8f7980aaa149d2b0368",
  "project_files.save": "38572e376db36f81582dc6419fded35ff9d7c9185f5af2cdaafd74c94790f90a",
  "project_files.close": "95d0099ec2a378a1bbb65676799dd3baae2f36b838301f7aa165b116fba5edf6",
  "project_files.query": "9a8b0d3a99adf5d7d53b62261dfac83e8b3ea44c10cb2f6c7a9c3d79422fef08",
  "project_files.get": "6b0f4e16a00aa119b86cbb5493be0bac945ff08a5e63773a8f2c2f9296658d5b",
  "project_files.import_text": "0f168320abb858892a2724b0b59862475bec653d1670ce754d61f2d82c912538",
  "project_files.annotate": "70feae2ad14c49c4ae95b5bb69b4a50fbf93191cde840544cf89b6cbe8dc5c58"
} /* PROJECT_FILES_CONTRACTS_END */;
  let selectedContracts=new Set();
  let state=null, selected=null, history=[], summaries=[], nextRecord=null, nextHistory=null, epoch=0, busy=false, blocked=false;
  let importDirty=false, annotationDirty=false, pending=null;
  const dirty=()=>importDirty||annotationDirty;
  const checkpoint=()=>state?.project?.checkpoint??null;
  const exact=(value,keys)=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
  const str=(value,max,empty=false)=>typeof value==='string'&&Array.from(value).length<=max&&(empty||/\S/u.test(value));
  const id=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
  const sha=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  const texts=(value,max,min=0,length=120)=>Array.isArray(value)&&value.length>=min&&value.length<=max&&new Set(value).size===value.length&&value.every(item=>str(item,length));
  const positive=value=>Number.isSafeInteger(value)&&value>0;
  function annotationOK(task,value,nullable=false){
    if(value===null)return nullable;
    if(task==='text_classification')return exact(value,['label'])&&str(value.label,80);
    if(task==='text_corpus')return exact(value,['note'])&&str(value.note,4000);
    return exact(value,['spans'])&&Array.isArray(value.spans)&&value.spans.length<=500&&value.spans.every(span=>exact(span,['label','start','end'])&&str(span.label,80)&&Number.isSafeInteger(span.start)&&span.start>=0&&positive(span.end)&&span.end>span.start);
  }
  function recordOK(value){
    const fields=['id','kind','name','text','groups','parents','provenance','task','annotation','review','revision','source_revision','created_at','updated_at'];
    return exact(value,fields)&&id(value.id)&&value.kind==='text'&&str(value.name,200)&&str(value.text,200000)&&texts(value.groups,30,1)&&texts(value.parents,30)&&exact(value.provenance,['method','rights','normalization'])&&value.provenance.method==='import'&&str(value.provenance.rights,1000)&&value.provenance.normalization==='NFC; LF newlines'&&tasks.includes(value.task)&&annotationOK(value.task,value.annotation,true)&&['draft','human_reviewed'].includes(value.review)&&positive(value.revision)&&value.source_revision===1&&str(value.created_at,80)&&str(value.updated_at,80);
  }
  function projectOK(value){return exact(value,['project_id','name','checkpoint'])&&id(value.project_id)&&str(value.name,200)&&sha(value.checkpoint);}
  function summaryOK(value){
    return exact(value,['id','kind','name','task','review','revision','source_revision','created_at','updated_at'])&&id(value.id)&&value.kind==='text'&&str(value.name,200)&&tasks.includes(value.task)&&['draft','human_reviewed'].includes(value.review)&&positive(value.revision)&&value.source_revision===1&&str(value.created_at,80)&&str(value.updated_at,80);
  }
  function receiptOK(value){
    const fields=['committed','selected','project_id','checkpoint','request_key'];
    return exact(value,value?.selected===false?[...fields,'root','directory']:fields)&&value.committed===true&&typeof value.selected==='boolean'&&id(value.project_id)&&sha(value.checkpoint)&&typeof value.request_key==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(value.request_key)&&(value.selected||(str(value.root,160)&&str(value.directory,512)));
  }
  function stateOK(value){
    const fields=['format','binding','state','roots','project','available_actions'];
    if(!exact(value,value?.state==='recovery_required'?[...fields,'recovery']:fields)||value.format!=='project_files_state_v1'||!id(value.binding)||!texts(value.roots,100,0,160)||!Array.isArray(value.available_actions)||value.available_actions.length>8||new Set(value.available_actions).size!==value.available_actions.length||!value.available_actions.every(action=>actions.includes(action)))return false;
    if(value.state==='no_project_open')return value.project===null;
    if(!projectOK(value.project))return false;
    if(value.state==='open')return true;
    const recovery=value.recovery;
    return value.state==='recovery_required'&&exact(recovery,['action','root','directory','reason','request_key'])&&recovery.action==='open'&&str(recovery.root,160)&&str(recovery.directory,512)&&['unknown_publication','projection_unavailable'].includes(recovery.reason)&&(recovery.request_key===null||typeof recovery.request_key==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(recovery.request_key))&&value.available_actions.length===1&&value.available_actions[0]==='open';
  }
  function boundOK(value,kind){
    const fields=kind==='query'?['binding','project_id','checkpoint','items','next_after_id']:['binding','project_id','checkpoint','record','history','next_history_before_revision'];
    if(!exact(value,fields)||!id(value.binding)||!id(value.project_id)||!sha(value.checkpoint))return false;
    if(kind==='query')return Array.isArray(value.items)&&value.items.length<=100&&value.items.every(summaryOK)&&(value.next_after_id===null||id(value.next_after_id)&&value.items.at(-1)?.id===value.next_after_id)&&value.items.every((item,index)=>index===0||item.id>value.items[index-1].id);
    return recordOK(value.record)&&Array.isArray(value.history)&&value.history.length<=4&&value.history.every(recordOK)&&value.history.every((item,index)=>item.id===value.record.id&&item.revision<=value.record.revision&&(index===0||item.revision<value.history[index-1].revision))&&(value.next_history_before_revision===null||positive(value.next_history_before_revision)&&value.history.at(-1)?.revision===value.next_history_before_revision);
  }
  function message(value){$('project-files-status').textContent=value;}
  function error(value){
    const node=$('project-files-error');node.textContent=value;node.hidden=false;node.focus();
  }
  function clearError(){$('project-files-error').hidden=true;$('project-files-error').textContent='';}
  function controls(){
    const open=state?.state==='open', allowed=action=>!busy&&!blocked&&selectedContracts.has('project_files.'+action)&&state?.available_actions.includes(action);
    for(const action of ['new','open','save','close'])$('project-files-'+action).disabled=!allowed(action);
    $('project-files-refresh').disabled=busy;
    $('project-files-root').disabled=busy||state?.state==='recovery_required';
    $('project-files-directory').disabled=busy||state?.state==='recovery_required';
    $('project-files-name').disabled=busy||state?.state==='recovery_required';
    $('text-import-fields').disabled=!open||!allowed('import_text');
    $('annotation-fields').disabled=!selected||!allowed('annotate');
    $('import-text').disabled=!allowed('import_text');
    $('annotation-save').disabled=!selected||!allowed('annotate');
    $('project-files-discard').disabled=busy||!dirty();
    $('records-more').hidden=nextRecord===null;$('records-more').disabled=!allowed('query');
    $('record-history-more').hidden=nextHistory===null;$('record-history-more').disabled=!selected||!allowed('get');
    $('project-files-open').textContent=state?.state==='recovery_required'?'Reopen to reconcile':'Open project';
    for(const button of $('records-list').querySelectorAll('button'))button.disabled=busy||blocked;
    $('project-files-dirty').textContent=dirty()?'This tab has unsent or unacknowledged edits. After an error, inspect saved state before retrying; explicitly discard these edits before closing. Unsent annotations must be resolved before selecting a different record.':'No unsubmitted edits.';
    if(window.TuldokAuth&&!window.TuldokAuth.canReview())$('record-review').value='draft';
  }
  function showState(){
    const root=$('project-files-root'), previous=root.value;root.replaceChildren();
    for(const alias of state.roots){const option=document.createElement('option');option.value=alias;option.textContent=alias;root.append(option);}
    if(state.roots.includes(previous))root.value=previous;
    const recovery=state.state==='recovery_required';
    $('project-files-summary').textContent=state.project?`${state.project.name} · ${state.project.project_id} · ${recovery?'last acknowledged':'saved'} checkpoint ${state.project.checkpoint}${recovery?' · Reopen this project to reconcile its saved state.':''}`:'No project open.';
    if(recovery){root.value=state.recovery.root;$('project-files-directory').value=state.recovery.directory;}
    controls();
  }
  function annotationHelp(){
    const task=$('annotation-task').value;
    $('annotation-label').textContent=task==='text_classification'?'Class label':task==='text_corpus'?'Corpus note':'Entity spans (JSON)';
    $('annotation-help').textContent=task==='text_classification'?'Enter one classification label, up to 80 characters.':task==='text_corpus'?'Enter a human-authored corpus note, up to 4,000 characters.':'Enter {"spans":[{"label":"person","start":0,"end":4}]}. Offsets count Unicode code points; an empty spans array records a negative.';
    $('annotation-value').maxLength=task==='text_classification'?80:task==='text_corpus'?4000:200000;
  }
  function showRecord(focus=false){
    $('record-heading').textContent=selected?selected.name:'Select a text record';
    $('record-summary').textContent=selected?`Revision ${selected.revision} · ${selected.review} · source revision ${selected.source_revision}`:'';
    $('record-text').value=selected?.text??'';
    $('annotation-task').value=selected?.task??'text_classification';
    const value=selected?.annotation;
    $('annotation-value').value=value?(selected.task==='text_entities'?JSON.stringify(value,null,2):value.label??value.note):'';
    $('annotation-groups').value=selected?.groups.join(', ')??'';
    $('record-review').value=selected?.review??'draft';
    annotationHelp();
    showHistory();controls();if(focus)$('record-heading').focus();
  }
  function showHistory(){
    const list=$('record-history');list.replaceChildren();
    for(const snapshot of history){const item=document.createElement('li'),title=document.createElement('p'),body=document.createElement('pre');title.textContent=`Revision ${snapshot.revision} · ${snapshot.review} · ${snapshot.task}`;body.textContent=JSON.stringify(snapshot.annotation,null,2);item.append(title,body);list.append(item);}
    controls();
  }
  function showRecords(items){
    const list=$('records-list');list.replaceChildren();
    if(!items.length){const item=document.createElement('li');item.textContent='No text records yet.';list.append(item);}
    for(const record of items){const item=document.createElement('li'),button=document.createElement('button');button.type='button';button.dataset.recordId=record.id;button.textContent=`${record.name} · ${record.review} · revision ${record.revision}`;button.setAttribute('aria-current',String(record.id===selected?.id));button.onclick=()=>select(record.id);item.append(button);list.append(item);}
    controls();
  }
  function needClean(){if(!dirty())return true;error('This tab has unsent or unacknowledged edits. Inspect saved state after an error, then submit or choose “Discard unsubmitted edits” before this action.');return false;}
  async function discover(ticket){
    let response,value;
    try{response=await window.TuldokAuth.fetch('/api/agent/capabilities',{cache:'no-store'});value=await response.json();}
    catch(_){const failure=Error('Project contracts unavailable. Refresh status before continuing.');failure.code='transport';throw failure;}
    if(ticket!==epoch)return false;
    if(!response.ok){const failure=Error(value?.error??'Project contracts unavailable. Sign in and refresh status.');failure.status=response.status;throw failure;}
    if(!exact(value,['format','envelope_version','catalog_id','operations','limits'])||value.format!=='agent_capabilities_v1'||value.envelope_version!==1||!id(value.catalog_id)||!Array.isArray(value.operations)||value.operations.length>256||JSON.stringify(value).length>1048576||!exact(value.limits,['request_bytes','response_bytes','max_operations'])||value.limits.request_bytes!==1048576||value.limits.response_bytes!==16777216||value.limits.max_operations!==256)throw Error('Unsupported project capability envelope.');
    const identity=window.TuldokAuth.identity?.();
    if(identity?.catalog_id&&identity.catalog_id!==value.catalog_id)throw Error('Project capability catalog differs from the current session.');
    const names=new Set(),chosen=new Set();
    for(const operation of value.operations){
      if(!exact(operation,['id','contracts','availability'])||typeof operation.id!=='string'||!/^[a-z][a-z0-9_.]{0,79}$/.test(operation.id)||names.has(operation.id)||!['available','unavailable','unsupported'].includes(operation.availability)||!Array.isArray(operation.contracts)||!operation.contracts.length||operation.contracts.length>4)throw Error('Unsupported operation capability.');
      names.add(operation.id);const versions=new Set();
      for(const contract of operation.contracts){
        if(!exact(contract,['version','sha256','input_schema','output_schema','scopes','authority','effects','retry','bounds'])||!positive(contract.version)||versions.has(contract.version)||!sha(contract.sha256)||!contract.input_schema||typeof contract.input_schema!=='object'||Array.isArray(contract.input_schema)||!contract.output_schema||typeof contract.output_schema!=='object'||Array.isArray(contract.output_schema)||!texts(contract.scopes,16,0,40)||!['agent','owner'].includes(contract.authority)||!['read','mutation'].includes(contract.effects)||!['read','cas','receipt','never'].includes(contract.retry)||!exact(contract.bounds,['request_bytes','response_bytes','inline_decoded_bytes','json_depth'])||!Object.values(contract.bounds).every(positive))throw Error('Unsupported operation contract.');
        versions.add(contract.version);
        // Remote schemas are opaque discovery data; only installed local pins
        // select behavior. Every request lets the owner verify this exact pin.
        if(operation.availability==='available'&&contract.version===1&&Object.hasOwn(pins,operation.id)&&contract.sha256===pins[operation.id])chosen.add(operation.id);
      }
    }
    selectedContracts=chosen;
    if(!chosen.has('project_files.status')){const failure=Error('No compatible project status contract is available.');failure.code='contract_mismatch';throw failure;}
    return true;
  }
  async function request(path,{body,kind='state',ticket=epoch,read=false,recordId}={}){
    const binding=state?.binding, expected=checkpoint(), project=state?.project?.project_id;
    const action=path===''?'status':path.startsWith('/records?')?'query':path.startsWith('/records/')?(body===undefined?'get':'annotate'):path.slice(1).replaceAll('-','_');
    const operation='project_files.'+action;
    if(!selectedContracts.has(operation)){const failure=Error('No compatible contract is available for '+action+'. Refresh project status.');failure.code='contract_mismatch';throw failure;}
    let response,value;
    try{
      response=await window.TuldokAuth.fetch(base+path,{method:body===undefined?'GET':'POST',headers:{'Tuldok-Operation-Contract':operation+'/1/'+pins[operation],...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
      value=await response.json();
    }catch(_){const failure=Error(body===undefined?'Project response unavailable. Refresh status to recover.':'Acknowledgement unavailable; the edit may already be saved. Keep your edits and refresh status before retrying.');failure.code='transport';throw failure;}
    if(ticket!==epoch){message('A superseded project response was ignored. The current view is unchanged.');return null;}
    if(!response.ok){const fields=['error',...(Object.hasOwn(value??{},'code')?['code']:[]),...(Object.hasOwn(value??{},'receipt')?['receipt']:[])];const valid=exact(value,fields)&&str(value.error,1000)&&(!Object.hasOwn(value,'code')||str(value.code,120))&&(!Object.hasOwn(value,'receipt')||receiptOK(value.receipt));const failure=Error(valid?`${value.code??'error'}: ${value.error}`:'Invalid project error response. Refresh status.');failure.code=valid?(value.code??'http_error'):'transport';failure.status=response.status;if(valid&&value.receipt)failure.receipt=value.receipt;throw failure;}
    if(!(kind==='state'?stateOK(value):boundOK(value,kind))){const failure=Error('Unsupported project response. The current state is unknown; refresh status before continuing.');failure.code='transport';throw failure;}
    if(kind!=='state'&&(value.binding!==binding||value.project_id!==project||(read&&value.checkpoint!==expected)||(recordId&&value.record?.id!==recordId))){const failure=Error('stale: Response belongs to a different project or checkpoint. Your unsubmitted edits remain here. Refresh status.');failure.code='stale';throw failure;}
    return value;
  }
  async function run(work,{clean=false}={}){
    if(busy)return;if(clean&&!needClean())return;
    const ticket=++epoch;busy=true;clearError();controls();
    let nextFocus=null;
    try{nextFocus=await work(ticket);}catch(failure){
      if(ticket===epoch){
        if(failure.status===409||failure.status>=500||['stale','conflict','binding_mismatch','transport','projection_unavailable','stale_binding','stale_checkpoint','too_large'].includes(failure.code))blocked=true;
        if(failure.receipt){const receipt=failure.receipt;$('project-files-receipt').hidden=false;$('project-files-receipt').textContent=`Saved to project ${receipt.project_id} at checkpoint ${receipt.checkpoint}; request ${receipt.request_key}. ${receipt.selected?'Refresh status and reopen to restore the local view.':'The project was created but is not selected. Refresh status, then Open its directory.'}`;if(!receipt.selected){$('project-files-root').value=receipt.root;$('project-files-directory').value=receipt.directory;}}
        error(failure.message);
      }
    }finally{if(ticket===epoch){busy=false;controls();if(nextFocus)nextFocus.focus();}}
  }
  async function query(ticket,append=false){
    if(state?.state!=='open'){summaries=[];nextRecord=null;showRecords([]);return;}
    const cursor=append?nextRecord:null,parameters={binding:state.binding,checkpoint:checkpoint()};
    if(cursor!==null)parameters.after_id=cursor;
    const result=await request('/records?'+new URLSearchParams(parameters),{kind:'query',ticket,read:true});
    if(result){if(cursor!==null&&result.items.some(item=>item.id<=cursor))throw Error('Invalid record-page continuation. Refresh status.');summaries=append?[...summaries,...result.items]:result.items;nextRecord=result.next_after_id;showRecords(summaries);}
  }
  function olderHistory(){return run(async ticket=>{
    if(!selected||nextHistory===null)return;
    const before=nextHistory;
    const result=await request('/records/'+selected.id+'?'+new URLSearchParams({binding:state.binding,checkpoint:checkpoint(),before_revision:before}),{kind:'record',ticket,read:true,recordId:selected.id});
    if(!result)return;
    if(result.record.revision!==selected.revision||result.history.some(item=>item.revision>=before))throw Error('Invalid history-page continuation. Refresh status.');
    history=[...history,...result.history];nextHistory=result.next_history_before_revision;showHistory();message('Older saved annotation history loaded.');return nextHistory===null?$('record-history-title'):$('record-history-more');
  });}
  function refresh(){return run(async ticket=>{
    if(!await discover(ticket))return;
    const value=await request('',{ticket});if(!value)return;
    const changed=state?.binding!==value.binding||checkpoint()!==value.project?.checkpoint;
    state=value;blocked=false;
    if(changed){selected=null;history=[];nextHistory=null;if(!annotationDirty)showRecord();else{$('record-heading').textContent='Unsubmitted annotation from a prior checkpoint';$('record-summary').textContent='Project changed. Your unsubmitted annotation remains below; discard it before selecting a saved record.';$('record-text').value='';}}
    showState();await query(ticket);message(dirty()?'Project status refreshed. Unsubmitted edits remain in this tab.':'Project status refreshed.');
  });}
  function select(recordId){if(annotationDirty){error('The annotation editor has unsent or unacknowledged edits. Submit or explicitly discard that annotation before selecting a saved record.');return;}return run(async ticket=>{
    const result=await request('/records/'+recordId+'?'+new URLSearchParams({binding:state.binding,checkpoint:checkpoint()}),{kind:'record',ticket,read:true,recordId});
    if(!result)return;selected=result.record;history=result.history;nextHistory=result.next_history_before_revision;annotationDirty=false;showRecord(true);await query(ticket);message('Saved text and annotation history loaded.');
  });}
  function key(){return crypto.randomUUID().replaceAll('-','');}
  function mutationBody(path,fields){
    const body={binding:state.binding,expected_checkpoint:checkpoint(),...fields};
    const signature=JSON.stringify({path,body});
    if(!pending||pending.signature!==signature)pending={signature,key:key()};
    return {...body,request_key:pending.key};
  }
  function lifecycle(action){const recovering=action==='open'&&state?.state==='recovery_required';return run(async ticket=>{
    const fields={};
    if(['new','open'].includes(action)){
      if(!$('project-files-root').value||!$('project-files-directory').value.trim())throw Error('Choose a local root and relative project directory.');
      fields.root=$('project-files-root').value;fields.directory=$('project-files-directory').value;
      if(action==='new'){if(!$('project-files-name').value.trim())throw Error('Enter a name for the new project.');fields.name=$('project-files-name').value;}
    }
    const value=await request('/'+action,{ticket,body:mutationBody('/'+action,fields)});if(!value)return;
    state=value;pending=null;if(action!=='save'){selected=null;history=[];nextHistory=null;}showState();if(action!=='save'&&!annotationDirty)showRecord();else if(recovering&&annotationDirty){$('record-heading').textContent='Preserved unsubmitted annotation';$('record-text').value='';}await query(ticket);message(action==='save'?'Project checkpoint is saved.':action==='close'?'Project closed.':`Project ${action==='new'?'created':'opened'}.`);
    return action==='save'?$('project-files-save'):(state.state==='open'?$('text-name'):$('project-files-directory'));
  },{clean:!recovering});}
  function groups(value){const result=value.split(',').map(item=>item.trim()).filter(Boolean);if(!texts(result,30,1))throw Error('Supply 1–30 distinct protected group IDs, each up to 120 characters.');return result;}
  async function acceptRecord(value,ticket){
    state={...state,project:{...state.project,checkpoint:value.checkpoint}};selected=value.record;history=value.history;nextHistory=value.next_history_before_revision;pending=null;annotationDirty=false;showState();showRecord(true);await query(ticket);
  }
  $('text-import-form').onsubmit=event=>{
    event.preventDefault();if(annotationDirty){error('Submit or discard the current annotation before creating another text record.');return;}
    run(async ticket=>{
      const asset={name:$('text-name').value,text:$('text-content').value,groups:groups($('text-groups').value),rights:$('text-rights').value};
      if(!str(asset.name,200)||!str(asset.text,200000)||!str(asset.rights,1000))throw Error('Enter a name, text and rights note within the displayed limits.');
      const value=await request('/import-text',{kind:'record',ticket,body:mutationBody('/import-text',{asset})});if(!value)return;
      importDirty=false;$('text-name').value='';$('text-content').value='';await acceptRecord(value,ticket);message('Text submitted and saved to the project.');
    });
  };
  $('annotation-form').onsubmit=event=>{
    event.preventDefault();run(async ticket=>{
      if(!selected)throw Error('Select a saved text record first.');
      const task=$('annotation-task').value,raw=$('annotation-value').value;
      let annotation;if(task==='text_entities'){try{annotation=JSON.parse(raw);}catch(_){throw Error('Entity spans must be valid JSON.');}}else annotation=task==='text_corpus'?{note:raw}:{label:raw};
      if(!annotationOK(task,annotation))throw Error('The annotation does not match this task. Follow the instructions above the editor.');
      const body={revision:selected.revision,source_revision:selected.source_revision,task,annotation,groups:groups($('annotation-groups').value),review:$('record-review').value};
      const value=await request('/records/'+selected.id,{kind:'record',ticket,recordId:selected.id,body:mutationBody('/records/'+selected.id,{annotation:body})});if(!value)return;
      await acceptRecord(value,ticket);message('Annotation submitted and saved to the project.');
    });
  };
  for(const action of ['new','open','save','close'])$('project-files-'+action).onclick=()=>lifecycle(action);
  $('project-files-refresh').onclick=refresh;
  $('records-more').onclick=()=>run(async ticket=>{await query(ticket,true);message('More text records loaded.');return nextRecord===null?$('records-title'):$('records-more');});
  $('record-history-more').onclick=olderHistory;
  $('project-files-discard').onclick=()=>{importDirty=false;annotationDirty=false;$('text-name').value='';$('text-content').value='';$('text-groups').value='project';$('text-rights').value='unknown';showRecord();clearError();message('Unsubmitted edits discarded. Saved project records are unchanged.');};
  for(const field of ['text-name','text-content','text-groups','text-rights'])$(field).addEventListener('input',()=>{importDirty=true;controls();});
  for(const field of ['annotation-value','annotation-groups','record-review','annotation-task'])$(field).addEventListener(field==='annotation-task'||field==='record-review'?'change':'input',()=>{annotationDirty=true;annotationHelp();controls();});
  window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
  window.addEventListener('tuldok-session',()=>{++epoch;busy=false;blocked=true;selectedContracts=new Set();controls();message('Session changed. Refreshing project status; your unsubmitted edits remain here.');refresh();});
  controls();refresh();
})();
