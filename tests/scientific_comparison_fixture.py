"""Real retained identity/readers with synthetic terminal bytes, no executed producer.

Tiny runtime inventory contains /usr/bin/true and dummy torch/numpy packages.
It is NOT runnable Python. Actual owner APIs capture material, grant and admit
finite Studies. Test setup explicitly authors terminal receipts and arrays;
publication, recovery, cold Runs._load, context/array validation and HTTP stay real.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import psycopg
from psycopg import sql

from app import Dataset
from auth_helpers import ExplicitOwnerFixture
from pipeline import digest
from qualify_publication_synthetic import project_fixture, PACKAGE
from runtime_snapshots import RuntimeSnapshots
from test_extension_field_evidence import npy
from workbench import encode, timestamp

SCOPE='Synthetic retained diagnostics; no producer execution, runtime, custody or scientific qualification'


class ScientificFixture:
    def __init__(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-m6-')
        self.root=Path(self.temporary.name);self.dataset=None;self.schema=None;self.dsn=None
        try:self.create()
        except BaseException:self.close();raise

    def create(self):
        # Capture the tiny structural inventory before any work is admitted.
        python=self.root/'source-python';site=self.root/'source-packages'
        (python/'bin').mkdir(parents=True);(python/'lib/python3.12/lib-dynload').mkdir(parents=True)
        shutil.copyfile('/usr/bin/true',python/'bin/python3.12')
        (python/'lib/python3.12/lib-dynload/fixture.txt').write_text('fixture only')
        names=[]
        for name in ('torch','numpy'):
            (site/name).mkdir(parents=True);(site/name/'__init__.py').write_text('fixture = True\n')
            info=site/(name+'-0.0.dist-info');info.mkdir()
            (info/'METADATA').write_text('Name: '+name+'\nVersion: 0.0\n');(info/'LICENSE').write_text('Test fixture')
            names.extend([name,info.name])
        config=dict(schema_version=1,python_root=str(python),python_version='3.12',site_packages=str(site),packages=names)
        # Inventory is pure; the project must exist before Dataset opens its root.
        from runtime_snapshots import inventory, canonical, sha
        runtime=sha(canonical(inventory(config)[0]))
        self.definition,self.manifest,self.recipe_sha=project_fixture(self.root/'project',runtime)
        self.dataset=Dataset(self.root/'catalog',project_roots={'synthetic':self.root/'project'})
        dataset=self.dataset;self.schema=dataset.db.schema;self.dsn=dataset.db.dsn
        self.owner=ExplicitOwnerFixture.bootstrap(dataset)
        with self.owner.bound(dataset),patch('recipe_process.launch',side_effect=AssertionError('Synthetic fixture must never launch compute')):
            snapshots=RuntimeSnapshots(dataset.db,dataset.access,dataset.path)
            self.runtime=snapshots.create(config,runtime,quiesced=True,reserve_bytes=0)
            project=dataset.projects.open_snapshot({'root':'synthetic','manifest_path':'project.json'})
            graph=dataset.pipelines.create_external({'name':SCOPE,'project_id':project['id'],'recipe_id':'synthetic',
                'expected_sha256':self.recipe_sha,'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':self.manifest['data'][0]['sha256']}}})
            policy=self.definition['model_evidence']
            draft=dataset.models.create({'name':SCOPE,'kind':'captured_source','task':{'kind':'task','catalog_id':dataset.db.dataset_id,
                'id':policy['task']['id'],'revision':policy['task']['revision'],'sha256':digest(policy['task']['definition'])},
                'specification':policy['model_specification'],'preprocessing_policy':policy['preprocessing_policy'],
                'output_policy':policy['output_policy'],'source_selector':{'project_id':project['id'],'recipe_id':'synthetic','expected_sha256':self.recipe_sha}})
            model=dataset.models.publish(draft['id'],{'revision':draft['revision']})
            selection={'format':'selection_policy_v1','metric_definition_sha256':digest(policy['metric_definitions'][0]),
                'checkpoint_rule':'last','replicate_reduce':'individual','required_capabilities':policy['profile']['required_capabilities'],
                'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
            study=dataset.studies.create({'name':SCOPE,'policy':selection,'limits':{'attempt_slots':3,
                'admitted_wall_seconds':1000,'retained_bytes':64*1024**2,'peak_staging_bytes':64*1024**2}})
            self.study_id=study['id'];self.trials=[];self.runs=[];self.refs=[]
            for index in range(3):
                state=dataset.studies.get(study['id'])['study']
                trial=dataset.studies.prepare_trial(study['id'],{'request_key':'m6-prepare-'+str(index),'revision':state['revision'],
                    'graph_id':graph['id'],'graph_revision':graph['revision'],'model':model['ref'],'replicate':index})
                self.trials.append(trial)
                lineage=dataset.studies.lineage;baseline=lineage.ref(self.trials[0]) if index else None
                lineage.record({'request_key':'m6-lineage-'+str(index),'revision':lineage.list()['revision'],'trial':lineage.ref(trial),
                    'intent':{'ancestry':'root','parent':None,'baseline':baseline,'cohort':'Synthetic M6 fixture',
                    'hypothesis':SCOPE,'change_summary':'Explicit synthetic predictions differ by 2.',
                    'target':{'metric_id':policy['metric_definitions'][0]['id'],'metric_definition_sha256':selection['metric_definition_sha256'],
                        'direction':'minimize','threshold':None,'acceptance':'Unknown: no owned scientific criterion supplied.'}}})
                state=dataset.studies.get(study['id'])['study']
                if state['state']!='open':
                    dataset.studies.continue_study(study['id'],{'request_key':'m6-open-'+str(index),'revision':state['revision'],'admission_epoch':state['admission_epoch']})
                grant=dataset.studies.approve(study['id'],{'trial_id':trial['id'],'expected_material_sha256':trial['material']['sha256'],
                    'consumer_actor_id':self.owner.identity['actor_id']})
                state=dataset.studies.get(study['id'])['study']
                with patch.object(dataset.runs,'_start'):
                    admitted=dataset.studies.admit(study['id'],{'request_key':'m6-admit-'+str(index),'revision':state['revision'],
                        'admission_epoch':state['admission_epoch'],'trial_id':trial['id'],'approval_id':grant['id']})
                run=dataset.runs._load(admitted['run']['id'])
                # Explicit test-only terminal setup. Production readers below
                # independently validate the unchanged admitted context/receipt.
                self.author_outputs(run,0 if index==0 else 2)
                import recipe_contract,recipe_process
                inventory=recipe_contract.verify_outputs(Path(run['spec']['output_dir']),run['outputs'],run['spec']['max_output_bytes'])
                helper={'pid':99999999,'start_ticks':'1','boot_id':'00000000-0000-0000-0000-000000000000'}
                run['custody_identity']={'attempt_id':run['id'],'request_sha256':run['request_sha256'],
                    'spec_sha256':hashlib.sha256(recipe_process.encoded(run['spec'])).hexdigest(),'helper':helper}
                receipt={'schema_version':1,**run['custody_identity'],'go_received':True,'spawn_closed':True,'drained':True,'echild':True,
                    'outcome':'completed','reason':'synthetic_fixture_only_no_execution','leader_returncode':0,
                    'streams':{key:{'bytes':0,'sha256':hashlib.sha256(b'').hexdigest()} for key in ('stdout','stderr')}}
                custody=dataset.runs._external_directory(run)/'custody';custody.mkdir(exist_ok=True)
                (custody/'receipt.json').write_bytes(encode(receipt).encode())
                for key in ('stdout','stderr'):(custody/(key+'.log')).write_bytes(b'')
                run.update(custody_phase='drained',finished_at=timestamp(),started_at=timestamp())
                if index<2:
                    run['artifacts'],run['custody_receipt_sha256']=dataset.runs._publish_external(run,receipt,inventory=inventory)
                    run['state']='completed';run['progress']['stage']='fixture_terminal'
                else:
                    run['publication_source']=dataset.runs._retain_external_publication_source(run,receipt,inventory)
                    run['state']='interrupted';run['progress']['stage']='fixture_publication_fault'
                    run['publication_fault']={'format':'external_publication_fault_v1','source_sha256':run['publication_source']['sha256'],
                        'code':'unavailable','message':'Explicit synthetic fixture publication fault; no execution','recorded_at':timestamp()}
                # Missing owner spans remain unknown; protocol checkpoint labels
                # in diagnostics are not presented as measurements of execution.
                run['_phase_timings']=[]
                dataset.runs._save(run)
                self.runs.append(dataset.runs._load(run['id']))
                if index==2:
                    recovered=dataset.runs.recover_publication({'run_id':run['id'],'source_ref':run['publication_source'],'request_key':'m6-recover-exact'})
                    self.refs.append(recovered['result_ref'])
            self.project_id=project['id'];self.model=model
            dataset.studies.reconcile(study['id'])
            self.before_counts=self.counts()

    def author_outputs(self,run,offset):
        directory=Path(run['spec']['output_dir']);directory.mkdir(exist_ok=True)
        spec=importlib.util.spec_from_file_location('m6_authored_writer',PACKAGE/'evidence_writer.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        writer=module.Evidence(directory,encode(run['extension_context']).encode())
        fixture=json.loads((PACKAGE/'fixture.json').read_bytes())
        member=next(row for row in fixture['cases'] if row['id']==fixture['probe_member_id'])
        (directory/'transform.npy').write_bytes(npy([0,1],[2]));writer.transform('transform.npy')
        (directory/'input-initial.npy').write_bytes(npy(member['initial'],[4,4,4]))
        (directory/'reference.npy').write_bytes(npy(member['target'],[4,4,4]))
        for point in (16,32,48,64):
            (directory/f'weights-{point}.npy').write_bytes(npy([0,0],[2]))
            (directory/f'prediction-{point}.npy').write_bytes(npy([value+offset for value in member['target']],[4,4,4]))
            writer.checkpoint(point,{'optimizer_update':point,'epoch':None,'fit_pass':None,'physical_time':None,'wall_elapsed_ms':point},
                f'weights-{point}.npy',{metric['id']:offset for metric in writer.policy['metric_definitions']})
        writer.finish();writer.write('diagnostics.json',{'scope':SCOPE,'clocks':'Fixture protocol labels, not executed optimizer passes or measured time',
            'numerical_acceptance':'not_evaluated'})

    def counts(self):
        return {table:self.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations')}

    def body(self,recovered=False):
        with self.owner.bound(self.dataset):
            first=self.dataset.runs.model_evidence(self.runs[0]['id'],{},contract_version=2)
            if recovered:
                second=self.dataset.runs.publication_model_evidence(self.refs[0],{})['evidence']
                operand={'kind':'publication_result','ref':self.refs[0]}
                artifacts=self.dataset.runs.publication_result(self.refs[0])['artifacts']
            else:
                second=self.dataset.runs.model_evidence(self.runs[1]['id'],{},contract_version=2)
                operand={'kind':'completed_run','catalog_id':self.dataset.db.dataset_id,'run_id':self.runs[1]['id']}
                artifacts=self.runs[1]['artifacts']
        selection={'metric_id':first['metric_definitions'][0]['id'],'mode':'paired'}
        for prefix,value,items in [('',first,self.runs[0]['artifacts']),('other_',second,artifacts)]:
            selection.update({prefix+'checkpoint_sha256':value['checkpoint_index']['entries'][0]['checkpoint']['sha256'],
                prefix+'evaluation_sha256':next(row['sha256'] for row in items if row['name']=='model-evidence.json'),
                prefix+'metric_definition_sha256':digest(value['metric_definitions'][0])})
        return {'operands':[{'kind':'completed_run','catalog_id':self.dataset.db.dataset_id,'run_id':self.runs[0]['id']},operand],
            'selection':selection,'point':{'field_id':first['fields'][0]['field_id'],'x':1,'y':2,'z':3}}

    def close(self):
        if self.dataset:self.dataset.close();self.dataset=None
        if self.schema:
            with psycopg.connect(self.dsn,autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
            self.schema=None
        self.temporary.cleanup()


def main():
    """Long-lived real HTTP fixture; control commands touch only owned fresh files."""
    from http.server import ThreadingHTTPServer
    import sys
    import threading
    from app import make_handler
    fixture=ScientificFixture();server=None;thread=None;moved=None
    receipt={'scope':SCOPE,'synthetic_terminal_setup':True,'producer_executed':False,
        'runtime_is_runnable_python':False,'canonical_load_and_context_substituted':False,
        'catalog_schema':fixture.schema,'checks':[]}
    try:
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(fixture.dataset))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        source_fixture=json.loads((PACKAGE/'fixture.json').read_bytes())
        source_case=next(row for row in source_fixture['cases'] if row['id']==source_fixture['probe_member_id'])
        expected={'baseline':source_case['target'][0],'candidate':source_case['target'][0]+2,'delta':2,
            'units':fixture.definition['model_evidence']['fields'][0]['contract']['output']['units']}
        print(json.dumps({'expected_point_zero':expected,'port':server.server_port,'data':str(fixture.dataset.path),
            'baseline':fixture.runs[0]['id'],'candidate':fixture.runs[1]['id'],'recovered':fixture.runs[2]['id'],
            'trial_id':fixture.trials[1]['id'],'ref':fixture.refs[0]}),flush=True)
        for line in sys.stdin:
            command=line.strip()
            if command=='done':break
            root=fixture.dataset.runs.path/fixture.runs[1]['id']
            if command=='remove':
                moved=root.with_name(root.name+'-held-by-fixture');root.rename(moved)
            elif command=='restore' and moved is not None:
                moved.rename(root);moved=None
            else:raise ValueError('Unknown fixture control command')
            print(json.dumps({'control':command}),flush=True)
        receipt.update(counts_before=fixture.before_counts,counts_after=fixture.counts(),
            original_recovered_state=fixture.dataset.runs._load(fixture.runs[2]['id'])['state'],result_ref=fixture.refs[0],
            model_ref=fixture.model['ref'],material_refs=[row['material'] for row in fixture.trials])
        if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(receipt,indent=2)+'\n')
    finally:
        if moved is not None:moved.rename(fixture.dataset.runs.path/fixture.runs[1]['id'])
        if server:server.shutdown();server.server_close()
        if thread:thread.join(5)
        fixture.close()


if __name__=='__main__':main()
