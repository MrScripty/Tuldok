"""Canonical A authored byte-contract fixtures; no producer Run or quality claim.

The exact PR76 author source is a dependency. An isolated developer can point
TULDOK_CANONICAL_AUTHOR_SOURCE at an explicitly materialized copy of that source;
every numerical/SDK source is still checked against the literal frozen contract.
The production package implementation has no environment/source hook.
"""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import candidate_packages as p
import extension_evidence as evidence
from tuldok_extension_sdk.evidence import Evidence
from test_candidate_packages import fixture as classifier_fixture
from test_extension_field_evidence import npy

ROOT = Path(__file__).resolve().parents[1]
INFERENCE = ROOT/'examples/extensions/field-surrogate/v3-canonical'
AUTHOR = Path(os.environ.get('TULDOK_CANONICAL_AUTHOR_SOURCE', str(INFERENCE)))


def fixture(configuration=None):
    """Only the public JSON writer runs; numeric states are explicit test values."""
    contract = p.decode((INFERENCE/'inference-contract.json').read_bytes())
    frozen = contract['policy']; authority = contract['source_authority']
    sources = {name: (AUTHOR/name).read_bytes() for name in [*authority['numerical_sources'], *authority['sdk_sources']]}
    sources.update({'infer.py': (INFERENCE/'infer.py').read_bytes(),
                    'inference-contract.json': (INFERENCE/'inference-contract.json').read_bytes()})
    for kind, value in authority['role_declarations'].items():
        sources[kind+'.json'] = evidence.canonical(value)+b'\n'
    original = p.decode((ROOT/'examples/extensions/field-surrogate/v2/recipe.json').read_bytes())
    recipe = copy.deepcopy(original); policy = recipe['model_evidence']; catalog = 'd'*32; run_id = 'a'*32
    runtime = p.decode(classifier_fixture()[1]['runtime.json']); runtime['snapshot']['catalog_id'] = catalog
    recipe.update(schema_version=3, format='external_model_evidence_recipe_v2', entrypoint='producer.py',
                  name='Explicit authored canonical café fixture',
                  runtime_snapshot_sha256=runtime['snapshot']['manifest_sha256'])
    policy.update(format='extension_field_policy_v2', model_specification=copy.deepcopy(frozen['model_specification']),
                  preprocessing_policy=copy.deepcopy(frozen['preprocessing_policy']), output_policy=copy.deepcopy(frozen['output_policy']))
    policy['model_specification']['configuration'] = configuration or {'initial_scale': .5, 'initial_offset': -.25}
    policy['task'].update(revision=3, definition=authority['role_declarations']['task'])
    policy['profile'].update(id=frozen['profile']['id'], revision=3)
    field = {'id':'raw', 'contract': copy.deepcopy(frozen['field_contract']),
             'geometry': frozen['geometry'], 'gauge_policy': frozen['gauge_policy']}
    policy['fields'] = [field]
    authored = p.decode(sources['authored-source.json']); native = {}; cases = []; members = []
    release_sha = p.sha(b'x')  # Byte-contract fixture only; no actual Release or Run.
    for ordinal, case in enumerate(authored['cases']):
        record_id = str(ordinal+1)*32
        members.append({'case_id':case['id'],'record_id':record_id,'revision':1,'source_revision':1,'split':case['split']})
        arrays = []
        for field_id, key in [('initial','initial'),('reference','target')]:
            name = ('input-initial.npy' if field_id == 'initial' else 'reference.npy') if case['split'] == 'validation' else case['id']+'-'+field_id+'.npy'
            raw = npy(case[key], [4,4,4]); native[name] = raw; payload, _ = p._scalar_npy(raw,(4,4,4))
            arrays.append({'field_id':field_id,'source_sha256':p.sha(raw),'payload_sha256':p.sha(payload),
                           'gauge_policy_sha256':frozen['field_contract']['output']['gauge_policy_sha256'],
                           'output':p.blob(name,raw,'application/x-npy')})
        cases.append({'id':case['id'],'record_id':record_id,'split':case['split'],'arrays':arrays,
                      'release_sha256':release_sha,'geometry_sha256':evidence.digest(frozen['geometry']),'frame':0,'time':'0'})
    source_contract = copy.deepcopy(frozen['field_contract'])
    source_contract.update(adapter={'name':'authored_scalar_a_canonical_source','version':1},source_sha256='9'*64)
    source_contract['output'].update(field_id='reference',stage='reference_target')
    derivation = {'format':'field_input_derivation_v1','contract_sha256':evidence.digest(source_contract),
                  'family_scope':'selected_records_only','cases':cases,'fit_case_ids':['train-0','train-1']}
    derivation_raw = evidence.canonical(derivation)+b'\n'
    provenance_raw = evidence.canonical({'release_sha256':release_sha,'contract':source_contract,'catalog_id':catalog,
        'source_sha256':p.sha(sources['authored-source.json']),'compiler_sha256':'9'*64})+b'\n'
    canonical = {'format':'canonical_field_inputs_v1','release':{'input':'canonical','sha256':release_sha},
        'derivation':{'input':'derivation','sha256':p.sha(derivation_raw),'output':'canonical-derivation.json'},
        'provenance':{'input':'provenance','sha256':p.sha(provenance_raw)},'contract':source_contract,'members':members,
        'mapping':{'inputs':[{'source_field_id':'initial','model_field_id':'initial'}],'target':{'source_field_id':'reference'}}}
    policy['canonical'] = canonical
    for row in [*policy['fit_members'], *[item['frozen_reference'] for item in policy['probe']['candidates']]]:
        row.update(input='canonical', sha256=release_sha)
    payload,_ = p._scalar_npy(native['reference.npy'],(4,4,4))
    policy['field_targets']=[{'member_id':'validation-0','field_id':'raw','payload_sha256':p.sha(payload)}]
    policy['probe']['candidates'][0]['target_sha256']=evidence.digest([{'field_id':'raw','payload_sha256':p.sha(payload)}])
    recipe['inputs']={'canonical':{'max_bytes':1048576},'derivation':{'max_bytes':65536},'provenance':{'max_bytes':65536}}
    recipe['arguments']=[{'input':name} for name in recipe['inputs']]+[{'model_evidence_context':True},{'output_dir':True}]
    for name in native:
        if not any(row['path']==name for row in recipe['outputs']):
            recipe['outputs'].append({'path':name,'role':'field_source','max_bytes':8192,'required':True})
    recipe['outputs'].append({'path':'canonical-derivation.json','role':'field_derivation','max_bytes':65536,'required':True})
    for row in recipe['outputs']:
        name=row['path']
        if name in native:row['role']='field_source'
        elif name.startswith('prediction-'):row['role']='field_prediction'
        elif name.startswith('checkpoint-'):row['role']='model_checkpoint'
        elif name.startswith('weights-') or name=='transform.npy':row['role']='model_state'
    refs=[{'id':value['id'],'version':value['version'],'kind':kind,'path':kind+'.json',
           'sha256':p.sha(sources[kind+'.json']),'bytes':len(sources[kind+'.json'])} for kind,value in authority['role_declarations'].items()]
    provider={'package':{'id':'example.scalar-a','version':'3.0.0'},'runtime':{'profile':'captured_cpu_python_v1','snapshot_sha256':runtime['snapshot']['manifest_sha256']},
        'sources':[{'path':name,'sha256':p.sha(raw),'bytes':len(raw)} for name,raw in sources.items() if not name.endswith('.json') or name in ('authored-source.json','inference-contract.json')],
        'contributions':refs,'license':{'notices':[{'path':'NOTICE.txt','sha256':p.sha(sources['NOTICE.txt']),'bytes':len(sources['NOTICE.txt'])}]}}
    sources['extension.json']=evidence.canonical(provider)+b'\n'
    recipe['sources']=[{'path':name,'sha256':p.sha(raw)} for name,raw in sorted(sources.items())]
    policy['adapter_sha256']=field['contract']['source_sha256']=evidence.digest(sorted(recipe['sources'],key=lambda item:item['path']))
    sources['recipe.json']=evidence.canonical(recipe)+b'\n'
    sources['project.json']=evidence.canonical({'id':'c'*32,'source':'Authored structural source only'})
    binding={'format':'tuldok_extension_binding_v1','project':{'manifest_sha256':p.sha(sources['project.json'])},
             'inventory':[{'path':name,'sha256':p.sha(raw),'bytes':len(raw)} for name,raw in sources.items() if name!='recipe.json']}
    sources['runtime-bootstrap/extension-binding.json']=evidence.canonical(binding)
    task={'kind':'task','catalog_id':catalog,'id':policy['task']['id'],'revision':3,'sha256':evidence.digest(policy['task']['definition'])}
    published={'material':{'format':'model_material_v1','catalog_id':catalog,'task':task,
        'source_closure':[{'import_path':name,'blob':p.blob('source-'+str(i),raw)} for i,(name,raw) in enumerate(sources.items())]}}
    for name,key in [('specification','model_specification'),('preprocessing_policy','preprocessing_policy'),('output_policy','output_policy')]:
        published[name]=evidence.canonical(policy[key]);published['material'][name]=p.blob(name+'.json',published[name])
    model={'kind':'model','catalog_id':catalog,'id':'b'*32,'revision':1,'sha256':p.sha(p.encoded(published['material']))}
    old_manifest, old_files = __import__('test_scalar_candidate_packages').fixture()
    static=p.decode(old_files['execution-context.json'])['static']
    static.update(policy=policy,model=model,task=task)
    static['profile'].update(task_sha256=task['sha256'],model_sha256=model['sha256'])
    static['profile']['definition'].update(id=policy['profile']['id'],revision=3,sha256=evidence.digest(policy['profile']))
    static['probe'].update(task_sha256=task['sha256'],data_sha256=release_sha)
    static['probe']['members'][0].update(policy['probe']['candidates'][0])
    static['inputs']={'canonical':{'kind':'frozen_release','catalog_id':catalog,'release_id':release_sha,'measured_sha256':release_sha,'bytes':1},
        'derivation':{'measured_sha256':p.sha(derivation_raw)},'provenance':{'measured_sha256':p.sha(provenance_raw)}}
    capture_raw={'source/'+name:raw for name,raw in sources.items() if name!='recipe.json'}
    capture_raw.update({'input/derivation':derivation_raw,'input/provenance':provenance_raw,'input/canonical':b'x'})
    execution={'catalog_id':catalog,'recipe':recipe,'inputs':static['inputs']}
    static['execution_material_sha256']=evidence.digest(execution)
    captures=[{'path':name,'blob':p.blob(f'capture-{i:04d}.bin',raw)} for i,(name,raw) in enumerate(capture_raw.items())]
    snapshot={'format':'external_model_evidence_snapshot_v1','preflight':{'material':execution,'material_sha256':evidence.digest(execution)},
              'evidence_context':static,'capture_paths':captures}
    snapshot_raw=evidence.canonical(snapshot)
    composition={'catalog_id':catalog,'model':model,'recipe_document':p.blob('recipe.json',snapshot_raw),
                 'trainer':{'id':'external_model_evidence_recipe_v1','sha256':evidence.digest(recipe)},
                 'runtime':{'sha256':runtime['snapshot']['manifest_sha256']},
                 'captures':[item['blob'] for item in captures]}
    comp_sha=evidence.digest(composition)
    context={'format':'extension_evidence_context_v1','static':static,'composition':{'kind':'recipe_material','catalog_id':catalog,'id':comp_sha,'sha256':comp_sha},
             'run_id':run_id,'request_sha256':'1'*64}
    with tempfile.TemporaryDirectory() as directory:
        output=Path(directory);writer=Evidence(output,evidence.canonical(context))
        for name,raw in native.items():(output/name).write_bytes(raw)
        (output/'canonical-derivation.json').write_bytes(derivation_raw)
        (output/'transform.npy').write_bytes(npy([3,2],[2]));writer.transform('transform.npy')
        _,values=p._scalar_npy(native['input-initial.npy'],(4,4,4))
        for point in (16,32,48,64):
            (output/f'weights-{point}.npy').write_bytes(npy([2,-.5],[2]))
            (output/f'prediction-{point}.npy').write_bytes(npy([x-3.5 for x in values],[4,4,4]))
            writer.checkpoint(point,{'optimizer_update':point,'epoch':None,'fit_pass':None,'physical_time':None,'wall_elapsed_ms':point},
                              f'weights-{point}.npy',{'reference_mse':0})
        writer.finish();artifacts={path.name:path.read_bytes() for path in output.iterdir()}
    checkpoint=writer.entries[-1]['checkpoint']
    decision={'format':'candidate_v1','id':'2'*32,'study_id':'3'*32,'trial_id':'4'*32,'run_id':run_id,
        'checkpoint_sha256':checkpoint['sha256'],'evaluation_sha256':p.sha(artifacts['model-evidence.json']),
        'policy':{},'decision':'diagnostic','limitations':['Authored byte-contract fixture only; no actual Run.']}
    candidate={'ref':{'kind':'candidate','catalog_id':catalog,'id':decision['id'],'sha256':p.sha(p.encoded(decision))},
               'candidate':decision,'run_id':run_id,'checkpoint':checkpoint}
    return p.canonical_a_closure(candidate,artifacts,sources,runtime,published,
        {'composition':evidence.canonical(composition),'execution_snapshot':snapshot_raw,'canonical_provenance':provenance_raw})


class CanonicalCandidatePackageTests(unittest.TestCase):
    def setUp(self):
        self.manifest,self.files=fixture()

    def test_complete_inspection_is_inert_and_closes_nested_imports_and31_outputs(self):
        with patch('importlib.util.spec_from_file_location',side_effect=AssertionError('No import during inspection')):
            raw=p.create_package(self.manifest,self.files);p.inspect_package(raw,p.sha(raw))
        task=p.decode(self.files[self.manifest['task']['name']])
        self.assertIn('tuldok_extension_sdk/evidence.py',{item['import_path'] for item in task['source_map']})
        self.assertEqual(len(p.decode(self.files['lineage.json'])['sources']),31)
        self.assertFalse(any(name.endswith('.zip') for name in self.files))

    def test_selected_state_replay_ignores_training_initialization_configuration(self):
        result=p._infer_scalar_a(self.manifest,self.files,'5'*64,'6'*64)
        self.assertTrue(result['verified']);self.assertEqual(result['outputs'][0]['stage'],'train')
        self.assertLess(result['outputs'][0]['max_absolute_difference'],1e-14)
        other,files=fixture({'initial_scale':-.75,'initial_offset':.9})
        self.assertEqual(p._infer_scalar_a(other,files,'5'*64,'6'*64)['outputs'][0]['values_c_order'],result['outputs'][0]['values_c_order'])

    def test_canonical_request_source_preserves32_input_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared=p.prepare_project(Path(directory)/'prepared',self.manifest,self.files,snapshot_sha256='6'*64)
            recipe=p.decode((Path(directory)/'prepared/package-recipe.json').read_bytes())
            self.assertEqual(len(recipe['inputs']),32)
            self.assertNotIn('request',recipe['inputs'])
            self.assertIn({'path':'request.json','sha256':p.sha(p.encoded(self.manifest))},recipe['sources'])
            self.assertEqual(recipe['arguments'][1:3],[{'literal':'--request-from-source'},{'literal':'request.json'}])
            self.assertEqual(len(prepared['graph']['inputs']),32)
            output=Path(directory)/'packed';output.mkdir()
            result=subprocess.run([sys.executable,'-I','-S','-B',str(Path(directory)/'prepared/candidate_packages.py'),
                'pack','--request-from-source','request.json','--blobs',str(Path(directory)/'prepared/closure.zip'),
                '--output-dir',str(output)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            raw=(output/'package.zip').read_bytes();p.inspect_package(raw,p.sha(raw))

    def test_missing_native_inference_role_or_nested_source_refuses(self):
        task=p.decode(self.files[self.manifest['task']['name']])
        source=next(item['blob']['name'] for item in task['source_map'] if item['import_path']=='tuldok_extension_sdk/evidence.py')
        for name in ('weights-64.npy','train-0-initial.npy','canonical-derivation.json','infer.py',source):
            with self.subTest(name=name),self.assertRaises(p.PackageError):
                p.create_package(self.manifest,{key:raw for key,raw in self.files.items() if key!=name})

    def test_wrong_selected_weights_and_transform_do_not_reconstruct(self):
        for name in ('weights-64.npy','transform.npy'):
            changed=dict(self.files);changed[name]=npy([0,1],[2])
            with self.subTest(name=name),self.assertRaises(p.PackageError):
                p._infer_scalar_a(self.manifest,changed,'5'*64,'6'*64)

    def test_semantic_role_substitution_refuses_even_before_outer_hash_validation(self):
        task=p.decode(self.files[self.manifest['task']['name']])
        mapping={item['import_path']:item['blob'] for item in task['source_map']}
        files=dict(self.files);role=p.decode(files[mapping['trainer.json']['name']])
        role['stages'][0]['clock']='physical_time'
        files[mapping['trainer.json']['name']]=p.encoded(role)
        contract=p.decode(files['inference-contract.json'])
        context=p.decode(files['execution-context.json']);recipe=p.decode(files[mapping['recipe.json']['name']])
        with self.assertRaisesRegex(p.PackageError,'semantic role'):
            p._validate_canonical_a_sources(self.manifest,files,task,contract,context['static']['policy'],recipe,
                mapping,p.decode(files[self.manifest['checkpoint']['name']]),lambda item:None)

    def test_rehashed_gauge_stage_and_alias_path_do_not_change_the_literal_profile(self):
        from test_candidate_packages import PackageTests
        for mode in ('gauge','stage','alias'):
            manifest=copy.deepcopy(self.manifest);files=dict(self.files)
            if mode=='alias':
                task=p.decode(files[manifest['task']['name']]);task['source_map'][0]['import_path']='../outside.py'
                PackageTests.replace_blob(self,manifest,files,manifest['task']['name'],p.encoded(task))
            else:
                context=p.decode(files['execution-context.json'])
                if mode=='gauge':context['static']['policy']['fields'][0]['gauge_policy']['operation']='subtract_mean'
                else:context['static']['policy']['fields'][0]['contract']['output']['stage']='post_train_mapping'
                PackageTests.replace_blob(self,manifest,files,'execution-context.json',p.encoded(context))
            with self.subTest(mode=mode),self.assertRaises(p.PackageError):
                p.create_package(manifest,files)

    def test_transitive_source_current_authority_refusal_is_preserved_for_canonical_package(self):
        from access import AccessError
        from types import SimpleNamespace
        from unittest.mock import Mock
        require=Mock(side_effect=AccessError('Current source authority revoked','forbidden',403))
        load=Mock(side_effect=AssertionError('Do not inspect a source before current authorization'))
        source=SimpleNamespace(access=SimpleNamespace(require=require),_load=load)
        # The exact package graph retains all31 parent references; production
        # owner calls still use the shared current-authority walk, with no bypass.
        with tempfile.TemporaryDirectory() as directory:
            prepared=p.prepare_project(Path(directory)/'prepared',self.manifest,self.files)
            self.assertEqual({row['run_id'] for row in prepared['graph']['inputs'].values() if row.get('kind')=='run_artifact'}, {'a'*32})
            inputs={key:{'kind':'run_artifact','source':{'run_id':row['run_id'],'artifact_name':row['artifact_name'],
                     'measured_sha256':row['expected_sha256']}} for key,row in prepared['graph']['inputs'].items() if row.get('kind')=='run_artifact'}
            with self.assertRaises(AccessError):p.authorize_material_inputs(source,{'inputs':inputs})
            load.assert_not_called()

    def test_extra_declared_stdlib_shadow_source_refuses_the_literal_profile(self):
        task=p.decode(self.files[self.manifest['task']['name']]);contract=p.decode(self.files['inference-contract.json'])
        mapping={item['import_path']:item['blob'] for item in task['source_map']}
        mapping['json.py']=p.blob('extra-shadow.bin',b'raise RuntimeError("never imported")')
        files=dict(self.files,**{'extra-shadow.bin':b'raise RuntimeError("never imported")'})
        with patch('importlib.util.spec_from_file_location',side_effect=AssertionError('No source imports')):
            with self.assertRaisesRegex(p.PackageError,'full published source closure'):
                p._validate_canonical_a_sources(self.manifest,files,task,contract,
                    p.decode(files['execution-context.json'])['static']['policy'],p.decode(files[mapping['recipe.json']['name']]),
                    mapping,p.decode(files[self.manifest['checkpoint']['name']]),lambda item:None)


if __name__=='__main__':
    unittest.main()
