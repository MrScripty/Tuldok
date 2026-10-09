// Standalone typed text configuration only. Never authenticated-owner admission.
'use strict';
const pumasModelSelections={},pumasModelSelectionOperations={};
let pumasModelSelectionHidden=false;
function pumasModelSelectionStamp(prefix){
  const e=name=>document.getElementById(prefix+'-'+name);
  return JSON.stringify([['url','model','profile','protocol'].map(n=>e(n).value),pumasTypedEpoch[prefix]||0,
    prefix==='grounded'?modelEpoch:[textClassificationProposalModelEpoch,textClassificationProposalFormEpoch],
    current?[current.id,current.revision,current.source_revision]:null,editorEpoch,dirty,
    typeof hasUnsavedEdits==='function'?hasUnsavedEdits():false]);
}
function pumasModelSelectionRender(prefix){
  const button=document.getElementById(prefix+'-selection-use');
  if(button)button.disabled=pumasModelSelectionHidden||!!pumasModelSelectionOperations[prefix]||!pumasModelSelections[prefix];
}
function pumasModelSelectionInvalidate(prefix){
  delete pumasModelSelections[prefix];pumasModelSelectionRender(prefix);
}
const pumasSelectedTypedSource='40c5cbfed67a6f0e862a1197bb5105363d67bdb1';
function pumasSelectedEndpoint(raw){
  const url=new URL(raw);
  if(url.protocol!=='http:'||url.username||url.password||!['','/'].includes(url.pathname)||url.search||url.hash||/[?#\s]/.test(raw))throw Error('Invalid selected endpoint.');
  const host=url.hostname;
  if(!/^127\.\d+\.\d+\.\d+$/.test(host)&&host!=='[::1]')throw Error('Invalid selected numeric-loopback endpoint.');
  return 'http://'+host+':'+(url.port||'80');
}
function pumasSelectedAssociation(value,body){
  const manifest=value?.capability_observation?.capabilities;
  return value?.server_url===pumasSelectedEndpoint(body.server_url)&&value.model===body.model&&value.purpose===body.purpose&&value.protocol==='pumas_typed_v1'&&
    typeof value.profile==='string'&&/^[A-Za-z0-9_.-]{1,128}$/.test(value.profile)&&(!body.profile||body.profile===value.profile)&&
    value.producer_contract_source===pumasSelectedTypedSource&&value.owner_authenticated===false&&value.inference_admitted===false&&
    manifest?.model===value.model&&manifest.profile===value.profile&&/^[0-9a-f]{64}$/.test(value.capability_observation.observed_sha256);
}
async function pumasModelSelectionAction(prefix,use){
  const get=n=>document.getElementById(prefix+'-'+n),purpose=prefix==='grounded'?'rewrite':'classification';
  if(pumasModelSelectionHidden||pumasModelSelectionOperations[prefix])return;
  const old=pumasModelSelections[prefix];
  if(use&&(!old||old.stamp!==pumasModelSelectionStamp(prefix))){pumasModelSelectionInvalidate(prefix);return;}
  const token={stamp:pumasModelSelectionStamp(prefix)};pumasModelSelectionOperations[prefix]=token;
  const live=()=>!pumasModelSelectionHidden&&pumasModelSelectionOperations[prefix]===token&&token.stamp===pumasModelSelectionStamp(prefix);
  const output=get('capability-metadata');output.hidden=false;output.textContent=use?'Rechecking exact serving alias/profile and compatible text options…':'Inspecting explicit serving alias and resolving exact text profile…';pumasModelSelectionRender(prefix);
  try{
    if(get('protocol').value!=='pumas_typed_v1')throw Error('Choose Pumas typed v1 for standalone text selection.');
    const body={server_url:get('url').value,model:get('model').value,profile:use?old.selection.profile:get('profile').value||null,purpose};
    const value=await api('/api/generation/typed-selection',body);
    if(!live())return;
    if(!pumasSelectedAssociation(value,body))throw Error('Selected text configuration association changed. Inspect again.');
    if(use&&(value.profile!==old.selection.profile||value.server_url!==old.selection.server_url||value.producer_contract_source!==old.selection.producer_contract_source||value.capability_observation?.observed_sha256!==old.selection.capability_observation?.observed_sha256))throw Error('Exact selected profile/endpoint/source changed. Inspect again.');
    if(use){
      // No await between fields. Ordinary URL events can clear catalog options.
      for(const [name,val] of [['url',value.server_url],['protocol',value.protocol],['profile',value.profile]]){
        const input=get(name);input.value=val;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
      }
      const option=new Option(value.model,value.model);get('model').replaceChildren(option);get('model').value=value.model;
      get('model').dispatchEvent(new Event('input',{bubbles:true}));get('model').dispatchEvent(new Event('change',{bubbles:true}));
      output.hidden=false;output.textContent=JSON.stringify({selection:value,configuration_applied:true,proposal_started:false,owner_authenticated:false},null,2);
    }else{pumasModelSelections[prefix]={selection:value,stamp:token.stamp};output.textContent=JSON.stringify(value,null,2);}
  }catch(error){if(live()){pumasModelSelectionInvalidate(prefix);output.hidden=false;output.textContent=error.message;}}
  finally{if(pumasModelSelectionOperations[prefix]===token){delete pumasModelSelectionOperations[prefix];pumasModelSelectionRender(prefix);}}
}
for(const prefix of ['text-classification-proposal','grounded']){
  document.getElementById(prefix+'-selection-inspect').addEventListener('click',()=>pumasModelSelectionAction(prefix,false));
  document.getElementById(prefix+'-selection-use').addEventListener('click',()=>pumasModelSelectionAction(prefix,true));
  pumasModelSelectionRender(prefix);
}
window.addEventListener('pagehide',()=>{pumasModelSelectionHidden=true;for(const prefix of ['text-classification-proposal','grounded']){delete pumasModelSelectionOperations[prefix];pumasModelSelectionInvalidate(prefix);}});
window.addEventListener('pageshow',()=>{pumasModelSelectionHidden=false;for(const prefix of ['text-classification-proposal','grounded'])pumasModelSelectionRender(prefix);});
