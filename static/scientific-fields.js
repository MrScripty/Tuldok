'use strict';
let scientificGeneration=0,scientificController=null,scientificSlice=null;
function scientificShape(record,field) {
  const shape=[...record.field_sequence.manifest.grid.shape_xyz];
  if(field.centering.startsWith('face_'))shape['xyz'.indexOf(field.centering.slice(5))]++;
  return shape.reverse();
}
function decodeScientificSlice(value,record,request) {
  const manifest=record.field_sequence.manifest,field=manifest.fields.find(item=>item.id===request.field),shape=scientificShape(record,field);
  const dimensions={z:shape[0],y:shape[1],x:shape[2]},[row,column]={z:['y','x'],y:['z','x'],x:['z','y']}[request.axis];
  const vector=v=>Array.isArray(v)&&v.length===3&&v.every(n=>typeof n==='number'&&Number.isFinite(n));
  if(!value||value.id!==record.id||value.content_hash!==record.content_hash||value.frame!==request.frame||value.field!==request.field||
    value.axis!==request.axis||value.index!==request.index||value.time!==manifest.frames[request.frame].time||value.time_units!==manifest.time_units||
    value.units!==field.units||value.stage!==field.stage||value.centering!==field.centering||value.dtype!==field.dtype||
    !value.grid||value.grid.units!==manifest.grid.units||!Array.isArray(value.shape_zyx)||value.shape_zyx.length!==3||!shape.every((n,i)=>value.shape_zyx[i]===n)||value.row_axis!==row||value.column_axis!==column||
    !['physical_origin','physical_row_step','physical_column_step'].every(key=>vector(value[key]))||
    !Array.isArray(value.values)||value.values.length!==dimensions[row]||!value.values.every(values=>Array.isArray(values)&&values.length===dimensions[column]&&values.every(n=>typeof n==='number'&&Number.isFinite(n))))throw Error('Invalid scientific field slice response.');
  return value;
}
function scientificProbe() {
  if(!scientificSlice)return;
  const row=Number($('scientific-row').value),column=Number($('scientific-column').value),value=scientificSlice;
  if(!Number.isInteger(row)||!Number.isInteger(column)||row<0||column<0||row>=value.values.length||column>=value.values[0].length){$('scientific-probe').textContent='Choose an in-bounds row and column.';return;}
  const physical=value.physical_origin.map((n,i)=>n+row*value.physical_row_step[i]+column*value.physical_column_step[i]);
  $('scientific-probe').textContent=`Row ${row}, column ${column}: ${Object.is(value.values[row][column],-0)?'-0':String(value.values[row][column])} ${value.units} · physical (${physical.join(', ')}) ${value.grid.units}.`;
}
function drawScientificSlice(value) {
  scientificSlice=value;
  const canvas=$('scientific-canvas'),rows=value.values.length,columns=value.values[0].length;
  canvas.width=columns;canvas.height=rows;
  let low=Infinity,high=-Infinity;for(const row of value.values)for(const number of row){low=Math.min(low,number);high=Math.max(high,number);}
  const scale=Math.max(Math.abs(low),Math.abs(high)),range=scale?high/scale-low/scale:0;
  const ctx=canvas.getContext('2d'),pixels=ctx.createImageData(columns,rows);
  for(let row=0;row<rows;row++)for(let column=0;column<columns;column++){
    const gray=range?Math.round(255*(value.values[row][column]/scale-low/scale)/range):128;pixels.data.set([gray,gray,gray,255],(row*columns+column)*4);
  }
  ctx.putImageData(pixels,0,0);canvas.hidden=false;
  canvas.setAttribute('aria-label',`Scientific index slice ${value.axis} ${value.index}; rows +${value.row_axis}, columns +${value.column_axis}; display-only grayscale range ${low} to ${high} ${value.units}.`);
  $('scientific-status').textContent=`Frame ${value.frame} · time ${value.time} ${value.time_units} · ${value.centering} · ${value.dtype} · ${value.units}. Producer-declared stage: ${value.stage}.`;
  $('scientific-coordinates').textContent=`${value.axis.toUpperCase()} index ${value.index}; rows +${value.row_axis}, columns +${value.column_axis}. Sample origin (${value.physical_origin.join(', ')}) ${value.grid.units}; row step (${value.physical_row_step.join(', ')}), column step (${value.physical_column_step.join(', ')}). Display range ${low} to ${high}; original floats stay unchanged.`;
  $('scientific-row').max=String(rows-1);$('scientific-column').max=String(columns-1);
  $('scientific-row').value='0';$('scientific-column').value='0';scientificProbe();
}
function scientificShown(record) {
  const generation=++scientificGeneration;scientificController?.abort();scientificController=null;scientificSlice=null;
  $('scientific-inspection').hidden=record.kind!=='field_sequence';$('scientific-canvas').hidden=true;$('scientific-probe').textContent='';$('scientific-coordinates').textContent='';
  if(record.kind!=='field_sequence')return;
  const manifest=record.field_sequence.manifest;
  $('scientific-note').value=record.annotation?.note||'';$('scientific-metadata').textContent=JSON.stringify(record.field_sequence,null,2);
  $('scientific-download').href='/api/workbench/asset/'+record.id;$('scientific-download').download=record.id+'.zip';
  for(const [id,items] of [['scientific-frame',manifest.frames.map((frame,i)=>({value:String(i),label:`${i} · ${frame.time} ${manifest.time_units}`}))],['scientific-field',manifest.fields.map(field=>({value:field.id,label:field.label}))]]){
    $(id).replaceChildren();for(const item of items){const option=document.createElement('option');option.value=item.value;option.textContent=item.label;$(id).append(option);}
  }
  $('scientific-axis').value='z';$('scientific-index').value='0';
  const load=async reset=>{
    scientificController?.abort();const controller=new AbortController();scientificController=controller;scientificSlice=null;
    const field=manifest.fields.find(item=>item.id===$('scientific-field').value),shape=scientificShape(record,field),axis=$('scientific-axis').value;
    $('scientific-index').max=String(shape['zyx'.indexOf(axis)]-1);if(reset||Number($('scientific-index').value)>Number($('scientific-index').max))$('scientific-index').value='0';
    const request={frame:Number($('scientific-frame').value),field:field.id,axis,index:Number($('scientific-index').value)};
    const owns=()=>generation===scientificGeneration&&scientificController===controller&&current?.id===record.id&&current.content_hash===record.content_hash;
    $('scientific-canvas').hidden=true;$('scientific-status').textContent='Loading exact numeric slice…';$('scientific-probe').textContent='';$('scientific-coordinates').textContent='';
    try{
      const response=await (globalThis.TuldokAuth?.fetch || fetch)('/api/workbench/records/'+record.id+'/scientific?'+new URLSearchParams(request),{signal:controller.signal}),raw=await response.json();
      if(!response.ok)throw Error(raw.error||'Scientific slice unavailable.');
      const value=decodeScientificSlice(raw,record,request);if(owns())drawScientificSlice(value);
    }catch(error){if(owns()&&error.name!=='AbortError')$('scientific-status').textContent=error.message;}
    finally{if(scientificController===controller)scientificController=null;}
  };
  for(const id of ['scientific-frame','scientific-field','scientific-axis','scientific-index']){
    $(id).oninput=event=>event.stopPropagation();
    $(id).onchange=event=>{event.stopPropagation();load(id==='scientific-field'||id==='scientific-axis');};
  }
  for(const id of ['scientific-row','scientific-column'])$(id).oninput=event=>{event.stopPropagation();scientificProbe();};
  load(true);
}
window.addEventListener('pagehide',()=>{++scientificGeneration;scientificController?.abort();scientificController=null;});
