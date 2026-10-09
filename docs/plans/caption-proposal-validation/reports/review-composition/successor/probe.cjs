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
const result={source_commit:'9483d4a2f5c1391b3f882e107cee6846aeb36a39',source_tree:'0fe33807c03e582c3a5ce9f4403be37e570e8f59',cases:cases.length,accepted_front:acceptedFront,accepted_both:acceptedBoth,preserved_exact_intent:preserved,accepted_front_rejected_back:bad.length,conservative_front_rejections:conservative.length};
fs.writeFileSync(dir+'/result.json',JSON.stringify(result,null,2));fs.writeFileSync(dir+'/mismatches.json',JSON.stringify(mismatches,null,2));console.log(JSON.stringify(result,null,2));if(bad.length)console.log(JSON.stringify(bad.slice(0,15),null,2));
