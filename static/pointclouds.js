'use strict';
let pointcloudImportBusy=false,pointcloudInspectionGeneration=0,pointcloudInspectionController=null;
function decodePointcloudInspection(value,record) {
  const metadata=record.pointcloud,keys=['id','content_hash','bounds','units','coordinate_system','point_count','sample_count','properties','points'];
  const vector=items=>Array.isArray(items)&&items.length===3&&items.every(n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<=1e12);
  if(!value||Object.keys(value).sort().join()!==keys.sort().join()||value.id!==record.id||value.content_hash!==record.content_hash||
     !Number.isInteger(value.point_count)||value.point_count<1||value.point_count>20000||value.point_count!==metadata.point_count||value.sample_count!==Math.min(512,value.point_count)||
     !Array.isArray(value.properties)||value.properties.length!==metadata.properties.length||!value.properties.every((p,i)=>p&&Object.keys(p).sort().join()==='dtype,name'&&p.name===metadata.properties[i].name&&p.dtype===metadata.properties[i].dtype)||
     !Array.isArray(value.points)||value.points.length!==value.sample_count||!value.points.every(p=>Array.isArray(p)&&p.length===metadata.properties.length&&p.every((n,i)=>typeof n==='number'&&Number.isFinite(n)&&(metadata.properties[i].dtype==='uchar'?Number.isInteger(n)&&n>=0&&n<=255:Math.abs(n)<=1e12)))||
     !value.bounds||Object.keys(value.bounds).sort().join()!=='max,min'||!vector(value.bounds.min)||!vector(value.bounds.max)||!['min','max'].every(k=>value.bounds[k].every((n,i)=>n===metadata.bounds[k][i]))||
     value.units!==metadata.manifest.units||!value.coordinate_system||Object.keys(value.coordinate_system).sort().join()!=='frame,handedness,up_axis'||!['frame','handedness','up_axis'].every(k=>value.coordinate_system[k]===metadata.manifest.coordinate_system[k])) throw Error('Invalid point-cloud inspection response.');
  return value;
}
function renderPointcloudInspection(value) {
  const holder=$('pointcloud-projections');holder.replaceChildren();
  for(const [horizontal,vertical] of [[0,1],[0,2],[1,2]]) {
    const figure=document.createElement('figure'),caption=document.createElement('figcaption'),svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    caption.textContent=`${'xyz'[horizontal].toUpperCase()} / ${'xyz'[vertical].toUpperCase()} · ${value.units} · ${value.coordinate_system.frame}`;
    svg.setAttribute('viewBox','0 0 240 220');svg.setAttribute('role','img');svg.setAttribute('aria-label',`${caption.textContent} projection of first ${value.sample_count} points`);
    const low=value.bounds.min,high=value.bounds.max,span=Math.max(high[horizontal]-low[horizontal],high[vertical]-low[vertical]);
    const offset=(n,axis)=>span>0?((n-low[axis])/span-(high[axis]-low[axis])/span/2)*190:0;
    for(const p of value.points) {
      const circle=document.createElementNS('http://www.w3.org/2000/svg','circle');
      circle.setAttribute('cx',120+offset(p[horizontal],horizontal));circle.setAttribute('cy',110-offset(p[vertical],vertical));circle.setAttribute('r','2');svg.append(circle);
    }
    figure.append(caption,svg);holder.append(figure);
  }
}
function pointcloudShown(record) {
  const generation=++pointcloudInspectionGeneration;
  pointcloudInspectionController?.abort();pointcloudInspectionController=null;
  $('pointcloud-inspection').hidden=record.kind!=='pointcloud';$('pointcloud-projections').replaceChildren();$('pointcloud-preview-status').textContent='';
  if(record.kind!=='pointcloud')return;
  $('pointcloud-note').value=record.annotation?.note||'';$('pointcloud-metadata').textContent=JSON.stringify(record.pointcloud,null,2);
  $('pointcloud-download').href='/api/workbench/asset/'+record.id;$('pointcloud-download').download=record.id+'.zip';
  const controller=new AbortController();pointcloudInspectionController=controller;
  const owns=()=>generation===pointcloudInspectionGeneration&&current?.id===record.id&&current?.kind==='pointcloud'&&current.content_hash===record.content_hash;
  $('pointcloud-preview-status').textContent='Loading bounded point inspection…';
  (async()=>{
    try {
      const response=await fetch('/api/workbench/pointcloud-inspection/'+record.id,{signal:controller.signal}),raw=await response.json();
      if(!response.ok)throw Error(raw.error||'Point inspection unavailable.');
      const value=decodePointcloudInspection(raw,record);if(!owns())return;
      renderPointcloudInspection(value);
      $('pointcloud-preview-status').textContent=`${value.point_count} points. Showing first ${value.sample_count} original points in three projections; ${value.coordinate_system.handedness}-handed, ${value.coordinate_system.up_axis} up. Bounds and raw download cover the whole cloud. Named attribute dtypes and declared source lineage are in metadata.`;
    } catch(error) {if(owns()&&error.name!=='AbortError')$('pointcloud-preview-status').textContent=error.message;}
    finally {if(pointcloudInspectionController===controller)pointcloudInspectionController=null;}
  })();
}
window.addEventListener('pagehide',()=>{++pointcloudInspectionGeneration;pointcloudInspectionController?.abort();pointcloudInspectionController=null;});
$('pointcloud-import-form').addEventListener('submit',async event=>{
  event.preventDefault();if(pointcloudImportBusy)return;pointcloudImportBusy=true;
  const controls=[...$('pointcloud-import-form').querySelectorAll('input,button')];controls.forEach(c=>c.disabled=true);
  const status=$('pointcloud-import-status');
  try {
    const ply=$('pointcloud-ply').files[0],sidecar=$('pointcloud-manifest').files[0],name=$('pointcloud-name').value,group=$('pointcloud-group').value.trim(),rights=$('pointcloud-rights').value||'unknown';
    status.textContent='Reading and validating the complete bounded point cloud…';
    const files={'points.ply':await meshFile(ply,2097152,'points.ply'),'points.json':await meshFile(sidecar,32768,'points.json')};
    const row=await api('pointcloud-import',{files,name,groups:group?[group]:[],rights});
    status.textContent=`Imported ${row.name}: ${row.pointcloud.point_count} points, unreviewed. Open it to inspect and review.`;
    await refresh();
  } catch(error) {status.textContent=error.message+' Check the collection before repeating a request whose response was lost.';}
  finally {pointcloudImportBusy=false;controls.forEach(c=>c.disabled=false);}
});
