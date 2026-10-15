"""Actual owner/HTTP/Run classifier qualification; no injected completion or artifacts."""
import argparse
import base64
import copy
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
import agent_api
from app import Dataset,make_handler
from auth_helpers import ExplicitOwnerFixture
from PIL import Image


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n')


def populate(dataset, fixture):
    if fixture != {'format':'authored_image_fixture_v1','description':'Deterministic authored CPU evidence fixture, not a quality benchmark',
                   'classes':['circle','square'],'splits':['train','validation','test'],
                   'examples_per_class_split':2,'size':[24,24],'generator':'rgb_patterns_v1','seed':19}:
        raise ValueError('Fixture source differs from the qualified RGB pattern protocol.')
    rows=[]
    for split_index,split in enumerate(fixture['splits']):
        for label_index,label in enumerate(fixture['classes']):
            for number in range(2):
                image=Image.new('RGB',(24,24));pixels=image.load()
                for y in range(24):
                    for x in range(24):
                        shape=(x-12)**2+(y-12)**2<50 if label=='circle' else 6<=x<18 and 6<=y<18
                        pixels[x,y]=((190 if shape else 20)+number,30+split_index*20,(x*3+y+19+number*17)%180)
                out=io.BytesIO();image.save(out,format='PNG')
                row=dataset.workbench.import_asset({'kind':'image','image':base64.b64encode(out.getvalue()).decode(),
                    'name':f'{split}-{label}-{number}.png','groups':[f'authored-{split}-{label}-{number}'],
                    'rights':'Authored deterministic fixture for CPU contract qualification; not measured model quality.'},source_split=split)
                row=dataset.workbench.save(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],
                    task='image_classification',annotation={'label':label},groups=row['groups'],review='human_reviewed'))
                rows.append(row)
    return rows


def freeze(dataset,rows):
    body={'format':'image_classification_v1','items':[{key:row[key] for key in ('id','revision','source_revision')} for row in rows],
          'ratios':{'train':34,'validation':33,'test':33},'seed':42}
    preview=dataset.releases.preview(body)
    if not preview['eligible']:raise ValueError(str(preview['blockers']))
    return dataset.releases.create(dict(body,preview_token=preview['preview_token']))


def qualify(args):
    output=args.output.resolve();output.mkdir(mode=0o700,parents=True,exist_ok=False)
    fixture_path=args.fixture/'fixture.json';fixture_raw=fixture_path.read_bytes();fixture=json.loads(fixture_raw)
    dataset=Dataset(output/'catalog');owner=ExplicitOwnerFixture.bootstrap(dataset)
    with owner.bound(dataset):rows=populate(dataset,fixture);release=freeze(dataset,rows)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset));endpoint=f'http://127.0.0.1:{server.server_port}'
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    calls=[]
    def call(operation,arguments):
        version=2 if operation in ('graphs.create','graphs.save') else 1
        method,path,body=agent_api.project_request(operation,arguments,version=version)
        headers={**owner.headers,'Origin':endpoint,agent_api.CONTRACT_HEADER:agent_api.selected_header(operation,version)}
        if body is not None:headers['Content-Type']='application/json'
        request=Request(endpoint+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
        with urlopen(request,timeout=120) as response:
            value=json.load(response);calls.append({'operation':operation,'status':response.status})
        # Every public response passes its selected shared output contract.
        agent_api.validate_output(operation,{'status':response.status,'result':value},version=version)
        return value
    started=time.monotonic()
    try:
        definitions=call('recipes.list',{})
        definition=next(item for item in definitions['recipes'] if item['id']=='image_classification_model_v2')
        model_body=copy.deepcopy(definition['model_template']);model_body['name']='Qualified actual CPU TinyCNN'
        model_body['specification'].update(widths=[8,12,16],input_size=32)
        model_body['preprocessing_policy']['size']=[32,32]
        model=call('models.create',model_body)
        material=call('models.publish',{'model_id':model['id'],'revision':model['revision']})
        graph=call('graphs.create',{'name':'Actual bounded classifier','release_id':release['id'],'recipe':'image_classification_model_v2'})
        changed=copy.deepcopy(graph)
        next(node for node in changed['nodes'] if node['type']=='train')['parameters'].update(epochs=2,widths=[8,12,16],input_size=32)
        graph=call('graphs.save',{'graph_id':graph['id'],'revision':graph['revision'],'document':changed})
        validation=call('graphs.validate',{'graph_id':graph['id'],'revision':graph['revision']})
        study=call('studies.create',{'name':'Finite actual classifier qualification','limits':{'attempt_slots':3,'admitted_wall_seconds':3000,
            'retained_bytes':512*1024**2,'peak_staging_bytes':1024**3},'policy':validation['selection_policy']})
        def prepare(graph,study):
            trial=call('studies.prepare_trial',{'study_id':study['id'],'request_key':'prepare-'+graph['id'],
                'revision':study['revision'],'graph_id':graph['id'],'graph_revision':graph['revision'],'model':material['ref'],'replicate':0})
            current=call('studies.get',{'study_id':study['id']})['study']
            if not current['open']:
                call('studies.continue',{'study_id':study['id'],'request_key':'continue-'+graph['id'],
                    'revision':current['revision'],'admission_epoch':current['admission_epoch']})
                current=call('studies.get',{'study_id':study['id']})['study']
            admitted=call('studies.admit',{'study_id':study['id'],'request_key':'admit-'+graph['id'],
                'revision':current['revision'],'admission_epoch':current['admission_epoch'],'trial_id':trial['id']})
            run=admitted['run'];until=time.monotonic()+180
            while run['state'] in ('queued','running','cancelling') and time.monotonic()<until:
                time.sleep(.15);run=call('runs.get',{'run_id':run['id']})
            if run['state']!='completed':raise ValueError(f'Actual Run failed: {run}')
            return trial,run
        trial,run=prepare(graph,study)
        evidence=call('runs.model_evidence',{'run_id':run['id']})
        save(output/'evidence.json',evidence);save(output/'run.json',run);save(output/'trial.json',trial)
        for entry in evidence['checkpoint_index']['entries']:
            query=call('runs.model_evidence',{'run_id':run['id'],'checkpoint_sha256':entry['checkpoint']['sha256']})
            save(output/f'checkpoint-{entry["clocks"]["epoch"]}.json',query)
        # Correct current train annotation; retain frozen validation membership unchanged.
        with owner.bound(dataset):
            current=dataset.workbench.get(rows[0]['id'])
            rows[0]=dataset.workbench.save(current['id'],dict(revision=current['revision'],source_revision=current['source_revision'],
                task=current['task'],annotation={'label':'square'},groups=current['groups'],review='human_reviewed'))
            corrected_release=freeze(dataset,rows)
        corrected=call('graphs.create',{'name':'Corrected current data','release_id':corrected_release['id'],'recipe':'image_classification_model_v2'})
        edited=copy.deepcopy(corrected)
        next(node for node in edited['nodes'] if node['type']=='train')['parameters'].update(epochs=2,widths=[8,12,16],input_size=32)
        corrected=call('graphs.save',{'graph_id':corrected['id'],'revision':corrected['revision'],'document':edited})
        call('studies.reconcile',{'study_id':study['id']})
        second_trial,second_run=prepare(corrected,call('studies.get',{'study_id':study['id']})['study'])
        comparison=call('runs.compare_model_evidence',{'run_id':run['id'],'other_run_id':second_run['id']})
        if comparison['state']!='compatible':raise ValueError(str(comparison))
        save(output/'comparison.json',comparison);save(output/'corrected-run.json',second_run)
        # No replay or backfill on close/reopen; identical immutable evidence remains readable.
        server.shutdown();server.server_close();thread.join(timeout=5);dataset.close()
        dataset=Dataset(output/'catalog')
        with owner.bound(dataset):
            reopened=dataset.runs.model_evidence(run['id'])
            if reopened!=evidence:raise ValueError('Cold evidence reopen changed.')
            private=dataset.runs._load(run['id'])
            job={'parent_pid':os.getpid(),'release_path':str(dataset.releases.locate(run['release_id'])),
                 'release_sha256':run['release_sha256'],'output_dir':str(dataset.runs.path/run['id']),'parameters':run['parameters']}
            save(output/'independent-job.json',job)
        runtime=os.environ['TULDOK_TRAINING_PYTHON']
        replay=subprocess.run([runtime,str(ROOT/'image_training.py'),'--verify-evidence',str(output/'independent-job.json')],capture_output=True,timeout=100)
        if replay.returncode:raise ValueError('Independent cold checkpoint reconstruction failed: '+replay.stdout.decode())
        receipt={'task':'image','source_fixture_sha256':hashlib.sha256(fixture_raw).hexdigest(),
            'run_id':run['id'],'corrected_run_id':second_run['id'],'study_id':study['id'],
            'checkpoints':len(evidence['checkpoint_index']['entries']),'probe_members':len(evidence['probe']['members']),
            'retained_bytes':sum(item['bytes'] for item in run['artifacts']),
            'wall_elapsed_seconds':time.monotonic()-started,'peak_rss_bytes':run['metrics']['runtime']['peak_rss_bytes'],
            'runtime':run['runtime']['runtime'],'hardware':{'machine':platform.machine(),'cpu_count':os.cpu_count()},
            'actual_training':True,'cold_reopen':True,'independent_fixed_inference':True,'compatible_correction':True,
            'http_operations':calls,'ui_qualification':'requires separate1440/390 keyboard browser run',
            'limitations':['Authored patterns qualify evidence plumbing, not generalization or useful classifier quality.','CPU only; no GPU, resume or adaptive budget.']}
        save(output/'receipt.json',receipt)
        return receipt
    finally:
        if thread.is_alive():server.shutdown();server.server_close();thread.join(timeout=5)
        dataset.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',choices=['image','text','audio'],required=True);parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.task == 'image':
        result = qualify(args)
    else:
        from qualify_one_fit import qualify as qualify_one_fit
        result = qualify_one_fit(args)
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
