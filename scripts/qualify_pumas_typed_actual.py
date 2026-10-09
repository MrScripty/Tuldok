#!/usr/bin/env python3
"""Qualify consumer owners against an already running pinned native gateway.

Requires the authored non-test managed-process harness receipt. No model loads,
downloads, simulated Pumas gateway, automatic retry or public writes.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
import pumas_operations as pumas
from workbench import WorkbenchError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    gateway=json.loads(args.gateway_receipt.read_text()); root=args.gateway_receipt.parent
    assert gateway['producer_commit']==pumas.SOURCE_COMMIT
    assert all(gateway[k] is True for k in ('compiled_without_cfg_test','controlled_no_models','owned_listener_verified'))
    def control(**changes):
        path=root/'text-worker/control.json'; value=json.loads(path.read_text());value.update(changes)
        staging=path.with_suffix('.pending');staging.write_text(json.dumps(value));staging.replace(path)
    def posts():
        path=root/'text-worker/requests.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines() if json.loads(line).get('method')=='POST']
    cases=[]; evidence=[]
    with tempfile.TemporaryDirectory(prefix='tuldok-native-typed-') as folder:
        data=Dataset(folder)
        def source(name):
            return data.workbench.import_asset(dict(kind='text',name=name,text='The meeting is confirmed. '+name,
                groups=['native-authored-family'],rights='Authored controlled qualification'))
        def body(row,**changes):
            value=dict(request_id=uuid.uuid4().hex,source_id=row['id'],revision=row['revision'],source_revision=row['source_revision'],
                server_url=gateway['gateway_url'],model=gateway['text_alias'],instruction='Classify exactly.',labels=['positive','negative'],
                seed=None,protocol=pumas.PROTOCOL,profile=None)
            value.update(changes);return value
        def generate(request):
            owner=data.text_classification_proposals;job=owner.start(request);owner.worker.join(10)
            if owner.worker.is_alive():
                owner.cancel({'job_id':job['id']});owner.worker.join(3);raise AssertionError('Controlled qualification did not finish.')
            return owner.get(job['id'])
        def check(condition,name,detail=None):
            assert condition,(name,detail);cases.append(name)
        try:
            control(text_mode='success',text_response='{"label":"positive"}',text_delay=0)
            manifest=pumas.capabilities(gateway['gateway_url'],gateway['text_alias'])
            check(manifest['capabilities']['profile']==gateway['text_profile'],'actual selected alias resolves exact profile')
            row=source('classification');request=body(row);before=len(posts());job=generate(request);evidence.append(job)
            check(job['status']=='completed' and job['canonical_request']['profile']==gateway['text_profile'],
                'classification actual typed result and captured profile',job['error'])
            check(data.workbench.get(row['id'])['annotation'] is None,'proposal leaves source unchanged')
            data.text_classification_proposals.start(request)
            check(len(posts())==before+1,'local same-ID admission does not replay native provider')
            applied=data.text_classification_proposals.decide(job['id'],dict(revision=job['revision'],decision='apply_draft',labels=request['labels']))['record']
            check(applied['review']=='draft' and applied['provenance']==row['provenance'],'classification draft preserves rights/history owner')
            try:
                data.releases.create(dict(items=[{k:applied[k] for k in ('id','revision','source_revision')}],ratios=dict(train=100,validation=0,test=0),seed=42))
                raise AssertionError('Draft was released')
            except WorkbenchError: cases.append('draft cannot release before separate human review')
            reviewed=data.workbench.save(applied['id'],dict(revision=applied['revision'],source_revision=applied['source_revision'],
                task='text_classification',annotation=applied['annotation'],groups=applied['groups'],review='human_reviewed'))
            control(text_response=json.dumps({'candidates':[{'text':'The confirmed meeting will take place, classification.',
                'label':'positive','evidence':[{'start':0,'end':len(reviewed['text']),'quote':reviewed['text']}]}]}))
            rewrite={k:v for k,v in body(reviewed).items() if k not in ('request_id','labels')};rewrite['count']=1
            owner=data.grounded;proposal=owner.start(rewrite);owner.worker.join(10);proposal=owner.get(proposal['id']);evidence.append(proposal)
            check(proposal['status']=='completed','actual typed grounded quotes validated',proposal['error'])
            candidate=owner.review(proposal['id'],dict(revision=proposal['revision'],candidate_id=proposal['candidates'][0]['id'],
                decision='admit_draft',note='Controlled source/quote reviewed; separate annotation review remains.'))['record']
            check(candidate['review']=='draft' and candidate['parents']==[reviewed['id']] and candidate['groups']==reviewed['groups'],
                'grounded candidate inherits source family and remains draft')
            control(text_response='{"label":"positive"}',text_delay=3.2)
            started=time.monotonic();slow=generate(body(source('long controlled response')))
            check(slow['status']=='completed' and time.monotonic()-started>=3,'finite generation outlives three-second discovery budget',slow['error'])
            control(text_delay=0,text_mode='transport_loss');request=body(source('uncertain loss'));before=len(posts());lost=generate(request);evidence.append(lost)
            check(lost['provider_outcome']=='unknown' and lost['status']=='failed','native authoritative unknown transport outcome',lost)
            data.text_classification_proposals.start(request)
            check(len(posts())==before+1,'unknown native provider attempt is never replayed by same local ID')
            control(text_mode='hold');request=body(source('explicit cancellation'));before=len(posts());owner=data.text_classification_proposals;cancelled=owner.start(request)
            end=time.monotonic()+3
            while len(posts())==before and time.monotonic()<end:time.sleep(.02)
            check(len(posts())==before+1,'held native request reaches exactly one original backend')
            owner.cancel({'job_id':cancelled['id']});owner.worker.join(3);cancelled=owner.get(cancelled['id']);evidence.append(cancelled)
            check(not owner.worker.is_alive() and owner.active_id is None and cancelled['provider_outcome']=='unknown',
                'explicit cancellation retires local actor/worker without cessation claim')
            control(text_mode='success')
            unavailable=generate(body(source('unknown served alias'),model='unserved-exact-alias'))
            check(unavailable['status']=='failed' and unavailable['provider_outcome']=='not_admitted','unknown serving alias rejects before provider effects')
            image=dict(server_url=gateway['gateway_url'],model=gateway['image_alias'],protocol=pumas.PROTOCOL,profile=None,
                request_id=uuid.uuid4().hex,prompt='Literal controlled blue fixture.',width=16,height=12,seed=7)
            result=data.image_requests.generate(image);evidence.append(result['metadata'])
            check(result['metadata']['canonical_request']['profile']==gateway['image_profile'] and (result['width'],result['height'])==(16,12),
                'actual managed image admission and native typed PNG projection')
            try:data.image_requests.generate(dict(image,width=2049));raise AssertionError('Oversized image admitted')
            except ValueError:cases.append('consumer image allocation bound rejects before POST')
        finally:
            control(text_mode='success',text_delay=0,text_response='{"label":"positive"}')
            data.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'origin':'Actual pinned production Pumas gateway, controlled backend; no model inference.',
        'producer_commit':pumas.SOURCE_COMMIT,'gateway':gateway,'passed':cases,'count':len(cases),'evidence':evidence},indent=2)+'\n')
    print(str(len(cases))+' actual native consumer checks passed: '+str(args.output))


if __name__=='__main__':main()
