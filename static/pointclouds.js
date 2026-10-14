'use strict';
let pointcloudImportBusy = false, pointcloudGeneration = 0, pointcloudController = null, pointcloudView = null;
function decodePointcloudInspection(value, record) {
  const meta = record.pointcloud;
  const vector = v => Array.isArray(v) && v.length === 3 && v.every(n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 1e12);
  if (!value || value.id !== record.id || value.content_hash !== record.content_hash ||
      value.point_count !== meta.point_count || value.sample_count !== Math.min(512, meta.point_count) ||
      !Array.isArray(value.properties) || value.properties.length !== meta.properties.length || !value.properties.every((property,i) => property && property.name === meta.properties[i].name && property.dtype === meta.properties[i].dtype) ||
      !value.bounds || !vector(value.bounds.min) || !vector(value.bounds.max) ||
      !['min','max'].every(key => value.bounds[key].every((n,i) => n === meta.bounds[key][i])) ||
      value.units !== meta.manifest.units || !value.coordinate_system ||
      !['frame','handedness','up_axis'].every(key => value.coordinate_system[key] === meta.manifest.coordinate_system[key]) ||
      !Array.isArray(value.points) || value.points.length !== value.sample_count ||
      !value.points.every(row => Array.isArray(row) && row.length === meta.properties.length && vector(row.slice(0,3)) && row.every(n => typeof n === 'number' && Number.isFinite(n)))) {
    throw Error('Invalid point cloud inspection response.');
  }
  return value;
}
function drawPointcloud() {
  if (!pointcloudView) return;
  const {value,yaw,pitch,zoom} = pointcloudView, svg = $('pointcloud-svg');
  svg.replaceChildren();
  const span = Math.max(...value.bounds.max.map((n,i) => n-value.bounds.min[i]));
  const angle = yaw*Math.PI/180, tilt = pitch*Math.PI/180;
  for (const [index,point] of value.points.entries()) {
    const v = point.slice(0,3).map((n,i) => span > 0 ? (n-value.bounds.min[i])/span-(value.bounds.max[i]-value.bounds.min[i])/span/2 : 0);
    const x=v[0]*Math.cos(angle)-v[1]*Math.sin(angle), depth=v[0]*Math.sin(angle)+v[1]*Math.cos(angle);
    const y=v[2]*Math.cos(tilt)-depth*Math.sin(tilt);
    const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
    circle.setAttribute('cx',String(200+x*190*zoom));circle.setAttribute('cy',String(150-y*190*zoom));circle.setAttribute('r','2.5');
    circle.setAttribute('fill','#276674');circle.dataset.sourceIndex=String(index);
    const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`Source point ${index}: ${point.slice(0,3).join(', ')} ${value.units}`;circle.append(title);svg.append(circle);
  }
  svg.setAttribute('aria-label',`First ${value.sample_count} of ${value.point_count} source points, original order; native XYZ in ${value.units}, frame ${value.coordinate_system.frame}. Yaw ${yaw} degrees, tilt ${pitch} degrees.`);
  $('pointcloud-view-position').textContent=`Yaw ${yaw}° · tilt ${pitch}° · ${Math.round(zoom*100)}%`;
}
function renderPointcloud(value) {
  const holder=$('pointcloud-preview');holder.replaceChildren();
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.id='pointcloud-svg';svg.setAttribute('viewBox','0 0 400 300');svg.setAttribute('role','img');svg.style.cssText='display:block;width:100%;height:280px;background:#edf4f6';
  const position=document.createElement('p');position.id='pointcloud-view-position';position.setAttribute('role','status');
  const buttons=document.createElement('div');buttons.className='mesh-view-buttons';
  pointcloudView={value,yaw:35,pitch:25,zoom:1};
  const actions=[['Rotate left',()=>pointcloudView.yaw=(pointcloudView.yaw+345)%360],['Rotate right',()=>pointcloudView.yaw=(pointcloudView.yaw+15)%360],['Tilt up',()=>pointcloudView.pitch=Math.min(90,pointcloudView.pitch+15)],['Tilt down',()=>pointcloudView.pitch=Math.max(-90,pointcloudView.pitch-15)],['Zoom in',()=>pointcloudView.zoom=Math.min(2,pointcloudView.zoom+.25)],['Zoom out',()=>pointcloudView.zoom=Math.max(.5,pointcloudView.zoom-.25)],['Reset view',()=>Object.assign(pointcloudView,{yaw:35,pitch:25,zoom:1})]];
  for (const [name,action] of actions) {const button=document.createElement('button');button.type='button';button.textContent=name;button.onclick=()=>{if(pointcloudView){action();drawPointcloud();}};buttons.append(button);}
  holder.append(svg,position,buttons);drawPointcloud();
}
function pointcloudShown(record) {
  const generation=++pointcloudGeneration;pointcloudController?.abort();pointcloudController=null;pointcloudView=null;
  $('pointcloud-inspection').hidden=record.kind!=='pointcloud';$('pointcloud-preview').replaceChildren();$('pointcloud-preview-status').textContent='';
  if(record.kind!=='pointcloud')return;
  $('pointcloud-note').value=record.annotation?.note||'';$('pointcloud-metadata').textContent=JSON.stringify(record.pointcloud,null,2);
  $('pointcloud-download').href='/api/workbench/asset/'+record.id;$('pointcloud-download').download=record.id+'.zip';
  const controller=new AbortController();pointcloudController=controller;
  const owns=()=>generation===pointcloudGeneration&&current?.id===record.id&&current.content_hash===record.content_hash;
  $('pointcloud-preview-status').textContent='Loading bounded point inspection…';
  (async()=>{try {
    const response=await (globalThis.TuldokAuth?.fetch || fetch)('/api/workbench/pointcloud-inspection/'+record.id,{signal:controller.signal});const raw=await response.json();
    if(!response.ok)throw Error(raw.error||'Point inspection unavailable.');
    const value=decodePointcloudInspection(raw,record);if(!owns())return;renderPointcloud(value);
    $('pointcloud-preview-status').textContent=`Showing first ${value.sample_count} of ${value.point_count} points in original order. Native XYZ: ${value.units}, ${value.coordinate_system.frame}, ${value.coordinate_system.handedness}-handed, ${value.coordinate_system.up_axis} up. Display rotation only; original values, colors and normals stay unchanged.`;
  }catch(error){if(owns()&&error.name!=='AbortError')$('pointcloud-preview-status').textContent=error.message;}
  finally{if(pointcloudController===controller)pointcloudController=null;}})();
}
window.addEventListener('pagehide',()=>{++pointcloudGeneration;pointcloudController?.abort();pointcloudController=null;});
async function pointcloudFile(file,maximum,name) {
  if(!file||file.name!==name||!file.size||file.size>maximum)throw Error(`Choose ${name}, at most ${maximum} bytes.`);
  const raw=new Uint8Array(await file.arrayBuffer());let binary='';for(let offset=0;offset<raw.length;offset+=32768)binary+=String.fromCharCode(...raw.subarray(offset,offset+32768));return btoa(binary);
}
$('pointcloud-import-form').addEventListener('submit',async event=>{
  event.preventDefault();if(pointcloudImportBusy)return;pointcloudImportBusy=true;
  const controls=[...$('pointcloud-import-form').querySelectorAll('input,button')];controls.forEach(control=>control.disabled=true);
  const status=$('pointcloud-import-status');
  try {
    status.textContent='Validating original point cloud…';
    const files={'points.ply':await pointcloudFile($('pointcloud-file').files[0],2097152,'points.ply'),'points.json':await pointcloudFile($('pointcloud-manifest').files[0],32768,'points.json')};
    const row=await api('pointcloud-import',{files,name:$('pointcloud-name').value,rights:$('pointcloud-rights').value||'unknown'});
    status.textContent=`Imported ${row.name}: ${row.pointcloud.point_count} points, unreviewed. Open to inspect and review.`;await refresh();
  }catch(error){status.textContent=error.message+' Check the collection before repeating a request whose response was lost.';}
  finally{pointcloudImportBusy=false;controls.forEach(control=>control.disabled=false);}
});
