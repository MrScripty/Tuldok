"""Adopting existing files as products (docs/plans/definition-first-projects/spec-m8.md, section 3).

Every test needs a database and runs only when TULDOK_DATABASE_URL names a
disposable cluster (spec-m1-m2.md, section 1). Each starts from
test_tuldok_project_builds.BuildCase: a Git-committed copy of the buildable
fixture with its environment connected, TULDOK_PROJECT_HOME pointing at a
temporary directory, dropped afterwards. TULDOK_SETTINGS points at a file in
that directory too, so the real settings file is never read. The files
adopted are written by the tests under the same temporary directory, so they
are on the project directory's filesystem and are linked unless --copy. The
builds run the fixture's stand-in scripts; no GPU is used.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import adoption, builds, local, operations  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
import test_tuldok_project_service as service_base  # noqa: E402

NUMBERS = {'numbers': [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]}   # the stand-in dataset makes numbers in [-1, 1]


class AdoptionCase(builds_base.BuildCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.old = self.temporary / 'old'
        self.old.mkdir()
        self.numbers = self.source('numbers.json', json.dumps(NUMBERS))
        self.weights = self.source('weights.json', json.dumps({'constant': 0.25}))

    def source(self, name, text):
        path = self.old / name
        path.write_text(text, encoding='utf-8')
        return path

    def manifest(self, *entries, **top):
        document = {'format': 'tuldok_adoption_v1', 'products': list(entries), **top}
        path = self.temporary / 'manifest.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        return document, path

    def numbers_entry(self, **extra):
        return {'reference': 'datasets/numbers', 'note': 'made long ago', 'files': {'numbers.json': str(self.numbers)},
                **extra}

    def adopt(self, *entries, dry_run=False, copy=False, replace=False):
        document, _ = self.manifest(*entries)
        with self.opened() as project:
            made = adoption.make_plan(project, document, copy=copy, replace=replace)
            return made if dry_run else adoption.adopt(project, made)

    def refused(self, document):
        with self.opened() as project:
            with self.assertRaises(adoption.AdoptionError) as caught:
                adoption.make_plan(project, document)
        return caught.exception.problems

    def run_cli(self, *arguments):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)],
                              cwd=builds_base.REPOSITORY, env=environment, capture_output=True, text=True, timeout=120)

    def nothing_recorded(self):
        self.assertEqual(self.runs(), [])
        self.assertEqual(self.products(), [])


class Adopting(AdoptionCase):

    def test_an_adopted_dataset_is_built_and_used_by_a_real_build(self):
        before = (self.numbers.read_bytes(), os.stat(self.numbers))
        done = self.adopt(self.numbers_entry())
        entry = done['entries'][0]
        self.assertEqual((entry['action'], entry['missing'], done['counts']['linked'], done['counts']['copied']),
                         ('adopt', [], 1, 0))
        self.assertEqual(entry['directory'], os.path.join(self.home, self.project_id, 'runs', entry['run_id'], 'output'))
        adopted = Path(entry['directory']) / 'numbers.json'
        self.assertEqual(os.stat(adopted).st_ino, before[1].st_ino)  # a hard link on the same filesystem
        self.assertEqual([name for name in os.listdir(self.home / self.project_id / 'runs')], [entry['run_id']])

        status = self.status()['datasets/numbers']
        self.assertEqual((status['state'], status['adopted'], status['causes']), ('built', True, []))
        self.assertEqual(self.states()['datasets/numbers'], 'built')
        run = self.runs('datasets/numbers')[0]
        size = len(before[0])
        self.assertEqual((run['state'], run['commit'], run['argv'], run['problem'], run['bytes']),
                         ('adopted', '', [], 'made long ago', size))
        self.assertIsNotNone(run['started_at'])
        self.assertIsNotNone(run['finished_at'])
        product = self.products('datasets/numbers')[0]
        self.assertTrue(product['adopted'])
        self.assertEqual(product['outputs'], {'data': {'path': 'numbers.json', 'role': 'data', 'bytes': size}})

        made = self.plan('benchmarks/score')
        actions = {step['reference']: step['action'] for step in made['steps']}
        self.assertEqual(actions, {'environments/test-python': 'ready', 'datasets/numbers': 'built',
                                   'recipes/fit-a': 'build', 'benchmarks/score': 'build'})
        self.assertTrue(next(step for step in made['steps'] if step['reference'] == 'datasets/numbers')['adopted'])
        done = self.build('benchmarks/score')
        self.assertTrue(done['ok'], done)
        self.assertEqual(self.ran(done), [('recipes/fit-a', '', 'succeeded'), ('benchmarks/score', 'fit-a', 'succeeded'),
                                          ('benchmarks/score', 'zero', 'succeeded')])
        weights = Path(self.products('recipes/fit-a')[0]['directory']) / 'weights.json'
        self.assertGreater(json.loads(weights.read_text())['constant'], 1)  # trained on the adopted numbers
        self.assertEqual({entry['state'] for entry in self.status().values()}, {'built'})
        self.assertEqual((self.numbers.read_bytes(), os.stat(self.numbers).st_mtime_ns,
                          os.stat(self.numbers).st_mode), (before[0], before[1].st_mtime_ns, before[1].st_mode))

    def test_a_dataset_that_declares_no_outputs_is_adopted_as_a_directory(self):
        def whole(document):  # use the dataset's directory as a whole
            document['run']['inputs']['data'] = 'datasets/numbers'
            command = document['run']['command']
            command[command.index('{inputs.data}')] = '{inputs.data}/numbers.json'
        self.edit('recipes/fit-a', whole)
        self.edit('benchmarks/score', whole)
        self.edit('datasets/numbers', lambda document: document['run'].pop('outputs'))
        extra = self.source('notes.txt', 'n' * 7)
        done = self.adopt({'reference': 'datasets/numbers',
                           'files': {'numbers.json': str(self.numbers), 'any/where/notes.txt': str(extra)}})
        entry = done['entries'][0]
        self.assertEqual((entry['outputs'], entry['missing']), ({}, []))
        total = self.numbers.stat().st_size + 7
        self.assertEqual(self.runs('datasets/numbers')[0]['bytes'], total)
        product = self.products('datasets/numbers')[0]
        self.assertEqual((product['outputs'], product['adopted']), ({}, True))
        self.assertTrue((Path(entry['directory']) / 'any' / 'where' / 'notes.txt').is_file())
        self.assertEqual(self.status()['datasets/numbers']['state'], 'built')
        done = self.build('recipes/fit-b')  # fit-b reads {inputs.data}/numbers.json
        self.assertTrue(done['ok'], done)
        self.assertEqual(self.ran(done), [('recipes/fit-b', '', 'succeeded')])
        weights = Path(self.products('recipes/fit-b')[0]['directory']) / 'weights.json'
        self.assertGreater(json.loads(weights.read_text())['constant'], 1)  # read from the adopted directory

    def test_copy_copies(self):
        done = self.adopt(self.numbers_entry(), copy=True)
        self.assertEqual((done['counts']['linked'], done['counts']['copied']), (0, 1))
        adopted = Path(done['entries'][0]['directory']) / 'numbers.json'
        self.assertNotEqual(os.stat(adopted).st_ino, os.stat(self.numbers).st_ino)
        self.assertEqual(adopted.read_bytes(), self.numbers.read_bytes())

    def test_a_file_under_a_declared_output_and_a_missing_output(self):
        def two_outputs(document):
            document['run']['outputs'] = {'data': {'path': 'numbers.json', 'role': 'data'},
                                          'extra': {'path': 'extra', 'role': 'file'},
                                          'more': {'path': 'more.json', 'role': 'file'}}
        self.edit('datasets/numbers', two_outputs)
        part = self.source('part.bin', 'x' * 10)
        done = self.adopt({'reference': 'datasets/numbers',
                           'files': {'numbers.json': str(self.numbers), 'extra/deep/part.bin': str(part)}})
        entry = done['entries'][0]
        self.assertEqual(entry['missing'], [{'name': 'more', 'path': 'more.json'}])
        self.assertEqual(done['counts']['missing'], 1)
        self.assertTrue((Path(entry['directory']) / 'extra' / 'deep' / 'part.bin').is_file())
        product = self.products('datasets/numbers')[0]
        self.assertEqual(sorted(product['outputs']), ['data', 'extra'])
        self.assertEqual(product['outputs']['extra']['bytes'], 10)
        self.assertIsNone(self.runs('datasets/numbers')[0]['problem'])  # no note
        self.assertEqual(self.status()['datasets/numbers']['state'], 'built')

    def test_dry_run_changes_nothing(self):
        done = self.adopt(self.numbers_entry(), dry_run=True)
        self.assertEqual(done['counts'], {'adopt': 1, 'skip': 0, 'missing': 0, 'files': 1,
                                          'bytes': self.numbers.stat().st_size, 'linked': 1, 'copied': 0})
        self.nothing_recorded()
        self.assertFalse((self.home / self.project_id / 'runs').exists())
        _, path = self.manifest(self.numbers_entry())
        shown = self.run_cli('adopt', self.folder, path, '--dry-run')
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertTrue(shown.stdout.startswith('Would adopt 1 entry, skip 0 that already have a product.\n'),
                        shown.stdout)
        self.assertIn('1 file', shown.stdout)
        self.assertIn('linked', shown.stdout)
        self.assertTrue(shown.stdout.endswith('Nothing was changed (--dry-run).\n'))
        self.nothing_recorded()

    def test_a_second_adopt_skips_and_replace_adopts_again(self):
        first = self.adopt(self.numbers_entry())['entries'][0]['run_id']
        again = self.adopt(self.numbers_entry())
        self.assertEqual((again['entries'][0]['action'], again['entries'][0]['current_run']), ('skip', first))
        self.assertEqual(again['counts']['adopt'], 0)
        self.assertEqual(len(self.runs()), 1)
        replaced = self.adopt(self.numbers_entry(), replace=True)['entries'][0]['run_id']
        self.assertNotEqual(replaced, first)
        self.assertEqual(self.products('datasets/numbers')[0]['run_id'], replaced)
        with self.opened() as project:
            rows = project._execute('SELECT run_id, current FROM {schema}.products ORDER BY current').fetchall()
        self.assertEqual(rows, [(first, False), (replaced, True)])  # the old product stays, no longer current

    def test_an_adopted_product_is_never_out_of_date(self):
        self.adopt(self.numbers_entry(), {'reference': 'recipes/fit-a', 'files': {'weights.json': str(self.weights)}})
        self.assertEqual(self.states()['recipes/fit-a'], 'built')
        self.edit('recipes/fit-a', lambda document: document.update(title='Fit a, retitled'))
        self.edit('datasets/numbers', lambda document: document['run']['settings'].update(count=7))
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# changed\n')
        self.write_code('make_data.py', (self.code / 'make_data.py').read_text() + '# changed\n')
        self.commit('Change the code.')
        status = self.status()
        self.assertEqual({reference: status[reference]['state'] for reference in status},
                         {'datasets/numbers': 'built', 'recipes/fit-a': 'built'})
        made = self.plan('datasets/numbers')
        made['steps'] = [dict(step, action='build') if step['reference'] == 'datasets/numbers' else step
                         for step in made['steps']]
        made['counts']['build'] = 1
        done = builds.execute(self.folder, made, confirm=lambda given: True)  # a real build of the definition
        self.assertTrue(done['ok'], done)
        self.assertEqual(self.status()['recipes/fit-a']['state'], 'built')  # its input was rebuilt: not compared
        numbers = self.status()['datasets/numbers']
        self.assertEqual((numbers['state'], numbers['adopted']), ('built', False))  # the build replaced it
        self.assertFalse(self.products('datasets/numbers')[0]['adopted'])
        self.assertEqual(json.loads(self.numbers.read_text()), NUMBERS)  # the old file is untouched

    def test_plan_needs_nothing_an_adopted_definition_uses(self):
        self.adopt({'reference': 'recipes/fit-a', 'files': {'weights.json': str(self.weights)}})
        made = self.plan('recipes/fit-a')
        self.assertEqual([(step['reference'], step['action']) for step in made['steps']], [('recipes/fit-a', 'built')])
        self.assertEqual(made['counts']['build'], 0)

    def test_a_benchmark_subject_uses_an_adopted_recipe_held_by_its_label(self):
        self.edit('recipes/fit-a', lambda document: document.update(
            earlier_work={'rebuild': 'no', 'reason': 'Its code is lost.'}))
        self.assertEqual(self.plan('benchmarks/score')['steps'][-1]['subjects']['run'], ['zero'])  # held before
        self.adopt({'reference': 'recipes/fit-a', 'files': {'weights.json': str(self.weights)}})
        made = self.plan('benchmarks/score')
        self.assertEqual(made['steps'][-1]['subjects']['run'], ['fit-a', 'zero'])
        done = self.build('benchmarks/score')
        self.assertTrue(done['ok'], done)
        self.assertEqual(self.ran(done), [('datasets/numbers', '', 'succeeded'), ('benchmarks/score', 'fit-a', 'succeeded'),
                                          ('benchmarks/score', 'zero', 'succeeded')])
        score = self.status()['benchmarks/score']
        self.assertEqual((score['state'], sorted(score['subjects'])), ('built', ['fit-a', 'zero']))
        run = self.runs('benchmarks/score')
        fit = next(row for row in run if row['subject'] == 'fit-a')
        self.assertEqual(fit['inputs']['{recipe}']['run_id'], self.products('recipes/fit-a')[0]['run_id'])
        self.assertEqual(self.build('benchmarks/score')['steps'], [])  # nothing left to build


class Refusals(AdoptionCase):

    def test_every_refusal_stops_the_whole_manifest(self):
        good = self.numbers_entry()
        link = self.old / 'link.json'
        link.symlink_to(self.numbers)
        with self.opened() as project:
            project.remove_definition('steps/gpu-two')
        weights = {'weights.json': str(self.weights)}
        cases = {
            'another format': ({'format': 'tuldok_adoption_v2', 'products': [good]}, 'format'),
            'an unknown top field': ({'format': 'tuldok_adoption_v1', 'products': [good], 'x': 1}, "'x'"),
            'no products': ({'format': 'tuldok_adoption_v1', 'products': []}, '1 to 5000'),
            'too many products': ({'format': 'tuldok_adoption_v1', 'products': [good] * 5001}, '1 to 5000'),
            'a reference twice': (self.manifest(good, good)[0], 'more than once'),
            'not a reference': (self.manifest(dict(good, reference='numbers'))[0], 'reference such as'),
            'no such definition': (self.manifest(dict(good, reference='datasets/none'))[0], 'no definition'),
            'a removed definition': (self.manifest({'reference': 'steps/gpu-two', 'files': {
                'times.json': str(self.numbers)}})[0], 'no definition'),
            'a benchmark': (self.manifest({'reference': 'benchmarks/score', 'files': {
                'values.json': str(self.numbers)}})[0], 'only a dataset, recipe or step'),
            'an environment': (self.manifest(dict(good, reference='environments/test-python'))[0],
                               'only a dataset, recipe or step'),
            'an unknown entry field': (self.manifest(dict(good, size=3))[0], "'size'"),
            'an empty note': (self.manifest(dict(good, note=''))[0], 'note'),
            'a note too long': (self.manifest(dict(good, note='n' * 401))[0], 'note'),
            'no files': (self.manifest(dict(good, files={}))[0], '1 to 200'),
            'files not an object': (self.manifest(dict(good, files=[str(self.numbers)]))[0], '1 to 200'),
            'too many files': (self.manifest(dict(good, files={f'numbers.json/{index}': str(self.numbers)
                                                              for index in range(201)}))[0], '1 to 200'),
            'a key not in normal form': (self.manifest(dict(good, files={'./numbers.json': str(self.numbers)}))[0],
                                         'normal form'),
            'an absolute key': (self.manifest(dict(good, files={'/numbers.json': str(self.numbers)}))[0], 'absolute'),
            'a key with ..': (self.manifest(dict(good, files={'../numbers.json': str(self.numbers)}))[0], "'..'"),
            'a key that is no declared output': (self.manifest(dict(good, files={'other.json': str(self.numbers)}))[0],
                                                 'not a declared output'),
            'a file with a file under it': (self.manifest({'reference': 'recipes/fit-a', 'files': {
                'weights.json': str(self.weights), 'weights.json/x': str(self.weights)}})[0], 'nothing can be under'),
            'a relative source': (self.manifest(dict(good, files={'numbers.json': 'old/numbers.json'}))[0],
                                  'absolute path'),
            'a missing source': (self.manifest(dict(good, files={'numbers.json': str(self.old / 'gone.json')}))[0],
                                 'cannot be read'),
            'a link': (self.manifest(dict(good, files={'numbers.json': str(link)}))[0], 'is a link'),
            'a directory': (self.manifest(dict(good, files={'numbers.json': str(self.old)}))[0], 'not a regular file'),
        }
        for name, (document, words) in cases.items():
            with self.subTest(name):
                if name not in ('another format', 'an unknown top field', 'no products', 'too many products'):
                    document['products'].append({'reference': 'recipes/fit-a', 'files': weights})  # a good entry too
                problems = self.refused(document)
                self.assertTrue(any(words in problem for problem in problems), problems)
        self.nothing_recorded()
        self.assertFalse((self.home / self.project_id / 'runs').exists())
        self.assertEqual(link.resolve(), self.numbers)

    def test_the_command_line_refuses_with_status_1(self):
        _, path = self.manifest(self.numbers_entry(), {'reference': 'recipes/fit-a',
                                                       'files': {'weights.json': str(self.old / 'gone')}})
        refused = self.run_cli('adopt', self.folder, path)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, '')
        self.assertIn('products[1] (recipes/fit-a): the source of weights.json', refused.stderr)
        self.assertIn('Nothing was adopted: 1 problem in the manifest.', refused.stderr)
        self.nothing_recorded()
        path.write_text('{"format": ', encoding='utf-8')
        self.assertEqual(self.run_cli('adopt', self.folder, path).returncode, 1)
        missing = self.run_cli('adopt', self.folder, self.temporary / 'none.json')
        self.assertEqual(missing.returncode, 2)
        self.assertIn('cannot be read', missing.stderr)

    def test_a_broken_settings_file_stops_a_store_command(self):
        (self.temporary / 'settings.json').write_text('{"format": "tuldok_settings_v1", "extra": 1}')
        _, path = self.manifest(self.numbers_entry())
        with mock.patch.dict(os.environ, {local.HOME_VARIABLE: ''}):
            refused = self.run_cli('adopt', self.folder, path, '--dry-run')
        self.assertEqual(refused.returncode, 2)
        self.assertIn(f'The settings file {self.temporary / "settings.json"} is not valid', refused.stderr)


class Shown(AdoptionCase):

    def test_runs_products_run_and_the_app_show_adopted(self):
        _, path = self.manifest(self.numbers_entry())
        done = self.run_cli('adopt', self.folder, path)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith('Adopted 1 entry, skipped 0 that already have a product.\n'
                                               '1 file, '), done.stdout)
        run_id = self.runs()[0]['id']
        self.assertIn(f'adopted  datasets/numbers  1 file', done.stdout)
        self.assertIn(f'run {run_id}', done.stdout)
        again = json.loads(self.run_cli('adopt', self.folder, path, '--json').stdout)
        self.assertEqual((again['dry_run'], again['counts']['skip'], again['entries'][0]['action']),
                         (False, 1, 'skip'))

        runs = self.run_cli('runs', self.folder).stdout.splitlines()
        self.assertEqual(runs[1].split()[1:4], ['datasets/numbers', '-', 'adopted'])
        products = self.run_cli('products', self.folder).stdout.splitlines()
        self.assertTrue(products[1].endswith('(adopted)'), products)
        self.assertTrue(json.loads(self.run_cli('products', self.folder, '--json').stdout)[0]['adopted'])
        shown = self.run_cli('run', self.folder, run_id).stdout
        self.assertIn('none: adopted, not built here', shown)
        self.assertIn('made long ago', shown)
        self.assertIn('(adopted)', shown)
        self.assertTrue(json.loads(self.run_cli('run', self.folder, run_id, '--json').stdout)['product']['adopted'])
        self.assertIn('adopted, not built here', self.run_cli('plan', self.folder, 'datasets/numbers').stdout)

        service = Service(self.folder)
        self.addCleanup(service.close)
        for name, arguments in (('runs', {}), ('run', {'run': run_id}), ('products', {})):
            result = service.call(name, arguments, service_base.OWNER)
            self.assertTrue(set(operations.by_name(name).result) <= set(result), name)
        self.assertEqual(service.call('runs', {}, service_base.OWNER)['runs'][0]['state'], 'adopted')
        self.assertTrue(service.call('run', {'run': run_id}, service_base.OWNER)['product']['adopted'])
        self.assertTrue(service.call('products', {}, service_base.OWNER)['products'][0]['adopted'])
        self.assertTrue(service.call('plan', {'targets': ['datasets/numbers']}, service_base.OWNER)['steps'][-1]['adopted'])


if __name__ == '__main__':
    unittest.main()
