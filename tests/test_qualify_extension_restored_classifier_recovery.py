"""Pure guards and actual retained receipt checks; never open a catalog."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import qualify_extension_restored_classifier_recovery as recovery


class RecoveryGuards(unittest.TestCase):
    def test_receipt_output_cannot_change_source_backup_restore_or_failed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);report={'source':str(root/'original'),'output':str(root/'core')}
            destination=root/'core/restored-catalog';failed=root/'failed'
            selected={'current_roots':{'a':str(root/'original-author')}}
            for parent in (root/'original',root/'core',root/'core/stopped-backup',destination,
                           root/'original-author',failed,recovery.Path(recovery.__file__).parents[1]):
                output=parent/'must-not-create'
                with self.subTest(parent=parent),self.assertRaises(recovery.transfer.StorageTransferError):
                    recovery.guard_recovery_output(report,destination,selected,failed,output)
                self.assertFalse(output.exists())
            recovery.guard_recovery_output(report,destination,selected,failed,root/'separate')

    def test_root_bookend_binds_inode_and_bytes_and_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir();path=source/'fixture.json';path.write_text('{}')
            first=recovery.root_state({'a':str(source)})
            path.write_text('{"changed":true}')
            self.assertNotEqual(first,recovery.root_state({'a':str(source)}))
            path.unlink();path.symlink_to(root/'other')
            with self.assertRaises(RuntimeError):recovery.root_state({'a':str(source)})


ACTUAL=Path('/workspace/shared/extension-ab-e4-inputs-01/classifier-recovery-source.json')


@unittest.skipUnless(ACTUAL.is_file(),'Requires the explicit completed actual restored classifier receipt set.')
class ActualHeldReceipts(unittest.TestCase):
    def test_actual_completed_source_binds_all_roles_before_any_catalog_open(self):
        sha=hashlib.sha256(ACTUAL.read_bytes()).hexdigest();source,docs,directory=recovery.sources(ACTUAL,sha)
        report,destination,database,report_sha=recovery.read_report(Path(source['retention_report']['path']))
        selected=recovery.retention.load_selection(Path(source['selection']['path']))
        args=(report,destination,database,report_sha,source['disabled_selection_report']['sha256'],selected)
        recovery.bind_completed(docs,*args)
        for change in ('run','material','settlement','source'):
            bad=copy.deepcopy(docs)
            if change=='run':bad['run']['id']='a'*32
            elif change=='material':bad['prepared']['trial']['material']['sha256']='a'*64
            elif change=='settlement':bad['study']['charged']['attempt_slots']=2
            else:bad['failure']['catalog_path']=report['source']
            with self.subTest(change=change),self.assertRaises(RuntimeError):recovery.bind_completed(bad,*args)

    def test_changed_held_document_hash_refuses_before_target_open(self):
        value=json.loads(ACTUAL.read_bytes());value['documents']['run']['sha256']='a'*64
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'source.json';path.write_text(json.dumps(value))
            with self.assertRaises(RuntimeError):
                recovery.sources(path,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
