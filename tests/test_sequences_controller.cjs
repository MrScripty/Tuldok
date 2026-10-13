// File-capture/UI projection proof only; native producer qualification is separate.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element {
  constructor(){this.files=[];this.value='';this.hidden=false;this.textContent='';this.listeners={};this.disabled=false;}
  addEventListener(event,fn){this.listeners[event]=fn;}
}
function fixture(){
  const elements=new Map(),calls=[];
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  $('sequence-import-form').querySelectorAll=()=>[...elements.values()];
  const record={id:'record',kind:'sequence',name:'Captured source',sequence:{manifest:{frame_count:9}},annotation:null};
  const context=vm.createContext({Uint8Array,btoa,$,api:async(route,body)=>{calls.push({route,body});return record;},refresh:async()=>{}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/sequences.js'),'utf8'),context);
  const file=(name,raw)=>({name,size:Buffer.byteLength(raw),arrayBuffer:async()=>Buffer.from(raw)});
  for(const [id,name] of [['sequence-run','run.json'],['sequence-frames','frames.jsonl'],['sequence-controls','controls.json']])$(id).files=[file(name,'captured '+name)];
  $('sequence-name').value='captured name';$('sequence-group').value='family';$('sequence-rights').value='captured rights';
  return {$,calls,context,file,record,submit:()=>$('sequence-import-form').listeners.submit({preventDefault(){}})};
}
(async()=>{
  const f=fixture();let finish;
  f.$('sequence-run').files[0].arrayBuffer=()=>new Promise(resolve=>finish=resolve);
  const running=f.submit();await f.submit();assert.equal(f.calls.length,0);
  f.$('sequence-controls').files=[f.file('controls.json','changed after submit')];f.$('sequence-frames').files=[];f.$('sequence-name').value='changed name';
  finish(Buffer.from('captured run.json'));await running;
  assert.equal(f.calls.length,1);const body=f.calls[0].body;
  assert.equal(body.name,'captured name');assert.equal(body.rights,'captured rights');
  assert.equal(Buffer.from(body.files['controls.json'],'base64').toString(),'captured controls.json');
  assert.equal(Buffer.from(body.files['frames.jsonl'],'base64').toString(),'captured frames.jsonl');
  for(const candidate of [{name:'wrong.json',size:1},{name:'controls.json',size:65537},{name:'controls.json',size:0}]){
    const rejected=fixture();rejected.$('sequence-controls').files=[candidate];await rejected.submit();assert.equal(rejected.calls.length,0);
    assert.match(rejected.$('sequence-import-status').textContent,/Choose controls.json/);
  }
  const v1=fixture();v1.$('sequence-controls').files=[];await v1.submit();assert.equal(Object.hasOwn(v1.calls[0].body.files,'controls.json'),false);
  f.record.sequence.controls_summary={version:2,interval_count:8,axis_order:['x','y','z'],side_order:['low','high'],speed_sign:'source declaration',provenance:{origin:'producer_emitted',author:'Synthetic fixture'},intervals:[{id:'native'}]};
  f.context.sequenceShown(f.record);assert.equal(f.$('sequence-controls-inspection').hidden,false);assert.match(f.$('sequence-controls-summary').textContent,/8 accepted intervals/);
  assert.match(f.$('sequence-controls-detail').textContent,/source declaration/);assert.match(f.$('sequence-download').textContent,/controls.json/);
  f.context.sequenceShown(v1.record);assert.equal(f.$('sequence-controls-inspection').hidden,true);assert.equal(f.$('sequence-controls-detail').textContent,'');
  assert.doesNotMatch(f.$('sequence-download').textContent,/controls.json/);
  console.log('PASS sequence UI: immutable optional-file capture, duplicate fence, bounds, v1 preservation and server-owned controls projection');
})().catch(error=>{console.error(error);process.exitCode=1;});
