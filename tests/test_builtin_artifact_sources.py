"""Versioned built-in publication provenance; no fabricated external custody."""
import base64
import copy
import unittest
import recipe_process


class BuiltinArtifactSourceTests(unittest.TestCase):
    def source(self):
        raw = b'authored byte provenance fixture only'
        identity = {'dataset_id': 'a' * 32, 'run_id': 'b' * 32, 'graph_sha256': 'c' * 64,
                    'release_id': 'd' * 64, 'release_sha256': 'd' * 64}
        manifest = {'schema_version': 1, 'source_identity': identity, 'adapter': {'name': 'tinycnn_cpu', 'version': 2},
            'artifacts': [{'name': 'weights-epoch-0001.pt', 'sha256': recipe_process.digest(raw), 'bytes': len(raw),
                           'media_type': 'application/octet-stream', 'split': None}]}
        manifest_raw = recipe_process.encoded(manifest)
        return raw, {'schema_version': 2, 'kind': 'builtin_classifier_publication_v1',
            'catalog_id': identity['dataset_id'], 'run_id': identity['run_id'], 'request_sha256': 'e' * 64,
            'material_sha256': 'f' * 64, 'graph_sha256': identity['graph_sha256'],
            'release_sha256': identity['release_sha256'], 'adapter_sha256': '1' * 64,
            'artifact_name': 'weights-epoch-0001.pt', 'artifact_role': 'model_evidence',
            'artifact_bytes': len(raw), 'measured_sha256': recipe_process.digest(raw),
            'artifact_manifest_sha256': recipe_process.digest(manifest_raw),
            'artifact_manifest_base64': base64.b64encode(manifest_raw).decode(), 'population': 'train'}

    def test_exact_builtin_proof_has_distinct_version_and_no_external_custody(self):
        raw, source = self.source()
        self.assertEqual(recipe_process.validate_artifact_source(source, recipe_process.digest(raw), len(raw)), source)
        self.assertNotIn('custody_identity', source)
        self.assertNotIn('custody_receipt_base64', source)

    def test_changed_version_identity_manifest_weight_and_population_fail(self):
        raw, source = self.source()
        changes = [{'schema_version': 1}, {'schema_version': True}, {'kind': 'external'},
            {'run_id': 'c' * 32}, {'catalog_id': 'c' * 32}, {'graph_sha256': '0' * 64},
            {'artifact_name': 'other.pt'}, {'artifact_bytes': len(raw)+1}, {'artifact_bytes': True},
            {'measured_sha256': '0' * 64}, {'artifact_manifest_sha256': '0' * 64},
            {'artifact_manifest_base64': 'not-base64'}, {'population': 'unknown'}, {'population': 'test'}, {'population': 'validation'},
            {'custody_identity': {}}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(recipe_process.ProcessError):
                recipe_process.validate_artifact_source(dict(source, **change), recipe_process.digest(raw), len(raw))
        with self.assertRaises(recipe_process.ProcessError):
            recipe_process.validate_artifact_source(source, '0' * 64, len(raw))

    def test_manifest_rehash_cannot_change_selected_bytes_or_source_identity(self):
        raw, source = self.source()
        for field, value in (('run_id', 'c'*32), ('release_sha256', 'f'*64)):
            changed = copy.deepcopy(source)
            manifest = recipe_process.decode(base64.b64decode(source['artifact_manifest_base64']))
            manifest['source_identity'][field] = value
            contents = recipe_process.encoded(manifest)
            changed.update(artifact_manifest_base64=base64.b64encode(contents).decode(), artifact_manifest_sha256=recipe_process.digest(contents))
            with self.subTest(field=field), self.assertRaises(recipe_process.ProcessError):
                recipe_process.validate_artifact_source(changed, recipe_process.digest(raw), len(raw))


if __name__ == '__main__':
    unittest.main()
