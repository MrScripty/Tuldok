"""Pre-target driver guards only; no catalog, Run or numerical qualification."""
import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

import qualify_main505_agent_authoring as driver


def advertised():
    rows=[]
    for name in dict.fromkeys((*driver.FIXED,*driver.AUTHORING)):
        rows.append(dict(id=name,contracts=[dict(version=driver.FIXED.get(name,1),authority='agent')]))
    rows.extend(dict(id=name,contracts=[dict(version=1,authority='owner')]) for name in driver.OWNER_ONLY)
    return dict(operations=rows)


class Main505AgentAuthoringGuards(unittest.TestCase):
    def test_new_negotiated_versions_and_existing_owner_authority_are_exact(self):
        with patch.object(driver.agent_api,'capabilities',return_value=advertised()):
            result=driver.required_contracts()
        self.assertEqual(result['recipes.inspect']['version'],3)
        self.assertEqual(result['models.publish']['version'],2)
        for name in ('graphs.create_external','graphs.preflight_external','studies.prepare_trial'):
            self.assertEqual(result[name]['version'],2)
        self.assertNotIn('studies.create',result)
        self.assertNotIn('studies.continue',result)

    def test_old_inspection_and_capture_versions_do_not_substitute(self):
        for name in ('recipes.inspect','models.publish','graphs.create_external',
                     'graphs.preflight_external','studies.prepare_trial'):
            with self.subTest(operation=name):
                value=advertised()
                row=next(row for row in value['operations'] if row['id']==name)
                row['contracts'][0]['version']-=1
                with patch.object(driver.agent_api,'capabilities',return_value=value),self.assertRaisesRegex(RuntimeError,'absent'):
                    driver.required_contracts()

    def test_missing_snapshot_operation_or_owner_only_agent_authoring_refuses(self):
        for change in ('missing','owner'):
            value=advertised()
            if change=='missing':value['operations']=[row for row in value['operations'] if row['id']!='project_snapshots.open']
            else:next(row for row in value['operations'] if row['id']=='models.publish')['contracts'][0]['authority']='owner'
            with patch.object(driver.agent_api,'capabilities',return_value=value),self.assertRaises(RuntimeError):
                driver.required_contracts()

    def test_study_authority_must_never_be_broadened_by_fixture(self):
        for name in driver.OWNER_ONLY:
            value=advertised()
            next(row for row in value['operations'] if row['id']==name)['contracts'][0]['authority']='agent'
            with patch.object(driver.agent_api,'capabilities',return_value=value),self.assertRaisesRegex(RuntimeError,'owner-only'):
                driver.required_contracts()

    def test_absent_new_api_refuses_before_any_target_mutation_or_runtime_read(self):
        workspace=driver.PARENT/(driver.PREFIX+uuid.uuid4().hex)
        args=argparse.Namespace(workspace=workspace,expected_runtime_sha256=driver.RUNTIME_SHA,
            expected_host_commit='f'*40,runtime_config=Path('/not-opened'),oracle_python=Path('/not-opened'))
        value=advertised();value['operations']=[row for row in value['operations'] if row['id']!='project_snapshots.list']
        with patch.object(driver.subprocess,'check_output',side_effect=['f'*40+'\n','']), \
             patch.object(driver.agent_api,'capabilities',return_value=value), \
             patch.object(driver.psycopg,'connect',side_effect=AssertionError('No database before reviewed API')) as database, \
             patch.object(driver,'Dataset',side_effect=AssertionError('No catalog before reviewed API')) as dataset, \
             patch.object(driver,'inventory',side_effect=AssertionError('No runtime read before reviewed API')) as runtime, \
             self.assertRaisesRegex(RuntimeError,'project_snapshots.list'):
            driver.main(args)
        self.assertFalse(workspace.exists())
        database.assert_not_called();dataset.assert_not_called();runtime.assert_not_called()

    def test_new_namespace_and_absent_direct_child_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary)
            target=parent/(driver.PREFIX+uuid.uuid4().hex)
            path,database=driver.guard_workspace(target,parent=parent)
            self.assertEqual(path,target)
            self.assertEqual(database,'tuldok_main505_agent_'+target.name[len(driver.PREFIX):])
            for wrong in (parent/'catalog',parent/'nested'/target.name):
                with self.assertRaises(RuntimeError):driver.guard_workspace(wrong,parent=parent)
            target.mkdir()
            with self.assertRaisesRegex(RuntimeError,'absent'):driver.guard_workspace(target,parent=parent)
            target.rmdir();target.symlink_to(parent,target_is_directory=True)
            with self.assertRaises(RuntimeError):driver.guard_workspace(target,parent=parent)

    def test_runtime_nomination_cannot_fall_back_before_source_or_target(self):
        workspace=driver.PARENT/(driver.PREFIX+uuid.uuid4().hex)
        args=argparse.Namespace(workspace=workspace,expected_runtime_sha256='0'*64)
        with patch.object(driver.subprocess,'check_output',side_effect=AssertionError('No source or target yet')), \
             self.assertRaisesRegex(RuntimeError,'main505 only'):
            driver.main(args)
        self.assertFalse(workspace.exists())

    def test_sdk_known_refusal_and_observed_run_are_preserved_without_retry(self):
        self.assertEqual(driver.sdk_admission_state(dict(state='passed',run_id='a'*32)),'completed')
        self.assertEqual(driver.sdk_admission_state(dict(state='failed',run_id='a'*32)),'run_observed')
        for state in ('refused','stale','unsupported'):
            self.assertEqual(driver.sdk_admission_state(dict(state=state)),'refused')
        for state in ('unavailable','unknown',None):
            self.assertEqual(driver.sdk_admission_state(dict(state=state)),'unknown')

    def test_measured_storage_includes_manifest_and_owner_capture_uses_full_reserve(self):
        measured=897*1024**2;manifest_bytes=3*1024**2+17
        reserve=3*320*1024**2+1024**3
        required=measured+manifest_bytes+reserve
        plan=driver.disk_plan(measured,manifest_bytes,required)
        self.assertEqual(plan['required_bytes'],required)
        self.assertEqual(plan['reserve_bytes'],reserve)
        self.assertEqual(plan['headroom_bytes'],1024**3)
        self.assertEqual(plan['capture_and_staging_bytes']+plan['headroom_bytes'],reserve)
        with self.assertRaisesRegex(RuntimeError,'Insufficient space'):
            driver.disk_plan(measured,manifest_bytes,required-1)
        # The reserve argument at the real owner boundary must match the exact
        # pre-target plan, rather than falling back to production's 6 GiB.
        owner=Mock()
        owner.inspect.return_value=dict(inventory_sha256=driver.RUNTIME_SHA,
            total_bytes=measured,manifest_bytes=manifest_bytes)
        config={'explicit_runtime_configuration':'test-only'}
        self.assertIs(driver.capture_runtime(owner,config,plan),owner.create.return_value)
        owner.create.assert_called_once_with(config,driver.RUNTIME_SHA,quiesced=True,reserve_bytes=reserve)
        from runtime_snapshots import DEFAULT_RESERVE
        self.assertEqual(DEFAULT_RESERVE,6*1024**3)

    def test_owner_capture_refuses_changed_manifest_before_create(self):
        plan=driver.disk_plan(100,10,100+10+3*320*1024**2+1024**3)
        for change in ({'manifest_bytes':11},{'total_bytes':101},{'inventory_sha256':'0'*64}):
            owner=Mock()
            owner.inspect.return_value=dict(inventory_sha256=driver.RUNTIME_SHA,total_bytes=100,manifest_bytes=10)
            owner.inspect.return_value.update(change)
            with self.assertRaisesRegex(RuntimeError,'differs'):
                driver.capture_runtime(owner,{},plan)
            owner.create.assert_not_called()
        for manifest in (0,True,-1):
            with self.assertRaisesRegex(RuntimeError,'canonical manifest'):
                driver.disk_plan(100,manifest,10**12)


if __name__=='__main__':unittest.main()
