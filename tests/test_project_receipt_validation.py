"""One mixed candidate: retain every receipt check without repeated decoding."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_files as files
import project_material as material
import project_measurements as measurements
import project_projection as projection
import project_sources as sources
from project_artifacts import ProjectArtifacts, ProjectArtifactError
from project_store import ProjectStore
from test_retained_measurements import fixture
from workbench import WorkbenchError

PROJECT = 'a' * 32
ACTOR = 'c' * 32
INSTANT = '2026-10-25T00:00:00+00:00'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def operation(name, key, result):
    return dict(family='project_operation', id=PROJECT + '.' + sha(key.encode()), document=dict(
        format='project_operation_v2', project_id=PROJECT, operation=name,
        target=None, request_key=key, input_sha256='d' * 64, result=copy.deepcopy(result)))


def candidate():
    packets = []
    for index in range(2):
        value = fixture()
        value['title'] = f'Packet {index}'
        raw = json.dumps(value).encode()
        packets.append(dict(raw=raw, sha256=sha(raw), path=f'packet-{index}.json',
                            reference_id=f'packet-{index}', title=value['title']))
    manifest = dict(schema_version=1, id='b' * 32, name='Receipt source',
        data=[dict(id=p['reference_id'], label=p['title'], path=p['path'], sha256=p['sha256'])
              for p in packets], recipes=[], evidence=[], requirements=[])
    raw = json.dumps(manifest).encode()
    digest = sha(raw)
    snapshot = dict(id=manifest['id'], name=manifest['name'], root='original',
        root_identity=[1, 2], manifest_path='source.json', manifest_sha256=digest, manifest=manifest)
    retained = dict(family='project_snapshot', id=PROJECT + '.' + digest, document=dict(
        format=material.FAMILIES['project_snapshot'], origin_catalog_id=PROJECT, value=snapshot,
        artifacts=[dict(name='source.json', blob=dict(sha256=digest, bytes=len(raw)),
            role='project_manifest', preservation='unique', required_for=['snapshot_verification'])], audit=[]))
    records = [retained]
    for hashed, size in [(digest, len(raw)), *[(p['sha256'], len(p['raw'])) for p in packets]]:
        records.append(dict(family='project_artifact', id=hashed,
            document=dict(format='project_artifact_v1', sha256=hashed, bytes=size)))
    source_result = dict(origin_catalog_id=PROJECT, project_id=manifest['id'], manifest_sha256=digest,
        name=manifest['name'], schema_version=1, actor_id=ACTOR, registered_at=INSTANT)
    for index in range(2):
        records.append(operation('source.register', f'source-{index}', source_result))
    for index, packet in enumerate(packets):
        doc = dict(format=measurements.FORMAT, origin_catalog_id=PROJECT, id=packet['sha256'],
            title=packet['title'], blob=dict(sha256=packet['sha256'], bytes=len(packet['raw'])),
            source=dict(origin_catalog_id=PROJECT, project_id=manifest['id'], manifest_sha256=digest,
                reference_id=packet['reference_id'], path=packet['path'], measured_sha256=packet['sha256']),
            actor_id=ACTOR, imported_at=INSTANT)
        records.append(dict(family=measurements.FAMILY, id=PROJECT + '.' + packet['sha256'], document=doc))
        records.append(operation('measurements.import', f'packet-{index}', doc))
    for batch in range(2):
        items = []
        for index in range(2):
            path = f'notes/note-{batch}-{index}.md'
            raw = f'Owned note {batch}-{index} 山'.encode()
            version = dict(revision=1, sha256=sha(raw), bytes=len(raw), text=raw.decode(),
                           adopted_at=INSTANT, actor_id=ACTOR)
            identity = files.file_id(PROJECT, 'note', path)
            doc = dict(format=files.FORMAT, project_id=PROJECT, kind='note', path=path,
                       current=copy.deepcopy(version), history=[version], origin=None)
            records.append(dict(family=files.FAMILY, id=identity, document=doc))
            items.append(dict(id=identity, project_id=PROJECT, kind='note', path=path, changed=True,
                              **{key: version[key] for key in ('revision', 'sha256', 'bytes', 'adopted_at')}))
        records.append(operation('files.adopt_many', f'notes-{batch}', dict(items=items, changed_count=2)))
    return records


class ReceiptValidationTests(unittest.TestCase):
    def test_whole_candidate_decodes_each_receipt_owner_once(self):
        records = candidate()
        before = copy.deepcopy(records)
        with patch.object(files, 'decode_records', wraps=files.decode_records) as file_decode, \
                patch.object(projection, 'decode_file_records', file_decode), \
                patch.object(measurements, 'decode_records', wraps=measurements.decode_records) as measurement_decode, \
                patch.object(projection, 'decode_measurement_records', measurement_decode), \
                patch.object(material, 'decode_records', wraps=material.decode_records) as material_decode, \
                patch.object(measurements, 'material_records', material_decode), \
                patch.object(sources, 'material_records', material_decode):
            projection.validate_project_records(records, project_id=PROJECT, artifacts=None)
        self.assertEqual(records, before)
        for name, actual, expected in [('files', file_decode.call_count, 1),
                                      ('measurements', measurement_decode.call_count, 1),
                                      ('material-owning readers', material_decode.call_count, 3)]:
            with self.subTest(owner=name):
                self.assertEqual(actual, expected, 'Receipt validation redecoded the same candidate')

    def test_standalone_file_batch_decodes_inventory_once(self):
        records = candidate()
        result = next(r['document']['result'] for r in records
                      if r['family'] == 'project_operation'
                      and r['document']['operation'] == 'files.adopt_many')
        with patch.object(files, 'decode_records', wraps=files.decode_records) as decode:
            self.assertTrue(files.validate_operation_result('files.adopt_many', result, records))
        self.assertEqual(decode.call_count, 1, 'Each batch item decoded the full file inventory')

    def test_forged_late_file_or_measurement_receipt_is_rejected(self):
        for owner in ('files.adopt_many', 'measurements.import', 'source.register'):
            records = candidate()
            result = [r['document']['result'] for r in records if r['family'] == 'project_operation'
                      and r['document']['operation'] == owner][-1]
            if owner == 'files.adopt_many':
                result['items'][-1]['sha256'] = 'e' * 64
            else:
                result['name' if owner == 'source.register' else 'title'] = 'Forged retained value'
            with self.subTest(owner=owner), self.assertRaises(WorkbenchError):
                projection.validate_project_records(records, project_id=PROJECT, artifacts=None)

    def test_unknown_operation_still_has_no_accepting_owner(self):
        records = candidate()
        records.append(operation('unknown.capture', 'unknown', {}))
        with self.assertRaises(WorkbenchError) as error:
            projection.validate_project_records(records, project_id=PROJECT, artifacts=None)
        self.assertEqual(error.exception.code, 'unsupported')

    def test_owned_validators_and_standalone_calls_do_not_share_candidates(self):
        for name, module in [('files.adopt_many', files), ('measurements.import', measurements),
                             ('source.register', sources)]:
            records = candidate()
            original_result = copy.deepcopy(next(r['document']['result'] for r in records
                if r['family'] == 'project_operation' and r['document']['operation'] == name))
            checker = module.receipt_validator(records)
            self.assertTrue(checker(name, original_result))
            self.assertTrue(module.validate_operation_result(name, original_result, records))
            if module is files:
                doc = next(r['document'] for r in records if r['family'] == files.FAMILY)
                value = doc['history'][0]
                value.update(text='Edited candidate', sha256=sha(b'Edited candidate'), bytes=16)
                doc['current'] = copy.deepcopy(value)
            elif module is measurements:
                next(r['document'] for r in records if r['family'] == measurements.FAMILY)['title'] = 'Edited candidate'
            else:
                value = next(r['document']['value'] for r in records if r['family'] == 'project_snapshot')
                value['name'] = value['manifest']['name'] = 'Edited candidate'
            with self.subTest(owner=name):
                self.assertTrue(checker(name, original_result), 'Owned candidate changed with caller mutation')
                with self.assertRaises(WorkbenchError):
                    module.receipt_validator(records)(name, original_result)
                with self.assertRaises(WorkbenchError):
                    module.validate_operation_result(name, original_result, records)

    def test_standalone_unrecognized_and_malformed_results_do_not_decode(self):
        for name, module in [('files.adopt_many', files), ('measurements.import', measurements),
                             ('source.register', sources)]:
            records = candidate()
            attribute = 'material_records' if module is sources else 'decode_records'
            with self.subTest(owner=name), patch.object(module, attribute,
                    side_effect=AssertionError('Result shape must precede candidate decoding')) as decode:
                self.assertFalse(module.validate_operation_result('unknown.capture', {}, records))
                with self.assertRaises(WorkbenchError):
                    module.validate_operation_result(name, {}, records)
                decode.assert_not_called()

    def test_unused_malformed_file_and_missing_packet_reference_still_reject(self):
        records = candidate()
        next(r['document']['history'][0] for r in records if r['family'] == files.FAMILY)['text'] = 'Unhashed'
        records = [r for r in records if r['family'] != 'project_operation'
                   or r['document']['operation'] != 'files.adopt_many']
        with self.assertRaises(WorkbenchError):
            projection.validate_project_records(records, project_id=PROJECT, artifacts=None)
        records = candidate()
        next(r['document'] for r in records if r['family'] == measurements.FAMILY)['source']['reference_id'] = 'absent'
        with self.assertRaises(WorkbenchError):
            projection.validate_project_records(records, project_id=PROJECT, artifacts=None)

    def test_each_new_measurement_validator_checks_actual_packet_bytes(self):
        records = candidate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            with ProjectStore.create(root, 'Packet custody fixture', 'create', 'a' * 64) as store:
                with ProjectArtifacts(store) as artifacts:
                    docs = [r['document'] for r in records if r['family'] == measurements.FAMILY]
                    for index, doc in enumerate(docs):
                        packet = fixture()
                        packet['title'] = f'Packet {index}'
                        raw = json.dumps(packet).encode()
                        self.assertEqual(sha(raw), doc['id'])
                        artifacts.publish_bytes(raw, measurements.declaration(doc['blob']))
                    checker = measurements.receipt_validator(records, artifacts=artifacts)
                    self.assertTrue(checker('measurements.import', docs[0]))
                    payload = root / 'artifacts/sha256' / docs[0]['id']
                    raw = payload.read_bytes()
                    payload.chmod(0o600)
                    payload.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                    with self.assertRaises((WorkbenchError, ProjectArtifactError)):
                        measurements.receipt_validator(records, artifacts=artifacts)
