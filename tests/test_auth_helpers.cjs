// Fixture credentials must never reach debugger/fake-provider or redirected origins.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const requests=[],files=new Map(),cookies=[];
const filesystem={existsSync:p=>files.has(p),readFileSync:p=>files.get(p),unlinkSync:p=>files.delete(p)};
const context={module:{exports:{}},URL,Headers,Response,globalThis:null,require:name=>{
  if(name==='node:fs')return filesystem;
  if(name==='node:path')return path;
  if(name==='node:crypto')return {randomUUID:()=>String(files.size)};
  if(name==='node:child_process')return {execFileSync:(program,args)=>{assert.equal(program,'python3');assert.deepEqual(Array.from(args.slice(0,2)),['access.py','login']);files.set(args[args.indexOf('--out')+1],'one-time-fixture\n');}};
  throw Error(name);
},fetch:async(input,options={})=>{requests.push({input:String(input),options});if(String(input).endsWith('/api/access/session'))return new Response('{}',{headers:{'Set-Cookie':'tuldok_session=opaque-fixture; HttpOnly; SameSite=Strict; Path=/'}});return new Response('{}');}};
context.globalThis=context;vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'auth_helpers.cjs'),'utf8'),context);
(async()=>{
  const fixture=context.module.exports.authenticatedFixture();await fixture.register('http://127.0.0.1:10001','/fixture/data','/fixture');assert.equal(files.size,0);
  await fixture.fetch('http://127.0.0.1:10001/api/workbench/records',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  let sent=requests.at(-1).options;assert.equal(sent.headers.get('Cookie'),'tuldok_session=opaque-fixture');assert.equal(sent.headers.get('Origin'),'http://127.0.0.1:10001');assert.equal(sent.redirect,'error');
  for(const url of ['http://127.0.0.1:10002/api/workbench/records','http://127.0.0.1:10002/json','http://localhost:10001/api/workbench/records','http://127.0.0.1:10001/fixture/control']){
    await fixture.fetch(url);sent=requests.at(-1).options;assert.equal(new Headers(sent.headers).get('Cookie'),null);assert.equal(new Headers(sent.headers).get('Origin'),null);
  }
  await fixture.browser(async(method,params)=>{cookies.push({method,params});return {success:true};},'http://127.0.0.1:10001');assert.equal(cookies[0].method,'Network.setCookie');assert.equal(cookies[0].params.httpOnly,true);assert.equal(cookies[0].params.sameSite,'Strict');
  await assert.rejects(fixture.browser(async()=>({}),'http://127.0.0.1:10002'),/Register explicit/);
  console.log('PASS auth fixture exact-origin credential boundary, no forwarding to debugger/provider, no redirects, explicit CDP session');
})().catch(error=>{console.error(error);process.exitCode=1;});
