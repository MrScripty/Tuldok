"""Real catalog/capture/admission study boundaries, with no numerical claims."""
import copy
from contextlib import contextmanager
import json
import importlib.util
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from access import Access, AccessError
import agent_api
from app import Dataset, make_handler
from auth_helpers import execute_admitted
from backup_metadata import backup_catalog, restore_catalog, read_catalog, summaries
from experiments import Experiments
from metadata import Metadata, CommitOutcomeUnknown
from model_definitions import ModelDefinitions
from pipeline import digest
from runs import Runs
from test_model_definitions import CapturedModelCase
from test_external_runs import ExternalCase
from workbench import WorkbenchError


class StudyTests(CapturedModelCase):
    def setUp(self):
        super().setUp()
        self.dataset.models=self.models
        self.studies=Experiments(self.dataset)
        self.model=self.publish(self.create())
        self.policy={'format':'selection_policy_v1','metric_definition_sha256':digest({'kind':'neutral_fixture_only'}),
                     'checkpoint_rule':'explicit','replicate_reduce':'individual','required_capabilities':[],
                     'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
        with self.owner.bound(self.dataset):
            self.study=self.studies.create({'name':'Finite neutral source exercise',
                'limits':{'attempt_slots':3,'admitted_wall_seconds':1000,'retained_bytes':10**8,'peak_staging_bytes':10**8},
                'policy':self.policy})

    def prepare(self,key=None):
        with self.owner.bound(self.dataset):
            study=self.studies.get(self.study['id'])['study']
            body={'request_key':key or 'prepare-'+uuid.uuid4().hex,'revision':study['revision'],
                  'graph_id':self.graph['id'],'graph_revision':self.graph['revision'],'model':self.model['ref'],'replicate':0}
            return self.studies.prepare_trial(study['id'],body),body

    def open(self):
        with self.owner.bound(self.dataset):
            study=self.studies.get(self.study['id'])['study']
            return self.studies.continue_study(study['id'],{'request_key':'continue-'+uuid.uuid4().hex,
                            'revision':study['revision'],'admission_epoch':study['admission_epoch']})

    def approve(self,actor=None):
        with self.owner.bound(self.dataset):
            study=self.studies._study(self.study['id']);trial=self.studies.trial(study['trial_ids'][0])
            return self.studies.approve(study['id'],{'trial_id':trial['id'],
                'expected_material_sha256':trial['material']['sha256'],
                'consumer_actor_id':actor or self.agent['identity']['actor_id']})

    def admission_body(self,trial,approval=None):
        with self.owner.bound(self.dataset):study=self.studies.get(self.study['id'])['study']
        body={'request_key':'attempt-'+uuid.uuid4().hex,'revision':study['revision'],
              'admission_epoch':study['admission_epoch'],'trial_id':trial['id']}
        if approval:body['approval_id']=approval['id']
        return body

    def test_preparation_is_inert_atomic_and_reconciles_after_draft_edit(self):
        with patch('subprocess.run',side_effect=AssertionError('Inert preparation must not launch')):
            trial,body=self.prepare()
        with self.owner.bound(self.dataset):
            material=self.dataset.pipelines.recipe_material(trial['material'],verify=True)
            changed=copy.deepcopy(self.graph);changed['name']='Edited after retained preparation'
            self.dataset.pipelines.save(self.graph['id'],{'revision':1,'document':changed})
            self.assertEqual(self.studies.prepare_trial(self.study['id'],body),trial)
            cold=self.dataset.pipelines.capture_recipe_material(trial['material'],self.path/'cold-stage')
            self.assertEqual(cold['graph'],self.graph)
            self.assertEqual(cold['material_sha256'],self.preflight['material_sha256'])
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(material['material']['data'],[]) # Project data remain typed captures.
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_prepare_audit_failure_rolls_back_trial_membership_and_material_bytes(self):
        audit=self.dataset.access.audit
        def fail(action,*args,**kwargs):
            if action=='studies.prepare_trial':raise RuntimeError('Required attachment audit fails')
            return audit(action,*args,**kwargs)
        with patch.object(self.dataset.access,'audit',side_effect=fail),self.assertRaises(RuntimeError):self.prepare()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.get(self.study['id'])['study']['trial_ids'],[])
            for table in ('model_trials','workspace_recipe_materials'):
                self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(list(self.dataset.pipelines.material_path.iterdir()),[])

    def test_agent_exact_grant_admission_and_unchanged_receipt_do_not_double_charge_or_wake(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            result=self.studies.admit(self.study['id'],body);wake.assert_called_once();wake.reset_mock()
            self.assertEqual(self.studies.admit(self.study['id'],body),result);wake.assert_not_called()
            with self.assertRaises(WorkbenchError):self.studies.admit(self.study['id'],dict(body,revision=body['revision']+1))
        with self.owner.bound(self.dataset):
            state=self.studies.get(self.study['id'])
            self.assertEqual(len(state['reservations']),1);self.assertEqual(state['charged']['attempt_slots'],1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    def test_audit_failure_rolls_back_entire_attempt_and_grant(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        audit=self.dataset.access.audit
        def fail(action,*args,**kwargs):
            if action=='studies.admit':raise RuntimeError('Required admission audit fails')
            return audit(action,*args,**kwargs)
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with patch.object(self.dataset.access,'audit',side_effect=fail),self.assertRaises(RuntimeError):
                self.studies.admit(self.study['id'],body)
            wake.assert_not_called()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.get(self.study['id'])['reservations'],[])
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)
        self.assertEqual(list(self.dataset.runs.path.glob('.external-*')),[])

    def test_stop_closes_epoch_before_cancel_and_old_admission_preserves_grant(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.owner.bound(self.dataset):
            study=self.studies.get(self.study['id'])['study']
            stopped=self.studies.stop(study['id'],{'request_key':'stop-'+uuid.uuid4().hex,'revision':study['revision']})
            self.assertEqual(stopped['status']['study']['state'],'stopped')
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(WorkbenchError):
            self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)
            self.assertEqual(self.studies.get(self.study['id'])['reservations'],[])

    def test_owner_control_and_budget_inequality_preserve_current_rights(self):
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(AccessError):
            self.studies.create({'name':'No authority','limits':self.study['limits'],'policy':self.policy})
        trial,_=self.prepare()
        with self.owner.bound(self.dataset):
            study=self.studies.get(self.study['id'])['study'];limits=dict(study['limits'],admitted_wall_seconds=1)
            self.studies.save(study['id'],{'revision':study['revision'],'name':study['name'],'limits':limits,'policy':study['policy']})
        self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(WorkbenchError):self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_source_drift_after_trial_preparation_is_not_silently_replaced(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        (self.project_path/'recipe.py').write_bytes(self.source+b'\n# drift\n')
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(WorkbenchError):self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):self.assertEqual(self.studies.get(self.study['id'])['reservations'],[])

    def peer(self):
        db=Metadata(self.dataset.path,create=False);self.addCleanup(db.close)
        access=Access(db,self.dataset.path)
        runs=copy.copy(self.dataset.runs);runs.db=db;runs.lock=db.lock;runs.access=access
        pipelines=copy.copy(self.dataset.pipelines);pipelines.db=db;pipelines.lock=db.lock;pipelines.access=access
        dataset=SimpleNamespace(db=db,lock=db.lock,path=self.dataset.path,access=access,runs=runs,pipelines=pipelines,
                                projects=self.dataset.projects,releases=self.dataset.releases)
        pipelines.dataset=dataset;runs.dataset=dataset;runs.pipelines=pipelines
        dataset.models=ModelDefinitions(dataset)
        return Experiments(dataset)

    def test_second_connection_stop_wins_race_before_atomic_admission(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve());peer=self.peer()
        staged=threading.Event();release=threading.Event();results=[]
        capture=self.dataset.pipelines.capture_recipe_material
        def pause_capture(*args,**kwargs):
            value=capture(*args,**kwargs);staged.set()
            if not release.wait(10):raise RuntimeError('Test peer failed to close epoch')
            return value
        def admit():
            try:
                with self.dataset.access.bind(self.agent['token']):results.append(self.studies.admit(self.study['id'],body))
            except BaseException as error:results.append(error)
        with patch.object(self.dataset.pipelines,'capture_recipe_material',side_effect=pause_capture):
            worker=threading.Thread(target=admit);worker.start()
            try:
                self.assertTrue(staged.wait(10))
                with self.owner.bound(peer.dataset):
                    state=peer.get(self.study['id'])['study']
                    peer.stop(state['id'],{'request_key':'peer-stop-'+uuid.uuid4().hex,'revision':state['revision']})
            finally:release.set();worker.join(15)
        self.assertFalse(worker.is_alive());self.assertEqual(len(results),1);self.assertIsInstance(results[0],WorkbenchError)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_unacknowledged_real_commit_retains_study_run_and_exact_grant_without_wake(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        command=self.dataset.db.connection._exec_command
        def lose_commit_reply(statement,*args,**kwargs):
            result=yield from command(statement,*args,**kwargs)
            if statement==b'COMMIT':raise psycopg.OperationalError('Injected loss of committed admission reply')
            return result
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with patch.object(self.dataset.db.connection,'_exec_command',side_effect=lose_commit_reply):
                with self.assertRaises(CommitOutcomeUnknown):self.studies.admit(self.study['id'],body)
            wake.assert_not_called()
            result=self.studies.admit(self.study['id'],body);wake.assert_not_called()
        self.assertTrue((self.dataset.runs.path/('.external-'+result['run']['id'])).is_dir())
        peer=Metadata(self.dataset.path,create=False)
        try:
            self.assertEqual(peer.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0],1)
            self.assertEqual(peer.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],1)
            self.assertEqual(peer.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)
        finally:peer.close()

    def test_stop_after_admission_observes_closed_epoch_before_queued_child_cancel(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        peer=self.peer();cancel=peer.dataset.runs.cancel;observed=[]
        def guarded_cancel(run_id):
            observed.append(peer._study(self.study['id'])['open'])
            return cancel(run_id)
        with self.owner.bound(peer.dataset),patch.object(peer.dataset.runs,'cancel',side_effect=guarded_cancel):
            state=peer.get(self.study['id'])['study']
            result=peer.stop(state['id'],{'request_key':'peer-stop-'+uuid.uuid4().hex,'revision':state['revision']})
            self.assertEqual(result['status']['study']['state'],'stopped')
            self.assertEqual(peer.dataset.runs.get(admitted['run']['id'])['state'],'cancelled')
        self.assertEqual(observed,[False])

    def test_stopped_complete_backup_restores_material_trial_and_admission_without_replay(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        self.dataset.close()
        before=Metadata(self.dataset.path,create=False)
        try:expected=summaries(read_catalog(before));schema=before.schema
        finally:before.close()
        backup=self.path/'backup';backup_catalog(self.dataset.path,backup,quiesced=True)
        old=Metadata(self.dataset.path,create=False)
        try:
            from psycopg import sql
            old.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        finally:old.close()
        restored=self.path/'restored';restore_catalog(backup,restored)
        cold=Metadata(restored,create=False)
        try:self.assertEqual(summaries(read_catalog(cold)),expected)
        finally:cold.close()
        self.dataset=Dataset(restored,project_roots={'fixture':self.project_path})
        with self.owner.bound(self.dataset),patch.object(self.dataset.runs,'_start') as wake:
            material=self.dataset.pipelines.recipe_material(trial['material'],verify=True)
            self.assertEqual(material['ref'],trial['material'])
            self.assertEqual(self.dataset.studies.trial(trial['id']),trial)
            result=self.dataset.studies.reconcile(self.study['id'])
            self.assertEqual(result['charged']['attempt_slots'],1)
            self.assertEqual(self.dataset.runs.get(admitted['run']['id'])['state'],'cancelled')
            wake.assert_not_called()
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    def test_two_connection_admissions_compete_for_one_revision_without_second_grant_consumption(self):
        trial,_=self.prepare();self.open();peer=self.peer()
        left=self.admission_body(trial,self.approve());right=self.admission_body(trial,self.approve(self.other['identity']['actor_id']))
        ready=threading.Barrier(2);results=[]
        def capture(owner):
            original=owner.dataset.pipelines.capture_recipe_material
            def wait(*args,**kwargs):
                value=original(*args,**kwargs);ready.wait(timeout=10);return value
            return wait
        def admit(owner,token,body):
            try:
                with owner.access.bind(token):results.append(owner.admit(self.study['id'],body))
            except BaseException as error:results.append(error)
        with patch.object(self.dataset.pipelines,'capture_recipe_material',side_effect=capture(self.studies)),\
             patch.object(peer.dataset.pipelines,'capture_recipe_material',side_effect=capture(peer)),\
             patch.object(self.dataset.runs,'_start'),patch.object(peer.dataset.runs,'_start'):
            threads=[threading.Thread(target=admit,args=(self.studies,self.agent['token'],left)),
                     threading.Thread(target=admit,args=(peer,self.other['token'],right))]
            for worker in threads:worker.start()
            for worker in threads:worker.join(20)
        self.assertTrue(all(not worker.is_alive() for worker in threads))
        self.assertEqual(sum(isinstance(value,dict) for value in results),1)
        self.assertEqual(sum(isinstance(value,WorkbenchError) for value in results),1)
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.runs.list()),1)
            self.assertEqual(self.studies.get(self.study['id'])['charged']['attempt_slots'],1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    def server(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def close():server.shutdown();server.server_close();worker.join(5)
        self.addCleanup(close)
        return 'http://127.0.0.1:'+str(server.server_port)

    def test_public_selected_http_preserves_legacy_and_owner_control_and_admission_receipt(self):
        endpoint=self.server()
        def owner_call(name,arguments):
            method,path,body=agent_api.project_request(name,arguments,1)
            request=Request(endpoint+path,data=None if body is None else agent_api.encoded(body),method=method,
                headers={**self.owner.headers,'Content-Type':'application/json',
                         agent_api.CONTRACT_HEADER:agent_api.selected_header(name)})
            with urlopen(request,timeout=20) as response:
                return agent_api.validate_output(name,{'status':response.status,'result':json.loads(response.read())},1)
        agent=agent_api.AgentClient(endpoint,self.agent['token'],self.dataset.db.dataset_id)
        self.assertEqual(agent.call('models.get',{'model_id':self.model['ref']['id']})['result']['revision'],1)
        created=owner_call('models.create',self.model_body)
        self.assertEqual(created['status'],201)
        published=owner_call('models.publish',{'model_id':created['result']['id'],'revision':1})
        self.assertEqual(published['status'],200)
        self.assertEqual(agent.call('models.material',{'ref':published['result']['ref']})['result'],published['result'])
        first_page=agent.call('models.list',{'limit':1})['result']
        second_page=agent.call('models.list',{'limit':1,'cursor':first_page['next_cursor']})['result']
        self.assertEqual(len(first_page['models']),1);self.assertEqual(len(second_page['models']),1)
        self.assertNotEqual(first_page['models'][0]['id'],second_page['models'][0]['id'])
        self.assertIsNone(second_page['next_cursor'])
        def unqualified(kind):
            return {'kind':kind,'catalog_id':self.dataset.db.dataset_id,'id':'unqualified.fixture','revision':1,
                    'sha256':digest({'unqualified_draft_reference':kind})}
        runtime_sha=digest({'unqualified_draft_runtime':True})
        draft_fields={'name':'Inert draft; no qualified trainer','task':self.model_body['task'],
            'data':[{'kind':'release','catalog_id':self.dataset.db.dataset_id,'id':'a'*64,'sha256':'a'*64}],
            'model':self.model['ref'],'trainer':unqualified('trainer'),'parameters':{},'evaluation_profile':unqualified('profile'),
            'runtime':{'kind':'runtime','catalog_id':self.dataset.db.dataset_id,'id':runtime_sha,'sha256':runtime_sha},'layout':{}}
        draft=owner_call('recipes.create',draft_fields)['result']
        self.assertEqual(agent.call('recipes.get',{'recipe_id':draft['id']})['result'],draft)
        changed=dict(draft,name='Explicit unqualified draft edit')
        saved=owner_call('recipes.save',{'recipe_id':draft['id'],'revision':1,'document':changed})['result']
        self.assertEqual(saved['revision'],2)
        self.assertEqual(agent.call('recipes.list_drafts',{})['result']['recipes'],[saved])
        refused=agent.call('studies.create',{'name':'Owner control','limits':self.study['limits'],'policy':self.policy})
        self.assertEqual(refused['status'],403)
        body=json.dumps(self.model_body).encode()
        request=Request(endpoint+'/api/workspace/models',data=body,
                        headers={**self.owner.headers,'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as error:urlopen(request,timeout=10)
        self.assertEqual(error.exception.code,409)
        trial,prepare_body=self.prepare();self.open()
        approval_body={'study_id':self.study['id'],'trial_id':trial['id'],
            'expected_material_sha256':trial['material']['sha256'],'consumer_actor_id':self.agent['identity']['actor_id']}
        self.assertEqual(agent.call('studies.approve',approval_body)['status'],403)
        grant=owner_call('studies.approve',approval_body)
        self.assertEqual(grant['status'],201)
        admit_body=self.admission_body(trial,grant['result'])
        with patch.object(self.dataset.runs,'_start') as wake:
            result=agent.call('studies.admit',dict(admit_body,study_id=self.study['id']))
            self.assertEqual(result['status'],201);wake.assert_called_once();wake.reset_mock()
            self.assertEqual(agent.call('studies.admit',dict(admit_body,study_id=self.study['id'])),result)
            wake.assert_not_called()
        self.assertEqual(agent.call('recipes.material',{'ref':trial['material']})['result']['ref'],trial['material'])
        page=agent.call('studies.get',{'study_id':self.study['id'],'limit':1})['result']
        self.assertEqual(len(page['reservations']),1)
        with self.owner.bound(self.dataset):
            state=page['study']
            self.studies.save(state['id'],{'revision':state['revision'],'name':state['name'],'limits':state['limits'],'policy':state['policy']})
        stale=agent.call('studies.get',{'study_id':self.study['id'],'offset':1,'revision':state['revision']})
        self.assertEqual(stale['status'],409)
        self.assertEqual(agent_api.REGISTRY_DIGEST,'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')

    def test_actual_command_line_and_official_mcp_process_inspect_same_retained_model(self):
        trial,_=self.prepare()
        endpoint=self.server();config=self.path/'client.json';token=self.path/'credential'
        token.write_text(self.agent['token']);token.chmod(0o600)
        config.write_text(json.dumps({'endpoint':endpoint,'catalog_id':self.dataset.db.dataset_id,'token_file':str(token)}))
        config.chmod(0o600)
        inspected={}
        for operation,arguments in [('models.get',{'model_id':self.model['ref']['id']}),
                                    ('recipes.material',{'ref':trial['material']}),
                                    ('studies.get',{'study_id':self.study['id']})]:
            argument_file=self.path/(operation+'.json');argument_file.write_text(json.dumps(arguments))
            completed=subprocess.run([sys.executable,'project_cli.py','--config',str(config),'call','--operation',operation,
                                      '--arguments',str(argument_file)],capture_output=True,text=True,timeout=20)
            self.assertEqual(completed.returncode,0,completed.stderr)
            inspected[operation]=json.loads(completed.stdout)
        self.assertEqual(inspected['recipes.material']['ref'],trial['material'])
        self.assertEqual(inspected['studies.get']['study']['trial_ids'],[trial['id']])
        if importlib.util.find_spec('mcp') is None:
            self.skipTest('Actual CLI checks passed; optional MCP requires the separate hash-locked agent CI environment.')
        import anyio
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def inspect():
            params=StdioServerParameters(command=sys.executable,args=['mcp_stdio.py','--config',str(config)],
                                        cwd=str(Path(__file__).resolve().parents[1]))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();tools=await session.list_tools()
                    self.assertIn('models_get',[tool.name for tool in tools.tools])
                    result=await session.call_tool('models_get',{'model_id':self.model['ref']['id']})
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent,{'status':200,'result':inspected['models.get']})
        anyio.run(inspect)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_actual_admitted_neutral_process_completes_and_conservative_settlement_keeps_charges(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        execute_admitted(self.dataset,admitted['run']['id'])
        with self.owner.bound(self.dataset):
            run=self.dataset.runs.get(admitted['run']['id'])
            self.assertEqual(run['state'],'completed');self.assertEqual(run['custody_phase'],'drained')
            settled=self.studies.reconcile(self.study['id'])
            self.assertEqual(settled['reservations'][0]['state'],'settled')
            self.assertEqual(settled['charged'],admitted['reservation']['envelope'])
            self.assertTrue((self.dataset.runs.path/('.external-'+run['id'])).exists())

    def test_repeated_old_stop_receipt_never_cancels_a_new_epoch_child(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            first=self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            study=self.studies.get(self.study['id'])['study']
            stop={'request_key':'stop-'+uuid.uuid4().hex,'revision':study['revision']}
            stopped=self.studies.stop(study['id'],stop)
        self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            second=self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            repeated=self.studies.stop(self.study['id'],stop)
            self.assertEqual(repeated['receipt'],stopped['receipt'])
            self.assertEqual(repeated['receipt']['run_ids'],[first['run']['id']])
            self.assertTrue(repeated['status']['study']['open'])
            self.assertEqual(self.dataset.runs.get(second['run']['id'])['state'],'queued')

    def test_postcommit_response_read_failure_preserves_durable_custody_and_charge(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with patch.object(self.dataset.runs,'get',side_effect=RuntimeError('Injected postcommit response read failure')):
                with self.assertRaisesRegex(RuntimeError,'postcommit response'):self.studies.admit(self.study['id'],body)
            wake.assert_called_once();wake.reset_mock()
            result=self.studies.admit(self.study['id'],body);wake.assert_not_called()
        self.assertTrue((self.dataset.runs.path/('.external-'+result['run']['id'])).is_dir())
        peer=Metadata(self.dataset.path,create=False)
        try:
            self.assertEqual(peer.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],1)
            self.assertEqual(peer.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0],1)
            self.assertEqual(peer.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)
        finally:peer.close()

    def test_postcommit_wake_failure_preserves_durable_custody_and_charge(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']):
            with patch.object(self.dataset.runs,'_start',side_effect=RuntimeError('Injected committed wake failure')):
                with self.assertRaisesRegex(RuntimeError,'committed wake'):self.studies.admit(self.study['id'],body)
            with patch.object(self.dataset.runs,'_start') as wake:
                result=self.studies.admit(self.study['id'],body);wake.assert_not_called()
        self.assertTrue((self.dataset.runs.path/('.external-'+result['run']['id'])).is_dir())

    def test_large_valid_membership_remains_readable_and_continuation_receipt_reconciles(self):
        trial,_=self.prepare()
        with self.owner.bound(self.dataset),self.dataset.db.transaction():
            study=self.studies._study(self.study['id']);rows=[]
            for number in range(1,7501):
                item=dict(trial,id=f'{number:032x}',replicate=number)
                rows.append((item['id'],study['id'],trial['material']['sha256'],number,json.dumps(item)))
                study['trial_ids'].append(item['id'])
            with self.dataset.db.connection.cursor() as cursor:
                cursor.executemany('INSERT INTO model_trials VALUES(%s,%s,%s,%s,%s)',rows)
            study['membership_revision']+=1
            self.dataset.db.execute('INSERT INTO model_study_memberships VALUES(%s,%s,%s)',
                (study['id'],study['membership_revision'],json.dumps({'trial_ids':study['trial_ids']})))
            self.studies._write(study,'studies.prepare_trial',{'fixture':'seeded valid membership, no execution'})
        with self.owner.bound(self.dataset):
            state=self.studies.get(self.study['id'])['study']
            self.assertGreater(len(agent_api.encoded(state)),256*1024)
            self.assertEqual(len(state['trial_ids']),7501)
            body={'request_key':'continue-large-'+uuid.uuid4().hex,'revision':state['revision'],'admission_epoch':0}
            opened=self.studies.continue_study(state['id'],body)
            self.assertEqual(self.studies.continue_study(state['id'],body),opened)

    def test_distinct_studies_accept_same_scoped_key_with_independent_runs_and_grants(self):
        trial,prepare=self.prepare();self.open();left=self.admission_body(trial,self.approve())
        left['request_key']='attempt-0001'
        with self.owner.bound(self.dataset):
            other=self.studies.create({'name':'Independent study','limits':self.study['limits'],'policy':self.policy})
            other_trial=self.studies.prepare_trial(other['id'],dict(prepare,request_key='other-prepare-'+uuid.uuid4().hex,revision=1))
            other=self.studies.get(other['id'])['study']
            other=self.studies.continue_study(other['id'],{'request_key':'other-continue-'+uuid.uuid4().hex,
                'revision':other['revision'],'admission_epoch':other['admission_epoch']})
        right={'request_key':'attempt-0001','revision':other['revision'],'admission_epoch':other['admission_epoch'],
               'trial_id':other_trial['id'],'approval_id':self.approve()['id']}
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            first=self.studies.admit(self.study['id'],left);second=self.studies.admit(other['id'],right)
            self.assertNotEqual(first['run']['id'],second['run']['id'])
            self.assertNotEqual(first['run']['request_key'],second['run']['request_key'])
            self.assertEqual(first['reservation']['request_key'],second['reservation']['request_key'])
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],2)

    def test_recipe_orphan_reconciliation_rejects_child_rewrite_after_hash(self):
        with self.owner.bound(self.dataset):
            prepared=self.dataset.pipelines.prepare_external_material(self.graph['id'],1,self.model['ref'])
        target=self.dataset.pipelines.material_path/prepared['document']['ref']['sha256']
        prepared['staging'].rename(target)
        child=target/prepared['document']['material']['captures'][0]['name'];transaction=self.dataset.db.transaction
        @contextmanager
        def rewrite_after_hash(*args,**kwargs):
            before=target.stat();raw=child.read_bytes();child.chmod(0o600);child.write_bytes(b'x'*len(raw))
            after=target.stat();self.assertEqual((before.st_ino,before.st_mtime_ns,before.st_ctime_ns),
                                                (after.st_ino,after.st_mtime_ns,after.st_ctime_ns))
            with transaction(*args,**kwargs):yield
        with self.owner.bound(self.dataset):
            study=self.studies.get(self.study['id'])['study']
            body={'request_key':'orphan-'+uuid.uuid4().hex,'revision':study['revision'],'graph_id':self.graph['id'],
                  'graph_revision':1,'model':self.model['ref'],'replicate':0,'reconcile_capture':True}
            with patch.object(self.dataset.db,'transaction',rewrite_after_hash),self.assertRaises(WorkbenchError):
                self.studies.prepare_trial(study['id'],body)
            self.assertEqual(self.studies.get(study['id'])['study']['trial_ids'],[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_recipe_materials').fetchone()[0],0)
        self.assertTrue(target.exists())

    def test_owner_can_adopt_exact_orphan_recipe_only_by_explicit_reconciliation(self):
        with self.owner.bound(self.dataset):
            prepared=self.dataset.pipelines.prepare_external_material(self.graph['id'],1,self.model['ref'])
        prepared['staging'].rename(self.dataset.pipelines.material_path/prepared['document']['ref']['sha256'])
        with self.assertRaises(WorkbenchError):self.prepare()
        with self.owner.bound(self.dataset):
            trial=self.studies.prepare_trial(self.study['id'],{'request_key':'adopt-'+uuid.uuid4().hex,'revision':1,
                'graph_id':self.graph['id'],'graph_revision':1,'model':self.model['ref'],'replicate':0,'reconcile_capture':True})
            self.assertEqual(self.dataset.pipelines.recipe_material(trial['material'],verify=True),prepared['document'])

    def revocation_race(self,credential):
        trial,_=self.prepare();self.open();grant=self.approve();body=self.admission_body(trial,grant);peer=self.peer()
        staged=threading.Event();release=threading.Event();results=[]
        capture=self.dataset.pipelines.capture_recipe_material
        def pause(*args,**kwargs):
            value=capture(*args,**kwargs);staged.set()
            if not release.wait(10):raise RuntimeError('Revocation peer timed out')
            return value
        def admit():
            try:
                with self.dataset.access.bind(self.agent['token']):results.append(self.studies.admit(self.study['id'],body))
            except BaseException as error:results.append(error)
        with patch.object(self.dataset.pipelines,'capture_recipe_material',side_effect=pause),patch.object(self.dataset.runs,'_start') as wake:
            worker=threading.Thread(target=admit);worker.start()
            try:
                self.assertTrue(staged.wait(10))
                with self.owner.bound(peer.dataset):
                    if credential:peer.access.revoke(self.agent['identity']['credential_id'])
                    else:peer.access.revoke_execution(grant['id'])
            finally:release.set();worker.join(15)
            wake.assert_not_called()
        self.assertFalse(worker.is_alive());self.assertEqual(len(results),1);self.assertIsInstance(results[0],AccessError)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.get(self.study['id'])['reservations'],[])
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_second_connection_grant_revocation_wins_before_atomic_study_admission(self):
        self.revocation_race(False)

    def test_second_connection_credential_revocation_wins_before_atomic_study_admission(self):
        self.revocation_race(True)

    def test_exact_trial_retry_consumes_new_grant_and_cumulative_charge(self):
        trial,_=self.prepare();self.open();first_body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            first=self.studies.admit(self.study['id'],first_body)
        with self.owner.bound(self.dataset):
            self.dataset.runs.cancel(first['run']['id']);self.studies.reconcile(self.study['id'])
        retry=dict(self.admission_body(trial,self.approve()),parent_run_id=first['run']['id'])
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            next_run=self.studies.admit(self.study['id'],retry)
        with self.owner.bound(self.dataset):
            self.assertEqual(next_run['run']['parent_run_id'],first['run']['id'])
            self.assertEqual(next_run['run']['attempt'],2)
            self.assertEqual(next_run['reservation']['material_sha256'],first['reservation']['material_sha256'])
            self.assertEqual(self.studies.get(self.study['id'])['charged']['attempt_slots'],2)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],2)

    def test_changed_runtime_policy_rejects_retry_without_new_charge_or_grant_consumption(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            first=self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            self.dataset.runs.cancel(first['run']['id']);self.studies.reconcile(self.study['id'])
        retry=dict(self.admission_body(trial,self.approve()),parent_run_id=first['run']['id'])
        self.dataset.external_runtime_profile={'executable':'/usr/bin/python3','trusted_install_owner_uid':os.stat('/usr').st_uid+1}
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(WorkbenchError):self.studies.admit(self.study['id'],retry)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.get(self.study['id'])['charged']['attempt_slots'],1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    def test_unknown_child_closes_epoch_and_preserves_full_obligation(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset),self.dataset.db.transaction():
            run=self.dataset.runs._load(admitted['run']['id'])
            self.dataset.runs._event(run,'unknown','Injected durable unknown custody for composition refusal test.')
            self.dataset.runs._save(run)
        with self.owner.bound(self.dataset):
            result=self.studies.reconcile(self.study['id']);study=result['study']
            self.assertFalse(study['open']);self.assertEqual(study['state'],'unknown')
            self.assertEqual(result['charged'],admitted['reservation']['envelope'])
            with self.assertRaises(WorkbenchError):self.studies.continue_study(study['id'],{
                'request_key':'unknown-continue-'+uuid.uuid4().hex,'revision':study['revision'],'admission_epoch':study['admission_epoch']})

    def test_reopen_after_ungraceful_connection_loss_never_replays_queued_study_child(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        # No worker was started: drop the owning connection without graceful
        # Runs.close cancellation, reproducing a queued admission crash boundary.
        self.dataset.projects.close();self.dataset.db.close()
        with patch.object(Runs,'_start') as wake:
            self.dataset=Dataset(self.path/'catalog',project_roots={'fixture':self.project_path})
            self.studies=self.dataset.studies;self.models=self.dataset.models
            with self.owner.bound(self.dataset):
                self.assertEqual(self.dataset.runs.get(admitted['run']['id'])['state'],'interrupted')
                self.assertEqual(self.studies.reconcile(self.study['id'])['charged']['attempt_slots'],1)
            wake.assert_not_called()

    def test_cold_receipt_and_accounting_refuse_corrupt_row_or_lowered_charge(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        original=admitted['reservation']
        for field in ('run_id','envelope','settled'):
            changed=copy.deepcopy(original)
            if field=='run_id':changed['run_id']='a'*32
            elif field=='envelope':changed['envelope']['retained_bytes']=1
            else:
                changed['state']='settled';changed['settled']=dict(changed['envelope'],attempt_slots=0)
            with self.owner.bound(self.dataset),self.dataset.db.transaction():
                self.dataset.db.execute('UPDATE model_attempt_reservations SET document=%s WHERE id=%s',
                                        (json.dumps(changed),original['id']))
            try:
                with self.dataset.access.bind(self.agent['token']),self.assertRaises(WorkbenchError):
                    self.studies.admit(self.study['id'],body)
                with self.owner.bound(self.dataset),self.assertRaises(WorkbenchError):self.studies.get(self.study['id'])
            finally:
                with self.owner.bound(self.dataset),self.dataset.db.transaction():
                    self.dataset.db.execute('UPDATE model_attempt_reservations SET document=%s WHERE id=%s',
                                            (json.dumps(original),original['id']))

    def test_legacy_preflight_grant_does_not_authorize_composed_study_material(self):
        trial,_=self.prepare();self.open()
        legacy=ExternalCase.approve(self);body=self.admission_body(trial,legacy)
        self.assertNotEqual(legacy['material_sha256'],trial['material']['sha256'])
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(AccessError):self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.get(self.study['id'])['reservations'],[])
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_model_policy_substitution_cannot_reuse_sibling_composition_grant(self):
        first,_=self.prepare();first_grant=self.approve()
        changed=copy.deepcopy(self.model_body);changed['preprocessing_policy']['inert_policy_revision']='changed'
        with self.owner.bound(self.dataset):
            draft=self.models.create(changed);model=self.models.publish(draft['id'],{'revision':1})
            study=self.studies.get(self.study['id'])['study']
            sibling=self.studies.prepare_trial(study['id'],{'request_key':'sibling-'+uuid.uuid4().hex,
                'revision':study['revision'],'graph_id':self.graph['id'],'graph_revision':1,'model':model['ref'],'replicate':0})
        self.open();body=self.admission_body(sibling,first_grant)
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(AccessError):self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            grant=self.studies.approve(self.study['id'],{'trial_id':sibling['id'],'expected_material_sha256':sibling['material']['sha256'],
                'consumer_actor_id':self.agent['identity']['actor_id']})
            self.assertNotEqual(first_grant['material_sha256'],grant['material_sha256'])
        body['approval_id']=grant['id']
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            result=self.studies.admit(self.study['id'],body)
            self.assertEqual(result['run']['approval_material_sha256'],sibling['material']['sha256'])
            self.assertEqual(self.studies.admit(self.study['id'],body),result)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.get(self.study['id'])['charged']['attempt_slots'],1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    def test_cold_run_refuses_different_self_consistent_preflight_under_composed_approval(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset),self.dataset.db.transaction():
            run=self.dataset.runs._load(admitted['run']['id'])
            original=self.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(run['id'],)).fetchone()[0]
            run['material']['runtime']['trusted_install_owner_uid']+=1
            run['material_sha256']=digest(run['material']);run['spec']['trusted_install_owner_uid']+=1
            import recipe_contract
            recipe_contract.validate_spec(run['material'],run['spec'],run['spec']['cwd'])
            self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(json.dumps(run),run['id']))
        try:
            with self.owner.bound(self.dataset),self.assertRaises(WorkbenchError):self.dataset.runs.get(run['id'])
        finally:
            with self.owner.bound(self.dataset),self.dataset.db.transaction():
                self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(original,run['id']))

    def test_cold_study_run_cannot_drop_composition_marker_to_skip_approval_binding(self):
        trial,_=self.prepare();self.open();body=self.admission_body(trial,self.approve())
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],body)
        with self.owner.bound(self.dataset):
            retained=self.dataset.runs._load(admitted['run']['id'])
            original=self.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(retained['id'],)).fetchone()[0]
        for replace_preflight in (False,True):
            with self.subTest(replace_preflight=replace_preflight):
                run=copy.deepcopy(retained);run.pop('approval_material_sha256')
                if replace_preflight:
                    run['material']['runtime']['trusted_install_owner_uid']+=1
                    run['material_sha256']=digest(run['material']);run['spec']['trusted_install_owner_uid']+=1
                    import recipe_contract
                    recipe_contract.validate_spec(run['material'],run['spec'],run['spec']['cwd'])
                with self.owner.bound(self.dataset),self.dataset.db.transaction():
                    self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(json.dumps(run),run['id']))
                try:
                    with self.owner.bound(self.dataset),self.assertRaises(WorkbenchError):
                        self.dataset.runs.get(run['id'])
                finally:
                    with self.owner.bound(self.dataset),self.dataset.db.transaction():
                        self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(original,run['id']))

    def test_cold_study_run_requires_its_exact_consumed_actor_grant(self):
        trial,_=self.prepare();self.open();grant=self.approve()
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.studies.admit(self.study['id'],self.admission_body(trial,grant))
        with self.owner.bound(self.dataset):self.dataset.runs.cancel(admitted['run']['id'])
        sibling_grant=self.approve()
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            self.studies.admit(self.study['id'],self.admission_body(trial,sibling_grant))
        replacements=(sibling_grant,self.approve(),self.approve(self.other['identity']['actor_id']))
        with self.owner.bound(self.dataset):
            retained=self.dataset.runs._load(admitted['run']['id'])
            original=self.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(retained['id'],)).fetchone()[0]
        for replacement in replacements:
            with self.subTest(approval_id=replacement['id']):
                run=copy.deepcopy(retained);run['approval_id']=replacement['id']
                with self.owner.bound(self.dataset),self.dataset.db.transaction():
                    self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(json.dumps(run),run['id']))
                try:
                    with self.owner.bound(self.dataset),self.assertRaises(WorkbenchError):
                        self.dataset.runs.get(run['id'])
                finally:
                    with self.owner.bound(self.dataset),self.dataset.db.transaction():
                        self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(original,run['id']))
