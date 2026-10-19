'use strict';
window.WorkspacePhaseContracts={
  'runs.phase_timings/1':'2ccaba59a34e24203fdb873713e3607e4df8c5a942d1da508792b765a00e5da2',
  'graphs.preparation_timings/1':'94f848f833254da60a4843ca4f943e1c4fcc62d036c7be2f2b44731fb559fd17'
};
window.WorkspacePhaseTimings=function({api,render,identity=()=>window.TuldokAuth?.identity(),
  now=()=>performance.now(),schedule=setTimeout,unschedule=clearTimeout}){
  const esc=window.workspaceEscape,max=7*24*60*60*1000,
    owners={pipeline:['prepare','capture'],runs:['catalog_lock_wait','queue','launch_verification','output_validation','publication','recovery_verification','recovery_publication'],custodian:['custodian_preparation','go_wait','runtime_verification','leader_lifetime','drain']},
    reasons=['catalog_lock','capacity','preparing_material','capturing_inputs','scheduler','verifying_captures','owner_go','leader','descendants','validating_outputs','copying_outputs'];
  let epoch=0,selection=null,current=()=>false,value=null,message='',timer=null,request=null,reads=0,started=0,paused=false;
  const closed=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
  const id=v=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v),sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),natural=(v,limit)=>Number.isSafeInteger(v)&&v>=0&&v<=limit;
  const session=()=>JSON.stringify([identity()?.catalog_id,identity()?.actor_id,identity()?.credential_id]);
  function invalidate(){epoch++;if(timer!==null)unschedule(timer);timer=null;request?.abort();request=null;selection=null;value=null;message='';current=()=>false;paused=false;}
  function check(v){
    const preparation=selection.kind==='preparation',fields=preparation?['format','catalog_id','graph_id','graph_revision','actor_id','selection','observation','evidence','records']:['format','catalog_id','run_id','original_run_state','evidence','records'];
    if(!closed(v,fields)||v.catalog_id!==identity()?.catalog_id||!id(v.catalog_id)||v.format!==(preparation?'graph_preparation_timings_v1':'run_phase_timings_v1')||!Array.isArray(v.records)||v.records.length>(preparation?1:4))throw Error('Timing identity or shape differs.');
    if(preparation){
      if(v.graph_id!==selection.id||v.graph_revision!==selection.revision||v.actor_id!==identity()?.actor_id||v.selection!=='latest_actor_graph_revision_observation'||!['owner_observed','unknown_granularity'].includes(v.evidence))throw Error('Preparation observation belongs to another selection.');
      const o=v.observation;
      if((v.records.length===0)!==(o===null)||o!==null&&(!closed(o,['operation','clock_id','material_sha256'])||!['graphs.preflight_external','graphs.capture_external'].includes(o.operation)||o.clock_id!==v.records[0]?.clock_id||o.material_sha256!==null&&!sha(o.material_sha256)))throw Error('Preparation operation, clock or material differs.');
    }else if(v.run_id!==selection.id||!['queued','running','cancelling','completed','failed','cancelled','interrupted','unknown'].includes(v.original_run_state)||!['owner_observed','partial','unknown_granularity','unavailable'].includes(v.evidence))throw Error('Timing observation belongs to another Run.');
    if(v.records.length===0?!['unknown_granularity','unavailable'].includes(v.evidence):!['owner_observed','partial'].includes(v.evidence))throw Error('Timing availability contradicts its records.');
    const clocks=new Set();
    for(const r of v.records){
      if(!closed(r,['format','owner','clock_id','observed_at_ms','dropped_spans','spans'])||r.format!=='owner_phase_timings_v1'||!Object.hasOwn(owners,r.owner)||!id(r.clock_id)||clocks.has(r.clock_id)||!natural(r.observed_at_ms,Number.MAX_SAFE_INTEGER)||!natural(r.dropped_spans,2**31-1)||!Array.isArray(r.spans)||r.spans.length<1||r.spans.length>32||preparation&&r.owner!=='pipeline')throw Error('Owner timing record is invalid.');
      clocks.add(r.clock_id);const sequences=new Set();
      for(const s of r.spans){
        if(!closed(s,['sequence','phase','state','started_offset_ms','ended_offset_ms','elapsed_ms','wait_reason'])||!natural(s.sequence,2**31-1)||s.sequence===0||sequences.has(s.sequence)||!owners[r.owner].includes(s.phase)||!['open','measured','incomplete'].includes(s.state)||!natural(s.started_offset_ms,max)||!natural(s.elapsed_ms,max)||s.started_offset_ms+s.elapsed_ms>max||s.wait_reason!==null&&!reasons.includes(s.wait_reason)||s.state!=='open'&&s.wait_reason!==null||s.state==='measured'&&(!natural(s.ended_offset_ms,max)||s.ended_offset_ms-s.started_offset_ms!==s.elapsed_ms)||s.state!=='measured'&&s.ended_offset_ms!==null||preparation&&s.phase!==(v.observation.operation==='graphs.preflight_external'?'prepare':'capture'))throw Error('Owner phase duration or wait is inconsistent.');
        sequences.add(s.sequence);
      }
    }
    return structuredClone(v);
  }
  async function refresh(){
    if(!selection||request)return;
    const own=epoch,credential=session(),valid=()=>own===epoch&&credential===session()&&current();
    if(!valid())return;
    if(timer!==null)unschedule(timer);timer=null;
    if(reads>=30||now()-started>=75000){paused=true;render();return;}
    reads++;const selected=selection,controller=new AbortController();request=controller;
    try{
      const route=selected.kind==='preparation'?'graphs/'+encodeURIComponent(selected.id)+'/preparation-timings':'runs/'+encodeURIComponent(selected.id)+'/phase-timings';
      const result=await api(route,selected.kind==='preparation'?{revision:selected.revision}:undefined,1,Math.min(10000,Math.max(1,75000-(now()-started))),controller.signal);
      if(!valid())return;value=check(result);message='';
    }catch(error){if(valid()){value=null;message=error.message||'Timing read unavailable.';if([401,403].includes(error.status))paused=true;}}
    finally{
      if(request===controller)request=null;
      if(valid()){
        paused=paused||reads>=30||now()-started>=75000;render();
        if(!paused)timer=schedule(()=>{timer=null;refresh();},2000);
      }
    }
  }
  function select(next,isCurrent,restartWindow=false){
    const same=selection&&JSON.stringify(next)===JSON.stringify(selection);
    current=isCurrent;
    if(same){if(restartWindow)restart();else if(!request&&timer===null&&!paused)refresh();return;}
    invalidate();current=isCurrent;selection=structuredClone(next);reads=0;started=now();refresh();
  }
  function restart(){if(!selection)return;request?.abort();request=null;epoch++;reads=0;started=now();paused=false;refresh();}
  const observedLabel=ms=>{const date=new Date(ms);return Number.isNaN(date.getTime())?String(ms)+' epoch ms':date.toISOString();};
  function html(){
    if(!selection)return '';
    const preparation=selection.kind==='preparation';
    return `<section class="phase-timing-panel" aria-labelledby="phase-${selection.kind}-title"><h3 id="phase-${selection.kind}-title">${preparation?'Preparation observations':'Run phase observations'}</h3><p role="status">${esc(message||(!value?'Waiting for current timing evidence.':value.evidence.replaceAll('_',' ')))}${paused?' Automatic timing refresh paused.':''}</p><button id="phase-${selection.kind}-refresh" type="button" data-phase-refresh>Refresh timing observations</button><p>Intervals can overlap. Different owner clocks cannot be subtracted or added. Open intervals describe the last observation; elapsed time is not extrapolated.</p>${preparation?'<p>Latest observation for this actor and graph revision; another tab can replace it. This does not establish successful preflight or execution approval.</p>':''}${value?.observation?`<p>Observed operation ${esc(value.observation.operation)} · material <code class="project-path">${esc(value.observation.material_sha256||'not yet known')}</code></p>`:''}${value?.records?.length?value.records.map(r=>`<section><h4>${esc(r.owner)} owner</h4><p>Observed at ${esc(observedLabel(r.observed_at_ms))} · clock <code class="project-path">${esc(r.clock_id)}</code>${r.dropped_spans?' · '+r.dropped_spans+' omitted spans':''}</p><div id="phase-${selection.kind}-${r.clock_id}" class="phase-timing-table" tabindex="0" role="region" aria-label="${esc(r.owner)} phase intervals"><table><thead><tr><th scope="col">Phase</th><th scope="col">State</th><th scope="col">Observed ms</th><th scope="col">Wait</th><th scope="col">Clock offsets ms</th></tr></thead><tbody>${r.spans.map(s=>`<tr><th scope="row">${esc(s.phase.replaceAll('_',' '))}</th><td>${esc(s.state)}</td><td>${s.elapsed_ms}${s.state==='incomplete'?' (observed prefix)':''}</td><td>${esc(s.wait_reason?.replaceAll('_',' ')||'—')}</td><td>${s.started_offset_ms} → ${s.ended_offset_ms===null?'unknown end':s.ended_offset_ms}</td></tr>`).join('')}</tbody></table></div></section>`).join(''):'<p>No detailed phase history is available. Existing coarse Run timestamps remain unchanged.</p>'}</section>`;
  }
  function bind(root){root.querySelector('[data-phase-refresh]')?.addEventListener('click',restart);}
  return {select,invalidate,html,bind};
};
