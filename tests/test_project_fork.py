"""Independent fork publication: exact origins, verified bytes, no-clobber roots."""
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_fork as fork_module
from project_artifacts import ProjectArtifacts
from project_fork import ProjectForkError, active_records, decode_fork, publish_fork
from project_material import ProjectMaterial, decode_records as decode_material_records
from project_store import ProjectStore, ProjectStoreError, DIR_FLAGS
from test_project_material import model, SOURCE


def body(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate(records, project_id):
    decode_fork(records, project_id=project_id)
    decode_material_records(records)


class ForkFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tuldok-fork-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.root = self.path / 'projects'
        self.root.mkdir()
        self.root_fd = os.open(self.root, DIR_FLAGS)
        self.addCleanup(lambda: os.close(self.root_fd))
        self.source_path = self.root / 'source'
        self.source = ProjectStore.create(self.source_path, 'Source scientific intent', 'create-source', 'a' * 64)
        self.addCleanup(lambda: self.source.close())
        self.artifacts = ProjectArtifacts(self.source)
        self.addCleanup(self.artifacts.close)
        self.origin = self.source.snapshot()['project_id']
        self.material_value, payloads = model(self.origin)
        local = self.path / 'local-material'
        capture = local / self.material_value['ref']['sha256']
        capture.mkdir(parents=True)
        for name, raw in payloads.items():
            (capture / name).write_bytes(raw)
        session = SimpleNamespace(snapshot=self.source.snapshot(), artifacts=self.artifacts, check=lambda: None)
        self.material = ProjectMaterial(session)
        self.record = self.material.capture_model_material(self.material_value, local)
        records = [*self.material.declarations(self.record), self.record]
        self.original = self.source.commit(records, self.source.snapshot()['checkpoint'], 'retain', body(records))

    def candidate(self, source, destination):
        return dict(records=copy.deepcopy(source['records']), mapping=[], archived=[],
                    artifacts=[dict(declaration=copy.deepcopy(item['document']), preservation='unique')
                               for item in source['records'] if item['family'] == 'project_artifact'])

    def fork(self, relative='fork', **options):
        arguments = dict(root_path=self.root, name='Independent copy', expected_checkpoint=self.original['checkpoint'],
                         request_key='fork:one', quiescent=True, build_candidate=self.candidate, validate_candidate=validate)
        arguments.update(options)
        return publish_fork(self.source, self.artifacts, self.root_fd, relative, **arguments)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(ProjectStoreError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def canonical_bytes(self):
        return {p.relative_to(self.source_path).as_posix(): p.read_bytes()
                for p in self.source_path.rglob('*') if p.is_file() and '.tuldok-local' not in p.parts}

    def test_complete_fork_retains_exact_original_material_hashes_and_copies_without_aliases(self):
        before = self.canonical_bytes()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('No project execution')):
            result = self.fork()
        snapshot, overlay = result['snapshot'], result['fork']
        self.assertNotEqual(snapshot['project_id'], self.origin)
        self.assertFalse(result['reconciled'])
        self.assertEqual(overlay['source'], dict(project_id=self.origin, checkpoint=self.original['checkpoint']))
        self.assertEqual(next(item for item in snapshot['records'] if item['family'] == 'model_material'), self.record)
        with ProjectStore.open(self.root / 'fork') as destination, ProjectArtifacts(destination) as artifacts:
            reader = ProjectMaterial(SimpleNamespace(snapshot=destination.snapshot(), artifacts=artifacts, check=lambda: None))
            self.assertEqual(reader.model(self.material_value['ref'], verify=True), self.material_value)
            source_ref = self.material_value['material']['source_closure'][0]['blob']
            self.assertEqual(reader.blob(self.material_value['ref'], source_ref), SOURCE)
            for sha in overlay['artifacts']['copied']:
                old = self.source_path / 'artifacts/sha256' / sha
                new = self.root / 'fork/artifacts/sha256' / sha
                self.assertEqual(new.read_bytes(), old.read_bytes())
                self.assertNotEqual((new.stat().st_dev, new.stat().st_ino), (old.stat().st_dev, old.stat().st_ino))
                self.assertEqual(new.stat().st_nlink, 1)
            manifest = json.loads((self.root / 'fork/.tuldok/project.json').read_bytes())
            self.assertTrue(all(item['namespace'] == snapshot['project_id'] for item in manifest['inventory']))
        self.assertEqual(self.canonical_bytes(), before)

    def test_exact_retry_reconciles_and_changed_body_or_unrelated_destination_never_overwrites(self):
        first = self.fork()
        before = (self.root / 'fork/.tuldok/project.json').read_bytes()
        with patch.object(self, 'candidate', side_effect=AssertionError('Never repeat construction')):
            replay = self.fork()
        self.assertTrue(replay['reconciled'])
        self.assertEqual(replay['snapshot'], first['snapshot'])
        self.assert_code('conflict', self.fork, name='Different request')
        self.assertEqual((self.root / 'fork/.tuldok/project.json').read_bytes(), before)
        other = self.root / 'unrelated'
        with ProjectStore.create(other, 'Existing owner', 'other', 'b' * 64):
            pass
        unrelated = (other / '.tuldok/project.json').read_bytes()
        self.assert_code('conflict', self.fork, 'unrelated')
        self.assertEqual((other / '.tuldok/project.json').read_bytes(), unrelated)

    def test_quiescence_checkpoint_overlap_and_symlink_guards_precede_publication(self):
        before = self.canonical_bytes()
        self.assert_code('busy', self.fork, quiescent=False)
        self.assert_code('stale', self.fork, expected_checkpoint='f' * 64)
        self.assert_code('invalid', self.fork, 'source/nested-fork')
        self.assert_code('invalid', self.fork, 'source')
        alias = self.root / 'alias'
        alias.symlink_to(self.source_path, target_is_directory=True)
        self.assert_code('conflict', self.fork, 'alias')
        self.assert_code('invalid', self.fork, '../escape')
        self.assertEqual(self.canonical_bytes(), before)
        self.assertFalse((self.source_path / 'nested-fork').exists())

    def test_missing_unique_corrupt_and_source_hardlinks_block_without_final_destination(self):
        declaration = next(item['document'] for item in self.original['records'] if item['family'] == 'project_artifact')
        payload = self.source_path / 'artifacts/sha256' / declaration['sha256']
        raw = payload.read_bytes()
        payload.unlink()
        self.assert_code('unavailable', self.fork)
        self.assertFalse((self.root / 'fork').exists())
        payload.write_bytes(b'corrupt')
        self.assert_code('invalid', self.fork)
        payload.unlink()
        payload.write_bytes(raw)
        os.link(payload, self.path / 'unsafe-alias')
        self.assert_code('invalid', self.fork)
        self.assertFalse((self.root / 'fork').exists())
        self.assertEqual(self.source.snapshot(), self.original)

    def test_missing_regenerable_is_explicit_and_present_regenerable_is_still_copied(self):
        # Model evidence above remains unique. Two separate owner-declared cache
        # payloads exercise the explicit regenerable policy without downgrading it.
        caches = [b'Regenerable optional cache one', b'Regenerable optional cache two']
        declarations = [dict(format='project_artifact_v1', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)) for raw in caches]
        records = copy.deepcopy(self.original['records'])
        for raw, declaration in zip(caches, declarations):
            self.artifacts.publish_bytes(raw, declaration)
            records.append(dict(family='project_artifact', id=declaration['sha256'], document=declaration))
        self.original = self.source.commit(records, self.original['checkpoint'], 'cache-declarations', body(records))
        missing = declarations[0]['sha256']
        (self.source_path / 'artifacts/sha256' / missing).unlink()
        regenerable = {item['sha256'] for item in declarations}
        def candidate(source, destination):
            value = self.candidate(source, destination)
            for edge in value['artifacts']:
                if edge['declaration']['sha256'] in regenerable:
                    edge['preservation'] = 'regenerable'
            return value
        result = self.fork(build_candidate=candidate)
        self.assertEqual(result['fork']['artifacts']['missing_regenerable'], [missing])
        self.assertIn(declarations[1]['sha256'], result['fork']['artifacts']['copied'])
        self.assertEqual(len(result['fork']['artifacts']['copied']), len(records)-2)
        with ProjectStore.open(self.root / 'fork') as destination, ProjectArtifacts(destination) as owner:
            self.assertEqual(owner.status(declarations[0])['state'], 'missing')

    def test_invalid_candidate_or_omitted_inventory_retains_stage_and_source(self):
        before = self.canonical_bytes()
        def changed(source, destination):
            value = self.candidate(source, destination)
            next(item for item in value['records'] if item['family']=='project_artifact')['document']['bytes'] += 1
            return value
        error = self.assert_code('invalid', self.fork, build_candidate=changed)
        self.assertTrue(error.staging_directory.startswith('.tuldok-fork-'))
        self.assertFalse((self.root / 'fork').exists())
        def missing_plan(source, destination):
            value = self.candidate(source, destination)
            value['artifacts'] = []
            return value
        self.assert_code('invalid', self.fork, build_candidate=missing_plan)
        self.assertEqual(self.canonical_bytes(), before)

    def test_final_rename_race_never_overwrites_existing_destination(self):
        rename = fork_module._rename_noreplace
        target = self.root / 'fork'
        def race(parent, source, destination):
            if destination == 'fork':
                self.assertFalse(target.exists())
                target.mkdir()
                (target / 'owned.txt').write_bytes(b'Existing owner')
            rename(parent, source, destination)
        with patch.object(fork_module, '_rename_noreplace', side_effect=race):
            self.assert_code('conflict', self.fork)
        self.assertEqual(list(target.iterdir()), [target / 'owned.txt'])
        self.assertEqual((target / 'owned.txt').read_bytes(), b'Existing owner')

    def test_post_rename_fsync_failure_is_unknown_and_exact_retry_requires_fresh_barrier(self):
        sync = fork_module.os.fsync
        root = self.root.stat()
        def fail_final_parent(fd):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == (root.st_dev, root.st_ino) and (self.root / 'fork').exists():
                raise OSError(errno.EIO, 'fork parent durability unknown')
            return sync(fd)
        with patch.object(fork_module.os, 'fsync', side_effect=fail_final_parent):
            error = self.assert_code('unknown', self.fork)
            self.assertTrue(error.receipt['committed'])
            self.assertFalse(error.receipt['selected'])
            self.assert_code('unavailable', self.fork)
        reconciled = self.fork()
        self.assertTrue(reconciled['reconciled'])
        self.assertEqual(reconciled['snapshot']['project_id'], error.receipt['project_id'])
        self.assertEqual(self.source.snapshot(), self.original)

    def test_real_process_kill_before_and_after_destination_publication_is_coherent(self):
        self.artifacts.close()
        self.source.close()
        code = r'''
import copy,os,sys
import project_fork as m
from project_artifacts import ProjectArtifacts
from project_store import ProjectStore,DIR_FLAGS
from project_material import decode_records
root,window=sys.argv[1:]
source=ProjectStore.open(os.path.join(root,'source'))
artifacts=ProjectArtifacts(source)
rootfd=os.open(root,DIR_FLAGS)
rename=m._rename_noreplace
commit=ProjectStore.commit
def kill_rename(*args):
    if window=='before_rename':os._exit(77)
    rename(*args)
    if window=='after_rename':os._exit(77)
def kill_commit(*args,**kwargs):
    value=commit(*args,**kwargs)
    if window=='after_checkpoint':os._exit(77)
    return value
m._rename_noreplace=kill_rename
ProjectStore.commit=kill_commit
def build(snapshot,dest):
    return {'records':copy.deepcopy(snapshot['records']),'mapping':[],'archived':[],
        'artifacts':[{'declaration':item['document'],'preservation':'unique'}
            for item in snapshot['records'] if item['family']=='project_artifact']}
def validate(records,project):
    m.decode_fork(records,project_id=project);decode_records(records)
m.publish_fork(source,artifacts,rootfd,'fork',root_path=root,name='Independent copy',
    expected_checkpoint=source.snapshot()['checkpoint'],request_key='fork:one',quiescent=True,
    build_candidate=build,validate_candidate=validate)
raise AssertionError('Fault window was not reached')
'''
        for window in ('after_checkpoint', 'before_rename', 'after_rename'):
            with self.subTest(window=window):
                root = self.path / ('kill-' + window)
                root.mkdir()
                shutil.copytree(self.source_path, root / 'source')
                child = subprocess.run([sys.executable, '-c', code, str(root), window],
                    cwd=Path(fork_module.__file__).parent, capture_output=True, text=True, timeout=15)
                self.assertEqual(child.returncode, 77, child.stderr)
                self.assertEqual((root / 'fork').exists(), window == 'after_rename')
                with ProjectStore.open(root / 'source') as source, ProjectArtifacts(source) as artifacts:
                    self.assertEqual(source.snapshot(), self.original)
                    if window == 'after_rename':
                        rootfd = os.open(root, DIR_FLAGS)
                        try:
                            result = publish_fork(source, artifacts, rootfd, 'fork', root_path=root,
                                name='Independent copy', expected_checkpoint=self.original['checkpoint'],
                                request_key='fork:one', quiescent=True,
                                build_candidate=lambda *_: self.fail('Never repeat an already published fork'),
                                validate_candidate=validate)
                            self.assertTrue(result['reconciled'])
                        finally:
                            os.close(rootfd)
                    else:
                        stages = list(root.glob('.tuldok-fork-*'))
                        self.assertEqual(len(stages), 1)
                        with ProjectStore.open(stages[0]) as retained:
                            overlay = decode_fork(retained.snapshot()['records'])
                            self.assertEqual(overlay['source']['checkpoint'], self.original['checkpoint'])
                            self.assertEqual(next(item for item in retained.snapshot()['records']
                                if item['family']=='model_material'), self.record)

    def test_current_overlay_filters_receipts_and_original_editables_without_rewriting_history(self):
        source_id = 'a' * 32
        new_id = 'b' * 32
        # Structural mapping tests stay at this codec boundary; semantic data
        # origin construction is owned and tested by ProjectData's fork codec.
        originals = [dict(family='workbench_text', id=source_id, document={'format': 'workbench_text_v1'}),
                     dict(family='project_operation', id='c' * 64, document={'format': 'project_operation_v1'})]
        destination = dict(family='workbench_record', id=new_id, document={'format': 'workbench_record_v1'})
        identity = 'd' * 32
        source = dict(project_id='e' * 32, checkpoint='f' * 64)
        overlay = dict(format='project_fork_v1', source=source, destination_project_id=identity,
            request_key='fork:fixture', request_sha256=fork_module._digest(fork_module._input(source, 'copy', 'Copy', 'fork:fixture')),
            directory='copy', name='Copy', mapping=[dict(family='workbench_text', source_id=source_id,
            source_revision=1, destination_id=new_id)], archived=[dict(family=i['family'], id=i['id']) for i in sorted(originals, key=lambda i:(i['family'],i['id']))],
            artifacts=dict(copied=[], missing_regenerable=[]))
        current = dict(family='project_fork', id=identity, document=overlay)
        records = [*originals, destination, current]
        self.assertEqual(decode_fork(records, project_id=identity), overlay)
        self.assertEqual(active_records(records, project_id=identity), [destination, current])
        self.assertEqual(records[0], originals[0])
        bad = copy.deepcopy(records)
        bad[-1]['document']['mapping'][0]['source_revision'] = True
        self.assert_code('invalid', decode_fork, bad)
        bad = copy.deepcopy(records)
        bad[-1]['document']['mapping'][0]['destination_id'] = source_id
        self.assert_code('invalid', decode_fork, bad)


if __name__ == '__main__':
    unittest.main()
