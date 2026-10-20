'use strict';
// Qualification-only protocol timing: no responses or application handlers are substituted.
const Native=globalThis.WebSocket;
globalThis.WebSocket=class extends Native{
  constructor(...args){
    super(...args);this.nextInternal=100000000;this.callbacks=new Map();this.held=null;this.armed=false;this.witnessed=false;this.firstReleased=false;this.continued=false;
    this.addEventListener('message',event=>{
      const value=JSON.parse(event.data);
      if(this.callbacks.has(value.id)){const callback=this.callbacks.get(value.id);this.callbacks.delete(value.id);callback(value);}
      if(value.method==='Fetch.requestPaused'&&value.params.request.url.endsWith('/workspace-projects.js')){this.held=value.params.requestId;console.log('STARTUP held actual workspace-projects.js response');this.releaseIfClicked();}
    });
  }
  own(method,params,callback=()=>{}){const id=++this.nextInternal;this.callbacks.set(id,callback);super.send(JSON.stringify({id,method,params}));}
  send(raw){
    const value=JSON.parse(raw);
    if(value.method==='Page.navigate'&&value.params.url.endsWith('/workspaces')&&!this.armed){this.armed=true;this.own('Fetch.enable',{patterns:[{urlPattern:'*/workspace-projects.js',requestStage:'Response'}]},()=>super.send(raw));return;}
    if(value.method==='Input.dispatchMouseEvent'&&value.params.type==='mousePressed'&&!this.witnessed){
      this.witnessed=true;this.own('Runtime.evaluate',{expression:`JSON.stringify({disabled:document.getElementById('open-project').disabled,handler:typeof document.getElementById('open-project').onclick,dialog:document.getElementById('project-open-dialog').open,hit:document.elementFromPoint(${value.params.x},${value.params.y})?.id})`,returnByValue:true},reply=>{console.log('STARTUP before original first pointer click',reply.result?.result?.value);super.send(raw);});return;
    }
    super.send(raw);
    if(this.witnessed&&value.method==='Input.dispatchMouseEvent'&&value.params.type==='mouseReleased'){this.firstReleased=true;this.releaseIfClicked();}
  }
  releaseIfClicked(){
    if(!this.held||!this.firstReleased||this.continued)return;
    this.continued=true;const requestId=this.held;this.held=null;
    setTimeout(()=>this.own('Fetch.continueRequest',{requestId},()=>{
      this.own('Fetch.disable',{});
      setTimeout(()=>this.own('Runtime.evaluate',{expression:"JSON.stringify({disabled:document.getElementById('open-project').disabled,handler:typeof document.getElementById('open-project').onclick,dialog:document.getElementById('project-open-dialog').open,status:document.getElementById('workspace-status').textContent})",returnByValue:true},reply=>console.log('STARTUP after original click and actual module release',reply.result?.result?.value)),500);
    }),500);
  }
};
