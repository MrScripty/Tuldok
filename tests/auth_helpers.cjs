// Explicit real authority fixtures. No server hooks, runtime test modes, or global fetch patch.
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
function authenticatedFixture(){
  const sessions=new Map();
  async function register(origin,data,root){
    origin=new URL(origin).origin;
    if(sessions.has(origin))return;
    const file=path.join(path.dirname(data),'owner-login-'+crypto.randomUUID()+'.txt');
    let token;
    try{
      execFileSync('python3',['access.py','login','--data',data,'--out',file],{cwd:root,stdio:['ignore','pipe','pipe']});
      token=fs.readFileSync(file,'utf8').trim();
    }finally{if(fs.existsSync(file))fs.unlinkSync(file);}
    const response=await globalThis.fetch(origin+'/api/access/session',{method:'POST',redirect:'error',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({token})});
    token=null;
    if(!response.ok)throw Error('Fixture owner session exchange failed: HTTP '+response.status);
    const cookie=response.headers.get('set-cookie');
    if(!cookie||!cookie.toLowerCase().includes('httponly'))throw Error('Fixture login did not issue HttpOnly session cookie');
    const pair=cookie.split(';')[0],position=pair.indexOf('=');
    sessions.set(origin,{name:pair.slice(0,position),value:pair.slice(position+1),cookie:pair});
    await response.json();
  }
  async function fetch(input,options={}){
    const url=new URL(typeof input==='string'?input:input.url),session=sessions.get(url.origin);
    if(!session||!(url.pathname.startsWith('/api/')))return globalThis.fetch(input,options);
    const headers=new Headers(options.headers);headers.set('Cookie',session.cookie);headers.set('Origin',url.origin);
    return globalThis.fetch(input,{...options,headers,redirect:'error'});
  }
  async function browser(send,origin){
    origin=new URL(origin).origin;const session=sessions.get(origin);
    if(!session)throw Error('Register explicit application credentials before browser navigation');
    const result=await send('Network.setCookie',{name:session.name,value:session.value,url:origin+'/',httpOnly:true,sameSite:'Strict',path:'/'});
    if(result.success===false)throw Error('Browser fixture session cookie refused');
  }
  return {register,fetch,browser};
}
module.exports={authenticatedFixture};
