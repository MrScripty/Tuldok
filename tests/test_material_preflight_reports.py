"""Exact retained-material inspection and transport; no scientific acceptance."""
import copy
from contextlib import redirect_stderr
import io
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import agent_api as api
import pipeline
import project_cli
import test_run_preflight_report as graph_reports
import test_run_preflight_refusals as graph_refusals
from workbench import WorkbenchError


class MaterialPreflightReportTests(unittest.TestCase):
    def setUp(self):
        fixture=graph_reports.PreflightReportTests('runTest');fixture.setUp()
        self.graph,self.prepared=fixture.graph,fixture.prepared
        catalog=self.prepared['material']['catalog_id']
        def ref(kind,name,revision=True):
            result={'kind':kind,'catalog_id':catalog,'id':name,'sha256':'c'*64}
            if revision:result['revision']=1
            return result
        blob={'name':'recipe.json','sha256':'d'*64,'bytes':10,'media_type':'application/json'}
        material={'format':'recipe_material_v1','catalog_id':catalog,'recipe_id':self.graph['id'],
            'recipe_revision':self.graph['revision'],'recipe_document':blob,
            'executable_sha256':self.prepared['material_sha256'],'model':ref('model','e'*32),
            'data':[],'trainer':ref('trainer','external_recipe_v1'),
            'evaluation_profile':ref('profile','opaque_external_outputs_v1'),
            'resolved_profile':dict(blob,name='profile.json'),
            'runtime':ref('runtime',pipeline.digest(self.prepared['material']['runtime']),False),
            'captures':[dict(blob,name='capture-0000.bin')],
            'resource_envelope':{key:1 for key in ('attempt_slots','admitted_wall_seconds','retained_bytes','peak_staging_bytes')}}
        material['runtime']['sha256']=material['runtime']['id']
        sha=pipeline.digest(material)
        self.value={'ref':{'kind':'recipe_material','catalog_id':catalog,'id':sha,'sha256':sha},'material':material}

    def success(self):
        return {'status':200,'result':dict(copy.deepcopy(self.value),preflight_report=
            pipeline._recipe_material_preflight_report(self.value,self.graph,self.prepared))}

    def refusal(self,code='stale',status=409):
        error=WorkbenchError('Private detail',code,status)
        report=pipeline._external_preflight_refusal(self.value['ref']['catalog_id'],None,None,error,
                                                  material_ref=self.value['ref'])
        return {'status':status,'result':{'error':str(error),'code':code,'preflight_report':report}}

    def test_distinct_outer_inner_and_graph_identities_and_deferred_execution(self):
        value=self.success();api.validate_output('recipes.preflight_material',value)
        report=value['result']['preflight_report']
        self.assertEqual(report['material_sha256'],self.value['ref']['sha256'])
        self.assertEqual(report['execution_material_sha256'],self.prepared['material_sha256'])
        self.assertEqual(report['execution_sha256'],self.prepared['execution_sha256'])
        self.assertEqual(report['model_ref'],self.value['material']['model'])
        self.assertEqual(report['admission'],'not_reserved')
        original=pipeline._external_preflight_report(self.graph,self.prepared,version=2)
        self.assertEqual(report['checks'],original['checks'])
        self.assertEqual(len(report['checks']),10)
        self.assertLess(len(json.dumps(report).encode()),8192)
        self.assertFalse(api.operation('recipes.preflight_material')['side_effects'])
        self.assertEqual(api.operation('recipes.preflight_material')['scopes'],['inspect'])

    def test_refusal_is_bounded_request_provenance_with_unknown_identities(self):
        for code in ('invalid','unsupported','unavailable','stale','conflict','too_large','storage'):
            value=self.refusal(code);api.validate_output('recipes.preflight_material',value)
            report=value['result']['preflight_report']
            self.assertEqual(report['recipe_material_ref'],self.value['ref'])
            for key in ('graph_id','graph_revision','model_ref','execution_material_sha256',
                        'execution_sha256','material_sha256'):self.assertIsNone(report[key])
            self.assertFalse(any(row['state']=='checked' for row in report['checks']))
            self.assertNotIn('Private detail',json.dumps(report))
        for status in (401,403):
            api.validate_output('recipes.preflight_material',{'status':status,'result':{'error':'Denied','code':'forbidden'}})

    def test_consumer_rejects_forged_links_proofs_owners_states_and_bounds(self):
        mutations=(lambda r:r.update(material_sha256='a'*64),
            lambda r:r.update(execution_material_sha256='a'*64),lambda r:r.update(execution_sha256=None),
            lambda r:r.update(graph_revision=3),lambda r:r.update(model_ref=None),
            lambda r:r['recipe_material_ref'].update(id='a'*64),lambda r:r['checks'][0].update(owner='runs'),
            lambda r:r['checks'][-1].update(state='checked'),lambda r:r['checks'].pop(),
            lambda r:r['checks'][0].update(detail='x'*241))
        for mutate in mutations:
            value=self.success();report=value['result']['preflight_report'];mutate(report)
            graph_refusals.PreflightRefusalTests.rehash(report)
            with self.assertRaises(api.AgentAPIError):api.validate_output('recipes.preflight_material',value)
        for key,value in (('graph_id','a'*32),('graph_revision',1),('model_ref',self.value['material']['model']),
                          ('execution_material_sha256','a'*64)):
            envelope=self.refusal();report=envelope['result']['preflight_report'];report[key]=value
            graph_refusals.PreflightRefusalTests.rehash(report)
            with self.assertRaises(api.AgentAPIError):api.validate_output('recipes.preflight_material',envelope)

    def test_consumer_refuses_rehashed_foreign_or_builtin_compositions_and_runtime_provenance(self):
        for key in ('model','trainer','evaluation_profile','runtime'):
            value=self.success();result=value['result'];material=result['material'];report=result['preflight_report']
            material[key]['catalog_id']='a'*32
            sha=pipeline.digest(material);result['ref'].update(id=sha,sha256=sha)
            report.update(recipe_material_ref=copy.deepcopy(result['ref']),material_sha256=sha,
                          model_ref=copy.deepcopy(material['model']))
            graph_refusals.PreflightRefusalTests.rehash(report)
            with self.assertRaises(api.AgentAPIError):api.validate_output('recipes.preflight_material',value)
        for change in (lambda m:m['trainer'].update(id=pipeline.BUILTIN_TRAINERS[0]),
                       lambda m:m['runtime'].update(id='a'*64)):
            value=self.success();result=value['result'];report=result['preflight_report'];change(result['material'])
            sha=pipeline.digest(result['material']);result['ref'].update(id=sha,sha256=sha)
            report.update(recipe_material_ref=copy.deepcopy(result['ref']),material_sha256=sha)
            graph_refusals.PreflightRefusalTests.rehash(report)
            with self.assertRaises(api.AgentAPIError):api.validate_output('recipes.preflight_material',value)
        for code in ('runtime_inventory','runtime_ready_go','authority_admission','custody_completion','output_publication'):
            value=self.success();report=value['result']['preflight_report']
            next(row for row in report['checks'] if row['code']==code)['evidence_sha256']='a'*64
            graph_refusals.PreflightRefusalTests.rehash(report)
            with self.assertRaises(api.AgentAPIError):api.validate_output('recipes.preflight_material',value)

    def test_builtin_refuses_before_probe_and_early_foreign_ref_stays_bare(self):
        value=copy.deepcopy(self.value);value['material']['trainer']['id']=pipeline.BUILTIN_TRAINERS[0]
        owner=SimpleNamespace(access=Mock(),db=SimpleNamespace(dataset_id=self.value['ref']['catalog_id']),
            recipe_material=Mock(return_value=value),_prepare_recipe_material=Mock())
        with patch('subprocess.Popen',side_effect=AssertionError('No native probe')):
            with self.assertRaises(WorkbenchError) as caught:
                pipeline.Pipelines.preflight_recipe_material(owner,self.value['ref'],report=True)
        self.assertEqual(caught.exception.code,'unsupported');owner._prepare_recipe_material.assert_not_called()
        api.validate_output('recipes.preflight_material',{'status':caught.exception.status,
            'result':{'error':str(caught.exception),'code':caught.exception.code,
                      'preflight_report':caught.exception.preflight_report}})
        owner.recipe_material.reset_mock()
        with self.assertRaises(WorkbenchError) as caught:
            pipeline.Pipelines.preflight_recipe_material(owner,dict(self.value['ref'],catalog_id='a'*32),report=True)
        self.assertIsNone(getattr(caught.exception,'preflight_report',None));owner.recipe_material.assert_not_called()

    def test_default_internal_path_and_private_verified_ref_fence_are_preserved(self):
        owner=SimpleNamespace(access=Mock(),_prepare_recipe_material=Mock(return_value={'kind':'builtin'}))
        self.assertEqual(pipeline.Pipelines.preflight_recipe_material(owner,self.value['ref']),{'kind':'builtin'})
        owner._prepare_recipe_material.assert_called_once_with(self.value['ref'])
        wrong=copy.deepcopy(self.value);wrong['ref']['sha256']='a'*64
        with self.assertRaises(WorkbenchError):
            pipeline.Pipelines._prepare_recipe_material(owner,self.value['ref'],_verified=wrong)

    def test_client_correlates_ref_catalog_and_real_error_transport_with_no_retry(self):
        client=api.AgentClient('http://127.0.0.1:12345','k'*32,self.value['ref']['catalog_id'])
        client._ready=True;client._selected={'recipes.preflight_material':1}
        for value in (self.success(),self.refusal()):
            client._request=Mock(return_value=value)
            self.assertEqual(client.call('recipes.preflight_material',{'ref':self.value['ref']}),value)
            client._request.reset_mock()
            with self.assertRaises(api.AgentAPIError):
                client.call('recipes.preflight_material',{'ref':dict(self.value['ref'],sha256='a'*64)})
            self.assertEqual(client._request.call_count,1)
        value=self.refusal();value['result'].update(error='k'*32,unrelated='discard')
        fixture=graph_refusals.PreflightRefusalTests('runTest')
        with fixture.transport(value) as base:
            client=api.AgentClient(base,'k'*32,self.value['ref']['catalog_id'])
            client._ready=True;client._selected={'recipes.preflight_material':1}
            result=client.call('recipes.preflight_material',{'ref':self.value['ref']})
            self.assertEqual(result['result']['error'],'[redacted]');self.assertNotIn('unrelated',result['result'])
            stderr=io.StringIO()
            with tempfile.NamedTemporaryFile(mode='w+',suffix='.json') as arguments:
                json.dump({'ref':self.value['ref']},arguments);arguments.flush()
                with patch.object(api.AgentClient,'from_config',return_value=client),redirect_stderr(stderr):
                    code=project_cli.main(['--config','/unused','call','--operation','recipes.preflight_material',
                                           '--arguments',arguments.name])
            self.assertEqual(code,1);self.assertEqual(json.loads(stderr.getvalue())['preflight_report'],
                                                   value['result']['preflight_report'])
            value['result']['preflight_report']=None
            with self.assertRaises(api.AgentAPIError):client.call('recipes.preflight_material',{'ref':self.value['ref']})


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class MaterialPreflightHTTPTests(unittest.TestCase):
    def fixture(self):
        import test_experiments as studies
        case=studies.StudyTests('runTest');self.addCleanup(case.doCleanups);case.setUp()
        self.schema=case.dataset.db.schema
        return case

    def test_actual_study_material_http_cli_drift_cold_read_and_replay_are_inert(self):
        case=self.fixture();trial,body=case.prepare();ref=trial['material']
        base=case.server();client=api.AgentClient(base,case.agent['token'],case.dataset.db.dataset_id)
        with case.owner.bound(case.dataset):
            before=case.studies.get(case.study['id'])
            tables=('workspace_recipe_materials','model_trials','workspace_runs','access_execution_grants',
                    'access_execution_consumptions','model_attempt_reservations')
            counts={name:case.dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in tables}
            stored=case.dataset.pipelines.recipe_material(ref,verify=True)
            graph=copy.deepcopy(case.graph);graph['name']='New draft after retained preparation'
            case.dataset.pipelines.save(graph['id'],{'revision':graph['revision'],'document':graph})
        with patch('subprocess.Popen',side_effect=AssertionError('Preflight cannot execute')):
            value=client.call('recipes.preflight_material',{'ref':ref})
            self.assertEqual(value['status'],200)
            report=value['result']['preflight_report']
            self.assertEqual(report['graph_revision'],case.graph['revision'])
            self.assertEqual({k:v for k,v in value['result'].items() if k!='preflight_report'},stored)
            (case.project_path/'recipe.py').write_bytes(case.source+b'\n# actual source drift\n')
            refused=client.call('recipes.preflight_material',{'ref':ref})
            self.assertEqual(refused['status'],409)
            self.assertIsNone(refused['result']['preflight_report']['model_ref'])
            self.assertIsNone(refused['result']['preflight_report']['execution_sha256'])
            stderr=io.StringIO()
            with tempfile.NamedTemporaryFile(mode='w+',suffix='.json') as arguments:
                json.dump({'ref':ref},arguments);arguments.flush()
                with patch.object(api.AgentClient,'from_config',return_value=client),redirect_stderr(stderr):
                    code=project_cli.main(['--config','/unused','call','--operation','recipes.preflight_material',
                                           '--arguments',arguments.name])
            self.assertEqual(code,1)
            self.assertEqual(json.loads(stderr.getvalue())['preflight_report'],refused['result']['preflight_report'])
            self.assertEqual(client.call('recipes.material',{'ref':ref})['result'],stored)
            with case.owner.bound(case.dataset):
                self.assertEqual(case.studies.prepare_trial(case.study['id'],body),trial)
                self.assertEqual(case.studies.get(case.study['id']),before)
                self.assertEqual(case.dataset.runs.list(),[])
                self.assertEqual(case.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)
                self.assertEqual({name:case.dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0]
                                  for name in tables},counts)
        request=Request(base+'/api/workspace/recipe-material/preflight',data=api.encoded({'ref':ref}),
                        headers={'Authorization':'Bearer '+case.agent['token'],'Content-Type':'application/json'})
        with patch.object(case.dataset.pipelines,'preflight_recipe_material') as prepare:
            with self.assertRaises(HTTPError) as caught:urlopen(request,timeout=20)
            self.assertEqual(caught.exception.code,409)
            self.assertNotIn('preflight_report',json.loads(caught.exception.read()));prepare.assert_not_called()
        bad=api.AgentClient(base,'x'*32,case.dataset.db.dataset_id)
        bad._ready=True;bad._selected={'recipes.preflight_material':1}
        with patch.object(case.dataset.pipelines,'preflight_recipe_material') as prepare:
            denied=bad.call('recipes.preflight_material',{'ref':ref})
            self.assertEqual(denied['status'],401);self.assertNotIn('preflight_report',denied['result'])
            prepare.assert_not_called()

    def test_current_disclosure_rechecked_and_retained_tamper_has_unknown_proofs(self):
        case=self.fixture();trial,_=case.prepare();ref=trial['material']
        with case.owner.bound(case.dataset):
            value=case.dataset.pipelines.recipe_material(ref,verify=True)
            from access import AccessError
            with patch.object(case.dataset.pipelines,'recipe_material',side_effect=[value,AccessError('Revoked')]):
                with self.assertRaises(AccessError) as caught:
                    case.dataset.pipelines.preflight_recipe_material(ref,report=True)
            self.assertIsNone(getattr(caught.exception,'preflight_report',None))
            item=value['material']['captures'][0]
            path=case.dataset.pipelines.material_path/ref['sha256']/item['name']
            path.chmod(0o600);path.write_bytes(b'x'*item['bytes'])
            with self.assertRaises(WorkbenchError) as caught:
                case.dataset.pipelines.preflight_recipe_material(ref,report=True)
            report=caught.exception.preflight_report
            self.assertEqual(report['state'],'blocked');self.assertIsNone(report['material_sha256'])
            self.assertFalse(any(row['state']=='checked' for row in report['checks']))


if __name__=='__main__':unittest.main()
