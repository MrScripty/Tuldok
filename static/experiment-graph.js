'use strict';
// Shared presentation of declared relationships. Callers own provenance,
// authorization, asynchronous reads, selection and the corresponding details.
(() => {
  const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function text(value,limit) {return typeof value==='string'&&value.length>0&&value.length<=limit;}
  function validate(nodes) {
    if(!Array.isArray(nodes)||nodes.length>100)throw Error('The experiment graph holds at most 100 entries.');
    const ids=new Set();
    for(const node of nodes) {
      if(!node||!text(node.id,256)||ids.has(node.id)||!text(node.title,500)||
         typeof node.recordedAt!=='string'||node.recordedAt.length>80||
         !Array.isArray(node.lines)||node.lines.length>5||node.lines.some(line=>!text(line,2000))||
         [node.parent,node.baseline].some(ref=>ref!==null&&!text(ref,256)))throw Error('Invalid experiment graph entry.');
      ids.add(node.id);
    }
  }
  function layout(nodes) {
    validate(nodes);
    const byId=new Map(nodes.map(node=>[node.id,node])),depth=new Map();
    function level(id,path=new Set()) {
      if(depth.has(id))return depth.get(id);
      if(path.has(id))throw Error('Derivation contains a cycle.');
      path=new Set(path);path.add(id);
      const parent=byId.get(id)?.parent;
      const value=parent&&byId.has(parent)?level(parent,path)+1:0;
      depth.set(id,value);return value;
    }
    const rows=new Map(),positions=new Map();
    for(const node of [...nodes].sort((a,b)=>a.recordedAt.localeCompare(b.recordedAt)||a.id.localeCompare(b.id))) {
      const column=level(node.id),row=rows.get(column)||0;rows.set(column,row+1);
      positions.set(node.id,{x:24+column*300,y:24+row*180});
    }
    return {positions,width:Math.max(600,...[...positions.values()].map(p=>p.x+276)),height:Math.max(240,...[...positions.values()].map(p=>p.y+160))};
  }
  function render(nodes,{selected='',zoom=1}={}) {
    if(typeof selected!=='string'||selected.length>256||typeof zoom!=='number'||!Number.isFinite(zoom)||zoom<0.6||zoom>1.6)throw Error('Invalid experiment graph selection or zoom.');
    const graph=layout(nodes),edges=[];
    for(const node of nodes)for(const kind of ['parent','baseline']) {
      const from=graph.positions.get(node[kind]),to=graph.positions.get(node.id);
      if(from&&to)edges.push(`<path class="${kind}" d="M${from.x+252},${from.y+72+(kind==='baseline'?10:0)} C${from.x+285},${from.y+72} ${to.x-30},${to.y+72} ${to.x},${to.y+72}"/>`);
    }
    const buttons=nodes.map(node=>{
      const p=graph.positions.get(node.id);
      return `<button id="lineage-node-${escape(node.id)}" type="button" data-lineage-node="${escape(node.id)}" class="lineage-node" aria-pressed="${selected===node.id}" style="left:${p.x}px;top:${p.y}px"><strong>${escape(node.title)}</strong>${node.lines.map(line=>`<span>${escape(line)}</span>`).join('')}</button>`;
    }).join('');
    return {...graph,html:`<div class="lineage-viewport" tabindex="0" aria-label="Experiment graph; scroll horizontally and vertically to explore"><div style="width:${graph.width*zoom}px;height:${graph.height*zoom}px"><div class="lineage-canvas" style="width:${graph.width}px;height:${graph.height}px;transform:scale(${zoom})"><svg width="${graph.width}" height="${graph.height}" aria-hidden="true">${edges.join('')}</svg>${buttons}</div></div></div>`};
  }
  window.WorkspaceExperimentGraph=Object.freeze({layout,render});
})();
