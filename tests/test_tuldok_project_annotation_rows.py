"""The working copy of annotations and the five operations: sections 3 to 5 of spec-d4.md (slice D4b).

Each test starts from test_tuldok_project_inside.ProductCase (a Git-committed
copy of the buildable fixture with an adopted product for datasets/numbers),
writes a record list and its files into that product, adds four tasks on
datasets/numbers (a class, a boxes, a spans and a segments task) and serves
the folder with a Service. Annotations are set, counted, saved, reverted,
changed on disk and found stale through the service's operations, as the page
and an agent would. Run only when TULDOK_DATABASE_URL names a disposable
cluster. No GPU is used.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import adoption, annotation_records, annotations, inside, service, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
import test_tuldok_project_inside as inside_base  # noqa: E402

OWNER = inside_base.OWNER
AT = '2026-11-13T10:02:11Z'
TASK = 'annotations/scenes'
LINES = 'annotations/scenes.jsonl'
# The time bounds of the test with 100,000 annotations, in seconds. Measured when it was written: set (500 calls of
# 200) 33 s, count 0.24 s, save 2.2 s, open again 0.02 s, a fresh import of the saved file 4.7 s; each bound is
# several times that, so that a slower machine passes and a change of order (a file rendered on every call, a
# query per row) does not.
BOUNDS = {'set': 120.0, 'count': 2.0, 'save': 10.0, 'reopen': 2.0, 'import': 30.0}


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def agent(*scopes, label='Helper'):
    return {'actor_id': 'agent-7f3c', 'kind': 'agent', 'label': label, 'scopes': list(scopes)}


@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class AnnotationCase(inside_base.ProductCase):
    """ProductCase with records of several kinds, four tasks on datasets/numbers and a Service."""

    RECORDS = None

    def setUp(self):
        super().setUp()
        self.write('img.png', inside_base.png(20, 10))
        self.write('snd.wav', inside_base.wav16([0] * 8000, rate=8000))   # one second
        self.write('f1.txt', 'abcdef')
        self.records = self.RECORDS or [
            {'id': 't1', 'kind': 'text', 'text': 'hello world', 'sha256': sha('hello world')},
            {'id': 't2', 'kind': 'text', 'text': 'second'},
            {'id': 'f1', 'kind': 'text', 'path': 'f1.txt'},
            {'id': 'img', 'kind': 'image', 'path': 'img.png'},
            {'id': 'snd', 'kind': 'audio', 'path': 'snd.wav'},
        ]
        self.write_list(self.records)
        self.task('scenes', 'class', ['cat', 'dog'])
        self.task('shapes', 'boxes', ['cat'])
        self.task('mentions', 'spans', ['PER'])
        self.task('speech', 'segments', ['speech'])
        patcher = mock.patch.object(service, '_now', return_value=AT)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def write_list(self, records):
        self.write('records.jsonl', ''.join(json.dumps(record) + '\n' for record in records))

    def task(self, name, kind, vocabulary=None):
        document = {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': name.title(),
                    'dataset': 'datasets/numbers', 'task': kind}
        if vocabulary:
            document['vocabulary'] = vocabulary
        (self.folder / 'annotations').mkdir(exist_ok=True)
        (self.folder / f'annotations/{name}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def call(self, name, actor=OWNER, **arguments):
        result = self.service.call(name, arguments, actor)
        json.dumps(result, allow_nan=False)
        return result

    def refused(self, name, actor=OWNER, **arguments):
        with self.assertRaises(store.ProjectError) as caught:
            self.service.call(name, arguments, actor)
        return caught.exception

    def set(self, *items, task='scenes', actor=OWNER, **extra):
        return self.call('set_annotation', actor=actor, task=task, items=list(items), **extra)

    def lines_file(self, name='scenes'):
        return self.folder / f'annotations/{name}.jsonl'

    def disk_lines(self, name='scenes'):
        return [json.loads(line) for line in self.lines_file(name).read_text(encoding='utf-8').splitlines()]

    def counts(self, task=TASK):
        return next(item for item in self.call('annotation_tasks')['tasks'] if item['task'] == task)

    def rewrite(self, rows, name='scenes'):
        """Write the line file by hand (as a pull would), with a time other than the one recorded."""
        path = self.lines_file(name)
        before = path.stat().st_mtime_ns if path.exists() else 0
        path.write_bytes(annotations.write(rows))
        os.utime(path, ns=(before + 10_000_000_000, before + 10_000_000_000))


class WorkingCopy(AnnotationCase):

    def test_set_count_save_and_open_again(self):
        done = self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'},
                        {'record': 't2', 'state': 'draft', 'value': None, 'note': 'not sure'})
        self.assertEqual(done, {'task': TASK, 'set': 2, 'removed': 0, 'unsaved': 2})
        status = self.call('status')
        self.assertEqual((status['annotations_unsaved'], status['annotations_changed']),
                         ([{'task': TASK, 'records': 2}], []))
        listed = self.counts()
        self.assertEqual((listed['records'], listed['unsaved'], listed['type'], listed['dataset'], listed['run']),
                         (5, 2, 'class', 'datasets/numbers', self.run_id))
        self.assertEqual(listed['counts'], {'unannotated': 3, 'draft': 1, 'accepted': 1, 'needs-work': 0,
                                            'rejected': 0, 'stale': 0, 'invalid': 0})
        self.assertFalse(self.lines_file().exists())

        saved = self.call('save')
        self.assertEqual((saved['annotations_written'], saved['annotations_deleted']), ([LINES], []))
        self.assertEqual(self.lines_file().read_bytes(), (
            '{"record":"t1","sha256":"%s","state":"accepted","value":"cat","by":"owner","at":"%s"}\n'
            '{"record":"t2","sha256":"%s","state":"draft","value":null,"note":"not sure","by":"owner","at":"%s"}\n'
            % (sha('hello world'), AT, sha('second'), AT)).encode())
        self.assertEqual(self.call('status')['annotations_unsaved'], [])
        self.assertEqual(self.counts()['unsaved'], 0)
        self.assertEqual(self.call('save')['annotations_written'], [])  # nothing left to write

        one = self.call('annotation', task='scenes', record='t2')
        self.assertEqual((one['unsaved'], one['stale'], one['sha256']), (False, False, sha('second')))
        self.assertEqual(one['annotation'], one['saved'])
        # A second open, and a fresh import of the folder into an empty database, read the same.
        again = Service(self.folder)
        self.addCleanup(again.close)
        self.assertEqual(again.call('annotation', {'task': TASK, 'record': 't2'}, OWNER), one)
        self.service.close()
        again.close()
        store.drop_project(self.project_id)
        fresh = Service(self.folder)
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.call('annotation', {'task': TASK, 'record': 't2'}, OWNER)['annotation'],
                         one['annotation'])
        self.assertEqual(fresh.call('status', {}, OWNER)['annotations_unsaved'], [])

    def test_remove_and_delete_the_file(self):
        self.set({'record': 't1', 'state': 'rejected'})
        self.call('save')
        done = self.set({'record': 't1', 'remove': True}, {'record': 't2', 'remove': True})
        self.assertEqual((done['set'], done['removed'], done['unsaved']), (0, 1, 1))
        self.assertIsNone(self.call('annotation', task='scenes', record='t1')['annotation'])
        self.assertEqual(self.call('save')['annotations_deleted'], [LINES])
        self.assertFalse(self.lines_file().exists())
        self.assertEqual(self.call('status')['annotations_unsaved'], [])

    def test_revert(self):
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'})
        self.call('save')
        self.set({'record': 't1', 'state': 'accepted', 'value': 'dog'}, {'record': 't2', 'state': 'draft'},
                 {'record': 'f1', 'state': 'draft'})
        self.assertEqual(self.call('revert_annotations', task=TASK, records=['t1']), {'task': TASK, 'reverted': 1})
        back = self.call('annotation', task='scenes', record='t1')
        self.assertEqual((back['annotation']['value'], back['unsaved']), ('cat', False))
        self.assertEqual(self.call('revert_annotations', task='scenes'), {'task': TASK, 'reverted': 2})
        self.assertIsNone(self.call('annotation', task='scenes', record='t2')['annotation'])
        self.assertEqual(self.call('status')['annotations_unsaved'], [])
        self.assertEqual(self.call('revert_annotations', task='scenes')['reverted'], 0)
        # A removal is reverted too.
        self.set({'record': 't1', 'remove': True})
        self.call('revert_annotations', task='scenes')
        self.assertEqual(self.call('annotation', task='scenes', record='t1')['annotation']['value'], 'cat')

    def test_a_file_changed_on_disk_is_imported(self):
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'}, {'record': 't2', 'state': 'draft'})
        self.call('save')
        rows = self.disk_lines()
        rows[1]['state'] = 'needs-work'
        rows.append({'record': 'zz', 'sha256': None, 'state': 'rejected', 'value': None, 'by': 'owner', 'at': AT})
        self.rewrite(rows)
        self.assertEqual(self.call('annotation', task='scenes', record='t2')['annotation']['state'], 'needs-work')
        counts = self.counts()['counts']
        self.assertEqual((counts['needs-work'], counts['rejected'], counts['stale']), (1, 1, 1))  # zz is not a record
        status = self.call('status')
        self.assertEqual((status['annotations_unsaved'], status['annotations_changed']), ([], []))
        # The same bytes with a new time are not imported again: only the time recorded changes.
        os.utime(self.lines_file(), ns=(1, 1))
        self.assertEqual(self.call('annotation', task='scenes', record='zz')['annotation']['state'], 'rejected')
        # A line file that is gone forgets the saved lines; an unsaved edit stays, as unsaved.
        self.set({'record': 't1', 'state': 'accepted', 'value': 'dog'})
        self.lines_file().unlink()
        status = self.call('status')
        self.assertEqual(status['annotations_unsaved'], [{'task': TASK, 'records': 1}])
        one = self.call('annotation', task='scenes', record='t1')
        self.assertEqual((one['annotation']['value'], one['saved'], one['unsaved']), ('dog', None, True))
        self.assertIsNone(self.call('annotation', task='scenes', record='t2')['annotation'])
        self.assertEqual(self.call('save')['annotations_written'], [LINES])
        self.assertEqual([row['record'] for row in self.disk_lines()], ['t1'])

    def test_an_edit_of_the_same_size_at_the_same_time_is_still_noticed(self):
        # Written twice within one tick of the clock, to the same size: size and time say nothing changed.
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'})
        self.call('save')
        path = self.lines_file()
        before = os.stat(path)
        edited = path.read_bytes().replace(b'"value":"cat"', b'"value":"dog"')
        self.assertEqual(len(edited), before.st_size)
        path.write_bytes(edited)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(os.stat(path).st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.call('annotation', task='scenes', record='t1')['annotation']['value'], 'dog')
        # And save does not write over such an edit: with an unsaved change of that record it is a conflict.
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'})
        again = path.read_bytes().replace(b'"value":"dog"', b'"value":"cat"').replace(b'"state":"accepted"',
                                                                                    b'"state":"rejected"')
        now = os.stat(path)
        path.write_bytes(again)
        os.utime(path, ns=(now.st_atime_ns, now.st_mtime_ns))
        self.assertEqual(self.refused('save').code, 'conflict')
        self.assertEqual(path.read_bytes(), again)      # nothing was written over the edit

    def test_a_change_on_disk_to_an_edited_record_is_a_conflict(self):
        for choice, value in (('keep', 'dog'), ('discard', 'cat')):
            with self.subTest(choice):
                self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'},
                         {'record': 't2', 'state': 'draft'})
                self.call('save')
                self.set({'record': 't1', 'state': 'accepted', 'value': 'dog'})
                rows = self.disk_lines()
                rows[1]['note'] = 'changed on disk, t1 is not'
                self.rewrite(rows)
                # A change to another record than the one edited here is no conflict: it is imported.
                self.assertEqual(self.call('annotation', task='scenes', record='t2')['annotation']['note'],
                                 'changed on disk, t1 is not')
                rows = self.disk_lines()
                rows[0]['note'] = 'changed on disk'
                self.rewrite(rows)
                refused = self.refused('summary')
                self.assertEqual((refused.code, refused.references), ('conflict', [LINES]))
                self.assertIn(LINES, str(refused))
                self.assertEqual(self.refused('save').code, 'conflict')
                self.call('resolve_conflict', choice=choice)
                one = self.call('annotation', task='scenes', record='t1')
                self.assertEqual(one['annotation']['value'], value)
                self.assertEqual(one['saved']['note'], 'changed on disk')
                self.assertEqual(one['unsaved'], choice == 'keep')
                self.call('save')
                self.assertEqual(self.disk_lines()[0]['value'], value)
                self.assertEqual(self.call('status')['annotations_unsaved'], [])
                self.call('set_annotation', task='scenes', items=[{'record': 't1', 'remove': True},
                                                                  {'record': 't2', 'remove': True}])
                self.call('save')

    def test_save_refuses_a_file_changed_since_it_was_imported(self):
        self.set({'record': 't1', 'state': 'draft'})
        self.call('save')
        self.set({'record': 't2', 'state': 'draft'})
        with store.open_project(self.folder) as project:
            rows = self.disk_lines()
            rows[0]['note'] = 'between the open and the save'
            self.rewrite(rows)
            with self.assertRaises(store.ProjectError) as caught:
                project.save()
        self.assertEqual((caught.exception.code, caught.exception.references), ('changed-on-disk', [LINES]))

    def test_activity_names_the_task_and_how_many(self):
        self.set({'record': 't1', 'state': 'draft'}, {'record': 't2', 'state': 'draft'})
        self.call('revert_annotations', task='annotations/scenes')
        rows = self.call('activity')['items']
        self.assertEqual([(row['operation'], row['target'], row['outcome'], row['detail']) for row in rows],
                         [('revert_annotations', TASK, 'done', '2 reverted'),
                          ('set_annotation', TASK, 'done', '2 set, 0 removed')])

    def test_an_agents_line_says_agent_and_its_label_and_nothing_else_of_it(self):
        label = 'Night shift helper ' + 'x' * 100
        self.set({'record': 't1', 'state': 'draft', 'value': 'cat'}, actor=agent('inspect', 'edit', label=label))
        self.assertEqual(self.refused('set_annotation', actor=agent('inspect'), task='scenes',
                                      items=[{'record': 't1', 'state': 'draft'}]).code, 'forbidden')
        self.call('save')
        text = self.lines_file().read_text(encoding='utf-8')
        [row] = self.disk_lines()
        self.assertEqual(row['by'], 'agent:' + label[:80])
        self.assertEqual(len(row['by']), len('agent:') + 80)
        for secret in ('agent-7f3c', 'inspect', 'edit', 'scopes', 'actor'):
            self.assertNotIn(secret, text)

    def test_removing_a_task_with_annotations_is_refused(self):
        self.set({'record': 't1', 'state': 'draft'}, {'record': 't2', 'state': 'draft'}, {'record': 'f1', 'state': 'draft'})
        refused = self.refused('remove_definition', reference=TASK)
        self.assertEqual(refused.code, 'in-use')
        self.assertIn('3 annotations', str(refused))
        self.call('revert_annotations', task='scenes')
        self.call('remove_definition', reference=TASK)  # none left: it may go
        self.assertEqual(self.call('save')['deleted'], [TASK])

    def test_a_removed_task_takes_its_file_with_it(self):
        self.set({'record': 't1', 'state': 'draft'})
        self.call('save')
        self.set({'record': 't1', 'remove': True})
        self.call('remove_definition', reference=TASK)
        saved = self.call('save')
        self.assertEqual((saved['deleted'], saved['annotations_deleted']), ([TASK], [LINES]))
        self.assertFalse(self.lines_file().exists())
        self.assertTrue(self.call('check')['ok'])


class Refusals(AnnotationCase):
    """Every refusal of set_annotation; each changes nothing and is recorded."""

    def assertRefused(self, code, task='scenes', items=(), **extra):
        before = self.call('status')['annotations_unsaved']
        refused = self.refused('set_annotation', task=task, items=list(items), **extra)
        self.assertEqual(refused.code, code, str(refused))
        self.assertEqual(self.call('status')['annotations_unsaved'], before)
        self.assertNotIn('label', str(refused).lower())
        return refused

    def test_every_refusal(self):
        self.set({'record': 't1', 'state': 'draft'})
        good = {'record': 't2', 'state': 'accepted', 'value': 'cat'}
        cases = [
            ('not-found', 'nothing', [good], {}),                                        # no such task
            ('invalid', 'scenes', [], {}),                                               # no item
            ('invalid', 'scenes', [good] * 201, {}),                                     # over 200 items
            ('invalid', 'scenes', [{**good, 'state': 'done'}], {}),                      # not a state
            ('invalid', 'scenes', [{**good, 'colour': 'red'}], {}),                      # an unknown key
            ('invalid', 'scenes', [{**good, 'note': 'n' * 4001}], {}),                   # a note too long
            ('invalid', 'scenes', [{'record': 't2', 'remove': False}], {}),              # remove must be true
            ('invalid', 'scenes', [{**good, 'record': 'r' * 601}], {}),                  # a record id too long
            ('invalid', 'scenes', [good, {'record': 'missing', 'state': 'draft'}], {}),  # not in the product
            ('invalid', 'scenes', [good, {**good, 'value': 'dog'}], {}),                 # a record twice
            ('invalid', 'scenes', [{**good, 'value': 'cow'}], {}),                       # a term not in the vocabulary
            ('invalid', 'scenes', [{**good, 'value': None}], {}),                        # accepted without a value
            ('invalid', 'scenes', [{**good, 'value': ['cat']}], {}),                     # not one term
            ('invalid', 'scenes', [{**good, 'note': 'a\x00b'}], {}),                     # U+0000
            ('invalid', 'scenes', [good], {'from': {'model': 'x' * 3000}}),              # from over 2 KiB
            ('invalid', 'shapes', [{'record': 't2', 'state': 'accepted',                 # boxes on a text
                                    'value': [{'term': 'cat', 'x': 0, 'y': 0, 'w': 1, 'h': 1}]}], {}),
            ('invalid', 'shapes', [{'record': 'img', 'state': 'accepted',                # outside the image
                                    'value': [{'term': 'cat', 'x': 15, 'y': 0, 'w': 10, 'h': 5}]}], {}),
            ('invalid', 'mentions', [{'record': 't1', 'state': 'accepted',               # past the text
                                      'value': [{'term': 'PER', 'start': 6, 'end': 12}]}], {}),
            ('invalid', 'mentions', [{'record': 'f1', 'state': 'accepted',               # past a file's text
                                      'value': [{'term': 'PER', 'start': 0, 'end': 7}]}], {}),
            ('invalid', 'speech', [{'record': 'snd', 'state': 'accepted',                # past the sound
                                    'value': [{'term': 'speech', 'start': 0.5, 'end': 1.5}]}], {}),
            ('invalid', 'speech', [{'record': 'img', 'state': 'draft', 'value': None}], {}),  # not a sound
        ]
        for code, task, items, extra in cases:
            with self.subTest(task=task, items=str(items)[:120]):
                refused = self.assertRefused(code, task, items, **extra)
                if code == 'invalid' and items and len(items) <= 2 and 'remove' not in items[-1] \
                        and len(items[-1]['record']) <= 600 and items[-1].get('state') in annotations.STATES \
                        and set(items[-1]) <= {'record', 'state', 'value', 'note'} \
                        and len(items[-1].get('note') or '') <= 4000:
                    self.assertEqual([problem.pointer for problem in refused.problems], [f'/items/{len(items) - 1}'])
        # The same items, right, are kept; the bounds were the record's.
        self.set({'record': 'img', 'state': 'accepted', 'value': [{'term': 'cat', 'x': 10, 'y': 0, 'w': 10, 'h': 10}]},
                 task='shapes')
        self.set({'record': 't1', 'state': 'accepted', 'value': [{'term': 'PER', 'start': 6, 'end': 11}]},
                 task='mentions')
        self.set({'record': 'f1', 'state': 'accepted', 'value': [{'term': 'PER', 'start': 0, 'end': 6}]},
                 task='mentions')
        self.set({'record': 'snd', 'state': 'accepted', 'value': [{'term': 'speech', 'start': 0.5, 'end': 1.0,
                                                                   'text': 'hi'}]}, task='speech')
        # Without a product, there is nothing to annotate; a removal is still allowed.
        with store.open_project(self.folder) as project:
            project._execute('UPDATE {schema}.products SET current = false')
        self.assertRefused('not-found', 'scenes', [good])
        self.assertEqual(self.set({'record': 't1', 'remove': True})['removed'], 1)
        refusals = [row for row in self.call('activity', limit=500)['items'] if row['outcome'] != 'done']
        self.assertEqual(len(refusals), len(cases) + 1)
        self.assertTrue(all(row['target'] in (TASK, 'annotations/nothing', 'annotations/shapes',
                                              'annotations/mentions', 'annotations/speech') for row in refusals))

    def test_a_value_the_task_no_longer_allows_is_counted_invalid(self):
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'}, {'record': 't2', 'state': 'accepted',
                                                                         'value': 'dog'})
        self.assertEqual(self.counts()['counts']['invalid'], 0)
        text = (self.folder / 'annotations/scenes.json').read_text(encoding='utf-8').replace('"dog"', '"bird"')
        self.call('set_definition', reference=TASK, text=text)
        self.assertEqual(self.counts()['counts']['invalid'], 1)
        self.assertEqual([record['id'] for record in self.call('annotated_records', task='scenes',
                                                               state='invalid')['records']], ['t2'])


class Stale(AnnotationCase):

    def test_stale_by_a_missing_record_and_by_different_content(self):
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'}, {'record': 't2', 'state': 'draft'},
                 {'record': 'f1', 'state': 'draft'})
        self.assertEqual(self.counts()['counts']['stale'], 0)
        # The record list now gives another hash for t1, and has no t2.
        records = [dict(record) for record in self.records if record['id'] != 't2']
        records[0]['sha256'] = sha('hello there')
        self.write_list(records)
        listed = self.counts()
        self.assertEqual((listed['counts']['stale'], listed['records'], listed['counts']['unannotated']), (2, 4, 2))
        page = self.call('annotated_records', task='scenes', state='stale')
        self.assertEqual([(record['id'], record['in_product'], record['annotation']['stale'])
                          for record in page['records']], [('t1', True, True), ('t2', False, True)])
        self.assertEqual(self.call('annotation', task='scenes', record='t1')['stale'], True)
        # "Still right": setting it again takes the record's hash.
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'})
        self.assertEqual(self.call('annotation', task='scenes', record='t1')['annotation']['sha256'],
                         sha('hello there'))
        self.assertEqual(self.counts()['counts']['stale'], 1)

    def test_stale_when_a_new_product_holds_other_content(self):
        self.set({'record': 'f1', 'state': 'draft'})
        source = self.temporary / 'again.json'
        source.write_text('{}', encoding='utf-8')
        manifest = {'format': 'tuldok_adoption_v1',
                    'products': [{'reference': 'datasets/numbers', 'files': {'numbers.json': str(source)}}]}
        with self.opened() as project:
            done = adoption.adopt(project, adoption.make_plan(project, manifest, copy=True, replace=True))
        output = Path(done['entries'][0]['directory'])
        (output / 'records.jsonl').write_text(json.dumps({'id': 'f1', 'kind': 'text', 'path': 'f1.txt'}) + '\n')
        (output / 'f1.txt').write_text('abcdeF')
        self.assertEqual(self.counts()['counts']['stale'], 1)
        (output / 'f1.txt').write_text('abcdef')   # a run's files never change; this one is read once, then kept
        self.assertEqual(self.counts()['counts']['stale'], 1)


class Hashes(AnnotationCase):

    def test_computed_once_per_run_and_record_and_not_over_the_bound(self):
        calls = []
        original = annotation_records._file_sha256

        def counted(path, limit):
            calls.append(os.path.basename(path))
            return original(path, limit)

        with mock.patch.object(annotation_records, '_file_sha256', counted):
            self.set({'record': 'f1', 'state': 'draft'}, {'record': 'img', 'state': 'draft'})
            self.assertEqual(sorted(calls), ['f1.txt', 'img.png'])
            self.counts()
            self.call('annotated_records', task='scenes')
            self.call('annotation', task='scenes', record='f1')
            self.set({'record': 'f1', 'state': 'rejected'})
            self.assertEqual(sorted(calls), ['f1.txt', 'img.png'])
            # The hash of a record that is not annotated is computed when it is asked for, once.
            self.assertEqual(self.call('annotation', task='scenes', record='snd')['sha256'],
                             sha((self.output / 'snd.wav').read_bytes()))
            self.call('annotation', task='scenes', record='snd')
            self.assertEqual(calls.count('snd.wav'), 1)
        self.assertEqual(self.call('annotation', task='scenes', record='f1')['annotation']['sha256'], sha('abcdef'))
        # A record over the bound is not hashed: its annotation carries null and is tied by its id alone.
        with mock.patch.object(annotation_records, 'HASH_LIMIT', 8):
            self.write('big.txt', 'more than eight bytes')
            self.write_list(self.records + [{'id': 'big', 'kind': 'text', 'path': 'big.txt'}])
            self.set({'record': 'big', 'state': 'draft'})
            one = self.call('annotation', task='scenes', record='big')
            self.assertEqual((one['annotation']['sha256'], one['sha256'], one['stale']), (None, None, False))

    def test_an_archive_member_is_hashed_decompressed(self):
        import zipfile
        member = b'inside the archive ' * 100
        self.write('pack.zip', inside_base.zip_bytes({'a.txt': member}, zipfile.ZIP_DEFLATED))
        self.write_list(self.records + [{'id': 'packed', 'kind': 'text', 'path': 'pack.zip!a.txt'}])
        self.set({'record': 'packed', 'state': 'draft'})
        self.assertEqual(self.call('annotation', task='scenes', record='packed')['annotation']['sha256'], sha(member))

    def test_the_record_list_may_carry_the_hash(self):
        bad = dict(self.records[1], sha256='ABC')
        self.write_list([self.records[0], bad])
        listed = self.call('records', run=self.run_id)
        self.assertEqual([record['sha256'] for record in listed['records']], [sha('hello world')])
        self.assertEqual(listed['problems'][0]['line'], 2)
        self.assertIn('sha256', listed['problems'][0]['message'])


class Reads(AnnotationCase):

    def test_annotated_records_pages_and_filters(self):
        self.set({'record': 't1', 'state': 'accepted', 'value': 'cat'}, {'record': 'img', 'state': 'rejected'})
        page = self.call('annotated_records', task='scenes', limit=2)
        self.assertEqual((page['total'], page['run'], [record['id'] for record in page['records']]),
                         (5, self.run_id, ['t1', 't2']))
        first = page['records'][0]
        self.assertEqual(first['annotation'], {'state': 'accepted', 'value': 'cat', 'note': None, 'by': 'owner',
                                               'at': AT, 'stale': False, 'unsaved': True})
        self.assertEqual((first['preview'], first['in_product'], first['sha256']), ('hello world', True,
                                                                                     sha('hello world')))
        self.assertIsNone(page['records'][1]['annotation'])
        self.assertEqual(page['counts']['unannotated'], 3)
        for state, expected in (('unannotated', ['t2', 'f1', 'snd']), ('accepted', ['t1']), ('rejected', ['img']),
                                ('draft', []), ('stale', []), ('invalid', [])):
            with self.subTest(state):
                found = self.call('annotated_records', task='scenes', state=state)
                self.assertEqual(([record['id'] for record in found['records']], found['total']),
                                 (expected, len(expected)))
        self.assertEqual([record['id'] for record in self.call('annotated_records', task='annotations/scenes',
                                                               kind='image')['records']], ['img'])
        self.assertEqual([record['id'] for record in self.call('annotated_records', task='scenes', offset=4)['records']],
                         ['snd'])
        self.assertEqual(self.refused('annotated_records', task='scenes', limit=201).code, 'invalid')
        self.assertEqual(self.refused('annotation', task='nothing', record='t1').code, 'not-found')

    def test_tasks_are_listed_with_what_the_page_needs(self):
        tasks = self.call('annotation_tasks')['tasks']
        self.assertEqual([task['task'] for task in tasks], ['annotations/mentions', 'annotations/scenes',
                                                           'annotations/shapes', 'annotations/speech'])
        self.assertEqual(set(tasks[1]), {'task', 'title', 'dataset', 'type', 'vocabulary', 'run', 'records', 'counts',
                                         'unsaved'})
        self.assertEqual(tasks[1]['vocabulary'], ['cat', 'dog'])

    def test_reads_change_nothing_on_disk_and_are_not_recorded(self):
        self.set({'record': 't1', 'state': 'draft'})
        before = sorted((path, path.stat().st_mtime_ns) for path in self.folder.rglob('*') if path.is_file())
        rows = len(self.call('activity')['items'])
        self.call('annotation_tasks')
        self.call('annotated_records', task='scenes')
        self.call('annotation', task='scenes', record='t1')
        self.call('status')
        after = sorted((path, path.stat().st_mtime_ns) for path in self.folder.rglob('*') if path.is_file())
        self.assertEqual((before, len(self.call('activity')['items'])), (after, rows))


class Many(AnnotationCase):
    """100,000 annotations: set in batches of 200 through the service, counted, saved and opened again."""

    COUNT = 100_000
    RECORDS = [{'id': f'r{index:06d}', 'kind': 'text', 'text': f'record {index}', 'sha256': sha(f'record {index}')}
               for index in range(COUNT)]

    def test_one_hundred_thousand(self):
        times = {}
        started = time.perf_counter()
        for first in range(0, self.COUNT, 200):
            self.set(*({'record': f'r{index:06d}', 'state': ('accepted', 'draft', 'rejected', 'needs-work')[index % 4],
                        'value': 'cat' if index % 4 == 0 else None} for index in range(first, first + 200)))
        times['set'] = time.perf_counter() - started

        started = time.perf_counter()
        listed = self.counts()
        times['count'] = time.perf_counter() - started
        self.assertEqual(listed['counts'], {'unannotated': 0, 'draft': 25_000, 'accepted': 25_000,
                                            'needs-work': 25_000, 'rejected': 25_000, 'stale': 0, 'invalid': 0})
        self.assertEqual(listed['unsaved'], self.COUNT)
        started = time.perf_counter()
        self.assertEqual(self.call('status')['annotations_unsaved'], [{'task': TASK, 'records': self.COUNT}])
        times['status'] = time.perf_counter() - started

        started = time.perf_counter()
        self.assertEqual(self.call('save')['annotations_written'], [LINES])
        times['save'] = time.perf_counter() - started
        self.assertEqual(len(self.lines_file().read_bytes().splitlines()), self.COUNT)

        started = time.perf_counter()
        again = Service(self.folder)
        self.addCleanup(again.close)
        self.assertEqual(again.call('annotation', {'task': TASK, 'record': 'r099999'}, OWNER)['annotation']['state'],
                         'needs-work')
        times['reopen'] = time.perf_counter() - started

        self.service.close()
        again.close()
        store.drop_project(self.project_id)
        inside.forget_indexes()
        started = time.perf_counter()
        fresh = Service(self.folder)
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.call('annotation_tasks', {}, OWNER)['tasks'][1]['counts']['accepted'], 25_000)
        times['import'] = time.perf_counter() - started
        print(f'\n100,000 annotations: ' + ', '.join(f'{name} {seconds:.2f} s' for name, seconds in times.items()),
              file=sys.stderr)
        for name, bound in BOUNDS.items():
            self.assertLess(times[name], bound, name)


if __name__ == '__main__':
    unittest.main()
