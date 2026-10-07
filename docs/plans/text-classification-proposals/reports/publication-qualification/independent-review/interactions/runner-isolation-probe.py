"""Independent bounded runner isolation probe using detached temporary files only."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

source_root = Path(__file__).resolve().parents[7]
spec = importlib.util.spec_from_file_location('qualification_runner_under_review', source_root/'scripts/qualify_text_classification_local.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
inherited = json.loads(runner.INHERITED.read_text())
with tempfile.TemporaryDirectory(prefix='classification-runner-isolation-review-') as folder:
    root = Path(folder)
    old_parent = root/'docs/plans/old-task/reports'
    old_classification = root/'docs/plans/text-classification-proposals/reports'
    output = old_classification/'publication-qualification'
    expected = {
        old_parent/'inherited.png': b'original inherited screenshot\x00\xff',
        old_parent/'delete-me.txt': b'original deleted report',
        old_classification/'gates/results.json': b'[{"prior":"classification qualification"}]\n',
        old_classification/'independent-review/receipt.json': b'{"prior":"independent review"}\n',
    }
    for file, content in expected.items():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    inherited_path = root/'inherited-commands.json'
    inherited_path.write_text(json.dumps(inherited))
    extra = old_parent/'fixture-new-file.txt'
    def fake_git(*arguments):
        if arguments == ('ls-files', '-z'):
            return b'\0'.join(str(file.relative_to(root)).encode() for file in expected) + b'\0'
        if arguments[:1] == ('rev-parse',):
            return b'fixed-synthetic-candidate\n'
        if arguments[:1] == ('diff',):
            return b''
        raise AssertionError(arguments)
    class SyntheticGate:
        pid = 1
        def __init__(self, argv, **options):
            assert argv == ['node', '--check', 'static/text-classification-proposals.js']
            expected_files = list(expected)
            expected_files[0].write_bytes(b'replaced inherited screenshot')
            expected_files[1].unlink()
            expected_files[2].write_bytes(b'replaced old gate results')
            expected_files[3].write_bytes(b'replaced old review receipt')
            extra.write_text('new fixture artifact')
            options['stdout'].write('bounded synthetic gate completed\n')
        def wait(self, timeout):
            return 0
    runner.ROOT = root
    runner.INHERITED = inherited_path
    runner.REPORT = old_classification
    runner.git = fake_git
    runner.source_snapshot = lambda: {'head':'fixed-synthetic-candidate','files':{},'sha256':'unchanged-source'}
    runner.consumer_blocker = lambda python: None
    runner.subprocess.Popen = SyntheticGate
    prior_argv = sys.argv
    sys.argv = ['runner', '--only', '^node --check static/text-classification-proposals[.]js$',
                '--report-root', str(output), '--timeout', '1']
    try:
        result = runner.main()
    finally:
        sys.argv = prior_argv
    assert result == 1, 'A one-gate subset correctly remains incomplete against full 46-gate requirement'
    for file, content in expected.items():
        assert file.read_bytes() == content, str(file)
    assert not extra.exists(), 'New fixture artifact must be copied then removed from prior report trees'
    gates = json.loads((output/'gates/results.json').read_text())
    assert len(gates) == 1 and gates[0]['status'] == 'passed'
    assert gates[0]['historical_report_hashes_preserved']
    assert gates[0]['historical_report_files_preserved'] == len(expected)
    artifact_root = output/'component-artifacts/node---check-static-text-classification-proposals.js'
    copied = artifact_root/extra.relative_to(root)
    assert copied.read_text() == 'new fixture artifact'
    assert (artifact_root/list(expected)[0].relative_to(root)).read_bytes() == b'replaced inherited screenshot'
    assert (artifact_root/list(expected)[2].relative_to(root)).read_bytes() == b'replaced old gate results'
    summary = json.loads((output/'gates/summary.json').read_text())
    assert summary['historical_report_hashes_preserved']
    assert summary['recorded_gates'] == 1 and summary['gate_count'] == 46
    assert summary['qualified_passing_gates'] == 1
    print(json.dumps({'independent_runner_isolation':'passed','preserved_old_files':len(expected),
                      'isolated_artifacts':len(gates[0]['component_artifacts']),
                      'subset_correctly_incomplete':True,'new_output_root':str(output.relative_to(root))}, sort_keys=True))
