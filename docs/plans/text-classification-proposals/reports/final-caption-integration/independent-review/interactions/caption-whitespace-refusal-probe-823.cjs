'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),cp=require('node:child_process');
const {harness,storage,row,flush}=require('./caption-storage-harness.cjs');
const key='tuldok.caption-proposal-recovery.v1';
(async()=>{
 const persistence=storage(),first=harness(persistence);first.context.image={...row,kind:'image',task:'image_caption'};first.run('current=image');
 for(const [field,value] of Object.entries({url:'http://127.0.0.1:9999',model:'caption-fixture',guidance:'   ',seed:'42'}))first.element('caption-proposal-'+field).value=value;
 const submitting=first.element('caption-proposal-form').dispatch('submit');await flush();const posted=first.take('caption-proposals','POST'),body=structuredClone(posted.body);
 const backend=cp.spawnSync('/workspace/Tuldok/.venv/bin/python',['caption-refusal-http.py'],{input:JSON.stringify(body),encoding:'utf8',timeout:10000});assert.equal(backend.status,0,backend.stderr);
 const result=JSON.parse(backend.stdout);fs.writeFileSync('caption-whitespace-823-real-refusal.json',JSON.stringify(result,null,2));fs.writeFileSync('caption-whitespace-823-captured-body.json',JSON.stringify(body,null,2));
 posted.reject(Error('Lost actual backend400 acknowledgement'));await submitting;const raw=persistence.values.get(key);assert.equal(first.run('captionProposalPendingRequest.request_id'),body.request_id);
 const next=harness(persistence);next.context.image={...row,kind:'image',task:'image_caption'};next.run('current=image');assert.equal(next.element('caption-proposal-guidance').value,'   ');
 const polling=next.run('refreshCaptionProposals()');next.take('caption-proposals','GET').resolve({jobs:[]});await flush();const absent=Error(result.exact.body.error);absent.status=404;next.take('caption-proposals/'+body.request_id,'GET').reject(absent);await polling;
 next.element('caption-proposal-guidance').value='Correct visible-pixel guidance';await next.element('caption-proposal-form').dispatch('submit');assert.equal(next.requests.filter(r=>r.body).length,0);
 next.element('caption-proposal-guidance').value='   ';const retrying=next.element('caption-proposal-form').dispatch('submit');await flush();const retry=next.take('caption-proposals','POST');assert.deepEqual(structuredClone(retry.body),body);const refusal=Error(result.repeat.body.error);refusal.status=400;retry.reject(refusal);await retrying;
 assert.equal(persistence.values.get(key),raw);next.element('caption-proposal-guidance').value='Correct visible-pixel guidance';await next.element('caption-proposal-form').dispatch('submit');assert.equal(next.requests.filter(r=>r.body).length,0);
 console.log(JSON.stringify({finding:'confirmed',guidance_codepoints:3,frontend_persisted:true,backend:result,reload_restores_invalid_guidance:true,corrected_guidance_posts:0,exact_retry_retains_body:true,status:next.element('caption-proposal-status').textContent},null,2));
})().catch(error=>{console.error(error.stack);process.exitCode=1});
