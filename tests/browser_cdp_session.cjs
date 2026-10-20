'use strict';
// Test-owned protocol requests and modal expectations share one socket lifetime.
function cdpSession(socket,{timeoutMs=15000,onEvent=()=>{}}={}){
  let sequence=0,closed=false,dialog=null,expectation=null;
  const pending=new Map();
  function fail(error){
    closed=true;
    for(const task of pending.values()){clearTimeout(task.timer);task.reject(error);}
    pending.clear();expectation?.reject(error);
  }
  function send(method,params={},budgetMs=timeoutMs){
    return new Promise((resolve,reject)=>{
      if(closed){reject(Error('CDP socket is closed'));return;}
      const id=++sequence;
      const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},budgetMs);
      pending.set(id,{resolve,reject,timer});
      try{socket.send(JSON.stringify({id,method,params}));}
      catch(error){clearTimeout(timer);pending.delete(id);reject(error);}
    });
  }
  socket.addEventListener('message',event=>{
    const message=JSON.parse(event.data);
    if(message.id){
      const task=pending.get(message.id);
      if(!task)return; // Replies may arrive after the owning request timed out.
      pending.delete(message.id);clearTimeout(task.timer);
      message.error?task.reject(Object.assign(Error(message.error.message),{code:message.error.code})):task.resolve(message.result);
      return;
    }
    if(message.method==='Page.javascriptDialogOpening'){
      dialog=message.params;expectation?.resolve(dialog);
    }
    if(message.method==='Page.javascriptDialogClosed')dialog=null;
    onEvent(message);
  });
  socket.addEventListener('close',()=>fail(Error('CDP socket closed')));
  socket.addEventListener('error',()=>fail(Error('CDP socket failed')));
  async function withDialog(action,{accept,type='confirm',message:expectedMessage,waitMs=timeoutMs}={}){
    if(expectation||dialog)throw Error('A CDP dialog is already owned');
    let timer,triggered,own;
    const opened=new Promise((resolve,reject)=>{
      own={resolve,reject};expectation=own;
      timer=setTimeout(()=>reject(Error('CDP dialog opening timed out')),waitMs);
    });
    try{
      // Arm the event before triggering. The action itself may wait for dismissal.
      triggered=Promise.resolve().then(action);
      triggered.catch(error=>own.reject(error));
      const event=await opened;
      if(event.type!==type||event.message!==expectedMessage)throw Error('Unexpected CDP dialog: '+JSON.stringify(event));
      await send('Page.handleJavaScriptDialog',{accept});
      await triggered;
      return event;
    }finally{clearTimeout(timer);if(expectation===own)expectation=null;}
  }
  return {send,withDialog,hasDialog:()=>dialog!==null,close(){fail(Error('CDP session disposed'));socket.close();}};
}
module.exports={cdpSession};
