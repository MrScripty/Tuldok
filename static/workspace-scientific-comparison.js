"use strict";
// Runs/extension evidence own all compatibility and arithmetic. This view only selects and renders.
window.WorkspaceScientificContracts = {'runs.compare_scientific_evidence/1':'32fe4994c2a38f8d38335c3c2d1db84c82c0f3b61c6a11d95e71cc5f02f35be5'};
window.WorkspaceScientificComparison = function ({api,announce,identity=()=>window.TuldokAuth?.identity()}) {
  const esc=window.workspaceEscape,enc=encodeURIComponent,same=(a,b)=>window.WorkspacePublicationDocuments.same(a,b);
  const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  const session=()=>JSON.stringify([identity()?.catalog_id,identity()?.actor_id,identity()?.credential_id]);
  const eligible=run=>run?.graph?.recipe==='external_recipe'&&['completed','failed','interrupted'].includes(run.state);
  let generation=0,intent=0,source=null,target=null,result=null,error='',busy=false,chosen='',pending=null,loadedSession=null;
  let selected={checkpoint:'',other:'',metric:'',field:'',x:0,y:0,z:0,mode:'paired'};
  function clear(){intent++;result=null;error='';}
  function fence(current){const own=++intent,version=generation,credential=session();return ()=>current()&&own===intent&&version===generation&&credential===session();}
  function decodeIndex(value,run){
    if(value?.state!=='verified'||value.manifest?.producer?.run_id!==run.id||value.probe?.split!=='validation'||!Array.isArray(value.probe.members)||!Array.isArray(value.fields)||!Array.isArray(value.checkpoint_index?.entries)||!Array.isArray(value.metric_definitions)||!value.metric_definition_hashes)throw Error('Exact retained standalone field evidence is unavailable.');
    for(const entry of value.checkpoint_index.entries)if(!hash(entry.checkpoint?.sha256)||!entry.clocks||entry.clocks.physical_time!==null)throw Error('Checkpoint identity or standalone progress is invalid.');
    return value;
  }
  async function read(run,current){
    let operand,artifacts,value;
    if(run.state==='completed'){
      operand={kind:'completed_run',catalog_id:identity()?.catalog_id,run_id:run.id};artifacts=run.artifacts;
      value=await api('runs/'+enc(run.id)+'/model-evidence',{},2);
    }else{
      const status=await api('runs/'+enc(run.id)+'/publication',undefined,2);if(!current())return;
      const ref=status.continuation?.result_ref;
      if(!ref||!window.WorkspacePublicationDocuments.resultRef(ref,{catalog_id:identity()?.catalog_id,run_id:run.id}))throw Error('This stopped Run has no exact attached recovered publication Ref.');
      operand={kind:'publication_result',ref};
      const retained=await api('publication-results',{ref},1);if(!current())return;
      if(!same(retained.result_ref,ref))throw Error('Recovered publication identity differs.');artifacts=retained.artifacts;
      const projection=await api('publication-results/model-evidence',{ref,selectors:{}},1);if(!current())return;
      if(!same(projection.result_ref,ref))throw Error('Recovered evidence identity differs.');value=projection.evidence;
    }
    if(!current())return;
    const evidence=decodeIndex(value,run),evaluation=artifacts?.find(row=>row.name==='model-evidence.json');
    if(!hash(evaluation?.sha256))throw Error('Exact evaluation artifact is unavailable.');
    return {run,evidence,operand,evaluation:evaluation.sha256};
  }
  function defaults(){
    if(source){selected.checkpoint=source.evidence.checkpoint_index.entries.find(row=>row.selected)?.checkpoint.sha256||source.evidence.checkpoint_index.entries[0]?.checkpoint.sha256||'';selected.metric=source.evidence.metric_definitions[0]?.id||'';selected.field=source.evidence.fields[0]?.field_id||'';}
    selected.other=target?.evidence.checkpoint_index.entries.find(row=>row.selected)?.checkpoint.sha256||target?.evidence.checkpoint_index.entries[0]?.checkpoint.sha256||'';
  }
  function request(){return {operands:[source.operand,target.operand],selection:{checkpoint_sha256:selected.checkpoint,other_checkpoint_sha256:selected.other,evaluation_sha256:source.evaluation,other_evaluation_sha256:target.evaluation,metric_id:selected.metric,metric_definition_sha256:source.evidence.metric_definition_hashes[selected.metric],other_metric_definition_sha256:target.evidence.metric_definition_hashes[selected.metric],mode:selected.mode},point:{field_id:selected.field,x:selected.x,y:selected.y,z:selected.z}};}
  function decode(value,body){
    const finite=(item,depth=0)=>depth<=64&&(item===null||typeof item==='string'||typeof item==='boolean'||typeof item==='number'&&Number.isFinite(item)||Array.isArray(item)&&item.every(child=>finite(child,depth+1))||item&&typeof item==='object'&&Object.values(item).every(child=>finite(child,depth+1)));
    if(!finite(value)||!Array.isArray(value?.scalar?.sides)||value.scalar.sides.length!==2)throw Error('Comparison numeric values or sides are invalid.');
    if(value?.format!=='scientific_comparison_v1'||!same(value.point,body.point)||!Array.isArray(value.operands)||value.operands.length!==2||!value.operands.every((side,i)=>same(side.operand,body.operands[i]))||!['compatible','incompatible'].includes(value.scalar?.state)||value.scalar.mode!==body.selection.mode||!Array.isArray(value.scalar.reasons)||value.scalar.reasons.some(reason=>typeof reason!=='string')||!Array.isArray(value.cases)||value.cases.length>16||value.criterion?.state!=='unknown'||typeof value.criterion.reason!=='string'||!value.coverage)throw Error('Comparison response identity or projection differs.');
    value.scalar.sides.forEach((side,i)=>{
      const prefix=i?'other_':'',index=i?target:source,definition=index.evidence.metric_definitions.find(row=>row.id===body.selection.metric_id),entry=index.evidence.checkpoint_index.entries.find(row=>row.checkpoint.sha256===body.selection[prefix+'checkpoint_sha256']);
      if(side.run_id!==(body.operands[i].run_id||body.operands[i].ref.run_id)||side.split!=='validation'||['checkpoint_sha256','evaluation_sha256','metric_definition_sha256'].some(key=>side[key]!==body.selection[prefix+key])||side.metric_id!==body.selection.metric_id||side.units!==definition?.units||side.direction!==definition?.direction||!same(side.clocks,entry?.clocks)||!side.result||(side.result.state==='observed'?(!Number.isFinite(side.result.value)||!Number.isSafeInteger(side.result.sample_count)||side.result.sample_count<1):side.result.state!=='undefined'||typeof side.result.reason!=='string'))throw Error('Comparison side identities or observations differ.');
      const metadata=value.operands[i];if(metadata.original_run_state!==index.run.state||metadata.model?.sha256!==index.evidence.manifest.model_sha256||metadata.material?.sha256!==index.evidence.manifest.producer.material_sha256||metadata.memory?.state!=='unknown'||typeof metadata.memory.reason!=='string'||metadata.custody!=='managed_run_artifacts'||!metadata.timings||!Array.isArray(metadata.artifacts)||metadata.artifacts.length>256)throw Error('Comparison material or diagnostic scope differs.');
    });
    const expectedCases=new Map([...source.evidence.probe.members,...target.evidence.probe.members].map(row=>[JSON.stringify(row.frozen_reference),row.frozen_reference]));
    const receivedCases=new Set();
    for(const row of value.cases){
      const identity=JSON.stringify(row.case);if(!expectedCases.has(identity)||receivedCases.has(identity))throw Error('Case identity does not belong to the selected union.');receivedCases.add(identity);
      if(!row.case||!Array.isArray(row.values)||row.values.length!==2||row.acceptance?.state!=='unknown'||typeof row.acceptance.reason!=='string')throw Error('Case correspondence is invalid.');
      for(const side of row.values)if(side.state==='observed'?(!Number.isFinite(side.prediction)||!Number.isFinite(side.reference)||typeof side.units!=='string'):side.state!=='missing'||typeof side.reason!=='string')throw Error('Case value is invalid.');
      if(row.prediction_delta!==null&&(!Number.isFinite(row.prediction_delta?.value)||typeof row.prediction_delta.units!=='string'||value.scalar.state!=='compatible'||body.selection.mode!=='paired'))throw Error('Incompatible or invalid diagnostic delta.');
    }
    for(const key of ['baseline','candidate','matched','union'])if(!Number.isSafeInteger(value.coverage[key])||value.coverage[key]<0||value.coverage[key]>16)throw Error('Coverage is invalid.');
    if(receivedCases.size!==expectedCases.size||value.coverage.union!==value.cases.length)throw Error('Coverage count differs.');
    return value;
  }
  const clock=value=>Object.entries(value).filter(([key,v])=>v!==null).map(([key,v])=>key+' '+v).join(' · ');
  function checkpoints(evidence,value){return evidence.checkpoint_index.entries.map(row=>`<option value="${esc(row.checkpoint.sha256)}" ${value===row.checkpoint.sha256?'selected':''}>${esc(clock(row.clocks))} · ${esc(row.checkpoint.sha256.slice(0,12))}</option>`).join('');}
  function valueHTML(side){return side.state==='observed'?`${esc(side.prediction)} / ${esc(side.reference)} ${esc(side.units)}`:`Missing: ${esc(side.reason)}`;}
  function resultHTML(){
    if(!result)return '';
    const scalar=result.scalar;
    return `<div id="scientific-result" tabindex="-1"><h4>Exact comparison: ${esc(scalar.state)}</h4><p>${scalar.reasons.map(esc).join(' ')||'Compatible retained validation meanings.'}</p><p>Coverage: baseline ${result.coverage.baseline}; candidate ${result.coverage.candidate}; matched ${result.coverage.matched}; union ${result.coverage.union}.</p><p>Scientific acceptance: unknown — ${esc(result.criterion.reason)}. Field-point subtraction is diagnostic only; no error operator or acceptance threshold is applied.</p><div class="real-table-wrap" tabindex="0" aria-label="Exact per-case diagnostic values"><table><caption>Selected field point · prediction / reference; delta is candidate prediction minus baseline prediction</caption><thead><tr><th scope="col">Frozen case</th><th scope="col">Baseline</th><th scope="col">Candidate</th><th scope="col">Diagnostic delta</th><th scope="col">Acceptance</th></tr></thead><tbody>${result.cases.map(row=>`<tr><th scope="row">${esc(JSON.stringify(row.case))}</th>${row.values.map(side=>`<td>${valueHTML(side)}</td>`).join('')}<td>${row.prediction_delta?esc(row.prediction_delta.value)+' '+esc(row.prediction_delta.units):'Unavailable'}</td><td>Unknown: ${esc(row.acceptance.reason)}</td></tr>`).join('')}</tbody></table></div><div class="real-table-wrap" tabindex="0"><table><caption>Exact retained scalar observations and actual recorded progress</caption><thead><tr><th scope="col">Side</th><th scope="col">Progress</th><th scope="col">Value</th></tr></thead><tbody>${scalar.sides.map((side,i)=>`<tr><th scope="row">${i?'Candidate':'Baseline'}</th><td>${esc(clock(side.clocks))}<br><small>Epoch: ${side.clocks.epoch===null?'not recorded':esc(side.clocks.epoch)}; fit pass: ${side.clocks.fit_pass===null?'not recorded':esc(side.clocks.fit_pass)}; physical time: ${side.clocks.physical_time===null?'not declared':esc(side.clocks.physical_time)}</small></td><td>${side.result.state==='observed'?esc(side.result.value)+' '+esc(side.units):'Undefined: '+esc(side.result.reason)}</td></tr>`).join('')}</tbody></table></div>${result.operands.map((side,i)=>{const id=side.operand.run_id||side.operand.ref.run_id;return `<details><summary>${i?'Candidate':'Baseline'} · configuration, timings, memory, logs and immutable refs</summary><p>Managed Run custody · original state ${esc(side.original_run_state)}. External Project activity remains separate.</p><p>Memory: unknown · ${esc(side.memory.reason)}</p><button type="button" data-scientific-run="${esc(id)}">Open this Run's retained logs and diagnostics</button><p>Configuration ${same(result.operands[0].configuration,result.operands[1].configuration)?'identical':'differs'}; exact Model/material/Trial refs and owner timing records:</p><pre>${esc(JSON.stringify(side,null,2))}</pre></details>`;}).join('')}</div>`;
  }
  return {
    invalidate(){generation++;clear();source=null;target=null;busy=false;chosen='';loadedSession=null;},
    queueComparison(runId,baseline){pending={runId,baseline,session:session()};},
    async load(run,current){generation++;clear();source=null;target=null;busy=false;chosen='';if(!eligible(run))return;const valid=fence(current);try{const value=await read(run,valid);if(!valid())return;source=value;loadedSession=session();defaults();}catch(problem){if(valid())error=problem.message;}},
    html(run,runs){
      if(!eligible(run))return '';
      if(loadedSession!==null&&loadedSession!==session())return '<section class="scientific-comparison"><p role="status">Session changed. Refresh saved Runs to inspect current evidence.</p></section>';
      return `<section class="model-evidence scientific-comparison" aria-labelledby="scientific-heading"><h3 id="scientific-heading">Scientific baseline / candidate feedback</h3><p>The open Run is the baseline. Select exact retained checkpoints and a field point. Selection reads evidence only. Recorded progress does not certify numerical acceptance.</p>${source?`<form id="scientific-form"><div class="model-fields"><label>Candidate Run<select id="scientific-candidate"><option value="">Choose a retained candidate</option>${runs.filter(row=>eligible(row)&&row.id!==run.id).map(row=>`<option value="${esc(row.id)}" ${chosen===row.id?'selected':''}>${esc(row.graph.name)} · ${esc(row.state)} · ${esc(row.id)}</option>`).join('')}</select></label><label>Baseline checkpoint<select id="scientific-checkpoint">${checkpoints(source.evidence,selected.checkpoint)}</select></label>${target?`<label>Candidate checkpoint<select id="scientific-other">${checkpoints(target.evidence,selected.other)}</select></label>`:''}<label>Declared scalar metric<select id="scientific-metric">${source.evidence.metric_definitions.map(row=>`<option value="${esc(row.id)}" ${row.id===selected.metric?'selected':''}>${esc(row.id)} · ${esc(row.units)} · ${esc(row.direction)}</option>`).join('')}</select></label><label>Declared field<select id="scientific-field">${[...new Set(source.evidence.fields.map(row=>row.field_id))].map(id=>`<option value="${esc(id)}" ${id===selected.field?'selected':''}>${esc(id)}</option>`).join('')}</select></label>${['x','y','z'].map(axis=>`<label>Point ${axis.toUpperCase()}<input id="scientific-${axis}" type="number" min="0" max="127" step="1" required value="${selected[axis]}"></label>`).join('')}<label>Mode<select id="scientific-mode"><option value="paired" ${selected.mode==='paired'?'selected':''}>Paired diagnostics</option><option value="side_by_side" ${selected.mode==='side_by_side'?'selected':''}>Side by side</option></select></label></div><button id="scientific-compare" ${busy||!target?'disabled':''}>Compare exact retained evidence</button></form>`:''}<p role="status">${busy?'Reading exact evidence; previous values cleared.':esc(error)}</p>${resultHTML()}</section>`;
    },
    bind(root,run,runs,rerender,current,openRun){
      if(!eligible(run))return;
      const render=()=>{const focus=document.activeElement?.id;rerender();if(focus)root.querySelector('#'+CSS.escape(focus))?.focus({preventScroll:true});};
      root.querySelector('#scientific-candidate')?.addEventListener('change',async event=>{
        chosen=event.target.value;target=null;clear();const valid=fence(current);busy=!!chosen;render();if(!chosen)return;
        try{const detail=await api('runs/'+enc(chosen));if(!valid())return;const value=await read(detail,valid);if(!valid())return;target=value;selected.other=target.evidence.checkpoint_index.entries.find(row=>row.selected)?.checkpoint.sha256||target.evidence.checkpoint_index.entries[0]?.checkpoint.sha256||'';}
        catch(problem){if(valid()){target=null;error=problem.message;}}
        finally{if(valid()){busy=false;render();}}
      });
      if(pending?.runId===run.id&&pending.session===session()&&source){const select=root.querySelector('#scientific-candidate');if(select&&[...select.options].some(row=>row.value===pending.baseline)){select.value=pending.baseline;pending=null;select.dispatchEvent(new Event('change'));}}
      for(const key of ['checkpoint','other','metric','field','x','y','z','mode'])root.querySelector('#scientific-'+key)?.addEventListener('change',event=>{selected[key]='xyz'.includes(key)?(event.target.value.trim()===''?NaN:Number(event.target.value)):event.target.value;clear();busy=false;render();});
      root.querySelector('#scientific-form')?.addEventListener('submit',async event=>{
        event.preventDefault();if(busy||!source||!target)return;clear();const valid=fence(current);busy=true;const body=request();render();
        try{if(!['x','y','z'].every(axis=>Number.isInteger(body.point[axis])&&body.point[axis]>=0&&body.point[axis]<=127)||!hash(body.selection.metric_definition_sha256)||!hash(body.selection.other_metric_definition_sha256))throw Error('Select a supported metric on both sides and bounded integer coordinates.');const value=await api('scientific-comparison',body,1);if(!valid())return;result=decode(value,body);announce('Exact retained diagnostic comparison loaded. Scientific acceptance remains unknown.');}
        catch(problem){if(valid()){result=null;error=problem.message;if([401,403].includes(problem.status)){source=null;target=null;}}}
        finally{if(valid()){busy=false;render();if(result)root.querySelector('#scientific-result')?.focus();}}
      });
      for(const button of root.querySelectorAll('[data-scientific-run]'))button.onclick=()=>{if(current())openRun(button.dataset.scientificRun);};
    },
  };
};
