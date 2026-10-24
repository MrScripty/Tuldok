'use strict';
// The native host owns binding/checkpoint/credential changes and exact reads.
// This controller owns source choice, its finite graph window and pending reads.
(() => {
  const id=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
  const natural=value=>Number.isSafeInteger(value)&&value>=0;
  const short=value=>String(value).slice(0,12);
  const key=(origin,trial)=>origin+'.'+trial;
  const element=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
  window.ProjectExperimentProgression=function({root,read,inspectStudy,inspectTrial,inspectRun,onContextFocusLost=()=>{}}) {
    root.innerHTML='<h2>Experiment progression</h2><p>Explore recorded relationships across saved Studies. Solid edges show derivation; dashed edges show comparison baselines. Run states are saved outcomes.</p><div class="actions"><button type="button" id="project-progression-origins">Load history sources</button><button type="button" id="project-progression-origins-more" hidden>More history sources</button></div><form id="project-progression-form"><label>History source<select id="project-progression-origin"><option value="">Choose a history source</option></select></label><label>Recorded cohort (optional exact match)<input id="project-progression-cohort" maxlength="120"></label><button id="project-progression-load">Load graph</button></form><p id="project-progression-status" role="status" aria-live="polite"></p><div class="actions"><button type="button" id="project-progression-zoom-out" aria-label="Zoom experiment graph out">−</button><button type="button" id="project-progression-zoom-in" aria-label="Zoom experiment graph in">+</button><button type="button" id="project-progression-zoom-reset">Reset zoom</button><button type="button" id="project-progression-more" hidden>Load next 20 Trials</button></div><div id="project-progression-graph"></div><p id="project-progression-summary"></p><section id="project-progression-detail" aria-label="Selected Trial"></section>';
    const $=name=>root.querySelector('#project-progression-'+name);
    let context=null,generation=0,pending=null,busy=false,origins=[],originsNext=0,originsTotal=0;
    let nodes=new Map(),origin='',appliedCohort=null,next=0,total=0,related=new Map(),selected='',zoom=1;
    function clearGraph(){nodes.clear();related.clear();origin='';appliedCohort=null;next=0;total=0;selected='';$('graph').replaceChildren();$('detail').replaceChildren();$('summary').textContent='';}
    function controls(){
      const enabled=!!context?.enabled;
      $('origins').disabled=!enabled||busy;$('origins-more').disabled=!enabled||busy;
      $('origins-more').hidden=originsNext>=originsTotal;
      $('origin').disabled=!enabled||busy||!origins.length;$('cohort').disabled=!enabled||busy;
      $('load').disabled=!enabled||busy||!$('origin').value;
      $('more').hidden=next>=total;$('more').disabled=!enabled||busy||nodes.size>=100;
      for(const name of ['zoom-out','zoom-in','zoom-reset'])$(name).disabled=!enabled||busy||!nodes.size;
      for(const button of root.querySelectorAll('[data-lineage-node],#project-progression-detail button'))button.disabled=!enabled||busy;
      root.setAttribute('aria-busy',String(busy));
    }
    function reset(){
      ++generation;pending?.abort();pending=null;busy=false;clearGraph();origins=[];originsNext=0;originsTotal=0;
      const option=element('option','Choose a history source');option.value='';$('origin').replaceChildren(option);
      $('cohort').value='';$('status').textContent='';controls();
    }
    async function perform(work){
      if(!context?.enabled||busy)return;
      const ticket=++generation,authority=context.key;pending=new AbortController();const signal=pending.signal;busy=true;controls();
      const active=()=>ticket===generation&&context?.key===authority&&!signal.aborted;
      try{await work(active,signal);}catch(error){if(active()){const ownedFocus=root.contains(document.activeElement);reset();$('status').textContent=error.message;if(ownedFocus)$('origins').focus();}}
      finally{if(active()){busy=false;pending=null;controls();}}
    }
    function page(value,offset,limit,items){
      if(!value||value.offset!==offset||value.limit!==limit||!natural(value.total)||!Array.isArray(items)||items.length!==Math.min(limit,Math.max(0,value.total-offset)))throw Error('History page differs from its selected continuation.');
    }
    async function loadOrigins(append=false){
      return perform(async(active,signal)=>{
        const offset=append?originsNext:0,value=await read('progression_origins',{offset,limit:40},signal);if(!active())return;
        page(value,offset,40,value.items);
        const seen=new Set(append?origins.map(item=>item.origin_catalog_id):[]);
        for(const item of value.items){if(!id(item.origin_catalog_id)||seen.has(item.origin_catalog_id)||!natural(item.study_count)||!natural(item.trial_count))throw Error('Invalid history source.');seen.add(item.origin_catalog_id);}
        if(!append){clearGraph();origins=[];const option=element('option','Choose a history source');option.value='';$('origin').replaceChildren(option);}
        origins.push(...value.items);originsNext=offset+value.items.length;originsTotal=value.total;
        for(const item of value.items){const option=element('option',(item.origin_catalog_id===context.project_id?'This project':'Imported catalog '+short(item.origin_catalog_id))+' · '+item.study_count+' Studies · '+item.trial_count+' Trials');option.value=item.origin_catalog_id;$('origin').append(option);}
        $('status').textContent=origins.length?'Choose a history source to load its Trials.':'No recorded Study history in this project.';
        if(!append)$('origin').focus();
      });
    }
    function validNode(node,source){
      const trial=node?.trial,lineage=node?.lineage;
      if(!id(trial?.id)||!id(trial?.study_id)||trial.study_id!==node.study?.id||typeof node.study.name!=='string'||
         trial.material?.catalog_id!==source||!natural(node.attempt_count)||!Array.isArray(node.runs)||node.runs.length>5||node.runs.length>node.attempt_count||node.runs_truncated!==(node.attempt_count>node.runs.length)||
         node.runs.some(run=>!id(run.id)||typeof run.state!=='string'||Object.hasOwn(run,'validation')))throw Error('Invalid saved Trial overview.');
      if(lineage!==null&&(lineage?.trial?.catalog_id!==source||lineage.trial.trial_id!==trial.id||lineage.trial.material_sha256!==trial.material.sha256))throw Error('Trial ancestry belongs to different material.');
    }
    async function loadGraph(append=false){
      const requestedOrigin=append?origin:$('origin').value,cohort=append?appliedCohort:($('cohort').value||null),offset=append?next:0;
      if(!id(requestedOrigin)||append&&nodes.size>=100)return;
      return perform(async(active,signal)=>{
        const args={origin_catalog_id:requestedOrigin,offset,limit:20,...(cohort===null?{}:{cohort})};
        const value=await read('progression',args,signal);if(!active())return;
        page(value,offset,20,value.nodes);
        if(value.origin_catalog_id!==requestedOrigin||value.evidence!=='saved_metadata_only'||value.historical!==true||value.execution_available!==false||value.cohort!==cohort||!Array.isArray(value.related)||value.related.length>40)throw Error('History response differs from the selected source.');
        const seen=new Set(append?nodes.keys():[]);
        for(const node of value.nodes){validNode(node,requestedOrigin);const identity=key(requestedOrigin,node.trial.id);if(seen.has(identity))throw Error('Duplicate Trial in history page.');seen.add(identity);}
        for(const ref of value.related)if(!id(ref.catalog_id)||!id(ref.trial_id)||typeof ref.material_sha256!=='string'||!/^[a-f0-9]{64}$/.test(ref.material_sha256))throw Error('Invalid related Trial identity.');
        if(seen.size>100)throw Error('The graph window holds 100 Trials; choose a recorded cohort for another window.');
        if(!append){clearGraph();origin=requestedOrigin;appliedCohort=cohort;}
        for(const node of value.nodes)nodes.set(key(origin,node.trial.id),structuredClone(node));
        for(const ref of value.related)related.set(key(ref.catalog_id,ref.trial_id),structuredClone(ref));
        next=offset+value.nodes.length;total=value.total;render();
        $('status').textContent=nodes.size?'Loaded '+nodes.size+' recorded Trials.':'No Trials match this source and recorded cohort.';
      });
    }
    function detail(){
      const node=nodes.get(selected);$('detail').replaceChildren();if(!node)return;
      const add=(tag,text)=>{const e=element(tag,text);$('detail').append(e);return e;};
      add('h3','Trial '+short(node.trial.id));add('p',node.study.name);
      if(node.lineage){const intent=node.lineage.intent;add('p',intent.hypothesis);add('p',intent.change_summary);}
      else add('p','Historical ancestry and intent are unknown. No relationships are inferred.');
      for(const kind of ['parent','baseline']){
        const ref=node.lineage?.intent[kind],label=kind==='parent'?'Parent':'Comparison baseline';
        if(ref){const button=add('button',label+' Trial '+short(ref.trial_id));button.type='button';button.onclick=()=>inspectTrial(ref.catalog_id,ref.trial_id);}
        else add('p',label+': none declared.');
      }
      for(const [label,inspect,identity] of [['Inspect Study',inspectStudy,node.study.id],['Inspect Trial',inspectTrial,node.trial.id]]){const button=add('button',label);button.type='button';button.onclick=()=>inspect(origin,identity);}
      add('h4','Saved Run outcomes');
      for(const run of node.runs){const button=add('button','Inspect Run '+short(run.id)+' · saved '+run.state);button.type='button';button.onclick=()=>inspectRun(origin,run.id);}
      if(!node.attempt_count)add('p','No recorded admitted attempt.');
      if(node.runs_truncated)add('p','Showing five of '+node.attempt_count+' recorded attempts.');
      const facts=add('details'),summary=element('summary','Exact original references and recorded intent');facts.append(summary,element('pre',JSON.stringify({origin_catalog_id:origin,trial:node.trial,lineage:node.lineage},null,2)));
    }
    function render(){
      const focused=$('graph').contains(document.activeElement)?document.activeElement.id:null;
      const graph=window.WorkspaceExperimentGraph.render([...nodes.values()].map(node=>({id:key(origin,node.trial.id),title:node.study.name,recordedAt:node.lineage?.recorded_at||'',
        parent:node.lineage?.intent.parent?key(node.lineage.intent.parent.catalog_id,node.lineage.intent.parent.trial_id):null,
        baseline:node.lineage?.intent.baseline?key(node.lineage.intent.baseline.catalog_id,node.lineage.intent.baseline.trial_id):null,
        lines:[short(node.trial.id)+' · '+(node.lineage?.intent.ancestry||'ancestry unknown'),node.lineage?.intent.change_summary||'Intent not recorded',(node.runs[0]?.state||'prepared')+' · '+node.attempt_count+' recorded attempts']})),{selected,zoom});
      $('graph').innerHTML=graph.html;
      for(const button of $('graph').querySelectorAll('[data-lineage-node]')){button.disabled=busy;button.onclick=()=>{selected=button.dataset.lineageNode;render();$('status').textContent='Selected Trial '+short(nodes.get(selected).trial.id)+'.';};}
      const outside=[...related.keys()].filter(identity=>!nodes.has(identity)).length;
      $('summary').textContent=nodes.size+' of '+total+' Trials loaded · '+(appliedCohort===null?'all recorded cohorts':'applied cohort: '+appliedCohort)+' · '+outside+' related identities outside this graph window.';
      detail();if(focused)$('graph').querySelector('#'+CSS.escape(focused))?.focus({preventScroll:true});
    }
    $('origins').onclick=()=>loadOrigins();$('origins-more').onclick=()=>loadOrigins(true);
    $('form').onsubmit=event=>{event.preventDefault();loadGraph();};$('more').onclick=()=>loadGraph(true);
    $('origin').onchange=()=>{++generation;pending?.abort();pending=null;busy=false;clearGraph();$('status').textContent='Load the selected history source.';controls();};
    for(const [name,delta] of [['zoom-in',0.2],['zoom-out',-0.2],['zoom-reset',null]])$(name).onclick=()=>{zoom=delta===null?1:Math.max(0.6,Math.min(1.6,zoom+delta));render();};
    return {setContext(value){if(value.key!==context?.key){const ownedFocus=root.contains(document.activeElement);context=value;reset();if(ownedFocus)onContextFocusLost();}else context=value;root.hidden=!value.enabled;controls();},clear(){context=null;reset();root.hidden=true;}};
  };
})();
