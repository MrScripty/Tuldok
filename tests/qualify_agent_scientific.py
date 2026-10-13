"""Opt-in real official-SDK byte parity against already qualified scientific Runs.

No model execution, graph editing, import, review, or scientific requalification.
Only explicit local QA-owner credential issuance/revocation changes authority.
All received artifact bytes are provisional until their complete hash matches the
prior authenticated HTTP inventory; bulk payloads are hashed and discarded.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = 8 * 1024 * 1024


def private_file(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as target:
        target.write(raw)


def http(endpoint, route, cookie=None, body=None):
    headers = {'Origin': endpoint}
    if cookie:
        headers['Cookie'] = cookie
    if body is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(endpoint + route, headers=headers,
        data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response), response.headers


async def qualify(args, endpoint, credential, config, report):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    previous = json.loads((args.evidence / 'receipt.json').read_text())
    expected_run = previous['run_id']
    expected_record = previous['record_id']
    inventory = {item['name']: item for item in json.loads(
        (args.evidence / 'completed-http-inventory.json').read_text())}
    project = json.loads((args.project / 'project.json').read_text())
    recipe = next(item for item in project['recipes'] if item['id'] == 'evaluate')
    calls = []

    async def call(session, name, arguments=None):
        response = await session.call_tool(name.replace('.', '_'), arguments or {})
        envelope = response.structuredContent
        assert isinstance(envelope, dict) and set(envelope) == {'status', 'result'}, name
        assert json.loads(response.content[0].text) == envelope, name
        assert envelope['status'] == 200 and not response.isError, name
        calls.append({'operation': name, 'status': envelope['status']})
        return envelope['result']

    parameters = StdioServerParameters(command=sys.executable,
        args=[str(ROOT / 'mcp_stdio.py'), '--config', str(config)], cwd=str(ROOT))
    with (report / 'bridge-stderr.log').open('w+') as errors:
        async with stdio_client(parameters, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                assert initialized.protocolVersion == '2025-06-18'
                tools = await session.list_tools()
                assert 'runs_artifact_chunk' in {tool.name for tool in tools.tools}
                identity = await call(session, 'identity.get')
                assert identity['kind'] == 'agent' and identity['scopes'] == ['inspect']
                assert identity['actor_id'] == credential['identity']['actor_id']
                context = await call(session, 'context.get')
                projects = await call(session, 'projects.list')
                inspected_project = await call(session, 'projects.get', {'project_id': project['id']})
                inspected_recipe = await call(session, 'recipes.inspect', {'project_id': project['id'],
                    'reference_id': 'evaluate', 'expected_sha256': recipe['sha256']})
                before_runs = await call(session, 'runs.list')
                before_graphs = await call(session, 'graphs.list')
                before_record = await call(session, 'data.get', {'record_id': expected_record})
                run = await call(session, 'runs.get', {'run_id': expected_run})
                training = await call(session, 'runs.get', {'run_id': previous['source_training_run']})
                assert run['state'] == training['state'] == 'completed'
                assert run['custody_phase'] == training['custody_phase'] == 'drained'
                assert run['material_sha256'] == previous['material_sha256']
                graph = await call(session, 'graphs.get', {'graph_id': run['graph']['id']})
                progress = await call(session, 'runs.progress', {'run_id': expected_run})
                assert progress['evidence'] == 'custody_verified'
                slice_value = await call(session, 'data.scientific', {'record_id': expected_record,
                    'frame': 0, 'field': 'pressure', 'axis': 'z', 'index': 0})
                expected_slice = json.loads((args.evidence / 'representative-inspection.json').read_text())
                assert slice_value == expected_slice
                transferred = []
                for name in ('input-model.pt', 'fields-learned-900-000.zip'):
                    expected = inventory[name]
                    artifact = next(item for item in run['artifacts'] if item['name'] == name)
                    assert (artifact['bytes'], artifact['sha256']) == (expected['bytes'], expected['sha256'])
                    digest, offset, segments = hashlib.sha256(), 0, []
                    while offset < expected['bytes']:
                        part = await call(session, 'runs.artifact_chunk', {'run_id': expected_run,
                            'name': name, 'expected_sha256': expected['sha256'],
                            'offset': offset, 'max_bytes': SEGMENT})
                        assert part['verification'] == 'segment_read_whole_hash_unverified'
                        assert (part['run_id'], part['name'], part['expected_sha256'], part['total_bytes']) == (expected_run, name, expected['sha256'], expected['bytes'])
                        raw = base64.b64decode(part['data_base64'], validate=True)
                        segment_sha = hashlib.sha256(raw).hexdigest()
                        assert part['segment_sha256'] == segment_sha
                        assert (part['offset'], part['bytes'], part['next_offset']) == (offset, len(raw), offset + len(raw))
                        assert 0 < len(raw) <= SEGMENT
                        digest.update(raw)
                        segments.append({'offset': offset, 'bytes': len(raw), 'sha256': segment_sha})
                        offset += len(raw)
                        assert part['eof'] == (offset == expected['bytes'])
                    assert offset == expected['bytes'] and digest.hexdigest() == expected['sha256']
                    transferred.append({'name': name, 'bytes': offset, 'sha256': digest.hexdigest(),
                        'segments': segments, 'verification': 'complete_reassembled_hash_matches_prior_HTTP'})
                    print('Verified real MCP artifact:', name, offset, 'bytes', flush=True)
                assert len(transferred[1]['segments']) > 1
                assert await call(session, 'runs.list') == before_runs
                assert await call(session, 'graphs.list') == before_graphs
                assert await call(session, 'data.get', {'record_id': expected_record}) == before_record
                result = {'qualification': 'Actual official SDK stdio agent → authenticated HTTP → existing scientific owners; byte parity only',
                    'new_model_execution': False, 'new_scientific_acceptance': False,
                    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'catalog_id': identity['catalog_id'], 'actor_id': identity['actor_id'], 'scopes': identity['scopes'],
                    'protocol_version': initialized.protocolVersion, 'run_id': expected_run,
                    'training_run_id': training['id'], 'record_id': expected_record,
                    'run_and_graph_lists_unchanged': True, 'reviewed_record_exactly_unchanged': True,
                    'typed_slice_exact_prior_HTTP_match': True, 'transferred_artifacts': transferred,
                    'calls': calls, 'context': context, 'projects': projects,
                    'project': inspected_project, 'recipe': inspected_recipe, 'graph': graph}
        errors.seek(0)
        assert credential['token'] not in errors.read()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--app-python', default='/workspace/Tuldok/.venv/bin/python')
    parser.add_argument('--qualification-admitted', action='store_true', required=True)
    args = parser.parse_args()
    args.catalog, args.project, args.evidence = (p.resolve() for p in (args.catalog, args.project, args.evidence))
    args.report.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='tuldok-agent-scientific-private-') as private:
        private = Path(private)
        with (args.report / 'app.log').open('w+') as log:
            server = subprocess.Popen([args.app_python, '-u', 'app.py', '--data', str(args.catalog),
                '--port', '0', '--project-root', 'sample=' + str(args.project)], cwd=ROOT,
                stdout=log, stderr=subprocess.STDOUT)
            credential, cookie, endpoint = None, None, None
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    log.flush()
                    match = re.search(r'127\.0\.0\.1:(\d+)', (args.report / 'app.log').read_text())
                    if match:
                        endpoint = 'http://127.0.0.1:' + match[1]
                        break
                    assert server.poll() is None, 'Application exited before readiness'
                    time.sleep(.1)
                assert endpoint, 'Application readiness timeout'
                login = private / 'owner-login'
                subprocess.run([args.app_python, 'access.py', 'login', '--data', str(args.catalog),
                    '--out', str(login)], cwd=ROOT, check=True, capture_output=True)
                owner, headers = http(endpoint, '/api/access/session', body={'token': login.read_text().strip()})
                login.unlink()
                cookie = headers['Set-Cookie'].split(';')[0]
                credential, _ = http(endpoint, '/api/access/credentials', cookie,
                    {'label': 'P6 actual scientific read-only QA', 'scopes': ['inspect'], 'ttl_seconds': 3600})
                token_file, config = private / 'agent-token', private / 'config.json'
                private_file(token_file, (credential['token'] + '\n').encode())
                private_file(config, json.dumps({'endpoint': endpoint, 'catalog_id': owner['catalog_id'],
                    'token_file': str(token_file), 'timeout': 120}).encode())
                result = asyncio.run(qualify(args, endpoint, credential, config, args.report))
                result['credential_revoked_after_qualification'] = True
                http(endpoint, '/api/access/credentials/' + credential['identity']['credential_id'] + '/revoke', cookie, {})
                credential = None
                (args.report / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
                print('PASS actual scientific MCP byte parity:', args.report, flush=True)
            finally:
                try:
                    if credential is not None:
                        http(endpoint, '/api/access/credentials/' + credential['identity']['credential_id'] + '/revoke', cookie, {})
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)


if __name__ == '__main__':
    main()
