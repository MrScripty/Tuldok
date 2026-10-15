"""Representative transport only; the separate real SDK conformance gate owns execution proof."""
import base64
import copy
import hashlib
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tuldok_extension_sdk import evidence as sdk
from tuldok_extension_sdk.__main__ import _CLI, _conformance, _selection, main
from test_extension_field_evidence import authored_fixture

ROOT = Path(__file__).resolve().parents[1]

# Explicit representative public-CLI transport. It never calls the app, admits a
# real Run or computes any numerical value. Real acceptance must use project_cli.
REPRESENTATIVE_CLI = '''import argparse,base64,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',required=True);commands=p.add_subparsers(dest='command',required=True)
a=commands.add_parser('call');a.add_argument('--operation',required=True);a.add_argument('--arguments',required=True)
a=commands.add_parser('download')
for flag in ('run-id','name','expected-sha256','out'):a.add_argument('--'+flag,required=True)
a=p.parse_args();fixture=json.loads(Path(a.config).read_text())
if a.command=='call':print(json.dumps(fixture['calls'][a.operation]))
else:
 raw=base64.b64decode(fixture['blobs'][a.name]);Path(a.out).write_bytes(raw);print(json.dumps({'sha256':a.expected_sha256,'bytes':len(raw)}))
'''


class RepresentativeTransport:
    def __init__(self, fixture):
        self.fixture=fixture;self.calls=[];self.run_id=None;self.admission=False;self.deadline=time.monotonic()+10
        self.refuse=None;self.corrupt=False

    def call(self, operation, arguments):
        self.calls.append(operation)
        if operation==self.refuse:raise sdk.EvidenceError('Representative public CLI refused.', 'refused')
        return copy.deepcopy(self.fixture['calls'][operation])

    def close(self):
        pass

    def download(self, run_id, item, destination):
        self.calls.append('runs.artifact_chunk')
        raw=self.fixture['blobs'][item['name']]
        destination.write_bytes(raw+b'X' if self.corrupt else raw)


class SDKConformanceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        old=self.root/'original';old.mkdir()
        definition,model,composition,run,old_writer=authored_fixture(old)
        context=copy.deepcopy(run['extension_context']);static=context['static'];catalog=static['catalog_id']
        graph_id='4'*32;study_id='5'*32;trial_id='6'*32;approval_id='7'*32;actor='8'*32;project='9'*32
        selector = dict(project_id=project, recipe_id='scalar-a-canonical-v3', expected_sha256='a'*64)
        model['material'].update(kind='captured_source', source_selector=selector)
        # Actual graphs.get wire shape from the failed canonical A01 response,
        # with identities redacted. There is no top-level project_id.
        graph = dict(schema_version=1, mode='real', recipe='external_recipe', recipe_version=1,
            id=graph_id, revision=1, name='Representative public canonical graph', layout={},
            nodes=[dict(id='input', type='input', definition_version=1, parameters=dict(selector, inputs={
                'canonical':dict(kind='frozen_release', release_id='c'*64, expected_sha256='c'*64),
                'derivation':dict(reference_id='derivation', expected_sha256='d'*64),
                'provenance':dict(reference_id='provenance', expected_sha256='e'*64)})),
                dict(id='execute', type='execute', definition_version=1, parameters=dict(learning_rate=.1, updates=64)),
                dict(id='output', type='output', definition_version=1, parameters={})],
            edges=[{'from':'input','output':'data','to':'execute','input':'data'},
                   {'from':'execute','output':'artifacts','to':'output','input':'artifacts'}])
        material=dict(format='recipe_material_v1',catalog_id=catalog,recipe_id=graph_id,recipe_revision=1,
            recipe_document=dict(name='recipe.json',sha256='a'*64,bytes=1,media_type='application/json'),
            executable_sha256=static['execution_material_sha256'],model=static['model'],data=[],
            trainer=dict(kind='trainer',catalog_id=catalog,id='external_model_evidence_recipe_v1',revision=1,sha256='a'*64),
            evaluation_profile=static['profile']['definition'],resolved_profile=dict(name='profile.json',sha256='b'*64,bytes=1,media_type='application/json'),
            runtime=dict(kind='runtime',catalog_id=catalog,id='e'*64,sha256='e'*64),captures=[dict(name='capture-0000.bin',sha256='b'*64,bytes=1,media_type='application/octet-stream')],
            resource_envelope=dict(attempt_slots=1,admitted_wall_seconds=60,retained_bytes=1048576,peak_staging_bytes=2097152))
        material_sha=sdk.digest(material);ref=dict(kind='recipe_material',catalog_id=catalog,id=material_sha,sha256=material_sha)
        context['composition']=ref;self.context_raw=sdk.canonical(context)
        output=self.root/'produced';output.mkdir();writer=sdk.Evidence(output,self.context_raw)
        for name in ('transform.npy','input-initial.npy','reference.npy'):shutil.copyfile(old/name,output/name)
        writer.transform('transform.npy')
        for point in (16,32,48,64):
            for prefix in ('weights','prediction'):shutil.copyfile(old/f'{prefix}-{point}.npy',output/f'{prefix}-{point}.npy')
            writer.checkpoint(point,dict(optimizer_update=point,epoch=None,fit_pass=None,physical_time=None,wall_elapsed_ms=point),f'weights-{point}.npy',{'reference_mse':0})
        writer.finish();writer.write('diagnostics.json',{'scope':'representative structural transport; no real execution'})
        blobs={path.name:path.read_bytes() for path in output.iterdir()}
        manifest=json.loads(blobs['model-evidence.json'])
        public=dict(state='verified',validation='structural_and_identity_closure; numerical_acceptance_is_separate',
            manifest=manifest,checkpoint_index=json.loads(blobs['checkpoints.json']),probe=static['probe'],
            metric_definitions=static['policy']['metric_definitions'],observations=json.loads(blobs['observations.json']),
            model_definition=static['policy']['model_specification'],fields=[],
            metric_definition_hashes={item['id']:sdk.digest(item) for item in static['policy']['metric_definitions']},
            checkpoints=[json.loads(blobs[f'checkpoint-{point}.json']) for point in (16,32,48,64)])
        artifacts=[dict(name=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),locked=False,role='model_evidence',media_type='application/octet-stream') for name,raw in blobs.items()]
        current=dict(id=context['run_id'],dataset_id=catalog,actor_id=actor,approval_id=approval_id,approval_material_sha256=material_sha,
            material_sha256=material['executable_sha256'],study_membership=dict(study_id=study_id,trial_id=trial_id),state='completed',artifacts=artifacts)
        self.selection=dict(format='extension_sdk_conformance_selection_v1',catalog_id=catalog,actor_id=actor,project_id=project,study_id=study_id,trial_id=trial_id,
            revision=3,admission_epoch=1,approval_id=approval_id,request_key='explicit-conformance-001',expected=dict(graph_id=graph_id,graph_revision=1,
            material_sha256=material_sha,model_sha256=static['model']['sha256'],runtime_sha256='e'*64,task_sha256=static['task']['sha256'],profile_definition_sha256=static['profile']['definition']['sha256']))
        reservation={key:self.selection[key] for key in ('study_id','trial_id','admission_epoch','actor_id','request_key')}
        reservation.update(run_id=context['run_id'],material_sha256=material_sha,request_sha256=context['request_sha256'])
        self.fixture=dict(blobs=blobs,calls={
            'identity.get':dict(kind='agent',catalog_id=catalog,actor_id=actor,scopes=['inspect','execute']),
            'studies.get':dict(study=dict(id=study_id,revision=3,admission_epoch=1,open=True,state='open',trial_ids=[trial_id])),
            'studies.trial':dict(id=trial_id,study_id=study_id,material=ref),
            'recipes.material':dict(ref=ref,material=material),'models.material':model,
            'graphs.get':graph,
            'studies.admit':dict(reservation=reservation,run=current),'runs.get':current,'runs.model_evidence':public})
        self.output=self.root/'download';self.output.mkdir()

    def execute(self, transport=None):
        return _conformance(_selection(sdk.canonical(self.selection)),transport or RepresentativeTransport(self.fixture),self.output)

    def test_representative_contract_pass_is_separate_from_numerical_acceptance(self):
        client=RepresentativeTransport(self.fixture);result=self.execute(client)
        self.assertEqual(result['state'],'passed');self.assertEqual(result['numerical'],'not_evaluated')
        self.assertEqual(result['contract']['scope'],'common_d2_identity_and_whole_blob_closure')
        self.assertEqual(client.calls.count('studies.admit'),1)
        self.assertFalse(set(client.calls)&{'studies.continue','studies.create','studies.approve','runs.submit_external'})
        for name,raw in self.fixture['blobs'].items():self.assertEqual((self.output/name).read_bytes(),raw)

    def test_representative_graph_is_valid_in_the_real_public_graph_owner(self):
        from pipeline import decode_graph
        from recipe_contract import graph_parameters
        graph = decode_graph(copy.deepcopy(self.fixture['calls']['graphs.get']))
        config, parameters = graph_parameters(graph)
        self.assertNotIn('project_id', graph)
        self.assertEqual({key: config[key] for key in ('project_id', 'recipe_id', 'expected_sha256')},
                         self.fixture['calls']['models.material']['material']['source_selector'])
        self.assertEqual(parameters, {'learning_rate': .1, 'updates': 64})

    def test_graph_identity_shape_ambiguity_and_selector_drift_never_admit(self):
        mutations = [
            lambda g: g.update(id='0'*32), lambda g: g.update(revision=True),
            lambda g: g.update(recipe='image_classification_model_v2'), lambda g: g.update(mode='fixture'),
            lambda g: g.update(schema_version=True), lambda g: g.update(recipe_version=2),
            lambda g: g['nodes'].pop(0), lambda g: g['nodes'].append(copy.deepcopy(g['nodes'][0])),
            lambda g: g['nodes'][1].update(type='input'), lambda g: g['nodes'][1].update(id='input'),
            lambda g: g['nodes'][0].update(definition_version=True),
            lambda g: g['nodes'][0]['parameters'].update(project_id='0'*32),
            lambda g: g['nodes'][0]['parameters'].update(recipe_id='another-recipe'),
            lambda g: g['nodes'][0]['parameters'].update(expected_sha256='f'*64),
            lambda g: g['nodes'][0]['parameters'].update(inputs=[]),
            lambda g: g['nodes'][0]['parameters'].pop('project_id'),
            lambda g: g.update(project_id=self.selection['project_id']),
            lambda g: g['edges'][0].update(to='output'),
            lambda g: g.update(nodes=None),
        ]
        for mutation in mutations:
            fixture = copy.deepcopy(self.fixture); mutation(fixture['calls']['graphs.get'])
            client = RepresentativeTransport(fixture)
            with self.subTest(mutation=mutation), self.assertRaises(sdk.EvidenceError) as caught:
                self.execute(client)
            self.assertIn(caught.exception.state, ('invalid', 'unsupported', 'stale'))
            self.assertNotIn('studies.admit', client.calls)
            self.assertFalse(client.admission)
        fixture = copy.deepcopy(self.fixture)
        fixture['calls']['graphs.get'] = dict(id=self.selection['expected']['graph_id'], revision=1,
                                            project_id=self.selection['project_id'])
        client = RepresentativeTransport(fixture)
        with self.assertRaises(sdk.EvidenceError): self.execute(client)
        self.assertNotIn('studies.admit', client.calls)

    def test_source_selector_must_match_published_model_before_admission(self):
        for change in (lambda m: m.pop('source_selector'), lambda m: m.update(kind='template'),
                       lambda m: m['source_selector'].update(expected_sha256='f'*64)):
            fixture = copy.deepcopy(self.fixture); change(fixture['calls']['models.material']['material'])
            client = RepresentativeTransport(fixture)
            with self.subTest(change=change), self.assertRaises(sdk.EvidenceError) as caught:
                self.execute(client)
            self.assertEqual(caught.exception.state, 'stale')
            self.assertNotIn('studies.admit', client.calls)

    def test_valid_reordered_and_renamed_node_ids_keep_the_same_selector(self):
        graph = self.fixture['calls']['graphs.get']
        names = {'input':'source', 'execute':'fit', 'output':'evidence'}
        for node in graph['nodes']: node['id'] = names[node['id']]
        for edge in graph['edges']:
            edge['from'] = names[edge['from']]; edge['to'] = names[edge['to']]
        graph['nodes'].reverse(); graph['edges'].reverse()
        client = RepresentativeTransport(self.fixture)
        self.assertEqual(self.execute(client)['state'], 'passed')
        self.assertEqual(client.calls.count('studies.admit'), 1)

    def test_missing_grant_expected_identity_and_coerced_revision_refuse_before_dispatch(self):
        for change in (lambda s:s.pop('approval_id'),lambda s:s['expected'].pop('runtime_sha256'),lambda s:s.update(revision=True),lambda s:s.update(request_key='')):
            selection=copy.deepcopy(self.selection);change(selection)
            with self.subTest(change=change),self.assertRaises(sdk.EvidenceError):_selection(sdk.canonical(selection))

    def test_missing_scope_stale_revision_and_model_drift_never_admit(self):
        for change in (lambda f:f['calls']['identity.get'].update(scopes=['inspect']),
                       lambda f:f['calls']['studies.get']['study'].update(revision=4),
                       lambda f:f['calls']['recipes.material']['material']['model'].update(sha256='f'*64)):
            fixture=copy.deepcopy(self.fixture);change(fixture);client=RepresentativeTransport(fixture)
            with self.subTest(change=change),self.assertRaises(sdk.EvidenceError):self.execute(client)
            self.assertNotIn('studies.admit',client.calls)

    def test_revoked_grant_refuses_once_without_retry_or_creation(self):
        client=RepresentativeTransport(self.fixture);client.refuse='studies.admit'
        with self.assertRaises(sdk.EvidenceError) as caught:self.execute(client)
        self.assertEqual(caught.exception.state,'refused');self.assertEqual(client.calls.count('studies.admit'),1)
        self.assertNotIn('runs.get',client.calls)

    def test_revoked_read_after_admission_retains_run_identity_without_contract_pass(self):
        client=RepresentativeTransport(self.fixture);client.refuse='runs.model_evidence'
        with self.assertRaises(sdk.EvidenceError) as caught:self.execute(client)
        self.assertEqual(caught.exception.state,'refused');self.assertEqual(client.run_id,'1'*32)
        self.assertEqual(client.calls.count('studies.admit'),1);self.assertNotIn('runs.artifact_chunk',client.calls)

    def test_whole_download_hash_and_private_projection_cannot_be_substituted(self):
        client=RepresentativeTransport(self.fixture);client.corrupt=True
        with self.assertRaisesRegex(sdk.EvidenceError,'Whole artifact'):self.execute(client)
        self.assertEqual(client.calls.count('studies.admit'),1)
        changed=copy.deepcopy(self.fixture);changed['calls']['runs.model_evidence']['_arrays']={}
        other=self.root/'other';other.mkdir()
        with self.assertRaisesRegex(sdk.EvidenceError,'public verified'):_conformance(self.selection,RepresentativeTransport(changed),other)

    def test_incompatible_operation_and_active_deadline_have_no_fallback(self):
        client=RepresentativeTransport(self.fixture);client.refuse='recipes.material'
        with self.assertRaises(sdk.EvidenceError):self.execute(client)
        self.assertNotIn('studies.admit',client.calls)
        fixture=copy.deepcopy(self.fixture);fixture['calls']['studies.admit']['run']['state']='running'
        client=RepresentativeTransport(fixture);client.deadline=time.monotonic()-1
        with self.assertRaises(sdk.EvidenceError) as caught:self.execute(client)
        self.assertEqual(caught.exception.state,'unknown');self.assertEqual(client.run_id,'1'*32)
        self.assertEqual(client.calls.count('studies.admit'),1)

    def test_machine_refusals_and_unknown_acknowledgement_never_claim_contract_pass(self):
        selection_file=self.root/'selection.json';selection_file.write_bytes(sdk.canonical(self.selection))
        for kind in ('scope','revoked','malformed_ack'):
            fixture=copy.deepcopy(self.fixture);client=RepresentativeTransport(fixture)
            if kind=='scope':fixture['calls']['identity.get']['scopes']=['inspect']
            elif kind=='revoked':client.refuse='studies.admit'
            else:fixture['calls']['studies.admit']={}
            output=io.StringIO()
            with self.subTest(kind=kind),patch('tuldok_extension_sdk.__main__._CLI',return_value=client),redirect_stdout(output):
                status=main(['conformance','--config','explicit-config','--cli','explicit-cli','--cli-sha256','a'*64,
                    '--selection',str(selection_file),'--output',str(self.root/('machine-'+kind))])
            result=json.loads(output.getvalue());self.assertEqual(status,2)
            self.assertEqual(result['state'],'unknown' if kind=='malformed_ack' else 'refused')
            self.assertEqual(result['contract']['state'],'not_evaluated');self.assertEqual(result['numerical'],'not_evaluated')
            self.assertLessEqual(client.calls.count('studies.admit'),1)

    def cli_client(self, source):
        path=self.root/'selected_cli.py';path.write_text(source)
        config=self.root/'explicit-config.json';config.write_text('{}');config.chmod(0o600)
        client=_CLI(SimpleNamespace(cli=str(path),config=str(config),cli_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),deadline_seconds=20))
        self.addCleanup(client.close)
        return client,path

    def test_selected_cli_entry_bytes_remain_immutable_after_path_replacement(self):
        client,path=self.cli_client("print('{\"original_checked_bytes\":true}')")
        path.write_text("print('{\"substituted_after_hash\":true}')")
        with self.assertRaises(OSError): os.write(client.entry_fd,b'x')
        self.assertEqual(client.call('identity.get',{}),{'original_checked_bytes':True})

    def test_stdout_stderr_floods_are_stopped_during_bounded_drain(self):
        for descriptor in (1,2):
            client,_path=self.cli_client(f"import os\nwhile True:os.write({descriptor},b'x'*65536)")
            started=time.monotonic()
            with self.subTest(descriptor=descriptor),self.assertRaisesRegex(sdk.EvidenceError,'result bound'):
                client.call('identity.get',{})
            self.assertLess(time.monotonic()-started,10)
            client.close()

    def test_inflight_cli_timeout_is_unknown_without_retry(self):
        client,_path=self.cli_client('import time;time.sleep(5)')
        client.deadline=time.monotonic()+.1
        with self.assertRaises(sdk.EvidenceError) as caught:
            client._run(['call','--operation','studies.admit','--arguments','explicit.json'],mutation=True)
        self.assertEqual(caught.exception.state,'unknown')

    def test_standalone_command_delegates_only_explicit_trusted_cli_fixed_argv(self):
        kit=self.root/'kit';kit.mkdir()
        for source in ('tuldok_extension_sdk','extension_schemas'):shutil.copytree(ROOT/source,kit/source,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(ROOT/'extension_contract.py',kit/'extension_contract.py')
        cli=self.root/'representative_cli.py';cli.write_text(REPRESENTATIVE_CLI)
        config=self.root/'representative-transport.json';config.write_text(json.dumps(dict(calls=self.fixture['calls'],blobs={key:base64.b64encode(raw).decode() for key,raw in self.fixture['blobs'].items()})));config.chmod(0o600)
        selection=self.root/'selection.json';selection.write_bytes(sdk.canonical(self.selection))
        output=self.root/'command-output'
        command=[sys.executable,'-E','-B','-m','tuldok_extension_sdk','conformance','--config',str(config),'--cli',str(cli),
            '--cli-sha256',hashlib.sha256(cli.read_bytes()).hexdigest(),'--selection',str(selection),'--output',str(output)]
        result=subprocess.run(command,cwd=kit,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        value=json.loads(result.stdout);self.assertEqual(value['state'],'passed');self.assertEqual(value['numerical'],'not_evaluated')
        self.assertFalse((kit/'app.py').exists());self.assertFalse((kit/'agent_api.py').exists())
        bad=command.copy();bad[bad.index('--cli-sha256')+1]='f'*64;bad[bad.index('--output')+1]=str(self.root/'not-created')
        result=subprocess.run(bad,cwd=kit,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2);self.assertEqual(json.loads(result.stdout)['state'],'stale')
        self.assertFalse((self.root/'not-created').exists())
