#!/usr/bin/env python3
"""Run bounded, synthetic local gates and preserve inherited report evidence.

No dependencies, credentials, model weights, real gateway, or public service are
installed or contacted. Browser fixtures launch their own loopback HTTP servers.
Pinned consumer gates are recorded as blocked when their dependencies are absent.
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
import time

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/plans/text-classification-proposals/reports'
INHERITED = ROOT / 'docs/plans/caption-proposals/reports/gates/results.json'
NEW_COMMANDS = (
    'node --check static/text-classification-proposals.js',
    'node tests/test_text_classification_proposals_controller.cjs',
    'node tests/browser_text_classification_proposals.cjs',
)
CONSUMER_COMMANDS = {
    'node tests/browser_preferences.cjs',
    'node tests/browser_instruction_responses.cjs',
    'node tests/browser_combined_workbench.cjs',
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


def report_paths():
    return {path for path in (ROOT / 'docs/plans').glob('**/reports/**/*')
            if path.is_file() and REPORT not in path.parents}


def source_snapshot():
    paths = {path for path in ROOT.glob('*.py') if path.is_file()}
    paths.add(ROOT / 'requirements.txt')
    for directory in ('static', 'tests', 'scripts', '.github'):
        paths.update(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts)
    hashes = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sorted(paths)}
    return {'head': git('rev-parse', 'HEAD').decode().strip(),
            'files': hashes, 'sha256': sha(json.dumps(hashes, sort_keys=True).encode())}


def transient_paths(command):
    category = ('classification-preferences' if 'classification_preferences_integration' in command else
                'text-classification-proposals' if 'text_classification_proposals' in command else
                'caption-proposals' if 'caption_proposals' in command else
                'rights-note' if 'rights_note' in command else None)
    return {path for path in (ROOT / 'test-results' / category).rglob('*') if path.is_file()} if category else set()


def main():
    global REPORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inherited-only', action='store_true')
    parser.add_argument('--only', help='Run commands matching this regular expression.')
    parser.add_argument('--resume', action='store_true', help='Keep passing commands qualified against this exact unchanged source; rerun others.')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--report-root', type=Path, default=REPORT,
                        help='Fresh repository-local report directory; prior qualification artifacts remain unchanged.')
    parser.add_argument('--timeout', type=int, default=180, help='Maximum seconds per command (1..300).')
    args = parser.parse_args()
    REPORT = args.report_root.resolve()
    if ROOT not in REPORT.parents:
        parser.error('--report-root must be inside this repository')
    if not 1 <= args.timeout <= 300:
        parser.error('--timeout must be between 1 and 300 seconds')
    inherited_commands = [row['command'] for row in json.loads(INHERITED.read_text())]
    if len(inherited_commands) != 43 or len(set(inherited_commands)) != 43:
        raise RuntimeError('Expected all 43 unique PR17 inherited gates.')
    # Qualify the combined branch's registered checks, including later features.
    # Installation steps are deliberately excluded: this runner stays offline.
    workflow = (ROOT / '.github/workflows/tests.yml').read_text()
    registered = re.findall(r'^\s+- run: ((?:node |python -m unittest )[^\n]+)$', workflow, re.M)
    required = inherited_commands + list(NEW_COMMANDS)
    if len(registered) != len(set(registered)) or not set(required).issubset(registered):
        raise RuntimeError('Workflow must retain every inherited and classification gate exactly once.')
    commands = inherited_commands if args.inherited_only else registered
    selected = [command for command in commands if not args.only or re.search(args.only, command)]
    gates = REPORT / 'gates'
    gates.mkdir(parents=True, exist_ok=True)
    results_path = gates / 'results.json'
    previous = {row['command']: row for row in json.loads(results_path.read_text())} if results_path.exists() else {}
    results = dict(previous)
    tracked = [ROOT / name.decode() for name in git('ls-files', '-z').split(b'\0')
               if name and '/reports/' in name.decode() and not name.decode().startswith(str(REPORT.relative_to(ROOT)) + '/')]
    preserved = {path: path.read_bytes() for path in tracked}
    existing = report_paths()
    blocker = consumer_blocker(args.python)
    env = os.environ.copy()
    env.update(PATH=str(Path(args.python).resolve().parent) + os.pathsep + env.get('PATH', ''),
               BROWSER=env.get('BROWSER', shutil.which('chromium') or '/usr/bin/chromium'),
               INSTRUCTION_CONSUMER_PYTHON=args.python,
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
    # Keep python3 browser subprocesses in the selected virtual environment.
    env['PATH'] = str(Path(args.python).absolute().parent) + os.pathsep + env['PATH']
    started = time.time()
    for number, command in enumerate(selected, 1):
        source_before = source_snapshot()
        prior = results.get(command, {})
        if (args.resume and prior.get('status') == 'passed' and prior.get('source_stable_during_gate')
                and prior.get('source_sha256_end') == source_before['sha256']
                and prior.get('source_head_end') == source_before['head']):
            continue
        stem = re.sub(r'[^A-Za-z0-9._-]+', '-', command).strip('-')
        log = gates / (stem + '.log')
        row = {'command': command, 'status': 'blocked' if command in CONSUMER_COMMANDS and blocker else 'running',
               'exit_code': None, 'seconds': 0, 'log': str(log.relative_to(ROOT)),
               'historical_report_files_preserved': len(preserved)}
        row.update(source_head_start=source_before['head'], source_sha256_start=source_before['sha256'])
        transient_before = {path: sha(path.read_bytes()) for path in transient_paths(command)}
        print(f'[{number}/{len(selected)}] {command}', flush=True)
        before = time.monotonic()
        try:
            if row['status'] == 'blocked':
                row['blocker'] = blocker
                log.write_text(blocker + '\n')
            else:
                argv = shlex.split(command)
                if argv[0] == 'python':
                    argv[0] = args.python
                with log.open('w') as output:
                    process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output,
                                               stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        code = process.wait(timeout=args.timeout)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        code = 124
                        row['blocker'] = f'Bounded gate exceeded {args.timeout} seconds.'
                row['exit_code'] = code
                row['status'] = 'passed' if code == 0 else 'failed'
        finally:
            # Inherited fixture screenshots/session output are copied to this
            # task's evidence tree before the prior tracked bytes are restored.
            changed = []
            for path in report_paths():
                if path in preserved and path.read_bytes() == preserved[path]:
                    continue
                if path not in preserved and path in existing:
                    continue
                target = REPORT / 'component-artifacts' / stem / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                changed.append(str(target.relative_to(ROOT)))
            for path, content in preserved.items():
                if not path.exists() or path.read_bytes() != content:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
            for path in report_paths() - existing:
                path.unlink()
            for path in transient_paths(command):
                if transient_before.get(path) == sha(path.read_bytes()):
                    continue
                target = REPORT / 'component-artifacts' / stem / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                changed.append(str(target.relative_to(ROOT)))
            source_after = source_snapshot()
            row.update(source_head_end=source_after['head'], source_sha256_end=source_after['sha256'],
                       source_stable_during_gate=source_before == source_after)
            row['component_artifacts'] = changed
            row['component_artifact_sha256'] = {name: sha((ROOT / name).read_bytes()) for name in changed}
            row['seconds'] = round(time.monotonic() - before, 3)
            row['historical_report_hashes_preserved'] = all(path.read_bytes() == content for path, content in preserved.items())
            results[command] = row
            ordered = [results[command] for command in commands if command in results]
            results_path.write_text(json.dumps(ordered, indent=2) + '\n')
            print(f'  {row["status"]} ({row["seconds"]}s)', flush=True)
    ordered = [results[command] for command in commands if command in results]
    final_source = source_snapshot()
    stale_passed = [row['command'] for row in ordered if row['status'] == 'passed'
                    and (not row.get('source_stable_during_gate')
                         or row.get('source_head_end') != final_source['head']
                         or row.get('source_sha256_end') != final_source['sha256'])]
    evidence = {
        'scope': 'Bounded synthetic HTTP/browser fixtures; no real inference, dependency/model downloads, credentials, or public writes.',
        'source_head': git('rev-parse', 'HEAD').decode().strip(),
        'source_tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
        'source_diff_sha256': sha(git('diff', 'HEAD', '--', '.', ':!docs/plans/**/reports/**')),
        'python': args.python, 'browser': env['BROWSER'], 'seconds': round(time.time() - started, 3),
        'gate_count': len(commands), 'recorded_gates': len(ordered),
        'passed': sum(row['status'] == 'passed' for row in ordered),
        'failed': sum(row['status'] == 'failed' for row in ordered),
        'blocked': sum(row['status'] == 'blocked' for row in ordered),
        'inherited_gate_count': 43,
        'registered_workflow_gate_count': len(registered),
        'historical_report_files_preserved': len(preserved),
        'historical_reports': {str(path.relative_to(ROOT)): sha(content) for path, content in preserved.items()},
        'historical_report_hashes_preserved': all(path.read_bytes() == content for path, content in preserved.items()),
        'source_snapshot': final_source,
        'stale_passed_gates': stale_passed,
        'qualified_passing_gates': sum(row['status'] == 'passed' for row in ordered) - len(stale_passed),
    }
    (gates / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({key: evidence[key] for key in ('recorded_gates', 'passed', 'failed', 'blocked', 'historical_report_files_preserved', 'historical_report_hashes_preserved')}, indent=2))
    return 1 if evidence['failed'] or evidence['blocked'] or stale_passed or evidence['recorded_gates'] != len(commands) else 0


if __name__ == '__main__':
    raise SystemExit(main())
