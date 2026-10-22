"""Fixed consumer composition evidence, separate from canonical owner I/O tests."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import agent_api
from project_dispatch import SUPPORTED_OPERATIONS, dispatch
from project_material import ProjectMaterial
from workbench import WorkbenchError

PROJECT, RECORD, ORIGIN = 'a' * 32, 'b' * 32, 'c' * 32
CHECKPOINT, SHA = 'd' * 64, 'e' * 64
BOUND = dict(binding='f' * 32, expected_checkpoint=CHECKPOINT, request_key='dispatch-fixture-1')
READ = dict(binding='f' * 32, checkpoint=CHECKPOINT)


class Authority:
    def __init__(self, deny_owner=False):
        self.calls = []
        self.deny_owner = deny_owner

    def require(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if kwargs.get('owner_only') and self.deny_owner:
            raise WorkbenchError('Current owner authority is required.', 'forbidden', 403)
        return SimpleNamespace(actor_id=PROJECT)


def projection():
    access = Authority()
    session = SimpleNamespace(access=access, snapshot={'project_id': PROJECT, 'records': []})
    return SimpleNamespace(session=session, data=Mock(), materials=Mock(), history=Mock(),
        context=SimpleNamespace(models=Mock(), pipelines=Mock()), artifacts=Mock(),
        producers=Mock(), source_adapter=Mock(), runtime_manifest=Mock(), disclose=Mock(), resolve_artifact=Mock())


class Dispatch(unittest.TestCase):
    def test_supported_operations_match_the_finite_public_contract(self):
        self.assertEqual(SUPPORTED_OPERATIONS, agent_api.PROJECT_FILES_M2)
        with self.assertRaises(WorkbenchError) as failure:
            dispatch(object(), 'project_files.runs_execute', {})
        self.assertEqual(failure.exception.code, 'unsupported')

    def test_metadata_calls_preserve_native_body_and_canonical_arguments(self):
        selected = projection()
        selected.data.correct_rights_note.return_value = {'changed': True}
        arguments = dict(BOUND, record_id=RECORD, revision=3, source_revision=1, note='Unique authored rights note')
        agent_api.validate_arguments('project_files.data_rights', arguments)
        self.assertEqual(dispatch(selected, 'project_files.data_rights', arguments), {'changed': True})
        selected.data.correct_rights_note.assert_called_once_with(RECORD,
            {'revision': 3, 'source_revision': 1, 'note': 'Unique authored rights note'}, CHECKPOINT, BOUND['request_key'])
        selected.history.prepare_trial_from_material.return_value = {'id': RECORD}
        ref = dict(kind='recipe_material', catalog_id=ORIGIN, id=SHA, sha256=SHA)
        arguments = dict(BOUND, study_id=RECORD, revision=2, material=ref, replicate=0)
        dispatch(selected, 'project_files.trial_prepare', arguments)
        selected.history.prepare_trial_from_material.assert_called_once_with(RECORD,
            {'revision': 2, 'material': ref, 'replicate': 0}, CHECKPOINT, BOUND['request_key'])

    def test_external_graph_creation_uses_canonical_material_boundary(self):
        selected = projection()
        body = {'name': 'New external scientific recipe', 'project_id': RECORD,
                'recipe_id': 'owned_recipe', 'expected_sha256': SHA, 'inputs': {}, 'parameters': {}}
        arguments = dict(BOUND, **body)
        agent_api.validate_arguments('project_files.graph_create_external', arguments)
        selected.materials.mutate_definition.side_effect = lambda family, operation, target, value, cp, key, invoke: invoke()
        selected.context.pipelines.create_external.return_value = {'id': RECORD, 'revision': 1}
        result = dispatch(selected, 'project_files.graph_create_external', arguments)
        self.assertEqual(result, {'id': RECORD, 'revision': 1})
        selected.context.pipelines.create_external.assert_called_once_with(body)
        captured = selected.materials.mutate_definition.call_args.args
        self.assertEqual(captured[:6], ('pipeline_graph', 'graphs.create_external', None,
                                        body, CHECKPOINT, BOUND['request_key']))

    def test_project_graph_inputs_reuse_current_domain_grammar_without_legacy_changes(self):
        from contextlib import nullcontext
        import threading
        from pipeline import Pipelines
        for project, domain in (('graph_create', 'graphs.create'),
                                ('graph_create_external', 'graphs.create_external'),
                                ('graph_save', 'graphs.save')):
            expected = copy.deepcopy(agent_api.operation(domain)['inputSchema'])
            expected['properties'].update(copy.deepcopy(agent_api._PROJECT_FILES_MUTATION))
            expected['required'] = list(dict.fromkeys(expected['required'] + list(agent_api._PROJECT_FILES_MUTATION)))
            self.assertEqual(agent_api.operation('project_files.' + project)['inputSchema'], expected)
        # The real metadata owner authors each model graph without a worker or
        # runtime. Only its SQL transaction sink is substituted in this grammar test.
        owner = object.__new__(Pipelines)
        owner.lock = threading.RLock()
        owner.access = Mock()
        owner.db = SimpleNamespace(transaction=lambda: nullcontext(), execute=Mock())
        for recipe in ('image_classification_model_v2', 'text_classification_model_v2', 'audio_classification_model_v2'):
            body = {'name': 'Current typed model graph', 'release_id': SHA, 'recipe': recipe}
            graph = owner.create(body)
            agent_api.validate_arguments('project_files.graph_create', dict(BOUND, **body))
            agent_api.validate_arguments('project_files.graph_save', dict(BOUND,
                graph_id=graph['id'], revision=graph['revision'], document=graph))
            with self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_arguments('graphs.create', body, version=1)
        self.assertEqual(agent_api.REGISTRY_DIGEST, agent_api._LEGACY_DIGEST)

    def test_history_pages_are_bounded_and_keep_exact_owner_snapshots(self):
        selected = projection()
        snapshots = [{'id': RECORD, 'revision': revision, 'text': '\U0001f9ea' * 200000}
                     for revision in range(6, 0, -1)]
        selected.data.history.return_value = snapshots
        arguments = dict(READ, record_id=RECORD, offset=1, limit=4)
        value = dispatch(selected, 'project_files.data_history', arguments)
        self.assertEqual(value, {'items': snapshots[1:5], 'total': 6, 'offset': 1, 'limit': 4})
        agent_api.validate_output('project_files.data_history', {'status': 200, 'result': {
            'binding': READ['binding'], 'project_id': PROJECT, 'checkpoint': CHECKPOINT, 'value': value}})
        self.assertLess(len(agent_api.encoded(value, ensure_ascii=False)), agent_api.RESPONSE_LIMIT)
        with self.assertRaises(WorkbenchError):
            dispatch(selected, 'project_files.data_history', dict(arguments, limit=5))

    def test_study_summary_pages_membership_without_losing_full_charge_totals(self):
        selected = projection()
        trial_ids = [format(index, '032x') for index in range(10000)]
        original = {'study': {'format': 'study_v1', 'id': RECORD, 'name': 'Scientific intent',
                             'revision': 3, 'trial_ids': trial_ids},
                    'reservations': [], 'charged': {'attempt_slots': 10000},
                    'revision_history_complete': True,
                    'page': {'offset': 40, 'limit': 20, 'total': 0, 'study_revision': 3, 'next_offset': None}}
        selected.history.study.return_value = original
        result = dispatch(selected, 'project_files.study', dict(READ, study_id=RECORD,
            origin_catalog_id=ORIGIN, offset=40, limit=20, revision=3))
        self.assertNotIn('trial_ids', result['study'])
        self.assertEqual(result['study']['source_format'], 'study_v1')
        self.assertEqual(result['study']['trial_count'], 10000)
        self.assertEqual(result['trials'], {'items': [{'id': identity} for identity in trial_ids[40:60]],
                                          'total': 10000, 'offset': 40, 'limit': 20})
        self.assertEqual(result['charged'], {'attempt_slots': 10000})
        self.assertEqual(original['study']['trial_ids'], trial_ids)

    def test_material_replay_still_checks_current_reconciliation_authority(self):
        selected = projection()
        selected.session.access = Authority(deny_owner=True)
        selected.session.mutate = Mock(return_value={'ref': {'sha256': SHA}})
        selected.materials = ProjectMaterial(selected.session)
        arguments = dict(BOUND, model_id=RECORD, revision=1, reconcile_capture=True)
        with self.assertRaises(WorkbenchError) as failure:
            dispatch(selected, 'project_files.model_publish', arguments)
        self.assertEqual(failure.exception.code, 'forbidden')
        selected.session.mutate.assert_not_called()
        selected.context.models.publish.assert_not_called()
        # Ordinary publication retains its actual edit-agent policy and may
        # reconcile an original durable result without invoking the publisher.
        result = dispatch(selected, 'project_files.model_publish', dict(arguments, reconcile_capture=False))
        self.assertEqual(result, {'ref': {'sha256': SHA}})
        selected.session.mutate.assert_called_once()
        selected.context.models.publish.assert_not_called()

    def test_current_owner_root_choice_and_local_disclosure_use_their_owners(self):
        selected = projection()
        selected.session.access = Authority(deny_owner=True)
        with self.assertRaises(WorkbenchError):
            dispatch(selected, 'project_files.source_register', dict(BOUND, root='fixture', manifest_path='owned/manifest.json'))
        selected.source_adapter.register.assert_not_called()
        selected = projection()
        dispatch(selected, 'project_files.expose_holdout', dict(BOUND, run_id=RECORD, origin_catalog_id=ORIGIN, reason='Review held-out diagnostics'))
        selected.disclose.assert_called_once_with(RECORD, {'origin_catalog_id': ORIGIN, 'reason': 'Review held-out diagnostics'}, CHECKPOINT, BOUND['request_key'])
        selected.history.record_disclosure.assert_not_called()

    def test_explicit_preparation_keeps_runtime_and_sequence_semantics_with_owners(self):
        selected = projection()
        files = {'owned-input': 'original opaque bytes'}
        prepared = {'bundle': b'validated native source'}
        selected.data.workbench.sequences.prepare_project_files.return_value = prepared
        arguments = dict(BOUND, files=files, groups=['fixture'], rights='Authored')
        dispatch(selected, 'project_files.data_import_sequence', arguments)
        selected.data.workbench.sequences.prepare_project_files.assert_called_once_with(files)
        selected.data.import_bundle.assert_called_once_with('sequence', prepared,
            {'files': files, 'groups': ['fixture'], 'rights': 'Authored'}, CHECKPOINT, BOUND['request_key'])
        ref = {'kind': 'model', 'catalog_id': PROJECT, 'id': RECORD, 'revision': 1, 'sha256': SHA}
        dispatch(selected, 'project_files.recipe_prepare', dict(BOUND, graph_id=RECORD, revision=1, model=ref))
        selected.materials.prepare_recipe.assert_called_once_with(selected.context.pipelines, RECORD, 1, ref,
            CHECKPOINT, BOUND['request_key'], builtin=False, reconcile_capture=False, runtime_manifest=selected.runtime_manifest)

    def test_producer_inspection_preserves_origin_and_entry_pagination(self):
        selected = projection()
        args = dict(READ, family='generation_history', origin_catalog_id=ORIGIN, producer_id=RECORD,
                    entries_offset=40, entries_limit=20)
        agent_api.validate_arguments('project_files.producer', args)
        dispatch(selected, 'project_files.producer', args)
        selected.producers.get.assert_called_once_with('generation_history', RECORD,
            origin_catalog_id=ORIGIN, entries_offset=40, entries_limit=20)
        selected.producers.capture.assert_not_called()

    def test_run_summary_keeps_counts_and_exact_document_without_unbounded_collections(self):
        selected = projection()
        large = [{'state': 'observed', 'message': 'unique observation'}] * 100000
        selected.history.run.return_value = {
            'origin_catalog_id': ORIGIN, 'historical': True, 'execution_available': False,
            'evidence': 'unverified', 'run': {'schema_version': 1, 'id': RECORD, 'state': 'completed',
                'events': large, 'material': {'captured': 'large exact original document'}},
            'payloads': [], 'disclosures': [], 'document': {'sha256': SHA, 'bytes': 20000000},
            'page': {'offset': 40, 'limit': 20, 'total': 0, 'next_offset': None,
                     'disclosures_total': 0, 'disclosures_next_offset': None}}
        result = dispatch(selected, 'project_files.run', dict(READ, origin_catalog_id=ORIGIN,
                          run_id=RECORD, offset=40, limit=20))
        self.assertEqual(result['run']['state'], 'completed')
        self.assertEqual(result['run']['collection_counts']['events'], 100000)
        self.assertNotIn('events', result['run'])
        self.assertNotIn('material', result['run'])
        self.assertEqual(result['document'], {'sha256': SHA, 'bytes': 20000000})
        self.assertLess(len(agent_api.encoded(result)), 4096)
        selected.history.run.assert_called_once_with(RECORD, origin_catalog_id=ORIGIN, offset=40, limit=20)

    def test_document_segments_delegate_exact_hash_and_current_origin(self):
        selected = projection()
        arguments = dict(READ, run_id=RECORD, origin_catalog_id=ORIGIN, expected_sha256=SHA,
                         offset=262144, limit=262144)
        agent_api.validate_arguments('project_files.run_document_segment', arguments)
        dispatch(selected, 'project_files.run_document_segment', arguments)
        selected.history.run_document_segment.assert_called_once_with(RECORD, origin_catalog_id=ORIGIN,
            expected_sha256=SHA, offset=262144, limit=262144)
        # Source listing is a current binding-aware owner read, not manifest
        # inference in a client or a generic walk of archived source records.
        reference = dict(origin_catalog_id=ORIGIN, project_id=RECORD, manifest_sha256=SHA)
        dispatch(selected, 'project_files.source_references', dict(READ, **reference, offset=40, limit=20))
        selected.source_adapter.references.assert_called_once_with(reference, offset=40, limit=20)

    def test_artifact_resolution_requires_current_owner_before_the_custody_seam(self):
        selected = projection()
        selected.session.access = Authority(deny_owner=True)
        arguments = dict(BOUND, sha256=SHA, root='fixture', path='observations/unique.bin')
        agent_api.validate_arguments('project_files.artifact_resolve', arguments)
        with self.assertRaises(WorkbenchError):
            dispatch(selected, 'project_files.artifact_resolve', arguments)
        selected.resolve_artifact.assert_not_called()
        selected.session.access = Authority()
        dispatch(selected, 'project_files.artifact_resolve', arguments)
        selected.resolve_artifact.assert_called_once_with(
            {'sha256': SHA, 'root': 'fixture', 'path': 'observations/unique.bin'}, CHECKPOINT, BOUND['request_key'])
        self.assertEqual(agent_api.contract('project_files.artifact_resolve')['authority'], 'owner')

    def test_artifact_inventory_never_opens_or_invents_payload_bytes(self):
        selected = projection()
        declaration = dict(format='project_artifact_v1', sha256=SHA, bytes=17)
        selected.session.snapshot['records'] = [{'family': 'project_artifact', 'id': SHA, 'document': declaration}]
        selected.artifacts.inspect.return_value = {'state': 'missing', 'expected_bytes': 17}
        value = dispatch(selected, 'project_files.artifacts', READ)
        self.assertEqual(value['items'][0]['availability']['state'], 'missing')
        self.assertEqual(value['items'][0]['bytes'], 17)
        selected.artifacts.read_blob.assert_not_called()
        selected.artifacts.publish_bytes.assert_not_called()
        with self.assertRaises(WorkbenchError) as failure:
            dispatch(selected, 'project_files.artifact_status', dict(READ, sha256='0' * 64))
        self.assertEqual(failure.exception.status, 404)


class BooleanQueries(unittest.TestCase):
    def test_sdk_and_http_select_canonical_boolean_queries(self):
        name = 'project_files.candidate'
        selection = (name, 1, agent_api.contract(name)['sha256'])
        for value in (False, True):
            arguments = dict(READ, candidate_id=RECORD, origin_catalog_id=ORIGIN, verify=value)
            method, target, body = agent_api.project_request(name, arguments)
            self.assertIn('verify=' + str(value).lower(), target)
            self.assertEqual(agent_api.validate_selected(selection, method, target, body), arguments)
            with self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_arguments(name, dict(arguments, verify=str(value).lower()))
        for invalid in ('True', 'False', '1', 'yes', ''):
            target = '/api/workspace/project-files/candidates/' + RECORD + '?binding=' + READ['binding'] + '&checkpoint=' + CHECKPOINT + '&origin_catalog_id=' + ORIGIN + '&verify=' + invalid
            with self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_selected(selection, 'GET', target, None)


if __name__ == '__main__':
    unittest.main()
