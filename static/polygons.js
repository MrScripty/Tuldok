'use strict';
let polygonPointer = null, polygonTask = '';
const polygonNumberSources=new WeakMap(),polygonNumber=/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/;
async function polygonReadResponse(response,result) {
  const records=Array.isArray(result.items)?result.items:[result.record||result];
  const raw=await response.text();
  if(!records.some(r=>r.task==='image_segmentation'&&r.annotation?.instances?.length)) return;
  const source=JSON.parse(raw,(_key,value,context)=>{
    if(typeof value!=='number') return value;
    if(!context?.source) throw Error('This browser cannot preserve source coordinate primitives. Use a browser with JSON parse source support.');
    return context.source;
  });
  const originals=Array.isArray(source.items)?source.items:[source.record||source];
  records.forEach((record,i)=>{
    if(record.task!=='image_segmentation') return;
    record.annotation.instances.forEach((target,j)=>polygonNumberSources.set(target,originals[i].annotation.instances[j].points));
  });
}
function polygonRequestBody(body) {
  const instances=body.annotation.instances.map(target=>{
    const sources=polygonNumberSources.get(target);
    const points=target.points.map((point,i)=>'['+point.map((value,j)=>{
      const token=sources?.[i]?.[j];
      if(token!==undefined) {
        if(!polygonNumber.test(token)||!Number.isFinite(Number(token))||!Object.is(Number(token),value)) throw Error('Polygon coordinate evidence changed. Reload or explicitly reauthor this instance.');
        return token;
      }
      return Object.is(value,-0)?'-0.0':JSON.stringify(value);
    }).join(',')+']').join(',');
    return '{"label":'+JSON.stringify(target.label)+',"points":['+points+']}';
  }).join(',');
  const annotation='{"instances":['+instances+']}';
  return '{'+Object.entries(body).map(([key,value])=>JSON.stringify(key)+':'+(key==='annotation'?annotation:JSON.stringify(value))).join(',')+'}';
}
function polygonPending() { return $('polygon-points').value.length > 0; }
function polygonShown(record) {
  if(record.task==='image_segmentation') targets.forEach((target,i)=>{
    const sources=polygonNumberSources.get(record.annotation?.instances[i]);
    if(sources) polygonNumberSources.set(target,sources);
  });
  polygonPointer = null; polygonTask = record.task; $('polygon-points').value = '';
  $('polygon-status').textContent = 'Single simple rings, 3–128 vertices; at most 100 instances and 1,024 total vertices. Closure is implicit.';
}
function polygonTaskChange() {
  const next = $('task').value;
  if(next !== polygonTask && (polygonPending() || polygonPointer) && !confirm('Discard the unfinished polygon vertices before changing task?')) {
    $('task').value = polygonTask; return false;
  }
  polygonPointer = null;
  if(next !== polygonTask) $('polygon-points').value = '';
  polygonTask = next; return true;
}
function polygonControls(task) {
  const active=task==='image_segmentation';$('polygon-controls').hidden=!active;
  // Enlarge tiny sources while preserving aspect ratio and matching SVG extent.
  $('image-frame').style.width=active&&current?.kind==='image'?`min(100%, ${Math.min(420,460*current.width/current.height)}px)`:'';
  $('asset-image').style.width=active?'100%':'';
}
function polygonSaveCheck() {
  if(polygonPointer) throw Error('Finish or cancel the active polygon capture before saving the annotation.');
  if(polygonPending()) throw Error('Add the unfinished polygon or clear its vertices before saving the annotation.');
}
function polygonPoints() {
  const lines = $('polygon-points').value.split(/\r?\n/).filter(line=>line.trim());
  if(lines.length<3 || lines.length>128) throw Error('Enter 3–128 vertices, one x,y pair per line. Do not repeat the closing vertex.');
  return lines.map(line=>{
    const parts=line.split(',');
    if(parts.length!==2 || parts.some(part=>!part.trim())) throw Error('Each vertex needs exactly two finite coordinates: x,y.');
    const point=parts.map(Number);
    if(point.some(v=>!Number.isFinite(v)) || point[0]<0 || point[1]<0 || point[0]>current.width || point[1]>current.height)
      throw Error('Vertices must fit the oriented image pixel edges.');
    return point;
  });
}
action('add-polygon',()=>{
  if(!current || $('task').value!=='image_segmentation' || $('editor').dataset.busy || (typeof rightsBusy!=='undefined' && rightsBusy)) return;
  const points=polygonPoints(),sources=$('polygon-points').value.split(/\r?\n/).filter(line=>line.trim()).map((line,i)=>line.split(',').map((part,j)=>{
    const token=part.trim();return polygonNumber.test(token)?token:Object.is(points[i][j],-0)?'-0.0':JSON.stringify(points[i][j]);
  }));
  if(targets.length>=100 || targets.reduce((n,t)=>n+t.points.length,points.length)>1024) throw Error('Polygon instance/vertex bound exceeded.');
  const target={label:$('label').value,points};polygonNumberSources.set(target,sources);
  targets.push(target); $('polygon-points').value='';markDirty();renderTargets();
  $('polygon-status').textContent='Polygon added to the draft. Save, reopen and review its exact vertices; server validation rejects intersecting or degenerate rings.';
});
action('clear-polygon',()=>{
  if($('editor').dataset.busy || (typeof rightsBusy!=='undefined' && rightsBusy)) return;
  polygonPointer=null;$('polygon-points').value='';markDirty();$('polygon-status').textContent='Pending vertices cleared. Saved instances are unchanged until you save.';
});
function polygonCaptureReady(image) {
  return current?.kind==='image' && $('task').value==='image_segmentation' && !$('editor').dataset.busy
    && !(typeof rightsBusy!=='undefined' && rightsBusy) && !image.hidden && image.complete
    && image.naturalWidth===current.width && image.naturalHeight===current.height
    && image.currentSrc===new URL('/api/workbench/asset/'+current.id+'?revision='+current.source_revision,location.href).href;
}
$('asset-image').addEventListener('pointerdown',event=>{
  const image=event.currentTarget;
  if(!event.isPrimary || event.button!==0 || !polygonCaptureReady(image) || polygonPointer) return;
  // Capture initiation is editor intent: an older Open must not adopt its result.
  ++editorEpoch;
  polygonPointer={pointer:event.pointerId,id:current.id,source:current.source_revision,epoch:editorEpoch,src:image.currentSrc};
  image.setPointerCapture(event.pointerId);event.preventDefault();
});
$('asset-image').addEventListener('pointerup',event=>{
  const held=polygonPointer,image=event.currentTarget;
  if(!held || event.pointerId!==held.pointer) return;
  polygonPointer=null;
  if(!event.isPrimary || event.button!==0 || !polygonCaptureReady(image) || current.id!==held.id
     || current.source_revision!==held.source || editorEpoch!==held.epoch || image.currentSrc!==held.src) return;
  const rectangle=image.getBoundingClientRect(),x=(event.clientX-rectangle.left)*current.width/rectangle.width,y=(event.clientY-rectangle.top)*current.height/rectangle.height;
  if(!Number.isFinite(x)||!Number.isFinite(y)||x<0||y<0||x>current.width||y>current.height) return;
  if($('polygon-points').value.split(/\r?\n/).filter(line=>line.trim()).length>=128) {notice('At most 128 pending vertices.',true);return;}
  const line=`${x},${y}`;
  if($('polygon-points').value.length+line.length+1>8192) {notice('Pending vertex text exceeds its bound.',true);return;}
  $('polygon-points').value+=($('polygon-points').value?'\n':'')+line;
  $('polygon-points').dispatchEvent(new Event('input',{bubbles:true}));
  $('polygon-status').textContent='Exact native pixel-edge vertex captured. Add the polygon when complete; coordinates are never rounded or clipped.';
});
for(const name of ['pointercancel','lostpointercapture']) $('asset-image').addEventListener(name,event=>{
  if(polygonPointer?.pointer===event.pointerId) polygonPointer=null;
});
