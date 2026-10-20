'use strict';
// Controlled CDP scheduling reproduces the departing-document window; not a hosted trace.
const assert=require('node:assert/strict');
const {cdpSession}=require('./browser_cdp_session.cjs');
const {accessSession}=require('./browser_access_session.cjs');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
class Socket extends EventTarget{
  constructor(){super();this.reads=0;this.loaded=false;this.requested=new Promise(resolve=>{this.acknowledged=resolve;});}
  receive(value){this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify(value)}));}
  send(raw){
    const {id,method}=JSON.parse(raw);
    if(method==='Page.getFrameTree'){this.receive({id,result:{frameTree:{frame:{id:'main',loaderId:'old'}}}});return;}
    if(method==='Page.navigate'||method==='Page.reload'){this.receive({id,result:{}});this.acknowledged();return;}
    if(method==='Runtime.never')return;
    if(method==='Runtime.evaluate'){
      this.reads++;
      if(!this.loaded){this.receive({id,error:{code:-32000,message:'Inspected target navigated or closed'}});return;}
    }
    this.receive({id,result:{result:{value:true}}});
  }
  frame(id,loaderId,parentId){this.receive({method:'Page.frameNavigated',params:{frame:{id,loaderId,parentId}}});}
  load(frameId,loaderId,name='load'){this.receive({method:'Page.lifecycleEvent',params:{frameId,loaderId,name}});}
  close(){this.dispatchEvent(new Event('close'));}
}
async function verifyAccessNavigation(){
  for(const method of ['Page.navigate','Page.reload']){
    const oldSocket=new Socket(),old=cdpSession(oldSocket);
    try{
      await old.send(method);
      await assert.rejects(old.send('Runtime.evaluate',{expression:'original access assertion'}),error=>error.code===-32000&&error.message==='Inspected target navigated or closed');
    }finally{old.close();}
    const socket=new Socket(),current=accessSession(socket,{pollMs:1,loadTimeoutMs:1000});
    current.setPhase(method==='Page.reload'?'scoped-agent-reload':'initial-navigation');
    try{
      let finished=false;
      const action=(async()=>{await current.navigate(method);await current.send('Runtime.evaluate',{expression:'original access assertion'});finished=true;})();
      await socket.requested;await tick();assert.equal(socket.reads,0);assert.equal(finished,false);
      socket.frame('child','child-new','main');socket.load('child','child-new');
      socket.frame('main','new');socket.load('main','old');socket.load('main','new','DOMContentLoaded');
      await tick();assert.equal(socket.reads,0);assert.equal(finished,false,'Old/subframe/DOMContentLoaded events never permit access DOM reads');
      socket.loaded=true;socket.load('main','new');await action;assert.equal(socket.reads,1);assert.equal(finished,true);
    }finally{current.close();}
  }
  console.log('PASS access navigation/reload reproduction: old acknowledgement permits failing DOM read; changed main loader plus its load gates the original assertion');
  for(const kind of ['timeout','close']){
    const socket=new Socket(),current=accessSession(socket,{pollMs:1,loadTimeoutMs:25});current.setPhase('scoped-agent-reload');
    try{
      const navigation=current.navigate('Page.reload');
      const rejected=assert.rejects(navigation,kind==='close'?/\[scoped-agent-reload\] Page.reload: CDP socket closed/:/\[scoped-agent-reload\] Page.reload: new main document load timed out/);
      await socket.requested;if(kind==='close')socket.close();await rejected;assert.equal(socket.reads,0);
    }finally{current.close();}
  }
  const socket=new Socket(),current=accessSession(socket,{timeoutMs:20});current.setPhase('private-operation');
  try{
    await assert.rejects(current.send('Runtime.never',{token:'MUST_NOT_APPEAR'}),error=>error.message==='Access browser [private-operation] Runtime.never: CDP timeout: Runtime.never'&&!error.message.includes('MUST_NOT_APPEAR'));
    assert.ok(!JSON.stringify(current.snapshot()).includes('MUST_NOT_APPEAR'));
  }finally{current.close();}
  console.log('PASS access phase-specific timeout/target-close failures are bounded; diagnostics omit command parameters');
}
module.exports={verifyAccessNavigation};
if(require.main===module)verifyAccessNavigation().catch(error=>{console.error(error);process.exitCode=1;});
