'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const {qaRoot,qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),suite='qa-output-regression';
assert.throws(()=>qaRoot(root,path.join(root,'docs/plans/example/reports')),/ignored build\/output/);
assert.throws(()=>qaRoot(root,path.join(root,'tests/fixtures')),/ignored build\/output/);
assert.throws(()=>qaRoot(root,root),/ignored build\/output/);
assert.equal(qaRoot(root,path.join(root,'output','qa')),path.join(root,'output','qa'));
assert.deepEqual(screenshotOptions,{format:'jpeg',quality:85,captureBeyondViewport:false});
const fake=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-qa-routing-'));
try{
  fs.mkdirSync(path.join(fake,'build/qa'),{recursive:true});
  fs.mkdirSync(path.join(fake,'docs/fixtures'),{recursive:true});
  fs.symlinkSync(path.join(fake,'docs/fixtures'),path.join(fake,'build/qa/aliased-suite'));
  assert.throws(()=>qaDirectory(fake,'aliased-suite',path.join(fake,'build/qa')),/ignored build\/output/);
  assert.deepEqual(fs.readdirSync(path.join(fake,'docs/fixtures')),[]);
}finally{fs.rmSync(fake,{recursive:true,force:true});}
const dir=qaDirectory(root,suite);assert.equal(qaDirectory(root,suite),dir);
fs.writeFileSync(path.join(dir,'first.txt'),'retain first run');
const child=spawnSync(process.execPath,['-e',"console.log(require('./tests/qa_artifacts.cjs').qaDirectory(process.cwd(),'qa-output-regression'))"],{cwd:root,encoding:'utf8'});
assert.equal(child.status,0,child.stderr);const next=child.stdout.trim();assert.notEqual(next,dir);
assert.equal(fs.readFileSync(path.join(dir,'first.txt'),'utf8'),'retain first run');
const ignored=spawnSync('git',['check-ignore','--',dir,next],{cwd:root,encoding:'utf8'});assert.equal(ignored.status,0,ignored.stderr);
console.log('QA output routing: rejected tracked trees, ignored roots, distinct process runs, earlier outputs retained, JPEG85.');
