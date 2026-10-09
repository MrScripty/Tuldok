// Explicit original-SDK observation; owns configuration only, never acquisition.
'use strict';
let pumasOwnerLibraries=null,pumasOwnerReceipt=null,pumasOwnerEpoch=0,pumasOwnerOperation=null,pumasOwnerPaused=false;
let pumasOwnerCatalog=null,pumasOwnerTypedInspection=null;
const pumasOwnerTargets={caption:'caption-proposal',classification:'text-classification-proposal',rewrite:'grounded'};
const pumasOwnerStatus=message=>{$('pumas-owner-status').textContent=message;};
const pumasOwnerSelected=()=>pumasOwnerLibraries?.registered_libraries.find(row=>row.id===$('pumas-owner-library').value);
function pumasOwnerConfiguration(prefix){
  const epochs=prefix==='text-classification-proposal'?[textClassificationProposalModelEpoch,textClassificationProposalFormEpoch]:prefix==='caption-proposal'?[captionProposalModelEpoch]:[modelEpoch];
  return JSON.stringify([['url','model','protocol','profile'].map(name=>$(prefix+'-'+name)?.value??(name==='protocol'?'legacy':null)),epochs,pumasTypedEpoch[prefix]||0]);
}
function renderPumasOwner(){
  const row=pumasOwnerSelected(),busy=!!pumasOwnerOperation||pumasOwnerPaused;
  $('pumas-owner-list').disabled=busy;$('pumas-owner-observe').disabled=busy||!row;
  $('pumas-owner-use').disabled=busy||!row||!pumasOwnerReceipt;
  $('pumas-owner-models').disabled=busy||!row||!pumasOwnerReceipt;
  $('pumas-owner-capability').disabled=busy||!row||!pumasOwnerReceipt||!$('pumas-owner-model').value||$('pumas-owner-target').value==='caption';
  const models=row&&pumasOwnerLibraries.local_models.find(item=>item.registry_library_id===row.id);
  $('pumas-owner-metadata').hidden=!row;
  $('pumas-owner-metadata').textContent=row?JSON.stringify({library:row,local_index:models,
    producer_commit:pumasOwnerLibraries.producer_commit,producer_status:pumasOwnerLibraries.producer_status,
    registry_context:pumasOwnerLibraries.registry_context,scope:pumasOwnerLibraries.scope,
    authenticated_observation:pumasOwnerReceipt,serving_catalog:pumasOwnerCatalog,typed_inspection:pumasOwnerTypedInspection},null,2):'';
}
function clearPumasOwner(){
  pumasOwnerLibraries=null;pumasOwnerReceipt=null;pumasOwnerCatalog=null;pumasOwnerTypedInspection=null;
  $('pumas-owner-model').replaceChildren(new Option('Inspect serving aliases first',''));
  $('pumas-owner-library').replaceChildren(new Option('Choose a registered library',''));renderPumasOwner();
}
$('pumas-owner-list').addEventListener('click',async()=>{
  if(pumasOwnerOperation||pumasOwnerPaused)return;
  const token={epoch:++pumasOwnerEpoch};pumasOwnerOperation=token;clearPumasOwner();
  pumasOwnerStatus('Reading registered libraries and bounded local index observations…');
  try{
    const result=await api('/api/generation/local-pumas/libraries',{});
    if(token.epoch!==pumasOwnerEpoch||pumasOwnerPaused)return;
    if(!Array.isArray(result.registered_libraries)||!Array.isArray(result.local_models))throw Error('Invalid local library observations.');
    pumasOwnerLibraries=result;
    $('pumas-owner-library').replaceChildren(new Option('Choose a registered library',''),...result.registered_libraries.map(row=>new Option(row.name+' · '+row.root,row.id)));
    pumasOwnerStatus(result.registered_libraries.length?'Select a library and inspect its local index before authenticating the existing HTTP owner. Index rows are not served aliases or runtime readiness.':'The selected registry has no registered libraries. No owner was started.');
  }catch(error){if(token.epoch===pumasOwnerEpoch&&!pumasOwnerPaused)pumasOwnerStatus(error.message);}
  finally{if(pumasOwnerOperation===token){pumasOwnerOperation=null;renderPumasOwner();}}
});
$('pumas-owner-library').addEventListener('change',()=>{++pumasOwnerEpoch;pumasOwnerReceipt=null;pumasOwnerCatalog=null;pumasOwnerTypedInspection=null;$('pumas-owner-model').replaceChildren(new Option('Inspect serving aliases first',''));renderPumasOwner();});
$('pumas-owner-target').addEventListener('change',()=>{++pumasOwnerEpoch;pumasOwnerTypedInspection=null;renderPumasOwner();});
for(const prefix of Object.values(pumasOwnerTargets))for(const name of ['url','model','protocol','profile'])
  for(const event of ['input','change'])$(prefix+'-'+name)?.addEventListener(event,()=>{++pumasOwnerEpoch;});
async function pumasOwnerAction(use){
  const row=pumasOwnerSelected(),prefix=pumasOwnerTargets[$('pumas-owner-target').value];
  if(!row||!prefix||pumasOwnerOperation||pumasOwnerPaused||(use&&!pumasOwnerReceipt))return;
  if(use&&($(prefix+'-protocol')?.value||'legacy')!=='legacy'){
    pumasOwnerStatus('Typed v1 and authenticated discovery are separate producer stacks. This chooser cannot compose them; choose the compatible API explicitly.');return;
  }
  const selected={id:row.id,root:row.root},selection=JSON.stringify(row),config=pumasOwnerConfiguration(prefix);
  const token={epoch:++pumasOwnerEpoch};pumasOwnerOperation=token;renderPumasOwner();
  const current=()=>token.epoch===pumasOwnerEpoch&&!pumasOwnerPaused&&JSON.stringify(pumasOwnerSelected())===selection&&pumasOwnerConfiguration(prefix)===config;
  pumasOwnerStatus(use?'Reauthenticating the selected existing owner before copying its URL…':'Authenticating selected core IPC, HTTP descriptor and final core identity…');
  try{
    const result=await api('/api/generation/local-pumas/'+(use?'use':'observe'),use?{receipt:pumasOwnerReceipt,protocol:'legacy'}:{selected});
    if(!current())return;
    if(JSON.stringify(result.observation?.selected)!==JSON.stringify(selected)||result.observation?.producer_commit!==pumasOwnerLibraries.producer_commit)
      throw Error('Authenticated library/source context changed. List again.');
    if(use&&JSON.stringify(result.observation.service)!==JSON.stringify(pumasOwnerReceipt.observation.service))throw Error('Core/HTTP descriptor changed. Authenticate again.');
    pumasOwnerReceipt=result;
    if(use){
      const input=$(prefix+'-url');input.value=result.server_url;
      input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
      pumasOwnerStatus('URL copied after fresh authenticated observation. No proposal, model or acquisition request started. Ownership is not reserved for later inference.');
    }else pumasOwnerStatus('Existing owner authenticated at this observation. Inspect its full identity, then explicitly Use to reauthenticate and copy the URL. No lifetime lease or model readiness is established.');
  }catch(error){if(current()){pumasOwnerReceipt=null;pumasOwnerStatus(error.message);}}
  finally{if(pumasOwnerOperation===token){pumasOwnerOperation=null;renderPumasOwner();}}
}
$('pumas-owner-observe').addEventListener('click',()=>pumasOwnerAction(false));
$('pumas-owner-use').addEventListener('click',()=>pumasOwnerAction(true));
window.addEventListener('pagehide',()=>{++pumasOwnerEpoch;pumasOwnerPaused=true;pumasOwnerOperation=null;clearPumasOwner();});
window.addEventListener('pageshow',()=>{pumasOwnerPaused=false;renderPumasOwner();});
clearPumasOwner();

for(const id of ['pumas-owner-model','pumas-owner-profile'])for(const event of ['input','change'])$(id).addEventListener(event,()=>{++pumasOwnerEpoch;pumasOwnerTypedInspection=null;renderPumasOwner();});
async function pumasOwnerInspectTyped(capability){
  const row=pumasOwnerSelected(),purpose=$('pumas-owner-target').value;
  if(!row||!pumasOwnerReceipt||pumasOwnerOperation||pumasOwnerPaused)return;
  if(capability&&(purpose==='caption'||!$('pumas-owner-model').value)){pumasOwnerStatus('Select a serving alias and supported text purpose. Image-to-Text unavailable.');return;}
  const receipt=pumasOwnerReceipt,prefix=pumasOwnerTargets[purpose];
  const stamp=()=>JSON.stringify([pumasOwnerSelected(),purpose,pumasOwnerConfiguration(prefix),$('pumas-owner-target').value,$('pumas-owner-model').value,$('pumas-owner-profile').value,current?[current.id,current.revision,current.source_revision]:null,editorEpoch,dirty]);
  const token={epoch:++pumasOwnerEpoch,stamp:stamp()};pumasOwnerOperation=token;renderPumasOwner();
  const live=()=>!pumasOwnerPaused&&pumasOwnerOperation===token&&token.epoch===pumasOwnerEpoch&&token.stamp===stamp();
  pumasOwnerStatus('Reading serving observations between two fresh authenticated owner checks. Owner-bound typed use remains unavailable.');
  try{
    const body=capability?{receipt,model:$('pumas-owner-model').value,profile:$('pumas-owner-profile').value||null,purpose}:{receipt};
    const value=await api('/api/generation/local-pumas/'+(capability?'typed_selection':'typed_models'),body);
    if(!live())return;
    const observation=value.receipt?.observation;
    if(value.kind!==(capability?'capability':'catalog')||value.discovery_contract_source!==pumasOwnerLibraries.producer_commit||value.typed_contract_source!==pumasSelectedTypedSource||
       value.inference_admitted!==false||value.configuration_apply_supported!==false||value.joint_producer_qualified!==false||
       JSON.stringify(observation?.service)!==JSON.stringify(receipt.observation.service)||observation?.registry_context!==receipt.observation.registry_context||
       JSON.stringify(observation?.selected)!==JSON.stringify(receipt.observation.selected)||observation?.producer_commit!==receipt.observation.producer_commit||value.receipt.server_url!==receipt.server_url||
       (capability?!pumasSelectedAssociation(value.inspection,{server_url:receipt.server_url,model:body.model,profile:body.profile,purpose}):
         value.inspection?.producer_contract_source!==pumasSelectedTypedSource||!Array.isArray(value.inspection.models)||value.inspection.models.length>64||
         value.inspection.models.some(r=>typeof r.id!=='string'||!r.id||r.id.length>256)||new Set(value.inspection.models.map(r=>r.id)).size!==value.inspection.models.length))
      throw Error('Owner/inspection association changed; no typed configuration applied.');
    pumasOwnerReceipt=value.receipt;pumasOwnerTypedInspection=value;
    if(!capability){pumasOwnerCatalog=value.inspection;$('pumas-owner-model').replaceChildren(new Option('Choose an explicit serving alias',''),...value.inspection.models.map(r=>new Option(r.id,r.id)));}
    pumasOwnerStatus('Read-only serving observation complete. Public producer stacks remain separate; authenticated typed configuration/inference unavailable. No model operation or acquisition started.');
  }catch(error){if(live()){pumasOwnerTypedInspection=null;pumasOwnerStatus(error.message+' Owner-bound typed use unavailable; no fallback.');}}
  finally{if(pumasOwnerOperation===token){pumasOwnerOperation=null;renderPumasOwner();}}
}
$('pumas-owner-models').addEventListener('click',()=>pumasOwnerInspectTyped(false));
$('pumas-owner-capability').addEventListener('click',()=>pumasOwnerInspectTyped(true));
