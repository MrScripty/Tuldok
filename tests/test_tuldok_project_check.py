"""The project folder checker: the fixture passes, and each rule of the format is caught when broken.

Each rule test copies tests/fixtures/tuldok_project/minimal into a temporary
directory, breaks exactly one rule of section 2 of
docs/plans/definition-first-projects/spec-m1-m2.md, and asserts the reported
path, JSON pointer and severity. Results-file content (2.8) belongs to
tuldok_project.results; the classes that need it call the real function and are
kept apart (ResultsFiles, CommandLineOnFixture). Every other class replaces it
with a stub so that a fault there cannot mask or fake a fault here.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import documents, graph, results  # noqa: E402
from tuldok_project.check import check_folder  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DELETE = object()


def _parts(pointer):
    return [part.replace('~1', '/').replace('~0', '~') for part in pointer.split('/')[1:]]


def _apply(document, pointer, value):
    """Set (or with DELETE remove) the value at pointer; an index equal to a list's length appends."""
    *parents, last = _parts(pointer)
    holder = document
    for part in parents:
        holder = holder[int(part)] if isinstance(holder, list) else holder[part]
    if isinstance(holder, list):
        index = int(last)
        if value is DELETE:
            del holder[index]
        elif index == len(holder):
            holder.append(value)
        else:
            holder[index] = value
    elif value is DELETE:
        del holder[last]
    else:
        holder[last] = value


class FixtureCopy(unittest.TestCase):
    """A fresh copy of the fixture per test, with helpers to break it."""
    stub_results = True

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name) / 'minimal'
        shutil.copytree(FIXTURE, self.base, symlinks=True)
        self.project = self.base / 'project'
        self.code = self.base / 'code'
        if self.stub_results:
            patcher = mock.patch.object(results, 'check_results', return_value=[])
            patcher.start()
            self.addCleanup(patcher.stop)

    def edit(self, relative, pointer, value):
        path = self.project / relative
        document = json.loads(path.read_text(encoding='utf-8'))
        _apply(document, pointer, value)
        path.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def write(self, relative, content):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding='utf-8')

    def assertProblem(self, report, path, pointer, severity='error', *, alone=True):
        listing = '\n'.join(f'  {p.severity} {p.path} {p.pointer!r} {p.message}' for p in report.problems) or '  (none)'
        matches = [p for p in report.problems if (p.path, p.pointer, p.severity) == (path, pointer, severity)]
        self.assertTrue(matches, f'expected {severity} at {path} {pointer!r}; got:\n{listing}')
        for problem in matches:
            self.assertTrue(problem.message.strip(), 'every problem carries a sentence')
            self.assertTrue(problem.message.rstrip().endswith('.'), problem.message)
        if alone:
            self.assertEqual(len(report.problems), 1, f'expected only that problem; got:\n{listing}')
        return matches[0]

    def assertClean(self, report):
        listing = '\n'.join(f'  {p.severity} {p.path} {p.pointer!r} {p.message}' for p in report.problems)
        self.assertEqual(report.problems, [], listing)
        self.assertTrue(report.ok)


# -------------------------------------------------------------- 2.1 layout

class Layout(FixtureCopy):
    def test_fixture_has_no_problems_and_parses_the_project(self):
        report = check_folder(self.project)
        self.assertClean(report)
        self.assertEqual(report.project['code_root'], '../code')
        self.assertEqual({d.kind for d in report.definitions.values()}, set(documents.DIRECTORIES))
        self.assertIn(graph.Edge('recipes/stepper-k2', 'recipes/stepper-k1', 'input:start'), report.edges)
        waves = report.definitions['datasets/waves']
        self.assertEqual((waves.kind, waves.name, waves.path), ('dataset', 'waves', 'datasets/waves.json'))
        self.assertEqual(len(waves.sha256), 64)
        self.assertEqual(waves.document['title'], 'Wave scenes')

    def test_unknown_top_level_file(self):
        self.write('extra.txt', 'x')
        self.assertProblem(check_folder(self.project), 'extra.txt', '')

    def test_unknown_top_level_directory(self):
        self.write('scratch/a.txt', 'x')
        self.assertProblem(check_folder(self.project), 'scratch', '')

    def test_readme_and_gitignore_are_allowed(self):
        self.write('.gitignore', '*.tmp\n')
        self.assertClean(check_folder(self.project))

    def test_definition_directory_may_be_absent(self):
        shutil.rmtree(self.project / 'charts')
        self.edit('tuldok.json', '/map', DELETE)  # map.chart names a chart (spec-w1.md)
        self.assertClean(check_folder(self.project))

    def test_definition_directory_holds_only_json(self):
        self.write('datasets/notes.txt', 'x')
        self.assertProblem(check_folder(self.project), 'datasets/notes.txt', '')

    def test_definition_directory_has_no_subdirectories(self):
        self.write('datasets/old/waves.json', '{}')
        self.assertProblem(check_folder(self.project), 'datasets/old', '')

    def test_definition_file_name_follows_the_name_rule(self):
        shutil.copy(self.project / 'charts/speed-accuracy.json', self.project / 'charts/Speed_Accuracy.json')
        self.assertProblem(check_folder(self.project), 'charts/Speed_Accuracy.json', '')

    def test_definition_directory_must_be_a_directory(self):
        shutil.rmtree(self.project / 'charts')
        self.write('charts', 'x')
        report = check_folder(self.project)
        self.assertProblem(report, 'charts', '', alone=False)
        # tuldok.json's map.chart names a chart, which is then not there (spec-w1.md).
        self.assertProblem(report, 'tuldok.json', '/map/chart', alone=False)
        self.assertEqual(len(report.problems), 2)

    def test_definition_file_may_not_be_a_symbolic_link(self):
        os.symlink('speed-accuracy.json', self.project / 'charts/copy.json')
        self.assertProblem(check_folder(self.project), 'charts/copy.json', '')

    def test_definition_directory_may_not_be_a_symbolic_link(self):
        shutil.move(self.project / 'charts', self.base / 'charts')
        os.symlink(self.base / 'charts', self.project / 'charts')
        report = check_folder(self.project)
        self.assertProblem(report, 'charts', '', alone=False)
        # tuldok.json's map.chart names a chart, which is then not there (spec-w1.md).
        self.assertProblem(report, 'tuldok.json', '/map/chart', alone=False)
        self.assertEqual(len(report.problems), 2)

    def test_project_file_may_not_be_a_symbolic_link(self):
        shutil.move(self.project / 'tuldok.json', self.base / 'tuldok.json')
        os.symlink(self.base / 'tuldok.json', self.project / 'tuldok.json')
        self.assertProblem(check_folder(self.project), 'tuldok.json', '')

    def test_project_file_is_required(self):
        (self.project / 'tuldok.json').unlink()
        self.assertProblem(check_folder(self.project), 'tuldok.json', '')

    def test_notes_may_not_hold_symbolic_links(self):
        os.symlink('fits/early-fit.md', self.project / 'notes/link.md')
        self.assertProblem(check_folder(self.project), 'notes/link.md', '')

    def test_definition_size_cap(self):
        path = self.project / 'charts/speed-accuracy.json'
        path.write_text(path.read_text() + ' ' * (1024 * 1024), encoding='utf-8')
        self.assertProblem(check_folder(self.project), 'charts/speed-accuracy.json', '')

    def test_project_file_size_cap(self):
        path = self.project / 'tuldok.json'
        path.write_text(path.read_text() + ' ' * (64 * 1024), encoding='utf-8')
        self.assertProblem(check_folder(self.project), 'tuldok.json', '')

    def test_results_file_size_cap(self):
        with open(self.project / 'results/rollout.csv', 'r+b') as handle:
            handle.truncate(16 * 1024 * 1024 + 1)
        self.assertProblem(check_folder(self.project), 'results/rollout.csv', '')

    def test_results_directory_holds_only_csv_files_with_valid_names(self):
        self.write('results/rollout.txt', 'x')
        self.write('results/Rollout.csv', 'x')
        report = check_folder(self.project)
        self.assertProblem(report, 'results/rollout.txt', '', alone=False)
        self.assertProblem(report, 'results/Rollout.csv', '', alone=False)
        self.assertEqual(len(report.problems), 2)

    def test_missing_folder_is_reported_not_raised(self):
        report = check_folder(self.base / 'nowhere')
        self.assertProblem(report, '.', '')


# ------------------------------------------------------------ 2.2 JSON rules

CHART = 'charts/speed-accuracy.json'
CHART_TEXT = ('{"format": "tuldok_definition_v1", "kind": "chart", "title": "T", '
              '"benchmark": "benchmarks/rollout", "form": "tradeoff", "metric": "rmse", "metric_x": "seconds"%s}')


class JsonRules(FixtureCopy):
    def test_strict_decoding(self):
        cases = {
            'duplicate key': CHART_TEXT % ', "title": "again"',
            'NaN': CHART_TEXT % ', "labels": {"a": NaN}',
            'Infinity': CHART_TEXT % ', "labels": {"a": Infinity}',
            'minus Infinity': CHART_TEXT % ', "labels": {"a": -Infinity}',
            'overflowing number': CHART_TEXT % ', "labels": {"a": 1e999}',
            'not an object': '[1, 2]',
            'not JSON': '{"format": ',
            'not UTF-8': b'{"title": "\xff"}',
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.setUp()
                self.write(CHART, text)
                self.assertProblem(check_folder(self.project), CHART, '')

    def test_valid_raw_text_passes(self):
        self.write(CHART, CHART_TEXT % '')
        self.assertClean(check_folder(self.project))

    def test_free_content_in_settings_config_and_labels(self):
        self.edit('datasets/waves.json', '/run/settings/Any Key!', {'Nested': [1, None, {'x': True}]})
        self.edit('models/stepper.json', '/config_file', DELETE)
        self.edit('models/stepper.json', '/config', {'Width': 32, 'blocks': [{'kind': 'conv'}]})
        self.edit('recipes/early-fit.json', '/labels/Any Key!', 'value')
        self.assertClean(check_folder(self.project))


# ---------------------------------- 2.3 to 2.7: one field of one document

LONG = 'x' * 4001
# (label, file, pointer to change, new value or DELETE, expected pointer)
DOCUMENT_CASES = [
    # 2.2 unknown fields
    ('unknown top-level field', 'datasets/waves.json', '/owner', 'me', '/owner'),
    ('unknown nested field', 'datasets/waves.json', '/run/shell', True, '/run/shell'),
    # 2.3 tuldok.json
    ('project format', 'tuldok.json', '/format', 'tuldok_project_v2', '/format'),
    ('project id', 'tuldok.json', '/id', '3F9C2A1B7D4E4F60A8B1C2D3E4F50617', '/id'),
    ('project id length', 'tuldok.json', '/id', 'abc', '/id'),
    ('project name required', 'tuldok.json', '/name', DELETE, '/name'),
    ('project name length', 'tuldok.json', '/name', 'x' * 121, '/name'),
    ('project name empty', 'tuldok.json', '/name', '', '/name'),
    ('project code root absolute', 'tuldok.json', '/code_root', '/srv/code', '/code_root'),
    ('project unknown field', 'tuldok.json', '/owner', 'me', '/owner'),
    # 2.5 common fields
    ('definition format', 'datasets/waves.json', '/format', 'tuldok_definition_v2', '/format'),
    ('kind matches directory', 'models/stepper.json', '/kind', 'dataset', '/kind'),
    ('kind is known', 'models/stepper.json', '/kind', 'widget', '/kind'),
    ('kind required', 'models/stepper.json', '/kind', DELETE, '/kind'),
    ('title required', 'models/stepper.json', '/title', DELETE, '/title'),
    ('title empty', 'models/stepper.json', '/title', '', '/title'),
    ('title length', 'models/stepper.json', '/title', 'x' * 201, '/title'),
    ('description length', 'models/stepper.json', '/description', LONG, '/description'),
    ('card exists', 'recipes/early-fit.json', '/card', 'notes/fits/missing.md', '/card'),
    ('card under notes', 'recipes/early-fit.json', '/card', 'README.md', '/card'),
    ('card path normal', 'recipes/early-fit.json', '/card', 'notes/../README.md', '/card'),
    ('labels count', 'recipes/early-fit.json', '/labels', {f'k{i}': 'v' for i in range(33)}, '/labels'),
    ('label value type', 'recipes/early-fit.json', '/labels/fit_id', 42, '/labels/fit_id'),
    ('label value length', 'recipes/early-fit.json', '/labels/fit_id', 'x' * 401, '/labels/fit_id'),
    ('no earlier_work on environment', 'environments/lab-cpu.json', '/earlier_work', {'rebuild': 'yes'}, '/earlier_work'),
    ('no earlier_work on chart', CHART, '/earlier_work', {'rebuild': 'yes'}, '/earlier_work'),
    ('rebuild no needs reason', 'recipes/early-fit.json', '/earlier_work/reason', DELETE, '/earlier_work/reason'),
    ('reason length', 'recipes/early-fit.json', '/earlier_work/reason', 'x' * 1001, '/earlier_work/reason'),
    ('rebuild value', 'steps/solver.json', '/earlier_work', {'rebuild': 'maybe'}, '/earlier_work/rebuild'),
    ('earlier_work unknown field', 'recipes/early-fit.json', '/earlier_work/when', '2026', '/earlier_work/when'),
    # 2.6 the run block
    ('run required', 'datasets/waves.json', '/run', DELETE, '/run'),
    ('command required', 'datasets/waves.json', '/run/command', DELETE, '/run/command'),
    ('command not empty', 'steps/solver.json', '/run/command', [], '/run/command'),
    ('command at most 64', 'steps/solver.json', '/run/command', ['cargo'] * 65, '/run/command'),
    ('command strings', 'steps/solver.json', '/run/command/1', 3, '/run/command/1'),
    ('python needs environment', 'steps/solver.json', '/run/environment', DELETE, '/run/environment'),
    ('environment reference directory', 'steps/solver.json', '/run/environment', 'steps/solver', '/run/environment'),
    ('input key pattern', 'recipes/stepper-k1.json', '/run/inputs/Training', 'datasets/waves', '/run/inputs/Training'),
    ('input count', 'recipes/stepper-k1.json', '/run/inputs', {'training': 'datasets/waves', **{f'i{n}': 'datasets/waves' for n in range(32)}}, '/run/inputs'),
    ('input reference directory', 'recipes/stepper-k1.json', '/run/inputs/training', 'models/stepper', '/run/inputs/training'),
    ('input object needs output', 'datasets/waves.json', '/run/inputs/solver/output', DELETE, '/run/inputs/solver'),
    ('input object unknown field', 'datasets/waves.json', '/run/inputs/solver/as', 'x', '/run/inputs/solver'),
    ('settings excludes settings_file', 'recipes/stepper-k1.json', '/run/settings', {}, '/run/settings_file'),
    ('settings is an object', 'recipes/stepper-k2.json', '/run/settings', [1], '/run/settings'),
    ('env key pattern', 'datasets/waves.json', '/run/env/omp', '1', '/run/env/omp'),
    ('env value string', 'datasets/waves.json', '/run/env/OMP_NUM_THREADS', 2, '/run/env/OMP_NUM_THREADS'),
    ('env count', 'datasets/waves.json', '/run/env', {f'V{n}': '1' for n in range(33)}, '/run/env'),
    ('output key pattern', 'datasets/waves.json', '/run/outputs/Scenes', {'path': 's', 'role': 'data'}, '/run/outputs/Scenes'),
    ('output role', 'datasets/waves.json', '/run/outputs/scenes/role', 'dataset', '/run/outputs/scenes/role'),
    ('output path required', 'datasets/waves.json', '/run/outputs/scenes/path', DELETE, '/run/outputs/scenes/path'),
    ('output path relative', 'datasets/waves.json', '/run/outputs/scenes/path', '/tmp/scenes', '/run/outputs/scenes/path'),
    ('output path inside', 'datasets/waves.json', '/run/outputs/scenes/path', '../scenes', '/run/outputs/scenes/path'),
    ('resources gpu boolean', 'recipes/stepper-k1.json', '/run/resources/gpu', 1, '/run/resources/gpu'),
    ('resources cpu_threads', 'recipes/stepper-k1.json', '/run/resources/cpu_threads', 0, '/run/resources/cpu_threads'),
    ('resources memory positive', 'recipes/stepper-k1.json', '/run/resources/memory_gb', 0, '/run/resources/memory_gb'),
    ('resources wall positive', 'recipes/stepper-k1.json', '/run/resources/wall_hours', -1, '/run/resources/wall_hours'),
    ('resources disk positive', 'recipes/stepper-k1.json', '/run/resources/disk_gb', 0, '/run/resources/disk_gb'),
    ('resources unknown', 'recipes/stepper-k1.json', '/run/resources/tpu', 1, '/run/resources/tpu'),
    ('sources count', 'recipes/stepper-k1.json', '/run/sources', ['lab/train.py'] * 65, '/run/sources'),
    ('estimate unknown field', 'datasets/waves.json', '/run/estimate/shell', True, '/run/estimate/shell'),
    ('estimate needs command', 'datasets/waves.json', '/run/estimate/command', DELETE, '/run/estimate/command'),
    # 2.6 placeholders
    ('unknown placeholder', 'datasets/waves.json', '/run/command/7', '{out}', '/run/command/7'),
    ('undeclared input placeholder', 'datasets/waves.json', '/run/command/3', '{inputs.mesher}', '/run/command/3'),
    ('settings placeholder needs settings', 'steps/solver.json', '/run/command/3', '{settings}', '/run/command/3'),
    ('subject placeholder only in benchmark', 'steps/solver.json', '/run/command/3', '{subject}', '/run/command/3'),
    ('subject.name placeholder only in benchmark', 'steps/solver.json', '/run/command/3', '{subject.name}', '/run/command/3'),
    ('lone opening brace', 'steps/solver.json', '/run/command/3', '{output', '/run/command/3'),
    ('lone closing brace', 'steps/solver.json', '/run/command/3', 'output}', '/run/command/3'),
    ('literal braces are fine', 'steps/solver.json', '/run/command/3', '{{output}}/x', None),
    ('placeholder in env value', 'datasets/waves.json', '/run/env/OMP_NUM_THREADS', '{threads}', '/run/env/OMP_NUM_THREADS'),
    ('placeholder in estimate', 'datasets/waves.json', '/run/estimate/command/1', '{inputs.nope}', '/run/estimate/command/1'),
    ('non-python command needs no environment', 'steps/solver.json', '/run/command', ['cargo', 'build', '--target-dir', '{output}'], None),
    # 2.7 dataset
    ('splits count integer', 'datasets/waves.json', '/splits/train', 1.5, '/splits/train'),
    ('splits count not negative', 'datasets/waves.json', '/splits/train', -1, '/splits/train'),
    # 2.7 model
    ('config excludes config_file', 'models/stepper.json', '/config', {}, '/config_file'),
    ('entry is a string', 'models/stepper.json', '/entry', ['lab.model'], '/entry'),
    ('model sources count', 'models/stepper.json', '/sources', ['lab/model.py'] * 65, '/sources'),
    ('model has no run', 'models/stepper.json', '/run', {'command': ['true']}, '/run'),
    # 2.7 recipe
    ('recipe model directory', 'recipes/stepper-k1.json', '/model', 'datasets/waves', '/model'),
    # 2.7 step
    # 2.7 benchmark
    ('benchmark needs one results output', 'benchmarks/rollout.json', '/run/outputs/values/role', 'data', '/run/outputs'),
    ('benchmark has only one results output', 'benchmarks/rollout.json', '/run/outputs/more', {'path': 'm.jsonl', 'role': 'results'}, '/run/outputs'),
    ('benchmark run declares outputs', 'benchmarks/rollout.json', '/run/outputs', DELETE, '/run'),
    ('metrics required', 'benchmarks/rollout.json', '/metrics', DELETE, '/metrics'),
    ('metrics not empty', 'benchmarks/rollout.json', '/metrics', [], '/metrics'),
    ('metric id unique', 'benchmarks/rollout.json', '/metrics/2', {'id': 'rmse', 'title': 'Again', 'better': 'lower'}, '/metrics/2/id'),
    ('metric id pattern', 'benchmarks/rollout.json', '/metrics/2', {'id': 'Error', 'title': 'E', 'better': 'lower'}, '/metrics/2/id'),
    ('metric better', 'benchmarks/rollout.json', '/metrics/0/better', 'smaller', '/metrics/0/better'),
    ('metric title required', 'benchmarks/rollout.json', '/metrics/0/title', DELETE, '/metrics/0/title'),
    ('metric unknown field', 'benchmarks/rollout.json', '/metrics/0/scale', 'log', '/metrics/0/scale'),
    ('subjects required', 'benchmarks/rollout.json', '/subjects', DELETE, '/subjects'),
    ('subject name unique', 'benchmarks/rollout.json', '/subjects/3', {'name': 'stepper-k1'}, '/subjects/3/name'),
    ('subject name pattern', 'benchmarks/rollout.json', '/subjects/3', {'name': 'Stepper K3'}, '/subjects/3/name'),
    ('subject recipe directory', 'benchmarks/rollout.json', '/subjects/0/recipe', 'models/stepper', '/subjects/0/recipe'),
    ('subject argument recipe needs recipe', 'benchmarks/rollout.json', '/subjects/3', {'name': 'baseline', 'argument': '{recipe}/model.pt'}, '/subjects/3/argument'),
    ('subject argument only recipe', 'benchmarks/rollout.json', '/subjects/0/argument', '{output}/model.pt', '/subjects/0/argument'),
    ('cases dataset directory', 'benchmarks/rollout.json', '/cases/dataset', 'recipes/stepper-k1', '/cases/dataset'),
    ('cases count', 'benchmarks/rollout.json', '/cases/count', -1, '/cases/count'),
    ('cases unknown field', 'benchmarks/rollout.json', '/cases/seed', 1, '/cases/seed'),
    ('summary statistic', 'benchmarks/rollout.json', '/summary/statistics/0', 'average', '/summary/statistics/0'),
    ('summary group_by count', 'benchmarks/rollout.json', '/summary/group_by', ['horizon'] + [f'g{n}' for n in range(8)], '/summary/group_by'),
    ('summary group_by pattern', 'benchmarks/rollout.json', '/summary/group_by/1', 'Scene', '/summary/group_by/1'),
    # 2.7 environment
    ('python version form', 'environments/lab-cpu.json', '/python', '3.12.1', '/python'),
    ('python version major', 'environments/lab-cpu.json', '/python', '2.7', '/python'),
    ('python required', 'environments/lab-cpu.json', '/python', DELETE, '/python'),
    ('device', 'environments/lab-cpu.json', '/device', 'gpu', '/device'),
    ('packages not empty', 'environments/lab-cpu.json', '/packages', {}, '/packages'),
    ('packages count', 'environments/lab-cpu.json', '/packages', {f'p{n}': '1.0' for n in range(65)}, '/packages'),
    ('package version exact', 'environments/lab-cpu.json', '/packages/numpy', '>=2.3', '/packages/numpy'),
    ('install requirements required', 'environments/lab-cpu.json', '/install/requirements', DELETE, '/install/requirements'),
    ('index urls https', 'environments/lab-cpu.json', '/install/index_urls/0', 'http://pypi.org/simple', '/install/index_urls/0'),
    ('index urls count', 'environments/lab-cpu.json', '/install/index_urls', ['https://a.example/'] * 5, '/install/index_urls'),
    # 2.7 chart
    ('tradeoff needs metric_x', CHART, '/metric_x', DELETE, '/metric_x'),
    ('metric_x only on tradeoff', 'charts/rollout-ranking.json', '/metric_x', 'seconds', '/metric_x'),
    ('chart form', 'charts/rollout-ranking.json', '/form', 'pie', '/form'),
    ('chart statistic', 'charts/rollout-ranking.json', '/statistic', 'mode', '/statistic'),
    ('chart benchmark directory', 'charts/rollout-ranking.json', '/benchmark', 'datasets/waves', '/benchmark'),
    ('chart metric in benchmark', 'charts/rollout-ranking.json', '/metric', 'mae', '/metric'),
    ('chart metric_x in benchmark', CHART, '/metric_x', 'joules', '/metric_x'),
    ('chart subjects in benchmark', 'charts/rollout-ranking.json', '/subjects/0', 'nobody', '/subjects/0'),
    ('chart group in group_by', 'charts/rollout-ranking.json', '/group', 'scene', '/group'),
]


class DocumentRules(FixtureCopy):
    def test_each_single_document_rule(self):
        for label, relative, pointer, value, expected in DOCUMENT_CASES:
            with self.subTest(label):
                self.setUp()
                if relative.startswith('benchmarks/'):
                    # A broken benchmark also makes its results file unchecked (a
                    # warning, tested in ResultsFiles); drop the file to isolate the rule.
                    shutil.rmtree(self.project / 'results')
                self.edit(relative, pointer, value)
                report = check_folder(self.project)
                if expected is None:
                    self.assertClean(report)
                else:
                    self.assertProblem(report, relative, expected)

    def test_step_run_is_required_and_its_named_outputs_go_with_it(self):
        self.edit('steps/solver.json', '/run', DELETE)
        report = check_folder(self.project)
        self.assertProblem(report, 'steps/solver.json', '/run', alone=False)
        self.assertProblem(report, 'datasets/waves.json', '/run/inputs/solver/output', alone=False)
        self.assertEqual(len(report.problems), 2)

    def test_chart_is_not_checked_against_a_broken_benchmark(self):
        shutil.rmtree(self.project / 'results')
        self.edit('benchmarks/rollout.json', '/metrics', DELETE)
        self.assertProblem(check_folder(self.project), 'benchmarks/rollout.json', '/metrics')

    def test_needs_work_with_a_reason_passes(self):
        for relative in ('datasets/waves.json', 'models/stepper.json', 'recipes/stepper-k1.json',
                         'benchmarks/rollout.json', 'steps/solver.json'):
            with self.subTest(relative):
                self.setUp()
                self.edit(relative, '/earlier_work', {'rebuild': 'needs-work', 'reason': 'The command takes an old flag.'})
                self.assertClean(check_folder(self.project))

    def test_needs_work_needs_a_reason(self):
        self.edit('recipes/stepper-k1.json', '/earlier_work', {'rebuild': 'needs-work'})
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/earlier_work/reason')

    def test_needs_work_still_needs_run(self):
        self.edit('datasets/waves.json', '/run', DELETE)
        self.edit('datasets/waves.json', '/earlier_work', {'rebuild': 'needs-work', 'reason': 'The command takes an old flag.'})
        self.assertProblem(check_folder(self.project), 'datasets/waves.json', '/run')

    def test_unknown_rebuild_value_is_an_error(self):
        self.edit('recipes/stepper-k1.json', '/earlier_work', {'rebuild': 'later', 'reason': 'x'})
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/earlier_work/rebuild')

    def test_run_is_required_unless_rebuild_is_no(self):
        self.edit('datasets/waves.json', '/run', DELETE)
        self.edit('datasets/waves.json', '/earlier_work', {'rebuild': 'after-inputs'})
        self.assertProblem(check_folder(self.project), 'datasets/waves.json', '/run')
        self.edit('datasets/waves.json', '/earlier_work', {'rebuild': 'no', 'reason': 'Lost.'})
        self.assertClean(check_folder(self.project))

    def test_unknown_field_names_the_field(self):
        self.edit('datasets/waves.json', '/run/shell', True)
        problem = self.assertProblem(check_folder(self.project), 'datasets/waves.json', '/run/shell')
        self.assertIn("'shell'", problem.message)

    def test_many_problems_in_many_files_are_all_reported(self):
        self.edit('datasets/waves.json', '/title', '')
        self.edit('models/stepper.json', '/owner', 'me')
        self.write(CHART, '{"broken": ')
        report = check_folder(self.project)
        self.assertProblem(report, 'datasets/waves.json', '/title', alone=False)
        self.assertProblem(report, 'models/stepper.json', '/owner', alone=False)
        self.assertProblem(report, CHART, '', alone=False)
        self.assertEqual(len(report.problems), 3)
        self.assertFalse(report.ok)


# ------------------------------------------------------ 2.9 across files

class CrossFileRules(FixtureCopy):
    def test_each_reference_names_an_existing_definition(self):
        cases = [
            ('input', 'recipes/stepper-k1.json', '/run/inputs/training', 'datasets/missing', '/run/inputs/training'),
            ('input object', 'datasets/waves.json', '/run/inputs/solver/from', 'steps/missing', '/run/inputs/solver/from'),
            ('environment', 'steps/solver.json', '/run/environment', 'environments/gpu', '/run/environment'),
            ('model', 'recipes/stepper-k1.json', '/model', 'models/missing', '/model'),
            ('subject recipe', 'benchmarks/rollout.json', '/subjects/0/recipe', 'recipes/missing', '/subjects/0/recipe'),
            ('cases dataset', 'benchmarks/rollout.json', '/cases/dataset', 'datasets/missing', '/cases/dataset'),
            ('chart benchmark', CHART, '/benchmark', 'benchmarks/missing', '/benchmark'),
        ]
        for label, relative, pointer, value, expected in cases:
            with self.subTest(label):
                self.setUp()
                self.edit(relative, pointer, value)
                self.assertProblem(check_folder(self.project), relative, expected)

    def test_named_output_must_be_declared_by_producer(self):
        self.edit('recipes/stepper-k2.json', '/run/inputs/start/output', 'checkpoint')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k2.json', '/run/inputs/start/output')

    def test_named_output_of_producer_without_run(self):
        self.edit('recipes/stepper-k2.json', '/run/inputs/start/from', 'recipes/early-fit')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k2.json', '/run/inputs/start/output')

    def test_cycle_is_reported_on_each_member(self):
        self.edit('steps/solver.json', '/run/inputs', {'seed': 'datasets/waves'})
        report = check_folder(self.project)
        self.assertProblem(report, 'steps/solver.json', '/run/inputs/seed', alone=False)
        self.assertProblem(report, 'datasets/waves.json', '/run/inputs/solver/from', alone=False)
        self.assertEqual(len(report.problems), 2)

    def test_definition_using_itself_is_a_cycle(self):
        self.edit('datasets/waves.json', '/run/inputs/again', 'datasets/waves')
        self.assertProblem(check_folder(self.project), 'datasets/waves.json', '/run/inputs/again')


class CodeRootPaths(FixtureCopy):
    def test_missing_code_path_is_an_error(self):
        cases = [
            ('settings_file', 'recipes/stepper-k1.json', '/run/settings_file', 'configs/missing.json'),
            ('run sources', 'recipes/stepper-k1.json', '/run/sources/0', 'lab/missing.py'),
            ('config_file', 'models/stepper.json', '/config_file', 'configs/missing.json'),
            ('model sources', 'models/stepper.json', '/sources/0', 'lab/missing.py'),
            ('install requirements', 'environments/lab-cpu.json', '/install/requirements', 'missing.txt'),
        ]
        for label, relative, pointer, value in cases:
            with self.subTest(label):
                self.setUp()
                self.edit(relative, pointer, value)
                self.assertProblem(check_folder(self.project), relative, pointer)

    def test_missing_code_path_is_a_warning_for_earlier_work(self):
        self.edit('models/stepper.json', '/earlier_work', {'rebuild': 'yes'})
        self.edit('models/stepper.json', '/config_file', 'configs/missing.json')
        report = check_folder(self.project)
        self.assertProblem(report, 'models/stepper.json', '/config_file', 'warning')
        self.assertTrue(report.ok)

    def test_code_path_may_not_leave_the_code_root(self):
        self.edit('recipes/stepper-k1.json', '/run/sources/0', '../project/tuldok.json')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/run/sources/0')

    def test_code_path_must_be_normalised(self):
        for value in ('lab//train.py', './lab/train.py', 'lab/', '/abs/train.py'):
            with self.subTest(value):
                self.setUp()
                self.edit('recipes/stepper-k1.json', '/run/sources/0', value)
                self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/run/sources/0')

    def test_code_path_may_not_escape_through_a_symbolic_link(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret.py').write_text('x')
        os.symlink(outside, self.code / 'escape')
        self.edit('recipes/stepper-k1.json', '/run/sources/0', 'escape/secret.py')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/run/sources/0')

    def test_code_root_must_be_a_directory(self):
        self.edit('tuldok.json', '/code_root', '../nowhere')
        self.assertProblem(check_folder(self.project), 'tuldok.json', '/code_root')

    def test_no_code_skips_lookups_but_not_path_form(self):
        self.edit('tuldok.json', '/code_root', '../nowhere')
        self.edit('recipes/stepper-k1.json', '/run/settings_file', 'configs/missing.json')
        self.assertClean(check_folder(self.project, code=False))
        self.edit('recipes/stepper-k1.json', '/run/sources/0', '../lab/train.py')
        self.assertProblem(check_folder(self.project, code=False), 'recipes/stepper-k1.json', '/run/sources/0')


class ProjectCodePaths(FixtureCopy):
    """The optional code_paths of tuldok.json (spec-m6.md section 2)."""

    def test_existing_paths_pass(self):
        self.edit('tuldok.json', '/code_paths', ['lab', 'configs/stepper.json', 'requirements.txt'])
        self.assertClean(check_folder(self.project))

    def test_must_list_one_to_sixty_four_paths(self):
        for label, value in (('empty', []), ('too many', [f'p{i}' for i in range(65)]), ('not a list', 'lab'),
                             ('not strings', [3])):
            with self.subTest(label):
                self.setUp()
                self.edit('tuldok.json', '/code_paths', value)
                pointer = '/code_paths/0' if label == 'not strings' else '/code_paths'
                self.assertProblem(check_folder(self.project, code=False), 'tuldok.json', pointer)

    def test_paths_must_be_in_normal_form(self):
        for value in ('lab//train.py', './lab', 'lab/', '/abs', '../code/lab'):
            with self.subTest(value):
                self.setUp()
                self.edit('tuldok.json', '/code_paths', ['configs', value])
                self.assertProblem(check_folder(self.project), 'tuldok.json', '/code_paths/1')

    def test_paths_are_listed_once(self):
        self.edit('tuldok.json', '/code_paths', ['lab', 'configs', 'lab'])
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/code_paths/2')
        self.assertIn('more than once', problem.message)

    def test_missing_path_is_an_error(self):
        self.edit('tuldok.json', '/code_paths', ['lab', 'missing'])
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/code_paths/1')
        self.assertIn('does not exist', problem.message)

    def test_path_may_not_escape_through_a_symbolic_link(self):
        outside = self.base / 'outside'
        outside.mkdir()
        os.symlink(outside, self.code / 'escape')
        self.edit('tuldok.json', '/code_paths', ['escape'])
        self.assertProblem(check_folder(self.project), 'tuldok.json', '/code_paths/0')

    def test_no_code_skips_lookups_but_not_form_or_repeats(self):
        self.edit('tuldok.json', '/code_paths', ['missing'])
        self.assertClean(check_folder(self.project, code=False))
        self.edit('tuldok.json', '/code_paths', ['missing', 'missing', 'a/../b'])
        report = check_folder(self.project, code=False)
        self.assertProblem(report, 'tuldok.json', '/code_paths/1', alone=False)
        self.assertProblem(report, 'tuldok.json', '/code_paths/2', alone=False)
        self.assertEqual(len(report.problems), 2)


# ------------------------------------------------------------ 2.8 results

class ResultsFiles(FixtureCopy):
    """Uses the real results.check_results (slice T2)."""
    stub_results = False

    def test_fixture_with_its_results_file_has_no_problems(self):
        self.assertClean(check_folder(self.project))

    def test_problem_in_a_results_row_carries_the_file_path(self):
        path = self.project / 'results/rollout.csv'
        path.write_text(path.read_text().replace('early-fit,rmse,,', 'nobody,rmse,,', 1))
        report = check_folder(self.project)
        problem = self.assertProblem(report, 'results/rollout.csv', 'line 2', alone=False)
        self.assertIn('nobody', ' '.join(p.message for p in report.problems))
        self.assertTrue(problem.message)

    def test_results_not_checked_against_a_broken_benchmark(self):
        self.edit('benchmarks/rollout.json', '/metrics/0/better', 'smaller')
        report = check_folder(self.project)
        self.assertProblem(report, 'benchmarks/rollout.json', '/metrics/0/better', alone=False)
        self.assertProblem(report, 'results/rollout.csv', '', 'warning', alone=False)
        self.assertEqual(len(report.problems), 2)


class ResultsFileBenchmark(FixtureCopy):
    """The results file's benchmark must exist (check.py's rule; no call to check_results)."""

    def test_results_file_needs_its_benchmark(self):
        shutil.copy(self.project / 'results/rollout.csv', self.project / 'results/other.csv')
        self.assertProblem(check_folder(self.project), 'results/other.csv', '')


# ------------------------------------------------------- graph and schemas

class Graph(unittest.TestCase):
    def setUp(self):
        with mock.patch.object(results, 'check_results', return_value=[]):
            report = check_folder(FIXTURE / 'project')
        self.definitions = {reference: d.document for reference, d in report.definitions.items()}

    def test_order_puts_dependencies_first_with_ties_by_reference(self):
        built = graph.order(self.definitions)
        self.assertEqual(sorted(built), sorted(self.definitions))
        position = {reference: index for index, reference in enumerate(built)}
        for edge in graph.edges(self.definitions):
            self.assertLess(position[edge.to_ref], position[edge.from_ref], edge)
        self.assertEqual(built[:3], ['environments/lab-cpu', 'models/stepper', 'recipes/early-fit'])

    def test_users_of(self):
        users = graph.users_of(self.definitions, 'recipes/stepper-k1')
        self.assertEqual(users, [graph.Edge('benchmarks/rollout', 'recipes/stepper-k1', 'subject:stepper-k1'),
                                 graph.Edge('recipes/stepper-k2', 'recipes/stepper-k1', 'compared'),
                                 graph.Edge('recipes/stepper-k2', 'recipes/stepper-k1', 'derived'),
                                 graph.Edge('recipes/stepper-k2', 'recipes/stepper-k1', 'input:start')])

    def test_cycles_and_order_refuses_them(self):
        self.assertEqual(graph.cycles(self.definitions), [])
        self.definitions['steps/solver']['run']['inputs'] = {'seed': 'datasets/waves'}
        self.assertEqual(graph.cycles(self.definitions), [('datasets/waves', 'steps/solver')])
        with self.assertRaises(ValueError):
            graph.order(self.definitions)

    def test_edges_ignore_malformed_fields(self):
        self.assertEqual(graph.edges({'datasets/x': {'kind': 'dataset', 'run': {'inputs': [1], 'environment': 3}}}), [])


class Schemas(unittest.TestCase):
    def test_schemas_are_valid_and_share_their_definitions(self):
        names = ['project'] + list(documents.DIRECTORIES)
        shared = {}
        for name in names:
            documents.validator(name)  # checks the schema against the 2020-12 meta-schema
            schema = json.loads((REPOSITORY / 'tuldok_project/schemas' / f'{name}.schema.json').read_text())
            self.assertEqual(schema['$schema'], 'https://json-schema.org/draft/2020-12/schema')
            for key, value in schema.get('$defs', {}).items():
                with self.subTest(schema=name, definition=key):
                    self.assertEqual(shared.setdefault(key, value), value,
                                     'a $defs entry must be the same in every schema that has it')


# --------------------------------------------------------- command line

def _run(*arguments):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)],
                          cwd=REPOSITORY, env=environment, capture_output=True, text=True, timeout=60)


class CommandLine(FixtureCopy):
    """Runs on a copy without results/, so it does not depend on results.check_results."""

    def setUp(self):
        super().setUp()
        shutil.rmtree(self.project / 'results')

    def test_clean_folder_exits_zero(self):
        completed = _run('check', self.project)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('0 errors, 0 warnings', completed.stdout)

    def test_broken_folder_exits_one_and_prints_each_problem(self):
        self.edit('datasets/waves.json', '/title', '')
        completed = _run('check', self.project)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn('error  datasets/waves.json  /title  ', completed.stdout)
        self.assertIn('1 error, 0 warnings', completed.stdout)

    def test_json_output_parses(self):
        self.edit('datasets/waves.json', '/title', '')
        completed = _run('check', self.project, '--json')
        self.assertEqual(completed.returncode, 1)
        report = json.loads(completed.stdout)
        self.assertFalse(report['ok'])
        self.assertEqual(report['problems'], [{'severity': 'error', 'path': 'datasets/waves.json',
                                               'pointer': '/title', 'message': report['problems'][0]['message']}])

    def test_warnings_alone_exit_zero_and_no_code_skips_lookups(self):
        self.edit('recipes/stepper-k1.json', '/run/settings_file', 'configs/missing.json')
        self.assertEqual(_run('check', self.project).returncode, 1)
        self.assertEqual(_run('check', self.project, '--no-code').returncode, 0)
        self.edit('models/stepper.json', '/earlier_work', {'rebuild': 'yes'})
        self.edit('models/stepper.json', '/config_file', 'configs/missing.json')
        self.edit('recipes/stepper-k1.json', '/run/settings_file', 'configs/train-k1.json')
        completed = _run('check', self.project)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn('warning  models/stepper.json  /config_file', completed.stdout)

    def test_usage_error_exits_two(self):
        self.assertEqual(_run('check').returncode, 2)
        self.assertEqual(_run('verify', self.project).returncode, 2)


class CommandLineOnFixture(unittest.TestCase):
    """The real fixture, results file included: depends on results.check_results (slice T2)."""

    def test_fixture_exits_zero(self):
        completed = _run('check', FIXTURE / 'project', '--json')
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['problems'], [])


if __name__ == '__main__':
    unittest.main()
