'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const fixture=require('./model_portfolio_fixture.cjs'),window={};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/project-model-portfolio.js'),'utf8'),{window,TextEncoder});
const {decode,checkCard}=window.ProjectModelPortfolioDocument;
const valid=()=>structuredClone(fixture.document),parse=value=>decode(JSON.stringify(value));
assert.deepEqual(JSON.parse(JSON.stringify(parse(valid()))),fixture.document);
let checks=1;
function bad(change,message,code='invalid'){
  const value=valid();change(value);
  assert.throws(()=>parse(value),error=>error.code===code&&error.message===message);checks++;
}
bad(d=>{d.format='other';},'Unsupported model-organization document format.','unsupported');
bad(d=>{d.extra=true;},'Invalid model-organization document.');
bad(d=>{d.models=[];},'Invalid model-organization document.');
bad(d=>{d.groups.push(structuredClone(d.groups[0]));},'Invalid or duplicate organization group.');
bad(d=>{d.groups[0].parent='missing';},'Organization group parent is unavailable.');
bad(d=>{d.groups[0].parent='pressure';},'Organization grouping contains a cycle.');
bad(d=>{d.models.push(structuredClone(d.models[0]));},'Invalid or duplicate organized model.');
bad(d=>{d.models[0].group_id='missing';},'Invalid or duplicate organized model.');
bad(d=>{d.models[0].aliases.push('C107');},'Invalid or duplicate organized model.');
bad(d=>{d.models[0].review='qualified';},'Invalid or duplicate organized model.');
bad(d=>{delete d.models[0].summary.method;},'Reviewed model requires all six authored summary fields.');
bad(d=>{d.models[1].summary={};},'Pending review cannot expose a reviewed summary.');
bad(d=>{d.models[0].card.path='notes/../private';},'Invalid captured model-note reference.');
bad(d=>{d.models[0].card.revision=0;},'Invalid captured model-note reference.');
bad(d=>{d.relationships[0].to='unknown';},'Invalid authored model relationship.');
bad(d=>{d.relationships[0].to=d.relationships[0].from;},'Invalid authored model relationship.');
bad(d=>{d.relationships[0].kind='trial_parent';},'Invalid authored model relationship.');
bad(d=>{d.relationships.push(structuredClone(d.relationships[0]));},'Duplicate authored model relationship.');
bad(d=>{const a=d.relationships[0];a.kind='parameter_derivation';d.relationships.push({...a,from:a.to,to:a.from});},'Authored parameter derivation contains a cycle.');
assert.throws(()=>decode('not JSON'),error=>error.code==='invalid'&&error.message==='Organization note is not valid JSON.');checks++;
assert.throws(()=>decode(' '.repeat(1048577)),error=>error.code==='invalid'&&error.message==='Organization note exceeds its retained text limit.');checks++;
assert.equal(checkCard(valid(),fixture.document.models[0],fixture.cards[0]),fixture.cards[0].version.text);checks++;
for(const change of [r=>{r.project_id='c'.repeat(32);},r=>{r.id='d'.repeat(64);},r=>{r.path='notes/other.md';},r=>{r.version.revision=3;},r=>{r.version.sha256='e'.repeat(64);},r=>{r.version.deleted=true;}]){
  const result=structuredClone(fixture.cards[0]);change(result);
  assert.throws(()=>checkCard(valid(),fixture.document.models[0],result),error=>error.code==='invalid'&&error.message==='Model card differs from its exact retained organization reference.');checks++;
}
{
  const value=valid();value.models[0].summary.method='Not present in the captured card.';
  assert.throws(()=>checkCard(value,value.models[0],fixture.cards[0]),error=>error.message==='Authored summary differs from the captured model card.');checks++;
}
{
  const value=valid();value.relationships[0].excerpt='Not present in the captured card.';
  assert.throws(()=>checkCard(value,value.models[0],fixture.cards[0]),error=>error.message==='Authored relationship excerpt differs from its captured model card.');checks++;
}
console.log('PASS authored portfolio document:',checks,'literal contract/reference decisions; no native capture or browser claim.');
