// Session ownership and no-replay behavior; transport fixture, not authentication proof.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const nodes=new Map(),handlers=new Map(),requests=[],answers=[];
class Element{
  constructor(){this.value='';this.dataset={};this.disabled=false;this.open=false;}
  set id(value){nodes.set(value,this);}
  set innerHTML(value){for(const match of value.matchAll(/id="([^"]+)"/g))if(!nodes.has(match[1]))nodes.set(match[1],new Element());}
  setAttribute(){} focus(){} showModal(){this.open=true;} close(){this.open=false;}
}
for(const id of ['record-review','response-review','preference-review'])nodes.set(id,new Element());
const doc={readyState:'complete',getElementById:id=>nodes.get(id),createElement:()=>new Element(),querySelectorAll:()=>[],body:{prepend(){},append(){}}};
const owner={label:'Owner',kind:'owner',scopes:['inspect','edit','approve-review']},agent={label:'Agent',kind:'agent',scopes:['inspect','edit']};
const defer=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const reply=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const initial=defer();answers.push(initial.promise);
const context={document:doc,URL,Response,CustomEvent:class{},MutationObserver:class{observe(){}},location:{origin:'http://localhost:8091',href:'http://localhost:8091/workbench'},fetch:(input,options={})=>{requests.push({input,options});assert.ok(answers.length,'Unexpected fetch');return answers.shift();},addEventListener:(name,fn)=>handlers.set(name,fn),dispatchEvent(){},postMessage(){},window:null,globalThis:null};context.window=context;context.parent=context;context.globalThis=context;
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/auth.js'),'utf8'),context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function login(identity){nodes.get('session-token').value='private-code';answers.push(Promise.resolve(reply(identity)));await nodes.get('session-form').onsubmit({preventDefault(){}});assert.equal(nodes.get('session-token').value,'');}
(async()=>{
  initial.resolve(reply({error:'sign in'},401));await tick();
  const count=requests.length;const blocked=await context.TuldokAuth.fetch(new Request('http://localhost:8091/api/workbench/import',{method:'POST',body:'{}'}));assert.equal(blocked.status,401);assert.equal(requests.length,count,'Initial POST Request is refused before sending');
  await login(owner);assert.equal(context.TuldokAuth.identity().kind,'owner');
  // An older identity lookup must not replace the later successful login.
  const stale=defer();answers.push(stale.promise);handlers.get('message')({origin:context.location.origin,data:{type:'tuldok-session-changed'}});
  await login(agent);stale.resolve(reply(owner));await tick();assert.equal(context.TuldokAuth.identity().kind,'agent');assert.equal(nodes.get('record-review').disabled,true);
  // An old rejected write still returns its rejection, but cannot log out a newer session.
  const rejected=defer();answers.push(rejected.promise);const attempt=context.TuldokAuth.fetch('/api/workbench/import',{method:'POST',body:'{}'});await tick();await login(owner);rejected.resolve(reply({error:'expired'},401));assert.equal((await attempt).status,401);assert.equal(context.TuldokAuth.identity().kind,'owner');assert.equal(nodes.get('record-review').disabled,false);
  const before=requests.filter(item=>item.input==='/api/workbench/import').length;
  answers.push(Promise.resolve(reply({error:'expired'},401)));assert.equal((await context.TuldokAuth.fetch('/api/workbench/import',{method:'POST',body:'{}'})).status,401);assert.equal(context.TuldokAuth.identity(),null);assert.equal(nodes.get('session-dialog').open,true);
  await login(owner);assert.equal(requests.filter(item=>item.input==='/api/workbench/import').length,before+1,'Login never replays a rejected mutation');
  answers.push(Promise.reject(Error('Session lookup unavailable')));handlers.get('message')({origin:context.location.origin,data:{type:'tuldok-session-changed'}});await tick();assert.equal(context.TuldokAuth.identity(),null);assert.equal(nodes.get('record-review').disabled,true);
  assert.equal(answers.length,0);console.log('PASS auth controller: stale identity/401 ownership, review scopes, code clearing, no mutation replay');
})().catch(error=>{console.error(error);process.exitCode=1;});
