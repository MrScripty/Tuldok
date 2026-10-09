"""Regression for prior-report recursion and clean-checkout fixture relocation."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qa_qualification', ROOT / 'scripts/qualify_text_classification_local.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class QaQualification(unittest.TestCase):
    def test_relocated_lossless_inputs_match_archived_source_hashes(self):
        archive = json.loads((ROOT / 'docs/qa/historical-artifacts.json').read_text())
        self.assertEqual(len(archive['relocated_lossless_inputs']), 11)
        for row in archive['relocated_lossless_inputs']:
            data = (ROOT / row['path']).read_bytes()
            self.assertEqual(len(data), row['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
        for path in (ROOT / 'tests/fixtures/native-caption-release').rglob('*.png'):
            self.assertEqual(path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')

    def test_repeated_gate_outputs_never_recapture_prior_reports_or_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / 'tests/fixtures/qa/inherited-gates.json'
            registry.parent.mkdir(parents=True)
            registry.write_bytes((ROOT / 'tests/fixtures/qa/inherited-gates.json').read_bytes())
            inherited = json.loads(registry.read_text())['commands']
            command = 'node tests/output-fixture.cjs'
            workflow = root / '.github/workflows/tests.yml'
            workflow.parent.mkdir(parents=True)
            workflow.write_text('\n'.join('      - run: ' + c for c in inherited + list(qa.NEW_COMMANDS) + [command]))
            (root / 'requirements.txt').write_text('')
            (root / 'tests/output-fixture.cjs').write_text("const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');assert.equal(process.env.TULDOK_SOURCE_ROOT,path.resolve(__dirname,'..'));fs.writeFileSync(path.join(process.env.TULDOK_QA_OUTPUT_ROOT,'fresh.txt'),'new gate bytes');")
            historical = root / 'docs/plans/old/reports/component-artifacts/prior.txt'
            historical.parent.mkdir(parents=True)
            historical.write_text('old report bytes')
            old_run = root / 'build/qa/previous/artifacts/prior.txt'
            old_run.parent.mkdir(parents=True)
            old_run.write_text('previous run bytes')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'add', 'tests', '.github', 'requirements.txt'], cwd=root, check=True)
            subprocess.run(['git', '-c', 'user.name=QA fixture', '-c', 'user.email=qa@example.invalid', 'commit', '-qm', 'fixture'], cwd=root, check=True)
            args = ['qualify', '--only', 'output-fixture', '--report-root', str(root / 'build/qa/qualification'), '--python', sys.executable]
            with patch.object(qa, 'ROOT', root), patch.object(qa, 'consumer_blocker', return_value=None), patch.dict('os.environ', {'TULDOK_SOURCE_ROOT': str(root / 'wrong-checkout')}):
                for _ in range(2):
                    with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(qa.main(), 0)
                runs = sorted((root / 'build/qa/qualification').glob('run-*'))
                self.assertEqual(len(runs), 2)
                for run in runs:
                    rows = json.loads((run / 'gates/results.json').read_text())
                    self.assertEqual(len(rows), 1)
                    artifacts = rows[0]['component_artifacts']
                    self.assertEqual(len(artifacts), 1)
                    self.assertTrue(artifacts[0].endswith('/fresh.txt'))
                    self.assertEqual((root / artifacts[0]).read_text(), 'new gate bytes')
                    self.assertEqual(list(run.rglob('prior.txt')), [])
                resume = args + ['--resume']
                resume[resume.index('--report-root') + 1] = str(runs[-1])
                with patch.object(sys, 'argv', resume), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(qa.main(), 0)
                self.assertEqual(len(list((runs[-1] / 'gates').rglob('fresh.txt'))), 1)
                results_path = runs[-1] / 'gates/results.json'
                for mutation in ('corrupt', 'delete'):
                    prior = json.loads(results_path.read_text())[0]
                    path = root / prior['component_artifacts'][0]
                    if mutation == 'corrupt':
                        path.write_text('changed output bytes')
                    else:
                        path.unlink()
                    with patch.object(sys, 'argv', resume), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(qa.main(), 0)
                    current = json.loads(results_path.read_text())[0]
                    self.assertNotEqual(current['artifact_output_root'], prior['artifact_output_root'])
                    self.assertEqual((root / current['component_artifacts'][0]).read_text(), 'new gate bytes')
                    self.assertTrue(qa.artifacts_reusable(current, results_path.parent / 'node-tests-output-fixture.cjs'))
            self.assertEqual(historical.read_text(), 'old report bytes')
            self.assertEqual(old_run.read_text(), 'previous run bytes')

    def test_aggregate_rejects_source_and_report_output_roots(self):
        for path in [ROOT, ROOT / 'docs/plans/reports', ROOT / 'tests/fixtures']:
            with self.assertRaises(ValueError):
                qa.output_container(path)


if __name__ == '__main__':
    unittest.main()
