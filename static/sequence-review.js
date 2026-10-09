'use strict';
// Native projection only. Existing editor/review/release owners retain all writes.
let sequenceReviewEpoch=0, sequenceReviewRecord=null, sequenceReviewRequest=null;
let sequenceReviewData=null, sequenceReviewFrame=0, sequenceReviewTimer=null, sequenceReviewDeparted=false;
const sequenceReviewLimit=128*1024, sequenceReviewAxes=['x','y','z'];
function sequenceReviewStop(){if(sequenceReviewTimer!==null)clearInterval(sequenceReviewTimer);sequenceReviewTimer=null;$('sequence-review-play').textContent='Play frames';}
function sequenceReviewInvalidate(message='Choose a native field and plane, then explicitly load all nine frames.'){
  ++sequenceReviewEpoch;sequenceReviewRequest?.controller.abort();sequenceReviewRequest=null;
  sequenceReviewStop();sequenceReviewData=null;sequenceReviewFrame=0;
  $('sequence-review-view').hidden=true;$('sequence-review-append').disabled=true;
  $('sequence-review-load').disabled=false;$('sequence-review-cancel').disabled=true;
  $('sequence-review-status').textContent=message;
}
function sequenceReviewShown(record){
  sequenceReviewInvalidate();sequenceReviewRecord=record.kind==='sequence'?structuredClone(record):null;
  $('sequence-review').hidden=!sequenceReviewRecord;sequenceReviewBounds();
}
function sequenceReviewBounds(){
  const shape=sequenceReviewRecord?.sequence?.manifest?.geometry?.field_shapes?.[$('sequence-review-field').value];
  if(shape)['i','j','k'].forEach((axis,j)=>$('sequence-review-'+axis).max=shape[j]-1);
}
function sequenceReviewSame(a,b){
  if(typeof a!==typeof b||a===null||b===null)return a===b;
  if(typeof a==='number')return Number.isFinite(a)&&a===b;
  if(typeof a!=='object')return a===b;
  if(Array.isArray(a)!==Array.isArray(b))return false;
  const keys=Object.keys(a),other=Object.keys(b);
  return keys.length===other.length&&keys.every(key=>Object.hasOwn(b,key)&&sequenceReviewSame(a[key],b[key]));
}
function sequenceReviewRequire(value,message){if(!value)throw Error('Invalid trajectory response: '+message+'.');}
function sequenceReviewKeys(value,keys){sequenceReviewRequire(value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key)),'closed object keys');}
function sequenceReviewInterval(entries,k){
  if(!k)return null;const a=entries[k-1],b=entries[k];
  return {start_frame:k-1,end_frame:k,start_time_s:a.time_s,end_time_s:b.time_s,dt_s:b.dt_s,
    carrier_before:a.carrier_stamp,carrier_after:b.carrier_stamp,liquid_before:a.liquid_stamp,liquid_after:b.liquid_stamp};
}
function sequenceReviewValidate(data,record,body){
  sequenceReviewKeys(data,['id','revision','source_revision','content_hash','scope','adapter','run_sha256','frames_sha256','geometry','pressure_semantics','field','plane','controls','frames']);
  for(const key of ['id','revision','source_revision','content_hash'])sequenceReviewRequire(sequenceReviewSame(data[key],record[key]),'record '+key);
  const metadata=record.sequence,manifest=metadata.manifest,geometry=manifest.geometry;
  for(const [key,value] of Object.entries({scope:metadata.scope,adapter:metadata.adapter,run_sha256:metadata.run_sha256,frames_sha256:manifest.frames_sha256,geometry,pressure_semantics:manifest.pressure_semantics}))sequenceReviewRequire(sequenceReviewSame(data[key],value),key+' association');
  const name=body.field,shape=geometry.field_shapes[name],normal=sequenceReviewAxes.indexOf(body.plane_axis),axes=[0,1,2].filter(j=>j!==normal);
  const offset=name.startsWith('velocity_')?geometry.face_offsets[name.at(-1)]:geometry.cell_offset;
  const units=manifest.units[name.startsWith('velocity_')?'velocity':name];
  sequenceReviewRequire(sequenceReviewSame(data.field,{name,shape,dtype:manifest.field_types[name],units,index:body.index,
    flat_index:body.index[0]+shape[0]*(body.index[1]+shape[1]*body.index[2]),location_offset:offset,
    position_m:body.index.map((n,j)=>geometry.origin_m[j]+(n+offset[j])*geometry.spacing_m[j])}),'native field/index/position');
  sequenceReviewRequire(sequenceReviewSame(data.plane,{axis:body.plane_axis,index:body.index[normal],axes:axes.map(j=>sequenceReviewAxes[j]),shape:axes.map(j=>shape[j]),order:'horizontal native index fastest'}),'native plane axes/order');
  sequenceReviewRequire(data.plane.shape[0]*data.plane.shape[1]<=144&&Array.isArray(data.frames)&&data.frames.length===9&&metadata.frame_index.length===9,'bounded nine-frame plane');
  if(manifest.version===2){
    sequenceReviewRequire(sequenceReviewSame(data.controls,{...metadata.controls,scope:'producer_controls_validated',
      units:{time:'s',outward_speed:'m/s',inlet_fraction:'dimensionless',source_rate:'m^3/s',body_acceleration:'m/s^2'},
      limitation:'producer_emitted is declared provenance; file validation does not authenticate actual execution'}),'original controls hash/units/provenance');
  }else sequenceReviewRequire(sequenceReviewSame(data.controls,{scope:'interval_controls_emitted_unavailable',reason:'pinned producer v1 emits no per-interval controls/source/force records'}),'v1 unavailable controls');
  data.frames.forEach((frame,k)=>{
    sequenceReviewKeys(frame,['metadata','accepted_interval','emitted_control','value','minimum','maximum','plane_values']);
    sequenceReviewRequire(sequenceReviewSame(frame.metadata,metadata.frame_index[k])&&frame.metadata.frame===k,'frame index/hash/time/stamp/diagnostics');
    const interval=sequenceReviewInterval(metadata.frame_index,k);
    sequenceReviewRequire(sequenceReviewSame(frame.accepted_interval,interval),'accepted adjacent interval');
    if(k&&manifest.version===2){
      const control=frame.emitted_control;
      sequenceReviewKeys(control,[...Object.keys(interval),'boundary_stamp','inlet_stamp','outward_speed_m_s','inlet_fraction','source_mode','source_rate_m3_s','body_acceleration_m_s2']);
      sequenceReviewRequire(sequenceReviewSame(control,{...interval,boundary_stamp:{id:'47',version:'0'},inlet_stamp:{id:'53',version:'0'},outward_speed_m_s:[[-.25,.25],[0,0],[0,0]],inlet_fraction:[[0,0],[0,0],[0,0]],source_mode:'none',source_rate_m3_s:0,body_acceleration_m_s2:[0,0,0]}),'emitted interval controls and stamps');
    }else sequenceReviewRequire(frame.emitted_control===null,'constructor/v1 no emitted control');
    sequenceReviewRequire(Array.isArray(frame.plane_values)&&frame.plane_values.length===data.plane.shape[0]*data.plane.shape[1],'complete plane count');
    const values=[frame.value,frame.minimum,frame.maximum,...frame.plane_values];
    sequenceReviewRequire(values.every(value=>typeof value==='number'&&Number.isFinite(value)&&(data.field.dtype!=='f32'||Object.is(Math.fround(value),value))),'finite native dtype values');
    sequenceReviewRequire(frame.minimum<=frame.maximum&&[frame.value,...frame.plane_values].every(value=>value>=frame.minimum&&value<=frame.maximum),'native field range');
    const point=body.index[axes[0]]+data.plane.shape[0]*body.index[axes[1]];
    sequenceReviewRequire(Object.is(frame.value,frame.plane_values[point]),'probe/plane association');
  });
  return data;
}
async function sequenceReviewRead(response){
  const reader=response.body?.getReader();if(!reader)throw Error('Trajectory response has no bounded byte stream.');
  const chunks=[];let size=0;
  try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>sequenceReviewLimit)throw Error('Trajectory response exceeds 128 KiB.');chunks.push(value);}}
  catch(error){await reader.cancel().catch(()=>{});throw error;}
  finally{reader.releaseLock();}
  const raw=new Uint8Array(size);let at=0;for(const chunk of chunks){raw.set(chunk,at);at+=chunk.byteLength;}
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
}
function sequenceReviewInput(){
  const name=$('sequence-review-field').value,shape=sequenceReviewRecord.sequence.manifest.geometry.field_shapes[name];
  if(!shape)throw Error('Choose a named native field.');
  const index=['i','j','k'].map((axis,j)=>{const raw=$('sequence-review-'+axis).value;
    if(!/^(0|[1-9][0-9]*)$/.test(raw)||!Number.isSafeInteger(Number(raw))||Number(raw)>=shape[j])throw Error(`Native ${axis} must be an integer from 0 to ${shape[j]-1}.`);return Number(raw);});
  const plane_axis=$('sequence-review-axis').value;if(!sequenceReviewAxes.includes(plane_axis))throw Error('Choose native plane axis x, y or z.');
  return {revision:sequenceReviewRecord.revision,source_revision:sequenceReviewRecord.source_revision,field:name,index,plane_axis};
}
function sequenceReviewCurrent(record){return !sequenceReviewDeparted&&current?.kind==='sequence'&&current.task==='sequence_transport'&&$('task').value==='sequence_transport'&&['id','revision','source_revision','content_hash'].every(key=>current[key]===record[key]);}
$('sequence-review-load').addEventListener('click',async()=>{
  if(sequenceReviewRequest||sequenceReviewDeparted||!sequenceReviewRecord)return;
  sequenceReviewInvalidate();
  const record=sequenceReviewRecord,epoch=sequenceReviewEpoch,controller=new AbortController(),request={controller,epoch};
  sequenceReviewRequest=request;$('sequence-review-load').disabled=true;$('sequence-review-cancel').disabled=false;
  const live=()=>sequenceReviewRequest===request&&epoch===sequenceReviewEpoch&&sequenceReviewCurrent(record);
  $('sequence-review-status').textContent='Verifying original bundle and loading all nine native slices…';
  try{
    const body=sequenceReviewInput(),raw=JSON.stringify(body);if(new TextEncoder().encode(raw).length>4096)throw Error('Trajectory request exceeds 4 KiB.');
    const response=await fetch('/api/workbench/sequence-review/'+encodeURIComponent(record.id),{method:'POST',headers:{'Content-Type':'application/json'},body:raw,signal:controller.signal});
    const data=await sequenceReviewRead(response);if(!live())return;
    if(!response.ok)throw Error(data.error||'Trajectory read failed.');
    const checked=sequenceReviewValidate(data,record,body);if(!live())return;
    sequenceReviewData=checked;sequenceReviewFrame=0;sequenceReviewRender();
    $('sequence-review-status').textContent='Nine verified native slices loaded. Frame navigation stays local. Review and training qualification unchanged.';
  }catch(error){if(live()){sequenceReviewData=null;$('sequence-review-view').hidden=true;$('sequence-review-append').disabled=true;$('sequence-review-status').textContent=error.message+' Retry explicitly after checking inputs.';}}
  finally{if(sequenceReviewRequest===request){sequenceReviewRequest=null;$('sequence-review-load').disabled=false;$('sequence-review-cancel').disabled=true;}}
});
$('sequence-review-cancel').addEventListener('click',()=>sequenceReviewInvalidate('Read canceled. Load explicitly to retry.'));
for(const id of ['field','axis','i','j','k'])for(const event of ['input','change'])$('sequence-review-'+id).addEventListener(event,()=>{sequenceReviewInvalidate();sequenceReviewBounds();});
$('task').addEventListener('change',()=>sequenceReviewInvalidate('Task changed. Reopen the sequence before loading a trajectory.'));
window.addEventListener('pagehide',()=>{sequenceReviewDeparted=true;sequenceReviewInvalidate();sequenceReviewRecord=null;});
window.addEventListener('pageshow',event=>{if(event.persisted){sequenceReviewDeparted=false;sequenceReviewInvalidate('Page restored. Explicitly reload the trajectory; your draft note is retained.');sequenceReviewRecord=current?.kind==='sequence'?structuredClone(current):null;$('sequence-review').hidden=!sequenceReviewRecord;sequenceReviewBounds();}});
function sequenceReviewNumber(value){return Object.is(value,-0)?'-0':String(value);}
function sequenceReviewScale(value,minimum,maximum){
  if(minimum===maximum)return .5;
  const scale=Math.max(Math.abs(minimum),Math.abs(maximum));
  return Math.max(0,Math.min(1,(value/scale-minimum/scale)/(maximum/scale-minimum/scale)));
}
function sequenceReviewSvg(tag,attributes,text){const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;return node;}
function sequenceReviewRender(){
  const data=sequenceReviewData;if(!data)return;
  const k=sequenceReviewFrame,frame=data.frames[k],field=data.field,plane=data.plane;
  $('sequence-review-view').hidden=false;$('sequence-review-append').disabled=false;
  $('sequence-review-frame').value=k;$('sequence-review-prev').disabled=k===0;$('sequence-review-next').disabled=k===8;
  $('sequence-review-label').textContent=`Frame ${k} · time ${sequenceReviewNumber(frame.metadata.time_s)} s · ${field.name} [${field.index.join(', ')}] = ${sequenceReviewNumber(frame.value)} ${field.units}`;
  $('sequence-review-native').textContent=`${field.dtype} · shape [${field.shape.join(', ')}] · native offset [${field.location_offset.join(', ')}] · point [${field.position_m.join(', ')}] m · plane ${plane.axis}=${plane.index}, ${plane.axes.join('/')} · full-field range ${sequenceReviewNumber(frame.minimum)} … ${sequenceReviewNumber(frame.maximum)}`;
  const svg=$('sequence-review-slice');svg.replaceChildren();
  svg.append(sequenceReviewSvg('title',{},`Native ${plane.axes.join('/')} sample plane, frame ${k}; horizontal native index fastest`));
  frame.plane_values.forEach((value,n)=>{const i=n%plane.shape[0],j=Math.floor(n/plane.shape[0]),shade=sequenceReviewScale(value,frame.minimum,frame.maximum);
    const point=sequenceReviewSvg('circle',{cx:25+i*450/Math.max(1,plane.shape[0]-1),cy:225-j*200/Math.max(1,plane.shape[1]-1),r:5,fill:`hsl(${240-240*shade} 75% 42%)`});point.append(sequenceReviewSvg('title',{},`${plane.axes[0]}=${i}, ${plane.axes[1]}=${j}: ${sequenceReviewNumber(value)} ${field.units}`));svg.append(point);});
  const normal=sequenceReviewAxes.indexOf(plane.axis),axes=[0,1,2].filter(j=>j!==normal);
  svg.append(sequenceReviewSvg('circle',{cx:25+field.index[axes[0]]*450/Math.max(1,plane.shape[0]-1),cy:225-field.index[axes[1]]*200/Math.max(1,plane.shape[1]-1),r:9,fill:'none',stroke:'currentColor','stroke-width':2}));
  const trace=$('sequence-review-trace');trace.replaceChildren();trace.append(sequenceReviewSvg('title',{},'Nine-frame native index time trace'));
  const low=Math.min(...data.frames.map(f=>f.value)),high=Math.max(...data.frames.map(f=>f.value)),first=data.frames[0].metadata.time_s,last=data.frames[8].metadata.time_s;
  const points=data.frames.map(f=>[25+450*sequenceReviewScale(f.metadata.time_s,first,last),225-200*sequenceReviewScale(f.value,low,high)]);
  trace.append(sequenceReviewSvg('polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:'currentColor','stroke-width':2}));
  points.forEach(([cx,cy],j)=>{const node=sequenceReviewSvg('circle',{cx,cy,r:j===k?7:4,fill:j===k?'#e16d25':'currentColor'});node.append(sequenceReviewSvg('title',{},`Frame ${j}: ${sequenceReviewNumber(data.frames[j].value)} ${field.units}`));trace.append(node);});
  $('sequence-review-details').textContent=JSON.stringify({frame:frame.metadata,accepted_interval:frame.accepted_interval,emitted_control:frame.emitted_control,controls:data.controls,pressure_semantics:data.pressure_semantics},null,2);
  $('sequence-review-values').textContent=frame.plane_values.map((value,n)=>`${plane.axes[0]}=${n%plane.shape[0]}, ${plane.axes[1]}=${Math.floor(n/plane.shape[0])}: ${sequenceReviewNumber(value)}`).join('\n');
  $('sequence-review-samples').textContent=data.frames.map((f,j)=>`Frame ${j} · ${sequenceReviewNumber(f.metadata.time_s)} s · ${sequenceReviewNumber(f.value)} ${field.units}`).join('\n');
}
function sequenceReviewMove(k){sequenceReviewStop();if(!sequenceReviewData)return;sequenceReviewFrame=Math.max(0,Math.min(8,k));sequenceReviewRender();}
$('sequence-review-prev').addEventListener('click',()=>sequenceReviewMove(sequenceReviewFrame-1));
$('sequence-review-next').addEventListener('click',()=>sequenceReviewMove(sequenceReviewFrame+1));
$('sequence-review-frame').addEventListener('input',()=>sequenceReviewMove(Number($('sequence-review-frame').value)));
$('sequence-review-play').addEventListener('click',()=>{
  if(sequenceReviewTimer!==null){sequenceReviewStop();return;}if(!sequenceReviewData)return;
  if(sequenceReviewFrame===8)sequenceReviewFrame=0;
  $('sequence-review-play').textContent='Pause frames';sequenceReviewRender();
  sequenceReviewTimer=setInterval(()=>{if(!sequenceReviewData||!sequenceReviewCurrent(sequenceReviewRecord)){sequenceReviewStop();return;}sequenceReviewFrame++;sequenceReviewRender();if(sequenceReviewFrame===8)sequenceReviewStop();},500);
});
$('sequence-review-append').addEventListener('click',()=>{
  try{
    if(!sequenceReviewData||!sequenceReviewCurrent(sequenceReviewRecord))throw Error('Reload the current native trajectory before appending a reference.');
    if($('editor').dataset.busy||(typeof rightsBusy!=='undefined'&&rightsBusy)||(typeof responseBusy!=='undefined'&&responseBusy)||(typeof preferenceBusy!=='undefined'&&preferenceBusy)||(typeof captionProposalBusy!=='undefined'&&captionProposalBusy)||(typeof textClassificationProposalBusy!=='undefined'&&textClassificationProposalBusy))throw Error('Wait for the current editor action before appending a reference.');
    const data=sequenceReviewData,frame=data.frames[sequenceReviewFrame],field=data.field;
    const reference=`Native inspection: ${field.name} [${field.index.join(', ')}], frame ${frame.metadata.frame}, time ${sequenceReviewNumber(frame.metadata.time_s)} s, value ${sequenceReviewNumber(frame.value)} ${field.units}; plane ${data.plane.axis}=${data.plane.index}; frame SHA256 ${frame.metadata.sha256}.`;
    const note=$('sequence-note'),old=note.value;if(old.split('\n').includes(reference)){$('sequence-review-status').textContent='This exact inspection reference is already in the draft note.';return;}
    const next=old+(old&&!old.endsWith('\n')?'\n':'')+reference;
    if(/[\uD800-\uDFFF]/u.test(next)||[...next].length>4000)throw Error('The complete review note must contain valid Unicode and at most 4,000 code points. Nothing appended.');
    note.value=next;markDirty();$('sequence-review-status').textContent='Inspection reference appended to the draft note. Save and human review remain separate explicit actions.';
  }catch(error){$('sequence-review-status').textContent=error.message;}
});
