// Projection/lifecycle evidence only; browser_meshes proves real browser geometry.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
  constructor(){this.children=[];this.attrs={};this.value='';this.listeners={};}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  setAttribute(key,value){this.attrs[key]=value;}
  addEventListener(name,fn){this.listeners[name]=fn;}
  querySelectorAll(){return [];}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const requests=[],listeners={};
const context=vm.createContext({AbortController,console,document:{createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener:(name,fn)=>listeners[name]=fn},$:element,current:null,
  fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve})),api:()=>{throw Error('Unexpected import');},refresh:async()=>{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/meshes.js'),'utf8'),context);
const run=source=>vm.runInContext(source,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const record={id:'a'.repeat(32),kind:'mesh',content_hash:'b'.repeat(64),annotation:{note:'Original note'},mesh:{triangle_count:1,vertex_count:3,
  bounds:{max:[1e-320,1e-320,1],min:[0,0,0]},manifest:{units:'m',coordinate_system:{frame:'tiny',handedness:'right',up_axis:'z'}}}};
const payload={id:record.id,content_hash:record.content_hash,bounds:{min:[0,0,0],max:[1e-320,1e-320,1]},units:'m',coordinate_system:{up_axis:'z',frame:'tiny',handedness:'right'},triangle_count:1,sample_count:1,triangles:[[[0,0,0],[1e-320,0,1],[0,1e-320,0]]]};
const reply=(request,value,ok=true)=>request.resolve({ok,json:async()=>value});
function show(value){context.current=value;context.fixture=value;run('meshShown(fixture)');}
(async()=>{
  show(record);const first=requests.shift();
  show({...record,annotation:{note:'Later same-ID note'}});const newer=requests.shift();assert.equal(first.options.signal.aborted,true);
  reply(newer,payload);await flush();assert.equal(element('mesh-projections').children.length,3);
  element('mesh-note').value='Unsaved note';reply(first,payload);await flush();assert.equal(element('mesh-note').value,'Unsaved note');
  for(const figure of element('mesh-projections').children){assert.match(figure.children[0].textContent,/m · tiny/);assert.ok(figure.children[1].attrs['aria-label']);for(const polygon of figure.children[1].children)assert.ok(!/Infinity|NaN/.test(polygon.attrs.points));}
  show(record);const stale=requests.shift();show({id:'c'.repeat(32),kind:'text'});reply(stale,{error:'Stale unavailable'},false);await flush();assert.equal(element('mesh-inspection').hidden,true);assert.equal(element('mesh-preview-status').textContent,'');
  show(record);reply(requests.shift(),{...payload,content_hash:'0'.repeat(64)});await flush();assert.equal(element('mesh-preview-status').textContent,'Invalid geometry inspection response.');assert.equal(element('mesh-projections').children.length,0);
  show(record);const shutdown=requests.shift();listeners.pagehide();assert.equal(shutdown.options.signal.aborted,true);reply(shutdown,payload);await flush();assert.equal(element('mesh-projections').children.length,0);
  console.log('Mesh projection/controller: finite tiny-coordinate wireframes, key-order-independent proof, same-ID/leave/shutdown fencing and malformed-response rejection preserve note ownership.');
})().catch(error=>{console.error(error);process.exitCode=1;});
