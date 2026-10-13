'use strict';
// Credentials are exchanged once and never retained by application JavaScript.
window.TuldokAuth=(()=>{
  let identity=null,initialResolve,checkedResolve,initial=true,busy=false,checkGeneration=0;
  const checked=new Promise(resolve=>{checkedResolve=resolve;});
  const initialLogin=new Promise(resolve=>{initialResolve=resolve;});
  const $=id=>document.getElementById(id);
  const canReview=()=>identity?.kind==='owner'&&identity.scopes.includes('approve-review');
  function controls(){
    for(const id of ['record-review','response-review','preference-review']){
      const node=$(id);if(!node)continue;
      const denied=!canReview();
      if(denied&&!node.disabled){node.disabled=true;node.dataset.authDisabled='true';}
      if(!denied&&node.dataset.authDisabled){node.disabled=false;delete node.dataset.authDisabled;}
      node.title=denied?'Human review requires an owner session.':'';
    }
  }
  function render(){
    $('session-identity').textContent=identity?`${identity.label} · ${identity.kind}`:'Signed out';
    $('session-logout').hidden=!identity;controls();
  }
  function login(message='Enter the one-time code from your private local login file.'){
    $('session-status').textContent=message;
    if(!$('session-dialog').open)$('session-dialog').showModal();
    $('session-token').focus();
  }
  function notifyFrames(){
    if(window.parent!==window)window.parent.postMessage({type:'tuldok-session-changed'},location.origin);
    for(const frame of document.querySelectorAll('iframe'))frame.contentWindow?.postMessage({type:'tuldok-session-changed'},location.origin);
  }
  function accept(value){
    if(!value||!['owner','agent'].includes(value.kind)||!Array.isArray(value.scopes)||typeof value.label!=='string')throw Error('Unsupported session identity.');
    identity=value;render();window.dispatchEvent(new CustomEvent('tuldok-session',{detail:{kind:value.kind,scopes:[...value.scopes]}}));
  }
  async function check(){
    if(busy)return;const generation=++checkGeneration;
    try{
      const response=await globalThis.fetch('/api/access/session',{credentials:'same-origin',cache:'no-store'});
      if(generation!==checkGeneration)return;
      if(response.status===401){identity=null;render();login();return;}
      const value=await response.json();if(generation!==checkGeneration)return;if(!response.ok)throw Error(value.error||'Session unavailable.');
      accept(value);$('session-dialog').close();initialResolve();initial=false;
    }catch(error){if(generation===checkGeneration){identity=null;render();login(error.message);}}
    finally{checkedResolve();}
  }
  async function request(input,options={}){
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return globalThis.fetch(input,options);
    await checked;
    if(initial){
      if((options.method||(typeof input==='string'?'GET':input.method)||'GET').toUpperCase()!=='GET')return new Response(JSON.stringify({error:'Sign in, then retry this action explicitly.'}),{status:401,headers:{'Content-Type':'application/json'}});
      await initialLogin;
    }
    const generation=checkGeneration;
    const response=await globalThis.fetch(input,{...options,credentials:'same-origin'});
    if(response.status===401&&generation===checkGeneration){identity=null;render();login('Session expired or revoked. Your edits remain here. Sign in, then retry the action explicitly.');}
    return response;
  }
  function mount(){
    const bar=document.createElement('div');bar.className='session-bar';
    bar.innerHTML='<span id="session-identity">Checking session…</span><button id="session-open" type="button">Session</button><button id="session-logout" type="button" hidden>Sign out</button>';
    const dialog=document.createElement('dialog');dialog.id='session-dialog';dialog.setAttribute('aria-labelledby','session-title');
    dialog.innerHTML='<h2 id="session-title">Local session</h2><form id="session-form"><label>One-time login code<input id="session-token" type="password" autocomplete="off" required></label><button id="session-submit">Sign in</button><button id="session-close" type="button">Keep edits</button></form><p id="session-status" role="status"></p><p class="session-help">Generate a private code with <code>python access.py login --data CATALOG --out FILE</code>. Do not share that file.</p>';
    document.body.prepend(bar);document.body.append(dialog);
    $('session-open').onclick=()=>login(identity?'Current session: '+identity.label+'. Enter a new one-time code to change sessions.':undefined);
    $('session-close').onclick=()=>dialog.close();
    $('session-form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;busy=true;++checkGeneration;$('session-submit').disabled=true;
      const token=$('session-token').value;$('session-token').value='';
      try{
        const response=await globalThis.fetch('/api/access/session',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
        const value=await response.json();if(!response.ok)throw Error(value.error||'Login refused.');
        accept(value);dialog.close();initialResolve();initial=false;
        notifyFrames();
      }catch(error){$('session-status').textContent=error.message;}
      finally{busy=false;$('session-submit').disabled=false;}
    };
    $('session-logout').onclick=async()=>{
      if(busy)return;busy=true;++checkGeneration;$('session-logout').disabled=true;
      try{
        const response=await globalThis.fetch('/api/access/logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'});
        if(!response.ok&&response.status!==401)throw Error((await response.json()).error||'Sign out failed.');
        identity=null;render();login('Signed out. Your current edits remain here.');notifyFrames();
      }catch(error){login(error.message);}
      finally{busy=false;$('session-logout').disabled=false;}
    };
    new MutationObserver(controls).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
    window.addEventListener('message',event=>{if(event.origin===location.origin&&event.data?.type==='tuldok-session-changed')check();});
    check();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
  return {fetch:request,identity:()=>identity,canReview};
})();
