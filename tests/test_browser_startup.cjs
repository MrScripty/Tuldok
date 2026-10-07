// Controlled child launchers prove startup policy, not a healthy Chrome/CDP page.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {STARTUP_BUDGET_MS,waitForDebugger}=require('./browser_startup.cjs');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-startup-policy-')),children=[];
function launch(code,...args){const child=spawn(process.execPath,['-e',code,...args],{stdio:'ignore'});children.push(child);return child;}
function detached(child){
  assert.equal(child.listenerCount('error'),0,'Startup error listener must be removed');
  assert.equal(child.listenerCount('exit'),0,'Startup exit listener must be removed');
}
(async()=>{
  assert.equal(STARTUP_BUDGET_MS,60_000);
  const active=path.join(temporary,'DevToolsActivePort');
  // A ready child can write while the parent's event loop is held past its budget.
  const held=spawn(process.execPath,['-e',"const fs=require('node:fs');process.on('message',()=>{setTimeout(()=>fs.writeFileSync(process.argv[1],'43210\\n/held-loop'),80);process.send('armed')});process.send('ready')",active],{stdio:['ignore','ignore','ignore','ipc']});
  children.push(held);
  await new Promise(resolve=>held.once('message',resolve));
  const armed=new Promise(resolve=>held.once('message',resolve));held.send('arm');await armed;
  const heldStart=performance.now();
  const heldWait=waitForDebugger(held,active,{budgetMs:50,pollMs:10});
  while(performance.now()-heldStart<200){} // Deliberately prevent either timer from running.
  assert.ok(fs.existsSync(active),'Independent child must have supplied readiness during the hold');
  await assert.rejects(heldWait,/exceeded 50 ms startup budget/);
  detached(held);held.kill();fs.unlinkSync(active);
  const delayed=launch("const fs=require('node:fs');setTimeout(()=>fs.writeFileSync(process.argv[1],'43210\\n/fixture'),20_510);setInterval(()=>{},1000)",active);
  const start=performance.now();
  assert.equal(await waitForDebugger(delayed,active),'43210');
  const elapsed=performance.now()-start;
  assert.ok(elapsed>15_000&&elapsed<STARTUP_BUDGET_MS,'Late readiness must fit only the infrastructure budget');
  detached(delayed);delayed.kill();fs.unlinkSync(active);
  // A live child that never supplies readiness exhausts its bounded allowance.
  const exhausted=launch('setInterval(()=>{},1000)');
  await assert.rejects(waitForDebugger(exhausted,active,{budgetMs:250,pollMs:10}),/exceeded 250 ms startup budget/);
  detached(exhausted);assert.equal(exhausted.exitCode,null);exhausted.kill();
  // Exit/spawn events fail promptly even when the full budget is available.
  const dead=launch('process.exit(23)');
  let death;
  dead.once('exit',()=>death=performance.now());
  await assert.rejects(waitForDebugger(dead,active),/exited before debugger readiness/);
  assert.equal(dead.exitCode,23);assert.ok(performance.now()-death<1_000,'Reject promptly after the observed exit');detached(dead);
  const missing=spawn(path.join(temporary,'missing-browser'),[],{stdio:'ignore'});children.push(missing);
  let spawnFailure;
  missing.once('error',()=>spawnFailure=performance.now());
  await assert.rejects(waitForDebugger(missing,active),/spawn failed before debugger readiness/);
  assert.ok(performance.now()-spawnFailure<1_000,'Reject promptly after the observed spawn error');
  detached(missing);
  // Already-dead children must not be accepted through a stale readiness file.
  fs.writeFileSync(active,'43210\n/stale');
  await assert.rejects(waitForDebugger(dead,active),/exited before debugger readiness/);detached(dead);
  console.log(`Browser startup policy: ${Math.round(elapsed)} ms late readiness within 60s, held-event-loop deadline, budget exhaustion, dead process, spawn failure and listener cleanup passed. Real browser health requires the actual suites.`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  for(const child of children)child.kill();fs.rmSync(temporary,{recursive:true,force:true});
});
