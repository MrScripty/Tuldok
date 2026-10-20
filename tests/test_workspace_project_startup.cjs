'use strict';
// Controller construction only; browser_scientific_fields owns real startup/pointer evidence.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function verifyProjectStartup(){
  const html=fs.readFileSync(path.join(__dirname,'../static/workspaces.html'),'utf8');
  assert.match(html.match(/<button\b[^>]*id="open-project"[^>]*>/)[0],/\bdisabled\b/,'The initial server markup must withhold the unbound action');
  const nodes=new Map(),listeners=[],requests=[];
  function node(id){
    if(!nodes.has(id))nodes.set(id,{disabled:id==='open-project',open:false,addEventListener(){},showModal(){this.open=true;},close(){this.open=false;},focus(){}});
    return nodes.get(id);
  }
  const button=node('open-project');let disabled=true,enables=0;
  Object.defineProperty(button,'disabled',{get:()=>disabled,set:value=>{
    if(!value){
      assert.equal(typeof button.onclick,'function','The controller installs the action before exposing it');
      assert.equal(typeof node('project-open-form').onsubmit,'function','The complete open form is owned before exposure');
      assert.ok(listeners.includes('pagehide'),'Controller disposal is owned before exposure');
      enables++;
    }
    disabled=value;
  }});
  const window={workspaceEscape:String,addEventListener:event=>listeners.push(event)};
  const context={window,document:{getElementById:node},WorkspaceProjectActivity:()=>({stop(){}}),WorkspaceExternalProject:()=>({cancel(){}}),WorkspaceExtensionModelAuthor:()=>({cancel(){}}),fetch:url=>{requests.push(url);return new Promise(()=>{});}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/workspace-projects.js'),'utf8'),context);
  assert.equal(button.disabled,true,'Loading the module alone does not expose an unconstructed controller');
  window.WorkspaceProjects({select:{value:'fixtures'},roots:{},announce(){},switchSource(){},contextChanged(){}});
  assert.equal(button.disabled,false);assert.equal(enables,1);
  button.onclick();assert.equal(node('project-open-dialog').open,true,'The enabled first action opens its dialog synchronously');
  assert.deepEqual(requests,['/api/workspace/project-snapshots']);
  console.log('PASS project startup markup disabled; owning constructor binds action, form and teardown before enable; first action opens synchronously and reads only');
}
module.exports={verifyProjectStartup};
if(require.main===module)verifyProjectStartup();
