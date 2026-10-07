// Test-only debugger startup budget; product/UI waits remain with each suite.
'use strict';
const fs=require('node:fs');
const STARTUP_BUDGET_MS=60_000;
function waitForDebugger(child,active,{budgetMs=STARTUP_BUDGET_MS,pollMs=100}={}){
  if(!Number.isInteger(budgetMs)||budgetMs<1||budgetMs>STARTUP_BUDGET_MS)throw Error('Invalid browser startup budget');
  return new Promise((resolve,reject)=>{
    let poll,deadline,settled=false;
    function finish(error,port){
      if(settled)return;settled=true;
      clearTimeout(poll);clearTimeout(deadline);
      child.removeListener('error',failed);child.removeListener('exit',exited);
      error?reject(error):resolve(port);
    }
    function failed(error){finish(Error('Browser spawn failed before debugger readiness: '+error.message));}
    function exited(){finish(Error('Browser exited before debugger readiness'));}
    function check(){
      if(child.exitCode!==null||child.signalCode!==null){exited();return;}
      try{
        const port=fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0];
        if(port){finish(null,port);return;}
      }catch(error){finish(error);return;}
      poll=setTimeout(check,pollMs);
    }
    child.once('error',failed);child.once('exit',exited);
    deadline=setTimeout(()=>finish(Error(`Browser debugger readiness exceeded ${budgetMs} ms startup budget`)),budgetMs);
    check();
  });
}
module.exports={STARTUP_BUDGET_MS,waitForDebugger};
