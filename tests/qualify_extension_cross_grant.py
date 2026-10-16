"""Opt-in public A-grant/B-material refusal on an already qualified restore only.

No original catalog/root writes, source Run, SDK admission/retry, or private
Access admission call. Root configuration is the reviewed current_roots document
in the E4 selection. Ordinary owner calls prepare two new finite restored-only
Studies/Trials from existing Models/graphs, because a restored CPU descriptor
has a new root and therefore may produce new composition identities. A fresh,
unspent exact A approval is issued to a fresh agent; its one public B admission
request MUST refuse with the material mismatch and preserve all pre-request
rows/counters/charges. Historical spent A grants are not used as mismatch proof.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import time
from unittest.mock import patch
import uuid

from psycopg.conninfo import make_conninfo

from agent_api import AgentClient
from app import Dataset
from auth_helpers import ExplicitOwnerFixture
import backup_metadata as transfer
from qualify_extension_ab_retention import load_selection,reviewed,selected_reads
from qualify_extension_retention import require,serve,stop
from qualify_scientific_restore import compare,read_private,save_private,snapshot


TABLES=('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations',
        'model_studies','model_trials','workspace_recipe_materials')


def control_state(dataset,study_ids):
    with dataset.lock,dataset.db.transaction():
        tables=transfer.read_catalog(dataset.db)
        return {'counts':{name:dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in TABLES},
            'tables':{name:summary for name,summary in transfer.summaries(tables).items() if name!='access_audit'},
            'studies':{identity:dataset.studies.get(identity) for identity in study_ids},
            'run_directories':sorted(path.name for path in dataset.runs.path.iterdir())}


def check_refusal(response,before,after,grant,actor,material):
    require(grant['consumer_actor_id']==actor and grant['material_sha256']!=material and grant['revoked_at'] is None and
            grant['expires_at']>time.time(),'Expected current unspent A approval for the same consuming actor and a different material.')
    require(response['status']==403 and response['result'].get('code')=='forbidden' and
            response['result'].get('error')=='Execution approval does not match this actor and reviewed material.',
            'Public B admission did not reach the exact reviewed-material mismatch.')
    require(before==after,'Refused public admission changed rows/counters/charges or retained Run directories.')


def run_control(destination,connection,selected,output):
    require('current_roots' in selected,'The public negative requires an explicit reviewed original root map.')
    dataset=server=thread=None
    report={'format':'extension_ab_public_cross_material_refusal_v1','state':'in_progress',
            'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'roots_reference':selected['references'].get('current_roots'),
            'target':'restored_disposable_copy_only','historical_materials':{label:selected[label]['material']['ref'] for label in ('a','b')},
            'claim':'Fresh unspent exact A composition approval cannot authorize B; historical spent A grant is not the mismatch witness.'}
    with (patch('subprocess.Popen',side_effect=AssertionError('Cross-material control must not execute')),
            patch('runs.Runs._start',side_effect=AssertionError('Cross-material control must not schedule'))):
        try:
            dataset=Dataset(destination,dsn=connection,project_roots=selected['current_roots'])
            owner=ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                before_setup=control_state(dataset,[selected[label]['selection']['study_id'] for label in ('a','b')])
                studies={};trials={};materials={}
                for label in ('a','b'):
                    chosen=selected[label];selector=chosen['model']['material']['source_selector']
                    inspected=dataset.pipelines.inspect_external_recipe(selector['project_id'],selector['recipe_id'],selector['expected_sha256'],contract_version=2)
                    studies[label]=dataset.studies.create({'name':'Restored-only '+label.upper()+' exact-grant negative',
                        'policy':inspected['selection_policy'],'limits':{'attempt_slots':1,'admitted_wall_seconds':2400,
                            'retained_bytes':512*1024**2,'peak_staging_bytes':1024**3}})
                    expected=chosen['selection']['expected']
                    trials[label]=dataset.studies.prepare_trial(studies[label]['id'],{'request_key':'control-prepare-'+uuid.uuid4().hex,
                        'revision':studies[label]['revision'],'graph_id':expected['graph_id'],'graph_revision':expected['graph_revision'],
                        'model':chosen['model']['ref'],'replicate':0})
                    materials[label]=dataset.pipelines.recipe_material(trials[label]['material'],verify=True)
                require(materials['a']['ref']['sha256']!=materials['b']['ref']['sha256'] and
                        materials['a']['material']['model']==selected['a']['model']['ref'] and
                        materials['b']['material']['model']==selected['b']['model']['ref'],
                        'Control must retain distinct exact A/B source Models and compositions.')
                agent=dataset.access.issue({'label':'Restored-only exact A grant negative consumer','scopes':['inspect','execute'],'ttl_seconds':600})
                approval=dataset.studies.approve(studies['a']['id'],{'trial_id':trials['a']['id'],
                    'expected_material_sha256':materials['a']['ref']['sha256'],'consumer_actor_id':agent['identity']['actor_id'],'ttl_seconds':600})
                state=dataset.studies.get(studies['b']['id'])['study']
                dataset.studies.continue_study(studies['b']['id'],{'request_key':'control-open-'+uuid.uuid4().hex,
                    'revision':state['revision'],'admission_epoch':state['admission_epoch']})
                state=dataset.studies.get(studies['b']['id'])['study']
                ids=[selected[label]['selection']['study_id'] for label in ('a','b')]+[value['id'] for value in studies.values()]
                before=control_state(dataset,ids)
                require(all(before['studies'][identity]==state for identity,state in before_setup['studies'].items()),
                        'Control preparation changed an original Study or its charges.')
                require(dataset.db.execute('SELECT count(*) FROM access_execution_consumptions WHERE grant_id=%s',(approval['id'],)).fetchone()[0]==0,
                        'Control A approval must be unspent before the request.')
            server,thread,endpoint=serve(dataset);client=AgentClient(endpoint,agent['token'],dataset.db.dataset_id)
            body={'study_id':studies['b']['id'],'request_key':'control-wrong-material-'+uuid.uuid4().hex,
                  'revision':state['revision'],'admission_epoch':state['admission_epoch'],'trial_id':trials['b']['id'],'approval_id':approval['id']}
            report.update(request=body,admission_request_state='may_have_been_sent')
            response=client.call('studies.admit',body)
            with owner.bound(dataset):
                after=control_state(dataset,ids)
                check_refusal(response,before,after,approval,agent['identity']['actor_id'],materials['b']['ref']['sha256'])
                require(dataset.db.execute('SELECT count(*) FROM access_execution_consumptions WHERE grant_id=%s',(approval['id'],)).fetchone()[0]==0,
                        'Refused A approval was consumed.')
                report.update(state='refused_without_execution',admission_request_state='refused_403',request=body,response=response,before=before,after=after,
                    before_setup=before_setup,control_materials={label:value['ref'] for label,value in materials.items()},
                    approval=approval,approval_unconsumed=True,actor_matches=True,original_study_charges_unchanged=True,
                    root_policy='Only reviewed original roots were read; restored runtime root may change new composition SHA.')
                dataset.access.revoke_execution(approval['id']);dataset.access.revoke(agent['identity']['credential_id'])
                state=dataset.studies.get(studies['b']['id'])['study']
                dataset.studies.stop(studies['b']['id'],{'request_key':'control-close-'+uuid.uuid4().hex,'revision':state['revision']})
            stop(server,thread);server=thread=None;dataset.close()
            dataset=Dataset(destination,dsn=connection,project_roots={})
            with owner.bound(dataset):
                selected_reads(dataset,selected)
            report['roots_removed_and_historical_reads_verified']=True
            save_private(output/'refusal.json',report)
            return report
        except BaseException as error:
            report.update(state='inspect_restored_state_before_retry',error_type=type(error).__name__,failure=str(error))
            save_private(output/'failure.json',report)
            raise
        finally:
            if server is not None:stop(server,thread)
            if dataset is not None:dataset.close()


def main(args):
    retained=reviewed({'path':str(args.retention_report.resolve()),'sha256':args.retention_report_sha256})
    require(retained.get('format')=='extension_ab_retention_qualification_v1' and retained.get('state') in ('passed','rootless_retention_verified_disable_pending') and
            retained.get('source_unchanged') is True and re.fullmatch('tuldok_ab_retention_[a-f0-9]{32}',retained.get('restored_database','')),
            'Select a reviewed successful E4 restore report, never an original catalog.')
    selected=load_selection(args.selection)
    require(transfer.file_hash(args.selection)==retained['selection_sha256'],'Control selection differs from qualified restore.')
    destination=Path(retained['output'])/'restored-catalog';source=Path(retained['source']);output=args.output.resolve()
    transfer.separate_paths(source,destination);transfer.separate_paths(source,output);transfer.separate_paths(destination,output)
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    connection=os.environ['TULDOK_DATABASE_URL'];baseline=read_private(Path(retained['output'])/'baseline.private.json')
    compare(snapshot(source,connection),baseline)
    result=run_control(destination,make_conninfo(connection,dbname=retained['restored_database']),selected,output)
    compare(snapshot(source,connection),baseline)
    require(load_selection(args.selection)==selected,'Reviewed selection changed during public control.')
    save_private(output/'source-unchanged.json',{'state':'passed','source_unchanged':True,'refusal':result['state'],
        'retention_report_sha256':args.retention_report_sha256,'selection_sha256':transfer.file_hash(args.selection)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retention-report',type=Path,required=True)
    parser.add_argument('--retention-report-sha256',required=True)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
