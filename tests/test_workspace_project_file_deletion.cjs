'use strict';
// Controlled response checks; actual filesystem/HTTP proof is a separate gate.
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const {mount,bound,response,tick,P,ACTOR,C,NEXT}=require('./test_workspace_project_files_m4.cjs');
const path='notes/scientist.md',text='Ω authored note\0before\r\n',sha=crypto.createHash('sha256').update(text).digest('hex');
const id=crypto.createHash('sha256').update(P+'\0note\0'+path).digest('hex'),stamp='2026-10-22T12:00:00+00:00';
const positive={revision:1,sha256:sha,bytes:Buffer.byteLength(text),text,adopted_at:stamp,actor_id:ACTOR};
const deleted={revision:2,deleted:true,sha256:null,bytes:0,text:null,adopted_at:stamp,actor_id:ACTOR};
const selection=version=>({id,project_id:P,kind:'note',path,version});
const missing={id,kind:'note',path,revision:1,expected_sha256:sha,expected_bytes:positive.bytes,observed_sha256:null,observed_bytes:null,state:'missing',reason:'missing'};
const tombstone={...missing,revision:2,expected_sha256:null,expected_bytes:0,state:'deleted',reason:null};
const page=item=>({items:[item],offset:0,limit:40,total:1});
async function chooseMissing(h){h.answers.push(response(bound(page(missing))));await h.click('project-working-load');h.answers.push(response(bound(selection(positive))));await h.row('project-working-list');}
(async()=>{
  {
    const h=mount();await tick();await chooseMissing(h);
    assert.equal(h.nodes.get('project-working-delete-fields').disabled,false);
    assert.equal(h.nodes.get('project-working-text').value,text);
    assert.match(h.nodes.get('project-working-delete-summary').textContent,new RegExp(sha));
    assert.ok(!h.requests.some(r=>r.url.endsWith('/adopt-deletion')),'Inspection must never adopt deletion');
    const before=h.requests.length;await h.submit('project-working-delete-form');assert.equal(h.requests.length,before);assert.match(h.nodes.get('project-files-error').textContent,/explicitly confirm/);
    h.nodes.get('project-working-delete-confirm').checked=true;
    h.nodes.get('project-working-delete-confirm').listeners.get('change')();
    h.answers.push(({url,options})=>{assert.equal(url,'/api/workspace/project-files/files/adopt-deletion');const body=JSON.parse(options.body);assert.equal(body.binding,'b'.repeat(32));assert.equal(body.expected_checkpoint,C);assert.equal(body.path,path);assert.equal(body.expected_revision,1);assert.equal(body.expected_sha256,sha);assert.deepEqual(Object.keys(body).sort(),['binding','expected_checkpoint','expected_revision','expected_sha256','path','request_key']);return response(bound({id,project_id:P,kind:'note',path,revision:2,sha256:null,bytes:0,deleted:true,adopted_at:stamp,changed:true},NEXT));},response(bound(page(tombstone),NEXT)),response(bound(selection(deleted),NEXT)));
    await h.submit('project-working-delete-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-working-text').value,'');assert.match(h.nodes.get('project-working-summary').textContent,/note deletion retained/);assert.equal(h.nodes.get('project-working-delete-fields').disabled,true);
    const metadata=v=>Object.fromEntries(Object.entries(v).filter(([k])=>k!=='text'));
    h.answers.push(response(bound({id,items:[metadata(positive),metadata(deleted)],offset:0,limit:40,total:2},NEXT)));
    await h.click('project-working-history');const labels=h.nodes.get('project-working-history-list').querySelectorAll('button').map(b=>b.textContent);assert.match(labels[1],/note deletion/);assert.doesNotMatch(labels[1],/null/);
    h.answers.push(response(bound(selection(positive),NEXT)));await h.row('project-working-history-list');assert.equal(h.nodes.get('project-working-text').value,text);assert.equal(h.nodes.get('project-working-delete-fields').disabled,true);
  }
  {
    const h=mount();await tick();await chooseMissing(h);
    h.answers.push(response(bound(page({...missing,state:'unchanged',observed_sha256:sha,observed_bytes:positive.bytes,reason:null}))));await h.click('project-working-load');
    assert.equal(h.nodes.get('project-working-delete-fields').disabled,true,'Fresh inspection invalidates prior missing-note choice');
    h.nodes.get('project-working-delete-confirm').checked=true;const before=h.requests.length;await h.submit('project-working-delete-form');assert.equal(h.requests.length,before);
  }
  {
    const h=mount();await tick();await chooseMissing(h);h.nodes.get('project-working-delete-confirm').checked=true;
    h.answers.push(response(bound({id,project_id:P,kind:'note',path,revision:2,sha256:sha,bytes:0,deleted:true,adopted_at:stamp,changed:true},NEXT)));
    await h.submit('project-working-delete-form');assert.match(h.nodes.get('project-files-error').textContent,/differs/);assert.equal(h.nodes.get('project-working-text').value,text,'Malformed deletion ACK cannot replace captured text');
  }
  console.log('PASS 3 note-deletion controller groups: explicit missing-note confirmation, exact CAS, tombstone/history, refresh invalidation and malformed ACK refusal');
})().catch(error=>{console.error(error);process.exitCode=1;});
