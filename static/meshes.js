'use strict';
let meshImportBusy = false, meshInspectionGeneration = 0, meshInspectionController = null;
let meshSpatialView = null;
function meshRotation(vector, yaw, pitch) {
  const y=yaw*Math.PI/180,p=pitch*Math.PI/180;
  const horizontal=vector[0]*Math.cos(y)-vector[1]*Math.sin(y);
  const depth=vector[0]*Math.sin(y)+vector[1]*Math.cos(y);
  return [horizontal,vector[2]*Math.cos(p)-depth*Math.sin(p)];
}
function drawMeshSpatial() {
  if(!meshSpatialView)return;
  const {value,yaw,pitch,zoom}=meshSpatialView,svg=$('mesh-spatial-svg');svg.replaceChildren();
  const span=Math.max(...value.bounds.max.map((n,i)=>n-value.bounds.min[i]));
  const project=vertex=>{
    // Normalize before rotation: even the accepted smallest native doubles stay finite.
    const normalized=vertex.map((n,i)=>span>0?(n-value.bounds.min[i])/span-(value.bounds.max[i]-value.bounds.min[i])/span/2:0);
    const point=meshRotation(normalized,yaw,pitch);
    return [200+point[0]*190*zoom,150-point[1]*190*zoom];
  };
  for(const triangle of value.triangles){
    const polygon=document.createElementNS('http://www.w3.org/2000/svg','polygon');
    polygon.setAttribute('points',triangle.map(vertex=>project(vertex).join(',')).join(' '));svg.append(polygon);
  }
  for(let axis=0;axis<3;axis++){
    const direction=[0,0,0];direction[axis]=1;const end=meshRotation(direction,yaw,pitch);
    const line=document.createElementNS('http://www.w3.org/2000/svg','line');line.setAttribute('x1','48');line.setAttribute('y1','250');line.setAttribute('x2',String(48+end[0]*28));line.setAttribute('y2',String(250-end[1]*28));line.setAttribute('class','mesh-axis-'+axis);
    const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x',String(48+end[0]*39));label.setAttribute('y',String(254-end[1]*39));label.textContent='XYZ'[axis];svg.append(line,label);
  }
  $('mesh-view-position').textContent=`Yaw ${yaw}° · tilt ${pitch}° · ${Math.round(zoom*100)}%`;
  svg.setAttribute('aria-label',`Spatial wireframe, first ${value.sample_count} of ${value.triangle_count} triangles; native XYZ axes, ${value.units}, ${value.coordinate_system.frame}. Yaw ${yaw} degrees, tilt ${pitch} degrees, zoom ${Math.round(zoom*100)} percent.`);
}
function mountMeshSpatial(value) {
  let holder=$('mesh-spatial');
  if(!holder){
    holder=document.createElement('section');holder.id='mesh-spatial';holder.setAttribute('aria-label','Spatial mesh inspection');
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.id='mesh-spatial-svg';svg.setAttribute('viewBox','0 0 400 300');svg.setAttribute('role','img');
    const controls=document.createElement('div');controls.className='mesh-view-controls';
    const title=document.createElement('strong');title.textContent='Spatial view';controls.append(title);
    const position=document.createElement('p');position.id='mesh-view-position';position.setAttribute('role','status');controls.append(position);
    const actions=[['Rotate left',()=>meshSpatialView.yaw=(meshSpatialView.yaw+345)%360],['Rotate right',()=>meshSpatialView.yaw=(meshSpatialView.yaw+15)%360],['Tilt up',()=>meshSpatialView.pitch=Math.min(90,meshSpatialView.pitch+15)],['Tilt down',()=>meshSpatialView.pitch=Math.max(-90,meshSpatialView.pitch-15)],['Zoom in',()=>meshSpatialView.zoom=Math.min(2,meshSpatialView.zoom+.25)],['Zoom out',()=>meshSpatialView.zoom=Math.max(.5,meshSpatialView.zoom-.25)],['Reset view',()=>Object.assign(meshSpatialView,{yaw:35,pitch:25,zoom:1})]];
    const buttons=document.createElement('div');buttons.className='mesh-view-buttons';
    for(const [name,action] of actions){const button=document.createElement('button');button.type='button';button.textContent=name;button.addEventListener('click',()=>{if(!meshSpatialView)return;action();drawMeshSpatial();});buttons.append(button);}
    controls.append(buttons);const help=document.createElement('p');help.className='mesh-view-help';help.textContent='Display controls only. Original geometry and declared axes stay unchanged.';controls.append(help);holder.append(svg,controls);$('mesh-projections').before(holder);
  }
  holder.hidden=false;meshSpatialView={value,yaw:35,pitch:25,zoom:1};drawMeshSpatial();
}
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
  mountMeshSpatial(value);
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
  meshSpatialView=null;if($('mesh-spatial'))$('mesh-spatial').hidden=true;
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
      $('mesh-preview-status').textContent=`${record.mesh.vertex_count} vertices, ${value.triangle_count} triangles. Showing first ${value.sample_count} triangles in spatial and axis views; ${value.coordinate_system.handedness}-handed, ${value.coordinate_system.up_axis} up. Bounds and raw download cover the whole mesh. ${record.mesh.provided_normals ? 'Provided normals are retained without normalization.' : 'No vertex normals were supplied.'}`;
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

// A successful frozen-release publication is owned by workbench.js. Validation
// owns only this transient view; clearing/superseding a release fences its reply.
let meshReleaseGeneration=0,meshReleaseController=null,meshPublishedRelease=null;
function decodeMeshReleaseReport(value,release) {
  const exact=(item,keys)=>item&&typeof item==='object'&&!Array.isArray(item)&&Object.keys(item).sort().join()===keys.sort().join();
  const integer=(n,low,high)=>Number.isInteger(n)&&n>=low&&n<=high;
  const string=(s,cap)=>typeof s==='string'&&s.length>0&&[...s].length<=cap&&[...s].every(c=>c.codePointAt(0)<0xd800||c.codePointAt(0)>0xdfff);
  const hash=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
  const vector=v=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<=1e12);
  const keys=['schema_version','validation','release_sha256','mesh_count','triangle_count','vertex_count','split_counts','family_scope','limitations','meshes'];
  const rowKeys=['id','name','revision','source_revision','split','asset_sha256','geometry_sha256','manifest_sha256','vertex_count','triangle_count','properties','bounds','units','coordinate_system','provenance','review','rights'];
  const valid=exact(value,keys)&&value.schema_version===1&&value.validation==='mesh_release_integrity'&&value.release_sha256===release.id&&
    integer(value.mesh_count,1,64)&&integer(value.triangle_count,1,2560000)&&integer(value.vertex_count,3,1280000)&&value.family_scope==='selected_records_only'&&
    exact(value.split_counts,['train','validation','test'])&&Object.values(value.split_counts).every(n=>integer(n,0,64))&&Object.values(value.split_counts).reduce((a,b)=>a+b,0)===value.mesh_count&&
    Array.isArray(value.limitations)&&value.limitations.length===3&&value.limitations.every(s=>string(s,1000))&&
    Array.isArray(value.meshes)&&value.meshes.length===value.mesh_count&&value.meshes.every(row=>exact(row,rowKeys)&&
      typeof row.id==='string'&&/^[a-f0-9]{32}$/.test(row.id)&&string(row.name,200)&&integer(row.revision,1,Number.MAX_SAFE_INTEGER)&&row.source_revision===1&&
      ['train','validation','test'].includes(row.split)&&['asset_sha256','geometry_sha256','manifest_sha256'].every(key=>hash(row[key]))&&
      integer(row.vertex_count,3,20000)&&integer(row.triangle_count,1,40000)&&
      Array.isArray(row.properties)&&[3,6].includes(row.properties.length)&&row.properties.every((p,i)=>exact(p,['name','dtype'])&&p.name===['x','y','z','nx','ny','nz'][i]&&['float','double'].includes(p.dtype))&&
      exact(row.bounds,['min','max'])&&vector(row.bounds.min)&&vector(row.bounds.max)&&row.bounds.min.every((n,i)=>n<=row.bounds.max[i])&&['m','cm','mm'].includes(row.units)&&
      exact(row.coordinate_system,['frame','handedness','up_axis'])&&string(row.coordinate_system.frame,120)&&['right','left'].includes(row.coordinate_system.handedness)&&['x','y','z'].includes(row.coordinate_system.up_axis)&&
      exact(row.provenance,['source','revision','license','description'])&&Object.values(row.provenance).every(s=>string(s,1000))&&row.review==='human_reviewed'&&string(row.rights,1000));
  if(!valid||new Set(value.meshes.map(row=>row.id)).size!==value.mesh_count||
    value.meshes.reduce((sum,row)=>sum+row.vertex_count,0)!==value.vertex_count||value.meshes.reduce((sum,row)=>sum+row.triangle_count,0)!==value.triangle_count||
    Object.entries(value.split_counts).some(([split,n])=>value.meshes.filter(row=>row.split===split).length!==n))throw Error('Invalid mesh release validation response.');
  return value;
}
function meshReleaseCleared() {
  ++meshReleaseGeneration;meshReleaseController?.abort();meshReleaseController=null;meshPublishedRelease=null;
  const panel=$('mesh-release-validation');if(panel)panel.hidden=true;
}
function meshReleasePublished(event) {
  meshReleaseCleared();const release=event.detail;
  if(!release||typeof release.id!=='string'||!/^[a-f0-9]{64}$/.test(release.id)||release.url!=='/api/workbench/releases/'+release.id+'.zip')return;
  meshPublishedRelease={id:release.id,url:release.url};
  let panel=$('mesh-release-validation');
  if(!panel){
    panel=document.createElement('section');panel.id='mesh-release-validation';panel.setAttribute('aria-label','Frozen mesh validation');
    const button=document.createElement('button');button.id='mesh-validate-release';button.type='button';button.textContent='Validate mesh release';button.addEventListener('click',validateMeshRelease);
    const status=document.createElement('p');status.id='mesh-release-status';status.setAttribute('role','status');
    const details=document.createElement('div');details.id='mesh-release-details';panel.append(button,status,details);$('release-result').after(panel);
  }
  panel.hidden=false;$('mesh-validate-release').disabled=false;$('mesh-release-details').replaceChildren();
  $('mesh-release-status').textContent='Check exact source hashes, native geometry and frozen splits. Mesh-only canonical releases, up to 64 meshes.';
}
async function validateMeshRelease() {
  if(!meshPublishedRelease||meshReleaseController)return;
  const release=meshPublishedRelease,generation=meshReleaseGeneration,controller=new AbortController();meshReleaseController=controller;
  const owns=()=>generation===meshReleaseGeneration&&meshPublishedRelease?.id===release.id;
  $('mesh-validate-release').disabled=true;$('mesh-release-details').replaceChildren();$('mesh-release-status').textContent='Validating frozen mesh bytes and record projections…';
  try{
    const response=await fetch('/api/workbench/mesh-release-validation/'+release.id,{signal:controller.signal});
    const raw=await response.json();if(!response.ok)throw Error(raw.error||'Mesh release validation unavailable.');
    const value=decodeMeshReleaseReport(raw,release);if(!owns())return;
    $('mesh-release-status').textContent=`Integrity verified: ${value.mesh_count} whole meshes · ${value.vertex_count} vertices · ${value.triangle_count} triangles. Selected-record family checks only.`;
    const list=document.createElement('ul');
    for(const row of value.meshes){const item=document.createElement('li');item.textContent=`${row.name} · ${row.split} · revision ${row.revision} · ${row.units} · ${row.coordinate_system.frame} (${row.coordinate_system.handedness}-handed, ${row.coordinate_system.up_axis} up)`;list.append(item);}
    const limitation=document.createElement('p');limitation.textContent='Original PLY and sidecar hashes match. Omitted ancestors, source independence, physics and training suitability are not certified.';
    $('mesh-release-details').append(list,limitation);
  }catch(error){if(owns()&&error.name!=='AbortError')$('mesh-release-status').textContent=error.message;}
  finally{if(meshReleaseController===controller)meshReleaseController=null;if(owns())$('mesh-validate-release').disabled=false;}
}
window.addEventListener('tuldok:release-published',meshReleasePublished);
window.addEventListener('tuldok:release-cleared',meshReleaseCleared);
window.addEventListener('pagehide',meshReleaseCleared);
