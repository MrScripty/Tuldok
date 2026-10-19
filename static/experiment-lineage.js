'use strict';
// Experiments owns ancestry and intent. Pipeline owns recipe edits; Runs owns evidence.
(() => {
  // Generated from agent_api.contract; checked by the lineage contract regression.
  Object.assign(window.WorkspaceModelContracts, {"studies.branch_trial": "76b6415bce7e03aef825e0a64fac690f6f2e46bcbb54fd3423979c87449b2af5", "studies.lineage": "33ee4e76a92b1481c2e6fca72b571b2f363ca18d9098acf065d025c2e27963f9", "studies.lineage_trial": "f3ec663dfa413eeeaf5ab017c28d02d0ec4f14a724c0067d07592110bf7e694a", "studies.prepare_branch": "7f4e4d8b92d86fc6f5dedf363c4ad4dbc125df914af9a18450aab0c894a13b43", "studies.record_lineage": "f8315af375e0667d4dd55e6d7decf8155ef70eaed2c19b60d7256010da9d26a4"});
  const enc=encodeURIComponent, short=value=>String(value||'').slice(0,12);
  function layout(nodes) {
    const byId=new Map(nodes.map(node=>[node.trial.id,node])), depth=new Map();
    function level(id,path=new Set()) {
      if(depth.has(id))return depth.get(id);
      if(path.has(id))throw Error('Derivation contains a cycle.');
      path=new Set(path);path.add(id);
      const parent=byId.get(id)?.lineage?.intent.parent?.trial_id;
      const value=parent&&byId.has(parent)?level(parent,path)+1:0;depth.set(id,value);return value;
    }
    const rows=new Map(), positions=new Map();
    for(const node of [...nodes].sort((a,b)=>(a.lineage?.recorded_at||'').localeCompare(b.lineage?.recorded_at||'')||a.trial.id.localeCompare(b.trial.id))) {
      const column=level(node.trial.id),row=rows.get(column)||0;rows.set(column,row+1);
      positions.set(node.trial.id,{x:24+column*300,y:24+row*180});
    }
    return {positions,width:Math.max(600,...[...positions.values()].map(p=>p.x+276)),height:Math.max(240,...[...positions.values()].map(p=>p.y+160))};
  }
  window.WorkspaceLineageLayout=layout;
  window.WorkspaceExperimentLineage=function({api,announce,getIntent,getView,getGraph,isDirty,openRecipe,openRun,compare}) {
    const esc=value=>window.workspaceEscape(value), identity=()=>window.TuldokAuth?.identity();
    let root=null,catalog=null,nodes=new Map(),revision=null,next=null,selected='',filter='',appliedFilter='',journalScope=null,message='',failed=false,
      related=[],generation=0,query=0,busy=null,zoom=1,form=null,draft={},job=null,publicationGeneration=0,publications=new Map();
    const owner=()=>identity()?.kind==='owner',canEdit=()=>identity()?.scopes?.includes('edit');
    const journalKey=()=>catalog+':'+identity()?.actor_id;
    function remember(value=job,key=journalKey()){history.replaceState({...history.state,experimentBranches:{...history.state?.experimentBranches,[key]:value}},'');}
    const requestId=value=>value?.body?.request_key||value?.record?.request_key;
    function scope(){const version=generation,intent=getIntent(),credential=identity()?.credential_id,id=catalog;
      return()=>version===generation&&intent===getIntent()&&credential===identity()?.credential_id&&id===catalog&&getView()==='pipeline';}
    function note(value,error=false){message=value;failed=error;announce(value,error);}
    function clearPublications(){publicationGeneration++;publications.clear();}
    function invalidate(clear=false){generation++;query++;busy=null;clearPublications();if(clear){nodes.clear();related=[];revision=null;next=null;selected='';form=null;draft={};job=null;journalScope=null;appliedFilter='';filter='';message='';}}
    function ref(node){return {catalog_id:catalog,trial_id:node.trial.id,material_sha256:node.trial.material.sha256};}
    async function page(append=false){
      if(busy)return;clearPublications();const current=scope(),own=++query,token={},requestedFilter=append?appliedFilter:filter;busy=token;render();
      try{
        const params=new URLSearchParams({limit:'20'});if(requestedFilter)params.set('cohort',requestedFilter);
        if(append){params.set('cursor',next);params.set('revision',revision);}
        const result=await api('experiment-lineage?'+params);if(!current()||own!==query)return;
        if(!Array.isArray(result.nodes)||result.nodes.length>20||result.nodes.some(n=>n.trial.material.catalog_id!==catalog))throw Error('The lineage page belongs to another catalog or exceeds its bound.');
        if(append&&nodes.size+result.nodes.length>100)throw Error('The visual window holds 100 trials. Filter by cohort to inspect another window.');
        if(!append){nodes=new Map();related=[];appliedFilter=requestedFilter;}
        for(const node of result.nodes)nodes.set(node.trial.id,node);
        related=[...new Map([...related,...result.related].map(item=>[item.trial_id,item])).values()].filter(item=>!nodes.has(item.trial_id));
        revision=result.revision;next=result.next_cursor;note('Loaded '+nodes.size+' trials. '+(next?'More pages are available.':'End of this catalog/cohort window.'));
      }catch(error){if(current()&&own===query){if([401,403].includes(error.status)){nodes.clear();related=[];selected='';}note(error.message,true);}}
      finally{if(current()&&own===query&&busy===token){busy=null;render();}}
    }
    async function perform(action){
      if(busy)return;const current=scope(),token={};busy=token;render();
      try{await action(current);}catch(error){if(current()){if([401,403].includes(error.status)){nodes.clear();related=[];selected='';}note(error.message,true);}}
      finally{if(current()&&busy===token){busy=null;render();}}
    }
    async function write(route,body,current,save){
      const origin=job,key=journalKey();
      const result=await api(route,body);save(result,origin);
      remember(origin,key);
      if(journalKey()===key&&requestId(job)===requestId(origin))job=origin;
      if(!current())throw Object.assign(Error('The request completed after navigation. Return with the same actor to inspect its retained result.'),{committed:true});
      return result;
    }
    function startForm(kind){
      const node=nodes.get(selected);if(!node)return;
      form=kind;const intent=node.lineage?.intent;
      draft={cohort:intent?.cohort||'',hypothesis:'',change:'',metric:intent?.target.metric_id||'loss',definition:intent?.target.metric_definition_sha256||'',direction:intent?.target.direction||'minimize',threshold:'',acceptance:'',name:'Branch of '+short(node.trial.id),newStudy:true,studyName:'Branch Study '+short(node.trial.id),ancestry:'unknown',baseline:kind==='branch'?node.trial.id:''};render();root.querySelector('#lineage-cohort')?.focus();
    }
    function intentValue(){
      const node=nodes.get(selected),baseline=nodes.get(draft.baseline);
      return {ancestry:form==='branch'?'derived':draft.ancestry,parent:form==='branch'?ref(node):null,
        baseline:baseline?ref(baseline):null,cohort:draft.cohort,hypothesis:draft.hypothesis,change_summary:draft.change,
        target:{metric_id:draft.metric,metric_definition_sha256:draft.definition||null,direction:draft.direction,threshold:draft.threshold===''?null:Number(draft.threshold),acceptance:draft.acceptance}};
    }
    function intentForm(){
      if(!form)return '';
      const field=(id,label,max=2000)=>`<label>${label}<input id="lineage-${id}" value="${esc(draft[id])}" maxlength="${max}" required></label>`;
      return `<form id="lineage-intent-form"><fieldset ${busy?'disabled':''}><legend>${form==='branch'?'Branch from retained Trial':'Record immutable Trial intent'}</legend><p>Intent is an authored hypothesis. It does not establish scientific qualification or comparison compatibility.</p><div class="lineage-fields">${field('cohort','Cohort',120)}${field('hypothesis','Hypothesis')}${field('change','Intended change')}${field('metric','Target metric ID',80)}<label>Exact metric definition SHA256 (leave blank for unknown)<input id="lineage-definition" value="${esc(draft.definition)}" pattern="[a-f0-9]{64}" maxlength="64"></label><label>Direction<select id="lineage-direction">${['minimize','maximize','target'].map(v=>`<option ${draft.direction===v?'selected':''}>${v}</option>`).join('')}</select></label><label>Target threshold (optional)<input id="lineage-threshold" type="number" step="any" value="${esc(draft.threshold)}"></label>${field('acceptance','Acceptance intent')}<label>Comparison baseline<select id="lineage-baseline"><option value="">No declared baseline</option>${[...nodes.values()].filter(n=>form==='branch'||n.trial.id!==selected).map(n=>`<option value="${esc(n.trial.id)}" ${draft.baseline===n.trial.id?'selected':''}>${esc(n.study.name)} · ${esc(short(n.trial.id))}</option>`).join('')}</select></label>${form==='record'?`<label>Ancestry<select id="lineage-ancestry"><option value="unknown">Unknown historical ancestry</option><option value="root" ${draft.ancestry==='root'?'selected':''}>Declared root</option></select></label>`:`${field('name','New recipe name',120)}${owner()?`<label><input id="lineage-new-study" type="checkbox" ${draft.newStudy?'checked':''}> Create a separate closed Study with the same finite policy and limits</label>${draft.newStudy?field('studyName','New Study name',120).replaceAll('lineage-studyName','lineage-study-name'):''}`:'<p>The branch will use the parent Study.</p>'}`}</div><div class="actions"><button id="lineage-intent-submit">${form==='branch'?'Create branch recipe':'Save immutable intent'}</button><button type="button" id="lineage-form-cancel">Cancel</button></div></fieldset></form>`;
    }
    function detail(){
      const node=nodes.get(selected);if(!node)return '<p>Select a Trial to inspect its intent, exact material and outcomes.</p>';
      const intent=node.lineage?.intent,target=intent?.target;
      const link=(label,value)=>value?`<button type="button" data-lineage-related="${esc(value.trial_id)}">${label} ${esc(short(value.trial_id))}</button>`:`<span>${label}: ${label==='Parent'?'unknown / none declared':'none declared'}</span>`;
      return `<h3 tabindex="-1">Trial ${esc(short(node.trial.id))}</h3><p>${esc(node.study.name)} · ${node.attempt_count} admitted attempts${node.runs_truncated?' (latest five shown)':''}</p><p class="lineage-hash">Exact material ${esc(node.trial.material.sha256)}</p>${intent?`<p><strong>${esc(intent.cohort)}</strong> · ${esc(intent.ancestry)} · ${esc(node.lineage.timing)}</p><dl><dt>Hypothesis</dt><dd>${esc(intent.hypothesis)}</dd><dt>Change</dt><dd>${esc(intent.change_summary)}</dd><dt>Target</dt><dd>${esc(target.metric_id)} · ${esc(target.direction)} ${target.threshold===null?'(no numeric threshold)':esc(target.threshold)}<br>${esc(target.acceptance)}<br>Metric definition: ${esc(target.metric_definition_sha256||'unknown')}</dd></dl>`:'<p>Historical ancestry and intent are unknown. No relationships are inferred.</p>'}<div class="actions">${link('Parent',intent?.parent)}${link('Baseline',intent?.baseline)}</div><div class="actions"><button type="button" id="lineage-recipe">Open current recipe (Trial retained r${node.recipe.revision})</button>${!node.lineage&&canEdit()&&!job?'<button type="button" id="lineage-record">Record intent</button>':''}${canEdit()&&!job?'<button type="button" id="lineage-branch">Branch from Trial</button>':''}</div><h4>Actual saved outcomes</h4><p>Saved status and validation summaries. Open a Run to verify its checkpoint, probes and retained evidence.</p>${node.runs.map(run=>`<div class="lineage-attempt"><button type="button" data-lineage-run="${esc(run.id)}">${esc(run.state)} · ${esc(short(run.id))}</button>${run.parent_run_id?`<p>Execution retry of Run ${esc(short(run.parent_run_id))}</p>`:''}<p>${Object.entries(run.validation).map(([k,v])=>esc(k)+': '+esc(v)).join(' · ')||'No saved validation summary.'}</p>${publicationHTML(run)}</div>`).join('')||'<p>No admitted Run. Preparation does not execute a recipe.</p>'}${intent?.baseline&&node.runs.some(r=>r.state==='completed')?'<button type="button" id="lineage-compare">Compare completed Run with baseline</button>':''}${intentForm()}`;
    }
    function publicationHTML(run){
      if(!['failed','interrupted'].includes(run.state))return '';
      const value=publications.get(run.id),continuation=value?.continuation;
      return `<div class="lineage-publication"><button type="button" data-lineage-publication="${esc(run.id)}" ${busy?'disabled':''}>Inspect saved publication status</button>${value?`<p>Original Run: <strong>${esc(value.original_run_state)}</strong> · publication: <strong>${esc(continuation?.state||'not recorded')}</strong>. Saved metadata only; current bytes require Run inspection.</p><p>${continuation?`Publication attempt ${continuation.attempt_count} of ${value.limits.max_attempts}`:`Eligibility: ${esc(value.eligibility)}`}</p>${value.original_fault?`<p>Original publication fault: ${esc(value.original_fault.code)} · ${esc(value.original_fault.message)}</p>`:''}${continuation?.result_ref?`<details><summary>Exact recovered publication Ref</summary><pre>${esc(JSON.stringify(continuation.result_ref,null,2))}</pre></details><button type="button" data-lineage-publication-run="${esc(run.id)}">Open original Run to inspect this Ref</button>`:'<p>Open the original Run for current-owner recovery or pause controls.</p>'}`:''}</div>`;
    }
    async function inspectPublication(runId){
      const node=nodes.get(selected),run=node?.runs.find(item=>item.id===runId);
      if(!run||!['failed','interrupted'].includes(run.state))return;
      const selectedTrial=selected,own=++publicationGeneration;publications.clear();
      await perform(async current=>{
        const result=await api('runs/'+enc(run.id)+'/publication',undefined,2);
        if(!current()||selected!==selectedTrial||own!==publicationGeneration)return;
        const checked=await window.WorkspacePublicationDocuments.status(result,{catalog_id:catalog,run_id:run.id,original_run_state:run.state});
        if(!current()||selected!==selectedTrial||own!==publicationGeneration)return;
        publications.set(run.id,structuredClone(checked));note('Saved publication metadata inspected for the original '+run.state+' Run. Open Runs for current byte verification.');
      });
    }
    const canClose=()=>!!job?.branch&&!busy&&!job.approvalUnknown&&(!job.prepare||!!job.trial)&&(!job.continue||!!job.run)&&(!job.admission||!!job.run);
    function jobHTML(){
      if(!job)return '';
      const result=job.branch;
      return `<section class="lineage-job"><h3>Branch workflow</h3><p>${result?`Cloned exact parent ${esc(short(result.parent.trial_id))} into recipe ${esc(short(result.graph.id))}.`:'The exact request is retained for reconciliation.'}</p>${job.trial?`<p>Prepared Trial ${esc(short(job.trial.id))}. Intent and material are immutable.</p>`:''}<div class="actions">${!result?'<button id="lineage-reconcile">Reconcile same request</button>':`<button id="lineage-open-recipe">Open cloned recipe</button>${!job.trial?'<button id="lineage-prepare">Prepare saved revision</button>':!job.run?`${owner()&&result.graph.recipe==='external_recipe'&&!job.approval?'<button id="lineage-approve">Approve exact material</button>':''}<button id="lineage-start" ${!owner()||result.graph.recipe==='external_recipe'&&!job.approval?'disabled':''}>${job.admission?'Reconcile finite admission':'Start finite trial'}</button>`:'<button id="lineage-open-run">Inspect admitted Run</button>'}`}${canClose()?'<button id="lineage-finish">Close branch workflow</button>':''}</div>${result&&!job.trial?'<p>Edit and save the cloned recipe first. Preparation captures its saved revision using the parent’s published Model. Architecture changes require a matching published Model.</p><label>Matching Model reference for architecture changes (optional JSON)<textarea id="lineage-model" rows="3"></textarea></label>':''}<p>Preparation creates no Run. Explicit admission uses the existing finite Study budget and current execution permissions.</p></section>`;
    }
    function render(){
      if(!root||getView()!=='pipeline')return;
      const focus=root.contains(document.activeElement)?document.activeElement.id:null,scroll=root.querySelector('.lineage-viewport'),position=scroll?{left:scroll.scrollLeft,top:scroll.scrollTop}:null;
      let graph;try{graph=layout([...nodes.values()]);}catch(error){graph={positions:new Map(),width:600,height:240};message=error.message;failed=true;}
      const edges=[];
      for(const node of nodes.values())for(const kind of ['parent','baseline']){
        const target=node.lineage?.intent[kind]?.trial_id,from=graph.positions.get(target),to=graph.positions.get(node.trial.id);
        if(from&&to)edges.push(`<path class="${kind}" d="M${from.x+252},${from.y+72+(kind==='baseline'?10:0)} C${from.x+285},${from.y+72} ${to.x-30},${to.y+72} ${to.x},${to.y+72}"/>`);
      }
      root.innerHTML=`<section class="panel panel-pad lineage-panel" aria-labelledby="lineage-heading"><span class="eyebrow">EXPERIMENTS · ACROSS STUDIES</span><h2 id="lineage-heading">Experiment progression</h2><p>Follow declared derivation, comparison baselines and actual outcomes. Solid edges show derivation; dashed edges show baselines. Execution retries remain inside their Trial.</p><form id="lineage-filter-form"><label>Cohort (exact match; blank shows all)<input id="lineage-filter" maxlength="120" value="${esc(filter)}" ${busy?'disabled':''}></label><button id="lineage-refresh" ${busy?'disabled':''}>Refresh graph</button></form><p role="status" class="${failed?'error-panel':''}">${esc(message)}</p><div class="actions"><button id="lineage-zoom-out" aria-label="Zoom graph out">−</button><button id="lineage-zoom-in" aria-label="Zoom graph in">+</button><button id="lineage-zoom-reset">Reset zoom</button><span>${Math.round(zoom*100)}%</span></div><div class="lineage-viewport" tabindex="0" aria-label="Experiment graph; scroll horizontally and vertically to explore"><div style="width:${graph.width*zoom}px;height:${graph.height*zoom}px"><div class="lineage-canvas" style="width:${graph.width}px;height:${graph.height}px;transform:scale(${zoom})"><svg width="${graph.width}" height="${graph.height}" aria-hidden="true">${edges.join('')}</svg>${[...nodes.values()].map(node=>{const p=graph.positions.get(node.trial.id);if(!p)return '';const intent=node.lineage?.intent,run=node.runs[0];return `<button id="lineage-node-${esc(node.trial.id)}" type="button" data-lineage-node="${esc(node.trial.id)}" class="lineage-node" aria-pressed="${selected===node.trial.id}" style="left:${p.x}px;top:${p.y}px"><strong>${esc(node.study.name)}</strong><span>${esc(short(node.trial.id))} · ${esc(intent?.ancestry||'ancestry unknown')}</span><span>${esc(intent?.change_summary||'Intent not recorded')}</span><span>${esc(run?.state||'prepared')} · ${node.attempt_count} attempts</span>${intent?`<span>Target: ${esc(intent.target.metric_id)} ${esc(intent.target.direction)}</span>`:''}</button>`;}).join('')}</div></div></div><p>${nodes.size} trials loaded${appliedFilter?' · applied cohort: '+esc(appliedFilter):' · all cohorts'}${next?' · more pages available':''}. ${related.length} related identities are outside this loaded window. Layout order does not imply chronology.</p><div class="actions">${next?`<button id="lineage-more" ${busy||nodes.size>=100?'disabled':''}>Load next 20 trials</button>`:''}${related.map(item=>`<button type="button" data-lineage-related="${esc(item.trial_id)}">Load related ${esc(short(item.trial_id))}</button>`).join('')}</div><div id="lineage-detail">${detail()}</div>${jobHTML()}</section>`;
      bind();if(position){const viewport=root.querySelector('.lineage-viewport');viewport.scrollLeft=position.left;viewport.scrollTop=position.top;}
      if(focus)root.querySelector('#'+CSS.escape(focus))?.focus({preventScroll:true});
    }
    function bind(){
      const on=(id,event,handler)=>root.querySelector('#'+id)?.addEventListener(event,handler);
      on('lineage-filter','input',event=>filter=event.target.value);
      on('lineage-filter-form','submit',event=>{event.preventDefault();page();});on('lineage-more','click',()=>page(true));
      for(const button of root.querySelectorAll('[data-lineage-node]'))button.onclick=()=>{if(busy)return;selected=button.dataset.lineageNode;form=null;clearPublications();render();};
      for(const button of root.querySelectorAll('[data-lineage-related]'))button.onclick=()=>perform(async current=>{
        const id=button.dataset.lineageRelated;if(!nodes.has(id)){if(nodes.size>=100)throw Error('Refine the cohort before loading more than 100 trials.');const node=await api('experiment-lineage/'+enc(id));if(!current())return;nodes.set(id,node);}selected=id;form=null;clearPublications();
      });
      for(const [id,delta] of [['lineage-zoom-in',0.2],['lineage-zoom-out',-0.2],['lineage-zoom-reset',null]])on(id,'click',()=>{zoom=delta===null?1:Math.min(1.6,Math.max(0.6,zoom+delta));render();});
      on('lineage-record','click',()=>startForm('record'));on('lineage-branch','click',()=>startForm('branch'));on('lineage-form-cancel','click',()=>{form=null;render();});
      for(const [id,key] of [['cohort','cohort'],['hypothesis','hypothesis'],['change','change'],['metric','metric'],['definition','definition'],['direction','direction'],['threshold','threshold'],['acceptance','acceptance'],['name','name'],['study-name','studyName'],['ancestry','ancestry'],['baseline','baseline']])on('lineage-'+id,['direction','ancestry','baseline'].includes(id)?'change':'input',event=>draft[key]=event.target.value);
      on('lineage-new-study','change',event=>{draft.newStudy=event.target.checked;render();});
      on('lineage-intent-form','submit',event=>{event.preventDefault();const kind=form,intent=intentValue(),node=nodes.get(selected);
        if(kind==='branch'){job={body:{request_key:crypto.randomUUID(),name:draft.name,intent,...(owner()&&draft.newStudy?{new_study_name:draft.studyName}:{})}};remember();}
        else{job={record:{request_key:crypto.randomUUID(),revision,trial:ref(node),intent}};remember();}
        form=null;perform(current=>commitIntent(current));
      });
      on('lineage-reconcile','click',()=>perform(current=>commitIntent(current)));
      on('lineage-recipe','click',()=>perform(current=>openRecipe(nodes.get(selected).recipe.id,current)));
      for(const button of root.querySelectorAll('[data-lineage-publication]'))button.onclick=()=>inspectPublication(button.dataset.lineagePublication);
      for(const button of root.querySelectorAll('[data-lineage-publication-run]'))button.onclick=()=>perform(current=>openRun(button.dataset.lineagePublicationRun,current));
      for(const button of root.querySelectorAll('[data-lineage-run]'))button.onclick=()=>perform(current=>openRun(button.dataset.lineageRun,current));
      on('lineage-compare','click',()=>perform(async current=>{
        const node=nodes.get(selected),baseline=await api('experiment-lineage/'+enc(node.lineage.intent.baseline.trial_id));if(!current())return;
        const left=node.runs.find(run=>run.state==='completed'),right=baseline.runs.find(run=>run.state==='completed');
        if(!right)throw Error('No completed baseline Run in its latest five attempts. Open its retained Study for older attempts.');
        await compare(left.id,right.id,current);
      }));
      on('lineage-open-recipe','click',()=>perform(current=>openRecipe(job.branch.graph.id,current)));
      on('lineage-model','input',event=>{job.modelText=event.target.value;remember();});
      const model=root.querySelector('#lineage-model');if(model)model.value=job.modelText||'';
      on('lineage-prepare','click',()=>perform(async current=>{
        if(isDirty())throw Error('Save or discard recipe edits before capturing the branch.');
        if(!job.prepare){const graph=await api('graphs/'+enc(job.branch.graph.id)),state=await api('studies/'+enc(job.branch.study_id));if(!current())return;
          job.prepare={request_key:crypto.randomUUID(),revision:state.study.revision,branch_request_key:job.body.request_key,graph_revision:graph.revision,replicate:0,...(job.modelText?{model:JSON.parse(job.modelText)}:{})};remember();}
        const origin=job,key=journalKey();
        try{await write('studies/'+enc(origin.branch.study_id)+'/prepare-branch',origin.prepare,current,(result,entry)=>entry.trial=result);}
        catch(error){if([400,404,409].includes(error.status)&&['invalid','stale','unsupported','unavailable'].includes(error.code)){origin.prepare=null;remember(origin,key);}throw error;}
        note('Branch Trial prepared with immutable intent. No Run was admitted.');
        const node=await api('experiment-lineage/'+enc(job.trial.id));if(current()){nodes.set(node.trial.id,node);selected=node.trial.id;}
      }));
      on('lineage-approve','click',()=>perform(async current=>{
        if(job.approvalUnknown)throw Error('Approval acknowledgement is uncertain. Inspect execution grants before issuing another approval.');
        const origin=job,key=journalKey();
        try{await write('studies/'+enc(job.branch.study_id)+'/approve',{trial_id:job.trial.id,expected_material_sha256:job.trial.material.sha256,consumer_actor_id:identity().actor_id},current,(result,entry)=>entry.approval=result);}
        catch(error){if(!error.committed&&(!error.status||error.status>=500)){origin.approvalUnknown=true;remember(origin,key);}throw error;}
      }));
      on('lineage-start','click',()=>perform(async current=>{
        if(!owner())throw Error('An owner must explicitly admit this branch.');
        if(!job.admission){let state=await api('studies/'+enc(job.branch.study_id));if(!current())return;
          if(!state.study.open){if(!job.continue){job.continue={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch};remember();}await write('studies/'+enc(job.branch.study_id)+'/continue',job.continue,current,()=>{});state=await api('studies/'+enc(job.branch.study_id));if(!current())return;}
          job.admission={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch,trial_id:job.trial.id,...(job.approval?{approval_id:job.approval.id}:{})};remember();}
        // A postcommit Run read may fail even with a 4xx. Preserve the exact
        // admission body until its durable receipt is explicitly reconciled.
        await write('studies/'+enc(job.branch.study_id)+'/admit',job.admission,current,(result,entry)=>entry.run=result.run);
        note('Finite branch attempt admitted. Inspect its actual Run evidence.');await openRun(job.run.id,current);
      }));
      on('lineage-open-run','click',()=>perform(current=>openRun(job.run.id,current)));
      on('lineage-finish','click',()=>{if(!canClose())return;job=null;remember();render();});
    }
    async function commitIntent(current){
      if(job.record){await write('experiment-lineage',job.record,current,(result,entry)=>entry.recorded=result);const node=await api('experiment-lineage/'+enc(job.record.trial.trial_id));if(!current())return;nodes.set(node.trial.id,node);revision=null;next=null;job=null;remember();note('Immutable intent recorded; historical Trial bytes are unchanged.');}
      else{await write('experiment-lineage/branch',job.body,current,(result,entry)=>entry.branch=result);note('Retained Trial recipe cloned. Edit and save the branch, then prepare it explicitly.');}
    }
    return {
      mount(node,context){root=node;if(catalog!==context?.dataset_id){invalidate(true);catalog=context?.dataset_id;}if(journalScope!==journalKey()){journalScope=journalKey();job=history.state?.experimentBranches?.[journalScope]||null;}render();if(catalog&&!revision&&!busy)page();},
      invalidate,
      sessionChanged(){invalidate(true);render();},
    };
  };
})();
