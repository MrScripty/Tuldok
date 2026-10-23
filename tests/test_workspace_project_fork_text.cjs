'use strict';
const assert=require('node:assert/strict');
const {mount,state,records,response,tick,B,P,ACTOR,C,NEXT,capabilities,versionPins}=require('./test_workspace_project_files_m4.cjs');
const R='1'.repeat(32),origin={project_id:ACTOR,checkpoint:NEXT,family:'workbench_record',id:'2'.repeat(32),revision:1,source_revision:1};
const row=()=>({id:R,kind:'text',name:'Independent fork Ω',text:'Exact original scientific note',groups:['fixture'],parents:[],provenance:{method:'project_fork',rights:'Owned retained source',origin},task:'text_corpus',annotation:{note:'Original rationale'},review:'draft',revision:1,source_revision:1,created_at:'2026-10-22T12:00:00+00:00',updated_at:'2026-10-22T12:00:00+00:00'});
const record=value=>({binding:B,project_id:P,checkpoint:C,record:value,history:[value],next_history_before_revision:null});
function caps(v2){const value=structuredClone(capabilities);if(v2)for(const op of value.operations)if(versionPins[op.id])op.contracts.push({...op.contracts[0],version:2,sha256:versionPins[op.id][2]});return value;}
(async()=>{
  {
    const h=mount(caps(true));await tick();
    // Replace the next read-only query with a real record summary DTO.
    const full=row(),summary=Object.fromEntries(Object.entries(full).filter(([key])=>['id','kind','name','task','review','revision','source_revision','created_at','updated_at'].includes(key)));
    h.answers.push(response(state()),response({...records(),items:[summary]}));await h.click('project-files-refresh');
    h.answers.push(response(record(full)),response({...records(),items:[summary]}));await h.row('records-list');
    const get=h.requests.findLast(r=>r.options.headers['Tuldok-Operation-Contract'].startsWith('project_files.get/'));
    assert.ok(get.options.headers['Tuldok-Operation-Contract'].startsWith('project_files.get/2/'));assert.equal(h.nodes.get('record-text').value,full.text);assert.equal(h.nodes.get('annotation-value').value,'Original rationale');
    h.input('annotation-value','Independent new rationale');const revised={...full,revision:2,annotation:{note:'Independent new rationale'}};
    h.answers.push(response(record(revised)),response({...records(),items:[{...summary,revision:2}]}));await h.submit('annotation-form');
    const edit=h.requests.findLast(r=>r.options.method==='POST');assert.ok(edit.options.headers['Tuldok-Operation-Contract'].startsWith('project_files.annotate/2/'));assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('annotation-value').value,'Independent new rationale');
  }
  {
    const h=mount(caps(false));await tick();const full=row(),summary=Object.fromEntries(Object.entries(full).filter(([key])=>['id','kind','name','task','review','revision','source_revision','created_at','updated_at'].includes(key)));
    h.answers.push(response(state()),response({...records(),items:[summary]}));await h.click('project-files-refresh');h.answers.push(response(record(full)));await h.row('records-list');
    assert.match(h.nodes.get('project-files-error').textContent,/Version 1 cannot represent/);assert.equal(h.nodes.get('record-text').value,'');
  }
  console.log('Fork text controller: 2 selected groups PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
