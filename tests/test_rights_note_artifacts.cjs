// Real browser reruns preserve lossless authored fixtures and earlier QA outputs.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {qaRoot}=require('./qa_artifacts.cjs');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
const reportRoot=path.join(qaRoot(root),'rights-note');
const git=(...args)=>{const r=spawnSync('git',args,{cwd:root,encoding:'utf8'});assert.equal(r.status,0,r.stderr);return r.stdout;};
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const tracked=git('ls-files','-z','--','tests/fixtures').split('\0').filter(Boolean);
assert.ok(tracked.some(file=>file.endsWith('.png')),'Lossless authored fixtures must remain tracked');
const snapshot=()=>Object.fromEntries(tracked.map(file=>[file,hash(path.join(root,file))]));
const before=snapshot(),runs=()=>fs.existsSync(reportRoot)?fs.readdirSync(reportRoot).filter(name=>name.startsWith('run-')):[];
const captures=[];
for(let i=0;i<2;i++){
  const prior=new Set(runs());
  const child=spawnSync(process.execPath,[path.join(root,'tests/browser_rights_note.cjs')],{
    cwd:root,env:{...process.env,TULDOK_SOURCE_ROOT:root},encoding:'utf8',timeout:120_000,maxBuffer:8*1024*1024});
  process.stdout.write(child.stdout||'');process.stderr.write(child.stderr||'');
  assert.equal(child.status,0,child.error?.message||'The unchanged rights-note browser workflow must pass');
  assert.deepEqual(snapshot(),before,`Browser run ${i+1} modified tracked evidence`);
  for(const capture of captures)assert.equal(hash(path.join(root,capture.file)),capture.sha256,'A rerun overwrote an earlier screenshot');
  const added=runs().filter(name=>!prior.has(name));assert.equal(added.length,1,'Each browser run needs one fresh output directory');
  const folder=path.join(reportRoot,added[0]);
  assert.deepEqual(fs.readdirSync(folder).sort(),['rights-desktop.jpg','rights-narrow.jpg']);
  for(const name of fs.readdirSync(folder)){
    const file=path.join(folder,name),relative=path.relative(root,file),bytes=fs.readFileSync(file);
    assert.ok(bytes.length>8);assert.deepEqual(bytes.subarray(0,3),Buffer.from([255,216,255]),'Actual JPEG capture required');
    assert.ok(git('check-ignore','--',relative).trim(),'Transient output must stay outside tracked evidence');
    captures.push({file:relative,sha256:hash(file),bytes:bytes.length});
  }
}
const sourcePaths=['.gitignore','.github/workflows/tests.yml','tests/qa_artifacts.cjs','tests/browser_rights_note.cjs','tests/test_rights_note_artifacts.cjs'];
const identity=git('rev-parse','HEAD','HEAD^{tree}').trim().split('\n');
const receipt={source_head:identity[0],source_tree:identity[1],
  source_state:git('status','--porcelain','--',...sourcePaths).trim()?'workingtree':'committed',
  browser_script_sha256:hash(path.join(root,'tests/browser_rights_note.cjs')),
  regression_script_sha256:hash(__filename),browser_runs:2,tracked_evidence_files:tracked.length,
  tracked_evidence_before_sha256:crypto.createHash('sha256').update(JSON.stringify(before)).digest('hex'),
  tracked_evidence_unchanged_after_each_run:true,earlier_captures_retained:true,captures,result:'PASS'};
const receiptFolder=fs.mkdtempSync(path.join(reportRoot,'preservation-'));
fs.writeFileSync(path.join(receiptFolder,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(`Rights-note artifact preservation: ${tracked.length} authored fixture files unchanged after each of two real browser runs; four JPEG85 captures retained in distinct ignored directories. Receipt: ${path.relative(root,receiptFolder)}/receipt.json`);
