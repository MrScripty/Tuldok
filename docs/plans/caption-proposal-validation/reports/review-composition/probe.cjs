'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const dir=__dirname,root='/workspace/Tuldok-caption-validation-local';
const source=fs.readFileSync(root+'/static/caption-proposals.js','utf8');
const context=vm.createContext({URL});vm.runInContext(source.slice(0,source.indexOf('function captionProposalStoredRequest')),context);
const cases=JSON.parse(fs.readFileSync(dir+'/cases.json','utf8')),mismatches=[];let acceptedFront=0,acceptedBoth=0,preserved=0;
for(const item of cases){context.probe=item.body;let frontend=true,error='';try{const out=vm.runInContext('captionProposalRecoveryBody(probe)',context);assert.deepEqual(JSON.parse(JSON.stringify(out)),item.body);preserved++;}catch(exc){if(exc instanceof assert.AssertionError)throw exc;frontend=false;error=exc.message;}
 if(frontend)acceptedFront++;if(frontend&&item.backend_accepted)acceptedBoth++;
 if(frontend!==item.backend_accepted)mismatches.push({...item,frontend_accepted:frontend,frontend_error:error});
}
const bad=mismatches.filter(c=>c.frontend_accepted),conservative=mismatches.filter(c=>!c.frontend_accepted);
const result={source_commit:'e89cf7636e3b6790179a0de3f4aeb9c433217bed',source_tree:'ea56fd0702b8b65a8ca2c60288fffce88c512a5d',cases:cases.length,accepted_front:acceptedFront,accepted_both:acceptedBoth,preserved_exact_intent:preserved,accepted_front_rejected_back:bad.length,conservative_front_rejections:conservative.length};
fs.writeFileSync(dir+'/result.json',JSON.stringify(result,null,2));fs.writeFileSync(dir+'/mismatches.json',JSON.stringify(mismatches,null,2));console.log(JSON.stringify(result,null,2));if(bad.length)console.log(JSON.stringify(bad.slice(0,15),null,2));
