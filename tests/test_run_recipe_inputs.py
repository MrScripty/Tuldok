"""Completed neutral Run inputs and generated evidence; no model qualification."""
import copy
import hashlib
import json
import unittest
import uuid
from unittest.mock import patch

import recipe_contract as contract
import recipe_process
from test_external_runs import ExternalCase, sha
from workbench import WorkbenchError


class RunRecipeInputs(ExternalCase):
    def completed_source(self):
        with self.owner.bound(self.dataset):
            run = self.dataset.runs.submit_external(self.body())
        self.await_state(run['id'], {'completed'})
        with self.owner.bound(self.dataset):
            return self.dataset.runs.get(run['id'])

    def downstream(self, source, evidence=False):
        body = self.graph_body()
        if evidence:
            definition = copy.deepcopy(self.definition)
            definition['arguments'].append({'input_evidence': True})
            raw = json.dumps(definition).encode()
            (self.project_path / 'recipe.json').write_bytes(raw)
            manifest = copy.deepcopy(self.manifest)
            manifest['id'] = uuid.uuid4().hex
            body['project_id'] = manifest['id']
            manifest['recipes'][0]['sha256'] = sha(raw)
            (self.project_path / 'project.json').write_text(json.dumps(manifest))
            self.dataset.projects.open({'root': 'fixture', 'manifest_path': 'project.json'})
            body['expected_sha256'] = sha(raw)
        artifact = source['artifacts'][0]
        body['inputs']['sample'] = {'kind': 'run_artifact', 'run_id': source['id'],
                                   'artifact_name': artifact['name'], 'expected_sha256': artifact['sha256']}
        return self.dataset.pipelines.create_external(body)

    def test_actual_completed_input_capture_and_cold_evidence(self):
        source = self.completed_source()
        with self.owner.bound(self.dataset):
            graph = self.downstream(source, evidence=True)
            preflight = self.dataset.pipelines.preflight_external(graph['id'], 1)
            target = self.path / 'downstream'
            capture = self.dataset.pipelines.capture_external(graph['id'], 1, preflight['material_sha256'], target)
            inputs = capture['material']['inputs']
            self.assertEqual(inputs['sample']['kind'], 'run_artifact')
            self.assertEqual(inputs['sample']['source']['run_id'], source['id'])
            self.assertEqual(json.loads((target / contract.INPUT_EVIDENCE).read_bytes()), inputs)
            self.assertIn(str(target / contract.INPUT_EVIDENCE), capture['spec']['argv'])
            recipe_process.validate_spec(dict(capture['spec'], attempt_id='d'*32, request_sha256='e'*64))
            original = self.dataset.runs.path / source['id'] / source['artifacts'][0]['name']
            self.assertEqual((target / 'input/sample').read_bytes(), original.read_bytes())
            original.unlink()
            contract.validate_spec(capture['material'], capture['spec'], target)
            with self.assertRaises(WorkbenchError):
                self.dataset.pipelines.preflight_external(graph['id'], 1)
        for mutate in (lambda m: m['inputs']['sample']['source'].update(catalog_id='f'*32),
                       lambda m: m['inputs']['sample']['source'].update(artifact_bytes=1),
                       lambda m: m['inputs']['sample']['source'].update(material_sha256='f'*64),
                       lambda m: m['captures'][contract.INPUT_EVIDENCE].update(sha256='f'*64)):
            changed = copy.deepcopy(capture['material'])
            mutate(changed)
            with self.assertRaises(WorkbenchError):
                contract.validate_material(changed)

    def test_input_drift_and_mixed_binding_refuse_before_capture(self):
        source = self.completed_source()
        with self.owner.bound(self.dataset):
            graph = self.downstream(source)
            before = self.dataset.pipelines.preflight_external(graph['id'], 1)
            self.assertNotIn(contract.INPUT_EVIDENCE, before['material']['captures'])
            edited = copy.deepcopy(graph)
            binding = edited['nodes'][0]['parameters']['inputs']['sample']
            binding['reference_id'] = 'sample'
            bad = self.dataset.pipelines.save(graph['id'], {'revision': 1, 'document': edited})
            with self.assertRaises(WorkbenchError):
                self.dataset.pipelines.preflight_external(bad['id'], 2)
            graph = self.downstream(source)
            artifact = self.dataset.runs.path / source['id'] / source['artifacts'][0]['name']
            artifact.write_bytes(b'changed')
            with patch('subprocess.Popen', side_effect=AssertionError('Input capture executed code')):
                with self.assertRaises(WorkbenchError):
                    self.dataset.pipelines.capture_external(graph['id'], 1, before['material_sha256'], self.path / 'refused')
            self.assertFalse((self.path / 'refused').exists())


if __name__ == '__main__':
    unittest.main()
