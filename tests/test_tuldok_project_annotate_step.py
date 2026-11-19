"""The step annotate and the annotation sets it makes: sections 3 and 4 of spec-t4.md (slice T4b).

Two stand-in segmentors (one script, code/segment.py, run with two
thresholds: a project's own command in a test environment connected to the
interpreter running the tests) annotate four small images (masks and
polygons) and two small point clouds (point objects) of a dataset built by
import, for real through builds.execute. Each set has the lines, sidecars and
annotator.json expected; a line naming a record the input lacks and a line
with a bad value are dropped and counted; a run that fails half way is
resumed by the next build, which annotates only the rest. The Pumas route
is asked of tests/fake_pumas_typed.py (as test_tuldok_project_pumas does):
boxes as a JSON list, an answer that is not one refused. No real Pumas, no
GPU. The database parts run only when TULDOK_DATABASE_URL names a disposable
cluster. The stand-ins and the test data are shared with
test_tuldok_project_annotation_agreement through make_project.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import (annotation_payloads as payloads, annotation_sets, builds, check, environments,  # noqa: E402
                            local, plan, steps, store)

DATABASE = os.environ.get('TULDOK_DATABASE_URL')
GIT = ['git', '-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false']
RIGHTS = 'Made for this test; anything may be done with it.'

# ------------------------------------------------------------ the test data

def png_rgb(width, height, pixel):
    """An RGB PNG whose pixel(x, y) gives (r, g, b); rows unfiltered."""
    rows = b''.join(b'\x00' + b''.join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def blobs(width, height, rectangles):
    """An image of dark rectangles (x, y, w, h, red or blue) with a softer one-pixel rim, on white."""
    def pixel(x, y):
        for bx, by, bw, bh, colour in rectangles:
            inside = bx <= x < bx + bw and by <= y < by + bh
            rim = bx - 1 <= x < bx + bw + 1 and by - 1 <= y < by + bh + 1
            dark = (40, 40, 200) if colour == 'blue' else (200, 40, 40)
            if inside:
                return dark
            if rim:
                return tuple((255 + value) // 2 for value in dark)   # the rim: lighter, where thresholds differ
        return (255, 255, 255)
    return png_rgb(width, height, pixel)


IMAGES = {
    'images/a.png': blobs(24, 16, [(2, 2, 6, 5, 'red'), (14, 6, 7, 7, 'blue')]),
    'images/b.png': blobs(24, 16, [(4, 4, 10, 8, 'red')]),
    'images/c.png': blobs(24, 16, [(1, 1, 4, 4, 'blue'), (10, 3, 5, 9, 'blue')]),
    'images/d.png': blobs(24, 16, []),
}


def cloud(count, top):
    """An ASCII PLY of count points on a line rising in z; the points above z = top are 'the top'."""
    lines = ['ply', 'format ascii 1.0', f'element vertex {count}', 'property float x', 'property float y',
             'property float z', 'end_header']
    lines += [f'{n * 0.1:.2f} {0.05 * (n % 3):.2f} {n / (count - 1):.3f}' for n in range(count)]
    return ('\n'.join(lines) + '\n').encode('ascii')


CLOUDS = {'clouds/p.ply': cloud(20, 0.5), 'clouds/q.ply': cloud(30, 0.5)}

# The stand-in segmentor: a project's own script. It reads the contract's variables and writes lines.
SEGMENT = r'''"""A stand-in segmentor for Tuldok's tests: dark pixels below a threshold, points above a height."""
import json, os, struct, sys, zlib

def read_png(path):
    data = open(path, 'rb').read()
    width, height = struct.unpack('>II', data[16:24])
    at, body = 8, b''
    while at < len(data):
        length, kind = struct.unpack('>I4s', data[at:at + 8])
        if kind == b'IDAT':
            body += data[at + 8:at + 8 + length]
        at += 12 + length
    raw = zlib.decompress(body)
    rows = [raw[y * (width * 3 + 1) + 1:(y + 1) * (width * 3 + 1)] for y in range(height)]
    return width, height, [[tuple(row[x * 3:x * 3 + 3]) for x in range(width)] for row in rows]

def write_png(path, width, values):
    rows = b''.join(b'\x00' + bytes(values[y * width:(y + 1) * width]) for y in range(len(values) // width))
    part = lambda kind, body: struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    with open(path, 'wb') as out:
        out.write(b'\x89PNG\r\n\x1a\n' + part(b'IHDR', struct.pack('>IIBBBBB', width, len(values) // width, 8, 0, 0, 0, 0))
                  + part(b'IDAT', zlib.compress(rows)) + part(b'IEND', b''))

threshold = float(sys.argv[1])
options = json.loads(os.environ['TULDOK_ANNOTATE_OPTIONS'])
task = json.load(open(os.environ['TULDOK_TASK']))
todo = [json.loads(line) for line in open(os.environ['TULDOK_TODO'])]
marker = options.get('fail_once')
failing = marker is not None and not os.path.exists(marker)
if marker is not None and not failing:
    open(marker + '.todo', 'w').write(json.dumps([r['id'] for r in todo]))
out = open(os.environ['TULDOK_ANNOTATIONS'], 'a')
for number, record in enumerate(todo):
    if failing and number == 1:
        open(marker, 'w').write('failed once')
        sys.exit(4)
    value = None
    if record['kind'] == 'image':
        width, height, pixels = read_png(record['path'])
        ids, found = [0] * (width * height), {}
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[y][x]
                if (r + g + b) / 3 < threshold:
                    colour = 'blue' if b > r else 'red'
                    ids[y * width + x] = found.setdefault(colour, len(found) + 1)
        if task['task'] == 'mask':
            name = record['id'] + '.png'
            write_png(os.path.join(os.environ['TULDOK_FILES'], name), width, ids)
            value = {'file': name, 'classes': {str(n): 'blob' for n in found.values()} or {'1': 'blob'},
                     'confidence': 0.9}
        else:
            value = []
            for colour, n in sorted(found.items()):
                xs = [i % width for i, v in enumerate(ids) if v == n]
                ys = [i // width for i, v in enumerate(ids) if v == n]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
                value.append({'term': colour, 'points': [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                              'confidence': round(1 - n / 10, 2)})
    else:
        rows = open(record['path']).read().split('end_header\n')[1].split('\n')
        zs = [float(row.split()[2]) for row in rows if row.strip()]
        value = [{'term': 'top', 'indices': [i for i, z in enumerate(zs) if z > threshold / 255]}]
    out.write(json.dumps({'record': record['id'], 'value': value}) + '\n')
    out.flush()
    print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'segment', 'completed': number + 1,
                      'total': len(todo), 'metrics': {}}), flush=True)
if options.get('noise'):
    out.write(json.dumps({'record': 'nobody', 'value': []}) + '\n')
    out.write(json.dumps({'record': todo[0]['id'], 'value': 'not a value'}) + '\n') if todo else None
    out.write('not json\n')
'''


def task(dataset, kind, vocabulary=None, **fields):
    document = {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': f'A {kind} task',
                'dataset': dataset, 'task': kind}
    if vocabulary is not None:
        document['vocabulary'] = vocabulary
    document.update(fields)
    return document


def annotator(task_reference, threshold, name, input_dataset='datasets/raw', **settings):
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': f'{name} on {task_reference}',
            'run': {'step': 'annotate', 'inputs': {'records': input_dataset}, 'annotations': [task_reference],
                    'command': ['python', 'segment.py', str(threshold)], 'environment': 'environments/test-python',
                    'settings': {'by': {'kind': 'script', 'name': name, 'version': '1'}, **settings}}}


DEFINITIONS = {
    'datasets/raw': {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Images and clouds',
                     'run': {'step': 'import', 'settings': {'source': 'data', 'rights': RIGHTS}}},
    'annotations/masks': task('datasets/raw', 'mask', ['blob'], mask='instance'),
    'annotations/shapes': task('datasets/raw', 'polygons', ['red', 'blue']),
    'annotations/objects': task('datasets/raw', 'points', ['top']),
    'datasets/masks-a': annotator('annotations/masks', 160, 'segment-a'),
    'datasets/masks-b': annotator('annotations/masks', 200, 'segment-b'),
    'datasets/shapes-a': annotator('annotations/shapes', 160, 'segment-a', options={'noise': True}),
    'datasets/shapes-b': annotator('annotations/shapes', 200, 'segment-b'),
    'datasets/objects-a': annotator('annotations/objects', 128, 'segment-a'),
    'datasets/objects-b': annotator('annotations/objects', 140, 'segment-b'),
    'environments/test-python': {'format': 'tuldok_definition_v1', 'kind': 'environment',
                                 'title': 'The interpreter running the tests', 'python': '3.12', 'device': 'cpu',
                                 'packages': {'jsonschema': '4.26.0'}},
}


def make_project(root, project_id, extra=None):
    """root/project and root/code: the definitions, the stand-in and the images and clouds."""
    folder, code = root / 'project', root / 'code'
    for directory in ('datasets', 'annotations', 'environments'):
        (folder / directory).mkdir(parents=True, exist_ok=True)
    (folder / 'tuldok.json').write_text(json.dumps({'format': 'tuldok_project_v1', 'id': project_id,
                                                    'name': 'Annotators test project', 'code_root': '../code'},
                                                   indent=2) + '\n', encoding='utf-8')
    for reference, document in {**DEFINITIONS, **(extra or {})}.items():
        (folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    for name, data in {**IMAGES, **CLOUDS}.items():
        path = code / 'data' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (code / 'segment.py').write_text(SEGMENT, encoding='utf-8')
    return folder


def _writable(root):
    for current, directories, _files in os.walk(root):
        for name in directories:
            os.chmod(os.path.join(current, name), 0o755)


class Checked(unittest.TestCase):
    """check on an annotate's run (spec-t4.md section 4), with no database."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = make_project(Path(directory.name), uuid.uuid4().hex)

    def write(self, reference, document):
        (self.folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def problems(self, reference):
        return {(p.pointer, p.severity) for p in check.check_folder(self.folder).problems
                if p.path == f'{reference}.json'}

    def test_the_stand_ins_check(self):
        self.assertEqual([p for p in check.check_folder(self.folder).problems if p.severity == 'error'], [])

    def test_each_rule(self):
        document = annotator('annotations/masks', 1, 'x')
        document['run']['settings']['pumas'] = {'model': 'm'}
        self.write('datasets/masks-a', document)
        self.assertIn(('/run', 'error'), self.problems('datasets/masks-a'))
        document = annotator('annotations/masks', 1, 'x', limit=0)
        document['run']['settings']['by'] = {'kind': 'robot', 'name': ''}
        document['run']['annotations'] = ['annotations/masks', 'annotations/shapes']
        self.write('datasets/masks-a', document)
        found = self.problems('datasets/masks-a')
        for pointer in ('/run/settings/by', '/run/settings/limit', '/run/annotations'):
            self.assertIn((pointer, 'error'), found)
        document = annotator('annotations/masks', 1, 'x', input_dataset='datasets/masks-b')
        self.write('datasets/masks-a', document)
        self.assertIn(('/run/annotations/0', 'error'), self.problems('datasets/masks-a'))
        # import, freeze and generate still take no command or environment
        document = dict(DEFINITIONS['datasets/raw'])
        document['run'] = dict(document['run'], environment='environments/test-python')
        self.write('datasets/raw', document)
        self.assertIn(('/run/environment', 'error'), self.problems('datasets/raw'))


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Built(unittest.TestCase):
    """The stand-ins run for real by builds.execute."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.root = self.temporary / 'repository'
        self.root.mkdir()
        self.home = self.temporary / 'home'
        self.addCleanup(_writable, self.home)
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.home),
                                               local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project_id = uuid.uuid4().hex
        self.marker = self.temporary / 'failed-once'
        extra = {'datasets/resumed': annotator('annotations/objects', 128, 'segment-r',
                                               options={'fail_once': str(self.marker)})}
        self.folder = make_project(self.root, self.project_id, extra)
        subprocess.run([*GIT, '-C', str(self.root), 'init', '-q'], check=True)
        subprocess.run([*GIT, '-C', str(self.root), 'add', '-A'], check=True)
        subprocess.run([*GIT, '-C', str(self.root), 'commit', '-q', '-m', 'The project.'], check=True)
        self.addCleanup(store.drop_project, self.project_id)
        with store.open_project(self.folder) as project:
            self.assertTrue(environments.connect(project, 'environments/test-python', sys.executable)['ok'])

    def build(self, *targets, ok=True):
        with store.open_project(self.folder) as project:
            made = plan.build_plan(project, list(targets))
        done = builds.execute(self.folder, made, confirm=lambda given: True)
        self.assertEqual(done['ok'], ok, done)
        return done

    def product(self, reference):
        with store.open_project(self.folder) as project:
            return builds.products(project, reference)[0]['directory']

    def test_two_segmentors_make_two_sets(self):
        self.build('datasets/masks-a', 'datasets/masks-b', 'datasets/shapes-a', 'datasets/shapes-b',
                   'datasets/objects-a', 'datasets/objects-b')
        tasks = {'masks': DEFINITIONS['annotations/masks'], 'shapes': DEFINITIONS['annotations/shapes'],
                 'objects': DEFINITIONS['annotations/objects']}
        sets = {}
        for name in ('masks-a', 'masks-b', 'shapes-a', 'shapes-b', 'objects-a', 'objects-b'):
            directory = self.product(f'datasets/{name}')
            sets[name] = annotation_sets.read_set(directory, tasks[name.split('-')[0]])
            sets[name]['directory'] = directory
        self.assertEqual(sorted(sets['masks-a']['records']), ['images__a.png', 'images__b.png', 'images__c.png',
                                                              'images__d.png'])
        self.assertEqual(sorted(sets['objects-a']['records']), ['clouds__p.ply', 'clouds__q.ply'])
        annotator_file = json.loads(Path(sets['masks-a']['directory'], 'annotator.json').read_text())
        self.assertEqual(annotator_file['format'], 'tuldok_annotator_v1')
        self.assertEqual(annotator_file['task'], 'annotations/masks')
        self.assertEqual(annotator_file['by'], {'kind': 'script', 'name': 'segment-a', 'version': '1',
                                                'settings': {}})
        self.assertEqual((annotator_file['records'], annotator_file['made']), (6, 4))
        # The masks: the rim is dark enough for b (200) and not for a (160), so b's objects are one pixel wider.
        line = sets['masks-a']['records']['images__a.png']
        self.assertEqual(line['value']['classes'], {'1': 'blob', '2': 'blob'})
        self.assertEqual(line['confidence'] if 'confidence' in line else line['value']['confidence'], 0.9)
        a = payloads.read_png(annotation_sets.sidecar(sets['masks-a']['directory'], line['value']['file']))[2]
        b = payloads.read_png(annotation_sets.sidecar(sets['masks-b']['directory'],
                                                      sets['masks-b']['records']['images__a.png']['value']['file']))[2]
        self.assertEqual((sum(1 for v in a if v == 1), sum(1 for v in a if v == 2)), (30, 49))
        self.assertEqual((sum(1 for v in b if v == 1), sum(1 for v in b if v == 2)), (56, 81))
        # The point objects: points above 128/255 and 140/255 of the height.
        self.assertEqual(sets['objects-a']['records']['clouds__p.ply']['value'],
                         [{'term': 'top', 'indices': list(range(10, 20))}])
        self.assertEqual(sets['objects-b']['records']['clouds__p.ply']['value'],
                         [{'term': 'top', 'indices': list(range(11, 20))}])
        # The noise of shapes-a: an unknown record, a bad value and a line that is not JSON, all dropped.
        self.assertEqual(sorted(sets['shapes-a']['records']), sorted(sets['shapes-b']['records']))
        log = self.run_log('datasets/shapes-a')
        for words in ('lines the annotator wrote are not JSON', 'name a record the input does not have',
                      'hold a value the task does not allow'):
            self.assertIn(words, log)
        lines = Path(sets['shapes-a']['directory'], 'annotations.jsonl').read_text().splitlines()
        self.assertEqual([json.loads(line)['record'] for line in lines], sorted(json.loads(line)['record']
                                                                                for line in lines))
        self.assertTrue(lines[0].startswith('{"record":"images__a.png","sha256":"'))
        self.assertIn('"value":[{"term":"blue","points":[[14,6],[21,6],[21,13],[14,13]],"confidence":0.8}', lines[0])

    def run_log(self, reference):
        with store.open_project(self.folder) as project:
            run = builds.products(project, reference)[0]['run_id']
            directory = project._execute('SELECT directory FROM {schema}.runs WHERE id = %s', (run,)).fetchone()[0]
        return ''.join(path.read_text(errors='replace') for path in Path(directory).glob('*.log'))

    def test_a_failed_run_is_resumed(self):
        done = self.build('datasets/resumed', ok=False)
        self.assertEqual(done['steps'][-1]['state'], 'failed')
        self.assertTrue(self.marker.exists())
        self.build('datasets/resumed')
        given = json.loads(Path(str(self.marker) + '.todo').read_text())
        self.assertEqual(given, ['clouds__q.ply'])   # p was annotated before the first run failed
        found = annotation_sets.read_set(self.product('datasets/resumed'), DEFINITIONS['annotations/objects'])
        self.assertEqual(sorted(found['records']), ['clouds__p.ply', 'clouds__q.ply'])


class Pumas(unittest.TestCase):
    """The Pumas route of annotate, as a function on directories, against the fake endpoint."""

    def setUp(self):
        import fake_pumas_typed
        from test_tuldok_project_pumas import listing
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.server, self.base, self.fake = fake_pumas_typed.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.fake['served_models'] = listing()
        records = self.root / 'records'
        (records / 'files').mkdir(parents=True)
        lines = []
        for name, data in IMAGES.items():
            identifier = name.replace('/', '__')
            (records / 'files' / identifier).write_bytes(data)
            lines.append({'id': identifier, 'kind': 'image', 'path': f'files/{identifier}'})
        (records / 'records.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in lines))
        self.records = records

    def annotate(self, answers, kind='boxes', vocabulary=('red', 'blue')):
        answers = list(answers)
        self.fake['respond'] = lambda body: {'kind': 'text', 'text': answers.pop(0), 'finish_reason': 'stop'}
        output = self.root / f'output-{len(list(self.root.iterdir()))}'
        output.mkdir()
        said = []
        counts = steps.annotate_records(
            {'by': {'kind': 'model', 'name': 'vision'}, 'pumas': {'model': 'controlled-vision',
                                                                  'profile': 'vision-cpu'}},
            str(output), records=str(self.records),
            task={'reference': 'annotations/boxes', 'document': task('datasets/raw', kind, list(vocabulary))},
            run_directory=str(self.root), endpoint=self.base, out=said.append)
        return counts, output, said

    def test_boxes_asked_as_json(self):
        answer = '```json\n[{"term": "red", "x": 2, "y": 2, "w": 6, "h": 5}]\n```'
        counts, output, said = self.annotate([answer, '[]', 'I see two blue squares.',
                                              '[{"term": "green", "x": 0, "y": 0, "w": 1, "h": 1}]'])
        self.assertEqual((counts['kept'], counts['refused']), (2, 2))
        lines = [json.loads(line) for line in (output / 'annotations.jsonl').read_text().splitlines()]
        self.assertEqual([(line['record'], line['value']) for line in lines],
                         [('images__a.png', [{'term': 'red', 'x': 2, 'y': 2, 'w': 6, 'h': 5}]),
                          ('images__b.png', [])])
        by = json.loads((output / 'annotator.json').read_text())['by']
        self.assertEqual(by['model'], {'model': 'controlled-vision', 'profile': 'vision-cpu',
                                       'capability': 'image_to_text'})
        asked = self.fake['requests'][-4]
        self.assertEqual(asked['capability'], 'image_to_text')
        self.assertIn('of 24 by 16 pixels', json.dumps(asked))
        self.assertTrue(any('not a JSON list of regions' in line for line in said))

    def test_every_one_of_the_first_refused_fails(self):
        with self.assertRaises(steps.StepError):
            self.annotate(['no'] * 4)


if __name__ == '__main__':
    unittest.main()
