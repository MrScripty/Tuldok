"""Independent real local HTTP boundary probe; all provider replies synthetic."""
import hashlib, json, pathlib, sys, tempfile, threading, urllib.error, urllib.request, uuid
from http.server import ThreadingHTTPServer
ROOT=pathlib.Path('/workspace/Tuldok')
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from app import Dataset, make_handler
from fake_classification_model import start
from workbench import WorkbenchError

def check(condition,message):
    if not condition: raise AssertionError(message)

def blocked(fn,message):
    try: fn()
    except (WorkbenchError,urllib.error.HTTPError): return
    raise AssertionError(message)

with tempfile.TemporaryDirectory(prefix='classification-boundary-') as tmp:
    data=Dataset(tmp); provider,url,requests=start()
    http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(data))
    threading.Thread(target=http.serve_forever,daemon=True).start()
    endpoint=f'http://127.0.0.1:{http.server_port}/api/workbench/text-classification-proposals'
    def api(path='',body=None):
        req=urllib.request.Request(endpoint+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as reply:return json.load(reply)
    def source(suffix):return data.workbench.import_asset(dict(kind='text',name=suffix,text='Exact text '+suffix+' e\u0301 😀',groups=['independent-'+suffix],rights='Authored synthetic reviewer fixture'))
    def generate(row,instruction='  Exact guidance\n',labels=None):
        body=dict(request_id=uuid.uuid4().hex,source_id=row['id'],revision=row['revision'],source_revision=row['source_revision'],server_url=url+'/v1/',model='classification-fixture',instruction=instruction,seed=4294967295,labels=labels or ['\ufeffexact','café','cafe\u0301'])
        ack=api(body=body);data.text_classification_proposals.worker.join(5)
        check(not data.text_classification_proposals.worker.is_alive(),'bounded worker completed')
        job=api('/'+ack['id']);return body,job
    def decide(job,decision='apply_draft',**updates):
        body=dict(revision=job['revision'],decision=decision)
        if decision=='apply_draft':body['labels']=job['config']['labels']
        body.update(updates);return api('/decide/'+job['id'],body)
    def state():return '\n'.join(data.db.iterdump())
    try:
        row=source('deletion');body,job=generate(row);check(job['status']=='completed','completed deletion candidate')
        with data.lock,data.db:data.db.execute('DELETE FROM workbench_records WHERE id=?',(row['id'],))
        before=state();blocked(lambda:decide(job),'deleted source cannot Apply');check(state()==before,'deleted Apply leaves all persisted state unchanged')
        count=len(requests);check(api(body=body)['id']==job['id'],'same admission reconciles after source deletion');check(len(requests)==count,'deleted source same-ID replay never reruns inference')
        blocked(lambda:decide(job,'reject',revision=job['revision']-1),'stale Reject rejected')
        rejected=decide(job,'reject',labels=['unrelated']);check(rejected['record'] is None and rejected['changed'],'current Reject independent of deleted source and unrelated labels')
        check(not decide(rejected['job'],'reject')['changed'],'Reject idempotent after deletion')
        print('deleted_source_apply_no_mutation_and_reject_independent PASS')

        row=source('revision');body,job=generate(row);before=state()
        for updates in [dict(revision=job['revision']-1),dict(revision=True),dict(labels=list(reversed(job['config']['labels']))),dict(labels=['invented'])]:
            blocked(lambda updates=updates:decide(job,**updates),'stale or malformed Apply rejected');check(state()==before,'invalid Apply leaves state unchanged')
        updated=data.workbench.save(row['id'],dict(row,annotation={'label':'human prior target'},review='human_reviewed'))
        before=state();blocked(lambda:decide(job),'existing target cannot be overwritten');check(state()==before,'classification cannot overwrite reviewed target')
        check(decide(job,'reject')['record'] is None,'Reject remains usable after target changed')
        print('proposal_revision_label_cas_and_existing_target_fence PASS')

        row=source('selection');ref={key:row[key] for key in ('id','revision','source_revision')}
        fixed=data.selections.create(dict(name='Exact selected text',items=[ref]))
        answerbody=dict(id=uuid.uuid4().hex,prompt_id=row['id'],revision=0,parent_revision=row['revision'],source_revision=row['source_revision'],completion='Exact independent answer\r\n😀 ',review='human_reviewed')
        answer=data.workbench.save_response(answerbody)['response']
        pair={key:answerbody[key] for key in ('id','prompt_id','parent_revision','source_revision')};pair['revision']=answer['revision']
        instruction_body=dict(format='text_instruction_v1',items=[pair],seed=42,ratios=dict(train=100,validation=0,test=0))
        before_preview=data.releases.preview(instruction_body);check(before_preview['eligible'],'initial answer pair eligible')
        body,job=generate(row);check(job['config']['requested_server_url']==body['server_url'] and job['config']['instruction']==body['instruction'],'exact raw provider and prompt preserved')
        brief=json.loads(requests[-1]['body']['messages'][1]['content']);check(brief['labels']==body['labels'] and brief['instruction']==body['instruction'],'Unicode labels and guidance unchanged on wire')
        applied=decide(job);current=applied['record'];check(current['review']=='draft' and current['annotation']=={'label':'\ufeffexact'},'Apply only draft exact label including BOM')
        for key in ('provenance','groups','parents','text','content_hash','source_sha256','source_revision'):check(current[key]==row[key],'preserved acquisition/source '+key)
        check(not data.selections.load(fixed['id'])['current'],'saved fixed text revisions stale after Apply')
        check(data.workbench._response(answer['id'])==answer,'independent saved response unchanged')
        check(not data.releases.preview(instruction_body)['eligible'],'old fixed answer pair stale after Apply')
        blocked(lambda:data.releases.create(dict(instruction_body,preview_token=before_preview['preview_token'])),'old preview token cannot freeze stale answer pair')
        record_body=dict(items=[{key:current[key] for key in ('id','revision','source_revision')}],seed=42,ratios=dict(train=100,validation=0,test=0))
        check(not data.releases.preview(record_body)['eligible'],'draft classification cannot be released without author review')
        before=state();blocked(lambda:decide(job,labels=['invented']),'replay still checks exact labels');check(state()==before,'bad replay no mutation')
        check(not decide(job)['changed'],'good replay idempotent even original proposal revision')
        print('draft_provenance_fixed_text_and_answer_selection_compatibility PASS')

        row=source('abstain');body,job=generate(row,'abstain');before=state()
        check(job['status']=='abstained' and job['annotation'] is None and job['response_sha256'],'explicit abstention with retained evidence')
        blocked(lambda:decide(job),'abstention never applies');check(state()==before,'abstention Apply no mutation')
        check(data.workbench.get(row['id'])==row,'abstention leaves exact source untouched')
        check(decide(job,'reject')['changed'],'abstention can be rejected explicitly')
        print('abstention_never_guesses_or_grants_review PASS')
        print(json.dumps({'synthetic_provider_requests':len(requests),'real_inference':False,'cases':4}))
    finally:
        http.shutdown();http.server_close();data.close();provider.shutdown();provider.server_close()
