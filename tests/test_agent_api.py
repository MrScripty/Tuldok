"""Bounded registry/client tests; no model or external recipe execution."""
import base64
from contextlib import contextmanager
import hashlib
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import agent_api as api

HAS_JSONSCHEMA = importlib.util.find_spec('jsonschema') is not None

TOKEN = 'test-agent-credential-abcdefghijklmnopqrstuvwxyz'
CATALOG = 'a' * 32


def sample(schema):
    if 'const' in schema:
        return schema['const']
    if 'enum' in schema:
        return schema['enum'][0]
    if 'oneOf' in schema:
        return sample(schema['oneOf'][0])
    kind = schema.get('type')
    if kind == 'object':
        return {key: sample(schema['properties'][key]) for key in schema.get('required', [])}
    if kind == 'array':
        return [sample(schema['items']) for _ in range(schema.get('minItems', 0))]
    if kind in ('number', 'integer'):
        return schema.get('minimum', schema.get('exclusiveMinimum', 0) + 1)
    if kind == 'boolean':
        return False
    if kind == 'string':
        pattern = schema.get('pattern', '')
        if pattern == '^[a-f0-9]{32}$': return 'a'*32
        if pattern == '^[a-f0-9]{64}$': return 'a'*64
        if pattern.endswith('{8,128}$'): return 'request-key'
        if pattern == '^[A-Za-z0-9+/]*={0,2}$': return 'YQ=='
        return 'example'
    return None


class RegistryTests(unittest.TestCase):
    def test_discovery_is_stdlib_only_in_cold_process(self):
        code = 'import sys;sys.path.insert(0,sys.argv[1]);import agent_api;agent_api.discovery();assert not any(x in sys.modules for x in ("jsonschema","app","workbench","mcp","psycopg"))'
        subprocess.run([sys.executable, '-I', '-S', '-c', code, str(Path(api.__file__).parent)], check=True, capture_output=True, timeout=10)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_all_operation_schemas_and_route_projections(self):
        api.validate_registry()
        operations = api.discovery()['operations']
        self.assertEqual(len({op['mcp_name'] for op in operations}), len(operations))
        for op in operations:
            with self.subTest(op=op['operation_id']):
                args = sample(op['inputSchema'])
                if op['operation_id'] == 'data.import_image':
                    args['image'] = 'YQ=='
                method, path, body = api.project_request(op['mcp_name'], args)
                self.assertEqual(method, op['method'])
                self.assertNotIn('{', path)
                self.assertTrue(path.startswith('/api/'))
                self.assertEqual(body is None, method == 'GET')
                with self.assertRaises(api.AgentAPIError):
                    api.validate_arguments(op['operation_id'], dict(args, unowned=True))
        value = api.discovery(); digest = value.pop('digest')
        self.assertEqual(digest, hashlib.sha256(api.encoded(value)).hexdigest())
        value['operations'].clear()
        self.assertTrue(api.discovery()['operations'])

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_draft_tasks_and_no_human_or_programmatic_review(self):
        for task, annotation in api.ANNOTATIONS.items():
            args = dict(record_id=CATALOG, revision=1, source_revision=1, task=task,
                        annotation=sample(annotation), groups=['family'], review='draft')
            api.validate_arguments('data.save_draft', args)
            for review in ('human_reviewed', 'programmatically_verified'):
                with self.assertRaises(api.AgentAPIError):
                    api.validate_arguments('data.save_draft', dict(args, review=review))
        source = (Path(api.__file__).parent/'workbench.py').read_text()
        for task in api.ANNOTATIONS:
            self.assertIn(repr(task), source)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_integer_unicode_nonfinite_and_closed_subobjects(self):
        for value in (True, -1):
            with self.assertRaises(api.AgentAPIError):
                api.validate_arguments('runs.artifact_chunk', dict(run_id=CATALOG, name='result.bin', expected_sha256='a'*64, offset=value, max_bytes=1))
        # Standard JSON Schema integer includes integral floats. Preserve the
        # value for the stricter canonical owner rather than coerce it here.
        projected = api.project_request('graphs.preflight_external', {'graph_id': CATALOG, 'revision': 1.0})
        self.assertIs(type(projected[2]['revision']), float)
        for value in (float('nan'), '\ud800', '\x00'):
            with self.assertRaises(api.AgentAPIError):
                api.validate_arguments('data.query', {'q': value})
        with self.assertRaises(api.AgentAPIError): api.decode(b'{"a":1,"a":2}')
        with self.assertRaises(api.AgentAPIError): api.decode(b'{"a":NaN}')
        nested = None
        for _ in range(api.DEPTH_LIMIT+2): nested = [nested]
        with self.assertRaises(api.AgentAPIError): api._finite(nested)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_bindings_known_graph_drafts_and_no_executable_topology_requirement(self):
        schema = api.operation('graphs.save')['inputSchema']
        body = sample(schema)
        body['document']['edges'] = []
        api.validate_arguments('graphs.save', body)
        body['document']['nodes'][0]['parameters']['shell'] = 'sh'
        with self.assertRaises(api.AgentAPIError): api.validate_arguments('graphs.save', body)
        create = dict(name='External', project_id=CATALOG, recipe_id='recipe', expected_sha256='a'*64,
                      inputs={'sample': {'kind': 'run_artifact', 'run_id': CATALOG, 'artifact_name': 'model.pt', 'expected_sha256': 'b'*64}})
        api.validate_arguments('graphs.create_external', create)
        create['inputs']['sample']['path'] = '/tmp/unowned'
        with self.assertRaises(api.AgentAPIError): api.validate_arguments('graphs.create_external', create)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_import_bytes_bound_is_aggregate(self):
        raw = base64.b64encode(b'a'*(api.INLINE_LIMIT//2+1)).decode()
        with self.assertRaises(api.AgentAPIError) as caught:
            api.validate_arguments('data.import_mesh', {'files': {'mesh.ply': raw, 'mesh.json': raw}, 'groups': ['source']})
        self.assertEqual(caught.exception.code, 'too_large')
        for keys in [('run.json', 'frames.jsonl')]:
            api.validate_arguments('data.import_sequence', {'files': {k:'YQ==' for k in keys}, 'groups':['source']})

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_exposure_grant_and_projection(self):
        self.assertEqual(api.project_request('runs.expose_test', {'run_id': CATALOG, 'reason': 'explicit disclosure'}),
                         ('POST', '/api/workspace/runs/'+CATALOG+'/expose-test', {'reason':'explicit disclosure'}))
        self.assertEqual(api.operation('runs.expose_test')['scopes'], ['inspect','expose-holdout'])
        for name in ('runs.retry', 'runs.approve_external', 'access.issue', 'data.review'):
            with self.assertRaises(api.AgentAPIError): api.operation(name)
        args = dict(request_key='test-request', graph_id=CATALOG, graph_revision=1, expected_digest='a'*64)
        with self.assertRaises(api.AgentAPIError): api.validate_arguments('runs.submit_external', args)
        args['approval_id'] = 'b'*32
        api.validate_arguments('runs.submit_external', args)


@contextmanager
def server(mode='normal'):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_POST(self): self.do_GET()
        def do_GET(self):
            calls.append((self.command, self.path, self.headers.get('Authorization')))
            if self.headers.get('Content-Length'):
                self.rfile.read(int(self.headers['Content-Length']))
            if self.path == '/api/access/session':
                value = {'kind': 'owner' if mode == 'owner' else 'agent', 'catalog_id': CATALOG, 'actor_id': CATALOG, 'scopes': ['inspect','edit']}
            elif self.path == '/api/workspace/context': value = {'dataset_id': CATALOG}
            elif self.path == '/api/agent/operations':
                value = api.discovery()
                if mode == 'mismatch': value['digest'] = '0'*64
            elif self.path.startswith('/api/workbench/records'):
                value = {'items': [], 'total': 0, 'offset': 0, 'limit': 1}
            elif self.path == '/api/workspace/projects':
                value = {'id': CATALOG, 'manifest_sha256':'a'*64}
            else: value = {'ok': True}
            if mode == 'false_success' and self.command == 'POST': value = {'error': 'Not success'}
            if mode == 'revoked' and self.path == '/api/agent/operations' and sum(path == self.path for _,path,_ in calls) > 1:
                value = {'code':'unauthenticated','error':'Credential is revoked.'}
            raw = json.dumps(value).encode()
            if mode == 'trickle' and self.path.endswith('/records'):
                try:
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Trickle: '); self.wfile.flush()
                    for _ in range(40):
                        self.wfile.write(b'x'); self.wfile.flush(); time.sleep(.02)
                except OSError: pass
                return
            status = 307 if mode == 'redirect' else 503 if mode in ('unknown','code_echo') and self.command == 'POST' else 200
            if mode == 'revoked' and value.get('code') == 'unauthenticated': status = 401
            if status == 503: raw = json.dumps({'code':TOKEN if mode == 'code_echo' else 'commit_unknown','error':'Uncertain '+TOKEN}).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html' if mode == 'html' else 'application/json')
            self.send_header('Content-Length', '9'*5000 if mode == 'huge_digits' else str(len(raw)+1 if mode == 'truncated' else api.RESPONSE_LIMIT+1 if mode == 'huge' else len(raw)))
            if mode == 'duplicate': self.send_header('Content-Length', str(len(raw)))
            if mode == 'compressed': self.send_header('Content-Encoding', 'gzip')
            if mode == 'chunked': self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            self.wfile.write(raw)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    try: yield 'http://127.0.0.1:'+str(httpd.server_port), calls
    finally: httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


class ClientTests(unittest.TestCase):
    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_three_file_sequence_is_unsupported_before_http_dispatch(self):
        supported = {'files': {'run.json': 'YQ==', 'frames.jsonl': 'YQ=='}, 'groups': ['source']}
        api.validate_arguments('data.import_sequence', supported)
        unsupported = dict(supported, files=dict(supported['files'], **{'controls.json': 'YQ=='}))
        with server() as (endpoint, calls):
            client = api.AgentClient(endpoint, TOKEN, CATALOG)
            for name in ('data.import_sequence', 'data_import_sequence'):
                with self.subTest(name=name), self.assertRaises(api.AgentAPIError) as caught:
                    client.call(name, unsupported)
                self.assertEqual((caught.exception.code, caught.exception.status), ('unsupported', 400))
                self.assertEqual(str(caught.exception), 'Generic agent sequence imports support run.json and frames.jsonl only.')
                self.assertEqual(calls, [], 'Unsupported sequence must not bootstrap, inspect or mutate HTTP state.')
                self.assertFalse(client._ready)

    def test_fixed_endpoint_and_private_configuration(self):
        for endpoint in ('https://127.0.0.1:1', 'http://localhost:1', 'http://127.0.0.2:1', 'http://127.0.0.1:1/x', 'http://user@127.0.0.1:1', 'http://127.0.0.1:1?x=1'):
            with self.assertRaises(api.AgentAPIError): api.AgentClient(endpoint, TOKEN, CATALOG)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory); token = path/'token'; config = path/'config'
            token.write_text(TOKEN); token.chmod(0o600)
            config.write_text(json.dumps({'endpoint':'http://127.0.0.1:1','catalog_id':CATALOG,'token_file':str(token)})); config.chmod(0o600)
            api.AgentClient.from_config(config)
            token.chmod(0o644)
            with self.assertRaises(api.AgentAPIError): api.AgentClient.from_config(config)
            token.unlink(); token.symlink_to(config)
            with self.assertRaises(api.AgentAPIError): api.AgentClient.from_config(config)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_authenticated_discovery_proxy_ignored_and_one_mutation(self):
        with server() as (endpoint, calls), patch.dict(os.environ, {'http_proxy':'http://bad.invalid:1', 'HTTP_PROXY':'http://bad.invalid:1'}):
            client = api.AgentClient(endpoint, TOKEN, CATALOG)
            self.assertEqual(client.call('data.query', {'limit':1})['status'], 200)
            self.assertEqual(client.call('projects.open', {'root':'qa','manifest_path':'project.json'})['status'], 200)
            self.assertEqual(sum(method=='POST' for method,_,_ in calls), 1)
            self.assertEqual(sum(path=='/api/agent/operations' for _,path,_ in calls), 2)
            self.assertTrue(all(auth=='Bearer '+TOKEN for _,_,auth in calls))

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_framing_identity_registry_refusals(self):
        for mode in ('owner','mismatch','redirect','html','duplicate','compressed','chunked','truncated','huge','huge_digits'):
            with self.subTest(mode=mode), server(mode) as (endpoint,calls):
                with self.assertRaises(api.AgentAPIError) as caught:
                    api.AgentClient(endpoint,TOKEN,CATALOG).call('projects.open',{'root':'qa','manifest_path':'project.json'})
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertFalse(any(method=='POST' for method,_,_ in calls))

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_unknown_commit_is_not_retried_or_secret_echoed(self):
        with server('unknown') as (endpoint,calls):
            result = api.AgentClient(endpoint,TOKEN,CATALOG).call('projects.open',{'root':'qa','manifest_path':'project.json'})
            self.assertEqual(result['status'],503)
            self.assertEqual(result['result']['code'],'commit_unknown')
            self.assertNotIn(TOKEN,json.dumps(result))
            self.assertEqual(sum(method=='POST' for method,_,_ in calls),1)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_absolute_header_deadline_includes_trickle(self):
        with server('trickle') as (endpoint,_calls):
            client = api.AgentClient(endpoint,TOKEN,CATALOG,timeout=.15)
            client.bootstrap()
            start=time.monotonic()
            with self.assertRaises(api.AgentAPIError): client.call('data.query',{})
            self.assertLess(time.monotonic()-start,1)


class OutputTests(unittest.TestCase):
    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_typed_error_and_success_shapes(self):
        for name in ('data.query', 'runs.list', 'projects.open', 'runs.artifact_chunk'):
            with self.assertRaises(api.AgentAPIError):
                api.validate_output(name, {'status':200,'result':{'error':'not success'}})
            api.validate_output(name, {'status':409,'result':{'error':'Domain refused','code':'conflict'}})
        with self.assertRaises(api.AgentAPIError):
            api.validate_output('runs.list', {'status':200,'result':{}})
        for mode in ('false_success','code_echo'):
            with server(mode) as (endpoint,calls):
                with self.assertRaises(api.AgentAPIError) as caught:
                    api.AgentClient(endpoint,TOKEN,CATALOG).call('projects.open',{'root':'qa','manifest_path':'project.json'})
                self.assertNotIn(TOKEN,str(caught.exception))
                self.assertEqual(sum(method=='POST' for method,_,_ in calls),1)

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_segment_reassembly_and_whole_hash_tamper(self):
        original=b'whole original artifact'
        expected=hashlib.sha256(original).hexdigest()
        class Client:
            payload=original
            def call(self,name,args):
                data=self.payload[args['offset']:args['offset']+args['max_bytes']]
                value={k:args[k] for k in ('run_id','name','expected_sha256','offset')}
                value.update(total_bytes=len(self.payload),media_type='application/octet-stream',bytes=len(data),
                             next_offset=args['offset']+len(data),eof=args['offset']+len(data)==len(self.payload),
                             data_base64=base64.b64encode(data).decode(),segment_sha256=hashlib.sha256(data).hexdigest(),
                             verification='segment_read_whole_hash_unverified')
                envelope={'status':200,'result':value}
                api.validate_output(name,envelope)
                return envelope
        client=Client();chunks=[]
        result=api.verify_artifact(client,CATALOG,'result.bin',expected,consume=chunks.append,chunk_bytes=5)
        self.assertEqual(b''.join(chunks),original)
        self.assertEqual(result['verification'],'whole_sha256_verified')
        client.payload=b'x'+original[1:]
        with self.assertRaises(api.AgentAPIError) as caught:
            api.verify_artifact(client,CATALOG,'result.bin',expected,chunk_bytes=5)
        self.assertEqual(caught.exception.code,'artifact_mismatch')


class ParityRegressionTests(unittest.TestCase):
    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_image_forwards_exact_raw_base64(self):
        raw = base64.b64encode(b'original image bytes').decode()
        _, _, body = api.project_request('data.import_image', {'image':raw,'groups':['source']})
        self.assertEqual(body, {'image':raw,'groups':['source'],'kind':'image'})
        with self.assertRaises(api.AgentAPIError):
            api.validate_arguments('data.import_image', {'image':'data:image/png;base64,'+raw,'groups':['source']})

    @unittest.skipUnless(HAS_JSONSCHEMA, 'Optional agent jsonschema dependency is not installed.')
    def test_revoked_discovery_preserves_http_status_and_code_without_mutation(self):
        with server('revoked') as (endpoint,calls):
            client=api.AgentClient(endpoint,TOKEN,CATALOG)
            client.bootstrap()
            with self.assertRaises(api.AgentAPIError) as caught:
                client.call('projects.open', {'root':'qa','manifest_path':'project.json'})
            self.assertEqual((caught.exception.status,caught.exception.code),(401,'unauthenticated'))
            self.assertEqual(str(caught.exception),'Credential is revoked.')
            self.assertFalse(any(method=='POST' for method,_,_ in calls))
