"""The project of tests/browser_project_workspace_annotation_kinds.cjs: a Git repository with code/ and project/.

code/ holds examples/tiny-project's make_scenes.py (run here: three images, two point clouds, an array of frames
and a series) and its stand-in annotator, annotators/standin.py. project/ imports the scenes (datasets/scenes) and
has a task of each type the stand-in makes, each with two annotators: the stand-in at two thresholds, in
environments/test-python (the interpreter running the check, connected by the check). Prints the task names, the
annotators and the project's id as JSON.

    python tests/browser_annotation_kinds_fixture.py <repository directory>
"""
import json
import pathlib
import shutil
import subprocess
import sys
import uuid

EXAMPLE = pathlib.Path(__file__).resolve().parents[1] / 'examples' / 'tiny-project' / 'code'
GIT = ['git', '-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false',
       '-c', 'init.defaultBranch=main']
DEFINITION = 'tuldok_definition_v1'
# task -> (type, vocabulary, fields, thresholds of A and B)
TASKS = {
    'masks': ('mask', ['blob'], {'mask': 'instance'}, (160, 200)),
    'shapes': ('polygons', ['red', 'blue'], {}, (160, 200)),
    'depths': ('depth', None, {'units': 'm'}, (160, 200)),
    'corners': ('keypoints', ['red', 'blue'], {'keypoints': ['head', 'tail'], 'skeleton': [['head', 'tail']]},
                (160, 200)),
    'tops': ('points', ['top'], {}, (128, 140)),
    'boxes3d': ('box3d', ['top'], {}, (128, 140)),
    'stretches': ('timeseries', ['high'], {}, (160, 200)),
    'tracks': ('track', ['square'], {}, (160, 200)),
}


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main(repository):
    repository = pathlib.Path(repository)
    code, folder = repository / 'code', repository / 'project'
    (code / 'annotators').mkdir(parents=True)
    shutil.copyfile(EXAMPLE / 'make_scenes.py', code / 'make_scenes.py')
    shutil.copyfile(EXAMPLE / 'annotators' / 'standin.py', code / 'annotators' / 'standin.py')
    subprocess.run([sys.executable, 'make_scenes.py'], cwd=code, check=True)
    project_id = uuid.uuid4().hex
    write(folder / 'tuldok.json', {'format': 'tuldok_project_v1', 'id': project_id, 'name': 'Annotation kinds check',
                                   'code_root': '../code'})
    write(folder / 'environments' / 'test-python.json', {
        'format': DEFINITION, 'kind': 'environment', 'title': 'The interpreter running the check', 'python': '3.12',
        'device': 'cpu', 'packages': {'jsonschema': '4.26.0'}})
    write(folder / 'datasets' / 'scenes.json', {
        'format': DEFINITION, 'kind': 'dataset', 'title': 'Scenes',
        'run': {'step': 'import', 'settings': {'source': 'scenes', 'rights': 'Made for this check.'}}})
    annotators = []
    for name, (kind, vocabulary, fields, thresholds) in TASKS.items():
        task = {'format': DEFINITION, 'kind': 'annotation', 'title': f'The {name}', 'dataset': 'datasets/scenes',
                'task': kind, **fields}
        if vocabulary:
            task['vocabulary'] = vocabulary
        write(folder / 'annotations' / f'{name}.json', task)
        for letter, threshold in zip('ab', thresholds):
            reference = f'datasets/{name}-{letter}'
            annotators.append(reference)
            write(folder / f'{reference}.json', {
                'format': DEFINITION, 'kind': 'dataset', 'title': f'Stand-in {letter.upper()} on {name}',
                'run': {'step': 'annotate', 'inputs': {'records': 'datasets/scenes'},
                        'annotations': [f'annotations/{name}'],
                        'command': ['python', 'annotators/standin.py', str(threshold)],
                        'environment': 'environments/test-python',
                        'settings': {'by': {'kind': 'script', 'name': f'stand-in {letter.upper()}', 'version': '1'}}}})
    for arguments in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'The fixture.']):
        subprocess.run([*GIT, '-C', str(repository), *arguments], check=True)
    print(json.dumps({'project_id': project_id, 'tasks': {name: spec[0] for name, spec in TASKS.items()},
                      'annotators': annotators}))


if __name__ == '__main__':
    main(sys.argv[1])
