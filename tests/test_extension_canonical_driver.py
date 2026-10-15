"""Representative driver guards; these fixtures are not admitted Run evidence."""
import copy
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import agent_api
import extension_evidence as evidence
import qualify_extension_canonical as driver


class CanonicalDriverGuards(unittest.TestCase):
    def test_oracle_context_identity_comes_from_independent_run_custody(self):
        raw=b'representative-context-bytes'
        expected=hashlib.sha256(raw).hexdigest()
        receipt=dict(name='execution-context.json',role='model_context',bytes=len(raw),sha256=expected)
        # Public runs.get exposes authoritative artifact receipts, never private spec.
        run=dict(artifacts=[receipt])
        self.assertEqual(driver.verify_context_custody(run,raw),expected)
        for mutated in (raw+b'x',b'X'+raw[1:]):
            with self.assertRaisesRegex(RuntimeError,'retained Run custody'):
                driver.verify_context_custody(run,mutated)
        receipt['bytes']=True
        with self.assertRaises(RuntimeError):driver.verify_context_custody(run,raw)
        receipt['bytes']=len(raw);receipt['role']='field_source'
        with self.assertRaises(RuntimeError):driver.verify_context_custody(run,raw)
        receipt['role']='model_context';run['artifacts'].append(dict(receipt))
        with self.assertRaises(RuntimeError):driver.verify_context_custody(run,raw)

    def test_existing_catalog_is_rejected_before_any_dataset_or_source_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog=Path(temporary)/'catalog';catalog.mkdir();marker=catalog/'unrelated.txt';marker.write_text('preserve')
            with patch.object(driver,'Dataset',side_effect=AssertionError('Existing catalog must not open')):
                with self.assertRaisesRegex(RuntimeError,'absent disposable catalog'):
                    driver.main(SimpleNamespace(catalog=catalog))
            self.assertEqual(marker.read_text(),'preserve')

    def test_missing_inference_authority_refuses_before_catalog_runtime_or_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);package=root/'package';shutil.copytree(driver.PACKAGE,package)
            for name in ('infer.py','inference-contract.json'):
                path=package/name
                if path.exists():path.unlink()
            with patch.object(driver,'PACKAGE',package),patch.object(driver,'Dataset',side_effect=AssertionError('No source activation yet')):
                with self.assertRaisesRegex(RuntimeError,'inference authority nomination is absent'):
                    driver.main(SimpleNamespace(catalog=root/'absent-catalog'))
            self.assertFalse((root/'absent-catalog').exists())

    def test_frozen_source_pin_enforces_actual_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project';shutil.copytree(driver.PACKAGE,project)
            driver.verify_frozen_sources(project)
            source=project/'producer.py';source.write_bytes(source.read_bytes()+b'\n# changed source\n')
            with self.assertRaisesRegex(RuntimeError,'Reviewed canonical source differs'):
                driver.verify_frozen_sources(project)

    def test_notice_source_pin_refuses_changed_accepted_rights_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project';shutil.copytree(driver.PACKAGE,project)
            source=project/'NOTICE.txt';source.write_bytes(source.read_bytes()+b'\nchanged\n')
            with self.assertRaisesRegex(RuntimeError,'Reviewed canonical source differs: NOTICE.txt'):
                driver.verify_frozen_sources(project)

    def test_timeout_observation_is_bounded_redacted_and_not_an_outcome(self):
        timeout=subprocess.TimeoutExpired(['sdk'],1,output=b'secret-token'+b'x'*300000,stderr=b'secret-token'+b'y'*70000)
        observed=driver.sdk_observation(timeout,'secret-token')
        self.assertNotIn('secret-token',str(observed))
        self.assertLessEqual(len(observed['stdout']),262144);self.assertLessEqual(len(observed['stderr']),65536)
        self.assertIsNone(observed['returncode']);self.assertNotIn('state',observed)

    def accounting(self):
        selection=dict(study_id='1'*32,trial_id='2'*32,actor_id='3'*32,admission_epoch=1,revision=4,
                       request_key='representative-request',approval_id='4'*32,expected=dict(material_sha256='5'*64))
        envelope=dict(attempt_slots=1,admitted_wall_seconds=197,retained_bytes=4226200,peak_staging_bytes=5771708)
        body={key:selection[key] for key in ('request_key','revision','admission_epoch','trial_id','approval_id')}
        request_sha=evidence.digest(dict(operation_id='studies.admit',version=1,contract_sha256=agent_api.contract('studies.admit',1)['sha256'],
                                         study_id=selection['study_id'],body=body))
        reservation={key:selection[key] for key in ('study_id','trial_id','actor_id','admission_epoch','request_key')}
        reservation.update(run_id='6'*32,material_sha256='5'*64,parent_run_id=None,state='settled',request_sha256=request_sha,
                           envelope=copy.deepcopy(envelope),settled=copy.deepcopy(envelope))
        return selection,dict(material=dict(resource_envelope=envelope)),dict(id='6'*32,parent_run_id=None),dict(request_sha256=request_sha),dict(charged=copy.deepcopy(envelope),reservations=[reservation])

    def test_all_four_actual_envelope_dimensions_and_identity_bindings_are_checked(self):
        values=self.accounting();driver.verify_accounting(*values)
        for container in ('charged','envelope','settled'):
            for dimension in ('attempt_slots','admitted_wall_seconds','retained_bytes','peak_staging_bytes'):
                selected,material,run,context,state=self.accounting()
                target=state['charged'] if container=='charged' else state['reservations'][0][container]
                target[dimension]+=1
                with self.subTest(container=container,dimension=dimension),self.assertRaises(RuntimeError):
                    driver.verify_accounting(selected,material,run,context,state)
        for key in ('study_id','trial_id','actor_id','admission_epoch','request_key','run_id','material_sha256','parent_run_id','request_sha256','state'):
            selected,material,run,context,state=self.accounting();state['reservations'][0][key]='changed'
            with self.subTest(key=key),self.assertRaises(RuntimeError):driver.verify_accounting(selected,material,run,context,state)
        selected,material,run,context,state=self.accounting();state['reservations'][0]['envelope']['attempt_slots']=True
        with self.assertRaises(RuntimeError):driver.verify_accounting(selected,material,run,context,state)
