#!/usr/bin/env python3
"""Run bounded offline QA gates with fresh ignored output directories.

Inputs live in tests/fixtures. Each child receives its own QA output root; old
reports, archives, previous runs and this runner's logs are never recaptured.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
NEW_COMMANDS = (
    'node --check static/polygons.js',
    'node tests/check_polygon_coco.cjs',
    'node tests/browser_polygon_segmentation.cjs',
    'node --check static/text-classification-proposals.js',
    'node tests/test_text_classification_proposals_controller.cjs',
    'node tests/browser_text_classification_proposals.cjs',
    'node tests/test_image_classification_export_controller.cjs',
    'node tests/browser_image_classification_export.cjs',
    'node tests/check_image_classification_consumer.cjs',
)
CONSUMER_COMMANDS = {
    'node tests/browser_preferences.cjs',
    'node tests/browser_instruction_responses.cjs',
    'node tests/browser_combined_workbench.cjs',
    'node tests/check_image_classification_consumer.cjs',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def consumer_blocker(python):
    """Check installed package metadata only; never install or import models."""
    pins = json.loads((ROOT / 'tests/instruction-consumer-pins.json').read_text())
    code = ('import importlib.metadata as m,json; names=json.loads(' + repr(json.dumps(list(pins['versions']))) + '); '
            'print(json.dumps({n: next((d.version for d in m.distributions() '
            'if d.metadata["Name"].lower().replace("_","-")==n.lower().replace("_","-")), None) '
            'for n in names}))')
    result = subprocess.run([python, '-c', code], capture_output=True, text=True, timeout=20)
    if result.returncode:
        return 'Installed pinned consumer metadata check failed: ' + result.stderr.strip()
    actual = json.loads(result.stdout)
    missing = [f'{name}=={expected} (installed: {actual[name] or "missing"})'
               for name, expected in pins['versions'].items() if actual[name] != expected]
    return ('Pinned instruction-consumer dependencies unavailable: ' + ', '.join(missing)
            + '. This runner never installs dependencies; provision an authorized isolated consumer environment separately.') if missing else None


def source_snapshot():
    paths = {path for path in ROOT.glob('*.py') if path.is_file()}
    paths.add(ROOT / 'requirements.txt')
    for directory in ('static', 'tests', 'scripts', 'tools', '.github'):
        paths.update(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts)
    hashes = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sorted(paths)}
    return {'head': git('rev-parse', 'HEAD').decode().strip(),
            'files': hashes, 'sha256': sha(json.dumps(hashes, sort_keys=True).encode())}


def output_container(path):
    path = path.resolve()
    for parent in (ROOT / 'build', ROOT / 'output'):
        if path == parent or parent in path.parents:
            return path
    raise ValueError('Qualification output must be inside ignored build/ or output/.')


def artifact_manifest(directory):
    """Only this gate's direct output subtree; no copying or report discovery."""
    return {str(path.relative_to(ROOT)): sha(path.read_bytes())
            for path in sorted(directory.rglob('*')) if path.is_file()}


def artifacts_reusable(prior, gate_dir):
    """Reuse only the unchanged, complete outputs from this gate's own run."""
    try:
        output = (ROOT / prior['artifact_output_root']).resolve()
        hashes = prior['component_artifact_sha256']
        if (not output.is_dir() or output.parent != gate_dir.resolve()
                or not output.name.startswith('artifacts-') or not isinstance(hashes, dict)
                or prior['component_artifacts'] != list(hashes)):
            return False
        for name in hashes:
            path = (ROOT / name).resolve()
            if output not in path.parents or not path.is_file():
                return False
        return artifact_manifest(output) == hashes
    except (KeyError, OSError, TypeError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inherited-only', action='store_true')
    parser.add_argument('--only', help='Run commands matching this regular expression.')
    parser.add_argument('--resume', action='store_true', help='Resume an explicit existing run with unchanged source.')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--report-root', type=Path, default=ROOT / 'build/qa/qualification',
                        help='Ignored output container; each invocation creates a fresh run directory.')
    parser.add_argument('--timeout', type=int, default=180, help='Maximum seconds per command (1..300).')
    args = parser.parse_args()
    try:
        container = output_container(args.report_root)
    except ValueError as error:
        parser.error(str(error))
    if not 1 <= args.timeout <= 300:
        parser.error('--timeout must be between 1 and 300 seconds')
    if args.resume:
        report = container
        if not (report / 'gates/results.json').is_file():
            parser.error('--resume requires the explicit existing run directory')
    else:
        container.mkdir(parents=True, exist_ok=True)
        report = Path(tempfile.mkdtemp(prefix='run-', dir=container))
    print('Qualification output: ' + str(report.relative_to(ROOT)), flush=True)
    registry = json.loads((ROOT / 'tests/fixtures/qa/inherited-gates.json').read_text())
    inherited = registry['commands']
    if len(inherited) != 43 or len(set(inherited)) != 43:
        raise RuntimeError('Expected all 43 unique inherited gates.')
    workflow = (ROOT / '.github/workflows/tests.yml').read_text()
    registered = re.findall(r'^\s+- run: ((?:node |python -m unittest )[^\n]+)$', workflow, re.M)
    if len(registered) != len(set(registered)) or not set(inherited + list(NEW_COMMANDS)).issubset(registered):
        raise RuntimeError('Workflow must retain every inherited and classification gate exactly once.')
    commands = inherited if args.inherited_only else registered
    selected = [command for command in commands if not args.only or re.search(args.only, command)]
    if not selected:
        parser.error('--only selected no registered gates')
    gates = report / 'gates'
    gates.mkdir(parents=True, exist_ok=True)
    results_path = gates / 'results.json'
    previous = {row['command']: row for row in json.loads(results_path.read_text())} if results_path.exists() else {}
    results = dict(previous)
    blocker = consumer_blocker(args.python)
    env = os.environ.copy()
    for name in ('TULDOK_CLASSIFICATION_REPORT_ROOT', 'TULDOK_CAPTION_REPORT_ROOT',
                 'TULDOK_CLASSIFICATION_PREFERENCES_REPORT_ROOT', 'TULDOK_SEQUENCE_ACTUAL_REPORT_ROOT'):
        env.pop(name, None)
    env.update(PATH=str(Path(args.python).absolute().parent) + os.pathsep + env.get('PATH', ''),
               BROWSER=env.get('BROWSER', shutil.which('chromium') or '/usr/bin/chromium'),
               INSTRUCTION_CONSUMER_PYTHON=args.python, TULDOK_SOURCE_ROOT=str(ROOT),
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
    started = time.time()
    for number, command in enumerate(selected, 1):
        source_before = source_snapshot()
        prior = results.get(command, {})
        stem = re.sub(r'[^A-Za-z0-9._-]+', '-', command).strip('-')
        gate_dir = output_container(gates / stem)
        if (args.resume and prior.get('status') == 'passed' and prior.get('source_stable_during_gate')
                and prior.get('source_sha256_end') == source_before['sha256']
                and prior.get('source_head_end') == source_before['head']
                and artifacts_reusable(prior, gate_dir)):
            continue
        gate_dir.mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix='artifacts-', dir=gate_dir))
        log = gate_dir / 'gate.log'
        child_env = dict(env, TULDOK_QA_OUTPUT_ROOT=str(output), TULDOK_EVIDENCE_DIR=str(output))
        row = {'command': command, 'status': 'blocked' if command in CONSUMER_COMMANDS and blocker else 'running',
               'exit_code': None, 'seconds': 0, 'log': str(log.relative_to(ROOT)),
               'source_head_start': source_before['head'], 'source_sha256_start': source_before['sha256']}
        print(f'[{number}/{len(selected)}] {command}', flush=True)
        before = time.monotonic()
        if row['status'] == 'blocked':
            row['blocker'] = blocker
            log.write_text(blocker + '\n')
        else:
            argv = shlex.split(command)
            if argv[0] == 'python':
                argv[0] = args.python
            with log.open('w') as stream:
                process = subprocess.Popen(argv, cwd=ROOT, env=child_env, stdout=stream,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    code = 124
                    row['blocker'] = f'Bounded gate exceeded {args.timeout} seconds.'
            row.update(exit_code=code, status='passed' if code == 0 else 'failed')
        source_after = source_snapshot()
        artifacts = artifact_manifest(output)
        row.update(source_head_end=source_after['head'], source_sha256_end=source_after['sha256'],
                   source_stable_during_gate=source_before == source_after,
                   artifact_output_root=str(output.relative_to(ROOT)),
                   component_artifacts=list(artifacts), component_artifact_sha256=artifacts,
                   seconds=round(time.monotonic() - before, 3))
        results[command] = row
        results_path.write_text(json.dumps([results[c] for c in commands if c in results], indent=2) + '\n')
        print(f'  {row["status"]} ({row["seconds"]}s)', flush=True)
    ordered = [results[command] for command in selected]
    final_source = source_snapshot()
    stale = [row['command'] for row in ordered if row['status'] == 'passed'
             and (not row.get('source_stable_during_gate')
                  or row.get('source_head_end') != final_source['head']
                  or row.get('source_sha256_end') != final_source['sha256'])]
    evidence = {
        'scope': 'Bounded offline QA fixtures, including recorded actual sequence bytes; ignored direct gate outputs; no report/previous-run copying, producer execution, training, inference or downloads.',
        'source_head': final_source['head'], 'source_tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
        'python': args.python, 'browser': env['BROWSER'], 'seconds': round(time.time() - started, 3),
        'gate_count': len(selected), 'recorded_gates': len(ordered),
        'passed': sum(row['status'] == 'passed' for row in ordered),
        'failed': sum(row['status'] == 'failed' for row in ordered),
        'blocked': sum(row['status'] == 'blocked' for row in ordered),
        'registered_workflow_gate_count': len(registered), 'inherited_gate_count': 43,
        'source_snapshot': final_source, 'stale_passed_gates': stale,
        'qualified_passing_gates': sum(row['status'] == 'passed' for row in ordered) - len(stale),
    }
    (gates / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({key: evidence[key] for key in ('recorded_gates', 'passed', 'failed', 'blocked')}, indent=2))
    return int(bool(evidence['failed'] or evidence['blocked'] or stale))


if __name__ == '__main__':
    raise SystemExit(main())
