'use strict';
// Literal presentation-document fixtures, independent of the decoder.
const crypto=require('node:crypto');
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const project='a'.repeat(32),path='notes/00-methods.portfolio.json';
const summary={method:'A small pressure correction model.',purpose:'Measure one pressure correction.',experiment:'Two retained training scenes.',outcome:'Retained diagnostic result; not a rollout qualification.',lesson:'Compare work and accuracy on the same cases.',reproduction:'Use the retained source recipe; clean retraining remains pending.'};
const cardText=Object.values(summary).join('\n\n')+'\nOriginal receipt bytes remain here.\n';
const ref=(path,text)=>({file_id:hash(project+'\0note\0'+path),path,revision:2,sha256:hash(text)});
const first={id:'fit-first',label:'First model',group_id:'pressure',aliases:['C107'],review:'source_reviewed',card:ref('notes/first.md',cardText),summary};
const second={id:'fit-second',label:'Second model',group_id:'pressure',aliases:['C106'],review:'review_pending',card:ref('notes/second.md','Original pending card.\n'),summary:null};
const document={format:'project_model_portfolio_v1',project_id:project,title:'Retained fit guide',description:'Authored retrospective organization; original Trial history is unchanged.',authorship:'retrospective',groups:[{id:'pressure',label:'Pressure methods',parent:null,description:'Pressure requests, not complete simulation steps.'}],models:[first,second],relationships:[{from:first.id,to:second.id,kind:'comparison',explanation:'Authored comparison with the earlier control.',evidence_model:first.id,excerpt:summary.lesson}]};
const result=(model,text)=>({id:model.card.file_id,project_id:project,kind:'note',path:model.card.path,version:{revision:2,sha256:hash(text),bytes:Buffer.byteLength(text),text,actor_id:'b'.repeat(32),adopted_at:'2026-10-25T00:00:00+00:00'}});
const cards=[result(first,cardText),result(second,'Original pending card.\n')];
const raw=JSON.stringify(document),guideRef=ref(path,raw),guide={...result({card:guideRef},raw),version:{...result({card:guideRef},raw).version,revision:1}};
const inspection={id:guideRef.file_id,kind:'note',path,revision:1,expected_sha256:guideRef.sha256,expected_bytes:Buffer.byteLength(raw),observed_sha256:guideRef.sha256,observed_bytes:Buffer.byteLength(raw),state:'unchanged',reason:null};
module.exports={project,document,summary,cards,guide,inspection};
