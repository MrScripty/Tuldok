"""Finite native phase evidence and original-host custody; no imported launch."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
import recipe_process
from pipeline import adapter_identity_for_graph, digest
from project_artifacts import ProjectArtifacts
from project_custody import ProjectCustody, NATIVE_PHASE_LIMIT, validate as validate_custody
from project_native_execution import ProjectNativeExecution, decode_records, phase_reference, classify_probe, OBSERVATIONS, FORMAT, FAMILY
from project_native_process import prepare
from project_session import ProjectSessionError
from project_store import ProjectStore
from workbench import WorkbenchError
import test_project_native_preparation as preparation_fixture
import test_project_study_execution as study_fixture
import test_project_files_http as http_fixture


class NativePhaseCodecs(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-native-phase-')
        self.addCleanup(self.temporary.cleanup);self.path=Path(self.temporary.name)
        self.store=ProjectStore.create(self.path/'project','Native phase fixture','new-native-phase','a'*64)
        self.addCleanup(self.store.close)
        self.artifacts=ProjectArtifacts(self.store);self.addCleanup(self.artifacts.close)
        self.project=self.store.snapshot()['project_id'];self.phase=uuid.uuid4().hex
        executable=str(Path('/usr/bin/python3').resolve())
        raw=Path(executable).read_bytes();self.source=b'print("inert codec fixture")\n'
        self.prepared=prepare(self.path/'phase',phase='probe',attempt_id=self.phase,request_sha256='b'*64,
            runtime=dict(executable=executable,executable_sha256=hashlib.sha256(raw).hexdigest(),
                trusted_install_owner_uid=os.stat('/usr').st_uid,
                files={executable:dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))}),
            worker='text_training.py',sources={'text_training.py':self.source})
        definition={'text_training.py':hashlib.sha256(self.source).hexdigest()}
        self.document=dict(format=FORMAT,origin_catalog_id=self.project,phase_id=self.phase,
            phase='probe',run_id=None,recipe='text_classification',request_key='native-phase-fixture',
            request_sha256='b'*64,actor_id='c'*32,
            definition_identity=dict(definition_files=definition,adapter_definition_sha256=digest(definition)),
            spec=self.prepared.spec,events=[self.event('prepared')],payloads=[],
            observations=dict.fromkeys(OBSERVATIONS),probe_result=None)
        self.payload('spec.json',recipe_process.encoded(self.prepared.spec),'execution_spec')
        self.payload('source/text_training.py',self.source,'execution_source')

    @staticmethod
    def event(state,helper=None,receipt_sha256=None):
        return dict(state=state,at='2026-10-22T12:00:00+00:00',actor_id='c'*32,helper=helper,receipt_sha256=receipt_sha256)

    def payload(self,name,raw,role):
        blob=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        self.artifacts.publish_bytes(raw,dict(format='project_artifact_v1',**blob))
        self.document['payloads'].append(dict(name=name,blob=blob,role=role,
            preservation='unique',required_for=['execution_proof']))
        for key,(filename,maximum) in OBSERVATIONS.items():
            if name==filename:
                if key=='probe_stdout':self.document['probe_result']=classify_probe(self.document['recipe'],raw)
                try:self.document['observations'][key]=raw.decode('utf8') if len(raw)<=maximum else None
                except UnicodeError:self.document['observations'][key]=None
        return blob

    def records(self):
        return [dict(family=FAMILY,id=self.project+'.'+self.phase,document=copy.deepcopy(self.document)),
            *[dict(family='project_artifact',id=edge['blob']['sha256'],
                   document=dict(format='project_artifact_v1',**edge['blob'])) for edge in self.document['payloads']]]

    def completed(self,stdout=None):
        helper=recipe_process.identity(os.getpid())
        stdout=stdout if stdout is not None else recipe_process.encoded(dict(schema_version=1,available=True,
            adapter=adapter_identity_for_graph(dict(recipe='text_classification')),
            runtime=dict(python='3.12.fixture',device='cpu',threads=1,
                scikit_learn='1.7.2',numpy='fixture',scipy='fixture',Pillow='fixture'),problems=[]))+b'\n'
        stderr=b''
        receipt=dict(schema_version=1,attempt_id=self.phase,request_sha256='b'*64,
            spec_sha256=hashlib.sha256(recipe_process.encoded(self.document['spec'])).hexdigest(),
            helper=helper,go_received=True,spawn_closed=True,drained=True,echild=True,
            outcome='completed',reason='completed',leader_returncode=0,
            streams={name:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                     for name,raw in (('stdout',stdout),('stderr',stderr))})
        self.payload('stdout.log',stdout,'measured_stream');self.payload('stderr.log',stderr,'measured_stream')
        blob=self.payload('receipt.json',recipe_process.encoded(receipt),'custody_proof')
        self.document['events']=[self.event('prepared'),self.event('ready',helper),
            self.event('go_intent',helper),self.event('completed',helper,blob['sha256'])]
        return helper,receipt

    def test_small_canonical_proofs_reject_semantic_tampering_and_classify_malformed_process_output(self):
        self.completed();records=self.records()
        forged=copy.deepcopy(records)
        forged[0]['document']['observations']['drain_receipt']+=' '
        with self.assertRaisesRegex(WorkbenchError,'Canonical native observation differs'):
            decode_records(forged)
        for raw,outcome in ((b'package warning\n{}','invalid_observation'),(b'\xff','invalid_utf8'),(b'x'*32769,'too_large')):
            self.document['payloads']=[edge for edge in self.document['payloads']
                if edge['name'] not in ('stdout.log','stderr.log','receipt.json')]
            self.completed(raw)
            self.assertEqual(self.document['probe_result']['outcome'],outcome)
            self.assertEqual(decode_records(self.records())[self.project+'.'+self.phase],self.document)

    def test_prepared_and_measured_terminal_are_exact_inert_evidence(self):
        self.assertEqual(decode_records(self.records(),artifacts=self.artifacts)[self.project+'.'+self.phase],self.document)
        helper,receipt=self.completed();records=self.records()
        with (patch('subprocess.Popen',side_effect=AssertionError('Historical phase launched')),
              patch('project_native_execution.prepare',side_effect=AssertionError('Historical phase prepared'))):
            decoded=decode_records(records,artifacts=self.artifacts)
        self.assertEqual(decoded[self.project+'.'+self.phase],self.document)
        self.assertEqual(phase_reference(self.document)['receipt_sha256'],
            hashlib.sha256(recipe_process.encoded(receipt)).hexdigest())

    def test_environment_source_and_terminal_receipt_tampering_are_rejected(self):
        self.completed();records=self.records()
        changes=(lambda value:value['spec']['env'].update(ACCESS_TOKEN='never-retain'),
                 lambda value:value['events'][-1].update(helper=recipe_process.identity(os.getpid())|{'pid':1}),
                 lambda value:value['payloads'].pop(1),
                 lambda value:value.update(unclassified=True),
                 lambda value:value['events'][-1].update(receipt_sha256='d'*64))
        for change in changes:
            malformed=copy.deepcopy(records);change(malformed[0]['document'])
            with self.assertRaises(WorkbenchError):decode_records(malformed,artifacts=self.artifacts)

    def test_historical_uid_and_original_paths_are_not_current_launch_authority(self):
        self.document['spec']['trusted_install_owner_uid']=os.getuid()
        self.document['payloads']=[edge for edge in self.document['payloads'] if edge['name']!='spec.json']
        self.payload('spec.json',recipe_process.encoded(self.document['spec']),'execution_spec')
        with patch('subprocess.Popen',side_effect=AssertionError('No historical execution')):
            self.assertEqual(len(decode_records(self.records(),artifacts=self.artifacts)),1)
        with self.assertRaises(recipe_process.ProcessError):recipe_process.validate_spec(self.document['spec'])

    def test_declared_missing_phase_bytes_stay_inert_and_present_corruption_is_rejected(self):
        self.completed();records=self.records()
        source=next(edge['blob'] for edge in self.document['payloads'] if edge['name']=='source/text_training.py')
        path=self.path/'project/artifacts/sha256'/source['sha256']
        path.chmod(0o600);path.write_bytes(b'x'*source['bytes'])
        with self.assertRaisesRegex(WorkbenchError,'Present native evidence differs'):
            decode_records(records,artifacts=self.artifacts)
        for entry in (self.path/'project/artifacts/sha256').iterdir():entry.unlink()
        with (patch('subprocess.Popen',side_effect=AssertionError('Missing historical bytes executed')),
              patch('project_native_execution.prepare',side_effect=AssertionError('Missing bytes regenerated'))):
            decoded=decode_records(records,artifacts=self.artifacts)
        self.assertEqual(decoded[self.project+'.'+self.phase],self.document)
        self.assertEqual(self.artifacts.status(dict(format='project_artifact_v1',**source))['state'],'missing')

    def test_native_journal_upgrade_binds_physical_phase_and_requires_terminal_drain_ack(self):
        control=self.path/'host';control.mkdir()
        owner=ProjectCustody(control,'e'*32);journal=owner.for_projection(self.store,'f'*32)
        self.assertEqual(journal.snapshot()['format'],'project_local_custody_v1')
        journal.native_prepared(self.document)
        self.assertEqual(journal.snapshot()['format'],'project_local_custody_v2')
        self.assertEqual(len(owner.pending(self.store)),1)
        with self.assertRaises(WorkbenchError):journal.native_confirmed(self.phase)
        journal.native_launch_intent(self.phase)
        helper,receipt=self.completed();journal.native_launched(self.phase,helper)
        ready=copy.deepcopy(self.document);ready['events']=ready['events'][:2];journal.native_observed(ready)
        go=copy.deepcopy(self.document);go['events']=go['events'][:3];journal.native_observed(go)
        fresh=owner.for_projection(self.store,'f'*32)
        self.assertEqual(fresh.snapshot()['native_phases'][0]['state'],'go_intent')
        bad=copy.deepcopy(self.document);bad['request_sha256']='0'*64
        with self.assertRaises(WorkbenchError):fresh.native_observed(bad)
        fresh.native_observed(self.document);fresh.native_confirmed(self.phase)
        self.assertFalse(owner.for_projection(self.store,'f'*32).has_pending)
        self.assertEqual(owner.pending(self.store),[])

    def test_native_admission_private_version_preserves_original_binding_without_imported_authority(self):
        control=self.path/'host';control.mkdir()
        owner=ProjectCustody(control,'e'*32);journal=owner.for_projection(self.store,'f'*32)
        run=dict(id='1'*32,admission_id='2'*32,request_sha256='3'*64,
            graph_sha256='4'*64,release_sha256='5'*64,runtime={'observed':'fixture'})
        journal.observe_native_admission(run)
        current=owner.for_projection(self.store,'f'*32)
        self.assertEqual(current.snapshot()['format'],'project_local_custody_v3')
        self.assertEqual(current.snapshot()['native_admissions'][0]['phase_started'],False)
        self.assertTrue(current.has_pending);self.assertEqual(len(owner.pending(self.store)),1)
        changed=dict(run,admission_id='6'*32)
        with self.assertRaises(WorkbenchError):current.observe_native_admission(changed)
        malformed=current.snapshot();malformed['native_admissions'][0]['grant']='not-authority'
        with self.assertRaises(WorkbenchError):validate_custody(malformed)
        current.settle_native_admission(run['id'])
        self.assertFalse(current.has_pending)

    def test_native_phase_capacity_covers_all_current_worker_phases_and_one_foreground(self):
        from run_capacity import MAX_ATTEMPTS
        control=self.path/'host';control.mkdir()
        journal=ProjectCustody(control,'e'*32).for_projection(self.store,'f'*32)
        value=journal.snapshot();value.update(format='project_local_custody_v3',native_admissions=[])
        entry=dict(phase_id='1'*32,phase='probe',run_id=None,request_sha256='2'*64,
            spec_sha256='3'*64,state='prepared',helper=None,receipt_sha256=None)
        value['native_phases']=[dict(entry,phase_id=f'{index+1:032x}') for index in range(3*MAX_ATTEMPTS+1)]
        self.assertEqual(len(validate_custody(value)['native_phases']),NATIVE_PHASE_LIMIT)
        value['native_phases'].append(dict(entry,phase_id='f'*32))
        with self.assertRaisesRegex(WorkbenchError,'Too many unresolved native phases'):validate_custody(value)

    def test_native_exposure_observation_is_portable_science_and_rejects_unclassified_fields(self):
        from runs import project_run_projection
        from test_project_history import legacy_run
        run=legacy_run()
        observation=dict(exposed=True,events=[dict(id='1'*32,record_id='2'*32,source_hash='3'*64,
            reason='Actual prior exposure',run_id=run['id'],release_id=run['release_id'],created_at=run['created_at'])])
        run['execution_test_exposure']=observation
        projected=project_run_projection(run)
        self.assertEqual(projected['execution_test_exposure'],observation)
        self.assertNotIn('worker',projected)
        run['execution_test_exposure']['grant']='not-science'
        with self.assertRaises(WorkbenchError):project_run_projection(run)

    def test_model_aware_job_evidence_must_match_run_even_when_all_template_hashes_are_consistent(self):
        import audio_training
        import image_training
        import model_evidence
        import one_fit_evidence
        import text_training
        for adapter in (text_training,audio_training,image_training):
            parameters={key:rule['default'] for key,rule in adapter.PARAMETER_BOUNDS.items()}
            if adapter is image_training:parameters.update(widths=[4,8,16],input_size=32,head='linear')
            owner=model_evidence if adapter is image_training else one_fit_evidence.contract(adapter)
            context=dict(material_sha256='1'*64,model_sha256='2'*64,adapter_sha256='3'*64,
                profile=owner.profile(self.project,'2'*64,parameters,2))
            worker=Path(adapter.__file__).name;source=b'# Exact authored retained worker; never executed.\n'
            definition={worker:hashlib.sha256(source).hexdigest()}
            run=dict(id='4'*32,dataset_id=self.project,graph=dict(recipe=adapter.MODEL_RECIPE),graph_sha256='5'*64,
                release_id='6'*64,release_sha256='6'*64,parameters=parameters,adapter=adapter.MODEL_ADAPTER,
                runtime=dict(definition_files=definition),evidence_context=context)
            def records_for(change=None):
                phase=uuid.uuid4().hex;stage=self.path/('model-context-'+phase);output=stage/'output'
                job=dict(schema_version=2,dataset_id=self.project,run_id=run['id'],graph_sha256=run['graph_sha256'],
                    release_id=run['release_id'],release_sha256=run['release_sha256'],release_path=str(self.path/'retained-release.zip'),
                    output_dir=str(output),parameters=parameters,parent_pid=1)
                if adapter is image_training:job['evidence_context']=copy.deepcopy(context)
                else:job.update(one_fit_evidence.job_for_run(run,output),release_path=str(self.path/'retained-release.zip'))
                if change is not None:change(job)
                # These forgeries pass the live adapter's well-formed job
                # decoder. Every captured-file/template/spec SHA is freshly
                # rebuilt, isolating the missing scientific relation to Run.
                self.assertEqual(adapter._checked_job(job),job)
                spec=self.prepared.spec
                executable=spec['argv'][0]
                runtime=dict(executable=executable,executable_sha256=spec['executable_sha256'],
                    trusted_install_owner_uid=spec['trusted_install_owner_uid'],
                    files={row['path']:{key:row[key] for key in ('sha256','bytes')} for row in spec['runtime_files']})
                prepared=prepare(stage,phase='train',attempt_id=phase,request_sha256='7'*64,runtime=runtime,
                    worker=worker,sources={worker:source},job=job,model_aware=True)
                self.document=dict(format=FORMAT,origin_catalog_id=self.project,phase_id=phase,phase='train',
                    run_id=run['id'],recipe=adapter.MODEL_RECIPE,request_key='model-context-'+phase,request_sha256='7'*64,
                    actor_id='c'*32,definition_identity=dict(definition_files=definition,adapter_definition_sha256=digest(definition)),
                    spec=prepared.spec,events=[self.event('prepared')],payloads=[],observations=dict.fromkeys(OBSERVATIONS),probe_result=None)
                self.payload('spec.json',recipe_process.encoded(prepared.spec),'execution_spec')
                for item in prepared.spec['captured_files']:
                    name=str(Path(item['path']).relative_to(stage))
                    self.payload(name,Path(item['path']).read_bytes(),'execution_spec' if name=='native-job-template.json' else 'execution_source')
                records=self.records();records[0]['id']=self.project+'.'+phase
                return records+[dict(family='run_history',id=self.project+'.'+run['id'],document={'run':copy.deepcopy(run)})]
            with self.subTest(adapter=adapter.MODEL_RECIPE),patch('subprocess.Popen',side_effect=AssertionError('Retained job decoder launched')):
                self.assertEqual(len(decode_records(records_for())),1)
                if adapter is image_training:
                    changes=[lambda job:job['evidence_context'].update(model_sha256='8'*64),
                        lambda job:job['evidence_context']['profile']['probe_selection'].update(count=1)]
                else:
                    changes=[lambda job,key=key:job['evidence'].update({key:'8'*64}) for key in
                        ('model_sha256','material_sha256','adapter_sha256','profile_sha256','selection_policy_sha256','output_policy_sha256')]
                    def downgraded(job):
                        job['schema_version']=1;job.pop('adapter');job.pop('evidence')
                    changes.append(downgraded)
                for change in changes:
                    with self.assertRaisesRegex(WorkbenchError,'exact scientific Run inputs'):decode_records(records_for(change))


class NativeOutputAnchors(unittest.TestCase):
    def test_stage_output_and_leaf_symlinks_and_directory_replacement_never_receive_provenance(self):
        with tempfile.TemporaryDirectory(prefix='native-output-anchor-') as temporary:
            root=Path(temporary);phase='1'*32;run_id='2'*32
            output=root/'project-native-phases'/phase/'output';output.mkdir(parents=True)
            foreign=root/'foreign';foreign.mkdir();(foreign/'model.json').write_bytes(b'foreign')
            recorded=[]
            native=ProjectNativeExecution(SimpleNamespace(projection=None,session=SimpleNamespace(snapshot={'records':[]}),
                db=SimpleNamespace(path=root,dataset_id='3'*32),runtime_access=None))
            native._retain=lambda document,name,raw,role:recorded.append((name,raw,role))
            document=dict(phase_id=phase,phase='train',run_id=run_id,spec=dict(output_dir=str(output),max_output_bytes=1024))
            run=dict(graph=dict(recipe='text_classification'))
            output.rmdir();output.symlink_to(foreign,target_is_directory=True)
            with self.assertRaisesRegex(WorkbenchError,'stage is unavailable'):native._retain_outputs(document,run=run)
            output.unlink();output.mkdir();(output/'model.json').symlink_to(foreign/'model.json')
            with self.assertRaisesRegex(WorkbenchError,'stage is unavailable'):native._retain_outputs(document,run=run)
            (output/'model.json').unlink();(output/'model.json').write_bytes(b'original')
            original_read=os.read;replaced=[]
            def read(descriptor,maximum):
                raw=original_read(descriptor,maximum)
                if not replaced:
                    replaced.append(True);output.rename(output.parent/'original-output')
                    output.symlink_to(foreign,target_is_directory=True)
                return raw
            with patch('project_native_execution.os.read',side_effect=read),self.assertRaises(WorkbenchError):
                native._retain_outputs(document,run=run)
            self.assertEqual(recorded,[])
            output.unlink();(output.parent/'original-output').rename(output)
            native._retain_outputs(document,run=run)
            self.assertEqual(recorded,[('output/model.json',b'original','measured_output')])


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class NativeProbeBoundaryTests(unittest.TestCase):
    """Actual child/native probe; authored release summary only, no model fit."""
    setUp=study_fixture.ProjectStudyControlTests.setUp
    cleanup=study_fixture.ProjectStudyControlTests.cleanup
    metadata=study_fixture.ProjectStudyControlTests.metadata
    open_projection=study_fixture.ProjectStudyControlTests.open_projection
    graph=preparation_fixture.NativePreparationTests.graph
    release=preparation_fixture.NativePreparationTests.release

    def install_journal(self):
        projection=self.projection
        owner=ProjectCustody(self.host.db.path,self.host.db.dataset_id)
        projection.custody=projection.execution.custody=owner.for_projection(self.store,projection.db.projection_id)
        projection.session.publication_intent=projection.execution._publication_intent
        return owner

    def deferred_failure(self,state):
        projection=self.projection;db=projection.db;execution=projection.execution
        db.execute('CREATE TEMP TABLE native_ack_parent(id INT PRIMARY KEY)')
        db.execute('CREATE TEMP TABLE native_ack_child(id INT REFERENCES native_ack_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        original=execution.before_commit;fired=[]
        def before():
            target=any(doc['events'][-1]['state']==state for doc in execution.native._dirty.values())
            original()
            if target and not fired:
                fired.append(True);db.execute('INSERT INTO native_ack_child VALUES(1)')
        # Fault injection wraps the installed owner; production correctly
        # refuses a second owner through set_project_hooks.
        self.enterContext(patch.object(db,'_project_before_commit',new=before))
        return fired

    def test_never_entered_launch_can_settle_but_restarted_ambiguous_spawn_window_remains_unknown(self):
        self.install_journal();projection=self.projection;native=projection.execution.native
        with self.owner.bound(self.host),patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}):
            graph=self.graph();original=native._dispatch_authorized;stopped=[]
            def dispatch(identity):
                original(identity)
                entry=next((row for row in projection.custody.snapshot().get('native_phases',[]) if row['phase_id']==identity),None)
                if entry is not None and entry['state']=='launch_intent':
                    stopped.append(identity);raise WorkbenchError('Controlled authority loss before entering launch.','unavailable',409)
            with patch.object(projection.pipelines,'inspect_release',side_effect=self.release), \
                    patch.object(native,'_dispatch_authorized',side_effect=dispatch), \
                    patch('subprocess.Popen',side_effect=AssertionError('Never-entered launch constructed a child')):
                with self.assertRaisesRegex(WorkbenchError,'Controlled authority loss'):
                    projection.execution.native_preflight(graph['id'],1,projection.session.snapshot['checkpoint'],'native-never-entered')
            phase=stopped[0]
            # An independently restarted owner has no private proof that the
            # launch call was not entered after the durable intent.
            original_native=ProjectNativeExecution(projection.execution)
            with patch.object(projection,'reconcile_inert',side_effect=AssertionError('Unknown spawn reconstructed')):
                with self.assertRaisesRegex(WorkbenchError,'helper drainage identity'):
                    original_native.reconcile(phase,projection.session.snapshot['checkpoint'])
            # Its original process retains the exact before-call proof.
            with patch('subprocess.Popen',side_effect=AssertionError('Never-launched recovery launched')):
                result=native.reconcile(phase,projection.session.snapshot['checkpoint'])
            self.assertEqual(result['state'],'failed');self.assertIsNone(result['receipt_sha256'])
            self.assertFalse(projection.custody.has_pending);projection.execution.assert_quiescent()

    def test_generic_reconciliation_refuses_native_phase_before_recovery_or_reconstruction(self):
        self.install_journal();projection=self.projection
        with self.owner.bound(self.host):
            with patch.object(projection.custody,'snapshot',return_value={'native_phases':[dict(phase_id='1'*32)]}), \
                    patch.object(self.store,'recover_checkpoint',side_effect=AssertionError('Generic native recovery touched checkout')), \
                    patch.object(projection,'reconcile_inert',side_effect=AssertionError('Generic native recovery reconstructed')):
                for action in (projection.execution.reconcile_current,
                        lambda:projection.execution.reconcile_original(expected_checkpoint=projection.session.snapshot['checkpoint'])):
                    with self.assertRaisesRegex(WorkbenchError,'native_reconcile') as error:action()
                    self.assertEqual(error.exception.code,'unavailable')

    def test_never_launched_failed_phase_sql_ack_loss_reconciles_exact_terminal_fact_without_popen(self):
        """A second failure must not strand a proven non-process intent."""
        self.install_journal();projection=self.projection;native=projection.execution.native
        with self.owner.bound(self.host),patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}), \
                patch('subprocess.Popen',side_effect=AssertionError('Never-launched double-fault spawned a child')):
            graph=self.graph();original=native._dispatch_authorized;stopped=[]
            def refuse_before_launch(identity):
                original(identity)
                entry=next((row for row in projection.custody.snapshot().get('native_phases',[]) if row['phase_id']==identity),None)
                if entry is not None and entry['state']=='launch_intent':
                    stopped.append(identity)
                    raise WorkbenchError('Controlled refusal before launch entry.','unavailable',409)
            with patch.object(projection.pipelines,'inspect_release',side_effect=self.release), \
                    patch.object(native,'_dispatch_authorized',side_effect=refuse_before_launch):
                with self.assertRaisesRegex(WorkbenchError,'Controlled refusal'):
                    projection.execution.native_preflight(graph['id'],graph['revision'],
                        projection.session.snapshot['checkpoint'],'native-never-launched-double-fault')
            self.assertEqual(len(stopped),1);phase=stopped[0]
            self.assertIn(phase,native._never_launched)
            fired=self.deferred_failure('failed')
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                native.reconcile(phase,projection.session.snapshot['checkpoint'])
            self.assertEqual(fired,[True]);self.assertFalse(projection.session.available)
            terminal=self.store.snapshot()
            document=next(row['document'] for row in terminal['records'] if row['family']==FAMILY)
            self.assertEqual(document['events'][-1]['state'],'failed')
            self.assertIsNone(document['events'][-1]['helper'])
            self.assertIsNone(document['events'][-1]['receipt_sha256'])
            self.assertTrue(all(value is None for value in document['observations'].values()))
            pending=projection.custody.snapshot()['native_phases']
            self.assertEqual(len(pending),1);self.assertEqual(pending[0]['state'],'launch_intent')
            self.assertIn(phase,native._never_launched)
            projection.db._project_before_commit=projection.execution.before_commit
            result=native.reconcile(phase,projection.session.snapshot['checkpoint'])
            self.assertEqual(result['state'],'failed');self.assertIsNone(result['receipt_sha256'])
            self.assertTrue(projection.session.available);self.assertFalse(projection.custody.has_pending)
            self.assertNotIn(phase,native._never_launched)
            self.assertEqual(self.store.snapshot(),terminal,'Recovery duplicated or changed the acknowledged terminal science')
            self.assertEqual(projection.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)
            self.assertEqual(projection.db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)
            projection.execution.assert_quiescent()

    def test_second_foreground_probe_refuses_before_preparation_without_blocking_current_owner(self):
        native=self.projection.execution.native
        native._foreground_phase='f'*32
        try:
            with patch('project_native_execution.prepare',side_effect=AssertionError('Second foreground prepared')):
                with self.assertRaisesRegex(WorkbenchError,'Another explicit native preparation'):
                    native._run_phase('probe','text_classification','second-probe',None,{},None)
            self.assertEqual(native._foreground_phase,'f'*32)
        finally:native._foreground_phase=None

    def _admission_ack_failure(self):
        from runs import Runs
        from test_project_native_study import prepare_text_source
        projection=self.projection;self.install_journal()
        _,release=prepare_text_source(projection,key_prefix='native-no-dispatch')
        body=dict(name='Never-dispatched current admission',recipe='text_validate_export',release_id=release['id'])
        graph=projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
            projection.session.snapshot['checkpoint'],'no-dispatch-graph',lambda:projection.pipelines.create(body))
        validation=projection.execution.native_preflight(graph['id'],1,projection.session.snapshot['checkpoint'],'no-dispatch-validation')
        self.assertTrue(validation['valid'],validation)
        projection.db.execute('CREATE TEMP TABLE native_admit_parent(id INT PRIMARY KEY)')
        projection.db.execute('CREATE TEMP TABLE native_admit_child(id INT REFERENCES native_admit_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        original=Runs._admit
        def admit(owner,*args,**kwargs):
            result=original(owner,*args,**kwargs)
            owner.db.execute('INSERT INTO native_admit_child VALUES(1)')
            return result
        with patch.object(Runs,'_admit',new=admit),patch('subprocess.Popen',side_effect=AssertionError('Unacknowledged native admission dispatched')):
            with self.assertRaises(ProjectSessionError) as failure:
                projection.execution.native_submit(dict(graph_id=graph['id'],graph_revision=1,
                    validation_token=validation['validation_token']),projection.session.snapshot['checkpoint'],'no-dispatch-admit')
            self.assertIsInstance(failure.exception.__cause__,psycopg.errors.ForeignKeyViolation)
            self.assertEqual(failure.exception.code,'projection_unavailable')
        journal=projection.custody.snapshot()
        self.assertEqual(journal['format'],'project_local_custody_v3')
        self.assertEqual(len(journal['native_admissions']),1);self.assertEqual(journal['native_phases'],[])
        self.assertFalse(journal['native_admissions'][0]['phase_started'])
        self.assertEqual(projection.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)
        self.assertEqual(projection.db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)
        self.assertFalse(projection.session.available)
        with self.assertRaises(WorkbenchError):projection.execution.assert_quiescent()
        return journal

    def test_native_admission_sql_ack_failure_clears_only_current_non_effect_intent_without_authority(self):
        with self.owner.bound(self.host):
            self._admission_ack_failure();projection=self.projection
            before=self.store.snapshot()
            with patch('subprocess.Popen',side_effect=AssertionError('Current admission reconciliation dispatched')):
                result=projection.execution.reconcile_current()
            self.assertTrue(result['available']);self.assertFalse(projection.custody.has_pending)
            self.assertEqual(self.store.snapshot(),before)
            retained=next(row['document']['run'] for row in before['records'] if row['family']=='run_history')
            self.assertEqual(retained['state'],'queued')
            self.assertEqual(projection.db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)
            projection.execution.assert_quiescent();projection.close()

    def test_native_admission_sql_ack_failure_original_physical_reopen_stays_inert_until_exact_clear(self):
        from metadata import Metadata
        from project_projection import ProjectProjection
        with self.owner.bound(self.host):
            self._admission_ack_failure();previous=self.projection
            path=previous.db.path;identity=previous.db.projection_id
            previous.sources.close();previous.artifacts.close();previous.db.close()
            self.projections.remove(previous)
            db=Metadata(path,create=False,dataset_id=self.store.snapshot()['project_id'],projection_id=identity)
            self.databases.append(db)
            journal=ProjectCustody(self.host.db.path,self.host.db.dataset_id).for_projection(self.store,identity)
            with patch('runs.Runs',side_effect=AssertionError('Original physical reopen constructed Runs')):
                projection=ProjectProjection(self.store,db,self.host.access,{},custody=journal,restore=False)
            self.projections.append(projection);self.assertFalse(projection.session.available)
            self.assertIsNone(projection.execution._runs)
            before=self.store.snapshot()
            with patch('subprocess.Popen',side_effect=AssertionError('Original admission clear dispatched')):
                result=projection.execution.reconcile_original(expected_checkpoint=projection.session.snapshot['checkpoint'])
            self.assertTrue(result['available']);self.assertFalse(journal.has_pending)
            self.assertEqual(self.store.snapshot(),before);self.assertIsNone(projection.execution._runs)
            self.assertEqual(db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)
            projection.close()

    def test_actual_go_intent_sql_failure_sends_no_go_then_exact_receipt_reconciles_without_launch(self):
        self.install_journal();projection=self.projection;go=[]
        with self.owner.bound(self.host),patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}):
            graph=self.graph();fired=self.deferred_failure('go_intent')
            with patch.object(projection.pipelines,'inspect_release',side_effect=self.release), \
                    patch.object(recipe_process.Handle,'go',side_effect=AssertionError('GO before SQL acknowledgement')):
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    projection.execution.native_preflight(graph['id'],1,projection.session.snapshot['checkpoint'],'go-ack-failure')
            self.assertEqual(fired,[True]);self.assertFalse(projection.session.available)
            phase=projection.execution.health()['native_phases']['items'][0]
            self.assertEqual(phase['state'],'ready')
            projection.db._project_before_commit=projection.execution.before_commit
            with patch('subprocess.Popen',side_effect=AssertionError('Reconciliation launched')), \
                    patch.object(recipe_process.Handle,'go',side_effect=AssertionError('Reconciliation replayed GO')):
                result=projection.execution.native_reconcile(phase['phase_id'],projection.session.snapshot['checkpoint'])
            self.assertEqual(result['state'],'failed');self.assertTrue(projection.session.available)
            self.assertFalse(projection.custody.has_pending);projection.execution.assert_quiescent()
            document=next(r['document'] for r in self.store.snapshot()['records'] if r['family']==FAMILY)
            receipt=recipe_process.decode(document['observations']['drain_receipt'])
            self.assertFalse(receipt['go_received']);self.assertTrue(receipt['drained'])

    def test_non_utf8_probe_with_terminal_sql_failure_reconciles_process_without_valid_preflight_or_reexecution(self):
        self.install_journal();projection=self.projection
        with self.owner.bound(self.host),patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}):
            graph=self.graph()
            source=self.root/'protocol-fixture';source.mkdir()
            for name in projection.pipelines.definition_identity(graph['recipe'])['definition_files']:
                (source/name).write_bytes((projection.pipelines.source_path/name).read_bytes())
            (source/'text_training.py').write_bytes(b'import sys\nsys.stdout.buffer.write(b"\\xff")\nsys.stdout.flush()\n')
            with patch.object(projection.pipelines,'source_path',source):
                fired=self.deferred_failure('completed')
                with patch.object(projection.pipelines,'inspect_release',side_effect=self.release):
                    with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                        projection.execution.native_preflight(graph['id'],1,projection.session.snapshot['checkpoint'],'malformed-ack-failure')
            self.assertEqual(fired,[True]);self.assertFalse(projection.session.available)
            projection.db._project_before_commit=projection.execution.before_commit
            phase=projection.execution.health()['native_phases']['items'][0]
            with patch('subprocess.Popen',side_effect=AssertionError('Malformed recovery launched')), \
                    patch.object(recipe_process.Handle,'go',side_effect=AssertionError('Malformed recovery replayed GO')):
                result=projection.execution.native_reconcile(phase['phase_id'],projection.session.snapshot['checkpoint'])
            self.assertEqual(result['state'],'completed')
            self.assertFalse(projection.custody.has_pending);self.assertTrue(projection.session.available)
            document=next(r['document'] for r in self.store.snapshot()['records'] if r['family']==FAMILY)
            self.assertIsNone(document['observations']['probe_stdout'])
            self.assertEqual(document['probe_result']['outcome'],'invalid_utf8')
            self.assertEqual(recipe_process.decode(document['observations']['drain_receipt'])['leader_returncode'],0)
            self.assertFalse(any(r['family']=='project_operation' and r['document']['operation']=='native_preparation.validate'
                                 for r in self.store.snapshot()['records']))

    def test_real_probe_go_requires_canonical_and_sql_ack_and_retains_exact_raw_observation(self):
        control=self.install_journal();projection=self.projection;go=[]
        original=recipe_process.Handle.go
        def observed(handle,helper):
            self.assertFalse(projection.db.in_transaction)
            current=self.store.snapshot()
            document=next(r['document'] for r in current['records'] if r['family']==FAMILY
                and r['document']['phase_id']==handle.spec['attempt_id'])
            self.assertEqual(document['events'][-1]['state'],'go_intent')
            fresh=control.for_projection(self.store,projection.db.projection_id)
            self.assertEqual(fresh.snapshot()['native_phases'][0]['state'],'go_intent')
            go.append(handle.spec['attempt_id']);return original(handle,helper)
        with self.owner.bound(self.host),patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}):
            graph=self.graph()
            with patch.object(projection.pipelines,'inspect_release',side_effect=self.release), \
                    patch.object(recipe_process.Handle,'go',new=observed), \
                    patch('runs.Runs',side_effect=AssertionError('Probe constructed Runs')):
                value=projection.execution.native_preflight(graph['id'],1,projection.session.snapshot['checkpoint'],'actual-probe')
            self.assertIs(type(value['valid']),bool);self.assertEqual(len(go),1)
            records=self.store.snapshot()['records'];phases=decode_records(records,artifacts=projection.artifacts)
            self.assertEqual(len(phases),1)
            document=next(iter(phases.values()))
            self.assertIn(document['events'][-1]['state'],('completed','failed'))
            stdout=next(edge['blob'] for edge in document['payloads'] if edge['name']=='stdout.log')
            raw=projection.artifacts.read_blob(stdout,maximum_bytes=32768)
            self.assertEqual(recipe_process.decode(raw)['runtime'],value['runtime']['runtime'])
            self.assertFalse(projection.custody.has_pending);self.assertFalse(projection.execution.native.has_local_custody)
            self.assertEqual(projection.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class NativePhaseRecoveryHTTP(unittest.TestCase):
    setUp=http_fixture.ProjectFilesHTTP.setUp
    cleanup_owned=http_fixture.ProjectFilesHTTP.cleanup_owned
    select_host=http_fixture.ProjectFilesHTTP.select_host
    request=http_fixture.ProjectFilesHTTP.request
    state=http_fixture.ProjectFilesHTTP.state
    envelope=http_fixture.ProjectFilesHTTP.envelope
    action=http_fixture.ProjectFilesHTTP.action
    create=http_fixture.ProjectFilesHTTP.create
    graph=preparation_fixture.NativePreparationTests.graph
    release=preparation_fixture.NativePreparationTests.release
    deferred_failure=NativeProbeBoundaryTests.deferred_failure

    def native_http(self,action,arguments,version=1):
        import agent_api
        name='project_files.'+action
        method,path,body=agent_api.project_request(name,arguments,version=version)
        request=Request(self.origin+path,method=method,
            data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+self.owner.token,'Origin':self.origin,'Content-Type':'application/json',
                     'Tuldok-Operation-Contract':agent_api.selected_header(name,version)})
        try:response=urlopen(request,timeout=45)
        except HTTPError as error:response=error
        with response:return response.status,json.load(response)

    def stop_without_effects(self,workspace):
        # This fixture has only the canceled, drained probe and no Run owner.
        # Preserve its physical SQL/journal for the explicit restarted owner.
        for candidate,server,thread in self.hosts:
            if candidate is workspace:
                server.shutdown();server.server_close();thread.join(3);break
        for projection in (workspace._projection,workspace._retained_recovery):
            if projection is not None:
                self.assertIsNone(projection.execution._runs)
                projection.sources.close();projection.artifacts.close();projection.db.close()
        workspace._store.close()
        for _path,descriptor in workspace._roots.values():os.close(descriptor)
        workspace._roots.clear();workspace.db.close();workspace._closed=True

    def test_uncertain_spawn_without_handle_fences_public_preflight_and_never_infers_cessation(self):
        import project_workspace
        from project_native_process import PreparedNative
        self.enterContext(patch.object(project_workspace,'M3_ENABLED',True))
        self.enterContext(patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}))
        self.create();self.projection=self.workspace._projection
        with self.owner.bound(self.workspace):graph=self.graph()
        acknowledged=self.state();projection=self.projection;entered=[]
        def uncertain_launch(prepared,custody_directory,*,_before_spawn=None):
            self.assertIsNotNone(_before_spawn)
            _before_spawn();entered.append(prepared.spec['attempt_id'])
            # The foundation's own real seam tests establish this callback is
            # the Popen entry boundary. Simulate only its uncertain exception;
            # do not fabricate a child, Handle, drainage, or successful result.
            raise OSError('Controlled uncertainty after entering spawn boundary')
        arguments=dict(binding=acknowledged['binding'],expected_checkpoint=acknowledged['project']['checkpoint'],
            graph_id=graph['id'],revision=graph['revision'],request_key='native-uncertain-spawn')
        try:
            with patch.object(projection.pipelines,'inspect_release',side_effect=self.release), \
                    patch.object(PreparedNative,'launch',new=uncertain_launch), \
                    patch('subprocess.Popen',side_effect=AssertionError('Unknown-spawn control created a real child')):
                status,error=self.native_http('native_preflight',arguments)
                self.assertEqual((status,error['code']),(409,'outcome_unknown'))
                self.assertEqual(len(entered),1);self.assertFalse(projection.session.available)
                self.assertNotIn(entered[0],projection.execution.native._never_launched)
                entry=projection.custody.snapshot()['native_phases'][0]
                self.assertEqual(entry['state'],'launch_intent');self.assertIsNone(entry['helper'])
                self.assertIsNone(entry['receipt_sha256'])
                recovery=self.state();self.assertEqual(recovery['state'],'recovery_required')
                public=dict(binding=recovery['binding'],checkpoint=recovery['project']['checkpoint'])
                status,health=self.native_http('execution_health',public,2)
                self.assertEqual(status,200,health);self.assertFalse(health['value']['available'])
                self.assertEqual(health['value']['native_phases']['items'][0]['phase_id'],entered[0])
                before=self.workspace._store.snapshot()
                status,error=self.native_http('native_preflight',dict(arguments,
                    expected_checkpoint=public['checkpoint'],request_key='native-fresh-after-uncertainty'))
                self.assertEqual((status,error['code']),(503,'projection_unavailable'))
                status,error=self.native_http('native_reconcile',dict(binding=public['binding'],
                    expected_checkpoint=public['checkpoint'],phase_id=entered[0]))
                self.assertEqual((status,error['code']),(409,'unknown'))
                self.assertEqual(entered,[entry['phase_id']])
                self.assertFalse(projection.session.available);self.assertTrue(projection.custody.has_pending)
                self.assertEqual(self.workspace._store.snapshot(),before)
        finally:
            # This test explicitly forbids real process creation. Preserve the
            # unresolved private record while disposing only fixture handles.
            self.stop_without_effects(self.workspace)

    def test_selected_health_versions_discover_original_phase_and_named_recovery_never_replays_go(self):
        import agent_api
        import project_workspace
        self.enterContext(patch.object(project_workspace,'M3_ENABLED',True))
        self.enterContext(patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':'/usr/bin/python3'}))
        self.create();self.projection=self.workspace._projection
        with self.owner.bound(self.workspace):graph=self.graph()
        acknowledged=self.state();projection=self.projection
        fired=self.deferred_failure('go_intent')
        arguments=dict(binding=acknowledged['binding'],expected_checkpoint=acknowledged['project']['checkpoint'],
            graph_id=graph['id'],revision=graph['revision'],request_key='http-original-native-phase')
        with patch.object(projection.pipelines,'inspect_release',side_effect=self.release), \
                patch.object(recipe_process.Handle,'go',side_effect=AssertionError('Unacknowledged HTTP phase sent GO')):
            status,error=self.native_http('native_preflight',arguments)
        self.assertEqual((status,error['code']),(503,'storage'));self.assertEqual(fired,[True])
        recovery=self.state();self.assertEqual(recovery['state'],'recovery_required')
        self.assertEqual(recovery['binding'],acknowledged['binding'])
        self.assertEqual(recovery['project']['checkpoint'],acknowledged['project']['checkpoint'])
        pinned=dict(binding=recovery['binding'],checkpoint=recovery['project']['checkpoint'],offset=0,limit=1)
        for version in (1,2):
            status,reply=self.native_http('execution_health',pinned,version)
            self.assertEqual(status,200,reply)
            agent_api.validate_output('project_files.execution_health',dict(status=200,result=reply),version=version)
            self.assertEqual(reply['checkpoint'],pinned['checkpoint']);self.assertFalse(reply['value']['available'])
            self.assertEqual('native_phases' in reply['value'],version==2)
            if version==2:
                phase=reply['value']['native_phases']['items'][0]
                self.assertEqual(reply['value']['native_phases']['total'],1)
                self.assertIsNone(phase['run_id']);self.assertEqual(phase['state'],'ready')
        for changed in (dict(pinned,binding='e'*32),dict(pinned,checkpoint='f'*64)):
            self.assertEqual(self.native_http('execution_health',changed,2)[0],409)
        with patch.object(projection,'reconcile_inert',side_effect=AssertionError('Generic native reconstruction')):
            status,error=self.native_http('execution_reconcile_current',
                dict(binding=recovery['binding'],expected_checkpoint=pinned['checkpoint']))
        self.assertEqual((status,error['code']),(409,'unavailable'))
        physical=projection.db.projection_id;control=self.workspace.path
        self.stop_without_effects(self.workspace)
        with patch('runs.Runs',side_effect=AssertionError('Original HTTP Open constructed Runs')), \
                patch('subprocess.Popen',side_effect=AssertionError('Original HTTP recovery launched')), \
                patch.object(recipe_process.Handle,'go',side_effect=AssertionError('Original HTTP recovery replayed GO')):
            self.select_host(control,{'fixture':self.external})
            self.action('open',root='fixture',directory='alpha')
            state=self.state();self.assertEqual(state['state'],'recovery_required')
            current=dict(binding=state['binding'],checkpoint=state['project']['checkpoint'],offset=0,limit=1)
            status,reply=self.native_http('execution_health',current,2)
            self.assertEqual(status,200,reply);self.assertEqual(reply['value']['native_phases']['items'],[phase])
            self.assertEqual(self.workspace._retained_recovery.db.projection_id,physical)
            status,result=self.native_http('native_reconcile',dict(binding=state['binding'],
                expected_checkpoint=current['checkpoint'],phase_id=phase['phase_id']))
            self.assertEqual(status,200,result);self.assertEqual(result['binding'],state['binding'])
            self.assertEqual(result['value']['state'],'failed')
            self.assertEqual(self.workspace._projection.db.projection_id,physical)
            self.assertIsNone(self.workspace._projection.execution._runs)
            self.assertFalse(self.workspace._projection.custody.has_pending)
            self.action('close')


if __name__=='__main__':unittest.main()
