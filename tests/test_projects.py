"""Real project registration and read-only filesystem/HTTP inspection boundaries."""
from auth_helpers import bind_owner
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
import projects
from workbench import WorkbenchError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProjectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.external = self.path / 'external'
        self.external.mkdir()
        self.files = {'data.bin': b'native-data', 'recipe.py': b'raise RuntimeError("Project source must never execute")\n',
                      'note.md': b'# Evidence\nDeclared observations only.\n', 'runtime.txt': b'Unqualified environment declaration\n'}
        for name, raw in self.files.items():
            (self.external / name).write_bytes(raw)
        self.value = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Local fixture',
                      'data': [{'id': 'source', 'label': 'Native source', 'path': 'data.bin', 'sha256': sha(self.files['data.bin'])}],
                      'recipes': [{'id': 'script', 'label': 'Unexecuted recipe', 'path': 'recipe.py'}],
                      'evidence': [{'id': 'note', 'label': 'Observations', 'path': 'note.md', 'sha256': sha(self.files['note.md'])}],
                      'requirements': [{'id': 'python', 'label': 'Declared Python'},
                                       {'id': 'runtime', 'label': 'Runtime file', 'path': 'runtime.txt'}]}
        self.write_manifest()
        self.dataset = Dataset(self.path / 'catalog', project_roots={'fixture': self.external}); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(lambda: self.dataset.close())
        self.owner = self.dataset.projects

    def write_manifest(self, value=None, raw=None, name='project.json'):
        (self.external / name).write_bytes(raw if raw is not None else json.dumps(value or self.value).encode())

    def open(self, **changes):
        return self.owner.open(dict({'root': 'fixture', 'manifest_path': 'project.json'}, **changes))

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.external.iterdir() if path.is_file() and not path.is_symlink()}

    def reopen(self, roots):
        self.dataset.close()
        self.dataset = Dataset(self.path / 'catalog', project_roots=roots); self.actor = bind_owner(self, self.dataset)
        self.owner = self.dataset.projects

    def test_real_registration_reads_hashes_and_never_executes_or_mutates_sources(self):
        before = self.snapshot()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Inspection cannot execute project code')):
            result = self.open()
            self.assertEqual(self.open(), result)
            evidence = self.owner.evidence(self.value['id'], 'note')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result['mode'], 'inspection')
        self.assertEqual(result['execution'], 'unsupported')
        self.assertEqual(result['manifest_status'], 'unchanged')
        self.assertEqual(result['data'][0]['integrity'], 'verified')
        self.assertEqual(result['recipes'][0]['integrity'], 'unverified')
        self.assertEqual(result['requirements'][0]['status'], 'unverified')
        self.assertEqual(result['requirements'][1]['status'], 'present_unqualified')
        self.assertEqual(evidence['text'], self.files['note.md'].decode())
        self.assertEqual(evidence['scientific_verification'], 'not_performed')
        self.assertEqual(len(self.owner.list()['projects']), 1)
        self.reopen({'fixture': self.external})
        self.assertEqual(self.owner.get(self.value['id']), result)

    def test_data_reference_captures_exact_bytes_and_saved_origin(self):
        before = self.snapshot()
        opened = self.open()
        expected = sha(self.files['data.bin'])
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Read cannot execute source')):
            raw, origin = self.owner.read_data_reference(self.value['id'], 'source', expected, projects.DATA_LIMIT)
        self.assertEqual(raw, self.files['data.bin'])
        self.assertEqual(origin, {'project_id': self.value['id'], 'manifest_sha256': opened['manifest_sha256'],
            'reference_id': 'source', 'path': 'data.bin', 'measured_sha256': expected})
        self.assertEqual(self.snapshot(), before)
        (self.external / 'data.bin').write_bytes(b'replaced after capture')
        self.assertEqual(raw, self.files['data.bin'], 'Caller owns captured bytes, not a path reopened later')

    def test_data_reference_refuses_stale_or_declared_hash_mismatch(self):
        self.open()
        changed = b'new source bytes'
        (self.external / 'data.bin').write_bytes(changed)
        for expected in (sha(self.files['data.bin']), sha(changed)):
            with self.subTest(expected=expected), self.assertRaises(WorkbenchError) as caught:
                self.owner.read_data_reference(self.value['id'], 'source', expected, projects.DATA_LIMIT)
            self.assertEqual(caught.exception.code, 'conflict')
        self.value['id'] = uuid.uuid4().hex
        self.value['data'][0].pop('sha256')
        self.write_manifest()
        self.open()
        with self.assertRaises(WorkbenchError) as caught:
            self.owner.read_data_reference(self.value['id'], 'source', sha(self.files['data.bin']), projects.DATA_LIMIT)
        self.assertEqual(caught.exception.code, 'conflict')
        self.assertEqual(self.owner.read_data_reference(self.value['id'], 'source', sha(changed), projects.DATA_LIMIT)[0], changed)

    def test_data_reference_bounds_and_section_selection(self):
        self.open()
        expected = sha(self.files['data.bin'])
        for reference in ('note', 'script', 'runtime', 'absent', '../data.bin', '/data.bin'):
            with self.subTest(reference=reference), self.assertRaises(WorkbenchError) as caught:
                self.owner.read_data_reference(self.value['id'], reference, expected, projects.DATA_LIMIT)
            self.assertEqual(caught.exception.code, 'not_found')
        for digest, limit in ((None, 100), ('bad', 100), ('A'*64, 100),
                              (expected, True), (expected, 0), (expected, projects.DATA_LIMIT+1)):
            with self.subTest(digest=digest, limit=limit), self.assertRaises(WorkbenchError):
                self.owner.read_data_reference(self.value['id'], 'source', digest, limit)
        with self.assertRaises(WorkbenchError) as caught:
            self.owner.read_data_reference(self.value['id'], 'source', expected, len(self.files['data.bin'])-1)
        self.assertEqual(caught.exception.code, 'too_large')

    def test_data_reference_inspection_exceeds_text_budget_but_obeys_total_budget(self):
        raw = b'x' * (projects.FILE_LIMIT + 1)
        (self.external / 'data.bin').write_bytes(raw)
        self.value['data'][0]['sha256'] = sha(raw)
        self.value['recipes'] = [{'id': 'same', 'label': 'Same file as recipe', 'path': 'data.bin'}]
        self.write_manifest()
        opened = self.open()
        self.assertEqual(opened['data'][0]['observed_sha256'], sha(raw))
        self.assertEqual(opened['data'][0]['bytes'], len(raw))
        self.assertEqual(opened['recipes'][0]['integrity'], 'unverified')
        self.assertNotIn('observed_sha256', opened['recipes'][0])
        captured, _origin = self.owner.read_data_reference(self.value['id'], 'source', sha(raw), projects.DATA_LIMIT)
        self.assertEqual(captured, raw)
        with patch.object(projects, 'INSPECTION_LIMIT', len(raw)-1):
            bounded = self.owner.get(self.value['id'])
        self.assertNotIn('observed_sha256', bounded['data'][0])
        self.assertEqual(bounded['data'][0]['integrity'], 'unverified')

    def test_data_reference_missing_and_rebound_root_never_reads_replacement(self):
        self.open()
        expected = sha(self.files['data.bin'])
        (self.external / 'data.bin').unlink()
        with self.assertRaises(WorkbenchError) as caught:
            self.owner.read_data_reference(self.value['id'], 'source', expected, projects.DATA_LIMIT)
        self.assertEqual(caught.exception.code, 'unavailable')
        replacement = self.path / 'replacement'
        replacement.mkdir()
        (replacement / 'data.bin').write_bytes(self.files['data.bin'])
        for roots in ({}, {'fixture': replacement}):
            self.reopen(roots)
            with patch.object(self.owner, '_read', side_effect=AssertionError('Rebound root must not be read')):
                with self.assertRaises(WorkbenchError) as caught:
                    self.owner.read_data_reference(self.value['id'], 'source', expected, projects.DATA_LIMIT)
            self.assertEqual(caught.exception.code, 'unavailable')

    def test_data_reference_rejects_symlinks_special_files_and_traversal(self):
        outside = self.path / 'outside.bin'
        outside.write_bytes(self.files['data.bin'])
        (self.external / 'link.bin').symlink_to(outside)
        (self.external / 'linkdir').symlink_to(self.path, target_is_directory=True)
        (self.external / 'folder.bin').mkdir()
        os.mkfifo(self.external / 'pipe.bin')
        paths = ('link.bin', 'linkdir/outside.bin', 'folder.bin', 'pipe.bin')
        self.value['data'] = [{'id': 'r'+str(index), 'label': path, 'path': path} for index, path in enumerate(paths)]
        self.write_manifest()
        self.open()
        for index, path in enumerate(paths):
            with self.subTest(path=path), self.assertRaises(WorkbenchError):
                self.owner.read_data_reference(self.value['id'], 'r'+str(index), sha(self.files['data.bin']), projects.DATA_LIMIT)
        for path in ('../outside.bin', '/outside.bin', 'folder.bin/../data.bin'):
            self.value['id'] = uuid.uuid4().hex
            self.value['data'] = [{'id': 'source', 'label': 'Unsafe', 'path': path}]
            self.write_manifest()
            with self.subTest(path=path), self.assertRaises(WorkbenchError):
                self.open()
        self.assertEqual(len(self.owner.list()['projects']), 1)

    def test_changed_manifest_flags_original_snapshot_and_id_conflicts(self):
        opened = self.open()
        changed = copy.deepcopy(self.value)
        changed['name'] = 'Changed owner file'
        changed['data'] = []
        self.write_manifest(changed)
        current = self.owner.get(self.value['id'])
        self.assertEqual(current['manifest_status'], 'changed')
        self.assertEqual(current['name'], opened['name'])
        self.assertEqual(current['data'], opened['data'])
        with self.assertRaises(WorkbenchError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'conflict')
        self.assertEqual(len(self.owner.list()['projects']), 1)
        self.write_manifest(name='elsewhere.json')
        with self.assertRaises(WorkbenchError):
            self.open(manifest_path='elsewhere.json')
        (self.external / 'project.json').unlink()
        self.assertEqual(self.owner.get(self.value['id'])['manifest_status'], 'missing')

    def test_absent_and_rebound_roots_keep_snapshot_without_new_root_reads(self):
        self.open()
        self.reopen({})
        result = self.owner.get(self.value['id'])
        self.assertEqual(result['manifest_status'], 'unavailable')
        self.assertEqual(result['data'][0]['status'], 'unavailable')
        self.assertEqual(self.owner.list()['roots'], [])
        with self.assertRaises(WorkbenchError):
            self.owner.evidence(self.value['id'], 'note')
        replacement = self.path / 'different'
        replacement.mkdir()
        for name, raw in self.snapshot().items():
            (replacement / name).write_bytes(raw)
        self.reopen({'fixture': replacement})
        self.assertEqual(self.owner.get(self.value['id'])['data'][0]['status'], 'unavailable')
        with self.assertRaises(WorkbenchError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'conflict')

    def test_manifest_traversal_symlinks_directories_and_fifo_refused_without_registration(self):
        outside = self.path / 'outside.json'
        outside.write_text(json.dumps(self.value))
        (self.external / 'link.json').symlink_to(outside)
        (self.external / 'directory').mkdir()
        (self.external / 'linkdir').symlink_to(self.path, target_is_directory=True)
        os.mkfifo(self.external / 'fifo.json')
        for path in ('../outside.json', '/absolute.json', 'directory/../project.json', './project.json',
                     'directory//file', 'directory\\file', '/'.join(['deep']*17), 'link.json', 'directory', 'fifo.json', 'linkdir/outside.json'):
            with self.subTest(path=path), self.assertRaises(WorkbenchError):
                self.open(manifest_path=path)
        self.assertEqual(self.owner.list()['projects'], [])

    def test_unsafe_reference_files_and_missing_entries_are_reported_without_following(self):
        (self.external / 'link.md').symlink_to(self.path / 'outside.md')
        (self.path / 'outside.md').write_text('outside secret')
        os.mkfifo(self.external / 'pipe.md')
        (self.external / 'folder.md').mkdir()
        self.value['evidence'] = [{'id': str(index), 'label': name, 'path': name}
                                  for index, name in enumerate(('link.md', 'pipe.md', 'folder.md', 'missing.md'))]
        self.write_manifest()
        result = self.open()
        self.assertEqual([entry['status'] for entry in result['evidence']], ['unavailable','unavailable','unavailable','missing'])
        for entry in self.value['evidence']:
            with self.assertRaises(WorkbenchError):
                self.owner.evidence(self.value['id'], entry['id'])

    def test_malformed_manifest_types_json_and_unknown_fields_are_atomic(self):
        invalid = [b'{"schema_version":1,"schema_version":1}', b'\xff', b'{"name":NaN}', b'['*1200+b']'*1200, b'{}']
        for mutation in (
            {'schema_version': True}, {'schema_version': 2}, {'id': 'bad'}, {'name': ''}, {'name': '\ud800'},
            {'data': {}}, {'data': [None]}, {'data': [{'id':'x','label':'x','path':'../bad'}]},
            {'data': [{'id':'x','label':'x','path':'data.bin','sha256':'not-a-hash'}]},
            {'requirements': [{'id':'a','label':'x','sha256':'0'*64}]}, {'extra': 1},
        ):
            invalid.append(json.dumps(dict(self.value, **mutation)).encode())
        duplicated = copy.deepcopy(self.value)
        duplicated['data'] *= 2
        invalid.append(json.dumps(duplicated).encode())
        for raw in invalid:
            self.write_manifest(raw=raw)
            with self.subTest(raw=raw[:80]), self.assertRaises(WorkbenchError):
                self.open()
        self.assertEqual(self.owner.list()['projects'], [])

    def test_evidence_hash_text_suffix_and_size_fail_closed(self):
        self.open()
        for raw in (b'changed', b'\xff', b'\x00binary', b'x'*(projects.TEXT_LIMIT+1)):
            (self.external / 'note.md').write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises(WorkbenchError):
                self.owner.evidence(self.value['id'], 'note')
        with self.assertRaises(WorkbenchError):
            self.owner.evidence(self.value['id'], 'script')
        self.value['id'] = uuid.uuid4().hex
        self.value['evidence'] = [{'id':'code','label':'Code','path':'recipe.py'}]
        self.write_manifest()
        self.open()
        with self.assertRaises(WorkbenchError) as caught:
            self.owner.evidence(self.value['id'], 'code')
        self.assertEqual(caught.exception.code, 'unsupported')

    def test_unhashed_evidence_controls_remain_unavailable_and_changed_sources_are_explicit(self):
        self.value['evidence'][0].pop('sha256')
        self.write_manifest()
        self.open()
        for raw in (b'\x00binary', b'\x1b[31mterminal'):
            (self.external / 'note.md').write_bytes(raw)
            with self.assertRaises(WorkbenchError) as caught:
                self.owner.evidence(self.value['id'], 'note')
            self.assertEqual(caught.exception.code, 'unsupported')
        (self.external / 'data.bin').write_bytes(b'changed native bytes')
        inspected = self.owner.get(self.value['id'])['data'][0]
        self.assertEqual(inspected['status'], 'available')
        self.assertEqual(inspected['integrity'], 'mismatch')
        self.assertEqual(inspected['sha256'], sha(self.files['data.bin']))
        self.assertEqual(inspected['observed_sha256'], sha(b'changed native bytes'))
        (self.external / 'data.bin').unlink()
        self.assertEqual(self.owner.get(self.value['id'])['data'][0]['status'], 'missing')

    def test_file_manifest_reference_and_total_inspection_budgets(self):
        self.write_manifest(raw=b' ' * (projects.MANIFEST_LIMIT+1))
        with self.assertRaises(WorkbenchError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'too_large')
        self.value['data'] = [{'id':f'a{i}','label':'One','path':'data.bin'} for i in range(65)]
        self.write_manifest()
        with self.assertRaises(WorkbenchError):
            self.open()
        with (self.external / 'large.bin').open('wb') as handle:
            handle.truncate(projects.DATA_LIMIT+1)
        self.value['data'] = [{'id':'large','label':'Large','path':'large.bin','sha256':'0'*64},
                              {'id':'small','label':'Small','path':'data.bin','sha256':sha(self.files['data.bin'])}]
        self.write_manifest()
        result = self.open()
        self.assertEqual(result['data'][0]['integrity'], 'unverified')
        self.assertNotIn('observed_sha256', result['data'][0])
        self.assertEqual(result['data'][1]['integrity'], 'verified')
        with patch.object(projects, 'INSPECTION_LIMIT', len(self.files['data.bin'])):
            result = self.owner.get(self.value['id'])
        self.assertEqual(result['data'][1]['integrity'], 'verified')
        self.assertNotIn('observed_sha256', result['recipes'][0])
        self.assertNotIn('observed_sha256', result['evidence'][0])

    def test_request_misuse_invalid_ids_and_configuration_are_typed(self):
        for body in (None, [], {}, {'root': '/tmp','manifest_path':'project.json'},
                     {'root': {},'manifest_path':'project.json'}, {'root':'fixture','manifest_path':True},
                     {'root':'fixture','manifest_path':'project.json','execute':True}):
            with self.subTest(body=body), self.assertRaises(WorkbenchError):
                self.owner.open(body)
        for value in ('bad', '../project', True, uuid.uuid4().hex):
            with self.assertRaises(WorkbenchError):
                self.owner.get(value)
        for roots in ({'invalid/alias':self.external}, {'valid':self.path/'absent'}):
            with self.assertRaises(WorkbenchError):
                projects.Projects(self.dataset, roots)

    def test_real_http_registration_detail_evidence_and_no_execution_route(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        base = 'http://127.0.0.1:' + str(server.server_port) + '/api/workspace/projects'
        def request(suffix='', body=None, raw=None):
            raw = json.dumps(body).encode() if body is not None else raw
            with urllib.request.urlopen(self.actor.request(base+suffix, data=raw,
                    headers={'Content-Type':'application/json'} if raw is not None else {})) as response:
                return response.status, json.load(response)
        self.assertEqual(request()[1]['roots'], ['fixture'])
        status, opened = request(body={'root':'fixture','manifest_path':'project.json'})
        self.assertIn(status, (200,201))
        project = '/' + self.value['id']
        self.assertEqual(request(project)[1], opened)
        self.assertEqual(request(project+'/evidence/note')[1]['text'], self.files['note.md'].decode())
        for suffix, payload in (('', None), (project, None), (project+'/evidence/note', None),
                                ('', json.dumps({'root':'fixture','manifest_path':'project.json'}).encode())):
            hostile = self.actor.request(base+suffix, data=payload,
                headers={'Host':'attacker.example', 'Content-Type':'application/json'})
            with self.subTest(host='attacker.example', suffix=suffix, method=hostile.get_method()), self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(hostile)
            self.assertEqual(caught.exception.code, 403)
            self.assertEqual(json.loads(caught.exception.read())['code'], 'forbidden')
        self.assertEqual(len(self.owner.list()['projects']), 1)
        for suffix, raw in (('', b'{"root":"fixture","root":"fixture","manifest_path":"project.json"}'),
                            ('', b'{"x":'+b'['*1200+b'0'+b']'*1200+b'}'),
                            ('', b'{"root":"fixture","manifest_path":"../outside.json"}'),
                            (project+'/execute', b'{}')):
            with self.subTest(suffix=suffix), self.assertRaises(urllib.error.HTTPError) as caught:
                request(suffix, raw=raw)
            self.assertIn(caught.exception.code, (400,404,405))
