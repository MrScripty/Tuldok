'use strict';
let volumeImportBusy=false,volumeGeneration=0;
const volumeRequests=new Map();
function decodeVolumeSlice(value,record,axis,index) {
  const dimensions={z:record.volume.shape[0],y:record.volume.shape[1],x:record.volume.shape[2]};
  const [row,column]={z:['y','x'],y:['z','x'],x:['z','y']}[axis];
  const vector=v=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n));
  if(!value||value.id!==record.id||value.content_hash!==record.content_hash||value.axis!==axis||value.index!==index||
     value.row_axis!==row||value.column_axis!==column||value.units!==record.volume.manifest.units||
     !['physical_origin','physical_row_step','physical_column_step'].every(key=>vector(value[key]))||
     !Array.isArray(value.values)||value.values.length!==dimensions[row]||
     !value.values.every(values=>Array.isArray(values)&&values.length===dimensions[column]&&values.every(n=>Number.isInteger(n)&&n>=0&&n<=255)))throw Error('Invalid native volume slice response.');
  return value;
}
function renderVolumeSlice(value) {
  const canvas=$('volume-canvas-'+value.axis),rows=value.values.length,columns=value.values[0].length;
  canvas.width=columns;canvas.height=rows;
  const context=canvas.getContext('2d'),pixels=context.createImageData(columns,rows);
  for(let row=0;row<rows;row++)for(let column=0;column<columns;column++){
    const offset=(row*columns+column)*4,v=value.values[row][column];pixels.data.set([v,v,v,255],offset);
  }
  context.putImageData(pixels,0,0);
  const vector=v=>v.map(n=>Number(n.toPrecision(7))).join(', ');
  $('volume-position-'+value.axis).textContent=`${value.axis.toUpperCase()} index ${value.index} · rows +${value.row_axis}, columns +${value.column_axis}. Voxel-center origin (${vector(value.physical_origin)}) ${value.units}; row step (${vector(value.physical_row_step)}), column step (${vector(value.physical_column_step)}) ${value.units}.`;
  canvas.setAttribute('aria-label',`Native uint8 slice ${value.axis} index ${value.index}, ${rows} rows along ${value.row_axis}, ${columns} columns along ${value.column_axis}; grayscale maps values 0 to 255. Physical origin ${vector(value.physical_origin)} ${value.units}.`);
  canvas.hidden=false;
}
async function loadVolumeSlice(record,axis,index,generation) {
  volumeRequests.get(axis)?.abort();const controller=new AbortController();volumeRequests.set(axis,controller);
  const owns=()=>volumeRequests.get(axis)===controller&&generation===volumeGeneration&&current?.id===record.id&&current.content_hash===record.content_hash;
  $('volume-canvas-'+axis).hidden=true;$('volume-position-'+axis).textContent='Loading native index slice…';
  try{
    const response=await (globalThis.TuldokAuth?.fetch || fetch)(`/api/workbench/volume-inspection/${record.id}?axis=${axis}&index=${index}`,{signal:controller.signal});const raw=await response.json();
    if(!response.ok)throw Error(raw.error||'Volume slice unavailable.');
    const value=decodeVolumeSlice(raw,record,axis,index);if(owns())renderVolumeSlice(value);
  }catch(error){if(owns()&&error.name!=='AbortError')$('volume-position-'+axis).textContent=error.message;}
  finally{if(volumeRequests.get(axis)===controller)volumeRequests.delete(axis);}
}
function volumeShown(record) {
  const generation=++volumeGeneration;for(const controller of volumeRequests.values())controller.abort();volumeRequests.clear();
  $('volume-inspection').hidden=record.kind!=='volume';$('volume-preview').replaceChildren();$('volume-preview-status').textContent='';
  if(record.kind!=='volume')return;
  $('volume-note').value=record.annotation?.note||'';$('volume-metadata').textContent=JSON.stringify(record.volume,null,2);
  $('volume-download').href='/api/workbench/asset/'+record.id;$('volume-download').download=record.id+'.zip';
  $('volume-preview-status').textContent=`${record.volume.shape.join(' × ')} voxels [z,y,x] · uint8. Three native index planes, not world-axis reslicing. Grayscale 0–255; ${record.volume.manifest.value_semantics}. Physical coordinates use the declared affine (${record.volume.manifest.units}); original voxels stay unchanged.`;
  for(const [offset,axis] of ['z','y','x'].entries()){
    const figure=document.createElement('figure');figure.className='volume-slice';
    const label=document.createElement('label');label.textContent=axis.toUpperCase()+' index';
    const slider=document.createElement('input');slider.type='range';slider.id='volume-index-'+axis;slider.min='0';slider.max=String(record.volume.shape[offset]-1);slider.step='1';slider.value='0';
    // View position never becomes an annotation edit or resets human review.
    slider.addEventListener('input',event=>{event.stopPropagation();loadVolumeSlice(record,axis,Number(slider.value),generation);});
    label.append(slider);
    const canvas=document.createElement('canvas');canvas.id='volume-canvas-'+axis;canvas.setAttribute('role','img');canvas.style.cssText='display:block;max-width:100%;width:240px;image-rendering:pixelated;background:#eee';
    const status=document.createElement('p');status.id='volume-position-'+axis;status.setAttribute('role','status');
    figure.append(label,canvas,status);$('volume-preview').append(figure);loadVolumeSlice(record,axis,0,generation);
  }
}
window.addEventListener('pagehide',()=>{++volumeGeneration;for(const controller of volumeRequests.values())controller.abort();volumeRequests.clear();});
async function volumeFile(file,maximum,name) {
  if(!file||file.name!==name||!file.size||file.size>maximum)throw Error(`Choose ${name}, at most ${maximum} bytes.`);
  const raw=new Uint8Array(await file.arrayBuffer());let binary='';for(let offset=0;offset<raw.length;offset+=32768)binary+=String.fromCharCode(...raw.subarray(offset,offset+32768));return btoa(binary);
}
$('volume-import-form').addEventListener('submit',async event=>{
  event.preventDefault();if(volumeImportBusy)return;volumeImportBusy=true;
  const controls=[...$('volume-import-form').querySelectorAll('input,button')];controls.forEach(control=>control.disabled=true);
  const status=$('volume-import-status');
  try{
    status.textContent='Validating original uint8 volume…';
    const files={'volume.npy':await volumeFile($('volume-file').files[0],2101258,'volume.npy'),'volume.json':await volumeFile($('volume-manifest').files[0],32768,'volume.json')};
    const row=await api('volume-import',{files,name:$('volume-name').value,rights:$('volume-rights').value||'unknown'});
    status.textContent=`Imported ${row.name}: ${row.volume.voxel_count} voxels, unreviewed. Open to inspect and review.`;await refresh();
  }catch(error){status.textContent=error.message+' Check the collection before repeating a request whose response was lost.';}
  finally{volumeImportBusy=false;controls.forEach(control=>control.disabled=false);}
});
