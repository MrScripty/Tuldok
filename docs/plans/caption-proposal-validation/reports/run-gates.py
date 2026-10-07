from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

root = Path('/workspace/Tuldok-caption-validation-local')
output = Path('/workspace/tuldok-owner-review/caption-validation-local')
logs = output / 'gates'
logs.mkdir(exist_ok=True)
commands = [c for c in re.findall(r'^      - run: (.+)$', (root / '.github/workflows/tests.yml').read_text(), re.M) if 'pip install' not in c]
assert len(commands) == 43
base = '10de10b6710976570ace33b033ffb2349995edec'
base_workflow = subprocess.check_output(['git', 'show', base + ':.github/workflows/tests.yml'], cwd=root, text=True)
original = [c for c in re.findall(r'^      - run: (.+)$', base_workflow, re.M) if 'pip install' not in c]
assert commands == original and len(original) == 43
identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=root, text=True).splitlines()
source = {'head': identity[0], 'tree': identity[1], 'base': base, 'inherited_gates': 43, 'gates': 43}
(logs / 'source.json').write_text(json.dumps(source, indent=2) + '\n')
def report_files():
    return {p.relative_to(root).as_posix(): p for p in (root / 'docs/plans').rglob('*') if p.is_file() and '/reports/' in p.as_posix()}
baseline = {name: path.read_bytes() for name, path in report_files().items()}
env = dict(os.environ, BROWSER='/usr/bin/chromium', INSTRUCTION_CONSUMER_PYTHON='/workspace/tuldok-owner-review/combined-workbench-local/consumer-venv/bin/python')
results = []
artifacts = []
(logs / 'results.json').write_text('[]\n')
for index, command in enumerate(commands, 1):
    print(f'{index}/43 {command}', flush=True)
    started = time.monotonic()
    result = None
    try:
        with (logs / f'{index:02}.log').open('w') as log:
            result = subprocess.run(command, shell=True, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    finally:
        # Qualify fresh captures without replacing historical evidence in this branch.
        for name, path in report_files().items():
            data = path.read_bytes()
            if name not in baseline or data != baseline[name]:
                target = output / 'component-artifacts' / f'gate-{index:02}' / name
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
                artifacts.append({'gate': index, 'path': target.relative_to(output).as_posix(), 'original_path': name,
                                  'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            if name not in baseline:
                path.unlink()
        for name, data in baseline.items():
            path = root / name
            if not path.exists() or path.read_bytes() != data:
                path.write_bytes(data)
        assert all((root / name).read_bytes() == data for name, data in baseline.items())
        (output / 'component-artifacts.json').write_text(json.dumps(artifacts, indent=2) + '\n')
    results.append({'command': command, 'exit_code': result.returncode, 'seconds': round(time.monotonic() - started, 3),
                    'historical_report_files_preserved': len(baseline)})
    (logs / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(f'  exit={result.returncode}', flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == identity[0]
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip()
print('All 43 aggregate gates passed; all historical report files restored byte-identically after every gate.', flush=True)
