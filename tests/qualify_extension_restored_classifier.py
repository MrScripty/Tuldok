"""Opt-in actual built-in continuity after restored-only B selection refusals.

Read a separately passed E4 report and reviewed selection. This driver can only
mutate its existing disposable restored catalog, never the original source.
One ordinary owner Study admission trains a small image classifier. Historical
A/B source/package reads are bookended with process launch and scheduling
forbidden. This is a continuity fixture, not numerical or physical acceptance.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import uuid

from psycopg.conninfo import make_conninfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api
import backup_metadata as transfer
from app import Dataset,make_handler
from auth_helpers import ExplicitOwnerFixture
from workbench import WorkbenchError
import qualify_extension_ab_retention as retention
from qualify_model_development import populate,freeze


def require(condition,message):
    if not condition:raise RuntimeError(message)


def read_report(path):
    raw=retention.regular(path,2*1024**2);value=retention.evidence.decode(raw,2*1024**2)
    require(value.get('format')=='extension_ab_retention_qualification_v1' and
            value.get('state') in ('passed','rootless_retention_verified_disable_pending') and
            value.get('source_unchanged') is True and value.get('restored_database_retained') is True,
            'Select the successful actual E4 stopped restore report.')
    source=Path(value['source']).resolve();output=Path(value['output']).resolve();destination=output/'restored-catalog'
    require(source!=destination and source not in destination.parents and destination not in source.parents and
            destination.is_dir() and any(destination.glob('.restore-receipt-*.json')),
            'Only the existing disposable restored destination can be selected.')
    database=value['restored_database']
    require(type(database) is str and database.startswith('tuldok_ab_retention_') and
            len(database)==len('tuldok_ab_retention_')+32 and retention.ID.fullmatch(database[-32:]),
            'Select the exact new E4 database.')
    return value,destination,database,hashlib.sha256(raw).hexdigest()


def guard_output(report,destination,selected,output):
    """Refuse every original/catalog/source tree before creating a receipt."""
    protected=[Path(report['source']),destination,ROOT,
               Path(report['output'])/'restored-only-b-source',
               *[Path(value) for value in selected.get('current_roots',{}).values()]]
    for path in protected:transfer.separate_paths(path,output)


def main(args):
    report,destination,database,report_sha=read_report(args.retention_report)
    require(report_sha==args.retention_report_sha256,'Select the exact reviewed stopped restore report.')
    disabled_raw=retention.regular(args.disabled_selection_report,2*1024**2)
    require(hashlib.sha256(disabled_raw).hexdigest()==args.disabled_selection_report_sha256,
            'Select the exact actual restored B disable/removal witness.')
    disabled=retention.evidence.decode(disabled_raw,2*1024**2)
    require(disabled.get('format')=='extension_ab_restored_disable_refusal_v1' and disabled.get('state')=='passed' and
            disabled.get('retention_report_sha256')==report_sha and
            disabled.get('restored_catalog_path')==str(destination) and
            {row['mode'] for row in disabled.get('new_selection_refusals',[])}=={'disabled','removed'},
            'Actual restored B disable/removal refusals must precede continuity.')
    selected=retention.load_selection(args.selection)
    require(selected['catalog_id']==report['baseline']['dataset_id'],'Reviewed retention catalog differs.')
    require(hashlib.sha256(args.selection.read_bytes()).hexdigest()==report['selection_sha256'] and
            selected['references'].get('current_roots')==report['reviewed_references'].get('current_roots'),
            'Select the exact qualified retention selection and original root reference.')
    runtime=args.runtime_python.absolute()
    require(runtime.is_file() and os.environ.get('TULDOK_TRAINING_PYTHON')==str(runtime),
            'Explicitly select the actual supported CPU training interpreter; no fallback.')
    output=args.output.resolve();require(not output.exists(),'Choose an absent classifier evidence destination.')
    guard_output(report,destination,selected,output)
    output.mkdir(mode=0o700,parents=True)
    connection=make_conninfo(os.environ['TULDOK_DATABASE_URL'],dbname=database)
    retained_root=Path(report['output'])/'restored-only-b-source'
    require(retained_root.is_dir(),'Restored-only B selection source is missing.')
    roots={'retention-b':str(retained_root)}
    state=dict(format='extension_restored_classifier_continuity_v1',state='in_progress',
        retention_report_sha256=report_sha,selection_sha256=hashlib.sha256(args.selection.read_bytes()).hexdigest(),
        disabled_selection_report_sha256=args.disabled_selection_report_sha256,
        host_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),catalog_path=str(destination),
        database_name=database,catalog_id=selected['catalog_id'],project_roots=roots,
        admission_state='not_started',scope='Actual restored-only built-in continuity fixture; no model-quality/physics acceptance.')
    def save(name,value):
        path=output/name
        with path.open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')
        return path
    dataset=server=thread=owner=None;calls=[]
    try:
        dataset=Dataset(destination,dsn=connection,project_roots=roots)
        require(dataset.db.dataset_id==selected['catalog_id'],'Restored metadata identity differs.')
        require(dataset.db.connection.info.dbname==database,'Selected destination connection differs.')
        owner=ExplicitOwnerFixture.bootstrap(dataset)
        with owner.bound(dataset),patch('subprocess.Popen',side_effect=AssertionError('Historical reads must not execute')),\
                patch('runs.Runs._start',side_effect=AssertionError('Historical reads must not schedule')):
            # Configure roots={} only for this retained read proof; the new B
            # snapshot root is restored unchanged immediately afterward.
            available=dataset.projects.roots;dataset.projects.roots={}
            try:before=retention.selected_reads(dataset,selected)
            finally:dataset.projects.roots=available
        server=make_handler(dataset)
        from http.server import ThreadingHTTPServer
        server=ThreadingHTTPServer(('127.0.0.1',0),server)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        endpoint='http://127.0.0.1:'+str(server.server_port)
        def call(operation,arguments,version=1):
            method,path,body=agent_api.project_request(operation,arguments,version)
            headers={**owner.headers,agent_api.CONTRACT_HEADER:agent_api.selected_header(operation,version),'Origin':endpoint}
            if body is not None:headers['Content-Type']='application/json'
            request=Request(endpoint+path,method=method,headers=headers,data=None if body is None else agent_api.encoded(body))
            try:
                with urlopen(request,timeout=180) as response:status=response.status;value=json.loads(response.read())
            except HTTPError as error:
                raise RuntimeError('Selected public '+operation+' refused '+str(error.code)) from None
            agent_api.validate_output(operation,{'status':status,'result':value},version)
            calls.append({'operation':operation,'version':version,'status':status})
            return value
        with owner.bound(dataset):
            fixture_raw=(ROOT/'tests/fixtures/model_development/fixture.json').read_bytes()
            rows=populate(dataset,json.loads(fixture_raw));release=freeze(dataset,rows)
        definition=next(row for row in call('recipes.list',{})['recipes'] if row['id']=='image_classification_model_v2')
        body=copy.deepcopy(definition['model_template']);body['name']='Restored unrelated classifier after B disabled'
        body['specification'].update(widths=[4,4,4],input_size=32);body['preprocessing_policy']['size']=[32,32]
        draft=call('models.create',body);model=call('models.publish',{'model_id':draft['id'],'revision':draft['revision']})
        graph=call('graphs.create',{'name':'Restored unrelated TinyCNN continuity','release_id':release['id'],
                                  'recipe':'image_classification_model_v2'},2)
        document=copy.deepcopy(graph)
        next(row for row in document['nodes'] if row['type']=='train')['parameters'].update(epochs=1,widths=[4,4,4],input_size=32)
        graph=call('graphs.save',{'graph_id':graph['id'],'revision':graph['revision'],'document':document},2)
        validation=call('graphs.validate',{'graph_id':graph['id'],'revision':graph['revision']})
        study=call('studies.create',{'name':'Restored built-in continuity only','policy':validation['selection_policy'],
            'limits':{'attempt_slots':1,'admitted_wall_seconds':1200,'retained_bytes':512*1024**2,'peak_staging_bytes':1024**3}})
        trial=call('studies.prepare_trial',{'study_id':study['id'],'revision':study['revision'],'request_key':'prepare-'+uuid.uuid4().hex,
            'graph_id':graph['id'],'graph_revision':graph['revision'],'model':model['ref'],'replicate':0})
        current=call('studies.get',{'study_id':study['id']})['study']
        current=call('studies.continue',{'study_id':study['id'],'revision':current['revision'],
            'admission_epoch':current['admission_epoch'],'request_key':'continue-'+uuid.uuid4().hex})
        save('prepared.json',{'release':release,'model':model,'graph':graph,'study':current,'trial':trial,
                              'fixture_sha256':hashlib.sha256(fixture_raw).hexdigest()})
        state['admission_state']='may_have_been_sent';save('before-admission.json',state)
        admitted=call('studies.admit',{'study_id':study['id'],'revision':current['revision'],
            'admission_epoch':current['admission_epoch'],'trial_id':trial['id'],'request_key':'admit-'+uuid.uuid4().hex})
        run=admitted['run'];state.update(run_id=run['id'],admission_state='admitted')
        save('admission.json',admitted)
        deadline=time.monotonic()+300
        while run['state'] in ('queued','running','cancelling') and time.monotonic()<deadline:
            time.sleep(.2);run=call('runs.get',{'run_id':run['id']})
        save('run.json',run)
        require(run['state']=='completed','Actual unrelated classifier did not complete; never retry an uncertain admission.')
        evidence=call('runs.model_evidence',{'run_id':run['id']})
        require(evidence['state']=='verified' and len(evidence['checkpoint_index']['entries'])==1,
                'Actual one-epoch built-in evidence unavailable.')
        require(evidence['checkpoint_index']['entries'][0]['clocks']['epoch']==1,
                'Actual classifier checkpoint must identify its one epoch.')
        save('evidence.json',evidence)
        settled=call('studies.reconcile',{'study_id':study['id']})
        require(settled['charged']['attempt_slots']==1 and len(settled['reservations'])==1 and
                settled['reservations'][0]['run_id']==run['id'] and settled['reservations'][0]['state']=='settled',
                'Unrelated finite owner admission did not settle exactly once.')
        save('study.json',settled)
        deadline=time.monotonic()+15
        while dataset.runs._thread is not None and time.monotonic()<deadline:time.sleep(.05)
        material=call('recipes.material',{'ref':trial['material']})
        server.shutdown();server.server_close();thread.join(timeout=5);server=thread=None
        with owner.bound(dataset):dataset.access.logout()
        dataset.close();dataset=None
        with patch('subprocess.Popen',side_effect=AssertionError('Cold reads must not execute')),\
                patch('runs.Runs._start',side_effect=AssertionError('Historical reads must not schedule')):
            dataset=Dataset(destination,dsn=connection,project_roots=roots)
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                require(dataset.runs.get(run['id'])==run and dataset.models.material(model['ref'],verify=True)==model and
                        dataset.pipelines.recipe_material(trial['material'],verify=True)==material and
                        dataset.studies.get(study['id'])==settled and
                        dataset.runs.model_evidence(run['id'])==evidence,
                        'Cold actual classifier Run/Model/material/Study/evidence differs.')
                cold=[];locked=[]
                for item in run['artifacts']:
                    if item['locked']:
                        try:dataset.runs.artifact(run['id'],item['name'])
                        except WorkbenchError as error:
                            require((error.code,error.status)==('conflict',409),'Wrong protected test refusal.')
                            locked.append(item['name']);continue
                        raise RuntimeError('Protected classifier test output was disclosed.')
                    raw,_=dataset.runs.artifact(run['id'],item['name'])
                    captured,capture=dataset.runs.capture_artifact(run['id'],item['name'],item['sha256'])
                    with dataset.runs.open_artifact(run['id'],item['name']) as (stream,metadata):
                        digest=hashlib.sha256();count=0
                        while piece:=stream.read(1024**2):digest.update(piece);count+=len(piece)
                    require(raw==captured and len(raw)==count==metadata['bytes']==item['bytes'] and
                            hashlib.sha256(raw).hexdigest()==digest.hexdigest()==capture['measured_sha256']==item['sha256'],
                            'Cold actual classifier whole/stream/capture identity differs.')
                    cold.append({key:item[key] for key in ('name','bytes','sha256')})
                save('cold-custody.json',{'state':'passed','whole_stream_capture':cold,'protected_locked':locked,
                                         'process_and_scheduler_blocked':True})
                available=dataset.projects.roots;dataset.projects.roots={}
                try:require(retention.selected_reads(dataset,selected)==before,'Historical A/B source/package meaning changed.')
                finally:dataset.projects.roots=available
                releasedoc=next(row for row in dataset.pipelines.releases() if row['id']==release['id'])
        recipe_id=selected['b']['model']['material']['source_selector']['recipe_id']
        checks=dict(disposable_restored_catalog=True,refusals=[dict(mode=row['mode'],project_id=row['project_id'],recipe_id=recipe_id)
            for row in disabled['new_selection_refusals']],retained_runs=[
                dict(label='a',run_id=selected['a']['run']['id'],expected_fields=[dict(field_id='raw',stage='train')]),
                dict(label='b',run_id=selected['b']['run']['id'],expected_fields=[dict(field_id='raw',stage='raw_inference'),
                    dict(field_id='corrected',stage='boundary_enforcement')])],unrelated_run_id=run['id'],
            unrelated_graph_id=graph['id'],unrelated_release_id=release['id'],unrelated_recipe_choices=releasedoc['allowed_recipes'])
        for row in checks['retained_runs']:
            save('native-'+row['label']+'-source.json',dict(catalog_path=str(destination),run_id=row['run_id'],project_roots=roots,
                expected_fields=row['expected_fields'],restored_checks=checks))
        state.update(state='passed',admission_state='completed',historical_A_B_package_unchanged=True,
            built_in_epoch=1,study_id=study['id'],trial_id=trial['id'],graph_id=graph['id'],release_id=release['id'],
            cold_exact_objects=True,cold_whole_stream_capture_count=len(cold),protected_locked=locked,
            owner_admission=True,delegated_grant_used=False,charged=settled['charged'],native_checks=checks,calls=calls)
        save('receipt.json',state)
        print('PASS actual restored classifier '+run['id']+' '+str(output),flush=True)
    except BaseException as error:
        state.update(state='failed',failure_type=type(error).__name__,failure=str(error))
        if state['admission_state']=='may_have_been_sent':state['admission_state']='unknown'
        save('failure.json',state);raise
    finally:
        if server is not None and hasattr(server,'shutdown'):server.shutdown();server.server_close()
        if thread is not None:thread.join(timeout=5)
        if dataset is not None:
            if owner is not None:
                with owner.bound(dataset):dataset.access.logout()
            dataset.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('retention-report','disabled-selection-report','selection','output','runtime-python'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--disabled-selection-report-sha256',required=True)
    parser.add_argument('--retention-report-sha256',required=True)
    main(parser.parse_args())
