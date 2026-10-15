"""Operator-owned public preparation and observation of an authored extension.

Default: prepare one finite Study/Trial and owner grant, then stop before SDK
admission. --serve waits for the separate author's SDK stdout JSON in
sdk-result.json; --run-sdk explicitly invokes the reviewed public SDK/CLI after
an exact clean host commit is selected. Neither mode retries an admission.

--reviewed-inventory is operator-reviewed JSON:
 {"format":"extension_author_reviewed_inventory_v1","files":{"project.json":
 "<sha256>","recipe.json":"<sha256>","fixture.json":"<sha256>",...}}
It must cover every project/provider/contribution/source/notice, the frozen
oracle and its fixture. The harness verifies these bytes; it never generates an
accepted review inventory or edits the author package. --roots optionally names
the complete configured startup root map, allowing separate A/B roots in one
catalog. Existing catalog counts need not be zero. Qualification checks this
Study's single reservation, not a global count assumption.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_api
import pipeline
from app import Dataset, make_handler
from runtime_snapshots import RuntimeSnapshots

RUNTIME_SHA = '50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d'
SHA = re.compile('[a-f0-9]{64}')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, maximum=8*1024**2):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum,
                'Expected a nonempty bounded regular file: ' + str(path))
        chunks = []; remaining = maximum+1
        while remaining:
            piece = os.read(fd, min(65536, remaining))
            if not piece:
                break
            chunks.append(piece); remaining -= len(piece)
        raw = b''.join(chunks); after = os.fstat(fd)
        require(len(raw) == before.st_size and
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'File changed while reading.')
        return raw
    finally:
        os.close(fd)


def document(path):
    return agent_api.decode(regular(path))


def review_package(package, reviewed):
    """Verify an explicit review receipt and every declared dependency, inertly."""
    require(type(reviewed) is dict and set(reviewed) == {'format', 'files'} and
            reviewed['format'] == 'extension_author_reviewed_inventory_v1', 'Select an exact review inventory.')
    files = reviewed['files']
    require(type(files) is dict and 1 <= len(files) <= 128, 'Review inventory exceeds its file bound.')
    blobs = {}; total = 0
    for name, expected in files.items():
        parts = PurePosixPath(name)
        require(type(name) is str and name == parts.as_posix() and not parts.is_absolute()
                and all(piece not in ('', '.', '..') for piece in parts.parts)
                and type(expected) is str and SHA.fullmatch(expected), 'Invalid review path/hash.')
        path = package
        for piece in parts.parts:
            path = path / piece
            require(not path.is_symlink(), 'Reviewed paths cannot traverse symlinks.')
        raw = regular(path); total += len(raw)
        require(total <= 8*1024**2 and sha(raw) == expected, 'Reviewed package bytes differ: ' + name)
        blobs[name] = raw
    def read(name):
        require(name in blobs, 'Review inventory omits required dependency: ' + name)
        return agent_api.decode(blobs[name])
    project = read('project.json')
    require(project['schema_version'] == 2 and len(project['recipes']) == 1,
            'Select one explicit v2 Project recipe.')
    recipe_ref = project['recipes'][0]; recipe = read(recipe_ref['path'])
    require(sha(blobs[recipe_ref['path']]) == recipe_ref['sha256'] and
            recipe['schema_version'] == 3 and recipe['format'] == 'external_model_evidence_recipe_v2',
            'Select the reviewed bound recipe variant.')
    require(recipe['runtime'] == 'captured_cpu_python_v1' and
            recipe['runtime_snapshot_sha256'] == RUNTIME_SHA, 'Runtime nomination differs; no fallback.')
    for row in project['data'] + project['extensions']:
        read_raw = blobs.get(row['path'])
        require(read_raw is not None and sha(read_raw) == row['sha256'], 'Project dependency was not reviewed.')
    for row in project['extensions']:
        provider = read(row['path'])
        for item in provider['sources'] + provider['contributions'] + provider['license']['notices']:
            require(item['path'] in blobs and sha(blobs[item['path']]) == item['sha256'] and
                    len(blobs[item['path']]) == item['bytes'], 'Provider dependency was not reviewed.')
    for row in recipe['sources']:
        require(row['path'] in blobs and sha(blobs[row['path']]) == row['sha256'],
                'Recipe source was not reviewed.')
    frozen = read('oracle-freeze.json')
    for name, key in (('cold_oracle.py', 'oracle_sha256'), ('fixture.json', 'fixture_sha256')):
        require(name in blobs and sha(blobs[name]) == frozen[key], 'Frozen independent oracle/fixture differs.')
    return project, recipe, blobs


def selection_for(catalog_id, actor_id, project_id, study, trial, grant, material, model):
    """Exact public SDK selection; this document conveys no approval authority."""
    require(material['trainer']['id'] == 'external_model_evidence_recipe_v1',
            'Generic composition trainer identity differs.')
    return {'format': 'extension_sdk_conformance_selection_v1', 'catalog_id': catalog_id,
        'actor_id': actor_id, 'project_id': project_id, 'study_id': study['id'], 'trial_id': trial['id'],
        'revision': study['revision'], 'admission_epoch': study['admission_epoch'], 'approval_id': grant['id'],
        'request_key': 'sdk-admit-' + uuid.uuid4().hex,
        'expected': {'graph_id': material['recipe_id'], 'graph_revision': material['recipe_revision'],
            'material_sha256': trial['material']['sha256'], 'model_sha256': model['ref']['sha256'],
            'runtime_sha256': material['runtime']['sha256'], 'task_sha256': model['material']['task']['sha256'],
            'profile_definition_sha256': material['evaluation_profile']['sha256']}}


class Operator:
    def __init__(self, args):
        self.args = args; self.output = args.output.resolve(); self.sequence = 0
        self.dataset = self.server = self.thread = self.owner = self.agent = None
        self.review = None
        self.roots = document(args.roots) if args.roots else {args.root_alias: str(args.package.resolve())}
        require(type(self.roots) is dict and self.roots.get(args.root_alias) == str(args.package.resolve())
                and all(type(k) is str and type(v) is str and Path(v).is_absolute()
                        for k, v in self.roots.items()), 'Select the complete explicit configured root map.')

    def write(self, name, value, private=False):
        path = self.output / name
        raw = value if type(value) is bytes else agent_api.encoded(value) + b'\n'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        return path

    def start(self, serve=True):
        self.dataset = Dataset(self.args.catalog.resolve(), project_roots=self.roots)
        self.owner = self.dataset.access.exchange(self.dataset.access._local_owner_token())
        if serve:
            self.start_http()

    def retain_review(self, inventory_raw, blobs):
        """Keep the initial operator review outside the mutable author package."""
        self.review = {'inventory_sha256': sha(inventory_raw),
            'files': {name: sha(raw) for name, raw in blobs.items()}}
        oracle_root = self.output / 'reviewed-oracle'
        oracle_root.mkdir(mode=0o700)
        for name, raw in [('reviewed-inventory.private.json', inventory_raw),
                ('reviewed-oracle/cold_oracle.py', blobs['cold_oracle.py']),
                ('reviewed-oracle/fixture.json', blobs['fixture.json'])]:
            self.write(name, raw, private=True).chmod(0o400)
        self.write('review-freeze.json', self.review, private=True)

    def oracle_inputs(self):
        require(self.review is not None, 'Initial operator review is unavailable.')
        inventory = regular(self.output / 'reviewed-inventory.private.json')
        require(sha(inventory) == self.review['inventory_sha256'], 'Retained review inventory changed.')
        paths = [self.output / 'reviewed-oracle' / name for name in ('cold_oracle.py', 'fixture.json')]
        for path in paths:
            require(sha(regular(path)) == self.review['files'][path.name], 'Retained frozen oracle input changed.')
        return paths

    def start_http(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop(self):
        if self.server is not None:
            self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
            require(not self.thread.is_alive(), 'Loopback server did not stop.')
            self.server = self.thread = None
        if self.dataset is not None:
            if self.owner is not None:
                with self.dataset.access.bind(self.owner['token']):
                    self.dataset.access.logout()
            self.dataset.close(); self.dataset = self.owner = None

    def http(self, operation, arguments, version=1):
        method, path, body = agent_api.project_request(operation, arguments, version)
        result = self.raw(method, path, body,
            {agent_api.CONTRACT_HEADER: agent_api.selected_header(operation, version)})
        agent_api.validate_output(operation, result, version)
        self.sequence += 1
        self.write(f'{self.sequence:03d}-{operation}.json', result)
        require(200 <= result['status'] < 300, operation + ' refused: ' + str(result['result'])[:1000])
        return result['result']

    def raw(self, method, path, body=None, headers=None, binary=False):
        request = Request(self.endpoint + path, method=method,
            data=None if body is None else agent_api.encoded(body),
            headers={'Authorization': 'Bearer ' + self.owner['token'], 'Content-Type': 'application/json',
                     **(headers or {})})
        try:
            response = urlopen(request, timeout=360)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(16*1024**2+1)
            require(len(raw) <= 16*1024**2, 'HTTP output exceeds the operator bound.')
            return {'status': response.status, 'result': raw if binary else agent_api.decode(raw)}

    def prepare(self, project, recipe, reviewed_blobs):
        with self.dataset.access.bind(self.owner['token']):
            snapshots = RuntimeSnapshots(self.dataset.db, self.dataset.access, self.dataset.path)
            config = document(self.args.runtime_config)
            inventory = snapshots.inspect(config)
            require(inventory['inventory_sha256'] == RUNTIME_SHA, 'Sanctioned runtime inventory differs.')
            runtime = snapshots.create(config, RUNTIME_SHA, quiesced=True)
            require(runtime['profile'] == 'captured_cpu_python_v1' and runtime['manifest_sha256'] == RUNTIME_SHA,
                    'Captured runtime profile/manifest differs.')
        self.write('runtime.json', runtime)
        # Runtime capture is quiesced before exposing any loopback request.
        self.start_http()
        opened = self.raw('POST', '/api/workspace/project-snapshots',
                          {'root': self.args.root_alias, 'manifest_path': 'project.json'})
        require(opened['status'] == 201 and opened['result']['id'] == project['id'] and
                opened['result']['manifest_sha256'] == sha(reviewed_blobs['project.json']), 'Exact Project open refused.')
        self.write('opened.json', opened)
        ref = project['recipes'][0]
        selector = {'project_id': project['id'], 'recipe_id': ref['id'], 'expected_sha256': ref['sha256']}
        inspected = self.http('recipes.inspect', {'project_id': project['id'], 'reference_id': ref['id'],
                                                 'expected_sha256': ref['sha256']}, 2)
        require(inspected['definition'] == recipe and 'extension_binding' in inspected,
                'Current selected bound source differs from reviewed recipe.')
        for item in inspected['extension_binding']['inventory']:
            require(item['path'] in reviewed_blobs and sha(reviewed_blobs[item['path']]) == item['sha256'] and
                    len(reviewed_blobs[item['path']]) == item['bytes'], 'Captured binding differs from reviewed bytes.')
        for item in inspected['extension_binding']['contributions']:
            provider = item['provider']
            require(provider['runtime']['profile'] == 'captured_cpu_python_v1' and
                    provider['runtime'].get('snapshot_sha256') == RUNTIME_SHA,
                    'Provider must explicitly nominate the sanctioned runtime.')
            require(set(provider) == {'reference_id', 'id', 'version', 'sha256', 'runtime', 'effects', 'resources'},
                    'Provider projection differs.')
        policy = recipe['model_evidence']
        draft = self.http('models.create', {'name': 'Explicit authored extension qualification',
            'kind': 'captured_source', 'task': inspected['model_task'],
            'specification': policy['model_specification'], 'preprocessing_policy': policy['preprocessing_policy'],
            'output_policy': policy['output_policy'], 'source_selector': selector})
        model = self.http('models.publish', {'model_id': draft['id'], 'revision': draft['revision']})
        if self.args.inputs:
            inputs = document(self.args.inputs)
        else:
            refs = {row['id']: row for row in project['data']}
            require(set(recipe['inputs']) <= set(refs), 'Supply exact explicit --inputs JSON.')
            inputs = {key: {'reference_id': refs[key]['id'], 'expected_sha256': refs[key]['sha256']}
                      for key in recipe['inputs']}
        graph = self.http('graphs.create_external', {'name': 'Explicit authored extension qualification',
            **selector, 'inputs': inputs, 'parameters': {}})
        self.http('graphs.preflight_external', {'graph_id': graph['id'], 'revision': graph['revision']})
        study = self.http('studies.create', {'name': 'One explicit authored extension source attempt',
            'policy': inspected['selection_policy'], 'limits': {'attempt_slots': 1,
                'admitted_wall_seconds': self.args.wall_seconds, 'retained_bytes': self.args.retained_bytes,
                'peak_staging_bytes': self.args.staging_bytes}})
        trial = self.http('studies.prepare_trial', {'study_id': study['id'], 'request_key': 'prepare-' + uuid.uuid4().hex,
            'revision': study['revision'], 'graph_id': graph['id'], 'graph_revision': graph['revision'],
            'model': model['ref'], 'replicate': 0})
        material = self.http('recipes.material', {'ref': trial['material']})['material']
        runtime_sha = pipeline.digest(runtime)
        require(material['runtime'] == {'kind': 'runtime', 'catalog_id': self.dataset.db.dataset_id,
                    'id': runtime_sha, 'sha256': runtime_sha} and
                material['model']['sha256'] == model['ref']['sha256'] and
                material['trainer']['sha256'] == pipeline.digest(recipe), 'Published composition differs.')
        current = self.http('studies.get', {'study_id': study['id']})['study']
        self.http('studies.continue', {'study_id': study['id'], 'request_key': 'continue-' + uuid.uuid4().hex,
            'revision': current['revision'], 'admission_epoch': current['admission_epoch']})
        credential = self.raw('POST', '/api/access/credentials',
            {'label': 'Explicit authored extension SDK consumer', 'scopes': ['inspect', 'execute'],
             'ttl_seconds': 3600})
        require(credential['status'] == 201, 'Consumer credential issuance refused.')
        self.agent = credential['result']
        grant = self.http('studies.approve', {'study_id': study['id'], 'trial_id': trial['id'],
            'expected_material_sha256': trial['material']['sha256'],
            'consumer_actor_id': self.agent['identity']['actor_id']})
        state = self.http('studies.get', {'study_id': study['id']})
        require(state['reservations'] == [] and state['charged']['attempt_slots'] == 0,
                'Preparation unexpectedly admitted a source attempt.')
        selection = selection_for(self.dataset.db.dataset_id, self.agent['identity']['actor_id'],
                                  project['id'], state['study'], trial, grant, material, model)
        self.write('sdk-selection.json', selection, private=True)
        token = self.write('agent-token.private', self.agent['token'].encode(), private=True)
        self.write('agent-config.private', {'endpoint': self.endpoint, 'catalog_id': self.dataset.db.dataset_id,
                                          'token_file': str(token)}, private=True)
        return {'selection': selection, 'model': model, 'material': material,
                'runtime': runtime, 'prepared_state': state}

    def download(self, run, directory):
        directory.mkdir(mode=0o700)
        for item in run['artifacts']:
            require(item['locked'] is False, 'Actual artifact is protected.')
            name = item['name']
            require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', name) and 0 < item['bytes'] <= 8*1024**2,
                    'Actual artifact inventory exceeds its bound.')
            result = self.raw('GET', '/api/workspace/runs/' + run['id'] + '/artifacts/' + quote(name), binary=True)
            require(result['status'] == 200 and len(result['result']) == item['bytes'] and
                    sha(result['result']) == item['sha256'], 'Actual downloaded whole artifact differs.')
            with (directory/name).open('xb') as handle:
                handle.write(result['result'])

    def verify(self, prepared, sdk):
        selected = prepared['selection']; expected = selected['expected']
        require(sdk['format'] == 'extension_sdk_conformance_v1' and sdk['state'] == 'passed' and
                sdk['numerical'] == 'not_evaluated' and sdk['operations'].count('studies.admit') == 1 and
                not set(sdk['operations']) & {'studies.create', 'studies.approve', 'studies.continue', 'runs.submit_external'} and
                sdk['material_sha256'] == expected['material_sha256'] and
                sdk['study_id'] == selected['study_id'] and sdk['trial_id'] == selected['trial_id'] and
                sdk['request_key'] == selected['request_key'], 'SDK has no exact successful selected result.')
        run = self.http('runs.get', {'run_id': sdk['run_id']})
        require(run['state'] == 'completed' and run['custody_phase'] == 'drained' and
                run['actor_id'] == selected['actor_id'] and run['approval_id'] == selected['approval_id'] and
                run['approval_material_sha256'] == expected['material_sha256'] and
                run['study_membership'] == {'study_id': selected['study_id'], 'trial_id': selected['trial_id']},
                'Actual Run differs from the author selection or is not complete/drained.')
        projection = self.http('runs.model_evidence', {'run_id': run['id']}, 2)
        require(projection['state'] == 'verified', 'Actual selected field evidence is not verified.')
        self.download(run, self.output/'artifacts')
        for item in run['artifacts']:
            raw = regular(self.output/'sdk-artifacts'/item['name'])
            require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'SDK whole download differs.')
        with self.dataset.access.bind(self.owner['token']), self.dataset.lock:
            context = self.dataset.runs._load(run['id'])['spec']['model_evidence_context']
        require(sha(regular(self.output/'artifacts/execution-context.json')) == context['sha256'],
                'Independent retained custody context differs.')
        oracle_path, fixture_path = self.oracle_inputs()
        oracle = subprocess.run([str(self.args.oracle_python), '-I', '-S', '-B',
            str(oracle_path), '--fixture', str(fixture_path),
            '--artifacts', str(self.output/'artifacts'), '--expected-context-sha256', context['sha256'],
            '--report', str(self.output/'oracle.json')], capture_output=True, timeout=60)
        require(oracle.returncode == 0, 'Frozen independent oracle refused; no numerical acceptance.')
        state = self.http('studies.reconcile', {'study_id': selected['study_id']})
        require(state['charged']['attempt_slots'] == 1 and len(state['reservations']) == 1 and
                state['reservations'][0]['run_id'] == run['id'] and state['reservations'][0]['state'] == 'settled',
                'This Study must contain exactly one actual settled source charge.')
        self.stop(); self.start()
        require(self.http('runs.get', {'run_id': run['id']}) == run, 'Cold Run changed.')
        require(self.http('models.material', {'ref': prepared['model']['ref']}) == prepared['model'], 'Cold Model changed.')
        require(self.http('recipes.material', {'ref':
            {'kind': 'recipe_material', 'catalog_id': selected['catalog_id'],
             'id': expected['material_sha256'], 'sha256': expected['material_sha256']}})['material'] ==
                prepared['material'], 'Cold composition changed.')
        require(self.http('runs.model_evidence', {'run_id': run['id']}, 2) == projection, 'Cold evidence changed.')
        require(self.http('studies.get', {'study_id': selected['study_id']}) == state, 'Cold Study changed.')
        self.download(run, self.output/'cold-artifacts')
        return {'format': 'extension_author_operator_qualification_v1', 'state': 'passed',
            'run_id': run['id'], 'selection': selected, 'charged': state['charged'], 'custody_context': context,
            'artifacts': [{key: item[key] for key in ('name', 'bytes', 'sha256')} for item in run['artifacts']],
            'oracle': document(self.output/'oracle.json'), 'cold_whole_downloads_verified': True,
            'scope': 'Actual selected SDK source attempt, retained custody and independent frozen oracle; physical/product acceptance remains separate.'}


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('package', 'reviewed-inventory', 'catalog', 'runtime-config', 'output', 'oracle-python', 'cli'):
        result.add_argument('--' + name, type=Path, required=True)
    result.add_argument('--cli-sha256', required=True)
    result.add_argument('--expected-host-commit', required=True, help='Exact reviewed clean host source commit')
    result.add_argument('--roots', type=Path)
    result.add_argument('--root-alias', default='author-b')
    result.add_argument('--inputs', type=Path, help='Exact ordinary graph Project-reference inputs JSON')
    result.add_argument('--wall-seconds', type=int, default=900)
    result.add_argument('--retained-bytes', type=int, default=128*1024**2)
    result.add_argument('--staging-bytes', type=int, default=256*1024**2)
    result.add_argument('--wait-seconds', type=int, default=1800)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true', help='Default: stop without any SDK admission')
    mode.add_argument('--serve', action='store_true', help='Wait for separate author sdk-result.json; never invoke SDK')
    mode.add_argument('--run-sdk', action='store_true', help='Explicitly invoke the frozen SDK/CLI and admit the selected source Trial')
    return result


def wait_for_result(path, seconds):
    """A shell stdout redirect exists before its complete JSON is written."""
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        try:
            return document(path)
        except (OSError, RuntimeError, agent_api.AgentAPIError):
            time.sleep(min(.5, max(0, deadline-time.monotonic())))
    raise RuntimeError('Complete author result pending; inspect durable state before retrying.')


def frozen_host(args):
    host = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(host == args.expected_host_commit and not subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT), 'Select the exact clean reviewed host commit.')
    return host


def main(args):
    host = frozen_host(args)
    require(SHA.fullmatch(args.cli_sha256) and sha(regular(args.cli)) == args.cli_sha256,
            'Trusted public CLI source differs.')
    require(1 <= args.wait_seconds <= 3600 and 1 <= args.wall_seconds <= 86400 and
            args.retained_bytes > 0 and args.staging_bytes > 0, 'Select finite positive qualification budgets.')
    reviewed_raw = regular(args.reviewed_inventory)
    reviewed_inventory = agent_api.decode(reviewed_raw)
    project, recipe, blobs = review_package(args.package.resolve(), reviewed_inventory)
    operator = Operator(args); operator.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    operator.retain_review(reviewed_raw, blobs)
    prepared = None; passed = False
    try:
        operator.start(serve=False); prepared = operator.prepare(project, recipe, blobs)
        operator.write('prepared.json', dict(prepared, host_commit=host, driver_sha256=sha(Path(__file__).read_bytes()),
            reviewed_inventory_sha256=sha(reviewed_raw), project_files={name: sha(raw) for name, raw in blobs.items()},
            state='prepared_before_sdk_admission', physical_qualification='not_established'))
        command = [sys.executable, '-B', '-m', 'tuldok_extension_sdk', 'conformance',
            '--config', str(operator.output/'agent-config.private'), '--cli', str(args.cli.resolve()),
            '--cli-sha256', args.cli_sha256, '--selection', str(operator.output/'sdk-selection.json'),
            '--output', str(operator.output/'sdk-artifacts'), '--deadline-seconds', str(args.wait_seconds)]
        operator.write('author-command.json', {'argv': command, 'cwd': str(ROOT),
            'stdout_destination': str(operator.output/'sdk-result.json'),
            'instruction': 'Author runs only after main declares the host/package frozen; no owner credential is supplied.'})
        print(json.dumps({'state': 'prepared_before_sdk_admission', 'prepared': str(operator.output/'prepared.json'),
                          'author_command': str(operator.output/'author-command.json'), 'endpoint': operator.endpoint}), flush=True)
        if not args.serve and not args.run_sdk:
            return
        if args.run_sdk:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=args.wait_seconds+30)
            require(operator.agent['token'].encode() not in completed.stdout+completed.stderr, 'Credential disclosure refused.')
            operator.write('sdk-result.json', agent_api.decode(completed.stdout))
            require(completed.returncode == 0, 'SDK refused; inspect durable selection before any retry.')
        else:
            wait_for_result(operator.output/'sdk-result.json', args.wait_seconds)
        # Recheck reviewed source and frozen oracle bytes before independent execution.
        frozen_host(args)
        require(regular(args.reviewed_inventory) == reviewed_raw, 'Original reviewed inventory changed.')
        _, _, current_blobs = review_package(args.package.resolve(), reviewed_inventory)
        require(current_blobs == blobs, 'Original frozen author/oracle closure changed.')
        receipt = operator.verify(prepared, document(operator.output/'sdk-result.json'))
        operator.write('receipt.json', dict(receipt, host_commit=host)); passed = True
        print(json.dumps({'state': 'passed', 'receipt': str(operator.output/'receipt.json')}), flush=True)
    except BaseException as error:
        operator.write('failure.json', {'state': 'inspect_durable_state_before_retry',
            'error_type': type(error).__name__, 'prepared_selection': None if prepared is None else prepared['selection']})
        raise
    finally:
        # Preserve an unresolved/prepared actor for explicit owner reconciliation;
        # the bounded credential expires normally. Revoke only after verified success.
        if passed and operator.agent is not None:
            with operator.dataset.access.bind(operator.owner['token']):
                operator.dataset.access.revoke(operator.agent['identity']['credential_id'])
        operator.stop()


if __name__ == '__main__':
    main(parser().parse_args())
