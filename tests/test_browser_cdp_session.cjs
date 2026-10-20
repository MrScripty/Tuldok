'use strict';
// Controlled protocol timing proves synchronization/deadlines, not product UI.
const assert=require('node:assert/strict');
const {cdpSession}=require('./browser_cdp_session.cjs');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const message='Discard unsaved annotation, rights-note, response or judgment edits?';
class Socket extends EventTarget{
  constructor(){super();this.dialog=false;this.decisions=[];this.held=[];this.timers=[];}
  receive(value){this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify(value)}));}
  send(raw){
    const {id,method,params}=JSON.parse(raw);this.lastId=id;
    if(method==='Runtime.evaluate'&&params.expression==='open'){
      this.held.push(id);
      this.timers.push(setTimeout(()=>{this.dialog=true;this.receive({method:'Page.javascriptDialogOpening',params:{type:'confirm',message}});},180));return;
    }
    if(method==='Runtime.never'||method==='Runtime.evaluate'&&this.dialog){this.held.push(id);return;}
    if(method==='Page.handleJavaScriptDialog'){
      if(!this.dialog){this.receive({id,error:{code:-32602,message:'No dialog is showing'}});return;}
      this.decisions.push(params.accept);this.dialog=false;this.receive({method:'Page.javascriptDialogClosed',params:{result:params.accept}});
      for(const held of this.held.splice(0))this.receive({id:held,result:{result:{value:true}}});
    }
    this.receive({id,result:{result:{value:true}}});
  }
  close(){this.timers.forEach(clearTimeout);this.dispatchEvent(new Event('close'));}
}
async function verifyCDPSession(){
  const oldSocket=new Socket(),old=cdpSession(oldSocket,{timeoutMs:500});
  try{
    const click=old.send('Runtime.evaluate',{expression:'open'});click.catch(()=>{});
    await pause(100);
    await assert.rejects(old.send('Page.handleJavaScriptDialog',{accept:false}),error=>error.code===-32602&&error.message==='No dialog is showing');
    await pause(100);assert.equal(old.hasDialog(),true,'The real protocol opening arrives after the obsolete fixed wait');
    const started=performance.now();
    await assert.rejects(old.send('Runtime.evaluate',{expression:'diagnostics'},25),/CDP timeout: Runtime.evaluate/);
    assert.ok(performance.now()-started<250,'Late-modal diagnostics must terminate within their own budget');
    console.log('PASS reproduced fixed100ms race: delayed180ms confirm rejects premature handling; blocked diagnostics time out');
  }finally{old.close();}
  const socket=new Socket(),session=cdpSession(socket,{timeoutMs:500});
  try{
    for(const accept of [false,true,true]){
      const event=await session.withDialog(()=>session.send('Runtime.evaluate',{expression:'open'}),{accept,message});
      assert.equal(event.type,'confirm');assert.equal(session.hasDialog(),false);
    }
    assert.deepEqual(socket.decisions,[false,true,true],'Each newly observed dialog is handled exactly once with its selected decision');
    await assert.rejects(session.withDialog(()=>Promise.resolve(),{accept:true,message,waitMs:20}),/dialog opening timed out/);
    await assert.rejects(session.withDialog(()=>Promise.reject(Error('Trigger failed')),{accept:true,message}),/Trigger failed/);
    await assert.rejects(session.send('Runtime.never',{},20),/CDP timeout/);
    assert.doesNotThrow(()=>socket.receive({id:socket.lastId,result:{}}),'Late timed-out replies are harmless');
    await session.send('Browser.getVersion');
    const pending=session.send('Runtime.never');const rejected=assert.rejects(pending,/socket closed/);socket.close();await rejected;
    console.log('PASS fresh delayed cancel/accept/discard, absent dialog, trigger failure, bounded request, late reply and socket-close drainage');
  }finally{session.close();}
  for(const kind of ['wrong','error']){
    const socket=new Socket(),session=cdpSession(socket,{timeoutMs:500});
    try{
      if(kind==='wrong'){
        await assert.rejects(session.withDialog(()=>session.send('Runtime.evaluate',{expression:'open'}),{accept:true,message:'Wrong prompt'}),/Unexpected CDP dialog/);
        assert.deepEqual(socket.decisions,[],'An unexpected prompt is never autoaccepted');
      }else{
        const pending=session.send('Runtime.never'),rejected=assert.rejects(pending,/socket failed/);socket.dispatchEvent(new Event('error'));await rejected;
      }
    }finally{session.close();}
  }
  console.log('PASS unexpected dialog fails closed and socket error drains owned requests');
}
module.exports={verifyCDPSession};
if(require.main===module)verifyCDPSession().catch(error=>{console.error(error);process.exitCode=1;});
