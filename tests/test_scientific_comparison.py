"""Retained-byte diagnostics only; fixtures do not qualify scientific acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

import agent_api
import extension_evidence as evidence
from test_extension_field_evidence import authored_fixture, npy
from workbench import WorkbenchError


def retained_pair(root):
    """Independently authored field values, with all owner-verified content hashes."""
    fixtures=[]
    for index in range(2):
        directory=root/str(index);directory.mkdir()
        definition,model,composition,run,writer=authored_fixture(directory)
        # A second identity is deliberately rebuilt in every owned JSON record.
        if index:
            for path in directory.glob('*.json'):
                raw=path.read_bytes().replace(b'1'*32,b'3'*32)
                path.write_bytes(raw)
            run['id']='3'*32;run['extension_context']['run_id']=run['id']
            # Checkpoint descriptor hashes changed; rebuild their dependants.
            for group,entry in zip(writer.field_groups,writer.entries,strict=True):
                old=entry['checkpoint']['sha256'];new=writer.blob(entry['checkpoint']['name'])
                entry['checkpoint']=new
                group['run_id']=run['id'];group['checkpoint_sha256']=new['sha256']
                for row in writer.observations:
                    if row['checkpoint_sha256']==old:row.update(run_id=run['id'],checkpoint_sha256=new['sha256'])
            writer.context['run_id']=run['id']
            writer.entries[-1]['selected']=True
            (directory/'checkpoints.json').write_bytes(evidence.canonical({'format':'checkpoint_index_v1','run_id':run['id'],'entries':writer.entries})+b'\n')
            (directory/'observations.json').write_bytes(evidence.canonical(writer.observations)+b'\n')
        context_raw=evidence.canonical(run['extension_context'])
        (directory/'execution-context.json').write_bytes(context_raw)
        run['spec']['model_evidence_context'].update(bytes=len(context_raw),sha256=hashlib.sha256(context_raw).hexdigest())
        # The independently expected diagnostic difference is 2 at every cell.
        reference_raw=(directory/'reference.npy').read_bytes();offset=10+struct.unpack_from('<H',reference_raw,8)[0]
        values=list(struct.unpack_from('<64d',reference_raw,offset))
        for point in (16,32,48,64):
            (directory/f'prediction-{point}.npy').write_bytes(npy([v+index*2 for v in values],[4,4,4]))
        for group in writer.field_groups:
            for case in group['cases']:case['predicted']=writer.blob(case['predicted']['name'])
        (directory/'field-index.json').write_bytes(evidence.canonical(writer.field_groups)+b'\n')
        manifest=json.loads((directory/'model-evidence.json').read_bytes())
        for key,name in [('checkpoints','checkpoints.json'),('field_index','field-index.json')]:manifest[key]=writer.blob(name)
        manifest['observations']=[writer.blob('observations.json')]
        (directory/'model-evidence.json').write_bytes(evidence.canonical(manifest)+b'\n')
        run['artifacts']=[{'name':row['path'],'role':row['role'],'bytes':(directory/row['path']).stat().st_size,
            'sha256':hashlib.sha256((directory/row['path']).read_bytes()).hexdigest(),'media_type':'application/octet-stream'} for row in definition['outputs']]
        verified=evidence.verify(directory,run,run['extension_context'])
        fixtures.append((directory,run,verified))
    return fixtures


def choices(pair):
    body={'metric_id':pair[0][2]['metric_definitions'][0]['id'],'mode':'paired'}
    for index,(directory,run,value) in enumerate(pair):
        prefix='other_' if index else ''
        body.update({prefix+'checkpoint_sha256':value['checkpoint_index']['entries'][0]['checkpoint']['sha256'],
                     prefix+'evaluation_sha256':hashlib.sha256((directory/'model-evidence.json').read_bytes()).hexdigest(),
                     prefix+'metric_definition_sha256':evidence.digest(value['metric_definitions'][0])})
    return body


class ScientificComparisonTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.pair=retained_pair(Path(temporary.name));self.selection=choices(self.pair)
        self.verified=[item[2] for item in self.pair];self.contexts=[item[1]['extension_context'] for item in self.pair]
        self.point={'field_id':self.verified[0]['fields'][0]['field_id'],'x':1,'y':2,'z':3}

    def compare(self):return evidence.compare_scientific(self.verified,self.contexts,self.selection,self.point)

    def test_independent_expected_values_and_exact_clocks_with_no_scientific_criterion(self):
        result=self.compare();row=result['cases'][0]
        self.assertEqual(result['scalar']['state'],'compatible')
        reference_raw=(self.pair[0][0]/'reference.npy').read_bytes()
        offset=10+struct.unpack_from('<H',reference_raw,8)[0]+8*(1+4*(2+4*3))
        expected=struct.unpack_from('<d',reference_raw,offset)[0]
        self.assertEqual(row['values'][0]['prediction'],expected)
        self.assertEqual(row['values'][1]['prediction'],expected+2)
        self.assertEqual(row['prediction_delta']['value'],2)
        self.assertEqual(result['coverage'],{'baseline':1,'candidate':1,'matched':1,'union':1})
        self.assertEqual(row['acceptance']['state'],'unknown')
        self.assertEqual(result['scalar']['sides'][0]['clocks']['optimizer_update'],16)
        self.assertIsNone(result['scalar']['sides'][0]['clocks']['fit_pass'])
        self.assertNotIn('_arrays',json.dumps(result))

    def test_isolated_incompatibilities_have_no_delta(self):
        mutations=[
            ('data',lambda:self.verified[1]['manifest'].update(data_sha256='a'*64),'Evaluation data identities differ.'),
            ('split',lambda:self.verified[1]['probe'].update(split='train'),'Evaluation splits differ or are unsupported.'),
            ('normalization',lambda:self.contexts[1]['static']['policy']['preprocessing_policy'].update(scope='different'),'Preprocessing policies differ.'),
            ('geometry',lambda:self.contexts[1]['static']['policy']['fields'][0]['geometry']['origin_xyz'].__setitem__(0,1),'Field contracts, geometry or gauge semantics differ.'),
            ('cases',lambda:self.verified[1]['probe']['members'][0]['frozen_reference'].update(member_id='other'),'Frozen validation membership or targets differ.'),
            ('selection',lambda:self.verified[1]['probe'].update(selection_policy_sha256='a'*64),'Case selection policies differ.'),
        ]
        for label,mutate,reason in mutations:
            with self.subTest(dimension=label):
                originals=copy.deepcopy((self.verified,self.contexts));mutate();result=self.compare()
                self.assertEqual(result['scalar']['state'],'incompatible');self.assertIn(reason,result['scalar']['reasons'])
                self.assertIsNone(result['scalar']['delta']);self.assertTrue(all(row['prediction_delta'] is None for row in result['cases']))
                self.verified,self.contexts=originals
        for key,value in [('units','other_unit'),('direction','none'),('reduction','other')]:
            with self.subTest(metric=key):
                original=copy.deepcopy(self.verified[1]['metric_definitions'][0]);self.verified[1]['metric_definitions'][0][key]=value
                self.selection['other_metric_definition_sha256']=evidence.digest(self.verified[1]['metric_definitions'][0])
                result=self.compare();self.assertIn('Metric definition, population, units or evaluator semantics differ.',result['scalar']['reasons'])
                self.verified[1]['metric_definitions'][0]=original;self.selection=choices(self.pair)

    def test_missing_cases_are_union_rows_and_never_paired_by_ordinal(self):
        self.verified[1]['probe']['members'][0]['frozen_reference']['member_id']='different'
        result=self.compare();self.assertEqual(result['coverage'],{'baseline':1,'candidate':1,'matched':0,'union':2})
        self.assertEqual(sum(side['state']=='missing' for row in result['cases'] for side in row['values']),2)
        self.assertTrue(all(row['prediction_delta'] is None for row in result['cases']))

    def test_selection_is_exact_and_side_by_side_or_missing_fields_never_invents_values(self):
        self.selection['mode']='side_by_side';self.assertIsNone(self.compare()['cases'][0]['prediction_delta'])
        self.point['field_id']='not_retained';result=self.compare()
        self.assertTrue(all(side['state']=='missing' for side in result['cases'][0]['values']))
        self.point['field_id']=self.verified[0]['fields'][0]['field_id'];self.point['x']=4
        with self.assertRaises(WorkbenchError):self.compare()
        self.point['x']=0;self.selection['checkpoint_sha256']='f'*64
        with self.assertRaises(WorkbenchError):self.compare()

    def test_new_contract_is_read_only_and_old_pins_unchanged(self):
        contract=agent_api.contract('runs.compare_scientific_evidence',1)
        self.assertEqual(contract['effects'],'read')
        self.assertIn(contract['sha256'],(Path(__file__).parents[1]/'static/workspace-scientific-comparison.js').read_text())
        self.assertEqual(agent_api.contract('runs.compare_model_evidence',2)['sha256'],'0c89402e1749b5bca7c09c66bc5bfc13cd33b3be6e15c69826074583fc0e13c5')
        with self.assertRaises(agent_api.AgentAPIError):agent_api.validate_arguments('runs.compare_scientific_evidence',{'operands':[],'selection':self.selection,'point':self.point})


@unittest.skipUnless(__import__('os').environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ScientificReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scientific_comparison_fixture import ScientificFixture
        cls.fixture=ScientificFixture()

    @classmethod
    def tearDownClass(cls):cls.fixture.close()

    def test_actual_completed_and_attached_publication_readers_preserve_failed_state_and_counts(self):
        fixture=self.fixture;dataset=fixture.dataset
        for recovered in (False,True):
            body=fixture.body(recovered)
            with fixture.owner.bound(dataset):result=dataset.runs.compare_scientific_evidence(body)
            self.assertEqual(result['scalar']['state'],'compatible')
            self.assertEqual(result['cases'][0]['prediction_delta']['value'],2)
            self.assertEqual(result['scalar']['delta']['value'],2)
            self.assertEqual(result['operands'][0]['model'],fixture.model['ref'])
            self.assertEqual(result['operands'][0]['study_membership']['trial_id'],fixture.trials[0]['id'])
            self.assertEqual(result['operands'][1]['memory']['state'],'unknown')
            self.assertEqual(result['operands'][1]['original_run_state'],'interrupted' if recovered else 'completed')
            agent_api.validate_output('runs.compare_scientific_evidence',{'status':200,'result':result})
        self.assertEqual(fixture.counts(),fixture.before_counts)
        with fixture.owner.bound(dataset):
            self.assertEqual(dataset.runs.get(fixture.runs[2]['id'])['state'],'interrupted')
            body=fixture.body();body['operands'][1]={'kind':'completed_run','catalog_id':dataset.db.dataset_id,'run_id':fixture.runs[2]['id']}
            with self.assertRaises(WorkbenchError) as caught:dataset.runs.compare_scientific_evidence(body)
            self.assertEqual(caught.exception.code,'unsupported')
            with self.assertRaises(WorkbenchError):dataset.runs.model_evidence(fixture.runs[2]['id'],{},contract_version=2)

    def test_exact_ref_and_evaluation_refuse_before_projection(self):
        fixture=self.fixture;dataset=fixture.dataset
        body=fixture.body(True);body['operands'][1]['ref']=dict(body['operands'][1]['ref'],sha256='f'*64)
        with fixture.owner.bound(dataset),self.assertRaises(WorkbenchError):dataset.runs.compare_scientific_evidence(body)
        body=fixture.body();body['selection']['other_evaluation_sha256']='f'*64
        with fixture.owner.bound(dataset),self.assertRaises(WorkbenchError) as caught:dataset.runs.compare_scientific_evidence(body)
        self.assertEqual(caught.exception.code,'stale')

    def test_current_material_blob_and_retained_root_removal_are_refused(self):
        fixture=self.fixture;dataset=fixture.dataset;body=fixture.body()
        root=dataset.runs.path/fixture.runs[1]['id'];moved=root.with_name(root.name+'-test-held')
        root.rename(moved)
        try:
            with fixture.owner.bound(dataset),self.assertRaises(WorkbenchError):dataset.runs.compare_scientific_evidence(body)
        finally:moved.rename(root)
        # Full canonical _load/_extension_context rederive the Model closure.
        item=fixture.model['material']['source_closure'][0]['blob']
        path=dataset.models.path/fixture.model['ref']['sha256']/item['name'];raw=path.read_bytes();mode=path.stat().st_mode&0o777
        path.chmod(0o600);path.write_bytes(b'x'*len(raw));path.chmod(mode)
        try:
            with fixture.owner.bound(dataset),self.assertRaises(WorkbenchError):dataset.runs.compare_scientific_evidence(body)
        finally:path.chmod(0o600);path.write_bytes(raw);path.chmod(mode)

    def test_revocation_during_owner_projection_fences_all_result_delivery(self):
        from access import AccessError
        from unittest.mock import patch
        fixture=self.fixture;dataset=fixture.dataset;body=fixture.body()
        with fixture.owner.bound(dataset):agent=dataset.access.issue({'label':'M6 inspect-only','scopes':['inspect']})
        original=evidence.compare_scientific
        def revoke_after_projection(*args):
            value=original(*args)
            with fixture.owner.bound(dataset):dataset.access.revoke(agent['identity']['credential_id'])
            return value
        with dataset.access.bind(agent['token']),patch('extension_evidence.compare_scientific',side_effect=revoke_after_projection),self.assertRaises(AccessError):
            dataset.runs.compare_scientific_evidence(body)

    def test_actual_http_requires_exact_contract_and_serves_both_custody_forms(self):
        from http.server import ThreadingHTTPServer
        import threading
        from urllib.error import HTTPError
        from urllib.request import urlopen
        from app import make_handler
        fixture=self.fixture;server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(fixture.dataset))
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)+'/api/workspace/scientific-comparison'
            for recovered in (False,True):
                body=fixture.body(recovered)
                request=fixture.owner.request(url,json.dumps(body).encode(),{'Content-Type':'application/json',
                    'Tuldok-Operation-Contract':'runs.compare_scientific_evidence/1/'+agent_api.contract('runs.compare_scientific_evidence')['sha256']})
                with urlopen(request) as response:result=json.load(response)
                self.assertEqual(result['cases'][0]['prediction_delta']['value'],2)
            request=fixture.owner.request(url,json.dumps(body).encode(),{'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as caught:urlopen(request)
            self.assertEqual(caught.exception.code,409)
        finally:server.shutdown();server.server_close();thread.join(5)


if __name__=='__main__':unittest.main()
