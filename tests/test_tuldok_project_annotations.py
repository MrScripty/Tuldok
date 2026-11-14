"""Annotation tasks and their line files: sections 1 and 2 of spec-d4.md (slice D4a).

A task of each kind checks; each rule of the task and of a line, broken once,
gives its problem at its line; a file written from the rows it was read into
is the same bytes; lines are ordered and escaped as section 2 says; a line
file without its task is an error; a fresh open of a folder with a task lists
it and its edge; planning a task plans its dataset. Each test works on a copy
of tests/fixtures/tuldok_project/minimal, whose annotations/wave-quality is a
class task on datasets/waves.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import annotations, plan, store  # noqa: E402
from tuldok_project.check import check_folder  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')
TASK = 'annotations/wave-quality'
AT = '2026-11-13T10:02:11Z'
SHA = '9f' * 32

# One sound value per task, and the vocabulary each task's definition carries.
VALUES = {
    'review': None,
    'class': 'cat',
    'tags': ['indoor', 'night'],
    'text': 'a dog on a sofa',
    'boxes': [{'term': 'cat', 'x': 10, 'y': 4, 'w': 80, 'h': 60}],
    'spans': [{'term': 'cat', 'start': 0, 'end': 5}],
    'segments': [{'term': 'speech', 'start': 1.25, 'end': 3.5, 'text': 'hello'}],
}
VOCABULARY = ['cat', 'indoor', 'night', 'speech']


def line(record='a1', **fields):
    row = {'record': record, 'sha256': SHA, 'state': 'accepted', 'value': 'cat', 'by': 'owner', 'at': AT}
    row.update(fields)
    return annotations.encode(row)


class FolderCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name) / 'minimal'
        shutil.copytree(FIXTURE, self.base)
        self.folder = self.base / 'project'

    def task(self, name='wave-quality', **fields):
        document = {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': 'T',
                    'dataset': 'datasets/waves', 'task': 'class', 'vocabulary': VOCABULARY}
        document.update(fields)
        document = {key: value for key, value in document.items() if value is not None}
        (self.folder / f'annotations/{name}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def lines(self, *texts, name='wave-quality', raw=None):
        data = raw if raw is not None else ''.join(text + '\n' for text in texts).encode('utf-8')
        (self.folder / f'annotations/{name}.jsonl').write_bytes(data)

    def problems(self):
        return [(p.severity, p.path, p.pointer) for p in check_folder(self.folder).problems]

    def assertOnly(self, expected):
        report = check_folder(self.folder)
        listing = '\n'.join(f'  {p.severity} {p.path} {p.pointer!r} {p.message}' for p in report.problems)
        self.assertEqual([(p.severity, p.path, p.pointer) for p in report.problems], [expected], listing)
        message = report.problems[0].message
        self.assertTrue(message.endswith('.'), message)
        self.assertNotIn('label', message.lower())
        return message


class Tasks(FolderCase):
    def test_the_fixture_task_checks(self):
        self.assertEqual(self.problems(), [])

    def test_a_task_of_each_kind_checks(self):
        for task, value in VALUES.items():
            with self.subTest(task=task):
                vocabulary = VOCABULARY if task in annotations.VOCABULARY_TASKS else None
                self.task(task=task, vocabulary=vocabulary)
                self.lines(line(value=value), line('a2', state='draft', value=None, by='agent:helper',
                                                    note='first pass', **{'from': {'model': 'm'}}))
                self.assertEqual(self.problems(), [])

    def test_each_rule_of_a_task(self):
        cases = [
            ('no dataset', {'dataset': None}, '/dataset'),
            ('dataset in another directory', {'dataset': 'recipes/stepper-k1'}, '/dataset'),
            ('dataset missing', {'dataset': 'datasets/nowhere'}, '/dataset'),
            ('unknown task', {'task': 'polygons'}, '/task'),
            ('class needs a vocabulary', {'vocabulary': None}, '/vocabulary'),
            ('review takes none', {'task': 'review'}, '/vocabulary'),
            ('text takes none', {'task': 'text'}, '/vocabulary'),
            ('empty vocabulary', {'vocabulary': []}, '/vocabulary'),
            ('repeated term', {'vocabulary': ['cat', 'cat']}, '/vocabulary'),
            ('term too long', {'vocabulary': ['x' * 201]}, '/vocabulary/0'),
            ('empty term', {'vocabulary': ['']}, '/vocabulary/0'),
            ('control character in a term', {'vocabulary': ['a\nb']}, '/vocabulary/0'),
            ('too many terms', {'vocabulary': [f't{i}' for i in range(501)]}, '/vocabulary'),
            ('no run', {'run': {'command': ['true']}}, '/run'),
            ('no earlier_work', {'earlier_work': {'rebuild': 'yes'}}, '/earlier_work'),
        ]
        self.lines()  # no line file problems in the way: an empty file is a warning, removed below
        os.remove(self.folder / 'annotations/wave-quality.jsonl')
        for name, fields, pointer in cases:
            with self.subTest(name):
                self.task(**{'task': 'class', 'vocabulary': VOCABULARY, 'dataset': 'datasets/waves', **fields})
                self.assertOnly(('error', 'annotations/wave-quality.json', pointer))

    def test_a_line_file_without_its_task(self):
        self.lines(line(), name='orphan')
        message = self.assertOnly(('error', 'annotations/orphan.jsonl', ''))
        self.assertIn('annotations/orphan.json', message)

    def test_other_files_are_refused_in_annotations(self):
        (self.folder / 'annotations/notes.txt').write_text('x')
        self.assertOnly(('error', 'annotations/notes.txt', ''))

    def test_line_files_belong_to_annotations_only(self):
        (self.folder / 'datasets/waves.jsonl').write_text(line() + '\n')
        self.assertOnly(('error', 'datasets/waves.jsonl', ''))

    def test_a_task_with_errors_leaves_its_lines_unchecked(self):
        self.task(task='polygons')
        self.lines('not json')
        self.assertEqual(self.problems(), [('error', 'annotations/wave-quality.json', '/task'),
                                           ('warning', 'annotations/wave-quality.jsonl', '')])


class Lines(FolderCase):
    """Each rule of section 2 broken once, as line 2 after a sound line 1."""

    def broken(self, text, severity='error', pointer='line 2', task='class', vocabulary=VOCABULARY):
        self.task(task=task, vocabulary=vocabulary)
        self.lines(line('a0', value=VALUES[task]), text)
        return self.assertOnly((severity, 'annotations/wave-quality.jsonl', pointer))

    def test_each_rule_of_a_line(self):
        long_record = 'r' * 601
        cases = [
            ('not JSON', '{"record":', {}),
            ('not an object', '["a1"]', {}),
            ('a key twice', '{"record":"a1","record":"a2"}', {}),
            ('NaN', line()[:-1] + ',"from":{"x":NaN}}', {}),
            ('unknown key', line()[:-1] + ',"extra":1}', {}),
            ('missing key', line().replace(',"sha256":"' + SHA + '"', ''), {}),
            ('record too long', line(long_record), {}),
            ('record with a control character', line('a\x01'), {}),
            ('record empty', line(''), {}),
            ('sha256 malformed', line(sha256='ABC'), {}),
            ('state unknown', line(state='done'), {}),
            ('accepted without a value', line(value=None), {}),
            ('review with a value', line(value='cat'), {'task': 'review', 'vocabulary': None}),
            ('class value not a string', line(value=['cat']), {}),
            ('tags repeated', line(value=['indoor', 'indoor']), {'task': 'tags'}),
            ('tags not a list', line(value='indoor'), {'task': 'tags'}),
            ('text too long', line(value='x' * (64 * 1024 + 1)), {'task': 'text', 'vocabulary': None}),
            ('box with no width', line(value=[{'term': 'cat', 'x': 0, 'y': 0, 'w': 0, 'h': 5}]), {'task': 'boxes'}),
            ('box left of the image', line(value=[{'term': 'cat', 'x': -1, 'y': 0, 'w': 2, 'h': 5}]), {'task': 'boxes'}),
            ('box missing h', line(value=[{'term': 'cat', 'x': 0, 'y': 0, 'w': 2}]), {'task': 'boxes'}),
            ('span backwards', line(value=[{'term': 'cat', 'start': 5, 'end': 5}]), {'task': 'spans'}),
            ('span in fractions', line(value=[{'term': 'cat', 'start': 0.5, 'end': 5}]), {'task': 'spans'}),
            ('span with text', line(value=[{'term': 'cat', 'start': 0, 'end': 5, 'text': 'x'}]), {'task': 'spans'}),
            ('segment backwards', line(value=[{'term': 'speech', 'start': 2, 'end': 1}]), {'task': 'segments'}),
            ('segment text not a string', line(value=[{'term': 'speech', 'start': 0, 'end': 1, 'text': 3}]),
             {'task': 'segments'}),
            ('note too long', line(note='n' * 4001), {}),
            ('note null', line()[:-1] + ',"note":null}', {}),
            ('by an id', line(by='credential-1234'), {}),
            ('by an agent with no label', line(by='agent:'), {}),
            ('by an agent label too long', line(by='agent:' + 'x' * 81), {}),
            ('at not a real time', line(at='2026-02-30T10:00:00Z'), {}),
            ('at not UTC', line(at='2026-11-13T10:02:11+01:00'), {}),
            ('from not an object', line(**{'from': 'model'}), {}),
            ('from too large', line(**{'from': {'x': 'y' * 2048}}), {}),
            ('a lone surrogate', line(note='x').replace('"x"', '"\\ud800"'), {}),
            ('duplicate record', line('a0'), {}),
            ('out of order', line('A'), {}),
        ]
        for name, text, task in cases:
            with self.subTest(name):
                self.broken(text, **task)

    def test_warnings(self):
        cases = [
            ('a term not in the vocabulary', line(value='dog'), 'line 2'),
            ('a blank line', '', 'line 2'),
            ('another form', line().replace(',', ', ', 1), 'line 2'),
            ('keys in another order', '{"sha256":"' + SHA + '","record":"a1","state":"accepted","value":"cat",'
                                      '"by":"owner","at":"' + AT + '"}', 'line 2'),
            ('ASCII escapes', line(note='é').replace('é', '\\u00e9'), 'line 2'),
        ]
        for name, text, pointer in cases:
            with self.subTest(name):
                self.broken(text, 'warning', pointer)

    def test_a_term_removed_from_the_vocabulary_counts_its_uses(self):
        self.task(vocabulary=['cat', 'noisy'])
        self.lines(line('a1', value='dog'), line('a2'), line('a3', value='dog'))
        message = self.assertOnly(('warning', 'annotations/wave-quality.jsonl', 'line 1'))
        self.assertIn("'dog'", message)
        self.assertIn('2 annotations use it (lines 1, 3)', message)

    def test_the_file_as_a_whole(self):
        self.task()
        self.lines(raw=line().encode('utf-8'))
        self.assertOnly(('warning', 'annotations/wave-quality.jsonl', 'line 1'))   # no final line end
        self.lines(raw=b'')
        self.assertOnly(('warning', 'annotations/wave-quality.jsonl', ''))         # no line at all
        self.lines(raw=b'\xff\n')
        self.assertOnly(('error', 'annotations/wave-quality.jsonl', ''))           # not UTF-8

    def test_the_first_twenty_then_a_count(self):
        self.task()
        self.lines(*[line(f'a{i:02}', state='done') for i in range(25)])
        report = check_folder(self.folder)
        pointers = [p.pointer for p in report.problems]
        self.assertEqual(len(pointers), 21)
        self.assertEqual(sorted(pointers[1:], key=lambda p: int(p.split()[1])),
                         [f'line {n}' for n in range(1, 21)])
        self.assertEqual(report.problems[0].pointer, '')
        self.assertIn('5 more problems', report.problems[0].message)


class Writing(unittest.TestCase):
    def test_a_well_formed_file_is_written_back_byte_for_byte(self):
        raw = ''.join(text + '\n' for text in [
            '{"record":"a1","sha256":"' + SHA + '","state":"rejected","value":null,"note":"blurry","by":"owner","at":"' + AT + '"}',
            '{"record":"a2","sha256":null,"state":"accepted","value":"cat","by":"owner","at":"' + AT + '"}',
            '{"record":"a3","sha256":null,"state":"accepted","value":["indoor","night"],"by":"owner","at":"' + AT + '"}',
            '{"record":"a4","sha256":null,"state":"draft","value":"un chien \\"Rex\\"\\n sur le canapé ✓","by":"agent:helper","at":"' + AT + '","from":{"model":"m","score":0.5}}',
            '{"record":"a5","sha256":null,"state":"accepted","value":[{"term":"cat","x":10,"y":4.5,"w":80,"h":60}],"by":"owner","at":"' + AT + '"}',
            '{"record":"a6","sha256":null,"state":"accepted","value":[{"term":"cat","start":0,"end":5}],"by":"owner","at":"' + AT + '"}',
            '{"record":"a7","sha256":null,"state":"accepted","value":[{"term":"speech","start":1.25,"end":3.5,"text":"hello"}],"by":"owner","at":"' + AT + '"}',
        ]).encode('utf-8')
        for task in annotations.TASKS:
            parsed = annotations.read(raw, task, VOCABULARY)
            self.assertEqual(len(parsed.rows), 7)
            self.assertEqual(annotations.write(row for _, row in parsed.rows), raw)

    def test_order_and_escaping(self):
        rows = [{'record': record, 'sha256': None, 'state': 'draft', 'value': None, 'by': 'owner', 'at': AT,
                 'note': 'tab\there "quoted" \\ é   😀'}
                for record in ('é', 'b', '😀', 'Z', 'a', '￿', 'a b')]
        rows[0]['from'] = None   # absent
        data = annotations.write(rows)
        lines = data.decode('utf-8').split('\n')
        self.assertEqual(lines[-1], '')
        records = [json.loads(text)['record'] for text in lines[:-1]]
        self.assertEqual(records, ['Z', 'a', 'a b', 'b', 'é', '￿', '😀'])
        self.assertEqual([record.encode('utf-8') for record in records],
                         sorted(record.encode('utf-8') for record in records))
        first = lines[0]
        self.assertTrue(first.startswith('{"record":"Z","sha256":null,"state":"draft","value":null,"note":'))
        self.assertTrue(first.endswith(',"by":"owner","at":"' + AT + '"}'))
        self.assertIn('"tab\\there \\"quoted\\" \\\\ é   😀"', first)
        self.assertNotIn('"from"', data.decode('utf-8'))
        self.assertNotIn(', ', first.split('"note"')[0])
        self.assertEqual(annotations.write([]), b'')
        parsed = annotations.read(data, 'review', [])
        self.assertEqual(parsed.problems, [])

    def test_an_item_is_written_in_its_key_order(self):
        row = {'at': AT, 'by': 'owner', 'value': [{'h': 2, 'w': 3, 'term': 'cat', 'y': 1, 'x': 0}],
               'state': 'accepted', 'sha256': None, 'record': 'r'}
        self.assertEqual(annotations.encode(row),
                         '{"record":"r","sha256":null,"state":"accepted",'
                         '"value":[{"term":"cat","x":0,"y":1,"w":3,"h":2}],"by":"owner","at":"' + AT + '"}')


class Records(unittest.TestCase):
    """What only the record can tell: its kind, an image's size, a text's length, a sound's length."""

    def errors(self, task, value, **record):
        row = {'record': 'r', 'sha256': None, 'state': 'accepted', 'value': value, 'by': 'owner', 'at': AT}
        return annotations.validate(task, VOCABULARY, row, **record)

    def test_kinds(self):
        self.assertEqual(annotations.record_kinds('boxes'), ('image',))
        self.assertEqual(annotations.record_kinds('spans'), ('text',))
        self.assertEqual(annotations.record_kinds('segments'), ('audio',))
        for task in ('review', 'class', 'tags', 'text'):
            self.assertNotIn('file', annotations.record_kinds(task))
            self.assertIn('mesh', annotations.record_kinds(task))
        self.assertEqual(self.errors('class', 'cat', kind='image'), [])
        self.assertEqual(len(self.errors('class', 'cat', kind='file')), 1)
        self.assertEqual(len(self.errors('boxes', VALUES['boxes'], kind='text')), 1)

    def test_bounds(self):
        self.assertEqual(self.errors('boxes', VALUES['boxes'], kind='image', size=(90, 64)), [])
        self.assertEqual(len(self.errors('boxes', VALUES['boxes'], kind='image', size=(89, 64))), 1)
        self.assertEqual(self.errors('spans', VALUES['spans'], kind='text', length=5), [])
        self.assertEqual(len(self.errors('spans', VALUES['spans'], kind='text', length=4)), 1)
        self.assertEqual(self.errors('segments', VALUES['segments'], kind='audio', duration=3.5), [])
        self.assertEqual(len(self.errors('segments', VALUES['segments'], kind='audio', duration=3.4)), 1)

    def test_a_term_outside_the_vocabulary_is_an_error_for_an_edit(self):
        self.assertEqual(len(self.errors('class', 'dog')), 1)
        self.assertEqual(annotations.value_problems('tags', VOCABULARY, 'accepted', ['dog', 'cat', 'ant']),
                         ([], ['ant', 'dog']))


class Planning(FolderCase):
    def test_planning_a_task_plans_its_dataset(self):
        report = check_folder(self.folder)
        definitions = {reference: d.document for reference, d in report.definitions.items()}
        result = plan.make_plan(definitions, [TASK])
        self.assertEqual(result['targets'], ['datasets/waves'])
        self.assertIn(f'{TASK} annotates the records of datasets/waves, which is planned in its place.',
                      result['notes'])
        self.assertNotIn('annotation', {step['kind'] for step in result['steps']})
        self.assertEqual(result['steps'][-1]['reference'], 'datasets/waves')
        everything = plan.make_plan(definitions, [], every=True)
        self.assertNotIn(TASK, [step['reference'] for step in everything['steps']])


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Opening(FolderCase):
    def setUp(self):
        super().setUp()
        self.project_id = uuid.uuid4().hex
        project_file = self.folder / 'tuldok.json'
        document = json.loads(project_file.read_text(encoding='utf-8'))
        document['id'] = self.project_id
        project_file.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.addCleanup(store.drop_project, self.project_id)

    def open(self):
        project = store.open_project(self.folder)
        self.addCleanup(project.close)
        return project

    def test_a_fresh_open_lists_the_task_and_its_edge(self):
        project = self.open()
        rows = project.definitions(kind='annotation')
        self.assertEqual([(row['reference'], row['state']) for row in rows], [(TASK, 'none')])
        self.assertIn({'from': TASK, 'to': 'datasets/waves', 'role': 'dataset'}, project.graph()['edges'])
        self.assertIn({'reference': TASK, 'role': 'dataset'}, project.definition('datasets/waves')['used_by'])
        status = project.status()
        self.assertEqual((status['irregular'], status['added'], status['changed']), ([], [], []))
        project.close()
        self.assertEqual(self.open().definitions(kind='annotation')[0]['reference'], TASK)  # the quick second open

    def test_a_line_file_without_its_task_stops_the_open(self):
        self.lines(line(), name='orphan')
        with self.assertRaises(store.ProjectError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertIn('annotations/orphan.jsonl', [p.path for p in caught.exception.problems])

    def test_a_bad_line_stops_the_open(self):
        self.lines(line('a1'), line('a0'))
        with self.assertRaises(store.ProjectError) as caught:
            self.open()
        self.assertIn(('annotations/wave-quality.jsonl', 'line 2'),
                      [(p.path, p.pointer) for p in caught.exception.problems])


if __name__ == '__main__':
    unittest.main()
