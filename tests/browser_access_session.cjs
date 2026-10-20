'use strict';
const {cdpSession}=require('./browser_cdp_session.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');

// Access-test diagnostics contain phase/method/loader identity, never command parameters.
function accessSession(socket,{timeoutMs=15000,loadTimeoutMs=20000,pollMs=25,onEvent=()=>{}}={}){
  const loads=pageLoadTracker(),events=[];
  let phase='startup',lastMethod=null,terminal=null;
  const session=cdpSession(socket,{timeoutMs,onEvent:message=>{
    loads.observe(message);
    if(message.method==='Page.frameNavigated'&&!message.params.frame.parentId){
      const {id,loaderId}=message.params.frame;events.push({event:'main-frame',frame:id,loader:loaderId});
    }
    if(message.method==='Page.lifecycleEvent'&&message.params.name==='load'){
      events.push({event:'load',frame:message.params.frameId,loader:message.params.loaderId});
    }
    if(events.length>12)events.splice(0,events.length-12);
    onEvent(message);
  }});
  socket.addEventListener('close',()=>{terminal='CDP socket closed';});
  socket.addEventListener('error',()=>{terminal='CDP socket failed';});
  function contextual(error,owner,method){
    return Object.assign(new Error(`Access browser [${owner}] ${method}: ${error.message}`,{cause:error}),{code:error.code});
  }
  async function send(method,params={},budgetMs){
    const owner=phase;lastMethod=method;
    try{return await session.send(method,params,budgetMs);}
    catch(error){throw contextual(error,owner,method);}
  }
  async function navigate(method,params={}){
    if(!['Page.navigate','Page.reload'].includes(method))throw Error('Unsupported access navigation');
    const owner=phase,previous=(await send('Page.getFrameTree')).frameTree.frame;
    if(!previous.id||!previous.loaderId)throw Error(`Access browser [${owner}] missing previous main loader`);
    const result=await send(method,params);
    if(result.errorText)throw Error(`Access browser [${owner}] ${method}: ${result.errorText}`);
    const deadline=performance.now()+loadTimeoutMs;
    // Navigation acknowledgement can precede document replacement. Never poll that old DOM.
    while(!loads.reloaded(previous)){
      if(terminal)throw contextual(Error(terminal),owner,method);
      if(performance.now()>=deadline)throw Error(`Access browser [${owner}] ${method}: new main document load timed out`);
      await new Promise(resolve=>setTimeout(resolve,pollMs));
    }
  }
  return {send,navigate,setPhase(value){phase=value;},snapshot(){return {phase,last_method:lastMethod,events:[...events]};},close(){terminal='CDP session disposed';session.close();}};
}
module.exports={accessSession};
