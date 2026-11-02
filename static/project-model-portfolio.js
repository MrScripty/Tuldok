'use strict';
// Authored organization is a retained note, not Trial lineage or qualification.
// This module owns its document contract, finite view and cancellable reads.
(() => {
  const fields=['method','purpose','experiment','outcome','lesson','reproduction'];
  const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&
    Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
  const text=(value,limit)=>typeof value==='string'&&value.length>0&&value.length<=limit;
  const identity=value=>text(value,160)&&/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(value);
  const sha=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  const natural=value=>Number.isSafeInteger(value)&&value>=0;
  function fail(message,code='invalid'){throw Object.assign(Error(message),{code});}
  function noteRef(value){
    if(!exact(value,['file_id','path','revision','sha256'])||!sha(value.file_id)||!sha(value.sha256)||
       !natural(value.revision)||value.revision<1||!text(value.path,512)||!value.path.startsWith('notes/')||
       value.path.split('/').some(part=>!part||part==='.'||part==='..'))fail('Invalid captured model-note reference.');
  }
  function decode(raw){
    if(typeof raw!=='string'||new TextEncoder().encode(raw).length>1048576)fail('Organization note exceeds its retained text limit.');
    let value;try{value=JSON.parse(raw);}catch{fail('Organization note is not valid JSON.');}
    if(value?.format!=='project_model_portfolio_v1')fail('Unsupported model-organization document format.','unsupported');
    if(!exact(value,['format','project_id','title','description','authorship','groups','models','relationships'])||
       !/^[a-f0-9]{32}$/.test(value.project_id)||!text(value.title,200)||!text(value.description,8000)||
       value.authorship!=='retrospective'||!Array.isArray(value.groups)||value.groups.length>64||
       !Array.isArray(value.models)||!value.models.length||value.models.length>1000||
       !Array.isArray(value.relationships)||value.relationships.length>2000)fail('Invalid model-organization document.');
    const groups=new Map(),models=new Map();
    for(const group of value.groups){
      if(!exact(group,['id','label','parent','description'])||!identity(group.id)||groups.has(group.id)||
         !text(group.label,200)||!text(group.description,8000)||group.parent!==null&&!identity(group.parent))fail('Invalid or duplicate organization group.');
      groups.set(group.id,group);
    }
    for(const group of groups.values()){
      const visited=new Set([group.id]);let parent=group.parent;
      while(parent!==null){if(!groups.has(parent))fail('Organization group parent is unavailable.');
        if(visited.has(parent))fail('Organization grouping contains a cycle.');visited.add(parent);parent=groups.get(parent).parent;}
    }
    for(const model of value.models){
      if(!exact(model,['id','label','group_id','aliases','review','card','summary'])||!identity(model.id)||models.has(model.id)||
         !text(model.label,500)||!groups.has(model.group_id)||!Array.isArray(model.aliases)||model.aliases.length>128||
         new Set(model.aliases).size!==model.aliases.length||model.aliases.some(alias=>!text(alias,500))||
         !['source_reviewed','review_pending'].includes(model.review))fail('Invalid or duplicate organized model.');
      noteRef(model.card);
      if(model.review==='source_reviewed'){
        if(!exact(model.summary,fields)||fields.some(field=>!text(model.summary[field],16384)))fail('Reviewed model requires all six authored summary fields.');
      }else if(model.summary!==null)fail('Pending review cannot expose a reviewed summary.');
      models.set(model.id,model);
    }
    const pairs=new Set();
    for(const relation of value.relationships){
      if(!exact(relation,['from','to','kind','explanation','evidence_model','excerpt'])||
         !models.has(relation.from)||!models.has(relation.to)||relation.from===relation.to||
         !['comparison','parameter_derivation'].includes(relation.kind)||!text(relation.explanation,8000)||
         !models.has(relation.evidence_model)||!text(relation.excerpt,16384))fail('Invalid authored model relationship.');
      const key=JSON.stringify([relation.from,relation.to,relation.kind]);if(pairs.has(key))fail('Duplicate authored model relationship.');pairs.add(key);
    }
    const parents=new Map(),complete=new Set(),visiting=new Set();
    for(const relation of value.relationships)if(relation.kind==='parameter_derivation'){
      if(!parents.has(relation.from))parents.set(relation.from,[]);parents.get(relation.from).push(relation.to);
    }
    function visit(id){if(complete.has(id))return;if(visiting.has(id))fail('Authored parameter derivation contains a cycle.');
      visiting.add(id);for(const parent of parents.get(id)||[])visit(parent);visiting.delete(id);complete.add(id);}
    for(const id of parents.keys())visit(id);
    return value;
  }
  function checkCard(document,model,result){
    const ref=model.card,version=result?.version;
    if(result?.project_id!==document.project_id||result.id!==ref.file_id||result.path!==ref.path||result.kind!=='note'||
       version?.deleted===true||version?.revision!==ref.revision||version.sha256!==ref.sha256||typeof version.text!=='string')
      fail('Model card differs from its exact retained organization reference.');
    if(model.summary&&fields.some(field=>!version.text.includes(model.summary[field])))fail('Authored summary differs from the captured model card.');
    for(const relation of document.relationships)if(relation.evidence_model===model.id&&!version.text.includes(relation.excerpt))
      fail('Authored relationship excerpt differs from its captured model card.');
    return version.text;
  }
  window.ProjectModelPortfolioDocument=Object.freeze({decode,checkCard});
  const node=(tag,value)=>{const element=document.createElement(tag);if(value!==undefined)element.textContent=value;return element;};
  window.ProjectModelPortfolio=function({root,read,onContextFocusLost=()=>{}}){
    root.innerHTML='<h2>Authored model organization</h2><p>Browse a retained guide to models and their methods. Grouping and retrospective comparison notes are separate from recorded Trial ancestry and scientific qualification.</p><div class="actions"><button type="button" id="project-portfolio-notes">Find organization notes</button><button type="button" id="project-portfolio-notes-more" hidden>Next note page</button></div><p id="project-portfolio-note-count"></p><form id="project-portfolio-source-form"><label>Adopted organization note<select id="project-portfolio-note"></select></label><button id="project-portfolio-load">Load organization</button></form><p id="project-portfolio-status" role="status" aria-live="polite" tabindex="-1"></p><div id="project-portfolio-content" hidden><h3 id="project-portfolio-title"></h3><p id="project-portfolio-description"></p><p id="project-portfolio-source"></p><form id="project-portfolio-filter-form"><label>Method group<select id="project-portfolio-group"><option value="">All groups</option></select></label><label>Model name or alias<input id="project-portfolio-search" maxlength="500" type="search"></label><label>Source review<select id="project-portfolio-review"><option value="">All models</option><option value="source_reviewed">Source reviewed</option><option value="review_pending">Review pending</option></select></label><button>Apply filters</button></form><p id="project-portfolio-count"></p><p>Solid edges show authored grouping only. Model relationships and their source excerpts are listed with the selected model.</p><div id="project-portfolio-graph"></div><div class="actions"><button type="button" id="project-portfolio-prev">Previous models</button><button type="button" id="project-portfolio-next">Next models</button></div><section id="project-portfolio-detail" aria-label="Selected model summary"></section></div>';
    const $=name=>root.querySelector('#project-portfolio-'+name);
    let context=null,generation=0,pending=null,busy=false,notes=new Map(),noteOffset=0,noteTotal=0;
    let guide=null,groups=new Map(),models=new Map(),applied={group:'',search:'',review:''},offset=0,selected='';
    const pageSize=20;
    function controls(){
      const enabled=!!context?.enabled;
      for(const name of ['notes','notes-more','note','load','group','search','review','prev','next'])$(name).disabled=!enabled||busy;
      $('note').disabled ||= !notes.size;$('load').disabled ||= !notes.has($('note').value);
      $('notes-more').hidden=noteOffset>=noteTotal;$('notes-more').disabled ||= noteOffset>=noteTotal;
      $('prev').disabled ||= !guide||offset===0;$('next').disabled ||= !guide||offset+pageSize>=filtered().length;
      for(const button of root.querySelectorAll('#project-portfolio-filter-form button,[data-lineage-node],#project-portfolio-detail button'))button.disabled=!enabled||busy;
      root.setAttribute('aria-busy',String(busy));
    }
    function clearGuide(){guide=null;groups.clear();models.clear();selected='';offset=0;applied={group:'',search:'',review:''};$('content').hidden=true;$('detail').replaceChildren();$('graph').replaceChildren();$('search').value='';$('review').value='';$('group').replaceChildren();}
    function reset(){++generation;pending?.abort();pending=null;busy=false;notes.clear();noteOffset=noteTotal=0;$('note').replaceChildren();$('note-count').textContent='';$('status').textContent='';clearGuide();controls();}
    async function perform(work){
      if(!context?.enabled||busy)return;
      const ticket=++generation,key=context.key;pending=new AbortController();const signal=pending.signal;busy=true;controls();
      const active=()=>ticket===generation&&context?.enabled&&context.key===key&&!signal.aborted;
      try{await work(active,signal);}catch(error){if(active()){$('detail').replaceChildren();$('status').textContent=(error.code?error.code+': ':'')+error.message;$('status').focus();}}
      finally{if(active()){busy=false;pending=null;controls();}}
    }
    async function findNotes(more=false){
      return perform(async(active,signal)=>{
        const requested=more?noteOffset:0,value=await read('files_inspect',{offset:requested,limit:40},signal);if(!active())return;
        if(value?.offset!==requested||value.limit!==40||!natural(value.total)||!Array.isArray(value.items)||
           value.items.length!==Math.min(40,Math.max(0,value.total-requested)))fail('Organization note page differs from its continuation.');
        if(!more){clearGuide();notes.clear();$('note').replaceChildren();}
        for(const item of value.items)if(item.kind==='note'&&item.path?.endsWith('.portfolio.json')){
          if(!sha(item.id)||!natural(item.revision)||item.revision<1||!sha(item.expected_sha256)||notes.has(item.id))fail('Invalid organization note selection.');
          notes.set(item.id,structuredClone(item));const option=node('option',item.path+' · revision '+item.revision);option.value=item.id;$('note').append(option);
        }
        noteOffset=requested+value.items.length;noteTotal=value.total;
        $('note-count').textContent=`${notes.size} organization notes found; inspected ${noteOffset} of ${noteTotal} adopted files.`;
        $('status').textContent=notes.size?'Choose a retained organization note.':'No organization note on these pages. Adopt a .portfolio.json note or inspect the next page.';
      });
    }
    function inGroup(model,wanted){let id=model.group_id;while(id!==null){if(id===wanted)return true;id=groups.get(id).parent;}return false;}
    function filtered(){if(!guide)return [];return guide.models.filter(model=>(!applied.group||inGroup(model,applied.group))&&
      (!applied.review||model.review===applied.review)&&(!applied.search||[model.label,...model.aliases].some(value=>value.toLocaleLowerCase().includes(applied.search))));}
    function render(){
      if(!guide)return;
      const focused=$('graph').contains(document.activeElement)?document.activeElement.id:null;
      const matching=filtered(),shown=matching.slice(offset,offset+pageSize),included=new Set();
      for(const model of shown){let id=model.group_id;while(id!==null){included.add(id);id=groups.get(id).parent;}}
      const graphNodes=[...included].map(id=>{const group=groups.get(id);return {id:'group/'+id,title:group.label,recordedAt:'',parent:group.parent===null?null:'group/'+group.parent,baseline:null,lines:['Authored method group']};});
      graphNodes.push(...shown.map(model=>({id:'model/'+model.id,title:model.label,recordedAt:'',parent:'group/'+model.group_id,baseline:null,
        lines:[model.aliases.slice(0,3).join(' · ')||model.id,model.review==='source_reviewed'?'Source reviewed · authored summary':'Source review pending']})));
      $('graph').innerHTML=window.WorkspaceExperimentGraph.render(graphNodes,{selected:selected?'model/'+selected:'',zoom:1}).html;
      for(const button of $('graph').querySelectorAll('[data-lineage-node]')){
        const value=button.dataset.lineageNode;
        button.onclick=()=>{if(value.startsWith('model/'))void selectModel(value.slice(6));else{$('group').value=value.slice(6);applyFilters();}};
      }
      $('count').textContent=`${guide.models.length} models in this guide; ${guide.models.filter(model=>model.review==='source_reviewed').length} source reviewed. ${matching.length} match the applied filters. Showing ${shown.length?offset+1:0}–${offset+shown.length}.`;
      controls();
      if(focused){const replacement=$('graph').querySelector('#'+CSS.escape(focused));
        if(replacement)replacement.focus({preventScroll:true});else{$('count').tabIndex=-1;$('count').focus();}}
    }
    function applyFilters(){if(!guide||busy)return;applied={group:$('group').value,search:$('search').value.trim().toLocaleLowerCase(),review:$('review').value};
      if(applied.group&&!groups.has(applied.group))return;offset=0;selected='';$('detail').replaceChildren();render();$('status').textContent='Applied model filters.';}
    async function loadGuide(){
      const choice=notes.get($('note').value);if(!choice)return;
      return perform(async(active,signal)=>{
        clearGuide();const value=await read('file_get',{file_id:choice.id,revision:choice.revision},signal);if(!active())return;
        if(value?.id!==choice.id||value.project_id!==context.project_id||value.kind!=='note'||value.path!==choice.path||
           value.version?.revision!==choice.revision||value.version.sha256!==choice.expected_sha256||value.version.deleted===true)fail('Organization note differs from the selected captured revision.');
        const parsed=decode(value.version.text);
        if(parsed.project_id!==context.project_id)fail('This guide belongs to another project; re-author its captured note bindings.','unsupported');
        guide=parsed;groups=new Map(guide.groups.map(group=>[group.id,group]));models=new Map(guide.models.map(model=>[model.id,model]));
        $('title').textContent=guide.title;$('description').textContent=guide.description;
        $('source').textContent=`Retrospective authored guide · ${choice.path} · revision ${choice.revision} · SHA256 ${choice.expected_sha256}`;
        const all=node('option','All groups');all.value='';$('group').append(all);
        for(const group of guide.groups){const option=node('option',group.label);option.value=group.id;$('group').append(option);}
        $('content').hidden=false;render();$('status').textContent='Loaded retained authored model organization.';
      });
    }
    async function selectModel(id){
      const model=models.get(id);if(!model||busy)return;
      return perform(async(active,signal)=>{
        if(!filtered().some(item=>item.id===id)){
          applied={group:'',search:'',review:''};$('group').value='';$('search').value='';$('review').value='';
        }
        offset=Math.floor(filtered().findIndex(item=>item.id===id)/pageSize)*pageSize;
        selected=id;$('detail').replaceChildren();render();
        const value=await read('file_get',{file_id:model.card.file_id,revision:model.card.revision},signal);if(!active())return;
        const captured=checkCard(guide,model,value),heading=node('h3',model.label);heading.id='project-portfolio-model-heading';heading.tabIndex=-1;$('detail').append(heading);
        $('detail').append(node('p',(model.aliases.join(' · ')||model.id)+' · '+(model.review==='source_reviewed'?'Source reviewed':'Source review pending')));
        if(model.summary){const labels={method:'Method',purpose:'Purpose',experiment:'Training and experiment',outcome:'Observed outcome',lesson:'Lesson',reproduction:'Reproduction'};
          for(const field of fields){$('detail').append(node('h4',labels[field]),node('p',model.summary[field]));}}
        else $('detail').append(node('p','A source-reviewed interpretation has not been recorded for this fit. Its original captured card remains available below.'));
        const relations=guide.relationships.filter(relation=>relation.from===id||relation.to===id);
        if(relations.length){$('detail').append(node('h4','Authored model relationships'));
          for(const relation of relations){const box=node('div'),other=models.get(relation.from===id?relation.to:relation.from),button=node('button',
              (relation.kind==='comparison'?'Comparison: ':relation.from===id?'Parameters from: ':'Derived model: ')+other.label);button.type='button';button.onclick=()=>void selectModel(other.id);
            box.append(button,node('p',relation.explanation));const evidence=node('details');evidence.append(node('summary','Exact retained relationship excerpt'),node('p',relation.excerpt));
            const source=node('button','Read evidence card: '+models.get(relation.evidence_model).label);source.type='button';source.onclick=()=>void selectModel(relation.evidence_model);evidence.append(source);box.append(evidence);$('detail').append(box);}}
        const raw=node('details'),summary=node('summary','Exact captured card and original receipts');raw.append(summary,node('p',`${model.card.path} · revision ${model.card.revision} · SHA256 ${model.card.sha256}`),node('pre',captured));$('detail').append(raw);
        $('status').textContent='Exact retained model summary and captured evidence.';heading.focus();
      });
    }
    $('notes').onclick=()=>void findNotes();$('notes-more').onclick=()=>void findNotes(true);
    $('note').onchange=()=>{clearGuide();controls();};
    $('source-form').onsubmit=event=>{event.preventDefault();void loadGuide();};
    $('filter-form').onsubmit=event=>{event.preventDefault();applyFilters();};
    for(const [name,direction] of [['prev',-1],['next',1]])$(name).onclick=()=>{if(busy||!guide)return;offset=Math.max(0,offset+direction*pageSize);selected='';$('detail').replaceChildren();render();};
    controls();
    return {setContext(value){if(value.key!==context?.key||context?.enabled&&!value.enabled){const owned=root.contains(document.activeElement);context=value;reset();if(owned)onContextFocusLost();}else context=value;root.hidden=!value.enabled;controls();},clear(){context=null;reset();root.hidden=true;}};
  };
})();
