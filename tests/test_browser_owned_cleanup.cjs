'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process');
const {stopOwnedChildren}=require('./browser_owned_cleanup.cjs');
(async()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-owned-browser-stop-'));
  const child=spawn(process.execPath,['-e',`const fs=require('fs');process.on('SIGTERM',()=>setTimeout(()=>{fs.writeFileSync(process.argv[1],'final owned write');process.exit(0);},300));console.log('ready');setInterval(()=>{},1000);`,path.join(directory,'last-write')],{stdio:['ignore','pipe','pipe']});
  try{
    await new Promise((resolve,reject)=>{child.stdout.once('data',resolve);child.once('error',reject);});
    await stopOwnedChildren([child]);assert.equal(child.exitCode,0);assert.equal(fs.readFileSync(path.join(directory,'last-write'),'utf8'),'final owned write');
    fs.rmSync(directory,{recursive:true,force:true});assert.equal(fs.existsSync(directory),false);
    const stubborn=spawn(process.execPath,['-e',`process.on('SIGTERM',()=>{});console.log('ready');setInterval(()=>{},1000);`],{stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{stubborn.stdout.once('data',resolve);stubborn.once('error',reject);});
    await stopOwnedChildren([stubborn],{graceMs:50,killMs:2000});assert.equal(stubborn.signalCode,'SIGKILL');
    await stopOwnedChildren([child,stubborn]);
    console.log('PASS owned delayed final write completes before removal; ignored TERM is bounded and already-exited handles are harmless');
  }finally{if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');fs.rmSync(directory,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
