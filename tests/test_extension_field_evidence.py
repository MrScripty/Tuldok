"""Structural/context negative witnesses; synthetic states are not model qualification."""
import copy
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import extension_evidence as evidence
import recipe_contract
import recipe_process
from workbench import WorkbenchError

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'examples/extensions/field-surrogate/v2'


def npy(values,shape):
    header=repr({'descr':'<f8','fortran_order':False,'shape':tuple(shape)}).encode('ascii')
    header+=b' '*((-(10+len(header)+1))%16)+b'\n'
    return b'\x93NUMPY\x01\x00'+struct.pack('<H',len(header))+header+struct.pack('<'+'d'*len(values),*values)


def authored_fixture(root):
    """Build explicit synthetic D2 bytes, never invoke the numerical producer."""
    definition=recipe_contract.decode_definition((PACKAGE/'recipe.json').read_bytes())
    policy=definition['model_evidence'];catalog='d'*32
    task={'kind':'task','catalog_id':catalog,'id':policy['task']['id'],'revision':policy['task']['revision'],'sha256':evidence.digest(policy['task']['definition'])}
    model={'ref':{'kind':'model','catalog_id':catalog,'id':'a'*32,'revision':1,'sha256':'b'*64},
           'material':{'task':task,**{key:{'sha256':evidence.digest(policy[policy_key])} for key,policy_key in
            [('specification','model_specification'),('preprocessing_policy','preprocessing_policy'),('output_policy','output_policy')]}}}
    fixture_raw=(PACKAGE/'fixture.json').read_bytes();fixture=json.loads(fixture_raw)
    receipt={'project_id':'e'*32,'manifest_sha256':'f'*64,'reference_id':'fixture','path':'fixture.json','measured_sha256':hashlib.sha256(fixture_raw).hexdigest()}
    execution={'catalog_id':catalog,'recipe':definition,'inputs':{'fixture':receipt},'parameters':recipe_contract.validate_parameters(definition,{})}
    static=evidence.resolve(policy,model,execution)
    composition={'ref':{'kind':'recipe_material','catalog_id':catalog,'id':'c'*64,'sha256':'c'*64},
                 'material':{'model':model['ref'],'executable_sha256':evidence.digest(execution)}}
    run={'id':'1'*32,'dataset_id':catalog,'request_sha256':'2'*64,'material':execution,
         'material_sha256':evidence.digest(execution),'approval_material_sha256':'c'*64,'outputs':definition['outputs']}
    context=evidence.context(static,composition['ref'],run['id'],run['request_sha256'])
    context_raw=evidence.canonical(context)
    run.update(extension_context=context,spec={'model_evidence_context':{'path':'/synthetic/runtime-bootstrap/model-evidence-context.json',
                'bytes':len(context_raw),'sha256':hashlib.sha256(context_raw).hexdigest()}})
    # Explicitly invoke only the author's JSON writer in this structural fixture.
    spec=importlib.util.spec_from_file_location('authored_evidence_writer',PACKAGE/'evidence_writer.py')
    writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer)
    instance=writer.Evidence(root,context_raw)
    (root/'transform.npy').write_bytes(npy([0,1],[2]));instance.transform('transform.npy')
    member=next(row for row in fixture['cases'] if row['id']==fixture['probe_member_id'])
    (root/'input-initial.npy').write_bytes(npy(member['initial'],[4,4,4]))
    (root/'reference.npy').write_bytes(npy(member['target'],[4,4,4]))
    for point in (16,32,48,64):
        (root/f'weights-{point}.npy').write_bytes(npy([0,0],[2]))
        (root/f'prediction-{point}.npy').write_bytes(npy(member['target'],[4,4,4]))
        instance.checkpoint(point,{'optimizer_update':point,'epoch':None,'fit_pass':None,'physical_time':None,'wall_elapsed_ms':point},
                            f'weights-{point}.npy',{'reference_mse':0})
    instance.finish();instance.write('diagnostics.json',{'scope':'synthetic structural state, no training'})
    run['artifacts']=[{'name':row['path'],'role':row['role'],'bytes':(root/row['path']).stat().st_size,
                       'sha256':hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),'media_type':'application/octet-stream'}
                      for row in definition['outputs']]
    return definition,model,composition,run,instance


class ExtensionEvidenceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.definition,self.model,self.composition,self.run,self.writer=authored_fixture(self.root)
        self.policy=self.definition['model_evidence']

    def verify(self):return evidence.verify(self.root,self.run,self.run['extension_context'])

    def test_verification_stops_at_payload_and_field_boundaries(self):
        import field_evidence
        for phase, code in (('payload', 'cancelled'), ('field', 'unavailable')):
            with self.subTest(phase=phase):
                stopped = []
                def guard():
                    if stopped:
                        raise WorkbenchError('Authored verification stop', code, 409)
                original = evidence.read_regular if phase == 'payload' else field_evidence.validate_pair
                calls = []
                def stop_after_first(*args, **kwargs):
                    calls.append(True)
                    self.assertEqual(len(calls), 1, 'Verification continued after stop')
                    value = original(*args, **kwargs)
                    stopped.append(True)
                    return value
                target = 'extension_evidence.read_regular' if phase == 'payload' else 'field_evidence.validate_pair'
                with patch(target, side_effect=stop_after_first):
                    with self.assertRaises(WorkbenchError) as caught:
                        evidence.verify(self.root, self.run, self.run['extension_context'], checkpoint=guard)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(len(calls), 1)

    def test_exact_field_comparison_uses_authoritative_policies_and_geometry(self):
        verified = self.verify(); context = self.run['extension_context']
        selected = verified['checkpoint_index']['entries'][0]['checkpoint']['sha256']
        metric = verified['metric_definitions'][0]
        selection = {'checkpoint_sha256': selected, 'other_checkpoint_sha256': selected,
            'evaluation_sha256': hashlib.sha256((self.root / 'model-evidence.json').read_bytes()).hexdigest(),
            'other_evaluation_sha256': hashlib.sha256((self.root / 'model-evidence.json').read_bytes()).hexdigest(),
            'metric_id': metric['id'], 'metric_definition_sha256': evidence.digest(metric),
            'other_metric_definition_sha256': evidence.digest(metric), 'mode': 'paired'}
        compared = evidence.compare([verified, verified], [context, context], selection)
        self.assertEqual(compared['state'], 'compatible')
        self.assertEqual(compared['delta'], {'state': 'observed', 'value': 0, 'units': metric['units']})
        # These are structural synthetic states, never a numerical acceptance.
        changed = copy.deepcopy(context)
        changed['static']['policy']['fields'][0]['geometry']['origin_xyz'][0] += 1
        refused = evidence.compare([verified, verified], [context, changed], selection)
        self.assertEqual(refused['state'], 'incompatible'); self.assertIsNone(refused['delta'])
        self.assertIn('Field contracts, geometry or gauge semantics differ.', refused['reasons'])
        wrong = dict(selection, metric_definition_sha256='f' * 64)
        with self.assertRaises(WorkbenchError): evidence.compare([verified, verified], [context, context], wrong)

    def refresh_synthetic_host_inventory(self):
        """Explicit synthetic prepublication hash snapshot, never an admitted Run."""
        for item in self.run['artifacts']:
            raw=(self.root/item['name']).read_bytes()
            item.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

    def rewrite(self,name,value):
        (self.root/name).write_bytes(evidence.canonical(value)+b'\n')

    def rehash(self,name,manifest_key):
        manifest=json.loads((self.root/'model-evidence.json').read_bytes())
        manifest[manifest_key]=self.writer.blob(name)
        self.rewrite('model-evidence.json',manifest)

    def test_closed_d2_structure_and_exact_bounded_query_without_loading_state(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Decoder/query must not execute')):
            verified=self.verify();public=evidence.query(verified)
            self.assertEqual(public['state'],'verified');self.assertNotIn('_arrays',public)
            entries=public['checkpoint_index']['entries']
            self.assertEqual([entry['clocks']['optimizer_update'] for entry in entries],[16,32,48,64])
            # Identical synthetic weight bytes at distinct actual clock coordinates remain distinct descriptors.
            self.assertEqual(len({entry['checkpoint']['sha256'] for entry in entries}),4)
            result=evidence.query(verified,{'checkpoint_sha256':entries[0]['checkpoint']['sha256'],
                'member_ordinal':0,'field_id':'raw','axis':'y','index':2})['field']
            self.assertEqual(result['prediction'],result['reference'])
            self.assertEqual((result['row_axis'],result['column_axis']),('z','x'))
            self.assertEqual(result['physical_origin'],[.5,2.5,.5])
            self.assertEqual(result['gauge_policy'],self.policy['fields'][0]['gauge_policy'])
            self.assertEqual(result['gauge_policy_sha256'],evidence.digest(result['gauge_policy']))
            self.assertEqual(result['time_units'],'not_applicable')

    def test_actual_decoder_reads_bind_host_inventory_after_any_prior_hash_pass(self):
        # A prior host hashing pass is insufficient: forge a coherent worker
        # bundle after it and keep the original authoritative Run inventory.
        self.verify()
        path=self.root/'prediction-16.npy';raw=path.read_bytes()
        path.write_bytes(raw[:-8]+struct.pack('<d',123.0))
        index=json.loads((self.root/'field-index.json').read_bytes())
        index[0]['cases'][0]['predicted']=self.writer.blob('prediction-16.npy')
        self.rewrite('field-index.json',index);self.rehash('field-index.json','field_index')
        with self.assertRaisesRegex(WorkbenchError,'authoritative retained artifact'):
            self.verify()

    def test_decoder_retains_one_root_and_refuses_directory_replacement_after_first_read(self):
        original=evidence.read_regular;first=True;moved=self.root.with_name(self.root.name+'-held')
        self.addCleanup(lambda:shutil.rmtree(moved,ignore_errors=True))
        def read(*args,**kwargs):
            nonlocal first
            raw=original(*args,**kwargs)
            if first:
                first=False;self.root.rename(moved);self.root.mkdir()
            return raw
        with patch.object(evidence,'read_regular',side_effect=read),self.assertRaisesRegex(WorkbenchError,'directory identity changed'):
            self.verify()

    def test_file_reader_refuses_changed_current_root_or_filename(self):
        for variant in ('root','file'):
            with tempfile.TemporaryDirectory() as outer:
                root=Path(outer)/'live';root.mkdir();(root/'data.json').write_bytes(b'{}')
                original=os.read;first=True
                def read(fd,count):
                    nonlocal first
                    raw=original(fd,count)
                    if first:
                        first=False
                        if variant=='root':root.rename(Path(outer)/'held');root.mkdir()
                        else:(root/'data.json').rename(root/'held.json')
                        (root/'data.json').write_bytes(b'{}')
                    return raw
                with self.subTest(variant=variant),patch('os.read',side_effect=read),self.assertRaises(WorkbenchError):
                    evidence.read_regular(root,'data.json',100)

    def test_wrong_context_model_profile_task_attempt_and_spec_refuse(self):
        for change in (
            lambda c:c.update(run_id='3'*32),lambda c:c.update(request_sha256='4'*64),
            lambda c:c['static']['model'].update(sha256='5'*64),lambda c:c['static']['profile'].update(model_sha256='6'*64),
            lambda c:c['static']['task'].update(sha256='7'*64),lambda c:c['composition'].update(sha256='8'*64)):
            value=copy.deepcopy(self.run['extension_context']);change(value)
            with self.subTest(change=change),self.assertRaises(WorkbenchError):evidence.verify(self.root,self.run,value)
        changed=copy.deepcopy(self.run);changed['spec']['model_evidence_context']['sha256']='9'*64
        with self.assertRaises(WorkbenchError):evidence.verify(self.root,changed,changed['extension_context'])
        with self.assertRaises(WorkbenchError):evidence.validate_context(self.run['extension_context'],self.run,self.composition,
            dict(self.run['extension_context']['static'],model={'kind':'model'}))

    def test_every_input_receipt_kind_is_checked_even_when_not_referenced(self):
        execution=copy.deepcopy(self.run['material'])
        execution['recipe']['inputs']['unused']={'max_bytes':65536}
        for kind in ('run_artifact','frozen_release',None):
            execution['inputs']['unused']={'kind':kind}
            with self.subTest(kind=kind),self.assertRaisesRegex(WorkbenchError,'including unused inputs'):
                evidence.resolve(execution['recipe']['model_evidence'],self.model,execution)

    def test_closed_malformed_policy_and_declared_input_shape_refuse_typed(self):
        for change in (lambda p:p['probe'].update(data_input={}),lambda p:p['field_outputs'][0].update(field_id=[]),
                       lambda p:p['fields'][0]['contract']['inputs'][0].update(shape_zyx=[3,3,3]),
                       lambda p:p['fields'][0]['contract']['adapter'].update(version=2**53),
                       lambda p:p['fit_members'][0].update(split='validation'),
                       lambda p:p['probe']['candidates'][0]['frozen_reference'].update(split='test')):
            value=copy.deepcopy(self.definition);change(value['model_evidence'])
            with self.subTest(change=change),self.assertRaises(WorkbenchError):recipe_contract.decode_definition(evidence.canonical(value))

    def test_required_missing_symlink_hardlink_and_duplicate_json_refuse(self):
        for name in ('weights-16.npy','profile.json','input-initial.npy','reference.npy'):
            source=self.root/name;raw=source.read_bytes();source.unlink()
            with self.subTest(name=name),self.assertRaises(WorkbenchError):self.verify()
            source.write_bytes(raw)
        path=self.root/'reference.npy';raw=path.read_bytes();outside=self.root.parent/(self.root.name+'-outside.npy')
        outside.write_bytes(raw);self.addCleanup(outside.unlink)
        path.unlink();path.symlink_to(outside)
        with self.assertRaises(WorkbenchError):self.verify()
        path.unlink();os.link(outside,path)
        with self.assertRaises(WorkbenchError):self.verify()
        path.unlink();path.write_bytes(raw)
        (self.root/'profile.json').write_bytes(b'{"x":1,"x":2}')
        with self.assertRaises(WorkbenchError):self.verify()

    def test_changed_reference_with_all_worker_hashes_rewritten_still_refuses(self):
        path=self.root/'reference.npy';raw=path.read_bytes();path.write_bytes(raw[:-8]+struct.pack('<d',42))
        index=json.loads((self.root/'field-index.json').read_bytes())
        for group in index:group['cases'][0]['reference']=self.writer.blob('reference.npy')
        self.rewrite('field-index.json',index);self.rehash('field-index.json','field_index')
        self.refresh_synthetic_host_inventory()
        with self.assertRaisesRegex(WorkbenchError,'admitted target'):self.verify()

    def test_changed_probe_input_with_updated_file_integrity_still_refuses(self):
        path=self.root/'input-initial.npy';raw=path.read_bytes();path.write_bytes(raw[:-8]+struct.pack('<d',42))
        self.refresh_synthetic_host_inventory()
        with self.assertRaisesRegex(WorkbenchError,'admitted identity'):self.verify()

    def test_field_order_stage_gauge_shape_clock_and_member_negatives(self):
        original=(self.root/'field-index.json').read_bytes()
        for change in (lambda v:v[0]['cases'][0].update(member_ordinal=True),
                       lambda v:v[0]['cases'][0].update(gauge_policy_sha256='0'*64),
                       lambda v:v[0]['cases'][0].update(geometry_sha256='0'*64),
                       lambda v:v[0].update(checkpoint_sha256='0'*64),
                       lambda v:v[0]['cases'][0].update(predicted=self.writer.blob('prediction-32.npy')),
                       lambda v:v[0]['cases'][0].update(time_units='s')):
            value=json.loads(original);change(value);self.rewrite('field-index.json',value);self.rehash('field-index.json','field_index')
            with self.subTest(change=change),self.assertRaises(WorkbenchError):self.verify()
        (self.root/'field-index.json').write_bytes(original);self.rehash('field-index.json','field_index')
        index=json.loads((self.root/'checkpoints.json').read_bytes());index['entries'][0]['clocks']['optimizer_update']=17
        self.rewrite('checkpoints.json',index);self.rehash('checkpoints.json','checkpoints')
        with self.assertRaises(WorkbenchError):self.verify()

    def test_untrusted_nested_blob_and_observation_shapes_fail_typed(self):
        original=(self.root/'model-evidence.json').read_bytes()
        for key,value in (('checkpoints',[]),('field_index',{}),('probe',None),('observations',[{}])):
            manifest=json.loads(original);manifest[key]=value;self.rewrite('model-evidence.json',manifest)
            with self.subTest(key=key),self.assertRaises(WorkbenchError):self.verify()
        (self.root/'model-evidence.json').write_bytes(original)
        rows=json.loads((self.root/'observations.json').read_bytes());rows[0]['checkpoint_sha256']={}
        self.rewrite('observations.json',rows)
        manifest=json.loads(original);manifest['observations']=[self.writer.blob('observations.json')];self.rewrite('model-evidence.json',manifest)
        with self.assertRaises(WorkbenchError):self.verify()

    def test_copied_clock_and_task_json_type_aliases_do_not_match(self):
        descriptor=json.loads((self.root/'checkpoint-16.json').read_bytes())
        descriptor['clocks']['optimizer_update']=16.0
        self.rewrite('checkpoint-16.json',descriptor)
        index=json.loads((self.root/'checkpoints.json').read_bytes())
        index['entries'][0]['checkpoint']=self.writer.blob('checkpoint-16.json')
        self.rewrite('checkpoints.json',index);self.rehash('checkpoints.json','checkpoints')
        with self.assertRaises(WorkbenchError):self.verify()

    def test_exact_policy_documents_reject_integer_float_alias(self):
        profile=json.loads((self.root/'profile.json').read_bytes());profile['probe_selection']['seed']=0.0
        self.rewrite('profile.json',profile)
        with self.assertRaises(WorkbenchError):self.verify()

    def test_exact_task_ref_rejects_float_revision(self):
        manifest=json.loads((self.root/'model-evidence.json').read_bytes());manifest['task']['revision']=2.0
        self.rewrite('model-evidence.json',manifest)
        with self.assertRaises(WorkbenchError):self.verify()

    def test_independent_oracle_refuses_synthetic_zero_state_even_with_exact_targets(self):
        spec=importlib.util.spec_from_file_location('independent_scalar_oracle',PACKAGE/'cold_oracle.py')
        oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
        with self.assertRaises(oracle.OracleError):
            oracle.qualify(PACKAGE/'fixture.json',self.root,self.run['spec']['model_evidence_context']['sha256'])

    def test_test_unknown_or_incomplete_selectors_do_not_project(self):
        verified=self.verify();checkpoint=verified['checkpoint_index']['entries'][0]['checkpoint']['sha256']
        for selectors in ({'split':'test'},{'checkpoint_sha256':'0'*64},
                          {'checkpoint_sha256':checkpoint,'member_ordinal':0},
                          {'checkpoint_sha256':checkpoint,'member_ordinal':True,'field_id':'raw','axis':'z','index':0},
                          {'checkpoint_sha256':checkpoint,'member_ordinal':0,'field_id':'raw','axis':'z','index':4},
                          {'checkpoint_sha256':checkpoint,'member_ordinal':0,'field_id':'other','axis':'z','index':0}):
            with self.subTest(selectors=selectors),self.assertRaises(WorkbenchError):evidence.query(verified,selectors)


class ContextCaptureTests(unittest.TestCase):
    def test_explicit_versions_and_legacy_argument_domain(self):
        from test_recipe_contract import definition
        legacy=definition();self.assertEqual(recipe_contract.decode_definition(evidence.canonical(legacy)),legacy)
        legacy['arguments'].append({'model_evidence_context':True})
        with self.assertRaises(WorkbenchError):recipe_contract.decode_definition(evidence.canonical(legacy))
        current=json.loads((PACKAGE/'recipe.json').read_bytes())
        for change in (lambda v:v.update(schema_version=1),lambda v:v.update(format='external_recipe_v1'),
                       lambda v:v['arguments'].pop(1),lambda v:v['arguments'].append({'model_evidence_context':True})):
            value=copy.deepcopy(current);change(value)
            with self.subTest(change=change),self.assertRaises(WorkbenchError):recipe_contract.decode_definition(evidence.canonical(value))
        self.assertEqual(evidence.CONTEXT_PATH,recipe_contract.EVIDENCE_CONTEXT)
        self.assertEqual(evidence.CONTEXT_PATH,recipe_process.MODEL_CONTEXT_PATH)
        self.assertEqual(evidence.MAX_CONTEXT_BYTES,recipe_process.MODEL_CONTEXT_LIMIT)

    def test_spec2_context_is_explicit_exact_inventory_and_argument_only(self):
        # This is a static descriptor/spec grammar fixture, never installed or launched.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bootstrap=root/'runtime-bootstrap';raw=b'{}'
            descriptor={'schema_version':1,'profile':'captured_cpu_python_v1','catalog_id':'d'*32,
                'root':str(root/'runtime-snapshots'/('a'*64)),'manifest_sha256':'a'*64,'manifest_bytes':1000,
                'file_count':10,'total_bytes':10000,'python_version':'3.12','packages':{'numpy':'2.3.5','torch':'2.8.0+cpu'},
                'launch':{'python':'python/bin/python3.12','loader':'system/lib/ld-linux-x86-64.so.2',
                'home':'python','stdlib':'python/lib/python3.12','dynload':'python/lib/python3.12/lib-dynload',
                'packages':'packages','library_dirs':['system/lib']}}
            context={'path':str(root/evidence.CONTEXT_PATH),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            def item(path,content):return {'path':str(path),'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
            spec={'schema_version':2,'attempt_id':'1'*32,'request_sha256':'2'*64,
                'argv':[str(Path('/usr/bin/python3').resolve()),'-I','-S','-B',str(bootstrap/'recipe_process.py'),
                    '--cpu-launch',str(bootstrap/'snapshot.json'),str(root/'source/producer.py'),context['path']],
                'env':{},'cwd':str(root),'stdin_base64':'','wall_seconds':60,'executable_sha256':'3'*64,
                'max_output_bytes':1048576,'output_dir':str(root/'output'),'trusted_install_owner_uid':os.stat('/usr').st_uid,
                'captured_files':[item(bootstrap/'recipe_process.py',b'static bootstrap placeholder'),
                    item(bootstrap/'snapshot.json',recipe_process.encoded(descriptor)),item(root/'source/producer.py',b'static source placeholder'),context],
                'runtime_files':[],'native_loader_policy':'glibc_x86_64_no_preload_v1','cpu_snapshot':descriptor,
                'model_evidence_context':context}
            self.assertEqual(recipe_process.validate_spec(spec),spec)
            for change in (lambda v:v.update(schema_version=1),lambda v:v.update(model_evidence_context=None),
                           lambda v:v['argv'].append(context['path']),lambda v:v['captured_files'].pop(),
                           lambda v:v['model_evidence_context'].update(bytes=True),lambda v:v.pop('cpu_snapshot')):
                value=copy.deepcopy(spec);change(value)
                with self.subTest(change=change),self.assertRaises(recipe_process.ProcessError):recipe_process.validate_spec(value)

    def test_context_refuses_current_root_child_or_filename_replacement(self):
        for variant in ('root','child','file'):
            with tempfile.TemporaryDirectory() as outer:
                root=Path(outer)/'live';path=root/evidence.CONTEXT_PATH;path.parent.mkdir(parents=True)
                raw=b'{}';path.write_bytes(raw);path.chmod(0o400)
                spec={'schema_version':2,'cwd':str(root),'model_evidence_context':
                    {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}
                original=os.read;first=True
                def read(fd,count):
                    nonlocal first
                    content=original(fd,count)
                    if first:
                        first=False
                        if variant=='root':root.rename(Path(outer)/'held');path.parent.mkdir(parents=True)
                        elif variant=='child':path.parent.rename(root/'held');path.parent.mkdir()
                        else:path.rename(path.with_name('held.json'))
                        path.write_bytes(raw);path.chmod(0o400)
                    return content
                with self.subTest(variant=variant),patch('os.read',side_effect=read),self.assertRaises(recipe_process.ProcessError):
                    recipe_process.verify_model_context(spec)

    def test_context_file_is_exact_readonly_owned_and_not_a_hardlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/evidence.CONTEXT_PATH;path.parent.mkdir();raw=b'{"fixture":"structural only"}'
            path.write_bytes(raw);path.chmod(0o400)
            spec={'schema_version':2,'cwd':str(root),'model_evidence_context':{'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}
            recipe_process.verify_model_context(spec)
            path.chmod(0o600)
            with self.assertRaises(recipe_process.ProcessError):recipe_process.verify_model_context(spec)
            path.chmod(0o400);link=root/'alias';os.link(path,link)
            with self.assertRaises(recipe_process.ProcessError):recipe_process.verify_model_context(spec)
            link.unlink();path.chmod(0o600);path.write_bytes(b'X'*len(raw));path.chmod(0o400)
            with self.assertRaises(recipe_process.ProcessError):recipe_process.verify_model_context(spec)
            # Legacy capture verification gains no file/path/context requirement.
            recipe_process.verify_model_context({'schema_version':1})


if __name__=='__main__':unittest.main()
@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class RetainedExtensionRecordTests(unittest.TestCase):
    def test_actual_preflight_rejects_unused_run_input_before_capture_or_runtime(self):
        from test_external_runs import ExternalCase
        case=ExternalCase(methodName='runTest');self.addCleanup(case.doCleanups);case.setUp()
        for source in PACKAGE.iterdir():
            if source.is_file():shutil.copyfile(source,case.project_path/source.name)
        definition=json.loads((case.project_path/'recipe.json').read_bytes())
        definition['inputs']['unused']={'max_bytes':65536}
        raw=evidence.canonical(definition);(case.project_path/'recipe.json').write_bytes(raw)
        manifest=json.loads((case.project_path/'project.json').read_bytes())
        manifest['recipes'][0]['sha256']=hashlib.sha256(raw).hexdigest()
        (case.project_path/'project.json').write_bytes(evidence.canonical(manifest))
        with case.owner.bound(case.dataset):
            case.dataset.projects.open({'root':'fixture','manifest_path':'project.json'})
            graph=case.dataset.pipelines.create_external({'name':'Unsupported unused input negative',
                'project_id':manifest['id'],'recipe_id':manifest['recipes'][0]['id'],'expected_sha256':hashlib.sha256(raw).hexdigest(),
                'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':hashlib.sha256((PACKAGE/'fixture.json').read_bytes()).hexdigest()},
                          'unused':{'kind':'run_artifact','run_id':'f'*32,'artifact_name':'unused.npy','expected_sha256':'e'*64}}})
            with patch.object(case.dataset.runs,'capture_artifact',side_effect=AssertionError('Unsupported receipt reached capture')),                    patch('runtime_snapshots.RuntimeSnapshots.get',side_effect=AssertionError('Unsupported receipt reached runtime')):
                with self.assertRaisesRegex(WorkbenchError,'including unused inputs'):
                    case.dataset.pipelines.preflight_external(graph['id'],graph['revision'])
            for table in ('workspace_runs','access_execution_consumptions','access_execution_grants'):
                self.assertEqual(case.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_malformed_retained_material_refuses_through_actual_run_loader(self):
        from test_external_runs import ExternalCase
        from workbench import encode
        case=ExternalCase(methodName='runTest');self.addCleanup(case.doCleanups);case.setUp()
        queued=case.queued(case.body(approval=case.approve()))
        with case.owner.bound(case.dataset),case.dataset.lock:
            self.assertEqual(case.dataset.runs.model_evidence(queued['id'],{'split':'validation'},contract_version=2)['state'],'unsupported')
            with self.assertRaises(WorkbenchError):case.dataset.runs.model_evidence(queued['id'],{'split':'validation'},contract_version=1)
            row=case.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(queued['id'],)).fetchone()
            original=json.loads(row[0])
            for material in ([],None,{'recipe':[]},{'recipe':None}):
                changed=dict(original,material=material)
                with case.dataset.db.transaction():
                    case.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(encode(changed),queued['id']))
                try:
                    with self.subTest(material=material),self.assertRaises(WorkbenchError) as refused:
                        case.dataset.runs._load(queued['id'])
                    self.assertEqual(refused.exception.code,'unavailable')
                finally:
                    with case.dataset.db.transaction():
                        case.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',(encode(original),queued['id']))
