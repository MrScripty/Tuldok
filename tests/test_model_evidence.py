"""Automatic classifier evidence verified against actual CPU state and catalog custody."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent/'fixtures'))
from app import Dataset
from auth_helpers import ExplicitOwnerFixture
from image_classification_fixture import populate
import image_training
import model_evidence
from workbench import WorkbenchError

ROOT=Path(__file__).resolve().parents[1]


class ModelParameterTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'),'Qualified CPU runtime required for stable numerical oracle.')
    def test_saturated_logits_match_actual_torch_cross_entropy_without_clamping(self):
        # This checks the numerical formula; it never creates a fitted Run.
        code="import json,torch; x=torch.tensor([[0.,-1000.]],dtype=torch.float32); print(json.dumps({'loss':float(torch.nn.functional.cross_entropy(x,torch.tensor([1]))),'probabilities':x.softmax(1)[0].tolist()}))"
        result=subprocess.run([os.environ['TULDOK_TRAINING_PYTHON'],'-c',code],capture_output=True,timeout=30,check=True)
        actual=json.loads(result.stdout)
        self.assertEqual(actual['probabilities'],[1.,0.])
        loss,probabilities=model_evidence.stable_cross_entropy([0.,-1000.],1)
        self.assertEqual(loss,actual['loss']);self.assertEqual(probabilities,actual['probabilities'])
        self.assertEqual(loss,1000.)
        for logits in ([float('nan'),0.],[float('inf'),0.],[]):
            with self.assertRaises(ValueError):model_evidence.stable_cross_entropy(logits,0)

    def test_v2_architecture_is_typed_and_legacy_parameters_stay_closed(self):
        parameters={key:rule['default'] for key,rule in image_training.PARAMETER_BOUNDS.items()}
        params=dict(parameters,widths=[4,12,64],input_size=32,head='linear')
        self.assertEqual(image_training.validate_model_parameters(params),params)
        for changed in ({'widths':[4,True,16]},{'widths':[4,8]},{'widths':[4,8,65]},
                        {'input_size':True},{'input_size':48},{'head':'custom'},{'dropout':.2}):
            with self.subTest(changed=changed),self.assertRaises(image_training.TrainingError):
                image_training.validate_model_parameters(dict(params,**changed))
        with self.assertRaises(image_training.TrainingError):image_training.validate_parameters(params)
        self.assertEqual(image_training.TRANSFORM['version'],1)
        self.assertEqual(image_training.transform_for_parameters(params)['version'],2)

    def test_checkpoint_inventory_fits_closed_32_file_profile(self):
        self.assertEqual(len(model_evidence.payload_names(5))+1,31)
        self.assertNotIn('model-evidence.json',model_evidence.BASE_PAYLOADS)


@unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'),'Separately provisioned qualified CPU runtime required.')
class ActualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='actual-model-evidence-')
        cls.dataset=Dataset(Path(cls.temporary.name)/'catalog')
        cls.owner=ExplicitOwnerFixture.bootstrap(cls.dataset)
        try:
            with cls.owner.bound(cls.dataset):
                rows=populate(cls.dataset)
                body={'format':'image_classification_v1','items':[{key:row[key] for key in ('id','revision','source_revision')} for row in rows],
                      'ratios':{'train':34,'validation':33,'test':33},'seed':42}
                preview=cls.dataset.releases.preview(body)
                release=cls.dataset.releases.create(dict(body,preview_token=preview['preview_token']))
                graph=cls.dataset.pipelines.create({'name':'Actual evidence regression','release_id':release['id'],'recipe':image_training.MODEL_RECIPE})
                changed=copy.deepcopy(graph)
                next(node for node in changed['nodes'] if node['type']=='train')['parameters'].update(epochs=2,widths=[4,8,12],input_size=32)
                graph=cls.dataset.pipelines.save(graph['id'],{'revision':graph['revision'],'document':changed})
                validation=cls.dataset.pipelines.validate(graph['id'],{'revision':graph['revision']})
                cls.completed_run=cls.dataset.runs.submit({'request_key':'actual-evidence-regression','graph_id':graph['id'],
                    'graph_revision':graph['revision'],'validation_token':validation['validation_token']})
                until=time.monotonic()+120
                while cls.completed_run['state'] in ('queued','running','cancelling') and time.monotonic()<until:
                    time.sleep(.1);cls.completed_run=cls.dataset.runs.get(cls.completed_run['id'])
                if cls.completed_run['state']!='completed':raise AssertionError(cls.completed_run.get('error'))
                cls.private=cls.dataset.runs._load(cls.completed_run['id'])
                cls.evidence=cls.dataset.runs.model_evidence(cls.completed_run['id'])
        except BaseException:
            cls.dataset.close();cls.temporary.cleanup();raise

    @classmethod
    def tearDownClass(cls):
        cls.dataset.close();cls.temporary.cleanup()

    def test_real_epochs_have_bound_descriptors_and_distinct_weights(self):
        entries=self.evidence['checkpoint_index']['entries']
        self.assertEqual([entry['clocks']['epoch'] for entry in entries],[1,2])
        self.assertEqual(len({entry['checkpoint']['sha256'] for entry in entries}),2)
        self.assertEqual(sum(entry['selected'] for entry in entries),1)
        self.assertEqual(self.evidence['manifest']['format'],'model_evidence_v1')
        self.assertEqual(len(self.evidence['probe']['members']),2)
        with self.owner.bound(self.dataset):
            for entry in entries:
                result=self.dataset.runs.model_evidence(self.completed_run['id'],{'checkpoint_sha256':entry['checkpoint']['sha256']})
                self.assertEqual(result['checkpoint']['clocks'],entry['clocks'])
                self.assertEqual(result['predictions']['checkpoint_sha256'],entry['checkpoint']['sha256'])
            self.assertEqual(self.dataset.runs.compare_model_evidence(self.completed_run['id'],self.completed_run['id'])['state'],'compatible')

    def test_missing_or_modified_required_evidence_cannot_publish_or_reopen(self):
        source=self.dataset.runs.path/self.completed_run['id']
        for name in ('weights-epoch-0001.pt','probes-epoch-0002.json','checkpoint-epoch-0002.json','probe.json','validation-logits.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/'output';shutil.copytree(source,target)
                (target/name).unlink()
                with self.assertRaises(WorkbenchError):self.dataset.runs._verify_directory(self.private,target)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'output';shutil.copytree(source,target)
            descriptor=json.loads((target/'checkpoint-epoch-0001.json').read_text());descriptor['clocks']['epoch']=2
            (target/'checkpoint-epoch-0001.json').write_text(json.dumps(descriptor))
            with self.assertRaises(ValueError):model_evidence.verify(target,self.private,self.private['metrics'])

    def test_checkpoint_replay_is_an_actual_separate_cpu_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp)/'job.json';job.write_text(json.dumps({'parent_pid':os.getpid(),
                'release_path':self.private['release_path'],'release_sha256':self.completed_run['release_sha256'],
                'output_dir':str(self.dataset.runs.path/self.completed_run['id']),'parameters':self.completed_run['parameters']}))
            result=subprocess.run([os.environ['TULDOK_TRAINING_PYTHON'],str(ROOT/'image_training.py'),'--verify-evidence',str(job)],
                                  capture_output=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout.decode())

    def test_queries_never_deserialize_weights_or_expose_test(self):
        with self.owner.bound(self.dataset),patch('subprocess.Popen',side_effect=AssertionError('Query must be inert')):
            result=self.dataset.runs.model_evidence(self.completed_run['id'])
            self.assertEqual(result,self.evidence)
            with self.assertRaises(WorkbenchError):self.dataset.runs.model_evidence(self.completed_run['id'],{'split':'test'})
            with self.assertRaises(WorkbenchError):self.dataset.runs.model_evidence(self.completed_run['id'],{'checkpoint_sha256':'f'*64})
            self.assertFalse(self.dataset.runs.get(self.completed_run['id'])['test_exposure']['exposed'])

    def test_real_http_downloads_each_retained_checkpoint_and_weights(self):
        from app import make_handler
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        import threading
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        endpoint=f'http://127.0.0.1:{server.server_port}'
        try:
            for entry in self.evidence['checkpoint_index']['entries']:
                with self.owner.bound(self.dataset):
                    selected=self.dataset.runs.model_evidence(self.completed_run['id'],{'checkpoint_sha256':entry['checkpoint']['sha256']})
                for item in (entry['checkpoint'],selected['checkpoint']['weights']):
                    request=Request(endpoint+'/api/workspace/runs/'+self.completed_run['id']+'/artifacts/'+item['name'],
                        headers={**self.owner.headers,'Origin':endpoint})
                    with urlopen(request,timeout=30) as response:raw=response.read()
                    self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(item['bytes'],item['sha256']))
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)

    def test_study_budget_cannot_delegate_builtin_execution(self):
        from access import AccessError
        with self.owner.bound(self.dataset):
            model_body=copy.deepcopy(next(item for item in self.dataset.pipelines.definitions()['recipes']
                if item['id']==image_training.MODEL_RECIPE)['model_template'])
            model_body.update(specification=self.evidence['model_definition']['specification'],
                              preprocessing_policy=self.evidence['model_definition']['preprocessing_policy'])
            model=self.dataset.models.create(model_body)
            material=self.dataset.models.publish(model['id'],{'revision':model['revision']})
            graph=self.completed_run['graph']
            validation=self.dataset.pipelines.validate(graph['id'],{'revision':graph['revision']})
            study=self.dataset.studies.create({'name':'Owner authority regression','limits':{'attempt_slots':2,
                'admitted_wall_seconds':2000,'retained_bytes':256*1024**2,'peak_staging_bytes':512*1024**2},
                'policy':validation['selection_policy']})
            trial=self.dataset.studies.prepare_trial(study['id'],{'request_key':'prepare-owner-authority',
                'revision':study['revision'],'graph_id':graph['id'],'graph_revision':graph['revision'],
                'model':material['ref'],'replicate':0})
            current=self.dataset.studies.get(study['id'])['study']
            current=self.dataset.studies.continue_study(study['id'],{'request_key':'continue-owner-authority',
                'revision':current['revision'],'admission_epoch':current['admission_epoch']})
            agent=self.dataset.access.issue({'label':'Classifier inspector','scopes':['inspect','execute']})
            grant=self.dataset.access.grant_execution(trial['material']['sha256'],agent['identity']['actor_id'])
        body={'request_key':'admit-owner-authority','revision':current['revision'],
              'admission_epoch':current['admission_epoch'],'trial_id':trial['id'],'approval_id':grant['id']}
        with self.dataset.access.bind(agent['token']),self.assertRaises(AccessError):
            self.dataset.studies.admit(study['id'],body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.studies.get(study['id'])['charged']['attempt_slots'],0)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions WHERE grant_id=%s',(grant['id'],)).fetchone()[0],0)
            body.pop('approval_id')
            with patch.object(self.dataset.runs,'_start'):
                admitted=self.dataset.studies.admit(study['id'],body)
            self.assertEqual(admitted['run']['study_membership'],{'study_id':study['id'],'trial_id':trial['id']})
            self.dataset.runs.cancel(admitted['run']['id'])

    def test_standalone_run_has_no_invented_study_membership(self):
        with self.owner.bound(self.dataset):
            result=self.dataset.runs.get(self.completed_run['id'])
        self.assertIsNone(result['study_membership'])
        self.assertNotIn('evidence_context',result)

if __name__=='__main__':unittest.main()
