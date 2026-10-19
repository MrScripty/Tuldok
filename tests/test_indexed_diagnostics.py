"""Bounded diagnostic protocol evidence; synthetic JSON is never a science claim."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import extension_evidence as host
import recipe_contract
from tuldok_extension_sdk import diagnostics
from tuldok_extension_sdk.evidence import Evidence, EvidenceError
from workbench import WorkbenchError
from test_extension_field_evidence import authored_fixture


def opt_in(definition):
    """A fresh explicit policy, preserving every old science output/grammar."""
    policy = definition['model_evidence']
    policy['format'] = diagnostics.POLICY_FORMAT
    case = policy['probe']['candidates'][0]['frozen_reference']['member_id']
    capture = dict(format=diagnostics.CAPTURE_FORMAT, payload_schema=diagnostics.PAYLOAD_SCHEMA,
        index=dict(name='diagnostic-index.json', max_bytes=16384),
        shards=[dict(name=f'diagnostic-{ordinal}.json', max_bytes=8192) for ordinal in range(2)],
        records_per_shard=3, max_record_bytes=1024, phases=['serialization'], coverage=[
            dict(case_id=case, checkpoint_point=16, phase='serialization', required_count=1, optional_count=2),
            dict(case_id=case, checkpoint_point=32, phase='serialization', required_count=1, optional_count=1)])
    policy['diagnostic_capture'] = capture
    for artifact, role, required in [(capture['index'], diagnostics.INDEX_ROLE, True),
                                     *((item, diagnostics.SHARD_ROLE, False) for item in capture['shards'])]:
        definition['outputs'].append(dict(path=artifact['name'], max_bytes=artifact['max_bytes'], role=role, required=required))
    return capture


def indexed_fixture(root):
    definition, model, composition, run, _legacy_writer = authored_fixture(root)
    capture = opt_in(definition)
    recipe_contract.decode_definition(host.canonical(definition))
    execution = run['material']
    static = host.resolve(definition['model_evidence'], model, execution)
    run['material_sha256'] = host.digest(execution)
    composition['material']['executable_sha256'] = run['material_sha256']
    context = host.context(static, composition['ref'], run['id'], run['request_sha256'])
    context_raw = host.canonical(context)
    run['extension_context'] = context
    run['spec']['model_evidence_context'].update(bytes=len(context_raw), sha256=hashlib.sha256(context_raw).hexdigest())
    for path in root.glob('*.json'):
        if path.name != 'diagnostics.json':
            path.unlink()
    writer = Evidence(root, context_raw)
    writer.transform('transform.npy')
    for point in (16, 32, 48, 64):
        writer.checkpoint(point, dict(optimizer_update=point, epoch=None, fit_pass=None, physical_time=None, wall_elapsed_ms=point),
                          f'weights-{point}.npy', dict(reference_mse=0))
    writer.finish()
    checkpoints = {entry['clocks']['optimizer_update']: entry['checkpoint']['sha256'] for entry in writer.entries}
    records = [dict(ordinal=ordinal, case_id=capture['coverage'][0]['case_id'], checkpoint_point=point,
                    checkpoint_sha256=checkpoints[point], phase='serialization',
                    payload=dict(scope='synthetic protocol JSON; no training', label=str(ordinal)))
               for ordinal, point in ((0, 16), (1, 16), (3, 32), (4, 32))]
    omitted = [dict(start=2, count=1, reason='capture_budget')]
    index = writer.diagnostics(records, omitted)
    refresh_inventory(root, run)
    return definition, run, writer, records, omitted, index


def refresh_inventory(root, run):
    run['artifacts'] = [dict(name=row['path'], role=row['role'], bytes=(root / row['path']).stat().st_size,
        sha256=hashlib.sha256((root / row['path']).read_bytes()).hexdigest(), media_type='application/octet-stream')
        for row in run['outputs'] if (root / row['path']).is_file()]


class DiagnosticAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.definition = json.loads((Path(__file__).resolve().parents[1] / 'examples/extensions/field-surrogate/v2/recipe.json').read_bytes())
        self.capture = opt_in(self.definition)

    def decode(self):
        with patch('subprocess.Popen', side_effect=AssertionError('Diagnostic admission launched compute')):
            return recipe_contract.decode_definition(host.canonical(self.definition))

    def test_explicit_opt_in_keeps_profile_and_closed_science_capabilities(self):
        self.assertEqual(self.decode(), self.definition)
        self.assertEqual(self.definition['model_evidence']['profile']['required_capabilities'], host.CAPABILITIES)
        self.assertEqual(self.definition['model_evidence']['profile']['optional_capabilities'], [])
        self.assertIn('tuldok_extension_sdk/diagnostics.py', recipe_contract.recipe_host_identity(self.definition))
        self.assertEqual(diagnostics.POLICY_FORMAT, recipe_contract.INDEXED_POLICY_FORMAT)
        legacy = json.loads((Path(__file__).resolve().parents[1] / 'examples/extensions/field-surrogate/v2/recipe.json').read_bytes())
        self.assertEqual(set(recipe_contract.recipe_host_identity(legacy)), set(recipe_contract.EVIDENCE_HOST_NAMES))

    def test_impossible_population_record_index_and_aggregate_declarations_refuse_inertly(self):
        changes = [
            lambda: self.capture['coverage'][0].update(required_count=7),
            lambda: self.capture.update(max_record_bytes=8192),
            lambda: self.capture.update(max_record_bytes=1),
            lambda: self.definition['model_evidence']['profile']['limits'].update(total_output_bytes=920000),
        ]
        original = copy.deepcopy(self.definition)
        for change in changes:
            with self.subTest(change=change):
                self.definition = copy.deepcopy(original)
                self.capture = self.definition['model_evidence']['diagnostic_capture']
                change()
                with self.assertRaises(WorkbenchError) as caught:
                    self.decode()
                self.assertEqual(caught.exception.code, 'unsupported')

    def test_addon_requires_explicit_tag_and_exact_output_roles(self):
        original = copy.deepcopy(self.definition)
        for change in (
            lambda: self.definition['model_evidence'].update(format=host.POLICY_FORMAT),
            lambda: self.definition['outputs'][-1].update(role='arbitrary_diagnostic'),
            lambda: self.definition['outputs'][-1].update(required=True),
            lambda: self.capture['coverage'][0].update(case_id='unadmitted-case'),
            lambda: self.capture['coverage'][0].update(checkpoint_point=17),
            lambda: self.capture['coverage'][0].update(phase='unadmitted-phase'),
        ):
            with self.subTest(change=change):
                self.definition = copy.deepcopy(original)
                self.capture = self.definition['model_evidence']['diagnostic_capture']
                change()
                with self.assertRaises(WorkbenchError): self.decode()

    def test_bound_recipe_selects_the_same_addon_with_its_existing_target_contract(self):
        self.definition = json.loads((Path(__file__).resolve().parents[1] /
            'examples/extensions/field-surrogate-b-independent/v1/recipe.json').read_bytes())
        self.capture = opt_in(self.definition)
        self.capture['coverage'][0]['checkpoint_point'] = 32
        self.capture['coverage'][1]['checkpoint_point'] = 64
        self.assertEqual(self.decode(), self.definition)
        self.assertTrue(recipe_contract.is_bound_evidence(self.definition))
        self.assertIn('field_targets', self.definition['model_evidence'])
        self.assertEqual(set(recipe_contract.recipe_host_identity(self.definition)),
            set(recipe_contract.BOUND_EVIDENCE_HOST_NAMES) | set(recipe_contract.DIAGNOSTIC_HOST_NAMES))


class DiagnosticRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.definition, self.run, self.writer, self.records, self.omitted, self.index = indexed_fixture(self.root)
        self.capture = self.definition['model_evidence']['diagnostic_capture']

    def verify(self):
        return host.verify(self.root, self.run, self.run['extension_context'])

    def rewrite(self, filename, value, refresh=True):
        (self.root / filename).write_bytes(host.canonical(value) + b'\n')
        if refresh: refresh_inventory(self.root, self.run)

    def test_supported_sdk_two_shards_cold_host_and_unchanged_public_projection(self):
        with patch('subprocess.Popen', side_effect=AssertionError('Diagnostic verification launched compute')):
            verified = self.verify()
            self.assertEqual(verified['_diagnostics'], self.index)
            cold = host.verify(Path(str(self.root)), copy.deepcopy(self.run), copy.deepcopy(self.run['extension_context']))
            self.assertEqual(cold['_diagnostics'], self.index)
            self.assertEqual(len(self.index['shards']), 2)
            self.assertEqual(self.index['coverage'], dict(total_count=5, required_count=2, optional_count=3,
                retained_required_count=2, retained_optional_count=2, omitted_count=1, omitted=self.omitted))
            self.assertNotIn('_diagnostics', host.query(verified))
            self.assertNotIn('diagnostics', host.query(verified))
            import agent_api
            client = agent_api.AgentClient('http://127.0.0.1:12345', 'x' * 32, self.run['dataset_id'])
            client._ready = True; client._selected = {'runs.model_evidence': 2}
            response = {'status': 200, 'result': host.query(verified)}
            with patch.object(client, '_request', return_value=response):
                self.assertEqual(client.call('runs.model_evidence', {'run_id': self.run['id']}), response)
            self.assertEqual(set(verified['manifest']), {'format', 'schema_version', 'producer', 'task', 'model_sha256',
                'data_sha256', 'profile_sha256', 'probe', 'metric_definitions', 'checkpoints', 'observations', 'field_index', 'coverage', 'inference'})

    def test_current_host_inventory_hash_still_dominates_forged_coherent_index(self):
        shard = json.loads((self.root / 'diagnostic-0.json').read_bytes())
        shard['records'][0]['payload']['label'] = 'mutated'
        self.rewrite('diagnostic-0.json', shard, refresh=False)
        index = copy.deepcopy(self.index)
        index['shards'][0]['blob'] = dict(
            name='diagnostic-0.json', bytes=(self.root / 'diagnostic-0.json').stat().st_size,
            sha256=hashlib.sha256((self.root / 'diagnostic-0.json').read_bytes()).hexdigest(), media_type='application/json')
        self.rewrite('diagnostic-index.json', index, refresh=False)
        with self.assertRaisesRegex(WorkbenchError, 'authoritative retained artifact'):
            self.verify()

    def test_index_identity_order_count_ranges_media_and_mandatory_coverage_refuse(self):
        for change in (
            lambda index: index.update(capture_sha256='f' * 64),
            lambda index: index.update(material_sha256='f' * 64),
            lambda index: index['shards'].reverse(),
            lambda index: index['shards'][0].update(record_count=2),
            lambda index: index['shards'][0].update(first_ordinal=1),
            lambda index: index['shards'][0]['blob'].update(media_type='text/plain'),
            lambda index: index['coverage'].update(omitted_count=2),
            lambda index: index['coverage'].update(omitted=[dict(start=0, count=1, reason='capture_budget')]),
            lambda index: index['coverage'].update(omitted=[dict(start=2, count=1, reason='unknown')]),
        ):
            with self.subTest(change=change):
                changed = copy.deepcopy(self.index); change(changed)
                self.rewrite('diagnostic-index.json', changed)
                with self.assertRaises(WorkbenchError): self.verify()
        self.rewrite('diagnostic-index.json', self.index)

    def test_forged_shard_case_checkpoint_phase_order_and_payload_refuse(self):
        original = (self.root / 'diagnostic-0.json').read_bytes()
        for change in (
            lambda row: row.update(case_id='unadmitted'),
            lambda row: row.update(checkpoint_sha256='f' * 64),
            lambda row: row.update(phase='unadmitted'),
            lambda row: row.update(ordinal=1),
            lambda row: row.update(payload=[]),
            lambda row: row.update(payload=dict(text='a' * 1024)),
        ):
            with self.subTest(change=change):
                shard = json.loads(original); change(shard['records'][0])
                self.rewrite('diagnostic-0.json', shard)
                index = copy.deepcopy(self.index); raw = (self.root / 'diagnostic-0.json').read_bytes()
                index['shards'][0]['blob'].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                self.rewrite('diagnostic-index.json', index)
                with self.assertRaises(WorkbenchError): self.verify()

    def test_diagnostic_capture_never_repairs_invalid_scientific_evidence(self):
        (self.root / 'reference.npy').write_bytes(b'invalid scientific array')
        refresh_inventory(self.root, self.run)
        with patch.object(diagnostics, 'verify', side_effect=AssertionError('Invalid science reached diagnostic verifier')):
            with self.assertRaises(WorkbenchError): self.verify()

    def test_sdk_refuses_missing_mandatory_or_unexplained_optional_records_before_writing(self):
        for records, omitted in ((self.records[1:], self.omitted), (self.records, []),
                (self.records, [dict(start=0, count=1, reason='not_available')])):
            with self.subTest(records=records, omitted=omitted):
                before = self.writer.inventory()
                with self.assertRaises(EvidenceError): self.writer.diagnostics(records, omitted)
                self.assertEqual(before, self.writer.inventory())


if __name__ == '__main__': unittest.main()
