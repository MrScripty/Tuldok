'use strict';
// Five installed controller operations; discovery never executes remote schemas.
(()=>{
  const families={records:'Data records',responses:'Responses',preferences:'Comparative judgments',selections:'Saved selections',searches:'Saved searches',graphs:'Pipeline graphs',recipe_drafts:'Recipe definitions',model_definitions:'Model definitions',studies:'Studies',runs:'Historical Runs',releases:'Frozen releases',exposures:'Exposure facts',model_materials:'Model materials',recipe_materials:'Recipe materials',runtime_materials:'Runtime materials'};
  const canonicalFamilies=['workbench_record','workbench_response','workbench_preference','saved_selection','saved_search','pipeline_graph','recipe_definition','model_definition','study_history','trial_history','run_history','candidate_history','dataset_release','dataset_exposure','model_material','recipe_material','runtime_material','project_snapshot','project_artifact','project_file','generation_history','grounded_history','caption_proposal_history','text_proposal_history'];
  const shaRoots=new Set(['releases','model_materials','recipe_materials','runtime_materials']),producerKinds=['generation','grounded','caption','text_proposal'];
  const sections=['included','required','unassigned','excluded','blockers','warnings','artifacts','working_files'];
  const actions=['status','preview','report_page','stop','extract'];
  const exact=(v,keys)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
  const text=(v,max,empty=false)=>typeof v==='string'&&Array.from(v).length<=max&&(empty||/\S/u.test(v));
  const id=v=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v),sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
  const integer=(v,max=1000000)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
  const clone=v=>JSON.parse(JSON.stringify(v));
  function protocol(message){const failure=Error(message);failure.code='invalid_response';return failure;}
  const leaf=v=>text(v,200)&&!/[\/\\\x00-\x1f]/.test(v)&&!['.','..'].includes(v);
  const working=v=>exact(v,['kind','path'])&&['script','note'].includes(v.kind)&&text(v.path,512)&&v.path.startsWith(v.kind==='script'?'scripts/':'notes/')&&!/[\\\x00-\x1f]/.test(v.path)&&v.path.split('/').length<=16&&v.path.split('/').every(p=>p&&!['.','..'].includes(p));
  function normalizeSelection(value){
    if(!exact(value,['project_snapshot','roots','decisions'])||!exact(value.project_snapshot,['id','manifest_sha256'])||!id(value.project_snapshot.id)||!sha(value.project_snapshot.manifest_sha256))throw Error('Choose the exact registered project ID and manifest SHA256.');
    if(!value.roots||typeof value.roots!=='object'||Array.isArray(value.roots)||Object.keys(value.roots).some(k=>!Object.hasOwn(families,k)&&!['producer_jobs','working_files'].includes(k)))throw Error('The selection contains an unknown source family.');
    const roots={};
    for(const family of Object.keys(families)){
      const list=value.roots[family]??[];
      if(!Array.isArray(list)||list.length>10000||new Set(list).size!==list.length||!list.every(shaRoots.has(family)?sha:id))throw Error('Use unique exact '+(shaRoots.has(family)?'SHA256 digests':'IDs')+' for '+families[family]+'.');
      roots[family]=[...list].sort();
    }
    const jobs=value.roots.producer_jobs??[],files=value.roots.working_files??[];
    if(!Array.isArray(jobs)||jobs.length>10000||!jobs.every(j=>exact(j,['kind','id'])&&producerKinds.includes(j.kind)&&id(j.id))||new Set(jobs.map(j=>j.kind+':'+j.id)).size!==jobs.length)throw Error('Choose known producer kinds and unique job IDs.');
    if(!Array.isArray(files)||files.length>1000||!files.every(working)||new Set(files.map(f=>f.kind+':'+f.path)).size!==files.length)throw Error('Working files must be unique scripts/... or notes/... paths within the selected project.');
    roots.producer_jobs=clone(jobs).sort((a,b)=>(a.kind+':'+a.id).localeCompare(b.kind+':'+b.id));
    roots.working_files=clone(files).sort((a,b)=>(a.kind+':'+a.path).localeCompare(b.kind+':'+b.path));
    if(!Array.isArray(value.decisions)||value.decisions.length>10000||!value.decisions.every(d=>exact(d,['family','id','include','reason'])&&canonicalFamilies.includes(d.family)&&text(d.id,128)&&typeof d.include==='boolean'&&text(d.reason,1000))||new Set(value.decisions.map(d=>d.family+':'+d.id)).size!==value.decisions.length)throw Error('Each ownership decision needs a known family, exact report ID and reason.');
    const result={project_snapshot:clone(value.project_snapshot),roots,decisions:clone(value.decisions).sort((a,b)=>(a.family+':'+a.id).localeCompare(b.family+':'+b.id))};
    if(new TextEncoder().encode(JSON.stringify(result)).length>1048576)throw Error('The selection exceeds one MiB.');
    return result;
  }
  const sourceOK=v=>exact(v,['catalog_id','schema_version','catalog_signature','snapshot_sha256','backup_receipt_sha256','external_inventory_sha256'])&&id(v.catalog_id)&&v.schema_version===10&&sha(v.catalog_signature)&&sha(v.snapshot_sha256)&&(v.backup_receipt_sha256===null||sha(v.backup_receipt_sha256))&&sha(v.external_inventory_sha256);
  const failureOK=v=>v===null||(v&&typeof v==='object'&&Object.keys(v).every(k=>['action','code','detail','staging_directory'].includes(k))&&['stop','extract'].includes(v.action)&&text(v.code,120)&&text(v.detail,1000,true)&&(v.staging_directory===undefined||leaf(v.staging_directory)));
  function receiptOK(v){
    if(v===null)return true;
    if(exact(v,['format','committed','project_id','checkpoint','request_key','input_sha256','report_sha256','source','artifacts','verification','replayed']))return v.format==='project_transfer_receipt_v1'&&v.committed===true&&id(v.project_id)&&sha(v.checkpoint)&&text(v.request_key,128)&&sha(v.input_sha256)&&sha(v.report_sha256)&&sourceOK(v.source)&&v.source.backup_receipt_sha256!==null&&exact(v.artifacts,['copied_count','missing_regenerable_count'])&&integer(v.artifacts.copied_count)&&integer(v.artifacts.missing_regenerable_count)&&exact(v.verification,['checkpoint','active_data_records'])&&v.verification.checkpoint===v.checkpoint&&integer(v.verification.active_data_records)&&typeof v.replayed==='boolean';
    return v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).every(k=>['committed','selected','project_id','checkpoint','request_key','directory'].includes(k))&&v.committed===true&&typeof v.selected==='boolean'&&id(v.project_id)&&sha(v.checkpoint)&&text(v.request_key,128)&&(v.directory===undefined||leaf(v.directory));
  }
  function stateOK(v){
    if(!exact(v,['format','binding','phase','source_catalog_id','control_catalog_id','roots','available_actions','report','backup','destination','failure','last_receipt'])||v.format!=='project_transfer_state_v1'||!id(v.binding)||!['source_live','source_stopped','source_fenced'].includes(v.phase)||!id(v.source_catalog_id)||!id(v.control_catalog_id)||v.source_catalog_id===v.control_catalog_id||!Array.isArray(v.roots)||!v.roots.length||v.roots.length>100||!v.roots.every(r=>typeof r==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(r))||new Set(v.roots).size!==v.roots.length||!Array.isArray(v.available_actions)||!v.available_actions.includes('status')||!v.available_actions.every(a=>actions.includes(a))||new Set(v.available_actions).size!==v.available_actions.length||!failureOK(v.failure)||!receiptOK(v.last_receipt))return false;
    if(v.report!==null&&(!exact(v.report,['report_sha256','selection_sha256','source','can_extract','counts'])||!sha(v.report.report_sha256)||!sha(v.report.selection_sha256)||!sourceOK(v.report.source)||v.report.source.catalog_id!==v.source_catalog_id||typeof v.report.can_extract!=='boolean'||!exact(v.report.counts,sections)||!Object.values(v.report.counts).every(n=>integer(n))))return false;
    if(v.backup!==null&&(!exact(v.backup,['root','directory','receipt_sha256'])||!v.roots.includes(v.backup.root)||!leaf(v.backup.directory)||!sha(v.backup.receipt_sha256)))return false;
    if(v.destination!==null&&(!exact(v.destination,['root','directory'])||!v.roots.includes(v.destination.root)||!leaf(v.destination.directory)))return false;
    return v.phase!=='source_fenced'||v.available_actions.every(a=>a==='status');
  }
  function itemOK(section,v){
    if(['included','unassigned'].includes(section))return exact(v,['family','id','revision'])&&text(v.family,64)&&text(v.id,128)&&(v.revision===null||integer(v.revision)&&v.revision>0);
    if(['required','excluded'].includes(section))return exact(v,['family','id'])&&text(v.family,64)&&text(v.id,128);
    if(['blockers','warnings'].includes(section))return exact(v,['family','id','code','detail'])&&text(v.family,64)&&text(v.id,128)&&text(v.code,120)&&text(v.detail,1000,true);
    if(section==='artifacts')return exact(v,['sha256','bytes','preservation','state'])&&sha(v.sha256)&&integer(v.bytes,Number.MAX_SAFE_INTEGER)&&['unique','regenerable'].includes(v.preservation)&&['verified','missing','corrupt','unverified'].includes(v.state);
    return section==='working_files'&&exact(v,['kind','path','sha256','bytes'])&&working({kind:v.kind,path:v.path})&&sha(v.sha256)&&integer(v.bytes,1048576);
  }
  function pageOK(v){return exact(v,['format','binding','report_sha256','section','items','offset','limit','total'])&&v.format==='project_transfer_report_page_v1'&&id(v.binding)&&sha(v.report_sha256)&&sections.includes(v.section)&&integer(v.offset)&&v.limit===40&&integer(v.total)&&Array.isArray(v.items)&&v.items.length<=40&&v.items.length===Math.min(40,Math.max(0,v.total-v.offset))&&v.items.every(item=>itemOK(v.section,item));}
  if(typeof module==='object'&&module.exports)module.exports={normalizeSelection,stateOK,pageOK,receiptOK};
  if(typeof document==='undefined')return;
  const $=name=>document.getElementById(name),base='/api/workspace/project-transfer';
  const pins=/* PROJECT_TRANSFER_CONTRACTS_START */
{
  "project_transfer.extract": "00e0ae9a09d36279684f3614e76445ba1dca50557e55047f699a48b43f823aa8",
  "project_transfer.preview": "7072d7f08763dd05e36c9be6b5aa730411948bb34c32361ec80215dd8b31bf24",
  "project_transfer.report_page": "09dd19eb4299b323710181ea20a7b4dcffce0c2173eeb51a315d551e72811515",
  "project_transfer.status": "190e72fe33a75105b3da034469931b4e30e646ef38af6b55ff8a3c2444725870",
  "project_transfer.stop": "050519dab950115508123eef3bf9a9fe4aad40b920a6612b1b850688afec90b8"
}
/* PROJECT_TRANSFER_CONTRACTS_END */;
  const routes={status:{method:'GET',path:''},preview:{method:'POST',path:'/preview'},report_page:{method:'GET',path:'/report'},stop:{method:'POST',path:'/stop'},extract:{method:'POST',path:'/extract'}};
  let state=null,contracts=new Set(),draft={roots:{},decisions:[]},busy=false,epoch=0,revision=0,reviewed=false,onlyCessation=false;
  let handoff=false,freshControlAttempt=false,freshControl=false,refreshAfter=false,pending=null,lastReceipt=null,page=null,controlCatalog=null,dirty=false;
  function error(message){$('transfer-error').hidden=false;$('transfer-error').textContent=message;$('transfer-error').focus();}
  function message(value){$('transfer-status').textContent=value;}
  function clearError(){$('transfer-error').hidden=true;$('transfer-error').textContent='';}
  function currentOwner(){const value=window.TuldokAuth?.identity?.();return value?.kind==='owner'&&value.scopes?.includes('admin');}
  function action(name){return currentOwner()&&contracts.has('project_transfer.'+name)&&state?.available_actions.includes(name);}
  function signedControl(){return freshControl&&window.TuldokAuth?.identity?.()?.catalog_id===controlCatalog;}
  function controls(){
    const live=state?.phase==='source_live',stopped=state?.phase==='source_stopped',report=state?.report;
    $('selection-fields').disabled=busy||!!pending||!action('preview')||(stopped&&!signedControl());
    $('transfer-refresh').disabled=busy;
    $('report-load').disabled=busy||!report||!action('report_page')||(stopped&&!signedControl());
    $('report-previous').disabled=$('report-load').disabled||!page||page.offset===0;
    $('report-next').disabled=$('report-load').disabled||!page||page.offset+page.items.length>=page.total;
    $('report-reviewed').disabled=busy||!reviewed||!report;
    $('stop-fields').disabled=busy||!live||!action('stop')||!reviewed;
    $('transfer-stop').disabled=$('stop-fields').disabled||!onlyCessation||!$('report-reviewed').checked||!$('stop-confirm').checked;
    $('extract-fields').disabled=busy||!!pending||!stopped||!signedControl()||!action('extract')||!reviewed||!report?.can_extract;
    $('transfer-extract').disabled=$('extract-fields').disabled||!$('report-reviewed').checked||!$('extract-confirm').checked;
    $('transfer-reconcile').hidden=!pending;
    $('transfer-reconcile').disabled=busy||!pending||!stopped||!signedControl()||!action('extract')||state.report?.report_sha256!==pending.report_sha256;
    $('control-signin-panel').hidden=!handoff&&!(stopped&&!signedControl());
    $('control-signin').disabled=busy;
    $('transfer-fence').hidden=state?.phase!=='source_fenced';
    $('transfer-fence').textContent='The source remains fenced. No stopped-source proof is available; extraction is unavailable. Retain any reported receipt or staging directory for operator review.';
  }
  function invalidate(){revision++;dirty=true;reviewed=false;onlyCessation=false;page=null;$('report-reviewed').checked=false;$('stop-confirm').checked=false;$('extract-confirm').checked=false;$('report-items').replaceChildren();$('selection-dirty').textContent='Selection changed. Explicitly preview it again before any source action.';controls();}
  function selection(){return normalizeSelection({project_snapshot:{id:$('snapshot-id').value.trim(),manifest_sha256:$('snapshot-sha').value.trim()},roots:clone(draft.roots),decisions:clone(draft.decisions)});}
  function summarize(){
    const list=$('selection-summary');list.replaceChildren();
    for(const [key,values] of Object.entries(draft.roots))if(values.length){const li=document.createElement('li');li.textContent=`${families[key]??(key==='producer_jobs'?'Producer observations':'Working files')}: ${values.length}`;const remove=document.createElement('button');remove.type='button';remove.textContent='Remove this family';remove.onclick=()=>{delete draft.roots[key];invalidate();summarize();};li.append(remove);list.append(li);}
    for(const decision of draft.decisions){const li=document.createElement('li');li.textContent=`${decision.include?'Include':'Exclude'} ${decision.family} ${decision.id}: ${decision.reason}`;const remove=document.createElement('button');remove.type='button';remove.textContent='Remove decision';remove.onclick=()=>{draft.decisions=draft.decisions.filter(d=>d!==decision);invalidate();summarize();};li.append(remove);list.append(li);}
    if(!list.children.length){const li=document.createElement('li');li.textContent='No global source facts selected. Only the exact registered snapshot will be included unless you add roots.';list.append(li);}
  }
  function fillRoots(){for(const name of ['backup-root','destination-root']){const node=$(name),old=node.value;node.replaceChildren();for(const alias of state.roots){const option=document.createElement('option');option.value=alias;option.textContent=alias;node.append(option);}if(state.roots.includes(old))node.value=old;}}
  function keepReceipt(value){if(!receiptOK(value)||value===null)return;lastReceipt=clone(value);$('transfer-receipt').textContent=`Publication recorded: project ${value.project_id}; ${value.verification?'current verified checkpoint':'recorded checkpoint'} ${value.checkpoint}; request ${value.request_key}.${value.replayed?' Exact request reconciled.':''}`;$('project-files-link').hidden=false;}
  function adopt(value,{ownPreview=false}={}){
    if(!stateOK(value))throw protocol('Unsupported extraction controller response. Refresh status before continuing.');
    const changed=state?.binding!==value.binding;state=value;controlCatalog=value.control_catalog_id;
    fillRoots();if(value.last_receipt)keepReceipt(value.last_receipt);
    if(!ownPreview)$('selection-dirty').textContent='Controller status is current. Explicitly preview your local selection before any source effect.';
    if(changed||!ownPreview){reviewed=false;onlyCessation=false;$('report-reviewed').checked=false;page=null;$('report-items').replaceChildren();}
    if(value.phase==='source_live'){handoff=false;freshControl=false;freshControlAttempt=false;}
    else{handoff=!signedControl();}
    $('transfer-context').textContent=`${value.phase.replaceAll('_',' ')} · source ${value.source_catalog_id} · separate control host ${value.control_catalog_id}`;
    $('control-signin-status').textContent=`Control catalog: ${value.control_catalog_id}. ${signedControl()?'Fresh control sign-in verified.':'Submit a new control-host login code using the standard session dialog.'}`;
    $('report-summary').textContent=value.report?`Report ${value.report.report_sha256}. Included ${value.report.counts.included}; required ${value.report.counts.required}; unassigned ${value.report.counts.unassigned}; blockers ${value.report.counts.blockers}; warnings ${value.report.counts.warnings}; artifacts ${value.report.counts.artifacts}. ${value.report.can_extract?'Complete stopped-source closure is available.':'Extraction is unavailable until every blocker is resolved.'}`:'No current report. Explicitly preview this selection.';
    if(value.destination){$('destination-root').value=value.destination.root;$('destination-directory').value=value.destination.directory;}
    if(value.backup){$('backup-root').value=value.backup.root;$('backup-directory').value=value.backup.directory;}
    $('extract-destination').textContent=value.destination?`Confirmed destination: ${value.destination.root} / ${value.destination.directory}.`:'Confirm the destination before stopping the source.';
    if(value.failure){$('transfer-pending').hidden=false;$('transfer-pending').textContent=`${value.failure.action}: ${value.failure.code}. ${value.failure.detail}${value.failure.staging_directory?' Retained stage: '+value.failure.staging_directory+'.':''}`;}
    controls();
  }
  function row(section,item){const li=document.createElement('li');
    if(section==='artifacts')li.textContent=`${item.sha256} · ${item.bytes} bytes · ${item.preservation} · ${item.state}`;
    else if(section==='working_files')li.textContent=`${item.kind}: ${item.path} · ${item.bytes} bytes · ${item.sha256}`;
    else{li.textContent=`${item.family} · ${item.id}${item.revision!==undefined&&item.revision!==null?' · revision '+item.revision:''}${item.code?' · '+item.code:''}`;if(item.detail){const detail=document.createElement('p');detail.textContent=item.detail;li.append(detail);}}
    return li;
  }
  async function discover(ticket){
    const response=await window.TuldokAuth.fetch('/api/agent/capabilities',{cache:'no-store'}),value=await response.json();
    if(ticket!==epoch)return false;if(!response.ok)throw Error(value?.error??'Sign in, then refresh extraction status.');
    if(!exact(value,['format','envelope_version','catalog_id','operations','limits'])||value.format!=='agent_capabilities_v1'||value.envelope_version!==1||!id(value.catalog_id)||!Array.isArray(value.operations)||value.operations.length>256||!exact(value.limits,['request_bytes','response_bytes','max_operations'])||value.limits.request_bytes!==1048576||value.limits.response_bytes!==16777216||value.limits.max_operations!==256)throw protocol('Unsupported capability discovery response.');
    if(window.TuldokAuth.identity?.()?.catalog_id!==value.catalog_id)throw Error('Capabilities belong to a different current session.');
    const chosen=new Set(),seen=new Set();
    for(const operation of value.operations){if(!exact(operation,['id','contracts','availability'])||typeof operation.id!=='string'||seen.has(operation.id)||!Array.isArray(operation.contracts)||operation.contracts.length>4||!['available','unavailable','unsupported'].includes(operation.availability))throw Error('Unsupported capability entry.');seen.add(operation.id);
      const versions=new Set();for(const contract of operation.contracts){if(!exact(contract,['version','sha256','input_schema','output_schema','scopes','authority','effects','retry','bounds'])||!Number.isSafeInteger(contract.version)||contract.version<1||versions.has(contract.version)||!sha(contract.sha256)||!contract.input_schema||typeof contract.input_schema!=='object'||!contract.output_schema||typeof contract.output_schema!=='object'||!Array.isArray(contract.scopes)||!contract.scopes.every(s=>text(s,40))||!['owner','agent'].includes(contract.authority)||!['read','mutation'].includes(contract.effects)||!['read','cas','receipt','never'].includes(contract.retry)||!exact(contract.bounds,['request_bytes','response_bytes','inline_decoded_bytes','json_depth'])||!Object.values(contract.bounds).every(v=>Number.isSafeInteger(v)&&v>0))throw protocol('Unsupported installed contract discovery frame.');versions.add(contract.version);if(contract.version===1&&operation.availability==='available'&&pins[operation.id]===contract.sha256)chosen.add(operation.id);}
    }
    contracts=chosen;if(!contracts.has('project_transfer.status'))throw Error('No compatible extraction status contract is available.');return true;
  }
  async function call(name,args,ticket,{mutation=false}={}){
    const operation='project_transfer.'+name,route=routes[name];if(!contracts.has(operation))throw Error('No compatible contract is available for '+name+'. Refresh status.');
    let response,value;
    try{const query=route.method==='GET'&&Object.keys(args).length?'?'+new URLSearchParams(args):'';response=await window.TuldokAuth.fetch(base+route.path+query,{method:route.method,cache:'no-store',headers:{'Tuldok-Operation-Contract':operation+'/1/'+pins[operation],...(route.method==='POST'?{'Content-Type':'application/json'}:{})},...(route.method==='POST'?{body:JSON.stringify(args)}:{})});value=await response.json();}
    catch(_){const failure=Error(mutation?'Acknowledgement unavailable. Keep this exact request and refresh status; the source may be fenced or publication may already exist.':'Response unavailable. Refresh status explicitly.');failure.code='transport';throw failure;}
    if(new TextEncoder().encode(JSON.stringify(value)).length>1048576)throw Error('Extraction response exceeds its interface bound.');
    if(mutation&&value?.receipt&&receiptOK(value.receipt))keepReceipt(value.receipt);
    if(ticket!==epoch){message('A session change superseded the response. Any known publication receipt has been retained. Refresh status before continuing.');return null;}
    if(!response.ok){const keys=['error',...(Object.hasOwn(value??{},'code')?['code']:[]),...(Object.hasOwn(value??{},'receipt')?['receipt']:[])];const valid=exact(value,keys)&&text(value.error,1000)&&(!value.code||text(value.code,120))&&(!value.receipt||receiptOK(value.receipt));const failure=Error(valid?`${value.code??'error'}: ${value.error}`:'Unsupported error response. Retain the current request and refresh status.');failure.code=valid?(value.code??'http_error'):'transport';throw failure;}
    return value;
  }
  async function run(work){if(busy)return;busy=true;clearError();const ticket=++epoch;controls();try{await work(ticket);}catch(failure){if(ticket===epoch){if(['invalid_response','transport','stale'].includes(failure.code)){reviewed=false;onlyCessation=false;$('report-reviewed').checked=false;if(failure.code==='invalid_response')contracts.clear();}error(failure.message);}}finally{busy=false;controls();if(refreshAfter){refreshAfter=false;void refresh();}}}
  async function refresh(){return run(async ticket=>{if(!await discover(ticket))return;const value=await call('status',{},ticket);if(value){adopt(value);message('Controller status refreshed. No source or publication action was retried.');}});}
  async function loadPage(ticket,offset=0,section=$('report-section').value){
    const binding=state?.binding,report=state?.report?.report_sha256;if(!report)throw Error('Preview the selection before loading its report.');
    const value=await call('report_page',{binding,report_sha256:report,section,offset,limit:40},ticket);
    if(!value)return;if(!pageOK(value)||value.binding!==binding||value.report_sha256!==report||value.section!==section||value.offset!==offset||value.total!==state.report.counts[section])throw protocol('Report page is stale or unsupported. Preview and review the current report again.');
    page=value;$('report-items').replaceChildren(...value.items.map(item=>row(section,item)));$('report-page-status').textContent=`${section.replaceAll('_',' ')}: ${value.items.length?value.offset+1:0}–${value.offset+value.items.length} of ${value.total}.`;
    if(section==='blockers')onlyCessation=value.total===1&&value.items.length===1&&value.items[0].code==='cessation_proof_unavailable'&&value.items[0].family==='source'&&value.items[0].id===state.source_catalog_id;
    controls();
  }
  function selectionAction(work){try{work();invalidate();summarize();}catch(failure){error(failure.message);}}
  for(const [value,label] of Object.entries(families)){const option=document.createElement('option');option.value=value;option.textContent=label;$('selection-family').append(option);}
  for(const value of canonicalFamilies){const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');$('decision-family').append(option);}
  $('selection-add').onclick=()=>selectionAction(()=>{const key=$('selection-family').value,values=$('selection-ids').value.split(/[\s,]+/u).filter(Boolean);if(!values.length||!values.every(shaRoots.has(key)?sha:id))throw Error('Enter exact '+(shaRoots.has(key)?'SHA256 digests':'32-character IDs')+' for this family.');draft.roots[key]=[...new Set([...(draft.roots[key]??[]),...values])].sort();if(draft.roots[key].length>10000)throw Error('Select at most 10,000 roots per family.');$('selection-ids').value='';});
  $('producer-add').onclick=()=>selectionAction(()=>{const value={kind:$('producer-kind').value,id:$('producer-id').value.trim()};if(!producerKinds.includes(value.kind)||!id(value.id))throw Error('Choose a known producer kind and exact job ID.');const list=draft.roots.producer_jobs??=[];if(!list.some(v=>v.kind===value.kind&&v.id===value.id))list.push(value);$('producer-id').value='';});
  $('working-add').onclick=()=>selectionAction(()=>{const value={kind:$('working-kind').value,path:$('working-path').value.trim()};if(!working(value))throw Error('Use an exact scripts/... or notes/... path without traversal.');const list=draft.roots.working_files??=[];if(!list.some(v=>v.kind===value.kind&&v.path===value.path))list.push(value);$('working-path').value='';});
  $('decision-add').onclick=()=>selectionAction(()=>{const value={family:$('decision-family').value,id:$('decision-id').value.trim(),include:$('decision-include').value==='include',reason:$('decision-reason').value};if(!canonicalFamilies.includes(value.family)||!text(value.id,128)||!text(value.reason,1000))throw Error('Enter a known report family, exact ID and reason.');draft.decisions=draft.decisions.filter(v=>!(v.family===value.family&&v.id===value.id));draft.decisions.push(value);$('decision-id').value='';$('decision-reason').value='';});
  $('selection-clear').onclick=()=>selectionAction(()=>{draft={roots:{},decisions:[]};});
  $('selection-file').onchange=async()=>{const ticket=epoch;try{const file=$('selection-file').files?.[0];if(!file)return;if(file.size>1048576)throw Error('Selection files are limited to one MiB.');const value=normalizeSelection(JSON.parse(await file.text()));if(ticket!==epoch){message('A superseded selection file was ignored. The current selection is unchanged.');return;}$('snapshot-id').value=value.project_snapshot.id;$('snapshot-sha').value=value.project_snapshot.manifest_sha256;draft={roots:value.roots,decisions:value.decisions};invalidate();summarize();message('Loaded a closed selection document. Review its friendly summary, then explicitly preview.');}catch(failure){error('Selection file refused: '+failure.message);}finally{$('selection-file').value='';}};
  for(const name of ['snapshot-id','snapshot-sha'])$(name).addEventListener('input',invalidate);
  for(const name of ['report-reviewed','stop-confirm','extract-confirm'])$(name).addEventListener('change',controls);
  $('transfer-refresh').onclick=refresh;
  $('transfer-preview-form').onsubmit=event=>{event.preventDefault();return run(async ticket=>{const body=selection(),selectedRevision=revision;if(!await discover(ticket))return;const value=await call('preview',{binding:state.binding,selection:body},ticket);if(value&&selectedRevision===revision){adopt(value,{ownPreview:true});reviewed=true;dirty=false;onlyCessation=false;$('selection-dirty').textContent='This exact selection was previewed. Review the report before proceeding.';$('report-section').value='blockers';await loadPage(ticket,0,'blockers');message(state.phase==='source_live'?'Read-only preview complete. Review the closure before any explicit stop.':'Stopped-source preview complete. Review this exact report before extraction.');$('report-title').focus();controls();}});};
  $('report-load').onclick=()=>run(ticket=>loadPage(ticket));$('report-previous').onclick=()=>run(ticket=>loadPage(ticket,Math.max(0,(page?.offset??0)-40)));$('report-next').onclick=()=>run(ticket=>loadPage(ticket,(page?.offset??0)+(page?.items.length??0)));
  $('report-section').addEventListener('change',()=>{page=null;controls();});
  $('transfer-stop-form').onsubmit=event=>{event.preventDefault();return run(async ticket=>{
    if(!reviewed||!onlyCessation||!$('report-reviewed').checked||!$('stop-confirm').checked)throw Error('Review this report and explicitly confirm source stop first.');
    const body={binding:state.binding,report_sha256:state.report.report_sha256,backup_root:$('backup-root').value,backup_directory:$('backup-directory').value.trim(),destination_root:$('destination-root').value,directory:$('destination-directory').value.trim()};
    if(!leaf(body.backup_directory)||!leaf(body.directory)||body.backup_root===body.destination_root&&body.backup_directory===body.directory)throw Error('Choose different new backup and destination directory names without separators.');
    handoff=true;freshControl=false;freshControlAttempt=false;reviewed=false;$('report-reviewed').checked=false;message('Explicit source stop is pending. No other effect is available.');
    try{const value=await call('stop',body,ticket,{mutation:true});if(value){adopt(value);message('Source stop returned. Sign in separately to the control host, then explicitly preview again.');$('control-title').focus();}}
    finally{handoff=true;$('control-signin-panel').hidden=false;$('control-signin-status').textContent=`Separate control catalog: ${controlCatalog??'refresh controller status'}. Submit a new login code, then refresh status.`;window.dispatchEvent(new MessageEvent('message',{origin:location.origin,data:{type:'tuldok-session-changed'}}));}
  });};
  $('control-signin').onclick=()=>{const button=$('session-open');if(button)button.click();else error('The standard session dialog is unavailable.');};
  const loginForm=$('session-form');if(loginForm)loginForm.addEventListener('submit',()=>{if(handoff||state?.phase!=='source_live')freshControlAttempt=true;},true);
  const logout=$('session-logout');if(logout)logout.addEventListener('click',()=>{epoch++;contracts.clear();reviewed=false;onlyCessation=false;freshControl=false;freshControlAttempt=false;$('report-reviewed').checked=false;controls();message('Session sign-out requested. Local selection and retained receipts remain; sign in before continuing.');},true);
  async function extract(ticket,body){
    pending=clone(body);$('transfer-pending').hidden=false;$('transfer-pending').textContent=`Retained request ${body.request_key} for ${body.destination_root} / ${body.directory}. No automatic retry will occur.`;controls();
    const value=await call('extract',body,ticket,{mutation:true});if(!value)return;
    if(!exact(value,['format','binding','receipt','selection'])||value.format!=='project_transfer_extraction_result_v1'||value.binding!==state.binding||!receiptOK(value.receipt)||!exact(value.selection,['selected','state','error'])||typeof value.selection.selected!=='boolean')throw protocol('Unsupported extraction result. Retain its known receipt and refresh status.');
    keepReceipt(value.receipt);const selected=value.selection.selected,project=value.selection.state?.project;
    if(selected&&(!project||project.project_id!==value.receipt.project_id||project.checkpoint!==value.receipt.checkpoint))throw protocol('Publication is recorded, but the selected project identity or checkpoint differs. Inspect the file workspace explicitly.');
    pending=null;reviewed=false;$('report-reviewed').checked=false;$('extract-confirm').checked=false;$('transfer-pending').hidden=true;$('selection-outcome').textContent=selected?'At acknowledgement, the verified destination was selected. The file workspace link opens the current inert metadata view.':'Publication is recorded. Selection was unavailable; inspect the file workspace and Open this directory explicitly.';
    message(value.receipt.replayed?'Exact extraction request reconciled against the current destination.':'Project published. No computation was started.');$('outcome-title').focus();
  }
  $('transfer-extract-form').onsubmit=event=>{event.preventDefault();return run(async ticket=>{if(!signedControl()||!reviewed||!state?.report?.can_extract||!$('report-reviewed').checked||!$('extract-confirm').checked)throw Error('Sign in to the control host and review the stopped-source report before extraction.');const body={binding:state.binding,report_sha256:state.report.report_sha256,destination_root:state.destination?.root,directory:state.destination?.directory,name:$('destination-name').value,request_key:$('extraction-key').value.trim()};if(!text(body.name,200)||!text(body.request_key,128)||!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(body.request_key))throw Error('Enter a project name and exact request key.');await extract(ticket,body);});};
  $('transfer-reconcile').onclick=()=>run(async ticket=>{if(!pending||!signedControl()||state?.report?.report_sha256!==pending.report_sha256)throw Error('Refresh current authorization and this exact report before an explicit reconciliation.');await extract(ticket,{...pending,binding:state.binding});});
  window.addEventListener('tuldok-session',()=>{epoch++;contracts.clear();reviewed=false;onlyCessation=false;$('report-reviewed').checked=false;$('report-items').replaceChildren();if(freshControlAttempt&&window.TuldokAuth.identity?.()?.catalog_id===controlCatalog){freshControl=true;handoff=false;message('Fresh control-host sign-in verified. Explicitly preview the stopped source again.');}controls();if(busy)refreshAfter=true;else void refresh();});
  window.addEventListener('beforeunload',event=>{if(dirty||pending){event.preventDefault();event.returnValue='';}});
  $('extraction-key').value=crypto.randomUUID().replaceAll('-','');summarize();controls();void refresh();
})();
