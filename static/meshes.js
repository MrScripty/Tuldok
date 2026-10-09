'use strict';
let meshImportBusy = false, meshInspectionGeneration = 0, meshInspectionController = null;
function decodeMeshInspection(value, record) {
  const keys=['id','content_hash','bounds','units','coordinate_system','triangle_count','sample_count','triangles'];
  const vector=items=>Array.isArray(items)&&items.length===3&&items.every(item=>typeof item==='number'&&Number.isFinite(item)&&Math.abs(item)<=1e12);
  if(!value||Object.keys(value).sort().join()!==keys.sort().join()||value.id!==record.id||value.content_hash!==record.content_hash||
     value.triangle_count!==record.mesh.triangle_count||value.sample_count!==Math.min(512,value.triangle_count)||
     !Array.isArray(value.triangles)||value.triangles.length!==value.sample_count||!value.triangles.every(triangle=>Array.isArray(triangle)&&triangle.length===3&&triangle.every(vector))||
     !value.bounds||!vector(value.bounds.min)||!vector(value.bounds.max)||Object.keys(value.bounds).sort().join()!=='max,min'||!['min','max'].every(key=>value.bounds[key].every((number,i)=>number===record.mesh.bounds[key][i]))||
     value.units!==record.mesh.manifest.units||!value.coordinate_system||Object.keys(value.coordinate_system).sort().join()!=='frame,handedness,up_axis'||!['frame','handedness','up_axis'].every(key=>value.coordinate_system[key]===record.mesh.manifest.coordinate_system[key])) throw Error('Invalid geometry inspection response.');
  return value;
}
function renderMeshInspection(value) {
  const holder=$('mesh-projections'); holder.replaceChildren();
  for(const [horizontal,vertical] of [[0,1],[0,2],[1,2]]) {
    const axes='xyz',figure=document.createElement('figure'),caption=document.createElement('figcaption');
    caption.textContent=`${axes[horizontal].toUpperCase()} / ${axes[vertical].toUpperCase()} · ${value.units} · ${value.coordinate_system.frame}`;
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 240 220');svg.setAttribute('role','img');svg.setAttribute('aria-label',`${caption.textContent} wireframe projection of ${value.sample_count} triangles`);
    const low=value.bounds.min,high=value.bounds.max,span=Math.max(high[horizontal]-low[horizontal],high[vertical]-low[vertical]);
    const offset=(coordinate,axis)=>span>0?((coordinate-low[axis])/span-(high[axis]-low[axis])/span/2)*190:0;
    // One common scale preserves projection aspect; points are display-only.
    for(const triangle of value.triangles) {
      const polygon=document.createElementNS('http://www.w3.org/2000/svg','polygon');
      polygon.setAttribute('points',triangle.map(vertex=>`${120+offset(vertex[horizontal],horizontal)},${110-offset(vertex[vertical],vertical)}`).join(' '));
      svg.append(polygon);
    }
    figure.append(caption,svg);holder.append(figure);
  }
}
function meshShown(record) {
  const generation=++meshInspectionGeneration;
  meshInspectionController?.abort();meshInspectionController=null;
  const panel=$('mesh-inspection');panel.hidden=record.kind!=='mesh';
  $('mesh-projections').replaceChildren();$('mesh-preview-status').textContent='';
  if(record.kind!=='mesh')return;
  $('mesh-note').value=record.annotation?.note||'';
  $('mesh-metadata').textContent=JSON.stringify(record.mesh,null,2);
  $('mesh-download').href='/api/workbench/asset/'+record.id;$('mesh-download').download=record.id+'.zip';
  const controller=new AbortController();meshInspectionController=controller;
  const owns=()=>generation===meshInspectionGeneration&&current?.id===record.id&&current?.kind==='mesh'&&current.content_hash===record.content_hash;
  $('mesh-preview-status').textContent='Loading bounded geometry inspection…';
  // Geometry owns only its projection; note/review/selection remain editor-owned.
  (async()=>{
    try {
      const response=await fetch('/api/workbench/mesh-inspection/'+record.id,{signal:controller.signal});
      const raw=await response.json();if(!response.ok)throw Error(raw.error||'Geometry inspection unavailable.');
      const value=decodeMeshInspection(raw,record);if(!owns())return;
      renderMeshInspection(value);
      $('mesh-preview-status').textContent=`${record.mesh.vertex_count} vertices, ${value.triangle_count} triangles. Showing first ${value.sample_count} triangles in three projections; ${value.coordinate_system.handedness}-handed, ${value.coordinate_system.up_axis} up. Bounds and raw download cover the whole mesh. ${record.mesh.provided_normals ? 'Provided normals are retained without normalization.' : 'No vertex normals were supplied.'}`;
    } catch(error) {if(owns()&&error.name!=='AbortError')$('mesh-preview-status').textContent=error.message;}
    finally {if(meshInspectionController===controller)meshInspectionController=null;}
  })();
}
window.addEventListener('pagehide',()=>{++meshInspectionGeneration;meshInspectionController?.abort();meshInspectionController=null;});
async function meshFile(file, maximum, name) {
  if(!file||file.name!==name||!file.size||file.size>maximum)throw Error(`Choose ${name}, at most ${maximum} bytes.`);
  const raw=new Uint8Array(await file.arrayBuffer());let binary='';
  for(let start=0;start<raw.length;start+=32768)binary+=String.fromCharCode(...raw.subarray(start,start+32768));
  return btoa(binary);
}
$('mesh-import-form').addEventListener('submit',async event=>{
  event.preventDefault();if(meshImportBusy)return;meshImportBusy=true;
  const controls=[...$('mesh-import-form').querySelectorAll('input,button')];controls.forEach(control=>control.disabled=true);
  const status=$('mesh-import-status');
  try {
    const ply=$('mesh-ply').files[0],sidecar=$('mesh-manifest').files[0],name=$('mesh-name').value,group=$('mesh-group').value.trim(),rights=$('mesh-rights').value||'unknown';
    status.textContent='Reading and validating the complete bounded geometry…';
    const files={'mesh.ply':await meshFile(ply,2097152,'mesh.ply'),'mesh.json':await meshFile(sidecar,32768,'mesh.json')};
    const record=await api('mesh-import',{files,name,groups:group?[group]:[],rights});
    status.textContent=`Imported ${record.name}: ${record.mesh.vertex_count} vertices, ${record.mesh.triangle_count} triangles, unreviewed. Open it to inspect and review.`;
    await refresh();
  } catch(error) {status.textContent=error.message+' Check the collection before repeating a request whose response was lost.';}
  finally {meshImportBusy=false;controls.forEach(control=>control.disabled=false);}
});
