// Projection/lifecycle evidence only; browser_pointclouds proves real browser geometry.
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
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/pointclouds.js'),'utf8'),context);
const run=source=>vm.runInContext(source,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const properties=[{name:'x',dtype:'double'},{name:'y',dtype:'float'},{name:'z',dtype:'double'}];
const record={id:'a'.repeat(32),kind:'pointcloud',content_hash:'b'.repeat(64),annotation:{note:'Original point note'},pointcloud:{point_count:2,properties,bounds:{max:[5e-324,5e-324,1],min:[0,0,0]},manifest:{units:'mm',coordinate_system:{frame:'tiny',handedness:'right',up_axis:'z'}}}};
const payload={id:record.id,content_hash:record.content_hash,bounds:{min:[0,0,0],max:[5e-324,5e-324,1]},units:'mm',coordinate_system:{up_axis:'z',frame:'tiny',handedness:'right'},point_count:2,sample_count:2,properties,points:[[0,0,0],[5e-324,0,1]]};
const reply=(request,value,ok=true)=>request.resolve({ok,json:async()=>value});
function show(value){context.current=value;context.fixture=value;run('pointcloudShown(fixture)');}
(async()=>{
 show(record);const first=requests.shift();show({...record,annotation:{note:'Later same-ID point note'}});const newer=requests.shift();assert.equal(first.options.signal.aborted,true);reply(newer,payload);await flush();assert.equal(element('pointcloud-projections').children.length,3);
 element('pointcloud-note').value='Unsaved point note';reply(first,payload);await flush();assert.equal(element('pointcloud-note').value,'Unsaved point note');
 for(const figure of element('pointcloud-projections').children){assert.match(figure.children[0].textContent,/mm · tiny/);for(const circle of figure.children[1].children){const {cx,cy}=circle.attrs;assert.ok(Number.isFinite(Number(cx))&&Number.isFinite(Number(cy)));assert.ok(cx>=0&&cx<=240&&cy>=0&&cy<=220);}}
 show(record);const stale=requests.shift();show({id:'c'.repeat(32),kind:'mesh'});reply(stale,{error:'Stale point source'},false);await flush();assert.equal(element('pointcloud-inspection').hidden,true);assert.equal(element('pointcloud-preview-status').textContent,'');
 const malformed=[{...payload,content_hash:'0'.repeat(64)},{...payload,sample_count:1},{...payload,properties:[{name:'y',dtype:'double'},...properties.slice(1)]},{...payload,points:[[NaN,0,0],[0,0,0]]},{...payload,bounds:{min:[0,0,0],max:[1,1,1]}},{...payload,extra:true}];
 for(const value of malformed){show(record);reply(requests.shift(),value);await flush();assert.equal(element('pointcloud-preview-status').textContent,'Invalid point-cloud inspection response.');assert.equal(element('pointcloud-projections').children.length,0);}
 const zero={...record,pointcloud:{...record.pointcloud,bounds:{min:[0,0,0],max:[0,0,0]}}};show(zero);reply(requests.shift(),{...payload,bounds:zero.pointcloud.bounds,points:[[0,0,0],[0,0,0]]});await flush();for(const figure of element('pointcloud-projections').children)for(const circle of figure.children[1].children){assert.equal(circle.attrs.cx,120);assert.equal(circle.attrs.cy,110);}
 show(record);const shutdown=requests.shift();listeners.pagehide();assert.equal(shutdown.options.signal.aborted,true);reply(shutdown,payload);await flush();assert.equal(element('pointcloud-projections').children.length,0);
 console.log('Point-cloud controller: bounded native metadata association, tiny/zero-span finite projections, malformed data and same-ID/kind/shutdown ownership PASS.');
})().catch(error=>{console.error(error);process.exitCode=1;});
