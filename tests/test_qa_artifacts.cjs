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
const callers=[
  ['browser_saved_searches.cjs','saved-searches'],
  ['browser_sequences.cjs','simulation-sequence'],
  ['browser_sequences_actual.cjs','simulation-sequence-actual','TULDOK_SEQUENCE_ACTUAL_REPORT_ROOT'],
  ['browser_meshes.cjs','static-mesh'],
  ['browser_pumas_gateways.cjs','pumas-gateways'],
  ['browser_caption_proposals.cjs','caption-proposals'],
  ['browser_text_classification_proposals.cjs','text-classification-proposals','TULDOK_CLASSIFICATION_REPORT_ROOT'],
  ['browser_classification_preferences_integration.cjs','classification-preferences','TULDOK_CLASSIFICATION_PREFERENCES_REPORT_ROOT'],
  ['browser_rights_note.cjs','rights-note'],
  ['test_rights_note_artifacts.cjs','rights-note'],
  ['test_rights_note_artifacts.cjs','rights-note-preservation'],
];
let callerProbes=0;
for(const [script,outputSuite,legacyOverride] of callers){
 for(const override of [null,'TULDOK_QA_OUTPUT_ROOT',...(legacyOverride?[legacyOverride]:[])]){
  const source=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-qa-caller-'));
  try{
    const inputs=path.join(source,'tests/fixtures'),output=path.join(source,override?'output/qa':'build/qa');
    fs.mkdirSync(inputs,{recursive:true});fs.mkdirSync(output,{recursive:true});
    fs.writeFileSync(path.join(inputs,'authored.txt'),'unchanged authored bytes');
    fs.symlinkSync(inputs,path.join(output,outputSuite));
    const sentinel=path.join(source,'unexpected-child.txt'),preload=path.join(source,'no-children.cjs');
    fs.writeFileSync(preload,"const cp=require('node:child_process'),fs=require('node:fs');for(const name of ['spawn','spawnSync','execFileSync'])cp[name]=()=>{fs.writeFileSync(process.env.QA_SPAWN_SENTINEL,'unexpected child');throw Error('Unexpected child launched before output validation');};");
    const env={...process.env,TULDOK_SOURCE_ROOT:source,QA_SPAWN_SENTINEL:sentinel};
    for(const name of ['TULDOK_QA_OUTPUT_ROOT','TULDOK_CLASSIFICATION_REPORT_ROOT','TULDOK_CLASSIFICATION_PREFERENCES_REPORT_ROOT','TULDOK_CAPTION_REPORT_ROOT','TULDOK_SEQUENCE_ACTUAL_REPORT_ROOT'])delete env[name];
    if(override)env[override]=output;
    const result=spawnSync(process.execPath,['--require',preload,path.join(root,'tests',script)],{cwd:root,env,encoding:'utf8',timeout:5000});
    assert.equal(result.status,1,`${script}/${outputSuite}: ${result.error||result.stderr}`);
    assert.match(result.stderr,/QA output must be outside the source tree or inside ignored build\/output folders/,`${script}/${outputSuite}: caller must reject the suite alias`);
    assert.equal(fs.existsSync(sentinel),false,`${script}: output validation must precede child launches`);
    assert.deepEqual(fs.readdirSync(inputs),['authored.txt'],`${script}: no run directory in authored fixtures`);
    assert.equal(fs.readFileSync(path.join(inputs,'authored.txt'),'utf8'),'unchanged authored bytes');
    callerProbes++;
  }finally{fs.rmSync(source,{recursive:true,force:true});}
 }
}
const dir=qaDirectory(root,suite);assert.equal(qaDirectory(root,suite),dir);
fs.writeFileSync(path.join(dir,'first.txt'),'retain first run');
const child=spawnSync(process.execPath,['-e',"console.log(require('./tests/qa_artifacts.cjs').qaDirectory(process.cwd(),'qa-output-regression'))"],{cwd:root,encoding:'utf8'});
assert.equal(child.status,0,child.stderr);const next=child.stdout.trim();assert.notEqual(next,dir);
assert.equal(fs.readFileSync(path.join(dir,'first.txt'),'utf8'),'retain first run');
const ignored=spawnSync('git',['check-ignore','--',dir,next],{cwd:root,encoding:'utf8'});assert.equal(ignored.status,0,ignored.stderr);
console.log(`QA output routing: rejected tracked trees and ${callerProbes} actual-caller suite aliases with default/override roots before child launches; ignored roots, distinct process runs, earlier outputs retained, JPEG85.`);
