'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),cp=require('node:child_process');
const dir=__dirname,root='/workspace/Tuldok-caption-validation-local';
const source=fs.readFileSync(root+'/static/caption-proposals.js','utf8'),context=vm.createContext({URL});
vm.runInContext(source.slice(0,source.indexOf('function captionProposalStoredRequest')),context);
const base={source_id:'a'.repeat(32),revision:2,source_revision:1,server_url:'http://127.0.0.1:8765',model:'fixture',instruction:'Original exact guidance',seed:42,request_id:'0'.repeat(31)+'1'};
const cases=[];
for(const [label,character,where] of [['slashes','/','suffix'],['ascii-space',' ','prefix'],['ascii-space',' ','suffix'],['tab','\t','prefix'],['tab','\t','suffix'],['python-NEL','\u0085','prefix'],['python-NEL','\u0085','suffix'],['ideographic-space','\u3000','prefix'],['ideographic-space','\u3000','suffix']]) {
 const construct=count=>({...base,server_url:where==='prefix'?character.repeat(count)+base.server_url:base.server_url+character.repeat(count)});
 const factor=JSON.stringify(character).length-2,available=32768-JSON.stringify(base).length,count=Math.floor(available/factor);
 for(const delta of [-1,0,1,2]) {
  const body=construct(count+delta);if(delta===0 && JSON.stringify(body).length<32768)body.server_url=' '+body.server_url;
  cases.push({label:label+'-'+where+'-'+delta,body,length:JSON.stringify(body).length});
 }
}
const oracle=cp.spawnSync('python',['-c',`import sys,json,ai_http\nfrom workbench import text_value\nout=[]\nfor b in json.load(sys.stdin):\n try:\n  text_value(ai_http.validate_url('llamacpp',b['server_url']),'Server URL',2048);out.append(True)\n except ValueError:out.append(False)\nprint(json.dumps(out))`],{cwd:root,input:JSON.stringify(cases.map(c=>c.body)),encoding:'utf8'});
assert.equal(oracle.status,0,oracle.stderr);const backend=JSON.parse(oracle.stdout);let mismatches=[];
for(const [i,item]of cases.entries()){
 assert.equal(backend[i],true,'Envelope cases all backend-admissible');context.probe=item.body;let accepted=true,error='';
 try{const result=vm.runInContext('captionProposalRecoveryBody(probe)',context);assert.deepEqual(JSON.parse(JSON.stringify(result)),item.body);}catch(exc){if(exc instanceof assert.AssertionError)throw exc;accepted=false;error=exc.message;}
 item.backend_accepted=true;item.frontend_accepted=accepted;item.frontend_error=error;
 if(accepted!==(item.length<=32768))mismatches.push(item);
}
const result={source_commit:cp.execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),source_tree:cp.execFileSync('git',['rev-parse','HEAD^{tree}'],{cwd:root,encoding:'utf8'}).trim(),cases:cases.length,mismatches:mismatches.length,accepted_exact_cap:cases.filter(c=>c.length===32768&&c.frontend_accepted).length,rejected_over_cap:cases.filter(c=>c.length>32768&&!c.frontend_accepted).length};
fs.writeFileSync(dir+'/envelope-result.json',JSON.stringify(result,null,2)+'\n');fs.writeFileSync(dir+'/envelope-cases.json',JSON.stringify(cases,null,2)+'\n');console.log(JSON.stringify(result,null,2));assert.equal(mismatches.length,0,'Fresh persistence envelope must preflight before storage');
