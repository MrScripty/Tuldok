'use strict';
// Only the supplied test-owned ChildProcess handles may be stopped.
async function stopOwnedChildren(children,{graceMs=5000,killMs=2000}={}){
  await Promise.all(children.map(child=>new Promise((resolve,reject)=>{
    if(child.exitCode!==null||child.signalCode!==null){resolve();return;}
    let escalation,deadline;
    function finished(){clearTimeout(escalation);clearTimeout(deadline);child.removeListener('exit',finished);resolve();}
    child.once('exit',finished);
    escalation=setTimeout(()=>{if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');},graceMs);
    deadline=setTimeout(()=>{child.removeListener('exit',finished);reject(Error('Owned browser fixture child did not exit; retaining temporary directory.'));},graceMs+killMs);
    child.kill('SIGTERM');
  })));
}
module.exports={stopOwnedChildren};
