"""Independent repair probes using a temporary synthetic repository/report tree."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/workspace/Tuldok')
spec = importlib.util.spec_from_file_location('qualification_runner_review', ROOT / 'scripts/qualify_text_classification_local.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ReportIsolationReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prior_root = self.root / 'docs/plans/text-classification-proposals/reports'
        self.fresh = self.prior_root / 'publication-qualification/fresh-run'
        self.prior = self.prior_root / 'gates/old.log'
        self.historical = self.root / 'docs/plans/inherited/reports/history.txt'
        for path, data in ((self.prior, b'prior classification evidence'), (self.historical, b'inherited evidence')):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.inherited = self.root / 'inherited-gates.json'
        generated = self.prior_root / 'new-report.txt'
        code = ('from pathlib import Path; '
            f'Path({str(self.prior)!r}).write_text("independent-gate-marker current output"); '
            f'Path({str(generated)!r}).write_text("new synthetic report")')
        (self.root / 'independent-gate-marker.py').write_text(code)
        self.command = 'python independent-gate-marker.py'
        self.inherited.write_text(json.dumps([{'command': self.command}] +
            [{'command': f'python -c "print({index})"'} for index in range(42)]))
        self.generated = generated
        self.before = {self.prior: self.prior.read_bytes(), self.historical: self.historical.read_bytes()}

    def git(self, *args):
        if args == ('ls-files', '-z'):
            return ('\0'.join(str(path.relative_to(self.root)) for path in self.before) + '\0').encode()
        if args == ('rev-parse', 'HEAD'): return b'synthetic-review-head\n'
        if args == ('rev-parse', 'HEAD^{tree}'): return b'synthetic-review-tree\n'
        if args[0] == 'diff': return b''
        raise AssertionError(args)

    def context(self, argv):
        from contextlib import ExitStack
        stack = ExitStack()
        for item in (
            patch.object(runner, 'ROOT', self.root), patch.object(runner, 'REPORT', self.prior_root),
            patch.object(runner, 'INHERITED', self.inherited), patch.object(runner, 'git', side_effect=self.git),
            patch.object(runner, 'source_snapshot', return_value={'head': 'synthetic-review-head', 'files': {}, 'sha256': 'fixed-source'}),
            patch.object(runner, 'consumer_blocker', return_value=None), patch.object(sys, 'argv', argv)):
            stack.enter_context(item)
        return stack

    def test_fresh_root_restores_prior_reports_and_retains_current_artifacts(self):
        argv = ['review', '--python', sys.executable, '--report-root', str(self.fresh), '--only', 'independent-gate-marker']
        with self.context(argv):
            self.assertEqual(runner.main(), 1)  # A deliberately partial aggregate is never fully qualified.
        for path, data in self.before.items(): self.assertEqual(path.read_bytes(), data)
        self.assertFalse(self.generated.exists())
        rows = json.loads((self.fresh / 'gates/results.json').read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'passed')
        self.assertTrue(rows[0]['historical_report_hashes_preserved'])
        self.assertEqual(rows[0]['historical_report_files_preserved'], 2)
        artifacts = {Path(name).name: (self.root / name).read_text() for name in rows[0]['component_artifacts']}
        self.assertEqual(artifacts['old.log'], 'independent-gate-marker current output')
        self.assertEqual(artifacts['new-report.txt'], 'new synthetic report')
        summary = json.loads((self.fresh / 'gates/summary.json').read_text())
        self.assertTrue(summary['historical_report_hashes_preserved'])
        self.assertEqual((summary['recorded_gates'], summary['gate_count'], summary['qualified_passing_gates']), (1, 46, 1))

    def test_report_projection_excludes_only_fresh_output_root(self):
        self.fresh.mkdir(parents=True)
        fresh_log = self.fresh / 'fresh.log'; fresh_log.write_text('current evidence')
        with patch.object(runner, 'ROOT', self.root), patch.object(runner, 'REPORT', self.fresh):
            projected = runner.report_paths()
        self.assertIn(self.prior, projected)
        self.assertIn(self.historical, projected)
        self.assertNotIn(fresh_log, projected)

    def test_output_root_outside_repository_is_rejected_without_writes(self):
        outside = self.root.parent / (self.root.name + '-not-authorized-output')
        with self.context(['review', '--report-root', str(outside)]):
            with self.assertRaises(SystemExit) as rejected: runner.main()
        self.assertEqual(rejected.exception.code, 2)
        self.assertFalse(outside.exists())
        for path, data in self.before.items(): self.assertEqual(path.read_bytes(), data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
