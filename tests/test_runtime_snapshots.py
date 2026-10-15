"""Offline capture authority and exact immutable publication (no model acceptance)."""
import copy
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from access import Access, AccessError
from metadata import Metadata
from runtime_snapshots import RuntimeSnapshots, inventory, canonical, sha, configuration
from workbench import WorkbenchError
import test_workspace_metadata as metadata_tests


class RuntimeSnapshotContract(unittest.TestCase):
    setUp = metadata_tests.WorkspaceMetadata.setUp
    cleanup_schemas = metadata_tests.WorkspaceMetadata.cleanup_schemas
    catalog = metadata_tests.WorkspaceMetadata.catalog

    def fixture(self):
        db=self.catalog(version=8);access=Access(db,db.path)
        token=access.exchange(access._local_owner_token(initial=True))['token']
        self.enterContext(access.bind(token))
        python=self.root/'source-python';site=self.root/'source-packages'
        (python/'bin').mkdir(parents=True);(python/'lib/python3.12/lib-dynload').mkdir(parents=True)
        shutil.copyfile('/usr/bin/true',python/'bin/python3.12')
        (python/'lib/python3.12/lib-dynload/fixture.txt').write_text('fixture only')
        (python/'lib/fixture.txt').write_text('not selected')
        names=[]
        for name in ('torch','numpy'):
            (site/name).mkdir(parents=True);(site/name/'__init__.py').write_text('fixture = True\n')
            info=site/(name+'-0.0.dist-info');info.mkdir()
            (info/'METADATA').write_text('Name: '+name+'\nVersion: 0.0\n')
            (info/'LICENSE').write_text('Test fixture')
            names.extend([name,info.name])
        config=dict(schema_version=1,python_root=str(python),python_version='3.12',site_packages=str(site),packages=names)
        # Explicit tiny fixture, not a runnable Python/model environment.
        owner=RuntimeSnapshots(db,access,db.path)
        return db,access,owner,config

    def test_exact_capture_survives_source_removal_and_reuses_without_overwrite(self):
        db,access,owner,config=self.fixture()
        observed=owner.inspect(config)
        # Ensure python/lib is a recorded launch directory via the stdlib descendants.
        value=owner.create(config,observed['inventory_sha256'],quiesced=True,reserve_bytes=0)
        root=Path(value['root']);manifest=(root/'manifest.json').read_bytes()
        self.assertEqual(sha(manifest),value['manifest_sha256'])
        self.assertEqual(value,owner.create(config,observed['inventory_sha256'],quiesced=True,reserve_bytes=0))
        shutil.rmtree(config['python_root']);shutil.rmtree(config['site_packages'])
        self.assertEqual(value,owner.get(value['manifest_sha256']))
        self.assertEqual((root/'packages/torch/__init__.py').read_bytes(),b'fixture = True\n')
        self.assertEqual((root/'packages/torch/__init__.py').stat().st_mode&0o777,0o400)
        self.assertFalse(list(owner.path.glob('.capture-*')))

    def test_backup_restore_keeps_cold_runtime_modes_and_refuses_changed_completed_modes(self):
        from backup_metadata import backup_catalog, restore_catalog, StorageTransferError
        db, access, owner, config = self.fixture()
        identity = owner.inspect(config)['inventory_sha256']
        value = owner.create(config, identity, quiesced=True, reserve_bytes=0)
        manifest = (Path(value['root']) / 'manifest.json').read_bytes()
        backup = self.root / 'backup-runtime'
        backup_catalog(db.path, backup, quiesced=True)
        metadata_tests.WorkspaceMetadata.drop(self, db)
        restored = self.root / 'restored-runtime'
        restore_catalog(backup, restored)
        restore_catalog(backup, restored)
        restored_executable = restored / Path(value['root']).relative_to(db.path) / 'python/bin/python3.12'
        restored_executable.chmod(0o400)
        with self.assertRaises(StorageTransferError):
            restore_catalog(backup, restored)
        restored_executable.chmod(0o500)
        current = Metadata(restored, create=False, schema_version=db.schema_version); self.addCleanup(current.close)
        restored_access = Access(current, restored)
        token = restored_access.exchange(restored_access._local_owner_token())['token']
        with restored_access.bind(token):
            actual = RuntimeSnapshots(current, restored_access, restored).get(identity)
        self.assertEqual((Path(actual['root']) / 'manifest.json').read_bytes(), manifest)
        executable = Path(actual['root']) / 'python/bin/python3.12'
        self.assertEqual(executable.stat().st_mode & 0o777, 0o500)
        executable.chmod(0o400)
        with self.assertRaises(StorageTransferError):
            restore_catalog(backup, restored)

    def test_unicode_nested_path_uses_shared_canonical_bytes(self):
        db,access,owner,config=self.fixture()
        (Path(config['site_packages'])/'torch'/'méta.txt').write_text('unicode entry')
        identity=owner.inspect(config)['inventory_sha256']
        value=owner.create(config,identity,quiesced=True,reserve_bytes=0)
        self.assertEqual(owner.get(identity),value)
        raw=(Path(value['root'])/'manifest.json').read_bytes()
        self.assertIn(b'm\\u00e9ta.txt',raw)

    def test_quiesced_lease_and_owner_are_required(self):
        db,access,owner,config=self.fixture();identity=owner.inspect(config)['inventory_sha256']
        with self.assertRaises(WorkbenchError):owner.create(config,identity,reserve_bytes=0)
        peer=Metadata(db.path,create=False,schema_version=db.schema_version);self.addCleanup(peer.close)
        self.assertTrue(peer.claim_runtime('workspace_runs'))
        with self.assertRaises(WorkbenchError):owner.create(config,identity,quiesced=True,reserve_bytes=0)
        peer.close()
        access.logout()
        with self.assertRaises(AccessError):owner.inspect(config)

    def test_inventory_drift_and_disk_shortage_never_publish(self):
        db,access,owner,config=self.fixture();identity=owner.inspect(config)['inventory_sha256']
        (Path(config['site_packages'])/'torch/__init__.py').write_text('changed')
        with self.assertRaises(WorkbenchError):owner.create(config,identity,quiesced=True,reserve_bytes=0)
        identity=owner.inspect(config)['inventory_sha256']
        with patch('runtime_snapshots.shutil.disk_usage',return_value=shutil._ntuple_diskusage(0,0,0)):
            with self.assertRaises(WorkbenchError):owner.create(config,identity,quiesced=True,reserve_bytes=1)
        self.assertFalse((owner.path/identity).exists())

    def test_missing_and_tampered_snapshot_are_domain_conflicts(self):
        db,access,owner,config=self.fixture()
        with self.assertRaises(WorkbenchError) as caught:owner.get('0'*64)
        self.assertEqual(caught.exception.status,409)
        identity=owner.inspect(config)['inventory_sha256']
        value=owner.create(config,identity,quiesced=True,reserve_bytes=0)
        file=Path(value['root'])/'packages/torch/__init__.py'
        file.chmod(0o600);file.write_text('tampered');file.chmod(0o400)
        with self.assertRaises(WorkbenchError) as caught:owner.get(identity)
        self.assertEqual(caught.exception.status,409)

    def test_retained_unknown_run_blocks_offline_capture(self):
        db,access,owner,config=self.fixture();identity=owner.inspect(config)['inventory_sha256']
        with db.transaction():
            db.execute('INSERT INTO workspace_runs(id,request_key,request_sha256,document) VALUES(%s,%s,%s,%s)',
                       ('held','held','0'*64,'{"state":"unknown"}'))
        with self.assertRaises(WorkbenchError):owner.create(config,identity,quiesced=True,reserve_bytes=0)
        self.assertFalse((owner.path/identity).exists())

    def test_copy_failure_removes_only_unpublished_staging(self):
        db,access,owner,config=self.fixture();identity=owner.inspect(config)['inventory_sha256']
        from runtime_snapshots import file_identity
        def changed(path,*,destination=None):
            value=file_identity(path,destination=destination)
            if destination is not None:value['sha256']='0'*64
            return value
        with patch('runtime_snapshots.file_identity',side_effect=changed):
            with self.assertRaises(WorkbenchError):owner.create(config,identity,quiesced=True,reserve_bytes=0)
        self.assertFalse((owner.path/identity).exists())
        self.assertFalse(list(owner.path.glob('.capture-*')))

    def test_full_verification_failure_prevents_publication(self):
        db,access,owner,config=self.fixture();identity=owner.inspect(config)['inventory_sha256']
        from recipe_process import ProcessError
        checked=[]
        def reject(value):
            checked.append(Path(value['root']))
            self.assertEqual(checked[-1].name,identity)
            self.assertEqual(checked[-1].parent.name,'runtime-snapshots')
            self.assertTrue(checked[-1].parent.parent.name.startswith('.capture-'))
            self.assertFalse((owner.path/identity).exists())
            raise ProcessError('injected whole-tree rejection')
        with patch('recipe_process.verify_cpu_snapshot',side_effect=reject):
            with self.assertRaises(WorkbenchError):
                owner.create(config,identity,quiesced=True,reserve_bytes=0)
        self.assertEqual(len(checked),1)
        self.assertFalse((owner.path/identity).exists())
        self.assertFalse(list(owner.path.glob('.capture-*')))

    def test_lost_success_audit_ack_keeps_verifiable_immutable_content(self):
        db,access,owner,config=self.fixture();identity=owner.inspect(config)['inventory_sha256']
        audit=access.audit
        def uncertain(action,*args,**kwargs):
            if action=='runtime_snapshots.create':raise RuntimeError('audit acknowledgement uncertain')
            return audit(action,*args,**kwargs)
        with patch.object(access,'audit',side_effect=uncertain):
            with self.assertRaisesRegex(RuntimeError,'uncertain'):
                owner.create(config,identity,quiesced=True,reserve_bytes=0)
        self.assertEqual(owner.get(identity)['manifest_sha256'],identity)

    def test_explicit_test_binary_exclusion_retains_required_sibling(self):
        db,access,owner,config=self.fixture()
        directory=Path(config['site_packages'])/'torch/bin';directory.mkdir()
        (directory/'test_api').write_bytes(b'excluded fixture')
        (directory/'torch_shm_manager').write_bytes(b'required sibling fixture')
        config['exclude_paths']=['torch/bin/test_api']
        manifest,_sources=inventory(config)
        paths={row['path'] for row in manifest['files']}
        self.assertNotIn('packages/torch/bin/test_api',paths)
        self.assertIn('packages/torch/bin/torch_shm_manager',paths)

    def test_closed_config_rejects_escaping_exclusions_and_source_links(self):
        db,access,owner,config=self.fixture()
        for key,value in [('exclude_paths',['torch/../numpy']),('exclude_paths',['torch-0.0.dist-info/LICENSE']),('stdlib_exclude_paths',['../x.so'])]:
            malformed=copy.deepcopy(config);malformed[key]=value
            with self.assertRaises(WorkbenchError):configuration(malformed)
        (Path(config['site_packages'])/'torch/escape').symlink_to('/etc/passwd')
        with self.assertRaises(WorkbenchError):inventory(config)


if __name__=='__main__':unittest.main()
