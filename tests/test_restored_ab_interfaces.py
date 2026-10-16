"""Preparation guard regressions; no catalog open or actual qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_restored_ab_interfaces as witness


class RestoredClientGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.original=self.base/'original';self.original.mkdir()
        self.project=self.base/'project';self.project.mkdir()
        self.root=self.base/'retention';self.root.mkdir()
        self.restored=self.root/'restored-catalog';self.restored.mkdir()
        self.roots=self.base/'roots.json';self.roots.write_text(json.dumps({'project':str(self.project)}))
        self.selection=self.base/'selection.json'
        self.selection.write_text(json.dumps({'format':'extension_ab_retention_selection_v1','catalog_id':'a'*32,
            'current_roots':{'path':str(self.roots),'sha256':witness.sha(self.roots.read_bytes())}}))
        self.marker=self.restored/('.restore-receipt-'+'b'*64+'.json')
        self.marker.write_text(json.dumps({'kind':'postgresql-restore','backup_sha256':'b'*64,'dataset_id':'a'*32}))
        self.report=self.root/'report.json'
        self.report_value=dict(format='extension_ab_retention_qualification_v1',state='rootless_retention_verified_disable_pending',
            restored_database_retained=True,source_unchanged=True,rootless_warm=True,rootless_cold=True,
            restored_database='tuldok_ab_retention_'+'c'*32,source=str(self.original),output=str(self.root),
            selection_sha256=witness.sha(self.selection.read_bytes()),reviewed_references=json.loads(self.selection.read_bytes()),
            backup={'receipt_digest':'b'*64})
        self.report.write_text(json.dumps(self.report_value))

    def args(self,output):
        return argparse.Namespace(source=Path(witness.__file__).resolve().parents[1],retention_report=self.report,
            retention_sha256=witness.sha(self.report.read_bytes()),selection=self.selection,output=output,restored_copy_lease=True)

    def refuse(self,output,message):
        with patch('metadata.Metadata',side_effect=AssertionError('Metadata must not open')) as metadata:
            with self.assertRaisesRegex(AssertionError,message):witness.run(self.args(output))
            metadata.assert_not_called()
        self.assertFalse(output.exists())

    def test_all_original_restored_code_and_project_outputs_refuse_before_write_or_database(self):
        for protected in (self.original,self.restored,self.project,Path(witness.__file__).resolve().parents[1]):
            with self.subTest(protected=protected):self.refuse(protected/'no-write-output','Output overlaps')

    def test_symlink_alias_to_original_is_protected(self):
        alias=self.base/'alias';alias.symlink_to(self.original,target_is_directory=True)
        self.refuse(alias/'no-write-output','Output overlaps')

    def test_changed_current_roots_refuses_before_output_or_database(self):
        self.roots.write_text(json.dumps({'other':str(self.base/'other')}))
        self.refuse(self.base/'no-output','Reviewed reference changed')

    def test_report_parent_cannot_retarget_a_different_restore(self):
        self.report_value['output']=str(self.base/'other-retention')
        self.report.write_text(json.dumps(self.report_value))
        self.refuse(self.base/'no-output','Report output path differs')

    def test_restore_marker_binds_catalog_and_backup(self):
        self.marker.write_text(json.dumps({'kind':'postgresql-restore','backup_sha256':'b'*64,'dataset_id':'d'*32}))
        self.refuse(self.base/'no-output','Exact restore marker differs')

    def test_regular_receipt_symlink_is_refused(self):
        alias=self.base/'receipt-alias';alias.symlink_to(self.report)
        with self.assertRaises(OSError):witness.bounded(alias)


if __name__=='__main__':unittest.main()
