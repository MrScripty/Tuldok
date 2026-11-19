"""The steps Tuldok provides (docs/plans/definition-first-projects/spec-d4.md, section 6, slice D4c).

import and freeze are first tested as functions on directories the test
writes. Then a project is built for real through builds.execute: a Git
repository holding the project folder and its code side by side (code_root
../code, so the line files are read from the commit and not from the
snapshot), an import from a relative source, two tasks with annotations, a
third task on the same dataset, and a freeze. Those tests run only when
TULDOK_DATABASE_URL names a disposable cluster. No GPU, no environment: a step
runs with Tuldok's own interpreter, and the code root holds a decoy
tuldok_project/steps.py that fails if it is ever imported.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import (annotations, build_requests, builds, check, inside, local, plan, steps,  # noqa: E402
                            store)

DATABASE = os.environ.get('TULDOK_DATABASE_URL')
GIT = ['git', '-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false']
RIGHTS = 'Made by the test; anything may be done with them.'
AT = '2026-11-13T10:00:00Z'
PLY_FACES = b'ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\n' \
            b'element face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n'
PLY_POINTS = b'ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n' \
             b'end_header\n0 0 0\n'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _tree(root):
    """A source tree holding a file of each kind, nested files, names that make the same id, and links."""
    files = {
        'notes/a.txt': b'first line\n\n  \nsecond line\r\n',
        'notes/b.jsonl': b'{"text": "from json"}\n{"other": 1}\n[1, 2]\n',
        'images/cat.png': b'\x89PNG\r\n\x1a\nnot really',
        'sounds/hello.wav': b'RIFF....WAVE',
        'shapes/cloud.xyz': b'0 0 0\n1 1 1\n',
        'shapes/mesh.obj': b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n',
        'shapes/faces.ply': PLY_FACES,
        'shapes/points.ply': PLY_POINTS,
        'arrays/x.npy': b'\x93NUMPY fake',
        'other/blob.bin': b'\x00\x01\x02',
        'same id/a b.txt': b'one\n',
        'same id/a_b.txt': b'two\n',
        'odd/bang!name.txt': b'bang\n',
    }
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return files


def _records(output):
    with open(Path(output) / 'records.jsonl', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle]


def _row(record, state, value, sha256=None, by='owner'):
    return {'record': record, 'sha256': sha256, 'state': state, 'value': value, 'by': by, 'at': AT}


class Shared(unittest.TestCase):
    """What steps.py repeats from inside.py, standard library alone, stays the same."""

    def test_kinds_patterns_and_ids(self):
        self.assertEqual(steps.EXTENSIONS, inside.EXTENSIONS)
        self.assertEqual(steps.KINDS, inside.KINDS)
        for pattern in ('**/*', '*.png', 'a/**/b?.txt', '**', 'x/*/y'):
            self.assertEqual(steps.pattern_regex(pattern).pattern, inside.pattern_regex(pattern).pattern)
        self.assertEqual(steps.id_from('a b/c!d/é.png'), 'a_b__c_d___.png')
        self.assertEqual(len(steps.id_from('x' * 300)), 200)
        used = set()
        self.assertEqual([steps.unique(name, used, 200) for name in ('a.png', 'a.png', 'a.png', 'a-2.png')],
                         ['a.png', 'a-2.png', 'a-3.png', 'a-2-2.png'])
        long = 'y' * 196 + '.png'
        self.assertEqual(len(steps.unique(long, {long}, 200)), 200)


class Import(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.code = self.temporary / 'code'
        self.source = self.code / 'data'
        self.files = _tree(self.source)
        outside = self.temporary / 'outside'
        outside.mkdir()
        (outside / 'secret.txt').write_text('never imported', encoding='utf-8')
        os.symlink(outside / 'secret.txt', self.source / 'notes' / 'leaving.txt')
        os.symlink(outside, self.source / 'leaving-folder')
        os.symlink(self.source / 'images' / 'cat.png', self.source / 'other' / 'cat-again.png')
        self.said = []

    def output(self, name='out'):
        path = self.temporary / name
        path.mkdir()
        return path

    def run_import(self, settings, *, name='out', code=True):
        output = self.output(name)
        counts = steps.import_files({'rights': RIGHTS, **settings}, str(output),
                                    code_root=str(self.code) if code else None, out=self.said.append)
        return output, counts, _records(output)

    def test_every_kind_from_a_relative_source(self):
        output, counts, records = self.run_import({'source': 'data'})
        by_origin = {record['origin']['path']: record for record in records}
        kinds = {path: record['kind'] for path, record in by_origin.items()}
        self.assertEqual(kinds['images/cat.png'], 'image')
        self.assertEqual(kinds['sounds/hello.wav'], 'audio')
        self.assertEqual(kinds['shapes/cloud.xyz'], 'pointcloud')
        self.assertEqual(kinds['shapes/points.ply'], 'pointcloud')
        self.assertEqual(kinds['shapes/mesh.obj'], 'mesh')
        self.assertEqual(kinds['shapes/faces.ply'], 'mesh')
        self.assertEqual(kinds['arrays/x.npy'], 'array')
        self.assertEqual(kinds['other/blob.bin'], 'file')
        self.assertEqual(kinds['notes/a.txt'], 'text')
        # A link inside the source is imported where it stands; links leaving it are skipped and counted.
        self.assertIn('other/cat-again.png', by_origin)
        self.assertNotIn('notes/leaving.txt', by_origin)
        self.assertEqual(counts['links_out'], 2)
        self.assertTrue(any('2 symbolic links leaving the source were skipped.' in line for line in self.said))
        self.assertEqual(len(records), len(self.files) + 1)
        for path, data in self.files.items():
            record = by_origin[path]
            self.assertEqual((record['sha256'], record['bytes'], record['rights']), (_sha(data), len(data), RIGHTS))
            placed = output / record['path']
            self.assertEqual(placed.read_bytes(), data)
            self.assertEqual(os.stat(placed).st_ino, os.stat(self.source / path).st_ino)   # hard-linked
            self.assertEqual(list(record), ['id', 'kind', 'path', 'sha256', 'bytes', 'rights', 'origin'])
        # Ids from paths, made unique; a name holding '!' is placed where an address cannot read it as an archive.
        self.assertEqual(by_origin['images/cat.png']['id'], 'images__cat.png')
        self.assertEqual(by_origin['same id/a b.txt']['id'], 'same_id__a_b.txt')
        self.assertEqual(by_origin['same id/a_b.txt']['id'], 'same_id__a_b-2.txt')
        self.assertEqual(by_origin['odd/bang!name.txt']['path'], 'files/odd/bang_name.txt')
        self.assertEqual(by_origin['images/cat.png']['path'], 'files/images/cat.png')
        self.assertEqual(len({record['id'] for record in records}), len(records))
        # Nothing outside the output was written, nothing in the source changed.
        self.assertEqual(sorted(os.listdir(output)), ['files', 'records.jsonl'])
        self.assertEqual((self.source / 'notes' / 'a.txt').read_bytes(), self.files['notes/a.txt'])

    def test_by_pattern_with_a_kind_from_an_absolute_source(self):
        _, counts, records = self.run_import({'source': str(self.source), 'pattern': 'shapes/*.ply', 'kind': 'mesh'},
                                             code=False)
        self.assertEqual([(record['origin']['path'], record['kind']) for record in records],
                         [('shapes/faces.ply', 'mesh'), ('shapes/points.ply', 'mesh')])
        self.assertEqual(counts['links_out'], 1)   # the folder link is not a file the pattern can take

    def test_lines(self):
        _, counts, records = self.run_import({'source': 'data', 'pattern': 'notes/*', 'lines': True})
        texts = [(record['id'], record['text'], record['origin']) for record in records]
        self.assertEqual(texts, [
            ('notes__a.txt__1', 'first line', {'path': 'notes/a.txt', 'line': 1}),
            ('notes__a.txt__4', 'second line', {'path': 'notes/a.txt', 'line': 4}),
            ('notes__b.jsonl__1', 'from json', {'path': 'notes/b.jsonl', 'line': 1}),
            ('notes__b.jsonl__2', '{"other": 1}', {'path': 'notes/b.jsonl', 'line': 2}),
            ('notes__b.jsonl__3', '[1, 2]', {'path': 'notes/b.jsonl', 'line': 3})])
        for record in records:
            self.assertEqual(record['kind'], 'text')
            self.assertNotIn('path', record)
            self.assertEqual(record['sha256'], _sha(record['text'].encode('utf-8')))
            self.assertEqual(record['bytes'], len(record['text'].encode('utf-8')))
        self.assertEqual(counts['lines'], 5)

    def test_the_product_is_read_by_the_readers_with_its_hashes(self):
        output, _, records = self.run_import({'source': 'data', 'pattern': '**/*.txt', 'lines': True})
        product = inside.Product('run-import', str(output))
        listed = inside.records(product, limit=200)
        self.assertEqual(listed['source'], 'records.jsonl')
        self.assertEqual(listed['problems'], [])
        self.assertEqual(listed['total'], len(records))
        shown = {record['id']: record for record in listed['records']}
        for record in records:
            self.assertEqual(shown[record['id']]['sha256'], record['sha256'])
            self.assertEqual(shown[record['id']]['bytes'], record['bytes'])
            self.assertIsNone(shown[record['id']]['meta'])
        one = inside.record(product, records[0]['id'])
        self.assertEqual(one['content']['text'], records[0]['text'])
        self.assertEqual(one['record']['sha256'], records[0]['sha256'])

    def test_a_source_that_leaves_the_code_root(self):
        os.symlink(self.temporary / 'outside', self.code / 'away')
        with self.assertRaisesRegex(steps.StepError, 'outside the code root'):
            steps.import_files({'source': 'away', 'rights': RIGHTS}, str(self.output()), code_root=str(self.code),
                               out=self.said.append)


class Freeze(unittest.TestCase):
    """freeze on an imported product of ten text records, with two tasks."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        source = self.temporary / 'source'
        source.mkdir()
        for number in range(10):
            (source / f'r{number}.txt').write_text(f'record {number}\n', encoding='utf-8')
        self.product = self.temporary / 'product'
        self.product.mkdir()
        steps.import_files({'source': str(source), 'rights': RIGHTS}, str(self.product), out=lambda text: None)
        self.records = {record['id']: record for record in _records(self.product)}
        self.count = 0

    def lines(self, name, rows):
        path = self.temporary / f'{name}.jsonl'
        data = annotations.write(rows)
        path.write_bytes(data)
        return str(path), _sha(data)

    def task(self, name, rows, task='class', vocabulary=('good', 'bad')):
        path, digest = self.lines(name, rows)
        return {'reference': f'annotations/{name}', 'task': task, 'vocabulary': list(vocabulary), 'lines': path,
                'sha256': digest}

    def freeze(self, settings, tasks):
        self.count += 1
        output = self.temporary / f'frozen-{self.count}'
        output.mkdir()
        said = []
        counts = steps.freeze_records(settings, str(output), records=str(self.product), tasks=tasks,
                                      out=said.append)
        return output, counts, _records(output), said

    def accepted_all(self):
        return [_row(identifier, 'accepted', 'good', record['sha256'])
                for identifier, record in self.records.items()]

    def test_splits_by_the_shares_the_same_for_a_seed(self):
        tasks = [self.task('quality', self.accepted_all())]
        settings = {'seed': 7, 'shares': {'train': 8, 'validation': 1, 'test': 1}}
        output, counts, frozen, _ = self.freeze(settings, tasks)
        self.assertEqual([record['split'] for record in frozen], ['test'] + ['train'] * 8 + ['validation'])
        self.assertEqual(counts['included'], 10)
        again = self.freeze(settings, tasks)[2]
        self.assertEqual(frozen, again)
        other = self.freeze({**settings, 'seed': 8}, tasks)[2]
        self.assertNotEqual([record['id'] for record in frozen], [record['id'] for record in other])
        self.assertEqual(sorted(record['id'] for record in frozen), sorted(record['id'] for record in other))
        # The order is the SHA-256 of the seed and the record's hash.
        expected = sorted(self.records.values(), key=lambda record: steps.order_key(7, record['sha256'], record['id']))
        self.assertEqual([record['id'] for record in frozen], [record['id'] for record in expected])
        for record in frozen:
            source = self.records[record['id']]
            self.assertEqual(record['sha256'], source['sha256'])
            self.assertEqual(record['annotations'], {'quality': {'state': 'accepted', 'value': 'good'}})
            self.assertEqual(os.stat(output / record['path']).st_ino, os.stat(self.product / source['path']).st_ino)
            self.assertEqual(list(record)[-2:], ['split', 'annotations'])

    def test_includes_by_state_and_leaves_out_stale_ones(self):
        ids = sorted(self.records)
        rows = [_row(ids[0], 'accepted', 'good', self.records[ids[0]]['sha256']),
                _row(ids[1], 'accepted', 'bad', None),                          # tied by id alone
                _row(ids[2], 'needs-work', 'bad', self.records[ids[2]]['sha256']),
                _row(ids[3], 'rejected', None, self.records[ids[3]]['sha256']),
                _row(ids[4], 'accepted', 'good', '0' * 64),                    # its content differs
                _row('gone', 'accepted', 'good', '1' * 64),                     # its record is gone
                _row(ids[5], 'draft', None, self.records[ids[5]]['sha256'])]
        captions = [_row(ids[0], 'draft', 'a caption', self.records[ids[0]]['sha256']),
                    _row(ids[1], 'accepted', 'stale caption', '2' * 64),
                    _row(ids[9], 'accepted', 'not taken', None)]
        tasks = [self.task('quality', rows), self.task('captions', captions, task='text', vocabulary=())]
        _, counts, frozen, said = self.freeze({'seed': 1, 'shares': {'all': 1}}, tasks)
        self.assertEqual(sorted(record['id'] for record in frozen), [ids[0], ids[1]])
        carried = {record['id']: record['annotations'] for record in frozen}
        self.assertEqual(carried[ids[0]], {'quality': {'state': 'accepted', 'value': 'good'},
                                           'captions': {'state': 'draft', 'value': 'a caption'}})
        self.assertEqual(carried[ids[1]], {'quality': {'state': 'accepted', 'value': 'bad'}})
        self.assertEqual((counts['stale'], counts['excluded'], counts['unannotated'], counts['stale_other']),
                         (2, 3, 4, 1))
        self.assertIn('2 annotations of quality are stale (the record is gone or its content differs) and were '
                      'left out.', said)
        self.assertTrue(any(line.startswith('{"format":"tuldok_progress_v1","stage":"freeze"') for line in said))
        wider = self.freeze({'seed': 1, 'shares': {'all': 1}, 'include': ['accepted', 'needs-work', 'draft']},
                            tasks)[2]
        self.assertEqual(sorted(record['id'] for record in wider), [ids[0], ids[1], ids[2], ids[5]])

    def test_a_changed_line_file_is_refused(self):
        task = self.task('quality', self.accepted_all())
        task['sha256'] = '3' * 64
        with self.assertRaisesRegex(steps.StepError, 'not the file the build read'):
            self.freeze({'seed': 1, 'shares': {'all': 1}}, [task])


class Checked(unittest.TestCase):
    """check: the step's settings, inputs and tasks (section 6), on a folder written by the test."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.folder = self.root / 'project'
        _write_project(self.root, uuid.uuid4().hex)

    def problems(self):
        report = check.check_folder(self.folder)
        return {(problem.severity, problem.path, problem.pointer, problem.message) for problem in report.problems}

    def write(self, reference, document):
        path = self.folder / f'{reference}.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def test_the_fixture_checks(self):
        self.assertEqual({problem for problem in self.problems() if problem[0] == 'error'}, set())

    def test_an_absolute_source_is_a_warning(self):
        self.write('datasets/raw', _import_definition({'source': str(self.root / 'code' / 'data')}))
        self.assertIn(('warning', 'datasets/raw.json', '/run/settings/source',
                       f'The source {self.root / "code" / "data"} is absolute, so this dataset can be built on this '
                       'machine only; give a path relative to the code root.'), self.problems())

    def test_settings_and_fields_a_step_does_not_take(self):
        document = _import_definition({'source': 'missing', 'kind': 'video', 'lines': 'yes', 'extra': 1,
                                       'pattern': '../x'})
        del document['run']['settings']['rights']
        document['run'].update(command=['python', 'x.py'], environment='environments/none',
                               outputs={'data': {'path': 'x', 'role': 'data'}})
        self.write('datasets/raw', document)
        found = {(pointer, severity) for severity, path, pointer, _ in self.problems() if path == 'datasets/raw.json'}
        for pointer in ('/run/settings/rights', '/run/settings/kind', '/run/settings/lines', '/run/settings/extra',
                        '/run/settings/pattern', '/run/settings/source', '/run/command', '/run/environment',
                        '/run/outputs'):
            self.assertIn((pointer, 'error'), found)

    def test_a_freeze_by_a_task_of_another_dataset(self):
        self.write('datasets/elsewhere', _import_definition({'source': 'data'}))
        self.write('annotations/other-place', {'format': 'tuldok_definition_v1', 'kind': 'annotation',
                                               'title': 'Elsewhere', 'dataset': 'datasets/elsewhere',
                                               'task': 'review'})
        frozen = _freeze_definition(['annotations/quality', 'annotations/other-place'])
        frozen['run']['settings'] = {'seed': 1.5, 'shares': {'train': 0}, 'include': ['accepted', 'accepted']}
        self.write('datasets/frozen', frozen)
        problems = self.problems()
        self.assertIn(('error', 'datasets/frozen.json', '/run/annotations/1',
                       'annotations/other-place annotates datasets/elsewhere, not datasets/raw, the input of this '
                       'freeze; name a task of its input.'), problems)
        found = {pointer for severity, path, pointer, _ in problems if path == 'datasets/frozen.json'}
        self.assertTrue({'/run/settings/seed', '/run/settings/shares', '/run/settings/include'} <= found)

    def test_a_plan_shows_the_step_and_notes_a_task_elsewhere(self):
        definitions = {path.parent.name + '/' + path.stem: json.loads(path.read_text(encoding='utf-8'))
                       for path in self.folder.glob('*/*.json')}
        definitions['annotations/quality']['dataset'] = 'datasets/frozen'
        made = plan.make_plan(definitions, ['datasets/frozen'])
        shown = {step['reference']: (step['command'], step['environment'], step['step'], step['annotations'])
                 for step in made['steps']}
        self.assertEqual(shown, {'datasets/raw': (['tuldok', 'import'], None, 'import', []),
                                 'datasets/frozen': (['tuldok', 'freeze'], None, 'freeze',
                                                     ['annotations/quality', 'annotations/captions'])})
        self.assertIn('datasets/frozen freezes by annotations/quality, which annotates datasets/frozen, not its '
                      'input datasets/raw; it fails when built.', made['notes'])


# ------------------------------------------------------------- a project

def _import_definition(settings):
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Imported',
            'run': {'step': 'import', 'settings': {'rights': RIGHTS, **settings}}}


def _freeze_definition(tasks):
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Frozen',
            'run': {'step': 'freeze', 'inputs': {'records': 'datasets/raw'}, 'annotations': tasks,
                    'settings': {'seed': 11, 'shares': {'train': 3, 'test': 1}}}}


def _write_project(root, project_id):
    """root/project (the folder, code_root ../code) and root/code (a source tree, and a decoy of Tuldok's steps)."""
    folder, code = root / 'project', root / 'code'
    for directory in ('datasets', 'annotations'):
        (folder / directory).mkdir(parents=True)
    (folder / 'tuldok.json').write_text(json.dumps({'format': 'tuldok_project_v1', 'id': project_id,
                                                    'name': 'Steps test project', 'code_root': '../code'},
                                                   indent=2) + '\n', encoding='utf-8')
    definitions = {
        'datasets/raw': _import_definition({'source': 'data', 'pattern': '**/*.txt'}),
        'datasets/frozen': _freeze_definition(['annotations/quality', 'annotations/captions']),
        'annotations/quality': {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': 'Quality',
                                'dataset': 'datasets/raw', 'task': 'class', 'vocabulary': ['good', 'bad']},
        'annotations/captions': {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': 'Captions',
                                 'dataset': 'datasets/raw', 'task': 'text'},
        'annotations/unrelated': {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': 'Unrelated',
                                  'dataset': 'datasets/raw', 'task': 'review'},
    }
    for reference, document in definitions.items():
        (folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    for number in range(8):
        path = code / 'data' / f'item-{number}.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'item {number}\n', encoding='utf-8')
    decoy = code / 'tuldok_project'
    decoy.mkdir()
    (decoy / '__init__.py').write_text('', encoding='utf-8')
    (decoy / 'steps.py').write_text('import sys\nprint("the snapshot\'s code was imported", file=sys.stderr)\n'
                                    'sys.exit(3)\n', encoding='utf-8')


def _writable(root):
    for current, directories, _files in os.walk(root):
        for name in directories:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                os.chmod(path, 0o755)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Built(unittest.TestCase):
    """import and freeze built for real by builds.execute, and the frozen dataset's out-of-date state."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / 'repository'
        self.root.mkdir()
        self.home = Path(directory.name) / 'home'
        self.addCleanup(_writable, self.home)
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project_id = uuid.uuid4().hex
        _write_project(self.root, self.project_id)
        self.folder = self.root / 'project'
        self.git('init', '-q')
        self.commit('The project.')
        self.addCleanup(store.drop_project, self.project_id)

    def git(self, *arguments):
        subprocess.run([*GIT, '-C', str(self.root), *arguments], check=True, capture_output=True, timeout=60)

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def opened(self):
        return store.open_project(self.folder)

    def build(self, *targets, scratch=False):
        with self.opened() as project:
            made = plan.build_plan(project, list(targets))
        done = builds.execute(self.folder, made, confirm=lambda given: True, scratch=scratch)
        self.assertTrue(done['ok'], done)
        return done

    def status(self):
        with self.opened() as project:
            return builds.status(project)

    def product(self, reference):
        with self.opened() as project:
            found = builds.products(project, reference)
        return found[0]

    def write_lines(self, name, rows):
        (self.folder / 'annotations' / f'{name}.jsonl').write_bytes(annotations.write(rows))

    def test_import_then_freeze_and_out_of_date_by_the_line_files(self):
        done = self.build('datasets/raw')
        run = done['steps'][0]
        with self.opened() as project:
            row = builds.run_details(project, run['run_id'])
        # Tuldok's interpreter and code; no environment; the snapshot's decoy never imported.
        self.assertEqual(row['argv'][:5], [sys.executable, '-m', 'tuldok_project.steps', 'import',
                                           os.path.join(row['directory'], 'settings.json')])
        self.assertIsNone(row['environment'])
        self.assertEqual((row['env']['PYTHONSAFEPATH'], row['env']['PYTHONPATH']), ('1', builds.TULDOK_ROOT))
        stderr = (Path(row['directory']) / 'stderr.log').read_text(encoding='utf-8')
        self.assertNotIn('snapshot', stderr)
        raw = self.product('datasets/raw')
        records = {record['id']: record for record in _records(raw['directory'])}
        self.assertEqual(sorted(records), [f'item-{number}.txt' for number in range(8)])
        event = (Path(row['directory']) / 'stdout.log').read_text(encoding='utf-8')
        self.assertIn('"stage":"import","completed":8,"total":8', event)

        ids = sorted(records)
        self.write_lines('quality', [_row(identifier, 'accepted', 'good', records[identifier]['sha256'])
                                     for identifier in ids[:6]] + [_row(ids[6], 'rejected', None)])
        self.write_lines('captions', [_row(ids[0], 'accepted', 'the first item', records[ids[0]]['sha256'])])
        self.write_lines('unrelated', [_row(ids[0], 'accepted', None)])
        self.commit('Annotations.')
        done = self.build('datasets/frozen')
        self.assertEqual([step['reference'] for step in done['steps']], ['datasets/frozen'])
        frozen_product = self.product('datasets/frozen')
        frozen = _records(frozen_product['directory'])
        self.assertEqual([record['split'] for record in frozen], ['test'] + ['train'] * 5)   # 6 cut 1:3
        self.assertEqual({record['id'] for record in frozen}, set(ids[:6]))
        first = next(record for record in frozen if record['id'] == ids[0])
        self.assertEqual(first['annotations'], {'quality': {'state': 'accepted', 'value': 'good'},
                                                'captions': {'state': 'accepted', 'value': 'the first item'}})
        with self.opened() as project:
            row = builds.run_details(project, frozen_product['run_id'])
            covered = build_requests.covers(project, plan.build_plan(project, ['datasets/frozen']),
                                            ['datasets/frozen'], every=False, scratch=False)
        quality = (self.folder / 'annotations' / 'quality.jsonl').read_bytes()
        self.assertEqual(row['annotations']['annotations/quality']['sha256'], _sha(quality))
        self.assertEqual(row['annotations']['annotations/quality']['file'], 'annotations/quality.jsonl')
        self.assertEqual(set(row['annotations']), {'annotations/quality', 'annotations/captions'})
        self.assertIn('annotations/quality', covered['definitions'])
        self.assertIn('annotations/captions', covered['definitions'])
        self.assertIsNone(row['environment'])
        self.assertEqual(self.status()['datasets/frozen']['state'], 'built')
        # The frozen product is read by spec-d1's readers, with its splits and annotations.
        listed = inside.records(inside.Product(frozen_product['run_id'], frozen_product['directory']), limit=200)
        self.assertEqual((listed['splits'], listed['problems']), ({'train': 5, 'test': 1}, []))
        self.assertEqual(next(record for record in listed['records'] if record['id'] == ids[0])['annotations'],
                         first['annotations'])

        # Another task's file changes: still built.
        self.write_lines('unrelated', [_row(ids[1], 'accepted', None)])
        self.commit('Another task.')
        self.assertEqual(self.status()['datasets/frozen']['state'], 'built')
        # One of its tasks' files changes but is not committed: the commit a build would use is unchanged.
        self.write_lines('quality', [_row(ids[0], 'rejected', None)])
        self.assertEqual(self.status()['datasets/frozen']['state'], 'built')
        self.commit('Fewer accepted.')
        entry = self.status()['datasets/frozen']
        self.assertEqual(entry['state'], 'out-of-date')
        self.assertEqual(entry['causes'], [f'the annotations of annotations/quality (annotations/quality.jsonl) changed '
                                           f'since run {frozen_product["run_id"][:12]}'])
        self.assertEqual(self.status()['datasets/raw']['state'], 'built')
        done = self.build('datasets/frozen')
        self.assertEqual(_records(self.product('datasets/frozen')['directory']), [])
        self.assertEqual(self.status()['datasets/frozen']['state'], 'built')
        # A file removed is a cause too.
        os.remove(self.folder / 'annotations' / 'captions.jsonl')
        self.commit('No captions.')
        self.assertIn('are gone since run', self.status()['datasets/frozen']['causes'][0])

    def test_the_source_changing_puts_an_import_out_of_date(self):
        self.build('datasets/raw')
        (self.root / 'code' / 'data' / 'item-0.txt').write_text('changed\n', encoding='utf-8')
        self.commit('A source file changed.')
        causes = self.status()['datasets/raw']['causes']
        self.assertEqual(len(causes), 1)
        self.assertTrue(causes[0].startswith('its source data changed since commit '), causes)
        self.assertTrue(causes[0].endswith(': data/item-0.txt'), causes)

    def test_a_scratch_freeze_reads_the_working_tree(self):
        self.build('datasets/raw')
        records = {record['id']: record for record in _records(self.product('datasets/raw')['directory'])}
        self.write_lines('quality', [_row(identifier, 'accepted', 'good', record['sha256'])
                                     for identifier, record in records.items()])
        self.build('datasets/frozen', scratch=True)
        self.assertEqual(len(_records(self.product('datasets/frozen')['directory'])), 8)
        self.assertEqual(self.status()['datasets/frozen']['state'], 'built')
        self.write_lines('quality', [_row('item-0.txt', 'accepted', 'bad', records['item-0.txt']['sha256'])])
        self.assertIn('annotations/quality', self.status()['datasets/frozen']['causes'][0])

    def test_a_step_is_cancelled_like_any_run(self):
        # The cancel file is written before the custodian first looks, while the step is still starting.
        for number in range(200):
            (self.root / 'code' / 'data' / f'bulk-{number:05}.txt').write_text(str(number), encoding='utf-8')
        self.commit('Many files.')
        with self.opened() as project:
            made = plan.build_plan(project, ['datasets/raw'])

        def on_event(kind, item):
            if kind == 'start':
                Path(item['directory'], 'cancel').touch()

        done = builds.execute(self.folder, made, confirm=lambda given: True, on_event=on_event)
        self.assertFalse(done['ok'])
        self.assertEqual(done['steps'][0]['state'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
