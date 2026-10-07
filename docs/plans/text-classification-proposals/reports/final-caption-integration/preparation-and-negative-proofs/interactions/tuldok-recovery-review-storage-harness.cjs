'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{constructor(id){this.id=id;this.value='';this.children=[];this.dataset={};this.listeners={};}addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}replaceChildren(...children){this.children=children;}append(...children){this.children.push(...children);}async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this,target:this});}}
const root=process.env.TULDOK_SOURCE_ROOT||'/workspace/Tuldok';
const row={id:'a'.repeat(32),name:'Synthetic source',kind:'text',task:'text_classification',text:'Exact synthetic source\r\ne\u0301 😀',annotation:null,revision:1,source_revision:1,content_hash:'hash',source_sha256:'source'};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function storage(){const values=new Map(),log=[];return{values,log,getItem(key){log.push(['get',key]);return values.get(key)??null;},setItem(key,value){log.push(['set',key,value]);values.set(key,value);},removeItem(key){log.push(['remove',key]);values.delete(key);}};}
function harness(persistence,locks={request:async(_name,_options,fn)=>fn()}){
 const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);},requests=[],events={};
 const context=vm.createContext({console,crypto,JSON,URL,navigator:{locks},current:row,editorEpoch:0,responseIntentEpoch:()=>0,hasUnsavedEdits:()=>false,invalidateRelease(){},refresh:async()=>{},showRecord(){},openRecord:async()=>{},localStorage:persistence,
  setTimeout:()=>1,clearTimeout(){},document:{createElement:()=>new Element('')},window:{localStorage:persistence,addEventListener(event,fn){(events[event]||=[]).push(fn);}},
  $:element,api:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
 context.action=(id,fn,event='click')=>element(id).addEventListener(event,fn);
 vm.runInContext(fs.readFileSync(path.join(root,'static/text-classification-proposals.js'),'utf8'),context);
 const run=code=>vm.runInContext(code,context);
 const take=(url,method)=>{const index=requests.findIndex(request=>request.url===url&&(method===undefined||(request.body===undefined?'GET':'POST')===method));assert.notEqual(index,-1,`missing ${method||''} ${url}`);return requests.splice(index,1)[0];};
 const fill=(guidance='Original exact guidance')=>{for(const [id,value] of Object.entries({url:'http://127.0.0.1:9999/v1/',model:'fixture',guidance,seed:'42',labels:'["keep","cancel"]'}))element('text-classification-proposal-'+id).value=value;};
 return{element,requests,run,take,fill,context,events};
}
module.exports={harness,storage,row,flush,root};
