// Read-only gateway observations own configuration controls, never annotation state.
'use strict';
let pumasGateways=[],pumasGatewayEpoch=0,pumasGatewayOperation=null,pumasGatewayPaused=false;
const pumasGatewayTargets={caption:'caption-proposal-url',classification:'text-classification-proposal-url',rewrite:'grounded-url'};
const pumasGatewayStatus=message=>{$('pumas-gateway-status').textContent=message;};
function selectedPumasGateway(){return pumasGateways.find(row=>row.server_url===$('pumas-gateway-choice').value);}
function pumasGatewayConfiguration(target){
  // Existing owners can restore frozen settings without dispatching DOM events.
  const owner=target==='text-classification-proposal-url'?[textClassificationProposalModelEpoch,textClassificationProposalFormEpoch]:
    target==='caption-proposal-url'?captionProposalModelEpoch:modelEpoch;
  return JSON.stringify([$(target).value,$(target.replace(/-url$/,'-model')).value,owner]);
}
function renderPumasGateway(){
  const row=selectedPumasGateway();
  $('pumas-gateway-metadata').hidden=!row;
  $('pumas-gateway-metadata').textContent=row?JSON.stringify(row,null,2):'';
  $('pumas-gateway-use').disabled=!!pumasGatewayOperation||pumasGatewayPaused||!row;
  $('pumas-gateway-scan').disabled=!!pumasGatewayOperation||pumasGatewayPaused;
}
function clearPumasGateways(){
  pumasGateways=[];$('pumas-gateway-choice').replaceChildren(new Option('Choose an advertised gateway',''));renderPumasGateway();
}
$('pumas-gateway-scan').addEventListener('click',async()=>{
  if(pumasGatewayOperation||pumasGatewayPaused)return;
  const token={epoch:++pumasGatewayEpoch};pumasGatewayOperation=token;clearPumasGateways();
  pumasGatewayStatus('Looking for local Pumas advertisements…');
  try{
    const result=await api('/api/generation/advertised-gateways',{});
    if(token.epoch!==pumasGatewayEpoch||pumasGatewayPaused)return;
    if(!Array.isArray(result.gateways))throw Error('Invalid gateway observations.');
    pumasGateways=result.gateways;
    $('pumas-gateway-choice').replaceChildren(new Option('Choose an advertised gateway',''),...pumasGateways.map(row=>
      new Option(row.server_url+' · '+row.advertisement.build_info.package_version+' · '+row.advertisement.instance.registry_library_id,row.server_url)));
    pumasGatewayStatus(pumasGateways.length?'Choose a gateway and annotation workflow. Model support is checked when you request a proposal.':'No compatible HTTP advertisements found. Start Pumas with HTTP discovery, or enter a legacy gateway URL in the proposal form.');
  }catch(error){if(token.epoch===pumasGatewayEpoch&&!pumasGatewayPaused)pumasGatewayStatus(error.message);}
  finally{if(pumasGatewayOperation===token){pumasGatewayOperation=null;renderPumasGateway();}}
});
for(const id of ['pumas-gateway-choice','pumas-gateway-target'])$(id).addEventListener('change',()=>{++pumasGatewayEpoch;renderPumasGateway();});
for(const id of Object.values(pumasGatewayTargets)) {
  for(const control of [$(id),$(id.replace(/-url$/, '-model'))])
    for(const event of ['input','change'])control.addEventListener(event,()=>{++pumasGatewayEpoch;});
}
$('pumas-gateway-use').addEventListener('click',async()=>{
  const row=selectedPumasGateway(),target=pumasGatewayTargets[$('pumas-gateway-target').value];
  if(!row||!target||pumasGatewayOperation||pumasGatewayPaused)return;
  const token={epoch:++pumasGatewayEpoch,configuration:pumasGatewayConfiguration(target)};pumasGatewayOperation=token;renderPumasGateway();
  pumasGatewayStatus('Rechecking the selected gateway…');
  try{
    const result=await api('/api/generation/inspect-gateway',{server_url:row.server_url});
    if(token.epoch!==pumasGatewayEpoch||pumasGatewayPaused||token.configuration!==pumasGatewayConfiguration(target))return;
    if(result.server_url!==row.server_url||JSON.stringify(result.advertisement)!==JSON.stringify(row.advertisement)){
      clearPumasGateways();throw Error('Gateway advertisement changed. Scan again before choosing it.');
    }
    const input=$(target);input.value=row.server_url;
    input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
    pumasGatewayStatus('Gateway URL set. Open the chosen proposal form and list its served models; no proposal was started.');
  }catch(error){if(token.epoch===pumasGatewayEpoch&&!pumasGatewayPaused&&token.configuration===pumasGatewayConfiguration(target))pumasGatewayStatus(error.message);}
  finally{if(pumasGatewayOperation===token){pumasGatewayOperation=null;renderPumasGateway();}}
});
window.addEventListener('pagehide',()=>{++pumasGatewayEpoch;pumasGatewayPaused=true;pumasGatewayOperation=null;clearPumasGateways();});
window.addEventListener('pageshow',()=>{pumasGatewayPaused=false;renderPumasGateway();});
clearPumasGateways();
