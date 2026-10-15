"""Actual inert captured-model publication and retained byte custody; no training."""
import copy
import hashlib
import json
import os
from unittest.mock import patch
from contextlib import contextmanager

from access import AccessError
from model_definitions import ModelDefinitions, natural, reference
from pipeline import digest
from test_external_runs import ExternalCase
from workbench import WorkbenchError


class CapturedModelCase(ExternalCase):
    def setUp(self):
        super().setUp()
        self.models=ModelDefinitions(self.dataset)
        self.model_body={'name':'Neutral captured model metadata','kind':'captured_source',
            'task':{'kind':'task','catalog_id':self.dataset.db.dataset_id,'id':'neutral.bytes',
                    'revision':1,'sha256':digest({'format':'authored_neutral_task_v1'})},
            'specification':{'format':'authored_neutral_model_v1'},
            'source_selector':{'project_id':self.manifest['id'],'recipe_id':'neutral',
                               'expected_sha256':hashlib.sha256(self.definition_raw).hexdigest()},
            'preprocessing_policy':{'kind':'identity'},'output_policy':{'kind':'exact_bytes'}}

    def create(self):
        with self.owner.bound(self.dataset):return self.models.create(self.model_body)

    def publish(self,draft):
        with self.owner.bound(self.dataset):return self.models.publish(draft['id'],{'revision':draft['revision']})


class ModelDefinitionTests(CapturedModelCase):

    def test_integer_and_reference_domains_reject_bool_unsafe_and_cross_catalog(self):
        for value in (True,-1,2**53,1.0,'1'):
            with self.subTest(value=value),self.assertRaises(WorkbenchError):natural(value,'test')
        self.assertEqual(natural(2**53-1,'test'),2**53-1)
        changed=dict(self.model_body['task'],catalog_id='a'*32)
        with self.assertRaises(WorkbenchError):reference(changed,'task',self.dataset.db.dataset_id)

    def test_publish_captures_exact_source_without_import_or_process_and_survives_draft_edit(self):
        draft=self.create()
        with patch('subprocess.run',side_effect=AssertionError('Publication must be inert')):
            published=self.publish(draft)
        self.assertEqual(published['material']['entrypoint'],'recipe.py')
        with self.owner.bound(self.dataset):
            sources={item['import_path']:self.models.read_blob(published['ref'],item['blob'])
                     for item in published['material']['source_closure']}
            self.assertEqual(sources['recipe.py'],self.source)
            changed=copy.deepcopy(draft);changed['specification']['new_width']=32
            saved=self.models.save(draft['id'],{'revision':1,'document':changed})
            self.assertEqual(saved['revision'],2)
            self.assertEqual(self.models.material(published['ref'],verify=True),published)
            self.assertEqual(self.models.publish(draft['id'],{'revision':1}),published)
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_stale_save_source_drift_and_missing_authority_leave_no_publication(self):
        draft=self.create();self.publish(draft)
        with self.owner.bound(self.dataset):
            self.models.save(draft['id'],{'revision':1,'document':draft})
            with self.assertRaises(WorkbenchError):self.models.save(draft['id'],{'revision':1,'document':draft})
        (self.project_path/'recipe.py').write_bytes(self.source+b'\n# source drift\n')
        with self.assertRaises(WorkbenchError):self.publish(dict(draft,revision=2))
        with self.dataset.access.bind(self.agent['token']),self.assertRaises(AccessError):
            self.models.create(self.model_body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_materials').fetchone()[0],1)

    def test_cold_material_refuses_blob_tampering_and_symlinks(self):
        published=self.publish(self.create());item=published['material']['source_closure'][0]['blob']
        path=self.models.path/published['ref']['sha256']/item['name'];original=path.read_bytes()
        path.chmod(0o600);path.write_bytes(b'x'*len(original))
        with self.owner.bound(self.dataset),self.assertRaises(WorkbenchError):
            self.models.material(published['ref'],verify=True)
        path.unlink();outside=self.path/'outside';outside.write_bytes(original);path.symlink_to(outside)
        with self.owner.bound(self.dataset),self.assertRaises(WorkbenchError):
            self.models.material(published['ref'],verify=True)

    def test_public_blob_read_requires_exact_published_model_and_inventory(self):
        published=self.publish(self.create());item=published['material']['source_closure'][0]['blob']
        wrong=dict(published['ref'],id='a'*32)
        with self.owner.bound(self.dataset):
            with self.assertRaises(WorkbenchError):self.models.read_blob(wrong,item)
            with self.assertRaises(WorkbenchError):self.models.read_blob(published['ref'],dict(item,name='source-9999.bin'))
            with self.assertRaises(WorkbenchError):self.models.read_blob(dict(published['ref'],revision=2),item)

    def test_required_audit_failure_rolls_back_model_and_cleans_new_files(self):
        draft=self.create()
        original=self.dataset.access.audit
        def fail(action,*args,**kwargs):
            if action=='models.publish':raise RuntimeError('Injected required audit failure')
            return original(action,*args,**kwargs)
        with patch.object(self.dataset.access,'audit',side_effect=fail),self.assertRaises(RuntimeError):
            self.publish(draft)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_materials').fetchone()[0],0)
        self.assertEqual(list(self.models.path.iterdir()),[])

    def test_owner_orphan_reconciliation_rejects_in_place_child_rewrite_after_hash(self):
        draft=self.create();published=self.publish(draft)
        with self.owner.bound(self.dataset),self.dataset.db.transaction():
            self.dataset.db.execute('DELETE FROM model_materials WHERE id=%s',(draft['id'],))
        target=self.models.path/published['ref']['sha256'];item=published['material']['source_closure'][0]['blob']
        child=target/item['name'];transaction=self.dataset.db.transaction
        @contextmanager
        def rewrite_after_hash(*args,**kwargs):
            before=target.stat();raw=child.read_bytes();child.chmod(0o600);child.write_bytes(b'x'*len(raw))
            after=target.stat();self.assertEqual((before.st_ino,before.st_mtime_ns,before.st_ctime_ns),
                                                (after.st_ino,after.st_mtime_ns,after.st_ctime_ns))
            with transaction(*args,**kwargs):yield
        with self.owner.bound(self.dataset),patch.object(self.dataset.db,'transaction',rewrite_after_hash):
            with self.assertRaises(WorkbenchError):self.models.publish(draft['id'],{'revision':1,'reconcile_capture':True})
        self.assertTrue(target.exists())
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_materials').fetchone()[0],0)
